"""Synthetic matched success/failure/timeout/restart, never real Train fits."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
from supervisor_harness.test_continuous_discovery_batch import ContinuousDiscoveryBatchTests
from supervisor_harness import opened_train_discovery_worker as worker
from data_scientist_harness import test_micro_evolution as fixture
from data_scientist_harness.co_evolution_loop import micro_pair_hash


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name).resolve()
        self.batch = ContinuousDiscoveryBatch(self.repo / "batch", allow_temporary=True)
        now = datetime.now(timezone.utc)
        self.batch.initialize(batch_id="test-binding", start_utc=now,
            deadline_utc=now + timedelta(hours=1), max_attempts=3,
            initial_incumbent={"candidate_id":"raw-market", "candidate_sha256":"a"*64,
                "scorecard_sha256":"b"*64, "review_sha256":"c"*64},
            active_pool_capacity=2, scheduling_policy="final-singleton-v1")
        self.batch.record_micro_evolution("initialize", fixture.config(),
            expected_state_sha256=self.batch.snapshot()["state_sha256"])
        helper = ContinuousDiscoveryBatchTests()
        members = [helper.pool_member("a"), helper.pool_member("b", allocation="exploration", method_family="other")]
        for item in members: item["research_parent_sha256"] = "a"*64
        members[0]["candidate_id"] = "freshness"
        self.batch.select_controller_pool(members)
        self.runner = "research/market_rsi/experiments/nfl_ingame_test.py"
        path = self.repo / self.runner; path.parent.mkdir(parents=True); path.write_text("# fixture\n")
        memory = self.repo / "memory.json"; memory.write_text("{}")
        self.request = {"attempt_id":"a", "candidate_id":"freshness",
            "module":"experiments.nfl_ingame_test", "source_commit":"test-commit",
            "files":{self.runner:worker.sha(path)}, "python":sys.executable,
            "python_sha256":worker.sha(sys.executable), "memory":str(memory),
            "memory_sha256":worker.sha(memory), "runtime_pair_sha256":micro_pair_hash(
                self.batch.snapshot()["micro_evolution"]), "spec_sha256":"e"*64,
            "max_fits":4, "max_wall_seconds":10}
        self.git = patch.object(worker.subprocess, "check_output", return_value="test-commit\n")
        self.git.start(); self.addCleanup(self.git.stop)
        self.rss = patch.object(worker, "sample_rss", return_value=128)
        self.rss.start(); self.addCleanup(self.rss.stop)

    def completed_child(self, *args, **kwargs):
        output = self.batch.root / "runs/a"; output.mkdir()
        manifest = {"complete":True, "model_fits":4}
        for name in ("pre_score_lock", "input_receipts", "exclusions", "predictions", "scorecard"):
            path = output / (name + (".csv" if name == "predictions" else ".json"))
            path.write_text("{}")
            manifest[name + "_sha256"] = worker.sha(path)
        (output / "manifest.json").write_text(json.dumps(manifest))
        return Mock(pid=1234, wait=Mock(return_value=0), poll=Mock(return_value=0))

    def test_success_bound_terminal_and_history_restart(self):
        with patch.object(worker.subprocess, "Popen", side_effect=self.completed_child) as launch:
            receipt = worker.execute(self.batch, self.request, self.repo)
            self.assertEqual(receipt["outcome"], "succeeded")
            self.assertEqual(launch.call_args.kwargs["env"]["OPENBLAS_NUM_THREADS"], "1")
            self.assertNotIn("HOME", launch.call_args.kwargs["env"])
        state = self.batch.snapshot()
        self.assertEqual(state["attempts_claimed"], 1)
        self.assertEqual(state["branches"][0]["stage"], "execution_terminal")
        restarted = ContinuousDiscoveryBatch(self.batch.root, allow_temporary=True)
        self.assertEqual(restarted.snapshot(), state)
        with patch.object(worker.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(RuntimeError, "already claimed"):
                worker.execute(restarted, self.request, self.repo)
            launch.assert_not_called()

    def test_failure_is_terminal_and_retains_logs(self):
        with patch.object(worker.subprocess, "Popen", return_value=Mock(
                pid=1234, wait=Mock(return_value=7), poll=Mock(return_value=7))):
            receipt = worker.execute(self.batch, self.request, self.repo)
        self.assertEqual(receipt["outcome"], "failed")
        self.assertEqual(receipt["exit_code"], 7)
        self.assertTrue((self.batch.root / "worker/a.stderr").is_file())
        self.assertEqual(self.batch.snapshot()["branches"][0]["execution_outcome"], "failed")

    def test_timeout_kills_group_before_terminal(self):
        child = Mock(pid=1234, wait=Mock(side_effect=[worker.subprocess.TimeoutExpired("x", 10), -9]))
        with patch.object(worker.subprocess, "Popen", return_value=child), patch.object(worker.os, "killpg") as kill, patch.object(worker.time, "monotonic", side_effect=[0,0,0,11,11]):
            receipt = worker.execute(self.batch, self.request, self.repo)
        kill.assert_called_once_with(1234, 9)
        self.assertEqual(receipt["error"], "bounded timeout")

    def test_sampled_rss_ceiling_stops_child(self):
        child = Mock(pid=1234, wait=Mock(return_value=-9))
        with patch.object(worker.subprocess, "Popen", return_value=child), patch.object(worker.os, "killpg") as kill, patch.object(worker, "sample_rss", return_value=1048577):
            receipt = worker.execute(self.batch, self.request, self.repo)
        kill.assert_called_once_with(1234, 9)
        self.assertEqual(receipt["error"], "sampled RSS ceiling")

    def test_crashed_claim_cannot_relaunch(self):
        self.batch.mark_implementation_ready("a", runner_sha256=self.request["files"][self.runner], spec_sha256="e"*64)
        self.batch.claim_execution("a", claim_id="a-claim", runtime_pair_sha256=self.request["runtime_pair_sha256"],
                                   memory_snapshot_sha256=self.request["memory_sha256"])
        with patch.object(worker.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(RuntimeError, "already claimed"):
                worker.execute(self.batch, self.request, self.repo)
            launch.assert_not_called()

    def test_source_and_memory_drift_fail_before_claim(self):
        for field in ("memory_sha256", "python_sha256"):
            request = {**self.request, field:"f"*64}
            with self.assertRaises(ValueError): worker.execute(self.batch, request, self.repo)
        (self.repo / self.runner).write_text("# modified")
        with self.assertRaises(ValueError): worker.execute(self.batch, self.request, self.repo)
        self.assertEqual(self.batch.snapshot()["attempts_claimed"], 0)

    def test_request_boundaries(self):
        for changes in ({"module":"os"}, {"max_fits":5}, {"max_wall_seconds":901},
                        {"attempt_id":"../a"}, {"source_commit":"stale"}, {"extra":1}):
            with self.assertRaises(ValueError): worker.validate({**self.request, **changes}, self.repo)

    def test_aggregate_fit_reservation_fails_before_spawn(self):
        folder = self.batch.root / "worker"; folder.mkdir()
        for number in range(3): worker.save(folder / f"old{number}.request.json", {"max_fits":4})
        with patch.object(worker.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(RuntimeError, "twelve-fit"):
                worker.execute(self.batch, self.request, self.repo)
            launch.assert_not_called()

    def test_corrupt_artifact_is_failure_not_success(self):
        def launch(*args, **kwargs):
            child = self.completed_child()
            (self.batch.root / "runs/a/scorecard.json").write_text("tampered")
            return child
        with patch.object(worker.subprocess, "Popen", side_effect=launch):
            receipt = worker.execute(self.batch, self.request, self.repo)
        self.assertEqual(receipt["outcome"], "failed")
        self.assertIn("artifact hash drift", receipt["error"])


if __name__ == "__main__": unittest.main()
