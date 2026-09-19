"""Offline guest-loop checks only; no model, E2B, keys, or benchmark data."""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from market_rsi import canonical, digest
from supervisor_harness import directional_guest_worker as worker


CYCLE = "cycle-directional-01"
INPUT_SHA = "a" * 64


def order(sequence: int, *, task_id: str | None = None) -> dict:
    task = {"schema": "market_directional_task_v1",
            "cycle_id": CYCLE, "input_sha256": INPUT_SHA,
            "sequence": sequence,
            "task_id": task_id or f"public-hash-{sequence:03d}",
            "public_text": f"public synthetic task {sequence:03d}"}
    return {"schema": "market_directional_order_v1",
            "cycle_id": CYCLE, "input_sha256": INPUT_SHA,
            "sequence": sequence, "task_id": task["task_id"],
            "task_sha256": digest(task), "public_text": task["public_text"]}


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def sleep(self, interval):
        self.value += interval


class DirectionalGuestWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "directional"
        self.orders = self.root / "orders"
        self.orders.mkdir(parents=True)

    def _write(self, sequence: int, value: dict | None = None):
        (self.orders / f"{sequence:03d}.json").write_text(
            canonical(value if value is not None else order(sequence)))

    def _run(self, **kwargs) -> list[dict]:
        output = io.StringIO()
        with redirect_stdout(output):
            worker.run(self.root, **kwargs)
        return [json.loads(line) for line in output.getvalue().splitlines()]

    def test_twenty_sequential_orders_one_process_exact_receipts_and_milestones(self):
        self._write(0)

        def issue_next(_interval):
            next_sequence = len(list((self.root / "events").glob("*.json")))
            self._write(next_sequence)

        lines = self._run(sleep=issue_next)
        self.assertEqual(len(lines), 40)
        self.assertEqual(lines, [
            {"schema": "market_directional_guest_milestone_v1",
             "sequence": sequence, "kind": kind}
            for sequence in range(20) for kind in ("ack", "event")])
        self.assertEqual(len(list((self.root / "acks").iterdir())), 20)
        self.assertEqual(len(list((self.root / "events").iterdir())), 20)
        for sequence in range(20):
            expected_order = order(sequence)
            order_sha = digest(expected_order)
            text_sha = hashlib.sha256(
                expected_order["public_text"].encode("utf-8")).hexdigest()
            ack = json.loads((self.root / "acks" / f"{sequence:03d}.json").read_text())
            event = json.loads((self.root / "events" / f"{sequence:03d}.json").read_text())
            self.assertEqual(ack, {
                "schema": "market_directional_ack_v1", "cycle_id": CYCLE,
                "sequence": sequence, "order_sha256": order_sha})
            self.assertEqual(event, {
                "schema": "market_directional_tool_event_v1", "cycle_id": CYCLE,
                "sequence": sequence, "task_id": expected_order["task_id"],
                "order_sha256": order_sha, "tool_name": "hash_public_text",
                "input_sha256": text_sha, "output_sha256": text_sha,
                "status": "ok"})

    def test_one_expected_order_exits_with_unchanged_ack_event_schema(self):
        self._write(0)
        lines = self._run(expected_orders=1)
        expected_order = order(0)
        text_sha = hashlib.sha256(
            expected_order["public_text"].encode("utf-8")).hexdigest()
        self.assertEqual(lines, [
            {"schema": "market_directional_guest_milestone_v1",
             "sequence": 0, "kind": "ack"},
            {"schema": "market_directional_guest_milestone_v1",
             "sequence": 0, "kind": "event"}])
        self.assertEqual(json.loads((self.root / "acks/000.json").read_text()), {
            "schema": "market_directional_ack_v1", "cycle_id": CYCLE,
            "sequence": 0, "order_sha256": digest(expected_order)})
        self.assertEqual(json.loads((self.root / "events/000.json").read_text()), {
            "schema": "market_directional_tool_event_v1", "cycle_id": CYCLE,
            "sequence": 0, "task_id": expected_order["task_id"],
            "order_sha256": digest(expected_order),
            "tool_name": "hash_public_text", "input_sha256": text_sha,
            "output_sha256": text_sha, "status": "ok"})

    def test_one_order_mode_rejects_any_second_order_before_receipts(self):
        self._write(0)
        self._write(1)
        with self.assertRaisesRegex(ValueError, "unexpected"):
            self._run(expected_orders=1)
        self.assertEqual(list((self.root / "acks").iterdir()), [])
        self.assertEqual(list((self.root / "events").iterdir()), [])

    def test_one_order_mode_rejects_late_second_duplicate_task_id(self):
        self._write(0)
        output = io.StringIO()
        original_milestone = worker._milestone

        def add_duplicate_after_event(sequence, kind):
            original_milestone(sequence, kind)
            if kind == "event":
                self._write(1, order(1, task_id=order(0)["task_id"]))

        with patch.object(worker, "_milestone", side_effect=add_duplicate_after_event):
            with redirect_stdout(output), self.assertRaisesRegex(ValueError, "unexpected"):
                worker.run(self.root, expected_orders=1)
        self.assertEqual([json.loads(line)["kind"]
                          for line in output.getvalue().splitlines()],
                         ["ack", "event"])
        self.assertFalse((self.root / "acks/001.json").exists())
        self.assertFalse((self.root / "events/001.json").exists())

    def test_expected_order_count_is_only_one_or_historical_twenty(self):
        for value in (0, 2, 21, True, "1"):
            with self.subTest(value=value), self.assertRaisesRegex(
                    ValueError, "expected-order bound"):
                self._run(expected_orders=value)

    def test_cli_isolated_python_emits_all_milestones(self):
        for sequence in range(20):
            self._write(sequence)
        command = [sys.executable, "-I", str(Path(worker.__file__).resolve()),
                   "--root", str(self.root), "--total-timeout", "5"]
        result = subprocess.run(command, text=True, capture_output=True,
                                timeout=7, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 40)
        self.assertEqual(json.loads(result.stdout.splitlines()[-1])["kind"], "event")

    def test_cli_one_order_count_is_explicit_and_exits_after_one(self):
        self._write(0)
        command = [sys.executable, "-I", str(Path(worker.__file__).resolve()),
                   "--root", str(self.root), "--total-timeout", "5",
                   "--expected-orders", "1"]
        result = subprocess.run(command, text=True, capture_output=True,
                                timeout=7, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([json.loads(line)["kind"]
                          for line in result.stdout.splitlines()], ["ack", "event"])

    def test_duplicate_task_id_fails_before_second_ack(self):
        self._write(0)
        self._write(1, order(1, task_id=order(0)["task_id"]))
        with self.assertRaisesRegex(ValueError, "duplicate guest task ID"):
            self._run()
        self.assertFalse((self.root / "acks/001.json").exists())

    def test_changed_cycle_or_a_input_fails_before_second_ack(self):
        for change in ({"cycle_id": "different-cycle"},
                       {"input_sha256": "b" * 64}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / "directional"
                orders = root / "orders"
                orders.mkdir(parents=True)
                (orders / "000.json").write_text(canonical(order(0)))
                altered = {**order(1), **change}
                task = {"schema": "market_directional_task_v1",
                        "cycle_id": altered["cycle_id"],
                        "input_sha256": altered["input_sha256"],
                        "sequence": 1, "task_id": altered["task_id"],
                        "public_text": altered["public_text"]}
                altered["task_sha256"] = digest(task)
                (orders / "001.json").write_text(canonical(altered))
                with redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                    worker.run(root)
                self.assertFalse((root / "acks/001.json").exists())

    def test_wrong_task_hash_and_extra_field_fail_before_ack(self):
        for change in ({"task_sha256": "0" * 64}, {"extra": "untrusted"},
                       {"input_sha256": "invalid"}, {"sequence": True},
                       {"public_text": "x" * 4097}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / "directional"
                (root / "orders").mkdir(parents=True)
                (root / "orders/000.json").write_text(canonical({**order(0), **change}))
                with self.assertRaises(ValueError):
                    worker.run(root)
                self.assertEqual(list((root / "acks").iterdir()), [])

    def test_duplicate_json_member_is_rejected(self):
        raw = canonical(order(0)).removesuffix("}") + ',"sequence":0}'
        (self.orders / "000.json").write_text(raw)
        with self.assertRaisesRegex(ValueError, "duplicate JSON member"):
            self._run()

    def test_prior_order_mutation_stops_next_handoff(self):
        self._write(0)

        def mutate(_interval):
            (self.orders / "000.json").write_text(canonical({**order(0), "public_text": "changed"}))
            self._write(1)

        with self.assertRaisesRegex(ValueError, "mutated"):
            self._run(sleep=mutate)
        self.assertFalse((self.root / "acks/001.json").exists())

    def test_prior_ack_mutation_stops_next_handoff(self):
        self._write(0)

        def mutate(_interval):
            (self.root / "acks/000.json").write_text("{}")
            self._write(1)

        with self.assertRaisesRegex(ValueError, "mutated"):
            self._run(sleep=mutate)
        self.assertFalse((self.root / "acks/001.json").exists())

    def test_order_mutation_after_ack_prevents_event(self):
        self._write(0)
        output = io.StringIO()
        original_milestone = worker._milestone

        def mutate_after_ack(sequence, kind):
            original_milestone(sequence, kind)
            if kind == "ack":
                (self.orders / "000.json").write_text(canonical({**order(0), "public_text": "changed"}))

        with patch.object(worker, "_milestone", side_effect=mutate_after_ack):
            with redirect_stdout(output), self.assertRaisesRegex(ValueError, "mutated"):
                worker.run(self.root, expected_orders=1)
        self.assertEqual([json.loads(line)["kind"] for line in output.getvalue().splitlines()],
                         ["ack"])
        self.assertFalse((self.root / "events/000.json").exists())

    def test_preexisting_output_and_unexpected_order_fail_closed(self):
        self._write(0)
        (self.root / "acks").mkdir()
        (self.root / "acks/000.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "not fresh"):
            self._run()
        (self.root / "acks/000.json").unlink()
        (self.orders / "000-copy.json").write_text(canonical(order(0)))
        with self.assertRaisesRegex(ValueError, "unexpected"):
            self._run()

    def test_order_symlink_is_rejected(self):
        source = Path(self.temp.name) / "source.json"
        source.write_text(canonical(order(0)))
        (self.orders / "000.json").symlink_to(source)
        with self.assertRaisesRegex(ValueError, "unsafe"):
            self._run()

    def test_bounded_timeout_has_no_receipts(self):
        clock = FakeClock()
        with self.assertRaisesRegex(TimeoutError, "000 timed out"):
            self._run(clock=clock, sleep=clock.sleep,
                      poll_interval=0.01, per_order_timeout=0.03,
                      expected_orders=1)
        self.assertEqual(list((self.root / "acks").iterdir()), [])
        self.assertEqual(list((self.root / "events").iterdir()), [])

    def test_failed_event_publication_has_no_event_milestone(self):
        self._write(0)
        output = io.StringIO()
        original_link = worker.os.link
        calls = 0

        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise FileExistsError("simulated event path collision")
            return original_link(source, target)

        with patch.object(worker.os, "link", side_effect=fail_second):
            with redirect_stdout(output), self.assertRaises(FileExistsError):
                worker.run(self.root)
        self.assertEqual([json.loads(line)["kind"] for line in output.getvalue().splitlines()],
                         ["ack"])
        self.assertFalse((self.root / "events/000.json").exists())


if __name__ == "__main__":
    unittest.main()
