import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coder_worker import dispatch_code_once, prepare_code_request
from dev_evidence import commit_completion
from failure_evidence import build_worker_failure
from market_rsi import fresh_json
from paid_budget import PaidBudget
from research_context import freeze_common
from researcher_worker import dispatch_once
from study_state import StudyState
from worker_receipts import read_code_terminal, read_research_terminal
from test_researcher_worker import FakeTransport, task, proposal
from test_coder_worker import FakeCoder, LIMITS, RUNTIME
from test_worker_receipts import INSPECT_CODE


class FailureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        common = self.root / "common.json"
        freeze_common(common)
        self.budget = PaidBudget.create(self.root / "budget", {
            "experiment_id": "fixture-research", "cap_usd": "2", "target_usd": "1",
            "buckets_usd": {"learning": "1", "final": "1"}, "authority": "offline test"})
        self.study = StudyState.create(self.root / "study", common_manifest=common,
            tasks=[task(), task(1, "transfer")], baseline_source_hashes={"task-0": "a" * 64, "task-1": "a" * 64},
            max_steps_per_task=3, max_diagnostics_per_task=1, max_research_calls_per_task=4,
            deadline_utc="2099-01-01T00:00:00+00:00", worst_case_step_seconds=300)
        self.prepared = self.study.claim("learn", "trial-01")
        self.rdir, self.cdir = self.root / "research-01", self.root / "coding-01"
        self.identity = {"authentication": "fixture", "model": "fixture"}

    def tearDown(self):
        self.tmp.cleanup()

    def research(self, text="not valid JSON", transport=None):
        self.rt = transport or FakeTransport(text=text)
        return dispatch_once(self.prepared, self.rt, self.budget, self.rdir)

    def coder(self, body=None):
        self.research(json.dumps(proposal()))
        code_request = prepare_code_request(self.prepared, self.rt.text, RUNTIME, LIMITS)
        self.ct = FakeCoder(body or {"status": "unsupported", "code": "", "notes": "fixture unsupported"})
        dispatch_code_once(code_request, self.ct, self.cdir)

    def build(self, coding=False, **kwargs):
        args = {"research_directory": self.rdir, "budget": self.budget, "expected_live": False}
        if coding:
            args.update(coding_directory=self.cdir, frozen_runtime=RUNTIME, frozen_coder_limits=LIMITS,
                        expected_coder_identity=self.identity)
        args.update(kwargs)
        return build_worker_failure(self.study, **args)

    def test_invalid_first_proposal_is_preserved_without_retry_or_score(self):
        self.assertFalse(self.research()["valid"])
        before = self.budget.snapshot()
        built = self.build()
        value = built["completion"]
        self.assertEqual(value["raw_research_response"], "not valid JSON")
        self.assertEqual(value["payload"]["train_dev_results"], {})
        self.assertIsNone(value["payload"]["proposal"])
        self.assertFalse(value["eligible_submission"])
        self.assertEqual(value["payload"]["failure"]["kind"], "invalid_json")
        commit_completion(self.study, built)
        next_request = self.study.next_request("learn")
        record = json.loads(next_request["messages"][1]["content"])["records"][0]
        self.assertNotIn("candidate_code", record["payload"])
        self.assertIn("candidate_code_sha256", record["payload"])
        self.assertEqual(record["payload"]["failure"], value["payload"]["failure"])
        self.assertEqual(self.rt.sample_count, 1)
        self.assertEqual(self.budget.snapshot(), before)

    def test_unsupported_code_retained_as_text_not_executed(self):
        self.coder()
        built = self.build(coding=True)
        value = built["completion"]
        failure = value["payload"]["failure"]
        self.assertEqual(failure["stage"], "coding")
        self.assertEqual(failure["kind"], "invalid_or_unsupported_code")
        self.assertIn("turn.completed", failure["available_trace"]["coding_events"])
        self.assertIsNone(value["payload"]["usage"]["coding"]["allocated_cost_usd"])
        commit_completion(self.study, built)
        self.assertEqual(self.ct.count, 1)

    def test_syntax_error_is_a_terminal_coding_outcome(self):
        self.coder({"status": "implemented", "code": "def inspect( broken", "notes": "fixture syntax error"})
        built = self.build(coding=True)
        self.assertEqual(built["completion"]["payload"]["candidate_code"], "def inspect( broken")
        self.assertFalse(built["completion"]["eligible_submission"])

    def test_valid_proposal_cannot_be_silently_discarded(self):
        self.research(json.dumps(proposal()))
        with self.assertRaisesRegex(ValueError, "valid proposal"):
            self.build()

    def test_valid_code_cannot_be_silently_discarded(self):
        self.coder({"status": "implemented", "code": INSPECT_CODE, "notes": "fixture code"})
        with self.assertRaisesRegex(ValueError, "valid code"):
            self.build(coding=True)

    def test_ambiguous_provider_failure_keeps_hold_and_active_claim(self):
        with self.assertRaises(TimeoutError):
            self.research(transport=FakeTransport(error=TimeoutError("fixture provider ambiguity")))
        before = self.budget.snapshot()
        self.assertGreater(float(before["reserved_usd"]), 0)
        with self.assertRaises(ValueError):
            self.build()
        self.assertIsNotNone(self.study.snapshot()["active"])
        self.assertEqual(self.budget.snapshot(), before)
        self.assertEqual(self.rt.sample_count, 1)

    def test_terminal_but_late_response_stays_failed(self):
        # Controlled runner clock: start, preparation, metering, assessment.
        with patch("researcher_worker.time.monotonic", side_effect=[0, 0, 31, 31]):
            report = self.research(json.dumps(proposal()))
        self.assertFalse(report["valid"])
        built = self.build()
        self.assertEqual(built["completion"]["payload"]["failure"]["kind"], "wall_limit")
        self.assertEqual(built["completion"]["payload"]["proposal"], proposal())

    def test_other_arm_receipts_cannot_be_imported(self):
        self.research()
        original = self.prepared["audit"]["arm"]
        self.prepared["audit"]["arm"] = "archive"
        with self.assertRaises(ValueError):
            read_research_terminal(self.rdir, self.prepared, self.budget, expected_live=False)
        self.prepared["audit"]["arm"] = original

    def test_invented_failure_assessment_rejected(self):
        self.research(json.dumps(proposal()))
        path = self.rdir / "assessment.json"
        value = json.loads(path.read_text())
        value["valid"] = False
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            self.build()

    def test_coder_usage_mutation_rejected(self):
        self.coder()
        path = self.cdir / "subscription-usage.json"
        value = json.loads(path.read_text())
        value["usage"]["output_tokens"] += 1
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            self.build(coding=True)

    def test_mutation_after_build_before_memory_rejected(self):
        self.research()
        built = self.build()
        fresh_json(self.rdir / "failure.json", {"error_type": "late failure"})
        with self.assertRaises(ValueError):
            commit_completion(self.study, built)

    def test_live_path_cannot_use_fixture_completion(self):
        self.research()
        with self.assertRaisesRegex(RuntimeError, "scientific admission"):
            self.build(expected_live=True)

    def test_no_completion_without_an_active_claim(self):
        self.research()
        commit_completion(self.study, self.build())
        with self.assertRaises(ValueError):
            self.build()


if __name__ == "__main__":
    unittest.main()
