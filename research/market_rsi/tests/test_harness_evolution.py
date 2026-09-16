from __future__ import annotations

import copy
import unittest

from controller_harness_contract import ALLOWED_TOOLS
from harness_evolution import (
    EVALUATION_SCHEMA,
    assess_evaluation,
    baseline_profile,
    make_candidate,
    validate_profile,
)
from market_rsi import digest


class HarnessEvolutionTests(unittest.TestCase):
    def setUp(self):
        self.parent = baseline_profile(ALLOWED_TOOLS)
        self.candidate = make_candidate(self.parent, {
            "research_guidance": "Inspect failures first, then choose the next research action.",
            "change_hypothesis": "Earlier failure retrieval will improve valid execution rate.",
        }, allowed_tools=ALLOWED_TOOLS)

    def evaluation(self):
        return {
            "schema": EVALUATION_SCHEMA,
            "parent_profile_sha256": digest(self.parent),
            "candidate_profile_sha256": digest(self.candidate),
            "same_controller": True,
            "same_tasks": True,
            "same_budget": True,
            "submissions_precommitted": True,
            "labels_opened_once": True,
            "protocol_violations": 0,
            "parent_metrics": {"primary_improvement": 0.01,
                               "valid_experiment_rate": 0.70,
                               "cost_per_valid_experiment": 1.0},
            "candidate_metrics": {"primary_improvement": 0.02,
                                  "valid_experiment_rate": 0.80,
                                  "cost_per_valid_experiment": 1.05},
        }

    def test_ai_can_change_inner_guidance_but_not_active_kernel(self):
        receipt = validate_profile(self.candidate, allowed_tools=ALLOWED_TOOLS)
        self.assertEqual(receipt["generation"], 1)
        self.assertEqual(self.candidate["parent_profile_sha256"], digest(self.parent))
        changed = copy.deepcopy(self.candidate)
        changed["authority_boundary"]["may_change_current_session"] = True
        with self.assertRaisesRegex(ValueError, "authority boundary"):
            validate_profile(changed, allowed_tools=ALLOWED_TOOLS)
        changed = copy.deepcopy(self.candidate)
        changed["authority_boundary"]["may_activate_unadmitted_tools"] = True
        with self.assertRaisesRegex(ValueError, "authority boundary"):
            validate_profile(changed, allowed_tools=ALLOWED_TOOLS)

    def test_ai_may_propose_new_tools_with_bounded_capabilities(self):
        proposal = {
            "tool_name": "archive_failure_cluster",
            "description": "Cluster prior failures without reading sealed evaluation labels.",
            "source_sha256": "1" * 64,
            "input_schema_sha256": "2" * 64,
            "test_receipt_sha256": "3" * 64,
            "requested_capabilities": ["read_archive", "write_inner_workspace"],
        }
        candidate = make_candidate(self.parent, {
            "tool_proposals": [proposal],
            "change_hypothesis": "A failure clustering tool will reduce repeated invalid experiments.",
        }, allowed_tools=ALLOWED_TOOLS)
        self.assertTrue(validate_profile(candidate, allowed_tools=ALLOWED_TOOLS)["valid"])
        changed = copy.deepcopy(candidate)
        changed["tool_proposals"][0]["requested_capabilities"] = ["read_transfer_labels"]
        with self.assertRaisesRegex(ValueError, "outside the outer kernel"):
            validate_profile(changed, allowed_tools=ALLOWED_TOOLS)

    def test_candidate_applies_only_after_comparable_one_shot_evaluation(self):
        result = assess_evaluation(
            self.parent, self.candidate, self.evaluation(), allowed_tools=ALLOWED_TOOLS
        )
        self.assertTrue(result["promotion_eligible_for_next_session"])
        self.assertFalse(result["automatic_promotion"])
        self.assertFalse(result["research_claim"])

    def test_worse_effectiveness_cost_or_protocol_violation_blocks_candidate(self):
        for field, value in (
            ("primary_improvement", 0.0),
            ("valid_experiment_rate", 0.60),
            ("cost_per_valid_experiment", 1.20),
        ):
            evaluation = self.evaluation()
            evaluation["candidate_metrics"][field] = value
            with self.subTest(field=field):
                result = assess_evaluation(
                    self.parent, self.candidate, evaluation, allowed_tools=ALLOWED_TOOLS
                )
                self.assertFalse(result["promotion_eligible_for_next_session"])
        evaluation = self.evaluation()
        evaluation["protocol_violations"] = 1
        result = assess_evaluation(
            self.parent, self.candidate, evaluation, allowed_tools=ALLOWED_TOOLS
        )
        self.assertFalse(result["promotion_eligible_for_next_session"])

    def test_comparison_must_freeze_both_sides_before_one_label_open(self):
        for key in ("same_controller", "same_tasks", "same_budget",
                    "submissions_precommitted", "labels_opened_once"):
            evaluation = self.evaluation()
            evaluation[key] = False
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "not isolated"):
                assess_evaluation(
                    self.parent, self.candidate, evaluation, allowed_tools=ALLOWED_TOOLS
                )


if __name__ == "__main__":
    unittest.main()
