"""Trusted, immutable admission receipt for a live market study.

This module does not decide whether collector source proves receipt-time
semantics. A trusted review must provide that conclusion with exact evidence
hashes. This module enforces that the reviewed evidence, data, study, scorer,
runtime, budget and deadline are unchanged whenever a paid stage starts.
Candidate code and research-model output cannot create or modify this receipt.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re

from market_rsi import digest, file_hash, fresh_json
from paid_budget import PaidBudget
from worker_receipts import read_regular


SCHEMA = "market_scientific_admission_v1"
EVIDENCE_KINDS = {"collector_source", "collector_runtime", "collector_session",
    "capture_manifest", "split_receipt", "materializer_receipt", "scorer_contract",
    "deadline_verification"}
CHECKS = {"collector_version_bound_to_capture", "receipt_clock_semantics_reviewed",
    "receipt_recorded_before_archive_write", "subscription_sequence_scope_reviewed",
    "reconnect_requires_fresh_snapshot", "whole_game_split_verified",
    "chronological_label_availability_verified", "train_dev_public_projection_verified",
    "scorer_contract_frozen", "candidate_isolation_verified",
    "end_to_end_deadline_verified", "provider_budget_bound"}
RECEIPT_KEYS = {"schema", "experiment_id", "created_at_utc", "deadline_utc",
    "evidence_class", "review_id", "reviewer_role", "checks", "evidence_files",
    "study_manifest_sha256", "runner_config_sha256", "task_data_sha256",
    "runtime_sha256", "coder_limits_sha256", "coder_identity_sha256",
    "worker_source_hashes_sha256", "budget_cap_usd", "test_set_opened",
    "external_results_seen", "scientific_admission"}
EVIDENCE_KEYS = {"kind", "path", "sha256"}
SHA = re.compile(r"[0-9a-f]{64}")


def _utc(value, name):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(name + " must be an ISO UTC timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError(name + " must be an ISO UTC timestamp")
    return parsed


def _sha(value, name):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError(name + " must be SHA-256")
    return value


def _evidence(receipt):
    entries = receipt["evidence_files"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("nonempty scientific evidence list required")
    kinds, seen = set(), set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != EVIDENCE_KEYS:
            raise ValueError("exact evidence file declaration required")
        kind, path = entry["kind"], Path(entry["path"]).absolute()
        if kind not in EVIDENCE_KINDS or str(path) in seen:
            raise ValueError("unknown evidence kind or duplicate path")
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("evidence must be a bounded regular file")
        if file_hash(path) != _sha(entry["sha256"], "evidence hash"):
            raise ValueError("scientific evidence changed")
        kinds.add(kind)
        seen.add(str(path))
    if not EVIDENCE_KINDS <= kinds:
        raise ValueError("every scientific evidence kind is required")


def validate_receipt(receipt, config, manifest, budget):
    if not isinstance(receipt, dict) or set(receipt) != RECEIPT_KEYS or receipt["schema"] != SCHEMA:
        raise ValueError("exact scientific admission receipt required")
    if (receipt["experiment_id"] != config["experiment_id"]
            or receipt["experiment_id"] != manifest["experiment_id"]
            or receipt["evidence_class"] != "reviewed_historical_source"
            or receipt["reviewer_role"] != "trusted_runner_reviewer"
            or not isinstance(receipt["review_id"], str) or not receipt["review_id"]):
        raise ValueError("admission ownership or review identity mismatch")
    created = _utc(receipt["created_at_utc"], "created_at_utc")
    deadline = _utc(receipt["deadline_utc"], "deadline_utc")
    if receipt["deadline_utc"] != manifest["deadline_utc"] or created >= deadline:
        raise ValueError("admission is outside the fixed study window")
    if (not isinstance(receipt["checks"], dict) or set(receipt["checks"]) != CHECKS
            or any(value is not True for value in receipt["checks"].values())):
        raise ValueError("all independent scientific admission checks must pass")
    if config.get("end_to_end_wall_enforcement_verified") is not True:
        raise ValueError("runner has not verified its end-to-end deadline enforcement")
    if (receipt["scientific_admission"] is not True or receipt["test_set_opened"] is not False
            or receipt["external_results_seen"] is not False):
        raise ValueError("admission cannot follow Test/results access")
    expected = {"study_manifest_sha256": digest(manifest),
        "runner_config_sha256": digest(config), "task_data_sha256": digest(config["task_data"]),
        "runtime_sha256": digest(config["runtime"]), "coder_limits_sha256": digest(config["coder_limits"]),
        "coder_identity_sha256": digest(config["coder_identity"]),
        "worker_source_hashes_sha256": digest(config["source_hashes"]),
        "budget_cap_usd": budget.snapshot()["cap_usd"]}
    for key, value in expected.items():
        if receipt[key] != value:
            raise ValueError("admission differs from frozen " + key)
    for key in expected:
        if key.endswith("sha256"):
            _sha(receipt[key], key)
    _evidence(receipt)
    return receipt


def _context(runner_root):
    runner_root = Path(runner_root).absolute()
    config = json.loads(read_regular(runner_root / "config.json"))
    commitment = json.loads(read_regular(runner_root / "config-commitment.json"))
    if config.get("schema") != "market_study_runner_v1" or commitment != {"sha256": digest(config)}:
        raise ValueError("runner configuration commitment changed")
    manifest = json.loads(read_regular(Path(config["study_path"]) / "manifest.json"))
    budget = PaidBudget(config["budget_path"])
    return runner_root, config, manifest, budget


def install_admission(runner_root, reviewed_receipt):
    """Install one reviewed receipt. Existing or partial installs never overwrite."""
    runner_root, config, manifest, budget = _context(runner_root)
    receipt = json.loads(read_regular(reviewed_receipt))
    validate_receipt(receipt, config, manifest, budget)
    deadline = _utc(manifest["deadline_utc"], "deadline_utc")
    if datetime.now(timezone.utc).timestamp() + config["worst_case_step_seconds"] > deadline.timestamp():
        raise TimeoutError("a full admitted step no longer fits before the study deadline")
    target = runner_root / "scientific-admission.json"
    fresh_json(target, receipt)
    fresh_json(runner_root / "scientific-admission-install.json", {
        "schema": "market_scientific_admission_install_v1", "receipt_sha256": file_hash(target),
        "experiment_id": config["experiment_id"], "installed_at_utc": datetime.now(timezone.utc).isoformat(),
        "paid_dispatch": False, "test_set_opened": False})
    return verify_installed_admission(runner_root)


def verify_installed_admission(runner_root):
    runner_root, config, manifest, budget = _context(runner_root)
    receipt_path = runner_root / "scientific-admission.json"
    install_path = runner_root / "scientific-admission-install.json"
    if not receipt_path.is_file() or receipt_path.is_symlink() or not install_path.is_file() or install_path.is_symlink():
        raise RuntimeError("scientific admission receipt is unavailable")
    receipt = json.loads(read_regular(receipt_path))
    install = json.loads(read_regular(install_path))
    expected_install = {"schema": "market_scientific_admission_install_v1",
        "receipt_sha256": file_hash(receipt_path), "experiment_id": config["experiment_id"],
        "installed_at_utc": install.get("installed_at_utc"), "paid_dispatch": False,
        "test_set_opened": False}
    _utc(install.get("installed_at_utc"), "installed_at_utc")
    if install != expected_install:
        raise ValueError("scientific admission installation changed")
    return validate_receipt(receipt, config, manifest, budget)


def owning_runner(path):
    """Find only an ancestor with the exact runner schema; never follow symlinks."""
    path = Path(path).absolute()
    for candidate in (path, *path.parents):
        config_path = candidate / "config.json"
        if config_path.is_symlink():
            raise ValueError("runner ancestry cannot traverse a symlinked config")
        if config_path.is_file():
            try:
                value = json.loads(read_regular(config_path))
            except (ValueError, json.JSONDecodeError):
                continue
            if value.get("schema") == "market_study_runner_v1":
                return candidate
    raise RuntimeError("scientific admission owner is unavailable")
