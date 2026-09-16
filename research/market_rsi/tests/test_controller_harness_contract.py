from __future__ import annotations

import copy
import unittest
from decimal import Decimal

from controller_harness_contract import (
    ALLOWED_TOOLS,
    MAX_CUMULATIVE_INPUT_TOKENS,
    MAX_CUMULATIVE_OUTPUT_TOKENS,
    MAX_INPUT_TOKENS_PER_TURN,
    MAX_OUTPUT_TOKENS_PER_TURN,
    TERMINAL_SUBMISSION_MAX_OUTPUT,
    TERMINAL_SUBMISSION_OUTPUT_RESERVE,
    TERMINAL_SUBMISSION_TOOL_RESERVE,
    TERMINAL_SUBMISSION_TRIGGER_OUTPUT,
    build_contract,
    validate_contract,
)
from objective_contract import build_objective_contract


class ControllerHarnessContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = build_contract(
            experiment_id="fixture-controller-harness-v3",
            opaque_test_commitment="a" * 64,
            objective_contract=build_objective_contract(
                experiment_id="fixture-controller-harness-v3",
                objective_id="future-midpoint-window-mean-45-75s-v1",
                train_diagnostics_sha256="b" * 64,
                literature_snapshot_sha256="c" * 64,
                literature_ids=["zhang-zohren-roberts-deeplob-2018"],
                evidence_class="formal_learning",
            ),
        )

    def changed(self, section, key, value):
        contract = copy.deepcopy(self.contract)
        contract[section][key] = value
        return contract

    def test_uses_codex_as_glm_workbench_with_192k_input_and_64k_output(self):
        self.assertEqual(self.contract["harness"]["engine"], "codex")
        self.assertEqual(self.contract["harness"]["memory_mode"], "archive_only")
        self.assertEqual(
            self.contract["harness"]["profile_policy"],
            "one_frozen_h0_for_entire_archive_lineage",
        )
        self.assertEqual(self.contract["harness"]["profile_changes_during_archive_lineage"], 0)
        self.assertEqual(
            self.contract["harness"]["tool_proposals_during_archive_lineage"],
            "archive_only_not_activated",
        )
        self.assertFalse(self.contract["harness"]["controller_writes_learned_guide"])
        self.assertEqual(
            self.contract["research_budget"]["max_input_tokens_per_turn"],
            MAX_INPUT_TOKENS_PER_TURN,
        )
        self.assertEqual(
            self.contract["research_budget"]["max_output_tokens_per_turn"],
            MAX_OUTPUT_TOKENS_PER_TURN,
        )
        self.assertGreater(MAX_CUMULATIVE_INPUT_TOKENS, MAX_INPUT_TOKENS_PER_TURN)
        self.assertEqual(MAX_CUMULATIVE_OUTPUT_TOKENS, MAX_OUTPUT_TOKENS_PER_TURN)
        self.assertEqual(
            self.contract["research_budget"]["terminal_submission_output_reserve"],
            TERMINAL_SUBMISSION_OUTPUT_RESERVE,
        )
        self.assertEqual(
            self.contract["research_budget"]["terminal_submission_trigger_output"],
            TERMINAL_SUBMISSION_TRIGGER_OUTPUT,
        )
        self.assertEqual(
            self.contract["research_budget"]["terminal_submission_max_output"],
            TERMINAL_SUBMISSION_MAX_OUTPUT,
        )
        self.assertEqual(
            self.contract["research_budget"]["terminal_submission_tool_reserve"],
            TERMINAL_SUBMISSION_TOOL_RESERVE,
        )
        self.assertEqual(
            Decimal(self.contract["research_budget"]["worst_case_controller_usd"]),
            Decimal("8.44038144"),
        )

    def test_long_working_notebook_is_not_the_final_runner_action(self):
        decision = self.contract["decision_envelope"]
        self.assertTrue(decision["long_notebook_is_separate"])
        self.assertLess(decision["max_bytes"], MAX_CUMULATIVE_OUTPUT_TOKENS)

    def test_allows_research_work_but_not_hidden_test_or_direct_dispatch(self):
        self.assertIn("read_research_guide", ALLOWED_TOOLS)
        self.assertIn("read_objective_contract", ALLOWED_TOOLS)
        self.assertIn("read_harness_profile", ALLOWED_TOOLS)
        self.assertIn("search_public_literature", ALLOWED_TOOLS)
        self.assertIn("list_algorithms", ALLOWED_TOOLS)
        self.assertIn("inspect_algorithm", ALLOWED_TOOLS)
        self.assertIn("run_train_cv_candidate", ALLOWED_TOOLS)
        self.assertEqual(
            self.contract["evidence_policy"]["sealed_dev_score_visibility"],
            "next_round_archive_only",
        )
        self.assertIn("read_future_test", self.contract["harness"]["denied_capabilities"])
        self.assertIn("read_current_dev_labels", self.contract["harness"]["denied_capabilities"])
        self.assertIn(
            "reuse_consumed_dev_for_evaluation",
            self.contract["harness"]["denied_capabilities"],
        )
        self.assertIn("direct_paid_dispatch", self.contract["harness"]["denied_capabilities"])

    def test_data_lifecycle_is_runner_enforced_and_source_bound(self):
        policy = self.contract["evidence_policy"]
        self.assertEqual(
            policy["controller_learning_access"],
            "all_train_and_consumed_dev_with_labels",
        )
        self.assertEqual(
            policy["dev_after_score"],
            "atomically_promote_to_next_round_train",
        )
        self.assertEqual(policy["consumed_dev_evaluation_reuse"], "forbidden")
        self.assertEqual(len(policy["data_lifecycle_source_sha256"]), 64)
        time_series = policy["time_series_validation"]
        self.assertEqual(time_series["order"], "past_to_future_only")
        self.assertFalse(time_series["random_shuffle"])
        self.assertFalse(time_series["boundary_may_use_targets"])
        self.assertEqual(time_series["outer_dev_openings_per_round"], 1)
        self.assertEqual(time_series["final_promotion_minimum_untouched_utc_days"], 20)
        research_harness = policy["time_series_research_harness"]
        self.assertEqual(
            research_harness["phase_order"][2],
            "freeze_one_objective_and_baseline",
        )
        self.assertEqual(research_harness["evaluation"]["dev_openings_per_round"], 1)

    def test_rejects_short_output_regression_resampling_or_test_access(self):
        cases = [
            self.changed("research_budget", "max_output_tokens_per_turn", 4096),
            self.changed("harness", "automatic_resampling", 1),
            self.changed("evidence_policy", "visible_splits", ["train", "dev", "test"]),
            self.changed("harness", "allowed_tools", list(ALLOWED_TOOLS) + ["raw_host_shell"]),
            self.changed("harness", "controller_writes_learned_guide", True),
            self.changed("harness", "profile_changes_during_archive_lineage", 1),
            self.changed("evidence_policy", "dev_after_score", "leave_as_dev"),
            self.changed("evidence_policy", "consumed_dev_evaluation_reuse", "allowed"),
            self.changed("evidence_policy", "controller_may_change_objective", True),
        ]
        changed_time_series = copy.deepcopy(self.contract)
        changed_time_series["evidence_policy"]["time_series_validation"][
            "random_shuffle"] = True
        cases.append(changed_time_series)
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_contract(case)


if __name__ == "__main__":
    unittest.main()
