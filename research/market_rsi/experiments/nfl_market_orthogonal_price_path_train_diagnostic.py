#!/usr/bin/env python3
"""Opened-Train Discovery runner for MarketOrthogonalPricePath-v1.

This thin sibling keeps the reviewed NFL materialization, fold, scoring, and
offset-loss contracts.  It adds two fixed signed price-path summaries and
residualizes them against market logit using prior fit rows only.  It contains
no network/provider client and never opens protected Dev/Final data.
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
from scipy.stats import rankdata
from sklearn.preprocessing import StandardScaler

from experiments import nfl_market_only_ridge_calibration_train_diagnostic as calibration


offset = calibration.offset
base = calibration.base
SOURCE_ROOT = calibration.SOURCE_ROOT
PERSISTENT_ARTIFACT_ROOT = calibration.PERSISTENT_ARTIFACT_ROOT
EXPECTED_EVENTS = calibration.EXPECTED_EVENTS
EXPECTED_DATES = calibration.EXPECTED_DATES
EXPECTED_REAL_FOLD_COUNTS = calibration.EXPECTED_REAL_FOLD_COUNTS
EXPECTED_MATERIALIZED_KEY_SHA256 = calibration.EXPECTED_MATERIALIZED_KEY_SHA256
EXPECTED_CHECK_MASK_SHA256 = calibration.EXPECTED_CHECK_MASK_SHA256
MAX_STALENESS_SECONDS = calibration.MAX_STALENESS_SECONDS
STRICT_WIN_TOLERANCE = calibration.STRICT_WIN_TOLERANCE

EXPECTED_CALIBRATION_RUNNER_SHA256 = (
    "71d329468c865246616b8cb1ee7b284a488c9ad382f2bda830bb529e383cc191"
)
EXPECTED_CALIBRATION_TEST_SHA256 = (
    "548d8d633fc2007414d10874b11300442ebb97719eb101bb451cd3bd8d755bb0"
)
CONTROLLER_PROPOSAL_PATH = (
    Path(__file__).resolve().parents[1]
    / "supervisor_harness"
    / "AGENT_LOG_POST_CALIBRATION_NEXT_CONTROLLER_2026-09-29.md"
)
EXPECTED_CONTROLLER_PROPOSAL_SHA256 = (
    "8b5fbdef19279098759169d5a83ced8077abfe5c56b787667bd9dbb0a5632719"
)
ARCHIVED_CALIBRATION_ROOT = PERSISTENT_ARTIFACT_ROOT / (
    "first-real-train-diagnostic-market-only-ridge-calibration-20260929-01"
)
ARCHIVED_CALIBRATION_SHA256 = MappingProxyType({
    "exclusions.json": "c6e8d143c0aa20610e1ea391200d692bff94ee0fd39e3e9107993fae7538f131",
    "input_receipts.json": "db6506a0544a82b2a51d82bc65fb77f1a435f511da34f568041aea7d64f2f297",
    "manifest.json": "a6e2e63b97fabab640c83f264e2c3afdbee1390f90dd2f1c39ffeb31131f37bb",
    "pre_score_lock.json": "190a846bf29edb1418ba7a2677d8cc87aa1b488cfe3284943d75a21481537ac7",
    "predictions.csv": "b9d28742157dd79cead5d2f22071daaa40526ad78b55b6a9c007f43c9e5f2358",
    "scorecard.json": "513856565af0cd9d4142b875d9fb38b3141bb59da58f330d4a6fa1c9144e7f2b",
    "staleness_inventory.json": "3b545bd2542b4a4102ed0aa0f2adaed435322fc58bea06b599ebee765abea10e",
})
ARCHIVED_FIELDS = (
    "fold", "game_id", "split_date", "game_week", "event_id", "market_id",
    "cutoff_ms", "outcome_available_ms", "outcome", "market_probability",
    "ordinary_probability", "market_only_calibration_probability",
    "archived_full_offset_probability",
)
VWAP_FEATURES = tuple(
    f"trailing_{minutes}m_weighted_mean_home_probability"
    for minutes in (15, 60, 240)
)
MOVE_FEATURES = tuple(
    f"trailing_{minutes}m_last_minus_first_home_probability"
    for minutes in (15, 60, 240)
)
INACTIVE_STD_THRESHOLD = 1e-8
CANDIDATE_SPEC = MappingProxyType({
    "name": "MarketOrthogonalPricePath-v1",
    "raw_families": {
        "g": "market_probability_minus_mean(VWAP_15m,VWAP_60m,VWAP_240m)",
        "d": "mean(last_minus_first_15m,last_minus_first_60m,last_minus_first_240m)",
    },
    "market_residualization": "fit-only OLS against [1,z_market]",
    "lstsq_rcond": 1e-12,
    "rank_required": 2,
    "inactive_fit_population_std_at_most": INACTIVE_STD_THRESHOLD,
    "candidate_design": ["z_market", "z_g", "z_d"],
    "offset": "unstandardized market logit coefficient fixed at 1",
    "objective": "mean Bernoulli NLL plus 0.5 times squared L2 of all 4 parameters",
    "lambda": 1.0,
    "penalize_intercept": True,
    "initial_parameters": "all_zero",
    "optimizer": "L-BFGS-B analytic gradient maxiter=1000 gtol=1e-8 ftol=1e-12",
    "dtype": "float64",
    "hyperparameter_search": False,
})
EXPECTED_CANDIDATE_SPEC_SHA256 = (
    "3c3adf107569fadc8c13dc2a682b2a8e170322b863a439b5f1ea974449e06228"
)


def _validate_frozen_specs() -> None:
    calibration._validate_frozen_specs()
    if base._digest(dict(CANDIDATE_SPEC)) != EXPECTED_CANDIDATE_SPEC_SHA256:
        raise RuntimeError("orthogonal price-path candidate spec changed")
    # Exact names are part of the frozen recipe; resolving them here also
    # catches duplicates or parent feature-schema drift before data access.
    _feature_indices(VWAP_FEATURES)
    _feature_indices(MOVE_FEATURES)


def execution_identity() -> dict:
    return {
        "calibration_runner_sha256": base._sha256(Path(calibration.__file__)),
        "calibration_test_sha256": base._sha256(
            Path(__file__).resolve().parents[1]
            / "tests"
            / "test_nfl_market_only_ridge_calibration_train_diagnostic.py"
        ),
        "controller_proposal_path": str(CONTROLLER_PROPOSAL_PATH),
        "controller_proposal_sha256": base._sha256(CONTROLLER_PROPOSAL_PATH),
        "runtime_and_deeper_dependencies": calibration._validate_execution_identity(),
    }


def _validate_execution_identity() -> dict:
    identity = execution_identity()
    expected = {
        "calibration_runner_sha256": EXPECTED_CALIBRATION_RUNNER_SHA256,
        "calibration_test_sha256": EXPECTED_CALIBRATION_TEST_SHA256,
        "controller_proposal_sha256": EXPECTED_CONTROLLER_PROPOSAL_SHA256,
    }
    if any(identity[name] != value for name, value in expected.items()):
        raise RuntimeError(f"frozen execution identity changed: {identity}")
    return identity


def validate_archived_calibration_artifact(
        root: Path, *, verify_frozen_hashes: bool) -> dict:
    root = Path(root).resolve()
    observed = {path.name for path in root.iterdir() if path.is_file()}
    if observed != set(ARCHIVED_CALIBRATION_SHA256):
        raise ValueError("archived calibration artifact file set differs")
    hashes = {name: base._sha256(root / name) for name in sorted(observed)}
    if verify_frozen_hashes and hashes != dict(ARCHIVED_CALIBRATION_SHA256):
        raise ValueError("archived calibration artifact hash changed")
    manifest = base._strict_json(root / "manifest.json")
    if (not isinstance(manifest, dict)
            or manifest.get("schema") != "nfl_market_only_ridge_calibration_train_manifest_v1"
            or manifest.get("complete") is not True
            or manifest.get("status") != "COMPLETE"
            or manifest.get("provider_cost_usd") != "0"
            or manifest.get("route_dev_opened") is not False
            or manifest.get("sealed_final_opened") is not False
            or manifest.get("external_fetch") is not False
            or manifest.get("paid_provider") is not False):
        raise ValueError("archived calibration manifest boundary failed")
    bindings = {
        "pre_score_lock.json": manifest.get("pre_score_lock_sha256"),
        "input_receipts.json": manifest.get("input_receipts_sha256"),
        "exclusions.json": manifest.get("exclusions_sha256"),
        "staleness_inventory.json": manifest.get("staleness_inventory_sha256"),
        "predictions.csv": manifest.get("predictions_sha256"),
        "scorecard.json": manifest.get("scorecard_sha256"),
    }
    if any(hashes[name] != value for name, value in bindings.items()):
        raise ValueError("archived calibration manifest hash binding failed")
    return {"artifact_root": str(root), "artifact_hashes": hashes}


def _feature_indices(names: Sequence[str]) -> tuple[int, ...]:
    indices = []
    for name in names:
        matches = [i for i, observed in enumerate(base.FEATURE_NAMES) if observed == name]
        if len(matches) != 1:
            raise RuntimeError(f"frozen feature name missing or duplicated: {name}")
        indices.append(matches[0])
    return tuple(indices)


def _invalid_transform(reason: str, **detail: object) -> None:
    raise offset.InvalidDataQuality(
        f"INVALID_DATA_QUALITY: price-path transform {reason}",
        {
            "schema": "nfl_market_orthogonal_price_path_invalid_transform_v1",
            "status": "INVALID_DATA_QUALITY",
            "stage": "fit_only_price_path_transform",
            "reason": reason,
            **detail,
        },
    )


def price_path_families(rows: Sequence[base.DiagnosticRow]) -> np.ndarray:
    """Return fixed [g,d] summaries selected only by exact frozen names."""
    if not rows:
        _invalid_transform("empty_rows", rows=0)
    matrix = np.asarray([row.features for row in rows], dtype=np.float64)
    if matrix.shape != (len(rows), len(base.FEATURE_NAMES)) or not np.all(np.isfinite(matrix)):
        _invalid_transform(
            "feature_matrix_shape_or_nonfinite",
            rows=len(rows), observed_shape=list(matrix.shape),
            expected_shape=[len(rows), len(base.FEATURE_NAMES)],
        )
    vwap = matrix[:, _feature_indices(VWAP_FEATURES)]
    move = matrix[:, _feature_indices(MOVE_FEATURES)]
    market = np.asarray(
        [row.trusted["market_probability"] for row in rows], dtype=np.float64
    )
    result = np.column_stack((market - np.mean(vwap, axis=1), np.mean(move, axis=1)))
    if not np.all(np.isfinite(result)):
        _invalid_transform("raw_family_nonfinite", rows=len(rows))
    return result


def fit_price_path_transform(
        fit_rows: Sequence[base.DiagnosticRow],
        check_rows: Sequence[base.DiagnosticRow]) -> dict:
    """Fit the label-free market residualizer/scalers on fit rows only."""
    fit_logits = calibration._market_logits(fit_rows)
    check_logits = calibration._market_logits(check_rows)
    scaler = StandardScaler()
    z_market_fit = scaler.fit_transform(fit_logits.reshape(-1, 1))[:, 0]
    z_market_check = scaler.transform(check_logits.reshape(-1, 1))[:, 0]
    raw_fit = price_path_families(fit_rows)
    raw_check = price_path_families(check_rows)
    a_fit = np.column_stack((np.ones(len(fit_rows)), z_market_fit))
    beta, _, rank, singular = np.linalg.lstsq(a_fit, raw_fit, rcond=1e-12)
    if int(rank) != 2:
        _invalid_transform(
            "market_residualization_rank_failure",
            observed_rank=int(rank), required_rank=2,
            singular_values=[float(value) for value in singular],
            fit_rows=len(fit_rows), check_rows=len(check_rows),
        )
    a_check = np.column_stack((np.ones(len(check_rows)), z_market_check))
    residual_fit = raw_fit - a_fit @ beta
    residual_check = raw_check - a_check @ beta
    means = np.mean(residual_fit, axis=0)
    scales = np.std(residual_fit, axis=0, ddof=0)
    inactive = scales <= INACTIVE_STD_THRESHOLD
    z_family_fit = np.zeros_like(residual_fit)
    z_family_check = np.zeros_like(residual_check)
    for column in range(2):
        if not inactive[column]:
            z_family_fit[:, column] = (
                residual_fit[:, column] - means[column]
            ) / scales[column]
            z_family_check[:, column] = (
                residual_check[:, column] - means[column]
            ) / scales[column]
    arrays = (
        z_market_fit, z_market_check, raw_fit, raw_check, residual_fit,
        residual_check, z_family_fit, z_family_check, beta, means, scales,
    )
    if any(not np.all(np.isfinite(value)) for value in arrays):
        _invalid_transform(
            "nonfinite_transform_output",
            fit_rows=len(fit_rows), check_rows=len(check_rows),
        )
    return {
        "fit_design": np.column_stack((z_market_fit, z_family_fit)),
        "check_design": np.column_stack((z_market_check, z_family_check)),
        "fit_logits": fit_logits,
        "check_logits": check_logits,
        "raw_fit": raw_fit,
        "raw_check": raw_check,
        "residual_fit": residual_fit,
        "residual_check": residual_check,
        "z_family_fit": z_family_fit,
        "z_family_check": z_family_check,
        "parameters": {
            "market_scaler_mean": float(scaler.mean_[0]),
            "market_scaler_scale": float(scaler.scale_[0]),
            "lstsq_rcond": 1e-12,
            "rank": int(rank),
            "singular_values": [float(value) for value in singular],
            "residualization_beta_rows_intercept_market": [
                [float(value) for value in row] for row in beta
            ],
            "residual_fit_means_g_d": [float(value) for value in means],
            "residual_fit_population_stds_g_d": [float(value) for value in scales],
            "inactive_families_g_d": [bool(value) for value in inactive],
            "inactive_threshold_inclusive": INACTIVE_STD_THRESHOLD,
        },
    }


def _correlation(left: np.ndarray, right: np.ndarray, *, rank: bool = False) -> dict:
    left = np.asarray(left, dtype=np.float64)
    right = np.asarray(right, dtype=np.float64)
    if left.shape != right.shape or left.ndim != 1:
        raise ValueError("correlation vectors must align")
    if left.size < 2:
        return {"value": None, "count": int(left.size), "reason": "fewer_than_2_rows"}
    if rank:
        left, right = rankdata(left, method="average"), rankdata(right, method="average")
    if float(np.std(left)) == 0.0 or float(np.std(right)) == 0.0:
        return {"value": None, "count": int(left.size), "reason": "constant_input"}
    return {
        "value": float(np.corrcoef(left, right)[0, 1]),
        "count": int(left.size),
        "reason": None,
    }


def information_diagnostics(
        raw: np.ndarray, residual: np.ndarray, standardized: np.ndarray,
        market_logits: np.ndarray, outcomes: Sequence[int], market: Sequence[float],
        dates: Sequence[str]) -> dict:
    names = ("g_market_minus_mean_vwap", "d_mean_price_move")
    y_minus_market = np.asarray(outcomes, dtype=np.float64) - np.asarray(
        market, dtype=np.float64
    )
    families = {}
    for column, name in enumerate(names):
        raw_variance = float(np.var(raw[:, column], ddof=0))
        residual_variance = float(np.var(residual[:, column], ddof=0))
        date_moments = []
        for date in sorted(set(dates)):
            mask = np.asarray([value == date for value in dates])
            moments = standardized[mask, column] * y_minus_market[mask]
            date_moments.append({
                "schedule_date": date,
                "events": int(np.sum(mask)),
                "mean_z_times_y_minus_market": float(np.mean(moments)),
            })
        families[name] = {
            "count": int(len(raw)),
            "raw_variance": raw_variance,
            "residual_variance": residual_variance,
            "residual_over_raw_variance_fraction": (
                residual_variance / raw_variance if raw_variance > 0 else None
            ),
            "raw_correlation_with_market_logit": _correlation(
                raw[:, column], market_logits
            ),
            "residual_correlation_with_market_logit": _correlation(
                residual[:, column], market_logits
            ),
            "pearson_z_with_y_minus_market": _correlation(
                standardized[:, column], y_minus_market
            ),
            "spearman_z_with_y_minus_market": _correlation(
                standardized[:, column], y_minus_market, rank=True
            ),
            "mean_z_times_y_minus_market": float(np.mean(
                standardized[:, column] * y_minus_market
            )),
            "per_schedule_date_moment": date_moments,
        }
    return {
        "families": families,
        "residual_family_correlation": _correlation(residual[:, 0], residual[:, 1]),
    }


def _fit_fold_models(fit_rows: Sequence[base.DiagnosticRow],
                     check_rows: Sequence[base.DiagnosticRow]) -> dict:
    # Validate and freeze the label-free transform before spending any model
    # fit. Rank/nonfinite failures are data-quality terminal for this run.
    transform = fit_price_path_transform(fit_rows, check_rows)
    controls = calibration._fit_fold_models(fit_rows, check_rows)
    control_params = controls["calibration_parameters"]
    transform_params = transform["parameters"]
    mean_delta = abs(
        transform_params["market_scaler_mean"] - control_params["mu"]
    )
    scale_delta = abs(
        transform_params["market_scaler_scale"] - control_params["scale"]
    )
    if mean_delta > 1e-12 or scale_delta > 1e-12:
        raise RuntimeError("candidate market scaler differs from calibration control")
    fit_market = [row.trusted["market_probability"] for row in fit_rows]
    check_market = [row.trusted["market_probability"] for row in check_rows]
    # The frozen recipe requires fit-only information measurement before the
    # candidate sees outcomes through its optimizer.  This function consumes
    # outcomes only for reporting associations; it cannot gate or mutate the
    # already frozen transform or candidate design.
    fit_diagnostics = information_diagnostics(
        transform["raw_fit"], transform["residual_fit"],
        transform["z_family_fit"], transform["fit_logits"],
        [row.trusted["outcome"] for row in fit_rows], fit_market,
        [row.split_date for row in fit_rows],
    )
    y_fit = np.asarray([row.trusted["outcome"] for row in fit_rows], dtype=np.int64)
    parameters, optimizer = offset.fit_offset_ridge(
        transform["fit_design"], y_fit, transform["fit_logits"]
    )
    candidate_values = offset.offset_probabilities(
        parameters, transform["check_design"], transform["check_logits"]
    )
    # Check diagnostics are intentionally computed only after prediction; they
    # are descriptive and cannot affect this attempt's model or row mask.
    check_diagnostics = information_diagnostics(
        transform["raw_check"], transform["residual_check"],
        transform["z_family_check"], transform["check_logits"],
        [row.trusted["outcome"] for row in check_rows], check_market,
        [row.split_date for row in check_rows],
    )
    fit_diagnostics["fit_rows_only_transform"] = True
    check_diagnostics["uses_prior_fold_transform_without_refit"] = True
    return {
        **controls,
        "candidate_values": candidate_values,
        "candidate_optimizer": optimizer,
        "candidate_parameters": {
            "b": float(parameters[0]),
            "w_market": float(parameters[1]),
            "w_g": float(parameters[2]),
            "w_d": float(parameters[3]),
            "market_scaler_vs_calibration_mean_absolute_difference": mean_delta,
            "market_scaler_vs_calibration_scale_absolute_difference": scale_delta,
            **transform_params,
        },
        "fit_information_diagnostics": fit_diagnostics,
        "check_information_diagnostics": check_diagnostics,
    }


def _fit_and_predict(plan: Sequence[dict]) -> tuple[list[dict], list[dict]]:
    predictions, reports = [], []
    for fold in plan:
        result = _fit_fold_models(fold["fit_rows"], fold["check_rows"])
        rows = fold["check_rows"]
        ordinary = base._prediction_records(rows, result["ordinary_values"])
        cal = base._prediction_records(rows, result["calibration_values"])
        candidate = base._prediction_records(rows, result["candidate_values"])
        outcomes = [row.trusted["outcome"] for row in rows]
        market_values = [row.trusted["market_probability"] for row in rows]
        metrics = {
            "market": base._simple_metrics(outcomes, market_values),
            "ordinary": base._simple_metrics(
                outcomes, [item["probability"] for item in ordinary]
            ),
            "market_only_calibration": base._simple_metrics(
                outcomes, [item["probability"] for item in cal]
            ),
            "candidate": base._simple_metrics(
                outcomes, [item["probability"] for item in candidate]
            ),
        }
        reports.append({
            "fold": fold["fold"],
            "fit_dates": fold["fit_dates"],
            "check_dates": fold["check_dates"],
            "fit_events": len(fold["fit_rows"]),
            "check_events": len(rows),
            "fit_label_unavailable_events": fold["fit_label_unavailable_events"],
            **metrics,
            "candidate_minus_market_brier": metrics["candidate"]["brier"] - metrics["market"]["brier"],
            "candidate_minus_market_log_loss": metrics["candidate"]["log_loss"] - metrics["market"]["log_loss"],
            "candidate_minus_calibration_brier": metrics["candidate"]["brier"] - metrics["market_only_calibration"]["brier"],
            "candidate_minus_calibration_log_loss": metrics["candidate"]["log_loss"] - metrics["market_only_calibration"]["log_loss"],
            "candidate_minus_ordinary_brier": metrics["candidate"]["brier"] - metrics["ordinary"]["brier"],
            "candidate_minus_ordinary_log_loss": metrics["candidate"]["log_loss"] - metrics["ordinary"]["log_loss"],
            "candidate_optimizer": result["candidate_optimizer"],
            "candidate_parameters": result["candidate_parameters"],
            "calibration_optimizer": result["optimizer"],
            "calibration_parameters": result["calibration_parameters"],
            "fit_information_diagnostics": result["fit_information_diagnostics"],
            "check_information_diagnostics": result["check_information_diagnostics"],
            "candidate_probability_correction": {
                "mean": float(np.mean(result["candidate_values"] - np.asarray(market_values))),
                "minimum": float(np.min(result["candidate_values"] - np.asarray(market_values))),
                "maximum": float(np.max(result["candidate_values"] - np.asarray(market_values))),
            },
        })
        for row, ordinary_item, cal_item, candidate_item in zip(
                rows, ordinary, cal, candidate, strict=True):
            predictions.append({
                "fold": fold["fold"], "row": row, "ordinary": ordinary_item,
                "market_only_calibration": cal_item, "candidate": candidate_item,
            })
    keys = [item["row"].key for item in predictions]
    if len(keys) != len(set(keys)):
        raise ValueError("an event appears in multiple check folds")
    return predictions, reports


def bind_archived_controls(predictions: Sequence[dict], fold_reports: Sequence[dict],
                           predictions_csv: Path,
                           *, verify_frozen_hash: bool) -> dict:
    predictions_csv = Path(predictions_csv)
    if (verify_frozen_hash
            and base._sha256(predictions_csv)
            != ARCHIVED_CALIBRATION_SHA256["predictions.csv"]):
        raise ValueError("archived calibration predictions hash changed")
    with predictions_csv.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != ARCHIVED_FIELDS:
            raise ValueError("archived calibration prediction schema changed")
        archived = list(reader)
    if len(archived) != len(predictions):
        raise ValueError("archived calibration row count differs")
    max_ordinary, max_calibration = 0.0, 0.0
    for item, control in zip(predictions, archived, strict=True):
        row = item["row"]
        identity = (
            str(item["fold"]), row.game_id, row.split_date,
            offset.game_week(row.game_id), row.trusted["event_id"],
            row.trusted["market_id"], str(row.trusted["cutoff_ms"]),
            str(row.trusted["outcome_available_ms"]), str(row.trusted["outcome"]),
        )
        if identity != tuple(control[name] for name in ARCHIVED_FIELDS[:9]):
            raise ValueError("archived calibration identity/order/outcome differs")
        if row.trusted["market_probability"] != float(control["market_probability"]):
            raise ValueError("archived calibration market probability differs")
        ordinary_delta = abs(
            item["ordinary"]["probability"] - float(control["ordinary_probability"])
        )
        calibration_delta = abs(
            item["market_only_calibration"]["probability"]
            - float(control["market_only_calibration_probability"])
        )
        max_ordinary = max(max_ordinary, ordinary_delta)
        max_calibration = max(max_calibration, calibration_delta)
        if ordinary_delta > 1e-10 or calibration_delta > 1e-10:
            raise ValueError("recomputed frozen control differs by >1e-10")
        item["archived_full_offset"] = base._prediction_records(
            [row], [float(control["archived_full_offset_probability"])]
        )[0]
    for report in fold_reports:
        items = [item for item in predictions if item["fold"] == report["fold"]]
        outcomes = [item["row"].trusted["outcome"] for item in items]
        archived_metrics = base._simple_metrics(
            outcomes, [item["archived_full_offset"]["probability"] for item in items]
        )
        report["archived_full_offset"] = archived_metrics
        report["candidate_minus_archived_full_offset_brier"] = (
            report["candidate"]["brier"] - archived_metrics["brier"]
        )
        report["candidate_minus_archived_full_offset_log_loss"] = (
            report["candidate"]["log_loss"] - archived_metrics["log_loss"]
        )
    return {
        "archived_predictions_sha256": base._sha256(predictions_csv),
        "rows": len(predictions),
        "identity_order_outcomes_exact": True,
        "market_probability_exact": True,
        "control_probability_tolerance": 1e-10,
        "maximum_ordinary_absolute_difference": max_ordinary,
        "maximum_calibration_absolute_difference": max_calibration,
        "archived_full_offset_refit": False,
    }


def _pair_score(rows: Sequence[base.DiagnosticRow], left: Sequence[dict],
                left_name: str, right_name: str,
                *, right: Sequence[dict] | None = None) -> dict:
    return calibration._pair_score(
        rows, left, left_name, right_name, right=right
    )


def corrected_grouped_inference(predictions: Sequence[dict]) -> dict:
    outcomes = [item["row"].trusted["outcome"] for item in predictions]
    arms = {
        "market": [item["row"].trusted["market_probability"] for item in predictions],
        "ordinary": [item["ordinary"]["probability"] for item in predictions],
        "market_only_calibration": [item["market_only_calibration"]["probability"] for item in predictions],
        "archived_full_offset": [item["archived_full_offset"]["probability"] for item in predictions],
        "candidate": [item["candidate"]["probability"] for item in predictions],
    }
    comparisons = {
        "candidate_minus_market": ("candidate", "market"),
        "candidate_minus_ordinary": ("candidate", "ordinary"),
        "candidate_minus_market_only_calibration": ("candidate", "market_only_calibration"),
        "candidate_minus_archived_full_offset": ("candidate", "archived_full_offset"),
        "market_only_calibration_minus_market": ("market_only_calibration", "market"),
    }
    groups = {
        "schedule_day": [item["row"].split_date for item in predictions],
        "observed_game_week": [offset.game_week(item["row"].game_id) for item in predictions],
    }
    result = {
        "primary_estimand": "equal-event Brier and log loss",
        "events": len(predictions),
        "schedule_dates": len(set(groups["schedule_day"])),
        "game_weeks": len(set(groups["observed_game_week"])),
        "schedule_day_resample": {},
        "observed_game_week_cluster_sensitivity": {},
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
    fields = (*ARCHIVED_FIELDS, "candidate_probability")
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
                "candidate_probability": item["candidate"]["probability"],
            })
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def run(source_root: Path, output: Path, *, expected_events: int = EXPECTED_EVENTS,
        expected_dates: int = EXPECTED_DATES, allow_test_paths: bool = False,
        generated_utc: str | None = None,
        archived_calibration_root: Path | None = None) -> dict:
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    _validate_frozen_specs()
    identity = _validate_execution_identity()
    archive_root = Path(
        archived_calibration_root or ARCHIVED_CALIBRATION_ROOT
    ).resolve()
    archive_binding = validate_archived_calibration_artifact(
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

    output.mkdir(parents=True, exist_ok=False)
    fit_started = False
    scoring_started = False
    try:
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
            if counts != EXPECTED_REAL_FOLD_COUNTS:
                raise ValueError("fit/check event counts differ from frozen parent")
            if any(item["fit_label_unavailable_events"] for item in plan):
                raise ValueError("frozen parent expects zero unavailable fit labels")
            real_check = [row for item in plan for row in item["check_rows"]]
            if (len(real_check) != 87
                    or len({row.split_date for row in real_check}) != 20
                    or len({offset.game_week(row.game_id) for row in real_check}) != 7):
                raise ValueError("exact real check breadth differs")
            offset.require_expected_check_mask(real_check, EXPECTED_CHECK_MASK_SHA256)

        inputs = {
            "schema": "nfl_market_orthogonal_price_path_train_inputs_v1",
            "source_dataset_id": source_root.name,
            "source_manifest_sha256": base._sha256(source_root / "manifest.json"),
            "cohort_sha256": base._sha256(source_root / "cohort.csv"),
            "source_events": expected_events, "source_dates": expected_dates,
            "runner_source_sha256": base._sha256(Path(__file__)),
            "execution_identity": identity,
            "archived_calibration_binding": archive_binding,
            "all_source_file_receipts": source_file_receipts,
            "materialized_event_receipts": [row.source_receipt for row in materialized],
            "route_dev_opened": False, "sealed_final_opened": False,
            "provider_cost_usd": "0",
        }
        exclusions_doc = {
            "schema": "nfl_market_orthogonal_price_path_train_exclusions_v1",
            "source_events": expected_events, "materialized_events": len(materialized),
            "excluded_events": len(exclusions),
            "reconciles_to_source_denominator": len(materialized) + len(exclusions) == expected_events,
            "exclusions": exclusions,
        }
        base._atomic_json(output / "input_receipts.json", inputs)
        base._atomic_json(output / "exclusions.json", exclusions_doc)
        lock = {
            "schema": "nfl_market_orthogonal_price_path_train_pre_score_lock_v1",
            "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "problem": "test two compressed signed price-path families after fit-only market residualization",
            "domain": "2025 NFL two-outcome moneyline opened Train Discovery",
            "source_manifest_sha256": inputs["source_manifest_sha256"],
            "cohort_sha256": inputs["cohort_sha256"],
            "input_receipts_sha256": base._sha256(output / "input_receipts.json"),
            "exclusions_sha256": base._sha256(output / "exclusions.json"),
            "staleness_inventory_sha256": base._sha256(output / "staleness_inventory.json"),
            "controller_provenance": {
                "model": "gpt-6-astra", "reasoning_effort": "high",
                "proposal_path": str(CONTROLLER_PROPOSAL_PATH),
                "proposal_sha256": EXPECTED_CONTROLLER_PROPOSAL_SHA256,
            },
            "execution_identity": identity,
            "archived_calibration_binding": archive_binding,
            "source_events": expected_events, "source_dates": expected_dates,
            "materialized_key_sha256": materialized_hash,
            "canonical_check_mask_sha256": EXPECTED_CHECK_MASK_SHA256 if not allow_test_paths else None,
            "decision_cutoff": "event_start_utc minus 15 minutes",
            "max_staleness_seconds": MAX_STALENESS_SECONDS,
            "outcome_orientation": "home-token settlement probability",
            "folds": folds,
            "candidate_spec": dict(CANDIDATE_SPEC),
            "candidate_spec_sha256": base._digest(dict(CANDIDATE_SPEC)),
            "model_fits": {
                "candidate": 4, "market_only_calibration": 4,
                "ordinary_reference": 4, "archived_full_offset_refits": 0,
            },
            "event_weighting": "one row per event; equal event weight",
            "grouped_inference": {
                "seed": offset.BOOTSTRAP_SEED,
                "replicates": offset.BOOTSTRAP_REPLICATES,
                "per_draw_estimand": "pooled equal-event mean loss delta",
            },
            "keep_rule": "candidate beats market and ordinary aggregate Brier/log by >1e-12 and Brier in >=3/4 folds against each",
            "evidence_labels": {
                "literature_supported_principles": [
                    "strictly-prior temporal fitting", "fit-only preprocessing",
                    "paired same-row comparison", "dependence-aware grouped resampling",
                ],
                "project_chosen_parameters_not_literature_consensus": [
                    "two equal-weight family formulas", "linear residualization and rcond",
                    "inactive threshold", "NFL/cutoff/staleness/folds/lambda/optimizer/seed/KEEP rule",
                ],
                "unvalidated_hypotheses": [
                    "compressed signed price paths may add information beyond market",
                    "this residual trainer may convert that association into better proper scores",
                ],
            },
            "route_dev_opened": False, "sealed_final_opened": False,
            "external_fetch": False, "paid_provider": False,
            "provider_cost_usd": "0", "promotion_authorized": False,
        }
        base._atomic_json(output / "pre_score_lock.json", lock)

        fit_started = True
        predictions, fold_reports = _fit_and_predict(plan)
        control_parity = bind_archived_controls(
            predictions, fold_reports, archive_root / "predictions.csv",
            verify_frozen_hash=not allow_test_paths,
        )
        check_rows = [item["row"] for item in predictions]
        if not allow_test_paths:
            offset.require_expected_check_mask(check_rows, EXPECTED_CHECK_MASK_SHA256)
        records = {
            "ordinary": [item["ordinary"] for item in predictions],
            "market_only_calibration": [item["market_only_calibration"] for item in predictions],
            "archived_full_offset": [item["archived_full_offset"] for item in predictions],
            "candidate": [item["candidate"] for item in predictions],
        }
        scoring_started = True
        comparisons = {
            "candidate_minus_market": ("candidate", "market"),
            "candidate_minus_ordinary": ("candidate", "ordinary"),
            "candidate_minus_market_only_calibration": ("candidate", "market_only_calibration"),
            "candidate_minus_archived_full_offset": ("candidate", "archived_full_offset"),
            "market_only_calibration_minus_market": ("market_only_calibration", "market"),
            "ordinary_minus_market": ("ordinary", "market"),
            "archived_full_offset_minus_market": ("archived_full_offset", "market"),
        }
        pairwise = {}
        for name, (left, right) in comparisons.items():
            pairwise[name] = _pair_score(
                check_rows, records[left], left, right,
                right=None if right == "market" else records[right],
            )
        masks = {
            name: value["proper_scorer_output"]["coverage"]["complete_mask_sha256"]
            for name, value in pairwise.items()
        }
        if len(set(masks.values())) != 1:
            raise RuntimeError("pairwise proper scorers did not receive one common mask")
        def arm_from(pair: str, role: str) -> dict:
            score = pairwise[pair]["proper_scorer_output"]
            prefix = "market" if role == "market" else "candidate"
            return {
                "brier": score["primary"][f"equal_event_{prefix}_brier"],
                "log_loss": score["primary"][f"equal_event_{prefix}_log_loss"],
                "calibration": score["calibration"][prefix],
            }
        aggregate = {
            "market": arm_from("candidate_minus_market", "market"),
            "ordinary_reference": arm_from("ordinary_minus_market", "candidate"),
            "market_only_calibration": arm_from("market_only_calibration_minus_market", "candidate"),
            "archived_full_offset": arm_from("archived_full_offset_minus_market", "candidate"),
            "candidate": arm_from("candidate_minus_market", "candidate"),
            "pairwise_deltas": {name: value["equal_event_delta"] for name, value in pairwise.items()},
        }
        decision, conditions = offset.diagnostic_keep(
            aggregate["candidate"], aggregate["market"], aggregate["ordinary_reference"],
            [fold["market"]["brier"] - fold["candidate"]["brier"] > STRICT_WIN_TOLERANCE for fold in fold_reports],
            [fold["ordinary"]["brier"] - fold["candidate"]["brier"] > STRICT_WIN_TOLERANCE for fold in fold_reports],
        )
        calibration_diagnostic = {
            "candidate_beats_calibration_aggregate_brier": aggregate["market_only_calibration"]["brier"] - aggregate["candidate"]["brier"] > STRICT_WIN_TOLERANCE,
            "candidate_beats_calibration_aggregate_log_loss": aggregate["market_only_calibration"]["log_loss"] - aggregate["candidate"]["log_loss"] > STRICT_WIN_TOLERANCE,
            "candidate_calibration_fold_brier_wins": [fold["market_only_calibration"]["brier"] - fold["candidate"]["brier"] > STRICT_WIN_TOLERANCE for fold in fold_reports],
        }
        _write_predictions(output / "predictions.csv", predictions)
        scorecard = {
            "schema": "nfl_market_orthogonal_price_path_train_scorecard_v1",
            "diagnostic_decision": decision,
            "decision_scope": "replace current best for further Discovery only",
            "keep_conditions": conditions,
            "candidate_vs_calibration_diagnostic": calibration_diagnostic,
            "source_denominator": {
                "events": expected_events, "dates": expected_dates,
                "materialized_events": len(materialized), "excluded_events": len(exclusions),
                "check_events": len(check_rows),
                "check_dates": len({row.split_date for row in check_rows}),
                "check_game_weeks": len({offset.game_week(row.game_id) for row in check_rows}),
            },
            "arms": {
                "market": "decision-time market probability",
                "ordinary_reference": "unchanged 17-feature LogisticRegression reference",
                "market_only_calibration": "recomputed frozen two-parameter calibration control",
                "archived_full_offset": "immutable full-offset predictions; not refit",
                "candidate": "MarketOrthogonalPricePath-v1",
            },
            "control_parity": control_parity,
            "identical_masks": {"all_arms_share_one_complete_mask": True, "mask_sha256": masks},
            "aggregate": aggregate, "folds": fold_reports,
            "pairwise_proper_scores": pairwise,
            "corrected_grouped_inference": corrected_grouped_inference(predictions),
            "incumbent_and_branch_semantics": {
                "current_best_before_run": "decision-time market probability",
                "current_best_after_run": "MarketOrthogonalPricePath-v1" if decision == "KEEP" else "decision-time market probability",
                "all_research_branches_retained": True,
            },
            "inference_boundary": "reused opened-Train Discovery; not independent OOS",
            "unsupported_claims": [
                "promotion or formal OOS improvement", "profitability",
                "generalization beyond 2025 NFL", "nonlinear conditional independence",
                "RSI self-evolution or transferable research skill",
            ],
            "route_dev_opened": False, "sealed_final_opened": False,
            "provider_cost_usd": "0", "promotion_authorized": False,
        }
        base._atomic_json(output / "scorecard.json", scorecard)
        manifest = {
            "schema": "nfl_market_orthogonal_price_path_train_manifest_v1",
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
            "model_fits": 12, "candidate_fits": 4, "calibration_fits": 4,
            "ordinary_reference_fits": 4, "archived_full_offset_refits": 0,
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
                "schema": "nfl_market_orthogonal_price_path_train_failure_v1",
                "status": "INVALID_DATA_QUALITY" if invalid else "FAILED",
                "error_type": type(error).__name__, "error": str(error)[:1200],
                "fit_started": fit_started, "scoring_started": scoring_started,
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
