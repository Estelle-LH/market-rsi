"""Fixed two-row synthetic self-check candidate for the one-shot Docker canary.

This module is deliberately useless as a market model.  It returns two fixed
interior probabilities only after checking the narrow runtime boundary that
the synthetic canary is authorized to exercise.  It accepts no configuration,
data path, outcome, credential, provider, scorer, or durable output path.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import select
import socket
import stat
import sys
from pathlib import Path
from typing import Any


_RELEASE_FIELDS = {
    "schema", "run_id", "sequence", "row_id", "event_id", "market_id",
    "cutoff_ms", "feature_available_ms", "market_probability",
}
_ROWS = (
    {
        "event_id": "synthetic-isolation-event-000",
        "market_id": "synthetic-isolation-market-000",
        "cutoff_ms": 1_700_000_000_000,
        "feature_available_ms": 1_699_999_999_000,
        "market_probability": 0.4,
    },
    {
        "event_id": "synthetic-isolation-event-001",
        "market_id": "synthetic-isolation-market-001",
        "cutoff_ms": 1_700_000_060_000,
        "feature_available_ms": 1_700_000_059_000,
        "market_probability": 0.6,
    },
)
_PROBABILITIES = (0.25, 0.75)
_RUN_ID = re.compile(r"run-[0-9a-f]{64}\Z")
_SOURCE_DIRECTORY = Path("/opt/market-rsi")
_SOURCE_PATHS = {
    _SOURCE_DIRECTORY / "container_candidate_guest.py",
    _SOURCE_DIRECTORY / "candidate.py",
}
_ABSENT_PATHS = (
    Path("/Users/estelle/Library/Application Support/MarketRSI/"
         "synthetic-adapter-canaries/"
         "market-rsi-real-candidate-isolation-canary-20260929-01/"
         "adapter-host-decoy-synthetic.txt"),
    Path("/Users/estelle/Library/Application Support/MarketRSI/"
         "synthetic-adapter-canaries/"
         "market-rsi-real-candidate-isolation-canary-20260929-01/"
         "protocol-host-decoy-synthetic.txt"),
    Path("/var/run/docker.sock"),
    Path("/run/docker.sock"),
    Path("/run/secrets"),
    Path("/root/.aws"),
    Path("/root/.config/gcloud"),
    Path("/root/.ssh"),
    Path("/home/estelle/.aws"),
    Path("/home/estelle/.ssh"),
)
_EXPECTED_TMPFS_BYTES = 64 * 1024 * 1024
_EXPECTED_MEMORY_BYTES = 512 * 1024 * 1024
_sequence = 0
_bound_run_id: str | None = None


def _mounts() -> dict[str, tuple[str, frozenset[str]]]:
    result: dict[str, tuple[str, frozenset[str]]] = {}
    raw = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
    for line in raw.splitlines():
        left, separator, right = line.partition(" - ")
        if not separator:
            raise RuntimeError("malformed mountinfo")
        left_fields = left.split()
        right_fields = right.split()
        if len(left_fields) < 6 or len(right_fields) < 3:
            raise RuntimeError("malformed mountinfo record")
        mountpoint = left_fields[4].replace("\\040", " ")
        options = frozenset(left_fields[5].split(",")) | frozenset(
            right_fields[2].split(",")
        )
        result[mountpoint] = (right_fields[0], options)
    return result


def _read_positive_integer(path: Path) -> int:
    value = path.read_text(encoding="ascii").strip()
    if not value.isascii() or not value.isdecimal():
        raise RuntimeError(f"non-integer cgroup value: {path}")
    result = int(value)
    if result <= 0:
        raise RuntimeError(f"non-positive cgroup value: {path}")
    return result


def _check_cgroup() -> None:
    unified = Path("/sys/fs/cgroup/cgroup.controllers")
    if unified.is_file():
        if _read_positive_integer(Path("/sys/fs/cgroup/pids.max")) != 32:
            raise RuntimeError("pids.max differs from 32")
        if _read_positive_integer(Path("/sys/fs/cgroup/memory.max")) != _EXPECTED_MEMORY_BYTES:
            raise RuntimeError("memory.max differs from 512 MiB")
        cpu = Path("/sys/fs/cgroup/cpu.max").read_text(encoding="ascii").split()
        if len(cpu) != 2 or not all(value.isdecimal() for value in cpu):
            raise RuntimeError("finite cgroup v2 CPU quota required")
        quota, period = map(int, cpu)
    else:
        if _read_positive_integer(Path("/sys/fs/cgroup/pids/pids.max")) != 32:
            raise RuntimeError("pids.max differs from 32")
        memory_path = Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")
        if _read_positive_integer(memory_path) != _EXPECTED_MEMORY_BYTES:
            raise RuntimeError("memory limit differs from 512 MiB")
        quota = _read_positive_integer(Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us"))
        period = _read_positive_integer(Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us"))
    if quota != period:
        raise RuntimeError("CPU quota is not exactly one CPU")


def _check_mounts() -> None:
    mounts = _mounts()
    root = mounts.get("/")
    if root is None or "ro" not in root[1] or "rw" in root[1]:
        raise RuntimeError("container root is not read-only")
    if set(_SOURCE_DIRECTORY.iterdir()) != _SOURCE_PATHS:
        raise RuntimeError("source mount inventory differs from two-file allowlist")
    for path in _SOURCE_PATHS:
        metadata = path.stat(follow_symlinks=False)
        mount = mounts.get(str(path))
        if (not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o444
                or mount is None
                or "ro" not in mount[1]
                or "rw" in mount[1]
                or os.access(path, os.W_OK)):
            raise RuntimeError("source bind is not an exact read-only 0444 file")
    tmp = mounts.get("/tmp")
    if (tmp is None or tmp[0] != "tmpfs" or "rw" not in tmp[1]
            or not {"noexec", "nosuid", "nodev"}.issubset(tmp[1])):
        raise RuntimeError("/tmp is not the bounded hardened tmpfs")
    sizes = [value for value in tmp[1] if value.startswith("size=")]
    if len(sizes) != 1:
        raise RuntimeError("one tmpfs size commitment required")
    size = sizes[0][5:].lower()
    if size.endswith("k"):
        size_bytes = int(size[:-1]) * 1024
    elif size.endswith("m"):
        size_bytes = int(size[:-1]) * 1024 * 1024
    else:
        size_bytes = int(size)
    if size_bytes != _EXPECTED_TMPFS_BYTES:
        raise RuntimeError("/tmp size differs from 64 MiB")
    probe = Path("/tmp/synthetic-market-rsi-canary-probe")
    descriptor = os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(descriptor, b"synthetic-only\n")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    probe.unlink()
    if probe.exists():
        raise RuntimeError("temporary probe deletion failed")


def _check_network_denials() -> None:
    test_net = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    test_net.settimeout(0.2)
    try:
        code = test_net.connect_ex(("192.0.2.1", 9))
        if code == 0:
            raise RuntimeError("TEST-NET connection unexpectedly succeeded")
        if code not in {
            errno.EACCES, errno.EADDRNOTAVAIL, errno.EHOSTDOWN,
            errno.EHOSTUNREACH, errno.ENETDOWN, errno.ENETUNREACH,
            errno.ECONNREFUSED, errno.ETIMEDOUT,
        }:
            raise RuntimeError("unexpected TEST-NET connection result")
    finally:
        test_net.close()
    docker_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    docker_socket.settimeout(0.2)
    try:
        code = docker_socket.connect_ex("/var/run/docker.sock")
        if code == 0:
            raise RuntimeError("Docker socket unexpectedly reachable")
        if code not in {errno.EACCES, errno.ENOENT, errno.ENOTDIR, errno.ECONNREFUSED}:
            raise RuntimeError("unexpected Docker socket connection result")
    finally:
        docker_socket.close()


def _check_runtime() -> None:
    if os.geteuid() != 65534 or os.getegid() != 65534 or os.getgroups():
        raise RuntimeError("exact 65534:65534 identity without groups required")
    status = Path("/proc/self/status").read_text(encoding="ascii")
    if "NoNewPrivs:\t1" not in status:
        raise RuntimeError("NoNewPrivs is not set")
    if {name for _, name in socket.if_nameindex()} != {"lo"}:
        raise RuntimeError("only loopback may be visible")
    for path in _ABSENT_PATHS:
        if os.path.lexists(path):
            raise RuntimeError(f"forbidden host/credential path is visible: {path}")
    _check_mounts()
    _check_cgroup()
    _check_network_denials()


def _check_no_presend() -> None:
    descriptor = sys.stdin.buffer.fileno()
    was_blocking = os.get_blocking(descriptor)
    try:
        os.set_blocking(descriptor, False)
        try:
            buffered = sys.stdin.buffer.peek(1)
        except BlockingIOError:
            buffered = b""
    finally:
        os.set_blocking(descriptor, was_blocking)
    if buffered:
        raise RuntimeError("next stdin row was buffered before response")
    readable, _, _ = select.select([sys.stdin.buffer], [], [], 0)
    if readable:
        raise RuntimeError("next stdin row or EOF was visible before response")


def predict(public_row: dict[str, Any]) -> float:
    """Return one fixed synthetic probability after all boundary probes pass."""

    global _bound_run_id, _sequence
    if type(public_row) is not dict or set(public_row) != _RELEASE_FIELDS:
        raise ValueError("exact released-row schema required")
    if _sequence >= len(_ROWS) or public_row.get("sequence") != _sequence:
        raise ValueError("exact two-row sequence required")
    if public_row.get("schema") != "minimal_prediction_public_as_of_row_v1":
        raise ValueError("frozen public-row schema required")
    expected = _ROWS[_sequence]
    for key, value in expected.items():
        if public_row.get(key) != value or type(public_row.get(key)) is not type(value):
            raise ValueError("synthetic row differs from frozen content")
    run_id = public_row.get("run_id")
    row_id = public_row.get("row_id")
    expected_row_id = "row-" + hashlib.sha256(json.dumps(
        {"schema": "minimal_prediction_public_as_of_row_v1", "row": expected},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    if (type(run_id) is not str or _RUN_ID.fullmatch(run_id) is None
            or row_id != expected_row_id):
        raise ValueError("deterministic run/row identity required")
    if _bound_run_id is None:
        _bound_run_id = run_id
    elif run_id != _bound_run_id:
        raise ValueError("run identity changed across rows")
    _check_runtime()
    _check_no_presend()
    probability = _PROBABILITIES[_sequence]
    _sequence += 1
    return probability


__all__ = ["predict"]
