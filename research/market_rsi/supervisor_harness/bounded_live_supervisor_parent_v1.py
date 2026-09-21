"""Outer process parent for the one-shot bounded Controller -> local-B entry.

The child cannot read the provider key until this parent has claimed its exact
PID/command in the durable watchdog and installed the matching claim receipt.
The parent then observes artifact progress and independently invokes the local
PID/Docker cleanup control if progress stops.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from market_rsi import canonical, digest, file_hash, fresh_json, identifier
from paid_budget import PaidBudget
from supervisor_harness import bounded_live_entry_v1 as entry
from supervisor_harness.supervisor_watchdog import SupervisorWatchdog
from supervisor_harness.supervisor_watchdog_local_control import (
    LocalProcessDockerControl, process_command_sha256,
    stable_process_command_sha256,
)
from supervisor_harness.supervisor_watchdog_monitor import (
    CLEANUP_SCHEMA, _sha_file_tail, controller_repair_input, monitor_once,
)


RESULT_SCHEMA = "market_bounded_live_supervisor_parent_v1"
PROGRESS_NAMES = {
    "publication.json", "runtime.json", "input.json", "admission.json",
    "reserved.json", "preflight.json", "dispatched.json",
    "reconciliation.json", "result.json", "outer-failure.json",
    "outer-unresolved.json", "claim.json", "request.json", "encoded.json",
    "cost-preview.json", "provider-receipt.json", "decision.json",
    "broker-binding.json", "task.json", "order.json", "b-launch.json",
    "process.json", "cleanup.json",
}


def _artifact_progress(root: Path) -> str | None:
    root = Path(root)
    if not root.exists():
        return None
    if root.is_symlink() or not root.is_dir():
        raise ValueError("unsafe live artifact root")
    records = []
    for path in sorted(root.rglob("*.json")):
        if (path.name not in PROGRESS_NAMES or path.is_symlink()
                or not path.is_file() or path.stat().st_size > 1024 * 1024):
            continue
        records.append({"path": str(path.relative_to(root)),
                        "sha256": file_hash(path)})
    return digest(records) if records else None


def _budget_reader(root: Path, task_id: str) -> dict:
    snapshot = PaidBudget(root).snapshot()
    job = snapshot.get("jobs", {}).get(task_id)
    observed = "none" if job is None else job.get("state")
    state = {
        "cancelled_before_dispatch": "settled",
        "metered_terminal": "settled",
    }.get(observed, observed)
    if state not in {"none", "reserved", "dispatched", "settled",
                     "uncertain_terminal"}:
        raise ValueError("unrecognized live budget state")
    return {"checked": True, "task_id": task_id, "state": state,
            "snapshot_sha256": digest(snapshot)}


def _child_command(args, claim: Path) -> list[str]:
    command = [sys.executable, str(Path(entry.__file__).resolve())]
    paths = ("root", "adapter_claim_root", "global_state_root", "decision_doc",
             "budget_root", "packet", "runtime_receipt", "env_file",
             "tokenizer_cache")
    strings = ("experiment_id", "budget_cap_usd", "cycle_id",
               "expected_packet_sha256", "expected_head_sha256",
               "expected_decision_sha256", "prior_canary_sha256",
               "release_tag", "expected_source_sha256")
    for name in paths:
        command.extend(["--" + name.replace("_", "-"), str(getattr(args, name))])
    command.extend(["--supervisor-claim", str(claim)])
    for name in strings:
        command.extend(["--" + name.replace("_", "-"), str(getattr(args, name))])
    return command


def supervise_started(*, child: subprocess.Popen, cycle_id: str,
                      command_sha256: str, container_name: str,
                      artifact_root: Path, supervisor_root: Path,
                      budget_evidence, data_evidence,
                      heartbeat_seconds: float = 2.0,
                      heartbeat_timeout_seconds: int = 10,
                      progress_timeout_seconds: int = 30,
                      terminal_budget_states: frozenset[str] = frozenset({"settled"})) -> dict:
    """Supervise one already-started exact child until terminal or incident."""
    watchdog = SupervisorWatchdog(supervisor_root / "watchdog")
    start = datetime.now(timezone.utc)
    watchdog.initialize(now=start)
    watchdog.claim_task(
        task_id=cycle_id, task_kind="research", stage="bounded_live_entry",
        owner="outer_supervisor",
        heartbeat_timeout_seconds=heartbeat_timeout_seconds,
        progress_timeout_seconds=progress_timeout_seconds,
        input_sha256=digest({"cycle_id": cycle_id,
                             "command_sha256": command_sha256}),
        process_identity={"pid": child.pid,
                          "command_sha256": command_sha256},
        container_identity={"name": container_name,
                            "label": container_name}, now=start)
    claim = {"schema": entry.SUPERVISOR_CLAIM_SCHEMA,
             "cycle_id": cycle_id, "task_id": cycle_id, "pid": child.pid,
             "process_command_sha256": command_sha256,
             "supervisor_pid": os.getpid(),
             "supervisor_command_sha256": process_command_sha256(os.getpid())[0],
             "watchdog_head_sha256": watchdog.snapshot()["head_sha256"],
             "automatic_retry": False}
    if claim["supervisor_command_sha256"] is None:
        raise RuntimeError("cannot bind outer Supervisor command identity")
    fresh_json(supervisor_root / "supervisor-claim.json", claim)
    control = LocalProcessDockerControl(
        budget_evidence=budget_evidence, data_evidence=data_evidence)
    last_progress = None
    tick = 0
    next_heartbeat = time.monotonic()
    incident = None
    while child.poll() is None:
        progress = _artifact_progress(artifact_root)
        material = progress is not None and progress != last_progress
        now_mono = time.monotonic()
        if material or now_mono >= next_heartbeat:
            watchdog.heartbeat(cycle_id, material_progress=material,
                               progress_sha256=progress if material else None)
            if material:
                last_progress = progress
            next_heartbeat = now_mono + heartbeat_seconds
        # The child can exit after the loop-head poll and before independent
        # process evidence is collected.  Reap that exact Popen here instead
        # of letting ``ps`` observe a transient zombie command string as an
        # identity substitution.  A PID reused by another process is still
        # rejected by the independent terminal evidence below.
        if child.poll() is not None:
            break
        tick += 1
        monitor_root = supervisor_root / "monitor" / f"{tick:06d}"
        try:
            observed = monitor_once(
                watchdog=watchdog, control=control,
                log_path=supervisor_root / "child.log", output=monitor_root)
        except ValueError as exc:
            # There is a second, narrower exit window between the poll above
            # and the monitor's kernel read.  Suppress only the exact process-
            # identity error when this parent can reap the same child as a
            # terminal process.  Every other monitor error remains fatal.
            if (str(exc) == "process evidence does not match exact task identity"
                    and child.poll() is not None):
                break
            raise
        if observed["incident_created"]:
            incident = observed
            break
        time.sleep(min(0.25, heartbeat_seconds))

    try:
        exit_code = child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        exit_code = None
    state = watchdog.snapshot()
    if incident is None and state["active_task"]["status"] == "active":
        terminal_evidence = control.evidence(
            state["active_task"],
            _sha_file_tail(supervisor_root / "child.log"))
        independently_terminal = (
            terminal_evidence["process"]["present"] is False
            and terminal_evidence["container"]["present"] is False
            and terminal_evidence["budget"]["state"] in terminal_budget_states)
        if (exit_code == 0 and (artifact_root / "result.json").is_file()
                and independently_terminal):
            watchdog.close_success(
                cycle_id, result_sha256=file_hash(artifact_root / "result.json"))
        else:
            packet = watchdog.report_failure(
                cycle_id, classification="worker_error",
                evidence=terminal_evidence)
            cleanup = control.stop_exact(state["active_task"])
            if (not isinstance(cleanup, dict)
                    or cleanup.get("schema") != CLEANUP_SCHEMA
                    or cleanup.get("task_id") != cycle_id):
                raise ValueError("terminal exact cleanup receipt is incomplete")
            fresh_json(supervisor_root / "terminal-cleanup.json", cleanup)
            fresh_json(supervisor_root / "controller-repair-input.json",
                       controller_repair_input(packet))
            incident = {"incident_created": True,
                        "incident_id": packet["incident_id"],
                        "classification": packet["classification"],
                        "cleanup_verified": cleanup.get("cleanup_verified")}
    final = watchdog.snapshot()
    passed = (exit_code == 0 and incident is None
              and final["active_task"] is None)
    result = {"schema": RESULT_SCHEMA, "cycle_id": cycle_id,
              "passed": passed, "child_exit_code": exit_code,
              "incident_created": incident is not None,
              "incident_id": None if incident is None else incident["incident_id"],
              "automatic_retry": False,
              "watchdog_head_sha256": final["head_sha256"]}
    fresh_json(supervisor_root / "result.json", result)
    return result


def run(args) -> dict:
    identifier(args.cycle_id)
    supervisor_root = Path(args.supervisor_root)
    if supervisor_root.exists() or supervisor_root.is_symlink():
        raise FileExistsError("fresh supervisor root required")
    supervisor_root.mkdir(parents=True, mode=0o700)
    claim = supervisor_root / "supervisor-claim.json"
    command = _child_command(args, claim)
    log_handle = (supervisor_root / "child.log").open("xb")
    child = subprocess.Popen(command, stdout=log_handle, stderr=subprocess.STDOUT)
    try:
        command_sha = stable_process_command_sha256(child.pid)
        return supervise_started(
            child=child, cycle_id=args.cycle_id,
            command_sha256=command_sha,
            container_name="market-rsi-b-" + args.cycle_id,
            artifact_root=args.root, supervisor_root=supervisor_root,
            budget_evidence=lambda task_id: _budget_reader(
                args.budget_root, task_id),
            data_evidence=lambda _task_id: {
                "gate_status": "not_applicable", "evidence_sha256": None},
            terminal_budget_states=frozenset({"settled"}))
    finally:
        log_handle.close()
        if child.poll() is None:
            child.kill()
            child.wait()


def parser() -> argparse.ArgumentParser:
    value = entry.parser(require_supervisor_claim=False)
    value.description = "Run one bounded live entry under the durable outer Supervisor"
    value.add_argument("--supervisor-root", required=True, type=Path)
    return value


def main() -> None:
    print(json.dumps(run(parser().parse_args()), sort_keys=True))


if __name__ == "__main__":
    main()
