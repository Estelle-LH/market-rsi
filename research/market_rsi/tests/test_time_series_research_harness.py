from __future__ import annotations

import copy
import unittest

from time_series_research_harness import harness_contract, validate_harness_contract


class TimeSeriesResearchHarnessTests(unittest.TestCase):
    def setUp(self):
        self.contract = harness_contract()

    def test_objective_is_frozen_before_dev_and_model_research(self):
        phases = self.contract["phase_order"]
        self.assertLess(
            phases.index("freeze_one_objective_and_baseline"),
            phases.index("freeze_unopened_dev_schedule"),
        )
        discovery = self.contract["objective_discovery_controller"]
        self.assertTrue(discovery["proposal_space"]["controller_may_propose_new_target"])
        self.assertIn(
            "measure_trivial_baseline_strength_by_day_game_and_regime",
            discovery["automatic_first_pass"],
        )
        self.assertLess(
            phases.index("freeze_unopened_dev_schedule"),
            phases.index("research_models_features_and_training_transforms_on_train_cv"),
        )

    def test_includes_simple_robust_and_model_based_target_families(self):
        families = {
            item["family"]
            for item in self.contract["objective_research"]["candidate_families"]
        }
        self.assertEqual(
            families,
            {
                "point_future_price",
                "uniform_future_window_mean",
                "forward_weighted_future_window_mean",
                "robust_future_window_location",
                "future_trade_vwap",
                "latent_state_filter",
            },
        )

    def test_dense_future_quotes_and_temporal_groups_are_required(self):
        data = self.contract["data_contract"]
        self.assertEqual(
            data["label_source"],
            "dense_raw_quotes_covering_the_full_future_window",
        )
        self.assertFalse(data["random_row_split"])
        self.assertIn("never_split", data["group_boundary"])
        population = data["training_population_policy"]
        self.assertTrue(population["row_count_is_not_independent_sample_size"])
        self.assertFalse(
            population["evaluation_population"]["future_target_based_filtering"]
        )

    def test_controller_has_model_freedom_but_not_objective_freedom_after_freeze(self):
        research = self.contract["model_research"]
        self.assertIn("model_family", research["controller_can_change"])
        self.assertIn("loss_or_training_transform", research["controller_can_change"])
        self.assertIn("frozen_objective", research["controller_cannot_change"])
        self.assertTrue(
            self.contract["objective_research"]
            ["objective_change_requires_fresh_experiment_and_unopened_dev"]
        )

    def test_dev_is_one_shot_and_then_becomes_train(self):
        evaluation = self.contract["evaluation"]
        self.assertEqual(evaluation["dev_openings_per_round"], 1)
        self.assertEqual(
            evaluation["consumed_dev_becomes"],
            "next_round_train_and_never_dev_again",
        )

    def test_contract_fails_closed(self):
        changed = copy.deepcopy(self.contract)
        changed["data_contract"]["random_row_split"] = True
        with self.assertRaises(ValueError):
            validate_harness_contract(changed)


if __name__ == "__main__":
    unittest.main()
