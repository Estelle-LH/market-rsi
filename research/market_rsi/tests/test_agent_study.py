import tempfile
import unittest
from pathlib import Path

from agent_study import ARMS, Study
from market_rsi import digest, load_json
from study_smoke import fixture_manifest, fixture_scores, fixture_usage, learn, run, submit_all


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "study"
        self.manifest = fixture_manifest()

    def create(self):
        return Study.create(self.root, self.manifest)

    def learned(self):
        study = self.create()
        learn(study, self.manifest)
        return study

    def ready(self):
        study = self.learned()
        study.freeze_researchers()
        return study

    def submission(self, request, status="valid"):
        return dict(initial_baseline_sha256=request["baseline_sha256"], predictor_sha256=digest("predictor"),
                    executor_receipt_sha256=digest("receipt"), status=status)

    def test_duplicate_claim_rejected(self):
        self.create()
        with self.assertRaises(FileExistsError):
            self.create()

    def test_no_live_claim_from_unfinished_adapter(self):
        self.manifest["evidence_class"] = "prospective"
        with self.assertRaisesRegex(ValueError, "not implemented"):
            self.create()

    def test_no_inherited_paid_budget(self):
        self.manifest["limits"]["new_external_usd"] = "300"
        with self.assertRaises(ValueError):
            self.create()

    def test_group_leakage_rejected(self):
        self.manifest["tasks"][-1]["group_ids"] = self.manifest["tasks"][0]["group_ids"]
        with self.assertRaisesRegex(ValueError, "reused"):
            self.create()

    def test_chronological_leakage_rejected(self):
        self.manifest["tasks"][0]["end_ms"] = 50000
        with self.assertRaisesRegex(ValueError, "predate"):
            self.create()

    def test_unknown_task_fields_rejected(self):
        self.manifest["tasks"][0]["hidden_labels"] = [1, 0]
        with self.assertRaises(ValueError):
            self.create()

    def test_common_agent_and_limits_all_arms(self):
        study = self.create()
        requests = [study.begin_episode("task-0", arm) for arm in ARMS]
        for request in requests:
            self.assertEqual(request["agent"], self.manifest["agent"])
            self.assertEqual(request["limits"], self.manifest["limits"])
            self.assertEqual(request["baseline"], requests[0]["baseline"])
            self.assertTrue(request["reset_downstream"])

    def test_public_request_has_no_internal_task_inventory(self):
        request = self.create().begin_episode("task-0", "reset")
        for key in ("tasks", "group_ids", "data_sha256", "scorer_sha256", "start_ms", "end_ms"):
            self.assertNotIn(key, request)
        self.assertFalse(request["hidden_test_access"])
        self.assertFalse(request["cross_arm_access"])

    def test_out_of_order_learning_rejected(self):
        with self.assertRaises(ValueError):
            self.create().begin_episode("task-1", "memory")

    def test_transfer_before_freeze_rejected(self):
        with self.assertRaises(ValueError):
            self.create().begin_episode("task-2", "memory")

    def test_freeze_before_all_learning_finished_rejected(self):
        with self.assertRaises(ValueError):
            self.create().freeze_researchers()

    def test_fixed_arm_cannot_store_memory(self):
        with self.assertRaisesRegex(ValueError, "does not carry"):
            self.create().update_memory("reset", "lesson", ["x"], digest("response"))

    def test_memory_requires_own_committed_experience(self):
        study = self.learned()
        with self.assertRaisesRegex(ValueError, "cross-arm"):
            study.update_memory("memory", "lesson", ["episode-task-1-memory_market"], digest("response"))

    def test_memory_lineage_and_unchanged_llm(self):
        study = self.learned()
        a = study._read("memory-memory-001.json")
        b = study._read("memory-memory-002.json")
        self.assertEqual(b["previous_sha256"], digest(a))
        self.assertEqual(b["core_sha256"], a["core_sha256"])
        self.assertNotEqual(b["text"], a["text"])
        self.assertEqual(study._latest_memory("reset")["generation"], 0)

    def test_no_post_freeze_memory_update(self):
        with self.assertRaisesRegex(ValueError, "frozen"):
            self.ready().update_memory("memory", "new", ["episode-task-1-memory"], digest("response"))

    def test_transfer_tasks_share_frozen_memory_not_checkpoints(self):
        study = self.ready()
        a = study.begin_episode("task-2", "memory")
        b = study.begin_episode("task-3", "memory")
        self.assertEqual(a["researcher_memory"], b["researcher_memory"])
        self.assertEqual(a["baseline"], b["baseline"])
        self.assertNotIn("checkpoint", a["researcher_memory"])

    def test_hidden_results_cannot_be_learning_feedback(self):
        study = self.ready()
        study.begin_episode("task-2", "memory")
        with self.assertRaisesRegex(ValueError, "transfer"):
            study.record_learning_feedback("task-2", "memory", dict(scope="train_dev_only"),
                                           fixture_usage(), digest("receipt"))

    def test_wrong_baseline_rejected(self):
        study = self.ready()
        request = study.begin_episode("task-2", "memory")
        submission = self.submission(request)
        submission["initial_baseline_sha256"] = digest("some other checkpoint")
        with self.assertRaisesRegex(ValueError, "baseline"):
            study.commit_submission("task-2", "memory", submission, fixture_usage())

    def test_early_hidden_score_open_rejected(self):
        with self.assertRaises(ValueError):
            self.ready().begin_scoring()

    def test_budget_overrun_rejected(self):
        study = self.ready()
        request = study.begin_episode("task-2", "memory")
        usage = fixture_usage()
        usage["tokens"] = 20001
        with self.assertRaisesRegex(ValueError, "cap"):
            study.commit_submission("task-2", "memory", self.submission(request), usage)

    def test_duplicate_hidden_open_rejected(self):
        study = self.ready()
        submit_all(study, self.manifest)
        study.begin_scoring()
        with self.assertRaises(FileExistsError):
            study.begin_scoring()

    def test_duplicate_submission_rejected(self):
        study = self.ready()
        request = study.begin_episode("task-2", "memory")
        study.commit_submission("task-2", "memory", self.submission(request), fixture_usage())
        with self.assertRaises(FileExistsError):
            study.commit_submission("task-2", "memory", self.submission(request), fixture_usage())

    def test_researcher_invalid_submission_kept_as_baseline(self):
        study = self.ready()
        for task in self.manifest["tasks"]:
            if task["phase"] == "transfer":
                for arm in ARMS:
                    request = study.begin_episode(task["id"], arm)
                    status = "researcher_invalid" if arm == "memory" else "valid"
                    study.commit_submission(task["id"], arm, self.submission(request, status), fixture_usage())
        study.begin_scoring()
        scores = fixture_scores(self.manifest)
        scores["task-2"]["arms"]["memory"] = .20
        with self.assertRaisesRegex(ValueError, "baseline fallback"):
            study.record_scores(scores, digest("receipt"))
        scores["task-2"]["arms"]["memory"] = .25
        result = study.record_scores(scores, digest("receipt"))
        self.assertEqual(result["mean_brier_gain"]["memory"], 0)
        self.assertEqual(result["task_count"], 2)

    def test_score_write_is_once_only(self):
        study = self.ready()
        submit_all(study, self.manifest)
        study.begin_scoring()
        study.record_scores(fixture_scores(self.manifest), digest("receipt"))
        with self.assertRaises(FileExistsError):
            study.record_scores(fixture_scores(self.manifest), digest("receipt"))

    def test_missing_task_not_dropped(self):
        study = self.ready()
        submit_all(study, self.manifest)
        study.begin_scoring()
        scores = fixture_scores(self.manifest)
        del scores["task-3"]
        with self.assertRaises(ValueError):
            study.record_scores(scores, digest("receipt"))

    def test_changed_evaluator_rejected(self):
        study = self.ready()
        submit_all(study, self.manifest)
        study.begin_scoring()
        scores = fixture_scores(self.manifest)
        scores["task-3"]["scorer_sha256"] = digest("changed scorer")
        with self.assertRaisesRegex(ValueError, "changed"):
            study.record_scores(scores, digest("receipt"))

    def test_infrastructure_unknown_blocks_headline(self):
        study = self.ready()
        for task in self.manifest["tasks"]:
            if task["phase"] == "transfer":
                for arm in ARMS:
                    request = study.begin_episode(task["id"], arm)
                    status = "infrastructure_failure" if (task["id"], arm) == ("task-2", "memory") else "valid"
                    study.commit_submission(task["id"], arm, self.submission(request, status), fixture_usage())
        study.begin_scoring()
        scores = fixture_scores(self.manifest)
        scores["task-2"]["arms"]["memory"] = None
        result = study.record_scores(scores, digest("receipt"))
        self.assertEqual(len(result["incomplete"]), 1)
        self.assertIsNone(result["paired_comparisons"]["memory_minus_reset"])
        self.assertIsNone(result["mean_brier_gain"]["memory"])

    def test_equal_task_weighting_and_paired_deltas(self):
        study = self.ready()
        submit_all(study, self.manifest)
        study.begin_scoring()
        scores = fixture_scores(self.manifest)
        scores["task-2"]["arms"].update(memory=.20, memory_market=.21)
        scores["task-3"]["arms"].update(memory=.22, memory_market=.23)
        result = study.record_scores(scores, digest("receipt"))
        self.assertAlmostEqual(result["paired_comparisons"]["memory_minus_reset"], .04)
        self.assertAlmostEqual(result["paired_comparisons"]["market_minus_memory"], -.01)
        self.assertFalse(result["prospective_claim"])
        self.assertFalse(result["llm_weight_learning_claim"])

    def test_mutated_memory_detected(self):
        study = self.learned()
        path = study.root / "memory-memory-002.json"
        path.write_text('{}')
        with self.assertRaisesRegex(ValueError, "changed"):
            study.freeze_researchers()

    def test_end_to_end_fixture_is_not_llm_evidence(self):
        run(self.root)
        summary = load_json(self.root / "smoke-summary.json")
        self.assertEqual(summary["actual_agent_calls"], 0)
        self.assertTrue(summary["scores_are_fabricated"])
        self.assertFalse(summary["learning_result_claim"])


if __name__ == "__main__":
    unittest.main()
