"""Independent outer monitor and repair-packet dispatcher.

The monitor is deliberately separate from the watched runner.  It receives
exact, supervisor-owned observations, asks the durable watchdog to classify a
stall, and only then invokes an exact-identity cleanup control.  It never
retries a task or calls a model.  Instead it emits one bounded Controller
repair input that requires a causal fix, a minimal canary, and a fresh ID.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from supervisor_harness.supervisor_watchdog import (
    SupervisorWatchdog, _exclusive_json,
)


MONITOR_SCHEMA = "market_supervisor_watchdog_monitor_v1"
CLEANUP_SCHEMA = "market_supervisor_exact_cleanup_v1"
REPAIR_INPUT_SCHEMA = "market_supervisor_controller_repair_input_v1"


def _sha_file_tail(path: Path, limit: int = 64 * 1024) -> str:
    path = Path(path)
    if (path.is_symlink() or not path.is_file()
            or path.stat().st_size > 10 * 1024 * 1024):
        raise ValueError("unsafe or missing watched log")
    with path.open("rb") as handle:
        if path.stat().st_size > limit:
            handle.seek(-limit, os.SEEK_END)
        return hashlib.sha256(handle.read()).hexdigest()


def controller_repair_input(incident: dict) -> dict:
    """Expose causal facts and constraints, not host authority or raw logs."""
    if not isinstance(incident, dict) or incident.get("schema") != "market_supervisor_incident_v1":
        raise ValueError("watchdog incident required")
    task = incident.get("task_snapshot", {})
    evidence = incident.get("evidence", {})
    return {
        "schema": REPAIR_INPUT_SCHEMA,
        "incident_id": incident["incident_id"],
        "failed_task_id": incident["task_id"],
        "task_kind": incident["task_kind"],
        "stage": incident["stage"],
        "classification": incident["classification"],
        "heartbeat_age_seconds": incident["heartbeat_age_seconds"],
        "progress_age_seconds": incident["progress_age_seconds"],
        "last_progress_sha256": task.get("last_progress_sha256"),
        "log_tail_sha256": evidence.get("log_tail_sha256"),
        "data_gate_status": evidence.get("data", {}).get("gate_status"),
        "budget_state": evidence.get("budget", {}).get("state"),
        "required_response": {
            "choose_one_causal_layer": True,
            "describe_evidence_needed": True,
            "propose_one_bounded_repair": True,
            "define_minimal_canary": True,
            "define_stop_rule": True,
        },
        "hard_limits": {
            "same_id_retry": False,
            "automatic_retry": False,
            "score_targeted_retry": False,
            "change_original_result": False,
            "open_sealed_or_scored_data": False,
            "start_training_without_data_admission": False,
            "repair_requires_fresh_id": True,
            "repair_requires_independent_canary": True,
        },
    }


def monitor_once(*, watchdog: SupervisorWatchdog, control, log_path: Path,
                 output: Path, now=None) -> dict:
    """Inspect one active task once and dispatch a repair packet if stalled.

    ``control`` is supervisor-owned and must implement ``evidence(task,
    log_tail_sha256)`` and ``stop_exact(task)``.  The latter returns exact
    process/container cleanup receipts and is called only after the watchdog
    has frozen an incident.
    """
    if output.exists() or output.is_symlink():
        raise FileExistsError("monitor output must be fresh")
    state = watchdog.snapshot()
    task = state.get("active_task")
    if task is None:
        raise ValueError("watchdog has no active task")
    if task.get("status") != "active":
        raise ValueError("monitor will not repeat cleanup for a terminal incident")
    log_sha = _sha_file_tail(log_path)
    evidence = control.evidence(task, log_sha)
    incident = watchdog.tick(now=now, evidence=evidence)
    output.mkdir(parents=True)
    if incident is None:
        result = {"schema": MONITOR_SCHEMA, "task_id": task["task_id"],
                  "status": "healthy", "incident_created": False,
                  "cleanup_called": False, "automatic_retry": False}
        _exclusive_json(output / "result.json", result)
        return result

    cleanup = control.stop_exact(task)
    required_cleanup = {"schema", "task_id", "process_identity_matched",
                        "process_absent", "container_identity_matched",
                        "container_absent", "cleanup_verified"}
    if (not isinstance(cleanup, dict) or set(cleanup) != required_cleanup
            or cleanup.get("schema") != CLEANUP_SCHEMA
            or cleanup.get("task_id") != task["task_id"]):
        raise ValueError("exact cleanup receipt is incomplete")
    _exclusive_json(output / "cleanup.json", cleanup)
    repair = controller_repair_input(incident)
    _exclusive_json(output / "controller-repair-input.json", repair)
    result = {"schema": MONITOR_SCHEMA, "task_id": task["task_id"],
              "status": "repair_pending" if cleanup["cleanup_verified"]
              else "repair_pending_cleanup_failed",
              "incident_created": True, "incident_id": incident["incident_id"],
              "classification": incident["classification"],
              "cleanup_called": True,
              "cleanup_verified": cleanup["cleanup_verified"],
              "repair_input_sha256": hashlib.sha256(
                  (output / "controller-repair-input.json").read_bytes()).hexdigest(),
              "automatic_retry": False}
    _exclusive_json(output / "result.json", result)
    return result
