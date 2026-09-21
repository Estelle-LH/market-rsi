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
    OfflineGate1ProviderFake, SUBMIT_TOOL, expected_packet,
)
from supervisor_harness.p0_gate1_controller_outer import run_outer
from supervisor_harness.p0_gate1_research_contract import DECISION_SCHEMA


SCHEMA = "market_p0_gate1_controller_outer_canary_v1"


def _decision() -> dict:
    return {
        "schema": DECISION_SCHEMA,
        "investigation_id": "gate1-outer-canary-plan",
        "question_id": "2025_whole_season_trade_access",
        "source_id": "polymarket_official_trades",
        "hypothesis": "The official interface documents historical market trade access.",
        "fixed_sample_rule": "Inspect the one frozen official documentation page.",
        "requested_operations": ["inspect_official_documentation"],
        "expected_evidence": "A bounded page hash and documented interface fields.",
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
            prior_canary_sha256=file_hash(Path(__file__)),
            release_tag="market-rsi-protocol-v-synthetic",
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
    passed = (
        outer_result.get("passed") is True
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
        "task_sha256": file_hash(
            output / cycle_id / "adapter" / cycle_id / "task.json"),
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
    print(json.dumps(execute(parser.parse_args().output), sort_keys=True))
