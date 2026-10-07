#!/usr/bin/env python3
"""Train-only diagnostic for MarketOnlyRidgeCalibration-v1.

The fitted candidate sees only the decision-time market probability/logit. It
reuses the reviewed offset solver and all data/evaluation contracts, while the
completed full-offset predictions are an immutable archived comparison arm.
No network/provider client or protected Dev/Final path is present.
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
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from experiments import nfl_market_offset_ridge_train_diagnostic as offset


base = offset.base
SOURCE_ROOT = offset.SOURCE_ROOT
PERSISTENT_ARTIFACT_ROOT = offset.PERSISTENT_ARTIFACT_ROOT
EXPECTED_EVENTS = offset.EXPECTED_EVENTS
EXPECTED_DATES = offset.EXPECTED_DATES
EXPECTED_REAL_FOLD_COUNTS = offset.EXPECTED_REAL_FOLD_COUNTS
EXPECTED_MATERIALIZED_KEY_SHA256 = offset.EXPECTED_MATERIALIZED_KEY_SHA256
EXPECTED_CHECK_MASK_SHA256 = offset.EXPECTED_CHECK_MASK_SHA256
MAX_STALENESS_SECONDS = offset.MAX_STALENESS_SECONDS
STRICT_WIN_TOLERANCE = offset.STRICT_WIN_TOLERANCE
BOOTSTRAP_SEED = offset.BOOTSTRAP_SEED
BOOTSTRAP_REPLICATES = offset.BOOTSTRAP_REPLICATES

EXPECTED_OFFSET_RUNNER_SHA256 = (
    "6b788cf2070cc98ae8aca03d825d7f84df8f14beb1e08ad9ec88117f294b974f"
)
EXPECTED_OFFSET_TEST_SHA256 = (
    "409fd88d93c59b5d0bb25a1765471ad9249c0a5872cc77d31e69922a77fd0f41"
)
CONTROLLER_PROPOSAL_PATH = (
    Path(__file__).resolve().parents[1]
    / "supervisor_harness"
    / "AGENT_LOG_MARKET_CALIBRATION_NEXT_CONTROLLER_2026-09-29.md"
)
EXPECTED_CONTROLLER_PROPOSAL_SHA256 = (
    "cd40d3e9dababfd0da1548c4ea61e505e12fa6de2c1af0003f4f787179bf5622"
)
ARCHIVED_OFFSET_ROOT = PERSISTENT_ARTIFACT_ROOT / (
    "first-real-train-diagnostic-market-offset-ridge-20260929-02"
)
ARCHIVED_OFFSET_SHA256 = MappingProxyType({
    "exclusions.json": (
        "2d6d6327a59f77ac20b945fe7eece2c982e16da671aabf8fc96f48a4573f72a9"
    ),
    "input_receipts.json": (
        "79a0d53c9bd1b78a3e4059cd2aa7e6c9f7100eef1a40a05877e10d5a6ce82cd9"
    ),
    "manifest.json": (
        "2296835ec561858383750cba8d81124daf479de1caa288908d98503a7b93acc6"
    ),
    "pre_score_lock.json": (
        "264341f66c382001c86a01ab45835b03780b06e926d79176b141d6c86d3492a1"
    ),
    "predictions.csv": (
        "d917a1980bc0b4621ee9ab0cdc6672b47e58cbea0ae4ed335c952d40dd51288c"
    ),
    "scorecard.json": (
        "276423d4cfe97ca1198f6f95a420036bf53b7f756bdd021d691951bc4b367907"
    ),
    "staleness_inventory.json": (
        "3b545bd2542b4a4102ed0aa0f2adaed435322fc58bea06b599ebee765abea10e"
    ),
})
ORIGINAL_PARENT_PREDICTIONS_SHA256 = (
    "f91647a2a5b84836bd717ce2d0c6fd404bc1f4a759342a8b8d40fc6e576f37c1"
)
CALIBRATION_SPEC = MappingProxyType({
    "name": "MarketOnlyRidgeCalibration-v1",
    "prediction_time_inputs": (
        "market_probability_and_derived_unstandardized_market_logit_only"
    ),
    "offset": "unstandardized_market_logit_coefficient_1",
    "residual_inputs": "one_fold_standardized_market_logit_plus_intercept",
    "objective": (
        "mean_bernoulli_nll_plus_0.5_lambda_times_squared_l2_all_2_parameters"
    ),
    "lambda": 1.0,
    "penalize_intercept": True,
    "initial_parameters": "all_zero",
    "optimizer": (
        "reuse_MarketOffsetRidgeLogistic-v1_scipy.optimize.minimize_L-BFGS-B"
    ),
    "jac": "analytic",
    "maxiter": 1000,
    "gtol": 1e-8,
    "ftol": 1e-12,
    "dtype": "float64",
    "probability_policy": "existing_reject_outside_1e-6_to_1_minus_1e-6",
    "hyperparameter_search": False,
})
EXPECTED_CALIBRATION_SPEC_SHA256 = (
    "dffb3552ff1b2725beda1d0bd724ecd756291983ad12e27bffd02fb549dbe2ad"
)
ARCHIVED_FIELDS = (
    "fold", "game_id", "split_date", "game_week", "event_id", "market_id",
    "cutoff_ms", "outcome_available_ms", "outcome", "market_probability",
    "ordinary_probability", "candidate_probability",
)


def _validate_frozen_specs() -> None:
    if base._digest(dict(CALIBRATION_SPEC)) != EXPECTED_CALIBRATION_SPEC_SHA256:
        raise RuntimeError("calibration spec digest changed")
    offset._validate_frozen_specs()


def execution_identity() -> dict:
    dependency = offset._validate_execution_identity()
    return {
        "offset_runner_sha256": base._sha256(Path(offset.__file__)),
        "offset_test_sha256": base._sha256(
            Path(__file__).resolve().parents[1]
            / "tests"
            / "test_nfl_market_offset_ridge_train_diagnostic.py"
        ),
        "controller_proposal_path": str(CONTROLLER_PROPOSAL_PATH),
        "controller_proposal_sha256": base._sha256(CONTROLLER_PROPOSAL_PATH),
        "runtime_and_deeper_dependencies": dependency,
    }


def _validate_execution_identity() -> dict:
    identity = execution_identity()
    if identity["offset_runner_sha256"] != EXPECTED_OFFSET_RUNNER_SHA256:
        raise RuntimeError("frozen offset runner hash changed")
    if identity["offset_test_sha256"] != EXPECTED_OFFSET_TEST_SHA256:
        raise RuntimeError("frozen offset tests hash changed")
    if identity["controller_proposal_sha256"] != EXPECTED_CONTROLLER_PROPOSAL_SHA256:
        raise RuntimeError("calibration Controller proposal hash changed")
    return identity


def validate_archived_offset_artifact(root: Path, *, verify_frozen_hashes: bool) -> dict:
    root = Path(root).resolve()
    observed_files = {path.name for path in root.iterdir() if path.is_file()}
    expected_files = set(ARCHIVED_OFFSET_SHA256)
    if observed_files != expected_files:
        raise ValueError("archived full-offset artifact file set differs")
    hashes = {name: base._sha256(root / name) for name in sorted(expected_files)}
    if verify_frozen_hashes and hashes != dict(ARCHIVED_OFFSET_SHA256):
        raise ValueError("archived full-offset artifact hash changed")
    manifest = base._strict_json(root / "manifest.json")
    if (not isinstance(manifest, dict)
            or manifest.get("schema") != "nfl_market_offset_ridge_train_manifest_v1"
            or manifest.get("complete") is not True
            or manifest.get("status") != "COMPLETE"
            or manifest.get("diagnostic_decision") not in {"KEEP", "REVERT"}
            or manifest.get("provider_cost_usd") != "0"
            or manifest.get("route_dev_opened") is not False
            or manifest.get("sealed_final_opened") is not False
            or manifest.get("external_fetch") is not False
            or manifest.get("paid_provider") is not False):
        raise ValueError("archived full-offset manifest boundary failed")
    manifest_bindings = {
        "pre_score_lock.json": manifest.get("pre_score_lock_sha256"),
        "input_receipts.json": manifest.get("input_receipts_sha256"),
        "exclusions.json": manifest.get("exclusions_sha256"),
        "staleness_inventory.json": manifest.get("staleness_inventory_sha256"),
        "predictions.csv": manifest.get("predictions_sha256"),
        "scorecard.json": manifest.get("scorecard_sha256"),
    }
    if any(hashes[name] != value for name, value in manifest_bindings.items()):
        raise ValueError("archived full-offset manifest hash binding failed")
    scorecard = base._strict_json(root / "scorecard.json")
    parity = scorecard.get("control_parity") if isinstance(scorecard, dict) else None
    if (not isinstance(parity, dict)
            or parity.get("identity_order_mask_exact") is not True
            or parity.get("market_probability_exact") is not True
            or parity.get("maximum_ordinary_absolute_difference", math.inf) > 1e-10):
        raise ValueError("archived full-offset control parity is invalid")
    if verify_frozen_hashes and parity.get(
            "parent_predictions_sha256") != ORIGINAL_PARENT_PREDICTIONS_SHA256:
        raise ValueError("archived full-offset original-parent binding changed")
    return {
        "artifact_root": str(root),
        "artifact_hashes": hashes,
        "manifest_decision": manifest["diagnostic_decision"],
        "original_parent_control_parity": parity,
    }


def _fold_plan(rows: Sequence[base.DiagnosticRow], folds: Sequence[dict]) -> list[dict]:
    by_date: dict[str, list[base.DiagnosticRow]] = {}
    for row in rows:
        by_date.setdefault(row.split_date, []).append(row)
    plan = []
    for fold in folds:
        check_rows = sorted(
            [row for date in fold["check_dates"] for row in by_date.get(date, [])],
            key=lambda row: row.key,
        )
        if not check_rows:
            raise ValueError(f"fold {fold['fold']} has no eligible check rows")
        first_check_cutoff = min(row.trusted["cutoff_ms"] for row in check_rows)
        fit_candidates = [
            row for date in fold["fit_dates"] for row in by_date.get(date, [])
        ]
        fit_rows = sorted(
            [row for row in fit_candidates
             if row.trusted["outcome_available_ms"] < first_check_cutoff],
            key=lambda row: row.key,
        )
        unavailable = sorted(
            row.game_id for row in fit_candidates
            if row.trusted["outcome_available_ms"] >= first_check_cutoff
        )
        if not fit_rows or len({row.trusted["outcome"] for row in fit_rows}) != 2:
            raise ValueError(f"fold {fold['fold']} fit rows lack both outcome classes")
        offset.validate_train_evaluation_rows(
            [row.trusted for row in fit_rows], [row.trusted for row in check_rows]
        )
        plan.append({
            "fold": fold["fold"],
            "fit_dates": fold["fit_dates"],
            "check_dates": fold["check_dates"],
            "fit_rows": fit_rows,
            "check_rows": check_rows,
            "fit_label_unavailable_events": unavailable,
        })
    keys = [row.key for item in plan for row in item["check_rows"]]
    if len(keys) != len(set(keys)):
        raise ValueError("an event appears in multiple check folds")
    return plan


def _market_logits(rows: Sequence[base.DiagnosticRow]) -> np.ndarray:
    probabilities = np.asarray(
        [row.trusted["market_probability"] for row in rows], dtype=np.float64
    )
    values = np.log(probabilities / (1.0 - probabilities))
    feature_values = np.asarray([row.features[0] for row in rows], dtype=np.float64)
    if not np.allclose(values, feature_values, rtol=0.0, atol=1e-12):
        raise RuntimeError("market-logit feature differs from market probability")
    return values


def _fit_fold_models(fit_rows: Sequence[base.DiagnosticRow],
                     check_rows: Sequence[base.DiagnosticRow]) -> dict:
    x_fit = np.asarray([row.features for row in fit_rows], dtype=np.float64)
    x_check = np.asarray([row.features for row in check_rows], dtype=np.float64)
    y_fit = np.asarray([row.trusted["outcome"] for row in fit_rows], dtype=np.int64)
    fit_logits = _market_logits(fit_rows)
    check_logits = _market_logits(check_rows)

    full_scaler = StandardScaler()
    standardized_fit = full_scaler.fit_transform(x_fit)
    standardized_check = full_scaler.transform(x_check)
    one_scaler = StandardScaler()
    one_fit = one_scaler.fit_transform(fit_logits.reshape(-1, 1))
    one_check = one_scaler.transform(check_logits.reshape(-1, 1))
    mean_delta = abs(float(one_scaler.mean_[0]) - float(full_scaler.mean_[0]))
    scale_delta = abs(float(one_scaler.scale_[0]) - float(full_scaler.scale_[0]))
    if mean_delta > 1e-12 or scale_delta > 1e-12:
        raise RuntimeError("one-column scaler differs from full-scaler column zero")

    ordinary = LogisticRegression(
        C=1.0, solver="lbfgs", max_iter=500, random_state=23
    )
    ordinary.fit(standardized_fit, y_fit)
    parameters, optimizer = offset.fit_offset_ridge(one_fit, y_fit, fit_logits)
    ordinary_values = np.asarray(
        ordinary.predict_proba(standardized_check)[:, 1], dtype=np.float64
    )
    calibration_values = offset.offset_probabilities(
        parameters, one_check, check_logits
    )
    b, w = (float(value) for value in parameters)
    mu, scale = float(one_scaler.mean_[0]), float(one_scaler.scale_[0])
    return {
        "ordinary_values": ordinary_values,
        "calibration_values": calibration_values,
        "optimizer": optimizer,
        "calibration_parameters": {
            "b": b,
            "w": w,
            "mu": mu,
            "scale": scale,
            "equivalent_affine_logit_intercept": b - w * mu / scale,
            "equivalent_affine_logit_slope": 1.0 + w / scale,
            "single_vs_full_scaler_mean_absolute_difference": mean_delta,
            "single_vs_full_scaler_scale_absolute_difference": scale_delta,
        },
    }


def _fit_and_predict(plan: Sequence[dict]) -> tuple[list[dict], list[dict]]:
    predictions = []
    reports = []
    for fold in plan:
        result = _fit_fold_models(fold["fit_rows"], fold["check_rows"])
        check_rows = fold["check_rows"]
        ordinary = base._prediction_records(check_rows, result["ordinary_values"])
        calibration = base._prediction_records(
            check_rows, result["calibration_values"]
        )
        outcomes = [row.trusted["outcome"] for row in check_rows]
        market_values = [row.trusted["market_probability"] for row in check_rows]
        market_metrics = base._simple_metrics(outcomes, market_values)
        ordinary_metrics = base._simple_metrics(
            outcomes, [row["probability"] for row in ordinary]
        )
        calibration_metrics = base._simple_metrics(
            outcomes, [row["probability"] for row in calibration]
        )
        reports.append({
            "fold": fold["fold"],
            "fit_dates": fold["fit_dates"],
            "check_dates": fold["check_dates"],
            "fit_events": len(fold["fit_rows"]),
            "check_events": len(check_rows),
            "fit_label_unavailable_events": fold["fit_label_unavailable_events"],
            "calibration_prediction_time_inputs": ["market_probability", "market_logit"],
            "unused_residual_feature_count": 16,
            "market": market_metrics,
            "ordinary": ordinary_metrics,
            "market_only_calibration": calibration_metrics,
            "market_only_calibration_minus_market_brier": (
                calibration_metrics["brier"] - market_metrics["brier"]
            ),
            "market_only_calibration_minus_market_log_loss": (
                calibration_metrics["log_loss"] - market_metrics["log_loss"]
            ),
            "market_only_calibration_minus_ordinary_brier": (
                calibration_metrics["brier"] - ordinary_metrics["brier"]
            ),
            "market_only_calibration_minus_ordinary_log_loss": (
                calibration_metrics["log_loss"] - ordinary_metrics["log_loss"]
            ),
            "optimizer": result["optimizer"],
            "calibration_parameters": result["calibration_parameters"],
        })
        for row, ordinary_record, calibration_record in zip(
                check_rows, ordinary, calibration, strict=True):
            predictions.append({
                "fold": fold["fold"],
                "row": row,
                "ordinary": ordinary_record,
                "market_only_calibration": calibration_record,
            })
    return predictions, reports


def bind_archived_full_offset(predictions: Sequence[dict], fold_reports: Sequence[dict],
                              predictions_csv: Path,
                              *, verify_frozen_hash: bool) -> dict:
    predictions_csv = Path(predictions_csv)
    if (verify_frozen_hash
            and base._sha256(predictions_csv)
            != ARCHIVED_OFFSET_SHA256["predictions.csv"]):
        raise ValueError("archived full-offset predictions hash changed")
    with predictions_csv.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != ARCHIVED_FIELDS:
            raise ValueError("archived full-offset prediction schema changed")
        archived = list(reader)
    if len(archived) != len(predictions):
        raise ValueError("archived full-offset row count differs")
    max_ordinary_delta = 0.0
    for item, control in zip(predictions, archived, strict=True):
        row = item["row"]
        actual_identity = (
            str(item["fold"]), row.game_id, row.split_date,
            offset.game_week(row.game_id), row.trusted["event_id"],
            row.trusted["market_id"], str(row.trusted["cutoff_ms"]),
            str(row.trusted["outcome_available_ms"]), str(row.trusted["outcome"]),
        )
        expected_identity = tuple(control[name] for name in ARCHIVED_FIELDS[:9])
        if actual_identity != expected_identity:
            raise ValueError("archived full-offset identity/order/outcome differs")
        if row.trusted["market_probability"] != float(control["market_probability"]):
            raise ValueError("archived full-offset market probability differs")
        ordinary_delta = abs(
            item["ordinary"]["probability"] - float(control["ordinary_probability"])
        )
        max_ordinary_delta = max(max_ordinary_delta, ordinary_delta)
        if ordinary_delta > 1e-10:
            raise ValueError("ordinary probability differs from archived control by >1e-10")
        item["archived_full_offset"] = base._prediction_records(
            [row], [float(control["candidate_probability"])]
        )[0]
    for report in fold_reports:
        items = [item for item in predictions if item["fold"] == report["fold"]]
        outcomes = [item["row"].trusted["outcome"] for item in items]
        archived_metrics = base._simple_metrics(
            outcomes,
            [item["archived_full_offset"]["probability"] for item in items],
        )
        report["archived_full_offset"] = archived_metrics
        report["archived_full_offset_minus_market_brier"] = (
            archived_metrics["brier"] - report["market"]["brier"]
        )
        report["archived_full_offset_minus_market_log_loss"] = (
            archived_metrics["log_loss"] - report["market"]["log_loss"]
        )
        report["archived_full_offset_minus_ordinary_brier"] = (
            archived_metrics["brier"] - report["ordinary"]["brier"]
        )
        report["archived_full_offset_minus_ordinary_log_loss"] = (
            archived_metrics["log_loss"] - report["ordinary"]["log_loss"]
        )
        report["archived_full_offset_minus_market_only_calibration_brier"] = (
            archived_metrics["brier"] - report["market_only_calibration"]["brier"]
        )
        report["archived_full_offset_minus_market_only_calibration_log_loss"] = (
            archived_metrics["log_loss"]
            - report["market_only_calibration"]["log_loss"]
        )
    return {
        "archived_predictions_sha256": base._sha256(predictions_csv),
        "rows": len(predictions),
        "identity_order_outcomes_exact": True,
        "market_probability_exact": True,
        "ordinary_probability_tolerance": 1e-10,
        "maximum_ordinary_absolute_difference": max_ordinary_delta,
        "archived_full_offset_refit": False,
    }


def _pair_score(rows: Sequence[base.DiagnosticRow], left: Sequence[dict],
                left_name: str, right_name: str,
                *, right: Sequence[dict] | None = None) -> dict:
    score = base._score(list(rows), list(left), reference=list(right) if right else None)
    primary = score["primary"]
    return {
        "left_arm": left_name,
        "right_arm": right_name,
        "delta_convention": f"{left_name}_minus_{right_name}; negative loss is better",
        "equal_event_delta": {
            "brier": primary["equal_event_candidate_minus_market_brier"],
            "log_loss": primary["equal_event_candidate_minus_market_log_loss"],
        },
        "proper_scorer_output": score,
    }


def _group_delta_detail(deltas: Sequence[float], labels: Sequence[str]) -> dict:
    report = offset.cluster_resample_equal_event_delta(deltas, labels)
    records = []
    for unit in sorted(set(labels)):
        values = [
            float(value) for value, label in zip(deltas, labels, strict=True)
            if label == unit
        ]
        records.append({
            "unit": unit,
            "events": len(values),
            "delta_sum": math.fsum(values),
            "delta_mean": math.fsum(values) / len(values),
        })
    report["per_unit_event_delta_records"] = records
    return report


def corrected_grouped_inference(predictions: Sequence[dict]) -> dict:
    outcomes = [item["row"].trusted["outcome"] for item in predictions]
    arms = {
        "market": [item["row"].trusted["market_probability"] for item in predictions],
        "ordinary": [item["ordinary"]["probability"] for item in predictions],
        "market_only_calibration": [
            item["market_only_calibration"]["probability"] for item in predictions
        ],
        "archived_full_offset": [
            item["archived_full_offset"]["probability"] for item in predictions
        ],
    }
    comparisons = {
        "market_only_calibration_minus_market": ("market_only_calibration", "market"),
        "archived_full_offset_minus_market_only_calibration": (
            "archived_full_offset", "market_only_calibration"
        ),
        "market_only_calibration_minus_ordinary": (
            "market_only_calibration", "ordinary"
        ),
        "archived_full_offset_minus_market": ("archived_full_offset", "market"),
        "archived_full_offset_minus_ordinary": ("archived_full_offset", "ordinary"),
    }
    groups = {
        "schedule_day": [item["row"].split_date for item in predictions],
        "observed_game_week": [
            offset.game_week(item["row"].game_id) for item in predictions
        ],
    }
    result = {
        "primary_estimand": "equal-event Brier and log loss",
        "events": len(predictions),
        "schedule_dates": len(set(groups["schedule_day"])),
        "game_weeks": len(set(groups["observed_game_week"])),
        "schedule_date_event_counts": {
            unit: groups["schedule_day"].count(unit)
            for unit in sorted(set(groups["schedule_day"]))
        },
        "game_week_event_counts": {
            unit: groups["observed_game_week"].count(unit)
            for unit in sorted(set(groups["observed_game_week"]))
        },
        "schedule_day_resample": {},
        "observed_game_week_cluster_sensitivity": {},
    }
    for group_name, labels in groups.items():
        target = (
            result["schedule_day_resample"] if group_name == "schedule_day"
            else result["observed_game_week_cluster_sensitivity"]
        )
        for comparison, (left, right) in comparisons.items():
            target[comparison] = {
                loss: _group_delta_detail(
                    offset._loss_deltas(
                        outcomes, arms[left], arms[right], loss
                    ),
                    labels,
                )
                for loss in ("brier", "log_loss")
            }
    result["schedule_day_resample"]["unit_definition"] = (
        "20 complete source schedule dates; sampled with replacement, then all "
        "events pooled and the equal-event delta recomputed"
    )
    weeks = sorted(set(groups["observed_game_week"]))
    right_edge = weeks[-1]
    result["observed_game_week_cluster_sensitivity"].update({
        "unit_definition": (
            "observed NFL game-week clusters; not all clusters are complete weeks"
        ),
        "right_edge_partial_week": right_edge,
        "right_edge_partial_week_events": groups["observed_game_week"].count(right_edge),
        "primary_denominator_changed": False,
        "interpretation": (
            "secondary limited-precision sensitivity; partial right-edge week retained"
        ),
    })
    return result


def _write_predictions(path: Path, predictions: Sequence[dict]) -> None:
    fields = (
        "fold", "game_id", "split_date", "game_week", "event_id", "market_id",
        "cutoff_ms", "outcome_available_ms", "outcome", "market_probability",
        "ordinary_probability", "market_only_calibration_probability",
        "archived_full_offset_probability",
    )
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in predictions:
            row = item["row"]
            writer.writerow({
                "fold": item["fold"],
                "game_id": row.game_id,
                "split_date": row.split_date,
                "game_week": offset.game_week(row.game_id),
                "event_id": row.trusted["event_id"],
                "market_id": row.trusted["market_id"],
                "cutoff_ms": row.trusted["cutoff_ms"],
                "outcome_available_ms": row.trusted["outcome_available_ms"],
                "outcome": row.trusted["outcome"],
                "market_probability": row.trusted["market_probability"],
                "ordinary_probability": item["ordinary"]["probability"],
                "market_only_calibration_probability": item[
                    "market_only_calibration"
                ]["probability"],
                "archived_full_offset_probability": item[
                    "archived_full_offset"
                ]["probability"],
            })
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def run(source_root: Path, output: Path, *, expected_events: int = EXPECTED_EVENTS,
        expected_dates: int = EXPECTED_DATES, allow_test_paths: bool = False,
        generated_utc: str | None = None,
        archived_offset_root: Path | None = None) -> dict:
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    _validate_frozen_specs()
    identity = _validate_execution_identity()
    archive_root = Path(archived_offset_root or ARCHIVED_OFFSET_ROOT).resolve()
    archive_binding = validate_archived_offset_artifact(
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
    cohort_path = source_root / "cohort.csv"
    cohort = base._read_cohort(cohort_path)
    if len(cohort) != expected_events:
        raise ValueError("source denominator differs from frozen event count")
    if set((source_root / "catalog").glob("*.json")) != {
            source_root / "catalog" / f"{row['game_id']}.json" for row in cohort}:
        raise ValueError("normalized catalog population differs from cohort")

    output.mkdir(parents=True, exist_ok=False)
    fit_started = False
    scoring_started = False
    try:
        source_file_receipts = [{
            "source_ordinal": ordinal,
            "game_id": item["game_id"],
            "catalog_meta_sha256": base._sha256(
                source_root / "catalog" / f"{item['game_id']}.json"
            ),
            "catalog_stored_sha256": base._sha256(
                source_root / "catalog" / f"{item['game_id']}.raw.json.gz"
            ),
            "trade_manifest_sha256": base._sha256(
                source_root / "trades" / item["game_id"] / "manifest.json"
            ),
            "trade_window_sha256": base._sha256(
                source_root / "trades" / item["game_id"] / "trade_window.csv"
            ),
        } for ordinal, item in enumerate(cohort)]
        materialized = []
        exclusions = []
        for ordinal, item in enumerate(cohort):
            try:
                materialized.append(base._materialize_event(source_root, item))
            except base.EventExclusion as error:
                exclusions.append({
                    "source_ordinal": ordinal,
                    "game_id": item["game_id"],
                    "game_date": item["game_date"],
                    "reason": error.code,
                    "detail": str(error)[:400],
                })
        if len(materialized) + len(exclusions) != expected_events:
            raise RuntimeError("materialized plus excluded events do not reconcile")
        if not allow_test_paths:
            base.validate_exact_cohort_attrition(
                expected_events, len(materialized), exclusions
            )
            offset.validate_exact_real_exclusion(exclusions)
        if not materialized:
            raise ValueError("all source events were excluded")
        materialized.sort(key=lambda row: row.key)
        materialized_hash = base._digest([list(row.key) for row in materialized])
        if not allow_test_paths and materialized_hash != EXPECTED_MATERIALIZED_KEY_SHA256:
            raise ValueError("materialized key population differs from frozen parent")
        source_ordinals = {item["game_id"]: ordinal for ordinal, item in enumerate(cohort)}
        staleness = offset.staleness_inventory(materialized, source_ordinals)
        base._atomic_json(output / "staleness_inventory.json", staleness)
        offset.require_staleness_gate(
            staleness,
            expected_binary_rows=194 if not allow_test_paths else len(materialized),
        )
        folds = base.chronological_date_folds(
            [item["game_date"] for item in cohort], expected_dates=expected_dates
        )
        plan = _fold_plan(materialized, folds)
        if not allow_test_paths:
            counts = tuple(
                (len(item["fit_rows"]), len(item["check_rows"])) for item in plan
            )
            if counts != EXPECTED_REAL_FOLD_COUNTS:
                raise ValueError("fit/check event counts differ from frozen parent")
            if any(item["fit_label_unavailable_events"] for item in plan):
                raise ValueError("frozen parent expects zero unavailable fit labels")
            check_rows = [row for item in plan for row in item["check_rows"]]
            if (len(check_rows) != 87
                    or len({row.split_date for row in check_rows}) != 20
                    or len({offset.game_week(row.game_id) for row in check_rows}) != 7):
                raise ValueError("exact real check breadth differs")
            offset.require_expected_check_mask(check_rows, EXPECTED_CHECK_MASK_SHA256)

        input_receipts = {
            "schema": "nfl_market_only_ridge_calibration_train_inputs_v1",
            "source_dataset_id": source_root.name,
            "source_manifest_sha256": base._sha256(source_root / "manifest.json"),
            "cohort_sha256": base._sha256(cohort_path),
            "source_events": expected_events,
            "source_dates": expected_dates,
            "runner_source_sha256": base._sha256(Path(__file__)),
            "execution_identity": identity,
            "archived_full_offset_binding": archive_binding,
            "all_source_file_receipts": source_file_receipts,
            "materialized_event_receipts": [row.source_receipt for row in materialized],
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "provider_cost_usd": "0",
        }
        exclusions_artifact = {
            "schema": "nfl_market_only_ridge_calibration_train_exclusions_v1",
            "source_events": expected_events,
            "materialized_events": len(materialized),
            "excluded_events": len(exclusions),
            "reconciles_to_source_denominator": (
                len(materialized) + len(exclusions) == expected_events
            ),
            "exclusions": exclusions,
        }
        base._atomic_json(output / "input_receipts.json", input_receipts)
        base._atomic_json(output / "exclusions.json", exclusions_artifact)
        lock = {
            "schema": "nfl_market_only_ridge_calibration_train_pre_score_lock_v1",
            "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "problem": (
                "test past-fitted identity-shrunk affine calibration of market log-odds "
                "and compare archived added-column offset predictions"
            ),
            "domain": "2025 NFL two-outcome moneyline opened Train Discovery",
            "source_manifest_sha256": input_receipts["source_manifest_sha256"],
            "cohort_sha256": input_receipts["cohort_sha256"],
            "input_receipts_sha256": base._sha256(output / "input_receipts.json"),
            "exclusions_sha256": base._sha256(output / "exclusions.json"),
            "staleness_inventory_sha256": base._sha256(
                output / "staleness_inventory.json"
            ),
            "controller_provenance": {
                "model": "gpt-6-astra",
                "reasoning_effort": "high",
                "proposal_path": str(CONTROLLER_PROPOSAL_PATH),
                "proposal_sha256": EXPECTED_CONTROLLER_PROPOSAL_SHA256,
            },
            "execution_identity": identity,
            "archived_full_offset_binding": archive_binding,
            "source_events": expected_events,
            "source_dates": expected_dates,
            "materialized_key_sha256": materialized_hash,
            "canonical_check_mask_sha256": (
                EXPECTED_CHECK_MASK_SHA256 if not allow_test_paths else None
            ),
            "decision_cutoff": "event_start_utc minus 15 minutes",
            "max_staleness_seconds": MAX_STALENESS_SECONDS,
            "staleness_boundary": "inclusive; age in [0,600] passes",
            "outcome_availability": (
                "maximum of present selected-market closedTime, selected-market "
                "umaEndDate, and event finishedTimestamp"
            ),
            "folds": folds,
            "ordinary_spec": dict(base.ORDINARY_SPEC),
            "ordinary_spec_sha256": base._digest(dict(base.ORDINARY_SPEC)),
            "calibration_spec": dict(CALIBRATION_SPEC),
            "calibration_spec_sha256": base._digest(dict(CALIBRATION_SPEC)),
            "model_fits": {
                "market_only_calibration": 4,
                "ordinary_reference": 4,
                "archived_full_offset_refits": 0,
            },
            "event_weighting": "one row per event; equal event weight",
            "corrected_inference": {
                "schedule_units": "20 complete source schedule dates",
                "week_units": (
                    "seven observed NFL week clusters; Week 14 partial with one event"
                ),
                "seed": BOOTSTRAP_SEED,
                "replicates": BOOTSTRAP_REPLICATES,
                "per_draw_estimand": "pooled equal-event mean loss delta",
            },
            "keep_rule": (
                "calibration Brier and log loss beat market and ordinary by >1e-12; "
                "calibration Brier beats each in at least 3/4 folds"
            ),
            "incumbent_and_branch_semantics": {
                "current_best_before_run": "decision-time market probability",
                "keep_action": (
                    "replace current best with MarketOnlyRidgeCalibration-v1 for "
                    "further Discovery only"
                ),
                "revert_action": "retain decision-time market as current best",
                "ordinary_role": "ordinary reference; not Strong-Baseline-1",
                "branch_retention": (
                    "retain calibration, archived full-offset, and prior HGB branches"
                ),
                "full_offset_attribution_not_keep_condition": True,
            },
            "evidence_labels": {
                "literature_supported_principles": [
                    "strictly-prior temporal fitting",
                    "fit-only preprocessing",
                    "dependence-aware grouped resampling",
                ],
                "project_chosen_parameters_not_literature_consensus": [
                    "NFL seed cohort and 15-minute cutoff",
                    "600-second staleness bound and 22+4x5 folds",
                    "affine-logit calibration with lambda=1",
                    "solver tolerances, seed 23, 1000 replicates, and KEEP rule",
                ],
                "unvalidated_hypotheses": [
                    "market-only past-fitted calibration may improve proper scores",
                    "the 16 added full-offset columns may help or damage this recipe",
                ],
            },
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "external_fetch": False,
            "paid_provider": False,
            "provider_cost_usd": "0",
            "promotion_authorized": False,
        }
        base._atomic_json(output / "pre_score_lock.json", lock)

        fit_started = True
        predictions, fold_reports = _fit_and_predict(plan)
        archive_parity = bind_archived_full_offset(
            predictions,
            fold_reports,
            archive_root / "predictions.csv",
            verify_frozen_hash=not allow_test_paths,
        )
        check_rows = [item["row"] for item in predictions]
        if not allow_test_paths:
            offset.require_expected_check_mask(check_rows, EXPECTED_CHECK_MASK_SHA256)

        ordinary_records = [item["ordinary"] for item in predictions]
        calibration_records = [item["market_only_calibration"] for item in predictions]
        archived_records = [item["archived_full_offset"] for item in predictions]
        scoring_started = True
        pairwise = {
            "market_only_calibration_minus_market": _pair_score(
                check_rows, calibration_records,
                "market_only_calibration", "market"
            ),
            "archived_full_offset_minus_market_only_calibration": _pair_score(
                check_rows, archived_records,
                "archived_full_offset", "market_only_calibration",
                right=calibration_records,
            ),
            "market_only_calibration_minus_ordinary": _pair_score(
                check_rows, calibration_records,
                "market_only_calibration", "ordinary", right=ordinary_records,
            ),
            "archived_full_offset_minus_market": _pair_score(
                check_rows, archived_records, "archived_full_offset", "market"
            ),
            "archived_full_offset_minus_ordinary": _pair_score(
                check_rows, archived_records,
                "archived_full_offset", "ordinary", right=ordinary_records,
            ),
            "ordinary_minus_market": _pair_score(
                check_rows, ordinary_records, "ordinary", "market"
            ),
        }
        mask_hashes = {
            name: value["proper_scorer_output"]["coverage"]["complete_mask_sha256"]
            for name, value in pairwise.items()
        }
        if len(set(mask_hashes.values())) != 1:
            raise RuntimeError("pairwise proper scorers did not receive one common mask")
        calibration_score = pairwise[
            "market_only_calibration_minus_market"
        ]["proper_scorer_output"]
        ordinary_score = pairwise["ordinary_minus_market"]["proper_scorer_output"]
        archived_score = pairwise[
            "archived_full_offset_minus_market"
        ]["proper_scorer_output"]
        calibration_primary = calibration_score["primary"]
        ordinary_primary = ordinary_score["primary"]
        archived_primary = archived_score["primary"]
        aggregate = {
            "market": {
                "brier": calibration_primary["equal_event_market_brier"],
                "log_loss": calibration_primary["equal_event_market_log_loss"],
                "calibration": calibration_score["calibration"]["market"],
            },
            "ordinary_reference": {
                "brier": ordinary_primary["equal_event_candidate_brier"],
                "log_loss": ordinary_primary["equal_event_candidate_log_loss"],
                "calibration": ordinary_score["calibration"]["candidate"],
            },
            "market_only_calibration": {
                "brier": calibration_primary["equal_event_candidate_brier"],
                "log_loss": calibration_primary["equal_event_candidate_log_loss"],
                "calibration": calibration_score["calibration"]["candidate"],
            },
            "archived_full_offset": {
                "brier": archived_primary["equal_event_candidate_brier"],
                "log_loss": archived_primary["equal_event_candidate_log_loss"],
                "calibration": archived_score["calibration"]["candidate"],
            },
            "pairwise_deltas": {
                name: value["equal_event_delta"] for name, value in pairwise.items()
            },
        }
        decision, conditions = offset.diagnostic_keep(
            aggregate["market_only_calibration"],
            aggregate["market"],
            aggregate["ordinary_reference"],
            [
                fold["market"]["brier"] - fold["market_only_calibration"]["brier"]
                > STRICT_WIN_TOLERANCE
                for fold in fold_reports
            ],
            [
                fold["ordinary"]["brier"]
                - fold["market_only_calibration"]["brier"]
                > STRICT_WIN_TOLERANCE
                for fold in fold_reports
            ],
        )
        _write_predictions(output / "predictions.csv", predictions)
        scorecard = {
            "schema": "nfl_market_only_ridge_calibration_train_scorecard_v1",
            "diagnostic_decision": decision,
            "decision_scope": "replace current best for further Discovery only",
            "keep_conditions": conditions,
            "source_denominator": {
                "events": expected_events,
                "dates": expected_dates,
                "materialized_events": len(materialized),
                "excluded_events": len(exclusions),
                "check_events": len(check_rows),
                "check_dates": len({row.split_date for row in check_rows}),
                "check_game_weeks": len({offset.game_week(row.game_id) for row in check_rows}),
                "materialization_coverage": len(materialized) / expected_events,
                "check_fraction_of_source_events": len(check_rows) / expected_events,
            },
            "arms": {
                "market": "decision-time market probability",
                "ordinary_reference": "unchanged 17-feature LogisticRegression reference",
                "market_only_calibration": "new two-parameter fitted calibration",
                "archived_full_offset": (
                    "immutable MarketOffsetRidgeLogistic-v1 predictions; not refit"
                ),
            },
            "archive_parity": archive_parity,
            "identical_masks": {
                "all_named_arms_share_one_complete_check_mask": True,
                "pairwise_complete_mask_sha256": mask_hashes,
                "common_complete_mask_sha256": next(iter(mask_hashes.values())),
            },
            "aggregate": aggregate,
            "folds": fold_reports,
            "pairwise_proper_scores": pairwise,
            "corrected_grouped_inference": corrected_grouped_inference(predictions),
            "incumbent_and_branch_semantics": {
                "current_best_before_run": "decision-time market probability",
                "current_best_after_run": (
                    "MarketOnlyRidgeCalibration-v1" if decision == "KEEP"
                    else "decision-time market probability"
                ),
                "all_research_branches_retained": True,
                "ordinary_role": "ordinary reference; not Strong-Baseline-1",
            },
            "inference_boundary": (
                "reused opened-Train Discovery; descriptive intervals, not independent OOS"
            ),
            "unsupported_claims": [
                "promotion or formal out-of-sample improvement",
                "profitability or executable-price performance",
                "generalization beyond the 2025 NFL seed domain",
                "causal information content of each added feature",
                "formal evaluation of RSI self-evolution",
            ],
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "provider_cost_usd": "0",
            "promotion_authorized": False,
        }
        base._atomic_json(output / "scorecard.json", scorecard)
        final = {
            "schema": "nfl_market_only_ridge_calibration_train_manifest_v1",
            "complete": True,
            "status": "COMPLETE",
            "completed_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "pre_score_lock_sha256": base._sha256(output / "pre_score_lock.json"),
            "input_receipts_sha256": base._sha256(output / "input_receipts.json"),
            "exclusions_sha256": base._sha256(output / "exclusions.json"),
            "staleness_inventory_sha256": base._sha256(
                output / "staleness_inventory.json"
            ),
            "predictions_sha256": base._sha256(output / "predictions.csv"),
            "scorecard_sha256": base._sha256(output / "scorecard.json"),
            "source_events": expected_events,
            "materialized_events": len(materialized),
            "excluded_events": len(exclusions),
            "check_events": len(check_rows),
            "model_fits": 8,
            "calibration_fits": 4,
            "ordinary_reference_fits": 4,
            "archived_full_offset_refits": 0,
            "diagnostic_decision": decision,
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "external_fetch": False,
            "paid_provider": False,
            "provider_cost_usd": "0",
            "promotion_authorized": False,
        }
        base._atomic_json(output / "manifest.json", final)
        return final
    except Exception as error:
        if output.exists() and not (output / "manifest.json").exists():
            invalid = isinstance(error, offset.InvalidDataQuality)
            failure = {
                "schema": "nfl_market_only_ridge_calibration_train_failure_v1",
                "status": "INVALID_DATA_QUALITY" if invalid else "FAILED",
                "error_type": type(error).__name__,
                "error": str(error)[:1200],
                "fit_started": fit_started,
                "scoring_started": scoring_started,
                "route_dev_opened": False,
                "sealed_final_opened": False,
                "external_fetch": False,
                "paid_provider": False,
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
    result = run(args.source_root, args.output)
    print(json.dumps({
        "complete": result["complete"],
        "status": result["status"],
        "source_events": result["source_events"],
        "materialized_events": result["materialized_events"],
        "excluded_events": result["excluded_events"],
        "check_events": result["check_events"],
        "model_fits": result["model_fits"],
        "archived_full_offset_refits": result["archived_full_offset_refits"],
        "diagnostic_decision": result["diagnostic_decision"],
        "provider_cost_usd": result["provider_cost_usd"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
