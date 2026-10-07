#!/usr/bin/env python3
"""Frozen nonlinear market residual HGB; historical Train Discovery only."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import math
import os
from pathlib import Path

import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor

from experiments import nfl_ingame_market_freshness_interaction_offset as common


TASK_ID = "InGameMarketResidualHGB-v1"
ARM_CANDIDATE = "market_residual_hgb"
ARM_RESEARCH_PARENT = "frozen_actual_research_parent"
ARM_RAW, ARM_ORDINARY, ARM_PARENT = common.ARM_RAW, common.ARM_ORDINARY, common.ARM_PARENT
SOURCE_ROOT, V0_ARTIFACT_ROOT = common.SOURCE_ROOT, common.V0_ARTIFACT_ROOT
MODEL_FITS = 4
CONTRACT = Path(__file__).parents[1] / "supervisor_harness" / "COEVO_NEXT_BATCH_CONTRACTS_2026-10-03.json"
CONTRACT_SHA256 = "b6942eb906344b9acc97950f1c72c14024e981792744ed2bc83ca7944e6406b8"
COMMON_SOURCE_SHA256 = "d7e16a2d745f6440fe84b97aba54950b2c78a23428172b6002b187b385f057cd"
HGB_PARAMS = {"loss": "squared_error", "quantile": None, "learning_rate": .03, "max_iter": 64,
    "max_leaf_nodes": 4, "max_depth": 2, "min_samples_leaf": 20, "l2_regularization": 16.,
    "max_features": 1., "max_bins": 32, "categorical_features": None, "monotonic_cst": None,
    "interaction_cst": None, "warm_start": False, "early_stopping": False, "scoring": "loss",
    "validation_fraction": None, "n_iter_no_change": 10, "tol": 1e-7, "verbose": 0, "random_state": 23}


def require_dependencies(candidate_id: str) -> tuple[dict, dict]:
    common.require_dependencies(common.TASK_ID)
    for path, expected in ((CONTRACT, CONTRACT_SHA256), (Path(common.__file__), COMMON_SOURCE_SHA256)):
        if not path.is_file() or path.is_symlink() or common._sha256(path) != expected:
            raise ValueError(f"frozen HGB dependency missing, symlinked or hash-changed: {path.name}")
    contract = common.settlement._strict_json(CONTRACT)
    selected = [item for item in contract["candidates"] if item["candidate_id"] == candidate_id]
    if (len(selected) != 1 or contract["shared_prediction_recipe"]["params"] != HGB_PARAMS
            or sklearn.__version__ != "1.6.1"):
        raise ValueError("frozen HGB recipe, constructor or runtime identity changed")
    parent = selected[0]["research_parent"]
    parent_source = Path(__file__).with_name({common.TASK_ID: "nfl_ingame_market_freshness_interaction_offset.py",
        "InGameCausalPossessionPressureOffset-v1": "nfl_ingame_causal_possession_pressure_offset.py"}[parent["candidate_id"]])
    if parent_source.is_symlink() or common._sha256(parent_source) != parent["runner_sha256"]:
        raise ValueError("frozen actual-parent source changed")
    return contract, selected[0]


def feature_matrix(rows: list, *, include_state: bool) -> np.ndarray:
    values = []
    for row in rows:
        raw = row.trusted["market_probability"]
        common.identity._clipped_logits([raw])
        if row.market_features != (math.log(raw / (1 - raw)),):
            raise ValueError("market logit differs from exact frozen raw probability")
        market = [float(row.market_features[0]), common.causal_age(row.source_receipt)]
        if include_state:
            state = np.asarray(row.state_features, dtype=np.float64)
            if (state.shape != (9,) or not np.isfinite(state).all() or not -100 <= state[0] <= 100
                    or not 900 <= state[1] <= 1380 or state[2] not in (0, 1)
                    or np.any((state[3:7] != 0) & (state[3:7] != 1)) or np.sum(state[3:7]) != 1
                    or not 0 <= state[7] <= 100 or not -1 <= state[8] <= 1):
                raise ValueError("frozen causal state vector is incomplete or outside physical bounds")
            market.extend(state.tolist())
        values.append(market)
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.shape != (len(rows), 11 if include_state else 2) or not len(rows) or not np.isfinite(matrix).all():
        raise ValueError("HGB feature matrix must be complete and finite")
    return matrix


def bound_probabilities(raw: object, residual: object) -> tuple[list[float], dict]:
    raw, residual = common._vector(raw, "raw market probability"), common._vector(residual, "HGB residual")
    common.identity._clipped_logits(raw)
    if raw.shape != residual.shape:
        raise ValueError("HGB residual and raw probability are misaligned")
    unbounded = raw + residual
    if not np.isfinite(unbounded).all():
        raise FloatingPointError("HGB unbounded probabilities are nonfinite")
    epsilon = common.probability_contract.DEFAULT_PROBABILITY_POLICY.epsilon
    clipped = np.clip(unbounded, epsilon, 1 - epsilon)
    probabilities = [common.probability_contract.validate_probability(float(value),
        common.probability_contract.DEFAULT_PROBABILITY_POLICY, "residual HGB") for value in clipped]
    return probabilities, {"clipped_rows": int(np.count_nonzero(clipped != unbounded)),
        "lower_clipped_rows": int(np.count_nonzero(unbounded < epsilon)),
        "upper_clipped_rows": int(np.count_nonzero(unbounded > 1 - epsilon)),
        "epsilon": epsilon, "rows_removed": 0}


def fit_hgb_residual(fit: list, check: list, *, include_state: bool) -> tuple[list[float], dict]:
    fit_x, check_x = feature_matrix(fit, include_state=include_state), feature_matrix(check, include_state=include_state)
    outcomes = common._vector([row.trusted["outcome"] for row in fit], "fit outcomes")
    if np.any((outcomes != 0) & (outcomes != 1)):
        raise ValueError("fit outcomes are not binary")
    target = outcomes - np.asarray([row.trusted["market_probability"] for row in fit])
    model = HistGradientBoostingRegressor(**HGB_PARAMS)
    if model.get_params(deep=False) != HGB_PARAMS:
        raise ValueError("HGB constructor parameters differ from frozen contract")
    model.fit(fit_x, target)
    if model.n_iter_ != 64 or model.get_params(deep=False) != HGB_PARAMS:
        raise RuntimeError("HGB fit did not preserve exactly64 stages and frozen constructor")
    residual = model.predict(check_x)
    state = primitive_predictor_state(model, include_state=include_state)
    if not np.array_equal(predict_primitive(state, check_x), residual):
        raise RuntimeError("primitive numeric predictor replay differs from fitted HGB")
    probabilities, bounding = bound_probabilities([row.trusted["market_probability"] for row in check], residual)
    return probabilities, {"estimator": "sklearn.ensemble.HistGradientBoostingRegressor",
        "constructor_params": model.get_params(deep=False), "n_iter": int(model.n_iter_),
        "input_columns": fit_x.shape[1], "fit_target": "y-p_raw", "fit_events": len(fit),
        "check_events": len(check), "normalization": "none", "control_refits": 0, "retry_count": 0,
        "bounding": bounding, "converged": "not_applicable_fixed64_boosting_stages",
        "primitive_prediction_state": state, "predictor_state_sha256": common._digest(state),
        "primitive_replay_exact": True}


def primitive_predictor_state(model, *, include_state: bool) -> dict:
    names = ["market_logit", "market_staleness_seconds"] + (list(common.base.STATE_FEATURE_NAMES) if include_state else [])
    baseline = np.asarray(model._baseline_prediction)
    if baseline.shape != (1, 1) or not np.isfinite(baseline).all() or len(model._predictors) != 64:
        raise ValueError("HGB primitive baseline/stage shape changed")
    trees = []
    for stage in model._predictors:
        if len(stage) != 1 or len(stage[0].nodes) > 7:
            raise ValueError("HGB primitive tree exceeds fixed four-leaf/depth2 shape")
        nodes = []
        for node in stage[0].nodes:
            if node["is_categorical"]:
                raise ValueError("HGB unexpected categorical split")
            nodes.append({name: node[name].item() for name in (
                "value", "feature_idx", "num_threshold", "left", "right", "is_leaf", "missing_go_to_left")})
        trees.append(nodes)
    state = {"schema": "hgb_numeric_prediction_state_v1", "baseline_prediction": float(baseline[0, 0]),
        "feature_names": names, "trees": trees, "stage_count": 64,
        "leaf_values_include_learning_rate": True, "constructor_params": dict(HGB_PARAMS)}
    common._digest(state)
    return state


def predict_primitive(state: dict, matrix: object) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float64)
    if (matrix.ndim != 2 or matrix.shape[1] != len(state["feature_names"]) or not np.isfinite(matrix).all()
            or len(state["trees"]) != 64 or state["stage_count"] != 64):
        raise ValueError("primitive HGB matrix/stage shape changed")
    result = np.full(matrix.shape[0], state["baseline_prediction"], dtype=np.float64)
    for tree in state["trees"]:
        for ordinal, row in enumerate(matrix):
            index = 0
            for _ in range(3):
                node = tree[index]
                if node["is_leaf"]:
                    result[ordinal] += node["value"]
                    break
                index = node["left"] if row[node["feature_idx"]] <= node["num_threshold"] else node["right"]
            else:
                raise ValueError("primitive HGB tree exceeds depth2 or lacks leaf")
    if not np.isfinite(result).all():
        raise FloatingPointError("primitive HGB prediction became nonfinite")
    return result


def load_parent_predictions(recipe: dict, controls: dict, frozen: dict) -> dict:
    evidence = recipe["research_parent"]
    root = Path(evidence["artifact_root"])
    hashes = {"manifest.json": evidence["manifest_sha256"], "scorecard.json": evidence["scorecard_sha256"],
        "predictions.csv": evidence["predictions_sha256"]}
    if root.is_symlink():
        raise ValueError("actual-parent root is symlinked")
    for name, digest in hashes.items():
        path = root / name
        if not path.is_file() or path.is_symlink() or common._sha256(path) != digest:
            raise ValueError(f"frozen actual-parent artifact hash changed: {name}")
    manifest = common.settlement._strict_json(root / "manifest.json")
    if (manifest.get("complete") is not True or manifest.get("task_id") != evidence["candidate_id"]
            or manifest.get("model_fits") != 4 or manifest.get("check_events") != 87
            or manifest.get("predictions_sha256") != hashes["predictions.csv"]
            or manifest.get("scorecard_sha256") != hashes["scorecard.json"]):
        raise ValueError("frozen actual-parent completion or identity changed")
    availability = {common.identity._control_key(item): int(item["outcome_available_ms"])
        for item in frozen["predictions"]}
    result, ordered = {}, []
    for item in common.frozen_v0._read_csv(root / "predictions.csv"):
        key = common.identity._control_key(item)
        control = controls.get(key)
        if (control is None or key in result or int(item["fold"]) != control["fold"]
                or item["game_id"] != control["game_id"] or item["game_date"] != control["game_date"]
                or item["game_week"] != control["game_week"] or int(item["outcome"]) != control["outcome"]
                or int(item["outcome_available_ms"]) != availability[key]):
            raise ValueError("frozen actual-parent key/fold/identity/label changed")
        for arm, column in ((ARM_RAW, "raw_market_probability"),
                (ARM_ORDINARY, "frozen_v0_ordinary_market_only_probability"),
                (ARM_PARENT, "frozen_v0_market_plus_state_parent_probability")):
            if float(item[column]) != control[arm]:
                raise ValueError("frozen actual-parent comparator changed")
        result[key] = common.probability_contract.validate_probability(float(item["candidate_probability"]),
            common.probability_contract.DEFAULT_PROBABILITY_POLICY, ARM_RESEARCH_PARENT)
        ordered.append(list(key))
    if len(result) != 87 or set(result) != set(controls) or common._digest(ordered) != common.frozen_v0.EXPECTED_CHECK_KEY_SHA256:
        raise ValueError("frozen actual-parent exact87 common mask changed")
    return result


def aggregate(predictions: list, arm: str) -> dict:
    result = common._aggregate(predictions, arm)
    outcomes = [item["row"].trusted["outcome"] for item in predictions]
    parent = [item[ARM_RESEARCH_PARENT] for item in predictions]
    result[ARM_RESEARCH_PARENT] = common.settlement._simple_metrics(outcomes, parent)
    result[ARM_RESEARCH_PARENT]["reliability_table"] = common.base._reliability_table(outcomes, parent)
    return result


def paired_evidence(predictions: list, arm: str) -> dict:
    result = common._paired_evidence(predictions, arm)
    records = [{"game_date": item["row"].game_date, "game_week": item["row"].game_week,
        **{metric: common.identity._loss(item["row"].trusted["outcome"], item[arm], metric)
            - common.identity._loss(item["row"].trusted["outcome"], item[ARM_RESEARCH_PARENT], metric)
            for metric in ("brier", "log_loss")}} for item in predictions]
    result[f"candidate_minus_{ARM_RESEARCH_PARENT}"] = {metric: {
        "delta_convention": "candidate minus actual frozen research parent; negative loss is better",
        "equal_event_mean": math.fsum(row[metric] for row in records) / len(records),
        "by_schedule_date": common.base._group_means(records, "game_date", metric),
        "schedule_date_interval": common.base._group_bootstrap(records, "game_date", metric, seed=20260929, replicates=10000),
        "observed_game_week_interval": common.base._group_bootstrap(records, "game_week", metric, seed=20260929, replicates=10000)
    } for metric in ("brier", "log_loss")}
    return result


def fit_and_predict(rows: list, folds: list, controls: dict, parent: dict, *, include_state: bool, arm: str) -> tuple[list, list]:
    by_date = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    predictions, reports = [], []
    for fold in folds:
        check = sorted([row for day in fold["check_dates"] for row in by_date.get(day, [])], key=lambda row: row.key)
        fit, unavailable = common.nested._strict_prior_rows(by_date, fold["fit_dates"], check)
        for row in check:
            frozen = controls.get(row.key)
            if (frozen is None or row.key not in parent or frozen["fold"] != fold["fold"]
                    or frozen["game_id"] != row.game_id or frozen["game_date"] != row.game_date
                    or frozen["game_week"] != row.game_week or frozen["outcome"] != row.trusted["outcome"]
                    or frozen[ARM_RAW] != row.trusted["market_probability"]):
                raise ValueError("candidate differs from frozen actual-parent or v0 common mask")
        values, trainer = fit_hgb_residual(fit, check, include_state=include_state)
        block = [{"fold": fold["fold"], "row": row, "feature": 0.0, ARM_RAW: row.trusted["market_probability"],
            ARM_ORDINARY: controls[row.key][ARM_ORDINARY], ARM_PARENT: controls[row.key][ARM_PARENT],
            ARM_RESEARCH_PARENT: parent[row.key], arm: probability} for row, probability in zip(check, values, strict=True)]
        metrics = aggregate(block, arm)
        reports.append({"fold": fold["fold"], "fit_dates": list(fold["fit_dates"]), "check_dates": list(fold["check_dates"]),
            "fit_events": len(fit), "check_events": len(check), "fit_label_unavailable_game_ids": unavailable,
            "trainer": trainer, "arms": metrics, "same_rows_labels_and_checkpoints": True,
            "candidate_minus_actual_parent": {metric: metrics[arm][metric] - metrics[ARM_RESEARCH_PARENT][metric]
                for metric in ("brier", "log_loss")}})
        predictions.extend(block)
    keys = [item["row"].key for item in predictions]
    if len(reports) != 4 or len(keys) != len(set(keys)) or set(keys) != set(controls) or set(keys) != set(parent):
        raise ValueError("four fits or exact frozen common mask changed")
    return predictions, reports


def write_predictions(path: Path, predictions: list, arm: str) -> None:
    fields = ("fold", "game_id", "game_date", "game_week", "event_id", "market_id", "cutoff_ms",
        "outcome_available_ms", "outcome", "raw_market_probability", "frozen_v0_ordinary_market_only_probability",
        "frozen_v0_market_plus_state_parent_probability", "candidate_probability", "frozen_actual_parent_probability")
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in predictions:
            row = item["row"]
            writer.writerow(dict(zip(fields, [item["fold"], row.game_id, row.game_date, row.game_week,
                row.trusted["event_id"], row.trusted["market_id"], row.trusted["cutoff_ms"],
                row.trusted["outcome_available_ms"], row.trusted["outcome"], item[ARM_RAW],
                item[ARM_ORDINARY], item[ARM_PARENT], item[arm], item[ARM_RESEARCH_PARENT]], strict=True)))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def run_recipe(source_root: Path, output: Path, *, candidate_id: str, arm: str, include_state: bool,
               runner_file: Path, allow_test_paths: bool = False) -> dict:
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    common.base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    output.mkdir(parents=True, exist_ok=False)
    try:
        contract, recipe = require_dependencies(candidate_id)
        frozen = common.frozen_v0._validate_v0_artifact(V0_ARTIFACT_ROOT)
        controls = common.identity._frozen_controls(frozen)
        parent = load_parent_predictions(recipe, controls, frozen)
        cohort = common.base._validate_source(source_root, expected_events=195, expected_dates=42, allow_test_paths=allow_test_paths)
        pbp = common.base._validate_pbp_receipts(source_root, cohort)
        if pbp != frozen["receipts"]["pbp_receipts"]:
            raise ValueError("opened-Train PBP receipts differ from frozen v0")
        states = {row["game_id"]: row for row in frozen["anchors"]}
        rows, exclusions = [], []
        for ordinal, item in enumerate(cohort):
            try:
                rows.append(common.base._load_dynamic_market(source_root, item, states[item["game_id"]]))
            except common.settlement.EventExclusion as error:
                exclusions.append({"source_ordinal": ordinal, "game_id": item["game_id"], "game_date": item["game_date"],
                    "reason": error.code, "detail": str(error)[:400]})
        rows.sort(key=lambda row: row.key)
        receipts = [row.source_receipt for row in rows]
        if (len(rows) != 193 or len(rows) + len(exclusions) != 195
                or [(item["game_id"], item["reason"]) for item in exclusions] != common.identity.EXPECTED_EXCLUSIONS
                or common._digest(receipts) != common._digest(frozen["receipts"]["materialized_receipts"])):
            raise ValueError("frozen195 denominator, exact exclusions or causal receipts changed")
        feature_matrix(rows, include_state=include_state)
        common.base._atomic_json(output / "input_receipts.json", {"task_id": candidate_id,
            "controller_contract_sha256": CONTRACT_SHA256, "runner_sha256": common._sha256(runner_file),
            "shared_hgb_scaffold_sha256": common._sha256(Path(__file__)), "frozen_common_source_sha256": COMMON_SOURCE_SHA256,
            "dependency_source_hashes": {module.__name__: digest for module, digest in common.DEPENDENCIES.items()},
            "v0_artifact_hashes": frozen["hashes"], "parent_artifacts": recipe["research_parent"], "pbp_receipts": pbp,
            "materialized_receipts": receipts, "source_manifest_sha256": common._sha256(source_root / "manifest.json"),
            "cohort_sha256": common._sha256(source_root / "cohort.csv"), **common.BOUNDARY_FLAGS})
        common.base._atomic_json(output / "pre_score_lock.json", {"task_id": candidate_id,
            "generated_utc": datetime.now(timezone.utc).isoformat(), "controller_contract_sha256": CONTRACT_SHA256,
            "scientific_recipe": recipe, "shared_prediction_recipe": contract["shared_prediction_recipe"],
            "boundary": contract["boundary"], "folds": frozen["folds"], "fit_budget": 4, "automatic_retries": 0,
            "thread_environment_contract": common.identity.THREAD_ENV_CONTRACT, **common.BOUNDARY_FLAGS})
        common.base._atomic_json(output / "exclusions.json", {"source_events": 195, "materialized_events": 193,
            "excluded_events": 2, "reconciles_to_source_denominator": True, "exclusions": exclusions})
        predictions, reports = fit_and_predict(rows, frozen["folds"], controls, parent, include_state=include_state, arm=arm)
        check_hash = common._digest([list(item["row"].key) for item in predictions])
        if (len(predictions) != 87 or check_hash != common.frozen_v0.EXPECTED_CHECK_KEY_SHA256
                or tuple(item["fit_events"] for item in reports) != (106, 132, 148, 176)
                or tuple(item["check_events"] for item in reports) != (26, 16, 28, 17)
                or any(item["fit_label_unavailable_game_ids"] for item in reports)):
            raise ValueError("frozen chronology, fit counts or exact87 mask changed")
        predictor_states = {"schema": "hgb_numeric_prediction_states_v1", "task_id": candidate_id,
            "folds": [{"fold": report["fold"], "state_sha256": report["trainer"]["predictor_state_sha256"],
                "state": report["trainer"].pop("primitive_prediction_state")} for report in reports]}
        common.base._atomic_json(output / "predictor_states.json", predictor_states)
        metrics, paired = aggregate(predictions, arm), paired_evidence(predictions, arm)
        scientific, operational, conditions = common.decision(metrics, reports, paired, arm)
        scorecard = {"schema": "coevo_frozen_candidate_scorecard_v1", "task_id": candidate_id, "candidate_arm": arm,
            "actual_research_parent_arm": ARM_RESEARCH_PARENT, "actual_research_parent_id": recipe["research_parent"]["candidate_id"],
            "scientific_decision": scientific, "operational_decision": operational, "decision_conditions": conditions,
            "model_fits": 4, "control_refits": 0, "constructor_params": HGB_PARAMS,
            "feature_names": recipe["feature_names"], "clipped_check_rows": sum(item["trainer"]["bounding"]["clipped_rows"] for item in reports),
            "source_denominator": {"events": 195, "dates": 42, "materialized_events": 193, "excluded_events": 2,
                "check_events": 87, "check_dates": len({item["row"].game_date for item in predictions}),
                "check_game_weeks": len({item["row"].game_week for item in predictions})},
            "identical_masks": {"all_four_arms_same_rows_labels_and_checkpoints": True, "actual_parent_same_rows": True,
                "check_key_sha256": check_hash, "matches_frozen_v0": True},
            "aggregate": metrics, "folds": reports, "paired_grouped_evidence": paired,
            "research_parent_sha256": recipe["research_parent"]["runner_sha256"],
            "comparison_incumbent_sha256": recipe["comparison_incumbent_sha256"],
            "parent_attribution": recipe["parent_attribution"], "paired_sibling_analysis": "Supervisor only after both verified",
            "inference_boundary": "repeatedly inspected opened-Train Discovery; historical event clock only", **common.BOUNDARY_FLAGS}
        write_predictions(output / "predictions.csv", predictions, arm)
        common.base._atomic_json(output / "scorecard.json", scorecard)
        manifest = {"schema": "coevo_frozen_candidate_manifest_v1", "complete": True, "task_id": candidate_id,
            "completed_utc": datetime.now(timezone.utc).isoformat(), "source_events": 195,
            "materialized_events": 193, "excluded_events": 2, "check_events": 87,
            "model_fits": 4, "control_refits": 0, "automatic_retries": 0,
            "scientific_decision": scientific, "operational_decision": operational,
            **{f"{name}_sha256": common._sha256(output / f"{name}.{suffix}") for name, suffix in (
                ("pre_score_lock", "json"), ("input_receipts", "json"), ("exclusions", "json"),
                ("predictions", "csv"), ("scorecard", "json"), ("predictor_states", "json"))}, **common.BOUNDARY_FLAGS}
        common.base._atomic_json(output / "manifest.json", manifest)
        return manifest
    except Exception as error:
        common.base._atomic_json(output / "failure.json", {"task_id": candidate_id,
            "error_type": type(error).__name__, "error": str(error)[:1200], "model_fits_maximum": 4,
            "automatic_retries": 0, **common.BOUNDARY_FLAGS})
        raise


def run(source_root: Path, output: Path, *, allow_test_paths: bool = False) -> dict:
    return run_recipe(source_root, output, candidate_id=TASK_ID, arm=ARM_CANDIDATE,
        include_state=False, runner_file=Path(__file__), allow_test_paths=allow_test_paths)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(common.settlement.json.dumps(run(args.source_root, args.output), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
