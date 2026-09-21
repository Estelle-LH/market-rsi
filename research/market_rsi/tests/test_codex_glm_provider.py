from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_glm_provider import ControllerSession, TinkerGLMBackend
from controller_harness_contract import (
    MAX_CUMULATIVE_OUTPUT_TOKENS,
    TERMINAL_SUBMISSION_MAX_OUTPUT,
    TERMINAL_SUBMISSION_OUTPUT_RESERVE,
    TERMINAL_SUBMISSION_TRIGGER_OUTPUT,
)
from glm_canary import MODEL
from paid_budget import PaidBudget


def tool():
    return {"type": "function", "name": "exec_command", "description": "fixture",
            "parameters": {"type": "object", "properties": {
                "cmd": {"type": "string"}}, "required": ["cmd"]}}


def submit_tool():
    return {"type": "function", "name": "mcp__controller_tools__submit_decision",
            "description": "fixture", "parameters": {"type": "object",
            "properties": {"decision": {"type": "object"}}, "required": ["decision"]}}


def first_request():
    return {"model": MODEL, "stream": True, "store": False,
            "instructions": "bounded fixture", "tools": [tool()],
            "input": [{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": "inspect"}]}]}


class FakeBackend:
    def __init__(self):
        self.responses = [
            "<think>inspect</think><tool_call>exec_command<arg_key>cmd</arg_key>"
            "<arg_value>pwd</arg_value></tool_call>",
            "<think>done</think>final decision",
        ]
        self.calls = []

    def encode(self, turn):
        self.calls.append(("encode", turn))
        return {"rendered_prompt": "fixture", "token_ids": [1, 2, 3],
                "tokenizer_repo": "fixture", "tokenizer_revision": "fixture",
                "chat_template_sha256": "a" * 64}

    def sample(self, token_ids, max_output_tokens, timeout_seconds):
        self.calls.append(("sample", token_ids, max_output_tokens, timeout_seconds))
        text = self.responses.pop(0)
        return {"text": text, "output_tokens": [4, 5], "cached_input_tokens": 1,
                "finish_reason": "stop", "provider": {"reported_model": MODEL,
                "session_id": "fixture", "sampling_session_id": "fixture"}}


class FakeTokenizer:
    def __init__(self):
        self.reasoning_effort = None

    def apply_chat_template(self, messages, *, tools, tokenize,
                            add_generation_prompt, reasoning_effort):
        self.reasoning_effort = reasoning_effort
        return (f"Reasoning Effort: {reasoning_effort.title()}\n"
                + ("<tools>fixture</tools>" if tools else ""))

    def encode(self, rendered, *, add_special_tokens):
        return [1, 2, 3]


class TinkerGLMBackendEncodingTests(unittest.TestCase):
    def test_low_reasoning_effort_is_applied_to_pinned_template(self):
        backend = object.__new__(TinkerGLMBackend)
        backend.tokenizer = FakeTokenizer()
        encoded = backend.encode({
            "messages": [{"role": "user", "content": "bounded"}],
            "tools": [{"type": "function", "function": {
                "name": "fixture", "parameters": {"type": "object"}}}],
            "reasoning_effort": "low",
        })
        self.assertEqual(backend.tokenizer.reasoning_effort, "low")
        self.assertEqual(encoded["token_ids"], [1, 2, 3])

    def test_unknown_reasoning_effort_fails_before_rendering(self):
        backend = object.__new__(TinkerGLMBackend)
        backend.tokenizer = FakeTokenizer()
        with self.assertRaisesRegex(ValueError, "low or high"):
            backend.encode({"messages": [], "tools": [],
                            "reasoning_effort": "medium"})
        self.assertIsNone(backend.tokenizer.reasoning_effort)


class ControllerSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.budget = PaidBudget.create(self.root / "budget", {
            "experiment_id": "controller-fixture", "cap_usd": "10", "target_usd": "10",
            "buckets_usd": {"setup": "10"}, "authority": "fixture only"})
        self.backend = FakeBackend()
        self.session = ControllerSession(session_id="controller-fixture", output=self.root / "session",
                                         backend=self.backend, budget=self.budget,
                                         require_terminal_submission=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_two_turn_tool_loop_has_two_exact_paid_receipts(self):
        first = self.session.handle(first_request())
        call = first[-1]["response"]["output"][0]
        self.assertEqual(call["name"], "exec_command")
        second_request = first_request()
        second_request["input"] += [
            {"type": "function_call", "call_id": call["call_id"],
             "name": call["name"], "arguments": call["arguments"]},
            {"type": "function_call_output", "call_id": call["call_id"],
             "output": "/work\n"},
        ]
        second = self.session.handle(second_request)
        self.assertEqual(second[-1]["response"]["output"][0]["content"][0]["text"],
                         "final decision")
        snapshot = self.budget.snapshot()
        self.assertEqual(len(snapshot["jobs"]), 2)
        self.assertEqual({job["state"] for job in snapshot["jobs"].values()},
                         {"metered_terminal"})
        self.assertEqual(self.session.turns, 2)
        self.assertEqual(self.session.tool_calls, 1)

    def test_wrong_model_fails_before_provider_or_budget(self):
        request = first_request()
        request["model"] = "wrong"
        with self.assertRaisesRegex(ValueError, "wrong controller model"):
            self.session.handle(request)
        self.assertFalse(self.backend.calls)
        self.assertFalse(self.budget.snapshot()["jobs"])

    def test_prose_without_submission_is_metered_terminal_failure_no_resampling(self):
        session=ControllerSession(session_id="prose-fixture",output=self.root/'prose',
            backend=self.backend,budget=self.budget)
        self.backend.responses[0]='</think>I defer. This is not an actual tool call.<|user|>'
        with self.assertRaisesRegex(ValueError,'unsubmitted narrative'):
            session.handle(first_request())
        self.assertTrue(session.failed);self.assertEqual(session.turns,1)
        self.assertEqual(len([c for c in self.backend.calls if c[0]=='sample']),1)
        jobs=self.budget.snapshot()['jobs']
        self.assertEqual(len(jobs),1)
        self.assertEqual(next(iter(jobs.values()))['state'],'metered_terminal')
        self.assertEqual(json.loads((self.root/'prose/request-failure.json').read_text())['stage'],
                         'terminal_submission_protocol')
        self.assertFalse((self.root/'prose/terminal-handshake.json').exists())
        self.assertTrue((self.root/'prose/turn-001/response.json').exists())
        with self.assertRaisesRegex(ValueError,'terminal'):
            session.handle(first_request())
        self.assertEqual(len([c for c in self.backend.calls if c[0]=='sample']),1)

    def test_required_submission_policy_is_frozen_in_claim(self):
        session=ControllerSession(session_id='required-fixture',output=self.root/'required',
            backend=self.backend,budget=self.budget)
        self.assertTrue(json.loads((self.root/'required/claim.json').read_text())['terminal_submission_required'])

    def test_local_tokenizer_failure_is_recorded_without_request_or_exception_secrets(self):
        secret = "fixture-private-value-not-to-log"
        request = first_request()
        request["instructions"] = secret
        with patch.object(self.backend, "encode", side_effect=RuntimeError(secret)):
            with self.assertRaisesRegex(RuntimeError, secret):
                self.session.handle(request)
        path = self.root / "session/request-failure.json"
        original = path.read_bytes()
        record = json.loads(original)
        self.assertEqual(record["stage"], "local_tokenizer")
        self.assertFalse(record["provider_invoked_for_request"])
        self.assertEqual(record["completed_turns"], 0)
        self.assertTrue(record["session_terminal"])
        self.assertNotIn(secret, original.decode())
        self.assertFalse(self.budget.snapshot()["jobs"])
        self.assertTrue(self.session.failed)
        with self.assertRaisesRegex(ValueError, "terminal"):
            self.session.handle(first_request())
        self.assertEqual(path.read_bytes(), original)

    def test_input_conversion_failure_records_its_stage_before_paid_work(self):
        with patch("codex_glm_provider.responses_request_to_glm", side_effect=ValueError("fixture")):
            with self.assertRaises(ValueError):
                self.session.handle(first_request())
        record = json.loads((self.root / "session/request-failure.json").read_text())
        self.assertEqual(record["stage"], "input_conversion")
        self.assertFalse(record["provider_invoked_for_request"])
        self.assertFalse(self.backend.calls)
        self.assertFalse(self.budget.snapshot()["jobs"])

    def test_http_failure_without_parsed_request_is_terminal_and_unpaid(self):
        self.session.record_request_failure(ValueError("fixture"), stage="loopback_http_request")
        record = json.loads((self.root / "session/request-failure.json").read_text())
        self.assertIsNone(record["request_sha256"])
        self.assertEqual(record["stage"], "loopback_http_request")
        self.assertFalse(record["provider_invoked_for_request"])
        self.assertFalse(self.budget.snapshot()["jobs"])

    def test_parallel_tool_batch_counts_each_call_and_roundtrips(self):
        self.backend.responses[0] = (
            "<think>inspect two things</think>"
            "<tool_call>exec_command<arg_key>cmd</arg_key><arg_value>pwd</arg_value></tool_call>"
            "<tool_call>exec_command<arg_key>cmd</arg_key><arg_value>ls</arg_value></tool_call>"
        )
        first = self.session.handle(first_request())
        calls = first[-1]["response"]["output"]
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.session.tool_calls, 2)
        second_request = first_request()
        for call in calls:
            second_request["input"].append({
                "type": "function_call", "call_id": call["call_id"],
                "name": call["name"], "arguments": call["arguments"],
            })
        for call in calls:
            second_request["input"].append({
                "type": "function_call_output", "call_id": call["call_id"], "output": "ok",
            })
        second = self.session.handle(second_request)
        self.assertEqual(second[-1]["response"]["output"][0]["type"], "message")
        self.assertEqual(self.session.turns, 2)

    def test_divergent_history_fails_closed(self):
        self.session.handle(first_request())
        with self.assertRaisesRegex(ValueError, "history diverged"):
            self.session.handle(first_request())
        self.assertEqual(len(self.budget.snapshot()["jobs"]), 1)

    def test_same_count_but_substituted_tool_history_fails_closed(self):
        first = self.session.handle(first_request())
        call = first[-1]["response"]["output"][0]
        request = first_request()
        request["input"] += [
            {"type": "function_call", "call_id": call["call_id"],
             "name": "write_stdin", "arguments": call["arguments"]},
            {"type": "function_call_output", "call_id": call["call_id"], "output": "ok"},
        ]
        with self.assertRaisesRegex(ValueError, "history diverged"):
            self.session.handle(request)

    def test_successful_submission_gets_local_terminal_handshake_without_paid_turn(self):
        self.backend.responses[0] = (
            "<tool_call>mcp__controller_tools__submit_decision"
            "<arg_key>decision</arg_key><arg_value>{\"action\":\"select\"}</arg_value>"
            "</tool_call>"
        )
        request = first_request()
        request["tools"] = [submit_tool()]
        first = self.session.handle(request)
        call = first[-1]["response"]["output"][0]
        self.assertEqual(call["name"], "submit_decision")
        request["input"] += [
            {"type": "function_call", "call_id": call["call_id"],
             "name": call["name"], "namespace": call["namespace"],
             "arguments": call["arguments"]},
            {"type": "function_call_output", "call_id": call["call_id"],
             "output": [{"type": "input_text", "text": "Wall time: 0.001 seconds"},
                        {"type": "input_text", "text": "{\"bytes\":42,\"submitted\":true}"}]},
        ]
        terminal = self.session.handle(request)
        message = terminal[-1]["response"]["output"][0]["content"][0]["text"]
        self.assertEqual(message, "Controller decision submitted; session complete.")
        self.assertEqual(self.session.turns, 1)
        self.assertEqual(len(self.budget.snapshot()["jobs"]), 1)
        receipt = json.loads((self.root / "session/terminal-handshake.json").read_text())
        self.assertFalse(receipt["provider_called"])

    def test_custom_objective_submit_tool_uses_same_unpaid_handshake(self):
        custom = ControllerSession(
            session_id="objective-fixture",
            output=self.root / "objective-session",
            backend=self.backend,
            budget=self.budget,
            submit_tool="submit_objective_decision",
            allowed_tools=("submit_objective_decision",),
        )
        self.backend.responses[0] = (
            "<tool_call>mcp__controller_tools__submit_objective_decision"
            "<arg_key>decision</arg_key><arg_value>{\"action\":\"select\"}</arg_value>"
            "</tool_call>"
        )
        request = first_request()
        request["tools"] = [{"type": "function",
            "name": "mcp__controller_tools__submit_objective_decision",
            "description": "fixture", "parameters": {"type": "object",
            "properties": {"decision": {"type": "object"}},
            "required": ["decision"]}}]
        first = custom.handle(request)
        call = first[-1]["response"]["output"][0]
        request["input"] += [
            {"type": "function_call", "call_id": call["call_id"],
             "name": call["name"], "namespace": call["namespace"],
             "arguments": call["arguments"]},
            {"type": "function_call_output", "call_id": call["call_id"],
             "output": "{\"bytes\":42,\"submitted\":true}"},
        ]
        terminal = custom.handle(request)
        message = terminal[-1]["response"]["output"][0]["content"][0]["text"]
        self.assertEqual(message, "Controller decision submitted; session complete.")
        self.assertEqual(custom.turns, 1)

    def test_terminal_output_phase_exposes_only_submission_and_keeps_decision_model_authored(self):
        session = ControllerSession(
            session_id="terminal-fixture",
            output=self.root / "terminal-session",
            backend=self.backend,
            budget=self.budget,
            submit_tool="submit_decision",
            allowed_tools=("exec_command", "submit_decision"),
        )
        session.tokens.output_tokens = (
            MAX_CUMULATIVE_OUTPUT_TOKENS - TERMINAL_SUBMISSION_TRIGGER_OUTPUT
        )
        self.backend.responses[0] = (
            "<tool_call>mcp__controller_tools__submit_decision"
            "<arg_key>decision</arg_key><arg_value>{\"action\":\"retain\"}</arg_value>"
            "</tool_call>"
        )
        request = first_request()
        request["tools"] = [tool(), submit_tool()]
        response = session.handle(request)
        call = response[-1]["response"]["output"][0]
        self.assertEqual(call["name"], "submit_decision")
        encoded = next(value[1] for value in self.backend.calls if value[0] == "encode")
        self.assertEqual(
            [item["function"]["name"] for item in encoded["tools"]],
            ["mcp__controller_tools__submit_decision"],
        )
        self.assertIn("terminal phase", encoded["messages"][-1]["content"])
        sampled = next(value for value in self.backend.calls if value[0] == "sample")
        self.assertLessEqual(sampled[2], TERMINAL_SUBMISSION_MAX_OUTPUT)

    def test_ordinary_turn_cannot_spend_terminal_output_reserve(self):
        remaining = TERMINAL_SUBMISSION_TRIGGER_OUTPUT + 1
        self.session.tokens.output_tokens = MAX_CUMULATIVE_OUTPUT_TOKENS - remaining
        self.session.handle(first_request())
        sampled = next(value for value in self.backend.calls if value[0] == "sample")
        self.assertEqual(sampled[2], remaining - TERMINAL_SUBMISSION_OUTPUT_RESERVE)


if __name__ == "__main__":
    unittest.main()
