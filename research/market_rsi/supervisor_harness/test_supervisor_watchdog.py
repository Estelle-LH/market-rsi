from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from supervisor_harness.supervisor_watchdog import SupervisorWatchdog


SHA = "a" * 64


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "watchdog"
        self.clock = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
        self.watchdog = SupervisorWatchdog(self.root)
        self.watchdog.initialize(now=self.clock)

    def tearDown(self):
        self.tmp.cleanup()

    def claim(self, kind="infrastructure"):
        self.watchdog.claim_task(
            task_id="task-001", task_kind=kind, stage="source_check",
            owner="researcher", heartbeat_timeout_seconds=10,
            progress_timeout_seconds=30, input_sha256=SHA,
            process_identity={"pid": 1234, "command_sha256": "b" * 64},
            container_identity={"name": "market-rsi-b-task-001", "label": "task-001"},
            now=self.clock)

    def evidence(self):
        return {"process": {"checked": True, "pid": 1234,
                             "command_sha256": "b" * 64, "present": True},
                "container": {"checked": True, "name": "market-rsi-b-task-001",
                              "label": "task-001", "present": True},
                "data": {"gate_status": "not_applicable", "evidence_sha256": None},
                "budget": {"checked": True, "task_id": "task-001",
                           "state": "none", "snapshot_sha256": "9" * 64},
                "log_tail_sha256": "c" * 64}

    def test_healthy_task_does_not_create_incident(self):
        self.claim()
        self.watchdog.heartbeat("task-001", material_progress=True,
                                progress_sha256="d" * 64,
                                now=self.clock + timedelta(seconds=5))
        self.assertIsNone(self.watchdog.tick(
            now=self.clock + timedelta(seconds=9), evidence=self.evidence()))
        self.assertFalse((self.root / "incidents").exists())

    def test_alive_but_no_material_progress_stalls(self):
        self.claim()
        for seconds in (5, 10, 15, 20, 25, 30):
            self.watchdog.heartbeat("task-001", material_progress=False,
                                    now=self.clock + timedelta(seconds=seconds))
        packet = self.watchdog.tick(now=self.clock + timedelta(seconds=31),
                                    evidence=self.evidence())
        self.assertEqual(packet["classification"], "no_material_progress")
        self.assertFalse(packet["automatic_retry"])
        self.assertFalse(packet["downstream_training_allowed"])

    def test_missing_heartbeat_stalls_and_restart_preserves_incident(self):
        self.claim()
        packet = self.watchdog.tick(now=self.clock + timedelta(seconds=11),
                                    evidence=self.evidence())
        self.assertEqual(packet["classification"], "worker_heartbeat_timeout")
        restarted = SupervisorWatchdog(self.root)
        state = restarted.snapshot()
        self.assertEqual(state["active_task"]["status"], "repair_pending")
        self.assertEqual(len(state["incidents"]), 1)
        self.assertIsNone(restarted.tick(now=self.clock + timedelta(seconds=100),
                                        evidence=self.evidence()))

    def test_failed_data_gate_blocks_training_and_creates_repair_plan(self):
        self.claim(kind="data")
        self.watchdog.record_data_gate("task-001", passed=False,
                                       evidence_sha256="e" * 64,
                                       now=self.clock + timedelta(seconds=2))
        evidence = self.evidence()
        evidence["data"] = {"gate_status": "failed", "evidence_sha256": "e" * 64}
        packet = self.watchdog.tick(now=self.clock + timedelta(seconds=3),
                                    evidence=evidence)
        self.assertEqual(packet["classification"], "data_admission_failure")
        self.assertFalse(packet["downstream_training_allowed"])
        self.assertIn("Controller chooses one bounded data diagnosis",
                      packet["repair_plan"]["steps"][2]["action"])

    def test_repair_requires_canary_and_fresh_id(self):
        self.claim()
        packet = self.watchdog.tick(now=self.clock + timedelta(seconds=11),
                                    evidence=self.evidence())
        with self.assertRaises(ValueError):
            self.watchdog.close_after_verified_repair(
                "task-001", incident_id=packet["incident_id"],
                canary_sha256="f" * 64, fresh_resume_id="task-001",
                now=self.clock + timedelta(seconds=20))
        state = self.watchdog.close_after_verified_repair(
            "task-001", incident_id=packet["incident_id"],
            canary_sha256="f" * 64, fresh_resume_id="task-002",
            now=self.clock + timedelta(seconds=20))
        self.assertIsNone(state["active_task"])
        self.assertIn("task-001", state["claimed_task_ids"])
        self.assertNotIn("task-002", state["claimed_task_ids"])

    def test_malformed_journal_fails_closed(self):
        with self.watchdog.journal.open("a") as handle:
            handle.write(json.dumps({"bad": True}) + "\n")
        with self.assertRaises(ValueError):
            SupervisorWatchdog(self.root).snapshot()

    def test_only_one_active_task_and_never_reuse_id(self):
        self.claim()
        with self.assertRaises(ValueError):
            self.watchdog.claim_task(
                task_id="task-002", task_kind="data", stage="other",
                owner="researcher", heartbeat_timeout_seconds=10,
                progress_timeout_seconds=30, input_sha256=SHA, now=self.clock)

    def test_evidence_must_match_exact_process_and_container(self):
        self.claim()
        for field, value in (("pid", 9999), ("command_sha256", "0" * 64)):
            evidence = self.evidence()
            evidence["process"][field] = value
            with self.assertRaises(ValueError):
                self.watchdog.tick(now=self.clock + timedelta(seconds=11),
                                   evidence=evidence)
        evidence = self.evidence()
        evidence["container"]["name"] = "wrong-container"
        with self.assertRaises(ValueError):
            self.watchdog.tick(now=self.clock + timedelta(seconds=11),
                               evidence=evidence)

    def test_training_or_evaluation_requires_data_admission_receipt(self):
        for kind in ("training", "evaluation"):
            with self.assertRaises(ValueError):
                self.watchdog.claim_task(
                    task_id=f"{kind}-001", task_kind=kind, stage="run",
                    owner="runner", heartbeat_timeout_seconds=10,
                    progress_timeout_seconds=30, input_sha256=SHA,
                    now=self.clock)
        state = self.watchdog.claim_task(
            task_id="training-accepted", task_kind="training", stage="run",
            owner="runner", heartbeat_timeout_seconds=10,
            progress_timeout_seconds=30, input_sha256=SHA,
            data_admission_sha256="8" * 64, now=self.clock)
        self.assertEqual(state["active_task"]["data_admission_sha256"], "8" * 64)

    def test_data_task_cannot_close_until_gate_passes(self):
        self.claim(kind="data")
        with self.assertRaises(ValueError):
            self.watchdog.close_success("task-001", result_sha256="7" * 64,
                                        now=self.clock + timedelta(seconds=1))
        self.watchdog.record_data_gate("task-001", passed=True,
                                       evidence_sha256="6" * 64,
                                       now=self.clock + timedelta(seconds=2))
        state = self.watchdog.close_success("task-001", result_sha256="7" * 64,
                                            now=self.clock + timedelta(seconds=3))
        self.assertIsNone(state["active_task"])

    def test_immediate_worker_failure_creates_incident_without_retry(self):
        self.claim()
        packet = self.watchdog.report_failure(
            "task-001", classification="worker_error", evidence=self.evidence(),
            now=self.clock + timedelta(seconds=1))
        self.assertEqual(packet["classification"], "worker_error")
        self.assertFalse(packet["automatic_retry"])
        self.assertEqual(self.watchdog.snapshot()["active_task"]["status"],
                         "repair_pending")

    def test_unknown_failure_classification_is_rejected(self):
        self.claim()
        with self.assertRaises(ValueError):
            self.watchdog.report_failure(
                "task-001", classification="retry_for_score",
                evidence=self.evidence(), now=self.clock + timedelta(seconds=1))


if __name__ == "__main__":
    unittest.main()
