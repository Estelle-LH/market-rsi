from __future__ import annotations

import math
from pathlib import Path
import unittest
from unittest import mock

import numpy as np

from experiments import nfl_ingame_causal_possession_pressure_offset as candidate
from experiments.test_nfl_ingame_market_freshness_interaction_offset import synthetic_problem


class CausalPossessionPressureOffsetTests(unittest.TestCase):
    def test_exact_pressure_formula_orientation_and_monotonicity(self):
        home = {"possession_is_home": "1", "down": "2", "yards_to_go": "10", "yards_to_opponent_goal": "25"}
        self.assertEqual(candidate.possession_pressure(home), .25)
        self.assertEqual(candidate.possession_pressure({**home, "possession_is_home": "0"}), -.25)
        for field, value in (("down", "3"), ("yards_to_go", "20"), ("yards_to_opponent_goal", "50")):
            self.assertLess(candidate.possession_pressure({**home, field: value}), .25)
        self.assertEqual(candidate.possession_pressure({**home, "yards_to_opponent_goal": "100"}), 0.)

    def test_state_bounds_and_missing_nonfinite_fields_rejected(self):
        state = synthetic_problem()[3]["game-0"]
        for field, value in (("possession_is_home", .5), ("down", 2.5), ("down", 0),
            ("yards_to_go", -1), ("yards_to_go", 101), ("yards_to_opponent_goal", 101), ("down", math.nan)):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                candidate.possession_pressure({**state, field: value})
        with self.assertRaisesRegex(ValueError, "incomplete"):
            candidate.possession_pressure({})

    def test_no_future_state_inputs_and_no_fit_or_check_scaling(self):
        rows, _, _, states = synthetic_problem()
        fit, check, report = candidate.pressure_features(rows[:22], rows[22:], states=states)
        poisoned = {game: {**state, "home_score_post": 1000, "play_result": "touchdown",
            "final_score": 999, "future_play": math.nan} for game, state in states.items()}
        new_fit, new_check, new_report = candidate.pressure_features(rows[:22], rows[22:], states=poisoned)
        np.testing.assert_array_equal(fit, new_fit)
        np.testing.assert_array_equal(check, new_check)
        self.assertEqual(report, new_report)
        self.assertEqual(report["scaling"], "none")
        missing = {**states, "unrelated-game": states["game-0"]}
        missing.pop("game-0")
        with self.assertRaisesRegex(ValueError, "missing"):
            candidate.pressure_features(rows[:22], rows[22:], states=missing)

    def test_four_synthetic_fits_same_frozen_controls_and_parent_distinct(self):
        rows, folds, controls, states = synthetic_problem()
        with mock.patch.object(candidate.common, "fit_single_offset", wraps=candidate.common.fit_single_offset) as fit:
            predictions, reports = candidate.common._fit_and_predict(rows, folds, controls, states,
                candidate.pressure_features, candidate.ARM_CANDIDATE)
        self.assertEqual(fit.call_count, 4)
        self.assertEqual({item["row"].key for item in predictions}, set(controls))
        self.assertTrue(all(item["optimizer"]["unused_zero_column_coefficient"] == 0 for item in reports))
        self.assertEqual(len(predictions), 20)
        for item in predictions:
            frozen = controls[item["row"].key]
            self.assertEqual(item[candidate.ARM_PARENT], frozen[candidate.ARM_PARENT])

    def test_zero_coefficient_and_derivatives_reuse_identical_solver(self):
        rows, _, _, states = synthetic_problem()
        x, _, _ = candidate.pressure_features(rows[:4], rows[4:5], states=states)
        raw = [row.trusted["market_probability"] for row in rows[:4]]
        logits = [row.market_features[0] for row in rows[:4]]
        self.assertEqual(candidate.common.candidate_probabilities(0., x, logits, raw_probabilities=raw), raw)
        beta, h = .2, 1e-5
        labels = [row.trusted["outcome"] for row in rows[:4]]
        _, gradient, hessian = candidate.common.objective_gradient_hessian(beta, x, labels, logits)
        hi = candidate.common.objective_gradient_hessian(beta + h, x, labels, logits)
        lo = candidate.common.objective_gradient_hessian(beta - h, x, labels, logits)
        self.assertAlmostEqual(gradient, (hi[0] - lo[0]) / (2 * h), places=7)
        self.assertAlmostEqual(hessian, (hi[1] - lo[1]) / (2 * h), places=7)

    def test_separate_recipe_and_prediction_arm_forwarded(self):
        with mock.patch.object(candidate.common, "run_recipe", return_value={}) as run:
            candidate.run(Path("source"), Path("out"), allow_test_paths=True)
        self.assertEqual(run.call_args.kwargs["candidate_id"], candidate.TASK_ID)
        self.assertEqual(run.call_args.kwargs["arm"], candidate.ARM_CANDIDATE)
        self.assertIs(run.call_args.kwargs["feature_builder"], candidate.pressure_features)
        self.assertNotEqual(candidate.TASK_ID, candidate.common.TASK_ID)


if __name__ == "__main__":
    unittest.main()
