"""Native recorder failure to original decision fixtures; zero fits or account calls."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from data_scientist_harness import test_micro_evolution as evolution
from data_scientist_harness.co_evolution_loop import initialize_micro_evolution, micro_pair_hash

from supervisor_harness import account_controller_feedback_consumer as c
from supervisor_harness import controller_failure_feedback as f
from supervisor_harness import test_account_controller_feedback_consumer as legacy
from supervisor_harness import test_continuous_discovery_batch as recording
from supervisor_harness import test_learning_checkpoint_assessment as learning

NOW = legacy.NOW


class Fixture:
    def __init__(self, root):
        self.root = Path(root).resolve(); self.repo = self.root / "repo"; self.repo.mkdir()
        self.values, self.bindings = {}, {}
        self.source = self.repo / "research/market_rsi/experiments/nfl_ingame_synthetic.py"
        self.source.parent.mkdir(parents=True); self.source.write_bytes(b"synthetic source")
        self.python = self.root / "python"; self.python.write_bytes(b"synthetic Python")
        self.cli = self.root / "cli"; self.cli.write_bytes(b"synthetic CLI")
        runtime_pair = micro_pair_hash(initialize_micro_evolution(evolution.config()))
        self.good, self.incumbent = learning.sha("good:runner"), recording.sha("market-baseline")
        self.write("memory", {"accepted_success": self.good, "failure_requires_repair": "no valid predictions"})
        self.write("history", {"evidence": self.good})
        self.write("pool", {"branches": [{"source_sha256": self.good}, {"source_sha256": self.incumbent}]})
        self.write("authority", {"start_utc": "2026-10-05T15:27:11Z", "deadline_utc": c.DEADLINE,
            "selection_cutoff_utc": c.CUTOFF, "limits": {"attempts": 6, "statistical_fits": 24,
                "live_candidate_processes": 2, "threads_per_candidate": 1, "per_attempt_seconds": 900,
                "sampled_rss_bytes": 1073741824, "paid_provider_calls": 0, "paid_provider_spend_usd": "0"},
            "attempts": [{"attempt_id": label, "fits_reserved": 4, "actual_fits": fits, "status": "closed"}
                         for label, fits in [("good", 4), ("failed", 0)]]})
        self.write("overhead", {"implementation_seconds": 2})
        self.write("request", {"attempt_id": "failed", "candidate_id": "candidate-failed",
            "module": "experiments.nfl_ingame_synthetic", "source_commit": "fixture-commit",
            "files": {str(self.source.relative_to(self.repo)): c.sha(self.source)},
            "python": str(self.python), "python_sha256": c.sha(self.python),
            "memory": self.bindings["memory"]["path"], "memory_sha256": self.bindings["memory"]["sha256"],
            "runtime_pair_sha256": runtime_pair, "spec_sha256": learning.sha("spec"),
            "max_fits": 4, "max_wall_seconds": 900})
        output = str(self.root / "runs" / "failed")
        self.write("failure", {"attempt_id": "failed", "request_sha256": self.bindings["request"]["sha256"],
            "source_commit": "fixture-commit", "command": [str(self.python), "-B", "-m",
                "experiments.nfl_ingame_synthetic", "--source-root", str(f.worker.TRAIN), "--output", output],
            "runtime_pair_sha256": runtime_pair, "memory_sha256": self.bindings["memory"]["sha256"],
            "outcome": "failed", "exit_code": 1, "error": "ValueError: stale input before fit", "wall_seconds": .12,
            "fits_reserved": 4, "sampled_peak_rss_kib": 1024, "rss_limit_kib": 1048576,
            "rss_limit_enforcement": "one-second polling; not OS-hard isolation",
            "stdout_sha256": learning.sha("stdout"), "stderr_sha256": learning.sha("stderr"),
            "output": output, "metrics_independently_reviewed": False, "network_isolation_enforced": False,
            "provider_calls_requested": 0})
        self.write("review", {"schema": "controller_failure_review_v1", "passed": True, "artifact_kind": "failure",
            "candidate_id": "candidate-failed", "attempt_id": "failed", "source_commit": "fixture-commit",
            "request_sha256": self.bindings["request"]["sha256"], "failure_sha256": self.bindings["failure"]["sha256"],
            "failure_stage": "pre_fit", "actual_fits": 0})
        self.batch = recording.ContinuousDiscoveryBatch(self.root / "batch", allow_temporary=True,
            test_clock=lambda: NOW, allow_test_clock=True)
        self.batch.initialize(batch_id="synthetic-failure-v4", start_utc=NOW - timedelta(minutes=10),
            deadline_utc=NOW + timedelta(hours=1), max_attempts=6,
            initial_incumbent={"candidate_id": "market", "candidate_sha256": self.incumbent,
                "scorecard_sha256": learning.sha("prior-market-card"), "review_sha256": "0" * 64},
            active_pool_capacity=2, learning_checkpoint_version=1)
        self.batch.record_micro_evolution("initialize", evolution.config(),
            expected_state_sha256=self.batch.snapshot()["state_sha256"], now=NOW - timedelta(minutes=9, seconds=30))
        helper = recording.ContinuousDiscoveryBatchTests()
        self.batch.select_controller_pool([helper.pool_member("good"), helper.pool_member("failed",
            allocation="exploration", method_family="tree")], now=NOW - timedelta(minutes=9))
        for label in ("good", "failed"):
            failed = label == "failed"
            moment = NOW - timedelta(minutes=4 if failed else 8)
            self.batch.mark_implementation_ready(label, runner_sha256=c.sha(self.source) if failed else self.good,
                spec_sha256=learning.sha("spec"), now=moment)
            self.batch.claim_execution(label, claim_id=label + "-claim", now=moment + timedelta(seconds=1),
                runtime_pair_sha256=self.values["request"]["runtime_pair_sha256"],
                memory_snapshot_sha256=self.bindings["memory"]["sha256"])
            self.batch.mark_execution_terminal(label, claim_id=label + "-claim", outcome="failed" if failed else "succeeded",
                execution_receipt_sha256=self.bindings["failure"]["sha256"] if failed else learning.sha("good:receipt"),
                now=moment + timedelta(seconds=2))
            review_sha = self.bindings["review"]["sha256"] if failed else learning.sha("good:review")
            cp = learning.checkpoint(label, credit=1 if failed else 2, status="invalid" if failed else "valid",
                action="stop" if failed else "branch", kind="failure_diagnosis" if failed else "hypothesis_test")
            cp["validity"]["review_sha256"] = review_sha
            self.batch.record_result_review(label, decision="REVERT", scorecard_sha256=self.bindings["failure"]["sha256"]
                if failed else learning.sha("good:card"), review_sha256=review_sha, independently_reviewed=True,
                performance_validity=cp["validity"], now=moment + timedelta(seconds=3))
            self.batch.record_learning_checkpoint(label, cp, now=moment + timedelta(seconds=4))
            state = self.batch.mark_controller_feedback_ready(label, now=moment + timedelta(seconds=5))
        self.write("feedback", next(b["feedback_packet"] for b in state["branches"] if b["attempt_id"] == "failed"))

    def write(self, role, value):
        path = self.root / (role + ".json"); path.write_text(json.dumps(value, allow_nan=False))
        self.values[role] = value; self.bindings[role] = {"path": str(path), "sha256": c.sha(path)}

    def prepare(self): return c.prepare_input(self.bindings, self.batch, self.repo, NOW)

    def rebound_packet(self, *, review=None, failure=None):
        """Adversarial self-consistent hashes test semantic checks, not just drift."""
        if failure is not None: self.write("failure", failure)
        review = deepcopy(review or self.values["review"])
        review["failure_sha256"] = self.bindings["failure"]["sha256"]; self.write("review", review)
        feedback = deepcopy(self.values["feedback"])
        feedback.update(review_sha256=self.bindings["review"]["sha256"],
            execution_receipt_sha256=self.bindings["failure"]["sha256"], scorecard_sha256=self.bindings["failure"]["sha256"])
        feedback["learning_checkpoint"]["validity"]["review_sha256"] = self.bindings["review"]["sha256"]
        self.write("feedback", feedback)
        state = self.batch.snapshot(); branch = next(b for b in state["branches"] if b["attempt_id"] == "failed")
        branch.update(feedback_packet=feedback, feedback_packet_sha256=c._digest(feedback),
            execution_receipt_sha256=self.bindings["failure"]["sha256"], review_sha256=self.bindings["review"]["sha256"])
        with patch.object(self.batch, "snapshot", return_value=state): return self.prepare()

    def decision(self, packet):
        result = legacy.Fixture.decision(self, packet)
        result.update(actual_parent_sha256=self.good, comparison_incumbent_sha256=self.incumbent)
        result["evidence_used"] = [{"sha256": self.bindings["failure"]["sha256"],
            "finding": "Pre-fit failure has zero predictions", "choice_consequence": "repair from a valid saved parent"}]
        result["active_pool"] = [{"parent_sha256": self.good, "method_family": "calibration", "reason": "valid parent"},
            {"parent_sha256": self.incumbent, "method_family": "market", "reason": "market anchor"}]
        return result

    def transport(self, directory, packet, timeout, mutate=None):
        response = self.decision(packet)
        if mutate: mutate(response)
        identity = c._identity(packet.get("evidence_session"), True)
        c.save(directory / "process.json", {"pid": 123, "command": c._command(directory),
            "cli_sha256": c.CLI_SHA, "input_sha256": c._digest(packet), **identity})
        c.save(directory / "response.json", response)
        events = [{"type": "thread.started"}, {"type": "item.completed", "item": {
            "type": "agent_message", "text": json.dumps(response)}},
            {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}]
        (directory / "events.jsonl").write_text("\n".join(json.dumps(item) for item in events))
        (directory / "stderr").write_bytes(b"")
        c.save(directory / "completion.json", {"exit_code": 0, "timed_out": False, **identity,
            "hashes": {name: c.sha(directory / name) for name in
                ["process.json", "events.jsonl", "stderr", "schema.json", "input.json", "response.json"]}})


class FailureFeedbackTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(); self.addCleanup(temp.cleanup); self.f = Fixture(temp.name)
        for mock in (patch.object(c.subprocess, "check_output", return_value=b"synthetic source"),
                     patch.object(c, "CLI", self.f.cli), patch.object(c, "CLI_SHA", c.sha(self.f.cli))):
            mock.start(); self.addCleanup(mock.stop)

    def test_native_failed_receipt_reaches_input_without_fake_scores(self):
        packet = self.f.prepare()
        self.assertEqual(packet["schema"], "controller_failure_feedback_input_v1")
        self.assertIsNone(packet["numerical"]); self.assertIsNone(packet["supplement"])
        self.assertEqual(packet["failure"], self.f.values["failure"])
        self.assertEqual(packet["failure_review"]["actual_fits"], 0)
        self.assertEqual(packet["feedback"]["scorecard_sha256"], packet["feedback"]["execution_receipt_sha256"])
        self.assertEqual(packet["feedback"]["learning_checkpoint"]["validity"]["status"], "invalid")
        self.assertFalse(any(self.f.root.glob("*scorecard*"))); self.assertFalse(any(self.f.root.glob("*.csv")))
        self.assertEqual(self.f.batch.snapshot()["incumbent"]["candidate_sha256"], self.f.incumbent)

    def test_valid_parent_original_response_and_restart_do_not_resample(self):
        packet = self.f.prepare(); calls = []
        def transport(*args): calls.append(1); self.f.transport(*args)
        result = c.consume(packet, self.f.root / "calls", batch=self.f.batch, repo=self.f.repo, now=NOW, transport=transport)
        self.assertEqual(result["actual_parent_sha256"], self.f.good)
        self.f.write("authority", {"closed": True})
        recovered = c.consume(packet, self.f.root / "calls", batch=self.f.batch, repo=self.f.repo,
            now=c.DEADLINE, transport=lambda *args: self.fail("no second call"))
        self.assertEqual(recovered, result); self.assertEqual(len(calls), 1)

    def test_failed_predictor_and_unprovided_parent_rejected_by_original_validator(self):
        packet = self.f.prepare()
        for i, parent in enumerate((c.sha(self.f.source), "f" * 64)):
            def transport(directory, value, timeout):
                self.f.transport(directory, value, timeout, mutate=lambda r: r.update(actual_parent_sha256=parent))
            with self.assertRaisesRegex(ValueError, "unprovided evidence/parent"):
                c.consume(packet, self.f.root / ("rejected" + str(i)), batch=self.f.batch, repo=self.f.repo, now=NOW, transport=transport)

    def test_strict_review_failure_types_and_no_unbound_numerical_artifacts(self):
        original = deepcopy(self.f.values["review"])
        for key, value in (("passed", 1), ("artifact_kind", "scorecard"), ("failure_stage", "guessed"),
                           ("actual_fits", True), ("actual_fits", 1), ("failure_sha256", "f" * 64)):
            item = deepcopy(original); item[key] = value; self.f.write("review", item)
            with self.assertRaises(ValueError): self.f.prepare()
        self.f.write("review", original)
        for role in ("scorecard", "predictions", "supplement"):
            bindings = dict(self.f.bindings, **{role: self.f.bindings["failure"]})
            with self.assertRaises(ValueError): f.prepare_input(bindings, self.f.batch, self.f.repo, NOW)

    def test_native_worker_receipt_resource_and_claim_drifts_rejected(self):
        original = deepcopy(self.f.values["failure"])
        for key, value in (("fits_reserved", True), ("provider_calls_requested", 1), ("metrics_independently_reviewed", True),
                           ("sampled_peak_rss_kib", -1), ("wall_seconds", True), ("exit_code", False),
                           ("error", ""), ("memory_sha256", "f" * 64), ("command", ["sh"]), ("outcome", "succeeded")):
            item = deepcopy(original); item[key] = value; self.f.write("failure", item)
            with self.assertRaises(ValueError): self.f.prepare()

    def test_plain_nonzero_worker_exit_without_exception_preserves_null_error(self):
        failure = deepcopy(self.f.values["failure"]); failure["error"] = None
        packet = self.f.rebound_packet(failure=failure)
        self.assertIsNone(packet["failure"]["error"]); self.assertEqual(packet["failure"]["exit_code"], 1)
        for code in (0, None, True):
            failure["exit_code"] = code
            with self.assertRaises(ValueError): self.f.rebound_packet(failure=failure)

    def test_self_consistent_resource_and_stage_fabrications_are_denied(self):
        original = deepcopy(self.f.values["failure"])
        for key, value in (("fits_reserved", True), ("provider_calls_requested", True),
                           ("wall_seconds", True), ("sampled_peak_rss_kib", True), ("error", "")):
            failure = deepcopy(original); failure[key] = value
            with self.assertRaises(ValueError): self.f.rebound_packet(failure=failure)
        for fits in (True, 1, -1, 5):
            review = deepcopy(self.f.values["review"]); review["actual_fits"] = fits
            with self.assertRaises(ValueError): self.f.rebound_packet(failure=original, review=review)

    def test_reviewed_partial_fit_failure_records_actual_not_reserved(self):
        authority = deepcopy(self.f.values["authority"]); authority["attempts"][1]["actual_fits"] = 2
        self.f.write("authority", authority)
        review = deepcopy(self.f.values["review"]); review.update(failure_stage="fit", actual_fits=2)
        packet = self.f.rebound_packet(review=review)
        self.assertEqual(packet["failure_review"]["actual_fits"], 2)
        self.assertEqual(packet["failure"]["fits_reserved"], 4); self.assertIsNone(packet["numerical"])

    def test_actual_claim_and_branch_drift_is_not_hidden_by_valid_packet_hash(self):
        original = self.f.batch.snapshot()
        for key, value in (("claim_id", None), ("runtime_pair_sha256", "f" * 64),
                           ("execution_outcome", "succeeded"), ("memory_snapshot_sha256", "f" * 64)):
            state = deepcopy(original); next(b for b in state["branches"] if b["attempt_id"] == "failed")[key] = value
            with patch.object(self.f.batch, "snapshot", return_value=state), self.assertRaises(ValueError): self.f.prepare()

    def test_controller_transport_failure_keeps_claim_and_cannot_retry(self):
        packet = self.f.prepare(); calls = []
        def fail_transport(*args): calls.append(1); raise RuntimeError("synthetic transport interruption")
        with self.assertRaises(RuntimeError):
            c.consume(packet, self.f.root / "interrupted", batch=self.f.batch, repo=self.f.repo, now=NOW, transport=fail_transport)
        with self.assertRaises(FileNotFoundError):
            c.consume(packet, self.f.root / "interrupted", batch=self.f.batch, repo=self.f.repo, now=NOW,
                transport=lambda *args: self.fail("preserved failed claim must not relaunch"))
        self.assertEqual(len(calls), 1)
        failure = c._json(next((self.f.root / "interrupted").glob("*/failure.json")).read_bytes())
        self.assertIs(failure["no_resample"], True)

    def test_receipt_duplicate_keys_nonfinite_and_extra_numeric_fields_denied(self):
        path = Path(self.f.bindings["failure"]["path"]); original = path.read_bytes()
        for blob in (b'{"outcome":"failed","outcome":"succeeded"}', b'{"wall_seconds":NaN}'):
            path.write_bytes(blob); self.f.bindings["failure"]["sha256"] = c.sha(path)
            with self.assertRaises(ValueError): self.f.prepare()
        path.write_bytes(original); self.f.bindings["failure"]["sha256"] = c.sha(path)
        failure = deepcopy(self.f.values["failure"]); failure["score"] = .14
        with self.assertRaisesRegex(ValueError, "exact native worker"):
            self.f.rebound_packet(failure=failure)

    def test_native_prompt_copies_factual_failure_without_scientific_refutation(self):
        packet = self.f.prepare(); prompt = c._prompt(packet)
        self.assertIn("independently reviewed factual execution failure", prompt)
        self.assertIn("No valid prediction scores are supplied", prompt)
        self.assertIn("execution failure is not scientific refutation", prompt)
        self.assertNotIn("verified numerical evidence", prompt)
        self.assertIn(packet["failure"]["error"], prompt)
        self.assertIn('"actual_fits": 0', prompt)
        self.assertIn("input_sha256=" + c._digest(packet), prompt)

    def test_helper_only_source_drift_blocks_original_recovery_without_resampling(self):
        packet = self.f.prepare(); calls = []
        def transport(*args): calls.append(1); self.f.transport(*args)
        c.consume(packet, self.f.root / "source-drift", batch=self.f.batch, repo=self.f.repo, now=NOW, transport=transport)
        directory = self.f.root / "source-drift" / packet["bindings"]["feedback"]["sha256"]
        original_sha, helper = c.sha, Path(f.__file__).resolve()
        claim = c._json((directory / "claim.json").read_bytes())
        self.assertEqual(claim["failure_adapter_source_sha256"], original_sha(helper))
        def drift(path): return "f" * 64 if Path(path).resolve() == helper else original_sha(path)
        with patch.object(c, "sha", side_effect=drift):
            with self.assertRaisesRegex(ValueError, "same feedback changed"):
                c.consume(packet, self.f.root / "source-drift", batch=self.f.batch, repo=self.f.repo, now=NOW,
                    transport=lambda *args: self.fail("source drift must not trigger new model call"))
            with self.assertRaisesRegex(ValueError, "completion provenance drift"):
                c._recover(directory, packet)
        self.assertEqual(len(calls), 1)

    def test_source_runtime_memory_hash_and_closed_budget_denials(self):
        for path in (self.f.source, self.f.python, Path(self.f.bindings["memory"]["path"])):
            original = path.read_bytes(); path.write_bytes(original + b" ")
            with self.assertRaises(ValueError): self.f.prepare()
            path.write_bytes(original)
        with self.assertRaisesRegex(ValueError, "outer selection stop"):
            f.prepare_input(self.f.bindings, self.f.batch, self.f.repo, c.CUTOFF)
        with self.assertRaisesRegex(ValueError, "prospective budget binding drift"):
            f.prepare_input(self.f.bindings, self.f.batch, self.f.repo, NOW, prospective_binding={"reset": True})


if __name__ == "__main__": unittest.main()
