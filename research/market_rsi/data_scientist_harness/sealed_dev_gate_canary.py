"""Create an auditable synthetic canary for the one-shot sealed-Dev gate."""
from __future__ import annotations

import argparse
from pathlib import Path

from market_rsi import digest, file_hash, fresh_json
from data_scientist_harness.research_cycle_contract import (
    begin_discovery,
    complete_discovery,
    freeze_confirmation,
)
from data_scientist_harness.sealed_dev_gate import SealedDevGate, data_commitment


def run(output: Path) -> dict:
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("fresh canary output required")
    fixtures = output / "synthetic-fixtures"
    fixtures.mkdir(parents=True)
    train = fixtures / "opened-train.csv"
    dev = fixtures / "sealed-dev.csv"
    eligibility = fixtures / "eligible-dev-cohort.json"
    evaluator = fixtures / "frozen-evaluator.py"
    train.write_text("x,y\n0,0\n1,1\n")
    dev.write_text("x,y\n2,2\n3,3\n")
    eligibility.write_text('{"ids":["synthetic-dev"]}\n')
    evaluator.write_text("# Synthetic canary evaluator; no market score.\n")

    release = {
        "harness_version": "synthetic-sealed-dev-canary-v1",
        "release_sha256": digest({"fixture": "release"}),
        "commit": "0" * 40,
        "tag": "synthetic-only",
        "published": True,
        "canary_sha256": digest({"fixture": "prior-canary"}),
    }
    discovery = begin_discovery(release, {
        "discovery_id": "synthetic-discovery",
        "broad_problem": "Verify the execution boundary without market data.",
        "allowed_research_types": ["research_tooling"],
        "accessible_data_roles": ["opened_train", "synthetic_canary"],
        "maximum_iterations": 1,
        "maximum_cost_usd": 0.0,
        "required_outputs": ["candidate", "negative-test"],
        "primary_reward": None,
        "formal_claims_allowed": False,
        "route_dev_access": False,
        "sealed_final_access": False,
    })
    fresh_json(output / "01-discovery-start.json", discovery)
    completion = complete_discovery(discovery, {
        "discovery_id": "synthetic-discovery",
        "trace_sha256": digest({"trace": "synthetic"}),
        "opened_data_hashes": {"opened-train": file_hash(train)},
        "literature_record_ids": [],
        "candidate_graphs": [{
            "candidate_id": "identity-candidate",
            "research_type": "research_tooling",
            "question": "Does the gate enforce the preregistered evaluation?",
            "method": "Claim the one-shot allowance before opening the synthetic Dev file.",
            "evidence_refs": ["opened-train", "negative-test"],
            "evaluation_idea": "Record one result and prove a second claim is rejected.",
            "previously_untried_in_project": True,
        }],
        "iterations_completed": 1,
        "cost_usd": 0.0,
        "route_dev_opened": False,
        "sealed_final_opened": False,
        "terminal_cleanup_passed": True,
    })
    fresh_json(output / "02-discovery-complete.json", completion)
    confirmation = freeze_confirmation(completion, {
        "confirmation_id": "synthetic-confirmation",
        "selected_candidate_id": "identity-candidate",
        "research_question": "Does the persistent gate reject a second Dev view?",
        "claim_type": "execution_canary_not_scientific",
        "baseline_id": "no-persistent-gate",
        "primary_metric": "second_view_rejected",
        "reward_direction": "maximize",
        "target_spec_sha256": sha("2"),
        "evaluator_spec_sha256": file_hash(evaluator),
        "eligible_data_sha256": file_hash(eligibility),
        "untouched_data_role": "route_dev_one_shot",
        "secondary_metrics": ["reward_mutation_rejected", "data_mutation_rejected"],
        "constraints": ["synthetic fixtures only", "zero provider calls"],
        "disqualifiers": ["second Dev claim succeeds", "reward changes after freeze"],
        "maximum_cost_usd": 0.0,
        "maximum_evaluation_uses": 1,
        "reward_locked_before_results": True,
        "reward_change_after_results_allowed": False,
        "evaluation_evidence_output": {
            "kind": "scalar_terminal_v1", "metric": "second_view_rejected",
            "persist_terminal_record_runner_private": True,
            "public_visibility": "aggregate_only",
        },
    })
    fresh_json(output / "03-reward-lock.json", confirmation)
    gate = SealedDevGate.reserve(output / "04-sealed-gate", confirmation,
                                 eligibility, evaluator)
    gate.register_materialization({"synthetic-dev": dev}, {
        "eligible_data_sha256": file_hash(eligibility),
        "selection_count": 1,
        "materialized_count": 1,
        "excluded_count": 0,
        "scored": False,
        "labels_summarized": False,
        "source_manifest_sha256": digest({"synthetic": "materializer"}),
    })
    claim = gate.claim_once("synthetic-eval-1")
    # The canary runner, not a Controller, now owns the private paths.  The
    # synthetic score checks only that the frozen file remains readable.
    result = {
        "second_view_rejected": True,
        "synthetic_dev_sha256": file_hash(claim["dev_files"]["synthetic-dev"]),
        "scientific_score": False,
    }
    receipt = gate.record_result("synthetic-eval-1", result)
    try:
        gate.claim_once("synthetic-eval-2")
    except ValueError as error:
        second_claim = {"rejected": True, "reason": str(error)}
    else:
        raise AssertionError("one-shot Dev gate allowed a second claim")
    fresh_json(output / "05-negative-test.json", second_claim)
    summary = {
        "schema": "sealed_dev_gate_canary_v1",
        "passed": second_claim["rejected"],
        "scientific_score": False,
        "market_data_opened": False,
        "provider_calls": 0,
        "evaluation_uses": receipt["evaluation_uses"],
        "second_view_rejected": second_claim["rejected"],
        "reward_frozen_before_evaluation": True,
        "dev_frozen_before_evaluation": True,
        "confirmation_sha256": confirmation["record_sha256"],
        "journal_sha256": file_hash(gate.private / "journal.jsonl"),
        "receipt_sha256": file_hash(gate.public / "evaluation-receipt.json"),
    }
    summary["result_sha256"] = digest(summary)
    fresh_json(output / "complete.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(run(args.output))


if __name__ == "__main__":
    main()
