#!/usr/bin/env python3
"""Four-fold prior-play-success uncertainty-stratified offset diagnostic."""
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
from scipy.special import expit

from minimal_prediction_loop.probability_contract import (
    DEFAULT_PROBABILITY_POLICY, validate_probability,
)
from experiments import nfl_ingame_win_probability_train_diagnostic as base
from experiments import nfl_ingame_prior_play_success_residual_audit as prior
from experiments import nfl_ingame_prior_play_success_market_uncertainty_audit as uncertainty
from experiments import nfl_ingame_identity_anchored_market_calibration as identity
from experiments import nfl_ingame_static_state_nested_shrinkage_train_diagnostic as nested
from experiments import nfl_settlement_probability_train_diagnostic as settlement


TASK_ID = "InGamePriorPlaySuccessUncertaintyStratifiedOffset-v4"
QUESTION_ID = "ingame-prior-play-success-uncertainty-stratified-offset-v4-q1"
QUESTION_DIGEST = "07f351446245acacefb0a21b5e24ac82e590936a753dc7347a735a1ab7377026"
HYPOTHESIS_DIGEST = "21255a12838e33b05df9dc4fc92b4a0a7d063216c3cf475f2558416c167f0fea"
RULE_DIGEST = "aa9a76e5a245c5cc353cb1ca236d19069f72cda1e522afad956cda72bb70bb4d"
COMPONENT_SPEC_DIGEST = "a0f6647768c575fa95b9826a917faf53baed4891125d549ae9d892cadfa7dbde"
SELECTION_RECORD_DIGEST = "0d7e7fc61de795ca13ac546c7c96ffd55f2362bb62c94647a0eb2155b533003e"
RECOVERY_STATE_HINT_SHA256 = "a702cf0354cdac9c088c742d1197ec41e80e4c00719f44fc487c2ff57ff63137"
CONTROLLER_LOG = Path(__file__).parents[1] / "supervisor_harness" / (
    "AGENT_LOG_INGAME_PREDICTIVE_AUTONOMY_GENERATION2_SINGLE_CANDIDATE_CONTROLLER_2026-09-29.md"
)
CONTROLLER_LOG_SHA256 = "db9481637ab55dec104bdd9cde4a0199022ea404781e60bec9563c05aad94eb8"

SOURCE_ROOT = base.SOURCE_ROOT
PERSISTENT_ARTIFACT_ROOT = base.PERSISTENT_ARTIFACT_ROOT
V0_ARTIFACT_ROOT = prior.V0_ARTIFACT_ROOT
FEATURE_ARTIFACT_ROOT = uncertainty.PARENT_ARTIFACT_ROOT
EXPECTED_EVENTS = 195
EXPECTED_DATES = 42
EXPECTED_MATERIALIZED_EVENTS = 193
EXPECTED_CHECK_EVENTS = 87
EXPECTED_FIT_EVENTS = (106, 132, 148, 176)
EXPECTED_CHECK_EVENTS_BY_FOLD = (26, 16, 28, 17)
EXPECTED_CHECK_KEY_SHA256 = prior.EXPECTED_CHECK_KEY_SHA256
EXPECTED_EXCLUSIONS = (
    ("2025_04_GB_DAL", "unresolved_outcome"),
    ("2025_05_TEN_ARI", "market_trade_too_stale"),
)
FEATURE_SHA256 = "cca09f294f88f19a5cfa05fce294d6ec2a11c6264fed54840460784cbabea764"
FEATURE_MANIFEST_SHA256 = "addececc96838399be8b9713b85048dba6c449e840aff6f69f099f1779750144"

ARM_RAW = "raw_market"
ARM_ORDINARY = "frozen_v0_ordinary_market_only"
ARM_PARENT = "frozen_v0_market_plus_state_parent"
ARM_CANDIDATE = "prior_play_success_uncertainty_stratified_offset"
ALL_ARMS = (ARM_RAW, ARM_ORDINARY, ARM_PARENT, ARM_CANDIDATE)
UNCERTAINTY_THRESHOLD = 0.1875
PENALTY = 16.0
MAX_ITERATIONS = 50
GRADIENT_TOLERANCE = 1e-8
MODEL_FITS = 4
BOOTSTRAP_SEED = 20260929
BOOTSTRAP_REPLICATES = 10_000
THREAD_ENV_CONTRACT = identity.THREAD_ENV_CONTRACT

COMPONENT_SPEC = {
    "features": [
        "x_low=s if p_now*(1-p_now)<0.1875 else 0",
        "x_high=s if p_now*(1-p_now)>=0.1875 else 0",
    ],
    "linear_predictor": "logit(p_now)+beta_low*x_low+beta_high*x_high",
    "intercept": False, "market_logit_coefficient": 1.0,
    "objective": "sum Bernoulli NLL + 0.5*16*(beta_low^2+beta_high^2)",
    "solver": "deterministic analytic damped Newton", "maximum_iterations": 50,
    "gradient_infinity_tolerance": 1e-8, "outer_fits": 4, "retries": 0,
}
IMPLEMENTATION_COMPONENT_SPEC_SHA256 = "67acf31036ba2272af31a529dbdb2589ad77e457bd81aed4036ddcfc61bacc2d"
SCHEDULER_BRANCH_BINDING = {
    "allocation": "exploitation", "attempt_id": "attempt-03",
    "candidate_id": TASK_ID,
    "comparison_incumbent_sha256": "89a8ef92c9cf4844b99e0136c51a1f8b896cdd66afcd23e8b8a23499859ffc7f",
    "controller_decision_sha256": CONTROLLER_LOG_SHA256,
    "hypothesis_digest_sha256": HYPOTHESIS_DIGEST,
    "method_family": "prior_play_success_uncertainty_stratified_offset_prediction",
    "predeclared_rule_sha256": RULE_DIGEST, "question_digest_sha256": QUESTION_DIGEST,
    "question_id": QUESTION_ID,
    "research_parent_sha256": "c40b1df57588b296e72ffe5b220c91aa0dd16d31ef1c573bdb4b0e7c0d72f79d",
    "resource_hint": {"authority_granted": False, "max_attempts": 1,
        "max_bytes": 0, "max_cost_usd": 0.0, "max_time_seconds": 900,
        "resource_class": "small_experiment"},
    "recovery_state_hint_sha256": RECOVERY_STATE_HINT_SHA256,
}
SCHEDULER_BRANCH_BINDING_SHA256 = "3a980cf0cd33380a2ccfc5aff3779cf48ee18508dfe717f728ffa7d3a4cd50f1"


def _sha256(path: Path) -> str:
    return settlement._sha256(Path(path))


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


def _require_dependencies() -> None:
    checks = (
        (CONTROLLER_LOG, CONTROLLER_LOG_SHA256, "Controller"),
        (Path(base.__file__), "e61668c7e29cf4dda95f6cc315b248dbe6744a9dcc0ae0cd6077d880ca6265b7", "v0 runner"),
        (Path(prior.__file__), "a612371ae77a78441c2d9416d6edc035a916879057fed9ef731de46476a07bcb", "feature validator"),
        (Path(uncertainty.__file__), "e51f85ed368c53545369dfdd7505dcee3331917cba115ebacb5194290808e745", "uncertainty audit"),
        (Path(identity.__file__), "dc4e372440dc3f29091770394a8989c3602e83c37f0909367a5ce321bc614b05", "scorecard scaffold"),
        (Path(nested.__file__), "a3026d5a12fa0028087f470e44b71f4e6eb9de1432e351e415e72a039b83f65b", "chronology dependency"),
    )
    for path, expected, label in checks:
        if not path.is_file() or path.is_symlink() or _sha256(path) != expected:
            raise ValueError(f"frozen {label} missing, symlinked, or hash-changed")
    if _digest(COMPONENT_SPEC) != IMPLEMENTATION_COMPONENT_SPEC_SHA256:
        raise ValueError("implementation component spec changed")
    if _digest(SCHEDULER_BRANCH_BINDING) != SCHEDULER_BRANCH_BINDING_SHA256:
        raise ValueError("scheduler recovery binding changed")
    identity._require_single_thread_environment()


def stratified_features(signals: object, probabilities: object) -> np.ndarray:
    values = np.asarray(signals, dtype=np.float64)
    p = np.asarray(probabilities, dtype=np.float64)
    if (values.ndim != 1 or p.shape != values.shape or values.size == 0
            or not np.all(np.isfinite(values)) or not np.all(np.isfinite(p))
            or np.any(p < DEFAULT_PROBABILITY_POLICY.epsilon)
            or np.any(p > 1 - DEFAULT_PROBABILITY_POLICY.epsilon)):
        raise ValueError("signals/probabilities must be aligned finite endpoint-safe vectors")
    high = p * (1.0 - p) >= UNCERTAINTY_THRESHOLD
    return np.column_stack((np.where(high, 0.0, values), np.where(high, values, 0.0)))


def objective_gradient_hessian(parameters: object, features: object, outcomes: object,
                               market_logits: object) -> tuple[float, np.ndarray, np.ndarray]:
    theta = np.asarray(parameters, dtype=np.float64)
    design = np.asarray(features, dtype=np.float64)
    labels = np.asarray(outcomes, dtype=np.float64)
    offsets = np.asarray(market_logits, dtype=np.float64)
    if (theta.shape != (2,) or design.ndim != 2 or design.shape[1] != 2
            or labels.shape != (design.shape[0],) or offsets.shape != labels.shape
            or design.shape[0] == 0 or not all(np.all(np.isfinite(item)) for item in (theta, design, labels, offsets))
            or np.any((labels != 0) & (labels != 1))):
        raise ValueError("stratified objective inputs are invalid or misaligned")
    eta = offsets + design @ theta
    probabilities = expit(eta)
    objective = float(np.sum(np.logaddexp(0.0, eta) - labels * eta))
    objective += 0.5 * PENALTY * float(theta @ theta)
    gradient = design.T @ (probabilities - labels) + PENALTY * theta
    hessian = design.T @ (design * (probabilities * (1.0 - probabilities))[:, None])
    hessian += PENALTY * np.eye(2)
    if not (math.isfinite(objective) and np.all(np.isfinite(gradient)) and np.all(np.isfinite(hessian))):
        raise FloatingPointError("stratified objective became nonfinite")
    return objective, gradient, hessian


def fit_stratified_offset(features: object, outcomes: object,
                          market_logits: object) -> tuple[np.ndarray, dict]:
    design = np.asarray(features, dtype=np.float64)
    labels = np.asarray(outcomes, dtype=np.float64)
    offsets = np.asarray(market_logits, dtype=np.float64)
    theta = np.zeros(2, dtype=np.float64)
    evaluations = backtracks = 0
    for iteration in range(MAX_ITERATIONS + 1):
        objective, gradient, hessian = objective_gradient_hessian(theta, design, labels, offsets)
        evaluations += 1
        grad_inf = float(np.max(np.abs(gradient)))
        if grad_inf <= GRADIENT_TOLERANCE:
            return theta, {"converged": True, "iterations": iteration,
                "function_gradient_hessian_evaluations": evaluations,
                "backtracking_steps": backtracks, "objective": objective,
                "gradient_infinity_norm": grad_inf, "beta_low": float(theta[0]),
                "beta_high": float(theta[1]), "penalty": PENALTY,
                "market_logit_coefficient_fixed": 1.0, "intercept": False,
                "retry_count": 0}
        if iteration == MAX_ITERATIONS:
            break
        direction = np.linalg.solve(hessian, gradient)
        directional = float(gradient @ direction)
        if not math.isfinite(directional) or directional <= 0:
            raise RuntimeError("damped Newton direction is not a descent direction")
        step = 1.0
        for _ in range(60):
            proposal = theta - step * direction
            proposal_objective = objective_gradient_hessian(proposal, design, labels, offsets)[0]
            evaluations += 1
            if proposal_objective <= objective - 1e-4 * step * directional:
                theta = proposal
                break
            step *= 0.5; backtracks += 1
        else:
            raise RuntimeError("damped Newton line search failed; no retry authorized")
    raise RuntimeError(f"stratified optimizer failed frozen convergence: iterations=50, grad_inf={grad_inf}")


def candidate_probabilities(parameters: object, features: object,
                            market_logits: object) -> list[float]:
    theta = np.asarray(parameters, dtype=np.float64)
    design = np.asarray(features, dtype=np.float64)
    offsets = np.asarray(market_logits, dtype=np.float64)
    if theta.shape != (2,) or design.ndim != 2 or design.shape[1] != 2 or offsets.shape != (design.shape[0],):
        raise ValueError("candidate prediction inputs are misaligned")
    result = expit(offsets + design @ theta)
    return [validate_probability(float(value), DEFAULT_PROBABILITY_POLICY, ARM_CANDIDATE) for value in result]


def _fit_and_predict(rows: Sequence[base.InGameRow], folds: Sequence[dict],
                     indicators: Mapping[str, dict], controls: Mapping[tuple[str, str, int], dict]
                     ) -> tuple[list[dict], list[dict]]:
    if set(indicators) != {row.game_id for row in rows}:
        raise ValueError("prior-play feature must cover all 193 materialized rows")
    by_date: dict[str, list[base.InGameRow]] = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    predictions, reports = [], []
    fit_count = 0
    for fold in folds:
        check_rows = sorted([row for value in fold["check_dates"] for row in by_date.get(value, [])], key=lambda row: row.key)
        fit_rows, unavailable = nested._strict_prior_rows(by_date, fold["fit_dates"], check_rows)
        fit_p = np.asarray([row.trusted["market_probability"] for row in fit_rows])
        check_p = np.asarray([row.trusted["market_probability"] for row in check_rows])
        fit_x = stratified_features([indicators[row.game_id]["signal"] for row in fit_rows], fit_p)
        check_x = stratified_features([indicators[row.game_id]["signal"] for row in check_rows], check_p)
        parameters, optimizer = fit_stratified_offset(
            fit_x, [row.trusted["outcome"] for row in fit_rows],
            [row.market_features[0] for row in fit_rows],
        )
        fit_count += 1
        candidate = candidate_probabilities(parameters, check_x, [row.market_features[0] for row in check_rows])
        arm_values = {arm: [] for arm in ALL_ARMS}
        for row, value in zip(check_rows, candidate, strict=True):
            frozen = controls.get(row.key)
            raw = validate_probability(float(row.trusted["market_probability"]), DEFAULT_PROBABILITY_POLICY, ARM_RAW)
            if (frozen is None or frozen["fold"] != fold["fold"] or frozen["game_id"] != row.game_id
                    or frozen["game_date"] != row.game_date or frozen["game_week"] != row.game_week
                    or frozen["outcome"] != row.trusted["outcome"] or frozen[identity.ARM_RAW] != raw):
                raise ValueError("candidate row differs from frozen v0 identity/label/raw")
            item = {"fold": fold["fold"], "row": row, "signal": indicators[row.game_id]["signal"],
                    ARM_RAW: raw, ARM_ORDINARY: frozen[identity.ARM_ORDINARY],
                    ARM_PARENT: frozen[identity.ARM_PARENT], ARM_CANDIDATE: value}
            predictions.append(item)
            for arm in ALL_ARMS:
                arm_values[arm].append(item[arm])
        outcomes = [row.trusted["outcome"] for row in check_rows]
        reports.append({"fold": fold["fold"], "fit_dates": list(fold["fit_dates"]),
            "check_dates": list(fold["check_dates"]), "fit_events": len(fit_rows),
            "check_events": len(check_rows), "fit_label_unavailable_game_ids": unavailable,
            "fit_low_events": int(np.sum(fit_p * (1.0 - fit_p) < UNCERTAINTY_THRESHOLD)),
            "fit_high_events": int(np.sum(fit_p * (1.0 - fit_p) >= UNCERTAINTY_THRESHOLD)),
            "optimizer": optimizer,
            "arms": {arm: settlement._simple_metrics(outcomes, arm_values[arm]) for arm in ALL_ARMS},
            "same_rows_labels_and_checkpoints": True})
    keys = [item["row"].key for item in predictions]
    if fit_count != MODEL_FITS or len(keys) != len(set(keys)) or set(keys) != set(controls):
        raise ValueError("exact four fits or exact frozen common mask changed")
    return predictions, reports


def _aggregate(predictions: Sequence[dict]) -> dict:
    outcomes = [item["row"].trusted["outcome"] for item in predictions]
    result = {}
    for arm in ALL_ARMS:
        values = [item[arm] for item in predictions]
        result[arm] = settlement._simple_metrics(outcomes, values)
        result[arm]["reliability_table"] = base._reliability_table(outcomes, values)
    return result


def _paired_evidence(predictions: Sequence[dict]) -> dict:
    records = []
    for item in predictions:
        row = item["row"]
        record = {"game_id": row.game_id, "game_date": row.game_date, "game_week": row.game_week}
        for comparator in (ARM_RAW, ARM_ORDINARY, ARM_PARENT):
            for metric in ("brier", "log_loss"):
                record[f"candidate_minus_{comparator}_{metric}"] = (
                    identity._loss(row.trusted["outcome"], item[ARM_CANDIDATE], metric)
                    - identity._loss(row.trusted["outcome"], item[comparator], metric))
        records.append(record)
    evidence = {}
    for comparator in (ARM_RAW, ARM_ORDINARY, ARM_PARENT):
        comparison = f"candidate_minus_{comparator}"
        evidence[comparison] = {}
        for metric in ("brier", "log_loss"):
            key = f"{comparison}_{metric}"
            evidence[comparison][metric] = {"delta_convention": f"{comparison}; negative loss is better",
                "equal_event_mean": math.fsum(row[key] for row in records) / len(records),
                "by_schedule_date": base._group_means(records, "game_date", key),
                "schedule_date_interval": base._group_bootstrap(records, "game_date", key, seed=BOOTSTRAP_SEED, replicates=BOOTSTRAP_REPLICATES),
                "observed_game_week_interval": base._group_bootstrap(records, "game_week", key, seed=BOOTSTRAP_SEED, replicates=BOOTSTRAP_REPLICATES)}
    return evidence


def decision(aggregate: Mapping[str, dict], folds: Sequence[dict], paired: Mapping[str, dict]
             ) -> tuple[str, str, dict]:
    candidate = aggregate[ARM_CANDIDATE]
    raw_wins = [fold["arms"][ARM_CANDIDATE]["brier"] < fold["arms"][ARM_RAW]["brier"] for fold in folds]
    ordinary_wins = [fold["arms"][ARM_CANDIDATE]["brier"] < fold["arms"][ARM_ORDINARY]["brier"] for fold in folds]
    conditions = {
        "candidate_brier_below_all_three": all(candidate["brier"] < aggregate[arm]["brier"] for arm in (ARM_RAW, ARM_ORDINARY, ARM_PARENT)),
        "candidate_log_loss_below_all_three": all(candidate["log_loss"] < aggregate[arm]["log_loss"] for arm in (ARM_RAW, ARM_ORDINARY, ARM_PARENT)),
        "raw_brier_fold_wins_at_least_3_of_4": sum(raw_wins) >= 3,
        "ordinary_brier_fold_wins_at_least_3_of_4": sum(ordinary_wins) >= 3,
        "date_brier_upper_below_zero": paired[f"candidate_minus_{ARM_RAW}"]["brier"]["schedule_date_interval"]["interval_95"][1] < 0,
        "week_brier_upper_below_zero": paired[f"candidate_minus_{ARM_RAW}"]["brier"]["observed_game_week_interval"]["interval_95"][1] < 0,
        "raw_brier_fold_wins_at_most_1_of_4": sum(raw_wins) <= 1,
        "raw_brier_fold_wins": raw_wins, "ordinary_brier_fold_wins": ordinary_wins,
    }
    support = all(conditions[key] for key in (
        "candidate_brier_below_all_three", "candidate_log_loss_below_all_three",
        "raw_brier_fold_wins_at_least_3_of_4", "ordinary_brier_fold_wins_at_least_3_of_4",
        "date_brier_upper_below_zero", "week_brier_upper_below_zero"))
    refute = (candidate["brier"] >= aggregate[ARM_RAW]["brier"]
              or candidate["log_loss"] >= aggregate[ARM_RAW]["log_loss"]
              or conditions["raw_brier_fold_wins_at_most_1_of_4"])
    scientific = "SUPPORTED" if support else "REFUTED" if refute else "INCONCLUSIVE"
    return scientific, "KEEP" if support else "REVERT", conditions


def _write_predictions(path: Path, predictions: Sequence[dict]) -> None:
    fields = ("fold", "game_id", "game_date", "game_week", "event_id", "market_id",
        "cutoff_ms", "outcome_available_ms", "outcome", "raw_market_probability",
        "frozen_v0_ordinary_market_only_probability", "frozen_v0_market_plus_state_parent_probability",
        "prior_play_success_signal", "uncertainty_stratified_offset_probability")
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for item in predictions:
            row = item["row"]
            writer.writerow({"fold": item["fold"], "game_id": row.game_id, "game_date": row.game_date,
                "game_week": row.game_week, "event_id": row.trusted["event_id"], "market_id": row.trusted["market_id"],
                "cutoff_ms": row.trusted["cutoff_ms"], "outcome_available_ms": row.trusted["outcome_available_ms"],
                "outcome": row.trusted["outcome"], "raw_market_probability": item[ARM_RAW],
                "frozen_v0_ordinary_market_only_probability": item[ARM_ORDINARY],
                "frozen_v0_market_plus_state_parent_probability": item[ARM_PARENT],
                "prior_play_success_signal": item["signal"],
                "uncertainty_stratified_offset_probability": item[ARM_CANDIDATE]})
        stream.flush(); os.fsync(stream.fileno())
    temporary.replace(path)


def run(source_root: Path, output: Path, *, allow_test_paths: bool = False,
        generated_utc: str | None = None) -> dict:
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    output.mkdir(parents=True, exist_ok=False)
    try:
        _require_dependencies()
        frozen = prior._validate_v0_artifact(V0_ARTIFACT_ROOT)
        feature_artifact = uncertainty._validate_parent_artifact(FEATURE_ARTIFACT_ROOT)
        if (feature_artifact["hashes"]["prior_play_success.csv"] != FEATURE_SHA256
                or feature_artifact["hashes"]["manifest.json"] != FEATURE_MANIFEST_SHA256):
            raise ValueError("frozen 193-row feature artifact changed")
        indicators = prior._load_indicators(FEATURE_ARTIFACT_ROOT / "prior_play_success.csv", frozen)
        controls = identity._frozen_controls(frozen)
        cohort = base._validate_source(source_root, expected_events=EXPECTED_EVENTS, expected_dates=EXPECTED_DATES, allow_test_paths=allow_test_paths)
        states = {row["game_id"]: row for row in frozen["anchors"]}
        rows, exclusions = [], []
        for ordinal, item in enumerate(cohort):
            try: rows.append(base._load_dynamic_market(source_root, item, states[item["game_id"]]))
            except settlement.EventExclusion as error:
                exclusions.append({"source_ordinal": ordinal, "game_id": item["game_id"], "game_date": item["game_date"], "reason": error.code, "detail": str(error)[:400]})
        rows.sort(key=lambda row: row.key)
        if (len(rows) != EXPECTED_MATERIALIZED_EVENTS
                or tuple((item["game_id"], item["reason"]) for item in exclusions) != EXPECTED_EXCLUSIONS):
            raise ValueError("exact frozen 195 -> 193 + 2 attrition changed")
        lock = {"schema": "nfl_ingame_prior_play_success_uncertainty_stratified_offset_pre_score_lock_v4",
            "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(), "task_id": TASK_ID,
            "question_id": QUESTION_ID, "question_digest_sha256": QUESTION_DIGEST,
            "hypothesis_digest_sha256": HYPOTHESIS_DIGEST, "predeclared_rule_sha256": RULE_DIGEST,
            "component_spec_sha256": COMPONENT_SPEC_DIGEST, "implementation_component_spec_sha256": IMPLEMENTATION_COMPONENT_SPEC_SHA256,
            "component_spec": COMPONENT_SPEC, "controller_log_sha256": CONTROLLER_LOG_SHA256,
            "selection_record_sha256": SELECTION_RECORD_DIGEST, "recovery_state_hint_sha256": RECOVERY_STATE_HINT_SHA256,
            "scheduler_branch_binding": SCHEDULER_BRANCH_BINDING, "scheduler_branch_binding_sha256": SCHEDULER_BRANCH_BINDING_SHA256,
            "feature_sha256": FEATURE_SHA256, "folds": frozen["folds"], "fit_budget": MODEL_FITS,
            "thread_environment_contract": THREAD_ENV_CONTRACT, "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "resource_cap": {"processes": 1, "threads": 1, "fits": 4, "wall_seconds": 900,
                "rss_mib": 768, "network_bytes": 0, "provider_calls": 0, "provider_cost_usd": "0", "retries": 0},
            "route_dev_opened": False, "sealed_final_opened": False, "external_fetch": False,
            "paid_provider": False, "provider_cost_usd": "0", "promotion_authorized": False}
        base._atomic_json(output / "pre_score_lock.json", lock)
        base._atomic_json(output / "input_receipts.json", {"schema": "nfl_ingame_prior_play_success_uncertainty_stratified_offset_inputs_v4",
            "task_id": TASK_ID, "runner_sha256": _sha256(Path(__file__)), "controller_log_sha256": CONTROLLER_LOG_SHA256,
            "v0_artifact_hashes": frozen["hashes"], "feature_artifact_hashes": feature_artifact["hashes"],
            "materialized_receipts": [row.source_receipt for row in rows],
            "route_dev_opened": False, "sealed_final_opened": False, "external_fetch": False,
            "paid_provider": False, "provider_cost_usd": "0"})
        base._atomic_json(output / "exclusions.json", {"schema": "nfl_ingame_prior_play_success_uncertainty_stratified_offset_exclusions_v4",
            "source_events": EXPECTED_EVENTS, "materialized_events": len(rows), "excluded_events": len(exclusions),
            "reconciles_to_source_denominator": len(rows) + len(exclusions) == EXPECTED_EVENTS, "exclusions": exclusions})
        predictions, reports = _fit_and_predict(rows, frozen["folds"], indicators, controls)
        check_hash = _digest([list(item["row"].key) for item in predictions])
        if (len(predictions) != EXPECTED_CHECK_EVENTS or check_hash != EXPECTED_CHECK_KEY_SHA256
                or tuple(item["fit_events"] for item in reports) != EXPECTED_FIT_EVENTS
                or tuple(item["check_events"] for item in reports) != EXPECTED_CHECK_EVENTS_BY_FOLD
                or any(item["fit_label_unavailable_game_ids"] for item in reports)):
            raise ValueError("frozen chronology, fit counts, or exact 87-row mask changed")
        aggregate = _aggregate(predictions); paired = _paired_evidence(predictions)
        scientific, operational, conditions = decision(aggregate, reports, paired)
        scorecard = {"schema": "nfl_ingame_prior_play_success_uncertainty_stratified_offset_scorecard_v4",
            "task_id": TASK_ID, "scientific_decision": scientific, "operational_decision": operational,
            "decision_conditions": conditions, "model_fits": MODEL_FITS, "control_refits": 0,
            "source_denominator": {"events": EXPECTED_EVENTS, "dates": EXPECTED_DATES,
                "materialized_events": len(rows), "excluded_events": len(exclusions), "check_events": len(predictions),
                "check_dates": len({item["row"].game_date for item in predictions}),
                "check_game_weeks": len({item["row"].game_week for item in predictions})},
            "identical_masks": {"all_four_arms_same_rows_labels_and_checkpoints": True,
                "check_key_sha256": check_hash, "matches_frozen_v0": True},
            "aggregate": aggregate, "folds": reports, "paired_grouped_evidence": paired,
            "inference_boundary": "repeatedly inspected opened-Train Discovery only",
            "incumbent_changed": operational == "KEEP", "route_dev_opened": False,
            "sealed_final_opened": False, "external_fetch": False, "paid_provider": False,
            "provider_cost_usd": "0", "promotion_authorized": False}
        _write_predictions(output / "predictions.csv", predictions); base._atomic_json(output / "scorecard.json", scorecard)
        manifest = {"schema": "nfl_ingame_prior_play_success_uncertainty_stratified_offset_manifest_v4", "complete": True,
            "completed_utc": generated_utc or datetime.now(timezone.utc).isoformat(), "task_id": TASK_ID,
            "pre_score_lock_sha256": _sha256(output / "pre_score_lock.json"), "input_receipts_sha256": _sha256(output / "input_receipts.json"),
            "exclusions_sha256": _sha256(output / "exclusions.json"), "predictions_sha256": _sha256(output / "predictions.csv"),
            "scorecard_sha256": _sha256(output / "scorecard.json"), "source_events": EXPECTED_EVENTS,
            "materialized_events": len(rows), "excluded_events": len(exclusions), "check_events": len(predictions),
            "model_fits": MODEL_FITS, "control_refits": 0, "scientific_decision": scientific,
            "operational_decision": operational, "route_dev_opened": False, "sealed_final_opened": False,
            "external_fetch": False, "paid_provider": False, "provider_cost_usd": "0", "promotion_authorized": False}
        base._atomic_json(output / "manifest.json", manifest); return manifest
    except Exception as error:
        if output.exists() and not (output / "manifest.json").exists():
            base._atomic_json(output / "failure.json", {"schema": "nfl_ingame_prior_play_success_uncertainty_stratified_offset_failure_v4",
                "error_type": type(error).__name__, "error": str(error)[:1200], "model_fits_maximum": MODEL_FITS,
                "route_dev_opened": False, "sealed_final_opened": False, "external_fetch": False,
                "paid_provider": False, "provider_cost_usd": "0", "promotion_authorized": False})
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); print(json.dumps(run(args.source_root, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
