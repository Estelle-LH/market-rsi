"""CP1 synthetic boundary checks: owned temporary ledger, fake HTTP, no live claim."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE / "tools"))
sys.path.insert(0, str(SOURCE / "research" / "market_rsi"))

import earnings_controller as c
from edgar_forecast_budget import BudgetStop, PilotBudget
from edgar_forecast_full_budget import activate, FullBudget
from earnings_http import RawOpenAIHTTP, save_bytes
from earnings_night_budget import history_snapshot, NightBudget

MODEL = "gpt-6.1-sol"
PARENT = "0f8f514740159bccd5df4a3b3c72f87938e3e9d7"
LIMITS = {"max_input_tokens": 10000, "max_output_tokens": 16384, "wall_seconds": 600}
RATES = {"api_model": MODEL, "effort": "xhigh", "input": "2", "cached": ".1",
         "write": "2.5", "output": "10"}
DEADLINE_INIT = c.DeadlineHTTP.__init__


class FixtureClock:
    def __init__(self):
        self.wall = time.time()
        self.monotonic = time.monotonic()

    def advance(self, *, wall=0, monotonic=0):
        self.wall += wall
        self.monotonic += monotonic


class OwnedBudget(NightBudget):
    """The test owns this connection; the service must not close or recreate it."""
    def __init__(self, *args, **kwargs):
        self.close_calls = 0
        super().__init__(*args, **kwargs)

    def close(self):
        self.close_calls += 1
        super().close()


class FakeWireHTTP(RawOpenAIHTTP):
    """Produce real receipt files while never creating a network connection."""
    def __init__(self, response, *, after_count=None):
        super().__init__("", timeout=600)
        self.response = response
        self.after_count = after_count
        self.calls = []
        self.timeouts = []

    def post(self, endpoint, payload):
        self.calls.append((endpoint, copy.deepcopy(payload)))
        self.timeouts.append(self.timeout)
        prefix, self.record_prefix = self.record_prefix, None
        if prefix is None or not prefix.with_suffix(".intent.json").is_file():
            raise AssertionError("Fake physical dispatch must follow durable send intent")
        if endpoint == "/v1/responses/input_tokens":
            value = {"input_tokens": 10}
        elif endpoint == "/v1/responses":
            if isinstance(self.response, BaseException):
                raise self.response
            value = copy.deepcopy(self.response)
        else:
            raise AssertionError("Unexpected fake HTTP endpoint")
        raw = (json.dumps(value, ensure_ascii=False, indent=1) + "\n").encode()
        save_bytes(prefix.with_suffix(".raw.bin"), raw)
        if endpoint == "/v1/responses/input_tokens" and self.after_count is not None:
            self.after_count()
        return value


class CapacityControllerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cp1-controller-boundary-")
        self.addCleanup(self.temp.cleanup)
        self.owned = Path(self.temp.name).resolve()
        self.root = self.owned / "session"
        (self.root / "roles").mkdir(parents=True)
        self.slots = [self.root / "roles" / f"controller-{index:02d}" for index in range(1, 4)]
        self.clock = FixtureClock()
        self.context_path = self.owned / "context.json"
        self.context = {
            "schema": "earnings_capacity_controller_transport_v1", "source_commit": PARENT,
            "root": str(self.root), "rates": copy.deepcopy(RATES), "limits": dict(LIMITS),
            "cutoff_utc": self.utc(self.clock.wall + 3600),
            "cutoff_monotonic": self.clock.monotonic + 3600,
            "slots": [str(slot) for slot in self.slots],
        }
        self.binding = self.bind_context(self.context)
        observation = {
            "prediction": {"planned_targets": 5, "scored_targets": 0, "score_out_of_5": None},
            "execution": {"status": "FAILED_NO_RETRY", "turns": 24,
                          "tool_calls": 23, "error_type": "ValueError"}, "cik": "fixture",
        }
        packet = {
            "task_id": "fixture", "parent_feedback_sha256": "b" * 64,
            "parent_pair_sha256": "a" * 64, "questions": "five invented questions",
            "feedback": {"observation": observation, "baseline_score_out_of_5": 1.5},
            "prior_recipe": None,
        }
        profiles = {
            "R": {"axis": "R", "research_instructions": "Check units", "reuse_facts": True},
            "H": {"axis": "H", "read_chunk_limit": 1000, "search_hit_limit": 5},
        }
        self.prompt = c.capacity_input(packet, profiles)
        self.chosen = {
            "schema": "earnings_capacity_decision_v1", "axis": "R",
            "component": "research_policy", "parent_pair_sha256": "a" * 64,
            "feedback_sha256": "b" * 64, "hypothesis": "Verify units before forecasting",
            "expected_effect": "Fewer invented numbers",
        }
        ledger = self.owned / "owned-synthetic.sqlite3"
        pilot = PilotBudget(ledger)
        try:
            pilot.reserve("synthetic-prior", MODEL, 10000)
            pilot.settle("synthetic-prior", 1000)
        finally:
            pilot.close()
        activate(ledger, "c" * 64, PARENT)
        full = FullBudget(ledger)
        try:
            baseline = history_snapshot(full.db)
        finally:
            full.close()
        self.budget = OwnedBudget(
            ledger, baseline=baseline, deadline_utc=self.utc(self.clock.wall + 7200),
            clock=lambda: self.clock.wall, monotonic=lambda: self.clock.monotonic,
            captured_deadline=self.clock.monotonic + 7200,
        )
        self.addCleanup(NightBudget.close, self.budget)
        self.client = FakeWireHTTP(self.response())
        self.factory = Mock(return_value=self.client)

    @staticmethod
    def utc(epoch):
        return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def bind_context(self, value):
        raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
        self.context_path.write_bytes(raw)
        return {"path": str(self.context_path), "sha256": hashlib.sha256(raw).hexdigest()}

    def controller(self, context=None, *, binding=None, factory=None):
        if context is not None:
            binding = self.bind_context(context)
        return c.CapacityController(
            self.binding if binding is None else binding, budget=self.budget,
            client_factory=self.factory if factory is None else factory,
        )

    def response(self, chosen=None):
        return {
            "status": "completed", "model": MODEL, "service_tier": "default",
            "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30,
                      "input_tokens_details": {"cached_tokens": 0}},
            "output": [{"type": "message", "content": [{"type": "output_text",
                       "text": json.dumps(self.chosen if chosen is None else chosen)}]}],
        }

    def invoke(self, service=None, *, prompt=None, slot=None):
        # DeadlineHTTP exposes injectable clocks, but its default arguments hold
        # the original functions. Inject the same fixture clocks used by the
        # caller-owned budget and Controller checks without replacing post().
        def init_deadline(transport, client, **options):
            options.update(clock=lambda: self.clock.wall, monotonic=lambda: self.clock.monotonic)
            DEADLINE_INIT(transport, client, **options)
        with patch.object(c.time, "time", side_effect=lambda: self.clock.wall), \
                patch.object(c.time, "monotonic", side_effect=lambda: self.clock.monotonic), \
                patch.object(c.DeadlineHTTP, "__init__", new=init_deadline):
            return (self.controller() if service is None else service).propose(
                self.prompt if prompt is None else prompt,
                self.slots[0] if slot is None else slot,
            )

    def terminal(self, slot=None, error_type=None):
        slot = self.slots[0] if slot is None else slot
        result = json.loads((slot / "result.json").read_text())
        self.assertEqual(result["status"], "FAILED_NO_RETRY")
        self.assertEqual(result["evidence_scope"], "unverified_transport_component")
        self.assertIs(result["model_authorship_verified"], False)
        if error_type is not None:
            self.assertEqual(result["error_type"], error_type)
        self.assertFalse((slot / "decision.json").exists())
        return result

    @staticmethod
    def saved_files(slot):
        return {str(path.relative_to(slot)): path.read_bytes()
                for path in slot.rglob("*") if path.is_file()}

    def generation_rows(self):
        return self.budget.db.execute(
            "SELECT reserved,charged,status FROM requests WHERE id != 'synthetic-prior' ORDER BY rowid"
        ).fetchall()

    def test_expired_wall_or_monotonic_cutoff_prevents_factory_and_claim(self):
        for kind in ("wall", "monotonic"):
            with self.subTest(kind=kind):
                context = copy.deepcopy(self.context)
                if kind == "wall":
                    context["cutoff_utc"] = self.utc(self.clock.wall - 1)
                else:
                    context["cutoff_monotonic"] = self.clock.monotonic - 1
                with self.assertRaises(BudgetStop):
                    self.invoke(self.controller(context))
                self.factory.assert_not_called()
                self.assertFalse(self.slots[0].exists())
                self.assertEqual(self.generation_rows(), [])

    def test_each_dispatch_timeout_uses_smallest_wall_monotonic_or_rollout_window(self):
        windows = (
            ("wall", 600, 15, 40, 15),
            ("monotonic", 600, 40, 12, 12),
            ("rollout", 7, 40, 40, 7),
        )
        for index, (kind, rollout, wall_left, monotonic_left, expected) in enumerate(windows):
            with self.subTest(kind=kind):
                context = copy.deepcopy(self.context)
                context["limits"]["wall_seconds"] = rollout
                context["cutoff_utc"] = self.utc(self.clock.wall + wall_left)
                context["cutoff_monotonic"] = self.clock.monotonic + monotonic_left
                client = FakeWireHTTP(self.response(), after_count=lambda: self.clock.advance(wall=2, monotonic=2))
                factory = Mock(return_value=client)
                self.invoke(self.controller(context, factory=factory), slot=self.slots[index])
                self.assertEqual(len(client.calls), 2)
                self.assertGreater(client.timeouts[0], 0)
                self.assertLessEqual(client.timeouts[0], expected)
                self.assertGreater(client.timeouts[1], 0)
                self.assertLessEqual(client.timeouts[1], expected - 2)

    def assert_expiry_between_count_and_generation(self, kind):
        context = copy.deepcopy(self.context)
        if kind == "wall":
            context["cutoff_utc"] = self.utc(self.clock.wall + 10)
            advance = lambda: self.clock.advance(wall=20)
        elif kind == "monotonic":
            context["cutoff_monotonic"] = self.clock.monotonic + 10
            advance = lambda: self.clock.advance(monotonic=20)
        else:
            context["limits"]["wall_seconds"] = 10
            advance = lambda: self.clock.advance(monotonic=20)
        client = FakeWireHTTP(self.response(), after_count=advance)
        factory = Mock(return_value=client)
        with self.assertRaises(RuntimeError):
            self.invoke(self.controller(context, factory=factory))
        self.assertEqual([endpoint for endpoint, _ in client.calls], ["/v1/responses/input_tokens"])
        self.terminal(error_type="BudgetStop")
        self.assertTrue((self.slots[0] / "01-count.json").is_file())
        self.assertFalse((self.slots[0] / "01-response.json").exists())

    def test_wall_expiry_between_count_and_generation_stops_send(self):
        self.assert_expiry_between_count_and_generation("wall")

    def test_monotonic_expiry_between_count_and_generation_stops_send(self):
        self.assert_expiry_between_count_and_generation("monotonic")

    def test_rollout_expiry_between_count_and_generation_stops_send(self):
        self.assert_expiry_between_count_and_generation("rollout")

    def test_context_hash_drift_after_constructor_refuses_before_factory(self):
        service = self.controller()
        self.context_path.write_bytes(self.context_path.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.invoke(service)
        self.factory.assert_not_called()
        self.assertFalse(self.slots[0].exists())
        self.assertEqual(self.generation_rows(), [])

    def test_context_drift_during_budget_check_is_rechecked_before_factory(self):
        service = self.controller()
        active = self.budget.active
        def mutate_context():
            active()
            self.context_path.write_bytes(self.context_path.read_bytes() + b" ")
        with patch.object(self.budget, "active", side_effect=mutate_context), self.assertRaises(RuntimeError):
            self.invoke(service)
        self.factory.assert_not_called()
        self.terminal(error_type="ValueError")
        self.assertEqual(self.generation_rows(), [])
        self.assertFalse((self.slots[0] / "01-count.json").exists())

    def test_cutoff_crossed_during_budget_check_is_rechecked_before_factory(self):
        for index, kind in enumerate(("wall", "monotonic")):
            with self.subTest(kind=kind):
                context = copy.deepcopy(self.context)
                context["cutoff_utc"] = self.utc(self.clock.wall + 10)
                context["cutoff_monotonic"] = self.clock.monotonic + 10
                service = self.controller(context)
                active = self.budget.active
                def cross_cutoff():
                    active()
                    self.clock.advance(**{kind: 20})
                with patch.object(self.budget, "active", side_effect=cross_cutoff), self.assertRaises(RuntimeError):
                    self.invoke(service, slot=self.slots[index])
                self.factory.assert_not_called()
                self.terminal(self.slots[index], "BudgetStop")
                self.assertEqual(self.generation_rows(), [])

    def test_context_hash_drift_between_count_and_generation_is_terminal_uncertain(self):
        self.client.after_count = lambda: self.context_path.write_bytes(self.context_path.read_bytes() + b" ")
        with self.assertRaises(RuntimeError):
            self.invoke()
        self.assertEqual([endpoint for endpoint, _ in self.client.calls], ["/v1/responses/input_tokens"])
        self.terminal(error_type="ValueError")
        self.assertTrue((self.slots[0] / "01-count.json").exists())
        self.assertTrue((self.slots[0] / "01-request.json").exists())
        self.assertFalse((self.slots[0] / "response.json").exists())
        rows = self.generation_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1:], (0, "uncertain"))
        self.assertGreater(rows[0][0], 0)
        failed = [json.loads(path.read_text()) for path in self.slots[0].glob("http-*.failed.json")]
        self.assertEqual(failed, [{"exception_type": "ValueError", "retry_allowed": False}])
        self.assertEqual(self.budget.close_calls, 0)

    def test_undeclared_outside_and_noncanonical_slot_refused_before_factory(self):
        candidates = (
            self.root / "roles" / "controller-04", self.owned / "outside-controller",
            str(self.root / "roles") + "/../roles/controller-01",
            "roles/controller-01",
        )
        service = self.controller()
        for slot in candidates:
            with self.subTest(slot=str(slot)), self.assertRaises(ValueError):
                self.invoke(service, slot=slot)
        self.factory.assert_not_called()
        self.assertEqual(self.generation_rows(), [])
        self.assertFalse(self.slots[0].exists())

    def test_slot_and_roles_symlinks_refused_before_factory(self):
        service = self.controller()
        outside = self.owned / "outside"
        outside.mkdir()
        self.slots[0].symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.invoke(service)
        with self.assertRaises(ValueError):
            self.controller()
        self.factory.assert_not_called()
        self.assertEqual(list(outside.iterdir()), [])

    def test_roles_ancestor_symlink_refused_before_factory(self):
        service = self.controller()
        outside = self.owned / "outside"
        outside.mkdir()
        (self.root / "roles").rmdir()
        (self.root / "roles").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.invoke(service)
        self.factory.assert_not_called()
        self.assertEqual(list(outside.iterdir()), [])

    def test_successful_slot_cannot_be_reused_or_modify_originals(self):
        service = self.controller()
        binding = self.invoke(service, slot=str(self.slots[0]))
        self.assertEqual(binding["path"], str(self.slots[0] / "response.json"))
        originals = self.saved_files(self.slots[0])
        rows = self.generation_rows()
        with self.assertRaises(FileExistsError):
            self.invoke(service)
        self.factory.assert_called_once_with()
        self.assertEqual(len(self.client.calls), 2)
        self.assertEqual(self.saved_files(self.slots[0]), originals)
        self.assertEqual(self.generation_rows(), rows)

    def test_semantic_failure_settles_cost_preserves_alias_and_is_terminal_only_for_slot(self):
        self.client.response = self.response(dict(self.chosen, feedback_sha256="d" * 64))
        with self.assertRaises(RuntimeError):
            self.invoke()
        self.terminal(error_type="ValueError")
        self.assertEqual((self.slots[0] / "response.json").read_bytes(),
                         (self.slots[0] / "01-response.json").read_bytes())
        rows = self.generation_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2], "settled")
        self.assertGreater(rows[0][1], 0)
        originals = self.saved_files(self.slots[0])
        with self.assertRaises(FileExistsError):
            self.invoke()
        self.assertEqual(self.saved_files(self.slots[0]), originals)
        self.assertEqual(self.generation_rows(), rows)
        self.client.response = self.response()
        self.invoke(slot=self.slots[1])
        self.assertEqual([row[2] for row in self.generation_rows()], ["settled", "settled"])
        self.assertEqual(self.budget.close_calls, 0)

    def test_transport_failure_is_uncertain_sanitized_and_prevents_retry(self):
        sentinel = "SYNTHETIC_UNTRUSTED_EXCEPTION_TEXT"
        self.client.response = TimeoutError(sentinel)
        service = self.controller()
        with self.assertRaises(RuntimeError):
            self.invoke(service)
        self.terminal(error_type="TimeoutError")
        rows = self.generation_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1:], (0, "uncertain"))
        self.assertGreater(rows[0][0], 0)
        summary = json.loads((self.slots[0] / "budget-summary.json").read_text())
        self.assertTrue(summary["blocked"])
        self.assertGreater(summary["unresolved_reserved_usd"], 0)
        self.assertFalse((self.slots[0] / "response.json").exists())
        originals = self.saved_files(self.slots[0])
        self.assertNotIn(sentinel, b"".join(originals.values()).decode())
        with self.assertRaises(FileExistsError):
            self.invoke(service)
        with self.assertRaises(BudgetStop):
            self.invoke(service, slot=self.slots[1])
        self.assertFalse(self.slots[1].exists())
        self.assertEqual(self.saved_files(self.slots[0]), originals)
        self.assertEqual(self.generation_rows(), rows)
        self.factory.assert_called_once_with()
        self.assertEqual(len(self.client.calls), 2)
        self.assertEqual(self.budget.close_calls, 0)

    def test_limits_require_exact_positive_ints_with_original_ceilings(self):
        for field, ceiling in LIMITS.items():
            for value in (False, True, 0, -1, 1.0, "1", ceiling + 1):
                with self.subTest(field=field, value=value):
                    context = copy.deepcopy(self.context)
                    context["limits"][field] = value
                    with self.assertRaises(ValueError):
                        self.controller(context)
        for limits in ({}, dict(LIMITS, extra=1)):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                self.controller(dict(self.context, limits=limits))
        self.factory.assert_not_called()
        self.assertEqual(self.generation_rows(), [])

    def test_context_schema_source_clock_rates_and_slot_configuration_are_exact(self):
        cases = [
            dict(self.context, schema="another_schema"), dict(self.context, source_commit="short"),
            dict(self.context, source_commit=True), dict(self.context, root="relative"),
            dict(self.context, cutoff_utc="2099-01-01T00:00:00+00:00"),
            dict(self.context, cutoff_monotonic=True), dict(self.context, cutoff_monotonic=-1),
            dict(self.context, cutoff_monotonic="1"), dict(self.context, slots=[]),
            dict(self.context, slots=[str(self.slots[0])] * 2),
            dict(self.context, slots=[str(slot) for slot in self.slots] + [str(self.root / "roles/controller-04")]),
            dict(self.context, slots=[str(self.owned / "outside")]),
            dict(self.context, slots=["roles/controller-01"]), dict(self.context, extra="not-a-grant"),
            dict(self.context, rates=dict(RATES, output="0")),
            dict(self.context, rates=dict(RATES, input="-1")),
            dict(self.context, rates=dict(RATES, api_model="")),
        ]
        for missing in self.context:
            value = copy.deepcopy(self.context)
            del value[missing]
            cases.append(value)
        for index, value in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(ValueError):
                self.controller(value)
        self.factory.assert_not_called()
        self.assertEqual(self.generation_rows(), [])

    def test_context_binding_hash_path_fields_and_symlink_are_checked_at_constructor(self):
        cases = [dict(self.binding, sha256="f" * 64), dict(self.binding, path="context.json"),
                 dict(self.binding, extra=True), {"path": self.binding["path"]},
                 dict(self.binding, sha256=True)]
        for binding in cases:
            with self.subTest(binding=binding), self.assertRaises(ValueError):
                self.controller(binding=binding)
        alias = self.owned / "context-alias.json"
        alias.symlink_to(self.context_path)
        with self.assertRaises(ValueError):
            self.controller(binding=dict(self.binding, path=str(alias)))
        self.factory.assert_not_called()

    def test_nonfinite_context_cutoff_is_rejected_before_factory(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            raw = json.dumps(dict(self.context, cutoff_monotonic=value), allow_nan=True).encode()
            self.context_path.write_bytes(raw)
            binding = {"path": str(self.context_path), "sha256": hashlib.sha256(raw).hexdigest()}
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.controller(binding=binding)
        self.factory.assert_not_called()
        self.assertEqual(self.generation_rows(), [])

    def test_invalid_prompt_lineage_is_refused_before_factory(self):
        updates = (
            {"parent_pair_sha256": "short"}, {"feedback_sha256": "d" * 64},
            {"parent_feedback_sha256": "d" * 64}, {"feedback_sha256": True},
        )
        service = self.controller()
        for update in updates:
            prompt = copy.deepcopy(self.prompt)
            prompt.update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.invoke(service, prompt=prompt)
        self.factory.assert_not_called()
        self.assertFalse(self.slots[0].exists())
        self.assertEqual(self.generation_rows(), [])

    def test_v2_external_budget_deadline_clips_each_http_timeout(self):
        self.budget.monotonic_deadline = self.clock.monotonic + 5
        self.client.after_count = lambda: self.clock.advance(wall=2, monotonic=2)
        self.invoke()
        self.assertEqual([endpoint for endpoint, _ in self.client.calls],
                         ["/v1/responses/input_tokens", "/v1/responses"])
        counterexample = json.dumps({
            "timeouts": self.client.timeouts, "external_budget_seconds_at_count": 5,
            "external_budget_seconds_at_generation": 3,
            "result": json.loads((self.slots[0] / "result.json").read_text()),
        }, sort_keys=True)
        self.assertLessEqual(self.client.timeouts[0], 5, counterexample)
        self.assertLessEqual(self.client.timeouts[1], 3, counterexample)
        self.assertGreater(self.client.timeouts[1], 0)
        self.assertEqual(self.budget.close_calls, 0)

    def test_v2_generation_crossing_external_budget_is_paid_but_not_accepted(self):
        self.budget.monotonic_deadline = self.clock.monotonic + 5
        clock = self.clock
        class FinishesAfterBudget(FakeWireHTTP):
            def post(self, endpoint, payload):
                value = super().post(endpoint, payload)
                if endpoint == "/v1/responses":
                    clock.advance(monotonic=6)
                return value
        self.client = FinishesAfterBudget(self.response())
        self.factory = Mock(return_value=self.client)
        error = None
        try:
            self.invoke()
        except RuntimeError as caught:
            error = caught
        original = self.slots[0] / "response.json"
        captured = self.slots[0] / "01-response.json"
        self.assertTrue(original.is_file())
        self.assertEqual(original.read_bytes(), captured.read_bytes())
        rows = self.generation_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2], "settled")
        self.assertGreater(rows[0][1], 0)
        counterexample = json.dumps({
            "external_budget_seconds_remaining": self.budget.monotonic_deadline - self.clock.monotonic,
            "result": json.loads((self.slots[0] / "result.json").read_text()),
            "decision_exists": (self.slots[0] / "decision.json").exists(),
            "original_alias_preserved": original.read_bytes() == captured.read_bytes(),
            "original_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
            "generation_rows": rows,
        }, sort_keys=True)
        self.assertIsInstance(error, RuntimeError, counterexample)
        self.terminal(error_type="BudgetStop")
        self.assertEqual(self.budget.close_calls, 0)

    def test_v2_summary_crossing_context_and_rollout_cutoff_is_not_accepted(self):
        context = copy.deepcopy(self.context)
        context["cutoff_utc"] = self.utc(self.clock.wall + 10)
        context["cutoff_monotonic"] = self.clock.monotonic + 10
        context["limits"]["wall_seconds"] = 10
        service = self.controller(context)
        summary = self.budget.summary
        def late_summary():
            value = summary()
            self.clock.advance(wall=20, monotonic=20)
            return value
        error = None
        with patch.object(self.budget, "summary", side_effect=late_summary):
            try:
                self.invoke(service)
            except RuntimeError as caught:
                error = caught
        original = self.slots[0] / "response.json"
        captured = self.slots[0] / "01-response.json"
        self.assertTrue(original.is_file())
        self.assertEqual(original.read_bytes(), captured.read_bytes())
        rows = self.generation_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2], "settled")
        self.assertGreater(rows[0][1], 0)
        self.assertTrue((self.slots[0] / "budget-summary.json").is_file())
        counterexample = json.dumps({
            "context_monotonic_seconds_remaining": context["cutoff_monotonic"] - self.clock.monotonic,
            "result": json.loads((self.slots[0] / "result.json").read_text()),
            "decision_exists": (self.slots[0] / "decision.json").exists(),
            "original_alias_preserved": original.read_bytes() == captured.read_bytes(),
            "original_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
            "generation_rows": rows,
        }, sort_keys=True)
        self.assertIsInstance(error, RuntimeError, counterexample)
        self.terminal(error_type="BudgetStop")
        self.assertEqual(self.budget.close_calls, 0)

    def test_caller_budget_and_factory_are_required_no_credentials_or_budget_creation(self):
        with self.assertRaises(TypeError):
            c.CapacityController(self.binding, budget=self.budget)
        with self.assertRaises(TypeError):
            c.CapacityController(self.binding, client_factory=self.factory)
        with self.assertRaises((TypeError, ValueError)):
            c.CapacityController(self.binding, budget=self.budget, client_factory=None)
        with self.assertRaises(ValueError):
            c.CapacityController(self.binding, budget=None, client_factory=self.factory)
        with patch.object(c, "credential", side_effect=AssertionError("No credential read is allowed")), \
                patch.object(c, "NightBudget", side_effect=AssertionError("Budget belongs to the caller")):
            self.invoke()
        self.assertEqual(self.budget.close_calls, 0)
        self.assertEqual(self.budget.db.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
