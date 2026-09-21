from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from market_rsi import canonical
from supervisor_harness import bounded_live_supervisor_parent_v1 as parent
from supervisor_harness.supervisor_watchdog_local_control import (
    stable_process_command_sha256,
)


class FakeControl:
    instances = []

    def __init__(self, *, budget_evidence, data_evidence):
        self.budget = budget_evidence
        self.data = data_evidence
        self.stop_calls = 0
        self.__class__.instances.append(self)

    def evidence(self, task, log_sha):
        present = task["status"] == "active" and False
        return {
            "process": {"checked": True,
                        "pid": task["process_identity"]["pid"],
                        "command_sha256": task["process_identity"]["command_sha256"],
                        "present": present},
            "container": {"checked": True,
                          "name": task["container_identity"]["name"],
                          "label": task["container_identity"]["label"],
                          "present": False},
            "data": self.data(task["task_id"]),
            "budget": self.budget(task["task_id"]),
            "log_tail_sha256": log_sha,
        }

    def stop_exact(self, task):
        self.stop_calls += 1
        return {"schema": "market_supervisor_exact_cleanup_v1",
                "task_id": task["task_id"],
                "process_identity_matched": True, "process_absent": True,
                "container_identity_matched": True, "container_absent": True,
                "cleanup_verified": True}


class ExitRaceControl(FakeControl):
    """Reproduce a child exit during the monitor's process observation."""

    child = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.first_evidence = True

    def evidence(self, task, log_sha):
        if self.first_evidence:
            self.first_evidence = False
            time.sleep(.25)
            if self.__class__.child.poll() is None:
                raise AssertionError("test child did not exit in race window")
            raise ValueError("process evidence does not match exact task identity")
        return super().evidence(task, log_sha)


class SupervisorParentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        FakeControl.instances.clear()

    def test_progress_hashes_only_allowlisted_regular_json(self):
        artifacts = self.root / "artifacts"
        artifacts.mkdir()
        (artifacts / "result.json").write_text(canonical({"passed": True}))
        first = parent._artifact_progress(artifacts)
        (artifacts / "secret.json").write_text(canonical({"secret": True}))
        self.assertEqual(parent._artifact_progress(artifacts), first)
        (artifacts / "result.json").write_text(canonical({"passed": False}))
        self.assertNotEqual(parent._artifact_progress(artifacts), first)

    def test_supervises_short_success_and_installs_claim(self):
        artifacts = self.root / "cycle-ok"
        artifacts.mkdir()
        (artifacts / "result.json").write_text(canonical({"passed": True}))
        supervisor = self.root / "supervisor"
        supervisor.mkdir()
        (supervisor / "child.log").write_text("synthetic child\n")
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(.15)"])
        command_sha = "c" * 64
        budget = lambda task_id: {
            "checked": True, "task_id": task_id, "state": "none",
            "snapshot_sha256": "a" * 64}
        data = lambda _task_id: {
            "gate_status": "not_applicable", "evidence_sha256": None}
        try:
            with patch.object(parent, "LocalProcessDockerControl", FakeControl), \
                 patch.object(parent, "process_command_sha256",
                              return_value=("e" * 64, True)):
                result = parent.supervise_started(
                    child=child, cycle_id="cycle-ok",
                    command_sha256=command_sha,
                    container_name="market-rsi-b-cycle-ok",
                    artifact_root=artifacts, supervisor_root=supervisor,
                    budget_evidence=budget, data_evidence=data,
                    heartbeat_seconds=.05,
                    terminal_budget_states=frozenset({"none"}))
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
        self.assertTrue(result["passed"])
        self.assertTrue((supervisor / "supervisor-claim.json").is_file())
        self.assertFalse(result["incident_created"])
        self.assertEqual(FakeControl.instances[-1].stop_calls, 0)

    def test_nonzero_child_freezes_failure_and_runs_exact_cleanup(self):
        artifacts = self.root / "cycle-fail"
        artifacts.mkdir()
        supervisor = self.root / "supervisor-fail"
        supervisor.mkdir()
        (supervisor / "child.log").write_text("synthetic failure\n")
        child = subprocess.Popen([sys.executable, "-c", "raise SystemExit(7)"])
        budget = lambda task_id: {
            "checked": True, "task_id": task_id, "state": "none",
            "snapshot_sha256": "a" * 64}
        data = lambda _task_id: {
            "gate_status": "not_applicable", "evidence_sha256": None}
        with patch.object(parent, "LocalProcessDockerControl", FakeControl), \
             patch.object(parent, "process_command_sha256",
                          return_value=("e" * 64, True)):
            result = parent.supervise_started(
                child=child, cycle_id="cycle-fail", command_sha256="d" * 64,
                container_name="market-rsi-b-cycle-fail",
                artifact_root=artifacts, supervisor_root=supervisor,
                budget_evidence=budget, data_evidence=data,
                heartbeat_seconds=.05,
                terminal_budget_states=frozenset({"none"}))
        self.assertFalse(result["passed"])
        self.assertTrue(result["incident_created"])
        self.assertEqual(FakeControl.instances[-1].stop_calls, 1)
        self.assertTrue((supervisor / "terminal-cleanup.json").is_file())
        self.assertTrue((supervisor / "controller-repair-input.json").is_file())

    def test_clean_exit_during_monitor_identity_read_is_terminal_not_incident(self):
        artifacts = self.root / "cycle-race"
        artifacts.mkdir()
        (artifacts / "result.json").write_text(canonical({"passed": True}))
        supervisor = self.root / "supervisor-race"
        supervisor.mkdir()
        (supervisor / "child.log").write_text("synthetic success\n")
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(.12)"])
        ExitRaceControl.child = child
        budget = lambda task_id: {
            "checked": True, "task_id": task_id, "state": "none",
            "snapshot_sha256": "a" * 64}
        data = lambda _task_id: {
            "gate_status": "not_applicable", "evidence_sha256": None}
        with patch.object(parent, "LocalProcessDockerControl", ExitRaceControl), \
             patch.object(parent, "process_command_sha256",
                          return_value=("e" * 64, True)):
            result = parent.supervise_started(
                child=child, cycle_id="cycle-race",
                command_sha256="f" * 64,
                container_name="market-rsi-b-cycle-race",
                artifact_root=artifacts, supervisor_root=supervisor,
                budget_evidence=budget, data_evidence=data,
                heartbeat_seconds=.05,
                terminal_budget_states=frozenset({"none"}))
        self.assertTrue(result["passed"])
        self.assertFalse(result["incident_created"])
        self.assertEqual(ExitRaceControl.instances[-1].stop_calls, 0)


if __name__ == "__main__":
    unittest.main()
