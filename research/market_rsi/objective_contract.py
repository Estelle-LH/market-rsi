"""Prospective objective governance for market time-series research.

Objective discovery and model improvement are separate phases.  A controller
may compare target definitions using public literature and already-open Train
data.  Before a Dev schedule can be frozen, the runner must freeze exactly one
objective contract.  Changing the target later requires a new experiment and
new unopened evaluation data.
"""
from __future__ import annotations

import copy
from pathlib import Path

from market_rsi import digest, fresh_json, identifier


SCHEMA = "market_research_objective_contract_v1"
POLICY_SCHEMA = "market_objective_discovery_policy_v1"


_OBJECTIVES = {
    "future-midpoint-point-60s-v1": {
        "status": "pilot_reference",
        "prediction_kind": "bounded_continuous",
        "prediction_unit": "probability",
        "prediction_bounds": [0.0, 1.0],
        "label": {
            "quantity": "first_admitted_midpoint_at_or_after_horizon",
            "aggregation": "point",
            "decision_horizon_seconds": 60,
            "maximum_label_lateness_seconds": 5,
            "future_window_seconds": None,
            "minimum_future_observations": 1,
        },
        "baseline": "decision_time_midpoint_persistence",
        "raw_metric": "equal_game_mse",
        "comparison_metric": "one_minus_candidate_mse_over_persistence_mse",
        "notes": "The existing pilot target. It can be too flat and sensitive to one future quote.",
    },
    "future-midpoint-window-mean-45-75s-v1": {
        "status": "train_only_audit_required",
        "prediction_kind": "bounded_continuous",
        "prediction_unit": "probability",
        "prediction_bounds": [0.0, 1.0],
        "label": {
            "quantity": "arithmetic_mean_of_admitted_midpoints_in_future_window",
            "aggregation": "uniform_mean",
            "decision_horizon_seconds": 60,
            "maximum_label_lateness_seconds": 15,
            "future_window_seconds": [45, 75],
            "minimum_future_observations": 3,
        },
        "baseline": "decision_time_midpoint_persistence",
        "raw_metric": "equal_game_mse",
        "comparison_metric": "one_minus_candidate_mse_over_persistence_mse",
        "notes": "A smoothed future-price target intended to reduce single-tick label noise.",
    },
    "future-midpoint-window-forward-ewma-45-75s-v1": {
        "status": "train_only_audit_required",
        "prediction_kind": "bounded_continuous",
        "prediction_unit": "probability",
        "prediction_bounds": [0.0, 1.0],
        "label": {
            "quantity": "forward_exponentially_weighted_mean_of_admitted_midpoints",
            "aggregation": "forward_ewma",
            "decision_horizon_seconds": 60,
            "maximum_label_lateness_seconds": 15,
            "future_window_seconds": [45, 75],
            "minimum_future_observations": 3,
            "half_life_seconds": 10,
            "weight_reference": "window_end",
            "effective_horizon_must_be_reported": True,
        },
        "baseline": "decision_time_midpoint_persistence",
        "raw_metric": "equal_game_mse",
        "comparison_metric": "one_minus_candidate_mse_over_persistence_mse",
        "notes": "The future-window analogue of a reverse EMA; later observations receive more weight and shift the effective horizon later.",
    },
    "future-midpoint-window-median-45-75s-v1": {
        "status": "train_only_audit_required",
        "prediction_kind": "bounded_continuous",
        "prediction_unit": "probability",
        "prediction_bounds": [0.0, 1.0],
        "label": {
            "quantity": "median_of_admitted_midpoints_in_future_window",
            "aggregation": "median",
            "decision_horizon_seconds": 60,
            "maximum_label_lateness_seconds": 15,
            "future_window_seconds": [45, 75],
            "minimum_future_observations": 3,
        },
        "baseline": "decision_time_midpoint_persistence",
        "raw_metric": "equal_game_mse",
        "comparison_metric": "one_minus_candidate_mse_over_persistence_mse",
        "notes": "Robust to isolated quote spikes but can suppress short genuine information jumps.",
    },
    "future-trade-vwap-45-75s-v1": {
        "status": "requires_trade_capture_and_train_only_audit",
        "prediction_kind": "bounded_continuous",
        "prediction_unit": "probability",
        "prediction_bounds": [0.0, 1.0],
        "label": {
            "quantity": "size_weighted_mean_of_confirmed_trades_in_future_window",
            "aggregation": "trade_vwap",
            "decision_horizon_seconds": 60,
            "maximum_label_lateness_seconds": 15,
            "future_window_seconds": [45, 75],
            "minimum_future_observations": 1,
            "required_trade_fields": [
                "market_id",
                "asset_id",
                "matched_at",
                "collector_observed_at",
                "price",
                "size",
                "side",
                "stable_trade_id",
            ],
        },
        "baseline": "decision_time_midpoint_persistence",
        "raw_metric": "equal_game_mse",
        "comparison_metric": "one_minus_candidate_mse_over_persistence_mse",
        "notes": (
            "Closer to executed prices, but conditional on a trade occurring; "
            "must report no-trade coverage, volume concentration, staleness, "
            "and bid-ask-bounce diagnostics."
        ),
    },
    "future-direction-deadband-45-75s-v1": {
        "status": "train_only_audit_required",
        "prediction_kind": "three_class_probability",
        "prediction_unit": "probability_vector_down_flat_up",
        "prediction_bounds": [0.0, 1.0],
        "label": {
            "quantity": "direction_of_future_window_mean_relative_to_decision_midpoint",
            "aggregation": "uniform_mean_then_deadband",
            "decision_horizon_seconds": 60,
            "maximum_label_lateness_seconds": 15,
            "future_window_seconds": [45, 75],
            "minimum_future_observations": 3,
            "deadband_rule": "frozen_train_only_threshold_above_observed_quote_noise",
        },
        "baseline": "train_only_class_frequency_and_persistence_direction",
        "raw_metric": "equal_game_multiclass_brier",
        "comparison_metric": "one_minus_candidate_brier_over_baseline_brier",
        "notes": "Tests predictable direction while treating tiny moves as flat.",
    },
    "event-resolution-probability-v1": {
        "status": "separate_long_horizon_study",
        "prediction_kind": "bounded_continuous",
        "prediction_unit": "event_probability",
        "prediction_bounds": [0.0, 1.0],
        "label": {
            "quantity": "resolved_binary_event_outcome",
            "aggregation": "event_resolution",
            "decision_horizon_seconds": None,
            "maximum_label_lateness_seconds": None,
            "future_window_seconds": None,
            "minimum_future_observations": None,
        },
        "baseline": "decision_time_market_probability",
        "raw_metric": "equal_market_brier",
        "comparison_metric": "one_minus_candidate_brier_over_market_brier",
        "notes": "A final-event forecasting question, not the same study as short-horizon price prediction.",
    },
}


def _add_midpoint_horizon(horizon: int, start: int, end: int,
                          half_life: int) -> None:
    common = {
        "status": "train_only_audit_required",
        "prediction_kind": "bounded_continuous",
        "prediction_unit": "probability",
        "prediction_bounds": [0.0, 1.0],
        "baseline": "decision_time_midpoint_persistence",
        "raw_metric": "equal_game_mse",
        "comparison_metric": "one_minus_candidate_mse_over_persistence_mse",
    }
    _OBJECTIVES[f"future-midpoint-point-{horizon}s-v1"] = {
        **copy.deepcopy(common),
        "label": {
            "quantity": "first_admitted_midpoint_at_or_after_horizon",
            "aggregation": "point",
            "decision_horizon_seconds": horizon,
            "maximum_label_lateness_seconds": 5,
            "future_window_seconds": None,
            "minimum_future_observations": 1,
        },
        "notes": "A longer-horizon point target; compare its movement rate and single-quote sensitivity with window targets.",
    }
    variants = {
        "mean": ("uniform_mean", "arithmetic_mean_of_admitted_midpoints_in_future_window"),
        "median": ("median", "median_of_admitted_midpoints_in_future_window"),
        "forward-ewma": (
            "forward_ewma", "forward_exponentially_weighted_mean_of_admitted_midpoints"
        ),
    }
    for slug, (aggregation, quantity) in variants.items():
        label = {
            "quantity": quantity,
            "aggregation": aggregation,
            "decision_horizon_seconds": horizon,
            "maximum_label_lateness_seconds": end - horizon,
            "future_window_seconds": [start, end],
            "minimum_future_observations": 3,
        }
        if slug == "forward-ewma":
            label.update({
                "half_life_seconds": half_life,
                "weight_reference": "window_end",
                "effective_horizon_must_be_reported": True,
            })
        objective_slug = "forward-ewma" if slug == "forward-ewma" else slug
        _OBJECTIVES[
            f"future-midpoint-window-{objective_slug}-{start}-{end}s-v1"
        ] = {
            **copy.deepcopy(common),
            "label": label,
            "notes": (
                "A longer-horizon future-window target. It is pre-materialized only "
                "to let the Train-only controller audit horizon and smoothing choices."
            ),
        }


for _horizon, _start, _end, _half_life in (
    (300, 270, 330, 20),
    (900, 840, 960, 40),
):
    _add_midpoint_horizon(_horizon, _start, _end, _half_life)


def objective_catalog() -> dict:
    return {
        "schema": "market_research_objective_catalog_v1",
        "objectives": [
            {"objective_id": objective_id, **copy.deepcopy(spec)}
            for objective_id, spec in _OBJECTIVES.items()
        ],
        "catalog_is_exhaustive": False,
    }


def discovery_policy() -> dict:
    body = {
        "schema": POLICY_SCHEMA,
        "phase_order": [
            "objective_discovery_on_open_train",
            "freeze_one_objective_contract",
            "freeze_unopened_dev_schedule",
            "model_and_feature_self_improvement",
            "one_time_dev_scoring",
        ],
        "allowed_discovery_inputs": [
            "public_literature",
            "already_open_train_features",
            "already_open_train_labels",
        ],
        "forbidden_discovery_inputs": [
            "current_or_future_dev_labels",
            "future_test",
            "candidate_scores_on_unopened_data",
        ],
        "required_train_only_diagnostics": [
            "coverage_by_utc_day_and_whole_game",
            "unchanged_or_flat_fraction",
            "target_scale_and_tail_quantiles",
            "label_stability_under_small_window_or_horizon_changes",
            "effective_horizon_after_weighting",
            "persistence_or_market_baseline_error",
            "baseline_error_by_day_and_whole_game",
            "effective_independent_days_and_games",
            "trade_occurrence_and_volume_coverage_when_trade_labels_are_used",
            "transaction_price_bid_ask_bounce_when_trade_labels_are_used",
        ],
        "reporting": {
            "raw_error_required": True,
            "scale_free_skill_vs_predeclared_baseline_required": True,
            "human_readable_units_required": True,
            "target_conditioned_slices_are_diagnostic_only": True,
        },
        "change_rule": (
            "Changing label quantity, horizon, smoothing window, deadband, baseline, "
            "or primary score requires a new experiment ID and fresh unopened Dev."
        ),
    }
    return {**body, "policy_sha256": digest(body)}


def build_objective_contract(
    *,
    experiment_id: str,
    objective_id: str,
    train_diagnostics_sha256: str,
    literature_snapshot_sha256: str,
    literature_ids: list[str],
    evidence_class: str,
) -> dict:
    """Build one immutable objective chosen before Dev scheduling."""
    identifier(experiment_id)
    if objective_id not in _OBJECTIVES:
        raise ValueError("unknown objective ID")
    if evidence_class not in {"diagnostic", "formal_learning"}:
        raise ValueError("objective evidence class must be diagnostic or formal_learning")
    for value in (train_diagnostics_sha256, literature_snapshot_sha256):
        if (not isinstance(value, str) or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)):
            raise ValueError("lowercase SHA-256 objective evidence required")
    if (not isinstance(literature_ids, list)
            or literature_ids != sorted(set(literature_ids))
            or any(not isinstance(item, str) or not item for item in literature_ids)):
        raise ValueError("literature IDs must be a sorted unique list")
    body = {
        "schema": SCHEMA,
        "experiment_id": experiment_id,
        "objective_id": objective_id,
        "objective": copy.deepcopy(_OBJECTIVES[objective_id]),
        "selection": {
            "phase": "objective_discovery_on_open_train",
            "evidence_class": evidence_class,
            "selected_using": "public_literature_and_already_open_train_only",
            "train_diagnostics_sha256": train_diagnostics_sha256,
            "literature_snapshot_sha256": literature_snapshot_sha256,
            "literature_ids": literature_ids,
            "dev_labels_used": False,
            "future_test_used": False,
            "selected_before_dev_schedule": True,
        },
        "governance": discovery_policy(),
    }
    value = {**body, "objective_contract_sha256": digest(body)}
    validate_objective_contract(value)
    return value


def validate_objective_contract(value: dict, *, experiment_id: str | None = None) -> dict:
    if not isinstance(value, dict) or set(value) != {
        "schema", "experiment_id", "objective_id", "objective", "selection",
        "governance", "objective_contract_sha256",
    }:
        raise ValueError("objective contract fields changed")
    identifier(value.get("experiment_id"))
    if experiment_id is not None and value["experiment_id"] != experiment_id:
        raise ValueError("objective contract belongs to a different experiment")
    objective_id = value.get("objective_id")
    if (value.get("schema") != SCHEMA or objective_id not in _OBJECTIVES
            or value.get("objective") != _OBJECTIVES[objective_id]
            or value.get("governance") != discovery_policy()):
        raise ValueError("objective definition or policy changed")
    selection = value.get("selection")
    if (not isinstance(selection, dict) or set(selection) != {
            "phase", "evidence_class", "selected_using", "train_diagnostics_sha256",
            "literature_snapshot_sha256", "literature_ids", "dev_labels_used",
            "future_test_used", "selected_before_dev_schedule",
    } or selection["phase"] != "objective_discovery_on_open_train"
            or selection["evidence_class"] not in {"diagnostic", "formal_learning"}
            or selection["selected_using"]
            != "public_literature_and_already_open_train_only"
            or selection["dev_labels_used"] is not False
            or selection["future_test_used"] is not False
            or selection["selected_before_dev_schedule"] is not True
            or selection["literature_ids"] != sorted(set(selection["literature_ids"]))):
        raise ValueError("objective selection boundary changed")
    for key in ("train_diagnostics_sha256", "literature_snapshot_sha256"):
        candidate = selection[key]
        if (not isinstance(candidate, str) or len(candidate) != 64
                or any(character not in "0123456789abcdef" for character in candidate)):
            raise ValueError("objective evidence hash changed")
    body = {key: value[key] for key in value if key != "objective_contract_sha256"}
    if value["objective_contract_sha256"] != digest(body):
        raise ValueError("objective contract hash changed")
    return value


def label_delay_bounds_ms(value: dict) -> tuple[int, int]:
    """Return the causal label-availability window frozen by an objective."""
    checked = validate_objective_contract(value)
    label = checked["objective"]["label"]
    horizon = label.get("decision_horizon_seconds")
    lateness = label.get("maximum_label_lateness_seconds")
    window = label.get("future_window_seconds")
    if isinstance(window, list) and len(window) == 2:
        start, end = window
        if (type(start) is not int or type(end) is not int
                or start <= 0 or end <= start):
            raise ValueError("invalid frozen objective window")
        # A window statistic is knowable once the wall clock reaches its end.
        return end * 1000, end * 1000
    if (type(horizon) is int and type(lateness) is int
            and horizon > 0 and lateness >= 0):
        return horizon * 1000, (horizon + lateness) * 1000
    raise ValueError("objective has no bounded short-horizon label availability")


def freeze_objective_contract(path: Path, **kwargs) -> dict:
    value = build_objective_contract(**kwargs)
    fresh_json(Path(path), value)
    return value


def promote_diagnostic_objective_for_formal(value: dict) -> tuple[dict, dict]:
    """Adopt an unchanged pre-Dev diagnostic choice for formal learning.

    This is not a second controller sample. It changes only the evidence-class
    declaration after the first valid objective choice and before any Dev
    schedule exists; the objective and all selection evidence remain identical.
    """
    source = validate_objective_contract(value)
    if source["selection"]["evidence_class"] != "diagnostic":
        raise ValueError("only a diagnostic pre-Dev objective can be promoted")
    formal = build_objective_contract(
        experiment_id=source["experiment_id"],
        objective_id=source["objective_id"],
        train_diagnostics_sha256=source["selection"]["train_diagnostics_sha256"],
        literature_snapshot_sha256=source["selection"]["literature_snapshot_sha256"],
        literature_ids=source["selection"]["literature_ids"],
        evidence_class="formal_learning",
    )
    receipt_body = {
        "schema": "market_formal_objective_adoption_v1",
        "experiment_id": source["experiment_id"],
        "objective_id": source["objective_id"],
        "source_objective_contract_sha256": source["objective_contract_sha256"],
        "formal_objective_contract_sha256": formal["objective_contract_sha256"],
        "objective_definition_unchanged": source["objective"] == formal["objective"],
        "selection_evidence_unchanged": all(
            source["selection"][key] == formal["selection"][key]
            for key in (
                "train_diagnostics_sha256", "literature_snapshot_sha256",
                "literature_ids", "dev_labels_used", "future_test_used",
                "selected_before_dev_schedule",
            )
        ),
        "controller_resampled": False,
        "dev_schedule_created_before_adoption": False,
        "future_test_used": False,
    }
    if (receipt_body["objective_definition_unchanged"] is not True
            or receipt_body["selection_evidence_unchanged"] is not True):
        raise ValueError("formal adoption changed the scientific objective")
    return formal, {**receipt_body, "receipt_sha256": digest(receipt_body)}


def pilot_reference_objective_contract(experiment_id: str) -> dict:
    """Return an explicit diagnostic-only contract for historical canaries."""
    return build_objective_contract(
        experiment_id=experiment_id,
        objective_id="future-midpoint-point-60s-v1",
        train_diagnostics_sha256=digest({"legacy_pilot": experiment_id}),
        literature_snapshot_sha256=digest({"legacy_pilot_snapshot": 1}),
        literature_ids=[],
        evidence_class="diagnostic",
    )
