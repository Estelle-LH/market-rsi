from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_rsi import canonical, digest
from supervisor_harness.build_p0_gate1_controller_packet import build
from supervisor_harness.p0_gate1_public_fetch import ADMISSION_SCHEMA
from supervisor_harness import p0_gate1_source_scope_fetch_adapter as scope_adapter
from supervisor_harness import p0_gate1_watched_fetch as watched_module
from supervisor_harness.p0_gate1_research_contract import (
    DECISION_SCHEMA, validate_and_compile,
)
from supervisor_harness.p0_gate1_watched_fetch import run, run_preclaimed
from supervisor_harness.supervisor_watchdog import SupervisorWatchdog


class FakeTransport:
    def __init__(self, response):
        self.response = response

    def fetch(self, url, *, timeout_seconds, max_bytes):
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class Clock:
    def __init__(self):
        self.value = datetime(2026, 9, 20, 1, 0, tzinfo=timezone.utc)

    def __call__(self):
        value = self.value
        self.value += timedelta(seconds=1)
        return value


class WatchedGate1FetchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.watchdog = SupervisorWatchdog(root / "watchdog")
        self.clock = Clock()
        self.watchdog.initialize(now=self.clock())
        gate0 = {"schema": "market_p0_gate0_verdict_v1",
                 "metadata_inventory_passed": True,
                 "2025_formal_final_admitted": False}
        live = {"schema": "market_controller_b_live_acceptance_v1", "passed": True,
                "claim_boundaries": {
                    "bounded_live_transport_and_accounting_proven": True,
                    "formal_admission": False,
                    "prediction_improvement_proven": False}}
        packet = build(gate0, live)
        decision = {
            "schema": DECISION_SCHEMA, "investigation_id": "watched-fetch-001",
            "question_id": "research_use_rights",
            "source_id": "kalshi_official_historical_data",
            "hypothesis": "Official documentation describes historical objects.",
            "fixed_sample_rule": "Inspect the one frozen official documentation page.",
            "requested_operations": ["inspect_official_documentation"],
            "expected_evidence": "Raw bytes, response metadata, and a snapshot hash.",
            "max_requests": 1, "max_bytes": 10000, "max_minutes": 10,
            "max_provider_cost_usd": "0",
            "stop_rule": "Stop after one response or any redirect, error, or timeout.",
        }
        self.task = validate_and_compile(decision, packet)
        self.admission = {"schema": ADMISSION_SCHEMA,
                          "task_sha256": digest(self.task),
                          "source_id": "kalshi_official_historical_data",
                          "fetch_authorized": True,
                          "max_bytes": 10000, "max_requests": 1}
        self.output = root / "snapshot"

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, transport):
        return run(watchdog=self.watchdog, task_id="gate1-fetch-task-001",
                   task=self.task, admission=self.admission,
                   output=self.output, transport=transport, pid=1234,
                   process_command_sha256="5" * 64,
                   budget_snapshot_sha256="6" * 64, clock=self.clock)

    def test_success_records_progress_and_terminal_close(self):
        url = self.task["source"]["url"]
        receipt = self.call(FakeTransport(
            {"status": 200, "final_url": url,
             "headers": {"Content-Type": "text/html"}, "body": b"official"}))
        state = self.watchdog.snapshot()
        self.assertEqual(receipt["requests_made"], 1)
        self.assertIsNone(state["active_task"])
        self.assertEqual(state["incidents"], [])

    def test_timeout_becomes_worker_incident_and_never_success(self):
        with self.assertRaises(TimeoutError):
            self.call(FakeTransport(TimeoutError("fixed timeout")))
        state = self.watchdog.snapshot()
        self.assertEqual(state["active_task"]["status"], "repair_pending")
        self.assertEqual(state["incidents"][0]["classification"], "worker_error")
        self.assertFalse(self.output.exists())

    def test_bad_response_becomes_malformed_data_incident(self):
        url = self.task["source"]["url"]
        with self.assertRaises(ValueError):
            self.call(FakeTransport(
                {"status": 200, "final_url": url,
                 "headers": {"Content-Type": "application/octet-stream"},
                 "body": b"bad"}))
        state = self.watchdog.snapshot()
        self.assertEqual(state["incidents"][0]["classification"], "malformed_data")

    def source_scope_pair(self):
        run_root = Path(self.tmp.name) / "source-scope-run"
        release_source = "a" * 64
        runtime = "b" * 64
        authorization = "c" * 64
        canary_receipt = "d" * 64
        canary_verification = "e" * 64
        task = {
            "schema": scope_adapter.TASK_SCHEMA,
            "attempt_id": scope_adapter.ATTEMPT_ID,
            "request_bundle_canonical_sha256":
                scope_adapter.REQUEST_BUNDLE_SHA256,
            "request_plan_canonical_sha256":
                scope_adapter.REQUEST_PLAN_SHA256,
            "authorization_file_sha256": authorization,
            "release": {"tag": scope_adapter.RELEASE_TAG,
                        "commit": "1" * 40, "tag_object": "2" * 40,
                        "source_sha256": release_source},
            "runtime_sha256": runtime,
            "prior_canary_receipt_sha256": canary_receipt,
            "prior_canary_verification_sha256": canary_verification,
            "source": {"source_id": scope_adapter.SOURCE_ID,
                       "url": scope_adapter.DOCUMENT_URL,
                       "url_sha256": scope_adapter.DOCUMENT_URL_SHA256},
            "request": {"method": "GET", "query_parameters": [],
                        "body": None,
                        "transport_headers": dict(
                            scope_adapter.REQUEST_HEADERS)},
            "bounds": {"max_requests": 1,
                       "max_response_bytes":
                           scope_adapter.MAX_RESPONSE_BYTES,
                       "max_elapsed_seconds":
                           scope_adapter.MAX_ELAPSED_SECONDS,
                       "transport_timeout_seconds":
                           scope_adapter.TRANSPORT_TIMEOUT_SECONDS,
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
            "schema": scope_adapter.ADMISSION_SCHEMA,
            "attempt_id": scope_adapter.ATTEMPT_ID,
            "task_canonical_sha256": digest(task),
            "request_bundle_canonical_sha256":
                scope_adapter.REQUEST_BUNDLE_SHA256,
            "request_plan_canonical_sha256":
                scope_adapter.REQUEST_PLAN_SHA256,
            "authorization_file_sha256": authorization,
            "release_source_sha256": release_source,
            "runtime_sha256": runtime,
            "prior_canary_receipt_sha256": canary_receipt,
            "prior_canary_verification_sha256": canary_verification,
            "source_id": scope_adapter.SOURCE_ID,
            "url_sha256": scope_adapter.DOCUMENT_URL_SHA256,
            "fetch_authorized": True,
            "snapshot_retention_authorized": True,
            "max_requests": 1,
            "max_response_bytes": scope_adapter.MAX_RESPONSE_BYTES,
        }
        return run_root, task, admission

    def claim_source_scope(self, task, admission):
        self.watchdog.claim_task(
            task_id=scope_adapter.ATTEMPT_ID + "-watched-fetch",
            task_kind="research", stage="gate1_source_scope_fetch",
            owner="trusted_broker", heartbeat_timeout_seconds=20,
            progress_timeout_seconds=30,
            input_sha256=digest({"task": task, "admission": admission}),
            process_identity={"pid": 4321, "command_sha256": "5" * 64},
            container_identity=None, now=self.clock())

    @staticmethod
    def fake_source_scope_fetch(_task, _admission, output):
        output.mkdir()
        (output / "public-source.snapshot").write_bytes(b"official")
        receipt = {"fixture": "exact"}
        (output / "receipt.json").write_text(canonical(receipt) + "\n")
        return receipt

    def test_preclaimed_records_two_progress_events_and_does_not_close(self):
        run_root, task, admission = self.source_scope_pair()
        run_root.mkdir()
        self.claim_source_scope(task, admission)
        with patch.object(scope_adapter, "RUN_ROOT", run_root), patch.object(
                watched_module, "fetch_source_scope_snapshot",
                side_effect=self.fake_source_scope_fetch):
            receipt = run_preclaimed(
                watchdog=self.watchdog,
                task_id=scope_adapter.ATTEMPT_ID + "-watched-fetch",
                task=task, admission=admission, output=run_root / "snapshot",
                pid=4321, process_command_sha256="5" * 64,
                budget_snapshot_sha256="6" * 64,
                receipt_validator=lambda value, _path: value,
                clock=self.clock)
        active = self.watchdog.snapshot()["active_task"]
        self.assertEqual(receipt, {"fixture": "exact"})
        self.assertEqual(active["progress_seq"], 2)
        self.assertEqual(active["status"], "active")

    def test_preclaimed_failure_reports_one_incident_and_never_closes(self):
        run_root, task, admission = self.source_scope_pair()
        run_root.mkdir()
        self.claim_source_scope(task, admission)
        with patch.object(scope_adapter, "RUN_ROOT", run_root), patch.object(
                watched_module, "fetch_source_scope_snapshot",
                side_effect=TimeoutError("fixed timeout")):
            with self.assertRaises(TimeoutError):
                run_preclaimed(
                    watchdog=self.watchdog,
                    task_id=scope_adapter.ATTEMPT_ID + "-watched-fetch",
                    task=task, admission=admission,
                    output=run_root / "snapshot", pid=4321,
                    process_command_sha256="5" * 64,
                    budget_snapshot_sha256="6" * 64,
                    receipt_validator=lambda value, _path: value,
                    clock=self.clock)
        state = self.watchdog.snapshot()
        self.assertEqual(len(state["incidents"]), 1)
        self.assertEqual(state["active_task"]["status"], "repair_pending")

    def test_preclaimed_missing_claim_fails_before_fetch(self):
        run_root, task, admission = self.source_scope_pair()
        run_root.mkdir()
        with patch.object(scope_adapter, "RUN_ROOT", run_root), patch.object(
                watched_module, "fetch_source_scope_snapshot") as fetch:
            with self.assertRaisesRegex(ValueError, "active parent"):
                run_preclaimed(
                    watchdog=self.watchdog,
                    task_id=scope_adapter.ATTEMPT_ID + "-watched-fetch",
                    task=task, admission=admission,
                    output=run_root / "snapshot", pid=4321,
                    process_command_sha256="5" * 64,
                    budget_snapshot_sha256="6" * 64,
                    receipt_validator=lambda value, _path: value,
                    clock=self.clock)
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
