"""One-session Responses provider backed by the pinned Tinker GLM-5.3 model.

This module owns provider metering and the permanent no-resample turn ledger.
Codex talks only to a loopback HTTP wrapper around ``ControllerSession``; the
model credential remains in this parent process and never enters its shell.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from codex_glm_responses_adapter import (
    AdapterProtocolError,
    SessionTokenBudget,
    parse_glm_completion,
    response_events,
    responses_request_to_glm,
)
from controller_harness_contract import (
    MAX_TOOL_CALLS,
    MAX_TURNS,
    TERMINAL_SUBMISSION_MAX_OUTPUT,
    TERMINAL_SUBMISSION_OUTPUT_RESERVE,
    TERMINAL_SUBMISSION_TOOL_RESERVE,
    TERMINAL_SUBMISSION_TRIGGER_OUTPUT,
)
from glm_canary import HF_MODEL, MODEL, RATES, cost
from market_rsi import canonical, digest, file_hash, fresh_json


TOKENIZER_REVISION = "aca966e4e02791568aa6a4ced368624b3d897f42"
CHAT_TEMPLATE_SHA256 = "3740abcea51c45830cb3ca562084ad5fb2ef53589376f73332e9886f93ade41c"
SUBMIT_TOOL = "submit_decision"


def _output_text(output) -> list[str]:
    if isinstance(output, str):
        return [output]
    if not isinstance(output, list):
        return []
    return [item.get("text", "") for item in output
            if isinstance(item, dict) and isinstance(item.get("text"), str)]


def successful_submission(request: dict, submit_tool: str = SUBMIT_TOOL) -> str | None:
    """Return the one successful submit call ID in a Codex request, if present."""
    calls = {}
    outputs = {}
    for item in request.get("input", []):
        if not isinstance(item, dict):
            continue
        if item.get("type") == "function_call":
            name = item.get("name")
            if item.get("namespace") == "mcp__controller_tools":
                name = str(name)
            calls[item.get("call_id")] = name
        elif item.get("type") == "function_call_output":
            outputs[item.get("call_id")] = item.get("output")
    successful = []
    for call_id, name in calls.items():
        if name != submit_tool or call_id not in outputs:
            continue
        for text in _output_text(outputs[call_id]):
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            if (isinstance(value, dict) and value.get("submitted") is True
                    and type(value.get("bytes")) is int and value["bytes"] > 0):
                successful.append(call_id)
                break
    if len(successful) > 1:
        raise AdapterProtocolError("multiple successful controller submissions")
    return successful[0] if successful else None


class TinkerGLMBackend:
    """Pinned tokenizer and one persistent Tinker sampling client."""

    def __init__(self, api_key: str, tokenizer_cache: Path):
        if not isinstance(api_key, str) or not api_key:
            raise ValueError("Tinker credential is required")
        self.api_key = api_key
        self.tokenizer_cache = Path(tokenizer_cache).resolve()
        self._sampler = None
        self._load_tokenizer()

    def _load_tokenizer(self) -> None:
        from transformers import AutoTokenizer

        snapshot = (
            self.tokenizer_cache
            / "models--zai-org--GLM-5.3"
            / "snapshots"
            / TOKENIZER_REVISION
        )
        if not snapshot.is_dir():
            raise ValueError("verified GLM tokenizer snapshot is unavailable")
        self.tokenizer = AutoTokenizer.from_pretrained(
            str(snapshot),
            trust_remote_code=False,
            token=False,
            local_files_only=True,
        )
        template = self.tokenizer.chat_template
        if not isinstance(template, str):
            template = canonical(template)
        if hashlib.sha256(template.encode()).hexdigest() != CHAT_TEMPLATE_SHA256:
            raise ValueError("frozen GLM chat template changed")

    def encode(self, turn: dict) -> dict:
        rendered = self.tokenizer.apply_chat_template(
            turn["messages"],
            tools=turn["tools"],
            tokenize=False,
            add_generation_prompt=True,
            reasoning_effort="high",
        )
        tools = turn.get("tools")
        if ("Reasoning Effort: High" not in rendered
                or (tools and "<tools>" not in rendered)
                or (not tools and "<tools>" in rendered)):
            raise ValueError("GLM high-effort template/tool contract was not applied")
        ids = list(map(int, self.tokenizer.encode(rendered, add_special_tokens=False)))
        return {
            "rendered_prompt": rendered,
            "token_ids": ids,
            "tokenizer_repo": HF_MODEL,
            "tokenizer_revision": TOKENIZER_REVISION,
            "chat_template_sha256": CHAT_TEMPLATE_SHA256,
        }

    def _sampling_client(self):
        if self._sampler is not None:
            return self._sampler
        import tinker
        from tinker.lib.retry_handler import RetryConfig

        client = tinker.ServiceClient(
            api_key=self.api_key,
            timeout=30,
            max_retries=0,
            user_metadata={"component": "market-rsi-codex-controller"},
        )
        capabilities = client.get_server_capabilities()
        if MODEL not in [item.model_name for item in capabilities.supported_models]:
            raise ValueError("exact pinned GLM controller is unavailable")
        sampler = client.create_sampling_client(
            base_model=MODEL,
            retry_config=RetryConfig(enable_retry_logic=False, progress_timeout=300),
        )
        if sampler.get_base_model() not in {MODEL, HF_MODEL}:
            raise ValueError("provider returned a different controller model")
        self._sampler = sampler
        return sampler

    def sample(self, token_ids: list[int], max_output_tokens: int, timeout_seconds: int) -> dict:
        from tinker import types

        sampler = self._sampling_client()
        result = sampler.sample(
            prompt=types.ModelInput.from_ints(token_ids),
            num_samples=1,
            sampling_params=types.SamplingParams(
                max_tokens=max_output_tokens,
                temperature=1.0,
                seed=23,
                stop=[self.tokenizer.eos_token_id],
            ),
        ).result(timeout=timeout_seconds)
        if len(result.sequences) != 1:
            raise ValueError("one GLM sample required; no candidate resampling")
        sequence = result.sequences[0]
        output_ids = list(map(int, sequence.tokens))
        return {
            "text": self.tokenizer.decode(output_ids, skip_special_tokens=False),
            "output_tokens": output_ids,
            "cached_input_tokens": int(result.prompt_cache_hit_tokens),
            "finish_reason": sequence.stop_reason,
            "provider": {
                "reported_model": sampler.get_base_model(),
                "session_id": sampler.holder.get_session_id(),
                "sampling_session_id": sampler._sampling_session_id,
            },
        }


class ControllerSession:
    """Serialize every paid GLM turn and return Codex-compatible SSE events."""

    def __init__(
        self,
        *,
        session_id: str,
        output: Path,
        backend: Any,
        budget: Any,
        budget_bucket: str = "setup",
        sample_timeout_seconds: int = 900,
        submit_tool: str = SUBMIT_TOOL,
        allowed_tools=None,
        require_terminal_submission: bool = True,
        protocol_error_tool: str | None = None,
        max_protocol_feedback: int = 0,
    ):
        if not session_id or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-" for ch in session_id):
            raise ValueError("stable lowercase session ID required")
        self.session_id = session_id
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.backend = backend
        self.budget = budget
        self.budget_bucket = budget_bucket
        self.sample_timeout_seconds = sample_timeout_seconds
        if (not isinstance(submit_tool, str) or not submit_tool
                or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_"
                       for ch in submit_tool)):
            raise ValueError("stable submit tool name required")
        self.submit_tool = submit_tool
        if type(require_terminal_submission) is not bool:
            raise ValueError("terminal submission policy must be explicit boolean")
        self.require_terminal_submission = require_terminal_submission
        self.allowed_tools = tuple(allowed_tools or __import__(
            "controller_harness_contract").ALLOWED_TOOLS)
        if (not self.allowed_tools or len(set(self.allowed_tools)) != len(self.allowed_tools)
                or submit_tool not in self.allowed_tools):
            raise ValueError("complete allowed tool set must contain the submit tool")
        self.tokens = SessionTokenBudget()
        if (type(max_protocol_feedback) is not int or not 0 <= max_protocol_feedback <= 2
                or (protocol_error_tool is None) != (max_protocol_feedback == 0)
                or (protocol_error_tool is not None and protocol_error_tool not in self.allowed_tools)):
            raise ValueError("explicit allowlisted protocol feedback tool and at most two feedbacks required")
        self.protocol_error_tool = protocol_error_tool
        self.max_protocol_feedback = max_protocol_feedback
        self.protocol_feedback_count = 0
        self.turns = 0
        self.tool_calls = 0
        self.tool_call_names: list[str] = []
        self.emitted_calls: list[dict] = []
        self.failed = False
        self.request_stage = "not_started"
        self.request_provider_invoked = False
        self.lock = threading.Lock()
        fresh_json(self.output / "claim.json", {
            "schema": "codex_glm_controller_session_v1",
            "session_id": session_id,
            "model": MODEL,
            "seed": 23,
            "temperature": 1.0,
            "automatic_resampling": 0,
            "submit_tool": submit_tool,
            "terminal_submission_required": require_terminal_submission,
            "protocol_error_tool": protocol_error_tool,
            "max_protocol_feedback": max_protocol_feedback,
            "terminal_submission_policy": {
                "output_reserve": TERMINAL_SUBMISSION_OUTPUT_RESERVE,
                "trigger_output": TERMINAL_SUBMISSION_TRIGGER_OUTPUT,
                "max_output": TERMINAL_SUBMISSION_MAX_OUTPUT,
                "tool_reserve": TERMINAL_SUBMISSION_TOOL_RESERVE,
                "submission_inferred_or_repaired": False,
            },
            "allowed_tools": list(self.allowed_tools),
            "rates": RATES,
            "adapter_sha256": file_hash(Path(__file__).with_name("codex_glm_responses_adapter.py")),
            "provider_sha256": file_hash(__file__),
        })

    def handle(self, request: dict) -> list[dict]:
        with self.lock:
            self.request_stage = "request_validation"
            self.request_provider_invoked = False
            try:
                return self._handle(request)
            except Exception as error:
                self.record_request_failure(error, request)
                raise

    def record_request_failure(self, error: Exception, request=None, *, stage=None):
        """Keep first failure evidence even before a paid turn exists; never log secrets.

        Exception text, source lines, request bodies, headers and locals are omitted.
        Locations and hashes distinguish adapter failures from provider failures without
        relying on Codex's generic rendering of a loopback HTTP 500.
        """
        self.failed = True
        destination = self.output / "request-failure.json"
        if destination.exists():
            return
        fresh_json(destination, {
            "schema": "codex_glm_request_failure_v1",
            "stage": stage or self.request_stage,
            "error_type": type(error).__name__,
            "error_message_sha256": hashlib.sha256(str(error).encode()).hexdigest(),
            "traceback_locations": [
                {"file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno}
                for frame in traceback.extract_tb(error.__traceback__)
            ],
            "request_sha256": digest(request) if request is not None else None,
            "completed_turns": self.turns,
            "provider_invoked_for_request": self.request_provider_invoked,
            "automatic_retry": False,
            "session_terminal": True,
        })

    def _handle(self, request: dict) -> list[dict]:
        if self.failed:
            raise AdapterProtocolError("controller session is terminal after a failed turn")
        if request.get("model") != MODEL:
            raise AdapterProtocolError("Codex requested the wrong controller model")
        history_calls = []
        for item in request.get("input", []):
            if not isinstance(item, dict) or item.get("type") != "function_call":
                continue
            name = item.get("name")
            namespace = item.get("namespace")
            if namespace is not None:
                name = f"{namespace}__{name}"
            history_calls.append({"call_id": item.get("call_id"), "name": name,
                                  "arguments": item.get("arguments")})
        if history_calls != self.emitted_calls or len(history_calls) != self.tool_calls:
            raise AdapterProtocolError("Codex tool history diverged from the permanent session")

        submitted_call_id = successful_submission(request, self.submit_tool)
        if submitted_call_id is not None:
            receipt = {
                "schema": "codex_glm_controller_terminal_handshake_v1",
                "submit_call_id": submitted_call_id,
                "request_sha256": digest(request),
                "provider_called": False,
                "paid_turn_added": False,
                "note": "Codex harness acknowledgment after the controller decision was durably stored.",
            }
            fresh_json(self.output / "terminal-handshake.json", receipt)
            return response_events(
                {"kind": "message", "text": "Controller decision submitted; session complete."},
                response_id=f"resp_{self.session_id}_terminal",
                item_id=f"item_{self.session_id}_terminal",
                call_id=f"call_{self.session_id}_terminal",
                usage={"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
                allowed_tools=self.allowed_tools,
            )

        if self.turns >= MAX_TURNS:
            raise AdapterProtocolError("controller turn allowance exhausted")

        terminal_submission_phase = (
            self.tokens.remaining_output_tokens
            <= TERMINAL_SUBMISSION_TRIGGER_OUTPUT
            or self.tool_calls >= MAX_TOOL_CALLS - TERMINAL_SUBMISSION_TOOL_RESERVE
        )
        self.request_stage = "input_conversion"
        converted = responses_request_to_glm(request, self.allowed_tools)
        if terminal_submission_phase:
            wire_submit = "mcp__controller_tools__" + self.submit_tool
            submit_tools = [
                tool for tool in converted["tools"]
                if tool["function"]["name"] == wire_submit
            ]
            if len(submit_tools) != 1:
                raise AdapterProtocolError(
                    "terminal submission tool is missing or duplicated")
            converted["tools"] = submit_tools
            converted["messages"].append({
                "role": "system",
                "content": (
                    "The frozen research allowance has entered its terminal phase. "
                    "Do not inspect, search, fit, or narrate. Call " + self.submit_tool
                    + " now with one already-supported candidate, or explicitly retain "
                    "the baseline. The runner will not infer or repair a decision."
                ),
            })
        self.request_stage = "local_tokenizer"
        encoded = self.backend.encode(converted)
        input_tokens = len(encoded["token_ids"])
        self.request_stage = "token_budget_admission"
        try:
            max_output_tokens = self.tokens.admit(input_tokens)
            if terminal_submission_phase:
                max_output_tokens = min(
                    max_output_tokens, TERMINAL_SUBMISSION_MAX_OUTPUT)
            else:
                # Ordinary research turns cannot consume the capacity reserved
                # for one final model-authored submission turn.
                max_output_tokens = min(
                    max_output_tokens,
                    self.tokens.remaining_output_tokens
                    - TERMINAL_SUBMISSION_OUTPUT_RESERVE,
                )
                if max_output_tokens <= 0:
                    raise AdapterProtocolError(
                        "terminal submission reserve reached before terminal phase")
        except AdapterProtocolError as error:
            self.failed = True
            fresh_json(self.output / "pre-dispatch-failure.json", {
                "error_type": type(error).__name__,
                "protocol_error": str(error),
                "automatic_retry": False,
                "provider_called": False,
                "cumulative_input_tokens": self.tokens.input_tokens,
                "cumulative_output_tokens": self.tokens.output_tokens,
            })
            raise
        turn_number = self.turns + 1
        self.request_stage = "turn_claim_and_budget_reservation"
        turn_id = f"{self.session_id}-turn-{turn_number:03d}"
        turn_path = self.output / f"turn-{turn_number:03d}"
        turn_path.mkdir(mode=0o700, exist_ok=False)
        upper = cost(input_tokens, max_output_tokens)
        fresh_json(turn_path / "request.json", {
            "turn_id": turn_id,
            "responses_request": request,
            "glm_messages": converted["messages"],
            "glm_tools": converted["tools"],
            "rendered_prompt": encoded["rendered_prompt"],
            "token_ids": encoded["token_ids"],
            "tokenizer_repo": encoded["tokenizer_repo"],
            "tokenizer_revision": encoded["tokenizer_revision"],
            "chat_template_sha256": encoded["chat_template_sha256"],
            "input_tokens": input_tokens,
            "max_output_tokens": max_output_tokens,
            "upper_usd": str(upper),
            "terminal_submission_phase": terminal_submission_phase,
        })
        self.budget.reserve(
            turn_id,
            self.budget_bucket,
            str(upper),
            "tinker",
            digest(encoded["token_ids"]),
        )
        self.budget.dispatch(turn_id)
        began = time.monotonic()
        try:
            self.request_stage = "provider_sampling"
            self.request_provider_invoked = True
            sampled = self.backend.sample(
                encoded["token_ids"], max_output_tokens, self.sample_timeout_seconds
            )
            self.request_stage = "provider_receipt_and_response_validation"
            output_tokens = sampled["output_tokens"]
            cached = sampled["cached_input_tokens"]
            if (
                not isinstance(output_tokens, list)
                or any(type(token) is not int for token in output_tokens)
                or not isinstance(cached, int)
                or not 0 <= cached <= input_tokens
            ):
                raise ValueError("invalid provider token receipt")
            self.tokens.settle(len(output_tokens))
            metered = cost(input_tokens, len(output_tokens), cached)
            receipt = {
                "terminal": True,
                "provider": "tinker",
                "model": MODEL,
                "prompt_tokens": input_tokens,
                "cache_hit_prompt_tokens": cached,
                "output_tokens": len(output_tokens),
                "metered_cost_usd": str(metered),
                "cost_basis": "returned token quantities x frozen rates; not invoice",
                "finish_reason": sampled["finish_reason"],
                "duration_seconds": time.monotonic() - began,
                "rates": RATES,
                "provider_session": sampled["provider"],
            }
            fresh_json(turn_path / "response.json", {
                "text": sampled["text"],
                "tokens": output_tokens,
                "receipt": receipt,
            })
            self.budget.settle_metered(turn_id, str(metered), receipt)
            try:
                parsed = parse_glm_completion(sampled["text"], self.allowed_tools,
                    tool_schemas={t["function"]["name"]: t["function"]["parameters"]
                                  for t in converted["tools"]})
            except AdapterProtocolError as error:
                if not self.protocol_error_tool or self.protocol_feedback_count >= self.max_protocol_feedback:
                    raise
                # Never execute or repair the requested action. Deliver an explicitly
                # runner-authored error receipt through a harmless workbench tool.
                # The next model turn is a new, metered response to that feedback,
                # not a hidden retry of this sample; all old callers stay terminal.
                self.protocol_feedback_count += 1
                feedback = {"schema":"controller_protocol_feedback_v1", "origin":"trusted_runner",
                    "model_authored_tool_call":False, "original_action_executed":False,
                    "original_response_sha256":file_hash(turn_path/"response.json"),
                    "turn_number":turn_number, "error_type":"AdapterProtocolError",
                    "error":str(error), "feedback_index":self.protocol_feedback_count,
                    "maximum_feedbacks":self.max_protocol_feedback,
                    "automatic_provider_retry":False, "requires_new_metered_model_turn":True,
                    "correction":"Use an exact available tool name and its declared argument keys. "
                        "Reference IDs are argument values, not tool names. No proposed action was executed. "
                        "Do not invent reading records, results or a submission. "
                        "Valid GLM shape: <tool_call>TOOL_NAME<arg_key>KEY</arg_key>"
                        "<arg_value>VALUE</arg_value></tool_call>."}
                fresh_json(turn_path/"protocol-feedback.json",feedback)
                parsed = {"kind":"function_call", "name":"mcp__controller_tools__"+self.protocol_error_tool,
                    "arguments":{"turn_number":turn_number,
                        "receipt_sha256":file_hash(turn_path/"protocol-feedback.json")}}
            if parsed["kind"] == "message" and self.require_terminal_submission:
                # The paid sample remains immutable and fully metered. Never turn
                # prose into an invented submission, resample, or label it success.
                self.turns = turn_number
                self.request_stage = "terminal_submission_protocol"
                raise AdapterProtocolError(
                    "controller returned unsubmitted narrative; finish by calling "
                    + self.submit_tool + "; no automatic retry or inferred decision")
            if parsed["kind"] in {"function_call", "function_calls"}:
                calls = ([{"name": parsed["name"]}] if parsed["kind"] == "function_call"
                         else parsed["calls"])
                if self.tool_calls + len(calls) > MAX_TOOL_CALLS:
                    raise AdapterProtocolError("controller tool-call allowance exhausted")
                self.tool_calls += len(calls)
                self.tool_call_names.extend(call["name"] for call in calls)
            self.turns = turn_number
            usage = {
                "input_tokens": input_tokens,
                "cached_input_tokens": cached,
                "output_tokens": len(output_tokens),
            }
            events = response_events(
                parsed,
                response_id=f"resp_{turn_id}",
                item_id=f"item_{turn_id}",
                call_id=f"call_{turn_id}",
                usage=usage,
                allowed_tools=self.allowed_tools,
            )
            for item in events[-1]["response"]["output"]:
                if item.get("type") != "function_call":
                    continue
                name = item["name"]
                if item.get("namespace") is not None:
                    name = f"{item['namespace']}__{name}"
                self.emitted_calls.append({"call_id": item["call_id"], "name": name,
                                           "arguments": item["arguments"]})
            fresh_json(turn_path / "assessment.json", {
                "valid": True,
                "kind": parsed["kind"],
                "runner_protocol_feedback": (turn_path/"protocol-feedback.json").is_file(),
                "cumulative_input_tokens": self.tokens.input_tokens,
                "cumulative_output_tokens": self.tokens.output_tokens,
                "cumulative_tool_calls": self.tool_calls,
                "tool_names": ([parsed["name"]] if parsed["kind"] == "function_call"
                               else [call["name"] for call in parsed.get("calls", [])]),
            })
            return events
        except Exception as error:
            self.failed = True
            failure = {
                "error_type": type(error).__name__,
                "duration_seconds": time.monotonic() - began,
                "automatic_retry": False,
                "note": "The permanent controller session is terminal; inspect provider and budget receipts.",
            }
            if isinstance(error, AdapterProtocolError):
                failure["protocol_error"] = str(error)
            fresh_json(turn_path / "failure.json", failure)
            raise
