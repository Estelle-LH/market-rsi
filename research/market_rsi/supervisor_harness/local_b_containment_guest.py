"""Pre-reviewed synthetic arbitrary-code probe for one local B container.

Only fresh synthetic decoy paths are attempted.  This is deliberately not a
general researcher worker and never reads a paid credential or market data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import socket


SCHEMA = "market_local_b_containment_order_v1"
RESULT_SCHEMA = "market_local_b_containment_event_v1"
TEST_NETWORK_ADDRESS = ("192.0.2.1", 9)


def canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: dict) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _read_order(root: Path) -> dict:
    path = root / "orders" / "000.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("bounded synthetic order missing")
    order = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(order, dict)
            or set(order) != {"schema", "cycle_id", "artifact_root",
                              "public_text", "decoy_paths"}
            or order["schema"] != SCHEMA
            or not isinstance(order["cycle_id"], str)
            or not order["cycle_id"].startswith("local-b-containment-")
            or not isinstance(order["public_text"], str)
            or not order["public_text"].startswith("synthetic-public-")
            or not isinstance(order["decoy_paths"], dict)
            or set(order["decoy_paths"]) != {"host", "controller", "key"}):
        raise ValueError("invalid synthetic containment order")
    artifact_root = Path(order["artifact_root"])
    if (artifact_root.parent != Path("/private/tmp")
            or not artifact_root.name.startswith(order["cycle_id"] + "-")):
        raise ValueError("decoy root must be a fresh synthetic temporary root")
    expected = {
        "host": artifact_root / "host-only" / "host-decoy.txt",
        "controller": artifact_root / "controller-only" / "a-context-decoy.txt",
        "key": artifact_root / "key-only" / "fake-key-decoy.txt"}
    if order["decoy_paths"] != {name: str(path) for name, path in expected.items()}:
        raise ValueError("decoy paths differ from the reviewed synthetic set")
    return order


def _denied_read(path: str) -> tuple[bool, str]:
    try:
        Path(path).read_bytes()
    except OSError as exc:
        return True, type(exc).__name__
    return False, "ReadSucceeded"


def _denied_write() -> tuple[bool, str]:
    # Existing parent directory in the read-only container root, never a host
    # bind mount.  No path in a user home or protected Market RSI tree is used.
    try:
        Path("/opt/market-rsi/containment-escape-decoy.txt").write_text("synthetic")
    except OSError as exc:
        return True, type(exc).__name__
    return False, "WriteSucceeded"


def _denied_network() -> tuple[bool, str]:
    # TEST-NET-1 documentation address, not a paid service or user endpoint.
    try:
        with socket.create_connection(TEST_NETWORK_ADDRESS, timeout=0.5):
            pass
    except OSError as exc:
        return True, type(exc).__name__
    return False, "ConnectSucceeded"


def run(root: Path) -> dict:
    root = Path(root)
    if root != Path("/work/directional") or root.is_symlink() or not root.is_dir():
        raise ValueError("containment guest needs the exact B work mount")
    order = _read_order(root)
    reads = {name: _denied_read(path) for name, path in order["decoy_paths"].items()}
    write_denied, write_error = _denied_write()
    network_denied, network_error = _denied_network()
    positive = root / "positive-control.txt"
    with positive.open("x", encoding="utf-8") as output:
        output.write(order["public_text"])
    positive_ok = positive.read_text(encoding="utf-8") == order["public_text"]
    event = {
        "schema": RESULT_SCHEMA, "cycle_id": order["cycle_id"],
        "order_sha256": digest(order),
        "public_text_sha256": hashlib.sha256(order["public_text"].encode()).hexdigest(),
        "decoy_reads_denied": {name: item[0] for name, item in reads.items()},
        "decoy_read_error_types": {name: item[1] for name, item in reads.items()},
        "root_write_denied": write_denied,
        "root_write_error_type": write_error,
        "test_net_connect_denied": network_denied,
        "test_net_error_type": network_error,
        "positive_work_write_and_read": positive_ok,
        "synthetic_only": True, "model_authorship_proven": False,
        "full_isolation_proven": False}
    events = root / "events"
    events.mkdir(mode=0o700)
    path = events / "000.json"
    with path.open("x", encoding="utf-8") as output:
        output.write(canonical(event) + "\n")
    if json.loads(path.read_text(encoding="utf-8")) != event:
        raise RuntimeError("allowed B work channel did not round-trip")
    print(canonical(event), flush=True)
    if (not all(event["decoy_reads_denied"].values())
            or not write_denied or not network_denied or not positive_ok):
        raise RuntimeError("synthetic containment probe observed a boundary breach")
    return event


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--per-order-timeout", type=float, required=True)
    parser.add_argument("--total-timeout", type=float, required=True)
    args = parser.parse_args()
    if args.per_order_timeout != 10 or args.total_timeout != 120:
        raise ValueError("unexpected pinned B command timeouts")
    run(args.root)


if __name__ == "__main__":
    main()
