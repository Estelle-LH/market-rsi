"""Fail-closed specification for the fresh terminal-capacity-repaired v4 study."""
from __future__ import annotations

from market_rsi import digest
from memory_policy.spec import ARM_DEFINITIONS, _session
from memory_policy.spec_v2 import RETRY_POLICY, SOURCE_INTEGRITY
from memory_policy.spec_v3 import TRAINER_RESOURCE_GATE


TERMINAL_CAPACITY_GATE = {
    "failure_layer": "controller_terminal_submission_capacity",
    "ordinary_research_may_consume_reserved_output": False,
    "terminal_submission_must_be_model_authored": True,
    "prose_to_submission_conversion": False,
    "paid_response_resampling": False,
    "submission_output_reserve": 16_384,
    "terminal_trigger_remaining_output": 32_768,
    "terminal_submission_max_output": 16_384,
    "terminal_tool_reserve": 4,
    "same_for_all_arms": True,
}

V3_FAILURE_SHA256 = (
    "09514138bdad9bc1dc97d496e129caa6a68c076bbf2f343ac555f34cff91727e"
)
V3_OPENED_DEV = ["2026-09-11T04", "2026-09-11T05"]


def validate(spec):
    required = {
        "schema", "experiment_id", "question", "changed_stage", "arms",
        "component_hashes", "fixed_contract", "source_integrity",
        "candidate_admission", "trainer_resource_gate",
        "terminal_capacity_gate", "supersedes", "initial_train", "dev",
        "final", "rounds", "minimum_final_sessions", "formal_promotion",
        "stop_policy", "retry_policy", "budget", "prior_exposure",
        "claim_limits",
    }
    if not isinstance(spec, dict) or set(spec) != required:
        raise ValueError("unexpected v4 memory-policy specification fields")
    if (spec["schema"] != "market_rsi_memory_policy_v4"
            or spec["changed_stage"] != "controller_memory_representation"):
        raise ValueError("wrong v4 experiment schema or changed stage")
    if spec["arms"] != ARM_DEFINITIONS:
        raise ValueError("exact three memory representations required")
    expected_hashes = {
        name: digest({"arm": name, **definition, "all_other_inputs": "identical"})
        for name, definition in ARM_DEFINITIONS.items()
    }
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
    if spec["terminal_capacity_gate"] != TERMINAL_CAPACITY_GATE:
        raise ValueError("exact shared terminal-capacity repair required")

    admission = spec["candidate_admission"]
    expected_admission = {
        "schema", "artifact_sha256", "selection_rule",
        "target_statistics_computed", "fits", "provider_calls",
    }
    if (not isinstance(admission, dict) or set(admission) != expected_admission
            or admission["schema"] != "memory_policy_candidate_admission_v1"
            or not isinstance(admission["artifact_sha256"], str)
            or len(admission["artifact_sha256"]) != 64
            or any(admission[key] != 0
                   for key in ("target_statistics_computed", "fits", "provider_calls"))
            or admission["selection_rule"] !=
                "first passing candidates in each ordered group; no target statistics"):
        raise ValueError("exact score-free v4 admission required")
    if spec["supersedes"] != {
        "experiment_id": "memory-policy-v3-20260915-01",
        "failure_status": "invalidated_no_same_run_retry",
        "failure_disposition_sha256": V3_FAILURE_SHA256,
        "opened_dev_sessions": V3_OPENED_DEV,
        "artifacts_reused_for_training": False,
        "scientific_change": "none",
        "shared_harness_fix": "controller_terminal_submission_capacity",
    }:
        raise ValueError("v3 invalidation and non-reuse boundary required")

    train, dev, final = spec["initial_train"], spec["dev"], spec["final"]
    if (spec["rounds"] != 8 or len(train) != 3 or len(dev) != 8
            or spec["minimum_final_sessions"] != 20 or len(final) != 20):
        raise ValueError("exact 3/8/20 v4 split required")
    rows = train + dev + final
    if any(not isinstance(row, dict)
           or set(row) != {"session", "compressed_bytes"}
           or type(row["compressed_bytes"]) is not int
           or row["compressed_bytes"] <= 0 for row in rows):
        raise ValueError("exact source identities required")
    names = [row["session"] for row in rows]
    parsed = [[_session(row["session"]) for row in group]
              for group in (train, dev, final)]
    if (len(names) != len(set(names))
            or any(group != sorted(group) for group in parsed)
            or max(parsed[0]) >= min(parsed[1])
            or max(parsed[1]) >= min(parsed[2])):
        raise ValueError("unique chronological Train, Dev and Final required")
    opened = spec["prior_exposure"].get("opened_sessions")
    if (not isinstance(opened, list) or opened != sorted(set(opened))
            or set(names) & set(opened)
            or not set(V3_OPENED_DEV).issubset(opened)):
        raise ValueError("opened sessions cannot return as v4 evidence")
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
            or spec["budget"].get("new_authorization_usd") != "0"
            or spec["budget"].get("paid_component") != "GLM controller turns only"
            or spec["budget"].get("atomic_unit") !=
                "fresh plus archive plus compact controller sessions"
            or spec["budget"].get("unused_reservation_is_not_spend") is not True):
        raise ValueError("budget identity or atomic unit differs")
    if spec["claim_limits"] != {
        "distinct_final_utc_dates": 4,
        "evidence_class":
            "three-arm fresh-evidence terminal-capacity-repaired memory-policy rerun",
        "formal_promotion_claim": False,
        "general_rsi_claim": False,
        "profitability_claim": False,
    }:
        raise ValueError("v4 evidence boundaries must be explicit")
    return spec
