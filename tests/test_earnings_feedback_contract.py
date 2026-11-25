"""Synthetic engineering checks of the actual driver, not financial forecasts.

Only the provider and trusted task handlers are fixtures. No production
earnings admission, scoring, accounting or R/H activation is simulated as real.
"""
from copy import deepcopy
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

# Match the source-checkout imports used by the inherited driver tests while
# keeping root unittest discovery independent of the caller's PYTHONPATH.
with patch.object(sys, "path", [str(Path(__file__).resolve().parents[1] /
                                  "research" / "market_rsi"), *sys.path]):
    from supervisor_harness import feedback_linked_loop as loop


class EarningsFeedbackContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.root = self.directory / "loop"
        if destination := os.environ.get("EARNINGS_TEST_ARTIFACT_DIR"):
            # Opt-in copies retain durable synthetic evidence for worker runs.
            self.addCleanup(shutil.copytree, self.directory,
                            Path(destination) / self._testMethodName)
        self.seed = {"task_id": "synthetic-earnings-five-targets-v1",
                     "cutoff": "2026-01-31", "status": "seed"}
        self.identities = {stage: {"fixture_handler": stage, "version": 1}
                           for stage in loop.STAGES}
        self.calls = []
        self.provider = Mock(side_effect=self.mock_forecast)
        self.handlers = {stage: self.handler(stage) for stage in loop.STAGES}
        self.admit = lambda context: True
        self.known_first_failure = False

    def mock_forecast(self, request):
        scale = 90 if request["recipe"]["strategy"] == "recheck-evidence" else 100
        return {"status": "succeeded", "predictions": [
            {"target_id": f"T{index:03d}", "predicted_value": scale * index,
             "unit": "synthetic USD million"} for index in range(1, 6)]}

    def handler(self, stage):
        def actual(context):
            self.calls.append((context["round_index"], stage))
            outputs = context["outputs"]
            if stage == "input":
                return {"feedback": context["previous_result"],
                        "feedback_sha256": context["previous_feedback_sha256"]}
            if stage == "controller":
                packet = outputs["input"]
                strategy = ("recheck-evidence" if packet["feedback"].get("decision")
                            == "REVISE" else "baseline")
                return {"recipe": {"strategy": strategy},
                        "consumed_feedback_sha256": packet["feedback_sha256"]}
            if stage == "implement":
                recipe = outputs["controller"]["recipe"]
                return {"effective_recipe": recipe, "recipe_sha256": loop.c._digest(recipe)}
            if stage == "source_review":
                return {"fixture_review": True}
            if stage == "execute":
                implementation = outputs["implement"]
                request = {"task_id": context["seed"]["task_id"],
                           "recipe": implementation["effective_recipe"],
                           "recipe_sha256": implementation["recipe_sha256"],
                           "feedback_sha256": context["previous_feedback_sha256"]}
                if self.known_first_failure and context["round_index"] == 1:
                    return {"status": "failed", "error": "synthetic known rejection",
                            "provider_calls": 0}
                return self.provider(request)
            if stage == "result_review":
                return {"fixture_reviewed_status": outputs["execute"]["status"]}
            return {"execution": outputs["execute"], "review": outputs["result_review"],
                    "decision": "REVISE" if context["round_index"] == 1 else "HOLD"}
        return actual

    def run_loop(self):
        return loop.run(self.root, self.handlers, seed=self.seed, admit=self.admit,
                        max_rounds=2, handler_identity=lambda: deepcopy(self.identities))

    def output(self, round_index, stage):
        return loop._read_pair(self.root / f"round-{round_index:04d}-{stage}.done.json")["output"]

    def snapshot(self):
        return {path.name: path.read_bytes() for path in self.root.glob("*.json")}

    def test_two_rounds_deliver_digest_and_execute_consumed_recipe(self):
        result = self.run_loop()
        self.assertEqual((result["status"], result["completed_rounds"]), ("completed", 2))
        self.assertEqual(self.calls, [(n, stage) for n in (1, 2) for stage in loop.STAGES])
        first = self.output(1, "reconcile")
        digest = loop.c._digest(first)
        self.assertEqual(self.output(2, "input"), {"feedback": first, "feedback_sha256": digest})
        self.assertEqual(self.output(2, "controller")["consumed_feedback_sha256"], digest)
        claim = loop.c._json((self.root / "round-0002-input.claim.json").read_bytes())
        self.assertEqual(claim["previous_feedback_sha256"], digest)
        self.assertEqual(self.provider.call_count, 2)
        request = self.provider.call_args_list[1].args[0]
        implementation = self.output(2, "implement")
        self.assertEqual(request["feedback_sha256"], digest)
        self.assertEqual(request["recipe"], implementation["effective_recipe"])
        self.assertEqual(request["recipe_sha256"], loop.c._digest(request["recipe"]))
        self.assertEqual(request["recipe"]["strategy"], "recheck-evidence")
        predictions = result["result"]["execution"]["predictions"]
        self.assertEqual([p["target_id"] for p in predictions], [f"T{i:03d}" for i in range(1, 6)])
        self.assertTrue(all(type(p["predicted_value"]) in (int, float)
                            and math.isfinite(p["predicted_value"]) for p in predictions))
        self.assertEqual(predictions[0]["predicted_value"], 90)
        self.assertEqual(self.output(1, "execute")["predictions"][0]["predicted_value"], 100)

    def test_denied_execution_has_no_claim_provider_call_or_downstream_stage(self):
        self.admit = lambda context: context["stage"] != "execute"
        result = self.run_loop()
        self.assertEqual(result, {"status": "stopped", "completed_rounds": 0,
                                  "round_index": 1, "stage": "execute"})
        self.assertEqual(self.calls, [(1, stage) for stage in loop.STAGES[:4]])
        self.provider.assert_not_called()
        self.assertFalse(list(self.root.glob("round-0001-execute.*.json")))

    def test_closed_initial_admission_does_not_create_loop(self):
        self.admit = lambda context: False
        self.assertEqual(self.run_loop(), {"status": "stopped", "completed_rounds": 0,
                                          "stage": "input"})
        self.assertEqual(self.calls, [])
        self.provider.assert_not_called()
        self.assertFalse(self.root.exists())

    def test_partial_resume_and_completed_replay_avoid_duplicate_provider_calls(self):
        self.admit = lambda context: context["stage"] != "execute"
        self.assertEqual(self.run_loop()["stage"], "execute")
        before = self.snapshot()
        self.calls.clear()
        self.admit = lambda context: True
        result = self.run_loop()
        self.assertEqual(self.calls, [(1, s) for s in loop.STAGES[4:]] +
                         [(2, s) for s in loop.STAGES])
        self.assertEqual(self.provider.call_count, 2)
        self.assertEqual({name: self.snapshot()[name] for name in before}, before)
        completed = self.snapshot()
        self.calls.clear()
        self.provider.reset_mock()
        self.admit = lambda context: False
        self.assertEqual(self.run_loop(), result)
        self.assertEqual(self.calls, [])
        self.provider.assert_not_called()
        self.assertEqual(self.snapshot(), completed)

    def test_uncertain_provider_failure_is_recorded_and_never_retried(self):
        self.provider.side_effect = RuntimeError("synthetic uncertain provider completion")
        with self.assertRaisesRegex(loop.LoopHalted, "no retry"):
            self.run_loop()
        self.assertEqual(self.provider.call_count, 1)
        failure = loop.c._json((self.root / "round-0001-execute.failed.json").read_bytes())
        self.assertEqual(failure["exception_type"], "RuntimeError")
        self.assertIs(failure["retry_allowed"], False)
        self.assertFalse((self.root / "round-0001-execute.done.json").exists())
        before = self.snapshot()
        self.calls.clear()
        self.provider.reset_mock(side_effect=True)
        self.provider.side_effect = self.mock_forecast
        with self.assertRaisesRegex(loop.LoopHalted, "closed to retry"):
            self.run_loop()
        self.assertEqual(self.calls, [])
        self.provider.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_known_failure_is_feedback_for_new_round_not_retry_of_failed_round(self):
        self.known_first_failure = True
        result = self.run_loop()
        first = self.output(1, "reconcile")
        self.assertEqual(first["execution"]["status"], "failed")
        self.assertEqual(first["review"]["fixture_reviewed_status"], "failed")
        self.assertEqual(self.output(2, "input")["feedback"], first)
        self.assertEqual(result["completed_rounds"], 2)
        self.assertEqual(self.provider.call_count, 1)
        self.assertEqual(self.provider.call_args.args[0]["recipe"]["strategy"], "recheck-evidence")
        self.assertEqual(self.calls.count((1, "execute")), 1)
        self.assertEqual(self.calls.count((2, "execute")), 1)

    def test_bound_seed_task_and_handler_identity_drift_block_resume(self):
        self.run_loop()
        before = self.snapshot()
        for changed in ("task_id", "cutoff", "handler"):
            with self.subTest(changed=changed):
                seed, identities = deepcopy(self.seed), deepcopy(self.identities)
                if changed == "handler":
                    self.identities["execute"]["version"] = 2
                else:
                    self.seed[changed] = "different-bound-value"
                self.calls.clear()
                self.provider.reset_mock()
                with self.assertRaisesRegex(loop.LoopHalted, "drift"):
                    self.run_loop()
                self.assertEqual(self.calls, [])
                self.provider.assert_not_called()
                self.assertEqual(self.snapshot(), before)
                self.seed, self.identities = seed, identities

    def test_nonfinite_provider_output_records_terminal_failure(self):
        for index, value in enumerate((float("nan"), float("inf"), -float("inf"))):
            with self.subTest(value=value):
                self.root = self.directory / f"nonfinite-{index}"
                self.provider.reset_mock()
                self.provider.side_effect = lambda request, value=value: {
                    "status": "succeeded", "predictions": [{"predicted_value": value}]}
                with self.assertRaisesRegex(loop.LoopHalted, "no retry"):
                    self.run_loop()
                self.assertEqual(self.provider.call_count, 1)
                self.assertTrue((self.root / "round-0001-execute.failed.json").exists())

    def test_generic_driver_has_no_earnings_output_schema_gate(self):
        # This passing gap demonstration must not be described as financial
        # validation: JSON-safe missing targets, booleans and strings are accepted.
        self.provider.side_effect = lambda request: {"status": "succeeded", "predictions": [
            {"target_id": "T001", "predicted_value": True},
            {"target_id": "T001", "predicted_value": "not a number"}]}
        result = self.run_loop()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["result"]["execution"]["predictions"]), 2)


if __name__ == "__main__":
    unittest.main()
