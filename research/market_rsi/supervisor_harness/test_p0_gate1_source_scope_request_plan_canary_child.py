"""Focused offline tests for the zero-effect D0 bridge canary child."""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import pwd
import tempfile
import unittest
from unittest.mock import patch

from market_rsi import canonical, digest, file_hash
from supervisor_harness.build_p0_gate1_controller_packet import build
from supervisor_harness import p0_gate1_source_scope_request_plan as bridge
from supervisor_harness import p0_gate1_source_scope_request_plan_canary_child as child


def _packet():
    return build(
        {"schema": "market_p0_gate0_verdict_v1",
         "metadata_inventory_passed": True,
         "2025_formal_final_admitted": False},
        {"schema": "market_controller_b_live_acceptance_v1", "passed": True,
         "claim_boundaries": {
             "bounded_live_transport_and_accounting_proven": True,
             "formal_admission": False,
             "prediction_improvement_proven": False}},
    )


def _provenance(decision, packet):
    return {
        "schema": "market_rsi_source_scope_field_provenance_v1",
        "cycle_id": bridge.D0_CYCLE_ID,
        "decision_id": bridge.D0_DECISION_ID,
        "controller_authored_objects": [
            "bounded_investigation", "future_role_split", "horizon_cutoff",
            "intended_uses", "scientific_source_response"],
        "trusted_protocol_fields": [
            "decision_id", "decision_status", "non_authority", "schema",
            "bounded_investigation.max_spend_usd_micros_proposed",
            "bounded_investigation.preserve_failures_without_retry_expansion",
            "bounded_investigation.stop_before_unregistered_response_class",
            "bounded_investigation.stop_on_first_rights_or_authority_unknown",
            "future_role_split.cross_role_reuse_policy",
            "future_role_split.unknown_exposure_policy",
            "horizon_cutoff.availability_cutoff_relation",
            "horizon_cutoff.availability_formula_id",
            "horizon_cutoff.provider_receiver_clocks_separate"],
        "submission_sha256": bridge.D0_SUBMISSION_SHA256,
        "decision_sha256": bridge.D0_DECISION_SHA256,
        "scope_options_sha256": bridge.FROZEN_SCOPE_OPTIONS_SHA256,
        "raw_controller_response_sha256": bridge.D0_RAW_RESPONSE_SHA256,
        "all_external_authority_false": True,
    }


def _write(path: Path, value) -> None:
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(canonical(value) + "\n")


def _fixture(root: Path):
    decision = deepcopy(bridge._EXPECTED_DECISION)
    packet = _packet()
    provenance = _provenance(decision, packet)
    review = {
        "schema": "market_p0_gate1_controller_review_v1",
        "cycle_id": bridge.D0_CYCLE_ID,
        "adapter_passed": True,
        "compiled_plan_sha256": None,
        "formal_data_admitted": False,
        "public_fetch_performed": False,
        "automatic_retry": False,
    }
    paths = {name: root / name for name in (
        "decision", "submission", "provenance", "raw_response", "packet",
        "publication", "result", "review")}
    paths["raw_response"] = root / "raw-response.txt"
    _write(paths["review"], review)
    result = {
        "schema": "market_p0_gate1_controller_outer_result_v1",
        "cycle_id": bridge.D0_CYCLE_ID,
        "passed": True,
        "submission_kind": "source_scope_decision",
        "compiled_plan_sha256": None,
        "formal_data_admitted": False,
        "public_fetch_performed": False,
        "automatic_retry": False,
        "review_sha256": file_hash(paths["review"]),
    }
    publication = {
        "schema": "market_rsi_protocol_publication_v1",
        "origin": child.PUBLISHED_ORIGIN,
        "tag": bridge.D0_RELEASE_TAG,
        "commit": bridge.D0_RELEASE_COMMIT,
        "tag_object": bridge.D0_RELEASE_TAG_OBJECT,
        "source_sha256": bridge.D0_CONTROLLED_SOURCE_SHA256,
    }
    values = {
        "decision": decision,
        "submission": bridge._controller_submission(decision),
        "provenance": provenance,
        "raw_response": b"fixture raw response\n",
        "packet": packet,
        "publication": publication,
        "result": result,
    }
    for name, value in values.items():
        _write(paths[name], value)
    hashes = {name: file_hash(path) for name, path in paths.items()}
    return paths, hashes


class RequestPlanCanaryChildTests(unittest.TestCase):
    def test_exact_fixture_compiles_twice_with_zero_effects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            paths, hashes = _fixture(root)
            artifacts = root / "artifacts"
            release = {"tag": child.RELEASE_TAG, "commit": "b" * 40,
                       "tag_object": "c" * 40, "source_sha256": "d" * 64}
            claim = {"release": release}
            args = argparse.Namespace(
                artifacts=artifacts, supervisor_claim=root / "claim.json",
                cycle_id=child.CANARY_ID, release_tag=child.RELEASE_TAG,
                release_commit="b" * 40, release_tag_object="c" * 40,
                source_sha256="d" * 64, runtime_sha256="e" * 64,
                **{"d0_" + name: path for name, path in paths.items()},
            )
            with patch.object(child, "D0_FILE_SHA256", hashes), patch.object(
                    child, "_verify_supervisor_claim",
                    return_value=(claim, "f" * 64)):
                result = child.run(args)
            self.assertTrue(result["passed"])
            self.assertEqual(result["provider_calls"], 0)
            self.assertEqual(result["network_requests"], 0)
            self.assertEqual(result["external_bytes_received"], 0)
            self.assertEqual(result["request_plan_canonical_sha256"],
                             child.REQUEST_PLAN_CANONICAL_SHA256)
            self.assertEqual(digest(child._parse_json(
                (artifacts / "request-plan-bundle.json").read_bytes(), "bundle")),
                child.REQUEST_BUNDLE_CANONICAL_SHA256)

    def test_mutated_d0_file_is_rejected_before_compile(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            paths, hashes = _fixture(root)
            paths["decision"].write_text("{}\n")
            args = argparse.Namespace(**{"d0_" + name: path
                                         for name, path in paths.items()})
            with patch.object(child, "D0_FILE_SHA256", hashes):
                with self.assertRaisesRegex(ValueError, "file commitment changed"):
                    child._verify_d0(args)

    def test_symlink_and_replaced_ancestor_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            real = root / "real"
            real.mkdir()
            target = real / "evidence.json"
            target.write_text("{}\n")
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "canonical|ancestor"):
                child._read_regular(alias / "evidence.json", "alias evidence")

            replacement = root / "replace"
            replacement.mkdir()
            replace_target = replacement / "evidence.json"
            replace_target.write_text("{}\n")
            original_read = os.read
            changed = False

            def replacing_read(fd, size):
                nonlocal changed
                if not changed:
                    changed = True
                    replacement.rename(root / "old-replace")
                    replacement.mkdir()
                    replace_target.write_text("{}\n")
                return original_read(fd, size)

            with patch("os.read", side_effect=replacing_read):
                with self.assertRaisesRegex(ValueError, "changed"):
                    child._read_regular(replace_target, "replaced evidence")

    def test_registered_packet_file_hash_is_the_durable_preflight_value(self):
        self.assertEqual(
            child.D0_FILE_SHA256["packet"],
            "bb15603ffd32c8b18b17339ce88aec15294862950d8dc8cb3036485716fe1acd",
        )
        path = (
            Path(pwd.getpwuid(os.geteuid()).pw_dir)
            / "Library/Application Support/MarketRSI/runs"
            / "market-rsi-v0125-gate1-first-current-source-20260928-01"
            / "controller-input.json"
        )
        if path.is_file():
            self.assertEqual(file_hash(path), child.D0_FILE_SHA256["packet"])

    def test_imports_exclude_fetch_provider_and_network_modules(self):
        tree = ast.parse(Path(child.__file__).read_text())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(item.name for item in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
        forbidden = ("public_fetch", "watched_fetch", "urllib", "requests",
                     "httpx", "socket", "codex_glm_provider", "paid_budget")
        self.assertFalse(any(any(token in name for token in forbidden)
                             for name in names))


if __name__ == "__main__":
    unittest.main()
