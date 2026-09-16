"""End-to-end orchestration with fake providers and fake cloud receipts only."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import development_harbor
from market_rsi import digest, fresh_json
from paid_budget import PaidBudget
from prediction_stream import encoded
from research_context import freeze_common
from study_runner import StudyRunner
from step_deadline import LOCAL_OVERHEAD_SECONDS
from study_state import StudyState
import test_development_harbor as harbor_fixtures
from test_coder_worker import FakeCoder, LIMITS, SOURCE, RUNTIME
from test_researcher_worker import FakeTransport, task, proposal
from test_trial_inputs import PROFILE
from market_harbor import fixture_packet


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.common = self.root / "common.json"
        freeze_common(self.common)
        self.budget = PaidBudget.create(self.root / "budget", {"experiment_id": "fixture-research",
            "cap_usd": "20", "target_usd": "10", "buckets_usd": {"learning": "10", "final": "10"},
            "authority": "offline fabricated orchestration receipts only"})
        self.tasks = [task(i, "learning" if i < 2 else "transfer") for i in range(4)]
        self.task_data = {}
        packet = fixture_packet()
        dev = [dict(r, target=r["features"]["x"], label_available_ms=r["decision_ms"] + 60000)
               for r in packet["evaluation"]]
        for t in self.tasks:
            t["evaluation_contract"]["baseline_rule"] = "zero"
            mapping = {}
            for entry in t["data_catalog"]:
                split = entry["split"]
                data = encoded({"schema": "market_permitted_rows_v1", "experiment_id": "fixture-research",
                    "task_id": t["task_id"], "split": split, "feature_names": ["x"],
                    "rows": packet["train"] if split == "train" else dev})
                entry["sha256"] = hashlib.sha256(data).hexdigest()
                path = self.root / (t["task_id"] + "-" + split + ".json")
                path.write_bytes(data)
                mapping.update({split + "_id": entry["artifact_id"], split + "_path": str(path)})
            self.task_data[t["task_id"]] = mapping
        self.runtime = dict(copy.deepcopy(RUNTIME), execution_limits=copy.deepcopy(PROFILE))
        self.identity = {"authentication": "fixture", "model": "fixture"}
        self.executions = 0

    def tearDown(self):
        self.tmp.cleanup()

    def create(self, *, live=False, deadline="2099-01-01T00:00:00+00:00", step_bound=360):
        self.study = StudyState.create(self.root / "study", common_manifest=self.common,
            tasks=self.tasks, baseline_source_hashes={t["task_id"]: "b" * 64 for t in self.tasks},
            max_steps_per_task=1, deadline_utc=deadline, worst_case_step_seconds=step_bound)
        self.runner = StudyRunner.create(self.root / "runner", self.study, self.budget,
            runtime=self.runtime, coder_limits=LIMITS, coder_identity=self.identity,
            task_data=self.task_data, live=live)
        return self.runner

    def execute_fixture(self, bundle, root, budget):
        # Receipt fabrication only; source returned by FakeCoder is never run.
        self.executions += 1
        helper = harbor_fixtures.DevelopmentTests()
        helper.root = root
        helper.outputs(bundle)
        claim = development_harbor.verify_job(root)[0]
        bucket = "learning" if claim["phase"] == "learning" else "final"
        budget.reserve(root.name, bucket, "0.10", "e2b", digest(claim))
        budget.dispatch(root.name)
        sid = "fixture-owned-" + str(self.executions)
        fresh_json(root / "sandbox.json", {"sandbox_id": sid})
        start = datetime.now(timezone.utc)
        fresh_json(root / "runtime.json", {"sandbox_id": sid, "template_id": claim["template"],
            "cpu_count": 2, "memory_mb": 512, "allow_internet_access": False,
            "started_at": start.isoformat(), "expiry_at": (start + timedelta(seconds=240)).isoformat()})
        fresh_json(root / "cleanup-01.json", {"sandbox_id": sid, "kill_acknowledged": True})

    def transports(self):
        return (FakeTransport(text=json.dumps(dict(proposal(), action="experiment"))),
                FakeCoder({"status": "implemented", "code": SOURCE, "notes": "human fixture only"}))

    def test_full_three_arm_learning_and_transfer_loop_without_provider_or_candidate_execution(self):
        runner = self.create()
        seen, calls = [], []
        for _ in range(30):
            action = runner.next_action()
            seen.append(action)
            if action["action"] == "research_closed":
                break
            if action["action"].startswith("freeze_"):
                runner.tick()
                continue
            rt, ct = self.transports()
            if action["action"] == "selection":
                rt.text = json.dumps({"selected_candidate_id": "baseline", "reason": "fixture choice only",
                                      "evidence_trial_ids": []})
            elif action["arm"] == "learn" and action["task_index"] == 1:
                value = dict(proposal(), action="experiment", guide_update={
                    "text": "Fixture-only evidence-linked revision, not actual learning.",
                    "evidence_trial_ids": ["task-000-learn-step-00"]})
                rt.text = json.dumps(value)
            result = runner.tick(rt, ct, fixture_execute=self.execute_fixture)
            self.assertFalse(result["scientific_admission"])
            calls.append((action, rt.messages, rt.sample_count, ct.count))
        self.assertEqual(seen[-1]["action"], "research_closed")
        self.assertFalse(seen[-1]["hidden_scoring_authorized"])
        self.assertEqual(self.executions, 12)
        self.assertEqual(sum(c[2] for c in calls), 24)
        self.assertEqual(sum(c[3] for c in calls), 12)
        self.assertEqual(self.study.snapshot()["submitted_by_arm"], {a: 4 for a in ("reset", "archive", "learn")})
        first = [digest(m) for a, m, _, _ in calls if a["action"] == "experiment" and a["task_index"] == 0]
        self.assertEqual(len(set(first)), 1)
        for action, messages, _, _ in calls:
            public = json.loads(messages[1]["content"])
            for record in public["records"]:
                self.assertIn("-" + action["arm"] + "-", record["trial_id"])
                if action["task_index"] == 3:
                    self.assertNotEqual(record["task_index"], 2)
            if action["action"] == "experiment" and action["task_index"] == 1 and action["arm"] == "reset":
                self.assertEqual(public["records"], [])
        transfer_guides = [json.loads(messages[1]["content"])["research_guide"]
            for action, messages, _, _ in calls if action["action"] == "experiment"
            and action["arm"] == "learn" and action["task_index"] >= 2]
        self.assertEqual(len(transfer_guides), 2)
        self.assertIsNotNone(transfer_guides[0])
        self.assertEqual(transfer_guides[0], transfer_guides[1])
        self.assertEqual(self.budget.snapshot()["reserved_usd"], "1.20")

    def test_research_timeout_preserves_pending_claim_and_never_resamples(self):
        runner = self.create()
        rt, ct = self.transports()
        rt.error = TimeoutError("fixture ambiguity")
        with self.assertRaises(TimeoutError):
            runner.tick(rt, ct, fixture_execute=self.execute_fixture)
        self.assertEqual(runner.tick(rt, ct)["action"], "reconcile_pending")
        self.assertEqual(rt.sample_count, 1)
        self.assertEqual(ct.count, 0)
        with self.assertRaises(ValueError):
            runner.reconcile_pending()
        self.assertIsNotNone(self.study.snapshot()["active"])

    def test_invalid_first_proposal_records_failure_without_coding_or_execution(self):
        runner = self.create()
        rt, ct = self.transports()
        rt.text = "invalid proposal fixture"
        result = runner.tick(rt, ct, fixture_execute=self.execute_fixture)
        self.assertEqual(result["failure"]["stage"], "research")
        self.assertEqual((rt.sample_count, ct.count, self.executions), (1, 0, 0))
        self.assertIsNone(self.study.snapshot()["active"])

    def test_terminal_unsupported_code_is_recorded_without_execution(self):
        runner = self.create()
        rt, ct = self.transports()
        ct.body = {"status": "unsupported", "code": "", "notes": "fixture unsupported"}
        result = runner.tick(rt, ct, fixture_execute=self.execute_fixture)
        self.assertEqual(result["failure"]["stage"], "coding")
        self.assertEqual(self.executions, 0)

    def test_live_tick_blocks_before_claim_model_setup_or_coding(self):
        runner = self.create(live=True)
        rt, ct = self.transports()
        rt.live = ct.live = True
        with self.assertRaisesRegex(RuntimeError, "scientific admission"):
            runner.tick(rt, ct)
        self.assertEqual((rt.encode_count, rt.sample_count, ct.count), (0, 0, 0))
        self.assertIsNone(self.study.snapshot()["active"])

    def test_live_transport_cannot_use_fixture_runner(self):
        runner = self.create()
        rt, ct = self.transports()
        rt.live = True
        with self.assertRaisesRegex(ValueError, "transport mode"):
            runner.tick(rt, ct)
        self.assertEqual(rt.encode_count, 0)

    def test_changed_data_is_rejected_before_claim_and_paid_dispatch(self):
        runner = self.create()
        Path(self.task_data["task-0"]["train_path"]).write_bytes(b"{}")
        rt, ct = self.transports()
        with self.assertRaisesRegex(ValueError, "data changed"):
            runner.tick(rt, ct)
        self.assertIsNone(self.study.snapshot()["active"])
        self.assertEqual(rt.sample_count, 0)

    def test_changed_frozen_config_is_rejected(self):
        runner = self.create()
        path = runner.root / "config.json"
        value = json.loads(path.read_text())
        value["runtime"]["prediction_max"] = 999
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "configuration/source"):
            runner.next_action()

    def test_full_worker_bound_must_fit_study_envelope(self):
        with self.assertRaisesRegex(ValueError, "all worker stages"):
            self.create(step_bound=200)

    def test_expired_window_does_not_create_claim_or_launch(self):
        runner = self.create(deadline="2020-01-01T00:00:00+00:00")
        rt, ct = self.transports()
        self.assertEqual(runner.tick(rt, ct)["action"], "window_closed")
        self.assertEqual(rt.sample_count, 0)

    def test_slow_catalog_preparation_does_not_claim_or_launch_late_research(self):
        runner = self.create()
        rt, ct = self.transports()
        clock = [datetime(2098, 1, 1, tzinfo=timezone.utc).timestamp()]
        deadline = datetime(2099, 1, 1, tzinfo=timezone.utc).timestamp()
        original = runner._arguments

        def slow_catalog(*args):
            result = original(*args)
            clock[0] = deadline - 1
            return result

        with patch("study_runner.time.time", side_effect=lambda: clock[0]), patch.object(runner, "_arguments", slow_catalog):
            result = runner.tick(rt, ct, fixture_execute=self.execute_fixture)
        self.assertEqual((result["action"], result["stage"]), ("window_closed", "research"))
        self.assertIsNone(self.study.snapshot()["active"])
        self.assertEqual((rt.sample_count, ct.count, self.executions), (0, 0, 0))
        self.assertEqual(self.budget.snapshot()["reserved_usd"], "0")

    def test_slow_claim_preserves_id_but_does_not_launch_research(self):
        runner = self.create()
        rt, ct = self.transports()
        clock = [datetime(2098, 1, 1, tzinfo=timezone.utc).timestamp()]
        deadline = datetime(2099, 1, 1, tzinfo=timezone.utc).timestamp()
        original = StudyState.claim

        def slow_claim(study, *args):
            result = original(study, *args)
            clock[0] = deadline - 1
            return result

        with patch("study_runner.time.time", side_effect=lambda: clock[0]), patch.object(StudyState, "claim", slow_claim):
            result = runner.tick(rt, ct, fixture_execute=self.execute_fixture)
        self.assertEqual(result["stage"], "research")
        self.assertIsNotNone(self.study.snapshot()["active"])
        self.assertEqual(runner.tick(rt, ct)["action"], "reconcile_pending")
        self.assertEqual((rt.sample_count, ct.count, self.executions), (0, 0, 0))

    def test_late_coding_phase_preserves_first_research_and_no_resampling(self):
        runner = self.create()
        rt, ct = self.transports()
        clock = [datetime(2098, 1, 1, tzinfo=timezone.utc).timestamp()]
        deadline = datetime(2099, 1, 1, tzinfo=timezone.utc).timestamp()
        original = rt.sample

        def delayed_sample(*args):
            result = original(*args)
            clock[0] = deadline - 1
            return result

        with patch("study_runner.time.time", side_effect=lambda: clock[0]), patch.object(rt, "sample", delayed_sample):
            result = runner.tick(rt, ct, fixture_execute=self.execute_fixture)
        self.assertEqual((result["action"], result["stage"]), ("window_closed", "coding"))
        self.assertFalse(result["limits_shortened"])
        self.assertEqual((rt.sample_count, ct.count, self.executions), (1, 0, 0))
        self.assertIsNotNone(self.study.snapshot()["active"])
        stop = runner.root / "jobs" / result["active_trial_id"] / "window-closed-coding.json"
        self.assertEqual(json.loads(stop.read_text()), result)
        self.assertEqual(runner.tick(rt, ct)["action"], "reconcile_pending")
        self.assertEqual(rt.sample_count, 1)

    def test_slow_sandbox_preparation_cannot_create_a_late_sandbox(self):
        runner = self.create()
        rt, ct = self.transports()
        clock = [datetime(2098, 1, 1, tzinfo=timezone.utc).timestamp()]
        deadline = datetime(2099, 1, 1, tzinfo=timezone.utc).timestamp()
        original = development_harbor.prepare_job

        def slow_prepare(*args):
            result = original(*args)
            clock[0] = deadline - 1
            return result

        with patch("study_runner.time.time", side_effect=lambda: clock[0]), patch.object(development_harbor, "prepare_job", slow_prepare):
            result = runner.tick(rt, ct, fixture_execute=self.execute_fixture)
        self.assertEqual(result["stage"], "sandbox")
        self.assertEqual((rt.sample_count, ct.count, self.executions), (1, 1, 0))
        self.assertEqual(self.budget.snapshot()["reserved_usd"], "0")
        self.assertEqual(runner.tick(rt, ct)["action"], "reconcile_pending")

    def test_late_selection_claim_does_not_generate_another_answer(self):
        runner = self.create()
        rt, ct = self.transports()
        runner.tick(rt, ct, fixture_execute=self.execute_fixture)
        # Complete the same first opportunity for the other two arms.
        for _ in range(2):
            a, b = self.transports()
            runner.tick(a, b, fixture_execute=self.execute_fixture)
        self.assertEqual(runner.next_action()["action"], "selection")
        clock = [datetime(2098, 1, 1, tzinfo=timezone.utc).timestamp()]
        deadline = datetime(2099, 1, 1, tzinfo=timezone.utc).timestamp()
        original = StudyState.claim_selection

        def slow_claim(study, *args):
            result = original(study, *args)
            clock[0] = deadline - 1
            return result

        rt, ct = self.transports()
        with patch("study_runner.time.time", side_effect=lambda: clock[0]), patch.object(StudyState, "claim_selection", slow_claim):
            result = runner.tick(rt, ct, fixture_execute=self.execute_fixture)
        self.assertEqual((result["action"], result["stage"]), ("window_closed", "selection"))
        self.assertEqual(rt.sample_count, 0)
        self.assertEqual(runner.tick(rt, ct)["action"], "reconcile_pending")

    def test_all_external_stages_share_one_nonrenewable_step_deadline(self):
        runner = self.create()
        config = json.loads((runner.root / "config.json").read_text())
        self.assertTrue(config["end_to_end_wall_enforcement_verified"])
        self.assertEqual(config["worst_case_step_seconds"],
            self.tasks[0]["resource_limits"]["max_wall_seconds"] + LIMITS["wall_seconds"] + 5 + 270 + 2
            + LOCAL_OVERHEAD_SECONDS)

    def test_atomic_allowance_checked_before_research_and_final_bucket_not_borrowed(self):
        runner = self.create()
        self.budget.reserve("fixture-other", "learning", "9.99", "e2b", "a" * 64)
        rt, ct = self.transports()
        self.assertEqual(runner.tick(rt, ct)["action"], "budget_blocked")
        self.assertIsNone(self.study.snapshot()["active"])
        self.assertEqual(rt.sample_count, 0)
        self.assertEqual(self.budget.snapshot()["buckets"]["final"]["available_usd"], "10")

    def test_completed_receipts_reconcile_after_interruption_without_another_call(self):
        runner = self.create()
        rt, ct = self.transports()
        with patch.object(runner, "reconcile_pending", side_effect=RuntimeError("fixture interruption")):
            with self.assertRaises(RuntimeError):
                runner.tick(rt, ct, fixture_execute=self.execute_fixture)
        restarted = StudyRunner(runner.root)
        self.assertEqual(restarted.tick(rt, ct)["action"], "reconcile_pending")
        restarted.reconcile_pending()
        self.assertEqual((rt.sample_count, ct.count, self.executions), (1, 1, 1))
        self.assertIsNone(self.study.snapshot()["active"])

    def test_missing_sandbox_completion_remains_pending(self):
        runner = self.create()
        rt, ct = self.transports()
        with self.assertRaises(ValueError):
            runner.tick(rt, ct)
        self.assertIsNotNone(self.study.snapshot()["active"])
        self.assertEqual(self.executions, 0)
        with self.assertRaises(FileNotFoundError):
            runner.reconcile_pending()

    def test_durable_completion_before_journal_append_is_recovered_without_dispatch(self):
        from market_rsi import Journal
        runner = self.create()
        rt, ct = self.transports()
        original = Journal.append
        def interrupted(journal, event, payload):
            if event == "step_completed":
                raise RuntimeError("fixture crash after durable completion")
            return original(journal, event, payload)
        with patch.object(Journal, "append", interrupted):
            with self.assertRaisesRegex(RuntimeError, "fixture crash"):
                runner.tick(rt, ct, fixture_execute=self.execute_fixture)
        self.assertIsNotNone(self.study.snapshot()["active"])
        runner.reconcile_pending()
        self.assertIsNone(self.study.snapshot()["active"])
        self.assertEqual((rt.sample_count, ct.count, self.executions), (1, 1, 1))

    def test_runtime_and_deployed_endpoints_are_pinned_before_first_action(self):
        runner = self.create()
        config = json.loads((runner.root / "config.json").read_text())
        for source in ("prediction_candidate_server.py", "inspection_candidate_server.py",
                       "diagnostic_channel.py", "fixtures/harbor-stream-01/isolation_probe.py",
                       "tasks/development-worker/instruction.md"):
            self.assertEqual(len(config["source_hashes"][source]), 64)
        self.assertTrue(config["end_to_end_wall_enforcement_verified"])

    def test_reviewed_closed_failure_keeps_attempt_and_advances_schedule_without_retry(self):
        runner = self.create()
        trial_id = runner.next_action()["trial_id"]
        def failed_fixture(bundle, root, budget):
            self.execute_fixture(bundle, root, budget)
            def mutate(name, update):
                path = root / name
                value = json.loads(path.read_text())
                update(value)
                path.write_text(json.dumps(value))
            (root / "collected/execution.json").unlink()
            (root / "collected/predictions/complete.json").unlink()
            path = root / "collected/predictions/predictions.jsonl"
            path.write_bytes(path.read_bytes().splitlines(keepends=True)[0])
            mutate("collection.json", lambda x: x.update(missing_or_failed={"execution.json": "NotFound",
                                                                         "predictions/complete.json": "NotFound"}))
            mutate("command.json", lambda x: x.update(exit_code=1))
            mutate("collected/protocol.json", lambda x: x.update(events=x["events"][:5] + [{"type": "timeout"}]))
            fresh_json(root / "failure.json", {"error_type": "ValueError", "scored": False, "automatic_retry": False})
            fresh_json(root / "collected/failure.json", {"error_type": "TimeoutError", "scored": False})
        rt, ct = self.transports()
        result = runner.tick(rt, ct, fixture_execute=failed_fixture)
        self.assertTrue(result["failure"]["continuation_requires_causal_review"])
        self.assertEqual(runner.next_action()["action"], "causal_review_required")
        root = runner._paths(trial_id)["development_directory"]
        before = self.budget.snapshot()
        runner.review_closed_failure(trial_id, review_id="review-01",
            rationale="Human fixture review of a fabricated timeout under unchanged isolation and setup; no actual diagnosis.",
            evidence_paths=[root / "collected/protocol.json", root / "libraries.json"])
        self.assertNotEqual(runner.next_action()["trial_id"], trial_id)
        self.assertEqual(self.budget.snapshot(), before)
        self.assertEqual((rt.sample_count, ct.count, self.executions), (1, 1, 1))


if __name__ == "__main__":
    unittest.main()
