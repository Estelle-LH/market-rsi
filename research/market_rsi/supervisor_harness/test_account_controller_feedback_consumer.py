"""Synthetic-only accepted-feedback and original-response recovery checks."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from supervisor_harness import account_controller_feedback_consumer as c
from supervisor_harness.test_learning_checkpoint_assessment import (
    branch as learning_branch, checkpoint, ranked,
)
from supervisor_harness.learning_checkpoint_assessment import assess_checkpoint


NOW = datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc)
PARENT, INCUMBENT, OTHER, CONSUMED, ARCHIVED = [char * 64 for char in "12345"]


class Batch:
    def __init__(self, fixture): self.fixture = fixture
    def snapshot(self):
        feedback = self.fixture.values["feedback"]
        return {"branches": [{"attempt_id": "attempt-02", "stage": self.fixture.stage,
            "feedback_packet": feedback, "feedback_packet_sha256": c._digest(feedback)}]}


class Fixture:
    def __init__(self, root):
        self.root = Path(root).resolve(); self.repo = self.root / "repo"
        self.repo.mkdir(); self.values, self.bindings = {}, {}
        self.stage = "controller_feedback_ready"
        self.source = self.repo / "research/market_rsi/experiments/synthetic.py"
        self.source.parent.mkdir(parents=True); self.source.write_bytes(b"synthetic source")
        self.python = self.root / "synthetic-python"; self.python.write_bytes(b"not executable")
        self.cli = self.root / "synthetic-cli"; self.cli.write_bytes(b"not executable CLI")
        self.write("predictions", b"event,p,y\nfixture,.5,1\n")
        self.write("memory", {"accepted_prior": OTHER, "negative_finding": "direction remained harmful"})
        self.write("history", {"results": [{"sha256": OTHER, "valid": True}]})
        self.write("pool", {"branches": [{"source_sha256": PARENT}, {"source_sha256": OTHER}],
            "C2_consumed": {"source_sha256": CONSUMED}})
        self.write("authority", {"start_utc": "2026-10-05T15:27:11Z", "deadline_utc": c.DEADLINE,
            "selection_cutoff_utc": c.CUTOFF, "limits": {"attempts": 6, "statistical_fits": 24,
                "live_candidate_processes": 2, "threads_per_candidate": 1, "per_attempt_seconds": 900,
                "sampled_rss_bytes": 1073741824, "paid_provider_calls": 0, "paid_provider_spend_usd": "0"},
            "attempts": [{"attempt_id": "attempt-02", "fits_reserved": 4, "actual_fits": 4, "status": "closed"}]})
        self.write("overhead", {"implementation_seconds": 12, "capabilities": "C1/C7 parent schemas only; alpha16; not generic"})
        metric = {"brier": .14, "log_loss": .43, "calibration_slope": 1., "reliability_table": [{"n": 87}]}
        self.write("scorecard", {"task_id": "synthetic-candidate", "research_parent_sha256": PARENT,
            "comparison_incumbent_sha256": INCUMBENT, "historical_event_clock_only": True, "provider_cost_usd": "0", **c.FLAGS,
            "source_denominator": {"events": 195, "dates": 42, "materialized_events": 193, "excluded_events": 2,
                "check_events": 87, "check_dates": 20, "check_game_weeks": 7},
            "aggregate": {"candidate": metric, "raw_market": metric},
            "folds": [{"fold": index + 1, "fit_events": fit, "check_events": check,
                "metrics": {"candidate": metric}, "trainer": {"unneeded": list(range(100))}}
                for index, (fit, check) in enumerate(zip([106, 132, 148, 176], [26, 16, 28, 17]))],
            "paired_grouped_evidence": {"candidate_minus_raw": {"brier": {"equal_event_mean": 0.,
                "schedule_date_interval": [-.01, .01], "observed_game_week_interval": [-.02, .02],
                "by_schedule_date": list(range(20))}}},
            "correction_diagnostics": {"candidate": {"energy": .001, "alignment": -.001}},
            "per_schedule_date_correction_diagnostics": list(range(20))})
        self.write("supplement", {"scorecard_sha256": self.bindings["scorecard"]["sha256"],
            "predictions_sha256": self.bindings["predictions"]["sha256"], "actual_parent_source_sha256": PARENT,
            "aggregate": {"energy": .001, "alignment": -.001}, "parameters": {"beta": .03},
            "per_schedule_date_correction_diagnostics": list(range(20))})
        self.write("review", {"passed": True, "candidate_id": "synthetic-candidate", "source_commit": "fixture-commit",
            "supplement_sha256": self.bindings["supplement"]["sha256"]})
        self.write("request", {"source_commit": "fixture-commit", "candidate_id": "synthetic-candidate",
            "attempt_id": "attempt-02", "module": "experiments.synthetic",
            "files": {"research/market_rsi/experiments/synthetic.py": c.sha(self.source)},
            "memory_sha256": self.bindings["memory"]["sha256"], "python": str(self.python), "python_sha256": c.sha(self.python)})
        self.write("feedback", {"attempt_id": "attempt-02", "candidate_id": "synthetic-candidate",
            "independently_reviewed": True, "review_sha256": self.bindings["review"]["sha256"],
            "scorecard_sha256": self.bindings["scorecard"]["sha256"], "research_parent_sha256": PARENT,
            "comparison_incumbent_sha256": INCUMBENT, "runner_sha256": c.sha(self.source),
            "research_credit": {"value": 2}, "scientific_decision": "REFUTED", "operational_decision": "REVERT",
            "next_pool_selection_hint": {"attempts_remaining": 0, "recommended_active_slots": 0,
                "ranked_research_parents": [{"candidate_id": "eligible-" + source[0], "candidate_sha256": source,
                    "research_credit": 2, "research_outcome": "refute", "route_action": "branch", "followups_remaining": None}
                    for source in [PARENT, OTHER, ARCHIVED]] + [{"candidate_id": "raw-baseline", "candidate_sha256": INCUMBENT,
                    "research_credit": 0, "research_outcome": "baseline", "route_action": "batch_start", "followups_remaining": None}]}})
        self.batch = Batch(self)

    def write(self, role, value):
        path = self.root / (role + (".csv" if isinstance(value, bytes) else ".json"))
        path.write_bytes(value if isinstance(value, bytes) else json.dumps(value, allow_nan=False).encode())
        self.values[role] = value
        self.bindings[role] = {"path": str(path), "sha256": c.sha(path)}

    def prepare(self): return c.prepare_input(self.bindings, self.batch, self.repo, NOW)

    def decision(self, packet):
        return {"schema": "controller_next_decision_v1", "input_sha256": c._digest(packet),
            "feedback_sha256": packet["bindings"]["feedback"]["sha256"], "requested_model": c.MODEL,
            "serving_snapshot": "unknown", "action": "propose_candidate", "candidate_id": "next-synthetic-candidate",
            "question_id": "distinct-synthetic-question", "actual_parent_sha256": PARENT,
            "comparison_incumbent_sha256": INCUMBENT, "hypothesis": "synthetic distinct question",
            "recipe": "non-executable scientific description", "expected_evidence": "paired prediction evidence",
            "evidence_used": [{"sha256": OTHER, "finding": "valid negative direction evidence",
                "choice_consequence": "test conditional rather than repeat exact recipe"}],
            "active_pool": [{"parent_sha256": PARENT, "method_family": "calibration", "reason": "distinct question"},
                {"parent_sha256": OTHER, "method_family": "state", "reason": "method diversity"}],
            "memory_additions": "preserve exact negative finding", "stopped_exact_recipes": "prior exact failed recipe",
            "attribution": "H handoff not R improvement", "resources": {"fits": 4, "seconds": 900, "threads": 1,
                "rss_bytes": 1073741824, "provider_calls": 0},
            "boundary": "resident_train_only_fixed_scoring_no_external_no_protected_no_release"}

    def transport(self, directory, packet, timeout, mutate=None, event=None, completion=None):
        response = self.decision(packet)
        if mutate: mutate(response)
        c.save(directory / "process.json", {"pid": 123, "command": c._command(directory),
            "cli_sha256": c.CLI_SHA, "input_sha256": c._digest(packet), **c._identity()})
        c.save(directory / "response.json", response)
        events = [{"type": "thread.started"}, {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(response)}},
            {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}]
        if event: events.insert(1, event)
        (directory / "events.jsonl").write_text("\n".join(json.dumps(item) for item in events))
        (directory / "stderr").write_bytes(b"")
        record = {"exit_code": 0, "timed_out": False, **c._identity(), "hashes": {name: c.sha(directory / name) for name in
            ["process.json", "events.jsonl", "stderr", "schema.json", "input.json", "response.json"]}}
        if completion: record.update(completion)
        c.save(directory / "completion.json", record)


class ConsumerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.f = Fixture(self.temp.name)
        self.patches = [patch.object(c.subprocess, "check_output", return_value=b"synthetic source"),
            patch.object(c, "CLI", self.f.cli), patch.object(c, "CLI_SHA", c.sha(self.f.cli))]
        for mock in self.patches: mock.start(); self.addCleanup(mock.stop)
        self.packet = self.f.prepare(); self.calls = 0

    def consume(self, transport=None, packet=None, root=None):
        return c.consume(packet or self.packet, root or self.f.root / "calls", batch=self.f.batch,
            repo=self.f.repo, now=NOW, transport=transport or self.transport)

    def transport(self, directory, packet, timeout):
        self.calls += 1; self.assertLessEqual(timeout, 120); self.f.transport(directory, packet, timeout)

    def use_v4(self):
        feedback = deepcopy(self.f.values["feedback"])
        value = checkpoint("parent")
        value["validity"]["review_sha256"] = feedback["review_sha256"]
        value["exploration"]["next_question_sha256"] = None
        original = learning_branch("parent")
        original["review_sha256"] = feedback["review_sha256"]
        assessment = assess_checkpoint(value, original, set())
        feedback.update(schema=c.EVIDENCE_SCHEMA_V4, protocol_version=4, learning_checkpoint=assessment,
                        review_decision="REVERT", execution_outcome="succeeded")
        feedback["research_credit"].update(value=0, question_digest_sha256=original["question_digest_sha256"])
        parents = []
        for label, source in [("parent", PARENT), ("other", OTHER)]:
            record = ranked(label)
            record["candidate_sha256"] = source
            parents.append(record)
        feedback["next_pool_selection_hint"]["ranked_research_parents"] = parents
        self.f.write("feedback", feedback)
        self.packet = self.f.prepare()
        return feedback

    def test_v4_zero_credit_revert_reaches_input_and_shared_parent_recovery(self):
        feedback = self.use_v4()
        self.assertEqual(self.packet["feedback"]["learning_checkpoint"], feedback["learning_checkpoint"])
        self.assertEqual(self.packet["feedback"]["learning_checkpoint"]["prediction_decision"], "REVERT")
        self.assertIsNone(self.packet["feedback"]["learning_checkpoint"]["exploration"]["next_question_sha256"])
        self.assertEqual(set(self.packet["bindings"]), c.ROLES)
        self.assertEqual(self.consume()["actual_parent_sha256"], PARENT)
        self.assertEqual(self.calls, 1)

    def test_v4_opt_in_missing_or_mixed_markers_reject_before_transport(self):
        original = self.use_v4()
        for mutate in [lambda f: f.update(schema="legacy"), lambda f: f.update(protocol_version=True),
                       lambda f: f.update(protocol_version=5), lambda f: f.pop("learning_checkpoint")]:
            feedback = deepcopy(original); mutate(feedback); self.f.write("feedback", feedback)
            with self.assertRaises((ValueError, KeyError)): self.f.prepare()
        self.assertEqual(self.calls, 0)

    def test_v4_consumed_invalid_or_drifted_parent_is_not_valid_evidence(self):
        original = self.use_v4()
        def invalidate(record):
            record["execution_outcome"] = "failed"
            record["learning_checkpoint"]["validity"]["status"] = "invalid"
        for index, mutate in enumerate([lambda r: r.update(followups_remaining=0), invalidate,
                                       lambda r: r.update(review_sha256=CONSUMED),
                                       lambda r: r["learning_checkpoint"]["learning"].update(credit=2)]):
            feedback = deepcopy(original)
            mutate(feedback["next_pool_selection_hint"]["ranked_research_parents"][0])
            self.f.write("feedback", feedback); packet = self.f.prepare()
            with self.assertRaisesRegex(ValueError, "unprovided evidence/parent"):
                self.consume(packet=packet, root=self.f.root / ("v4-invalid-" + str(index)))

    def test_v4_original_response_recovery_ignores_changed_live_pool_and_deadline(self):
        original = self.use_v4()
        response = self.consume()
        changed = deepcopy(original)
        changed["next_pool_selection_hint"]["ranked_research_parents"][0]["followups_remaining"] = 0
        self.f.write("feedback", changed)
        self.f.write("authority", {"closed": True})
        self.f.stage = "result_reviewed"
        recovered = c.consume(self.packet, self.f.root / "calls", batch=self.f.batch, repo=self.f.repo,
                              now=c.DEADLINE, transport=lambda *args: self.fail("never resample"))
        self.assertEqual(recovered, response)
        self.assertEqual(self.calls, 1)

    def test_v4_checkpoint_projection_cannot_inflate_credit_or_reclassify_result(self):
        original = self.use_v4()
        for mutate in [lambda f: f["research_credit"].update(value=2),
                       lambda f: f["learning_checkpoint"].update(prediction_decision="KEEP"),
                       lambda f: f["learning_checkpoint"]["validity"].update(review_sha256=CONSUMED)]:
            feedback = deepcopy(original); mutate(feedback); self.f.write("feedback", feedback)
            with self.assertRaises(ValueError): self.f.prepare()
        self.assertEqual(self.calls, 0)

    def test_v4_hash_mention_is_not_verified_citation_or_new_authority(self):
        feedback = self.use_v4()
        feedback["learning_checkpoint"]["learning"]["evidence_sha256"] = "f" * 64
        self.f.write("feedback", feedback); packet = self.f.prepare()
        def mutate(response): response["evidence_used"][0]["sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "unprovided evidence/parent"):
            self.consume(lambda directory, value, timeout: self.f.transport(directory, value, timeout, mutate=mutate),
                         packet=packet, root=self.f.root / "v4-unverified-citation")
        with self.assertRaisesRegex(ValueError, "outer selection stop"):
            c.check_budget(self.f.values["authority"], c.CUTOFF)

    def test_direct_numbers_compact_and_bound(self):
        self.assertEqual(self.packet["numerical"]["aggregate"]["candidate"]["brier"], .14)
        self.assertEqual(len(self.packet["numerical"]["folds"]), 4)
        self.assertNotIn("trainer", self.packet["numerical"]["folds"][0])
        self.assertNotIn("reliability_table", self.packet["numerical"]["aggregate"]["candidate"])
        self.assertNotIn("by_schedule_date", self.packet["numerical"]["paired_grouped_evidence"]["candidate_minus_raw"]["brier"])
        self.assertEqual(set(self.packet["omitted_from_prompt"]), c.OMITTED)
        self.assertEqual(set(self.packet["bindings"]), c.ROLES)
        self.assertIn("not generic", self.packet["overhead"]["capabilities"])

    def test_once_original_ack_and_parallel(self):
        results, errors = [], []
        def invoke():
            try: results.append(self.consume())
            except Exception as error: errors.append(error)
        threads = [threading.Thread(target=invoke) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(errors, []); self.assertEqual(len(results), 2); self.assertEqual(self.calls, 1)
        self.assertEqual(self.consume(), results[0]); self.assertEqual(self.calls, 1)
        ack = c._json(next((self.f.root / "calls").glob("*/ack.json")).read_bytes())
        self.assertEqual(ack["usage"]["input_tokens"], 10); self.assertEqual(ack["serving_snapshot"], "unknown")

    def test_post_claim_uncertainty_never_resamples(self):
        def crash(*args): self.calls += 1; raise RuntimeError("capacity unknown")
        with self.assertRaisesRegex(RuntimeError, "capacity"): self.consume(crash)
        with self.assertRaises(FileNotFoundError): self.consume()
        self.assertEqual(self.calls, 1)
        failure = c._json(next((self.f.root / "calls").glob("*/failure.json")).read_bytes())
        self.assertTrue(failure["no_resample"])

    def test_completed_original_crash_before_ack_recovers(self):
        original = c.save
        def fail_ack(path, value):
            if Path(path).name == "ack.json": raise RuntimeError("ack crash")
            original(path, value)
        with patch.object(c, "save", side_effect=fail_ack):
            with self.assertRaisesRegex(RuntimeError, "ack crash"): self.consume()
        response = self.consume(); self.assertEqual(response["requested_model"], c.MODEL); self.assertEqual(self.calls, 1)

    def test_timeout_tool_and_malformed_preserved(self):
        cases = [({"completion": {"timed_out": True, "exit_code": -9}}, RuntimeError),
            ({"event": {"type": "item.completed", "item": {"type": "command_execution"}}}, ValueError),
            ({"event": {"type": "turn.failed"}}, ValueError),
            ({"mutate": lambda response: response.update(extra="forbidden")}, ValueError)]
        for index, (kwargs, error_type) in enumerate(cases):
            with self.subTest(index=index):
                root = self.f.root / ("failure-" + str(index))
                def transport(directory, packet, timeout): self.calls += 1; self.f.transport(directory, packet, timeout, **kwargs)
                with self.assertRaises(error_type): self.consume(transport, root=root)
                with self.assertRaises(error_type): self.consume(root=root)
        self.assertEqual(self.calls, 4)

    def test_parent_evidence_pool_and_authority_response_rejections(self):
        mutations = [lambda r: r.update(actual_parent_sha256=CONSUMED), lambda r: r.update(serving_snapshot="invented"),
            lambda r: r["evidence_used"][0].update(sha256="f" * 64),
            lambda r: r["resources"].update(fits=5), lambda r: r["active_pool"][1].update(method_family="calibration"),
            lambda r: r["active_pool"][1].update(parent_sha256=PARENT), lambda r: r.update(boundary="open_final")]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                def transport(directory, packet, timeout): self.f.transport(directory, packet, timeout, mutate=mutate)
                with self.assertRaises(ValueError): self.consume(transport, root=self.f.root / ("invalid-" + str(index)))

    def test_unreviewed_hash_source_and_numeric_drift_rejected(self):
        self.f.stage = "result_reviewed"
        with self.assertRaises(ValueError): self.f.prepare()
        self.f.stage = "controller_feedback_ready"
        for role, field, value in [("review", "passed", False), ("supplement", "actual_parent_source_sha256", OTHER),
            ("request", "python_sha256", OTHER), ("scorecard", "sealed_final_opened", True)]:
            old = deepcopy(self.f.values[role]); changed = deepcopy(old); changed[field] = value; self.f.write(role, changed)
            with self.subTest(role=role):
                with self.assertRaises(ValueError): self.f.prepare()
            self.f.write(role, old)
        self.f.source.write_bytes(b"drift")
        with self.assertRaises(ValueError): self.f.prepare()

    def test_commit_bytes_not_current_head(self):
        with patch.object(c.subprocess, "check_output", return_value=b"wrong historic bytes"):
            with self.assertRaisesRegex(ValueError, "commit"): self.f.prepare()
        self.assertEqual(self.f.prepare(), self.packet)

    def test_same_id_packet_or_original_file_drift_no_recall(self):
        self.consume(); changed = deepcopy(self.packet); changed["numerical"]["aggregate"]["candidate"]["brier"] = .1
        with self.assertRaisesRegex(ValueError, "same feedback changed"): self.consume(packet=changed)
        directory = next((self.f.root / "calls").glob("*/claim.json")).parent
        (directory / "response.json").write_text("{}")
        with self.assertRaises(ValueError): self.consume()
        self.assertEqual(self.calls, 1)

    def test_budget_caps_cutoff_types_and_slots(self):
        authority = self.f.values["authority"]
        c.check_budget(authority, NOW)
        for mutate in [lambda a: a["limits"].update(attempts=7), lambda a: a.update(deadline_utc="later"),
            lambda a: a.update(attempts=[{"attempt_id": str(i), "fits_reserved": 4, "actual_fits": 4, "status": "closed"} for i in range(6)]),
            lambda a: a.update(attempts=[{"attempt_id": str(i), "fits_reserved": 4, "actual_fits": 0, "status": "running"} for i in range(2)]),
            lambda a: a.update(attempts=[{"attempt_id": str(i), "fits_reserved": 4, "actual_fits": 0, "status": "execution_reserved"} for i in range(2)]),
            lambda a: a["attempts"][0].update(actual_fits=True), lambda a: a["attempts"][0].update(fits_reserved=5)]:
            changed = deepcopy(authority); mutate(changed)
            with self.assertRaises(ValueError): c.check_budget(changed, NOW)
        for moment in ["2026-10-05T15:00:00Z", c.CUTOFF, c.DEADLINE]:
            with self.assertRaises(ValueError): c.check_budget(authority, moment)

    def test_strict_json_and_cli_path_guard(self):
        for raw in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}']:
            with self.assertRaises(ValueError): c._json(raw)
        with patch.object(c, "CLI_SHA", OTHER):
            with self.assertRaisesRegex(ValueError, "CLI"): self.consume()
        alias = self.f.root / "alias"; alias.symlink_to(self.f.root)
        with self.assertRaises(ValueError): self.consume(root=alias / "calls")

    def test_transport_frozen_args_and_timeout_process_truth(self):
        directory = self.f.root / "transport"; directory.mkdir()
        c.save(directory / "input.json", self.packet); c.save(directory / "schema.json", c.SCHEMA)
        prompts = []
        class Child:
            pid, returncode = 321, -9
            def communicate(self, data, timeout):
                prompts.append(data.decode()); raise subprocess.TimeoutExpired("synthetic", timeout)
            def poll(self): return None
            def wait(self, timeout): return self.returncode
        with patch.object(c.subprocess, "Popen", return_value=Child()) as popen, patch.object(c.os, "killpg") as kill:
            c._transport(directory, self.packet, 12)
        command = popen.call_args.args[0]
        self.assertEqual(command, c._command(directory)); self.assertIn("--ignore-user-config", command)
        self.assertTrue(popen.call_args.kwargs["start_new_session"]); kill.assert_called_once()
        self.assertIn("input_sha256=" + c._digest(self.packet), prompts[0])
        self.assertIn("feedback_sha256=" + self.packet["bindings"]["feedback"]["sha256"], prompts[0])
        self.assertIn("do not calculate hashes", prompts[0])
        for guidance in ["Within the still-open budget", "reasonable distinct small actual prediction hypothesis",
            "even without prior improvement", "first small hypotheses do not require prior gains",
            "Negative scores or implementation overhead are not reasons to stop", "Supervisor owns allowed stop conditions",
            "Methods remain open", "no forced R modification or scoring change",
            "specific genuinely necessary next operation", "not a disguised voluntary stop", "a request grants no authority"]:
            self.assertIn(guidance, prompts[0])
        completion = c._json((directory / "completion.json").read_bytes())
        self.assertTrue(completion["timed_out"]); self.assertEqual(completion["exit_code"], -9)
        self.assertNotIn("response.json", completion["hashes"])

    def test_completion_command_stdout_schema_and_ack_drift(self):
        for index, name in enumerate(["process.json", "events.jsonl", "schema.json", "ack.json"]):
            root = self.f.root / ("drift-" + str(index)); self.consume(root=root)
            directory = next(root.glob("*/claim.json")).parent
            (directory / name).write_text("{}")
            with self.subTest(name=name):
                with self.assertRaises((ValueError, KeyError)): self.consume(root=root)
        self.assertEqual(self.calls, 4)

    def test_bound_numeric_geometry_and_csv_supplement_drift(self):
        for role, mutate in [("scorecard", lambda r: r["source_denominator"].update(check_events=86)),
            ("scorecard", lambda r: r["folds"][0].update(fit_events=105)),
            ("scorecard", lambda r: r.update(historical_event_clock_only=False)),
            ("supplement", lambda r: r.update(predictions_sha256=OTHER))]:
            original = deepcopy(self.f.values[role]); changed = deepcopy(original); mutate(changed)
            self.f.write(role, changed)
            with self.assertRaises(ValueError): self.f.prepare()
            self.f.write(role, original)

    def test_original_recovery_after_live_authority_source_and_deadline_change(self):
        original = self.consume(); self.assertEqual(self.calls, 1)
        self.f.write("authority", {"changed": "all slots consumed"})
        self.f.source.write_bytes(b"later source checkpoint")
        response = c.consume(self.packet, self.f.root / "calls", batch=self.f.batch, repo=self.f.repo,
            now="2026-10-05T20:00:00Z", transport=lambda *args: self.fail("must never resample"))
        self.assertEqual(response, original); self.assertEqual(self.calls, 1)

    def test_changed_claim_and_saved_input_reject_without_transport(self):
        for index, name in enumerate(["claim.json", "input.json"]):
            root = self.f.root / ("claimed-" + str(index)); self.consume(root=root)
            directory = next(root.glob("*/claim.json")).parent
            (directory / name).write_text("{}")
            with self.assertRaises(ValueError): self.consume(root=root)
        self.assertEqual(self.calls, 2)

    def test_restore_eligible_archive_not_current_pool_and_reject_consumed(self):
        def restore(response):
            response["actual_parent_sha256"] = ARCHIVED
            response["active_pool"][0]["parent_sha256"] = ARCHIVED
        response = self.consume(lambda directory, packet, timeout: self.f.transport(directory, packet, timeout, mutate=restore))
        self.assertEqual(response["actual_parent_sha256"], ARCHIVED)
        self.assertNotIn(ARCHIVED, {item["source_sha256"] for item in self.packet["pool"]["branches"]})
        self.assertEqual(self.packet["feedback"]["next_pool_selection_hint"]["attempts_remaining"], 0)

    def test_credit_alone_and_ineligible_route_do_not_grant_parent(self):
        old = deepcopy(self.f.values["feedback"])
        for index, record in enumerate([{"candidate_id": "consumed", "candidate_sha256": CONSUMED, "research_credit": 1,
                "research_outcome": "inconclusive", "route_action": "bounded_followup", "followups_remaining": 0},
            {"candidate_id": "credit-alone", "candidate_sha256": c.sha(self.f.source), "research_credit": 2,
                "research_outcome": "refute", "route_action": "cooldown", "followups_remaining": None}]):
            changed = deepcopy(old); changed["next_pool_selection_hint"]["ranked_research_parents"].append(record)
            self.f.write("feedback", changed); packet = self.f.prepare()
            def mutate(response): response.update(actual_parent_sha256=record["candidate_sha256"])
            with self.assertRaises(ValueError):
                self.consume(lambda directory, value, timeout: self.f.transport(directory, value, timeout, mutate=mutate),
                    packet=packet, root=self.f.root / ("route-" + str(index)))
        self.f.write("feedback", old)

    def test_exact_actual_string_zero_cost_not_numeric_or_bool_coercion(self):
        self.assertEqual(self.f.prepare()["numerical"]["aggregate"]["candidate"]["brier"], .14)
        for cost in ["1", 0, False, 0.0, "0.0", None]:
            card = deepcopy(self.f.values["scorecard"]); card["provider_cost_usd"] = cost
            self.f.write("scorecard", card)
            supplement = deepcopy(self.f.values["supplement"])
            supplement["scorecard_sha256"] = self.f.bindings["scorecard"]["sha256"]; self.f.write("supplement", supplement)
            review = deepcopy(self.f.values["review"])
            review["supplement_sha256"] = self.f.bindings["supplement"]["sha256"]; self.f.write("review", review)
            feedback = deepcopy(self.f.values["feedback"])
            feedback.update(scorecard_sha256=self.f.bindings["scorecard"]["sha256"], review_sha256=self.f.bindings["review"]["sha256"])
            self.f.write("feedback", feedback)
            with self.subTest(cost=cost):
                with self.assertRaisesRegex(ValueError, "historical/cost"): self.f.prepare()

    def test_consumer_source_and_scope_bound_no_code_drift_recovery(self):
        self.consume(); directory = next((self.f.root / "calls").glob("*/claim.json")).parent
        for name in ["claim.json", "process.json", "completion.json"]:
            receipt = c._json((directory / name).read_bytes())
            for key, value in c._identity().items(): self.assertEqual(receipt[key], value)
        with patch.object(c, "_identity", return_value={"consumer_source_sha256": OTHER, "scope_sha256": c.SCOPE_SHA}):
            with self.assertRaisesRegex(ValueError, "same feedback changed"): self.consume()
        self.assertEqual(self.calls, 1)

    def test_post_spawn_metadata_communicate_and_interruption_cleanup_once(self):
        for index, trigger in enumerate(["process", "communicate", "interrupt"]):
            root = self.f.root / ("cleanup-" + str(index)); original = c.save
            class Child:
                pid, returncode = 999, -9
                def poll(self): return None
                def communicate(self, data, timeout):
                    if trigger == "interrupt": raise KeyboardInterrupt("synthetic interrupted")
                    raise OSError("synthetic communicate error")
                def wait(self, timeout): self.wait_timeout = timeout; return self.returncode
            child = Child()
            def fail_receipt(path, value):
                if trigger == "process" and Path(path).name == "process.json": raise OSError("synthetic metadata error")
                original(path, value)
            with patch.object(c.subprocess, "Popen", return_value=child) as popen, patch.object(c.os, "killpg") as kill, patch.object(c, "save", side_effect=fail_receipt):
                with self.assertRaises((OSError, KeyboardInterrupt)): self.consume(c._transport, root=root)
                self.assertEqual(popen.call_count, 1); kill.assert_called_once_with(child.pid, c.signal.SIGKILL)
                self.assertEqual(child.wait_timeout, 5)
                with self.assertRaises(FileNotFoundError): self.consume(c._transport, root=root)
                self.assertEqual(popen.call_count, 1)
            failure = c._json(next(root.glob("*/failure.json")).read_bytes())
            self.assertTrue(failure["no_resample"])

    def test_cleanup_reap_timeout_is_bounded_no_second_cleanup(self):
        class Child:
            pid, returncode = 555, None
            def poll(self): return None
            def communicate(self, data, timeout): raise subprocess.TimeoutExpired("synthetic", timeout)
            def wait(self, timeout): raise subprocess.TimeoutExpired("bounded-reap", timeout)
        with patch.object(c.subprocess, "Popen", return_value=Child()), patch.object(c.os, "killpg") as kill:
            with self.assertRaisesRegex(RuntimeError, "bounded cleanup"): self.consume(c._transport)
            kill.assert_called_once()

    def test_service_schema_nodes_have_explicit_consistent_types(self):
        nodes = []
        def walk(node):
            nodes.append(node)
            self.assertIn(node["type"], {"object", "array", "string", "integer"})
            if "const" in node:
                expected = str if node["type"] == "string" else int
                self.assertIs(type(node["const"]), expected)
            if "enum" in node:
                self.assertEqual(node["type"], "string")
                self.assertTrue(all(type(value) is str for value in node["enum"]))
            for child in node.get("properties", {}).values(): walk(child)
            if "items" in node: walk(node["items"])
        walk(c.SCHEMA); self.assertGreater(len(nodes), 20)
        decision = self.f.decision(self.packet); c._validate(decision, c.SCHEMA)
        self.assertEqual(set(c.SCHEMA["required"]), set(decision))
        self.assertIs(c.SCHEMA["additionalProperties"], False)
        for name, value in {"schema": "controller_next_decision_v1", "requested_model": "gpt-6.1-sol",
            "serving_snapshot": "unknown", "boundary": "resident_train_only_fixed_scoring_no_external_no_protected_no_release"}.items():
            self.assertEqual(c.SCHEMA["properties"][name]["const"], value)
        self.assertEqual(c.SCHEMA["properties"]["action"]["enum"], ["propose_candidate", "request_closed_authority"])
        resource_nodes = c.SCHEMA["properties"]["resources"]["properties"]
        self.assertEqual({name: node["const"] for name, node in resource_nodes.items()},
            {"fits": 4, "seconds": 900, "threads": 1, "rss_bytes": 1073741824, "provider_calls": 0})

    def test_open_budget_voluntary_stop_rejected_original_preserved_no_resample(self):
        c.check_budget(self.packet["authority"], NOW)
        decision = self.f.decision(self.packet); decision["action"] = "stop_in_scope"
        with self.assertRaisesRegex(ValueError, "response enum drift"): c._validate(decision, c.SCHEMA)
        def stopped(directory, packet, timeout):
            self.calls += 1
            self.f.transport(directory, packet, timeout, mutate=lambda response: response.update(action="stop_in_scope"))
        with self.assertRaisesRegex(ValueError, "response enum drift"): self.consume(stopped)
        with self.assertRaisesRegex(ValueError, "response enum drift"): self.consume()
        self.assertEqual(self.calls, 1)
        directory = next((self.f.root / "calls").glob("*/claim.json")).parent
        self.assertEqual(c._json((directory / "response.json").read_bytes())["action"], "stop_in_scope")
        self.assertTrue(c._json((directory / "failure.json").read_bytes())["no_resample"])
        self.assertFalse((directory / "ack.json").exists())

    def test_proposal_and_closed_request_valid_typed_bounded_not_authority(self):
        original_authority = deepcopy(self.f.values["authority"])
        for action in ["propose_candidate", "request_closed_authority"]:
            decision = self.f.decision(self.packet); decision["action"] = action
            c._validate(decision, c.SCHEMA)
            def selected(directory, packet, timeout):
                self.calls += 1
                self.f.transport(directory, packet, timeout, mutate=lambda response: response.update(action=action))
            response = self.consume(selected, root=self.f.root / action)
            self.assertEqual(response["action"], action)
            self.assertEqual(response["resources"], {"fits":4,"seconds":900,"threads":1,"rss_bytes":1073741824,"provider_calls":0})
            self.assertEqual(response["boundary"], "resident_train_only_fixed_scoring_no_external_no_protected_no_release")
            self.assertEqual(self.f.values["authority"], original_authority)
        self.assertEqual(self.calls, 2)

    def pilot(self):
        binding = c.prospective_pilot_binding()
        authority = {"batch_id": binding["batch_id"], "start_utc": binding["start_utc"],
                     "deadline_utc": binding["deadline_utc"], "selection_cutoff_utc": binding["selection_cutoff_utc"],
                     "limits": deepcopy(binding["limits"]), "attempts": []}
        self.f.write("authority", authority)
        now = datetime(2026, 10, 5, 21, 20, tzinfo=timezone.utc)
        packet = c.prepare_input(self.f.bindings, self.f.batch, self.f.repo, now, prospective_binding=binding)
        return binding, authority, packet, now

    def test_prospective_exact_pilot_is_explicit_copy_and_keeps_legacy_defaults(self):
        original_deadline, original_cutoff = c.DEADLINE, c.CUTOFF
        binding, authority, packet, now = self.pilot()
        self.assertEqual((original_deadline, original_cutoff), ("2026-10-05T19:27:11Z", "2026-10-05T19:12:11Z"))
        self.assertEqual(binding["limits"]["attempts"], 3)
        self.assertEqual(binding["limits"]["statistical_fits"], 12)
        self.assertEqual(packet["prospective_budget_binding"], binding)
        self.assertNotIn("prospective_budget_binding", self.packet)
        binding["limits"]["attempts"] = 99
        self.assertEqual(packet["prospective_budget_binding"]["limits"]["attempts"], 3)
        self.assertEqual(c.prospective_pilot_binding()["limits"]["attempts"], 3)
        with self.assertRaisesRegex(ValueError, "outer authority changed"):
            c.check_budget(authority, now)
        self.assertEqual((c.DEADLINE, c.CUTOFF), (original_deadline, original_cutoff))

    def test_prospective_binding_types_window_identity_and_selfgrant_fail_closed(self):
        binding, authority, packet, now = self.pilot()
        mutations = [lambda b: b.update(batch_id="unapproved"), lambda b: b.update(start_utc="2026-10-05T21:00:00Z"),
                     lambda b: b.update(deadline_utc="2026-10-05T23:00:00Z"), lambda b: b.update(authority_granted=True),
                     lambda b: b["limits"].update(attempts=4), lambda b: b["limits"].update(statistical_fits=16),
                     lambda b: b["limits"].update(threads_per_candidate=True), lambda b: b["limits"].update(threads_per_candidate=1.0),
                     lambda b: b["limits"].update(paid_provider_calls=1)]
        for mutate in mutations:
            changed = deepcopy(binding); mutate(changed)
            with self.assertRaises(ValueError): c.check_budget(authority, now, prospective_binding=changed)
        for field, value in [("batch_id", "wrong"), ("start_utc", "2026-10-05T21:09:54Z"),
                             ("selection_cutoff_utc", "2026-10-05T22:25:55Z"), ("deadline_utc", "2026-10-05T22:40:55Z")]:
            changed = deepcopy(authority); changed[field] = value
            with self.assertRaises(ValueError): c.check_budget(changed, now, prospective_binding=binding)
        changed = deepcopy(authority); changed["limits"]["threads_per_candidate"] = True
        with self.assertRaises(ValueError): c.check_budget(changed, now, prospective_binding=binding)
        self.assertEqual(self.calls, 0)

    def test_prospective_three_twelve_cutoff_concurrency_and_fit_types(self):
        binding, authority, packet, now = self.pilot()
        c.check_budget(authority, binding["start_utc"], prospective_binding=binding)
        for moment in ("2026-10-05T21:09:54Z", binding["selection_cutoff_utc"], binding["deadline_utc"]):
            with self.assertRaisesRegex(ValueError, "outer selection stop"):
                c.check_budget(authority, moment, prospective_binding=binding)
        changed = deepcopy(authority)
        changed["attempts"] = [{"attempt_id": str(i), "fits_reserved": 4, "actual_fits": 4, "status": "closed"} for i in range(2)]
        c.check_budget(changed, now, prospective_binding=binding)
        changed["attempts"].append({"attempt_id": "third", "fits_reserved": 4, "actual_fits": 4, "status": "closed"})
        with self.assertRaisesRegex(ValueError, "outer selection stop"):
            c.check_budget(changed, now, prospective_binding=binding)
        for status in ("claimed", "running", "execution_claimed", "execution_reserved"):
            changed["attempts"] = [{"attempt_id": str(i), "fits_reserved": 4, "actual_fits": 0, "status": status} for i in range(2)]
            with self.assertRaisesRegex(ValueError, "concurrency"):
                c.check_budget(changed, now, prospective_binding=binding)
        changed["attempts"] = [{"attempt_id": "one", "fits_reserved": 4, "actual_fits": True, "status": "closed"}]
        with self.assertRaisesRegex(ValueError, "invalid actual/reserved"):
            c.check_budget(changed, now, prospective_binding=binding)

    def test_prospective_once_claim_identity_timeout_and_original_recovery(self):
        binding, authority, packet, now = self.pilot()
        root = self.f.root / "pilot-calls"
        def transport(directory, value, timeout):
            self.calls += 1
            self.assertEqual(timeout, 120.)
            self.assertEqual(value["prospective_budget_binding"], binding)
            self.f.transport(directory, value, timeout)
        result = c.consume(packet, root, batch=self.f.batch, repo=self.f.repo, now=now, transport=transport, prospective_binding=binding)
        directory = next(root.glob("*/claim.json")).parent
        claim = c._json((directory / "claim.json").read_bytes())
        self.assertEqual(claim["prospective_budget_binding_sha256"], c._digest(binding))
        self.assertEqual(claim["input_sha256"], c._digest(packet))
        self.f.write("authority", {"closed": True})
        self.f.source.write_bytes(b"later-source")
        recovered = c.consume(packet, root, batch=self.f.batch, repo=self.f.repo, now="2026-10-05T23:00:00Z",
                              transport=lambda *args: self.fail("no repeat"), prospective_binding=binding)
        self.assertEqual(recovered, result)
        self.assertEqual(self.calls, 1)
        with self.assertRaisesRegex(ValueError, "explicit prospective"):
            c.consume(packet, root, batch=self.f.batch, repo=self.f.repo, now=now, transport=transport)
        changed = deepcopy(binding); changed["deadline_utc"] = "2026-10-05T23:00:00Z"
        with self.assertRaisesRegex(ValueError, "binding drift"):
            c.consume(packet, root, batch=self.f.batch, repo=self.f.repo, now=now, transport=transport, prospective_binding=changed)
        changed_claim = deepcopy(claim); changed_claim["prospective_budget_binding_sha256"] = OTHER
        (directory / "claim.json").write_text(json.dumps(changed_claim))
        with self.assertRaisesRegex(ValueError, "same feedback changed"):
            c.consume(packet, root, batch=self.f.batch, repo=self.f.repo, now=now, transport=transport, prospective_binding=binding)
        self.assertEqual(self.calls, 1)

    def test_prospective_packet_drift_or_missing_explicit_binding_never_transports(self):
        binding, authority, packet, now = self.pilot()
        for mutate in [lambda p: p.pop("prospective_budget_binding"),
                       lambda p: p["prospective_budget_binding"]["limits"].update(threads_per_candidate=True),
                       lambda p: p["prospective_budget_binding"].update(batch_id="different")]:
            changed = deepcopy(packet); mutate(changed)
            with self.assertRaisesRegex(ValueError, "explicit prospective"):
                c.consume(changed, self.f.root / "no-call", batch=self.f.batch, repo=self.f.repo, now=now,
                          transport=self.transport, prospective_binding=binding)
        with self.assertRaisesRegex(ValueError, "explicit prospective"):
            c.consume(self.packet, self.f.root / "no-call", batch=self.f.batch, repo=self.f.repo, now=now,
                      transport=self.transport, prospective_binding=binding)
        self.assertFalse((self.f.root / "no-call").exists())
        self.assertEqual(self.calls, 0)

    def test_prospective_capacity_failure_is_original_once_only_no_retry(self):
        binding, authority, packet, now = self.pilot()
        def crash(*args):
            self.calls += 1
            raise RuntimeError("synthetic capacity unknown")
        kwargs = {"batch": self.f.batch, "repo": self.f.repo, "now": now, "prospective_binding": binding}
        with self.assertRaisesRegex(RuntimeError, "capacity"):
            c.consume(packet, self.f.root / "pilot-failure", transport=crash, **kwargs)
        with self.assertRaises(FileNotFoundError):
            c.consume(packet, self.f.root / "pilot-failure", transport=self.transport, **kwargs)
        self.assertEqual(self.calls, 1)
        failure = c._json(next((self.f.root / "pilot-failure").glob("*/failure.json")).read_bytes())
        self.assertTrue(failure["no_resample"])

    def test_prospective_frozen_validation_repo_not_changed_canonical_source(self):
        binding, authority, packet, now = self.pilot()
        canonical = self.f.root / "current-canonical-repo"
        current_source = canonical / "research/market_rsi/experiments/synthetic.py"
        current_source.parent.mkdir(parents=True)
        current_source.write_bytes(b"later canonical source")
        # The supplied frozen validation checkout retains original bytes/commit.
        self.assertEqual(c.prepare_input(self.f.bindings, self.f.batch, self.f.repo, now, prospective_binding=binding), packet)
        with self.assertRaisesRegex(ValueError, "source byte drift"):
            c.prepare_input(self.f.bindings, self.f.batch, canonical, now, prospective_binding=binding)
        with patch.object(c.subprocess, "check_output", return_value=b"different frozen commit bytes"):
            with self.assertRaisesRegex(ValueError, "source commit drift"):
                c.prepare_input(self.f.bindings, self.f.batch, self.f.repo, now, prospective_binding=binding)
        changed_request = deepcopy(self.f.values["request"])
        changed_request["files"] = {"../outside.py": OTHER}
        self.f.write("request", changed_request)
        with self.assertRaises(ValueError):
            c.prepare_input(self.f.bindings, self.f.batch, self.f.repo, now, prospective_binding=binding)
        self.assertEqual(self.calls, 0)


    def continuation(self):
        binding = c.continuation_pilot_binding()
        authority = {key: deepcopy(binding[key]) for key in ("batch_id", "start_utc", "selection_cutoff_utc", "deadline_utc", "limits")}
        authority["attempts"] = []
        self.f.write("authority", authority)
        now = datetime(2026, 10, 5, 22, 40, tzinfo=timezone.utc)
        packet = c.prepare_input(self.f.bindings, self.f.batch, self.f.repo, now, prospective_binding=binding)
        return binding, authority, packet, now

    def test_continuation_exact_copy_preserves_original_defaults_and_rejects_selfgrant(self):
        binding, authority, packet, now = self.continuation()
        self.assertEqual((binding["batch_id"], binding["start_utc"], binding["selection_cutoff_utc"], binding["deadline_utc"]),
            ("market-rsi-learning-checkpoint-continuation-20261005-01", "2026-10-05T22:32:32Z", "2026-10-05T23:47:32Z", "2026-10-06T00:02:32Z"))
        self.assertEqual(binding["limits"], {"attempts": 2, "statistical_fits": 8, "live_candidate_processes": 2,
            "threads_per_candidate": 1, "per_attempt_seconds": 900, "sampled_rss_bytes": 1073741824,
            "paid_provider_calls": 0, "paid_provider_spend_usd": "0"})
        self.assertEqual((c.DEADLINE, c.CUTOFF), ("2026-10-05T19:27:11Z", "2026-10-05T19:12:11Z"))
        self.assertEqual(c.prospective_pilot_binding()["limits"]["attempts"], 3)
        self.assertNotIn("prospective_budget_binding", self.packet)
        for field, value in (("attempts", True), ("attempts", 2.0), ("statistical_fits", 12),
                ("paid_provider_calls", 1), ("paid_provider_spend_usd", 0), ("threads_per_candidate", 2)):
            changed = deepcopy(binding); changed["limits"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                c.check_budget(authority, now, prospective_binding=changed)
        for field, value in (("schema", "other"), ("batch_id", "other"), ("authority_granted", True),
                ("deadline_utc", "2026-10-06T01:00:00Z")):
            changed = deepcopy(binding); changed[field] = value
            with self.assertRaises(ValueError): c.check_budget(authority, now, prospective_binding=changed)
        binding["limits"]["attempts"] = 999
        self.assertEqual(packet["prospective_budget_binding"]["limits"]["attempts"], 2)
        self.assertEqual(c.continuation_pilot_binding()["limits"]["attempts"], 2)
        self.assertEqual(self.calls, 0)

    def test_continuation_two_eight_clock_caps_cross_window_and_duplicate_fit_guards(self):
        binding, authority, packet, now = self.continuation()
        c.check_budget(authority, binding["start_utc"], prospective_binding=binding)
        for moment in ("2026-10-05T22:32:31Z", binding["selection_cutoff_utc"], binding["deadline_utc"]):
            with self.assertRaisesRegex(ValueError, "selection stop"):
                c.check_budget(authority, moment, prospective_binding=binding)
        for other in (None, c.prospective_pilot_binding()):
            with self.assertRaises(ValueError): c.check_budget(authority, now, prospective_binding=other)
        old = c.prospective_pilot_binding()
        old_authority = {key: deepcopy(old[key]) for key in ("batch_id", "start_utc", "selection_cutoff_utc", "deadline_utc", "limits")}
        old_authority["attempts"] = []
        with self.assertRaises(ValueError): c.check_budget(old_authority, now, prospective_binding=old)
        with self.assertRaises(ValueError): c.check_budget(old_authority, now, prospective_binding=binding)
        authority["attempts"] = [{"attempt_id": "one", "fits_reserved": 4, "actual_fits": 4, "status": "closed"}]
        c.check_budget(authority, now, prospective_binding=binding)
        authority["attempts"].append({"attempt_id": "two", "fits_reserved": 4, "actual_fits": 4, "status": "closed"})
        with self.assertRaisesRegex(ValueError, "selection stop"):
            c.check_budget(authority, now, prospective_binding=binding)
        authority["attempts"] = [{"attempt_id": "one", "fits_reserved": 4, "actual_fits": True, "status": "closed"}]
        with self.assertRaisesRegex(ValueError, "invalid actual/reserved"):
            c.check_budget(authority, now, prospective_binding=binding)
        authority["limits"]["threads_per_candidate"] = True
        with self.assertRaises(ValueError): c.check_budget(authority, now, prospective_binding=binding)

    def test_continuation_claim_input_binding_original_recovery_and_cross_window_drift(self):
        binding, authority, packet, now = self.continuation()
        root = self.f.root / "continuation-calls"
        result = c.consume(packet, root, batch=self.f.batch, repo=self.f.repo, now=now,
            transport=self.transport, prospective_binding=binding)
        directory = next(root.glob("*/claim.json")).parent
        claim = c._json((directory / "claim.json").read_bytes())
        self.assertEqual(claim["prospective_budget_binding_sha256"], c._digest(binding))
        self.assertEqual(claim["input_sha256"], c._digest(packet))
        self.f.write("authority", {"closed": True}); self.f.source.write_bytes(b"later source")
        recovered = c.consume(packet, root, batch=self.f.batch, repo=self.f.repo, now="2026-10-06T01:00:00Z",
            transport=lambda *args: self.fail("no resample"), prospective_binding=binding)
        self.assertEqual(recovered, result)
        for other in (None, c.prospective_pilot_binding()):
            with self.assertRaisesRegex(ValueError, "explicit prospective"):
                c.consume(packet, root, batch=self.f.batch, repo=self.f.repo, now=now,
                    transport=self.transport, prospective_binding=other)
        changed = deepcopy(packet); changed["prospective_budget_binding"]["limits"]["attempts"] = 3
        with self.assertRaisesRegex(ValueError, "explicit prospective"):
            c.consume(changed, root, batch=self.f.batch, repo=self.f.repo, now=now,
                transport=self.transport, prospective_binding=binding)
        claim["prospective_budget_binding_sha256"] = c._digest(c.prospective_pilot_binding())
        (directory / "claim.json").write_text(json.dumps(claim))
        with self.assertRaisesRegex(ValueError, "same feedback changed"):
            c.consume(packet, root, batch=self.f.batch, repo=self.f.repo, now=now,
                transport=self.transport, prospective_binding=binding)
        self.assertEqual(self.calls, 1)

    def test_continuation_retains_original_runtime_source_commit_and_review_guards(self):
        binding, authority, packet, now = self.continuation()
        for path in (self.f.source, self.f.python):
            original = path.read_bytes(); path.write_bytes(b"drift")
            with self.assertRaises(ValueError):
                c.prepare_input(self.f.bindings, self.f.batch, self.f.repo, now, prospective_binding=binding)
            path.write_bytes(original)
        with patch.object(c.subprocess, "check_output", return_value=b"wrong frozen commit"):
            with self.assertRaisesRegex(ValueError, "source commit drift"):
                c.prepare_input(self.f.bindings, self.f.batch, self.f.repo, now, prospective_binding=binding)
        review = deepcopy(self.f.values["review"]); review["passed"] = False
        self.f.write("review", review)
        with self.assertRaisesRegex(ValueError, "admission drift"):
            c.prepare_input(self.f.bindings, self.f.batch, self.f.repo, now, prospective_binding=binding)
        self.assertEqual(self.calls, 0)

    def test_continuation_failed_original_transport_never_retries_or_resets_budget(self):
        binding, authority, packet, now = self.continuation()
        def failed(*args):
            self.calls += 1
            raise RuntimeError("synthetic uncertain capacity")
        kwargs = {"batch": self.f.batch, "repo": self.f.repo, "now": now, "prospective_binding": binding}
        root = self.f.root / "continuation-failed"
        with self.assertRaises(RuntimeError): c.consume(packet, root, transport=failed, **kwargs)
        with self.assertRaises(FileNotFoundError): c.consume(packet, root, transport=self.transport, **kwargs)
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.f.values["authority"], authority)
        self.assertTrue(c._json(next(root.glob("*/failure.json")).read_bytes())["no_resample"])


    def ten_hour(self):
        binding = c.ten_hour_window_binding()
        authority = {key: deepcopy(binding[key]) for key in
                     ("batch_id", "start_utc", "selection_cutoff_utc", "deadline_utc", "limits")}
        authority["attempts"] = []
        self.f.write("authority", authority)
        now = datetime(2026, 10, 6, 5, tzinfo=timezone.utc)
        packet = c.prepare_input(self.f.bindings, self.f.batch, self.f.repo, now, prospective_binding=binding)
        return binding, authority, packet, now

    def test_ten_hour_exact_fresh_identity_ceiling_copy_and_old_defaults(self):
        binding, authority, packet, now = self.ten_hour()
        self.assertEqual((binding["batch_id"], binding["start_utc"], binding["selection_cutoff_utc"], binding["deadline_utc"]),
            ("market-rsi-controller-enablement-10h-20261006-01", "2026-10-06T04:36:33Z", "2026-10-06T14:21:33Z", "2026-10-06T14:36:33Z"))
        self.assertEqual(binding["limits"], {"attempts": 12, "statistical_fits": 48, "live_candidate_processes": 2,
            "threads_per_candidate": 1, "per_attempt_seconds": 900, "sampled_rss_bytes": 1073741824,
            "paid_provider_calls": 0, "paid_provider_spend_usd": "0"})
        self.assertEqual((c.DEADLINE, c.CUTOFF), ("2026-10-05T19:27:11Z", "2026-10-05T19:12:11Z"))
        self.assertEqual(c.prospective_pilot_binding()["limits"]["attempts"], 3)
        self.assertEqual(c.continuation_pilot_binding()["limits"]["attempts"], 2)
        binding["limits"]["attempts"] = 999
        self.assertEqual(packet["prospective_budget_binding"]["limits"]["attempts"], 12)
        self.assertEqual(c.ten_hour_window_binding()["limits"]["attempts"], 12)
        self.assertEqual(self.calls, 0)

    def test_ten_hour_rejects_self_grants_types_or_changed_window_before_call(self):
        binding, authority, packet, now = self.ten_hour()
        for field, value in (("attempts", True), ("attempts", 12.0), ("attempts", 13),
                ("statistical_fits", 52), ("paid_provider_calls", 1), ("paid_provider_spend_usd", 0),
                ("threads_per_candidate", 2), ("sampled_rss_bytes", 2147483648)):
            changed = deepcopy(binding); changed["limits"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                c.check_budget(authority, now, prospective_binding=changed)
        for field, value in (("batch_id", "other"), ("schema", "other"), ("authority_granted", True),
                ("deadline_utc", "2026-10-06T15:36:33Z")):
            changed = deepcopy(binding); changed[field] = value
            with self.assertRaises(ValueError): c.check_budget(authority, now, prospective_binding=changed)
        for other in (None, c.prospective_pilot_binding(), c.continuation_pilot_binding()):
            with self.assertRaises(ValueError): c.check_budget(authority, now, prospective_binding=other)
        self.assertEqual(self.calls, 0)

    def test_ten_hour_twelve_forty_eight_clock_concurrency_and_consumed_failures(self):
        binding, authority, packet, now = self.ten_hour()
        c.check_budget(authority, binding["start_utc"], prospective_binding=binding)
        for moment in ("2026-10-06T04:36:32Z", binding["selection_cutoff_utc"], binding["deadline_utc"]):
            with self.assertRaisesRegex(ValueError, "selection stop"):
                c.check_budget(authority, moment, prospective_binding=binding)
        authority["attempts"] = [{"attempt_id": str(i), "fits_reserved": 4,
            "actual_fits": 0, "status": "failed"} for i in range(11)]
        c.check_budget(authority, now, prospective_binding=binding)
        authority["attempts"].append({"attempt_id": "twelfth", "fits_reserved": 4, "actual_fits": 0, "status": "failed"})
        with self.assertRaisesRegex(ValueError, "selection stop"):
            c.check_budget(authority, now, prospective_binding=binding)
        authority["attempts"] = [{"attempt_id": str(i), "fits_reserved": 4,
            "actual_fits": 0, "status": "running"} for i in range(2)]
        with self.assertRaisesRegex(ValueError, "concurrency"):
            c.check_budget(authority, now, prospective_binding=binding)
        authority["attempts"][1]["status"] = "failed"
        c.check_budget(authority, now, prospective_binding=binding)
        authority["attempts"][0]["actual_fits"] = True
        with self.assertRaisesRegex(ValueError, "invalid actual/reserved"):
            c.check_budget(authority, now, prospective_binding=binding)

    def test_ten_hour_original_claim_recovery_no_cross_window_or_resample(self):
        binding, authority, packet, now = self.ten_hour()
        root = self.f.root / "ten-hour-calls"
        result = c.consume(packet, root, batch=self.f.batch, repo=self.f.repo, now=now,
            transport=self.transport, prospective_binding=binding)
        claim = c._json(next(root.glob("*/claim.json")).read_bytes())
        self.assertEqual(claim["prospective_budget_binding_sha256"], c._digest(binding))
        self.assertEqual(claim["input_sha256"], c._digest(packet))
        self.f.write("authority", {"closed": True}); self.f.source.write_bytes(b"later source")
        self.assertEqual(c.consume(packet, root, batch=self.f.batch, repo=self.f.repo,
            now="2026-10-06T15:00:00Z", transport=lambda *args: self.fail("no retry"),
            prospective_binding=binding), result)
        for other in (None, c.continuation_pilot_binding()):
            with self.assertRaisesRegex(ValueError, "explicit prospective"):
                c.consume(packet, root, batch=self.f.batch, repo=self.f.repo, now=now,
                    transport=self.transport, prospective_binding=other)
        self.assertEqual(self.calls, 1)

    def test_ten_hour_keeps_source_runtime_review_and_uncertain_failure_guards(self):
        binding, authority, packet, now = self.ten_hour()
        original = self.f.source.read_bytes(); self.f.source.write_bytes(b"drift")
        with self.assertRaisesRegex(ValueError, "source byte drift"):
            c.prepare_input(self.f.bindings, self.f.batch, self.f.repo, now, prospective_binding=binding)
        self.f.source.write_bytes(original)
        def failed(*args):
            self.calls += 1
            raise RuntimeError("synthetic uncertain capacity")
        kwargs = {"batch": self.f.batch, "repo": self.f.repo, "now": now, "prospective_binding": binding}
        root = self.f.root / "ten-hour-failed"
        with self.assertRaises(RuntimeError): c.consume(packet, root, transport=failed, **kwargs)
        with self.assertRaises(FileNotFoundError): c.consume(packet, root, transport=self.transport, **kwargs)
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.f.values["authority"], authority)
        self.assertTrue(c._json(next(root.glob("*/failure.json")).read_bytes())["no_resample"])


    def fresh_authorized(self):
        binding = c.fresh_three_attempt_binding("2026-10-06T15:00:00Z")
        authority = {key: deepcopy(binding[key]) for key in
                     ("batch_id", "start_utc", "selection_cutoff_utc", "deadline_utc", "limits")}
        authority["attempts"] = []
        self.f.write("authority", authority)
        now = datetime(2026, 10, 6, 15, 1, tzinfo=timezone.utc)
        packet = c.prepare_input(self.f.bindings, self.f.batch, self.f.repo, now,
                                 prospective_binding=binding)
        return binding, authority, packet, now

    def test_fresh_authorized_fixed_caps_and_once_frozen_ready_time(self):
        binding, authority, packet, now = self.fresh_authorized()
        self.assertEqual(binding["batch_id"], "market-rsi-authorized-discovery-20261006-01")
        self.assertEqual((binding["selection_cutoff_utc"], binding["deadline_utc"]),
                         ("2026-10-06T16:15:00Z", "2026-10-06T16:30:00Z"))
        self.assertEqual(binding["limits"], c.prospective_pilot_binding()["limits"])
        self.assertEqual(packet["prospective_budget_binding"], binding)
        self.assertEqual(c.ten_hour_window_binding()["limits"]["attempts"], 12)
        self.assertEqual(c.continuation_pilot_binding()["limits"]["attempts"], 2)
        for bad in (True, "2026-10-05T15:00:00Z", "2026-10-06T14:51:59Z",
                    "2026-10-06T15:00:00+00:00", "2026-10-06T15:00:00.001Z"):
            with self.assertRaises(ValueError): c.fresh_three_attempt_binding(bad)
        self.assertEqual(self.calls, 0)

    def test_fresh_authorized_mutation_or_clock_reset_never_admitted(self):
        binding, authority, packet, now = self.fresh_authorized()
        for field, value in (("attempts", 4), ("attempts", True), ("attempts", 3.0),
                ("statistical_fits", 16), ("threads_per_candidate", 2), ("paid_provider_calls", 1)):
            changed = deepcopy(binding); changed["limits"][field] = value
            with self.assertRaises(ValueError): c.check_budget(authority, now, prospective_binding=changed)
        for field, value in (("batch_id", "other"), ("schema", "other"),
                ("deadline_utc", "2026-10-06T16:31:00Z"), ("authority_granted", True)):
            changed = deepcopy(binding); changed[field] = value
            with self.assertRaises(ValueError): c.check_budget(authority, now, prospective_binding=changed)
        with self.assertRaises(ValueError):
            c.check_budget(authority, now, prospective_binding=c.fresh_three_attempt_binding("2026-10-06T15:01:00Z"))
        for other in (None, c.ten_hour_window_binding(), c.continuation_pilot_binding()):
            with self.assertRaises(ValueError): c.check_budget(authority, now, prospective_binding=other)
        self.assertEqual(self.calls, 0)

    def test_fresh_authorized_failures_count_and_cutoff_concurrency_stay_fixed(self):
        binding, authority, packet, now = self.fresh_authorized()
        for moment in ("2026-10-06T14:59:59Z", binding["selection_cutoff_utc"], binding["deadline_utc"]):
            with self.assertRaises(ValueError): c.check_budget(authority, moment, prospective_binding=binding)
        authority["attempts"] = [{"attempt_id": str(i), "fits_reserved": 4,
                                 "actual_fits": 0, "status": "failed"} for i in range(2)]
        c.check_budget(authority, now, prospective_binding=binding)
        authority["attempts"].append({"attempt_id": "third", "fits_reserved": 4,
                                    "actual_fits": 0, "status": "failed"})
        with self.assertRaises(ValueError): c.check_budget(authority, now, prospective_binding=binding)
        authority["attempts"] = authority["attempts"][:2]
        for item in authority["attempts"]: item["status"] = "running"
        with self.assertRaises(ValueError): c.check_budget(authority, now, prospective_binding=binding)

    def test_fresh_authorized_original_once_recovery_cannot_change_clock(self):
        binding, authority, packet, now = self.fresh_authorized()
        root = self.f.root / "fresh-authorized-original"
        result = c.consume(packet, root, batch=self.f.batch, repo=self.f.repo, now=now,
                           transport=self.transport, prospective_binding=binding)
        self.f.write("authority", {"closed": True}); self.f.source.write_bytes(b"later source")
        self.assertEqual(c.consume(packet, root, batch=self.f.batch, repo=self.f.repo,
            now="2026-10-07T00:00:00Z", transport=lambda *args: self.fail("no retry"),
            prospective_binding=binding), result)
        changed = c.fresh_three_attempt_binding("2026-10-06T15:01:00Z")
        with self.assertRaisesRegex(ValueError, "explicit prospective"):
            c.consume(packet, root, batch=self.f.batch, repo=self.f.repo, now=now,
                      transport=self.transport, prospective_binding=changed)
        self.assertEqual(self.calls, 1)

if __name__ == "__main__": unittest.main()
