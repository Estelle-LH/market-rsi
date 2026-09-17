"""Offline one-B directional handoff fixture; never calls E2B or a model."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from market_rsi import canonical, digest
from supervisor_harness.directional_handoff import (
    B_ACK_DIR, B_EVENT_DIR, B_ORDER_DIR, DirectionalHandoff,
    EXPECTED_HANDOFFS)
from supervisor_harness.global_state_gate import SupervisorGlobalState


class Clock:
    def __init__(self):
        self.now = 1_000_000_000

    def __call__(self):
        return self.now

    def advance(self, ns):
        self.now += ns


class Files:
    def __init__(self):
        self.contents = {}
        self.writes = []

    def read(self, path):
        return self.contents[path]

    def write(self, path, value):
        if path in self.contents:
            raise ValueError("guest order path reused")
        self.writes.append(path)
        self.contents[path] = value


class Sandbox:
    def __init__(self, sandbox_id):
        self.sandbox_id = sandbox_id
        self.files = Files()


class DirectionalHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        decision = self.root / "decision.md"
        decision.write_text("frozen supervisor decision\n")
        self.state = SupervisorGlobalState(self.root / "state", decision)
        snapshot = self.state.initialize()
        self.state.claim("cycle-directional-01",
                         expected_head_sha256=snapshot["head_sha256"],
                         source_sha256="b" * 64, prior_canary_sha256="c" * 64)
        self.b = Sandbox("persistent-B")
        self.clock = Clock()
        self.handoff = DirectionalHandoff(
            researcher_sandbox=self.b, state=self.state,
            cycle_id="cycle-directional-01", input_sha256="a" * 64,
            receipt_root=self.root / "directional", clock_ns=self.clock)

    def _task(self, seq):
        return {"schema": "market_directional_task_v1",
                "cycle_id": "cycle-directional-01", "input_sha256": "a" * 64,
                "sequence": seq, "task_id": f"public-hash-{seq:03d}",
                "public_text": f"public synthetic task {seq:03d}"}

    def _b_ack(self, seq, order, **changes):
        ack = {"schema": "market_directional_ack_v1",
               "cycle_id": "cycle-directional-01", "sequence": seq,
               "order_sha256": digest(order)}
        self.b.files.contents[f"{B_ACK_DIR}/{seq:03d}.json"] = canonical(
            {**ack, **changes})

    def _b_event(self, seq, order, **changes):
        text_sha = hashlib.sha256(order["public_text"].encode()).hexdigest()
        event = {"schema": "market_directional_tool_event_v1",
                 "cycle_id": "cycle-directional-01", "sequence": seq,
                 "task_id": order["task_id"], "order_sha256": digest(order),
                 "tool_name": "hash_public_text", "input_sha256": text_sha,
                 "output_sha256": text_sha, "status": "ok"}
        self.b.files.contents[f"{B_EVENT_DIR}/{seq:03d}.json"] = canonical(
            {**event, **changes})
        return event

    def _one(self, seq, *, handoff_ns=100_000_000, visibility_ns=100_000_000):
        task = self._task(seq)
        order = self.handoff.send_task(seq, task)
        self.assertEqual(json.loads(self.b.files.read(
            f"{B_ORDER_DIR}/{seq:03d}.json")), order)
        self._b_ack(seq, order)
        self.clock.advance(handoff_ns)
        self.handoff.receive_ack(seq)
        event = self._b_event(seq, order)
        self.handoff.receive_event(seq)
        self.clock.advance(visibility_ns)
        view = self.handoff.read_event_for_a(seq)
        self.assertEqual(view["event"], event)
        self.assertEqual(view["event_sha256"], digest(event))
        self.assertEqual(view["task_sha256"], digest(task))
        return view

    def test_twenty_distinct_handoffs_and_a_reads_reuse_one_b(self):
        for seq in range(EXPECTED_HANDOFFS):
            self._one(seq)
        summary = self.handoff.finish()
        self.assertTrue(summary["friction_criterion_passed"])
        self.assertEqual(summary["sample_count"], 20)
        self.assertEqual(summary["missing_count"], 0)
        self.assertEqual(summary["duplicate_count"], 0)
        self.assertEqual(summary["timeout_count"], 0)
        self.assertEqual(summary["handoff_p95_ns"], 100_000_000)
        self.assertEqual(summary["event_visibility_p95_ns"], 100_000_000)
        self.assertEqual(self.b.sandbox_id, "persistent-B")
        self.assertEqual(self.b.files.writes, [
            f"{B_ORDER_DIR}/{seq:03d}.json" for seq in range(20)])
        receipts = list((self.root / "directional").glob("*-a-read.json"))
        self.assertEqual(len(receipts), 20)
        self.assertFalse(summary["live_e2b_proven"])
        self.assertFalse(summary["glm_authorship_proven"])
        self.assertFalse(summary["cleanup_verified"])

    def test_duplicate_or_out_of_order_task_fails_closed(self):
        self._one(0)
        with self.assertRaises(ValueError):
            self.handoff.send_task(0, self._task(0))
        self.assertEqual(self.handoff.stage, "failed")
        self.assertEqual(len(self.b.files.writes), 1)
        summary = self.handoff.finish()
        self.assertFalse(summary["friction_criterion_passed"])
        self.assertEqual(summary["missing_count"], 19)
        self.assertEqual(summary["duplicate_count"], 1)

    def test_reused_a_task_id_is_rejected_before_second_b_write(self):
        self._one(0)
        task = {**self._task(1), "task_id": self._task(0)["task_id"]}
        with self.assertRaisesRegex(ValueError, "duplicate A task ID"):
            self.handoff.send_task(1, task)
        self.assertEqual(len(self.b.files.writes), 1)
        self.assertEqual(self.handoff.finish()["duplicate_count"], 1)

    def test_wrong_ack_hash_stops_before_event_delivery(self):
        order = self.handoff.send_task(0, self._task(0))
        self._b_ack(0, order, order_sha256="0" * 64)
        with self.assertRaises(ValueError):
            self.handoff.receive_ack(0)
        self.assertEqual(self.handoff.stage, "failed")
        self.assertFalse((self.root / "directional/000-event.json").exists())

    def test_tampered_b_event_never_reaches_a(self):
        order = self.handoff.send_task(0, self._task(0))
        self._b_ack(0, order)
        self.handoff.receive_ack(0)
        self._b_event(0, order, output_sha256="0" * 64)
        with self.assertRaises(ValueError):
            self.handoff.receive_event(0)
        self.assertFalse((self.root / "directional/000-a-read.json").exists())

    def test_tampered_host_order_receipt_blocks_ack(self):
        order = self.handoff.send_task(0, self._task(0))
        self._b_ack(0, order)
        (self.root / "directional/000-order.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "host handoff receipt changed"):
            self.handoff.receive_ack(0)
        self.assertFalse((self.root / "directional/000-ack.json").exists())

    def test_tampered_host_event_receipt_blocks_a_read(self):
        order = self.handoff.send_task(0, self._task(0))
        self._b_ack(0, order)
        self.handoff.receive_ack(0)
        self._b_event(0, order)
        self.handoff.receive_event(0)
        (self.root / "directional/000-event.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "host handoff receipt changed"):
            self.handoff.read_event_for_a(0)
        self.assertFalse((self.root / "directional/000-a-read.json").exists())

    def test_missing_event_is_not_a_complete_sample(self):
        order = self.handoff.send_task(0, self._task(0))
        self._b_ack(0, order)
        self.handoff.receive_ack(0)
        with self.assertRaises(KeyError):
            self.handoff.receive_event(0)
        summary = self.handoff.finish()
        self.assertEqual(summary["sample_count"], 0)
        self.assertEqual(summary["missing_count"], 20)
        self.assertFalse(summary["friction_criterion_passed"])

    def test_timeout_is_terminal_and_not_counted(self):
        order = self.handoff.send_task(0, self._task(0))
        self._b_ack(0, order)
        self.handoff.receive_ack(0)

        def timeout(_path):
            raise TimeoutError("simulated B event read timeout")

        self.b.files.read = timeout
        with self.assertRaises(TimeoutError):
            self.handoff.receive_event(0)
        summary = self.handoff.finish()
        self.assertEqual(summary["failure"], "TimeoutError")
        self.assertEqual(summary["timeout_count"], 1)
        self.assertFalse(summary["friction_criterion_passed"])

    def test_event_visibility_includes_broker_file_read(self):
        original_read = self.b.files.read

        def delayed_read(path):
            if path.startswith(B_EVENT_DIR):
                self.clock.advance(200_000_000)
            return original_read(path)

        self.b.files.read = delayed_read
        self._one(0, visibility_ns=100_000_000)
        receipt = json.loads((self.root / "directional/000-a-read.json").read_text())
        self.assertEqual(receipt["event_visibility_latency_ns"], 300_000_000)

    def test_p95_and_single_leg_limits_are_independent(self):
        for seq in range(20):
            self._one(seq, handoff_ns=2_100_000_000 if seq == 19 else 100_000_000)
        summary = self.handoff.finish()
        self.assertTrue(summary["friction_criterion_passed"])
        self.assertEqual(summary["handoff_p95_ns"], 100_000_000)
        self.assertEqual(summary["handoff_max_ns"], 2_100_000_000)

    def test_two_slow_samples_fail_p95(self):
        for seq in range(20):
            self._one(seq, visibility_ns=2_100_000_000 if seq >= 18 else 100_000_000)
        summary = self.handoff.finish()
        self.assertFalse(summary["friction_criterion_passed"])
        self.assertEqual(summary["event_visibility_p95_ns"], 2_100_000_000)

    def test_single_transport_leg_above_five_seconds_fails(self):
        for seq in range(20):
            self._one(seq, handoff_ns=5_000_000_001 if seq == 19 else 100_000_000)
        summary = self.handoff.finish()
        self.assertFalse(summary["friction_criterion_passed"])
        self.assertEqual(summary["handoff_max_ns"], 5_000_000_001)

    def test_wrong_frozen_input_rejected_before_guest_write(self):
        task = {**self._task(0), "input_sha256": "d" * 64}
        with self.assertRaises(ValueError):
            self.handoff.send_task(0, task)
        self.assertEqual(self.b.files.writes, [])

    def test_changed_b_identity_or_closed_cycle_blocks_next_handoff(self):
        self.b.sandbox_id = "replacement-B"
        with self.assertRaises(ValueError):
            self.handoff.send_task(0, self._task(0))
        self.assertEqual(self.b.files.writes, [])


if __name__ == "__main__":
    unittest.main()
