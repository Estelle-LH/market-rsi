"""Fail-closed specification for the three-arm controller-memory study."""
from __future__ import annotations

from datetime import datetime

from market_rsi import digest


ARM_DEFINITIONS = {
    "fresh": {"prior_own_round_memory": "none"},
    "archive": {"prior_own_round_memory": "complete_raw_archive"},
    "compact": {"prior_own_round_memory": "deterministic_structured_summary_v1"},
}


def _session(value):
    if not isinstance(value, str):
        raise ValueError("session must be a string")
    parsed = datetime.strptime(value, "%Y-%m-%dT%H")
    if parsed.strftime("%Y-%m-%dT%H") != value:
        raise ValueError("canonical hourly session required")
    return parsed


def validate(spec):
    required = {
        "schema", "experiment_id", "question", "changed_stage", "arms",
        "component_hashes", "fixed_contract", "source_integrity",
        "initial_train", "dev", "final", "rounds", "minimum_final_sessions",
        "formal_promotion", "stop_policy", "budget", "prior_exposure",
        "claim_limits",
    }
    if not isinstance(spec, dict) or set(spec) != required:
        raise ValueError("unexpected memory-policy specification fields")
    if (spec["schema"] != "market_rsi_memory_policy_v1"
            or spec["changed_stage"] != "controller_memory_representation"):
        raise ValueError("wrong experiment schema or changed stage")
    if spec["arms"] != ARM_DEFINITIONS:
        raise ValueError("exact three memory representations required")
    expected_hashes = {name: digest({"arm": name, **definition,
        "all_other_inputs": "identical"}) for name, definition in ARM_DEFINITIONS.items()}
    if spec["component_hashes"] != expected_hashes or len(set(expected_hashes.values())) != 3:
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

    if spec["source_integrity"] != {
        "scope": "all initial Train, rolling Dev and Final objects",
        "timing": "complete before first paid controller call",
        "checks": "full zstd decode, every-line JSON parse, bytes, compressed and decoded hashes, start/end file identity",
        "controller_visibility": "receipt metadata only; no source rows or target statistics",
        "materialization_binding": "must reproduce the preflight receipt",
        "failure_action": "stop before paid work; select a new manifest, never post-score replacement",
    }:
        raise ValueError("all-source structural preflight must be frozen")

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
    if (spec["budget"].get("existing_global_cap_usd") != "200"
            or spec["budget"].get("paid_component") != "GLM controller turns only"
            or spec["budget"].get("atomic_unit") != "fresh plus archive plus compact controller sessions"
            or spec["budget"].get("unused_reservation_is_not_spend") is not True):
        raise ValueError("budget identity or atomic unit differs")
    return spec
