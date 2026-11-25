"""I5 repaired-boundary probes; original REPLAN evidence is preserved separately.

All QA and worker predictions below are invented. The scorer is the unchanged
original code artifact, never real benchmark labels or a fabricated scoring rule.
Fixture TestCases are composed through module aliases to avoid double discovery.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

import edgar_forecast_audit as original
import earnings_capacity_task as earnings
from earnings_feedback import project_feedback
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_capacity_feedback_engine as common_fixture
import test_earnings_capacity_loop as earnings_fixture
import earnings_transport_fixture as transport


SCORER = Path("/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/earnings-overnight-20261012/exact-benchmark/scripts/edgar_forecast_bench.py")
SCORER_SHA256 = "00283f8dec7565ebf22d3fb232ca4e956d23c76ef2c2e3f40b8f8f65dc23b563"
TARGETS = [f"T{i:03d}" for i in range(1, 6)]
INVENTED_QA = {"targets": [{"target_id": target, "ground_truth_numeric": 100,
    "ground_truth_surface": "100", "unit_hint": "count",
    "scoring": {"mode": "absolute", "full_tolerance": 0, "half_tolerance": 0}}
    for target in TARGETS]}


def invented_predictions(value=100):
    return {"predictions": [{"target_id": target, "predicted_value": value}
                            for target in TARGETS]}


def arithmetic_worker_original(worker, slot):
    """Worker reads public numbers and emits an intentionally wrong sum; no score."""
    root = Path(slot)
    root.mkdir(parents=True, exist_ok=False)
    numbers = engine.read(worker.task.data)["numbers"]
    worker.state["records"].append({"public_data": worker.task.data, "values": numbers})
    worker.task.calls.append(worker)
    return {name: engine.save(root / f"{name}.json", value) for name, value in {
        "result": {"status": "completed", "prediction": sum(numbers) + 1},
        "state": worker.state,
        "consumption": {"pair": worker.pair, "parent_state": worker.parent,
                        "public_data": worker.task.data,
                        "messages": worker.context["messages"],
                        "tool_bounds": worker.context["tool_bounds"]}}.items()}


class I5ScoringFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.scorer, actual_hash = original.load_scorer(SCORER)
        self.assertEqual(actual_hash, SCORER_SHA256)
        self.earnings_fixture = None
        self.physical_calls = 0

    def common(self):
        fixture = common_fixture.CommonEngineTests(
            "test_sum_task_has_actual_scores_versions_state_and_completed_restore")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.setup_task("sum")
        return fixture

    def fixture(self):
        if self.earnings_fixture is None:
            fixture = earnings_fixture.CapacityLoopTests("test_no_roles_has_no_paid_default")
            fixture.setUp()
            self.addCleanup(fixture.doCleanups)
            self.earnings_fixture = fixture
        return self.earnings_fixture

    def write_case(self, fixture, worker, slot, *, payload=None, score_override=None,
                   status="COMPLETED_SCORED", malformed=False, two_turns=False):
        """Real original capture; malformed=True explicitly corrupts fixture completion."""
        slot = Path(slot)
        slot.mkdir(parents=True, exist_ok=False)
        payload = invented_predictions() if payload is None else payload
        calls = [0]
        def reply(request):
            self.physical_calls += 1
            calls[0] += 1
            if two_turns and calls[0] == 1:
                return {"status": "completed", "output": [{"type": "function_call",
                    "call_id": "invented-calculate", "name": "calculate",
                    "arguments": json.dumps({"expression": "100"})}]}
            return {"status": "completed", "output": [{"type": "message", "content": [
                {"type": "output_text", "text": json.dumps(payload)}]}]}
        if malformed:
            with self.assertRaises(ValueError):
                transport.run_forecast(fixture, worker, slot, reply)
            # The real forecaster refuses this raw final. Adversarial worker completion
            # below is explicitly corrupted fixture data, not a successful forecast.
            worker.finish(slot)
            engine.save(slot / "predictions.json", payload)
            result = {"turns": calls[0], "tool_calls": worker.calls,
                      "wall_seconds": 0, "corrupted_fixture_completion": True}
        else:
            result = transport.run_forecast(fixture, worker, slot, reply)
        raw = engine.pin(slot / f"{calls[0]:02d}-response.json")
        predictions = engine.pin(slot / "predictions.json")
        actual = transport.score_payload(fixture.envelope["evaluation_kernel"], slot)
        retained_score = actual if score_override is None else score_override
        result.update(status=status, planned_targets=5,
                      scored_targets=5 if status == "COMPLETED_SCORED" else 0)
        if status == "COMPLETED_SCORED":
            result["points"] = retained_score["score_out_of_5"]
        else:
            result["error_type"] = "InventedFailure"
        output = {"result": engine.save(slot / "result.json", result),
                  "score": engine.save(slot / "score.json", retained_score)}
        return output, actual, raw, predictions

    def case(self, label, *, payload=None, score_override=None, status="COMPLETED_SCORED",
             malformed=False, two_turns=False):
        fixture = self.fixture()
        task = earnings.EarningsTask()
        task.preflight(fixture.envelope)
        pair = digest(fixture.native.batch.snapshot()["micro_evolution"]["active_pair"])
        worker = task.worker(fixture.envelope, fixture.native.restore(), pair,
                             fixture.envelope["initial_state"])
        slot = fixture.root / label
        output, actual, raw, predictions = self.write_case(fixture, worker, slot,
            payload=payload, score_override=score_override, status=status,
            malformed=malformed, two_turns=two_turns)
        return task, worker, slot, output, actual, raw, predictions

    def test_common_engine_scores_wrong_worker_original_outside_role(self):
        fixture = self.common()
        originals = []
        def execute(worker, slot):
            output = arithmetic_worker_original(worker, slot)
            originals.append(output)
            return output
        services = dict(fixture.services(), execute=execute)
        outcome = engine.run(fixture.bound, fixture.native.restore(), fixture.task, services=services)
        self.assertEqual((outcome["status"], outcome["completed_rounds"]), ("completed", 2))
        self.assertTrue(all(set(output) == {"result", "state", "consumption"} for output in originals))
        self.assertEqual(engine.read(originals[0]["result"])["prediction"], 10)
        self.assertEqual(engine.read(fixture.task.expected)["answer"], 9)
        self.assertEqual(fixture.packets[1]["feedback"]["observed"], {"squared_error": 1})
        self.assertEqual(outcome["result"]["feedback"]["observed"], {"squared_error": 1})
        self.assertFalse(outcome["result"]["claims"]["learning"])

    def test_completed_original_scorer_output_is_aggregate_only(self):
        task, worker, slot, output, actual, raw, predictions = self.case("completed")
        strict = earnings.e.strict_predictions(engine.read(raw), TARGETS)
        self.assertEqual(strict, engine.read(predictions))
        self.assertEqual(actual["score_out_of_5"], 5)
        accepted = task.execution(output, worker, slot)
        self.assertIsNone(worker.capacity.batch.snapshot()["micro_evolution"]["pending"])
        # Direct execution is upstream of the engine's review/feedback handoff.
        # Supply its explicit no-proposal verdict without inventing an effect
        # receipt or bypassing original-scorer/trace diagnostic verification.
        feedback = task.feedback(dict(accepted, capacity_review="continue"), self.earnings_fixture.envelope)
        self.assertEqual(feedback["observation"]["prediction"],
                         {"planned_targets": 5, "scored_targets": 5, "score_out_of_5": 5})
        self.assertNotIn("ground_truth", json.dumps(feedback))
        self.assertNotIn("per_target", json.dumps(feedback))
        self.assertEqual(feedback["research_diagnostics"]["review"]["verdict"], "continue")
        self.assertEqual(feedback["research_diagnostics"]["review"]["reason"], "NOT_MEASURED")
        self.assertEqual(engine.read(output["score"]), actual)

    def test_failed_and_unknown_terminal_outputs_are_refused_without_rewrite(self):
        for label, status in (("failed", "FAILED_NO_RETRY"), ("unknown", "STARTED")):
            with self.subTest(status=status):
                task, worker, slot, output, _, _, _ = self.case(label, status=status)
                before = {name: Path(bound["path"]).read_bytes() for name, bound in output.items()}
                with self.assertRaisesRegex(RuntimeError, "Forecast failed once"):
                    task.execution(output, worker, slot)
                self.assertEqual(before, {name: Path(bound["path"]).read_bytes()
                                          for name, bound in output.items()})
        failed = engine.read(output["result"])
        failed.update(status="FAILED_NO_RETRY")
        projected = project_feedback(failed, None, task_id="invented-task", cik="invented-cik")
        self.assertEqual(projected["prediction"],
                         {"planned_targets": 5, "scored_targets": 0, "score_out_of_5": None})

    def test_duplicate_and_unknown_original_ids_cannot_be_feedback(self):
        for label, target_id, field in (("duplicate", "T001", "duplicate_prediction_ids"),
                                        ("unknown-id", "T999", "unknown_prediction_ids")):
            with self.subTest(target_id=target_id):
                payload = invented_predictions()
                payload["predictions"][-1]["target_id"] = target_id
                task, worker, slot, output, actual, raw, _ = self.case(
                    label, payload=payload, malformed=True)
                self.assertEqual(actual[field], [target_id])
                with self.assertRaises(ValueError):
                    earnings.e.strict_predictions(engine.read(raw), TARGETS)
                with self.assertRaisesRegex(ValueError, "Five unique IDs"):
                    task.execution(output, worker, slot)

    def test_wrong_slot_original_is_refused_even_with_valid_bytes_and_hash(self):
        task, worker, slot, output, actual, _, _ = self.case("declared-slot")
        outside = engine.save(self.earnings_fixture.root / "outside-score.json", actual)
        with self.assertRaisesRegex(ValueError, "outside declared role slot"):
            task.execution(dict(output, score=outside), worker, slot)
        self.assertEqual(engine.read(outside), actual)

    def test_corrupt_retained_score_stops_cold_engine_replay_before_worker(self):
        fixture = self.common()
        outcome = fixture.invoke_engine()
        retained = fixture.root / "episode/roles/forecast-2/score.json"
        original_hash = hashlib.sha256(retained.read_bytes()).hexdigest()
        retained.write_bytes(b'{"squared_error":999}\n')
        self.assertNotEqual(hashlib.sha256(retained.read_bytes()).hexdigest(), original_hash)
        before = (len(fixture.packets), len(fixture.task.calls))
        with self.assertRaises((ValueError, engine.driver.LoopHalted)):
            fixture.invoke_engine()
        self.assertEqual((len(fixture.packets), len(fixture.task.calls)), before)
        self.assertEqual(outcome["status"], "completed")

    def test_fake_score_matching_result_is_rejected_without_replacement(self):
        fake = self.scorer(predictions_payload=invented_predictions(100),
                           benchmark_qa_payload=deepcopy(INVENTED_QA))
        task, worker, slot, output, actual, raw, predictions = self.case(
            "consistent-forgery", payload=invented_predictions(200), score_override=fake)
        self.assertEqual(earnings.e.strict_predictions(engine.read(raw), TARGETS),
                         engine.read(predictions))
        self.assertEqual(actual["score_out_of_5"], 0)
        self.assertTrue(all(row["predicted_numeric"] == 200 for row in actual["per_target"]))
        before = {path.name: path.read_bytes() for path in slot.glob("*.json")}
        calls = self.physical_calls
        for _ in range(2):
            with self.assertRaisesRegex(ValueError, "Original scorer/result mismatch"):
                task.execution(output, worker, slot)
        self.assertEqual(self.physical_calls, calls)
        self.assertEqual(before, {path.name: path.read_bytes() for path in slot.glob("*.json")})
        print("I5_REPAIR_RAW=" + json.dumps({"invented_inputs_only": True,
            "original_scorer_sha256": SCORER_SHA256, "raw_response": engine.read(raw),
            "raw_predictions": engine.read(predictions), "result_original": engine.read(output["result"]),
            "retained_score_original": engine.read(output["score"]), "original_scorer_output": actual,
            "rejection": "Original scorer/result mismatch", "unchanged_originals": True,
            "additional_physical_calls": self.physical_calls-calls}, sort_keys=True), flush=True)


if __name__ == "__main__":
    unittest.main()
