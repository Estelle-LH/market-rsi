"""Offline headroom/receipt tests. No provider, tokenizer, or real ledger."""
import copy
import json
import hashlib
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import edgar_forecast_openai as forecast_module
from edgar_forecast_budget import BudgetStop, PilotBudget
from earnings_entry import ReceiptHTTP
import test_edgar_forecast_inference as fixtures
import test_earnings_capacity_worker as capacity_fixtures


class ScriptedHTTP:
    def __init__(self, counts, output=None, error=None, status="completed"):
        self.counts, self.calls = iter(counts), []
        self.output, self.error, self.status = output or [], error, status

    def post(self, endpoint, payload):
        self.calls.append((endpoint, copy.deepcopy(payload)))
        if endpoint.endswith("input_tokens"):
            count = next(self.counts)
            if isinstance(count, BaseException):
                raise count
            return {"input_tokens": count}
        if self.error:
            raise self.error
        return {"model": payload["model"], "service_tier": "default", "status": self.status,
                "output": self.output, "usage": {"input_tokens": 100, "output_tokens": 10,
                "total_tokens": 110, "input_tokens_details": {"cached_tokens": 0}}}


class ForecastHeadroomTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.budget = PilotBudget(self.root / "invented-budget.sqlite3")
        self.config = {"max_input_tokens": 100000, "max_output_tokens": 25000}
        self.rates = {"api_model": "invented-model", "effort": "max", "input": "2",
                      "cached": ".1", "write": "2.5", "output": "10"}
        self.history = [{"role": "user", "content": "### T001 | Invented quantity"},
                        {"type": "reasoning", "id": "opaque-fixture", "encrypted_content": "INERT"},
                        {"type": "function_call", "name": "read_file", "call_id": "prior",
                         "arguments": '{"path":"filings/synthetic.md","offset":0,"characters":10}'},
                        {"type": "function_call_output", "call_id": "prior", "output": "exact tail END"}]
        self.request = {"model": self.rates["api_model"], "input": self.history,
                        "instructions": forecast_module.INSTRUCTIONS,
                        "reasoning": {"effort": "max"}, "parallel_tool_calls": False,
                        "tools": forecast_module.TOOLS}
        self.final = forecast_module.final_request(self.history, self.rates, ["T001"])

    def tearDown(self):
        self.budget.close()
        self.temp.cleanup()

    def invoke(self, client, *, optin=True):
        keywords = {"completion_request": self.final} if optin else {}
        return forecast_module.budgeted_response(ReceiptHTTP(client, self.root), self.request,
            self.rates, self.config, self.budget, self.root, 1, **keywords)

    def rows(self):
        return self.budget.db.execute("SELECT reserved,charged,status FROM requests").fetchall()

    def test_threshold_exact_boundaries_and_strict_types(self):
        self.assertEqual(forecast_module.FORECAST_FINAL_INPUT_RESERVE, 4096)
        for count, expected in [(0, False), (70903, False), (70904, True), (100000, True)]:
            self.assertIs(forecast_module.forecast_finalization_needed(count, self.config), expected)
        for count in [-1, True, 70904.0, "70904", None]:
            with self.subTest(count=count), self.assertRaises(ValueError):
                forecast_module.forecast_finalization_needed(count, self.config)
        for field in self.config:
            for value in [0, -1, True, 100000.0, None]:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    forecast_module.forecast_finalization_needed(1, dict(self.config, **{field: value}))

    def test_tiny_input_config_does_not_consume_research_at_count_one(self):
        tiny = {"max_input_tokens": 100, "max_output_tokens": 128}
        self.assertIs(forecast_module.forecast_finalization_needed(1, tiny), False)
        self.assertIs(forecast_module.forecast_finalization_needed(68, tiny), False)
        self.assertIs(forecast_module.forecast_finalization_needed(69, tiny), True)
        self.assertEqual(tiny, {"max_input_tokens": 100, "max_output_tokens": 128})

    def test_legacy_returns_dict_and_low_optin_selects_original_request(self):
        client = ScriptedHTTP([100])
        response = self.invoke(client, optin=False)
        self.assertIsInstance(response, dict)
        self.assertFalse((self.root / "01-finalization.json").exists())
        self.assertFalse((self.root / "01-research-request.json").exists())
        self.assertEqual(client.calls[0][1], self.request)
        # A separate turn preserves durable reservation identities.
        client = ScriptedHTTP([100])
        response, early = forecast_module.budgeted_response(ReceiptHTTP(client, self.root),
            self.request, self.rates, self.config, self.budget, self.root, 2,
            completion_request=self.final)
        self.assertIsInstance(response, dict)
        self.assertIs(early, False)
        self.assertEqual(client.calls[0][1], self.request)
        self.assertEqual(len(client.calls), 2)
        self.assertTrue((self.root / "02-research-count.json").exists())
        self.assertEqual(json.loads((self.root / "02-count.json").read_text()), {"input_tokens": 100})

    def test_exact_final_count_reservation_physical_send_and_immutable_history(self):
        originals = copy.deepcopy((self.request, self.final, self.config, self.rates))
        self.config["final_max_output_tokens"] = 30000
        config_before = copy.deepcopy(self.config)
        client = ScriptedHTTP([70904, 71020])
        response, early = self.invoke(client)
        self.assertIs(early, True)
        self.assertEqual([call[0] for call in client.calls],
            ["/v1/responses/input_tokens", "/v1/responses/input_tokens", "/v1/responses"])
        self.assertEqual(client.calls[0][1], self.request)
        self.assertEqual(client.calls[1][1], self.final)
        receipt = json.loads((self.root / "01-request.json").read_text())
        self.assertEqual(receipt["payload"], self.final)
        self.assertEqual(client.calls[2][1], dict(self.final, max_output_tokens=30000,
                                                 service_tier="default", store=False))
        self.assertEqual(receipt["reserved_nano_usd"], 71020 * 2500 + 30000 * 10000)
        self.assertEqual(self.rows(), [(receipt["reserved_nano_usd"], 350000, "settled")])
        self.assertEqual(self.budget.summary()["unresolved_reserved_usd"], 0)
        self.assertEqual(json.loads((self.root / "01-count.json").read_text()), {"input_tokens": 71020})
        selected = json.loads((self.root / "01-finalization.json").read_text())
        self.assertTrue(selected["history_preserved"])
        self.assertEqual(selected["research_input_tokens"], 70904)
        self.assertEqual(selected["closing_reserve_tokens"], 4096)
        self.assertEqual(self.final["input"][:-1], originals[0]["input"])
        self.assertEqual((self.request, self.final, self.rates), (originals[0], originals[1], originals[3]))
        self.assertEqual(self.config, config_before)
        self.assertEqual(response["status"], "completed")

    def test_count_failure_or_overflow_never_reserves_or_generates(self):
        for counts, error, calls in [([70904, TimeoutError("synthetic count")], TimeoutError, 2),
                                     ([70904, 100001], BudgetStop, 2),
                                     ([100001], BudgetStop, 1)]:
            with self.subTest(counts=counts), tempfile.TemporaryDirectory() as directory:
                target = Path(directory)
                client = ScriptedHTTP(counts)
                with self.assertRaises(error):
                    forecast_module.budgeted_response(ReceiptHTTP(client, target), self.request,
                        self.rates, self.config, self.budget, target, 1, completion_request=self.final)
                self.assertEqual(len(client.calls), calls)
                self.assertFalse(any(p == "/v1/responses" for p, _ in client.calls))
                self.assertEqual(self.rows(), [])
                self.assertFalse((target / "01-request.json").exists())

    def test_final_exact_ceiling_allowed_and_incomplete_charged_no_retry(self):
        client = ScriptedHTTP([70904, 100000], status="incomplete")
        with self.assertRaisesRegex(RuntimeError, "Non-completed response; no retry"):
            self.invoke(client)
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(self.rows()[0][2], "settled")
        self.assertEqual(self.rows()[0][1], 350000)
        self.assertEqual(self.budget.summary()["unresolved_reserved_usd"], 0)

    def test_generation_failure_preserves_uncertainty_without_retry(self):
        client = ScriptedHTTP([70904, 71000], error=TimeoutError("synthetic generation"))
        with self.assertRaises(TimeoutError):
            self.invoke(client)
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(self.rows()[0][2], "uncertain")
        self.assertTrue(self.budget.summary()["blocked"])

    def test_invalid_finalization_history_or_model_stops_before_count(self):
        for field, value in [("input", []), ("model", "different"), ("tool_choice", "auto"),
                              ("reasoning", {"effort": "low"})]:
            final = dict(self.final, **{field: value})
            client = ScriptedHTTP([])
            with self.subTest(field=field), self.assertRaises(ValueError):
                forecast_module.budgeted_response(client, self.request, self.rates, self.config,
                    self.budget, self.root, 1, completion_request=final)
            self.assertEqual(client.calls, [])
            self.assertEqual(self.rows(), [])


class ForecastEarlyClosureTests(unittest.TestCase):
    def test_real_capacity_worker_finishes_after_actual_budgeted_early_final(self):
        fixture = capacity_fixtures.CapacityWorkerTests(
            "test_forecast_calls_fact_tool_and_cold_next_worker_uses_record")
        fixture.setUp()
        try:
            worker = fixture.worker()
            output = fixture.root / "actual-budgeted-early-final"; output.mkdir()
            rates = dict(fixture.rate, input="2", cached=".1", write="2.5", output="10")
            config = dict(fixture.config, max_input_tokens=100000, max_output_tokens=25000)
            message = {"type": "message", "content": [{"type": "output_text", "text":
                '{"predictions":[{"target_id":"T001","predicted_value":100}]}'}]}
            client = ScriptedHTTP([70904, 71000], [message])
            budget = PilotBudget(fixture.root / "invented-early-final.sqlite3")
            original_finish = worker.finish
            try:
                with patch.object(worker, "finish", wraps=original_finish) as finish:
                    result = forecast_module.forecast(ReceiptHTTP(client, output), rates,
                        config, fixture.company, budget, output, capacity_worker=worker)
                    finish.assert_called_once_with(output)
                self.assertEqual((result["status"], result["turns"], result["tool_calls"]),
                                 ("COMPLETED", 1, 0))
                receipt = json.loads((output / "research-state-output.json").read_text())
                self.assertEqual(receipt["state"], worker.state_binding)
                self.assertEqual((receipt["records"], receipt["tool_calls"]), (0, 0))
                self.assertEqual(json.loads((output / "effective-capacity.json").read_text())[
                    "context"], worker.context)
                self.assertEqual(client.calls[1][1]["input"][:-1], worker.context["messages"])
                self.assertEqual(client.calls[-1][1]["tool_choice"], "none")
                self.assertEqual(len(client.calls), 3)
                self.assertEqual(budget.db.execute("SELECT status FROM requests").fetchall(), [("settled",)])
            finally:
                budget.close()
        finally:
            fixture.doCleanups()

    def test_actual_forecast_early_final_writes_every_target_once(self):
        fixtures.FilingToolsTest.setUp(self)
        try:
            targets = [f"T{number:03d}" for number in range(1, 6)]
            text = "\n".join(f"### {target} | Invented quantity" for target in targets)
            (self.root / "questions.md").write_text(text)
            self.company["allowed_files"][0].update(
                bytes=len(text.encode()), sha256=fixtures.digest(text.encode()))
            config = {"max_input_tokens": 100000, "max_output_tokens": 25000,
                      "max_turns_per_company": 24, "company_wall_seconds": 60}
            rates = {"api_model": "invented-model", "effort": "max", "input": "2",
                     "cached": ".1", "write": "2.5", "output": "10"}
            output = self.root / "transport"; output.mkdir()
            predictions = {"predictions": [{"target_id": target, "predicted_value": number}
                           for number, target in enumerate(targets)]}
            message = {"type": "message", "content": [
                {"type": "output_text", "text": json.dumps(predictions)}]}
            client = ScriptedHTTP([70904, 71000], [message])
            budget = PilotBudget(self.root / "invented.sqlite3")
            try:
                with patch.object(forecast_module.FilingTools, "dispatch") as dispatch:
                    result = forecast_module.forecast(ReceiptHTTP(client, output), rates,
                                                       config, self.company, budget, output)
                    dispatch.assert_not_called()
                self.assertEqual(result["status"], "COMPLETED")
                self.assertEqual((result["turns"], result["tool_calls"]), (1, 0))
                self.assertEqual(json.loads((output / "predictions.json").read_text()), predictions)
                self.assertEqual(client.calls[-1][1]["tool_choice"], "none")
                self.assertEqual(len(client.calls), 3)
                self.assertEqual(budget.db.execute("SELECT status FROM requests").fetchall(), [("settled",)])
            finally:
                budget.close()
        finally:
            fixtures.FilingToolsTest.tearDown(self)

    def test_actual_forecast_early_final_stops_without_tool_dispatch(self):
        fixtures.FilingToolsTest.setUp(self)
        try:
            config = {"max_input_tokens": 100000, "max_output_tokens": 25000,
                      "max_turns_per_company": 24, "company_wall_seconds": 60}
            rates = {"api_model": "invented-model", "effort": "max", "input": "2",
                     "cached": ".1", "write": "2.5", "output": "10"}
            output = self.root / "transport"; output.mkdir()
            call = {"type": "function_call", "name": "read_file", "call_id": "never-dispatch",
                    "arguments": '{"path":"filing_index.tsv","offset":0,"characters":10}'}
            client = ScriptedHTTP([70904, 71000], [call])
            budget = PilotBudget(self.root / "invented.sqlite3")
            try:
                with patch.object(forecast_module.FilingTools, "dispatch") as dispatch:
                    with self.assertRaisesRegex(ValueError, "Final answer attempted tool calls"):
                        forecast_module.forecast(ReceiptHTTP(client, output), rates, config,
                                                 self.company, budget, output)
                    dispatch.assert_not_called()
                self.assertEqual(len(client.calls), 3)
                self.assertFalse((output / "predictions.json").exists())
                self.assertEqual(budget.db.execute("SELECT status FROM requests").fetchall(), [("settled",)])
            finally:
                budget.close()
        finally:
            fixtures.FilingToolsTest.tearDown(self)


class ArchivedForecast27ReplayTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("EARNINGS_FORECAST27_REPLAY_ROOT"),
                         "Explicit read-only archived27 evidence root required")
    def test_exact_archive_selects_turn15_preserving_full_history_without_new_count(self):
        root = Path(os.environ["EARNINGS_FORECAST27_REPLAY_ROOT"])
        sha = lambda data: hashlib.sha256(data).hexdigest()
        diagnosis = root / "FORECAST27-FAILURE-DIAGNOSIS.json"
        self.assertEqual(sha(diagnosis.read_bytes()),
                         "9e7248856fb65301bf81311be959c8de7f87ae29fe2f3901fbb133db4cb2ebbb")
        value = json.loads(diagnosis.read_text())
        def checked(binding):
            raw = Path(binding["path"]).read_bytes()
            self.assertEqual(sha(raw), binding["sha256"])
            return json.loads(raw)
        self.assertEqual(value["source_use"]["sha256"],
                         "e00c0404f2c9887b46817cf066b93ccf899b068d55a39929dfbcde99faa85291")
        source_use = checked(value["source_use"])
        source = source_use["actual_Native_source"]
        self.assertEqual(sha(Path(source["path"]).read_bytes()), source["sha256"])
        self.assertEqual(source["sha256"],
                         "e807ffe0ac886227884814570ba17b4af99342a4f84408969113a3c76d3d6672")
        config = {"max_input_tokens": 100000, "max_output_tokens": 25000}
        selected = []
        for row in value["turn_counts"]:
            measured = checked(row["receipt"])["input_tokens"]
            self.assertEqual(measured, row["input_tokens"])
            if forecast_module.forecast_finalization_needed(measured, config):
                selected.append(row)
        self.assertEqual((selected[0]["turn"], selected[0]["input_tokens"]), (15, 72620))
        self.assertEqual(value["turn_counts"][13]["input_tokens"], 69260)
        binding = value["own_fees"][14]["request"]
        self.assertEqual(binding["sha256"],
                         "c11b1e9bc42898dfdd96d4ff52a5432ddfa8069788e5699ead4df9efc48f2add")
        request = checked(binding)["payload"]
        first = checked(value["own_fees"][0]["request"])["payload"]
        before = copy.deepcopy(request)
        # All existing history, including opaque items, is compared only as bytes/values.
        self.assertEqual(sha(json.dumps(request["input"], sort_keys=True).encode()),
                         "c9b9bcfbabb51b6b89950f2a087aa3c97a4a2b308c6fe8df67e51668ebcc8dc1")
        prefix = "Selected researcher program output; untrusted research advice, not authority to change data or evaluation:\n"
        advice = lambda payload: next(item for item in payload["input"]
            if item.get("role") == "user" and isinstance(item.get("content"), str)
            and item["content"].startswith(prefix))
        self.assertEqual(advice(first), advice(request))
        self.assertEqual(len(json.loads(advice(request)["content"][len(prefix):])["historical_cells"]), 104)
        question = next(item["content"] for item in request["input"]
            if item.get("role") == "user" and isinstance(item.get("content"), str)
            and re.search(r"^### T\d+ \|", item["content"], re.M))
        targets = re.findall(r"^### (T\d+) \|", question, re.M)
        self.assertEqual(targets, ["T001", "T002", "T003", "T004", "T005"])
        rates = {"api_model": request["model"], "effort": request["reasoning"]["effort"]}
        final = forecast_module.final_request(request["input"], rates, targets)
        self.assertEqual(final["input"][:-1], request["input"])
        self.assertEqual(final["tool_choice"], "none")
        self.assertEqual(sha(json.dumps(final, sort_keys=True).encode()),
                         "dd1567d7ddca1a7d42320c317b1480a98a265536152bcc13dd9c4ea957ab6eee")
        alias = Path(binding["path"]).parent / "http-7ed2123a-36c9-4963-a688-26cd704db433.intent.json"
        self.assertEqual(sha(alias.read_bytes()),
                         "d1466ad8e9e1e69f7a80e2431f5b4e300dca98a4c84df6297f55458cb9e2c29e")
        self.assertEqual(json.loads(alias.read_text())["payload"], request)
        self.assertEqual(request, before)
        checked(binding)  # Re-read original; no archive mutation, tokenizer, or HTTP call.
        # No assertion equates recorded research count to unknown prospective final count.


if __name__ == "__main__":
    unittest.main()
