"""Offline tests for the trusted Gate 1 exact-request plan compiler."""
from __future__ import annotations

import copy
import hashlib
from unittest import mock
import unittest
from urllib.parse import parse_qs, urlsplit

from market_rsi import canonical, digest
from supervisor_harness.build_p0_gate1_controller_packet import build
from supervisor_harness.p0_gate1_plan_compiler import (
    BUNDLE_SCHEMA,
    EXACT_MANIFEST_SCHEMA,
    SYNTHETIC_CATALOG_COMMITMENT_ID,
    compile_exact_request_plan,
)
from supervisor_harness.p0_gate1_research_contract import (
    DECISION_SCHEMA,
    EXACT_TRADE_SAMPLE_RULE,
)
from supervisor_harness.p0_gate1_sample_materializer import materialize


def synthetic_catalog() -> bytes:
    dates_and_starts = (
        ("2025-09-04", 1_757_016_000),
        ("2025-09-11", 1_757_620_800),
        ("2025-09-18", 1_758_225_600),
        ("2025-09-25", 1_758_830_400),
        ("2025-10-02", 1_759_435_200),
    )
    rows = []
    for number, (game_date, start) in enumerate(dates_and_starts, 1):
        rows.append({
            "game_date": game_date,
            "game_id": f"train-game-{number:03d}",
            "split_role": "market_train",
            "condition_id": "0x" + f"{number:064x}",
            "asset_ids": [str(10_000 + number), str(20_000 + number)],
            "start_timestamp": start,
            "end_timestamp": start + 61_200,
        })
    value = {
        "schema": "market_p0_gate1_train_catalog_v1",
        "catalog_id": "gate1-train-canary-catalog-v1",
        "source_id": "polymarket_public_trades_v1",
        "data_scope": "public_train_only",
        "rows": rows,
    }
    return canonical(value).encode("utf-8")


def packet() -> dict:
    return build(
        {"schema": "market_p0_gate0_verdict_v1",
         "metadata_inventory_passed": True,
         "2025_formal_final_admitted": False},
        {"schema": "market_controller_b_live_acceptance_v1", "passed": True,
         "claim_boundaries": {
             "bounded_live_transport_and_accounting_proven": True,
             "formal_admission": False,
             "prediction_improvement_proven": False,
         }},
    )


def decision() -> dict:
    return {
        "schema": DECISION_SCHEMA,
        "investigation_id": "gate1-exact-trades-canary",
        "question_id": "2025_whole_season_trade_access",
        "source_id": "polymarket_official_trades",
        "hypothesis": "Three fixed Train markets can test bounded public trade retrieval.",
        "fixed_sample_rule": EXACT_TRADE_SAMPLE_RULE,
        "requested_operations": ["fetch_fixed_public_sample"],
        "expected_evidence": "Six exact public GET request receipts or one terminal failure.",
        "max_requests": 6,
        "max_bytes": 2_000_000,
        "max_minutes": 15,
        "max_provider_cost_usd": "0",
        "stop_rule": "Stop after the six fixed pages or the first boundary failure.",
    }


class Gate1PlanCompilerTests(unittest.TestCase):
    def compile(self, **changes: object) -> dict:
        selected = decision()
        selected.update(changes)
        return compile_exact_request_plan(
            selected, packet(), synthetic_catalog(),
            SYNTHETIC_CATALOG_COMMITMENT_ID)

    def test_compiles_one_hash_bound_exact_request_manifest(self) -> None:
        bundle = self.compile()
        self.assertEqual(bundle["schema"], BUNDLE_SCHEMA)
        manifest = bundle["exact_request_manifest"]
        self.assertEqual(manifest["schema"], EXACT_MANIFEST_SCHEMA)
        self.assertEqual(bundle["exact_request_manifest_canonical_sha256"],
                         digest(manifest))
        self.assertEqual(manifest["request_count"], 6)
        self.assertEqual(manifest["materialization_binding"]["sample_ids"],
                         ["train-game-001", "train-game-003", "train-game-005"])
        self.assertEqual(
            manifest["materialization_binding"]["materialization_sha256"],
            bundle["materialization"]["materialization_sha256"])
        self.assertEqual(
            manifest["materialization_binding"]["request_plan_inputs_sha256"],
            digest(bundle["materialization"]["request_plan_inputs"]))
        self.assertEqual(manifest["handler_chain"]["future_executor_handler_id"],
                         None)
        self.assertFalse(manifest["execution_policy"][
            "network_execution_authorized"])
        self.assertTrue(bundle["claim_boundaries"]["synthetic_canary_only"])
        self.assertEqual(
            bundle["execution_receipt_contract"]["request_manifest_sha256"],
            digest(manifest))
        for request in manifest["requests"]:
            parsed = urlsplit(request["url"])
            query = parse_qs(parsed.query)
            self.assertEqual((parsed.scheme, parsed.netloc, parsed.path),
                             ("https", "data-api.polymarket.com", "/trades"))
            self.assertEqual(query["limit"], ["100"])
            self.assertNotIn("Authorization", request["headers"])

    def test_same_exact_inputs_compile_identically(self) -> None:
        self.assertEqual(self.compile(), self.compile())

    def test_catalog_hash_is_registry_authority_not_caller_input(self) -> None:
        changed = bytearray(synthetic_catalog())
        changed[-1:] = b" "
        self.assertEqual(len(hashlib.sha256(changed).hexdigest()), 64)
        with self.assertRaisesRegex(ValueError, "trusted commitment"):
            compile_exact_request_plan(
                decision(), packet(), bytes(changed),
                SYNTHETIC_CATALOG_COMMITMENT_ID)
        with self.assertRaisesRegex(ValueError, "commitment registry"):
            compile_exact_request_plan(
                decision(), packet(), synthetic_catalog(),
                "caller-supplied-catalog")

    def test_controller_cannot_choose_rule_url_endpoint_or_trusted_limits(self) -> None:
        cases = (
            {"fixed_sample_rule": "first middle last"},
            {"url": "https://example.invalid/trades"},
            {"endpoint": "/another"},
            {"max_requests": 7},
            {"max_bytes": 1_999_999},
            {"max_minutes": 14},
            {"max_provider_cost_usd": "0.01"},
        )
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.compile(**changes)

    def test_wrong_question_or_operation_fails_closed(self) -> None:
        for changes in (
            {"question_id": "2023_real_fill_sparsity"},
            {"requested_operations": ["inspect_official_documentation"]},
            {"requested_operations": ["fetch_fixed_public_sample",
                                      "inspect_official_documentation"]},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.compile(**changes)

    def test_recomputes_complete_row_hash_before_query_builder(self) -> None:
        raw = synthetic_catalog()
        real = materialize(raw, hashlib.sha256(raw).hexdigest())
        forged = copy.deepcopy(real)
        forged["request_plan_inputs"][0]["input_sha256"] = "f" * 64
        forged["request_plan_inputs_sha256"] = digest(
            forged["request_plan_inputs"])
        forged["sample_commitments"][0]["input_sha256"] = "f" * 64
        body = {key: value for key, value in forged.items()
                if key != "materialization_sha256"}
        forged["materialization_sha256"] = digest(body)
        with mock.patch(
                "supervisor_harness.p0_gate1_plan_compiler.materialize",
                return_value=forged):
            with self.assertRaisesRegex(ValueError, "complete trusted catalog rows"):
                self.compile()

    def test_verifies_materialization_and_request_input_commitments(self) -> None:
        raw = synthetic_catalog()
        real = materialize(raw, hashlib.sha256(raw).hexdigest())
        bad_materialization = copy.deepcopy(real)
        bad_materialization["materialization_sha256"] = "0" * 64
        with mock.patch(
                "supervisor_harness.p0_gate1_plan_compiler.materialize",
                return_value=bad_materialization):
            with self.assertRaisesRegex(ValueError, "commitment changed"):
                self.compile()

        bad_inputs = copy.deepcopy(real)
        bad_inputs["request_plan_inputs_sha256"] = "0" * 64
        body = {key: value for key, value in bad_inputs.items()
                if key != "materialization_sha256"}
        bad_inputs["materialization_sha256"] = digest(body)
        with mock.patch(
                "supervisor_harness.p0_gate1_plan_compiler.materialize",
                return_value=bad_inputs):
            with self.assertRaisesRegex(ValueError, "input commitment changed"):
                self.compile()


if __name__ == "__main__":
    unittest.main()
