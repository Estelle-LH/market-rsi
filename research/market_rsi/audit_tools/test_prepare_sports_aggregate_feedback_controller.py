import unittest

from audit_tools.prepare_sports_aggregate_feedback_controller import (
    build_feedback_findings,
)


class SportsAggregateFeedbackPreparationTests(unittest.TestCase):
    def test_feedback_is_aggregate_and_keeps_failed_rules_visible(self):
        rep_summary = {
            "parent_raw_state": {
                "equal_game_candidate_mse": 2.0,
                "relative_mse_improvement": 0.1,
                "equal_game_calibration_slope": 1.0,
            },
            "full_k4": {
                "equal_game_candidate_mse": 1.0,
                "minimum_fold_relative_mse_improvement": 0.2,
                "positive_game_fraction": 0.8,
                "equal_game_calibration_slope": 1.12,
                "paired_against_parent": {
                    "relative_mse_improvement_vs_parent": 0.5,
                    "positive_game_fraction_vs_parent": 0.8,
                },
            },
        }
        for name in ("state_wp_delta_only", "score_time_k4_only",
                     "possession_field_only", "without_state_wp_delta"):
            rep_summary[name] = {
                "equal_game_calibration_slope": 1.0,
                "paired_against_parent": {"relative_mse_improvement_vs_parent": 0.1},
            }
        representation = {
            "lock": {"target": "elapsed_30s_delta", "rolling_design": {"blocks": 3}},
            "result": {"primary_candidate": "full_k4", "summary": rep_summary,
                       "primary_support_rule_satisfied": False},
        }
        trainer = {
            "lock": {"candidate": {"parameters": {"max_iter": 150}}},
            "result": {
                "parent": {"equal_game_candidate_mse": 1.0,
                           "equal_game_calibration_slope": 1.12},
                "candidate": {"equal_game_candidate_mse": 0.9,
                              "fold_equal_game_candidate_mse": [1.0, 0.9, 0.8],
                              "equal_game_calibration_slope": 1.0},
                "paired_against_parent": {
                    "relative_mse_improvement_vs_parent": 0.1,
                    "positive_game_fraction_vs_parent": 0.75,
                    "candidate_minus_parent_date_block_interval": {
                        "lower": -0.1, "upper": 0.01,
                    },
                },
                "support_conditions": {
                    "paired_date_block_interval_upper_below_zero": False,
                },
                "support_rule_satisfied": False,
            },
        }
        findings = build_feedback_findings(
            {}, {}, representation, trainer,
            {"jobs": {"secret": {}}, "available_usd": "10"},
        )
        self.assertEqual([finding["id"] for finding in findings], [
            "experiment-chain", "representation-attribution", "trainer-result",
            "remaining-uncertainty", "evaluation-boundary", "next-controller-decision",
        ])
        self.assertFalse(findings[2]["support_conditions"][
            "paired_date_block_interval_upper_below_zero"
        ])
        self.assertNotIn("jobs", findings[-1]["budget"])
        self.assertIn("single highest-information", findings[-1]["instructions"])
        self.assertIn("cannot train", findings[-1]["instructions"])


if __name__ == "__main__":
    unittest.main()
