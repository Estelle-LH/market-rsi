"""Focused offline tests for the exact source-scope fetch adapter."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from market_rsi import digest, file_hash, fresh_json
from supervisor_harness import p0_gate1_source_scope_fetch_adapter as adapter
from supervisor_harness import p0_gate1_source_scope_request_plan as bridge
from supervisor_harness.test_p0_gate1_source_scope_request_plan import (
    _decision, _packet, _provenance,
)


SOURCE_HASHES = {"controlled.py": "a" * 64}
SOURCE_SHA256 = digest(SOURCE_HASHES)
RUNTIME = {"schema": "fixture-runtime", "python": "3.12"}
RUNTIME_SHA256 = digest(RUNTIME)
RELEASE = {"tag": adapter.RELEASE_TAG, "commit": "b" * 40,
           "tag_object": "c" * 40, "source_sha256": SOURCE_SHA256}


def bundle() -> dict:
    decision = _decision()
    packet = _packet()
    return bridge.compile_document_request_plan(
        decision, _provenance(decision, packet), packet,
        d0_source_sha256=bridge.D0_CONTROLLED_SOURCE_SHA256)


def canary(path: Path, receipt_sha256: str) -> dict:
    evidence = {
        "publication": "1" * 64, "runtime": "2" * 64,
        "request_bundle": "3" * 64, "permanent_claim": "4" * 64,
        "child_result": "5" * 64, "supervisor_claim": "6" * 64,
        "supervisor_result": "7" * 64, "watchdog_journal": "8" * 64,
        "watchdog_snapshot": "9" * 64, "terminal_clear": "a" * 64,
    }
    return {
        "schema": adapter.CANARY_VERIFICATION_SCHEMA, "passed": True,
        "canary_id": adapter.CANARY_ID, "receipt_path": str(path),
        "receipt_sha256": receipt_sha256, "release": dict(RELEASE),
        "runtime_sha256": RUNTIME_SHA256,
        "d0_evidence_sha256": {
            "decision": "1" * 64, "submission": "2" * 64,
            "provenance": "3" * 64, "raw_response": "4" * 64,
            "packet": "5" * 64, "publication": "6" * 64,
            "result": "7" * 64, "review": "8" * 64,
        },
        "request_plan_canonical_sha256": adapter.REQUEST_PLAN_SHA256,
        "request_bundle_canonical_sha256": adapter.REQUEST_BUNDLE_SHA256,
        "request_bundle_file_sha256": "d" * 64,
        "provider_calls": 0, "network_requests": 0,
        "actual_provider_cost_usd": "0", "external_bytes_received": 0,
        "public_fetch_performed": False, "snapshot_retained": False,
        "data_admitted": False, "train_dev_final_read": False,
        "training_or_evaluation_performed": False, "automatic_retry": False,
        "terminal_cleanup_verified": True, "evidence_sha256": evidence,
    }


def make_binding(base: Path, *, authorization_mutation=None):
    root = base / adapter.ATTEMPT_ID
    receipt_path = base / "canary" / "receipt.json"
    receipt_path.parent.mkdir()
    receipt_path.write_text("canary\n")
    receipt_sha = file_hash(receipt_path)
    verified = canary(receipt_path, receipt_sha)
    authorization = {
        "schema": adapter.AUTHORIZATION_SCHEMA,
        "attempt_id": adapter.ATTEMPT_ID,
        "request_bundle_canonical_sha256": adapter.REQUEST_BUNDLE_SHA256,
        "request_plan_canonical_sha256": adapter.REQUEST_PLAN_SHA256,
        "document_url_sha256": adapter.DOCUMENT_URL_SHA256,
        "release": dict(RELEASE), "runtime_sha256": RUNTIME_SHA256,
        "prior_canary_receipt_sha256": receipt_sha,
        "prior_canary_verification_sha256": digest(verified),
        "output_root": str(root), "fetch_authorized": True,
        "snapshot_retention_authorized": True,
        "max_requests": 1, "max_response_bytes": 1_000_000,
        "max_elapsed_seconds": 300, "transport_timeout_seconds": 15,
        "provider_cost_usd": "0", "redirects_allowed": False,
        "automatic_retries_allowed": False, "alternate_url_allowed": False,
        "credential_use_allowed": False, "purchase_allowed": False,
        "source_write_allowed": False,
        "formal_data_admission_authorized": False,
        "train_dev_final_access_authorized": False,
        "training_evaluation_authorized": False,
        "snapshot_redistribution_authorized": False,
        "prediction_claim_authorized": False,
    }
    if authorization_mutation:
        authorization_mutation(authorization)
    auth_path = base / "authorization.json"
    fresh_json(auth_path, authorization)
    os.chmod(auth_path, 0o600)
    with patch.object(adapter.protocol_source_release, "source_hashes",
                      return_value=SOURCE_HASHES), patch.object(
            adapter, "_verify_canary_receipt", return_value=verified):
        decision = _decision()
        packet = _packet()
        binding = adapter.prepare_execution_binding(
            bundle(), d0_decision=decision,
            d0_decision_provenance=_provenance(decision, packet),
            d0_packet=packet, authorization_path=auth_path,
            expected_authorization_sha256=file_hash(auth_path),
            canary_receipt_path=receipt_path,
            expected_canary_receipt_sha256=receipt_sha,
            runtime_receipt=RUNTIME, output_root=root)
    return binding, auth_path, verified


class SourceScopeFetchAdapterTests(unittest.TestCase):
    def test_exact_bundle_authority_and_real_verifier_shape_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / adapter.ATTEMPT_ID
            with patch.object(adapter, "RUN_ROOT", root):
                binding, _, verified = make_binding(base)
                self.assertEqual(
                    adapter.validate_task_admission(
                        binding["task"], binding["admission"]),
                    (binding["task"], binding["admission"]))
                self.assertEqual(
                    binding["canary_verification_canonical_sha256"],
                    digest(verified))

    def test_short_reads_are_completed_and_hash_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / adapter.ATTEMPT_ID
            with patch.object(adapter, "RUN_ROOT", root):
                _, auth, _ = make_binding(base)
                real_read = os.read
                with patch.object(adapter.os, "read",
                                  side_effect=lambda fd, size: real_read(
                                      fd, min(size, 3))):
                    value, observed = adapter.load_authorization(
                        auth, expected_sha256=file_hash(auth))
                self.assertEqual(value["attempt_id"], adapter.ATTEMPT_ID)
                self.assertEqual(observed, file_hash(auth))

    def test_every_nested_language_is_closed_and_cross_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / adapter.ATTEMPT_ID
            with patch.object(adapter, "RUN_ROOT", root):
                binding, _, _ = make_binding(base)
                mutations = []
                for target in ("task", "admission"):
                    value = deepcopy(binding)
                    value[target]["extra"] = False
                    value[target + "_canonical_sha256"] = digest(value[target])
                    if target == "task":
                        value["admission"]["task_canonical_sha256"] = digest(
                            value["task"])
                        value["admission_canonical_sha256"] = digest(
                            value["admission"])
                    mutations.append(value)
                for section, key, changed in (
                        ("bounds", "max_requests", 2),
                        ("policy", "redirects_allowed", True),
                        ("authority", "formal_data_admission_authorized", True),
                        ("release", "source_sha256", "f" * 64),
                        ("request", "method", "POST"),
                        ("source", "url", "https://attacker.invalid/")):
                    value = deepcopy(binding)
                    value["task"][section][key] = changed
                    value["task_canonical_sha256"] = digest(value["task"])
                    value["admission"]["task_canonical_sha256"] = digest(
                        value["task"])
                    value["admission_canonical_sha256"] = digest(
                        value["admission"])
                    mutations.append(value)
                for value in mutations:
                    with self.subTest(value=value["task"].get("bounds")):
                        with self.assertRaises(ValueError):
                            adapter.validate_execution_binding(value)

    def test_authority_extra_wrong_type_and_separate_permission_reject(self):
        changes = (
            lambda value: value.__setitem__("extra", False),
            lambda value: value.__setitem__("fetch_authorized", 1),
            lambda value: value.__setitem__(
                "formal_data_admission_authorized", True),
            lambda value: value["release"].__setitem__(
                "source_sha256", "f" * 64),
        )
        for index, change in enumerate(changes):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary).resolve()
                root = base / adapter.ATTEMPT_ID
                with patch.object(adapter, "RUN_ROOT", root):
                    with self.assertRaises(ValueError):
                        make_binding(base, authorization_mutation=change)

    def test_arbitrary_output_and_bare_canary_digest_are_not_interfaces(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            with self.assertRaises(ValueError):
                make_binding(base)
        self.assertNotIn("canary_verification_sha256",
                         adapter.prepare_execution_binding.__annotations__)


if __name__ == "__main__":
    unittest.main()
