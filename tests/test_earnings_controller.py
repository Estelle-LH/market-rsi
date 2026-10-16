"""Synthetic provider/ledger tests; no paid calls or live-loop claim."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import earnings_controller as c
from edgar_forecast_budget import PilotBudget
from edgar_forecast_full_budget import activate, FullBudget
from earnings_night_budget import history_snapshot

MODEL = "gpt-6.1-sol"


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        ledger = self.root / "synthetic.sqlite3"
        old = PilotBudget(ledger)
        old.reserve("prior", MODEL, 10000)
        old.settle("prior", 1000)
        old.close()
        activate(ledger, "a" * 64, "b" * 40)
        budget = FullBudget(ledger)
        baseline = history_snapshot(budget.db)
        budget.close()
        rates = {"api_model": MODEL, "effort": "xhigh", "input": "2", "cached": ".1", "write": "2.5", "output": "10"}
        self.envelope = {"source_commit": "a" * 40, "controller_limits": {
            "max_input_tokens": 10000, "max_output_tokens": 16384, "wall_seconds": 600},
            "baseline_config": {"ledger": str(ledger), "baseline": baseline,
            "new_request_cutoff_utc": "2099-01-01T00:00:00Z", "model": MODEL,
            "runtime_config": {"models": {MODEL: rates}}}}
        observation = {"prediction": {"planned_targets": 5, "scored_targets": 0, "score_out_of_5": None},
            "execution": {"status": "FAILED_NO_RETRY", "turns": 24, "tool_calls": 23, "error_type": "ValueError"}, "cik": "fixture"}
        self.packet = {"task_id": "fixture", "parent_feedback_sha256": "b" * 64,
            "questions": "five invented questions", "feedback": {"observation": observation,
            "baseline_score_out_of_5": 1.5}, "prior_recipe": None}
        self.recipe = {"schema": "earnings_research_recipe_v1", "task_id": "fixture",
            "parent_feedback_sha256": "b" * 64, "research_instructions": "Reconcile units before forecasting."}
        self.binding = {"path": "synthetic-packet", "sha256": "c" * 64}

    def response(self, recipe=None):
        return {"status": "completed", "model": MODEL, "service_tier": "default",
            "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30,
                      "input_tokens_details": {"cached_tokens": 0}},
            "output": [{"type": "message", "content": [{"type": "output_text",
                      "text": json.dumps(self.recipe if recipe is None else recipe)}]}]}

    def invoke(self, response, name):
        calls = []
        class Provider:
            timeout = 600
            def post(self, path, payload):
                calls.append((path, copy.deepcopy(payload)))
                if path.endswith("input_tokens"):
                    return {"input_tokens": 10}
                if isinstance(response, Exception):
                    raise response
                return response
        output = self.root / name
        output.mkdir()
        value = c._claimed(self.envelope, self.packet, self.binding, c.safe_input(self.packet),
                           output, time.monotonic() + 60, Provider)
        return value, calls, output

    def test_count_reservation_exact_payload_settlement_and_no_tools(self):
        binding, calls, output = self.invoke(self.response(), "success")
        self.assertEqual([p for p, _ in calls], ["/v1/responses/input_tokens", "/v1/responses"])
        counted, sent = calls[0][1], calls[1][1]
        self.assertEqual(sent, dict(counted, max_output_tokens=16384, service_tier="default", store=False))
        self.assertEqual((sent["tools"], sent["tool_choice"], sent["reasoning"]), ([], "none", {"effort": "xhigh"}))
        receipt = json.loads((output / "01-request.json").read_text())
        intent = next(json.loads(p.read_text()) for p in output.glob("*.intent.json")
                      if json.loads(p.read_text())["endpoint"] == "/v1/responses")
        self.assertEqual(intent["complete_reservation"], receipt)
        proposal = json.loads(c.e.checked(binding))
        self.assertEqual(proposal, {"recipe": self.recipe, "input_packet": self.binding, "source_commit": "a" * 40})
        summary = json.loads((output / "budget-summary.json").read_text())
        self.assertEqual(summary["unresolved_reserved_usd"], 0)
        self.assertGreater(summary["night_charged_upper_bound_usd"], 0)

    def test_invalid_recipe_settles_usage_but_preserves_failure(self):
        with self.assertRaises(RuntimeError):
            self.invoke(self.response(dict(self.recipe, parent_feedback_sha256="c" * 64)), "bad")
        output = self.root / "bad"
        self.assertFalse((output / "proposal.json").exists())
        self.assertEqual(json.loads((output / "result.json").read_text())["status"], "FAILED_NO_RETRY")
        self.assertEqual(json.loads((output / "budget-summary.json").read_text())["unresolved_reserved_usd"], 0)
        self.assertTrue((output / "01-response.json").exists())

    def test_transport_failure_is_uncertain_and_no_retry(self):
        with self.assertRaises(RuntimeError):
            self.invoke(TimeoutError("invented transport error"), "unknown")
        output = self.root / "unknown"
        self.assertEqual(len(list(output.glob("*.intent.json"))), 2)
        self.assertGreater(json.loads((output / "budget-summary.json").read_text())["unresolved_reserved_usd"], 0)

    def test_hard_deadline_before_factory_prevents_send(self):
        from unittest.mock import Mock
        output = self.root / "late"
        output.mkdir()
        factory = Mock()
        with self.assertRaises(RuntimeError):
            c._claimed(self.envelope, self.packet, self.binding, c.safe_input(self.packet), output,
                       time.monotonic() - 1, factory)
        factory.assert_not_called()
        factory.return_value.post.assert_not_called()

    def test_whitelist_does_not_serialize_gold_or_paths(self):
        self.packet["feedback"]["gold"] = "DO_NOT_SEND"
        self.packet["feedback"]["observation"]["prediction"]["target_values"] = "DO_NOT_SEND"
        self.packet["feedback"]["observation"]["execution"]["path"] = "DO_NOT_SEND"
        self.packet["private"] = "DO_NOT_SEND"
        text = json.dumps(c.safe_input(self.packet))
        self.assertNotIn("DO_NOT_SEND", text)
        self.assertIn("1.5", text)

    def test_duplicate_refusal_tools_identity_and_bounds_rejected(self):
        for recipe in (dict(self.recipe, extra=True), dict(self.recipe, task_id="other"),
                       dict(self.recipe, research_instructions="x" * 2201)):
            with self.assertRaises(ValueError):
                c.parse_recipe(self.response(recipe), self.packet)
        for kind in ("function_call", "refusal"):
            response = self.response()
            response["output"].append({"type": kind})
            with self.assertRaises(ValueError):
                c.parse_recipe(response, self.packet)
        response = self.response()
        response["output"][0]["content"][0]["text"] = '{"schema":1,"schema":2}'
        with self.assertRaises(ValueError):
            c.parse_recipe(response, self.packet)


if __name__ == "__main__":
    unittest.main()
