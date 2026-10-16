"""CP1 synthetic Responses transport: owned ledgers, captured bytes, no network."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "research" / "market_rsi"))

import earnings_controller as controller
import earnings_entry as entry
from edgar_forecast_budget import PilotBudget, BudgetStop
from edgar_forecast_full_budget import FullBudget, activate
from earnings_http import RawOpenAIHTTP
from earnings_night_budget import NightBudget, history_snapshot
from supervisor_harness import feedback_linked_loop as driver


MODEL = "gpt-6.1-sol"
SOURCE_COMMIT = "0f8f514740159bccd5df4a3b3c72f87938e3e9d7"
FIELDS = {"schema", "axis", "component", "parent_pair_sha256",
          "feedback_sha256", "hypothesis", "expected_effect"}
PRIVATE = "CP1_PRIVATE_LABEL_OR_PATH_MUST_NOT_REACH_REQUEST"


def _pin(path):
    return {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}


def _save(path, value):
    entry.durable_json(path, value)
    return _pin(path)


def _wire(value):
    # Deliberate whitespace proves wire originals are not parsed/reserialized.
    return (json.dumps(value, ensure_ascii=False, indent=3) + "\n\n").encode()


class _TransportFixture:
    """A single owned temporary ledger and a two-endpoint fake HTTP exchange."""

    def __init__(self, owner, root):
        self.root = root.resolve()
        self.root.mkdir()
        self.ledger = self.root / "synthetic-owned.sqlite3"
        prior = PilotBudget(self.ledger)
        try:
            prior.reserve("fixture-prior", MODEL, 10000)
            prior.settle("fixture-prior", 1000)
        finally:
            prior.close()
        activate(self.ledger, "a" * 64, SOURCE_COMMIT)
        full = FullBudget(self.ledger)
        try:
            self.baseline = history_snapshot(full.db)
        finally:
            full.close()
        self.cutoff = time.monotonic() + 300
        self.budget = NightBudget(self.ledger, baseline=self.baseline,
            deadline_utc="2099-01-01T00:00:00Z", captured_deadline=self.cutoff)
        owner.addCleanup(self.budget.close)
        self.rates = {"api_model": MODEL, "effort": "xhigh", "input": "2",
                      "cached": ".1", "write": "2.5", "output": "10"}
        self.limits = {"max_input_tokens": 10000, "max_output_tokens": 1024,
                       "wall_seconds": 60}
        self.slots = [str(self.root / "roles" / f"controller-{i:02d}")
                      for i in range(1, 4)]
        self.context = {"schema": "earnings_capacity_controller_transport_v1",
            "source_commit": SOURCE_COMMIT, "root": str(self.root),
            "rates": self.rates, "limits": self.limits,
            "cutoff_utc": "2099-01-01T00:00:00Z",
            "cutoff_monotonic": self.cutoff, "slots": self.slots}
        self.context_binding = _save(self.root / "context.json", self.context)
        packet = {"task_id": "invented-earnings-fixture",
            "parent_feedback_sha256": "b" * 64, "parent_pair_sha256": "a" * 64,
            "questions": "Five invented historical filing questions.",
            "feedback": {"observation": {
                "prediction": {"planned_targets": 5, "scored_targets": 0,
                               "score_out_of_5": None},
                "execution": {"status": "FAILED_NO_RETRY", "turns": 24,
                              "tool_calls": 23, "error_type": "ValueError"},
                "cik": "invented-company"}, "baseline_score_out_of_5": 1.5},
            "prior_recipe": None}
        self.profiles = {
            "R": {"axis": "R", "research_instructions": "Reconcile filing units.",
                  "reuse_facts": True},
            "H": {"axis": "H", "read_chunk_limit": 1000, "search_hit_limit": 20}}
        self.prompt = controller.capacity_input(packet, self.profiles)
        self.calls = []
        self.connections = []
        self.count_raw = _wire({"object": "response.input_tokens", "input_tokens": 20})
        # Empty value is intentional: no key lookup or real credential is used.
        self.http = RawOpenAIHTTP("", 600)
        self.factory = Mock(side_effect=lambda: self.http)

    def decision(self, axis="R", component=None):
        return {"schema": "earnings_capacity_decision_v1", "axis": axis,
            "component": component or {"R": "research_policy", "H": "tool_interface",
                                       "continue": "none"}[axis],
            "parent_pair_sha256": self.prompt["parent_pair_sha256"],
            "feedback_sha256": self.prompt["feedback_sha256"],
            "hypothesis": "Reconcile units before accepting an estimate.",
            "expected_effect": "Reduce inconsistent invented-unit calculations."}

    def response(self, decision=None):
        return {"id": "resp_invented_capacity", "object": "response",
            "created_at": 1791928800, "status": "completed", "error": None,
            "incomplete_details": None, "model": MODEL, "service_tier": "default",
            "usage": {"input_tokens": 12, "output_tokens": 7, "total_tokens": 19,
                      "input_tokens_details": {"cached_tokens": 3},
                      "output_tokens_details": {"reasoning_tokens": 2}},
            "output": [{"id": "rs_fixture", "type": "reasoning", "summary": []},
                {"id": "msg_fixture", "type": "message", "status": "completed",
                 "role": "assistant", "content": [{"type": "output_text",
                    "text": json.dumps(self.decision() if decision is None else decision),
                    "annotations": []}]}]}

    def service(self):
        return controller.CapacityController(self.context_binding,
            budget=self.budget, client_factory=self.factory)

    def fake_connection(self, generation):
        fixture = self

        class Connection:
            def __init__(self, host, timeout):
                if host != "api.openai.com":
                    raise AssertionError("Unexpected fake HTTP host")
                self.timeout, self.closed = timeout, False
                fixture.connections.append(self)

            def request(self, method, endpoint, body, headers):
                expected = ["/v1/responses/input_tokens", "/v1/responses"]
                if method != "POST" or len(fixture.calls) >= len(expected):
                    raise AssertionError("Unexpected HTTP call or retry")
                if endpoint != expected[len(fixture.calls)]:
                    raise AssertionError("Count/generation order differs")
                self.endpoint = endpoint
                fixture.calls.append((endpoint, json.loads(body)))

            def getresponse(self):
                if self.endpoint.endswith("input_tokens"):
                    raw = fixture.count_raw
                elif isinstance(generation, BaseException):
                    raise generation
                else:
                    raw = generation
                return Mock(status=200, getheader=Mock(return_value="req_cp1_fixture"),
                            read=Mock(side_effect=lambda limit: raw[:limit]))

            def close(self):
                self.closed = True

        return Connection

    def invoke(self, generation, *, prompt=None, slot=0, service=None):
        if not isinstance(generation, (bytes, BaseException)):
            generation = _wire(generation)
        # Guard every fake exchange against implicit credential/budget fallbacks.
        with patch("earnings_http.http.client.HTTPSConnection",
                   side_effect=self.fake_connection(generation)), \
             patch.object(controller, "credential", side_effect=AssertionError("No credentials")), \
             patch.object(controller, "NightBudget", side_effect=AssertionError("Externally owned budget")):
            return (service or self.service()).propose(
                deepcopy(self.prompt if prompt is None else prompt), self.slots[slot])

    def originals(self, slot=0):
        root = Path(self.slots[slot])
        return {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}

    def intent_records(self, slot=0):
        result = {}
        for path in Path(self.slots[slot]).glob("http-*.intent.json"):
            row = json.loads(path.read_bytes())
            prefix = path.name.removesuffix(".intent.json")
            result[row["endpoint"]] = (row, path.with_name(prefix))
        return result


class CapacityControllerTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cp1-controller-transport-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def fixture(self, name):
        return _TransportFixture(self, self.root / name)

    def assert_settled_failure(self, fixture, response):
        raw = _wire(response)
        with self.assertRaises(RuntimeError):
            fixture.invoke(raw)
        output = Path(fixture.slots[0])
        self.assertEqual([p for p, _ in fixture.calls],
                         ["/v1/responses/input_tokens", "/v1/responses"])
        self.assertEqual((output / "response.json").read_bytes(),
                         (output / "01-response.json").read_bytes())
        self.assertFalse((output / "decision.json").exists())
        result = json.loads((output / "result.json").read_bytes())
        self.assertEqual(result["status"], "FAILED_NO_RETRY")
        self.assertIsInstance(result["error_type"], str)
        self.assertIs(result["model_authorship_verified"], False)
        self.assertNotIn(PRIVATE, (output / "result.json").read_text())
        intents = fixture.intent_records()
        self.assertEqual(len(intents), 2)
        _, prefix = intents["/v1/responses"]
        self.assertEqual(prefix.with_suffix(".raw.bin").read_bytes(), raw)
        self.assertEqual(fixture.budget.db.execute(
            "SELECT charged,status FROM requests WHERE id!='fixture-prior'").fetchall(),
            [(92800, "settled")])
        summary = json.loads((output / "budget-summary.json").read_bytes())
        self.assertEqual(summary["unresolved_reserved_usd"], 0)
        self.assertAlmostEqual(summary["night_charged_upper_bound_usd"], 92800 / 1e9)
        self.assertEqual(history_snapshot(fixture.budget.db, fixture.baseline["max_rowid"]),
                         fixture.baseline)
        fixture.budget.active()  # The owner still has its open, settled handle.
        self.assertTrue(all(connection.closed for connection in fixture.connections))

    def test_request_strict_seven_fields_no_tools_and_feedback_whitelist(self):
        fixture = self.fixture("builder")
        prompt = deepcopy(fixture.prompt)
        prompt["private"] = PRIVATE
        prompt["feedback"]["gold"] = PRIVATE
        prompt["feedback"]["observation"]["prediction"]["target_values"] = PRIVATE
        prompt["feedback"]["observation"]["execution"]["path"] = "/private/" + PRIVATE
        original_prompt = deepcopy(prompt)
        request = controller.capacity_request(prompt, fixture.rates)
        self.assertEqual(prompt, original_prompt)
        self.assertEqual((request["tools"], request["tool_choice"],
                          request["parallel_tool_calls"]), ([], "none", False))
        self.assertEqual(request["model"], MODEL)
        self.assertEqual(request["reasoning"], {"effort": "xhigh"})
        self.assertNotIn(PRIVATE, json.dumps(request))
        self.assertEqual(len(request["input"]), 1)
        self.assertEqual(request["input"][0]["role"], "user")
        safe = json.loads(request["input"][0]["content"])
        self.assertEqual(safe, fixture.prompt)
        self.assertEqual(safe["profiles"], fixture.profiles)
        self.assertEqual(safe["feedback_sha256"], safe["parent_feedback_sha256"])
        self.assertEqual(safe["parent_pair_sha256"], "a" * 64)
        self.assertEqual(safe["feedback"]["baseline_score_out_of_5"], 1.5)
        form = request["text"]["format"]
        self.assertEqual(form["type"], "json_schema")
        self.assertEqual(form["name"], "earnings_capacity_decision_v1")
        self.assertIs(form["strict"], True)
        schema = form["schema"]
        self.assertEqual(schema["type"], "object")
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(set(schema["properties"]), FIELDS)
        self.assertEqual(set(schema["required"]), FIELDS)
        self.assertEqual(len(schema["required"]), 7)
        self.assertTrue(all(value["type"] == "string" for value in schema["properties"].values()))
        self.assertEqual(set(schema["properties"]["axis"]["enum"]), {"R", "H", "continue"})
        self.assertNotIn("max_output_tokens", request)

    def test_R_H_continue_preserve_raw_alias_derived_decision_and_exact_charge(self):
        for axis in ("R", "H", "continue"):
            with self.subTest(axis=axis):
                fixture = self.fixture(axis)
                choice = fixture.decision(axis)
                raw = _wire(fixture.response(choice))
                with patch.object(fixture.budget, "close", wraps=fixture.budget.close) as closed:
                    binding = fixture.invoke(raw)
                    closed.assert_not_called()
                output = Path(fixture.slots[0])
                self.assertEqual(binding, _pin(output / "response.json"))
                self.assertEqual(entry.checked(binding), (output / "01-response.json").read_bytes())
                self.assertEqual(json.loads((output / "decision.json").read_bytes()),
                                 {"decision": choice, "original": binding})
                self.assertEqual(controller.parse_capacity_decision(
                    json.loads(entry.checked(binding)), fixture.prompt), choice)
                count_request, sent_request = fixture.calls[0][1], fixture.calls[1][1]
                self.assertEqual(count_request, controller.capacity_request(fixture.prompt, fixture.rates))
                self.assertEqual(sent_request, dict(count_request, max_output_tokens=1024,
                                                   service_tier="default", store=False))
                reservation = json.loads((output / "01-request.json").read_bytes())
                self.assertEqual(reservation["payload"], count_request)
                self.assertEqual(reservation["reserved_nano_usd"], 20 * 2500 + 1024 * 10000)
                intents = fixture.intent_records()
                count_intent, count_prefix = intents["/v1/responses/input_tokens"]
                send_intent, send_prefix = intents["/v1/responses"]
                self.assertEqual(count_intent["payload"], count_request)
                self.assertEqual(send_intent["payload"], sent_request)
                self.assertEqual(send_intent["complete_reservation"], reservation)
                self.assertEqual(send_intent["budget_request_id"], reservation["request_id"])
                self.assertEqual(send_intent["request_receipt_sha256"],
                                 _pin(output / "01-request.json")["sha256"])
                self.assertFalse(count_intent["retry_allowed"])
                self.assertFalse(send_intent["retry_allowed"])
                self.assertEqual(count_prefix.with_suffix(".raw.bin").read_bytes(), fixture.count_raw)
                self.assertEqual(send_prefix.with_suffix(".raw.bin").read_bytes(), raw)
                self.assertEqual(json.loads(send_prefix.with_suffix(".response.json").read_bytes()),
                                 json.loads((output / "01-response.json").read_bytes()))
                self.assertEqual(fixture.budget.db.execute(
                    "SELECT id,model,reserved,charged,status FROM requests WHERE id!='fixture-prior'"
                ).fetchall(), [(reservation["request_id"], MODEL,
                               reservation["reserved_nano_usd"], 92800, "settled")])
                summary = json.loads((output / "budget-summary.json").read_bytes())
                self.assertEqual(summary["unresolved_reserved_usd"], 0)
                self.assertAlmostEqual(summary["night_charged_upper_bound_usd"], 92800 / 1e9)
                result = json.loads((output / "result.json").read_bytes())
                self.assertNotEqual(result["status"], "FAILED_NO_RETRY")
                self.assertIs(result["model_authorship_verified"], False)
                self.assertIn("unverified", json.dumps(result).lower())
                self.assertTrue(all(connection.closed for connection in fixture.connections))
                self.assertEqual(len(fixture.connections), 2)
                fixture.factory.assert_called_once()
                fixture.budget.active()

    def test_malformed_duplicate_extra_or_missing_decision_settles_original_usage(self):
        for name in ("malformed", "duplicate", "extra", "missing"):
            with self.subTest(name=name):
                fixture = self.fixture(name)
                response = fixture.response()
                item = response["output"][1]["content"][0]
                if name == "malformed":
                    item["text"] = "{" + PRIVATE
                elif name == "duplicate":
                    item["text"] = item["text"][:-1] + ', "axis":"H"}'
                elif name == "extra":
                    item["text"] = json.dumps(dict(fixture.decision(), extra=PRIVATE))
                else:
                    choice = fixture.decision()
                    del choice["hypothesis"]
                    item["text"] = json.dumps(choice)
                self.assert_settled_failure(fixture, response)

    def test_refusal_tool_incomplete_and_error_responses_keep_settled_originals(self):
        for name in ("content-refusal", "item-refusal", "function_call",
                     "custom_tool_call", "incomplete", "error"):
            with self.subTest(name=name):
                fixture = self.fixture(name)
                response = fixture.response()
                if name == "content-refusal":
                    response["output"][1]["content"] = [{"type": "refusal", "refusal": PRIVATE}]
                elif name == "item-refusal":
                    response["output"].append({"type": "refusal", "refusal": PRIVATE})
                elif name in ("function_call", "custom_tool_call"):
                    response["output"].append({"type": name, "call_id": "call_invented",
                        "name": "must_never_execute", "arguments": PRIVATE})
                elif name == "incomplete":
                    response["status"] = "incomplete"
                    response["incomplete_details"] = {"reason": "max_output_tokens"}
                else:
                    response["error"] = {"code": "invented_error", "message": PRIVATE}
                self.assert_settled_failure(fixture, response)

    def test_lineage_and_component_rejections_keep_settled_originals(self):
        for name in ("parent", "feedback", "wrong-component", "continue-component"):
            with self.subTest(name=name):
                fixture = self.fixture(name)
                choice = fixture.decision()
                if name == "parent":
                    choice["parent_pair_sha256"] = "c" * 64
                elif name == "feedback":
                    choice["feedback_sha256"] = "c" * 64
                elif name == "wrong-component":
                    choice["component"] = "tool_interface"
                else:
                    choice["axis"] = "continue"
                self.assert_settled_failure(fixture, fixture.response(choice))

    def test_builtin_unknown_or_malformed_output_items_are_terminal_paid_failures(self):
        cases = (
            ("web-search", {"id": "ws_fixture", "type": "web_search_call",
                "status": "completed", "action": {"type": "search", "query": PRIVATE}}),
            ("file-search", {"id": "fs_fixture", "type": "file_search_call",
                "status": "completed", "queries": [PRIVATE], "results": []}),
            ("code-interpreter", {"id": "ci_fixture", "type": "code_interpreter_call",
                "status": "completed", "container_id": "fixture_container",
                "code": PRIVATE, "outputs": []}),
            ("computer", {"id": "cu_fixture", "type": "computer_call",
                "status": "completed", "call_id": "call_fixture",
                "action": {"type": "screenshot"}, "pending_safety_checks": []}),
            ("unknown-type", {"type": "future_unknown_output", "payload": PRIVATE}),
            ("missing-type", {"id": "malformed_fixture", "payload": PRIVATE}),
            ("non-string-type", {"type": 42, "payload": PRIVATE}),
            ("null-item", None),
            ("string-item", PRIVATE),
            ("list-item", [PRIVATE]),
        )
        for name, item in cases:
            with self.subTest(name=name):
                fixture = self.fixture("output-v3-" + name)
                response = fixture.response()
                response["output"].insert(1, deepcopy(item))
                self.assert_settled_failure(fixture, response)
                originals = fixture.originals()
                ledger = fixture.budget.db.execute("SELECT * FROM requests ORDER BY id").fetchall()
                with self.assertRaises(FileExistsError):
                    fixture.invoke(response)
                self.assertEqual(fixture.originals(), originals)
                self.assertEqual(fixture.budget.db.execute(
                    "SELECT * FROM requests ORDER BY id").fetchall(), ledger)
                self.assertEqual(len(fixture.calls), 2)
                self.assertEqual(len(fixture.connections), 2)
                fixture.factory.assert_called_once()
                terminal = json.loads(originals["result.json"])
                self.assertFalse(terminal["retry_allowed"])
                self.assertNotIn(PRIVATE, json.dumps(terminal))

    def test_generation_transport_failure_remains_uncertain_and_sanitized(self):
        fixture = self.fixture("timeout")
        with self.assertRaises(RuntimeError):
            fixture.invoke(TimeoutError(PRIVATE))
        output = Path(fixture.slots[0])
        self.assertEqual([path for path, _ in fixture.calls],
                         ["/v1/responses/input_tokens", "/v1/responses"])
        self.assertEqual(len(fixture.connections), 2)
        self.assertFalse((output / "01-response.json").exists())
        self.assertFalse((output / "response.json").exists())
        self.assertFalse((output / "decision.json").exists())
        self.assertEqual(fixture.budget.db.execute(
            "SELECT reserved,charged,status FROM requests WHERE id!='fixture-prior'"
        ).fetchall(), [(20 * 2500 + 1024 * 10000, 0, "uncertain")])
        summary = json.loads((output / "budget-summary.json").read_bytes())
        self.assertGreater(summary["unresolved_reserved_usd"], 0)
        self.assertTrue(summary["blocked"])
        result = json.loads((output / "result.json").read_bytes())
        self.assertEqual(result["status"], "FAILED_NO_RETRY")
        self.assertEqual(result["error_type"], "TimeoutError")
        self.assertNotIn(PRIVATE, json.dumps(result))
        failures = list(output.glob("http-*.failed.json"))
        self.assertEqual(len(failures), 1)
        self.assertNotIn(PRIVATE, failures[0].read_text())
        self.assertEqual(json.loads(failures[0].read_bytes())["exception_type"], "TimeoutError")
        with self.assertRaises(BudgetStop):
            fixture.budget.active()

    def test_failed_transport_controller_halts_driver_before_any_subsequent_role(self):
        fixture = self.fixture("driver")
        service = fixture.service()
        response = fixture.response(dict(fixture.decision(), feedback_sha256="c" * 64))
        downstream = []

        def input_stage(context):
            return {"packet": deepcopy(fixture.prompt)}

        def controller_stage(context):
            original = fixture.invoke(response, prompt=context["outputs"]["input"]["packet"],
                                      service=service)
            return {"original": original, "artifacts": [original]}

        def later(context):
            downstream.append(context["outputs"])
            return {}

        handlers = {name: later for name in driver.STAGES}
        handlers.update(input=input_stage, controller=controller_stage)
        identity = {name: {"fixture_handler": name, "controller_source": _pin(Path(controller.__file__))}
                    for name in driver.STAGES}
        kwargs = {"seed": {"fixture": "closed-controller-failure"}, "admit": lambda context: True,
                  "max_rounds": 1, "handler_identity": lambda: deepcopy(identity)}
        loop = fixture.root / "loop"
        with self.assertRaises(driver.LoopHalted):
            driver.run(loop, handlers, **kwargs)
        originals = fixture.originals()
        ledger = fixture.budget.db.execute("SELECT * FROM requests ORDER BY id").fetchall()
        with self.assertRaises(driver.LoopHalted):
            driver.run(loop, handlers, **kwargs)
        self.assertEqual(downstream, [])
        self.assertEqual(len(fixture.calls), 2)
        self.assertEqual(fixture.originals(), originals)
        self.assertEqual(fixture.budget.db.execute("SELECT * FROM requests ORDER BY id").fetchall(), ledger)
        self.assertTrue((loop / "round-0001-controller.failed.json").is_file())
        self.assertFalse((loop / "round-0001-implement.claim.json").exists())
        self.assertEqual(json.loads(originals["budget-summary.json"])["unresolved_reserved_usd"], 0)
        self.assertEqual(originals["response.json"], originals["01-response.json"])


if __name__ == "__main__":
    unittest.main()
