"""Prospective early Author completion, never an automatic generation retry.

All packets, carriers, responses, clocks and ledgers are invented. Tests are
written independently; no actual provider or historical failed run is opened.
"""
from copy import deepcopy
import hashlib
import json
import unittest
from unittest.mock import Mock, patch

import earnings_open_context as context
import earnings_open_roles as roles
from edgar_forecast_budget import BudgetStop
from market_rsi import digest
import test_earnings_author_final_context as context_fixture
import test_earnings_open_roles as role_fixture


class AuthorEarlyFinalizationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = context_fixture.AuthorFinalContextTests(
            "test_snapshot_preserves_initial_packet_complete_public_code_and_all_other_fields")
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.normal = deepcopy(self.fixture.request)
        self.normal.update(tool_choice="auto", instructions=roles.AUTHOR)
        self.completion = dict(deepcopy(self.normal), tool_choice="none",
            instructions=roles.AUTHOR + roles.FINALIZE + roles.FINAL_AUTHOR)
        self.limits = {"max_input_tokens": 10000, "max_output_tokens": 32768}

    def helper(self):
        helper = role_fixture.OpenRoleTests("test_author_finalization_documents_actual_schema_and_preserves_exact_candidate_fields")
        helper.setUp(); self.addCleanup(helper.doCleanups)
        return helper

    def author_value(self, helper):
        return {"decision_sha256": digest(helper.choice("R")),
            "source_text": "PROGRAM={'axis':'R'}\ndef run(p): return 1\n",
            "test_text": "CASES=[{'input':{},'expected':1}]"}

    def test_fourth_early_snapshot_joins_exact_prospective_request_and_receipt(self):
        client = Mock()
        client.post.side_effect = [{"input_tokens": n} for n in (23000, 18000, 16000, 9000)]
        before = deepcopy(self.normal)
        result = context.pack(client, self.normal, self.limits, self.root, 2,
                              completion_request=self.completion)
        sent = [call.args[1] for call in client.post.call_args_list]
        self.assertEqual(sent[:3], [before, context.project(before, 2000)[0], context.project(before, 500)[0]])
        self.assertEqual(sent[3], context.author_final_view(self.completion, 100)[0])
        self.assertEqual(result, sent[3])
        self.assertEqual(result["tool_choice"], "none")
        self.assertEqual(self.normal, before)
        self.assertEqual(result["input"][0], before["input"][0])
        receipt = json.loads((self.root / "02-context-04.json").read_bytes())
        self.assertTrue(receipt["early_finalization"])
        self.assertTrue(receipt["generation_not_sent"])
        for field, value in (("original_request_sha256", before),
                             ("finalization_request_sha256", self.completion),
                             ("effective_request_sha256", result)):
            self.assertEqual(receipt[field], hashlib.sha256(context.encoded(value)).hexdigest())

    def test_prospective_request_cannot_change_packet_model_tools_format_or_other_settings(self):
        for index, kind in enumerate(("input", "model", "tools", "format", "reasoning", "extra", "tool_choice", "instructions")):
            candidate = deepcopy(self.completion)
            if kind == "input": candidate["input"][0]["content"] += "changed"
            elif kind == "model": candidate["model"] = "different-model"
            elif kind == "tools": candidate["tools"] = []
            elif kind == "format": candidate["text"]["format"]["name"] = "earnings_open_decision_v1"
            elif kind == "reasoning": candidate["reasoning"] = {"effort": "high"}
            elif kind == "extra": candidate["new_field"] = True
            elif kind == "tool_choice": candidate["tool_choice"] = "auto"
            else: candidate["instructions"] = "unrelated completion"
            client = Mock(); client.post.return_value = {"input_tokens": 23000}
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                context.pack(client, self.normal, self.limits, self.root, index + 3,
                             completion_request=candidate)
            self.assertLessEqual(client.post.call_count, 3)

    def test_default_fitting_Controller_and_already_final_Author_paths_are_unchanged(self):
        client = Mock(); client.post.return_value = {"input_tokens": 9000}
        selected = context.pack(client, self.normal, self.limits, self.root, 20,
                                completion_request=self.completion)
        self.assertEqual(selected, self.normal)
        self.assertEqual(selected["tool_choice"], "auto")
        self.assertEqual(client.post.call_count, 1)
        legacy = Mock(); legacy.post.return_value = {"input_tokens": 23000}
        with self.assertRaises(BudgetStop):
            context.pack(legacy, self.normal, self.limits, self.root, 21)
        self.assertEqual(legacy.post.call_count, 4)
        self.assertEqual(legacy.post.call_args_list[-1].args[1], context.project(self.normal, 100)[0])
        for author in (False, True):
            helper = self.helper()
            helper.generations = [helper.message(self.author_value(helper) if author else helper.choice("continue"))]
            service = helper.service(author=author, max_turns=1)
            def keep(client, request, limits, output, turn, **options):
                self.assertIsNone(options.get("completion_request"))
                return deepcopy(request)
            with patch.object(roles, "pack", side_effect=keep), patch.object(roles, "budgeted_response", side_effect=helper.fake_paid):
                if author: service.author(helper.choice("R"), {"axis": "R"}, str(helper.slot))
                else: service.propose(helper.prompt, str(helper.slot))

    def test_fourth_count_or_deadline_failure_is_not_caught_retried_or_replaced(self):
        for turn, last in ((30, TimeoutError("synthetic count timeout")),
                           (31, BudgetStop("synthetic original deadline")), (32, {"input_tokens": 10001})):
            client = Mock(); client.post.side_effect = [{"input_tokens": 23000}] * 3 + [last]
            expected = type(last) if isinstance(last, Exception) else BudgetStop
            with self.subTest(turn=turn), self.assertRaises(expected):
                context.pack(client, self.normal, self.limits, self.root, turn,
                             completion_request=self.completion)
            self.assertEqual(client.post.call_count, 4)
            self.assertTrue(all(call.args[0] == "/v1/responses/input_tokens" for call in client.post.call_args_list))

    def test_actual_role_closes_at_turn_two_of_three_and_never_dispatches_final_tools(self):
        for tool_violation in (False, True):
            helper = self.helper()
            helper.generations = [helper.tool_response(helper.call()),
                helper.tool_response(helper.call("forbidden-final")) if tool_violation else helper.message(self.author_value(helper))]
            observed = []
            def force_final(client, request, limits, output, turn, **options):
                completion = options.get("completion_request")
                self.assertIsNotNone(completion)
                self.assertEqual(completion, dict(request, tool_choice="none",
                    instructions=request["instructions"] + roles.FINALIZE + roles.FINAL_AUTHOR))
                observed.append(turn)
                return deepcopy(request) if turn == 1 else context.author_final_view(completion, 100)[0]
            service = helper.service(author=True, max_turns=3)
            with patch.object(roles, "pack", side_effect=force_final), patch.object(roles, "budgeted_response", side_effect=helper.fake_paid):
                if tool_violation:
                    with self.assertRaises(RuntimeError): service.author(helper.choice("R"), {"axis": "R"}, str(helper.slot))
                else: service.author(helper.choice("R"), {"axis": "R"}, str(helper.slot))
            self.assertEqual(observed, [1, 2])
            self.assertEqual(len(helper.requests), 2)
            self.assertEqual(helper.requests[-1]["tool_choice"], "none")
            self.assertEqual(len(helper.broker.calls), 1)
            self.assertEqual((helper.slot / "candidate.json").exists(), not tool_violation)

    def test_early_snapshot_matches_stock_recount_reservation_and_one_physical_generation(self):
        from edgar_forecast_budget import PilotBudget
        from edgar_forecast_openai import budgeted_response
        from earnings_entry import ReceiptHTTP
        calls, counts = [], iter((23000, 18000, 16000, 9000, 9000))
        model = self.normal["model"]
        class Client:
            def post(client, endpoint, payload):
                calls.append((endpoint, deepcopy(payload)))
                if endpoint.endswith("input_tokens"): return {"input_tokens": next(counts)}
                return {"model": model, "service_tier": "default", "status": "completed", "error": None,
                        "output": [], "usage": {"input_tokens": 9000, "output_tokens": 7, "total_tokens": 9007,
                                                 "input_tokens_details": {"cached_tokens": 0}}}
        transport = ReceiptHTTP(Client(), self.root)
        selected = context.pack(transport, self.normal, self.limits, self.root, 40,
                                completion_request=self.completion)
        budget = PilotBudget(self.root / "invented-only-budget.sqlite3"); self.addCleanup(budget.close)
        rates = {"api_model": model, "effort": "max", "input": "2", "cached": ".1", "write": "2.5", "output": "10"}
        budgeted_response(transport, selected, rates, self.limits, budget, self.root, 40)
        self.assertEqual([endpoint for endpoint, _ in calls], ["/v1/responses/input_tokens"] * 5 + ["/v1/responses"])
        reserved = json.loads((self.root / "40-request.json").read_bytes())
        self.assertEqual(calls[3][1], selected)
        self.assertEqual(calls[4][1], selected)
        self.assertEqual(reserved["payload"], selected)
        self.assertEqual(calls[-1][1], dict(selected, max_output_tokens=32768, service_tier="default", store=False))
        self.assertEqual(budget.db.execute("SELECT status FROM requests").fetchall(), [("settled",)])
        self.assertEqual(budget.summary()["unresolved_reserved_usd"], 0)
