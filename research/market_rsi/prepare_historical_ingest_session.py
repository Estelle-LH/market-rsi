#!/usr/bin/env python3
"""Prepare and optionally launch exactly one source-bound ingest controller."""
from __future__ import annotations

import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import time

from historical_ingest_controller import prepare_workspace
from market_rsi import canonical, file_hash, fresh_json, identifier
from paid_budget import PaidBudget


def prepare(output: Path, *, inventory: Path, canary: Path, budget: Path,
            runtime: Path, env_file: Path, tokenizer: Path, execute: bool = False,
            source_issues: Path | None = None) -> dict:
    output = output.absolute()
    identifier(output.name)
    # Preserve venv executable path rather than resolving the underlying Python symlink.
    runtime = runtime.absolute()
    if not runtime.is_file() or not os.access(runtime, os.X_OK):
        raise ValueError("verified executable runtime required")
    state = PaidBudget(budget).snapshot()
    if any(k.startswith(output.name + "-") for k in state["jobs"]):
        raise ValueError("controller run ID already permanently claimed")
    if float(state["buckets"]["setup"]["available_usd"]) < 1.0:
        raise ValueError("setup bucket cannot reserve next controller request")
    root = Path(__file__).absolute().parent
    lock = (root / "artifacts" / "historical-ingest-controller.lock").open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise ValueError("another historical-ingest controller owns the process lock")
    try:
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
        prepare_workspace(output / "workspace", inventory=inventory, canary=canary,
                          session_id=output.name, experiment_id=state["experiment_id"],
                          source_issues=source_issues)
        prompt = (
            "Continue the approved historical-data work after its passing canary. "
            "Inspect the full inventory, canary limitations, later source-issue evidence and resource cap; research "
            "the scientific sampling implications; propose and compare at least two "
            "distinct executable selections. Choose one exact 40-or-more-date raw "
            "manifest within 5 GB, or explicitly defer if none is scientifically useful. "
            "Use propose_ingest_recipe to compute actual available dates and bytes; "
            "do not keep manually guessing dates. You choose the rule, dates and available "
            "streams, not the runner. With identity mismatches, acquisition is RAW QA ONLY: "
            "preserve and flag mismatches, never relabel automatically or admit to training. Keep all valid "
            "records in selected files. A partial file-date is not a full session. "
            "Do not silently favor large future movements. This is preparation, not "
            "Train/Dev or objective selection. Submit your first valid decision and exit."
        )
        (output / "prompt.txt").write_text(prompt)
        command = [str(runtime), str(root / "run_codex_glm_controller.py"),
                   "--session-id", output.name, "--output", str(output / "session"),
                   "--workspace", str(output / "workspace"), "--prompt", str(output / "prompt.txt"),
                   "--budget", str(budget.absolute()), "--budget-bucket", "setup",
                   "--env-file", str(env_file.absolute()), "--tokenizer-cache", str(tokenizer.absolute()),
                   "--tool-mode", "canary", "--controller-stage", "ingest"]
        source_hashes = {p.name: file_hash(p) for p in sorted(root.glob("*.py"))}
        receipt = {"schema": "historical_ingest_preparation_v1", "command": command,
                   "source_hashes": source_hashes, "runtime_sha256": file_hash(runtime),
                   "prompt_sha256": file_hash(output / "prompt.txt"),
                   "budget_before": {k: v for k, v in state.items() if k != "jobs"},
                   "download_started": False, "formal_experiment_started": False}
        fresh_json(output / "preparation.json", receipt)
        if execute:
            fresh_json(output / "dispatch-claim.json", {
                "session_id": output.name, "claimed_unix_ns": time.time_ns(),
                "preparation_sha256": file_hash(output / "preparation.json")})
            if any(file_hash(root / name) != expected for name, expected in source_hashes.items()):
                raise ValueError("source changed before dispatch")
            with (output / "runner.log").open("x") as log:
                process = subprocess.Popen(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=True, pass_fds=(lock.fileno(),))
            fresh_json(output / "runner-process.json", {
                "pid": process.pid, "process_group": process.pid, "command": command,
                "lock_inherited": True, "started_unix_ns": time.time_ns()})
            receipt = {"pid": process.pid, "session_id": output.name,
                       "output": str(output), "paid_controller_started": True,
                       "download_started": False}
        return receipt
    finally:
        # The child keeps the inherited lock until it exits.
        lock.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("output", "inventory", "canary", "budget", "runtime", "env-file", "tokenizer"):
        parser.add_argument("--" + arg, type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--source-issues", type=Path)
    args = parser.parse_args()
    print(canonical(prepare(args.output, inventory=args.inventory, canary=args.canary,
                            budget=args.budget, runtime=args.runtime, env_file=args.env_file,
                            tokenizer=args.tokenizer, execute=args.execute,
                            source_issues=args.source_issues)))
