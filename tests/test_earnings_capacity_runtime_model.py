"""CP4e fixed-context checks; compose owned fixtures without TestCase inheritance."""
from copy import deepcopy
from pathlib import Path
import unittest

import test_earnings_capacity_runtime as owner
import earnings_entry as entry
from edgar_forecast_full_budget import MODELS

COUNT, GENERATE = "/v1/responses/input_tokens", "/v1/responses"
OTHER_MODEL, AMOUNT = "gpt-5.5-2026-04-23", 10_290_000
MISSING = object()


class CapacityRuntimeModelTests(unittest.TestCase):
    def setUp(self):
        self.case = owner.CapacityRuntimeOwnerTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def refuse(self, name, endpoint, mutate, *, metadata=False):
        suffix = "count" if endpoint == COUNT else "generation"
        fixture = self.case.fixture("model-" + name + "-" + suffix, purpose="controller_protocol")
        with self.assertRaises(ValueError), fixture.exchange():
            with fixture.open() as owned:
                budget = owned["budget"]
                role = owned["roles"]["controller"].__self__
                facade = role.factory()
                rates = deepcopy(role.context["rates"])
                request = owner.controller.capacity_request(fixture.prompt(), rates)
                mutate(request)
                if metadata:
                    alternate = dict(rates, api_model=OTHER_MODEL, effort="low")
                    role.context["rates"] = deepcopy(alternate)
                    fixture.rates.update(alternate)
                slot = Path(fixture.slots["controller"][0])
                slot.mkdir(parents=True)
                prefix = slot / "http-fixed-model"
                payload = request
                intent = {"endpoint": endpoint, "payload": payload,
                          "utc_epoch": self.case.wall, "retry_allowed": False}
                if endpoint == GENERATE:
                    # The alternate known-model loan/receipt/intent agree with
                    # each other; only the original fixed context disagrees.
                    model = request.get("model")
                    loan_model = model if model in MODELS else owner.MODEL
                    request_id = "model-loan-" + name
                    budget.reserve(request_id, loan_model, AMOUNT)
                    record = {"request_id": request_id, "reserved_nano_usd": AMOUNT,
                              "payload": deepcopy(request)}
                    owner._save(slot / "01-count.json", {"input_tokens": 20})
                    bound = owner._save(slot / "01-request.json", record)
                    payload = dict(request, max_output_tokens=1024, service_tier="default", store=False)
                    intent.update(payload=payload, complete_reservation=record,
                                  budget_request_id=request_id, request_receipt_sha256=bound["sha256"])
                owner._save(prefix.with_suffix(".intent.json"), intent)
                facade.record_prefix = prefix
                rows = fixture.rows()
                originals = {path: path.read_bytes() for path in slot.iterdir()}
                context = Path(owned["context_bindings"]["controller"]["path"])
                originals.update({context: context.read_bytes(), fixture.claim_path(): fixture.claim_path().read_bytes()})
                facade.post(endpoint, payload)
        self.case.assert_closed_once(budget)
        self.assertEqual(fixture.calls, [])
        self.assertEqual(fixture.connections, [])
        self.assertEqual(fixture.rows(), rows)
        self.assertEqual({path: path.read_bytes() for path in originals}, originals)
        self.assertEqual(fixture.rows()[0], ("fixture-prior", owner.MODEL, 10000, 1000, "settled"))
        self.assertTrue(fixture.claim_path().is_file())
        self.assertEqual(fixture.terminal()["status"], "FAILED_NO_RETRY")
        self.assertEqual(fixture.terminal()["error_type"], "ValueError")
        self.assertIs(fixture.terminal()["retry_allowed"], False)
        if endpoint == GENERATE:
            self.assertEqual(fixture.rows()[-1][2:], (AMOUNT, 0, "reserved"))
            self.assertEqual(fixture.terminal()["budget_summary"]["unresolved_reserved_usd"], AMOUNT / 1e9)
        else:
            self.assertEqual(len(fixture.rows()), 1)

    def test_original_actual_controller_keeps_fixed_payload_raw_alias_and_settlement(self):
        fixture = self.case.fixture("model-original-positive", purpose="controller_protocol")
        with fixture.exchange(), fixture.open() as owned:
            budget = owned["budget"]
            result = owned["roles"]["controller"](fixture.prompt(), fixture.slots["controller"][0])
            slot = Path(fixture.slots["controller"][0])
            self.assertEqual(Path(result["path"]).read_bytes(), (slot / "01-response.json").read_bytes())
            intents = {entry.strict_json(path.read_text())["endpoint"]: path
                       for path in slot.glob("http-*.intent.json")}
            self.assertEqual(owner._raw_receipt(intents[COUNT]).read_bytes(), fixture.count_raw)
            self.assertEqual(owner._raw_receipt(intents[GENERATE]).read_bytes(), fixture.generation)
        self.case.assert_closed_once(budget)
        self.assertEqual([endpoint for endpoint, _ in fixture.calls], [COUNT, GENERATE])
        for _, payload in fixture.calls:
            self.assertEqual(payload["model"], owner.MODEL)
            self.assertEqual(payload["reasoning"], {"effort": "xhigh"})
        self.assertEqual(fixture.rows()[-1][3:], (92800, "settled"))
        self.assertEqual(sum(row[3] for row in fixture.rows()), 93800)
        self.assertEqual(fixture.terminal()["status"], "COMPLETED_COMPONENT_CONTEXT")

    def test_consistent_alternate_known_model_is_rejected_by_both_endpoints(self):
        for endpoint in (COUNT, GENERATE):
            with self.subTest(endpoint=endpoint):
                self.refuse("alternate-model", endpoint, lambda request: request.update(model=OTHER_MODEL))

    def test_consistent_alternate_effort_is_rejected_by_both_endpoints(self):
        for endpoint in (COUNT, GENERATE):
            with self.subTest(endpoint=endpoint):
                self.refuse("alternate-effort", endpoint,
                            lambda request: request.update(reasoning={"effort": "low"}))

    def test_missing_or_malformed_model_and_reasoning_are_rejected_by_both_endpoints(self):
        variants = (("model", MISSING), ("model", None), ("model", 1), ("model", {}),
                    ("reasoning", MISSING), ("reasoning", None), ("reasoning", "xhigh"),
                    ("reasoning", {}), ("reasoning", {"effort": None}),
                    ("reasoning", {"effort": "xhigh", "extra": False}))
        for index, (field, value) in enumerate(variants):
            def mutate(request, field=field, value=value):
                if value is MISSING:
                    request.pop(field)
                else:
                    request[field] = value
            for endpoint in (COUNT, GENERATE):
                with self.subTest(field=field, value=value, endpoint=endpoint):
                    self.refuse("malformed-" + str(index), endpoint, mutate)

    def test_new_caller_rates_metadata_cannot_redefine_the_original_context(self):
        for endpoint in (COUNT, GENERATE):
            with self.subTest(endpoint=endpoint):
                self.refuse("new-rates", endpoint,
                            lambda request: request.update(model=OTHER_MODEL, reasoning={"effort": "low"}),
                            metadata=True)


if __name__ == "__main__":
    unittest.main()
