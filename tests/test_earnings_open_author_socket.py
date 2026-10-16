"""Scoped Author socket allowance with original deadlines/accounting intact.

All HTTP bytes, clocks, grants and financial inputs below are invented test
fixtures. Real raw receipts/counting/reservation/deadline/assembly code runs;
no real provider, credentials, production ledger or candidate execution does.
"""
from copy import deepcopy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "research" / "market_rsi"))

import earnings_open_roles as roles
from earnings_capacity_runtime import _OwnedHTTP
from edgar_forecast_budget import BudgetStop
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_capacity_author_transport as author_fixture
import test_earnings_capacity_controller_transport as controller_fixture
import test_earnings_open_roles as open_fixture


class IntSubclass(int):
    pass


class OpenAuthorSocketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="open-author-socket-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def fixture(self, name, *, role_seconds=900, context_seconds=1200,
                budget_seconds=1200, utc_seconds=3600):
        fixture = author_fixture._AuthorFixture(self, self.root / name)
        fixture.wall = float(int(fixture.wall))
        fixture.budget.monotonic_deadline = fixture.monotonic + budget_seconds
        context = deepcopy(fixture.context)
        context["limits"] = {"max_input_tokens": 10000, "max_output_tokens": 32768,
                             "wall_seconds": role_seconds}
        context["cutoff_monotonic"] = fixture.monotonic + context_seconds
        context["cutoff_utc"] = dt.datetime.fromtimestamp(
            fixture.wall + utc_seconds, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        fixture.bind_context(context)
        # Exercise the same property-forwarding owned raw client used in live
        # assembly. Its checks and all ledger operations are on this temp root.
        def check(loan):
            pending = fixture.budget.db.execute(
                "SELECT id,model,reserved FROM requests WHERE status='reserved'").fetchall()
            if loan is None:
                self.assertEqual(pending, [])
                fixture.budget.active()
            else:
                self.assertEqual(pending, [loan])
        owned = _OwnedHTTP(fixture.http, check,
            {slot: context["limits"] for slot in fixture.slots}, fixture.rates)
        fixture.factory.side_effect = lambda: owned
        return fixture

    def service(self, fixture, **options):
        return roles.OpenAuthor(fixture.context_binding, budget=fixture.budget,
            client_factory=fixture.factory, broker=open_fixture.Broker(), max_turns=1, **options)

    def payload(self, fixture):
        return {"decision_sha256": digest(fixture.choice()),
            "source_text": "PROGRAM={'axis':'R'}\ndef run(payload): return {'advice':'Check units'}\n",
            "test_text": "CASES=[{'input':{},'expected':{'advice':'Check units'}}]"}

    def invoke(self, fixture, service, response=None):
        return fixture.invoke(fixture.response(self.payload(fixture)) if response is None else response,
            chosen=fixture.choice(), before={"axis": "R"}, service=service)

    def test_default_socket_stays_600_and_optin_only_changes_socket_not_payload_or_reservation(self):
        observations = []
        for name, options, expected in (("default", {}, 600),
                                        ("explicit-none", {"socket_timeout_seconds": None}, 600),
                                        ("author-optin", {"socket_timeout_seconds": 900}, 900)):
            with self.subTest(name=name):
                fixture = self.fixture(name)
                self.assertEqual(fixture.http.timeout, 600)
                service = self.service(fixture, **options)
                binding = self.invoke(fixture, service)
                self.assertEqual([connection.timeout for connection in fixture.connections],
                                 [expected, expected])
                self.assertEqual(len(fixture.calls), 2)
                count, generation = [payload for _, payload in fixture.calls]
                self.assertEqual(count["model"], "gpt-6.1-sol")
                self.assertEqual(count["reasoning"], {"effort": "xhigh"})
                self.assertNotIn("max_output_tokens", count)
                self.assertEqual(generation, dict(count, max_output_tokens=32768,
                                                  service_tier="default", store=False))
                self.assertEqual(fixture.rows(), [(20 * 2500 + 32768 * 10000, 92800, "settled")])
                self.assertEqual(fixture.budget.summary()["unresolved_reserved_usd"], 0)
                self.assertEqual(Path(binding["path"]).read_bytes(),
                                 (Path(fixture.slots[0]) / "01-response.json").read_bytes())
                self.assertTrue(all(connection.closed for connection in fixture.connections))
                observations.append((count, generation, fixture.rows()))
        self.assertEqual(observations[0], observations[1])
        self.assertEqual(observations[0], observations[2])

    def test_author_socket_is_clipped_to_remaining_role_context_budget_and_utc_windows(self):
        cases = [
            ("role", {}, 900, 73, 827),
            ("context", {"context_seconds": 180}, 180, 20, 160),
            ("budget", {"budget_seconds": 140}, 140, 20, 120),
            ("utc", {"utc_seconds": 125}, 125, 5, 120),
        ]
        for name, options, first, elapsed, final in cases:
            with self.subTest(name=name):
                fixture = self.fixture(name, **options)
                def advance():
                    fixture.wall += elapsed
                    fixture.monotonic += elapsed
                fixture.after_count = advance
                self.invoke(fixture, self.service(fixture, socket_timeout_seconds=900))
                self.assertEqual([connection.timeout for connection in fixture.connections], [first, final])
                self.assertEqual(fixture.rows()[0][2], "settled")

    def test_noncanonical_or_unsupported_optin_rejects_before_client_creation(self):
        for index, value in enumerate((True, False, 600, 899, 901, 900.0, "900", IntSubclass(900), [], {})):
            with self.subTest(value=repr(value)):
                fixture = self.fixture(f"invalid-{index}")
                with self.assertRaises(ValueError):
                    self.service(fixture, socket_timeout_seconds=value)
                fixture.factory.assert_not_called()
                self.assertEqual(fixture.calls, [])
                self.assertEqual(fixture.rows(), [])
        fixture = self.fixture("short-role", role_seconds=600)
        with self.assertRaises(ValueError):
            self.service(fixture, socket_timeout_seconds=900)
        fixture.factory.assert_not_called()

    def test_controller_rejects_author_optin_and_retains_its_original_timeout(self):
        fixture = controller_fixture._TransportFixture(self, self.root / "controller")
        with self.assertRaises(ValueError):
            roles.OpenController(fixture.context_binding, budget=fixture.budget,
                client_factory=fixture.factory, broker=open_fixture.Broker(), socket_timeout_seconds=900)
        fixture.factory.assert_not_called()
        service = roles.OpenController(fixture.context_binding, budget=fixture.budget,
            client_factory=fixture.factory, broker=open_fixture.Broker(), max_turns=1)
        fixture.invoke(fixture.response(fixture.decision("continue")), service=service)
        self.assertEqual(len(fixture.connections), 2)
        # Controller's original 60-second role fixture clips raw600; no900 is used.
        self.assertTrue(all(0 < connection.timeout <= 60 for connection in fixture.connections))
        self.assertEqual(fixture.budget.summary()["unresolved_reserved_usd"], 0)

    def test_generation_timeout_remains_uncertain_failstop_without_retry_refund_or_new_slot(self):
        fixture = self.fixture("generation-timeout")
        service = self.service(fixture, socket_timeout_seconds=900)
        with self.assertRaises(RuntimeError):
            self.invoke(fixture, service, TimeoutError("SYNTHETIC_SOCKET_TIMEOUT_PRIVATE"))
        self.assertEqual(len(fixture.calls), 2)
        self.assertEqual(fixture.rows(), [(20 * 2500 + 32768 * 10000, 0, "uncertain")])
        slot = Path(fixture.slots[0])
        terminal = json.loads((slot / "result.json").read_bytes())
        self.assertEqual(terminal["status"], "FAILED_NO_RETRY")
        self.assertEqual(terminal["error_type"], "TimeoutError")
        self.assertFalse(terminal["retry_allowed"])
        self.assertNotIn("SYNTHETIC_SOCKET_TIMEOUT_PRIVATE", json.dumps(terminal))
        self.assertFalse((slot / "candidate.json").exists())
        before, rows = fixture.originals(), fixture.rows()
        with self.assertRaises(FileExistsError):
            self.invoke(fixture, service)
        self.assertEqual(fixture.originals(), before)
        self.assertEqual(fixture.rows(), rows)
        with self.assertRaises(BudgetStop):
            fixture.invoke(fixture.response(self.payload(fixture)), chosen=fixture.choice(),
                before={"axis": "R"}, slot=1, service=service)
        self.assertFalse(Path(fixture.slots[1]).exists())
        self.assertEqual(len(fixture.calls), 2)
        self.assertTrue(all(connection.closed for connection in fixture.connections))

    def test_count_timeout_stops_before_generation_or_any_reservation(self):
        fixture = self.fixture("count-timeout")
        original_fake = fixture.fake_connection
        def fail_count(generation):
            parent = original_fake(generation)
            class Connection(parent):
                def getresponse(inner):
                    if inner.endpoint.endswith("input_tokens"):
                        raise TimeoutError("Synthetic count timeout")
                    return super().getresponse()
            return Connection
        fixture.fake_connection = fail_count
        with self.assertRaises(RuntimeError):
            self.invoke(fixture, self.service(fixture, socket_timeout_seconds=900))
        self.assertEqual([endpoint for endpoint, _ in fixture.calls], ["/v1/responses/input_tokens"])
        self.assertEqual(fixture.rows(), [])
        self.assertFalse((Path(fixture.slots[0]) / "candidate.json").exists())
        self.assertEqual(json.loads((Path(fixture.slots[0]) / "result.json").read_bytes())["status"], "FAILED_NO_RETRY")


class OpenAuthorSocketAssemblyTests(unittest.TestCase):
    def fixture(self, *, followup=False):
        import test_earnings_open_assembly as assembly_fixture
        helper = assembly_fixture.OpenAssemblyTests(
            "test_complete_open_continue_delivers_actual_final_feedback_to_next_controller")
        self.addCleanup(helper.doCleanups)
        fixture = helper.fixture()
        if not followup:
            return assembly_fixture, helper, fixture
        grant = engine.read(fixture.envelope["grant"])
        grant["schema"] = "earnings_research_followup_grant_v1"
        fixture.envelope["grant"] = fixture.save("invented-role-socket-grant", grant)
        study = deepcopy(fixture.raw.study)
        study["new_live_grant"] = fixture.envelope["grant"]
        fixture.envelope["study"] = fixture.save("invented-role-socket-study", study)
        author_limits = {"max_input_tokens": 10000, "max_output_tokens": 32768, "wall_seconds": 900}
        fixture.envelope["role_limits"]["author"] = deepcopy(author_limits)
        fixture.runtime["limits"]["author"] = deepcopy(author_limits)
        fixture.runtime["forecast_study"] = fixture.envelope["study"]
        fixture.runtime_binding = fixture.save("invented-role-socket-runtime", fixture.runtime)
        fixture.episode_binding = fixture.save("invented-role-socket-episode", fixture.envelope)
        fixed = fixture.native["micro_config"]["fixed_context"]
        fixed["resource_policy_sha256"] = digest(fixture.runtime_binding)
        fixed["authority_sha256"] = digest({key: fixture.envelope[key] for key in ("mode", "grant", "window")})
        fixed["data_scope_sha256"] = digest({"study": fixture.envelope["study"],
            "cik": fixture.envelope["cik"], "kernel": fixture.envelope["evaluation_kernel"]})
        fixture.plan["episode"] = fixture.episode_binding
        fixture.assembly.update(episode=fixture.episode_binding, runtime=fixture.runtime_binding,
            native=fixture.save("invented-role-socket-native", fixture.native),
            matched_plan=fixture.save("invented-role-socket-plan", fixture.plan))
        policy = engine.read(fixture.assembly["transport_policy"])
        policy.update(schema="edgar_foreground_role_socket_policy_v1", author_socket_timeout_seconds=900)
        fixture.assembly["transport_policy"] = fixture.save("invented-role-socket-policy", policy)
        self.rebind(fixture)
        return assembly_fixture, helper, fixture

    def rebind(self, fixture):
        review = engine.read(fixture.assembly["independent_review"])
        review["episode"] = fixture.episode_binding
        review["reviewed_configuration_sha256"] = digest({key: value for key, value in
            fixture.assembly.items() if key != "independent_review"})
        fixture.assembly["independent_review"] = fixture.save("invented-role-socket-review", review)
        fixture.assembly_binding = fixture.save("invented-role-socket-assembly", fixture.assembly)

    def test_new_policy_reaches_only_author_factory_and_forecast_gets_exact_old600_projection(self):
        module, helper, fixture = self.fixture(followup=True)
        author_options, controller_options, forecasts = [], [], []
        author_init, controller_init = roles.OpenAuthor.__init__, roles.OpenController.__init__
        forecast_init = module.assembly.CapacityForecast.__init__
        def author_spy(instance, *args, **kwargs):
            author_options.append(kwargs.get("socket_timeout_seconds"))
            author_init(instance, *args, **kwargs)
        def controller_spy(instance, *args, **kwargs):
            controller_options.append(kwargs.get("socket_timeout_seconds"))
            controller_init(instance, *args, **kwargs)
        def forecast_spy(instance, *args, **kwargs):
            forecasts.append(kwargs["transport_policy_binding"])
            forecast_init(instance, *args, **kwargs)
        sequence = [fixture.raw.research(), fixture.raw.final(), helper.choose(fixture, "continue"),
                    fixture.raw.research(), fixture.raw.final(), helper.choose(fixture, "continue")]
        # This invented socket-policy fixture has no inherited research context;
        # real grant admission is covered separately, not by a private JSON file.
        with helper.scope(fixture), fixture.exchange(sequence), \
                patch('earnings_open_fresh_grant.policy', return_value={}), \
                patch.object(roles.OpenAuthor, "__init__", new=author_spy), \
                patch.object(roles.OpenController, "__init__", new=controller_spy), \
                patch.object(module.assembly.CapacityForecast, "__init__", new=forecast_spy):
            result = engine.read(module.assembly.run(fixture.episode_binding, fixture.assembly_binding))
        self.assertEqual(result["outcome"]["completed_rounds"], 2)
        self.assertEqual(author_options, [900])
        self.assertEqual(controller_options, [None])
        self.assertEqual(len(forecasts), 1)
        projected = engine.read(forecasts[0])
        combined = engine.read(fixture.assembly["transport_policy"])
        self.assertEqual(projected, {**{key: value for key, value in combined.items()
            if key != "author_socket_timeout_seconds"}, "schema": "edgar_foreground_slow_call_policy_v1"})
        self.assertEqual(projected["effective_socket_timeout_seconds"], 600)
        self.assertEqual(forecasts[0]["path"], str(fixture.root / "forecast-transport-policy.json"))
        self.assertTrue(all(0 < connection.timeout <= 600 for connection in fixture.raw.connections))

    def test_policy_schema_types_and_grant_joins_reject_before_runtime_owner(self):
        module, helper, fixture = self.fixture(followup=True)
        original = engine.read(fixture.assembly["transport_policy"])
        mutations = [("author_socket_timeout_seconds", 900.0), ("author_socket_timeout_seconds", True),
                     ("author_socket_timeout_seconds", 901), ("effective_socket_timeout_seconds", 600.0),
                     ("role_and_global_deadlines_unchanged", 1), ("retry_allowed", 0),
                     ("schema", "edgar_foreground_slow_call_policy_v1"),
                     ("source_commit", "f" * 40)]
        with helper.scope(fixture):
            module.assembly.validate(fixture.episode_binding, fixture.assembly_binding)
            for index, (key, value) in enumerate(mutations):
                with self.subTest(key=key, value=value):
                    changed = deepcopy(fixture.assembly)
                    changed["transport_policy"] = fixture.save(f"invalid-policy-{index}", dict(original, **{key: value}))
                    bound = fixture.save(f"invalid-assembly-{index}", changed)
                    with self.assertRaises(ValueError):
                        module.assembly.validate(fixture.episode_binding, bound)
        self.assertEqual(fixture.factory_calls, 0)
        self.assertFalse(fixture.paths["batch_root"].exists())
        old_module, old_helper, old = self.fixture()
        bad = engine.read(old.assembly["transport_policy"])
        bad.update(schema="edgar_foreground_role_socket_policy_v1", author_socket_timeout_seconds=900)
        old.assembly["transport_policy"] = old.save("invalid-old-grant-new-policy", bad)
        self.rebind(old)
        with old_helper.scope(old), self.assertRaises(ValueError):
            old_module.assembly.validate(old.episode_binding, old.assembly_binding)
        self.assertEqual(old.factory_calls, 0)


if __name__ == "__main__":
    unittest.main()
