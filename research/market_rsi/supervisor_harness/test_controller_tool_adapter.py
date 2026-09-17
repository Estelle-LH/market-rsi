"""Offline role/source tests; these do not assert a live E2B connection."""
from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace

from data_scientist_harness import fixtures
from data_scientist_harness.broker import Broker
from supervisor_harness.controller_tool_adapter import ControllerToolAdapter


class FakeBroker:
    def __init__(self):
        self.calls = []

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        return {"tool": name, "arguments": arguments, "status": "ok"}


class ControllerToolAdapterTests(unittest.TestCase):
    def setUp(self):
        self.broker = FakeBroker()
        self.adapter = ControllerToolAdapter(
            self.broker, controller_sandbox_id="controller-A",
            researcher_sandbox_id="researcher-B", input_sha256="a" * 64)
        self.controller = SimpleNamespace(sandbox_id="controller-A")
        self.researcher = SimpleNamespace(sandbox_id="researcher-B")
        self.request = {"schema": "controller_literature_tool_request_v1",
                        "input_sha256": "a" * 64, "call_id": "search-01",
                        "tool": "search_literature_live",
                        "arguments": {"query": "sports prediction calibration"}}

    def test_controller_query_reaches_existing_broker_and_marks_metadata(self):
        result = self.adapter.call_from_sandbox(self.controller, self.request)
        self.assertEqual(self.broker.calls, [(
            "search_literature_live", {"query": "sports prediction calibration"})])
        self.assertTrue(result["metadata_is_not_paper_read"])
        self.assertEqual(result["input_sha256"], "a" * 64)

    def test_researcher_or_guest_claimed_role_cannot_use_controller_tools(self):
        with self.assertRaises(ValueError):
            self.adapter.call_from_sandbox(self.researcher, self.request)
        with self.assertRaises(ValueError):
            self.adapter.call_from_sandbox(self.controller, {
                **self.request, "sandbox_id": "controller-A"})
        self.assertEqual(self.broker.calls, [])

    def test_wrong_input_and_unauthorized_tool_are_rejected_before_broker(self):
        for altered in ({**self.request, "input_sha256": "b" * 64},
                        {**self.request, "tool": "train_candidate"}):
            with self.assertRaises(ValueError):
                self.adapter.call_from_sandbox(self.controller, altered)
        self.assertEqual(self.broker.calls, [])

    def test_distinct_sandbox_ids_required(self):
        with self.assertRaises(ValueError):
            ControllerToolAdapter(self.broker, controller_sandbox_id="same",
                                  researcher_sandbox_id="same", input_sha256="a" * 64)

    def test_actual_broker_search_read_and_record_chain_is_reused(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "research"
            manifest_sha = fixtures.workspace(workspace, network=True)
            broker = Broker(workspace, manifest_sha, transport=fixtures.fake_transport)
            broker.call("inspect_harness", {})
            adapter = ControllerToolAdapter(
                broker, controller_sandbox_id="controller-A",
                researcher_sandbox_id="researcher-B", input_sha256="a" * 64)
            search = adapter.call_from_sandbox(self.controller, self.request)
            self.assertEqual(search["broker_record"]["read_level"], "metadata_only")
            read = adapter.call_from_sandbox(self.controller, {
                **self.request, "call_id": "read-01", "tool": "read_public_source",
                "arguments": {"url": "https://example.org/research", "offset": 0}})
            read_record = read["broker_record"]
            self.assertIn("text", read_record)
            recorded = adapter.call_from_sandbox(self.controller, {
                **self.request, "call_id": "record-01", "tool": "record_research",
                "arguments": {"layer": "evaluation", "question": "Can we calibrate?",
                              "read_records": [read_record["record_id"]],
                              "applicability": "Synthetic fixture only",
                              "limitations": "Not validated on market data",
                              "alternatives": "Ordinary baseline",
                              "proposed_test": "Compare on frozen Train rows"}})
            self.assertFalse(recorded["broker_record"]["applied_on_our_data"])
            self.assertEqual(len(broker.store.records("record_research")), 1)


if __name__ == "__main__":
    unittest.main()
