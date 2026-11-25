"""Actual counted Controller requests and strict numeric research feedback.

Protocol-only literals are labelled as such below. Integration uses actual
original forecast/probe/review/Task feedback and temporary owned accounting;
HTTP/Controller responses and the earlier loop's author roles are invented.
It does not establish actual-model authorship, learning or a full CLI run.
"""
from contextlib import ExitStack
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import earnings_controller as controller
import earnings_entry as entry
import earnings_research_diagnostics as diagnostics
from earnings_feedback import project_feedback
from earnings_shadow_measurement import FAMILIES, METRICS
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_capacity_controller_transport as transport
import test_earnings_pending_evolution as pending_fixture

PRIVATE = "CP8_RAW_QA_PRIVATE_PATH_ERROR_MUST_NOT_ENTER_PAYLOAD"
GRAMMAR = "earnings-shadow-v1|<component>|<metric>|<lower-or-higher>|<positive-integer>|score_nonregression|matched_trial_only"
EXECUTION_FIELDS = METRICS | {"initial_records", "score_out_of_5"}
REVIEW_FIELDS = {"verdict", "reason", "metric", "direction", "min_delta", "observed_delta", "score_delta", "benefit_observed"}


class CapacityFeedbackContractTests(unittest.TestCase):
    def transport_fixture(self, name="request"):
        tmp = tempfile.TemporaryDirectory(prefix="cp8-feedback-contract-")
        self.addCleanup(tmp.cleanup)
        return transport._TransportFixture(self, Path(tmp.name).resolve() / name)

    def protocol(self):
        # This numerical literal tests only validation, never actual execution.
        observation = project_feedback({"status": "COMPLETED_SCORED", "planned_targets": 5,
            "scored_targets": 5, "points": 5, "turns": 2, "tool_calls": 2},
            {"score_out_of_5": 5, "target_count": 5, "prediction_count": 5,
             "duplicate_prediction_ids": [], "unknown_prediction_ids": []}, task_id="protocol-fixture", cik="fixture")
        value = {"schema": "earnings_research_diagnostics_v1", "execution": {
            "turns": 2, "tool_calls": 2, "input_tokens": 24, "output_tokens": 14,
            "tool_return_characters": 1200, "repeated_reads": 0, "rejected_tools": 0,
            "records_added": 1, "initial_records": 0, "score_out_of_5": 5},
            "review": {"verdict": "accept", "reason": "MATCHED_OPERATIONAL_BENEFIT",
                "metric": "tool_return_characters", "direction": "lower", "min_delta": 1,
                "observed_delta": -4, "score_delta": 0, "benefit_observed": True}}
        return value, observation

    def pending(self, axes=("H", "R")):
        fixture = pending_fixture._PendingFixture(self, axes=axes)
        fixture.run()
        return fixture

    def stage(self, fixture, index, name):
        return engine.read(engine.pin(fixture.raw.role_root / "loop" / f"round-{index:04d}-{name}.done.json"))["output"]

    def original_tree(self, root):
        return {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file() and not p.is_symlink()}

    def test_actual_counted_request_discloses_exact_grammar_and_allowed_metrics(self):
        fixture = self.transport_fixture()
        chosen = fixture.decision("continue")
        original = fixture.invoke(fixture.response(chosen))
        self.assertEqual(engine.read(original), dict(fixture.response(chosen), _request_id="req_cp1_fixture"))
        self.assertEqual(Path(original["path"]).read_bytes(),
                         (Path(fixture.slots[0]) / "01-response.json").read_bytes())
        self.assertEqual([endpoint for endpoint, _ in fixture.calls], ["/v1/responses/input_tokens", "/v1/responses"])
        count, generation = [payload for _, payload in fixture.calls]
        for request in (count, generation):
            instructions = request["instructions"]
            self.assertIn(GRAMMAR, instructions)
            self.assertIn("canonical integer1..999999999 (no leading zero)", instructions)
            self.assertIn("direction lower or higher", instructions)
            declared = instructions.split("Allowed metrics by component: ", 1)[1].split(". Example:", 1)[0]
            self.assertEqual(json.loads(declared), {key: sorted(value) for key, value in FAMILIES.items()})
            self.assertIn("Continue may use a plain nonempty no-change expected_effect", instructions)
            self.assertIn("no forced sequence", instructions)
            self.assertEqual((request["tools"], request["tool_choice"], request["parallel_tool_calls"]), ([], "none", False))
        self.assertEqual(count["instructions"], generation["instructions"])
        self.assertEqual(fixture.budget.db.execute("SELECT charged,status FROM requests WHERE id!='fixture-prior'").fetchall(),
                         [(92800, "settled")])
        self.assertEqual(fixture.factory.call_count, 1)
        self.assertEqual(engine.read(engine.pin(Path(fixture.slots[0]) / "decision.json"))["decision"], chosen)

    def test_absent_diagnostics_preserves_legacy_seed_payload_and_free_continue(self):
        fixture = self.transport_fixture()
        prompt = deepcopy(fixture.prompt)
        self.assertNotIn("research_diagnostics", prompt["feedback"])
        request = controller.capacity_request(prompt, fixture.rates)
        self.assertEqual(json.loads(request["input"][0]["content"]), prompt)
        self.assertEqual(fixture.prompt, prompt)
        chosen = fixture.decision("continue")
        chosen["expected_effect"] = "Keep the working parent without another mutation."
        fixture.invoke(fixture.response(chosen))
        self.assertEqual(json.loads(fixture.calls[1][1]["input"][0]["content"]), prompt)
        self.assertEqual(engine.read(engine.pin(Path(fixture.slots[0]) / "decision.json"))["decision"]["axis"], "continue")

    def test_original_recipe_source_prefix_remains_byte_exact(self):
        raw = Path(controller.__file__).read_bytes()
        self.assertGreater(len(raw), 10844)
        self.assertEqual(sha256(raw[:10844]).hexdigest(), "de63b6bc968e283092fe656abb67b4c8a19d7c97c2e3b6f8bf15428c7122c5cd")

    def test_exact_protocol_diagnostics_are_copied_not_aliased_or_expanded(self):
        value, observation = self.protocol()
        before = deepcopy(value)
        returned = diagnostics.validate_diagnostics(value, observation)
        self.assertEqual(returned, before)
        self.assertEqual(set(returned["execution"]), EXECUTION_FIELDS)
        self.assertEqual(set(returned["review"]), REVIEW_FIELDS)
        returned["execution"]["input_tokens"] = 0
        returned["review"]["reason"] = "NOT_MEASURED"
        self.assertEqual(value, before)

    def test_numeric_diagnostics_require_exact_integer_counts_finite_scores_and_bounds(self):
        value, observation = self.protocol()
        mutations = [("input_tokens", True), ("output_tokens", 1.0), ("records_added", -1),
                     ("initial_records", 10**12+1), ("turns", 0), ("turns", 25),
                     ("tool_calls", False), ("repeated_reads", 3), ("rejected_tools", 3),
                     ("score_out_of_5", True), ("score_out_of_5", float("nan")),
                     ("score_out_of_5", float("inf")), ("score_out_of_5", -1), ("score_out_of_5", 6)]
        for field, bad in mutations:
            with self.subTest(field=field, bad=repr(bad)):
                changed = deepcopy(value); changed["execution"][field] = bad
                with self.assertRaises(ValueError): diagnostics.validate_diagnostics(changed, observation)

    def test_prediction_execution_aggregate_coherence_is_required(self):
        value, observation = self.protocol()
        for kind in ("score", "turns", "tool_calls", "failed"):
            with self.subTest(kind=kind):
                changed = deepcopy(observation)
                if kind == "score": changed["prediction"]["score_out_of_5"] = 4
                elif kind == "failed": changed["execution"]["status"] = "FAILED_NO_RETRY"
                else: changed["execution"][kind] += 1
                with self.assertRaises(ValueError): diagnostics.validate_diagnostics(value, changed)

    def test_unknown_fields_reasons_paths_errors_and_raw_labels_are_rejected(self):
        value, observation = self.protocol()
        for kind in ("schema", "top", "execution", "review", "reason", "metric", "verdict",
                     "missing-execution", "missing-review", "missing-top"):
            with self.subTest(kind=kind):
                changed = deepcopy(value)
                if kind == "schema": changed["schema"] = PRIVATE
                elif kind == "top": changed["raw_qa"] = PRIVATE
                elif kind == "execution": changed["execution"]["path"] = "/private/" + PRIVATE
                elif kind == "review": changed["review"]["rationale"] = PRIVATE
                elif kind == "missing-execution": changed["execution"].pop("input_tokens")
                elif kind == "missing-review": changed["review"].pop("reason")
                elif kind == "missing-top": changed.pop("schema")
                else: changed["review"][kind] = PRIVATE
                with self.assertRaises(ValueError): diagnostics.validate_diagnostics(changed, observation)

    def test_unmeasured_review_keeps_all_deltas_null_and_legacy_verdicts_flexible(self):
        value, observation = self.protocol()
        for verdict in ("continue", "pending", "accept", "reject"):
            changed = deepcopy(value)
            changed["review"] = dict.fromkeys(REVIEW_FIELDS)
            changed["review"].update(verdict=verdict, reason="NOT_MEASURED", benefit_observed=False)
            self.assertEqual(diagnostics.validate_diagnostics(changed, observation), changed)
            for field in ("direction", "min_delta", "observed_delta", "score_delta"):
                bad = deepcopy(changed); bad["review"][field] = 1
                with self.subTest(verdict=verdict, field=field), self.assertRaises(ValueError):
                    diagnostics.validate_diagnostics(bad, observation)

    def test_measured_review_requires_valid_finite_metric_direction_threshold_and_deltas(self):
        value, observation = self.protocol()
        for field, bad in (("metric", "future_accuracy"), ("direction", "flat"),
                           ("min_delta", True), ("min_delta", 0), ("min_delta", float("inf")),
                           ("observed_delta", float("nan")), ("score_delta", -6), ("score_delta", 6),
                           ("benefit_observed", 1)):
            changed = deepcopy(value); changed["review"][field] = bad
            with self.subTest(field=field, bad=repr(bad)), self.assertRaises(ValueError):
                diagnostics.validate_diagnostics(changed, observation)

    def test_benefit_reason_verdict_and_observed_delta_must_agree(self):
        value, observation = self.protocol()
        bad_reviews = [dict(value["review"], observed_delta=0), dict(value["review"], direction="higher"),
            dict(value["review"], score_delta=-1), dict(value["review"], verdict="reject"),
            dict(value["review"], reason="NO_MATCHED_BENEFIT", benefit_observed=False),
            dict(value["review"], verdict="reject", reason="NO_MATCHED_BENEFIT", benefit_observed=False),
            dict(value["review"], reason="UNKNOWN_EFFECT_SEMANTICS", benefit_observed=False)]
        for index, review in enumerate(bad_reviews):
            changed = deepcopy(value); changed["review"] = review
            with self.subTest(case=index), self.assertRaises(ValueError):
                diagnostics.validate_diagnostics(changed, observation)
        for review in (dict(value["review"], observed_delta=0, verdict="reject", reason="NO_MATCHED_BENEFIT", benefit_observed=False),
                       dict(value["review"], score_delta=-1, verdict="reject", reason="NO_MATCHED_BENEFIT", benefit_observed=False),
                       dict(value["review"], direction="higher", observed_delta=4),
                       dict(value["review"], verdict="reject", reason="MECHANICAL_CHECKS_INCOMPLETE_OR_FAILED", benefit_observed=False)):
            changed = deepcopy(value); changed["review"] = review
            self.assertEqual(diagnostics.validate_diagnostics(changed, observation), changed)

    def test_optional_diagnostics_cannot_leak_extras_into_physical_request(self):
        fixture = self.transport_fixture()
        value, observation = self.protocol()
        prompt = deepcopy(fixture.prompt)
        prompt["feedback"] = {"observation": observation, "baseline_score_out_of_5": None, "research_diagnostics": value,
                              "raw_qa": PRIVATE}
        prompt["task_id"] = observation["task_id"]
        prompt["feedback"]["observation"]["prediction"]["ground_truth"] = PRIVATE
        prompt["feedback"]["observation"]["execution"]["raw_error"] = PRIVATE
        original = deepcopy(prompt)
        request = controller.capacity_request(prompt, fixture.rates)
        payload = json.loads(request["input"][0]["content"])
        self.assertEqual(payload["feedback"]["research_diagnostics"], value)
        self.assertNotIn(PRIVATE, json.dumps(request))
        self.assertEqual(prompt, original)
        chosen = fixture.decision("continue")
        fixture.invoke(fixture.response(chosen), prompt=prompt)
        self.assertNotIn(PRIVATE, json.dumps(fixture.calls))
        self.assertEqual(json.loads(fixture.calls[1][1]["input"][0]["content"])["feedback"]["research_diagnostics"], value)

    def test_malformed_diagnostics_refuse_before_count_factory_slot_or_budget_claim(self):
        fixture = self.transport_fixture()
        value, observation = self.protocol()
        prompt = deepcopy(fixture.prompt)
        prompt["task_id"] = observation["task_id"]
        value["review"]["raw_error"] = PRIVATE
        prompt["feedback"] = {"observation": observation, "baseline_score_out_of_5": None, "research_diagnostics": value}
        rows = fixture.budget.db.execute("SELECT id,reserved,charged,status FROM requests ORDER BY rowid").fetchall()
        with self.assertRaises(ValueError): fixture.invoke(fixture.response(), prompt=prompt)
        self.assertEqual(fixture.calls, [])
        fixture.factory.assert_not_called()
        self.assertFalse(Path(fixture.slots[0]).exists())
        self.assertEqual(fixture.budget.db.execute("SELECT id,reserved,charged,status FROM requests ORDER BY rowid").fetchall(), rows)

    def test_actual_Task_feedback_H_benefit_and_R_no_benefit_use_original_numeric_traces(self):
        fixture = self.pending()
        originals = self.original_tree(fixture.raw.role_root)
        native = fixture.raw.native.batch.snapshot()
        rows, calls = fixture.raw.rows(), deepcopy(fixture.raw.calls)
        for index, reason, verdict in ((1, "MATCHED_OPERATIONAL_BENEFIT", "accept"), (2, "NO_MATCHED_BENEFIT", "reject")):
            output = self.stage(fixture, index, "execute")
            feedback = fixture.task.feedback(output, fixture.envelope)
            self.assertEqual(feedback, self.stage(fixture, index, "result_review")["feedback"])
            value = feedback["research_diagnostics"]
            self.assertEqual(value, diagnostics.project_diagnostics(output, feedback["observation"]))
            self.assertEqual(set(value["execution"]), EXECUTION_FIELDS)
            self.assertEqual(set(value["review"]), REVIEW_FIELDS)
            self.assertEqual((value["review"]["reason"], value["review"]["verdict"]), (reason, verdict))
            measured = engine.read(output["effect_review"]["comparison"])
            criterion = measured["declaration"]
            self.assertEqual(value["review"]["observed_delta"], measured["delta"][criterion["metric"]])
            self.assertEqual(value["review"]["score_delta"], measured["score_delta"])
            self.assertEqual(value["review"]["benefit_observed"], measured["benefit_observed"])
            self.assertNotIn(str(fixture.raw.root), json.dumps(feedback))
            self.assertNotIn("ground_truth_numeric", json.dumps(feedback))
        self.assertEqual(self.original_tree(fixture.raw.role_root), originals)
        self.assertEqual(fixture.raw.native.batch.snapshot(), native)
        self.assertEqual((fixture.raw.rows(), fixture.raw.calls), (rows, calls))

    def test_contradictory_retained_receipt_cannot_be_projected_as_next_feedback(self):
        fixture = self.pending(axes=("H",))
        output = self.stage(fixture, 1, "execute")
        receipt = engine.read(output["effect_review"]["review_receipt"])
        receipt["review"].update(decision="reject", reason="NO_MATCHED_BENEFIT", benefit_observed=False)
        wrong = engine.save(fixture.raw.root / "contradictory-review.json", receipt)
        changed = dict(output, capacity_review="reject", effect_review=dict(output["effect_review"], review_receipt=wrong))
        with self.assertRaises(ValueError): fixture.task.feedback(changed, fixture.envelope)

    def test_next_actual_counted_Controller_payload_receives_exact_prior_feedback_digest_and_state(self):
        fixture = self.pending()
        raw = fixture.raw
        first_result = self.stage(fixture, 1, "result_review")
        self.assertEqual(fixture.packets[1]["feedback_sha256"], digest(first_result))
        self.assertEqual(fixture.packets[1]["feedback"], first_result["feedback"])
        previous_state = first_result["state"]
        previous_bytes = Path(previous_state["path"]).read_bytes()
        next_effective = json.loads((Path(raw.slots[3]) / "effective-capacity.json").read_bytes())
        self.assertEqual(next_effective["initial_state"]["sha256"], previous_state["sha256"])
        slots = [str(raw.role_root / "roles" / f"feedback-controller-{i:02d}") for i in (1, 2)]
        context = {"schema": "earnings_capacity_controller_transport_v1", "source_commit": pending_fixture.raw_fixture.SOURCE_COMMIT,
            "root": str(raw.role_root), "rates": raw.rate, "limits": {"max_input_tokens": 10000, "max_output_tokens": 1024, "wall_seconds": 60},
            "cutoff_utc": raw.context["cutoff_utc"], "cutoff_monotonic": raw.context["cutoff_monotonic"], "slots": slots}
        bound = engine.save(raw.root / "feedback-controller-context.json", context)
        actual = controller.CapacityController(bound, budget=raw.budget, client_factory=raw.factory)
        replies = []
        for packet in fixture.packets:
            chosen = {"schema": "earnings_capacity_decision_v1", "axis": "continue", "component": "none",
                "parent_pair_sha256": packet["parent_pair_sha256"], "feedback_sha256": packet["feedback_sha256"],
                "hypothesis": "Inspect retained measured feedback before another bounded trial", "expected_effect": "Continue the functioning parent."}
            replies.append(raw.response([{"type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(chosen)}]}]))
        before_calls, before_rows = len(raw.calls), len(raw.rows())
        raw_replies = [None] * (before_calls // 2) + replies
        with ExitStack() as stack:
            stack.enter_context(patch("earnings_http.http.client.HTTPSConnection", side_effect=raw.fake_connection(raw_replies)))
            stack.enter_context(patch.object(controller, "credential", side_effect=AssertionError("No credentials")))
            stack.enter_context(patch.object(controller, "NightBudget", side_effect=AssertionError("No ledger reopen")))
            for packet, slot in zip(fixture.packets, slots): actual.propose(packet, slot)
        self.assertEqual(len(raw.calls), before_calls + 4)
        self.assertEqual(len(raw.rows()), before_rows + 2)
        self.assertTrue(all(row[2] == "settled" for row in raw.rows()))
        for offset, expected in ((0, fixture.packets[0]), (2, fixture.packets[1])):
            count_payload, physical_payload = [row[1] for row in raw.calls[before_calls+offset:before_calls+offset+2]]
            self.assertIn(GRAMMAR, physical_payload["instructions"])
            self.assertEqual(json.loads(count_payload["input"][0]["content"]), expected)
            self.assertEqual(json.loads(physical_payload["input"][0]["content"]), expected)
        self.assertNotIn("research_diagnostics", fixture.packets[0]["feedback"])
        self.assertEqual(fixture.packets[1]["feedback"]["research_diagnostics"]["review"]["reason"], "MATCHED_OPERATIONAL_BENEFIT")
        self.assertEqual(Path(previous_state["path"]).read_bytes(), previous_bytes)
        self.assertEqual(fixture.packets[1]["feedback_sha256"], digest(first_result))
        self.assertEqual(actual.budget, raw.budget)


if __name__ == "__main__":
    unittest.main()
