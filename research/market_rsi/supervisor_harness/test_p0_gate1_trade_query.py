import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from market_rsi import canonical, digest
from supervisor_harness.p0_gate1_executable_plan_canary_fixtures import (
    frozen_catalog_bytes, trade_builder_input,
)
from supervisor_harness.p0_gate1_sample_materializer import materialize
from supervisor_harness.p0_gate1_trade_query import (
    BUILD_RECEIPT_SCHEMA,
    EXECUTION_RECEIPT_SCHEMA,
    FIXED_OFFSETS,
    MANIFEST_SCHEMA,
    SYNTHETIC_CATALOG_COMMITMENT_ID,
    build_bundle,
    build_request_manifest,
    parse_unique_json,
    write_bundle,
)


class Gate1TradeQueryBuilderTests(unittest.TestCase):
    def setUp(self):
        self.value = trade_builder_input()

    def test_builds_exact_allowlisted_https_requests_without_network(self):
        manifest = build_request_manifest(self.value)
        self.assertEqual(manifest["schema"], MANIFEST_SCHEMA)
        self.assertEqual(manifest["request_count"], 6)
        self.assertFalse(manifest["execution_policy"]["network_execution_authorized"])
        self.assertFalse(manifest["execution_policy"]["redirects_allowed"])
        self.assertEqual([item["query"]["offset"] for item in manifest["requests"]],
                         [0, 100, 0, 100, 0, 100])
        for request in manifest["requests"]:
            parsed = urlsplit(request["url"])
            query = parse_qs(parsed.query)
            self.assertEqual((parsed.scheme, parsed.netloc, parsed.path),
                             ("https", "data-api.polymarket.com", "/trades"))
            self.assertEqual(request["method"], "GET")
            self.assertEqual(query["limit"], ["100"])
            self.assertEqual(query["takerOnly"], ["true"])
            self.assertFalse(request["follow_redirects"])
            self.assertNotIn("Authorization", request["headers"])

    def test_manifest_and_receipt_contract_have_canonical_hashes(self):
        first = build_bundle(self.value)
        second = build_bundle(copy.deepcopy(self.value))
        self.assertEqual(first, second)
        self.assertEqual(first["request_manifest_canonical_sha256"],
                         digest(first["request_manifest"]))
        contract = first["execution_receipt_contract"]
        self.assertEqual(contract["execution_receipt_schema"],
                         EXECUTION_RECEIPT_SCHEMA)
        self.assertEqual(contract["request_manifest_sha256"],
                         first["request_manifest_canonical_sha256"])
        self.assertEqual(contract["hard_constraints"]["redirects_followed"], 0)
        self.assertFalse(contract["hard_constraints"]["dev_data_read"])
        self.assertFalse(contract["hard_constraints"]["final_data_read"])

    def test_model_supplied_url_or_unknown_parameter_is_rejected(self):
        for where, key, value in (
            ("top", "url", "https://data-api.polymarket.com/trades"),
            ("top", "authorization", "Bearer secret"),
            ("row", "method", "POST"),
            ("row", "query", {"limit": 100}),
        ):
            changed = copy.deepcopy(self.value)
            target = changed if where == "top" else changed["request_plan_inputs"][0]
            target[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_request_manifest(changed)

    def test_dev_final_login_paid_and_write_scopes_are_rejected(self):
        for scope in ("dev", "Dev", "final", "Final", "login", "paid", "write"):
            changed = copy.deepcopy(self.value)
            changed["data_scope"] = scope
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                build_request_manifest(changed)

    def test_hard_budgets_and_fixed_paging_fail_closed(self):
        for field, value in (
            ("limit", 101),
            ("limit", 50),
            ("offsets", [0, 200]),
            ("max_requests", 7),
            ("max_requests", 8),
            ("max_total_bytes", 2_000_001),
            ("max_elapsed_seconds", 901),
        ):
            changed = copy.deepcopy(self.value)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                build_request_manifest(changed)
        changed = copy.deepcopy(self.value)
        changed["max_requests"] = 3
        with self.assertRaises(ValueError):
            build_request_manifest(changed)

    def test_six_request_plan_rejects_seven_request_ceiling(self):
        exact_plan = trade_builder_input()
        self.assertEqual(build_request_manifest(exact_plan)["request_count"], 6)
        exact_plan["max_requests"] = 7
        with self.assertRaisesRegex(ValueError, "hard ceiling"):
            build_request_manifest(exact_plan)

    def test_direct_builder_rejects_fabricated_selection_hash(self):
        changed = copy.deepcopy(self.value)
        changed["request_plan_inputs"][0]["input_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "complete trusted catalog rows"):
            build_request_manifest(changed)
        with self.assertRaisesRegex(ValueError, "complete trusted catalog rows"):
            build_bundle(
                changed, catalog_json=frozen_catalog_bytes(),
                catalog_commitment_id=SYNTHETIC_CATALOG_COMMITMENT_ID)

    def test_rehashed_catalog_or_row_cannot_supply_its_own_authority(self):
        raw = frozen_catalog_bytes()
        forged_catalog = json.loads(raw)
        forged_catalog["rows"][0]["asset_ids"] = ["99999"]
        forged_raw = canonical(forged_catalog).encode("utf-8")
        forged_inputs = materialize(
            forged_raw, hashlib.sha256(forged_raw).hexdigest())[
                "request_plan_inputs"]
        changed = copy.deepcopy(self.value)
        changed["request_plan_inputs"] = forged_inputs
        with self.assertRaisesRegex(ValueError, "trusted commitment"):
            build_request_manifest(
                changed, catalog_json=forged_raw,
                catalog_commitment_id=SYNTHETIC_CATALOG_COMMITMENT_ID)

        forged_row = copy.deepcopy(json.loads(raw)["rows"][0])
        forged_row["asset_ids"] = ["99999"]
        changed["request_plan_inputs"] = copy.deepcopy(self.value[
            "request_plan_inputs"])
        changed["request_plan_inputs"][0]["asset_ids"] = ["99999"]
        changed["request_plan_inputs"][0]["input_sha256"] = digest(forged_row)
        with self.assertRaisesRegex(ValueError, "complete trusted catalog rows"):
            build_request_manifest(
                changed, catalog_json=raw,
                catalog_commitment_id=SYNTHETIC_CATALOG_COMMITMENT_ID)

    def test_explicit_catalog_binding_requires_both_inputs_and_registered_hash(self):
        raw = frozen_catalog_bytes()
        for binding in (
            {"catalog_json": raw},
            {"catalog_commitment_id": SYNTHETIC_CATALOG_COMMITMENT_ID},
        ):
            with self.subTest(binding=list(binding)), self.assertRaisesRegex(
                    ValueError, "both required"):
                build_request_manifest(self.value, **binding)
        with self.assertRaisesRegex(ValueError, "commitment registry"):
            build_request_manifest(
                self.value, catalog_json=raw,
                catalog_commitment_id="caller-supplied-catalog")
        with self.assertRaisesRegex(ValueError, "trusted commitment"):
            build_request_manifest(
                self.value, catalog_json=raw + b" ",
                catalog_commitment_id=SYNTHETIC_CATALOG_COMMITMENT_ID)

    def test_additional_market_exceeds_six_request_hard_cap(self):
        changed = copy.deepcopy(self.value)
        changed["request_plan_inputs"].append({
            "sample_id": "train-game-006",
            "condition_id": "0x" + "6" * 64,
            "asset_ids": ["623456789", "687654321"],
            "start_timestamp": 1758000000,
            "end_timestamp": 1758060000,
            "input_sha256": "6" * 64,
        })
        with self.assertRaises(ValueError):
            build_request_manifest(changed)

    def test_ids_windows_and_provenance_are_strict(self):
        cases = (
            ("condition_id", "condition-from-model"),
            ("asset_ids", ["1", "1"]),
            ("asset_ids", ["01", "2"]),
            ("start_timestamp", 1757077200),
            ("input_sha256", "A" * 64),
        )
        for field, value in cases:
            changed = copy.deepcopy(self.value)
            changed["request_plan_inputs"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                build_request_manifest(changed)

    def test_duplicate_json_members_are_rejected(self):
        raw = json.dumps(self.value)
        raw = raw[:-1] + ',"source_id":"polymarket_public_trades_v1"}'
        with self.assertRaises(ValueError):
            parse_unique_json(raw)

    def test_offline_runner_writes_exact_manifest_contract_and_build_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fresh"
            receipt = write_bundle(self.value, output)
            self.assertEqual(receipt["schema"], BUILD_RECEIPT_SCHEMA)
            self.assertEqual(receipt["network_requests_made"], 0)
            self.assertEqual(receipt["bytes_fetched"], 0)
            manifest_bytes = (output / "request-manifest.json").read_bytes()
            self.assertEqual(receipt["request_manifest_file_sha256"],
                             hashlib.sha256(manifest_bytes).hexdigest())
            self.assertEqual(json.loads(manifest_bytes)["request_count"], 6)
            self.assertTrue((output / "execution-receipt-contract.json").is_file())
            with self.assertRaises(FileExistsError):
                write_bundle(self.value, output)

    def test_boolean_is_not_accepted_as_an_integer_bound(self):
        for field in ("limit", "max_requests", "max_total_bytes",
                      "max_elapsed_seconds"):
            changed = copy.deepcopy(self.value)
            changed[field] = True
            with self.subTest(field=field), self.assertRaises(ValueError):
                build_request_manifest(changed)

    def test_fixed_sample_materializer_outputs_are_drop_in_inputs(self):
        raw = frozen_catalog_bytes()
        materialized = materialize(raw, hashlib.sha256(raw).hexdigest())
        changed = copy.deepcopy(self.value)
        changed["source_id"] = materialized["source_id"]
        changed["data_scope"] = materialized["data_scope"]
        changed["request_plan_inputs"] = materialized["request_plan_inputs"]
        manifest = build_request_manifest(
            changed, catalog_json=raw,
            catalog_commitment_id=SYNTHETIC_CATALOG_COMMITMENT_ID)
        self.assertEqual(manifest["request_count"], 6)
        self.assertEqual(
            [item["selection_input_sha256"] for item in manifest["requests"]][::2],
            [item["input_sha256"] for item in materialized["request_plan_inputs"]],
        )

    def test_fixed_offsets_constant_is_exact(self):
        self.assertEqual(FIXED_OFFSETS, (0, 100))


if __name__ == "__main__":
    unittest.main()
