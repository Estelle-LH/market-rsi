"""No-network tests for exact formal Train admission receipt validation."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import patch

from supervisor_harness import formal_train_admission as admission


DATASET_BYTES = b'{"schema":"synthetic_train_test_bundle_v1","rows":[1,2,3]}\n'
DATASET_SHA = hashlib.sha256(DATASET_BYTES).hexdigest()
QUESTION_ID = "2025_whole_season_trade_access"
SEASON_IDS = ("2023", "2024", "2025")
CONTROLLER_TASK_SHA = "7" * 64


def valid_receipt() -> dict:
    return {
        "schema": admission.SCHEMA,
        "receipt_id": "formal-train-test-receipt-v1",
        "issuer_id": admission.INDEPENDENT_ISSUER_ID,
        "issued_utc": "2026-09-22T12:00:00Z",
        "dataset": {
            "dataset_id": "synthetic-train-test-dataset-v1",
            "dataset_sha256": DATASET_SHA,
            "row_manifest_sha256": "2" * 64,
            "source_version_sha256": "3" * 64,
            "split_scope": admission.TRAIN_SCOPE,
            "row_count": 100,
            "season_ids": list(SEASON_IDS),
            "question_id": QUESTION_ID,
            "controller_task_sha256": CONTROLLER_TASK_SHA,
        },
        "gates": {
            name: {"status": "passed", "evidence_sha256": digit * 64}
            for name, digit in zip(admission.REQUIRED_GATES, ("4", "5", "6"))
        },
        "claim_boundaries": {
            "formal_train_admitted": True,
            "dev_data_read": False,
            "final_data_read": False,
            "unknowns_remaining": False,
        },
    }


class FormalTrainAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.dataset = self.root / "train-bundle.json"
        self.dataset.write_bytes(DATASET_BYTES)

    def tearDown(self):
        self.temp.cleanup()

    def write_receipt(self, receipt: dict, name: str = "admission.json") -> tuple[Path, str]:
        path = self.root / name
        raw = admission._canonical(receipt)
        path.write_bytes(raw)
        return path, hashlib.sha256(raw).hexdigest()

    @staticmethod
    def commitment(receipt: dict, file_sha256: str) -> MappingProxyType:
        return MappingProxyType({
            receipt["receipt_id"]: {
                "receipt_file_sha256": file_sha256,
                "receipt_schema": admission.SCHEMA,
                "issuer_id": receipt.get("issuer_id", admission.INDEPENDENT_ISSUER_ID),
                "dataset_id": receipt["dataset"]["dataset_id"],
                "dataset_sha256": receipt["dataset"]["dataset_sha256"],
                "season_ids": receipt["dataset"]["season_ids"],
                "question_id": receipt["dataset"]["question_id"],
                "controller_task_sha256": receipt["dataset"][
                    "controller_task_sha256"],
            },
        })

    def validate(self, receipt: dict) -> dict:
        path, file_sha = self.write_receipt(receipt)
        with patch.object(admission, "TRUSTED_RECEIPT_COMMITMENTS",
                          self.commitment(receipt, file_sha)):
            return admission.validate_formal_train_admission(
                path, expected_receipt_sha256=file_sha,
                dataset_path=self.dataset,
                expected_question_id=QUESTION_ID,
                expected_season_ids=SEASON_IDS,
                expected_controller_task_sha256=CONTROLLER_TASK_SHA)

    def test_exact_code_owned_receipt_passes(self):
        value = self.validate(valid_receipt())
        self.assertEqual(value["dataset_sha256"], DATASET_SHA)
        self.assertEqual(value["row_count"], 100)
        self.assertEqual(value["issuer_id"], admission.INDEPENDENT_ISSUER_ID)

    def test_production_registry_admits_no_current_artifact(self):
        self.assertEqual(dict(admission.TRUSTED_RECEIPT_COMMITMENTS), {})
        receipt = valid_receipt()
        path, file_sha = self.write_receipt(receipt)
        with self.assertRaisesRegex(ValueError, "not code-owned"):
            admission.validate_formal_train_admission(
                path, expected_receipt_sha256=file_sha,
                dataset_path=self.dataset, expected_question_id=QUESTION_ID,
                expected_season_ids=SEASON_IDS,
                expected_controller_task_sha256=CONTROLLER_TASK_SHA)

    def test_missing_issuer_fails(self):
        missing = valid_receipt()
        del missing["issuer_id"]
        path, file_sha = self.write_receipt(missing)
        with self.assertRaisesRegex(ValueError, "fields differ"):
            admission.validate_formal_train_admission(
                path, expected_receipt_sha256=file_sha,
                dataset_path=self.dataset, expected_question_id=QUESTION_ID,
                expected_season_ids=SEASON_IDS,
                expected_controller_task_sha256=CONTROLLER_TASK_SHA)

    def test_untrusted_receipt_fails_before_dataset_is_read(self):
        receipt = valid_receipt()
        receipt["issuer_id"] = "caller_claimed_issuer"
        path, file_sha = self.write_receipt(receipt)
        with patch.object(admission, "_hash_exact_dataset") as hash_dataset:
            with self.assertRaisesRegex(ValueError, "issuer is not trusted"):
                admission.validate_formal_train_admission(
                    path, expected_receipt_sha256=file_sha,
                    dataset_path=self.dataset,
                    expected_question_id=QUESTION_ID,
                    expected_season_ids=SEASON_IDS,
                    expected_controller_task_sha256=CONTROLLER_TASK_SHA)
            hash_dataset.assert_not_called()

        untrusted = valid_receipt()
        untrusted["issuer_id"] = "caller_claimed_issuer"
        path, file_sha = self.write_receipt(untrusted, "untrusted.json")
        with self.assertRaisesRegex(ValueError, "issuer is not trusted"):
            admission.validate_formal_train_admission(
                path, expected_receipt_sha256=file_sha,
                dataset_path=self.dataset, expected_question_id=QUESTION_ID,
                expected_season_ids=SEASON_IDS,
                expected_controller_task_sha256=CONTROLLER_TASK_SHA)

    def test_dataset_hash_mismatch_fails(self):
        receipt = valid_receipt()
        receipt["dataset"]["dataset_sha256"] = "9" * 64
        path, file_sha = self.write_receipt(receipt)
        with patch.object(admission, "TRUSTED_RECEIPT_COMMITMENTS",
                          self.commitment(receipt, file_sha)):
            with self.assertRaisesRegex(ValueError, "exact task dataset bytes"):
                admission.validate_formal_train_admission(
                    path, expected_receipt_sha256=file_sha,
                    dataset_path=self.dataset, expected_question_id=QUESTION_ID,
                    expected_season_ids=SEASON_IDS,
                    expected_controller_task_sha256=CONTROLLER_TASK_SHA)

    def test_question_and_seasons_must_match_task(self):
        receipt = valid_receipt()
        path, file_sha = self.write_receipt(receipt)
        with patch.object(admission, "TRUSTED_RECEIPT_COMMITMENTS",
                          self.commitment(receipt, file_sha)):
            with self.assertRaisesRegex(ValueError, "question differs"):
                admission.validate_formal_train_admission(
                    path, expected_receipt_sha256=file_sha,
                    dataset_path=self.dataset,
                    expected_question_id="2023_real_fill_sparsity",
                    expected_season_ids=SEASON_IDS,
                    expected_controller_task_sha256=CONTROLLER_TASK_SHA)
            with self.assertRaisesRegex(ValueError, "seasons differ"):
                admission.validate_formal_train_admission(
                    path, expected_receipt_sha256=file_sha,
                    dataset_path=self.dataset,
                    expected_question_id=QUESTION_ID,
                    expected_season_ids=("2024", "2025"),
                    expected_controller_task_sha256=CONTROLLER_TASK_SHA)
            with self.assertRaisesRegex(ValueError, "Controller task differs"):
                admission.validate_formal_train_admission(
                    path, expected_receipt_sha256=file_sha,
                    dataset_path=self.dataset,
                    expected_question_id=QUESTION_ID,
                    expected_season_ids=SEASON_IDS,
                    expected_controller_task_sha256="8" * 64)

    def test_rights_coverage_and_exposure_must_pass(self):
        for gate_name in admission.REQUIRED_GATES:
            for status in ("failed", "unknown"):
                with self.subTest(gate=gate_name, status=status):
                    receipt = valid_receipt()
                    receipt["gates"][gate_name]["status"] = status
                    path, file_sha = self.write_receipt(
                        receipt, f"{gate_name}-{status}.json")
                    with self.assertRaisesRegex(
                            ValueError, f"{gate_name} admission gate did not pass"):
                        admission.validate_formal_train_admission(
                            path, expected_receipt_sha256=file_sha,
                            dataset_path=self.dataset,
                            expected_question_id=QUESTION_ID,
                            expected_season_ids=SEASON_IDS,
                            expected_controller_task_sha256=CONTROLLER_TASK_SHA)

    def test_unknown_or_protected_boundaries_fail(self):
        mutations = (
            ("unknowns_remaining", True),
            ("dev_data_read", True),
            ("final_data_read", True),
            ("formal_train_admitted", False),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                receipt = valid_receipt()
                receipt["claim_boundaries"][field] = value
                path, file_sha = self.write_receipt(
                    receipt, f"boundary-{field}.json")
                with self.assertRaisesRegex(ValueError, "boundaries do not pass"):
                    admission.validate_formal_train_admission(
                        path, expected_receipt_sha256=file_sha,
                        dataset_path=self.dataset,
                        expected_question_id=QUESTION_ID,
                        expected_season_ids=SEASON_IDS,
                        expected_controller_task_sha256=CONTROLLER_TASK_SHA)

    def test_symlink_and_path_substitution_fail(self):
        receipt = valid_receipt()
        target, file_sha = self.write_receipt(receipt, "target.json")
        link = self.root / "link.json"
        link.symlink_to(target)
        with patch.object(admission, "TRUSTED_RECEIPT_COMMITMENTS",
                          self.commitment(receipt, file_sha)):
            with self.assertRaisesRegex(ValueError, "cannot use symlinks"):
                admission.validate_formal_train_admission(
                    link, expected_receipt_sha256=file_sha,
                    dataset_path=self.dataset, expected_question_id=QUESTION_ID,
                    expected_season_ids=SEASON_IDS,
                    expected_controller_task_sha256=CONTROLLER_TASK_SHA)

            substituted = deepcopy(receipt)
            substituted["dataset"]["row_count"] = 101
            target.write_bytes(admission._canonical(substituted))
            with self.assertRaisesRegex(ValueError, "receipt hash changed"):
                admission.validate_formal_train_admission(
                    target, expected_receipt_sha256=file_sha,
                    dataset_path=self.dataset, expected_question_id=QUESTION_ID,
                    expected_season_ids=SEASON_IDS,
                    expected_controller_task_sha256=CONTROLLER_TASK_SHA)

    def test_dataset_symlink_and_byte_substitution_fail(self):
        receipt = valid_receipt()
        path, file_sha = self.write_receipt(receipt)
        dataset_link = self.root / "train-link.json"
        dataset_link.symlink_to(self.dataset)
        with patch.object(admission, "TRUSTED_RECEIPT_COMMITMENTS",
                          self.commitment(receipt, file_sha)):
            with self.assertRaisesRegex(ValueError, "dataset path cannot use symlinks"):
                admission.validate_formal_train_admission(
                    path, expected_receipt_sha256=file_sha,
                    dataset_path=dataset_link,
                    expected_question_id=QUESTION_ID,
                    expected_season_ids=SEASON_IDS,
                    expected_controller_task_sha256=CONTROLLER_TASK_SHA)
            self.dataset.write_bytes(DATASET_BYTES + b"substituted\n")
            with self.assertRaisesRegex(ValueError, "exact task dataset bytes"):
                admission.validate_formal_train_admission(
                    path, expected_receipt_sha256=file_sha,
                    dataset_path=self.dataset,
                    expected_question_id=QUESTION_ID,
                    expected_season_ids=SEASON_IDS,
                    expected_controller_task_sha256=CONTROLLER_TASK_SHA)

    def test_arbitrary_digest_does_not_create_authority(self):
        receipt = valid_receipt()
        path, file_sha = self.write_receipt(receipt)
        with self.assertRaisesRegex(ValueError, "receipt hash changed"):
            admission.validate_formal_train_admission(
                path, expected_receipt_sha256="a" * 64,
                dataset_path=self.dataset, expected_question_id=QUESTION_ID,
                expected_season_ids=SEASON_IDS,
                expected_controller_task_sha256=CONTROLLER_TASK_SHA)
        with self.assertRaisesRegex(ValueError, "not code-owned"):
            admission.validate_formal_train_admission(
                path, expected_receipt_sha256=file_sha,
                dataset_path=self.dataset, expected_question_id=QUESTION_ID,
                expected_season_ids=SEASON_IDS,
                expected_controller_task_sha256=CONTROLLER_TASK_SHA)


if __name__ == "__main__":
    unittest.main()
