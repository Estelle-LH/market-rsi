"""Execute the broker's bounded public-string canary in the researcher guest.

This is deliberately not a general research worker or an isolation proof. The
trusted host must independently verify the result and its source sandbox ID.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


MAX_ORDER_BYTES = 64 * 1024


def execute(order: dict) -> dict:
    required = {"schema", "cycle_id", "input_sha256", "decision_sha256",
                "task_id", "task_type", "data_role", "public_text"}
    if (not isinstance(order, dict) or set(order) != required
            or order["schema"] != "market_broker_researcher_order_v1"
            or order["task_type"] != "code_canary"
            or order["data_role"] != "synthetic_fixture"
            or not isinstance(order["public_text"], str)
            or not 0 < len(order["public_text"].encode("utf-8")) <= 4096):
        raise ValueError("researcher order is outside the synthetic canary lane")
    for name in ("cycle_id", "task_id"):
        if (not isinstance(order[name], str) or not order[name]
                or len(order[name]) > 128):
            raise ValueError("invalid order identifier")
    for name in ("input_sha256", "decision_sha256"):
        value = order[name]
        if (not isinstance(value, str) or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)):
            raise ValueError("invalid order hash")
    canonical = json.dumps(order, sort_keys=True, separators=(",", ":"),
                           allow_nan=False).encode("utf-8")
    return {"schema": "market_broker_researcher_result_v1",
            "cycle_id": order["cycle_id"],
            "order_sha256": hashlib.sha256(canonical).hexdigest(),
            "decision_sha256": order["decision_sha256"],
            "task_id": order["task_id"],
            "text_sha256": hashlib.sha256(order["public_text"].encode("utf-8")).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order", type=Path, default=Path("/tmp/market-researcher/order.json"))
    parser.add_argument("--result", type=Path, default=Path("/tmp/market-researcher/result.json"))
    args = parser.parse_args()
    if (args.order.is_symlink() or not args.order.is_file()
            or args.order.stat().st_size > MAX_ORDER_BYTES
            or args.result.exists() or args.result.is_symlink()):
        raise ValueError("missing, oversized, or reused researcher artifact")
    order = json.loads(args.order.read_bytes())
    result = execute(order)
    with args.result.open("x", encoding="utf-8") as output:
        json.dump(result, output, sort_keys=True, separators=(",", ":"))


if __name__ == "__main__":
    main()
