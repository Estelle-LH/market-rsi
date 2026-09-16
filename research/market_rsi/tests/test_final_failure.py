"""Fabricated final failure/review cases; no actual candidate/provider execution."""
import json
import unittest
from unittest.mock import patch

from market_rsi import Journal, fresh_json
import test_final_stage as fixtures


class FinalFailureTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.FinalTests()
        self.fx.setUp(); self.fx.context(); self.fx.seal()
        self.stage = self.fx.create()
        self.job = self.stage._load()[0]["jobs"][0]["job_id"]
        self.root = self.stage.root / "jobs" / self.job
        self.rationale = ("Human fixture judgment only: fabricated evidence describes a candidate timeout "
            "after valid isolation and unchanged setup. No real failure cause is asserted.")

    def tearDown(self):
        self.fx.tearDown()

    def mutate(self, name, update):
        path = self.root / name
        value = json.loads(path.read_text()); update(value); path.write_text(json.dumps(value))

    def failed_executor(self, bundle, root, budget):
        self.fx.fx.execute_fixture(bundle, root, budget)
        (root / "collected/execution.json").unlink()
        (root / "collected/predictions/complete.json").unlink()
        (root / "collected/predictions/predictions.jsonl").write_bytes(b"")
        self.mutate("command.json", lambda x: x.update(exit_code=1, stderr="PRIVATE_RUNNER_TRACEBACK"))
        self.mutate("collection.json", lambda x: x.update(missing_or_failed={"execution.json": "NotFound", "predictions/complete.json": "NotFound"}))
        self.mutate("collected/protocol.json", lambda x: x.update(events=x["events"][:3] + [{"type": "timeout"}]))
        fresh_json(root / "failure.json", {"error_type": "ValueError", "scored": False, "automatic_retry": False})
        fresh_json(root / "collected/failure.json", {"error_type": "TimeoutError", "scored": False})

    def run_failure(self):
        return self.stage.tick(fixture_execute=self.failed_executor)

    def review(self):
        return self.stage.review_failure(self.job, review_id="final-review-01", rationale=self.rationale,
            evidence_paths=[self.root / "collected/protocol.json", self.root / "libraries.json"])

    def test_closed_failure_is_retained_without_score_and_blocks_more_paid_dispatch(self):
        result = self.run_failure()
        self.assertEqual(result["status"], "failed_unscored")
        count = self.fx.fx.executions
        snapshot = self.stage.status_report()
        self.assertEqual(snapshot["planned_executions"], 8)
        self.assertEqual(snapshot["terminal_executions"], 1)
        self.assertEqual(snapshot["failed_executions"], 1)
        self.assertEqual(snapshot["jobs"][0]["status"], "failed_unscored")
        self.assertTrue(all(j["status"] == "not_started" for j in snapshot["jobs"][1:]))
        self.assertIsNone(snapshot["numeric_score"])
        self.assertEqual(self.stage.tick()["action"], "causal_review_required")
        self.assertEqual(self.fx.fx.executions, count)
        saved = json.loads((self.root / "verified-final.json").read_text())
        self.assertIsNone(saved["predictions"])
        self.assertFalse(saved["failure_observation"]["cause_independently_established"])
        self.assertNotIn("PRIVATE_RUNNER_TRACEBACK", json.dumps(saved["failure_observation"]))

    def test_review_keeps_failure_and_cost_then_final_report_contains_all_tasks(self):
        old_memory = self.fx.study.journal.path.read_bytes()
        self.run_failure()
        original = (self.root / "verified-final.json").read_bytes()
        before = self.fx.budget.snapshot()
        self.review()
        self.assertEqual(self.fx.budget.snapshot(), before)
        self.assertEqual((self.root / "verified-final.json").read_bytes(), original)
        for _ in range(7):
            self.stage.tick(fixture_execute=self.fx.fx.execute_fixture)
        result = self.stage.score()
        self.assertEqual(result["verified_executions"], 8)
        self.assertEqual(result["successful_executions"], 7)
        self.assertEqual(result["failed_executions"], 1)
        self.assertFalse(result["full_comparison_available"])
        self.assertEqual(result["failed_job_ids"], [self.job])
        self.assertEqual(set(result["tasks"]), {"task-2", "task-3"})
        failed_task = result["tasks"]["task-2"]
        self.assertFalse(failed_task["comparison_complete"])
        self.assertTrue(all(v is None for v in failed_task["against_common_baseline"].values()))
        self.assertEqual(self.fx.study.journal.path.read_bytes(), old_memory)
        self.assertNotIn(self.rationale, json.dumps(result))
        self.assertFalse(self.stage.status_report()["comparison_complete"])

    def test_missing_cleanup_is_ambiguous_not_a_closed_candidate_failure(self):
        def executor(bundle, root, budget):
            self.failed_executor(bundle, root, budget)
            self.mutate("cleanup-01.json", lambda x: x.update(kill_acknowledged=False))
        with self.assertRaisesRegex(ValueError, "kill"):
            self.stage.tick(fixture_execute=executor)
        self.assertEqual(self.stage.tick()["action"], "reconcile_pending")
        self.assertEqual(self.stage.status_report()["jobs"][0]["status"], "pending_unreconciled")
        with self.assertRaisesRegex(ValueError, "completed unreviewed"):
            self.review()

    def test_command_transport_error_remains_pending(self):
        def executor(bundle, root, budget):
            self.failed_executor(bundle, root, budget)
            fresh_json(root / "command-error.json", {"error_type": "TimeoutError"})
        with self.assertRaises(ValueError):
            self.stage.tick(fixture_execute=executor)
        self.assertEqual(self.stage.status_report()["terminal_executions"], 0)

    def test_missing_package_setup_cannot_be_called_candidate_outcome(self):
        def executor(bundle, root, budget):
            self.failed_executor(bundle, root, budget)
            self.mutate("libraries.json", lambda x: x.update(actual={}))
        with self.assertRaisesRegex(ValueError, "setup/library"):
            self.stage.tick(fixture_execute=executor)

    def test_success_receipts_cannot_be_discarded_as_failed_score(self):
        def executor(bundle, root, budget):
            self.fx.fx.execute_fixture(bundle, root, budget)
            self.mutate("command.json", lambda x: x.update(exit_code=1))
            fresh_json(root / "failure.json", {"error_type": "ValueError", "scored": False, "automatic_retry": False})
            fresh_json(root / "collected/failure.json", {"error_type": "TimeoutError", "scored": False})
        with self.assertRaises(ValueError):
            self.stage.tick(fixture_execute=executor)

    def test_candidate_stderr_alone_cannot_clear_the_review(self):
        self.run_failure()
        with self.assertRaisesRegex(ValueError, "stderr alone"):
            self.stage.review_failure(self.job, review_id="final-review-01", rationale=self.rationale,
                evidence_paths=[self.root / "collected/candidate-stderr.log", self.root / "collected/candidate-diagnostic.json"])

    def test_duplicate_review_or_source_outcome_change_is_rejected(self):
        self.run_failure(); self.review()
        with self.assertRaises(ValueError):
            self.review()
        self.assertEqual(self.stage.status_report()["failed_executions"], 1)

    def test_review_transaction_can_recover_without_extra_execution(self):
        self.run_failure()
        count = self.fx.fx.executions
        original = Journal.append
        def fail_append(journal, event, payload):
            if event == "failure_reviewed":
                raise OSError("fixture transaction interruption")
            return original(journal, event, payload)
        with patch.object(Journal, "append", fail_append):
            with self.assertRaises(OSError):
                self.review()
        self.assertEqual(self.stage.tick()["action"], "causal_review_required")
        self.review()
        self.assertEqual(self.fx.fx.executions, count)
        self.assertTrue(self.stage.status_report()["jobs"][0]["reviewed"])

    def test_changed_terminal_failure_evidence_blocks_review(self):
        self.run_failure()
        self.mutate("collected/protocol.json", lambda x: x["events"].append({"type": "timeout"}))
        with self.assertRaisesRegex(ValueError, "differs from its original"):
            self.review()

    def test_later_invoice_does_not_rewrite_failure_snapshot(self):
        self.run_failure()
        original = (self.root / "verified-final.json").read_bytes()
        self.fx.budget.settle_metered(self.job, "0.01", {"terminal": True, "fixture": True})
        self.fx.budget.record_invoice(self.job, "0.015", "b" * 64)
        before = self.fx.budget.snapshot()
        self.review()
        self.assertEqual(self.fx.budget.snapshot(), before)
        self.assertEqual((self.root / "verified-final.json").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
