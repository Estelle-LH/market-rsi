"""Offline self-checks for executable-plan canary fixtures.

These tests exercise the already-available materializer and request builder.
The decision-to-task and compiled-bundle checks remain intentionally deferred
until ``p0_gate1_plan_compiler`` exists.
"""
from __future__ import annotations

import copy
import hashlib
import unittest

from market_rsi import canonical, digest
from supervisor_harness.p0_gate1_executable_plan_canary_fixtures import (
    ADVERSARIAL_VECTORS,
    CATALOG_COMMITMENT_ID,
    EXPECTED_COMPILED,
    EXPECTED_REQUEST_PLAN_INPUTS,
    EXPECTED_WAVE1,
    FIXTURE_SCHEMA,
    REQUIRED_THREATS,
    VALID_DECISION,
    ZERO_SIDE_EFFECT_ASSERTIONS,
    fixture,
    frozen_catalog_bytes,
    trade_builder_input,
)
from supervisor_harness.p0_gate1_controller_adapter import expected_packet
from supervisor_harness.p0_gate1_plan_compiler import (
    BUNDLE_SCHEMA,
    EXACT_MANIFEST_SCHEMA,
    compile_exact_request_plan,
)
from supervisor_harness.p0_gate1_research_contract import parse_unique_json
from supervisor_harness.p0_gate1_sample_materializer import (
    canonical_output,
    materialize,
)
from supervisor_harness.p0_gate1_trade_query import (
    build_bundle,
    build_request_manifest,
    parse_unique_json as parse_unique_trade_json,
)


class Gate1ExecutablePlanCanaryFixtureTests(unittest.TestCase):
    def test_fixture_is_complete_copy_and_has_all_required_threats(self) -> None:
        value = fixture()
        self.assertEqual(value["schema"], FIXTURE_SCHEMA)
        self.assertEqual(value["catalog_commitment_id"], CATALOG_COMMITMENT_ID)
        case_ids = [item["case_id"] for item in ADVERSARIAL_VECTORS]
        self.assertEqual(len(case_ids), len(set(case_ids)))
        observed = {
            threat
            for item in ADVERSARIAL_VECTORS
            for threat in item["threats"]
        }
        self.assertEqual(observed, REQUIRED_THREATS)
        self.assertTrue(all(item["must_fail_before"] for item in
                            ADVERSARIAL_VECTORS))
        value["decision"]["max_requests"] = 999
        self.assertEqual(VALID_DECISION["max_requests"], 6)

    def test_frozen_catalog_materializes_to_literal_expected_hashes(self) -> None:
        raw = frozen_catalog_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         EXPECTED_WAVE1["catalog_file_sha256"])
        result = materialize(raw, EXPECTED_WAVE1["catalog_file_sha256"])
        self.assertEqual(result["sample_ids"],
                         EXPECTED_WAVE1["selected_sample_ids"])
        self.assertEqual(result["selected_rows_sha256"],
                         EXPECTED_WAVE1["selected_rows_sha256"])
        self.assertEqual(result["request_plan_inputs"],
                         EXPECTED_REQUEST_PLAN_INPUTS)
        self.assertEqual(result["request_plan_inputs_sha256"],
                         EXPECTED_WAVE1["request_plan_inputs_sha256"])
        self.assertEqual(result["materialization_sha256"],
                         EXPECTED_WAVE1["materialization_body_sha256"])
        self.assertEqual(digest(result),
                         EXPECTED_WAVE1["materialization_canonical_sha256"])
        output, output_sha = canonical_output(result)
        self.assertEqual(output_sha,
                         EXPECTED_WAVE1["materialization_file_sha256"])
        self.assertTrue(output.endswith(b"\n"))

    def test_literal_builder_input_produces_exact_six_request_bundle(self) -> None:
        value = trade_builder_input()
        self.assertEqual(digest(value),
                         EXPECTED_WAVE1["trade_builder_input_sha256"])
        bundle = build_bundle(value)
        manifest = bundle["request_manifest"]
        receipt = bundle["execution_receipt_contract"]
        self.assertEqual(manifest["request_count"], 6)
        self.assertEqual(bundle["request_manifest_canonical_sha256"],
                         EXPECTED_WAVE1["trade_request_manifest_sha256"])
        self.assertEqual(
            bundle["execution_receipt_contract_canonical_sha256"],
            EXPECTED_WAVE1["execution_receipt_contract_sha256"],
        )
        self.assertEqual([item["url_sha256"] for item in manifest["requests"]],
                         EXPECTED_WAVE1["request_url_sha256"])
        manifest_file_sha = hashlib.sha256(
            (canonical(manifest) + "\n").encode("utf-8")).hexdigest()
        receipt_file_sha = hashlib.sha256(
            (canonical(receipt) + "\n").encode("utf-8")).hexdigest()
        self.assertEqual(manifest_file_sha,
                         EXPECTED_WAVE1["trade_request_manifest_file_sha256"])
        self.assertEqual(
            receipt_file_sha,
            EXPECTED_WAVE1["execution_receipt_contract_file_sha256"],
        )
        self.assertFalse(
            manifest["execution_policy"]["network_execution_authorized"])
        self.assertFalse(manifest["claim_boundaries"]["data_fetched"])
        self.assertFalse(
            manifest["claim_boundaries"]["formal_data_admitted"])

    def test_integrated_compiler_produces_literal_exact_bundle(self) -> None:
        first = compile_exact_request_plan(
            copy.deepcopy(VALID_DECISION), expected_packet(),
            frozen_catalog_bytes(), CATALOG_COMMITMENT_ID)
        second = compile_exact_request_plan(
            copy.deepcopy(VALID_DECISION), expected_packet(),
            frozen_catalog_bytes(), CATALOG_COMMITMENT_ID)
        self.assertEqual(first, second)
        self.assertEqual(first["schema"], BUNDLE_SCHEMA)
        manifest = first["exact_request_manifest"]
        self.assertEqual(manifest["schema"], EXACT_MANIFEST_SCHEMA)
        self.assertEqual(manifest["request_count"], 6)
        self.assertEqual(
            manifest["materialization_binding"]["sample_ids"],
            EXPECTED_WAVE1["selected_sample_ids"],
        )
        self.assertEqual(
            [item["url_sha256"] for item in manifest["requests"]],
            EXPECTED_WAVE1["request_url_sha256"],
        )
        values = {
            "broker_task": first["broker_task"],
            "exact_manifest": manifest,
            "execution_receipt_contract": first[
                "execution_receipt_contract"],
            "compiled_bundle": first,
        }
        for name, value in values.items():
            self.assertEqual(
                digest(value), EXPECTED_COMPILED[f"{name}_canonical_sha256"])
            self.assertEqual(
                hashlib.sha256((canonical(value) + "\n").encode()).hexdigest(),
                EXPECTED_COMPILED[f"{name}_file_sha256"],
            )
        self.assertEqual(first["materialization_canonical_file_sha256"],
                         EXPECTED_WAVE1["materialization_file_sha256"])
        self.assertEqual(first["claim_boundaries"], {
            "synthetic_canary_only": True,
            "network_requests_made": 0,
            "provider_calls_made": 0,
            "data_fetched": False,
            "dev_data_read": False,
            "final_data_read": False,
            "formal_data_admitted": False,
            "prediction_improvement_proven": False,
        })

    def test_duplicate_json_fixtures_reach_fail_closed_parsers(self) -> None:
        raw_decision = canonical(VALID_DECISION)
        raw_decision = raw_decision[:-1] + ',"max_requests":6}'
        with self.assertRaisesRegex(ValueError, "duplicate decision field"):
            parse_unique_json(raw_decision)

        raw_catalog = frozen_catalog_bytes()
        raw_catalog = raw_catalog[:-1] + b',"catalog_id":"duplicate"}'
        with self.assertRaisesRegex(ValueError, "duplicate JSON field"):
            materialize(raw_catalog, hashlib.sha256(raw_catalog).hexdigest())

        raw_builder = canonical(trade_builder_input())
        raw_builder = raw_builder[:-1] + ',"max_requests":6}'
        with self.assertRaisesRegex(ValueError, "duplicate JSON member"):
            parse_unique_trade_json(raw_builder)

    def test_existing_wave1_rejects_direct_scope_and_authority_injection(self) -> None:
        value = trade_builder_input()
        for key, injected in (
            ("url", "https://example.invalid/trades"),
            ("retry_count", 1),
            ("follow_redirects", True),
            ("authorization", "Bearer fixture-not-a-secret"),
            ("paid_access_allowed", True),
            ("method", "POST"),
            ("query", {"maker": "caller"}),
        ):
            changed = copy.deepcopy(value)
            changed[key] = injected
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_request_manifest(changed)
        changed = copy.deepcopy(value)
        changed["data_scope"] = "sealed_final"
        with self.assertRaisesRegex(ValueError, "public Train"):
            build_request_manifest(changed)
        changed = copy.deepcopy(value)
        changed["max_total_bytes"] = 2_000_001
        with self.assertRaisesRegex(ValueError, "hard ceiling"):
            build_request_manifest(changed)

    def test_audit_replan_vectors_are_not_lost(self) -> None:
        required_case_ids = {
            "packet_registry_shallow_alias_mutation",
            "packet_rights_shallow_alias_mutation",
            "catalog_changed_with_caller_rehash",
            "builder_arbitrary_well_formed_input_hash",
            "builder_limit_pagination_gap",
            "packet_hard_limits_tamper",
            "materialization_missing_commitment",
            "materialization_missing_request_inputs_commitment",
            "compiled_source_mapping_tamper",
            "compiled_offline_builder_mislabeled_as_executor",
        }
        self.assertTrue(required_case_ids.issubset(
            {item["case_id"] for item in ADVERSARIAL_VECTORS}))

    def test_zero_side_effect_receipt_values_are_exact(self) -> None:
        self.assertEqual(ZERO_SIDE_EFFECT_ASSERTIONS, {
            "provider_calls": 0,
            "provider_cost_usd": "0",
            "network_requests_made": 0,
            "bytes_fetched": 0,
            "public_fetch_performed": False,
            "dev_data_read": False,
            "final_data_read": False,
            "formal_data_admitted": False,
        })


if __name__ == "__main__":
    unittest.main()
