"""Pure verifier for the exact v0.1.26 one-shot source-scope fetch result."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

from market_rsi import digest
from paid_budget import PaidBudget
from supervisor_harness.global_state_gate import SupervisorGlobalState
from supervisor_harness.p0_gate1_source_scope_fetch_adapter import (
    ATTEMPT_ID, RELEASE_TAG, _validate_bundle, _verify_canary_receipt,
    validate_execution_binding,
)
from supervisor_harness import p0_gate1_source_scope_watched_fetch_child as child
from supervisor_harness import run_p0_gate1_source_scope_watched_fetch as parent


VERIFICATION_SCHEMA = "market_p0_gate1_source_scope_fetch_verification_v1"
WATCHDOG_SCHEMA = "market_supervisor_watchdog_v1"
ZERO = "0" * 64
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_TASK_CLAIM_FIELDS = {
    "task_id", "task_kind", "stage", "owner", "status", "started_utc",
    "last_heartbeat_utc", "last_progress_utc", "progress_seq",
    "last_progress_sha256", "heartbeat_timeout_seconds",
    "progress_timeout_seconds", "input_sha256", "data_admission_sha256",
    "process_identity", "container_identity", "data_gate", "incident_id",
}


def _sha(value: object, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be lowercase SHA-256")
    return value


def _read(path: Path, label: str, *, limit: int = 8 * 1024 * 1024) -> bytes:
    path = Path(path)
    if not path.is_absolute():
        raise ValueError(f"{label} path must be absolute")
    ancestors = [Path("/")]
    cursor = Path("/")
    for part in path.parts[1:-1]:
        cursor = cursor / part
        ancestors.append(cursor)
    ancestor_before = []
    for ancestor in ancestors:
        item = os.lstat(ancestor)
        if not stat.S_ISDIR(item.st_mode) or stat.S_ISLNK(item.st_mode):
            raise ValueError(f"{label} ancestor is unsafe")
        ancestor_before.append((item.st_dev, item.st_ino, item.st_mode))
    named_before = os.lstat(path)
    if (stat.S_ISLNK(named_before.st_mode)
            or path.resolve(strict=True) != path):
        raise ValueError(f"{label} path is not canonical")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or not 0 < before.st_size <= limit):
            raise ValueError(
                f"{label} must be a bounded single-link regular file")
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        named_after = os.lstat(path)
    finally:
        os.close(descriptor)
    named_closed = os.lstat(path)
    ancestor_after = []
    for ancestor in ancestors:
        item = os.lstat(ancestor)
        if not stat.S_ISDIR(item.st_mode) or stat.S_ISLNK(item.st_mode):
            raise ValueError(f"{label} ancestor changed")
        ancestor_after.append((item.st_dev, item.st_ino, item.st_mode))
    identity = lambda item: (item.st_dev, item.st_ino, item.st_mode,
                             item.st_nlink, item.st_uid, item.st_size,
                             item.st_mtime_ns, item.st_ctime_ns)
    if (identity(named_before) != identity(before)
            or identity(after) != identity(before)
            or identity(named_after) != identity(after)
            or identity(named_closed) != identity(after)
            or ancestor_before != ancestor_after
            or len(raw) != before.st_size):
        raise ValueError(f"{label} changed while reading")
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or not 0 < before.st_size <= limit):
        raise ValueError(f"{label} must be a bounded single-link regular file")
    return raw


def _json(path: Path, label: str, *, canonical: bool = True) -> tuple[dict, bytes]:
    raw = _read(path, label)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not JSON") from exc
    if type(value) is not dict:
        raise ValueError(f"{label} must be a JSON object")
    expected = (json.dumps(value, ensure_ascii=True, allow_nan=False,
                           sort_keys=True, separators=(",", ":"))
                + "\n").encode("ascii")
    if canonical and raw != expected:
        raise ValueError(f"{label} is not canonical")
    return value, raw


def _bound_file(value: object, expected: Path, sha: object,
                label: str, *, canonical: bool = True) -> tuple[dict, bytes]:
    if type(value) is not str or Path(value) != expected:
        raise ValueError(f"{label} path changed")
    document, raw = _json(expected, label, canonical=canonical)
    if hashlib.sha256(raw).hexdigest() != _sha(sha, label):
        raise ValueError(f"{label} hash changed")
    return document, raw


def _watchdog(raw: bytes, snapshot: dict, binding: dict,
              pid: int, command_sha256: str, receipt_sha256: str,
              parent_claim: dict) -> None:
    records = []
    prior = ZERO
    for index, line in enumerate(raw.splitlines(), start=1):
        event = json.loads(line)
        if type(event) is not dict or set(event) != {
                "schema", "seq", "time_utc", "event", "payload",
                "prev_sha256", "sha256"}:
            raise ValueError("watchdog event fields differ")
        event_sha = event["sha256"]
        body = {name: value for name, value in event.items()
                if name != "sha256"}
        if (event["schema"] != WATCHDOG_SCHEMA or event["seq"] != index
                or event["prev_sha256"] != prior
                or event_sha != digest(body)):
            raise ValueError("watchdog hash chain changed")
        prior = event_sha
        records.append(event)
    if (len(records) < 5 or records[0]["event"] != "initialize"
            or records[0]["payload"] != {}
            or records[1]["event"] != "task_claim"
            or records[-1]["event"] != "task_close"
            or any(item["event"] != "heartbeat" for item in records[2:-1])):
        raise ValueError("watchdog success grammar changed")
    claim = records[1]["payload"]
    expected_input = digest({"task": binding["task"],
                             "admission": binding["admission"]})
    if (set(claim) != _TASK_CLAIM_FIELDS
            or claim.get("task_id") != child.TASK_ID
            or claim.get("task_kind") != "research"
            or claim.get("stage") != "gate1_source_scope_fetch"
            or claim.get("owner") != "trusted_broker"
            or claim.get("status") != "active"
            or claim.get("input_sha256") != expected_input
            or claim.get("process_identity") != {
                "pid": pid, "command_sha256": command_sha256}
            or claim.get("container_identity") is not None
            or claim.get("data_admission_sha256") is not None):
        raise ValueError("watchdog claim changed")
    if (claim["heartbeat_timeout_seconds"] != 20
            or claim["progress_timeout_seconds"] != 30
            or claim["progress_seq"] != 0
            or claim["last_progress_sha256"] is not None
            or claim["data_gate"] is not None
            or claim["incident_id"] is not None
            or parent_claim["watchdog_head_sha256"] != records[1]["sha256"]):
        raise ValueError("watchdog claim deadlines or head changed")
    for item in records[2:-1]:
        payload = item["payload"]
        if (set(payload) != {"task_id", "material_progress",
                             "progress_sha256"}
                or payload["task_id"] != child.TASK_ID
                or type(payload["material_progress"]) is not bool
                or payload["material_progress"] is not True
                or _SHA256.fullmatch(payload["progress_sha256"] or "") is None):
            raise ValueError("watchdog heartbeat changed")
    if (records[2]["payload"]["progress_sha256"] != expected_input
            or records[-2]["payload"]["progress_sha256"] != receipt_sha256):
        raise ValueError("watchdog progress endpoints changed")
    if records[-1]["payload"] != {
            "task_id": child.TASK_ID, "outcome": "passed",
            "result_sha256": receipt_sha256, "old_id_reusable": False}:
        raise ValueError("watchdog close changed")
    if (snapshot.get("schema") != WATCHDOG_SCHEMA
            or snapshot.get("seq") != len(records)
            or snapshot.get("head_sha256") != prior
            or snapshot.get("active_task") is not None
            or snapshot.get("claimed_task_ids") != [child.TASK_ID]
            or snapshot.get("incidents") != []):
        raise ValueError("watchdog terminal snapshot changed")


def verify_fetch_receipt(
        result_path: Path, *, expected_result_sha256: str,
        expected_source_sha256: str, expected_runtime_sha256: str,
        expected_release_tag: str, expected_release_commit: str,
        expected_release_tag_object: str, expected_authorization_sha256: str,
        expected_prior_canary_receipt_sha256: str,
        expected_budget_snapshot_sha256: str) -> dict[str, Any]:
    """Verify all immutable evidence for the single successful fetch."""
    for value, label in (
            (expected_result_sha256, "result"),
            (expected_source_sha256, "source"),
            (expected_runtime_sha256, "runtime"),
            (expected_authorization_sha256, "authorization"),
            (expected_prior_canary_receipt_sha256, "prior canary"),
            (expected_budget_snapshot_sha256, "budget snapshot")):
        _sha(value, label)
    if (expected_release_tag != RELEASE_TAG
            or type(expected_release_commit) is not str
            or _SHA1.fullmatch(expected_release_commit) is None
            or type(expected_release_tag_object) is not str
            or _SHA1.fullmatch(expected_release_tag_object) is None):
        raise ValueError("exact v0.1.26 release identity required")
    result_path = Path(result_path)
    result, result_raw = _json(result_path, "parent result")
    if (hashlib.sha256(result_raw).hexdigest() != expected_result_sha256
            or set(result) != parent.RESULT_FIELDS
            or result["schema"] != parent.RESULT_SCHEMA
            or result["attempt_id"] != ATTEMPT_ID
            or result["passed"] is not True):
        raise ValueError("parent result changed")
    root = result_path.parent
    if (not result_path.is_absolute() or result_path != root / "result.json"
            or root != parent.RUN_ROOT):
        raise ValueError("parent result must be the exact run-root result")
    binding, binding_raw = _bound_file(
        result["binding_path"], root / "binding.json",
        result["binding_file_sha256"], "binding")
    binding = validate_execution_binding(binding)
    if (digest(binding) != result["binding_canonical_sha256"]
            or binding["current_source_sha256"] != expected_source_sha256
            or binding["runtime_sha256"] != expected_runtime_sha256
            or binding["authorization_file_sha256"]
            != expected_authorization_sha256
            or binding["task"]["prior_canary_receipt_sha256"]
            != expected_prior_canary_receipt_sha256
            or binding["task"]["release"] != {
                "tag": expected_release_tag, "commit": expected_release_commit,
                "tag_object": expected_release_tag_object,
                "source_sha256": expected_source_sha256}):
        raise ValueError("binding release/evidence commitments changed")
    authorization_copy, _ = _bound_file(
        result["authorization_copy_path"], root / "authorization.json",
        result["authorization_copy_file_sha256"], "authorization copy")
    if (result["authorization_copy_file_sha256"]
            != expected_authorization_sha256
            or authorization_copy.get("schema")
            != "market_p0_gate1_source_scope_fetch_authorization_v1"):
        raise ValueError("authorization copy changed")
    request_bundle, _ = _bound_file(
        result["request_bundle_path"], root / "request-plan-bundle.json",
        result["request_bundle_file_sha256"], "request bundle")
    _validate_bundle(request_bundle)
    runtime_receipt, _ = _bound_file(
        result["runtime_receipt_path"], root / "runtime.json",
        result["runtime_receipt_file_sha256"], "runtime receipt")
    if digest(runtime_receipt) != expected_runtime_sha256:
        raise ValueError("runtime receipt changed")
    canary_verification, _ = _bound_file(
        result["canary_verification_path"],
        root / "canary-verification.json",
        result["canary_verification_file_sha256"], "canary verification")
    if canary_verification != binding["canary_verification"]:
        raise ValueError("canary verification copy changed")
    replayed_canary = _verify_canary_receipt(
        Path(canary_verification["receipt_path"]),
        expected_receipt_sha256=expected_prior_canary_receipt_sha256,
        expected_source_sha256=expected_source_sha256,
        expected_runtime_sha256=expected_runtime_sha256,
        expected_release_tag=expected_release_tag,
        expected_release_commit=expected_release_commit,
        expected_release_tag_object=expected_release_tag_object)
    if replayed_canary != canary_verification:
        raise ValueError("full prior canary replay changed")
    claim, claim_raw = _bound_file(
        result["parent_claim_path"], root / "supervisor-claim.json",
        result["parent_claim_file_sha256"], "parent claim")
    if (set(claim) != child.PARENT_CLAIM_FIELDS
            or claim["schema"] != parent.PARENT_CLAIM_SCHEMA
            or claim["task_id"] != child.TASK_ID
            or claim["binding_canonical_sha256"] != digest(binding)
            or claim["pid"] != result["child_pid"]
            or claim["process_command_sha256"]
            != result["process_command_sha256"]
            or claim["budget_snapshot_sha256"]
            != expected_budget_snapshot_sha256
            or claim["binding_path"] != str(root / "binding.json")
            or claim["output_path"] != str(root / "snapshot")
            or claim["watchdog_root"] != str(root / "watchdog")
            or claim["claim_path"] != str(root / "supervisor-claim.json")
            or type(claim["parent_pid"]) is not int
            or claim["parent_pid"] <= 1
            or _SHA256.fullmatch(claim["parent_command_sha256"] or "") is None
            or claim["global_state_root"] != str(parent.GLOBAL_STATE_ROOT)
            or claim["global_state_head_sha256"]
            != result["global_state_head_sha256"]
            or claim["decision_doc_path"] != str(parent.DECISION_DOC)
            or claim["decision_doc_sha256"] != result["decision_doc_sha256"]
            or claim["budget_root"] != str(parent.BUDGET_ROOT)
            or claim["automatic_retry"] is not False):
        raise ValueError("parent claim changed")
    child_result, child_raw = _bound_file(
        result["child_result_path"], root / "child-result.json",
        result["child_result_file_sha256"], "child result")
    parent._validate_child_result(child_result, binding)
    receipt, receipt_raw = _bound_file(
        result["receipt_path"], root / "snapshot" / "receipt.json",
        result["receipt_file_sha256"], "snapshot receipt")
    snapshot_path = root / "snapshot" / "public-source.snapshot"
    if result["snapshot_path"] != str(snapshot_path):
        raise ValueError("snapshot path changed")
    child._validate_receipt(receipt, binding, snapshot_path)
    if (hashlib.sha256(_read(snapshot_path, "snapshot")).hexdigest()
            != result["snapshot_sha256"]
            or snapshot_path.stat().st_size != result["snapshot_bytes"]):
        raise ValueError("snapshot commitment changed")
    watchdog_snapshot, snapshot_raw = _bound_file(
        result["watchdog_snapshot_path"], root / "watchdog" / "snapshot.json",
        result["watchdog_snapshot_file_sha256"], "watchdog snapshot",
        canonical=False)
    journal_path = root / "watchdog" / "journal.jsonl"
    if result["watchdog_journal_path"] != str(journal_path):
        raise ValueError("watchdog journal path changed")
    journal_raw = _read(journal_path, "watchdog journal")
    if hashlib.sha256(journal_raw).hexdigest() != result[
            "watchdog_journal_file_sha256"]:
        raise ValueError("watchdog journal hash changed")
    _watchdog(journal_raw, watchdog_snapshot, binding,
              result["child_pid"], result["process_command_sha256"],
              result["receipt_file_sha256"], claim)
    global_journal_path = Path(result["global_state_journal_path"])
    if (global_journal_path != parent.GLOBAL_STATE_ROOT / "journal.jsonl"
            or Path(result["decision_doc_path"]) != parent.DECISION_DOC
            or Path(result["budget_root"]) != parent.BUDGET_ROOT):
        raise ValueError("authoritative state/decision/budget path changed")
    global_journal_raw = _read(global_journal_path, "global-state journal")
    if (hashlib.sha256(global_journal_raw).hexdigest()
            != result["global_state_journal_file_sha256"]):
        raise ValueError("global-state journal hash changed")
    decision_path = Path(result["decision_doc_path"])
    if (hashlib.sha256(_read(decision_path, "decision document")).hexdigest()
            != result["decision_doc_sha256"]):
        raise ValueError("decision document hash changed")
    global_state = SupervisorGlobalState(
        global_journal_path.parent, decision_path).snapshot()
    if (global_state["active_cycle"] != ATTEMPT_ID
            or global_state["head_sha256"]
            != result["global_state_head_sha256"]
            or ATTEMPT_ID not in global_state["claimed_cycles"]
            or ATTEMPT_ID in global_state["completed_cycles"]
            or result["global_state_status"]
            != "active_pending_independent_review"):
        raise ValueError("attempt is not permanently active pending review")
    budget_snapshot = PaidBudget(Path(result["budget_root"])).snapshot()
    if (digest(budget_snapshot) != expected_budget_snapshot_sha256
            or result["budget_snapshot_sha256"]
            != expected_budget_snapshot_sha256
            or ATTEMPT_ID in budget_snapshot.get("jobs", {})
            or result["budget_state"] != "none"):
        raise ValueError("authoritative zero-budget boundary changed")
    if (result["task_canonical_sha256"] != digest(binding["task"])
            or result["admission_canonical_sha256"] != digest(binding["admission"])
            or result["authorization_file_sha256"]
            != expected_authorization_sha256
            or result["prior_canary_receipt_sha256"]
            != expected_prior_canary_receipt_sha256
            or result["prior_canary_verification_sha256"]
            != binding["task"]["prior_canary_verification_sha256"]
            or result["receipt_file_sha256"]
            != child_result["receipt_file_sha256"]
            or result["snapshot_sha256"] != child_result["snapshot_sha256"]
            or result["snapshot_bytes"] != child_result["snapshot_bytes"]
            or result["final_url"] != binding["task"]["source"]["url"]
            or result["content_encoding"] is not None
            or result["child_exit_code"] != 0
            or result["terminal_process_absent"] is not True
            or result["terminal_container_absent"] is not True
            or result["watchdog_head_sha256"]
            != watchdog_snapshot["head_sha256"]
            or result["watchdog_seq"] != watchdog_snapshot["seq"]
            or result["global_state_head_sha256"]
            != global_state["head_sha256"]
            or type(result["requests_made"]) is not int
            or result["requests_made"] != 1
            or type(result["redirects_followed"]) is not int
            or result["redirects_followed"] != 0
            or type(result["automatic_retries"]) is not int
            or result["automatic_retries"] != 0
            or type(result["provider_calls"]) is not int
            or result["provider_calls"] != 0
            or result["actual_provider_cost_usd"] != "0"
            or any(result[name] is not False for name in (
                "rights_proven", "formal_data_admitted",
                "train_dev_final_read", "training_or_evaluation_performed",
                "snapshot_redistributed", "prediction_improvement_proven"))):
        raise ValueError("parent terminal boundary changed")
    evidence = {
        "binding": hashlib.sha256(binding_raw).hexdigest(),
        "parent_claim": hashlib.sha256(claim_raw).hexdigest(),
        "child_result": hashlib.sha256(child_raw).hexdigest(),
        "snapshot_receipt": hashlib.sha256(receipt_raw).hexdigest(),
        "snapshot": result["snapshot_sha256"],
        "watchdog_journal": hashlib.sha256(journal_raw).hexdigest(),
        "watchdog_snapshot": hashlib.sha256(snapshot_raw).hexdigest(),
        "global_state_journal": hashlib.sha256(
            global_journal_raw).hexdigest(),
        "decision_document": result["decision_doc_sha256"],
        "budget_snapshot": expected_budget_snapshot_sha256,
    }
    return {
        "schema": VERIFICATION_SCHEMA, "passed": True,
        "attempt_id": ATTEMPT_ID, "result_path": str(result_path),
        "result_sha256": expected_result_sha256,
        "release": binding["task"]["release"],
        "runtime_sha256": expected_runtime_sha256,
        "authorization_file_sha256": expected_authorization_sha256,
        "prior_canary_receipt_sha256": expected_prior_canary_receipt_sha256,
        "request_plan_canonical_sha256":
            binding["task"]["request_plan_canonical_sha256"],
        "request_bundle_canonical_sha256":
            binding["task"]["request_bundle_canonical_sha256"],
        "snapshot_sha256": result["snapshot_sha256"],
        "snapshot_bytes": result["snapshot_bytes"],
        "final_url": result["final_url"], "content_encoding": None,
        "requests_made": 1, "redirects_followed": 0,
        "automatic_retries": 0, "provider_calls": 0,
        "actual_provider_cost_usd": "0", "rights_proven": False,
        "formal_data_admitted": False, "train_dev_final_read": False,
        "training_or_evaluation_performed": False,
        "snapshot_redistributed": False,
        "prediction_improvement_proven": False,
        "terminal_cleanup_verified": True, "evidence_sha256": evidence,
        "global_state_status": "active_pending_independent_review",
    }
