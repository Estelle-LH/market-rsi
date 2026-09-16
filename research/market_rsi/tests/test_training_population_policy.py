from __future__ import annotations

import unittest

from training_population_policy import audit_open_train, policy_contract


class TrainingPopulationPolicyTests(unittest.TestCase):
    def test_rows_are_not_reported_as_independent_evidence(self):
        rows = []
        for day in range(1, 5):
            for index in range(3):
                decision = day * 86_400_000 + index * 1_000
                rows.append({
                    "row_id": f"{day}-{index}", "game_id": f"game-{day}-{index % 2}",
                    "market_id": f"market-{day}-{index % 2}", "decision_ms": decision,
                    "features": {"mid": 0.5},
                    "target": 0.5 if index < 2 else 0.501,
                })
        report = audit_open_train(rows)
        self.assertEqual(report["rows"], 12)
        self.assertEqual(report["utc_days"], 4)
        self.assertEqual(report["whole_games"], 8)
        self.assertFalse(report["rows_are_independent_samples"])
        self.assertEqual(report["target_activity"]["moving_rows"], 4)
        self.assertTrue(report["sufficiency"]["enough_to_execute_pipeline"])
        self.assertIsNone(report["sufficiency"]["enough_for_performance_claim"])

    def test_evaluation_cannot_drop_rows_using_future_target(self):
        contract = policy_contract()
        evaluation = contract["evaluation_population"]
        self.assertFalse(evaluation["future_target_based_filtering"])
        self.assertFalse(evaluation["future_target_magnitude_weighting"])
        self.assertEqual(evaluation["primary"], "unweighted_full_population_equal_game_score")


if __name__ == "__main__":
    unittest.main()
