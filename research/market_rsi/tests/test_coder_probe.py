import json
import unittest

from coder_probe import command, inspect_events


class CoderProbeTests(unittest.TestCase):
    def test_no_repo_config_tools_or_new_api_auth(self):
        args = command("/private/tmp/example", "schema.json", "answer.json")
        self.assertIn("--ignore-user-config", args)
        self.assertIn("--ephemeral", args)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", args)
        self.assertNotIn("tools.view_image=false", args)
        self.assertIn("view_image", args)
        for value in ('approval_policy="never"', 'web_search="disabled"',
                      'permissions.market_probe.filesystem={":minimal"="read", ":workspace_roots"="read", "/Users/estelle"="deny"}',
                      "agents.enabled=false", "features.skip_host_skill_discovery=true"):
            self.assertIn(value, args)

    def test_tool_event_rejected(self):
        lines = "\n".join(json.dumps(e) for e in [
            {"type": "item.completed", "item": {"type": "command_execution"}},
            {"type": "turn.completed", "usage": {"input_tokens": 4, "output_tokens": 3}}])
        self.assertEqual(inspect_events(lines)["unexpected_item_types"], ["command_execution"])

    def test_plain_output_and_terminal_usage(self):
        lines = "\n".join(json.dumps(e) for e in [
            {"type": "item.completed", "item": {"type": "agent_message"}},
            {"type": "turn.completed", "usage": {"input_tokens": 4, "output_tokens": 3}}])
        report = inspect_events(lines)
        self.assertTrue(report["completed_once"])
        self.assertEqual(report["unexpected_item_types"], [])
        self.assertEqual(report["usage"]["input_tokens"], 4)

    def test_specific_startup_warning_not_a_tool_call(self):
        lines = json.dumps({"type": "item.completed", "item": {"type": "error",
            "message": "Under-development features enabled: skip_host_skill_discovery. This is a warning."}})
        report = inspect_events(lines)
        self.assertEqual(len(report["startup_warnings"]), 1)
        self.assertEqual(report["unexpected_item_types"], [])

    def test_other_item_error_is_not_ignored(self):
        lines = json.dumps({"type": "item.completed", "item": {"type": "error",
            "message": "Could not enforce file access restrictions"}})
        self.assertEqual(inspect_events(lines)["unexpected_item_types"], ["error"])


if __name__ == "__main__":
    unittest.main()
