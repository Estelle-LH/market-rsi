#!/usr/bin/env python3
"""Frozen market-offset score-by-time diagnostic on opened 2025 NFL Train.

This is a historical, repeatedly inspected Train diagnostic.  It develops the
archived negative PBP branch from ``InGameWinProbabilityTrainDiagnostic-v0``
without changing that run.  The market logit is a fixed coefficient-one
offset; only an intercept and predeclared state coefficients are estimated.
No score from this task is comparable to the separate pregame task.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from sklearn.preprocessing import StandardScaler

from minimal_prediction_loop import probability_contract, proper_scoring
from minimal_prediction_loop.probability_contract import (
    DEFAULT_PROBABILITY_POLICY,
    validate_probability,
    validate_train_evaluation_rows,
)
from minimal_prediction_loop.proper_scoring import bounded_log_loss, brier_loss
from experiments import nfl_ingame_win_probability_train_diagnostic as base
from experiments import nfl_settlement_probability_train_diagnostic as settlement


TASK_ID = "InGameMarketOffsetScoreTimeDiagnostic-v1"
QUESTION_ID = "ingame-offset-scoretime-v1-q1"
QUESTION_RECORD_SHA256 = "8cfabbfb4f93b2eddf31f61f7d4a2850b1e4dd0032661ae80ed433d1e36bfa9f"
SOURCE_ROOT = base.SOURCE_ROOT
PERSISTENT_ARTIFACT_ROOT = base.PERSISTENT_ARTIFACT_ROOT
EXPECTED_EVENTS = base.EXPECTED_EVENTS
EXPECTED_DATES = base.EXPECTED_DATES
EXTRACTOR = base.EXTRACTOR
SEED = base.SEED
BOOTSTRAP_SEED = base.BOOTSTRAP_SEED
BOOTSTRAP_REPLICATES = base.BOOTSTRAP_REPLICATES
PENALTY_LAMBDA = 1.0
EXPECTED_MATERIALIZED_EVENTS = 193
EXPECTED_CHECK_EVENTS = 87
EXPECTED_FIT_EVENTS = (106, 132, 148, 176)
EXPECTED_CHECK_EVENTS_BY_FOLD = (26, 16, 28, 17)
EXPECTED_MATERIALIZED_KEY_SHA256 = "0bb6ae95fd26937b592569f004c16ac729b1e4c6b796c975a1d988e57c4d2c34"
EXPECTED_CHECK_KEY_SHA256 = "2e35779fdbb4b83e129758008338b0c778d7f6281682118ad8d26d21293cc9f9"
EXPECTED_CHECKPOINT_STATE_SHA256 = "235510db382de2e4b321f11db80b9f5b969c094eb2d122b18ab373e6d31ae96e"

V0_ARTIFACT_ROOT = Path(
    "/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/"
    "artifacts/nfl-ingame-win-probability-train-diagnostic-20260929-01"
)
V0_ARTIFACT_HASHES = {
    "checkpoint_state.csv": EXPECTED_CHECKPOINT_STATE_SHA256,
    "exclusions.json": "db5b535d261f1e6676beafebeb7aee70833ea1d7988aba25a95c905a9955eaf1",
    "input_receipts.json": "0fa0a2444beaddd0a51efd2024c5e6d7c09158db7d6488a59421a99866fdbf18",
    "manifest.json": "9c6ab11fc553a13e35b410c8763d87a85b535a5ab9b47df8c8dc0d10ac922fc7",
    "pre_score_lock.json": "dc3a8bf1a27795750c44193000480c9279dd47de5d115d6cfad829e5b81d6ef2",
    "predictions.csv": "505e11a4ceb3ae569397bbbc11c6a0be6e9f04a494c9ecb1f4ca40dc06d76d56",
    "scorecard.json": "74c2f23de2ae129ead4d7def1a692d69240ac799582e54db3623865c3525de87",
}
V0_RUNNER_SHA256 = "e61668c7e29cf4dda95f6cc315b248dbe6744a9dcc0ae0cd6077d880ca6265b7"
EXTRACTOR_SHA256 = "37a26997406de0e54bd9d91de10e7417a8b340c68b675892c4f16e9a51675163"
CONTROLLER_LOG = Path(__file__).parents[1] / "supervisor_harness" / (
    "AGENT_LOG_INGAME_MARKET_OFFSET_SCORE_TIME_V1_CONTROLLER_2026-09-29.md"
)
CONTROLLER_LOG_SHA256 = "3930ab266e1983e6cd15a3472977984961b0f08a45e246eebb8feefbb048e8ce"
V0_RESULT_REVIEW = Path(__file__).parents[1] / "supervisor_harness" / (
    "AGENT_LOG_NFL_INGAME_WIN_PROBABILITY_V0_RESULT_INDEPENDENT_REVIEW_2026-09-29.md"
)
V0_RESULT_REVIEW_SHA256 = "325543498c556a1c1ba0e8e3adde42c4546c35e1b0bcffac8efbeafd3d38f983"

ARM_INTERCEPT = "market_offset_intercept"
ARM_LINEAR = "market_offset_linear_state"
ARM_SCORE_TIME = "market_offset_score_time_state"
OFFSET_ARMS = (ARM_INTERCEPT, ARM_LINEAR, ARM_SCORE_TIME)
ALL_ARMS = ("raw_market",) + OFFSET_ARMS
ARM_COMPONENT_SPEC_SHA256 = {
    ARM_INTERCEPT: "e2f71e54a5c2d933c4554ee111b8316ac7e64198b047b053fbd39d3b12242da7",
    ARM_LINEAR: "bd907c7048076b033611d56eb10a02a637d427a7d0dcd3d95c45da84af42d95c",
    ARM_SCORE_TIME: "bcdb518f4f7c7ea1a0da70bc841d67990b07c39c953c9cf63b707b3f5cfdd56a",
}
LINEAR_FEATURE_NAMES = base.STATE_FEATURE_NAMES
SCORE_TIME_FEATURE_NAME = "score_time_ratio_k4"
SCORE_TIME_FEATURE_NAMES = LINEAR_FEATURE_NAMES + (SCORE_TIME_FEATURE_NAME,)
LINEAR_CONTINUOUS_INDICES = (0, 1, 7, 8)
SCORE_TIME_CONTINUOUS_INDICES = LINEAR_CONTINUOUS_INDICES + (9,)
SOLVER_SPEC = {
    "optimizer": "scipy.optimize.minimize",
    "method": "L-BFGS-B",
    "maxiter": 1000,
    "gtol": 1e-8,
    "ftol": 1e-12,
    "analytic_gradient": True,
    "objective": "sum binary NLL + 0.5 * L2(non-intercept coefficients)",
    "penalty_lambda": PENALTY_LAMBDA,
    "market_logit_coefficient": 1.0,
    "intercept_penalized": False,
    "retry_count": 0,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_frozen_file(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or path.is_symlink() or _sha256(path) != expected:
        raise ValueError(f"frozen {label} is missing, nonregular, symlinked, or hash-changed")


def _validate_frozen_dependencies() -> None:
    _require_frozen_file(Path(base.__file__), V0_RUNNER_SHA256, "v0 runner")
    _require_frozen_file(EXTRACTOR, EXTRACTOR_SHA256, "checkpoint extractor")
    _require_frozen_file(CONTROLLER_LOG, CONTROLLER_LOG_SHA256, "Controller decision")
    _require_frozen_file(V0_RESULT_REVIEW, V0_RESULT_REVIEW_SHA256, "v0 result review")


def _validate_v0_artifact(root: Path = V0_ARTIFACT_ROOT) -> dict:
    root = Path(root).resolve()
    if not root.is_dir() or root.is_symlink():
        raise ValueError("frozen v0 result artifact is unavailable")
    observed = sorted(path.name for path in root.iterdir())
    if observed != sorted(V0_ARTIFACT_HASHES):
        raise ValueError("frozen v0 result artifact file set changed")
    for name, digest in V0_ARTIFACT_HASHES.items():
        _require_frozen_file(root / name, digest, f"v0 artifact {name}")
    manifest = settlement._strict_json(root / "manifest.json")
    scorecard = settlement._strict_json(root / "scorecard.json")
    lock = settlement._strict_json(root / "pre_score_lock.json")
    if (manifest.get("complete") is not True
            or manifest.get("task_id") != "InGameWinProbabilityTrainDiagnostic-v0"
            or manifest.get("source_events") != EXPECTED_EVENTS
            or manifest.get("materialized_events") != EXPECTED_MATERIALIZED_EVENTS
            or manifest.get("excluded_events") != 2
            or manifest.get("check_events") != EXPECTED_CHECK_EVENTS
            or manifest.get("model_fits") != 8
            or manifest.get("data_increment_decision") != "PBP_INCREMENT_NOT_SUPPORTED"
            or manifest.get("route_dev_opened") is not False
            or manifest.get("sealed_final_opened") is not False
            or manifest.get("external_fetch") is not False
            or manifest.get("provider_cost_usd") != "0"):
        raise ValueError("frozen v0 manifest boundary or result changed")
    masks = scorecard.get("identical_masks", {})
    if (masks.get("check_key_sha256") != EXPECTED_CHECK_KEY_SHA256
            or masks.get("all_three_arms_same_rows_labels_and_checkpoints") is not True
            or masks.get("one_checkpoint_per_game") is not True):
        raise ValueError("frozen v0 common-mask evidence changed")
    if lock.get("materialized_key_sha256") != EXPECTED_MATERIALIZED_KEY_SHA256:
        raise ValueError("frozen v0 materialized population changed")
    return {"manifest": manifest, "scorecard": scorecard, "pre_score_lock": lock}


def _score_time_ratio_k4(row: base.InGameRow) -> float:
    score = float(row.state_features[0])
    seconds = float(row.state_features[1])
    clipped = min(3600.0, max(0.0, seconds))
    value = score * math.exp(4.0 * (1.0 - clipped / 3600.0))
    if not math.isfinite(value):
        raise ValueError("score_time_ratio_k4 is nonfinite")
    return value


def _validate_extracted_score_time(state: Mapping[str, str]) -> None:
    if state.get("status") != "eligible":
        return
    score = float(state["home_score_diff_pre"])
    seconds = float(state["regulation_seconds_remaining"])
    observed = float(state["score_time_ratio_k4"])
    expected = score * math.exp(4.0 * (1.0 - min(3600.0, max(0.0, seconds)) / 3600.0))
    if not all(math.isfinite(value) for value in (score, seconds, observed, expected)):
        raise ValueError("nonfinite extracted score-time feature")
    if not math.isclose(observed, expected, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("extracted score_time_ratio_k4 differs from frozen formula")


def _features(row: base.InGameRow, arm: str) -> tuple[float, ...]:
    if arm == ARM_INTERCEPT:
        return ()
    if arm == ARM_LINEAR:
        return tuple(float(value) for value in row.state_features)
    if arm == ARM_SCORE_TIME:
        return tuple(float(value) for value in row.state_features) + (
            _score_time_ratio_k4(row),
        )
    raise ValueError(f"unknown arm: {arm}")


def _feature_names(arm: str) -> tuple[str, ...]:
    if arm == ARM_INTERCEPT:
        return ()
    if arm == ARM_LINEAR:
        return LINEAR_FEATURE_NAMES
    if arm == ARM_SCORE_TIME:
        return SCORE_TIME_FEATURE_NAMES
    raise ValueError(f"unknown arm: {arm}")


def _continuous_indices(arm: str) -> tuple[int, ...]:
    if arm == ARM_INTERCEPT:
        return ()
    if arm == ARM_LINEAR:
        return LINEAR_CONTINUOUS_INDICES
    if arm == ARM_SCORE_TIME:
        return SCORE_TIME_CONTINUOUS_INDICES
    raise ValueError(f"unknown arm: {arm}")


def _as_matrix(values: object, label: str, *, columns: int | None = None) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64)
    if result.ndim != 2 or result.shape[0] == 0 or not np.all(np.isfinite(result)):
        raise ValueError(f"{label} must be a nonempty finite float64 matrix")
    if columns is not None and result.shape[1] != columns:
        raise ValueError(f"{label} has the wrong feature width")
    return result


def _as_binary(values: object, rows: int) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64)
    if (result.shape != (rows,) or not np.all(np.isfinite(result))
            or not np.all(np.isin(result, (0.0, 1.0)))):
        raise ValueError("outcomes must be one finite binary value per row")
    return result


def offset_objective_gradient(parameters: object, standardized_features: object,
                              outcomes: object, market_logits: object,
                              *, penalty_lambda: float = PENALTY_LAMBDA,
                              ) -> tuple[float, np.ndarray]:
    """Return frozen sum-NLL plus non-intercept ridge objective and gradient."""
    features = _as_matrix(standardized_features, "standardized features")
    labels = _as_binary(outcomes, features.shape[0])
    offsets = np.asarray(market_logits, dtype=np.float64)
    theta = np.asarray(parameters, dtype=np.float64)
    if offsets.shape != (features.shape[0],) or not np.all(np.isfinite(offsets)):
        raise ValueError("market logits must be finite and aligned")
    if theta.shape != (features.shape[1] + 1,) or not np.all(np.isfinite(theta)):
        raise ValueError("parameter vector has the wrong shape or is nonfinite")
    if not math.isfinite(float(penalty_lambda)) or penalty_lambda < 0:
        raise ValueError("penalty lambda must be finite and nonnegative")
    linear = offsets + theta[0] + features @ theta[1:]
    weights = theta[1:]
    objective = (
        float(np.sum(np.logaddexp(0.0, linear) - labels * linear))
        + 0.5 * float(penalty_lambda) * float(weights @ weights)
    )
    residual = expit(linear) - labels
    gradient = np.empty_like(theta)
    gradient[0] = float(np.sum(residual))
    gradient[1:] = features.T @ residual + float(penalty_lambda) * weights
    if not math.isfinite(objective) or not np.all(np.isfinite(gradient)):
        raise FloatingPointError("offset objective or gradient is nonfinite")
    return objective, gradient


def offset_probabilities(parameters: object, standardized_features: object,
                         market_logits: object) -> np.ndarray:
    features = _as_matrix(standardized_features, "standardized features")
    theta = np.asarray(parameters, dtype=np.float64)
    offsets = np.asarray(market_logits, dtype=np.float64)
    if theta.shape != (features.shape[1] + 1,):
        raise ValueError("parameter vector has the wrong shape")
    if offsets.shape != (features.shape[0],):
        raise ValueError("market logits have the wrong shape")
    if not np.all(np.isfinite(theta)) or not np.all(np.isfinite(offsets)):
        raise ValueError("parameters and market logits must be finite")
    # There is intentionally no trainable multiplier on offsets.
    probabilities = expit(offsets + theta[0] + features @ theta[1:])
    if not np.all(np.isfinite(probabilities)):
        raise FloatingPointError("offset probabilities are nonfinite")
    return np.asarray(probabilities, dtype=np.float64)


def _scale_fold(fit: np.ndarray, check: np.ndarray, arm: str,
                ) -> tuple[np.ndarray, np.ndarray, dict]:
    feature_names = _feature_names(arm)
    fit = _as_matrix(fit, "fit features", columns=len(feature_names))
    check = _as_matrix(check, "check features", columns=len(feature_names))
    indices = _continuous_indices(arm)
    if not indices:
        return fit.copy(), check.copy(), {
            "fit_only": True, "continuous_indices": [], "feature_names": [],
            "means": [], "scales": [],
        }
    if len(set(indices)) != len(indices) or any(
            index < 0 or index >= fit.shape[1] for index in indices):
        raise ValueError("continuous feature indices are invalid")
    scaler = StandardScaler().fit(fit[:, indices])
    fit_result, check_result = fit.copy(), check.copy()
    fit_result[:, indices] = scaler.transform(fit[:, indices])
    check_result[:, indices] = scaler.transform(check[:, indices])
    return fit_result, check_result, {
        "fit_only": True,
        "continuous_indices": list(indices),
        "feature_names": [feature_names[index] for index in indices],
        "means": [float(value) for value in scaler.mean_],
        "scales": [float(value) for value in scaler.scale_],
    }


def _conditioning(matrix: np.ndarray) -> dict:
    design = np.column_stack((np.ones(matrix.shape[0]), matrix))
    singular = np.linalg.svd(design, compute_uv=False)
    rank = int(np.linalg.matrix_rank(design))
    condition = float(np.linalg.cond(design))
    return {
        "rows": int(design.shape[0]),
        "columns_including_intercept": int(design.shape[1]),
        "matrix_rank": rank,
        "rank_deficient": rank < design.shape[1],
        "condition_number": condition if math.isfinite(condition) else None,
        "largest_singular_value": float(singular[0]),
        "smallest_singular_value": float(singular[-1]),
        "diagnostic_only": True,
    }


def fit_offset_arm(standardized_fit: object, outcomes: object,
                   fit_market_logits: object) -> tuple[np.ndarray, dict]:
    features = _as_matrix(standardized_fit, "standardized fit features")
    labels = _as_binary(outcomes, features.shape[0])
    offsets = np.asarray(fit_market_logits, dtype=np.float64)
    if offsets.shape != (features.shape[0],) or not np.all(np.isfinite(offsets)):
        raise ValueError("fit market logits must be finite and aligned")

    def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
        return offset_objective_gradient(theta, features, labels, offsets)

    initial = np.zeros(features.shape[1] + 1, dtype=np.float64)
    result = minimize(
        objective, initial, method="L-BFGS-B", jac=True,
        options={"maxiter": 1000, "gtol": 1e-8, "ftol": 1e-12},
    )
    parameters = np.asarray(result.x, dtype=np.float64)
    final_objective, final_gradient = objective(parameters)
    gradient_infinity_norm = float(np.max(np.abs(final_gradient)))
    if (not bool(result.success) or not math.isfinite(final_objective)
            or not np.all(np.isfinite(parameters))
            or not np.all(np.isfinite(final_gradient))
            or gradient_infinity_norm > 1e-5):
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
        "intercept": float(parameters[0]),
        "non_intercept_coefficients": [float(value) for value in parameters[1:]],
        "market_logit_coefficient_fixed": 1.0,
        "intercept_penalized": False,
        "retry_count": 0,
    }


def _fit_and_predict(rows: Sequence[base.InGameRow], folds: Sequence[dict],
                     ) -> tuple[list[dict], list[dict]]:
    by_date: dict[str, list[base.InGameRow]] = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    predictions: list[dict] = []
    fold_reports = []
    fit_count = 0
    for fold in folds:
        check_rows = sorted(
            [row for date in fold["check_dates"] for row in by_date.get(date, [])],
            key=lambda row: row.key,
        )
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
        if not fit_rows or not check_rows or len({
                row.trusted["outcome"] for row in fit_rows}) != 2:
            raise ValueError(f"fold {fold['fold']} has an invalid fit/check population")
        validate_train_evaluation_rows(
            [row.trusted for row in fit_rows], [row.trusted for row in check_rows]
        )
        y_fit = np.asarray([row.trusted["outcome"] for row in fit_rows], dtype=np.float64)
        y_check = [row.trusted["outcome"] for row in check_rows]
        fit_offsets = np.asarray([row.market_features[0] for row in fit_rows], dtype=np.float64)
        check_offsets = np.asarray([row.market_features[0] for row in check_rows], dtype=np.float64)
        raw_market = [row.trusted["market_probability"] for row in check_rows]
        predicted: dict[str, list[float]] = {}
        optimizer_reports = {}
        for arm in OFFSET_ARMS:
            fit_matrix = np.asarray([_features(row, arm) for row in fit_rows], dtype=np.float64)
            check_matrix = np.asarray([_features(row, arm) for row in check_rows], dtype=np.float64)
            if arm == ARM_INTERCEPT:
                fit_matrix = fit_matrix.reshape(len(fit_rows), 0)
                check_matrix = check_matrix.reshape(len(check_rows), 0)
            scaled_fit, scaled_check, scaling = _scale_fold(fit_matrix, check_matrix, arm)
            parameters, optimizer = fit_offset_arm(scaled_fit, y_fit, fit_offsets)
            fit_count += 1
            values = offset_probabilities(parameters, scaled_check, check_offsets)
            predicted[arm] = [
                validate_probability(float(value), DEFAULT_PROBABILITY_POLICY, arm)
                for value in values
            ]
            optimizer_reports[arm] = {
                "component_spec_sha256": ARM_COMPONENT_SPEC_SHA256[arm],
                "feature_names": list(_feature_names(arm)),
                "scaling": scaling,
                "conditioning": _conditioning(scaled_fit),
                "optimizer": optimizer,
            }
        arms = {
            "raw_market": settlement._simple_metrics(y_check, raw_market),
            **{
                arm: settlement._simple_metrics(y_check, predicted[arm])
                for arm in OFFSET_ARMS
            },
        }
        fold_reports.append({
            "fold": fold["fold"],
            "fit_dates": fold["fit_dates"],
            "check_dates": fold["check_dates"],
            "fit_events": len(fit_rows),
            "check_events": len(check_rows),
            "fit_label_unavailable_game_ids": unavailable,
            "fit_label_unavailable_game_ids_sha256": settlement._digest(unavailable),
            "arms": arms,
            "score_time_minus_linear_brier": (
                arms[ARM_SCORE_TIME]["brier"] - arms[ARM_LINEAR]["brier"]
            ),
            "optimizer_reports": optimizer_reports,
            "same_rows_labels_offsets_trainer_and_budget": True,
        })
        for index, row in enumerate(check_rows):
            item = {"fold": fold["fold"], "row": row, "raw_market": raw_market[index]}
            item.update({arm: predicted[arm][index] for arm in OFFSET_ARMS})
            predictions.append(item)
    if fit_count != 12:
        raise RuntimeError(f"exactly 12 fits required, observed {fit_count}")
    keys = [item["row"].key for item in predictions]
    if len(keys) != len(set(keys)):
        raise ValueError("an event appears in more than one check fold")
    return predictions, fold_reports


def _loss(outcome: int, probability: float, metric: str) -> float:
    if metric == "brier":
        return brier_loss(probability, outcome)
    if metric == "log_loss":
        return bounded_log_loss(probability, outcome)
    raise ValueError("unknown metric")


def _aggregate(predictions: Sequence[dict]) -> dict:
    outcomes = [item["row"].trusted["outcome"] for item in predictions]
    result = {}
    for arm in ALL_ARMS:
        values = [item[arm] for item in predictions]
        result[arm] = settlement._simple_metrics(outcomes, values)
        result[arm]["reliability_table"] = base._reliability_table(outcomes, values)
    return result


def _paired_records(predictions: Sequence[dict]) -> list[dict]:
    records = []
    for item in predictions:
        row = item["row"]
        record = {
            "game_id": row.game_id, "game_date": row.game_date,
            "game_week": row.game_week, "outcome": row.trusted["outcome"],
        }
        for metric in ("brier", "log_loss"):
            losses = {arm: _loss(row.trusted["outcome"], item[arm], metric) for arm in ALL_ARMS}
            for comparison, candidate, reference in (
                    ("score_time_minus_linear", ARM_SCORE_TIME, ARM_LINEAR),
                    ("score_time_minus_raw_market", ARM_SCORE_TIME, "raw_market"),
                    ("linear_minus_raw_market", ARM_LINEAR, "raw_market")):
                record[f"{comparison}_{metric}"] = losses[candidate] - losses[reference]
        records.append(record)
    return records


def _paired_evidence(records: Sequence[dict]) -> dict:
    evidence = {}
    for comparison in (
            "score_time_minus_linear", "score_time_minus_raw_market",
            "linear_minus_raw_market"):
        evidence[comparison] = {}
        for metric in ("brier", "log_loss"):
            key = f"{comparison}_{metric}"
            evidence[comparison][metric] = {
                "delta_convention": f"{comparison}; negative loss is better",
                "equal_event_mean": math.fsum(row[key] for row in records) / len(records),
                "by_event": [
                    {"game_id": row["game_id"], "game_date": row["game_date"],
                     "game_week": row["game_week"], key: row[key]}
                    for row in records
                ],
                "by_schedule_date": base._group_means(records, "game_date", key),
                "schedule_date_interval": base._group_bootstrap(records, "game_date", key),
                "observed_game_week_interval": base._group_bootstrap(records, "game_week", key),
            }
    return evidence


def score_time_decision(aggregate: Mapping[str, dict], folds: Sequence[dict],
                        ) -> tuple[str, dict]:
    nonlinear = aggregate[ARM_SCORE_TIME]
    linear = aggregate[ARM_LINEAR]
    raw = aggregate["raw_market"]
    wins = [
        fold["arms"][ARM_SCORE_TIME]["brier"] < fold["arms"][ARM_LINEAR]["brier"]
        for fold in folds
    ]
    conditions = {
        "score_time_brier_below_linear_offset": nonlinear["brier"] < linear["brier"],
        "score_time_log_loss_below_linear_offset": nonlinear["log_loss"] < linear["log_loss"],
        "score_time_brier_fold_wins_at_least_3_of_4": sum(wins) >= 3,
        "score_time_brier_below_raw_market": nonlinear["brier"] < raw["brier"],
        "score_time_log_loss_below_raw_market": nonlinear["log_loss"] < raw["log_loss"],
        "fold_brier_wins": wins,
    }
    representation = all(conditions[key] for key in (
        "score_time_brier_below_linear_offset",
        "score_time_log_loss_below_linear_offset",
        "score_time_brier_fold_wins_at_least_3_of_4",
    ))
    incumbent = all(conditions[key] for key in (
        "score_time_brier_below_raw_market", "score_time_log_loss_below_raw_market",
    ))
    if representation and incumbent:
        decision = "LINEAR_REPRESENTATION_FAILURE_SUPPORTED"
    elif not representation:
        decision = "SCORE_TIME_K4_HYPOTHESIS_REFUTED"
    else:
        decision = "SCORE_TIME_K4_NARROWING_INCONCLUSIVE"
    return decision, conditions


def _write_predictions(path: Path, predictions: Sequence[dict]) -> None:
    fields = (
        "fold", "game_id", "game_date", "game_week", "event_id", "market_id",
        "cutoff_ms", "outcome_available_ms", "outcome", "raw_market_probability",
        "market_offset_intercept_probability", "market_offset_linear_state_probability",
        "market_offset_score_time_state_probability",
    )
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in predictions:
            row = item["row"]
            writer.writerow({
                "fold": item["fold"], "game_id": row.game_id,
                "game_date": row.game_date, "game_week": row.game_week,
                "event_id": row.trusted["event_id"], "market_id": row.trusted["market_id"],
                "cutoff_ms": row.trusted["cutoff_ms"],
                "outcome_available_ms": row.trusted["outcome_available_ms"],
                "outcome": row.trusted["outcome"],
                "raw_market_probability": item["raw_market"],
                "market_offset_intercept_probability": item[ARM_INTERCEPT],
                "market_offset_linear_state_probability": item[ARM_LINEAR],
                "market_offset_score_time_state_probability": item[ARM_SCORE_TIME],
            })
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def run(source_root: Path, output: Path, *, expected_events: int = EXPECTED_EVENTS,
        expected_dates: int = EXPECTED_DATES, allow_test_paths: bool = False,
        generated_utc: str | None = None) -> dict:
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    _validate_frozen_dependencies()
    _validate_v0_artifact()
    cohort = base._validate_source(
        source_root, expected_events=expected_events,
        expected_dates=expected_dates, allow_test_paths=allow_test_paths,
    )
    pbp_receipts = base._validate_pbp_receipts(source_root, cohort)
    output.mkdir(parents=True, exist_ok=False)
    try:
        state_path = output / "checkpoint_state.csv"
        states = base._extract_state_rows(source_root, state_path)
        materialized = []
        exclusions = []
        for ordinal, item in enumerate(cohort):
            state = states[item["game_id"]]
            _validate_extracted_score_time(state)
            try:
                materialized.append(base._load_dynamic_market(source_root, item, state))
            except settlement.EventExclusion as error:
                exclusions.append({
                    "source_ordinal": ordinal, "game_id": item["game_id"],
                    "game_date": item["game_date"], "reason": error.code,
                    "detail": str(error)[:400],
                })
        if len(materialized) + len(exclusions) != expected_events:
            raise RuntimeError("materialized and excluded events do not reconcile")
        expected_exclusions = [
            ("2025_04_GB_DAL", "unresolved_outcome"),
            ("2025_05_TEN_ARI", "market_trade_too_stale"),
        ]
        if (len(materialized) != EXPECTED_MATERIALIZED_EVENTS
                or [(item["game_id"], item["reason"]) for item in exclusions]
                != expected_exclusions
                or _sha256(state_path) != EXPECTED_CHECKPOINT_STATE_SHA256
                or settlement._digest([list(row.key) for row in sorted(
                    materialized, key=lambda row: row.key
                )]) != EXPECTED_MATERIALIZED_KEY_SHA256):
            raise ValueError("exact v0 checkpoint/attrition boundary changed")
        materialized.sort(key=lambda row: row.key)
        folds = settlement.chronological_date_folds(
            [item["game_date"] for item in cohort], expected_dates=expected_dates
        )
        input_receipts = {
            "schema": "nfl_ingame_market_offset_score_time_inputs_v1",
            "task_id": TASK_ID,
            "source_dataset_id": source_root.name,
            "source_manifest_sha256": settlement._sha256(source_root / "manifest.json"),
            "cohort_sha256": settlement._sha256(source_root / "cohort.csv"),
            "checkpoint_extractor_sha256": _sha256(EXTRACTOR),
            "checkpoint_state_sha256": _sha256(state_path),
            "runner_source_sha256": _sha256(Path(__file__)),
            "v0_runner_sha256": _sha256(Path(base.__file__)),
            "settlement_dependency_sha256": _sha256(Path(settlement.__file__)),
            "probability_contract_sha256": _sha256(Path(probability_contract.__file__)),
            "proper_scoring_dependency_sha256": _sha256(Path(proper_scoring.__file__)),
            "controller_log_sha256": _sha256(CONTROLLER_LOG),
            "v0_result_review_sha256": _sha256(V0_RESULT_REVIEW),
            "v0_artifact_root": str(V0_ARTIFACT_ROOT),
            "v0_artifact_hashes": V0_ARTIFACT_HASHES,
            "pbp_receipts": pbp_receipts,
            "materialized_receipts": [row.source_receipt for row in materialized],
            "route_dev_opened": False, "sealed_final_opened": False,
            "external_fetch": False, "provider_cost_usd": "0",
        }
        exclusions_record = {
            "schema": "nfl_ingame_market_offset_score_time_exclusions_v1",
            "source_events": expected_events, "materialized_events": len(materialized),
            "excluded_events": len(exclusions),
            "reconciles_to_source_denominator": len(materialized) + len(exclusions) == expected_events,
            "exclusions": exclusions,
        }
        base._atomic_json(output / "input_receipts.json", input_receipts)
        base._atomic_json(output / "exclusions.json", exclusions_record)
        lock = {
            "schema": "nfl_ingame_market_offset_score_time_pre_score_lock_v1",
            "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "task_id": TASK_ID, "question_id": QUESTION_ID,
            "question_record_sha256": QUESTION_RECORD_SHA256,
            "question": (
                "Does a fixed market-logit offset plus score_time_ratio_k4 recover stable "
                "incremental settlement information missed by additive linear state?"
            ),
            "research_parent": {
                "task_id": "InGameWinProbabilityTrainDiagnostic-v0",
                "branch": "market_plus_state_model negative branch",
                "scorecard_sha256": V0_ARTIFACT_HASHES["scorecard.json"],
                "result_review_sha256": V0_RESULT_REVIEW_SHA256,
            },
            "comparison_incumbent": "v0 raw_market on exact common mask",
            "separate_from_pregame_task": True,
            "source_denominator_events": EXPECTED_EVENTS,
            "materialized_events": EXPECTED_MATERIALIZED_EVENTS,
            "source_identity": {
                "source_manifest_sha256": settlement._sha256(source_root / "manifest.json"),
                "cohort_sha256": settlement._sha256(source_root / "cohort.csv"),
                "checkpoint_extractor_sha256": _sha256(EXTRACTOR),
                "checkpoint_state_sha256": _sha256(state_path),
                "runner_source_sha256": _sha256(Path(__file__)),
                "v0_artifact_hashes": V0_ARTIFACT_HASHES,
            },
            "expected_exclusions": expected_exclusions,
            "expected_check_events": EXPECTED_CHECK_EVENTS,
            "expected_check_key_sha256": EXPECTED_CHECK_KEY_SHA256,
            "checkpoint_rule": (
                "exact v0 first nondeleted Q3 pre-play row with clockTime<=08:00 and "
                "complete causal state; selection independent of prices/outcomes"
            ),
            "maximum_trade_staleness_seconds": base.MAX_TRADE_STALENESS_SECONDS,
            "same_second_trade_rule": "integer-second market trade must strictly precede PBP event second",
            "availability_boundary": (
                "historical event wall clock only; provider publish/local receive timestamps absent"
            ),
            "arms": {
                "raw_market": "unfitted v0 decision-time market incumbent",
                ARM_INTERCEPT: {"features": [], "component_spec_sha256": ARM_COMPONENT_SPEC_SHA256[ARM_INTERCEPT]},
                ARM_LINEAR: {"features": list(LINEAR_FEATURE_NAMES), "component_spec_sha256": ARM_COMPONENT_SPEC_SHA256[ARM_LINEAR]},
                ARM_SCORE_TIME: {"features": list(SCORE_TIME_FEATURE_NAMES), "component_spec_sha256": ARM_COMPONENT_SPEC_SHA256[ARM_SCORE_TIME]},
            },
            "score_time_ratio_k4": (
                "home_score_diff_pre * exp(4 * (1 - clip(regulation_seconds_remaining,0,3600)/3600))"
            ),
            "solver": SOLVER_SPEC,
            "preprocessing": (
                "fit-fold StandardScaler on continuous state columns only; binary/down one-hot "
                "unscaled; market logit is never scaled and remains coefficient one"
            ),
            "folds": folds, "expected_fit_events": list(EXPECTED_FIT_EVENTS),
            "expected_check_events_by_fold": list(EXPECTED_CHECK_EVENTS_BY_FOLD),
            "fit_budget": 12, "automatic_retries": 0,
            "primary_metric": "equal-event Brier on one identical checkpoint per game",
            "secondary": [
                "log loss", "calibration slope/intercept", "per-fold paired deltas",
                "per-date paired deltas", "schedule-date interval", "observed-week sensitivity",
            ],
            "support_rule": (
                "score-time Brier and log loss below both linear-offset state and raw market, "
                "and Brier below linear-offset state in at least 3/4 folds"
            ),
            "refute_rule": (
                "score-time fails either aggregate proper-score comparison to linear-offset "
                "state, or wins Brier in fewer than 3/4 folds"
            ),
            "inconclusive_rule": (
                "score-time passes the complete linear-offset representation rule but does not "
                "beat raw market on both aggregate proper scores"
            ),
            "stop_rule": "one frozen run; any identity/boundary/optimizer failure is terminal; no retry",
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "materialized_key_sha256": EXPECTED_MATERIALIZED_KEY_SHA256,
            "resource_cap": {
                "local_fits": 12, "wall_minutes": 10, "rss_gib": 1,
                "network_bytes": 0, "provider_calls": 0, "provider_cost_usd": "0",
            },
            "route_dev_opened": False, "sealed_final_opened": False,
            "external_fetch": False, "paid_provider": False,
            "provider_cost_usd": "0", "promotion_authorized": False,
        }
        base._atomic_json(output / "pre_score_lock.json", lock)

        predictions, fold_reports = _fit_and_predict(materialized, folds)
        check_hash = settlement._digest([list(item["row"].key) for item in predictions])
        if (len(predictions) != EXPECTED_CHECK_EVENTS
                or check_hash != EXPECTED_CHECK_KEY_SHA256
                or tuple(item["fit_events"] for item in fold_reports) != EXPECTED_FIT_EVENTS
                or tuple(item["check_events"] for item in fold_reports) != EXPECTED_CHECK_EVENTS_BY_FOLD
                or any(item["fit_label_unavailable_game_ids"] for item in fold_reports)):
            raise ValueError("v0 chronological common mask or label availability changed")
        aggregate = _aggregate(predictions)
        decision, conditions = score_time_decision(aggregate, fold_reports)
        records = _paired_records(predictions)
        scorecard = {
            "schema": "nfl_ingame_market_offset_score_time_scorecard_v1",
            "task_id": TASK_ID, "representation_decision": decision,
            "decision_conditions": conditions,
            "source_denominator": {
                "events": expected_events, "dates": expected_dates,
                "materialized_events": len(materialized), "excluded_events": len(exclusions),
                "materialization_coverage": len(materialized) / expected_events,
                "check_events": len(predictions),
                "check_dates": len({item["row"].game_date for item in predictions}),
                "check_game_weeks": len({item["row"].game_week for item in predictions}),
            },
            "identical_masks": {
                "all_four_arms_same_rows_labels_and_checkpoints": True,
                "check_key_sha256": check_hash,
                "matches_v0_check_key_sha256": check_hash == EXPECTED_CHECK_KEY_SHA256,
                "one_checkpoint_per_game": len(predictions) == len({item["row"].game_id for item in predictions}),
            },
            "model_fits": 12, "aggregate": aggregate,
            "deltas": {
                "score_time_minus_linear": {
                    metric: aggregate[ARM_SCORE_TIME][metric] - aggregate[ARM_LINEAR][metric]
                    for metric in ("brier", "log_loss")
                },
                "score_time_minus_raw_market": {
                    metric: aggregate[ARM_SCORE_TIME][metric] - aggregate["raw_market"][metric]
                    for metric in ("brier", "log_loss")
                },
            },
            "folds": fold_reports,
            "paired_grouped_evidence": _paired_evidence(records),
            "evidence_classification": {
                "score_time_vs_linear_offset": "prediction-representation evidence",
                "offset_arms_vs_raw_market": "model evidence on fixed in-game data",
                "broader_PBP_data_increment": "not resolved by one representation",
                "research_mechanism": "not tested",
            },
            "inference_boundary": (
                "repeatedly inspected opened-Train historical diagnostic; no realtime, "
                "untouched OOS, promotion, deployment, PnL, or cross-task claim"
            ),
            "cross_task_comparison_forbidden": "do not compare numeric scores with pregame task",
            "route_dev_opened": False, "sealed_final_opened": False,
            "provider_cost_usd": "0", "promotion_authorized": False,
        }
        _write_predictions(output / "predictions.csv", predictions)
        base._atomic_json(output / "scorecard.json", scorecard)
        manifest = {
            "schema": "nfl_ingame_market_offset_score_time_manifest_v1",
            "complete": True,
            "completed_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "task_id": TASK_ID,
            "pre_score_lock_sha256": _sha256(output / "pre_score_lock.json"),
            "input_receipts_sha256": _sha256(output / "input_receipts.json"),
            "exclusions_sha256": _sha256(output / "exclusions.json"),
            "predictions_sha256": _sha256(output / "predictions.csv"),
            "scorecard_sha256": _sha256(output / "scorecard.json"),
            "source_events": expected_events, "materialized_events": len(materialized),
            "excluded_events": len(exclusions), "check_events": len(predictions),
            "model_fits": 12, "representation_decision": decision,
            "historical_event_clock_only": True,
            "route_dev_opened": False, "sealed_final_opened": False,
            "external_fetch": False, "paid_provider": False,
            "provider_cost_usd": "0", "promotion_authorized": False,
        }
        base._atomic_json(output / "manifest.json", manifest)
        return manifest
    except Exception as error:
        if output.exists() and not (output / "manifest.json").exists():
            base._atomic_json(output / "failure.json", {
                "schema": "nfl_ingame_market_offset_score_time_failure_v1",
                "error_type": type(error).__name__, "error": str(error)[:1200],
                "route_dev_opened": False, "sealed_final_opened": False,
                "external_fetch": False, "paid_provider": False,
                "provider_cost_usd": "0", "promotion_authorized": False,
            })
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source_root, args.output)
    print(json.dumps({
        "complete": result["complete"], "task_id": result["task_id"],
        "source_events": result["source_events"],
        "materialized_events": result["materialized_events"],
        "excluded_events": result["excluded_events"],
        "check_events": result["check_events"], "model_fits": result["model_fits"],
        "representation_decision": result["representation_decision"],
        "provider_cost_usd": result["provider_cost_usd"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
