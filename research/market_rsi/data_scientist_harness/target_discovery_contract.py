"""Typed opened-Train target discovery without an arbitrary-code escape hatch."""
from __future__ import annotations

from market_rsi import digest


FIELDS = {
    "spec_id", "opened_data_role", "clock_domain", "decision_anchor", "price_source",
    "pre_price_rule", "pre_price_max_age_seconds", "elapsed_horizons_seconds",
    "elapsed_endpoint_rule", "event_horizons_trade_count", "event_endpoint_rule",
    "max_event_target_wall_seconds", "target_transform", "direction_deadband_bps",
    "missing_endpoint_policy", "comparison_support", "source_receipt_sha256",
    "route_dev_access", "sealed_final_access",
}


def _sha(value: object, label: str) -> None:
    if (not isinstance(value, str) or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)):
        raise ValueError(f"{label} must be a lowercase SHA256")


def _ordered_unique_ints(values: object, *, low: int, high: int, label: str) -> None:
    if not isinstance(values, list) or len(values) > 16:
        raise ValueError(f"{label} must be a bounded list")
    if any(type(value) is not int or not low <= value <= high for value in values):
        raise ValueError(f"{label} contains an out-of-range value")
    if values != sorted(set(values)):
        raise ValueError(f"{label} must be sorted and unique")


def validate_target_discovery_spec(spec: dict) -> None:
    if not isinstance(spec, dict) or set(spec) != FIELDS:
        raise ValueError("exact target-discovery schema required")
    if not isinstance(spec["spec_id"], str) or not spec["spec_id"]:
        raise ValueError("target-discovery spec id required")
    if spec["opened_data_role"] != "opened_train":
        raise ValueError("target discovery is limited to opened Train")
    if not isinstance(spec["clock_domain"], str) or not spec["clock_domain"]:
        raise ValueError("target clock domain required")
    exact = {
        "decision_anchor": "play_event_time",
        "price_source": "historical_executed_trade_print_home_outcome",
        "pre_price_rule": "last_trade_at_or_before_decision_with_max_age",
        "elapsed_endpoint_rule": "last_trade_strictly_after_decision_at_or_before_horizon",
        "event_endpoint_rule": "nth_trade_strictly_after_decision",
        "missing_endpoint_policy": "unavailable_do_not_filter",
    }
    for key, value in exact.items():
        if spec[key] != value:
            raise ValueError(f"unsafe or unsupported {key}")
    if type(spec["pre_price_max_age_seconds"]) is not int or not 1 <= spec["pre_price_max_age_seconds"] <= 3600:
        raise ValueError("pre-price max age must be 1..3600 seconds")
    _ordered_unique_ints(spec["elapsed_horizons_seconds"], low=1, high=3600,
                         label="elapsed horizons")
    _ordered_unique_ints(spec["event_horizons_trade_count"], low=1, high=64,
                         label="event horizons")
    if not spec["elapsed_horizons_seconds"] and not spec["event_horizons_trade_count"]:
        raise ValueError("at least one elapsed or event target is required")
    if type(spec["max_event_target_wall_seconds"]) is not int or not 1 <= spec["max_event_target_wall_seconds"] <= 3600:
        raise ValueError("event target wall bound must be 1..3600 seconds")
    if spec["target_transform"] not in {"price_delta", "direction"}:
        raise ValueError("known target transform required")
    if (type(spec["direction_deadband_bps"]) is not int
            or not 0 <= spec["direction_deadband_bps"] <= 5000):
        raise ValueError("direction deadband must be 0..5000 bps")
    if spec["target_transform"] == "price_delta" and spec["direction_deadband_bps"] != 0:
        raise ValueError("price-delta target cannot carry a direction deadband")
    if spec["comparison_support"] not in {"per_target", "common_all_targets"}:
        raise ValueError("explicit target comparison support required")
    _sha(spec["source_receipt_sha256"], "source_receipt_sha256")
    if spec["route_dev_access"] is not False or spec["sealed_final_access"] is not False:
        raise ValueError("target discovery cannot access Route-Dev or Final")


def freeze_target_discovery_spec(spec: dict) -> dict:
    validate_target_discovery_spec(spec)
    result = {
        "schema": "frozen_target_discovery_spec_v1",
        "state": "target_spec_frozen",
        "spec": dict(spec),
        "performance_reward": None,
        "formal_selection_allowed": False,
    }
    result["record_sha256"] = digest(result)
    return result


def verify_frozen_target_discovery_spec(frozen: dict) -> dict:
    if not isinstance(frozen, dict) or set(frozen) != {
        "schema", "state", "spec", "performance_reward",
        "formal_selection_allowed", "record_sha256",
    }:
        raise ValueError("exact frozen target-discovery record required")
    unsigned = {key: value for key, value in frozen.items() if key != "record_sha256"}
    if (frozen["schema"] != "frozen_target_discovery_spec_v1"
            or frozen["state"] != "target_spec_frozen"
            or frozen["record_sha256"] != digest(unsigned)
            or frozen["performance_reward"] is not None
            or frozen["formal_selection_allowed"] is not False):
        raise ValueError("frozen target-discovery record was modified")
    validate_target_discovery_spec(frozen["spec"])
    return frozen["spec"]
