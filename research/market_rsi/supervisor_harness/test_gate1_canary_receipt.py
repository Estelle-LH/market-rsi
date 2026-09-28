from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch

from supervisor_harness.gate1_canary_receipt import (
    BOOTSTRAP_CANARY_SCHEMA,
    FIRST_CANARY_BOOTSTRAP_FILE,
    FIRST_CANARY_CHILD_ENTRY,
    FIRST_CANARY_CHILD_RELATIVE,
    PUBLISHED_ORIGIN,
    _MAX_PRIOR_CHAIN_DEPTH,
    PRIOR_VERIFICATION_FILE,
    _digest,
    _verify_gate1_canary_receipt,
    first_canary_bootstrap_document,
    verify_first_canary_bootstrap,
    verify_gate1_canary_receipt,
)
from supervisor_harness import p0_gate1_controller_adapter as controller_adapter
from supervisor_harness import gate1_canary_receipt as receipt_module
from supervisor_harness import p0_gate1_controller_live_entry as live_entry
from supervisor_harness import p0_gate1_controller_supervisor_parent as parent_module
from supervisor_harness import protocol_source_release
from supervisor_harness import prospective_source_scope_decision as source_scope


FIXTURE_NAME = "market-rsi-gate1-receipt-unit-fixture-v5-01"
FIXTURE_SOURCE_HASHES = {
    "supervisor_harness/run_p0_gate1_controller_production_cli_canary.py":
        "a" * 64,
}
FIXTURE_RUNTIME = {
    "schema": "market_bounded_live_outer_runtime_v3",
    "python_executable": "hermetic-fixture-python",
    "python_version": "3.12.0 (hermetic receipt fixture)",
}
SOURCE = _digest(FIXTURE_SOURCE_HASHES)
RUNTIME = _digest(FIXTURE_RUNTIME)
TAG = "market-rsi-protocol-v-hermetic-receipt-unit"
COMMIT = "1" * 40
TAG_OBJECT = "2" * 40
REAL_TAG = "market-rsi-protocol-v9.9.9"
REAL_COMMIT = "3" * 40
REAL_TAG_OBJECT = "4" * 40


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def _rehash_generic_journal(path: Path) -> list[dict]:
    records = [json.loads(line) for line in path.read_text().splitlines()]
    previous = "0" * 64
    for index, record in enumerate(records):
        record["seq"] = index
        record["previous"] = previous
        record["hash"] = _digest({key: value for key, value in record.items()
                                  if key != "hash"})
        previous = record["hash"]
    path.write_text("".join(json.dumps(record, sort_keys=True,
                                      separators=(",", ":")) + "\n"
                            for record in records))
    return records


def _rehash_watchdog(path: Path) -> list[dict]:
    records = [json.loads(line) for line in path.read_text().splitlines()]
    previous = "0" * 64
    for index, record in enumerate(records, 1):
        record["seq"] = index
        record["prev_sha256"] = previous
        record["sha256"] = _digest({key: value for key, value in record.items()
                                    if key != "sha256"})
        previous = record["sha256"]
    path.write_text("".join(json.dumps(record, sort_keys=True,
                                      separators=(",", ":")) + "\n"
                            for record in records))
    return records


def _build_legacy_v5_fixture(root: Path) -> dict[str, str]:
    """Write one relocatable synthetic v5 receipt tree for verifier tests."""
    root = Path(root)
    if not root.is_absolute():
        raise ValueError("absolute fixture root required")
    if root.exists() or root.is_symlink():
        raise FileExistsError("fresh fixture root required")
    if not root.parent.is_dir() or root.parent.is_symlink():
        raise ValueError("exact fixture parent required")

    cycle = root.name + "-transaction"
    transaction = root / cycle
    adapter_root = transaction / "adapter" / cycle
    supervisor_root = root / "supervisor"
    watchdog_root = supervisor_root / "watchdog"
    for directory in (
            adapter_root, watchdog_root, root / "budget",
            root / "global-state", root / "claims"):
        directory.mkdir(parents=True, mode=0o700)

    decision_path = root / "decision.md"
    decision_path.write_text("synthetic hermetic Gate 1 receipt fixture only\n")
    packet = {
        "schema": "market_p0_gate1_controller_packet_fixture_v1",
        "purpose": "exercise the legacy receipt verifier without authority",
    }
    _write(root / "controller-input.json", packet)
    _write(root / "runtime.json", FIXTURE_RUNTIME)
    _write(transaction / "input.json", packet)
    _write(transaction / "runtime.json", FIXTURE_RUNTIME)

    claim = {
        "schema": "market_p0_gate1_controller_adapter_claim_v5",
        "cycle_id": cycle,
        "packet_sha256": _digest(packet),
        "source_hashes": {"hermetic_fixture.py": "b" * 64},
        "runtime": {
            "python_executable": FIXTURE_RUNTIME["python_executable"],
            "python_version": FIXTURE_RUNTIME["python_version"],
        },
        "requested_model": "hermetic-offline-model",
        "tools": ["submit_bounded_plan"],
        "reasoning_effort": "low",
        "num_samples": 1,
        "temperature": 1.0,
        "seed": 23,
        "max_output_tokens": 256,
        "sample_timeout_seconds": 30,
        "automatic_retry": False,
        "execution_mode": "offline_fake",
        "formal_data_admitted": False,
    }
    _write(root / "claims" / f"{cycle}.json", claim)
    _write(adapter_root / "claim.json", claim)
    _write(adapter_root / "input.json", packet)
    encoded = {
        "rendered_prompt": "hermetic legacy receipt fixture",
        "token_ids": [101, 102, 103],
        "tokenizer_repo": "hermetic/offline",
        "tokenizer_revision": "fixture",
        "chat_template_sha256": "c" * 64,
    }
    _write(adapter_root / "encoded.json", encoded)
    _write(transaction / "preencoded.json", encoded)
    _write(adapter_root / "request.json", {
        "schema": "market_p0_gate1_controller_request_fixture_v1",
        "model": "hermetic-offline-model",
        "num_samples": 1,
        "input_sha256": _hash(adapter_root / "input.json"),
    })
    _write(adapter_root / "cost-preview.json", {
        "schema": "market_p0_gate1_controller_cost_preview_v1",
        "upper_usd_not_invoice": "0.00005103",
        "provider_called": False,
        "budget_mutated_by_adapter": False,
    })
    raw_text = "hermetic offline bounded-plan fixture"
    sampled = {
        "text": raw_text,
        "output_tokens": [201, 202, 203],
        "cached_input_tokens": 0,
        "finish_reason": "stop",
        "provider": {
            "reported_model": "hermetic-offline-model",
            "session_id": "hermetic-fixture-session",
            "sampling_session_id": "hermetic-fixture-sampling-session",
        },
    }
    _write(adapter_root / "raw-response.json", sampled)
    (adapter_root / "raw-response.txt").write_text(raw_text)
    _write(adapter_root / "provider-receipt.json", {
        "schema": "market_p0_gate1_controller_provider_receipt_v1",
        "terminal": True,
        "provider_called": False,
        "automatic_retry": False,
        "sample_count": 1,
        "reported_model": "hermetic-offline-model",
        "input_tokens": 3,
        "output_tokens": 3,
        "cached_input_tokens": 0,
        "metered_cost_usd_not_invoice": "0.00005103",
    })
    _write(adapter_root / "submission.json", {
        "kind": "bounded_plan", "fixture": True,
    })
    _write(adapter_root / "decision.json", {
        "schema": "market_p0_gate1_controller_decision_fixture_v1",
        "status": "non_executable",
    })

    artifact_names = {
        "claim.json", "cost-preview.json", "decision.json", "encoded.json",
        "failure.json", "field-provenance.json", "input.json",
        "proposal.json", "provider-receipt.json", "raw-response.json",
        "raw-response.txt", "request.json", "submission.json", "task.json",
    }
    artifact_sha256 = {
        name: (_hash(adapter_root / name)
               if (adapter_root / name).is_file() else None)
        for name in sorted(artifact_names)
    }
    adapter = {
        "schema": "market_p0_gate1_controller_adapter_result_v5",
        "cycle_id": cycle,
        "dispatch_gate_called": True,
        "execution_mode": "offline_fake",
        "automatic_retry": False,
        "provider_called": False,
        "sample_count_max": 1,
        "formal_data_admitted": False,
        "public_fetch_performed": False,
        "sealed_data_read": False,
        "completed_live_decision_pending_review": False,
        "valid_plan_only_decision": True,
        "valid_non_executable_proposal": False,
        "submission_kind": "bounded_plan",
        "failure_type": None,
        "requested_model": "hermetic-offline-model",
        "reported_model": "hermetic-offline-model",
        "input_tokens": 3,
        "output_tokens": 3,
        "cached_input_tokens": 0,
        "metered_cost_usd_not_invoice": "0.00005103",
        "tools": ["submit_bounded_plan"],
        "registry_claim_sha256": _hash(root / "claims" / f"{cycle}.json"),
        "artifact_sha256": artifact_sha256,
    }
    _write(adapter_root / "result.json", adapter)

    publication = {
        "schema": "market_rsi_protocol_publication_v1",
        "origin": PUBLISHED_ORIGIN,
        "tag": TAG,
        "commit": COMMIT,
        "tag_object": TAG_OBJECT,
        "source_sha256": SOURCE,
        "source_hashes": FIXTURE_SOURCE_HASHES,
        "isolation_proven": False,
        "model_authorship_proven": False,
    }
    admission = {
        "schema": "market_p0_gate1_controller_outer_v1",
        "cycle_id": cycle,
        "execution_mode": "offline_fake",
        "automatic_retry": False,
        "formal_data_admitted": False,
        "public_fetch_authorized": False,
        "provider_sample_max": 1,
        "packet_sha256": _digest(packet),
        "source_sha256": SOURCE,
        "prior_canary_sha256": FIXTURE_SOURCE_HASHES[
            "supervisor_harness/run_p0_gate1_controller_production_cli_canary.py"],
        "publication_sha256": _digest(publication),
        "runtime_sha256": RUNTIME,
        "budget_bucket": "setup",
        "budget_cap_usd": "1",
        "budget_experiment_id": "hermetic-receipt-fixture",
        "provider": "offline_fake",
        "upper_usd_not_invoice": "0.00005103",
    }
    _write(transaction / "admission.json", admission)
    _write(transaction / "preflight.json", {
        "schema": "market_bounded_live_outer_preflight_v3",
        "cycle_id": cycle,
        "clear": True,
        "matching_process_ids": [],
        "matching_container_ids": [],
    })
    _write(transaction / "publication.json", publication)
    review = {
        "schema": "market_p0_gate1_controller_review_v1",
        "cycle_id": cycle,
        "adapter_passed": True,
        "adapter_result_sha256": _hash(adapter_root / "result.json"),
        "task_sha256": None,
        "proposal_sha256": None,
        "compiled_plan_sha256": None,
        "automatic_retry": False,
        "formal_data_admitted": False,
        "public_fetch_performed": False,
        "provider_receipt_valid": True,
        "publication_runtime_state_unchanged": True,
    }
    _write(transaction / "review.json", review)
    child = {
        "schema": "market_p0_gate1_controller_outer_result_v1",
        "cycle_id": cycle,
        "passed": True,
        "execution_mode": "offline_fake",
        "provider_sample_max": 1,
        "automatic_retry": False,
        "formal_data_admitted": False,
        "public_fetch_performed": False,
        "input_sha256": _hash(transaction / "input.json"),
        "admission_sha256": _hash(transaction / "admission.json"),
        "preflight_sha256": _hash(transaction / "preflight.json"),
        "publication_sha256": _hash(transaction / "publication.json"),
        "runtime_sha256": _hash(transaction / "runtime.json"),
        "adapter_result_sha256": _hash(adapter_root / "result.json"),
        "review_sha256": _hash(transaction / "review.json"),
        "compiled_plan_sha256": None,
        "submission_kind": "bounded_plan",
        "ledger_outcome": "metered_terminal",
        "supervisor_outcome": "passed",
        "upper_usd_not_invoice": "0.00005103",
    }
    _write(transaction / "result.json", child)

    watchdog_path = watchdog_root / "journal.jsonl"
    watchdog_path.write_text("".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        for record in (
            {"schema": "market_supervisor_watchdog_v1",
             "time_utc": "2026-01-01T00:00:00.000000Z",
             "event": "initialize", "payload": {}},
            {"schema": "market_supervisor_watchdog_v1",
             "time_utc": "2026-01-01T00:00:01.000000Z",
             "event": "task_claim", "payload": {
                 "task_id": cycle, "status": "active", "incident_id": None,
                 "data_gate": None, "data_admission_sha256": None,
                 "process_identity": {"pid": 4242,
                                      "command_sha256": "d" * 64},
                 "container_identity": {
                     "name": f"market-rsi-b-{cycle}",
                     "label": f"market-rsi-b-{cycle}"}}},
            {"schema": "market_supervisor_watchdog_v1",
             "time_utc": "2026-01-01T00:00:02.000000Z",
             "event": "heartbeat", "payload": {
                 "task_id": cycle, "material_progress": True,
                 "progress_sha256": "e" * 64}},
            {"schema": "market_supervisor_watchdog_v1",
             "time_utc": "2026-01-01T00:00:03.000000Z",
             "event": "task_close", "payload": {
                 "task_id": cycle, "outcome": "passed",
                 "old_id_reusable": False,
                 "result_sha256": _hash(transaction / "result.json")}},
        )))
    watchdog = _rehash_watchdog(watchdog_path)
    _write(watchdog_root / "snapshot.json", {
        "schema": "market_supervisor_watchdog_v1",
        "initialized": True,
        "seq": len(watchdog),
        "head_sha256": watchdog[-1]["sha256"],
        "last_event_utc": watchdog[-1]["time_utc"],
        "active_task": None,
        "claimed_task_ids": [cycle],
        "incidents": [],
    })
    _write(supervisor_root / "supervisor-claim.json", {
        "schema": "market_bounded_live_supervisor_claim_v1",
        "cycle_id": cycle,
        "task_id": cycle,
        "automatic_retry": False,
        "pid": 4242,
        "watchdog_head_sha256": watchdog[1]["sha256"],
    })
    _write(supervisor_root / "result.json", {
        "schema": "market_bounded_live_supervisor_parent_v1",
        "cycle_id": cycle,
        "passed": True,
        "automatic_retry": False,
        "child_exit_code": 0,
        "incident_created": False,
        "incident_id": None,
        "watchdog_head_sha256": watchdog[-1]["sha256"],
    })
    (supervisor_root / "child.log").write_bytes(
        (transaction / "result.json").read_bytes())

    global_path = root / "global-state" / "journal.jsonl"
    global_path.write_text("".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        for record in (
            {"time": "2026-01-01T00:00:00.000000Z", "event": "initialize",
             "payload": {"decision_doc_sha256": _hash(decision_path)}},
            {"time": "2026-01-01T00:00:01.000000Z", "event": "cycle_claim",
             "payload": {
                 "cycle_id": cycle, "source_sha256": SOURCE,
                 "prior_canary_sha256": FIXTURE_SOURCE_HASHES[
                     "supervisor_harness/run_p0_gate1_controller_production_cli_canary.py"],
                 "decision_doc_sha256": _hash(decision_path)}},
            {"time": "2026-01-01T00:00:03.000000Z", "event": "cycle_close",
             "payload": {"cycle_id": cycle, "outcome": "passed",
                         "review_sha256": _hash(transaction / "review.json")}},
        )))
    _rehash_generic_journal(global_path)

    meter = {
        "adapter_result_sha256": _hash(adapter_root / "result.json"),
        "terminal": True,
        "provider_called": False,
        "automatic_retry": False,
        "sample_count": 1,
        "metered_cost_usd_not_invoice": "0.00005103",
    }
    _write(root / "budget" / f"{cycle}.metering.json", meter)
    budget_path = root / "budget" / "journal.jsonl"
    budget_path.write_text("".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        for record in (
            {"time": "2026-01-01T00:00:00.000000Z", "event": "authorized",
             "payload": {"experiment_id": "hermetic-receipt-fixture"}},
            {"time": "2026-01-01T00:00:01.000000Z", "event": "reserved",
             "payload": {"job_id": cycle, "input_sha256": _digest(packet)}},
            {"time": "2026-01-01T00:00:02.000000Z", "event": "dispatched",
             "payload": {"job_id": cycle}},
            {"time": "2026-01-01T00:00:03.000000Z",
             "event": "metered_terminal", "payload": {
                 "job_id": cycle, "metered_usd": "0.00005103",
                 "receipt_sha256": _digest(meter)}},
        )))
    _rehash_generic_journal(budget_path)

    receipt = {
        "schema": "market_p0_gate1_controller_production_cli_canary_v1",
        "cycle_id": cycle,
        "passed": True,
        "production_parent_used": True,
        "production_cli_arguments_used": True,
        "supervisor_claim_verified_by_child": True,
        "offline_provider_substituted": True,
        "provider_calls": 0,
        "actual_provider_cost_usd": "0",
        "synthetic_ledger_metered_usd": "0.00005103",
        "public_fetch_performed": False,
        "formal_data_admitted": False,
        "review_only_without_catalog": True,
        "automatic_retry": False,
        "packet_file_sha256": _hash(root / "controller-input.json"),
        "packet_canonical_sha256": _digest(packet),
        "child_result_sha256": _hash(transaction / "result.json"),
        "supervisor_claim_sha256": _hash(
            supervisor_root / "supervisor-claim.json"),
        "supervisor_result_sha256": _hash(supervisor_root / "result.json"),
    }
    _write(root / "canary-result.json", receipt)
    return {
        "source_sha256": SOURCE,
        "runtime_sha256": RUNTIME,
        "receipt_sha256": _hash(root / "canary-result.json"),
    }


def _scope_submission() -> dict:
    options = controller_adapter.expected_packet()[
        "prospective_source_scope_decision"]
    pair = options["source_response_options"][1]
    split = options["split_policy"]
    cutoff = options["cutoff_contract"]
    return {
        "scientific_source_response": {
            "source_registry_entry_id": pair["source_registry_entry_id"],
            "response_class_id": pair["response_class_id"],
        },
        "intended_uses": {
            "requested_use_ids": ["model_training", "private_research"],
        },
        "future_role_split": {
            "requested_future_role": "train_candidate",
            "split_policy_id": split["split_policy_id"],
            "split_policy_sha256": split["split_policy_sha256"],
            "exposure_ledger_id": "not_yet_created",
        },
        "horizon_cutoff": {
            "claim_semantics": "prospective_point_in_time",
            "prediction_horizon_us": 60_000_000,
            "cutoff_semantics_id": cutoff["cutoff_semantics_id"],
            "cutoff_contract_sha256": cutoff["cutoff_contract_sha256"],
            "label_window_start_relation": "strictly_after_cutoff",
            "label_window_end_relation": "at_or_before_cutoff_plus_horizon",
        },
        "bounded_investigation": {
            "mode": "first_party_document_review_only",
            "max_documents_proposed": 1,
            "max_provider_requests_proposed": 0,
            "max_raw_bytes_proposed": 0,
            "max_elapsed_seconds_proposed": 300,
        },
    }


def _submitted(value: dict) -> str:
    arguments = []
    for key, item in value.items():
        encoded = json.dumps(item, separators=(",", ":"))
        arguments.append(
            f"<arg_key>{key}</arg_key><arg_value>{encoded}</arg_value>")
    return ("fixture reasoning</think>\n<tool_call>submit_source_scope_decision"
            + "".join(arguments) + "</tool_call>")


class StableAncestorIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.ancestor = self.root / "evidence"
        self.ancestor.mkdir()
        self.target = self.ancestor / "receipt.json"
        self.target.write_bytes(b'{"passed":true}\n')

    def snapshots(self):
        return receipt_module._canonical_path_chain(
            self.target, "path-safety fixture")

    def test_unrelated_sibling_and_ancestor_timestamp_activity_is_accepted(self):
        expected = self.target.read_bytes()
        before = self.ancestor.stat()
        real_read = receipt_module.os.read
        changed = False

        def read_with_sibling_activity(descriptor, size):
            nonlocal changed
            if not changed:
                sibling = self.ancestor / "unrelated.tmp"
                sibling.write_bytes(b"unrelated")
                sibling.unlink()
                receipt_module.os.utime(
                    self.ancestor,
                    ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
                changed = True
            return real_read(descriptor, size)

        with patch.object(receipt_module.os, "read",
                          side_effect=read_with_sibling_activity):
            self.assertEqual(
                receipt_module._read_regular(
                    self.target, "path-safety fixture"), expected)
        after = self.ancestor.stat()
        self.assertTrue(changed)
        self.assertNotEqual((before.st_mtime_ns, before.st_ctime_ns),
                            (after.st_mtime_ns, after.st_ctime_ns))

    def test_ancestor_symlink_substitution_is_rejected(self):
        snapshots = self.snapshots()
        original = self.root / "evidence-original"
        self.ancestor.rename(original)
        self.ancestor.symlink_to(original, target_is_directory=True)
        try:
            with self.assertRaisesRegex(ValueError, "ancestor changed"):
                receipt_module._confirm_path_chain(
                    snapshots, "path-safety fixture")
        finally:
            self.ancestor.unlink()
            original.rename(self.ancestor)

    def test_ancestor_replacement_inode_is_rejected(self):
        snapshots = self.snapshots()
        original = self.root / "evidence-original"
        self.ancestor.rename(original)
        self.ancestor.mkdir()
        try:
            with self.assertRaisesRegex(ValueError, "ancestor changed"):
                receipt_module._confirm_path_chain(
                    snapshots, "path-safety fixture")
        finally:
            self.ancestor.rmdir()
            original.rename(self.ancestor)

    def test_ancestor_type_change_is_rejected(self):
        snapshots = self.snapshots()
        original = self.root / "evidence-original"
        self.ancestor.rename(original)
        self.ancestor.write_bytes(b"not a directory")
        try:
            with self.assertRaisesRegex(ValueError, "ancestor changed"):
                receipt_module._confirm_path_chain(
                    snapshots, "path-safety fixture")
        finally:
            self.ancestor.unlink()
            original.rename(self.ancestor)

    def test_ancestor_mode_change_is_rejected(self):
        snapshots = self.snapshots()
        original_mode = stat.S_IMODE(self.ancestor.stat().st_mode)
        changed_mode = original_mode ^ stat.S_IXUSR
        self.ancestor.chmod(changed_mode)
        try:
            with self.assertRaisesRegex(ValueError, "ancestor changed"):
                receipt_module._confirm_path_chain(
                    snapshots, "path-safety fixture")
        finally:
            self.ancestor.chmod(original_mode)

    def test_target_file_mutation_remains_rejected(self):
        real_read = receipt_module.os.read
        changed = False

        def read_after_target_mutation(descriptor, size):
            nonlocal changed
            if not changed:
                self.target.write_bytes(b'{"passed":false,"changed":true}\n')
                changed = True
            return real_read(descriptor, size)

        with patch.object(receipt_module.os, "read",
                          side_effect=read_after_target_mutation):
            with self.assertRaisesRegex(ValueError, "changed during verification"):
                receipt_module._read_regular(
                    self.target, "path-safety fixture")


class FirstCanaryBootstrapProofTests(unittest.TestCase):
    RUNTIME = "b" * 64

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.path = self.root / FIRST_CANARY_BOOTSTRAP_FILE
        source_hashes = {
            FIRST_CANARY_CHILD_RELATIVE: _hash(FIRST_CANARY_CHILD_ENTRY),
            "supervisor_harness/example-controlled-source.py": "a" * 64,
        }
        self.publication = {
            "schema": "market_rsi_protocol_publication_v1",
            "origin": PUBLISHED_ORIGIN,
            "tag": REAL_TAG,
            "commit": REAL_COMMIT,
            "tag_object": REAL_TAG_OBJECT,
            "source_sha256": _digest(source_hashes),
            "source_hashes": source_hashes,
            "isolation_proven": False,
            "model_authorship_proven": False,
        }
        self.source = self.publication["source_sha256"]
        _write(self.path, first_canary_bootstrap_document(
            publication=self.publication,
            runtime_sha256=self.RUNTIME,
            child_entry=FIRST_CANARY_CHILD_ENTRY))

    def verify(self, **overrides):
        arguments = {
            "expected_bootstrap_sha256": _hash(self.path),
            "expected_source_sha256": self.source,
            "expected_runtime_sha256": self.RUNTIME,
            "expected_release_tag": REAL_TAG,
            "expected_release_commit": REAL_COMMIT,
            "expected_release_tag_object": REAL_TAG_OBJECT,
            "expected_child_entry": FIRST_CANARY_CHILD_ENTRY,
        }
        arguments.update(overrides)
        return verify_first_canary_bootstrap(self.path, **arguments)

    def test_exact_bootstrap_is_zero_provider_and_fully_bound(self):
        result = self.verify()
        self.assertTrue(result["passed"])
        self.assertEqual(result["provider_calls"], 0)
        self.assertEqual(result["actual_provider_cost_usd"], "0")
        self.assertEqual(result["source_sha256"], self.source)
        self.assertEqual(result["runtime_sha256"], self.RUNTIME)
        self.assertEqual(result["child_entry"]["path"],
                         str(FIRST_CANARY_CHILD_ENTRY))

    def test_source_runtime_release_and_child_are_not_substitutable(self):
        mutations = (
            {"expected_source_sha256": "c" * 64},
            {"expected_runtime_sha256": "d" * 64},
            {"expected_release_tag": "market-rsi-protocol-v0.1.22"},
            {"expected_release_commit": "7" * 40},
            {"expected_release_tag_object": "8" * 40},
            {"expected_child_entry": Path(__file__).resolve()},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValueError):
                    self.verify(**mutation)

    def test_mutated_or_extended_bootstrap_fails_even_when_rehashed(self):
        for field, value in (
                ("provider_calls_max", 1),
                ("live_provider_constructor_allowed", True),
                ("actual_provider_cost_usd", "0.01"),
                ("unexpected", False)):
            with self.subTest(field=field):
                document = first_canary_bootstrap_document(
                    publication=self.publication,
                    runtime_sha256=self.RUNTIME,
                    child_entry=FIRST_CANARY_CHILD_ENTRY)
                document[field] = value
                _write(self.path, document)
                with self.assertRaisesRegex(
                        ValueError, "commitments differ"):
                    self.verify(expected_bootstrap_sha256=_hash(self.path))

    def test_forged_or_stale_nested_publication_fails_when_rehashed(self):
        cases = (
            ("origin", "https://example.invalid/forged.git"),
            ("tag", "market-rsi-protocol-v-synthetic-cli-canary"),
            ("commit", "7" * 40),
            ("unexpected", False),
        )
        for field, value in cases:
            with self.subTest(field=field):
                document = first_canary_bootstrap_document(
                    publication=self.publication,
                    runtime_sha256=self.RUNTIME,
                    child_entry=FIRST_CANARY_CHILD_ENTRY)
                document["publication"][field] = value
                _write(self.path, document)
                with self.assertRaises(ValueError):
                    self.verify(expected_bootstrap_sha256=_hash(self.path))

    def test_wrong_filename_and_symlink_fail(self):
        renamed = self.root / "canary-result.json"
        shutil.copy2(self.path, renamed)
        with self.assertRaisesRegex(ValueError, "bootstrap path"):
            verify_first_canary_bootstrap(
                renamed,
                expected_bootstrap_sha256=_hash(renamed),
                expected_source_sha256=self.source,
                expected_runtime_sha256=self.RUNTIME,
                expected_release_tag=REAL_TAG,
                expected_release_commit=REAL_COMMIT,
                expected_release_tag_object=REAL_TAG_OBJECT)
        alias_root = self.root / "alias"
        alias_root.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            verify_first_canary_bootstrap(
                alias_root / FIRST_CANARY_BOOTSTRAP_FILE,
                expected_bootstrap_sha256=_hash(self.path),
                expected_source_sha256=self.source,
                expected_runtime_sha256=self.RUNTIME,
                expected_release_tag=REAL_TAG,
                expected_release_commit=REAL_COMMIT,
                expected_release_tag_object=REAL_TAG_OBJECT)


class Gate1CanaryReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        temporary_root = Path(self.temporary.name).resolve()
        pristine_parent = temporary_root / "pristine"
        pristine_parent.mkdir()
        self.pristine_root = pristine_parent / FIXTURE_NAME
        identity = _build_legacy_v5_fixture(self.pristine_root)
        self.original_receipt_sha256 = identity["receipt_sha256"]
        working_parent = temporary_root / "working"
        working_parent.mkdir()
        self.root = working_parent / FIXTURE_NAME
        shutil.copytree(self.pristine_root, self.root)
        self.receipt = self.root / "canary-result.json"

    def reset_fixture(self) -> None:
        shutil.rmtree(self.root)
        shutil.copytree(self.pristine_root, self.root)
        self.receipt = self.root / "canary-result.json"

    def verify(self, **overrides):
        arguments = {
            "expected_receipt_sha256": _hash(self.receipt),
            "expected_source_sha256": SOURCE,
            "expected_runtime_sha256": RUNTIME,
            "expected_release_tag": TAG,
            "expected_release_commit": COMMIT,
            "expected_release_tag_object": TAG_OBJECT,
        }
        arguments.update(overrides)
        return verify_gate1_canary_receipt(self.receipt, **arguments)

    def rewrite_receipt(self, **updates) -> None:
        value = json.loads(self.receipt.read_text())
        value.update(updates)
        _write(self.receipt, value)

    def relink_child(self, **updates) -> None:
        canary = json.loads(self.receipt.read_text())
        child_path = self.root / canary["cycle_id"] / "result.json"
        child = json.loads(child_path.read_text())
        child.update(updates)
        _write(child_path, child)
        self.rewrite_receipt(child_result_sha256=_hash(child_path))

    def relink_admission(self) -> None:
        """Relink an edited admission through child, watchdog and receipt."""
        receipt = json.loads(self.receipt.read_text())
        cycle = receipt["cycle_id"]
        transaction = self.root / cycle
        child_path = transaction / "result.json"
        child = json.loads(child_path.read_text())
        child["admission_sha256"] = _hash(transaction / "admission.json")
        _write(child_path, child)

        watchdog_path = self.root / "supervisor/watchdog/journal.jsonl"
        watchdog = [json.loads(line) for line in watchdog_path.read_text().splitlines()]
        watchdog[-1]["payload"]["result_sha256"] = _hash(child_path)
        watchdog_path.write_text("".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            for record in watchdog))
        watchdog = _rehash_watchdog(watchdog_path)
        snapshot_path = self.root / "supervisor/watchdog/snapshot.json"
        snapshot = json.loads(snapshot_path.read_text())
        snapshot["head_sha256"] = watchdog[-1]["sha256"]
        _write(snapshot_path, snapshot)
        supervisor_result_path = self.root / "supervisor/result.json"
        supervisor_result = json.loads(supervisor_result_path.read_text())
        supervisor_result["watchdog_head_sha256"] = watchdog[-1]["sha256"]
        _write(supervisor_result_path, supervisor_result)
        (self.root / "supervisor/child.log").write_bytes(child_path.read_bytes())
        self.rewrite_receipt(
            child_result_sha256=_hash(child_path),
            supervisor_result_sha256=_hash(supervisor_result_path))

    def relink_watchdog(self, records: list[dict]) -> list[dict]:
        """Rehash a deliberate watchdog fixture and its terminal cross-links."""
        watchdog_path = self.root / "supervisor/watchdog/journal.jsonl"
        watchdog_path.write_text("".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            for record in records))
        records = _rehash_watchdog(watchdog_path)
        snapshot_path = self.root / "supervisor/watchdog/snapshot.json"
        snapshot = json.loads(snapshot_path.read_text())
        snapshot.update({
            "seq": len(records),
            "head_sha256": records[-1]["sha256"],
            "last_event_utc": records[-1]["time_utc"],
        })
        _write(snapshot_path, snapshot)
        supervisor_result_path = self.root / "supervisor/result.json"
        supervisor_result = json.loads(supervisor_result_path.read_text())
        supervisor_result["watchdog_head_sha256"] = records[-1]["sha256"]
        _write(supervisor_result_path, supervisor_result)
        self.rewrite_receipt(
            supervisor_result_sha256=_hash(supervisor_result_path))
        return records

    def watchdog_with_heartbeats(self, payloads: list[dict]) -> list[dict]:
        """Replace the one preserved heartbeat with deterministic payloads."""
        watchdog_path = self.root / "supervisor/watchdog/journal.jsonl"
        original = [json.loads(line) for line in
                    watchdog_path.read_text().splitlines()]
        template = original[2]
        heartbeats = []
        for index, payload in enumerate(payloads, 1):
            heartbeat = copy.deepcopy(template)
            heartbeat["time_utc"] = f"2026-09-24T02:18:{49 + index:02d}.000000Z"
            heartbeat["payload"] = payload
            heartbeats.append(heartbeat)
        return [original[0], original[1], *heartbeats, original[-1]]

    def relink_fixture(self) -> None:
        """Relink hashes after an adversarial fixture edit, without blessing it."""
        receipt = json.loads(self.receipt.read_text())
        cycle = receipt["cycle_id"]
        transaction = self.root / cycle
        adapter_root = transaction / "adapter" / cycle
        adapter_path = adapter_root / "result.json"
        adapter = json.loads(adapter_path.read_text())
        for name in adapter["artifact_sha256"]:
            path = adapter_root / name
            adapter["artifact_sha256"][name] = (
                _hash(path) if path.is_file() else None)
        adapter["registry_claim_sha256"] = _hash(
            self.root / "claims" / f"{cycle}.json")
        _write(adapter_path, adapter)

        meter_path = self.root / "budget" / f"{cycle}.metering.json"
        meter = json.loads(meter_path.read_text())
        meter["adapter_result_sha256"] = _hash(adapter_path)
        _write(meter_path, meter)
        budget_path = self.root / "budget" / "journal.jsonl"
        budget = [json.loads(line) for line in budget_path.read_text().splitlines()]
        packet = json.loads((self.root / "controller-input.json").read_text())
        budget[1]["payload"]["input_sha256"] = _digest(packet)
        budget[-1]["payload"]["receipt_sha256"] = _digest(meter)
        budget_path.write_text("".join(json.dumps(record, sort_keys=True,
                                                 separators=(",", ":")) + "\n"
                                       for record in budget))
        _rehash_generic_journal(budget_path)

        review_path = transaction / "review.json"
        review = json.loads(review_path.read_text())
        review.update({"adapter_result_sha256": _hash(adapter_path),
                       "task_sha256": None, "proposal_sha256": None,
                       "compiled_plan_sha256": None})
        _write(review_path, review)
        child_path = transaction / "result.json"
        child = json.loads(child_path.read_text())
        child.update({
            "input_sha256": _hash(transaction / "input.json"),
            "admission_sha256": _hash(transaction / "admission.json"),
            "adapter_result_sha256": _hash(adapter_path),
            "review_sha256": _hash(review_path),
            "submission_kind": "source_scope_decision",
            "compiled_plan_sha256": None,
        })
        _write(child_path, child)

        watchdog_path = self.root / "supervisor/watchdog/journal.jsonl"
        watchdog = [json.loads(line) for line in watchdog_path.read_text().splitlines()]
        watchdog[-1]["payload"]["result_sha256"] = _hash(child_path)
        watchdog_path.write_text("".join(json.dumps(record, sort_keys=True,
                                                   separators=(",", ":")) + "\n"
                                         for record in watchdog))
        watchdog = _rehash_watchdog(watchdog_path)
        snapshot_path = self.root / "supervisor/watchdog/snapshot.json"
        snapshot = json.loads(snapshot_path.read_text())
        snapshot["head_sha256"] = watchdog[-1]["sha256"]
        _write(snapshot_path, snapshot)
        supervisor_result_path = self.root / "supervisor/result.json"
        supervisor_result = json.loads(supervisor_result_path.read_text())
        supervisor_result["watchdog_head_sha256"] = watchdog[-1]["sha256"]
        _write(supervisor_result_path, supervisor_result)
        (self.root / "supervisor/child.log").write_bytes(child_path.read_bytes())

        global_path = self.root / "global-state/journal.jsonl"
        global_records = [json.loads(line) for line in global_path.read_text().splitlines()]
        global_records[-1]["payload"]["review_sha256"] = _hash(review_path)
        global_path.write_text("".join(json.dumps(record, sort_keys=True,
                                                separators=(",", ":")) + "\n"
                                      for record in global_records))
        _rehash_generic_journal(global_path)

        self.rewrite_receipt(
            packet_file_sha256=_hash(self.root / "controller-input.json"),
            packet_canonical_sha256=_digest(packet),
            child_result_sha256=_hash(child_path),
            supervisor_result_sha256=_hash(supervisor_result_path))

    def upgrade_fixture_to_v6_scope_decision(self) -> None:
        """Build an exact current-packet v6 fixture; this is not a canary."""
        prior_parent = Path(self.temporary.name).resolve() / "prior-evidence"
        prior_root = prior_parent / FIXTURE_NAME
        if not prior_root.exists():
            prior_parent.mkdir()
            shutil.copytree(self.pristine_root, prior_root)
        prior_receipt = prior_root / "canary-result.json"
        previous_verification = verify_gate1_canary_receipt(
            prior_receipt,
            expected_receipt_sha256=self.original_receipt_sha256,
            expected_source_sha256=SOURCE,
            expected_runtime_sha256=RUNTIME,
            expected_release_tag=TAG,
            expected_release_commit=COMMIT,
            expected_release_tag_object=TAG_OBJECT,
        )
        receipt = json.loads(self.receipt.read_text())
        cycle = receipt["cycle_id"]
        transaction = self.root / cycle
        adapter_root = transaction / "adapter" / cycle
        packet = controller_adapter.expected_packet()
        submission = _scope_submission()
        raw = _submitted(submission)
        sampled = {
            "text": raw,
            "output_tokens": [201, 202, 203],
            "cached_input_tokens": 0,
            "finish_reason": "stop",
            "provider": {
                "reported_model": controller_adapter.HF_MODEL,
                "session_id": "offline-v6-fixture-session",
                "sampling_session_id": "offline-v6-fixture-sampling-session",
            },
        }
        generated_parent = Path(tempfile.mkdtemp(
            dir=self.temporary.name, prefix="v6-adapter-fixture-"))
        generated_claims = generated_parent / "claims"
        generated_claims.mkdir(parents=True)
        generated_root = generated_parent / cycle
        result = controller_adapter.run(
            root=generated_root, claim_root=generated_claims,
            cycle_id=cycle, packet=packet,
            backend=controller_adapter.OfflineGate1ProviderFake(sampled),
            before_sample=lambda _preview: None)
        self.assertTrue(result["valid_source_scope_decision"])

        shutil.rmtree(adapter_root)
        shutil.copytree(generated_root, adapter_root)
        shutil.copy2(generated_claims / f"{cycle}.json",
                     self.root / "claims" / f"{cycle}.json")
        normalized_claim = json.loads((adapter_root / "claim.json").read_text())
        normalized_claim["runtime"] = {
            "python_executable": FIXTURE_RUNTIME["python_executable"],
            "python_version": FIXTURE_RUNTIME["python_version"],
        }
        _write(adapter_root / "claim.json", normalized_claim)
        _write(self.root / "claims" / f"{cycle}.json", normalized_claim)
        _write(self.root / "controller-input.json", packet)
        _write(transaction / "input.json", packet)
        shutil.copy2(adapter_root / "encoded.json", transaction / "preencoded.json")

        admission_path = transaction / "admission.json"
        admission = json.loads(admission_path.read_text())
        admission["packet_sha256"] = _digest(packet)
        admission["prior_canary_sha256"] = self.original_receipt_sha256
        admission["prior_canary_verification_sha256"] = _digest(
            previous_verification)
        _write(admission_path, admission)
        _write(transaction / PRIOR_VERIFICATION_FILE, previous_verification)

        global_path = self.root / "global-state/journal.jsonl"
        global_records = [json.loads(line) for line in global_path.read_text().splitlines()]
        global_records[1]["payload"]["prior_canary_sha256"] = (
            self.original_receipt_sha256)
        global_path.write_text("".join(json.dumps(record, sort_keys=True,
                                                separators=(",", ":")) + "\n"
                                      for record in global_records))
        _rehash_generic_journal(global_path)
        self.relink_fixture()

    def rewrite_v6_lineage(self, submission: dict, decision: dict) -> None:
        """Write a fully rehashed adversarial lineage into the v6 fixture."""
        receipt = json.loads(self.receipt.read_text())
        cycle = receipt["cycle_id"]
        adapter_root = self.root / cycle / "adapter" / cycle
        packet = json.loads((self.root / "controller-input.json").read_text())
        raw = _submitted(submission)
        sampled = json.loads((adapter_root / "raw-response.json").read_text())
        sampled["text"] = raw
        _write(adapter_root / "raw-response.json", sampled)
        (adapter_root / "raw-response.txt").write_text(raw)
        _write(adapter_root / "submission.json", submission)
        _write(adapter_root / "decision.json", decision)
        _write(adapter_root / "decision-provenance.json",
               controller_adapter._decision_provenance(
                   submission, decision, packet, cycle, raw))
        self.relink_fixture()

    def current_v6_lineage(self) -> tuple[dict, dict, Path]:
        receipt = json.loads(self.receipt.read_text())
        cycle = receipt["cycle_id"]
        adapter_root = self.root / cycle / "adapter" / cycle
        return (
            json.loads((adapter_root / "submission.json").read_text()),
            json.loads((adapter_root / "decision.json").read_text()),
            adapter_root,
        )

    def bind_v6_prior_record(self, record: dict) -> None:
        """Relink a v6 fixture to an adversarial stored prior record."""
        receipt = json.loads(self.receipt.read_text())
        cycle = receipt["cycle_id"]
        transaction = self.root / cycle
        _write(transaction / PRIOR_VERIFICATION_FILE, record)
        admission_path = transaction / "admission.json"
        admission = json.loads(admission_path.read_text())
        admission["prior_canary_sha256"] = record["receipt_sha256"]
        admission["prior_canary_verification_sha256"] = _digest(record)
        _write(admission_path, admission)
        global_path = self.root / "global-state/journal.jsonl"
        global_records = [json.loads(line) for line in
                          global_path.read_text().splitlines()]
        global_records[1]["payload"]["prior_canary_sha256"] = record[
            "receipt_sha256"]
        global_path.write_text("".join(
            json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n"
            for item in global_records))
        _rehash_generic_journal(global_path)
        self.relink_fixture()

    def upgrade_v6_fixture_to_first_canary_bootstrap(self) -> str:
        """Relink a receipt fixture to the typed first-canary proof."""
        self.upgrade_fixture_to_v6_scope_decision()
        receipt = json.loads(self.receipt.read_text())
        cycle = receipt["cycle_id"]
        transaction = self.root / cycle

        publication_path = transaction / "publication.json"
        publication = json.loads(publication_path.read_text())
        publication.update({
            "tag": REAL_TAG,
            "commit": REAL_COMMIT,
            "tag_object": REAL_TAG_OBJECT,
        })
        publication["source_hashes"] = protocol_source_release.source_hashes()
        source = _digest(publication["source_hashes"])
        publication["source_sha256"] = source
        _write(publication_path, publication)
        child_path = transaction / "result.json"
        child_result = json.loads(child_path.read_text())
        child_result["publication_sha256"] = _hash(publication_path)
        _write(child_path, child_result)

        bootstrap_path = self.root / FIRST_CANARY_BOOTSTRAP_FILE
        verified_publication = dict(publication)
        verified_publication["origin"] = PUBLISHED_ORIGIN
        with patch.object(
                protocol_source_release, "verify_published",
                return_value=verified_publication) as verify_published:
            publication_token = (
                parent_module.verified_first_canary_publication(
                    release_tag=REAL_TAG,
                    expected_source_sha256=source))
        verify_published.assert_called_once_with(
            tag=REAL_TAG, expected_source_sha256=source)
        _write(bootstrap_path, first_canary_bootstrap_document(
            publication=publication_token.value(),
            runtime_sha256=RUNTIME,
            child_entry=FIRST_CANARY_CHILD_ENTRY))
        bootstrap_record = verify_first_canary_bootstrap(
            bootstrap_path,
            expected_bootstrap_sha256=_hash(bootstrap_path),
            expected_source_sha256=source,
            expected_runtime_sha256=RUNTIME,
            expected_release_tag=REAL_TAG,
            expected_release_commit=REAL_COMMIT,
            expected_release_tag_object=REAL_TAG_OBJECT,
            expected_child_entry=FIRST_CANARY_CHILD_ENTRY)
        _write(transaction / PRIOR_VERIFICATION_FILE, bootstrap_record)

        admission_path = transaction / "admission.json"
        admission = json.loads(admission_path.read_text())
        admission["source_sha256"] = source
        admission["publication_sha256"] = _digest(publication)
        admission["prior_canary_sha256"] = bootstrap_record["bootstrap_sha256"]
        admission["prior_canary_verification_sha256"] = _digest(
            bootstrap_record)
        _write(admission_path, admission)

        global_path = self.root / "global-state/journal.jsonl"
        global_records = [json.loads(line) for line in
                          global_path.read_text().splitlines()]
        global_records[1]["payload"]["source_sha256"] = source
        global_records[1]["payload"]["prior_canary_sha256"] = (
            bootstrap_record["bootstrap_sha256"])
        global_path.write_text("".join(
            json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n"
            for item in global_records))
        _rehash_generic_journal(global_path)
        self.relink_fixture()
        self.rewrite_receipt(
            schema=BOOTSTRAP_CANARY_SCHEMA,
            first_canary_bootstrap_used=True)
        return source

    def test_exact_legacy_v5_unit_fixture_passes_and_is_deterministic(self):
        result = self.verify(
            expected_receipt_sha256=self.original_receipt_sha256)
        self.assertTrue(result["passed"])
        self.assertEqual(result["provider_calls"], 0)
        self.assertTrue(result["terminal_cleanup_verified"])
        self.assertGreaterEqual(len(result["evidence_sha256"]), 25)
        comparison_parent = Path(self.temporary.name).resolve() / "comparison"
        comparison_parent.mkdir()
        comparison_root = comparison_parent / FIXTURE_NAME
        comparison_identity = _build_legacy_v5_fixture(comparison_root)
        manifest = {
            str(path.relative_to(self.pristine_root)): _hash(path)
            for path in self.pristine_root.rglob("*") if path.is_file()
        }
        comparison_manifest = {
            str(path.relative_to(comparison_root)): _hash(path)
            for path in comparison_root.rglob("*") if path.is_file()
        }
        self.assertEqual(comparison_identity["receipt_sha256"],
                         self.original_receipt_sha256)
        self.assertEqual(comparison_manifest, manifest)
        historical_id = (
            "market-rsi-gate1-v0122-" +
            "production-cli-canary-20260923-02")
        for path in comparison_root.rglob("*"):
            if path.is_file():
                self.assertNotIn(historical_id.encode(), path.read_bytes())

    def test_exact_current_packet_v6_fixture_passes_and_has_no_task(self):
        self.upgrade_fixture_to_v6_scope_decision()
        result = self.verify()
        self.assertTrue(result["passed"])
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        adapter_root = self.root / cycle / "adapter" / cycle
        self.assertTrue((adapter_root / "decision-provenance.json").is_file())
        self.assertFalse((adapter_root / "task.json").exists())

    def test_bootstrap_shaped_v6_receipt_replays_exact_proof(self):
        source = self.upgrade_v6_fixture_to_first_canary_bootstrap()
        result = self.verify(
            expected_source_sha256=source,
            expected_release_tag=REAL_TAG,
            expected_release_commit=REAL_COMMIT,
            expected_release_tag_object=REAL_TAG_OBJECT,
            expected_receipt_sha256=_hash(self.receipt))
        self.assertTrue(result["passed"])
        self.assertEqual(result["provider_calls"], 0)
        self.assertEqual(result["actual_provider_cost_usd"], "0")
        self.assertIn(FIRST_CANARY_BOOTSTRAP_FILE,
                      result["evidence_sha256"])
        live_prior = live_entry.gate1_canary_receipt.verify_gate1_canary_receipt(
            self.receipt,
            expected_receipt_sha256=_hash(self.receipt),
            expected_source_sha256=source,
            expected_runtime_sha256=RUNTIME,
            expected_release_tag=REAL_TAG,
            expected_release_commit=REAL_COMMIT,
            expected_release_tag_object=REAL_TAG_OBJECT)
        self.assertEqual(live_prior, result)

    def test_bootstrap_receipt_rejects_mutated_child_source_binding(self):
        source = self.upgrade_v6_fixture_to_first_canary_bootstrap()
        publication_path = self.root / json.loads(
            self.receipt.read_text())["cycle_id"] / "publication.json"
        publication = json.loads(publication_path.read_text())
        publication["source_hashes"][
            FIRST_CANARY_CHILD_RELATIVE] = (
                "9" * 64)
        changed_source = _digest(publication["source_hashes"])
        publication["source_sha256"] = changed_source
        _write(publication_path, publication)
        # Rebinding the outer hashes cannot legitimize a child not named by
        # the bootstrap proof.
        admission_path = publication_path.with_name("admission.json")
        admission = json.loads(admission_path.read_text())
        admission["source_sha256"] = changed_source
        admission["publication_sha256"] = _digest(publication)
        _write(admission_path, admission)
        global_path = self.root / "global-state/journal.jsonl"
        records = [json.loads(line) for line in global_path.read_text().splitlines()]
        records[1]["payload"]["source_sha256"] = changed_source
        global_path.write_text("".join(
            json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n"
            for item in records))
        _rehash_generic_journal(global_path)
        child_path = publication_path.with_name("result.json")
        child_result = json.loads(child_path.read_text())
        child_result["publication_sha256"] = _hash(publication_path)
        _write(child_path, child_result)
        self.relink_fixture()
        with self.assertRaises(ValueError):
            self.verify(
                expected_source_sha256=changed_source,
                expected_release_tag=REAL_TAG,
                expected_release_commit=REAL_COMMIT,
                expected_release_tag_object=REAL_TAG_OBJECT,
                expected_receipt_sha256=_hash(self.receipt))

    def test_v6_changed_offline_token_ids_fail_when_fully_relinked(self):
        self.upgrade_fixture_to_v6_scope_decision()
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        adapter_root = self.root / cycle / "adapter" / cycle
        encoded_path = adapter_root / "encoded.json"
        encoded = json.loads(encoded_path.read_text())
        self.assertEqual(encoded["token_ids"],
                         list(controller_adapter.OFFLINE_FAKE_TOKEN_IDS))
        encoded["token_ids"][0] += 1
        _write(encoded_path, encoded)
        _write(self.root / cycle / "preencoded.json", encoded)
        self.relink_fixture()
        with self.assertRaisesRegex(ValueError, "decision lineage"):
            self.verify()

    def test_exponent_overflow_fails_when_admission_is_fully_relinked(self):
        admission_path = self.root / json.loads(
            self.receipt.read_text())["cycle_id"] / "admission.json"
        raw = admission_path.read_text()
        marker = '"provider_sample_max":1'
        self.assertEqual(raw.count(marker), 1)
        admission_path.write_text(raw.replace(
            marker, '"provider_sample_max":1e999'))
        self.relink_admission()
        with self.assertRaisesRegex(ValueError, "invalid admission JSON"):
            self.verify()

    def test_nested_nonfinite_fails_when_admission_is_fully_relinked(self):
        self.upgrade_fixture_to_v6_scope_decision()
        admission_path = self.root / json.loads(
            self.receipt.read_text())["cycle_id"] / "admission.json"
        raw = admission_path.read_text()
        marker = '"provider_sample_max":1'
        self.assertEqual(raw.count(marker), 1)
        admission_path.write_text(raw.replace(
            marker, '"provider_sample_max":[{"nested":{"value":1e999}}]'))
        self.relink_admission()
        with self.assertRaisesRegex(ValueError, "invalid admission JSON"):
            self.verify()

    def test_v5_rejects_v6_only_admission_member_when_fully_relinked(self):
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        admission_path = self.root / cycle / "admission.json"
        admission = json.loads(admission_path.read_text())
        admission["prior_canary_verification_sha256"] = "7" * 64
        _write(admission_path, admission)
        self.relink_admission()
        with self.assertRaisesRegex(ValueError, "invalid v5 admission fields"):
            self.verify()

    def test_v6_rejects_unknown_admission_member_when_fully_relinked(self):
        self.upgrade_fixture_to_v6_scope_decision()
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        admission_path = self.root / cycle / "admission.json"
        admission = json.loads(admission_path.read_text())
        admission["undeclared_extension"] = {"reviewed": False}
        _write(admission_path, admission)
        self.relink_admission()
        with self.assertRaisesRegex(ValueError, "invalid v6 admission fields"):
            self.verify()

    def test_v6_unregistered_source_response_pair_fails_when_fully_relinked(self):
        self.upgrade_fixture_to_v6_scope_decision()
        submission, decision, _ = self.current_v6_lineage()
        pair = {"source_registry_entry_id": "src_" + "z" * 26,
                "response_class_id": "rsp_" + "y" * 26}
        submission["scientific_source_response"] = copy.deepcopy(pair)
        decision["scientific_source_response"] = copy.deepcopy(pair)
        self.assertEqual(source_scope.validate_decision(decision), decision)
        self.rewrite_v6_lineage(submission, decision)
        with self.assertRaisesRegex(ValueError, "reviewed pair"):
            self.verify()

    def test_v6_wrong_split_and_cutoff_fail_when_fully_relinked(self):
        attacks = (
            ("split", "future_role_split", {
                "split_policy_id": "spl_" + "z" * 26,
                "split_policy_sha256": "9" * 64,
            }),
            ("cutoff", "horizon_cutoff", {
                "cutoff_semantics_id": "cut_" + "z" * 26,
                "cutoff_contract_sha256": "8" * 64,
            }),
        )
        for label, section, changes in attacks:
            with self.subTest(label=label):
                self.upgrade_fixture_to_v6_scope_decision()
                submission, decision, _ = self.current_v6_lineage()
                submission[section].update(changes)
                decision[section].update(changes)
                self.assertEqual(source_scope.validate_decision(decision), decision)
                self.rewrite_v6_lineage(submission, decision)
                with self.assertRaisesRegex(ValueError,
                                            "split policy|cutoff contract"):
                    self.verify()
                self.reset_fixture()

    def test_v6_raw_terminal_response_must_reparse_exactly(self):
        self.upgrade_fixture_to_v6_scope_decision()
        submission, decision, adapter_root = self.current_v6_lineage()
        raw_path = adapter_root / "raw-response.txt"
        changed = raw_path.read_text() + " trailing narrative"
        raw_path.write_text(changed)
        sampled = json.loads((adapter_root / "raw-response.json").read_text())
        sampled["text"] = changed
        _write(adapter_root / "raw-response.json", sampled)
        packet = json.loads((self.root / "controller-input.json").read_text())
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        _write(adapter_root / "decision-provenance.json",
               controller_adapter._decision_provenance(
                   submission, decision, packet, cycle, changed))
        self.relink_fixture()
        with self.assertRaisesRegex(ValueError, "final Controller output"):
            self.verify()

    def test_v6_expanded_decision_must_equal_current_adapter_reconstruction(self):
        self.upgrade_fixture_to_v6_scope_decision()
        submission, decision, adapter_root = self.current_v6_lineage()
        decision["bounded_investigation"]["max_documents_proposed"] = 2
        self.assertEqual(source_scope.validate_decision(decision), decision)
        _write(adapter_root / "decision.json", decision)
        packet = json.loads((self.root / "controller-input.json").read_text())
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        raw = (adapter_root / "raw-response.txt").read_text()
        _write(adapter_root / "decision-provenance.json",
               controller_adapter._decision_provenance(
                   submission, decision, packet, cycle, raw))
        self.relink_fixture()
        with self.assertRaisesRegex(ValueError, "decision lineage"):
            self.verify()

    def test_v6_full_provenance_must_be_reproduced(self):
        self.upgrade_fixture_to_v6_scope_decision()
        _, _, adapter_root = self.current_v6_lineage()
        path = adapter_root / "decision-provenance.json"
        provenance = json.loads(path.read_text())
        provenance["scope_options_sha256"] = "7" * 64
        _write(path, provenance)
        self.relink_fixture()
        with self.assertRaisesRegex(ValueError, "decision lineage"):
            self.verify()

    def test_v6_packet_must_be_exact_current_packet_even_when_relinked(self):
        self.upgrade_fixture_to_v6_scope_decision()
        packet_path = self.root / "controller-input.json"
        packet = json.loads(packet_path.read_text())
        packet["purpose"] += " changed"
        _write(packet_path, packet)
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        _write(self.root / cycle / "input.json", packet)
        self.relink_fixture()
        with self.assertRaisesRegex(ValueError,
                                    "exact frozen packet|exact current Controller packet"):
            self.verify()

    def test_v6_prior_receipt_chain_uses_admission_not_legacy_runner_hash(self):
        self.upgrade_fixture_to_v6_scope_decision()
        journal = self.root / "global-state" / "journal.jsonl"
        records = [json.loads(line) for line in journal.read_text().splitlines()]
        records[1]["payload"]["prior_canary_sha256"] = "d" * 64
        journal.write_text("".join(json.dumps(record, sort_keys=True,
                                             separators=(",", ":")) + "\n"
                                   for record in records))
        _rehash_generic_journal(journal)
        self.relink_fixture()
        with self.assertRaisesRegex(ValueError, "verified prior receipt"):
            self.verify()

    def test_v6_requires_prior_canary_verification_commitment(self):
        self.upgrade_fixture_to_v6_scope_decision()
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        admission_path = self.root / cycle / "admission.json"
        admission = json.loads(admission_path.read_text())
        admission.pop("prior_canary_verification_sha256")
        _write(admission_path, admission)
        self.relink_fixture()
        with self.assertRaisesRegex(ValueError, "invalid v6 admission fields"):
            self.verify()

    def test_v6_fully_relinked_arbitrary_prior_hash_and_record_fail(self):
        self.upgrade_fixture_to_v6_scope_decision()
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        record_path = self.root / cycle / PRIOR_VERIFICATION_FILE
        record = json.loads(record_path.read_text())
        record["receipt_sha256"] = "d" * 64
        record["evidence_sha256"] = {"fabricated.json": "e" * 64}
        self.bind_v6_prior_record(record)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.verify()

    def test_v6_missing_or_changed_prior_verification_record_fails(self):
        self.upgrade_fixture_to_v6_scope_decision()
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        record_path = self.root / cycle / PRIOR_VERIFICATION_FILE
        record_path.unlink()
        with self.assertRaisesRegex(ValueError, "missing persisted prior"):
            self.verify()

        self.reset_fixture()
        self.upgrade_fixture_to_v6_scope_decision()
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        record_path = self.root / cycle / PRIOR_VERIFICATION_FILE
        record = json.loads(record_path.read_text())
        record["evidence_sha256"] = {
            **record["evidence_sha256"], "invented.json": "f" * 64}
        self.bind_v6_prior_record(record)
        with self.assertRaisesRegex(ValueError, "independent replay"):
            self.verify()

    def test_v6_self_and_cross_prior_cycles_fail(self):
        self.upgrade_fixture_to_v6_scope_decision()
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        record_path = self.root / cycle / PRIOR_VERIFICATION_FILE
        record = json.loads(record_path.read_text())
        record["receipt_path"] = str(self.receipt)
        record["receipt_sha256"] = _hash(self.receipt)
        self.bind_v6_prior_record(record)
        with self.assertRaisesRegex(ValueError, "path cycle"):
            self.verify()

        self.reset_fixture()
        self.upgrade_fixture_to_v6_scope_decision()
        first_root, first_receipt = self.root, self.receipt
        cross_parent = Path(self.temporary.name).resolve() / "cross-evidence"
        cross_root = cross_parent / FIXTURE_NAME
        cross_parent.mkdir()
        shutil.copytree(first_root, cross_root)
        cross_receipt = cross_root / "canary-result.json"

        try:
            self.root, self.receipt = cross_root, cross_receipt
            cross_record_path = cross_root / cycle / PRIOR_VERIFICATION_FILE
            cross_record = json.loads(cross_record_path.read_text())
            cross_record["receipt_path"] = str(first_receipt)
            cross_record["receipt_sha256"] = _hash(first_receipt)
            self.bind_v6_prior_record(cross_record)
            cross_hash = _hash(cross_receipt)
        finally:
            self.root, self.receipt = first_root, first_receipt

        first_record = json.loads(
            (first_root / cycle / PRIOR_VERIFICATION_FILE).read_text())
        first_record["receipt_path"] = str(cross_receipt)
        first_record["receipt_sha256"] = cross_hash
        self.bind_v6_prior_record(first_record)
        with self.assertRaisesRegex(ValueError, "path cycle"):
            self.verify()

    def test_prior_chain_depth_is_bounded_before_evidence_recursion(self):
        with self.assertRaisesRegex(ValueError, "bounded depth"):
            _verify_gate1_canary_receipt(
                self.receipt,
                expected_receipt_sha256=self.original_receipt_sha256,
                expected_source_sha256=SOURCE,
                expected_runtime_sha256=RUNTIME,
                expected_release_tag=TAG,
                expected_release_commit=COMMIT,
                expected_release_tag_object=TAG_OBJECT,
                visited_receipts=frozenset(),
                depth=_MAX_PRIOR_CHAIN_DEPTH + 1,
            )

    def test_v6_internal_adapter_parent_symlink_is_rejected(self):
        self.upgrade_fixture_to_v6_scope_decision()
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        adapter_parent = self.root / cycle / "adapter"
        actual = self.root.parent / "actual-adapter-parent"
        adapter_parent.rename(actual)
        adapter_parent.symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "canonical|symlink"):
            self.verify()

    def test_bare_hash_or_inexact_path_is_never_enough(self):
        with self.assertRaisesRegex(ValueError, "absolute"):
            verify_gate1_canary_receipt(
                Path("canary-result.json"),
                expected_receipt_sha256=self.original_receipt_sha256,
                expected_source_sha256=SOURCE, expected_runtime_sha256=RUNTIME,
                expected_release_tag=TAG, expected_release_commit=COMMIT,
                expected_release_tag_object=TAG_OBJECT)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.verify(expected_receipt_sha256="0" * 64)
        renamed = self.root / "plausible-pass.json"
        self.receipt.rename(renamed)
        self.receipt = renamed
        with self.assertRaisesRegex(ValueError, "filename"):
            self.verify()

    def test_noncanonical_and_symlinked_ancestor_receipt_paths_fail(self):
        alias = self.root.parent / "evidence-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        arguments = {
            "expected_receipt_sha256": _hash(self.receipt),
            "expected_source_sha256": SOURCE,
            "expected_runtime_sha256": RUNTIME,
            "expected_release_tag": TAG,
            "expected_release_commit": COMMIT,
            "expected_release_tag_object": TAG_OBJECT,
        }
        with self.assertRaisesRegex(ValueError, "canonical"):
            verify_gate1_canary_receipt(alias / "canary-result.json", **arguments)
        noncanonical = (self.root / ".." / self.root.name /
                        "canary-result.json")
        with self.assertRaisesRegex(ValueError, "canonical"):
            verify_gate1_canary_receipt(noncanonical, **arguments)

    def test_receipt_symlink_is_rejected(self):
        actual = self.root / "actual.json"
        self.receipt.rename(actual)
        self.receipt.symlink_to(actual)
        with self.assertRaisesRegex(ValueError, "regular"):
            self.verify(expected_receipt_sha256=_hash(actual))

    def test_top_level_false_pass_or_authority_flags_fail(self):
        attacks = {
            "passed": False,
            "production_parent_used": False,
            "production_cli_arguments_used": False,
            "supervisor_claim_verified_by_child": False,
            "offline_provider_substituted": False,
            "provider_calls": 1,
            "actual_provider_cost_usd": "0.01",
            "public_fetch_performed": True,
            "formal_data_admitted": True,
            "review_only_without_catalog": False,
            "automatic_retry": True,
        }
        original = self.receipt.read_bytes()
        for field, value in attacks.items():
            with self.subTest(field=field):
                self.receipt.write_bytes(original)
                self.rewrite_receipt(**{field: value})
                with self.assertRaises(ValueError):
                    self.verify()

    def test_boolean_provider_count_and_unknown_member_fail(self):
        self.rewrite_receipt(provider_calls=False)
        with self.assertRaises(ValueError):
            self.verify()
        self.receipt.write_bytes(
            self.pristine_root.joinpath("canary-result.json").read_bytes())
        self.rewrite_receipt(unreviewed=True)
        with self.assertRaisesRegex(ValueError, "fields"):
            self.verify()

    def test_stale_source_runtime_and_release_commitments_fail(self):
        attacks = {
            "expected_source_sha256": "0" * 64,
            "expected_runtime_sha256": "0" * 64,
            "expected_release_tag": "market-rsi-protocol-v0.1.21",
            "expected_release_commit": "3" * 40,
            "expected_release_tag_object": "4" * 40,
        }
        for name, value in attacks.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.verify(**{name: value})

    def test_missing_or_mutated_linked_artifact_fails(self):
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        artifact = self.root / cycle / "adapter" / cycle / "raw-response.txt"
        artifact.write_text(artifact.read_text() + "tamper")
        with self.assertRaisesRegex(ValueError, "changed adapter artifact"):
            self.verify()
        artifact.unlink()
        with self.assertRaisesRegex(ValueError, "missing adapter artifact"):
            self.verify()

    def test_child_fetch_admission_retry_and_compiled_plan_fail_even_when_relinked(self):
        attacks = {
            "public_fetch_performed": True,
            "formal_data_admitted": True,
            "automatic_retry": True,
            "compiled_plan_sha256": "5" * 64,
            "execution_mode": "live",
            "provider_sample_max": 2,
        }
        original_root = Path(self.temporary.name) / "original"
        shutil.copytree(self.root, original_root)
        for field, value in attacks.items():
            with self.subTest(field=field):
                shutil.rmtree(self.root)
                shutil.copytree(original_root, self.root)
                self.receipt = self.root / "canary-result.json"
                self.relink_child(**{field: value})
                with self.assertRaises(ValueError):
                    self.verify()

    def test_adapter_provider_call_fails_even_when_parent_links_are_updated(self):
        canary = json.loads(self.receipt.read_text())
        cycle = canary["cycle_id"]
        adapter_path = self.root / cycle / "adapter" / cycle / "result.json"
        adapter = json.loads(adapter_path.read_text())
        adapter["provider_called"] = True
        _write(adapter_path, adapter)
        self.relink_child(adapter_result_sha256=_hash(adapter_path))
        with self.assertRaisesRegex(ValueError, "adapter result"):
            self.verify()

    def test_provider_receipt_and_budget_terminal_evidence_fail_closed(self):
        canary = json.loads(self.receipt.read_text())
        cycle = canary["cycle_id"]
        provider = self.root / cycle / "adapter" / cycle / "provider-receipt.json"
        value = json.loads(provider.read_text())
        value["provider_called"] = True
        _write(provider, value)
        with self.assertRaises(ValueError):
            self.verify()
        provider.write_bytes(self.pristine_root.joinpath(
            cycle, "adapter", cycle, "provider-receipt.json").read_bytes())
        journal = self.root / "budget" / "journal.jsonl"
        journal.write_text("\n".join(journal.read_text().splitlines()[:-1]) + "\n")
        with self.assertRaisesRegex(ValueError, "budget"):
            self.verify()

    def test_process_or_container_preflight_fails_when_relinked(self):
        canary = json.loads(self.receipt.read_text())
        cycle = canary["cycle_id"]
        path = self.root / cycle / "preflight.json"
        value = json.loads(path.read_text())
        value["matching_process_ids"] = [999]
        _write(path, value)
        self.relink_child(preflight_sha256=_hash(path))
        with self.assertRaisesRegex(ValueError, "preflight"):
            self.verify()

    def test_terminal_watchdog_snapshot_is_required(self):
        path = self.root / "supervisor" / "watchdog" / "snapshot.json"
        value = json.loads(path.read_text())
        value["active_task"] = {"task_id": "still-running"}
        _write(path, value)
        with self.assertRaisesRegex(ValueError, "not terminal"):
            self.verify()

    def test_one_material_watchdog_heartbeat_is_valid(self):
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        progress = "5" * 64
        records = self.watchdog_with_heartbeats([{
            "task_id": cycle,
            "material_progress": True,
            "progress_sha256": progress,
        }])
        self.relink_watchdog(records)
        result = self.verify()
        self.assertTrue(result["passed"])
        snapshot = json.loads((
            self.root / "supervisor/watchdog/snapshot.json").read_text())
        self.assertEqual(snapshot["seq"], 4)

    def test_multiple_mixed_watchdog_heartbeats_are_valid(self):
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        payloads = [
            {"task_id": cycle, "material_progress": False,
             "progress_sha256": None},
            {"task_id": cycle, "material_progress": True,
             "progress_sha256": "6" * 64},
            {"task_id": cycle, "material_progress": False,
             "progress_sha256": None},
            {"task_id": cycle, "material_progress": True,
             "progress_sha256": "7" * 64},
        ]
        records = self.watchdog_with_heartbeats(payloads)
        records = self.relink_watchdog(records)
        result = self.verify()
        self.assertTrue(result["passed"])
        snapshot = json.loads((
            self.root / "supervisor/watchdog/snapshot.json").read_text())
        self.assertEqual(snapshot["seq"], 7)
        self.assertEqual(snapshot["last_event_utc"], records[-1]["time_utc"])

    def test_watchdog_rejects_zero_extra_and_reordered_heartbeats(self):
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        valid_payload = {"task_id": cycle, "material_progress": False,
                         "progress_sha256": None}
        original_root = Path(self.temporary.name) / "watchdog-order-original"
        shutil.copytree(self.root, original_root)
        for attack in ("zero", "extra", "reordered"):
            with self.subTest(attack=attack):
                shutil.rmtree(self.root)
                shutil.copytree(original_root, self.root)
                self.receipt = self.root / "canary-result.json"
                records = self.watchdog_with_heartbeats([valid_payload])
                if attack == "zero":
                    records = [records[0], records[1], records[-1]]
                elif attack == "extra":
                    extra = copy.deepcopy(records[2])
                    extra["event"] = "data_gate"
                    records.insert(-1, extra)
                else:
                    records[1], records[2] = records[2], records[1]
                self.relink_watchdog(records)
                with self.assertRaisesRegex(ValueError, "event sequence"):
                    self.verify()

    def test_watchdog_rejects_wrong_task_types_progress_and_extra_fields(self):
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        attacks = (
            {"task_id": cycle + "-other", "material_progress": False,
             "progress_sha256": None},
            {"task_id": cycle, "material_progress": 1,
             "progress_sha256": None},
            {"task_id": cycle, "material_progress": True,
             "progress_sha256": None},
            {"task_id": cycle, "material_progress": True,
             "progress_sha256": "A" * 64},
            {"task_id": cycle, "material_progress": False,
             "progress_sha256": "8" * 64},
            {"task_id": cycle, "material_progress": False,
             "progress_sha256": None, "unreviewed": True},
        )
        original_root = Path(self.temporary.name) / "watchdog-payload-original"
        shutil.copytree(self.root, original_root)
        for payload in attacks:
            with self.subTest(payload=payload):
                shutil.rmtree(self.root)
                shutil.copytree(original_root, self.root)
                self.receipt = self.root / "canary-result.json"
                self.relink_watchdog(
                    self.watchdog_with_heartbeats([payload]))
                with self.assertRaisesRegex(ValueError, "watchdog"):
                    self.verify()

    def test_watchdog_rejects_bad_hash_chain(self):
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        records = self.watchdog_with_heartbeats([{
            "task_id": cycle, "material_progress": True,
            "progress_sha256": "9" * 64,
        }])
        self.relink_watchdog(records)
        path = self.root / "supervisor/watchdog/journal.jsonl"
        changed = [json.loads(line) for line in path.read_text().splitlines()]
        changed[2]["payload"]["progress_sha256"] = "a" * 64
        path.write_text("".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            for record in changed))
        with self.assertRaisesRegex(ValueError, "hash chain"):
            self.verify()

    def test_watchdog_rejects_bad_initialization_and_close_when_rehashed(self):
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        payload = {"task_id": cycle, "material_progress": False,
                   "progress_sha256": None}
        original_root = Path(self.temporary.name) / "watchdog-terminal-original"
        shutil.copytree(self.root, original_root)
        for attack in ("initialization", "close"):
            with self.subTest(attack=attack):
                shutil.rmtree(self.root)
                shutil.copytree(original_root, self.root)
                self.receipt = self.root / "canary-result.json"
                records = self.watchdog_with_heartbeats([payload])
                if attack == "initialization":
                    records[0]["payload"] = {"unreviewed": True}
                else:
                    records[-1]["payload"]["outcome"] = "failed"
                self.relink_watchdog(records)
                with self.assertRaisesRegex(ValueError, "watchdog"):
                    self.verify()

    def test_watchdog_snapshot_cardinality_and_last_event_are_exact(self):
        cycle = json.loads(self.receipt.read_text())["cycle_id"]
        payloads = [
            {"task_id": cycle, "material_progress": False,
             "progress_sha256": None},
            {"task_id": cycle, "material_progress": True,
             "progress_sha256": "b" * 64},
        ]
        self.relink_watchdog(self.watchdog_with_heartbeats(payloads))
        snapshot_path = self.root / "supervisor/watchdog/snapshot.json"
        original = json.loads(snapshot_path.read_text())
        for field, value in (("seq", 4),
                             ("last_event_utc", "2026-01-01T00:00:00Z")):
            with self.subTest(field=field):
                changed = dict(original)
                changed[field] = value
                _write(snapshot_path, changed)
                with self.assertRaisesRegex(ValueError, "not terminal"):
                    self.verify()
        _write(snapshot_path, original)
        self.assertTrue(self.verify()["passed"])

    def test_global_state_must_close_and_no_retry_can_be_appended(self):
        journal = self.root / "global-state" / "journal.jsonl"
        journal.write_text("\n".join(journal.read_text().splitlines()[:-1]) + "\n")
        with self.assertRaisesRegex(ValueError, "global-state"):
            self.verify()

    def test_duplicate_json_members_are_rejected(self):
        raw = self.receipt.read_text().rstrip()
        self.receipt.write_text(raw[:-1] + ',"passed":true}\n')
        with self.assertRaisesRegex(ValueError, "invalid canary receipt JSON"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
