"""Host-side one-B transport adapter; no model, budget, or admission authority.

The caller must first admit the exact cycle, source release, budget hold, E2B
policy and isolation canary. An injected factory creates exactly one sandbox.
Guest stdout is only a readiness hint: every ACK/event is independently read
and hash-bound by DirectionalHandoff before it can be exposed to A.

Fake-SDK tests of this module are not live E2B, GLM, isolation, or cost proof.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import queue
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from market_rsi import digest, file_hash, fresh_json, identifier
from supervisor_harness.directional_handoff import (
    B_ORDER_DIR, DirectionalHandoff, EXPECTED_HANDOFFS, MAX_MESSAGE_BYTES,
    P95_LIMIT_NS, SINGLE_LEG_LIMIT_NS,
)


GUEST_SCRIPT = "/tmp/market_directional_guest.py"
GUEST_ROOT = "/tmp/market-researcher/directional"
STAGING_DIR = f"{GUEST_ROOT}/staging"
GUEST_TOTAL_TIMEOUT_SECONDS = 120
GUEST_COMMAND = (f"python3 -I {GUEST_SCRIPT} --root {GUEST_ROOT} "
                 "--poll-interval 0.02 --per-order-timeout 5 "
                 f"--total-timeout {GUEST_TOTAL_TIMEOUT_SECONDS}")
MILESTONE_SCHEMA = "market_directional_guest_milestone_v1"
MAX_GUEST_SOURCE_BYTES = 128 * 1024
MAX_STDIO_BYTES = 16 * 1024
FILE_REQUEST_TIMEOUT_SECONDS = 5
MILESTONE_TIMEOUT_SECONDS = 8
PROCESS_WAIT_SECONDS = 10
PROCESS_STREAM_TIMEOUT_SECONDS = 145
MIN_SANDBOX_REMAINING_SECONDS = 160
SANDBOX_TIMEOUT_SECONDS = 180
E2B_SDK_VERSION = "2.38.0"
NETWORK = {"allow_out": [], "deny_out": ["0.0.0.0/0"],
           "allow_public_traffic": False}
LIFECYCLE = {"on_timeout": "kill", "auto_resume": False}


def _sha(value: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise ValueError("lowercase SHA256 required")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate guest milestone member")
        value[key] = item
    return value


class _BoundedFiles:
    def __init__(self, sandbox, sandbox_id: str):
        self._sandbox = sandbox
        self._sandbox_id = sandbox_id

    def _guard(self):
        if self._sandbox.sandbox_id != self._sandbox_id:
            raise ValueError("B sandbox identity changed")

    def write(self, path: str, value: str):
        self._guard()
        if path.startswith(B_ORDER_DIR + "/") and path.endswith(".json"):
            # SDK upload completion does not establish whether the watched
            # path was visible midway through the upload. Stage outside the
            # guest's watched orders directory, then publish by rename.
            staged = f"{STAGING_DIR}/{Path(path).name}"
            self._sandbox.files.write(
                staged, value, request_timeout=FILE_REQUEST_TIMEOUT_SECONDS)
            return self._sandbox.files.rename(
                staged, path, request_timeout=FILE_REQUEST_TIMEOUT_SECONDS)
        return self._sandbox.files.write(
            path, value, request_timeout=FILE_REQUEST_TIMEOUT_SECONDS)

    def read(self, path: str) -> str:
        self._guard()
        return self._sandbox.files.read(
            path, request_timeout=FILE_REQUEST_TIMEOUT_SECONDS)

    def make_dir(self, path: str) -> bool:
        self._guard()
        return self._sandbox.files.make_dir(
            path, request_timeout=FILE_REQUEST_TIMEOUT_SECONDS)


class _ObservedB:
    """Expose only one fixed sandbox identity and bounded file operations."""

    def __init__(self, sandbox, sandbox_id: str):
        self._sandbox = sandbox
        self._sandbox_id = sandbox_id
        self.files = _BoundedFiles(sandbox, sandbox_id)

    @property
    def sandbox_id(self) -> str:
        if self._sandbox.sandbox_id != self._sandbox_id:
            raise ValueError("B sandbox identity changed")
        return self._sandbox_id


class E2BGuestSession:
    """One foreground SDK command in a host thread, with bounded JSONL hints.

    E2B 2.38.0 delivers stdout in arbitrary chunks. `commands.run`'s timeout
    bounds the entire command stream, not an individual guest operation.
    """

    def __init__(self, sandbox, command: str = GUEST_COMMAND):
        self._sandbox = sandbox
        self._command = command
        self._messages: queue.Queue[dict] = queue.Queue(maxsize=EXPECTED_HANDOFFS * 2 + 1)
        self._done = threading.Event()
        self._lock = threading.Lock()
        self._buffer = ""
        self._stdout_bytes = 0
        self._stderr_bytes = 0
        self._stdout_hash = hashlib.sha256()
        self._stderr_hash = hashlib.sha256()
        self._result = None
        self._error: Exception | None = None
        self._thread = threading.Thread(target=self._run, name="market-one-b-guest", daemon=True)
        self._thread.start()

    def _on_stdout(self, chunk: str) -> None:
        if not isinstance(chunk, str):
            raise ValueError("guest stdout must be text")
        encoded = chunk.encode("utf-8")
        with self._lock:
            self._stdout_bytes += len(encoded)
            if self._stdout_bytes > MAX_STDIO_BYTES:
                raise ValueError("oversized guest stdout")
            self._stdout_hash.update(encoded)
            self._buffer += chunk
            if len(self._buffer.encode("utf-8")) > MAX_MESSAGE_BYTES:
                raise ValueError("oversized guest stdout line")
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                if not line or len(line.encode("utf-8")) > 512:
                    raise ValueError("invalid guest milestone line")
                value = json.loads(line, object_pairs_hook=_unique_object)
                if (not isinstance(value, dict)
                        or set(value) != {"schema", "sequence", "kind"}):
                    raise ValueError("guest milestone schema invalid")
                value["_host_callback_ns"] = time.monotonic_ns()
                self._messages.put_nowait(value)

    def _on_stderr(self, chunk: str) -> None:
        if not isinstance(chunk, str):
            raise ValueError("guest stderr must be text")
        encoded = chunk.encode("utf-8")
        with self._lock:
            self._stderr_bytes += len(encoded)
            if self._stderr_bytes > MAX_STDIO_BYTES:
                raise ValueError("oversized guest stderr")
            self._stderr_hash.update(encoded)

    def _run(self) -> None:
        try:
            result = self._sandbox.commands.run(
                self._command, on_stdout=self._on_stdout,
                on_stderr=self._on_stderr, timeout=PROCESS_STREAM_TIMEOUT_SECONDS)
            if type(result.exit_code) is not int or result.exit_code != 0:
                raise RuntimeError("guest process exited unsuccessfully")
            with self._lock:
                if self._buffer:
                    raise ValueError("unterminated guest milestone line")
            self._result = result
        except Exception as exc:
            self._error = exc
        finally:
            self._done.set()

    def next_message(self, timeout_seconds: float) -> dict | None:
        if timeout_seconds < 0:
            raise ValueError("negative guest wait")
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                return self._messages.get_nowait()
            except queue.Empty:
                if self._done.is_set():
                    if self._error is not None:
                        raise self._error
                    return None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._done.wait(min(remaining, .01))

    def wait(self, timeout_seconds: float) -> dict:
        if not self._done.wait(timeout_seconds):
            raise TimeoutError("guest process did not finish")
        if self._error is not None:
            raise self._error
        if self._result is None:
            raise RuntimeError("guest process has no result")
        return {"exit_code": self._result.exit_code,
                "stdout_bytes": self._stdout_bytes,
                "stderr_bytes": self._stderr_bytes,
                "stdout_sha256": self._stdout_hash.hexdigest(),
                "stderr_sha256": self._stderr_hash.hexdigest()}


def launch_e2b_guest(sandbox, command: str = GUEST_COMMAND) -> E2BGuestSession:
    """SDK-backed launcher, called only by an explicitly admitted caller."""
    return E2BGuestSession(sandbox, command)


def _require_local_sdk_runtime() -> None:
    local_market_root = Path(__file__).resolve().parents[4]
    if (importlib.metadata.version("e2b") != E2B_SDK_VERSION
            or sys.prefix == sys.base_prefix
            or not Path(sys.prefix).resolve().is_relative_to(local_market_root)
            or not Path(sys.executable).absolute().is_relative_to(local_market_root)):
        raise ValueError("one-B creation requires pinned local E2B runtime")


def create_one_b_sandbox(sandbox_class, *, key: str, cycle_id: str):
    """Explicit paid boundary; caller must pass prior release/budget gates.

    No paid key is passed as a guest environment variable. Network echo and
    isolation must still be independently checked; request flags alone prove
    neither. Never call this from an offline fixture.
    """
    identifier(cycle_id)
    if not isinstance(key, str) or not key:
        raise ValueError("host E2B credential required")
    _require_local_sdk_runtime()
    return sandbox_class.create(
        template="base", timeout=SANDBOX_TIMEOUT_SECONDS, secure=True,
        api_key=key, request_timeout=15, envs={}, volume_mounts={},
        allow_internet_access=False, network=NETWORK, lifecycle=LIFECYCLE,
        metadata={"experiment_id": "market-rsi-directional-one-b",
                  "job_id": cycle_id, "role": "researcher"})


def _account_receipt(check_account_clear, expected_id: str | None) -> dict:
    result = check_account_clear(expected_id)
    if (not isinstance(result, dict)
            or set(result) != {"clear", "checked_sandbox_id", "active_market_rsi_ids"}
            or result["clear"] is not True
            or result["checked_sandbox_id"] != expected_id
            or result["active_market_rsi_ids"] != []):
        raise RuntimeError("E2B account-clear check is missing or negative")
    return result


def _require_guest_ttl(sandbox, sandbox_id: str, cycle_id: str) -> dict:
    """Require a host-observed expiry beyond guest and stream deadlines."""
    info = sandbox.get_info(request_timeout=FILE_REQUEST_TIMEOUT_SECONDS)
    end_at = getattr(info, "end_at", None)
    lifecycle = getattr(info, "lifecycle", None)
    network = getattr(info, "network", None)
    metadata = getattr(info, "metadata", None)
    now = datetime.now(timezone.utc)
    missing_allow_out = isinstance(network, dict) and "allow_out" not in network
    if (getattr(info, "sandbox_id", None) != sandbox_id
            or not isinstance(end_at, datetime) or end_at.tzinfo is None
            or lifecycle != LIFECYCLE
            or getattr(info, "allow_internet_access", None) is not False
            or not isinstance(network, dict)
            or network.get("deny_out") != NETWORK["deny_out"]
            or network.get("allow_public_traffic") is not False
            or (not missing_allow_out and network.get("allow_out") != [])
            or not isinstance(metadata, dict)
            or metadata.get("experiment_id") != "market-rsi-directional-one-b"
            or metadata.get("job_id") != cycle_id
            or metadata.get("role") != "researcher"
            or getattr(info, "volume_mounts", None) != []
            or type(getattr(info, "cpu_count", None)) is not int
            or not 0 < info.cpu_count <= 8
            or type(getattr(info, "memory_mb", None)) is not int
            or not 0 < info.memory_mb <= 8192):
        raise ValueError("B expiry or mandatory safety policy echo is unconfirmed")
    remaining = (end_at - now).total_seconds()
    if remaining < MIN_SANDBOX_REMAINING_SECONDS:
        raise ValueError("B TTL has insufficient guest/cleanup headroom")
    return {"sandbox_id": sandbox_id, "end_at_utc": end_at.isoformat(),
            "host_checked_at_utc": now.isoformat(),
            "remaining_seconds": remaining,
            "guest_total_timeout_seconds": GUEST_TOTAL_TIMEOUT_SECONDS,
            "sdk_stream_timeout_seconds": PROCESS_STREAM_TIMEOUT_SECONDS,
            "minimum_remaining_seconds": MIN_SANDBOX_REMAINING_SECONDS,
            "lifecycle": LIFECYCLE,
            "network_observed": {
                "allow_out": None if missing_allow_out else network["allow_out"],
                "deny_out": network["deny_out"],
                "allow_public_traffic": network["allow_public_traffic"]},
            "policy_echo_accepted": not missing_allow_out,
            "missing_policy_fields": ["allow_out"] if missing_allow_out else [],
            "synthetic_transport_diagnostic_only": missing_allow_out,
            "allow_internet_access": False,
            "cpu_count": info.cpu_count, "memory_mb": info.memory_mb,
            "volume_mounts": []}


def _milestone(session, sequence: int, kind: str, clock_ns) -> dict:
    value = session.next_message(MILESTONE_TIMEOUT_SECONDS)
    observed_ns = clock_ns()
    if value is None:
        raise TimeoutError("guest milestone missing")
    if isinstance(session, E2BGuestSession):
        if not isinstance(value, dict) or type(value.get("_host_callback_ns")) is not int:
            raise ValueError("missing host callback timestamp")
        callback_ns = value.pop("_host_callback_ns")
    else:
        # Injected offline sessions do not prove callback arrival timing.
        callback_ns = observed_ns
    if (not isinstance(value, dict)
            or set(value) != {"schema", "sequence", "kind"}
            or value.get("schema") != MILESTONE_SCHEMA
            or type(value.get("sequence")) is not int
            or value["sequence"] != sequence
            or value.get("kind") != kind
            or type(observed_ns) is not int or callback_ns > observed_ns):
        raise ValueError("guest milestone duplicate, out of order or malformed")
    return {"schema": MILESTONE_SCHEMA, "sequence": sequence, "kind": kind,
            "host_callback_ns": callback_ns,
            "host_monotonic_observed_ns": observed_ns}


def run_one_b_transport(*, state, cycle_id: str, input_sha256: str,
                        public_source: str, guest_source_path: Path,
                        receipt_root: Path, create_sandbox: Callable[[], object],
                        check_account_clear: Callable[[str | None], dict],
                        launch_guest: Callable[[object, str], object] = launch_e2b_guest,
                        clock_ns: Callable[[], int] = time.monotonic_ns) -> dict:
    """Exercise 20 distinct synthetic tasks in one B and kill its exact ID.

    No E2B call occurs until the caller supplies a factory and this function's
    fresh-root/state/source/account checks pass. It does not reserve money,
    create a global cycle, invoke GLM or certify isolation. Never treat a fake
    factory's passing summary as a live provider latency measurement.
    """
    identifier(cycle_id)
    _sha(input_sha256)
    if (not isinstance(public_source, str) or not public_source
            or len(public_source.encode("utf-8")) > 3000):
        raise ValueError("bounded nonempty public source required")
    root = Path(receipt_root)
    if root.exists() or root.is_symlink():
        raise FileExistsError("fresh one-B adapter receipt root required")
    guest_path = Path(guest_source_path)
    if (guest_path.is_symlink() or not guest_path.is_file()
            or guest_path.stat().st_size > MAX_GUEST_SOURCE_BYTES):
        raise ValueError("missing or unsafe guest source")
    guest_raw = guest_path.read_bytes()
    if not guest_raw or len(guest_raw) > MAX_GUEST_SOURCE_BYTES:
        raise ValueError("missing or oversized guest source bytes")
    guest_text = guest_raw.decode("utf-8")
    guest_sha = hashlib.sha256(guest_raw).hexdigest()
    if file_hash(guest_path) != guest_sha:
        raise ValueError("guest source changed while reading")
    adapter_sha = file_hash(__file__)
    if state.snapshot()["active_cycle"] != cycle_id:
        raise ValueError("supervisor cycle is not active")
    before_ns = clock_ns()
    if type(before_ns) is not int:
        raise ValueError("invalid host monotonic clock")
    root.mkdir(mode=0o700)
    fresh_json(root / "claim.json", {
        "schema": "market_one_b_transport_claim_v1", "cycle_id": cycle_id,
        "input_sha256": input_sha256,
        "public_source_sha256": hashlib.sha256(public_source.encode()).hexdigest(),
        "guest_source_sha256": guest_sha, "adapter_source_sha256": adapter_sha,
        "expected_tasks": EXPECTED_HANDOFFS, "guest_command": GUEST_COMMAND,
        "synthetic_tasks": True, "glm_authorship_proven": False,
        "isolation_proven": False, "provider_latency_proven": False,
        "automatic_retry": False})
    stage = "pre_account"
    sandbox = None
    sandbox_id = None
    session = None
    summary = None
    policy_receipt = None
    error = None
    milestones = []
    callback_to_a_read_ns = []
    command_receipt = None
    cleanup = {"sandbox_id": None, "id_unchanged": False,
               "kill_acknowledged": False, "account_clear": False}
    try:
        pre = _account_receipt(check_account_clear, None)
        fresh_json(root / "pre-account.json", pre)
        stage = "create_b"
        sandbox = create_sandbox()
        sandbox_id = getattr(sandbox, "sandbox_id", None)
        if not isinstance(sandbox_id, str) or not sandbox_id:
            raise ValueError("created B has no stable sandbox ID")
        cleanup["sandbox_id"] = sandbox_id
        create_done_ns = clock_ns()
        if type(create_done_ns) is not int or create_done_ns < before_ns:
            raise ValueError("host monotonic clock regressed")
        fresh_json(root / "sandbox.json", {
            "schema": "market_one_b_sandbox_v1", "sandbox_id": sandbox_id,
            "host_create_start_ns": before_ns, "host_create_done_ns": create_done_ns,
            "startup_latency_ns": create_done_ns - before_ns})
        observed = _ObservedB(sandbox, sandbox_id)
        stage = "guest_source_transfer"
        observed.files.write(GUEST_SCRIPT, guest_text)
        if observed.files.read(GUEST_SCRIPT) != guest_text:
            raise ValueError("guest source transfer mismatch")
        stage = "guest_staging_setup"
        if observed.files.make_dir(STAGING_DIR) is not True:
            raise ValueError("guest staging directory is not fresh")
        stage = "guest_ttl"
        policy_receipt = _require_guest_ttl(sandbox, sandbox_id, cycle_id)
        fresh_json(root / "sandbox-ttl.json", policy_receipt)
        stage = "directional_handoff_setup"
        handoff = DirectionalHandoff(
            researcher_sandbox=observed, state=state, cycle_id=cycle_id,
            input_sha256=input_sha256, receipt_root=root / "handoff",
            clock_ns=clock_ns)
        stage = "launch_guest"
        session = launch_guest(sandbox, GUEST_COMMAND)
        if not all(callable(getattr(session, name, None))
                   for name in ("next_message", "wait")):
            raise TypeError("guest launcher did not return an observed session")
        for sequence in range(EXPECTED_HANDOFFS):
            stage = f"task_{sequence:03d}"
            if sandbox.sandbox_id != sandbox_id:
                raise ValueError("B sandbox identity changed")
            if (file_hash(guest_path) != guest_sha
                    or file_hash(__file__) != adapter_sha):
                raise ValueError("executable source changed during B transport")
            task = {"schema": "market_directional_task_v1",
                    "cycle_id": cycle_id, "input_sha256": input_sha256,
                    "sequence": sequence, "task_id": f"public-source-{sequence:03d}",
                    "public_text": f"{public_source}\nitem:{sequence:03d}"}
            handoff.send_task(sequence, task)
            milestones.append(_milestone(session, sequence, "ack", clock_ns))
            handoff.receive_ack(sequence)
            event_milestone = _milestone(session, sequence, "event", clock_ns)
            milestones.append(event_milestone)
            handoff.receive_event(sequence)
            handoff.read_event_for_a(sequence)
            handoff._guard()
            read_receipt = json.loads((handoff.root / f"{sequence:03d}-a-read.json").read_text())
            visibility_ns = (read_receipt["host_read_done_ns"]
                             - event_milestone["host_callback_ns"])
            if type(visibility_ns) is not int or visibility_ns < 0:
                raise ValueError("invalid callback-to-A host timing")
            callback_to_a_read_ns.append(visibility_ns)
        stage = "guest_completion"
        command_receipt = session.wait(PROCESS_WAIT_SECONDS)
        if session.next_message(0) is not None:
            raise ValueError("extra guest milestone after 20 tasks")
        stage = "summary"
        summary = handoff.finish()
        if not summary["friction_criterion_passed"]:
            raise RuntimeError("predeclared directional friction criterion failed")
        callback_p95_ns = sorted(callback_to_a_read_ns)[
            math.ceil(.95 * len(callback_to_a_read_ns)) - 1]
        callback_max_ns = max(callback_to_a_read_ns)
        if (callback_p95_ns > P95_LIMIT_NS
                or callback_max_ns > SINGLE_LEG_LIMIT_NS):
            raise RuntimeError("callback-to-A event visibility criterion failed")
        if (file_hash(guest_path) != guest_sha
                or file_hash(__file__) != adapter_sha):
            raise ValueError("executable source changed after B transport")
        fresh_json(root / "milestones.json", {"items": milestones})
        fresh_json(root / "callback-visibility.json", {
            "schema": "market_one_b_callback_visibility_v1",
            "callback_to_a_read_ns": callback_to_a_read_ns,
            "p95_ns": callback_p95_ns, "max_ns": callback_max_ns,
            "p95_limit_ns": P95_LIMIT_NS,
            "single_leg_limit_ns": SINGLE_LEG_LIMIT_NS,
            "criterion_passed": True,
            "live_callback_timing": isinstance(session, E2BGuestSession)})
        fresh_json(root / "guest-command.json", command_receipt)
    except Exception as exc:
        error = exc
        fresh_json(root / "failure.json", {
            "schema": "market_one_b_transport_failure_v1", "stage": stage,
            "error_type": type(exc).__name__, "sandbox_id": sandbox_id,
            "completed_milestones": len(milestones)})
    finally:
        if sandbox is not None:
            try:
                cleanup["id_unchanged"] = sandbox.sandbox_id == sandbox_id
                cleanup["kill_acknowledged"] = sandbox.kill() is True
            except Exception as exc:
                cleanup["kill_error_type"] = type(exc).__name__
        try:
            post = _account_receipt(check_account_clear, sandbox_id)
            cleanup["account_clear"] = True
            fresh_json(root / "post-account.json", post)
        except Exception as exc:
            cleanup["account_error_type"] = type(exc).__name__
        fresh_json(root / "cleanup.json", cleanup)
    if not (cleanup["id_unchanged"] and cleanup["kill_acknowledged"]
            and cleanup["account_clear"]):
        raise RuntimeError("exact B cleanup or account-clear check unconfirmed") from error
    if error is not None:
        raise error
    assert summary is not None and command_receipt is not None and policy_receipt is not None
    receipt = {"schema": "market_one_b_transport_result_v1",
               "cycle_id": cycle_id, "sandbox_id": sandbox_id,
               "handoff_summary_sha256": digest(summary),
               "guest_command_sha256": digest(command_receipt),
               "milestones_sha256": file_hash(root / "milestones.json"),
               "callback_visibility_sha256": file_hash(root / "callback-visibility.json"),
               "cleanup_sha256": file_hash(root / "cleanup.json"),
               "sandbox_policy_sha256": file_hash(root / "sandbox-ttl.json"),
               "friction_criterion_passed": True,
               "policy_echo_accepted": policy_receipt["policy_echo_accepted"],
               "synthetic_transport_diagnostic_only": policy_receipt[
                   "synthetic_transport_diagnostic_only"],
               "synthetic_tasks": True, "glm_authorship_proven": False,
               "isolation_proven": False, "provider_latency_proven": False,
               "cost_verified": False}
    fresh_json(root / "result.json", receipt)
    return receipt
