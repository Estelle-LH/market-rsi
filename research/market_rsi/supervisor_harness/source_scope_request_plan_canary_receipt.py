"""Pure verifier for the exact v0.1.26 zero-effect D0 bridge canary.

The verifier only reads caller-bound local evidence.  It performs no lookup,
subprocess, Git, network, provider, credential, budget, state, data, training,
or evaluation action.  A bare receipt digest is deliberately insufficient.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import pwd
import re
from typing import Any

from market_rsi import digest
from supervisor_harness import p0_gate1_source_scope_request_plan_canary_child as child


VERIFICATION_SCHEMA = (
    "market_p0_gate1_source_scope_request_plan_canary_verification_v1"
)
CANARY_SCHEMA = "market_p0_gate1_source_scope_request_plan_canary_v1"
SUPERVISOR_RESULT_SCHEMA = (
    "market_p0_gate1_source_scope_request_plan_canary_supervisor_v1"
)
PERMANENT_CLAIM_SCHEMA = (
    "market_p0_gate1_source_scope_request_plan_canary_permanent_claim_v1"
)
RUNTIME_SCHEMA = "market_p0_gate1_source_scope_request_plan_canary_runtime_v1"
TERMINAL_CLEAR_SCHEMA = (
    "market_p0_gate1_source_scope_request_plan_canary_terminal_clear_v1"
)
WATCHDOG_SCHEMA = "market_supervisor_watchdog_v1"
ZERO = "0" * 64
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_ACCOUNT_HOME = Path(pwd.getpwuid(os.geteuid()).pw_dir)
_MARKET_RSI_HOME = _ACCOUNT_HOME / "Library/Application Support/MarketRSI"
RUN_ROOT = _MARKET_RSI_HOME / "runs" / child.CANARY_ID
CLAIM_ROOT = (
    _MARKET_RSI_HOME / "self-evolving-v18-local/artifacts/"
    "p0-gate1-source-scope-request-canary-claims-v1"
)

_RECEIPT_FIELDS = {
    "schema", "canary_id", "passed", "release", "publication_path",
    "publication_sha256", "runtime_path", "runtime_sha256", "runtime_file_sha256",
    "d0_evidence_sha256", "request_plan_canonical_sha256",
    "request_bundle_canonical_sha256", "request_bundle_path",
    "request_bundle_file_sha256", "permanent_claim_path",
    "permanent_claim_sha256", "child_result_path", "child_result_sha256",
    "supervisor_claim_path", "supervisor_claim_sha256",
    "supervisor_result_path", "supervisor_result_sha256",
    "watchdog_journal_path", "watchdog_journal_sha256",
    "watchdog_snapshot_path", "watchdog_snapshot_sha256",
    "watchdog_head_sha256", "terminal_clear_path", "terminal_clear_sha256",
    "provider_calls", "network_requests", "actual_provider_cost_usd",
    "external_bytes_received", "public_fetch_performed", "snapshot_retained",
    "data_admitted", "train_dev_final_read",
    "training_or_evaluation_performed", "automatic_retry",
    "terminal_cleanup_verified",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA256")
    return value


def _load(path: Path, label: str) -> tuple[dict, bytes]:
    raw = child._read_regular(path, label)
    return child._parse_json(raw, label), raw


def _bound_path(value: object, expected: Path, label: str) -> Path:
    _require(type(value) is str, f"{label} path must be a string")
    path = Path(value)
    _require(path == expected and path.is_absolute(), f"{label} path changed")
    return path


def _load_bound(value: object, expected: Path, expected_sha: object,
                label: str) -> tuple[dict, bytes]:
    path = _bound_path(value, expected, label)
    document, raw = _load(path, label)
    _require(hashlib.sha256(raw).hexdigest() == _sha256(expected_sha, label),
             f"{label} file commitment changed")
    return document, raw


def _zero_effects(record: dict, label: str) -> None:
    _require(
        type(record.get("provider_calls")) is int
        and record.get("provider_calls") == 0
        and type(record.get("network_requests")) is int
        and record.get("network_requests") == 0
        and record.get("actual_provider_cost_usd") == "0"
        and type(record.get("external_bytes_received")) is int
        and record.get("external_bytes_received") == 0
        and record.get("public_fetch_performed") is False
        and record.get("snapshot_retained") is False
        and record.get("data_admitted") is False
        and record.get("train_dev_final_read") is False
        and record.get("training_or_evaluation_performed") is False
        and record.get("automatic_retry") is False,
        f"{label} external-effect boundary changed",
    )


def _watchdog(journal_raw: bytes, snapshot: dict, child_result_sha256: str,
              supervisor_claim: dict, release: dict,
              runtime_sha256: str) -> None:
    records = []
    prior = ZERO
    for index, raw_line in enumerate(journal_raw.splitlines(), start=1):
        event = child._parse_json(raw_line, f"watchdog event {index}")
        _require(set(event) == {
            "schema", "seq", "time_utc", "event", "payload",
            "prev_sha256", "sha256",
        }, "invalid watchdog event fields")
        event_sha = event["sha256"]
        body = {key: value for key, value in event.items() if key != "sha256"}
        _require(event["schema"] == WATCHDOG_SCHEMA
                 and event["seq"] == index
                 and event["prev_sha256"] == prior
                 and event_sha == digest(body),
                 "watchdog journal hash chain changed")
        prior = event_sha
        records.append(event)
    _require(len(records) >= 3, "watchdog journal is incomplete")
    _require(records[0]["event"] == "initialize"
             and records[0]["payload"] == {},
             "watchdog initialization changed")
    claims = [item for item in records if item["event"] == "task_claim"]
    closes = [item for item in records if item["event"] == "task_close"]
    incidents = [item for item in records if item["event"] == "incident"]
    material = [item for item in records
                if item["event"] == "heartbeat"
                and item["payload"].get("material_progress") is True]
    _require(len(claims) == 1 and len(closes) == 1 and not incidents
             and len(material) >= 2,
             "watchdog terminal sequence changed")
    claim = claims[0]["payload"]
    close = closes[0]["payload"]
    _require(
        claim.get("task_id") == child.CANARY_ID
        and claim.get("task_kind") == "research"
        and claim.get("stage") == "bridge_canary"
        and claim.get("status") == "active"
        and claim.get("owner") == "outer_supervisor"
        and claim.get("heartbeat_timeout_seconds") == 10
        and claim.get("progress_timeout_seconds") == 20
        and claim.get("process_identity") == {
            "pid": supervisor_claim["pid"],
            "command_sha256": supervisor_claim["process_command_sha256"],
        }
        and claim.get("container_identity") == {
            "name": "market-rsi-b-" + child.CANARY_ID,
            "label": "market-rsi-b-" + child.CANARY_ID,
        }
        and claim.get("input_sha256") == digest({
            "canary_id": child.CANARY_ID,
            "release": release,
            "runtime_sha256": runtime_sha256,
            "request_plan_canonical_sha256": child.REQUEST_PLAN_CANONICAL_SHA256,
            "request_bundle_canonical_sha256": child.REQUEST_BUNDLE_CANONICAL_SHA256,
            "d0_evidence_sha256": child.D0_FILE_SHA256,
        })
        and claim.get("data_admission_sha256") is None
        and close == {
            "task_id": child.CANARY_ID,
            "outcome": "passed",
            "result_sha256": child_result_sha256,
            "old_id_reusable": False,
        },
        "watchdog claim/close binding changed",
    )
    _require(all(
        item["payload"].get("task_id") == child.CANARY_ID
        and _SHA256.fullmatch(item["payload"].get("progress_sha256", ""))
        for item in material
    ), "watchdog material progress evidence changed")
    _require(snapshot.get("schema") == WATCHDOG_SCHEMA
             and snapshot.get("head_sha256") == prior
             and snapshot.get("active_task") is None
             and snapshot.get("claimed_task_ids") == [child.CANARY_ID]
             and snapshot.get("incidents") == [],
             "watchdog terminal snapshot changed")


def verify_canary_receipt(
    receipt_path: Path,
    *,
    expected_receipt_sha256: str,
    expected_source_sha256: str,
    expected_runtime_sha256: str,
    expected_release_tag: str,
    expected_release_commit: str,
    expected_release_tag_object: str,
) -> dict[str, Any]:
    """Verify and summarize one exact immutable PASS evidence tree."""

    expected_receipt_sha256 = _sha256(expected_receipt_sha256, "receipt")
    expected_source_sha256 = _sha256(expected_source_sha256, "source")
    expected_runtime_sha256 = _sha256(expected_runtime_sha256, "runtime")
    _require(expected_release_tag == child.RELEASE_TAG,
             "exact v0.1.26 release tag required")
    _require(type(expected_release_commit) is str
             and _SHA1.fullmatch(expected_release_commit) is not None,
             "full release commit required")
    _require(type(expected_release_tag_object) is str
             and _SHA1.fullmatch(expected_release_tag_object) is not None,
             "full annotated tag object required")
    receipt_path = Path(receipt_path)
    receipt, receipt_raw = _load(receipt_path, "canary receipt")
    _require(hashlib.sha256(receipt_raw).hexdigest() == expected_receipt_sha256,
             "canary receipt file commitment changed")
    _require(set(receipt) == _RECEIPT_FIELDS, "invalid canary receipt fields")
    root = receipt_path.parent
    _require(receipt_path == RUN_ROOT / "receipt.json" and root == RUN_ROOT,
             "receipt must be the predeclared durable non-cloud run receipt")
    release = {
        "tag": expected_release_tag,
        "commit": expected_release_commit,
        "tag_object": expected_release_tag_object,
        "source_sha256": expected_source_sha256,
    }
    _require(receipt["schema"] == CANARY_SCHEMA
             and receipt["canary_id"] == child.CANARY_ID
             and receipt["passed"] is True
             and receipt["release"] == release
             and receipt["runtime_sha256"] == expected_runtime_sha256
             and receipt["d0_evidence_sha256"] == child.D0_FILE_SHA256
             and receipt["request_plan_canonical_sha256"]
             == child.REQUEST_PLAN_CANONICAL_SHA256
             and receipt["request_bundle_canonical_sha256"]
             == child.REQUEST_BUNDLE_CANONICAL_SHA256
             and receipt["terminal_cleanup_verified"] is True,
             "canary receipt binding changed")
    _zero_effects(receipt, "canary receipt")

    publication, _ = _load_bound(
        receipt["publication_path"], root / "publication.json",
        receipt["publication_sha256"], "publication")
    _require(publication.get("schema") == "market_rsi_protocol_publication_v1"
             and set(publication) == {
                 "schema", "origin", "tag", "commit", "tag_object",
                 "source_sha256", "source_hashes", "isolation_proven",
                 "model_authorship_proven",
             }
             and publication.get("origin") == child.PUBLISHED_ORIGIN
             and publication.get("tag") == expected_release_tag
             and publication.get("commit") == expected_release_commit
             and publication.get("tag_object") == expected_release_tag_object
             and publication.get("source_sha256") == expected_source_sha256
             and type(publication.get("source_hashes")) is dict
             and digest(publication["source_hashes"]) == expected_source_sha256,
             "publication release binding changed")
    _require(publication["isolation_proven"] is False
             and publication["model_authorship_proven"] is False,
             "publication claim boundary changed")

    runtime, _ = _load_bound(
        receipt["runtime_path"], root / "runtime.json",
        receipt["runtime_file_sha256"], "runtime")
    _require(set(runtime) == {
        "schema", "python_executable", "python_version", "source_hashes",
        "source_hashes_sha256", "provider_modules_loaded",
        "public_fetch_modules_loaded", "watched_fetch_modules_loaded",
        "network_modules_loaded_by_canary",
    } and runtime["schema"] == RUNTIME_SCHEMA
        and type(runtime["source_hashes"]) is dict
        and digest(runtime) == expected_runtime_sha256
        and digest(runtime["source_hashes"]) == runtime["source_hashes_sha256"]
        and all(publication["source_hashes"].get(name) == value
                for name, value in runtime["source_hashes"].items())
        and runtime["provider_modules_loaded"] is False
        and runtime["public_fetch_modules_loaded"] is False
        and runtime["watched_fetch_modules_loaded"] is False
        and runtime["network_modules_loaded_by_canary"] is False,
        "runtime binding or import boundary changed")

    bundle, _ = _load_bound(
        receipt["request_bundle_path"], root / "artifacts" / "request-plan-bundle.json",
        receipt["request_bundle_file_sha256"], "request-plan bundle")
    _require(digest(bundle) == child.REQUEST_BUNDLE_CANONICAL_SHA256
             and bundle.get("request_plan_canonical_sha256")
             == child.REQUEST_PLAN_CANONICAL_SHA256
             and bundle.get("future_fetch_admission_requirements", {}).get(
                 "fetch_authorized") is False
             and bundle.get("request_plan", {}).get("authority", {}).get(
                 "request_executable") is False,
             "request-plan bundle commitment or authority changed")

    permanent_claim_path = CLAIM_ROOT / f"{child.CANARY_ID}.json"
    permanent_claim, _ = _load_bound(
        receipt["permanent_claim_path"], permanent_claim_path,
        receipt["permanent_claim_sha256"], "permanent claim")
    _require(set(permanent_claim) == {
        "schema", "canary_id", "output_root", "release", "runtime_sha256",
        "d0_evidence_sha256", "request_plan_canonical_sha256",
        "request_bundle_canonical_sha256", "automatic_retry",
        "same_id_retry_allowed",
    } and permanent_claim["schema"] == PERMANENT_CLAIM_SCHEMA
        and permanent_claim["canary_id"] == child.CANARY_ID
        and permanent_claim["output_root"] == str(root)
        and permanent_claim["release"] == release
        and permanent_claim["runtime_sha256"] == expected_runtime_sha256
        and permanent_claim["d0_evidence_sha256"] == child.D0_FILE_SHA256
        and permanent_claim["request_plan_canonical_sha256"]
        == child.REQUEST_PLAN_CANONICAL_SHA256
        and permanent_claim["request_bundle_canonical_sha256"]
        == child.REQUEST_BUNDLE_CANONICAL_SHA256
        and permanent_claim["automatic_retry"] is False
        and permanent_claim["same_id_retry_allowed"] is False,
        "permanent claim binding changed")

    child_result, _ = _load_bound(
        receipt["child_result_path"], root / "artifacts" / "result.json",
        receipt["child_result_sha256"], "child result")
    _require(set(child_result) == {
                 "schema", "canary_id", "passed", "release", "runtime_sha256",
                 "d0_evidence_sha256", "request_plan_canonical_sha256",
                 "request_bundle_canonical_sha256",
                 "request_bundle_file_sha256", "supervisor_claim_sha256",
                 "provider_calls", "network_requests",
                 "actual_provider_cost_usd", "external_bytes_received",
                 "public_fetch_performed", "snapshot_retained", "data_admitted",
                 "train_dev_final_read", "training_or_evaluation_performed",
                 "automatic_retry",
             }
             and child_result.get("schema") == child.CANARY_CHILD_SCHEMA
             and child_result.get("canary_id") == child.CANARY_ID
             and child_result.get("passed") is True
             and child_result.get("release") == release
             and child_result.get("runtime_sha256") == expected_runtime_sha256
             and child_result.get("d0_evidence_sha256") == child.D0_FILE_SHA256
             and child_result.get("request_plan_canonical_sha256")
             == child.REQUEST_PLAN_CANONICAL_SHA256
             and child_result.get("request_bundle_canonical_sha256")
             == child.REQUEST_BUNDLE_CANONICAL_SHA256
             and child_result.get("request_bundle_file_sha256")
             == receipt["request_bundle_file_sha256"]
             and child_result.get("supervisor_claim_sha256")
             == receipt["supervisor_claim_sha256"],
             "child result binding changed")
    _zero_effects(child_result, "child result")

    supervisor_claim, _ = _load_bound(
        receipt["supervisor_claim_path"],
        root / "supervisor" / "supervisor-claim.json",
        receipt["supervisor_claim_sha256"], "supervisor claim")
    _require(set(supervisor_claim) == {
                 "schema", "cycle_id", "task_id", "pid",
                 "process_command_sha256", "supervisor_pid",
                 "supervisor_command_sha256", "watchdog_head_sha256",
                 "release", "runtime_sha256", "request_plan_canonical_sha256",
                 "request_bundle_canonical_sha256", "permanent_claim_sha256",
                 "automatic_retry",
             }
             and supervisor_claim.get("schema") == child.SUPERVISOR_CLAIM_SCHEMA
             and supervisor_claim.get("cycle_id") == child.CANARY_ID
             and supervisor_claim.get("task_id") == child.CANARY_ID
             and type(supervisor_claim.get("pid")) is int
             and supervisor_claim["pid"] > 1
             and type(supervisor_claim.get("supervisor_pid")) is int
             and supervisor_claim["supervisor_pid"] > 1
             and supervisor_claim.get("release") == release
             and supervisor_claim.get("runtime_sha256") == expected_runtime_sha256
             and supervisor_claim.get("request_plan_canonical_sha256")
             == child.REQUEST_PLAN_CANONICAL_SHA256
             and supervisor_claim.get("request_bundle_canonical_sha256")
             == child.REQUEST_BUNDLE_CANONICAL_SHA256
             and supervisor_claim.get("permanent_claim_sha256")
             == receipt["permanent_claim_sha256"]
             and supervisor_claim.get("automatic_retry") is False,
             "supervisor claim binding changed")
    for name in ("process_command_sha256", "supervisor_command_sha256",
                 "watchdog_head_sha256"):
        _sha256(supervisor_claim.get(name), f"supervisor claim {name}")

    supervisor_result, _ = _load_bound(
        receipt["supervisor_result_path"], root / "supervisor" / "result.json",
        receipt["supervisor_result_sha256"], "supervisor result")
    _require(supervisor_result == {
        "schema": SUPERVISOR_RESULT_SCHEMA,
        "cycle_id": child.CANARY_ID,
        "passed": True,
        "child_exit_code": 0,
        "incident_created": False,
        "incident_id": None,
        "budget_state": "none",
        "data_gate_status": "not_applicable",
        "automatic_retry": False,
        "watchdog_head_sha256": receipt["watchdog_head_sha256"],
    }, "supervisor terminal result changed")

    snapshot, _ = _load_bound(
        receipt["watchdog_snapshot_path"],
        root / "supervisor" / "watchdog" / "snapshot.json",
        receipt["watchdog_snapshot_sha256"], "watchdog snapshot")
    journal_path = _bound_path(
        receipt["watchdog_journal_path"],
        root / "supervisor" / "watchdog" / "journal.jsonl",
        "watchdog journal")
    journal_raw = child._read_regular(journal_path, "watchdog journal")
    _require(hashlib.sha256(journal_raw).hexdigest()
             == _sha256(receipt["watchdog_journal_sha256"], "watchdog journal"),
             "watchdog journal file commitment changed")
    _watchdog(journal_raw, snapshot, receipt["child_result_sha256"],
              supervisor_claim, release, expected_runtime_sha256)
    _require(snapshot["head_sha256"] == receipt["watchdog_head_sha256"],
             "watchdog head binding changed")

    terminal_clear, _ = _load_bound(
        receipt["terminal_clear_path"], root / "terminal-clear.json",
        receipt["terminal_clear_sha256"], "terminal clear")
    _require(terminal_clear == {
        "schema": TERMINAL_CLEAR_SCHEMA,
        "canary_id": child.CANARY_ID,
        "exact_processes": [],
        "exact_containers": [],
        "container_label": None,
        "terminal_cleanup_verified": True,
    }, "terminal exact-clear evidence changed")

    evidence = {
        "publication": receipt["publication_sha256"],
        "runtime": receipt["runtime_file_sha256"],
        "request_bundle": receipt["request_bundle_file_sha256"],
        "permanent_claim": receipt["permanent_claim_sha256"],
        "child_result": receipt["child_result_sha256"],
        "supervisor_claim": receipt["supervisor_claim_sha256"],
        "supervisor_result": receipt["supervisor_result_sha256"],
        "watchdog_journal": receipt["watchdog_journal_sha256"],
        "watchdog_snapshot": receipt["watchdog_snapshot_sha256"],
        "terminal_clear": receipt["terminal_clear_sha256"],
    }
    return {
        "schema": VERIFICATION_SCHEMA,
        "passed": True,
        "canary_id": child.CANARY_ID,
        "receipt_path": str(receipt_path),
        "receipt_sha256": expected_receipt_sha256,
        "release": release,
        "runtime_sha256": expected_runtime_sha256,
        "d0_evidence_sha256": dict(child.D0_FILE_SHA256),
        "request_plan_canonical_sha256": child.REQUEST_PLAN_CANONICAL_SHA256,
        "request_bundle_canonical_sha256": child.REQUEST_BUNDLE_CANONICAL_SHA256,
        "request_bundle_file_sha256": receipt["request_bundle_file_sha256"],
        "provider_calls": 0,
        "network_requests": 0,
        "actual_provider_cost_usd": "0",
        "external_bytes_received": 0,
        "public_fetch_performed": False,
        "snapshot_retained": False,
        "data_admitted": False,
        "train_dev_final_read": False,
        "training_or_evaluation_performed": False,
        "automatic_retry": False,
        "terminal_cleanup_verified": True,
        "evidence_sha256": evidence,
    }
