"""Supervisor-owned local process and Docker evidence/cleanup control.

This adapter has host authority, so model output must never construct it or
choose its commands.  It verifies the exact task identity before cleanup and
returns only the narrow evidence schema accepted by the durable watchdog.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import time

from supervisor_harness.supervisor_watchdog_monitor import CLEANUP_SCHEMA


TASK_LABEL_KEY = "market-rsi-task-id"


def process_command_sha256(pid: int, *, run=subprocess.run) -> tuple[str | None, bool]:
    """Hash the kernel-visible command string for one exact PID."""
    result = run(["ps", "-p", str(pid), "-o", "command="], capture_output=True,
                 text=True, timeout=5, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return None, False
    command = result.stdout.rstrip("\n")
    return hashlib.sha256(command.encode()).hexdigest(), True


def stable_process_command_sha256(pid: int, *, seconds: float = 2.0,
                                  run=subprocess.run,
                                  monotonic=time.monotonic,
                                  sleep=time.sleep) -> str:
    """Wait for two identical observations after launchers finish execing."""
    deadline = monotonic() + seconds
    prior = None
    while monotonic() < deadline:
        observed, present = process_command_sha256(pid, run=run)
        if not present or observed is None:
            raise RuntimeError("process disappeared before identity stabilized")
        if observed == prior:
            return observed
        prior = observed
        sleep(0.05)
    raise TimeoutError("process command identity did not stabilize")


def container_identity(name: str, *, run=subprocess.run) -> tuple[str | None, bool]:
    """Return the fixed task label only when the exact Docker name exists."""
    result = run(["docker", "inspect", name], capture_output=True, text=True,
                 timeout=5, check=False)
    if result.returncode != 0:
        return None, False
    try:
        records = json.loads(result.stdout)
        if not isinstance(records, list) or len(records) != 1:
            raise ValueError
        record = records[0]
        actual = record.get("Name")
        labels = record.get("Config", {}).get("Labels") or {}
        if actual != "/" + name or not isinstance(labels, dict):
            raise ValueError
        label = labels.get(TASK_LABEL_KEY)
        if not isinstance(label, str):
            raise ValueError
        return label, True
    except (TypeError, ValueError, json.JSONDecodeError):
        raise ValueError("Docker identity response is malformed")


class LocalProcessDockerControl:
    """Collect evidence and stop only the PID/container bound to one task."""

    def __init__(self, *, budget_evidence, data_evidence, run=subprocess.run,
                 kill=os.kill, waitpid=os.waitpid,
                 monotonic=time.monotonic, sleep=time.sleep):
        self._budget = budget_evidence
        self._data = data_evidence
        self._run = run
        self._kill = kill
        self._waitpid = waitpid
        self._monotonic = monotonic
        self._sleep = sleep

    def _process(self, task: dict) -> dict:
        expected = task["process_identity"]
        if expected is None:
            return {"checked": True, "pid": None, "command_sha256": None,
                    "present": False}
        observed, present = process_command_sha256(expected["pid"], run=self._run)
        # Keep the expected identity in an absence receipt; a different live
        # command is surfaced as a mismatch and rejected by the watchdog.
        return {"checked": True, "pid": expected["pid"],
                "command_sha256": observed if present else expected["command_sha256"],
                "present": present}

    def _container(self, task: dict) -> dict:
        expected = task["container_identity"]
        if expected is None:
            return {"checked": True, "name": None, "label": None,
                    "present": False}
        observed, present = container_identity(expected["name"], run=self._run)
        return {"checked": True, "name": expected["name"],
                "label": observed if present else expected["label"],
                "present": present}

    def evidence(self, task: dict, log_tail_sha256: str) -> dict:
        budget = self._budget(task["task_id"])
        data = self._data(task["task_id"])
        return {"process": self._process(task),
                "container": self._container(task),
                "data": data, "budget": budget,
                "log_tail_sha256": log_tail_sha256}

    def _pid_absent(self, pid: int) -> bool:
        try:
            reaped, _ = self._waitpid(pid, os.WNOHANG)
            if reaped == pid:
                return True
        except (ChildProcessError, PermissionError):
            pass
        try:
            self._kill(pid, 0)
            return False
        except ProcessLookupError:
            return True
        except PermissionError:
            return False

    def _wait_pid_absent(self, pid: int, seconds: float) -> bool:
        deadline = self._monotonic() + seconds
        while self._monotonic() < deadline:
            if self._pid_absent(pid):
                return True
            self._sleep(0.02)
        return self._pid_absent(pid)

    def _wait_container_absent(self, name: str, seconds: float) -> bool:
        deadline = self._monotonic() + seconds
        while self._monotonic() < deadline:
            _, present = container_identity(name, run=self._run)
            if not present:
                return True
            self._sleep(0.02)
        _, present = container_identity(name, run=self._run)
        return not present

    def stop_exact(self, task: dict) -> dict:
        process = task["process_identity"]
        container = task["container_identity"]
        process_match = process is None
        process_absent = process is None
        container_match = container is None
        container_absent = container is None

        if process is not None:
            observed, present = process_command_sha256(process["pid"], run=self._run)
            process_match = (not present) or observed == process["command_sha256"]
            if present and process_match:
                self._kill(process["pid"], signal.SIGTERM)
                process_absent = self._wait_pid_absent(process["pid"], 2.0)
                if not process_absent:
                    self._kill(process["pid"], signal.SIGKILL)
                    process_absent = self._wait_pid_absent(process["pid"], 2.0)
            else:
                process_absent = not present

        if container is not None:
            observed, present = container_identity(container["name"], run=self._run)
            container_match = (not present) or observed == container["label"]
            if present and container_match:
                stopped = self._run(
                    ["docker", "stop", "--time", "2", container["name"]],
                    capture_output=True, text=True, timeout=8, check=False)
                if stopped.returncode == 0:
                    container_absent = self._wait_container_absent(
                        container["name"], 3.0)
            else:
                container_absent = not present

        verified = (process_match and process_absent
                    and container_match and container_absent)
        return {"schema": CLEANUP_SCHEMA, "task_id": task["task_id"],
                "process_identity_matched": process_match,
                "process_absent": process_absent,
                "container_identity_matched": container_match,
                "container_absent": container_absent,
                "cleanup_verified": verified}
