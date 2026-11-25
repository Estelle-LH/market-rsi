from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from edgar_forecast_budget import BudgetStop, PilotBudget, MODEL_CAP
from edgar_forecast_tools import FilingTools, calculate
from edgar_forecast_model_pilot import digest
from edgar_forecast_openai import budgeted_response, forecast, unit, RUNTIME, OpenAIHTTP, ProviderHTTPError, attempt_output, PILOT, final_request, predictions_from_output, INSTRUCTIONS, TOOLS, PLAN_HASH
from edgar_forecast_completion_trial import parent_history
from unittest.mock import patch, Mock
import json
import copy
import subprocess


class PilotBudgetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "budget.sqlite3"
        self.budget = PilotBudget(self.path)

    def tearDown(self):
        self.budget.close()
        self.tmp.cleanup()

    def test_reservation_survives_restart_and_blocks_dispatch(self):
        self.budget.reserve("a", "model", 1234)
        self.budget.close()
        self.budget = PilotBudget(self.path)
        self.assertEqual(self.budget.summary()["unresolved_reserved_usd"], 1234 / 1e9)
        with self.assertRaises(BudgetStop):
            self.budget.reserve("b", "other", 1)
        self.budget.settle("a", 1000)
        self.budget.reserve("b", "other", 1)

    def test_shared_process_and_model_ceilings(self):
        other = PilotBudget(self.path)
        try:
            for i in range(20):
                self.budget.reserve(str(i), "model" + str(i), MODEL_CAP)
                other.settle(str(i), MODEL_CAP)
            with self.assertRaises(BudgetStop):
                other.reserve("overflow", "new", 1)
        finally:
            other.close()
        self.assertEqual(self.budget.summary()["charged_upper_bound_usd"], 200)

    def test_model_ceiling_and_duplicate_identity(self):
        self.budget.reserve("a", "same", MODEL_CAP)
        self.budget.settle("a", MODEL_CAP)
        for name, model in [("b", "same"), ("a", "new")]:
            with self.assertRaises(BudgetStop):
                self.budget.reserve(name, model, 1)
        with self.assertRaises(BudgetStop):
            self.budget.settle("a", 0)

    def test_unknown_timeout_retains_liability(self):
        self.budget.reserve("timeout", "model", 999)
        self.budget.uncertain("timeout")
        self.assertTrue(self.budget.summary()["blocked"])
        self.assertEqual(self.budget.summary()["unresolved_reserved_usd"], 999 / 1e9)
        with self.assertRaises(BudgetStop):
            self.budget.settle("timeout", 0)

    def test_overcharge_is_recorded_and_blocks(self):
        self.budget.reserve("a", "model", 1)
        with self.assertRaises(BudgetStop):
            self.budget.settle("a", 2)
        self.assertEqual(self.budget.summary()["charged_upper_bound_usd"], 2 / 1e9)
        with self.assertRaises(BudgetStop):
            self.budget.reserve("b", "new", 1)

    def test_changed_existing_cap_rejected(self):
        self.budget.db.execute("UPDATE config SET cap=300 WHERE id=1")
        with self.assertRaises(BudgetStop):
            PilotBudget(self.path)

    def test_operator_reconciliation_preserves_full_liability_and_audit_on_restart(self):
        self.budget.reserve("original", "model", 250_960_000)
        self.budget.uncertain("original")
        self.budget.reconcile_uncertain_at_ceiling("original", "a" * 64)
        self.budget.close()
        self.budget = PilotBudget(self.path)
        self.budget.active()
        self.assertEqual(self.budget.summary()["charged_upper_bound_usd"], 0.25096)
        self.assertEqual(self.budget.summary()["unresolved_reserved_usd"], 0)
        self.assertEqual(self.budget.db.execute("SELECT prior_status, prior_charge, ceiling, evidence_sha256 FROM reconciliations").fetchone(),
                         ("uncertain", 0, 250_960_000, "a" * 64))
        with self.assertRaises(BudgetStop):
            self.budget.reconcile_uncertain_at_ceiling("original", "b" * 64)
        with self.assertRaises(BudgetStop):
            self.budget.settle("original", 0)
        with self.assertRaises(BudgetStop):
            self.budget.reserve("original", "model", 1)
        self.budget.reserve("next", "model", 1)

    def test_reconciliation_cannot_unblock_pending_or_overcharge(self):
        self.budget.reserve("original", "model", 123)
        with self.assertRaises(BudgetStop):
            self.budget.reconcile_uncertain_at_ceiling("original", "a" * 64)
        self.budget.uncertain("original")
        # Synthetic invalid concurrent/overcharge states must not be erased.
        for status, charged in [("reserved", 0), ("settled", 2)]:
            self.budget.db.execute("INSERT INTO requests VALUES ('other', 'model', 1, ?, ?)", (charged, status))
            with self.assertRaises(BudgetStop):
                self.budget.reconcile_uncertain_at_ceiling("original", "a" * 64)
            self.assertTrue(self.budget.summary()["blocked"])
            self.assertEqual(self.budget.db.execute("SELECT COUNT(*) FROM reconciliations").fetchone()[0], 0)
            self.budget.db.execute("DELETE FROM requests WHERE id='other'")
        with self.assertRaises(ValueError):
            self.budget.reconcile_uncertain_at_ceiling("original", "unsaved")

    def test_conservative_liability_still_counts_against_model_and_global_caps(self):
        self.budget.reserve("original", "model", MODEL_CAP)
        self.budget.uncertain("original")
        self.budget.reconcile_uncertain_at_ceiling("original", "a" * 64)
        with self.assertRaises(BudgetStop):
            self.budget.reserve("next", "model", 1)
        for i in range(19):
            self.budget.reserve(str(i), "model" + str(i), MODEL_CAP)
            self.budget.settle(str(i), MODEL_CAP)
        with self.assertRaises(BudgetStop):
            self.budget.reserve("overflow", "new", 1)


class AttemptIdentityTest(unittest.TestCase):
    def test_default_is_preserved_and_fresh_identity_is_exclusive(self):
        parent = PILOT / "fresh/gpt-5.5/CIK0000003545"
        self.assertEqual(attempt_output("gpt-5.5", "CIK0000003545"), parent)
        self.assertEqual(attempt_output("gpt-5.5", "CIK0000003545", "attempt-02-research-key"), parent / "attempt-02-research-key")
        with tempfile.TemporaryDirectory() as tmp, patch("edgar_forecast_openai.PILOT", Path(tmp)):
            path = attempt_output("gpt-5.5", "CIK0000003545", "attempt-02")
            path.mkdir(parents=True, exist_ok=False)
            with self.assertRaises(FileExistsError):
                path.mkdir(parents=True, exist_ok=False)

    def test_unsafe_attempt_ids_rejected(self):
        for identity in ["", "../previous", "/tmp/new", "a/b", "a" * 65, " space", "A"]:
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                attempt_output("gpt-5.5", "CIK0000003545", identity)


class FilingToolsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = {"questions.md": "### T001 | Revenue\nForecast revenue", "filing_index.tsv":
                     "date_filed\tform_type\taccession\tpath\n2026-01-01\t10-Q\told\tfilings/10-Q_old.md\n",
                     "filings/10-Q_old.md": "Revenue 100\nCosts 50\nrevenue 200"}
        self.company = {"visible_root": str(self.root), "target_accession": "hidden",
                        "cutoff": "2026-02-01", "allowed_files": []}
        for name, content in self.data.items():
            path = self.root / name
            path.parent.mkdir(exist_ok=True)
            path.write_text(content)
            self.company["allowed_files"].append({"path": name, "bytes": len(content.encode()),
                                                  "sha256": digest(content.encode())})
        self.tools = FilingTools(self.company)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_searches_and_calculates(self):
        self.assertEqual(self.tools.dispatch("read_file", {"path": "filings/10-Q_old.md", "offset": 0, "characters": 7})["text"], "Revenue")
        result = self.tools.dispatch("search_files", {"query": "revenue", "path_prefix": "filings/", "max_hits": 1})
        self.assertEqual((len(result["hits"]), result["total_matching_lines"]), (1, 2))
        self.assertEqual(self.tools.dispatch("calculate", {"expression": "100 * 1.05 - 50"}), {"value": 55.0})

    def test_rejects_extra_files_network_shell_and_invalid_arguments(self):
        for name, args in [("exec", {"command": "ls"}), ("web_search", {"query": "answers"}),
                           ("read_file", {"path": "../answers.json", "offset": 0, "characters": 10}),
                           ("read_file", {"path": "/etc/hosts", "offset": 0, "characters": 10}),
                           ("read_file", {"path": "questions.md", "offset": True, "characters": 10}),
                           ("read_file", {"path": "questions.md", "offset": 0, "characters": 20001}),
                           ("calculate", {"expression": "1+1", "extra": 1})]:
            with self.subTest(name=name, args=args), self.assertRaises(ValueError):
                self.tools.dispatch(name, args)

    def test_changed_or_symlinked_source_rejected(self):
        path = self.root / "questions.md"
        path.write_text("tampered")
        with self.assertRaises(ValueError):
            FilingTools(self.company)
        path.unlink()
        path.symlink_to(self.root / "filings/10-Q_old.md")
        with self.assertRaises(ValueError):
            FilingTools(self.company)

    def test_loaded_snapshot_is_immutable(self):
        (self.root / "questions.md").write_text("new data")
        self.assertEqual(self.tools.files["questions.md"], self.data["questions.md"])

    def test_index_cutoff_still_enforced(self):
        item = self.company["allowed_files"][1]
        text = self.data["filing_index.tsv"].replace("2026-01-01", "2026-02-02")
        (self.root / item["path"]).write_text(text)
        item.update(bytes=len(text.encode()), sha256=digest(text.encode()))
        with self.assertRaises(ValueError):
            FilingTools(self.company)

    def test_arithmetic_does_not_execute_code(self):
        for expression in ["__import__('os')", "(1).__class__", "10**100000", "[1]*5", "True+1", "1/0", "(-1)**0.5"]:
            with self.subTest(expression=expression), self.assertRaises((ValueError, ZeroDivisionError)):
                calculate(expression)
        self.assertEqual(calculate("-(10**2)/4"), -25)


class OfflineClient:
    def __init__(self, outputs):
        self.outputs, self.requests = iter(outputs), []

    def post(self, path, request):
        self.requests.append((path, copy.deepcopy(request)))
        if path.endswith("input_tokens"):
            return {"input_tokens": 100, "object": "response.input_tokens"}
        item = next(self.outputs)
        if isinstance(item, BaseException):
            raise item
        return {"model": request["model"], "status": "completed", "service_tier": "default",
                "usage": {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110,
                          "input_tokens_details": {"cached_tokens": 20}}, "output": item}


class OpenAIAdapterTest(unittest.TestCase):
    def setUp(self):
        FilingToolsTest.setUp(self)
        self.config = json.loads(RUNTIME.read_text())
        self.rates = self.config["models"]["gpt-6.1-sol"]
        self.out = self.root / "output"
        self.out.mkdir()
        self.budget = PilotBudget(self.root / "budget.sqlite3")

    def tearDown(self):
        self.budget.close()
        FilingToolsTest.tearDown(self)

    def test_final_only_ceiling_is_reserved_and_sent_without_research_change(self):
        self.config.update(max_turns_per_company=2, final_max_output_tokens=65536)
        call = {"type":"function_call","call_id":"first","name":"read_file",
                "arguments":json.dumps({"path":"filing_index.tsv","offset":0,"characters":100})}
        final = {"type":"message","content":[{"type":"output_text","text":
                 '{"predictions":[{"target_id":"T001","predicted_value":123}]}'}]}
        client = OfflineClient([[call],[final]])
        forecast(client,self.rates,self.config,self.company,self.budget,self.out)
        generated = [request for path,request in client.requests if path == "/v1/responses"]
        self.assertEqual([r["max_output_tokens"] for r in generated],[25000,65536])
        self.assertEqual(self.config["max_output_tokens"],25000)
        self.assertEqual([r["reasoning"] for r in generated],[{"effort":self.rates["effort"]}]*2)
        ceiling = max(unit(self.rates[k]) for k in ["input","cached","write"] if self.rates[k] is not None)
        reserves = [r[0] for r in self.budget.db.execute("SELECT reserved FROM requests ORDER BY rowid")]
        self.assertEqual(reserves,[100*ceiling+n*unit(self.rates["output"]) for n in [25000,65536]])

    def test_invalid_final_ceiling_rejects_before_api_or_reservation(self):
        self.config["max_turns_per_company"] = 1
        for invalid in [True,0,128001,"65536"]:
            self.config["final_max_output_tokens"] = invalid
            client = Mock()
            with self.assertRaises(ValueError):
                forecast(client,self.rates,self.config,self.company,self.budget,self.out)
            client.post.assert_not_called()
        self.assertEqual(self.budget.summary()["generation_requests_reserved"],0)

    def test_tool_to_final_loop_preserves_reasoning_and_phase(self):
        reasoning = {"type": "reasoning", "id": "r1", "encrypted_content": "opaque", "summary": []}
        call = {"type": "function_call", "call_id": "../../../odd", "name": "read_file",
                "arguments": json.dumps({"path": "filing_index.tsv", "offset": 0, "characters": 20000})}
        final = {"type": "message", "role": "assistant", "phase": "final_answer", "content": [
                 {"type": "output_text", "text": '{"predictions":[{"target_id":"T001","predicted_value":"123"}]}'}]}
        client = OfflineClient([[reasoning, call], [final]])
        result = forecast(client, self.rates, self.config, self.company, self.budget, self.out)
        self.assertEqual((result["status"], result["turns"], result["tool_calls"]), ("COMPLETED", 2, 1))
        self.assertEqual(result["strict_single_number_errors"], [])
        next_input = client.requests[2][1]["input"]
        self.assertIn(reasoning, next_input)
        self.assertEqual(next_input[-1]["call_id"], call["call_id"])
        self.assertEqual(len(list(self.out.glob("*-response.json"))), 2)
        self.assertEqual(len(list(self.out.glob("*-tool-*.json"))), 1)
        self.assertFalse(self.budget.summary()["blocked"])
        self.assertEqual(self.budget.summary()["generation_requests_reserved"], 2)

    def test_count_and_generation_payload_are_identical(self):
        request = {"model": self.rates["api_model"], "input": "public", "tools": [],
                   "reasoning": {"effort": "max"}, "parallel_tool_calls": False}
        client = OfflineClient([[]])
        budgeted_response(client, request, self.rates, self.config, self.budget, self.out, 1)
        counted, generated = client.requests[0][1], client.requests[1][1]
        self.assertEqual({k: generated[k] for k in counted}, counted)
        self.assertFalse(generated["store"])
        self.assertEqual(generated["service_tier"], "default")
        expected = (80 * unit("2.5") + 20 * unit("0.1") + 10 * unit("10")) / 1e9
        self.assertEqual(self.budget.summary()["charged_upper_bound_usd"], expected)

    def test_last_turn_closes_research_and_retains_definitions_without_calls(self):
        call = {"type": "function_call", "call_id": "first", "name": "read_file",
                "arguments": json.dumps({"path": "filing_index.tsv", "offset": 0, "characters": 20000})}
        final = {"type": "message", "content": [{"type": "output_text", "text":
                 '{"predictions":[{"target_id":"T001","predicted_value":123}]}'}]}
        self.config["max_turns_per_company"] = 2
        client = OfflineClient([[call], [final]])
        result = forecast(client, self.rates, self.config, self.company, self.budget, self.out)
        early, closing = client.requests[0][1], client.requests[2][1]
        self.assertEqual(early["instructions"], INSTRUCTIONS)
        self.assertNotIn("tool_choice", early)
        self.assertEqual(closing["tools"], TOOLS)
        self.assertEqual(closing["tool_choice"], "none")
        self.assertEqual(closing["reasoning"], early["reasoning"])
        self.assertIn("research phase has ended", closing["input"][-1]["content"])
        self.assertIn("T001", closing["input"][-1]["content"])
        self.assertEqual({k: client.requests[3][1][k] for k in closing}, closing)
        self.assertEqual(result["status"], "COMPLETED")

    def test_final_turn_rejects_tool_calls_without_execution(self):
        self.config["max_turns_per_company"] = 1
        call = {"type": "function_call", "call_id": "late", "name": "calculate", "arguments": '{"expression":"1+1"}'}
        client = OfflineClient([[call]])
        with self.assertRaises(ValueError):
            forecast(client, self.rates, self.config, self.company, self.budget, self.out)
        self.assertEqual(len(list(self.out.glob('*-tool-*.json'))), 0)
        self.assertFalse((self.out / "predictions.json").exists())
        self.assertFalse(self.budget.summary()["blocked"])

    def test_incomplete_prediction_schema_cannot_be_declared_complete(self):
        for text in ['{"predictions":[]}', '{"predictions":[{"target_id":"T001","predicted_value":"1 or 2"}]}',
                     '{"predictions":[{"target_id":"unknown","predicted_value":1}]}', 'not JSON']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                predictions_from_output([{"type": "message", "content": [{"type": "output_text", "text": text}]}], ["T001"])

    def test_final_request_does_not_mutate_preserved_history(self):
        history = [{"role": "user", "content": "public"}]
        before = copy.deepcopy(history)
        request = final_request(history, self.rates, ["T001"])
        self.assertEqual(history, before)
        self.assertEqual(request["input"][:-1], history)

    def test_timeout_preserves_reservation_without_retry(self):
        client = OfflineClient([TimeoutError("synthetic")])
        with self.assertRaises(TimeoutError):
            budgeted_response(client, {"model": self.rates["api_model"], "input": "x"},
                              self.rates, self.config, self.budget, self.out, 1)
        self.assertEqual(len(client.requests), 2)
        self.assertTrue(self.budget.summary()["blocked"])
        self.assertGreater(self.budget.summary()["unresolved_reserved_usd"], 0)

    def test_output_exhaustion_keeps_receipt_and_settles_known_usage_without_retry(self):
        client = OfflineClient([[]])
        original = client.post
        def exhausted(path, request):
            result = original(path, request)
            if not path.endswith("input_tokens"):
                result.update(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
                result["usage"].update(output_tokens=8192, total_tokens=8292,
                                       output_tokens_details={"reasoning_tokens": 8192})
            return result
        client.post = exhausted
        with self.assertRaises(RuntimeError):
            budgeted_response(client, {"model": self.rates["api_model"], "input": "x"},
                              self.rates, self.config, self.budget, self.out, 1)
        self.assertEqual(len(client.requests), 2)
        saved = json.loads((self.out / "01-response.json").read_text())
        self.assertEqual(saved["incomplete_details"], {"reason": "max_output_tokens"})
        self.assertFalse(self.budget.summary()["blocked"])
        self.assertGreater(self.budget.summary()["charged_upper_bound_usd"], 0)
        self.assertEqual(self.budget.summary()["unresolved_reserved_usd"], 0)
        self.assertFalse((self.out / "predictions.json").exists())

    def test_budget_rejection_precedes_generation(self):
        self.budget.reserve("existing", self.rates["api_model"], MODEL_CAP)
        self.budget.settle("existing", MODEL_CAP)
        client = OfflineClient([[]])
        with self.assertRaises(BudgetStop):
            budgeted_response(client, {"model": self.rates["api_model"], "input": "x"},
                              self.rates, self.config, self.budget, self.out, 1)
        self.assertEqual(len(client.requests), 1)  # Counter only, not generation.

    def test_unexpected_model_or_tier_cannot_release_reservation(self):
        client = OfflineClient([[]])
        original = client.post
        def changed(path, request):
            result = original(path, request)
            if not path.endswith("input_tokens"):
                result["model"] = "silent-fallback"
            return result
        client.post = changed
        with self.assertRaises(ValueError):
            budgeted_response(client, {"model": self.rates["api_model"], "input": "x"},
                              self.rates, self.config, self.budget, self.out, 1)
        self.assertTrue(self.budget.summary()["blocked"])


class ParentHistoryTest(unittest.TestCase):
    def setUp(self):
        FilingToolsTest.setUp(self)
        self.company["cik"] = "CIK0000003545"
        self.rates = json.loads(RUNTIME.read_text())["models"]["gpt-5.5"]
        self.parent = self.root / "parent"
        self.parent.mkdir()
        self.history = [{"role": "user", "content": self.data["questions.md"]},
                        {"type": "function_call", "call_id": "old", "name": "read_file"},
                        {"type": "function_call_output", "call_id": "old", "output": "public filing evidence"}]
        fixtures = {"identity.json": {"cik": self.company["cik"], "pilot_plan_sha256": PLAN_HASH,
                     "rates": self.rates, "source_commit": "a" * 40},
                    "24-request.json": {"payload": {"model": self.rates["api_model"], "input": self.history}},
                    "24-response.json": {"failed_final_marker": "must_not_enter_reused_history"}}
        receipts = []
        for name, value in fixtures.items():
            data = json.dumps(value).encode()
            (self.parent / name).write_bytes(data)
            receipts.append({"path": name, "sha256": digest(data)})
        summary = {"completed_model_turns": 23, "provider_incomplete_reason": "max_output_tokens",
                   "receipts": receipts, "tool_calls_by_name": {"read_file": 12, "search_files": 11}}
        (self.parent / "failure-summary.json").write_text(json.dumps(summary))
        self.summary_hash = digest((self.parent / "failure-summary.json").read_bytes())

    def tearDown(self):
        FilingToolsTest.tearDown(self)

    def test_only_pre_final_history_is_reused_with_explicit_provenance(self):
        history, provenance = parent_history(self.parent, self.company, self.rates, self.summary_hash)
        self.assertEqual(history, self.history)
        self.assertNotIn("must_not_enter_reused_history", json.dumps(history))
        self.assertEqual(provenance["reused_tool_calls"], 23)
        self.assertEqual(provenance["parent_summary_sha256"], self.summary_hash)
        self.assertEqual(provenance["parent_source_commit"], "a" * 40)

    def test_changed_summary_receipt_or_symlink_rejected(self):
        with self.assertRaises(ValueError):
            parent_history(self.parent, self.company, self.rates, "b" * 64)
        path = self.parent / "24-request.json"
        original = path.read_bytes()
        path.write_text("tampered")
        with self.assertRaises(ValueError):
            parent_history(self.parent, self.company, self.rates, self.summary_hash)
        path.write_bytes(original)
        path.unlink()
        path.symlink_to(self.root / "questions.md")
        with self.assertRaises(ValueError):
            parent_history(self.parent, self.company, self.rates, self.summary_hash)

    def test_cross_model_and_company_context_rejected(self):
        changed = dict(self.rates, api_model="other-model")
        with self.assertRaises(ValueError):
            parent_history(self.parent, self.company, changed, self.summary_hash)
        changed_company = dict(self.company, cik="another-company")
        with self.assertRaises(ValueError):
            parent_history(self.parent, changed_company, self.rates, self.summary_hash)


class RuntimeTimeoutTest(unittest.TestCase):
    def test_runtime_changes_only_authorized_timeout(self):
        repo = Path(__file__).resolve().parents[1]
        old_bytes = subprocess.run([
            "git", "show", "d346ddaa1062791692a4d58d3ea034ef436f6a81:benchmarks/edgar_forecast/openai_runtime.json"
        ], cwd=repo, check=True, capture_output=True).stdout
        timeout_bytes = subprocess.run([
            "git", "show", "98301b5a84582346c3a97f877bf2b26b424a4545:benchmarks/edgar_forecast/openai_runtime.json"
        ], cwd=repo, check=True, capture_output=True).stdout
        old, current = json.loads(old_bytes), json.loads(timeout_bytes)
        self.assertEqual(old.pop("request_timeout_seconds"), 60)
        self.assertEqual(current.pop("request_timeout_seconds"), 180)
        self.assertEqual(current, old)

    def test_runtime_changes_only_diagnosed_output_allowance(self):
        repo = Path(__file__).resolve().parents[1]
        old_bytes = subprocess.run([
            "git", "show", "23e30ad4cf664b45049056202ebc0c87a524985e:benchmarks/edgar_forecast/openai_runtime.json"
        ], cwd=repo, check=True, capture_output=True).stdout
        old, current = json.loads(old_bytes), json.loads(RUNTIME.read_text())
        self.assertEqual(old.pop("max_output_tokens"), 8192)
        self.assertEqual(current.pop("max_output_tokens"), 25000)
        self.assertEqual(current, old)

    def test_larger_output_keeps_existing_budget_reservation_bound(self):
        config = json.loads(RUNTIME.read_text())
        rates = config["models"]["gpt-5.5"]
        worst = config["max_input_tokens"] * unit(rates["input"]) + config["max_output_tokens"] * unit(rates["output"])
        self.assertEqual(worst, 1_250_000_000)
        self.assertLess(worst, MODEL_CAP)
        with tempfile.TemporaryDirectory() as directory:
            budget = PilotBudget(Path(directory) / "budget.sqlite3")
            try:
                budget.reserve("synthetic-output25000", rates["api_model"], worst)
                self.assertEqual(budget.summary()["unresolved_reserved_usd"], 1.25)
                self.assertEqual(budget.summary()["cap_usd"], 200)
                self.assertEqual(budget.summary()["model_cap_usd"], 10)
            finally:
                budget.close()

    def test_transport_uses_configured_wait_without_retry(self):
        response = Mock(status=200)
        response.read.return_value = b'{"status":"completed"}'
        response.getheader.return_value = "req_synthetic_timeout180"
        config = json.loads(RUNTIME.read_text())
        with patch("edgar_forecast_openai.http.client.HTTPSConnection") as connection:
            connection.return_value.getresponse.return_value = response
            result = OpenAIHTTP("synthetic-test-key", config["request_timeout_seconds"]).post(
                "/v1/responses", {"input": "public"})
            connection.assert_called_once_with("api.openai.com", timeout=180)
            connection.return_value.request.assert_called_once()
            connection.return_value.close.assert_called_once()
            self.assertEqual(result["status"], "completed")


class ProviderErrorTest(unittest.TestCase):
    def test_billing_codes_are_saved_without_raw_provider_message(self):
        for code in ["credit_balance_exhausted", "organization_spend_limit_exceeded", "project_spend_limit_exceeded", "organization_usage_limit_exceeded"]:
            self.assertEqual(ProviderHTTPError(429, "req_synthetic", code).detail["provider_code"], code)

    def test_http_error_receipt_omits_message_and_secret(self):
        response = Mock(status=429)
        response.read.return_value = json.dumps({"error": {"code": "insufficient_quota", "message": "DO_NOT_CAPTURE_SECRET"}}).encode()
        response.getheader.return_value = "req_synthetic_1"
        with patch("edgar_forecast_openai.http.client.HTTPSConnection") as connection:
            connection.return_value.getresponse.return_value = response
            with self.assertRaises(ProviderHTTPError) as caught:
                OpenAIHTTP("synthetic-test-key").post("/v1/responses", {"input": "public"})
            self.assertEqual(caught.exception.detail, {"http_status": 429, "provider_code": "insufficient_quota", "request_id": "req_synthetic_1"})
            self.assertNotIn("SECRET", str(caught.exception) + json.dumps(caught.exception.detail))
            self.assertEqual(connection.return_value.request.call_count, 1)
            connection.return_value.close.assert_called_once()

    def test_unknown_error_code_and_request_id_not_saved(self):
        error = ProviderHTTPError(403, "sk-secret-echo", "secret-echo")
        self.assertEqual(error.detail, {"http_status": 403, "provider_code": None, "request_id": None})

    def test_non_string_error_fields_not_saved(self):
        for code in (["insufficient_quota"], {"code": "insufficient_quota"}):
            error = ProviderHTTPError(429, ["req_synthetic_1"], code)
            self.assertEqual(error.detail, {"http_status": 429, "provider_code": None, "request_id": None})


if __name__ == "__main__":
    unittest.main()
