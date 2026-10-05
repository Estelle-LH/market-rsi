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
            def wait(self): return self.returncode
        with patch.object(c.subprocess, "Popen", return_value=Child()) as popen, patch.object(c.os, "killpg") as kill:
            c._transport(directory, self.packet, 12)
        command = popen.call_args.args[0]
        self.assertEqual(command, c._command(directory)); self.assertIn("--ignore-user-config", command)
        self.assertTrue(popen.call_args.kwargs["start_new_session"]); kill.assert_called_once()
        self.assertIn("input_sha256=" + c._digest(self.packet), prompts[0])
        self.assertIn("feedback_sha256=" + self.packet["bindings"]["feedback"]["sha256"], prompts[0])
        self.assertIn("do not calculate hashes", prompts[0])
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


if __name__ == "__main__": unittest.main()
