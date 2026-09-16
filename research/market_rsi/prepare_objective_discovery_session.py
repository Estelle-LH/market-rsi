#!/usr/bin/env python3
"""Prepare one permanent GLM objective-discovery session without dispatching it."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from market_rsi import canonical, digest, fresh_json, identifier
from objective_discovery_workspace import prepare_workspace
from paid_budget import PaidBudget


def prepare(
    output: Path,
    *,
    source: Path,
    train_dates: list[str],
    budget_path: Path,
    budget_bucket: str,
    env_file: Path,
    tokenizer_cache: Path,
    runtime_python: Path,
    evidence_class: str,
) -> dict:
    output = Path(output).resolve()
    identifier(output.name)
    runtime_python = Path(os.path.abspath(runtime_python))
    source = Path(source).resolve()
    env_file = Path(env_file).resolve()
    tokenizer_cache = Path(tokenizer_cache).resolve()
    if (not runtime_python.is_file() or not os.access(runtime_python, os.X_OK)
            or env_file.is_symlink() or not env_file.is_file()
            or tokenizer_cache.is_symlink() or not tokenizer_cache.is_dir()):
        raise ValueError("verified runtime, environment and tokenizer cache required")
    budget = PaidBudget(Path(budget_path).resolve())
    snapshot = budget.snapshot()
    if budget_bucket not in snapshot["buckets"]:
        raise ValueError("unknown objective-discovery budget bucket")
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    workspace = output / "workspace"
    session = output / "session"
    manifest = prepare_workspace(
        workspace,
        session_id=output.name,
        experiment_id=snapshot["experiment_id"],
        source_path=source,
        opened_train_utc_dates=train_dates,
        evidence_class=evidence_class,
    )
    prompt = (
        "Choose and freeze one forecasting objective using only the already-open Train "
        "evidence available through your tools. First inspect the actual source inventory "
        "and run the automatic time-series diagnostics. Profile cadence and at least one "
        "target, search relevant public literature, and inspect the non-exhaustive objective "
        "families. Write at least two scientifically distinct proposals when executable "
        "Train evidence permits, audit each proposal, and compare their stability. Choose "
        "the first objective you can justify from causal availability, coverage, target "
        "scale, baseline difficulty and nearby-definition stability. If a desired objective "
        "needs a missing data stream or materializer, record that as a failed proposal and "
        "select only an executable audited alternative. Submit one final objective decision "
        "and exit. Do not request or create Dev, do not evaluate any model, and do not assume "
        "that a small raw error means the objective is useful."
    )
    (output / "prompt.txt").write_text(prompt, encoding="utf-8")
    command = [
        str(runtime_python), str(Path(__file__).with_name("run_codex_glm_controller.py")),
        "--session-id", output.name,
        "--output", str(session),
        "--workspace", str(workspace),
        "--prompt", str(output / "prompt.txt"),
        "--budget", str(Path(budget_path).resolve()),
        "--budget-bucket", budget_bucket,
        "--env-file", str(env_file),
        "--tokenizer-cache", str(tokenizer_cache),
        "--tool-mode", "canary",
        "--controller-stage", "objective",
        "--require-all-tools",
    ]
    receipt = {
        "schema": "market_objective_discovery_preparation_v1",
        "session_id": output.name,
        "experiment_id": snapshot["experiment_id"],
        "evidence_class": evidence_class,
        "workspace_manifest_sha256": digest(manifest),
        "source_sha256": manifest["source_sha256"],
        "train_dates": train_dates,
        "dev_created": False,
        "future_test_opened": False,
        "model_improvement_started": False,
        "model_calls": 0,
        "command": command,
        "runtime_python": str(runtime_python),
        "runtime_python_sha256": hashlib.sha256(runtime_python.read_bytes()).hexdigest(),
    }
    fresh_json(output / "preparation.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--train-date", action="append", required=True)
    parser.add_argument("--budget", required=True, type=Path)
    parser.add_argument("--budget-bucket", default="setup")
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--tokenizer-cache", required=True, type=Path)
    parser.add_argument("--runtime-python", required=True, type=Path)
    parser.add_argument("--evidence-class", choices=("diagnostic", "formal_learning"),
                        default="diagnostic")
    args = parser.parse_args()
    result = prepare(
        args.output, source=args.source, train_dates=args.train_date,
        budget_path=args.budget, budget_bucket=args.budget_bucket,
        env_file=args.env_file, tokenizer_cache=args.tokenizer_cache,
        runtime_python=args.runtime_python, evidence_class=args.evidence_class,
    )
    print(canonical(result))


if __name__ == "__main__":
    main()
