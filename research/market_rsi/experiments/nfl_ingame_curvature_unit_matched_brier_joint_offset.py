#!/usr/bin/env python3
"""Frozen C4 design and local-unit Brier training; historical Train Discovery."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import math
from pathlib import Path
import platform

import numpy as np
import scipy
from scipy.optimize import minimize
from scipy.special import expit
from experiments import nfl_ingame_prior_play_volume_unit_scale_joint_offset as parent_module

native, common, sibling, shared, volume = (parent_module.native, parent_module.common,
    parent_module.sibling, parent_module.shared, parent_module.volume)
TASK_ID = "InGameCurvatureUnitMatchedBrierJointOffset-v4"
ARM_CANDIDATE = "curvature_unit_matched_brier_joint_offset"
ARM_RESEARCH_PARENT = shared.ARM_RESEARCH_PARENT
ARM_RAW, ARM_ORDINARY, ARM_PARENT = shared.ARM_RAW, shared.ARM_ORDINARY, shared.ARM_PARENT
SOURCE_ROOT, V0_ARTIFACT_ROOT, MODEL_FITS = shared.SOURCE_ROOT, shared.V0_ARTIFACT_ROOT, 4
CONTRACT = Path(__file__).parents[1] / "supervisor_harness" / "COEVO_BATCH5_CONTRACT_2026-10-03.json"
CONTRACT_SHA256 = "2da17c7c181ad3ffe050ac9c926bf3c0e27128f7d3a7e5aba2f1a9aca4b2f852"
PARENT_SOURCE_SHA256 = "ff251b120bd80dbcaf7846f830cb0c065d3abb15bb9bc769b9826d09e63c32da"
COLUMNS = parent_module.COLUMNS
OPTIONS = {"maxiter": 500, "gtol": 1e-8, "ftol": 1e-12, "maxls": 50, "maxcor": 10, "maxfun": 15000}
DESIGN_KEYS = ("native_fit_feature_sha256", "normalized_fit_feature_sha256", "native_check_feature_sha256",
    "normalized_check_feature_sha256", "volume_scale", "freshness_normalization", "fit_events")


class PipelineFailure(ValueError):
    """Terminal same-fit failure with a partial JSON-safe optimizer receipt."""
    def __init__(self, message: str, receipt: dict):
        super().__init__(message)
        self.receipt = receipt


def require_dependencies() -> dict:
    parent_module.require_dependencies()
    for path, expected in ((CONTRACT, CONTRACT_SHA256), (Path(parent_module.__file__), PARENT_SOURCE_SHA256)):
        if not path.is_file() or path.is_symlink() or common._sha256(path) != expected:
            raise ValueError(f"frozen Brier source/contract changed: {path.name}")
    contract = common.settlement._strict_json(CONTRACT)
    if (scipy.__version__ != "1.14.0" or contract["candidate_id"] != TASK_ID
            or contract["research_parent"]["runner_sha256"] != PARENT_SOURCE_SHA256
            or contract["fixed_information_and_representation"]["column_order"] != COLUMNS
            or contract["optimizer_pipeline"]["phase1"]["options"] != OPTIONS
            or contract["changed_training_recipe"]["fits"] != MODEL_FITS):
        raise ValueError("frozen Brier recipe/runtime/actual-parent changed")
    return contract


def load_parent(contract: dict, controls: dict, frozen: dict) -> tuple[dict, dict]:
    probabilities = shared.load_parent_predictions(contract, controls, frozen)
    evidence, root = contract["research_parent"], Path(contract["research_parent"]["artifact_root"])
    manifest = common.settlement._strict_json(root / "manifest.json")
    if set(evidence["artifact_hashes"]) != {"manifest.json", "input_receipts.json", "pre_score_lock.json",
            "exclusions.json", "predictor_states.json", "scorecard.json", "predictions.csv"}:
        raise ValueError("C4 parent requires exact seven-file receipt set")
    for filename, expected in evidence["artifact_hashes"].items():
        path, key = root / filename, filename.split(".")[0] + "_sha256"
        if (not path.is_file() or path.is_symlink() or common._sha256(path) != expected
                or evidence.get(key, expected) != expected
                or (filename != "manifest.json" and manifest.get(key) != expected)):
            raise ValueError(f"frozen C4 seven-file receipt changed: {filename}")
    receipts = common.settlement._strict_json(root / "input_receipts.json")
    lock = common.settlement._strict_json(root / "pre_score_lock.json")
    exclusions = common.settlement._strict_json(root / "exclusions.json")
    if (receipts["runner_sha256"] != PARENT_SOURCE_SHA256
            or receipts["controller_contract_sha256"] != parent_module.CONTRACT_SHA256
            or lock["task_id"] != parent_module.TASK_ID or lock["controller_contract_sha256"] != parent_module.CONTRACT_SHA256
            or receipts["v0_artifact_hashes"] != frozen["hashes"] or receipts["pbp_receipts"] != frozen["receipts"]["pbp_receipts"]
            or common._digest(receipts["materialized_receipts"]) != common._digest(frozen["receipts"]["materialized_receipts"])
            or (exclusions["source_events"], exclusions["materialized_events"], exclusions["excluded_events"]) != (195, 193, 2)
            or [(item["game_id"], item["reason"]) for item in exclusions["exclusions"]] != common.identity.EXPECTED_EXCLUSIONS
            or any(receipts.get(key) != value for key, value in common.BOUNDARY_FLAGS.items())):
        raise ValueError("C4 parent source/causal receipts/exclusion/kernel binding changed")
    artifact = common.settlement._strict_json(root / "predictor_states.json")
    reports = common.settlement._strict_json(root / "scorecard.json")["folds"]
    if (artifact["task_id"] != parent_module.TASK_ID or [item["fold"] for item in artifact["folds"]] != [1, 2, 3, 4]
            or len(reports) != 4 or len(evidence["state_sha256_by_fold"]) != 4):
        raise ValueError("C4 canonical four-state task/coverage changed")
    states = {}
    for item, report, expected in zip(artifact["folds"], reports, evidence["state_sha256_by_fold"], strict=True):
        state, digest = item["state"], common._digest(item["state"])
        if (digest != expected or digest != item["state_sha256"] or report["fold"] != item["fold"]
                or report["trainer"]["predictor_state_sha256"] != digest or state["schema"] != evidence["state_schema"]):
            raise ValueError("C4 canonical numeric state changed")
        states[item["fold"]] = state
    return probabilities, states


def design_receipt(fit: list, check: list, features: dict) -> tuple[tuple, dict]:
    design = parent_module.scaled_design(fit, check, features)
    a, b, x, z, scale, norm = design
    receipt = {"native_fit_feature_sha256": common._digest(a.tolist()), "native_check_feature_sha256": common._digest(b.tolist()),
        "normalized_fit_feature_sha256": common._digest(x.tolist()), "normalized_check_feature_sha256": common._digest(z.tolist()),
        "volume_scale": scale, "freshness_normalization": norm, "fit_events": len(fit)}
    return design, receipt


def replay_parent(rows: list, folds: list, features: dict, parent: dict, states: dict) -> tuple[dict, dict]:
    if len(folds) != 4 or set(states) != {1, 2, 3, 4}:
        raise ValueError("C4 replay requires four frozen folds/states")
    by_date = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    seen, receipts, expected_by_keys = set(), [], {}
    for fold in folds:
        check = sorted([row for day in fold["check_dates"] for row in by_date.get(day, [])], key=lambda row: row.key)
        fit, unavailable = common.nested._strict_prior_rows(by_date, fold["fit_dates"], check)
        _, receipt = design_receipt(fit, check, features)
        state = states[fold["fold"]]
        if unavailable or any(state[key] != receipt[key] for key in DESIGN_KEYS):
            raise ValueError("C4 parent exact native/normalized design/fit-only scale/available labels changed")
        values = parent_module.replay_unit(state, check, features)
        if any(row.key in seen or row.key not in parent or value != parent[row.key]
                for row, value in zip(check, values, strict=True)):
            raise ValueError("C4 parent primitive probabilities/common mask replay differs")
        seen.update(row.key for row in check)
        expected_by_keys[tuple(row.key for row in check)] = receipt
        receipts.append({"fold": fold["fold"], "parent_state_sha256": common._digest(state), **receipt,
            "parent_probabilities_replayed": len(check), "parent_refits": 0})
    if seen != set(parent):
        raise ValueError("C4 parent primitive replay coverage changed")
    return ({"folds": receipts, "parent_rows_replayed": len(seen), "parent_refits": 0,
        "all_parent_probabilities_exact": True, "all_four_designs_and_normalizers_exact": True}, expected_by_keys)


def curvature_units(matrix: object, raw: object) -> dict:
    x, p = np.asarray(matrix, dtype=np.float64), common._vector(raw, "fit raw probabilities")
    if x.ndim != 2 or x.shape != (len(p), 2) or not len(p) or not np.isfinite(x).all() or np.any((p <= 0) | (p >= 1)):
        raise ValueError("fit curvature requires finite two-column design/interior raw probabilities")
    with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
        v = p * (1 - p)
        denominator, numerator = np.sum(v[:, None] * x ** 2, axis=0), np.sum(2 * v[:, None] ** 2 * x ** 2, axis=0)
        if not np.isfinite(denominator).all() or not np.isfinite(numerator).all() or np.any(denominator <= 0):
            raise ValueError("fit curvature denominator must be finite and positive; no floor")
        ratio = numerator / denominator
        penalty = 16 * ratio
    if not np.isfinite(ratio).all() or not np.isfinite(penalty).all() or np.any((ratio <= 0) | (ratio > .5)):
        raise ValueError("fit curvature ratio must satisfy 0<r<=.5; no clipping/fallback")
    return {"n": numerator.tolist(), "d": denominator.tolist(), "r": ratio.tolist(), "lambda": penalty.tolist(),
        "fit_only": True, "uses_labels": False, "uses_check_rows": False, "base_nll_penalty": 16,
        "interpretation": "hypothetical zero-point expected diagonal prior/data units; not actual/full Hessian"}


def objective_gradient_hessian(theta: object, matrix: object, outcomes: object, offsets: object, penalty: object) -> tuple:
    theta, y, offsets, penalty = (common._vector(value, name) for value, name in (
        (theta, "Brier coefficients"), (outcomes, "fit labels"), (offsets, "fit offsets"), (penalty, "Brier prior")))
    x = np.asarray(matrix, dtype=np.float64)
    if (theta.shape != (2,) or penalty.shape != (2,) or np.any(penalty <= 0) or x.shape != (len(y), 2)
            or offsets.shape != y.shape or not len(y) or not np.isfinite(x).all() or np.any((y != 0) & (y != 1))):
        raise ValueError("Brier objective requires finite binary unweighted two-coordinate fit")
    with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
        eta = offsets + x @ theta
        if not np.isfinite(eta).all():
            raise ValueError("Brier objective eta is nonfinite")
        q = expit(eta)
        u, error = q * (1 - q), q - y
        value = float(np.sum(error ** 2) + .5 * np.sum(penalty * theta ** 2))
        gradient = 2 * x.T @ (error * u) + penalty * theta
        hessian = x.T @ (x * (2 * (u ** 2 + error * u * (1 - 2 * q)))[:, None]) + np.diag(penalty)
    if not math.isfinite(value) or not np.isfinite(gradient).all() or not np.isfinite(hessian).all():
        raise ValueError("Brier objective/gradient/Hessian is nonfinite")
    return value, gradient, hessian


def optimize_brier(x: np.ndarray, y: np.ndarray, offsets: np.ndarray, penalty: np.ndarray) -> tuple:
    receipt = {"initial": [0., 0.], "same_objective_and_lambda_all_phases": True, "lambda": penalty.tolist(),
        "lambda_sha256": common._digest(penalty.tolist()), "model_fits": 1, "restart_count": 0, "retry_count": 0,
        "phase1": {"method": "L-BFGS-B", "options": dict(OPTIONS), "bounds": None},
        "phase2": {"max_iterations": 25, "max_armijo_proposals": 60, "eigenvalue_floor_direction_only": 1e-6, "steps": []}}
    def evaluate(theta):
        return objective_gradient_hessian(theta, x, y, offsets, penalty)
    try:
        result = minimize(lambda theta: evaluate(theta)[:2], np.zeros(2), jac=True, method="L-BFGS-B", bounds=None, options=dict(OPTIONS))
        receipt["phase1"].update({"returned_x_repr": repr(result.x), "success": bool(result.success), "status": int(result.status),
            "message": str(result.message), "nit": int(result.nit), "nfev": int(result.nfev), "njev": int(result.njev),
            "reported_fun_repr": repr(result.fun), "reported_jac_repr": repr(result.jac)})
        reported_fun, reported_jac = float(result.fun), common._vector(result.jac, "phase1 reported gradient")
        if not math.isfinite(reported_fun) or reported_jac.shape != (2,):
            raise ValueError("phase1 reported objective/gradient is nonfinite or wrong shape")
        receipt["phase1"].update({"reported_fun": reported_fun, "reported_jac": reported_jac.tolist()})
        theta = common._vector(result.x, "phase1 returned coefficients")
        if theta.shape != (2,):
            raise ValueError("phase1 returned wrong parameter shape")
        value, gradient, hessian = evaluate(theta)
        receipt["phase1"].update({"returned_x": theta.tolist(), "success": bool(result.success), "status": int(result.status),
            "message": str(result.message), "nit": int(result.nit), "nfev": int(result.nfev), "njev": int(result.njev),
            "independent_objective": value, "independent_gradient": gradient.tolist()})
        receipt["phase2"]["initial"] = theta.tolist()
        for iteration in range(26):
            grad_inf = float(np.max(np.abs(gradient)))
            eigenvalues, eigenvectors = np.linalg.eigh((hessian + hessian.T) / 2)
            receipt["phase2"]["last_checked"] = {"x": theta.tolist(), "objective": value,
                "gradient": gradient.tolist(), "actual_hessian": hessian.tolist(), "actual_eigenvalues": eigenvalues.tolist()}
            if grad_inf <= 1e-8:
                break
            if iteration == 25:
                raise ValueError("modified-Newton maximum25 iterations reached")
            positive = (eigenvectors * np.maximum(eigenvalues, 1e-6)) @ eigenvectors.T
            direction = np.linalg.solve(positive, gradient)
            product = float(gradient @ direction)
            if not np.isfinite(direction).all() or not math.isfinite(product) or product <= 0:
                raise ValueError("modified-Newton direction is not finite strict descent")
            step = {"iteration": iteration + 1, "from_x": theta.tolist(), "objective_before": value,
                "gradient_infinity_before": grad_inf, "actual_hessian_eigenvalues": eigenvalues.tolist(),
                "direction": direction.tolist(), "gradient_dot_direction": product, "proposals": 0}
            receipt["phase2"]["steps"].append(step)
            alpha = 1.
            for proposal in range(60):
                step["proposals"] = proposal + 1
                new_theta = theta - alpha * direction
                new_value, new_gradient, new_hessian = evaluate(new_theta)
                if new_value <= value - 1e-4 * alpha * product:
                    step.update({"alpha": alpha, "accepted_x": new_theta.tolist(), "objective_after": new_value})
                    theta, value, gradient, hessian = new_theta, new_value, new_gradient, new_hessian
                    break
                alpha *= .5
            else:
                raise ValueError("modified-Newton maximum60 Armijo proposals failed")
        eigenvalues = np.linalg.eigvalsh((hessian + hessian.T) / 2)
        if float(np.max(np.abs(gradient))) > 1e-8 or np.min(eigenvalues) <= 0 or not np.isfinite(eigenvalues).all():
            raise ValueError("Brier final strict gradient/actual positive-definite Hessian failed")
        receipt["phase2"].update({"iterations": len(receipt["phase2"]["steps"]), "final_x": theta.tolist()})
        receipt.update({"converged": True, "local_not_global_optimum": True,
            "stationarity": {"objective": value, "gradient": gradient.tolist(), "gradient_infinity_norm": float(np.max(np.abs(gradient))),
                "hessian": hessian.tolist(), "hessian_eigenvalues": eigenvalues.tolist()}})
        return theta, receipt
    except Exception as error:
        receipt.update({"converged": False, "error_type": type(error).__name__, "error": str(error)[:600]})
        raise PipelineFailure(str(error), receipt) from error


def replay_brier(state: dict, rows: list, features: dict) -> list[float]:
    units = state["curvature_units"]
    penalty, ratio, numerator, denominator = (common._vector(units[key], "saved curvature " + key) for key in ("lambda", "r", "n", "d"))
    if (state["schema"] != "curvature_unit_matched_brier_joint_numeric_state_v1" or any(v.shape != (2,) for v in (penalty, ratio, numerator, denominator))
            or np.any(denominator <= 0) or np.any((ratio <= 0) | (ratio > .5)) or not np.array_equal(ratio, numerator / denominator)
            or not np.array_equal(penalty, 16 * ratio) or units["fit_only"] is not True
            or units["uses_labels"] is not False or units["uses_check_rows"] is not False
            or units["base_nll_penalty"] != 16 or state["training_objective"] != "unweighted_sum_Brier_plus_half_diagonal_prior"
            or state["effective_native_volume_penalty"] != penalty[0] * state["volume_scale"] * state["volume_scale"]):
        raise ValueError("saved fit-only Brier prior units changed")
    # Pure parent's prediction validator/link only, never its fit or run admission.
    proxy = {**state, "penalty_per_coordinate": 16,
        "effective_native_volume_penalty": 16 * state["volume_scale"] * state["volume_scale"]}
    return parent_module.replay_unit(proxy, rows, features)


def fit_brier(fit: list, check: list, bundle: dict) -> tuple[list[float], dict]:
    features, expected = bundle["features"], bundle["expected_by_keys"].get(tuple(row.key for row in check))
    design, receipt = design_receipt(fit, check, features)
    if expected is None or receipt != expected:
        raise ValueError("candidate C4 exact design/fit-only scales parity changed before fit")
    _, _, x, z, scale, _ = design
    units = curvature_units(x, sibling.raw_probabilities(fit))
    theta, optimizer = optimize_brier(x, np.asarray([row.trusted["outcome"] for row in fit]),
        np.asarray([row.market_features[0] for row in fit]), np.asarray(units["lambda"]))
    state = {"schema": "curvature_unit_matched_brier_joint_numeric_state_v1", "column_order": COLUMNS,
        "native_columns": native.COLUMNS, "volume_formula": volume.FORMULA, "freshness_formula": native.FRESHNESS_FORMULA,
        **receipt, "scale_ddof": 0, "scale_fit_only": True, "scale_only": True, "coefficients": theta.tolist(),
        "native_volume_coefficient": float(theta[0] / scale), "effective_native_volume_penalty": units["lambda"][0] * scale * scale,
        "curvature_units": units, "market_coefficient": 1, "intercept": False,
        "training_objective": "unweighted_sum_Brier_plus_half_diagonal_prior", "stationarity": optimizer["stationarity"],
        "optimizer_pipeline": optimizer, "actual_parent_design_parity": True}
    try:
        values = native.probabilities(theta, z, [row.market_features[0] for row in check], sibling.raw_probabilities(check))
        if values != replay_brier(state, check, features):
            raise ValueError("Brier numeric predictor replay differs")
    except Exception as error:
        raise PipelineFailure(str(error), {**optimizer, "post_optimization_prediction_error": str(error)[:600]}) from error
    return values, {"model_fits": 1, "input_columns": 2, "fit_events": len(fit), "fit_only": True,
        "optimizer": optimizer, "predictor_state_sha256": common._digest(state), "primitive_prediction_state": state,
        "primitive_replay_exact": True, "bounding": {"clipped_rows": 0, "rows_removed": 0, "epsilon": sibling.EPSILON}}


def annotate_question(metrics: dict, reports: list, paired: dict) -> dict:
    deltas = {name: metrics[ARM_CANDIDATE][name] - metrics[ARM_RESEARCH_PARENT][name] for name in ("brier", "log_loss")}
    wins = sum(item["arms"][ARM_CANDIDATE]["brier"] < item["arms"][ARM_RESEARCH_PARENT]["brier"] for item in reports)
    directional = deltas["brier"] < 0 and wins >= 3 and metrics[ARM_CANDIDATE]["log_loss"] < metrics[ARM_RAW]["log_loss"]
    evidence = paired[f"candidate_minus_{ARM_RESEARCH_PARENT}"]["brier"]
    return {"annotation_only_not_keep_judge": True, "candidate_minus_actual_parent": deltas, "parent_brier_block_wins": wins,
        "directional_primary_alignment_evidence": directional, "stronger_local_evidence": directional and all(
            evidence[name]["interval_95"][1] < 0 for name in ("schedule_date_interval", "observed_game_week_interval")),
        "exact_recipe_question_failed": deltas["brier"] >= 0 or metrics[ARM_CANDIDATE]["log_loss"] >= metrics[ARM_RAW]["log_loss"]}


def run(source_root: Path, output: Path, *, allow_test_paths: bool = False) -> dict:
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    common.base._validate_roots(source_root, output, allow_test_paths=allow_test_paths)
    output.mkdir(parents=True, exist_ok=False)
    progress = {"model_fits_started": 0, "model_fits_completed": 0, "optimizer_receipts": [],
        "started_count_semantics": "candidate fit-call entries; parity/unit failures may precede optimizer",
        "completed_count_semantics": "complete candidate fit plus validated primitive predictions; see optimizer receipts for fit status"}
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
            raise ValueError("Brier frozen195 denominator/exclusions/causal receipts changed")
        features, feature_receipts = native.load_features(source_root, frozen, contract, rows)
        parent_replay, expected_by_keys = replay_parent(rows, frozen["folds"], features, parent, parent_states)
        dependencies = {module.__name__: digest for module, digest in common.DEPENDENCIES.items()}
        dependencies.update({common.__name__: shared.COMMON_SOURCE_SHA256, shared.__name__: sibling.SHARED_SOURCE_SHA256,
            sibling.__name__: volume.SIBLING_SOURCE_SHA256, volume.__name__: native.VOLUME_SOURCE_SHA256,
            native.__name__: parent_module.NATIVE_SOURCE_SHA256, volume.uncertainty.__name__: volume.UNCERTAINTY_SOURCE_SHA256,
            parent_module.__name__: PARENT_SOURCE_SHA256})
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
        def tracked_fit(fit, check, bundle):
            progress["model_fits_started"] += 1
            try:
                values, trainer = fit_brier(fit, check, bundle)
            except PipelineFailure as error:
                progress["optimizer_receipts"].append(error.receipt)
                common.base._atomic_json(output / "optimizer_progress.json", progress)
                raise
            progress["model_fits_completed"] += 1
            progress["optimizer_receipts"].append(trainer["optimizer"])
            common.base._atomic_json(output / "optimizer_progress.json", progress)
            return values, trainer
        predictions, reports = sibling.fit_and_predict(rows, frozen["folds"], controls, parent,
            fit_predict=tracked_fit, features={"features": features, "expected_by_keys": expected_by_keys}, arm=ARM_CANDIDATE)
        check_hash = common._digest([list(item["row"].key) for item in predictions])
        if (len(predictions) != 87 or check_hash != common.frozen_v0.EXPECTED_CHECK_KEY_SHA256
                or tuple(item["fit_events"] for item in reports) != (106, 132, 148, 176)
                or tuple(item["check_events"] for item in reports) != (26, 16, 28, 17)
                or any(item["fit_label_unavailable_game_ids"] for item in reports) or progress["model_fits_completed"] != MODEL_FITS):
            raise ValueError("Brier frozen chronology/counts/exact87 mask/fourfit ceiling changed")
        states = {"schema": "curvature_brier_joint_numeric_prediction_states_v1", "task_id": TASK_ID,
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
            "actual_research_parent_arm": ARM_RESEARCH_PARENT, "actual_research_parent_id": parent_module.TASK_ID,
            "scientific_decision": scientific, "operational_decision": operational, "decision_conditions": conditions,
            "model_fits": MODEL_FITS, "control_refits": 0, "source_denominator": {"events": 195, "dates": 42,
                "materialized_events": 193, "excluded_events": 2, "check_events": 87,
                "check_dates": len({item["row"].game_date for item in predictions}), "check_game_weeks": len({item["row"].game_week for item in predictions})},
            "identical_masks": {"all_controls_same_rows_labels_and_checkpoints": True, "check_key_sha256": check_hash, "matches_frozen_v0": True},
            "aggregate": metrics, "folds": reports, "paired_grouped_evidence": paired, "correction_diagnostics": diagnostics,
            "parent_replay": parent_replay, "all_four_designs_and_normalizers_equal_c4": True,
            "primary_alignment_question_annotation": annotate_question(metrics, reports, paired), "research_parent_sha256": PARENT_SOURCE_SHA256,
            "comparison_incumbent_sha256": contract["comparison_incumbent_sha256"],
            "attribution": "C objective plus local prior-unit recipe; not pure loss, new data, H or R effect",
            "inference_boundary": "repeatedly inspected Train Discovery; historical clock only; local not global optimizer validity",
            **common.BOUNDARY_FLAGS}
        shared.write_predictions(output / "predictions.csv", predictions, ARM_CANDIDATE)
        common.base._atomic_json(output / "scorecard.json", scorecard)
        manifest = {"schema": "coevo_frozen_candidate_manifest_v1", "complete": True, "task_id": TASK_ID,
            "completed_utc": datetime.now(timezone.utc).isoformat(), "source_events": 195,
            "materialized_events": 193, "excluded_events": 2, "check_events": 87, "model_fits": MODEL_FITS,
            "control_refits": 0, "automatic_retries": 0, "scientific_decision": scientific, "operational_decision": operational,
            **{f"{name}_sha256": common._sha256(output / f"{name}.{suffix}") for name, suffix in (
                ("pre_score_lock", "json"), ("input_receipts", "json"), ("exclusions", "json"), ("optimizer_progress", "json"),
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
