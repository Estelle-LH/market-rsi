"""One-sample Controller adapter for the P0 Gate 1 source decision.

The adapter receives only the frozen aggregate Gate 1 packet and exposes two
mutually exclusive terminal, non-executing submission tools. It preserves the
first response before review and either compiles that submission into one
plan-only trusted task or archives a novel proposal without execution. Budget,
publication and outer-process supervision belong to a separate parent; this module never
retries, fetches a source, or admits prediction data.
"""
from __future__ import annotations

import base64
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

from codex_glm_provider import (
    CHAT_TEMPLATE_SHA256, TOKENIZER_REVISION, TinkerGLMBackend,
)
from codex_glm_responses_adapter import MCP_NAMESPACE, parse_glm_completion
from glm_canary import HF_MODEL, MODEL, RATES, cost
from market_rsi import (
    canonical, digest, file_hash, fresh_json, identifier, load_json,
)
from supervisor_harness.build_p0_gate1_controller_packet import (
    ALLOWED_QUESTIONS, RIGHTS_POLICY, SCHEMA as PACKET_SCHEMA,
    SHORT_BOUNDED_CHOICES, SOURCE_REGISTRY, SCOPE_DECISION_OPTIONS, build,
)
from supervisor_harness.p0_gate1_research_contract import (
    DECISION_SCHEMA, short_choice_provenance, validate_and_compile,
)
from supervisor_harness import p0_data_gap_proposal as gap_proposal
from supervisor_harness import prospective_source_scope_decision as source_scope


ADAPTER_SCHEMA = "market_p0_gate1_controller_adapter_v6"
REQUEST_SCHEMA = "market_p0_gate1_controller_request_v6"
PROVIDER_RECEIPT_SCHEMA = "market_p0_gate1_controller_provider_receipt_v1"
RESULT_SCHEMA = "market_p0_gate1_controller_adapter_result_v6"
# The complete nested D0 response is materially smaller than the old maximum.
# Exact encoding is still measured before claim/reservation/send; this cap keeps
# the single-sample hard upper below the separate $0.05 ceiling.
MAX_OUTPUT_TOKENS = 1600
SAMPLE_TIMEOUT_SECONDS = 90
MAX_COST_UPPER_USD = Decimal("0.05")
FROZEN_PACKET_CANONICAL_SHA256 = (
    "39114563de6f34b100431d02edb0677184a40f83ce9c0d3eda8afe76f963620b")
OFFLINE_FAKE_TOKEN_IDS = (101, 102, 103)
SUBMIT_TOOL = "submit_source_scope_decision"
SUBMIT_WIRE_TOOL = f"{MCP_NAMESPACE}__{SUBMIT_TOOL}"
PROPOSE_TOOL = "propose_data_gap_resolution"
PROPOSE_WIRE_TOOL = f"{MCP_NAMESPACE}__{PROPOSE_TOOL}"
SYSTEM_PROMPT = (
    "You are the research Controller. Record one complete non-executable D0 "
    "source/use/scope choice using the exact reviewed options. You own all five "
    "scientific objects: source/response, intended uses, future role/split, "
    "horizon/cutoff, and bounded investigation. You have no operational "
    "tools, files, network, credentials, benchmark rows, Dev labels, or Final "
    "labels. Use exactly one terminal submission tool as your complete answer. "
    "Supply exactly its five declared objects. Narrative-only answers, multiple "
    "submissions, placeholders, URLs, paths, commands, code, credentials, data "
    "rows and claims that an investigation already ran are invalid. Requested "
    "uses are scientific scope, not rights or authorization. Proposed request, "
    "byte and time caps are not permission. Trusted code adds only the decision "
    "ID, schema/status and fixed all-false safety literals; it never fills a "
    "scientific choice. No choice can fetch, execute, purchase, retain, admit, "
    "train, score, open Dev/Final or publish anything."
)


def _gap(packet: dict) -> dict:
    """Bind a public aggregate gap to the exact frozen Controller packet."""
    evidence = packet["known_aggregate_evidence"]
    return {
        "schema": gap_proposal.GAP_SCHEMA,
        "gap_id": "p0-prediction-data-admission",
        "evidence_sha256": digest(evidence),
        "summary": (
            "The 2023 market/fill coverage and 2025 whole-season trade/label "
            "coverage remain unverified; the old Final has only 11 dates. "
            "The Controller may propose a new bounded way to investigate."),
        "scope": "public_or_opened_train",
        "sealed_values_exposed": False,
    }


def expected_packet() -> dict:
    """Return the one exact aggregate-only packet admitted by this version."""
    gate0 = {
        "schema": "market_p0_gate0_verdict_v1",
        "metadata_inventory_passed": True,
        "2025_formal_final_admitted": False,
    }
    live = {
        "schema": "market_controller_b_live_acceptance_v1",
        "passed": True,
        "claim_boundaries": {
            "bounded_live_transport_and_accounting_proven": True,
            "formal_admission": False,
            "prediction_improvement_proven": False,
        },
    }
    return build(gate0, live)


def _typed_canonical_bytes(value: object) -> bytes:
    """Return canonical JSON bytes without Python type coercion or extensions."""
    def validate(item: object) -> None:
        item_type = type(item)
        if item is None or item_type in {str, bool, int, float}:
            return
        if item_type is list:
            for child in item:
                validate(child)
            return
        if item_type is dict:
            if any(type(key) is not str for key in item):
                raise ValueError("Controller packet contains a non-string JSON key")
            for child in item.values():
                validate(child)
            return
        raise ValueError("Controller packet contains a non-JSON-native type")

    validate(value)
    return canonical(value).encode("utf-8")


def _packet(value: dict) -> dict:
    if type(value) is not dict:
        raise ValueError("Gate 1 Controller packet is not the exact frozen packet")
    expected_bytes = _typed_canonical_bytes(expected_packet())
    expected_sha256 = hashlib.sha256(expected_bytes).hexdigest()
    if expected_sha256 != FROZEN_PACKET_CANONICAL_SHA256:
        raise RuntimeError("Gate 1 adapter frozen packet commitment changed")
    try:
        value_bytes = _typed_canonical_bytes(value)
    except (TypeError, ValueError):
        raise ValueError(
            "Gate 1 Controller packet is not the exact frozen packet") from None
    if (value_bytes != expected_bytes
            or hashlib.sha256(value_bytes).hexdigest()
            != FROZEN_PACKET_CANONICAL_SHA256):
        raise ValueError("Gate 1 Controller packet is not the exact frozen packet")
    return value


def _submission_parameters(packet: dict) -> dict:
    options = packet["prospective_source_scope_decision"]
    pairs = options["source_response_options"]
    split = options["split_policy"]
    cutoff = options["cutoff_contract"]
    caps = options["hard_proposed_caps"]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "scientific_source_response", "intended_uses",
            "future_role_split", "horizon_cutoff", "bounded_investigation",
        ],
        "properties": {
            "scientific_source_response": {
                "type": "object", "additionalProperties": False,
                "required": ["source_registry_entry_id", "response_class_id"],
                "properties": {
                    "source_registry_entry_id": {
                        "type": "string",
                        "enum": [item["source_registry_entry_id"] for item in pairs],
                    },
                    "response_class_id": {
                        "type": "string",
                        "enum": [item["response_class_id"] for item in pairs],
                    },
                },
            },
            "intended_uses": {
                "type": "object", "additionalProperties": False,
                "required": ["requested_use_ids"],
                "properties": {"requested_use_ids": {
                    "type": "array", "minItems": 1, "uniqueItems": True,
                    "items": {"type": "string", "enum": options["intended_use_ids"]},
                }},
            },
            "future_role_split": {
                "type": "object", "additionalProperties": False,
                "required": [
                    "requested_future_role", "split_policy_id",
                    "split_policy_sha256", "exposure_ledger_id",
                ],
                "properties": {
                    "requested_future_role": {
                        "type": "string", "enum": options["future_roles"]},
                    "split_policy_id": {"type": "string", "enum": [split["split_policy_id"]]},
                    "split_policy_sha256": {
                        "type": "string", "enum": [split["split_policy_sha256"]]},
                    "exposure_ledger_id": {"type": "string", "enum": ["not_yet_created"]},
                },
            },
            "horizon_cutoff": {
                "type": "object", "additionalProperties": False,
                "required": [
                    "claim_semantics", "prediction_horizon_us",
                    "cutoff_semantics_id", "cutoff_contract_sha256",
                    "label_window_start_relation", "label_window_end_relation",
                ],
                "properties": {
                    "claim_semantics": {"type": "string", "enum": options["claim_semantics"]},
                    "prediction_horizon_us": {
                        "type": "integer", "minimum": 0, "maximum": 31536000000000},
                    "cutoff_semantics_id": {
                        "type": "string", "enum": [cutoff["cutoff_semantics_id"]]},
                    "cutoff_contract_sha256": {
                        "type": "string", "enum": [cutoff["cutoff_contract_sha256"]]},
                    "label_window_start_relation": {
                        "type": "string",
                        "enum": ["at_or_after_cutoff", "not_applicable", "strictly_after_cutoff"],
                    },
                    "label_window_end_relation": {
                        "type": "string",
                        "enum": [
                            "at_or_before_cutoff_plus_horizon", "not_applicable",
                            "strictly_before_cutoff_plus_horizon",
                        ],
                    },
                },
            },
            "bounded_investigation": {
                "type": "object", "additionalProperties": False,
                "description": (
                    "Mode-dependent limits: bounded_metadata_canary_proposal "
                    "and bounded_response_canary_proposal require "
                    "max_documents_proposed=0; first_party_document_review_only "
                    "requires max_documents_proposed>=1, "
                    "max_provider_requests_proposed=0, and "
                    "max_raw_bytes_proposed=0; synthetic_contract_fixture_only "
                    "requires max_documents_proposed=0, "
                    "max_provider_requests_proposed=0, and "
                    "max_raw_bytes_proposed=0."
                ),
                "required": [
                    "mode", "max_documents_proposed",
                    "max_provider_requests_proposed", "max_raw_bytes_proposed",
                    "max_elapsed_seconds_proposed",
                ],
                "properties": {
                    "mode": {"type": "string", "enum": options["investigation_modes"]},
                    "max_documents_proposed": {
                        "type": "integer", "minimum": 0,
                        "maximum": caps["max_documents"],
                    },
                    "max_provider_requests_proposed": {
                        "type": "integer", "minimum": 0,
                        "maximum": caps["max_provider_requests"],
                    },
                    "max_raw_bytes_proposed": {
                        "type": "integer", "minimum": 0,
                        "maximum": caps["max_raw_bytes"],
                    },
                    "max_elapsed_seconds_proposed": {
                        "type": "integer", "minimum": 1,
                        "maximum": caps["max_elapsed_seconds"],
                    },
                },
            },
        },
    }


def _submission_tools(packet: dict) -> list[dict]:
    return [{
        "type": "function",
        "function": {
            "name": SUBMIT_WIRE_TOOL,
            "description": (
                "Submit the one complete source/use/scope D0 choice. This is "
                "terminal, scope-only and performs no operation."
            ),
            "parameters": _submission_parameters(packet),
        },
    }]


def _available_capabilities(packet: dict) -> list[dict]:
    """Return only the exact non-executable D0 options offered this turn."""
    return [dict(item, scope_only=True, executable=False)
            for item in packet["prospective_source_scope_decision"]
            ["source_response_options"]]


def _proposal_parameters(packet: dict) -> dict:
    limits = packet["hard_limits"]
    text = lambda: {"type": "string", "minLength": 1, "maxLength": 1000}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "proposal_id", "kind", "hypothesis", "candidate_source",
            "method", "fixed_sample_rule", "expected_evidence", "stop_rule",
            "max_requests", "max_bytes", "max_minutes",
            "max_provider_cost_usd",
        ],
        "properties": {
            "proposal_id": {
                "type": "string", "minLength": 1, "maxLength": 100,
                "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$",
            },
            "kind": {"type": "string", "enum": sorted(gap_proposal.PROPOSAL_KINDS)},
            "hypothesis": text(),
            "candidate_source": {"type": "string", "maxLength": 1000},
            "method": text(),
            "fixed_sample_rule": text(),
            "expected_evidence": text(),
            "stop_rule": text(),
            "max_requests": {
                "type": "integer", "minimum": 1,
                "maximum": limits["max_requests_ceiling"],
            },
            "max_bytes": {
                "type": "integer", "minimum": 1,
                "maximum": limits["max_bytes_ceiling"],
            },
            "max_minutes": {
                "type": "integer", "minimum": 1,
                "maximum": limits["max_minutes_ceiling"],
            },
            "max_provider_cost_usd": {
                "type": "string", "minLength": 1, "maxLength": 16,
            },
        },
    }


def request_turn(packet: dict) -> dict:
    """Return the exact terminal-submission turn used by preflight and execution."""
    packet = _packet(packet)
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": canonical({
                "packet": packet,
                "currently_available_source_response_options": (
                    _available_capabilities(packet)),
                "complete_D0_required": True,
                "all_external_authority_remains_false": True,
            })},
        ],
        "tools": _submission_tools(packet),
        "reasoning_effort": "low",
    }


def _sources() -> dict[str, str]:
    here = Path(__file__).resolve()
    return {
        "adapter": file_hash(here),
        "packet_builder": file_hash(
            here.with_name("build_p0_gate1_controller_packet.py")),
        "decision_contract": file_hash(
            here.with_name("p0_gate1_research_contract.py")),
        "data_gap_proposal_contract": file_hash(
            here.with_name("p0_data_gap_proposal.py")),
        "prospective_source_scope_decision": file_hash(
            here.with_name("prospective_source_scope_decision.py")),
        "provider": file_hash(here.parents[1] / "codex_glm_provider.py"),
        "completion_parser": file_hash(
            here.parents[1] / "codex_glm_responses_adapter.py"),
        "cost": file_hash(here.parents[1] / "glm_canary.py"),
    }


def _encoding(value: dict) -> int:
    if (not isinstance(value, dict)
            or set(value) != {"rendered_prompt", "token_ids", "tokenizer_repo",
                              "tokenizer_revision", "chat_template_sha256"}
            or not isinstance(value["rendered_prompt"], str)
            or not value["rendered_prompt"]
            or len(value["rendered_prompt"].encode("utf-8")) > 64 * 1024
            or value["tokenizer_repo"] != HF_MODEL
            or value["tokenizer_revision"] != TOKENIZER_REVISION
            or value["chat_template_sha256"] != CHAT_TEMPLATE_SHA256
            or not isinstance(value["token_ids"], list)
            or not 1 <= len(value["token_ids"]) <= 8192
            or any(type(token) is not int or token < 0
                   for token in value["token_ids"])):
        raise ValueError("pinned Controller encoding is incomplete or changed")
    return len(value["token_ids"])


def _provider_receipt(sampled: dict, input_tokens: int,
                      *, provider_called: bool) -> dict:
    if (not isinstance(sampled, dict) or set(sampled) != {
            "text", "output_tokens", "cached_input_tokens", "finish_reason",
            "provider"}):
        raise ValueError("malformed or multiple Controller response")
    output_tokens = sampled["output_tokens"]
    provider = sampled["provider"]
    if (not isinstance(sampled["text"], str)
            or not sampled["text"]
            or len(sampled["text"].encode("utf-8")) > 32 * 1024
            or not isinstance(output_tokens, list)
            or not 1 <= len(output_tokens) <= MAX_OUTPUT_TOKENS
            or any(type(token) is not int or token < 0 for token in output_tokens)
            or type(sampled["cached_input_tokens"]) is not int
            or not 0 <= sampled["cached_input_tokens"] <= input_tokens
            or sampled["finish_reason"] != "stop"
            or not isinstance(provider, dict)
            or set(provider) != {
                "reported_model", "session_id", "sampling_session_id"}
            or provider.get("reported_model") not in {MODEL, HF_MODEL}
            or not all(isinstance(provider.get(key), str) and provider[key]
                       and len(provider[key]) <= 128
                       for key in ("session_id", "sampling_session_id"))):
        raise ValueError("invalid Controller response or provenance")
    output_tokens = len(output_tokens)
    cached = sampled["cached_input_tokens"]
    metered = cost(input_tokens, output_tokens, cached)
    return {
        "schema": PROVIDER_RECEIPT_SCHEMA,
        "requested_model": MODEL,
        "reported_model": sampled["provider"]["reported_model"],
        "provider_session_id": sampled["provider"]["session_id"],
        "sampling_session_id": sampled["provider"]["sampling_session_id"],
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached,
        "output_token_ids_sha256": digest(sampled["output_tokens"]),
        "finish_reason": sampled["finish_reason"],
        "terminal": True,
        "rates": RATES,
        "metered_cost_usd_not_invoice": str(metered),
        "cost_basis": "returned token quantities x frozen rates; not invoice",
        "provider_called": provider_called,
        "automatic_retry": False,
        "sample_count": 1,
    }


def _decision_id(cycle_id: str) -> str:
    identifier(cycle_id)
    payload = base64.b32encode(hashlib.sha256(cycle_id.encode()).digest())
    return "dec_" + payload.decode("ascii").lower().rstrip("=")[:26]


def _scope_submission(arguments: dict, packet: dict, cycle_id: str) -> dict:
    required = set(_submission_parameters(packet)["required"])
    if set(arguments) != required:
        raise ValueError("source-scope fields differ from frozen contract")
    options = packet["prospective_source_scope_decision"]
    pair = arguments["scientific_source_response"]
    if pair not in [
            {"source_registry_entry_id": item["source_registry_entry_id"],
             "response_class_id": item["response_class_id"]}
            for item in options["source_response_options"]]:
        raise ValueError("source and response class are not one reviewed pair")
    uses = arguments["intended_uses"].get("requested_use_ids")
    if (not isinstance(uses, list) or uses != sorted(uses)
            or len(uses) != len(set(uses))):
        raise ValueError("requested uses must be sorted and duplicate-free")
    split = options["split_policy"]
    future = arguments["future_role_split"]
    if (future.get("split_policy_id") != split["split_policy_id"]
            or future.get("split_policy_sha256")
            != split["split_policy_sha256"]):
        raise ValueError("future split policy differs from reviewed bytes")
    cutoff = options["cutoff_contract"]
    horizon = arguments["horizon_cutoff"]
    if (horizon.get("cutoff_semantics_id") != cutoff["cutoff_semantics_id"]
            or horizon.get("cutoff_contract_sha256")
            != cutoff["cutoff_contract_sha256"]):
        raise ValueError("cutoff contract differs from reviewed bytes")
    caps = options["hard_proposed_caps"]
    investigation = arguments["bounded_investigation"]
    for field, cap in (
            ("max_documents_proposed", caps["max_documents"]),
            ("max_provider_requests_proposed", caps["max_provider_requests"]),
            ("max_raw_bytes_proposed", caps["max_raw_bytes"]),
            ("max_elapsed_seconds_proposed", caps["max_elapsed_seconds"])):
        value = investigation.get(field)
        if type(value) is not int or value < (1 if field == "max_elapsed_seconds_proposed" else 0) or value > cap:
            raise ValueError("proposed investigation cap is invalid")
    return source_scope.build_decision(
        decision_id=_decision_id(cycle_id),
        scientific_source_response=pair,
        intended_uses=arguments["intended_uses"],
        future_role_split={
            **future,
            "unknown_exposure_policy": "treat_as_exposed",
            "cross_role_reuse_policy": "no_role_reassignment_after_observation",
        },
        horizon_cutoff={
            **horizon,
            "availability_formula_id": "max_authenticated_inclusive_upper_bound_us_v2",
            "availability_cutoff_relation": (
                "availability_upper_bound_unix_us_lte_forecast_cutoff_unix_us"),
            "provider_receiver_clocks_separate": True,
        },
        bounded_investigation={
            **investigation,
            "max_spend_usd_micros_proposed": 0,
            "stop_on_first_rights_or_authority_unknown": True,
            "stop_before_unregistered_response_class": True,
            "preserve_failures_without_retry_expansion": True,
        },
    )


def _decision_provenance(submission: dict, decision: dict, packet: dict,
                         cycle_id: str, raw_text: str) -> dict:
    return {
        "schema": "market_rsi_source_scope_field_provenance_v1",
        "cycle_id": cycle_id,
        "decision_id": decision["decision_id"],
        "controller_authored_objects": [
            "bounded_investigation", "future_role_split", "horizon_cutoff",
            "intended_uses", "scientific_source_response",
        ],
        "trusted_protocol_fields": [
            "decision_id", "decision_status", "non_authority", "schema",
            "bounded_investigation.max_spend_usd_micros_proposed",
            "bounded_investigation.preserve_failures_without_retry_expansion",
            "bounded_investigation.stop_before_unregistered_response_class",
            "bounded_investigation.stop_on_first_rights_or_authority_unknown",
            "future_role_split.cross_role_reuse_policy",
            "future_role_split.unknown_exposure_policy",
            "horizon_cutoff.availability_cutoff_relation",
            "horizon_cutoff.availability_formula_id",
            "horizon_cutoff.provider_receiver_clocks_separate",
        ],
        "submission_sha256": digest(submission),
        "decision_sha256": digest(decision),
        "scope_options_sha256": digest(
            packet["prospective_source_scope_decision"]),
        "raw_controller_response_sha256": hashlib.sha256(
            raw_text.encode("utf-8")).hexdigest(),
        "all_external_authority_false": True,
    }


def _submitted_action(raw: str, packet: dict, cycle_id: str) -> tuple[str, dict, dict]:
    identifier(cycle_id)
    if (not isinstance(raw, str)
            or raw.count("<tool_call>") != 1
            or raw.count("</tool_call>") != 1):
        raise ValueError("exactly one complete terminal tool call is required")
    trailing = raw.rsplit("</tool_call>", 1)[1]
    for marker in ("<|im_end|>", "<|endoftext|>", "<|end|>"):
        trailing = trailing.replace(marker, "")
    # The pinned GLM chat template can close a completed assistant tool call by
    # emitting one empty tool-observation turn marker.  It carries no model
    # content and authorizes no operation.  Accept exactly that terminal marker;
    # narrative, a second marker/call, or any other trailing bytes still fail.
    if trailing.strip() == "<|observation|>":
        trailing = ""
    if trailing.strip():
        raise ValueError("terminal submission must be the final Controller output")
    parsed = parse_glm_completion(
        raw,
        (SUBMIT_TOOL,),
        tool_schemas={
            SUBMIT_WIRE_TOOL: _submission_parameters(packet),
        },
    )
    if parsed.get("kind") != "function_call":
        raise ValueError(
            "Controller must make exactly one terminal Gate 1 submission")
    arguments = parsed["arguments"]
    if parsed.get("name") == SUBMIT_WIRE_TOOL:
        return "source_scope_decision", _scope_submission(
            arguments, packet, cycle_id), dict(arguments)
    raise ValueError("unknown terminal Gate 1 submission tool")


def _submitted_decision(raw: str, packet: dict, cycle_id: str) -> dict:
    """Return the complete scope-only D0 decision from one exact submission."""
    kind, value, _submission = _submitted_action(raw, packet, cycle_id)
    if kind != "source_scope_decision":
        raise ValueError("Controller did not submit one source-scope decision")
    return value


class OfflineGate1ProviderFake:
    """Exact no-network fake accepted only for offline tests and canaries."""

    provider_called = False

    def __init__(self, sampled: dict, *,
                 token_ids: tuple[int, ...] = OFFLINE_FAKE_TOKEN_IDS,
                 sample_error: Exception | None = None):
        if (type(token_ids) is not tuple
                or token_ids != OFFLINE_FAKE_TOKEN_IDS
                or any(type(token) is not int for token in token_ids)):
            raise ValueError("offline Controller token IDs are frozen")
        self.sampled = sampled
        self.token_ids = OFFLINE_FAKE_TOKEN_IDS
        self.sample_error = sample_error
        self.encode_calls = 0
        self.sample_calls = 0

    def encode(self, request: dict) -> dict:
        self.encode_calls += 1
        if (self.encode_calls != 1
                or set(request) != {"messages", "tools", "reasoning_effort"}
                or request["tools"] != _submission_tools(expected_packet())
                or request["reasoning_effort"] != "low"):
            raise ValueError(
                "offline Controller accepts one low-effort terminal-tool encoding")
        return {
            "rendered_prompt": "offline-gate1:" + canonical(request),
            "token_ids": list(OFFLINE_FAKE_TOKEN_IDS),
            "tokenizer_repo": HF_MODEL,
            "tokenizer_revision": TOKENIZER_REVISION,
            "chat_template_sha256": CHAT_TEMPLATE_SHA256,
        }

    def sample(self, token_ids: list[int], max_output_tokens: int,
               timeout_seconds: int) -> dict:
        self.sample_calls += 1
        if (self.sample_calls != 1
                or type(token_ids) is not list
                or any(type(token) is not int for token in token_ids)
                or tuple(token_ids) != OFFLINE_FAKE_TOKEN_IDS
                or max_output_tokens != MAX_OUTPUT_TOKENS
                or timeout_seconds != SAMPLE_TIMEOUT_SECONDS):
            raise ValueError("offline Controller sample duplicated or changed")
        if self.sample_error is not None:
            raise self.sample_error
        return self.sampled


def _mode(backend) -> str:
    if type(backend) is OfflineGate1ProviderFake:
        return "offline_fake"
    if type(backend) is TinkerGLMBackend:
        return "live_pinned"
    raise RuntimeError("exact pinned or offline Gate 1 backend required")


def _write_failure(root: Path, stage: str, error: Exception) -> None:
    if not (root / "failure.json").exists():
        fresh_json(root / "failure.json", {
            "schema": "market_p0_gate1_controller_failure_v1",
            "stage": stage,
            "error_type": type(error).__name__,
            "error_sha256": hashlib.sha256(str(error).encode()).hexdigest(),
            "automatic_retry": False,
        })


def run(*, root: Path, claim_root: Path, cycle_id: str,
        packet: dict, backend, preencoded: dict | None = None,
        before_sample=None) -> dict:
    """Consume one permanent ID and one response; never fetch or retry."""
    identifier(cycle_id)
    packet = _packet(packet)
    mode = _mode(backend)
    root, claim_root = Path(root), Path(claim_root)
    if (root.name != cycle_id or root.exists() or root.is_symlink()
            or not claim_root.is_dir() or claim_root.is_symlink()
            or claim_root.resolve() == root.resolve()):
        raise ValueError("fresh exact Gate 1 output and claim registry required")
    source_hashes = _sources()
    claim = {
        "schema": ADAPTER_SCHEMA,
        "cycle_id": cycle_id,
        "packet_sha256": digest(packet),
        "source_hashes": source_hashes,
        "runtime": {"python_executable": str(Path(sys.executable).resolve()),
                    "python_version": sys.version},
        "requested_model": MODEL,
        "tools": [SUBMIT_TOOL],
        "scope_options_sha256": digest(
            packet["prospective_source_scope_decision"]),
        "rights_status": (
            "unknown_each_requested_use_requires_later_D2_evidence"),
        "reasoning_effort": "low",
        "num_samples": 1,
        "temperature": 1.0,
        "seed": 23,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "sample_timeout_seconds": SAMPLE_TIMEOUT_SECONDS,
        "automatic_retry": False,
        "execution_mode": mode,
        "formal_data_admitted": False,
    }
    registry = claim_root / f"{cycle_id}.json"
    fresh_json(registry, claim)
    root.mkdir(mode=0o700)
    fresh_json(root / "claim.json", claim)
    fresh_json(root / "input.json", packet)
    stage = "request"
    error = None
    provider_receipt = None
    decision = None
    task = None
    proposal_archive = None
    submission_kind = None
    submission = None
    field_provenance = None
    sample_attempted = False
    dispatch_gate_called = False
    expected_records = {"claim.json": claim, "input.json": packet}
    raw_text = None
    try:
        turn = request_turn(packet)
        request = {
            "schema": REQUEST_SCHEMA,
            "model": MODEL,
            "messages": turn["messages"],
            "tools": turn["tools"],
            "reasoning_effort": turn["reasoning_effort"],
            "num_samples": 1,
            "temperature": 1.0,
            "seed": 23,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "input_sha256": file_hash(root / "input.json"),
        }
        fresh_json(root / "request.json", request)
        expected_records["request.json"] = request
        stage = "encoding"
        encoded = (backend.encode(turn) if preencoded is None else preencoded)
        input_tokens = _encoding(encoded)
        fresh_json(root / "encoded.json", encoded)
        expected_records["encoded.json"] = encoded
        upper = cost(input_tokens, MAX_OUTPUT_TOKENS)
        if upper > MAX_COST_UPPER_USD:
            raise ValueError("Gate 1 Controller cost upper bound exceeds cap")
        preview = {
            "schema": "market_p0_gate1_controller_cost_preview_v1",
            "input_tokens": input_tokens,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "rates": RATES,
            "upper_usd_not_invoice": str(upper),
            "provider_called": False,
            "budget_mutated_by_adapter": False,
        }
        fresh_json(root / "cost-preview.json", preview)
        expected_records["cost-preview.json"] = preview
        stage = "dispatch_gate"
        if before_sample is not None:
            if not callable(before_sample):
                raise TypeError("before-sample gate must be callable")
            before_sample(dict(preview))
            dispatch_gate_called = True
        stage = "first_provider_sample"
        sample_attempted = True
        sampled = backend.sample(
            encoded["token_ids"], MAX_OUTPUT_TOKENS, SAMPLE_TIMEOUT_SECONDS)
        fresh_json(root / "raw-response.json", sampled)
        expected_records["raw-response.json"] = sampled
        if isinstance(sampled, dict) and isinstance(sampled.get("text"), str):
            raw_text = sampled["text"]
            with (root / "raw-response.txt").open("xb") as output:
                output.write(raw_text.encode("utf-8"))
        stage = "provider_receipt"
        provider_receipt = _provider_receipt(
            sampled, input_tokens, provider_called=mode == "live_pinned")
        fresh_json(root / "provider-receipt.json", provider_receipt)
        expected_records["provider-receipt.json"] = provider_receipt
        if _sources() != source_hashes:
            raise ValueError("Gate 1 source changed after first response")
        stage = "decision"
        submission_kind, decision, submission = _submitted_action(
            sampled["text"], packet, cycle_id)
        fresh_json(root / "submission.json", submission)
        expected_records["submission.json"] = submission
        fresh_json(root / "decision.json", decision)
        expected_records["decision.json"] = decision
        stage = "provenance"
        if submission_kind != "source_scope_decision":
            raise ValueError("only a source-scope decision is accepted")
        field_provenance = _decision_provenance(
            submission, decision, packet, cycle_id, raw_text)
        fresh_json(root / "decision-provenance.json", field_provenance)
        expected_records["decision-provenance.json"] = field_provenance
        stage = "final_integrity"
        if (load_json(registry) != claim
                or _sources() != source_hashes
                or any(load_json(root / name) != value
                       for name, value in expected_records.items())
                or raw_text is None
                or (root / "raw-response.txt").read_text(encoding="utf-8")
                != raw_text):
            raise ValueError("Gate 1 source, claim, or decision lineage changed")
    except Exception as exc:
        error = exc
        _write_failure(root, stage, exc)

    passed = error is None
    names = (
        "claim.json", "input.json", "request.json", "encoded.json",
        "cost-preview.json", "raw-response.json", "raw-response.txt",
        "provider-receipt.json", "submission.json", "decision.json",
        "decision-provenance.json",
        "field-provenance.json", "task.json",
        "proposal.json", "failure.json",
    )
    result = {
        "schema": RESULT_SCHEMA,
        "cycle_id": cycle_id,
        "execution_mode": mode,
        "submission_kind": submission_kind if passed else None,
        "valid_source_scope_decision": (
            passed and submission_kind == "source_scope_decision"),
        # Compatibility alias for old read-only dashboards.  It no longer
        # means an executable investigation plan and is not an admission gate.
        "valid_plan_only_decision": (
            passed and submission_kind == "source_scope_decision"),
        "valid_non_executable_proposal": False,
        "completed_live_decision_pending_review": passed and mode == "live_pinned",
        "failure_type": None if error is None else type(error).__name__,
        "artifact_sha256": {
            name: file_hash(root / name) if (root / name).is_file() else None
            for name in names
        },
        "registry_claim_sha256": file_hash(registry),
        "requested_model": MODEL,
        "reported_model": (provider_receipt or {}).get("reported_model"),
        "input_tokens": (provider_receipt or {}).get("input_tokens"),
        "output_tokens": (provider_receipt or {}).get("output_tokens"),
        "cached_input_tokens": (provider_receipt or {}).get("cached_input_tokens"),
        "metered_cost_usd_not_invoice": (provider_receipt or {}).get(
            "metered_cost_usd_not_invoice"),
        "provider_called": mode == "live_pinned" and sample_attempted,
        "dispatch_gate_called": dispatch_gate_called,
        "automatic_retry": False,
        "sample_count_max": 1,
        "tools": [SUBMIT_TOOL],
        "public_fetch_performed": False,
        "sealed_data_read": False,
        "formal_data_admitted": False,
    }
    fresh_json(root / "result.json", result)
    return result
