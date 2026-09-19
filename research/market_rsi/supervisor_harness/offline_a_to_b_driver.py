"""Offline-only fake Controller -> trusted broker -> fake local-B binding.

One already-preserved fake GLM first response may select a bounded public item
for a fixed hash task. The broker constructs the exact order; model text never
becomes code, shell, file path or a B credential. This does not launch Docker,
call GLM, prove authorship/isolation or admit a research cycle.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from glm_canary import MODEL
from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json
from supervisor_harness import frozen_glm_first_response as first


DECISION_SCHEMA = "market_glm_bounded_synthetic_choice_v1"
ORDER_SCHEMA = "market_offline_broker_order_v1"
ACK_SCHEMA = "market_offline_b_ack_v1"
EVENT_SCHEMA = "market_offline_b_event_v1"
MAX_MESSAGE_BYTES = 4096


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON field denied")
        value[key] = item
    return value


def _bounded_json(raw: str, *, label: str) -> dict:
    if (not isinstance(raw, str) or not raw
            or len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES):
        raise ValueError(f"{label} missing or oversized")
    value = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _sources() -> dict:
    return {"offline_driver": file_hash(__file__),
            "first_response_adapter": file_hash(first.__file__)}


def _read(root: Path, name: str) -> dict:
    path = root / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024:
        raise ValueError("missing or unsafe frozen Controller receipt")
    value = load_json(path)
    if not isinstance(value, dict):
        raise ValueError("frozen Controller receipt must be an object")
    return value


def _verify_first_response(glm_root: Path, glm_claim_root: Path,
                           cycle_id: str) -> tuple[dict, str, dict[str, str]]:
    if glm_root.name != cycle_id or glm_root.is_symlink():
        raise ValueError("exact frozen Controller root required")
    packet = _read(glm_root, "input.json")
    first._packet(packet, cycle_id)
    claim = _read(glm_root, "claim.json")
    request = _read(glm_root, "request.json")
    encoded = _read(glm_root, "encoded.json")
    sampled = _read(glm_root, "raw-response.json")
    result = _read(glm_root, "result.json")
    raw_path = glm_root / "raw-response.txt"
    if raw_path.is_symlink() or not raw_path.is_file() or raw_path.stat().st_size > 16 * 1024:
        raise ValueError("first raw Controller text missing or unsafe")
    raw = raw_path.read_text(encoding="utf-8")
    registry = glm_claim_root / f"{cycle_id}.json"
    if (glm_claim_root.is_symlink() or registry.is_symlink()
            or not registry.is_file() or registry.stat().st_size > 64 * 1024
            or load_json(registry) != claim
            or claim.get("schema") != "market_glm_first_claim_v1"
            or claim.get("cycle_id") != cycle_id
            or claim.get("source_hashes") != first._current_sources()
            or claim.get("runtime") != {
                "python_executable": str(Path(sys.executable).resolve()),
                "python_version": sys.version}
            or claim.get("provider_called") is not False
            or claim.get("formal_admission") is not False
            or claim.get("tools") != []
            or claim.get("num_samples") != 1
            or claim.get("packet_sha256") != digest(packet)
            or request.get("schema") != first.REQUEST_SCHEMA
            or request.get("model") != MODEL
            or request.get("tools") != []
            or request.get("num_samples") != 1
            or request.get("input_sha256") != file_hash(glm_root / "input.json")
            or request.get("messages") != [
                {"role": "system", "content": first.SYSTEM_PROMPT},
                {"role": "user", "content": canonical(packet)}]
            or not isinstance(encoded.get("token_ids"), list)
            or not first._review_sample(sampled, len(encoded["token_ids"]))[0]
            or sampled.get("text") != raw
            or result.get("schema") != "market_glm_first_offline_result_v1"
            or result.get("cycle_id") != cycle_id
            or result.get("valid_fake_response") is not True
            or result.get("requested_model") != MODEL
            or result.get("provider_called") is not False
            or result.get("actual_provider_cost_usd") != "0"
            or result.get("model_authorship_proven") is not False
            or result.get("formal_admission") is not False
            or result.get("claim_sha256") != file_hash(glm_root / "claim.json")
            or result.get("registry_claim_sha256") != file_hash(registry)
            or result.get("input_sha256") != file_hash(glm_root / "input.json")
            or result.get("request_sha256") != file_hash(glm_root / "request.json")
            or result.get("encoded_sha256") != file_hash(glm_root / "encoded.json")
            or result.get("raw_response_sha256") != file_hash(glm_root / "raw-response.json")
            or result.get("raw_text_sha256") != file_hash(raw_path)):
        raise ValueError("frozen fake Controller lineage changed or incomplete")
    names = ("input.json", "claim.json", "request.json", "encoded.json",
             "raw-response.json", "raw-response.txt", "result.json")
    hashes = {name: file_hash(glm_root / name) for name in names}
    hashes["registry_claim"] = file_hash(registry)
    return packet, raw, hashes


def _choice(raw: str, packet: dict) -> tuple[dict, dict]:
    decision = _bounded_json(raw, label="first Controller choice")
    if (set(decision) != {"schema", "task_id", "source_id", "action"}
            or decision.get("schema") != DECISION_SCHEMA
            or decision.get("action") != "hash_public_text"):
        raise ValueError("only one allowlisted public hash choice is accepted")
    identifier(decision["task_id"])
    candidates = [item for item in packet["context_items"]
                  if item["source_id"] == decision["source_id"]]
    if len(candidates) != 1:
        raise ValueError("choice must select exactly one allowed public item")
    return decision, candidates[0]


class OfflineFakeLocalB:
    """Exact offline fake; there is no Docker, E2B, shell or host file view."""

    def __init__(self, sandbox_id: str = "fake-local-b", *, mode: str = "ok"):
        identifier(sandbox_id)
        self.sandbox_id = sandbox_id
        self.mode = mode
        self.order = None
        self.sent = 0
        self.kills = 0
        self._ack = None
        self._event = None

    def publish(self, order: dict) -> None:
        self.sent += 1
        if self.sent != 1 or self.order is not None:
            raise ValueError("fake B cannot receive a duplicate order")
        self.order = order
        text_sha = hashlib.sha256(order["public_text"].encode()).hexdigest()
        self._ack = {"schema": ACK_SCHEMA, "cycle_id": order["cycle_id"],
                     "sandbox_id": self.sandbox_id, "order_sha256": digest(order)}
        self._event = {"schema": EVENT_SCHEMA, "cycle_id": order["cycle_id"],
                       "sandbox_id": self.sandbox_id, "order_sha256": digest(order),
                       "task_id": order["task_id"], "tool_name": "hash_public_text",
                       "input_sha256": text_sha, "output_sha256": text_sha,
                       "status": "ok"}
        if self.mode == "wrong_event":
            self._event["output_sha256"] = "0" * 64

    def read_ack(self, timeout_seconds: int) -> str:
        if timeout_seconds != 5 or self.order is None:
            raise ValueError("fake B ACK read contract changed")
        if self.mode == "timeout":
            raise TimeoutError("synthetic B ACK deadline")
        return canonical(self._ack)

    def read_event(self, timeout_seconds: int) -> str:
        if timeout_seconds != 5 or self.order is None:
            raise ValueError("fake B event read contract changed")
        if self.mode == "event_timeout":
            raise TimeoutError("synthetic B event deadline")
        return canonical(self._event)

    def kill(self) -> bool:
        self.kills += 1
        return self.mode != "kill_false"

    def absent(self, expected_id: str) -> bool:
        return self.sandbox_id == expected_id and self.kills == 1 and self.mode != "account_not_clear"


def run_offline_binding(*, root: Path, claim_root: Path, cycle_id: str,
                        glm_root: Path, glm_claim_root: Path,
                        researcher: OfflineFakeLocalB) -> dict:
    """Bind one fake first response to one fake B task; consume the ID once."""
    identifier(cycle_id)
    if type(researcher) is not OfflineFakeLocalB:
        raise RuntimeError("real local-B dispatch disabled in this source version")
    packet, raw, frozen_hashes = _verify_first_response(
        Path(glm_root), Path(glm_claim_root), cycle_id)
    root, claim_root = Path(root), Path(claim_root)
    if (root.name != cycle_id or root.exists() or root.is_symlink()
            or not claim_root.is_dir() or claim_root.is_symlink()):
        raise ValueError("fresh exact driver output and registry required")
    source_hashes = _sources()
    sandbox_id = researcher.sandbox_id
    claim = {"schema": "market_offline_a_to_b_claim_v1", "cycle_id": cycle_id,
             "first_response_sha256": frozen_hashes["raw-response.txt"],
             "first_result_sha256": frozen_hashes["result.json"],
             "source_hashes": source_hashes, "fake_b_id": sandbox_id,
             "one_task_max": True, "timeout_seconds_per_read": 5,
             "automatic_retry": False, "provider_called": False,
             "synthetic_only": True, "formal_admission": False}
    fresh_json(claim_root / f"{cycle_id}.json", claim)
    root.mkdir(mode=0o700)
    fresh_json(root / "claim.json", claim)
    fresh_json(root / "frozen-input-hashes.json", frozen_hashes)
    stage = "choice"
    error_type = None
    decision = order = ack = event = None
    try:
        decision, selected = _choice(raw, packet)
        fresh_json(root / "decision.json", decision)
        stage = "broker_order"
        order = {"schema": ORDER_SCHEMA, "cycle_id": cycle_id,
                 "task_id": decision["task_id"], "source_id": selected["source_id"],
                 "public_text": selected["text"],
                 "public_text_sha256": selected["text_sha256"],
                 "decision_sha256": digest(decision),
                 "first_response_sha256": frozen_hashes["raw-response.txt"],
                 "input_sha256": frozen_hashes["input.json"]}
        if len(canonical(order).encode()) > MAX_MESSAGE_BYTES:
            raise ValueError("broker order exceeds byte bound")
        fresh_json(root / "broker-order.json", order)
        stage = "publish_to_fake_b"
        researcher.publish(order)
        stage = "read_ack"
        raw_ack = researcher.read_ack(5)
        with (root / "raw-ack.json").open("xb") as output:
            output.write(raw_ack.encode("utf-8"))
        ack = _bounded_json(raw_ack, label="B ACK")
        if ack != {"schema": ACK_SCHEMA, "cycle_id": cycle_id,
                   "sandbox_id": sandbox_id, "order_sha256": digest(order)}:
            raise ValueError("B ACK does not bind exact broker order")
        stage = "read_event"
        raw_event = researcher.read_event(5)
        with (root / "raw-event.json").open("xb") as output:
            output.write(raw_event.encode("utf-8"))
        event = _bounded_json(raw_event, label="B event")
        text_sha = hashlib.sha256(selected["text"].encode()).hexdigest()
        if event != {"schema": EVENT_SCHEMA, "cycle_id": cycle_id,
                      "sandbox_id": sandbox_id, "order_sha256": digest(order),
                      "task_id": decision["task_id"],
                      "tool_name": "hash_public_text",
                      "input_sha256": text_sha, "output_sha256": text_sha,
                      "status": "ok"}:
            raise ValueError("B event differs from exact public hash task")
        stage = "post_execution_integrity"
        if (researcher.sandbox_id != sandbox_id or _sources() != source_hashes
                or load_json(root / "claim.json") != claim
                or load_json(root / "frozen-input-hashes.json") != frozen_hashes
                or load_json(root / "decision.json") != decision
                or load_json(root / "broker-order.json") != order
                or (root / "raw-ack.json").read_text(encoding="utf-8") != raw_ack
                or (root / "raw-event.json").read_text(encoding="utf-8") != raw_event
                or file_hash(claim_root / f"{cycle_id}.json") != file_hash(root / "claim.json")
                or {name: file_hash(Path(glm_root) / name)
                    for name in frozen_hashes if name != "registry_claim"}
                != {name: value for name, value in frozen_hashes.items()
                    if name != "registry_claim"}
                or file_hash(Path(glm_claim_root) / f"{cycle_id}.json") !=
                   frozen_hashes["registry_claim"]):
            raise ValueError("source, fake B ID, claim or frozen A evidence changed")
    except Exception as exc:
        error_type = type(exc).__name__
        fresh_json(root / "failure.json", {
            "schema": "market_offline_a_to_b_failure_v1", "cycle_id": cycle_id,
            "stage": stage, "error_type": error_type,
            "fake_b_id": sandbox_id, "automatic_retry": False})
    finally:
        try:
            id_unchanged = researcher.sandbox_id == sandbox_id
            kill_acknowledged = researcher.kill() is True
            absent = researcher.absent(sandbox_id) is True
        except Exception as exc:
            id_unchanged = kill_acknowledged = absent = False
            if error_type is None:
                error_type = type(exc).__name__
        cleanup = {"schema": "market_offline_a_to_b_cleanup_v1",
                   "cycle_id": cycle_id, "fake_b_id": sandbox_id,
                   "id_unchanged": id_unchanged,
                   "kill_acknowledged": kill_acknowledged,
                   "fake_account_absent": absent,
                   "exact_fake_cleanup_verified": id_unchanged and kill_acknowledged and absent}
        fresh_json(root / "cleanup.json", cleanup)
    passed = error_type is None and cleanup["exact_fake_cleanup_verified"]
    result = {"schema": "market_offline_a_to_b_result_v1", "cycle_id": cycle_id,
              "passed_offline_binding": passed,
              "failure_type": error_type if error_type else (
                  None if passed else "CleanupUnverified"),
              "claim_sha256": file_hash(root / "claim.json"),
              "frozen_input_hashes_sha256": file_hash(root / "frozen-input-hashes.json"),
              "decision_sha256": file_hash(root / "decision.json")
                  if (root / "decision.json").is_file() else None,
              "broker_order_sha256": file_hash(root / "broker-order.json")
                  if (root / "broker-order.json").is_file() else None,
              "raw_ack_sha256": file_hash(root / "raw-ack.json")
                  if (root / "raw-ack.json").is_file() else None,
              "raw_event_sha256": file_hash(root / "raw-event.json")
                  if (root / "raw-event.json").is_file() else None,
              "cleanup_sha256": file_hash(root / "cleanup.json"),
              "fake_b_id": sandbox_id, "fake_b_sent_count": researcher.sent,
              "synthetic_only": True, "provider_called": False,
              "model_authorship_proven": False, "full_isolation_proven": False,
              "formal_admission": False, "automatic_retry": False}
    fresh_json(root / "result.json", result)
    return result
