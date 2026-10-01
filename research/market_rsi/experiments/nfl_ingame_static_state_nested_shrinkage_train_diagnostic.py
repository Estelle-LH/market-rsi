#!/usr/bin/env python3
"""Nested prior-only shrinkage diagnostic for the frozen NFL in-game state.

This opened-Train Discovery runner changes only the trainer applied to the
exact nine static v0 checkpoint-state features.  It selects one ridge penalty
inside each outer fit using three strictly earlier two-date checks, refits once
on the full outer fit, and compares the candidate with raw market and the
hash-bound frozen v1 linear-offset predictions.  It is not untouched OOS,
realtime, promotion, PnL, or a cross-task comparison.
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

from minimal_prediction_loop import probability_contract, proper_scoring
from minimal_prediction_loop.probability_contract import (
    DEFAULT_PROBABILITY_POLICY,
    validate_probability,
    validate_train_evaluation_rows,
)
from experiments import nfl_ingame_win_probability_train_diagnostic as base
from experiments import nfl_ingame_market_offset_score_time_train_diagnostic as linear
from experiments import nfl_settlement_probability_train_diagnostic as settlement


TASK_ID = "InGameStaticStateNestedShrinkageDiagnostic-v2"
QUESTION_ID = "ingame-static-state-nested-shrinkage-v2-q1"
QUESTION_DIGEST = "8935256d05239c242b6492b29338c8c50381e6988ac69cc0acc3642adedc671c"
HYPOTHESIS_DIGEST = "c11b589592bb2c62c5c9cc7d11bdaf546cba425adfdc3ec68c15daf28c675d9c"
RULE_DIGEST = "b91582ce2d23dac111b50457e78c8a451407695d47f5a61aa0f1252fd857251d"
POOL_PLAN_DIGEST = "415c47dd6f8a6ca99df78a03f102256ba981923b8bfb0992a8f6aea02b87e0a8"
CONTROLLER_LOG = Path(__file__).parents[1] / "supervisor_harness" / (
    "AGENT_LOG_INGAME_DISCOVERY_V3_TWO_MEMBER_POOL_CONTROLLER_2026-09-29.md"
)
CONTROLLER_LOG_SHA256 = "a2c1c060b3ddf63ee3c0e1b6f7baebdba08b550c91be0a7d5585ead9b5dac18f"

SOURCE_ROOT = base.SOURCE_ROOT
PERSISTENT_ARTIFACT_ROOT = base.PERSISTENT_ARTIFACT_ROOT
EXPECTED_EVENTS = base.EXPECTED_EVENTS
EXPECTED_DATES = base.EXPECTED_DATES
EXTRACTOR = base.EXTRACTOR
BOOTSTRAP_SEED = base.BOOTSTRAP_SEED
BOOTSTRAP_REPLICATES = base.BOOTSTRAP_REPLICATES
EXPECTED_MATERIALIZED_EVENTS = linear.EXPECTED_MATERIALIZED_EVENTS
EXPECTED_CHECK_EVENTS = linear.EXPECTED_CHECK_EVENTS
EXPECTED_FIT_EVENTS = linear.EXPECTED_FIT_EVENTS
EXPECTED_CHECK_EVENTS_BY_FOLD = linear.EXPECTED_CHECK_EVENTS_BY_FOLD
EXPECTED_MATERIALIZED_KEY_SHA256 = linear.EXPECTED_MATERIALIZED_KEY_SHA256
EXPECTED_CHECK_KEY_SHA256 = linear.EXPECTED_CHECK_KEY_SHA256
EXPECTED_CHECKPOINT_STATE_SHA256 = linear.EXPECTED_CHECKPOINT_STATE_SHA256
V0_ARTIFACT_ROOT = linear.V0_ARTIFACT_ROOT
V0_ARTIFACT_HASHES = linear.V0_ARTIFACT_HASHES

V1_CONTROL_ROOT = Path(
    "/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/"
    "artifacts/nfl-ingame-market-offset-score-time-train-diagnostic-20260929-01"
)
V1_CONTROL_HASHES = {
    "checkpoint_state.csv": "235510db382de2e4b321f11db80b9f5b969c094eb2d122b18ab373e6d31ae96e",
    "exclusions.json": "f8aafae494b633ba32b0e786b49391008c544dd9aa1bb5736916cdbff46aa704",
    "input_receipts.json": "6f8b4c196f82fe7e9bb4ab75952eb66aaecdfb96040ff22beb2b71738bd1ebe8",
    "manifest.json": "b9840bc2fe6258be40f61800fa212e157821230bd3e5c0af6bc8bf43f537ab4b",
    "pre_score_lock.json": "4e578c6cdd94297ff8ab3753fb36f384b2db9bbe46a442d6f3f7f54c45f2a5fa",
    "predictions.csv": "f79a3f61a8bdcb71bcdf0f673bb87cfffe5a600a52ed523ec854978fa01fda54",
    "scorecard.json": "2301883843090a09326f03403be9564d6fbeddd962c3cc71789eba7b5155bcaf",
}
V1_RESULT_REVIEW = Path(__file__).parents[1] / "supervisor_harness" / (
    "AGENT_LOG_INGAME_MARKET_OFFSET_SCORE_TIME_V1_RESULT_INDEPENDENT_REVIEW_2026-09-29.md"
)
V1_RESULT_REVIEW_SHA256 = "2eb30f66be68721957e0cae68899ffb23e35a15d59587af535fea4359217f688"
V0_RESULT_REVIEW = linear.V0_RESULT_REVIEW
V0_RESULT_REVIEW_SHA256 = linear.V0_RESULT_REVIEW_SHA256
BASE_RUNNER_SHA256 = "e61668c7e29cf4dda95f6cc315b248dbe6744a9dcc0ae0cd6077d880ca6265b7"
LINEAR_RUNNER_SHA256 = "6194d25712df0e251fe0c56c671557967f8c7f5f7e62c28ca9981c09a3adf120"
EXTRACTOR_SHA256 = "37a26997406de0e54bd9d91de10e7417a8b340c68b675892c4f16e9a51675163"

ARM_RAW = "raw_market"
ARM_CONTROL = "frozen_c1_linear_control"
ARM_CANDIDATE = "nested_shrinkage_static_state"
ALL_ARMS = (ARM_RAW, ARM_CONTROL, ARM_CANDIDATE)
LAMBDA_GRID = (0.25, 1.0, 4.0, 16.0, 64.0)
INNER_CHECK_DATES = 2
INNER_SPLITS = 3
MAX_MODEL_FITS = 64
FEATURE_NAMES = base.STATE_FEATURE_NAMES
CONTINUOUS_INDICES = linear.LINEAR_CONTINUOUS_INDICES
SOLVER_SPEC = {
    "optimizer": "scipy.optimize.minimize",
    "method": "L-BFGS-B",
    "maxiter": 1000,
    "gtol": 1e-8,
    "ftol": 1e-12,
    "analytic_gradient": True,
    "objective": "sum binary NLL + 0.5 * lambda * L2(non-intercept coefficients)",
    "lambda_grid": list(LAMBDA_GRID),
    "market_logit_coefficient": 1.0,
    "intercept_penalized": False,
    "automatic_retries": 0,
}
CANDIDATE_COMPONENT_SPEC = {
    "features": list(FEATURE_NAMES),
    "continuous_indices": list(CONTINUOUS_INDICES),
    "market_logit_coefficient": 1.0,
    "intercept_penalized": False,
    "lambda_grid": list(LAMBDA_GRID),
    "inner_checks": "last six outer-fit dates as three consecutive two-date blocks",
    "selection": "pooled equal-event inner Brier; exact ties choose largest lambda",
    "outer_refits": 4,
    "maximum_model_fits": MAX_MODEL_FITS,
}
CANDIDATE_COMPONENT_SPEC_SHA256 = settlement._digest(CANDIDATE_COMPONENT_SPEC)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_frozen_file(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or path.is_symlink() or _sha256(path) != expected:
        raise ValueError(f"frozen {label} is missing, symlinked, or hash-changed")


def _validate_frozen_dependencies() -> None:
    _require_frozen_file(Path(base.__file__), BASE_RUNNER_SHA256, "v0 runner")
    _require_frozen_file(Path(linear.__file__), LINEAR_RUNNER_SHA256, "v1 control runner")
    _require_frozen_file(EXTRACTOR, EXTRACTOR_SHA256, "checkpoint extractor")
    _require_frozen_file(CONTROLLER_LOG, CONTROLLER_LOG_SHA256, "Controller pool decision")
    _require_frozen_file(V0_RESULT_REVIEW, V0_RESULT_REVIEW_SHA256, "v0 result review")
    _require_frozen_file(V1_RESULT_REVIEW, V1_RESULT_REVIEW_SHA256, "v1 result review")
    linear._validate_v0_artifact(V0_ARTIFACT_ROOT)


def _read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        return tuple(reader.fieldnames or ()), list(reader)


def _control_key(row: Mapping[str, str]) -> tuple[str, str, int]:
    try:
        cutoff = int(row["cutoff_ms"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("frozen control cutoff_ms is invalid") from error
    return str(row.get("event_id", "")), str(row.get("market_id", "")), cutoff


def _validate_v1_control(root: Path = V1_CONTROL_ROOT) -> dict:
    root = Path(root).resolve()
    if not root.is_dir() or root.is_symlink():
        raise ValueError("frozen v1 control artifact is unavailable")
    if sorted(path.name for path in root.iterdir()) != sorted(V1_CONTROL_HASHES):
        raise ValueError("frozen v1 control artifact file set changed")
    for name, digest in V1_CONTROL_HASHES.items():
        _require_frozen_file(root / name, digest, f"v1 control artifact {name}")
    manifest = settlement._strict_json(root / "manifest.json")
    scorecard = settlement._strict_json(root / "scorecard.json")
    if not isinstance(manifest, dict) or not isinstance(scorecard, dict):
        raise ValueError("frozen v1 manifest/scorecard must be objects")
    if (manifest.get("complete") is not True
            or manifest.get("task_id") != "InGameMarketOffsetScoreTimeDiagnostic-v1"
            or manifest.get("predictions_sha256") != V1_CONTROL_HASHES["predictions.csv"]
            or manifest.get("scorecard_sha256") != V1_CONTROL_HASHES["scorecard.json"]
            or manifest.get("check_events") != EXPECTED_CHECK_EVENTS
            or manifest.get("route_dev_opened") is not False
            or manifest.get("sealed_final_opened") is not False
            or manifest.get("external_fetch") is not False
            or manifest.get("paid_provider") is not False
            or manifest.get("provider_cost_usd") != "0"):
        raise ValueError("frozen v1 control completion or boundary changed")
    fields, rows = _read_csv(root / "predictions.csv")
    expected_fields = (
        "fold", "game_id", "game_date", "game_week", "event_id", "market_id",
        "cutoff_ms", "outcome_available_ms", "outcome", "raw_market_probability",
        "market_offset_intercept_probability", "market_offset_linear_state_probability",
        "market_offset_score_time_state_probability",
    )
    if fields != expected_fields or len(rows) != EXPECTED_CHECK_EVENTS:
        raise ValueError("frozen v1 control prediction schema/population changed")
    by_key: dict[tuple[str, str, int], dict] = {}
    ordered_keys = []
    for row in rows:
        key = _control_key(row)
        if key in by_key or not all(key[:2]):
            raise ValueError("frozen v1 control has duplicate or blank keys")
        try:
            fold = int(row["fold"])
            outcome = int(row["outcome"])
            raw_probability = float(row["raw_market_probability"])
            control_probability = float(row["market_offset_linear_state_probability"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("frozen v1 control row is nonnumeric") from error
        if fold not in (1, 2, 3, 4) or outcome not in (0, 1):
            raise ValueError("frozen v1 control fold/outcome changed")
        raw_probability = validate_probability(
            raw_probability, DEFAULT_PROBABILITY_POLICY, "frozen raw market"
        )
        control_probability = validate_probability(
            control_probability, DEFAULT_PROBABILITY_POLICY, "frozen linear control"
        )
        by_key[key] = {
            "fold": fold, "game_id": row["game_id"], "game_date": row["game_date"],
            "game_week": row["game_week"], "outcome": outcome,
            "raw_market_probability": raw_probability,
            "control_probability": control_probability,
        }
        ordered_keys.append(list(key))
    if settlement._digest(ordered_keys) != EXPECTED_CHECK_KEY_SHA256:
        raise ValueError("frozen v1 control common mask changed")
    masks = scorecard.get("identical_masks", {})
    if (masks.get("check_key_sha256") != EXPECTED_CHECK_KEY_SHA256
            or masks.get("all_four_arms_same_rows_labels_and_checkpoints") is not True):
        raise ValueError("frozen v1 control mask evidence changed")
    return {"manifest": manifest, "scorecard": scorecard, "rows_by_key": by_key}


def nested_objective_gradient(
    parameters: object,
    standardized_features: object,
    outcomes: object,
    market_logits: object,
    *,
    penalty_lambda: float,
) -> tuple[float, np.ndarray]:
    if float(penalty_lambda) not in LAMBDA_GRID:
        raise ValueError("penalty lambda is outside the frozen grid")
    return linear.offset_objective_gradient(
        parameters, standardized_features, outcomes, market_logits,
        penalty_lambda=float(penalty_lambda),
    )


def fit_nested_offset(
    standardized_fit: object,
    outcomes: object,
    fit_market_logits: object,
    *,
    penalty_lambda: float,
) -> tuple[np.ndarray, dict]:
    features = linear._as_matrix(
        standardized_fit, "standardized fit features", columns=len(FEATURE_NAMES)
    )
    labels = linear._as_binary(outcomes, features.shape[0])
    offsets = np.asarray(fit_market_logits, dtype=np.float64)
    if offsets.shape != (features.shape[0],) or not np.all(np.isfinite(offsets)):
        raise ValueError("fit market logits must be finite and aligned")

    def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
        return nested_objective_gradient(
            theta, features, labels, offsets, penalty_lambda=penalty_lambda
        )

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
            "nested offset optimizer failed frozen convergence checks: "
            f"lambda={penalty_lambda}, success={result.success}, status={result.status}, "
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
        "penalty_lambda": float(penalty_lambda),
        "intercept": float(parameters[0]),
        "non_intercept_coefficients": [float(value) for value in parameters[1:]],
        "market_logit_coefficient_fixed": 1.0,
        "intercept_penalized": False,
        "retry_count": 0,
    }


def inner_date_splits(outer_fit_dates: Sequence[str]) -> list[dict]:
    dates = list(outer_fit_dates)
    if len(dates) < 7 or dates != sorted(dates) or len(set(dates)) != len(dates):
        raise ValueError("outer fit dates must be sorted, unique, and leave prior inner fit")
    recent = dates[-INNER_CHECK_DATES * INNER_SPLITS:]
    result = []
    for index in range(INNER_SPLITS):
        start = index * INNER_CHECK_DATES
        check_dates = recent[start:start + INNER_CHECK_DATES]
        fit_dates = [value for value in dates if value < check_dates[0]]
        if (len(check_dates) != INNER_CHECK_DATES or not fit_dates
                or max(fit_dates) >= min(check_dates)):
            raise ValueError("inner split is not strictly chronological")
        result.append({
            "inner_split": index + 1,
            "fit_dates": fit_dates,
            "check_dates": check_dates,
        })
    return result


def select_lambda(pooled_brier_by_lambda: Mapping[float, float]) -> float:
    if set(pooled_brier_by_lambda) != set(LAMBDA_GRID):
        raise ValueError("inner selection must score the exact lambda grid")
    checked = {}
    for value in LAMBDA_GRID:
        loss = pooled_brier_by_lambda[value]
        if isinstance(loss, bool) or not math.isfinite(float(loss)) or float(loss) < 0:
            raise ValueError("inner pooled Brier must be finite and nonnegative")
        checked[value] = float(loss)
    return min(LAMBDA_GRID, key=lambda value: (checked[value], -value))


def _strict_prior_rows(
    by_date: Mapping[str, list[base.InGameRow]],
    fit_dates: Sequence[str],
    check_rows: Sequence[base.InGameRow],
) -> tuple[list[base.InGameRow], list[str]]:
    if not check_rows:
        raise ValueError("chronological check block is empty")
    first_check_cutoff = min(row.trusted["cutoff_ms"] for row in check_rows)
    candidates = [row for date in fit_dates for row in by_date.get(date, [])]
    fit_rows = sorted(
        [row for row in candidates
         if row.trusted["outcome_available_ms"] < first_check_cutoff],
        key=lambda row: row.key,
    )
    unavailable = sorted(
        row.game_id for row in candidates
        if row.trusted["outcome_available_ms"] >= first_check_cutoff
    )
    if unavailable:
        raise ValueError("an earlier-date inner/outer fit label was not strictly available")
    if (not fit_rows or len(fit_rows) != len(candidates)
            or len({row.trusted["outcome"] for row in fit_rows}) != 2):
        raise ValueError("chronological fit population is empty, incomplete, or one-class")
    validate_train_evaluation_rows(
        [row.trusted for row in fit_rows], [row.trusted for row in check_rows]
    )
    return fit_rows, unavailable


def _state_matrix(rows: Sequence[base.InGameRow]) -> np.ndarray:
    matrix = np.asarray([row.state_features for row in rows], dtype=np.float64)
    return linear._as_matrix(matrix, "static state features", columns=len(FEATURE_NAMES))


def _fit_and_predict(
    rows: Sequence[base.InGameRow],
    folds: Sequence[dict],
    control_rows_by_key: Mapping[tuple[str, str, int], dict],
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
        outer_fit, outer_unavailable = _strict_prior_rows(
            by_date, fold["fit_dates"], check_rows
        )
        inner_reports = []
        pooled_sums = {value: 0.0 for value in LAMBDA_GRID}
        pooled_events = {value: 0 for value in LAMBDA_GRID}
        for inner in inner_date_splits(fold["fit_dates"]):
            inner_check = sorted(
                [row for date in inner["check_dates"] for row in by_date.get(date, [])],
                key=lambda row: row.key,
            )
            inner_fit, unavailable = _strict_prior_rows(
                by_date, inner["fit_dates"], inner_check
            )
            fit_matrix = _state_matrix(inner_fit)
            check_matrix = _state_matrix(inner_check)
            scaled_fit, scaled_check, scaling = linear._scale_fold(
                fit_matrix, check_matrix, linear.ARM_LINEAR
            )
            y_fit = np.asarray(
                [row.trusted["outcome"] for row in inner_fit], dtype=np.float64
            )
            y_check = [row.trusted["outcome"] for row in inner_check]
            fit_offsets = np.asarray(
                [row.market_features[0] for row in inner_fit], dtype=np.float64
            )
            check_offsets = np.asarray(
                [row.market_features[0] for row in inner_check], dtype=np.float64
            )
            lambda_reports = []
            for penalty_lambda in LAMBDA_GRID:
                parameters, optimizer = fit_nested_offset(
                    scaled_fit, y_fit, fit_offsets, penalty_lambda=penalty_lambda
                )
                fit_count += 1
                values = linear.offset_probabilities(parameters, scaled_check, check_offsets)
                probabilities = [
                    validate_probability(
                        float(value), DEFAULT_PROBABILITY_POLICY,
                        f"inner lambda {penalty_lambda}",
                    ) for value in values
                ]
                loss_sum = math.fsum(
                    proper_scoring.brier_loss(value, outcome)
                    for value, outcome in zip(probabilities, y_check, strict=True)
                )
                pooled_sums[penalty_lambda] += loss_sum
                pooled_events[penalty_lambda] += len(y_check)
                lambda_reports.append({
                    "penalty_lambda": penalty_lambda,
                    "check_events": len(y_check),
                    "check_brier": loss_sum / len(y_check),
                    "optimizer": optimizer,
                })
            inner_reports.append({
                **inner,
                "fit_events": len(inner_fit),
                "check_events": len(inner_check),
                "fit_label_unavailable_game_ids": unavailable,
                "scaling": scaling,
                "lambda_reports": lambda_reports,
            })
        event_counts = set(pooled_events.values())
        if len(event_counts) != 1 or 0 in event_counts:
            raise RuntimeError("inner lambdas were not scored on one identical pooled mask")
        pooled = {
            value: pooled_sums[value] / pooled_events[value] for value in LAMBDA_GRID
        }
        selected = select_lambda(pooled)
        outer_fit_matrix = _state_matrix(outer_fit)
        outer_check_matrix = _state_matrix(check_rows)
        scaled_fit, scaled_check, outer_scaling = linear._scale_fold(
            outer_fit_matrix, outer_check_matrix, linear.ARM_LINEAR
        )
        parameters, outer_optimizer = fit_nested_offset(
            scaled_fit,
            np.asarray([row.trusted["outcome"] for row in outer_fit], dtype=np.float64),
            np.asarray([row.market_features[0] for row in outer_fit], dtype=np.float64),
            penalty_lambda=selected,
        )
        fit_count += 1
        candidate_values = linear.offset_probabilities(
            parameters, scaled_check,
            np.asarray([row.market_features[0] for row in check_rows], dtype=np.float64),
        )
        candidate_values = [
            validate_probability(
                float(value), DEFAULT_PROBABILITY_POLICY, ARM_CANDIDATE
            ) for value in candidate_values
        ]
        raw_values = []
        control_values = []
        outcomes = []
        for row in check_rows:
            frozen = control_rows_by_key.get(row.key)
            if frozen is None:
                raise ValueError("outer check row is missing from frozen v1 control")
            raw = validate_probability(
                float(row.trusted["market_probability"]),
                DEFAULT_PROBABILITY_POLICY, ARM_RAW,
            )
            if (frozen["fold"] != fold["fold"]
                    or frozen["game_id"] != row.game_id
                    or frozen["game_date"] != row.game_date
                    or frozen["game_week"] != row.game_week
                    or frozen["outcome"] != row.trusted["outcome"]
                    or frozen["raw_market_probability"] != raw):
                raise ValueError("frozen v1 control identity/label/raw market changed")
            raw_values.append(raw)
            control_values.append(frozen["control_probability"])
            outcomes.append(row.trusted["outcome"])
        arms = {
            ARM_RAW: settlement._simple_metrics(outcomes, raw_values),
            ARM_CONTROL: settlement._simple_metrics(outcomes, control_values),
            ARM_CANDIDATE: settlement._simple_metrics(outcomes, candidate_values),
        }
        fold_reports.append({
            "fold": fold["fold"],
            "fit_dates": list(fold["fit_dates"]),
            "check_dates": list(fold["check_dates"]),
            "fit_events": len(outer_fit),
            "check_events": len(check_rows),
            "fit_label_unavailable_game_ids": outer_unavailable,
            "inner_splits": inner_reports,
            "pooled_inner_events_per_lambda": pooled_events[selected],
            "pooled_inner_brier_by_lambda": [
                {"penalty_lambda": value, "brier": pooled[value]}
                for value in LAMBDA_GRID
            ],
            "selected_lambda": selected,
            "outer_scaling": outer_scaling,
            "outer_conditioning": linear._conditioning(scaled_fit),
            "outer_optimizer": outer_optimizer,
            "arms": arms,
            "candidate_minus_raw_market_brier": (
                arms[ARM_CANDIDATE]["brier"] - arms[ARM_RAW]["brier"]
            ),
            "candidate_minus_frozen_control_brier": (
                arms[ARM_CANDIDATE]["brier"] - arms[ARM_CONTROL]["brier"]
            ),
            "same_outer_rows_labels_and_checkpoints": True,
        })
        for index, row in enumerate(check_rows):
            predictions.append({
                "fold": fold["fold"], "row": row,
                ARM_RAW: raw_values[index], ARM_CONTROL: control_values[index],
                ARM_CANDIDATE: candidate_values[index],
            })
    if fit_count != MAX_MODEL_FITS:
        raise RuntimeError(f"exactly {MAX_MODEL_FITS} model fits required, observed {fit_count}")
    keys = [item["row"].key for item in predictions]
    if len(keys) != len(set(keys)) or set(keys) != set(control_rows_by_key):
        raise ValueError("candidate/control common check mask changed")
    return predictions, fold_reports


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
            losses = {
                arm: linear._loss(row.trusted["outcome"], item[arm], metric)
                for arm in ALL_ARMS
            }
            record[f"candidate_minus_raw_market_{metric}"] = (
                losses[ARM_CANDIDATE] - losses[ARM_RAW]
            )
            record[f"candidate_minus_frozen_control_{metric}"] = (
                losses[ARM_CANDIDATE] - losses[ARM_CONTROL]
            )
            record[f"frozen_control_minus_raw_market_{metric}"] = (
                losses[ARM_CONTROL] - losses[ARM_RAW]
            )
        records.append(record)
    return records


def _paired_evidence(records: Sequence[dict]) -> dict:
    evidence = {}
    for comparison in (
        "candidate_minus_raw_market",
        "candidate_minus_frozen_control",
        "frozen_control_minus_raw_market",
    ):
        evidence[comparison] = {}
        for metric in ("brier", "log_loss"):
            key = f"{comparison}_{metric}"
            evidence[comparison][metric] = {
                "delta_convention": f"{comparison}; negative loss is better",
                "equal_event_mean": math.fsum(row[key] for row in records) / len(records),
                "by_schedule_date": base._group_means(records, "game_date", key),
                "schedule_date_interval": base._group_bootstrap(
                    records, "game_date", key,
                    seed=BOOTSTRAP_SEED, replicates=BOOTSTRAP_REPLICATES,
                ),
                "observed_game_week_interval": base._group_bootstrap(
                    records, "game_week", key,
                    seed=BOOTSTRAP_SEED, replicates=BOOTSTRAP_REPLICATES,
                ),
            }
    return evidence


def nested_shrinkage_decision(
    aggregate: Mapping[str, dict], folds: Sequence[dict]
) -> tuple[str, dict]:
    candidate = aggregate[ARM_CANDIDATE]
    raw = aggregate[ARM_RAW]
    control = aggregate[ARM_CONTROL]
    raw_wins = [
        fold["arms"][ARM_CANDIDATE]["brier"] < fold["arms"][ARM_RAW]["brier"]
        for fold in folds
    ]
    control_wins = [
        fold["arms"][ARM_CANDIDATE]["brier"] < fold["arms"][ARM_CONTROL]["brier"]
        for fold in folds
    ]
    conditions = {
        "candidate_brier_below_raw_market": candidate["brier"] < raw["brier"],
        "candidate_log_loss_below_raw_market": candidate["log_loss"] < raw["log_loss"],
        "candidate_brier_below_frozen_control": candidate["brier"] < control["brier"],
        "candidate_log_loss_below_frozen_control": candidate["log_loss"] < control["log_loss"],
        "candidate_brier_raw_market_fold_wins_at_least_3_of_4": sum(raw_wins) >= 3,
        "candidate_brier_control_fold_wins_at_least_3_of_4": sum(control_wins) >= 3,
        "candidate_brier_raw_market_fold_wins_at_most_1_of_4": sum(raw_wins) <= 1,
        "candidate_brier_raw_market_fold_wins": raw_wins,
        "candidate_brier_frozen_control_fold_wins": control_wins,
    }
    aggregate_pass = all(conditions[key] for key in (
        "candidate_brier_below_raw_market",
        "candidate_log_loss_below_raw_market",
        "candidate_brier_below_frozen_control",
        "candidate_log_loss_below_frozen_control",
    ))
    support = aggregate_pass and all(conditions[key] for key in (
        "candidate_brier_raw_market_fold_wins_at_least_3_of_4",
        "candidate_brier_control_fold_wins_at_least_3_of_4",
    ))
    refute = (not aggregate_pass) or conditions[
        "candidate_brier_raw_market_fold_wins_at_most_1_of_4"
    ]
    if support:
        decision = "STATIC_STATE_NESTED_SHRINKAGE_SUPPORTED"
    elif refute:
        decision = "STATIC_STATE_NESTED_SHRINKAGE_REFUTED"
    else:
        decision = "STATIC_STATE_NESTED_SHRINKAGE_INCONCLUSIVE"
    return decision, conditions


def _write_predictions(path: Path, predictions: Sequence[dict]) -> None:
    fields = (
        "fold", "game_id", "game_date", "game_week", "event_id", "market_id",
        "cutoff_ms", "outcome_available_ms", "outcome", "raw_market_probability",
        "frozen_c1_linear_control_probability",
        "nested_shrinkage_static_state_probability",
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
                "event_id": row.trusted["event_id"],
                "market_id": row.trusted["market_id"],
                "cutoff_ms": row.trusted["cutoff_ms"],
                "outcome_available_ms": row.trusted["outcome_available_ms"],
                "outcome": row.trusted["outcome"],
                "raw_market_probability": item[ARM_RAW],
                "frozen_c1_linear_control_probability": item[ARM_CONTROL],
                "nested_shrinkage_static_state_probability": item[ARM_CANDIDATE],
            })
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def run(
    source_root: Path,
    output: Path,
    *,
    expected_events: int = EXPECTED_EVENTS,
    expected_dates: int = EXPECTED_DATES,
    allow_test_paths: bool = False,
    generated_utc: str | None = None,
) -> dict:
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    _validate_frozen_dependencies()
    control_artifact = _validate_v1_control()
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
            try:
                materialized.append(base._load_dynamic_market(source_root, item, state))
            except settlement.EventExclusion as error:
                exclusions.append({
                    "source_ordinal": ordinal, "game_id": item["game_id"],
                    "game_date": item["game_date"], "reason": error.code,
                    "detail": str(error)[:400],
                })
        expected_exclusions = [
            ("2025_04_GB_DAL", "unresolved_outcome"),
            ("2025_05_TEN_ARI", "market_trade_too_stale"),
        ]
        if (len(materialized) + len(exclusions) != expected_events
                or len(materialized) != EXPECTED_MATERIALIZED_EVENTS
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
            "schema": "nfl_ingame_static_state_nested_shrinkage_inputs_v2",
            "task_id": TASK_ID,
            "source_dataset_id": source_root.name,
            "source_manifest_sha256": settlement._sha256(source_root / "manifest.json"),
            "cohort_sha256": settlement._sha256(source_root / "cohort.csv"),
            "checkpoint_extractor_sha256": _sha256(EXTRACTOR),
            "checkpoint_state_sha256": _sha256(state_path),
            "runner_source_sha256": _sha256(Path(__file__)),
            "v0_runner_sha256": _sha256(Path(base.__file__)),
            "v1_control_runner_sha256": _sha256(Path(linear.__file__)),
            "settlement_dependency_sha256": _sha256(Path(settlement.__file__)),
            "probability_contract_sha256": _sha256(Path(probability_contract.__file__)),
            "proper_scoring_dependency_sha256": _sha256(Path(proper_scoring.__file__)),
            "controller_log_sha256": _sha256(CONTROLLER_LOG),
            "v0_result_review_sha256": _sha256(V0_RESULT_REVIEW),
            "v1_result_review_sha256": _sha256(V1_RESULT_REVIEW),
            "v0_artifact_root": str(V0_ARTIFACT_ROOT),
            "v0_artifact_hashes": V0_ARTIFACT_HASHES,
            "v1_control_artifact_root": str(V1_CONTROL_ROOT),
            "v1_control_artifact_hashes": V1_CONTROL_HASHES,
            "pbp_receipts": pbp_receipts,
            "materialized_receipts": [row.source_receipt for row in materialized],
            "route_dev_opened": False, "sealed_final_opened": False,
            "external_fetch": False, "paid_provider": False,
            "provider_cost_usd": "0",
        }
        exclusions_record = {
            "schema": "nfl_ingame_static_state_nested_shrinkage_exclusions_v2",
            "source_events": expected_events, "materialized_events": len(materialized),
            "excluded_events": len(exclusions),
            "reconciles_to_source_denominator": (
                len(materialized) + len(exclusions) == expected_events
            ),
            "exclusions": exclusions,
        }
        base._atomic_json(output / "input_receipts.json", input_receipts)
        base._atomic_json(output / "exclusions.json", exclusions_record)
        lock = {
            "schema": "nfl_ingame_static_state_nested_shrinkage_pre_score_lock_v2",
            "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "task_id": TASK_ID, "question_id": QUESTION_ID,
            "question_digest": QUESTION_DIGEST,
            "hypothesis_digest": HYPOTHESIS_DIGEST,
            "rule_digest": RULE_DIGEST,
            "pool_plan_digest": POOL_PLAN_DIGEST,
            "controller_log_sha256": CONTROLLER_LOG_SHA256,
            "candidate_component_spec_sha256": CANDIDATE_COMPONENT_SPEC_SHA256,
            "candidate_component_spec": CANDIDATE_COMPONENT_SPEC,
            "research_parent": "archived v0 market-plus-state negative branch",
            "comparison_incumbent": "v0 task-local raw_market",
            "read_only_attribution_control": {
                "arm": ARM_CONTROL,
                "source_task": "InGameMarketOffsetScoreTimeDiagnostic-v1",
                "predictions_sha256": V1_CONTROL_HASHES["predictions.csv"],
                "refit": False,
            },
            "source_denominator_events": expected_events,
            "materialized_events": EXPECTED_MATERIALIZED_EVENTS,
            "expected_exclusions": expected_exclusions,
            "expected_check_events": EXPECTED_CHECK_EVENTS,
            "expected_check_key_sha256": EXPECTED_CHECK_KEY_SHA256,
            "feature_names": list(FEATURE_NAMES),
            "preprocessing": (
                "each inner/outer fit gets its own fit-only StandardScaler on four "
                "continuous state columns; possession/down binaries remain raw; market "
                "logit remains unscaled with coefficient one"
            ),
            "nested_selection": {
                "last_outer_fit_dates": 6,
                "inner_splits": INNER_SPLITS,
                "consecutive_check_dates_per_split": INNER_CHECK_DATES,
                "lambda_grid": list(LAMBDA_GRID),
                "metric": "pooled equal-event inner Brier",
                "tie_break": "exact tie chooses largest lambda",
                "outer_refit": "one fit on full outer fit using selected lambda",
            },
            "solver": SOLVER_SPEC,
            "folds": folds,
            "expected_fit_events": list(EXPECTED_FIT_EVENTS),
            "expected_check_events_by_fold": list(EXPECTED_CHECK_EVENTS_BY_FOLD),
            "fit_budget": MAX_MODEL_FITS,
            "automatic_retries": 0,
            "primary_metric": "pooled equal-event Brier on exact common mask",
            "secondary": [
                "log loss", "calibration slope/intercept", "four outer folds",
                "selected lambdas", "all pooled inner losses",
                "complete schedule-date and observed-game-week intervals",
            ],
            "support_rule": (
                "candidate aggregate Brier and log loss below raw market and frozen C=1 "
                "linear control, with candidate Brier wins against each in at least 3/4 folds"
            ),
            "refute_rule": (
                "candidate fails either aggregate proper score against raw market, fails "
                "either against frozen C=1 linear control, or wins raw-market Brier in at "
                "most 1/4 folds"
            ),
            "inconclusive_rule": "all other valid outcomes",
            "stop_rule": (
                "one frozen run; maximum 64 fits; any identity, mask, chronology, nonfinite, "
                "optimizer, or inner-selection failure is terminal; no retry or tuning"
            ),
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "resource_cap": {
                "local_fits": MAX_MODEL_FITS, "wall_minutes": 15, "rss_gib": 1,
                "processes": 1, "network_bytes": 0, "provider_calls": 0,
                "provider_cost_usd": "0", "retries": 0,
            },
            "route_dev_opened": False, "sealed_final_opened": False,
            "external_fetch": False, "paid_provider": False,
            "provider_cost_usd": "0", "promotion_authorized": False,
        }
        base._atomic_json(output / "pre_score_lock.json", lock)
        predictions, fold_reports = _fit_and_predict(
            materialized, folds, control_artifact["rows_by_key"]
        )
        check_hash = settlement._digest([list(item["row"].key) for item in predictions])
        if (len(predictions) != EXPECTED_CHECK_EVENTS
                or check_hash != EXPECTED_CHECK_KEY_SHA256
                or tuple(item["fit_events"] for item in fold_reports) != EXPECTED_FIT_EVENTS
                or tuple(item["check_events"] for item in fold_reports)
                != EXPECTED_CHECK_EVENTS_BY_FOLD
                or any(item["fit_label_unavailable_game_ids"] for item in fold_reports)):
            raise ValueError("v0 chronological common mask or label availability changed")
        aggregate = _aggregate(predictions)
        decision, conditions = nested_shrinkage_decision(aggregate, fold_reports)
        records = _paired_records(predictions)
        scorecard = {
            "schema": "nfl_ingame_static_state_nested_shrinkage_scorecard_v2",
            "task_id": TASK_ID, "trainer_decision": decision,
            "decision_conditions": conditions,
            "source_denominator": {
                "events": expected_events, "dates": expected_dates,
                "materialized_events": len(materialized),
                "excluded_events": len(exclusions), "check_events": len(predictions),
                "check_dates": len({item["row"].game_date for item in predictions}),
                "check_game_weeks": len({item["row"].game_week for item in predictions}),
            },
            "identical_masks": {
                "candidate_raw_and_frozen_control_same_rows_labels_checkpoints": True,
                "check_key_sha256": check_hash,
                "matches_v0_and_v1_check_key_sha256": check_hash == EXPECTED_CHECK_KEY_SHA256,
                "one_checkpoint_per_game": (
                    len(predictions) == len({item["row"].game_id for item in predictions})
                ),
            },
            "model_fits": MAX_MODEL_FITS,
            "control_refits": 0,
            "aggregate": aggregate,
            "deltas": {
                "candidate_minus_raw_market": {
                    metric: aggregate[ARM_CANDIDATE][metric] - aggregate[ARM_RAW][metric]
                    for metric in ("brier", "log_loss")
                },
                "candidate_minus_frozen_control": {
                    metric: aggregate[ARM_CANDIDATE][metric] - aggregate[ARM_CONTROL][metric]
                    for metric in ("brier", "log_loss")
                },
            },
            "folds": fold_reports,
            "paired_grouped_evidence": _paired_evidence(records),
            "evidence_classification": (
                "trainer/shrinkage evidence on fixed static state and repeatedly inspected Train"
            ),
            "inference_boundary": (
                "repeatedly inspected opened-Train historical diagnostic; no realtime, "
                "untouched OOS, promotion, deployment, PnL, or cross-task claim"
            ),
            "cross_task_numeric_comparison_forbidden": True,
            "incumbent_changed": False,
            "research_credit_awarded": 0,
            "route_dev_opened": False, "sealed_final_opened": False,
            "external_fetch": False, "paid_provider": False,
            "provider_cost_usd": "0", "promotion_authorized": False,
        }
        _write_predictions(output / "predictions.csv", predictions)
        base._atomic_json(output / "scorecard.json", scorecard)
        manifest = {
            "schema": "nfl_ingame_static_state_nested_shrinkage_manifest_v2",
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
            "model_fits": MAX_MODEL_FITS, "control_refits": 0,
            "trainer_decision": decision,
            "historical_event_clock_only": True,
            "incumbent_changed": False,
            "route_dev_opened": False, "sealed_final_opened": False,
            "external_fetch": False, "paid_provider": False,
            "provider_cost_usd": "0", "promotion_authorized": False,
        }
        base._atomic_json(output / "manifest.json", manifest)
        return manifest
    except Exception as error:
        if output.exists() and not (output / "manifest.json").exists():
            base._atomic_json(output / "failure.json", {
                "schema": "nfl_ingame_static_state_nested_shrinkage_failure_v2",
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
        "check_events": result["check_events"], "model_fits": result["model_fits"],
        "trainer_decision": result["trainer_decision"],
        "provider_cost_usd": result["provider_cost_usd"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
