#!/usr/bin/env python3
"""Feedback-selected Brier-trained freshness descendant; opened Train only."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import math
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

from experiments import nfl_ingame_market_freshness_interaction_offset as common


TASK_ID = "InGameMarketFreshnessBrierOffset-v2"
ARM_CANDIDATE = "market_freshness_brier_offset"
ARM_RESEARCH_PARENT = "frozen_a1_freshness_parent"
ARM_RAW, ARM_ORDINARY, ARM_PARENT = common.ARM_RAW, common.ARM_ORDINARY, common.ARM_PARENT
SOURCE_ROOT, V0_ARTIFACT_ROOT = common.SOURCE_ROOT, common.V0_ARTIFACT_ROOT
MODEL_FITS, PENALTY = 4, 16.0
CONTRACT = Path(__file__).parents[1] / "supervisor_harness" / "COEVO_GENERATION2_CONTRACT_2026-10-03.json"
CONTRACT_SHA256 = "a177b01df267879275b337e73a86ee87c5a7c2e45da6312976ec2732d6f90fa2"
PARENT_SOURCE_SHA256 = "d7e16a2d745f6440fe84b97aba54950b2c78a23428172b6002b187b385f057cd"
OPTIMIZER_OPTIONS = {"maxiter": 500, "gtol": 1e-8, "ftol": 1e-12}


def require_dependencies() -> dict:
    common.require_dependencies(common.TASK_ID)
    for path, expected in ((CONTRACT, CONTRACT_SHA256), (Path(common.__file__), PARENT_SOURCE_SHA256)):
        if not path.is_file() or path.is_symlink() or common._sha256(path) != expected:
            raise ValueError(f"frozen C3 dependency missing, symlinked or hash-changed: {path.name}")
    contract = common.settlement._strict_json(CONTRACT)
    if contract["candidate_id"] != TASK_ID or contract["recipe"]["penalty"] != PENALTY:
        raise ValueError("frozen C3 candidate recipe identity changed")
    return contract


def brier_objective_gradient(parameters: object, features: object, outcomes: object,
                             market_logits: object) -> tuple[float, np.ndarray]:
    theta = np.asarray(parameters, dtype=np.float64)
    x, y, offsets = (common._vector(value, name) for value, name in (
        (features, "Brier feature"), (outcomes, "binary outcome"), (market_logits, "market logit")))
    if (theta.shape != (1,) or not np.isfinite(theta).all() or x.shape != y.shape
            or offsets.shape != y.shape or np.any((y != 0) & (y != 1))):
        raise ValueError("Brier objective inputs are invalid or misaligned")
    eta = offsets + theta[0] * x
    q = expit(eta)
    objective = float(np.sum((q - y) ** 2) + .5 * PENALTY * theta[0] ** 2)
    gradient = np.asarray([2 * np.sum(x * (q - y) * q * (1 - q)) + PENALTY * theta[0]])
    if not np.isfinite(eta).all() or not math.isfinite(objective) or not np.isfinite(gradient).all():
        raise FloatingPointError("Brier objective became nonfinite")
    return objective, gradient


def fit_brier_offset(features: object, outcomes: object, market_logits: object) -> tuple[float, dict]:
    # Validate before dispatch, and preserve the frozen single-start/no-retry recipe.
    brier_objective_gradient([0.0], features, outcomes, market_logits)
    result = minimize(brier_objective_gradient, np.zeros(1), args=(features, outcomes, market_logits),
        method="L-BFGS-B", jac=True, options=dict(OPTIMIZER_OPTIONS))
    objective, gradient = brier_objective_gradient(result.x, features, outcomes, market_logits)
    gradient_norm = float(np.max(np.abs(gradient)))
    q = expit(np.asarray(market_logits) + float(result.x[0]) * np.asarray(features))
    if (not bool(result.success) or not math.isfinite(float(result.fun))
            or not np.isfinite(q).all() or gradient_norm > OPTIMIZER_OPTIONS["gtol"]):
        raise RuntimeError(f"frozen Brier optimizer convergence failed; success={result.success}, "
            f"gradient={gradient_norm}; no retry authorized")
    return float(result.x[0]), {"converged": True, "optimizer": "scipy.optimize.minimize L-BFGS-B",
        "objective_definition": "sum Brier + 0.5*16*beta^2", "objective": objective,
        "gradient_infinity_norm": gradient_norm, "absolute_analytic_gradient": gradient_norm,
        "beta": float(result.x[0]), "iterations": int(result.nit), "function_evaluations": int(result.nfev),
        "optimizer_message": str(result.message), "options": dict(OPTIMIZER_OPTIONS),
        "initial_beta": 0.0, "penalty": PENALTY, "intercept": False,
        "market_logit_coefficient_fixed": 1.0, "retry_count": 0, "global_optimum_claim": False}


def load_parent_predictions(contract: dict, controls: dict, frozen: dict) -> dict:
    evidence = contract["research_parent"]
    path = Path(evidence["predictions_path"])
    expected = {"manifest.json": evidence["manifest_sha256"],
        "scorecard.json": evidence["scorecard_sha256"], "predictions.csv": evidence["predictions_sha256"]}
    if path.name != "predictions.csv" or path.parent.is_symlink():
        raise ValueError("frozen A1 parent prediction location is invalid")
    for name, digest in expected.items():
        item = path.parent / name
        if not item.is_file() or item.is_symlink() or common._sha256(item) != digest:
            raise ValueError(f"frozen A1 parent artifact hash changed: {name}")
    manifest = common.settlement._strict_json(path.parent / "manifest.json")
    if (manifest.get("complete") is not True or manifest.get("task_id") != common.TASK_ID
            or manifest.get("model_fits") != 4 or manifest.get("check_events") != 87
            or manifest.get("predictions_sha256") != expected["predictions.csv"]
            or manifest.get("scorecard_sha256") != expected["scorecard.json"]):
        raise ValueError("frozen A1 parent manifest identity changed")
    availability = {common.identity._control_key(item): int(item["outcome_available_ms"])
        for item in frozen["predictions"]}
    result, ordered = {}, []
    for item in common.frozen_v0._read_csv(path):
        key = common.identity._control_key(item)
        control = controls.get(key)
        if (control is None or key in result or int(item["fold"]) != control["fold"]
                or item["game_id"] != control["game_id"] or item["game_date"] != control["game_date"]
                or item["game_week"] != control["game_week"] or int(item["outcome"]) != control["outcome"]
                or int(item["outcome_available_ms"]) != availability[key]):
            raise ValueError("frozen A1 parent mask, fold, identity or label changed")
        for arm, column in ((ARM_RAW, "raw_market_probability"),
                (ARM_ORDINARY, "frozen_v0_ordinary_market_only_probability"),
                (ARM_PARENT, "frozen_v0_market_plus_state_parent_probability")):
            if float(item[column]) != control[arm]:
                raise ValueError("frozen A1 parent comparator probability changed")
        probability = common.probability_contract.validate_probability(float(item["candidate_probability"]),
            common.probability_contract.DEFAULT_PROBABILITY_POLICY, ARM_RESEARCH_PARENT)
        feature = float(item["candidate_feature"])
        if not math.isfinite(feature):
            raise ValueError("frozen A1 parent feature is nonfinite")
        result[key] = {"probability": probability, "feature": feature}
        ordered.append(list(key))
    if (len(result) != 87 or set(result) != set(controls)
            or common._digest(ordered) != common.frozen_v0.EXPECTED_CHECK_KEY_SHA256):
        raise ValueError("frozen A1 parent exact87 common mask changed")
    return result


def aggregate(predictions: list) -> dict:
    result = common._aggregate(predictions, ARM_CANDIDATE)
    outcomes = [item["row"].trusted["outcome"] for item in predictions]
    parent = [item[ARM_RESEARCH_PARENT] for item in predictions]
    result[ARM_RESEARCH_PARENT] = common.settlement._simple_metrics(outcomes, parent)
    result[ARM_RESEARCH_PARENT]["reliability_table"] = common.base._reliability_table(outcomes, parent)
    return result


def paired_evidence(predictions: list) -> dict:
    result = common._paired_evidence(predictions, ARM_CANDIDATE)
    records = []
    for item in predictions:
        row = item["row"]
        record = {"game_date": row.game_date, "game_week": row.game_week}
        for metric in ("brier", "log_loss"):
            record[metric] = (common.identity._loss(row.trusted["outcome"], item[ARM_CANDIDATE], metric)
                - common.identity._loss(row.trusted["outcome"], item[ARM_RESEARCH_PARENT], metric))
        records.append(record)
    result[f"candidate_minus_{ARM_RESEARCH_PARENT}"] = {metric: {
        "delta_convention": "candidate minus actual A1 parent; negative loss is better",
        "equal_event_mean": math.fsum(row[metric] for row in records) / len(records),
        "by_schedule_date": common.base._group_means(records, "game_date", metric),
        "schedule_date_interval": common.base._group_bootstrap(records, "game_date", metric, seed=20260929, replicates=10000),
        "observed_game_week_interval": common.base._group_bootstrap(records, "game_week", metric, seed=20260929, replicates=10000)
    } for metric in ("brier", "log_loss")}
    return result


def fit_and_predict(rows: list, folds: list, controls: dict, parent: dict) -> tuple[list, list]:
    by_date = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    predictions, reports = [], []
    for fold in folds:
        check = sorted([row for day in fold["check_dates"] for row in by_date.get(day, [])], key=lambda row: row.key)
        fit, unavailable = common.nested._strict_prior_rows(by_date, fold["fit_dates"], check)
        fit_x, check_x, transform = common.freshness_features(fit, check, states={})
        if any(parent.get(row.key, {}).get("feature") != float(feature)
               for row, feature in zip(check, check_x, strict=True)):
            raise ValueError("candidate differs from actual A1 parent feature before fit")
        beta, optimizer = fit_brier_offset(fit_x, [row.trusted["outcome"] for row in fit],
            [row.market_features[0] for row in fit])
        values = common.candidate_probabilities(beta, check_x, [row.market_features[0] for row in check],
            raw_probabilities=[row.trusted["market_probability"] for row in check])
        block = []
        for row, probability, feature in zip(check, values, check_x, strict=True):
            frozen, actual_parent = controls.get(row.key), parent.get(row.key)
            raw = row.trusted["market_probability"]
            if (frozen is None or actual_parent is None or frozen["fold"] != fold["fold"]
                    or frozen["game_id"] != row.game_id or frozen["game_date"] != row.game_date
                    or frozen["game_week"] != row.game_week or frozen["outcome"] != row.trusted["outcome"]
                    or frozen[ARM_RAW] != raw or actual_parent["feature"] != float(feature)):
                raise ValueError("candidate differs from frozen v0 or actual A1 parent feature/identity/label")
            block.append({"fold": fold["fold"], "row": row, "feature": float(feature), ARM_RAW: raw,
                ARM_ORDINARY: frozen[ARM_ORDINARY], ARM_PARENT: frozen[ARM_PARENT],
                ARM_RESEARCH_PARENT: actual_parent["probability"], ARM_CANDIDATE: probability})
        metrics = aggregate(block)
        reports.append({"fold": fold["fold"], "fit_dates": list(fold["fit_dates"]),
            "check_dates": list(fold["check_dates"]), "fit_events": len(fit), "check_events": len(check),
            "fit_label_unavailable_game_ids": unavailable, "feature_transform": transform,
            "optimizer": optimizer, "arms": metrics, "same_rows_labels_and_checkpoints": True,
            "candidate_minus_actual_a1_parent": {metric: metrics[ARM_CANDIDATE][metric]
                - metrics[ARM_RESEARCH_PARENT][metric] for metric in ("brier", "log_loss")}})
        predictions.extend(block)
    keys = [item["row"].key for item in predictions]
    if len(reports) != 4 or len(keys) != len(set(keys)) or set(keys) != set(controls) or set(keys) != set(parent):
        raise ValueError("four fits or frozen actual-parent common mask changed")
    return predictions, reports


def write_predictions(path: Path, predictions: list) -> None:
    # Reuse the unchanged writer and append the frozen parent column in a new file only.
    common._write_predictions(path, predictions, ARM_CANDIDATE)
    import csv
    import os
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fields, items = list(reader.fieldnames or ()), list(reader)
    temporary = path.with_suffix(".csv.parent.tmp")
    with temporary.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[*fields, "frozen_a1_parent_probability"])
        writer.writeheader()
        for item, prediction in zip(items, predictions, strict=True):
            writer.writerow({**item, "frozen_a1_parent_probability": prediction[ARM_RESEARCH_PARENT]})
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def run(source_root: Path, output: Path, *, allow_test_paths: bool = False) -> dict:
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    common.base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    output.mkdir(parents=True, exist_ok=False)
    try:
        contract = require_dependencies()
        frozen = common.frozen_v0._validate_v0_artifact(V0_ARTIFACT_ROOT)
        controls = common.identity._frozen_controls(frozen)
        parent = load_parent_predictions(contract, controls, frozen)
        cohort = common.base._validate_source(source_root, expected_events=195, expected_dates=42, allow_test_paths=allow_test_paths)
        pbp = common.base._validate_pbp_receipts(source_root, cohort)
        if pbp != frozen["receipts"]["pbp_receipts"]:
            raise ValueError("opened-Train PBP source receipts differ from frozen v0")
        states = {row["game_id"]: row for row in frozen["anchors"]}
        rows, exclusions = [], []
        for ordinal, item in enumerate(cohort):
            try:
                rows.append(common.base._load_dynamic_market(source_root, item, states[item["game_id"]]))
            except common.settlement.EventExclusion as error:
                exclusions.append({"source_ordinal": ordinal, "game_id": item["game_id"],
                    "game_date": item["game_date"], "reason": error.code, "detail": str(error)[:400]})
        rows.sort(key=lambda row: row.key)
        receipts = [row.source_receipt for row in rows]
        if (len(rows) != 193 or len(rows) + len(exclusions) != 195
                or [(item["game_id"], item["reason"]) for item in exclusions] != common.identity.EXPECTED_EXCLUSIONS
                or common._digest(receipts) != common._digest(frozen["receipts"]["materialized_receipts"])):
            raise ValueError("frozen195 denominator, exact exclusions or causal receipts changed")
        common.freshness_features(rows, rows, states={})
        inputs = {"task_id": TASK_ID, "controller_contract_sha256": CONTRACT_SHA256,
            "v0_artifact_hashes": frozen["hashes"], "materialized_receipts": receipts,
            "runner_sha256": common._sha256(Path(__file__)), "parent_source_sha256": PARENT_SOURCE_SHA256,
            "parent_artifacts": contract["research_parent"], "pbp_receipts": pbp,
            "dependency_source_hashes": {module.__name__: digest for module, digest in common.DEPENDENCIES.items()},
            "source_manifest_sha256": common._sha256(source_root / "manifest.json"),
            "cohort_sha256": common._sha256(source_root / "cohort.csv"), **common.BOUNDARY_FLAGS}
        common.base._atomic_json(output / "input_receipts.json", inputs)
        common.base._atomic_json(output / "pre_score_lock.json", {"task_id": TASK_ID,
            "generated_utc": datetime.now(timezone.utc).isoformat(), "controller_contract_sha256": CONTRACT_SHA256,
            "scientific_recipe": contract, "folds": frozen["folds"], "fit_budget": 4, "automatic_retries": 0,
            "thread_environment_contract": common.identity.THREAD_ENV_CONTRACT, **common.BOUNDARY_FLAGS})
        common.base._atomic_json(output / "exclusions.json", {"source_events": 195, "materialized_events": 193,
            "excluded_events": 2, "reconciles_to_source_denominator": True, "exclusions": exclusions})
        predictions, reports = fit_and_predict(rows, frozen["folds"], controls, parent)
        check_hash = common._digest([list(item["row"].key) for item in predictions])
        if (len(predictions) != 87 or check_hash != common.frozen_v0.EXPECTED_CHECK_KEY_SHA256
                or tuple(item["fit_events"] for item in reports) != (106, 132, 148, 176)
                or tuple(item["check_events"] for item in reports) != (26, 16, 28, 17)
                or any(item["fit_label_unavailable_game_ids"] for item in reports)):
            raise ValueError("frozen chronology, fit counts or exact87 mask changed")
        metrics, paired = aggregate(predictions), paired_evidence(predictions)
        scientific, operational, conditions = common.decision(metrics, reports, paired, ARM_CANDIDATE)
        scorecard = {"schema": "coevo_frozen_candidate_scorecard_v1", "task_id": TASK_ID,
            "candidate_arm": ARM_CANDIDATE, "actual_research_parent_arm": ARM_RESEARCH_PARENT,
            "scientific_decision": scientific, "operational_decision": operational,
            "decision_conditions": conditions, "model_fits": 4, "control_refits": 0,
            "source_denominator": {"events": 195, "dates": 42, "materialized_events": 193,
                "excluded_events": 2, "check_events": 87,
                "check_dates": len({item["row"].game_date for item in predictions}),
                "check_game_weeks": len({item["row"].game_week for item in predictions})},
            "identical_masks": {"all_four_arms_same_rows_labels_and_checkpoints": True,
                "actual_a1_parent_same_rows": True, "check_key_sha256": check_hash, "matches_frozen_v0": True},
            "aggregate": metrics, "folds": reports, "paired_grouped_evidence": paired,
            "research_parent_sha256": PARENT_SOURCE_SHA256,
            "comparison_incumbent_sha256": contract["comparison_incumbent_sha256"],
            "inference_boundary": "repeatedly inspected Train Discovery; no global optimum, realtime or mechanism claim",
            **common.BOUNDARY_FLAGS}
        write_predictions(output / "predictions.csv", predictions)
        common.base._atomic_json(output / "scorecard.json", scorecard)
        manifest = {"schema": "coevo_frozen_candidate_manifest_v1", "complete": True, "task_id": TASK_ID,
            "completed_utc": datetime.now(timezone.utc).isoformat(), "source_events": 195,
            "materialized_events": 193, "excluded_events": 2, "check_events": 87,
            "model_fits": 4, "control_refits": 0, "automatic_retries": 0,
            "scientific_decision": scientific, "operational_decision": operational,
            **{f"{name}_sha256": common._sha256(output / f"{name}.{suffix}") for name, suffix in (
                ("pre_score_lock", "json"), ("input_receipts", "json"), ("exclusions", "json"),
                ("predictions", "csv"), ("scorecard", "json"))}, **common.BOUNDARY_FLAGS}
        common.base._atomic_json(output / "manifest.json", manifest)
        return manifest
    except Exception as error:
        common.base._atomic_json(output / "failure.json", {"task_id": TASK_ID,
            "error_type": type(error).__name__, "error": str(error)[:1200],
            "model_fits_maximum": 4, "automatic_retries": 0, **common.BOUNDARY_FLAGS})
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(common.settlement.json.dumps(run(args.source_root, args.output), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
