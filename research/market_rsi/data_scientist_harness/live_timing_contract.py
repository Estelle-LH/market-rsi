"""Synthetic policy gate for prospective live sports timing studies.

This module checks a controller-authored study contract. It deliberately does
not read a feed, certify a timestamp, set a scientific threshold, or claim that
an event signal leads a market. In particular, an event-start wall clock is not
interchangeable with a provider publish timestamp.
"""
from market_rsi import digest


TEXT = {"type": "string", "minLength": 1}
YES_NO = {"type": "string", "enum": ["yes", "no"]}


def obj(fields):
    return {
        "type": "object", "properties": fields, "required": list(fields),
        "additionalProperties": False,
    }


SCHEMA = obj({
    "study_id": TEXT,
    "provider": TEXT,
    "provider_clock_semantics": {
        "type": "string", "enum": ["event_start", "provider_publish", "unknown"],
    },
    "provider_clock_resolution_ms": {"type": "integer"},
    "local_receive_time_verified": YES_NO,
    "market_local_receive_time_verified": YES_NO,
    "immutable_raw": YES_NO,
    "correction_or_overturn_state": {
        "type": "string", "enum": ["verified", "partial", "missing"],
    },
    "prospective_capture": YES_NO,
    "decision_clock": {"type": "string", "enum": ["local_receive"]},
    "horizon_stage": {
        "type": "string", "enum": ["opened_train_discovery", "protected_confirmation"],
    },
    "candidate_horizons_ms": {
        "type": "array", "items": {"type": "integer"},
        "minItems": 1, "maxItems": 12, "uniqueItems": True,
    },
    "horizons_chosen_before_stage_score": YES_NO,
    "horizon_selection_rule": TEXT,
    "primary_reward_name": TEXT,
    "reward_chosen_before_stage_score": YES_NO,
    "feature_completeness_threshold_per_mille": {"type": "integer"},
    "maximum_publish_to_receive_p99_ms": {"type": "integer"},
    "latency_threshold_basis": TEXT,
    "market_response_definition_frozen": YES_NO,
    "market_lead_support_rule_frozen": YES_NO,
    "minimum_games": {"type": "integer"},
    "minimum_events": {"type": "integer"},
    "protected_holdout_status": {
        "type": "string", "enum": ["untouched", "opened"],
    },
    "source_receipt_sha256": TEXT,
})


def _need(blockers, condition, message):
    if not condition:
        blockers.append(message)


def _sha(value):
    return (isinstance(value, str) and len(value) == 64
            and all(character in "0123456789abcdef" for character in value))


def probe(contract):
    """Classify which claims the proposed timing design could eventually test."""
    capture = []
    _need(capture, contract["prospective_capture"] == "yes",
          "live timing needs a prospectively frozen capture, not a reused case")
    _need(capture, contract["immutable_raw"] == "yes",
          "live timing needs immutable raw records")
    _need(capture, contract["local_receive_time_verified"] == "yes",
          "PBP local receive time must be observed")
    _need(capture, contract["correction_or_overturn_state"] == "verified",
          "correction/overturn handling must be verified")
    _need(capture, contract["decision_clock"] == "local_receive",
          "decision time must use the observed local receive clock")
    _need(capture, contract["provider_clock_resolution_ms"] > 0,
          "provider clock resolution must be positive")
    horizons = contract["candidate_horizons_ms"]
    _need(capture, bool(horizons) and all(value > 0 for value in horizons),
          "candidate horizons must be positive")
    _need(capture, len(horizons) == len(set(horizons)),
          "candidate horizons must be unique")
    _need(capture, contract["horizons_chosen_before_stage_score"] == "yes",
          "candidate horizons must be chosen before this stage is scored")
    _need(capture, bool(contract["horizon_selection_rule"].strip()),
          "horizon selection rule must be frozen before score")
    _need(capture, bool(contract["primary_reward_name"].strip()),
          "the primary reward must be named before score")
    _need(capture, contract["reward_chosen_before_stage_score"] == "yes",
          "the primary reward must be chosen before this stage is scored")
    if contract["horizon_stage"] == "protected_confirmation":
        _need(capture, len(horizons) == 1,
              "protected confirmation must carry one frozen horizon")
    _need(capture, 0 < contract["feature_completeness_threshold_per_mille"] <= 1000,
          "feature completeness threshold must be in 1..1000 per mille")
    _need(capture, contract["minimum_games"] > 0 and contract["minimum_events"] > 0,
          "positive prospective game and event counts are required")
    _need(capture, _sha(contract["source_receipt_sha256"]),
          "source receipt must be a lowercase SHA256")

    strict_latency = list(capture)
    _need(strict_latency, contract["provider_clock_semantics"] == "provider_publish",
          "event-start or unknown clocks cannot measure publish-to-receive latency")
    _need(strict_latency, contract["maximum_publish_to_receive_p99_ms"] > 0,
          "strict latency needs a positive predeclared p99 threshold")
    _need(strict_latency, bool(contract["latency_threshold_basis"].strip()),
          "latency threshold needs an explicit external or strategy basis")

    market_lead = list(strict_latency)
    _need(market_lead, contract["market_local_receive_time_verified"] == "yes",
          "market lead needs observed venue receive time on the same local clock")
    _need(market_lead, contract["market_response_definition_frozen"] == "yes",
          "market response must be defined before opening outcomes")
    _need(market_lead, contract["market_lead_support_rule_frozen"] == "yes",
          "market lead support/refutation rules must be frozen before score")

    independent = list(market_lead)
    _need(independent, contract["minimum_games"] >= 20,
          "independent promotion needs at least 20 prospective games")
    _need(independent, contract["protected_holdout_status"] == "untouched",
          "independent promotion needs an untouched protected cohort")

    result = {
        "schema": "live_timing_contract_probe_v1",
        "contract": contract,
        "contract_sha256": digest(contract),
        "claim_gates": {
            "capture_integrity": {"policy_passed": not capture, "blockers": capture},
            "strict_publish_to_receive_latency": {
                "policy_passed": not strict_latency, "blockers": strict_latency,
            },
            "market_lead": {"policy_passed": not market_lead, "blockers": market_lead},
            "independent_confirmation": {
                "policy_passed": not independent, "blockers": independent,
            },
        },
        "event_start_clock_is_publish_clock": False,
        "provider_event_to_receive_is_strict_feed_latency": False,
        "capture_health_is_market_lead_evidence": False,
        "opened_train_may_compare_predeclared_horizons": True,
        "post_score_horizon_selection_allowed": False,
        "thresholds_scientifically_supported_by_this_probe": False,
        "source_admitted": False,
        "data_read": False,
        "predictive_score_computed": False,
    }
    result["probe_sha256"] = digest(result)
    return result
