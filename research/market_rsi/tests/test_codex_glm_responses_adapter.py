from __future__ import annotations

import copy
import json
import unittest

from codex_glm_responses_adapter import (
    AdapterProtocolError,
    MCP_NAMESPACE,
    SessionTokenBudget,
    parse_glm_completion,
    response_events,
    responses_request_to_glm,
)
from controller_harness_contract import (
    ALLOWED_TOOLS,
    MAX_CUMULATIVE_INPUT_TOKENS,
    MAX_CUMULATIVE_OUTPUT_TOKENS,
    MAX_INPUT_TOKENS_PER_TURN,
    MAX_OUTPUT_TOKENS_PER_TURN,
)


def function_tool(name="exec_command"):
    return {"type": "function", "name": name, "description": "fixture",
            "parameters": {"type": "object", "properties": {
                "cmd": {"type": "string"}}, "required": ["cmd"]}}


def first_request():
    return {"stream": True, "store": False, "instructions": "research system",
            "input": [{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": "inspect train"}]}],
            "tools": [function_tool()]}


class RequestConversionTests(unittest.TestCase):
    def test_initial_messages_and_function_tools_convert(self):
        converted = responses_request_to_glm(first_request())
        self.assertEqual(converted["messages"], [
            {"role": "system", "content": "research system"},
            {"role": "user", "content": "inspect train"},
        ])
        self.assertEqual(converted["tools"][0]["function"]["name"], "exec_command")
        self.assertFalse(converted["parallel_tool_calls"])

    def test_followup_binds_call_to_exact_tool_output(self):
        request = first_request()
        request["input"] += [
            {"type": "function_call", "call_id": "call-1", "name": "exec_command",
             "arguments": json.dumps({"cmd": "pwd"})},
            {"type": "function_call_output", "call_id": "call-1", "output": "/tmp/work\n"},
        ]
        converted = responses_request_to_glm(request)
        self.assertEqual(converted["messages"][-2]["tool_calls"][0]["id"], "call-1")
        self.assertEqual(converted["messages"][-2]["tool_calls"][0]["function"]["arguments"],
                         {"cmd": "pwd"})
        self.assertEqual(converted["messages"][-1], {
            "role": "tool", "tool_call_id": "call-1", "content": "/tmp/work\n"})

    def test_followup_accepts_mcp_content_item_output(self):
        request = first_request()
        request["input"] += [
            {"type": "function_call", "call_id": "call-1", "name": "exec_command",
             "arguments": json.dumps({"cmd": "pwd"})},
            {"type": "function_call_output", "call_id": "call-1", "output": [
                {"type": "input_text", "text": "Wall time: 0.01 seconds"},
                {"type": "input_text", "text": "{\"train_rows\":20}"},
            ]},
        ]
        converted = responses_request_to_glm(request)
        self.assertEqual(converted["messages"][-1]["content"],
                         'Wall time: 0.01 seconds\n{\"train_rows\":20}')

    def test_rejects_web_search_or_orphaned_tool_history(self):
        web = first_request()
        web["tools"].append({"type": "web_search"})
        orphan = first_request()
        orphan["input"].append({"type": "function_call_output", "call_id": "missing",
                                "output": "no"})
        for request in (web, orphan):
            with self.subTest(request=request), self.assertRaises(AdapterProtocolError):
                responses_request_to_glm(request)

    def test_expands_exact_controller_namespace_and_drops_resource_helpers(self):
        request = first_request()
        request["tools"] = [
            function_tool("list_mcp_resources"),
            {"type": "namespace", "name": MCP_NAMESPACE, "description": "controller",
             "tools": [{"type": "function", "name": name, "description": name,
                        "parameters": {"type": "object", "properties": {}}}
                       for name in ALLOWED_TOOLS]}]
        converted = responses_request_to_glm(request)
        names = {tool["function"]["name"] for tool in converted["tools"]}
        self.assertEqual(names, {
            f"{MCP_NAMESPACE}__{name}" for name in ALLOWED_TOOLS
        })


class CompletionTests(unittest.TestCase):
    def test_parses_one_qwen_function_call_and_emits_codex_events(self):
        parsed = parse_glm_completion(
            "<think>inspect first</think><tool_call>exec_command"
            "<arg_key>cmd</arg_key><arg_value>python inspect.py</arg_value>"
            "<arg_key>yield_time_ms</arg_key><arg_value>10000</arg_value></tool_call>"
        )
        self.assertEqual(parsed, {"kind": "function_call", "name": "exec_command",
                                  "arguments": {"cmd": "python inspect.py",
                                                "yield_time_ms": 10000}})
        events = response_events(parsed, response_id="resp-1", item_id="fc-1", call_id="call-1",
                                 usage={"input_tokens": 21, "cached_input_tokens": 5,
                                        "output_tokens": 7})
        done = [event for event in events if event["type"] == "response.output_item.done"]
        self.assertEqual(done[0]["item"]["name"], "exec_command")
        self.assertEqual(events[-1]["type"], "response.completed")
        self.assertEqual(events[-1]["response"]["usage"]["input_tokens_details"],
                         {"cached_tokens": 5})

    def test_parses_final_message_and_accepts_multiple_calls(self):
        self.assertEqual(parse_glm_completion("<think>x</think>final answer"),
                         {"kind": "message", "text": "final answer"})
        call = ("<tool_call>exec_command<arg_key>cmd</arg_key>"
                "<arg_value>pwd</arg_value></tool_call>")
        parsed = parse_glm_completion(call + call)
        self.assertEqual(parsed, {"kind": "function_calls", "calls": [
            {"name": "exec_command", "arguments": {"cmd": "pwd"}},
            {"name": "exec_command", "arguments": {"cmd": "pwd"}},
        ]})
        events = response_events(parsed, response_id="resp-2", item_id="fc-2",
                                 call_id="call-2")
        done = [event for event in events if event["type"] == "response.output_item.done"]
        self.assertEqual(len(done), 2)
        self.assertEqual([item["call_id"] for item in events[-1]["response"]["output"]],
                         ["call-2_001", "call-2_002"])
        self.assertTrue(events[-1]["response"]["parallel_tool_calls"])

    def test_followup_groups_parallel_calls_in_one_assistant_message(self):
        request = first_request()
        request["input"] += [
            {"type": "function_call", "call_id": "call-1", "name": "exec_command",
             "arguments": json.dumps({"cmd": "pwd"})},
            {"type": "function_call", "call_id": "call-2", "name": "write_stdin",
             "arguments": json.dumps({"session_id": 1, "chars": ""})},
            {"type": "function_call_output", "call_id": "call-1", "output": "/tmp"},
            {"type": "function_call_output", "call_id": "call-2", "output": "done"},
        ]
        request["tools"].append({"type": "function", "name": "write_stdin",
                                 "description": "fixture", "parameters": {"type": "object"}})
        converted = responses_request_to_glm(request)
        assistants = [message for message in converted["messages"]
                      if message["role"] == "assistant"]
        self.assertEqual(len(assistants), 1)
        self.assertEqual([call["id"] for call in assistants[0]["tool_calls"]],
                         ["call-1", "call-2"])

    def test_namespaced_mcp_call_roundtrips_between_glm_and_codex(self):
        parsed = parse_glm_completion(
            "<tool_call>mcp__controller_tools__inspect_train_dev</tool_call>"
        )
        events = response_events(parsed, response_id="resp-mcp", item_id="fc-mcp",
                                 call_id="call-mcp")
        call = events[-1]["response"]["output"][0]
        self.assertEqual(call["namespace"], MCP_NAMESPACE)
        self.assertEqual(call["name"], "inspect_train_dev")

        request = first_request()
        request["tools"] = [{"type": "namespace", "name": MCP_NAMESPACE,
                             "description": "controller", "tools": [
            {"type": "function", "name": name, "description": name,
             "parameters": {"type": "object", "properties": {}}}
            for name in ALLOWED_TOOLS]}]
        request["input"] += [
            {"type": "function_call", "call_id": call["call_id"],
             "namespace": call["namespace"], "name": call["name"],
             "arguments": call["arguments"]},
            {"type": "function_call_output", "call_id": call["call_id"], "output": "ok"},
        ]
        converted = responses_request_to_glm(request)
        assistant = next(message for message in converted["messages"]
                         if message["role"] == "assistant")
        self.assertEqual(assistant["tool_calls"][0]["function"]["name"],
                         "mcp__controller_tools__inspect_train_dev")

    def test_bare_controller_member_is_normalized_to_namespaced_wire_name(self):
        parsed = parse_glm_completion(
            '<tool_call>submit_decision<arg_key>decision</arg_key>'
            '<arg_value>{"action":"select"}</arg_value></tool_call>'
        )
        self.assertEqual(parsed, {
            "kind": "function_call",
            "name": "mcp__controller_tools__submit_decision",
            "arguments": {"decision": {"action": "select"}},
        })
        events = response_events(parsed, response_id="resp-submit", item_id="fc-submit",
                                 call_id="call-submit")
        call = events[-1]["response"]["output"][0]
        self.assertEqual(call["namespace"], MCP_NAMESPACE)
        self.assertEqual(call["name"], "submit_decision")

    def test_rejects_forbidden_tool_and_duplicate_argument(self):
        forbidden = "<tool_call>read_future_test</tool_call>"
        duplicate = ("<tool_call>exec_command<arg_key>cmd</arg_key><arg_value>pwd</arg_value>"
                     "<arg_key>cmd</arg_key><arg_value>ls</arg_value></tool_call>")
        for response in (forbidden, duplicate):
            with self.subTest(response=response), self.assertRaises(AdapterProtocolError):
                parse_glm_completion(response)

    def test_recovers_restarted_call_but_still_checks_complete_body(self):
        restarted = (
            "<think>draft</think><tool_call>exec_command"
            "<arg_key>cmd</arg_key><arg_value></think>"
            "<tool_call>exec_command<arg_key>cmd</arg_key>"
            "<arg_value>pwd</arg_value></tool_call>"
        )
        self.assertEqual(parse_glm_completion(restarted), {
            "kind": "function_call",
            "name": "exec_command",
            "arguments": {"cmd": "pwd"},
        })

        duplicate_in_restarted_call = (
            "<tool_call>exec_command<arg_key>cmd</arg_key><arg_value>aborted"
            "<tool_call>exec_command<arg_key>cmd</arg_key><arg_value>pwd</arg_value>"
            "<arg_key>cmd</arg_key><arg_value>ls</arg_value></tool_call>"
        )
        with self.assertRaises(AdapterProtocolError):
            parse_glm_completion(duplicate_in_restarted_call)


class TokenBudgetTests(unittest.TestCase):
    def test_allows_192k_input_64k_output_and_enforces_session_totals(self):
        budget = SessionTokenBudget()
        self.assertEqual(budget.admit(MAX_INPUT_TOKENS_PER_TURN),
                         MAX_OUTPUT_TOKENS_PER_TURN)
        budget.settle(1024)
        self.assertEqual(MAX_CUMULATIVE_INPUT_TOKENS % MAX_INPUT_TOKENS_PER_TURN, 0)
        for _ in range(MAX_CUMULATIVE_INPUT_TOKENS // MAX_INPUT_TOKENS_PER_TURN - 1):
            budget.admit(MAX_INPUT_TOKENS_PER_TURN)
        self.assertEqual(budget.input_tokens, MAX_CUMULATIVE_INPUT_TOKENS)
        budget.settle(MAX_CUMULATIVE_OUTPUT_TOKENS - 1024)
        with self.assertRaises(AdapterProtocolError):
            budget.admit(1)

    def test_rejects_single_turn_over_frozen_limit(self):
        with self.assertRaises(AdapterProtocolError):
            SessionTokenBudget().admit(MAX_INPUT_TOKENS_PER_TURN + 1)


if __name__ == "__main__":
    unittest.main()
