"""Independent receipt and boundary checks for the synthetic Gate 1 canary."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from market_rsi import digest
from supervisor_harness import run_p0_gate1_executable_plan_canary as runner
from supervisor_harness.p0_gate1_executable_plan_canary_fixtures import (
    ADVERSARIAL_VECTORS, CATALOG_COMMITMENT_ID, EXPECTED_COMPILED,
    EXPECTED_WAVE1, VALID_DECISION, frozen_catalog_bytes,
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class Gate1ExecutablePlanCanaryTests(unittest.TestCase):
    def test_complete_valid_chain_and_twice_compiled_bytes(self) -> None:
        result = runner.execute()
        self.assertTrue(result["passed"])
        self.assertEqual(result["requests_planned"], 6)
        self.assertEqual(result["catalog_commitment_id"], CATALOG_COMMITMENT_ID)
        self.assertEqual(result["sample_ids"], EXPECTED_WAVE1["selected_sample_ids"])
        self.assertEqual(result["manifest_sha256"],
                         EXPECTED_COMPILED["exact_manifest_canonical_sha256"])
        self.assertEqual(result["materialization_sha256"],
                         EXPECTED_WAVE1["materialization_body_sha256"])
        self.assertEqual(result["request_plan_inputs_sha256"],
                         EXPECTED_WAVE1["request_plan_inputs_sha256"])
        self.assertEqual(result, runner.execute())

    def test_all_frozen_vectors_have_distinct_stable_receipts(self) -> None:
        baseline, cases, tamper = runner._offline()
        self.assertEqual(len(cases), len(ADVERSARIAL_VECTORS))
        self.assertEqual(len(cases), 34)
        self.assertEqual([v["vector_id"] for v in cases],
                         [v["case_id"] for v in ADVERSARIAL_VECTORS])
        self.assertEqual(len(tamper), len(runner._POST_COMPILE_POINTERS))
        self.assertEqual(len(set(v["vector_id"] for v in tamper)), len(tamper))
        for value in cases + tamper:
            with self.subTest(vector=value["vector_id"]):
                self.assertEqual(value["schema"], runner.VECTOR_SCHEMA)
                self.assertEqual(value["expected_outcome"], "rejected")
                self.assertEqual(value["observed_outcome"], "rejected")
                self.assertNotEqual(value["reason_code"], "UNEXPECTED_ACCEPTANCE")
                self.assertEqual(len(value["input_sha256"]), 64)
                self.assertEqual(len(value["output_sha256"]), 64)
                self.assertIsNone(value["output_artifact_sha256"])
                self.assertEqual(value["manifest_sha256"],
                                 digest(baseline["exact_request_manifest"]))
                self.assertEqual(value["ceilings"], {
                    "max_requests": 6, "max_bytes": 2_000_000,
                    "max_elapsed_seconds": 900, "max_provider_cost_usd": "0"})
                self.assertEqual(value["network_requests_made"], 0)
                self.assertEqual(value["provider_calls"], 0)
                self.assertFalse(value["dev_data_read"])
                self.assertFalse(value["final_data_read"])
        self.assertEqual(cases, [runner.run_vector(v["case_id"], baseline)
                                 for v in ADVERSARIAL_VECTORS])

    def test_reason_is_from_observed_rejection_not_any_value_error(self) -> None:
        with patch.object(runner, "_case_input", side_effect=ValueError("wrong failure")):
            with self.assertRaisesRegex(RuntimeError, "UNEXPECTED_REJECTION_REASON"):
                runner.run_vector("decision_unknown_operation")

    def test_refuses_unknown_vectors_and_caller_authored_trust(self) -> None:
        with self.assertRaisesRegex(ValueError, "UNKNOWN_VECTOR_ID"):
            runner.run_vector("new-caller-vector")
        with self.assertRaisesRegex(TypeError, "unexpected keyword"):
            runner.execute(trusted_catalog_sha256="f" * 64)
        baseline = runner._compile(VALID_DECISION, runner._packet(),
                                   frozen_catalog_bytes())
        bad = deepcopy(baseline)
        bad["exact_request_manifest"]["catalog_commitment"]["catalog_file_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "COMPILED_BUNDLE_MISMATCH"):
            runner.run_vector(ADVERSARIAL_VECTORS[0]["case_id"], bad)

    def test_refuses_missing_commitments_and_malformed_fixture(self) -> None:
        self.assertEqual(runner.run_vector("materialization_missing_commitment")
                         ["reason_code"], "MATERIALIZATION_BINDING_REJECTED")
        self.assertEqual(runner.run_vector(
            "materialization_missing_request_inputs_commitment")["observed_outcome"],
            "rejected")
        corrupted = list(deepcopy(ADVERSARIAL_VECTORS))
        corrupted[0]["mutation"]["value"] = "https://caller.invalid"
        with patch.object(runner, "ADVERSARIAL_VECTORS", tuple(corrupted)):
            with self.assertRaisesRegex(ValueError, "FROZEN_FIXTURE_MISMATCH"):
                runner.execute()
        with patch.object(runner, "fixture", return_value={"schema": "caller"}):
            with self.assertRaisesRegex(ValueError, "FROZEN_FIXTURE_MISMATCH"):
                runner.execute()

    def test_post_compile_checks_all_critical_artifact_families(self) -> None:
        baseline = runner._compile(VALID_DECISION, runner._packet(),
                                   frozen_catalog_bytes())
        pointers = runner._POST_COMPILE_POINTERS
        for prefix in ("/broker_task/", "/materialization/",
                       "/exact_request_manifest/", "/execution_receipt_contract/",
                       "/claim_boundaries/"):
            self.assertTrue(any(p.startswith(prefix) for p in pointers), prefix)
        self.assertEqual(len(runner._post_compile_tamper_receipts(baseline)), 26)
        altered = deepcopy(baseline)
        altered["materialization"].pop("request_plan_inputs_sha256")
        with self.assertRaisesRegex(ValueError, "COMPILED_BUNDLE_MISMATCH"):
            runner._verified_bundle(altered, baseline)

    def test_output_is_byte_identical_and_rehashable_outside_repo(self) -> None:
        with tempfile.TemporaryDirectory() as parent:
            first, second = Path(parent) / "one", Path(parent) / "two"
            result = runner.execute(first)
            self.assertEqual(result, runner.execute(second))
            names = sorted(path.name for path in first.iterdir())
            self.assertEqual(names, sorted([*result["artifact_sha256"],
                                            "canary-result.json"]))
            for name in names:
                self.assertEqual((first / name).read_bytes(),
                                 (second / name).read_bytes(), name)
            for name, expected in result["artifact_sha256"].items():
                self.assertEqual(sha((first / name).read_bytes()), expected)
            self.assertEqual(json.loads((first / "canary-result.json").read_text()),
                             result)
            adversarial = json.loads((first / "adversarial-receipt.json").read_text())
            valid = json.loads((first / "valid-path-receipt.json").read_text())
            self.assertEqual(valid["vector_id"], "known_good")
            self.assertEqual(valid["observed_outcome"], "accepted")
            self.assertEqual(valid["output_sha256"],
                             result["compiled_bundle_canonical_sha256"])
            self.assertEqual(adversarial["vector_count"], 34)
            self.assertEqual(adversarial["vectors_rejected"], 34)
            self.assertEqual(adversarial["post_compile_tamper_count"], 26)
            self.assertEqual(sha((first / "catalog.json").read_bytes()),
                             EXPECTED_WAVE1["catalog_file_sha256"])
            self.assertEqual((first / "catalog.json").read_bytes(),
                             frozen_catalog_bytes())
            with self.assertRaises(FileExistsError):
                runner.execute(first)

    def test_interrupted_write_has_no_success_marker(self) -> None:
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "interrupted"
            real = runner._write_atomic_exclusive
            def fail_at_receipt(path: Path, raw: bytes) -> None:
                if path.name == "adversarial-receipt.json":
                    raise OSError("simulated write interruption")
                real(path, raw)
            with patch.object(runner, "_write_atomic_exclusive", side_effect=fail_at_receipt):
                with self.assertRaisesRegex(OSError, "simulated write interruption"):
                    runner.execute(output)
            self.assertFalse((output / "canary-result.json").exists())
            with self.assertRaises(FileExistsError):
                runner.execute(output)

    def test_source_tree_output_is_denied_before_write(self) -> None:
        output = Path(__file__).parent / "never-write-gate1-runtime-receipts"
        with self.assertRaisesRegex(ValueError, "OUTSIDE_SOURCE_TREE"):
            runner.execute(output)
        self.assertFalse(output.exists())

    def test_network_attempt_cannot_be_a_canary_pass(self) -> None:
        def attempted_compilation(*args):
            socket.create_connection(("example.invalid", 443))
        with patch.object(runner, "compile_exact_request_plan",
                          side_effect=attempted_compilation):
            with self.assertRaisesRegex(RuntimeError, "NETWORK_FORBIDDEN"):
                runner.execute()

    def test_no_authority_from_receipts_or_executor_claim(self) -> None:
        result = runner.execute()
        for name in ("network_execution_authorized", "release_authorized",
                     "provider_execution_authorized", "data_fetch_authorized",
                     "dev_or_final_access_authorized", "formal_admission_authorized",
                     "public_fetch_performed", "formal_data_admitted"):
            self.assertIs(result[name], False, name)
        self.assertEqual(result["provider_cost_usd"], "0")
        self.assertEqual(result["bytes_fetched"], 0)
        self.assertEqual(result["network_requests_made"], 0)
        self.assertEqual(result["provider_calls"], 0)


if __name__ == "__main__":
    unittest.main()
