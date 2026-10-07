#!/usr/bin/env python3
"""One prior-to-market scalar temperature; repeated historical Train Discovery."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import math
from pathlib import Path
import platform

import numpy as np
from scipy.special import expit
from experiments import nfl_ingame_identity_blended_isotonic as parent_module

shared, common = parent_module.shared, parent_module.common
TASK_ID = "InGameMarketTemperatureOffset-v1"
ARM_CANDIDATE = "market_temperature_offset"
ARM_RESEARCH_PARENT = shared.ARM_RESEARCH_PARENT
ARM_RAW, ARM_ORDINARY, ARM_PARENT = shared.ARM_RAW, shared.ARM_ORDINARY, shared.ARM_PARENT
SOURCE_ROOT, V0_ARTIFACT_ROOT, MODEL_FITS, ALPHA = shared.SOURCE_ROOT, shared.V0_ARTIFACT_ROOT, 4, 16.
FEATURE_NAMES, LOWER_BOUND, MAX_STEPS, TOLERANCE = ["market_logit"], -1., 200, 1e-8
CONTRACT = Path(__file__).parents[1] / "supervisor_harness" / "COEVO_BATCH7_CONTRACT_2026-10-03.json"
CONTRACT_SHA256 = "f0d925977ef45677a557e2be18d6ec30ac56fe6fc8e9980df6a518a48b4b132b"
PARENT_SOURCE_SHA256 = "489d8268bd5243d94df9396f6dd5d616acfeab2d23f29d0e9e5903b7f156cce5"
EPSILON = common.probability_contract.DEFAULT_PROBABILITY_POLICY.epsilon


class FitFailure(ValueError):
    """Terminal numerical/output failure retaining its truthful partial receipt."""
    def __init__(self, message: str, receipt: dict):
        super().__init__(message)
        self.receipt = receipt


def require_dependencies() -> dict:
    dependencies = [(CONTRACT, CONTRACT_SHA256), (Path(parent_module.__file__), PARENT_SOURCE_SHA256),
        (Path(shared.__file__), parent_module.SHARED_SOURCE_SHA256), (Path(common.__file__), shared.COMMON_SOURCE_SHA256)]
    dependencies.extend((Path(module.__file__), digest) for module, digest in common.DEPENDENCIES.items())
    for path, expected in dependencies:
        if not path.is_file() or path.is_symlink() or common._sha256(path) != expected:
            raise ValueError(f"frozen temperature source/contract changed: {path.name}")
    common.identity._require_single_thread_environment()
    contract = common.settlement._strict_json(CONTRACT)
    recipe = contract["changed_training_recipe"]
    if (np.__version__ != "1.26.4" or shared.sklearn.__version__ != "1.6.1" or contract["candidate_id"] != TASK_ID
            or contract["research_parent"]["runner_sha256"] != PARENT_SOURCE_SHA256
            or contract["fixed_predictive_information"]["feature_names"] != FEATURE_NAMES
            or recipe["alpha"] != ALPHA or recipe["intercept"] != 0 or recipe["normalization"] != "none"
            or recipe["sample_weights"] is not None or recipe["fit_parameters"] != 1 or recipe["statistical_fits"] != MODEL_FITS):
        raise ValueError("frozen temperature recipe/runtime/actual-parent changed")
    return contract


def load_parent(contract: dict, controls: dict, frozen: dict) -> tuple[dict, dict]:
    parent = shared.load_parent_predictions(contract, controls, frozen)
    evidence, root = contract["research_parent"], Path(contract["research_parent"]["artifact_root"])
    manifest = common.settlement._strict_json(root / "manifest.json")
    names = {"manifest.json", "input_receipts.json", "pre_score_lock.json", "exclusions.json",
        "predictor_states.json", "scorecard.json", "predictions.csv"}
    if set(evidence["artifact_hashes"]) != names:
        raise ValueError("C1 parent requires exact seven-file receipt set")
    for filename, expected in evidence["artifact_hashes"].items():
        path, key = root / filename, filename.split(".")[0] + "_sha256"
        if (not path.is_file() or path.is_symlink() or common._sha256(path) != expected
                or evidence.get(key, expected) != expected
                or (filename != "manifest.json" and manifest.get(key) != expected)):
            raise ValueError(f"frozen C1 seven-file receipt changed: {filename}")
    receipts = common.settlement._strict_json(root / "input_receipts.json")
    lock = common.settlement._strict_json(root / "pre_score_lock.json")
    exclusions = common.settlement._strict_json(root / "exclusions.json")
    if (receipts["task_id"] != parent_module.TASK_ID or receipts["runner_sha256"] != PARENT_SOURCE_SHA256
            or receipts["controller_contract_sha256"] != parent_module.CONTRACT_SHA256
            or evidence["controller_contract_sha256"] != parent_module.CONTRACT_SHA256
            or lock["task_id"] != parent_module.TASK_ID or lock["controller_contract_sha256"] != parent_module.CONTRACT_SHA256
            or receipts["v0_artifact_hashes"] != frozen["hashes"] or receipts["pbp_receipts"] != frozen["receipts"]["pbp_receipts"]
            or common._digest(receipts["materialized_receipts"]) != common._digest(frozen["receipts"]["materialized_receipts"])
            or (exclusions["source_events"], exclusions["materialized_events"], exclusions["excluded_events"]) != (195, 193, 2)
            or [(item["game_id"], item["reason"]) for item in exclusions["exclusions"]] != common.identity.EXPECTED_EXCLUSIONS
            or any(receipts.get(key) != value for key, value in common.BOUNDARY_FLAGS.items())):
        raise ValueError("C1 source/causal receipts/exclusions/kernel binding changed")
    artifact = common.settlement._strict_json(root / "predictor_states.json")
    card = common.settlement._strict_json(root / "scorecard.json")
    reports = card["folds"]
    if (artifact["task_id"] != parent_module.TASK_ID or card["task_id"] != parent_module.TASK_ID
            or [item["fold"] for item in artifact["folds"]] != [1, 2, 3, 4]
            or len(reports) != 4 or len(evidence["state_sha256_by_fold"]) != 4):
        raise ValueError("C1 four-state task/coverage changed")
    states = {}
    for item, report, expected in zip(artifact["folds"], reports, evidence["state_sha256_by_fold"], strict=True):
        state, digest = item["state"], common._digest(item["state"])
        if (digest != expected or digest != item["state_sha256"] or report["fold"] != item["fold"]
                or report["trainer"]["predictor_state_sha256"] != digest or state["schema"] != evidence["state_schema"]
                or state["constructor_params"] != parent_module.ISOTONIC_PARAMS or state["blend_weight"] != parent_module.BLEND_WEIGHT
                or state["sample_weight"] is not None or state["fit_events"] != report["fit_events"]):
            raise ValueError("C1 canonical threshold state/recipe changed")
        parent_module.replay_isotonic(state, [.5])
        states[item["fold"]] = state
    return parent, states


def replay_parent(rows: list, folds: list, parent: dict, states: dict) -> dict:
    if len(folds) != 4 or set(states) != {1, 2, 3, 4}:
        raise ValueError("C1 parent replay requires four states")
    by_date = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    seen, receipts = set(), []
    for fold in folds:
        check = sorted([row for day in fold["check_dates"] for row in by_date.get(day, [])], key=lambda row: row.key)
        fit, unavailable = common.nested._strict_prior_rows(by_date, fold["fit_dates"], check)
        if unavailable or states[fold["fold"]]["fit_events"] != len(fit):
            raise ValueError("C1 replay past-label availability/fit count changed")
        raw = parent_module.raw_probabilities(check)
        values = parent_module.replay_isotonic(states[fold["fold"]], raw)
        if any(row.key in seen or row.key not in parent or value != parent[row.key]
                for row, value in zip(check, values, strict=True)):
            raise ValueError("C1 exact interpolation/common-mask replay differs")
        seen.update(row.key for row in check)
        receipts.append({"fold": fold["fold"], "state_sha256": common._digest(states[fold["fold"]]),
            "raw_check_sha256": common._digest(raw.tolist()), "parent_probability_rows_replayed": len(check), "parent_refits": 0})
    if len(seen) != 87 or seen != set(parent):
        raise ValueError("C1 exact87 parent replay coverage changed")
    return {"folds": receipts, "parent_rows_replayed": len(seen), "parent_refits": 0, "four_canonical_states_exact": True}


def objective_gradient_hessian(beta: float, logits: object, outcomes: object) -> tuple[float, float, float]:
    l, y = common._vector(logits, "fit market logits"), common._vector(outcomes, "fit binary outcomes")
    if not math.isfinite(beta) or beta < LOWER_BOUND or l.shape != y.shape or np.any((y != 0) & (y != 1)):
        raise ValueError("temperature objective requires finite beta>=-1/aligned binary outcomes")
    with np.errstate(over="raise", invalid="raise"):
        eta = (1 + beta) * l
        p = expit(eta)
        value = float(np.sum(np.logaddexp(0., eta) - y * eta) + .5 * ALPHA * beta * beta)
        gradient = float(np.sum((p - y) * l) + ALPHA * beta)
        hessian = float(np.sum(p * (1 - p) * l * l) + ALPHA)
    if not all(math.isfinite(v) for v in (value, gradient, hessian)) or hessian < ALPHA:
        raise ValueError("temperature objective/derivatives nonfinite or curvature<16")
    return value, gradient, hessian


def solve_temperature(logits: object, outcomes: object) -> tuple[float, dict]:
    receipt = {"model_fits": 1, "solver": "deterministic_constrained_scalar_bisection", "alpha": ALPHA,
        "lower_bound": LOWER_BOUND, "maximum_bisection_steps": MAX_STEPS, "tolerance": TOLERANCE,
        "optimization_calls_started": 1, "optimization_calls_completed": 0, "evaluations": 0,
        "bisection_steps": 0, "retry_count": 0, "fallback_count": 0,
        "count_semantics": "one solver function entry/valid return; evaluations count attempted F/g/h calls"}
    try:
        l, y = common._vector(logits, "fit market logits"), common._vector(outcomes, "fit binary outcomes")
        if l.shape != y.shape or np.any((y != 0) & (y != 1)):
            raise ValueError("temperature fit inputs/labels invalid")
        def evaluate(beta):
            receipt["evaluations"] += 1
            result = objective_gradient_hessian(beta, l, y)
            if len(result) != 3 or not all(math.isfinite(value) for value in result) or result[2] < ALPHA:
                raise ValueError("temperature evaluator returned invalid F/g/h")
            receipt["last_evaluation"] = {"beta": float(beta), "F": result[0], "gradient": result[1], "hessian": result[2]}
            return result
        upper = float(1 + math.fsum(abs(float(value)) for value in l) / ALPHA)
        if not math.isfinite(upper) or upper <= LOWER_BOUND:
            raise ValueError("temperature fit-only bracket is nonfinite")
        zero, _, _ = evaluate(0.)
        low, high = LOWER_BOUND, upper
        _, low_g, _ = evaluate(low)
        _, high_g, _ = evaluate(high)
        receipt.update({"initial_bracket": [low, high], "initial_bracket_gradients": [low_g, high_g], "F_zero": zero})
        receipt.update({"final_bracket": [low, high], "final_bracket_gradients": [low_g, high_g]})
        if high_g <= 0:
            raise ValueError("temperature upper bracket gradient is not positive")
        if low_g >= 0:
            beta = LOWER_BOUND
            receipt["boundary_solution"] = True
        else:
            beta = None
            receipt["boundary_solution"] = False
            for step in range(1, MAX_STEPS + 1):
                receipt["bisection_steps"] = step
                midpoint = float(low + (high - low) / 2)
                _, gradient, _ = evaluate(midpoint)
                if abs(gradient) <= TOLERANCE:
                    beta = midpoint
                    break
                if gradient > 0:
                    high, high_g = midpoint, gradient
                else:
                    low, low_g = midpoint, gradient
                receipt.update({"final_bracket": [low, high], "final_bracket_gradients": [low_g, high_g]})
            if beta is None:
                raise ValueError("temperature bisection exhausted200 without strict stationarity")
        receipt.update({"final_bracket": [low, high], "final_bracket_gradients": [low_g, high_g], "beta": beta})
        value, gradient, hessian = evaluate(beta)
        kkt = max(0., -gradient) if beta == LOWER_BOUND else abs(gradient)
        receipt.update({"F": value, "gradient": gradient, "hessian": hessian, "KKT": kkt})
        if beta < LOWER_BOUND or kkt > TOLERANCE or hessian < ALPHA or value > zero + TOLERANCE:
            raise ValueError("temperature independent KKT/curvature/objective check failed")
        receipt.update({"converged": True, "optimization_calls_completed": 1})
        return beta, receipt
    except Exception as error:
        receipt.update({"converged": False, "error_type": type(error).__name__, "error": str(error)[:600]})
        raise FitFailure(str(error), receipt) from error


def probabilities(beta: float, rows: list) -> tuple[list[float], dict]:
    raw = parent_module.raw_probabilities(rows)
    if not math.isfinite(beta) or beta < LOWER_BOUND:
        raise ValueError("temperature beta must be finite and>=-1")
    logits = np.asarray([row.market_features[0] for row in rows], dtype=np.float64)
    with np.errstate(over="raise", invalid="raise"):
        eta = (1 + beta) * logits
    if not np.isfinite(eta).all():
        raise ValueError("temperature predictor became nonfinite")
    unbounded = raw.copy() if beta == 0. else expit(eta)
    bounded = np.clip(unbounded, EPSILON, 1 - EPSILON)
    values = [common.probability_contract.validate_probability(float(value),
        common.probability_contract.DEFAULT_PROBABILITY_POLICY, ARM_CANDIDATE) for value in bounded]
    return values, {"clipped_rows": int(np.count_nonzero(bounded != unbounded)),
        "lower_clipped_rows": int(np.count_nonzero(unbounded < EPSILON)),
        "upper_clipped_rows": int(np.count_nonzero(unbounded > 1 - EPSILON)),
        "epsilon": EPSILON, "rows_removed": 0, "exact_zero_beta_identity": True}


def replay_predictor(state: dict, rows: list) -> tuple[list[float], dict]:
    beta = state["beta"]
    optimizer = state["optimizer"]
    if not all(math.isfinite(optimizer[key]) for key in ("beta", "F", "gradient", "hessian", "KKT", "F_zero")):
        raise ValueError("saved temperature optimizer receipt contains nonfinite primitives")
    expected_kkt = max(0., -optimizer["gradient"]) if beta == LOWER_BOUND else abs(optimizer["gradient"])
    if (state["schema"] != "market_temperature_offset_numeric_state_v1" or state["feature_columns"] != FEATURE_NAMES
            or state["temperature"] != 1 + beta or state["alpha"] != ALPHA or state["lower_bound"] != LOWER_BOUND
            or state["intercept"] != 0 or state["normalization"] != "none" or state["sample_weights"] is not None
            or state["optimizer"]["beta"] != beta or state["optimizer"]["converged"] is not True
            or optimizer["KKT"] != expected_kkt
            or state["optimizer"]["KKT"] > TOLERANCE or state["optimizer"]["hessian"] < ALPHA
            or state["optimizer"]["F"] > state["optimizer"]["F_zero"] + TOLERANCE):
        raise ValueError("saved temperature numeric state/recipe changed")
    raw = parent_module.raw_probabilities(rows)
    if state["raw_check_sha256"] != common._digest(raw.tolist()):
        raise ValueError("saved temperature check input hash changed")
    return probabilities(beta, rows)


def fit_temperature(fit: list, check: list, features: object = None) -> tuple[list[float], dict]:
    del features
    fit_raw, check_raw = parent_module.raw_probabilities(fit), parent_module.raw_probabilities(check)
    logits = np.asarray([row.market_features[0] for row in fit], dtype=np.float64)
    y = common._vector([row.trusted["outcome"] for row in fit], "past-fit labels")
    beta, receipt = solve_temperature(logits, y)
    try:
        if not math.isfinite(beta) or beta < LOWER_BOUND:
            raise ValueError("temperature solver returned invalid beta")
        state = {"schema": "market_temperature_offset_numeric_state_v1", "feature_columns": FEATURE_NAMES,
            "beta": beta, "temperature": 1 + beta, "alpha": ALPHA, "intercept": 0, "normalization": "none",
            "sample_weights": None, "lower_bound": LOWER_BOUND, "fit_events": len(fit),
            "raw_fit_sha256": common._digest(fit_raw.tolist()), "raw_check_sha256": common._digest(check_raw.tolist()),
            "fit_logit_sha256": common._digest(logits.tolist()), "optimizer": receipt}
        values, bounding = probabilities(beta, check)
        replayed, replay_bounds = replay_predictor(state, check)
        if values != replayed or bounding != replay_bounds:
            raise ValueError("temperature numeric predictor replay differs")
    except Exception as error:
        raise FitFailure(str(error), {**receipt, "post_optimization_prediction_error": str(error)[:600]}) from error
    return values, {"model_fits": 1, "fit_events": len(fit), "fit_parameters": 1, "input_columns": 1,
        "fit_only": True, "optimizer": receipt, "bounding": bounding, "numeric_replay_exact": True,
        "predictor_state_sha256": common._digest(state), "primitive_prediction_state": state}


def correction_diagnostics(predictions: list) -> dict:
    result = {}
    for arm in (ARM_CANDIDATE, ARM_RESEARCH_PARENT):
        corrections = [item[arm] - item[ARM_RAW] for item in predictions]
        energy = math.fsum(value * value for value in corrections) / len(predictions)
        alignment = math.fsum(2 * value * (item[ARM_RAW] - item["row"].trusted["outcome"])
            for item, value in zip(predictions, corrections, strict=True)) / len(predictions)
        result[arm] = {"equal_event_correction_energy": energy, "equal_event_signed_alignment": alignment,
            "equal_event_brier_delta_raw_identity": energy + alignment}
    return result


def correction_diagnostics_by_date(predictions: list) -> list:
    groups = defaultdict(list)
    for item in predictions:
        groups[item["row"].game_date].append(item)
    return [{"game_date": day, "events": len(block), "arms": correction_diagnostics(block)} for day, block in sorted(groups.items())]


def annotate_question(metrics: dict, reports: list, paired: dict, diagnostics: dict) -> dict:
    deltas = {name: metrics[ARM_CANDIDATE][name] - metrics[ARM_RESEARCH_PARENT][name] for name in ("brier", "log_loss")}
    wins = sum(item["arms"][ARM_CANDIDATE]["brier"] < item["arms"][ARM_RESEARCH_PARENT]["brier"] for item in reports)
    directional = all(value < 0 for value in deltas.values()) and wins >= 3
    evidence = paired[f"candidate_minus_{ARM_RESEARCH_PARENT}"]["brier"]
    return {"annotation_only_not_keep_judge": True, "candidate_minus_actual_parent": deltas, "parent_brier_block_wins": wins,
        "directional_calibration_evidence": directional, "stronger_local_evidence": directional and all(
            evidence[name]["interval_95"][1] < 0 for name in ("schedule_date_interval", "observed_game_week_interval")),
        "exact_recipe_question_failed": any(value >= 0 for value in deltas.values()),
        "repair_of_signed_alignment": diagnostics[ARM_CANDIDATE]["equal_event_signed_alignment"] < 0}


def run(source_root: Path, output: Path, *, allow_test_paths: bool = False) -> dict:
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    common.base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    output.mkdir(parents=True, exist_ok=False)
    progress = {"fit_calls_entered": 0, "fit_calls_completed": 0, "optimizer_receipts": [],
        "entry_semantics": "candidate fit function entry; valid completion includes numeric solve and output replay"}
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
            raise ValueError("temperature frozen195 denominator/exclusions/causal receipts changed")
        raw = parent_module.raw_probabilities(rows)
        parent_replay = replay_parent(rows, frozen["folds"], parent, parent_states)
        dependencies = {module.__name__: digest for module, digest in common.DEPENDENCIES.items()}
        dependencies.update({common.__name__: shared.COMMON_SOURCE_SHA256, shared.__name__: parent_module.SHARED_SOURCE_SHA256,
            parent_module.__name__: PARENT_SOURCE_SHA256})
        common.base._atomic_json(output / "input_receipts.json", {"task_id": TASK_ID,
            "controller_contract_sha256": CONTRACT_SHA256, "runner_sha256": common._sha256(Path(__file__)),
            "dependency_source_hashes": dependencies, "parent_replay": parent_replay,
            "raw_materialized_sha256": common._digest(raw.tolist()), "native_rows_validated": len(rows),
            "runtime_versions": {"python": platform.python_version(), "numpy": np.__version__,
                "scipy": parent_module.scipy.__version__, "sklearn": shared.sklearn.__version__},
            "v0_artifact_hashes": frozen["hashes"], "parent_artifacts": contract["research_parent"], "pbp_receipts": pbp,
            "materialized_receipts": receipts, "source_manifest_sha256": common._sha256(source_root / "manifest.json"),
            "cohort_sha256": common._sha256(source_root / "cohort.csv"), **common.BOUNDARY_FLAGS})
        common.base._atomic_json(output / "pre_score_lock.json", {"task_id": TASK_ID,
            "generated_utc": datetime.now(timezone.utc).isoformat(), "controller_contract_sha256": CONTRACT_SHA256,
            "scientific_recipe": contract, "folds": frozen["folds"], "fit_budget": MODEL_FITS, "automatic_retries": 0,
            "thread_environment_contract": common.identity.THREAD_ENV_CONTRACT, **common.BOUNDARY_FLAGS})
        common.base._atomic_json(output / "exclusions.json", {"source_events": 195, "materialized_events": 193,
            "excluded_events": 2, "reconciles_to_source_denominator": True, "exclusions": exclusions})
        def tracked_fit(fit, check, unused):
            progress["fit_calls_entered"] += 1
            try:
                values, trainer = fit_temperature(fit, check)
            except FitFailure as error:
                progress["optimizer_receipts"].append(error.receipt)
                common.base._atomic_json(output / "fit_progress.json", progress)
                raise
            progress["fit_calls_completed"] += 1
            progress["optimizer_receipts"].append(trainer["optimizer"])
            common.base._atomic_json(output / "fit_progress.json", progress)
            return values, trainer
        predictions, reports = parent_module.fit_and_predict(rows, frozen["folds"], controls, parent,
            fit_predict=tracked_fit, arm=ARM_CANDIDATE)
        for report in reports:
            report["correction_diagnostics"] = correction_diagnostics([item for item in predictions if item["fold"] == report["fold"]])
        check_hash = common._digest([list(item["row"].key) for item in predictions])
        if (len(predictions) != 87 or check_hash != common.frozen_v0.EXPECTED_CHECK_KEY_SHA256
                or tuple(item["fit_events"] for item in reports) != (106, 132, 148, 176)
                or tuple(item["check_events"] for item in reports) != (26, 16, 28, 17)
                or any(item["fit_label_unavailable_game_ids"] for item in reports) or progress["fit_calls_completed"] != MODEL_FITS):
            raise ValueError("temperature frozen chronology/counts/exact87 mask/fourfit ceiling changed")
        states = {"schema": "market_temperature_offset_numeric_states_v1", "task_id": TASK_ID,
            "folds": [{"fold": report["fold"], "state_sha256": report["trainer"]["predictor_state_sha256"],
                "state": report["trainer"].pop("primitive_prediction_state")} for report in reports]}
        common.base._atomic_json(output / "predictor_states.json", states)
        metrics, paired = shared.aggregate(predictions, ARM_CANDIDATE), shared.paired_evidence(predictions, ARM_CANDIDATE)
        scientific, operational, conditions = common.decision(metrics, reports, paired, ARM_CANDIDATE)
        diagnostics = correction_diagnostics(predictions)
        scorecard = {"schema": "coevo_frozen_candidate_scorecard_v1", "task_id": TASK_ID, "candidate_arm": ARM_CANDIDATE,
            "actual_research_parent_arm": ARM_RESEARCH_PARENT, "actual_research_parent_id": parent_module.TASK_ID,
            "scientific_decision": scientific, "operational_decision": operational, "decision_conditions": conditions,
            "model_fits": MODEL_FITS, "control_refits": 0, "feature_names": FEATURE_NAMES, "alpha": ALPHA,
            "clipped_check_rows": sum(item["trainer"]["bounding"]["clipped_rows"] for item in reports),
            "source_denominator": {"events": 195, "dates": 42, "materialized_events": 193, "excluded_events": 2, "check_events": 87,
                "check_dates": len({item["row"].game_date for item in predictions}), "check_game_weeks": len({item["row"].game_week for item in predictions})},
            "identical_masks": {"all_controls_same_rows_labels_and_checkpoints": True, "check_key_sha256": check_hash, "matches_frozen_v0": True},
            "aggregate": metrics, "folds": reports, "paired_grouped_evidence": paired, "correction_diagnostics": diagnostics,
            "per_schedule_date_correction_diagnostics": correction_diagnostics_by_date(predictions),
            "parent_replay": parent_replay, "calibration_question_annotation": annotate_question(metrics, reports, paired, diagnostics),
            "research_parent_sha256": PARENT_SOURCE_SHA256, "comparison_incumbent_sha256": contract["comparison_incumbent_sha256"],
            "attribution": contract["changed_training_recipe"]["attribution"],
            "training_loss_limit": "summed unweighted NLL with identity-centered prior; Brier judge unchanged",
            "inference_boundary": "repeatedly inspected Train Discovery; historical event clock only; no new information or H/R effect",
            **common.BOUNDARY_FLAGS}
        shared.write_predictions(output / "predictions.csv", predictions, ARM_CANDIDATE)
        common.base._atomic_json(output / "scorecard.json", scorecard)
        manifest = {"schema": "coevo_frozen_candidate_manifest_v1", "complete": True, "task_id": TASK_ID,
            "completed_utc": datetime.now(timezone.utc).isoformat(), "source_events": 195, "materialized_events": 193,
            "excluded_events": 2, "check_events": 87, "model_fits": MODEL_FITS, "control_refits": 0, "automatic_retries": 0,
            "scientific_decision": scientific, "operational_decision": operational,
            **{f"{name}_sha256": common._sha256(output / f"{name}.{suffix}") for name, suffix in (
                ("pre_score_lock", "json"), ("input_receipts", "json"), ("exclusions", "json"), ("fit_progress", "json"),
                ("predictions", "csv"), ("scorecard", "json"), ("predictor_states", "json"))}, **common.BOUNDARY_FLAGS}
        common.base._atomic_json(output / "manifest.json", manifest)
        return manifest
    except Exception as error:
        common.base._atomic_json(output / "failure.json", {"task_id": TASK_ID, "error_type": type(error).__name__,
            "error": str(error)[:1200], "model_fits_maximum": MODEL_FITS, "automatic_retries": 0, "fit_progress": progress,
            "optimizer_partial_receipt": getattr(error, "receipt", None), **common.BOUNDARY_FLAGS})
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(common.settlement.json.dumps(run(args.source_root, args.output), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
