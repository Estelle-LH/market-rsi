import copy
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from market_rsi import digest
from supervisor_harness.build_p0_gate1_controller_packet import build
from supervisor_harness.p0_gate1_public_fetch import (
    ADMISSION_SCHEMA, UrlLibTransport, _response_header_map, fetch_snapshot,
)
from supervisor_harness.p0_gate1_research_contract import (
    DECISION_SCHEMA, validate_and_compile,
)


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def fetch(self, url, *, timeout_seconds, max_bytes):
        self.calls += 1
        self.request = (url, timeout_seconds, max_bytes)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class Gate1PublicFetchTests(unittest.TestCase):
    def setUp(self):
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
            "schema": DECISION_SCHEMA, "investigation_id": "gate1-fetch-001",
            "question_id": "research_use_rights",
            "source_id": "kalshi_official_historical_data",
            "hypothesis": "Official documentation describes the available historical objects.",
            "fixed_sample_rule": "Inspect the single frozen official documentation page.",
            "requested_operations": ["inspect_official_documentation"],
            "expected_evidence": "A bounded raw page hash and documented object list.",
            "max_requests": 1, "max_bytes": 10000, "max_minutes": 10,
            "max_provider_cost_usd": "0",
            "stop_rule": "Stop after one response or any redirect, error, timeout, or oversize body.",
        }
        self.task = validate_and_compile(decision, packet)
        self.admission = {"schema": ADMISSION_SCHEMA,
                          "task_sha256": digest(self.task),
                          "source_id": "kalshi_official_historical_data",
                          "fetch_authorized": True,
                          "max_bytes": 10000, "max_requests": 1}
        self.url = self.task["source"]["url"]

    def test_exact_public_snapshot_is_written(self):
        transport = FakeTransport({"status": 200, "final_url": self.url,
                                   "headers": {"Content-Type": "text/html; charset=utf-8",
                                               "Authorization": "must-not-be-recorded"},
                                   "body": b"official public documentation"})
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fresh"
            receipt = fetch_snapshot(self.task, self.admission, output, transport)
            self.assertEqual((output / "public-source.snapshot").read_bytes(),
                             b"official public documentation")
            self.assertNotIn("authorization", str(receipt).lower())
            self.assertFalse(receipt["b_network_access"])
            self.assertEqual(transport.calls, 1)

    def test_redirect_or_host_change_fails_without_artifact(self):
        transport = FakeTransport({"status": 200, "final_url": "https://example.com/",
                                   "headers": {"Content-Type": "text/html"},
                                   "body": b"wrong host"})
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fresh"
            with self.assertRaises(ValueError):
                fetch_snapshot(self.task, self.admission, output, transport)
            self.assertFalse(output.exists())

    def test_oversize_body_fails_without_artifact(self):
        transport = FakeTransport({"status": 200, "final_url": self.url,
                                   "headers": {"Content-Type": "text/html"},
                                   "body": b"x" * 10001})
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fresh"
            with self.assertRaises(ValueError):
                fetch_snapshot(self.task, self.admission, output, transport)
            self.assertFalse(output.exists())

    def test_task_or_admission_authority_change_fails_before_fetch(self):
        for changed_task, changed_admission in (
                ({**self.task, "source": {**self.task["source"],
                                           "url": "https://example.com"}}, self.admission),
                (self.task, {**self.admission, "max_requests": 2}),
                (self.task, {**self.admission, "task_sha256": "0" * 64})):
            transport = FakeTransport(RuntimeError("must not be called"))
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    fetch_snapshot(changed_task, changed_admission,
                                   Path(directory) / "fresh", transport)
            self.assertEqual(transport.calls, 0)

    def test_transport_failure_leaves_no_output(self):
        transport = FakeTransport(TimeoutError("bounded timeout"))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fresh"
            with self.assertRaises(TimeoutError):
                fetch_snapshot(self.task, self.admission, output, transport)
            self.assertFalse(output.exists())

    def test_url_transport_disables_ambient_proxies(self):
        class Response:
            status = 200
            headers = {"Content-Type": "text/html"}

            def geturl(self):
                return self_url

            def read(self, _limit):
                return b"official"

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class Opener:
            def open(self, _request, *, timeout):
                self.timeout = timeout
                return Response()

        self_url = self.url
        opener = Opener()
        with patch.object(
                urllib.request, "build_opener", return_value=opener) as build:
            response = UrlLibTransport().fetch(
                self.url, timeout_seconds=15, max_bytes=100)
        handlers = build.call_args.args
        self.assertIsInstance(handlers[0], urllib.request.ProxyHandler)
        self.assertEqual(handlers[0].proxies, {})
        self.assertEqual(response["body"], b"official")

    def test_duplicate_sensitive_headers_reject_before_dict_conversion(self):
        for items in (
                [("Content-Type", "text/html"),
                 ("content-type", "text/plain")],
                [("ETag", "one"), ("etag", "two")],
                [("Content-Encoding", "identity"),
                 ("content-encoding", "gzip")],
                [("Last-Modified", "one"),
                 ("last-modified", "two")]):
            with self.subTest(items=items):
                with self.assertRaisesRegex(ValueError, "duplicate"):
                    _response_header_map(items)

    def test_fake_mapping_cannot_bypass_duplicate_or_content_type_bound(self):
        responses = (
            {"status": 200, "final_url": self.url,
             "headers": {"Content-Type": "text/html",
                         "content-type": "text/plain"}, "body": b"x"},
            {"status": 200, "final_url": self.url,
             "headers": {"Content-Type": "text/html;" + "a" * 501},
             "body": b"x"},
        )
        for response in responses:
            transport = FakeTransport(response)
            with self.subTest(headers=response["headers"]), \
                    tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "fresh"
                with self.assertRaises(ValueError):
                    fetch_snapshot(
                        self.task, self.admission, output, transport)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
