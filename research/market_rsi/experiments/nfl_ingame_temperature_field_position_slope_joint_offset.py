"""Frozen causal possessing-team field-position slope correction; historical Train Discovery."""
from __future__ import annotations
import argparse
import math
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy.special import expit
from experiments import nfl_ingame_temperature_possession_pressure_joint_offset as math_recipe
from experiments import nfl_ingame_market_temperature_offset as parent
from experiments import nfl_ingame_candidate_evidence_adapter as harness
from supervisor_harness import opened_train_discovery_worker as worker

common = parent.common
TASK_ID, ARM_CANDIDATE = "InGameTemperatureFieldPositionSlopeJointOffset-v1", "temperature_field_position_slope_joint_offset"
FEATURE_NAMES = ["market_logit", "preplay_field_position_market_slope"]
STATE_SCHEMA, ALPHA = "temperature_field_position_slope_joint_numeric_state_v1", 16.
REPO = Path(__file__).parents[3]
CONTRACT_RELATIVE = "research/market_rsi/supervisor_harness/CHECKPOINT_CONTINUATION_N1_CONTRACT_V2_2026-10-05.json"
CONTRACT = REPO / CONTRACT_RELATIVE
CONTRACT_SHA256 = "8e8af7359331a1ae3783420418d92e34e43e3229d911cdf0893b2fa91294067d"
MODULE = "experiments.nfl_ingame_temperature_field_position_slope_joint_offset"
SOURCE_REVIEW = "research/market_rsi/supervisor_harness/COEVO_H1_SOURCE_REVIEW_V3_2026-10-05.json"
SOURCE_REVIEW_SHA256 = "13913664f1f24590adcbd265f5d39121e95f2e71615651795242b87d372dd4cb"
PARITY_REVIEW = "research/market_rsi/supervisor_harness/COEVO_H1_LIVE_PARITY_REVIEW_2026-10-05.json"
PARITY_REVIEW_SHA256 = "c619bca98e52d1947b542647644500838dfb1dcdbb3eea803dc5a0b0c0ee9db0"
PROVENANCE_SOURCE = {"research/market_rsi/experiments/extract_nfl_ingame_checkpoint.R": "37a26997406de0e54bd9d91de10e7417a8b340c68b675892c4f16e9a51675163", "research/market_rsi/experiments/nfl_ingame_causal_possession_pressure_offset.py": "4ea2935fb896397b4d21125bb040a0f82ff82be01abd2779717378d3465a0ab3"}
objective_gradient_hessian, solve_joint = math_recipe.objective_gradient_hessian, math_recipe.solve_joint
FitFailure = parent.FitFailure

def utc_now():
    return datetime.now(timezone.utc)

def field_value(row, anchor):
    if (common.base.STATE_FEATURE_NAMES[2] != "possession_is_home"
            or common.base.STATE_FEATURE_NAMES[8] != "home_possession_field_advantage"):
        raise ValueError("frozen preplay field/possession columns changed")
    try:
        raw, raw_possession = anchor["yards_to_opponent_goal"], anchor["possession_is_home"]
        if any(isinstance(value, (bool, np.bool_)) or not isinstance(value, (str, int, float, np.integer, np.floating)) for value in (raw, raw_possession)):
            raise ValueError("preplay field/possession is not numeric")
        r, possession = float(raw), float(raw_possession)
        state_possession, signed_field = float(row.state_features[2]), float(row.state_features[8])
    except (KeyError, TypeError, IndexError, ValueError) as error:
        raise ValueError("preplay anchor field/possession or state is missing or invalid") from error
    if (not all(math.isfinite(value) for value in (r, possession, state_possession, signed_field))
            or not 0 <= r <= 100 or possession not in (0, 1) or state_possession != possession):
        raise ValueError("preplay field bounds or exact binary possession agreement changed")
    sign = 1 if possession == 1 else -1
    if not math.isclose(signed_field, sign * ((50 - r) / 50), rel_tol=0, abs_tol=1e-12):
        raise ValueError("preplay raw field and existing home-signed orientation disagree")
    return r, int(possession)

def prepare_features(rows, frozen, parent_states):
    parent.parent_module.raw_probabilities(rows)
    if len(rows) != 193 or len({row.game_id for row in rows}) != 193 or set(parent_states) != {1, 2, 3, 4}:
        raise ValueError("field-slope exact193 coverage/four parent states changed")
    anchors = {anchor["game_id"]: anchor for anchor in frozen["anchors"]}
    if len(anchors) != len(frozen["anchors"]) or not {row.game_id for row in rows}.issubset(anchors):
        raise ValueError("preplay field anchor coverage/uniqueness changed")
    values = {row.game_id: field_value(row, anchors[row.game_id]) for row in rows}
    fields, possessions = {key: value[0] for key, value in values.items()}, {key: value[1] for key, value in values.items()}
    return {"field_by_game_id": fields, "possession_by_game_id": possessions}, {
        "feature_names": FEATURE_NAMES, "input_events": 193, "anchor_field_sha256": common._digest(fields),
        "orientation_possession_sha256": common._digest(possessions), "validation_column_indices": [2, 8],
        "transform": "(1-yards_to_opponent_goal/100)*market_logit", "normalization": "none",
        "orientation_guard": "possession_sign*((50-r)/50)", "orientation_tolerance": 1e-12,
        "other_predictive_state_fields_used": False, "future_fields_used": False}

def field_column(rows, features):
    values = [field_value(row, {"yards_to_opponent_goal": features["field_by_game_id"][row.game_id],
        "possession_is_home": features["possession_by_game_id"][row.game_id]})[0] for row in rows]
    return common._vector([(1 - r / 100) * row.market_features[0] for row, r in zip(rows, values, strict=True)], "field-market slope")

def probabilities(beta, gamma, rows, features):
    parent.parent_module.raw_probabilities(rows)
    z = field_column(rows, features)
    if not math.isfinite(beta) or beta < -1 or not math.isfinite(gamma):
        raise ValueError("field-slope coefficients require finite beta>=-1/gamma")
    if gamma == 0.:
        return parent.probabilities(beta, rows)
    with np.errstate(over="raise", invalid="raise"):
        eta = (1 + beta) * np.asarray([row.market_features[0] for row in rows]) + gamma * z
    if not np.isfinite(eta).all():
        raise ValueError("field-slope prediction is nonfinite")
    q = expit(eta)
    bounded = np.clip(q, parent.EPSILON, 1 - parent.EPSILON)
    return [common.probability_contract.validate_probability(float(v), common.probability_contract.DEFAULT_PROBABILITY_POLICY, ARM_CANDIDATE) for v in bounded], {
        "clipped_rows": int(np.count_nonzero(q != bounded)), "lower_clipped_rows": int(np.count_nonzero(q < parent.EPSILON)),
        "upper_clipped_rows": int(np.count_nonzero(q > 1 - parent.EPSILON)), "epsilon": parent.EPSILON,
        "rows_removed": 0, "exact_zero_gamma_parent_identity": True}

def replay_predictor(state, rows, features):
    optimizer = state["optimizer"]
    theta = common._vector([state["beta"], state["gamma"]], "saved field-slope parameters")
    g, h = np.asarray(optimizer["gradient"], dtype=float), np.asarray(optimizer["hessian"], dtype=float)
    kkt = float(max(max(0., -g[0]) if theta[0] == -1 else abs(g[0]), abs(g[1]))) if g.shape == (2,) else math.inf
    gamma_bound = 1 + state["fit_z_absolute_sum"] / ALPHA
    beta_bound = 1 + state["fit_logit_absolute_sum"] / ALPHA
    if (state["schema"] != STATE_SCHEMA or state["feature_columns"] != FEATURE_NAMES or state["alpha"] != ALPHA
            or state["lower_bound"] != -1 or state["intercept"] != 0 or state["transform"] != "(1-yards_to_opponent_goal/100)*market_logit"
            or state["validation_column_indices"] != [2, 8] or state["orientation_guard"] != "possession_sign*((50-r)/50)"
            or state["orientation_tolerance"] != 1e-12 or state["field_name"] != "yards_to_opponent_goal"
            or state["validation_column_names"] != [common.base.STATE_FEATURE_NAMES[index] for index in (2, 8)]
            or not math.isfinite(state["fit_z_absolute_sum"]) or state["fit_z_absolute_sum"] < 0
            or not math.isfinite(state["fit_logit_absolute_sum"]) or state["fit_logit_absolute_sum"] < 0 or state["normalization"] != "none" or state["sample_weights"] is not None
            or state["contract_sha256"] != CONTRACT_SHA256 or state["source_sha256"] != common._sha256(Path(__file__))
            or state["temperature"] != 1 + theta[0] or state["fold_id"] != features["fold_id"]
            or state["parent_state_sha256"] != common._digest(features["parent_state"])
            or state["fit_events"] != features["parent_state"]["fit_events"]
            or state["optimizer_sha256"] != common._digest(optimizer) or optimizer["theta"] != theta.tolist()
            or optimizer["converged"] is not True or type(optimizer["model_fits"]) is not int or optimizer["model_fits"] != 1
            or optimizer["alpha"] != ALPHA or optimizer["solver"] != "cyclic_coordinate_bisection_beta_then_gamma"
            or optimizer["retry_count"] != 0 or optimizer["fallback_count"] != 0
            or optimizer["optimization_calls_started"] != 1 or optimizer["optimization_calls_completed"] != 1
            or optimizer["max_sweeps"] != 100 or optimizer["max_coordinate_steps"] != 200
            or optimizer["coordinate_tolerance"] != 1e-10 or optimizer["joint_tolerance"] != 1e-8
            or not 0 <= optimizer["sweeps"] <= 100 or optimizer["sweeps_started"] != optimizer["sweeps"]
            or optimizer["coordinate_updates"] != 2 * optimizer["sweeps"]
            or optimizer["warmstart"] != [features["parent_state"]["beta"], 0.]
            or optimizer["fit_only_brackets"] != [[-1., beta_bound], [-gamma_bound, gamma_bound]]
            or g.shape != (2,) or h.shape != (2, 2) or not np.isfinite(g).all() or not np.isfinite(h).all()
            or not np.allclose(h, h.T, rtol=0, atol=1e-10) or np.linalg.eigvalsh(h).min() < ALPHA - 1e-10
            or not all(math.isfinite(optimizer[key]) for key in ("F", "F_warmstart", "KKT"))
            or optimizer["KKT"] != kkt or kkt > 1e-8 or optimizer["F"] > optimizer["F_warmstart"] + 1e-8):
        raise ValueError("saved field-slope primitive recipe/optimizer changed")
    if (state["raw_check_sha256"] != common._digest(parent.parent_module.raw_probabilities(rows).tolist())
            or state["field_check_sha256"] != common._digest([features["field_by_game_id"][row.game_id] for row in rows])
            or state["orientation_check_sha256"] != common._digest([features["possession_by_game_id"][row.game_id] for row in rows])
            or state["slope_check_sha256"] != common._digest(field_column(rows, features).tolist())):
        raise ValueError("saved field-slope prediction inputs changed")
    return probabilities(*theta, rows, features)

def fit_predict(fit, check, features):
    saved_parent, fold = features["parent_state"], features["fold_id"]
    parent.replay_predictor(saved_parent, check)
    parent.parent_module.raw_probabilities(fit)
    if fold not in (1, 2, 3, 4) or saved_parent["fit_events"] != len(fit):
        raise ValueError("field-slope explicit past-parent fold/count changed")
    logits, z = [row.market_features[0] for row in fit], field_column(fit, features).tolist()
    theta, receipt = solve_joint(logits, z, [row.trusted["outcome"] for row in fit], saved_parent["beta"])
    try:
        state = {"schema": STATE_SCHEMA, "feature_columns": FEATURE_NAMES, "beta": float(theta[0]), "gamma": float(theta[1]),
            "temperature": 1 + float(theta[0]), "alpha": ALPHA, "lower_bound": -1., "intercept": 0, "transform": "(1-yards_to_opponent_goal/100)*market_logit",
            "validation_column_indices": [2, 8], "validation_column_names": ["possession_is_home", "home_possession_field_advantage"],
            "field_name": "yards_to_opponent_goal", "orientation_guard": "possession_sign*((50-r)/50)", "orientation_tolerance": 1e-12, "normalization": "none", "sample_weights": None, "fit_events": len(fit), "fold_id": fold,
            "fit_z_absolute_sum": math.fsum(abs(value) for value in z), "fit_logit_absolute_sum": math.fsum(abs(value) for value in logits), "contract_sha256": CONTRACT_SHA256, "source_sha256": common._sha256(Path(__file__)),
            "parent_state_sha256": common._digest(saved_parent), "fit_inputs_sha256": common._digest([logits, z]),
            "raw_check_sha256": common._digest(parent.parent_module.raw_probabilities(check).tolist()),
            "field_check_sha256": common._digest([features["field_by_game_id"][row.game_id] for row in check]),
            "orientation_check_sha256": common._digest([features["possession_by_game_id"][row.game_id] for row in check]),
            "slope_check_sha256": common._digest(field_column(check, features).tolist()), "optimizer": receipt, "optimizer_sha256": common._digest(receipt)}
        values, bounding = probabilities(*theta, check, features)
        if (values, bounding) != replay_predictor(state, check, features):
            raise ValueError("field-slope numeric replay differs")
    except Exception as error:
        raise FitFailure(str(error), {**receipt, "post_optimization_prediction_error": str(error)[:600]}) from error
    return values, {"model_fits": 1, "fit_events": len(fit), "fit_parameters": 2, "input_columns": 2, "fit_only": True,
        "optimizer": receipt, "bounding": bounding, "numeric_replay_exact": True,
        "primitive_prediction_state": state, "predictor_state_sha256": common._digest(state)}

def require_admission(source_root, output):
    if (REPO / CONTRACT_RELATIVE).is_symlink() or common._sha256(REPO / CONTRACT_RELATIVE) != CONTRACT_SHA256:
        raise ValueError("continuation N1 compiled scientific contract changed")
    contract = common.settlement._strict_json(REPO / CONTRACT_RELATIVE)
    resources = contract["resources"]
    start, deadline = [datetime.fromisoformat(resources[key].replace("Z", "+00:00")) for key in ("start_utc", "deadline_utc")]
    if not start <= utc_now() < deadline:
        raise ValueError("continuation N1 fresh execution authority expired or not started")
    output = Path(output)
    if output.is_symlink() or output.parent.name != "runs" or not output.name:
        raise ValueError("continuation N1 output must be exclusive worker pilot/runs/attempt")
    request_path = output.parents[1] / "worker" / f"{output.name}.request.json"
    if request_path.is_symlink():
        raise ValueError("continuation N1 request is symlinked")
    request = common.settlement._strict_json(request_path)
    if (request["attempt_id"] != output.name or request["candidate_id"] != TASK_ID or request["module"] != MODULE
            or request["spec_sha256"] != CONTRACT_SHA256 or request["max_fits"] != 4 or not 0 < request["max_wall_seconds"] <= 900
            or request["python"] != resources["python"] or request["python_sha256"] != resources["python_sha256"]):
        raise ValueError("continuation N1 exact request/spec/runtime changed")
    worker.validate(request, REPO)
    binding = harness.held_c7_binding()
    own_path = str(Path(__file__).resolve())
    dependencies = {**binding["dependency_source_hashes"], **{str((Path(__file__).parents[3] / path).resolve()): digest for path, digest in contract["reuse_helpers"].items()}}
    dependencies.update({str((Path(__file__).parents[3] / path).resolve()): digest for path, digest in PROVENANCE_SOURCE.items()})
    required = {str(Path(path).relative_to(Path(__file__).parents[3])): digest for path, digest in dependencies.items()}
    required.update({CONTRACT_RELATIVE: CONTRACT_SHA256, SOURCE_REVIEW: SOURCE_REVIEW_SHA256, PARITY_REVIEW: PARITY_REVIEW_SHA256,
        str(harness.CONTRACT.relative_to(Path(__file__).parents[3])): harness.CONTRACT_SHA256,
        str(Path(__file__).relative_to(Path(__file__).parents[3])): common._sha256(Path(__file__))})
    if any(request["files"].get(path) != digest for path, digest in required.items()):
        raise ValueError("continuation N1 exact source/helper/review coverage changed")
    review, parity = [common.settlement._strict_json(REPO / path) for path in (SOURCE_REVIEW, PARITY_REVIEW)]
    if review.get("passed") is not True or review.get("source_sha256") != binding["adapter_source_sha256"] or review.get("verdict") != "EXACT_SOURCE_ADMITTED_FOR_ONE_BOUNDED_HELD_C7_TRIAL":
        raise ValueError("continuation N1 H source is not independently admitted")
    expected = {"verdict": "PASS", "adapter_source_sha256": binding["adapter_source_sha256"], "source_review_sha256": SOURCE_REVIEW_SHA256,
        "predictions_exact": True, "predictor_states_exact": True, "original_scorecard_fields_exact": True, "fit_calls_entered": 4,
        "fit_calls_completed": 4, "control_refits": 0, "same_id_retries": 0, "source_K_C_worker_unchanged": True,
        "scope": "H1 held-C7 parity only; no predictive/R/automatic-continuation gain"}
    if any(type(parity.get(key)) is not type(value) or parity.get(key) != value for key, value in expected.items()):
        raise ValueError("continuation N1 H live parity gate failed")
    dependencies[own_path] = common._sha256(Path(__file__))
    binding.update(candidate_id=TASK_ID, arm=ARM_CANDIDATE, candidate_source_path=own_path, candidate_source_sha256=dependencies[own_path],
        candidate_contract_path=str(CONTRACT.resolve()), candidate_contract_sha256=CONTRACT_SHA256, research_parent=contract["research_parent"],
        feature_names=FEATURE_NAMES, comparison_incumbent_sha256=contract["comparison_incumbent"]["sha256"], attribution=contract["attribution"], dependency_source_hashes=dependencies)
    binding["callback_source_bindings"] = {name: own_path for name in ("prepare_features", "fit_predict", "replay_predictor")}
    harness.validate_binding(binding, {name: globals()[name] for name in binding["callback_source_bindings"]})
    return binding

def run(source_root, output, *, allow_test_paths=False):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError("continuation N1 output already exists; inspect without relaunch")
    try:
        binding = require_admission(source_root, output)
        if not allow_test_paths and Path(source_root).resolve() != worker.TRAIN.resolve():
            raise ValueError("continuation N1 source is not resident authorized Train")
        return harness.run_recipe(source_root, output, binding, prepare_features, fit_predict, replay_predictor, allow_test_paths=allow_test_paths)
    except Exception as error:
        if not output.exists():
            output.mkdir(parents=True, exist_ok=False)
            common.base._atomic_json(output / "failure.json", {"task_id": TASK_ID, "phase": "entry_admission", "error_type": type(error).__name__, "error": str(error)[:1200], "model_fits": 0, "automatic_retries": 0, **common.BOUNDARY_FLAGS})
        raise

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(common.settlement.json.dumps(run(args.source_root, args.output), sort_keys=True, indent=2))

if __name__ == "__main__":
    main()

