"""Zero-paid canary for the real outer-parent monitor and cleanup path."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

from market_rsi import canonical, file_hash, fresh_json
from supervisor_harness.bounded_live_supervisor_parent_v1 import supervise_started
from supervisor_harness.supervisor_watchdog_local_control import (
    TASK_LABEL_KEY, stable_process_command_sha256,
)


IMAGE = "python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea"


def _container_absent(name: str) -> bool:
    result = subprocess.run(["docker", "inspect", name], capture_output=True,
                            text=True, timeout=5, check=False)
    return result.returncode != 0


def run(output: Path) -> dict:
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError("fresh parent canary output required")
    output.mkdir(parents=True)
    cycle_id = output.name
    if not cycle_id.startswith("supervisor-live-parent-blocked-"):
        raise ValueError("explicit fresh parent canary ID required")
    artifacts = output / "child-artifacts"
    artifacts.mkdir()
    (output / "child.log").write_text("deliberately blocked supervised entry\n")
    container_name = "market-rsi-b-" + uuid.uuid4().hex[:20]
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(300)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    container_started = False
    try:
        command_sha = stable_process_command_sha256(child.pid)
        launched = subprocess.run(
            ["docker", "run", "-d", "--rm", "--name", container_name,
             "--label", f"{TASK_LABEL_KEY}={container_name}",
             "--network", "none", "--read-only", "--cap-drop", "ALL",
             "--pids-limit", "32", IMAGE, "sleep", "300"],
            capture_output=True, text=True, timeout=15, check=False)
        if launched.returncode != 0:
            raise RuntimeError("canary container did not start")
        container_started = True
        budget = lambda task_id: {
            "checked": True, "task_id": task_id, "state": "none",
            "snapshot_sha256": "a" * 64}
        data = lambda _task_id: {
            "gate_status": "not_applicable", "evidence_sha256": None}
        supervised = supervise_started(
            child=child, cycle_id=cycle_id, command_sha256=command_sha,
            container_name=container_name, artifact_root=artifacts,
            supervisor_root=output, budget_evidence=budget,
            data_evidence=data, heartbeat_seconds=.5,
            heartbeat_timeout_seconds=5, progress_timeout_seconds=5)
        cleanups = list((output / "monitor").glob("*/cleanup.json"))
        if len(cleanups) != 1:
            raise RuntimeError("exactly one incident cleanup receipt required")
        cleanup = json.loads(cleanups[0].read_text())
        passed = (supervised["incident_created"] is True
                  and supervised["passed"] is False
                  and cleanup.get("cleanup_verified") is True
                  and child.poll() is not None
                  and _container_absent(container_name)
                  and (output / "supervisor-claim.json").is_file())
        result = {
            "schema": "market_bounded_live_supervisor_parent_canary_v1",
            "cycle_id": cycle_id, "passed": passed,
            "provider_calls": 0, "provider_cost_usd": "0",
            "synthetic_only": True, "process_absent": child.poll() is not None,
            "container_absent": _container_absent(container_name),
            "supervisor_result_sha256": file_hash(output / "result.json"),
            "cleanup_sha256": file_hash(cleanups[0]),
        }
        if not passed:
            raise RuntimeError("outer-parent blocked-child acceptance failed")
        fresh_json(output / "canary-result.json", result)
        return result
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        if container_started and not _container_absent(container_name):
            subprocess.run(["docker", "rm", "-f", container_name],
                           capture_output=True, text=True, timeout=8, check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(run(parser.parse_args().output), sort_keys=True))


if __name__ == "__main__":
    main()
