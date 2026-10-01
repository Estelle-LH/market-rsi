"""Offline integration tests for the exact D0-to-document-fetch boundary."""
from __future__ import annotations

import ast
from copy import deepcopy
import inspect
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_rsi import digest
from supervisor_harness import p0_gate1_public_fetch as public_fetch
from supervisor_harness import p0_gate1_source_scope_fetch_adapter as adapter
from supervisor_harness import p0_gate1_source_scope_request_plan as bridge
from supervisor_harness import p0_gate1_source_scope_request_plan_canary_child as canary_child
from supervisor_harness import run_p0_gate1_source_scope_request_plan_canary as canary_parent
from supervisor_harness.test_p0_gate1_source_scope_request_plan import (
    _decision, _packet, _provenance,
)


def exact_pair(run_root: Path) -> tuple[dict, dict]:
    release_source = "a" * 64
    runtime = "b" * 64
    authorization = "c" * 64
    canary_receipt = "d" * 64
    canary_verification = "e" * 64
    task = {
        "schema": adapter.TASK_SCHEMA,
        "attempt_id": adapter.ATTEMPT_ID,
        "request_bundle_canonical_sha256": adapter.REQUEST_BUNDLE_SHA256,
        "request_plan_canonical_sha256": adapter.REQUEST_PLAN_SHA256,
        "authorization_file_sha256": authorization,
        "release": {"tag": adapter.RELEASE_TAG, "commit": "1" * 40,
                    "tag_object": "2" * 40,
                    "source_sha256": release_source},
        "runtime_sha256": runtime,
        "prior_canary_receipt_sha256": canary_receipt,
        "prior_canary_verification_sha256": canary_verification,
        "source": {"source_id": adapter.SOURCE_ID,
                   "url": adapter.DOCUMENT_URL,
                   "url_sha256": adapter.DOCUMENT_URL_SHA256},
        "request": {"method": "GET", "query_parameters": [], "body": None,
                    "transport_headers": dict(adapter.REQUEST_HEADERS)},
        "bounds": {"max_requests": adapter.MAX_REQUESTS,
                   "max_response_bytes": adapter.MAX_RESPONSE_BYTES,
                   "max_elapsed_seconds": adapter.MAX_ELAPSED_SECONDS,
                   "transport_timeout_seconds":
                       adapter.TRANSPORT_TIMEOUT_SECONDS,
                   "provider_cost_usd": "0"},
        "policy": {"redirects_allowed": False,
                   "automatic_retries_allowed": False,
                   "alternate_url_allowed": False,
                   "credential_use_allowed": False,
                   "purchase_allowed": False,
                   "source_write_allowed": False},
        "authority": {"network_fetch_authorized": True,
                      "snapshot_retention_authorized": True,
                      "formal_data_admission_authorized": False,
                      "train_dev_final_access_authorized": False,
                      "training_evaluation_authorized": False,
                      "snapshot_redistribution_authorized": False,
                      "prediction_claim_authorized": False},
        "output_root": str(run_root),
    }
    admission = {
        "schema": adapter.ADMISSION_SCHEMA,
        "attempt_id": adapter.ATTEMPT_ID,
        "task_canonical_sha256": digest(task),
        "request_bundle_canonical_sha256": adapter.REQUEST_BUNDLE_SHA256,
        "request_plan_canonical_sha256": adapter.REQUEST_PLAN_SHA256,
        "authorization_file_sha256": authorization,
        "release_source_sha256": release_source,
        "runtime_sha256": runtime,
        "prior_canary_receipt_sha256": canary_receipt,
        "prior_canary_verification_sha256": canary_verification,
        "source_id": adapter.SOURCE_ID,
        "url_sha256": adapter.DOCUMENT_URL_SHA256,
        "fetch_authorized": True,
        "snapshot_retention_authorized": True,
        "max_requests": adapter.MAX_REQUESTS,
        "max_response_bytes": adapter.MAX_RESPONSE_BYTES,
    }
    return task, admission


class SourceScopeFetchIntegrationTests(unittest.TestCase):
    def test_actual_reviewed_d0_compiles_twice_to_exact_bundle(self):
        packet = _packet()
        decision = _decision()
        provenance = _provenance(decision, packet)
        values = {
            "decision": decision, "decision_provenance": provenance,
            "packet": packet,
            "d0_source_sha256": bridge.D0_CONTROLLED_SOURCE_SHA256,
        }
        first = bridge.compile_document_request_plan(**values)
        second = bridge.compile_document_request_plan(**values)
        self.assertEqual(first, second)
        self.assertEqual(digest(first), adapter.REQUEST_BUNDLE_SHA256)
        self.assertEqual(first["request_plan_canonical_sha256"],
                         adapter.REQUEST_PLAN_SHA256)

    def test_exact_pair_performs_one_fake_call_and_writes_exact_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "run"
            run_root.mkdir()
            task, admission = exact_pair(run_root)
            response = {
                "status": 200, "final_url": adapter.DOCUMENT_URL,
                "headers": {"Content-Type": "text/html; charset=utf-8",
                            "Content-Encoding": "identity",
                            "ETag": "fixture"},
                "body": b"official documentation",
            }
            with patch.object(adapter, "RUN_ROOT", run_root), patch.object(
                    public_fetch.UrlLibTransport, "fetch",
                    return_value=response) as fetch:
                receipt = public_fetch.fetch_source_scope_snapshot(
                    task, admission, run_root / "snapshot")
            fetch.assert_called_once_with(
                adapter.DOCUMENT_URL,
                timeout_seconds=adapter.TRANSPORT_TIMEOUT_SECONDS,
                max_bytes=adapter.MAX_RESPONSE_BYTES)
            self.assertEqual(receipt["final_url"], adapter.DOCUMENT_URL)
            self.assertIsNone(receipt["content_encoding"])
            self.assertEqual(receipt["requests_made"], 1)
            self.assertEqual(receipt["automatic_retries"], 0)
            self.assertEqual(
                (run_root / "snapshot/public-source.snapshot").read_bytes(),
                b"official documentation")

    def test_cross_schema_and_authority_mutations_fail_before_transport(self):
        mutations = []
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for index in range(4):
                run_root = base / f"run-{index}"
                run_root.mkdir()
                task, admission = exact_pair(run_root)
                if index == 0:
                    task = {"schema": "market_p0_gate1_research_task_v1"}
                elif index == 1:
                    admission["schema"] = "market_p0_gate1_fetch_admission_v1"
                elif index == 2:
                    task["authority"]["prediction_claim_authorized"] = True
                    admission["task_canonical_sha256"] = digest(task)
                else:
                    admission["snapshot_retention_authorized"] = False
                mutations.append((run_root, task, admission))
            for run_root, task, admission in mutations:
                with self.subTest(run_root=run_root), patch.object(
                        adapter, "RUN_ROOT", run_root), patch.object(
                        public_fetch.UrlLibTransport, "fetch") as fetch:
                    with self.assertRaises(ValueError):
                        public_fetch.fetch_source_scope_snapshot(
                            task, admission, run_root / "snapshot")
                    fetch.assert_not_called()

    def test_redirect_encoding_and_oversize_reject_without_success_receipt(self):
        responses = (
            {"status": 200, "final_url": "https://example.invalid/",
             "headers": {"Content-Type": "text/html"}, "body": b"x"},
            {"status": 200, "final_url": adapter.DOCUMENT_URL,
             "headers": {"Content-Type": "text/html",
                         "Content-Encoding": "gzip"}, "body": b"x"},
            {"status": 200, "final_url": adapter.DOCUMENT_URL,
             "headers": {"Content-Type": "text/html"},
             "body": b"x" * (adapter.MAX_RESPONSE_BYTES + 1)},
            {"status": 200, "final_url": adapter.DOCUMENT_URL,
             "headers": {"Content-Type": "text/html",
                         "content-type": "text/plain"}, "body": b"x"},
            {"status": 200, "final_url": adapter.DOCUMENT_URL,
             "headers": {"Content-Type": "text/html;" + "a" * 501},
             "body": b"x"},
        )
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for index, response in enumerate(responses):
                run_root = base / f"run-{index}"
                run_root.mkdir()
                task, admission = exact_pair(run_root)
                with self.subTest(index=index), patch.object(
                        adapter, "RUN_ROOT", run_root), patch.object(
                        public_fetch.UrlLibTransport, "fetch",
                        return_value=response):
                    with self.assertRaises(ValueError):
                        public_fetch.fetch_source_scope_snapshot(
                            task, admission, run_root / "snapshot")
                self.assertFalse((run_root / "snapshot/receipt.json").exists())

    def test_bridge_canary_imports_no_fetch_or_network_module(self):
        forbidden = {"urllib", "requests", "http", "socket",
                     "p0_gate1_public_fetch", "p0_gate1_watched_fetch"}
        for module in (canary_child, canary_parent):
            tree = ast.parse(inspect.getsource(module))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[-1]
                                    for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[-1])
            self.assertTrue(forbidden.isdisjoint(imported),
                            forbidden & imported)


if __name__ == "__main__":
    unittest.main()
