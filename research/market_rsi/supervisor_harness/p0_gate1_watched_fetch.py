"""Bind the Gate 1 official-source fetch to the durable Supervisor watchdog.

This is the first real runner binding.  It records task claim, material
progress, exact process/budget evidence, terminal success, or an immediate
incident.  The underlying fetch remains one bounded allowlisted request.  A
separate outer monitor is still required to detect a child blocked below the
transport's wall timeout.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys

from market_rsi import canonical, digest
from supervisor_harness.p0_gate1_public_fetch import (
    fetch_snapshot, fetch_source_scope_snapshot,
)
from supervisor_harness.supervisor_watchdog import SupervisorWatchdog


def command_sha256(argv: list[str] | None = None) -> str:
    argv = list(sys.argv if argv is None else argv)
    return hashlib.sha256("\0".join(argv).encode()).hexdigest()


def _evidence(*, task_id: str, pid: int, command_sha: str,
              budget_snapshot_sha256: str, log_tail_sha256: str,
              present: bool = True) -> dict:
    return {
        "process": {"checked": True, "pid": pid,
                    "command_sha256": command_sha, "present": present},
        "container": {"checked": True, "name": None,
                      "label": None, "present": False},
        "data": {"gate_status": "unknown", "evidence_sha256": None},
        "budget": {"checked": True, "task_id": task_id, "state": "none",
                   "snapshot_sha256": budget_snapshot_sha256},
        "log_tail_sha256": log_tail_sha256,
    }


def run(*, watchdog: SupervisorWatchdog, task_id: str, task: dict,
        admission: dict, output: Path, transport, pid: int,
        process_command_sha256: str, budget_snapshot_sha256: str,
        clock=None) -> dict:
    """Run one already-compiled plan-only fetch under watchdog state."""
    now = None if clock is None else clock()
    input_sha = digest({"task": task, "admission": admission})
    watchdog.claim_task(
        task_id=task_id, task_kind="research", stage="gate1_public_fetch",
        owner="trusted_broker", heartbeat_timeout_seconds=20,
        progress_timeout_seconds=30, input_sha256=input_sha,
        process_identity={"pid": pid, "command_sha256": process_command_sha256},
        container_identity=None, now=now)
    watchdog.heartbeat(task_id, material_progress=True,
                       progress_sha256=input_sha,
                       now=None if clock is None else clock())
    try:
        receipt = fetch_snapshot(task, admission, output, transport)
    except Exception as exc:
        error_sha = hashlib.sha256(
            (type(exc).__name__ + ":" + str(exc)).encode()).hexdigest()
        classification = "malformed_data" if isinstance(
            exc, (ValueError, UnicodeError)) else "worker_error"
        watchdog.report_failure(
            task_id, classification=classification,
            evidence=_evidence(
                task_id=task_id, pid=pid, command_sha=process_command_sha256,
                budget_snapshot_sha256=budget_snapshot_sha256,
                log_tail_sha256=error_sha),
            now=None if clock is None else clock())
        raise
    receipt_sha = hashlib.sha256(
        (Path(output) / "receipt.json").read_bytes()).hexdigest()
    watchdog.heartbeat(task_id, material_progress=True,
                       progress_sha256=receipt_sha,
                       now=None if clock is None else clock())
    watchdog.close_success(task_id, result_sha256=receipt_sha,
                           now=None if clock is None else clock())
    return receipt


_PRECLAIMED_TASK_FIELDS = frozenset({
    "task_id", "task_kind", "stage", "owner", "status", "started_utc",
    "last_heartbeat_utc", "last_progress_utc", "progress_seq",
    "last_progress_sha256", "heartbeat_timeout_seconds",
    "progress_timeout_seconds", "input_sha256", "data_admission_sha256",
    "process_identity", "container_identity", "data_gate", "incident_id",
})


def _preclaimed_evidence(*, task_id: str, pid: int, command_sha: str,
                         budget_snapshot_sha256: str,
                         log_tail_sha256: str) -> dict:
    return {
        "process": {"checked": True, "pid": pid,
                    "command_sha256": command_sha, "present": True},
        "container": {"checked": True, "name": None,
                      "label": None, "present": False},
        "data": {"gate_status": "not_applicable", "evidence_sha256": None},
        "budget": {"checked": True, "task_id": task_id, "state": "none",
                   "snapshot_sha256": budget_snapshot_sha256},
        "log_tail_sha256": log_tail_sha256,
    }


def run_preclaimed(*, watchdog: SupervisorWatchdog, task_id: str, task: dict,
                   admission: dict, output: Path, pid: int,
                   process_command_sha256: str,
                   budget_snapshot_sha256: str, receipt_validator,
                   clock=None) -> dict:
    """Run the exact source-scope fetch under the parent's active claim.

    This seam never claims or closes the watchdog.  The outer parent owns both
    operations and the process/global-state terminal boundary.
    """
    if type(watchdog) is not SupervisorWatchdog:
        raise ValueError("exact Supervisor watchdog required")
    if (type(pid) is not int or pid <= 1
            or type(process_command_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", process_command_sha256) is None
            or type(budget_snapshot_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", budget_snapshot_sha256) is None
            or not callable(receipt_validator)):
        raise ValueError("exact preclaimed process and verifier required")
    # The adapter is the sole owner of the new task/admission language.  This
    # validation happens before either a heartbeat or transport call.
    from supervisor_harness.p0_gate1_source_scope_fetch_adapter import (
        validate_task_admission,
    )
    task, admission = validate_task_admission(task, admission)
    input_sha = digest({"task": task, "admission": admission})
    state = watchdog.snapshot()
    active = state.get("active_task")
    expected_identity = {
        "pid": pid, "command_sha256": process_command_sha256,
    }
    if (type(active) is not dict or set(active) != _PRECLAIMED_TASK_FIELDS
            or active["task_id"] != task_id
            or active["task_kind"] != "research"
            or active["stage"] != "gate1_source_scope_fetch"
            or active["owner"] != "trusted_broker"
            or active["status"] != "active"
            or active["heartbeat_timeout_seconds"] != 20
            or active["progress_timeout_seconds"] != 30
            or active["input_sha256"] != input_sha
            or active["process_identity"] != expected_identity
            or active["container_identity"] is not None
            or active["data_admission_sha256"] is not None
            or active["data_gate"] is not None
            or active["incident_id"] is not None
            or active["progress_seq"] != 0
            or active["last_progress_sha256"] is not None):
        raise ValueError("exact active parent watchdog claim required")
    watchdog.heartbeat(
        task_id, material_progress=True, progress_sha256=input_sha,
        now=None if clock is None else clock())
    try:
        receipt = fetch_source_scope_snapshot(task, admission, Path(output))
        snapshot = Path(output) / "public-source.snapshot"
        if receipt_validator(receipt, snapshot) != receipt:
            raise ValueError("snapshot receipt validator changed the receipt")
        receipt_path = Path(output) / "receipt.json"
        if (receipt_path.is_symlink() or not receipt_path.is_file()
                or receipt_path.stat().st_nlink != 1
                or receipt_path.read_bytes()
                != (canonical(receipt) + "\n").encode("utf-8")):
            raise ValueError("snapshot receipt is not exact canonical bytes")
    except Exception as exc:
        current = watchdog.snapshot().get("active_task")
        if (type(current) is dict and current.get("task_id") == task_id
                and current.get("status") == "active"):
            error_sha = hashlib.sha256(
                (type(exc).__name__ + ":" + str(exc)).encode()).hexdigest()
            watchdog.report_failure(
                task_id,
                classification=("malformed_data" if isinstance(
                    exc, (ValueError, UnicodeError)) else "worker_error"),
                evidence=_preclaimed_evidence(
                    task_id=task_id, pid=pid,
                    command_sha=process_command_sha256,
                    budget_snapshot_sha256=budget_snapshot_sha256,
                    log_tail_sha256=error_sha),
                now=None if clock is None else clock())
        raise
    receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    watchdog.heartbeat(
        task_id, material_progress=True, progress_sha256=receipt_sha,
        now=None if clock is None else clock())
    return receipt
