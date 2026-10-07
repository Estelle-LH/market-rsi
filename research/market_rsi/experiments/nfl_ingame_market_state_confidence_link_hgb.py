#!/usr/bin/env python3
"""Frozen state residual trees with a confidence-linked probability output."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import math
from pathlib import Path

import numpy as np
from scipy.special import expit

from experiments import nfl_ingame_market_residual_hgb as shared


TASK_ID = "InGameMarketStateConfidenceLinkHGB-v2"
ARM_CANDIDATE = "market_state_confidence_link_hgb"
ARM_RESEARCH_PARENT = shared.ARM_RESEARCH_PARENT
ARM_RAW, ARM_ORDINARY, ARM_PARENT = shared.ARM_RAW, shared.ARM_ORDINARY, shared.ARM_PARENT
SOURCE_ROOT, V0_ARTIFACT_ROOT = shared.SOURCE_ROOT, shared.V0_ARTIFACT_ROOT
MODEL_FITS, FACTOR = 4, 4.0
CONTRACT = Path(__file__).parents[1] / "supervisor_harness" / "COEVO_HGB_GENERATION2_CONTRACT_2026-10-03.json"
CONTRACT_SHA256 = "1676d24e3815f50cc65692320eda833007f4e6df6ea95238fcd820153b183414"
SHARED_SOURCE_SHA256 = "a17220dea91373b73c3f2e3a5d6e36f2b3e1b2866c8714cdc292dd921aefad79"


def require_dependencies() -> dict:
    shared.require_dependencies("InGameMarketStateResidualHGB-v1")
    for path, digest in ((CONTRACT, CONTRACT_SHA256), (Path(shared.__file__), SHARED_SOURCE_SHA256)):
        if not path.is_file() or path.is_symlink() or shared.common._sha256(path) != digest:
            raise ValueError(f"frozen confidence-link source/contract changed: {path.name}")
    contract = shared.common.settlement._strict_json(CONTRACT)
    parent_source = Path(__file__).with_name("nfl_ingame_market_state_residual_hgb.py")
    if (contract["candidate_id"] != TASK_ID or contract["changed_output_recipe"]["factor"] != FACTOR
            or parent_source.is_symlink() or shared.common._sha256(parent_source) != contract["research_parent"]["runner_sha256"]):
        raise ValueError("frozen confidence-link recipe/actual-parent source changed")
    return contract


def link_probabilities(raw: object, residual: object) -> tuple[list[float], dict]:
    raw = shared.common._vector(raw, "raw market probability")
    residual = shared.common._vector(residual, "finite pre-link residual")
    shared.common.identity._clipped_logits(raw)
    if raw.shape != residual.shape:
        raise ValueError("confidence-link residual/raw vectors are misaligned")
    offsets = np.asarray([math.log(value / (1 - value)) for value in raw])
    with np.errstate(over="raise", invalid="raise"):
        eta = offsets + FACTOR * residual
    if not np.isfinite(eta).all():
        raise FloatingPointError("confidence-link linear predictor is nonfinite")
    unbounded = expit(eta)
    unbounded[residual == 0.] = raw[residual == 0.]
    epsilon = shared.common.probability_contract.DEFAULT_PROBABILITY_POLICY.epsilon
    bounded = np.clip(unbounded, epsilon, 1 - epsilon)
    probabilities = [shared.common.probability_contract.validate_probability(float(value),
        shared.common.probability_contract.DEFAULT_PROBABILITY_POLICY, ARM_CANDIDATE) for value in bounded]
    return probabilities, {"clipped_rows": int(np.count_nonzero(bounded != unbounded)),
        "lower_clipped_rows": int(np.count_nonzero(unbounded < epsilon)),
        "upper_clipped_rows": int(np.count_nonzero(unbounded > 1 - epsilon)),
        "epsilon": epsilon, "rows_removed": 0, "exact_zero_residual_identity": True, "factor": FACTOR}


def load_parent(contract: dict, controls: dict, frozen: dict) -> tuple[dict, dict]:
    evidence = contract["research_parent"]
    probabilities = shared.load_parent_predictions({"research_parent": evidence}, controls, frozen)
    root = Path(evidence["artifact_root"])
    manifest = shared.common.settlement._strict_json(root / "manifest.json")
    for name in ("pre_score_lock", "predictor_states"):
        path = root / f"{name}.json"
        expected = evidence[f"{name}_sha256"]
        if (not path.is_file() or path.is_symlink() or shared.common._sha256(path) != expected
                or manifest.get(f"{name}_sha256") != expected):
            raise ValueError(f"frozen B2 parent {name} hash/binding changed")
    artifact = shared.common.settlement._strict_json(root / "predictor_states.json")
    reports = shared.common.settlement._strict_json(root / "scorecard.json")["folds"]
    states = {}
    for item in artifact["folds"]:
        number, state = item["fold"], item["state"]
        digest = shared.common._digest(state)
        if (number not in (1, 2, 3, 4) or number in states or digest != item["state_sha256"]
                or state["feature_names"] != contract["fixed_training_recipe"]["feature_names"]
                or state["constructor_params"] != shared.HGB_PARAMS or state["stage_count"] != 64
                or len(state["trees"]) != 64 or not state["leaf_values_include_learning_rate"]
                or reports[number - 1]["fold"] != number
                or reports[number - 1]["trainer"]["predictor_state_sha256"] != digest):
            raise ValueError("frozen B2 four canonical predictor states changed")
        states[number] = state
    if set(states) != {1, 2, 3, 4} or artifact["task_id"] != evidence["candidate_id"]:
        raise ValueError("frozen B2 predictor-state fold/task coverage changed")
    return probabilities, states


def correction_diagnostics(predictions: list) -> dict:
    result = {}
    for arm in (ARM_CANDIDATE, ARM_RESEARCH_PARENT):
        corrections = [item[arm] - item[ARM_RAW] for item in predictions]
        energy = math.fsum(value * value for value in corrections) / len(predictions)
        alignment = math.fsum(2 * correction * (item[ARM_RAW] - item["row"].trusted["outcome"])
            for item, correction in zip(predictions, corrections, strict=True)) / len(predictions)
        result[arm] = {"equal_event_correction_energy": energy, "equal_event_signed_alignment": alignment,
            "equal_event_brier_delta_raw_identity": energy + alignment}
    return result


def fit_and_predict(rows: list, folds: list, controls: dict, parent: dict, parent_states: dict) -> tuple[list, list]:
    by_date = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    predictions, reports = [], []
    for fold in folds:
        check = sorted([row for day in fold["check_dates"] for row in by_date.get(day, [])], key=lambda row: row.key)
        fit, unavailable = shared.common.nested._strict_prior_rows(by_date, fold["fit_dates"], check)
        for row in check:
            frozen = controls.get(row.key)
            if (frozen is None or row.key not in parent or frozen["fold"] != fold["fold"]
                    or frozen["game_id"] != row.game_id or frozen["game_date"] != row.game_date
                    or frozen["game_week"] != row.game_week or frozen["outcome"] != row.trusted["outcome"]
                    or frozen[ARM_RAW] != row.trusted["market_probability"]):
                raise ValueError("confidence-link row differs from frozen B2/v0 key/identity/label")
        old_probabilities, trainer = shared.fit_hgb_residual(fit, check, include_state=True)
        state = trainer["primitive_prediction_state"]
        frozen_state = parent_states[fold["fold"]]
        if shared.common._digest(state) != shared.common._digest(frozen_state):
            raise ValueError("confidence-link fit differs from frozen B2 canonical state")
        matrix = shared.feature_matrix(check, include_state=True)
        residual = shared.predict_primitive(state, matrix)
        parent_residual = shared.predict_primitive(frozen_state, matrix)
        frozen_probabilities = [parent[row.key] for row in check]
        if not np.array_equal(residual, parent_residual) or old_probabilities != frozen_probabilities:
            raise ValueError("confidence-link pre-link residual or B2 parent probability parity failed")
        values, bounding = link_probabilities([row.trusted["market_probability"] for row in check], residual)
        trainer = {**trainer, "parent_additive_bounding": trainer["bounding"], "bounding": bounding,
            "frozen_b2_predictor_state_sha256": shared.common._digest(frozen_state),
            "canonical_b2_state_exact": True, "prelink_residual_exact": True,
            "old_b2_probability_exact": True, "prelink_rows_checked": len(check)}
        block = [{"fold": fold["fold"], "row": row, "feature": 0., "prelink_residual": float(f),
            ARM_RAW: row.trusted["market_probability"], ARM_ORDINARY: controls[row.key][ARM_ORDINARY],
            ARM_PARENT: controls[row.key][ARM_PARENT], ARM_RESEARCH_PARENT: parent[row.key], ARM_CANDIDATE: probability}
            for row, probability, f in zip(check, values, residual, strict=True)]
        metrics = shared.aggregate(block, ARM_CANDIDATE)
        reports.append({"fold": fold["fold"], "fit_dates": list(fold["fit_dates"]), "check_dates": list(fold["check_dates"]),
            "fit_events": len(fit), "check_events": len(check), "fit_label_unavailable_game_ids": unavailable,
            "trainer": trainer, "arms": metrics, "same_rows_labels_and_checkpoints": True,
            "correction_diagnostics": correction_diagnostics(block),
            "candidate_minus_actual_parent": {metric: metrics[ARM_CANDIDATE][metric] - metrics[ARM_RESEARCH_PARENT][metric]
                for metric in ("brier", "log_loss")}})
        predictions.extend(block)
    keys = [item["row"].key for item in predictions]
    if len(reports) != 4 or len(keys) != len(set(keys)) or set(keys) != set(controls) or set(keys) != set(parent):
        raise ValueError("confidence-link four fits or frozen B2 common mask changed")
    return predictions, reports


def run(source_root: Path, output: Path, *, allow_test_paths: bool = False) -> dict:
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    shared.common.base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    output.mkdir(parents=True, exist_ok=False)
    try:
        contract = require_dependencies()
        frozen = shared.common.frozen_v0._validate_v0_artifact(V0_ARTIFACT_ROOT)
        controls = shared.common.identity._frozen_controls(frozen)
        parent, parent_states = load_parent(contract, controls, frozen)
        cohort = shared.common.base._validate_source(source_root, expected_events=195, expected_dates=42, allow_test_paths=allow_test_paths)
        pbp = shared.common.base._validate_pbp_receipts(source_root, cohort)
        if pbp != frozen["receipts"]["pbp_receipts"]:
            raise ValueError("opened-Train PBP receipts differ from frozen v0")
        states = {row["game_id"]: row for row in frozen["anchors"]}
        rows, exclusions = [], []
        for ordinal, item in enumerate(cohort):
            try:
                rows.append(shared.common.base._load_dynamic_market(source_root, item, states[item["game_id"]]))
            except shared.common.settlement.EventExclusion as error:
                exclusions.append({"source_ordinal": ordinal, "game_id": item["game_id"], "game_date": item["game_date"],
                    "reason": error.code, "detail": str(error)[:400]})
        rows.sort(key=lambda row: row.key)
        receipts = [row.source_receipt for row in rows]
        if (len(rows) != 193 or len(rows) + len(exclusions) != 195
                or [(item["game_id"], item["reason"]) for item in exclusions] != shared.common.identity.EXPECTED_EXCLUSIONS
                or shared.common._digest(receipts) != shared.common._digest(frozen["receipts"]["materialized_receipts"])):
            raise ValueError("confidence-link frozen195 denominator/exclusions/causal receipts changed")
        shared.feature_matrix(rows, include_state=True)
        shared.common.base._atomic_json(output / "input_receipts.json", {"task_id": TASK_ID,
            "controller_contract_sha256": CONTRACT_SHA256, "runner_sha256": shared.common._sha256(Path(__file__)),
            "shared_hgb_source_sha256": SHARED_SOURCE_SHA256, "frozen_common_source_sha256": shared.COMMON_SOURCE_SHA256,
            "dependency_source_hashes": {module.__name__: digest for module, digest in shared.common.DEPENDENCIES.items()},
            "v0_artifact_hashes": frozen["hashes"], "parent_artifacts": contract["research_parent"], "pbp_receipts": pbp,
            "materialized_receipts": receipts, "source_manifest_sha256": shared.common._sha256(source_root / "manifest.json"),
            "cohort_sha256": shared.common._sha256(source_root / "cohort.csv"), **shared.common.BOUNDARY_FLAGS})
        shared.common.base._atomic_json(output / "pre_score_lock.json", {"task_id": TASK_ID,
            "generated_utc": datetime.now(timezone.utc).isoformat(), "controller_contract_sha256": CONTRACT_SHA256,
            "scientific_recipe": contract, "folds": frozen["folds"], "fit_budget": 4, "automatic_retries": 0,
            "thread_environment_contract": shared.common.identity.THREAD_ENV_CONTRACT, **shared.common.BOUNDARY_FLAGS})
        shared.common.base._atomic_json(output / "exclusions.json", {"source_events": 195, "materialized_events": 193,
            "excluded_events": 2, "reconciles_to_source_denominator": True, "exclusions": exclusions})
        predictions, reports = fit_and_predict(rows, frozen["folds"], controls, parent, parent_states)
        check_hash = shared.common._digest([list(item["row"].key) for item in predictions])
        if (len(predictions) != 87 or check_hash != shared.common.frozen_v0.EXPECTED_CHECK_KEY_SHA256
                or tuple(item["fit_events"] for item in reports) != (106, 132, 148, 176)
                or tuple(item["check_events"] for item in reports) != (26, 16, 28, 17)
                or any(item["fit_label_unavailable_game_ids"] for item in reports)):
            raise ValueError("confidence-link frozen chronology, fit counts or exact87 mask changed")
        predictor_states = {"schema": "hgb_numeric_prediction_states_v1", "task_id": TASK_ID,
            "folds": [{"fold": report["fold"], "state_sha256": report["trainer"]["predictor_state_sha256"],
                "state": report["trainer"].pop("primitive_prediction_state")} for report in reports]}
        shared.common.base._atomic_json(output / "predictor_states.json", predictor_states)
        metrics, paired = shared.aggregate(predictions, ARM_CANDIDATE), shared.paired_evidence(predictions, ARM_CANDIDATE)
        scientific, operational, conditions = shared.common.decision(metrics, reports, paired, ARM_CANDIDATE)
        scorecard = {"schema": "coevo_frozen_candidate_scorecard_v1", "task_id": TASK_ID, "candidate_arm": ARM_CANDIDATE,
            "actual_research_parent_arm": ARM_RESEARCH_PARENT, "actual_research_parent_id": contract["research_parent"]["candidate_id"],
            "scientific_decision": scientific, "operational_decision": operational, "decision_conditions": conditions,
            "model_fits": 4, "control_refits": 0, "constructor_params": shared.HGB_PARAMS,
            "feature_names": contract["fixed_training_recipe"]["feature_names"],
            "clipped_check_rows": sum(item["trainer"]["bounding"]["clipped_rows"] for item in reports),
            "source_denominator": {"events": 195, "dates": 42, "materialized_events": 193, "excluded_events": 2,
                "check_events": 87, "check_dates": len({item["row"].game_date for item in predictions}),
                "check_game_weeks": len({item["row"].game_week for item in predictions})},
            "identical_masks": {"all_four_arms_same_rows_labels_and_checkpoints": True, "actual_parent_same_rows": True,
                "check_key_sha256": check_hash, "matches_frozen_v0": True},
            "parent_parity": {"four_canonical_states_exact": True, "prelink_rows_exact": len(predictions),
                "old_b2_probability_rows_exact": len(predictions)},
            "aggregate": metrics, "folds": reports, "paired_grouped_evidence": paired,
            "correction_diagnostics": correction_diagnostics(predictions),
            "research_parent_sha256": contract["research_parent"]["runner_sha256"],
            "comparison_incumbent_sha256": contract["comparison_incumbent_sha256"],
            "attribution": "C output link only after exact four-state and87 pre-link parity",
            "training_loss_limit": "unchanged residual squared-error does not optimize linked Brier directly",
            "inference_boundary": "repeatedly inspected opened-Train Discovery; historical event clock only", **shared.common.BOUNDARY_FLAGS}
        shared.write_predictions(output / "predictions.csv", predictions, ARM_CANDIDATE)
        shared.common.base._atomic_json(output / "prelink_residuals.json", {"task_id": TASK_ID,
            "rows": [{"key": list(item["row"].key), "fold": item["fold"], "residual": item["prelink_residual"]} for item in predictions]})
        shared.common.base._atomic_json(output / "scorecard.json", scorecard)
        manifest = {"schema": "coevo_frozen_candidate_manifest_v1", "complete": True, "task_id": TASK_ID,
            "completed_utc": datetime.now(timezone.utc).isoformat(), "source_events": 195,
            "materialized_events": 193, "excluded_events": 2, "check_events": 87,
            "model_fits": 4, "control_refits": 0, "automatic_retries": 0,
            "scientific_decision": scientific, "operational_decision": operational,
            **{f"{name}_sha256": shared.common._sha256(output / f"{name}.{suffix}") for name, suffix in (
                ("pre_score_lock", "json"), ("input_receipts", "json"), ("exclusions", "json"),
                ("predictions", "csv"), ("scorecard", "json"), ("predictor_states", "json"),
                ("prelink_residuals", "json"))}, **shared.common.BOUNDARY_FLAGS}
        shared.common.base._atomic_json(output / "manifest.json", manifest)
        return manifest
    except Exception as error:
        shared.common.base._atomic_json(output / "failure.json", {"task_id": TASK_ID,
            "error_type": type(error).__name__, "error": str(error)[:1200], "model_fits_maximum": 4,
            "automatic_retries": 0, **shared.common.BOUNDARY_FLAGS})
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(shared.common.settlement.json.dumps(run(args.source_root, args.output), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
