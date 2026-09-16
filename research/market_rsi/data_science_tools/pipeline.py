"""Pre-experiment data-science review, separate from frozen legacy runs.

Controller decisions are inputs, never proof of successful QA. Receipt files and
their commitments must be supplied by the runner outside the controller outbox.
This module is an admission prerequisite, not a budget reservation, data reader,
model executor, or replacement for the existing independent-validation checks.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import stat


SCHEMA = "market_data_science_review_v1"
BINDINGS = ("source_plan", "raw_manifest", "semantic_contract", "replay_contract",
            "feature_contract", "objective_contract", "split_contract", "execution_contract")
# These are required questions, not assistant-selected signal thresholds. A pass
# means the declared diagnostic was verified, not that it found a profitable edge.
STAGES = (
    ("sources", "来源与原件", ("source_plan", "raw_manifest"), (
        "selected_objects_accounted", "immutable_raw_and_provenance", "download_backup_disk_accounting")),
    ("coverage", "覆盖与样本量", ("source_plan", "raw_manifest"), (
        "actual_day_market_coverage", "quiet_vs_outage", "independent_sample_breadth", "sampling_plan_train_only")),
    ("semantics", "字段与异常记录", ("source_plan", "raw_manifest", "semantic_contract"), (
        "market_token_identity", "source_scoped_event_keys", "quote_trade_units", "anomalies_traceable")),
    ("causality", "当时可见的数据", ("raw_manifest", "semantic_contract", "replay_contract"), (
        "source_and_receipt_clock", "asof_market_join", "reconnect_snapshot_state", "missing_stale_candle_policy")),
    ("objective", "目标检查", ("replay_contract", "objective_contract"), (
        "controller_objective_decision", "label_window_availability", "train_target_activity_and_noise", "baseline_units_and_claim_scope")),
    ("features", "特征检查", ("replay_contract", "objective_contract", "feature_contract"), (
        "past_only_feature_windows", "train_only_normalization", "raw_signal_and_redundancy_measured", "feature_missingness_by_period")),
    ("split", "训练验证划分", ("source_plan", "raw_manifest", "replay_contract", "objective_contract", "split_contract"), (
        "chronological_whole_market_split", "label_overlap_purge", "opened_periods_not_fresh", "full_eval_population", "declared_session_requirements")),
    ("execution", "实验前检查", BINDINGS, (
        "baseline_canary_real_execution", "paired_rows_and_frozen_metrics", "independent_review_and_isolation", "actual_cost_budget_and_timeout")),
)
CHECK_STAGE = {check: stage for stage in STAGES for check in stage[3]}
SHA = re.compile(r"[0-9a-f]{64}\Z")
CONTROLS = {
    "raw_originals_preserved": True,
    "quiet_raw_rows_deleted": False,
    "future_movement_filters_eval": False,
    "missing_filled_as_no_change": False,
    "controller_can_self_approve": False,
    "sealed_values_used_for_design": False,
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def policy_sha256():
    return digest({"stages": STAGES, "controls": CONTROLS, "bindings": BINDINGS})


def _hash(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError("exact SHA256 required")
    return value


def _read_pinned(path, expected):
    """Small resident runner-owned receipts only; CLI is also OS-time-limited."""
    path = Path(path)
    if not path.is_absolute() or str(path.resolve()) != str(path):
        raise ValueError("canonical absolute receipt path required")
    s = path.stat()
    if not stat.S_ISREG(s.st_mode) or s.st_size > 8_388_608:
        raise ValueError("bounded regular receipt required")
    if getattr(s, "st_flags", 0) & getattr(stat, "SF_DATALESS", 0x40000000):
        raise ValueError("receipt is a dataless placeholder")
    with path.open("rb") as source:
        raw = source.read(8_388_609)
    if len(raw) > 8_388_608:
        raise ValueError("receipt grew beyond read bound")
    if hashlib.sha256(raw).hexdigest() != _hash(expected):
        raise ValueError("receipt bytes changed")
    return json.loads(raw)


def validate_spec(spec):
    if set(spec) != {"schema", "scope_id", "bindings", "controls", "controller_owns", "spec_sha256", "pipeline_policy_sha256"}:
        raise ValueError("exact data-science spec required")
    if spec["schema"] != SCHEMA or not isinstance(spec["scope_id"], str) or not spec["scope_id"]:
        raise ValueError("data-science scope required")
    if _hash(spec["spec_sha256"]) != digest({k: v for k, v in spec.items() if k != "spec_sha256"}):
        raise ValueError("data-science spec changed")
    if set(spec["bindings"]) != set(BINDINGS) or spec["controls"] != CONTROLS:
        raise ValueError("component bindings or safety controls changed")
    if spec["pipeline_policy_sha256"] != policy_sha256() or any(type(v) is not bool for v in spec["controls"].values()):
        raise ValueError("pipeline rules or control types changed")
    for value in spec["bindings"].values():
        if value is not None:
            _hash(value)
    if spec["controller_owns"] != ["source", "sampling", "features", "objective", "model"]:
        raise ValueError("runner must not select scientific methods")
    return spec


def evaluate(spec, reviewed_checks):
    """Pure status report. The runner must verify referenced bytes separately.

    An unresolved upstream stage blocks downstream readiness even if old receipts
    exist. Every receipt binds all upstream/component decisions relevant to it.
    Unknown never counts as pass. An optional input can only pass as unused when
    an independent review cites the frozen contract establishing non-use.
    """
    validate_spec(spec)
    if not isinstance(reviewed_checks, list):
        raise ValueError("reviewed checks must be a list")
    by_id = {}
    for item in reviewed_checks:
        expected = {"check_id", "status", "scope_id", "bindings", "reason", "evidence_refs", "reviewer_role"}
        if not isinstance(item, dict) or set(item) != expected:
            raise ValueError("exact independently reviewed check required")
        check = item["check_id"]
        if check not in CHECK_STAGE or check in by_id:
            raise ValueError("unknown or duplicate check")
        if item["scope_id"] != spec["scope_id"] or item["reviewer_role"] != "trusted_runner_review":
            raise ValueError("wrong scope or controller self-certification")
        if item["status"] not in ("pass", "fail", "unknown") or not isinstance(item["reason"], str) or not item["reason"].strip():
            raise ValueError("explicit result and reason required")
        required = CHECK_STAGE[check][2]
        expected_bindings = {k: spec["bindings"][k] for k in required}
        if item["bindings"] != expected_bindings:
            raise ValueError("stale review after component change")
        refs = item["evidence_refs"]
        if not isinstance(refs, list) or (item["status"] in ("pass", "fail") and not refs):
            raise ValueError("pass/failure needs actual evidence")
        seen_refs = set()
        for ref in refs:
            if set(ref) != {"path", "sha256"} or not isinstance(ref["path"], str) or ref["path"] in seen_refs:
                raise ValueError("unique evidence references required")
            _hash(ref["sha256"])
            seen_refs.add(ref["path"])
        if item["status"] == "pass" and any(v is None for v in expected_bindings.values()):
            raise ValueError("cannot pass before component definition is frozen")
        by_id[check] = item
    stages, blockers = [], []
    upstream_ready = True
    for key, title, bindings, checks in STAGES:
        missing = [c for c in checks if c not in by_id or by_id[c]["status"] == "unknown"]
        failed = [c for c in checks if c in by_id and by_id[c]["status"] == "fail"]
        local_ready = not missing and not failed
        status = "failed" if failed else "incomplete" if missing else "passed" if upstream_ready else "waiting_upstream"
        stages.append({"stage": key, "title": title, "status": status,
                       "missing_checks": missing, "failed_checks": failed,
                       "upstream_ready": upstream_ready})
        blockers.extend(failed + missing)
        upstream_ready = upstream_ready and local_ready
    return {"schema": "market_data_science_readiness_v1", "scope_id": spec["scope_id"],
            "spec_sha256": spec["spec_sha256"], "reviewed_checks_sha256": digest(reviewed_checks),
            "component_bindings": dict(spec["bindings"]), "pipeline_policy_sha256": policy_sha256(),
            "stages": stages, "blockers": blockers, "data_science_ready": upstream_ready,
            "execution_admitted": False, "new_labels_accessed": False,
            "decision_rule": "All required data-science checks first; separate runtime, one-shot cohort and budget gates still apply.",
            "research_next": next((s["stage"] for s in stages if s["status"] != "passed"), "experiment_preflight")}


def verify_review_files(spec_path, spec_sha256, review_path, review_sha256):
    """Only host-supplied commitments; never read a path named by the model."""
    spec = _read_pinned(spec_path, spec_sha256)
    checks = _read_pinned(review_path, review_sha256)
    report = evaluate(spec, checks)
    for item in checks:
        for ref in item["evidence_refs"]:
            _read_pinned(ref["path"], ref["sha256"])
    return report


def require_data_science_ready(spec_path, spec_sha256, review_path, review_sha256):
    report = verify_review_files(spec_path, spec_sha256, review_path, review_sha256)
    if not report["data_science_ready"]:
        raise RuntimeError("data-science preflight blocked: " + ", ".join(report["blockers"]))
    return report


def check_independent_validation_after_data_science(*, spec_path, spec_sha256, review_path,
                                                   review_sha256, proposal, context, runner, budget):
    """Additive entry point: data-science review BEFORE legacy validation checks.

    No evaluator/credentials are loaded here. A later runtime dispatcher must
    recheck this entry point before claiming a cohort or reserving provider cost.
    Legacy frozen entry points remain unchanged, not retroactively protected.
    """
    ready = require_data_science_ready(spec_path, spec_sha256, review_path, review_sha256)
    if (context.get("objective_sha256") != ready["component_bindings"]["objective_contract"]
            or context.get("source_contract_sha256") != ready["component_bindings"]["semantic_contract"]
            or runner.get("raw_manifest_sha256") != ready["component_bindings"]["raw_manifest"]
            or runner.get("data_science_spec_sha256") != ready["spec_sha256"]):
        raise ValueError("experiment differs from reviewed data/source/objective")
    from validation_tools.independent_validation import check_runner_evidence
    checked = check_runner_evidence(proposal, context, runner, budget)
    return {**checked, "data_science_review": ready}
