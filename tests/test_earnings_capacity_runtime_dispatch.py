"""CP4d permanent per-send/cleanup regressions; no live resources or network.

Compose the original owner fixture without inheriting/importing a discoverable
TestCase. Reviewer v1 artifacts and the original owner test stay immutable.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

import test_earnings_capacity_runtime as owner
import earnings_clock as clock
import earnings_entry as entry
from edgar_forecast_budget import BudgetStop
from edgar_forecast_openai import OpenAIHTTP
from earnings_http import RawOpenAIHTTP

COUNT = "/v1/responses/input_tokens"
GENERATE = "/v1/responses"
AMOUNT = 10_290_000
DRIFTS = ("spec", "source", "other-context", "clock", "seal", "resealed-clock",
          "rebound-spec", "boot", "expired", "mono-rollback")


class CapacityRuntimeDispatchTests(unittest.TestCase):
    def setUp(self):
        self.case = owner.CapacityRuntimeOwnerTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.origin = self.case.wall, self.case.mono
        self.drift_guards = []

    def fixture(self, name, *, source=False, purpose="capacity_episode"):
        if not source:
            return self.case.fixture("dispatch-" + name, purpose=purpose)
        # The only deliberately mutable executable bytes belong to this fresh
        # temporary source-bound fixture, never an existing production/test file.
        path = self.case.workspace / (name + "-factory.py")
        body = ("def construct(context_binding, *, budget, client_factory):\n"
                "    return controller.CapacityController(context_binding, "
                "budget=budget, client_factory=client_factory).propose\n")
        path.write_text(body)
        module_name = "cp4_dispatch_factory_" + name.replace("-", "_")
        module = types.ModuleType(module_name)
        module.__file__, module.controller = str(path), owner.controller
        sys.modules[module_name] = module
        self.addCleanup(sys.modules.pop, module_name, None)
        exec(compile(body, str(path), "exec"), module.__dict__)
        fixture = self.case.fixture("dispatch-" + name, purpose=purpose,
                                    factories={"controller": module.construct})
        fixture.factory_source = path
        return fixture

    def assert_failed(self, fixture, budget):
        self.case.assert_closed_once(budget)
        result = fixture.terminal()
        self.assertEqual(result["status"], "FAILED_NO_RETRY")
        self.assertIs(result["retry_allowed"], False)
        self.assertNotIn(owner.PRIVATE, fixture.claim_path(result=True).read_text())
        self.assertTrue(fixture.claim_path().is_file())
        return result

    def mutate(self, kind, fixture, owned):
        if kind == "spec":
            Path(fixture.binding["path"]).write_bytes(b"{}\n")
        elif kind == "source":
            fixture.factory_source.write_bytes(fixture.factory_source.read_bytes() + b"# changed\n")
        elif kind == "other-context":
            Path(owned["context_bindings"]["author"]["path"]).write_bytes(b"{}\n")
        elif kind == "clock":
            Path(owned["clock_binding"]["path"]).write_bytes(b"{}\n")
        elif kind == "seal":
            (fixture.root / "clock.binding.json").write_bytes(b"{}\n")
        elif kind == "resealed-clock":
            value = deepcopy(owned["window"])
            value["wall_origin"] -= 3600
            value["cutoff_monotonic"] += 3600
            value["deadline_monotonic"] += 3600
            path = Path(owned["clock_binding"]["path"])
            path.write_bytes(owner._wire(value))
            rebound = owner._pin(path)
            (fixture.root / "clock.binding.json").write_bytes(owner._wire(rebound))
            # Caller-visible metadata must not replace the owner's original seal.
            owned["clock_binding"].update(rebound)
            owned["window"].update(value)
        elif kind == "rebound-spec":
            value = deepcopy(fixture.spec)
            value["additional_cap_nano_usd"] -= 1
            path = Path(fixture.binding["path"])
            path.write_bytes(owner._wire(value))
            fixture.binding.update(owner._pin(path))
        elif kind == "boot":
            guard = patch.object(clock, "boot_id",
                                 return_value="22222222-2222-2222-2222-222222222222")
            guard.start()
            self.addCleanup(guard.stop)
            self.drift_guards.append(guard)
        elif kind == "expired":
            self.case.wall -= 3600
            self.case.mono = owned["window"]["cutoff_monotonic"] + 1
        elif kind == "mono-rollback":
            self.case.mono = owned["window"]["monotonic_origin"] - 1
        else:
            raise AssertionError("Undeclared synthetic drift")

    def probe_drift(self, kind, stage):
        self.case.wall, self.case.mono = self.origin
        for guard in reversed(self.drift_guards):
            guard.stop()
        self.drift_guards.clear()
        fixture = self.fixture(stage + "-" + kind, source=kind == "source")
        state, returned, caught = {}, False, None
        original_receipt, original_save = entry.ReceiptHTTP.post, entry.durable_json
        original_raw = RawOpenAIHTTP.post

        def after_count(client, endpoint, payload):
            response = original_receipt(client, endpoint, payload)
            if endpoint == COUNT:
                self.mutate(kind, fixture, state["owned"])
            return response

        def before_send(path, value):
            result = original_save(path, value)
            if Path(path).name.startswith("http-") and Path(path).name.endswith(".intent.json") \
                    and value.get("endpoint") == GENERATE:
                self.mutate(kind, fixture, state["owned"])
            return result

        def after_generation(client, endpoint, payload):
            response = original_raw(client, endpoint, payload)
            if endpoint == GENERATE:
                self.mutate(kind, fixture, state["owned"])
            return response

        selected = {"after-count": patch.object(entry.ReceiptHTTP, "post", after_count),
                    "before-send": patch.object(entry, "durable_json", before_send),
                    "after-generation": patch.object(RawOpenAIHTTP, "post", after_generation)}[stage]
        with fixture.exchange(), selected:
            try:
                with fixture.open() as owned:
                    state["owned"], budget = owned, owned["budget"]
                    owned["roles"]["controller"](fixture.prompt(), fixture.slots["controller"][0])
                    returned = True
            except BaseException as error:
                caught = error
        self.assertIsNotNone(caught)
        self.assertFalse(returned, "A drifted send/response cannot become an accepted decision")
        expected = [COUNT, GENERATE] if stage == "after-generation" else [COUNT]
        self.assertEqual([endpoint for endpoint, _ in fixture.calls], expected)
        output = Path(fixture.slots["controller"][0])
        self.assertFalse((output / "decision.json").exists())
        self.assertEqual(entry.strict_json((output / "result.json").read_text())["status"], "FAILED_NO_RETRY")
        self.assert_failed(fixture, budget)
        self.assertEqual(fixture.rows()[0], ("fixture-prior", owner.MODEL, 10000, 1000, "settled"))
        if kind == "expired" and stage == "after-count":
            self.assertEqual(len(fixture.rows()), 1)
        else:
            self.assertEqual([row[2:] for row in fixture.rows()[1:]], [(AMOUNT, 0, "uncertain")])
            self.assertEqual(fixture.terminal()["budget_summary"]["unresolved_reserved_usd"], AMOUNT / 1e9)
        intents = {entry.strict_json(p.read_text())["endpoint"]: p for p in output.glob("http-*.intent.json")}
        self.assertEqual(owner._raw_receipt(intents[COUNT]).read_bytes(), fixture.count_raw)
        if stage == "after-generation":
            self.assertEqual(owner._raw_receipt(intents[GENERATE]).read_bytes(), fixture.generation)
        elif GENERATE in intents:
            self.assertFalse(owner._raw_receipt(intents[GENERATE]).exists())
        self.assertTrue(all(connection.closed for connection in fixture.connections))

    def test_runtime_spec_drift_between_count_and_generation_blocks_dispatch(self):
        self.probe_drift("spec", "after-count")

    def test_shared_sealed_clock_drift_between_count_and_generation_blocks_dispatch(self):
        self.probe_drift("clock", "after-count")

    def test_other_role_context_drift_between_count_and_generation_blocks_dispatch(self):
        self.probe_drift("other-context", "after-count")

    def test_bound_factory_source_drift_between_count_and_generation_blocks_dispatch(self):
        self.probe_drift("source", "after-count")

    def test_boot_drift_between_count_and_generation_blocks_dispatch(self):
        self.probe_drift("boot", "after-count")

    def test_resealed_clock_and_mutated_public_metadata_cannot_replace_original(self):
        self.probe_drift("resealed-clock", "after-count")

    def test_rehashed_runtime_spec_and_mutated_caller_binding_cannot_replace_original(self):
        self.probe_drift("rebound-spec", "after-count")

    def test_all_shared_boundaries_are_rechecked_after_intent_before_physical_generation(self):
        for kind in DRIFTS:
            with self.subTest(kind=kind):
                self.probe_drift(kind, "before-send")

    def test_all_shared_boundaries_are_rechecked_after_physical_generation(self):
        for kind in DRIFTS:
            with self.subTest(kind=kind):
                self.probe_drift(kind, "after-generation")

    def test_caller_dictionary_mutations_leave_original_owner_metadata_and_clock_frozen(self):
        fixture = self.fixture("public-copies", purpose="controller_protocol")
        original_binding = deepcopy(fixture.binding)
        with fixture.exchange(), fixture.open() as owned:
            budget = owned["budget"]
            original_clock, original_window = deepcopy(owned["clock_binding"]), deepcopy(owned["window"])
            fixture.binding.update(path=str(fixture.home / "not-the-original.json"), sha256="f" * 64)
            owned["clock_binding"].update(path=str(fixture.home / "not-the-clock.json"), sha256="f" * 64)
            owned["window"]["cutoff_monotonic"] += 3600
            owned["window"]["monotonic_origin"] -= 3600
            owned["context_bindings"]["controller"].update(sha256="f" * 64)
            original = owned["roles"]["controller"](fixture.prompt(), fixture.slots["controller"][0])
            self.assertEqual(budget.monotonic_deadline, original_window["cutoff_monotonic"])
            self.assertEqual(Path(original["path"]).read_bytes(),
                             (Path(fixture.slots["controller"][0]) / "01-response.json").read_bytes())
        self.case.assert_closed_once(budget)
        self.assertEqual(fixture.terminal()["runtime"], original_binding)
        self.assertEqual(fixture.terminal()["clock"], original_clock)
        self.assertEqual(fixture.rows()[-1][3:], (92800, "settled"))

    def test_public_window_mutation_and_backward_wall_time_do_not_extend_dispatch(self):
        fixture = self.fixture("public-window-expiry", purpose="controller_protocol")
        state, original_receipt, caught = {}, entry.ReceiptHTTP.post, None
        def counted_then_expire(client, endpoint, payload):
            response = original_receipt(client, endpoint, payload)
            if endpoint == COUNT:
                owned = state["owned"]
                cutoff = owned["window"]["cutoff_monotonic"]
                owned["window"]["cutoff_monotonic"] += 3600
                self.case.wall -= 3600
                self.case.mono = cutoff + 1
            return response
        with fixture.exchange(), patch.object(entry.ReceiptHTTP, "post", counted_then_expire):
            try:
                with fixture.open() as owned:
                    state["owned"], budget = owned, owned["budget"]
                    owned["roles"]["controller"](fixture.prompt(), fixture.slots["controller"][0])
            except BaseException as error:
                caught = error
        self.assertIsNotNone(caught)
        self.assertEqual([endpoint for endpoint, _ in fixture.calls], [COUNT])
        self.assertEqual(len(fixture.rows()), 1)
        self.assert_failed(fixture, budget)

    def test_exact_own_pending_request_passes_twice_and_preserves_raw_alias_and_charge(self):
        fixture = self.fixture("own-pending-positive", purpose="controller_protocol")
        seen = []
        with fixture.exchange(), fixture.open() as owned:
            budget, check = owned["budget"], owned["budget"].check_reserved
            def observed(*loan):
                seen.append((loan, fixture.rows()[-1]))
                with self.assertRaises(BudgetStop):
                    budget.active()  # A pending request never gets ordinary new-request credit.
                return check(*loan)
            budget.check_reserved = observed
            original = owned["roles"]["controller"](fixture.prompt(), fixture.slots["controller"][0])
            output = Path(fixture.slots["controller"][0])
            reservation = entry.strict_json((output / "01-request.json").read_text())
            expected = (reservation["request_id"], owner.MODEL, AMOUNT)
            self.assertEqual([loan for loan, _ in seen], [expected, expected])
            self.assertEqual([row[2:] for _, row in seen], [(AMOUNT, 0, "reserved")] * 2)
            self.assertEqual(Path(original["path"]).read_bytes(), (output / "01-response.json").read_bytes())
            intents = {entry.strict_json(p.read_text())["endpoint"]: p for p in output.glob("http-*.intent.json")}
            self.assertEqual(owner._raw_receipt(intents[COUNT]).read_bytes(), fixture.count_raw)
            self.assertEqual(owner._raw_receipt(intents[GENERATE]).read_bytes(), fixture.generation)
            self.assertEqual(fixture.rows()[-1][3:], (92800, "settled"))
            self.assertEqual(sum(row[3] for row in fixture.rows()), 1000 + 92800)
        self.case.assert_closed_once(budget)
        self.assertEqual(fixture.terminal()["error_type"], None)

    def test_raw_facade_forwards_timeout_and_record_prefix_without_reading_key_at_creation(self):
        fixture = self.fixture("raw-properties", purpose="controller_protocol")
        with fixture.open() as owned:
            raw = fixture.make_http()
            fixture.client_factory.side_effect = lambda: raw
            def forbidden_key(client):
                raise AssertionError("Facade construction must not inspect/copy credentials")
            with patch.object(RawOpenAIHTTP, "key", new=property(forbidden_key), create=True):
                facade = owned["roles"]["controller"].__self__.factory()
            self.assertIsInstance(facade, RawOpenAIHTTP)
            self.assertNotIn("key", vars(facade))
            facade.timeout = 17
            self.assertEqual(raw.timeout, 17)
            raw.timeout = 13
            self.assertEqual(facade.timeout, 13)
            prefix = Path(fixture.slots["controller"][0]) / "http-forwarded"
            facade.record_prefix = prefix
            self.assertEqual(raw.record_prefix, prefix)
            raw.record_prefix = None
            self.assertIsNone(facade.record_prefix)
        self.assertEqual(fixture.calls, [])

    def manual(self, fixture, owned):
        output = Path(fixture.slots["controller"][0])
        output.mkdir(parents=True)
        facade = owned["roles"]["controller"].__self__.factory()
        request = owner.controller.capacity_request(fixture.prompt(), fixture.rates)
        owned["budget"].reserve("manual-owned-request", owner.MODEL, AMOUNT)
        record = {"request_id": "manual-owned-request", "reserved_nano_usd": AMOUNT, "payload": request}
        owner._save(output / "01-count.json", {"input_tokens": 20})
        owner._save(output / "01-request.json", record)
        payload = dict(request, max_output_tokens=1024, service_tier="default", store=False)
        prefix = output / "http-manual"
        intent = {"endpoint": GENERATE, "payload": payload, "utc_epoch": self.case.wall,
            "retry_allowed": False, "complete_reservation": record,
            "budget_request_id": record["request_id"],
            "request_receipt_sha256": owner._pin(output / "01-request.json")["sha256"]}
        return facade, prefix, record, payload, intent

    def manual_refusal(self, name, mutate, *, endpoint=GENERATE):
        fixture = self.fixture("manual-" + name, purpose="controller_protocol")
        caught = None
        with fixture.exchange():
            try:
                with fixture.open() as owned:
                    budget = owned["budget"]
                    facade, prefix, record, payload, intent = self.manual(fixture, owned)
                    mutate(fixture, owned, prefix, record, payload, intent)
                    owner._save(prefix.with_suffix(".intent.json"), intent)
                    facade.record_prefix = prefix
                    with self.assertRaises((ValueError, BudgetStop, KeyError, IndexError)):
                        facade.post(endpoint, payload)
            except BudgetStop as error:
                caught = error  # Normal owner closing still refuses unresolved own credit.
        self.assertIsNotNone(caught)
        self.assertEqual(fixture.calls, [], "Rejected intent/reservation must never reach fake HTTPS")
        self.assert_failed(fixture, budget)
        self.assertEqual(fixture.rows()[0][3], 1000)
        self.assertTrue(all(row[3] == 0 for row in fixture.rows()[1:]))

    def test_wrong_inflight_identity_model_amount_hash_or_competing_pending_refuses_send(self):
        def change_record(field, value):
            def mutate(fixture, owned, prefix, record, payload, intent):
                if field == "model":
                    record["payload"]["model"] = value
                    payload["model"] = value
                else:
                    record[field] = value
                path = prefix.parent / "01-request.json"
                path.write_bytes(owner._wire(record))
                intent["request_receipt_sha256"] = owner._pin(path)["sha256"]
            return mutate
        def extra_pending(fixture, owned, prefix, record, payload, intent):
            owned["budget"].db.execute("INSERT INTO requests VALUES ('other-pending',?,?,0,'reserved')",
                                       (owner.MODEL, 1))
        changes = (
            ("id", lambda f, o, p, r, q, i: i.update(budget_request_id="another-id")),
            ("amount", change_record("reserved_nano_usd", AMOUNT + 1)),
            ("model", change_record("model", "gpt-5.5-2026-04-23")),
            ("hash", lambda f, o, p, r, q, i: i.update(request_receipt_sha256="f" * 64)),
            ("other-pending", extra_pending),
        )
        for name, mutate in changes:
            with self.subTest(name=name):
                self.manual_refusal(name, mutate)

    def test_physical_model_or_extra_payload_cannot_borrow_original_models_reservation(self):
        for name, addition in (("physical-model", {"model": "gpt-5.5-2026-04-23"}),
                ("stored", {"store": True}), ("tier", {"service_tier": "priority"}),
                ("extra-field", {"unreviewed": True})):
            with self.subTest(name=name):
                self.manual_refusal(name, lambda f, o, p, r, q, i, add=addition: q.update(add))

    def test_physical_output_token_cap_requires_exact_bounded_positive_integer(self):
        for index, value in enumerate((True, 0, -1, 1025, 1024.0)):
            with self.subTest(value=value):
                self.manual_refusal("output-" + str(index),
                    lambda f, o, p, r, q, i, value=value: q.update(max_output_tokens=value))

    def test_count_endpoint_cannot_bypass_ordinary_pending_budget_stop(self):
        def mutate(fixture, owned, prefix, record, payload, intent):
            intent["endpoint"] = COUNT
        self.manual_refusal("count-pending", mutate, endpoint=COUNT)

    def test_unknown_endpoint_and_missing_intent_refuse_without_network(self):
        fixture = self.fixture("no-intent", purpose="controller_protocol")
        with fixture.exchange(), fixture.open() as owned:
            facade = owned["roles"]["controller"].__self__.factory()
            for endpoint in (COUNT, GENERATE, "/v1/unreviewed"):
                with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                    facade.post(endpoint, {"model": owner.MODEL})
        self.assertEqual(fixture.calls, [])
        self.assertEqual(len(fixture.rows()), 1)

    def test_raw_incompatible_clients_are_refused_before_any_post_or_fallback(self):
        for index, client in enumerate((object(), Mock(timeout=60), OpenAIHTTP("", 60))):
            with self.subTest(client=type(client).__name__):
                fixture = self.fixture("incompatible-" + str(index), purpose="controller_protocol")
                factory = Mock(return_value=client)
                with self.assertRaises(ValueError):
                    with fixture.open(client_factory=factory) as owned:
                        budget = owned["budget"]
                        owned["roles"]["controller"].__self__.factory()
                self.assert_failed(fixture, budget)
                factory.assert_called_once()
                self.assertEqual(fixture.calls, [])
                if isinstance(client, Mock):
                    client.post.assert_not_called()

    def test_created_raw_facade_cannot_dispatch_after_owner_lifetime_ends(self):
        fixture = self.fixture("retained-client", purpose="controller_protocol")
        with fixture.exchange(), self.assertRaises(BudgetStop):
            with fixture.open() as owned:
                budget = owned["budget"]
                facade, prefix, record, payload, intent = self.manual(fixture, owned)
                owner._save(prefix.with_suffix(".intent.json"), intent)
                facade.record_prefix = prefix
        with fixture.exchange(), self.assertRaises(BudgetStop):
            facade.post(GENERATE, payload)
        self.assertEqual(fixture.calls, [])
        self.assert_failed(fixture, budget)
        self.assertEqual(fixture.rows()[-1][2:], (AMOUNT, 0, "reserved"))

    def cleanup_probe(self, name, *, caller=None, summary=None, close=None):
        fixture = self.fixture(name, purpose="controller_protocol")
        caught = None
        try:
            with fixture.open() as owned:
                budget = owned["budget"]
                if summary is not None:
                    budget.summary = Mock(side_effect=summary)
                if close is not None:
                    original = budget.close
                    def interrupted_close():
                        original()
                        raise close
                    budget.close = interrupted_close
                if caller is not None:
                    raise caller
        except BaseException as error:
            caught = error
        expected = caller if caller is not None else summary if summary is not None else close
        self.assertIs(caught, expected)
        terminal = self.assert_failed(fixture, budget)
        self.assertEqual(terminal["error_type"], type(expected).__name__)
        self.assertEqual(fixture.calls, [])
        self.assertEqual(fixture.rows(), [("fixture-prior", owner.MODEL, 10000, 1000, "settled")])
        fixture.client_factory.assert_not_called()

    def test_summary_baseexception_keeps_sanitized_terminal_and_closes_once(self):
        self.cleanup_probe("summary-interrupt", summary=KeyboardInterrupt(owner.PRIVATE))

    def test_close_baseexception_keeps_sanitized_terminal_and_original_interrupt(self):
        self.cleanup_probe("close-interrupt", close=KeyboardInterrupt(owner.PRIVATE))

    def test_summary_systemexit_is_durable_and_preserves_original_identity(self):
        self.cleanup_probe("summary-systemexit", summary=SystemExit(owner.PRIVATE))

    def test_first_cleanup_interrupt_is_preserved_when_close_also_interrupts(self):
        self.cleanup_probe("two-cleanup-interrupts", summary=KeyboardInterrupt(owner.PRIVATE),
                           close=SystemExit(owner.PRIVATE))

    def test_caller_first_error_is_not_masked_by_summary_and_close_interrupts(self):
        self.cleanup_probe("caller-first", caller=ValueError(owner.PRIVATE),
                           summary=KeyboardInterrupt(owner.PRIVATE), close=SystemExit(owner.PRIVATE))

    def test_caller_interrupt_is_not_masked_by_ordinary_cleanup_failure(self):
        self.cleanup_probe("caller-interrupt-first", caller=KeyboardInterrupt(owner.PRIVATE),
                           summary=OSError(owner.PRIVATE), close=OSError(owner.PRIVATE))


if __name__ == "__main__":
    unittest.main()
