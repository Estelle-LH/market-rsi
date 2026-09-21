import hashlib
import json
import signal
from types import SimpleNamespace
import unittest

from supervisor_harness.supervisor_watchdog_local_control import (
    CLEANUP_SCHEMA, LocalProcessDockerControl, TASK_LABEL_KEY,
    container_identity, process_command_sha256, stable_process_command_sha256,
)


class FakeSystem:
    def __init__(self):
        self.command = "python worker.py --task task-001"
        self.pid_present = True
        self.container_present = True
        self.label = "task-001"
        self.signals = []

    def run(self, argv, **kwargs):
        if argv[0] == "ps":
            return SimpleNamespace(returncode=0 if self.pid_present else 1,
                                   stdout=self.command + "\n" if self.pid_present else "",
                                   stderr="")
        if argv[:2] == ["docker", "inspect"]:
            if not self.container_present:
                return SimpleNamespace(returncode=1, stdout="", stderr="missing")
            body = [{"Name": "/b-task-001",
                     "Config": {"Labels": {TASK_LABEL_KEY: self.label}}}]
            return SimpleNamespace(returncode=0, stdout=json.dumps(body), stderr="")
        if argv[:2] == ["docker", "stop"]:
            self.container_present = False
            return SimpleNamespace(returncode=0, stdout="b-task-001\n", stderr="")
        raise AssertionError(argv)

    def kill(self, pid, sig):
        if sig == 0:
            if not self.pid_present:
                raise ProcessLookupError
            return
        self.signals.append((pid, sig))
        self.pid_present = False


class LocalControlTests(unittest.TestCase):
    def setUp(self):
        self.system = FakeSystem()
        command_sha = hashlib.sha256(self.system.command.encode()).hexdigest()
        self.task = {"task_id": "task-001",
                     "process_identity": {"pid": 4321,
                                          "command_sha256": command_sha},
                     "container_identity": {"name": "b-task-001",
                                            "label": "task-001"}}
        self.control = LocalProcessDockerControl(
            budget_evidence=lambda task_id: {
                "checked": True, "task_id": task_id, "state": "reserved",
                "snapshot_sha256": "a" * 64},
            data_evidence=lambda task_id: {
                "gate_status": "unknown", "evidence_sha256": None},
            run=self.system.run, kill=self.system.kill,
            monotonic=lambda: 0.0, sleep=lambda _: None)

    def test_process_and_container_probe(self):
        command_sha, present = process_command_sha256(4321, run=self.system.run)
        self.assertTrue(present)
        self.assertEqual(command_sha, self.task["process_identity"]["command_sha256"])
        label, present = container_identity("b-task-001", run=self.system.run)
        self.assertTrue(present)
        self.assertEqual(label, "task-001")

    def test_stable_identity_requires_two_matching_observations(self):
        observed = stable_process_command_sha256(
            4321, run=self.system.run, monotonic=lambda: 0.0,
            sleep=lambda _: None)
        self.assertEqual(observed, self.task["process_identity"]["command_sha256"])

    def test_evidence_is_exact_and_bounded(self):
        evidence = self.control.evidence(self.task, "b" * 64)
        self.assertEqual(evidence["process"]["pid"], 4321)
        self.assertEqual(evidence["container"]["label"], "task-001")
        self.assertEqual(evidence["budget"]["state"], "reserved")
        self.assertNotIn(self.system.command, json.dumps(evidence))

    def test_stop_exact_verifies_then_stops_both(self):
        receipt = self.control.stop_exact(self.task)
        self.assertEqual(receipt["schema"], CLEANUP_SCHEMA)
        self.assertTrue(receipt["cleanup_verified"])
        self.assertEqual(self.system.signals, [(4321, signal.SIGTERM)])
        self.assertFalse(self.system.container_present)

    def test_mismatched_process_is_not_killed(self):
        self.system.command = "python unrelated.py"
        receipt = self.control.stop_exact(self.task)
        self.assertFalse(receipt["process_identity_matched"])
        self.assertFalse(receipt["cleanup_verified"])
        self.assertEqual(self.system.signals, [])

    def test_mismatched_container_is_not_stopped(self):
        self.system.label = "some-other-task"
        receipt = self.control.stop_exact(self.task)
        self.assertFalse(receipt["container_identity_matched"])
        self.assertFalse(receipt["cleanup_verified"])
        self.assertTrue(self.system.container_present)


if __name__ == "__main__":
    unittest.main()
