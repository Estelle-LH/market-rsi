"""Real score-free-provider canary for v2 semantic-bound materialization."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from market_rsi import digest, file_hash, fresh_json, load_json
from memory_policy.semantic_binding import structural_receipt
from memory_policy.study_v2 import (
    MATERIALIZATION_POLICY, long_exchange, worker_program,
)


SESSION = "2026-09-09T20"
ROLE = "diagnostic_canary"


def utc_day_start_ms(session: str) -> int:
    day = session.split("T", 1)[0]
    return int(datetime.strptime(day, "%Y-%m-%d").replace(
        tzinfo=timezone.utc).timestamp() * 1000)


def run(preflight_report, contract_report, output):
    preflight_report = Path(preflight_report).resolve()
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("fresh materialization-canary ID required")
    receipt = load_json(preflight_report)
    structural_receipt(receipt)
    if receipt.get("session") != SESSION or receipt.get("role") != ROLE:
        raise ValueError("only the fixed previously opened diagnostic source is allowed")
    value = load_json(contract_report)
    contract = value["spec"]["contract"]
    remote_path = "/opt/d10/derived/" + output.name + "/" + SESSION
    operation = {
        "date": SESSION,
        "path": "/opt/d10/raw/data/polymarket/polymarket-20260909T20.jsonl.zst",
        "output": remote_path,
        "compressed_bytes": receipt["advertised_bytes"],
        "contract": contract,
        "day_start_ms": utc_day_start_ms(SESSION),
        "role": ROLE,
        "commitments": [],
        "semantic_preflight_report": receipt,
        "resource_policy": MATERIALIZATION_POLICY,
    }
    output.mkdir()
    fresh_json(output / "claim.json", {
        "schema": "memory_policy_materialize_canary_claim_v2",
        "previously_opened_diagnostic_only": True,
        "preflight_report_sha256": file_hash(preflight_report),
        "operation_sha256": digest(operation),
        "provider_calls_allowed": 0,
    })
    report = long_exchange(worker_program(operation), output, MATERIALIZATION_POLICY)
    fresh_json(output / "report.json", report)
    header = report.get("header") or {}
    if (report.get("complete") is not True
            or report.get("semantic_preflight_reproduced") is not True
            or report.get("provider_calls") != 0
            or report.get("raw_rows_exported") != 0
            or header.get("shape", [0])[0] <= 0):
        raise ValueError("v2 materialization canary failed")
    result = {
        "schema": "memory_policy_materialize_canary_v2",
        "passed": True,
        "previously_opened_diagnostic_only": True,
        "session": SESSION,
        "selected_observations": report["selected_observations"],
        "derived_rows": header["shape"][0],
        "derived_bytes": header["bytes"],
        "elapsed_seconds": report["elapsed_seconds"],
        "peak_self_rss_kib_linux": report["peak_self_rss_kib_linux"],
        "semantic_preflight_reproduced": True,
        "provider_calls": 0,
        "raw_rows_exported": 0,
        "remote_cache_preserved": remote_path,
    }
    result["result_sha256"] = digest(result)
    fresh_json(output / "canary.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-report", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = run(args.preflight_report, args.contract, args.output)
    print({key: value[key] for key in (
        "passed", "selected_observations", "derived_rows", "elapsed_seconds",
        "provider_calls")})
