#!/usr/bin/env python3
"""Explicit raw-QA adaptation after a crossed-quote ingest stop.

Resume the unchanged controller manifest; preserve old failure and all acquired
bytes. Never call a model, acquire a new data selection or admit training data.
"""
import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time

from bounded_historical_ingest import read_controller_plan, run
from controller_activity_log import read_activity_events, verify_activity_log
from market_rsi import canonical, file_hash, fresh_json, load_json


def verify_stopped_source(session: Path, ingest: Path, previous: Path) -> dict:
    failure = load_json(previous / "failure.json")
    if failure.get("error") != "crossed PM quote":
        raise ValueError("this adaptation only handles the diagnosed crossed-quote stop")
    pid = load_json(previous / "watcher-process.json")["pid"]
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        pass
    else:
        raise ValueError("previous process still alive or PID reused; inspect before resume")
    if (ingest / "completion.json").exists() or list(ingest.rglob("*.partial")):
        raise ValueError("completed ingest or partial file cannot use this continuation")
    plan = read_controller_plan(session)
    if load_json(ingest / "claim.json")["plan_sha256"] != plan["plan_sha256"]:
        raise ValueError("source claim differs from unchanged selected plan")
    events = read_activity_events(ingest / "progress.jsonl")
    if not events or events[-1].get("error") != "crossed PM quote":
        raise ValueError("ingest is no longer at diagnosed failure; do not duplicate resume")
    return plan


def execute(session: Path, ingest: Path, reuse: Path, previous: Path, operation: Path):
    lock = (operation.parent / "historical-ingest-continuation.lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fresh_json(operation / "process.json", {"pid": os.getpid(), "started_unix_ns": time.time_ns()})
    try:
        plan = verify_stopped_source(session, ingest, previous)
        source_root = Path(__file__).absolute().parent
        preparation = load_json(session / "preparation.json")
        for name in ("historical_ingest_controller.py", "market_rsi.py"):
            if file_hash(source_root / name) != preparation["source_hashes"][name]:
                raise ValueError("unchanged controller/accounting source mismatch")
        adaptation = {
            "kind": "raw_only_crossed_quote_preserve_flag_v1",
            "operation_id": operation.name, "source_plan_sha256": plan["plan_sha256"],
            "previous_failure_sha256": file_hash(previous / "failure.json"),
            "ingest_log_before": verify_activity_log(ingest / "progress.jsonl"),
            "old_worker_sha256": preparation["source_hashes"]["bounded_historical_ingest.py"],
            "new_worker_sha256": file_hash(source_root / "bounded_historical_ingest.py"),
            "resume_code_sha256": file_hash(__file__),
            "raw_policy": "preserve_and_flag_no_training_admission",
            "description": "Record crossed rows as failed QA and quarantine; continue raw acquisition only.",
            "manifest_changed": False, "training_admitted": False,
            "new_model_calls": False, "score_retry": False,
        }
        fresh_json(operation / "source-adaptation.json", adaptation)
        result = run(session, ingest, reuse, resume=True,
                     quote_policy="preserve_and_flag_no_training_admission", adaptation=adaptation)
        fresh_json(operation / "result.json", result)
        return result
    except Exception as exc:
        fresh_json(operation / "failure.json", {"error": str(exc), "type": type(exc).__name__,
                                                  "raw_preserved": True, "automatic_retry": False})
        raise
    finally:
        lock.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("session-root", "ingest-root", "reuse-raw", "previous-operation", "operation-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--detach", action="store_true")
    args = parser.parse_args()
    session, ingest, reuse, previous, operation = [getattr(args, key).absolute() for key in
        ("session_root", "ingest_root", "reuse_raw", "previous_operation", "operation_root")]
    if args.detach:
        verify_stopped_source(session, ingest, previous)
        operation.mkdir(exist_ok=False, mode=0o700)
        fresh_json(operation / "claim.json", {"session": str(session), "ingest": str(ingest),
                                               "previous": str(previous), "code_sha256": file_hash(__file__)})
        command = [sys.executable, str(Path(__file__).absolute()), "--session-root", str(session),
                   "--ingest-root", str(ingest), "--reuse-raw", str(reuse),
                   "--previous-operation", str(previous), "--operation-root", str(operation)]
        with (operation / "runner.log").open("x") as log:
            child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        print(canonical({"pid": child.pid, "operation": str(operation), "new_model_calls": False}))
    else:
        print(canonical(execute(session, ingest, reuse, previous, operation)))
