"""Zero-paid acceptance canary for the Gate 1 one-response Controller adapter."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from glm_canary import HF_MODEL
from market_rsi import file_hash, fresh_json, load_json
from supervisor_harness.p0_gate1_controller_adapter import (
    OfflineGate1ProviderFake, SUBMIT_TOOL, expected_packet, run,
)
from supervisor_harness.p0_gate1_research_contract import DECISION_SCHEMA


SCHEMA = "market_p0_gate1_controller_adapter_canary_v1"


def _decision() -> dict:
    return {
        "schema": DECISION_SCHEMA,
        "investigation_id": "gate1-offline-source-plan",
        "question_id": "2025_whole_season_trade_access",
        "source_id": "polymarket_official_trades",
        "hypothesis": "The official interface documents historical market trade access.",
        "fixed_sample_rule": "Inspect the one frozen official documentation page.",
        "requested_operations": ["inspect_official_documentation"],
        "expected_evidence": "A bounded page hash and documented interface fields.",
        "rights_check": "Record only rights stated by the official source.",
        "max_requests": 1,
        "max_bytes": 100000,
        "max_minutes": 10,
        "max_provider_cost_usd": "0",
        "stop_rule": "Stop after one response or any redirect, error, timeout, or rights uncertainty.",
    }


def _submission(value: dict) -> str:
    arguments = []
    for key, item in value.items():
        encoded = item if isinstance(item, str) else json.dumps(
            item, separators=(",", ":"))
        arguments.append(
            f"<arg_key>{key}</arg_key><arg_value>{encoded}</arg_value>")
    return ("offline reasoning</think>\n"
            f"<tool_call>{SUBMIT_TOOL}" + "".join(arguments)
            + "</tool_call>")


def execute(output: Path) -> dict:
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError("fresh Gate 1 canary output required")
    output.mkdir(parents=True, mode=0o700)
    claims = output / "claims"
    claims.mkdir(mode=0o700)
    cycle_id = output.name
    raw = _submission(_decision())
    backend = OfflineGate1ProviderFake({
        "text": raw,
        "output_tokens": [301, 302, 303],
        "cached_input_tokens": 0,
        "finish_reason": "stop",
        "provider": {
            "reported_model": HF_MODEL,
            "session_id": "offline-gate1-session",
            "sampling_session_id": "offline-gate1-sampling-session",
        },
    })
    adapter_root = output / cycle_id
    adapter_result = run(
        root=adapter_root,
        claim_root=claims,
        cycle_id=cycle_id,
        packet=expected_packet(),
        backend=backend,
    )
    task = load_json(adapter_root / "task.json")
    passed = (
        adapter_result.get("valid_plan_only_decision") is True
        and adapter_result.get("execution_mode") == "offline_fake"
        and adapter_result.get("provider_called") is False
        and adapter_result.get("public_fetch_performed") is False
        and adapter_result.get("formal_data_admitted") is False
        and backend.encode_calls == 1
        and backend.sample_calls == 1
        and task.get("execution_boundary") == {
            "plan_only": True,
            "network_fetch_authorized": False,
            "purchase_authorized": False,
            "sealed_or_scored_data_authorized": False,
            "formal_admission_authorized": False,
        }
    )
    result = {
        "schema": SCHEMA,
        "cycle_id": cycle_id,
        "passed": passed,
        "adapter_result_sha256": file_hash(adapter_root / "result.json"),
        "claim_sha256": file_hash(claims / f"{cycle_id}.json"),
        "decision_sha256": file_hash(adapter_root / "decision.json"),
        "task_sha256": file_hash(adapter_root / "task.json"),
        "provider_calls": 0,
        "provider_cost_usd": "0",
        "synthetic_only": True,
        "public_fetch_performed": False,
        "formal_data_admitted": False,
    }
    fresh_json(output / "canary-result.json", result)
    if not passed:
        raise RuntimeError("Gate 1 Controller adapter canary failed")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    print(json.dumps(execute(parser.parse_args().output), sort_keys=True))
