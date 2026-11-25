"""I6 once-only restart/failure checks using native, invented offline fixtures.

Fixture TestCases are composed through module aliases; only seven tests collect.
No model, provider, network, live ledger or production source is modified.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import earnings_feedback_loop as flow
import test_capacity_feedback_engine as common_fixture
import test_earnings_capacity_loop as earnings_fixture
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


SCRIPT = Path(__file__).with_name("run_capacity_feedback_fixture.py")


def changed_execute(worker, slot):
    """Same behavior with a different retained handler identity."""
    return worker.execute(slot)


def retained_bytes(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


class I6RestartFailureTests(unittest.TestCase):
    def common(self):
        fixture = common_fixture.CommonEngineTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.setup_task("sum")
        return fixture

    @staticmethod
    def counts(fixture):
        return tuple(len(items) for items in
                     (fixture.packets, fixture.authored, fixture.reviewed, fixture.task.calls))

    def test_completed_restore_in_separate_process_has_zero_service_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "retained-sum"
            outputs = []
            for args in ([], ["--restore"]):
                process = subprocess.run(
                    [sys.executable, "-B", str(SCRIPT), "--root", str(root), *args],
                    text=True, capture_output=True, timeout=30)
                outputs.append({"args": args, "returncode": process.returncode,
                                "stdout": process.stdout, "stderr": process.stderr})
                print("I6_PROCESS_RAW=" + json.dumps(outputs[-1], sort_keys=True), flush=True)
                self.assertEqual(process.returncode, 0, process.stderr)
                report = json.loads(process.stdout)
                self.assertTrue(all(report["checks"].values()))
                self.assertEqual(report["model_calls"], 0)
                self.assertFalse(report["learning_claim"])
                if not args:
                    self.assertEqual(report["service_calls"],
                                     dict.fromkeys(engine.ROLES, 2))
                    before = retained_bytes(root)
                else:
                    self.assertEqual(report["service_calls"],
                                     dict.fromkeys(engine.ROLES, 0))
                    self.assertEqual(retained_bytes(root), before)

    def test_uncertain_execute_claim_without_done_halts_before_dispatch(self):
        fixture = self.common()
        save = engine.driver.c.save
        claim = fixture.root / "episode/loop/round-0001-execute.claim.json"

        def crash_after_claim(path, value):
            save(path, value)
            if Path(path) == claim:
                raise KeyboardInterrupt("invented crash after durable claim")

        with patch.object(engine.driver.c, "save", side_effect=crash_after_claim):
            with self.assertRaisesRegex(KeyboardInterrupt, "after durable claim"):
                fixture.invoke_engine()
        self.assertTrue(claim.is_file())
        self.assertFalse((claim.parent / "round-0001-execute.done.json").is_file())
        self.assertFalse((claim.parent / "round-0001-execute.failed.json").exists())
        self.assertEqual(self.counts(fixture), (1, 1, 1, 0))
        before = retained_bytes(fixture.root)
        with self.assertRaisesRegex(engine.driver.LoopHalted, "incomplete durable record"):
            fixture.invoke_engine()
        self.assertEqual(self.counts(fixture), (1, 1, 1, 0))
        self.assertEqual(retained_bytes(fixture.root), before)

    def test_saved_controller_failure_preserves_original_and_cannot_retry(self):
        fixture = self.common()
        fixture.bad_controller = True
        with self.assertRaises(engine.driver.LoopHalted):
            fixture.invoke_engine()
        failure = fixture.root / "episode/loop/round-0001-controller.failed.json"
        saved = json.loads(failure.read_bytes())
        self.assertEqual((saved["exception_type"], saved["retry_allowed"]),
                         ("JSONDecodeError", False))
        original = Path(fixture.envelope["slots"][0]["controller"]) / "response.json"
        self.assertEqual(engine.read(engine.pin(original))["output"][0]["content"][0]["text"],
                         "not JSON")
        before = retained_bytes(fixture.root)
        with self.assertRaisesRegex(engine.driver.LoopHalted, "closed to retry"):
            fixture.invoke_engine()
        self.assertEqual(self.counts(fixture), (1, 0, 0, 0))
        self.assertEqual(retained_bytes(fixture.root), before)

    def test_changed_selected_source_and_handler_refuse_completed_replay(self):
        for mode in ("source", "handler"):
            with self.subTest(mode=mode):
                fixture = self.common()
                outcome = fixture.invoke_engine()
                self.assertEqual(outcome["status"], "completed")
                before_counts = self.counts(fixture)
                services = fixture.services()
                if mode == "source":
                    # Only this fresh fixture's synthetic selected source is corrupted.
                    source = fixture.root / "harness_v2.py"
                    source.write_text("PROFILE = {}\n")
                else:
                    services["execute"] = changed_execute
                before = retained_bytes(fixture.root)
                with self.assertRaises((ValueError, engine.driver.LoopHalted)):
                    engine.run(fixture.bound, fixture.native.restore(), fixture.task,
                               services=services)
                self.assertEqual(self.counts(fixture), before_counts)
                self.assertEqual(retained_bytes(fixture.root), before)

    def test_changed_final_state_bytes_refuse_replay_without_new_records(self):
        fixture = self.common()
        outcome = fixture.invoke_engine()
        state = outcome["result"]["state"]
        path = Path(state["path"])
        original = engine.read(state)
        self.assertEqual(len(original["records"]), 2)
        path.write_text(json.dumps({"task": "sum", "records": []}))
        self.assertNotEqual(hashlib.sha256(path.read_bytes()).hexdigest(), state["sha256"])
        before, counts = retained_bytes(fixture.root), self.counts(fixture)
        with self.assertRaises((ValueError, engine.driver.LoopHalted)):
            fixture.invoke_engine()
        self.assertEqual(self.counts(fixture), counts)
        self.assertEqual(retained_bytes(fixture.root), before)

    def test_reconciliation_delivers_exact_next_state_feedback_and_history(self):
        fixture = self.common()
        outcome = fixture.invoke_engine()
        loop = fixture.root / "episode/loop"
        previous = engine.driver._read_pair(loop / "round-0001-reconcile.done.json")["output"]
        reviewed = engine.driver._read_pair(loop / "round-0001-result_review.done.json")["output"]
        self.assertEqual(previous, reviewed)
        first, second = fixture.task.calls
        self.assertEqual(second.parent, previous["state"])
        parent = engine.read(previous["state"])
        final = engine.read(outcome["result"]["state"])
        self.assertEqual(final["records"][:-1], parent["records"])
        self.assertEqual((len(parent["records"]), len(final["records"])), (1, 2))
        packet = engine.read(engine.pin(fixture.root / "episode/packet-02.json"))
        self.assertEqual(packet, fixture.packets[1])
        self.assertEqual(packet["feedback"], previous["feedback"])
        self.assertEqual(packet["feedback_sha256"], digest(previous))
        self.assertEqual(packet["parent_pair_sha256"], previous["pair_sha256"])
        self.assertEqual(first.state["records"], parent["records"])
        self.assertEqual(outcome["result"]["pair_sha256"],
                         digest(fixture.native.batch.snapshot()["micro_evolution"]["active_pair"]))
        self.assertEqual(len(fixture.native.batch.snapshot()["micro_evolution"]["history"]), 2)
        self.assertFalse(outcome["result"]["claims"]["learning"])
        self.assertFalse(outcome["result"]["claims"]["live_RH_authorship"])

    def test_failed_earnings_execution_preserves_fact_and_terminal_receipts(self):
        fixture = earnings_fixture.CapacityLoopTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.axes = ["continue", "continue"]
        calls = []

        def fail_after_fact(worker, slot):
            root = Path(slot)
            root.mkdir(parents=True, exist_ok=False)
            worker.start(root)
            tool = worker.dispatch("save_research_record", {
                "record_json": json.dumps(deepcopy(fixture.data.fact))})
            engine.save(root / "tool-receipt.json", tool)
            worker.finish(root)
            calls.append(worker)
            return {"result": engine.save(root / "result.json", {
                "status": "FAILED_NO_RETRY", "planned_targets": 5,
                "scored_targets": 0, "error_type": "InventedExecutionFailure"}),
                "score": engine.save(root / "score.json", {})}

        roles = {"controller": fixture.controller_role, "author": fixture.author_role,
                 "review": fixture.review_role, "forecast": fail_after_fact}
        with self.assertRaises(engine.driver.LoopHalted) as halted:
            flow.run_capacity(fixture.bound, fixture.native.restore(), roles=roles)
        self.assertIsInstance(halted.exception.__cause__, RuntimeError)
        worker = calls[0]
        self.assertEqual(worker.state_api.load(worker.state_binding)["records"][0]["record"],
                         fixture.data.fact)
        self.assertEqual(fixture.api.load(fixture.envelope["initial_state"])["records"], [])
        terminal = Path(fixture.envelope["slots"][0]["forecast"])
        self.assertEqual(engine.read(engine.pin(terminal / "result.json"))["status"],
                         "FAILED_NO_RETRY")
        self.assertEqual(engine.read(engine.pin(terminal / "research-state-output.json"))["state"],
                         worker.state_binding)
        before = retained_bytes(fixture.root)
        with self.assertRaisesRegex(engine.driver.LoopHalted, "closed to retry"):
            flow.run_capacity(fixture.bound, fixture.native.restore(), roles=roles)
        self.assertEqual((len(fixture.packets), len(calls)), (1, 1))
        self.assertEqual((fixture.authored, fixture.reviewed), ([], []))
        self.assertFalse(Path(fixture.envelope["slots"][1]["controller"]).exists())
        self.assertEqual(retained_bytes(fixture.root), before)


if __name__ == "__main__":
    unittest.main()
