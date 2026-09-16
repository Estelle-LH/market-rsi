import unittest

import numpy as np

from experiments.nfl_horizon_screen import rows_for_metric, target_profile


class HorizonScreenTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"game": "g1", "scheduled_utc": "2025-01-01T00:00:00Z",
             "outcomes": {"30": 0.1, "60": 0.2, "300": 0.3}},
            {"game": "g1", "scheduled_utc": "2025-01-01T00:00:00Z",
             "outcomes": {"30": 0.0, "60": 0.0, "300": 0.1}},
            {"game": "g2", "scheduled_utc": "2025-01-02T00:00:00Z",
             "outcomes": {"30": -0.1, "60": -0.2, "300": -0.3}},
        ]

    def test_metric_adapter_changes_only_target(self):
        adapted = rows_for_metric(self.rows, 60)
        self.assertEqual([row["target"] for row in adapted], [0.2, 0.0, -0.2])
        self.assertEqual([row["game"] for row in adapted], ["g1", "g1", "g2"])

    def test_target_profile_is_equal_game_for_baseline(self):
        profile = target_profile(self.rows, np.arange(3), 60)
        self.assertEqual(profile["games"], 2)
        self.assertAlmostEqual(profile["exact_zero_fraction"], 1 / 3)
        self.assertAlmostEqual(profile["equal_game_zero_change_mse"], 0.03)


if __name__ == "__main__":
    unittest.main()
