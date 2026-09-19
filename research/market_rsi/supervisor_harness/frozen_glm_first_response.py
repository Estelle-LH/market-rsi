"""Offline-only first-response GLM Controller adapter, with no tools or B.

The public packet is narrowly allowlisted; a local atomic ID claim prevents
reuse.  Only the exact in-memory FakeBackend is accepted.  The first returned
text and token/provider metadata are retained before review, with no retry,
content repair, scientific choice, provider connection or budget mutation.
This module is development evidence, not a live model-authorship gate.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys

from codex_glm_provider import CHAT_TEMPLATE_SHA256, TOKENIZER_REVISION
from glm_canary import HF_MODEL, MODEL, RATES, cost
from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json
from data_scientist_harness.literature import public_url


PACKET_SCHEMA = "market_glm_first_public_packet_v1"
REQUEST_SCHEMA = "market_glm_first_no_tools_request_v1"
MAX_ITEMS = 3
MAX_TEXT_BYTES = 1200
MAX_PACKET_BYTES = 4000
MAX_OUTPUT_TOKENS = 512
SAMPLE_TIMEOUT_SECONDS = 30
PROHIBITED_TEXT = re.compile(
    r"(?i)\b(?:sealed|hidden\s+(?:test|final)|dev\s+labels?|"
    r"final\s+labels?|api[_ -]?key|secret)\b")
SYSTEM_PROMPT = (
    "You are a research Controller receiving only the attached bounded public or "
    "synthetic context. Give one first response in ordinary text. No tools are "
    "available. Do not claim that a source was read, a researcher ran, a model "
    "was trained, or a hidden evaluation was accessed. Do not include chain of thought."
)


def _sha(value: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise ValueError("lowercase SHA256 required")
    return value


def _packet(packet: dict, cycle_id: str) -> dict:
    if (not isinstance(packet, dict)
            or set(packet) != {"schema", "cycle_id", "context_items"}
            or packet.get("schema") != PACKET_SCHEMA
            or packet.get("cycle_id") != cycle_id
            or not isinstance(packet.get("context_items"), list)
            or not 1 <= len(packet["context_items"]) <= MAX_ITEMS):
        raise ValueError("exact public/synthetic packet fields required")
    for item in packet["context_items"]:
        if (not isinstance(item, dict)
                or set(item) != {"role", "source_id", "text", "text_sha256"}
                or item.get("role") not in {"synthetic_fixture", "public_metadata"}
                or not isinstance(item.get("text"), str)
                or not item["text"].strip()
                or len(item["text"].encode("utf-8")) > MAX_TEXT_BYTES
                or any(ord(c) < 32 and c not in "\n\t" for c in item["text"])
                or PROHIBITED_TEXT.search(item["text"]) is not None
                or _sha(item.get("text_sha256")) != hashlib.sha256(
                    item["text"].encode("utf-8")).hexdigest()):
            raise ValueError("bounded source-hashed public item required")
        source_id = item.get("source_id")
        if item["role"] == "synthetic_fixture":
            if (not isinstance(source_id, str)
                    or not source_id.startswith("synthetic:")
                    or len(source_id) > 100):
                raise ValueError("synthetic source ID required")
        else:
            public_url(source_id)  # URL syntax only: no fetch or DNS call.
    if len(canonical(packet).encode("utf-8")) > MAX_PACKET_BYTES:
        raise ValueError("public packet exceeds byte bound")
    return packet


def _current_sources() -> dict:
    here = Path(__file__).resolve()
    return {"first_response_adapter": file_hash(here),
            "provider_contract": file_hash(here.parents[1] / "codex_glm_provider.py"),
            "cost_contract": file_hash(here.parents[1] / "glm_canary.py"),
            "public_source_gate": file_hash(here.parents[1] /
                                            "data_scientist_harness" / "literature.py")}


class OfflineFakeBackend:
    """Exact test double. It cannot import, construct or call a provider."""

    def __init__(self, sampled: dict, *, token_ids: list[int] | None = None):
        self.sampled = sampled
        self.token_ids = [11, 12, 13] if token_ids is None else token_ids
        self.encode_calls = 0
        self.sample_calls = 0

    def encode(self, turn: dict) -> dict:
        self.encode_calls += 1
        if set(turn) != {"messages", "tools"} or turn["tools"] != []:
            raise ValueError("fake backend accepts no tool catalog")
        rendered = canonical(turn)
        return {"rendered_prompt": rendered, "token_ids": list(self.token_ids),
                "tokenizer_repo": HF_MODEL,
                "tokenizer_revision": TOKENIZER_REVISION,
                "chat_template_sha256": CHAT_TEMPLATE_SHA256}

    def sample(self, token_ids: list[int], max_output_tokens: int,
               timeout_seconds: int) -> dict:
        self.sample_calls += 1
        if (self.sample_calls != 1 or token_ids != self.token_ids
                or max_output_tokens != MAX_OUTPUT_TOKENS
                or timeout_seconds != SAMPLE_TIMEOUT_SECONDS):
            raise ValueError("fake sample contract changed or duplicated")
        return self.sampled


def _review_sample(sampled: dict, input_tokens: int) -> tuple[bool, str]:
    if not isinstance(sampled, dict) or set(sampled) != {
            "text", "output_tokens", "cached_input_tokens", "finish_reason", "provider"}:
        return False, "malformed_or_multiple_response"
    output_tokens = sampled["output_tokens"]
    provider = sampled["provider"]
    if (not isinstance(sampled["text"], str)
            or not sampled["text"]
            or len(sampled["text"].encode("utf-8")) > 16 * 1024
            or "<tool_call" in sampled["text"].lower()
            or not isinstance(output_tokens, list)
            or not 1 <= len(output_tokens) <= MAX_OUTPUT_TOKENS
            or any(type(token) is not int or token < 0 for token in output_tokens)
            or type(sampled["cached_input_tokens"]) is not int
            or not 0 <= sampled["cached_input_tokens"] <= input_tokens
            # A truncated first answer is preserved but cannot be promoted to
            # a complete decision. Extend this allowlist only for an exactly
            # evidenced provider terminal reason, never for a length cap.
            or sampled["finish_reason"] != "stop"
            or not isinstance(provider, dict)
            or set(provider) != {"reported_model", "session_id", "sampling_session_id"}
            or provider.get("reported_model") not in {MODEL, HF_MODEL}
            or not all(isinstance(provider.get(key), str) and provider[key]
                       and len(provider[key]) <= 128
                       for key in ("session_id", "sampling_session_id"))):
        return False, "invalid_first_response_or_provenance"
    return True, "first_fake_response_preserved"


def run_offline_first_response(*, root: Path, claim_root: Path, cycle_id: str,
                               packet: dict, backend: OfflineFakeBackend) -> dict:
    """Consume one unique fake response; never call a real GLM or B backend."""
    identifier(cycle_id)
    if type(backend) is not OfflineFakeBackend:
        raise RuntimeError("live GLM backend disabled in this source version")
    packet = _packet(packet, cycle_id)
    root, claim_root = Path(root), Path(claim_root)
    if (root.name != cycle_id or root.exists() or root.is_symlink()
            or not claim_root.is_dir() or claim_root.is_symlink()
            or claim_root.resolve() == root.resolve()):
        raise ValueError("fresh exact output and existing safe claim registry required")
    source_hashes = _current_sources()
    claim = {"schema": "market_glm_first_claim_v1", "cycle_id": cycle_id,
             "packet_sha256": digest(packet), "source_hashes": source_hashes,
             "runtime": {"python_executable": str(Path(sys.executable).resolve()),
                         "python_version": sys.version},
             "requested_model": MODEL, "tools": [], "num_samples": 1,
             "temperature": 1.0, "seed": 23,
             "max_output_tokens": MAX_OUTPUT_TOKENS,
             "sample_timeout_seconds": SAMPLE_TIMEOUT_SECONDS,
             "automatic_retry": False, "backend": "offline_fake_only",
             "provider_called": False, "formal_admission": False,
             "public_origin_independently_verified": False}
    # Atomic x-mode registry claim consumes this ID even if any later step
    # fails. A second output directory cannot silently resample the ID.
    fresh_json(claim_root / f"{cycle_id}.json", claim)
    root.mkdir(mode=0o700)
    fresh_json(root / "claim.json", claim)
    fresh_json(root / "input.json", packet)
    stage = "request"
    try:
        request = {"schema": REQUEST_SCHEMA, "model": MODEL,
                   "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": canonical(packet)}],
                   "tools": [], "num_samples": 1, "temperature": 1.0,
                   "seed": 23, "max_output_tokens": MAX_OUTPUT_TOKENS,
                   "input_sha256": file_hash(root / "input.json")}
        fresh_json(root / "request.json", request)
        stage = "encoding"
        encoded = backend.encode({"messages": request["messages"], "tools": []})
        if (not isinstance(encoded, dict)
                or set(encoded) != {"rendered_prompt", "token_ids", "tokenizer_repo",
                                   "tokenizer_revision", "chat_template_sha256"}
                or not isinstance(encoded["rendered_prompt"], str)
                or encoded["rendered_prompt"] != canonical({
                    "messages": request["messages"], "tools": []})
                or encoded["tokenizer_repo"] != HF_MODEL
                or encoded["tokenizer_revision"] != TOKENIZER_REVISION
                or encoded["chat_template_sha256"] != CHAT_TEMPLATE_SHA256
                or not isinstance(encoded["token_ids"], list)
                or not 1 <= len(encoded["token_ids"]) <= 8192
                or any(type(token) is not int or token < 0
                       for token in encoded["token_ids"])):
            raise ValueError("fake encoding/provenance mismatch")
        fresh_json(root / "encoded.json", encoded)
        input_tokens = len(encoded["token_ids"])
        upper = cost(input_tokens, MAX_OUTPUT_TOKENS)
        fresh_json(root / "cost-preview.json", {
            "schema": "market_glm_first_cost_preview_v1",
            "input_tokens_fake": input_tokens,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "rates": RATES, "frozen_rate_upper_usd_fake_not_invoice": str(upper),
            "actual_provider_cost_usd": "0", "provider_called": False})
        stage = "first_fake_sample"
        sampled = backend.sample(encoded["token_ids"], MAX_OUTPUT_TOKENS,
                                 SAMPLE_TIMEOUT_SECONDS)
        # Preserve the exact first returned payload before validating it. A
        # malformed response is terminal for this claim, never a retry cue.
        fresh_json(root / "raw-response.json", sampled)
        if isinstance(sampled, dict) and isinstance(sampled.get("text"), str):
            with (root / "raw-response.txt").open("xb") as output:
                output.write(sampled["text"].encode("utf-8"))
        stage = "response_review"
        valid, reason = _review_sample(sampled, input_tokens)
        if _current_sources() != source_hashes:
            valid, reason = False, "executable_source_changed"
        if (file_hash(claim_root / f"{cycle_id}.json") !=
                file_hash(root / "claim.json")
                or load_json(root / "input.json") != packet
                or load_json(root / "request.json") != request):
            valid, reason = False, "claim_input_or_request_changed"
        metered_fake = (str(cost(input_tokens, len(sampled["output_tokens"]),
                                 sampled["cached_input_tokens"]))
                        if valid else None)
        result = {"schema": "market_glm_first_offline_result_v1",
                  "cycle_id": cycle_id, "valid_fake_response": valid,
                  "reason": reason, "claim_sha256": file_hash(root / "claim.json"),
                  "registry_claim_sha256": file_hash(claim_root / f"{cycle_id}.json"),
                  "input_sha256": file_hash(root / "input.json"),
                  "request_sha256": file_hash(root / "request.json"),
                  "encoded_sha256": file_hash(root / "encoded.json"),
                  "raw_response_sha256": file_hash(root / "raw-response.json"),
                  "raw_text_sha256": (file_hash(root / "raw-response.txt")
                                      if (root / "raw-response.txt").is_file() else None),
                  "requested_model": MODEL,
                  "fake_backend_reported_model": (sampled.get("provider", {}).get(
                      "reported_model") if isinstance(sampled, dict)
                      and isinstance(sampled.get("provider"), dict) else None),
                  "fake_usage_cost_usd_not_invoice": metered_fake,
                  "actual_provider_cost_usd": "0", "provider_called": False,
                  "model_identity_proven": False,
                  "model_authorship_proven": False,
                  "scientific_decision_validated": False,
                  "public_origin_independently_verified": False,
                  "formal_admission": False, "automatic_retry": False}
        fresh_json(root / "result.json", result)
        return result
    except Exception as exc:
        fresh_json(root / "failure.json", {
            "schema": "market_glm_first_offline_failure_v1", "cycle_id": cycle_id,
            "stage": stage, "error_type": type(exc).__name__,
            "sample_calls": backend.sample_calls,
            "automatic_retry": False, "provider_called": False,
            "formal_admission": False})
        raise
