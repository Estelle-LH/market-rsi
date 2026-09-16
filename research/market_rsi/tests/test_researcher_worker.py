import copy
import json
import tempfile
import unittest
from pathlib import Path

from market_rsi import digest, load_json
from paid_budget import PaidBudget
from research_context import freeze_common
from researcher_worker import (GLMTransport, MEMORY_RECORD_MAX_BYTES, assess_proposal,
                               dispatch_once, memory_inspection, memory_payload, prepare_request)


def task(index=0, phase="learning", experiment="fixture-research"):
    return {"schema": "market_research_task_v1", "experiment_id": experiment,
            "task_id": f"task-{index}", "task_index": index, "phase": phase,
            "objective": "Compare predictive error on the declared task.",
            "data_catalog": [{"artifact_id": name, "split": name, "sha256": "a" * 64,
                              "description": "Synthetic fixture only"} for name in ["train", "dev"]],
            "evaluation_contract": {"primary_metric": "mse", "target": "mid_change"},
            "resource_limits": {"max_input_tokens": 10000, "max_output_tokens": 1024, "max_wall_seconds": 30},
            "opaque_test_commitment": "b" * 64}


def record(arm="learn", index=0, step=0, phase="learning"):
    return {"schema": "market_research_record_v1", "experiment_id": "fixture-research",
            "arm": arm, "task_id": f"task-{index}", "task_index": index, "step_index": step,
            "phase": phase, "trial_id": f"trial-{index}-{step}", "visibility": "train_dev",
            "origin": "runner_recorded_train_dev", "payload": {"proposal": {**proposal(), "action": "experiment"},
                "candidate_code": "fixture code text, never executed", "train_dev_results": {"dev": {
                    "execution_verified": True, "scientific_admission": True,
                    "numeric": {"aggregate": {"mse": 0.12}}}},
                "usage": {"fixture": True}, "failure": None}}


def proposal():
    return {"action": "inspect", "question": "Are the declared inputs consistent?", "changed_stage": "data",
            "hypothesis": "Check timing before fitting.", "coding_brief": "Inspect the permitted input timestamps.",
            "expected_evidence": ["Timestamp checks"], "guide_update": None}


class FakeTransport:
    live = False
    def __init__(self, text=None, error=None, finish_reason="stop"):
        self.text = json.dumps(proposal()) if text is None else text
        self.error, self.finish_reason = error, finish_reason
        self.encode_count, self.sample_count = 0, 0

    def encode(self, messages):
        self.encode_count += 1
        self.messages = copy.deepcopy(messages)
        return {"token_ids": [1, 2, 3], "rendered_prompt": "fixture only",
                "tokenizer_repo": "fixture", "tokenizer_revision": "fixture",
                "chat_template_sha256": "a" * 64}

    def sample(self, ids, maximum, timeout):
        self.sample_count += 1
        if self.error:
            raise self.error
        return {"text": self.text, "output_tokens": [10, 11], "cached_input_tokens": 0,
                "finish_reason": self.finish_reason, "provider": {"fixture": True}}


class RequestFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.common = self.root / "common.json"
        freeze_common(self.common)

    def tearDown(self):
        self.tmp.cleanup()

    def prepared(self, arm="learn", index=0, step=0, records=None, guide=None, phase="learning"):
        return prepare_request(self.common, arm=arm, task=task(index, phase), step_index=step,
                               records=records or [], guide=guide)


class RequestTests(RequestFixture):
    def test_common_prompt_and_manifest_identical_across_arms(self):
        packets = [self.prepared(arm) for arm in ["reset", "archive", "learn"]]
        self.assertEqual(len({p["messages"][0]["content"] for p in packets}), 1)
        self.assertEqual(len({digest(p["messages"]) for p in packets}), 1)
        self.assertEqual(len({p["audit"]["common_manifest_sha256"] for p in packets}), 1)
        for p in packets:
            public = json.loads(p["messages"][1]["content"])
            self.assertEqual(public["records"], [])
            self.assertNotIn("arm", public)
            self.assertNotIn(str(self.root), p["messages"][1]["content"])
            self.assertEqual(p["packet_sha256"], digest({k: v for k, v in p.items() if k != "packet_sha256"}))

    def test_owned_history_is_complete_not_replaced_by_host_summary(self):
        r = record()
        p = self.prepared(index=1, records=[r])
        public = json.loads(p["messages"][1]["content"])
        projected = public["records"][0]["payload"]
        self.assertNotIn("candidate_code", projected)
        self.assertIn("candidate_code_sha256", projected)
        self.assertIn("memory_projection", projected)
        self.assertEqual(projected["proposal"], r["payload"]["proposal"])
        self.assertEqual(p["audit"]["record_sha256"], [digest(r)])

    def test_oversized_trace_is_hash_referenced_under_fixed_memory_bound(self):
        payload = record()["payload"]
        payload["proposal"] = {**proposal(), "coding_brief": "brief " * 10000}
        payload["train_dev_results"] = {"dev": {
            "execution_verified": True, "scientific_admission": True,
            "numeric": {"aggregate": {"mse": 0.12}, "rows": list(range(10000))},
            "inspection": {"row_count": 6000, "anomalies": {}, "unused": "x" * 100000},
            "available_trace": {"candidate_stderr": {"text": "private " * 50000,
                "bytes": 400000, "sha256": "c" * 64, "origin": "candidate"},
                "research_response": "response " * 50000, "coding_notes": "note " * 5000}}}
        projected = memory_payload(payload)
        raw = json.dumps(projected, sort_keys=True).encode()
        self.assertLessEqual(len(raw), MEMORY_RECORD_MAX_BYTES)
        self.assertNotIn(b"private private", raw)
        self.assertNotIn(b"response response", raw)
        self.assertIn(b"full_split_reference", raw)

    def test_projection_note_is_counted_before_memory_bound(self):
        payload = record()["payload"]
        # This fixture fits under the bound before the projection note and is
        # one byte over after it.  The selector must receive the compact
        # numeric score instead of losing the whole result behind a hash.
        payload["train_dev_results"]["dev"]["available_trace"] = {
            "data_evidence": {"notes": "x" * 6896}}
        projected = memory_payload(payload)
        raw = json.dumps(projected, sort_keys=True).encode()
        self.assertLessEqual(len(raw), MEMORY_RECORD_MAX_BYTES)
        self.assertIn("numeric", projected["train_dev_results"]["dev"])
        self.assertEqual(projected["train_dev_results"]["dev"]["numeric"]["aggregate"]["mse"], 0.12)

    def test_oversized_failure_and_proposal_have_total_hash_fallback(self):
        payload = record()["payload"]
        payload["proposal"] = {**proposal(), "question": "q" * 100000,
                               "hypothesis": "h" * 100000, "coding_brief": "b" * 100000}
        payload["train_dev_results"] = {"dev": {"numeric": {"aggregate": "a" * 100000},
                                                  "available_trace": {"stderr": "s" * 100000}}}
        payload["usage"] = {"note": "u" * 100000}
        payload["failure"] = {"diagnosis": "f" * 100000}
        projected = memory_payload(payload)
        raw = json.dumps(projected, sort_keys=True).encode()
        self.assertLessEqual(len(raw), MEMORY_RECORD_MAX_BYTES)
        for fragment in (b"q" * 1000, b"a" * 1000, b"s" * 1000, b"u" * 1000, b"f" * 1000):
            self.assertNotIn(fragment, raw)
        self.assertIn(b"sha256", raw)

    def test_reset_remembers_current_task_but_not_earlier_tasks(self):
        self.prepared("reset", step=1, records=[record("reset")])
        with self.assertRaises(ValueError):
            self.prepared("reset", index=1, records=[record("reset")])

    def test_wrong_arm_hidden_feedback_and_host_advice_rejected(self):
        for field, value in [("arm", "archive"), ("visibility", "hidden_test"),
                             ("origin", "human_intervention"), ("experiment_id", "other")]:
            r = record()
            r[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.prepared(index=1, records=[r])
        r = record()
        r["payload"]["train_dev_results"]["test"] = {"mse": 0.01}
        with self.assertRaises(ValueError):
            self.prepared(index=1, records=[r])

    def test_future_duplicate_and_reordered_history_rejected(self):
        for history in ([record()], [record(), record()], [record(step=1), record(step=0)]):
            with self.subTest(history=history), self.assertRaises(ValueError):
                self.prepared(records=history)
        with self.assertRaises(ValueError):
            self.prepared(index=1, records=[record(step=1), record(step=0)])

    def test_transfer_records_do_not_pass_to_later_transfer_tasks(self):
        with self.assertRaises(ValueError):
            self.prepared(index=2, records=[record(index=1, phase="transfer")], phase="transfer")
        self.prepared(index=2, step=1, records=[record(index=2, phase="transfer")], phase="transfer")

    def test_guide_requires_learn_arm_and_owned_record_evidence(self):
        guide = {"schema": "market_research_guide_v1", "experiment_id": "fixture-research", "arm": "learn",
                 "revision_id": "guide-1", "origin": "agent_generated", "text": "Check timing first.",
                 "evidence_trial_ids": ["trial-0-0"]}
        self.prepared(index=1, records=[record()], guide=guide)
        for change in ({"origin": "host_generated"}, {"evidence_trial_ids": ["unseen-trial"]}, {"arm": "archive"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.prepared(index=1, records=[record()], guide={**guide, **change})

    def test_changed_common_manifest_fails(self):
        data = load_json(self.common)
        data["system_prompt"] += "changed"
        self.common.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.prepared()

    def test_hidden_catalog_and_extra_task_fields_fail(self):
        for change in ("catalog", "extra"):
            t = task()
            if change == "catalog":
                t["data_catalog"][1]["split"] = "test"
            else:
                t["final_scores"] = {"a": 0.9}
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare_request(self.common, arm="learn", task=t, step_index=0, records=[])

    def test_proposal_guide_update_is_disabled_outside_learning_learn_arm(self):
        p = proposal()
        p["guide_update"] = {"text": "A changed rule", "evidence_trial_ids": ["trial-0-0"]}
        self.assertTrue(assess_proposal(json.dumps(p), self.prepared(index=1, records=[record()])["audit"])["valid"])
        for arm in ["archive", "reset"]:
            self.assertFalse(assess_proposal(json.dumps(p), self.prepared(arm)["audit"])["valid"])
        self.assertFalse(assess_proposal(json.dumps(p), self.prepared(index=1, phase="transfer")["audit"])["valid"])

    def test_invalid_proposal_is_not_repaired_or_assumed_success(self):
        for text in ("not json", "[]", json.dumps({**proposal(), "action": "read_hidden_test"}),
                     json.dumps({**proposal(), "guide_update": {"text": "new", "evidence_trial_ids": []}})):
            self.assertFalse(assess_proposal(text, self.prepared()["audit"])["valid"])

    def test_omitted_guide_update_is_normalized_to_null_only(self):
        value = proposal()
        del value["guide_update"]
        result = assess_proposal(json.dumps(value), self.prepared()["audit"])
        self.assertTrue(result["valid"])
        self.assertIsNone(result["proposal"]["guide_update"])
        value["unexpected"] = "not permitted"
        self.assertFalse(assess_proposal(json.dumps(value), self.prepared()["audit"])["valid"])

    def test_nested_inspection_findings_remain_visible_and_bounded(self):
        value = {"scored": False, "scientific_admission": False,
                 "independent_score": None, "origin": "sandbox_inspection",
                 "diagnostic": {
                     "baseline": {"all_train": {"rows": 6000,
                         "persistence_mse": 4.54166666666666e-7,
                         "zero_target_change_fraction": 0.7325}},
                     "change_distribution": {"median": 0.0, "max": 0.015},
                     "candidate_single_stage_changes": [
                         {"rank": 1, "changed_stage": "predictor",
                          "change": "Fit a regularized residual predictor."}],
                     "bulk": {str(index): "x" * 1000 for index in range(100)}}}
        projected = memory_inspection(value)
        findings = projected["diagnostic_findings"]
        self.assertEqual(findings["baseline.all_train.rows"], 6000)
        self.assertEqual(findings["baseline.all_train.persistence_mse"], 4.54166666666666e-7)
        self.assertIn("candidate_single_stage_changes[0].change", findings)
        self.assertLessEqual(len(json.dumps(projected, sort_keys=True).encode()), 3500)
        self.assertIn("full_inspection_reference", projected)

    def test_dev_public_bulk_cannot_crowd_out_train_baseline_and_cadence(self):
        value = {"scored": False, "scientific_admission": False,
                 "independent_score": None, "origin": "sandbox_inspection",
                 "diagnostic": {
                     "dev_public": {f"field_{index}": index for index in range(200)},
                     "historical_summary": {
                         "train_baselines": {"persistence": {
                             "mse": 4.54166666666666e-7, "n": 6000}},
                         "sampling_cadence": {"median_gap_ms": 430013,
                                              "gaps_over_60s": 5704}},
                 }}
        projected = memory_inspection(value)
        findings = projected["diagnostic_findings"]
        self.assertEqual(
            findings["historical_summary.train_baselines.persistence.mse"],
            4.54166666666666e-7,
        )
        self.assertEqual(
            findings["historical_summary.sampling_cadence.median_gap_ms"],
            430013,
        )
        self.assertLessEqual(len(findings), 64)
        self.assertTrue(projected["diagnostic_summary_truncated"])
        self.assertLessEqual(len(json.dumps(projected, sort_keys=True).encode()), 3500)

    def test_concise_contract_reports_exact_failure_reason(self):
        cases = [
            ({**proposal(), "question": "q" * 241}, "question_too_long"),
            ({**proposal(), "expected_evidence": ["e"] * 6}, "invalid_expected_evidence"),
            ({**proposal(), "coding_brief": "b" * 1801}, "coding_brief_too_long"),
        ]
        for value, reason in cases:
            with self.subTest(reason=reason):
                result = assess_proposal(json.dumps(value), self.prepared()["audit"])
                self.assertFalse(result["valid"])
                self.assertEqual(result["reason"], reason)

    def test_diagnostic_slot_is_separate_and_enforced(self):
        open_audit = self.prepared()["audit"]
        open_audit["slot_policy"] = {"scoreable_candidates_remaining": 2,
                                     "diagnostic_attempts_remaining": 1,
                                     "research_calls_remaining": 4}
        self.assertTrue(assess_proposal(json.dumps(proposal()), open_audit)["valid"])
        closed_audit = copy.deepcopy(open_audit)
        closed_audit["slot_policy"]["diagnostic_attempts_remaining"] = 0
        result = assess_proposal(json.dumps(proposal()), closed_audit)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "diagnostic_slot_exhausted")

    def test_guide_cannot_cite_inspection_or_failed_record(self):
        inspection = record()
        inspection["payload"]["proposal"] = proposal()
        failed = record(index=1)
        failed["payload"]["failure"] = {"stage": "sandbox"}
        prepared = self.prepared(index=2, records=[inspection, failed])
        self.assertEqual(prepared["audit"]["scored_guide_evidence_trial_ids"], [])
        update = {**proposal(), "guide_update": {
            "text": "A durable rule", "evidence_trial_ids": [inspection["trial_id"]]}}
        result = assess_proposal(json.dumps(update), prepared["audit"])
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "invalid_guide_evidence")


class DispatchTests(RequestFixture):
    def budget(self, experiment="fixture-research"):
        return PaidBudget.create(self.root / "budget", {"experiment_id": experiment, "cap_usd": "2",
            "target_usd": "1", "buckets_usd": {"learning": "1", "final": "1"},
            "authority": "offline fixture only; no real provider requests"})

    def test_one_dispatch_binds_common_and_accounts_terminal_mock(self):
        transport, budget, prepared = FakeTransport(), self.budget(), self.prepared()
        out = self.root / "request-01"
        result = dispatch_once(prepared, transport, budget, out)
        self.assertTrue(result["valid"])
        self.assertFalse(result["live_transport"])
        self.assertIsNone(result["research_score"])
        self.assertEqual(transport.sample_count, 1)
        saved = load_json(out / "request.json")
        self.assertEqual(saved["audit"]["common_manifest_sha256"], prepared["audit"]["common_manifest_sha256"])
        self.assertEqual(budget.snapshot()["reserved_usd"], "0")
        self.assertEqual(budget.snapshot()["buckets"]["final"]["available_usd"], "1")
        with self.assertRaises(FileExistsError):
            dispatch_once(prepared, transport, budget, out)
        self.assertEqual(transport.sample_count, 1)

    def test_ambiguous_provider_failure_retains_hold_and_never_retries(self):
        transport, budget = FakeTransport(error=TimeoutError("ambiguous fixture")), self.budget()
        out = self.root / "request-01"
        with self.assertRaises(TimeoutError):
            dispatch_once(self.prepared(), transport, budget, out)
        self.assertEqual(transport.sample_count, 1)
        self.assertEqual(budget.snapshot()["jobs"][out.name]["state"], "dispatched")
        self.assertTrue((out / "failure.json").exists())
        self.assertFalse((out / "assessment.json").exists())

    def test_bad_response_still_records_terminal_usage(self):
        budget, transport = self.budget(), FakeTransport(text="invalid fixture JSON")
        out = self.root / "request-01"
        result = dispatch_once(self.prepared(), transport, budget, out)
        self.assertFalse(result["valid"])
        self.assertEqual(budget.snapshot()["jobs"][out.name]["state"], "metered_terminal")
        self.assertEqual(transport.sample_count, 1)

    def test_length_stop_is_recorded_as_truncation_not_generic_invalid_json(self):
        budget = self.budget()
        transport = FakeTransport(text=json.dumps(proposal()), finish_reason="length")
        result = dispatch_once(self.prepared(), transport, budget, self.root / "truncated-01")
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "output_truncated")
        self.assertEqual(budget.snapshot()["jobs"]["truncated-01"]["state"], "metered_terminal")

    def test_changed_packet_or_audit_fails_before_provider(self):
        for target in ("messages", "audit"):
            prepared, transport = self.prepared(), FakeTransport()
            if target == "messages":
                prepared["messages"][0]["content"] += "changed"
            else:
                prepared["audit"]["arm"] = "archive"
            with self.subTest(target=target), self.assertRaises(ValueError):
                dispatch_once(prepared, transport, None, self.root / "never-created")
            self.assertEqual(transport.encode_count, 0)

    def test_live_transport_is_blocked_without_independent_admission(self):
        transport = FakeTransport()
        transport.live = True
        with self.assertRaises(RuntimeError):
            dispatch_once(self.prepared(), transport, None, self.root / "no-live-request")
        self.assertEqual(transport.encode_count, 0)
        self.assertEqual(transport.sample_count, 0)
        self.assertFalse((self.root / "no-live-request").exists())

    def test_mock_transport_cannot_touch_real_experiment_ledger(self):
        budget = self.budget("not-a-fixture")
        t = task(experiment="not-a-fixture")
        prepared = prepare_request(self.common, arm="learn", task=t, step_index=0, records=[])
        with self.assertRaises(ValueError):
            dispatch_once(prepared, FakeTransport(), budget, self.root / "forbidden")
        self.assertEqual(budget.snapshot()["jobs"], {})

    def test_context_overflow_never_silently_drops_history(self):
        t = task()
        t["resource_limits"]["max_input_tokens"] = 2
        prepared = prepare_request(self.common, arm="learn", task=t, step_index=0, records=[])
        transport, budget = FakeTransport(), self.budget()
        with self.assertRaises(ValueError):
            dispatch_once(prepared, transport, budget, self.root / "too-large")
        self.assertEqual(transport.sample_count, 0)
        self.assertEqual(budget.snapshot()["jobs"], {})


if __name__ == "__main__":
    unittest.main()
