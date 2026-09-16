"""Build v3 from score-free receipts and the frozen resource-safe selection."""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

from market_rsi import digest, file_hash, fresh_json, load_json
from memory_policy.build_spec_v2 import validate_admission
from memory_policy.semantic_source_preflight import (
    source_hashes as semantic_source_hashes, validate_report,
)
from memory_policy.spec_v2 import RETRY_POLICY, SOURCE_INTEGRITY, validate as validate_v2
from memory_policy.spec_v3 import TRAINER_RESOURCE_GATE, validate as validate_v3


def selected_rows(selection, role):
    return [{"session": row["session"], "compressed_bytes": row["compressed_bytes"]}
            for row in selection[role]]


def report_map(admission_root):
    result = {}
    for directory in sorted(path for path in Path(admission_root).iterdir()
                            if path.is_dir()):
        report_path = directory / "report.json"
        if report_path.exists():
            report = load_json(report_path)
            result[report["session"]] = report
    return result


def validate_selection(selection_path, admission_root, admission_plan,
                       rebind_paths):
    selection_path = Path(selection_path).resolve()
    selection = load_json(selection_path)
    plan, admission, admitted = validate_admission(admission_root, admission_plan)
    required = {
        "schema", "superseded_experiment_id",
        "superseded_failure_decision_sha256",
        "source_admission_complete_sha256", "selection_rule",
        "selection_inputs", "forbidden_selection_inputs", "initial_train", "dev",
        "final", "excluded_before_dev", "reserved_after_final",
        "cumulative_train_through_round_8_selected_observations_upper",
        "cumulative_selected_observations_cap", "target_statistics_computed",
        "fits", "provider_calls",
    }
    if (not isinstance(selection, dict) or set(selection) != required
            or selection["schema"] != "memory_policy_score_free_reselection_v1"
            or selection["source_admission_complete_sha256"] !=
                file_hash(Path(admission_root) / "complete.json")
            or any(selection[key] != 0
                   for key in ("target_statistics_computed", "fits", "provider_calls"))
            or selection["cumulative_selected_observations_cap"] != 10_000_000):
        raise ValueError("score-free source selection identity failed")
    by_session = report_map(admission_root)
    rebound = {}
    for path in rebind_paths:
        value = load_json(Path(path) / "complete.json")
        signed = dict(value)
        result_sha256 = signed.pop("result_sha256", None)
        if (result_sha256 != digest(signed)
                or value.get("complete") is not True
                or len(value.get("reports", [])) != 1
                or value.get("source_hashes") != semantic_source_hashes()
                or value.get("contract_sha256") != admission["contract_sha256"]
                or value.get("target_statistics_computed") != 0
                or value.get("provider_calls") != 0):
            raise ValueError("complete single-source role preflight required")
        report = value["reports"][0]
        rebound[report["session"]] = report
    expected_rebound = {
        row["session"] for row in selection["dev"]
        if by_session[row["session"]]["role"] != "dev"
    }
    if set(rebound) != expected_rebound:
        raise ValueError("exact role-rebound receipt set required")
    for role in ("initial_train", "dev", "final"):
        for row in selection[role]:
            report = rebound.get(row["session"], by_session.get(row["session"]))
            expected = {"session": row["session"], "role": role,
                        "compressed_bytes": row["compressed_bytes"]}
            validate_report(expected, report)
            if report["semantic_receipt"]["selected_observations"] != row[
                    "selected_observations"]:
                raise ValueError("selected-observation receipt differs")
    cumulative = sum(row["selected_observations"]
                     for role in ("initial_train", "dev")
                     for row in selection[role])
    if (cumulative != selection[
            "cumulative_train_through_round_8_selected_observations_upper"]
            or cumulative > selection["cumulative_selected_observations_cap"]):
        raise ValueError("cumulative Train resource gate failed")
    if selected_rows(selection, "initial_train") != admitted["initial_train"]:
        raise ValueError("v3 must reuse the admitted initial Train only")
    prior_opened = {"2026-09-10T22", "2026-09-10T23"}
    candidates = []
    for group in plan["groups"]:
        if group["role"] not in {"dev", "final"}:
            continue
        for row in group["candidates"]:
            report = by_session[row["session"]]
            if report.get("complete") is True and row["session"] not in prior_opened:
                candidates.append({
                    **row,
                    "selected_observations":
                        report["semantic_receipt"]["selected_observations"],
                })
    candidates.sort(key=lambda row: row["session"])
    initial_total = sum(row["selected_observations"]
                        for row in selection["initial_train"])
    expected_dev = None
    for start in range(len(candidates) - 7):
        block = candidates[start:start + 8]
        if initial_total + sum(row["selected_observations"]
                               for row in block) <= 10_000_000:
            expected_dev = block
            break
    if selection["dev"] != expected_dev:
        raise ValueError("v3 Dev is not the first resource-feasible block")
    expected_final = [row for row in candidates
                      if row["session"] > selection["dev"][-1]["session"]][:20]
    if selection["final"] != expected_final:
        raise ValueError("v3 Final is not the first twenty later complete sources")
    names = [row["session"] for role in ("initial_train", "dev", "final")
             for row in selection[role]]
    if names != sorted(names) or len(names) != len(set(names)):
        raise ValueError("selection must be unique and chronological")
    return selection


def build(selection_path, admission_root, admission_plan, prior_spec_path,
          rebind_paths, output, experiment_id):
    selection = validate_selection(
        selection_path, admission_root, admission_plan, rebind_paths)
    prior = validate_v2(load_json(prior_spec_path))
    opened = list(prior["prior_exposure"]["opened_sessions"])
    opened.extend(row["session"] for row in prior["dev"][:2])
    opened = sorted(set(opened))
    spec = {
        "schema": "market_rsi_memory_policy_v3",
        "experiment_id": experiment_id,
        "question": prior["question"],
        "changed_stage": prior["changed_stage"],
        "arms": deepcopy(prior["arms"]),
        "component_hashes": deepcopy(prior["component_hashes"]),
        "fixed_contract": deepcopy(prior["fixed_contract"]),
        "source_integrity": deepcopy(SOURCE_INTEGRITY),
        "candidate_admission": {
            "schema": selection["schema"],
            "artifact_sha256": file_hash(selection_path),
            "source_admission_sha256":
                selection["source_admission_complete_sha256"],
            "selection_rule": selection["selection_rule"],
            "target_statistics_computed": 0,
            "fits": 0,
            "provider_calls": 0,
        },
        "trainer_resource_gate": deepcopy(TRAINER_RESOURCE_GATE),
        "supersedes": {
            "experiment_id": selection["superseded_experiment_id"],
            "failure_decision": "invalidate_run_and_redesign",
            "failure_decision_sha256":
                selection["superseded_failure_decision_sha256"],
            "opened_dev_sessions": ["2026-09-10T22", "2026-09-10T23"],
            "artifacts_reused_for_training": False,
        },
        "initial_train": selected_rows(selection, "initial_train"),
        "dev": selected_rows(selection, "dev"),
        "final": selected_rows(selection, "final"),
        "rounds": 8,
        "minimum_final_sessions": 20,
        "formal_promotion": False,
        "stop_policy": deepcopy(prior["stop_policy"]),
        "retry_policy": deepcopy(RETRY_POLICY),
        "budget": deepcopy(prior["budget"]),
        "prior_exposure": {"opened_sessions": opened},
        "claim_limits": {
            "distinct_final_utc_dates": 4,
            "evidence_class":
                "three-arm semantically admitted hourly memory-policy resource-repaired rerun",
            "formal_promotion_claim": False,
            "general_rsi_claim": False,
            "profitability_claim": False,
        },
    }
    validate_v3(spec)
    fresh_json(output, spec)
    return spec


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--admission-plan", type=Path, required=True)
    parser.add_argument("--prior-spec", type=Path, required=True)
    parser.add_argument("--role-preflight", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--experiment-id", required=True)
    args = parser.parse_args()
    value = build(args.selection, args.admission, args.admission_plan,
                  args.prior_spec, args.role_preflight, args.output,
                  args.experiment_id)
    print({"experiment_id": value["experiment_id"],
           "train": len(value["initial_train"]),
           "dev": len(value["dev"]), "final": len(value["final"])})
