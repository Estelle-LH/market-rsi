from __future__ import annotations

from collections import defaultdict
import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np
from scipy.special import expit

from experiments import nfl_ingame_curvature_unit_matched_brier_joint_offset as candidate
from experiments import test_nfl_ingame_prior_play_volume_unit_scale_joint_offset as parent_tests
from experiments import test_nfl_ingame_market_freshness_interaction_offset as old_tests


def problem():
    return parent_tests.problem()


def bundle_for(fit, check, features):
    _, receipt = candidate.design_receipt(fit, check, features)
    return {"features": features, "expected_by_keys": {tuple(row.key for row in check): receipt}}


def numeric_parent_state(fit, check, features):
    """Direct synthetic C4 authoring: never train a parent or inspect Train."""
    _, receipt = candidate.design_receipt(fit, check, features)
    scale, theta = receipt["volume_scale"], [.002, -.01]
    return {"schema": "prior_play_volume_unit_scale_joint_numeric_state_v1",
        "column_order": candidate.COLUMNS, "native_columns": candidate.native.COLUMNS,
        "volume_formula": candidate.volume.FORMULA, "freshness_formula": candidate.native.FRESHNESS_FORMULA,
        **receipt, "scale_ddof": 0, "scale_fit_only": True, "scale_only": True,
        "coefficients": theta, "native_volume_coefficient": theta[0] / scale,
        "effective_native_volume_penalty": 16 * scale * scale,
        "market_coefficient": 1, "intercept": False, "penalty_per_coordinate": 16,
        "synthetic_fixture": True}


def synthetic_parent_states(rows, folds, features):
    by_date = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    probabilities, states = {}, {}
    for fold in folds:
        check = sorted([row for day in fold["check_dates"] for row in by_date[day]], key=lambda row: row.key)
        fit, unavailable = candidate.common.nested._strict_prior_rows(by_date, fold["fit_dates"], check)
        assert not unavailable
        state = numeric_parent_state(fit, check, features)
        states[fold["fold"]] = state
        probabilities.update({row.key: p for row, p in zip(check,
            candidate.parent_module.replay_unit(state, check, features), strict=True)})
    return probabilities, states


def synthetic_parent_artifacts(root):
    evidence, controls, frozen, expected_key = parent_tests.synthetic_parent_artifacts(root)
    states = {"task_id": candidate.parent_module.TASK_ID, "folds": []}
    reports = {"task_id": candidate.parent_module.TASK_ID, "folds": []}
    rows, _, _, features = problem()
    for fold, fit_events in enumerate((106, 132, 148, 176), start=1):
        state = numeric_parent_state(rows[:22], rows[22:], features)
        state["fit_events"] = fit_events
        digest = candidate.common._digest(state)
        states["folds"].append({"fold": fold, "state": state, "state_sha256": digest})
        reports["folds"].append({"fold": fold, "trainer": {"predictor_state_sha256": digest}})
    receipts = {"task_id": candidate.parent_module.TASK_ID, "runner_sha256": candidate.PARENT_SOURCE_SHA256,
        "controller_contract_sha256": candidate.parent_module.CONTRACT_SHA256,
        "v0_artifact_hashes": frozen["hashes"], **frozen["receipts"], **candidate.common.BOUNDARY_FLAGS}
    lock = {"task_id": candidate.parent_module.TASK_ID,
        "controller_contract_sha256": candidate.parent_module.CONTRACT_SHA256}
    for name, value in (("predictor_states", states), ("scorecard", reports),
            ("input_receipts", receipts), ("pre_score_lock", lock)):
        candidate.common.base._atomic_json(root / f"{name}.json", value)
    manifest = candidate.common.settlement._strict_json(root / "manifest.json")
    manifest["task_id"] = candidate.parent_module.TASK_ID
    for name in ("predictor_states", "scorecard", "input_receipts", "pre_score_lock", "exclusions"):
        manifest[f"{name}_sha256"] = candidate.common._sha256(root / f"{name}.json")
    candidate.common.base._atomic_json(root / "manifest.json", manifest)
    files = ("manifest.json", "input_receipts.json", "pre_score_lock.json", "exclusions.json",
        "predictor_states.json", "scorecard.json", "predictions.csv")
    hashes = {name: candidate.common._sha256(root / name) for name in files}
    evidence["research_parent"].update({"candidate_id": candidate.parent_module.TASK_ID,
        "artifact_hashes": hashes, "state_schema": "prior_play_volume_unit_scale_joint_numeric_state_v1",
        "state_sha256_by_fold": [item["state_sha256"] for item in states["folds"]],
        **{name.split(".")[0] + "_sha256": digest for name, digest in hashes.items()}})
    return evidence, controls, frozen, expected_key


def optimizer_result(x, *, success=False, message="finite early-ftol fixture"):
    return SimpleNamespace(x=np.asarray(x), success=success, status=2, message=message,
        nit=1, nfev=2, njev=2, fun=1., jac=np.zeros(2))


class CurvatureUnitMatchedBrierJointOffsetTests(unittest.TestCase):
    def test_analytic_objective_gradient_hessian_and_finite_differences(self):
        rng = np.random.default_rng(20260929)
        x, offsets = rng.normal(size=(19, 2)), rng.normal(size=19)
        y, theta, penalty = rng.integers(0, 2, 19), np.asarray([.17, -.29]), np.asarray([2.3, 3.7])
        value, gradient, hessian = candidate.objective_gradient_hessian(theta, x, y, offsets, penalty)
        q = expit(offsets + x @ theta)
        u, error = q * (1 - q), q - y
        self.assertAlmostEqual(value, float(np.sum(error ** 2) + .5 * np.sum(penalty * theta ** 2)), places=14)
        np.testing.assert_allclose(gradient, 2 * x.T @ (error * u) + penalty * theta, rtol=0, atol=1e-14)
        np.testing.assert_allclose(hessian, x.T @ (x * (2 * (u ** 2 + error * u * (1 - 2 * q)))[:, None])
            + np.diag(penalty), rtol=0, atol=1e-14)
        for j in range(2):
            delta = np.eye(2)[j] * 1e-5
            high = candidate.objective_gradient_hessian(theta + delta, x, y, offsets, penalty)
            low = candidate.objective_gradient_hessian(theta - delta, x, y, offsets, penalty)
            self.assertAlmostEqual(gradient[j], (high[0] - low[0]) / 2e-5, places=7)
            np.testing.assert_allclose(hessian[:, j], (high[1] - low[1]) / 2e-5, rtol=0, atol=1e-8)

    def test_fit_only_expected_diagonal_curvature_units_not_observed_hessian(self):
        x = np.asarray([[1., -.3], [-.2, 2.], [.7, .8]])
        raw = np.asarray([.2, .5, .8])
        units = candidate.curvature_units(x, raw)
        v = raw * (1 - raw)
        d, n = np.sum(v[:, None] * x ** 2, axis=0), np.sum(2 * v[:, None] ** 2 * x ** 2, axis=0)
        np.testing.assert_array_equal(units["d"], d)
        np.testing.assert_array_equal(units["n"], n)
        np.testing.assert_array_equal(units["r"], n / d)
        np.testing.assert_array_equal(units["lambda"], 16 * n / d)
        self.assertEqual((units["fit_only"], units["uses_labels"], units["uses_check_rows"]), (True, False, False))
        # Conditional Bernoulli expectation at theta=0, not an observed-label Hessian claim.
        actual = np.zeros((2, 2))
        for row, p in zip(x, raw, strict=True):
            offset = np.asarray([np.log(p / (1 - p))])
            h0 = candidate.objective_gradient_hessian([0., 0.], row[None, :], [0], offset, [1., 1.])[2] - np.eye(2)
            h1 = candidate.objective_gradient_hessian([0., 0.], row[None, :], [1], offset, [1., 1.])[2] - np.eye(2)
            actual += (1 - p) * h0 + p * h1
        np.testing.assert_allclose(np.diag(actual), n, rtol=0, atol=1e-15)
        with self.assertRaisesRegex(ValueError, "positive; no floor"):
            candidate.curvature_units(np.column_stack((x[:, 0], np.zeros(3))), raw)
        for bad_x, bad_p in ((x, [0., .5, .8]), (x, [np.nan, .5, .8]), (x * np.inf, raw), (x[:, :1], raw)):
            with self.subTest(bad_p=bad_p), self.assertRaises(ValueError):
                candidate.curvature_units(bad_x, bad_p)

    def test_actual_synthetic_optimizer_determinism_strict_local_acceptance(self):
        rows, _, _, features = problem()
        x = candidate.parent_module.scaled_design(rows[:22], rows[22:], features)[2]
        y, offsets = np.asarray([row.trusted["outcome"] for row in rows[:22]]), np.asarray([row.market_features[0] for row in rows[:22]])
        penalty = np.asarray(candidate.curvature_units(x, candidate.sibling.raw_probabilities(rows[:22]))["lambda"])
        first, receipt = candidate.optimize_brier(x, y, offsets, penalty)
        second, repeated = candidate.optimize_brier(x, y, offsets, penalty)
        np.testing.assert_array_equal(first, second)
        self.assertEqual(receipt, repeated)
        self.assertEqual((receipt["model_fits"], receipt["restart_count"], receipt["retry_count"]), (1, 0, 0))
        self.assertTrue(receipt["same_objective_and_lambda_all_phases"])
        self.assertTrue(receipt["local_not_global_optimum"])
        self.assertEqual(receipt["phase1"]["options"], candidate.OPTIONS)
        self.assertLessEqual(receipt["stationarity"]["gradient_infinity_norm"], 1e-8)
        self.assertTrue(all(value > 0 for value in receipt["stationarity"]["hessian_eigenvalues"]))
        self.assertLessEqual(receipt["phase2"]["iterations"], 25)
        self.assertEqual(receipt["phase2"]["initial"], receipt["phase1"]["returned_x"])
        for step in receipt["phase2"]["steps"]:
            self.assertLessEqual(step["proposals"], 60)
            self.assertLessEqual(step["objective_after"], step["objective_before"]
                - 1e-4 * step["alpha"] * step["gradient_dot_direction"])

    def test_finite_unsuccessful_ftol_continuation_preserves_status_same_prior_no_restart(self):
        x = np.asarray([[1., .2], [-.5, 1.], [.3, -.7], [1.2, .8]])
        y, offsets, penalty = np.asarray([1, 0, 1, 0]), np.asarray([.2, -.1, .6, -.3]), np.asarray([2., 3.])
        start = np.asarray([.01, -.02])
        observed = []
        original = candidate.objective_gradient_hessian
        def evaluate(theta, matrix, labels, off, prior):
            observed.append((np.asarray(theta).copy(), np.asarray(prior).copy()))
            return original(theta, matrix, labels, off, prior)
        for success in (False, True):
            with self.subTest(success=success), mock.patch.object(candidate, "minimize",
                    return_value=optimizer_result(start, success=success)) as minimize, \
                    mock.patch.object(candidate, "objective_gradient_hessian", side_effect=evaluate):
                theta, receipt = candidate.optimize_brier(x, y, offsets, penalty)
            self.assertEqual(minimize.call_count, 1)
            np.testing.assert_array_equal(minimize.call_args.args[1], [0., 0.])
            self.assertEqual(receipt["phase1"]["success"], success)
            self.assertEqual(receipt["phase1"]["message"], "finite early-ftol fixture")
            self.assertEqual(receipt["phase2"]["initial"], start.tolist())
            self.assertEqual(receipt["phase2"]["steps"][0]["from_x"], start.tolist())
            self.assertGreater(receipt["phase2"]["iterations"], 0)
            self.assertGreater(max(abs(value) for value in receipt["phase1"]["independent_gradient"]), 1e-8)
            self.assertLessEqual(receipt["stationarity"]["gradient_infinity_norm"], 1e-8)
            self.assertNotEqual(theta.tolist(), [0., 0.])
        for _, prior in observed:
            np.testing.assert_array_equal(prior, penalty)

    def test_phase1_success_not_gradient_evidence_and_stationary_zero_step(self):
        args = (np.eye(2), np.asarray([1, 0]), np.zeros(2), np.ones(2))
        with mock.patch.object(candidate, "minimize", return_value=optimizer_result([0., 0.], success=True)), \
                mock.patch.object(candidate, "objective_gradient_hessian", return_value=(1., np.zeros(2), np.eye(2))):
            _, receipt = candidate.optimize_brier(*args)
        self.assertTrue(receipt["phase1"]["success"])
        self.assertEqual(receipt["phase2"]["iterations"], 0)
        with mock.patch.object(candidate, "minimize", return_value=optimizer_result([0., 0.], success=True)), \
                mock.patch.object(candidate, "objective_gradient_hessian", return_value=(1., np.zeros(2), -np.eye(2))), \
                self.assertRaisesRegex(candidate.PipelineFailure, "positive-definite"):
            candidate.optimize_brier(*args)

    def test_terminal_optimizer_nonfinite_armijo_and_iteration_caps(self):
        args = (np.eye(2), np.asarray([1, 0]), np.zeros(2), np.ones(2))
        with mock.patch.object(candidate, "minimize", return_value=optimizer_result([np.nan, 0.])), \
                self.assertRaises(candidate.PipelineFailure) as failed:
            candidate.optimize_brier(*args)
        self.assertFalse(failed.exception.receipt["converged"])
        self.assertEqual(failed.exception.receipt["restart_count"], 0)
        for field, value in (("fun", np.nan), ("jac", [np.inf, 0.])):
            result = optimizer_result([0., 0.])
            setattr(result, field, value)
            with self.subTest(field=field), mock.patch.object(candidate, "minimize", return_value=result), \
                    self.assertRaises(candidate.PipelineFailure):
                candidate.optimize_brier(*args)
        def always_reject_proposal(theta, *unused):
            return (1. if np.array_equal(theta, np.zeros(2)) else 2.), np.ones(2), np.eye(2)
        with mock.patch.object(candidate, "minimize", return_value=optimizer_result([0., 0.])), \
                mock.patch.object(candidate, "objective_gradient_hessian", side_effect=always_reject_proposal) as objective, \
                self.assertRaisesRegex(candidate.PipelineFailure, "maximum60") as failed:
            candidate.optimize_brier(*args)
        self.assertEqual(objective.call_count, 61)
        self.assertEqual(failed.exception.receipt["phase2"]["steps"][0]["proposals"], 60)
        def never_stationary(theta, *unused):
            return float(np.sum(theta)), np.ones(2), np.eye(2)
        with mock.patch.object(candidate, "minimize", return_value=optimizer_result([0., 0.])), \
                mock.patch.object(candidate, "objective_gradient_hessian", side_effect=never_stationary), \
                self.assertRaisesRegex(candidate.PipelineFailure, "maximum25") as failed:
            candidate.optimize_brier(*args)
        self.assertEqual(len(failed.exception.receipt["phase2"]["steps"]), 25)

    def test_eigenvalue_floor_only_step_direction_not_actual_hessian(self):
        args = (np.eye(2), np.asarray([1, 0]), np.zeros(2), np.ones(2))
        values = [(1., np.asarray([1e-6, 0.]), np.diag([-1., 2.])),
            (0., np.zeros(2), np.diag([-1., 2.]))]
        with mock.patch.object(candidate, "minimize", return_value=optimizer_result([0., 0.])), \
                mock.patch.object(candidate, "objective_gradient_hessian", side_effect=values), \
                self.assertRaisesRegex(candidate.PipelineFailure, "positive-definite") as failed:
            candidate.optimize_brier(*args)
        step = failed.exception.receipt["phase2"]["steps"][0]
        self.assertEqual(step["actual_hessian_eigenvalues"], [-1., 2.])
        np.testing.assert_allclose(step["direction"], [1., 0.], rtol=0, atol=1e-15)

    def test_exact_c4_design_real_synthetic_fit_zero_identity_and_numeric_replay(self):
        rows, _, _, features = problem()
        fit, check = rows[:22], rows[22:]
        bundle = bundle_for(fit, check, features)
        values, report = candidate.fit_brier(fit, check, bundle)
        self.assertEqual((values, report), candidate.fit_brier(fit, check, bundle))
        state = report["primitive_prediction_state"]
        self.assertEqual(values, candidate.replay_brier(state, check, features))
        for key, value in bundle["expected_by_keys"][tuple(row.key for row in check)].items():
            self.assertEqual(state[key], value)
        zero = {**state, "coefficients": [0., 0.], "native_volume_coefficient": 0.}
        np.testing.assert_array_equal(candidate.replay_brier(zero, check, features), candidate.sibling.raw_probabilities(check))
        self.assertEqual(state["curvature_units"], candidate.curvature_units(
            candidate.parent_module.scaled_design(fit, check, features)[2], candidate.sibling.raw_probabilities(fit)))
        bad = copy.deepcopy(bundle)
        bad["expected_by_keys"][tuple(row.key for row in check)]["volume_scale"] *= 2
        with mock.patch.object(candidate, "optimize_brier", side_effect=AssertionError("must reject before fit")), \
                self.assertRaisesRegex(ValueError, "parity"):
            candidate.fit_brier(fit, check, bad)

    def test_check_labels_future_state_and_check_features_cannot_change_fit_or_units(self):
        rows, _, _, features = problem()
        fit, check = rows[:22], rows[22:]
        _, first = candidate.fit_brier(fit, check, bundle_for(fit, check, features))
        changed = [candidate.common.base.InGameRow(row.game_id, row.game_date, row.game_week,
            {**row.trusted, "outcome": 1 - row.trusted["outcome"], "future_final": np.nan},
            row.market_features, (np.nan,) * 9, {**row.source_receipt,
                "market_staleness_seconds": 20., "latest_trade_epoch_ms": row.trusted["cutoff_ms"] - 20000}) for row in check]
        altered = {**features, **{row.game_id: -.5 for row in changed}}
        _, second = candidate.fit_brier(fit, changed, bundle_for(fit, changed, altered))
        one, two = first["primitive_prediction_state"], second["primitive_prediction_state"]
        check_keys = {"native_check_feature_sha256", "normalized_check_feature_sha256"}
        self.assertEqual({key: value for key, value in one.items() if key not in check_keys},
            {key: value for key, value in two.items() if key not in check_keys})
        self.assertEqual(first["optimizer"], second["optimizer"])
        self.assertNotEqual(one["normalized_check_feature_sha256"], two["normalized_check_feature_sha256"])

    def test_saved_prior_scale_and_nonfinite_objective_drift_fail_closed(self):
        rows, _, _, features = problem()
        _, report = candidate.fit_brier(rows[:22], rows[22:], bundle_for(rows[:22], rows[22:], features))
        state = report["primitive_prediction_state"]
        for key, value in (("lambda", [1., 1.]), ("r", [.6, .6]), ("n", [0., 0.]),
                ("fit_only", False), ("uses_labels", True), ("uses_check_rows", True), ("base_nll_penalty", 8)):
            bad = copy.deepcopy(state)
            bad["curvature_units"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                candidate.replay_brier(bad, rows[22:], features)
        for change in ({"volume_scale": 0.}, {"scale_ddof": 1}, {"coefficients": [np.nan, 0.]},
                {"effective_native_volume_penalty": 16.}, {"market_coefficient": 2}, {"intercept": True},
                {"training_objective": "modified"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                candidate.replay_brier({**state, **change}, rows[22:], features)
        for theta, labels, penalty in (([np.nan, 0], [0, 1], [1, 1]), ([0, 0], [0, .5], [1, 1]),
                ([0, 0], [0, 1], [0, 1])):
            with self.assertRaises(ValueError):
                candidate.objective_gradient_hessian(theta, np.eye(2), labels, [0, 0], penalty)

    def test_parent_direct_replay_exact_design_scale_feature_and_probability_fail_closed(self):
        rows, folds, _, features = problem()
        parent, states = synthetic_parent_states(rows, folds, features)
        with mock.patch.object(candidate.parent_module, "fit_unit", side_effect=AssertionError("no parent refit")):
            receipt, expected = candidate.replay_parent(rows, folds, features, parent, states)
        self.assertEqual((receipt["parent_rows_replayed"], receipt["parent_refits"]), (20, 0))
        self.assertEqual(len(expected), 4)
        for mode in ("scale", "normalizer", "hash", "features", "probability", "missing"):
            bad_states, bad_features, bad_parent = copy.deepcopy(states), dict(features), dict(parent)
            if mode == "scale":
                bad_states[1]["volume_scale"] *= 2
            elif mode == "normalizer":
                bad_states[1]["freshness_normalization"]["fit_age_mean"] += .01
            elif mode == "hash":
                bad_states[1]["normalized_fit_feature_sha256"] = "0" * 64
            elif mode == "features":
                bad_features[rows[0].game_id] += .01
            elif mode == "probability":
                bad_parent[next(iter(bad_parent))] += .01
            else:
                bad_parent.pop(next(iter(bad_parent)))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                candidate.replay_parent(rows, folds, bad_features, bad_parent, bad_states)

    def test_portable_parent_seven_file_hashes_canonical_states_controls_and_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            contract, controls, frozen, expected_key = synthetic_parent_artifacts(Path(directory))
            with mock.patch.object(candidate.common.frozen_v0, "EXPECTED_CHECK_KEY_SHA256", expected_key):
                parent, states = candidate.load_parent(contract, controls, frozen)
                self.assertEqual((len(parent), len(states)), (87, 4))
                for name in contract["research_parent"]["artifact_hashes"]:
                    bad = copy.deepcopy(contract)
                    bad["research_parent"]["artifact_hashes"][name] = "0" * 64
                    with self.subTest(name=name), self.assertRaises(ValueError):
                        candidate.load_parent(bad, controls, frozen)
                bad = copy.deepcopy(contract)
                bad["research_parent"]["state_sha256_by_fold"][0] = "0" * 64
                with self.assertRaisesRegex(ValueError, "canonical"):
                    candidate.load_parent(bad, controls, frozen)
                for field, value in (("outcome", 1), (candidate.ARM_ORDINARY, .01)):
                    altered = copy.deepcopy(controls)
                    altered[next(iter(altered))][field] += value
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        candidate.load_parent(contract, altered, frozen)
                bad_frozen = copy.deepcopy(frozen)
                bad_frozen["hashes"] = {"drift": "0" * 64}
                with self.assertRaisesRegex(ValueError, "receipts"):
                    candidate.load_parent(contract, controls, bad_frozen)

    def test_full195_synthetic_four_fits87_predictions_replay_and_old_judge(self):
        contract = candidate.common.settlement._strict_json(candidate.CONTRACT)
        def parent_loader(contract, controls, frozen):
            anchors = {state["game_id"]: state for state in frozen["anchors"]}
            cohort = candidate.common.base._validate_source(None)
            rows = [candidate.common.base._load_dynamic_market(None, item, anchors[item["game_id"]])
                for item in cohort if "exclusion" not in item]
            rows.sort(key=lambda row: row.key)
            return synthetic_parent_states(rows, frozen["folds"], parent_tests.features_for(rows))
        def feature_loader(source, frozen, contract, rows):
            return parent_tests.features_for(rows), {"all_materialized_rows_validated": len(rows)}
        with mock.patch.object(candidate.common, "run", side_effect=candidate.run), \
                mock.patch.object(candidate, "require_dependencies", return_value=contract), \
                mock.patch.object(candidate, "load_parent", side_effect=parent_loader), \
                mock.patch.object(candidate.volume, "load_features", side_effect=feature_loader), \
                mock.patch.object(candidate, "optimize_brier", wraps=candidate.optimize_brier) as fit, \
                mock.patch.object(candidate.parent_module, "fit_unit", side_effect=AssertionError("no parent refit")), \
                mock.patch.object(candidate.common.base, "_atomic_json", wraps=candidate.common.base._atomic_json) as write, \
                mock.patch.object(candidate.shared, "write_predictions", wraps=candidate.shared.write_predictions) as csv_write:
            old_tests.FreshnessInteractionOffsetTests().test_complete_synthetic_run_has_exact87_predictions_and_hash_bound_artifacts()
        self.assertEqual(fit.call_count, 4)
        predictions = csv_write.call_args.args[1]
        artifacts = {call.args[0].name: call.args[1] for call in write.call_args_list}
        card, progress = artifacts["scorecard.json"], artifacts["optimizer_progress.json"]
        self.assertEqual((progress["model_fits_started"], progress["model_fits_completed"]), (4, 4))
        self.assertEqual(len(progress["optimizer_receipts"]), 4)
        self.assertEqual(artifacts["input_receipts.json"]["parent_replay"]["parent_rows_replayed"], 87)
        self.assertEqual(artifacts["input_receipts.json"]["feature_receipts"]["causal_age_rows_validated"], 193)
        self.assertEqual(card["actual_research_parent_id"], candidate.parent_module.TASK_ID)
        self.assertTrue(card["all_four_designs_and_normalizers_equal_c4"])
        self.assertEqual(card["source_denominator"]["events"], 195)
        self.assertEqual(card["source_denominator"]["excluded_events"], 2)
        features = parent_tests.features_for([item["row"] for item in predictions])
        for item in artifacts["predictor_states.json"]["folds"]:
            check = [prediction["row"] for prediction in predictions if prediction["fold"] == item["fold"]]
            self.assertEqual(candidate.replay_brier(item["state"], check, features),
                [prediction[candidate.ARM_CANDIDATE] for prediction in predictions if prediction["fold"] == item["fold"]])
        with mock.patch.object(candidate.common.base, "_group_bootstrap", return_value={"interval_95": [-.1, .1]}) as draws:
            paired = candidate.shared.paired_evidence(predictions, candidate.ARM_CANDIDATE)
        self.assertEqual(draws.call_count, 16)
        metrics, reports = card["aggregate"], card["folds"]
        decision = candidate.common.decision(metrics, reports, paired, candidate.ARM_CANDIDATE)
        changed = {**metrics, candidate.ARM_RESEARCH_PARENT: {"brier": 0., "log_loss": 0.}}
        self.assertEqual(decision, candidate.common.decision(changed, reports, paired, candidate.ARM_CANDIDATE))
        for metric in ("brier", "log_loss"):
            self.assertAlmostEqual(paired[f"candidate_minus_{candidate.ARM_RESEARCH_PARENT}"][metric]["equal_event_mean"],
                metrics[candidate.ARM_CANDIDATE][metric] - metrics[candidate.ARM_RESEARCH_PARENT][metric], places=15)
        for arm, diagnostic in card["correction_diagnostics"].items():
            self.assertAlmostEqual(diagnostic["equal_event_brier_delta_raw_identity"],
                metrics[arm]["brier"] - metrics[candidate.ARM_RAW]["brier"], places=15)
        for key, value in candidate.common.BOUNDARY_FLAGS.items():
            self.assertEqual(card[key], value)

    def test_source_admission_failure_and_failed_attempt_no_retry_no_overwrite(self):
        with mock.patch.object(candidate.parent_module, "require_dependencies"), \
                mock.patch.object(candidate.common, "_sha256", return_value="0" * 64), \
                self.assertRaisesRegex(ValueError, "source/contract"):
            candidate.require_dependencies()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "failed"
            with mock.patch.object(candidate.common.base, "_validate_roots"), \
                    mock.patch.object(candidate, "require_dependencies", side_effect=ValueError("synthetic source drift")), \
                    mock.patch.object(candidate, "fit_brier", side_effect=AssertionError("must not fit")), \
                    self.assertRaisesRegex(ValueError, "source drift"):
                candidate.run(Path(directory), output, allow_test_paths=True)
            failure = candidate.common.settlement._strict_json(output / "failure.json")
            self.assertEqual(failure["automatic_retries"], 0)
            self.assertEqual(failure["fit_progress"]["model_fits_started"], 0)
            with mock.patch.object(candidate.common.base, "_validate_roots"), self.assertRaises(FileExistsError):
                candidate.run(Path(directory), output, allow_test_paths=True)

    def test_post_optimizer_prediction_failure_retains_converged_receipt(self):
        rows, _, _, features = problem()
        fit, check = rows[:22], rows[22:]
        with mock.patch.object(candidate.native, "probabilities", side_effect=ValueError("synthetic probability failure")), \
                self.assertRaisesRegex(candidate.PipelineFailure, "probability failure") as failed:
            candidate.fit_brier(fit, check, bundle_for(fit, check, features))
        receipt = failed.exception.receipt
        self.assertTrue(receipt["converged"])
        self.assertLessEqual(receipt["stationarity"]["gradient_infinity_norm"], 1e-8)
        self.assertEqual(receipt["retry_count"], 0)
        self.assertEqual(receipt["post_optimization_prediction_error"], "synthetic probability failure")

    def test_full_synthetic_first_fit_failure_receipt_preserved_without_retry(self):
        contract = candidate.common.settlement._strict_json(candidate.CONTRACT)
        def parent_loader(contract, controls, frozen):
            anchors = {state["game_id"]: state for state in frozen["anchors"]}
            cohort = candidate.common.base._validate_source(None)
            rows = [candidate.common.base._load_dynamic_market(None, item, anchors[item["game_id"]])
                for item in cohort if "exclusion" not in item]
            rows.sort(key=lambda row: row.key)
            return synthetic_parent_states(rows, frozen["folds"], parent_tests.features_for(rows))
        def feature_loader(source, frozen, contract, rows):
            return parent_tests.features_for(rows), {"all_materialized_rows_validated": len(rows)}
        partial = {"model_fits": 1, "restart_count": 0, "retry_count": 0, "converged": False,
            "phase1": {"success": False, "status": 2, "message": "synthetic nonfinite return"},
            "phase2": {"steps": []}}
        failure = candidate.PipelineFailure("synthetic first-fit failure", partial)
        with mock.patch.object(candidate.common, "run", side_effect=candidate.run), \
                mock.patch.object(candidate, "require_dependencies", return_value=contract), \
                mock.patch.object(candidate, "load_parent", side_effect=parent_loader), \
                mock.patch.object(candidate.volume, "load_features", side_effect=feature_loader), \
                mock.patch.object(candidate, "optimize_brier", side_effect=failure) as fit, \
                mock.patch.object(candidate.common.base, "_atomic_json", wraps=candidate.common.base._atomic_json) as write, \
                self.assertRaisesRegex(candidate.PipelineFailure, "first-fit failure"):
            old_tests.FreshnessInteractionOffsetTests().test_complete_synthetic_run_has_exact87_predictions_and_hash_bound_artifacts()
        self.assertEqual(fit.call_count, 1)
        artifacts = {call.args[0].name: call.args[1] for call in write.call_args_list}
        progress, saved = artifacts["optimizer_progress.json"], artifacts["failure.json"]
        self.assertEqual((progress["model_fits_started"], progress["model_fits_completed"]), (1, 0))
        self.assertEqual(progress["optimizer_receipts"], [partial])
        self.assertEqual(saved["optimizer_partial_receipt"], partial)
        self.assertEqual(saved["fit_progress"], progress)
        self.assertEqual(saved["automatic_retries"], 0)
        self.assertNotIn("scorecard.json", artifacts)


if __name__ == "__main__":
    unittest.main()
