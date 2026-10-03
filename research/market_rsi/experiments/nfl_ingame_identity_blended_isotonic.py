#!/usr/bin/env python3
"""Fixed identity-blended isotonic calibration; historical Train Discovery."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import math
from pathlib import Path
import platform

import numpy as np
import scipy
import sklearn
from sklearn.isotonic import IsotonicRegression

from experiments import nfl_ingame_market_residual_hgb as shared


common = shared.common
TASK_ID = "InGameIdentityBlendedIsotonic-v1"
ARM_CANDIDATE = "identity_blended_isotonic"
ARM_RESEARCH_PARENT = shared.ARM_RESEARCH_PARENT
ARM_RAW, ARM_ORDINARY, ARM_PARENT = shared.ARM_RAW, shared.ARM_ORDINARY, shared.ARM_PARENT
SOURCE_ROOT, V0_ARTIFACT_ROOT = shared.SOURCE_ROOT, shared.V0_ARTIFACT_ROOT
MODEL_FITS, BLEND_WEIGHT = 4, .25
CONTRACT = Path(__file__).parents[1] / "supervisor_harness" / "COEVO_BATCH3_CONTRACTS_2026-10-03.json"
CONTRACT_SHA256 = "c4fc188d525e87fdf1d84efc127ab7bf7a122eedf722db139f4f8fcd9f700b7f"
SHARED_SOURCE_SHA256 = "a17220dea91373b73c3f2e3a5d6e36f2b3e1b2866c8714cdc292dd921aefad79"
EPSILON = common.probability_contract.DEFAULT_PROBABILITY_POLICY.epsilon
ISOTONIC_PARAMS = {"y_min": EPSILON, "y_max": 1 - EPSILON, "increasing": True, "out_of_bounds": "clip"}


def require_dependencies(candidate_id: str = TASK_ID) -> tuple[dict, dict]:
    shared.require_dependencies(shared.TASK_ID)
    for path, digest in ((CONTRACT, CONTRACT_SHA256), (Path(shared.__file__), SHARED_SOURCE_SHA256)):
        if not path.is_file() or path.is_symlink() or common._sha256(path) != digest:
            raise ValueError(f"frozen Batch3 dependency/contract changed: {path.name}")
    contract = common.settlement._strict_json(CONTRACT)
    choices = [item for item in contract["candidates"] if item["candidate_id"] == candidate_id]
    if len(choices) != 1 or sklearn.__version__ != "1.6.1":
        raise ValueError("frozen Batch3 candidate/runtime changed")
    recipe = choices[0]
    parent_file = {"InGameMarketResidualHGB-v1": "nfl_ingame_market_residual_hgb.py",
        "InGameCausalPossessionPressureOffset-v1": "nfl_ingame_causal_possession_pressure_offset.py"}[recipe["research_parent"]["candidate_id"]]
    path = Path(__file__).with_name(parent_file)
    if path.is_symlink() or common._sha256(path) != recipe["research_parent"]["runner_sha256"]:
        raise ValueError("frozen Batch3 actual-parent source changed")
    return contract, recipe


def raw_probabilities(rows: list) -> np.ndarray:
    raw = common._vector([row.trusted["market_probability"] for row in rows], "raw market probabilities")
    common.identity._clipped_logits(raw)
    logits = np.asarray([math.log(value / (1 - value)) for value in raw])
    if not np.array_equal(logits, np.asarray([row.market_features[0] for row in rows])):
        raise ValueError("raw-market feature logit changed")
    return raw


def replay_isotonic(state: dict, raw: object) -> list[float]:
    raw = common._vector(raw, "isotonic prediction probabilities")
    common.identity._clipped_logits(raw)
    x = common._vector(state["X_thresholds_"], "isotonic X thresholds")
    y = common._vector(state["y_thresholds_"], "isotonic y thresholds")
    if (x.shape != y.shape or np.any(np.diff(x) <= 0) or np.any(np.diff(y) < 0)
            or np.any(x <= 0) or np.any(x >= 1) or np.any(y < EPSILON) or np.any(y > 1 - EPSILON)
            or state["X_min_"] != float(x[0]) or state["X_max_"] != float(x[-1])
            or state["constructor_params"] != ISOTONIC_PARAMS or state["blend_weight"] != BLEND_WEIGHT):
        raise ValueError("isotonic numeric thresholds, endpoints, constructor or blend changed")
    calibrated = np.interp(np.clip(raw, x[0], x[-1]), x, y)
    return [common.probability_contract.validate_probability(float(value),
        common.probability_contract.DEFAULT_PROBABILITY_POLICY, ARM_CANDIDATE)
        for value in (1 - BLEND_WEIGHT) * raw + BLEND_WEIGHT * calibrated]


def fit_isotonic(fit: list, check: list, features: object = None) -> tuple[list[float], dict]:
    del features
    fit_p, check_p = raw_probabilities(fit), raw_probabilities(check)
    y = common._vector([row.trusted["outcome"] for row in fit], "fit outcomes")
    if y.shape != fit_p.shape or np.any((y != 0) & (y != 1)):
        raise ValueError("isotonic fit labels must be aligned binary outcomes")
    model = IsotonicRegression(**ISOTONIC_PARAMS)
    if model.get_params(deep=False) != ISOTONIC_PARAMS:
        raise ValueError("isotonic actual constructor differs from frozen recipe")
    model.fit(fit_p, y, sample_weight=None)
    state = {"schema": "identity_blended_isotonic_numeric_state_v1", "constructor_params": model.get_params(deep=False),
        "blend_weight": BLEND_WEIGHT, "sample_weight": None, "fit_events": len(fit),
        "X_thresholds_": model.X_thresholds_.tolist(), "y_thresholds_": model.y_thresholds_.tolist(),
        "X_min_": float(model.X_min_), "X_max_": float(model.X_max_)}
    replay = replay_isotonic(state, check_p)
    calibrated = model.predict(check_p)
    values = ((1 - BLEND_WEIGHT) * check_p + BLEND_WEIGHT * calibrated).tolist()
    if not np.array_equal(np.asarray(replay), np.asarray(values)):
        raise ValueError("isotonic numeric interpolation replay differs from trained predictions")
    return values, {"constructor_params": state["constructor_params"], "model_fits": 1,
        "predictor_state_sha256": common._digest(state), "primitive_prediction_state": state,
        "threshold_count": len(model.X_thresholds_), "fit_events": len(fit), "input_columns": 1,
        "check_below_fit_range": int(np.count_nonzero(check_p < model.X_min_)),
        "check_above_fit_range": int(np.count_nonzero(check_p > model.X_max_)),
        "endpoint_clipping_is_not_row_deletion": True, "interpolation_replay_exact": True,
        "fit_only": True, "bounding": {"clipped_rows": 0, "rows_removed": 0, "epsilon": EPSILON}}


def fit_and_predict(rows: list, folds: list, controls: dict, parent: dict, *,
                    fit_predict=fit_isotonic, features: object = None, arm: str = ARM_CANDIDATE) -> tuple[list, list]:
    if len(folds) != MODEL_FITS or [fold["fold"] for fold in folds] != [1, 2, 3, 4]:
        raise ValueError("Batch3 requires exactly four ordered folds/fits")
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
                raise ValueError("Batch3 row differs from frozen actual-parent/v0 key/identity/label")
        values, trainer = fit_predict(fit, check, features)
        block = [{"fold": fold["fold"], "row": row, "feature": 0., ARM_RAW: row.trusted["market_probability"],
            ARM_ORDINARY: controls[row.key][ARM_ORDINARY], ARM_PARENT: controls[row.key][ARM_PARENT],
            ARM_RESEARCH_PARENT: parent[row.key], arm: value} for row, value in zip(check, values, strict=True)]
        metrics = shared.aggregate(block, arm)
        reports.append({"fold": fold["fold"], "fit_dates": list(fold["fit_dates"]), "check_dates": list(fold["check_dates"]),
            "fit_events": len(fit), "check_events": len(check), "fit_label_unavailable_game_ids": unavailable,
            "trainer": trainer, "arms": metrics, "same_rows_labels_and_checkpoints": True,
            "candidate_minus_actual_parent": {metric: metrics[arm][metric] - metrics[ARM_RESEARCH_PARENT][metric]
                for metric in ("brier", "log_loss")}})
        predictions.extend(block)
    keys = [item["row"].key for item in predictions]
    if len(keys) != len(set(keys)) or set(keys) != set(controls) or set(keys) != set(parent):
        raise ValueError("Batch3 frozen actual-parent common mask changed")
    return predictions, reports


def market_only_features(source_root: Path, frozen: dict, recipe: dict, rows: list) -> tuple[None, dict]:
    del source_root, frozen, recipe
    raw_probabilities(rows)
    return None, {"predictive_fields": ["raw_market_probability"], "all_materialized_rows_validated": len(rows)}


def run_recipe(source_root: Path, output: Path, *, candidate_id: str, arm: str, runner_file: Path,
               fit_predict, feature_loader, extra_dependency_hashes: dict | None = None,
               allow_test_paths: bool = False) -> dict:
    """Two Batch3 siblings reuse a bounded immutable evidence boundary, not a scheduler."""
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    common.base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    output.mkdir(parents=True, exist_ok=False)
    try:
        contract, recipe = require_dependencies(candidate_id)
        if runner_file.name != Path(recipe["allowed_production_paths"][0]).name:
            raise ValueError("Batch3 recipe/runner source identity changed")
        frozen = common.frozen_v0._validate_v0_artifact(V0_ARTIFACT_ROOT)
        controls = common.identity._frozen_controls(frozen)
        parent = shared.load_parent_predictions(recipe, controls, frozen)
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
            raise ValueError("Batch3 frozen195 denominator/exclusions/causal receipts changed")
        features, feature_receipts = feature_loader(source_root, frozen, recipe, rows)
        dependencies = {module.__name__: digest for module, digest in common.DEPENDENCIES.items()}
        dependencies.update({common.__name__: shared.COMMON_SOURCE_SHA256, shared.__name__: SHARED_SOURCE_SHA256,
            __name__: common._sha256(Path(__file__)), **(extra_dependency_hashes or {})})
        common.base._atomic_json(output / "input_receipts.json", {"task_id": candidate_id,
            "controller_contract_sha256": CONTRACT_SHA256, "runner_sha256": common._sha256(runner_file),
            "dependency_source_hashes": dependencies, "feature_receipts": feature_receipts,
            "runtime_versions": {"python": platform.python_version(), "numpy": np.__version__,
                "scipy": scipy.__version__, "sklearn": sklearn.__version__},
            "v0_artifact_hashes": frozen["hashes"], "parent_artifacts": recipe["research_parent"], "pbp_receipts": pbp,
            "materialized_receipts": receipts, "source_manifest_sha256": common._sha256(source_root / "manifest.json"),
            "cohort_sha256": common._sha256(source_root / "cohort.csv"), **common.BOUNDARY_FLAGS})
        common.base._atomic_json(output / "pre_score_lock.json", {"task_id": candidate_id,
            "generated_utc": datetime.now(timezone.utc).isoformat(), "controller_contract_sha256": CONTRACT_SHA256,
            "scientific_recipe": recipe, "batch_boundary": contract["boundary"], "folds": frozen["folds"],
            "fit_budget": MODEL_FITS, "automatic_retries": 0,
            "thread_environment_contract": common.identity.THREAD_ENV_CONTRACT, **common.BOUNDARY_FLAGS})
        common.base._atomic_json(output / "exclusions.json", {"source_events": 195, "materialized_events": 193,
            "excluded_events": 2, "reconciles_to_source_denominator": True, "exclusions": exclusions})
        predictions, reports = fit_and_predict(rows, frozen["folds"], controls, parent,
            fit_predict=fit_predict, features=features, arm=arm)
        check_hash = common._digest([list(item["row"].key) for item in predictions])
        if (len(predictions) != 87 or check_hash != common.frozen_v0.EXPECTED_CHECK_KEY_SHA256
                or tuple(item["fit_events"] for item in reports) != (106, 132, 148, 176)
                or tuple(item["check_events"] for item in reports) != (26, 16, 28, 17)
                or any(item["fit_label_unavailable_game_ids"] for item in reports)):
            raise ValueError("Batch3 frozen chronology, fit counts or exact87 mask changed")
        predictor_states = {"schema": "batch3_numeric_prediction_states_v1", "task_id": candidate_id,
            "folds": [{"fold": report["fold"], "state_sha256": report["trainer"]["predictor_state_sha256"],
                "state": report["trainer"].pop("primitive_prediction_state")} for report in reports]}
        common.base._atomic_json(output / "predictor_states.json", predictor_states)
        metrics, paired = shared.aggregate(predictions, arm), shared.paired_evidence(predictions, arm)
        scientific, operational, conditions = common.decision(metrics, reports, paired, arm)
        scorecard = {"schema": "coevo_frozen_candidate_scorecard_v1", "task_id": candidate_id, "candidate_arm": arm,
            "actual_research_parent_arm": ARM_RESEARCH_PARENT, "actual_research_parent_id": recipe["research_parent"]["candidate_id"],
            "scientific_decision": scientific, "operational_decision": operational, "decision_conditions": conditions,
            "model_fits": MODEL_FITS, "control_refits": 0, "recipe": recipe["recipe"],
            "source_denominator": {"events": 195, "dates": 42, "materialized_events": 193, "excluded_events": 2,
                "check_events": 87, "check_dates": len({item["row"].game_date for item in predictions}),
                "check_game_weeks": len({item["row"].game_week for item in predictions})},
            "identical_masks": {"all_four_arms_same_rows_labels_and_checkpoints": True, "actual_parent_same_rows": True,
                "check_key_sha256": check_hash, "matches_frozen_v0": True},
            "aggregate": metrics, "folds": reports, "paired_grouped_evidence": paired,
            "research_parent_sha256": recipe["research_parent"]["runner_sha256"],
            "comparison_incumbent_sha256": recipe["comparison_incumbent_sha256"],
            "attribution": recipe.get("parent_attribution", recipe["recipe"].get("attribution_limit")),
            "inference_boundary": "repeatedly inspected opened-Train Discovery; historical event clock only", **common.BOUNDARY_FLAGS}
        shared.write_predictions(output / "predictions.csv", predictions, arm)
        common.base._atomic_json(output / "scorecard.json", scorecard)
        manifest = {"schema": "coevo_frozen_candidate_manifest_v1", "complete": True, "task_id": candidate_id,
            "completed_utc": datetime.now(timezone.utc).isoformat(), "source_events": 195,
            "materialized_events": 193, "excluded_events": 2, "check_events": 87,
            "model_fits": MODEL_FITS, "control_refits": 0, "automatic_retries": 0,
            "scientific_decision": scientific, "operational_decision": operational,
            **{f"{name}_sha256": common._sha256(output / f"{name}.{suffix}") for name, suffix in (
                ("pre_score_lock", "json"), ("input_receipts", "json"), ("exclusions", "json"),
                ("predictions", "csv"), ("scorecard", "json"), ("predictor_states", "json"))}, **common.BOUNDARY_FLAGS}
        common.base._atomic_json(output / "manifest.json", manifest)
        return manifest
    except Exception as error:
        common.base._atomic_json(output / "failure.json", {"task_id": candidate_id,
            "error_type": type(error).__name__, "error": str(error)[:1200], "model_fits_maximum": MODEL_FITS,
            "automatic_retries": 0, **common.BOUNDARY_FLAGS})
        raise


def run(source_root: Path, output: Path, *, allow_test_paths: bool = False) -> dict:
    return run_recipe(source_root, output, candidate_id=TASK_ID, arm=ARM_CANDIDATE, runner_file=Path(__file__),
        fit_predict=fit_isotonic, feature_loader=market_only_features, allow_test_paths=allow_test_paths)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(common.settlement.json.dumps(run(args.source_root, args.output), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
