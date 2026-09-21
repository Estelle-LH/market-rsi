"""Zero-provider canary for the exact historical Gate 1 packet artifact."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from market_rsi import digest, fresh_json, load_json
from supervisor_harness.p0_gate1_controller_adapter import expected_packet
from supervisor_harness.p0_gate1_controller_supervisor_parent import (
    _preflight_packet,
)


SCHEMA = "market_p0_gate1_packet_preflight_canary_v1"


def execute(packet: Path, receipt: Path, output: Path) -> dict:
    packet, receipt, output = Path(packet), Path(receipt), Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError("fresh Gate 1 packet canary output required")
    receipt_value = load_json(receipt)
    if receipt_value.get("schema") != "market_p0_gate1_packet_receipt_v1":
        raise ValueError("unexpected Gate 1 packet receipt")
    observed = _preflight_packet(SimpleNamespace(
        packet=packet,
        expected_packet_file_sha256=receipt_value["packet_sha256"],
        expected_packet_canonical_sha256=digest(expected_packet()),
    ))
    output.mkdir(parents=True, mode=0o700)
    result = {
        "schema": SCHEMA,
        "passed": True,
        **observed,
        "provider_calls": 0,
        "provider_cost_usd": "0",
        "child_started": False,
        "run_id_claimed": False,
        "formal_data_admitted": False,
    }
    fresh_json(output / "canary-result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    print(json.dumps(execute(**vars(parser.parse_args())), sort_keys=True))
