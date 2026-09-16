#!/usr/bin/env python3
"""Prepare one permanent GLM data-research session without dispatching it."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

from data_discovery_workspace import prepare_workspace
from market_rsi import canonical, digest, fresh_json, identifier
from paid_budget import PaidBudget


def prepare(output: Path, *, source: Path, train_dates: list[str], budget_path: Path,
            budget_bucket: str, env_file: Path, tokenizer_cache: Path,
            runtime_python: Path, source_canary_report: Path | None = None) -> dict:
    output = Path(output).resolve()
    identifier(output.name)
    runtime_python = Path(os.path.abspath(runtime_python))
    env_file = Path(env_file).resolve()
    tokenizer_cache = Path(tokenizer_cache).resolve()
    if (not runtime_python.is_file() or not os.access(runtime_python, os.X_OK)
            or env_file.is_symlink() or not env_file.is_file()
            or tokenizer_cache.is_symlink() or not tokenizer_cache.is_dir()):
        raise ValueError("verified runtime, environment and tokenizer cache required")
    budget = PaidBudget(Path(budget_path).resolve())
    snapshot = budget.snapshot()
    if budget_bucket not in snapshot["buckets"]:
        raise ValueError("unknown data-discovery budget bucket")
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    manifest = prepare_workspace(
        output / "workspace", session_id=output.name,
        experiment_id=snapshot["experiment_id"],
        current_source_path=Path(source).resolve(),
        opened_train_utc_dates=train_dates,
        source_canary_report=source_canary_report,
    )
    prompt = (
        "Research and freeze the next data acquisition plan. Inspect the current data audit. "
        "If bounded source-canary evidence is present, inspect it first and treat every failed "
        "check and rejection reason as binding evidence rather than repeating the failed plan. "
        "Research the available real historical sources and relevant literature. Create at "
        "least two plans, audit both, and compare them. Prefer real historical data. The "
        "simulator is not a primary data source. Resolve terms and reuse before requesting any "
        "source market data. Specify independent days/markets, required "
        "streams, resource caps, a small source canary, separate canary and full-ingest "
        "acceptance tests, and rejection "
        "conditions. Select one plan, submit it once, and exit. Do not choose an objective, "
        "open Dev or Future Test, or request a full download."
    )
    (output / "prompt.txt").write_text(prompt, encoding="utf-8")
    command = [
        str(runtime_python), str(Path(__file__).with_name("run_codex_glm_controller.py")),
        "--session-id", output.name, "--output", str(output / "session"),
        "--workspace", str(output / "workspace"), "--prompt", str(output / "prompt.txt"),
        "--budget", str(Path(budget_path).resolve()), "--budget-bucket", budget_bucket,
        "--env-file", str(env_file), "--tokenizer-cache", str(tokenizer_cache),
        "--tool-mode", "canary", "--controller-stage", "data",
    ]
    receipt = {"schema": "market_data_discovery_preparation_v1",
               "session_id": output.name, "experiment_id": snapshot["experiment_id"],
               "workspace_manifest_sha256": digest(manifest),
               "current_source_sha256": manifest["current_source_sha256"],
               "train_dates": train_dates, "dev_created": False,
               "future_test_opened": False, "objective_selected": False,
               "full_download_started": False, "command": command,
               "runtime_python": str(runtime_python),
               "runtime_python_sha256": hashlib.sha256(runtime_python.read_bytes()).hexdigest()}
    fresh_json(output / "preparation.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--train-date", action="append", required=True)
    parser.add_argument("--budget", required=True, type=Path)
    parser.add_argument("--budget-bucket", default="setup")
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--tokenizer-cache", required=True, type=Path)
    parser.add_argument("--runtime-python", required=True, type=Path)
    parser.add_argument("--source-canary-report", type=Path)
    args = parser.parse_args()
    print(canonical(prepare(args.output, source=args.source, train_dates=args.train_date,
                            budget_path=args.budget, budget_bucket=args.budget_bucket,
                            env_file=args.env_file, tokenizer_cache=args.tokenizer_cache,
                            runtime_python=args.runtime_python,
                            source_canary_report=args.source_canary_report)))


if __name__ == "__main__":
    main()
