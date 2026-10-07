"""Controller's frozen uncertainty-weighted possession candidate; Train Discovery."""
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
TASK_ID = "InGameTemperatureUncertaintyWeightedPossessionJointOffset-v1"
ARM_CANDIDATE = "temperature_uncertainty_possession_joint_offset"
FEATURE_NAMES = ["market_logit", "uncertainty_weighted_possession"]
STATE_SCHEMA, ALPHA = "temperature_uncertainty_possession_joint_numeric_state_v1", 16.
TRANSFORM = "(2*possession_is_home-1)*4*p*(1-p)"
REPO = Path(__file__).parents[3]
CONTRACT_RELATIVE = "research/market_rsi/supervisor_harness/AUTHORIZED_A1_CONTRACT_2026-10-06.json"
CONTRACT = REPO / CONTRACT_RELATIVE
CONTRACT_SHA256 = "f75ed7a512589991c2179bcdf9b07e1df7b10e4febd3c6cfa50508510be41f6c"
EXECUTION_SPEC_RELATIVE = "research/market_rsi/supervisor_harness/AUTHORIZED_A1_EXECUTION_SPEC_V2_2026-10-06.json"
EXECUTION_SPEC_SHA256 = "2373059edf35c6b476331c53e57da539da7e08b6404b74f4830353120686f709"
RULE_RELATIVE = "research/market_rsi/supervisor_harness/AUTHORIZED_A1_RULE_2026-10-06.json"
RULE_SHA256 = "dc664e498c5982ab2880fdbc80a850e4428c288c00ebe43de9da0fa6c4a48906"
MODULE = "experiments.nfl_ingame_temperature_uncertainty_possession_joint_offset"
SOURCE_REVIEW = "research/market_rsi/supervisor_harness/COEVO_H1_SOURCE_REVIEW_V3_2026-10-05.json"
SOURCE_REVIEW_SHA256 = "13913664f1f24590adcbd265f5d39121e95f2e71615651795242b87d372dd4cb"
PARITY_REVIEW = "research/market_rsi/supervisor_harness/COEVO_H1_LIVE_PARITY_REVIEW_2026-10-05.json"
PARITY_REVIEW_SHA256 = "c619bca98e52d1947b542647644500838dfb1dcdbb3eea803dc5a0b0c0ee9db0"
PROVENANCE_SOURCE = {"research/market_rsi/experiments/nfl_ingame_causal_possession_pressure_offset.py": "4ea2935fb896397b4d21125bb040a0f82ff82be01abd2779717378d3465a0ab3"}
objective_gradient_hessian, solve_joint = math_recipe.objective_gradient_hessian, math_recipe.solve_joint
FitFailure = parent.FitFailure


def utc_now():
    return datetime.now(timezone.utc)


def possession_value(row, anchor=None):
    if common.base.STATE_FEATURE_NAMES[2] != "possession_is_home":
        raise ValueError("frozen preplay possession column changed")
    try:
        encoded = row.state_features[2]
        if isinstance(encoded, (bool, np.bool_)) or not isinstance(encoded, (int, float, np.integer, np.floating)):
            raise ValueError("preplay possession is not numeric")
        value = float(encoded)
        if anchor is not None:
            raw = anchor["possession_is_home"]
            if isinstance(raw, (bool, np.bool_)) or not isinstance(raw, (str, int, float, np.integer, np.floating)):
                raise ValueError("preplay anchor possession is not numeric")
            if float(raw) != value:
                raise ValueError("preplay anchor/state possession differs")
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise ValueError("preplay anchor/state possession missing or invalid") from error
    if not math.isfinite(value) or value not in (0., 1.):
        raise ValueError("preplay possession must be finite exact binary0/1")
    return value


def uncertainty_column(rows, features):
    raw = parent.parent_module.raw_probabilities(rows)
    values = [possession_value(row, {"possession_is_home": features["possession_by_game_id"][row.game_id]}) for row in rows]
    return common._vector([(2 * h - 1) * 4 * p * (1 - p)
                          for h, p in zip(values, raw.tolist(), strict=True)], "uncertainty possession")


def prepare_features(rows, frozen, parent_states):
    parent.parent_module.raw_probabilities(rows)
    if len(rows) != 193 or len({row.game_id for row in rows}) != 193 or set(parent_states) != {1, 2, 3, 4}:
        raise ValueError("uncertainty-possession exact193/fourparentstates changed")
    anchors = {anchor["game_id"]: anchor for anchor in frozen["anchors"]}
    if len(anchors) != len(frozen["anchors"]) or not {row.game_id for row in rows}.issubset(anchors):
        raise ValueError("preplay possession anchor coverage/uniqueness changed")
    values = {row.game_id: possession_value(row, anchors[row.game_id]) for row in rows}
    features = {"possession_by_game_id": values}
    return features, {"feature_names": FEATURE_NAMES, "input_events": 193,
        "anchor_possession_sha256": common._digest(values), "z_sha256": common._digest(uncertainty_column(rows, features).tolist()),
        "column_index": 2, "transform": TRANSFORM, "normalization": "none",
        "fitted_weight_parameters": 0, "other_predictive_state_fields_used": False, "future_fields_used": False}


def probabilities(beta, gamma, rows, features):
    z = uncertainty_column(rows, features)
    if not math.isfinite(beta) or beta < -1 or not math.isfinite(gamma):
        raise ValueError("uncertainty possession requires finite beta>=-1/gamma")
    if gamma == 0.:
        return parent.probabilities(beta, rows)
    with np.errstate(over="raise", invalid="raise"):
        eta = (1 + beta) * np.asarray([row.market_features[0] for row in rows]) + gamma * z
    if not np.isfinite(eta).all():
        raise ValueError("uncertainty possession prediction is nonfinite")
    q = expit(eta)
    bounded = np.clip(q, parent.EPSILON, 1 - parent.EPSILON)
    return [common.probability_contract.validate_probability(float(v), common.probability_contract.DEFAULT_PROBABILITY_POLICY, ARM_CANDIDATE) for v in bounded], {
        "clipped_rows": int(np.count_nonzero(q != bounded)), "lower_clipped_rows": int(np.count_nonzero(q < parent.EPSILON)),
        "upper_clipped_rows": int(np.count_nonzero(q > 1 - parent.EPSILON)), "epsilon": parent.EPSILON,
        "rows_removed": 0, "exact_zero_gamma_parent_identity": True}


def replay_predictor(state, rows, features):
    optimizer = state["optimizer"]
    theta = common._vector([state["beta"], state["gamma"]], "saved uncertainty possession parameters")
    g, h = np.asarray(optimizer["gradient"], dtype=float), np.asarray(optimizer["hessian"], dtype=float)
    kkt = float(max(max(0., -g[0]) if theta[0] == -1 else abs(g[0]), abs(g[1]))) if g.shape == (2,) else math.inf
    gamma_bound, beta_bound = 1 + state["fit_z_absolute_sum"] / ALPHA, 1 + state["fit_logit_absolute_sum"] / ALPHA
    if (state["schema"] != STATE_SCHEMA or state["feature_columns"] != FEATURE_NAMES or state["alpha"] != ALPHA
            or state["lower_bound"] != -1 or state["intercept"] != 0 or state["transform"] != TRANSFORM
            or state["column_index"] != 2 or state["column_name"] != common.base.STATE_FEATURE_NAMES[2]
            or not math.isfinite(state["fit_z_absolute_sum"]) or not 0 <= state["fit_z_absolute_sum"] <= state["fit_events"]
            or not math.isfinite(state["fit_logit_absolute_sum"]) or state["fit_logit_absolute_sum"] < 0
            or state["normalization"] != "none" or state["sample_weights"] is not None
            or state["contract_sha256"] != CONTRACT_SHA256 or state["execution_spec_sha256"] != EXECUTION_SPEC_SHA256
            or state["source_sha256"] != common._sha256(Path(__file__))
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
        raise ValueError("saved uncertainty possession recipe/optimizer changed")
    if (state["raw_check_sha256"] != common._digest(parent.parent_module.raw_probabilities(rows).tolist())
            or state["possession_check_sha256"] != common._digest([possession_value(row) for row in rows])
            or state["z_check_sha256"] != common._digest(uncertainty_column(rows, features).tolist())):
        raise ValueError("saved uncertainty possession prediction inputs changed")
    return probabilities(*theta, rows, features)


def fit_predict(fit, check, features):
    saved_parent, fold = features["parent_state"], features["fold_id"]
    parent.replay_predictor(saved_parent, check)
    parent.parent_module.raw_probabilities(fit)
    if fold not in (1, 2, 3, 4) or saved_parent["fit_events"] != len(fit):
        raise ValueError("uncertainty possession past-parent fold/count changed")
    logits, z = [row.market_features[0] for row in fit], uncertainty_column(fit, features).tolist()
    theta, receipt = solve_joint(logits, z, [row.trusted["outcome"] for row in fit], saved_parent["beta"])
    try:
        state = {"schema": STATE_SCHEMA, "feature_columns": FEATURE_NAMES, "beta": float(theta[0]), "gamma": float(theta[1]),
            "temperature": 1 + float(theta[0]), "alpha": ALPHA, "lower_bound": -1., "intercept": 0, "transform": TRANSFORM,
            "column_index": 2, "column_name": "possession_is_home", "normalization": "none", "sample_weights": None,
            "fit_events": len(fit), "fold_id": fold, "fit_z_absolute_sum": math.fsum(abs(value) for value in z),
            "fit_logit_absolute_sum": math.fsum(abs(value) for value in logits), "contract_sha256": CONTRACT_SHA256,
            "execution_spec_sha256": EXECUTION_SPEC_SHA256, "source_sha256": common._sha256(Path(__file__)),
            "parent_state_sha256": common._digest(saved_parent), "fit_inputs_sha256": common._digest([logits, z]),
            "raw_check_sha256": common._digest(parent.parent_module.raw_probabilities(check).tolist()),
            "possession_check_sha256": common._digest([possession_value(row) for row in check]),
            "z_check_sha256": common._digest(uncertainty_column(check, features).tolist()),
            "optimizer": receipt, "optimizer_sha256": common._digest(receipt)}
        values, bounding = probabilities(*theta, check, features)
        if (values, bounding) != replay_predictor(state, check, features):
            raise ValueError("uncertainty possession numeric replay differs")
    except Exception as error:
        raise FitFailure(str(error), {**receipt, "post_optimization_prediction_error": str(error)[:600]}) from error
    return values, {"model_fits": 1, "fit_events": len(fit), "fit_parameters": 2, "input_columns": 2, "fit_only": True,
        "optimizer": receipt, "bounding": bounding, "numeric_replay_exact": True,
        "primitive_prediction_state": state, "predictor_state_sha256": common._digest(state)}


def require_admission(source_root, output):
    for relative, digest in ((CONTRACT_RELATIVE, CONTRACT_SHA256), (EXECUTION_SPEC_RELATIVE, EXECUTION_SPEC_SHA256), (RULE_RELATIVE, RULE_SHA256)):
        if (REPO / relative).is_symlink() or common._sha256(REPO / relative) != digest:
            raise ValueError("A1 frozen scientific contract/execution spec/rule changed")
    contract, spec = [common.settlement._strict_json(REPO / relative) for relative in (CONTRACT_RELATIVE, EXECUTION_SPEC_RELATIVE)]
    resources = spec["resources"]
    start, deadline = [datetime.fromisoformat(resources[key].replace("Z", "+00:00")) for key in ("start_utc", "deadline_utc")]
    if not start <= utc_now() < deadline:
        raise ValueError("A1 execution authority expired or not started")
    output = Path(output)
    if output.is_symlink() or output.parent.name != "runs" or not output.name:
        raise ValueError("A1 output must be exclusive worker pilot/runs/attempt")
    request_path = output.parents[1] / "worker" / f"{output.name}.request.json"
    if request_path.is_symlink():
        raise ValueError("A1 request is symlinked")
    request = common.settlement._strict_json(request_path)
    if (request["attempt_id"] != output.name or request["candidate_id"] != TASK_ID or request["module"] != MODULE
            or request["spec_sha256"] != CONTRACT_SHA256 or type(request["max_fits"]) is not int or request["max_fits"] != 4
            or type(request["max_wall_seconds"]) is not int or not 0 < request["max_wall_seconds"] <= 900
            or request["python"] != resources["python"] or request["python_sha256"] != resources["python_sha256"]
            or spec["scientific_contract_path"] != CONTRACT_RELATIVE or spec["candidate_id"] != contract["candidate_id"]
            or spec["research_parent"]["runner_sha256"] != contract["actual_parent_sha256"]
            or spec["comparison_incumbent"]["sha256"] != contract["comparison_incumbent_sha256"]):
        raise ValueError("A1 exact request/spec/runtime/parent changed")
    worker.validate(request, REPO)
    binding = harness.held_c7_binding()
    dependencies = {**binding["dependency_source_hashes"], **{str((Path(__file__).parents[3] / path).resolve()): digest for path, digest in spec["reuse_helpers"].items()},
        **{str((Path(__file__).parents[3] / path).resolve()): digest for path, digest in PROVENANCE_SOURCE.items()}}
    required = {str(Path(path).relative_to(Path(__file__).parents[3])): digest for path, digest in dependencies.items()}
    required.update({CONTRACT_RELATIVE: CONTRACT_SHA256, EXECUTION_SPEC_RELATIVE: EXECUTION_SPEC_SHA256, RULE_RELATIVE: RULE_SHA256,
        SOURCE_REVIEW: SOURCE_REVIEW_SHA256, PARITY_REVIEW: PARITY_REVIEW_SHA256,
        str(harness.CONTRACT.relative_to(Path(__file__).parents[3])): harness.CONTRACT_SHA256,
        str(Path(__file__).relative_to(Path(__file__).parents[3])): common._sha256(Path(__file__))})
    if any(request["files"].get(path) != digest for path, digest in required.items()):
        raise ValueError("A1 exact source/helper/contract/spec coverage changed")
    review, parity = [common.settlement._strict_json(REPO / path) for path in (SOURCE_REVIEW, PARITY_REVIEW)]
    if review.get("passed") is not True or review.get("source_sha256") != binding["adapter_source_sha256"] or review.get("verdict") != "EXACT_SOURCE_ADMITTED_FOR_ONE_BOUNDED_HELD_C7_TRIAL":
        raise ValueError("A1 H source is not independently admitted")
    expected = {"verdict": "PASS", "adapter_source_sha256": binding["adapter_source_sha256"], "source_review_sha256": SOURCE_REVIEW_SHA256,
        "predictions_exact": True, "predictor_states_exact": True, "original_scorecard_fields_exact": True, "fit_calls_entered": 4,
        "fit_calls_completed": 4, "control_refits": 0, "same_id_retries": 0, "source_K_C_worker_unchanged": True,
        "scope": "H1 held-C7 parity only; no predictive/R/automatic-continuation gain"}
    if any(type(parity.get(key)) is not type(value) or parity.get(key) != value for key, value in expected.items()):
        raise ValueError("A1 H live parity gate failed")
    own_path = str(Path(__file__).resolve())
    dependencies.update({own_path: common._sha256(Path(__file__)), str((REPO / CONTRACT_RELATIVE).resolve()): CONTRACT_SHA256,
        str((REPO / EXECUTION_SPEC_RELATIVE).resolve()): EXECUTION_SPEC_SHA256, str((REPO / RULE_RELATIVE).resolve()): RULE_SHA256})
    binding.update(candidate_id=TASK_ID, arm=ARM_CANDIDATE, candidate_source_path=own_path, candidate_source_sha256=dependencies[own_path],
        candidate_contract_path=str((REPO / EXECUTION_SPEC_RELATIVE).resolve()), candidate_contract_sha256=EXECUTION_SPEC_SHA256,
        scientific_contract_sha256=CONTRACT_SHA256, research_parent=spec["research_parent"], feature_names=FEATURE_NAMES,
        comparison_incumbent_sha256=contract["comparison_incumbent_sha256"], attribution=spec["attribution"], dependency_source_hashes=dependencies)
    binding["callback_source_bindings"] = {name: own_path for name in ("prepare_features", "fit_predict", "replay_predictor")}
    harness.validate_binding(binding, {name: globals()[name] for name in binding["callback_source_bindings"]})
    return binding


def run(source_root, output, *, allow_test_paths=False):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError("A1 output already exists; inspect without relaunch")
    try:
        binding = require_admission(source_root, output)
        if not allow_test_paths and Path(source_root).resolve() != worker.TRAIN.resolve():
            raise ValueError("A1 source is not resident authorized Train")
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


if __name__ == "__main__": main()
