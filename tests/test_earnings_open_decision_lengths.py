"""Open Controller generation schema matches the original1000-character receiver.

Only invented replies and temporary fixtures; no real API, financial QA or
production ledger. Schema hints never replace original receiver validation.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "research" / "market_rsi"))

import earnings_controller as controller
import earnings_open_roles as roles
from market_rsi import digest
import test_earnings_capacity_controller_transport as transport_fixture
import test_earnings_open_roles as open_fixture


class OpenDecisionLengthTests(unittest.TestCase):
    def role_fixture(self):
        helper = open_fixture.OpenRoleTests(
            "test_controller_drives_multiple_tools_then_exact_final_alias")
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        return helper

    def test_actual_counted_and_physical_request_declare_both_exact_length_bounds(self):
        temporary = tempfile.TemporaryDirectory(prefix="open-decision-length-")
        self.addCleanup(temporary.cleanup)
        fixture = transport_fixture._TransportFixture(self, Path(temporary.name).resolve() / "owned")
        service = roles.OpenController(fixture.context_binding, budget=fixture.budget,
            client_factory=fixture.factory, broker=open_fixture.Broker(), max_turns=1)
        fixture.invoke(fixture.response(fixture.decision("continue")), service=service)
        self.assertEqual([endpoint for endpoint, _ in fixture.calls],
                         ["/v1/responses/input_tokens", "/v1/responses"])
        for _, request in fixture.calls:
            fields = request["text"]["format"]["schema"]["properties"]
            for key in ("hypothesis", "expected_effect"):
                self.assertEqual(fields[key], {"type": "string", "minLength": 1, "maxLength": 1000})
            self.assertIn("1000", request["instructions"])
            self.assertIn("characters", request["instructions"])
            self.assertEqual(request["model"], fixture.rates["api_model"])
            self.assertEqual(request["reasoning"], {"effort": fixture.rates["effort"]})
        self.assertEqual(fixture.calls[0][1]["text"], fixture.calls[1][1]["text"])
        self.assertEqual(fixture.budget.summary()["unresolved_reserved_usd"], 0)

    def test_original_receiver_accepts1000_and_rejects1001_for_both_fields_without_rewriting(self):
        helper = self.role_fixture()
        for field in ("hypothesis", "expected_effect"):
            for value in ("x", "x" * 1000, "研" * 1000):
                with self.subTest(field=field, valid_length=len(value)):
                    chosen = helper.choice("continue")
                    chosen[field] = value
                    before = deepcopy(chosen)
                    self.assertEqual(controller.parse_capacity_decision(helper.message(chosen), helper.prompt), chosen)
                    self.assertEqual(chosen, before)
            for value in ("", "x" * 1001, "x" * 1023):
                with self.subTest(field=field, invalid_length=len(value)):
                    chosen = helper.choice("continue")
                    chosen[field] = value
                    before = deepcopy(chosen)
                    with self.assertRaises(ValueError):
                        controller.parse_capacity_decision(helper.message(chosen), helper.prompt)
                    self.assertEqual(chosen, before)

    def test_completed_overlong_reply_is_preserved_failed_and_never_truncated_or_retried(self):
        for field in ("hypothesis", "expected_effect"):
            with self.subTest(field=field):
                helper = self.role_fixture()
                chosen = helper.choice("continue")
                chosen[field] = "x" * 1023
                helper.generations = [helper.message(chosen)]
                service = helper.service(max_turns=1)
                with self.assertRaises(RuntimeError):
                    helper.invoke(service)
                self.assertEqual(len(helper.requests), 1)
                self.assertEqual(helper.failure()["status"], "FAILED_NO_RETRY")
                self.assertFalse((helper.slot / "decision.json").exists())
                raw = (helper.slot / "response.json").read_bytes()
                original = json.loads(raw)
                self.assertEqual(json.loads(original["output"][0]["content"][0]["text"]), chosen)
                self.assertEqual(raw, (helper.slot / "01-response.json").read_bytes())
                with self.assertRaises(FileExistsError):
                    helper.invoke(service)
                self.assertEqual(len(helper.requests), 1)
                self.assertEqual((helper.slot / "response.json").read_bytes(), raw)

    def test_legacy_and_Author_formats_remain_unchanged_and_source_may_exceed1000(self):
        temporary = tempfile.TemporaryDirectory(prefix="legacy-decision-length-")
        self.addCleanup(temporary.cleanup)
        fixture = transport_fixture._TransportFixture(self, Path(temporary.name).resolve() / "owned")
        legacy = controller.capacity_request(fixture.prompt, fixture.rates)
        for field in ("hypothesis", "expected_effect"):
            self.assertEqual(legacy["text"]["format"]["schema"]["properties"][field], {"type": "string"})
        helper = self.role_fixture()
        chosen = helper.choice("R")
        source = "PROGRAM={'axis':'R'}\n" + "# Synthetic source comment.\n" * 60 + "def run(payload): return 1\n"
        self.assertGreater(len(source), 1000)
        payload = {"decision_sha256": digest(chosen), "source_text": source,
                   "test_text": "CASES=[{'input':{},'expected':1}]"}
        helper.generations = [helper.message(payload)]
        service = helper.service(author=True, max_turns=1)
        from unittest.mock import patch
        with patch.object(roles, "budgeted_response", side_effect=helper.fake_paid):
            service.author(chosen, {"axis": "R"}, str(helper.slot))
        fields = helper.requests[0]["text"]["format"]["schema"]["properties"]
        self.assertEqual(set(fields), {"decision_sha256", "source_text", "test_text"})
        self.assertEqual(fields["source_text"], {"type": "string"})
        self.assertEqual(fields["test_text"], {"type": "string"})
        self.assertEqual(helper.failure()["status"], "COMPLETED_CANDIDATE")


if __name__ == "__main__":
    unittest.main()
