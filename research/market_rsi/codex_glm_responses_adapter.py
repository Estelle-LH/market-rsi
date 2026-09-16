"""Pure protocol bridge between Codex Responses requests and GLM chat turns.

The network/provider process is intentionally separate.  These functions make
the wire conversion testable without Codex, Tinker, credentials, or paid work.
"""
from __future__ import annotations

import copy
import json
import re
import time
from dataclasses import dataclass
from typing import Any

from controller_harness_contract import (
    ALLOWED_TOOLS,
    MAX_CUMULATIVE_INPUT_TOKENS,
    MAX_CUMULATIVE_OUTPUT_TOKENS,
    MAX_CONTEXT_TOKENS,
    MAX_INPUT_TOKENS_PER_TURN,
    MAX_OUTPUT_TOKENS_PER_TURN,
)


MCP_NAMESPACE = "mcp__controller_tools"
MCP_RESOURCE_FUNCTIONS = frozenset({
    "list_mcp_resources", "list_mcp_resource_templates", "read_mcp_resource",
})
CONTROLLER_WIRE_FUNCTIONS = frozenset(
    f"{MCP_NAMESPACE}__{name}" for name in ALLOWED_TOOLS
)
WIRE_FUNCTIONS = frozenset({"exec_command", "write_stdin"}) | CONTROLLER_WIRE_FUNCTIONS
TOOL_CALL_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
TOOL_CALL_MARKER_RE = re.compile(r"<tool_call>|</tool_call>")
ARGUMENT_RE = re.compile(
    r"<arg_key>\s*(.*?)\s*</arg_key>\s*<arg_value>\s*(.*?)\s*</arg_value>",
    re.DOTALL,
)
SPECIAL_TOKENS = ("<|im_end|>", "<|endoftext|>", "<|end|>")


class AdapterProtocolError(ValueError):
    """The Codex request or GLM completion is outside the frozen bridge."""


def _text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        raise AdapterProtocolError("message content must be text or content list")
    parts = []
    for part in content:
        if not isinstance(part, dict) or part.get("type") not in {
            "input_text",
            "output_text",
            "text",
        }:
            raise AdapterProtocolError("only text message content is supported")
        text = part.get("text")
        if not isinstance(text, str):
            raise AdapterProtocolError("text content missing")
        parts.append(text)
    return "\n".join(parts)


def _wire_functions(allowed_tools) -> frozenset[str]:
    return frozenset({"exec_command", "write_stdin"}) | frozenset(
        f"{MCP_NAMESPACE}__{name}" for name in allowed_tools
    )


def _function_tool(tool: dict, allowed_tools=ALLOWED_TOOLS) -> dict:
    wire_functions = _wire_functions(allowed_tools)
    if (
        not isinstance(tool, dict)
        or tool.get("type") != "function"
        or tool.get("name") not in wire_functions
        or not isinstance(tool.get("parameters"), dict)
    ):
        raise AdapterProtocolError("unsupported Codex wire tool")
    function = {
        "name": tool["name"],
        "parameters": copy.deepcopy(tool["parameters"]),
    }
    if isinstance(tool.get("description"), str):
        function["description"] = tool["description"]
    return {"type": "function", "function": function}


def _tools(tools: Any, allowed_tools=ALLOWED_TOOLS) -> list[dict]:
    if not isinstance(tools, list):
        raise AdapterProtocolError("Responses tools must be a list")
    converted = []
    for tool in tools:
        if not isinstance(tool, dict):
            raise AdapterProtocolError("invalid Responses tool")
        if tool.get("type") == "function" and tool.get("name") in MCP_RESOURCE_FUNCTIONS:
            # Codex adds these generic helpers whenever MCP is configured. The
            # controller contract has no resource surface, so do not expose
            # them to GLM.
            continue
        if tool.get("type") == "namespace":
            if tool.get("name") != MCP_NAMESPACE or not isinstance(tool.get("tools"), list):
                raise AdapterProtocolError("unexpected deferred tool namespace")
            seen = set()
            for member in tool["tools"]:
                name = member.get("name") if isinstance(member, dict) else None
                if name not in allowed_tools or name in seen:
                    raise AdapterProtocolError("controller namespace changed")
                seen.add(name)
                flattened = copy.deepcopy(member)
                flattened["name"] = f"{MCP_NAMESPACE}__{name}"
                converted.append(_function_tool(flattened, allowed_tools))
            if seen != set(allowed_tools):
                raise AdapterProtocolError("controller namespace is incomplete")
            continue
        converted.append(_function_tool(tool, allowed_tools))
    return converted


def responses_request_to_glm(request: dict, allowed_tools=ALLOWED_TOOLS) -> dict:
    """Convert one bounded Codex request to an OpenAI-style GLM chat turn."""
    if not isinstance(request, dict) or request.get("stream") is not True:
        raise AdapterProtocolError("streaming Codex Responses request required")
    if request.get("store") not in {None, False}:
        raise AdapterProtocolError("provider-side conversation storage is disabled")
    instructions = request.get("instructions")
    if not isinstance(instructions, str) or not instructions.strip():
        raise AdapterProtocolError("controller instructions required")
    source_items = request.get("input")
    if not isinstance(source_items, list) or not source_items:
        raise AdapterProtocolError("nonempty Responses input required")

    messages: list[dict] = [{"role": "system", "content": instructions}]
    seen_calls: set[str] = set()
    completed_calls: set[str] = set()
    pending_assistant_calls: list[dict] = []

    def flush_assistant_calls() -> None:
        if not pending_assistant_calls:
            return
        messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": list(pending_assistant_calls),
        })
        pending_assistant_calls.clear()

    for item in source_items:
        if not isinstance(item, dict):
            raise AdapterProtocolError("invalid Responses input item")
        kind = item.get("type")
        if kind == "message":
            flush_assistant_calls()
            role = item.get("role")
            if role not in {"developer", "system", "user", "assistant"}:
                raise AdapterProtocolError("unsupported message role")
            messages.append({
                "role": "system" if role == "developer" else role,
                "content": _text_content(item.get("content")),
            })
            continue
        if kind == "function_call":
            name = item.get("name")
            namespace = item.get("namespace")
            if namespace is not None:
                if namespace != MCP_NAMESPACE or name not in allowed_tools:
                    raise AdapterProtocolError("unexpected function-call namespace")
                name = f"{namespace}__{name}"
            call_id = item.get("call_id")
            arguments = item.get("arguments")
            if (
                name not in _wire_functions(allowed_tools)
                or not isinstance(call_id, str)
                or not call_id
                or call_id in seen_calls
                or not isinstance(arguments, str)
            ):
                raise AdapterProtocolError("invalid or duplicate function call")
            try:
                parsed_arguments = json.loads(arguments)
            except json.JSONDecodeError as error:
                raise AdapterProtocolError("function arguments are not JSON") from error
            if not isinstance(parsed_arguments, dict):
                raise AdapterProtocolError("function arguments must be an object")
            seen_calls.add(call_id)
            pending_assistant_calls.append({
                "id": call_id,
                "type": "function",
                # GLM-5.3's frozen chat template iterates over an argument
                # object. Keeping the Responses JSON string here makes the
                # template fail before sampling.
                "function": {"name": name, "arguments": parsed_arguments},
            })
            continue
        if kind == "function_call_output":
            flush_assistant_calls()
            call_id = item.get("call_id")
            output = item.get("output")
            if (
                not isinstance(call_id, str)
                or call_id not in seen_calls
                or call_id in completed_calls
            ):
                raise AdapterProtocolError("orphan or duplicate function output")
            if isinstance(output, list):
                output = _text_content(output)
            if not isinstance(output, str):
                raise AdapterProtocolError("function output must be text or text content list")
            completed_calls.add(call_id)
            messages.append({"role": "tool", "tool_call_id": call_id, "content": output})
            continue
        raise AdapterProtocolError("unsupported Responses input item")

    flush_assistant_calls()
    if seen_calls != completed_calls:
        raise AdapterProtocolError("request contains a function call without its output")
    tools = _tools(request.get("tools", []), allowed_tools)
    if not tools:
        raise AdapterProtocolError("controller harness tools are missing")
    return {
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "parallel_tool_calls": False,
    }


def _coerce_arguments(arguments: dict[str, str], schema: dict | None = None) -> dict[str, Any]:
    """Decode structured fields, but preserve declared strings as template text.

    The pinned GLM template renders string arguments verbatim, even when their
    contents happen to be valid JSON. Blind json.loads changed JSON-text strings
    into objects and numeric-looking reference IDs into numbers. The request's
    actual tool schema, not a parameter-name exception, determines that boundary.
    Legacy callers without schemas retain their previous decoding behavior.
    """
    result: dict[str, Any] = {}
    properties = (schema or {}).get("properties", {})
    for key, value in arguments.items():
        if properties.get(key, {}).get("type") == "string":
            result[key] = value
            continue
        try:
            result[key] = json.loads(value)
        except json.JSONDecodeError:
            result[key] = value
    return result


def _complete_tool_call_bodies(text: str) -> list[str]:
    """Return complete calls, recovering a restarted call from an aborted prefix.

    GLM occasionally starts serializing a tool call, abandons it, and emits a
    fresh ``<tool_call>`` before closing the first one.  Tool calls cannot be
    nested, so the later opening marker is an unambiguous restart.  Keep the
    raw provider response for audit, but parse only the restarted complete
    body.  Genuine duplicate arguments inside that body remain invalid.
    """
    bodies: list[str] = []
    body_start: int | None = None
    for marker in TOOL_CALL_MARKER_RE.finditer(text):
        if marker.group(0) == "<tool_call>":
            # A second opening marker before a close supersedes the incomplete
            # prefix; nesting is not part of the frozen GLM tool-call grammar.
            body_start = marker.end()
        elif body_start is not None:
            bodies.append(text[body_start:marker.start()].strip())
            body_start = None
    return bodies


def parse_glm_completion(text: str, allowed_tools=ALLOWED_TOOLS, *, tool_schemas: dict | None = None) -> dict:
    """Parse one GLM text completion into tool calls or a final message."""
    if not isinstance(text, str):
        raise AdapterProtocolError("GLM completion must be text")
    cleaned = text
    for token in SPECIAL_TOKENS:
        cleaned = cleaned.replace(token, "")
    bodies = _complete_tool_call_bodies(cleaned)
    calls = []
    for body in bodies:
        first_argument = body.find("<arg_key>")
        name = (body if first_argument < 0 else body[:first_argument]).strip()
        # The GLM chat template exposes MCP members with their full wire name,
        # while the controller-facing instructions and tool descriptions use
        # the conceptual member name.  GLM can therefore emit either spelling.
        # Normalize only known controller members; arbitrary bare tool names
        # remain forbidden.
        if name in allowed_tools:
            name = f"{MCP_NAMESPACE}__{name}"
        if name not in _wire_functions(allowed_tools):
            raise AdapterProtocolError("GLM requested a forbidden wire tool")
        arguments: dict[str, str] = {}
        for argument in ARGUMENT_RE.finditer(body):
            key, value = argument.group(1).strip(), argument.group(2).strip()
            if not key or key in arguments:
                raise AdapterProtocolError("empty or duplicate GLM tool argument")
            arguments[key] = value
        if tool_schemas is not None and name not in tool_schemas:
            raise AdapterProtocolError("GLM requested a tool absent from this request")
        schema = tool_schemas[name] if tool_schemas is not None else None
        calls.append({"name": name, "arguments": _coerce_arguments(arguments, schema)})
    if len(calls) == 1:
        return {"kind": "function_call", **calls[0]}
    if calls:
        return {"kind": "function_calls", "calls": calls}
    final = TOOL_CALL_RE.sub("", cleaned)
    final = final.rsplit("</think>", 1)[-1].replace("<think>", "").strip()
    if not final:
        raise AdapterProtocolError("empty GLM completion")
    return {"kind": "message", "text": final}


def response_events(
    parsed: dict,
    *,
    response_id: str,
    item_id: str,
    call_id: str,
    usage: dict[str, int] | None = None,
    allowed_tools=ALLOWED_TOOLS,
) -> list[dict]:
    """Build the minimal Responses SSE event objects accepted by Codex CLI."""
    now = int(time.time())
    if parsed.get("kind") in {"function_call", "function_calls"}:
        calls = ([{"name": parsed["name"], "arguments": parsed["arguments"]}]
                 if parsed["kind"] == "function_call" else parsed.get("calls"))
        if not isinstance(calls, list) or not calls:
            raise AdapterProtocolError("empty parsed GLM function-call batch")
        output = []
        middle = []
        sequence = 1
        for index, call in enumerate(calls):
            if not isinstance(call, dict) or call.get("name") not in _wire_functions(allowed_tools) \
                    or not isinstance(call.get("arguments"), dict):
                raise AdapterProtocolError("invalid parsed GLM function call")
            suffix = "" if len(calls) == 1 else f"_{index + 1:03d}"
            current_item_id = item_id + suffix
            current_call_id = call_id + suffix
            arguments = json.dumps(call["arguments"], ensure_ascii=False,
                                   separators=(",", ":"))
            item = {"id": current_item_id, "type": "function_call",
                    "status": "completed", "call_id": current_call_id,
                    "name": call["name"], "arguments": arguments}
            if call["name"] in {
                    f"{MCP_NAMESPACE}__{name}" for name in allowed_tools}:
                item["namespace"] = MCP_NAMESPACE
                item["name"] = call["name"].removeprefix(f"{MCP_NAMESPACE}__")
            pending = dict(item, status="in_progress", arguments="")
            output.append(item)
            middle.extend([
                {"type": "response.output_item.added", "sequence_number": sequence,
                 "output_index": index, "item": pending},
                {"type": "response.function_call_arguments.delta",
                 "sequence_number": sequence + 1, "item_id": current_item_id,
                 "output_index": index, "delta": arguments},
                {"type": "response.function_call_arguments.done",
                 "sequence_number": sequence + 2, "item_id": current_item_id,
                 "output_index": index, "arguments": arguments},
                {"type": "response.output_item.done", "sequence_number": sequence + 3,
                 "output_index": index, "item": item},
            ])
            sequence += 4
    elif parsed.get("kind") == "message" and isinstance(parsed.get("text"), str):
        part = {"type": "output_text", "text": parsed["text"], "annotations": []}
        item = {"id": item_id, "type": "message", "status": "completed",
                "role": "assistant", "content": [part]}
        pending = dict(item, status="in_progress", content=[])
        output = [item]
        middle = [
            {"type": "response.output_item.added", "sequence_number": 1,
             "output_index": 0, "item": pending},
            {"type": "response.content_part.added", "sequence_number": 2,
             "item_id": item_id, "output_index": 0, "content_index": 0,
             "part": {"type": "output_text", "text": "", "annotations": []}},
            {"type": "response.output_text.delta", "sequence_number": 3,
             "item_id": item_id, "output_index": 0, "content_index": 0,
             "delta": parsed["text"]},
            {"type": "response.output_text.done", "sequence_number": 4,
             "item_id": item_id, "output_index": 0, "content_index": 0,
             "text": parsed["text"]},
            {"type": "response.content_part.done", "sequence_number": 5,
             "item_id": item_id, "output_index": 0, "content_index": 0,
             "part": part},
            {"type": "response.output_item.done", "sequence_number": 6,
             "output_index": 0, "item": item},
        ]
    else:
        raise AdapterProtocolError("invalid parsed GLM response")

    usage = usage or {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
    if (
        set(usage) != {"input_tokens", "cached_input_tokens", "output_tokens"}
        or any(type(value) is not int or value < 0 for value in usage.values())
        or usage["cached_input_tokens"] > usage["input_tokens"]
    ):
        raise AdapterProtocolError("invalid provider usage")
    response = {
        "id": response_id,
        "object": "response",
        "created_at": now,
        "completed_at": now,
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "max_output_tokens": MAX_OUTPUT_TOKENS_PER_TURN,
        "model": "zai-org/GLM-5.3:peft:262144",
        "output": output,
        "parallel_tool_calls": len(output) > 1,
        "previous_response_id": None,
        "reasoning": {"effort": None, "summary": None},
        "store": False,
        "temperature": 0.2,
        "text": {"format": {"type": "text"}},
        "tool_choice": "auto",
        "tools": [],
        "top_p": 1.0,
        "truncation": "disabled",
        "usage": {
            "input_tokens": usage["input_tokens"],
            "input_tokens_details": {"cached_tokens": usage["cached_input_tokens"]},
            "output_tokens": usage["output_tokens"],
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": usage["input_tokens"] + usage["output_tokens"],
        },
        "metadata": {},
    }
    created = dict(response, status="in_progress", completed_at=None, output=[])
    events = [{"type": "response.created", "sequence_number": 0, "response": created}]
    events.extend(middle)
    events.append({"type": "response.completed", "sequence_number": len(events),
                   "response": response})
    return events


@dataclass
class SessionTokenBudget:
    """Track actual provider tokens across every turn in one Codex session."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def remaining_output_tokens(self) -> int:
        return MAX_CUMULATIVE_OUTPUT_TOKENS - self.output_tokens

    def admit(self, turn_input_tokens: int) -> int:
        if not isinstance(turn_input_tokens, int) or turn_input_tokens <= 0:
            raise AdapterProtocolError("positive turn input token count required")
        if turn_input_tokens > MAX_INPUT_TOKENS_PER_TURN:
            raise AdapterProtocolError("turn input exceeds frozen per-turn limit")
        if self.input_tokens + turn_input_tokens > MAX_CUMULATIVE_INPUT_TOKENS:
            raise AdapterProtocolError("session cumulative input exhausted")
        remaining_output = self.remaining_output_tokens
        if remaining_output <= 0:
            raise AdapterProtocolError("session cumulative output exhausted")
        self.input_tokens += turn_input_tokens
        context_remaining = MAX_CONTEXT_TOKENS - turn_input_tokens
        if context_remaining <= 0:
            raise AdapterProtocolError("turn input leaves no output context")
        return min(MAX_OUTPUT_TOKENS_PER_TURN, remaining_output, context_remaining)

    def settle(self, turn_output_tokens: int) -> None:
        if not isinstance(turn_output_tokens, int) or turn_output_tokens < 0:
            raise AdapterProtocolError("nonnegative output token count required")
        if self.output_tokens + turn_output_tokens > MAX_CUMULATIVE_OUTPUT_TOKENS:
            raise AdapterProtocolError("provider output exceeded session allowance")
        self.output_tokens += turn_output_tokens
