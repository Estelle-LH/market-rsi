from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from market_rsi import digest
from supervisor_harness.build_p0_gate1_controller_packet import build
from supervisor_harness.p0_gate1_public_fetch import ADMISSION_SCHEMA
from supervisor_harness.p0_gate1_research_contract import (
    DECISION_SCHEMA, validate_and_compile,
)
from supervisor_harness.p0_gate1_watched_fetch import run
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


if __name__ == "__main__":
    unittest.main()
