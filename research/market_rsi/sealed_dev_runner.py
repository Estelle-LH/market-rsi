#!/usr/bin/env python3
"""Run one controller-frozen candidate once on the current sealed Dev block.

This process starts only after the controller session has exited.  It binds the
selected source to the append-only data lifecycle, executes exactly once, and
publishes the outcome only for the next Archive snapshot.  It never accepts a
Transfer path and never returns a score to the completed controller session.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from controller_activity_log import assess_activity_logs
from controller_candidate_harbor import (
    prepare_sealed_dev_job,
    run_job,
    verify_candidate_failure,
)
from controller_workspace import validate_workspace
from data_lifecycle import DataLifecycle
from market_rsi import canonical, digest, fresh_json, identifier
from objective_contract import validate_objective_contract


SCHEMA = "market_controller_sealed_dev_runner_v1"
OUTCOME_SCHEMA = "market_controller_sealed_dev_outcome_v1"


def _json(path: Path, maximum: int = 2 * 1024 * 1024):
    return json.loads(_regular(path, maximum))


def _regular(path: Path, maximum: int) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("missing, symlinked or oversized sealed Dev input")
    return path.read_bytes()


def _validate_config(path: Path, workspace: Path, lifecycle_class) -> tuple[dict, dict]:
    config = _json(path)
    manifest = validate_workspace(workspace)
    required = {
        "schema", "session_id", "experiment_id", "task_id", "train_path",
        "train_sha256", "dev_path", "dev_sha256", "lifecycle_root", "round_id",
        "controller_view_sha256", "train_dataset_ids", "dev_dataset_ids",
        "session_assessment_path", "budget_path", "env_file", "budget_bucket",
        "evidence_class",
    }
    evidence_class = config.get("evidence_class") if isinstance(config, dict) else None
    if evidence_class == "formal_learning":
        required |= {"round_binding_path", "round_binding_sha256",
                     "objective_contract_path", "objective_contract_sha256"}
    if (
        not isinstance(config, dict)
        or set(config) != required
        or config["schema"] != SCHEMA
        or any(config[key] != manifest[key]
               for key in ("session_id", "experiment_id", "task_id"))
        or config["budget_bucket"] != "learning"
        or config["evidence_class"] not in {"diagnostic", "formal_learning"}
    ):
        raise ValueError("invalid sealed Dev runner config")
    for key in ("train_sha256", "dev_sha256", "controller_view_sha256",
                "objective_contract_sha256"):
        if key not in config:
            continue
        value = config[key]
        if (not isinstance(value, str) or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)):
            raise ValueError("sealed Dev commitment required")
    for key in (
        "train_path", "dev_path", "lifecycle_root", "session_assessment_path",
        "budget_path", "env_file",
    ):
        if not isinstance(config[key], str) or not Path(config[key]).is_absolute():
            raise ValueError("absolute trusted sealed Dev path required")
    if evidence_class == "formal_learning":
        objective_path = Path(config["objective_contract_path"])
        if (not objective_path.is_absolute() or objective_path.is_symlink()
                or not objective_path.is_file()):
            raise ValueError("formal objective contract changed before sealed Dev")
        objective = validate_objective_contract(
            _json(objective_path), experiment_id=config["experiment_id"]
        )
        if (objective["objective_contract_sha256"]
                != config["objective_contract_sha256"]):
            raise ValueError("formal objective contract changed before sealed Dev")
    identifier(config["round_id"])
    for key in ("train_dataset_ids", "dev_dataset_ids"):
        values = config[key]
        if (not isinstance(values, list) or not values
                or len(set(values)) != len(values)):
            raise ValueError("nonempty unique lifecycle dataset IDs required")
        for value in values:
            identifier(value)

    session = _json(Path(config["session_assessment_path"]), 16 * 1024 * 1024)
    if (session.get("valid") is not True or session.get("process_reaped") is not True
            or session.get("submitted_decision_present") is not True
            or session.get("controller_integrity", {}).get("valid") is not True):
        raise ValueError("controller must finish and exit before sealed Dev opens")

    lifecycle = lifecycle_class(Path(config["lifecycle_root"]))
    view = lifecycle.controller_view(config["round_id"])
    if digest(view) != config["controller_view_sha256"]:
        raise ValueError("controller view changed before sealed Dev claim")
    if ([item["dataset_id"] for item in view["train_full_access"]]
            != config["train_dataset_ids"]
            or [item["dataset_id"] for item in view["dev_feature_only"]]
            != config["dev_dataset_ids"]):
        raise ValueError("sealed Dev materialization differs from lifecycle")
    if evidence_class == "formal_learning":
        from formal_round_binding import validate_binding
        binding_path = Path(config["round_binding_path"])
        if (not binding_path.is_absolute()
                or hashlib.sha256(_regular(binding_path, 2 * 1024 * 1024)).hexdigest()
                != config["round_binding_sha256"]):
            raise ValueError("formal round binding hash changed")
        binding = validate_binding(binding_path)
        if (binding["experiment_id"] != config["experiment_id"]
                or binding["task_id"] != config["task_id"]
                or binding["round_id"] != config["round_id"]
                or binding["train_path"] != config["train_path"]
                or binding["train_sha256"] != config["train_sha256"]
                or binding["dev_path"] != config["dev_path"]
                or binding["dev_sha256"] != config["dev_sha256"]
                or binding["lifecycle_root"] != config["lifecycle_root"]
                or binding["controller_view_sha256"]
                != config["controller_view_sha256"]
                or (binding.get("objective_contract_sha256") is not None
                    and binding.get("objective_contract_sha256")
                    != config["objective_contract_sha256"])):
            raise ValueError("sealed Dev config differs from formal round binding")
    return config, view


def validate_config(path: Path, workspace: Path) -> tuple[dict, dict]:
    return _validate_config(path, workspace, DataLifecycle)


def _selected(workspace: Path) -> dict:
    activity = assess_activity_logs(workspace)
    decision = _json(Path(workspace) / "submitted-decision.json", 16_384)
    name = decision.get("candidate_artifact")
    if name != activity["selected_candidate"]:
        raise ValueError("selected candidate differs from activity ledger")
    source = _regular(Path(workspace) / name, 131_072)
    return {
        "candidate": name,
        "candidate_sha256": hashlib.sha256(source).hexdigest(),
        "decision_sha256": digest(decision),
        "controller_integrity": activity["controller_integrity"],
    }


async def _run_once(
    workspace: Path, config_path: Path, output: Path, *, lifecycle_class,
    outcome_schema: str,
) -> dict:
    workspace = Path(workspace).resolve()
    output = Path(output).resolve()
    identifier(output.name)
    if (workspace / "sealed-dev-result.json").exists():
        raise ValueError("sealed Dev result already exists for this controller session")
    if output.exists():
        raise ValueError("fresh sealed Dev output directory required")
    config, view = _validate_config(config_path, workspace, lifecycle_class)
    selected = _selected(workspace)
    candidate_set_sha256 = digest(selected)
    lifecycle = lifecycle_class(Path(config["lifecycle_root"]))
    claim = lifecycle.claim_dev_score(
        config["round_id"], candidate_set_sha256=candidate_set_sha256
    )

    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    execution_id = f"{config['session_id']}-{output.name}-execution"
    identifier(execution_id)
    request = {
        "schema": "market_controller_execution_request_v1",
        # The output basename repeats across studies. Bind the paid job to the
        # permanent controller session so budget IDs can never collide.
        "execution_id": execution_id,
        "session_id": config["session_id"],
        "experiment_id": config["experiment_id"],
        "task_id": config["task_id"],
        "candidate_name": selected["candidate"],
        "candidate_sha256": selected["candidate_sha256"],
        "workspace_manifest_sha256": digest(validate_workspace(workspace)),
        "evaluation_role": "sealed_dev",
        "automatic_retry": False,
    }
    job = output / request["execution_id"]
    try:
        job_claim = prepare_sealed_dev_job(request, workspace, config, job)
    except Exception as error:
        infrastructure = {
            "schema": "market_controller_sealed_dev_infrastructure_failure_v1",
            "round_id": config["round_id"],
            "candidate_set_sha256": candidate_set_sha256,
            "dev_claim": claim,
            "stage": "local_job_preparation",
            "error_type": type(error).__name__,
            "automatic_retry": False,
            "provider_called": False,
            "dev_score_completed": False,
            "future_test_used": False,
        }
        fresh_json(output / "infrastructure-failure.json", infrastructure)
        raise RuntimeError(
            "sealed Dev local preflight failed; exact claim remains active and must not be resampled"
        ) from error
    try:
        score = await run_job(job, Path(config["budget_path"]), Path(config["env_file"]))
        if (score.get("evaluation_role") != "sealed_dev"
                or score.get("primary", {}).get("valid") is not True):
            raise ValueError("sealed Dev execution lacks a valid full-coverage score")
        scientific = {"status": "completed", "score": score, "failure": None}
    except Exception as error:
        try:
            failure = verify_candidate_failure(job)
        except Exception as verification_error:
            infrastructure = {
                "schema": "market_controller_sealed_dev_infrastructure_failure_v1",
                "round_id": config["round_id"],
                "candidate_set_sha256": candidate_set_sha256,
                "dev_claim": claim,
                "error_type": type(error).__name__,
                "verification_error_type": type(verification_error).__name__,
                "automatic_retry": False,
                "dev_score_completed": False,
                "future_test_used": False,
            }
            fresh_json(output / "infrastructure-failure.json", infrastructure)
            raise RuntimeError(
                "sealed Dev infrastructure failed; exact claim remains active and must not be resampled"
            ) from error
        scientific = {"status": "candidate_failed", "score": None, "failure": failure}

    score_receipt = {
        "schema": "market_controller_sealed_dev_score_receipt_v1",
        "round_id": config["round_id"],
        "candidate_set_sha256": candidate_set_sha256,
        "selected": selected,
        "controller_view_sha256": digest(view),
        "job_claim_sha256": digest(job_claim),
        "evaluation_role": "sealed_dev",
        "controller_session_already_exited": True,
        "score_visible_to_same_session": False,
        "future_test_used": False,
        **scientific,
    }
    predictor_validity = {
        "schema": "market_predictor_validity_assessment_v1",
        "valid": (
            scientific["status"] == "completed"
            and isinstance(scientific["score"], dict)
            and scientific["score"].get("primary", {}).get("valid") is True
            and scientific["score"].get("coverage", {}).get("coverage_fraction") == 1.0
        ),
        "status": scientific["status"],
        "full_coverage": (
            isinstance(scientific["score"], dict)
            and scientific["score"].get("coverage", {}).get("coverage_fraction") == 1.0
        ),
        "scientific_improvement_verified": False,
    }
    score_receipt["controller_integrity"] = selected["controller_integrity"]
    score_receipt["predictor_validity"] = predictor_validity
    fresh_json(output / "score-receipt.json", score_receipt)
    promotion = lifecycle.complete_dev_score(
        config["round_id"], score_receipt_sha256=digest(score_receipt)
    )
    outcome = {
        "schema": outcome_schema,
        "round_id": config["round_id"],
        "selected": selected,
        "dev_claim": claim,
        "score_receipt": score_receipt,
        "score_receipt_sha256": digest(score_receipt),
        "promotion": promotion,
        "lifecycle_audit": lifecycle.audit(),
        "controller_integrity": selected["controller_integrity"],
        "predictor_validity": predictor_validity,
        "visible_starting_next_archive": True,
        "future_test_used": False,
    }
    fresh_json(output / "outcome.json", outcome)
    fresh_json(workspace / "sealed-dev-result.json", outcome)
    return outcome


async def run_once(
    workspace: Path, config_path: Path, output: Path
) -> dict:
    return await _run_once(workspace, config_path, output,
                           lifecycle_class=DataLifecycle,
                           outcome_schema=OUTCOME_SCHEMA)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(canonical(asyncio.run(run_once(args.workspace, args.config, args.output))))
