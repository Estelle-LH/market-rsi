#!/usr/bin/env python3
"""Fixed fit-only linear residual ridge on B3 information/link; Train Discovery."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import math
from pathlib import Path
import platform

import numpy as np
from experiments import nfl_ingame_market_state_confidence_link_hgb as parent_module
from experiments import nfl_ingame_identity_blended_isotonic as sibling

shared, common = parent_module.shared, parent_module.shared.common
TASK_ID = "InGameMarketStateRidgeResidualLink-v1"
ARM_CANDIDATE = "market_state_ridge_residual_link"
ARM_RESEARCH_PARENT = shared.ARM_RESEARCH_PARENT
ARM_RAW, ARM_ORDINARY, ARM_PARENT = shared.ARM_RAW, shared.ARM_ORDINARY, shared.ARM_PARENT
SOURCE_ROOT, V0_ARTIFACT_ROOT, MODEL_FITS, ALPHA = shared.SOURCE_ROOT, shared.V0_ARTIFACT_ROOT, 4, 16.
CONTRACT = Path(__file__).parents[1] / "supervisor_harness" / "COEVO_BATCH6_CONTRACT_2026-10-03.json"
CONTRACT_SHA256 = "dc6b34a1ef0dadb744345bc34d7c200088c637c01e4fe73b80ec05ef1119d753"
PARENT_SOURCE_SHA256 = "376b34c656e5a70666e8863b507f518675858011c3da6530cf592a0e192957fe"
SIBLING_SOURCE_SHA256 = "489d8268bd5243d94df9396f6dd5d616acfeab2d23f29d0e9e5903b7f156cce5"
FEATURE_NAMES = ["market_logit", "market_staleness_seconds"] + list(common.base.STATE_FEATURE_NAMES)


class FitFailure(ValueError):
    """Terminal fit/output failure preserving the truthful partial solve receipt."""
    def __init__(self, message: str, receipt: dict):
        super().__init__(message)
        self.receipt = receipt


def require_dependencies() -> dict:
    parent_module.require_dependencies()
    for path, expected in ((CONTRACT, CONTRACT_SHA256), (Path(parent_module.__file__), PARENT_SOURCE_SHA256),
            (Path(sibling.__file__), SIBLING_SOURCE_SHA256)):
        if not path.is_file() or path.is_symlink() or common._sha256(path) != expected:
            raise ValueError(f"frozen ridge source/contract changed: {path.name}")
    contract = common.settlement._strict_json(CONTRACT)
    if (np.__version__ != "1.26.4" or contract["candidate_id"] != TASK_ID
            or contract["research_parent"]["runner_sha256"] != PARENT_SOURCE_SHA256
            or contract["fixed_information_and_output"]["feature_names"] != FEATURE_NAMES
            or contract["changed_training_recipe"]["alpha"] != ALPHA
            or contract["changed_training_recipe"]["output_factor"] != parent_module.FACTOR
            or contract["changed_training_recipe"]["statistical_fits"] != MODEL_FITS):
        raise ValueError("frozen ridge recipe/runtime/actual-parent changed")
    return contract


def load_parent(contract: dict, controls: dict, frozen: dict) -> tuple[dict, dict, dict]:
    probabilities = shared.load_parent_predictions(contract, controls, frozen)
    evidence, root = contract["research_parent"], Path(contract["research_parent"]["artifact_root"])
    manifest = common.settlement._strict_json(root / "manifest.json")
    names = {"manifest.json", "input_receipts.json", "pre_score_lock.json", "exclusions.json",
        "predictor_states.json", "prelink_residuals.json", "scorecard.json", "predictions.csv"}
    if set(evidence["artifact_hashes"]) != names:
        raise ValueError("B3 parent requires exact eight-file receipt set")
    for filename, expected in evidence["artifact_hashes"].items():
        path, key = root / filename, filename.split(".")[0] + "_sha256"
        if (not path.is_file() or path.is_symlink() or common._sha256(path) != expected
                or evidence.get(key, expected) != expected
                or (filename != "manifest.json" and manifest.get(key) != expected)):
            raise ValueError(f"frozen B3 eight-file receipt changed: {filename}")
    receipts = common.settlement._strict_json(root / "input_receipts.json")
    lock = common.settlement._strict_json(root / "pre_score_lock.json")
    exclusions = common.settlement._strict_json(root / "exclusions.json")
    if (receipts["runner_sha256"] != PARENT_SOURCE_SHA256
            or receipts["controller_contract_sha256"] != parent_module.CONTRACT_SHA256
            or evidence["controller_contract_sha256"] != parent_module.CONTRACT_SHA256
            or lock["task_id"] != parent_module.TASK_ID or lock["controller_contract_sha256"] != parent_module.CONTRACT_SHA256
            or receipts["v0_artifact_hashes"] != frozen["hashes"] or receipts["pbp_receipts"] != frozen["receipts"]["pbp_receipts"]
            or common._digest(receipts["materialized_receipts"]) != common._digest(frozen["receipts"]["materialized_receipts"])
            or (exclusions["source_events"], exclusions["materialized_events"], exclusions["excluded_events"]) != (195, 193, 2)
            or [(item["game_id"], item["reason"]) for item in exclusions["exclusions"]] != common.identity.EXPECTED_EXCLUSIONS
            or any(receipts.get(key) != value for key, value in common.BOUNDARY_FLAGS.items())):
        raise ValueError("B3 source/causal receipts/exclusion/kernel binding changed")
    artifact = common.settlement._strict_json(root / "predictor_states.json")
    reports = common.settlement._strict_json(root / "scorecard.json")["folds"]
    if (artifact["task_id"] != parent_module.TASK_ID or [item["fold"] for item in artifact["folds"]] != [1, 2, 3, 4]
            or len(reports) != 4 or len(evidence["state_sha256_by_fold"]) != 4):
        raise ValueError("B3 canonical four-state task/coverage changed")
    states = {}
    for item, report, expected in zip(artifact["folds"], reports, evidence["state_sha256_by_fold"], strict=True):
        state, digest = item["state"], common._digest(item["state"])
        if (digest != expected or digest != item["state_sha256"] or report["fold"] != item["fold"]
                or report["trainer"]["predictor_state_sha256"] != digest or state["schema"] != evidence["state_schema"]
                or state["feature_names"] != FEATURE_NAMES or state["constructor_params"] != shared.HGB_PARAMS
                or state["stage_count"] != 64 or len(state["trees"]) != 64 or state["leaf_values_include_learning_rate"] is not True):
            raise ValueError("B3 canonical64-tree state/recipe changed")
        states[item["fold"]] = state
    prelink = common.settlement._strict_json(root / "prelink_residuals.json")
    if prelink["task_id"] != parent_module.TASK_ID:
        raise ValueError("B3 prelink task changed")
    residuals = {}
    for item in prelink["rows"]:
        key = tuple(item["key"])
        value = float(item["residual"])
        if (key in residuals or key not in controls or item["fold"] != controls[key]["fold"] or not math.isfinite(value)):
            raise ValueError("B3 prelink key/fold/residual changed")
        residuals[key] = {"fold": item["fold"], "residual": value}
    if len(residuals) != 87 or set(residuals) != set(controls):
        raise ValueError("B3 exact87 prelink coverage changed")
    return probabilities, states, residuals


def replay_parent(rows: list, folds: list, parent: dict, states: dict, prelink: dict) -> dict:
    if len(folds) != 4 or set(states) != {1, 2, 3, 4} or set(parent) != set(prelink):
        raise ValueError("B3 parent replay requires four states and identical prelink mask")
    by_date = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    seen, receipts = set(), []
    for fold in folds:
        check = sorted([row for day in fold["check_dates"] for row in by_date.get(day, [])], key=lambda row: row.key)
        fit, unavailable = common.nested._strict_prior_rows(by_date, fold["fit_dates"], check)
        if unavailable:
            raise ValueError("B3 replay fit-label availability changed")
        matrix = shared.feature_matrix(check, include_state=True)
        residual = shared.predict_primitive(states[fold["fold"]], matrix)
        probabilities, bounding = parent_module.link_probabilities([row.trusted["market_probability"] for row in check], residual)
        if any(row.key in seen or row.key not in parent or value != parent[row.key]
                or prelink[row.key]["fold"] != fold["fold"] or prelink[row.key]["residual"] != float(f)
                for row, value, f in zip(check, probabilities, residual, strict=True)):
            raise ValueError("B3 exact prelink/tree/link/common-mask replay differs")
        seen.update(row.key for row in check)
        receipts.append({"fold": fold["fold"], "state_sha256": common._digest(states[fold["fold"]]),
            "check_native_feature_sha256": common._digest(matrix.tolist()), "prelink_rows_replayed": len(check),
            "parent_probability_rows_replayed": len(check), "parent_refits": 0, "bounding": bounding})
    if seen != set(parent):
        raise ValueError("B3 parent replay coverage changed")
    return {"folds": receipts, "parent_rows_replayed": len(seen), "prelink_rows_replayed": len(seen),
        "parent_refits": 0, "four_canonical_states_exact": True, "prelink_and_link_exact": True}


def fit_transform(fit_matrix: object, check_matrix: object) -> tuple[np.ndarray, np.ndarray, dict]:
    fit, check = np.asarray(fit_matrix, dtype=np.float64), np.asarray(check_matrix, dtype=np.float64)
    if (fit.ndim != 2 or check.ndim != 2 or fit.shape[1] != 11 or check.shape[1] != 11
            or not len(fit) or not len(check) or not np.isfinite(fit).all() or not np.isfinite(check).all()):
        raise ValueError("ridge normalization requires complete finite eleven-column matrices")
    with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
        mean, std = np.mean(fit, axis=0), np.std(fit, axis=0, ddof=0)
        constant = std == 0.
        if np.any(constant & ~np.all(fit == fit[0], axis=0)):
            raise ValueError("zero population std is not an exactly constant fit column")
        scale = np.where(constant, 1., std)
        a, b = (fit - mean) / scale, (check - mean) / scale
    if (not np.isfinite(mean).all() or not np.isfinite(std).all() or not np.isfinite(scale).all()
            or np.any(scale <= 0) or not np.isfinite(a).all() or not np.isfinite(b).all()):
        raise ValueError("ridge moments/normalized design became nonfinite")
    return a, b, {"mean": mean.tolist(), "population_std": std.tolist(), "scale": scale.tolist(),
        "constant_columns": constant.tolist(), "fit_only": True, "ddof": 0, "columns_retained": 11, "positive_floor": None}


def ridge_objective_gradient(intercept: float, theta: object, matrix: object, residual: object) -> tuple:
    theta, target = common._vector(theta, "ridge coefficients"), common._vector(residual, "past residual target")
    z = np.asarray(matrix, dtype=np.float64)
    if not math.isfinite(intercept) or theta.shape != (11,) or z.shape != (len(target), 11) or not len(target) or not np.isfinite(z).all():
        raise ValueError("ridge objective requires finite intercept/eleven coefficients/design/target")
    with np.errstate(over="raise", invalid="raise"):
        error = intercept + z @ theta - target
        objective = float(.5 * np.sum(error ** 2) + .5 * ALPHA * (theta @ theta))
        slope_gradient, intercept_gradient = z.T @ error + ALPHA * theta, float(np.sum(error))
    if not math.isfinite(objective) or not np.isfinite(slope_gradient).all() or not math.isfinite(intercept_gradient):
        raise ValueError("ridge objective/gradient is nonfinite")
    return objective, slope_gradient, intercept_gradient


def solve_ridge(matrix: object, residual: object) -> tuple[float, np.ndarray, dict]:
    receipt = {"model_fits": 1, "solver": "numpy.linalg.solve", "alpha": ALPHA, "sample_weights": None,
        "intercept_penalty": 0., "solve_calls_started": 0, "solve_calls_completed": 0, "retry_count": 0, "fallback_count": 0,
        "solve_count_semantics": "physical solve invocations/returns; returned invalid vectors are not valid fits"}
    try:
        z, r = np.asarray(matrix, dtype=np.float64), common._vector(residual, "past residual target")
        if z.shape != (len(r), 11) or not len(r) or not np.isfinite(z).all():
            raise ValueError("ridge solve requires finite nonempty eleven-column fit")
        with np.errstate(over="raise", invalid="raise"):
            intercept = float(np.mean(r))
            a, rhs = z.T @ z + ALPHA * np.eye(11), z.T @ (r - intercept)
        if not math.isfinite(intercept) or not np.isfinite(a).all() or not np.isfinite(rhs).all():
            raise ValueError("ridge normal equations/intercept are nonfinite")
        eigenvalues = np.linalg.eigvalsh(a)
        receipt.update({"intercept": intercept, "A": a.tolist(), "rhs": rhs.tolist(), "eigenvalues": eigenvalues.tolist()})
        if not np.isfinite(eigenvalues).all() or np.min(eigenvalues) <= 0:
            raise ValueError("ridge actual normal-equation matrix is not positive definite")
        receipt["solve_calls_started"] = 1
        raw_result = np.linalg.solve(a, rhs)
        receipt["solve_calls_completed"] = 1
        receipt["raw_return_repr"] = repr(raw_result)
        theta = common._vector(raw_result, "solved ridge coefficients")
        if theta.shape != (11,):
            raise ValueError("ridge solve returned wrong coefficient count")
        objective, slope_gradient, intercept_gradient = ridge_objective_gradient(intercept, theta, z, r)
        equation = a @ theta - rhs
        grad_inf = max(float(np.max(np.abs(slope_gradient))), abs(intercept_gradient))
        equation_inf = float(np.max(np.abs(equation)))
        receipt.update({"coefficients": theta.tolist(), "objective": objective, "slope_gradient": slope_gradient.tolist(),
            "intercept_gradient": intercept_gradient, "gradient_infinity_norm": grad_inf,
            "equation_residual": equation.tolist(), "equation_residual_infinity_norm": equation_inf})
        if not np.isfinite(equation).all() or grad_inf > 1e-8 or equation_inf > 1e-8:
            raise ValueError("ridge independent gradient/normal-equation residual exceeds1e-8")
        receipt["converged"] = True
        return intercept, theta, receipt
    except Exception as error:
        receipt.update({"converged": False, "error_type": type(error).__name__, "error": str(error)[:600]})
        raise FitFailure(str(error), receipt) from error


def replay_residual(state: dict, rows: list) -> np.ndarray:
    norm = state["normalization"]
    mean, std, scale, theta, native_beta = (common._vector(value, name) for value, name in (
        (norm["mean"], "saved mean"), (norm["population_std"], "saved std"), (norm["scale"], "saved scale"),
        (state["coefficients"], "saved ridge coefficients"), (state["native_coefficients"], "saved native coefficients")))
    constant = np.asarray(norm["constant_columns"])
    if (state["schema"] != "market_state_ridge_residual_numeric_state_v1" or state["feature_names"] != FEATURE_NAMES
            or any(v.shape != (11,) for v in (mean, std, scale, theta, native_beta)) or constant.shape != (11,)
            or constant.dtype != np.bool_ or not np.array_equal(constant, std == 0) or np.any(std < 0)
            or not np.array_equal(scale, np.where(constant, 1., std)) or np.any(scale <= 0)
            or norm["fit_only"] is not True or norm["ddof"] != 0 or norm["columns_retained"] != 11 or norm["positive_floor"] is not None
            or state["alpha"] != ALPHA or state["sample_weights"] is not None or state["intercept_penalty"] != 0
            or state["output_factor"] != parent_module.FACTOR or not math.isfinite(state["intercept"])
            or not np.array_equal(native_beta, theta / scale)
            or state["native_intercept"] != float(state["intercept"] - mean @ native_beta)
            or np.any(theta[constant] != 0)):
        raise ValueError("saved ridge numeric predictor/fit-only normalization changed")
    x = shared.feature_matrix(rows, include_state=True)
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        residual = state["intercept"] + ((x - mean) / scale) @ theta
        native_residual = state["native_intercept"] + x @ native_beta
    if not np.isfinite(residual).all() or not np.isfinite(native_residual).all() or np.max(np.abs(residual - native_residual)) > 1e-8:
        raise ValueError("ridge residual/native representation equivalence failed")
    return residual


def replay_predictor(state: dict, rows: list) -> tuple[list[float], dict]:
    return parent_module.link_probabilities([row.trusted["market_probability"] for row in rows], replay_residual(state, rows))


def fit_ridge(fit: list, check: list, features: object = None) -> tuple[list[float], dict]:
    del features
    fit_x, check_x = shared.feature_matrix(fit, include_state=True), shared.feature_matrix(check, include_state=True)
    z, w, normalization = fit_transform(fit_x, check_x)
    y, raw = common._vector([row.trusted["outcome"] for row in fit], "past-fit labels"), common._vector(
        [row.trusted["market_probability"] for row in fit], "past-fit raw probabilities")
    common.identity._clipped_logits(raw)
    if np.any((y != 0) & (y != 1)):
        raise ValueError("ridge fit labels must be binary and available")
    residual_target = y - raw
    intercept, theta, receipt = solve_ridge(z, residual_target)
    state = {"schema": "market_state_ridge_residual_numeric_state_v1", "feature_names": FEATURE_NAMES,
        "normalization": normalization, "intercept": intercept, "coefficients": theta.tolist(),
        "alpha": ALPHA, "sample_weights": None, "intercept_penalty": 0., "output_factor": parent_module.FACTOR,
        "native_coefficients": (theta / np.asarray(normalization["scale"])).tolist(),
        "native_intercept": float(intercept - np.asarray(normalization["mean"]) @ (theta / np.asarray(normalization["scale"]))),
        "native_fit_feature_sha256": common._digest(fit_x.tolist()), "native_check_feature_sha256": common._digest(check_x.tolist()),
        "normalized_fit_feature_sha256": common._digest(z.tolist()), "normalized_check_feature_sha256": common._digest(w.tolist()),
        "fit_events": len(fit), "normal_equations": receipt}
    try:
        if np.any(theta[np.asarray(normalization["constant_columns"])] != 0):
            raise ValueError("exact zero-variance fit column received nonzero coefficient")
        residual = intercept + w @ theta
        values, bounding = parent_module.link_probabilities([row.trusted["market_probability"] for row in check], residual)
        replayed, replay_bounds = replay_predictor(state, check)
        if not np.array_equal(residual, replay_residual(state, check)) or values != replayed or bounding != replay_bounds:
            raise ValueError("ridge numeric predictor/prelink replay differs")
    except Exception as error:
        raise FitFailure(str(error), {**receipt, "post_solve_prediction_error": str(error)[:600]}) from error
    return values, {"model_fits": 1, "input_columns": 11, "fit_parameters": 12, "fit_events": len(fit),
        "fit_only": True, "normal_equations": receipt, "check_residuals": residual.tolist(), "bounding": bounding,
        "predictor_state_sha256": common._digest(state), "primitive_prediction_state": state, "primitive_replay_exact": True}


def correction_diagnostics(predictions: list) -> dict:
    result = {}
    for arm in (ARM_CANDIDATE, ARM_RESEARCH_PARENT):
        correction = [item[arm] - item[ARM_RAW] for item in predictions]
        energy = math.fsum(value * value for value in correction) / len(predictions)
        alignment = math.fsum(2 * value * (item[ARM_RAW] - item["row"].trusted["outcome"])
            for item, value in zip(predictions, correction, strict=True)) / len(predictions)
        result[arm] = {"equal_event_correction_energy": energy, "equal_event_signed_alignment": alignment,
            "equal_event_brier_delta_raw_identity": energy + alignment}
    return result


def annotate_question(metrics: dict, reports: list, paired: dict, diagnostics: dict) -> dict:
    deltas = {name: metrics[ARM_CANDIDATE][name] - metrics[ARM_RESEARCH_PARENT][name] for name in ("brier", "log_loss")}
    wins = sum(item["arms"][ARM_CANDIDATE]["brier"] < item["arms"][ARM_RESEARCH_PARENT]["brier"] for item in reports)
    directional = all(value < 0 for value in deltas.values()) and wins >= 3
    evidence = paired[f"candidate_minus_{ARM_RESEARCH_PARENT}"]["brier"]
    return {"annotation_only_not_keep_judge": True, "candidate_minus_actual_parent": deltas, "parent_brier_block_wins": wins,
        "directional_trainer_evidence": directional, "stronger_local_evidence": directional and all(
            evidence[name]["interval_95"][1] < 0 for name in ("schedule_date_interval", "observed_game_week_interval")),
        "exact_recipe_question_failed": any(value >= 0 for value in deltas.values()),
        "repair_of_signed_alignment": diagnostics[ARM_CANDIDATE]["equal_event_signed_alignment"] < 0}


def correction_diagnostics_by_date(predictions: list) -> list:
    groups = defaultdict(list)
    for item in predictions:
        groups[item["row"].game_date].append(item)
    return [{"game_date": day, "events": len(block), "arms": correction_diagnostics(block)}
        for day, block in sorted(groups.items())]


def run(source_root: Path, output: Path, *, allow_test_paths: bool = False) -> dict:
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    common.base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    output.mkdir(parents=True, exist_ok=False)
    progress = {"fit_calls_entered": 0, "fit_calls_completed": 0, "solve_receipts": [],
        "entry_semantics": "candidate fit call; feature/label validation may precede direct solve"}
    try:
        contract = require_dependencies()
        frozen = common.frozen_v0._validate_v0_artifact(V0_ARTIFACT_ROOT)
        controls = common.identity._frozen_controls(frozen)
        parent, parent_states, prelink = load_parent(contract, controls, frozen)
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
            raise ValueError("ridge frozen195 denominator/exclusions/causal receipts changed")
        native_matrix = shared.feature_matrix(rows, include_state=True)
        parent_replay = replay_parent(rows, frozen["folds"], parent, parent_states, prelink)
        dependencies = {module.__name__: digest for module, digest in common.DEPENDENCIES.items()}
        dependencies.update({common.__name__: shared.COMMON_SOURCE_SHA256, shared.__name__: parent_module.SHARED_SOURCE_SHA256,
            sibling.__name__: SIBLING_SOURCE_SHA256, parent_module.__name__: PARENT_SOURCE_SHA256})
        common.base._atomic_json(output / "input_receipts.json", {"task_id": TASK_ID,
            "controller_contract_sha256": CONTRACT_SHA256, "runner_sha256": common._sha256(Path(__file__)),
            "dependency_source_hashes": dependencies, "parent_replay": parent_replay,
            "native_materialized_feature_sha256": common._digest(native_matrix.tolist()), "native_rows_validated": len(rows),
            "runtime_versions": {"python": platform.python_version(), "numpy": np.__version__, "sklearn": shared.sklearn.__version__},
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
                values, trainer = fit_ridge(fit, check)
            except FitFailure as error:
                progress["solve_receipts"].append(error.receipt)
                common.base._atomic_json(output / "fit_progress.json", progress)
                raise
            progress["fit_calls_completed"] += 1
            progress["solve_receipts"].append(trainer["normal_equations"])
            common.base._atomic_json(output / "fit_progress.json", progress)
            return values, trainer
        predictions, reports = sibling.fit_and_predict(rows, frozen["folds"], controls, parent, fit_predict=tracked_fit, arm=ARM_CANDIDATE)
        for fold, report in zip(frozen["folds"], reports, strict=True):
            block = [item for item in predictions if item["fold"] == fold["fold"]]
            for item, residual in zip(block, report["trainer"]["check_residuals"], strict=True):
                item["prelink_residual"] = residual
            report["correction_diagnostics"] = correction_diagnostics(block)
        check_hash = common._digest([list(item["row"].key) for item in predictions])
        if (len(predictions) != 87 or check_hash != common.frozen_v0.EXPECTED_CHECK_KEY_SHA256
                or tuple(item["fit_events"] for item in reports) != (106, 132, 148, 176)
                or tuple(item["check_events"] for item in reports) != (26, 16, 28, 17)
                or any(item["fit_label_unavailable_game_ids"] for item in reports) or progress["fit_calls_completed"] != MODEL_FITS):
            raise ValueError("ridge frozen chronology/counts/exact87 mask/fourfit ceiling changed")
        states = {"schema": "market_state_ridge_residual_numeric_states_v1", "task_id": TASK_ID,
            "folds": [{"fold": report["fold"], "state_sha256": report["trainer"]["predictor_state_sha256"],
                "state": report["trainer"].pop("primitive_prediction_state")} for report in reports]}
        common.base._atomic_json(output / "predictor_states.json", states)
        common.base._atomic_json(output / "prelink_residuals.json", {"task_id": TASK_ID,
            "rows": [{"key": list(item["row"].key), "fold": item["fold"], "residual": item["prelink_residual"]} for item in predictions]})
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
            "parent_replay": parent_replay, "trainer_question_annotation": annotate_question(metrics, reports, paired, diagnostics),
            "research_parent_sha256": PARENT_SOURCE_SHA256, "comparison_incumbent_sha256": contract["comparison_incumbent_sha256"],
            "attribution": contract["changed_training_recipe"]["attribution"],
            "training_loss_limit": "linear residual squared error is not exact linked Brier",
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
                ("predictions", "csv"), ("scorecard", "json"), ("predictor_states", "json"), ("prelink_residuals", "json"))}, **common.BOUNDARY_FLAGS}
        common.base._atomic_json(output / "manifest.json", manifest)
        return manifest
    except Exception as error:
        common.base._atomic_json(output / "failure.json", {"task_id": TASK_ID, "error_type": type(error).__name__,
            "error": str(error)[:1200], "model_fits_maximum": MODEL_FITS, "automatic_retries": 0, "fit_progress": progress,
            "solve_partial_receipt": getattr(error, "receipt", None), **common.BOUNDARY_FLAGS})
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(common.settlement.json.dumps(run(args.source_root, args.output), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
