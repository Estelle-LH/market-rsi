"""Zero-paid success-path canary for the real outer Supervisor parent.

This canary proves only that a claimed local child can make allowlisted
progress, run one short task-labelled Docker container, publish a regular
result, exit cleanly, and be accepted without incident or cleanup.  It does
not call a model, read market data, or admit a prediction experiment.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

from market_rsi import file_hash, fresh_json
from supervisor_harness.bounded_live_supervisor_parent_v1 import supervise_started
from supervisor_harness.supervisor_watchdog_local_control import (
    TASK_LABEL_KEY, stable_process_command_sha256,
)


IMAGE = "python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea"
CANARY_SCHEMA = "market_bounded_live_supervisor_parent_success_canary_v1"
CHILD_RESULT_SCHEMA = "market_bounded_live_supervisor_success_child_v1"


def _container_absent(name: str) -> bool:
    result = subprocess.run(
        ["docker", "inspect", name], capture_output=True, text=True,
        timeout=5, check=False)
    return result.returncode != 0


def _wait_for_claim(path: Path, cycle_id: str, seconds: float = 5.0) -> dict:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.is_symlink():
            raise ValueError("Supervisor claim cannot be a symlink")
        if path.is_file():
            value = json.loads(path.read_text())
            if (not isinstance(value, dict)
                    or value.get("cycle_id") != cycle_id
                    or value.get("task_id") != cycle_id
                    or value.get("automatic_retry") is not False):
                raise ValueError("Supervisor claim does not bind this canary")
            return value
        time.sleep(0.02)
    raise TimeoutError("Supervisor claim did not arrive")


def run_child(*, artifacts: Path, supervisor_claim: Path,
              container_name: str, cycle_id: str) -> int:
    """Run one bounded synthetic child after the parent installs its claim."""
    artifacts = Path(artifacts)
    claim = _wait_for_claim(Path(supervisor_claim), cycle_id)
    fresh_json(artifacts / "preflight.json", {
        "schema": "market_bounded_live_supervisor_success_preflight_v1",
        "cycle_id": cycle_id,
        "claim_head_sha256": claim["watchdog_head_sha256"],
        "synthetic_only": True,
        "provider_calls": 0,
    })
    completed = subprocess.run(
        ["docker", "run", "--rm", "--name", container_name,
         "--label", f"{TASK_LABEL_KEY}={container_name}",
         "--network", "none", "--read-only", "--cap-drop", "ALL",
         "--pids-limit", "32", IMAGE, "sleep", "1"],
        capture_output=True, text=True, timeout=15, check=False)
    if completed.returncode != 0:
        fresh_json(artifacts / "outer-failure.json", {
            "schema": "market_bounded_live_supervisor_success_child_failure_v1",
            "cycle_id": cycle_id,
            "classification": "synthetic_container_failed",
            "returncode": completed.returncode,
        })
        return 7
    fresh_json(artifacts / "result.json", {
        "schema": CHILD_RESULT_SCHEMA,
        "cycle_id": cycle_id,
        "passed": True,
        "synthetic_only": True,
        "provider_calls": 0,
        "provider_cost_usd": "0",
        "container_name": container_name,
    })
    return 0


def run(output: Path) -> dict:
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError("fresh success canary output required")
    output.mkdir(parents=True, mode=0o700)
    cycle_id = output.name
    if not cycle_id.startswith("supervisor-live-parent-success-"):
        raise ValueError("explicit fresh success canary ID required")
    artifacts = output / "child-artifacts"
    artifacts.mkdir(mode=0o700)
    claim = output / "supervisor-claim.json"
    container_name = "market-rsi-b-" + uuid.uuid4().hex[:20]
    command = [
        sys.executable, str(Path(__file__).resolve()), "--child",
        "--artifacts", str(artifacts), "--supervisor-claim", str(claim),
        "--container-name", container_name, "--cycle-id", cycle_id,
    ]
    log_handle = (output / "child.log").open("xb")
    child = subprocess.Popen(
        command, stdout=log_handle, stderr=subprocess.STDOUT)
    try:
        command_sha = stable_process_command_sha256(child.pid)
        budget = lambda task_id: {
            "checked": True, "task_id": task_id, "state": "none",
            "snapshot_sha256": "a" * 64,
        }
        data = lambda _task_id: {
            "gate_status": "not_applicable", "evidence_sha256": None,
        }
        supervised = supervise_started(
            child=child, cycle_id=cycle_id,
            command_sha256=command_sha, container_name=container_name,
            artifact_root=artifacts, supervisor_root=output,
            budget_evidence=budget, data_evidence=data,
            heartbeat_seconds=.25, heartbeat_timeout_seconds=5,
            progress_timeout_seconds=8,
            terminal_budget_states=frozenset({"none"}))
    finally:
        log_handle.close()
        if child.poll() is None:
            child.kill()
            child.wait()
        if not _container_absent(container_name):
            subprocess.run(
                ["docker", "rm", "-f", container_name], capture_output=True,
                text=True, timeout=8, check=False)

    cleanups = list((output / "monitor").glob("*/cleanup.json"))
    passed = (
        supervised["passed"] is True
        and supervised["incident_created"] is False
        and supervised["child_exit_code"] == 0
        and child.poll() == 0
        and _container_absent(container_name)
        and not cleanups
        and claim.is_file()
        and (artifacts / "preflight.json").is_file()
        and (artifacts / "result.json").is_file()
    )
    result = {
        "schema": CANARY_SCHEMA,
        "cycle_id": cycle_id,
        "passed": passed,
        "synthetic_only": True,
        "provider_calls": 0,
        "provider_cost_usd": "0",
        "incident_created": supervised["incident_created"],
        "cleanup_called": bool(cleanups),
        "process_absent": child.poll() is not None,
        "container_absent": _container_absent(container_name),
        "supervisor_result_sha256": file_hash(output / "result.json"),
        "child_result_sha256": file_hash(artifacts / "result.json"),
        "claim_sha256": file_hash(claim),
    }
    if not passed:
        raise RuntimeError("outer-parent success-path acceptance failed")
    fresh_json(output / "canary-result.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--supervisor-claim", type=Path)
    parser.add_argument("--container-name")
    parser.add_argument("--cycle-id")
    args = parser.parse_args()
    if args.child:
        required = (args.artifacts, args.supervisor_claim,
                    args.container_name, args.cycle_id)
        if any(value is None for value in required):
            parser.error("child mode requires artifacts, claim, container and cycle")
        raise SystemExit(run_child(
            artifacts=args.artifacts, supervisor_claim=args.supervisor_claim,
            container_name=args.container_name, cycle_id=args.cycle_id))
    if args.output is None:
        parser.error("--output is required")
    print(json.dumps(run(args.output), sort_keys=True))


if __name__ == "__main__":
    main()
