"""Review transitions over fabricated failure receipts; no provider or market run."""
import copy
import json
import unittest
from unittest.mock import patch

from dev_evidence import commit_completion
from failure_review import build_failure_review, commit_failure_review
from market_rsi import digest
import test_sandbox_failure_evidence as fixtures


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.SandboxFailureTests()
        self.fx.setUp()
        self.args = self.fx.failed_pipeline()
        self.study, self.root = self.fx.study, self.fx.root
        commit_completion(self.study, self.fx.build(self.args))
        self.rationale = ("Fabricated fixture review only: the fixture records a candidate response "
            "timeout after successful isolation and unchanged runtime setup. No real cause is asserted.")
        self.paths = [self.root / "collected/protocol.json", self.root / "libraries.json"]

    def tearDown(self):
        self.fx.tearDown()

    def build(self, **overrides):
        arguments = dict(trial_id="trial-01", review_id="review-01", rationale=self.rationale,
                         evidence_paths=self.paths, **self.args)
        arguments.update(overrides)
        return build_failure_review(self.study, self.root, **arguments)

    def original(self):
        return (self.study.root / "steps/trial-01/completion.json").read_bytes()

    def test_review_retains_original_failure_cost_and_guide_then_permits_next_new_id(self):
        original = self.original()
        before = self.fx.fx.fixture.budget.snapshot()
        built = self.build()
        self.assertFalse(built["automatic_causal_diagnosis"])
        commit_failure_review(self.study, built)
        self.assertEqual(self.original(), original)
        self.assertEqual(self.fx.fx.fixture.budget.snapshot(), before)
        snapshot = self.study.snapshot()
        self.assertEqual(snapshot["causal_review_trial_ids"], [])
        self.assertEqual(snapshot["reviewed_failure_trial_ids"], ["trial-01"])
        self.assertEqual(snapshot["records_by_arm"]["learn"], 1)
        prepared = self.study.claim("learn", "trial-02")
        self.assertEqual(prepared["audit"]["step_index"], 1)
        public = json.loads(prepared["messages"][1]["content"])
        self.assertNotIn(self.rationale, json.dumps(public))
        self.assertNotIn(str(self.root), json.dumps(public))
        self.assertTrue(public["records"][0]["payload"]["failure"]["continuation_requires_causal_review"])
        self.assertIsNone(public["research_guide"])

    def test_other_arm_sees_neither_failure_nor_review_advice(self):
        commit_failure_review(self.study, self.build())
        request = self.study.next_request("archive")
        public = json.loads(request["messages"][1]["content"])
        self.assertEqual(public["records"], [])
        self.assertNotIn(self.rationale, json.dumps(public))

    def test_duplicate_review_is_not_an_extra_attempt_or_new_judgment(self):
        built = self.build()
        commit_failure_review(self.study, built)
        with self.assertRaises(ValueError):
            commit_failure_review(self.study, built)
        with self.assertRaises(ValueError):
            self.build(review_id="review-02")
        with self.assertRaises(ValueError):
            self.study.claim("learn", "trial-01")

    def test_candidate_stderr_only_never_establishes_cause(self):
        with self.assertRaisesRegex(ValueError, "stderr alone"):
            self.build(evidence_paths=[self.root / "collected/candidate-stderr.log",
                                       self.root / "collected/candidate-diagnostic.json"])

    def test_unrelated_evidence_cannot_be_used_to_clear_pause(self):
        with self.assertRaisesRegex(ValueError, "unverified"):
            self.build(evidence_paths=[self.paths[0], self.root / "unrelated.json"])

    def test_full_failure_receipts_are_reverified_not_just_citations(self):
        self.fx.fx.mutate("cleanup-01.json", lambda x: x.update(kill_acknowledged=False))
        with self.assertRaisesRegex(ValueError, "kill"):
            self.build()
        self.assertEqual(self.study.snapshot()["causal_review_trial_ids"], ["trial-01"])

    def test_missing_library_remains_infrastructure_failure_not_reviewable_candidate(self):
        self.fx.fx.mutate("libraries.json", lambda x: x.update(actual={}))
        with self.assertRaisesRegex(ValueError, "library"):
            self.build()

    def test_mutation_after_build_blocks_review_commit(self):
        built = self.build()
        self.fx.fx.mutate("command.json", lambda x: x.update(exit_code=9))
        with self.assertRaises(ValueError):
            commit_failure_review(self.study, built)
        self.assertEqual(self.study.snapshot()["causal_review_trial_ids"], ["trial-01"])

    def test_live_path_keeps_actual_admission_gate_closed(self):
        with self.assertRaisesRegex(RuntimeError, "scientific admission"):
            self.build(expected_live=True)

    def test_changed_source_or_contract_cannot_be_a_review_disposition(self):
        built = self.build()
        built["review"]["disposition"] = "patched_runtime_and_retry"
        with self.assertRaisesRegex(ValueError, "unchanged contract"):
            commit_failure_review(self.study, built)

    def test_another_completion_cannot_replace_the_original(self):
        built = self.build()
        built["review"]["completion_sha256"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "replace an outcome"):
            commit_failure_review(self.study, built)

    def test_another_manifest_or_source_cannot_clear_pause(self):
        for key in ("study_manifest_sha256", "review_source_sha256"):
            built = self.build()
            built["review"][key] = "a" * 64
            with self.assertRaises(ValueError):
                commit_failure_review(self.study, built)

    def test_crash_after_durable_review_can_recover_without_new_outcome(self):
        built = self.build()
        with patch.object(self.study.journal, "append", side_effect=OSError("fixture interruption")):
            with self.assertRaises(OSError):
                commit_failure_review(self.study, built)
        self.assertEqual(self.study.snapshot()["causal_review_trial_ids"], ["trial-01"])
        rebuilt = self.build()
        self.assertEqual(rebuilt["review"], built["review"])
        commit_failure_review(self.study, rebuilt)
        self.assertEqual(self.study.snapshot()["causal_review_trial_ids"], [])
        self.assertEqual(len(self.study.journal.read()), 4)

    def test_review_file_mutation_breaks_replay(self):
        built = self.build()
        commit_failure_review(self.study, built)
        path = self.study.root / "failure-reviews/review-01/review.json"
        content = json.loads(path.read_text())
        content["rationale"] = "Changed reviewer statement after the permanent record was committed."
        path.write_text(json.dumps(content))
        with self.assertRaisesRegex(ValueError, "review changed"):
            self.study.snapshot()

    def test_later_verified_metering_and_invoice_do_not_rewrite_past_hold(self):
        original = self.original()
        budget = self.fx.fx.fixture.budget
        budget.settle_metered(self.root.name, "0.01", {"terminal": True, "fixture": True})
        budget.record_invoice(self.root.name, "0.012", "b" * 64)
        before = budget.snapshot()
        built = self.build()
        self.assertEqual(built["review"]["accounting_at_review"]["invoiced_usd"], "0.012")
        self.assertEqual(built["review"]["accounting_at_review"]["unresolved_hold_usd"], "0")
        commit_failure_review(self.study, built)
        self.assertEqual(self.original(), original)
        self.assertEqual(budget.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
