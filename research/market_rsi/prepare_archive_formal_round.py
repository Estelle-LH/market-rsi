#!/usr/bin/env python3
"""Prepare one paid Archive self-improvement round without dispatching it.

Round 1 creates the permanent prospective lifecycle, freezes the fixed H0
Codex harness, the policy-bound Transfer commitment, and the A0 persistence
submission.  Later rounds require the exact verified Archive history produced
by prior rounds.  Preparation is local and unpaid.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path

from archive_snapshot import empty_history, validate_history
from controller_harness_contract import (ALLOWED_TOOLS, build_contract,
                                         validate_contract)
from controller_provenance import freeze_source_manifest, validate_source_manifest
from controller_workspace import prepare_workspace
from formal_round_binding import freeze_binding, validate_data_root
from harness_evolution import baseline_profile, validate_profile
from market_rsi import canonical, digest, file_hash, fresh_json, identifier
from objective_contract import validate_objective_contract
from paid_budget import PaidBudget
from literature_catalog import literature_snapshot
from prospective_data_lifecycle import ProspectiveDataLifecycle


SCHEMA = "market_archive_formal_study_v1"
PREPARATION_SCHEMA = "market_archive_formal_round_preparation_v1"
A0_SOURCE = """def fit(train_rows, feature_names):
    return None


def predict(model, public_row):
    return public_row[\"features\"][\"mid\"]
"""


def _json(path: Path, maximum: int = 16 * 1024 * 1024):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("missing, symlinked or oversized formal-study input")
    return json.loads(path.read_bytes())


def _runtime(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("executable controller Python runtime required")
    return path


def _profile_sha256(profile: dict) -> str:
    return hashlib.sha256((canonical(profile) + "\n").encode()).hexdigest()


def _create_study(study: Path, data_root: Path, budget: PaidBudget,
                  objective_contract_path: Path,
                  seed_candidate_path: Path | None = None) -> tuple[dict, dict]:
    data = validate_data_root(data_root)
    budget_state = budget.snapshot()
    experiment_id = data["receipt"]["experiment_id"]
    if budget_state["experiment_id"] != experiment_id:
        raise ValueError("formal data and paid budget use different experiment IDs")
    if Decimal(budget_state["buckets"]["learning"]["available_usd"]) <= 0:
        raise ValueError("formal learning budget is not available")
    objective = validate_objective_contract(
        _json(Path(objective_contract_path)), experiment_id=experiment_id
    )
    if objective["selection"]["evidence_class"] != "formal_learning":
        raise ValueError("formal study requires a formal objective selection")
    data_objective_id = data["receipt"].get("objective_id")
    data_objective_sha256 = data["receipt"].get("objective_contract_sha256")
    if ((data_objective_id is None) != (data_objective_sha256 is None)
            or (data_objective_id is not None
                and (data_objective_id != objective["objective_id"]
                     or data_objective_sha256
                     != objective["objective_contract_sha256"]))):
        raise ValueError("formal data is bound to a different objective contract")

    study.mkdir(parents=True, mode=0o700, exist_ok=False)
    fresh_json(study / "objective-contract.json", objective)
    source_manifest = freeze_source_manifest(study / "source-manifest.json")
    source_manifest_sha256 = digest(source_manifest)
    profile = baseline_profile(ALLOWED_TOOLS)
    profile_sha256 = _profile_sha256(profile)
    lifecycle = ProspectiveDataLifecycle.create(
        study / "lifecycle", experiment_id=experiment_id,
        rounds=data["rounds"],
        transfer_policy_sha256=data["receipt"]["transfer_policy_sha256"])
    history = empty_history(lineage_id=study.name,
                            harness_profile_sha256=profile_sha256,
                            source_manifest_sha256=source_manifest_sha256)
    fresh_json(study / "initial-history.json", history)
    fresh_json(study / "harness-profile.json", profile)
    fresh_json(study / "transfer-policy.json", data["transfer_policy"])
    contract = build_contract(
        experiment_id=experiment_id,
        opaque_test_commitment=data["receipt"]["transfer_policy_sha256"],
        objective_contract=objective)
    fresh_json(study / "harness-contract.json", contract)

    submissions = study / "submissions"
    submissions.mkdir(mode=0o700)
    baseline = submissions / "a0-persistence.py"
    if seed_candidate_path is None:
        baseline_source = A0_SOURCE
        baseline_origin = "predeclared-persistence-baseline"
    else:
        seed_candidate_path = Path(seed_candidate_path).resolve()
        if (seed_candidate_path.is_symlink() or not seed_candidate_path.is_file()
                or seed_candidate_path.stat().st_size > 131_072):
            raise ValueError("regular bounded continuation seed required")
        baseline_source = seed_candidate_path.read_text(encoding="utf-8")
        if "def fit(" not in baseline_source or "def predict(" not in baseline_source:
            raise ValueError("continuation seed lacks candidate interface")
        baseline_origin = "validated-prior-study-seed"
    baseline.write_text(baseline_source, encoding="utf-8")
    a0 = {
        "schema": "market_archive_transfer_submission_v1",
        "submission_id": "a0",
        "origin": baseline_origin,
        "candidate_path": str(baseline.resolve()),
        "candidate_sha256": file_hash(baseline),
        "selected_before_learning": True,
        "transfer_opened": False,
    }
    fresh_json(submissions / "a0.json", a0)
    claim = {
        "schema": SCHEMA,
        "study_id": study.name,
        "experiment_id": experiment_id,
        "data_root": str(data["root"]),
        "data_receipt_sha256": digest(data["receipt"]),
        "source_manifest_sha256": source_manifest_sha256,
        "harness_profile_sha256": profile_sha256,
        "harness_contract_sha256": digest(contract),
        "objective_contract_sha256": objective["objective_contract_sha256"],
        "lifecycle_root": str(lifecycle.root),
        "lifecycle_manifest_sha256": digest(lifecycle._manifest()),
        "learning_round_ids": [item["round_id"] for item in data["rounds"]],
        "transfer_policy_sha256": data["receipt"]["transfer_policy_sha256"],
        "transfer_content_materialized": False,
        "a0_submission_sha256": digest(a0),
        "controller_model": contract["controller"]["model"],
        "harness": "codex-h0",
        "automatic_resampling": 0,
        "future_test_used": False,
    }
    fresh_json(study / "study-claim.json", claim)
    (study / "rounds").mkdir(mode=0o700)
    return claim, history


def _validate_study(study: Path, data_root: Path, budget: PaidBudget) -> dict:
    claim = _json(study / "study-claim.json")
    if (not isinstance(claim, dict) or claim.get("schema") != SCHEMA
            or claim.get("study_id") != study.name
            or claim.get("data_root") != str(Path(data_root).resolve())
            or claim.get("future_test_used") is not False
            or claim.get("automatic_resampling") != 0):
        raise ValueError("formal study claim changed")
    data = validate_data_root(data_root)
    source_manifest = validate_source_manifest(study / "source-manifest.json")
    profile = _json(study / "harness-profile.json")
    contract = _json(study / "harness-contract.json")
    objective = validate_objective_contract(
        _json(study / "objective-contract.json"),
        experiment_id=claim["experiment_id"],
    )
    data_objective_id = data["receipt"].get("objective_id")
    data_objective_sha256 = data["receipt"].get("objective_contract_sha256")
    if ((data_objective_id is None) != (data_objective_sha256 is None)
            or (data_objective_id is not None
                and (data_objective_id != objective["objective_id"]
                     or data_objective_sha256
                     != objective["objective_contract_sha256"]))):
        raise ValueError("formal data is bound to a different objective contract")
    a0 = _json(study / "submissions/a0.json")
    lifecycle = ProspectiveDataLifecycle(study / "lifecycle")
    validate_profile(profile, allowed_tools=ALLOWED_TOOLS)
    validate_contract(contract)
    if (set(a0) != {"schema", "submission_id", "origin", "candidate_path",
                    "candidate_sha256", "selected_before_learning",
                    "transfer_opened"}
            or a0["schema"] != "market_archive_transfer_submission_v1"
            or a0["submission_id"] != "a0"
            or a0["selected_before_learning"] is not True
            or a0["transfer_opened"] is not False
            or claim["experiment_id"] != budget.snapshot()["experiment_id"]
            or claim["experiment_id"] != data["receipt"]["experiment_id"]
            or claim["data_receipt_sha256"] != digest(data["receipt"])
            or claim["source_manifest_sha256"] != digest(source_manifest)
            or claim["harness_profile_sha256"] != _profile_sha256(profile)
            or claim["harness_contract_sha256"] != digest(contract)
            or claim.get("objective_contract_sha256")
            != objective["objective_contract_sha256"]
            or contract["evidence_policy"]["objective_contract"] != objective
            or claim["lifecycle_root"] != str(lifecycle.root)
            or claim["lifecycle_manifest_sha256"] != digest(lifecycle._manifest())
            or claim["transfer_policy_sha256"]
            != data["receipt"]["transfer_policy_sha256"]
            or claim["a0_submission_sha256"] != digest(a0)
            or file_hash(Path(a0["candidate_path"])) != a0["candidate_sha256"]):
        raise ValueError("formal study source, data, lifecycle, or A0 changed")
    return claim


def _history_for_round(study: Path, round_index: int,
                       history_path: Path | None) -> dict:
    expected = study / "initial-history.json" if round_index == 0 else history_path
    if expected is None:
        raise ValueError("later formal round requires exact prior Archive history")
    history = _json(Path(expected), 1_048_576)
    checked = validate_history(history)
    if (checked.get("legacy_empty") or checked["snapshots"] != round_index
            or history["lineage_id"] != study.name):
        raise ValueError("Archive history does not match formal round index")
    claim = _json(study / "study-claim.json")
    if (history["harness_profile_sha256"] != claim["harness_profile_sha256"]
            or history["source_manifest_sha256"] != claim["source_manifest_sha256"]):
        raise ValueError("Archive history belongs to a different frozen H0")
    return history


def prepare(study: Path, data_root: Path, budget_path: Path, env_file: Path,
            tokenizer_cache: Path, runtime_python: Path, round_id: str,
            history_path: Path | None = None,
            seed_candidate_path: Path | None = None,
            objective_contract_path: Path | None = None) -> dict:
    study = Path(study).resolve()
    data_root = Path(data_root).resolve()
    budget_path = Path(budget_path).resolve()
    env_file = Path(env_file).resolve()
    tokenizer_cache = Path(tokenizer_cache).resolve()
    runtime_python = _runtime(runtime_python)
    if (env_file.is_symlink() or not env_file.is_file()
            or tokenizer_cache.is_symlink() or not tokenizer_cache.is_dir()):
        raise ValueError("regular env file and tokenizer-cache directory required")
    identifier(study.name); identifier(round_id)
    data = validate_data_root(data_root)
    round_ids = [item["round_id"] for item in data["rounds"]]
    if round_id not in round_ids:
        raise ValueError("round not in frozen formal learning schedule")
    round_index = round_ids.index(round_id)
    budget = PaidBudget(budget_path)
    if round_index == 0:
        if study.exists():
            raise ValueError("fresh formal study root required for Round 1")
        if objective_contract_path is None:
            raise ValueError("Round 1 requires an objective frozen before Dev scheduling")
        claim, history = _create_study(study, data_root, budget,
                                       objective_contract_path,
                                       seed_candidate_path=seed_candidate_path)
    else:
        if objective_contract_path is not None:
            raise ValueError("objective cannot change inside a study lineage")
        if seed_candidate_path is not None:
            raise ValueError("continuation seed is allowed only when creating a study")
        if not study.is_dir():
            raise ValueError("existing formal study required for later round")
        claim = _validate_study(study, data_root, budget)
        history = _history_for_round(study, round_index, history_path)
    if round_index == 0:
        history = _history_for_round(study, round_index, None)

    lifecycle = ProspectiveDataLifecycle(study / "lifecycle")
    audit = lifecycle.audit()
    if len(audit["completed_rounds"]) != round_index or audit["active_dev_claim"] is not None:
        raise ValueError("formal lifecycle is not ready for requested round")
    contract = _json(study / "harness-contract.json")
    atomic_upper_usd = Decimal(
        contract["research_budget"]["worst_case_controller_usd"]) + Decimal("0.40")
    available = Decimal(budget.snapshot()["buckets"]["learning"]["available_usd"])
    if atomic_upper_usd > available:
        raise ValueError("formal round hard upper exceeds remaining learning budget")
    output = study / "rounds" / round_id
    output.mkdir(mode=0o700, exist_ok=False)
    binding = freeze_binding(output / "round-binding.json", data_root,
                             lifecycle.root, round_id)
    binding_path = output / "round-binding.json"
    binding_sha256 = file_hash(binding_path)
    session_id = f"{study.name}-{round_id}"
    workspace = output / "workspace"
    session = output / "session"
    profile = _json(study / "harness-profile.json")
    workspace_manifest = prepare_workspace(
        workspace, session_id=session_id, experiment_id=claim["experiment_id"],
        task_id=binding["task_id"], arm="archive-self-improvement",
        train_path=Path(binding["train_path"]), dev_path=Path(binding["dev_path"]),
        own_history=history, literature_snapshot=literature_snapshot(),
        opaque_test_commitment=claim["transfer_policy_sha256"],
        objective_contract=contract["evidence_policy"]["objective_contract"],
        harness_profile=profile)
    runner_config = {
        "schema": "market_controller_runner_v1",
        "session_id": session_id,
        "experiment_id": claim["experiment_id"],
        "task_id": binding["task_id"],
        "train_path": binding["train_path"],
        "train_sha256": binding["train_sha256"],
        "budget_path": str(budget_path),
        "env_file": str(env_file),
        "budget_bucket": "learning",
        "evidence_class": "formal_learning",
        "round_binding_path": str(binding_path.resolve()),
        "round_binding_sha256": binding_sha256,
        "objective_contract_path": str((study / "objective-contract.json").resolve()),
        "objective_contract_sha256": claim["objective_contract_sha256"],
    }
    fresh_json(output / "runner-config.json", runner_config)
    prompt = (
        f"This is {round_id} of the fixed-H0 Archive self-improvement study. Work as the "
        "research controller and choose the research path yourself. First read the frozen "
        "objective contract; you may not change its target, horizon, baseline or score. You can inspect all open "
        "Train labels, the current label-free Dev features, the full Archive from earlier "
        "rounds, the algorithm catalog, and frozen public literature. You may use, combine, "
        "modify, or invent methods; the catalog is not exhaustive and the guide is not a fixed "
        "workflow. Every literature query, algorithm inspection, candidate, execution, failure, "
        "cost, and decision is archived. Candidate files must be new flat lowercase .py files "
        "defining fit(train_rows, feature_names) and predict(model, public_row), with predictions "
        "in [0,1]. You have at most three runner-owned Train-CV executions. Current Dev labels "
        "remain sealed and will be scored exactly once only after you submit one executed "
        "candidate and exit. The score becomes visible only in the next round Archive. Future "
        "Transfer data is unavailable. Read whatever evidence you judge useful, form a testable "
        "hypothesis, and inspect the opened-Train population audit: rows are autocorrelated and "
        "must not be treated as independent samples. You may rebalance opened Train using a "
        "causal activity rule or capped Train-label weights, but the runner always evaluates the "
        "unweighted predeclared population and never filters Dev by its future movement. Preserve "
        "ancestry when using an Archive candidate, and submit exactly one "
        "decision. Do not ask the outer operator to choose the method for you."
    )
    (output / "prompt.txt").write_text(prompt, encoding="utf-8")
    controller_command = [
        str(runtime_python), str(Path(__file__).with_name("run_codex_glm_controller.py")),
        "--session-id", session_id, "--output", str(session),
        "--workspace", str(workspace), "--prompt", str(output / "prompt.txt"),
        "--budget", str(budget_path), "--budget-bucket", "learning",
        "--env-file", str(env_file), "--tokenizer-cache", str(tokenizer_cache),
        "--tool-mode", "formal", "--runner-config", str(output / "runner-config.json"),
        "--source-manifest", str(study / "source-manifest.json"),
    ]
    sealed_config = {
        "schema": "market_controller_sealed_dev_runner_v1",
        "session_id": session_id,
        "experiment_id": claim["experiment_id"],
        "task_id": binding["task_id"],
        "train_path": binding["train_path"],
        "train_sha256": binding["train_sha256"],
        "dev_path": binding["dev_path"],
        "dev_sha256": binding["dev_sha256"],
        "lifecycle_root": str(lifecycle.root),
        "round_id": round_id,
        "controller_view_sha256": binding["controller_view_sha256"],
        "train_dataset_ids": [item["dataset_id"]
                              for item in binding["controller_view"]["train_full_access"]],
        "dev_dataset_ids": [item["dataset_id"]
                            for item in binding["controller_view"]["dev_feature_only"]],
        "session_assessment_path": str(session / "assessment.json"),
        "budget_path": str(budget_path),
        "env_file": str(env_file),
        "budget_bucket": "learning",
        "evidence_class": "formal_learning",
        "round_binding_path": str(binding_path.resolve()),
        "round_binding_sha256": binding_sha256,
        "objective_contract_path": str((study / "objective-contract.json").resolve()),
        "objective_contract_sha256": claim["objective_contract_sha256"],
    }
    fresh_json(output / "sealed-dev-config.json", sealed_config)
    sealed_output = output / "sealed-dev"
    sealed_command = [
        str(runtime_python), str(Path(__file__).with_name(
            "prospective_sealed_dev_runner.py")),
        "--workspace", str(workspace), "--config", str(output / "sealed-dev-config.json"),
        "--output", str(sealed_output),
    ]
    preparation = {
        "schema": PREPARATION_SCHEMA,
        "study_id": study.name,
        "session_id": session_id,
        "experiment_id": claim["experiment_id"],
        "round_id": round_id,
        "round_index": round_index,
        "workspace_manifest_sha256": digest(workspace_manifest),
        "round_binding_sha256": binding_sha256,
        "runner_config_sha256": digest(runner_config),
        "sealed_dev_config_sha256": digest(sealed_config),
        "archive_history_sha256": digest(history),
        "source_manifest_sha256": claim["source_manifest_sha256"],
        "objective_contract_sha256": claim["objective_contract_sha256"],
        "controller_command": controller_command,
        "sealed_dev_command": sealed_command,
        "budget_before_dispatch": budget.snapshot(),
        "atomic_round_upper_usd": str(atomic_upper_usd),
        "model_calls": 0,
        "candidate_executions": 0,
        "dev_executions": 0,
        "automatic_resampling": 0,
        "future_test_used": False,
    }
    fresh_json(output / "preparation.json", preparation)
    return preparation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--budget", required=True, type=Path)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--tokenizer-cache", required=True, type=Path)
    parser.add_argument("--runtime-python", required=True, type=Path)
    parser.add_argument("--round-id", required=True)
    parser.add_argument("--history", type=Path)
    parser.add_argument("--seed-candidate", type=Path)
    parser.add_argument("--objective-contract", type=Path)
    args = parser.parse_args()
    print(canonical(prepare(args.study, args.data_root, args.budget, args.env_file,
                            args.tokenizer_cache, args.runtime_python, args.round_id,
                            args.history, args.seed_candidate, args.objective_contract)))


if __name__ == "__main__":
    main()
