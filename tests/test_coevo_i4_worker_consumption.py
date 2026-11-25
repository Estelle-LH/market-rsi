"""I4: physical worker payload/tool use versus declared receipts; invented data."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import earnings_capacity_task as task_module
import earnings_capacity_worker as worker_module
import earnings_transport_fixture as transport
import test_earnings_capacity_loop as fixtures
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine

ARTIFACT_ROOT = Path("/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/earnings-coevolution-plan-20261013/engine-interface-tests/workers/I4-child-v2")


class _ResettingTask(task_module.EarningsTask):
    """A deliberately faulty adapter silently loses preceding-round memory."""
    count = 0

    def worker(self, envelope, capacity, pair, state):
        self.count += 1
        if self.count == 2:
            state = envelope["initial_state"]
        return super().worker(envelope, capacity, pair, state)


class WorkerConsumptionTests(unittest.TestCase):
    def setUp(self):
        # Composition avoids importing/inheriting discoverable fixture tests.
        self.f = fixtures.CapacityLoopTests(
            "test_two_actual_driver_rounds_R_then_H_use_feedback_records_and_cold_replay")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.requests = []
        self.tool_arguments = []
        self.addCleanup(self.preserve_originals)

    def preserve_originals(self):
        # Archive the invented originals before the fixture removes its owned
        # temporary roots. Only this worker's declared diagnostic directory.
        originals = {}
        for path in sorted(self.f.root.rglob("*.json")):
            if not path.is_file():
                continue
            data = path.read_bytes()
            originals[str(path.relative_to(self.f.root))] = {
                "sha256": hashlib.sha256(data).hexdigest(), "raw": data.decode()}
        engine.save(ARTIFACT_ROOT / ("diagnostics-" + self._testMethodName + "-" + self.f.root.name + ".json"), {
            "test": self.id(), "fixture_root": str(self.f.root),
            "physical_fake_http_requests": self.requests,
            "physical_tool_arguments": self.tool_arguments,
            "invented_originals": originals})

    def worker(self, state=None, company=None, task_id=None):
        return worker_module.CapacityWorker(
            company or self.f.company, task_id or self.f.task,
            self.f.native.restore(),
            digest(self.f.native.batch.snapshot()["micro_evolution"]["active_pair"]),
            self.f.root / "i4-memory", state)

    def completion(self, output, result=None, score=None):
        score = score or {"score_out_of_5": 0, "target_count": 5, "prediction_count": 5,
                          "duplicate_prediction_ids": [], "unknown_prediction_ids": []}
        body = dict(result or {"turns": 2, "tool_calls": 0}, status="COMPLETED_SCORED", planned_targets=5,
                    scored_targets=5, points=score["score_out_of_5"])
        return {
            "result": engine.save(output / "result.json", body),
            "score": engine.save(output / "score.json", score)}

    def actual(self, worker, slot):
        output = Path(slot)
        output.mkdir(parents=True, exist_ok=False)
        n = len(self.f.executed)
        self.f.executed.append(worker)
        observed = []

        def reply(request):
            original = deepcopy(request)
            observed.append(original)
            turn = len(observed)
            self.requests.append({"slot": str(output), "turn": turn, "payload": original})
            if turn == 1:
                name = "save_research_record" if n == 0 else "read_file"
                args = ({"record_json": json.dumps(self.f.data.fact)} if n == 0 else
                        {"path": "filings/old.md", "offset": 0, "characters": 5000})
                return {"status": "completed", "output": [{
                    "type": "function_call", "call_id": f"invented-i4-{n}",
                    "name": name, "arguments": json.dumps(args)}]}
            return {"status": "completed", "output": [{"type": "message", "content": [{
                "type": "output_text", "text": json.dumps({"predictions": [
                    {"target_id": f"T{i:03d}", "predicted_value": 100} for i in range(1, 6)]})}]}]}

        def dispatch(name, arguments):
            self.tool_arguments.append({"slot": slot, "name": name,
                                        "arguments": deepcopy(arguments)})
            return underlying(name, arguments)

        underlying = worker.tools.dispatch
        with patch.object(worker.tools, "dispatch", side_effect=dispatch):
            result = transport.run_forecast(self.f, worker, output, reply)
        self.assertGreaterEqual(len(observed), 1)
        self.assertEqual(observed[0]["input"], worker.context["messages"])
        score = transport.score_payload(self.f.envelope["evaluation_kernel"], output)
        return self.completion(output, result, score)

    def receipt_only(self, worker, slot):
        """Forge matching receipts without start, finish, dispatch or provider."""
        output = Path(slot)
        output.mkdir(parents=True, exist_ok=False)
        self.f.executed.append(worker)
        engine.save(output / "effective-capacity.json", {
            "context": worker.context, "initial_state": worker.state_binding,
            "state_receipt": worker.state_receipt})
        engine.save(output / "research-state-output.json", {
            "state": worker.state_binding, "records": len(worker.state["records"]),
            "tool_calls": 0})
        return self.completion(output)

    def run_engine(self, task=None, execute=None):
        return engine.run(self.f.bound, self.f.native.restore(), task or task_module.EarningsTask(),
                          services={"controller": self.f.controller_role,
                                    "author": self.f.author_role, "review": self.f.review_role,
                                    "execute": execute or self.actual})

    def test_selected_R_reaches_wire_and_H_clamps_physical_tool_arguments(self):
        outcome = self.run_engine()
        self.assertEqual(outcome["completed_rounds"], 2)
        first = self.requests[0]["payload"]
        self.assertEqual(first["input"][1]["content"], "Verify signs with calculate")
        self.assertEqual(digest(first["input"]), self.f.executed[0].context["payload_sha256"])
        self.assertIn("save_research_record", [x["name"] for x in first["tools"]])
        second_read = next(x for x in self.tool_arguments if x["name"] == "read_file")
        self.assertEqual(second_read["arguments"]["characters"], 1000)
        self.assertTrue(all(r["selected_pair_sha256"] == self.f.executed[1].pair
                            for r in self.f.executed[1].context["receipts"]))
        with self.assertRaises(ValueError):
            self.f.executed[1].dispatch("read_file", {
                "path": "filings/old.md", "offset": 0, "characters": 20001})

    def test_exact_prior_state_digest_and_records_reach_cold_second_wire(self):
        self.run_engine()
        preceding = engine.driver._read_pair(
            self.f.root / "episode/loop/round-0001-reconcile.done.json")["output"]["state"]
        cold = self.f.executed[1]
        self.assertEqual(cold.state_receipt["state_sha256"], preceding["sha256"])
        first_input = next(x["payload"]["input"] for x in self.requests
                           if x["slot"] == self.f.envelope["slots"][1]["forecast"])
        notes = json.loads(first_input[-1]["content"].split("\n", 1)[1])
        self.assertEqual(notes, self.f.api.load(preceding))
        self.assertEqual(notes["records"][0]["record"], self.f.data.fact)
        before = len(self.requests)
        self.assertEqual(self.run_engine()["completed_rounds"], 2)
        self.assertEqual(len(self.requests), before)

    def test_silent_initial_memory_reset_cannot_close_second_round(self):
        with self.assertRaises(engine.driver.LoopHalted):
            self.run_engine(_ResettingTask())
        self.assertEqual(len(self.f.executed), 2)
        self.assertEqual(self.f.executed[1].state_receipt["state_sha256"],
                         self.f.envelope["initial_state"]["sha256"])
        self.assertFalse((self.f.root / "episode/loop/round-0002-reconcile.done.json").exists())

    def test_missing_effective_or_terminal_receipt_is_refused(self):
        task = task_module.EarningsTask()
        task.preflight(self.f.envelope)
        for missing in ("effective-capacity.json", "research-state-output.json"):
            with self.subTest(missing=missing):
                worker = self.worker(self.f.envelope["initial_state"])
                output = self.f.root / ("missing-" + missing)
                output.mkdir()
                originals = self.completion(output)
                if missing != "effective-capacity.json":
                    engine.save(output / "effective-capacity.json", {
                        "context": worker.context, "initial_state": worker.state_binding,
                        "state_receipt": worker.state_receipt})
                with self.assertRaises((FileNotFoundError, ValueError)):
                    task.execution(originals, worker, str(output))

    def test_forged_matching_receipts_without_physical_payload_are_refused(self):
        # This must fail closed even when the two declared receipt files match.
        # A pass here would establish receipt refusal, not model learning.
        with self.assertRaises(engine.driver.LoopHalted):
            self.run_engine(execute=self.receipt_only)
        self.assertEqual(self.requests, [])

    def test_selected_source_drift_refuses_before_physical_provider_call(self):
        worker = self.worker(self.f.envelope["initial_state"])
        # Runtime fixture source, never checkout production or fixture source.
        (self.f.root / "researcher_v1.py").write_text("PROFILE = {}\n")
        with self.assertRaises(ValueError):
            self.actual(worker, str(self.f.root / "source-drift-forecast"))
        self.assertEqual(self.requests, [])

    def test_wrong_company_cutoff_or_task_state_is_refused_before_send(self):
        bound = self.f.envelope["initial_state"]
        changes = ((dict(self.f.company, cik="CIK0000000002"), self.f.task),
                   (dict(self.f.company, cutoff="2026-02-02"), self.f.task),
                   (self.f.company, "invented-different-task"))
        for company, task_id in changes:
            with self.subTest(task_id=task_id, cik=company["cik"], cutoff=company["cutoff"]):
                with self.assertRaises(ValueError):
                    self.worker(bound, company, task_id)
        self.assertEqual(self.requests, [])


if __name__ == "__main__":
    unittest.main()
