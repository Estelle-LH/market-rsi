"""Prepare one exact release-bound D0 documentation fetch.

This module is deliberately transport-free.  It accepts only the reviewed
source-scope request bundle, a canonical one-shot dual-authority document, a
fresh independently verified bridge canary, the current runtime receipt, and
the current controlled-source tree.  It emits the distinct task/admission
objects that the shared fetch seam may accept after integration.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
from typing import Any

from market_rsi import digest
from supervisor_harness import protocol_source_release
from supervisor_harness import p0_gate1_source_scope_request_plan as bridge


BINDING_SCHEMA = "market_p0_gate1_source_scope_fetch_binding_v1"
TASK_SCHEMA = "market_p0_gate1_source_scope_fetch_task_v1"
ADMISSION_SCHEMA = "market_p0_gate1_source_scope_fetch_admission_v1"
SNAPSHOT_RECEIPT_SCHEMA = (
    "market_p0_gate1_source_scope_public_snapshot_receipt_v1"
)
AUTHORIZATION_SCHEMA = "market_p0_gate1_source_scope_fetch_authorization_v1"
PARENT_CLAIM_SCHEMA = "market_p0_gate1_source_scope_fetch_parent_claim_v1"
CANARY_VERIFICATION_SCHEMA = (
    "market_p0_gate1_source_scope_request_plan_canary_verification_v1"
)

RELEASE_TAG = "market-rsi-protocol-v0.1.26"
CANARY_ID = "market-rsi-v0126-gate1-d0-bridge-first-current-source-20260928-01"
ATTEMPT_ID = "market-rsi-v0126-gate1-official-doc-fetch-20260928-01"
USER_HOME = Path(pwd.getpwuid(os.geteuid()).pw_dir)
MARKET_RSI_ROOT = (USER_HOME
                   / "Library" / "Application Support" / "MarketRSI")
PINNED_PYTHON = (USER_HOME / ".cache" / "market-rsi" / "runtimes" /
                 "ds-py312-20260912-01" / "bin" / "python")
RUN_ROOT = MARKET_RSI_ROOT / "runs" / ATTEMPT_ID
GLOBAL_STATE_ROOT = (MARKET_RSI_ROOT / "self-evolving-v18-local" /
                     "research" / "market_rsi" / "artifacts" /
                     "supervisor-global-state-20260917-01")
DECISION_DOC = MARKET_RSI_ROOT / "control" / "RESEARCH_STATE.md"
BUDGET_ROOT = MARKET_RSI_ROOT / "budget-authoritative-20260916-01"
SOURCE_ID = "polymarket_official_trades"
DOCUMENT_URL = (
    "https://docs.polymarket.com/api-reference/core/"
    "get-trades-for-a-user-or-markets"
)
DOCUMENT_URL_SHA256 = (
    "2f12d47b49fc82adafda53effcc7a11edaa9fbd85a6de9b9403cc90f86cfb3fc"
)
REQUEST_PLAN_SHA256 = (
    "34b45266df887dbf308b196eac865bfc5a3a6b65257c667849605e5a8b9b812c"
)
REQUEST_BUNDLE_SHA256 = (
    "7f340e20702a03200628cbad06f300257252d06a8b564985cbbf60ad8535b931"
)
FUTURE_REQUIREMENTS_SHA256 = (
    "d2641c593b83f97722e7fb261b78a87849af5236166645c095f72f5523ab023e"
)
REQUEST_HEADERS = {
    "Accept": "application/json,text/html,text/plain;q=0.9",
    "User-Agent": "MarketRSI-Public-Research/1.0",
}
MAX_RESPONSE_BYTES = 1_000_000
MAX_ELAPSED_SECONDS = 300
TRANSPORT_TIMEOUT_SECONDS = 15
MAX_REQUESTS = 1
PROVIDER_COST_USD = "0"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}\Z")
_AUTHORIZATION_FIELDS = {
    "schema", "attempt_id", "request_bundle_canonical_sha256",
    "request_plan_canonical_sha256", "document_url_sha256", "release",
    "runtime_sha256", "prior_canary_receipt_sha256",
    "prior_canary_verification_sha256", "output_root", "fetch_authorized",
    "snapshot_retention_authorized", "max_requests", "max_response_bytes",
    "max_elapsed_seconds", "transport_timeout_seconds", "provider_cost_usd",
    "redirects_allowed", "automatic_retries_allowed",
    "alternate_url_allowed", "credential_use_allowed", "purchase_allowed",
    "source_write_allowed", "formal_data_admission_authorized",
    "train_dev_final_access_authorized", "training_evaluation_authorized",
    "snapshot_redistribution_authorized", "prediction_claim_authorized",
}
_RELEASE_FIELDS = {"tag", "commit", "tag_object", "source_sha256"}
_CANARY_FIELDS = {
    "schema", "passed", "canary_id", "receipt_path", "receipt_sha256",
    "release", "runtime_sha256", "d0_evidence_sha256",
    "request_plan_canonical_sha256", "request_bundle_canonical_sha256",
    "request_bundle_file_sha256", "provider_calls", "network_requests",
    "actual_provider_cost_usd", "external_bytes_received",
    "public_fetch_performed", "snapshot_retained", "data_admitted",
    "train_dev_final_read", "training_or_evaluation_performed",
    "automatic_retry", "terminal_cleanup_verified", "evidence_sha256",
}
_D0_EVIDENCE_FIELDS = {
    "decision", "submission", "provenance", "raw_response", "packet",
    "publication", "result", "review",
}
_CANARY_EVIDENCE_FIELDS = {
    "publication", "runtime", "request_bundle", "permanent_claim",
    "child_result", "supervisor_claim", "supervisor_result",
    "watchdog_journal", "watchdog_snapshot", "terminal_clear",
}
TASK_FIELDS = frozenset({
    "schema", "attempt_id", "request_bundle_canonical_sha256",
    "request_plan_canonical_sha256", "authorization_file_sha256", "release",
    "runtime_sha256", "prior_canary_receipt_sha256",
    "prior_canary_verification_sha256", "source", "request", "bounds",
    "policy", "authority", "output_root",
})
ADMISSION_FIELDS = frozenset({
    "schema", "attempt_id", "task_canonical_sha256",
    "request_bundle_canonical_sha256", "request_plan_canonical_sha256",
    "authorization_file_sha256", "release_source_sha256", "runtime_sha256",
    "prior_canary_receipt_sha256", "prior_canary_verification_sha256",
    "source_id", "url_sha256", "fetch_authorized",
    "snapshot_retention_authorized", "max_requests", "max_response_bytes",
})
SOURCE_FIELDS = frozenset({"source_id", "url", "url_sha256"})
REQUEST_FIELDS = frozenset({"method", "query_parameters", "body",
                            "transport_headers"})
BOUNDS_FIELDS = frozenset({"max_requests", "max_response_bytes",
                           "max_elapsed_seconds", "transport_timeout_seconds",
                           "provider_cost_usd"})
POLICY_FIELDS = frozenset({"redirects_allowed", "automatic_retries_allowed",
                           "alternate_url_allowed", "credential_use_allowed",
                           "purchase_allowed", "source_write_allowed"})
AUTHORITY_FIELDS = frozenset({
    "network_fetch_authorized", "snapshot_retention_authorized",
    "formal_data_admission_authorized", "train_dev_final_access_authorized",
    "training_evaluation_authorized", "snapshot_redistribution_authorized",
    "prediction_claim_authorized",
})
CLAIM_BOUNDARY_FIELDS = frozenset({
    "one_attempt_only", "automatic_retry", "rights_proven",
    "formal_data_admitted", "train_dev_final_read",
    "training_or_evaluation_authorized", "snapshot_redistribution_authorized",
    "prediction_improvement_proven",
})
BINDING_FIELDS = frozenset({
    "schema", "task", "task_canonical_sha256", "admission",
    "admission_canonical_sha256", "authorization_file_sha256",
    "authorization_path",
    "canary_verification", "canary_verification_canonical_sha256",
    "current_source_sha256", "runtime_sha256", "output_root",
    "claim_boundaries",
})


def _sha256(value: object, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be lowercase SHA-256")
    return value


def _sha1(value: object, label: str) -> str:
    if type(value) is not str or _SHA1.fullmatch(value) is None:
        raise ValueError(f"{label} must be lowercase Git object ID")
    return value


def _exact(value: object, fields: set[str], label: str) -> dict:
    if type(value) is not dict or set(value) != fields:
        raise ValueError(f"{label} fields differ from exact schema")
    return value


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("ascii")


def _absolute_path(value: object, label: str) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        raise ValueError(f"canonical absolute {label} required")
    text = os.fspath(value)
    if (not isinstance(text, str) or not text.startswith("/") or text == "/"
            or text.endswith("/") or "//" in text or "\0" in text
            or any(part in {"", ".", "..", "~"} for part in value.parts[1:])
            or text != "/" + "/".join(value.parts[1:])):
        raise ValueError(f"canonical absolute {label} required")
    return value


def load_authorization(path: Path, *, expected_sha256: str) -> tuple[dict, str]:
    """Read one canonical, private, immutable authorization document."""
    path = _absolute_path(path, "authorization path")
    expected_sha256 = _sha256(expected_sha256, "authorization")
    ancestors = [Path("/")]
    cursor = Path("/")
    for part in path.parts[1:-1]:
        cursor = cursor / part
        ancestors.append(cursor)
    ancestor_before = []
    for ancestor in ancestors:
        item = os.lstat(ancestor)
        if not stat.S_ISDIR(item.st_mode) or stat.S_ISLNK(item.st_mode):
            raise ValueError("authorization ancestors must be real directories")
        ancestor_before.append((item.st_dev, item.st_ino, item.st_mode))
    named_before = os.lstat(path)
    if stat.S_ISLNK(named_before.st_mode) or path.resolve(strict=True) != path:
        raise ValueError("authorization path cannot use symlinks")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o600
                or not 0 < before.st_size <= 64 * 1024):
            raise ValueError("authorization must be a private bounded regular file")
        parts = []
        remaining = 64 * 1024 + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            parts.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(parts)
        after = os.fstat(descriptor)
        named_after = os.lstat(path)
    finally:
        os.close(descriptor)
    identity = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_size,
                             item.st_mtime_ns, item.st_ctime_ns)
    named_identity = lambda item: (
        item.st_dev, item.st_ino, item.st_mode, item.st_nlink, item.st_uid,
        item.st_size, item.st_mtime_ns, item.st_ctime_ns)
    ancestor_after = []
    for ancestor in ancestors:
        item = os.lstat(ancestor)
        if not stat.S_ISDIR(item.st_mode) or stat.S_ISLNK(item.st_mode):
            raise ValueError("authorization ancestors changed")
        ancestor_after.append((item.st_dev, item.st_ino, item.st_mode))
    named_closed = os.lstat(path)
    if (identity(before) != identity(after)
            or named_identity(named_before) != named_identity(before)
            or named_identity(named_after) != named_identity(after)
            or named_identity(named_closed) != named_identity(after)
            or ancestor_before != ancestor_after
            or len(raw) != before.st_size):
        raise ValueError("authorization changed while reading")
    observed = hashlib.sha256(raw).hexdigest()
    if observed != expected_sha256:
        raise ValueError("authorization file hash changed")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("authorization is not canonical JSON") from exc
    if raw != _canonical_bytes(value):
        raise ValueError("authorization bytes are not canonical")
    return _exact(value, _AUTHORIZATION_FIELDS, "authorization"), observed


def _validate_bundle(bundle: dict) -> dict:
    if (type(bundle) is not dict
            or set(bundle) != {"schema", "request_plan",
                               "request_plan_canonical_sha256",
                               "future_fetch_admission_requirements",
                               "claim_boundaries"}
            or digest(bundle) != REQUEST_BUNDLE_SHA256
            or bundle.get("request_plan_canonical_sha256") != REQUEST_PLAN_SHA256
            or digest(bundle.get("request_plan")) != REQUEST_PLAN_SHA256
            or digest(bundle.get("future_fetch_admission_requirements"))
            != FUTURE_REQUIREMENTS_SHA256):
        raise ValueError("request bundle differs from exact reviewed D0 bundle")
    plan = bundle["request_plan"]
    request = plan.get("prospective_request") if type(plan) is dict else None
    limits = plan.get("limits") if type(plan) is dict else None
    policy = plan.get("policy") if type(plan) is dict else None
    authority = plan.get("authority") if type(plan) is dict else None
    requirements = bundle["future_fetch_admission_requirements"]
    if (type(request) is not dict
            or request != {
                "request_id": "market-rsi-v0125-polymarket-trades-docs-01",
                "method": "GET", "url": DOCUMENT_URL,
                "url_sha256": DOCUMENT_URL_SHA256, "query_parameters": [],
                "body": None, "transport_headers": REQUEST_HEADERS}
            or type(limits) is not dict
            or limits.get("max_http_attempts_if_later_authorized") != MAX_REQUESTS
            or limits.get("max_response_bytes_if_later_authorized")
            != MAX_RESPONSE_BYTES
            or limits.get("max_elapsed_seconds_if_later_authorized")
            != MAX_ELAPSED_SECONDS
            or limits.get("transport_timeout_seconds_if_later_authorized")
            != TRANSPORT_TIMEOUT_SECONDS
            or limits.get("d0_provider_requests_proposed") != 0
            or limits.get("d0_provider_raw_bytes_proposed") != 0
            or limits.get("provider_cost_usd_micros") != 0
            or type(policy) is not dict
            or policy.get("redirects_allowed") is not False
            or policy.get("automatic_retries_allowed") is not False
            or policy.get("alternate_host_or_page_allowed") is not False
            or policy.get("link_following_allowed") is not False
            or policy.get("documented_api_call_allowed") is not False
            or policy.get("authentication_allowed") is not False
            or policy.get("credential_use_allowed") is not False
            or policy.get("purchase_allowed") is not False
            or policy.get("source_write_allowed") is not False
            or policy.get("failure_is_terminal_for_attempt") is not True
            or policy.get("preserve_failures_without_retry_expansion") is not True
            or policy.get("stop_on_first_rights_or_authority_unknown") is not True
            or type(authority) is not dict or authority.get("plan_only") is not True
            or any(value is not False for key, value in authority.items()
                   if key != "plan_only")
            or type(requirements) is not dict
            or requirements.get("fetch_authorized") is not False
            or requirements.get("must_bind_request_plan_canonical_sha256")
            != REQUEST_PLAN_SHA256
            or requirements.get("must_bind_scientific_source_id") != SOURCE_ID
            or requirements.get("must_bind_exact_url_sha256")
            != DOCUMENT_URL_SHA256
            or requirements.get("must_bind_max_requests") != MAX_REQUESTS
            or requirements.get("must_bind_max_response_bytes")
            != MAX_RESPONSE_BYTES):
        raise ValueError("request bundle safety boundary changed")
    return bundle


def _validate_release(value: object) -> dict:
    release = _exact(value, _RELEASE_FIELDS, "release")
    if release["tag"] != RELEASE_TAG:
        raise ValueError("wrong exact release tag")
    _sha1(release["commit"], "release commit")
    _sha1(release["tag_object"], "release tag object")
    _sha256(release["source_sha256"], "release source")
    return release


def _validate_canary(value: object, *, release: dict, runtime_sha256: str,
                     receipt_path: Path, receipt_sha256: str) -> dict:
    record = _exact(value, _CANARY_FIELDS, "canary verification")
    evidence = _exact(record["d0_evidence_sha256"], _D0_EVIDENCE_FIELDS,
                      "D0 evidence")
    for name, item in evidence.items():
        _sha256(item, f"D0 evidence {name}")
    canary_evidence = _exact(
        record["evidence_sha256"], _CANARY_EVIDENCE_FIELDS,
        "canary evidence")
    for name, item in canary_evidence.items():
        _sha256(item, f"canary evidence {name}")
    for name in ("receipt_sha256", "request_bundle_file_sha256"):
        _sha256(record[name], f"canary {name}")
    if (record["schema"] != CANARY_VERIFICATION_SCHEMA
            or record["passed"] is not True
            or record["canary_id"] != CANARY_ID
            or record["receipt_path"] != str(receipt_path)
            or record["receipt_sha256"] != receipt_sha256
            or record["release"] != release
            or record["runtime_sha256"] != runtime_sha256
            or record["request_plan_canonical_sha256"] != REQUEST_PLAN_SHA256
            or record["request_bundle_canonical_sha256"] != REQUEST_BUNDLE_SHA256
            or type(record["provider_calls"]) is not int
            or record["provider_calls"] != 0
            or type(record["network_requests"]) is not int
            or record["network_requests"] != 0
            or record["actual_provider_cost_usd"] != "0"
            or type(record["external_bytes_received"]) is not int
            or record["external_bytes_received"] != 0
            or any(record[name] is not False for name in (
                "public_fetch_performed", "snapshot_retained", "data_admitted",
                "train_dev_final_read", "training_or_evaluation_performed",
                "automatic_retry"))
            or record["terminal_cleanup_verified"] is not True):
        raise ValueError("canary did not prove exact zero-effect bridge boundary")
    return record


def _verify_canary_receipt(path: Path, **expected: object) -> dict:
    # Delayed import lets this component merge independently; the integrated
    # source must provide the pure verifier before any live execution.
    from supervisor_harness.source_scope_request_plan_canary_receipt import (
        verify_canary_receipt,
    )
    return verify_canary_receipt(path, **expected)


def prepare_execution_binding(
        bundle: dict,
        *,
        d0_decision: dict,
        d0_decision_provenance: dict,
        d0_packet: dict,
        authorization_path: Path,
        expected_authorization_sha256: str,
        canary_receipt_path: Path,
        expected_canary_receipt_sha256: str,
        runtime_receipt: dict,
        output_root: Path,
) -> dict:
    """Return the only distinct task/admission pair for the authorized fetch."""
    bundle = _validate_bundle(bundle)
    first_compile = bridge.compile_document_request_plan(
        d0_decision, d0_decision_provenance, d0_packet,
        d0_source_sha256=bridge.D0_CONTROLLED_SOURCE_SHA256)
    second_compile = bridge.compile_document_request_plan(
        d0_decision, d0_decision_provenance, d0_packet,
        d0_source_sha256=bridge.D0_CONTROLLED_SOURCE_SHA256)
    if (first_compile != second_compile or first_compile != bundle
            or digest(first_compile) != REQUEST_BUNDLE_SHA256):
        raise ValueError("D0 evidence does not recompile to the reviewed bundle")
    authorization, authorization_sha256 = load_authorization(
        authorization_path, expected_sha256=expected_authorization_sha256)
    output_root = _absolute_path(output_root, "output root")
    canary_receipt_path = _absolute_path(canary_receipt_path, "canary receipt")
    canary_receipt_sha256 = _sha256(
        expected_canary_receipt_sha256, "canary receipt")
    runtime_sha256 = digest(runtime_receipt)
    current_source_hashes = protocol_source_release.source_hashes()
    current_source_sha256 = digest(current_source_hashes)
    release = _validate_release(authorization["release"])
    if release["source_sha256"] != current_source_sha256:
        raise ValueError("current controlled source differs from authorized release")
    canary = _verify_canary_receipt(
        canary_receipt_path,
        expected_receipt_sha256=canary_receipt_sha256,
        expected_source_sha256=current_source_sha256,
        expected_runtime_sha256=runtime_sha256,
        expected_release_tag=release["tag"],
        expected_release_commit=release["commit"],
        expected_release_tag_object=release["tag_object"],
    )
    canary = _validate_canary(
        canary, release=release, runtime_sha256=runtime_sha256,
        receipt_path=canary_receipt_path, receipt_sha256=canary_receipt_sha256)
    canary_verification_sha256 = digest(canary)
    false_fields = (
        "redirects_allowed", "automatic_retries_allowed",
        "alternate_url_allowed", "credential_use_allowed", "purchase_allowed",
        "source_write_allowed", "formal_data_admission_authorized",
        "train_dev_final_access_authorized", "training_evaluation_authorized",
        "snapshot_redistribution_authorized", "prediction_claim_authorized",
    )
    if (authorization["schema"] != AUTHORIZATION_SCHEMA
            or authorization["attempt_id"] != ATTEMPT_ID
            or not _ID.fullmatch(authorization["attempt_id"])
            or authorization["request_bundle_canonical_sha256"]
            != REQUEST_BUNDLE_SHA256
            or authorization["request_plan_canonical_sha256"]
            != REQUEST_PLAN_SHA256
            or authorization["document_url_sha256"] != DOCUMENT_URL_SHA256
            or authorization["runtime_sha256"] != runtime_sha256
            or authorization["prior_canary_receipt_sha256"]
            != canary_receipt_sha256
            or authorization["prior_canary_verification_sha256"]
            != canary_verification_sha256
            or authorization["output_root"] != str(output_root)
            or output_root != RUN_ROOT
            or authorization["fetch_authorized"] is not True
            or authorization["snapshot_retention_authorized"] is not True
            or type(authorization["max_requests"]) is not int
            or authorization["max_requests"] != MAX_REQUESTS
            or type(authorization["max_response_bytes"]) is not int
            or authorization["max_response_bytes"] != MAX_RESPONSE_BYTES
            or type(authorization["max_elapsed_seconds"]) is not int
            or authorization["max_elapsed_seconds"] != MAX_ELAPSED_SECONDS
            or type(authorization["transport_timeout_seconds"]) is not int
            or authorization["transport_timeout_seconds"]
            != TRANSPORT_TIMEOUT_SECONDS
            or authorization["provider_cost_usd"] != PROVIDER_COST_USD
            or any(authorization[name] is not False for name in false_fields)):
        raise ValueError("authorization differs from exact one-shot scope")
    task = {
        "schema": TASK_SCHEMA,
        "attempt_id": ATTEMPT_ID,
        "request_bundle_canonical_sha256": REQUEST_BUNDLE_SHA256,
        "request_plan_canonical_sha256": REQUEST_PLAN_SHA256,
        "authorization_file_sha256": authorization_sha256,
        "release": release,
        "runtime_sha256": runtime_sha256,
        "prior_canary_receipt_sha256": canary_receipt_sha256,
        "prior_canary_verification_sha256": canary_verification_sha256,
        "source": {"source_id": SOURCE_ID, "url": DOCUMENT_URL,
                   "url_sha256": DOCUMENT_URL_SHA256},
        "request": {"method": "GET", "query_parameters": [], "body": None,
                    "transport_headers": dict(REQUEST_HEADERS)},
        "bounds": {"max_requests": MAX_REQUESTS,
                   "max_response_bytes": MAX_RESPONSE_BYTES,
                   "max_elapsed_seconds": MAX_ELAPSED_SECONDS,
                   "transport_timeout_seconds": TRANSPORT_TIMEOUT_SECONDS,
                   "provider_cost_usd": PROVIDER_COST_USD},
        "policy": {"redirects_allowed": False,
                   "automatic_retries_allowed": False,
                   "alternate_url_allowed": False,
                   "credential_use_allowed": False,
                   "purchase_allowed": False,
                   "source_write_allowed": False},
        "authority": {"network_fetch_authorized": True,
                      "snapshot_retention_authorized": True,
                      "formal_data_admission_authorized": False,
                      "train_dev_final_access_authorized": False,
                      "training_evaluation_authorized": False,
                      "snapshot_redistribution_authorized": False,
                      "prediction_claim_authorized": False},
        "output_root": str(output_root),
    }
    task_sha256 = digest(task)
    admission = {
        "schema": ADMISSION_SCHEMA, "attempt_id": ATTEMPT_ID,
        "task_canonical_sha256": task_sha256,
        "request_bundle_canonical_sha256": REQUEST_BUNDLE_SHA256,
        "request_plan_canonical_sha256": REQUEST_PLAN_SHA256,
        "authorization_file_sha256": authorization_sha256,
        "release_source_sha256": current_source_sha256,
        "runtime_sha256": runtime_sha256,
        "prior_canary_receipt_sha256": canary_receipt_sha256,
        "prior_canary_verification_sha256": canary_verification_sha256,
        "source_id": SOURCE_ID, "url_sha256": DOCUMENT_URL_SHA256,
        "fetch_authorized": True, "snapshot_retention_authorized": True,
        "max_requests": MAX_REQUESTS,
        "max_response_bytes": MAX_RESPONSE_BYTES,
    }
    binding = {
        "schema": BINDING_SCHEMA,
        "task": task,
        "task_canonical_sha256": task_sha256,
        "admission": admission,
        "admission_canonical_sha256": digest(admission),
        "authorization_file_sha256": authorization_sha256,
        "authorization_path": str(authorization_path),
        "canary_verification": canary,
        "canary_verification_canonical_sha256": canary_verification_sha256,
        "current_source_sha256": current_source_sha256,
        "runtime_sha256": runtime_sha256,
        "output_root": str(output_root),
        "claim_boundaries": {
            "one_attempt_only": True, "automatic_retry": False,
            "rights_proven": False, "formal_data_admitted": False,
            "train_dev_final_read": False,
            "training_or_evaluation_authorized": False,
            "snapshot_redistribution_authorized": False,
            "prediction_improvement_proven": False,
        },
    }
    return validate_execution_binding(binding)


def validate_task_admission(task: object, admission: object) -> tuple[dict, dict]:
    """Validate the distinct closed task/admission language, without I/O."""
    task = _exact(task, TASK_FIELDS, "source-scope fetch task")
    admission = _exact(admission, ADMISSION_FIELDS, "source-scope admission")
    release = _validate_release(task["release"])
    source = _exact(task["source"], SOURCE_FIELDS, "task source")
    request = _exact(task["request"], REQUEST_FIELDS, "task request")
    bounds = _exact(task["bounds"], BOUNDS_FIELDS, "task bounds")
    policy = _exact(task["policy"], POLICY_FIELDS, "task policy")
    authority = _exact(task["authority"], AUTHORITY_FIELDS, "task authority")
    if type(task["output_root"]) is not str:
        raise ValueError("task output root must be a canonical absolute path")
    output_root = _absolute_path(Path(task["output_root"]), "task output root")
    for name in ("authorization_file_sha256", "runtime_sha256",
                 "prior_canary_receipt_sha256",
                 "prior_canary_verification_sha256"):
        _sha256(task[name], f"task {name}")
    if (task["schema"] != TASK_SCHEMA
            or task["attempt_id"] != ATTEMPT_ID
            or task["request_bundle_canonical_sha256"] != REQUEST_BUNDLE_SHA256
            or task["request_plan_canonical_sha256"] != REQUEST_PLAN_SHA256
            or source != {"source_id": SOURCE_ID, "url": DOCUMENT_URL,
                          "url_sha256": DOCUMENT_URL_SHA256}
            or request != {"method": "GET", "query_parameters": [],
                           "body": None, "transport_headers": REQUEST_HEADERS}
            or bounds != {"max_requests": MAX_REQUESTS,
                          "max_response_bytes": MAX_RESPONSE_BYTES,
                          "max_elapsed_seconds": MAX_ELAPSED_SECONDS,
                          "transport_timeout_seconds": TRANSPORT_TIMEOUT_SECONDS,
                          "provider_cost_usd": PROVIDER_COST_USD}
            or policy != {"redirects_allowed": False,
                          "automatic_retries_allowed": False,
                          "alternate_url_allowed": False,
                          "credential_use_allowed": False,
                          "purchase_allowed": False,
                          "source_write_allowed": False}
            or authority != {"network_fetch_authorized": True,
                             "snapshot_retention_authorized": True,
                             "formal_data_admission_authorized": False,
                             "train_dev_final_access_authorized": False,
                             "training_evaluation_authorized": False,
                             "snapshot_redistribution_authorized": False,
                             "prediction_claim_authorized": False}
            or output_root != RUN_ROOT):
        raise ValueError("source-scope fetch task changed")
    for name in ("task_canonical_sha256", "authorization_file_sha256",
                 "release_source_sha256", "runtime_sha256",
                 "prior_canary_receipt_sha256",
                 "prior_canary_verification_sha256"):
        _sha256(admission[name], f"admission {name}")
    if (admission["schema"] != ADMISSION_SCHEMA
            or admission["attempt_id"] != ATTEMPT_ID
            or admission["task_canonical_sha256"] != digest(task)
            or admission["request_bundle_canonical_sha256"]
            != REQUEST_BUNDLE_SHA256
            or admission["request_plan_canonical_sha256"] != REQUEST_PLAN_SHA256
            or admission["authorization_file_sha256"]
            != task["authorization_file_sha256"]
            or admission["release_source_sha256"] != release["source_sha256"]
            or admission["runtime_sha256"] != task["runtime_sha256"]
            or admission["prior_canary_receipt_sha256"]
            != task["prior_canary_receipt_sha256"]
            or admission["prior_canary_verification_sha256"]
            != task["prior_canary_verification_sha256"]
            or admission["source_id"] != SOURCE_ID
            or admission["url_sha256"] != DOCUMENT_URL_SHA256
            or admission["fetch_authorized"] is not True
            or admission["snapshot_retention_authorized"] is not True
            or type(admission["max_requests"]) is not int
            or admission["max_requests"] != MAX_REQUESTS
            or type(admission["max_response_bytes"]) is not int
            or admission["max_response_bytes"] != MAX_RESPONSE_BYTES):
        raise ValueError("source-scope fetch admission changed")
    return task, admission


def validate_execution_binding(value: object) -> dict:
    """Independently recheck a prepared binding before any child or transport."""
    binding = _exact(value, BINDING_FIELDS, "execution binding")
    task, admission = validate_task_admission(
        binding["task"], binding["admission"])
    for name in ("task_canonical_sha256", "admission_canonical_sha256",
                 "authorization_file_sha256",
                 "canary_verification_canonical_sha256",
                 "current_source_sha256", "runtime_sha256"):
        _sha256(binding[name], f"binding {name}")
    canary = binding["canary_verification"]
    if (type(binding["authorization_path"]) is not str
            or _absolute_path(Path(binding["authorization_path"]),
                              "binding authorization")
            != Path(binding["authorization_path"])):
        raise ValueError("binding authorization path changed")
    if type(canary) is not dict or type(canary.get("receipt_path")) is not str:
        raise ValueError("execution canary link changed")
    canary_path = _absolute_path(
        Path(canary["receipt_path"]), "binding canary receipt")
    canary = _validate_canary(
        canary, release=task["release"], runtime_sha256=task["runtime_sha256"],
        receipt_path=canary_path,
        receipt_sha256=task["prior_canary_receipt_sha256"])
    boundaries = _exact(binding["claim_boundaries"], CLAIM_BOUNDARY_FIELDS,
                        "execution claim boundaries")
    if (binding["schema"] != BINDING_SCHEMA
            or binding["task_canonical_sha256"] != digest(task)
            or binding["admission_canonical_sha256"] != digest(admission)
            or binding["authorization_file_sha256"]
            != task["authorization_file_sha256"]
            or binding["canary_verification_canonical_sha256"] != digest(canary)
            or task["prior_canary_verification_sha256"] != digest(canary)
            or binding["current_source_sha256"] != task["release"]["source_sha256"]
            or binding["runtime_sha256"] != task["runtime_sha256"]
            or binding["output_root"] != task["output_root"]
            or boundaries != {"one_attempt_only": True,
                              "automatic_retry": False,
                              "rights_proven": False,
                              "formal_data_admitted": False,
                              "train_dev_final_read": False,
                              "training_or_evaluation_authorized": False,
                              "snapshot_redistribution_authorized": False,
                              "prediction_improvement_proven": False}):
        raise ValueError("execution binding changed")
    return binding
