"""Fail-closed validation for Market RSI experiment specifications."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_rsi import canonical, digest, load_json


PREDICTION_SCHEMA = "market_rsi_prediction_experiment_v1"
SHA_FIELDS = {
    "data_admission_receipt_sha256", "data_manifest_sha256",
    "target_contract_sha256", "split_manifest_sha256",
    "strong_baseline_manifest_sha256", "candidate_budget_manifest_sha256",
}


def _validate_prediction_draft(spec: dict) -> dict:
    required = {
        "schema", "experiment_id", "design_status", "question",
        "changed_stage", "frozen_now", "pending_before_execution",
        "data_plan", "target_selection", "split_plan", "baseline_plan",
        "candidate_plan", "metrics", "promotion_gates", "budget",
        "claim_limits",
    }
    if not isinstance(spec, dict) or set(spec) != required:
        raise ValueError("unexpected prediction experiment fields")
    if spec["schema"] != PREDICTION_SCHEMA:
        raise ValueError("wrong prediction experiment schema")
    if spec["design_status"] != "draft_blocked_on_data_admission":
        raise ValueError("only a non-executable prediction draft is accepted")
    if spec["changed_stage"] != "prediction_search_policy":
        raise ValueError("first A/B may change only prediction search policy")
    if not isinstance(spec["question"], str) or not spec["question"].strip():
        raise ValueError("prediction question is required")

    frozen = spec["frozen_now"]
    if frozen != {
        "seed": 23,
        "causal_stage": "prediction",
        "data_gate": "formal_gate1_admission_required",
        "same_rows_for_all_arms": True,
        "no_imputation": True,
        "minimum_final_dates": 20,
        "final_access": "one_shot_after_full_lock",
        "primary_comparison": "rsi_candidate_vs_train_selected_strong_baseline",
        "primary_metric": "equal_game_mean_squared_error",
        "inference": "paired_date_block_95pct_interval",
        "pnl_policy": "not_measured",
        "execution_authorized": False,
    }:
        raise ValueError("incomplete or changed frozen prediction boundary")

    pending = spec["pending_before_execution"]
    if set(pending) != SHA_FIELDS or any(value is not None for value in pending.values()):
        raise ValueError("draft must expose every unresolved execution commitment")

    data = spec["data_plan"]
    if (set(data) != {"minimum_completed_seasons", "target_completed_seasons",
                      "required_price_semantics", "event_order",
                      "exclusion_policy", "required_admission_checks"}
            or data["minimum_completed_seasons"] < 3
            or data["target_completed_seasons"] < data["minimum_completed_seasons"]
            or data["required_price_semantics"] != "verified_trade_or_executable_quote"
            or data["event_order"] != "immutable_composite_row_key"
            or data["exclusion_policy"] != "evidence_backed_only_no_imputation"
            or not isinstance(data["required_admission_checks"], list)
            or len(data["required_admission_checks"]) < 5):
        raise ValueError("prediction data plan is incomplete")

    target = spec["target_selection"]
    if (set(target) != {"selected", "selection_data", "dev_visible",
                       "candidate_targets", "required_checks"}
            or target["selected"] is not None
            or target["selection_data"] != "opened_train_only"
            or target["dev_visible"] is not False
            or len(target["candidate_targets"]) < 2
            or len(target["required_checks"]) < 4):
        raise ValueError("target must remain unresolved without Dev access")

    split = spec["split_plan"]
    if (set(split) != {"ordering", "train", "route_dev", "audit_dev", "final",
                       "previously_opened_periods"}
            or split["ordering"] != "strict_chronological_nonoverlap"
            or split["final"] != {
                "manifest_sha256": None,
                "minimum_distinct_dates": 20,
                "access": "sealed_until_one_shot_final",
            }
            or split["train"] != {
                "manifest_sha256": None,
                "access": "opened",
                "purpose": "fit_and_target_selection",
            }
            or split["route_dev"] != {
                "manifest_sha256": None,
                "access": "aggregate_scores_only",
                "purpose": "round_selection",
            }
            or split["audit_dev"] != {
                "manifest_sha256": None,
                "access": "one_shot_after_candidate_lock",
                "purpose": "final_candidate_audit",
            }
            or split["previously_opened_periods"] != "diagnostic_only_excluded_from_promotion"):
        raise ValueError("chronological split plan is incomplete")

    baseline = spec["baseline_plan"]
    required_baselines = {"zero_change", "persistence", "ridge", "hgb"}
    if (set(baseline) != {"library", "selection_data", "selection_budget",
                         "strong_baseline_status", "same_rows"}
            or not required_baselines.issubset(set(baseline["library"]))
            or baseline["selection_data"] != "opened_train_only"
            or baseline["selection_budget"] != "fixed_before_fit"
            or baseline["strong_baseline_status"] != "pending"
            or baseline["same_rows"] is not True):
        raise ValueError("strong baseline plan is incomplete")

    candidate = spec["candidate_plan"]
    if (set(candidate) != {"controller", "supervisor", "research_scope",
                          "same_data_target_rows", "compute_match",
                          "one_changed_prediction_component_per_trial",
                          "archive_every_trial", "dev_policy"}
            or candidate["controller"] != "Tinker GLM-5.3"
            or candidate["supervisor"] != "Codex GPT-5.6 Sol"
            or candidate["same_data_target_rows"] is not True
            or candidate["compute_match"] != "same_total_dollars_and_record_tokens_wall_time"
            or candidate["one_changed_prediction_component_per_trial"] is not True
            or candidate["archive_every_trial"] is not True
            or candidate["dev_policy"] != "aggregate_feedback_only_no_row_or_label_access"):
        raise ValueError("RSI candidate plan is incomplete")

    required_metrics = {
        "equal_game_mse", "rmse_probability_points", "pearson_ic",
        "rank_ic", "calibration_slope", "calibration_intercept",
        "positive_game_fraction", "positive_date_fraction",
        "paired_date_block_95pct_interval", "label_coverage",
    }
    if set(spec["metrics"]) != required_metrics:
        raise ValueError("prediction metrics are incomplete")
    if spec["promotion_gates"] != {
        "minimum_final_dates": 20,
        "candidate_minus_strong_mse_below_zero": True,
        "paired_interval_upper_below_zero": True,
        "coverage_gate_passed": True,
        "calibration_not_worse": True,
        "no_final_tuning": True,
    }:
        raise ValueError("promotion gates changed")
    if spec["budget"] != {
        "existing_global_cap_usd": "200",
        "new_authorization_usd": "0",
        "read_authoritative_ledger_at_dispatch": True,
        "formal_run_budget_usd": None,
        "paid_execution_authorized": False,
    }:
        raise ValueError("draft cannot grant or guess paid execution authority")
    if spec["claim_limits"] != {
        "prediction_improvement_proven": False,
        "data_admitted": False,
        "target_frozen": False,
        "strong_baseline_frozen": False,
        "formal_experiment_started": False,
    }:
        raise ValueError("draft claim boundaries are overstated")
    return spec


def _session(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("session IDs must be strings")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H")
    except ValueError as error:
        raise ValueError("session IDs must use YYYY-MM-DDTHH") from error
    if parsed.strftime("%Y-%m-%dT%H") != value:
        raise ValueError("session IDs must be canonical")
    return parsed


def validate(spec: dict) -> dict:
    if isinstance(spec, dict) and spec.get("schema") == PREDICTION_SCHEMA:
        return _validate_prediction_draft(spec)
    required = {
        "schema", "experiment_id", "question", "changed_stage", "arms",
        "component_hashes", "fixed_contract", "initial_train", "dev",
        "final", "rounds", "minimum_final_sessions", "formal_promotion",
        "stop_policy", "budget", "prior_exposure", "claim_limits",
    }
    if not isinstance(spec, dict) or set(spec) != required:
        raise ValueError("unexpected experiment specification fields")
    if spec["schema"] != "market_rsi_memory_replication_v1":
        raise ValueError("wrong experiment schema")
    if spec["changed_stage"] != "controller_memory":
        raise ValueError("this study may change only controller memory")
    arms = spec["arms"]
    if set(arms) != {"fresh", "archive"}:
        raise ValueError("exact archive and fresh arms required")
    fresh = arms["fresh"]
    archive = arms["archive"]
    if (set(fresh) != {"prior_own_round_records"}
            or set(archive) != {"prior_own_round_records"}
            or fresh["prior_own_round_records"] != "hidden"
            or archive["prior_own_round_records"] != "visible"):
        raise ValueError("arms must differ only in prior own-round archive visibility")
    hashes = spec["component_hashes"]
    expected = {name: digest({"arm": name, **value, "all_other_inputs": "identical"})
                for name, value in arms.items()}
    if hashes != expected or hashes["fresh"] == hashes["archive"]:
        raise ValueError("declared arm hashes do not match canonical components")

    fixed = spec["fixed_contract"]
    expected_fixed = {
        "target_contract_sha256", "target", "horizon_seconds", "latency",
        "costs", "row_policy", "controller_model", "harness", "seed",
        "candidate_library", "trainer_selection", "normalizer_selection",
        "final_metric", "pnl_policy",
    }
    if set(fixed) != expected_fixed:
        raise ValueError("incomplete fixed scientific contract")
    if (fixed["horizon_seconds"] != 60 or fixed["seed"] != 23
            or fixed["final_metric"] != "equal-session mean squared error"
            or fixed["pnl_policy"] != "not measured"
            or fixed["trainer_selection"] != "same frozen Train-only library"
            or fixed["normalizer_selection"] != "same frozen Train-only library"):
        raise ValueError("target/evaluation or symmetric search-space contract changed")

    train = spec["initial_train"]
    dev = spec["dev"]
    final = spec["final"]
    if spec["rounds"] != len(dev) or not 8 <= spec["rounds"] <= 12:
        raise ValueError("replication must predeclare eight to twelve rounds")
    if spec["minimum_final_sessions"] < 20 or len(final) < spec["minimum_final_sessions"]:
        raise ValueError("at least twenty final sessions required")
    if spec["formal_promotion"] is not False:
        raise ValueError("hourly expanded pilot is not formal promotion evidence")
    all_rows = train + dev + final
    if any(set(row) != {"session", "compressed_bytes"} for row in all_rows):
        raise ValueError("session manifests require exact identity and byte count")
    names = [row["session"] for row in all_rows]
    if len(names) != len(set(names)) or any(type(row["compressed_bytes"]) is not int
                                            or row["compressed_bytes"] <= 0 for row in all_rows):
        raise ValueError("source sessions must be unique with positive exact bytes")
    parsed_train = [_session(row["session"]) for row in train]
    parsed_dev = [_session(row["session"]) for row in dev]
    parsed_final = [_session(row["session"]) for row in final]
    if (parsed_train != sorted(parsed_train) or parsed_dev != sorted(parsed_dev)
            or parsed_final != sorted(parsed_final)
            or max(parsed_train) >= min(parsed_dev) or max(parsed_dev) >= min(parsed_final)):
        raise ValueError("strict chronological Train, Dev and Final blocks required")
    if any(row["session"] in spec["prior_exposure"]["opened_final_sessions"] for row in final):
        raise ValueError("previously opened final data cannot be reused")
    if len({value.date() for value in parsed_final}) < 20 and spec["formal_promotion"]:
        raise ValueError("formal promotion requires twenty distinct UTC dates")
    if spec["stop_policy"] != {
        "planned_rounds": spec["rounds"],
        "performance_early_stop": False,
        "stop_before_unaffordable_atomic_pair": True,
        "no_score_retry": True,
    }:
        raise ValueError("stop policy must not use opened Final or cherry-pick scores")
    if (spec["budget"].get("existing_global_cap_usd") != "200"
            or spec["budget"].get("new_authorization_usd") != "0"):
        raise ValueError("only the existing two-hundred-dollar authorization is allowed")
    return spec


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    args = parser.parse_args()
    spec = validate(load_json(args.spec.resolve()))
    result = {"valid": True, "experiment_id": spec["experiment_id"],
              "schema": spec["schema"], "spec_sha256": digest(spec)}
    if spec["schema"] == PREDICTION_SCHEMA:
        result.update({"design_status": spec["design_status"],
                       "execution_authorized": spec["frozen_now"]["execution_authorized"]})
    else:
        result.update({"rounds": spec["rounds"], "final_sessions": len(spec["final"]),
                       "formal_promotion": spec["formal_promotion"]})
    print(canonical(result))


if __name__ == "__main__":
    main()
