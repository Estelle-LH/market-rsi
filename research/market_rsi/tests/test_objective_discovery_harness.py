from __future__ import annotations

import copy
import unittest

from objective_discovery_harness import (
    discovery_harness_contract,
    validate_discovery_harness,
)


class ObjectiveDiscoveryHarnessTests(unittest.TestCase):
    def setUp(self):
        self.contract = discovery_harness_contract()

    def test_controller_profiles_data_before_proposing_target(self):
        first_pass = self.contract["automatic_first_pass"]
        self.assertIn("measure_raw_and_materialized_cadence_by_market_day_and_game",
                      first_pass)
        self.assertIn("measure_trivial_baseline_strength_by_day_game_and_regime",
                      first_pass)
        self.assertIn("search_public_literature_for_the_observed_failure_modes",
                      first_pass)

    def test_catalog_is_not_a_fixed_menu(self):
        space = self.contract["proposal_space"]
        self.assertFalse(space["catalog_is_exhaustive"])
        self.assertTrue(space["controller_may_propose_new_target"])
        self.assertTrue(space["controller_may_propose_new_required_data_stream"])

    def test_controller_chooses_content_while_runner_enforces_boundaries(self):
        selection = self.contract["selection_rule"]
        self.assertTrue(selection["first_valid_controller_decision_only"])
        self.assertTrue(selection["no_human_target_choice_after_controller_dispatch"])
        self.assertTrue(
            selection["runner_validates_constraints_but_does_not_choose_scientific_content"]
        )
        self.assertFalse(selection["automatic_lowest_train_error_selection"])

    def test_dev_does_not_exist_during_objective_discovery(self):
        self.assertEqual(
            self.contract["runs_before"],
            "dev_schedule_creation_and_model_improvement",
        )
        self.assertIn(
            "create_or_open_dev_before_objective_freeze",
            self.contract["forbidden"],
        )

    def test_external_controller_receives_only_audited_aggregates(self):
        egress = self.contract["external_egress"]
        self.assertEqual(egress["destination"], "tinker_hosted_glm_5_3")
        self.assertFalse(egress["raw_rows_released"])
        self.assertIn("target_candidates", egress["forbidden_keys"])
        self.assertTrue(egress["every_released_result_hash_chain_logged"])

    def test_contract_fails_closed(self):
        changed = copy.deepcopy(self.contract)
        changed["selection_rule"]["automatic_lowest_train_error_selection"] = True
        with self.assertRaises(ValueError):
            validate_discovery_harness(changed)


if __name__ == "__main__":
    unittest.main()
