"""Explicit final-Author public snapshot; invented carriers are never evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import earnings_open_context as context
import earnings_open_roles as roles
from edgar_forecast_budget import BudgetStop
from market_rsi import digest
import test_earnings_open_roles as role_fixture


class NoCopyCarrier(str):
    """An invented marker; a public snapshot must never deepcopy this field."""
    def __deepcopy__(self, memo): raise AssertionError("Reasoning carrier copied")


class AuthorFinalContextTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="author-final-context-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = "def algorithm(payload):\n    return payload\n" + "# Full public code stays.\n" * 100
        self.call = {"type": "function_call", "call_id": "public_call", "name": "run_python",
                     "arguments": json.dumps({"source": self.source, "payload_json": "{}"})}
        self.output = {"type": "function_call_output", "call_id": "public_call", "output": "界" * 6000}
        self.message = {"type": "message", "role": "assistant", "id": "public-id",
                        "content": [{"type": "output_text", "text": self.source}]}
        fields = {name: {"type": "string"} for name in ("decision_sha256", "source_text", "test_text")}
        self.request = {"model": "gpt-6.1-sol", "reasoning": {"effort": "max"},
            "instructions": "Exact Author instruction", "tools": [{"synthetic": True}],
            "tool_choice": "none", "parallel_tool_calls": False,
            "text": {"format": {"type": "json_schema", "name": "earnings_open_author_v1", "strict": True,
                "schema": {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}}},
            "input": [{"role": "user", "content": json.dumps({"decision_sha256": "a" * 64, "before_profile": {"axis": "R"}})},
                {"type": "reasoning", "encrypted_content": "INVENTED_OPAQUE_CARRIER" * 2000},
                self.call, self.output, self.message]}

    def snapshot(self, request=None):
        result, receipts = context.author_final_view(self.request if request is None else request, 100)
        return result, receipts, json.loads(result["input"][1]["content"])

    def test_snapshot_preserves_initial_packet_complete_public_code_and_all_other_fields(self):
        before = deepcopy(self.request)
        result, receipts, snapshot = self.snapshot()
        self.assertEqual(self.request, before)
        self.assertEqual({k: v for k, v in result.items() if k != "input"},
                         {k: v for k, v in before.items() if k != "input"})
        self.assertEqual(len(result["input"]), 2)
        self.assertEqual(result["input"][0], before["input"][0])
        self.assertEqual(result["input"][1]["role"], "user")
        self.assertEqual(snapshot["schema"], "earnings_author_final_public_snapshot_v1")
        self.assertTrue(snapshot["notice"])
        records = snapshot["records"]
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0], self.call)
        self.assertEqual(records[2], {"type": "message", "role": "assistant",
                                     "content": [{"type": "output_text", "text": self.source}]})
        self.assertNotIn("INVENTED_OPAQUE_CARRIER", json.dumps(result))
        projected = json.loads(records[1]["output"])
        self.assertEqual(projected["original_output_sha256"], hashlib.sha256(self.output["output"].encode()).hexdigest())
        self.assertEqual(projected["original_output_bytes"], len(self.output["output"].encode()))
        self.assertTrue(projected["truncated"])
        self.assertLessEqual(len(projected["preview"].encode()), 100)
        by_index = {row["input_index"]: row for row in receipts}
        self.assertEqual(set(by_index), {2, 3, 4})
        for index, record in zip((2, 3, 4), records):
            self.assertEqual(by_index[index]["original_item_sha256"], hashlib.sha256(context.encoded(before["input"][index])).hexdigest())
            self.assertEqual(by_index[index]["public_record_sha256"], hashlib.sha256(context.encoded(record)).hexdigest())

    def test_reasoning_item_is_type_detected_only_not_read_copied_or_hashed_per_item(self):
        request = deepcopy(self.request)
        reasoning = {"type": "reasoning", "encrypted_content": NoCopyCarrier("INVENTED_SENTINEL")}
        request["input"][1] = reasoning
        original_encoded = context.encoded
        def public_encoding(value):
            if value is reasoning: raise AssertionError("Reasoning item hashed or serialized")
            return original_encoded(value)
        with patch.object(context, "encoded", side_effect=public_encoding):
            result, receipts, _ = self.snapshot(request)
        self.assertNotIn("INVENTED_SENTINEL", json.dumps(result))
        self.assertNotIn(1, [row["input_index"] for row in receipts])

    def test_strict_pairs_unknown_items_content_and_nonAuthor_final_format_reject(self):
        invalid_inputs = [
            [self.output], [self.call], [self.call, self.call, self.output],
            [self.call, self.output, self.output],
            [self.call, dict(self.output, call_id="unknown")],
            [{"type": "custom_tool_call", "call_id": "bad"}],
            [{"type": "message", "role": "assistant", "content": [{"type": "reasoning", "text": "INVENTED"}]}],
            [{"type": "message", "role": "assistant", "content": []}],
        ]
        for items in invalid_inputs:
            with self.subTest(items=items):
                changed = deepcopy(self.request)
                changed["input"] = [changed["input"][0], *deepcopy(items)]
                with self.assertRaises(ValueError): self.snapshot(changed)
        for kind in ("tool_choice", "format_name", "properties", "first_user"):
            changed = deepcopy(self.request)
            if kind == "tool_choice": changed["tool_choice"] = "auto"
            elif kind == "format_name": changed["text"]["format"]["name"] = "earnings_open_decision_v1"
            elif kind == "properties": del changed["text"]["format"]["schema"]["properties"]["source_text"]
            else: changed["input"][0] = {"role": "assistant", "content": "not initial packet"}
            with self.subTest(kind=kind), self.assertRaises(ValueError): self.snapshot(changed)

    def test_pack_first_three_native_views_then_explicit_fourth_snapshot_and_receipt(self):
        client = Mock()
        client.post.side_effect = [{"input_tokens": 23000}, {"input_tokens": 18000},
                                   {"input_tokens": 16000}, {"input_tokens": 9000}]
        before = deepcopy(self.request)
        result = context.pack(client, self.request, {"max_input_tokens": 10000}, self.root, 8, author_final=True)
        sent = [call.args[1] for call in client.post.call_args_list]
        self.assertEqual(len(sent), 4)
        self.assertEqual(sent[0], before)
        self.assertEqual(sent[1], context.project(before, 2000)[0])
        self.assertEqual(sent[2], context.project(before, 500)[0])
        self.assertEqual(sent[3], context.author_final_view(before, 100)[0])
        self.assertEqual(result, sent[-1])
        self.assertEqual(self.request, before)
        self.assertTrue(all(call.args[0] == "/v1/responses/input_tokens" for call in client.post.call_args_list))
        receipt = json.loads((self.root / "08-context-04.json").read_bytes())
        self.assertTrue(receipt["generation_not_sent"])
        self.assertEqual(receipt["original_request_sha256"], hashlib.sha256(context.encoded(before)).hexdigest())
        self.assertEqual(receipt["effective_request_sha256"], hashlib.sha256(context.encoded(result)).hexdigest())
        self.assertEqual(receipt["preview_bytes"], 100)

    def test_default_pack_remains_native_and_never_partially_replays_a_snapshot(self):
        client = Mock()
        client.post.return_value = {"input_tokens": 23000}
        with self.assertRaises(BudgetStop):
            context.pack(client, self.request, {"max_input_tokens": 10000}, self.root, 1)
        self.assertEqual(client.post.call_count, 4)
        for call in client.post.call_args_list:
            candidate = call.args[1]
            self.assertEqual(candidate["input"][0], self.request["input"][0])
            self.assertEqual(candidate["input"][1], self.request["input"][1])
            self.assertEqual(candidate["input"][2], self.call)
            self.assertEqual(candidate["input"][4], self.message)

    def test_fourth_count_failure_or_overcap_fails_once_without_generation_retry(self):
        for turn, final in ((2, TimeoutError("synthetic fourth count")), (3, {"input_tokens": 10001})):
            client = Mock()
            client.post.side_effect = [{"input_tokens": 23000}] * 3 + [final]
            error = TimeoutError if isinstance(final, Exception) else BudgetStop
            with self.subTest(turn=turn), self.assertRaises(error):
                context.pack(client, self.request, {"max_input_tokens": 10000}, self.root, turn, author_final=True)
            self.assertEqual(client.post.call_count, 4)
            self.assertTrue(all(call.args[0] == "/v1/responses/input_tokens" for call in client.post.call_args_list))

    def test_fourth_snapshot_matches_actual_stock_count_reservation_and_physical_generation(self):
        from edgar_forecast_budget import PilotBudget
        from edgar_forecast_openai import budgeted_response
        from earnings_entry import ReceiptHTTP
        calls, counts = [], iter((23000, 18000, 16000, 9000, 9000))
        original = deepcopy(self.request)
        class SyntheticClient:
            def post(client, endpoint, payload):
                calls.append((endpoint, deepcopy(payload)))
                if endpoint == "/v1/responses/input_tokens":
                    return {"input_tokens": next(counts)}
                if endpoint != "/v1/responses":
                    raise AssertionError("Unexpected synthetic dispatch")
                return {"model": original["model"], "service_tier": "default", "status": "completed",
                        "error": None, "output": [], "usage": {"input_tokens": 9000,
                        "output_tokens": 7, "total_tokens": 9007,
                        "input_tokens_details": {"cached_tokens": 0}}}
        transport = ReceiptHTTP(SyntheticClient(), self.root)
        limits = {"max_input_tokens": 10000, "max_output_tokens": 32768}
        selected = context.pack(transport, self.request, limits, self.root, 1, author_final=True)
        budget = PilotBudget(self.root / "synthetic-only-budget.sqlite3")
        self.addCleanup(budget.close)
        rates = {"api_model": original["model"], "effort": "max",
                 "input": "2", "cached": ".1", "write": "2.5", "output": "10"}
        budgeted_response(transport, selected, rates, limits, budget, self.root, 1)
        self.assertEqual([endpoint for endpoint, _ in calls],
                         ["/v1/responses/input_tokens"] * 5 + ["/v1/responses"])
        self.assertEqual(calls[3][1], selected)
        self.assertEqual(calls[4][1], selected)
        reserved = json.loads((self.root / "01-request.json").read_bytes())
        self.assertEqual(reserved["payload"], selected)
        self.assertEqual(calls[-1][1], dict(selected, max_output_tokens=32768,
                                          service_tier="default", store=False))
        intents = [json.loads(path.read_bytes()) for path in self.root.glob("http-*.intent.json")]
        generated = [row for row in intents if row["endpoint"] == "/v1/responses"]
        self.assertEqual(len(generated), 1)
        self.assertEqual(generated[0]["complete_reservation"], reserved)
        self.assertEqual(generated[0]["payload"], calls[-1][1])
        self.assertEqual(budget.db.execute("SELECT reserved,charged,status FROM requests").fetchall(),
                         [(9000 * 2500 + 32768 * 10000, 9000 * 2500 + 7 * 10000, "settled")])
        self.assertEqual(budget.db.execute("SELECT COUNT(*) FROM requests WHERE status!='settled'").fetchone()[0], 0)
        self.assertEqual(budget.summary()["unresolved_reserved_usd"], 0)
        self.assertEqual(self.request, original)

    def test_only_actual_Author_final_turn_opts_in_not_Controller_or_initial_Author(self):
        helper = role_fixture.OpenRoleTests("test_author_finalization_documents_actual_schema_and_preserves_exact_candidate_fields")
        helper.setUp(); self.addCleanup(helper.doCleanups)
        chosen = helper.choice("R")
        payload = {"decision_sha256": digest(chosen), "source_text": "PROGRAM={'axis':'R'}\ndef run(p): return 1\n",
                   "test_text": "CASES=[{'input':{},'expected':1}]"}
        helper.generations = [helper.tool_response(helper.call()), helper.message(payload)]
        service = helper.service(author=True, max_turns=2)
        with patch.object(roles, "pack", wraps=context.pack) as packed, patch.object(
                roles, "budgeted_response", side_effect=helper.fake_paid):
            service.author(chosen, {"axis": "R"}, str(helper.slot))
        self.assertEqual([call.kwargs.get("author_final", False) for call in packed.call_args_list], [False, True])
        other = role_fixture.OpenRoleTests("test_controller_drives_multiple_tools_then_exact_final_alias")
        other.setUp(); self.addCleanup(other.doCleanups)
        other.generations = [other.message(other.choice("continue"))]
        with patch.object(roles, "pack", wraps=context.pack) as packed:
            other.invoke(other.service(max_turns=1))
        self.assertEqual([call.kwargs.get("author_final", False) for call in packed.call_args_list], [False])
