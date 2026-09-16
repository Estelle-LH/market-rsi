#!/usr/bin/env python3
"""Continue the exact controller into its exact bounded raw ingest, unattended."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from bounded_historical_ingest import read_controller_plan, run
from market_rsi import canonical, file_hash, fresh_json


def wait_for_controller(session: Path, timeout_seconds=3600) -> dict:
    started = time.monotonic()
    pid = json.loads((session / "runner-process.json").read_bytes())["pid"]
    assessment = session / "session" / "assessment.json"
    while not assessment.exists():
        if time.monotonic() - started > timeout_seconds:
            raise TimeoutError("controller did not terminate within watcher deadline")
        try:
            os.kill(pid, 0)
        except ProcessLookupError as exc:
            raise ValueError("exact controller exited without an assessment; no download") from exc
        time.sleep(5)
    return read_controller_plan(session)


def execute(session: Path, output: Path, reuse_raw: Path, watcher: Path) -> dict:
    lock = (watcher.parent / "historical-ingest-continuation.lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fresh_json(watcher / "watcher-process.json", {"pid": os.getpid(), "started_unix_ns": time.time_ns(),
                                                 "controller_session": str(session), "output": str(output)})
    try:
        plan = wait_for_controller(session)
        if plan.get("identity_policy") != "preserve_and_flag_no_training_admission":
            raise ValueError("expected raw-only identity policy missing")
        evidence = session / "workspace" / "source-issues.json"
        if not evidence.is_file() or plan.get("source_issues_sha256") != file_hash(evidence):
            raise ValueError("selected plan did not bind later source-quality evidence")
        preparation = json.loads((session / "preparation.json").read_bytes())
        source_root = Path(__file__).absolute().parent
        for name in ("historical_ingest_controller.py", "bounded_historical_ingest.py", "market_rsi.py"):
            if file_hash(source_root / name) != preparation["source_hashes"].get(name):
                raise ValueError("execution source changed after controller preparation")
        fresh_json(watcher / "download-dispatch.json", {"plan_sha256": plan["plan_sha256"],
                                                       "selected_bytes": plan["audit"]["selected_bytes"],
                                                       "unix_ns": time.time_ns()})
        result = run(session, output, reuse_raw)
        fresh_json(watcher / "result.json", result)
        return result
    except Exception as exc:
        fresh_json(watcher / "failure.json", {"type": type(exc).__name__, "error": str(exc),
                                              "automatic_retry": False, "raw_preserved": True})
        raise
    finally:
        lock.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("session-root", "output", "reuse-raw", "watcher-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--detach", action="store_true")
    args = parser.parse_args()
    session, output, reuse, watcher = (getattr(args, name).absolute()
                                        for name in ("session_root", "output", "reuse_raw", "watcher_root"))
    if args.detach:
        watcher.mkdir(mode=0o700, exist_ok=False)
        fresh_json(watcher / "claim.json", {"session": str(session), "output": str(output),
                                            "script_sha256": file_hash(__file__)})
        command = [sys.executable, str(Path(__file__).absolute()), "--session-root", str(session),
                   "--output", str(output), "--reuse-raw", str(reuse), "--watcher-root", str(watcher)]
        with (watcher / "runner.log").open("x") as log:
            child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        print(canonical({"watcher_pid": child.pid, "watcher": str(watcher), "controller": str(session),
                         "new_model_process": False, "bulk_download_only_after_valid_decision": True}))
    else:
        print(canonical(execute(session, output, reuse, watcher)))
