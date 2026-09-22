"""Run one zero-paid restart/liveness fault-injection canary."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from supervisor_harness.supervisor_watchdog import (
    SupervisorWatchdog, _exclusive_json, _identifier,
)


def run(root: Path) -> dict:
    if root.exists() or root.is_symlink():
        raise FileExistsError("watchdog canary root must be fresh")
    cycle_id = _identifier(root.name, "watchdog canary ID")
    task_id = _identifier(cycle_id + "-stall", "watchdog task ID")
    resume_id = _identifier(cycle_id + "-resume", "watchdog resume ID")
    container_name = _identifier("market-rsi-b-" + cycle_id, "watchdog container")
    start = datetime.now(timezone.utc).replace(microsecond=0)
    watchdog = SupervisorWatchdog(root)
    watchdog.initialize(now=start)
    watchdog.claim_task(
        task_id=task_id, task_kind="infrastructure",
        stage="fault_injection", owner="canary_worker",
        heartbeat_timeout_seconds=10, progress_timeout_seconds=30,
        input_sha256="1" * 64,
        process_identity={"pid": 424242, "command_sha256": "2" * 64},
        container_identity={"name": container_name, "label": task_id},
        now=start)
    for seconds in (5, 10, 15, 20, 25, 30):
        watchdog.heartbeat(task_id, material_progress=False,
                           now=start + timedelta(seconds=seconds))
    incident = watchdog.tick(
        now=start + timedelta(seconds=31),
        evidence={"process": {"checked": True, "pid": 424242,
                              "command_sha256": "2" * 64, "present": False},
                  "container": {"checked": True,
                                "name": container_name,
                                "label": task_id,
                                "present": False},
                  "data": {"gate_status": "not_applicable",
                           "evidence_sha256": None},
                  "budget": {"checked": True,
                             "task_id": task_id,
                             "state": "none", "snapshot_sha256": "4" * 64},
                  "log_tail_sha256": "3" * 64})
    if incident is None or incident["classification"] != "no_material_progress":
        raise RuntimeError("watchdog did not detect synthetic no-progress fault")
    restarted = SupervisorWatchdog(root).snapshot()
    if (restarted["active_task"]["status"] != "repair_pending"
            or len(restarted["incidents"]) != 1):
        raise RuntimeError("watchdog restart lost active incident")
    canary = {"schema": "market_supervisor_watchdog_repair_canary_v1",
              "incident_id": incident["incident_id"],
              "fault": "alive_heartbeat_without_material_progress",
              "detected": True, "restart_recovered": True,
              "old_id_reused": False, "provider_cost_usd": "0"}
    canary_path = root / "repair-canary.json"
    _exclusive_json(canary_path, canary)
    canary_sha = hashlib.sha256(canary_path.read_bytes()).hexdigest()
    closed = watchdog.close_after_verified_repair(
        task_id, incident_id=incident["incident_id"],
        canary_sha256=canary_sha,
        fresh_resume_id=resume_id,
        now=start + timedelta(seconds=32))
    result = {"schema": "market_supervisor_watchdog_canary_result_v1",
              "passed": closed["active_task"] is None,
              "incident_id": incident["incident_id"],
              "classification": incident["classification"],
              "restart_recovered": True, "repair_canary_sha256": canary_sha,
              "fresh_resume_id": resume_id,
              "old_id_reusable": False, "provider_cost_usd": "0",
              "paid_process_started": False, "prediction_claim": False}
    _exclusive_json(root / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(run(parser.parse_args().output.resolve()), sort_keys=True))
