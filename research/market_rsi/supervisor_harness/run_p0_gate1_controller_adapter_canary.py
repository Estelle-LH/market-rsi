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


SCHEMA = "market_p0_gate1_controller_adapter_canary_v1"


def _decision() -> dict:
    options = expected_packet()["prospective_source_scope_decision"]
    pair = options["source_response_options"][1]
    split = options["split_policy"]
    cutoff = options["cutoff_contract"]
    return {
        "scientific_source_response": {
            "source_registry_entry_id": pair["source_registry_entry_id"],
            "response_class_id": pair["response_class_id"],
        },
        "intended_uses": {"requested_use_ids": ["model_training", "private_research"]},
        "future_role_split": {
            "requested_future_role": "train_candidate",
            "split_policy_id": split["split_policy_id"],
            "split_policy_sha256": split["split_policy_sha256"],
            "exposure_ledger_id": "not_yet_created",
        },
        "horizon_cutoff": {
            "claim_semantics": "prospective_point_in_time",
            "prediction_horizon_us": 60_000_000,
            "cutoff_semantics_id": cutoff["cutoff_semantics_id"],
            "cutoff_contract_sha256": cutoff["cutoff_contract_sha256"],
            "label_window_start_relation": "strictly_after_cutoff",
            "label_window_end_relation": "at_or_before_cutoff_plus_horizon",
        },
        "bounded_investigation": {
            "mode": "first_party_document_review_only",
            "max_documents_proposed": 1,
            "max_provider_requests_proposed": 0,
            "max_raw_bytes_proposed": 0,
            "max_elapsed_seconds_proposed": 300,
        },
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
    decision = load_json(adapter_root / "decision.json")
    provenance = load_json(adapter_root / "decision-provenance.json")
    passed = (
        adapter_result.get("valid_source_scope_decision") is True
        and adapter_result.get("execution_mode") == "offline_fake"
        and adapter_result.get("provider_called") is False
        and adapter_result.get("public_fetch_performed") is False
        and adapter_result.get("formal_data_admitted") is False
        and backend.encode_calls == 1
        and backend.sample_calls == 1
        and decision.get("decision_status") == "scope_only_non_executable"
        and all(value is False for value in decision["non_authority"].values())
        and provenance.get("all_external_authority_false") is True
        and not (adapter_root / "task.json").exists()
    )
    result = {
        "schema": SCHEMA,
        "cycle_id": cycle_id,
        "passed": passed,
        "adapter_result_sha256": file_hash(adapter_root / "result.json"),
        "claim_sha256": file_hash(claims / f"{cycle_id}.json"),
        "decision_sha256": file_hash(adapter_root / "decision.json"),
        "decision_provenance_sha256": file_hash(
            adapter_root / "decision-provenance.json"),
        "task_sha256": None,
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
