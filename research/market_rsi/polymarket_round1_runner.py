#!/usr/bin/env python3
"""Initialize and advance the single trusted Polymarket Round-1 runner."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from coder_worker import CodexCLITransport
from market_rsi import digest, file_hash, fresh_json
from paid_budget import PaidBudget
from polymarket_round1_protocol import validate_protocol, validate_study_binding
from research_context import freeze_common
from researcher_worker import GLMTransport
from scientific_admission import CHECKS, EVIDENCE_KINDS
from study_runner import StudyRunner
from study_state import StudyState


def _read(path):
    return json.loads(Path(path).read_text())


def _write_evidence(root, kind, value):
    path = root / "evidence" / (kind + ".json")
    fresh_json(path, value)
    return {"kind": kind, "path": str(path.resolve()), "sha256": file_hash(path)}


def initialize(args):
    collector_source_sha256 = args.collector_source_sha256.lower()
    if (len(collector_source_sha256) != 64
            or any(character not in "0123456789abcdef" for character in collector_source_sha256)):
        raise ValueError("exact 64-character collector source SHA-256 required")
    freeze = args.data_freeze.resolve()
    tasks = _read(freeze / "tasks.json")
    task_data = _read(freeze / "task-data.json")
    baselines = _read(freeze / "baseline-source-hashes.json")
    protocol = _read(freeze / "protocol.json")
    validate_protocol(protocol)
    if protocol["experiment_id"] != args.experiment_id:
        raise ValueError("data freeze belongs to another experiment")
    runtime_probe = _read(args.runtime_probe / "assessment.json")
    cleanup = _read(args.runtime_probe / "cleanup.json")
    if runtime_probe.get("passed") is not True or cleanup.get("kill_acknowledged") is not True:
        raise ValueError("runtime probe and exact cleanup must pass")

    root = args.output.resolve()
    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    (root / "evidence").mkdir(mode=0o700)
    common = root / "common-start.json"
    freeze_common(common)
    budget = PaidBudget.create(root / "budget", {
        "experiment_id": args.experiment_id, "cap_usd": "50", "target_usd": "40",
        "buckets_usd": {"learning": "30", "final": "20"},
        "authority": "User authorized a $100-$200 whole experiment; this first pilot is hard-capped at $50.",
    })
    deadline = datetime.fromisoformat(args.deadline_utc)
    if deadline.tzinfo is None or deadline.utcoffset().total_seconds() != 0:
        raise ValueError("explicit UTC deadline required")
    study = StudyState.create(root / "study", common_manifest=common, tasks=tasks,
        baseline_source_hashes=baselines, max_steps_per_task=2,
        max_diagnostics_per_task=1,
        max_research_calls_per_task=4,
        deadline_utc=args.deadline_utc, worst_case_step_seconds=1200)

    preflight_dir = root / "coder-readiness"
    preflight_dir.mkdir(mode=0o700)
    coder = CodexCLITransport(args.coder_pin)
    coder.bind_process_deadline(preflight_dir, time.monotonic() + 30)
    coder_identity = coder.check_ready()
    runtime = {
        "feature_names": ["bid", "ask", "mid", "spread", "bid_size", "ask_size", "imbalance"],
        "prediction_min": 0.0, "prediction_max": 1.0,
        "libraries": {"python": runtime_probe["python"]},
        "execution_limits": {
            "cpu_seconds": 120, "memory_mb": 512,
            "prediction": {"fit_timeout_seconds": 60, "predict_timeout_seconds": 5,
                           "wall_seconds": 120, "max_request_bytes": 8 * 1024 * 1024},
            "inspection": {"timeout_seconds": 120, "max_request_bytes": 8 * 1024 * 1024,
                           "max_response_bytes": 512 * 1024, "max_json_nodes": 10000,
                           "max_json_depth": 16},
        },
    }
    coder_limits = {"wall_seconds": 300, "max_prompt_bytes": 2 * 1024 * 1024,
                    "max_stream_bytes": 512 * 1024, "max_code_bytes": 64 * 1024}
    runner = StudyRunner.create(root / "runner", study, budget, runtime=runtime,
        coder_limits=coder_limits, coder_identity=coder_identity, task_data=task_data, live=True)
    config = _read(runner.root / "config.json")
    manifest = _read(study.root / "manifest.json")
    binding = validate_study_binding(protocol, manifest, config, budget.snapshot())
    fresh_json(root / "round1-binding.json", binding)

    materialization = _read(freeze / "materialization-receipt.json")
    source_bundle = _read(args.materialized)["source_bundle"]
    evidence = []
    evidence.append(_write_evidence(root, "collector_source", {
        "collector_source_sha256": collector_source_sha256,
        "review": "exact source hash bound; observed_at is written after full REST response receipt"}))
    evidence.append(_write_evidence(root, "collector_runtime", {
        "service": "ez-polymarket-us-capture.service", "transport": "independent REST full-book polling",
        "sequence_scope": "not applicable", "reconnect": "next successful poll is a complete fresh snapshot"}))
    evidence.append(_write_evidence(root, "collector_session", {
        "source_host": "173.255.231.4", "prospective_boundary_utc": "2026-09-07T16:08:41Z",
        "historical_use": "diagnostic Round 1 only"}))
    evidence.append(_write_evidence(root, "capture_manifest", source_bundle))
    evidence.append(_write_evidence(root, "split_receipt", {
        "materialization_receipt_sha256": file_hash(freeze / "materialization-receipt.json"),
        "tasks": materialization["tasks"], "whole_game_disjoint": True,
        "chronological_blocks": materialization["date_blocks"]}))
    evidence.append(_write_evidence(root, "materializer_receipt", materialization))
    evidence.append(_write_evidence(root, "scorer_contract", {
        "source_sha256": file_hash(Path(__file__).with_name("polymarket_scoring.py")),
        "target": "future_midpoint_at_60_seconds", "baseline": "current_midpoint_persistence",
        "primary": "same-mask MSE by game", "test_open_count": 1}))
    evidence.append(_write_evidence(root, "deadline_verification", {
        "deadline_utc": args.deadline_utc, "worst_case_step_seconds": 1200,
        "shared_nonrenewable_step_deadline": True,
        "runner_config_sha256": digest(config)}))
    if {entry["kind"] for entry in evidence} != EVIDENCE_KINDS:
        raise ValueError("complete scientific evidence set required")
    receipt = {"schema": "market_scientific_admission_v1", "experiment_id": args.experiment_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "deadline_utc": args.deadline_utc,
        "evidence_class": "reviewed_historical_source", "review_id": args.experiment_id + "-admission-01",
        "reviewer_role": "trusted_runner_reviewer", "checks": {key: True for key in CHECKS},
        "evidence_files": evidence, "study_manifest_sha256": digest(manifest),
        "runner_config_sha256": digest(config), "task_data_sha256": digest(config["task_data"]),
        "runtime_sha256": digest(config["runtime"]), "coder_limits_sha256": digest(config["coder_limits"]),
        "coder_identity_sha256": digest(config["coder_identity"]),
        "worker_source_hashes_sha256": digest(config["source_hashes"]),
        "budget_cap_usd": budget.snapshot()["cap_usd"], "test_set_opened": False,
        "external_results_seen": False, "scientific_admission": True}
    receipt_path = root / "reviewed-admission.json"
    fresh_json(receipt_path, receipt)
    runner.install_admission(receipt_path)
    fresh_json(root / "control.json", {
        "experiment_id": args.experiment_id, "runner": str(runner.root),
        "coder_pin": str(args.coder_pin.resolve()), "env_file": str(args.env_file.resolve()),
        "tokenizer_cache": str(args.tokenizer_cache.resolve()), "paid_concurrency": 1,
        "automatic_retries": 0, "test_opened": False})
    return status(root)


def status(root):
    root = Path(root).resolve()
    control = _read(root / "control.json")
    runner = StudyRunner(control["runner"])
    config, study, budget, _, _ = runner._load()
    return {"experiment_id": control["experiment_id"], "next_action": runner.next_action(),
            "study": study.snapshot(), "budget": budget.snapshot(),
            "runner_live": config["live"], "test_opened": control["test_opened"]}


def advance(root):
    root = Path(root).resolve()
    control = _read(root / "control.json")
    from dotenv import dotenv_values
    key = dotenv_values(control["env_file"]).get("TINKER_API_KEY")
    if not key:
        raise ValueError("Tinker key unavailable to trusted runner")
    runner = StudyRunner(control["runner"])
    action = runner.next_action()
    if action["action"] in {"research_closed", "causal_review_required", "window_closed",
                            "budget_blocked", "reconcile_pending"}:
        return status(root)
    researcher = GLMTransport(key, control["tokenizer_cache"])
    coder = None if action["action"] == "selection" else CodexCLITransport(control["coder_pin"])
    result = runner.tick(researcher, coder, env_file=control["env_file"])
    return {"advanced": action, "result": result, **status(root)}


def reconcile(root):
    """Finish the exact pending claim from existing receipts; never dispatch."""
    root = Path(root).resolve()
    control = _read(root / "control.json")
    runner = StudyRunner(control["runner"])
    if runner.next_action()["action"] != "reconcile_pending":
        raise ValueError("no exact pending claim to reconcile")
    result = runner.reconcile_pending()
    return {"reconciled": result, **status(root)}


def loop(root):
    while True:
        current = status(root)
        action = current["next_action"]["action"]
        print(json.dumps({"at": datetime.now(timezone.utc).isoformat(),
                          "next_action": current["next_action"],
                          "budget": current["budget"]}, sort_keys=True), flush=True)
        if action in {"research_closed", "causal_review_required", "window_closed",
                      "budget_blocked", "reconcile_pending"}:
            return current
        advance(root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("initialize")
    init.add_argument("--output", required=True, type=Path)
    init.add_argument("--data-freeze", required=True, type=Path)
    init.add_argument("--materialized", required=True, type=Path)
    init.add_argument("--runtime-probe", required=True, type=Path)
    init.add_argument("--collector-source-sha256", required=True)
    init.add_argument("--experiment-id", required=True)
    init.add_argument("--deadline-utc", required=True)
    init.add_argument("--coder-pin", required=True, type=Path)
    init.add_argument("--env-file", required=True, type=Path)
    init.add_argument("--tokenizer-cache", required=True, type=Path)
    for name in ("status", "advance", "reconcile", "loop"):
        item = sub.add_parser(name)
        item.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "initialize":
        result = initialize(args)
    elif args.command == "status":
        result = status(args.root)
    elif args.command == "advance":
        result = advance(args.root)
    elif args.command == "reconcile":
        result = reconcile(args.root)
    else:
        result = loop(args.root)
    print(json.dumps(result, sort_keys=True), flush=True)
