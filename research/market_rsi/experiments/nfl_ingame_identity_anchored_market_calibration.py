#!/usr/bin/env python3
"""Fit the frozen four-fold identity-anchored in-game market calibrator.

This is an opened-Train historical Discovery runner.  It changes only the
calibration trainer, preserves the exact v0 195 -> 193 -> 87 population, and
scores frozen v0 predictions as read-only comparators.  It is not realtime,
untouched OOS, promotion, deployment, PnL, or cross-task evidence.
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
import shutil
from typing import Mapping, Sequence

import numpy as np
from scipy.special import expit

from minimal_prediction_loop import probability_contract, proper_scoring
from minimal_prediction_loop.probability_contract import (
    DEFAULT_PROBABILITY_POLICY,
    validate_probability,
    validate_train_evaluation_rows,
)
from experiments import nfl_ingame_win_probability_train_diagnostic as base
from experiments import nfl_ingame_prior_play_success_residual_audit as frozen_v0
from experiments import nfl_settlement_probability_train_diagnostic as settlement


TASK_ID = "InGameIdentityAnchoredMarketCalibration-v1"
QUESTION_ID = "ingame-identity-anchored-market-calibration-v1-q1"
QUESTION_DIGEST = "4e074ad9b4ccc8af0373a6e50c4c1580f5dc3121fbc4ace484c6626058d02fbd"
HYPOTHESIS_DIGEST = "736ab3792406e98d2e2c5fd443b81c06b1b3d5c9cc097e0df2d9a23ee8f55d87"
RULE_DIGEST = "92399363c928900ac549131a9db1289c7dae3db68a6f3dc51459f373d4fb643e"
COMPONENT_SPEC_DIGEST = "128321cc21f68b649b7e631c1f29891e3b9dbca4190aa11dc6e7d37b096623d4"
SELECTION_PLAN_DIGEST = "606453d5dcb1082dc3e046e8c7203bdb5a23ac4f548ab5d734c59e8d6b951122"
CONTROLLER_LOG = Path(__file__).parents[1] / "supervisor_harness" / (
    "AGENT_LOG_INGAME_PREDICTIVE_AUTONOMY_GENERATION1_CONTROLLER_2026-09-29.md"
)
CONTROLLER_LOG_SHA256 = "a6259940439dff5e6c86a0d1c4de73e634608bb7b3d82804731ac103674e4efb"
BASE_RUNNER_SHA256 = "e61668c7e29cf4dda95f6cc315b248dbe6744a9dcc0ae0cd6077d880ca6265b7"
FROZEN_V0_VALIDATOR_SHA256 = "a612371ae77a78441c2d9416d6edc035a916879057fed9ef731de46476a07bcb"
SETTLEMENT_SHA256 = "1f1bdccd69d799be1af99ece4ee6198ffbd02f3a4550e651936fb3edfa83fb8b"

SOURCE_ROOT = base.SOURCE_ROOT
PERSISTENT_ARTIFACT_ROOT = base.PERSISTENT_ARTIFACT_ROOT
V0_ARTIFACT_ROOT = frozen_v0.V0_ARTIFACT_ROOT
EXPECTED_V0_HASHES = frozen_v0.EXPECTED_V0_HASHES
EXPECTED_EVENTS = 195
EXPECTED_DATES = base.EXPECTED_DATES
EXPECTED_MATERIALIZED_EVENTS = 193
EXPECTED_CHECK_EVENTS = 87
EXPECTED_FIT_EVENTS = (106, 132, 148, 176)
EXPECTED_CHECK_EVENTS_BY_FOLD = (26, 16, 28, 17)
EXPECTED_CHECK_KEY_SHA256 = frozen_v0.EXPECTED_CHECK_KEY_SHA256
EXPECTED_EXCLUSIONS = [
    ("2025_04_GB_DAL", "unresolved_outcome"),
    ("2025_05_TEN_ARI", "market_trade_too_stale"),
]

ARM_RAW = "raw_market"
ARM_ORDINARY = "frozen_v0_ordinary_market_only"
ARM_PARENT = "frozen_v0_market_plus_state_parent"
ARM_CANDIDATE = "identity_anchored_market_calibration"
ALL_ARMS = (ARM_RAW, ARM_ORDINARY, ARM_PARENT, ARM_CANDIDATE)
PENALTY = 16.0
MAX_ITERATIONS = 50
GRADIENT_TOLERANCE = 1e-8
BOOTSTRAP_SEED = 20260929
BOOTSTRAP_REPLICATES = 10_000
MODEL_FITS = 4

SCHEDULER_BRANCH_BINDING = {
    "allocation": "exploration",
    "attempt_id": "attempt-02",
    "batch_id": "market-rsi-ingame-predictive-autonomy-20260929-03",
    "candidate_id": TASK_ID,
    "comparison_incumbent_sha256": "89a8ef92c9cf4844b99e0136c51a1f8b896cdd66afcd23e8b8a23499859ffc7f",
    "controller_decision_sha256": CONTROLLER_LOG_SHA256,
    "hypothesis_digest_sha256": HYPOTHESIS_DIGEST,
    "method_family": "identity_anchored_market_calibration",
    "pool_generation": 1,
    "predeclared_rule_sha256": RULE_DIGEST,
    "question_digest_sha256": QUESTION_DIGEST,
    "question_id": QUESTION_ID,
    "research_parent_sha256": "c40b1df57588b296e72ffe5b220c91aa0dd16d31ef1c573bdb4b0e7c0d72f79d",
    "resource_hint": {
        "authority_granted": False, "max_attempts": 1, "max_bytes": 0,
        "max_cost_usd": 0.0, "max_time_seconds": 600,
        "resource_class": "small_experiment",
    },
    "selection_hint_sha256": "2ba03f832fbeddfc4e27d996ffffeefe10c41ee0c5714e57ee8c3db9525f8205",
}
SCHEDULER_BRANCH_BINDING_SHA256 = "b2c72d468c5542e57c43c9724329e8d5c8ccb51f8d0011ee0e8cdab34b78b80b"
SCHEDULER_SELECTION_STATE_SHA256 = "860cfecc832f4123a9a1a1c6f38a735325b02ae725f2afbba56167084a81c3a5"
SCHEDULER_SELECTION_JOURNAL_HEAD_SHA256 = "5bdd1ba9a7ca16df77819a8b49f564b1b6d7dd3cbb9826345cd21ad65235ac8f"

COMPONENT_SPEC = {
    "formula": "logit(q)=logit(p_now)+alpha+delta*z_market",
    "z_market": "fit-only mean/std standardization of clipped logit(p_now)",
    "clip_epsilon": DEFAULT_PROBABILITY_POLICY.epsilon,
    "objective": "sum Bernoulli NLL + 0.5*16*(alpha^2+delta^2)",
    "solver": "deterministic analytic damped Newton",
    "maximum_iterations": MAX_ITERATIONS,
    "gradient_infinity_tolerance": GRADIENT_TOLERANCE,
    "outer_fits": MODEL_FITS,
    "retries": 0,
}
IMPLEMENTATION_COMPONENT_SPEC_SHA256 = (
    "3befd9d507d5199329b4f18263522dc9ebba7e4f553acb5afb565206e3b513be"
)
THREAD_ENV_CONTRACT = {
    "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1", "PYTHONHASHSEED": "0",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


def _require_dependencies() -> None:
    expected = (
        (CONTROLLER_LOG, CONTROLLER_LOG_SHA256, "Controller log"),
        (Path(base.__file__), BASE_RUNNER_SHA256, "v0 runner"),
        (Path(frozen_v0.__file__), FROZEN_V0_VALIDATOR_SHA256, "v0 validator"),
        (Path(settlement.__file__), SETTLEMENT_SHA256, "settlement dependency"),
    )
    for path, digest, label in expected:
        if not path.is_file() or path.is_symlink() or _sha256(path) != digest:
            raise ValueError(f"frozen {label} is missing, symlinked, or hash-changed")
    if _digest(COMPONENT_SPEC) != IMPLEMENTATION_COMPONENT_SPEC_SHA256:
        raise ValueError("implementation component spec changed")
    if _digest(SCHEDULER_BRANCH_BINDING) != SCHEDULER_BRANCH_BINDING_SHA256:
        raise ValueError("scheduler branch binding changed")


def _require_single_thread_environment() -> None:
    drift = {name: os.environ.get(name) for name, expected in THREAD_ENV_CONTRACT.items()
             if os.environ.get(name) != expected}
    if drift:
        raise ValueError(f"frozen one-thread resource cap is not satisfied: {drift}")


def _control_key(row: Mapping[str, str]) -> tuple[str, str, int]:
    try:
        return str(row["event_id"]), str(row["market_id"]), int(row["cutoff_ms"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("frozen v0 prediction key is invalid") from error


def _frozen_controls(frozen: dict) -> dict[tuple[str, str, int], dict]:
    controls = {}
    ordered = []
    for raw in frozen["predictions"]:
        key = _control_key(raw)
        if key in controls or not all(key[:2]):
            raise ValueError("frozen v0 prediction key is blank or duplicated")
        try:
            fold, outcome = int(raw["fold"]), int(raw["outcome"])
            probabilities = {
                ARM_RAW: float(raw["raw_market_probability"]),
                ARM_ORDINARY: float(raw["market_model_probability"]),
                ARM_PARENT: float(raw["market_plus_state_probability"]),
            }
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("frozen v0 prediction row is malformed") from error
        if fold not in (1, 2, 3, 4) or outcome not in (0, 1):
            raise ValueError("frozen v0 fold/outcome changed")
        for arm, value in probabilities.items():
            probabilities[arm] = validate_probability(
                value, DEFAULT_PROBABILITY_POLICY, arm
            )
        controls[key] = {
            "fold": fold, "game_id": raw["game_id"],
            "game_date": raw["game_date"], "game_week": raw["game_week"],
            "outcome": outcome, **probabilities,
        }
        ordered.append(list(key))
    if len(controls) != EXPECTED_CHECK_EVENTS or _digest(ordered) != EXPECTED_CHECK_KEY_SHA256:
        raise ValueError("frozen v0 87-row common mask changed")
    return controls


def _clipped_logits(probabilities: object) -> np.ndarray:
    values = np.asarray(probabilities, dtype=np.float64)
    if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
        raise ValueError("market probabilities must be a finite nonempty vector")
    epsilon = DEFAULT_PROBABILITY_POLICY.epsilon
    if np.any(values < epsilon) or np.any(values > 1 - epsilon):
        raise ValueError("market probability violates the frozen endpoint policy")
    clipped = np.clip(values, epsilon, 1 - epsilon)
    return np.log(clipped / (1 - clipped))


def fit_only_market_standardization(
    fit_probabilities: object, check_probabilities: object,
) -> tuple[np.ndarray, np.ndarray, dict]:
    fit_logits = _clipped_logits(fit_probabilities)
    check_logits = _clipped_logits(check_probabilities)
    mean, scale = float(fit_logits.mean()), float(fit_logits.std(ddof=0))
    if not math.isfinite(mean) or not math.isfinite(scale) or scale <= 0:
        raise ValueError("fit market logits have zero or invalid scale")
    return (
        (fit_logits - mean) / scale,
        (check_logits - mean) / scale,
        {"fit_logit_mean": mean, "fit_logit_scale": scale, "ddof": 0},
    )


def identity_objective_gradient_hessian(
    parameters: object, market_logits: object, standardized_market: object,
    outcomes: object,
) -> tuple[float, np.ndarray, np.ndarray]:
    theta = np.asarray(parameters, dtype=np.float64)
    offsets = np.asarray(market_logits, dtype=np.float64)
    z_market = np.asarray(standardized_market, dtype=np.float64)
    labels = np.asarray(outcomes, dtype=np.float64)
    if (theta.shape != (2,) or offsets.ndim != 1 or z_market.shape != offsets.shape
            or labels.shape != offsets.shape or not len(offsets)
            or not all(np.isfinite(value).all() for value in (theta, offsets, z_market, labels))
            or np.any((labels != 0) & (labels != 1))):
        raise ValueError("identity objective inputs are invalid or misaligned")
    design = np.column_stack((np.ones(len(offsets)), z_market))
    eta = offsets + design @ theta
    probabilities = expit(eta)
    objective = float(np.sum(np.logaddexp(0.0, eta) - labels * eta))
    objective += 0.5 * PENALTY * float(theta @ theta)
    gradient = design.T @ (probabilities - labels) + PENALTY * theta
    hessian = design.T @ (design * (probabilities * (1 - probabilities))[:, None])
    hessian += PENALTY * np.eye(2)
    if not (math.isfinite(objective) and np.isfinite(gradient).all()
            and np.isfinite(hessian).all()):
        raise ValueError("identity objective became nonfinite")
    return objective, gradient, hessian


def fit_identity_anchored(
    fit_probabilities: object, outcomes: object,
) -> tuple[np.ndarray, dict, dict]:
    values = np.asarray(fit_probabilities, dtype=np.float64)
    labels = np.asarray(outcomes, dtype=np.float64)
    z_fit, _, scaling = fit_only_market_standardization(values, values)
    logits = _clipped_logits(values)
    theta = np.zeros(2, dtype=np.float64)
    evaluations = 0
    backtracks = 0
    for iteration in range(MAX_ITERATIONS + 1):
        objective, gradient, hessian = identity_objective_gradient_hessian(
            theta, logits, z_fit, labels
        )
        evaluations += 1
        grad_inf = float(np.max(np.abs(gradient)))
        if grad_inf <= GRADIENT_TOLERANCE:
            return theta, scaling, {
                "converged": True, "iterations": iteration,
                "function_gradient_hessian_evaluations": evaluations,
                "backtracking_steps": backtracks, "objective": objective,
                "gradient_infinity_norm": grad_inf,
                "alpha": float(theta[0]), "delta": float(theta[1]),
                "penalty": PENALTY, "retry_count": 0,
            }
        if iteration == MAX_ITERATIONS:
            break
        direction = np.linalg.solve(hessian, gradient)
        directional = float(gradient @ direction)
        if not math.isfinite(directional) or directional <= 0:
            raise RuntimeError("damped Newton direction is not a descent direction")
        step = 1.0
        accepted = False
        for _ in range(60):
            proposal = theta - step * direction
            proposal_objective = identity_objective_gradient_hessian(
                proposal, logits, z_fit, labels
            )[0]
            evaluations += 1
            if proposal_objective <= objective - 1e-4 * step * directional:
                theta, accepted = proposal, True
                break
            step *= 0.5
            backtracks += 1
        if not accepted:
            raise RuntimeError("damped Newton line search failed; no retry authorized")
    raise RuntimeError(
        "identity-anchored optimizer failed frozen convergence: "
        f"iterations={MAX_ITERATIONS}, grad_inf={grad_inf}"
    )


def identity_probabilities(
    parameters: object, raw_probabilities: object, scaling: Mapping[str, float],
) -> list[float]:
    values = np.asarray(raw_probabilities, dtype=np.float64)
    logits = _clipped_logits(values)
    mean, scale = float(scaling["fit_logit_mean"]), float(scaling["fit_logit_scale"])
    z_market = (logits - mean) / scale
    theta = np.asarray(parameters, dtype=np.float64)
    result = expit(logits + theta[0] + theta[1] * z_market)
    return [validate_probability(
        float(value), DEFAULT_PROBABILITY_POLICY, ARM_CANDIDATE
    ) for value in result]


def _strict_prior_rows(
    by_date: Mapping[str, list[base.InGameRow]], fit_dates: Sequence[str],
    check_rows: Sequence[base.InGameRow],
) -> tuple[list[base.InGameRow], list[str]]:
    if not check_rows:
        raise ValueError("chronological check block is empty")
    first_check_cutoff = min(row.trusted["cutoff_ms"] for row in check_rows)
    candidates = [row for date in fit_dates for row in by_date.get(date, [])]
    fit_rows = sorted([
        row for row in candidates
        if row.trusted["outcome_available_ms"] < first_check_cutoff
    ], key=lambda row: row.key)
    unavailable = sorted(
        row.game_id for row in candidates
        if row.trusted["outcome_available_ms"] >= first_check_cutoff
    )
    if (not fit_rows or len(fit_rows) != len(candidates) or unavailable
            or len({row.trusted["outcome"] for row in fit_rows}) != 2):
        raise ValueError("outer fit is incomplete, label-unavailable, or one-class")
    validate_train_evaluation_rows(
        [row.trusted for row in fit_rows], [row.trusted for row in check_rows]
    )
    return fit_rows, unavailable


def _fit_and_predict(
    rows: Sequence[base.InGameRow], folds: Sequence[dict],
    controls: Mapping[tuple[str, str, int], dict],
) -> tuple[list[dict], list[dict]]:
    by_date: dict[str, list[base.InGameRow]] = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    predictions, reports = [], []
    fit_count = 0
    for fold in folds:
        check_rows = sorted([
            row for date in fold["check_dates"] for row in by_date.get(date, [])
        ], key=lambda row: row.key)
        fit_rows, unavailable = _strict_prior_rows(
            by_date, fold["fit_dates"], check_rows
        )
        fit_raw = [row.trusted["market_probability"] for row in fit_rows]
        check_raw = [row.trusted["market_probability"] for row in check_rows]
        parameters, scaling, optimizer = fit_identity_anchored(
            fit_raw, [row.trusted["outcome"] for row in fit_rows]
        )
        fit_count += 1
        candidate = identity_probabilities(parameters, check_raw, scaling)
        arm_values = {arm: [] for arm in ALL_ARMS}
        for row, candidate_probability in zip(check_rows, candidate, strict=True):
            frozen = controls.get(row.key)
            raw = validate_probability(
                float(row.trusted["market_probability"]),
                DEFAULT_PROBABILITY_POLICY, ARM_RAW,
            )
            if (frozen is None or frozen["fold"] != fold["fold"]
                    or frozen["game_id"] != row.game_id
                    or frozen["game_date"] != row.game_date
                    or frozen["game_week"] != row.game_week
                    or frozen["outcome"] != row.trusted["outcome"]
                    or frozen[ARM_RAW] != raw):
                raise ValueError("candidate row differs from frozen v0 identity/label/raw")
            item = {"fold": fold["fold"], "row": row, **{
                ARM_RAW: raw, ARM_ORDINARY: frozen[ARM_ORDINARY],
                ARM_PARENT: frozen[ARM_PARENT], ARM_CANDIDATE: candidate_probability,
            }}
            predictions.append(item)
            for arm in ALL_ARMS:
                arm_values[arm].append(item[arm])
        outcomes = [row.trusted["outcome"] for row in check_rows]
        metrics = {
            arm: settlement._simple_metrics(outcomes, arm_values[arm])
            for arm in ALL_ARMS
        }
        reports.append({
            "fold": fold["fold"], "fit_dates": list(fold["fit_dates"]),
            "check_dates": list(fold["check_dates"]), "fit_events": len(fit_rows),
            "check_events": len(check_rows),
            "fit_label_unavailable_game_ids": unavailable,
            "fit_only_market_logit_scaling": scaling,
            "optimizer": optimizer, "arms": metrics,
            "same_rows_labels_and_checkpoints": True,
        })
    keys = [item["row"].key for item in predictions]
    if (fit_count != MODEL_FITS or len(keys) != len(set(keys))
            or set(keys) != set(controls)):
        raise ValueError("exact four fits or exact frozen common mask changed")
    return predictions, reports


def _aggregate(predictions: Sequence[dict]) -> dict:
    outcomes = [item["row"].trusted["outcome"] for item in predictions]
    result = {}
    for arm in ALL_ARMS:
        probabilities = [item[arm] for item in predictions]
        result[arm] = settlement._simple_metrics(outcomes, probabilities)
        result[arm]["reliability_table"] = base._reliability_table(
            outcomes, probabilities
        )
    return result


def _loss(outcome: int, probability: float, metric: str) -> float:
    if metric == "brier":
        return proper_scoring.brier_loss(probability, outcome)
    if metric == "log_loss":
        return proper_scoring.bounded_log_loss(probability, outcome)
    raise ValueError("unsupported proper score")


def _paired_records(predictions: Sequence[dict]) -> list[dict]:
    records = []
    for item in predictions:
        row = item["row"]
        record = {
            "game_id": row.game_id, "game_date": row.game_date,
            "game_week": row.game_week, "outcome": row.trusted["outcome"],
        }
        for comparator in (ARM_RAW, ARM_ORDINARY, ARM_PARENT):
            for metric in ("brier", "log_loss"):
                record[f"candidate_minus_{comparator}_{metric}"] = (
                    _loss(record["outcome"], item[ARM_CANDIDATE], metric)
                    - _loss(record["outcome"], item[comparator], metric)
                )
        records.append(record)
    return records


def _paired_evidence(records: Sequence[dict]) -> dict:
    evidence = {}
    for comparator in (ARM_RAW, ARM_ORDINARY, ARM_PARENT):
        comparison = f"candidate_minus_{comparator}"
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


def calibration_decision(
    aggregate: Mapping[str, dict], folds: Sequence[dict], paired: Mapping[str, dict],
) -> tuple[str, dict]:
    candidate = aggregate[ARM_CANDIDATE]
    raw_wins = [
        fold["arms"][ARM_CANDIDATE]["brier"] < fold["arms"][ARM_RAW]["brier"]
        for fold in folds
    ]
    ordinary_wins = [
        fold["arms"][ARM_CANDIDATE]["brier"] < fold["arms"][ARM_ORDINARY]["brier"]
        for fold in folds
    ]
    date_upper = paired[f"candidate_minus_{ARM_RAW}"]["brier"][
        "schedule_date_interval"
    ]["interval_95"][1]
    week_upper = paired[f"candidate_minus_{ARM_RAW}"]["brier"][
        "observed_game_week_interval"
    ]["interval_95"][1]
    conditions = {
        "candidate_aggregate_brier_below_all_three": all(
            candidate["brier"] < aggregate[arm]["brier"]
            for arm in (ARM_RAW, ARM_ORDINARY, ARM_PARENT)
        ),
        "candidate_aggregate_log_loss_below_all_three": all(
            candidate["log_loss"] < aggregate[arm]["log_loss"]
            for arm in (ARM_RAW, ARM_ORDINARY, ARM_PARENT)
        ),
        "candidate_raw_brier_fold_wins_at_least_3_of_4": sum(raw_wins) >= 3,
        "candidate_ordinary_brier_fold_wins_at_least_3_of_4": sum(ordinary_wins) >= 3,
        "candidate_raw_date_grouped_brier_upper_below_zero": date_upper < 0,
        "candidate_raw_week_grouped_brier_upper_below_zero": week_upper < 0,
        "candidate_raw_brier_fold_wins_at_most_1_of_4": sum(raw_wins) <= 1,
        "candidate_raw_brier_fold_wins": raw_wins,
        "candidate_ordinary_brier_fold_wins": ordinary_wins,
    }
    keep_keys = (
        "candidate_aggregate_brier_below_all_three",
        "candidate_aggregate_log_loss_below_all_three",
        "candidate_raw_brier_fold_wins_at_least_3_of_4",
        "candidate_ordinary_brier_fold_wins_at_least_3_of_4",
        "candidate_raw_date_grouped_brier_upper_below_zero",
        "candidate_raw_week_grouped_brier_upper_below_zero",
    )
    raw_aggregate_failure = (
        candidate["brier"] >= aggregate[ARM_RAW]["brier"]
        or candidate["log_loss"] >= aggregate[ARM_RAW]["log_loss"]
    )
    if all(conditions[key] for key in keep_keys):
        decision = "IDENTITY_ANCHORED_MARKET_CALIBRATION_KEEP"
    elif raw_aggregate_failure or conditions[
            "candidate_raw_brier_fold_wins_at_most_1_of_4"]:
        decision = "IDENTITY_ANCHORED_MARKET_CALIBRATION_REFUTED_REVERT"
    else:
        decision = "IDENTITY_ANCHORED_MARKET_CALIBRATION_INCONCLUSIVE_REVERT"
    conditions["scientific_refute_raw_aggregate_proper_score_failure"] = raw_aggregate_failure
    return decision, conditions


def _write_predictions(path: Path, predictions: Sequence[dict]) -> None:
    fields = (
        "fold", "game_id", "game_date", "game_week", "event_id", "market_id",
        "cutoff_ms", "outcome_available_ms", "outcome", "raw_market_probability",
        "frozen_v0_ordinary_market_only_probability",
        "frozen_v0_market_plus_state_parent_probability",
        "identity_anchored_market_calibration_probability",
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
                "frozen_v0_ordinary_market_only_probability": item[ARM_ORDINARY],
                "frozen_v0_market_plus_state_parent_probability": item[ARM_PARENT],
                "identity_anchored_market_calibration_probability": item[ARM_CANDIDATE],
            })
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def run(
    source_root: Path, output: Path, *, allow_test_paths: bool = False,
    generated_utc: str | None = None,
) -> dict:
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    _require_dependencies()
    _require_single_thread_environment()
    frozen = frozen_v0._validate_v0_artifact(V0_ARTIFACT_ROOT)
    controls = _frozen_controls(frozen)
    cohort = base._validate_source(
        source_root, expected_events=EXPECTED_EVENTS,
        expected_dates=EXPECTED_DATES, allow_test_paths=allow_test_paths,
    )
    pbp_receipts = base._validate_pbp_receipts(source_root, cohort)
    states = {row["game_id"]: row for row in frozen["anchors"]}
    output.mkdir(parents=True, exist_ok=False)
    try:
        shutil.copyfile(V0_ARTIFACT_ROOT / "checkpoint_state.csv", output / "checkpoint_state.csv")
        materialized, exclusions = [], []
        for ordinal, item in enumerate(cohort):
            try:
                materialized.append(base._load_dynamic_market(
                    source_root, item, states[item["game_id"]]
                ))
            except settlement.EventExclusion as error:
                exclusions.append({
                    "source_ordinal": ordinal, "game_id": item["game_id"],
                    "game_date": item["game_date"], "reason": error.code,
                    "detail": str(error)[:400],
                })
        materialized.sort(key=lambda row: row.key)
        observed_exclusions = [(row["game_id"], row["reason"]) for row in exclusions]
        if (len(materialized) != EXPECTED_MATERIALIZED_EVENTS
                or len(materialized) + len(exclusions) != EXPECTED_EVENTS
                or observed_exclusions != EXPECTED_EXCLUSIONS):
            raise ValueError("exact frozen 195 -> 193 attrition changed")
        folds = frozen["folds"]
        lock = {
            "schema": "nfl_ingame_identity_anchored_market_calibration_pre_score_lock_v1",
            "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "task_id": TASK_ID, "question_id": QUESTION_ID,
            "question_digest_sha256": QUESTION_DIGEST,
            "hypothesis_digest_sha256": HYPOTHESIS_DIGEST,
            "predeclared_rule_sha256": RULE_DIGEST,
            "component_spec_sha256": COMPONENT_SPEC_DIGEST,
            "implementation_component_spec_sha256": IMPLEMENTATION_COMPONENT_SPEC_SHA256,
            "component_spec": COMPONENT_SPEC,
            "thread_environment_contract": THREAD_ENV_CONTRACT,
            "selection_plan_sha256": SELECTION_PLAN_DIGEST,
            "controller_log_sha256": CONTROLLER_LOG_SHA256,
            "scheduler_branch_binding": SCHEDULER_BRANCH_BINDING,
            "scheduler_branch_binding_sha256": SCHEDULER_BRANCH_BINDING_SHA256,
            "scheduler_selection_state_sha256": SCHEDULER_SELECTION_STATE_SHA256,
            "scheduler_selection_journal_head_sha256": SCHEDULER_SELECTION_JOURNAL_HEAD_SHA256,
            "research_parent": "archived v0 market-plus-state negative branch",
            "comparison_incumbent": "v0 task-local raw market",
            "source_denominator_events": EXPECTED_EVENTS,
            "materialized_events": EXPECTED_MATERIALIZED_EVENTS,
            "expected_check_events": EXPECTED_CHECK_EVENTS,
            "expected_check_key_sha256": EXPECTED_CHECK_KEY_SHA256,
            "folds": folds, "expected_fit_events": list(EXPECTED_FIT_EVENTS),
            "expected_check_events_by_fold": list(EXPECTED_CHECK_EVENTS_BY_FOLD),
            "arms": list(ALL_ARMS), "fit_budget": MODEL_FITS,
            "automatic_retries": 0,
            "support_refute_inconclusive_rule": (
                "exact Controller generation1 attempt-02 rule bound by predeclared_rule_sha256"
            ),
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_replicates_each_for_date_and_week": BOOTSTRAP_REPLICATES,
            "resource_cap": {
                "processes": 1, "threads": 1, "local_fits": MODEL_FITS,
                "wall_seconds": 600, "rss_mib": 768, "retries": 0,
                "network_bytes": 0, "provider_calls": 0, "provider_cost_usd": "0",
            },
            "route_dev_opened": False, "sealed_final_opened": False,
            "external_fetch": False, "paid_provider": False,
            "provider_cost_usd": "0", "promotion_authorized": False,
        }
        base._atomic_json(output / "pre_score_lock.json", lock)
        base._atomic_json(output / "input_receipts.json", {
            "schema": "nfl_ingame_identity_anchored_market_calibration_inputs_v1",
            "task_id": TASK_ID, "source_dataset_id": source_root.name,
            "source_manifest_sha256": settlement._sha256(source_root / "manifest.json"),
            "cohort_sha256": settlement._sha256(source_root / "cohort.csv"),
            "checkpoint_state_sha256": _sha256(output / "checkpoint_state.csv"),
            "v0_artifact_root": str(V0_ARTIFACT_ROOT),
            "v0_artifact_hashes": EXPECTED_V0_HASHES,
            "runner_source_sha256": _sha256(Path(__file__)),
            "v0_runner_sha256": _sha256(Path(base.__file__)),
            "pbp_receipts": pbp_receipts,
            "materialized_receipts": [row.source_receipt for row in materialized],
            "route_dev_opened": False, "sealed_final_opened": False,
            "external_fetch": False, "paid_provider": False,
            "provider_cost_usd": "0",
        })
        base._atomic_json(output / "exclusions.json", {
            "schema": "nfl_ingame_identity_anchored_market_calibration_exclusions_v1",
            "source_events": EXPECTED_EVENTS,
            "materialized_events": len(materialized),
            "excluded_events": len(exclusions),
            "reconciles_to_source_denominator": True, "exclusions": exclusions,
        })
        predictions, fold_reports = _fit_and_predict(materialized, folds, controls)
        check_hash = _digest([list(item["row"].key) for item in predictions])
        if (len(predictions) != EXPECTED_CHECK_EVENTS
                or check_hash != EXPECTED_CHECK_KEY_SHA256
                or tuple(item["fit_events"] for item in fold_reports) != EXPECTED_FIT_EVENTS
                or tuple(item["check_events"] for item in fold_reports)
                != EXPECTED_CHECK_EVENTS_BY_FOLD
                or any(item["fit_label_unavailable_game_ids"] for item in fold_reports)):
            raise ValueError("frozen chronology, fit counts, or 87-row mask changed")
        aggregate = _aggregate(predictions)
        paired = _paired_evidence(_paired_records(predictions))
        decision, conditions = calibration_decision(aggregate, fold_reports, paired)
        scorecard = {
            "schema": "nfl_ingame_identity_anchored_market_calibration_scorecard_v1",
            "task_id": TASK_ID, "trainer_decision": decision,
            "decision_conditions": conditions,
            "source_denominator": {
                "events": EXPECTED_EVENTS, "dates": EXPECTED_DATES,
                "materialized_events": EXPECTED_MATERIALIZED_EVENTS,
                "excluded_events": len(exclusions), "check_events": len(predictions),
                "check_dates": len({item["row"].game_date for item in predictions}),
                "check_game_weeks": len({item["row"].game_week for item in predictions}),
            },
            "identical_masks": {
                "all_four_arms_same_rows_labels_and_checkpoints": True,
                "check_key_sha256": check_hash,
                "matches_frozen_v0_check_key_sha256": True,
                "one_checkpoint_per_game": (
                    len(predictions) == len({item["row"].game_id for item in predictions})
                ),
            },
            "model_fits": MODEL_FITS, "control_refits": 0,
            "automatic_retries": 0, "aggregate": aggregate,
            "folds": fold_reports, "paired_grouped_evidence": paired,
            "evidence_classification": (
                "market-only calibration/trainer evidence on repeatedly inspected opened Train"
            ),
            "inference_boundary": (
                "historical event clock only; not realtime, untouched OOS, promotion, "
                "deployment, PnL, data-increment, research-mechanism, or cross-task evidence"
            ),
            "incumbent_changed": decision.endswith("_KEEP"),
            "route_dev_opened": False, "sealed_final_opened": False,
            "external_fetch": False, "paid_provider": False,
            "provider_cost_usd": "0", "promotion_authorized": False,
        }
        _write_predictions(output / "predictions.csv", predictions)
        base._atomic_json(output / "scorecard.json", scorecard)
        manifest = {
            "schema": "nfl_ingame_identity_anchored_market_calibration_manifest_v1",
            "complete": True,
            "completed_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "task_id": TASK_ID,
            "pre_score_lock_sha256": _sha256(output / "pre_score_lock.json"),
            "input_receipts_sha256": _sha256(output / "input_receipts.json"),
            "exclusions_sha256": _sha256(output / "exclusions.json"),
            "predictions_sha256": _sha256(output / "predictions.csv"),
            "scorecard_sha256": _sha256(output / "scorecard.json"),
            "source_events": EXPECTED_EVENTS,
            "materialized_events": EXPECTED_MATERIALIZED_EVENTS,
            "excluded_events": len(exclusions), "check_events": len(predictions),
            "model_fits": MODEL_FITS, "control_refits": 0,
            "automatic_retries": 0, "trainer_decision": decision,
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
                "schema": "nfl_ingame_identity_anchored_market_calibration_failure_v1",
                "error_type": type(error).__name__, "error": str(error)[:1200],
                "model_fits_maximum": MODEL_FITS, "automatic_retries": 0,
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
