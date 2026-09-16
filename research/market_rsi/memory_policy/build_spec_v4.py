"""Build v4 only from fresh score-free admission and the frozen common contract."""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

from market_rsi import file_hash, fresh_json, load_json
from memory_policy.build_spec_v2 import validate_admission
from memory_policy.spec_v3 import validate as validate_v3
from memory_policy.spec_v4 import (
    TERMINAL_CAPACITY_GATE, V3_FAILURE_SHA256, V3_OPENED_DEV,
    validate as validate_v4,
)


def selected_observations(admission_root, selected):
    by_session = {}
    for directory in sorted(path for path in Path(admission_root).iterdir()
                            if path.is_dir()):
        report_path = directory / "report.json"
        if report_path.exists():
            report = load_json(report_path)
            by_session[report["session"]] = report
    return sum(
        by_session[row["session"]]["semantic_receipt"]["selected_observations"]
        for role in ("initial_train", "dev") for row in selected[role]
    )


def build(admission_root, plan_path, prior_spec_path, failure_path,
          output, experiment_id):
    plan, complete, selected = validate_admission(admission_root, plan_path)
    prior = validate_v3(load_json(prior_spec_path))
    failure_path = Path(failure_path).resolve()
    failure = load_json(failure_path)
    if (file_hash(failure_path) != V3_FAILURE_SHA256
            or failure.get("experiment_id") != "memory-policy-v3-20260915-01"
            or failure.get("status") != "invalidated_no_same_run_retry"
            or failure.get("round_3_dev_opened") is not False
            or failure.get("prior_dev_results_exposed") is not True
            or failure.get("same_run_resume_allowed") is not False):
        raise ValueError("exact closed v3 failure disposition required")
    if any(session not in plan["prior_exposure"] for session in V3_OPENED_DEV):
        raise ValueError("v3 opened Dev must be excluded before v4 admission")
    if selected_observations(admission_root, selected) > 10_000_000:
        raise ValueError("v4 cumulative Train resource gate failed")

    spec = {
        "schema": "market_rsi_memory_policy_v4",
        "experiment_id": experiment_id,
        "question": prior["question"],
        "changed_stage": prior["changed_stage"],
        "arms": deepcopy(prior["arms"]),
        "component_hashes": deepcopy(prior["component_hashes"]),
        "fixed_contract": deepcopy(prior["fixed_contract"]),
        "source_integrity": deepcopy(prior["source_integrity"]),
        "candidate_admission": {
            "schema": complete["schema"],
            "artifact_sha256": file_hash(Path(admission_root) / "complete.json"),
            "selection_rule": plan["selection_rule"],
            "target_statistics_computed": 0,
            "fits": 0,
            "provider_calls": 0,
        },
        "trainer_resource_gate": deepcopy(prior["trainer_resource_gate"]),
        "terminal_capacity_gate": deepcopy(TERMINAL_CAPACITY_GATE),
        "supersedes": {
            "experiment_id": "memory-policy-v3-20260915-01",
            "failure_status": "invalidated_no_same_run_retry",
            "failure_disposition_sha256": file_hash(failure_path),
            "opened_dev_sessions": list(V3_OPENED_DEV),
            "artifacts_reused_for_training": False,
            "scientific_change": "none",
            "shared_harness_fix": "controller_terminal_submission_capacity",
        },
        "initial_train": selected["initial_train"],
        "dev": selected["dev"],
        "final": selected["final"],
        "rounds": 8,
        "minimum_final_sessions": 20,
        "formal_promotion": False,
        "stop_policy": deepcopy(prior["stop_policy"]),
        "retry_policy": deepcopy(prior["retry_policy"]),
        "budget": deepcopy(prior["budget"]),
        "prior_exposure": {"opened_sessions": sorted(plan["prior_exposure"])},
        "claim_limits": {
            "distinct_final_utc_dates": 4,
            "evidence_class":
                "three-arm fresh-evidence terminal-capacity-repaired memory-policy rerun",
            "formal_promotion_claim": False,
            "general_rsi_claim": False,
            "profitability_claim": False,
        },
    }
    validate_v4(spec)
    fresh_json(output, spec)
    return spec


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--prior-spec", type=Path, required=True)
    parser.add_argument("--failure-disposition", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--experiment-id", required=True)
    args = parser.parse_args()
    value = build(args.admission, args.plan, args.prior_spec,
                  args.failure_disposition, args.output, args.experiment_id)
    print({"experiment_id": value["experiment_id"],
           "train": len(value["initial_train"]),
           "dev": len(value["dev"]), "final": len(value["final"])})
