import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from market_rsi import digest
from research_context import freeze_common
from study_state import StudyState
from test_coder_worker import SOURCE
from test_researcher_worker import proposal, task


ARMS = ("reset", "archive", "learn")


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.common = self.root / "common.json"
        freeze_common(self.common)
        self.tasks = [task(0), task(1), task(2, "transfer"), task(3, "transfer")]
        self.baselines = {t["task_id"]: "b" * 64 for t in self.tasks}
        self.study = StudyState.create(self.root / "study", common_manifest=self.common, tasks=self.tasks,
            baseline_source_hashes=self.baselines, max_steps_per_task=3,
            deadline_utc="2099-01-01T00:00:00+00:00", worst_case_step_seconds=300)
        self.counter = 0

    def tearDown(self):
        self.tmp.cleanup()

    def claimed(self, arm="learn", trial_id=None):
        self.counter += 1
        trial_id = trial_id or f"trial-{self.counter}"
        prepared = self.study.claim(arm, trial_id)
        return trial_id, prepared

    def completion(self, trial_id, prepared, *, p=None, eligible=False):
        p = {**proposal(), "action": "experiment"} if p is None else p
        return {"trial_id": trial_id, "research_packet_sha256": prepared["packet_sha256"],
            "raw_research_response": json.dumps(p), "eligible_submission": eligible,
            "evidence_commitments": {"synthetic_fixture": "a" * 64},
            "payload": {"proposal": p, "candidate_code": SOURCE,
                        "train_dev_results": {"dev": {"execution_verified": True,
                            "scientific_admission": True,
                            "numeric": {"aggregate": {"mse": 0.12}}}},
                        "usage": {"mock": True}, "failure": None}}

    def finish_step(self, arm="learn", *, p=None, eligible=False):
        trial_id, prepared = self.claimed(arm)
        self.study.complete(self.completion(trial_id, prepared, p=p, eligible=eligible))
        return trial_id

    def submit(self, arm, task_index, trial_id=None):
        submitted = {"arm": arm, "task_id": f"task-{task_index}", "trial_id": trial_id,
            "source_sha256": hashlib.sha256(SOURCE.encode()).hexdigest() if trial_id else self.baselines[f"task-{task_index}"],
            "selection_evidence_sha256": "c" * 64}
        self.study.submit_task(submitted)
        return submitted

    def finish_task(self, arm, index):
        self.finish_step(arm)
        self.submit(arm, index)

    def finish_learning(self):
        for arm in ARMS:
            for index in (0, 1):
                self.finish_task(arm, index)
        return self.study.freeze_learning()

    def public(self, arm):
        return json.loads(self.study.next_request(arm)["messages"][1]["content"])

    def test_same_initial_input_all_arms(self):
        requests = [self.study.next_request(arm) for arm in ARMS]
        self.assertEqual(len({digest(r["messages"]) for r in requests}), 1)
        self.assertFalse(self.study.snapshot()["scientific_admission"])

    def test_restart_preserves_active_claim_and_blocks_all_duplicate_dispatch(self):
        trial, prepared = self.claimed()
        restarted = StudyState(self.study.root)
        self.assertEqual(restarted.snapshot()["active"]["prepared"], prepared)
        self.assertEqual(restarted.snapshot()["active"]["trial_id"], trial)
        for arm in ARMS:
            with self.assertRaises(ValueError):
                restarted.claim(arm, "second-dispatch")
        with self.assertRaises(ValueError):
            restarted.next_request("learn")

    def test_trial_id_cannot_be_reused_even_after_completion(self):
        trial = self.finish_step()
        with self.assertRaises(ValueError):
            self.study.claim("archive", trial)

    def test_three_step_allowance_enforced(self):
        for _ in range(3):
            self.finish_step()
        with self.assertRaises(ValueError):
            self.claimed()
        self.assertEqual(self.study.snapshot()["records_by_arm"]["learn"], 3)

    def test_one_diagnostic_does_not_consume_two_candidate_attempts(self):
        other = StudyState.create(self.root / "study-with-diagnostics",
            common_manifest=self.common, tasks=self.tasks,
            baseline_source_hashes=self.baselines, max_steps_per_task=2,
            max_diagnostics_per_task=1,
            max_research_calls_per_task=4,
            deadline_utc="2099-01-01T00:00:00+00:00", worst_case_step_seconds=300)

        trial, prepared = "diagnostic-1", other.claim("learn", "diagnostic-1")
        other.complete(self.completion(trial, prepared, p=proposal()))
        public = json.loads(other.next_request("learn")["messages"][1]["content"])
        self.assertEqual(public["remaining_attempts"], {
            "scoreable_candidates_remaining": 2, "diagnostic_attempts_remaining": 0,
            "research_calls_remaining": 3})

        for index in range(2):
            trial = f"candidate-{index}"
            prepared = other.claim("learn", trial)
            other.complete(self.completion(trial, prepared,
                p={**proposal(), "action": "experiment"}, eligible=True))
        with self.assertRaises(ValueError):
            other.next_request("learn")
        selected = other.claim_selection("learn", "selection-after-two-candidates")
        self.assertEqual(selected["audit"]["step_index"], 3)

    def test_failed_call_does_not_fill_candidate_slot_but_call_cap_still_bounds_task(self):
        other = StudyState.create(self.root / "study-with-replacement",
            common_manifest=self.common, tasks=self.tasks,
            baseline_source_hashes=self.baselines, max_steps_per_task=2,
            max_diagnostics_per_task=1, max_research_calls_per_task=4,
            deadline_utc="2099-01-01T00:00:00+00:00", worst_case_step_seconds=300)

        trial, prepared = "invalid-1", other.claim("learn", "invalid-1")
        failed = self.completion(trial, prepared)
        failed["raw_research_response"] = "invalid output"
        failed["payload"]["proposal"] = None
        failed["payload"]["failure"] = {"stage": "research", "kind": "invalid_response"}
        other.complete(failed)
        public = json.loads(other.next_request("learn")["messages"][1]["content"])
        self.assertEqual(public["remaining_attempts"]["scoreable_candidates_remaining"], 2)
        self.assertEqual(public["remaining_attempts"]["research_calls_remaining"], 3)

        for index in range(2):
            trial = f"scored-{index}"
            prepared = other.claim("learn", trial)
            other.complete(self.completion(trial, prepared,
                p={**proposal(), "action": "experiment"}, eligible=True))
        with self.assertRaises(ValueError):
            other.next_request("learn")
        other.claim_selection("learn", "selection-after-replacement")

    def test_reset_keeps_current_task_but_drops_earlier_task_memory(self):
        trial = self.finish_step("reset")
        self.assertEqual([r["trial_id"] for r in self.public("reset")["records"]], [trial])
        self.submit("reset", 0)
        self.assertEqual(self.public("reset")["records"], [])

    def test_archive_keeps_own_past_records_without_other_arm(self):
        trial = self.finish_step("archive")
        self.submit("archive", 0)
        other = self.finish_step("learn")
        records = self.public("archive")["records"]
        self.assertEqual([r["trial_id"] for r in records], [trial])
        self.assertNotIn(other, str(records))

    def test_learn_guide_comes_from_valid_response_with_prior_owned_evidence(self):
        first = self.finish_step()
        p = {**proposal(), "action": "experiment"}
        p["guide_update"] = {"text": "Check the timing field before fitting.", "evidence_trial_ids": [first]}
        self.finish_step(p=p)
        guide = self.public("learn")["research_guide"]
        self.assertEqual(guide["text"], p["guide_update"]["text"])
        self.assertEqual(guide["evidence_trial_ids"], [first])
        self.submit("learn", 0)
        self.assertEqual(self.public("learn")["research_guide"], guide)

    def test_guide_cannot_cite_current_or_other_arm_unseen_result(self):
        self.finish_step()
        trial, prepared = self.claimed()
        p = proposal()
        p["guide_update"] = {"text": "Unseen claim", "evidence_trial_ids": [trial]}
        with self.assertRaises(ValueError):
            self.study.complete(self.completion(trial, prepared, p=p))
        self.assertEqual(self.study.snapshot()["active"]["trial_id"], trial)

    def test_archive_cannot_get_a_guide(self):
        prior = self.finish_step("archive")
        trial, prepared = self.claimed("archive")
        p = proposal()
        p["guide_update"] = {"text": "No archive guide", "evidence_trial_ids": [prior]}
        with self.assertRaises(ValueError):
            self.study.complete(self.completion(trial, prepared, p=p))

    def test_hidden_outcome_fields_rejected(self):
        trial, prepared = self.claimed()
        c = self.completion(trial, prepared)
        c["payload"]["train_dev_results"]["test"] = {"mse": .001}
        with self.assertRaises(ValueError):
            self.study.complete(c)

    def test_completion_is_bound_to_original_packet(self):
        trial, prepared = self.claimed()
        c = self.completion(trial, prepared)
        c["research_packet_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.study.complete(c)

    def test_invalid_response_counts_as_failure_not_rewritten_proposal(self):
        trial, prepared = self.claimed()
        c = self.completion(trial, prepared)
        c["raw_research_response"] = "invalid output"
        c["payload"]["proposal"] = None
        c["payload"]["failure"] = {"stage": "research", "kind": "invalid_response"}
        self.study.complete(c)
        record = self.public("learn")["records"][0]
        self.assertEqual(record["payload"]["failure"]["kind"], "invalid_response")
        self.assertIsNone(record["payload"]["proposal"])

    def test_completion_cannot_be_repeated(self):
        trial, prepared = self.claimed()
        c = self.completion(trial, prepared)
        self.study.complete(c)
        with self.assertRaises(ValueError):
            self.study.complete(c)

    def test_task_cannot_be_silently_skipped(self):
        with self.assertRaises(ValueError):
            self.submit("learn", 0)

    def test_only_own_task_eligible_candidate_or_common_baseline_can_be_submitted(self):
        own = self.finish_step(p=dict(proposal(), action="experiment"), eligible=True)
        other = self.finish_step("archive", p=dict(proposal(), action="experiment"), eligible=True)
        with self.assertRaises(ValueError):
            self.submit("learn", 0, other)
        self.submit("learn", 0, own)
        self.assertEqual(self.study.snapshot()["submitted_by_arm"]["learn"], 1)

    def test_inspection_cannot_be_claimed_as_predictor_submission(self):
        trial, prepared = self.claimed()
        with self.assertRaises(ValueError):
            self.study.complete(self.completion(trial, prepared, p=proposal(), eligible=True))

    def test_all_learning_arms_must_complete_before_transfer(self):
        self.finish_task("learn", 0)
        self.finish_task("learn", 1)
        with self.assertRaises(ValueError):
            self.study.next_request("learn")
        with self.assertRaises(ValueError):
            self.study.freeze_learning()

    def test_freeze_uses_last_state_once_without_selecting_best_guide(self):
        frozen = self.finish_learning()
        self.assertEqual(len(frozen["record_hashes"]["learn"]), 2)
        self.assertTrue(self.study.snapshot()["learning_frozen"])
        with self.assertRaises(ValueError):
            self.study.freeze_learning()
        self.assertEqual(self.public("learn")["task"]["phase"], "transfer")
        self.assertFalse(self.public("learn")["can_revise_guide"])

    def test_prior_transfer_experience_does_not_reach_later_transfer_task(self):
        self.finish_learning()
        trial = self.finish_step()
        self.assertIn(trial, str(self.public("learn")["records"]))
        self.submit("learn", 2)
        self.assertNotIn(trial, str(self.public("learn")["records"]))
        self.assertEqual(len(self.public("learn")["records"]), 2)

    def test_all_final_submissions_required_before_seal_and_no_more_research_after(self):
        self.finish_learning()
        with self.assertRaises(ValueError):
            self.study.freeze_transfer()
        for arm in ARMS:
            for index in (2, 3):
                self.finish_task(arm, index)
        frozen = self.study.freeze_transfer()
        self.assertTrue(frozen["ordering_ready"])
        self.assertFalse(frozen["scientific_admission"])
        for arm in ARMS:
            with self.assertRaises(ValueError):
                self.study.next_request(arm)
        with self.assertRaises(ValueError):
            self.study.freeze_transfer()

    def test_deadline_blocks_new_claim_without_hiding_existing_status(self):
        with patch("study_state.time.time", return_value=10**12):
            with self.assertRaises(TimeoutError):
                self.claimed()
        self.assertIsNone(self.study.snapshot()["active"])

    def test_manifest_mutation_rejected(self):
        p = self.study.root / "manifest.json"
        value = json.loads(p.read_text())
        value["max_steps_per_task"] = 300
        p.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            self.study.snapshot()

    def test_completed_payload_mutation_rejected(self):
        trial = self.finish_step()
        p = self.study.root / "steps" / trial / "completion.json"
        value = json.loads(p.read_text())
        value["payload"]["train_dev_results"] = {"dev": {"human_hint": "changed"}}
        p.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            self.study.snapshot()

    def test_hidden_score_event_not_supported_even_with_valid_journal_chain(self):
        with self.study.journal.locked():
            self.study.journal.append("hidden_score", {"score": .99})
        with self.assertRaises(ValueError):
            self.study.snapshot()

    def test_nonfinite_completion_never_creates_partial_permanent_file(self):
        trial, prepared = self.claimed()
        c = self.completion(trial, prepared)
        c["payload"]["train_dev_results"]["dev"]["bad"] = float("nan")
        with self.assertRaises(ValueError):
            self.study.complete(c)
        self.assertFalse((self.study.root / "steps" / trial / "completion.json").exists())

    def test_recover_durable_completion_without_new_model_request_or_file_rewrite(self):
        trial, prepared = self.claimed()
        c = self.completion(trial, prepared)
        with patch.object(self.study.journal, "append", side_effect=OSError("synthetic crash before append")):
            with self.assertRaises(OSError):
                self.study.complete(c)
        completed = self.study.root / "steps" / trial / "completion.json"
        raw = completed.read_bytes()
        reopened = StudyState(self.study.root)
        self.assertEqual(reopened.snapshot()["active"]["trial_id"], trial)
        reopened.recover_completion(trial)
        self.assertIsNone(reopened.snapshot()["active"])
        self.assertEqual(reopened.snapshot()["records_by_arm"]["learn"], 1)
        self.assertEqual(raw, completed.read_bytes())
        with self.assertRaises(ValueError):
            reopened.recover_completion(trial)

    def test_two_supervisor_instances_cannot_claim_simultaneously(self):
        def claim(arm):
            instance = StudyState(self.study.root)
            try:
                instance.claim(arm, "concurrent-" + arm)
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            accepted = list(pool.map(claim, ("learn", "archive")))
        self.assertEqual(sum(accepted), 1)
        self.assertIsNotNone(self.study.snapshot()["active"])


if __name__ == "__main__":
    unittest.main()
