#!/usr/bin/env python3
"""Run one known synthetic candidate through the controller Harbor/E2B bridge."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
from pathlib import Path

from controller_candidate_harbor import prepare_job, run_job
from controller_workspace import LITERATURE_SCHEMA, prepare_workspace
from market_rsi import canonical, digest, fresh_json, identifier
from paid_budget import PaidBudget


def row(name, game, day, mid, target):
    decision = day * 86_400_000 + int(mid * 10_000)
    return {"row_id": name, "game_id": game, "market_id": game + "-market",
            "decision_ms": decision, "feature_available_ms": decision,
            "features": {"mid": mid, "imbalance": 2 * mid - 1}, "target": target,
            "label_available_ms": decision + 60_000}


async def run(output: Path, budget_path: Path, env_file: Path) -> dict:
    output = Path(output).resolve(); identifier(output.name)
    budget = PaidBudget(budget_path); experiment_id = budget.snapshot()["experiment_id"]
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    train = {"schema": "market_permitted_rows_v1", "experiment_id": experiment_id,
        "task_id": "controller-bridge-synthetic", "split": "train",
        "feature_names": ["mid", "imbalance"],
        "rows": [row("t1", "train-game-1", 1, .25, .25),
                 row("t2", "train-game-2", 2, .75, .75)]}
    dev = {"schema": "market_permitted_rows_v1", "experiment_id": experiment_id,
        "task_id": "controller-bridge-synthetic", "split": "dev",
        "feature_names": ["mid", "imbalance"],
        "rows": [row("d1", "dev-game", 3, .2, .2), row("d2", "dev-game", 3, .8, .8)]}
    train_path, dev_path = output / "train.json", output / "dev.json"
    fresh_json(train_path, train); fresh_json(dev_path, dev)
    workspace = output / "workspace"
    manifest = prepare_workspace(workspace, session_id=output.name,
        experiment_id=experiment_id, task_id="controller-bridge-synthetic", arm="canary",
        train_path=train_path, dev_path=dev_path, own_history={"rounds": []},
        literature_snapshot={"schema": LITERATURE_SCHEMA, "papers": []},
        opaque_test_commitment="c" * 64)
    source = ("def fit(train_rows, feature_names):\n    return None\n\n"
              "def predict(model, public_row):\n    return public_row['features']['mid']\n")
    (workspace / "candidate.py").write_text(source)
    request = {"schema": "market_controller_execution_request_v1",
        "execution_id": output.name + "-execution-01", "session_id": output.name,
        "experiment_id": experiment_id, "task_id": "controller-bridge-synthetic",
        "candidate_name": "candidate.py",
        "candidate_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "workspace_manifest_sha256": digest(manifest), "evaluation_role": "train_cv",
        "automatic_retry": False}
    config = {"schema": "market_controller_runner_v1", "session_id": output.name,
        "experiment_id": experiment_id, "task_id": "controller-bridge-synthetic",
        "train_path": str(train_path), "train_sha256": hashlib.sha256(train_path.read_bytes()).hexdigest(),
        "budget_path": str(Path(budget_path).resolve()), "env_file": str(Path(env_file).resolve()),
        "budget_bucket": "setup", "evidence_class": "synthetic"}
    job = output / request["execution_id"]
    claim = prepare_job(request, workspace, config, job)
    score = await run_job(job, budget_path, env_file)
    assessment = {"schema": "market_controller_candidate_live_canary_v1", "passed": True,
        "research_result": False, "future_test_used": False, "automatic_retry": False,
        "job_claim_sha256": digest(claim), "primary": score["primary"],
        "coverage": score["coverage"], "budget": budget.snapshot()}
    fresh_json(output / "assessment.json", assessment)
    return assessment


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--budget", required=True, type=Path)
    parser.add_argument("--env-file", required=True, type=Path)
    args = parser.parse_args()
    print(canonical(asyncio.run(run(args.output, args.budget, args.env_file))))
