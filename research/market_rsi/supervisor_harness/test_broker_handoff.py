"""Zero-cost, object-shaped handoff tests; no real E2B or GLM calls."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from market_rsi import digest
from supervisor_harness.broker_handoff import (
    A_DECISION, A_FEEDBACK, B_ORDER, B_RESULT, BrokerHandoff)
from supervisor_harness.global_state_gate import SupervisorGlobalState


class Files:
    def __init__(self):
        self.contents = {}

    def read(self, path):
        return self.contents[path]

    def write(self, path, value):
        self.contents[path] = value


class Sandbox:
    def __init__(self, sandbox_id):
        self.sandbox_id = sandbox_id
        self.files = Files()


class BrokerHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        document = self.root / "decision.md"
        document.write_text("frozen supervisor decision\n")
        self.state = SupervisorGlobalState(self.root / "state", document)
        snapshot = self.state.initialize()
        self.state.claim("cycle-01", expected_head_sha256=snapshot["head_sha256"],
                         source_sha256="b" * 64, prior_canary_sha256="c" * 64)
        self.controller, self.researcher = Sandbox("controller-A"), Sandbox("researcher-B")
        self.handoff = BrokerHandoff(
            controller_sandbox=self.controller,
            researcher_sandbox=self.researcher, state=self.state,
            cycle_id="cycle-01", input_sha256="a" * 64,
            receipt_root=self.root / "handoff")
        self.decision = {
            "schema": "market_research_decision_v1", "cycle_id": "cycle-01",
            "input_sha256": "a" * 64, "task_id": "hash-public-canary",
            "task_type": "code_canary", "data_role": "synthetic_fixture",
            "question": "Can B hash this public string?",
            "hypothesis": "Its SHA256 equals the host's SHA256.",
            "expected_evidence": "Bound B result and host comparison.",
            "stop_rule": "One attempt, no retry.", "max_seconds": 20,
            "cost_bound_usd": "0", "public_text": "public synthetic text"}

    def _send_decision(self, decision=None):
        self.controller.files.write(A_DECISION, json.dumps(
            self.decision if decision is None else decision))

    def _send_result(self, order, *, mutate=None):
        result = {"schema": "market_broker_researcher_result_v1",
                  "cycle_id": "cycle-01", "order_sha256": digest(order),
                  "decision_sha256": order["decision_sha256"],
                  "task_id": order["task_id"],
                  "text_sha256": hashlib.sha256(order["public_text"].encode()).hexdigest()}
        self.researcher.files.write(B_RESULT, json.dumps(
            {**result, **(mutate or {})}))
        return result

    def test_exact_a_to_b_order_and_reviewed_b_to_a_feedback(self):
        self._send_decision()
        order = self.handoff.freeze_and_deliver()
        self.assertEqual(json.loads(self.researcher.files.read(B_ORDER)), order)
        self.assertEqual(set(self.researcher.files.contents), {B_ORDER})
        self.assertNotIn(B_ORDER, self.controller.files.contents)
        self._send_result(order)
        result = self.handoff.receive_result()
        review = {"schema": "market_broker_independent_review_v1",
                  "cycle_id": "cycle-01", "result_sha256": digest(result),
                  "verdict": "accept", "reason": "Host recomputed the exact public hash.",
                  "protected_data_opened": False}
        feedback = self.handoff.deliver_reviewed_feedback(review)
        self.assertEqual(json.loads(self.controller.files.read(A_FEEDBACK)), feedback)
        self.assertNotIn(A_FEEDBACK, self.researcher.files.contents)
        self.assertEqual(self.handoff.stage, "complete")
        self.assertTrue((self.root / "handoff/raw-decision.json").is_file())
        self.assertTrue((self.root / "handoff/feedback-delivery.json").is_file())

    def test_invalid_first_order_cannot_be_resampled(self):
        self._send_decision({**self.decision, "cost_bound_usd": "1"})
        with self.assertRaises(ValueError):
            self.handoff.freeze_and_deliver()
        self.assertTrue((self.root / "handoff/decision-failure.json").is_file())
        self.assertEqual(self.researcher.files.contents, {})
        self._send_decision()
        with self.assertRaises(ValueError):
            self.handoff.freeze_and_deliver()

    def test_tampered_researcher_result_fails_closed(self):
        self._send_decision()
        order = self.handoff.freeze_and_deliver()
        self._send_result(order, mutate={"text_sha256": "0" * 64})
        with self.assertRaises(ValueError):
            self.handoff.receive_result()
        self.assertTrue((self.root / "handoff/result-failure.json").is_file())
        self.assertNotIn(A_FEEDBACK, self.controller.files.contents)

    def test_tampered_host_order_cannot_admit_b_result(self):
        self._send_decision()
        order = self.handoff.freeze_and_deliver()
        self._send_result(order)
        changed = {**order, "public_text": "altered after delivery"}
        (self.root / "handoff/order.json").write_text(json.dumps(changed))
        with self.assertRaises(ValueError):
            self.handoff.receive_result()
        self.assertTrue((self.root / "handoff/result-failure.json").is_file())
        self.assertNotIn(A_FEEDBACK, self.controller.files.contents)

    def test_tampered_raw_controller_decision_cannot_admit_b_result(self):
        self._send_decision()
        order = self.handoff.freeze_and_deliver()
        self._send_result(order)
        (self.root / "handoff/raw-decision.json").write_text(
            json.dumps({"raw_utf8": "{}"}))
        with self.assertRaises(ValueError):
            self.handoff.receive_result()
        self.assertTrue((self.root / "handoff/result-failure.json").is_file())

    def test_malformed_first_decision_is_preserved_and_not_resampled(self):
        self.controller.files.write(A_DECISION, "{bad json")
        with self.assertRaises(json.JSONDecodeError):
            self.handoff.freeze_and_deliver()
        raw = json.loads((self.root / "handoff/raw-decision.json").read_text())
        self.assertEqual(raw["raw_utf8"], "{bad json")
        self.assertTrue((self.root / "handoff/decision-failure.json").is_file())

    def test_protected_or_wrong_review_is_rejected(self):
        self._send_decision()
        order = self.handoff.freeze_and_deliver()
        self._send_result(order)
        result = self.handoff.receive_result()
        review = {"schema": "market_broker_independent_review_v1",
                  "cycle_id": "cycle-01", "result_sha256": digest(result),
                  "verdict": "accept", "reason": "Hash matched.",
                  "protected_data_opened": True}
        with self.assertRaises(ValueError):
            self.handoff.deliver_reviewed_feedback(review)
        self.assertNotIn(A_FEEDBACK, self.controller.files.contents)
        self.assertTrue((self.root / "handoff/feedback-failure.json").is_file())
        with self.assertRaises(ValueError):
            self.handoff.deliver_reviewed_feedback({**review, "protected_data_opened": False})

    def test_tampered_raw_researcher_result_cannot_reach_a(self):
        self._send_decision()
        order = self.handoff.freeze_and_deliver()
        self._send_result(order)
        result = self.handoff.receive_result()
        (self.root / "handoff/raw-result.json").write_text(
            json.dumps({"raw_utf8": "{}"}))
        review = {"schema": "market_broker_independent_review_v1",
                  "cycle_id": "cycle-01", "result_sha256": digest(result),
                  "verdict": "accept", "reason": "Hash matched.",
                  "protected_data_opened": False}
        with self.assertRaises(ValueError):
            self.handoff.deliver_reviewed_feedback(review)
        self.assertTrue((self.root / "handoff/feedback-failure.json").is_file())
        self.assertNotIn(A_FEEDBACK, self.controller.files.contents)

    def test_closed_supervisor_cycle_blocks_handoff(self):
        self.state.close("cycle-01", outcome="failed")
        self._send_decision()
        with self.assertRaises(ValueError):
            self.handoff.freeze_and_deliver()
        self.assertEqual(self.researcher.files.contents, {})

    def test_same_sandbox_id_rejected(self):
        with self.assertRaises(ValueError):
            BrokerHandoff(
                controller_sandbox=self.controller,
                researcher_sandbox=self.controller,
                state=self.state, cycle_id="cycle-01", input_sha256="a" * 64,
                receipt_root=self.root / "same")


if __name__ == "__main__":
    unittest.main()
