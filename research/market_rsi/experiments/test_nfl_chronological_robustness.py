import unittest

import numpy as np

from experiments.nfl_chronological_robustness import (
    date_records,
    robustness_folds,
    support_conditions,
    supported,
)


class NFLChronologicalRobustnessTests(unittest.TestCase):
    def test_folds_are_strict_expanding_prefixes(self):
        games = [f"g{i:03d}" for i in range(163)]
        folds = robustness_folds(games)
        self.assertEqual(len(folds), 5)
        for index, fold in enumerate(folds):
            boundary = 63 + index * 20
            self.assertEqual(fold["fit_games"], games[:boundary])
            self.assertEqual(fold["check_games"], games[boundary:boundary + 20])
            self.assertFalse(set(fold["fit_games"]) & set(fold["check_games"]))

    def test_date_delta_is_candidate_minus_parent_loss(self):
        rows = [
            {"target": 1.0, "game_date": "2025-01-01", "game": "a"},
            {"target": 1.0, "game_date": "2025-01-01", "game": "b"},
        ]
        records = date_records(
            rows, np.asarray([0, 1]),
            np.asarray([0.0, 0.0]), np.asarray([0.5, 0.5]),
        )
        self.assertLess(records[0]["candidate_loss"] - records[0]["baseline_loss"], 0)

    def test_support_is_conjunctive_and_directional(self):
        public = {
            "unit_count": 10,
            "candidate_better_unit_fraction": 0.7,
            "equal_block_bootstrap_interval": {"upper": -0.01},
            "top_1_absolute_delta_share": 0.4,
        }
        self.assertTrue(supported(support_conditions(public)))
        for key, value in (
            ("unit_count", 7),
            ("candidate_better_unit_fraction", 0.59),
            ("top_1_absolute_delta_share", 0.51),
        ):
            bad = dict(public); bad[key] = value
            self.assertFalse(supported(support_conditions(bad)))
        bad = dict(public)
        bad["equal_block_bootstrap_interval"] = {"upper": 0.0}
        self.assertFalse(supported(support_conditions(bad)))


if __name__ == "__main__":
    unittest.main()
