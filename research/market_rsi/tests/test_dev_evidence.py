import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import unittest
from unittest.mock import patch

import development_harbor
from dev_evidence import build_completion, commit_completion, dev_metrics
from market_rsi import digest, fresh_json
from prediction_stream import encoded
from study_state import StudyState
from trial_inputs import prepare_development_trial
import test_trial_inputs as input_fixtures
import test_development_harbor as harbor_fixtures
from test_researcher_worker import task


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = input_fixtures.TrialInputsTests()
        self.fixture.setUp()
        self.root = self.fixture.root
        self.devroot = self.root / "development-01"
        self.public_task = task()
        self.public_task["evaluation_contract"]["baseline_rule"] = "zero"
        for entry in self.public_task["data_catalog"]:
            entry["sha256"] = hashlib.sha256(encoded(self.fixture.artifacts[entry["split"]])).hexdigest()
        self.study = StudyState.create(self.root / "study", common_manifest=self.fixture.common,
            tasks=[self.public_task, task(1, "transfer")],
            baseline_source_hashes={"task-0": "b" * 64, "task-1": "b" * 64}, max_steps_per_task=3,
            max_diagnostics_per_task=1, max_research_calls_per_task=4,
            deadline_utc="2099-01-01T00:00:00+00:00", worst_case_step_seconds=300)
        self.prepared = self.study.claim("learn", "trial-01")

    def tearDown(self):
        self.fixture.tearDown()

    def pipeline(self, action="experiment"):
        with patch.object(input_fixtures, "task", return_value=copy.deepcopy(self.public_task)):
            args = self.fixture.jobs(action=action, prepared_research=self.prepared)
        self.assertEqual(args["prepared_research"], self.prepared)
        bundle = prepare_development_trial(**args)
        development_harbor.prepare_job(bundle, self.devroot)
        helper = harbor_fixtures.DevelopmentTests()
        helper.root, helper.fixture = self.devroot, self.fixture
        helper.outputs(bundle)  # Fabricated runner receipts for integration tests only.
        claim = development_harbor.verify_job(self.devroot)[0]
        self.fixture.budget.reserve(self.devroot.name, "learning", "0.10", "e2b", digest(claim))
        self.fixture.budget.dispatch(self.devroot.name)
        fresh_json(self.devroot / "sandbox.json", {"sandbox_id": "fixture-owned"})
        start = datetime.now(timezone.utc)
        fresh_json(self.devroot / "runtime.json", {"sandbox_id": "fixture-owned", "template_id": claim["template"],
            "cpu_count": 2, "memory_mb": 512, "allow_internet_access": False,
            "started_at": start.isoformat(), "expiry_at": (start + timedelta(seconds=240)).isoformat()})
        fresh_json(self.devroot / "cleanup-01.json", {"sandbox_id": "fixture-owned", "kill_acknowledged": True})
        args.pop("prepared_research")
        return args

    def mutate(self, name, update):
        path = self.devroot / name
        value = json.loads(path.read_text())
        update(value)
        path.write_text(json.dumps(value))

    def build(self, args):
        return build_completion(self.study, self.devroot, **args)

    def test_actual_components_to_owned_record_and_next_request_with_mock_providers_only(self):
        args = self.pipeline()
        before = self.fixture.budget.snapshot()
        built = self.build(args)
        completion = built["completion"]
        feedback = completion["payload"]["train_dev_results"]["dev"]
        self.assertEqual(feedback["numeric"]["aggregate"]["candidate_minus_baseline_mse"], 0.0)
        self.assertIsNone(feedback["numeric"]["net_pnl"])
        self.assertFalse(feedback["scientific_admission"])
        trace = feedback["available_trace"]
        self.assertEqual(trace["dev"], self.fixture.artifacts["dev"]["rows"])
        self.assertEqual(trace["train"], self.fixture.artifacts["train"]["rows"])
        self.assertEqual(len(trace["protocol"]["events"]), 8)
        self.assertIn("turn.completed", trace["coding_events"])
        commit_completion(self.study, built)
        next_request = self.study.next_request("learn")
        record = json.loads(next_request["messages"][1]["content"])["records"][0]
        self.assertNotIn("candidate_code", record["payload"])
        self.assertEqual(record["payload"]["proposal"], completion["payload"]["proposal"])
        self.assertEqual(record["payload"]["train_dev_results"]["dev"]["numeric"]["aggregate"],
                         completion["payload"]["train_dev_results"]["dev"]["numeric"]["aggregate"])
        self.assertNotIn("rows", record["payload"]["train_dev_results"]["dev"]["numeric"])
        self.assertEqual(record["payload"]["train_dev_results"]["dev"]["available_trace"]["data_evidence"]["dev_rows"],
                         len(self.fixture.artifacts["dev"]["rows"]))
        self.assertNotIn(str(self.root), json.dumps(record))
        self.assertEqual(self.fixture.budget.snapshot(), before)

    def test_inspection_result_is_untrusted_and_not_predictor_eligible(self):
        args = self.pipeline("inspect")
        built = self.build(args)
        completion = built["completion"]
        self.assertFalse(completion["eligible_submission"])
        feedback = completion["payload"]["train_dev_results"]["dev"]
        self.assertTrue(feedback["inspection"]["diagnostic"]["passed"])
        self.assertIsNone(feedback["numeric"])
        self.assertEqual(feedback["inspection"]["origin"], "candidate_code_untrusted_diagnostic")

    def test_reservation_stays_hold_not_spend_after_cleanup_and_memory_commit(self):
        args = self.pipeline()
        built = self.build(args)
        usage = built["completion"]["payload"]["usage"]
        self.assertEqual(usage["sandbox"]["unresolved_hold_usd"], "0.10")
        self.assertIsNone(usage["sandbox"]["metered_usd"])
        self.assertIsNone(usage["sandbox"]["invoiced_usd"])
        self.assertIsNone(usage["coding"]["allocated_cost_usd"])
        commit_completion(self.study, built)
        self.assertEqual(self.fixture.budget.snapshot()["reserved_usd"], "0.10")

    def test_caller_cannot_supply_replacement_active_request(self):
        args = self.pipeline()
        with self.assertRaises(ValueError):
            build_completion(self.study, self.devroot, prepared_research=self.prepared, **args)

    def test_missing_current_claim_rejects_before_receipt_read(self):
        args = self.pipeline()
        built = self.build(args)
        commit_completion(self.study, built)
        with self.assertRaises(ValueError):
            self.build(args)

    def test_live_path_still_blocked_by_actual_admission_not_mock_flag(self):
        args = self.pipeline()
        args["expected_live"] = True
        with self.assertRaisesRegex(RuntimeError, "scientific admission"):
            self.build(args)

    def test_wrong_sandbox_cleanup_id_rejected(self):
        args = self.pipeline()
        self.mutate("cleanup-01.json", lambda x: x.update(sandbox_id="unrelated"))
        with self.assertRaises(ValueError):
            self.build(args)

    def test_unacknowledged_cleanup_rejected(self):
        args = self.pipeline()
        self.mutate("cleanup-01.json", lambda x: x.update(kill_acknowledged=False))
        with self.assertRaises(ValueError):
            self.build(args)

    def test_wrong_runtime_or_excess_lifetime_rejected(self):
        args = self.pipeline()
        self.mutate("runtime.json", lambda x: x.update(memory_mb=2048))
        with self.assertRaises(ValueError):
            self.build(args)

    def test_undeclared_budget_dispatch_rejected(self):
        args = self.pipeline()
        with patch.object(self.fixture.budget, "snapshot", wraps=self.fixture.budget.snapshot) as snap:
            state = self.fixture.budget.snapshot()
            state["jobs"].pop(self.devroot.name)
            snap.return_value = state
            # Research/coder receipt validation still runs; its research job is
            # present, but the sandbox has no matching budget dispatch.
            with self.assertRaises(ValueError):
                self.build(args)

    def test_failed_job_cannot_be_imported_as_success(self):
        args = self.pipeline()
        fresh_json(self.devroot / "failure.json", {"error_type": "fixture failure"})
        with self.assertRaises(ValueError):
            self.build(args)

    def test_saved_assessment_score_is_not_used(self):
        args = self.pipeline()
        fresh_json(self.devroot / "assessment.json", {"passed": True, "mse": -999999})
        result = self.build(args)["completion"]["payload"]["train_dev_results"]["dev"]["numeric"]
        self.assertGreaterEqual(result["aggregate"]["candidate"]["mse"], 0)

    def test_candidate_stderr_is_retained_but_root_traceback_is_not_model_input(self):
        from diagnostic_channel import stderr_receipt
        args = self.pipeline()
        path = self.devroot / "collected/candidate-stderr.log"
        path.write_text("candidate-controlled warning; not an independent diagnosis\n")
        diagnostic = self.devroot / "collected/candidate-diagnostic.json"
        diagnostic.write_text(json.dumps(stderr_receipt(path)))
        self.mutate("command.json", lambda x: x.update(stderr="RUNNER_ONLY_EVALUATOR_TRACEBACK"))
        built = self.build(args)
        payload = built["completion"]["payload"]
        text = json.dumps(payload)
        self.assertIn("candidate-controlled warning", text)
        self.assertNotIn("RUNNER_ONLY_EVALUATOR_TRACEBACK", text)
        self.assertFalse(payload["train_dev_results"]["dev"]["available_trace"]["candidate_stderr"]["independent_diagnosis"])

    def test_mutated_stderr_cannot_match_saved_diagnostic(self):
        args = self.pipeline()
        (self.devroot / "collected/candidate-stderr.log").write_text("replaced")
        with self.assertRaisesRegex(ValueError, "diagnostic receipt"):
            self.build(args)

    def test_mutation_between_build_and_memory_commit_is_detected(self):
        args = self.pipeline()
        built = self.build(args)
        self.mutate("collected/protocol.json", lambda x: x.update(events=[]))
        with self.assertRaises(ValueError):
            commit_completion(self.study, built)
        self.assertIsNotNone(self.study.snapshot()["active"])


class NumericFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.train = [{"target": .2}, {"target": .4}]
        self.dev = [{"row_id": "a", "game_id": "g1", "decision_ms": 86400000, "target": .1},
                    {"row_id": "b", "game_id": "g2", "decision_ms": 172800000, "target": .2}]
        self.contract = {"primary_metric": "mse", "target": "mid_change", "baseline_rule": "zero"}

    def test_baseline_rule_required_not_chosen_after_scores(self):
        for rule in (None, "best_of_zero_and_mean"):
            with self.assertRaises(ValueError):
                dev_metrics(self.train, self.dev, {"a": .1, "b": .2}, dict(self.contract, baseline_rule=rule))

    def test_prior_train_mean_not_dev_mean(self):
        result = dev_metrics(self.train, self.dev, {"a": .1, "b": .2}, dict(self.contract, baseline_rule="train_mean"))
        self.assertAlmostEqual(result["rows"][0]["baseline_prediction"], .3)
        self.assertEqual(result["aggregate"]["candidate"]["mse"], 0)
        self.assertEqual(len(result["by_day"]), 2)
        self.assertEqual(len(result["by_game"]), 2)
        self.assertFalse(result["promotion"])

    def test_missing_prediction_never_silently_intersects(self):
        with self.assertRaises(ValueError):
            dev_metrics(self.train, self.dev, {"a": .1}, self.contract)

    def test_future_midpoint_uses_each_rows_current_midpoint_as_persistence(self):
        train = [{"target": .42}, {"target": .53}]
        dev = [
            {"row_id": "a", "game_id": "g1", "decision_ms": 86400000,
             "features": {"mid": .40}, "target": .45},
            {"row_id": "b", "game_id": "g2", "decision_ms": 172800000,
             "features": {"mid": .60}, "target": .50},
        ]
        contract = {"primary_metric": "mse", "target": "future_midpoint",
                    "baseline_rule": "persistence"}
        result = dev_metrics(train, dev, {"a": .45, "b": .50}, contract)
        self.assertEqual([row["baseline_prediction"] for row in result["rows"]], [.40, .60])
        self.assertEqual(result["aggregate"]["candidate"]["mse"], 0)
        with self.assertRaises(ValueError):
            dev_metrics(train, dev, {"a": .45, "b": .50},
                        dict(contract, target="mid_change"))


if __name__ == "__main__":
    unittest.main()
