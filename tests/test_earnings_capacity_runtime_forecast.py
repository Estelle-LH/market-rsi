"""CP3b actual borrowed services and forecast-only resources on invented fixtures.

Review is a resource stand-in. The captured real Author candidate is not adopted
here: the native worker uses separately selected literal fixture profiles.
"""
from copy import deepcopy
import inspect
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_earnings_capacity_runtime as owner
import test_earnings_capacity_forecast as cp3
import earnings_capacity_runtime as runtime
import earnings_controller as controller
import earnings_entry as entry
from earnings_loop_policy import LIMITS
from earnings_night_budget import history_snapshot
from market_rsi import digest

COUNT, GENERATE = "/v1/responses/input_tokens", "/v1/responses"


def controller_factory(context_binding, *, budget, client_factory):
    return controller.CapacityController(context_binding, budget=budget, client_factory=client_factory).propose


def author_factory(context_binding, *, budget, client_factory):
    return controller.CapacityAuthor(context_binding, budget=budget, client_factory=client_factory).author


def review_factory(context_binding, *, budget, client_factory):
    return owner.Review(context_binding, budget=budget, client_factory=client_factory).invoke


class CapacityRuntimeForecastTests(unittest.TestCase):
    def setUp(self):
        self.case = owner.CapacityRuntimeOwnerTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def fixture(self, name, *, original_update=None):
        # Reuse CP3's data/native worker/scorer/raw fixture, closing its unused
        # setup budget once before the actual runtime owner can be opened.
        cleanups = []
        class CleanupCollector:
            def addCleanup(self, callback, *args, **kwargs):
                cleanups.append((callback, args, kwargs))
        raw = cp3._ForecastFixture(CleanupCollector())
        for callback, args, kwargs in cleanups:
            if getattr(callback, "__self__", None) is raw.budget:
                callback(*args, **kwargs)
            else:
                self.addCleanup(callback, *args, **kwargs)
        if original_update:
            raw.set_original_runtime(original_update)
        fixture = self.case.fixture("forecast-runtime-" + name)
        raw.rewrite_study(dict(raw.study, sole_ledger=str(fixture.ledger)))
        def forecast_factory(context_binding, *, budget, client_factory):
            context = entry.strict_json(entry.checked(context_binding).decode())
            clock_binding = entry.strict_json((Path(context["root"]) / "clock.binding.json").read_text())
            return entry.CapacityForecast(context_binding, budget=budget, client_factory=client_factory,
                study_binding=raw.study_binding, evaluation_kernel=raw.kernel, clock_binding=clock_binding).forecast
        fixture.factories = {"controller": controller_factory, "author": author_factory,
                             "review": review_factory, "forecast": forecast_factory}
        fixture.raw = raw
        fixture.rates = deepcopy(raw.rate)
        fixture.slots["forecast"] = [str(fixture.root / "roles" / f"forecast-{n:02d}") for n in range(1, 7)]
        fixture.spec.update(schema="earnings_capacity_runtime_v2", rates=fixture.rates,
                            forecast_study=deepcopy(raw.study_binding))
        fixture.limits["forecast"] = raw.limits()
        fixture.spec["sources"].update(forecast_entry=owner._pin(entry.__file__),
            forecaster=owner._pin(inspect.getsourcefile(entry.forecast)))
        fixture.spec["sources"].update({"factory_" + role: owner._pin(inspect.getsourcefile(factory))
                                        for role, factory in fixture.factories.items()})
        fixture.binding = owner._save(fixture.home / "v2-runtime-spec.json", fixture.spec)
        return fixture

    def exchange(self, fixture, replies, *, high_from=0):
        base = fixture.raw.fake_connection(replies)
        raw_fixture = fixture.raw
        class Connection(base):
            def getresponse(self):
                result = super().getresponse()
                if self.endpoint == COUNT and self.turn >= high_from:
                    raw = cp3._wire({"input_tokens": 20000})
                    raw_fixture.raws[-1] = (self.endpoint, self.turn, raw)
                    result.read.side_effect = lambda limit: raw[:limit]
                return result
        return patch("earnings_http.http.client.HTTPSConnection", side_effect=Connection)

    def refuse(self, fixture, mutate):
        binding = fixture.save_spec(mutate)
        rows, created = fixture.rows(), list(self.case.created)
        with self.assertRaises((ValueError, KeyError, TypeError, FileNotFoundError)):
            with fixture.open(binding=binding):
                self.fail("Invalid v2 commitment reached ownership")
        self.assertEqual(self.case.created, created)
        fixture.client_factory.assert_not_called()
        self.assertEqual(fixture.rows(), rows)
        self.assertFalse(fixture.root.exists())
        self.assertFalse(fixture.claim_path().exists())

    def verify_execution(self, fixture, output, worker, slot):
        task = cp3.EarningsTask()
        task.kernel = fixture.raw.kernel
        verified = task.execution(output, worker, Path(slot))
        self.assertEqual(verified["consumed"]["pair_sha256"], worker.pair)
        self.assertEqual(verified["state"], worker.state_binding)
        return verified

    def test_v1_exact_fourteen_fields_and_actual_controller_behavior_remain(self):
        fixture = self.case.fixture("forecast-v1-parity", purpose="controller_protocol")
        before = {path: path.read_bytes() for path in fixture.home.rglob("*") if path.is_file()}
        self.assertEqual(set(runtime.preflight_runtime(fixture.binding)), owner.SPEC_FIELDS)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        with fixture.exchange(), fixture.open() as owned:
            budget = owned["budget"]
            owned["roles"]["controller"](fixture.prompt(), fixture.slots["controller"][0])
        self.case.assert_closed_once(budget)
        self.assertEqual(fixture.rows()[-1][3:], (92800, "settled"))
        self.assertEqual(fixture.terminal()["status"], "COMPLETED_COMPONENT_CONTEXT")

    def test_v2_exact_fifteen_fields_readonly_and_only_forecast_has_original_resources(self):
        fixture = self.fixture("readonly")
        before = {path: path.read_bytes() for path in fixture.home.rglob("*") if path.is_file()}
        created = list(self.case.created)
        value = runtime.preflight_runtime(fixture.binding)
        self.assertEqual(set(value), owner.SPEC_FIELDS | {"forecast_study"})
        self.assertEqual(value["limits"]["forecast"],
                         {"max_input_tokens": 100000, "max_output_tokens": 25000, "wall_seconds": 1800})
        for role in ("controller", "author", "review"):
            self.assertTrue(all(value["limits"][role][key] <= LIMITS[key] for key in LIMITS))
        self.assertEqual(len(value["slots"]["forecast"]), 6)
        self.assertEqual(self.case.created, created)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        fixture.client_factory.assert_not_called()

    def test_actual_controller_author_and_two_forecast_turns_share_owner_and_task_execution(self):
        fixture = self.fixture("three-actual-services")
        # This case specifically tests two forecast turns. The old synthetic
        # 300s global cutoff now correctly forces immediate finalization; give
        # this invented owner >600s, without changing the production1800s wall.
        fixture.spec.update(cutoff_utc=owner._utc(self.case.wall + 2400),
                            deadline_utc=owner._utc(self.case.wall + 2700))
        fixture.binding = owner._save(fixture.home / "two-turn-runtime-spec.json", fixture.spec)
        raw, prompt = fixture.raw, fixture.prompt()
        chosen = json.loads(fixture.response()["output"][0]["content"][0]["text"])
        before = prompt["profiles"]["R"]
        after = dict(before, research_instructions="Reconcile exact units and filing dates.")
        author_payload = {"decision_sha256": digest(chosen), "source_text": "PROFILE = " + repr(after) + "\n",
            "test_text": "CASES = " + repr([{"field": "research_instructions", "expected": after["research_instructions"]}]) + "\n"}
        author_response = raw.response([{"type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": json.dumps(author_payload)}]}])
        replies = [fixture.response(), author_response, raw.research(), raw.final()]
        worker = raw.worker(selected=True)
        with self.exchange(fixture, replies, high_from=2), fixture.open() as owned:
            budget = owned["budget"]
            services = [owned["roles"][role].__self__ for role in ("controller", "author", "forecast")]
            self.assertTrue(all(service.budget is budget for service in services))
            self.assertTrue(all(service.factory is services[0].factory for service in services))
            self.assertEqual(services[2].clock_binding, owned["clock_binding"])
            self.assertEqual(services[2].window, owned["window"])
            self.assertEqual(services[2].context["cutoff_monotonic"], budget.monotonic_deadline)
            controller_original = owned["roles"]["controller"](prompt, fixture.slots["controller"][0])
            actual_choice = controller.parse_capacity_decision(entry.strict_json(entry.checked(controller_original).decode()), prompt)
            self.assertEqual(actual_choice, chosen)
            author_original = owned["roles"]["author"](actual_choice, before, fixture.slots["author"][0])
            candidate = cp3.EarningsTask().candidate(entry.strict_json(entry.checked(author_original).decode()), before, actual_choice)
            self.assertEqual(candidate["author_sha256"], digest(author_payload))
            self.assertIs(candidate["tests_executed"], False)
            with patch.object(entry, "NightBudget", side_effect=AssertionError("No forecast ledger reopen")):
                output = owned["roles"]["forecast"](worker, fixture.slots["forecast"][0])
            self.verify_execution(fixture, output, worker, fixture.slots["forecast"][0])
            self.assertEqual(worker.state["records"][0]["record"]["value"], 100)
            self.assertEqual(history_snapshot(budget.db, fixture.baseline["max_rowid"]), fixture.baseline)
            self.assertEqual(sum(item is budget for item in self.case.closed), 0)
            self.assertEqual([row[2:] for row in fixture.rows()[1:]],
                             [(10290000, 92800, "settled")] * 2 + [(300000000, 92800, "settled")] * 2)
        self.case.assert_closed_once(budget)
        self.assertEqual(sum(row[3] for row in fixture.rows()), 1000 + 4 * 92800)
        self.assertEqual(fixture.client_factory.call_count, 3)
        self.assertEqual(len(raw.calls), 8)
        for _, payload in raw.calls:
            self.assertEqual(payload["model"], raw.rate["api_model"])
            self.assertEqual(payload["reasoning"], {"effort": raw.rate["effort"]})
        self.assertEqual(raw.calls[5][1]["max_output_tokens"], 25000)
        self.assertEqual(raw.calls[7][1]["max_output_tokens"], 25000)
        self.assertTrue(all(connection.closed for connection in raw.connections))
        self.assertEqual(fixture.terminal()["status"], "COMPLETED_COMPONENT_CONTEXT")

    def test_bound_original_final_output_override_reaches_physical_forecast(self):
        fixture = self.fixture("final-override", original_update={"max_turns_per_company": 1, "final_max_output_tokens": 30000})
        worker = fixture.raw.worker()
        with self.exchange(fixture, [fixture.raw.final()]), fixture.open() as owned:
            budget = owned["budget"]
            output = owned["roles"]["forecast"](worker, fixture.slots["forecast"][0])
            self.verify_execution(fixture, output, worker, fixture.slots["forecast"][0])
        self.case.assert_closed_once(budget)
        self.assertEqual(fixture.raw.calls[1][1]["max_output_tokens"], 30000)
        self.assertEqual(fixture.raw.calls[0][1]["tool_choice"], "none")
        self.assertEqual(fixture.rows()[-1][2:], (350000000, 92800, "settled"))

    def test_controller_author_and_review_caps_cannot_expand(self):
        for role in ("controller", "author", "review"):
            for key in LIMITS:
                with self.subTest(role=role, key=key):
                    fixture = self.fixture(role + "-" + key)
                    self.refuse(fixture, lambda spec, role=role, key=key:
                                spec["limits"][role].update({key: LIMITS[key] + 1}))

    def test_forecast_limits_must_equal_original_not_even_silently_narrow(self):
        for key in LIMITS:
            for delta in (-1, 1):
                with self.subTest(key=key, delta=delta):
                    fixture = self.fixture("exact-" + key + "-" + str(delta))
                    self.refuse(fixture, lambda spec, key=key, delta=delta:
                                spec["limits"]["forecast"].update({key: spec["limits"]["forecast"][key] + delta}))

    def test_missing_or_extra_runtime_fields_and_v1_study_injection_reject(self):
        for index, change in enumerate((lambda spec: spec.pop("forecast_study"),
                lambda spec: spec.update(unreviewed=True),
                lambda spec: spec.update(schema="earnings_capacity_runtime_v1"))):
            with self.subTest(index=index):
                self.refuse(self.fixture("fields-" + str(index)), change)

    def test_expanded_schema_is_capacity_episode_only(self):
        self.refuse(self.fixture("purpose"), lambda spec: spec.update(purpose="controller_protocol"))

    def test_invalid_study_schema_model_or_binding_refuses_before_ownership(self):
        for index, change in enumerate((lambda value: value.update(schema="unknown"),
                lambda value: value["model"].update(requested_model="gpt-5.5-2026-04-23"),
                lambda value: value.pop("runtime_config"))):
            with self.subTest(index=index):
                fixture = self.fixture("study-" + str(index))
                study = deepcopy(fixture.raw.study)
                change(study)
                fixture.raw.rewrite_study(study)
                self.refuse(fixture, lambda spec: spec.update(forecast_study=fixture.raw.study_binding))
        self.refuse(self.fixture("study-hash"), lambda spec:
                    spec["forecast_study"].update(sha256="f" * 64))

    def test_study_runtime_and_exact_prior_config_must_agree(self):
        fixture = self.fixture("prior-config")
        study = deepcopy(fixture.raw.study)
        study["runtime_config"]["max_input_tokens"] -= 1
        fixture.raw.rewrite_study(study)
        self.refuse(fixture, lambda spec: spec.update(forecast_study=fixture.raw.study_binding))

    def test_original_resources_require_positive_exact_ints_and_at_most_twenty_four_turns(self):
        variants = ({"max_input_tokens": True}, {"max_output_tokens": 0},
                    {"company_wall_seconds": 1800.0}, {"request_timeout_seconds": 0},
                    {"max_turns_per_company": 25}, {"final_max_output_tokens": 0})
        for index, update in enumerate(variants):
            with self.subTest(update=update):
                self.refuse(self.fixture("resources-" + str(index), original_update=update), lambda spec: None)

    def test_all_role_rates_must_equal_original_model_effort_and_literal_prices(self):
        for key, value in (("api_model", "gpt-5.5-2026-04-23"), ("effort", "xhigh"),
                           ("input", "3"), ("cached", ".1")):
            with self.subTest(key=key):
                self.refuse(self.fixture("rates-" + key), lambda spec, key=key, value=value:
                            spec["rates"].update({key: value}))

    def test_v2_requires_actual_entry_forecaster_and_exact_factory_source_bindings(self):
        for key in ("forecast_entry", "forecaster", "factory_forecast"):
            with self.subTest(key=key):
                self.refuse(self.fixture("missing-source-" + key), lambda spec, key=key: spec["sources"].pop(key))
        for key in ("forecast_entry", "forecaster"):
            with self.subTest(substituted=key):
                self.refuse(self.fixture("wrong-source-" + key), lambda spec, key=key:
                            spec["sources"].update({key: owner._pin(controller.__file__)}))

    def test_forecast_slots_stay_unique_canonical_and_bounded_to_six(self):
        changes = (lambda spec: spec["slots"]["forecast"].append(spec["slots"]["forecast"][0]),
                   lambda spec: spec["slots"]["forecast"].__setitem__(0, spec["slots"]["author"][0]),
                   lambda spec: spec["slots"]["forecast"].__setitem__(0, str(Path(spec["root"]) / "outside")))
        for index, change in enumerate(changes):
            with self.subTest(index=index):
                self.refuse(self.fixture("slots-" + str(index)), change)

    def test_shared_guard_rereads_study_and_prior_after_physical_count_without_rebinding(self):
        for kind in ("study", "prior", "rebound-study"):
            with self.subTest(kind=kind):
                fixture = self.fixture("drift-" + kind)
                def drift(turn):
                    if kind == "prior":
                        fixture.raw.prior_path.write_bytes(b"{}\n")
                    elif kind == "study":
                        fixture.raw.study_path.write_bytes(b"{}\n")
                    else:
                        study = deepcopy(fixture.raw.study)
                        study["runtime_config"]["max_turns_per_company"] -= 1
                        fixture.raw.rewrite_study(study)
                        fixture.spec["forecast_study"] = deepcopy(fixture.raw.study_binding)
                fixture.raw.after_count = drift
                with self.assertRaises(RuntimeError), self.exchange(fixture, [fixture.raw.final()]):
                    with fixture.open() as owned:
                        budget = owned["budget"]
                        owned["roles"]["forecast"](fixture.raw.worker(), fixture.slots["forecast"][0])
                self.case.assert_closed_once(budget)
                self.assertEqual([endpoint for endpoint, _ in fixture.raw.calls], [COUNT])
                self.assertEqual(len(fixture.rows()), 1)
                raw_paths = list(Path(fixture.slots["forecast"][0]).glob("http-*.raw.bin"))
                self.assertEqual(len(raw_paths), 1)
                self.assertEqual(raw_paths[0].read_bytes(), cp3._wire({"input_tokens": 20000}))
                self.assertEqual(fixture.terminal()["status"], "FAILED_NO_RETRY")

    def test_forecast_uncertainty_remains_shared_and_blocks_other_actual_roles(self):
        fixture = self.fixture("uncertainty")
        with self.assertRaises(RuntimeError), self.exchange(fixture, [TimeoutError("invented uncertainty")]):
            with fixture.open() as owned:
                budget = owned["budget"]
                try:
                    owned["roles"]["forecast"](fixture.raw.worker(), fixture.slots["forecast"][0])
                except RuntimeError:
                    calls = list(fixture.raw.calls)
                    with self.assertRaises(owner.BudgetStop):
                        owned["roles"]["controller"](fixture.prompt(), fixture.slots["controller"][0])
                    chosen = json.loads(fixture.response()["output"][0]["content"][0]["text"])
                    with self.assertRaises(owner.BudgetStop):
                        owned["roles"]["author"](chosen, fixture.prompt()["profiles"]["R"], fixture.slots["author"][0])
                    self.assertEqual(fixture.raw.calls, calls)
                    self.assertEqual(history_snapshot(budget.db, fixture.baseline["max_rowid"]), fixture.baseline)
                    raise
        self.case.assert_closed_once(budget)
        self.assertEqual(fixture.rows()[-1][2:], (300000000, 0, "uncertain"))
        self.assertEqual(fixture.terminal()["budget_summary"]["unresolved_reserved_usd"], .3)
        self.assertEqual(fixture.client_factory.call_count, 1)
        self.assertEqual(fixture.terminal()["status"], "FAILED_NO_RETRY")


if __name__ == "__main__":
    unittest.main()
