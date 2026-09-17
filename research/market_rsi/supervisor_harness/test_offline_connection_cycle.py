"""Whole host-mediated connection with fakes; not GLM or E2B evidence."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from data_scientist_harness import fixtures
from data_scientist_harness.broker import Broker
from market_rsi import digest, file_hash
from supervisor_harness.broker_handoff import A_DECISION, A_FEEDBACK, B_ORDER, B_RESULT, BrokerHandoff
from supervisor_harness.controller_mailbox import ControllerMailbox, GUEST_OUTBOX
from supervisor_harness.controller_tool_adapter import ControllerToolAdapter
from supervisor_harness.global_state_gate import SupervisorGlobalState
from supervisor_harness import researcher_guest_worker


class Files:
    def __init__(self):
        self.contents = {}

    def read(self, path):
        return self.contents[path]

    def write(self, path, content):
        self.contents[path] = content


class Sandbox:
    def __init__(self, sandbox_id):
        self.sandbox_id = sandbox_id
        self.files = Files()


class OfflineConnectionCycleTests(unittest.TestCase):
    def test_same_a_and_b_are_bound_through_tools_order_and_feedback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            doc = root / "decision.md"
            doc.write_text("frozen supervisor packet\n")
            state = SupervisorGlobalState(root / "state", doc)
            snapshot = state.initialize()
            state.claim("cycle-01", expected_head_sha256=snapshot["head_sha256"],
                        source_sha256="b" * 64, prior_canary_sha256="c" * 64)
            workspace = root / "research-workspace"
            manifest_sha = fixtures.workspace(workspace, network=True)
            broker = Broker(workspace, manifest_sha, transport=fixtures.fake_transport)
            broker.call("inspect_harness", {})
            a, b = Sandbox("controller-A"), Sandbox("researcher-B")
            adapter = ControllerToolAdapter(
                broker, controller_sandbox_id=a.sandbox_id,
                researcher_sandbox_id=b.sandbox_id, input_sha256="a" * 64)
            mailbox = ControllerMailbox(
                controller_sandbox=a, adapter=adapter, state=state,
                cycle_id="cycle-01", receipt_root=root / "mailbox")

            def tool(index, call_id, name, arguments):
                a.files.write(f"{GUEST_OUTBOX}/{index:03d}.json", json.dumps({
                    "schema": "controller_literature_tool_request_v1",
                    "input_sha256": "a" * 64, "call_id": call_id,
                    "tool": name, "arguments": arguments}))
                return mailbox.serve_next(index)

            search = tool(0, "search-01", "search_literature_live",
                          {"query": "sports prediction calibration"})
            self.assertTrue(search["metadata_is_not_paper_read"])
            read = tool(1, "read-01", "read_public_source",
                        {"url": "https://example.org/research", "offset": 0})
            read_id = read["broker_record"]["record_id"]
            tool(2, "record-01", "record_research", {
                "layer": "evaluation", "question": "Can this transfer?",
                "read_records": [read_id], "applicability": "Synthetic fixture only",
                "limitations": "No market validation", "alternatives": "Ordinary model",
                "proposed_test": "Compare on opened Train before Dev"})

            handoff = BrokerHandoff(
                controller_sandbox=a, researcher_sandbox=b, state=state,
                cycle_id="cycle-01", input_sha256="a" * 64,
                receipt_root=root / "handoff")
            decision = {"schema": "market_research_decision_v1",
                        "cycle_id": "cycle-01", "input_sha256": "a" * 64,
                        "task_id": "hash-public-canary", "task_type": "code_canary",
                        "data_role": "synthetic_fixture",
                        "question": f"Can B hash a public record of read {read_id}?",
                        "hypothesis": "B's output matches host SHA256.",
                        "expected_evidence": "Bound B output and host review.",
                        "stop_rule": "One synthetic try, no retry.",
                        "max_seconds": 20, "cost_bound_usd": "0",
                        "public_text": f"read receipt {read_id}"}
            a.files.write(A_DECISION, json.dumps(decision))
            order = handoff.freeze_and_deliver()
            self.assertEqual(json.loads(b.files.read(B_ORDER)), order)
            guest_dir = root / "synthetic-researcher-guest"
            guest_dir.mkdir()
            guest_order, guest_result = guest_dir / "order.json", guest_dir / "result.json"
            guest_order.write_text(b.files.read(B_ORDER))
            worker = subprocess.run([
                sys.executable, "-I", str(Path(researcher_guest_worker.__file__).resolve()),
                "--order", str(guest_order), "--result", str(guest_result)],
                capture_output=True, text=True, timeout=5, check=False)
            self.assertEqual(worker.returncode, 0, worker.stderr)
            b.files.write(B_RESULT, guest_result.read_text())
            result = handoff.receive_result()
            review = {"schema": "market_broker_independent_review_v1",
                      "cycle_id": "cycle-01", "result_sha256": digest(result),
                      "verdict": "accept", "reason": "Host recomputed the public hash.",
                      "protected_data_opened": False}
            feedback = handoff.deliver_reviewed_feedback(review)
            self.assertEqual(json.loads(a.files.read(A_FEEDBACK)), feedback)
            self.assertNotIn(A_FEEDBACK, b.files.contents)
            self.assertEqual(len(broker.store.records("record_research")), 1)
            state.close("cycle-01", outcome="passed",
                        review_sha256=file_hash(root / "handoff/review.json"))
            self.assertIsNone(state.snapshot()["active_cycle"])


if __name__ == "__main__":
    unittest.main()
