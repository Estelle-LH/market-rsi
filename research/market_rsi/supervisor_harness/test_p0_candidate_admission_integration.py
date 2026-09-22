"""Zero-network tests for the non-test P0 candidate integration consumer."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import patch

from supervisor_harness import p0_candidate_admission_integration as integration
from supervisor_harness import protocol_source_release


def pretty(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True,
                       ensure_ascii=True, allow_nan=False) + "\n").encode()


class P0CandidateAdmissionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = integration._load_snapshot(integration.CANONICAL_REPO)

    def mutate_ledger(self, mutate) -> integration.CandidateSnapshot:
        ledger = json.loads(self.snapshot.ledger)
        mutate(ledger)
        ledger_raw = pretty(ledger)
        receipt = json.loads(self.snapshot.ledger_receipt)
        receipt["ledger_sha256"] = hashlib.sha256(ledger_raw).hexdigest()
        receipt_raw = pretty(receipt)
        hashes = dict(self.snapshot.sha256)
        hashes["ledger"] = hashlib.sha256(ledger_raw).hexdigest()
        hashes["ledger_receipt"] = hashlib.sha256(receipt_raw).hexdigest()
        return integration.CandidateSnapshot(
            ledger=ledger_raw, ledger_receipt=receipt_raw,
            catalog=self.snapshot.catalog, mapping=self.snapshot.mapping,
            sha256=MappingProxyType(hashes))

    @staticmethod
    def recommit(row: dict) -> None:
        row.pop("row_commitment_sha256", None)
        row["row_commitment_sha256"] = integration.ledger_builder.canonical_digest(row)

    def test_exact_canonical_candidate_integrates_without_authority(self) -> None:
        value = integration.integrate_candidate(integration.CANONICAL_REPO)
        self.assertEqual(value["status"], "candidate_only")
        self.assertEqual(value["denominator"], {
            "candidate_rows": 285,
            "mapped_oriented_rows": 284,
            "explicitly_unresolved_rows": 1,
            "cursor_candidate_streams": 284,
        })
        self.assertEqual(value["unresolved_event"]["event_id"], "17330")
        self.assertFalse(value["unresolved_event"]["mapping_resolved"])
        self.assertEqual(
            value["formal_train_receipt_boundary"]["trusted_receipt_commitments"], 0)
        self.assertFalse(value["claim_boundaries"]["formal_train_admitted"])
        self.assertFalse(value["claim_boundaries"]["network_execution_authorized"])

    def test_repository_substitution_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(ValueError, "exact canonical"):
                integration.integrate_candidate(Path(name).resolve())

    def test_file_and_parent_symlinks_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            target = root / "target.json"
            target.write_bytes(b"{}\n")
            link = root / "link.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "cannot use symlinks"):
                integration._read_pinned_file(
                    root, link, expected_path=link,
                    expected_sha256=hashlib.sha256(b"{}\n").hexdigest(),
                    maximum_bytes=100)
            directory = root / "real"
            directory.mkdir()
            nested = directory / "value.json"
            nested.write_bytes(b"{}\n")
            parent_link = root / "linked"
            parent_link.symlink_to(directory, target_is_directory=True)
            linked_file = parent_link / "value.json"
            with self.assertRaisesRegex(ValueError, "cannot use symlinks"):
                integration._read_pinned_file(
                    root, linked_file, expected_path=linked_file,
                    expected_sha256=hashlib.sha256(b"{}\n").hexdigest(),
                    maximum_bytes=100)

    def test_wrong_lexical_file_path_is_rejected_before_read(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            expected = root / "expected.json"
            substitute = root / "substitute.json"
            expected.write_bytes(b"{}\n")
            substitute.write_bytes(b"{}\n")
            with self.assertRaisesRegex(ValueError, "path substitution"):
                integration._read_pinned_file(
                    root, substitute, expected_path=expected,
                    expected_sha256=hashlib.sha256(b"{}\n").hexdigest(),
                    maximum_bytes=100)

    def test_change_while_reading_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            path = root / "value.json"
            raw = b"{}\n"
            path.write_bytes(raw)
            real_read = os.read
            changed = False

            def read_and_touch(descriptor, size):
                nonlocal changed
                value = real_read(descriptor, size)
                if value and not changed:
                    before = path.stat()
                    os.utime(path, ns=(before.st_atime_ns,
                                       before.st_mtime_ns + 1_000_000))
                    changed = True
                return value

            with patch.object(integration.os, "read", side_effect=read_and_touch):
                with self.assertRaisesRegex(ValueError, "changed while being read"):
                    integration._read_pinned_file(
                        root, path, expected_path=path,
                        expected_sha256=hashlib.sha256(raw).hexdigest(),
                        maximum_bytes=100)

    def test_transient_ancestor_symlink_swap_with_hardlink_fails(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            repo = root / "repo"
            ancestor = repo / "ancestor"
            alternate = root / "alternate"
            ancestor.mkdir(parents=True)
            alternate.mkdir()
            path = ancestor / "value.json"
            raw = b'{"fixed":true}\n'
            path.write_bytes(raw)
            os.link(path, alternate / "value.json")
            parked = repo / "ancestor-parked"
            real_read = os.read
            swapped = False

            def read_during_transient_swap(descriptor, size):
                nonlocal swapped
                value = real_read(descriptor, size)
                if value and not swapped:
                    ancestor.rename(parked)
                    ancestor.symlink_to(alternate, target_is_directory=True)
                    ancestor.unlink()
                    parked.rename(ancestor)
                    swapped = True
                return value

            with patch.object(
                    integration.os, "read",
                    side_effect=read_during_transient_swap):
                with self.assertRaisesRegex(ValueError, "ancestor directory changed"):
                    integration._read_pinned_file(
                        repo, path, expected_path=path,
                        expected_sha256=hashlib.sha256(raw).hexdigest(),
                        maximum_bytes=100)

    def test_validation_uses_retained_bytes_not_reopened_path(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            path = root / "value.json"
            original = b'{"value":1}\n'
            path.write_bytes(original)
            retained = integration._read_pinned_file(
                root, path, expected_path=path,
                expected_sha256=hashlib.sha256(original).hexdigest(),
                maximum_bytes=100)
            path.write_bytes(b'{"value":2}\n')
            self.assertEqual(retained, original)

    def test_ledger_receipt_mutation_and_admission_escalation_fail(self) -> None:
        receipt = json.loads(self.snapshot.ledger_receipt)
        receipt["admission_claim"] = True
        raw = pretty(receipt)
        hashes = dict(self.snapshot.sha256)
        hashes["ledger_receipt"] = hashlib.sha256(raw).hexdigest()
        candidate = integration.CandidateSnapshot(
            ledger=self.snapshot.ledger, ledger_receipt=raw,
            catalog=self.snapshot.catalog, mapping=self.snapshot.mapping,
            sha256=MappingProxyType(hashes))
        with self.assertRaisesRegex(ValueError, "receipt does not bind"):
            integration._compose_snapshot(candidate)

    def test_inserted_authority_aliases_fail(self) -> None:
        for field in (
                "rights_verified", "provider_verified",
                "network_access_authorized", "formal_training_authorized",
                "improvement_claim_allowed"):
            with self.subTest(field=field):
                def mutate(ledger, field=field):
                    ledger["rows"][0][field] = True
                    self.recommit(ledger["rows"][0])
                with self.assertRaisesRegex(ValueError, "authority escalation"):
                    integration._compose_snapshot(self.mutate_ledger(mutate))

    def test_any_dev_or_final_ledger_field_fails_even_when_false(self) -> None:
        for field in ("dev_score", "Final", "final_data_read"):
            with self.subTest(field=field):
                def mutate(ledger, field=field):
                    ledger["rows"][0][field] = False
                    self.recommit(ledger["rows"][0])
                with self.assertRaisesRegex(ValueError, "Dev/Final"):
                    integration._compose_snapshot(self.mutate_ledger(mutate))

    def test_ledger_orientation_identity_mismatch_fails(self) -> None:
        def mutate(ledger):
            row = next(item for item in ledger["rows"]
                       if item["mapping_status"] == "mapped")
            row["source_event_id"] = "999999"
            self.recommit(row)
        with self.assertRaisesRegex(ValueError, "ledger/orientation identity"):
            integration._compose_snapshot(self.mutate_ledger(mutate))

    def test_event_17330_cannot_be_inferred_or_removed(self) -> None:
        def mutate(ledger):
            row = next(item for item in ledger["rows"]
                       if item["mapping_status"] == "missing")
            row["source_event_id"] = "17330"
            row["source_event_slug"] = "nfl-kc-phi-2025-02-09"
            self.recommit(row)
        with self.assertRaisesRegex(ValueError, "explicitly unresolved"):
            integration._compose_snapshot(self.mutate_ledger(mutate))

    def test_formal_receipt_registry_cannot_escalate_candidate(self) -> None:
        with patch.object(
                integration.formal_train_admission,
                "TRUSTED_RECEIPT_COMMITMENTS", {"unexpected": {}}):
            with self.assertRaisesRegex(ValueError, "cannot consume formal"):
                integration._compose_snapshot(self.snapshot)

    def test_reviewed_modules_and_tests_are_controlled_sources(self) -> None:
        required = {
            "supervisor_harness/build_2024_train_candidate_ledger.py",
            "supervisor_harness/test_build_2024_train_candidate_ledger.py",
            "supervisor_harness/p0_2024_outcome_orientation.py",
            "supervisor_harness/test_p0_2024_outcome_orientation.py",
            "supervisor_harness/formal_train_admission.py",
            "supervisor_harness/test_formal_train_admission.py",
            "supervisor_harness/test_supervisor_watchdog.py",
            "supervisor_harness/p0_polymarket_v2_cursor_acquisition.py",
            "supervisor_harness/test_p0_polymarket_v2_cursor_acquisition.py",
            "supervisor_harness/p0_candidate_admission_integration.py",
            "supervisor_harness/test_p0_candidate_admission_integration.py",
        }
        self.assertTrue(required.issubset(protocol_source_release.PROTOCOL_FILES))


if __name__ == "__main__":
    unittest.main()
