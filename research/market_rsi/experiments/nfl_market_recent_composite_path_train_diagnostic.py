#!/usr/bin/env python3
"""Opened-Train Discovery runner for MarketRecentCompositePath-v2.

The candidate uses one recent, market-residualized composite path coefficient.
All five comparison arms are immutable controls from the completed Attempt-1
artifact.  No network/provider client or protected Dev/Final path is present.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

from experiments import nfl_market_orthogonal_price_path_train_diagnostic as prior


calibration = prior.calibration
offset = prior.offset
base = prior.base
SOURCE_ROOT = prior.SOURCE_ROOT
PERSISTENT_ARTIFACT_ROOT = prior.PERSISTENT_ARTIFACT_ROOT
EXPECTED_EVENTS = prior.EXPECTED_EVENTS
EXPECTED_DATES = prior.EXPECTED_DATES
EXPECTED_MATERIALIZED_KEY_SHA256 = prior.EXPECTED_MATERIALIZED_KEY_SHA256
EXPECTED_CHECK_MASK_SHA256 = prior.EXPECTED_CHECK_MASK_SHA256
MAX_STALENESS_SECONDS = prior.MAX_STALENESS_SECONDS
STRICT_WIN_TOLERANCE = prior.STRICT_WIN_TOLERANCE
RECENT_WEEKS = 3
MINIMUM_RECENT_ROWS = 30
EXPECTED_REAL_RECENT = MappingProxyType({
    1: {"weeks": ("2025_05", "2025_06", "2025_07"), "rows": 44,
        "ones": 22, "zeros": 22, "per_week": (14, 15, 15)},
    2: {"weeks": ("2025_06", "2025_07", "2025_08"), "rows": 43,
        "ones": 26, "zeros": 17, "per_week": (15, 15, 13)},
    3: {"weeks": ("2025_08", "2025_09", "2025_10"), "rows": 41,
        "ones": 20, "zeros": 21, "per_week": (13, 14, 14)},
    4: {"weeks": ("2025_10", "2025_11", "2025_12"), "rows": 43,
        "ones": 25, "zeros": 18, "per_week": (14, 15, 14)},
})

EXPECTED_PRIOR_RUNNER_SHA256 = (
    "af4508f0c808fbc236daae6607343c47238db26e2148289a08670fe71102f380"
)
EXPECTED_PRIOR_TEST_SHA256 = (
    "71e576f4a74aba6a334d09f76dc3d2023122b126a0b11ded8b2ddec6e2aad40a"
)
CONTROLLER_PROPOSAL_PATH = (
    Path(__file__).resolve().parents[1]
    / "supervisor_harness"
    / "AGENT_LOG_DISCOVERY_ATTEMPT2_CONTROLLER_2026-09-29.md"
)
EXPECTED_CONTROLLER_PROPOSAL_SHA256 = (
    "2d6f26fa8f83402fea1612297966792d27eba64796c73342170105507a44e061"
)
PRIOR_RESULT_REVIEW_PATH = (
    Path(__file__).resolve().parents[1]
    / "supervisor_harness"
    / "AGENT_LOG_MARKET_ORTHOGONAL_PRICE_PATH_V1_RESULT_INDEPENDENT_REVIEW_2026-09-29.md"
)
EXPECTED_PRIOR_RESULT_REVIEW_SHA256 = (
    "ea42908cbd95c93782a889a4e13f32e4b85009d03a95a1bd044a079117199f83"
)
ARCHIVED_PRIOR_ROOT = PERSISTENT_ARTIFACT_ROOT / (
    "first-real-train-diagnostic-market-orthogonal-price-path-20260929-01"
)
ARCHIVED_PRIOR_SHA256 = MappingProxyType({
    "exclusions.json": "e6ccbe815a5872261d3c07958506a602ed96ca0355913b079a1594c44a91fa3a",
    "input_receipts.json": "51fa298e2f6c7b672aedba1ed3d14aa5542e0f00232498f957a84298578c584d",
    "manifest.json": "e3ec0981f705ec511fa830680ddbe5f2e490e6a6be6eaa58550204de20725da4",
    "pre_score_lock.json": "365416786811f393ffa0e39f808404b8987f67c69b0c7bdce0b498363a51d9f4",
    "predictions.csv": "9d2d15a4a61d91aabc0862809906aebf8be7382dfaa380064676284ecd02dcc6",
    "scorecard.json": "263acc091232f0d3c27a3e4cd8bd0ef7aa392e00f06a0fc89dc6323c2692e4a4",
    "staleness_inventory.json": "3b545bd2542b4a4102ed0aa0f2adaed435322fc58bea06b599ebee765abea10e",
})
ARCHIVED_FIELDS = (*prior.ARCHIVED_FIELDS, "candidate_probability")
CANDIDATE_SPEC = MappingProxyType({
    "name": "MarketRecentCompositePath-v2",
    "candidate_fit_weeks": 3,
    "week_rule": "three_largest_fit_week_labels_strictly_less_than_first_check_week",
    "minimum_recent_rows": 30,
    "raw_families": dict(prior.CANDIDATE_SPEC["raw_families"]),
    "market_residualization": "recent-fit-only OLS against [1,z_market]",
    "lstsq_rcond": 1e-12,
    "rank_required": 2,
    "inactive_fit_population_std_at_most": prior.INACTIVE_STD_THRESHOLD,
    "composite": "restandardize((z_g+z_d)/2) on recent fit only",
    "offset": "unstandardized market logit coefficient fixed at 1",
    "linear_predictor": "eta=market_logit+w_composite*z_composite",
    "objective": "mean Bernoulli NLL plus 0.5*w_composite^2",
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
    "bf8c466e745679e4e1a6861f930659fa4633c41c3445a539634048782ef6ed82"
)
_WEEK_LABEL = re.compile(r"(20[0-9]{2})_([0-9]{2})\Z")


def execution_identity() -> dict:
    return {
        "prior_runner_sha256": base._sha256(Path(prior.__file__)),
        "prior_test_sha256": base._sha256(
            Path(__file__).resolve().parents[1]
            / "tests"
            / "test_nfl_market_orthogonal_price_path_train_diagnostic.py"
        ),
        "controller_proposal_path": str(CONTROLLER_PROPOSAL_PATH),
        "controller_proposal_sha256": base._sha256(CONTROLLER_PROPOSAL_PATH),
        "prior_result_review_path": str(PRIOR_RESULT_REVIEW_PATH),
        "prior_result_review_sha256": base._sha256(PRIOR_RESULT_REVIEW_PATH),
        "runtime_and_deeper_dependencies": prior._validate_execution_identity(),
    }


def _validate_execution_identity() -> dict:
    identity = execution_identity()
    expected = {
        "prior_runner_sha256": EXPECTED_PRIOR_RUNNER_SHA256,
        "prior_test_sha256": EXPECTED_PRIOR_TEST_SHA256,
        "controller_proposal_sha256": EXPECTED_CONTROLLER_PROPOSAL_SHA256,
        "prior_result_review_sha256": EXPECTED_PRIOR_RESULT_REVIEW_SHA256,
    }
    if any(identity[name] != value for name, value in expected.items()):
        raise RuntimeError(f"frozen execution identity changed: {identity}")
    return identity


def _validate_frozen_specs() -> None:
    prior._validate_frozen_specs()
    observed = base._digest(dict(CANDIDATE_SPEC))
    if observed != EXPECTED_CANDIDATE_SPEC_SHA256:
        raise RuntimeError(f"recent composite candidate spec changed: {observed}")


def validate_archived_prior_artifact(root: Path, *, verify_frozen_hashes: bool) -> dict:
    root = Path(root).resolve()
    observed = {path.name for path in root.iterdir() if path.is_file()}
    if observed != set(ARCHIVED_PRIOR_SHA256):
        raise ValueError("archived Attempt-1 artifact file set differs")
    hashes = {name: base._sha256(root / name) for name in sorted(observed)}
    if verify_frozen_hashes and hashes != dict(ARCHIVED_PRIOR_SHA256):
        raise ValueError("archived Attempt-1 artifact hash changed")
    manifest = base._strict_json(root / "manifest.json")
    if (not isinstance(manifest, dict)
            or manifest.get("schema") != "nfl_market_orthogonal_price_path_train_manifest_v1"
            or manifest.get("complete") is not True
            or manifest.get("status") != "COMPLETE"
            or manifest.get("provider_cost_usd") != "0"
            or manifest.get("route_dev_opened") is not False
            or manifest.get("sealed_final_opened") is not False
            or manifest.get("external_fetch") is not False
            or manifest.get("paid_provider") is not False):
        raise ValueError("archived Attempt-1 manifest boundary failed")
    bindings = {
        "pre_score_lock.json": manifest.get("pre_score_lock_sha256"),
        "input_receipts.json": manifest.get("input_receipts_sha256"),
        "exclusions.json": manifest.get("exclusions_sha256"),
        "staleness_inventory.json": manifest.get("staleness_inventory_sha256"),
        "predictions.csv": manifest.get("predictions_sha256"),
        "scorecard.json": manifest.get("scorecard_sha256"),
    }
    if any(hashes[name] != value for name, value in bindings.items()):
        raise ValueError("archived Attempt-1 manifest hash binding failed")
    return {"artifact_root": str(root), "artifact_hashes": hashes}


def _invalid_recent(reason: str, **detail: object) -> None:
    raise offset.InvalidDataQuality(
        f"INVALID_DATA_QUALITY: recent composite {reason}",
        {
            **detail,
            "schema": "nfl_market_recent_composite_invalid_v1",
            "status": "INVALID_DATA_QUALITY",
            "stage": "recent_candidate_selection_or_transform",
            "reason": reason,
        },
    )


def _week_key(label: str) -> tuple[int, int]:
    match = _WEEK_LABEL.fullmatch(label)
    if not match:
        _invalid_recent("invalid_game_week_label", label=label)
    return int(match.group(1)), int(match.group(2))


def select_recent_candidate_rows(
        fit_rows: Sequence[base.DiagnosticRow],
        check_rows: Sequence[base.DiagnosticRow], *,
        minimum_rows: int = MINIMUM_RECENT_ROWS,
        expected: Mapping[str, object] | None = None) -> dict:
    if not fit_rows or not check_rows:
        _invalid_recent("empty_fit_or_check_rows")
    check_weeks = sorted(
        {offset.game_week(row.game_id) for row in check_rows}, key=_week_key
    )
    first_check_week = check_weeks[0]
    eligible_weeks = sorted({
        offset.game_week(row.game_id) for row in fit_rows
        if _week_key(offset.game_week(row.game_id)) < _week_key(first_check_week)
    }, key=_week_key)
    if len(eligible_weeks) < RECENT_WEEKS:
        _invalid_recent(
            "fewer_than_three_strictly_prior_weeks",
            eligible_weeks=eligible_weeks, first_check_week=first_check_week,
        )
    selected_weeks = tuple(eligible_weeks[-RECENT_WEEKS:])
    selected = sorted(
        [row for row in fit_rows if offset.game_week(row.game_id) in selected_weeks],
        key=lambda row: row.key,
    )
    older = sorted([
        row for row in fit_rows
        if _week_key(offset.game_week(row.game_id)) < _week_key(first_check_week)
        and row not in selected
    ], key=lambda row: row.key)
    ineligible_same_or_later_week = sorted([
        row for row in fit_rows
        if _week_key(offset.game_week(row.game_id)) >= _week_key(first_check_week)
    ], key=lambda row: row.key)
    ones = sum(int(row.trusted["outcome"]) for row in selected)
    report = {
        "first_check_week": first_check_week,
        "check_week_labels": check_weeks,
        "eligible_strictly_prior_week_labels": eligible_weeks,
        "selected_week_labels": selected_weeks,
        "selected_rows": len(selected),
        "selected_ones": ones,
        "selected_zeros": len(selected) - ones,
        "selected_rows_per_week": tuple(
            sum(offset.game_week(row.game_id) == week for row in selected)
            for week in selected_weeks
        ),
        "older_fit_rows": len(older),
        "older_fit_week_labels": sorted(
            {offset.game_week(row.game_id) for row in older}, key=_week_key
        ),
        "ineligible_same_or_later_week_rows": len(ineligible_same_or_later_week),
        "ineligible_same_or_later_week_labels": sorted(
            {offset.game_week(row.game_id) for row in ineligible_same_or_later_week},
            key=_week_key,
        ),
    }
    if len(selected) < minimum_rows:
        _invalid_recent("fewer_than_minimum_recent_rows", minimum_rows=minimum_rows,
                        **report)
    if ones == 0 or ones == len(selected):
        _invalid_recent("recent_rows_lack_both_outcome_classes", **report)
    first_check_cutoff = min(row.trusted["cutoff_ms"] for row in check_rows)
    unavailable = [
        row.game_id for row in selected
        if row.trusted["outcome_available_ms"] >= first_check_cutoff
    ]
    if unavailable:
        _invalid_recent("recent_outcome_not_strictly_available", events=unavailable,
                        **report)
    if expected is not None:
        observed = {
            "weeks": selected_weeks, "rows": len(selected), "ones": ones,
            "zeros": len(selected) - ones,
            "per_week": report["selected_rows_per_week"],
        }
        if observed != dict(expected):
            _invalid_recent("exact_real_recent_cohort_mismatch",
                            observed=observed, expected=dict(expected))
    return {
        "selected_rows": selected, "older_rows": older,
        "ineligible_same_or_later_week_rows": ineligible_same_or_later_week,
        "report": report,
    }


def _apply_prior_transform(rows: Sequence[base.DiagnosticRow], params: Mapping[str, object]
                           ) -> dict:
    logits = calibration._market_logits(rows)
    mu = float(params["market_scaler_mean"])
    scale = float(params["market_scaler_scale"])
    if not math.isfinite(mu) or not math.isfinite(scale) or scale <= 0:
        _invalid_recent("invalid_market_scaler")
    z_market = (logits - mu) / scale
    raw = prior.price_path_families(rows)
    beta = np.asarray(params["residualization_beta_rows_intercept_market"], dtype=np.float64)
    residual = raw - np.column_stack((np.ones(len(rows)), z_market)) @ beta
    means = np.asarray(params["residual_fit_means_g_d"], dtype=np.float64)
    scales = np.asarray(params["residual_fit_population_stds_g_d"], dtype=np.float64)
    inactive = np.asarray(params["inactive_families_g_d"], dtype=bool)
    standardized = np.zeros_like(residual)
    for column in range(2):
        if not inactive[column]:
            standardized[:, column] = (residual[:, column] - means[column]) / scales[column]
    if any(not np.all(np.isfinite(value)) for value in
           (logits, z_market, raw, residual, standardized)):
        _invalid_recent("nonfinite_applied_transform", rows=len(rows))
    return {
        "logits": logits, "raw": raw, "residual": residual,
        "z_family": standardized,
    }


def fit_recent_composite_transform(
        selected_rows: Sequence[base.DiagnosticRow],
        older_rows: Sequence[base.DiagnosticRow],
        check_rows: Sequence[base.DiagnosticRow]) -> dict:
    transformed = prior.fit_price_path_transform(selected_rows, check_rows)
    params = dict(transformed["parameters"])
    selected = {
        "logits": transformed["fit_logits"], "raw": transformed["raw_fit"],
        "residual": transformed["residual_fit"],
        "z_family": transformed["z_family_fit"],
    }
    check = {
        "logits": transformed["check_logits"], "raw": transformed["raw_check"],
        "residual": transformed["residual_check"],
        "z_family": transformed["z_family_check"],
    }
    older = _apply_prior_transform(older_rows, params) if older_rows else {
        "logits": np.asarray([], dtype=np.float64),
        "raw": np.empty((0, 2), dtype=np.float64),
        "residual": np.empty((0, 2), dtype=np.float64),
        "z_family": np.empty((0, 2), dtype=np.float64),
    }
    composite_fit_raw = np.mean(selected["z_family"], axis=1)
    composite_mu = float(np.mean(composite_fit_raw))
    composite_scale = float(np.std(composite_fit_raw, ddof=0))
    composite_inactive = bool(
        all(params["inactive_families_g_d"])
        or composite_scale <= prior.INACTIVE_STD_THRESHOLD
    )
    if not math.isfinite(composite_mu) or not math.isfinite(composite_scale):
        _invalid_recent("nonfinite_composite_moments")
    raw_means = np.mean(selected["raw"], axis=0)
    raw_scales = np.std(selected["raw"], axis=0, ddof=0)
    raw_active = raw_scales > prior.INACTIVE_STD_THRESHOLD
    for group in (selected, older, check):
        raw_standardized = np.zeros_like(group["raw"])
        for column in range(2):
            if raw_active[column]:
                raw_standardized[:, column] = (
                    group["raw"][:, column] - raw_means[column]
                ) / raw_scales[column]
        group["raw_composite_diagnostic"] = (
            np.mean(raw_standardized, axis=1)
            if len(raw_standardized) else np.asarray([], dtype=np.float64)
        )
        raw_composite = (
            np.mean(group["z_family"], axis=1)
            if len(group["z_family"]) else np.asarray([], dtype=np.float64)
        )
        group["composite_raw"] = raw_composite
        group["z_composite"] = (
            np.zeros_like(raw_composite) if composite_inactive
            else (raw_composite - composite_mu) / composite_scale
        )
        if not np.all(np.isfinite(group["z_composite"])):
            _invalid_recent("nonfinite_composite_output")
    params.update({
        "composite_fit_mean": composite_mu,
        "composite_fit_population_std": composite_scale,
        "composite_inactive": composite_inactive,
        "composite_formula": "restandardize((z_g+z_d)/2)",
        "diagnostic_raw_family_means_g_d": [float(value) for value in raw_means],
        "diagnostic_raw_family_population_stds_g_d": [
            float(value) for value in raw_scales
        ],
    })
    z_market_fit = (
        selected["logits"] - float(params["market_scaler_mean"])
    ) / float(params["market_scaler_scale"])
    params["selected_fit_residual_orthogonality"] = {
        "absolute_residual_means_g_d": [
            abs(float(value)) for value in np.mean(selected["residual"], axis=0)
        ],
        "absolute_mean_z_market_times_residual_g_d": [
            abs(float(value)) for value in np.mean(
                z_market_fit[:, None] * selected["residual"], axis=0
            )
        ],
    }
    return {"selected": selected, "older": older, "check": check,
            "parameters": params}


def recent_objective_gradient(parameter: object, z_composite: object,
                              outcomes: object, market_logits: object
                              ) -> tuple[float, np.ndarray]:
    coefficient = np.asarray(parameter, dtype=np.float64)
    z = np.asarray(z_composite, dtype=np.float64)
    labels = np.asarray(outcomes, dtype=np.float64)
    logits = np.asarray(market_logits, dtype=np.float64)
    if coefficient.shape != (1,) or not np.all(np.isfinite(coefficient)):
        raise ValueError("coefficient must be one finite value")
    if (z.ndim != 1 or not len(z) or labels.shape != z.shape or logits.shape != z.shape
            or not np.all(np.isfinite(z)) or not np.all(np.isfinite(labels))
            or not np.all(np.isfinite(logits)) or not np.all(np.isin(labels, (0, 1)))):
        raise ValueError("recent objective inputs must be aligned finite binary rows")
    eta = logits + coefficient[0] * z
    probabilities = expit(eta)
    objective = float(np.mean(np.logaddexp(0.0, eta) - labels * eta))
    objective += 0.5 * float(coefficient[0] ** 2)
    gradient = np.asarray([
        float(np.mean(z * (probabilities - labels))) + float(coefficient[0])
    ])
    if not math.isfinite(objective) or not np.all(np.isfinite(gradient)):
        raise FloatingPointError("recent objective or gradient is nonfinite")
    return objective, gradient


def recent_probabilities(parameter: object, z_composite: object,
                         market_logits: object,
                         market_probabilities: object) -> np.ndarray:
    coefficient = np.asarray(parameter, dtype=np.float64)
    z = np.asarray(z_composite, dtype=np.float64)
    logits = np.asarray(market_logits, dtype=np.float64)
    market = np.asarray(market_probabilities, dtype=np.float64)
    if (coefficient.shape != (1,) or z.ndim != 1 or logits.shape != z.shape
            or market.shape != z.shape):
        raise ValueError("recent probability inputs have wrong shape")
    if (not np.all(np.isfinite(coefficient)) or not np.all(np.isfinite(z))
            or not np.all(np.isfinite(logits)) or not np.all(np.isfinite(market))
            or np.any(market <= 0) or np.any(market >= 1)):
        raise ValueError("recent probability inputs are nonfinite")
    expected_logits = np.log(market / (1.0 - market))
    if not np.allclose(logits, expected_logits, rtol=0.0, atol=1e-12):
        raise ValueError("market probabilities and logits differ")
    if float(coefficient[0]) == 0.0:
        # Preserve the exact incumbent bytes; expit(logit(p)) is not guaranteed
        # bit-for-bit identical for arbitrary binary64 probabilities.
        return market.copy()
    values = expit(logits + coefficient[0] * z)
    if not np.all(np.isfinite(values)):
        raise FloatingPointError("recent probabilities are nonfinite")
    return np.asarray(values, dtype=np.float64)


def fit_recent_composite(z_composite: object, outcomes: object,
                         market_logits: object) -> tuple[np.ndarray, dict]:
    z = np.asarray(z_composite, dtype=np.float64)
    labels = np.asarray(outcomes, dtype=np.float64)
    logits = np.asarray(market_logits, dtype=np.float64)

    def objective(value: np.ndarray) -> tuple[float, np.ndarray]:
        return recent_objective_gradient(value, z, labels, logits)

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
            "recent optimizer failed frozen convergence checks: "
            f"success={result.success}, objective={final_objective}, grad_inf={grad_inf}"
        )
    return parameter, {
        "success": True, "status": int(result.status),
        "message": str(result.message)[:300], "iterations": int(result.nit),
        "function_evaluations": int(result.nfev), "objective": final_objective,
        "gradient_infinity_norm": grad_inf,
        "parameters": [float(parameter[0])],
    }


def _moments_by(labels: Sequence[str], z: np.ndarray, residual: np.ndarray) -> list[dict]:
    result = []
    for label in sorted(set(labels)):
        mask = np.asarray([value == label for value in labels])
        values = z[mask] * residual[mask]
        result.append({"unit": label, "events": int(np.sum(mask)),
                       "mean_z_times_y_minus_market": float(np.mean(values))})
    return result


def information_diagnostics(group: Mapping[str, np.ndarray],
                            rows: Sequence[base.DiagnosticRow]) -> dict:
    if not rows:
        return {"events": 0, "reason": "no_older_rows"}
    market = np.asarray([row.trusted["market_probability"] for row in rows])
    outcomes = np.asarray([row.trusted["outcome"] for row in rows])
    residual_target = outcomes - market
    families = prior.information_diagnostics(
        group["raw"], group["residual"], group["z_family"], group["logits"],
        outcomes, market, [row.split_date for row in rows],
    )
    z = group["z_composite"]
    raw_composite = group["raw_composite_diagnostic"]
    residual_composite = group["composite_raw"]
    raw_variance = float(np.var(raw_composite, ddof=0))
    residual_variance = float(np.var(residual_composite, ddof=0))
    families["composite"] = {
        "events": len(rows),
        "raw_composite_variance": raw_variance,
        "residual_composite_variance": residual_variance,
        "residual_over_raw_composite_variance_fraction": (
            residual_variance / raw_variance if raw_variance > 0 else None
        ),
        "raw_composite_correlation_with_market_logit": prior._correlation(
            raw_composite, group["logits"]
        ),
        "residual_composite_correlation_with_market_logit": prior._correlation(
            residual_composite, group["logits"]
        ),
        "standardized_composite_variance": float(np.var(z, ddof=0)),
        "pearson_z_with_y_minus_market": prior._correlation(z, residual_target),
        "spearman_z_with_y_minus_market": prior._correlation(
            z, residual_target, rank=True
        ),
        "mean_z_times_y_minus_market": float(np.mean(z * residual_target)),
        "per_schedule_date_moment": _moments_by(
            [row.split_date for row in rows], z, residual_target
        ),
        "per_game_week_moment": _moments_by(
            [offset.game_week(row.game_id) for row in rows], z, residual_target
        ),
    }
    return families


def _breadth(rows: Sequence[base.DiagnosticRow]) -> dict:
    return {
        "rows": len(rows),
        "schedule_dates": len({row.split_date for row in rows}),
        "schedule_date_labels": sorted({row.split_date for row in rows}),
        "game_weeks": len({offset.game_week(row.game_id) for row in rows}),
        "game_week_labels": sorted(
            {offset.game_week(row.game_id) for row in rows}, key=_week_key
        ),
    }


def _fit_and_predict(plan: Sequence[dict], *, minimum_recent_rows: int,
                     enforce_real_counts: bool,
                     phase_state: dict[str, bool]) -> tuple[list[dict], list[dict]]:
    predictions, reports = [], []
    for fold in plan:
        expected = EXPECTED_REAL_RECENT[fold["fold"]] if enforce_real_counts else None
        selection = select_recent_candidate_rows(
            fold["fit_rows"], fold["check_rows"], minimum_rows=minimum_recent_rows,
            expected=expected,
        )
        selected, older = selection["selected_rows"], selection["older_rows"]
        transformed = fit_recent_composite_transform(
            selected, older, fold["check_rows"]
        )
        selected_diagnostics = information_diagnostics(
            transformed["selected"], selected
        )
        labels = np.asarray([row.trusted["outcome"] for row in selected])
        phase_state["fit_started"] = True
        parameter, optimizer = fit_recent_composite(
            transformed["selected"]["z_composite"], labels,
            transformed["selected"]["logits"],
        )
        candidate_values = recent_probabilities(
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
                "selected_recent_fit": _breadth(selected),
                "older_eligible_fit": _breadth(older),
                "ineligible_same_or_later_week_fit": _breadth(
                    selection["ineligible_same_or_later_week_rows"]
                ),
                "check": _breadth(fold["check_rows"]),
            },
            "transform_parameters": transformed["parameters"],
            "selected_recent_fit_information": selected_diagnostics,
            "older_fit_information": information_diagnostics(transformed["older"], older),
            "check_information": information_diagnostics(
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
                           predictions_csv: Path,
                           *, verify_frozen_hash: bool) -> dict:
    if (verify_frozen_hash and base._sha256(predictions_csv)
            != ARCHIVED_PRIOR_SHA256["predictions.csv"]):
        raise ValueError("archived Attempt-1 predictions hash changed")
    with Path(predictions_csv).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != ARCHIVED_FIELDS:
            raise ValueError("archived Attempt-1 prediction schema changed")
        archived = list(reader)
    if len(archived) != len(predictions):
        raise ValueError("archived Attempt-1 row count differs")
    arm_columns = {
        "ordinary": "ordinary_probability",
        "market_only_calibration": "market_only_calibration_probability",
        "archived_full_offset": "archived_full_offset_probability",
        "archived_attempt1": "candidate_probability",
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
            raise ValueError("archived Attempt-1 identity/order/outcome differs")
        if row.trusted["market_probability"] != float(control["market_probability"]):
            raise ValueError("archived Attempt-1 market probability differs")
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
        "control_probability_source": "immutable archived Attempt-1 predictions",
    }


def _pair_score(rows: Sequence[base.DiagnosticRow], left: Sequence[dict],
                left_name: str, right_name: str,
                *, right: Sequence[dict] | None = None) -> dict:
    return calibration._pair_score(rows, left, left_name, right_name, right=right)


def corrected_grouped_inference(predictions: Sequence[dict]) -> dict:
    outcomes = [item["row"].trusted["outcome"] for item in predictions]
    arms = {
        "market": [item["row"].trusted["market_probability"] for item in predictions],
        **{name: [item[name]["probability"] for item in predictions] for name in (
            "ordinary", "market_only_calibration", "archived_full_offset",
            "archived_attempt1", "candidate",
        )},
    }
    comparisons = {
        f"candidate_minus_{right}": ("candidate", right) for right in (
            "market", "ordinary", "market_only_calibration",
            "archived_full_offset", "archived_attempt1",
        )
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
    fields = (*ARCHIVED_FIELDS, "recent_composite_candidate_probability")
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
                "recent_composite_candidate_probability": item["candidate"]["probability"],
            })
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def run(source_root: Path, output: Path, *, expected_events: int = EXPECTED_EVENTS,
        expected_dates: int = EXPECTED_DATES, allow_test_paths: bool = False,
        generated_utc: str | None = None, archived_prior_root: Path | None = None,
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
        archive_root = Path(archived_prior_root or ARCHIVED_PRIOR_ROOT).resolve()
        archive_binding = validate_archived_prior_artifact(
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
            "schema": "nfl_market_recent_composite_path_train_inputs_v1",
            "source_dataset_id": source_root.name,
            "source_manifest_sha256": base._sha256(source_root / "manifest.json"),
            "cohort_sha256": base._sha256(source_root / "cohort.csv"),
            "source_events": expected_events, "source_dates": expected_dates,
            "runner_source_sha256": base._sha256(Path(__file__)),
            "execution_identity": identity, "archived_prior_binding": archive_binding,
            "all_source_file_receipts": source_file_receipts,
            "materialized_event_receipts": [row.source_receipt for row in materialized],
            "route_dev_opened": False, "sealed_final_opened": False,
            "provider_cost_usd": "0",
        }
        exclusions_doc = {
            "schema": "nfl_market_recent_composite_path_train_exclusions_v1",
            "source_events": expected_events, "materialized_events": len(materialized),
            "excluded_events": len(exclusions),
            "reconciles_to_source_denominator": len(materialized) + len(exclusions) == expected_events,
            "exclusions": exclusions,
        }
        base._atomic_json(output / "input_receipts.json", inputs)
        base._atomic_json(output / "exclusions.json", exclusions_doc)
        lock = {
            "schema": "nfl_market_recent_composite_path_train_pre_score_lock_v1",
            "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "problem": "test one recent three-week composite path correction anchored exactly to market",
            "domain": "2025 NFL two-outcome moneyline opened Train Discovery",
            "source_manifest_sha256": inputs["source_manifest_sha256"],
            "cohort_sha256": inputs["cohort_sha256"],
            "input_receipts_sha256": base._sha256(output / "input_receipts.json"),
            "exclusions_sha256": base._sha256(output / "exclusions.json"),
            "staleness_inventory_sha256": base._sha256(output / "staleness_inventory.json"),
            "controller_provenance": {
                "proposal_path": str(CONTROLLER_PROPOSAL_PATH),
                "proposal_sha256": EXPECTED_CONTROLLER_PROPOSAL_SHA256,
                "backend_slug_independently_queried": False,
                "adaptive_discovery_disclosure": (
                    "Attempt-2 selection used repeatedly inspected Attempt-1 "
                    "aggregate, fold, date, week and per-family label-dependent "
                    "diagnostics plus a new read-only label-dependent recent-window "
                    "signed-moment inventory; it is not aggregate-only or untouched"
                ),
            },
            "execution_identity": identity, "archived_prior_binding": archive_binding,
            "source_events": expected_events, "source_dates": expected_dates,
            "materialized_key_sha256": materialized_hash,
            "canonical_check_mask_sha256": EXPECTED_CHECK_MASK_SHA256 if not allow_test_paths else None,
            "decision_cutoff": "event_start_utc minus 15 minutes",
            "max_staleness_seconds": MAX_STALENESS_SECONDS,
            "folds": folds, "candidate_spec": dict(CANDIDATE_SPEC),
            "candidate_spec_sha256": base._digest(dict(CANDIDATE_SPEC)),
            "expected_real_recent_cohorts": {
                str(key): dict(value) for key, value in EXPECTED_REAL_RECENT.items()
            },
            "model_fits": {"candidate": 4, "all_archived_controls": 0},
            "archive_only_controls": [
                "market", "ordinary_reference", "market_only_calibration",
                "full_offset", "MarketOrthogonalPricePath-v1",
            ],
            "event_weighting": "one row per event; equal event weight",
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
        records = {name: [item[name] for item in predictions] for name in (
            "ordinary", "market_only_calibration", "archived_full_offset",
            "archived_attempt1", "candidate",
        )}
        scoring_started = True
        pairwise = {}
        for right in ("market", "ordinary", "market_only_calibration",
                      "archived_full_offset", "archived_attempt1"):
            pairwise[f"candidate_minus_{right}"] = _pair_score(
                check_rows, records["candidate"], "candidate", right,
                right=None if right == "market" else records[right],
            )
        for arm in ("ordinary", "market_only_calibration", "archived_full_offset",
                    "archived_attempt1"):
            pairwise[f"{arm}_minus_market"] = _pair_score(
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
            **{arm: arm_from(f"{arm}_minus_market", "candidate") for arm in (
                "ordinary", "market_only_calibration", "archived_full_offset",
                "archived_attempt1",
            )},
            "pairwise_deltas": {name: value["equal_event_delta"] for name, value in pairwise.items()},
        }
        decision, conditions = offset.diagnostic_keep(
            aggregate["candidate"], aggregate["market"], aggregate["ordinary"],
            [fold["market"]["brier"] - fold["candidate"]["brier"] > STRICT_WIN_TOLERANCE for fold in fold_reports],
            [fold["ordinary"]["brier"] - fold["candidate"]["brier"] > STRICT_WIN_TOLERANCE for fold in fold_reports],
        )
        branch_diagnostics = {}
        for arm in ("market_only_calibration", "archived_attempt1"):
            branch_diagnostics[f"candidate_vs_{arm}"] = {
                "beats_aggregate_brier": aggregate[arm]["brier"] - aggregate["candidate"]["brier"] > STRICT_WIN_TOLERANCE,
                "beats_aggregate_log_loss": aggregate[arm]["log_loss"] - aggregate["candidate"]["log_loss"] > STRICT_WIN_TOLERANCE,
                "fold_brier_wins": [fold[arm]["brier"] - fold["candidate"]["brier"] > STRICT_WIN_TOLERANCE for fold in fold_reports],
            }
        _write_predictions(output / "predictions.csv", predictions)
        scorecard = {
            "schema": "nfl_market_recent_composite_path_train_scorecard_v1",
            "diagnostic_decision": decision,
            "decision_scope": "replace current best for further Discovery only",
            "keep_conditions": conditions, "branch_diagnostics": branch_diagnostics,
            "source_denominator": {"events": expected_events, "dates": expected_dates,
                                   "materialized_events": len(materialized),
                                   "excluded_events": len(exclusions),
                                   "check_events": len(check_rows),
                                   "check_dates": len({row.split_date for row in check_rows}),
                                   "check_game_weeks": len({offset.game_week(row.game_id) for row in check_rows})},
            "arms": {
                "market": "decision-time market probability",
                "ordinary": "archived ordinary LogisticRegression reference",
                "market_only_calibration": "archived calibration control",
                "archived_full_offset": "archived full-offset control",
                "archived_attempt1": "archived MarketOrthogonalPricePath-v1",
                "candidate": "MarketRecentCompositePath-v2",
            },
            "control_parity": parity,
            "identical_masks": {"all_arms_share_one_complete_mask": True,
                                "mask_sha256": masks},
            "aggregate": aggregate, "folds": fold_reports,
            "pairwise_proper_scores": pairwise,
            "corrected_grouped_inference": corrected_grouped_inference(predictions),
            "incumbent_and_branch_semantics": {
                "current_best_before_run": "decision-time market probability",
                "current_best_after_run": "MarketRecentCompositePath-v2" if decision == "KEEP" else "decision-time market probability",
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
            "schema": "nfl_market_recent_composite_path_train_manifest_v1",
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
                "schema": "nfl_market_recent_composite_path_train_failure_v1",
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
