"""Original Controller close-score possession candidate; Train Discovery only."""
from __future__ import annotations
import argparse
import math
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from experiments import nfl_ingame_candidate_evidence_adapter_v2 as harness
from supervisor_harness import opened_train_discovery_worker as worker
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
from data_scientist_harness.co_evolution_loop import micro_pair_hash

common = harness.common
TASK_ID = "InGameTemperatureCloseScorePossessionJointOffset-v1"
ARM_CANDIDATE = "temperature_close_score_possession_joint_offset"
FEATURE_NAMES = ["market_logit", "close_score_possession_interaction"]
STATE_SCHEMA, FORMULA_VERSION = "close_score_possession_numeric_state_v1", "close_score_possession_v1"
FORMULA = "(2*possession_is_home-1)*(1-abs(clip(home_score_diff_pre/14,-1,1)))"
EPSILON, PENALTY = 1e-6, 8.
PARENT_SHA = "0414fcf2db6b564e4719e26f3746c1bdd1cdda216b4cf2bb82235387b5a969eb"
MODULE = "experiments.nfl_ingame_close_score_possession_offset_v1"
BATCH = "market-rsi-coevo-feedback-pilot-20261006-04"
AUTH_SHA = "d7ff6d39de17495de8bedc2d191838630c9d57bc362c9da2b5318ab62879f6d0"

def finite_number(value):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)) or not math.isfinite(float(value)):
        raise ValueError("finite numeric nonboolean input required")
    return float(value)

def derived_feature(score, possession):
    score, possession = finite_number(score), finite_number(possession)
    if possession not in (0., 1.):
        raise ValueError("possession must be exact numeric0/1")
    return (2. * possession - 1.) * (1. - abs(min(1., max(-1., score / 14.))))

def validate_feature():
    fixtures = [(0, 0, -1.), (0, 1, 1.), (7, 1, .5), (-7, 0, -.5), (14, 1, 0.), (-28, 0, 0.)]
    for score, possession, expected in fixtures:
        if derived_feature(score, possession) != expected:
            raise ValueError("candidate-specific close-score semantics failed")
    return {"formula_version": FORMULA_VERSION, "formula": FORMULA, "fixed_numeric_fixtures": len(fixtures),
        "statistical_fits": 0, "attribution": "C-specific formula checks; unchanged score-time H oracle not repurposed"}

def columns(rows):
    if common.base.STATE_FEATURE_NAMES[0] != "home_score_diff_pre" or common.base.STATE_FEATURE_NAMES[2] != "possession_is_home":
        raise ValueError("fixed causal state columns changed")
    for row in rows:
        finite_number(row.trusted["market_probability"])
    raw = harness.parent_module.raw_probabilities(rows)
    p = np.clip(raw, EPSILON, 1. - EPSILON)
    x = [derived_feature(row.state_features[0], row.state_features[2]) for row in rows]
    return np.column_stack((np.log(p / (1. - p)), x))

def prepare_features(rows, frozen, parent_reference):
    receipt = validate_feature()
    if (len(rows) != 193 or len({r.game_id for r in rows}) != 193
            or parent_reference.get("comparison_only") is not True or parent_reference.get("runner_sha256") != PARENT_SHA):
        raise ValueError("fixed193/actual comparison-only score-time parent changed")
    matrix = columns(rows)
    return {}, {**receipt, "feature_names": FEATURE_NAMES, "input_events": 193, "columns": [0, 2],
        "matrix_sha256": common._digest(matrix.tolist()), "future_fields_used": False, "fitted_feature_parameters": 0}

def objective_gradient(theta, matrix, y):
    eta = matrix[:, 0] + matrix @ theta
    value = float(np.sum(np.logaddexp(0., eta) - y * eta) + PENALTY * np.dot(theta, theta))
    return value, matrix.T @ (expit(eta) - y) + 2. * PENALTY * theta

def probabilities(theta, rows):
    theta = np.asarray([finite_number(v) for v in theta])
    if theta.shape != (2,) or theta[0] < -1.:
        raise ValueError("finite beta>=-1/gamma required")
    matrix = columns(rows)
    with np.errstate(over="raise", invalid="raise"):
        eta = matrix[:, 0] + matrix @ theta
    if not np.isfinite(eta).all():
        raise ValueError("nonfinite prediction")
    q = expit(eta); bounded = np.clip(q, EPSILON, 1. - EPSILON)
    return [common.probability_contract.validate_probability(float(v), common.probability_contract.DEFAULT_PROBABILITY_POLICY, ARM_CANDIDATE) for v in bounded], {
        "epsilon": EPSILON, "clipped_rows": int(np.count_nonzero(q != bounded)),
        "lower_clipped_rows": int(np.count_nonzero(q < EPSILON)), "upper_clipped_rows": int(np.count_nonzero(q > 1. - EPSILON)), "rows_removed": 0}

def fit_predict(fit, check, context):
    matrix, check_matrix = columns(fit), columns(check)
    y = common._vector([row.trusted["outcome"] for row in fit], "fit outcomes")
    if not len(fit) or not np.isin(y, [0., 1.]).all():
        raise ValueError("nonempty binary fit outcomes required")
    receipt = {"solver": "scipy_L-BFGS-B", "initial": [0., 0.], "maxiter": 1000, "gtol": 1e-8, "ftol": 0.,
        "optimization_calls_started": 1, "optimization_calls_completed": 0, "model_fits": 1, "retry_count": 0, "fallback_count": 0, "converged": False}
    try:
        result = minimize(objective_gradient, np.zeros(2), args=(matrix, y), jac=True, method="L-BFGS-B",
            bounds=[(-1., None), (None, None)], options={"maxiter": 1000, "gtol": 1e-8, "ftol": 0.})
        theta = np.asarray(result.x, dtype=float); value, gradient = objective_gradient(theta, matrix, y)
        receipt.update(optimization_calls_completed=1, status=int(result.status), iterations=int(result.nit),
            objective=value, gradient=gradient.tolist(), theta=theta.tolist(),
            converged=bool(result.success and np.isfinite(theta).all() and theta[0] >= -1. and math.isfinite(value) and np.isfinite(gradient).all()))
        if not receipt["converged"]:
            raise ValueError("single deterministic optimization failed")
        values, bounding = probabilities(theta, check)
    except Exception as error:
        raise harness.c7.FitFailure(str(error), receipt) from error
    state = {"schema": STATE_SCHEMA, "beta": float(theta[0]), "gamma": float(theta[1]), "fit_events": len(fit),
        "fold_id": context["fold_id"], "epsilon": EPSILON, "penalty": PENALTY, "score_divisor": 14.,
        "formula": FORMULA, "formula_version": FORMULA_VERSION, "probability_transform": "sigmoid_then_fixed_epsilon_clip",
        "optimizer": receipt, "source_sha256": common._sha256(Path(__file__)),
        "fit_matrix_sha256": common._digest(matrix.tolist()), "check_matrix_sha256": common._digest(check_matrix.tolist()),
        "fit_outcome_sha256": common._digest(y.tolist())}
    return values, {"model_fits": 1, "optimizer": receipt, "bounding": bounding,
        "primitive_prediction_state": state, "predictor_state_sha256": common._digest(state)}

def replay_predictor(state, rows, context):
    theta = [finite_number(state["beta"]), finite_number(state["gamma"])]
    expected = {"schema": STATE_SCHEMA, "epsilon": EPSILON, "penalty": PENALTY, "score_divisor": 14.,
        "formula": FORMULA, "formula_version": FORMULA_VERSION, "probability_transform": "sigmoid_then_fixed_epsilon_clip",
        "source_sha256": common._sha256(Path(__file__)), "fold_id": context["fold_id"]}
    optimizer = state["optimizer"]
    if (any(state.get(k) != v or type(state.get(k)) is not type(v) for k, v in expected.items())
            or type(state["fit_events"]) is not int or state["fit_events"] < 1 or optimizer["converged"] is not True
            or optimizer["theta"] != theta or optimizer["initial"] != [0., 0.] or optimizer["solver"] != "scipy_L-BFGS-B"
            or optimizer["maxiter"] != 1000 or optimizer["gtol"] != 1e-8 or optimizer["ftol"] != 0.
            or optimizer["retry_count"] != 0 or optimizer["fallback_count"] != 0
            or optimizer["optimization_calls_started"] != 1 or optimizer["optimization_calls_completed"] != 1
            or state["check_matrix_sha256"] != common._digest(columns(rows).tolist())):
        raise ValueError("primitive recipe/state/input replay changed")
    return probabilities(theta, rows)

def run(source_root, output, binding, *, allow_test_paths=False):
    return harness.run_recipe(source_root, output, binding, prepare_features, fit_predict, replay_predictor, allow_test_paths=allow_test_paths)

def require_admission(source_root, output):
    root = Path(output).resolve().parents[1]; load = common.settlement._strict_json
    authority = root / "authorization.json"
    if worker.sha(authority) != AUTH_SHA:
        raise ValueError("fresh04 authority drift")
    grant = load(authority)
    start, end = [datetime.fromisoformat(grant[k].replace("Z", "+00:00")) for k in ("start_utc", "deadline_utc")]
    request = load(root / "worker" / (Path(output).name + ".request.json")); worker.validate(request, Path(__file__).parents[3])
    binding = load(root / "binding.json"); native = ContinuousDiscoveryBatch(root).snapshot()
    branch = next(x for x in native["branches"] if x["attempt_id"] == request["attempt_id"])
    if (grant["batch_id"] != BATCH or not start <= datetime.now(timezone.utc) < end or request["module"] != MODULE
            or request["candidate_id"] != TASK_ID or request["max_fits"] != 4 or request["attempt_id"] != Path(output).name
            or native["batch_id"] != BATCH or native["max_attempts"] != 1 or native["deadline_utc"] != grant["deadline_utc"]
            or branch["candidate_id"] != TASK_ID
            or branch["stage"] != "execution_claimed" or branch["claim_id"] != request["attempt_id"] + "-claim"
            or request["runtime_pair_sha256"] != micro_pair_hash(native["micro_evolution"])
            or request["spec_sha256"] != binding["candidate_contract_sha256"]
            or Path(source_root).resolve() != worker.TRAIN.resolve()):
        raise ValueError("native fresh04 source/claim/pair/contract mismatch")
    harness.validate_binding(binding, dict(prepare_features=prepare_features, fit_predict=fit_predict, replay_predictor=replay_predictor))
    return binding

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--source-root", required=True); parser.add_argument("--output", required=True)
    args = parser.parse_args(); run(args.source_root, args.output, require_admission(args.source_root, args.output))
