"""Outer owner for one exact release-bound source-scope documentation fetch."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import stat
import sys
import time

from market_rsi import digest, file_hash, fresh_json
from paid_budget import PaidBudget
from supervisor_harness.global_state_gate import SupervisorGlobalState
from supervisor_harness.p0_gate1_source_scope_fetch_adapter import (
    ATTEMPT_ID, BUDGET_ROOT, DECISION_DOC, GLOBAL_STATE_ROOT, MARKET_RSI_ROOT,
    MAX_ELAPSED_SECONDS, PARENT_CLAIM_SCHEMA, PINNED_PYTHON,
    RUN_ROOT, prepare_execution_binding, validate_execution_binding,
    load_authorization,
)
from supervisor_harness import p0_gate1_source_scope_watched_fetch_child as child_entry
from supervisor_harness import protocol_source_release
from supervisor_harness import run_p0_gate1_source_scope_request_plan_canary as bridge_canary_runner
from supervisor_harness import source_scope_request_plan_canary_receipt as canary_receipt
from supervisor_harness.supervisor_watchdog import SupervisorWatchdog
from supervisor_harness.supervisor_watchdog_local_control import (
    LocalProcessDockerControl, container_identity, process_command_sha256,
    stable_process_command_sha256,
)


RESULT_SCHEMA = "market_p0_gate1_source_scope_watched_fetch_parent_result_v1"
FAILURE_SCHEMA = "market_p0_gate1_source_scope_watched_fetch_failure_v1"
RUNS_ROOT = MARKET_RSI_ROOT / "runs"
D0_ROOT = RUNS_ROOT / "market-rsi-v0125-gate1-controller-d0-20260928-01"
D0_ADAPTER_ROOT = D0_ROOT / "adapter" / "market-rsi-v0125-gate1-controller-d0-20260928-01"
D0_DECISION = D0_ADAPTER_ROOT / "decision.json"
D0_PROVENANCE = D0_ADAPTER_ROOT / "decision-provenance.json"
D0_PACKET = (RUNS_ROOT /
             "market-rsi-v0125-gate1-first-current-source-20260928-01" /
             "controller-input.json")
CONTAINER_NAME = "market-rsi-b-" + ATTEMPT_ID
CONTAINER_LABEL = ATTEMPT_ID
RESULT_FIELDS = frozenset({
    "schema", "attempt_id", "passed", "task_id", "child_pid",
    "process_command_sha256", "binding_canonical_sha256",
    "binding_path", "binding_file_sha256", "parent_claim_path",
    "parent_claim_file_sha256", "child_result_path",
    "child_result_file_sha256", "watchdog_journal_path",
    "watchdog_journal_file_sha256", "watchdog_snapshot_path",
    "watchdog_snapshot_file_sha256",
    "task_canonical_sha256", "admission_canonical_sha256",
    "authorization_file_sha256", "prior_canary_receipt_sha256",
    "prior_canary_verification_sha256", "receipt_path",
    "receipt_file_sha256", "snapshot_path", "snapshot_sha256",
    "snapshot_bytes", "final_url", "content_encoding", "requests_made",
    "redirects_followed",
    "automatic_retries", "provider_calls", "actual_provider_cost_usd",
    "rights_proven", "formal_data_admitted", "train_dev_final_read",
    "training_or_evaluation_performed", "snapshot_redistributed",
    "prediction_improvement_proven", "child_exit_code",
    "terminal_process_absent", "terminal_container_absent",
    "watchdog_head_sha256", "watchdog_seq",
    "global_state_head_sha256", "global_state_status",
    "budget_snapshot_sha256", "budget_state",
    "global_state_journal_path", "global_state_journal_file_sha256",
    "decision_doc_path", "decision_doc_sha256", "budget_root",
    "authorization_copy_path", "authorization_copy_file_sha256",
    "request_bundle_path", "request_bundle_file_sha256",
    "runtime_receipt_path", "runtime_receipt_file_sha256",
    "canary_verification_path", "canary_verification_file_sha256",
})
CHILD_ENTRY = Path(child_entry.__file__).resolve()
SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _durable_ancestor_identity() -> tuple[tuple[int, int, int, int], ...]:
    records = []
    current = Path("/")
    for part in RUNS_ROOT.parts[1:]:
        current = current / part
        item = os.lstat(current)
        if (not stat.S_ISDIR(item.st_mode) or stat.S_ISLNK(item.st_mode)
                or item.st_uid not in {0, os.geteuid()}
                or stat.S_IMODE(item.st_mode) & 0o022):
            raise ValueError("durable output ancestor is not a real directory")
        records.append((item.st_dev, item.st_ino, item.st_mode, item.st_uid))
    return tuple(records)


def _durable_root(path: Path) -> tuple[Path, tuple[tuple[int, int, int, int], ...]]:
    path = Path(path)
    if path != RUN_ROOT or not path.is_absolute() or path.exists() or path.is_symlink():
        raise ValueError("fresh exact durable MarketRSI run root required")
    runs = RUNS_ROOT
    if (runs.is_symlink() or not runs.is_dir()
            or runs.resolve(strict=True) != runs):
        raise ValueError("durable MarketRSI runs parent is unsafe")
    return path, _durable_ancestor_identity()


def _root_identity(root: Path) -> tuple[int, int, int, int]:
    item = os.lstat(root)
    if (not stat.S_ISDIR(item.st_mode) or stat.S_ISLNK(item.st_mode)
            or item.st_uid != os.geteuid()
            or stat.S_IMODE(item.st_mode) != 0o700):
        raise ValueError("durable run root is unsafe")
    return item.st_dev, item.st_ino, item.st_mode, item.st_uid


def _child_environment() -> dict[str, str]:
    """Return a credential/proxy/CA/Python-injection-free child environment."""
    environment = {"PATH": os.defpath, "LANG": "C", "LC_ALL": "C",
                   "PYTHONDONTWRITEBYTECODE": "1"}
    return environment


def _budget_none(budget: PaidBudget, expected_sha256: str) -> dict:
    if type(budget) is not PaidBudget:
        raise ValueError("exact authoritative PaidBudget required")
    expected_sha256 = child_entry._sha(expected_sha256, "budget snapshot")
    snapshot = budget.snapshot()
    if (digest(snapshot) != expected_sha256
            or ATTEMPT_ID in snapshot.get("jobs", {})):
        raise ValueError("authoritative budget is changed or contains this job")
    return snapshot


def _runtime_receipt(value: object) -> dict:
    fields = {
        "schema", "python_executable", "python_version", "source_hashes",
        "source_hashes_sha256", "provider_modules_loaded",
        "public_fetch_modules_loaded", "watched_fetch_modules_loaded",
        "network_modules_loaded_by_canary",
    }
    current = protocol_source_release.source_hashes()
    if (type(value) is not dict or set(value) != fields
            or value["schema"] != canary_receipt.RUNTIME_SCHEMA
            or Path(sys.executable) != PINNED_PYTHON
            or value["python_executable"] != str(PINNED_PYTHON.resolve(strict=True))
            or value["python_version"] != sys.version
            or type(value["source_hashes"]) is not dict
            or set(value["source_hashes"]) != set(
                bridge_canary_runner._SOURCE_FILES)
            or value["source_hashes_sha256"] != digest(value["source_hashes"])
            or any(current.get(name) != sha
                   for name, sha in value["source_hashes"].items())
            or any(value[name] is not False for name in (
                "provider_modules_loaded", "public_fetch_modules_loaded",
                "watched_fetch_modules_loaded",
                "network_modules_loaded_by_canary"))):
        raise ValueError("runtime receipt is not the exact current pinned runtime")
    return value


def _write_failure(root: Path, *, stage: str, error: BaseException,
                   state_status: str, watchdog_status: str,
                   budget_snapshot_sha256: str) -> Path:
    path = root / "failure.json"
    if not path.exists():
        fresh_json(path, {
            "schema": FAILURE_SCHEMA, "attempt_id": ATTEMPT_ID,
            "stage": stage, "error_type": type(error).__name__,
            "error_sha256": hashlib.sha256(str(error).encode()).hexdigest(),
            "global_state_status": state_status,
            "watchdog_status": watchdog_status,
            "budget_snapshot_sha256": budget_snapshot_sha256,
            "automatic_retry": False, "same_id_retry_allowed": False,
        })
    return path


def _terminal_cleanup(process, command_sha256: str) -> dict:
    errors = []
    process_absent = process is None
    if process is not None:
        try:
            if not command_sha256:
                present = process.poll() is None
                observed = None
            else:
                observed, present = process_command_sha256(process.pid)
            if present and command_sha256 and observed != command_sha256:
                errors.append("process_identity_mismatch")
            elif present:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            process_absent = process.poll() is not None
        except Exception as exc:
            errors.append(type(exc).__name__)
    container_absent = False
    try:
        label, present = container_identity(CONTAINER_NAME)
        if present and label == CONTAINER_LABEL:
            stopped = subprocess.run(
                ["docker", "stop", "--time", "2", CONTAINER_NAME],
                capture_output=True, text=True, timeout=8, check=False)
            if stopped.returncode != 0:
                errors.append("container_stop_failed")
            label, present = container_identity(CONTAINER_NAME)
        elif present:
            errors.append("container_identity_mismatch")
        container_absent = not present and label is None
    except Exception as exc:
        errors.append(type(exc).__name__)
    return {
        "schema": "market_p0_gate1_source_scope_terminal_cleanup_v1",
        "attempt_id": ATTEMPT_ID, "process_absent": process_absent,
        "container_absent": container_absent, "errors": errors,
        "cleanup_verified": process_absent and container_absent and not errors,
    }


def _canonical_json(path: Path, *, limit: int = 8 * 1024 * 1024) -> dict:
    raw = child_entry._read_regular(
        Path(path), "parent canonical JSON", limit=limit)
    value = json.loads(raw)
    expected = (json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True,
        separators=(",", ":")) + "\n").encode("ascii")
    if type(value) is not dict or raw != expected:
        raise ValueError("canonical JSON object required")
    return value


def _child_command(*, binding_path: Path, binding_sha256: str,
                   output: Path, watchdog_root: Path, claim_path: Path,
                   budget_snapshot_sha256: str) -> list[str]:
    return [
        sys.executable, "-I", "-B", str(CHILD_ENTRY),
        "--binding", str(binding_path),
        "--expected-binding-sha256", binding_sha256,
        "--output", str(output), "--watchdog-root", str(watchdog_root),
        "--supervisor-claim", str(claim_path),
        "--budget-snapshot-sha256", budget_snapshot_sha256,
    ]


def _claim(*, watchdog: SupervisorWatchdog, binding: dict, pid: int,
           command_sha256: str, budget_snapshot_sha256: str,
           claim_path: Path, parent_pid: int, parent_command_sha256: str,
           global_state_head_sha256: str, decision_doc_sha256: str,
           global_state_root: Path, decision_doc: Path, budget_root: Path,
           clock=None) -> dict:
    child_entry._sha(command_sha256, "process command")
    child_entry._sha(budget_snapshot_sha256, "budget snapshot")
    child_entry._sha(parent_command_sha256, "parent process command")
    child_entry._sha(global_state_head_sha256, "global state head")
    child_entry._sha(decision_doc_sha256, "decision document")
    if type(pid) is not int or pid <= 1:
        raise ValueError("real child PID required")
    input_sha256 = digest({"task": binding["task"],
                           "admission": binding["admission"]})
    watchdog.claim_task(
        task_id=child_entry.TASK_ID, task_kind="research",
        stage="gate1_source_scope_fetch", owner="trusted_broker",
        heartbeat_timeout_seconds=20, progress_timeout_seconds=30,
        input_sha256=input_sha256,
        process_identity={"pid": pid, "command_sha256": command_sha256},
        container_identity=None, now=None if clock is None else clock())
    claim = {
        "schema": PARENT_CLAIM_SCHEMA, "task_id": child_entry.TASK_ID,
        "binding_canonical_sha256": digest(binding), "pid": pid,
        "process_command_sha256": command_sha256,
        "budget_snapshot_sha256": budget_snapshot_sha256,
        "watchdog_head_sha256": watchdog.snapshot()["head_sha256"],
        "binding_path": str(Path(binding["output_root"]) / "binding.json"),
        "output_path": str(Path(binding["output_root"]) / "snapshot"),
        "watchdog_root": str(watchdog.root), "claim_path": str(claim_path),
        "parent_pid": parent_pid,
        "parent_command_sha256": parent_command_sha256,
        "global_state_root": str(global_state_root),
        "global_state_head_sha256": global_state_head_sha256,
        "decision_doc_path": str(decision_doc),
        "decision_doc_sha256": decision_doc_sha256,
        "budget_root": str(budget_root),
        "automatic_retry": False,
    }
    fresh_json(claim_path, claim)
    return claim


def _failure_evidence(*, pid: int, command_sha256: str,
                      budget_snapshot_sha256: str, error: BaseException,
                      process_present: bool) -> dict:
    return {
        "process": {"checked": True, "pid": pid,
                    "command_sha256": command_sha256,
                    "present": process_present},
        "container": {"checked": True, "name": None, "label": None,
                      "present": False},
        "data": {"gate_status": "not_applicable", "evidence_sha256": None},
        "budget": {"checked": True, "task_id": child_entry.TASK_ID,
                   "state": "none",
                   "snapshot_sha256": budget_snapshot_sha256},
        "log_tail_sha256": hashlib.sha256(
            (type(error).__name__ + ":" + str(error)).encode()).hexdigest(),
    }


def _report_once(*, watchdog: SupervisorWatchdog, pid: int,
                 command_sha256: str, budget_snapshot_sha256: str,
                 error: BaseException, process_present: bool, clock=None) -> None:
    active = watchdog.snapshot()["active_task"]
    if type(active) is dict and active.get("status") == "active":
        watchdog.report_failure(
            child_entry.TASK_ID,
            classification=("malformed_data" if isinstance(
                error, (ValueError, UnicodeError)) else "worker_error"),
            evidence=_failure_evidence(
                pid=pid, command_sha256=command_sha256,
                budget_snapshot_sha256=budget_snapshot_sha256, error=error,
                process_present=process_present),
            now=None if clock is None else clock())


def _validate_child_result(value: object, binding: dict) -> dict:
    if type(value) is not dict or set(value) != child_entry.RESULT_FIELDS:
        raise ValueError("child result fields differ")
    expected = {
        "schema": child_entry.RESULT_SCHEMA, "attempt_id": ATTEMPT_ID,
        "passed": True, "task_id": child_entry.TASK_ID,
        "input_sha256": digest({"task": binding["task"],
                                "admission": binding["admission"]}),
        "task_canonical_sha256": digest(binding["task"]),
        "admission_canonical_sha256": digest(binding["admission"]),
        "requests_made": 1, "redirects_followed": 0,
        "automatic_retries": 0, "provider_calls": 0,
        "actual_provider_cost_usd": "0", "rights_proven": False,
        "final_url": binding["task"]["source"]["url"],
        "content_encoding": None,
        "formal_data_admitted": False, "train_dev_final_read": False,
        "training_or_evaluation_performed": False,
        "snapshot_redistributed": False,
        "prediction_improvement_proven": False,
    }
    if any(value[name] != item for name, item in expected.items()):
        raise ValueError("child result changed")
    if any(type(value[name]) is not int for name in (
            "snapshot_bytes", "requests_made", "redirects_followed",
            "automatic_retries", "provider_calls")):
        raise ValueError("child result counters must be exact integers")
    if (type(value["receipt_file_sha256"]) is not str
            or type(value["snapshot_sha256"]) is not str):
        raise ValueError("child result hashes or size changed")
    return value


def _finish_success(*, binding: dict, watchdog: SupervisorWatchdog,
                    pid: int, command_sha256: str, child_exit_code: int,
                    terminal_process_absent: bool,
                    terminal_container_absent: bool,
                    global_state_head_sha256: str = "0" * 64,
                    global_state_status: str = "test_only_not_applicable",
                    budget_snapshot_sha256: str = "0" * 64,
                    global_state: SupervisorGlobalState | None = None,
                    budget_root: Path | None = None,
                    durable_ancestor_identity: tuple | None = None,
                    durable_root_identity: tuple | None = None,
                    clock=None) -> dict:
    binding = validate_execution_binding(binding)
    if (child_exit_code != 0 or terminal_process_absent is not True
            or terminal_container_absent is not True):
        raise ValueError("child did not exit cleanly and become absent")
    root = Path(binding["output_root"])
    if ((durable_root_identity is not None
            and _root_identity(root) != durable_root_identity)
            or (durable_ancestor_identity is not None
                and _durable_ancestor_identity()
                != durable_ancestor_identity)):
        raise ValueError("durable run root or ancestor identity changed")
    child_path = root / "child-result.json"
    child_result = _validate_child_result(_canonical_json(child_path), binding)
    receipt_path = root / "snapshot" / "receipt.json"
    snapshot_path = root / "snapshot" / "public-source.snapshot"
    receipt = _canonical_json(receipt_path)
    child_entry._validate_receipt(receipt, binding, snapshot_path)
    if (file_hash(receipt_path) != child_result["receipt_file_sha256"]
            or file_hash(snapshot_path) != child_result["snapshot_sha256"]
            or snapshot_path.stat().st_size != child_result["snapshot_bytes"]):
        raise ValueError("child output differs from verified receipt")
    active = watchdog.snapshot()["active_task"]
    if (type(active) is not dict or active.get("status") != "active"
            or active.get("task_id") != child_entry.TASK_ID
            or active.get("process_identity") != {
                "pid": pid, "command_sha256": command_sha256}
            or active.get("progress_seq") != 2
            or active.get("last_progress_sha256")
            != child_result["receipt_file_sha256"]
            or watchdog.snapshot().get("incidents") != []):
        raise ValueError("watchdog does not retain exact active child")
    if global_state is None:
        global_journal_path = root / "test-global-state-journal.jsonl"
        decision_doc_path = root / "test-decision.md"
        global_journal_sha256 = "0" * 64
        decision_doc_sha256 = "0" * 64
        budget_root_text = str(root / "test-budget")
    else:
        state_snapshot = global_state.snapshot()
        if (state_snapshot["active_cycle"] != ATTEMPT_ID
                or state_snapshot["head_sha256"] != global_state_head_sha256):
            raise ValueError("global state is not active pending independent review")
        global_journal_path = global_state.journal.path.resolve()
        decision_doc_path = global_state.decision_doc
        global_journal_sha256 = file_hash(global_journal_path)
        decision_doc_sha256 = file_hash(decision_doc_path)
        budget_root_text = str(Path(budget_root).resolve())
    preterminal = {
        "schema": "market_p0_gate1_source_scope_fetch_preterminal_v1",
        "attempt_id": ATTEMPT_ID,
        "binding_canonical_sha256": digest(binding),
        "receipt_file_sha256": child_result["receipt_file_sha256"],
        "snapshot_sha256": child_result["snapshot_sha256"],
        "global_state_head_sha256": global_state_head_sha256,
        "budget_snapshot_sha256": budget_snapshot_sha256,
        "process_absent": True, "container_absent": True,
        "ready_for_watchdog_close": True, "automatic_retry": False,
    }
    fresh_json(root / "preterminal.json", preterminal)
    watchdog.close_success(
        child_entry.TASK_ID,
        result_sha256=child_result["receipt_file_sha256"],
        now=None if clock is None else clock())
    terminal = watchdog.snapshot()
    result = {
        "schema": RESULT_SCHEMA, "attempt_id": ATTEMPT_ID, "passed": True,
        "task_id": child_entry.TASK_ID, "child_pid": pid,
        "process_command_sha256": command_sha256,
        "binding_canonical_sha256": digest(binding),
        "binding_path": str(root / "binding.json"),
        "binding_file_sha256": file_hash(root / "binding.json"),
        "parent_claim_path": str(root / "supervisor-claim.json"),
        "parent_claim_file_sha256": file_hash(
            root / "supervisor-claim.json"),
        "child_result_path": str(child_path),
        "child_result_file_sha256": file_hash(child_path),
        "task_canonical_sha256": digest(binding["task"]),
        "admission_canonical_sha256": digest(binding["admission"]),
        "authorization_file_sha256": binding["authorization_file_sha256"],
        "prior_canary_receipt_sha256":
            binding["task"]["prior_canary_receipt_sha256"],
        "prior_canary_verification_sha256":
            binding["task"]["prior_canary_verification_sha256"],
        "receipt_path": str(receipt_path),
        "receipt_file_sha256": child_result["receipt_file_sha256"],
        "snapshot_path": str(snapshot_path),
        "snapshot_sha256": child_result["snapshot_sha256"],
        "snapshot_bytes": child_result["snapshot_bytes"],
        "final_url": child_result["final_url"],
        "content_encoding": child_result["content_encoding"],
        "requests_made": 1, "redirects_followed": 0,
        "automatic_retries": 0, "provider_calls": 0,
        "actual_provider_cost_usd": "0", "rights_proven": False,
        "formal_data_admitted": False, "train_dev_final_read": False,
        "training_or_evaluation_performed": False,
        "snapshot_redistributed": False,
        "prediction_improvement_proven": False,
        "child_exit_code": 0, "terminal_process_absent": True,
        "terminal_container_absent": terminal_container_absent,
        "watchdog_head_sha256": terminal["head_sha256"],
        "watchdog_seq": terminal["seq"],
        "watchdog_journal_path": str(watchdog.journal),
        "watchdog_journal_file_sha256": file_hash(watchdog.journal),
        "watchdog_snapshot_path": str(watchdog.snapshot_path),
        "watchdog_snapshot_file_sha256": file_hash(watchdog.snapshot_path),
        "global_state_head_sha256": global_state_head_sha256,
        "global_state_status": global_state_status,
        "budget_snapshot_sha256": budget_snapshot_sha256,
        "budget_state": "none",
        "global_state_journal_path": str(global_journal_path),
        "global_state_journal_file_sha256": global_journal_sha256,
        "decision_doc_path": str(decision_doc_path),
        "decision_doc_sha256": decision_doc_sha256,
        "budget_root": budget_root_text,
        "authorization_copy_path": str(root / "authorization.json"),
        "authorization_copy_file_sha256": file_hash(
            root / "authorization.json"),
        "request_bundle_path": str(root / "request-plan-bundle.json"),
        "request_bundle_file_sha256": file_hash(
            root / "request-plan-bundle.json"),
        "runtime_receipt_path": str(root / "runtime.json"),
        "runtime_receipt_file_sha256": file_hash(root / "runtime.json"),
        "canary_verification_path": str(root / "canary-verification.json"),
        "canary_verification_file_sha256": file_hash(
            root / "canary-verification.json"),
    }
    try:
        fresh_json(root / "result.json", result)
    except Exception as exc:
        try:
            fresh_json(root / "post-close-failure.json", {
                "schema": "market_p0_gate1_source_scope_post_close_failure_v1",
                "attempt_id": ATTEMPT_ID,
                "error_type": type(exc).__name__,
                "error_sha256": hashlib.sha256(str(exc).encode()).hexdigest(),
                "watchdog_passed": True, "automatic_retry": False,
                "same_id_retry_allowed": False,
            })
        finally:
            raise
    return result


def run(args) -> dict:
    root, ancestor_identity = _durable_root(Path(args.output_root))
    if (Path(args.global_state_root) != GLOBAL_STATE_ROOT
            or Path(args.decision_doc) != DECISION_DOC
            or Path(args.budget_root) != BUDGET_ROOT):
        raise ValueError("exact authoritative state, decision and budget paths required")
    bundle = _canonical_json(Path(args.bundle))
    runtime = _runtime_receipt(_canonical_json(Path(args.runtime_receipt)))
    d0_decision = _canonical_json(D0_DECISION)
    d0_provenance = _canonical_json(D0_PROVENANCE)
    d0_packet = _canonical_json(D0_PACKET)
    binding = prepare_execution_binding(
        bundle, d0_decision=d0_decision,
        d0_decision_provenance=d0_provenance, d0_packet=d0_packet,
        authorization_path=Path(args.authorization),
        expected_authorization_sha256=args.expected_authorization_sha256,
        canary_receipt_path=Path(args.canary_receipt),
        expected_canary_receipt_sha256=args.expected_canary_receipt_sha256,
        runtime_receipt=runtime, output_root=root)
    state = SupervisorGlobalState(args.global_state_root, args.decision_doc)
    state_before = state.snapshot()
    if (state_before["head_sha256"]
            != child_entry._sha(args.expected_state_head_sha256, "state head")
            or state_before["decision_doc_sha256"]
            != child_entry._sha(args.expected_decision_sha256, "decision")
            or state_before["active_cycle"] is not None
            or ATTEMPT_ID in state_before["claimed_cycles"]):
        raise ValueError("global state is stale, active, or reuses this attempt")
    budget = PaidBudget(args.budget_root)
    budget_snapshot = _budget_none(
        budget, args.expected_budget_snapshot_sha256)
    budget_snapshot_sha256 = digest(budget_snapshot)
    root.mkdir(parents=True, mode=0o700)
    root_identity = _root_identity(root)
    if _durable_ancestor_identity() != ancestor_identity:
        raise ValueError("durable output ancestors changed")
    binding_path = root / "binding.json"
    authorization_copy, observed_authorization = load_authorization(
        Path(args.authorization),
        expected_sha256=args.expected_authorization_sha256)
    fresh_json(root / "authorization.json", authorization_copy)
    fresh_json(root / "request-plan-bundle.json", bundle)
    fresh_json(root / "runtime.json", runtime)
    fresh_json(root / "canary-verification.json",
               binding["canary_verification"])
    for copied in ("authorization.json", "request-plan-bundle.json",
                   "runtime.json", "canary-verification.json"):
        os.chmod(root / copied, 0o600)
    if file_hash(root / "authorization.json") != observed_authorization:
        raise ValueError("authorization copy differs from exact input bytes")
    fresh_json(binding_path, binding)
    watchdog = SupervisorWatchdog(root / "watchdog")
    watchdog.initialize()
    claim_path = root / "supervisor-claim.json"
    command = _child_command(
        binding_path=binding_path, binding_sha256=digest(binding),
        output=root / "snapshot", watchdog_root=watchdog.root,
        claim_path=claim_path,
        budget_snapshot_sha256=budget_snapshot_sha256)
    process = None
    log = None
    command_sha256 = ""
    parent_command_sha256, parent_present = process_command_sha256(os.getpid())
    if not parent_present or parent_command_sha256 is None:
        raise RuntimeError("cannot bind exact outer parent process")
    claimed = False
    stage = "global_state_claim"
    try:
        state_after_claim = state.claim(
            ATTEMPT_ID,
            expected_head_sha256=args.expected_state_head_sha256,
            source_sha256=binding["current_source_sha256"],
            prior_canary_sha256=args.expected_canary_receipt_sha256)
        claimed = True
        stage = "child_launch"
        log = (root / "child.log").open("xb")
        process = subprocess.Popen(
            command, stdout=log, stderr=subprocess.STDOUT,
            env=_child_environment(), cwd=SOURCE_ROOT)
        command_sha256 = stable_process_command_sha256(process.pid)
        stage = "watchdog_claim"
        _claim(
            watchdog=watchdog, binding=binding, pid=process.pid,
            command_sha256=command_sha256,
            budget_snapshot_sha256=budget_snapshot_sha256,
            claim_path=claim_path, parent_pid=os.getpid(),
            parent_command_sha256=parent_command_sha256,
            global_state_head_sha256=state_after_claim["head_sha256"],
            decision_doc_sha256=state_after_claim["decision_doc_sha256"],
            global_state_root=args.global_state_root,
            decision_doc=args.decision_doc, budget_root=args.budget_root)
        control = LocalProcessDockerControl(
            budget_evidence=lambda task_id: {
                "checked": True, "task_id": task_id, "state": "none",
                "snapshot_sha256": digest(_budget_none(
                    budget, args.expected_budget_snapshot_sha256)),
            },
            data_evidence=lambda _task_id: {
                "gate_status": "not_applicable", "evidence_sha256": None})
        deadline = time.monotonic() + MAX_ELAPSED_SECONDS
        stage = "supervise_child"
        while process.poll() is None:
            active = watchdog.snapshot()["active_task"]
            if type(active) is not dict or active.get("status") != "active":
                raise RuntimeError("child watchdog became terminal before success")
            observed, present = process_command_sha256(process.pid)
            if not present or observed != command_sha256:
                raise RuntimeError("child process identity changed while active")
            label, container_present = container_identity(CONTAINER_NAME)
            if container_present or label is not None:
                raise RuntimeError("source-scope fetch created a forbidden container")
            log.flush()
            os.fsync(log.fileno())
            incident = watchdog.tick(
                evidence=control.evidence(active, file_hash(root / "child.log")))
            if incident is not None:
                raise RuntimeError("outer watchdog created a terminal incident")
            if time.monotonic() >= deadline:
                raise TimeoutError("one-shot child exceeded elapsed bound")
            time.sleep(0.05)
        exit_code = process.wait(timeout=5)
        if exit_code != 0:
            raise RuntimeError(f"child exited {exit_code}")
        stage = "terminal_verification"
        terminal_active = watchdog.snapshot()["active_task"]
        if (type(terminal_active) is not dict
                or terminal_active.get("status") != "active"):
            raise RuntimeError("child watchdog is not active for terminal review")
        terminal_evidence = control.evidence(
            terminal_active, file_hash(root / "child.log"))
        label, container_present = container_identity(CONTAINER_NAME)
        terminal_process_absent = (
            terminal_evidence["process"]["present"] is False)
        terminal_container_absent = (
            not container_present and label is None)
        if (not terminal_process_absent or not terminal_container_absent
                or terminal_evidence["budget"]["state"] != "none"
                or terminal_evidence["data"]["gate_status"]
                != "not_applicable"):
            raise RuntimeError("independent terminal cleanup is incomplete")
        stage = "write_success_receipt"
        return _finish_success(
            binding=binding, watchdog=watchdog, pid=process.pid,
            command_sha256=command_sha256, child_exit_code=exit_code,
            terminal_process_absent=terminal_process_absent,
            terminal_container_absent=terminal_container_absent,
            global_state_head_sha256=state_after_claim["head_sha256"],
            global_state_status="active_pending_independent_review",
            budget_snapshot_sha256=budget_snapshot_sha256,
            global_state=state, budget_root=args.budget_root,
            durable_ancestor_identity=ancestor_identity,
            durable_root_identity=root_identity)
    except Exception as exc:
        cleanup = _terminal_cleanup(process, command_sha256)
        if (process is not None and command_sha256
                and cleanup["cleanup_verified"] is True):
            _report_once(
                watchdog=watchdog, pid=process.pid,
                command_sha256=command_sha256,
                budget_snapshot_sha256=budget_snapshot_sha256,
                error=exc, process_present=False)
        state_status = "not_claimed"
        if claimed:
            try:
                current = state.snapshot()
                if current["active_cycle"] == ATTEMPT_ID:
                    state.close(ATTEMPT_ID, outcome="failed")
                state_status = "closed_failed"
            except Exception:
                state_status = "close_failed"
        active = watchdog.snapshot()["active_task"]
        watchdog_status = (
            "idle" if active is None else str(active.get("status")))
        if _root_identity(root) == root_identity:
            fresh_json(root / "terminal-cleanup.json", cleanup)
            _write_failure(
                root, stage=stage, error=exc, state_status=state_status,
                watchdog_status=watchdog_status,
                budget_snapshot_sha256=budget_snapshot_sha256)
        raise
    finally:
        if log is not None:
            log.close()


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Run one exact official documentation fetch")
    value.add_argument("--bundle", required=True, type=Path)
    value.add_argument("--authorization", required=True, type=Path)
    value.add_argument("--expected-authorization-sha256", required=True)
    value.add_argument("--canary-receipt", required=True, type=Path)
    value.add_argument("--expected-canary-receipt-sha256", required=True)
    value.add_argument("--runtime-receipt", required=True, type=Path)
    value.add_argument("--output-root", required=True, type=Path)
    value.add_argument("--global-state-root", required=True, type=Path)
    value.add_argument("--decision-doc", required=True, type=Path)
    value.add_argument("--expected-state-head-sha256", required=True)
    value.add_argument("--expected-decision-sha256", required=True)
    value.add_argument("--budget-root", required=True, type=Path)
    value.add_argument("--expected-budget-snapshot-sha256", required=True)
    return value


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), sort_keys=True))
