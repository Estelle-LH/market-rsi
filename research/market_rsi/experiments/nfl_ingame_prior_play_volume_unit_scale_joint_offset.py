#!/usr/bin/env python3
"""Fit-unit volume coordinate and changed effective ridge prior; Train Discovery."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import math
from pathlib import Path
import platform

import numpy as np
import scipy
from scipy.special import expit

from experiments import nfl_ingame_prior_play_volume_freshness_joint_offset as native


common, sibling, shared, volume = native.common, native.sibling, native.shared, native.volume
TASK_ID = "InGamePriorPlayVolumeUnitScaleJointOffset-v3"
ARM_CANDIDATE = "prior_play_volume_unit_scale_joint_offset"
ARM_RESEARCH_PARENT = shared.ARM_RESEARCH_PARENT
ARM_RAW, ARM_ORDINARY, ARM_PARENT = shared.ARM_RAW, shared.ARM_ORDINARY, shared.ARM_PARENT
SOURCE_ROOT, V0_ARTIFACT_ROOT = shared.SOURCE_ROOT, shared.V0_ARTIFACT_ROOT
MODEL_FITS = 4
CONTRACT = Path(__file__).parents[1] / "supervisor_harness" / "COEVO_BATCH4_CONTRACT_2026-10-03.json"
CONTRACT_SHA256 = "c40d9c30dadab9c46d307a7f23ff697e911d5673f2b39e2ab1c24297b05c9394"
NATIVE_SOURCE_SHA256 = "7a3175c1ec75465e2b71816260d7ef2d8fd75bfd6a854da6276d619271c046ce"
COLUMNS = ["fit_unit_prior_play_volume_ratio", "fit_only_freshness_x_market_logit"]


def require_dependencies() -> dict:
    native.require_dependencies()
    for path, expected in ((CONTRACT, CONTRACT_SHA256), (Path(native.__file__), NATIVE_SOURCE_SHA256)):
        if not path.is_file() or path.is_symlink() or common._sha256(path) != expected:
            raise ValueError(f"frozen unit-scale source/contract changed: {path.name}")
    contract = common.settlement._strict_json(CONTRACT)
    if (contract["candidate_id"] != TASK_ID or contract["research_parent"]["runner_sha256"] != NATIVE_SOURCE_SHA256
            or contract["recipe"]["column_order"] != COLUMNS or contract["recipe"]["native_columns"] != native.COLUMNS
            or contract["recipe"]["penalty_per_coordinate"] != common.scaffold.PENALTY
            or contract["recipe"]["scale_only_not_centering"] is not True):
        raise ValueError("frozen fit-unit representation/actual-parent recipe changed")
    return contract


def load_parent(contract: dict, controls: dict, frozen: dict) -> tuple[dict, dict]:
    probabilities = shared.load_parent_predictions(contract, controls, frozen)
    evidence, root = contract["research_parent"], Path(contract["research_parent"]["artifact_root"])
    manifest = common.settlement._strict_json(root / "manifest.json")
    for name, suffix in (("input_receipts", "json"), ("pre_score_lock", "json"), ("exclusions", "json"),
            ("predictor_states", "json"), ("scorecard", "json"), ("predictions", "csv")):
        path, key = root / f"{name}.{suffix}", f"{name}_sha256"
        expected = evidence.get(key, manifest.get(key))
        if (not expected or not path.is_file() or path.is_symlink() or common._sha256(path) != expected
                or manifest.get(key) != expected):
            raise ValueError(f"frozen C3 seven-file parent receipt changed: {name}")
    receipts = common.settlement._strict_json(root / "input_receipts.json")
    lock = common.settlement._strict_json(root / "pre_score_lock.json")
    exclusions = common.settlement._strict_json(root / "exclusions.json")
    if (receipts["runner_sha256"] != NATIVE_SOURCE_SHA256 or receipts["controller_contract_sha256"] != native.CONTRACT_SHA256
            or lock["task_id"] != native.TASK_ID or lock["controller_contract_sha256"] != native.CONTRACT_SHA256
            or receipts["v0_artifact_hashes"] != frozen["hashes"]
            or receipts["pbp_receipts"] != frozen["receipts"]["pbp_receipts"]
            or common._digest(receipts["materialized_receipts"]) != common._digest(frozen["receipts"]["materialized_receipts"])
            or (exclusions["source_events"], exclusions["materialized_events"], exclusions["excluded_events"]) != (195, 193, 2)
            or [(item["game_id"], item["reason"]) for item in exclusions["exclusions"]] != common.identity.EXPECTED_EXCLUSIONS
            or any(receipts.get(key) != value for key, value in common.BOUNDARY_FLAGS.items())):
        raise ValueError("frozen C3 parent source/causal receipts/exclusion/kernel binding changed")
    artifact = common.settlement._strict_json(root / "predictor_states.json")
    reports = common.settlement._strict_json(root / "scorecard.json")["folds"]
    if (artifact["task_id"] != native.TASK_ID or [item["fold"] for item in artifact["folds"]] != [1, 2, 3, 4]
            or len(reports) != 4 or len(evidence["state_sha256_by_fold"]) != 4):
        raise ValueError("frozen C3 canonical four-state task/coverage changed")
    states = {}
    for item, report, expected in zip(artifact["folds"], reports, evidence["state_sha256_by_fold"], strict=True):
        state, digest = item["state"], common._digest(item["state"])
        norm = state["freshness_normalization"]
        theta = common._vector(state["coefficients"], "frozen parent coefficients")
        if (digest != expected or digest != item["state_sha256"] or report["fold"] != item["fold"]
                or report["trainer"]["predictor_state_sha256"] != digest or theta.shape != (2,)
                or state["schema"] != evidence["state_schema"] or state["column_order"] != native.COLUMNS
                or state["volume_formula"] != volume.FORMULA or state["freshness_formula"] != native.FRESHNESS_FORMULA
                or state["penalty_per_coordinate"] != 16 or state["market_coefficient"] != 1 or state["intercept"] is not False
                or norm.get("fit_only") is not True or not math.isfinite(norm["fit_age_mean"])
                or not 0 <= norm["fit_age_mean"] <= 300 or not math.isfinite(norm["fit_age_std_ddof0"])
                or norm["fit_age_std_ddof0"] <= 0):
            raise ValueError("frozen C3 canonical state/normalizer/formula changed")
        states[item["fold"]] = state
    return probabilities, states


def replay_parent(rows: list, folds: list, features: dict, parent: dict, states: dict) -> dict:
    if len(folds) != 4 or set(states) != {1, 2, 3, 4}:
        raise ValueError("C3 parent replay requires four frozen folds/states")
    by_date = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    seen, receipts = set(), []
    for fold in folds:
        check = sorted([row for day in fold["check_dates"] for row in by_date.get(day, [])], key=lambda row: row.key)
        fit, unavailable = common.nested._strict_prior_rows(by_date, fold["fit_dates"], check)
        design, _, normalizer = native.joint_design(fit, check, features)
        state = states[fold["fold"]]
        if (unavailable or state["fit_events"] != len(fit) or state["freshness_normalization"] != normalizer
                or state["fit_feature_sha256"] != common._digest(design.tolist())):
            raise ValueError("C3 parent native fit features/normalizer/available labels changed")
        values = native.replay_joint(state, check, features)
        if any(row.key in seen or row.key not in parent or value != parent[row.key]
                for row, value in zip(check, values, strict=True)):
            raise ValueError("C3 parent primitive probabilities/common mask replay differs")
        seen.update(row.key for row in check)
        receipts.append({"fold": fold["fold"], "parent_state_sha256": common._digest(state),
            "native_fit_feature_sha256": state["fit_feature_sha256"], "freshness_normalization_exact": True,
            "parent_probabilities_replayed": len(check), "parent_refits": 0})
    if seen != set(parent):
        raise ValueError("C3 parent primitive replay coverage changed")
    return {"folds": receipts, "parent_rows_replayed": len(seen), "parent_refits": 0,
        "all_parent_probabilities_exact": True, "all_freshness_normalizers_exact": True}


def scaled_design(fit: list, check: list, features: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, dict]:
    native_fit, native_check, normalizer = native.joint_design(fit, check, features)
    scale = float(np.std(native_fit[:, 0], ddof=0))
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("fit-only native volume population std must be finite and positive; no floor")
    normalized = []
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        for matrix in (native_fit, native_check):
            transformed = matrix.copy()
            transformed[:, 0] /= scale
            if not np.isfinite(transformed).all():
                raise ValueError("fit-unit transformed features became nonfinite")
            normalized.append(transformed)
    return native_fit, native_check, normalized[0], normalized[1], scale, normalizer


def replay_unit(state: dict, rows: list, features: dict) -> list[float]:
    scale, norm = state["volume_scale"], state["freshness_normalization"]
    theta = common._vector(state["coefficients"], "unit-scale coefficients")
    if (state["column_order"] != COLUMNS or state["native_columns"] != native.COLUMNS
            or state["volume_formula"] != volume.FORMULA or state["freshness_formula"] != native.FRESHNESS_FORMULA
            or state["scale_only"] is not True or state["scale_ddof"] != 0 or state["scale_fit_only"] is not True
            or not math.isfinite(scale) or scale <= 0 or theta.shape != (2,)
            or state["native_volume_coefficient"] != float(theta[0] / scale)
            or state["effective_native_volume_penalty"] != 16 * scale * scale
            or state["market_coefficient"] != 1 or state["intercept"] is not False or state["penalty_per_coordinate"] != 16
            or norm.get("fit_only") is not True or not math.isfinite(norm["fit_age_mean"])
            or not 0 <= norm["fit_age_mean"] <= 300 or not math.isfinite(norm["fit_age_std_ddof0"]) or norm["fit_age_std_ddof0"] <= 0):
        raise ValueError("unit-scale numeric state/fit-only scale/normalizer changed")
    raw = sibling.raw_probabilities(rows)
    ratios = common._vector([features[row.game_id] for row in rows], "native replay volume ratios")
    if np.any(ratios <= -1) or np.any(ratios >= 1):
        raise ValueError("native replay volume physical bounds changed")
    logits = np.asarray([row.market_features[0] for row in rows])
    ages = np.asarray([common.causal_age(row.source_receipt) for row in rows])
    design = np.column_stack((ratios / scale, (ages - norm["fit_age_mean"]) / norm["fit_age_std_ddof0"] * logits))
    return native.probabilities(theta, design, logits, raw)


def fit_unit(fit: list, check: list, features: dict) -> tuple[list[float], dict]:
    native_fit, native_check, design, check_design, scale, norm = scaled_design(fit, check, features)
    y, offsets = np.asarray([row.trusted["outcome"] for row in fit]), np.asarray([row.market_features[0] for row in fit])
    theta, optimizer = common.scaffold.fit_stratified_offset(design, y, offsets)
    theta = common._vector(theta, "fitted unit-scale coefficients")
    if theta.shape != (2,):
        raise ValueError("unit-scale optimizer returned wrong parameter shape")
    eta, p = offsets + design @ theta, expit(offsets + design @ theta)
    objective = float(np.sum(np.logaddexp(0., eta) - y * eta) + 8 * (theta @ theta))
    gradient = design.T @ (p - y) + 16 * theta
    hessian = design.T @ (design * (p * (1 - p))[:, None]) + 16 * np.eye(2)
    eigenvalues, grad_inf = np.linalg.eigvalsh(hessian), float(np.max(np.abs(gradient)))
    if (not optimizer["converged"] or optimizer["penalty"] != 16 or optimizer["retry_count"] != 0
            or optimizer["iterations"] > 50 or not math.isfinite(objective) or not np.isfinite(gradient).all()
            or not np.isfinite(hessian).all() or grad_inf > 1e-8 or np.min(eigenvalues) <= 0):
        raise ValueError("unit-scale fit failed finite stationarity/positive-definite Hessian")
    state = {"schema": "prior_play_volume_unit_scale_joint_numeric_state_v1", "column_order": COLUMNS,
        "native_columns": native.COLUMNS, "volume_formula": volume.FORMULA, "freshness_formula": native.FRESHNESS_FORMULA,
        "volume_scale": scale, "scale_ddof": 0, "scale_fit_only": True, "scale_only": True,
        "coefficients": theta.tolist(), "native_volume_coefficient": float(theta[0] / scale),
        "effective_native_volume_penalty": 16 * scale * scale, "freshness_normalization": norm,
        "market_coefficient": 1, "intercept": False, "penalty_per_coordinate": 16, "fit_events": len(fit),
        "native_fit_feature_sha256": common._digest(native_fit.tolist()), "normalized_fit_feature_sha256": common._digest(design.tolist()),
        "native_check_feature_sha256": common._digest(native_check.tolist()), "normalized_check_feature_sha256": common._digest(check_design.tolist()),
        "stationarity": {"objective": objective, "gradient": gradient.tolist(), "gradient_infinity_norm": grad_inf,
            "hessian": hessian.tolist(), "hessian_eigenvalues": eigenvalues.tolist()}}
    values = native.probabilities(theta, check_design, [row.market_features[0] for row in check], sibling.raw_probabilities(check))
    if values != replay_unit(state, check, features):
        raise ValueError("unit-scale numeric predictor replay differs")
    return values, {"model_fits": 1, "input_columns": 2, "fit_events": len(fit), "fit_only": True,
        "optimizer": optimizer, "legacy_beta_low_high_column_order": {"beta_low": COLUMNS[0], "beta_high": COLUMNS[1]},
        "predictor_state_sha256": common._digest(state), "primitive_prediction_state": state, "primitive_replay_exact": True,
        "bounding": {"clipped_rows": 0, "rows_removed": 0, "epsilon": sibling.EPSILON}}


def annotate_question(metrics: dict, reports: list, paired: dict) -> dict:
    deltas = {name: metrics[ARM_CANDIDATE][name] - metrics[ARM_RESEARCH_PARENT][name] for name in ("brier", "log_loss")}
    wins = sum(item["arms"][ARM_CANDIDATE]["brier"] < item["arms"][ARM_RESEARCH_PARENT]["brier"] for item in reports)
    directional = all(value < 0 for value in deltas.values()) and wins >= 3
    evidence = paired[f"candidate_minus_{ARM_RESEARCH_PARENT}"]["brier"]
    return {"annotation_only_not_keep_judge": True, "candidate_minus_actual_parent": deltas, "parent_brier_block_wins": wins,
        "directional_unit_prior_evidence": directional, "stronger_local_evidence": directional and all(
            evidence[name]["interval_95"][1] < 0 for name in ("schedule_date_interval", "observed_game_week_interval")),
        "exact_recipe_question_failed": any(value > 0 for value in deltas.values())}


def run(source_root: Path, output: Path, *, allow_test_paths: bool = False) -> dict:
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    common.base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    output.mkdir(parents=True, exist_ok=False)
    try:
        contract = require_dependencies()
        frozen = common.frozen_v0._validate_v0_artifact(V0_ARTIFACT_ROOT)
        controls = common.identity._frozen_controls(frozen)
        parent, parent_states = load_parent(contract, controls, frozen)
        cohort = common.base._validate_source(source_root, expected_events=195, expected_dates=42, allow_test_paths=allow_test_paths)
        pbp = common.base._validate_pbp_receipts(source_root, cohort)
        if pbp != frozen["receipts"]["pbp_receipts"]:
            raise ValueError("opened-Train PBP receipts differ from frozen v0")
        anchors = {row["game_id"]: row for row in frozen["anchors"]}
        rows, exclusions = [], []
        for ordinal, item in enumerate(cohort):
            try:
                rows.append(common.base._load_dynamic_market(source_root, item, anchors[item["game_id"]]))
            except common.settlement.EventExclusion as error:
                exclusions.append({"source_ordinal": ordinal, "game_id": item["game_id"], "game_date": item["game_date"],
                    "reason": error.code, "detail": str(error)[:400]})
        rows.sort(key=lambda row: row.key)
        receipts = [row.source_receipt for row in rows]
        if (len(rows) != 193 or len(rows) + len(exclusions) != 195
                or [(item["game_id"], item["reason"]) for item in exclusions] != common.identity.EXPECTED_EXCLUSIONS
                or common._digest(receipts) != common._digest(frozen["receipts"]["materialized_receipts"])):
            raise ValueError("unit-scale frozen195 denominator/exclusions/causal receipts changed")
        features, feature_receipts = native.load_features(source_root, frozen, contract, rows)
        parent_replay = replay_parent(rows, frozen["folds"], features, parent, parent_states)
        dependencies = {module.__name__: digest for module, digest in common.DEPENDENCIES.items()}
        dependencies.update({common.__name__: shared.COMMON_SOURCE_SHA256, shared.__name__: sibling.SHARED_SOURCE_SHA256,
            sibling.__name__: volume.SIBLING_SOURCE_SHA256, volume.__name__: native.VOLUME_SOURCE_SHA256,
            native.__name__: NATIVE_SOURCE_SHA256, volume.uncertainty.__name__: volume.UNCERTAINTY_SOURCE_SHA256})
        common.base._atomic_json(output / "input_receipts.json", {"task_id": TASK_ID,
            "controller_contract_sha256": CONTRACT_SHA256, "runner_sha256": common._sha256(Path(__file__)),
            "dependency_source_hashes": dependencies, "feature_receipts": feature_receipts, "parent_replay": parent_replay,
            "runtime_versions": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__, "sklearn": sibling.sklearn.__version__},
            "v0_artifact_hashes": frozen["hashes"], "parent_artifacts": contract["research_parent"], "pbp_receipts": pbp,
            "materialized_receipts": receipts, "source_manifest_sha256": common._sha256(source_root / "manifest.json"),
            "cohort_sha256": common._sha256(source_root / "cohort.csv"), **common.BOUNDARY_FLAGS})
        common.base._atomic_json(output / "pre_score_lock.json", {"task_id": TASK_ID,
            "generated_utc": datetime.now(timezone.utc).isoformat(), "controller_contract_sha256": CONTRACT_SHA256,
            "scientific_recipe": contract, "folds": frozen["folds"], "fit_budget": MODEL_FITS, "automatic_retries": 0,
            "thread_environment_contract": common.identity.THREAD_ENV_CONTRACT, **common.BOUNDARY_FLAGS})
        common.base._atomic_json(output / "exclusions.json", {"source_events": 195, "materialized_events": 193,
            "excluded_events": 2, "reconciles_to_source_denominator": True, "exclusions": exclusions})
        predictions, reports = sibling.fit_and_predict(rows, frozen["folds"], controls, parent,
            fit_predict=fit_unit, features=features, arm=ARM_CANDIDATE)
        check_hash = common._digest([list(item["row"].key) for item in predictions])
        if (len(predictions) != 87 or check_hash != common.frozen_v0.EXPECTED_CHECK_KEY_SHA256
                or tuple(item["fit_events"] for item in reports) != (106, 132, 148, 176)
                or tuple(item["check_events"] for item in reports) != (26, 16, 28, 17)
                or any(item["fit_label_unavailable_game_ids"] for item in reports)
                or any(item["trainer"]["primitive_prediction_state"]["freshness_normalization"] != parent_states[item["fold"]]["freshness_normalization"] for item in reports)):
            raise ValueError("unit-scale frozen chronology/counts/exact87 mask/C3 freshness parity changed")
        states = {"schema": "unit_scale_joint_numeric_prediction_states_v1", "task_id": TASK_ID,
            "folds": [{"fold": report["fold"], "state_sha256": report["trainer"]["predictor_state_sha256"],
                "state": report["trainer"].pop("primitive_prediction_state")} for report in reports]}
        common.base._atomic_json(output / "predictor_states.json", states)
        metrics, paired = shared.aggregate(predictions, ARM_CANDIDATE), shared.paired_evidence(predictions, ARM_CANDIDATE)
        scientific, operational, conditions = common.decision(metrics, reports, paired, ARM_CANDIDATE)
        diagnostics = {}
        for arm in (ARM_CANDIDATE, ARM_RESEARCH_PARENT):
            correction = [item[arm] - item[ARM_RAW] for item in predictions]
            energy = math.fsum(value * value for value in correction) / len(predictions)
            alignment = math.fsum(2 * value * (item[ARM_RAW] - item["row"].trusted["outcome"])
                for item, value in zip(predictions, correction, strict=True)) / len(predictions)
            diagnostics[arm] = {"equal_event_correction_energy": energy, "equal_event_signed_alignment": alignment,
                "equal_event_brier_delta_raw_identity": energy + alignment}
        scorecard = {"schema": "coevo_frozen_candidate_scorecard_v1", "task_id": TASK_ID, "candidate_arm": ARM_CANDIDATE,
            "actual_research_parent_arm": ARM_RESEARCH_PARENT, "actual_research_parent_id": native.TASK_ID,
            "scientific_decision": scientific, "operational_decision": operational, "decision_conditions": conditions,
            "model_fits": MODEL_FITS, "control_refits": 0, "source_denominator": {"events": 195, "dates": 42,
                "materialized_events": 193, "excluded_events": 2, "check_events": 87,
                "check_dates": len({item["row"].game_date for item in predictions}), "check_game_weeks": len({item["row"].game_week for item in predictions})},
            "identical_masks": {"all_controls_same_rows_labels_and_checkpoints": True, "check_key_sha256": check_hash, "matches_frozen_v0": True},
            "aggregate": metrics, "folds": reports, "paired_grouped_evidence": paired, "correction_diagnostics": diagnostics,
            "parent_replay": parent_replay, "all_four_freshness_normalizers_equal_c3": True,
            "unit_prior_question_annotation": annotate_question(metrics, reports, paired), "research_parent_sha256": NATIVE_SOURCE_SHA256,
            "comparison_incumbent_sha256": contract["comparison_incumbent_sha256"], "attribution": contract["recipe"]["attribution"],
            "inference_boundary": "repeatedly inspected opened-Train Discovery; historical event clock only", **common.BOUNDARY_FLAGS}
        shared.write_predictions(output / "predictions.csv", predictions, ARM_CANDIDATE)
        common.base._atomic_json(output / "scorecard.json", scorecard)
        manifest = {"schema": "coevo_frozen_candidate_manifest_v1", "complete": True, "task_id": TASK_ID,
            "completed_utc": datetime.now(timezone.utc).isoformat(), "source_events": 195,
            "materialized_events": 193, "excluded_events": 2, "check_events": 87, "model_fits": MODEL_FITS,
            "control_refits": 0, "automatic_retries": 0, "scientific_decision": scientific, "operational_decision": operational,
            **{f"{name}_sha256": common._sha256(output / f"{name}.{suffix}") for name, suffix in (
                ("pre_score_lock", "json"), ("input_receipts", "json"), ("exclusions", "json"),
                ("predictions", "csv"), ("scorecard", "json"), ("predictor_states", "json"))}, **common.BOUNDARY_FLAGS}
        common.base._atomic_json(output / "manifest.json", manifest)
        return manifest
    except Exception as error:
        common.base._atomic_json(output / "failure.json", {"task_id": TASK_ID, "error_type": type(error).__name__,
            "error": str(error)[:1200], "model_fits_maximum": MODEL_FITS, "automatic_retries": 0, **common.BOUNDARY_FLAGS})
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(common.settlement.json.dumps(run(args.source_root, args.output), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
