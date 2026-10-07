#!/usr/bin/env python3
"""Frozen two-coordinate count/freshness offset; historical Train Discovery."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import platform

import numpy as np
import scipy
from scipy.special import expit

from experiments import nfl_ingame_prior_play_volume_offset as volume


sibling, common = volume.sibling, volume.common
shared = sibling.shared
TASK_ID = "InGamePriorPlayVolumeFreshnessJointOffset-v2"
ARM_CANDIDATE = "prior_play_volume_freshness_joint_offset"
ARM_SECONDARY = "frozen_a1_freshness_reference"
ARM_RESEARCH_PARENT = shared.ARM_RESEARCH_PARENT
ARM_RAW, ARM_ORDINARY, ARM_PARENT = shared.ARM_RAW, shared.ARM_ORDINARY, shared.ARM_PARENT
SOURCE_ROOT, V0_ARTIFACT_ROOT = shared.SOURCE_ROOT, shared.V0_ARTIFACT_ROOT
MODEL_FITS = 4
CONTRACT = Path(__file__).parents[1] / "supervisor_harness" / "COEVO_BATCH3_GENERATION2_CONTRACT_2026-10-03.json"
CONTRACT_SHA256 = "a8d6d35671ef3daf537067159b1b75ee79bada910ece9b0d114b973f74ae5a0c"
VOLUME_SOURCE_SHA256 = "45d1e7f2ef2de62102f115816db9d90e0249d169722700df3d5cc6000704c1ca"
COLUMNS = ["prior_play_volume_ratio", "fit_only_freshness_x_market_logit"]
FRESHNESS_FORMULA = "((causal_age_seconds-fit_age_mean)/fit_age_std_ddof0)*logit(p_raw)"


def require_dependencies() -> dict:
    sibling.require_dependencies(volume.TASK_ID)
    for path, expected in ((CONTRACT, CONTRACT_SHA256), (Path(volume.__file__), VOLUME_SOURCE_SHA256),
            (Path(sibling.__file__), volume.SIBLING_SOURCE_SHA256),
            (Path(volume.uncertainty.__file__), volume.UNCERTAINTY_SOURCE_SHA256)):
        if not path.is_file() or path.is_symlink() or common._sha256(path) != expected:
            raise ValueError(f"frozen joint-offset source/contract changed: {path.name}")
    contract = common.settlement._strict_json(CONTRACT)
    if (contract["candidate_id"] != TASK_ID or contract["recipe"]["column_order"] != COLUMNS
            or contract["recipe"]["penalty_per_coordinate"] != common.scaffold.PENALTY
            or contract["recipe"]["objective_source_sha256"] != common.DEPENDENCIES[common.scaffold]
            or contract["research_parent"]["runner_sha256"] != VOLUME_SOURCE_SHA256
            or contract["secondary_feature_provenance_and_control"]["runner_sha256"] != shared.COMMON_SOURCE_SHA256):
        raise ValueError("frozen joint-offset recipe/parent/objective source changed")
    return contract


def load_controls(contract: dict, controls: dict, frozen: dict) -> tuple[dict, dict]:
    parent = shared.load_parent_predictions(contract, controls, frozen)
    evidence = contract["research_parent"]
    root = Path(evidence["artifact_root"])
    manifest = common.settlement._strict_json(root / "manifest.json")
    for name in ("pre_score_lock", "predictor_states"):
        path = root / f"{name}.json"
        if (not path.is_file() or path.is_symlink() or common._sha256(path) != evidence[f"{name}_sha256"]
                or manifest.get(f"{name}_sha256") != evidence[f"{name}_sha256"]):
            raise ValueError(f"frozen C2 parent {name} hash/binding changed")
    states = common.settlement._strict_json(root / "predictor_states.json")
    reports = common.settlement._strict_json(root / "scorecard.json")["folds"]
    if states["task_id"] != evidence["candidate_id"] or [item["fold"] for item in states["folds"]] != [1, 2, 3, 4]:
        raise ValueError("frozen C2 parent numeric-state task/four-fold coverage changed")
    for item, report in zip(states["folds"], reports, strict=True):
        state, digest = item["state"], common._digest(item["state"])
        if (digest != item["state_sha256"] or report["fold"] != item["fold"]
                or report["trainer"]["predictor_state_sha256"] != digest
                or state["formula"] != volume.FORMULA or state["penalty"] != 16
                or not math.isfinite(state["beta"]) or state["market_coefficient"] != 1
                or state["intercept"] is not False or state["standardization"] != "none"):
            raise ValueError("frozen C2 parent canonical numeric state changed")
    secondary = shared.load_parent_predictions({"research_parent": contract["secondary_feature_provenance_and_control"]}, controls, frozen)
    return parent, secondary


def load_features(source_root: Path, frozen: dict, contract: dict, rows: list) -> tuple[dict, dict]:
    features, receipts = volume.load_features(source_root, frozen, contract, rows)
    if set(features) != {row.game_id for row in rows}:
        raise ValueError("joint-offset volume feature coverage changed")
    ages = [common.causal_age(row.source_receipt) for row in rows]
    return features, {**receipts, "causal_age_rows_validated": len(ages),
        "causal_age_seconds_sha256": common._digest(ages), "column_order": COLUMNS}


def joint_design(fit: list, check: list, features: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    sibling.raw_probabilities(fit)
    sibling.raw_probabilities(check)
    fit_freshness, check_freshness, normalizer = common.freshness_features(fit, check, states={})
    matrices = []
    for rows, freshness in ((fit, fit_freshness), (check, check_freshness)):
        ratios = common._vector([features[row.game_id] for row in rows], "volume ratios")
        matrix = np.column_stack((ratios, freshness))
        if (matrix.shape != (len(rows), 2) or not np.isfinite(matrix).all()
                or np.any(ratios <= -1) or np.any(ratios >= 1)):
            raise ValueError("joint offset requires finite, aligned, physically valid two-coordinate inputs")
        matrices.append(matrix)
    return matrices[0], matrices[1], normalizer


def probabilities(parameters: object, design: object, market_logits: object, raw: object) -> list[float]:
    theta = common._vector(parameters, "joint coefficients")
    raw = common._vector(raw, "raw market probabilities")
    offsets = common._vector(market_logits, "market logits")
    matrix = np.asarray(design, dtype=np.float64)
    common.identity._clipped_logits(raw)
    if (theta.shape != (2,) or matrix.shape != (len(raw), 2) or not np.isfinite(matrix).all()
            or offsets.shape != raw.shape
            or not np.array_equal(offsets, np.asarray([math.log(p / (1 - p)) for p in raw]))):
        raise ValueError("joint probability features/coefficients/offsets/raw are invalid or misaligned")
    if np.all(theta == 0.):
        return raw.tolist()
    return common.scaffold.candidate_probabilities(theta, matrix, offsets)


def replay_joint(state: dict, rows: list, features: dict) -> list[float]:
    normalizer = state["freshness_normalization"]
    mean, scale = normalizer["fit_age_mean"], normalizer["fit_age_std_ddof0"]
    if (state["column_order"] != COLUMNS or state["volume_formula"] != volume.FORMULA
            or state["freshness_formula"] != FRESHNESS_FORMULA or state["penalty_per_coordinate"] != 16
            or state["market_coefficient"] != 1 or state["intercept"] is not False
            or normalizer.get("fit_only") is not True or not math.isfinite(mean) or not 0 <= mean <= 300
            or not math.isfinite(scale) or scale <= 0):
        raise ValueError("joint-offset numeric state/fit-only normalizer changed")
    ratios = common._vector([features[row.game_id] for row in rows], "replay volume ratios")
    if np.any(ratios <= -1) or np.any(ratios >= 1):
        raise ValueError("joint-offset replay volume ratio bounds changed")
    ages = np.asarray([common.causal_age(row.source_receipt) for row in rows])
    logits = np.asarray([row.market_features[0] for row in rows])
    design = np.column_stack((ratios, (ages - mean) / scale * logits))
    return probabilities(state["coefficients"], design, logits, sibling.raw_probabilities(rows))


def fit_joint(fit: list, check: list, features: dict) -> tuple[list[float], dict]:
    design, check_design, normalizer = joint_design(fit, check, features)
    y = np.asarray([row.trusted["outcome"] for row in fit], dtype=np.float64)
    offsets = np.asarray([row.market_features[0] for row in fit])
    theta, optimizer = common.scaffold.fit_stratified_offset(design, y, offsets)
    theta = common._vector(theta, "fitted joint coefficients")
    if theta.shape != (2,):
        raise ValueError("joint optimizer returned wrong parameter shape")
    eta = offsets + design @ theta
    p = expit(eta)
    objective = float(np.sum(np.logaddexp(0., eta) - y * eta) + 8 * (theta @ theta))
    gradient = design.T @ (p - y) + 16 * theta
    hessian = design.T @ (design * (p * (1 - p))[:, None]) + 16 * np.eye(2)
    eigenvalues = np.linalg.eigvalsh(hessian)
    grad_inf = float(np.max(np.abs(gradient)))
    if (not optimizer["converged"] or optimizer["penalty"] != 16 or optimizer["retry_count"] != 0
            or optimizer["iterations"] > 50 or not math.isfinite(objective) or not np.isfinite(gradient).all()
            or not np.isfinite(hessian).all() or grad_inf > 1e-8 or np.min(eigenvalues) <= 0):
        raise ValueError("joint-offset fit failed finite stationarity/positive-definite Hessian")
    state = {"schema": "prior_play_volume_freshness_joint_numeric_state_v1", "column_order": COLUMNS,
        "volume_formula": volume.FORMULA, "freshness_formula": FRESHNESS_FORMULA,
        "coefficients": theta.tolist(), "freshness_normalization": normalizer,
        "market_coefficient": 1, "intercept": False, "penalty_per_coordinate": 16,
        "fit_events": len(fit), "fit_feature_sha256": common._digest(design.tolist()),
        "stationarity": {"objective": objective, "gradient": gradient.tolist(), "gradient_infinity_norm": grad_inf,
            "hessian": hessian.tolist(), "hessian_eigenvalues": eigenvalues.tolist()}}
    values = probabilities(theta, check_design, [row.market_features[0] for row in check], sibling.raw_probabilities(check))
    if values != replay_joint(state, check, features):
        raise ValueError("joint-offset primitive prediction replay differs")
    correlation = float(np.corrcoef(design, rowvar=False)[0, 1]) if np.all(design.std(axis=0) > 0) else None
    return values, {"model_fits": 1, "fit_events": len(fit), "input_columns": 2, "fit_only": True,
        "optimizer": optimizer, "legacy_beta_low_high_column_order": {"beta_low": COLUMNS[0], "beta_high": COLUMNS[1]},
        "fit_design_correlation": correlation, "predictor_state_sha256": common._digest(state),
        "primitive_prediction_state": state, "primitive_replay_exact": True,
        "bounding": {"clipped_rows": 0, "rows_removed": 0, "epsilon": sibling.EPSILON}}


def aggregate(predictions: list) -> dict:
    result = shared.aggregate(predictions, ARM_CANDIDATE)
    y, values = [item["row"].trusted["outcome"] for item in predictions], [item[ARM_SECONDARY] for item in predictions]
    result[ARM_SECONDARY] = common.settlement._simple_metrics(y, values)
    result[ARM_SECONDARY]["reliability_table"] = common.base._reliability_table(y, values)
    return result


def paired_evidence(predictions: list) -> dict:
    result = shared.paired_evidence(predictions, ARM_CANDIDATE)
    records = [{"game_date": item["row"].game_date, "game_week": item["row"].game_week,
        **{metric: common.identity._loss(item["row"].trusted["outcome"], item[ARM_CANDIDATE], metric)
            - common.identity._loss(item["row"].trusted["outcome"], item[ARM_SECONDARY], metric)
            for metric in ("brier", "log_loss")}} for item in predictions]
    result[f"candidate_minus_{ARM_SECONDARY}"] = {metric: {
        "delta_convention": "candidate minus frozen A1 secondary reference; negative loss is better; not a KEEP judge",
        "equal_event_mean": math.fsum(row[metric] for row in records) / len(records),
        "by_schedule_date": common.base._group_means(records, "game_date", metric),
        "schedule_date_interval": common.base._group_bootstrap(records, "game_date", metric, seed=20260929, replicates=10000),
        "observed_game_week_interval": common.base._group_bootstrap(records, "game_week", metric, seed=20260929, replicates=10000)
    } for metric in ("brier", "log_loss")}
    return result


def annotate_question(metrics: dict, reports: list, paired: dict) -> dict:
    comparisons = (ARM_RESEARCH_PARENT, ARM_SECONDARY)
    deltas = {arm: {name: metrics[ARM_CANDIDATE][name] - metrics[arm][name] for name in ("brier", "log_loss")}
        for arm in comparisons}
    wins = {arm: sum(item["arms"][ARM_CANDIDATE]["brier"] < item["arms"][arm]["brier"] for item in reports)
        for arm in comparisons}
    directional = all(value < 0 for losses in deltas.values() for value in losses.values()) and all(value >= 3 for value in wins.values())
    parent_evidence = paired[f"candidate_minus_{ARM_RESEARCH_PARENT}"]["brier"]
    stronger = directional and all(parent_evidence[name]["interval_95"][1] < 0
        for name in ("schedule_date_interval", "observed_game_week_interval"))
    return {"annotation_only_not_keep_judge": True, "candidate_minus_references": deltas, "brier_block_wins": wins,
        "directional_complementarity": directional, "stronger_local_evidence": stronger,
        "exact_recipe_question_failed": any(value > 0 for value in deltas[ARM_RESEARCH_PARENT].values())}


def write_predictions(path: Path, predictions: list) -> None:
    fields = ("fold", "game_id", "game_date", "game_week", "event_id", "market_id", "cutoff_ms",
        "outcome_available_ms", "outcome", "raw_market_probability", "frozen_v0_ordinary_market_only_probability",
        "frozen_v0_market_plus_state_parent_probability", "candidate_probability", "frozen_actual_parent_probability",
        "frozen_a1_secondary_reference_probability")
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in predictions:
            row = item["row"]
            writer.writerow(dict(zip(fields, [item["fold"], row.game_id, row.game_date, row.game_week,
                row.trusted["event_id"], row.trusted["market_id"], row.trusted["cutoff_ms"],
                row.trusted["outcome_available_ms"], row.trusted["outcome"], item[ARM_RAW], item[ARM_ORDINARY],
                item[ARM_PARENT], item[ARM_CANDIDATE], item[ARM_RESEARCH_PARENT], item[ARM_SECONDARY]], strict=True)))
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
        parent, secondary = load_controls(contract, controls, frozen)
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
            raise ValueError("joint-offset frozen195 denominator/exclusions/causal receipts changed")
        features, feature_receipts = load_features(source_root, frozen, contract, rows)
        dependencies = {module.__name__: digest for module, digest in common.DEPENDENCIES.items()}
        dependencies.update({common.__name__: shared.COMMON_SOURCE_SHA256, shared.__name__: sibling.SHARED_SOURCE_SHA256,
            sibling.__name__: volume.SIBLING_SOURCE_SHA256, volume.__name__: VOLUME_SOURCE_SHA256,
            volume.uncertainty.__name__: volume.UNCERTAINTY_SOURCE_SHA256})
        common.base._atomic_json(output / "input_receipts.json", {"task_id": TASK_ID,
            "controller_contract_sha256": CONTRACT_SHA256, "runner_sha256": common._sha256(Path(__file__)),
            "dependency_source_hashes": dependencies, "feature_receipts": feature_receipts,
            "runtime_versions": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__, "sklearn": sibling.sklearn.__version__},
            "v0_artifact_hashes": frozen["hashes"], "parent_artifacts": contract["research_parent"],
            "secondary_artifacts": contract["secondary_feature_provenance_and_control"], "pbp_receipts": pbp,
            "materialized_receipts": receipts, "source_manifest_sha256": common._sha256(source_root / "manifest.json"),
            "cohort_sha256": common._sha256(source_root / "cohort.csv"), **common.BOUNDARY_FLAGS})
        common.base._atomic_json(output / "pre_score_lock.json", {"task_id": TASK_ID,
            "generated_utc": datetime.now(timezone.utc).isoformat(), "controller_contract_sha256": CONTRACT_SHA256,
            "scientific_recipe": contract, "folds": frozen["folds"], "fit_budget": MODEL_FITS, "automatic_retries": 0,
            "thread_environment_contract": common.identity.THREAD_ENV_CONTRACT, **common.BOUNDARY_FLAGS})
        common.base._atomic_json(output / "exclusions.json", {"source_events": 195, "materialized_events": 193,
            "excluded_events": 2, "reconciles_to_source_denominator": True, "exclusions": exclusions})
        predictions, reports = sibling.fit_and_predict(rows, frozen["folds"], controls, parent,
            fit_predict=fit_joint, features=features, arm=ARM_CANDIDATE)
        if set(secondary) != set(controls):
            raise ValueError("joint-offset A1 secondary common mask changed")
        for item in predictions:
            item[ARM_SECONDARY] = secondary[item["row"].key]
        for report in reports:
            report["arms"] = aggregate([item for item in predictions if item["fold"] == report["fold"]])
            report["candidate_minus_secondary_reference"] = {name: report["arms"][ARM_CANDIDATE][name]
                - report["arms"][ARM_SECONDARY][name] for name in ("brier", "log_loss")}
        check_hash = common._digest([list(item["row"].key) for item in predictions])
        if (len(predictions) != 87 or check_hash != common.frozen_v0.EXPECTED_CHECK_KEY_SHA256
                or tuple(item["fit_events"] for item in reports) != (106, 132, 148, 176)
                or tuple(item["check_events"] for item in reports) != (26, 16, 28, 17)
                or any(item["fit_label_unavailable_game_ids"] for item in reports)):
            raise ValueError("joint-offset frozen chronology/counts/exact87 mask changed")
        states = {"schema": "joint_offset_numeric_prediction_states_v1", "task_id": TASK_ID,
            "folds": [{"fold": report["fold"], "state_sha256": report["trainer"]["predictor_state_sha256"],
                "state": report["trainer"].pop("primitive_prediction_state")} for report in reports]}
        common.base._atomic_json(output / "predictor_states.json", states)
        metrics, paired = aggregate(predictions), paired_evidence(predictions)
        scientific, operational, conditions = common.decision(metrics, reports, paired, ARM_CANDIDATE)
        diagnostics = {}
        for arm in (ARM_CANDIDATE, ARM_RESEARCH_PARENT, ARM_SECONDARY):
            corrections = [item[arm] - item[ARM_RAW] for item in predictions]
            energy = math.fsum(value * value for value in corrections) / len(predictions)
            alignment = math.fsum(2 * value * (item[ARM_RAW] - item["row"].trusted["outcome"])
                for item, value in zip(predictions, corrections, strict=True)) / len(predictions)
            diagnostics[arm] = {"equal_event_correction_energy": energy, "equal_event_signed_alignment": alignment,
                "equal_event_brier_delta_raw_identity": energy + alignment}
        scorecard = {"schema": "coevo_frozen_candidate_scorecard_v1", "task_id": TASK_ID, "candidate_arm": ARM_CANDIDATE,
            "actual_research_parent_arm": ARM_RESEARCH_PARENT, "actual_research_parent_id": contract["research_parent"]["candidate_id"],
            "secondary_reference_arm": ARM_SECONDARY, "secondary_reference_id": contract["secondary_feature_provenance_and_control"]["candidate_id"],
            "scientific_decision": scientific, "operational_decision": operational, "decision_conditions": conditions,
            "model_fits": MODEL_FITS, "control_refits": 0, "source_denominator": {"events": 195, "dates": 42,
                "materialized_events": 193, "excluded_events": 2, "check_events": 87,
                "check_dates": len({item["row"].game_date for item in predictions}), "check_game_weeks": len({item["row"].game_week for item in predictions})},
            "identical_masks": {"all_controls_same_rows_labels_and_checkpoints": True, "check_key_sha256": check_hash, "matches_frozen_v0": True},
            "aggregate": metrics, "folds": reports, "paired_grouped_evidence": paired, "correction_diagnostics": diagnostics,
            "conditional_question_annotation": annotate_question(metrics, reports, paired),
            "research_parent_sha256": VOLUME_SOURCE_SHA256, "comparison_incumbent_sha256": contract["comparison_incumbent_sha256"],
            "attribution": contract["recipe"]["attribution"], "inference_boundary": "repeatedly inspected opened-Train Discovery; historical event clock only", **common.BOUNDARY_FLAGS}
        write_predictions(output / "predictions.csv", predictions)
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
