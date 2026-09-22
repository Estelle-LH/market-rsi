"""Run one fresh zero-paid blocked-child canary against real PID and Docker."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from market_rsi import canonical, digest, file_hash
from supervisor_harness.supervisor_watchdog import SupervisorWatchdog
from supervisor_harness.supervisor_watchdog_local_control import (
    LocalProcessDockerControl, TASK_LABEL_KEY, stable_process_command_sha256,
)
from supervisor_harness.supervisor_watchdog_monitor import monitor_once


HERE = Path(__file__).resolve().parent
IMAGE = "python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea"


def _absent(name: str) -> bool:
    result = subprocess.run(["docker", "inspect", name], capture_output=True,
                            text=True, timeout=5, check=False)
    return result.returncode != 0


def run(output: Path) -> dict:
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError("fresh canary output required")
    output.mkdir(parents=True)
    canary_id = output.name
    if not canary_id.startswith("supervisor-local-control-"):
        raise ValueError("canary ID must be explicit in the output name")
    task_id = canary_id + "-blocked-child"
    container_name = "market-rsi-" + uuid.uuid4().hex[:20]
    log = output / "child.log"
    log.write_text("deliberately blocked zero-paid child\n")
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(300)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    started_container = False
    try:
        command_sha = stable_process_command_sha256(child.pid)
        launched = subprocess.run(
            ["docker", "run", "-d", "--rm", "--name", container_name,
             "--label", f"{TASK_LABEL_KEY}={task_id}", "--network", "none",
             "--read-only", "--cap-drop", "ALL", "--pids-limit", "32",
             IMAGE, "sleep", "300"],
            capture_output=True, text=True, timeout=15, check=False)
        if launched.returncode != 0:
            raise RuntimeError("zero-paid canary container did not start")
        started_container = True
        watchdog = SupervisorWatchdog(output / "watchdog")
        start = datetime.now(timezone.utc)
        watchdog.initialize(now=start)
        input_sha = digest({"schema": "market_supervisor_local_control_canary_input_v1",
                            "canary_id": canary_id, "synthetic_only": True})
        watchdog.claim_task(
            task_id=task_id, task_kind="infrastructure", stage="blocked_child",
            owner="outer_supervisor", heartbeat_timeout_seconds=10,
            progress_timeout_seconds=30, input_sha256=input_sha,
            process_identity={"pid": child.pid, "command_sha256": command_sha},
            container_identity={"name": container_name, "label": task_id},
            now=start)
        budget_sha = hashlib.sha256(
            canonical({"task_id": task_id, "state": "none", "cost": "0"}).encode()
        ).hexdigest()
        control = LocalProcessDockerControl(
            budget_evidence=lambda observed: {
                "checked": True, "task_id": observed, "state": "none",
                "snapshot_sha256": budget_sha},
            data_evidence=lambda observed: {
                "gate_status": "not_applicable", "evidence_sha256": None})
        monitored = monitor_once(
            watchdog=watchdog, control=control, log_path=log,
            output=output / "monitor",
            now=start + timedelta(seconds=11))
        child.wait(timeout=5)
        cleanup = json.loads((output / "monitor" / "cleanup.json").read_text())
        passed = (monitored["status"] == "repair_pending"
                  and monitored["classification"] == "worker_heartbeat_timeout"
                  and cleanup["cleanup_verified"] is True
                  and child.poll() is not None and _absent(container_name))
        result = {
            "schema": "market_supervisor_local_control_canary_result_v1",
            "canary_id": canary_id, "task_id": task_id, "passed": passed,
            "synthetic_only": True, "provider_calls": 0,
            "provider_cost_usd": "0", "process_absent": child.poll() is not None,
            "container_absent": _absent(container_name),
            "monitor_result_sha256": file_hash(output / "monitor" / "result.json"),
            "cleanup_sha256": file_hash(output / "monitor" / "cleanup.json"),
            "source_sha256": digest({
                "runner": file_hash(Path(__file__)),
                "control": file_hash(HERE / "supervisor_watchdog_local_control.py"),
                "monitor": file_hash(HERE / "supervisor_watchdog_monitor.py"),
                "watchdog": file_hash(HERE / "supervisor_watchdog.py")}),
        }
        if not passed:
            raise RuntimeError("local control canary acceptance failed")
        (output / "result.json").write_text(canonical(result) + "\n")
        return result
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        if started_container and not _absent(container_name):
            subprocess.run(["docker", "rm", "-f", container_name],
                           capture_output=True, text=True, timeout=8, check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), sort_keys=True))


if __name__ == "__main__":
    main()
