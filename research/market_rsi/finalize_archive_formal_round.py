#!/usr/bin/env python3
"""Finalize one formal learning round into Archive and a frozen submission.

This runs only after the permanent controller session and its one-shot Dev
evaluation both finish.  It does not call a model, execute a sandbox, open
Transfer, or change the selected candidate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from archive_snapshot import (append_snapshot, build_snapshot, validate_history)
from controller_provenance import validate_source_manifest
from formal_round_binding import validate_data_root
from market_rsi import canonical, digest, file_hash, fresh_json, identifier
from prepare_archive_formal_round import PREPARATION_SCHEMA, SCHEMA as STUDY_SCHEMA
from prospective_data_lifecycle import ProspectiveDataLifecycle


SCHEMA = "market_archive_formal_round_finalization_v1"


def _json(path: Path, maximum: int = 16 * 1024 * 1024):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("missing, symlinked or oversized finalization input")
    return json.loads(path.read_bytes())


def finalize(study: Path, round_id: str, history_path: Path | None = None) -> dict:
    study = Path(study).resolve()
    identifier(study.name); identifier(round_id)
    claim = _json(study / "study-claim.json")
    if claim.get("schema") != STUDY_SCHEMA or claim.get("study_id") != study.name:
        raise ValueError("formal study claim changed")
    validate_source_manifest(study / "source-manifest.json")
    data = validate_data_root(Path(claim["data_root"]))
    round_ids = [item["round_id"] for item in data["rounds"]]
    if round_id not in round_ids:
        raise ValueError("round not in frozen study")
    round_index = round_ids.index(round_id)
    root = study / "rounds" / round_id
    if (root / "finalization.json").exists():
        raise ValueError("formal round already finalized")
    preparation = _json(root / "preparation.json")
    if (preparation.get("schema") != PREPARATION_SCHEMA
            or preparation.get("study_id") != study.name
            or preparation.get("round_id") != round_id
            or preparation.get("round_index") != round_index
            or preparation.get("source_manifest_sha256")
            != claim["source_manifest_sha256"]):
        raise ValueError("formal round preparation changed")
    binding_raw = (root / "round-binding.json").read_bytes()
    if hashlib.sha256(binding_raw).hexdigest() != preparation["round_binding_sha256"]:
        raise ValueError("formal round binding changed")
    for name, field in (("runner-config.json", "runner_config_sha256"),
                        ("sealed-dev-config.json", "sealed_dev_config_sha256")):
        if digest(_json(root / name)) != preparation[field]:
            raise ValueError("formal runner config changed")

    history_file = (study / "initial-history.json"
                    if round_index == 0 else Path(history_path) if history_path else None)
    if history_file is None:
        raise ValueError("later round finalization requires its exact input Archive history")
    history = _json(history_file, 1_048_576)
    checked_history = validate_history(history)
    if (checked_history.get("legacy_empty") or checked_history["snapshots"] != round_index
            or history["lineage_id"] != study.name
            or digest(history) != preparation["archive_history_sha256"]):
        raise ValueError("finalization Archive differs from round input")

    assessment = _json(root / "session/assessment.json", 32 * 1024 * 1024)
    if (assessment.get("valid") is not True
            or assessment.get("process_reaped") is not True
            or assessment.get("submitted_decision_present") is not True
            or assessment.get("source_manifest")
            != _json(study / "source-manifest.json")):
        raise ValueError("formal controller session did not finish validly")
    sealed = _json(root / "workspace/sealed-dev-result.json", 8 * 1024 * 1024)
    if (sealed.get("schema") != "market_controller_prospective_sealed_dev_outcome_v2"
            or sealed.get("round_id") != round_id
            or sealed.get("future_test_used") is not False
            or sealed.get("controller_integrity", {}).get("valid") is not True
            or sealed.get("predictor_validity", {}).get("valid") is not True):
        raise ValueError("formal one-shot Dev outcome missing")
    lifecycle = ProspectiveDataLifecycle(study / "lifecycle")
    audit = lifecycle.audit()
    if (len(audit["completed_rounds"]) != round_index + 1
            or audit["completed_rounds"][-1] != round_id
            or audit["active_dev_claim"] is not None
            or audit["transfer_scored"] is not False):
        raise ValueError("formal lifecycle did not complete exactly this round")

    previous = (history["snapshots"][-1]["snapshot_sha256"]
                if history["snapshots"] else None)
    snapshot = build_snapshot(
        root / "archive-snapshot.json", workspace=root / "workspace",
        session_output=root / "session", prompt_path=root / "prompt.txt",
        source_manifest_path=study / "source-manifest.json",
        lineage_id=study.name, round_index=round_index,
        previous_snapshot_sha256=previous)
    updated = append_snapshot(history, snapshot)
    fresh_json(root / "archive-history.json", updated)

    selected_name = snapshot["decision"]["candidate_artifact"]
    selected = next(item for item in snapshot["candidates"]
                    if item["candidate"] == selected_name)
    submission_id = f"a{round_index + 1}"
    submission_source = study / "submissions" / f"{submission_id}-candidate.py"
    submission_source.write_text(selected["source"], encoding="utf-8")
    submission = {
        "schema": "market_archive_transfer_submission_v1",
        "submission_id": submission_id,
        "origin": "formal-archive-round-selection",
        "round_id": round_id,
        "archive_snapshot_sha256": digest(snapshot),
        "candidate_name": selected_name,
        "candidate_path": str(submission_source.resolve()),
        "candidate_sha256": file_hash(submission_source),
        "dev_score_receipt_sha256": sealed["score_receipt_sha256"],
        "transfer_opened": False,
    }
    fresh_json(study / "submissions" / f"{submission_id}.json", submission)
    receipt = {
        "schema": SCHEMA,
        "study_id": study.name,
        "round_id": round_id,
        "round_index": round_index,
        "session_id": preparation["session_id"],
        "snapshot_sha256": digest(snapshot),
        "archive_history_sha256": digest(updated),
        "submission_id": submission_id,
        "submission_sha256": digest(submission),
        "lifecycle_audit": audit,
        "controller_metered_cost_usd": snapshot["metered_controller_usd"],
        "controller_integrity": sealed["controller_integrity"],
        "predictor_validity": sealed["predictor_validity"],
        "lineage_eligible": True,
        "future_test_used": False,
        "model_calls": 0,
        "sandbox_executions": 0,
    }
    fresh_json(root / "finalization.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", required=True, type=Path)
    parser.add_argument("--round-id", required=True)
    parser.add_argument("--history", type=Path)
    args = parser.parse_args()
    print(canonical(finalize(args.study, args.round_id, args.history)))
