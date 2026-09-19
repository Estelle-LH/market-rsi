from __future__ import annotations

import unittest
import os
from pathlib import Path

from codex_glm_provider import TinkerGLMBackend


TOKENIZER_CACHE = Path(os.environ.get(
    "MARKET_RSI_TOKENIZER_CACHE",
    Path(__file__).parents[1] / "artifacts" / "tokenizer-cache"))


class FrozenTokenizerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not TOKENIZER_CACHE.is_dir():
            raise unittest.SkipTest("verified local GLM tokenizer cache unavailable")
        cls.backend = TinkerGLMBackend("offline-fixture-key", TOKENIZER_CACHE)

    def test_real_glm_template_renders_tools_and_followup_output(self):
        tools = [{"type": "function", "function": {"name": "exec_command",
            "description": "Run one command", "parameters": {"type": "object",
            "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]}}}]
        messages = [
            {"role": "system", "content": "bounded"},
            {"role": "user", "content": "inspect"},
            {"role": "assistant", "content": "", "tool_calls": [{
                "id": "call-1", "type": "function", "function": {
                    "name": "exec_command", "arguments": {"cmd": "pwd"}}}]},
            {"role": "tool", "tool_call_id": "call-1", "content": "/work\n"},
        ]
        encoded = self.backend.encode({"messages": messages, "tools": tools})
        rendered = encoded["rendered_prompt"]
        self.assertIn("Reasoning Effort: High", rendered)
        self.assertIn("<tool_call>exec_command<arg_key>cmd</arg_key>", rendered)
        self.assertIn("<|observation|><tool_response>/work", rendered)
        self.assertGreater(len(encoded["token_ids"]), 0)

    def test_real_glm_template_accepts_explicit_no_tools_request(self):
        encoded = self.backend.encode({
            "messages": [
                {"role": "system", "content": "bounded"},
                {"role": "user", "content": "return one JSON object"},
            ],
            "tools": [],
        })
        rendered = encoded["rendered_prompt"]
        self.assertIn("Reasoning Effort: High", rendered)
        self.assertNotIn("<tools>", rendered)
        self.assertGreater(len(encoded["token_ids"]), 0)


if __name__ == "__main__":
    unittest.main()
