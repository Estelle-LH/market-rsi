"""CP2 Author: real capture/accounting on invented bytes, no network or grant.

Compose the existing CP1 raw HTTP fixture, not its TestCase, so inherited
Controller cases are not rediscovered as new Author evidence.
"""
from contextlib import ExitStack
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

import earnings_capacity_adapter as adapter
import earnings_capacity_task as task
import earnings_controller as controller
import earnings_entry as entry
import test_earnings_capacity_controller_transport as cp1
from edgar_forecast_budget import BudgetStop
from earnings_night_budget import history_snapshot
from earnings_loop_policy import LIMITS
from market_rsi import digest

DEADLINE_INIT = controller.DeadlineHTTP.__init__
PRIVATE = "CP2_PRIVATE_ERROR_TEXT_MUST_NOT_REACH_TERMINAL"
_DEFAULT = object()


class _AuthorFixture(cp1._TransportFixture):
    def __init__(self, owner, root):
        super().__init__(owner, root)
        self.slots = [str(self.root / "roles" / f"author-{i:02d}")
                      for i in range(1, 4)]
        self.context["schema"] = "earnings_capacity_author_transport_v1"
        self.context["slots"] = self.slots
        self.context_path = self.root / "author-context.json"
        self.context_binding = cp1._save(self.context_path, self.context)
        self.wall, self.monotonic = time.time(), time.monotonic()
        self.budget.clock = lambda: self.wall
        self.budget.monotonic = lambda: self.monotonic
        self.after_count = self.after_generation = None

    def bind_context(self, value):
        # These are temporary fixture inputs, never frozen experiment artifacts.
        self.context = deepcopy(value)
        self.context_path.write_bytes(cp1._wire(value))
        self.context_binding = cp1._pin(self.context_path)
        return self.context_binding

    def choice(self, axis="R", field="research_instructions"):
        component = {"research_instructions": "research_policy",
                     "reuse_facts": "memory_policy", "read_chunk_limit": "tool_interface",
                     "search_hit_limit": "tool_interface"}[field]
        return self.decision(axis, component)

    def payload(self, chosen=None, before=None, field="research_instructions"):
        chosen = self.choice() if chosen is None else chosen
        before = self.profiles[chosen["axis"]] if before is None else before
        after = deepcopy(before)
        after[field] = {"research_instructions": "Reconcile exact units and filing dates.",
                        "reuse_facts": False, "read_chunk_limit": 1500,
                        "search_hit_limit": 8}[field]
        return {"decision_sha256": digest(chosen), "source_text": "PROFILE = " + repr(after) + "\n",
                "test_text": "CASES = " + repr([{"field": field, "expected": after[field]}]) + "\n"}

    def response(self, payload=None):
        return super().response(self.payload() if payload is None else payload)

    def service(self, *, binding=None, budget=None, factory=None):
        return controller.CapacityAuthor(self.context_binding if binding is None else binding,
            budget=self.budget if budget is None else budget,
            client_factory=self.factory if factory is None else factory)

    def fake_connection(self, generation):
        parent = super().fake_connection(generation)
        fixture = self
        class Connection(parent):
            def getresponse(self):
                result = super().getresponse()
                callback = fixture.after_count if self.endpoint.endswith("input_tokens") else fixture.after_generation
                if callback is not None:
                    callback()
                return result
        return Connection

    def invoke(self, generation=None, *, chosen=None, before=_DEFAULT, slot=0, service=None):
        chosen = self.choice() if chosen is None else chosen
        before = self.profiles[chosen["axis"]] if before is _DEFAULT else before
        generation = self.response() if generation is None else generation
        if not isinstance(generation, (bytes, BaseException)):
            generation = cp1._wire(generation)
        def init_deadline(transport, client, **options):
            options.update(clock=lambda: self.wall, monotonic=lambda: self.monotonic)
            DEADLINE_INIT(transport, client, **options)
        with ExitStack() as stack:
            stack.enter_context(patch("earnings_http.http.client.HTTPSConnection",
                                      side_effect=self.fake_connection(generation)))
            stack.enter_context(patch.object(controller, "credential", side_effect=AssertionError("No credentials")))
            stack.enter_context(patch.object(controller, "NightBudget", side_effect=AssertionError("Owner budget only")))
            stack.enter_context(patch.object(controller.time, "time", side_effect=lambda: self.wall))
            stack.enter_context(patch.object(controller.time, "monotonic", side_effect=lambda: self.monotonic))
            stack.enter_context(patch.object(controller.DeadlineHTTP, "__init__", new=init_deadline))
            output = self.slots[slot] if type(slot) is int else slot
            return (self.service() if service is None else service).author(chosen, before, output)

    def rows(self):
        return self.budget.db.execute("SELECT reserved,charged,status FROM requests "
                                     "WHERE id!='fixture-prior' ORDER BY rowid").fetchall()


class CapacityAuthorTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cp2-author-transport-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def fixture(self, name):
        return _AuthorFixture(self, self.root / name)

    def assert_terminal(self, fixture, *, error_type=None):
        output = Path(fixture.slots[0])
        result = json.loads((output / "result.json").read_bytes())
        self.assertEqual(result["status"], "FAILED_NO_RETRY")
        self.assertIs(result["retry_allowed"], False)
        self.assertIs(result["model_authorship_verified"], False)
        self.assertEqual(result["evidence_scope"], "unverified_transport_component")
        if error_type is not None:
            self.assertEqual(result["error_type"], error_type)
        self.assertNotIn(PRIVATE, json.dumps(result))
        self.assertFalse((output / "candidate.json").exists())
        self.assertFalse((output / "decision.json").exists())
        return output

    def assert_paid_failure(self, fixture, response):
        raw = cp1._wire(response)
        with self.assertRaises(RuntimeError):
            fixture.invoke(raw)
        output = self.assert_terminal(fixture)
        self.assertEqual((output / "response.json").read_bytes(), (output / "01-response.json").read_bytes())
        self.assertEqual(fixture.rows(), [(20 * 2500 + 1024 * 10000, 92800, "settled")])
        self.assertEqual(len(fixture.calls), 2)
        _, prefix = fixture.intent_records()["/v1/responses"]
        self.assertEqual(prefix.with_suffix(".raw.bin").read_bytes(), raw)
        summary = json.loads((output / "budget-summary.json").read_bytes())
        self.assertEqual(summary["unresolved_reserved_usd"], 0)
        self.assertEqual(history_snapshot(fixture.budget.db, fixture.baseline["max_rowid"]), fixture.baseline)
        fixture.budget.active()
        originals, rows = fixture.originals(), fixture.rows()
        with self.assertRaises(FileExistsError):
            fixture.invoke(raw)
        self.assertEqual(fixture.originals(), originals)
        self.assertEqual(fixture.rows(), rows)
        fixture.factory.assert_called_once()
        self.assertTrue(all(connection.closed for connection in fixture.connections))

    def test_four_literal_components_capture_charge_and_reach_actual_task(self):
        cases = (("R", "research_instructions"), ("R", "reuse_facts"),
                 ("H", "read_chunk_limit"), ("H", "search_hit_limit"))
        for axis, field in cases:
            with self.subTest(axis=axis, field=field):
                fixture = self.fixture(field)
                chosen, before = fixture.choice(axis, field), fixture.profiles[axis]
                payload = fixture.payload(chosen, before, field)
                raw = cp1._wire(fixture.response(payload))
                with patch.object(fixture.budget, "close", wraps=fixture.budget.close) as closed:
                    binding = fixture.invoke(raw, chosen=chosen, before=before)
                    closed.assert_not_called()
                output = Path(fixture.slots[0])
                original = json.loads(entry.checked(binding))
                expected = adapter.author_candidate(original, before, chosen)
                self.assertEqual(task.EarningsTask().candidate(original, before, chosen), expected)
                self.assertEqual(binding, cp1._pin(output / "response.json"))
                self.assertEqual(entry.checked(binding), (output / "01-response.json").read_bytes())
                self.assertEqual(json.loads((output / "candidate.json").read_bytes()),
                                 {"candidate": expected, "original": binding})
                self.assertEqual(expected["author_sha256"], digest(payload))
                self.assertEqual(expected["source_sha256"], sha256(payload["source_text"].encode()).hexdigest())
                self.assertIs(expected["tests_executed"], False)
                self.assertFalse((output / "decision.json").exists())
                self.assertEqual(fixture.rows(), [(20 * 2500 + 1024 * 10000, 92800, "settled")])
                summary = json.loads((output / "budget-summary.json").read_bytes())
                self.assertAlmostEqual(summary["night_charged_upper_bound_usd"], 92800 / 1e9)
                self.assertEqual(summary["unresolved_reserved_usd"], 0)
                self.assertEqual(history_snapshot(fixture.budget.db, fixture.baseline["max_rowid"]), fixture.baseline)
                self.assertEqual(json.loads((output / "result.json").read_bytes())["status"], "COMPLETED_CANDIDATE")
                self.assertFalse(json.loads((output / "result.json").read_bytes())["model_authorship_verified"])
                self.assertEqual(len(fixture.calls), 2)
                self.assertTrue(all(connection.closed for connection in fixture.connections))
                fixture.factory.assert_called_once()
                fixture.budget.active()

    def test_request_three_exact_fields_no_tools_and_bound_decision_enum(self):
        fixture = self.fixture("request")
        chosen, before = fixture.choice(), deepcopy(fixture.profiles["R"])
        expected_chosen, expected_before = deepcopy(chosen), deepcopy(before)
        fixture.invoke(chosen=chosen, before=before)
        request, sent = fixture.calls[0][1], fixture.calls[1][1]
        self.assertEqual(chosen, expected_chosen)
        self.assertEqual(before, expected_before)
        self.assertEqual((request["tools"], request["tool_choice"], request["parallel_tool_calls"]), ([], "none", False))
        self.assertEqual(request["model"], cp1.MODEL)
        self.assertEqual(request["reasoning"], {"effort": "xhigh"})
        self.assertNotIn("max_output_tokens", request)
        self.assertEqual(sent, dict(request, max_output_tokens=1024, service_tier="default", store=False))
        form = request["text"]["format"]
        self.assertEqual(form["type"], "json_schema")
        self.assertIs(form["strict"], True)
        schema = form["schema"]
        self.assertEqual(set(schema["properties"]), {"decision_sha256", "source_text", "test_text"})
        self.assertEqual(set(schema["required"]), set(schema["properties"]))
        self.assertEqual(len(schema["required"]), 3)
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(schema["properties"]["decision_sha256"]["enum"], [digest(chosen)])
        safe = json.loads(request["input"][0]["content"])
        self.assertIn(expected_chosen, safe.values())
        self.assertIn(expected_before, safe.values())
        self.assertIn(digest(chosen), safe.values())
        self.assertEqual(request["input"][0]["role"], "user")
        reservation = json.loads((Path(fixture.slots[0]) / "01-request.json").read_bytes())
        self.assertEqual(reservation["payload"], request)
        intents = fixture.intent_records()
        count_intent, count_prefix = intents["/v1/responses/input_tokens"]
        send_intent, send_prefix = intents["/v1/responses"]
        self.assertEqual(count_intent["payload"], request)
        self.assertEqual(send_intent["payload"], sent)
        self.assertEqual(send_intent["complete_reservation"], reservation)
        self.assertEqual(send_intent["budget_request_id"], reservation["request_id"])
        self.assertEqual(send_intent["request_receipt_sha256"],
                         cp1._pin(Path(fixture.slots[0]) / "01-request.json")["sha256"])
        self.assertEqual(count_prefix.with_suffix(".raw.bin").read_bytes(), fixture.count_raw)
        self.assertFalse(send_intent["retry_allowed"])
        self.assertEqual(json.loads(send_prefix.with_suffix(".response.json").read_bytes()),
                         json.loads((Path(fixture.slots[0]) / "01-response.json").read_bytes()))

    def test_inputs_frozen_before_factory_mutates_callers_decision_and_profile(self):
        fixture = self.fixture("freeze")
        chosen, before = fixture.choice(), deepcopy(fixture.profiles["R"])
        frozen_choice, frozen_before = deepcopy(chosen), deepcopy(before)
        response = fixture.response(fixture.payload(frozen_choice, frozen_before))
        def mutate():
            chosen["component"] = "memory_policy"
            chosen["hypothesis"] = PRIVATE
            before["research_instructions"] = "Caller mutated after admission."
            return fixture.http
        fixture.factory.side_effect = mutate
        binding = fixture.invoke(response, chosen=chosen, before=before)
        request = fixture.calls[0][1]
        self.assertNotIn(PRIVATE, json.dumps(request))
        self.assertEqual(request["text"]["format"]["schema"]["properties"]["decision_sha256"]["enum"],
                         [digest(frozen_choice)])
        candidate = json.loads((Path(fixture.slots[0]) / "candidate.json").read_bytes())["candidate"]
        self.assertEqual(candidate, adapter.author_candidate(json.loads(entry.checked(binding)), frozen_before, frozen_choice))

    def test_split_text_one_final_message_passes_without_rewriting_original(self):
        fixture = self.fixture("split")
        response = fixture.response()
        text = response["output"][1]["content"][0]["text"]
        response["output"][1]["content"] = [{"type": "output_text", "text": text[:17]},
                                            {"type": "output_text", "text": text[17:]}]
        binding = fixture.invoke(response)
        self.assertEqual(json.loads(entry.checked(binding))["output"], response["output"])
        self.assertIsInstance(task.EarningsTask().candidate(json.loads(entry.checked(binding)),
                            fixture.profiles["R"], fixture.choice()), dict)

    def test_semantic_bad_payloads_pay_once_and_preserve_raw_alias(self):
        for name in ("wrong-digest", "extra", "missing", "malformed", "duplicate", "two-fields"):
            with self.subTest(case=name):
                fixture = self.fixture(name)
                response = fixture.response()
                payload = fixture.payload()
                if name == "wrong-digest": payload["decision_sha256"] = "c" * 64
                elif name == "extra": payload["private"] = PRIVATE
                elif name == "missing": del payload["test_text"]
                elif name == "two-fields":
                    after = dict(fixture.profiles["R"], research_instructions="new", reuse_facts=False)
                    payload["source_text"] = "PROFILE = " + repr(after)
                text = json.dumps(payload)
                if name == "malformed": text = "{" + PRIVATE
                elif name == "duplicate": text = text[:-1] + ', "decision_sha256":"' + digest(fixture.choice()) + '"}'
                response["output"][1]["content"][0]["text"] = text
                self.assert_paid_failure(fixture, response)

    def test_refusal_tool_incomplete_error_and_multiple_messages_pay_but_fail(self):
        for name in ("refusal", "function_call", "web_search_call", "unknown", "incomplete", "error", "two-messages"):
            with self.subTest(case=name):
                fixture = self.fixture(name)
                response = fixture.response()
                if name == "refusal": response["output"][1]["content"] = [{"type": "refusal", "refusal": PRIVATE}]
                elif name in ("function_call", "web_search_call", "unknown"):
                    response["output"].append({"type": name, "arguments": PRIVATE})
                elif name == "incomplete": response["status"] = "incomplete"
                elif name == "error": response["error"] = {"message": PRIVATE}
                else: response["output"].append(deepcopy(response["output"][1]))
                self.assert_paid_failure(fixture, response)

    def test_legacy_business_json_is_not_an_actual_transport_response(self):
        fixture = self.fixture("legacy-output")
        legacy = fixture.payload()
        # Usage is valid so the shared original transport charges before semantic admission.
        response = dict(legacy, model=cp1.MODEL, service_tier="default", usage=fixture.response()["usage"])
        self.assert_paid_failure(fixture, response)

    def test_generation_timeout_is_uncertain_no_refund_retry_or_budget_close(self):
        fixture = self.fixture("timeout")
        with patch.object(fixture.budget, "close", wraps=fixture.budget.close) as closed:
            with self.assertRaises(RuntimeError): fixture.invoke(TimeoutError(PRIVATE))
            closed.assert_not_called()
        output = self.assert_terminal(fixture, error_type="TimeoutError")
        self.assertFalse((output / "response.json").exists())
        self.assertFalse((output / "01-response.json").exists())
        self.assertEqual(fixture.rows(), [(20 * 2500 + 1024 * 10000, 0, "uncertain")])
        summary = json.loads((output / "budget-summary.json").read_bytes())
        self.assertTrue(summary["blocked"])
        self.assertGreater(summary["unresolved_reserved_usd"], 0)
        originals, rows = fixture.originals(), fixture.rows()
        with self.assertRaises(FileExistsError): fixture.invoke(TimeoutError(PRIVATE))
        self.assertEqual(fixture.originals(), originals)
        self.assertEqual(fixture.rows(), rows)
        with self.assertRaises(BudgetStop): fixture.invoke(slot=1)
        self.assertFalse(Path(fixture.slots[1]).exists())
        self.assertEqual(len(fixture.calls), 2)
        self.assertNotIn(PRIVATE, (output / "result.json").read_text())
        failed = list(output.glob("http-*.failed.json"))
        self.assertEqual(len(failed), 1)
        self.assertEqual(json.loads(failed[0].read_bytes()), {"exception_type": "TimeoutError", "retry_allowed": False})

    def test_invalid_raw_json_preserves_wire_and_uncertain_reservation(self):
        fixture = self.fixture("invalid-wire")
        raw = b'{"status":"completed", "status":"completed"}'
        with self.assertRaises(RuntimeError): fixture.invoke(raw)
        output = self.assert_terminal(fixture, error_type="ValueError")
        _, prefix = fixture.intent_records()["/v1/responses"]
        self.assertEqual(prefix.with_suffix(".raw.bin").read_bytes(), raw)
        self.assertEqual(fixture.rows(), [(20 * 2500 + 1024 * 10000, 0, "uncertain")])
        self.assertFalse((output / "01-response.json").exists())

    def test_successful_slot_is_consumed_without_rewriting_any_original(self):
        fixture = self.fixture("replay")
        service = fixture.service()
        fixture.invoke(service=service)
        originals, rows = fixture.originals(), fixture.rows()
        with self.assertRaises(FileExistsError): fixture.invoke(service=service)
        self.assertEqual(fixture.originals(), originals)
        self.assertEqual(fixture.rows(), rows)
        self.assertEqual(len(fixture.calls), 2)
        fixture.factory.assert_called_once()

    def test_continue_and_invalid_decisions_refuse_before_factory_or_slot(self):
        fixture = self.fixture("invalid-chosen")
        choice = fixture.choice()
        cases = [dict(choice, axis="continue", component="none"), dict(choice, schema="wrong"),
                 dict(choice, axis="H", component="research_policy"), dict(choice, hypothesis=""),
                 dict(choice, parent_pair_sha256="short"), dict(choice, feedback_sha256=True),
                 dict(choice, extra=PRIVATE)]
        for chosen in cases:
            with self.subTest(chosen=chosen), self.assertRaises(ValueError):
                fixture.invoke(chosen=chosen, before=fixture.profiles["R"])
        fixture.factory.assert_not_called()
        self.assertFalse(Path(fixture.slots[0]).exists())
        self.assertEqual(fixture.rows(), [])

    def test_invalid_before_profiles_refuse_before_factory_or_slot(self):
        fixture = self.fixture("invalid-before")
        before = fixture.profiles["R"]
        cases = [dict(before, axis="H"), dict(before, reuse_facts=1),
                 dict(before, research_instructions="x" * 2201), dict(before, extra=PRIVATE),
                 {"axis": "R", "research_instructions": "incomplete"}, None, "PROFILE = {}"]
        service = fixture.service()
        for value in cases:
            with self.subTest(profile=value), self.assertRaises(ValueError):
                fixture.invoke(service=service, before=value)
        fixture.factory.assert_not_called()
        self.assertFalse(Path(fixture.slots[0]).exists())
        self.assertEqual(fixture.rows(), [])

    def test_context_schema_source_rates_limits_clocks_and_fields_are_exact(self):
        fixture = self.fixture("bad-context")
        base = deepcopy(fixture.context)
        cases = [dict(base, schema="earnings_capacity_controller_transport_v1"),
                 dict(base, source_commit="short"), dict(base, source_commit=True),
                 dict(base, extra=True), dict(base, root="relative"), dict(base, slots=[]),
                 dict(base, slots=[base["slots"][0]] * 2),
                 dict(base, cutoff_monotonic=True), dict(base, cutoff_monotonic=-1),
                 dict(base, rates=dict(base["rates"], output="0"))]
        for field, ceiling in LIMITS.items():
            for bad in (True, 0, -1, 1.0, str(ceiling), ceiling + 1):
                cases.append(dict(base, limits=dict(base["limits"], **{field: bad})))
        for name in base:
            value = deepcopy(base)
            del value[name]
            cases.append(value)
        for index, value in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(ValueError):
                fixture.service(binding=fixture.bind_context(value))
        fixture.factory.assert_not_called()
        self.assertEqual(fixture.rows(), [])

    def test_binding_hash_noncanonical_path_and_symlink_refuse_before_factory(self):
        fixture = self.fixture("bad-binding")
        cases = [dict(fixture.context_binding, sha256="f" * 64),
                 dict(fixture.context_binding, path="author-context.json"),
                 dict(fixture.context_binding, extra=True), {"path": fixture.context_binding["path"]}]
        for value in cases:
            with self.subTest(binding=value), self.assertRaises(ValueError): fixture.service(binding=value)
        alias = fixture.root / "context-alias.json"
        alias.symlink_to(fixture.context_path)
        with self.assertRaises(ValueError): fixture.service(binding=dict(fixture.context_binding, path=str(alias)))
        fixture.factory.assert_not_called()
        self.assertEqual(fixture.rows(), [])

    def test_explicit_budget_factory_required_no_fallback(self):
        fixture = self.fixture("dependencies")
        with self.assertRaises(TypeError): controller.CapacityAuthor(fixture.context_binding, budget=fixture.budget)
        with self.assertRaises(TypeError): controller.CapacityAuthor(fixture.context_binding, client_factory=fixture.factory)
        with self.assertRaises(ValueError): controller.CapacityAuthor(fixture.context_binding, budget=None, client_factory=fixture.factory)
        with self.assertRaises(ValueError): controller.CapacityAuthor(fixture.context_binding, budget=fixture.budget, client_factory=None)
        fixture.factory.assert_not_called()
        self.assertEqual(fixture.rows(), [])

    def test_undeclared_noncanonical_and_outside_slots_refuse_before_factory(self):
        fixture = self.fixture("slots")
        service = fixture.service()
        candidates = [str(fixture.root / "roles" / "author-04"), str(self.root / "outside"),
                      str(fixture.root / "roles") + "/../roles/author-01", "roles/author-01"]
        for output in candidates:
            with self.subTest(slot=output), self.assertRaises(ValueError): fixture.invoke(service=service, slot=output)
        fixture.factory.assert_not_called()
        self.assertFalse(Path(fixture.slots[0]).exists())
        self.assertEqual(fixture.rows(), [])

    def test_slot_and_ancestor_symlinks_refuse_without_touching_target(self):
        for kind in ("slot", "ancestor"):
            with self.subTest(kind=kind):
                fixture = self.fixture("symlink-" + kind)
                service = fixture.service()
                outside = self.root / ("outside-" + kind)
                outside.mkdir()
                link = Path(fixture.slots[0]) if kind == "slot" else fixture.root / "roles"
                link.parent.mkdir(exist_ok=True)
                link.symlink_to(outside, target_is_directory=True)
                with self.assertRaises(ValueError): fixture.invoke(service=service)
                fixture.factory.assert_not_called()
                self.assertEqual(list(outside.iterdir()), [])
                self.assertEqual(fixture.rows(), [])

    def test_context_drift_after_constructor_refuses_before_claim(self):
        fixture = self.fixture("context-before")
        service = fixture.service()
        fixture.context_path.write_bytes(fixture.context_path.read_bytes() + b" ")
        with self.assertRaises(ValueError): fixture.invoke(service=service)
        fixture.factory.assert_not_called()
        self.assertFalse(Path(fixture.slots[0]).exists())

    def test_context_drift_during_budget_active_refuses_before_factory(self):
        fixture = self.fixture("context-active")
        service = fixture.service()
        active = fixture.budget.active
        def drift():
            active()
            fixture.context_path.write_bytes(fixture.context_path.read_bytes() + b" ")
        with patch.object(fixture.budget, "active", side_effect=drift), self.assertRaises(RuntimeError):
            fixture.invoke(service=service)
        self.assert_terminal(fixture, error_type="ValueError")
        fixture.factory.assert_not_called()
        self.assertEqual(fixture.rows(), [])

    def test_context_drift_between_count_generation_keeps_uncertain_reservation(self):
        fixture = self.fixture("context-after-count")
        fixture.after_count = lambda: fixture.context_path.write_bytes(fixture.context_path.read_bytes() + b" ")
        with self.assertRaises(RuntimeError): fixture.invoke()
        output = self.assert_terminal(fixture, error_type="ValueError")
        self.assertEqual([endpoint for endpoint, _ in fixture.calls], ["/v1/responses/input_tokens"])
        self.assertTrue((output / "01-request.json").exists())
        self.assertEqual(fixture.rows(), [(20 * 2500 + 1024 * 10000, 0, "uncertain")])

    def test_expired_original_wall_monotonic_and_budget_cutoff_refuse_before_claim(self):
        for kind in ("wall", "monotonic", "budget"):
            with self.subTest(kind=kind):
                fixture = self.fixture("expired-" + kind)
                ctx = deepcopy(fixture.context)
                if kind == "wall": ctx["cutoff_utc"] = "2000-01-01T00:00:00Z"
                elif kind == "monotonic": ctx["cutoff_monotonic"] = fixture.monotonic - 1
                else: fixture.budget.monotonic_deadline = fixture.monotonic - 1
                fixture.bind_context(ctx)
                with self.assertRaises(BudgetStop): fixture.invoke()
                fixture.factory.assert_not_called()
                self.assertFalse(Path(fixture.slots[0]).exists())
                self.assertEqual(fixture.rows(), [])

    def test_http_timeouts_clip_to_external_budget_and_rollout_windows(self):
        for kind in ("budget", "rollout"):
            with self.subTest(kind=kind):
                fixture = self.fixture("timeouts-" + kind)
                if kind == "budget": fixture.budget.monotonic_deadline = fixture.monotonic + 5
                else: fixture.bind_context(dict(fixture.context, limits=dict(fixture.limits, wall_seconds=5)))
                fixture.after_count = lambda: setattr(fixture, "monotonic", fixture.monotonic + 2)
                fixture.invoke()
                self.assertGreater(fixture.connections[0].timeout, 0)
                self.assertLessEqual(fixture.connections[0].timeout, 5)
                self.assertGreater(fixture.connections[1].timeout, 0)
                self.assertLessEqual(fixture.connections[1].timeout, 3)

    def test_cutoff_between_count_generation_prevents_paid_send(self):
        for kind in ("monotonic", "rollout"):
            with self.subTest(kind=kind):
                fixture = self.fixture("between-" + kind)
                if kind == "monotonic": fixture.bind_context(dict(fixture.context, cutoff_monotonic=fixture.monotonic + 5))
                else: fixture.bind_context(dict(fixture.context, limits=dict(fixture.limits, wall_seconds=5)))
                fixture.after_count = lambda: setattr(fixture, "monotonic", fixture.monotonic + 6)
                with self.assertRaises(RuntimeError): fixture.invoke()
                output = self.assert_terminal(fixture, error_type="BudgetStop")
                self.assertEqual([endpoint for endpoint, _ in fixture.calls], ["/v1/responses/input_tokens"])
                self.assertFalse((output / "01-response.json").exists())

    def test_late_generation_is_charged_and_captured_but_not_accepted(self):
        fixture = self.fixture("late-generation")
        fixture.budget.monotonic_deadline = fixture.monotonic + 5
        fixture.after_generation = lambda: setattr(fixture, "monotonic", fixture.monotonic + 6)
        with self.assertRaises(RuntimeError): fixture.invoke()
        output = self.assert_terminal(fixture, error_type="BudgetStop")
        self.assertEqual((output / "response.json").read_bytes(), (output / "01-response.json").read_bytes())
        self.assertEqual(fixture.rows()[0][1:], (92800, "settled"))

    def test_summary_crossing_cutoff_prevents_terminal_candidate_acceptance(self):
        fixture = self.fixture("late-summary")
        fixture.bind_context(dict(fixture.context, cutoff_monotonic=fixture.monotonic + 5))
        summary = fixture.budget.summary
        def late():
            value = summary()
            fixture.monotonic += 6
            return value
        with patch.object(fixture.budget, "summary", side_effect=late), self.assertRaises(RuntimeError): fixture.invoke()
        output = self.assert_terminal(fixture, error_type="BudgetStop")
        self.assertTrue((output / "budget-summary.json").exists())
        self.assertEqual((output / "response.json").read_bytes(), (output / "01-response.json").read_bytes())
        self.assertEqual(fixture.rows()[0][1:], (92800, "settled"))

    def test_summary_failure_cannot_return_candidate_and_never_closes_caller_budget(self):
        fixture = self.fixture("summary-error")
        with patch.object(fixture.budget, "summary", side_effect=ValueError(PRIVATE)), \
             patch.object(fixture.budget, "close", wraps=fixture.budget.close) as closed, self.assertRaises(RuntimeError):
            fixture.invoke()
        closed.assert_not_called()
        self.assert_terminal(fixture, error_type="ValueError")
        self.assertEqual(fixture.rows()[0][1:], (92800, "settled"))


if __name__ == "__main__":
    unittest.main()
