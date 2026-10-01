"""Focused pure-verifier tests for the zero-effect bridge canary receipt."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_rsi import digest, file_hash, fresh_json, load_json
from supervisor_harness import p0_gate1_source_scope_request_plan as bridge
from supervisor_harness import p0_gate1_source_scope_request_plan_canary_child as child
from supervisor_harness import source_scope_request_plan_canary_receipt as verifier
from supervisor_harness.supervisor_watchdog import SupervisorWatchdog
from supervisor_harness.test_p0_gate1_source_scope_request_plan_canary_child import (
    _packet, _provenance,
)


def _tree(base: Path):
    root = base / child.CANARY_ID
    artifacts = root / "artifacts"
    supervisor = root / "supervisor"
    artifacts.mkdir(parents=True)
    supervisor.mkdir()
    claim_root = base / "claims"
    claim_root.mkdir()
    release = {
        "tag": child.RELEASE_TAG,
        "commit": "b" * 40,
        "tag_object": "c" * 40,
        "source_sha256": "",
    }
    source_hashes = {"controlled.py": "a" * 64}
    release["source_sha256"] = digest(source_hashes)
    publication = {
        "schema": "market_rsi_protocol_publication_v1",
        "origin": child.PUBLISHED_ORIGIN,
        **release,
        "source_hashes": source_hashes,
        "isolation_proven": False,
        "model_authorship_proven": False,
    }
    fresh_json(root / "publication.json", publication)
    runtime = {
        "schema": verifier.RUNTIME_SCHEMA,
        "python_executable": "/durable/python",
        "python_version": "3.12.fixture",
        "source_hashes": source_hashes,
        "source_hashes_sha256": digest(source_hashes),
        "provider_modules_loaded": False,
        "public_fetch_modules_loaded": False,
        "watched_fetch_modules_loaded": False,
        "network_modules_loaded_by_canary": False,
    }
    fresh_json(root / "runtime.json", runtime)
    runtime_sha = digest(runtime)
    decision = deepcopy(bridge._EXPECTED_DECISION)
    packet = _packet()
    bundle = bridge.compile_document_request_plan(
        decision, _provenance(decision, packet), packet,
        d0_source_sha256=bridge.D0_CONTROLLED_SOURCE_SHA256)
    fresh_json(artifacts / "request-plan-bundle.json", bundle)

    permanent_claim = {
        "schema": verifier.PERMANENT_CLAIM_SCHEMA,
        "canary_id": child.CANARY_ID,
        "output_root": str(root),
        "release": release,
        "runtime_sha256": runtime_sha,
        "d0_evidence_sha256": dict(child.D0_FILE_SHA256),
        "request_plan_canonical_sha256": child.REQUEST_PLAN_CANONICAL_SHA256,
        "request_bundle_canonical_sha256": child.REQUEST_BUNDLE_CANONICAL_SHA256,
        "automatic_retry": False,
        "same_id_retry_allowed": False,
    }
    permanent_claim_path = claim_root / f"{child.CANARY_ID}.json"
    fresh_json(permanent_claim_path, permanent_claim)

    watchdog = SupervisorWatchdog(supervisor / "watchdog")
    watchdog.initialize()
    process_sha = "d" * 64
    input_sha = digest({
        "canary_id": child.CANARY_ID,
        "release": release,
        "runtime_sha256": runtime_sha,
        "request_plan_canonical_sha256": child.REQUEST_PLAN_CANONICAL_SHA256,
        "request_bundle_canonical_sha256": child.REQUEST_BUNDLE_CANONICAL_SHA256,
        "d0_evidence_sha256": child.D0_FILE_SHA256,
    })
    watchdog.claim_task(
        task_id=child.CANARY_ID, task_kind="research", stage="bridge_canary",
        owner="outer_supervisor", heartbeat_timeout_seconds=10,
        progress_timeout_seconds=20, input_sha256=input_sha,
        process_identity={"pid": 321, "command_sha256": process_sha},
        container_identity={
            "name": "market-rsi-b-" + child.CANARY_ID,
            "label": "market-rsi-b-" + child.CANARY_ID,
        })
    supervisor_claim = {
        "schema": child.SUPERVISOR_CLAIM_SCHEMA,
        "cycle_id": child.CANARY_ID,
        "task_id": child.CANARY_ID,
        "pid": 321,
        "process_command_sha256": process_sha,
        "supervisor_pid": 123,
        "supervisor_command_sha256": "e" * 64,
        "watchdog_head_sha256": watchdog.snapshot()["head_sha256"],
        "release": release,
        "runtime_sha256": runtime_sha,
        "request_plan_canonical_sha256": child.REQUEST_PLAN_CANONICAL_SHA256,
        "request_bundle_canonical_sha256": child.REQUEST_BUNDLE_CANONICAL_SHA256,
        "permanent_claim_sha256": file_hash(permanent_claim_path),
        "automatic_retry": False,
    }
    fresh_json(supervisor / "supervisor-claim.json", supervisor_claim)
    watchdog.heartbeat(child.CANARY_ID, material_progress=True,
                       progress_sha256="f" * 64)
    child_result = {
        "schema": child.CANARY_CHILD_SCHEMA,
        "canary_id": child.CANARY_ID,
        "passed": True,
        "release": release,
        "runtime_sha256": runtime_sha,
        "d0_evidence_sha256": dict(child.D0_FILE_SHA256),
        "request_plan_canonical_sha256": child.REQUEST_PLAN_CANONICAL_SHA256,
        "request_bundle_canonical_sha256": child.REQUEST_BUNDLE_CANONICAL_SHA256,
        "request_bundle_file_sha256": file_hash(
            artifacts / "request-plan-bundle.json"),
        "supervisor_claim_sha256": file_hash(supervisor / "supervisor-claim.json"),
        "provider_calls": 0,
        "network_requests": 0,
        "actual_provider_cost_usd": "0",
        "external_bytes_received": 0,
        "public_fetch_performed": False,
        "snapshot_retained": False,
        "data_admitted": False,
        "train_dev_final_read": False,
        "training_or_evaluation_performed": False,
        "automatic_retry": False,
    }
    fresh_json(artifacts / "result.json", child_result)
    watchdog.heartbeat(child.CANARY_ID, material_progress=True,
                       progress_sha256="1" * 64)
    watchdog.close_success(
        child.CANARY_ID, result_sha256=file_hash(artifacts / "result.json"))
    head = watchdog.snapshot()["head_sha256"]
    supervisor_result = {
        "schema": verifier.SUPERVISOR_RESULT_SCHEMA,
        "cycle_id": child.CANARY_ID,
        "passed": True,
        "child_exit_code": 0,
        "incident_created": False,
        "incident_id": None,
        "budget_state": "none",
        "data_gate_status": "not_applicable",
        "automatic_retry": False,
        "watchdog_head_sha256": head,
    }
    fresh_json(supervisor / "result.json", supervisor_result)
    terminal = {
        "schema": verifier.TERMINAL_CLEAR_SCHEMA,
        "canary_id": child.CANARY_ID,
        "exact_processes": [],
        "exact_containers": [],
        "container_label": None,
        "terminal_cleanup_verified": True,
    }
    fresh_json(root / "terminal-clear.json", terminal)
    receipt = {
        "schema": verifier.CANARY_SCHEMA,
        "canary_id": child.CANARY_ID,
        "passed": True,
        "release": release,
        "publication_path": str(root / "publication.json"),
        "publication_sha256": file_hash(root / "publication.json"),
        "runtime_path": str(root / "runtime.json"),
        "runtime_sha256": runtime_sha,
        "runtime_file_sha256": file_hash(root / "runtime.json"),
        "d0_evidence_sha256": dict(child.D0_FILE_SHA256),
        "request_plan_canonical_sha256": child.REQUEST_PLAN_CANONICAL_SHA256,
        "request_bundle_canonical_sha256": child.REQUEST_BUNDLE_CANONICAL_SHA256,
        "request_bundle_path": str(artifacts / "request-plan-bundle.json"),
        "request_bundle_file_sha256": file_hash(
            artifacts / "request-plan-bundle.json"),
        "permanent_claim_path": str(permanent_claim_path),
        "permanent_claim_sha256": file_hash(permanent_claim_path),
        "child_result_path": str(artifacts / "result.json"),
        "child_result_sha256": file_hash(artifacts / "result.json"),
        "supervisor_claim_path": str(supervisor / "supervisor-claim.json"),
        "supervisor_claim_sha256": file_hash(supervisor / "supervisor-claim.json"),
        "supervisor_result_path": str(supervisor / "result.json"),
        "supervisor_result_sha256": file_hash(supervisor / "result.json"),
        "watchdog_journal_path": str(supervisor / "watchdog" / "journal.jsonl"),
        "watchdog_journal_sha256": file_hash(
            supervisor / "watchdog" / "journal.jsonl"),
        "watchdog_snapshot_path": str(supervisor / "watchdog" / "snapshot.json"),
        "watchdog_snapshot_sha256": file_hash(
            supervisor / "watchdog" / "snapshot.json"),
        "watchdog_head_sha256": head,
        "terminal_clear_path": str(root / "terminal-clear.json"),
        "terminal_clear_sha256": file_hash(root / "terminal-clear.json"),
        "provider_calls": 0,
        "network_requests": 0,
        "actual_provider_cost_usd": "0",
        "external_bytes_received": 0,
        "public_fetch_performed": False,
        "snapshot_retained": False,
        "data_admitted": False,
        "train_dev_final_read": False,
        "training_or_evaluation_performed": False,
        "automatic_retry": False,
        "terminal_cleanup_verified": True,
    }
    fresh_json(root / "receipt.json", receipt)
    return root, claim_root, release, runtime_sha


class RequestPlanCanaryReceiptTests(unittest.TestCase):
    def test_complete_exact_tree_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, claim_root, release, runtime_sha = _tree(Path(temporary).resolve())
            receipt = root / "receipt.json"
            with patch.object(verifier, "RUN_ROOT", root), patch.object(
                    verifier, "CLAIM_ROOT", claim_root):
                result = verifier.verify_canary_receipt(
                    receipt, expected_receipt_sha256=file_hash(receipt),
                    expected_source_sha256=release["source_sha256"],
                    expected_runtime_sha256=runtime_sha,
                    expected_release_tag=release["tag"],
                    expected_release_commit=release["commit"],
                    expected_release_tag_object=release["tag_object"])
            self.assertTrue(result["passed"])
            self.assertEqual(result["provider_calls"], 0)
            self.assertTrue(result["terminal_cleanup_verified"])

    def test_false_is_not_accepted_as_a_zero_counter(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, claim_root, release, runtime_sha = _tree(Path(temporary).resolve())
            receipt = root / "receipt.json"
            value = load_json(receipt)
            receipt.unlink()
            value["provider_calls"] = False
            fresh_json(receipt, value)
            with patch.object(verifier, "RUN_ROOT", root), patch.object(
                    verifier, "CLAIM_ROOT", claim_root):
                with self.assertRaisesRegex(ValueError, "external-effect boundary"):
                    verifier.verify_canary_receipt(
                        receipt, expected_receipt_sha256=file_hash(receipt),
                        expected_source_sha256=release["source_sha256"],
                        expected_runtime_sha256=runtime_sha,
                        expected_release_tag=release["tag"],
                        expected_release_commit=release["commit"],
                        expected_release_tag_object=release["tag_object"])

    def test_mutated_bundle_and_wrong_durable_root_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, claim_root, release, runtime_sha = _tree(Path(temporary).resolve())
            receipt = root / "receipt.json"
            bundle = root / "artifacts" / "request-plan-bundle.json"
            bundle.write_text("{}\n")
            with patch.object(verifier, "RUN_ROOT", root), patch.object(
                    verifier, "CLAIM_ROOT", claim_root):
                with self.assertRaisesRegex(ValueError, "file commitment changed"):
                    verifier.verify_canary_receipt(
                        receipt, expected_receipt_sha256=file_hash(receipt),
                        expected_source_sha256=release["source_sha256"],
                        expected_runtime_sha256=runtime_sha,
                        expected_release_tag=release["tag"],
                        expected_release_commit=release["commit"],
                        expected_release_tag_object=release["tag_object"])
            with self.assertRaisesRegex(ValueError, "durable non-cloud"):
                verifier.verify_canary_receipt(
                    receipt, expected_receipt_sha256=file_hash(receipt),
                    expected_source_sha256=release["source_sha256"],
                    expected_runtime_sha256=runtime_sha,
                    expected_release_tag=release["tag"],
                    expected_release_commit=release["commit"],
                    expected_release_tag_object=release["tag_object"])


if __name__ == "__main__":
    unittest.main()
