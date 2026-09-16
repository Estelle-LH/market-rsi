import unittest

from experiments.nfl_representation_trainer_ablation import (
    HGB_PARAMETERS,
    parent_report,
    support_conditions,
    supported,
)


class RepresentationTrainerAblationTests(unittest.TestCase):
    def test_candidate_parameters_are_single_frozen_configuration(self):
        self.assertEqual(HGB_PARAMETERS, {
            "max_iter": 150,
            "learning_rate": 0.05,
            "max_leaf_nodes": 31,
            "min_samples_leaf": 50,
            "l2_regularization": 1.0,
        })

    def test_parent_report_restores_private_by_game_evidence(self):
        result = {"summary": {"full_k4": {"games": 1, "equal_game_candidate_mse": 2.0}}}
        diagnostics = {"aggregate_by_game": {"full_k4": [
            {"game": "g", "date": "2025-01-01", "rows": 2, "candidate_mse": 2.0}
        ]}}
        report = parent_report(result, diagnostics)
        self.assertEqual(report["by_game"][0]["game"], "g")

    def test_support_rule_is_conjunctive(self):
        candidate = {
            "equal_game_calibration_slope": 1.0,
            "positive_game_fraction": 0.8,
        }
        candidate_folds = [{"equal_game_candidate_mse": value} for value in (0.8, 0.9, 1.0)]
        parent_folds = [{"equal_game_candidate_mse": 1.1}] * 3
        paired = {"candidate_minus_parent_date_block_interval": {"upper": -0.01}}
        conditions = support_conditions(candidate, candidate_folds, parent_folds, paired)
        self.assertTrue(supported(conditions))
        self.assertEqual(conditions["fold_wins"], [True, True, True])

        bad_slope = dict(candidate, equal_game_calibration_slope=1.11)
        self.assertFalse(supported(support_conditions(
            bad_slope, candidate_folds, parent_folds, paired
        )))
        crossing = {"candidate_minus_parent_date_block_interval": {"upper": 0.0}}
        self.assertFalse(supported(support_conditions(
            candidate, candidate_folds, parent_folds, crossing
        )))

    def test_one_losing_fold_refutes_candidate(self):
        candidate = {"equal_game_calibration_slope": 1.0, "positive_game_fraction": 0.8}
        candidate_folds = [{"equal_game_candidate_mse": value} for value in (0.8, 1.1, 0.9)]
        parent_folds = [{"equal_game_candidate_mse": 1.0}] * 3
        paired = {"candidate_minus_parent_date_block_interval": {"upper": -0.01}}
        conditions = support_conditions(candidate, candidate_folds, parent_folds, paired)
        self.assertFalse(supported(conditions))
        self.assertEqual(conditions["fold_wins"], [True, False, True])


if __name__ == "__main__":
    unittest.main()
