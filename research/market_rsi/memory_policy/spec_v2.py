"""Fail-closed specification for the semantically admitted memory study."""
from __future__ import annotations

from memory_policy.spec import ARM_DEFINITIONS, _session
from market_rsi import digest


SOURCE_INTEGRITY = {
    "scope": "all initial Train, rolling Dev and Final objects",
    "timing": "complete before first paid controller call",
    "selection_kernel": "full pass through exact CacheProfile.consume; no summary or cache write",
    "structural_checks": "bytes, compressed and decoded hashes, every-line JSON, start/end file identity",
    "semantic_checks": "message routing, UTC source-time boundary, entity continuity, clocks and resource bounds",
    "controller_visibility": "receipt metadata only; no source rows, labels or target statistics",
    "materialization_binding": "byte identity and semantic selection counts must reproduce before cache write",
    "failure_action": "before freeze use first passing preregistered candidate; after freeze invalidate the run",
    "admission_wall_policy": "570-second scan gate plus 2100-second materialization for admitted large objects",
}

RETRY_POLICY = {
    "preserve_every_failure": True,
    "causal_fix_and_positive_negative_canary_before_retry": True,
    "same_run_resume": "only an exact idempotent checkpoint with no result or uncertain side effect",
    "fresh_id_recovery": "mechanical pre-result failure with unchanged scientific inputs only",
    "source_skip": "candidate admission before manifest freeze only",
    "source_failure_after_freeze": "invalidate the whole run",
    "result_retry": False,
}


def validate(spec):
    required = {
        "schema", "experiment_id", "question", "changed_stage", "arms",
        "component_hashes", "fixed_contract", "source_integrity",
        "candidate_admission", "initial_train", "dev", "final", "rounds",
        "minimum_final_sessions", "formal_promotion", "stop_policy", "retry_policy",
        "budget", "prior_exposure", "claim_limits",
    }
    if not isinstance(spec, dict) or set(spec) != required:
        raise ValueError("unexpected v2 memory-policy specification fields")
    if (spec["schema"] != "market_rsi_memory_policy_v2"
            or spec["changed_stage"] != "controller_memory_representation"):
        raise ValueError("wrong v2 experiment schema or changed stage")
    if spec["arms"] != ARM_DEFINITIONS:
        raise ValueError("exact three memory representations required")
    expected_hashes = {name: digest({"arm": name, **definition,
        "all_other_inputs": "identical"}) for name, definition in ARM_DEFINITIONS.items()}
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
            or fixed["rounds"] != spec["rounds"]
            or fixed["candidate_attempts_per_round"] != 3
            or fixed["final_metric"] != "equal-session mean squared error"
            or fixed["pnl_policy"] != "not measured"
            or fixed["trainer_selection"] != "same frozen Train-only library"
            or fixed["normalizer_selection"] != "same frozen Train-only library"):
        raise ValueError("incomplete or asymmetric fixed scientific contract")
    if spec["source_integrity"] != SOURCE_INTEGRITY:
        raise ValueError("semantic source gate must be frozen")
    admission = spec["candidate_admission"]
    if (not isinstance(admission, dict)
            or set(admission) != {"schema", "artifact_sha256", "selection_rule",
                                  "target_statistics_computed", "provider_calls"}
            or admission["schema"] != "memory_policy_candidate_admission_v1"
            or admission["selection_rule"] !=
                "first passing candidates in each ordered group; no target statistics"
            or admission["target_statistics_computed"] != 0
            or admission["provider_calls"] != 0
            or not isinstance(admission["artifact_sha256"], str)
            or len(admission["artifact_sha256"]) != 64):
        raise ValueError("exact score-free candidate admission required")

    train, dev, final = spec["initial_train"], spec["dev"], spec["final"]
    if (spec["rounds"] != len(dev) or spec["rounds"] != 8
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
            or set(names) & set(opened)):
        raise ValueError("opened sessions cannot return as experimental data")
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
        "evidence_class": "three-arm semantically admitted hourly memory-policy experiment",
        "formal_promotion_claim": False,
        "general_rsi_claim": False,
        "profitability_claim": False,
    }:
        raise ValueError("v2 evidence boundaries must be explicit")
    return spec
