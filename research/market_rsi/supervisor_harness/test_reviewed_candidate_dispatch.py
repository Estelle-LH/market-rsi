"""Synthetic native recorder/worker and original consumer replay, zero real fits."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from supervisor_harness import reviewed_candidate_dispatch as d
from supervisor_harness import account_controller_feedback_consumer as c
from supervisor_harness import opened_train_discovery_worker as w
from supervisor_harness import test_account_controller_feedback_consumer as consumer_fixture
from supervisor_harness import test_continuous_discovery_batch as recorder_fixture
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
from data_scientist_harness import test_micro_evolution as micro_fixture
from data_scientist_harness.co_evolution_loop import micro_pair_hash


NOW = consumer_fixture.NOW


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is not None else NOW.replace(tzinfo=None)


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.f = consumer_fixture.Fixture(self.temp.name)
        self.patches = [patch.object(c, "CLI", self.f.cli),
                        patch.object(c, "CLI_SHA", c.sha(self.f.cli)),
                        patch.object(w, "datetime", FrozenDatetime),
                        patch.object(w, "sample_rss", return_value=128)]
        for value in self.patches: value.start(); self.addCleanup(value.stop)
        authority = deepcopy(self.f.values["authority"])
        authority["batch_id"] = "synthetic-dispatch"
        self.f.write("authority", authority)
        with patch.object(c.subprocess, "check_output", return_value=b"synthetic source"):
            self.packet = self.f.prepare()
            self.decision = c.consume(self.packet, self.f.root / "calls", batch=self.f.batch,
                repo=self.f.repo, now=NOW, transport=self.f.transport)
            self.second_decision = {**self.decision, "candidate_id": "second-generic-candidate",
                                    "actual_parent_sha256": consumer_fixture.OTHER}
            with patch.object(self.f, "decision", return_value=self.second_decision):
                c.consume(self.packet, self.f.root / "calls-b", batch=self.f.batch,
                    repo=self.f.repo, now=NOW, transport=self.f.transport)
        self.directory = next((self.f.root / "calls").iterdir())
        self.second_directory = next((self.f.root / "calls-b").iterdir())
        helper = recorder_fixture.ContinuousDiscoveryBatchTests()
        parents = [helper.archived_parent(label) for label in ("negative-a", "negative-b")]
        for item, source in zip(parents, [consumer_fixture.PARENT, consumer_fixture.OTHER]):
            item["candidate_sha256"] = source
        self.batch = ContinuousDiscoveryBatch(self.f.root / "native-batch", allow_temporary=True,
                                             test_clock=lambda: NOW, allow_test_clock=True)
        self.batch.initialize(batch_id=authority["batch_id"], start_utc=authority["start_utc"],
            deadline_utc=authority["deadline_utc"], max_attempts=6,
            initial_incumbent={"candidate_id": "market", "candidate_sha256": consumer_fixture.INCUMBENT,
                "scorecard_sha256": "a" * 64, "review_sha256": "b" * 64},
            active_pool_capacity=2, initial_archived_parents=parents,
            scheduling_policy="final-singleton-v1")
        self.batch.record_micro_evolution("initialize", micro_fixture.config(),
            expected_state_sha256=self.batch.snapshot()["state_sha256"])
        members = [helper.pool_member("a", parent=consumer_fixture.PARENT),
                   helper.pool_member("b", parent=consumer_fixture.OTHER,
                                      allocation="exploration", method_family="other")]
        members[0].update(candidate_id=self.decision["candidate_id"],
                          controller_decision_sha256=c._digest(self.decision))
        members[1].update(candidate_id=self.second_decision["candidate_id"],
                          controller_decision_sha256=c._digest(self.second_decision))
        self.batch.select_controller_pool(members)
        self.runner = "research/market_rsi/experiments/nfl_ingame_unlisted_branch.py"
        path = self.f.repo / self.runner; path.write_text("# synthetic sibling\n")
        self.request = {"attempt_id": "a", "candidate_id": self.decision["candidate_id"],
            "module": "experiments.nfl_ingame_unlisted_branch", "source_commit": "fixture-commit",
            "files": {self.runner: w.sha(path)}, "python": str(self.f.python),
            "python_sha256": w.sha(self.f.python), "memory": self.f.bindings["memory"]["path"],
            "memory_sha256": self.f.bindings["memory"]["sha256"],
            "runtime_pair_sha256": micro_pair_hash(self.batch.snapshot()["micro_evolution"]),
            "spec_sha256": "e" * 64, "max_fits": 4, "max_wall_seconds": 10}
        self.write_request(self.request)
        self.authority_binding = self.f.bindings["authority"]
        self.git = patch.object(w.subprocess, "check_output", return_value="fixture-commit\n")
        self.git.start(); self.addCleanup(self.git.stop)

    def write_request(self, request):
        self.request_path = self.f.root / "new-request.json"
        self.request_path.write_text(json.dumps(request))
        self.request_binding = {"path": str(self.request_path), "sha256": w.sha(self.request_path)}
        self.review = {"schema": "reviewed_candidate_request_v1", "passed": True,
            "batch_id": "synthetic-dispatch", "decision_sha256": c._digest(self.decision),
            "request_sha256": self.request_binding["sha256"],
            "authority_sha256": self.f.bindings["authority"]["sha256"],
            "research_parent_sha256": self.decision["actual_parent_sha256"],
            "comparison_incumbent_sha256": self.decision["comparison_incumbent_sha256"]}
        self.write_review(self.review)

    def write_review(self, review):
        path = self.f.root / "new-review.json"; path.write_text(json.dumps(review))
        self.review_binding = {"path": str(path), "sha256": w.sha(path)}

    def invoke(self, **kw):
        arguments = {"now": NOW}; arguments.update(kw)
        return d.dispatch(self.batch, self.request_binding, self.review_binding,
            self.directory, self.authority_binding, self.f.repo, **arguments)

    def completed_child(self, *args, **kwargs):
        output = Path(args[0][args[0].index("--output") + 1]); output.mkdir()
        manifest = {"complete": True, "model_fits": 4}
        for name in ("pre_score_lock", "input_receipts", "exclusions", "predictions", "scorecard"):
            path = output / (name + (".csv" if name == "predictions" else ".json"))
            path.write_text("{}")
            manifest[name + "_sha256"] = w.sha(path)
        (output / "manifest.json").write_text(json.dumps(manifest))
        return Mock(pid=1234, wait=Mock(return_value=0), poll=Mock(return_value=0))

    def test_original_negative_parent_generic_sibling_native_success(self):
        with patch.object(w.subprocess, "Popen", side_effect=self.completed_child) as launch:
            receipt = self.invoke()
        self.assertEqual(receipt["outcome"], "succeeded"); launch.assert_called_once()
        branch = self.batch.snapshot()["branches"][0]
        self.assertEqual(branch["stage"], "execution_terminal")
        self.assertEqual(branch["research_parent_sha256"], consumer_fixture.PARENT)
        self.assertEqual(branch["comparison_incumbent_sha256"], consumer_fixture.INCUMBENT)
        self.assertEqual(self.batch.snapshot()["incumbent"]["candidate_sha256"], consumer_fixture.INCUMBENT)
        self.assertEqual(launch.call_args.args[0][3], self.request["module"])

    def test_native_nonzero_failure_with_error_none_is_retained_and_recovered(self):
        with patch.object(w.subprocess, "Popen", return_value=Mock(
                pid=1234, wait=Mock(return_value=7), poll=Mock(return_value=7))) as launch:
            first = self.invoke(); second = self.invoke(now=c.DEADLINE)
        self.assertEqual(first, second); self.assertEqual(first["outcome"], "failed")
        self.assertIsNone(first["error"]); launch.assert_called_once()
        self.assertTrue((self.batch.root / "worker/a.stderr").is_file())

    def test_restart_reconciles_complete_receipt_without_authority_head_or_spawn(self):
        original = self.batch.mark_execution_terminal
        with patch.object(w.subprocess, "Popen", side_effect=self.completed_child) as launch:
            with patch.object(self.batch, "mark_execution_terminal", side_effect=RuntimeError("interrupted terminal")):
                with self.assertRaisesRegex(RuntimeError, "interrupted terminal"): self.invoke()
            launch.assert_called_once()
        self.f.write("authority", {"closed": True})
        self.git.stop()
        self.batch = ContinuousDiscoveryBatch(self.batch.root, allow_temporary=True,
            test_clock=lambda: datetime(2026, 10, 6, tzinfo=timezone.utc), allow_test_clock=True)
        with patch.object(w.subprocess, "Popen") as launch, patch.object(w.subprocess, "check_output", side_effect=AssertionError("no HEAD")):
            receipt = self.invoke(now=c.DEADLINE)
            launch.assert_not_called()
        self.assertEqual(receipt["outcome"], "succeeded")
        self.assertEqual(self.batch.snapshot()["branches"][0]["stage"], "execution_terminal")

    def test_concurrent_same_id_spawns_once(self):
        results, errors = [], []
        def invoke():
            try: results.append(self.invoke())
            except Exception as error: errors.append(error)
        with patch.object(w.subprocess, "Popen", side_effect=self.completed_child) as launch:
            threads = [threading.Thread(target=invoke) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
        self.assertEqual(errors, []); self.assertEqual(len(results), 2)
        self.assertEqual(results[0], results[1]); launch.assert_called_once()

    def test_interrupted_uncertain_claim_never_retries(self):
        with patch.object(w.subprocess, "Popen", side_effect=KeyboardInterrupt("unknown")) as launch:
            with self.assertRaises(KeyboardInterrupt): self.invoke()
            with self.assertRaisesRegex(RuntimeError, "incomplete original claim"): self.invoke()
            launch.assert_called_once()
        self.assertEqual(self.batch.snapshot()["branches"][0]["stage"], "execution_claimed")

    def test_exact_review_lineage_candidate_and_binding_denied_before_spawn(self):
        for change in ({"passed": False}, {"passed": 1}, {"schema": "other"},
                       {"research_parent_sha256": "f" * 64}, {"decision_sha256": "f" * 64},
                       {"authority_sha256": "f" * 64}, {"request_sha256": "f" * 64},
                       {"comparison_incumbent_sha256": "f" * 64}, {"extra": True}):
            self.write_review({**self.review, **change})
            with patch.object(w.subprocess, "Popen") as launch:
                with self.assertRaises(ValueError): self.invoke()
                launch.assert_not_called()
        self.write_review(self.review)
        self.write_request({**self.request, "candidate_id": "different"})
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaises(ValueError): self.invoke()
            launch.assert_not_called()

    def test_source_runtime_memory_and_module_denied_before_spawn(self):
        original = deepcopy(self.request)
        for change in ({"source_commit": "stale"}, {"python_sha256": "f" * 64},
                       {"memory_sha256": "f" * 64}, {"module": "os"},
                       {"max_fits": 5}, {"max_wall_seconds": 901}):
            self.write_request({**original, **change})
            with patch.object(w.subprocess, "Popen") as launch:
                with self.assertRaises(ValueError): self.invoke()
                launch.assert_not_called()
        self.assertEqual(self.batch.snapshot()["attempts_claimed"], 0)

    def test_expired_budget_and_self_grant_denied_before_spawn(self):
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "selection stop"): self.invoke(now=c.CUTOFF)
            with self.assertRaisesRegex(ValueError, "binding drift"):
                self.invoke(prospective_binding={"attempts": 999})
            launch.assert_not_called()

    def test_success_artifact_drift_and_receipt_drift_reject_without_retry(self):
        with patch.object(w.subprocess, "Popen", side_effect=self.completed_child): self.invoke()
        (self.batch.root / "runs/a/predictions.csv").write_text("changed")
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "hash/path drift"): self.invoke()
            launch.assert_not_called()

    def test_dispatch_binding_drift_rejects_without_retry(self):
        with patch.object(w.subprocess, "Popen", side_effect=self.completed_child): self.invoke()
        path = self.batch.root / "dispatch/a.json"; value = json.loads(path.read_text())
        value["sources"]["dispatcher"] = "f" * 64; path.write_text(json.dumps(value))
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "dispatch/source binding drift"): self.invoke()
            launch.assert_not_called()

    def test_original_claim_and_schema_denied_before_worker_spawn(self):
        claim_path = self.directory / "claim.json"
        original = json.loads(claim_path.read_text())
        for change in ({"input_sha256": "f" * 64}, {"schema_sha256": "f" * 64},
                       {"consumer_source_sha256": "f" * 64}, {"extra": True}):
            claim_path.write_text(json.dumps({**original, **change}))
            with patch.object(w.subprocess, "Popen") as launch:
                with self.assertRaisesRegex(ValueError, "claim/schema drift"): self.invoke()
                launch.assert_not_called()
        claim_path.write_text(json.dumps(original))
        (self.directory / "schema.json").write_text("{}")
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "claim/schema drift"): self.invoke()
            launch.assert_not_called()

    def test_original_tool_failure_and_closed_authority_decision_never_dispatch(self):
        response = deepcopy(self.decision); response["action"] = "request_closed_authority"
        (self.directory / "response.json").write_text(json.dumps(response))
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaises(ValueError): self.invoke()
            launch.assert_not_called()

    def test_outer_batch_fit_attempt_concurrency_and_permission_stop(self):
        original = deepcopy(self.f.values["authority"])
        cases = [dict(original, batch_id="other"),
                 dict(original, external_fetch=True),
                 dict(original, attempts=[{"attempt_id": "a", "fits_reserved": 4,
                                         "actual_fits": 0, "status": "claimed"}]),
                 dict(original, attempts=[{"attempt_id": str(index), "fits_reserved": 4,
                                         "actual_fits": 0, "status": "closed"} for index in range(6)]),
                 dict(original, attempts=[{"attempt_id": str(index), "fits_reserved": 4,
                                         "actual_fits": 0, "status": "claimed"} for index in range(2)])]
        for authority in cases:
            self.f.write("authority", authority); self.authority_binding = self.f.bindings["authority"]
            self.write_request(self.request)
            with patch.object(w.subprocess, "Popen") as launch:
                with self.assertRaises(ValueError): self.invoke()
                launch.assert_not_called()
        self.assertEqual(self.batch.snapshot()["attempts_claimed"], 0)

    def test_runtime_source_and_dispatch_symlinks_fail_before_spawn(self):
        original = deepcopy(self.request)
        link = self.f.root / "python-link"; link.symlink_to(self.f.python)
        self.write_request({**original, "python": str(link)})
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "path drift"): self.invoke()
            launch.assert_not_called()
        self.write_request(original)
        outside = self.f.root / "outside-dispatch"; outside.mkdir()
        (self.batch.root / "dispatch").mkdir(exist_ok=True)
        (self.batch.root / "dispatch/a.lock").unlink()
        (self.batch.root / "dispatch/a.lock").symlink_to(outside / "lock")
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaises(OSError): self.invoke()
            launch.assert_not_called()
        self.assertFalse((outside / "lock").exists())

    def test_receipt_and_log_drift_fail_closed_on_restart(self):
        with patch.object(w.subprocess, "Popen", side_effect=self.completed_child): self.invoke()
        path = self.batch.root / "worker/a.receipt.json"; original = json.loads(path.read_text())
        for changes in ({"source_commit": "other"}, {"attempt_id": "other"},
                        {"outcome": "failed", "exit_code": 0, "error": None},
                        {"metrics_independently_reviewed": True}, {"extra": True}):
            path.write_text(json.dumps({**original, **changes}))
            with patch.object(w.subprocess, "Popen") as launch:
                with self.assertRaises(ValueError): self.invoke()
                launch.assert_not_called()
        path.write_text(json.dumps(original))
        (self.batch.root / "worker/a.stderr").write_text("changed")
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "hash/path drift"): self.invoke()
            launch.assert_not_called()

    def test_completed_native_failure_requires_original_process_evidence(self):
        with patch.object(w.subprocess, "Popen", return_value=Mock(
                pid=1234, wait=Mock(return_value=7), poll=Mock(return_value=7))): self.invoke()
        (self.batch.root / "worker/a.process.json").unlink()
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "process evidence missing"): self.invoke()
            launch.assert_not_called()

    def test_stale_snapshot_local_attempt_fit_and_live_reservations_stop_fresh_dispatch(self):
        directory = self.batch.root / "dispatch"; directory.mkdir()
        # Synthetic historical admission records are reserved, not scored.
        for index in range(5): (directory / f"old-{index}.json").write_text("{}")
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "stale outer snapshot"): self.invoke()
            launch.assert_not_called()
        for index in range(5): (directory / f"old-{index}.json").unlink()
        # Even zero native claims cannot erase two already-admitted reservations.
        (directory / "b.json").write_text("{}")
        authority = deepcopy(self.f.values["authority"])
        authority["attempts"][0]["status"] = "claimed"
        self.f.write("authority", authority); self.authority_binding = self.f.bindings["authority"]
        self.write_request(self.request)
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "stale outer snapshot"): self.invoke()
            launch.assert_not_called()

    def select_second(self):
        self.decision, self.directory = self.second_decision, self.second_directory
        self.write_request({**self.request, "attempt_id": "b", "candidate_id": self.decision["candidate_id"]})

    def test_two_distinct_ids_execute_parallel_under_native_two_slot_guard(self):
        entered, release = threading.Event(), threading.Event()
        results, errors = [], []
        def child(*args, **kwargs):
            if args[0][-1].endswith("/a"):
                entered.set(); self.assertTrue(release.wait(5))
            return self.completed_child(*args, **kwargs)
        def first():
            try: results.append(self.invoke())
            except BaseException as error: errors.append(error)
        with patch.object(w.subprocess, "Popen", side_effect=child) as launch:
            thread = threading.Thread(target=first); thread.start()
            self.assertTrue(entered.wait(5))
            self.assertEqual(self.batch.snapshot()["branches"][0]["stage"], "execution_claimed")
            self.select_second()
            try: results.append(self.invoke())
            finally: release.set(); thread.join(5)
        self.assertEqual(errors, []); self.assertEqual(len(results), 2)
        self.assertEqual(launch.call_count, 2)
        self.assertTrue(all(item["outcome"] == "succeeded" for item in results))

    def test_actual_first_dispatch_consumes_stale_snapshot_before_second_spawn(self):
        authority = deepcopy(self.f.values["authority"])
        authority["attempts"] = [{"attempt_id": "prior-" + str(index), "fits_reserved": 4,
                                  "actual_fits": 4, "status": "closed"} for index in range(5)]
        self.f.write("authority", authority); self.authority_binding = self.f.bindings["authority"]
        self.write_request(self.request)
        with patch.object(w.subprocess, "Popen", side_effect=self.completed_child) as launch:
            self.invoke(); self.select_second()
            with self.assertRaisesRegex(ValueError, "stale outer snapshot"): self.invoke()
            launch.assert_called_once()
        self.assertEqual(self.batch.snapshot()["attempts_claimed"], 1)

    def test_unrecorded_native_claim_consumes_stale_outer_fit_allowance(self):
        authority = deepcopy(self.f.values["authority"])
        authority["attempts"] = [{"attempt_id": "prior-" + str(index), "fits_reserved": 4,
                                  "actual_fits": 4, "status": "closed"} for index in range(5)]
        self.f.write("authority", authority); self.authority_binding = self.f.bindings["authority"]
        self.write_request(self.request)
        self.batch.mark_implementation_ready("b", runner_sha256=self.request["files"][self.runner], spec_sha256="e" * 64)
        self.batch.claim_execution("b", claim_id="b-claim", runtime_pair_sha256=self.request["runtime_pair_sha256"],
                                   memory_snapshot_sha256=self.request["memory_sha256"])
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "stale outer snapshot"): self.invoke()
            launch.assert_not_called()

    def test_native_receipt_scalar_type_drift_is_not_accepted(self):
        with patch.object(w.subprocess, "Popen", side_effect=self.completed_child): self.invoke()
        path = self.batch.root / "worker/a.receipt.json"; original = json.loads(path.read_text())
        for change in ({"exit_code": False}, {"exit_code": 0.0}, {"sampled_peak_rss_kib": 128.0}):
            path.write_text(json.dumps({**original, **change}))
            with patch.object(w.subprocess, "Popen") as launch:
                with self.assertRaises(ValueError): self.invoke()
                launch.assert_not_called()
        path.write_text(json.dumps(original))
        manifest_path = self.batch.root / "runs/a/manifest.json"; manifest = json.loads(manifest_path.read_text())
        manifest_path.write_text(json.dumps({**manifest, "model_fits": 4.0}))
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "fit manifest"): self.invoke()
            launch.assert_not_called()
    def test_native_pre_spawn_failure_retains_receipt_without_fabricated_process(self):
        with patch.object(w.subprocess, "Popen", side_effect=OSError("synthetic process unavailable")) as launch:
            first = self.invoke(); second = self.invoke()
            launch.assert_called_once()
        self.assertEqual(first, second); self.assertEqual(first["outcome"], "failed")
        self.assertIsNone(first["exit_code"])
        self.assertIn("synthetic process unavailable", first["error"])
        self.assertFalse((self.batch.root / "worker/a.process.json").exists())
        self.assertFalse((self.batch.root / "runs/a/predictions.csv").exists())

    def test_original_request_source_hash_drift_denies_before_spawn(self):
        (self.f.repo / self.runner).write_text("# drifted source")
        with patch.object(w.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "source file drift"): self.invoke()
            launch.assert_not_called()


if __name__ == "__main__": unittest.main()
