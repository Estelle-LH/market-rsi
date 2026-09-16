#!/usr/bin/env python3
"""Freeze one old Train/Dev task as a v3 controller-harness canary.

This creates new artifacts and a new permanent session ID.  It does not open
Future Test, execute a candidate, call a model, or mutate the old Round 1 run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from controller_workspace import prepare_workspace
from controller_provenance import freeze_source_manifest
from literature_catalog import literature_snapshot
from market_rsi import canonical, digest, fresh_json, identifier
from paid_budget import PaidBudget


def prepare(output: Path, source_round: Path, budget_path: Path, env_file: Path,
            tokenizer_cache: Path, runtime_python: Path, task_id: str) -> dict:
    output = Path(output).resolve()
    identifier(output.name); identifier(task_id)
    source_config = json.loads((Path(source_round) / "runner/config.json").read_text())
    task_data = source_config["task_data"][task_id]
    tasks = json.loads((Path(source_round).parent / "polymarket-rsi-round1-20260907-01-data"
                        / "freeze-v8/tasks.json").read_text())
    task = next(item for item in tasks if item["task_id"] == task_id)
    budget = PaidBudget(budget_path)
    experiment_id = budget.snapshot()["experiment_id"]
    session_id = output.name
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    session = output / "session"
    workspace = output / "workspace"
    manifest = prepare_workspace(workspace, session_id=session_id,
        experiment_id=experiment_id, task_id=task_id, arm="harness-canary",
        train_path=Path(task_data["train_path"]), dev_path=Path(task_data["dev_path"]),
        own_history={"schema": "market_controller_history_v1", "rounds": [],
                     "note": "Old diagnostic task reused only to verify the v3 harness."},
        literature_snapshot=literature_snapshot(),
        opaque_test_commitment=task["opaque_test_commitment"])
    train_path, dev_path = Path(task_data["train_path"]), Path(task_data["dev_path"])
    runner_config = {"schema": "market_controller_runner_v1", "session_id": session_id,
        "experiment_id": experiment_id, "task_id": task_id,
        "train_path": str(train_path.resolve()),
        "train_sha256": hashlib.sha256(train_path.read_bytes()).hexdigest(),
        "budget_path": str(Path(budget_path).resolve()),
        "env_file": str(Path(env_file).resolve()), "budget_bucket": "setup",
        "evidence_class": "diagnostic"}
    fresh_json(output / "runner-config.json", runner_config)
    source_manifest = freeze_source_manifest(output / "source-manifest.json")
    prompt = (
        "This is a harness canary, not a performance result. Work as the research controller. "
        "Read the active harness profile, frozen objective contract and research guide, inspect the allowed Train labels and label-free Dev features, "
        "search the frozen public literature, list the algorithm catalog, inspect at least one "
        "catalog entry, read your own history, and design a Python-standard-library candidate. The "
        "candidate must define fit(train_rows, feature_names) and predict(model, public_row), and "
        "return probabilities in [0,1]. When writing it, record algorithm_family, hypothesis, "
        "literature_ids, change_summary and parent_candidate when applicable. Execute at least "
        "one candidate on reusable Train-CV only. Current Dev is sealed and must not be scored "
        "inside this session. Candidate names must be flat lowercase .py filenames such "
        "as candidate_v1.py, and the first candidate must omit all parent fields. Read the "
        "aggregate Train-CV result, revise once if useful and within the three-execution cap, then submit "
        "exactly one decision selecting a successfully executed candidate. Do not seek Dev labels "
        "or Future Test. A score from this old task is diagnostic only."
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
        "--runner-config", str(output / "runner-config.json"), "--require-all-tools"]
    command += ["--source-manifest", str(output / "source-manifest.json")]
    receipt = {"schema": "market_controller_harness_canary_preparation_v1",
        "session_id": session_id, "experiment_id": experiment_id, "task_id": task_id,
        "workspace_manifest_sha256": digest(manifest),
        "runner_config_sha256": digest(runner_config), "command": command,
        "source_manifest_sha256": digest(source_manifest),
        "runtime_python": str(runtime_python), "runtime_python_sha256": hashlib.sha256(
            runtime_python.read_bytes()).hexdigest(),
        "runtime_python_target": str(runtime_python.resolve()),
        "old_task_reused": True, "research_result": False, "future_test_used": False,
        "model_calls": 0, "candidate_executions": 0}
    fresh_json(output / "preparation.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-round", required=True, type=Path)
    parser.add_argument("--budget", required=True, type=Path)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--tokenizer-cache", required=True, type=Path)
    parser.add_argument("--runtime-python", required=True, type=Path)
    parser.add_argument("--task-id", default="pm-r1-task-00")
    args = parser.parse_args()
    print(canonical(prepare(args.output, args.source_round, args.budget, args.env_file,
                            args.tokenizer_cache, args.runtime_python, args.task_id)))
