"""Independent CP4 owner probes: real temporary budgets and fake raw HTTPS only.

These prove local resource ownership, not full role implementations or live
admission. No actual budget ledger, provider key, or network is used.
"""
from contextlib import closing, contextmanager, nullcontext
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import inspect
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "research" / "market_rsi"))

import earnings_capacity_runtime as runtime
import earnings_clock as clock
import earnings_controller as controller
import earnings_entry as entry
import edgar_forecast_openai as forecast
from edgar_forecast_budget import BudgetStop, PilotBudget
from edgar_forecast_full_budget import activate
from earnings_http import RawOpenAIHTTP
from earnings_night_budget import DeadlineHTTP, NightBudget, history_snapshot

MODEL = "gpt-6.1-sol"
PARENT = "76885ad4ec7a2bd83bf24aeb8de051816d507e2a"
BOOT = "11111111-1111-1111-1111-111111111111"
PRIVATE = "CP4_PRIVATE_EXCEPTION_TEXT_MUST_NOT_REACH_OWNER_RESULT"
ROLES = ("controller", "author", "review", "forecast")
SPEC_FIELDS = {"schema", "purpose", "id", "source_commit", "root", "ledger",
               "baseline", "cutoff_utc", "deadline_utc",
               "additional_cap_nano_usd", "rates", "limits", "slots", "sources"}
CONTEXT_FIELDS = {"schema", "source_commit", "root", "rates", "limits",
                  "cutoff_utc", "cutoff_monotonic", "slots"}


def _pin(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}


def _save(path, value):
    entry.durable_json(path, value)
    return _pin(path)


def _utc(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _wire(value):
    return (json.dumps(value, ensure_ascii=False, indent=3) + "\n\n").encode()


def _raw_receipt(intent):
    prefix = intent.with_name(intent.name.removesuffix(".intent.json"))
    return prefix.with_suffix(".raw.bin")


class _StandIn:
    """A trusted source-bound factory, not a replacement production service."""
    role = None

    def __init__(self, context_binding, *, budget, client_factory):
        self.binding = deepcopy(context_binding)
        self.context = entry.strict_json(entry.checked(self.binding).decode())
        if (set(self.context) != CONTEXT_FIELDS or self.context["schema"] !=
                f"earnings_capacity_{self.role}_transport_v1"):
            raise ValueError("Exact declared role context required")
        self.budget, self.factory = budget, client_factory

    def invoke(self, slot=None):
        ctx = self.context
        slot = ctx["slots"][0] if slot is None else slot
        if slot not in ctx["slots"]:
            raise ValueError("Undeclared stand-in slot")
        if entry.strict_json(entry.checked(self.binding).decode()) != ctx:
            raise ValueError("Role context drift")
        output = Path(slot)
        output.mkdir(parents=True, exist_ok=False)
        request = {"model": ctx["rates"]["api_model"],
            "reasoning": {"effort": ctx["rates"]["effort"]},
            "input": [{"role": "user", "content": "Synthetic " + self.role}],
            "tools": [], "tool_choice": "none", "parallel_tool_calls": False}
        transport = DeadlineHTTP(self.factory(), deadline_utc=ctx["cutoff_utc"],
            rollout_seconds=ctx["limits"]["wall_seconds"],
            captured_deadline=ctx["cutoff_monotonic"])
        return forecast.budgeted_response(entry.ReceiptHTTP(transport, output),
            request, ctx["rates"], ctx["limits"], self.budget, output, 1)


class Author(_StandIn):
    role = "author"


class Review(_StandIn):
    role = "review"


class Forecast(_StandIn):
    role = "forecast"


class BrokenAuthor(Author):
    def __init__(self, context_binding, *, budget, client_factory):
        super().__init__(context_binding, budget=budget, client_factory=client_factory)
        raise ValueError(PRIVATE)


def controller_factory(context_binding, *, budget, client_factory):
    return controller.CapacityController(context_binding, budget=budget,
                                         client_factory=client_factory).propose


def author_factory(context_binding, *, budget, client_factory):
    return Author(context_binding, budget=budget, client_factory=client_factory).invoke


def review_factory(context_binding, *, budget, client_factory):
    return Review(context_binding, budget=budget, client_factory=client_factory).invoke


def forecast_factory(context_binding, *, budget, client_factory):
    return Forecast(context_binding, budget=budget, client_factory=client_factory).invoke


def broken_author_factory(context_binding, *, budget, client_factory):
    return BrokenAuthor(context_binding, budget=budget, client_factory=client_factory).invoke


class _Fixture:
    def __init__(self, case, name, *, purpose="capacity_episode", ledger=None,
                 identifier=None, factories=None):
        self.case, self.home = case, case.workspace / name
        self.home.mkdir()
        self.root = self.home / "runtime-root"
        self.ledger = ledger or self.home / "synthetic-owned.sqlite3"
        if ledger is None:
            prior = PilotBudget(self.ledger)
            try:
                prior.reserve("fixture-prior", MODEL, 10000)
                prior.settle("fixture-prior", 1000)
            finally:
                prior.close()
            activate(self.ledger, "a" * 64, PARENT)
        with closing(sqlite3.connect(self.ledger.as_uri() + "?mode=ro", uri=True)) as db:
            self.baseline = history_snapshot(db)
        self.names = ROLES if purpose == "capacity_episode" else ("controller",)
        choices = {"controller": controller_factory, "author": author_factory,
                   "review": review_factory, "forecast": forecast_factory}
        self.factories = {k: choices[k] for k in self.names}
        if factories:
            self.factories.update(factories)
        self.rates = {"api_model": MODEL, "effort": "xhigh", "input": "2",
                      "cached": ".1", "write": "2.5", "output": "10"}
        self.limits = {k: {"max_input_tokens": 10000,
            "max_output_tokens": 1024, "wall_seconds": 60} for k in self.names}
        self.slots = {k: [str(self.root / "roles" / (k + "-01"))]
                      for k in self.names}
        sources = {"runtime": _pin(runtime.__file__),
            "budget": _pin(REPO / "tools" / "earnings_night_budget.py"),
            "clock": _pin(clock.__file__), "controller": _pin(controller.__file__)}
        sources.update({"factory_" + k: _pin(inspect.getsourcefile(v))
                        for k, v in self.factories.items()})
        self.spec = {"schema": "earnings_capacity_runtime_v1", "purpose": purpose,
            "id": identifier or name, "source_commit": PARENT,
            "root": str(self.root), "ledger": str(self.ledger),
            "baseline": deepcopy(self.baseline), "cutoff_utc": _utc(case.wall + 300),
            "deadline_utc": _utc(case.wall + 600),
            "additional_cap_nano_usd": 20_000_000_000, "rates": self.rates,
            "limits": self.limits, "slots": self.slots, "sources": sources}
        self.binding = _save(self.home / "runtime-spec.json", self.spec)
        self.calls, self.connections, self.clients = [], [], []
        self.count_raw = _wire({"object": "response.input_tokens", "input_tokens": 20})
        self.generation = _wire(self.response())
        self.client_factory = Mock(side_effect=self.make_http)

    def save_spec(self, change):
        value = deepcopy(self.spec)
        change(value)
        return _save(self.home / ("changed-" + str(len(list(self.home.glob("changed-*"))))
                                 + ".json"), value)

    def make_http(self):
        client = RawOpenAIHTTP("", 600)
        self.clients.append(client)
        return client

    def prompt(self):
        packet = {"task_id": "invented-earnings-runtime", "parent_feedback_sha256": "b" * 64,
            "parent_pair_sha256": "a" * 64, "questions": "Five invented filing questions.",
            "feedback": {"observation": {"prediction": {"planned_targets": 5,
                "scored_targets": 0, "score_out_of_5": None},
                "execution": {"status": "FAILED_NO_RETRY", "turns": 1,
                              "tool_calls": 0, "error_type": "ValueError"},
                "cik": "invented-company"}, "baseline_score_out_of_5": 1.5},
            "prior_recipe": None}
        profiles = {"R": {"axis": "R", "research_instructions": "Reconcile units.",
                           "reuse_facts": True},
                    "H": {"axis": "H", "read_chunk_limit": 1000,
                           "search_hit_limit": 20}}
        return controller.capacity_input(packet, profiles)

    def response(self):
        choice = {"schema": "earnings_capacity_decision_v1", "axis": "R",
            "component": "research_policy", "parent_pair_sha256": "a" * 64,
            "feedback_sha256": "b" * 64, "hypothesis": "Reconcile invented units.",
            "expected_effect": "Reduce inconsistent calculations."}
        return {"id": "resp_invented_runtime", "object": "response",
            "status": "completed", "error": None, "model": MODEL, "service_tier": "default",
            "usage": {"input_tokens": 12, "output_tokens": 7, "total_tokens": 19,
                "input_tokens_details": {"cached_tokens": 3}},
            "output": [{"id": "msg_fixture", "type": "message", "status": "completed",
                "role": "assistant", "content": [{"type": "output_text",
                    "text": json.dumps(choice), "annotations": []}]}]}

    @contextmanager
    def exchange(self):
        fixture = self

        class Connection:
            def __init__(self, host, timeout):
                if host != "api.openai.com":
                    raise AssertionError("Unexpected fake HTTP host")
                self.timeout, self.closed = timeout, False
                fixture.connections.append(self)

            def request(self, method, endpoint, body, headers):
                expected = "/v1/responses/input_tokens" if len(fixture.calls) % 2 == 0 else "/v1/responses"
                if method != "POST" or endpoint != expected:
                    raise AssertionError("Unexpected HTTP order or retry")
                self.endpoint = endpoint
                fixture.calls.append((endpoint, json.loads(body)))

            def getresponse(self):
                raw = fixture.count_raw if self.endpoint.endswith("input_tokens") else fixture.generation
                if isinstance(raw, BaseException):
                    raise raw
                return Mock(status=200, getheader=Mock(return_value="req_cp4_fixture"),
                            read=Mock(side_effect=lambda limit: raw[:limit]))

            def close(self):
                self.closed = True

        with patch("earnings_http.http.client.HTTPSConnection", side_effect=Connection):
            yield

    def open(self, *, binding=None, factories=None, client_factory=None):
        return runtime.open_capacity_runtime(binding or self.binding,
            client_factory=self.client_factory if client_factory is None else client_factory,
            role_factories=self.factories if factories is None else factories)

    def rows(self):
        with closing(sqlite3.connect(self.ledger.as_uri() + "?mode=ro", uri=True)) as db:
            return db.execute("SELECT id,model,reserved,charged,status FROM requests ORDER BY rowid").fetchall()

    def claim_path(self, result=False):
        identity = sha256(self.spec["id"].encode()).hexdigest()
        return self.ledger.parent / ".capacity-runtime-claims" / (identity + (".result.json" if result else ".json"))

    def terminal(self):
        return entry.strict_json(self.claim_path(result=True).read_text())


class CapacityRuntimeOwnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cp4-runtime-owner-")
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve()
        self.wall, self.mono = time.time(), time.monotonic()
        self.created, self.closed = [], []
        original_init, original_close = NightBudget.__init__, NightBudget.close

        def observed_init(budget, *args, **options):
            # Observe actual assembly without replacing the owner-supplied
            # clock, transaction or accounting implementation.
            self.created.append(budget)
            original_init(budget, *args, **options)

        def observed_close(budget):
            self.closed.append(budget)
            return original_close(budget)

        for guard in (patch.object(clock, "boot_id", return_value=BOOT),
                patch.object(time, "time", side_effect=lambda: self.wall),
                patch.object(time, "monotonic", side_effect=lambda: self.mono),
                patch.object(NightBudget, "__init__", observed_init),
                patch.object(NightBudget, "close", observed_close),
                patch.object(controller, "credential", side_effect=AssertionError("No credentials")),
                patch.object(forecast, "credential", side_effect=AssertionError("No credentials")),
                patch("earnings_http.http.client.HTTPSConnection", side_effect=AssertionError("No network")),
                patch("socket.create_connection", side_effect=AssertionError("No network fallback"))):
            guard.start()
            self.addCleanup(guard.stop)

    def fixture(self, name, **options):
        return _Fixture(self, name, **options)

    def assert_closed_once(self, budget):
        self.assertEqual(sum(value is budget for value in self.closed), 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            budget.db.execute("SELECT 1")

    def assert_terminal(self, fixture, error_type, *, summary=None):
        result = fixture.terminal()
        self.assertEqual(result["error_type"], error_type)
        self.assertIs(result["retry_allowed"], False)
        self.assertNotIn(PRIVATE, fixture.claim_path(result=True).read_text())
        if summary is not None:
            self.assertEqual(result["budget_summary"], summary)
        self.assertTrue(fixture.claim_path().is_file())
        return result

    def test_preflight_is_readonly_exact14_spec_and_opens_no_budget_or_client(self):
        fixture = self.fixture("readonly")
        before = {str(p.relative_to(fixture.home)): p.read_bytes()
                  for p in fixture.home.rglob("*") if p.is_file()}
        rows = fixture.rows()
        value = runtime.preflight_runtime(fixture.binding)
        self.assertIs(type(value), dict)
        self.assertEqual(set(value), SPEC_FIELDS)
        self.assertEqual(value, fixture.spec)
        self.assertEqual(self.created, [])
        fixture.client_factory.assert_not_called()
        self.assertFalse(fixture.root.exists())
        self.assertEqual(fixture.rows(), rows)
        self.assertEqual(before, {str(p.relative_to(fixture.home)): p.read_bytes()
                         for p in fixture.home.rglob("*") if p.is_file()})

    def test_real_controller_and_four_raw_transports_share_one_budget_clock_factory(self):
        fixture = self.fixture("shared")
        with fixture.exchange(), fixture.open() as owned:
            self.assertEqual(set(owned), {"budget", "window", "clock_binding", "roles", "context_bindings"})
            budget, window = owned["budget"], owned["window"]
            self.assertEqual(len(self.created), 1)
            self.assertIs(self.created[0], budget)
            self.assertEqual(set(owned["roles"]), set(ROLES))
            self.assertEqual(set(owned["context_bindings"]), set(ROLES))
            factory = owned["roles"]["controller"].__self__.factory
            self.assertIsNot(factory, fixture.client_factory)
            fixture.client_factory.assert_not_called()
            self.assertEqual(entry.strict_json(entry.checked(owned["clock_binding"]).decode()), window)
            self.assertEqual(budget.deadline, clock.utc_epoch(fixture.spec["cutoff_utc"]))
            self.assertLessEqual(budget.monotonic_deadline, window["cutoff_monotonic"])
            self.assertGreater(window["deadline_monotonic"], window["cutoff_monotonic"])
            for name, callback in owned["roles"].items():
                self.assertTrue(callable(callback))
                role = callback.__self__
                self.assertIs(role.budget, budget)
                self.assertIs(role.factory, factory)
                self.assertEqual(role.binding, owned["context_bindings"][name])
                self.assertEqual(set(role.context), CONTEXT_FIELDS)
                self.assertEqual(role.context["schema"], f"earnings_capacity_{name}_transport_v1")
                self.assertEqual(role.context["cutoff_monotonic"], window["cutoff_monotonic"])
                self.assertEqual(role.context["rates"], fixture.rates)
                self.assertEqual(role.context["slots"], fixture.slots[name])
                self.assertEqual(role.context["limits"], fixture.limits[name])
            original = owned["roles"]["controller"](fixture.prompt(), fixture.slots["controller"][0])
            self.assertEqual(Path(original["path"]).read_bytes(),
                             (Path(fixture.slots["controller"][0]) / "01-response.json").read_bytes())
            for name in ("author", "review", "forecast"):
                owned["roles"][name]()
            self.assertEqual(fixture.client_factory.call_count, 4)
            self.assertEqual(len(fixture.calls), 8)
            rows = fixture.rows()
            self.assertEqual(rows[0], ("fixture-prior", MODEL, 10000, 1000, "settled"))
            self.assertEqual([r[3:] for r in rows[1:]], [(92800, "settled")] * 4)
            self.assertEqual(history_snapshot(budget.db, fixture.baseline["max_rowid"]), fixture.baseline)
            for name in ROLES:
                slot = Path(fixture.slots[name][0])
                reservation = entry.strict_json((slot / "01-request.json").read_text())
                intents = {entry.strict_json(p.read_text())["endpoint"]: p
                           for p in slot.glob("http-*.intent.json")}
                self.assertEqual(set(intents), {"/v1/responses/input_tokens", "/v1/responses"})
                self.assertEqual(_raw_receipt(intents["/v1/responses/input_tokens"]).read_bytes(),
                                 fixture.count_raw)
                self.assertEqual(_raw_receipt(intents["/v1/responses"]).read_bytes(), fixture.generation)
                intent = entry.strict_json(intents["/v1/responses"].read_text())
                self.assertEqual(intent["complete_reservation"], reservation)
                self.assertEqual(intent["budget_request_id"], reservation["request_id"])
                self.assertIs(intent["retry_allowed"], False)
            summary = budget.summary()
            self.assertAlmostEqual(summary["night_charged_upper_bound_usd"], 4 * 92800 / 1e9)
            self.assertEqual(summary["unresolved_reserved_usd"], 0)
            budget.active()
        self.assert_closed_once(budget)
        self.assertTrue(all(c.closed for c in fixture.connections))
        self.assert_terminal(fixture, None, summary=summary)

    def test_controller_protocol_constructs_only_declared_controller_without_eager_client(self):
        fixture = self.fixture("controller-only", purpose="controller_protocol")
        with fixture.open() as owned:
            budget = owned["budget"]
            self.assertEqual(set(owned["roles"]), {"controller"})
            self.assertIsInstance(owned["roles"]["controller"].__self__, controller.CapacityController)
            fixture.client_factory.assert_not_called()
        self.assert_closed_once(budget)
        self.assert_terminal(fixture, None)

    def test_different_roots_on_same_ledger_share_nonblocking_parent_lock(self):
        first = self.fixture("first-owner")
        second = self.fixture("second-owner", ledger=first.ledger)
        with first.open() as owned:
            lock = first.ledger.parent / ".capacity-runtime.lock"
            self.assertTrue(lock.is_file())
            self.assertFalse((first.root / ".capacity-runtime.lock").exists())
            with self.assertRaises((BlockingIOError, FileExistsError, BudgetStop)):
                with second.open():
                    self.fail("Competing root acquired ownership")
            self.assertFalse(second.claim_path().exists())
            self.assertFalse(second.root.exists())
            second.client_factory.assert_not_called()
            self.assertEqual(len(self.created), 1)
            owned["budget"].active()
        with second.open() as owned:
            self.assertEqual(set(owned["roles"]), set(ROLES))
        self.assert_terminal(second, None)

    def test_same_id_on_cold_different_root_stays_consumed_without_overwriting_claim(self):
        first = self.fixture("consumed-id")
        with first.open():
            pass
        originals = {p.name: p.read_bytes() for p in (first.claim_path(), first.claim_path(result=True))}
        second = self.fixture("cold-root", ledger=first.ledger, identifier=first.spec["id"])
        before = len(self.created)
        with self.assertRaises((FileExistsError, ValueError, BudgetStop)):
            with second.open():
                self.fail("Consumed ID resumed")
        self.assertEqual(len(self.created), before)
        second.client_factory.assert_not_called()
        self.assertFalse(second.root.exists())
        self.assertEqual(originals, {p.name: p.read_bytes()
                         for p in (first.claim_path(), first.claim_path(result=True))})

    def test_caller_failure_rethrows_sanitizes_closes_and_consumes_id(self):
        fixture = self.fixture("caller-failure")
        error = ValueError(PRIVATE)
        with self.assertRaises(ValueError) as caught:
            with fixture.open() as owned:
                budget = owned["budget"]
                budget.reserve("caller-paid", MODEL, 100000)
                budget.settle("caller-paid", 50000)
                summary = budget.summary()
                raise error
        self.assertIs(caught.exception, error)
        self.assert_closed_once(budget)
        self.assert_terminal(fixture, "ValueError", summary=summary)
        self.assertEqual(fixture.rows()[-1][3:], (50000, "settled"))
        fixture.client_factory.assert_not_called()
        second = self.fixture("failed-cold-root", ledger=fixture.ledger,
                              identifier=fixture.spec["id"])
        with self.assertRaises((FileExistsError, ValueError, BudgetStop)):
            with second.open():
                self.fail("Failed ID resumed")

    def test_constructor_failure_closes_budget_once_releases_lock_and_preserves_claim(self):
        fixture = self.fixture("constructor-failure", factories={"author": broken_author_factory})
        with self.assertRaises(ValueError):
            with fixture.open():
                self.fail("Broken constructor returned ownership")
        self.assertEqual(len(self.created), 1)
        self.assert_closed_once(self.created[0])
        fixture.client_factory.assert_not_called()
        self.assert_terminal(fixture, "ValueError")
        next_fixture = self.fixture("after-constructor", ledger=fixture.ledger)
        with next_fixture.open():
            pass
        self.assert_terminal(next_fixture, None)

    def test_uncertain_raw_generation_keeps_reservation_and_blocks_other_roles(self):
        fixture = self.fixture("uncertain-generation")
        fixture.generation = TimeoutError(PRIVATE)
        with fixture.exchange(), self.assertRaises(RuntimeError):
            with fixture.open() as owned:
                budget = owned["budget"]
                try:
                    owned["roles"]["controller"](fixture.prompt(), fixture.slots["controller"][0])
                finally:
                    self.assertTrue(budget.summary()["blocked"])
                    with self.assertRaises(BudgetStop):
                        owned["roles"]["author"].__self__.factory()
                    self.assertEqual(fixture.client_factory.call_count, 1)
                    summary = budget.summary()
        self.assert_closed_once(budget)
        row = fixture.rows()[-1]
        self.assertEqual(row[3:], (0, "uncertain"))
        self.assertEqual(summary["unresolved_reserved_usd"], row[2] / 1e9)
        self.assertEqual(len(fixture.calls), 2)
        self.assert_terminal(fixture, "RuntimeError", summary=summary)
        self.assertTrue(all(c.closed for c in fixture.connections))

    def test_semantic_controller_failure_keeps_paid_raw_charge_without_retry(self):
        fixture = self.fixture("semantic-failure")
        response = fixture.response()
        response["output"][0]["content"][0]["text"] = "{" + PRIVATE
        fixture.generation = _wire(response)
        with fixture.exchange(), self.assertRaises(RuntimeError):
            with fixture.open() as owned:
                budget = owned["budget"]
                owned["roles"]["controller"](fixture.prompt(), fixture.slots["controller"][0])
        self.assert_closed_once(budget)
        self.assertEqual(fixture.rows()[-1][3:], (92800, "settled"))
        output = Path(fixture.slots["controller"][0])
        self.assertFalse((output / "decision.json").exists())
        raw = next(p for p in output.glob("http-*.intent.json")
                   if entry.strict_json(p.read_text())["endpoint"] == "/v1/responses")
        self.assertEqual(_raw_receipt(raw).read_bytes(), fixture.generation)
        self.assertEqual(len(fixture.calls), 2)
        self.assert_terminal(fixture, "RuntimeError")

    def test_extra_or_missing_factory_roles_and_wrong_module_fail_before_resources(self):
        fixture = self.fixture("factory-map")
        for factories in ({"controller": controller.CapacityController},
                dict(fixture.factories, unknown=Author),
                dict(fixture.factories, controller=controller.CapacityController)):
            with self.subTest(keys=list(factories)), self.assertRaises((ValueError, TypeError)):
                with fixture.open(factories=factories):
                    self.fail("Invalid factories accepted")
        self.assertEqual(self.created, [])
        self.assertFalse(fixture.claim_path().exists())
        fixture.client_factory.assert_not_called()

    def test_missing_explicit_client_or_role_factory_refuses_without_fallback(self):
        fixture = self.fixture("explicit-only")
        for client, factories in ((None, fixture.factories), (fixture.client_factory, None)):
            with self.subTest(client=client is None), self.assertRaises((ValueError, TypeError)):
                with runtime.open_capacity_runtime(fixture.binding, client_factory=client,
                                                   role_factories=factories):
                    self.fail("Implicit fallback accepted")
        self.assertEqual(self.created, [])
        self.assertFalse(fixture.claim_path().exists())
        fixture.client_factory.assert_not_called()

    def test_malformed_specs_reject_before_budget_client_or_claim(self):
        fixture = self.fixture("malformed")
        changes = (
            ("extra", lambda s: s.update(extra="not-declared")),
            ("missing", lambda s: s.pop("baseline")),
            ("schema", lambda s: s.update(schema="unknown")),
            ("purpose", lambda s: s.update(purpose="live")),
            ("id-case", lambda s: s.update(id="UPPER")),
            ("id-path", lambda s: s.update(id="../../other")),
            ("source", lambda s: s.update(source_commit="z" * 40)),
            ("cap-bool", lambda s: s.update(additional_cap_nano_usd=True)),
            ("cap-zero", lambda s: s.update(additional_cap_nano_usd=0)),
            ("cap-expansion", lambda s: s.update(additional_cap_nano_usd=20_000_000_001)),
            ("model", lambda s: s["rates"].update(api_model="unknown-model")),
            ("rates-extra", lambda s: s["rates"].update(extra="1")),
            ("rates-number", lambda s: s["rates"].update(input=2)),
            ("rates-negative", lambda s: s["rates"].update(output="-1")),
            ("limit-bool", lambda s: s["limits"]["author"].update(wall_seconds=True)),
            ("limit-expansion", lambda s: s["limits"]["author"].update(wall_seconds=601)),
            ("role-missing", lambda s: s["limits"].pop("review")),
            ("root-relative", lambda s: s.update(root="relative/root")),
            ("cutoff-offset", lambda s: s.update(cutoff_utc="2099-01-01T00:00:00+00:00")),
            ("cutoff-after-terminal", lambda s: s.update(cutoff_utc=_utc(self.wall + 900))),
            ("baseline-bool", lambda s: s["baseline"].update(request_count=True)),
            ("baseline-digest", lambda s: s["baseline"].update(rows_sha256="z" * 64)),
            ("sources-missing", lambda s: s["sources"].pop("clock")),
            ("sources-extra", lambda s: s["sources"].update(untrusted=s["sources"]["runtime"])),
            ("source-hash", lambda s: s["sources"]["runtime"].update(sha256="f" * 64)),
        )
        for name, change in changes:
            with self.subTest(name=name):
                binding = fixture.save_spec(change)
                with self.assertRaises((ValueError, BudgetStop)):
                    runtime.preflight_runtime(binding)
                with self.assertRaises((ValueError, BudgetStop)):
                    with fixture.open(binding=binding):
                        self.fail("Malformed owner entered")
        self.assertEqual(self.created, [])
        self.assertFalse(fixture.root.exists())
        self.assertFalse(fixture.claim_path().exists())
        fixture.client_factory.assert_not_called()

    def test_slots_must_be_unique_canonical_direct_roles_children(self):
        fixture = self.fixture("slots")
        changes = (
            lambda s: s["slots"].update(author=s["slots"]["controller"]),
            lambda s: s["slots"].update(controller=s["slots"]["controller"] * 2),
            lambda s: s["slots"].update(review=[]),
            lambda s: s["slots"].update(author=[str(fixture.root / "outside-01")]),
            lambda s: s["slots"].update(author=[str(fixture.root / "roles" / "nested" / "author-01")]),
            lambda s: s["slots"].update(author=[str(fixture.root / "roles") + "/../roles/author-01"]),
            lambda s: s["slots"].update(author=[True]),
        )
        for index, change in enumerate(changes):
            with self.subTest(index=index), self.assertRaises(ValueError):
                runtime.preflight_runtime(fixture.save_spec(change))
        self.assertEqual(self.created, [])

    def test_existing_nonempty_root_missing_ledger_and_symlink_ledger_refuse(self):
        fixture = self.fixture("paths")
        fixture.root.mkdir()
        _save(fixture.root / "unowned.json", {"do_not_overwrite": True})
        original = (fixture.root / "unowned.json").read_bytes()
        with self.assertRaises(ValueError):
            with fixture.open():
                self.fail("Existing unowned root admitted")
        self.assertEqual((fixture.root / "unowned.json").read_bytes(), original)
        missing = fixture.home / "must-not-create.sqlite3"
        linked = fixture.home / "linked.sqlite3"
        linked.symlink_to(fixture.ledger)
        for target in (missing, linked):
            with self.subTest(path=target.name), self.assertRaises(ValueError):
                runtime.preflight_runtime(fixture.save_spec(lambda s: s.update(ledger=str(target))))
        self.assertFalse(missing.exists())
        self.assertEqual(self.created, [])
        fixture.client_factory.assert_not_called()

    def test_root_parent_symlink_refuses_without_touching_target(self):
        fixture = self.fixture("root-symlink")
        target = fixture.home / "target"
        target.mkdir()
        link = fixture.home / "alias"
        link.symlink_to(target, target_is_directory=True)
        binding = fixture.save_spec(lambda s: s.update(root=str(link / "runtime-root")))
        with self.assertRaises(ValueError):
            with fixture.open(binding=binding):
                self.fail("Symlink root parent admitted")
        self.assertEqual(list(target.iterdir()), [])
        self.assertEqual(self.created, [])

    def test_lock_and_registry_symlinks_refuse_without_following_or_credentials(self):
        for name, component in (("lock-symlink", ".capacity-runtime.lock"),
                                ("registry-symlink", ".capacity-runtime-claims")):
            with self.subTest(component=component):
                fixture = self.fixture(name)
                target = fixture.home / "do-not-touch"
                if component.endswith("claims"):
                    target.mkdir()
                else:
                    _save(target, {"do_not_touch": True})
                original = None if target.is_dir() else target.read_bytes()
                (fixture.ledger.parent / component).symlink_to(target)
                with self.assertRaises((ValueError, OSError)):
                    with fixture.open():
                        self.fail("Symlink ownership component admitted")
                self.assertFalse(fixture.root.exists())
                if target.is_dir():
                    self.assertEqual(list(target.iterdir()), [])
                else:
                    self.assertEqual(target.read_bytes(), original)
                fixture.client_factory.assert_not_called()
        self.assertEqual(self.created, [])

    def test_claim_symlink_is_not_followed_or_replaced(self):
        fixture = self.fixture("claim-symlink")
        fixture.claim_path().parent.mkdir()
        target = fixture.home / "claim-target.json"
        _save(target, {"preserve": True})
        original = target.read_bytes()
        fixture.claim_path().symlink_to(target)
        with self.assertRaises((ValueError, FileExistsError, OSError)):
            with fixture.open():
                self.fail("Symlink claim admitted")
        self.assertEqual(target.read_bytes(), original)
        self.assertTrue(fixture.claim_path().is_symlink())
        self.assertEqual(self.created, [])
        fixture.client_factory.assert_not_called()

    def test_unknown_boot_stops_before_budget_and_credentials_with_consumed_claim(self):
        fixture = self.fixture("unknown-boot")
        with patch.object(clock, "boot_id", side_effect=PermissionError(PRIVATE)), \
                self.assertRaises(PermissionError):
            with fixture.open():
                self.fail("Unknown boot admitted")
        self.assertEqual(self.created, [])
        fixture.client_factory.assert_not_called()
        self.assert_terminal(fixture, "PermissionError")

    def test_changed_context_and_spec_refuse_before_lazy_client_factory(self):
        for name, target in (("context-drift", "context"), ("spec-drift", "spec")):
            with self.subTest(target=target):
                fixture = self.fixture(name)
                with self.assertRaises((ValueError, BudgetStop)), fixture.open() as owned:
                    role = owned["roles"]["author"].__self__
                    binding = role.binding if target == "context" else fixture.binding
                    # Mutate only this owned synthetic artifact, never source.
                    Path(binding["path"]).write_bytes(b"{}\n")
                    with self.assertRaises((ValueError, BudgetStop)):
                        role.factory()
                    fixture.client_factory.assert_not_called()

    def test_changed_boot_and_sealed_clock_refuse_before_lazy_client_factory(self):
        for name, probe in (("boot-drift", "boot"), ("clock-drift", "clock")):
            with self.subTest(probe=probe):
                fixture = self.fixture(name)
                terminal = self.assertRaises((ValueError, BudgetStop)) if probe == "clock" else nullcontext()
                with terminal, fixture.open() as owned:
                    role = owned["roles"]["review"].__self__
                    if probe == "boot":
                        with patch.object(clock, "boot_id", return_value="22222222-2222-2222-2222-222222222222"):
                            with self.assertRaises((ValueError, BudgetStop)):
                                role.factory()
                    else:
                        Path(owned["clock_binding"]["path"]).write_bytes(b"{}\n")
                        with self.assertRaises((ValueError, BudgetStop)):
                            role.factory()
                    fixture.client_factory.assert_not_called()

    def test_backward_wall_clock_cannot_renew_original_monotonic_cutoff(self):
        fixture = self.fixture("wall-rollback")
        with self.assertRaises(BudgetStop), fixture.open() as owned:
            budget = owned["budget"]
            original = owned["window"]["cutoff_monotonic"]
            before = Path(owned["clock_binding"]["path"]).read_bytes()
            self.wall -= 3600
            self.mono = original + 1
            with self.assertRaises(BudgetStop):
                owned["roles"]["forecast"].__self__.factory()
            with self.assertRaises(BudgetStop):
                budget.active()
            self.assertLessEqual(budget.monotonic_deadline, original)
            self.assertEqual(Path(owned["clock_binding"]["path"]).read_bytes(), before)
            fixture.client_factory.assert_not_called()

    def test_monotonic_clock_rollback_is_rejected_before_lazy_factory(self):
        fixture = self.fixture("mono-rollback")
        with self.assertRaises((ValueError, BudgetStop)), fixture.open() as owned:
            self.mono = owned["window"]["monotonic_origin"] - 1
            with self.assertRaises((ValueError, BudgetStop)):
                owned["roles"]["forecast"].__self__.factory()
            fixture.client_factory.assert_not_called()

    def test_factory_returning_after_original_cutoff_is_refused_without_http(self):
        fixture = self.fixture("late-factory")
        with self.assertRaises(BudgetStop), fixture.open() as owned:
            def late():
                self.mono = owned["window"]["cutoff_monotonic"] + 1
                return fixture.make_http()
            fixture.client_factory.side_effect = late
            with self.assertRaises(BudgetStop):
                owned["roles"]["author"].__self__.factory()
            fixture.client_factory.assert_called_once()
            self.assertEqual(fixture.calls, [])
            self.assertEqual(len(fixture.rows()), 1)

    def test_factory_raised_failure_is_not_retried_or_written_as_private_message(self):
        fixture = self.fixture("factory-failure")
        fixture.client_factory.side_effect = ValueError(PRIVATE)
        with self.assertRaises(ValueError):
            with fixture.open() as owned:
                budget = owned["budget"]
                owned["roles"]["author"].__self__.factory()
        fixture.client_factory.assert_called_once()
        self.assert_closed_once(budget)
        self.assert_terminal(fixture, "ValueError")
        self.assertEqual(len(fixture.rows()), 1)

    def test_prior_history_drift_refuses_lazy_factory_without_refund_or_new_call(self):
        fixture = self.fixture("history-drift")
        with self.assertRaises(BudgetStop):
            with fixture.open() as owned:
                budget = owned["budget"]
                budget.db.execute("UPDATE requests SET charged=1001 WHERE id='fixture-prior'")
                owned["roles"]["author"].__self__.factory()
        self.assert_closed_once(budget)
        fixture.client_factory.assert_not_called()
        self.assertEqual(fixture.rows()[0][3], 1001)
        self.assert_terminal(fixture, "BudgetStop")

    def test_retained_guarded_factory_cannot_outlive_owner_or_create_credentials(self):
        fixture = self.fixture("factory-after-close")
        with fixture.open() as owned:
            factory, budget = owned["roles"]["author"].__self__.factory, owned["budget"]
        self.assert_closed_once(budget)
        with self.assertRaises((BudgetStop, ValueError, RuntimeError, sqlite3.ProgrammingError)):
            factory()
        fixture.client_factory.assert_not_called()


    def test_smaller_owner_cap_is_cumulative_across_actual_role_transports(self):
        fixture = self.fixture("shared-downward-cap")
        binding = fixture.save_spec(lambda s: s.update(additional_cap_nano_usd=10_450_000))
        with fixture.exchange(), self.assertRaises(BudgetStop):
            with fixture.open(binding=binding) as owned:
                budget = owned["budget"]
                owned["roles"]["controller"](fixture.prompt(), fixture.slots["controller"][0])
                owned["roles"]["author"]()
                owned["roles"]["review"]()
        self.assert_closed_once(budget)
        self.assertEqual([r[3:] for r in fixture.rows()[1:]], [(92800, "settled")] * 2)
        self.assertEqual([endpoint for endpoint, _ in fixture.calls],
            ["/v1/responses/input_tokens", "/v1/responses"] * 2 + ["/v1/responses/input_tokens"])
        self.assertEqual(fixture.client_factory.call_count, 3)
        self.assert_terminal(fixture, "BudgetStop")

    def test_baseexception_caller_exit_is_preserved_and_budget_closed_once(self):
        fixture = self.fixture("caller-interrupt")
        error = KeyboardInterrupt(PRIVATE)
        with self.assertRaises(KeyboardInterrupt) as caught:
            with fixture.open() as owned:
                budget = owned["budget"]
                raise error
        self.assertIs(caught.exception, error)
        self.assert_closed_once(budget)
        self.assert_terminal(fixture, "KeyboardInterrupt")
        fixture.client_factory.assert_not_called()

    def test_terminal_summary_failure_is_recorded_and_not_reported_as_success(self):
        fixture = self.fixture("summary-failure")
        with self.assertRaises(RuntimeError):
            with fixture.open() as owned:
                budget = owned["budget"]
                budget.summary = Mock(side_effect=OSError(PRIVATE))
        self.assert_closed_once(budget)
        self.assert_terminal(fixture, "OSError")
        self.assertIsNone(fixture.terminal()["budget_summary"])

    def test_time_expiring_during_terminal_accounting_cannot_be_accepted(self):
        fixture = self.fixture("terminal-late-clock")
        with self.assertRaises(RuntimeError):
            with fixture.open() as owned:
                budget, original = owned["budget"], owned["budget"].summary
                def late_summary():
                    result = original()
                    self.mono = owned["window"]["cutoff_monotonic"] + 1
                    return result
                budget.summary = late_summary
        self.assert_closed_once(budget)
        self.assert_terminal(fixture, "BudgetStop")


if __name__ == "__main__":
    unittest.main()
