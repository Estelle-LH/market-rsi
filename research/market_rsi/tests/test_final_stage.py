"""All final-stage data, calls and cloud receipts here are fabricated fixtures."""
import copy
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import unittest
from unittest.mock import patch

import final_stage
from final_stage import FinalStage
from market_rsi import digest, fresh_json
from market_scoring import utc_date
from prediction_stream import encoded
from study_state import StudyState
from study_runner import StudyRunner
from test_coder_worker import SOURCE, LIMITS
import test_market_scoring as numeric_fixtures
import test_study_runner as runner_fixtures


class FinalTests(unittest.TestCase):
    def setUp(self):
        self.fx = runner_fixtures.RunnerTests()
        self.fx.setUp()
        self.root, self.budget = self.fx.root, self.fx.budget

    def tearDown(self):
        self.fx.tearDown()

    def context(self, change_hidden=None):
        self.hidden, self.baselines = {}, {}
        for task in self.fx.tasks:
            if task["phase"] != "transfer":
                continue
            index, tid = task["task_index"], task["task_id"]
            rows = numeric_fixtures.rows(day=4+index, market=f"hidden-m-{index}", game=f"hidden-g-{index}")
            rows[0]["features"]["x"] = .1
            spec = numeric_fixtures.spec(sessions=(utc_date(rows[0]["decision_ms"]),))
            obj = {"schema": "market_hidden_transfer_v1", "experiment_id": "fixture-research", "task_id": tid,
                   "materialized": rows, "score_spec": asdict(spec)}
            if change_hidden:
                change_hidden(obj)
            path = self.root / (tid + "-hidden.json")
            path.write_bytes(encoded(obj))
            self.hidden[tid] = path
            task["opaque_test_commitment"] = hashlib.sha256(path.read_bytes()).hexdigest()
            path = self.root / (tid + "-baseline.py")
            path.write_text(SOURCE)
            self.baselines[tid] = path
        self.study = StudyState.create(self.root / "study", common_manifest=self.fx.common,
            tasks=self.fx.tasks, baseline_source_hashes={t["task_id"]: hashlib.sha256(SOURCE.encode()).hexdigest() for t in self.fx.tasks},
            max_steps_per_task=1, deadline_utc="2099-01-01T00:00:00+00:00", worst_case_step_seconds=360)
        self.runner = StudyRunner.create(self.root / "runner", self.study, self.budget,
            runtime=self.fx.runtime, coder_limits=LIMITS, coder_identity=self.fx.identity,
            task_data=self.fx.task_data, live=False)
        return self.runner

    def seal(self, choose_candidate=False):
        for _ in range(30):
            action = self.runner.next_action()
            if action["action"] == "research_closed":
                return
            if action["action"].startswith("freeze_"):
                self.runner.tick(); continue
            rt, ct = self.fx.transports()
            if action["action"] == "selection":
                candidate = f"candidate-task-{action['task_index']:03d}-{action['arm']}-step-00"
                rt.text = json.dumps({"selected_candidate_id": candidate if choose_candidate else "baseline",
                    "reason": "Human fixture selection only", "evidence_trial_ids": []})
            self.runner.tick(rt, ct, fixture_execute=self.fx.execute_fixture)
        self.fail("fixture did not reach its seal")

    def create(self):
        return FinalStage.create(self.runner, hidden_paths=self.hidden, baseline_paths=self.baselines)

    def finish(self, stage):
        for _ in range(8):
            self.assertEqual(stage.tick(fixture_execute=self.fx.execute_fixture)["action"], "completed")
        self.assertEqual(stage.tick()["action"], "ready_for_score")

    def test_cannot_read_any_hidden_file_before_all_submissions_seal(self):
        self.context()
        with patch.object(final_stage, "_bytes", wraps=final_stage._bytes) as reads:
            with self.assertRaisesRegex(ValueError, "must seal"):
                self.create()
        reads.assert_not_called()
        self.assertFalse((self.study.root / "final-evaluation").exists())

    def test_complete_paired_report_is_synthetic_and_never_changes_research_memory(self):
        self.context(); self.seal()
        old_journal = self.study.journal.path.read_bytes()
        before = self.study.snapshot()
        stage = self.create()
        self.finish(stage)
        result = stage.score()
        self.assertEqual(result["planned_executions"], 8)
        self.assertEqual(result["verified_executions"], 8)
        self.assertTrue(result["synthetic"])
        self.assertFalse(result["scientific_admission"])
        self.assertFalse(result["researcher_feedback"])
        self.assertFalse(result["promotion"])
        self.assertIsNone(result["net_pnl"])
        self.assertEqual(set(result["tasks"]), {"task-2", "task-3"})
        for task in result["tasks"].values():
            self.assertEqual(task["learn_vs_archive"]["equal_session_delta_mse"], 0)
            self.assertIsNone(task["learn_vs_archive"]["net_pnl"])
        self.assertEqual(self.study.snapshot(), before)
        self.assertEqual(self.study.journal.path.read_bytes(), old_journal)
        with self.assertRaisesRegex(ValueError, "single report"):
            stage.score()

    def test_selected_candidate_source_is_preserved_without_new_coding(self):
        self.context(); self.seal(choose_candidate=True)
        stage = self.create()
        plan = json.loads((stage.root / "plan.json").read_text())
        for job in plan["jobs"]:
            if job["arm"] != "baseline":
                self.assertIsNotNone(job["submitted"]["trial_id"])
            self.assertEqual(job["source"], SOURCE)
        count = self.fx.executions
        stage.tick(fixture_execute=self.fx.execute_fixture)
        self.assertEqual(self.fx.executions, count + 1)

    def test_no_hidden_labels_or_endpoints_in_uploaded_packet(self):
        self.context(); self.seal(); stage = self.create()
        plan = stage._load()[0]
        bundle = stage._bundle(plan, plan["jobs"][0])
        self.assertEqual(bundle["binding"]["purpose"], "sealed_final_only")
        self.assertFalse(bundle["binding"]["hidden_labels_uploaded"])
        for row in bundle["packet"]["evaluation"]:
            self.assertNotIn("target", row)
            self.assertNotIn("labels", row)
            self.assertNotIn("runner_endpoints", row)
            self.assertNotIn("label_available_ms", row)
        self.assertNotIn("score_spec", bundle["packet"])

    def test_different_or_added_hidden_tasks_rejected(self):
        self.context(); self.seal()
        self.hidden["extra-task"] = self.root / "not-read.json"
        with self.assertRaisesRegex(ValueError, "exact sealed transfer tasks"):
            self.create()

    def test_changed_hidden_bytes_or_baseline_rejected(self):
        self.context(); self.seal()
        self.hidden["task-2"].write_text("{}")
        with self.assertRaisesRegex(ValueError, "opaque commitment"):
            self.create()

    def test_changed_original_baseline_rejected_before_hidden_read(self):
        self.context(); self.seal()
        self.baselines["task-2"].write_text("def fit(x): return 999")
        with self.assertRaisesRegex(ValueError, "original source"):
            self.create()

    def test_hidden_game_overlap_with_public_experience_rejected(self):
        self.context(lambda x: x["materialized"][0].update(game_id="fixture-game-1"))
        self.seal()
        with self.assertRaisesRegex(ValueError, "overlap public"):
            self.create()

    def test_one_game_cannot_be_counted_as_two_hidden_tasks(self):
        self.context(lambda x: x["materialized"][0].update(game_id="one-hidden-game"))
        self.seal()
        with self.assertRaisesRegex(ValueError, "another final task"):
            self.create()

    def test_same_day_public_dev_is_not_earlier_hidden_test(self):
        def same_day(obj):
            obj["materialized"] = numeric_fixtures.rows(day=2, game="hidden", market="hidden")
            obj["materialized"][0]["features"]["x"] = .1
            obj["score_spec"]["sessions"] = ["1970-01-03"]
        self.context(same_day); self.seal()
        with self.assertRaisesRegex(ValueError, "prior experience/Dev"):
            self.create()

    def test_final_target_cannot_be_changed_after_research(self):
        self.context(lambda x: x["score_spec"].update(target="buy_yes_gross_price_change")); self.seal()
        with self.assertRaisesRegex(ValueError, "final metric"):
            self.create()

    def test_live_gate_blocks_even_after_valid_ordering_before_hidden_read(self):
        self.context(); self.seal()
        config, study, budget, manifest, state = self.runner._load()
        with patch.object(self.runner, "_load", return_value=(dict(config, live=True), study, budget, manifest, state)), \
                patch.object(final_stage, "_bytes", wraps=final_stage._bytes) as reads:
            with self.assertRaisesRegex(RuntimeError, "scientific admission"):
                self.create()
        reads.assert_not_called()

    def test_no_duplicate_final_batch_or_score_from_partial_execution(self):
        self.context(); self.seal(); stage = self.create()
        with self.assertRaises(FileExistsError):
            self.create()
        stage.tick(fixture_execute=self.fx.execute_fixture)
        with self.assertRaisesRegex(ValueError, "every planned final execution"):
            stage.score()

    def test_interrupted_execution_reconciles_without_another_sandbox(self):
        self.context(); self.seal(); stage = self.create()
        with patch.object(stage, "reconcile_pending", side_effect=RuntimeError("fixture interruption")):
            with self.assertRaises(RuntimeError):
                stage.tick(fixture_execute=self.fx.execute_fixture)
        count = self.fx.executions
        self.assertEqual(stage.tick()["action"], "reconcile_pending")
        stage.reconcile_pending()
        self.assertEqual(self.fx.executions, count)

    def test_missing_final_prediction_never_becomes_smaller_scored_mask(self):
        self.context(); self.seal(); stage = self.create()
        with patch.object(stage, "reconcile_pending", side_effect=RuntimeError("fixture interruption")):
            with self.assertRaises(RuntimeError):
                stage.tick(fixture_execute=self.fx.execute_fixture)
        job = stage._load()[2]
        (stage.root / "jobs" / job / "collected/predictions/complete.json").unlink()
        with self.assertRaises(ValueError):
            stage.reconcile_pending()
        self.assertEqual(stage.tick()["action"], "reconcile_pending")

    def test_cleanup_failure_is_not_completed_even_with_all_predictions(self):
        self.context(); self.seal(); stage = self.create()
        with patch.object(stage, "reconcile_pending", side_effect=RuntimeError("fixture interruption")):
            with self.assertRaises(RuntimeError):
                stage.tick(fixture_execute=self.fx.execute_fixture)
        job = stage._load()[2]
        path = stage.root / "jobs" / job / "cleanup-01.json"
        value = json.loads(path.read_text()); value["kill_acknowledged"] = False; path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "kill"):
            stage.reconcile_pending()

    def test_final_report_rechecks_previously_verified_inputs(self):
        self.context(); self.seal(); stage = self.create(); self.finish(stage)
        self.hidden["task-2"].write_text("{}")
        with self.assertRaises(ValueError):
            stage.score()

    def test_entire_final_batch_must_fit_budget_and_clock(self):
        self.context(); self.seal()
        self.budget.reserve("fixture-final-reserve", "final", "9", "e2b", "a"*64)
        with self.assertRaisesRegex(ValueError, "protected remainder"):
            self.create()
        self.budget.cancel_before_dispatch("fixture-final-reserve")
        deadline = datetime.fromisoformat("2099-01-01T00:00:00+00:00").timestamp()
        with patch.object(final_stage.time, "time", return_value=deadline - 500):
            with self.assertRaisesRegex(TimeoutError, "full planned final batch"):
                self.create()

    def test_validly_rewritten_diagnostics_after_completion_cannot_change_final_evidence(self):
        from diagnostic_channel import stderr_receipt
        self.context(); self.seal(); stage = self.create(); self.finish(stage)
        job = stage._load()[0]["jobs"][0]["job_id"]
        root = stage.root / "jobs" / job / "collected"
        path = root / "candidate-stderr.log"
        path.write_text("Later validly formatted candidate diagnostic, not the original evidence.")
        (root / "candidate-diagnostic.json").write_text(json.dumps(stderr_receipt(path)))
        with self.assertRaisesRegex(ValueError, "changed after completion"):
            stage.score()

    def test_later_metering_is_not_double_charged_or_used_to_replace_historical_receipts(self):
        self.context(); self.seal(); stage = self.create(); self.finish(stage)
        job = stage._load()[0]["jobs"][0]["job_id"]
        original = (stage.root / "jobs" / job / "verified-final.json").read_bytes()
        self.budget.settle_metered(job, "0.01", {"terminal": True, "fixture": True})
        self.budget.record_invoice(job, "0.012", "a" * 64)
        snapshot = self.budget.snapshot()
        stage.score()
        self.assertEqual(self.budget.snapshot(), snapshot)
        self.assertEqual((stage.root / "jobs" / job / "verified-final.json").read_bytes(), original)

    def test_final_report_transaction_recovers_without_more_execution(self):
        from market_rsi import Journal
        self.context(); self.seal(); stage = self.create(); self.finish(stage)
        count = self.fx.executions
        original = Journal.append
        def fail_append(journal, event, payload):
            if event == "scored":
                raise OSError("fixture report interruption")
            return original(journal, event, payload)
        with patch.object(Journal, "append", fail_append):
            with self.assertRaises(OSError):
                stage.score()
        saved = (stage.root / "result.json").read_bytes()
        result = stage.score()
        self.assertEqual(self.fx.executions, count)
        self.assertEqual((stage.root / "result.json").read_bytes(), saved)
        self.assertEqual(result["verified_executions"], 8)


if __name__ == "__main__":
    unittest.main()
