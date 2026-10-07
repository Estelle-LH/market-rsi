"""Child-side execution for one exact source-scope documentation fetch.

The live shared fetch seam is resolved lazily and does not exist until the
integration step adds the distinct schema path.  No command-line or callable
transport injection exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from typing import Callable

# The parent launches this exact file with ``python -I -B`` and a minimal
# environment.  Add only the controlled source root derived from this file;
# never inherit cwd, PYTHONPATH or a sitecustomize hook.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market_rsi import digest, fresh_json
from paid_budget import PaidBudget
from supervisor_harness.global_state_gate import SupervisorGlobalState
from supervisor_harness.p0_gate1_source_scope_fetch_adapter import (
    ADMISSION_SCHEMA, ATTEMPT_ID, BUDGET_ROOT, DECISION_DOC,
    DOCUMENT_URL_SHA256, GLOBAL_STATE_ROOT, MAX_RESPONSE_BYTES,
    PARENT_CLAIM_SCHEMA, RUN_ROOT, SNAPSHOT_RECEIPT_SCHEMA, SOURCE_ID,
    TASK_SCHEMA, validate_execution_binding,
)
from supervisor_harness.supervisor_watchdog import SupervisorWatchdog
from supervisor_harness.supervisor_watchdog_local_control import (
    process_command_sha256,
)


RESULT_SCHEMA = "market_p0_gate1_source_scope_fetch_child_result_v1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
TASK_ID = ATTEMPT_ID + "-watched-fetch"
RECEIPT_FIELDS = frozenset({
    "schema", "attempt_id", "task_canonical_sha256",
    "admission_canonical_sha256", "request_plan_canonical_sha256",
    "authorization_file_sha256", "release_source_sha256", "source_id",
    "url_sha256", "final_url", "content_type", "content_encoding",
    "status", "response_headers",
    "snapshot_bytes", "snapshot_sha256", "requests_made",
    "redirects_followed", "automatic_retries", "provider_calls",
    "actual_provider_cost_usd", "rights_proven", "sealed_data_read",
    "formal_data_admitted", "train_dev_final_read",
    "training_or_evaluation_performed", "snapshot_redistributed",
    "prediction_improvement_proven",
})
RESULT_FIELDS = frozenset({
    "schema", "attempt_id", "passed", "task_id", "input_sha256",
    "task_canonical_sha256", "admission_canonical_sha256",
    "receipt_file_sha256", "snapshot_sha256", "snapshot_bytes",
    "final_url", "content_encoding",
    "requests_made", "redirects_followed", "automatic_retries",
    "provider_calls", "actual_provider_cost_usd", "rights_proven",
    "formal_data_admitted", "train_dev_final_read",
    "training_or_evaluation_performed", "snapshot_redistributed",
    "prediction_improvement_proven",
})
PARENT_CLAIM_FIELDS = frozenset({
    "schema", "task_id", "binding_canonical_sha256", "pid",
    "process_command_sha256", "budget_snapshot_sha256",
    "watchdog_head_sha256", "automatic_retry",
    "binding_path", "output_path", "watchdog_root", "claim_path",
    "parent_pid", "parent_command_sha256", "global_state_root",
    "global_state_head_sha256", "decision_doc_path",
    "decision_doc_sha256", "budget_root",
})


def _sha(value: object, label: str) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise ValueError(f"{label} must be lowercase SHA-256")
    return value


def _shared_preclaimed_runner() -> Callable:
    from supervisor_harness import p0_gate1_watched_fetch
    runner = getattr(p0_gate1_watched_fetch, "run_preclaimed", None)
    if not callable(runner):
        raise RuntimeError("source-scope preclaimed runner is not integrated")
    return runner


def _read_regular(path: Path, label: str, *, limit: int) -> bytes:
    path = Path(path)
    if not path.is_absolute():
        raise ValueError(f"{label} path must be absolute")
    ancestors = []
    cursor = Path(path.anchor)
    for part in path.parts[1:-1]:
        cursor = cursor / part
        item = os.lstat(cursor)
        if not stat.S_ISDIR(item.st_mode) or stat.S_ISLNK(item.st_mode):
            raise ValueError(f"{label} ancestor is unsafe")
        ancestors.append((cursor, (item.st_dev, item.st_ino, item.st_mode)))
    named_before = os.lstat(path)
    if (stat.S_ISLNK(named_before.st_mode)
            or not stat.S_ISREG(named_before.st_mode)
            or named_before.st_nlink != 1
            or not 0 < named_before.st_size <= limit
            or path.resolve(strict=True) != path):
        raise ValueError(f"{label} must be one canonical regular file")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                         | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(descriptor)
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
    identity = lambda item: (item.st_dev, item.st_ino, item.st_mode,
                             item.st_nlink, item.st_size, item.st_mtime_ns,
                             item.st_ctime_ns)
    if (identity(named_before) != identity(before)
            or identity(after) != identity(before)
            or identity(named_after) != identity(after)
            or identity(named_closed) != identity(after)
            or len(raw) != before.st_size):
        raise ValueError(f"{label} changed while reading")
    for ancestor, expected in ancestors:
        item = os.lstat(ancestor)
        if (not stat.S_ISDIR(item.st_mode) or stat.S_ISLNK(item.st_mode)
                or (item.st_dev, item.st_ino, item.st_mode) != expected):
            raise ValueError(f"{label} ancestor changed while reading")
    return raw


def _validate_receipt(receipt: object, binding: dict, snapshot: Path) -> dict:
    if type(receipt) is not dict or set(receipt) != RECEIPT_FIELDS:
        raise ValueError("source-scope snapshot receipt fields differ")
    task = binding["task"]
    admission = binding["admission"]
    headers = receipt["response_headers"]
    if (receipt["schema"] != SNAPSHOT_RECEIPT_SCHEMA
            or receipt["attempt_id"] != ATTEMPT_ID
            or receipt["task_canonical_sha256"] != digest(task)
            or receipt["admission_canonical_sha256"] != digest(admission)
            or receipt["request_plan_canonical_sha256"]
            != task["request_plan_canonical_sha256"]
            or receipt["authorization_file_sha256"]
            != task["authorization_file_sha256"]
            or receipt["release_source_sha256"]
            != binding["current_source_sha256"]
            or receipt["source_id"] != SOURCE_ID
            or receipt["url_sha256"] != DOCUMENT_URL_SHA256
            or receipt["final_url"] != task["source"]["url"]
            or receipt["content_encoding"] is not None
            or receipt["status"] != 200
            or receipt["content_type"] not in {
                "application/json", "text/html", "text/markdown", "text/plain"}
            or type(headers) is not dict
            or any(key not in {"etag", "last-modified"} for key in headers)
            or any(type(value) is not str
                   or len(value.encode("utf-8")) > 500
                   for value in headers.values())
            or type(receipt["snapshot_bytes"]) is not int
            or not 0 < receipt["snapshot_bytes"] <= MAX_RESPONSE_BYTES
            or type(receipt["requests_made"]) is not int
            or receipt["requests_made"] != 1
            or type(receipt["redirects_followed"]) is not int
            or receipt["redirects_followed"] != 0
            or type(receipt["automatic_retries"]) is not int
            or receipt["automatic_retries"] != 0
            or type(receipt["provider_calls"]) is not int
            or receipt["provider_calls"] != 0
            or receipt["actual_provider_cost_usd"] != "0"
            or any(receipt[name] is not False for name in (
                "rights_proven", "sealed_data_read", "formal_data_admitted",
                "train_dev_final_read", "training_or_evaluation_performed",
                "snapshot_redistributed", "prediction_improvement_proven"))):
        raise ValueError("source-scope snapshot receipt violates exact boundary")
    if snapshot.is_symlink() or not snapshot.is_file():
        raise ValueError("exact regular snapshot required")
    raw = _read_regular(snapshot, "public snapshot", limit=MAX_RESPONSE_BYTES)
    if (len(raw) != receipt["snapshot_bytes"]
            or hashlib.sha256(raw).hexdigest() != _sha(
                receipt["snapshot_sha256"], "snapshot")):
        raise ValueError("snapshot bytes differ from receipt")
    return receipt


def execute(
        *, binding: dict, output: Path, watchdog: SupervisorWatchdog,
        pid: int, process_command_sha256: str, budget_snapshot_sha256: str,
        clock=None,
) -> dict:
    """Execute exactly once under an initialized watchdog."""
    binding = validate_execution_binding(binding)
    if type(pid) is not int or pid <= 1:
        raise ValueError("real child PID required")
    _sha(process_command_sha256, "process command")
    _sha(budget_snapshot_sha256, "budget snapshot")
    output = Path(output)
    if (not output.is_absolute() or output.name != "snapshot"
            or output.parent != Path(binding["output_root"])
            or output.exists() or output.is_symlink()):
        raise ValueError("fresh exact snapshot output required")
    runner = _shared_preclaimed_runner()
    if not callable(runner):
        raise ValueError("exact preclaimed runner required")
    input_sha256 = digest({"task": binding["task"],
                           "admission": binding["admission"]})
    receipt_path = output / "receipt.json"
    snapshot_path = output / "public-source.snapshot"
    receipt = runner(
        watchdog=watchdog, task_id=TASK_ID, task=binding["task"],
        admission=binding["admission"], output=output, pid=pid,
        process_command_sha256=process_command_sha256,
        budget_snapshot_sha256=budget_snapshot_sha256,
        receipt_validator=lambda value, path: _validate_receipt(
            value, binding, Path(path)), clock=clock)
    _validate_receipt(receipt, binding, snapshot_path)
    receipt_raw = _read_regular(
        receipt_path, "snapshot receipt", limit=256 * 1024)
    expected_raw = (json.dumps(
        receipt, ensure_ascii=True, allow_nan=False, sort_keys=True,
        separators=(",", ":")) + "\n").encode("ascii")
    if receipt_raw != expected_raw:
        raise ValueError("snapshot receipt is not canonical")
    receipt_sha256 = hashlib.sha256(receipt_raw).hexdigest()
    result = {
        "schema": RESULT_SCHEMA, "attempt_id": ATTEMPT_ID, "passed": True,
        "task_id": TASK_ID, "input_sha256": input_sha256,
        "task_canonical_sha256": digest(binding["task"]),
        "admission_canonical_sha256": digest(binding["admission"]),
        "receipt_file_sha256": receipt_sha256,
        "snapshot_sha256": receipt["snapshot_sha256"],
        "snapshot_bytes": receipt["snapshot_bytes"],
        "final_url": receipt["final_url"],
        "content_encoding": receipt["content_encoding"],
        "requests_made": 1, "redirects_followed": 0,
        "automatic_retries": 0, "provider_calls": 0,
        "actual_provider_cost_usd": "0", "rights_proven": False,
        "formal_data_admitted": False, "train_dev_final_read": False,
        "training_or_evaluation_performed": False,
        "snapshot_redistributed": False,
        "prediction_improvement_proven": False,
    }
    fresh_json(Path(binding["output_root"]) / "child-result.json", result)
    return result


def _read_canonical(path: Path, *, limit: int = 2 * 1024 * 1024) -> dict:
    raw = _read_regular(Path(path), "canonical JSON", limit=limit)
    value = json.loads(raw)
    expected = (json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True,
        separators=(",", ":")) + "\n").encode("ascii")
    if type(value) is not dict or raw != expected:
        raise ValueError("canonical JSON object required")
    return value


def _wait_for_claim(path: Path, *, seconds: float = 10.0) -> dict:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists() or path.is_symlink():
            return _read_canonical(path, limit=16 * 1024)
        time.sleep(0.02)
    raise TimeoutError("outer parent claim was not installed")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Run the exact preclaimed source-scope fetch child")
    value.add_argument("--binding", required=True, type=Path)
    value.add_argument("--expected-binding-sha256", required=True)
    value.add_argument("--output", required=True, type=Path)
    value.add_argument("--watchdog-root", required=True, type=Path)
    value.add_argument("--supervisor-claim", required=True, type=Path)
    value.add_argument("--budget-snapshot-sha256", required=True)
    return value


def main(args) -> dict:
    expected_binding_path = RUN_ROOT / "binding.json"
    expected_output = RUN_ROOT / "snapshot"
    expected_watchdog = RUN_ROOT / "watchdog"
    expected_claim = RUN_ROOT / "supervisor-claim.json"
    if (Path(args.binding) != expected_binding_path
            or Path(args.output) != expected_output
            or Path(args.watchdog_root) != expected_watchdog
            or Path(args.supervisor_claim) != expected_claim):
        raise ValueError("child paths differ from the sole durable run root")
    binding = validate_execution_binding(_read_canonical(args.binding))
    expected_binding = _sha(args.expected_binding_sha256, "binding")
    if digest(binding) != expected_binding:
        raise ValueError("binding canonical hash changed")
    budget_sha256 = _sha(args.budget_snapshot_sha256, "budget snapshot")
    claim = _wait_for_claim(Path(args.supervisor_claim))
    if set(claim) != PARENT_CLAIM_FIELDS:
        raise ValueError("parent claim fields differ")
    watchdog = SupervisorWatchdog(args.watchdog_root)
    watchdog_state = watchdog.snapshot()
    parent_observed, parent_present = process_command_sha256(
        claim.get("parent_pid"))
    global_state = SupervisorGlobalState(GLOBAL_STATE_ROOT, DECISION_DOC).snapshot()
    budget = PaidBudget(BUDGET_ROOT).snapshot()
    if (claim["schema"] != PARENT_CLAIM_SCHEMA
            or claim["task_id"] != TASK_ID
            or claim["binding_canonical_sha256"] != expected_binding
            or claim["pid"] != os.getpid()
            or claim["process_command_sha256"]
            != watchdog_state.get("active_task", {}).get(
                "process_identity", {}).get("command_sha256")
            or claim["budget_snapshot_sha256"] != budget_sha256
            or claim["watchdog_head_sha256"] != watchdog_state["head_sha256"]
            or claim["binding_path"] != str(expected_binding_path)
            or claim["output_path"] != str(expected_output)
            or claim["watchdog_root"] != str(expected_watchdog)
            or claim["claim_path"] != str(expected_claim)
            or claim["parent_pid"] != os.getppid()
            or not parent_present
            or claim["parent_command_sha256"] != parent_observed
            or claim["global_state_root"] != str(GLOBAL_STATE_ROOT)
            or claim["global_state_head_sha256"]
            != global_state["head_sha256"]
            or global_state["active_cycle"] != ATTEMPT_ID
            or claim["decision_doc_path"] != str(DECISION_DOC)
            or claim["decision_doc_sha256"]
            != global_state["decision_doc_sha256"]
            or claim["budget_root"] != str(BUDGET_ROOT)
            or digest(budget) != budget_sha256
            or ATTEMPT_ID in budget.get("jobs", {})
            or claim["automatic_retry"] is not False):
        raise ValueError("parent claim does not bind this child")
    return execute(
        binding=binding, output=Path(args.output), watchdog=watchdog,
        pid=os.getpid(),
        process_command_sha256=claim["process_command_sha256"],
        budget_snapshot_sha256=budget_sha256)


if __name__ == "__main__":
    print(json.dumps(main(parser().parse_args()), sort_keys=True))
