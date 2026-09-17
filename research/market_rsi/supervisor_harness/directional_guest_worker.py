"""One-process, zero-paid guest half of the 20-order directional canary.

The host owns the broker, cycle gate, sandbox, timing and cleanup. This worker
only reads synthetic public-text orders inside B and writes hash-bound receipts.
It does not execute supplied code, call a model, use the network, or read keys.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable


DEFAULT_ROOT = Path("/tmp/market-researcher/directional")
EXPECTED_ORDERS = 20
MAX_ORDER_BYTES = 64 * 1024
MAX_PUBLIC_TEXT_BYTES = 4096
_IDENTIFIER = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _digest(value: dict) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON member")
        value[key] = item
    return value


def _read_file(path: Path) -> tuple[bytes, tuple[int, int, int, int, int]]:
    """Read a regular, bounded file without following a final-component link."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"unsafe or missing guest artifact: {path.name}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_ORDER_BYTES:
            raise ValueError(f"missing, empty, or oversized guest artifact: {path.name}")
        raw = os.read(fd, MAX_ORDER_BYTES + 1)
        after = os.fstat(fd)
        identity = (after.st_dev, after.st_ino, after.st_size,
                    after.st_mtime_ns, after.st_ctime_ns)
        if (len(raw) != before.st_size or len(raw) > MAX_ORDER_BYTES
                or (before.st_dev, before.st_ino, before.st_size,
                    before.st_mtime_ns, before.st_ctime_ns) != identity):
            raise ValueError(f"guest artifact changed while reading: {path.name}")
        return raw, identity
    finally:
        os.close(fd)


def _read_order(path: Path) -> tuple[dict, tuple[bytes, tuple[int, int, int, int, int]]]:
    raw, identity = _read_file(path)
    try:
        order = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid guest order JSON") from exc
    if not isinstance(order, dict):
        raise ValueError("guest order must be an object")
    return order, (raw, identity)


def _verify_unchanged(path: Path, snapshot: tuple[bytes, tuple[int, int, int, int, int]]) -> None:
    if _read_file(path) != snapshot:
        raise ValueError(f"guest order mutated: {path.name}")


def _validate_order(order: dict, sequence: int,
                    cycle_id: str | None, input_sha256: str | None,
                    task_ids: set[str]) -> tuple[str, str]:
    required = {"schema", "cycle_id", "input_sha256", "sequence", "task_id",
                "task_sha256", "public_text"}
    if set(order) != required or order["schema"] != "market_directional_order_v1":
        raise ValueError("guest order schema mismatch")
    if type(order["sequence"]) is not int or order["sequence"] != sequence:
        raise ValueError("guest order sequence mismatch")
    for name in ("cycle_id", "task_id"):
        if not isinstance(order[name], str) or not _IDENTIFIER.fullmatch(order[name]):
            raise ValueError(f"invalid {name}")
    for name in ("input_sha256", "task_sha256"):
        if not isinstance(order[name], str) or not _SHA256.fullmatch(order[name]):
            raise ValueError(f"invalid {name}")
    public_text = order["public_text"]
    if (not isinstance(public_text, str)
            or not 0 < len(public_text.encode("utf-8")) <= MAX_PUBLIC_TEXT_BYTES):
        raise ValueError("synthetic public text is empty or oversized")
    if cycle_id is not None and order["cycle_id"] != cycle_id:
        raise ValueError("cycle changed during guest session")
    if input_sha256 is not None and order["input_sha256"] != input_sha256:
        raise ValueError("A input changed during guest session")
    if order["task_id"] in task_ids:
        raise ValueError("duplicate guest task ID")
    task = {"schema": "market_directional_task_v1",
            "cycle_id": order["cycle_id"],
            "input_sha256": order["input_sha256"],
            "sequence": sequence, "task_id": order["task_id"],
            "public_text": public_text}
    if order["task_sha256"] != _digest(task):
        raise ValueError("guest order does not bind exact A task")
    return order["cycle_id"], order["input_sha256"]


def _ensure_dirs(root: Path) -> tuple[Path, Path, Path]:
    if root.is_symlink():
        raise ValueError("directional root is a symlink")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("unsafe directional root")
    dirs = tuple(root / name for name in ("orders", "acks", "events"))
    for directory in dirs:
        if directory.is_symlink():
            raise ValueError("directional directory is a symlink")
        directory.mkdir(mode=0o700, exist_ok=True)
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError("unsafe directional directory")
    if any(any(d.iterdir()) for d in dirs[1:]):
        raise ValueError("guest output directory is not fresh")
    return dirs


def _check_entries(orders: Path, acks: Path, events: Path, sequence: int) -> None:
    if any(directory.is_symlink() or not directory.is_dir()
           for directory in (orders.parent, orders, acks, events)):
        raise ValueError("directional directory changed or is unsafe")
    allowed_orders = {f"{n:03d}.json" for n in range(EXPECTED_ORDERS)}
    for entry in orders.iterdir():
        if entry.name not in allowed_orders or entry.is_symlink() or not entry.is_file():
            raise ValueError("unexpected or unsafe guest order entry")
        if int(entry.stem) < sequence:
            continue  # Checked byte-for-byte by the snapshot check below.
    expected_outputs = {f"{n:03d}.json" for n in range(sequence)}
    for directory in (acks, events):
        if {entry.name for entry in directory.iterdir()} != expected_outputs:
            raise ValueError("duplicate, missing, or premature guest output")
        if any(entry.is_symlink() or not entry.is_file() for entry in directory.iterdir()):
            raise ValueError("unsafe guest output entry")


def _publish(directory: Path, sequence: int, value: dict) -> tuple[Path, tuple[bytes, tuple[int, int, int, int, int]]]:
    """Publish complete bytes atomically, with exclusive destination creation."""
    destination = directory / f"{sequence:03d}.json"
    fd, temporary = tempfile.mkstemp(prefix=f".{sequence:03d}-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(_canonical(value))
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, destination)
    finally:
        os.unlink(temporary)
    directory_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    snapshot = _read_file(destination)
    if snapshot[0] != _canonical(value):
        raise ValueError("published guest artifact differs from intended bytes")
    return destination, snapshot


def _milestone(sequence: int, kind: str) -> None:
    value = {"schema": "market_directional_guest_milestone_v1",
             "sequence": sequence, "kind": kind}
    sys.stdout.write(_canonical(value).decode("utf-8") + "\n")
    sys.stdout.flush()


def run(root: Path = DEFAULT_ROOT, *, poll_interval: float = 0.01,
        per_order_timeout: float = 10.0, total_timeout: float = 360.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep) -> None:
    """Process exactly 20 sequential orders in one guest process/session."""
    if (not 0 < poll_interval <= 1 or not 0 < per_order_timeout <= 60
            or not 0 < total_timeout <= 3600):
        raise ValueError("invalid polling or timeout bound")
    orders, acks, events = _ensure_dirs(Path(root))
    start = clock()
    cycle_id = input_sha256 = None
    task_ids: set[str] = set()
    snapshots: list[tuple[Path, tuple[bytes, tuple[int, int, int, int, int]]]] = []
    published: list[tuple[Path, tuple[bytes, tuple[int, int, int, int, int]]]] = []
    for sequence in range(EXPECTED_ORDERS):
        deadline = min(start + total_timeout, clock() + per_order_timeout)
        path = orders / f"{sequence:03d}.json"
        while True:
            _check_entries(orders, acks, events, sequence)
            for old_path, snapshot in snapshots:
                _verify_unchanged(old_path, snapshot)
            for old_path, snapshot in published:
                _verify_unchanged(old_path, snapshot)
            if path.exists() or path.is_symlink():
                break
            if clock() >= deadline:
                raise TimeoutError(f"guest order {sequence:03d} timed out")
            sleep(min(poll_interval, max(0.0, deadline - clock())))
        if clock() > deadline:
            raise TimeoutError(f"guest order {sequence:03d} exceeded deadline")
        order, snapshot = _read_order(path)
        cycle_id, input_sha256 = _validate_order(
            order, sequence, cycle_id, input_sha256, task_ids)
        order_sha = _digest(order)
        text_sha = hashlib.sha256(order["public_text"].encode("utf-8")).hexdigest()
        ack = {"schema": "market_directional_ack_v1", "cycle_id": cycle_id,
               "sequence": sequence, "order_sha256": order_sha}
        event = {"schema": "market_directional_tool_event_v1",
                 "cycle_id": cycle_id, "sequence": sequence,
                 "task_id": order["task_id"], "order_sha256": order_sha,
                 "tool_name": "hash_public_text", "input_sha256": text_sha,
                 "output_sha256": text_sha, "status": "ok"}
        _verify_unchanged(path, snapshot)
        published.append(_publish(acks, sequence, ack))
        _milestone(sequence, "ack")
        _verify_unchanged(path, snapshot)
        published.append(_publish(events, sequence, event))
        _milestone(sequence, "event")
        snapshots.append((path, snapshot))
        task_ids.add(order["task_id"])
    _check_entries(orders, acks, events, EXPECTED_ORDERS)
    for path, snapshot in snapshots:
        _verify_unchanged(path, snapshot)
    for path, snapshot in published:
        _verify_unchanged(path, snapshot)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--poll-interval", type=float, default=0.01)
    parser.add_argument("--per-order-timeout", type=float, default=10.0)
    parser.add_argument("--total-timeout", type=float, default=360.0)
    args = parser.parse_args()
    run(args.root, poll_interval=args.poll_interval,
        per_order_timeout=args.per_order_timeout,
        total_timeout=args.total_timeout)


if __name__ == "__main__":
    main()
