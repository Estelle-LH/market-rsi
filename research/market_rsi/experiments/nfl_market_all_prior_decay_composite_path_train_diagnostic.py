#!/usr/bin/env python3
"""Opened-Train Discovery runner for MarketAllPriorDecayCompositePath-v4.

This is a trainer-support-only delta from Attempt 3.  The exact three-week
representation is retained, while the one-parameter candidate is fitted on
every strictly prior eligible week with a fixed one-week half-life.  All seven
controls are read only from the completed Attempt-3 artifact.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

import numpy as np

from experiments import nfl_market_recency_weighted_composite_path_train_diagnostic as parent


recent = parent.parent
base = parent.base
offset = parent.offset
calibration = parent.calibration
prior = parent.prior
SOURCE_ROOT = parent.SOURCE_ROOT
PERSISTENT_ARTIFACT_ROOT = parent.PERSISTENT_ARTIFACT_ROOT
EXPECTED_EVENTS = parent.EXPECTED_EVENTS
EXPECTED_DATES = parent.EXPECTED_DATES
EXPECTED_MATERIALIZED_KEY_SHA256 = parent.EXPECTED_MATERIALIZED_KEY_SHA256
EXPECTED_CHECK_MASK_SHA256 = parent.EXPECTED_CHECK_MASK_SHA256
MAX_STALENESS_SECONDS = parent.MAX_STALENESS_SECONDS
STRICT_WIN_TOLERANCE = parent.STRICT_WIN_TOLERANCE
MINIMUM_RECENT_ROWS = parent.MINIMUM_RECENT_ROWS
EXPECTED_REAL_RECENT = parent.EXPECTED_REAL_RECENT

EXPECTED_PARENT_RUNNER_SHA256 = "05af717084499618c99fefd034972681d4acef12b226b5fc8b8a4513c26fdbd1"
EXPECTED_PARENT_TEST_SHA256 = "9d2491170a1862a4239118ad8ff03d95e5c4ed5e682e131a5023ae4ac4b1363d"
CONTROLLER_PROPOSAL_PATH = (
    Path(__file__).resolve().parents[1] / "supervisor_harness"
    / "AGENT_LOG_DISCOVERY_ATTEMPT4_CONTROLLER_2026-09-29.md"
)
EXPECTED_CONTROLLER_PROPOSAL_SHA256 = "fab9f134f2e1523265a429fbd8ff2fc9a6ca98f37216a60d7371683e43d01595"
PARENT_RESULT_REVIEW_PATH = (
    Path(__file__).resolve().parents[1] / "supervisor_harness"
    / "AGENT_LOG_MARKET_RECENCY_WEIGHTED_COMPOSITE_PATH_V3_RESULT_INDEPENDENT_REVIEW_2026-09-29.md"
)
EXPECTED_PARENT_RESULT_REVIEW_SHA256 = (
    "016930f4d027be2ecee79b61beb76a914eb3198cc853c632cc79d764fcceb0ad"
)

ARCHIVED_PARENT_ROOT = PERSISTENT_ARTIFACT_ROOT / (
    "first-real-train-diagnostic-market-recency-weighted-composite-path-20260929-01"
)
ARCHIVED_PARENT_SHA256 = MappingProxyType({
    "exclusions.json": "cde9f1b57d1a6c8337200b6312cbac1ef2dae0434a9d30786baa52cfebb98df4",
    "input_receipts.json": "cc030734a5af5a264cda6b820cf4f08cafb0d2b8c30c70c13a210c513f57ca6e",
    "manifest.json": "03a0b3d932c3faff55ecde90bbcbcb99a24609a919e9562155112fc683c8b2af",
    "pre_score_lock.json": "2fd4e708eb1f0160bcc34edd6ddde8155e66bc3494cc2e2de7a9e978cbe1cfbd",
    "predictions.csv": "cbf2fba9fdd08f42ee9897cc01fdbf06052b9f10097eedd5dac21de84c53e9b1",
    "scorecard.json": "556af6167bed0bee9a2e7d47a1ba742af801f005fbcc16cb4d5af812ccae61cf",
    "staleness_inventory.json": "3b545bd2542b4a4102ed0aa0f2adaed435322fc58bea06b599ebee765abea10e",
})
ARCHIVED_FIELDS = (*parent.ARCHIVED_FIELDS, "recency_weighted_candidate_probability")

EXPECTED_REAL_ALL_PRIOR = MappingProxyType({
    1: MappingProxyType({
        "weeks": tuple(f"2025_{week:02d}" for week in range(1, 8)),
        "rows": 107, "ones": 61, "zeros": 46,
        "per_week": (16, 16, 16, 15, 14, 15, 15),
        "weight_sum": 29.625, "squared_weight_sum": 19.94140625,
        "class_weight_totals": (12.640625, 16.984375),
    }),
    2: MappingProxyType({
        "weeks": tuple(f"2025_{week:02d}" for week in range(1, 9)),
        "rows": 120, "ones": 69, "zeros": 51,
        "per_week": (16, 16, 16, 15, 14, 15, 15, 13),
        "weight_sum": 27.8125, "squared_weight_sum": 17.9853515625,
        "class_weight_totals": (11.3203125, 16.4921875),
    }),
    3: MappingProxyType({
        "weeks": tuple(f"2025_{week:02d}" for week in range(1, 11)),
        "rows": 148, "ones": 81, "zeros": 67,
        "per_week": (16, 16, 16, 15, 14, 15, 15, 13, 14, 14),
        "weight_sum": 27.953125, "squared_weight_sum": 18.62408447265625,
        "class_weight_totals": (13.830078125, 14.123046875),
    }),
    4: MappingProxyType({
        "weeks": tuple(f"2025_{week:02d}" for week in range(1, 13)),
        "rows": 177, "ones": 98, "zeros": 79,
        "per_week": (16, 16, 16, 15, 14, 15, 15, 13, 14, 14, 15, 14),
        "weight_sum": 28.48828125, "squared_weight_sum": 18.914005279541016,
        "class_weight_totals": (11.95751953125, 16.53076171875),
    }),
})

CANDIDATE_SPEC = MappingProxyType({
    "name": "MarketAllPriorDecayCompositePath-v4",
    "parent_representation": dict(recent.CANDIDATE_SPEC),
    "transform_fit_support": "three largest week labels strictly before first check week",
    "candidate_fit_support": "all fit rows with numeric game week strictly before first check week",
    "event_weight": "2**(numeric_week_index-latest_eligible_numeric_week_index)",
    "half_life_weeks": 1.0,
    "week_or_class_normalization": False,
    "transform_weighting": "unweighted identical to Attempts 2-3",
    "linear_predictor": "eta=market_logit+w_composite*z_composite",
    "objective": "event-weighted mean Bernoulli NLL plus 0.5*w_composite^2",
    "lambda": 1.0,
    "intercept": False,
    "market_recalibration_coefficient": False,
    "coefficient_constraint": "unconstrained",
    "initial_parameter": 0.0,
    "optimizer": "L-BFGS-B analytic gradient maxiter=1000 gtol=1e-8 ftol=1e-12",
    "dtype": "float64",
    "hyperparameter_search": False,
})
EXPECTED_CANDIDATE_SPEC_SHA256 = (
    "d6f24ff533387ef6a11aaf0627f27879d0e3c577e7c303aa8e864dc20d0f3f47"
)


def execution_identity() -> dict:
    return {
        "parent_runner_sha256": base._sha256(Path(parent.__file__)),
        "parent_test_sha256": base._sha256(
            Path(__file__).resolve().parents[1] / "tests"
            / "test_nfl_market_recency_weighted_composite_path_train_diagnostic.py"
        ),
        "controller_proposal_sha256": base._sha256(CONTROLLER_PROPOSAL_PATH),
        "parent_result_review_sha256": base._sha256(PARENT_RESULT_REVIEW_PATH),
        "runtime_and_deeper_dependencies": parent._validate_execution_identity(),
    }


def _validate_execution_identity() -> dict:
    identity = execution_identity()
    expected = {
        "parent_runner_sha256": EXPECTED_PARENT_RUNNER_SHA256,
        "parent_test_sha256": EXPECTED_PARENT_TEST_SHA256,
        "controller_proposal_sha256": EXPECTED_CONTROLLER_PROPOSAL_SHA256,
        "parent_result_review_sha256": EXPECTED_PARENT_RESULT_REVIEW_SHA256,
    }
    if any(identity[key] != value for key, value in expected.items()):
        raise RuntimeError(f"frozen execution identity changed: {identity}")
    return identity


def _validate_frozen_specs() -> None:
    parent._validate_frozen_specs()
    observed = base._digest(dict(CANDIDATE_SPEC))
    if observed != EXPECTED_CANDIDATE_SPEC_SHA256:
        raise RuntimeError(f"all-prior candidate spec changed: {observed}")


def validate_archived_parent_artifact(root: Path, *, verify_frozen_hashes: bool) -> dict:
    root = Path(root).resolve()
    observed = {path.name for path in root.iterdir() if path.is_file()}
    if observed != set(ARCHIVED_PARENT_SHA256):
        raise ValueError("archived Attempt-3 artifact file set differs")
    hashes = {name: base._sha256(root / name) for name in sorted(observed)}
    if verify_frozen_hashes and hashes != dict(ARCHIVED_PARENT_SHA256):
        raise ValueError("archived Attempt-3 artifact hash changed")
    manifest = base._strict_json(root / "manifest.json")
    if (not isinstance(manifest, dict)
            or manifest.get("schema") != "nfl_market_recency_weighted_composite_path_train_manifest_v1"
            or manifest.get("complete") is not True
            or manifest.get("status") != "COMPLETE"
            or manifest.get("model_fits") != 4
            or manifest.get("control_refits") != 0
            or manifest.get("provider_cost_usd") != "0"
            or manifest.get("route_dev_opened") is not False
            or manifest.get("sealed_final_opened") is not False
            or manifest.get("external_fetch") is not False
            or manifest.get("paid_provider") is not False):
        raise ValueError("archived Attempt-3 manifest boundary failed")
    bindings = {
        "pre_score_lock.json": manifest.get("pre_score_lock_sha256"),
        "input_receipts.json": manifest.get("input_receipts_sha256"),
        "exclusions.json": manifest.get("exclusions_sha256"),
        "staleness_inventory.json": manifest.get("staleness_inventory_sha256"),
        "predictions.csv": manifest.get("predictions_sha256"),
        "scorecard.json": manifest.get("scorecard_sha256"),
    }
    if any(hashes[name] != value for name, value in bindings.items()):
        raise ValueError("archived Attempt-3 manifest hash binding failed")
    return {"artifact_root": str(root), "artifact_hashes": hashes}


def numeric_week_index(label: str) -> int:
    year, week = recent._week_key(label)
    try:
        return date.fromisocalendar(year, week, 1).toordinal() // 7
    except ValueError:
        recent._invalid_recent("invalid_iso_game_week_label", label=label)
    raise AssertionError("unreachable")


def all_prior_decay_weights(
        rows: Sequence[base.DiagnosticRow], first_check_week: str, *,
        expected: Mapping[str, object] | None = None) -> tuple[np.ndarray, dict]:
    if not rows:
        recent._invalid_recent("empty_all_prior_fit_rows")
    check_index = numeric_week_index(first_check_week)
    row_weeks = [offset.game_week(row.game_id) for row in rows]
    row_indices = [numeric_week_index(label) for label in row_weeks]
    if any(index >= check_index for index in row_indices):
        recent._invalid_recent(
            "all_prior_fit_includes_same_or_later_week",
            first_check_week=first_check_week,
        )
    week_labels = tuple(sorted(set(row_weeks), key=recent._week_key))
    latest_index = max(row_indices)
    mapping = {label: float(2.0 ** (numeric_week_index(label) - latest_index))
               for label in week_labels}
    weights = np.asarray([mapping[label] for label in row_weeks], dtype=np.float64)
    if (weights.shape != (len(rows),) or not np.all(np.isfinite(weights))
            or np.any(weights <= 0) or max(mapping.values()) != 1.0):
        recent._invalid_recent("invalid_all_prior_decay_weights")
    outcomes = np.asarray([row.trusted["outcome"] for row in rows], dtype=np.int64)
    if not np.all(np.isin(outcomes, (0, 1))):
        recent._invalid_recent("invalid_all_prior_outcome")
    total = float(np.sum(weights))
    squared = float(np.sum(weights ** 2))
    per_week_counts = tuple(row_weeks.count(label) for label in week_labels)
    class_totals = tuple(float(np.sum(weights[outcomes == label])) for label in (0, 1))
    observed = {
        "weeks": week_labels, "rows": len(rows),
        "ones": int(np.sum(outcomes)), "zeros": int(len(rows) - np.sum(outcomes)),
        "per_week": per_week_counts, "weight_sum": total,
        "squared_weight_sum": squared, "class_weight_totals": class_totals,
    }
    if expected is not None and observed != dict(expected):
        recent._invalid_recent(
            "exact_real_all_prior_cohort_or_weight_mismatch",
            observed=observed, expected=dict(expected),
        )
    report = {
        "first_check_week": first_check_week,
        "latest_eligible_week": week_labels[-1],
        "week_weight_mapping": mapping,
        "per_week": [{
            "week": label,
            "events": per_week_counts[index],
            "ones": int(sum(row.trusted["outcome"] == 1 for row in rows
                            if offset.game_week(row.game_id) == label)),
            "zeros": int(sum(row.trusted["outcome"] == 0 for row in rows
                             if offset.game_week(row.game_id) == label)),
            "event_weight": mapping[label],
            "weight_sum": per_week_counts[index] * mapping[label],
        } for index, label in enumerate(week_labels)],
        "events": len(rows),
        "ones": int(np.sum(outcomes)),
        "zeros": int(len(rows) - np.sum(outcomes)),
        "weight_sum": total,
        "squared_weight_sum": squared,
        "kish_effective_rows": total ** 2 / squared,
        "weight_totals_by_class": {"0": class_totals[0], "1": class_totals[1]},
        "eligible_event_weight_ledger": [{
            "ordinal": ordinal,
            "game_id": row.game_id,
            "split_date": row.split_date,
            "event_id": row.trusted["event_id"],
            "outcome": row.trusted["outcome"],
            "game_week": row_weeks[ordinal],
            "event_weight": float(weights[ordinal]),
        } for ordinal, row in enumerate(rows)],
    }
    return weights, report


weighted_objective_gradient = parent.weighted_objective_gradient


def fit_all_prior_decay_composite(
        z_composite: object, outcomes: object, market_logits: object,
        weights: object) -> tuple[np.ndarray, dict]:
    return parent.fit_weighted_composite(
        z_composite, outcomes, market_logits, weights
    )


def _merge_transformed_groups(
        selected: Sequence[base.DiagnosticRow], older: Sequence[base.DiagnosticRow],
        transformed: Mapping[str, Mapping[str, np.ndarray]],
        eligible: Sequence[base.DiagnosticRow]) -> dict[str, np.ndarray]:
    if set(transformed["selected"]) != set(transformed["older"]):
        recent._invalid_recent("selected_older_transform_field_mismatch")
    merged: dict[str, np.ndarray] = {}
    for field in transformed["selected"]:
        keyed = {
            row.key: np.asarray(value)
            for group_rows, values in (
                (selected, transformed["selected"][field]),
                (older, transformed["older"][field]),
            )
            for row, value in zip(group_rows, values, strict=True)
        }
        if set(keyed) != {row.key for row in eligible}:
            recent._invalid_recent("eligible_transform_row_mismatch", field=field)
        merged[field] = np.asarray([keyed[row.key] for row in eligible], dtype=np.float64)
        if not np.all(np.isfinite(merged[field])):
            recent._invalid_recent("nonfinite_all_prior_transform", field=field)
    return merged


def _fit_and_predict(
        plan: Sequence[dict], *, minimum_recent_rows: int,
        enforce_real_counts: bool,
        phase_state: dict[str, bool]) -> tuple[list[dict], list[dict]]:
    predictions: list[dict] = []
    reports: list[dict] = []
    for fold in plan:
        expected_recent = EXPECTED_REAL_RECENT[fold["fold"]] if enforce_real_counts else None
        selection = recent.select_recent_candidate_rows(
            fold["fit_rows"], fold["check_rows"], minimum_rows=minimum_recent_rows,
            expected=expected_recent,
        )
        selected = selection["selected_rows"]
        older = selection["older_rows"]
        eligible = sorted([*older, *selected], key=lambda row: row.key)
        transformed = recent.fit_recent_composite_transform(
            selected, older, fold["check_rows"]
        )
        eligible_transformed = _merge_transformed_groups(
            selected, older, transformed, eligible
        )
        first_check_week = selection["report"]["first_check_week"]
        expected_all = EXPECTED_REAL_ALL_PRIOR[fold["fold"]] if enforce_real_counts else None
        weights, weight_report = all_prior_decay_weights(
            eligible, first_check_week, expected=expected_all
        )
        first_check_cutoff = min(row.trusted["cutoff_ms"] for row in fold["check_rows"])
        unavailable = [row.game_id for row in eligible
                       if row.trusted["outcome_available_ms"] >= first_check_cutoff]
        if unavailable:
            recent._invalid_recent(
                "all_prior_outcome_not_strictly_available", events=unavailable
            )
        labels = np.asarray([row.trusted["outcome"] for row in eligible], dtype=np.float64)
        if len(np.unique(labels)) != 2:
            recent._invalid_recent("all_prior_rows_lack_both_outcome_classes")
        market = np.asarray(
            [row.trusted["market_probability"] for row in eligible], dtype=np.float64
        )
        z = eligible_transformed["z_composite"]
        logits = eligible_transformed["logits"]
        residual_products = z * (labels - market)
        weighted_moment = float(np.sum(weights * residual_products) / np.sum(weights))
        gradient_at_zero = float(weighted_objective_gradient(
            np.zeros(1), z, labels, logits, weights
        )[1][0])
        if not math.isclose(gradient_at_zero, -weighted_moment,
                            rel_tol=0.0, abs_tol=1e-15):
            raise RuntimeError("gradient at zero is not negative weighted moment")
        weight_report.update({
            "weighted_mean_z_times_y_minus_market": weighted_moment,
            "unweighted_mean_z_times_y_minus_market": float(np.mean(residual_products)),
            "gradient_at_zero": gradient_at_zero,
            "coefficient_descent_direction": -gradient_at_zero,
            "gradient_at_zero_equals_negative_weighted_moment": True,
            "signed_moments_by_week": [],
        })
        row_weeks = [offset.game_week(row.game_id) for row in eligible]
        for week in weight_report["week_weight_mapping"]:
            mask = np.asarray([label == week for label in row_weeks], dtype=bool)
            weight_report["signed_moments_by_week"].append({
                "week": week,
                "events": int(np.sum(mask)),
                "unweighted_mean_z_times_y_minus_market": float(np.mean(residual_products[mask])),
                "weighted_mean_z_times_y_minus_market": float(
                    np.sum(weights[mask] * residual_products[mask]) / np.sum(weights[mask])
                ),
            })
        phase_state["fit_started"] = True
        parameter, optimizer = fit_all_prior_decay_composite(z, labels, logits, weights)
        candidate_values = recent.recent_probabilities(
            parameter, transformed["check"]["z_composite"],
            transformed["check"]["logits"],
            [row.trusted["market_probability"] for row in fold["check_rows"]],
        )
        candidate_records = base._prediction_records(
            list(fold["check_rows"]), candidate_values
        )
        outcomes = [row.trusted["outcome"] for row in fold["check_rows"]]
        market_values = [row.trusted["market_probability"] for row in fold["check_rows"]]
        market_metrics = base._simple_metrics(outcomes, market_values)
        candidate_metrics = base._simple_metrics(
            outcomes, [item["probability"] for item in candidate_records]
        )
        reports.append({
            "fold": fold["fold"], "fit_dates": fold["fit_dates"],
            "check_dates": fold["check_dates"],
            "expanding_fit_events": len(fold["fit_rows"]),
            "check_events": len(fold["check_rows"]),
            "fit_label_unavailable_events": fold["fit_label_unavailable_events"],
            "recent_selection": selection["report"],
            "breadth": {
                "selected_recent_transform_fit": recent._breadth(selected),
                "older_eligible_fit": recent._breadth(older),
                "all_prior_candidate_fit": recent._breadth(eligible),
                "ineligible_same_or_later_week_fit": recent._breadth(
                    selection["ineligible_same_or_later_week_rows"]
                ),
                "check": recent._breadth(fold["check_rows"]),
            },
            "transform_parameters": transformed["parameters"],
            "selected_recent_fit_information": recent.information_diagnostics(
                transformed["selected"], selected
            ),
            "older_fit_information": recent.information_diagnostics(
                transformed["older"], older
            ),
            "all_prior_fit_information": recent.information_diagnostics(
                eligible_transformed, eligible
            ),
            "check_information": recent.information_diagnostics(
                transformed["check"], fold["check_rows"]
            ),
            "all_prior_decay_weighting": weight_report,
            "market": market_metrics, "candidate": candidate_metrics,
            "candidate_minus_market_brier": candidate_metrics["brier"] - market_metrics["brier"],
            "candidate_minus_market_log_loss": candidate_metrics["log_loss"] - market_metrics["log_loss"],
            "optimizer": optimizer, "w_composite": float(parameter[0]),
            "candidate_probability_correction": {
                "minimum": float(np.min(candidate_values - np.asarray(market_values))),
                "mean": float(np.mean(candidate_values - np.asarray(market_values))),
                "maximum": float(np.max(candidate_values - np.asarray(market_values))),
            },
        })
        for row, record in zip(fold["check_rows"], candidate_records, strict=True):
            predictions.append({"fold": fold["fold"], "row": row, "candidate": record})
    keys = [item["row"].key for item in predictions]
    if len(keys) != len(set(keys)):
        raise ValueError("an event appears in multiple check folds")
    return predictions, reports


def bind_archived_controls(
        predictions: Sequence[dict], fold_reports: Sequence[dict],
        predictions_csv: Path, *, verify_frozen_hash: bool) -> dict:
    if (verify_frozen_hash and base._sha256(predictions_csv)
            != ARCHIVED_PARENT_SHA256["predictions.csv"]):
        raise ValueError("archived Attempt-3 predictions hash changed")
    with Path(predictions_csv).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != ARCHIVED_FIELDS:
            raise ValueError("archived Attempt-3 prediction schema changed")
        archived = list(reader)
    if len(archived) != len(predictions):
        raise ValueError("archived Attempt-3 row count differs")
    arm_columns = {
        "ordinary": "ordinary_probability",
        "market_only_calibration": "market_only_calibration_probability",
        "archived_full_offset": "archived_full_offset_probability",
        "archived_attempt1": "candidate_probability",
        "archived_attempt2": "recent_composite_candidate_probability",
        "archived_attempt3": "recency_weighted_candidate_probability",
    }
    for item, control in zip(predictions, archived, strict=True):
        row = item["row"]
        identity = (
            str(item["fold"]), row.game_id, row.split_date,
            offset.game_week(row.game_id), row.trusted["event_id"],
            row.trusted["market_id"], str(row.trusted["cutoff_ms"]),
            str(row.trusted["outcome_available_ms"]), str(row.trusted["outcome"]),
        )
        if identity != tuple(control[name] for name in ARCHIVED_FIELDS[:9]):
            raise ValueError("archived Attempt-3 identity/order/outcome differs")
        if row.trusted["market_probability"] != float(control["market_probability"]):
            raise ValueError("archived Attempt-3 market probability differs")
        for arm, column in arm_columns.items():
            item[arm] = base._prediction_records([row], [float(control[column])])[0]
    for report in fold_reports:
        items = [item for item in predictions if item["fold"] == report["fold"]]
        outcomes = [item["row"].trusted["outcome"] for item in items]
        for arm in arm_columns:
            metrics = base._simple_metrics(
                outcomes, [item[arm]["probability"] for item in items]
            )
            report[arm] = metrics
            report[f"candidate_minus_{arm}_brier"] = report["candidate"]["brier"] - metrics["brier"]
            report[f"candidate_minus_{arm}_log_loss"] = report["candidate"]["log_loss"] - metrics["log_loss"]
    return {
        "archived_predictions_sha256": base._sha256(predictions_csv),
        "rows": len(predictions), "identity_order_outcomes_exact": True,
        "market_probability_exact": True, "control_refits": 0,
        "control_probability_source": "immutable archived Attempt-3 predictions",
    }


CONTROL_NAMES = (
    "ordinary", "market_only_calibration", "archived_full_offset",
    "archived_attempt1", "archived_attempt2", "archived_attempt3",
)


def corrected_grouped_inference(predictions: Sequence[dict]) -> dict:
    outcomes = [item["row"].trusted["outcome"] for item in predictions]
    arms = {
        "market": [item["row"].trusted["market_probability"] for item in predictions],
        **{name: [item[name]["probability"] for item in predictions]
           for name in (*CONTROL_NAMES, "candidate")},
    }
    comparisons = {
        f"candidate_minus_{right}": ("candidate", right)
        for right in ("market", *CONTROL_NAMES)
    }
    groups = {
        "schedule_day": [item["row"].split_date for item in predictions],
        "observed_game_week": [offset.game_week(item["row"].game_id) for item in predictions],
    }
    result = {
        "primary_estimand": "equal-event Brier and log loss",
        "events": len(predictions), "schedule_dates": len(set(groups["schedule_day"])),
        "game_weeks": len(set(groups["observed_game_week"])),
        "schedule_day_resample": {}, "observed_game_week_cluster_sensitivity": {},
    }
    for group, labels in groups.items():
        target = (result["schedule_day_resample"] if group == "schedule_day"
                  else result["observed_game_week_cluster_sensitivity"])
        for name, (left, right) in comparisons.items():
            target[name] = {
                loss: calibration._group_delta_detail(
                    offset._loss_deltas(outcomes, arms[left], arms[right], loss), labels
                ) for loss in ("brier", "log_loss")
            }
    result["schedule_day_resample"]["unit_definition"] = (
        "complete source schedule dates; resample units then recompute pooled equal-event mean"
    )
    weeks = sorted(set(groups["observed_game_week"]))
    result["observed_game_week_cluster_sensitivity"].update({
        "unit_definition": "observed NFL game-week clusters; not all are complete weeks",
        "right_edge_partial_week": weeks[-1],
        "right_edge_partial_week_events": groups["observed_game_week"].count(weeks[-1]),
        "primary_denominator_changed": False,
    })
    return result


def _write_predictions(path: Path, predictions: Sequence[dict]) -> None:
    fields = (*ARCHIVED_FIELDS, "all_prior_decay_candidate_probability")
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in predictions:
            row = item["row"]
            writer.writerow({
                "fold": item["fold"], "game_id": row.game_id,
                "split_date": row.split_date, "game_week": offset.game_week(row.game_id),
                "event_id": row.trusted["event_id"], "market_id": row.trusted["market_id"],
                "cutoff_ms": row.trusted["cutoff_ms"],
                "outcome_available_ms": row.trusted["outcome_available_ms"],
                "outcome": row.trusted["outcome"],
                "market_probability": row.trusted["market_probability"],
                "ordinary_probability": item["ordinary"]["probability"],
                "market_only_calibration_probability": item["market_only_calibration"]["probability"],
                "archived_full_offset_probability": item["archived_full_offset"]["probability"],
                "candidate_probability": item["archived_attempt1"]["probability"],
                "recent_composite_candidate_probability": item["archived_attempt2"]["probability"],
                "recency_weighted_candidate_probability": item["archived_attempt3"]["probability"],
                "all_prior_decay_candidate_probability": item["candidate"]["probability"],
            })
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def run(
        source_root: Path, output: Path, *, expected_events: int = EXPECTED_EVENTS,
        expected_dates: int = EXPECTED_DATES, allow_test_paths: bool = False,
        generated_utc: str | None = None, archived_parent_root: Path | None = None,
        minimum_recent_rows: int = MINIMUM_RECENT_ROWS) -> dict:
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    output.mkdir(parents=True, exist_ok=False)
    phase_state = {"fit_started": False}
    scoring_started = False
    try:
        if not allow_test_paths and minimum_recent_rows != MINIMUM_RECENT_ROWS:
            raise ValueError("production minimum recent rows is frozen at 30")
        _validate_frozen_specs()
        identity = _validate_execution_identity()
        archive_root = Path(archived_parent_root or ARCHIVED_PARENT_ROOT).resolve()
        archive_binding = validate_archived_parent_artifact(
            archive_root, verify_frozen_hashes=not allow_test_paths
        )
        if not allow_test_paths:
            if base._sha256(source_root / "manifest.json") != base.EXPECTED_MANIFEST_SHA256:
                raise ValueError("frozen source manifest hash changed")
            if base._sha256(source_root / "cohort.csv") != base.EXPECTED_COHORT_SHA256:
                raise ValueError("frozen cohort hash changed")
        source_manifest = base._strict_json(source_root / "manifest.json")
        if (not isinstance(source_manifest, dict)
                or source_manifest.get("schema") != "nfl_2025_train_fresh_source_audit_v1"
                or source_manifest.get("complete") is not True
                or source_manifest.get("source_games") != expected_events
                or source_manifest.get("train_distinct_dates") != expected_dates
                or source_manifest.get("dev_final_opened") is not False
                or source_manifest.get("model_fits") != 0
                or source_manifest.get("provider_cost_usd") != "0"):
            raise ValueError("source manifest scope/completeness boundary failed")
        cohort = base._read_cohort(source_root / "cohort.csv")
        if len(cohort) != expected_events:
            raise ValueError("source denominator differs from frozen event count")
        if set((source_root / "catalog").glob("*.json")) != {
                source_root / "catalog" / f"{row['game_id']}.json" for row in cohort}:
            raise ValueError("normalized catalog population differs from cohort")
        source_file_receipts = [{
            "source_ordinal": ordinal, "game_id": item["game_id"],
            "catalog_meta_sha256": base._sha256(source_root / "catalog" / f"{item['game_id']}.json"),
            "catalog_stored_sha256": base._sha256(source_root / "catalog" / f"{item['game_id']}.raw.json.gz"),
            "trade_manifest_sha256": base._sha256(source_root / "trades" / item["game_id"] / "manifest.json"),
            "trade_window_sha256": base._sha256(source_root / "trades" / item["game_id"] / "trade_window.csv"),
        } for ordinal, item in enumerate(cohort)]
        materialized, exclusions = [], []
        for ordinal, item in enumerate(cohort):
            try:
                materialized.append(base._materialize_event(source_root, item))
            except base.EventExclusion as error:
                exclusions.append({
                    "source_ordinal": ordinal, "game_id": item["game_id"],
                    "game_date": item["game_date"], "reason": error.code,
                    "detail": str(error)[:400],
                })
        if len(materialized) + len(exclusions) != expected_events:
            raise RuntimeError("materialized plus excluded events do not reconcile")
        if not allow_test_paths:
            base.validate_exact_cohort_attrition(expected_events, len(materialized), exclusions)
            offset.validate_exact_real_exclusion(exclusions)
        materialized.sort(key=lambda row: row.key)
        materialized_hash = base._digest([list(row.key) for row in materialized])
        if not allow_test_paths and materialized_hash != EXPECTED_MATERIALIZED_KEY_SHA256:
            raise ValueError("materialized key population differs from frozen parent")
        ordinals = {item["game_id"]: ordinal for ordinal, item in enumerate(cohort)}
        staleness = offset.staleness_inventory(materialized, ordinals)
        base._atomic_json(output / "staleness_inventory.json", staleness)
        offset.require_staleness_gate(
            staleness, expected_binary_rows=194 if not allow_test_paths else len(materialized)
        )
        folds = base.chronological_date_folds(
            [item["game_date"] for item in cohort], expected_dates=expected_dates
        )
        plan = calibration._fold_plan(materialized, folds)
        if not allow_test_paths:
            counts = tuple((len(item["fit_rows"]), len(item["check_rows"])) for item in plan)
            if counts != prior.EXPECTED_REAL_FOLD_COUNTS:
                raise ValueError("fit/check event counts differ from frozen parent")
            if any(item["fit_label_unavailable_events"] for item in plan):
                raise ValueError("frozen parent expects zero unavailable fit labels")
            offset.require_expected_check_mask(
                [row for item in plan for row in item["check_rows"]],
                EXPECTED_CHECK_MASK_SHA256,
            )
        inputs = {
            "schema": "nfl_market_all_prior_decay_composite_path_train_inputs_v1",
            "source_dataset_id": source_root.name,
            "source_manifest_sha256": base._sha256(source_root / "manifest.json"),
            "cohort_sha256": base._sha256(source_root / "cohort.csv"),
            "source_events": expected_events, "source_dates": expected_dates,
            "runner_source_sha256": base._sha256(Path(__file__)),
            "execution_identity": identity, "archived_parent_binding": archive_binding,
            "all_source_file_receipts": source_file_receipts,
            "materialized_event_receipts": [row.source_receipt for row in materialized],
            "route_dev_opened": False, "sealed_final_opened": False,
            "provider_cost_usd": "0",
        }
        exclusions_doc = {
            "schema": "nfl_market_all_prior_decay_composite_path_train_exclusions_v1",
            "source_events": expected_events, "materialized_events": len(materialized),
            "excluded_events": len(exclusions),
            "reconciles_to_source_denominator": len(materialized) + len(exclusions) == expected_events,
            "exclusions": exclusions,
        }
        base._atomic_json(output / "input_receipts.json", inputs)
        base._atomic_json(output / "exclusions.json", exclusions_doc)
        lock = {
            "schema": "nfl_market_all_prior_decay_composite_path_train_pre_score_lock_v1",
            "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "problem": "test all-prior fixed-decay support for the frozen composite path trainer",
            "domain": "2025 NFL two-outcome moneyline opened Train Discovery",
            "source_manifest_sha256": inputs["source_manifest_sha256"],
            "cohort_sha256": inputs["cohort_sha256"],
            "input_receipts_sha256": base._sha256(output / "input_receipts.json"),
            "exclusions_sha256": base._sha256(output / "exclusions.json"),
            "staleness_inventory_sha256": base._sha256(output / "staleness_inventory.json"),
            "controller_provenance": {
                "proposal_path": str(CONTROLLER_PROPOSAL_PATH),
                "proposal_sha256": EXPECTED_CONTROLLER_PROPOSAL_SHA256,
                "adaptive_discovery_disclosure": (
                    "Attempt 4 was selected after reading label-dependent Attempt-3 aggregate, "
                    "fold, date, week, coefficient and information diagnostics; this is repeatedly "
                    "inspected Train Discovery"
                ),
            },
            "execution_identity": identity, "archived_parent_binding": archive_binding,
            "source_events": expected_events, "source_dates": expected_dates,
            "materialized_key_sha256": materialized_hash,
            "canonical_check_mask_sha256": EXPECTED_CHECK_MASK_SHA256 if not allow_test_paths else None,
            "decision_cutoff": "event_start_utc minus 15 minutes",
            "max_staleness_seconds": MAX_STALENESS_SECONDS,
            "folds": folds, "candidate_spec": dict(CANDIDATE_SPEC),
            "candidate_spec_sha256": base._digest(dict(CANDIDATE_SPEC)),
            "expected_real_recent_transform_cohorts": {
                str(key): dict(value) for key, value in EXPECTED_REAL_RECENT.items()
            },
            "expected_real_all_prior_fit_cohorts": {
                str(key): dict(value) for key, value in EXPECTED_REAL_ALL_PRIOR.items()
            },
            "model_fits": {"candidate": 4, "all_archived_controls": 0},
            "archive_only_controls": [
                "market", "ordinary_reference", "market_only_calibration", "full_offset",
                "MarketOrthogonalPricePath-v1", "MarketRecentCompositePath-v2",
                "MarketRecencyWeightedCompositePath-v3",
            ],
            "event_weighting": "evaluation equal-event; trainer all-prior fixed one-week half-life",
            "grouped_inference": {
                "seed": offset.BOOTSTRAP_SEED,
                "replicates": offset.BOOTSTRAP_REPLICATES,
                "per_draw_estimand": "pooled equal-event mean loss delta",
            },
            "keep_rule": (
                "all prior market/ordinary gates plus beats archived Attempt3 aggregate Brier/log "
                "by >1e-12 and Brier in >=3/4 folds"
            ),
            "route_dev_opened": False, "sealed_final_opened": False,
            "external_fetch": False, "paid_provider": False,
            "provider_cost_usd": "0", "promotion_authorized": False,
        }
        base._atomic_json(output / "pre_score_lock.json", lock)
        predictions, fold_reports = _fit_and_predict(
            plan, minimum_recent_rows=minimum_recent_rows,
            enforce_real_counts=not allow_test_paths, phase_state=phase_state,
        )
        parity = bind_archived_controls(
            predictions, fold_reports, archive_root / "predictions.csv",
            verify_frozen_hash=not allow_test_paths,
        )
        check_rows = [item["row"] for item in predictions]
        if not allow_test_paths:
            offset.require_expected_check_mask(check_rows, EXPECTED_CHECK_MASK_SHA256)
        records = {
            name: [item[name] for item in predictions]
            for name in (*CONTROL_NAMES, "candidate")
        }
        scoring_started = True
        pairwise = {}
        for right in ("market", *CONTROL_NAMES):
            pairwise[f"candidate_minus_{right}"] = recent._pair_score(
                check_rows, records["candidate"], "candidate", right,
                right=None if right == "market" else records[right],
            )
        for arm in CONTROL_NAMES:
            pairwise[f"{arm}_minus_market"] = recent._pair_score(
                check_rows, records[arm], arm, "market"
            )
        masks = {
            name: value["proper_scorer_output"]["coverage"]["complete_mask_sha256"]
            for name, value in pairwise.items()
        }
        if len(set(masks.values())) != 1:
            raise RuntimeError("pairwise proper scorers did not receive one common mask")

        def arm_from(pair: str, prefix: str) -> dict:
            score = pairwise[pair]["proper_scorer_output"]
            return {
                "brier": score["primary"][f"equal_event_{prefix}_brier"],
                "log_loss": score["primary"][f"equal_event_{prefix}_log_loss"],
                "calibration": score["calibration"][prefix],
            }

        aggregate = {
            "market": arm_from("candidate_minus_market", "market"),
            "candidate": arm_from("candidate_minus_market", "candidate"),
            **{arm: arm_from(f"{arm}_minus_market", "candidate") for arm in CONTROL_NAMES},
            "pairwise_deltas": {
                name: value["equal_event_delta"] for name, value in pairwise.items()
            },
        }
        prior_decision, prior_conditions = offset.diagnostic_keep(
            aggregate["candidate"], aggregate["market"], aggregate["ordinary"],
            [fold["market"]["brier"] - fold["candidate"]["brier"] > STRICT_WIN_TOLERANCE
             for fold in fold_reports],
            [fold["ordinary"]["brier"] - fold["candidate"]["brier"] > STRICT_WIN_TOLERANCE
             for fold in fold_reports],
        )
        incumbent_conditions = {
            "beats_attempt3_aggregate_brier": (
                aggregate["archived_attempt3"]["brier"] - aggregate["candidate"]["brier"]
                > STRICT_WIN_TOLERANCE
            ),
            "beats_attempt3_aggregate_log_loss": (
                aggregate["archived_attempt3"]["log_loss"] - aggregate["candidate"]["log_loss"]
                > STRICT_WIN_TOLERANCE
            ),
            "attempt3_fold_brier_wins_at_least_3_of_4": sum(
                fold["archived_attempt3"]["brier"] - fold["candidate"]["brier"]
                > STRICT_WIN_TOLERANCE for fold in fold_reports
            ) >= 3,
        }
        conditions = {**prior_conditions, **incumbent_conditions}
        decision = "KEEP" if prior_decision == "KEEP" and all(incumbent_conditions.values()) else "REVERT"
        branch_diagnostics = {}
        for arm in CONTROL_NAMES[1:]:
            branch_diagnostics[f"candidate_vs_{arm}"] = {
                "beats_aggregate_brier": aggregate[arm]["brier"] - aggregate["candidate"]["brier"] > STRICT_WIN_TOLERANCE,
                "beats_aggregate_log_loss": aggregate[arm]["log_loss"] - aggregate["candidate"]["log_loss"] > STRICT_WIN_TOLERANCE,
                "fold_brier_wins": [
                    fold[arm]["brier"] - fold["candidate"]["brier"] > STRICT_WIN_TOLERANCE
                    for fold in fold_reports
                ],
            }
        _write_predictions(output / "predictions.csv", predictions)
        scorecard = {
            "schema": "nfl_market_all_prior_decay_composite_path_train_scorecard_v1",
            "diagnostic_decision": decision,
            "decision_scope": "replace current best for further Discovery only",
            "keep_conditions": conditions, "branch_diagnostics": branch_diagnostics,
            "source_denominator": {
                "events": expected_events, "dates": expected_dates,
                "materialized_events": len(materialized), "excluded_events": len(exclusions),
                "check_events": len(check_rows),
                "check_dates": len({row.split_date for row in check_rows}),
                "check_game_weeks": len({offset.game_week(row.game_id) for row in check_rows}),
            },
            "arms": {
                "market": "decision-time market probability",
                "ordinary": "archived ordinary LogisticRegression reference",
                "market_only_calibration": "archived calibration control",
                "archived_full_offset": "archived full-offset control",
                "archived_attempt1": "archived MarketOrthogonalPricePath-v1",
                "archived_attempt2": "archived MarketRecentCompositePath-v2",
                "archived_attempt3": "archived MarketRecencyWeightedCompositePath-v3 incumbent",
                "candidate": "MarketAllPriorDecayCompositePath-v4",
            },
            "control_parity": parity,
            "identical_masks": {"all_arms_share_one_complete_mask": True, "mask_sha256": masks},
            "aggregate": aggregate, "folds": fold_reports,
            "pairwise_proper_scores": pairwise,
            "corrected_grouped_inference": corrected_grouped_inference(predictions),
            "incumbent_and_branch_semantics": {
                "current_best_before_run": "MarketRecencyWeightedCompositePath-v3",
                "current_best_after_run": (
                    "MarketAllPriorDecayCompositePath-v4" if decision == "KEEP"
                    else "MarketRecencyWeightedCompositePath-v3"
                ),
                "all_research_branches_retained": True,
            },
            "inference_boundary": "reused opened-Train Discovery; not independent OOS",
            "unsupported_claims": [
                "promotion or formal OOS improvement", "profitability",
                "generalization beyond 2025 NFL", "RSI self-evolution",
            ],
            "route_dev_opened": False, "sealed_final_opened": False,
            "provider_cost_usd": "0", "promotion_authorized": False,
        }
        base._atomic_json(output / "scorecard.json", scorecard)
        manifest = {
            "schema": "nfl_market_all_prior_decay_composite_path_train_manifest_v1",
            "complete": True, "status": "COMPLETE",
            "completed_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "pre_score_lock_sha256": base._sha256(output / "pre_score_lock.json"),
            "input_receipts_sha256": base._sha256(output / "input_receipts.json"),
            "exclusions_sha256": base._sha256(output / "exclusions.json"),
            "staleness_inventory_sha256": base._sha256(output / "staleness_inventory.json"),
            "predictions_sha256": base._sha256(output / "predictions.csv"),
            "scorecard_sha256": base._sha256(output / "scorecard.json"),
            "source_events": expected_events, "materialized_events": len(materialized),
            "excluded_events": len(exclusions), "check_events": len(check_rows),
            "model_fits": 4, "candidate_fits": 4, "control_refits": 0,
            "diagnostic_decision": decision,
            "route_dev_opened": False, "sealed_final_opened": False,
            "external_fetch": False, "paid_provider": False,
            "provider_cost_usd": "0", "promotion_authorized": False,
        }
        base._atomic_json(output / "manifest.json", manifest)
        return manifest
    except Exception as error:
        if output.exists() and not (output / "manifest.json").exists():
            invalid = isinstance(error, offset.InvalidDataQuality)
            failure = {
                "schema": "nfl_market_all_prior_decay_composite_path_train_failure_v1",
                "status": "INVALID_DATA_QUALITY" if invalid else "FAILED",
                "error_type": type(error).__name__, "error": str(error)[:1200],
                "fit_started": phase_state["fit_started"],
                "scoring_started": scoring_started,
                "route_dev_opened": False, "sealed_final_opened": False,
                "external_fetch": False, "paid_provider": False,
                "provider_cost_usd": "0",
            }
            if invalid:
                failure["data_quality_report"] = error.report
            base._atomic_json(output / "failure.json", failure)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.source_root, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
