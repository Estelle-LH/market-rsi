import math
import unittest

from experiments.nfl_representation_ablation import (
    CALIBRATION_RANGE,
    MINIMUM_POSITIVE_GAME_FRACTION,
    PARENT_MINIMUM_FOLD_SKILL,
    paired_against_parent,
    possession_field_interaction,
    score_time_ratio,
    supported,
)


class RepresentationAblationTests(unittest.TestCase):
    def test_score_time_ratio_has_declared_endpoints(self):
        self.assertEqual(score_time_ratio(7, 3600, 4), 7)
        self.assertAlmostEqual(score_time_ratio(7, 0, 4), 7 * math.exp(4))
        self.assertEqual(score_time_ratio(0, 1200, 4), 0)

    def test_possession_field_interaction_is_home_oriented_and_signed(self):
        self.assertAlmostEqual(possession_field_interaction(1, 20), 0.6)
        self.assertAlmostEqual(possession_field_interaction(0, 80), -0.6)

    def test_paired_comparison_uses_identical_games(self):
        parent = {
            "equal_game_candidate_mse": 2.0,
            "by_game": [
                {"game": "a", "date": "2025-01-01", "rows": 2, "candidate_mse": 1.0},
                {"game": "b", "date": "2025-01-02", "rows": 2, "candidate_mse": 3.0},
            ],
        }
        candidate = {
            "equal_game_candidate_mse": 1.75,
            "by_game": [
                {"game": "a", "date": "2025-01-01", "rows": 2, "candidate_mse": 0.5},
                {"game": "b", "date": "2025-01-02", "rows": 2, "candidate_mse": 3.0},
            ],
        }
        report = paired_against_parent(parent, candidate)
        self.assertEqual(report["candidate_minus_parent_equal_game_mse"], -0.25)
        self.assertEqual(report["positive_game_fraction_vs_parent"], 0.5)

    def test_support_rule_is_conjunctive(self):
        report = {
            "equal_game_calibration_slope": sum(CALIBRATION_RANGE) / 2,
            "positive_game_fraction": MINIMUM_POSITIVE_GAME_FRACTION,
        }
        folds = [{"relative_mse_improvement": PARENT_MINIMUM_FOLD_SKILL + 0.001}] * 3
        self.assertTrue(supported(report, folds))
        self.assertFalse(supported(
            {**report, "positive_game_fraction": MINIMUM_POSITIVE_GAME_FRACTION - 0.01},
            folds,
        ))
        self.assertFalse(supported(report, [
            {"relative_mse_improvement": PARENT_MINIMUM_FOLD_SKILL}, *folds[1:]
        ]))


if __name__ == "__main__":
    unittest.main()
