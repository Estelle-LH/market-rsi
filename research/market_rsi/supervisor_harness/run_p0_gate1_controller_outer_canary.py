"""Zero-paid synthetic canary for the Gate 1 state/budget transaction.

The canary deliberately substitutes a synthetic publication receipt and an
offline provider fake. It proves transaction ordering and reconciliation, not
Git publication, model authorship, provider spend, public fetching or data
admission. The production live entry has no such substitution surface.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from glm_canary import HF_MODEL
from market_rsi import digest, file_hash, fresh_json
from paid_budget import PaidBudget
from supervisor_harness import bounded_live_outer_runner_v3 as shared
from supervisor_harness import protocol_source_release
from supervisor_harness.global_state_gate import SupervisorGlobalState
from supervisor_harness.p0_gate1_controller_adapter import (
    OfflineGate1ProviderFake, PROPOSE_TOOL, SUBMIT_TOOL, expected_packet,
)
from supervisor_harness.p0_gate1_controller_outer import run_outer
from supervisor_harness.p0_data_gap_proposal import (
    FEEDBACK_SCHEMA, next_controller_input,
)


SCHEMA = "market_p0_gate1_controller_outer_canary_v1"


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


def _proposal() -> dict:
    return {
        "proposal_id": "gate1-outer-canary-novel-source",
        "kind": "new_source",
        "hypothesis": "A new public archive may contain missing fills.",
        "candidate_source": "One unregistered public archive",
        "method": "Check rights and one fixed game sample.",
        "fixed_sample_rule": "First game by public schedule order.",
        "expected_evidence": "Source revision, rights and raw fill receipt.",
        "stop_rule": "Stop on rights uncertainty or after one sample.",
        "max_requests": 3,
        "max_bytes": 1000000,
        "max_minutes": 10,
        "max_provider_cost_usd": "0",
    }


def _submission(value: dict, *, tool: str = SUBMIT_TOOL) -> str:
    arguments = []
    for key, item in value.items():
        encoded = item if isinstance(item, str) else json.dumps(
            item, separators=(",", ":"))
        arguments.append(
            f"<arg_key>{key}</arg_key><arg_value>{encoded}</arg_value>")
    return ("offline reasoning</think>\n"
            f"<tool_call>{tool}" + "".join(arguments)
            + "</tool_call>")


def execute(output: Path, *, proposal: bool = False,
            prior_canary_receipt: Path | None = None,
            prior_canary_sha256: str | None = None) -> dict:
    if proposal:
        raise ValueError("legacy proposal lane is not a D0 canary")
    if prior_canary_receipt is None or prior_canary_sha256 is None:
        raise ValueError("exact prior current-source canary receipt required")
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError("fresh Gate 1 outer canary output required")
    output.mkdir(parents=True, mode=0o700)
    decision_doc = output / "decision.md"
    decision_doc.write_text("synthetic Gate 1 outer canary only\n")
    state = SupervisorGlobalState(output / "global-state", decision_doc)
    state_before = state.initialize()
    budget_root = output / "budget"
    budget = PaidBudget.create(budget_root, {
        "experiment_id": "gate1-outer-canary-budget",
        "cap_usd": "1",
        "target_usd": "0.05",
        "buckets_usd": {"setup": "0.5", "repair": "0.5"},
        "authority": "zero-paid synthetic Gate 1 transaction canary",
    })
    claims = output / "claims"
    claims.mkdir(mode=0o700)
    cycle_id = output.name + "-transaction"
    packet = expected_packet()
    source_hashes = protocol_source_release.source_hashes()
    publication = {
        "schema": "market_rsi_protocol_publication_v1",
        "origin": "synthetic-offline-canary",
        "tag": "market-rsi-protocol-v-synthetic",
        "commit": "1" * 40,
        "tag_object": "2" * 40,
        "source_sha256": digest(source_hashes),
        "source_hashes": source_hashes,
        "isolation_proven": False,
        "model_authorship_proven": False,
    }
    runtime = shared.runtime_receipt()
    raw = _submission(_decision())
    backend = OfflineGate1ProviderFake({
        "text": raw,
        "output_tokens": [501, 502, 503],
        "cached_input_tokens": 0,
        "finish_reason": "stop",
        "provider": {
            "reported_model": HF_MODEL,
            "session_id": "offline-outer-canary-session",
            "sampling_session_id": "offline-outer-canary-sampling",
        },
    })
    with (patch(
            "supervisor_harness.p0_gate1_controller_outer._publication",
            return_value=publication),
          patch(
            "supervisor_harness.p0_gate1_controller_outer.shared._runtime",
            return_value=runtime)):
        outer_result = run_outer(
            root=output / cycle_id,
            claim_root=claims,
            state=state,
            budget=budget,
            budget_root=budget_root,
            experiment_id="gate1-outer-canary-budget",
            budget_cap_usd="1",
            cycle_id=cycle_id,
            packet=packet,
            expected_packet_sha256=digest(packet),
            expected_head_sha256=state_before["head_sha256"],
            expected_decision_sha256=file_hash(decision_doc),
            prior_canary_receipt=prior_canary_receipt,
            prior_canary_sha256=prior_canary_sha256,
            release_tag="market-rsi-protocol-v-synthetic",
            expected_release_commit="1" * 40,
            expected_release_tag_object="2" * 40,
            expected_source_sha256=digest(source_hashes),
            expected_runtime=runtime,
            check_clear=lambda task_id: {
                "schema": "market_bounded_live_outer_preflight_v3",
                "cycle_id": task_id,
                "clear": True,
                "matching_process_ids": [],
                "matching_container_ids": [],
            },
            backend=backend,
        )
    budget_after = budget.snapshot()
    state_after = state.snapshot()
    job = budget_after["jobs"][cycle_id]
    next_input_sha256 = None
    passed = (
        outer_result.get("passed") is True
        and outer_result.get("submission_kind") == "source_scope_decision"
        and outer_result.get("execution_mode") == "offline_fake"
        and job.get("state") == "metered_terminal"
        and state_after.get("active_cycle") is None
        and state_after.get("last_review_sha256") != "0" * 64
        and backend.encode_calls == 1
        and backend.sample_calls == 1
    )
    result = {
        "schema": SCHEMA,
        "cycle_id": cycle_id,
        "passed": passed,
        "outer_result_sha256": file_hash(output / cycle_id / "result.json"),
        "review_sha256": file_hash(output / cycle_id / "review.json"),
        "task_sha256": None,
        "proposal_sha256": None,
        "decision_sha256": file_hash(
            output / cycle_id / "adapter" / cycle_id / "decision.json"),
        "next_controller_input_sha256": next_input_sha256,
        "submission_kind": outer_result.get("submission_kind"),
        "synthetic_ledger_metered_usd": job["metered_usd"],
        "provider_calls": 0,
        "actual_provider_cost_usd": "0",
        "public_fetch_performed": False,
        "formal_data_admitted": False,
        "synthetic_publication_substituted": True,
    }
    fresh_json(output / "canary-result.json", result)
    if not passed:
        raise RuntimeError("Gate 1 outer transaction canary failed")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--proposal", action="store_true",
                        help="retired; retained only to fail closed")
    parser.add_argument("--prior-canary-receipt", type=Path)
    parser.add_argument("--prior-canary-sha256")
    args = parser.parse_args()
    print(json.dumps(execute(
        args.output, proposal=args.proposal,
        prior_canary_receipt=args.prior_canary_receipt,
        prior_canary_sha256=args.prior_canary_sha256), sort_keys=True))
