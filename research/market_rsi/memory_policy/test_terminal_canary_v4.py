from __future__ import annotations

import unittest

from memory_policy.terminal_canary_v4 import request


class TerminalCanaryV4Tests(unittest.TestCase):
    def test_request_is_synthetic_and_exposes_submission_without_market_data(self):
        value = request()
        names = [tool["name"] for tool in value["tools"]]
        self.assertEqual(names, [
            "mcp__controller_tools__inspect_experiment",
            "mcp__controller_tools__submit_candidate",
        ])
        body = str(value)
        self.assertIn("synthetic", body.lower())
        self.assertIn("baseline", body)
        self.assertNotIn("2026-09", body)
        self.assertNotIn("Dev", body)
        self.assertNotIn("Final", body)


if __name__ == "__main__":
    unittest.main()
