import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from earnings_feedback import project_feedback


class FeedbackProjectionTests(unittest.TestCase):
    def setUp(self):
        self.result = {"status": "COMPLETED_SCORED", "planned_targets": 5,
                       "scored_targets": 5, "points": 1.5, "turns": 3,
                       "tool_calls": 4, "wall_seconds": 12.5}
        self.score = {"score_out_of_5": 1.5, "target_count": 5, "prediction_count": 5,
                      "duplicate_prediction_ids": [], "unknown_prediction_ids": []}

    def project(self, result=None, score=None):
        return project_feedback(self.result if result is None else result,
            self.score if score is None else score, task_id="fixture-task", cik="fixture-company")

    def test_success_projects_aggregates_only_without_mutating_inputs(self):
        self.result.update(predictions=[{"predicted_value": "SECRET_PREDICTION"}],
                           qa_path="SECRET_LABEL_PATH", error_message="SECRET_ERROR")
        self.score.update(targets=[{"ground_truth": "SECRET_ANSWER"}],
                          nested={"expected_value": "SECRET_NESTED_LABEL"})
        before = copy.deepcopy((self.result, self.score))
        feedback = self.project()
        self.assertNotIn("SECRET_", json.dumps(feedback))
        self.assertEqual(feedback["prediction"], {"planned_targets": 5, "scored_targets": 5,
                                                  "score_out_of_5": 1.5})
        self.assertEqual((self.result, self.score), before)
        self.assertEqual(json.dumps(feedback, sort_keys=True), json.dumps(self.project(), sort_keys=True))

    def test_failure_keeps_all_five_targets_without_fabricated_score(self):
        failed = {"status": "FAILED_NO_RETRY", "planned_targets": 5, "scored_targets": 0,
                  "error_type": "BudgetStop", "error_message": "SECRET_VALUE"}
        feedback = project_feedback(failed, None, task_id="fixture-task", cik="fixture-company")
        self.assertEqual(feedback["prediction"], {"planned_targets": 5, "scored_targets": 0,
                                                  "score_out_of_5": None})
        self.assertEqual(feedback["execution"], {"status": "FAILED_NO_RETRY", "error_type": "BudgetStop"})
        with self.assertRaises(ValueError):
            project_feedback(failed, self.score, task_id="fixture-task", cik="fixture-company")

    def test_bad_denominator_status_coverage_and_points_refuse(self):
        for key, value in (("planned_targets", 4), ("scored_targets", 4),
                           ("planned_targets", 5.0), ("status", "STARTED"), ("points", 2),
                           ("points", True)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.project(dict(self.result, **{key: value}))
        for points in (True, "1.5", float("nan"), float("inf"), -1, 6):
            with self.subTest(points=points), self.assertRaises(ValueError):
                self.project(score=dict(self.score, score_out_of_5=points))
        for key, value in (("target_count", 4), ("prediction_count", 6),
                           ("duplicate_prediction_ids", ["T001"]), ("unknown_prediction_ids", ["T999"])):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.project(score=dict(self.score, **{key: value}))

    def test_execution_metadata_is_bounded_and_finite(self):
        for key, value in (("turns", True), ("turns", -1), ("tool_calls", "2"),
                           ("wall_seconds", float("nan")), ("wall_seconds", -1)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.project(dict(self.result, **{key: value}))


if __name__ == "__main__":
    unittest.main()
