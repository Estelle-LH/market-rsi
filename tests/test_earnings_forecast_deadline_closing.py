"""Independent offline deadline tests; synthetic clocks/transport, real budget path.

The capacity worker/native/state fixtures contain invented public data only.
No provider, production ledger, scorer, candidate host execution or saved QA.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import edgar_forecast_openai as forecast
from edgar_forecast_budget import BudgetStop, PilotBudget
from earnings_entry import ReceiptHTTP
import test_earnings_capacity_worker as workers
import test_earnings_capacity_forecast as entry_fixture


POLICY = {"schema": "capacity_forecast_closing_policy_v1", "reserve_seconds": 600,
          "deadline_source": "original_native_absolute_monotonic",
          "scope": "capacity_forecasts_only", "history_policy": "retain_all",
          "retry_allowed": False}


def answer(value=100):
    return [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(
        {"predictions": [{"target_id": "T001", "predicted_value": value}]})}]}]


class ScriptedHTTP:
    """Only the external HTTP service is scripted; all reservations are real."""
    def __init__(self, outputs, *, counts=None, generation_hook=None):
        self.outputs = iter(outputs)
        self.counts = iter(counts) if counts is not None else None
        self.calls = []
        self.generation_hook = generation_hook

    def post(self, endpoint, payload):
        self.calls.append((endpoint, deepcopy(payload)))
        if endpoint.endswith("input_tokens"):
            count = 100 if self.counts is None else next(self.counts)
            if isinstance(count, BaseException):
                raise count
            return {"input_tokens": count}
        output = next(self.outputs)
        if isinstance(output, BaseException):
            raise output
        if self.generation_hook:
            self.generation_hook()
        return {"model": payload["model"], "service_tier": "default", "status": "completed",
                "output": output, "usage": {"input_tokens": 100, "output_tokens": 10,
                "total_tokens": 110, "input_tokens_details": {"cached_tokens": 0}}}


class DeadlineClosingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = workers.CapacityWorkerTests(
            "test_forecast_calls_fact_tool_and_cold_next_worker_uses_record")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.worker = self.fixture.worker()
        self.output = self.fixture.root / "deadline-transport"
        self.output.mkdir()
        self.config = dict(self.fixture.config, max_turns_per_company=24,
                           company_wall_seconds=1800, max_input_tokens=100000,
                           max_output_tokens=25000)
        self.rates = dict(self.fixture.rate, input="2", cached=".1", write="2.5", output="10")
        self.now = [1000.0]
        self.budget = PilotBudget(self.fixture.root / "invented-deadline-budget.sqlite3")
        self.addCleanup(self.budget.close)

    def invoke(self, client, *, deadline=1600.0, worker=True, config=None):
        options = {} if deadline is None else {"capacity_deadline_monotonic": deadline}
        with patch.object(forecast.time, "monotonic", side_effect=lambda: self.now[0]):
            return forecast.forecast(ReceiptHTTP(client, self.output), self.rates,
                self.config if config is None else config, self.fixture.company,
                self.budget, self.output,
                capacity_worker=self.worker if worker else None, **options)

    def rows(self):
        return self.budget.db.execute("SELECT reserved,charged,status FROM requests").fetchall()

    def closing(self, turn=1):
        return json.loads((self.output / f"{turn:02d}-deadline-closing.json").read_text())

    def test_exact_600_boundary_closes_through_original_count_reserve_send(self):
        config, rates = deepcopy(self.config), deepcopy(self.rates)
        client = ScriptedHTTP([answer()])
        with patch.object(forecast, "budgeted_response", wraps=forecast.budgeted_response) as send:
            result = self.invoke(client)
        self.assertEqual((result["status"], result["turns"]), ("COMPLETED", 1))
        self.assertEqual(send.call_count, 1)
        self.assertEqual([p for p, _ in client.calls], ["/v1/responses/input_tokens", "/v1/responses"])
        count_request, physical = client.calls[0][1], client.calls[1][1]
        self.assertEqual(count_request["tool_choice"], "none")
        self.assertEqual(physical, dict(count_request, max_output_tokens=25000,
                                       service_tier="default", store=False))
        self.assertEqual(count_request["input"][:-1], self.worker.context["messages"])
        receipt = json.loads((self.output / "01-request.json").read_text())
        self.assertEqual(receipt["payload"], count_request)
        self.assertEqual(self.rows(), [(100 * 2500 + 25000 * 10000, 350000, "settled")])
        closing = self.closing()
        self.assertEqual(closing["policy"], POLICY)
        self.assertEqual((closing["reason"], closing["remaining_seconds"]), ("time_reserve", 600.0))
        self.assertEqual((closing["deadline_monotonic"], closing["checked_monotonic"]), (1600.0, 1000.0))
        self.assertFalse(closing["turn_ceiling_also_reached"])
        self.assertEqual((self.config, self.rates), (config, rates))
        self.assertTrue((self.output / "research-state-output.json").exists())

    def test_above_boundary_keeps_research_and_does_not_invent_closing_record(self):
        client = ScriptedHTTP([answer()])
        self.invoke(client, deadline=1600.000001)
        self.assertNotIn("tool_choice", client.calls[0][1])
        self.assertFalse((self.output / "01-deadline-closing.json").exists())
        self.assertTrue((self.output / "01-research-count.json").exists())
        self.assertEqual(self.config["max_turns_per_company"], 24)

    def test_original_outer_deadline_includes_start_setup(self):
        start = self.worker.start
        def slow_start(output):
            value = start(output)
            self.now[0] += 450
            return value
        with patch.object(self.worker, "start", side_effect=slow_start):
            self.invoke(ScriptedHTTP([answer()]), deadline=2000.0)
        self.assertEqual(self.closing()["remaining_seconds"], 550.0)
        self.assertEqual(self.closing()["deadline_monotonic"], 2000.0)

    def test_integrity_check_time_is_consumed_before_request_selection(self):
        check, seen = self.worker._check, [0]
        def slow_check():
            check()
            seen[0] += 1
            if seen[0] == 2:  # start() checks first; first-turn check is next.
                self.now[0] += 450
        with patch.object(self.worker, "_check", side_effect=slow_check):
            self.invoke(ScriptedHTTP([answer()]), deadline=2000.0)
        self.assertEqual(self.closing()["checked_monotonic"], 1450.0)
        self.assertEqual(self.closing()["remaining_seconds"], 550.0)

    def test_later_closing_preserves_initial_context_and_entire_tool_history(self):
        original = deepcopy(self.worker.context["messages"])
        call = {"type": "function_call", "call_id": "invented-read", "name": "read_file",
                "arguments": json.dumps({"path": "filing_index.tsv", "offset": 0, "characters": 20})}
        client = ScriptedHTTP([[call], answer()], generation_hook=lambda: self.now.__setitem__(0, 1400.0))
        result = self.invoke(client, deadline=2000.0)
        self.assertEqual(result["turns"], 2)
        generations = [payload for endpoint, payload in client.calls if endpoint == "/v1/responses"]
        first, final = generations
        observation = json.loads(next(self.output.glob("01-tool-*.json")).read_text())
        self.assertEqual(first["input"], original)
        self.assertEqual(final["input"][:-1], [*original, call, observation])
        self.assertEqual(final["input"][-2]["call_id"], "invented-read")
        self.assertEqual(final["tool_choice"], "none")
        self.assertEqual(final["model"], first["model"])
        self.assertEqual(final["reasoning"], first["reasoning"])
        self.assertEqual(self.closing(2)["history_items"], len(original) + 2)
        self.assertFalse((self.output / "01-deadline-closing.json").exists())

    def test_expiry_inside_integrity_check_never_counts_or_reserves(self):
        check, seen = self.worker._check, [0]
        def expire():
            check(); seen[0] += 1
            if seen[0] == 2:
                self.now[0] = 1600.0
        client = ScriptedHTTP([])
        with patch.object(self.worker, "_check", side_effect=expire), self.assertRaises(BudgetStop):
            self.invoke(client)
        self.assertEqual(client.calls, [])
        self.assertEqual(self.rows(), [])
        self.assertFalse((self.output / "predictions.json").exists())

    def test_invalid_standalone_expired_and_extended_deadlines_fail_closed(self):
        for value in (True, False, "1600", {}, [], float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.invoke(ScriptedHTTP([]), deadline=value)
        for value in (999.0, 1000.0):
            with self.subTest(expired=value), self.assertRaises(BudgetStop):
                self.invoke(ScriptedHTTP([]), deadline=value)
        with self.assertRaises(ValueError):
            self.invoke(ScriptedHTTP([]), deadline=2800.000001)
        with self.assertRaises(ValueError):
            self.invoke(ScriptedHTTP([]), deadline=1600.0, worker=False)
        self.assertEqual(self.rows(), [])

    def test_strict_final_decoder_refuses_tools_or_missing_targets_without_retry(self):
        missing = [{"type": "message", "content": [{"type": "output_text",
                    "text": '{"predictions":[]}'}]}]
        for number, output in enumerate(([{"type": "function_call", "call_id": "must-not-run",
            "name": "read_file", "arguments": "{}"}], answer(True), missing)):
            with self.subTest(output=number):
                self.output = self.fixture.root / f"strict-final-{number}"
                self.output.mkdir()
                client = ScriptedHTTP([output])
                with patch.object(self.worker, "dispatch") as dispatch, self.assertRaises(ValueError):
                    self.invoke(client)
                dispatch.assert_not_called()
                self.assertEqual(len(client.calls), 2)
                self.assertFalse((self.output / "predictions.json").exists())
        self.assertEqual([r[2] for r in self.rows()], ["settled"] * 3)

    def test_final_count_error_or_overflow_never_dispatches_or_retries(self):
        for number, count in enumerate((TimeoutError("synthetic original count timeout"), 100001)):
            self.output = self.fixture.root / f"failed-final-count-{number}"
            self.output.mkdir()
            client = ScriptedHTTP([], counts=[count])
            with self.subTest(count=count), self.assertRaises((TimeoutError, BudgetStop)):
                self.invoke(client)
            self.assertEqual(len(client.calls), 1)
            self.assertFalse((self.output / "01-request.json").exists())
        self.assertEqual(self.rows(), [])

    def test_generation_failure_retains_original_uncertainty_without_retry(self):
        client = ScriptedHTTP([TimeoutError("invented original generation timeout")])
        with self.assertRaises(TimeoutError):
            self.invoke(client)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(self.rows()[0][2], "uncertain")
        self.assertTrue(self.budget.summary()["blocked"])

    def test_no_deadline_capacity_and_standalone_keep_ordinary_behavior(self):
        for number, worker in enumerate((True, False)):
            self.output = self.fixture.root / f"ordinary-{number}"
            self.output.mkdir()
            client = ScriptedHTTP([answer()])
            self.invoke(client, deadline=None, worker=worker)
            self.assertNotIn("tool_choice", client.calls[0][1])
            self.assertFalse(list(self.output.glob("*-deadline-closing.json")))
        self.assertEqual(len(self.rows()), 2)

    def test_last_turn_and_original_headroom_remain_independent_triggers(self):
        client = ScriptedHTTP([answer()])
        self.invoke(client, deadline=2000.0, config=dict(self.config, max_turns_per_company=1))
        self.assertEqual(client.calls[0][1]["tool_choice"], "none")
        self.assertFalse(list(self.output.glob("*-deadline-closing.json")))
        self.output = self.fixture.root / "original-headroom"; self.output.mkdir()
        client = ScriptedHTTP([answer()], counts=[70904, 71000])
        self.invoke(client, deadline=2000.0)
        self.assertEqual(len(client.calls), 3)
        self.assertTrue((self.output / "01-finalization.json").exists())
        self.assertFalse(list(self.output.glob("*-deadline-closing.json")))


class EntryDeadlineBindingTests(unittest.TestCase):
    def test_original_entry_passes_existing_minimum_deadline_after_setup_without_renewal(self):
        fixture = entry_fixture._ForecastFixture(self)
        opened_at = fixture.monotonic
        fixture.budget.monotonic_deadline = opened_at + 700
        expected = fixture.budget.monotonic_deadline
        observed = {}
        def factory():
            fixture.monotonic += 120  # Synthetic client setup after hard was captured.
            return fixture.http
        fixture.factory.side_effect = factory
        def capture(*args, **kwargs):
            observed.update(kwargs)
            raise RuntimeError("inert stop before forecast/scorer/network")
        # Kernel admission is an explicit inert seam: this case tests the
        # entry-to-forecast deadline argument, not scoring/admission itself.
        with patch.object(entry_fixture.entry, "forecast", side_effect=capture), \
             patch.object(entry_fixture.measurement, "kernel", return_value=(None, None, [])):
            with self.assertRaisesRegex(RuntimeError, "Capacity forecast failed once") as raised:
                fixture.invoke(replies=[])
        self.assertEqual(str(raised.exception.__cause__), "inert stop before forecast/scorer/network")
        self.assertEqual(observed["capacity_deadline_monotonic"], expected)
        self.assertEqual(observed["capacity_deadline_monotonic"] - fixture.monotonic, 580)
        self.assertIsInstance(observed["capacity_worker"], entry_fixture.CapacityWorker)
        self.assertEqual(fixture.calls, [])
        self.assertEqual(fixture.rows(), [])


ARCHIVED_REPLAY_EVIDENCE = {}


class Original25PublicHistoryTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("MARKET_RSI_VERIFY_FORECAST25_CLOSING") == "1",
                         "Explicit read-only original25 public-history opt-in required")
    def test_original_19th_research_turn_has_room_but_needs_time_closing(self):
        root = Path("/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/"
                    "edgar-population-20261016/attempts/edgar-population-20261016-25/"
                    "roles/forecast-01-00")
        pins = {
            "19-request.json": "0181b06c72b261090ac2e8d949c711855b08557cb66fd35f22954f851dd13244",
            "19-count.json": "40d3b6a314ea0fc421b288ecbeb0ef13fa9e642d2384a927c88d8a706fd50e27",
            "19-response.json": "6be32e6e9eca0ccf17a5b25b56ad2fa363e638ee17d09dca7261bf6289db565b",
            "19-tool-dbe1d3e2f643.json": "a6946fa8b598df5b5c532f801307e252ad4bc038073194d5ee6371461abf9b7d"}
        bindings, values = {}, {}
        for name, expected in pins.items():
            path = root / name
            self.assertEqual(path.resolve(), path)
            self.assertFalse(path.is_symlink())
            data = path.read_bytes()
            actual = hashlib.sha256(data).hexdigest()
            self.assertEqual(actual, expected)
            bindings[name] = {"path": str(path), "sha256": actual}
            values[name] = json.loads(data)
        original_request = values["19-request.json"]["payload"]
        response = values["19-response.json"]
        observation = values["19-tool-dbe1d3e2f643.json"]
        self.assertEqual(values["19-count.json"]["input_tokens"], 44549)
        self.assertLess(44549, 100000)
        self.assertNotEqual(original_request.get("tool_choice"), "none")
        self.assertFalse(forecast.forecast_finalization_needed(44549, {
            "max_input_tokens": 100000, "max_output_tokens": 25000}))
        responses = sorted(root.glob("[0-9][0-9]-response.json"))
        self.assertEqual(len(responses), 19)
        response_bindings = []
        for path in responses:
            data = path.read_bytes()
            value = json.loads(data)
            self.assertEqual(value["status"], "completed")
            self.assertEqual(value["model"], original_request["model"])
            response_bindings.append({"path": str(path), "sha256": hashlib.sha256(data).hexdigest()})
        self.assertFalse((root / "predictions.json").exists())
        calls = [item for item in response["output"] if item.get("type") == "function_call"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(observation["type"], "function_call_output")
        self.assertEqual(observation["call_id"], calls[0]["call_id"])
        # Only item.type is examined for opaque reasoning. Its content is not
        # rendered/inspected; this is explicitly a full PUBLIC-history replay.
        public = lambda items: [item for item in items if item.get("type") != "reasoning"]
        history = [*public(original_request["input"]), *public(response["output"]), observation]
        before = deepcopy(history)
        targets = [target for item in history if item.get("role") == "user"
                   and type(item.get("content")) is str
                   for target in re.findall(r"^### (T\d+) \|", item["content"], re.M)]
        self.assertEqual(targets, [f"T{number:03d}" for number in range(1, 6)])
        rates = {"api_model": original_request["model"],
                 "effort": original_request["reasoning"]["effort"]}
        closed = forecast.final_request(history, rates, targets)
        self.assertEqual(closed["input"][:-1], history)
        self.assertEqual(history, before)
        self.assertEqual(closed["tool_choice"], "none")
        self.assertFalse(closed["parallel_tool_calls"])
        self.assertEqual(closed["model"], original_request["model"])
        self.assertEqual(closed["reasoning"], original_request["reasoning"])
        self.assertTrue(all(target in closed["input"][-1]["content"] for target in targets))
        self.assertEqual(forecast.capacity_forecast_closing_policy(), POLICY)
        ARCHIVED_REPLAY_EVIDENCE.update(bindings=bindings, responses=response_bindings,
            historical_input_tokens=44549, original_input_ceiling=100000,
            historical_completed_generations=19, original_tool_choice_not_none=True,
            original_predictions_present=False, public_history_items=len(history),
            latest_research_tool_calls=len(calls), targets=targets,
            exact_public_history_preserved=True, new_provider_or_token_count=False,
            new_forecast_or_score=False, opaque_reasoning_content_inspected=False)


if __name__ == "__main__":
    unittest.main()
