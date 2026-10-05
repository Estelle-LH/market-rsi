"""Synthetic scientific checks only; no opened Train fixtures or control refits."""
from __future__ import annotations

import copy
from dataclasses import replace
import math
import unittest
from unittest import mock

import numpy as np
from experiments import nfl_ingame_temperature_possession_pressure_joint_offset as candidate
from experiments import test_nfl_ingame_market_temperature_offset as old_tests


def fixture():
    rows, _, _, _ = old_tests.problem()
    fit, check = rows[:22], rows[22:27]
    _, trainer = candidate.parent.fit_temperature(fit, check)
    features = {"fold_id": 1, "parent_state": trainer["primitive_prediction_state"],
        "pressure": {row.game_id: (-1 if i % 2 else 1) * (i + 1) / 100 for i, row in enumerate(rows)}}
    return fit, check, features


class TemperaturePressureTests(unittest.TestCase):
    def test_objective_finite_differences_hessian_and_scalar_identity(self):
        l, p, y = np.array([-2., -.7, .1, .8, 2.4]), np.array([.4, -.2, .1, .8, -.3]), np.array([0., 1., 0., 1., 1.])
        theta, step = np.array([.21, -.12]), 1e-5
        value, gradient, hessian = candidate.objective_gradient_hessian(theta, l, p, y)
        self.assertGreaterEqual(np.linalg.eigvalsh(hessian).min(), 16.)
        for index in range(2):
            shift = np.zeros(2)
            shift[index] = step
            hi = candidate.objective_gradient_hessian(theta + shift, l, p, y)
            lo = candidate.objective_gradient_hessian(theta - shift, l, p, y)
            self.assertAlmostEqual(gradient[index], (hi[0] - lo[0]) / (2 * step), places=7)
            np.testing.assert_allclose(hessian[:, index], (hi[1] - lo[1]) / (2 * step), atol=1e-7, rtol=0)
        scalar = candidate.parent.objective_gradient_hessian(theta[0], l, y)
        joint = candidate.objective_gradient_hessian([theta[0], 0.], l, p, y)
        self.assertEqual(joint[0], scalar[0])
        self.assertAlmostEqual(joint[1][0], scalar[1], places=14)
        self.assertAlmostEqual(joint[2][0, 0], scalar[2], places=14)

    def test_deterministic_interior_fit_brackets_kkt_and_truthful_count(self):
        l, p, y = [-2., -.7, .1, .8, 2.4], [.4, -.2, .1, .8, -.3], [0, 1, 0, 1, 1]
        with mock.patch.object(candidate, "objective_gradient_hessian", wraps=candidate.objective_gradient_hessian) as evaluate:
            theta, receipt = candidate.solve_joint(l, p, y, .1)
        again, second = candidate.solve_joint(l, p, y, .1)
        np.testing.assert_array_equal(theta, again)
        self.assertEqual(receipt, second)
        self.assertEqual(receipt["evaluations"], evaluate.call_count)
        self.assertEqual(receipt["fit_only_brackets"], [[-1., 1 + sum(abs(v) for v in l) / 16],
            [-1 - sum(abs(v) for v in p) / 16, 1 + sum(abs(v) for v in p) / 16]])
        value, gradient, hessian = candidate.objective_gradient_hessian(theta, l, p, y)
        self.assertLessEqual(candidate._kkt(theta, gradient), 1e-8)
        self.assertGreaterEqual(np.linalg.eigvalsh(hessian).min(), 16)
        self.assertLessEqual(value, receipt["F_warmstart"] + 1e-8)
        self.assertTrue(receipt["converged"])
        self.assertEqual((receipt["model_fits"], receipt["optimization_calls_started"], receipt["optimization_calls_completed"]), (1, 1, 1))
        self.assertEqual((receipt["retry_count"], receipt["fallback_count"]), (0, 0))
        self.assertLessEqual(receipt["sweeps"], 100)
        for record in receipt["coordinates"]:
            self.assertGreater(record["endpoint_gradients"][1], 0)
            if record["index"] == 1:
                self.assertLess(record["endpoint_gradients"][0], 0)
            self.assertLessEqual(record["steps"], 200)

    def test_beta_boundary_all_zero_exact_gradient_and_zero_pressure_column(self):
        theta, receipt = candidate.solve_joint(np.full(30, 4.), np.zeros(30), np.zeros(30), 0.)
        self.assertEqual(theta.tolist(), [-1., 0.])
        self.assertEqual(receipt["KKT"], 0.)
        self.assertGreaterEqual(receipt["gradient"][0], 0.)
        theta, receipt = candidate.solve_joint(np.zeros(8), np.zeros(8), np.arange(8) % 2, 0.)
        self.assertEqual(theta.tolist(), [0., 0.])
        self.assertEqual((receipt["sweeps"], receipt["coordinate_updates"], receipt["coordinate_bisection_steps"]), (0, 0, 0))
        self.assertEqual(receipt["evaluations"], 2)
        theta, _ = candidate.solve_joint(np.zeros(8), np.ones(8), np.ones(8), .1)
        self.assertEqual(theta[0], 0.)
        self.assertGreater(theta[1], 0.)

    def test_invalid_input_nonfinite_derivatives_bracket_failure_and_partials(self):
        for l, p, y, beta in (([1], [1, 2], [1], 0.), ([math.nan], [1], [1], 0.),
                ([1], [1], [.2], 0.), ([1], [1], [1], -2.), ([1], [1], [1], math.inf)):
            with self.subTest(inputs=(l, p, y, beta)), self.assertRaises(candidate.FitFailure) as failure:
                candidate.solve_joint(l, p, y, beta)
            self.assertEqual(failure.exception.receipt["optimization_calls_completed"], 0)
            self.assertFalse(failure.exception.receipt["converged"])
        for value, g, h in ((math.nan, [0, 0], np.eye(2) * 16), (1., [math.nan, 0], np.eye(2) * 16),
                (1., [0, 0], np.eye(2) * 15), (1., [0, 0], [[16, math.inf], [0, 16]])):
            with self.subTest(derivatives=(value, g)), mock.patch.object(candidate, "objective_gradient_hessian",
                    return_value=(value, np.asarray(g), np.asarray(h))), self.assertRaises(candidate.FitFailure) as failure:
                candidate.solve_joint([1], [.1], [1], 0.)
            self.assertEqual(failure.exception.receipt["evaluations"], 1)
        def bad_bracket(theta, *args):
            return 1., np.asarray([1., 1.]), np.eye(2) * 16
        with mock.patch.object(candidate, "objective_gradient_hessian", side_effect=bad_bracket), self.assertRaises(candidate.FitFailure) as failure:
            candidate.solve_joint([1], [.1], [1], 0.)
        self.assertIn("bracket", str(failure.exception))
        self.assertIn("coordinates", failure.exception.receipt)

    def test_stagnation_coordinate_cap_and_sweep_cap_never_succeed_or_retry(self):
        def discontinuous(theta, *args):
            return 1., np.asarray([-1. if theta[0] < -.123456789 else 1., 1.]), np.eye(2) * 16
        with mock.patch.object(candidate, "objective_gradient_hessian", side_effect=discontinuous), self.assertRaises(candidate.FitFailure) as failure:
            candidate.solve_joint([1], [.1], [1], 0.)
        self.assertIn("stagnated", str(failure.exception))
        self.assertGreater(failure.exception.receipt["coordinate_bisection_steps"], 0)
        with mock.patch.object(candidate, "MAX_STEPS", 1), mock.patch.object(candidate, "objective_gradient_hessian", side_effect=discontinuous), self.assertRaises(candidate.FitFailure) as failure:
            candidate.solve_joint([1], [.1], [1], 0.)
        self.assertIn("coordinate cap", str(failure.exception))
        with mock.patch.object(candidate, "MAX_SWEEPS", 0), self.assertRaises(candidate.FitFailure) as failure:
            candidate.solve_joint([1], [.1], [1], 0.)
        self.assertIn("sweep cap", str(failure.exception))
        self.assertEqual(failure.exception.receipt["retry_count"], 0)

    def test_native_physical_feature_coverage_and_future_label_isolation(self):
        rows, _ = old_tests.expanded_problem()
        anchors = [{"game_id": row.game_id, "possession_is_home": i % 2, "down": i % 4 + 1,
            "yards_to_go": i % 11, "yards_to_opponent_goal": i % 101} for i, row in enumerate(rows)]
        frozen, parents = {"anchors": anchors}, {i: {} for i in range(1, 5)}
        features, receipt = candidate.prepare_features(rows, frozen, parents)
        self.assertEqual(receipt["input_events"], 193)
        self.assertEqual(len(features["pressure"]), 193)
        changed = copy.deepcopy(frozen)
        for anchor in changed["anchors"]:
            anchor.update({"outcome": 42, "terminal_score": 99, "future_plays": ["evil"]})
        changed_rows = [replace(row, trusted={**row.trusted, "outcome": 42}) for row in rows]
        self.assertEqual((features, receipt), candidate.prepare_features(changed_rows, changed, parents))
        for field, bad in (("possession_is_home", 2), ("down", 0), ("yards_to_go", -1), ("yards_to_opponent_goal", 101)):
            bad_frozen = copy.deepcopy(frozen)
            bad_frozen["anchors"][0][field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                candidate.prepare_features(rows, bad_frozen, parents)
        for bad_rows, bad_anchors, bad_parents in ((rows[:-1], anchors, parents), (rows, anchors[:-1], parents),
                (rows, anchors + [anchors[0]], parents), (rows, anchors, {1: {}})):
            with self.assertRaises(ValueError):
                candidate.prepare_features(bad_rows, {"anchors": bad_anchors}, bad_parents)

    def test_probability_gamma_zero_exact_parent_identity_and_bounds(self):
        _, check, features = fixture()
        for beta in (0., -.4, -1., .2, 1000.):
            self.assertEqual(candidate.probabilities(beta, 0., check, features), candidate.parent.probabilities(beta, check))
        values, bounds = candidate.probabilities(1000., 1000., check, features)
        self.assertEqual(len(values), len(check))
        self.assertEqual(bounds["rows_removed"], 0)
        self.assertGreater(bounds["clipped_rows"], 0)
        self.assertTrue(all(candidate.parent.EPSILON <= p <= 1 - candidate.parent.EPSILON for p in values))
        for beta, gamma in ((-2, 0), (math.inf, 0), (0, math.nan)):
            with self.assertRaises(ValueError):
                candidate.probabilities(beta, gamma, check, features)

    def test_fit_replay_same_input_state_checklabel_invariance_and_parent_context(self):
        fit, check, features = fixture()
        values, trainer = candidate.fit_predict(fit, check, features)
        state = trainer["primitive_prediction_state"]
        self.assertEqual(candidate.replay_predictor(state, check, features), (values, trainer["bounding"]))
        changed_check = [replace(row, trusted={**row.trusted, "outcome": 42, "future": "evil"}) for row in check]
        self.assertEqual(candidate.fit_predict(fit, changed_check, features), (values, trainer))
        self.assertEqual(trainer["model_fits"], 1)
        self.assertEqual(trainer["predictor_state_sha256"], candidate.common._digest(state))
        with mock.patch.object(candidate, "solve_joint", side_effect=AssertionError("replay must not fit")):
            self.assertEqual(candidate.replay_predictor(state, check, features)[0], values)
        for context in ({**features, "fold_id": 7}, {**features, "parent_state": {**features["parent_state"], "fit_events": 999}}):
            with self.assertRaises(ValueError):
                candidate.fit_predict(fit, check, context)
        zero = {**features, "pressure": {key: 0. for key in features["pressure"]}}
        actual, control = candidate.fit_predict(fit, check, zero)
        self.assertEqual(control["primitive_prediction_state"]["gamma"], 0.)
        self.assertEqual(actual, candidate.parent.replay_predictor(features["parent_state"], check)[0])

    def test_saved_state_recipe_source_coefficient_optimizer_and_input_drift(self):
        fit, check, features = fixture()
        _, trainer = candidate.fit_predict(fit, check, features)
        state = trainer["primitive_prediction_state"]
        mutations = {"schema": "wrong", "feature_columns": ["future"], "alpha": 8, "beta": -2,
            "gamma": math.nan, "temperature": 99, "intercept": 1, "normalization": "fit", "sample_weights": [], "lower_bound": -2,
            "source_sha256": "0" * 64, "contract_sha256": "0" * 64, "fold_id": 2,
            "parent_state_sha256": "0" * 64, "raw_check_sha256": "0" * 64, "pressure_check_sha256": "0" * 64,
            "optimizer_sha256": "0" * 64, "fit_events": 999}
        for key, value in mutations.items():
            changed = {**state, key: value}
            with self.subTest(key=key), self.assertRaises((ValueError, candidate.FitFailure)):
                candidate.replay_predictor(changed, check, features)
        for key, value in {"F": math.nan, "F_warmstart": math.inf, "KKT": math.nan, "gradient": [math.nan, 0],
                "hessian": [[15, 0], [0, 16]], "theta": [0, 0], "converged": False, "alpha": 8, "solver": "fallback",
                "retry_count": 1, "fallback_count": 1, "optimization_calls_completed": 0, "sweeps": 101,
                "coordinate_tolerance": 1e-3}.items():
            changed = copy.deepcopy(state)
            changed["optimizer"][key] = value
            changed["optimizer_sha256"] = candidate.common._digest(changed["optimizer"]) if key not in ("F", "F_warmstart", "KKT", "gradient") else state["optimizer_sha256"]
            with self.subTest(optimizer=key), self.assertRaises(ValueError):
                candidate.replay_predictor(changed, check, features)

    def test_unbound_harness_refuses_before_import_io_or_fit(self):
        with mock.patch.object(candidate, "solve_joint", side_effect=AssertionError("no fit")), self.assertRaises(RuntimeError):
            candidate.run("/does/not/exist", "/does/not/exist")

    def test_postprediction_failure_keeps_completed_solver_and_no_fallback(self):
        fit, check, features = fixture()
        with mock.patch.object(candidate, "probabilities", side_effect=ValueError("synthetic output failure")), self.assertRaises(candidate.FitFailure) as failure:
            candidate.fit_predict(fit, check, features)
        receipt = failure.exception.receipt
        self.assertEqual(receipt["optimization_calls_completed"], 1)
        self.assertEqual(receipt["fallback_count"], 0)
        self.assertIn("post_optimization_prediction_error", receipt)


if __name__ == "__main__":
    unittest.main()
