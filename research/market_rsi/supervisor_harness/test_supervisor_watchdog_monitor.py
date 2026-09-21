from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from supervisor_harness.supervisor_watchdog import SupervisorWatchdog
from supervisor_harness.supervisor_watchdog_monitor import (
    CLEANUP_SCHEMA, monitor_once,
)


class FakeControl:
    def __init__(self, *, cleanup=True, mismatch=False):
        self.cleanup = cleanup
        self.mismatch = mismatch
        self.stop_calls = 0

    def evidence(self, task, log_sha):
        process = task["process_identity"]
        container = task["container_identity"]
        return {
            "process": {"checked": True,
                        "pid": 9999 if self.mismatch else process["pid"],
                        "command_sha256": process["command_sha256"],
                        "present": True},
            "container": {"checked": True, "name": container["name"],
                          "label": container["label"], "present": True},
            "data": {"gate_status": "not_applicable",
                     "evidence_sha256": None},
            "budget": {"checked": True, "task_id": task["task_id"],
                       "state": "none", "snapshot_sha256": "9" * 64},
            "log_tail_sha256": log_sha,
        }

    def stop_exact(self, task):
        self.stop_calls += 1
        return {"schema": CLEANUP_SCHEMA, "task_id": task["task_id"],
                "process_identity_matched": True,
                "process_absent": self.cleanup,
                "container_identity_matched": True,
                "container_absent": self.cleanup,
                "cleanup_verified": self.cleanup}


class WatchdogMonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.watchdog = SupervisorWatchdog(root / "watchdog")
        self.start = datetime(2026, 9, 20, 2, 0, tzinfo=timezone.utc)
        self.watchdog.initialize(now=self.start)
        self.watchdog.claim_task(
            task_id="monitor-task-001", task_kind="infrastructure",
            stage="blocked_child", owner="outer_runner",
            heartbeat_timeout_seconds=10, progress_timeout_seconds=30,
            input_sha256="1" * 64,
            process_identity={"pid": 1234, "command_sha256": "2" * 64},
            container_identity={"name": "market-rsi-b-monitor-001",
                                "label": "monitor-task-001"},
            now=self.start)
        self.log = root / "worker.log"
        self.log.write_text("worker started\n")
        self.output = root / "monitor-result"

    def tearDown(self):
        self.tmp.cleanup()

    def test_healthy_task_does_not_cleanup(self):
        control = FakeControl()
        result = monitor_once(
            watchdog=self.watchdog, control=control, log_path=self.log,
            output=self.output, now=self.start + timedelta(seconds=5))
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(control.stop_calls, 0)

    def test_stalled_task_is_frozen_cleaned_and_dispatched(self):
        control = FakeControl()
        result = monitor_once(
            watchdog=self.watchdog, control=control, log_path=self.log,
            output=self.output, now=self.start + timedelta(seconds=11))
        self.assertEqual(result["classification"], "worker_heartbeat_timeout")
        self.assertTrue(result["cleanup_verified"])
        self.assertEqual(control.stop_calls, 1)
        repair = (self.output / "controller-repair-input.json").read_text()
        self.assertIn('"same_id_retry": false', repair)
        self.assertNotIn("1234", repair)

    def test_cleanup_failure_is_visible_and_never_retried(self):
        result = monitor_once(
            watchdog=self.watchdog, control=FakeControl(cleanup=False),
            log_path=self.log, output=self.output,
            now=self.start + timedelta(seconds=11))
        self.assertEqual(result["status"], "repair_pending_cleanup_failed")
        self.assertFalse(result["automatic_retry"])

    def test_identity_mismatch_fails_before_cleanup(self):
        control = FakeControl(mismatch=True)
        with self.assertRaises(ValueError):
            monitor_once(watchdog=self.watchdog, control=control,
                         log_path=self.log, output=self.output,
                         now=self.start + timedelta(seconds=11))
        self.assertEqual(control.stop_calls, 0)
        self.assertFalse(self.output.exists())

    def test_restart_does_not_repeat_cleanup(self):
        control = FakeControl()
        monitor_once(watchdog=self.watchdog, control=control,
                     log_path=self.log, output=self.output,
                     now=self.start + timedelta(seconds=11))
        with self.assertRaises(ValueError):
            monitor_once(watchdog=SupervisorWatchdog(self.watchdog.root),
                         control=control, log_path=self.log,
                         output=self.output.parent / "again",
                         now=self.start + timedelta(seconds=12))
        self.assertEqual(control.stop_calls, 1)


if __name__ == "__main__":
    unittest.main()
