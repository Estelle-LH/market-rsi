"""Original consumer/native recorder/dispatcher/worker, synthetic processes only."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch

from supervisor_harness import continuous_candidate_handoff as h
from supervisor_harness import account_controller_feedback_consumer as c
from supervisor_harness import opened_train_discovery_worker as w
from supervisor_harness import test_reviewed_candidate_dispatch as dispatch_fixture
from supervisor_harness import test_continuous_discovery_batch as recorder_fixture
from supervisor_harness import test_account_controller_feedback_consumer as consumer_fixture
from supervisor_harness import test_learning_checkpoint_assessment as learning_fixture
from supervisor_harness.learning_checkpoint_assessment import assess_checkpoint
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
from data_scientist_harness import test_micro_evolution as micro_fixture
from data_scientist_harness.co_evolution_loop import micro_pair_hash


NOW = consumer_fixture.NOW


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.f = dispatch_fixture.DispatchTests()
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.helper = recorder_fixture.ContinuousDiscoveryBatchTests()
        parent = self.helper.archived_parent("reviewed-negative")
        parent["candidate_sha256"] = consumer_fixture.PARENT
        self.batch = ContinuousDiscoveryBatch(self.f.f.root / "handoff-native", allow_temporary=True,
            test_clock=lambda: NOW, allow_test_clock=True)
        authority = self.f.f.values["authority"]
        self.batch.initialize(batch_id=authority["batch_id"], start_utc=authority["start_utc"],
            deadline_utc=authority["deadline_utc"], max_attempts=1,
            initial_incumbent={"candidate_id": "market", "candidate_sha256": consumer_fixture.INCUMBENT,
                "scorecard_sha256": "a" * 64, "review_sha256": "b" * 64},
            active_pool_capacity=2, initial_archived_parents=[parent],
            scheduling_policy="final-singleton-v1")
        self.batch.record_micro_evolution("initialize", micro_fixture.config(),
            expected_state_sha256=self.batch.snapshot()["state_sha256"])
        self.decision = self.f.decision
        self.selection = self.helper.pool_member("a", parent=consumer_fixture.PARENT,
                                               allocation="exploration")
        self.selection.update(candidate_id=self.decision["candidate_id"],
            controller_decision_sha256=c._digest(self.decision),
            question_id=self.decision["question_id"],
            question_digest_sha256=c._digest({"question_id": self.decision["question_id"],
                                             "hypothesis": self.decision["hypothesis"]}),
            hypothesis_digest_sha256=c._digest(self.decision["hypothesis"]))
        self.contract = {"schema": "controller_candidate_contract_v1",
                         "decision_sha256": c._digest(self.decision)}
        self.contract.update({key: self.decision[key] for key in h.CONTRACT_FIELDS
                              - {"schema", "decision_sha256"}})
        self.contract_binding = self.write("new-contract", self.contract)
        self.request = {**self.f.request, "spec_sha256": self.contract_binding["sha256"],
            "runtime_pair_sha256": micro_pair_hash(self.batch.snapshot()["micro_evolution"])}
        self.request_binding = self.write("handoff-request", self.request)
        self.review = {**self.f.review, "request_sha256": self.request_binding["sha256"],
            "contract_sha256": self.contract_binding["sha256"],
            "selection_sha256": c._digest(self.selection), "source_commit": self.request["source_commit"],
            "files": self.request["files"], "semantic_source_matches_decision": True}
        self.review_binding = self.write("source-review", self.review)

    def write(self, label, value):
        path = self.f.f.root / (label + ".json")
        path.write_text(json.dumps(value, allow_nan=False))
        return {"path": str(path), "sha256": w.sha(path)}

    def invoke(self, **kwargs):
        arguments = {"now": NOW}; arguments.update(kwargs)
        return h.handoff(self.batch, self.selection, self.request_binding, self.review_binding,
            self.contract_binding, self.f.directory, self.f.authority_binding, self.f.f.repo, **arguments)

    def test_actual_original_negative_parent_to_native_prediction_worker(self):
        with patch.object(w.subprocess, "Popen", side_effect=self.f.completed_child) as launch:
            receipt = self.invoke()
        launch.assert_called_once(); self.assertEqual(receipt["outcome"], "succeeded")
        self.assertIs(receipt["metrics_independently_reviewed"], False)
        branch = self.batch.snapshot()["branches"][0]
        for key, value in self.selection.items(): self.assertEqual(branch[key], value)
        self.assertEqual(branch["comparison_incumbent_sha256"], consumer_fixture.INCUMBENT)
        self.assertEqual(branch["stage"], "execution_terminal")
        self.assertEqual(self.batch.snapshot()["incumbent"]["candidate_sha256"], consumer_fixture.INCUMBENT)
        record = json.loads((self.batch.root / "handoff/a.json").read_text())
        self.assertEqual(record["source_review"], self.review_binding)
        self.assertIn("derivative adapter", record["dispatch_review_role"])

    def test_native_selection_owns_clock_not_supervisor_supplied_test_timestamp(self):
        original = self.batch.select_controller_pool
        def strict_native(selections, *, now=None):
            if now is not None:
                raise RuntimeError("production native clock rejects supplied time")
            return original(selections)
        with patch.object(self.batch, "select_controller_pool", side_effect=strict_native) as selected, \
                patch.object(w.subprocess, "Popen", side_effect=self.f.completed_child):
            receipt = self.invoke()
        self.assertEqual(receipt["outcome"], "succeeded")
        selected.assert_called_once_with([self.selection])

    def test_closed_supervisor_budget_still_rejects_before_native_own_clock(self):
        with patch.object(self.batch, "select_controller_pool") as selected, \
                patch.object(w.subprocess, "Popen") as launch, self.assertRaises(ValueError):
            self.invoke(now=c.CUTOFF)
        selected.assert_not_called(); launch.assert_not_called()

    def test_completed_recovery_no_reselection_no_head_no_authority_no_spawn(self):
        with patch.object(w.subprocess, "Popen", side_effect=self.f.completed_child): first = self.invoke()
        self.f.f.write("authority", {"closed": True})
        self.batch = ContinuousDiscoveryBatch(self.batch.root, allow_temporary=True,
            test_clock=lambda: datetime(2026, 10, 6, tzinfo=timezone.utc), allow_test_clock=True)
        with patch.object(self.batch, "select_controller_pool", side_effect=AssertionError("no selection")), \
                patch.object(w.subprocess, "check_output", side_effect=AssertionError("no HEAD")), \
                patch.object(w.subprocess, "Popen") as launch:
            second = self.invoke(now=c.DEADLINE)
        self.assertEqual(first, second); launch.assert_not_called()

    def test_native_nonzero_failure_is_factual_and_never_relaunched(self):
        with patch.object(w.subprocess, "Popen", return_value=Mock(
                pid=1234, wait=Mock(return_value=7), poll=Mock(return_value=7))) as launch:
            first = self.invoke(); second = self.invoke()
        self.assertEqual(first, second); launch.assert_called_once()
        self.assertEqual(first["outcome"], "failed"); self.assertIsNone(first["error"])

    def test_uncertain_original_claim_does_not_retry(self):
        with patch.object(w.subprocess, "Popen", side_effect=KeyboardInterrupt("uncertain")) as launch:
            with self.assertRaises(KeyboardInterrupt): self.invoke()
            with self.assertRaisesRegex(RuntimeError, "incomplete original claim"): self.invoke()
        launch.assert_called_once()
        self.assertEqual(self.batch.snapshot()["branches"][0]["stage"], "execution_claimed")

    def test_exact_already_selected_branch_resumes_without_reselecting(self):
        self.batch.select_controller_pool([self.selection])
        with patch.object(self.batch, "select_controller_pool", side_effect=AssertionError("no reselection")), \
                patch.object(w.subprocess, "Popen", side_effect=self.f.completed_child) as launch:
            receipt = self.invoke()
        launch.assert_called_once(); self.assertEqual(receipt["outcome"], "succeeded")

    def test_contract_original_question_hypothesis_recipe_parent_and_identity_denials(self):
        for change in ({"question_id": "different"}, {"hypothesis": "different"},
                       {"recipe": "different"}, {"expected_evidence": "different"},
                       {"actual_parent_sha256": consumer_fixture.OTHER},
                       {"comparison_incumbent_sha256": consumer_fixture.OTHER},
                       {"candidate_id": "different"}, {"decision_sha256": "f" * 64},
                       {"schema": "other"}, {"extra": 0}):
            self.contract_binding = self.write("new-contract", {**self.contract, **change})
            with patch.object(w.subprocess, "Popen") as launch:
                with self.assertRaisesRegex(ValueError, "admission drift"): self.invoke()
                launch.assert_not_called()
        self.assertEqual(self.batch.snapshot()["branches"], [])

    def test_independent_semantic_review_all_bindings_are_mandatory(self):
        for change in ({"semantic_source_matches_decision": False},
                       {"semantic_source_matches_decision": 1}, {"passed": 1},
                       {"selection_sha256": "f" * 64}, {"files": {}},
                       {"source_commit": "different"}, {"contract_sha256": "f" * 64},
                       {"request_sha256": "f" * 64}, {"authority_sha256": "f" * 64},
                       {"decision_sha256": "f" * 64}, {"extra": True}):
            self.review_binding = self.write("source-review", {**self.review, **change})
            with patch.object(w.subprocess, "Popen") as launch:
                with self.assertRaisesRegex(ValueError, "admission drift"): self.invoke()
                launch.assert_not_called()
        self.assertEqual(self.batch.snapshot()["branches"], [])

    def test_even_resealed_review_cannot_change_original_native_question(self):
        original = deepcopy(self.selection)
        for change in ({"question_id": "different"}, {"question_digest_sha256": "f" * 64},
                       {"hypothesis_digest_sha256": "f" * 64},
                       {"controller_decision_sha256": "f" * 64},
                       {"research_parent_sha256": consumer_fixture.OTHER}):
            self.selection = {**original, **change}
            self.review_binding = self.write("source-review", {
                **self.review, "selection_sha256": c._digest(self.selection)})
            with self.assertRaisesRegex(ValueError, "admission drift"): self.invoke()
        self.assertEqual(self.batch.snapshot()["branches"], [])

    def test_supplied_method_allocation_rule_resource_change_requires_new_admission(self):
        original = deepcopy(self.selection)
        for change in ({"method_family": "different"}, {"allocation": "exploitation"},
                       {"predeclared_rule_sha256": "f" * 64},
                       {"resource_hint": {**original["resource_hint"], "max_time_seconds": 599}}):
            self.selection = {**original, **change}
            with self.assertRaisesRegex(ValueError, "admission drift"): self.invoke()
        self.assertEqual(self.batch.snapshot()["branches"], [])

    def test_existing_different_question_branch_denied_without_worker(self):
        self.batch.select_controller_pool([{**self.selection, "question_id": "different"}])
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "selected branch/lineage drift"): self.invoke()
            launch.assert_not_called()

    def test_original_claim_tamper_denied_before_selection(self):
        path = self.f.directory / "claim.json"
        claim = json.loads(path.read_text()); claim["consumer_source_sha256"] = "f" * 64
        path.write_text(json.dumps(claim))
        with self.assertRaisesRegex(ValueError, "claim/schema drift"): self.invoke()
        self.assertEqual(self.batch.snapshot()["branches"], [])

    def test_reviewed_source_bytes_drift_denied_before_selection(self):
        (self.f.f.repo / self.f.runner).write_text("changed sibling")
        with self.assertRaisesRegex(ValueError, "source file drift"): self.invoke()
        self.assertEqual(self.batch.snapshot()["branches"], [])

    def test_handoff_and_derived_review_drift_stop_cached_replay(self):
        with patch.object(w.subprocess, "Popen", side_effect=self.f.completed_child): self.invoke()
        path = self.batch.root / "handoff/a.dispatch-review.json"
        path.write_text("{}")
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "derived dispatch review drift"): self.invoke()
            launch.assert_not_called()

    def test_two_concurrent_calls_make_one_selection_and_spawn(self):
        results, errors = [], []
        def call():
            try: results.append(self.invoke())
            except Exception as error: errors.append(error)
        with patch.object(w.subprocess, "Popen", side_effect=self.f.completed_child) as launch, \
                patch.object(self.batch, "select_controller_pool", wraps=self.batch.select_controller_pool) as select:
            threads = [threading.Thread(target=call) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
        self.assertEqual(errors, []); self.assertEqual(results[0], results[1])
        select.assert_called_once(); launch.assert_called_once()

    def test_global_cutoff_and_self_grant_stop_before_new_native_selection(self):
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "selection stop"): self.invoke(now=c.CUTOFF)
            with self.assertRaisesRegex(ValueError, "binding drift"):
                self.invoke(prospective_binding={"attempts": 999})
        launch.assert_not_called(); self.assertEqual(self.batch.snapshot()["branches"], [])

    def test_ordinary_two_branch_requirement_is_not_weakened(self):
        parent = self.helper.archived_parent("reviewed-negative")
        parent["candidate_sha256"] = consumer_fixture.PARENT
        authority = self.f.f.values["authority"]
        self.batch = ContinuousDiscoveryBatch(self.f.f.root / "ordinary-native", allow_temporary=True,
            test_clock=lambda: NOW, allow_test_clock=True)
        self.batch.initialize(batch_id=authority["batch_id"], start_utc=authority["start_utc"],
            deadline_utc=authority["deadline_utc"], max_attempts=2,
            initial_incumbent={"candidate_id": "market", "candidate_sha256": consumer_fixture.INCUMBENT,
                "scorecard_sha256": "a" * 64, "review_sha256": "b" * 64},
            active_pool_capacity=2, initial_archived_parents=[parent],
            scheduling_policy="final-singleton-v1")
        self.batch.record_micro_evolution("initialize", micro_fixture.config(),
            expected_state_sha256=self.batch.snapshot()["state_sha256"])
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "active global pool must contain 2 or 3"): self.invoke()
        launch.assert_not_called(); self.assertEqual(self.batch.snapshot()["branches"], [])

    def test_postselection_interruption_resumes_exact_native_selection_once(self):
        original = self.batch.select_controller_pool
        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("interrupted after durable native selection")
        with patch.object(self.batch, "select_controller_pool", side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError, "durable native selection"): self.invoke()
        self.assertFalse((self.batch.root / "handoff/a.json").exists())
        with patch.object(self.batch, "select_controller_pool", side_effect=AssertionError("no reselection")), \
                patch.object(w.subprocess, "Popen", side_effect=self.f.completed_child) as launch:
            receipt = self.invoke()
        launch.assert_called_once(); self.assertEqual(receipt["outcome"], "succeeded")

    def test_completed_receipt_reconciles_interrupted_terminal_once(self):
        original = self.batch.mark_execution_terminal
        with patch.object(self.batch, "mark_execution_terminal", side_effect=RuntimeError("terminal interruption")), \
                patch.object(w.subprocess, "Popen", side_effect=self.f.completed_child) as launch:
            with self.assertRaisesRegex(RuntimeError, "terminal interruption"): self.invoke()
            launch.assert_called_once()
        self.assertEqual(self.batch.snapshot()["branches"][0]["stage"], "execution_claimed")
        with patch.object(w.subprocess, "Popen") as launch:
            receipt = self.invoke(now=c.DEADLINE)
        launch.assert_not_called(); self.assertEqual(receipt["outcome"], "succeeded")
        self.assertEqual(self.batch.snapshot()["branches"][0]["stage"], "execution_terminal")

    def test_v4_negative_learning_branch_retains_distinct_question_eligibility(self):
        label = "reviewed-negative"
        parent = self.helper.archived_parent(label)
        parent["candidate_sha256"] = consumer_fixture.PARENT
        assessment = assess_checkpoint(learning_fixture.checkpoint(label, credit=2, action="branch"),
                                       learning_fixture.branch(label), set())
        parent.update(learning_checkpoint=assessment, consumed_followups=0,
            consumption_receipt_sha256=learning_fixture.sha("synthetic-no-consumption"),
            consumed_question_sha256s=[])
        authority = self.f.f.values["authority"]
        self.batch = ContinuousDiscoveryBatch(self.f.f.root / "v4-native", allow_temporary=True,
            test_clock=lambda: NOW, allow_test_clock=True)
        self.batch.initialize(batch_id=authority["batch_id"], start_utc=authority["start_utc"],
            deadline_utc=authority["deadline_utc"], max_attempts=1,
            initial_incumbent={"candidate_id": "market", "candidate_sha256": consumer_fixture.INCUMBENT,
                "scorecard_sha256": "a" * 64, "review_sha256": "b" * 64},
            active_pool_capacity=2, initial_archived_parents=[parent], learning_checkpoint_version=1)
        self.batch.record_micro_evolution("initialize", micro_fixture.config(),
            expected_state_sha256=self.batch.snapshot()["state_sha256"])
        self.request["runtime_pair_sha256"] = micro_pair_hash(self.batch.snapshot()["micro_evolution"])
        self.request_binding = self.write("handoff-request", self.request)
        self.review_binding = self.write("source-review", {
            **self.review, "request_sha256": self.request_binding["sha256"]})
        with patch.object(w.subprocess, "Popen", side_effect=self.f.completed_child): receipt = self.invoke()
        self.assertEqual(receipt["outcome"], "succeeded")
        self.assertEqual(self.batch.snapshot()["scheduling_version"], 4)
        self.assertEqual(self.batch.snapshot()["branches"][0]["research_parent_sha256"], consumer_fixture.PARENT)

    def test_original_extended_review_record_cannot_be_replaced_on_recovery(self):
        with patch.object(w.subprocess, "Popen", side_effect=self.f.completed_child): self.invoke()
        path = self.batch.root / "handoff/a.json"
        record = json.loads(path.read_text()); record["source_review"]["sha256"] = "f" * 64
        path.write_text(json.dumps(record))
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "handoff/source binding drift"): self.invoke()
            launch.assert_not_called()

    def test_handoff_directory_symlink_denied_before_selection(self):
        target = self.f.f.root / "outside-handoff"; target.mkdir()
        (self.batch.root / "handoff").symlink_to(target)
        with self.assertRaisesRegex(ValueError, "handoff directory symlink"): self.invoke()
        self.assertEqual(self.batch.snapshot()["branches"], [])


if __name__ == "__main__": unittest.main()
