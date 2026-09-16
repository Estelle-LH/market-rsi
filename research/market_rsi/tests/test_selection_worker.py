import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from market_rsi import digest, fresh_json
from paid_budget import PaidBudget
from research_context import freeze_common
from selection_protocol import assess_selection
from selection_worker import dispatch_selection, build_selection_completion, commit_selection
from study_state import StudyState
from worker_receipts import read_research_job
from test_researcher_worker import FakeTransport, task, proposal


CODE = "def fit(train, feature_names):\n    pass\ndef predict(row):\n    return 0.0\n"


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.common = self.root / "common.json"
        freeze_common(self.common)
        self.budget = PaidBudget.create(self.root / "budget", {
            "experiment_id": "fixture-research", "cap_usd": "2", "target_usd": "1",
            "buckets_usd": {"learning": "1", "final": "1"}, "authority": "synthetic selection test"})
        self.study = StudyState.create(self.root / "study", common_manifest=self.common,
            tasks=[task(), task(1, "transfer"), task(2, "transfer")],
            baseline_source_hashes={f"task-{i}": "b" * 64 for i in range(3)}, max_steps_per_task=1,
            max_diagnostics_per_task=1, max_research_calls_per_task=1,
            deadline_utc="2099-01-01T00:00:00+00:00", worst_case_step_seconds=300)

    def tearDown(self):
        self.tmp.cleanup()

    def step(self, arm="learn", index=0, eligible=True):
        trial = f"{arm}-task{index}-step0"
        prepared = self.study.claim(arm, trial)
        value = dict(proposal(), action="experiment" if eligible else "inspect")
        # Fabricated independently verified completion for state/selection tests.
        # No code is executed and no research score is measured by this fixture.
        self.study.complete({"trial_id": trial, "research_packet_sha256": prepared["packet_sha256"],
            "raw_research_response": json.dumps(value), "eligible_submission": eligible,
            "evidence_commitments": {"fixture": "a" * 64}, "payload": {"proposal": value,
                "candidate_code": CODE if eligible else "def inspect(*args): return {}",
                "train_dev_results": {"dev": {"fixture": True, "mse": .1}},
                "usage": {"fixture": True}, "failure": None}})
        return trial

    def claim(self, arm="learn", index=0):
        job = f"select-{arm}-task{index}"
        prepared = self.study.claim_selection(arm, job)
        return prepared, self.root / "provider-jobs" / job

    def choose(self, arm="learn", index=0, candidate=None):
        prepared, directory = self.claim(arm, index)
        candidate = candidate or "candidate-" + f"{arm}-task{index}-step0"
        self.transport = FakeTransport(text=json.dumps({"selected_candidate_id": candidate,
            "reason": "fixture selection, not evidence of improvement", "evidence_trial_ids": []}))
        report = dispatch_selection(self.study, self.transport, self.budget, directory)
        built = build_selection_completion(self.study, directory, self.budget, expected_live=False)
        return prepared, directory, report, built

    def test_selects_only_owned_eligible_code_from_first_metered_response(self):
        trial = self.step()
        prepared, directory, report, built = self.choose()
        self.assertTrue(report["valid"])
        self.assertEqual(prepared["audit"]["response_kind"], "task_selection")
        self.assertFalse(prepared["audit"]["can_revise_guide"])
        public = json.loads(prepared["messages"][1]["content"])
        self.assertEqual([x["candidate_id"] for x in public["eligible_candidates"]], ["baseline", "candidate-" + trial])
        self.assertNotIn(str(self.root), json.dumps(public))
        self.assertNotIn("arm", public)
        commit_selection(self.study, built)
        with self.study.journal.locked():
            _, state = self.study._load()
        self.assertEqual(state["submissions"]["learn"][0]["trial_id"], trial)
        self.assertEqual(state["submissions"]["learn"][0]["source_sha256"], hashlib.sha256(CODE.encode()).hexdigest())
        self.assertEqual(state["records"]["learn"][-1]["payload"]["proposal"]["accepted_candidate_id"], "candidate-" + trial)
        self.assertEqual(self.transport.sample_count, 1)
        self.assertEqual(self.budget.snapshot()["reserved_usd"], "0")

    def test_invalid_or_foreign_candidate_falls_back_without_resampling(self):
        self.step()
        _, _, report, built = self.choose(candidate="candidate-other-arm")
        self.assertFalse(report["valid"])
        commit_selection(self.study, built)
        with self.study.journal.locked():
            _, state = self.study._load()
        self.assertIsNone(state["submissions"]["learn"][0]["trial_id"])
        self.assertTrue(state["records"]["learn"][-1]["payload"]["proposal"]["fallback"])
        self.assertEqual(self.transport.sample_count, 1)

    def test_inspection_is_not_selectable(self):
        self.step(eligible=False)
        prepared, _, _, built = self.choose(candidate="candidate-learn-task0-step0")
        self.assertEqual(len(prepared["audit"]["selection_candidates"]), 1)
        self.assertFalse(built["completion"]["terminal_worker_valid"])

    def test_invented_evidence_or_guide_update_is_invalid(self):
        self.step()
        prepared, _ = self.claim()
        answer = {"selected_candidate_id": "baseline", "reason": "fixture", "evidence_trial_ids": ["foreign"]}
        self.assertFalse(assess_selection(json.dumps(answer), prepared["audit"])["valid"])
        answer.update(evidence_trial_ids=[], guide_update={"text": "new instruction"})
        self.assertFalse(assess_selection(json.dumps(answer), prepared["audit"])["valid"])

    def test_selection_cannot_be_passed_to_coding(self):
        self.step()
        prepared, directory, _, _ = self.choose()
        with self.assertRaises(ValueError):
            read_research_job(directory, prepared, self.budget, expected_live=False)

    def test_no_choice_before_fixed_experiment_count(self):
        with self.assertRaises(ValueError):
            self.claim()

    def test_pending_selection_blocks_research_and_duplicate_selection(self):
        self.step()
        self.claim()
        with self.assertRaises(ValueError):
            self.study.claim("reset", "another-job")
        with self.assertRaises(ValueError):
            self.study.claim_selection("learn", "another-choice")
        reopened = StudyState(self.study.root)
        self.assertEqual(reopened.snapshot()["active"]["kind"], "selection")

    def test_duplicate_worker_dispatch_rejected(self):
        self.step()
        _, directory, _, _ = self.choose()
        other = FakeTransport()
        with self.assertRaises(FileExistsError):
            dispatch_selection(self.study, other, self.budget, directory)
        self.assertEqual(other.sample_count, 0)

    def test_wrong_output_id_rejected_before_model_call(self):
        self.step()
        self.claim()
        transport = FakeTransport()
        with self.assertRaises(ValueError):
            dispatch_selection(self.study, transport, self.budget, self.root / "other")
        self.assertEqual(transport.sample_count, 0)

    def test_unmetered_provider_failure_stays_held_and_pending(self):
        self.step()
        _, directory = self.claim()
        transport = FakeTransport(error=TimeoutError("fixture ambiguity"))
        with self.assertRaises(TimeoutError):
            dispatch_selection(self.study, transport, self.budget, directory)
        before = self.budget.snapshot()
        self.assertGreater(float(before["reserved_usd"]), 0)
        with self.assertRaises(ValueError):
            build_selection_completion(self.study, directory, self.budget, expected_live=False)
        self.assertIsNotNone(self.study.snapshot()["active"])
        self.assertEqual(before, self.budget.snapshot())

    def test_live_dispatch_stays_blocked_before_encode_or_reservation(self):
        self.step()
        _, directory = self.claim()
        transport = FakeTransport()
        transport.live = True
        with self.assertRaisesRegex(RuntimeError, "scientific admission"):
            dispatch_selection(self.study, transport, self.budget, directory)
        self.assertEqual(transport.encode_count, 0)
        self.assertFalse(directory.exists())
        self.assertFalse(self.budget.snapshot()["jobs"])

    def test_receipt_mutation_between_read_and_commit_rejected(self):
        self.step()
        _, directory, _, built = self.choose()
        fresh_json(directory / "failure.json", {"error_type": "late failure"})
        with self.assertRaises(ValueError):
            commit_selection(self.study, built)

    def test_selection_cannot_create_an_experiment_completion(self):
        self.step()
        self.claim()
        with self.assertRaises(ValueError):
            self.study.complete({"trial_id": "select-learn-task0", "research_packet_sha256": "x", "raw_research_response": "{}",
                "eligible_submission": False, "evidence_commitments": {"fixture": "a"*64}, "payload": {}})

    def test_all_phase_freezes_and_transfer_feedback_isolation_with_recorded_selections(self):
        for arm in ("reset", "archive", "learn"):
            self.step(arm)
            _, _, _, built = self.choose(arm)
            commit_selection(self.study, built)
        self.study.freeze_learning()
        for arm in ("reset", "archive", "learn"):
            self.step(arm, 1)
            prepared, _, _, built = self.choose(arm, 1)
            public = json.loads(prepared["messages"][1]["content"])
            self.assertTrue(all(r["task_index"] == 1 for r in public["records"]) if arm == "reset" else True)
            commit_selection(self.study, built)
        with self.assertRaises(ValueError):
            self.study.freeze_transfer()
        for arm in ("reset", "archive", "learn"):
            request = self.study.next_request(arm)
            history = json.loads(request["messages"][1]["content"])["records"]
            self.assertTrue(all(r["task_index"] == 0 for r in history))
            self.step(arm, 2)
            _, _, _, built = self.choose(arm, 2)
            commit_selection(self.study, built)
        final = self.study.freeze_transfer()
        self.assertTrue(final["research_closed"])
        self.assertFalse(final["scientific_admission"])

    def test_crash_after_durable_completion_recovers_without_another_response(self):
        self.step()
        _, _, _, built = self.choose()
        original = self.study.journal.append
        def fail_once(kind, payload):
            if kind == "selection_completed":
                raise OSError("fixture journal interruption")
            return original(kind, payload)
        with patch.object(self.study.journal, "append", side_effect=fail_once):
            with self.assertRaises(OSError):
                commit_selection(self.study, built)
        reopened = StudyState(self.study.root)
        for reads in built["read_sets"]:
            reads.revalidate()
        reopened.recover_selection("select-learn-task0")
        self.assertIsNone(reopened.snapshot()["active"])
        self.assertEqual(self.transport.sample_count, 1)
        with self.assertRaises(ValueError):
            reopened.recover_selection("select-learn-task0")

    def test_deadline_blocks_new_selection(self):
        self.step()
        with patch("study_state.time.time", return_value=4102444800):
            with self.assertRaises(TimeoutError):
                self.claim()


if __name__ == "__main__":
    unittest.main()
