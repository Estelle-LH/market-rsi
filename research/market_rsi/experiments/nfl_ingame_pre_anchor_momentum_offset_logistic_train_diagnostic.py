#!/usr/bin/env python3
"""Four-fit pre-anchor momentum offset-logistic opened-Train diagnostic.

This runner changes only the prediction stage.  It reconstructs the reviewed
120-second strictly-prior market-momentum signal for every outer fit and check
row, fits a coefficient-one current-market-logit offset model, and scores it
against raw market and the read-only v0 ordinary market-only Logistic arm.
The repeatedly inspected Train result is Discovery evidence only.
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
)
from experiments import nfl_ingame_win_probability_train_diagnostic as base
from experiments import nfl_ingame_market_offset_score_time_train_diagnostic as offset
from experiments import nfl_ingame_static_state_nested_shrinkage_train_diagnostic as nested
from experiments import nfl_ingame_prior_play_success_residual_audit as prior
from experiments import nfl_ingame_pre_anchor_market_momentum_residual_audit as momentum
from experiments import nfl_settlement_probability_train_diagnostic as settlement


TASK_ID = "InGamePreAnchorMomentumOffsetLogistic-v4"
QUESTION_ID = "ingame-pre-anchor-momentum-offset-logistic-v4-q1"
QUESTION_DIGEST = "8b72e8eed478b3c55d6d44f83eeae27c0667dbf485b21b079378dd4f0b64d217"
HYPOTHESIS_DIGEST = "3819263244cd2cbacbf3ea0ae244bef830e58e67a584d9f7f0387d5b5d73b3bf"
RULE_DIGEST = "914a33a6eb2361a655b136207742d05a61ceb8b6ec1cf9cdeb7f568e2b217ff4"
COMPONENT_SPEC_DIGEST = "d979e6e8e18652569baad58ed50a4c8974ae17b400cba5b126c7c7b2a4a6492d"
SELECTION_PLAN_DIGEST = "606453d5dcb1082dc3e046e8c7203bdb5a23ac4f548ab5d734c59e8d6b951122"
CONTROLLER_LOG = Path(__file__).parents[1] / "supervisor_harness" / (
    "AGENT_LOG_INGAME_PREDICTIVE_AUTONOMY_GENERATION1_CONTROLLER_2026-09-29.md"
)
CONTROLLER_LOG_SHA256 = "a6259940439dff5e6c86a0d1c4de73e634608bb7b3d82804731ac103674e4efb"
PARENT_REVIEW = Path(__file__).parents[1] / "supervisor_harness" / (
    "AGENT_LOG_INGAME_PRE_ANCHOR_MARKET_MOMENTUM_RESIDUAL_V3_RESULT_INDEPENDENT_REVIEW_2026-09-29.md"
)
PARENT_REVIEW_SHA256 = "48080a2ccaa188673d7a2e29bc47bb10c1761e3bfc61aab5905b29b95e5a3079"
PARENT_ARTIFACT_ROOT = Path(
    "/Users/estelle/Library/Application Support/MarketRSI/self-evolving-v18-local/"
    "artifacts/nfl-ingame-pre-anchor-market-momentum-residual-audit-20260929-01"
)
PARENT_ARTIFACT_HASHES = {
    "manifest.json": "9e7d5813a798a23da5e9992e079ec795e55d952529f11927f6244e9ac80f7499",
    "scorecard.json": "86ea1966786b523785512987fab174df3ac02b43c6b297d1e8cadf1a0e013d72",
    "event_audit.csv": "324a0c4e607321c10c5303c301109b847c18dcdc84d0018f503963f4f7eb3ba9",
    "input_receipts.json": "61bcf572a99863092af8721db4c532586172d9213c108ad6834e3fcd7dcdf2eb",
    "pre_audit_lock.json": "31023472c8af84803275aa3a43f250f8554040470725a30dbe477eff07dfd387",
}

SOURCE_ROOT = base.SOURCE_ROOT
PERSISTENT_ARTIFACT_ROOT = base.PERSISTENT_ARTIFACT_ROOT
V0_ARTIFACT_ROOT = prior.V0_ARTIFACT_ROOT
EXPECTED_EVENTS = 195
EXPECTED_DATES = 42
EXPECTED_MATERIALIZED_EVENTS = 193
EXPECTED_CHECK_EVENTS = 87
EXPECTED_FIT_EVENTS = (106, 132, 148, 176)
EXPECTED_CHECK_EVENTS_BY_FOLD = (26, 16, 28, 17)
EXPECTED_MATERIALIZED_KEY_SHA256 = offset.EXPECTED_MATERIALIZED_KEY_SHA256
EXPECTED_CHECK_KEY_SHA256 = offset.EXPECTED_CHECK_KEY_SHA256
EXPECTED_EXCLUSIONS = (
    ("2025_04_GB_DAL", "unresolved_outcome"),
    ("2025_05_TEN_ARI", "market_trade_too_stale"),
)
BOOTSTRAP_SEED = 20260929
BOOTSTRAP_REPLICATES = 10_000
MODEL_FITS = 4
PENALTY_LAMBDA = 1.0

ARM_RAW = "raw_market"
ARM_ORDINARY = "v0_ordinary_market_only"
ARM_CANDIDATE = "pre_anchor_momentum_offset_logistic"
ALL_ARMS = (ARM_RAW, ARM_ORDINARY, ARM_CANDIDATE)

THREAD_ENV_CONTRACT = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "PYTHONHASHSEED": "0",
}
SOLVER_SPEC = {
    "optimizer": "scipy.optimize.minimize",
    "method": "L-BFGS-B",
    "maxiter": 1000,
    "gtol": 1e-8,
    "ftol": 1e-12,
    "analytic_gradient": True,
    "objective": "sum Bernoulli NLL + 0.5 * beta^2",
    "market_logit_coefficient": 1.0,
    "intercept_penalized": False,
    "automatic_retries": 0,
}
CANDIDATE_COMPONENT_SPEC = {
    "signal": "logit_clip_1e-6(p_now)-logit_clip_1e-6(p_ref)",
    "reference_cutoff": "floor(decision_epoch_seconds)-120",
    "reference_fill": "latest home-oriented size-weighted fill second strictly before cutoff; age <=300 seconds",
    "normalization": "outer-fit mean/std only",
    "linear_predictor": "logit(p_now)+alpha+beta*z_momentum",
    "objective": "sum Bernoulli NLL + 0.5*beta^2",
    "outer_fits": MODEL_FITS,
    "retry_count": 0,
}
IMPLEMENTATION_COMPONENT_SPEC_SHA256 = _IMPLEMENTATION_COMPONENT_SPEC_SHA256 = (
    "813601e3d98ecafe5d3e9f3a79f4d1cb8df7e464ea6bcde48e53d094f42c9522"
)

SCHEDULER_BRANCH_BINDING = {
    "allocation": "exploitation",
    "attempt_id": "attempt-01",
    "batch_id": "market-rsi-ingame-predictive-autonomy-20260929-03",
    "candidate_id": TASK_ID,
    "comparison_incumbent_sha256": "89a8ef92c9cf4844b99e0136c51a1f8b896cdd66afcd23e8b8a23499859ffc7f",
    "controller_decision_sha256": CONTROLLER_LOG_SHA256,
    "hypothesis_digest_sha256": HYPOTHESIS_DIGEST,
    "method_family": "pre_anchor_momentum_offset_logistic_prediction",
    "pool_generation": 1,
    "predeclared_rule_sha256": RULE_DIGEST,
    "question_digest_sha256": QUESTION_DIGEST,
    "question_id": QUESTION_ID,
    "research_parent_sha256": "a99cf9889ad1e463e8ae2294711cb0b1ad94735be933f2e02ba99cdb49ca26b9",
    "resource_hint": {
        "authority_granted": False,
        "max_attempts": 1,
        "max_bytes": 0,
        "max_cost_usd": 0.0,
        "max_time_seconds": 1200,
        "resource_class": "small_experiment",
    },
    "selection_hint_sha256": "2ba03f832fbeddfc4e27d996ffffeefe10c41ee0c5714e57ee8c3db9525f8205",
}
SCHEDULER_BRANCH_BINDING_SHA256 = "ed420e45fbcffd083605bbd7b0517606a36cbafed25aaa747b056ec896a1b49f"
SCHEDULER_SELECTION_STATE_SHA256 = "860cfecc832f4123a9a1a1c6f38a735325b02ae725f2afbba56167084a81c3a5"


def _sha256(path: Path) -> str:
    return settlement._sha256(Path(path))


def _digest(value: object) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(body).hexdigest()


def _require_frozen_file(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or path.is_symlink() or _sha256(path) != expected:
        raise ValueError(f"frozen {label} missing, symlinked, or hash-changed")


def _validate_thread_contract() -> None:
    drift = {key: os.environ.get(key) for key, value in THREAD_ENV_CONTRACT.items()
             if os.environ.get(key) != value}
    if drift:
        raise ValueError(f"single-thread launch contract not satisfied: {drift}")


def _validate_execution_identity() -> None:
    checks = (
        (CONTROLLER_LOG, CONTROLLER_LOG_SHA256, "Controller decision"),
        (PARENT_REVIEW, PARENT_REVIEW_SHA256, "parent result review"),
        (Path(base.__file__), "e61668c7e29cf4dda95f6cc315b248dbe6744a9dcc0ae0cd6077d880ca6265b7", "v0 runner"),
        (Path(offset.__file__), "6194d25712df0e251fe0c56c671557967f8c7f5f7e62c28ca9981c09a3adf120", "offset runner"),
        (Path(momentum.__file__), "a99cf9889ad1e463e8ae2294711cb0b1ad94735be933f2e02ba99cdb49ca26b9", "parent runner"),
        (Path(nested.__file__), "a3026d5a12fa0028087f470e44b71f4e6eb9de1432e351e415e72a039b83f65b", "chronology dependency"),
        (Path(prior.__file__), "a612371ae77a78441c2d9416d6edc035a916879057fed9ef731de46476a07bcb", "v0 validator"),
        (Path(settlement.__file__), "1f1bdccd69d799be1af99ece4ee6198ffbd02f3a4550e651936fb3edfa83fb8b", "settlement dependency"),
    )
    for path, expected, label in checks:
        _require_frozen_file(path, expected, label)
    if _digest(CANDIDATE_COMPONENT_SPEC) != IMPLEMENTATION_COMPONENT_SPEC_SHA256:
        raise ValueError("implementation component spec digest changed")
    if _digest(SCHEDULER_BRANCH_BINDING) != SCHEDULER_BRANCH_BINDING_SHA256:
        raise ValueError("scheduler branch binding digest changed")
    if (not PARENT_ARTIFACT_ROOT.is_dir() or PARENT_ARTIFACT_ROOT.is_symlink()
            or sorted(path.name for path in PARENT_ARTIFACT_ROOT.iterdir())
            != sorted(PARENT_ARTIFACT_HASHES)):
        raise ValueError("parent audit artifact set changed")
    for name, expected in PARENT_ARTIFACT_HASHES.items():
        _require_frozen_file(PARENT_ARTIFACT_ROOT / name, expected, f"parent artifact {name}")
    _validate_thread_contract()


def _validate_paths(source_root: Path, output: Path, *, allow_test_paths: bool) -> None:
    base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)


def _v0_controls(frozen: Mapping[str, object]) -> dict[tuple[str, str, int], dict]:
    rows = frozen.get("predictions")
    if not isinstance(rows, list):
        raise ValueError("frozen v0 predictions are absent")
    result = {}
    for item in rows:
        key = (str(item["event_id"]), str(item["market_id"]), int(item["cutoff_ms"]))
        if key in result:
            raise ValueError("frozen v0 control key is duplicated")
        raw = validate_probability(float(item["raw_market_probability"]), DEFAULT_PROBABILITY_POLICY, ARM_RAW)
        ordinary = validate_probability(float(item["market_model_probability"]), DEFAULT_PROBABILITY_POLICY, ARM_ORDINARY)
        result[key] = {
            "fold": int(item["fold"]), "game_id": item["game_id"],
            "game_date": item["game_date"], "game_week": item["game_week"],
            "outcome": int(item["outcome"]), "raw_probability": raw,
            "ordinary_probability": ordinary,
        }
    if len(result) != EXPECTED_CHECK_EVENTS:
        raise ValueError("frozen ordinary control population changed")
    return result


def _materialize(source_root: Path, cohort: Sequence[dict], frozen: Mapping[str, object]
                 ) -> tuple[list[base.InGameRow], list[dict]]:
    anchors = frozen.get("anchors")
    if not isinstance(anchors, list):
        raise ValueError("frozen checkpoint anchors are absent")
    states = {str(row["game_id"]): row for row in anchors}
    if len(states) != EXPECTED_EVENTS:
        raise ValueError("frozen checkpoint anchor population changed")
    rows, exclusions = [], []
    for ordinal, item in enumerate(cohort):
        try:
            rows.append(base._load_dynamic_market(source_root, item, states[item["game_id"]]))
        except settlement.EventExclusion as error:
            exclusions.append({
                "source_ordinal": ordinal, "game_id": item["game_id"],
                "game_date": item["game_date"], "reason": error.code,
                "detail": str(error)[:400],
            })
    rows.sort(key=lambda row: row.key)
    if (len(rows) != EXPECTED_MATERIALIZED_EVENTS
            or tuple((item["game_id"], item["reason"]) for item in exclusions) != EXPECTED_EXCLUSIONS
            or _digest([list(row.key) for row in rows]) != EXPECTED_MATERIALIZED_KEY_SHA256):
        raise ValueError("exact 195 -> 193 + 2 v0 materialization changed")
    return rows, exclusions


def _all_row_signals(source_root: Path, rows: Sequence[base.InGameRow],
                     cohort: Sequence[dict], frozen: Mapping[str, object]
                     ) -> tuple[dict[tuple[str, str, int], dict], list[dict]]:
    cohort_by_id = {item["game_id"]: item for item in cohort}
    anchors = frozen.get("anchors")
    if not isinstance(anchors, list):
        raise ValueError("frozen checkpoint anchors are absent")
    anchor_by_id = {str(item["game_id"]): item for item in anchors}
    signals, receipts = {}, []
    for row in rows:
        if row.game_id not in cohort_by_id or row.game_id not in anchor_by_id:
            raise ValueError("materialized row lacks cohort or anchor lineage")
        decision_floor = int(row.trusted["cutoff_ms"]) // 1000
        trades, receipt = momentum._load_oriented_trades(
            source_root, cohort_by_id[row.game_id], anchor_by_id[row.game_id], row.source_receipt
        )
        value = momentum.market_momentum_signal(trades, decision_floor)
        if (value["p_now"] != row.trusted["market_probability"]
                or value["current_latest_trade_epoch_s"] * 1000
                != int(row.source_receipt["latest_trade_epoch_ms"])):
            raise ValueError("replayed current market differs from v0 materialization")
        if row.key in signals:
            raise ValueError("momentum signal key is duplicated")
        signals[row.key] = value
        receipts.append({"game_id": row.game_id, **receipt, **{
            key: value[key] for key in (
                "decision_floor_epoch_s", "current_latest_trade_epoch_s",
                "reference_cutoff_epoch_s", "reference_latest_trade_epoch_s",
                "reference_age_seconds",
            )
        }})
    if len(signals) != len(rows):
        raise ValueError("momentum coverage must include every materialized fit/check row")
    return signals, receipts


def standardize_momentum(fit: object, check: object) -> tuple[np.ndarray, np.ndarray, dict]:
    fit_values = np.asarray(fit, dtype=np.float64)
    check_values = np.asarray(check, dtype=np.float64)
    if (fit_values.ndim != 1 or fit_values.size == 0 or check_values.ndim != 1
            or check_values.size == 0 or not np.all(np.isfinite(fit_values))
            or not np.all(np.isfinite(check_values))):
        raise ValueError("fit/check momentum must be nonempty finite vectors")
    mean = float(np.mean(fit_values))
    scale = float(np.std(fit_values, ddof=0))
    if not math.isfinite(scale) or scale <= 1e-8:
        raise ValueError("outer-fit momentum standard deviation is inactive")
    return ((fit_values - mean) / scale, (check_values - mean) / scale, {
        "fit_only": True, "mean": mean, "scale": scale,
        "fit_events": int(fit_values.size), "check_events": int(check_values.size),
    })


def momentum_objective_gradient(parameters: object, standardized_momentum: object,
                                outcomes: object, market_logits: object
                                ) -> tuple[float, np.ndarray]:
    features = np.asarray(standardized_momentum, dtype=np.float64)
    if features.ndim != 1:
        raise ValueError("standardized momentum must be one-dimensional")
    return offset.offset_objective_gradient(
        parameters, features[:, None], outcomes, market_logits,
        penalty_lambda=PENALTY_LAMBDA,
    )


def fit_momentum_offset(standardized_fit: object, outcomes: object,
                        fit_market_logits: object) -> tuple[np.ndarray, dict]:
    features = np.asarray(standardized_fit, dtype=np.float64)
    labels = np.asarray(outcomes, dtype=np.float64)
    offsets = np.asarray(fit_market_logits, dtype=np.float64)
    if (features.ndim != 1 or features.size == 0 or labels.shape != features.shape
            or offsets.shape != features.shape or not np.all(np.isfinite(features))
            or not np.all(np.isfinite(labels)) or not np.all(np.isin(labels, (0.0, 1.0)))
            or not np.all(np.isfinite(offsets))):
        raise ValueError("fit vectors must be finite, aligned, and binary-labelled")

    def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
        return momentum_objective_gradient(theta, features, labels, offsets)

    result = minimize(
        objective, np.zeros(2, dtype=np.float64), method="L-BFGS-B", jac=True,
        options={"maxiter": 1000, "gtol": 1e-8, "ftol": 1e-12},
    )
    parameters = np.asarray(result.x, dtype=np.float64)
    final_objective, final_gradient = objective(parameters)
    gradient_inf = float(np.max(np.abs(final_gradient)))
    if (not bool(result.success) or parameters.shape != (2,)
            or not np.all(np.isfinite(parameters)) or not math.isfinite(final_objective)
            or not np.all(np.isfinite(final_gradient)) or gradient_inf > 1e-5):
        raise RuntimeError(
            "momentum offset optimizer failed frozen convergence checks: "
            f"success={result.success}, status={result.status}, objective={final_objective}, "
            f"grad_inf={gradient_inf}, message={str(result.message)[:300]}"
        )
    return parameters, {
        "success": True, "status": int(result.status), "message": str(result.message)[:300],
        "iterations": int(result.nit), "function_evaluations": int(result.nfev),
        "objective": final_objective, "gradient_infinity_norm": gradient_inf,
        "alpha": float(parameters[0]), "beta_momentum": float(parameters[1]),
        "market_logit_coefficient_fixed": 1.0, "beta_penalty_lambda": PENALTY_LAMBDA,
        "intercept_penalized": False, "retry_count": 0,
    }


def momentum_probabilities(parameters: object, standardized_momentum: object,
                           market_logits: object) -> np.ndarray:
    features = np.asarray(standardized_momentum, dtype=np.float64)
    if features.ndim != 1:
        raise ValueError("standardized momentum must be one-dimensional")
    values = offset.offset_probabilities(parameters, features[:, None], market_logits)
    for value in values:
        validate_probability(float(value), DEFAULT_PROBABILITY_POLICY, ARM_CANDIDATE)
    return values


def _fit_and_predict(rows: Sequence[base.InGameRow], folds: Sequence[dict],
                     signals: Mapping[tuple[str, str, int], dict],
                     controls: Mapping[tuple[str, str, int], dict]
                     ) -> tuple[list[dict], list[dict]]:
    if set(signals) != {row.key for row in rows}:
        raise ValueError("momentum signals must cover the complete materialized population")
    by_date: dict[str, list[base.InGameRow]] = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    predictions, reports = [], []
    fit_count = 0
    for fold in folds:
        check_rows = sorted(
            [row for date in fold["check_dates"] for row in by_date.get(date, [])],
            key=lambda row: row.key,
        )
        fit_rows, unavailable = nested._strict_prior_rows(by_date, fold["fit_dates"], check_rows)
        fit_signal = [float(signals[row.key]["signal"]) for row in fit_rows]
        check_signal = [float(signals[row.key]["signal"]) for row in check_rows]
        z_fit, z_check, scaling = standardize_momentum(fit_signal, check_signal)
        parameters, optimizer = fit_momentum_offset(
            z_fit,
            [row.trusted["outcome"] for row in fit_rows],
            [row.market_features[0] for row in fit_rows],
        )
        fit_count += 1
        candidate_values = momentum_probabilities(
            parameters, z_check, [row.market_features[0] for row in check_rows]
        )
        raw_values, ordinary_values, outcomes = [], [], []
        for row in check_rows:
            control = controls.get(row.key)
            if control is None:
                raise ValueError("check row is absent from frozen v0 ordinary control")
            raw = validate_probability(
                float(row.trusted["market_probability"]), DEFAULT_PROBABILITY_POLICY, ARM_RAW
            )
            if (control["fold"] != fold["fold"] or control["game_id"] != row.game_id
                    or control["game_date"] != row.game_date
                    or control["game_week"] != row.game_week
                    or control["outcome"] != row.trusted["outcome"]
                    or control["raw_probability"] != raw):
                raise ValueError("frozen v0 ordinary identity/label/raw market changed")
            raw_values.append(raw)
            ordinary_values.append(control["ordinary_probability"])
            outcomes.append(row.trusted["outcome"])
        arms = {
            ARM_RAW: settlement._simple_metrics(outcomes, raw_values),
            ARM_ORDINARY: settlement._simple_metrics(outcomes, ordinary_values),
            ARM_CANDIDATE: settlement._simple_metrics(outcomes, candidate_values),
        }
        reports.append({
            "fold": fold["fold"], "fit_dates": list(fold["fit_dates"]),
            "check_dates": list(fold["check_dates"]), "fit_events": len(fit_rows),
            "check_events": len(check_rows), "fit_label_unavailable_game_ids": unavailable,
            "momentum_scaling": scaling, "optimizer": optimizer, "arms": arms,
            "candidate_minus_raw_market_brier": arms[ARM_CANDIDATE]["brier"] - arms[ARM_RAW]["brier"],
            "candidate_minus_v0_ordinary_brier": arms[ARM_CANDIDATE]["brier"] - arms[ARM_ORDINARY]["brier"],
            "same_rows_labels_and_checkpoints": True,
        })
        for index, row in enumerate(check_rows):
            predictions.append({
                "fold": fold["fold"], "row": row, "signal": signals[row.key],
                ARM_RAW: raw_values[index], ARM_ORDINARY: ordinary_values[index],
                ARM_CANDIDATE: float(candidate_values[index]),
            })
    if fit_count != MODEL_FITS:
        raise RuntimeError(f"exactly {MODEL_FITS} candidate fits required; observed {fit_count}")
    keys = [item["row"].key for item in predictions]
    if len(keys) != len(set(keys)) or set(keys) != set(controls):
        raise ValueError("candidate/raw/ordinary common check mask changed")
    return predictions, reports


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
        record = {"game_id": row.game_id, "game_date": row.game_date,
                  "game_week": row.game_week, "outcome": row.trusted["outcome"]}
        for metric in ("brier", "log_loss"):
            loss = {arm: offset._loss(row.trusted["outcome"], item[arm], metric) for arm in ALL_ARMS}
            record[f"candidate_minus_raw_market_{metric}"] = loss[ARM_CANDIDATE] - loss[ARM_RAW]
            record[f"candidate_minus_v0_ordinary_{metric}"] = loss[ARM_CANDIDATE] - loss[ARM_ORDINARY]
            record[f"v0_ordinary_minus_raw_market_{metric}"] = loss[ARM_ORDINARY] - loss[ARM_RAW]
        records.append(record)
    return records


def _paired_evidence(records: Sequence[dict]) -> dict:
    evidence = {}
    for comparison in (
        "candidate_minus_raw_market", "candidate_minus_v0_ordinary",
        "v0_ordinary_minus_raw_market",
    ):
        evidence[comparison] = {}
        for metric in ("brier", "log_loss"):
            key = f"{comparison}_{metric}"
            evidence[comparison][metric] = {
                "delta_convention": f"{comparison}; negative loss is better",
                "equal_event_mean": math.fsum(row[key] for row in records) / len(records),
                "by_schedule_date": base._group_means(records, "game_date", key),
                "schedule_date_interval": base._group_bootstrap(
                    records, "game_date", key, seed=BOOTSTRAP_SEED,
                    replicates=BOOTSTRAP_REPLICATES,
                ),
                "observed_game_week_interval": base._group_bootstrap(
                    records, "game_week", key, seed=BOOTSTRAP_SEED,
                    replicates=BOOTSTRAP_REPLICATES,
                ),
            }
    return evidence


def momentum_offset_decision(aggregate: Mapping[str, dict], folds: Sequence[dict],
                             paired: Mapping[str, dict]) -> tuple[str, str, dict]:
    candidate, raw, ordinary = (
        aggregate[ARM_CANDIDATE], aggregate[ARM_RAW], aggregate[ARM_ORDINARY]
    )
    raw_wins = [fold["arms"][ARM_CANDIDATE]["brier"] < fold["arms"][ARM_RAW]["brier"] for fold in folds]
    ordinary_wins = [fold["arms"][ARM_CANDIDATE]["brier"] < fold["arms"][ARM_ORDINARY]["brier"] for fold in folds]
    date_upper = float(paired["candidate_minus_raw_market"]["brier"]["schedule_date_interval"]["interval_95"][1])
    week_upper = float(paired["candidate_minus_raw_market"]["brier"]["observed_game_week_interval"]["interval_95"][1])
    conditions = {
        "candidate_brier_below_raw_market": candidate["brier"] < raw["brier"],
        "candidate_log_loss_below_raw_market": candidate["log_loss"] < raw["log_loss"],
        "candidate_brier_below_v0_ordinary": candidate["brier"] < ordinary["brier"],
        "candidate_log_loss_below_v0_ordinary": candidate["log_loss"] < ordinary["log_loss"],
        "candidate_raw_brier_fold_wins_at_least_3_of_4": sum(raw_wins) >= 3,
        "candidate_ordinary_brier_fold_wins_at_least_3_of_4": sum(ordinary_wins) >= 3,
        "date_grouped_candidate_minus_raw_brier_upper_below_zero": date_upper < 0,
        "week_grouped_candidate_minus_raw_brier_upper_below_zero": week_upper < 0,
        "candidate_raw_brier_fold_wins_at_most_1_of_4": sum(raw_wins) <= 1,
        "raw_brier_fold_wins": raw_wins, "ordinary_brier_fold_wins": ordinary_wins,
    }
    support = all(conditions[key] for key in (
        "candidate_brier_below_raw_market", "candidate_log_loss_below_raw_market",
        "candidate_brier_below_v0_ordinary", "candidate_log_loss_below_v0_ordinary",
        "candidate_raw_brier_fold_wins_at_least_3_of_4",
        "candidate_ordinary_brier_fold_wins_at_least_3_of_4",
        "date_grouped_candidate_minus_raw_brier_upper_below_zero",
        "week_grouped_candidate_minus_raw_brier_upper_below_zero",
    ))
    refute = (not conditions["candidate_brier_below_raw_market"]
              or not conditions["candidate_log_loss_below_raw_market"]
              or conditions["candidate_raw_brier_fold_wins_at_most_1_of_4"])
    scientific = ("PRE_ANCHOR_MOMENTUM_OFFSET_SUPPORTED" if support else
                  "PRE_ANCHOR_MOMENTUM_OFFSET_REFUTED" if refute else
                  "PRE_ANCHOR_MOMENTUM_OFFSET_INCONCLUSIVE")
    return scientific, ("KEEP" if support else "REVERT"), conditions


def _write_predictions(path: Path, predictions: Sequence[dict]) -> None:
    fields = (
        "fold", "game_id", "game_date", "game_week", "event_id", "market_id",
        "cutoff_ms", "outcome_available_ms", "outcome", "raw_market_probability",
        "v0_ordinary_market_only_probability", "pre_anchor_momentum_offset_probability",
        "parent_reference_probability", "parent_momentum_signal",
        "parent_reference_cutoff_epoch_s", "parent_reference_latest_trade_epoch_s",
        "parent_reference_age_seconds",
    )
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in predictions:
            row, signal = item["row"], item["signal"]
            writer.writerow({
                "fold": item["fold"], "game_id": row.game_id, "game_date": row.game_date,
                "game_week": row.game_week, "event_id": row.trusted["event_id"],
                "market_id": row.trusted["market_id"], "cutoff_ms": row.trusted["cutoff_ms"],
                "outcome_available_ms": row.trusted["outcome_available_ms"],
                "outcome": row.trusted["outcome"], "raw_market_probability": item[ARM_RAW],
                "v0_ordinary_market_only_probability": item[ARM_ORDINARY],
                "pre_anchor_momentum_offset_probability": item[ARM_CANDIDATE],
                "parent_reference_probability": signal["p_ref"],
                "parent_momentum_signal": signal["signal"],
                "parent_reference_cutoff_epoch_s": signal["reference_cutoff_epoch_s"],
                "parent_reference_latest_trade_epoch_s": signal["reference_latest_trade_epoch_s"],
                "parent_reference_age_seconds": signal["reference_age_seconds"],
            })
        stream.flush(); os.fsync(stream.fileno())
    temporary.replace(path)


def run(source_root: Path, output: Path, *, allow_test_paths: bool = False,
        generated_utc: str | None = None) -> dict:
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    _validate_paths(source_root, output, allow_test_paths=allow_test_paths)
    output.mkdir(parents=True, exist_ok=False)
    try:
        if not allow_test_paths:
            _validate_execution_identity()
        frozen = prior._validate_v0_artifact(V0_ARTIFACT_ROOT)
        cohort = base._validate_source(
            source_root, expected_events=EXPECTED_EVENTS, expected_dates=EXPECTED_DATES,
            allow_test_paths=allow_test_paths,
        )
        pbp_receipts = base._validate_pbp_receipts(source_root, cohort)
        rows, exclusions = _materialize(source_root, cohort, frozen)
        signals, trade_receipts = _all_row_signals(source_root, rows, cohort, frozen)
        controls = _v0_controls(frozen)
        folds = frozen["folds"]
        receipts = {
            "schema": "nfl_ingame_pre_anchor_momentum_offset_inputs_v4",
            "task_id": TASK_ID, "runner_sha256": _sha256(Path(__file__)),
            "controller_log_sha256": CONTROLLER_LOG_SHA256,
            "parent_runner_sha256": SCHEDULER_BRANCH_BINDING["research_parent_sha256"],
            "parent_review_sha256": PARENT_REVIEW_SHA256,
            "parent_artifact_hashes": PARENT_ARTIFACT_HASHES,
            "v0_artifact_hashes": frozen["hashes"], "pbp_receipts": pbp_receipts,
            "trade_receipts": trade_receipts, "thread_environment": {
                key: os.environ.get(key) for key in THREAD_ENV_CONTRACT
            },
            "route_dev_opened": False, "sealed_final_opened": False,
            "external_fetch": False, "paid_provider": False, "provider_cost_usd": "0",
        }
        base._atomic_json(output / "input_receipts.json", receipts)
        base._atomic_json(output / "exclusions.json", {
            "schema": "nfl_ingame_pre_anchor_momentum_offset_exclusions_v4",
            "source_events": EXPECTED_EVENTS, "materialized_events": len(rows),
            "excluded_events": len(exclusions), "exclusions": exclusions,
            "reconciles_to_source_denominator": len(rows) + len(exclusions) == EXPECTED_EVENTS,
        })
        lock = {
            "schema": "nfl_ingame_pre_anchor_momentum_offset_pre_score_lock_v4",
            "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "task_id": TASK_ID, "question_id": QUESTION_ID,
            "question_digest_sha256": QUESTION_DIGEST,
            "hypothesis_digest_sha256": HYPOTHESIS_DIGEST,
            "predeclared_rule_sha256": RULE_DIGEST,
            "component_spec_sha256": COMPONENT_SPEC_DIGEST,
            "implementation_component_spec_sha256": IMPLEMENTATION_COMPONENT_SPEC_SHA256,
            "selection_plan_sha256": SELECTION_PLAN_DIGEST,
            "controller_log_sha256": CONTROLLER_LOG_SHA256,
            "scheduler_branch_binding": SCHEDULER_BRANCH_BINDING,
            "scheduler_branch_binding_sha256": SCHEDULER_BRANCH_BINDING_SHA256,
            "scheduler_selection_state_sha256": SCHEDULER_SELECTION_STATE_SHA256,
            "candidate_component_spec": CANDIDATE_COMPONENT_SPEC,
            "solver": SOLVER_SPEC, "thread_environment_contract": THREAD_ENV_CONTRACT,
            "ordinary_baseline": {
                "source": "frozen v0 predictions.csv market_model_probability",
                "predictions_sha256": prior.EXPECTED_V0_HASHES["predictions.csv"],
                "refit": False,
            },
            "parent_lineage": {
                "task": momentum.TASK_ID, "runner_sha256": SCHEDULER_BRANCH_BINDING["research_parent_sha256"],
                "manifest_sha256": PARENT_ARTIFACT_HASHES["manifest.json"],
                "review_sha256": PARENT_REVIEW_SHA256,
            },
            "folds": folds, "expected_fit_events": list(EXPECTED_FIT_EVENTS),
            "expected_check_events_by_fold": list(EXPECTED_CHECK_EVENTS_BY_FOLD),
            "fit_budget": MODEL_FITS, "automatic_retries": 0,
            "primary_metric": "equal-event Brier on exact 87-row common mask",
            "bootstrap_seed": BOOTSTRAP_SEED, "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "resource_cap": {"processes": 1, "threads": 1, "fits": MODEL_FITS,
                             "wall_seconds": 1200, "rss_gib": 1, "network_bytes": 0,
                             "provider_calls": 0, "provider_cost_usd": "0", "retries": 0},
            "route_dev_opened": False, "sealed_final_opened": False,
            "external_fetch": False, "paid_provider": False, "provider_cost_usd": "0",
            "promotion_authorized": False,
        }
        base._atomic_json(output / "pre_score_lock.json", lock)
        predictions, fold_reports = _fit_and_predict(rows, folds, signals, controls)
        check_hash = _digest([list(item["row"].key) for item in predictions])
        if (len(predictions) != EXPECTED_CHECK_EVENTS or check_hash != EXPECTED_CHECK_KEY_SHA256
                or tuple(item["fit_events"] for item in fold_reports) != EXPECTED_FIT_EVENTS
                or tuple(item["check_events"] for item in fold_reports) != EXPECTED_CHECK_EVENTS_BY_FOLD
                or any(item["fit_label_unavailable_game_ids"] for item in fold_reports)):
            raise ValueError("frozen v0 folds, common mask, or label availability changed")
        aggregate = _aggregate(predictions)
        paired = _paired_evidence(_paired_records(predictions))
        scientific, operational, conditions = momentum_offset_decision(aggregate, fold_reports, paired)
        scorecard = {
            "schema": "nfl_ingame_pre_anchor_momentum_offset_scorecard_v4",
            "task_id": TASK_ID, "scientific_decision": scientific,
            "operational_decision": operational, "decision_conditions": conditions,
            "source_denominator": {"events": EXPECTED_EVENTS, "dates": EXPECTED_DATES,
                "materialized_events": len(rows), "excluded_events": len(exclusions),
                "check_events": len(predictions),
                "check_dates": len({item["row"].game_date for item in predictions}),
                "check_game_weeks": len({item["row"].game_week for item in predictions})},
            "identical_masks": {"all_three_probability_arms_same_rows_labels_and_checkpoints": True,
                "check_key_sha256": check_hash, "matches_frozen_v0": check_hash == EXPECTED_CHECK_KEY_SHA256,
                "one_checkpoint_per_game": len(predictions) == len({item["row"].game_id for item in predictions})},
            "model_fits": MODEL_FITS, "ordinary_control_refits": 0,
            "aggregate": aggregate, "folds": fold_reports, "paired_grouped_evidence": paired,
            "deltas": {comparison: {
                metric: paired[comparison][metric]["equal_event_mean"] for metric in ("brier", "log_loss")
            } for comparison in paired},
            "parent_lineage": lock["parent_lineage"],
            "inference_boundary": "repeatedly inspected opened-Train Discovery; not untouched OOS, promotion, deployment, PnL, or realtime proof",
            "incumbent_changed": operational == "KEEP",
            "route_dev_opened": False, "sealed_final_opened": False, "external_fetch": False,
            "paid_provider": False, "provider_cost_usd": "0", "promotion_authorized": False,
        }
        _write_predictions(output / "predictions.csv", predictions)
        base._atomic_json(output / "scorecard.json", scorecard)
        manifest = {
            "schema": "nfl_ingame_pre_anchor_momentum_offset_manifest_v4", "complete": True,
            "completed_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
            "task_id": TASK_ID, "pre_score_lock_sha256": _sha256(output / "pre_score_lock.json"),
            "input_receipts_sha256": _sha256(output / "input_receipts.json"),
            "exclusions_sha256": _sha256(output / "exclusions.json"),
            "predictions_sha256": _sha256(output / "predictions.csv"),
            "scorecard_sha256": _sha256(output / "scorecard.json"),
            "source_events": EXPECTED_EVENTS, "materialized_events": len(rows),
            "excluded_events": len(exclusions), "check_events": len(predictions),
            "model_fits": MODEL_FITS, "ordinary_control_refits": 0,
            "scientific_decision": scientific, "operational_decision": operational,
            "historical_event_clock_only": True, "route_dev_opened": False,
            "sealed_final_opened": False, "external_fetch": False, "paid_provider": False,
            "provider_cost_usd": "0", "promotion_authorized": False,
        }
        base._atomic_json(output / "manifest.json", manifest)
        return manifest
    except Exception as error:
        if output.exists() and not (output / "manifest.json").exists():
            base._atomic_json(output / "failure.json", {
                "schema": "nfl_ingame_pre_anchor_momentum_offset_failure_v4",
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
    print(json.dumps({key: result[key] for key in (
        "complete", "task_id", "check_events", "model_fits",
        "scientific_decision", "operational_decision", "provider_cost_usd",
    )}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
