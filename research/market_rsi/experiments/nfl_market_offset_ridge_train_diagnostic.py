#!/usr/bin/env python3
"""Train-only diagnostic for the frozen MarketOffsetRidgeLogistic-v1 recipe.

This runner reuses the reviewed settlement-probability materializer, temporal
folds, probability contract, and proper scorer.  It has no network/provider
client and cannot open Route-Dev or Final.  Reused Train checks are Discovery,
not untouched out-of-sample evidence and not promotion authorization.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import re
import sys
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

import numpy as np
import scipy
from scipy.optimize import minimize
from scipy.special import expit
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from experiments import nfl_settlement_probability_train_diagnostic as base
from minimal_prediction_loop import probability_contract, proper_scoring
from minimal_prediction_loop.probability_contract import validate_train_evaluation_rows
from minimal_prediction_loop.proper_scoring import bounded_log_loss, brier_loss


SOURCE_ROOT = base.SOURCE_ROOT
PERSISTENT_ARTIFACT_ROOT = base.PERSISTENT_ARTIFACT_ROOT
EXPECTED_EVENTS = base.EXPECTED_EVENTS
EXPECTED_DATES = base.EXPECTED_DATES
MAX_STALENESS_SECONDS = 600.0
BOOTSTRAP_SEED = 23
BOOTSTRAP_REPLICATES = 1000
STRICT_WIN_TOLERANCE = 1e-12
EXPECTED_PARENT_RUNNER_SHA256 = (
    "1f1bdccd69d799be1af99ece4ee6198ffbd02f3a4550e651936fb3edfa83fb8b"
)
EXPECTED_PARENT_TEST_SHA256 = (
    "6c349018fb28abcfcea825bec5cb8c9e2702d46e15712e30c9e66d5fb9785927"
)
EXPECTED_PROPER_SCORER_SHA256 = (
    "64165cbceb4bcba6d03b6b42402ea7a47790c9a57f9280b15bfe2fe57becc06b"
)
EXPECTED_PROBABILITY_CONTRACT_SHA256 = (
    "7ba4a32d3c3a2ab80ac17ca6c18ea29fe864b958de8a81ac2be59dba121e9d74"
)
CONTROLLER_PROPOSAL_PATH = (
    Path(__file__).resolve().parents[1]
    / "supervisor_harness"
    / "AGENT_LOG_FIRST_REAL_TRAIN_NEXT_HYPOTHESIS_2026-09-29.md"
)
EXPECTED_CONTROLLER_PROPOSAL_SHA256 = (
    "7345349cb0560a23e447b1e89b83e1c3de49adec6b1ada967a5a909ff1ab1314"
)
EXPECTED_RUNTIME = MappingProxyType({
    "executable": (
        "/Users/estelle/Library/Application Support/MarketRSI/"
        "runtime-py312/bin/python"
    ),
    "implementation": "CPython",
    "python_version": "3.12.3",
    "numpy_version": "1.26.4",
    "scipy_version": "1.14.0",
    "sklearn_version": "1.6.1",
})
EXPECTED_MATERIALIZED_KEY_SHA256 = (
    "59128473ae6c50b4acd2436ac18478d4fcd7dbd96ee887eb5ce2ae77ddfc72bd"
)
EXPECTED_CHECK_MASK_SHA256 = (
    "eddf8cc9509a3121a884143e9c9d24e2e85c72283957f446b1b44fd0bfc341cb"
)
EXPECTED_REAL_FOLD_COUNTS = ((107, 26), (133, 16), (149, 28), (177, 17))
PARENT_ARTIFACT_ROOT = PERSISTENT_ARTIFACT_ROOT / (
    "first-real-train-diagnostic-nfl-settlement-20260929-02"
)
PARENT_ARTIFACT_SHA256 = MappingProxyType({
    "pre_score_lock.json": (
        "1f54eb27bc22a728c67d161a512ccab0a5fa38f20c28aa6ee11f5b57f7489019"
    ),
    "manifest.json": (
        "a36bce7debb71333caa7b35afebeaf9e7adcdd0e07c1679fbf70369dffa6bcb4"
    ),
    "scorecard.json": (
        "98f78e0bc68f7743881d285560b5fbc1a9a6b74b5178601ff6fc4201128fb710"
    ),
    "predictions.csv": (
        "f91647a2a5b84836bd717ce2d0c6fd404bc1f4a759342a8b8d40fc6e576f37c1"
    ),
    "exclusions.json": (
        "cf61302708a6535b892232d3cf499575e3a8909a4aad1e8de1a0b7959a0164bd"
    ),
})
CANDIDATE_SPEC = MappingProxyType({
    "name": "MarketOffsetRidgeLogistic-v1",
    "offset": "unstandardized_market_logit_coefficient_1",
    "residual_inputs": (
        "all_17_unchanged_fold_standardized_features_plus_intercept"
    ),
    "objective": (
        "mean_bernoulli_nll_plus_0.5_lambda_times_squared_l2_all_18_parameters"
    ),
    "lambda": 1.0,
    "penalize_intercept": True,
    "initial_parameters": "all_zero",
    "optimizer": "scipy.optimize.minimize_L-BFGS-B",
    "jac": "analytic",
    "maxiter": 1000,
    "gtol": 1e-8,
    "ftol": 1e-12,
    "dtype": "float64",
    "probability_policy": "existing_reject_outside_1e-6_to_1_minus_1e-6",
    "hyperparameter_search": False,
})
EXPECTED_CANDIDATE_SPEC_SHA256 = (
    "70dc3f086f704e01bb90cabd54bb817b6fccf6765e17ff28aa0d19d97ccdd1f1"
)
EXPECTED_ORDINARY_SPEC_SHA256 = (
    "0759b88c679597203ca981abe8c60919eec35b8d621c6534518baaaa4c287752"
)
EXPECTED_FEATURE_SPEC_SHA256 = (
    "bac49f83adbdff4e775474d820d7f1d5b8029de563c82fabb2cf046b74123cab"
)
_GAME_WEEK = re.compile(r"(20[0-9]{2})_([0-9]{2})_[A-Z]{2,3}_[A-Z]{2,3}\Z")


class InvalidDataQuality(ValueError):
    """A common input gate failed before any model fit or score."""

    def __init__(self, message: str, report: dict):
        super().__init__(message)
        self.report = report


def _feature_spec() -> dict:
    return {
        "names": base.FEATURE_NAMES,
        "windows_seconds": base.WINDOW_SECONDS,
        "missing": "exclude_without_imputation",
        "orientation": {key: list(value) for key, value in base.TEAM_NAMES.items()},
    }


def _validate_frozen_specs() -> None:
    observed = {
        "candidate": base._digest(dict(CANDIDATE_SPEC)),
        "ordinary": base._digest(dict(base.ORDINARY_SPEC)),
        "feature": base._digest(_feature_spec()),
    }
    expected = {
        "candidate": EXPECTED_CANDIDATE_SPEC_SHA256,
        "ordinary": EXPECTED_ORDINARY_SPEC_SHA256,
        "feature": EXPECTED_FEATURE_SPEC_SHA256,
    }
    if observed != expected:
        raise RuntimeError(f"frozen spec digest mismatch: {observed}")


def execution_identity() -> dict:
    return {
        "executable": sys.executable,
        "implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_version_full": sys.version,
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "sklearn_version": sklearn.__version__,
        "parent_runner_sha256": base._sha256(Path(base.__file__)),
        "parent_test_sha256": base._sha256(
            Path(__file__).resolve().parents[1]
            / "tests"
            / "test_nfl_settlement_probability_train_diagnostic.py"
        ),
        "proper_scorer_sha256": base._sha256(Path(proper_scoring.__file__)),
        "probability_contract_sha256": base._sha256(
            Path(probability_contract.__file__)
        ),
        "controller_proposal_path": str(CONTROLLER_PROPOSAL_PATH),
        "controller_proposal_sha256": base._sha256(CONTROLLER_PROPOSAL_PATH),
    }


def _validate_execution_identity() -> dict:
    identity = execution_identity()
    expected = {
        **dict(EXPECTED_RUNTIME),
        "parent_runner_sha256": EXPECTED_PARENT_RUNNER_SHA256,
        "parent_test_sha256": EXPECTED_PARENT_TEST_SHA256,
        "proper_scorer_sha256": EXPECTED_PROPER_SCORER_SHA256,
        "probability_contract_sha256": EXPECTED_PROBABILITY_CONTRACT_SHA256,
        "controller_proposal_path": str(CONTROLLER_PROPOSAL_PATH),
        "controller_proposal_sha256": EXPECTED_CONTROLLER_PROPOSAL_SHA256,
    }
    observed = {key: identity[key] for key in expected}
    if observed != expected:
        raise RuntimeError(
            f"frozen source/runtime identity mismatch: expected={expected}, "
            f"observed={observed}"
        )
    return identity


def _as_float64_matrix(values: object, label: str) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64)
    if result.ndim != 2 or result.shape[0] == 0 or not np.all(np.isfinite(result)):
        raise ValueError(f"{label} must be a nonempty finite float64 matrix")
    return result


def _as_binary_vector(values: object, rows: int) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64)
    if (result.shape != (rows,) or not np.all(np.isfinite(result))
            or not np.all(np.isin(result, (0.0, 1.0)))):
        raise ValueError("outcomes must be one finite binary value per row")
    return result


def offset_objective_gradient(
        parameters: object, standardized_features: object, outcomes: object,
        market_logits: object, *, penalty_lambda: float = 1.0,
        ) -> tuple[float, np.ndarray]:
    """Return frozen mean-NLL plus all-parameter ridge objective and gradient."""
    features = _as_float64_matrix(standardized_features, "standardized features")
    labels = _as_binary_vector(outcomes, features.shape[0])
    offsets = np.asarray(market_logits, dtype=np.float64)
    theta = np.asarray(parameters, dtype=np.float64)
    if offsets.shape != (features.shape[0],) or not np.all(np.isfinite(offsets)):
        raise ValueError("market logits must be one finite value per row")
    if theta.shape != (features.shape[1] + 1,) or not np.all(np.isfinite(theta)):
        raise ValueError("parameter vector has the wrong shape or is nonfinite")
    if not math.isfinite(float(penalty_lambda)) or penalty_lambda < 0:
        raise ValueError("penalty lambda must be finite and nonnegative")
    linear = offsets + theta[0] + features @ theta[1:]
    objective = (
        float(np.mean(np.logaddexp(0.0, linear) - labels * linear))
        + 0.5 * float(penalty_lambda) * float(theta @ theta)
    )
    residual = expit(linear) - labels
    gradient = np.empty_like(theta)
    gradient[0] = float(np.mean(residual))
    gradient[1:] = features.T @ residual / features.shape[0]
    gradient += float(penalty_lambda) * theta
    if not math.isfinite(objective) or not np.all(np.isfinite(gradient)):
        raise FloatingPointError("offset objective or analytic gradient is nonfinite")
    return objective, gradient


def offset_probabilities(parameters: object, standardized_features: object,
                         market_logits: object) -> np.ndarray:
    features = _as_float64_matrix(standardized_features, "standardized features")
    theta = np.asarray(parameters, dtype=np.float64)
    offsets = np.asarray(market_logits, dtype=np.float64)
    if theta.shape != (features.shape[1] + 1,):
        raise ValueError("parameter vector has the wrong shape")
    if offsets.shape != (features.shape[0],):
        raise ValueError("market logits have the wrong shape")
    if not np.all(np.isfinite(theta)) or not np.all(np.isfinite(offsets)):
        raise ValueError("parameters and market logits must be finite")
    probabilities = expit(offsets + theta[0] + features @ theta[1:])
    if not np.all(np.isfinite(probabilities)):
        raise FloatingPointError("candidate probabilities are nonfinite")
    return np.asarray(probabilities, dtype=np.float64)


def fit_offset_ridge(standardized_fit: object, outcomes: object,
                     fit_market_logits: object) -> tuple[np.ndarray, dict]:
    features = _as_float64_matrix(standardized_fit, "standardized fit features")
    labels = _as_binary_vector(outcomes, features.shape[0])
    offsets = np.asarray(fit_market_logits, dtype=np.float64)
    if offsets.shape != (features.shape[0],) or not np.all(np.isfinite(offsets)):
        raise ValueError("fit market logits must be finite and aligned")

    def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
        return offset_objective_gradient(theta, features, labels, offsets)

    initial = np.zeros(features.shape[1] + 1, dtype=np.float64)
    result = minimize(
        objective,
        initial,
        method="L-BFGS-B",
        jac=True,
        options={"maxiter": 1000, "gtol": 1e-8, "ftol": 1e-12},
    )
    parameters = np.asarray(result.x, dtype=np.float64)
    final_objective, final_gradient = objective(parameters)
    gradient_infinity_norm = float(np.max(np.abs(final_gradient)))
    if (not bool(result.success) or not math.isfinite(final_objective)
            or not np.all(np.isfinite(parameters))
            or not np.all(np.isfinite(final_gradient))
            or gradient_infinity_norm > 1e-6):
        raise RuntimeError(
            "offset optimizer failed frozen convergence checks: "
            f"success={result.success}, status={result.status}, "
            f"objective={final_objective}, grad_inf={gradient_infinity_norm}, "
            f"message={str(result.message)[:300]}"
        )
    return parameters, {
        "success": True,
        "status": int(result.status),
        "message": str(result.message)[:300],
        "iterations": int(result.nit),
        "function_evaluations": int(result.nfev),
        "objective": final_objective,
        "gradient_infinity_norm": gradient_infinity_norm,
        "parameters": [float(value) for value in parameters],
    }


def staleness_inventory(rows: Sequence[base.DiagnosticRow],
                        source_ordinals: Mapping[str, int],
                        *, limit_seconds: float = MAX_STALENESS_SECONDS) -> dict:
    if not math.isfinite(limit_seconds) or limit_seconds < 0:
        raise ValueError("staleness limit must be finite and nonnegative")
    ages = []
    violations = []
    for row in rows:
        age = float(row.trusted["cutoff_ms"] - row.trusted["feature_available_ms"]) / 1000
        if not math.isfinite(age) or age < 0:
            violated = True
        else:
            violated = age > limit_seconds
        ages.append(age)
        if violated:
            violations.append({
                "source_ordinal": source_ordinals[row.game_id],
                "game_id": row.game_id,
                "event_id": row.trusted["event_id"],
                "schedule_date": row.split_date,
                "cutoff_second": row.trusted["cutoff_ms"] // 1000,
                "latest_trade_second": row.trusted["feature_available_ms"] // 1000,
                "observed_age_seconds": age,
                "reason": "staleness_limit_exceeded",
            })
    return {
        "schema": "nfl_market_offset_staleness_inventory_v1",
        "limit_seconds": limit_seconds,
        "boundary": "inclusive; age in [0,600] passes",
        "required_binary_rows": len(rows),
        "rows_checked": len(ages),
        "observed_min_seconds": min(ages) if ages else None,
        "observed_max_seconds": max(ages) if ages else None,
        "violations": violations,
        "valid": bool(ages) and not violations,
    }


def require_staleness_gate(report: dict, *, expected_binary_rows: int) -> None:
    if (report.get("required_binary_rows") != expected_binary_rows
            or report.get("rows_checked") != expected_binary_rows
            or report.get("valid") is not True
            or report.get("violations")):
        raise InvalidDataQuality(
            "INVALID_DATA_QUALITY: required binary rows violate the inclusive "
            "600-second latest-trade staleness gate",
            {
                **report,
                "status": "INVALID_DATA_QUALITY",
                "expected_binary_rows": expected_binary_rows,
                "actual_binary_rows_checked": report.get("rows_checked"),
            },
        )


def validate_exact_real_exclusion(exclusions: Sequence[dict]) -> None:
    expected = [{
        "source_ordinal": 53,
        "game_id": "2025_04_GB_DAL",
        "game_date": "2025-09-28",
        "reason": "unresolved_outcome",
    }]
    observed = [
        {key: row.get(key) for key in expected[0]}
        for row in exclusions
    ]
    if observed != expected:
        raise ValueError(
            "exact real exclusion must be ordinal 53, 2025_04_GB_DAL, "
            "2025-09-28, unresolved_outcome"
        )


def game_week(game_id: str) -> str:
    match = _GAME_WEEK.fullmatch(game_id)
    if match is None:
        raise ValueError(f"game ID does not encode a canonical season/week: {game_id}")
    return f"{match.group(1)}_{match.group(2)}"


def canonical_check_mask_sha256(rows: Sequence[base.DiagnosticRow]) -> str:
    """Match the proper scorer's validated cutoff/event/market key ordering."""
    canonical = probability_contract.validate_probability_rows(
        [dict(row.trusted) for row in rows]
    )
    return base._digest([list(row.key) for row in canonical])


def require_expected_check_mask(
        rows: Sequence[base.DiagnosticRow], expected_sha256: str) -> str:
    observed = canonical_check_mask_sha256(rows)
    if observed != expected_sha256:
        raise ValueError("check mask differs from frozen parent")
    return observed


def _means_for_cluster_draws(grouped_deltas: Mapping[str, Sequence[float]],
                             draws: Sequence[Sequence[str]]) -> list[float]:
    """Pool every event in sampled units, then recompute the event mean."""
    if not grouped_deltas:
        raise ValueError("at least one complete resampling unit is required")
    normalized = {}
    for unit, values in grouped_deltas.items():
        array = np.asarray(values, dtype=np.float64)
        if array.ndim != 1 or array.size == 0 or not np.all(np.isfinite(array)):
            raise ValueError(f"resampling unit {unit!r} has invalid event deltas")
        normalized[unit] = array
    means = []
    for draw in draws:
        if not draw:
            raise ValueError("cluster draw cannot be empty")
        selected = []
        for unit in draw:
            if unit not in normalized:
                raise ValueError(f"unknown resampling unit: {unit}")
            selected.append(normalized[unit])
        means.append(float(np.mean(np.concatenate(selected))))
    return means


def cluster_resample_equal_event_delta(
        event_deltas: Sequence[float], groups: Sequence[str], *,
        seed: int = BOOTSTRAP_SEED,
        replicates: int = BOOTSTRAP_REPLICATES) -> dict:
    deltas = np.asarray(event_deltas, dtype=np.float64)
    if (deltas.ndim != 1 or deltas.size == 0 or len(groups) != deltas.size
            or not np.all(np.isfinite(deltas))):
        raise ValueError("finite aligned event deltas are required")
    if replicates <= 0:
        raise ValueError("replicates must be positive")
    units = sorted(set(groups))
    if not units or any(not isinstance(value, str) or not value for value in groups):
        raise ValueError("nonempty string group labels are required")
    grouped = {
        unit: deltas[[index for index, value in enumerate(groups) if value == unit]]
        for unit in units
    }
    rng = np.random.default_rng(seed)
    draws = [
        [units[index] for index in rng.integers(0, len(units), size=len(units))]
        for _ in range(replicates)
    ]
    estimates = np.asarray(_means_for_cluster_draws(grouped, draws), dtype=np.float64)
    lower, upper = np.quantile(estimates, [0.025, 0.975])
    return {
        "estimand": "equal_event_mean_delta",
        "resampling": (
            "sample observed units with replacement; pool all events in selected "
            "units including repeated units; recompute equal-event mean per draw"
        ),
        "events": int(deltas.size),
        "units": len(units),
        "unit_labels": units,
        "unit_event_counts": {
            unit: int(grouped[unit].size) for unit in units
        },
        "seed": seed,
        "replicates": replicates,
        "point_estimate": float(np.mean(deltas)),
        "interval_95_percentile": [float(lower), float(upper)],
    }


def _loss_deltas(outcomes: Sequence[int], left: Sequence[float],
                 right: Sequence[float], loss: str) -> list[float]:
    if not (len(outcomes) == len(left) == len(right)):
        raise ValueError("paired loss arrays differ in length")
    if loss == "brier":
        function = brier_loss
    elif loss == "log_loss":
        function = bounded_log_loss
    else:
        raise ValueError("unsupported loss")
    return [
        function(float(a), int(y)) - function(float(b), int(y))
        for y, a, b in zip(outcomes, left, right, strict=True)
    ]


def corrected_grouped_inference(predictions: Sequence[dict]) -> dict:
    if not predictions:
        raise ValueError("predictions are empty")
    outcomes = [item["row"].trusted["outcome"] for item in predictions]
    forecasts = {
        "market": [item["row"].trusted["market_probability"] for item in predictions],
        "ordinary": [item["ordinary"]["probability"] for item in predictions],
        "candidate": [item["candidate"]["probability"] for item in predictions],
    }
    groups = {
        "schedule_day": [item["row"].split_date for item in predictions],
        "observed_game_week": [game_week(item["row"].game_id) for item in predictions],
    }
    comparisons = {
        "candidate_minus_market": ("candidate", "market"),
        "candidate_minus_ordinary": ("candidate", "ordinary"),
        "ordinary_minus_market": ("ordinary", "market"),
    }
    result = {
        "delta_convention": "left_minus_right; negative loss is better",
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
            result["schedule_day_resample"]
            if group_name == "schedule_day"
            else result["observed_game_week_cluster_sensitivity"]
        )
        for name, (left, right) in comparisons.items():
            target[name] = {
                loss: cluster_resample_equal_event_delta(
                    _loss_deltas(outcomes, forecasts[left], forecasts[right], loss),
                    labels,
                )
                for loss in ("brier", "log_loss")
            }
    schedule = result["schedule_day_resample"]
    schedule["unit_definition"] = (
        "complete source schedule dates contained wholly in chronological check folds"
    )
    week = result["observed_game_week_cluster_sensitivity"]
    ordered_weeks = sorted(set(groups["observed_game_week"]))
    right_edge = ordered_weeks[-1]
    week.update({
        "unit_definition": (
            "observed NFL game-week clusters in the fixed 87-event check mask; "
            "not all clusters are complete schedule weeks"
        ),
        "right_edge_partial_week": right_edge,
        "right_edge_partial_week_events": groups["observed_game_week"].count(right_edge),
        "primary_denominator_changed": False,
        "interpretation": (
            "secondary observed-week-cluster sensitivity; the right-edge partial week "
            "is retained to preserve the frozen 87-event primary denominator"
        ),
    })
    return result


def diagnostic_keep(candidate: Mapping[str, float], market: Mapping[str, float],
                    ordinary: Mapping[str, float],
                    candidate_market_fold_brier_wins: Iterable[bool],
                    candidate_ordinary_fold_brier_wins: Iterable[bool],
                    *, tolerance: float = STRICT_WIN_TOLERANCE) -> tuple[str, dict]:
    market_wins = list(candidate_market_fold_brier_wins)
    ordinary_wins = list(candidate_ordinary_fold_brier_wins)
    if len(market_wins) != 4 or len(ordinary_wins) != 4:
        raise ValueError("the frozen rule requires exactly four folds")

    def strict(reference: float, value: float) -> bool:
        return float(reference) - float(value) > tolerance

    conditions = {
        "candidate_aggregate_brier_below_market_by_more_than_1e-12": strict(
            market["brier"], candidate["brier"]
        ),
        "candidate_aggregate_log_loss_below_market_by_more_than_1e-12": strict(
            market["log_loss"], candidate["log_loss"]
        ),
        "candidate_aggregate_brier_below_ordinary_by_more_than_1e-12": strict(
            ordinary["brier"], candidate["brier"]
        ),
        "candidate_aggregate_log_loss_below_ordinary_by_more_than_1e-12": strict(
            ordinary["log_loss"], candidate["log_loss"]
        ),
        "candidate_brier_market_fold_wins_at_least_3_of_4": sum(market_wins) >= 3,
        "candidate_brier_ordinary_fold_wins_at_least_3_of_4": (
            sum(ordinary_wins) >= 3
        ),
        "candidate_market_fold_brier_wins": market_wins,
        "candidate_ordinary_fold_brier_wins": ordinary_wins,
        "strict_win_tolerance": tolerance,
    }
    decision_values = [
        value for key, value in conditions.items()
        if key not in {
            "candidate_market_fold_brier_wins",
            "candidate_ordinary_fold_brier_wins",
            "strict_win_tolerance",
        }
    ]
    return ("KEEP" if all(decision_values) else "REVERT", conditions)


def _fit_and_predict(rows: Sequence[base.DiagnosticRow], folds: Sequence[dict]
                     ) -> tuple[list[dict], list[dict]]:
    by_date: dict[str, list[base.DiagnosticRow]] = {}
    for row in rows:
        by_date.setdefault(row.split_date, []).append(row)
    all_predictions = []
    fold_reports = []
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
        label_unavailable = sorted(
            row.game_id for row in fit_candidates
            if row.trusted["outcome_available_ms"] >= first_check_cutoff
        )
        if not fit_rows or len({row.trusted["outcome"] for row in fit_rows}) != 2:
            raise ValueError(f"fold {fold['fold']} fit rows lack both outcome classes")
        validate_train_evaluation_rows(
            [row.trusted for row in fit_rows], [row.trusted for row in check_rows]
        )
        x_fit = np.asarray([row.features for row in fit_rows], dtype=np.float64)
        x_check = np.asarray([row.features for row in check_rows], dtype=np.float64)
        y_fit = np.asarray([row.trusted["outcome"] for row in fit_rows], dtype=np.int64)
        y_check = [row.trusted["outcome"] for row in check_rows]
        fit_market = np.asarray(
            [row.trusted["market_probability"] for row in fit_rows], dtype=np.float64
        )
        check_market = np.asarray(
            [row.trusted["market_probability"] for row in check_rows], dtype=np.float64
        )
        fit_logits = np.log(fit_market / (1.0 - fit_market))
        check_logits = np.log(check_market / (1.0 - check_market))
        if (not np.allclose(x_fit[:, 0], fit_logits, rtol=0.0, atol=1e-12)
                or not np.allclose(x_check[:, 0], check_logits, rtol=0.0, atol=1e-12)):
            raise RuntimeError("market-logit feature differs from unstandardized offset")
        scaler = StandardScaler()
        standardized_fit = scaler.fit_transform(x_fit)
        standardized_check = scaler.transform(x_check)
        ordinary = LogisticRegression(
            C=1.0, solver="lbfgs", max_iter=500, random_state=23
        )
        ordinary.fit(standardized_fit, y_fit)
        parameters, optimizer = fit_offset_ridge(
            standardized_fit, y_fit, fit_logits
        )
        ordinary_values = [
            float(value) for value in ordinary.predict_proba(standardized_check)[:, 1]
        ]
        candidate_values = [
            float(value) for value in offset_probabilities(
                parameters, standardized_check, check_logits
            )
        ]
        market_values = [float(value) for value in check_market]
        ordinary_records = base._prediction_records(check_rows, ordinary_values)
        candidate_records = base._prediction_records(check_rows, candidate_values)
        market_metrics = base._simple_metrics(y_check, market_values)
        ordinary_metrics = base._simple_metrics(y_check, ordinary_values)
        candidate_metrics = base._simple_metrics(y_check, candidate_values)
        fold_reports.append({
            "fold": fold["fold"],
            "fit_dates": fold["fit_dates"],
            "check_dates": fold["check_dates"],
            "fit_events": len(fit_rows),
            "check_events": len(check_rows),
            "fit_label_unavailable_events": label_unavailable,
            "identical_fit_feature_matrix": True,
            "identical_check_feature_matrix": True,
            "scaler_fit_rows_only": True,
            "market": market_metrics,
            "ordinary": ordinary_metrics,
            "candidate": candidate_metrics,
            "candidate_minus_market_brier": (
                candidate_metrics["brier"] - market_metrics["brier"]
            ),
            "candidate_minus_market_log_loss": (
                candidate_metrics["log_loss"] - market_metrics["log_loss"]
            ),
            "candidate_minus_ordinary_brier": (
                candidate_metrics["brier"] - ordinary_metrics["brier"]
            ),
            "candidate_minus_ordinary_log_loss": (
                candidate_metrics["log_loss"] - ordinary_metrics["log_loss"]
            ),
            "optimizer": optimizer,
        })
        for row, ordinary_record, candidate_record in zip(
                check_rows, ordinary_records, candidate_records, strict=True):
            all_predictions.append({
                "fold": fold["fold"],
                "row": row,
                "ordinary": ordinary_record,
                "candidate": candidate_record,
            })
    keys = [item["row"].key for item in all_predictions]
    if len(keys) != len(set(keys)):
        raise ValueError("an event appears in multiple check folds")
    return all_predictions, fold_reports


def validate_control_parity(predictions: Sequence[dict], parent_csv: Path,
                            *, verify_parent_hash: bool) -> dict:
    parent_csv = Path(parent_csv)
    if verify_parent_hash:
        for name, expected in PARENT_ARTIFACT_SHA256.items():
            path = parent_csv.parent / name
            if base._sha256(path) != expected:
                raise ValueError(f"frozen parent artifact hash changed: {name}")
    with parent_csv.open(newline="", encoding="utf-8") as stream:
        controls = list(csv.DictReader(stream))
    if len(controls) != len(predictions):
        raise ValueError("parent control row count differs")
    max_market_delta = 0.0
    max_ordinary_delta = 0.0
    for item, control in zip(predictions, controls, strict=True):
        row = item["row"]
        actual_identity = (
            str(item["fold"]), row.game_id, row.split_date,
            row.trusted["event_id"], row.trusted["market_id"],
            str(row.trusted["cutoff_ms"]), str(row.trusted["outcome_available_ms"]),
            str(row.trusted["outcome"]),
        )
        expected_identity = tuple(control[name] for name in (
            "fold", "game_id", "split_date", "event_id", "market_id", "cutoff_ms",
            "outcome_available_ms", "outcome",
        ))
        if actual_identity != expected_identity:
            raise ValueError("parent control identity/order/mask differs")
        market_delta = abs(
            row.trusted["market_probability"] - float(control["market_probability"])
        )
        ordinary_delta = abs(
            item["ordinary"]["probability"] - float(control["ordinary_probability"])
        )
        max_market_delta = max(max_market_delta, market_delta)
        max_ordinary_delta = max(max_ordinary_delta, ordinary_delta)
        if market_delta != 0.0:
            raise ValueError("market probability differs from frozen parent")
        if ordinary_delta > 1e-10:
            raise ValueError("ordinary probability differs from frozen parent by >1e-10")
    return {
        "parent_predictions_sha256": base._sha256(parent_csv),
        "rows": len(predictions),
        "identity_order_mask_exact": True,
        "market_probability_exact": True,
        "ordinary_probability_tolerance": 1e-10,
        "maximum_market_absolute_difference": max_market_delta,
        "maximum_ordinary_absolute_difference": max_ordinary_delta,
    }


def _write_predictions(path: Path, predictions: Sequence[dict]) -> None:
    fields = (
        "fold", "game_id", "split_date", "game_week", "event_id", "market_id",
        "cutoff_ms", "outcome_available_ms", "outcome", "market_probability",
        "ordinary_probability", "candidate_probability",
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
                "game_week": game_week(row.game_id),
                "event_id": row.trusted["event_id"],
                "market_id": row.trusted["market_id"],
                "cutoff_ms": row.trusted["cutoff_ms"],
                "outcome_available_ms": row.trusted["outcome_available_ms"],
                "outcome": row.trusted["outcome"],
                "market_probability": row.trusted["market_probability"],
                "ordinary_probability": item["ordinary"]["probability"],
                "candidate_probability": item["candidate"]["probability"],
            })
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def run(source_root: Path, output: Path, *, expected_events: int = EXPECTED_EVENTS,
        expected_dates: int = EXPECTED_DATES, allow_test_paths: bool = False,
        generated_utc: str | None = None,
        parent_predictions_path: Path | None = None) -> dict:
    """Run the frozen offset diagnostic; path/count overrides are test-only."""
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    _validate_frozen_specs()
    runtime_identity = _validate_execution_identity()
    if not allow_test_paths:
        if base._sha256(source_root / "manifest.json") != base.EXPECTED_MANIFEST_SHA256:
            raise ValueError("frozen source manifest hash changed")
        if base._sha256(source_root / "cohort.csv") != base.EXPECTED_COHORT_SHA256:
            raise ValueError("frozen cohort hash changed")
    manifest = base._strict_json(source_root / "manifest.json")
    if (not isinstance(manifest, dict)
            or manifest.get("schema") != "nfl_2025_train_fresh_source_audit_v1"
            or manifest.get("complete") is not True
            or manifest.get("source_games") != expected_events
            or manifest.get("train_distinct_dates") != expected_dates
            or manifest.get("dev_final_opened") is not False
            or manifest.get("model_fits") != 0
            or manifest.get("provider_cost_usd") != "0"):
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
            validate_exact_real_exclusion(exclusions)
        folds = base.chronological_date_folds(
            [item["game_date"] for item in cohort], expected_dates=expected_dates
        )
        if not materialized:
            raise ValueError("all source events were excluded")
        materialized.sort(key=lambda row: row.key)
        source_ordinals = {item["game_id"]: ordinal for ordinal, item in enumerate(cohort)}
        staleness = staleness_inventory(materialized, source_ordinals)
        base._atomic_json(output / "staleness_inventory.json", staleness)
        expected_binary_rows = 194 if not allow_test_paths else len(materialized)
        require_staleness_gate(staleness, expected_binary_rows=expected_binary_rows)

        input_receipts = {
            "schema": "nfl_market_offset_ridge_train_inputs_v1",
            "source_dataset_id": source_root.name,
            "source_manifest_sha256": base._sha256(source_root / "manifest.json"),
            "cohort_sha256": base._sha256(cohort_path),
            "source_events": expected_events,
            "source_dates": expected_dates,
            "runner_source_sha256": base._sha256(Path(__file__)),
            "parent_runner_source_sha256": runtime_identity["parent_runner_sha256"],
            "parent_test_source_sha256": runtime_identity["parent_test_sha256"],
            "proper_scorer_source_sha256": runtime_identity["proper_scorer_sha256"],
            "probability_contract_source_sha256": runtime_identity[
                "probability_contract_sha256"
            ],
            "runtime_identity": runtime_identity,
            "controller_proposal_path": runtime_identity["controller_proposal_path"],
            "controller_proposal_sha256": runtime_identity[
                "controller_proposal_sha256"
            ],
            "all_source_file_receipts": source_file_receipts,
            "materialized_event_receipts": [row.source_receipt for row in materialized],
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "provider_cost_usd": "0",
        }
        exclusions_artifact = {
            "schema": "nfl_market_offset_ridge_train_exclusions_v1",
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
        materialized_hash = base._digest([list(row.key) for row in materialized])
        if not allow_test_paths and materialized_hash != EXPECTED_MATERIALIZED_KEY_SHA256:
            raise ValueError("materialized key population differs from frozen parent")
        lock = {
            "schema": "nfl_market_offset_ridge_train_pre_score_lock_v1",
            "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "problem": (
                "test whether a fixed market-offset ridge residual predictor improves "
                "settlement probability on the unchanged causal representation"
            ),
            "changed_stage": "prediction_trainer_only",
            "domain": "2025 NFL two-outcome moneyline opened Train Discovery",
            "source_manifest_sha256": input_receipts["source_manifest_sha256"],
            "cohort_sha256": input_receipts["cohort_sha256"],
            "input_receipts_sha256": base._sha256(output / "input_receipts.json"),
            "exclusions_sha256": base._sha256(output / "exclusions.json"),
            "staleness_inventory_sha256": base._sha256(
                output / "staleness_inventory.json"
            ),
            "source_events": expected_events,
            "source_dates": expected_dates,
            "execution_identity": runtime_identity,
            "controller_provenance": {
                "model": "gpt-6-astra",
                "reasoning_effort": "high",
                "proposal_path": runtime_identity["controller_proposal_path"],
                "proposal_sha256": runtime_identity["controller_proposal_sha256"],
                "recipe_status": "frozen before this implementation and score",
            },
            "decision_cutoff": "event_start_utc minus 15 minutes",
            "chronological_grouping": (
                "exact cohort/catalog game_date; one whole schedule date per fold; "
                "never cutoff UTC calendar date"
            ),
            "outcome_availability": (
                "maximum of present selected-market closedTime, selected-market "
                "umaEndDate, and event finishedTimestamp; no other clock admitted"
            ),
            "same_second_baseline": (
                "size-weighted home-win probability at latest eligible integer second"
            ),
            "max_staleness_seconds": MAX_STALENESS_SECONDS,
            "staleness_boundary": "inclusive; age in [0,600] passes",
            "feature_names": list(base.FEATURE_NAMES),
            "feature_spec_sha256": base._digest(_feature_spec()),
            "folds": folds,
            "ordinary_spec": dict(base.ORDINARY_SPEC),
            "ordinary_spec_sha256": base._digest(dict(base.ORDINARY_SPEC)),
            "candidate_spec": dict(CANDIDATE_SPEC),
            "candidate_spec_sha256": base._digest(dict(CANDIDATE_SPEC)),
            "shared_preprocessing": "fold-fit StandardScaler",
            "event_weighting": "one row per event; equal event weight",
            "corrected_inference": {
                "seed": BOOTSTRAP_SEED,
                "replicates": BOOTSTRAP_REPLICATES,
                "units": [
                    "complete source schedule date",
                    "observed NFL game-week cluster with right-edge partial disclosed",
                ],
                "per_draw_estimand": "pooled equal-event mean loss delta",
            },
            "keep_rule": (
                "candidate Brier and log loss each beat market and ordinary by >1e-12; "
                "candidate Brier beats each reference in at least 3/4 folds"
            ),
            "materialized_key_sha256": materialized_hash,
            "incumbent_and_branch_semantics": {
                "current_best_before_run": "decision-time market probability",
                "keep_action": (
                    "replace current best with MarketOffsetRidgeLogistic-v1 for "
                    "further Discovery only"
                ),
                "revert_action": "retain decision-time market as current best",
                "ordinary_role": "ordinary reference; not Strong-Baseline-1",
                "branch_retention": (
                    "retain this candidate and prior HGB code, artifacts, and evidence "
                    "regardless of KEEP/REVERT"
                ),
            },
            "evidence_labels": {
                "literature_supported_principles": [
                    "strictly-prior fitting for temporal evaluation",
                    "dependence-aware grouped resampling",
                    "fit preprocessing only on prior training rows",
                ],
                "project_chosen_parameters_not_literature_consensus": [
                    "15-minute cutoff",
                    "22 initial fit dates plus four 5-date expanding checks",
                    "600-second inclusive staleness bound",
                    "lambda=1.0 with all 18 residual parameters penalized",
                    "bootstrap seed 23 and 1000 replicates",
                    "fixed LogisticRegression and MarketOffsetRidgeLogistic-v1 recipes",
                ],
                "unvalidated_hypothesis": (
                    "a penalized residual around the market offset adds settlement "
                    "information beyond the decision-time market"
                ),
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
        predictions, fold_reports = _fit_and_predict(materialized, folds)
        check_rows = [item["row"] for item in predictions]
        if not allow_test_paths:
            observed_counts = tuple(
                (report["fit_events"], report["check_events"])
                for report in fold_reports
            )
            if observed_counts != EXPECTED_REAL_FOLD_COUNTS:
                raise ValueError("fit/check event counts differ from frozen parent")
            if any(report["fit_label_unavailable_events"] for report in fold_reports):
                raise ValueError("frozen parent expects zero unavailable fit labels")
            if len(check_rows) != 87 or len({row.split_date for row in check_rows}) != 20:
                raise ValueError("exact cohort must retain 87 rows on 20 check dates")
            if len({game_week(row.game_id) for row in check_rows}) != 7:
                raise ValueError("exact check population must span seven NFL game weeks")
            require_expected_check_mask(check_rows, EXPECTED_CHECK_MASK_SHA256)

        parent_path = (
            Path(parent_predictions_path) if parent_predictions_path is not None
            else PARENT_ARTIFACT_ROOT / "predictions.csv"
        )
        control_parity = None
        if not allow_test_paths or parent_predictions_path is not None:
            control_parity = validate_control_parity(
                predictions,
                parent_path,
                verify_parent_hash=not allow_test_paths,
            )
        ordinary_records = [item["ordinary"] for item in predictions]
        candidate_records = [item["candidate"] for item in predictions]
        scoring_started = True
        ordinary_vs_market = base._score(check_rows, ordinary_records)
        candidate_vs_market = base._score(check_rows, candidate_records)
        candidate_vs_ordinary = base._score(
            check_rows, candidate_records, reference=ordinary_records
        )
        ordinary_primary = ordinary_vs_market["primary"]
        candidate_primary = candidate_vs_market["primary"]
        aggregate = {
            "market": {
                "brier": candidate_primary["equal_event_market_brier"],
                "log_loss": candidate_primary["equal_event_market_log_loss"],
                "calibration": candidate_vs_market["calibration"]["market"],
            },
            "ordinary": {
                "brier": ordinary_primary["equal_event_candidate_brier"],
                "log_loss": ordinary_primary["equal_event_candidate_log_loss"],
                "calibration": ordinary_vs_market["calibration"]["candidate"],
            },
            "candidate": {
                "brier": candidate_primary["equal_event_candidate_brier"],
                "log_loss": candidate_primary["equal_event_candidate_log_loss"],
                "calibration": candidate_vs_market["calibration"]["candidate"],
            },
            "candidate_minus_ordinary": {
                "brier": candidate_vs_ordinary["primary"][
                    "equal_event_candidate_minus_market_brier"
                ],
                "log_loss": candidate_vs_ordinary["primary"][
                    "equal_event_candidate_minus_market_log_loss"
                ],
            },
            "candidate_minus_market": {
                "brier": candidate_primary["equal_event_candidate_minus_market_brier"],
                "log_loss": candidate_primary[
                    "equal_event_candidate_minus_market_log_loss"
                ],
            },
        }
        decision, conditions = diagnostic_keep(
            aggregate["candidate"], aggregate["market"], aggregate["ordinary"],
            [
                fold["market"]["brier"] - fold["candidate"]["brier"]
                > STRICT_WIN_TOLERANCE
                for fold in fold_reports
            ],
            [
                fold["ordinary"]["brier"] - fold["candidate"]["brier"]
                > STRICT_WIN_TOLERANCE
                for fold in fold_reports
            ],
        )
        _write_predictions(output / "predictions.csv", predictions)
        scorecard = {
            "schema": "nfl_market_offset_ridge_train_scorecard_v1",
            "diagnostic_decision": decision,
            "decision_scope": "replace current best for further Discovery only",
            "incumbent_and_branch_semantics": {
                "current_best_before_run": "decision-time market probability",
                "current_best_after_run": (
                    "MarketOffsetRidgeLogistic-v1" if decision == "KEEP"
                    else "decision-time market probability"
                ),
                "ordinary_role": "ordinary reference; not Strong-Baseline-1",
                "candidate_branch_retained": True,
                "prior_hgb_branch_retained": True,
            },
            "keep_conditions": conditions,
            "source_denominator": {
                "events": expected_events,
                "dates": expected_dates,
                "materialized_events": len(materialized),
                "excluded_events": len(exclusions),
                "check_events": len(check_rows),
                "check_dates": len({row.split_date for row in check_rows}),
                "check_game_weeks": len({game_week(row.game_id) for row in check_rows}),
                "materialization_coverage": len(materialized) / expected_events,
                "check_fraction_of_source_events": len(check_rows) / expected_events,
            },
            "identical_masks": {
                "market_ordinary_candidate_check_keys_identical": True,
                "complete_mask_sha256": candidate_vs_market["coverage"][
                    "complete_mask_sha256"
                ],
                "ordinary_complete_mask_sha256": ordinary_vs_market["coverage"][
                    "complete_mask_sha256"
                ],
                "candidate_vs_ordinary_complete_mask_sha256": (
                    candidate_vs_ordinary["coverage"]["complete_mask_sha256"]
                ),
            },
            "control_parity": control_parity,
            "aggregate": aggregate,
            "folds": fold_reports,
            "paired_candidate_minus_ordinary": base._direct_candidate_ordinary_view(
                candidate_vs_ordinary
            ),
            "paired_candidate_minus_market": candidate_vs_market["paired_evidence"],
            "paired_ordinary_minus_market": ordinary_vs_market["paired_evidence"],
            "corrected_grouped_inference": corrected_grouped_inference(predictions),
            "inference_boundary": (
                "opened-Train chronological Discovery only; intervals are descriptive "
                "under repeated inspection, not independent OOS evidence"
            ),
            "unsupported_claims": [
                "promotion or formal out-of-sample improvement",
                "profitability or executable-price performance",
                "generalization beyond the 2025 NFL seed domain",
                "a uniquely identified causal contribution from anchoring or shrinkage",
            ],
            "route_dev_opened": False,
            "sealed_final_opened": False,
            "provider_cost_usd": "0",
            "promotion_authorized": False,
        }
        masks = scorecard["identical_masks"]
        if len({
                masks["complete_mask_sha256"],
                masks["ordinary_complete_mask_sha256"],
                masks["candidate_vs_ordinary_complete_mask_sha256"],
                }) != 1:
            raise RuntimeError("proper scorers did not receive identical check masks")
        base._atomic_json(output / "scorecard.json", scorecard)
        final = {
            "schema": "nfl_market_offset_ridge_train_manifest_v1",
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
            "model_fits": base.CHECK_FOLDS * 2,
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
            invalid = isinstance(error, InvalidDataQuality)
            failure = {
                "schema": "nfl_market_offset_ridge_train_failure_v1",
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
        "diagnostic_decision": result["diagnostic_decision"],
        "provider_cost_usd": result["provider_cost_usd"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
