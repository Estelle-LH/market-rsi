"""One-sample Controller adapter for the P0 Gate 1 source decision.

The adapter receives only the frozen aggregate Gate 1 packet and exposes two
mutually exclusive terminal, non-executing submission tools. It preserves the
first response before review and either compiles that submission into one
plan-only trusted task or archives a novel proposal without execution. Budget,
publication and outer-process supervision belong to a separate parent; this module never
retries, fetches a source, or admits prediction data.
"""
from __future__ import annotations

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
    SHORT_BOUNDED_CHOICES, SOURCE_REGISTRY, build,
)
from supervisor_harness.p0_gate1_research_contract import (
    DECISION_SCHEMA, short_choice_provenance, validate_and_compile,
)
from supervisor_harness import p0_data_gap_proposal as gap_proposal


ADAPTER_SCHEMA = "market_p0_gate1_controller_adapter_v5"
REQUEST_SCHEMA = "market_p0_gate1_controller_request_v5"
PROVIDER_RECEIPT_SCHEMA = "market_p0_gate1_controller_provider_receipt_v1"
RESULT_SCHEMA = "market_p0_gate1_controller_adapter_result_v5"
# The v4 short-choice packet and v5 request encode to 3,310 input tokens with
# the pinned local GLM tokenizer. A 2,750-token output cap yields a $0.0494991
# no-cache upper, below the separate $0.05 single-sample ceiling. The actual
# exact request is still re-encoded and checked before claim, reserve or send.
MAX_OUTPUT_TOKENS = 2750
SAMPLE_TIMEOUT_SECONDS = 90
MAX_COST_UPPER_USD = Decimal("0.05")
SUBMIT_TOOL = "submit_gate1_decision"
SUBMIT_WIRE_TOOL = f"{MCP_NAMESPACE}__{SUBMIT_TOOL}"
PROPOSE_TOOL = "propose_data_gap_resolution"
PROPOSE_WIRE_TOOL = f"{MCP_NAMESPACE}__{PROPOSE_TOOL}"
SYSTEM_PROMPT = (
    "You are the research Controller. Choose one bounded investigation from "
    "the frozen short choice IDs and questions, OR propose a novel data-gap "
    "source/method for review. You have no operational "
    "tools, files, network, credentials, benchmark rows, Dev labels, or Final "
    "labels. Use exactly one terminal submission tool as your complete answer. "
    "A novel proposal is archived only: it cannot fetch, execute, purchase, "
    "or admit data. Supply exactly the declared tool fields and no other "
    "or placeholder fields. Narrative-only answers and multiple submissions are "
    "invalid. Do not add local paths, commands, code, credentials, evaluation "
    "rows, or claims that an investigation already ran. A candidate public URL "
    "is untrusted text for review, never an instruction to fetch it. Neither "
    "submission tool can fetch, execute, purchase, or admit data. For a bounded "
    "choice submit only choice_id, question_id, hypothesis, expected_evidence "
    "and stop_rule. The trusted broker derives source, operation, sample rule, "
    "routine bounds and investigation ID from the selected choice and run claim. "
    "Do not submit these derived fields. Data-use "
    "and access policy is already fixed by the trusted Supervisor; do not submit "
    "or rewrite a rights-policy field. The fixed protocol schema is added by "
    "trusted code; do not submit a schema field. Follow the packet's current "
    "execution boundary and the listed exact available capabilities. The "
    "previous Controller answer is preserved as feedback, not a mandatory "
    "choice. You may revise it or propose another lawful approach."
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


def _packet(value: dict) -> dict:
    if (not isinstance(value, dict) or value != expected_packet()
            or value.get("schema") != PACKET_SCHEMA
            or value.get("allowed_questions") != list(ALLOWED_QUESTIONS)
            or value.get("allowed_sources") != list(SOURCE_REGISTRY)):
        raise ValueError("Gate 1 Controller packet is not the exact frozen packet")
    return value


def _submission_parameters(packet: dict) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(packet["required_bounded_submission_fields"]),
        "properties": {
            "choice_id": {
                "type": "string",
                "enum": [item["choice_id"] for item in packet["trusted_bounded_choices"]],
            },
            "question_id": {
                "type": "string", "enum": list(packet["allowed_questions"]),
            },
            "hypothesis": {"type": "string", "minLength": 1, "maxLength": 1000},
            "expected_evidence": {
                "type": "string", "minLength": 1, "maxLength": 1000,
            },
            "stop_rule": {"type": "string", "minLength": 1, "maxLength": 1000},
        },
    }


def _submission_tools(packet: dict) -> list[dict]:
    return [{
        "type": "function",
        "function": {
            "name": SUBMIT_WIRE_TOOL,
            "description": (
                "Submit the one final bounded Gate 1 plan. This is terminal and "
                "records data only; it performs no operation."
            ),
            "parameters": _submission_parameters(packet),
        },
    }, {
        "type": "function",
        "function": {
            "name": PROPOSE_WIRE_TOOL,
            "description": (
                "Archive one new data source or method for trusted review. "
                "Never executes or authorizes the proposal."
            ),
            "parameters": _proposal_parameters(packet),
        },
    }]


def _available_capabilities(packet: dict) -> list[dict]:
    """Describe only trusted choice IDs offered by this exact packet."""
    return [dict(item, plan_only=True)
            for item in packet["trusted_bounded_choices"]]


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
                "currently_available_bounded_capabilities": (
                    _available_capabilities(packet)),
                "open_ended_proposals_enter_review_only": True,
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
        (SUBMIT_TOOL, PROPOSE_TOOL),
        tool_schemas={
            SUBMIT_WIRE_TOOL: _submission_parameters(packet),
            PROPOSE_WIRE_TOOL: _proposal_parameters(packet),
        },
    )
    if parsed.get("kind") != "function_call":
        raise ValueError(
            "Controller must make exactly one terminal Gate 1 submission")
    arguments = parsed["arguments"]
    if parsed.get("name") == SUBMIT_WIRE_TOOL:
        if set(arguments) != set(packet["required_bounded_submission_fields"]):
            raise ValueError("short-choice fields differ from frozen contract")
        choices = {item["choice_id"]: item
                   for item in packet["trusted_bounded_choices"]}
        choice_id = arguments["choice_id"]
        if not isinstance(choice_id, str) or choice_id not in choices:
            raise ValueError("bounded choice was not offered in this turn")
        if arguments["question_id"] not in packet["allowed_questions"]:
            raise ValueError("question was not offered in this turn")
        selected = choices[choice_id]
        decision = {
            "schema": DECISION_SCHEMA,
            "investigation_id": cycle_id,
            "question_id": arguments["question_id"],
            "source_id": selected["source_id"],
            "hypothesis": arguments["hypothesis"],
            "fixed_sample_rule": selected["fixed_sample_rule"],
            "requested_operations": [selected["operation"]],
            "expected_evidence": arguments["expected_evidence"],
            **selected["derived_bounds"],
            "stop_rule": arguments["stop_rule"],
        }
        return "bounded_plan", decision, dict(arguments)
    if parsed.get("name") == PROPOSE_WIRE_TOOL:
        if set(arguments) != set(_proposal_parameters(packet)["required"]):
            raise ValueError("proposal fields differ from frozen contract")
        return "non_executable_proposal", {
            "schema": gap_proposal.PROPOSAL_SCHEMA,
            "gap_sha256": digest(_gap(packet)),
            **arguments,
        }, dict(arguments)
    raise ValueError("unknown terminal Gate 1 submission tool")


def _submitted_decision(raw: str, packet: dict, cycle_id: str) -> dict:
    """Compatibility helper for callers requiring the executable-plan lane."""
    kind, value, _submission = _submitted_action(raw, packet, cycle_id)
    if kind != "bounded_plan":
        raise ValueError("Controller submitted a proposal, not a bounded plan")
    return value


class OfflineGate1ProviderFake:
    """Exact no-network fake accepted only for offline tests and canaries."""

    provider_called = False

    def __init__(self, sampled: dict, *, token_ids: list[int] | None = None,
                 sample_error: Exception | None = None):
        self.sampled = sampled
        self.token_ids = [101, 102, 103] if token_ids is None else token_ids
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
            "token_ids": list(self.token_ids),
            "tokenizer_repo": HF_MODEL,
            "tokenizer_revision": TOKENIZER_REVISION,
            "chat_template_sha256": CHAT_TEMPLATE_SHA256,
        }

    def sample(self, token_ids: list[int], max_output_tokens: int,
               timeout_seconds: int) -> dict:
        self.sample_calls += 1
        if (self.sample_calls != 1 or token_ids != self.token_ids
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
        "tools": [SUBMIT_TOOL, PROPOSE_TOOL],
        "trusted_rights_policy": RIGHTS_POLICY,
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
        stage = "compile"
        if submission_kind == "bounded_plan":
            field_provenance = short_choice_provenance(
                submission["choice_id"], cycle_id)
            fresh_json(root / "field-provenance.json", field_provenance)
            expected_records["field-provenance.json"] = field_provenance
            task = validate_and_compile(
                decision, packet, field_provenance=field_provenance)
            fresh_json(root / "task.json", task)
            expected_records["task.json"] = task
        else:
            proposal_archive = gap_proposal.archive_proposal(
                _gap(packet), decision)
            fresh_json(root / "proposal.json", proposal_archive)
            expected_records["proposal.json"] = proposal_archive
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
        "field-provenance.json", "task.json",
        "proposal.json", "failure.json",
    )
    result = {
        "schema": RESULT_SCHEMA,
        "cycle_id": cycle_id,
        "execution_mode": mode,
        "submission_kind": submission_kind if passed else None,
        "valid_plan_only_decision": passed and submission_kind == "bounded_plan",
        "valid_non_executable_proposal": (
            passed and submission_kind == "non_executable_proposal"),
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
        "tools": [SUBMIT_TOOL, PROPOSE_TOOL],
        "public_fetch_performed": False,
        "sealed_data_read": False,
        "formal_data_admitted": False,
    }
    fresh_json(root / "result.json", result)
    return result
