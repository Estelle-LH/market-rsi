"""Fake provider/sandbox receipts only: these are not market experiments."""
import json
import unittest

from dev_evidence import commit_completion
from diagnostic_channel import stderr_receipt
from market_rsi import fresh_json
from sandbox_failure_evidence import build_sandbox_failure
import test_dev_evidence as fixtures


class SandboxFailureTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.EvidenceTests()
        self.fx.setUp()
        self.root, self.study = self.fx.devroot, self.fx.study

    def tearDown(self):
        self.fx.tearDown()

    def failed_pipeline(self, action="experiment"):
        args = self.fx.pipeline(action)
        # All edits below affect this test's temporary fabricated receipts only.
        (self.root / "collected/execution.json").unlink()
        missing = {"execution.json": "NotFound"}
        if action == "experiment":
            (self.root / "collected/predictions/complete.json").unlink()
            path = self.root / "collected/predictions/predictions.jsonl"
            path.write_bytes(path.read_bytes().splitlines(keepends=True)[0])
            missing["predictions/complete.json"] = "NotFound"
        self.fx.mutate("collection.json", lambda x: x.update(missing_or_failed=missing))
        self.fx.mutate("command.json", lambda x: x.update(exit_code=1, stderr="PRIVATE_RUNNER_TRACEBACK"))
        self.fx.mutate("collected/protocol.json", lambda x: x.update(
            events=x["events"][:5 if action == "experiment" else 1] + [
                {"type": "timeout", "partial_response": "candidate's partial response"}]))
        fresh_json(self.root / "failure.json", {"error_type": "ValueError", "scored": False, "automatic_retry": False})
        fresh_json(self.root / "collected/failure.json", {"error_type": "TimeoutError", "scored": False})
        path = self.root / "collected/candidate-stderr.log"
        path.write_text("Candidate's own warning, not an independently established diagnosis.\n")
        (self.root / "collected/candidate-diagnostic.json").write_text(json.dumps(stderr_receipt(path)))
        return args

    def build(self, args):
        return build_sandbox_failure(self.study, self.root, **args)

    def test_keeps_partial_trace_without_score_or_runner_traceback(self):
        args = self.failed_pipeline()
        before = self.fx.fixture.budget.snapshot()
        built = self.build(args)
        result = built["completion"]
        self.assertFalse(result["eligible_submission"])
        feedback = result["payload"]["train_dev_results"]["dev"]
        self.assertIsNone(feedback["independent_score"])
        trace = feedback["available_trace"]
        self.assertEqual(len(trace["partial_predictions"]["committed_before_failure"]), 1)
        self.assertFalse(trace["candidate_stderr"]["independent_diagnosis"])
        self.assertEqual(trace["dev"], self.fx.fixture.artifacts["dev"]["rows"])
        self.assertIn("Candidate's own warning", json.dumps(result["payload"]))
        self.assertNotIn("PRIVATE_RUNNER_TRACEBACK", json.dumps(result["payload"]))
        self.assertEqual(result["payload"]["usage"]["sandbox"]["unresolved_hold_usd"], "0.10")
        self.assertEqual(self.fx.fixture.budget.snapshot(), before)

    def test_commit_keeps_failure_and_blocks_research_selection_and_freeze(self):
        args = self.failed_pipeline()
        commit_completion(self.study, self.build(args))
        state = self.study.snapshot()
        self.assertIsNone(state["active"])
        self.assertEqual(state["causal_review_trial_ids"], ["trial-01"])
        for action in (lambda: self.study.next_request("learn"),
                       lambda: self.study.claim("reset", "new-trial"),
                       lambda: self.study.claim_selection("learn", "selection-01"),
                       self.study.freeze_learning, self.study.freeze_transfer):
            with self.assertRaisesRegex(ValueError, "causal review"):
                action()
        self.assertEqual(self.fx.fixture.budget.snapshot()["reserved_usd"], "0.10")

    def test_inspection_failure_has_no_prediction_score(self):
        result = self.build(self.failed_pipeline("inspect"))["completion"]
        trace = result["payload"]["train_dev_results"]["dev"]["available_trace"]
        self.assertIsNone(trace["partial_predictions"])
        self.assertFalse(result["eligible_submission"])

    def test_live_admission_cannot_be_bypassed(self):
        args = self.failed_pipeline()
        args["expected_live"] = True
        with self.assertRaisesRegex(RuntimeError, "scientific admission"):
            self.build(args)

    def test_caller_cannot_replace_active_request(self):
        args = self.failed_pipeline()
        with self.assertRaises(ValueError):
            build_sandbox_failure(self.study, self.root, prepared_research=self.fx.prepared, **args)

    def test_unacknowledged_cleanup_remains_blocked(self):
        args = self.failed_pipeline()
        self.fx.mutate("cleanup-01.json", lambda x: x.update(kill_acknowledged=False))
        with self.assertRaisesRegex(ValueError, "kill"):
            self.build(args)

    def test_cleanup_of_another_sandbox_is_not_enough(self):
        args = self.failed_pipeline()
        self.fx.mutate("cleanup-01.json", lambda x: x.update(sandbox_id="unrelated"))
        with self.assertRaisesRegex(ValueError, "another sandbox"):
            self.build(args)

    def test_failed_preimport_isolation_needs_separate_review(self):
        args = self.failed_pipeline()
        self.fx.mutate("collected/isolation.json", lambda x: x.update(checks={}))
        with self.assertRaisesRegex(ValueError, "post-isolation"):
            self.build(args)

    def test_missing_library_is_not_candidate_failure(self):
        args = self.failed_pipeline()
        self.fx.mutate("libraries.json", lambda x: x.update(actual={}))
        with self.assertRaisesRegex(ValueError, "library"):
            self.build(args)

    def test_nonterminal_command_error_cannot_be_closed(self):
        args = self.failed_pipeline()
        fresh_json(self.root / "command-error.json", {"error_type": "TimeoutError"})
        with self.assertRaises(ValueError):
            self.build(args)

    def test_successful_command_cannot_be_discarded(self):
        args = self.failed_pipeline()
        self.fx.mutate("command.json", lambda x: x.update(exit_code=0))
        with self.assertRaisesRegex(ValueError, "nonzero terminal"):
            self.build(args)

    def test_successful_execution_cannot_be_discarded(self):
        args = self.failed_pipeline()
        fresh_json(self.root / "collected/execution.json", {"scored": False})
        with self.assertRaisesRegex(ValueError, "conflict"):
            self.build(args)

    def test_finished_predictions_cannot_be_discarded(self):
        args = self.failed_pipeline()
        fresh_json(self.root / "collected/predictions/complete.json", {})
        with self.assertRaisesRegex(ValueError, "silently discarded"):
            self.build(args)

    def test_changed_partial_prediction_is_rejected(self):
        args = self.failed_pipeline()
        path = self.root / "collected/predictions/predictions.jsonl"
        row = json.loads(path.read_text())
        row["prediction"] = .7
        path.write_text(json.dumps(row) + "\n")
        with self.assertRaisesRegex(ValueError, "journal changed"):
            self.build(args)

    def test_missing_required_failure_output_blocks_completion(self):
        args = self.failed_pipeline()
        self.fx.mutate("collection.json", lambda x: x["missing_or_failed"].update({"protocol.json": "TimeoutError"}))
        with self.assertRaisesRegex(ValueError, "not collected"):
            self.build(args)

    def test_malformed_protocol_events_reject_cleanly(self):
        args = self.failed_pipeline()
        self.fx.mutate("collected/protocol.json", lambda x: x.update(events=["untrusted string"]))
        with self.assertRaisesRegex(ValueError, "protocol evidence"):
            self.build(args)

    def test_diagnostic_mutation_after_build_prevents_memory_commit(self):
        args = self.failed_pipeline()
        built = self.build(args)
        (self.root / "collected/candidate-stderr.log").write_text("replacement")
        with self.assertRaises(ValueError):
            commit_completion(self.study, built)
        self.assertIsNotNone(self.study.snapshot()["active"])


if __name__ == "__main__":
    unittest.main()
