"""Small-step controls are independent of prediction score and legacy releases."""
from copy import deepcopy
import unittest

from market_rsi import digest
from data_scientist_harness.co_evolution_loop import (
    MICRO_CHECKS, MICRO_CONTEXT, initialize_micro_evolution, micro_pair_hash,
    propose_micro_evolution, review_micro_evolution, rollback_micro_evolution,
)


def config():
    return {
        "pair": {"harness_sha256": "a" * 64, "researcher_sha256": "b" * 64},
        "fixed_context": {key: "c" * 64 for key in MICRO_CONTEXT},
        "allowed_write_paths": {"harness": ["tools/feedback.py"],
                                "researcher": ["researcher/instructions.md"]},
        "protected_paths": ["evaluator", "budget", "sealed"],
        "reviewer_id": "trusted-supervisor",
    }


def proposal(state, axis="harness", identifier="change-1"):
    pair = dict(state["active_pair"])
    pair[axis + "_sha256"] = "d" * 64
    return {
        "candidate_id": identifier, "proposer_id": "research-agent", "axis": axis,
        "component": "feedback_delivery" if axis == "harness" else "instructions",
        "behavior_change": "Include the existing error classification in feedback.",
        "problem_evidence_sha256": "e" * 64, "parent_pair_sha256": micro_pair_hash(state),
        "pair": pair, "fixed_context": deepcopy(state["fixed_context"]),
        "write_paths": list(state["allowed_write_paths"][axis]), "patch_sha256": "f" * 64,
    }


def review(state, decision="accept"):
    pending = state["pending"]
    return {
        "reviewer_id": "trusted-supervisor", "proposal_sha256": pending["record_sha256"],
        "decision": decision, "reason": "Existing traces are preserved and the intended handoff works.",
        "tested_pair_sha256": digest(pending["pair"]),
        "anchor_pair_sha256": digest(state["anchor_pair"]),
        "checks": {key: {"passed": True, "evidence_sha256": "1" * 64} for key in MICRO_CHECKS},
        "benefit_observed": True, "benefit_evidence_sha256": "2" * 64,
        "actual_write_paths": list(pending["write_paths"]),
    }


class MicroEvolutionTests(unittest.TestCase):
    def setUp(self):
        self.state = initialize_micro_evolution(config())

    def pending(self, axis="harness"):
        return propose_micro_evolution(self.state, proposal(self.state, axis))

    def test_harness_then_researcher_hold_other_axis_fixed(self):
        h = self.pending()
        self.assertEqual(h["active_pair"], self.state["active_pair"])
        h = review_micro_evolution(h, review(h))
        r = propose_micro_evolution(h, proposal(h, "researcher", "change-2"))
        r = review_micro_evolution(r, review(r))
        self.assertEqual(r["active_pair"], {"harness_sha256": "d" * 64, "researcher_sha256": "d" * 64})
        self.assertEqual(r["anchor_pair"], self.state["active_pair"])
        self.assertEqual(len(r["history"]), 2)
        self.assertIsNone(self.state["pending"])

    def test_two_axes_or_no_change_are_rejected(self):
        for pair in ({"harness_sha256": "d" * 64, "researcher_sha256": "d" * 64},
                     self.state["active_pair"]):
            value = proposal(self.state); value["pair"] = pair
            with self.assertRaisesRegex(ValueError, "exactly one axis"):
                propose_micro_evolution(self.state, value)

    def test_one_pending_change_and_no_id_reuse(self):
        pending = self.pending()
        with self.assertRaisesRegex(ValueError, "only one provisional"):
            propose_micro_evolution(pending, proposal(self.state, identifier="change-2"))
        rejected = review_micro_evolution(pending, review(pending, "reject"))
        self.assertEqual(rejected["active_pair"], self.state["active_pair"])
        self.assertIsNone(rejected["pending"])
        self.assertEqual(len(rejected["history"]), 1)
        with self.assertRaisesRegex(ValueError, "ID cannot be reused"):
            propose_micro_evolution(rejected, proposal(rejected))

    def test_all_fixed_context_changes_are_rejected(self):
        for key in MICRO_CONTEXT:
            value = proposal(self.state); value["fixed_context"][key] = "9" * 64
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "stay fixed"):
                propose_micro_evolution(self.state, value)

    def test_write_scope_and_measured_diff_must_match(self):
        for path in ("../escape", "/absolute", "tools/*", "evaluator/score.py", "other.py"):
            value = proposal(self.state); value["write_paths"] = [path]
            with self.subTest(path=path), self.assertRaises(ValueError):
                propose_micro_evolution(self.state, value)
        pending = self.pending(); receipt = review(pending)
        receipt["actual_write_paths"].append("other.py")
        with self.assertRaisesRegex(ValueError, "measured write scope"):
            review_micro_evolution(pending, receipt)

    def test_protected_paths_cannot_be_allowlisted(self):
        value = config(); value["allowed_write_paths"]["harness"] = ["evaluator/score.py"]
        with self.assertRaisesRegex(ValueError, "overlaps protected"):
            initialize_micro_evolution(value)
        for path in ("paid_budget.py", "data_scientist_harness/co_evolution_loop.py", ".git/config"):
            value = config(); value["allowed_write_paths"]["harness"] = [path]
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "overlaps protected"):
                initialize_micro_evolution(value)

    def test_independent_bound_review_and_every_check_required(self):
        pending = self.pending()
        for field, value in (("reviewer_id", "research-agent"),
                             ("proposal_sha256", "8" * 64),
                             ("tested_pair_sha256", "8" * 64),
                             ("anchor_pair_sha256", "8" * 64),
                             ("benefit_observed", False)):
            receipt = review(pending); receipt[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                review_micro_evolution(pending, receipt)
        for name in MICRO_CHECKS:
            receipt = review(pending); receipt["checks"][name]["passed"] = False
            with self.subTest(check=name), self.assertRaisesRegex(ValueError, "check failed"):
                review_micro_evolution(pending, receipt)
        receipt = review(pending); receipt["checks"].pop("bounded_trial")
        with self.assertRaises(ValueError):
            review_micro_evolution(pending, receipt)

    def test_reject_does_not_require_a_successful_trial(self):
        pending = self.pending(); receipt = review(pending, "reject")
        receipt.update(checks={}, benefit_observed=False, benefit_evidence_sha256=None,
                       tested_pair_sha256=None, anchor_pair_sha256=None, actual_write_paths=[])
        rejected = review_micro_evolution(pending, receipt)
        self.assertEqual(rejected["active_pair"], self.state["active_pair"])

    def test_rollback_preserves_history_and_requires_review(self):
        pending = self.pending(); accepted = review_micro_evolution(pending, review(pending))
        receipt = {"reviewer_id": "trusted-supervisor", "reason": "Downstream regression",
                   "evidence_sha256": "3" * 64}
        back = rollback_micro_evolution(accepted, receipt)
        self.assertEqual(back["active_pair"], self.state["active_pair"])
        self.assertEqual(back["used_candidate_ids"], ["change-1"])
        self.assertEqual(len(back["history"]), 2)
        self.assertIsNone(back["previous_pair"])
        with self.assertRaises(ValueError):
            rollback_micro_evolution(back, receipt)

    def test_tampered_state_and_stale_parent_rejected(self):
        state = deepcopy(self.state); state["active_pair"]["harness_sha256"] = "9" * 64
        with self.assertRaisesRegex(ValueError, "modified"):
            propose_micro_evolution(state, proposal(self.state))
        value = proposal(self.state); value["parent_pair_sha256"] = "9" * 64
        with self.assertRaisesRegex(ValueError, "stale parent"):
            propose_micro_evolution(self.state, value)


if __name__ == "__main__":
    unittest.main()
