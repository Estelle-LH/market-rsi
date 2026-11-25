"""Seven additional I5 probes on real captured synthetic physical originals."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

import earnings_capacity_task as earnings
from supervisor_harness import capacity_feedback_engine as engine
import test_coevo_i5_scoring_feedback as i5


class I5ScoringFeedbackChildTests(unittest.TestCase):
    def setUp(self):
        self.probe = i5.I5ScoringFeedbackTests(
            "test_completed_original_scorer_output_is_aggregate_only")
        self.probe.setUp()
        self.addCleanup(self.probe.doCleanups)

    def case(self, name):
        return self.probe.case(name, two_turns=True)

    def refuse(self, case, pattern):
        task, worker, slot, output, *_ = case
        before = {path.name: path.read_bytes() for path in slot.glob("*.json")}
        calls = self.probe.physical_calls
        with self.assertRaisesRegex((ValueError, FileNotFoundError), pattern):
            task.execution(output, worker, slot)
        self.assertEqual(self.probe.physical_calls, calls)
        self.assertEqual(before, {path.name: path.read_bytes() for path in slot.glob("*.json")})

    def corrupt(self, path, body):
        """Deliberate temporary fixture corruption, never a retained production run."""
        Path(path).write_text(json.dumps(body, sort_keys=True) + "\n")

    def test_two_turn_positive_retains_kernel_and_all_physical_originals(self):
        case = self.case("positive-two-turn")
        task, worker, slot, output, actual, raw, predictions = case
        accepted = task.execution(output, worker, slot)
        bound = {row["path"]: row["sha256"] for row in accepted["artifacts"]}
        required = [slot/f"{turn:02d}-{suffix}.json" for turn in (1, 2)
                    for suffix in ("request", "response", "count")]
        required += [slot/"predictions.json", next(slot.glob("01-tool-*.json"))]
        required += [Path(row["path"]) for row in task.kernel.values()]
        self.assertTrue(all(str(path) in bound for path in required))
        self.assertEqual(engine.read(output["score"]), actual)
        self.assertEqual(earnings.e.strict_predictions(engine.read(raw), i5.TARGETS),
                         engine.read(predictions))
        self.assertIsNone(worker.capacity.batch.snapshot()["micro_evolution"]["pending"])
        # The normal engine supplies this no-proposal verdict after execution;
        # this direct boundary probe supplies the missing stage explicitly.
        feedback = task.feedback(dict(accepted, capacity_review="continue"), self.probe.fixture().envelope)
        self.assertEqual(feedback["observation"]["prediction"]["score_out_of_5"], 5)
        self.assertEqual(engine.read(output["result"])["tool_calls"], 1)
        self.assertNotIn("ground_truth", json.dumps(feedback))
        self.assertNotIn("per_target", json.dumps(feedback))
        self.assertEqual(feedback["research_diagnostics"]["review"]["verdict"], "continue")
        self.assertEqual(feedback["research_diagnostics"]["review"]["reason"], "NOT_MEASURED")
        self.assertNotIn(task.kernel["qa"]["path"], json.dumps(worker.context))

    def test_equal_aggregate_tampered_full_score_is_rejected(self):
        fake = self.probe.scorer(predictions_payload=i5.invented_predictions(),
                                benchmark_qa_payload=deepcopy(i5.INVENTED_QA))
        fake["per_target"][0]["scoring_detail"] = {"absolute_error": 999}
        case = self.probe.case("same-aggregate-corrupt-full-score",
                              score_override=fake, two_turns=True)
        self.assertEqual(engine.read(case[3]["result"])["points"], 5)
        self.refuse(case, "Original scorer/result mismatch")

    def test_missing_stale_and_wrong_target_kernel_is_refused(self):
        case = self.case("kernel-base")
        fixture = self.probe.fixture()
        for name in ("absent", "missing-qa", "stale-qa", "wrong-targets"):
            with self.subTest(name=name):
                envelope = deepcopy(fixture.envelope)
                if name == "absent":
                    envelope.pop("evaluation_kernel")
                    pattern = "Explicit protected scorer"
                elif name == "missing-qa":
                    envelope["evaluation_kernel"].pop("qa")
                    pattern = "Explicit protected scorer"
                elif name == "stale-qa":
                    envelope["evaluation_kernel"]["qa"]["sha256"] = "f"*64
                    pattern = "Bound artifact changed"
                else:
                    qa = deepcopy(i5.INVENTED_QA)
                    qa["targets"][-1]["target_id"] = "T999"
                    envelope["evaluation_kernel"]["qa"] = engine.save(
                        fixture.root/"wrong-target-qa.json", qa)
                    pattern = "Protected QA does not match"
                calls = self.probe.physical_calls
                with self.assertRaisesRegex(ValueError, pattern):
                    earnings.EarningsTask().preflight(envelope)
                self.assertEqual(self.probe.physical_calls, calls)
        self.assertEqual(case[4]["score_out_of_5"], 5)

    def test_missing_nonconsecutive_and_extra_turn_originals_are_refused(self):
        for name in ("request", "count", "response", "gap", "extra"):
            with self.subTest(name=name):
                case = self.case("turn-"+name)
                slot = case[2]
                if name in ("request", "count", "response"):
                    (slot/f"01-{name}.json").rename(slot/f"omitted-01-{name}.json")
                elif name == "gap":
                    (slot/"02-response.json").rename(slot/"03-response.json")
                else:
                    engine.save(slot/"03-response.json", engine.read(case[5]))
                self.refuse(case, "Exact consecutive physical turn originals")

    def test_saved_predictions_differing_from_strict_final_are_refused(self):
        case = self.case("prediction-mismatch")
        self.corrupt(case[2]/"predictions.json", i5.invented_predictions(200))
        self.refuse(case, "Saved predictions differ from raw original final response")

    def test_missing_wrong_id_and_unconsumed_tool_outputs_are_refused(self):
        for name in ("missing", "wrong-call", "lost-history"):
            with self.subTest(name=name):
                case = self.case("tool-"+name)
                slot = case[2]
                tool = next(slot.glob("01-tool-*.json"))
                if name == "missing":
                    tool.rename(slot/"omitted-tool.json")
                    pattern = "01-tool-"
                elif name == "wrong-call":
                    observed = engine.read(engine.pin(tool))
                    observed["call_id"] = "different-call"
                    self.corrupt(tool, observed)
                    pattern = "Original tool result does not close exact call"
                else:
                    request = engine.read(engine.pin(slot/"02-request.json"))
                    request["payload"]["input"] = [row for row in request["payload"]["input"]
                                                   if row.get("type") != "function_call_output"]
                    self.corrupt(slot/"02-request.json", request)
                    pattern = "Physical request lost selected capacity/state or prior outputs"
                self.refuse(case, pattern)

    def test_forged_full_score_halts_engine_without_second_controller_or_retry(self):
        fixture = self.probe.fixture()
        fixture.axes = ["continue", "continue"]
        forged = self.probe.scorer(predictions_payload=i5.invented_predictions(100),
                                  benchmark_qa_payload=deepcopy(i5.INVENTED_QA))
        originals = []
        def execute(worker, slot):
            fixture.executed.append(worker)
            output, *_ = self.probe.write_case(fixture, worker, slot,
                payload=i5.invented_predictions(200), score_override=forged, two_turns=True)
            originals.append(output)
            return output
        services = {"controller": fixture.controller_role, "author": fixture.author_role,
                    "review": fixture.review_role, "execute": execute}
        def run():
            return engine.run(fixture.bound, fixture.native.restore(), earnings.EarningsTask(),
                              services=services)
        with self.assertRaises(engine.driver.LoopHalted) as stopped:
            run()
        self.assertIsInstance(stopped.exception.__cause__, ValueError)
        self.assertIn("Original scorer/result mismatch", str(stopped.exception.__cause__))
        failure = engine.read(engine.pin(fixture.root/"episode/loop/round-0001-execute.failed.json"))
        self.assertEqual(failure["exception_type"], "ValueError")
        self.assertFalse(failure["retry_allowed"])
        calls = self.probe.physical_calls
        before = {name: Path(bound["path"]).read_bytes() for name, bound in originals[0].items()}
        with self.assertRaises(engine.driver.LoopHalted):
            run()
        self.assertEqual(self.probe.physical_calls, calls)
        self.assertEqual((len(fixture.packets), len(fixture.executed)), (1, 1))
        self.assertEqual(before, {name: Path(bound["path"]).read_bytes()
                                  for name, bound in originals[0].items()})
        for stage in ("execute", "result_review", "reconcile"):
            self.assertFalse((fixture.root/f"episode/loop/round-0001-{stage}.done.json").exists())


if __name__ == "__main__":
    unittest.main()
