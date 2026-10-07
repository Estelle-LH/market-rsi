"""Original account Controller score-time recipe; historical Train Discovery."""
from __future__ import annotations
import argparse
import math
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from experiments import nfl_ingame_candidate_evidence_adapter as harness
from supervisor_harness import opened_train_discovery_worker as worker

parent, common = harness.c7, harness.common
TASK_ID = "InGameTemperatureScoreTimeJointOffset-v1"
ARM_CANDIDATE = "temperature_score_time_joint_offset"
FEATURE_NAMES = ["market_logit", "bounded_preplay_score_time_interaction"]
STATE_SCHEMA = "score_time_joint_offset_numeric_state_v1"
SEMANTIC_VERSION = "derived_feature_semantic_contract_v1"
FORMULA = "clip(home_score_diff_pre/14,-1,1)*(1-clip(regulation_seconds_remaining/3600,0,1))"
EPSILON, PENALTY = 1e-6, 8.
MODULE = "experiments.nfl_ingame_score_time_joint_offset_v1"

def finite_number(value):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)) or not math.isfinite(float(value)):
        raise ValueError("finite numeric nonboolean input required")
    return float(value)

def derived_feature(score, seconds):
    score, seconds = finite_number(score), finite_number(seconds)
    return min(1., max(-1., score / 14.)) * (1. - min(1., max(0., seconds / 3600.)))

def columns(rows):
    if common.base.STATE_FEATURE_NAMES[:2] != ("home_score_diff_pre", "regulation_seconds_remaining"):
        raise ValueError("fixed preplay columns changed")
    raw = parent.parent_module.raw_probabilities(rows)
    p = np.clip(raw, EPSILON, 1. - EPSILON)
    logit = np.log(p / (1. - p))
    x = np.asarray([derived_feature(row.state_features[0], row.state_features[1]) for row in rows])
    return np.column_stack((logit, x))

def prepare_features(rows, frozen, parent_states):
    from supervisor_harness.derived_feature_semantic_contract_v1 import validate_feature
    semantic = validate_feature(derived_feature)
    if len(rows) != 193 or len({row.game_id for row in rows}) != 193 or set(parent_states) != {1, 2, 3, 4}:
        raise ValueError("fixed193/fourfold parent coverage changed")
    matrix = columns(rows)
    return {}, {"feature_names": FEATURE_NAMES, "input_events": 193, "formula": FORMULA,
        "semantic_contract_version": SEMANTIC_VERSION, "semantic_validation": semantic,
        "columns": [0, 1], "matrix_sha256": common._digest(matrix.tolist()),
        "future_fields_used": False, "fitted_feature_parameters": 0}

def objective_gradient(theta, matrix, y):
    eta = matrix[:, 0] + matrix @ theta
    value = float(np.sum(np.logaddexp(0., eta) - y * eta) + PENALTY * np.dot(theta, theta))
    gradient = matrix.T @ (expit(eta) - y) + 2. * PENALTY * theta
    return value, gradient

def probabilities(theta, rows):
    theta = common._vector(theta, "beta/gamma")
    if theta.shape != (2,) or theta[0] < -1.:
        raise ValueError("finite beta>=-1 and gamma required")
    matrix = columns(rows)
    with np.errstate(over="raise", invalid="raise"):
        eta = matrix[:, 0] + matrix @ theta
    if not np.isfinite(eta).all():
        raise ValueError("nonfinite prediction")
    q = expit(eta); bounded = np.clip(q, EPSILON, 1. - EPSILON)
    return [common.probability_contract.validate_probability(float(v), common.probability_contract.DEFAULT_PROBABILITY_POLICY, ARM_CANDIDATE) for v in bounded], {
        "epsilon": EPSILON, "clipped_rows": int(np.count_nonzero(q != bounded)),
        "lower_clipped_rows": int(np.count_nonzero(q < EPSILON)),
        "upper_clipped_rows": int(np.count_nonzero(q > 1. - EPSILON)), "rows_removed": 0}

def fit_predict(fit, check, context):
    matrix, check_matrix = columns(fit), columns(check)
    y = common._vector([row.trusted["outcome"] for row in fit], "fit labels")
    if not np.isin(y, [0., 1.]).all() or not len(fit):
        raise ValueError("nonempty binary fit outcomes required")
    receipt = {"solver": "scipy_L-BFGS-B", "initial": [0., 0.], "maxiter": 1000,
        "gtol": 1e-8, "ftol": 0., "optimization_calls_started": 1, "optimization_calls_completed": 0,
        "model_fits": 1, "retry_count": 0, "fallback_count": 0, "converged": False}
    try:
        result = minimize(objective_gradient, np.zeros(2), args=(matrix, y), jac=True,
            method="L-BFGS-B", bounds=[(-1., None), (None, None)], options={"maxiter": 1000, "gtol": 1e-8, "ftol": 0.})
        theta = np.asarray(result.x, dtype=float)
        value, gradient = objective_gradient(theta, matrix, y)
        kkt = max(max(0., -gradient[0]) if theta[0] == -1. else abs(gradient[0]), abs(gradient[1]))
        receipt.update(optimization_calls_completed=1, status=int(result.status), iterations=int(result.nit),
            objective=value, gradient=gradient.tolist(), theta=theta.tolist(), kkt=float(kkt),
            converged=bool(result.success and np.isfinite(theta).all() and theta[0] >= -1. and math.isfinite(value) and np.isfinite(gradient).all()))
        if not receipt["converged"]:
            raise ValueError("single deterministic optimization failed convergence")
        values, bounding = probabilities(theta, check)
    except Exception as error:
        raise parent.FitFailure(str(error), receipt) from error
    state = {"schema": STATE_SCHEMA, "beta": float(theta[0]), "gamma": float(theta[1]),
        "fit_events": len(fit), "fold_id": context["fold_id"], "epsilon": EPSILON, "penalty": PENALTY,
        "score_divisor": 14., "seconds_divisor": 3600., "formula": FORMULA,
        "semantic_contract_version": SEMANTIC_VERSION, "optimizer": receipt,
        "source_sha256": common._sha256(Path(__file__)), "fit_matrix_sha256": common._digest(matrix.tolist()),
        "check_matrix_sha256": common._digest(check_matrix.tolist()), "fit_outcome_sha256": common._digest(y.tolist())}
    return values, {"model_fits": 1, "optimizer": receipt, "bounding": bounding,
        "primitive_prediction_state": state, "predictor_state_sha256": common._digest(state)}

def replay_predictor(state, rows, context):
    theta = [finite_number(state["beta"]), finite_number(state["gamma"])]
    expected = {"schema": STATE_SCHEMA, "epsilon": EPSILON, "penalty": PENALTY, "score_divisor": 14.,
        "seconds_divisor": 3600., "formula": FORMULA, "semantic_contract_version": SEMANTIC_VERSION,
        "source_sha256": common._sha256(Path(__file__)), "fold_id": context["fold_id"]}
    optimizer = state["optimizer"]
    if (any(state.get(k) != v or type(state.get(k)) is not type(v) for k, v in expected.items())
            or type(state["fit_events"]) is not int or state["fit_events"] < 1
            or optimizer["converged"] is not True or optimizer["theta"] != theta
            or optimizer["initial"] != [0., 0.] or optimizer["solver"] != "scipy_L-BFGS-B"
            or optimizer["maxiter"] != 1000 or optimizer["gtol"] != 1e-8 or optimizer["ftol"] != 0.
            or optimizer["retry_count"] != 0 or optimizer["fallback_count"] != 0
            or optimizer["optimization_calls_started"] != 1 or optimizer["optimization_calls_completed"] != 1
            or state["check_matrix_sha256"] != common._digest(columns(rows).tolist())):
        raise ValueError("primitive recipe/state/replay inputs changed")
    return probabilities(theta, rows)

def run(source_root, output, binding, *, allow_test_paths=False):
    return harness.run_recipe(source_root, output, binding, prepare_features, fit_predict, replay_predictor, allow_test_paths=allow_test_paths)

def require_admission(source_root, output):
    root = Path(output).resolve().parents[1]
    binding = common.settlement._strict_json(root / "binding.json")
    request = common.settlement._strict_json(root / "worker" / (Path(output).name + ".request.json"))
    worker.validate(request, Path(__file__).parents[3])
    authorization_path = root / "authorization.json"
    if worker.sha(authorization_path) != "8aca216300e0c47bffbe7f8e6959a4aba80cddd250066949654d90875d5ec057":
        raise ValueError("fresh pilot authorization changed")
    state = common.settlement._strict_json(authorization_path)
    start, deadline = [datetime.fromisoformat(state[k].replace("Z", "+00:00")) for k in ("start_utc", "deadline_utc")]
    if (not start <= datetime.now(timezone.utc) < deadline or request["module"] != MODULE
            or request["candidate_id"] != TASK_ID or request["max_fits"] != 4
            or request["attempt_id"] != Path(output).name
            or request["files"]["research/market_rsi/" + MODULE.replace(".", "/") + ".py"] != binding["candidate_source_sha256"]
            or request["spec_sha256"] != binding["candidate_contract_sha256"]
            or Path(source_root).resolve() != worker.TRAIN.resolve()):
        raise ValueError("fresh pilot identity/clock/source/contract changed")
    harness.validate_binding(binding, dict(prepare_features=prepare_features, fit_predict=fit_predict, replay_predictor=replay_predictor))
    return binding

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--source-root", required=True); parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run(args.source_root, args.output, require_admission(args.source_root, args.output))
