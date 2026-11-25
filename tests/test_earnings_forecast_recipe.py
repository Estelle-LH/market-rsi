"""Original forecaster recipe delivery on synthetic files/provider/ledger only."""
import ast
import copy
import inspect
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import edgar_forecast_openai as worker
from edgar_forecast_budget import PilotBudget
from edgar_forecast_model_pilot import digest
from earnings_entry import ReceiptHTTP

FROZEN = "4abaea576b5e5797070793dcf0778b3328218271"
RECIPE = {"schema": "earnings_research_recipe_v1", "task_id": "synthetic-task",
          "parent_feedback_sha256": "a" * 64,
          "research_instructions": "Use calculate to evaluate 100 + 23."}


class Provider:
    """Input-dependent fake choice; never presented as genuine model authorship."""
    def __init__(self):
        self.requests, self.turns = [], 0

    def post(self, endpoint, request):
        self.requests.append((endpoint, copy.deepcopy(request)))
        if endpoint.endswith("input_tokens"):
            return {"input_tokens": 100}
        self.turns += 1
        if self.turns == 1:
            use_recipe = any("Use calculate" in i.get("content", "") for i in request["input"] if i.get("role") == "user")
            name = "calculate" if use_recipe else "read_file"
            args = {"expression": "100 + 23"} if use_recipe else {"path": "filing_index.tsv", "offset": 0, "characters": 100}
            output = [{"type": "function_call", "call_id": "synthetic-action", "name": name, "arguments": json.dumps(args)}]
        else:
            text = '{"predictions":[{"target_id":"T001","predicted_value":123}]}'
            output = [{"type": "message", "content": [{"type": "output_text", "text": text}]}]
        return {"model": request["model"], "service_tier": "default", "status": "completed", "output": output,
                "usage": {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110, "input_tokens_details": {"cached_tokens": 0}}}


class ForecastRecipeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        files = {"questions.md": "### T001 | invented test quantity",
                 "filing_index.tsv": "date_filed\tform_type\taccession\tpath\n2026-01-01\t10-Q\told\tfilings/10-Q_old.md\n",
                 "filings/10-Q_old.md": "invented test quantity 100"}
        self.company = {"visible_root": str(self.root), "cutoff": "2026-02-01", "target_accession": "not-visible", "allowed_files": []}
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            self.company["allowed_files"].append({"path": name, "bytes": len(text.encode()), "sha256": digest(text.encode())})
        self.config = {"max_input_tokens": 100000, "max_output_tokens": 25000, "final_max_output_tokens": 65536,
                       "max_turns_per_company": 2, "company_wall_seconds": 1800}
        self.rates = {"api_model": "gpt-6.1-sol", "effort": "xhigh", "input": "2", "cached": "0.1", "write": "2.5", "output": "10"}

    def run_forecast(self, name, operation=worker.forecast, **kwargs):
        output = self.root / name
        output.mkdir()
        budget = PilotBudget(output / "synthetic.sqlite3")
        self.addCleanup(budget.close)
        provider = Provider()
        before = copy.deepcopy((self.rates, self.config, self.company, kwargs))
        result = operation(ReceiptHTTP(provider, output), self.rates, self.config, self.company, budget, output, **kwargs)
        self.assertEqual((self.rates, self.config, self.company, kwargs), before)
        self.assertEqual((result["status"], result["turns"], result["tool_calls"]), ("COMPLETED", 2, 1))
        return provider, budget, output

    def test_omitted_and_none_match_frozen_original_physical_payloads(self):
        source = subprocess.run(["git", "show", FROZEN + ":tools/edgar_forecast_openai.py"], cwd=ROOT, check=True, capture_output=True).stdout
        names = {"forecast", "final_request", "turn_config", "budgeted_response", "unit", "token", "predictions_from_output"}
        nodes = [n for n in ast.parse(source).body if (isinstance(n, ast.FunctionDef) and n.name in names)
                 or (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "INSTRUCTIONS" for t in n.targets))]
        namespace = dict(vars(worker))
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "<frozen-forecaster>", "exec"), namespace)
        original, _, _ = self.run_forecast("frozen", namespace["forecast"])
        default, _, _ = self.run_forecast("default")
        explicit, _, _ = self.run_forecast("none", research_recipe=None)
        self.assertEqual(original.requests, default.requests)
        self.assertEqual([json.dumps(p).encode() for _, p in original.requests], [json.dumps(p).encode() for _, p in explicit.requests])
        self.assertEqual(inspect.signature(worker.forecast).parameters["research_recipe"].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_canonical_recipe_reaches_count_reservation_wire_and_final_history(self):
        provider, budget, output = self.run_forecast("child", research_recipe=copy.deepcopy(RECIPE))
        reordered, _, _ = self.run_forecast("reordered", research_recipe=dict(reversed(list(RECIPE.items()))))
        self.assertEqual(provider.requests[0][1]["input"], reordered.requests[0][1]["input"])
        first, final = provider.requests[1][1], provider.requests[3][1]
        self.assertEqual(len(first["input"]), 2)
        message = first["input"][1]
        self.assertEqual(set(message), {"role", "content"})
        self.assertEqual(message["role"], "user")
        self.assertIn(json.dumps(RECIPE, sort_keys=True, separators=(",", ":"), ensure_ascii=False), message["content"])
        self.assertIn(message, final["input"])
        self.assertEqual(first["instructions"], worker.INSTRUCTIONS)
        self.assertNotIn("tool_choice", first)
        self.assertEqual(final["tool_choice"], "none")
        self.assertEqual(first["tools"], final["tools"])
        self.assertEqual(first["reasoning"], final["reasoning"])
        for turn in (1, 2):
            count, full = provider.requests[(turn - 1) * 2][1], provider.requests[(turn - 1) * 2 + 1][1]
            self.assertEqual({k: full[k] for k in count}, count)
            record = json.loads((output / f"{turn:02d}-request.json").read_text())
            self.assertEqual(record["payload"], count)
            self.assertEqual(record["reserved_nano_usd"], 100 * worker.unit("2.5") + full["max_output_tokens"] * worker.unit("10"))
            intents = [json.loads(p.read_text()) for p in output.glob("http-*.intent.json")]
            self.assertEqual([i["payload"] for i in intents if i.get("budget_request_id") == record["request_id"]], [full])
        self.assertEqual([p["max_output_tokens"] for e, p in provider.requests if e == "/v1/responses"], [25000, 65536])
        observation = next(i for i in final["input"] if i.get("type") == "function_call_output")
        self.assertEqual(json.loads(observation["output"]), {"value": 123.0})
        self.assertEqual(budget.summary()["generation_requests_reserved"], 2)
        self.assertFalse(budget.summary()["blocked"])

    def test_invalid_or_oversized_recipe_refuses_before_provider(self):
        from unittest.mock import Mock
        bad = ["not-a-dict", {}, dict(RECIPE, extra=1), dict(RECIPE, schema="wrong"),
               dict(RECIPE, parent_feedback_sha256="bad"), dict(RECIPE, research_instructions=""),
               dict(RECIPE, research_instructions="   "), dict(RECIPE, task_id="x" * 8192),
               dict(RECIPE, research_instructions="x" * 2201), dict(RECIPE, research_instructions="😀" * 1200)]
        for index, value in enumerate(bad):
            with self.subTest(index=index):
                client = Mock()
                with self.assertRaises(ValueError):
                    worker.forecast(client, self.rates, self.config, self.company, Mock(), self.root, research_recipe=value)
                client.post.assert_not_called()

    def test_exact_instruction_character_and_utf8_boundaries_remain_accepted(self):
        for instructions in ("x" * 2000, "x" * 2027, "x" * 2200, "😀" * 1024):
            with self.subTest(characters=len(instructions)):
                value = dict(RECIPE, research_instructions=instructions)
                before = copy.deepcopy(value)
                message = worker.research_recipe_message(value)
                self.assertIn(instructions, message["content"])
                self.assertLessEqual(len(message["content"].encode()), 8192)
                self.assertEqual(value, before)


if __name__ == "__main__":
    unittest.main()
