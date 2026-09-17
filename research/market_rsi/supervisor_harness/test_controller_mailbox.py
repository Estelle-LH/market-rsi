"""Offline E2B-object-shaped integration; no live GLM, E2B, or paid calls."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from data_scientist_harness import fixtures
from data_scientist_harness.broker import Broker
from supervisor_harness.controller_mailbox import (
    ControllerMailbox, GUEST_INBOX, GUEST_OUTBOX, MAX_REQUEST_BYTES)
from supervisor_harness.controller_tool_adapter import ControllerToolAdapter
from supervisor_harness.global_state_gate import SupervisorGlobalState


class FakeFiles:
    def __init__(self):
        self.contents = {}

    def read(self, path):
        return self.contents[path]

    def write(self, path, content):
        self.contents[path] = content


class FakeSandbox:
    def __init__(self, sandbox_id):
        self.sandbox_id = sandbox_id
        self.files = FakeFiles()


class FakeState:
    def __init__(self):
        self.active_cycle = "cycle-01"

    def snapshot(self):
        return {"active_cycle": self.active_cycle}


class ControllerMailboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        workspace = self.root / "research"
        manifest_sha = fixtures.workspace(workspace, network=True)
        self.broker = Broker(workspace, manifest_sha, transport=fixtures.fake_transport)
        self.broker.call("inspect_harness", {})
        self.controller = FakeSandbox("controller-A")
        self.researcher = FakeSandbox("researcher-B")
        self.state = FakeState()
        self.adapter = ControllerToolAdapter(
            self.broker, controller_sandbox_id="controller-A",
            researcher_sandbox_id="researcher-B", input_sha256="a" * 64)

    def _mailbox(self, name="mailbox", **kwargs):
        return ControllerMailbox(
            controller_sandbox=self.controller, adapter=self.adapter,
            state=self.state, cycle_id="cycle-01",
            receipt_root=self.root / name, **kwargs)

    def _queue(self, index, call_id, tool, arguments):
        self.controller.files.write(f"{GUEST_OUTBOX}/{index:03d}.json", json.dumps({
            "schema": "controller_literature_tool_request_v1",
            "input_sha256": "a" * 64, "call_id": call_id,
            "tool": tool, "arguments": arguments}))

    def test_search_read_record_flow_stays_on_controller_and_host(self):
        mailbox = self._mailbox()
        self._queue(0, "search-01", "search_literature_live",
                    {"query": "sports forecast calibration"})
        search = mailbox.serve_next(0)
        self.assertTrue(search["metadata_is_not_paper_read"])
        self._queue(1, "read-01", "read_public_source",
                    {"url": "https://example.org/research", "offset": 0})
        read = mailbox.serve_next(1)
        self._queue(2, "record-01", "record_research", {
            "layer": "evaluation", "question": "Can this calibration transfer?",
            "read_records": [read["broker_record"]["record_id"]],
            "applicability": "Synthetic fixture only",
            "limitations": "Not validated on market data",
            "alternatives": "Ordinary baseline",
            "proposed_test": "Compare on frozen Train rows"})
        mailbox.serve_next(2)
        self.assertEqual(len(self.broker.store.records("record_research")), 1)
        self.assertEqual(self.researcher.files.contents, {})
        self.assertEqual(json.loads(self.controller.files.read(
            f"{GUEST_INBOX}/001.json")), read)
        self.assertTrue((self.root / "mailbox/002-delivery.json").is_file())

    def test_replay_and_out_of_order_are_not_served(self):
        mailbox = self._mailbox(max_calls=1)
        self._queue(0, "search-01", "search_literature_live", {"query": "calibration"})
        with self.assertRaises(ValueError):
            mailbox.serve_next(1)
        mailbox.serve_next(0)
        with self.assertRaises(ValueError):
            mailbox.serve_next(0)
        with self.assertRaises(ValueError):
            mailbox.serve_next(1)
        with self.assertRaises(FileExistsError):
            self._mailbox()

    def test_duplicate_call_id_at_new_index_is_terminal(self):
        mailbox = self._mailbox()
        self._queue(0, "search-01", "search_literature_live", {"query": "calibration"})
        mailbox.serve_next(0)
        self._queue(1, "search-01", "search_literature_live", {"query": "other query"})
        with self.assertRaises(ValueError):
            mailbox.serve_next(1)
        self.assertTrue((self.root / "mailbox/001-failure.json").is_file())

    def test_stale_global_state_blocks_before_broker(self):
        mailbox = self._mailbox()
        self._queue(0, "search-01", "search_literature_live", {"query": "calibration"})
        self.state.active_cycle = None
        with self.assertRaises(ValueError):
            mailbox.serve_next(0)
        self.assertFalse((self.root / "mailbox/000-claim.json").exists())

    def test_real_global_state_document_edit_is_rejected(self):
        document = self.root / "decision.md"
        document.write_text("frozen decisions\n")
        state = SupervisorGlobalState(self.root / "state", document)
        snapshot = state.initialize()
        state.claim("cycle-01", expected_head_sha256=snapshot["head_sha256"],
                    source_sha256="b" * 64, prior_canary_sha256="c" * 64)
        mailbox = ControllerMailbox(
            controller_sandbox=self.controller, adapter=self.adapter,
            state=state, cycle_id="cycle-01", receipt_root=self.root / "mailbox")
        self._queue(0, "search-01", "search_literature_live", {"query": "calibration"})
        document.write_text("changed without state revision\n")
        with self.assertRaises(ValueError):
            mailbox.serve_next(0)
        self.assertFalse((self.root / "mailbox/000-claim.json").exists())

    def test_oversized_request_fails_without_broker(self):
        mailbox = self._mailbox()
        self.controller.files.write(f"{GUEST_OUTBOX}/000.json", "x" * (MAX_REQUEST_BYTES + 1))
        with self.assertRaises(ValueError):
            mailbox.serve_next(0)
        self.assertEqual(mailbox.next_index, 0)
        self.assertTrue(mailbox.terminal)
        self.assertTrue((self.root / "mailbox/000-attempt.json").is_file())
        self.assertTrue((self.root / "mailbox/000-failure.json").is_file())
        self.assertFalse((self.root / "mailbox/000-claim.json").exists())

    def test_missing_guest_request_is_receipted_without_replay(self):
        mailbox = self._mailbox()
        with self.assertRaises(KeyError):
            mailbox.serve_next(0)
        self.assertTrue((self.root / "mailbox/000-failure.json").is_file())
        with self.assertRaises(ValueError):
            mailbox.serve_next(0)

    def test_broker_rejection_is_terminal_and_receipted(self):
        mailbox = self._mailbox()
        self._queue(0, "bad-01", "read_public_source",
                    {"url": "file:///private/data", "offset": 0})
        with self.assertRaises(Exception):
            mailbox.serve_next(0)
        self.assertTrue((self.root / "mailbox/000-claim.json").is_file())
        self.assertTrue((self.root / "mailbox/000-failure.json").is_file())
        with self.assertRaises(ValueError):
            mailbox.serve_next(0)
        self.assertEqual(self.researcher.files.contents, {})

    def test_researcher_cannot_be_substituted_as_controller(self):
        with self.assertRaises(ValueError):
            ControllerMailbox(
                controller_sandbox=self.researcher, adapter=self.adapter,
                state=self.state, cycle_id="cycle-01",
                receipt_root=self.root / "bad")


if __name__ == "__main__":
    unittest.main()
