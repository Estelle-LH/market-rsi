#!/usr/bin/env python3
"""Prepare the second diagnostic session that must use a prior Archive parent.

Preparation is local and unpaid.  It neither calls the controller nor executes
a candidate.  The source task is old diagnostic data and cannot become a
research-performance result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from archive_snapshot import validate_history
from controller_provenance import freeze_source_manifest, source_manifest
from controller_workspace import prepare_workspace
from market_rsi import canonical, digest, fresh_json, identifier
from paid_budget import PaidBudget
from prepare_controller_harness_canary import literature_snapshot


def prepare(output: Path, source_round: Path, history_path: Path, budget_path: Path,
            env_file: Path, tokenizer_cache: Path, runtime_python: Path,
            task_id: str) -> dict:
    output = Path(output).resolve()
    identifier(output.name)
    identifier(task_id)
    history = json.loads(Path(history_path).read_bytes())
    history_check = validate_history(history)
    if history_check["legacy_empty"] or history_check["snapshots"] < 1:
        raise ValueError("nonempty verified Archive history required")
    if history["source_manifest_sha256"] != digest(source_manifest()):
        raise ValueError("Archive belongs to a different frozen H0 source set")
    source_config = json.loads((Path(source_round) / "runner/config.json").read_text())
    task_data = source_config["task_data"][task_id]
    tasks = json.loads((Path(source_round).parent / "polymarket-rsi-round1-20260907-01-data"
                        / "freeze-v8/tasks.json").read_text())
    task = next(item for item in tasks if item["task_id"] == task_id)
    budget = PaidBudget(budget_path)
    experiment_id = budget.snapshot()["experiment_id"]
    session_id = output.name
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    workspace = output / "workspace"
    session = output / "session"
    manifest = prepare_workspace(workspace, session_id=session_id,
        experiment_id=experiment_id, task_id=task_id, arm="archive-carryover-canary",
        train_path=Path(task_data["train_path"]), dev_path=Path(task_data["dev_path"]),
        own_history=history, literature_snapshot=literature_snapshot(),
        opaque_test_commitment=task["opaque_test_commitment"])
    train_path = Path(task_data["train_path"])
    runner_config = {"schema": "market_controller_runner_v1", "session_id": session_id,
        "experiment_id": experiment_id, "task_id": task_id,
        "train_path": str(train_path.resolve()),
        "train_sha256": hashlib.sha256(train_path.read_bytes()).hexdigest(),
        "budget_path": str(Path(budget_path).resolve()),
        "env_file": str(Path(env_file).resolve()), "budget_bucket": "setup",
        "evidence_class": "diagnostic"}
    fresh_json(output / "runner-config.json", runner_config)
    frozen_source_manifest = freeze_source_manifest(output / "source-manifest.json")
    prompt = (
        "This is the second Archive carryover canary, not a performance result. Read your own "
        "research history. Find the candidate selected in the latest prior snapshot, and write a "
        "new candidate that uses the exact archive_parent object shown there: prior session_id, "
        "candidate filename, and source_sha256. You may modify its method as you judge useful for "
        "this different old diagnostic task. Candidate names must be new flat lowercase .py "
        "filenames. Execute the new candidate on reusable Train-CV only. Current Dev remains "
        "sealed. If candidate code fails, use the "
        "untrusted diagnostic only to repair a new immutable version and preserve ancestry with "
        "parent_candidate. Submit exactly one successfully executed descendant. Do not seek Dev "
        "labels or Future Test."
    )
    (output / "prompt.txt").write_text(prompt, encoding="utf-8")
    runtime_python = Path(os.path.abspath(runtime_python))
    if not runtime_python.is_file() or not os.access(runtime_python, os.X_OK):
        raise ValueError("executable controller Python runtime required")
    command = [str(runtime_python), str(Path(__file__).with_name("run_codex_glm_controller.py")),
        "--session-id", session_id, "--output", str(session), "--workspace", str(workspace),
        "--prompt", str(output / "prompt.txt"), "--budget", str(Path(budget_path).resolve()),
        "--budget-bucket", "setup", "--env-file", str(Path(env_file).resolve()),
        "--tokenizer-cache", str(Path(tokenizer_cache).resolve()), "--tool-mode", "formal",
        "--runner-config", str(output / "runner-config.json"), "--source-manifest",
        str(output / "source-manifest.json")]
    receipt = {"schema": "market_archive_carryover_canary_preparation_v1",
        "session_id": session_id, "experiment_id": experiment_id, "task_id": task_id,
        "workspace_manifest_sha256": digest(manifest),
        "runner_config_sha256": digest(runner_config), "command": command,
        "source_manifest_sha256": digest(frozen_source_manifest),
        "archive_history_sha256": digest(history),
        "prior_snapshot_sha256": history["snapshots"][-1]["snapshot_sha256"],
        "runtime_python": str(runtime_python),
        "runtime_python_sha256": hashlib.sha256(runtime_python.read_bytes()).hexdigest(),
        "old_task_reused": True, "research_result": False, "future_test_used": False,
        "model_calls": 0, "candidate_executions": 0}
    fresh_json(output / "preparation.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-round", required=True, type=Path)
    parser.add_argument("--history", required=True, type=Path)
    parser.add_argument("--budget", required=True, type=Path)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--tokenizer-cache", required=True, type=Path)
    parser.add_argument("--runtime-python", required=True, type=Path)
    parser.add_argument("--task-id", default="pm-r1-task-01")
    args = parser.parse_args()
    print(canonical(prepare(args.output, args.source_round, args.history, args.budget,
                            args.env_file, args.tokenizer_cache, args.runtime_python,
                            args.task_id)))
