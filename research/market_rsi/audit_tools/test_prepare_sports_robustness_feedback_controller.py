import unittest

from audit_tools.prepare_sports_robustness_feedback_controller import (
    build_findings,
    public_receipts,
)


class SportsRobustnessFeedbackPreparationTests(unittest.TestCase):
    def test_public_receipts_omit_pre_score_locks(self):
        runs = [
            {"receipts": [
                {"path": "/x/result.json", "sha256": "a"},
                {"path": "/x/manifest.json", "sha256": "b"},
                {"path": "/x/pre_score_lock.json", "sha256": "c"},
            ]},
            {"receipts": [
                {"path": "/y/result.json", "sha256": "d"},
                {"path": "/y/manifest.json", "sha256": "e"},
            ]},
        ]
        kept = public_receipts(*runs)
        self.assertEqual(len(kept), 4)
        self.assertTrue(all("pre_score_lock" not in row["path"] for row in kept))

    def test_findings_use_canonical_loss_sign_and_boundaries(self):
        representation = {"result": {"primary_support_rule_satisfied": False}}
        trainer = {"result": {"support_rule_satisfied": False}}
        robustness = {
            "lock": {
                "target": "elapsed_30s_delta",
                "rolling_design": {"blocks": 5},
                "candidate": {"parameters": {"max_iter": 150}},
            },
            "result": {
                "parent": {"equal_game_candidate_mse": 1.0,
                           "equal_game_calibration_slope": 1.1},
                "candidate": {"equal_game_candidate_mse": 0.9,
                              "equal_game_calibration_slope": 1.0},
                "paired_date_evidence": {
                    "unit_count": 20,
                    "candidate_better_unit_fraction": 0.7,
                    "equal_unit_mean_delta": -0.1,
                    "equal_block_bootstrap_interval": {"lower": -0.2, "upper": -0.01},
                    "top_1_absolute_delta_share": 0.3,
                    "top_5_absolute_delta_share": 0.6,
                    "leave_one_unit_out_mean_delta": {"min": -0.2, "max": -0.01},
                },
                "rolling_check_games": 100,
                "rolling_check_rows": 1000,
                "second_moment_upper_crosscheck": -0.01,
                "support_conditions": {"paired": True},
                "support_rule_satisfied": True,
                "conclusion_status": "supported",
            },
        }
        findings = build_findings(
            {}, {}, representation, trainer, robustness,
            {"jobs": {"private": {}}, "available_usd": "10"},
        )
        self.assertEqual(findings[1]["canonical_delta"],
                         "candidate_minus_baseline; negative means lower candidate loss and therefore better")
        self.assertNotIn("jobs", findings[-1]["budget"])
        self.assertIn("cannot train", findings[-1]["instructions"])
        self.assertIn("future", " ".join(findings[4]["rules"]))


if __name__ == "__main__":
    unittest.main()
