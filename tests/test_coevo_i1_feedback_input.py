"""I1 adversarial synthetic checks; collect only these seven independent tests.

Fixture modules supply setup/helpers by composition, never inherited TestCases.
The earnings positive uses invented raw HTTP with the actual worker/scorer and
original trace verification; no real Controller/model/network calls occur.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import test_capacity_feedback_engine as fixtures
import test_earnings_capacity_forecast as earnings_fixture
from earnings_capacity_task import EarningsTask
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


class _FeedbackTask(fixtures.LocalTask):
    """Project independently computed output while preserving lineage checks."""

    def __init__(self, owner, *, tamper=None):
        super().__init__(owner, "sum")
        self.tamper = tamper
        self.seed_feedback_sha256 = None
        self.expected = engine.save(owner.root / "adversarial-scorer.json", {"answer": 5})

    def feedback(self, output, envelope):
        result = engine.read(output["result"])
        return {"task": self.kind, "observed": engine.read(output["score"]),
                "execution_summary": {"status": result["status"], "prediction": result["prediction"]}}

    def packet(self, envelope, ctx, selected_profiles, pair):
        value = super().packet(envelope, ctx, selected_profiles, pair)
        if ctx["round_index"] == 1:
            self.seed_feedback_sha256 = value["feedback_sha256"]
        elif self.tamper == "changed_body":
            value["feedback"]["observed"]["squared_error"] = 0
        elif self.tamper == "stale_digest":
            value["feedback_sha256"] = self.seed_feedback_sha256
        return value


class FeedbackInputInterfaceTests(unittest.TestCase):
    def generic_fixture(self, *, tamper=None):
        fixture = fixtures.CommonEngineTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.task = _FeedbackTask(fixture, tamper=tamper)
        fixture.envelope.update(mode="offline_replay", task_kind="sum", initial_state=fixture.task.initial)
        fixture.bound = engine.save(fixture.root / "i1-envelope.json", fixture.envelope)
        fixture.axes = ["continue", "continue"]
        return fixture

    @staticmethod
    def run_generic(fixture):
        return engine.run(fixture.bound, fixture.native.restore(), fixture.task, services={
            "controller": fixture.controller_role, "author": fixture.author_role,
            "review": fixture.review_role, "execute": fixture.execute_service})

    @staticmethod
    def previous_result(fixture):
        return engine.driver._read_pair(
            fixture.root / "episode/loop/round-0001-reconcile.done.json")["output"]

    def test_actual_nonzero_score_and_result_summary_reach_second_packet(self):
        fixture = self.generic_fixture()
        outcome = self.run_generic(fixture)
        self.assertEqual((outcome["status"], outcome["completed_rounds"]), ("completed", 2))
        # sum([10,-3,2])=9; trusted synthetic answer=5, hence (9-5)^2=16.
        actual = engine.read(engine.pin(Path(fixture.envelope["slots"][0]["forecast"]) / "score.json"))
        self.assertEqual(actual, {"squared_error": 16})
        self.assertEqual(fixture.packets[1]["feedback"], {
            "task": "sum", "observed": actual,
            "execution_summary": {"status": "completed", "prediction": 9}})
        self.assertEqual(fixture.packets[1]["feedback"], self.previous_result(fixture)["feedback"])

    def test_second_digest_commits_complete_previous_result_not_just_score(self):
        fixture = self.generic_fixture()
        self.run_generic(fixture)
        previous = self.previous_result(fixture)
        packet = fixture.packets[1]
        self.assertEqual(packet["feedback_sha256"], digest(previous))
        self.assertNotEqual(packet["feedback_sha256"], digest(previous["feedback"]))
        self.assertNotEqual(packet["feedback_sha256"], fixture.packets[0]["feedback_sha256"])
        self.assertEqual(packet["parent_pair_sha256"], previous["pair_sha256"])
        self.assertEqual(engine.read(engine.pin(fixture.root / "episode/packet-02.json")), packet)

    def assert_second_input_rejected(self, tamper):
        fixture = self.generic_fixture(tamper=tamper)
        with self.assertRaises(engine.driver.LoopHalted) as rejected:
            self.run_generic(fixture)
        self.assertIsInstance(rejected.exception.__cause__, ValueError)
        self.assertEqual(str(rejected.exception.__cause__), "Controller packet did not deliver exact parent feedback")
        self.assertEqual((len(fixture.packets), len(fixture.task.calls)), (1, 1))
        self.assertFalse((fixture.root / "episode/packet-02.json").exists())
        failed = json.loads((fixture.root / "episode/loop/round-0002-input.failed.json").read_text())
        self.assertEqual((failed["exception_type"], failed["retry_allowed"]), ("ValueError", False))

    def test_changed_second_score_body_with_copied_digest_is_rejected(self):
        self.assert_second_input_rejected("changed_body")

    def test_stale_first_digest_with_correct_second_body_is_rejected(self):
        self.assert_second_input_rejected("stale_digest")

    def test_changed_retained_score_bytes_are_rejected_before_another_controller(self):
        fixture = self.generic_fixture()
        self.run_generic(fixture)
        score_path = Path(fixture.envelope["slots"][0]["forecast"]) / "score.json"
        before = (len(fixture.packets), len(fixture.task.calls))
        # Synthetic temporary artifact corruption, never production source/data.
        score_path.write_text('{"squared_error": 0}\n')
        with self.assertRaises((ValueError, engine.driver.LoopHalted)):
            self.run_generic(fixture)
        self.assertEqual((len(fixture.packets), len(fixture.task.calls)), before)

    def earnings_projection(self, *, mismatched=False):
        if not mismatched:
            # A positive feedback claim now requires the actual accepted trace,
            # not an aggregate-only hand-made completion receipt. All provider
            # responses and financial inputs remain owned synthetic fixtures.
            fixture = earnings_fixture._ForecastFixture(self)
            worker = fixture.worker()
            payload = {"predictions": [{"target_id": f"T{i:03d}",
                        "predicted_value": 100 if i <= 2 else 200} for i in range(1, 6)]}
            raw = fixture.invoke(worker, replies=[fixture.research(), fixture.final(payload)])
            task = EarningsTask()
            task.kernel, task.state_api = fixture.kernel, worker.state_api
            accepted = task.execution(raw, worker, Path(fixture.slots[0]))
            self.assertIsNone(worker.capacity.batch.snapshot()["micro_evolution"]["pending"])
            # The generic engine adds this no-proposal verdict between execution
            # and feedback. This direct interface fixture supplies that stage
            # explicitly; it invents no review, adoption or measured benefit.
            output = dict(accepted, capacity_review="continue")
            return task, {"id": fixture.task_id, "cik": fixture.company["cik"]}, output
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        result = {"status": "COMPLETED_SCORED", "planned_targets": 5, "scored_targets": 5,
                  "points": 2.75, "turns": 4, "tool_calls": 7, "wall_seconds": 3.5,
                  "predictions": [{"value": "LABEL_SENTINEL_PREDICTION"}],
                  "qa_path": "LABEL_SENTINEL_PATH", "error_message": "LABEL_SENTINEL_ERROR"}
        score = {"score_out_of_5": 3, "target_count": 5,
                 "prediction_count": 5, "duplicate_prediction_ids": [], "unknown_prediction_ids": [],
                 "targets": [{"ground_truth": "LABEL_SENTINEL_GOLD"}],
                 "nested": {"expected_value": "LABEL_SENTINEL_NESTED"}}
        output = {"result": engine.save(root / "result.json", result),
                  "score": engine.save(root / "score.json", score)}
        task = EarningsTask()
        task.state_api = SimpleNamespace(tools=SimpleNamespace(files={"questions.md": "Synthetic five questions"}))
        envelope = {"id": "synthetic-i1", "cik": "CIK0000000001"}
        return task, envelope, output

    def test_earnings_task_projects_actual_aggregate_without_nested_labels(self):
        task, envelope, output = self.earnings_projection()
        originals = {bound["path"]: Path(bound["path"]).read_bytes() for bound in output["artifacts"]}
        feedback = task.feedback(output, envelope)
        previous = {"feedback": feedback, "state": output["state"],
                    "pair_sha256": output["consumed"]["pair_sha256"]}
        ctx = {"previous_result": previous, "previous_feedback_sha256": digest(previous)}
        profiles = {"R": {"axis": "R", "research_instructions": "", "reuse_facts": True},
                    "H": {"axis": "H", "read_chunk_limit": 20000, "search_hit_limit": 50}}
        packet = task.packet(envelope, ctx, profiles, previous["pair_sha256"])
        self.assertEqual(packet["feedback"], feedback)
        self.assertEqual(packet["feedback_sha256"], digest(previous))
        self.assertEqual(packet["feedback"]["observation"]["prediction"], {
            "planned_targets": 5, "scored_targets": 5, "score_out_of_5": 2})
        observed = packet["feedback"]["observation"]["execution"]
        actual = engine.read(output["result"])
        self.assertEqual(observed, {key: actual[key] for key in ("status", "turns", "tool_calls", "wall_seconds")})
        self.assertEqual((observed["status"], observed["turns"], observed["tool_calls"]),
                         ("COMPLETED_SCORED", 2, 2))
        self.assertEqual(packet["feedback"]["research_diagnostics"]["review"]["reason"], "NOT_MEASURED")
        self.assertEqual(packet["feedback"]["research_diagnostics"]["review"]["verdict"], "continue")
        self.assertNotIn("LABEL_SENTINEL_", json.dumps(packet))
        self.assertNotIn("ground_truth", json.dumps(packet))
        self.assertNotIn("per_target", json.dumps(packet))
        self.assertEqual({path: Path(path).read_bytes() for path in originals}, originals)

    def test_earnings_task_refuses_score_result_disagreement_before_packet(self):
        task, envelope, output = self.earnings_projection(mismatched=True)
        with self.assertRaisesRegex(ValueError, "Aggregate original score/result mismatch"):
            task.feedback(output, envelope)


if __name__ == "__main__":
    unittest.main()
