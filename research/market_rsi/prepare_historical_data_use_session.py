#!/usr/bin/env python3
"""Source-bound, exclusive preparation of one existing-corpus GLM review."""
from __future__ import annotations

import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import time

from historical_data_use_controller import prepare_workspace
from market_rsi import canonical, file_hash, fresh_json, identifier, load_json
from paid_budget import PaidBudget, money


PROMPT = (
    "Review the completed historical acquisition and real source-contract canary. "
    "Inspect measured quality, actual UTC receipt coverage and executable field/time "
    "rules before deciding. The previous smallest-file selection did not deliver "
    "verified complete sessions. You decide how to use existing open Train data: "
    "which actual UTC dates, primary observation, optional context streams, cadence, "
    "staleness, market clock scope and feature ideas. Explain coverage and sampling "
    "bias, including limitations of recorded clock proxies. Use the frozen literature "
    "catalog if helpful, accurately distinguishing it from live search. Select one "
    "diagnostic data-use proposal, or defer with a concrete evidence-based reason. "
    "Do not choose a forecast target, new download, Dev/Test period or claim data is "
    "training-ready. This proposal is followed by a separate causal materializer "
    "canary and then your objective research on open Train only. Quiet raw records "
    "stay preserved; no filtering based on future movements. Submit your first valid "
    "decision and exit without further confirmation."
)


def prepare(output: Path, *, feedback: Path, coverage: Path, source_canary: Path,
            budget: Path, runtime: Path, env_file: Path, tokenizer: Path,
            execute: bool = False) -> dict:
    output = output.absolute()
    identifier(output.name)
    runtime = runtime.absolute()  # Keep the venv executable, not its symlink target.
    if not runtime.is_file() or not os.access(runtime, os.X_OK):
        raise ValueError("verified executable runtime required")
    if not env_file.is_file() or not tokenizer.is_dir():
        raise ValueError("existing credential file and pinned tokenizer cache required")
    state = PaidBudget(budget).snapshot()
    if any(k.startswith(output.name + "-") for k in state["jobs"]):
        raise ValueError("controller run ID already permanently claimed")
    if money(state["buckets"]["setup"]["available_usd"]) < money("1"):
        raise ValueError("setup bucket cannot cover the next bounded controller request")
    if any(j["state"] == "dispatched" and "-turn-" in k
           for k, j in state["jobs"].items()):
        raise ValueError("an unresolved controller request must be reconciled first")
    root = Path(__file__).absolute().parent
    # Share the existing acquisition-controller lock: these stages cannot overlap.
    lock = (root / "artifacts" / "historical-ingest-controller.lock").open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise ValueError("another historical controller owns the process lock")
    try:
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
        prepare_workspace(output / "workspace", feedback=feedback, coverage=coverage,
                          source_canary=source_canary, session_id=output.name,
                          experiment_id=state["experiment_id"])
        evidence = load_json(output / "workspace" / "quality.json")
        prompt = PROMPT
        if "open_train_materialization" in evidence:
            prompt += (
                " Your first data-use proposal has now been executed locally and independently audited. "
                "Read the NEW open_train_materialization evidence and preserved prior_data_use_review, "
                "including contract-phase coverage, missing/stale states and the conditional nature "
                "of the quote-change diagnostics. This is a refinement after new source evidence, "
                "not a rerun to seek a better score. You may retain or revise justified parameters, "
                "or defer for a concrete unsupported data-contract extension. Do not turn unverified "
                "nominal windows into settlement truth or hide unsupported row weighting in feature ideas."
            )
        (output / "prompt.txt").write_text(prompt, encoding="utf-8")
        command = [str(runtime), str(root / "run_codex_glm_controller.py"),
                   "--session-id", output.name, "--output", str(output / "session"),
                   "--workspace", str(output / "workspace"), "--prompt", str(output / "prompt.txt"),
                   "--budget", str(budget.absolute()), "--budget-bucket", "setup",
                   "--env-file", str(env_file.absolute()), "--tokenizer-cache", str(tokenizer.absolute()),
                   "--tool-mode", "canary", "--controller-stage", "data_use"]
        source_hashes = {p.name: file_hash(p) for p in sorted(root.glob("*.py"))}
        # Retain exact readable source, not hashes of files that may later change.
        snapshot = output / "source-snapshot"
        snapshot.mkdir()
        for name, sha in source_hashes.items():
            (snapshot / name).write_bytes((root / name).read_bytes())
            if file_hash(snapshot / name) != sha:
                raise ValueError("source changed during snapshot")
        receipt = {"schema": "historical_data_use_preparation_v1", "command": command,
                   "source_hashes": source_hashes, "runtime_sha256": file_hash(runtime),
                   "source_snapshot_directory": str(snapshot),
                   "prompt_sha256": file_hash(output / "prompt.txt"),
                   "input_sha256": {"feedback": file_hash(feedback), "coverage": file_hash(coverage),
                                    "canary_result": file_hash(source_canary / "result.json"),
                                    "canary_claim": file_hash(source_canary / "claim.json")},
                   "budget_before": {k: v for k, v in state.items() if k != "jobs"},
                   "paid_controller_started": False, "download_started": False,
                   "formal_experiment_started": False}
        fresh_json(output / "preparation.json", receipt)
        if execute:
            fresh_json(output / "dispatch-claim.json", {
                "session_id": output.name, "claimed_unix_ns": time.time_ns(),
                "preparation_sha256": file_hash(output / "preparation.json")})
            if any(file_hash(root / name) != sha for name, sha in source_hashes.items()):
                raise ValueError("source changed before dispatch")
            with (output / "runner.log").open("x") as log:
                process = subprocess.Popen(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=True, pass_fds=(lock.fileno(),))
            fresh_json(output / "runner-process.json", {
                "pid": process.pid, "process_group": process.pid, "command": command,
                "lock_inherited": True, "started_unix_ns": time.time_ns()})
            return {"pid": process.pid, "session_id": output.name, "output": str(output),
                    "paid_controller_started": True, "download_started": False}
        return receipt
    finally:
        lock.close()  # The child keeps its inherited lock until it exits.


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "feedback", "coverage", "source-canary", "budget", "runtime", "env-file", "tokenizer"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    print(canonical(prepare(args.output, feedback=args.feedback, coverage=args.coverage,
        source_canary=args.source_canary, budget=args.budget, runtime=args.runtime,
        env_file=args.env_file, tokenizer=args.tokenizer, execute=args.execute)))
