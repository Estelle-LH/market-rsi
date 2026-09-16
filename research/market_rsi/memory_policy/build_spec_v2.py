"""Build the v2 spec only from a complete score-free candidate admission."""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

from market_rsi import digest, file_hash, fresh_json, load_json
from memory_policy.candidate_source_admission import (
    admission_source_hashes, select, validate_plan,
)
from memory_policy.semantic_source_preflight import validate_report
from memory_policy.spec import validate as validate_v1
from memory_policy.spec_v2 import RETRY_POLICY, SOURCE_INTEGRITY, validate as validate_v2


def validate_failed_report(row, report):
    if (report.get("complete") is not False
            or report.get("session") != row["session"]
            or report.get("role") != row["role"]
            or report.get("advertised_bytes") != row["compressed_bytes"]
            or not isinstance(report.get("failure"), dict)
            or any(report.get(key) != 0 for key in (
                "raw_rows_exported", "target_statistics_computed", "fits", "provider_calls"))):
        raise ValueError("bounded score-free failed candidate receipt required")


def validate_admission(root, plan_path):
    root = Path(root).resolve()
    plan_path = Path(plan_path).resolve()
    if (root / "failure.json").exists():
        raise ValueError("failed candidate admission cannot freeze a spec")
    plan = load_json(plan_path)
    groups = validate_plan(plan)
    claim = load_json(root / "claim.json")
    complete = load_json(root / "complete.json")
    selected_file = load_json(root / "selected-manifest.json")
    signed = dict(complete)
    result_sha256 = signed.pop("result_sha256", None)
    if (result_sha256 != digest(signed)
            or complete.get("schema") != "memory_policy_candidate_admission_v1"
            or complete.get("complete") is not True
            or complete.get("plan_sha256") != file_hash(plan_path)
            or complete.get("source_hashes") != admission_source_hashes()
            or claim.get("source_hashes") != complete["source_hashes"]
            or claim.get("plan_sha256") != complete["plan_sha256"]
            or complete.get("target_statistics_computed") != 0
            or complete.get("provider_calls") != 0
            or complete.get("fits") != 0
            or complete.get("raw_rows_exported") != 0
            or complete.get("selected_manifest") != selected_file):
        raise ValueError("candidate admission identity or zero-score boundary failed")
    ordered = [row for group in groups for row in group["candidates"]]
    results = {}
    for index, row in enumerate(ordered):
        report_path = root / f"{index:03d}-{row['role']}-{row['session']}" / "report.json"
        report = load_json(report_path)
        if report.get("complete") is True:
            validate_report(row, report)
        else:
            validate_failed_report(row, report)
        results[row["session"]] = report
    selected, rejected = select(groups, results)
    if selected != selected_file or rejected != complete.get("rejected"):
        raise ValueError("candidate selection is not reproducible from receipts")
    return plan, complete, selected


def build(root, plan_path, prior_spec_path, output, experiment_id):
    plan, complete, selected = validate_admission(root, plan_path)
    prior = validate_v1(load_json(prior_spec_path))
    spec = {
        "schema": "market_rsi_memory_policy_v2",
        "experiment_id": experiment_id,
        "question": "Which controller memory representation works best?",
        "changed_stage": "controller_memory_representation",
        "arms": deepcopy(prior["arms"]),
        "component_hashes": deepcopy(prior["component_hashes"]),
        "fixed_contract": deepcopy(prior["fixed_contract"]),
        "source_integrity": deepcopy(SOURCE_INTEGRITY),
        "candidate_admission": {
            "schema": complete["schema"],
            "artifact_sha256": file_hash(Path(root) / "complete.json"),
            "selection_rule": plan["selection_rule"],
            "target_statistics_computed": 0,
            "provider_calls": 0,
        },
        "initial_train": selected["initial_train"],
        "dev": selected["dev"],
        "final": selected["final"],
        "rounds": 8,
        "minimum_final_sessions": 20,
        "formal_promotion": False,
        "stop_policy": deepcopy(prior["stop_policy"]),
        "retry_policy": deepcopy(RETRY_POLICY),
        "budget": deepcopy(prior["budget"]),
        "prior_exposure": {"opened_sessions": plan["prior_exposure"]},
        "claim_limits": {
            "distinct_final_utc_dates": 4,
            "evidence_class": "three-arm semantically admitted hourly memory-policy experiment",
            "formal_promotion_claim": False,
            "general_rsi_claim": False,
            "profitability_claim": False,
        },
    }
    validate_v2(spec)
    fresh_json(output, spec)
    return spec


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--prior-spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--experiment-id", required=True)
    args = parser.parse_args()
    value = build(args.admission, args.plan, args.prior_spec,
                  args.output, args.experiment_id)
    print({"experiment_id": value["experiment_id"],
           "train": len(value["initial_train"]),
           "dev": len(value["dev"]), "final": len(value["final"])})
