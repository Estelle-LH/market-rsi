#!/usr/bin/env python3
"""Opened-Train Discovery runner for MarketRecencyWeightedCompositePath-v3.

This is a trainer-only delta from MarketRecentCompositePath-v2: the exact
three-week rows and transforms are retained, while fit NLL weights the oldest,
middle and newest weeks by 0.25, 0.50 and 1.00.  All controls are archived.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

from experiments import nfl_market_recent_composite_path_train_diagnostic as parent


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
WEEK_WEIGHTS = MappingProxyType({0: 0.25, 1: 0.50, 2: 1.00})
EXPECTED_REAL_WEIGHT_SUMS = MappingProxyType({1: 26.0, 2: 24.25, 3: 24.25, 4: 25.0})

EXPECTED_PARENT_RUNNER_SHA256 = "d005d9fe5df0c33c1eeb5aa8ba2d5e7ebbb5103c9b0e7935bb5ac3de8946c70f"
EXPECTED_PARENT_TEST_SHA256 = "4aac0a60e9e2b4bbffd9999bc1259d9c27df2b8c4b9be259d8dd22ceb3f6ca77"
CONTROLLER_PROPOSAL_PATH = (
    Path(__file__).resolve().parents[1] / "supervisor_harness"
    / "AGENT_LOG_DISCOVERY_ATTEMPT3_CONTROLLER_2026-09-29.md"
)
EXPECTED_CONTROLLER_PROPOSAL_SHA256 = "1def15625da467de6b6130dc7f7bf3adb08ae7da00ee43de9900c1d5a73283cc"
PARENT_RESULT_REVIEW_PATH = (
    Path(__file__).resolve().parents[1] / "supervisor_harness"
    / "AGENT_LOG_MARKET_RECENT_COMPOSITE_PATH_V2_RESULT_INDEPENDENT_REVIEW_2026-09-29.md"
)
EXPECTED_PARENT_RESULT_REVIEW_SHA256 = "6800cd9647508963a2eb1efa525f5489c04fd9e3c920fa2a495fba0f417d9c6d"
ARCHIVED_PARENT_ROOT = PERSISTENT_ARTIFACT_ROOT / (
    "first-real-train-diagnostic-market-recent-composite-path-20260929-01"
)
ARCHIVED_PARENT_SHA256 = MappingProxyType({
    "exclusions.json": "1ee1b77e6f1f71b4382c452916afe51d19d7edfa8b1a9844fd81e21f18d887e2",
    "input_receipts.json": "eeb0449123c55e6b0b3e7f7b314c9b5327b1404041d3dd5fb18dededdf718640",
    "manifest.json": "3434aef3a97fc54b61a6d0c762a1f80523d24f3a96c0071dd77944befef7683c",
    "pre_score_lock.json": "fc462890587cc7dc9a079acb128590a7a7ccdf5494c30be5d5136c3ee1a8ce62",
    "predictions.csv": "7691a6dbee6b7dc0949583a7a421e7a421ad7565caaf20ebf559121b1b76cca2",
    "scorecard.json": "29632c1a8879be045ffb5018067ec72c3eca70fad44f43b9b5a60060f1e992d8",
    "staleness_inventory.json": "3b545bd2542b4a4102ed0aa0f2adaed435322fc58bea06b599ebee765abea10e",
})
ARCHIVED_FIELDS = (*parent.ARCHIVED_FIELDS, "recent_composite_candidate_probability")
CANDIDATE_SPEC = MappingProxyType({
    "name": "MarketRecencyWeightedCompositePath-v3",
    "parent_representation": dict(parent.CANDIDATE_SPEC),
    "selected_week_event_weights_oldest_middle_newest": (0.25, 0.50, 1.00),
    "weight_assignment": "relative numeric rank of exact three selected week labels",
    "transform_weighting": "unweighted identical to Attempt-2",
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
EXPECTED_CANDIDATE_SPEC_SHA256 = "2f71194d76b3775739917992da6eaffe2d3535c409d3e30fc0f0ca82f9588903"


def execution_identity() -> dict:
    return {
        "parent_runner_sha256": base._sha256(Path(parent.__file__)),
        "parent_test_sha256": base._sha256(
            Path(__file__).resolve().parents[1] / "tests"
            / "test_nfl_market_recent_composite_path_train_diagnostic.py"
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
        raise RuntimeError(f"weighted candidate spec changed: {observed}")


def validate_archived_parent_artifact(root: Path, *, verify_frozen_hashes: bool) -> dict:
    root = Path(root).resolve()
    observed = {path.name for path in root.iterdir() if path.is_file()}
    if observed != set(ARCHIVED_PARENT_SHA256):
        raise ValueError("archived Attempt-2 artifact file set differs")
    hashes = {name: base._sha256(root / name) for name in sorted(observed)}
    if verify_frozen_hashes and hashes != dict(ARCHIVED_PARENT_SHA256):
        raise ValueError("archived Attempt-2 artifact hash changed")
    manifest = base._strict_json(root / "manifest.json")
    if (not isinstance(manifest, dict)
            or manifest.get("schema") != "nfl_market_recent_composite_path_train_manifest_v1"
            or manifest.get("complete") is not True
            or manifest.get("status") != "COMPLETE"
            or manifest.get("model_fits") != 4
            or manifest.get("control_refits") != 0
            or manifest.get("provider_cost_usd") != "0"
            or manifest.get("route_dev_opened") is not False
            or manifest.get("sealed_final_opened") is not False
            or manifest.get("external_fetch") is not False
            or manifest.get("paid_provider") is not False):
        raise ValueError("archived Attempt-2 manifest boundary failed")
    bindings = {
        "pre_score_lock.json": manifest.get("pre_score_lock_sha256"),
        "input_receipts.json": manifest.get("input_receipts_sha256"),
        "exclusions.json": manifest.get("exclusions_sha256"),
        "staleness_inventory.json": manifest.get("staleness_inventory_sha256"),
        "predictions.csv": manifest.get("predictions_sha256"),
        "scorecard.json": manifest.get("scorecard_sha256"),
    }
    if any(hashes[name] != value for name, value in bindings.items()):
        raise ValueError("archived Attempt-2 manifest hash binding failed")
    return {"artifact_root": str(root), "artifact_hashes": hashes}


def recency_weights(rows: Sequence[base.DiagnosticRow],
                    selected_week_labels: Sequence[str], *,
                    expected_total: float | None = None) -> tuple[np.ndarray, dict]:
    labels = tuple(selected_week_labels)
    if len(labels) != 3 or tuple(sorted(labels, key=parent._week_key)) != labels:
        parent._invalid_recent("weighted_candidate_requires_three_ordered_weeks",
                               labels=list(labels))
    mapping = {label: WEEK_WEIGHTS[index] for index, label in enumerate(labels)}
    row_labels = [offset.game_week(row.game_id) for row in rows]
    if set(row_labels) != set(labels):
        parent._invalid_recent("weighted_candidate_row_week_mismatch")
    weights = np.asarray([mapping[label] for label in row_labels], dtype=np.float64)
    if weights.shape != (len(rows),) or not np.all(np.isfinite(weights)) or np.any(weights <= 0):
        parent._invalid_recent("invalid_recency_weights")
    total = float(np.sum(weights))
    squared = float(np.sum(weights ** 2))
    if expected_total is not None and total != expected_total:
        parent._invalid_recent("exact_real_weight_sum_mismatch",
                               observed=total, expected=expected_total)
    report = {
        "week_weight_mapping": mapping,
        "per_week": [{
            "week": label,
            "events": row_labels.count(label),
            "event_weight": mapping[label],
            "weight_sum": row_labels.count(label) * mapping[label],
        } for label in labels],
        "weight_sum": total,
        "squared_weight_sum": squared,
        "kish_effective_rows": total ** 2 / squared,
        "weight_totals_by_class": {
            str(label): float(np.sum(weights[np.asarray([
                row.trusted["outcome"] == label for row in rows
            ], dtype=bool)])) for label in (0, 1)
        },
        "selected_event_weight_ledger": [{
            "ordinal": ordinal,
            "game_id": row.game_id,
            "split_date": row.split_date,
            "event_id": row.trusted["event_id"],
            "outcome": row.trusted["outcome"],
            "game_week": row_labels[ordinal],
            "event_weight": float(weights[ordinal]),
        } for ordinal, row in enumerate(rows)],
    }
    return weights, report


def weighted_objective_gradient(parameter: object, z_composite: object,
                                outcomes: object, market_logits: object,
                                weights: object) -> tuple[float, np.ndarray]:
    coefficient = np.asarray(parameter, dtype=np.float64)
    z = np.asarray(z_composite, dtype=np.float64)
    labels = np.asarray(outcomes, dtype=np.float64)
    logits = np.asarray(market_logits, dtype=np.float64)
    event_weights = np.asarray(weights, dtype=np.float64)
    if coefficient.shape != (1,) or not np.all(np.isfinite(coefficient)):
        raise ValueError("coefficient must be one finite value")
    if (z.ndim != 1 or not len(z) or labels.shape != z.shape
            or logits.shape != z.shape or event_weights.shape != z.shape
            or not np.all(np.isfinite(z)) or not np.all(np.isfinite(labels))
            or not np.all(np.isfinite(logits)) or not np.all(np.isfinite(event_weights))
            or not np.all(np.isin(labels, (0, 1))) or np.any(event_weights <= 0)):
        raise ValueError("weighted objective inputs must be aligned finite rows")
    eta = logits + coefficient[0] * z
    probabilities = expit(eta)
    weight_sum = float(np.sum(event_weights))
    losses = np.logaddexp(0.0, eta) - labels * eta
    objective = float(np.sum(event_weights * losses) / weight_sum)
    objective += 0.5 * float(coefficient[0] ** 2)
    gradient = np.asarray([
        float(np.sum(event_weights * z * (probabilities - labels)) / weight_sum)
        + float(coefficient[0])
    ])
    if not math.isfinite(objective) or not np.all(np.isfinite(gradient)):
        raise FloatingPointError("weighted objective or gradient is nonfinite")
    return objective, gradient


def fit_weighted_composite(z_composite: object, outcomes: object,
                           market_logits: object, weights: object) -> tuple[np.ndarray, dict]:
    z = np.asarray(z_composite, dtype=np.float64)
    labels = np.asarray(outcomes, dtype=np.float64)
    logits = np.asarray(market_logits, dtype=np.float64)
    event_weights = np.asarray(weights, dtype=np.float64)

    def objective(value: np.ndarray) -> tuple[float, np.ndarray]:
        return weighted_objective_gradient(value, z, labels, logits, event_weights)

    result = minimize(
        objective, np.zeros(1, dtype=np.float64), method="L-BFGS-B", jac=True,
        options={"maxiter": 1000, "gtol": 1e-8, "ftol": 1e-12},
    )
    parameter = np.asarray(result.x, dtype=np.float64)
    final_objective, final_gradient = objective(parameter)
    grad_inf = float(np.max(np.abs(final_gradient)))
    if (not bool(result.success) or not math.isfinite(final_objective)
            or not np.all(np.isfinite(parameter)) or grad_inf > 1e-6):
        raise RuntimeError(
            "weighted optimizer failed frozen convergence checks: "
            f"success={result.success}, objective={final_objective}, grad_inf={grad_inf}"
        )
    return parameter, {
        "success": True, "status": int(result.status),
        "message": str(result.message)[:300], "iterations": int(result.nit),
        "function_evaluations": int(result.nfev), "objective": final_objective,
        "gradient_infinity_norm": grad_inf,
        "parameters": [float(parameter[0])],
    }


def _fit_and_predict(plan: Sequence[dict], *, minimum_recent_rows: int,
                     enforce_real_counts: bool,
                     phase_state: dict[str, bool]) -> tuple[list[dict], list[dict]]:
    predictions, reports = [], []
    for fold in plan:
        expected = EXPECTED_REAL_RECENT[fold["fold"]] if enforce_real_counts else None
        selection = parent.select_recent_candidate_rows(
            fold["fit_rows"], fold["check_rows"], minimum_rows=minimum_recent_rows,
            expected=expected,
        )
        selected, older = selection["selected_rows"], selection["older_rows"]
        transformed = parent.fit_recent_composite_transform(
            selected, older, fold["check_rows"]
        )
        selected_diagnostics = parent.information_diagnostics(
            transformed["selected"], selected
        )
        expected_sum = EXPECTED_REAL_WEIGHT_SUMS[fold["fold"]] if enforce_real_counts else None
        weights, weight_report = recency_weights(
            selected, selection["report"]["selected_week_labels"],
            expected_total=expected_sum,
        )
        labels = np.asarray([row.trusted["outcome"] for row in selected])
        market = np.asarray([row.trusted["market_probability"] for row in selected])
        z = transformed["selected"]["z_composite"]
        weighted_moment = float(
            np.sum(weights * z * (labels - market)) / np.sum(weights)
        )
        unweighted_moment = float(np.mean(z * (labels - market)))
        gradient_at_zero = float(
            weighted_objective_gradient(
                np.zeros(1), z, labels, transformed["selected"]["logits"], weights
            )[1][0]
        )
        if not math.isclose(gradient_at_zero, -weighted_moment,
                            rel_tol=0.0, abs_tol=1e-15):
            raise RuntimeError("gradient at zero is not negative weighted moment")
        weight_report["weighted_mean_z_times_y_minus_market"] = weighted_moment
        weight_report["unweighted_mean_z_times_y_minus_market"] = unweighted_moment
        weight_report["gradient_at_zero"] = gradient_at_zero
        weight_report["coefficient_descent_direction"] = -gradient_at_zero
        weight_report["gradient_at_zero_equals_negative_weighted_moment"] = True
        selected_weeks = selection["report"]["selected_week_labels"]
        row_weeks = [offset.game_week(row.game_id) for row in selected]
        weight_report["signed_moments_by_week"] = []
        for week in selected_weeks:
            mask = np.asarray([label == week for label in row_weeks], dtype=bool)
            residual_products = z[mask] * (labels[mask] - market[mask])
            week_weights = weights[mask]
            weight_report["signed_moments_by_week"].append({
                "week": week,
                "events": int(np.sum(mask)),
                "unweighted_mean_z_times_y_minus_market": float(
                    np.mean(residual_products)
                ),
                "weighted_mean_z_times_y_minus_market": float(
                    np.sum(week_weights * residual_products) / np.sum(week_weights)
                ),
            })
        phase_state["fit_started"] = True
        parameter, optimizer = fit_weighted_composite(
            z, labels, transformed["selected"]["logits"], weights
        )
        candidate_values = parent.recent_probabilities(
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
                "selected_recent_fit": parent._breadth(selected),
                "older_eligible_fit": parent._breadth(older),
                "ineligible_same_or_later_week_fit": parent._breadth(
                    selection["ineligible_same_or_later_week_rows"]
                ),
                "check": parent._breadth(fold["check_rows"]),
            },
            "transform_parameters": transformed["parameters"],
            "selected_recent_fit_information": selected_diagnostics,
            "recency_weighting": weight_report,
            "older_fit_information": parent.information_diagnostics(
                transformed["older"], older
            ),
            "check_information": parent.information_diagnostics(
                transformed["check"], fold["check_rows"]
            ),
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


def bind_archived_controls(predictions: Sequence[dict], fold_reports: Sequence[dict],
                           predictions_csv: Path, *, verify_frozen_hash: bool) -> dict:
    if (verify_frozen_hash and base._sha256(predictions_csv)
            != ARCHIVED_PARENT_SHA256["predictions.csv"]):
        raise ValueError("archived Attempt-2 predictions hash changed")
    with Path(predictions_csv).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != ARCHIVED_FIELDS:
            raise ValueError("archived Attempt-2 prediction schema changed")
        archived = list(reader)
    if len(archived) != len(predictions):
        raise ValueError("archived Attempt-2 row count differs")
    arm_columns = {
        "ordinary": "ordinary_probability",
        "market_only_calibration": "market_only_calibration_probability",
        "archived_full_offset": "archived_full_offset_probability",
        "archived_attempt1": "candidate_probability",
        "archived_attempt2": "recent_composite_candidate_probability",
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
            raise ValueError("archived Attempt-2 identity/order/outcome differs")
        if row.trusted["market_probability"] != float(control["market_probability"]):
            raise ValueError("archived Attempt-2 market probability differs")
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
        "control_probability_source": "immutable archived Attempt-2 predictions",
    }


def corrected_grouped_inference(predictions: Sequence[dict]) -> dict:
    outcomes = [item["row"].trusted["outcome"] for item in predictions]
    arm_names = ("ordinary", "market_only_calibration", "archived_full_offset",
                 "archived_attempt1", "archived_attempt2", "candidate")
    arms = {"market": [item["row"].trusted["market_probability"] for item in predictions],
            **{name: [item[name]["probability"] for item in predictions]
               for name in arm_names}}
    comparisons = {f"candidate_minus_{right}": ("candidate", right) for right in
                   ("market", *arm_names[:-1])}
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
    fields = (*ARCHIVED_FIELDS, "recency_weighted_candidate_probability")
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
                "recency_weighted_candidate_probability": item["candidate"]["probability"],
            })
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def run(source_root: Path, output: Path, *, expected_events: int = EXPECTED_EVENTS,
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
                exclusions.append({"source_ordinal": ordinal, "game_id": item["game_id"],
                                   "game_date": item["game_date"], "reason": error.code,
                                   "detail": str(error)[:400]})
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
            "schema": "nfl_market_recency_weighted_composite_path_train_inputs_v1",
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
            "schema": "nfl_market_recency_weighted_composite_path_train_exclusions_v1",
            "source_events": expected_events, "materialized_events": len(materialized),
            "excluded_events": len(exclusions),
            "reconciles_to_source_denominator": len(materialized) + len(exclusions) == expected_events,
            "exclusions": exclusions,
        }
        base._atomic_json(output / "input_receipts.json", inputs)
        base._atomic_json(output / "exclusions.json", exclusions_doc)
        lock = {
            "schema": "nfl_market_recency_weighted_composite_path_train_pre_score_lock_v1",
            "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "problem": "test fixed recency weighting of the frozen three-week composite path trainer",
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
                    "Attempt-3 weighting was selected after reading label-dependent Attempt-2 "
                    "fold/week/date diagnostics; this is repeatedly inspected Train Discovery"
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
            "expected_real_recent_cohorts": {str(key): dict(value) for key, value in EXPECTED_REAL_RECENT.items()},
            "expected_real_weight_sums": {str(key): value for key, value in EXPECTED_REAL_WEIGHT_SUMS.items()},
            "model_fits": {"candidate": 4, "all_archived_controls": 0},
            "archive_only_controls": ["market", "ordinary_reference", "market_only_calibration",
                                      "full_offset", "MarketOrthogonalPricePath-v1",
                                      "MarketRecentCompositePath-v2"],
            "event_weighting": "evaluation equal-event; trainer fixed recency event weights",
            "grouped_inference": {"seed": offset.BOOTSTRAP_SEED,
                                  "replicates": offset.BOOTSTRAP_REPLICATES,
                                  "per_draw_estimand": "pooled equal-event mean loss delta"},
            "keep_rule": "candidate beats market and ordinary aggregate Brier/log by >1e-12 and Brier in >=3/4 folds against each",
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
        control_names = ("ordinary", "market_only_calibration", "archived_full_offset",
                         "archived_attempt1", "archived_attempt2")
        records = {name: [item[name] for item in predictions]
                   for name in (*control_names, "candidate")}
        scoring_started = True
        pairwise = {}
        for right in ("market", *control_names):
            pairwise[f"candidate_minus_{right}"] = parent._pair_score(
                check_rows, records["candidate"], "candidate", right,
                right=None if right == "market" else records[right],
            )
        for arm in control_names:
            pairwise[f"{arm}_minus_market"] = parent._pair_score(
                check_rows, records[arm], arm, "market"
            )
        masks = {name: value["proper_scorer_output"]["coverage"]["complete_mask_sha256"]
                 for name, value in pairwise.items()}
        if len(set(masks.values())) != 1:
            raise RuntimeError("pairwise proper scorers did not receive one common mask")

        def arm_from(pair: str, prefix: str) -> dict:
            score = pairwise[pair]["proper_scorer_output"]
            return {"brier": score["primary"][f"equal_event_{prefix}_brier"],
                    "log_loss": score["primary"][f"equal_event_{prefix}_log_loss"],
                    "calibration": score["calibration"][prefix]}

        aggregate = {
            "market": arm_from("candidate_minus_market", "market"),
            "candidate": arm_from("candidate_minus_market", "candidate"),
            **{arm: arm_from(f"{arm}_minus_market", "candidate") for arm in control_names},
            "pairwise_deltas": {name: value["equal_event_delta"] for name, value in pairwise.items()},
        }
        decision, conditions = offset.diagnostic_keep(
            aggregate["candidate"], aggregate["market"], aggregate["ordinary"],
            [fold["market"]["brier"] - fold["candidate"]["brier"] > STRICT_WIN_TOLERANCE
             for fold in fold_reports],
            [fold["ordinary"]["brier"] - fold["candidate"]["brier"] > STRICT_WIN_TOLERANCE
             for fold in fold_reports],
        )
        branch_diagnostics = {}
        for arm in ("market_only_calibration", "archived_attempt1", "archived_attempt2"):
            branch_diagnostics[f"candidate_vs_{arm}"] = {
                "beats_aggregate_brier": aggregate[arm]["brier"] - aggregate["candidate"]["brier"] > STRICT_WIN_TOLERANCE,
                "beats_aggregate_log_loss": aggregate[arm]["log_loss"] - aggregate["candidate"]["log_loss"] > STRICT_WIN_TOLERANCE,
                "fold_brier_wins": [fold[arm]["brier"] - fold["candidate"]["brier"] > STRICT_WIN_TOLERANCE
                                    for fold in fold_reports],
            }
        _write_predictions(output / "predictions.csv", predictions)
        scorecard = {
            "schema": "nfl_market_recency_weighted_composite_path_train_scorecard_v1",
            "diagnostic_decision": decision,
            "decision_scope": "replace current best for further Discovery only",
            "keep_conditions": conditions, "branch_diagnostics": branch_diagnostics,
            "source_denominator": {"events": expected_events, "dates": expected_dates,
                                   "materialized_events": len(materialized),
                                   "excluded_events": len(exclusions),
                                   "check_events": len(check_rows),
                                   "check_dates": len({row.split_date for row in check_rows}),
                                   "check_game_weeks": len({offset.game_week(row.game_id) for row in check_rows})},
            "arms": {"market": "decision-time market probability",
                     "ordinary": "archived ordinary LogisticRegression reference",
                     "market_only_calibration": "archived calibration control",
                     "archived_full_offset": "archived full-offset control",
                     "archived_attempt1": "archived MarketOrthogonalPricePath-v1",
                     "archived_attempt2": "archived MarketRecentCompositePath-v2",
                     "candidate": "MarketRecencyWeightedCompositePath-v3"},
            "control_parity": parity,
            "identical_masks": {"all_arms_share_one_complete_mask": True, "mask_sha256": masks},
            "aggregate": aggregate, "folds": fold_reports,
            "pairwise_proper_scores": pairwise,
            "corrected_grouped_inference": corrected_grouped_inference(predictions),
            "incumbent_and_branch_semantics": {
                "current_best_before_run": "decision-time market probability",
                "current_best_after_run": "MarketRecencyWeightedCompositePath-v3" if decision == "KEEP" else "decision-time market probability",
                "all_research_branches_retained": True,
            },
            "inference_boundary": "reused opened-Train Discovery; not independent OOS",
            "unsupported_claims": ["promotion or formal OOS improvement", "profitability",
                                   "generalization beyond 2025 NFL", "RSI self-evolution"],
            "route_dev_opened": False, "sealed_final_opened": False,
            "provider_cost_usd": "0", "promotion_authorized": False,
        }
        base._atomic_json(output / "scorecard.json", scorecard)
        manifest = {
            "schema": "nfl_market_recency_weighted_composite_path_train_manifest_v1",
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
                "schema": "nfl_market_recency_weighted_composite_path_train_failure_v1",
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
