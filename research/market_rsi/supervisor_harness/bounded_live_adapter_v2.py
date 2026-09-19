"""One-sample GLM -> trusted broker -> one-task local-Docker B adapter.

The production path composes the already-pinned Tinker backend and local B
boundary.  Credentials remain inside the backend object and are never passed
to B.  The offline path accepts only the exact fakes defined here.  This module
has no CLI: release/state/budget admission belongs to the outer runner.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from codex_glm_provider import (
    CHAT_TEMPLATE_SHA256, TOKENIZER_REVISION, TinkerGLMBackend,
)
from glm_canary import HF_MODEL, MODEL, RATES, cost
from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json
from supervisor_harness import directional_guest_worker as guest
from supervisor_harness import frozen_glm_first_response as first
from supervisor_harness import local_b_container
from supervisor_harness import local_b_containment_canary as cleanup_contract
from supervisor_harness import offline_a_to_b_driver as offline_driver


ADAPTER_SCHEMA = "market_bounded_live_adapter_v2"
REQUEST_SCHEMA = "market_bounded_live_first_request_v2"
PROVIDER_RECEIPT_SCHEMA = "market_bounded_live_provider_receipt_v2"
LAUNCH_SCHEMA = "market_bounded_live_b_launch_v2"
PROCESS_SCHEMA = "market_bounded_live_b_process_v2"
CLEANUP_SCHEMA = "market_bounded_live_b_cleanup_v2"
RESULT_SCHEMA = "market_bounded_live_result_v2"
MAX_OUTPUT_TOKENS = 512
SAMPLE_TIMEOUT_SECONDS = 30
B_FILE_TIMEOUT_SECONDS = 5
PROCESS_WAIT_SECONDS = 8
MAX_STDIO_BYTES = 16 * 1024
MAX_COST_UPPER_USD = Decimal("0.05")
GUEST_SOURCE = Path(__file__).with_name("directional_guest_worker.py")
SYSTEM_PROMPT = (
    "Choose exactly one supplied public or synthetic item for the fixed "
    "hash_public_text task. No tools are available. Return one JSON object and "
    "nothing else as the final answer; do not reveal chain of thought. The JSON "
    "keys are schema, task_id, source_id, "
    "action. schema must be market_glm_bounded_synthetic_choice_v1 and action "
    "must be hash_public_text. Never return code, commands, paths, keys, host "
    "authority, model calls, benchmark fields, or claims about unseen results."
)


def _sources() -> dict[str, str]:
    return {
        "adapter": file_hash(__file__),
        "provider": file_hash(Path(__file__).resolve().parents[1] /
                              "codex_glm_provider.py"),
        "cost": file_hash(Path(__file__).resolve().parents[1] / "glm_canary.py"),
        "packet_gate": file_hash(first.__file__),
        "choice_gate": file_hash(offline_driver.__file__),
        "container": file_hash(local_b_container.__file__),
        "guest": file_hash(GUEST_SOURCE),
        "cleanup": file_hash(cleanup_contract.__file__),
    }


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON field denied")
        value[key] = item
    return value


def _final_decision_text(raw: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise ValueError("missing first response text")
    if raw.lower().count("<tool_call"):
        raise ValueError("tool calls are forbidden")
    if raw.count("</think>") > 1:
        raise ValueError("ambiguous multiple reasoning terminators")
    final = raw.rsplit("</think>", 1)[-1].strip()
    terminal_markers = ("<|assistant|>", "<|endoftext|>", "<|user|>")
    removed = True
    while removed:
        removed = False
        for marker in terminal_markers:
            if final.endswith(marker):
                final = final.removesuffix(marker).strip()
                removed = True
    if final.startswith("```json\n") and final.endswith("\n```"):
        final = final[len("```json\n"):-len("\n```")].strip()
    if not final or len(final.encode("utf-8")) > first.MAX_PACKET_BYTES:
        raise ValueError("missing or oversized final choice")
    return final


def _choice(raw: str, packet: dict) -> tuple[dict, dict]:
    try:
        value = json.loads(_final_decision_text(raw),
                           object_pairs_hook=_unique_object)
    except json.JSONDecodeError as exc:
        raise ValueError("first response has no exact single JSON choice") from exc
    return offline_driver._choice(canonical(value), packet)


def _b_message(raw) -> dict:
    if (not isinstance(raw, str) or not raw
            or len(raw.encode("utf-8")) > guest.MAX_ORDER_BYTES):
        raise ValueError("missing or oversized B receipt")
    value = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError("B receipt must be an object")
    return value


def _bounded_stdio(value: str | bytes | None) -> tuple[str, int, str]:
    if value is None:
        value = ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if not isinstance(value, str):
        raise ValueError("B process output must be text")
    raw = value.encode("utf-8")
    if len(raw) > MAX_STDIO_BYTES:
        raise ValueError("B process output is oversized")
    return value, len(raw), hashlib.sha256(raw).hexdigest()


class OfflinePinnedProviderFake:
    """Exact offline provider fake; it has no imports or external client."""

    provider_called = False

    def __init__(self, sampled, *, token_ids: list[int] | None = None,
                 sample_error: Exception | None = None):
        self.sampled = sampled
        self.token_ids = [101, 102, 103] if token_ids is None else token_ids
        self.sample_error = sample_error
        self.encode_calls = 0
        self.sample_calls = 0

    def encode(self, turn: dict) -> dict:
        self.encode_calls += 1
        if (self.encode_calls != 1 or set(turn) != {"messages", "tools"}
                or turn["tools"] != []):
            raise ValueError("offline provider accepts one no-tools encoding")
        return {
            "rendered_prompt": "offline-pinned-template:" + canonical(turn),
            "token_ids": list(self.token_ids), "tokenizer_repo": HF_MODEL,
            "tokenizer_revision": TOKENIZER_REVISION,
            "chat_template_sha256": CHAT_TEMPLATE_SHA256,
        }

    def sample(self, token_ids: list[int], max_output_tokens: int,
               timeout_seconds: int):
        self.sample_calls += 1
        if (self.sample_calls != 1 or token_ids != self.token_ids
                or max_output_tokens != MAX_OUTPUT_TOKENS
                or timeout_seconds != SAMPLE_TIMEOUT_SECONDS):
            raise ValueError("offline provider sample duplicated or changed")
        if self.sample_error is not None:
            raise self.sample_error
        return self.sampled


class OfflineOneTaskProcessFake:
    """Strict local-B process/file fake with no subprocess or Docker access."""

    external_called = False

    def __init__(self, *, mode: str = "ok", container_name: str = "fake-local-b-v2"):
        identifier(container_name)
        self.mode = mode
        self.container_name = container_name
        self.launch_calls = 0
        self.publish_calls = 0
        self.wait_calls = 0
        self.order = None
        self.ack = None
        self.event = None
        self.command = None

    def launch(self, runtime_root: Path, cycle_id: str) -> dict:
        self.launch_calls += 1
        if self.launch_calls != 1 or self.order is not None:
            raise ValueError("fake B launch duplicated")
        self.command = [
            "docker", "run", "--rm", "--pull", "never", "--name",
            self.container_name, "--network", "none", "--read-only",
            local_b_container.IMAGE, "python", "-I", local_b_container.GUEST_PATH,
            "--root", local_b_container.WORK_PATH, "--per-order-timeout", "10",
            "--total-timeout", "120", "--expected-orders", "1",
        ]
        receipt = {
            "schema": LAUNCH_SCHEMA, "cycle_id": cycle_id,
            "container_name": self.container_name,
            "image": local_b_container.IMAGE, "command": self.command,
            "expected_orders": 1, "guest_source_sha256": file_hash(GUEST_SOURCE),
            "credential_fields_passed_to_b": [], "runtime_root": str(runtime_root),
            "offline_fake": True,
        }
        if self.mode == "launch_error_after_start":
            raise RuntimeError("fake launch failed after process creation")
        return receipt

    def publish(self, order: dict) -> None:
        self.publish_calls += 1
        if self.publish_calls != 1 or self.order is not None:
            raise ValueError("fake B order duplicated")
        self.order = order
        text_sha = hashlib.sha256(order["public_text"].encode()).hexdigest()
        self.ack = {"schema": "market_directional_ack_v1",
                    "cycle_id": order["cycle_id"], "sequence": 0,
                    "order_sha256": digest(order)}
        self.event = {"schema": "market_directional_tool_event_v1",
                      "cycle_id": order["cycle_id"], "sequence": 0,
                      "task_id": order["task_id"],
                      "order_sha256": digest(order),
                      "tool_name": "hash_public_text",
                      "input_sha256": text_sha, "output_sha256": text_sha,
                      "status": "ok"}
        if self.mode == "wrong_ack":
            self.ack["order_sha256"] = "0" * 64
        if self.mode == "wrong_event":
            self.event["output_sha256"] = "0" * 64

    def read_ack(self, timeout_seconds: int) -> str:
        if timeout_seconds != B_FILE_TIMEOUT_SECONDS or self.order is None:
            raise ValueError("fake ACK read contract changed")
        if self.mode == "ack_timeout":
            raise TimeoutError("fake B ACK timed out")
        return canonical(self.ack)

    def read_event(self, timeout_seconds: int) -> str:
        if timeout_seconds != B_FILE_TIMEOUT_SECONDS or self.order is None:
            raise ValueError("fake event read contract changed")
        if self.mode == "event_timeout":
            raise TimeoutError("fake B event timed out")
        return canonical(self.event)

    def wait(self, timeout_seconds: int):
        self.wait_calls += 1
        if timeout_seconds not in {1, PROCESS_WAIT_SECONDS} or self.wait_calls != 1:
            raise ValueError("fake process wait duplicated or changed")
        if self.mode == "missing_process":
            return None
        return {
            "schema": PROCESS_SCHEMA, "container_name": self.container_name,
            "exit_code": None if self.mode == "process_timeout" else 0,
            "timed_out": self.mode == "process_timeout",
            "process_reaped": self.mode != "process_timeout",
            "stdout_bytes": 0, "stderr_bytes": 0,
            "stdout_sha256": hashlib.sha256(b"").hexdigest(),
            "stderr_sha256": hashlib.sha256(b"").hexdigest(),
            "expected_orders": 1, "offline_fake": True,
        }

    def verify_one_exchange(self) -> bool:
        return (self.mode != "extra_order" and self.publish_calls == 1
                and self.order is not None)


class OfflineContainerControlFake:
    """Exact cleanup fake, separate from the fake process."""

    external_called = False

    def __init__(self, *, mode: str = "ok"):
        self.mode = mode
        self.calls = 0

    def cleanup(self, process: OfflineOneTaskProcessFake) -> dict:
        self.calls += 1
        if self.calls != 1 or type(process) is not OfflineOneTaskProcessFake:
            raise ValueError("fake cleanup duplicated or process type changed")
        verified = self.mode != "missing_cleanup"
        return {
            "schema": CLEANUP_SCHEMA,
            "container_name": process.container_name,
            "initial_inspection": "owned" if verified else "unknown",
            "stop_acknowledged": True if verified else False,
            "final_inspection": "absent" if verified else "unknown",
            "process_reaped": process.mode != "process_timeout",
            "exact_container_cleanup_verified": verified,
            "offline_fake": True,
        }


class LocalDockerOneTaskProcess:
    """Production local process boundary; never receives provider credentials."""

    external_called = True

    def __init__(self):
        self.container_name = None
        self.process = None
        self.files = None
        self.work = None
        self.command = None
        self.publish_calls = 0
        self._waited = False

    def launch(self, runtime_root: Path, cycle_id: str) -> dict:
        if self.process is not None:
            raise ValueError("local B launch duplicated")
        runtime_root = Path(runtime_root)
        runtime_root.mkdir(mode=0o700, exist_ok=False)
        self.work = runtime_root / "work"
        self.work.mkdir(mode=0o700)
        self.container_name = "market-rsi-b-" + cycle_id
        self.command = local_b_container.docker_command(
            container_name=self.container_name, source=GUEST_SOURCE,
            work=self.work, expected_orders=1)
        self.process = subprocess.Popen(
            self.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True)
        self.files = local_b_container.LocalBFiles(self.work)
        return {
            "schema": LAUNCH_SCHEMA, "cycle_id": cycle_id,
            "container_name": self.container_name,
            "image": local_b_container.IMAGE, "command": self.command,
            "expected_orders": 1, "guest_source_sha256": file_hash(GUEST_SOURCE),
            "credential_fields_passed_to_b": [], "runtime_root": str(runtime_root),
            "offline_fake": False,
        }

    def publish(self, order: dict) -> None:
        self.publish_calls += 1
        if self.publish_calls != 1 or self.files is None:
            raise ValueError("local B order duplicated or process absent")
        self.files.write(local_b_container.GUEST_ROOT + "/orders/000.json",
                         canonical(order))

    def _read(self, kind: str, timeout_seconds: int) -> str:
        if timeout_seconds != B_FILE_TIMEOUT_SECONDS or self.files is None:
            raise ValueError("local B read contract changed")
        path = self.work / kind / "000.json"
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if path.exists() or path.is_symlink():
                return self.files.read(
                    local_b_container.GUEST_ROOT + f"/{kind}/000.json")
            if self.process.poll() is not None:
                raise RuntimeError(f"local B exited before {kind}")
            time.sleep(.01)
        raise TimeoutError(f"local B {kind} timed out")

    def read_ack(self, timeout_seconds: int) -> str:
        return self._read("acks", timeout_seconds)

    def read_event(self, timeout_seconds: int) -> str:
        return self._read("events", timeout_seconds)

    def wait(self, timeout_seconds: int):
        if self._waited or self.process is None:
            raise ValueError("local B process wait duplicated or absent")
        self._waited = True
        timed_out = False
        try:
            stdout, stderr = self.process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout, stderr = exc.stdout, exc.stderr
        stdout, stdout_bytes, stdout_sha = _bounded_stdio(stdout)
        stderr, stderr_bytes, stderr_sha = _bounded_stdio(stderr)
        return {
            "schema": PROCESS_SCHEMA, "container_name": self.container_name,
            "exit_code": None if timed_out else self.process.returncode,
            "timed_out": timed_out,
            "process_reaped": self.process.poll() is not None,
            "stdout_bytes": stdout_bytes, "stderr_bytes": stderr_bytes,
            "stdout_sha256": stdout_sha, "stderr_sha256": stderr_sha,
            "expected_orders": 1, "offline_fake": False,
        }

    def verify_one_exchange(self) -> bool:
        if self.work is None:
            return False
        expected = {"orders", "acks", "events", "staging"}
        if ({entry.name for entry in self.work.iterdir()} != expected
                or any((self.work / kind).is_symlink()
                       for kind in expected)
                or any((self.work / kind).is_file() for kind in expected)):
            return False
        return (not any((self.work / "staging").iterdir())
                and all({entry.name for entry in (self.work / kind).iterdir()}
                        == {"000.json"} for kind in ("orders", "acks", "events")))

    def close_files(self) -> None:
        if self.files is not None:
            self.files.close()
            self.files = None


class LocalDockerContainerControl:
    """Parent-owned exact-label container cleanup and process reap."""

    external_called = True

    def cleanup(self, process: LocalDockerOneTaskProcess) -> dict:
        if type(process) is not LocalDockerOneTaskProcess:
            raise ValueError("exact local B process required for cleanup")
        process.close_files()
        cleanup = {"initial_inspection": "unknown",
                   "stop_acknowledged": False,
                   "final_inspection": "unknown",
                   "exact_container_cleanup_verified": False}
        if isinstance(process.container_name, str):
            try:
                cleanup = cleanup_contract._cleanup_exact(
                    process.container_name, control_run=subprocess.run)
            except Exception:
                pass
        reaped = process.process is not None and process.process.poll() is not None
        if process.process is not None and not reaped:
            try:
                process.process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.process.kill()
                process.process.communicate()
            reaped = process.process.poll() is not None
        return {
            "schema": CLEANUP_SCHEMA,
            "container_name": process.container_name,
            "initial_inspection": cleanup["initial_inspection"],
            "stop_acknowledged": cleanup["stop_acknowledged"],
            "final_inspection": cleanup["final_inspection"],
            "process_reaped": reaped,
            "exact_container_cleanup_verified":
                cleanup["exact_container_cleanup_verified"] and reaped,
            "offline_fake": False,
        }


def _execution_mode(backend, process, control) -> str:
    if (type(backend) is OfflinePinnedProviderFake
            and type(process) is OfflineOneTaskProcessFake
            and type(control) is OfflineContainerControlFake):
        return "offline_fake"
    if (type(backend) is TinkerGLMBackend
            and type(process) is LocalDockerOneTaskProcess
            and type(control) is LocalDockerContainerControl):
        return "live_pinned"
    raise RuntimeError("provider, process, and container controls must be exact matched types")


def _validate_encoding(encoded) -> int:
    if (not isinstance(encoded, dict)
            or set(encoded) != {"rendered_prompt", "token_ids", "tokenizer_repo",
                               "tokenizer_revision", "chat_template_sha256"}
            or not isinstance(encoded["rendered_prompt"], str)
            or not encoded["rendered_prompt"]
            or len(encoded["rendered_prompt"].encode("utf-8")) > 64 * 1024
            or encoded["tokenizer_repo"] != HF_MODEL
            or encoded["tokenizer_revision"] != TOKENIZER_REVISION
            or encoded["chat_template_sha256"] != CHAT_TEMPLATE_SHA256
            or not isinstance(encoded["token_ids"], list)
            or not 1 <= len(encoded["token_ids"]) <= 8192
            or any(type(token) is not int or token < 0
                   for token in encoded["token_ids"])):
        raise ValueError("pinned provider encoding is incomplete or changed")
    return len(encoded["token_ids"])


def _provider_receipt(sampled: dict, input_tokens: int,
                      *, provider_called: bool) -> dict:
    valid, reason = first._review_sample(sampled, input_tokens)
    if not valid:
        raise ValueError(reason)
    output_count = len(sampled["output_tokens"])
    cached = sampled["cached_input_tokens"]
    metered = cost(input_tokens, output_count, cached)
    return {
        "schema": PROVIDER_RECEIPT_SCHEMA,
        "requested_model": MODEL,
        "reported_model": sampled["provider"]["reported_model"],
        "provider_session_id": sampled["provider"]["session_id"],
        "sampling_session_id": sampled["provider"]["sampling_session_id"],
        "input_tokens": input_tokens,
        "output_tokens": output_count,
        "cached_input_tokens": cached,
        "output_token_ids_sha256": digest(sampled["output_tokens"]),
        "finish_reason": sampled["finish_reason"], "terminal": True,
        "rates": RATES, "metered_cost_usd_not_invoice": str(metered),
        "cost_basis": "returned token quantities x frozen rates; not invoice",
        "provider_called": provider_called, "automatic_retry": False,
        "sample_count": 1,
    }


def _process_valid(value: dict, container_name: str, *, offline: bool) -> bool:
    return (isinstance(value, dict)
            and set(value) == {"schema", "container_name", "exit_code",
                               "timed_out", "process_reaped", "stdout_bytes",
                               "stderr_bytes", "stdout_sha256", "stderr_sha256",
                               "expected_orders", "offline_fake"}
            and value.get("schema") == PROCESS_SCHEMA
            and value.get("container_name") == container_name
            and value.get("exit_code") == 0
            and value.get("timed_out") is False
            and value.get("process_reaped") is True
            and value.get("expected_orders") == 1
            and value.get("offline_fake") is offline
            and all(type(value.get(key)) is int and 0 <= value[key] <= MAX_STDIO_BYTES
                    for key in ("stdout_bytes", "stderr_bytes"))
            and all(isinstance(value.get(key), str) and len(value[key]) == 64
                    for key in ("stdout_sha256", "stderr_sha256")))


def _cleanup_valid(value: dict, container_name: str, *, offline: bool) -> bool:
    return (isinstance(value, dict)
            and set(value) == {"schema", "container_name", "initial_inspection",
                               "stop_acknowledged", "final_inspection",
                               "process_reaped", "exact_container_cleanup_verified",
                               "offline_fake"}
            and value.get("schema") == CLEANUP_SCHEMA
            and value.get("container_name") == container_name
            and value.get("process_reaped") is True
            and value.get("exact_container_cleanup_verified") is True
            and value.get("final_inspection") == "absent"
            and value.get("offline_fake") is offline)


def _failure(root: Path, cycle_id: str, stage: str, error: Exception) -> None:
    if not (root / "failure.json").exists():
        fresh_json(root / "failure.json", {
            "schema": "market_bounded_live_failure_v2", "cycle_id": cycle_id,
            "stage": stage, "error_type": type(error).__name__,
            "error_sha256": hashlib.sha256(str(error).encode()).hexdigest(),
            "automatic_retry": False,
        })


def run_bounded_adapter(*, root: Path, claim_root: Path, cycle_id: str,
                        packet: dict, backend, process, container_control) -> dict:
    """Consume one claim and compose one sample with one B task."""
    identifier(cycle_id)
    mode = _execution_mode(backend, process, container_control)
    packet = first._packet(packet, cycle_id)
    root, claim_root = Path(root), Path(claim_root)
    if (root.name != cycle_id or root.exists() or root.is_symlink()
            or not claim_root.is_dir() or claim_root.is_symlink()
            or claim_root.resolve() == root.resolve()):
        raise ValueError("fresh exact output and existing unique-claim registry required")
    source_hashes = _sources()
    offline = mode == "offline_fake"
    claim = {
        "schema": "market_bounded_live_claim_v2", "cycle_id": cycle_id,
        "packet_sha256": digest(packet), "source_hashes": source_hashes,
        "runtime": {"python_executable": str(Path(sys.executable).resolve()),
                    "python_version": sys.version},
        "requested_model": MODEL, "tools": [], "num_samples": 1,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "sample_timeout_seconds": SAMPLE_TIMEOUT_SECONDS,
        "expected_b_orders": 1, "automatic_retry": False,
        "execution_mode": mode, "formal_admission": False,
    }
    registry = claim_root / f"{cycle_id}.json"
    fresh_json(registry, claim)
    root.mkdir(mode=0o700)
    fresh_json(root / "claim.json", claim)
    fresh_json(root / "input.json", packet)
    stage = "request"
    error = None
    launch_attempted = False
    launched = False
    sample_attempted = False
    launch = process_receipt = cleanup_receipt = provider_receipt = None
    expected_records = {"claim.json": claim, "input.json": packet}
    expected_raw: dict[str, str] = {}
    try:
        request = {
            "schema": REQUEST_SCHEMA, "model": MODEL,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": canonical(packet)}],
            "tools": [], "num_samples": 1, "temperature": 1.0, "seed": 23,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "input_sha256": file_hash(root / "input.json"),
        }
        fresh_json(root / "request.json", request)
        expected_records["request.json"] = request
        stage = "encoding"
        encoded = backend.encode({"messages": request["messages"], "tools": []})
        input_tokens = _validate_encoding(encoded)
        fresh_json(root / "encoded.json", encoded)
        expected_records["encoded.json"] = encoded
        upper = cost(input_tokens, MAX_OUTPUT_TOKENS)
        if upper > MAX_COST_UPPER_USD:
            raise ValueError("provider cost upper bound exceeds adapter cap")
        cost_preview = {
            "schema": "market_bounded_live_cost_preview_v2",
            "input_tokens": input_tokens, "max_output_tokens": MAX_OUTPUT_TOKENS,
            "rates": RATES, "upper_usd_not_invoice": str(upper),
            "provider_called": False, "budget_mutated_by_adapter": False,
        }
        fresh_json(root / "cost-preview.json", cost_preview)
        expected_records["cost-preview.json"] = cost_preview
        stage = "first_provider_sample"
        sample_attempted = True
        sampled = backend.sample(encoded["token_ids"], MAX_OUTPUT_TOKENS,
                                 SAMPLE_TIMEOUT_SECONDS)
        # Preserve the first returned object before semantic/provenance review.
        fresh_json(root / "raw-response.json", sampled)
        if isinstance(sampled, dict) and isinstance(sampled.get("text"), str):
            with (root / "raw-response.txt").open("xb") as output:
                output.write(sampled["text"].encode("utf-8"))
            expected_raw["raw-response.txt"] = sampled["text"]
        expected_records["raw-response.json"] = sampled
        stage = "provider_receipt"
        provider_receipt = _provider_receipt(
            sampled, input_tokens, provider_called=not offline)
        fresh_json(root / "provider-receipt.json", provider_receipt)
        expected_records["provider-receipt.json"] = provider_receipt
        if _sources() != source_hashes:
            raise ValueError("executable source changed after first response")
        stage = "choice"
        decision, selected = _choice(sampled["text"], packet)
        fresh_json(root / "decision.json", decision)
        expected_records["decision.json"] = decision
        input_sha = file_hash(root / "input.json")
        task = {"schema": "market_directional_task_v1", "cycle_id": cycle_id,
                "input_sha256": input_sha, "sequence": 0,
                "task_id": decision["task_id"], "public_text": selected["text"]}
        order = {"schema": "market_directional_order_v1", "cycle_id": cycle_id,
                 "input_sha256": input_sha, "sequence": 0,
                 "task_id": decision["task_id"], "task_sha256": digest(task),
                 "public_text": selected["text"]}
        binding = {
            "schema": "market_bounded_live_broker_binding_v2",
            "cycle_id": cycle_id, "source_id": selected["source_id"],
            "public_text_sha256": selected["text_sha256"],
            "first_raw_response_sha256": file_hash(root / "raw-response.txt"),
            "decision_sha256": digest(decision), "task_sha256": digest(task),
            "order_sha256": digest(order), "allowed_action": "hash_public_text",
        }
        for name, value in (("broker-binding.json", binding),
                            ("task.json", task), ("order.json", order)):
            fresh_json(root / name, value)
            expected_records[name] = value
        stage = "b_launch"
        launch_attempted = True
        launch = process.launch(root / "b-runtime", cycle_id)
        launched = True
        if (not isinstance(launch, dict)
                or set(launch) != {"schema", "cycle_id", "container_name", "image",
                                   "command", "expected_orders",
                                   "guest_source_sha256",
                                   "credential_fields_passed_to_b", "runtime_root",
                                   "offline_fake"}
                or launch.get("schema") != LAUNCH_SCHEMA
                or launch.get("cycle_id") != cycle_id
                or launch.get("image") != local_b_container.IMAGE
                or launch.get("expected_orders") != 1
                or launch.get("guest_source_sha256") != file_hash(GUEST_SOURCE)
                or launch.get("credential_fields_passed_to_b") != []
                or launch.get("offline_fake") is not offline
                or not isinstance(launch.get("command"), list)
                or launch["command"].count("--expected-orders") != 1
                or launch["command"][launch["command"].index("--expected-orders") + 1] != "1"
                or any(item in {"--env", "-e", "--env-file", "--privileged",
                                "--publish", "-p"}
                       for item in launch["command"])):
            raise ValueError("one-task B launch receipt is incomplete or has authority")
        fresh_json(root / "b-launch.json", launch)
        expected_records["b-launch.json"] = launch
        stage = "b_publish"
        process.publish(order)
        stage = "b_ack"
        raw_ack = process.read_ack(B_FILE_TIMEOUT_SECONDS)
        with (root / "raw-ack.json").open("xb") as output:
            output.write(raw_ack.encode("utf-8"))
        expected_raw["raw-ack.json"] = raw_ack
        ack = _b_message(raw_ack)
        if ack != {"schema": "market_directional_ack_v1", "cycle_id": cycle_id,
                   "sequence": 0, "order_sha256": digest(order)}:
            raise ValueError("B ACK does not bind exact one-task order")
        stage = "b_event"
        raw_event = process.read_event(B_FILE_TIMEOUT_SECONDS)
        with (root / "raw-event.json").open("xb") as output:
            output.write(raw_event.encode("utf-8"))
        expected_raw["raw-event.json"] = raw_event
        event = _b_message(raw_event)
        text_sha = hashlib.sha256(selected["text"].encode()).hexdigest()
        if event != {"schema": "market_directional_tool_event_v1",
                      "cycle_id": cycle_id, "sequence": 0,
                      "task_id": decision["task_id"],
                      "order_sha256": digest(order),
                      "tool_name": "hash_public_text",
                      "input_sha256": text_sha, "output_sha256": text_sha,
                      "status": "ok"}:
            raise ValueError("B event does not bind exact public hash task")
        stage = "b_process"
        process_receipt = process.wait(PROCESS_WAIT_SECONDS)
        if not _process_valid(process_receipt, launch["container_name"],
                              offline=offline):
            raise ValueError("B process receipt missing or nonterminal")
        fresh_json(root / "process.json", process_receipt)
        expected_records["process.json"] = process_receipt
        if not process.verify_one_exchange():
            raise ValueError("B work directory is not exactly one exchange")
    except Exception as exc:
        error = exc
    finally:
        if launch_attempted and process_receipt is None:
            try:
                process_receipt = process.wait(1)
            except Exception:
                process_receipt = None
        if not (root / "process.json").exists():
            fallback_process = (process_receipt if isinstance(process_receipt, dict)
                                else {"schema": PROCESS_SCHEMA,
                                      "container_name": (launch or {}).get(
                                          "container_name", getattr(
                                              process, "container_name", None)),
                                      "exit_code": None,
                                      "timed_out": launch_attempted,
                                      "process_reaped": not launch_attempted,
                                      "stdout_bytes": 0, "stderr_bytes": 0,
                                      "stdout_sha256": hashlib.sha256(b"").hexdigest(),
                                      "stderr_sha256": hashlib.sha256(b"").hexdigest(),
                                      "expected_orders": 1,
                                      "offline_fake": offline})
            fresh_json(root / "process.json", fallback_process)
            expected_records["process.json"] = fallback_process
            process_receipt = fallback_process
        if launch_attempted:
            try:
                cleanup_receipt = container_control.cleanup(process)
            except Exception:
                cleanup_receipt = None
        if cleanup_receipt is None:
            cleanup_receipt = {
                "schema": CLEANUP_SCHEMA,
                "container_name": (launch or {}).get(
                    "container_name", getattr(process, "container_name", None)),
                "initial_inspection": ("not_started" if not launch_attempted
                                       else "unknown"),
                "stop_acknowledged": False,
                "final_inspection": ("absent" if not launch_attempted
                                     else "unknown"),
                "process_reaped": not launch_attempted,
                "exact_container_cleanup_verified": not launch_attempted,
                "offline_fake": offline,
            }
        fresh_json(root / "cleanup.json", cleanup_receipt)
        expected_records["cleanup.json"] = cleanup_receipt
    if error is None:
        stage = "final_integrity"
        try:
            if (not launched or launch is None
                    or not _process_valid(process_receipt, launch["container_name"],
                                          offline=offline)
                    or not _cleanup_valid(cleanup_receipt, launch["container_name"],
                                          offline=offline)
                    or _sources() != source_hashes
                    or load_json(registry) != claim
                    or any(load_json(root / name) != value
                           for name, value in expected_records.items())):
                raise ValueError("source, lineage, process, or cleanup integrity failed")
            if any((root / name).read_text(encoding="utf-8") != value
                   for name, value in expected_raw.items()):
                raise ValueError("raw response, ACK, or event receipt changed")
        except Exception as exc:
            error = exc
    if error is not None:
        _failure(root, cycle_id, stage, error)
    passed = error is None
    hash_names = (
        "claim.json", "input.json", "request.json", "encoded.json",
        "cost-preview.json", "raw-response.json", "raw-response.txt",
        "provider-receipt.json", "decision.json", "broker-binding.json",
        "task.json", "order.json", "b-launch.json", "raw-ack.json",
        "raw-event.json", "process.json", "cleanup.json",
    )
    result = {
        "schema": RESULT_SCHEMA, "cycle_id": cycle_id,
        "passed_offline_boundary_test": passed and offline,
        "completed_live_chain_pending_review": passed and not offline,
        "execution_mode": mode,
        "failure_type": type(error).__name__ if error is not None else None,
        "artifact_sha256": {name: file_hash(root / name)
                            if (root / name).is_file() else None
                            for name in hash_names},
        "registry_claim_sha256": file_hash(registry),
        "requested_model": MODEL,
        "reported_model": (provider_receipt or {}).get("reported_model"),
        "input_tokens": (provider_receipt or {}).get("input_tokens"),
        "output_tokens": (provider_receipt or {}).get("output_tokens"),
        "cached_input_tokens": (provider_receipt or {}).get("cached_input_tokens"),
        "metered_cost_usd_not_invoice": (provider_receipt or {}).get(
            "metered_cost_usd_not_invoice"),
        "provider_called": not offline and sample_attempted,
        "automatic_retry": False, "sample_count_max": 1,
        "b_task_count_max": 1,
        "exact_container_cleanup_verified": _cleanup_valid(
            cleanup_receipt, (launch or {}).get("container_name"), offline=offline)
            if launched else False,
        "model_identity_independently_proven": False,
        "model_authorship_independently_proven": False,
        "full_isolation_proven": False, "formal_admission": False,
        "budget_mutated_by_adapter": False,
    }
    fresh_json(root / "result.json", result)
    return result
