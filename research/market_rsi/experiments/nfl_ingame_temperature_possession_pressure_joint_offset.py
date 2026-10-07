"""Frozen temperature plus native pressure; historical Train Discovery only."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
from scipy.special import expit
from experiments import nfl_ingame_market_temperature_offset as parent
from experiments import nfl_ingame_causal_possession_pressure_offset as pressure

common = parent.common
TASK_ID = "InGameTemperaturePossessionPressureJointOffset-v1"
ARM_CANDIDATE = "temperature_possession_pressure_joint_offset"
FEATURE_NAMES = ["market_logit", "native_possession_pressure"]
ALPHA, LOWER_BOUND, MAX_SWEEPS, MAX_STEPS = 16., -1., 100, 200
COORD_TOLERANCE, KKT_TOLERANCE = 1e-10, 1e-8
CONTRACT = Path(__file__).parents[1] / "supervisor_harness" / "COEVO_D1_CONTRACT_2026-10-05.json"
CONTRACT_SHA256 = "36f69b7006c341133665c3393c1a71c4e1ff2677e677685081b95f50910eb6e7"
STATE_SCHEMA = "temperature_possession_pressure_numeric_state_v1"
FitFailure = parent.FitFailure


def objective_gradient_hessian(theta, logits, phi, outcomes):
    theta = common._vector(theta, "two joint parameters")
    l, p, y = [common._vector(v, n) for v, n in zip((logits, phi, outcomes),
        ("fit logits", "fit pressure", "fit outcomes"), strict=True)]
    if theta.shape != (2,) or theta[0] < LOWER_BOUND or l.shape != p.shape or l.shape != y.shape or np.any((y != 0) & (y != 1)):
        raise ValueError("joint objective requires aligned finite binary inputs and beta>=-1")
    with np.errstate(over="raise", invalid="raise"):
        eta = (1 + theta[0]) * l + theta[1] * p
        q, x = expit(eta), np.column_stack((l, p))
        value = float(np.sum(np.logaddexp(0., eta) - y * eta) + .5 * ALPHA * (theta @ theta))
        gradient = x.T @ (q - y) + ALPHA * theta
        hessian = x.T @ (q[:, None] * (1 - q[:, None]) * x) + ALPHA * np.eye(2)
    if not math.isfinite(value) or not np.isfinite(gradient).all() or not np.isfinite(hessian).all() or np.linalg.eigvalsh(hessian).min() < ALPHA - 1e-10:
        raise ValueError("joint objective/derivatives nonfinite or curvature below16")
    return value, gradient, hessian


def _kkt(theta, gradient):
    return float(max(max(0., -gradient[0]) if theta[0] == LOWER_BOUND else abs(gradient[0]), abs(gradient[1])))


def solve_joint(logits, phi, outcomes, warm_beta):
    receipt = {"model_fits": 1, "solver": "cyclic_coordinate_bisection_beta_then_gamma", "alpha": ALPHA,
        "max_sweeps": MAX_SWEEPS, "max_coordinate_steps": MAX_STEPS, "coordinate_tolerance": COORD_TOLERANCE,
        "joint_tolerance": KKT_TOLERANCE, "evaluations": 0, "sweeps": 0, "sweeps_started": 0, "coordinate_updates": 0,
        "coordinate_bisection_steps": 0, "coordinates": [], "optimization_calls_started": 1,
        "optimization_calls_completed": 0, "retry_count": 0, "fallback_count": 0}
    try:
        l, p, y = [common._vector(v, n) for v, n in zip((logits, phi, outcomes), ("logits", "pressure", "outcomes"), strict=True)]
        theta = common._vector([warm_beta, 0.], "past-parent warmstart")
        brackets = [[LOWER_BOUND, 1 + math.fsum(abs(float(v)) for v in l) / ALPHA],
            [-1 - math.fsum(abs(float(v)) for v in p) / ALPHA, 1 + math.fsum(abs(float(v)) for v in p) / ALPHA]]
        receipt.update({"warmstart": theta.tolist(), "theta": theta.tolist(), "fit_only_brackets": brackets})
        def evaluate(point):
            receipt["evaluations"] += 1
            value, g, h = objective_gradient_hessian(point, l, p, y)
            if (not math.isfinite(value) or np.asarray(g).shape != (2,) or np.asarray(h).shape != (2, 2)
                    or not np.isfinite(g).all() or not np.isfinite(h).all() or not np.allclose(h, h.T, rtol=0, atol=1e-10)
                    or np.linalg.eigvalsh(h).min() < ALPHA - 1e-10):
                raise ValueError("joint evaluator returned invalid finite F/g/H")
            receipt["last_evaluation"] = {"theta": point.tolist(), "F": value, "gradient": g.tolist(), "hessian": h.tolist()}
            return value, g, h
        initial, gradient, hessian = evaluate(theta)
        receipt["F_warmstart"] = initial
        for sweep in range(MAX_SWEEPS + 1):
            value, gradient, hessian = evaluate(theta)
            receipt.update({"theta": theta.tolist(), "F": value, "gradient": gradient.tolist(),
                "hessian": hessian.tolist(), "KKT": _kkt(theta, gradient)})
            if value > initial + KKT_TOLERANCE:
                raise ValueError("joint objective worsened beyond fixed tolerance")
            if receipt["KKT"] <= KKT_TOLERANCE:
                receipt.update({"converged": True, "optimization_calls_completed": 1})
                return theta, receipt
            if sweep == MAX_SWEEPS:
                raise ValueError("joint100sweep cap without joint stationarity")
            receipt["sweeps_started"] = sweep + 1
            for index, bracket in enumerate(brackets):
                low, high = bracket
                coordinate = {"sweep": sweep + 1, "index": index, "initial_bracket": bracket.copy(), "steps": 0}
                receipt["coordinates"].append(coordinate)
                def derivative(at):
                    point = theta.copy()
                    point[index] = at
                    return float(evaluate(point)[1][index])
                low_g, high_g = derivative(low), derivative(high)
                coordinate.update({"endpoint_gradients": [low_g, high_g], "final_bracket": [low, high]})
                if high_g <= 0 or (index == 1 and low_g >= 0):
                    raise ValueError("joint fit-only coordinate bracket failed")
                if index == 0 and low_g >= 0:
                    chosen = LOWER_BOUND
                elif abs(derivative(float(theta[index]))) <= COORD_TOLERANCE:
                    chosen = float(theta[index])
                else:
                    chosen = None
                    for step in range(1, MAX_STEPS + 1):
                        midpoint = float(low + (high - low) / 2)
                        if midpoint in (low, high):
                            raise ValueError("joint coordinate bisection stagnated")
                        coordinate["steps"] = step
                        receipt["coordinate_bisection_steps"] += 1
                        g = derivative(midpoint)
                        if abs(g) <= COORD_TOLERANCE:
                            chosen = midpoint
                            break
                        if g > 0:
                            high = midpoint
                        else:
                            low = midpoint
                        coordinate["final_bracket"] = [low, high]
                    if chosen is None:
                        raise ValueError("joint200coordinate cap without stationarity")
                theta[index] = chosen
                receipt["theta"] = theta.tolist()
                receipt["coordinate_updates"] += 1
                coordinate["chosen"] = chosen
            receipt["sweeps"] = sweep + 1
        raise ValueError("unreachable joint solver exit")
    except Exception as error:
        receipt.update({"converged": False, "error_type": type(error).__name__, "error": str(error)[:600]})
        raise FitFailure(str(error), receipt) from error


def prepare_features(rows, frozen, parent_states):
    anchors = frozen["anchors"]
    states = {state["game_id"]: state for state in anchors}
    if len(rows) != 193 or len({row.game_id for row in rows}) != 193 or len(states) != len(anchors) or not {row.game_id for row in rows} <= states.keys() or set(parent_states) != {1, 2, 3, 4}:
        raise ValueError("joint exact193 coverage/anchor uniqueness/fourparentstates changed")
    values = {row.game_id: pressure.possession_pressure(states[row.game_id]) for row in rows}
    parent.parent_module.raw_probabilities(rows)
    return {"pressure": values}, {"feature_names": FEATURE_NAMES, "scaling": "none", "intercept": 0,
        "input_events": len(rows), "pressure_sha256": common._digest(values), "future_fields_used": False}


def probabilities(beta, gamma, rows, features):
    raw = parent.parent_module.raw_probabilities(rows)
    if not math.isfinite(beta) or beta < LOWER_BOUND or not math.isfinite(gamma):
        raise ValueError("joint coefficients must be finite with beta>=-1")
    p = common._vector([features["pressure"][row.game_id] for row in rows], "check pressure")
    if np.any(np.abs(p) > 1):
        raise ValueError("joint pressure exceeds fixed native bounds")
    if gamma == 0.:
        return parent.probabilities(beta, rows)
    with np.errstate(over="raise", invalid="raise"):
        eta = (1 + beta) * np.asarray([row.market_features[0] for row in rows]) + gamma * p
    if not np.isfinite(eta).all():
        raise ValueError("joint predictor became nonfinite")
    q = expit(eta)
    bounded = np.clip(q, parent.EPSILON, 1 - parent.EPSILON)
    return [common.probability_contract.validate_probability(float(v), common.probability_contract.DEFAULT_PROBABILITY_POLICY, ARM_CANDIDATE) for v in bounded], {
        "clipped_rows": int(np.count_nonzero(q != bounded)), "lower_clipped_rows": int(np.count_nonzero(q < parent.EPSILON)),
        "upper_clipped_rows": int(np.count_nonzero(q > 1 - parent.EPSILON)), "epsilon": parent.EPSILON,
        "rows_removed": 0, "exact_zero_gamma_parent_identity": True}


def replay_predictor(state, rows, features):
    optimizer = state["optimizer"]
    theta = common._vector([state["beta"], state["gamma"]], "saved joint parameters")
    g, h = np.asarray(optimizer["gradient"], dtype=float), np.asarray(optimizer["hessian"], dtype=float)
    if (state["schema"] != STATE_SCHEMA or state["feature_columns"] != FEATURE_NAMES or state["alpha"] != ALPHA
            or state["lower_bound"] != LOWER_BOUND or state["intercept"] != 0 or state["normalization"] != "none"
            or state["sample_weights"] is not None or state["contract_sha256"] != CONTRACT_SHA256
            or state["optimizer_sha256"] != common._digest(optimizer)
            or state["source_sha256"] != common._sha256(Path(__file__)) or state["temperature"] != 1 + theta[0]
            or state["fold_id"] != features["fold_id"] or state["parent_state_sha256"] != common._digest(features["parent_state"])
            or optimizer["theta"] != theta.tolist() or optimizer["converged"] is not True or optimizer["alpha"] != ALPHA
            or optimizer["solver"] != "cyclic_coordinate_bisection_beta_then_gamma" or optimizer["retry_count"] != 0 or optimizer["fallback_count"] != 0
            or optimizer["optimization_calls_started"] != 1 or optimizer["optimization_calls_completed"] != 1
            or optimizer["max_sweeps"] != MAX_SWEEPS or optimizer["max_coordinate_steps"] != MAX_STEPS
            or optimizer["coordinate_tolerance"] != COORD_TOLERANCE or optimizer["joint_tolerance"] != KKT_TOLERANCE
            or not 0 <= optimizer["sweeps"] <= MAX_SWEEPS or optimizer["sweeps_started"] != optimizer["sweeps"]
            or optimizer["coordinate_updates"] != 2 * optimizer["sweeps"]
            or optimizer["warmstart"] != [features["parent_state"]["beta"], 0.]
            or state["fit_events"] != features["parent_state"]["fit_events"] or g.shape != (2,) or h.shape != (2, 2)
            or not np.isfinite(g).all() or not np.isfinite(h).all() or not np.allclose(h, h.T, rtol=0, atol=1e-10)
            or np.linalg.eigvalsh(h).min() < ALPHA - 1e-10
            or not all(math.isfinite(optimizer[k]) for k in ("F", "F_warmstart", "KKT"))
            or optimizer["KKT"] != _kkt(theta, g) or optimizer["KKT"] > KKT_TOLERANCE
            or optimizer["F"] > optimizer["F_warmstart"] + KKT_TOLERANCE):
        raise ValueError("saved joint primitive state/recipe/optimizer changed")
    raw = parent.parent_module.raw_probabilities(rows).tolist()
    p = [features["pressure"][row.game_id] for row in rows]
    if state["raw_check_sha256"] != common._digest(raw) or state["pressure_check_sha256"] != common._digest(p):
        raise ValueError("saved joint prediction inputs changed")
    return probabilities(*theta, rows, features)


def fit_predict(fit, check, features):
    saved_parent, fold = features["parent_state"], features["fold_id"]
    parent.replay_predictor(saved_parent, check)
    if fold not in (1, 2, 3, 4) or saved_parent["fit_events"] != len(fit):
        raise ValueError("joint explicit past-parent fold/fit count changed")
    parent.parent_module.raw_probabilities(fit)
    l = [row.market_features[0] for row in fit]
    phi = common._vector([features["pressure"][row.game_id] for row in fit], "fit pressure").tolist()
    if any(abs(value) > 1 for value in phi):
        raise ValueError("joint fit pressure exceeds frozen physical bounds")
    theta, receipt = solve_joint(l, phi, [row.trusted["outcome"] for row in fit], saved_parent["beta"])
    try:
        state = {"schema": STATE_SCHEMA, "feature_columns": FEATURE_NAMES, "beta": float(theta[0]), "gamma": float(theta[1]),
            "temperature": 1 + float(theta[0]), "alpha": ALPHA, "lower_bound": LOWER_BOUND, "intercept": 0,
            "normalization": "none", "sample_weights": None, "fit_events": len(fit), "fold_id": fold,
            "contract_sha256": CONTRACT_SHA256, "source_sha256": common._sha256(Path(__file__)),
            "parent_state_sha256": common._digest(saved_parent), "fit_inputs_sha256": common._digest([l, phi]),
            "raw_check_sha256": common._digest(parent.parent_module.raw_probabilities(check).tolist()),
            "pressure_check_sha256": common._digest([features["pressure"][row.game_id] for row in check]),
            "optimizer": receipt, "optimizer_sha256": common._digest(receipt)}
        values, bounding = probabilities(*theta, check, features)
        replayed, bounds = replay_predictor(state, check, features)
        if values != replayed or bounding != bounds:
            raise ValueError("joint numeric predictor replay differs")
    except Exception as error:
        raise FitFailure(str(error), {**receipt, "post_optimization_prediction_error": str(error)[:600]}) from error
    return values, {"model_fits": 1, "fit_events": len(fit), "fit_parameters": 2, "input_columns": 2,
        "fit_only": True, "optimizer": receipt, "bounding": bounding, "numeric_replay_exact": True,
        "primitive_prediction_state": state, "predictor_state_sha256": common._digest(state)}


def run(source_root, output, *, binding=None, allow_test_paths=False):
    # H1 is separately admitted and its exact source binding must be frozen by integration.
    if binding is None:
        raise RuntimeError("D1 H1 source/binding not yet independently admitted; execution refused")
    from experiments import nfl_ingame_candidate_evidence_adapter as harness
    return harness.run_recipe(source_root, output, binding, prepare_features, fit_predict, replay_predictor, allow_test_paths=allow_test_paths)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(common.settlement.json.dumps(run(args.source_root, args.output), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
