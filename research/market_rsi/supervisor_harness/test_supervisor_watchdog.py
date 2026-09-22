from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import patch

from supervisor_harness import formal_train_admission as admission
from supervisor_harness.supervisor_watchdog import SupervisorWatchdog


SHA = "a" * 64
TRAIN_BYTES = b'{"schema":"watchdog_train_bundle_v1","rows":[1]}\n'
TRAIN_SHA = hashlib.sha256(TRAIN_BYTES).hexdigest()
QUESTION_ID = "2025_whole_season_trade_access"
SEASONS = ("2023", "2024", "2025")
CONTROLLER_TASK_SHA = "7" * 64


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
        with self.assertRaisesRegex(ValueError, "exact validated"):
            self.watchdog.claim_task(
                task_id="training-digest-only", task_kind="training", stage="run",
                owner="runner", heartbeat_timeout_seconds=10,
                progress_timeout_seconds=30, input_sha256=SHA,
                data_admission_sha256="8" * 64, now=self.clock)

        artifact_root = Path(self.tmp.name).resolve()
        dataset_path = artifact_root / "train-bundle.json"
        dataset_path.write_bytes(TRAIN_BYTES)
        receipt = {
            "schema": admission.SCHEMA,
            "receipt_id": "watchdog-formal-train-test-v1",
            "issuer_id": admission.INDEPENDENT_ISSUER_ID,
            "issued_utc": "2026-09-22T12:00:00Z",
            "dataset": {
                "dataset_id": "watchdog-synthetic-train-v1",
                "dataset_sha256": TRAIN_SHA,
                "row_manifest_sha256": "2" * 64,
                "source_version_sha256": "3" * 64,
                "split_scope": admission.TRAIN_SCOPE,
                "row_count": 1,
                "season_ids": list(SEASONS),
                "question_id": QUESTION_ID,
                "controller_task_sha256": CONTROLLER_TASK_SHA,
            },
            "gates": {
                name: {"status": "passed", "evidence_sha256": digit * 64}
                for name, digit in zip(admission.REQUIRED_GATES, ("4", "5", "6"))
            },
            "claim_boundaries": {
                "formal_train_admitted": True,
                "dev_data_read": False,
                "final_data_read": False,
                "unknowns_remaining": False,
            },
        }
        receipt_path = artifact_root / "formal-train-admission.json"
        receipt_raw = admission._canonical(receipt)
        receipt_path.write_bytes(receipt_raw)
        receipt_sha = hashlib.sha256(receipt_raw).hexdigest()
        registry = MappingProxyType({receipt["receipt_id"]: {
            "receipt_file_sha256": receipt_sha,
            "receipt_schema": admission.SCHEMA,
            "issuer_id": admission.INDEPENDENT_ISSUER_ID,
            "dataset_id": receipt["dataset"]["dataset_id"],
            "dataset_sha256": TRAIN_SHA,
            "season_ids": list(SEASONS),
            "question_id": QUESTION_ID,
            "controller_task_sha256": CONTROLLER_TASK_SHA,
        }})
        with patch.object(admission, "TRUSTED_RECEIPT_COMMITMENTS", registry):
            state = self.watchdog.claim_task(
                task_id="training-accepted", task_kind="training", stage="run",
                owner="runner", heartbeat_timeout_seconds=10,
                progress_timeout_seconds=30, input_sha256=SHA,
                data_admission_sha256=receipt_sha,
                data_admission_receipt_path=receipt_path,
                data_admission_dataset_path=dataset_path,
                data_admission_question_id=QUESTION_ID,
                data_admission_season_ids=SEASONS,
                data_admission_controller_task_sha256=CONTROLLER_TASK_SHA,
                now=self.clock)
        task = state["active_task"]
        self.assertEqual(task["data_admission_sha256"], receipt_sha)
        self.assertEqual(task["dataset_sha256"], TRAIN_SHA)
        self.assertEqual(task["dataset_path"], str(dataset_path))
        self.assertEqual(task["data_admission_question_id"], QUESTION_ID)
        self.assertEqual(task["data_admission_season_ids"], list(SEASONS))
        self.assertEqual(
            task["data_admission_controller_task_sha256"], CONTROLLER_TASK_SHA)

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
