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
import sys

from market_rsi import digest
from supervisor_harness.p0_gate1_public_fetch import fetch_snapshot
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
