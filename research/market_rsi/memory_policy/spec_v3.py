"""Fail-closed specification for the resource-repaired memory-policy rerun."""
from __future__ import annotations

from market_rsi import digest
from memory_policy.broker_v3 import (
    REFIT_MAX_RSS_GIB, REFIT_TIMEOUT_SECONDS,
    TRIAL_MAX_RSS_GIB, TRIAL_TIMEOUT_SECONDS,
)
from memory_policy.spec import ARM_DEFINITIONS, _session
from memory_policy.spec_v2 import RETRY_POLICY, SOURCE_INTEGRITY


TRAINER_RESOURCE_GATE = {
    "candidate_fit_max_rss_gib": TRIAL_MAX_RSS_GIB,
    "candidate_fit_timeout_seconds": TRIAL_TIMEOUT_SECONDS,
    "mandatory_refit_max_rss_gib": REFIT_MAX_RSS_GIB,
    "mandatory_refit_timeout_seconds": REFIT_TIMEOUT_SECONDS,
    "max_fit_rows": 12000000,
    "max_cumulative_selected_observations": 10000000,
    "same_plan_and_rows_for_candidate_and_refit": True,
    "silent_subsampling": False,
    "all_arms_identical": True,
}


def validate(spec):
    required = {
        "schema", "experiment_id", "question", "changed_stage", "arms",
        "component_hashes", "fixed_contract", "source_integrity",
        "candidate_admission", "trainer_resource_gate", "supersedes",
        "initial_train", "dev", "final", "rounds", "minimum_final_sessions",
        "formal_promotion", "stop_policy", "retry_policy", "budget",
        "prior_exposure", "claim_limits",
    }
    if not isinstance(spec, dict) or set(spec) != required:
        raise ValueError("unexpected v3 memory-policy specification fields")
    if (spec["schema"] != "market_rsi_memory_policy_v3"
            or spec["changed_stage"] != "controller_memory_representation"):
        raise ValueError("wrong v3 experiment schema or changed stage")
    if spec["arms"] != ARM_DEFINITIONS:
        raise ValueError("exact three memory representations required")
    expected_hashes = {name: digest({"arm": name, **definition,
        "all_other_inputs": "identical"})
        for name, definition in ARM_DEFINITIONS.items()}
    if spec["component_hashes"] != expected_hashes:
        raise ValueError("memory component hashes differ from declared arms")

    fixed = spec["fixed_contract"]
    expected_fixed = {
        "target_contract_sha256", "target", "horizon_seconds", "latency",
        "costs", "row_policy", "controller_model", "harness", "seed",
        "candidate_library", "trainer_selection", "normalizer_selection",
        "rounds", "candidate_attempts_per_round", "final_metric", "pnl_policy",
    }
    if (not isinstance(fixed, dict) or set(fixed) != expected_fixed
            or fixed["horizon_seconds"] != 60 or fixed["seed"] != 23
            or fixed["rounds"] != 8
            or fixed["candidate_attempts_per_round"] != 3
            or fixed["final_metric"] != "equal-session mean squared error"
            or fixed["pnl_policy"] != "not measured"
            or fixed["trainer_selection"] != "same frozen Train-only library"
            or fixed["normalizer_selection"] != "same frozen Train-only library"):
        raise ValueError("incomplete or asymmetric fixed scientific contract")
    if spec["source_integrity"] != SOURCE_INTEGRITY:
        raise ValueError("semantic source gate must be frozen")
    if spec["trainer_resource_gate"] != TRAINER_RESOURCE_GATE:
        raise ValueError("exact repaired trainer resource gate required")

    admission = spec["candidate_admission"]
    expected_admission_fields = {
        "schema", "artifact_sha256", "source_admission_sha256",
        "selection_rule", "target_statistics_computed", "fits", "provider_calls",
    }
    if (not isinstance(admission, dict)
            or set(admission) != expected_admission_fields
            or admission["schema"] != "memory_policy_score_free_reselection_v1"
            or not all(isinstance(admission[key], str)
                       and len(admission[key]) == 64
                       for key in ("artifact_sha256", "source_admission_sha256"))
            or any(admission[key] != 0
                   for key in ("target_statistics_computed", "fits", "provider_calls"))
            or "No target statistic" not in admission["selection_rule"]):
        raise ValueError("exact score-free v3 reselection required")
    if spec["supersedes"] != {
        "experiment_id": "memory-policy-v2-20260915-01",
        "failure_decision": "invalidate_run_and_redesign",
        "failure_decision_sha256":
            "0d1f2fbf9af7e8d051f9aae91f8c3d36b8b02f60b82f01e29295519431bcebd9",
        "opened_dev_sessions": ["2026-09-10T22", "2026-09-10T23"],
        "artifacts_reused_for_training": False,
    }:
        raise ValueError("v2 invalidation and non-reuse boundary required")

    train, dev, final = spec["initial_train"], spec["dev"], spec["final"]
    if (spec["rounds"] != 8 or len(dev) != 8
            or spec["minimum_final_sessions"] < 20
            or len(final) < spec["minimum_final_sessions"]):
        raise ValueError("eight rounds and at least twenty Final sessions required")
    rows = train + dev + final
    if not train or any(not isinstance(row, dict)
            or set(row) != {"session", "compressed_bytes"}
            or type(row["compressed_bytes"]) is not int
            or row["compressed_bytes"] <= 0 for row in rows):
        raise ValueError("exact nonempty source identities required")
    names = [row["session"] for row in rows]
    if len(names) != len(set(names)):
        raise ValueError("source sessions must be unique")
    parsed = [[_session(row["session"]) for row in group]
              for group in (train, dev, final)]
    if (any(group != sorted(group) for group in parsed)
            or max(parsed[0]) >= min(parsed[1])
            or max(parsed[1]) >= min(parsed[2])):
        raise ValueError("strict chronological Train, Dev and Final blocks required")
    opened = spec["prior_exposure"].get("opened_sessions")
    if (not isinstance(opened, list) or len(opened) != len(set(opened))
            or set(names) & set(opened)
            or not set(spec["supersedes"]["opened_dev_sessions"]).issubset(opened)):
        raise ValueError("opened sessions cannot return as experimental data")
    if len({row["session"][:10] for row in final}) < 4:
        raise ValueError("Final must span at least four UTC dates")
    if spec["formal_promotion"] is not False:
        raise ValueError("hourly memory study is not formal promotion")
    if spec["stop_policy"] != {
        "planned_rounds": 8,
        "performance_early_stop": False,
        "stop_before_unaffordable_atomic_triple": True,
        "no_score_retry": True,
    }:
        raise ValueError("fixed no-cherry-pick stop policy required")
    if spec["retry_policy"] != RETRY_POLICY:
        raise ValueError("fixed repair-before-rerun policy required")
    if (spec["budget"].get("existing_global_cap_usd") != "200"
            or spec["budget"].get("paid_component") != "GLM controller turns only"
            or spec["budget"].get("atomic_unit") !=
                "fresh plus archive plus compact controller sessions"
            or spec["budget"].get("unused_reservation_is_not_spend") is not True):
        raise ValueError("budget identity or atomic unit differs")
    if spec["claim_limits"] != {
        "distinct_final_utc_dates": 4,
        "evidence_class":
            "three-arm semantically admitted hourly memory-policy resource-repaired rerun",
        "formal_promotion_claim": False,
        "general_rsi_claim": False,
        "profitability_claim": False,
    }:
        raise ValueError("v3 evidence boundaries must be explicit")
    return spec
