from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from controller_candidate_harbor import (ISOLATION_CHECKS, prepare_job,
                                         temporal_train_cv, terminal_nonzero_result,
                                         verify_and_score,
                                         verify_candidate_failure, verify_job)
from controller_workspace import LITERATURE_SCHEMA, prepare_workspace
from market_rsi import canonical, digest, fresh_json
from prediction_stream import PredictionJournal, fingerprint


DAY = 86_400_000


def row(name, game, day, mid, target):
    decision = day * DAY + int(mid * 10_000)
    return {"row_id": name, "game_id": game, "market_id": game + "-market",
            "decision_ms": decision, "feature_available_ms": decision,
            "features": {"mid": mid, "spread": 0.02}, "target": target,
            "label_available_ms": decision + 60_000}


class ControllerCandidateHarborTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / "controller-session-fixture"
        train = {"schema": "market_permitted_rows_v1", "experiment_id": "source-fixture",
                 "task_id": "task-fixture", "split": "train",
                 "feature_names": ["mid", "spread"],
                 "rows": [row("t1", "train-game-1", 1, .4, .42),
                          row("t2", "train-game-2", 2, .6, .58)]}
        dev = {"schema": "market_permitted_rows_v1", "experiment_id": "source-fixture",
               "task_id": "task-fixture", "split": "dev",
               "feature_names": ["mid", "spread"],
               "rows": [row("d1", "dev-game", 3, .3, .35),
                        row("d2", "dev-game", 3, .7, .65)]}
        self.train_path, self.dev_path = self.root / "train.json", self.root / "dev.json"
        self.train_path.write_text(canonical(train))
        self.dev_path.write_text(canonical(dev))
        abstract = "Forecast calibration and proper scoring rules."
        literature = {"schema": LITERATURE_SCHEMA, "papers": [{
            "paper_id": "paper-one", "title": "Calibration", "url": "https://example.org/paper",
            "year": 2020, "abstract": abstract,
            "content_sha256": hashlib.sha256(abstract.encode()).hexdigest()}]}
        self.manifest = prepare_workspace(self.workspace,
            session_id="controller-session-fixture", experiment_id="experiment-fixture",
            task_id="task-fixture", arm="learn", train_path=self.train_path,
            dev_path=self.dev_path, own_history={"rounds": []},
            literature_snapshot=literature, opaque_test_commitment="a" * 64)
        source = ("def fit(train_rows, feature_names):\n    return None\n\n"
                  "def predict(model, public_row):\n    return public_row['features']['mid']\n")
        (self.workspace / "candidate.py").write_text(source)
        self.request = {"schema": "market_controller_execution_request_v1",
            "execution_id": "controller-session-fixture-execution-01",
            "session_id": "controller-session-fixture", "experiment_id": "experiment-fixture",
            "task_id": "task-fixture", "candidate_name": "candidate.py",
            "candidate_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "workspace_manifest_sha256": digest(self.manifest), "evaluation_role": "train_cv",
            "automatic_retry": False}
        self.config = {"schema": "market_controller_runner_v1",
            "session_id": "controller-session-fixture", "experiment_id": "experiment-fixture",
            "task_id": "task-fixture", "train_path": str(self.train_path.resolve()),
            "train_sha256": hashlib.sha256(self.train_path.read_bytes()).hexdigest(),
            "budget_path": str((self.root / "budget").resolve()),
            "env_file": str((self.root / ".env").resolve()),
            "budget_bucket": "setup", "evidence_class": "synthetic"}
        self.job = self.root / self.request["execution_id"]

    def tearDown(self):
        self.temp.cleanup()

    def test_job_uses_train_cv_and_never_opens_current_dev(self):
        claim = prepare_job(self.request, self.workspace, self.config, self.job)
        packet = json.loads((self.job / "packet.json").read_text())
        labels = json.loads((self.job / "evaluation-labels.json").read_text())
        self.assertTrue(all("target" not in item and "label_available_ms" not in item
                            for item in packet["evaluation"]))
        self.assertEqual(set(labels), {item["row_id"] for item in packet["evaluation"]})
        self.assertFalse(claim["future_test_used"])
        self.assertEqual(claim["evaluation_role"], "train_cv")
        self.assertFalse(claim["current_dev_used"])
        self.assertEqual({row["row_id"] for row in packet["train"]}, {"t1"})
        self.assertEqual({row["row_id"] for row in packet["evaluation"]}, {"t2"})
        self.assertNotIn("test_path", self.config)
        self.assertNotIn("dev_path", self.config)

    def test_train_cv_preflight_records_fixed_policy(self):
        from controller_candidate_harbor import validate_train_cv_artifact
        report = validate_train_cv_artifact(
            self.train_path, self.config["train_sha256"], "task-fixture")
        self.assertEqual(report["split_policy"],
                         "market_time_series_split_policy_v1")
        self.assertEqual(report["configured_holdout_days"], 3)
        self.assertEqual(report["cv_utc_dates"], [2])
        self.assertFalse(report["boundary_selected_using_targets"])
        self.assertFalse(report["random_shuffle"])

    def test_train_cv_never_splits_a_game_that_crosses_midnight(self):
        rows = [
            row("early", "early-game", 1, .4, .42),
            row("cross-before", "cross-game", 1, .9, .45),
            row("cross-after", "cross-game", 2, .1, .46),
            row("late", "late-game", 2, .4, .48),
        ]
        # Make the crossing explicit: row() uses mid as a within-day offset.
        rows[1]["decision_ms"] = 2 * DAY - 30_000
        rows[1]["feature_available_ms"] = rows[1]["decision_ms"]
        rows[1]["label_available_ms"] = rows[1]["decision_ms"] + 60_000
        fit, cv = temporal_train_cv(rows)
        self.assertEqual({item["game_id"] for item in fit}, {"early-game"})
        self.assertEqual({item["game_id"] for item in cv}, {"late-game"})
        self.assertFalse({item["game_id"] for item in fit}
                         & {item["game_id"] for item in cv})
        self.assertNotIn("cross-game", {item["game_id"] for item in fit + cv})
        self.assertLess(max(item["label_available_ms"] for item in fit),
                        min(item["feature_available_ms"] for item in cv))

    def test_train_cv_uses_fixed_three_day_suffix(self):
        rows = [
            row("d1", "g1", 1, .1, .11),
            row("d2", "g2", 2, .1, .12),
            row("d3", "g3", 3, .1, .13),
            row("d4", "g4", 4, .1, .14),
            row("d5", "g5", 5, .1, .15),
        ]
        fit, cv = temporal_train_cv(rows)
        self.assertEqual({item["game_id"] for item in fit}, {"g1", "g2"})
        self.assertEqual({item["game_id"] for item in cv}, {"g3", "g4", "g5"})

    def test_train_cv_does_not_move_boundary_to_make_split_feasible(self):
        rows = [
            row("d1", "crossing", 1, .1, .11),
            row("d3", "crossing", 3, .1, .13),
            row("d4", "g4", 4, .1, .14),
            row("d5", "g5", 5, .1, .15),
        ]
        with self.assertRaisesRegex(ValueError, "fixed multi-day"):
            temporal_train_cv(rows)

    def test_candidate_and_trusted_sources_are_hash_bound(self):
        prepare_job(self.request, self.workspace, self.config, self.job)
        sources = json.loads((self.job / "sources.json").read_text())
        sources["deployed"]["public/candidate.py"] += "\n# changed"
        (self.job / "sources.json").write_text(canonical(sources))
        with self.assertRaisesRegex(ValueError, "source hash changed"):
            verify_job(self.job)

    def test_time_series_split_audit_is_recomputed_not_just_self_hashed(self):
        prepare_job(self.request, self.workspace, self.config, self.job)
        audit = json.loads((self.job / "split-audit.json").read_text())
        audit["boundary_selected_using_targets"] = True
        (self.job / "split-audit.json").write_text(canonical(audit))
        claim = json.loads((self.job / "claim.json").read_text())
        claim["split_audit_sha256"] = digest(audit)
        (self.job / "claim.json").write_text(canonical(claim))
        with self.assertRaisesRegex(ValueError, "time-series split changed"):
            verify_job(self.job)

    def test_independent_score_returns_aggregate_only(self):
        claim = prepare_job(self.request, self.workspace, self.config, self.job)
        _, _, _, packet, labels, _ = verify_job(self.job)
        journal = PredictionJournal(self.job / "collected/predictions",
            train_sha256=fingerprint(packet["train"]),
            evaluation_sha256=fingerprint(packet["evaluation"]),
            candidate_sha256=claim["candidate_sha256"],
            expected_predictions=len(packet["evaluation"]))
        previous = "0" * 64
        for sequence, public in enumerate(packet["evaluation"]):
            record = {"sequence": sequence, "row_id": public["row_id"],
                      "prediction": labels[public["row_id"]],
                      "feature_row_sha256": fingerprint(public), "previous": previous}
            record["hash"] = fingerprint(record)
            journal.commit(record)
            previous = record["hash"]
        complete = journal.finish()
        fresh_json(self.job / "collected/isolation.json", {
            "checks": {name: True for name in ISOLATION_CHECKS}, "exit_code": 0,
            "probe_sha256": claim["deployed_hashes"]["public/isolation_probe.py"]})
        fresh_json(self.job / "collected/execution.json", {
            "stream": {"predictions": len(packet["evaluation"]), "scored": False},
            "complete": complete, "scored": False})
        fresh_json(self.job / "command.json", {"exit_code": 0, "stdout": "", "stderr": ""})
        fresh_json(self.job / "cleanup-01.json", {"sandbox_id": "fixture",
            "kill_acknowledged": True,
            "cost_reconciliation": "test receipt"})
        result = verify_and_score(self.job)
        self.assertEqual(result["evaluation_role"], "train_cv")
        self.assertRegex(result["prediction_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(result["primary"]["valid"])
        self.assertEqual(result["primary"]["candidate_all_rows_mse"], 0)
        self.assertNotIn("per_game", result)
        self.assertNotIn("row_outcomes", result)

    def test_command_exception_with_collected_candidate_failure_is_not_infrastructure(self):
        claim = prepare_job(self.request, self.workspace, self.config, self.job)
        collected = self.job / "collected"
        collected.mkdir()
        fresh_json(collected / "isolation.json", {
            "checks": {name: True for name in ISOLATION_CHECKS}, "exit_code": 0,
            "probe_sha256": claim["deployed_hashes"]["public/isolation_probe.py"]})
        fresh_json(collected / "failure.json", {
            "error_type": "KeyError", "scored": False})
        fresh_json(collected / "candidate-stderr.json", {
            "origin": "candidate_controlled_stderr", "bytes": 26,
            "sha256": "b" * 64, "encoding": "utf-8",
            "text": "Traceback: KeyError(-1)\n", "truncated": False,
            "independent_diagnosis": False})
        fresh_json(self.job / "command-error.json", {
            "error_type": "CommandExitException"})
        fresh_json(self.job / "cleanup-01.json", {"sandbox_id": "fixture",
            "kill_acknowledged": True, "cost_reconciliation": "test receipt"})
        result = verify_candidate_failure(self.job)
        self.assertEqual(result["failure_code"], "KeyError")
        self.assertEqual(result["candidate_sha256"], claim["candidate_sha256"])
        self.assertFalse(result["scored"])
        self.assertIn("KeyError", result["candidate_diagnostic"]["text_prefix"])
        self.assertFalse(result["candidate_diagnostic"]["trusted_for_scoring"])

    def test_candidate_failure_without_command_evidence_stays_infrastructure_unknown(self):
        claim = prepare_job(self.request, self.workspace, self.config, self.job)
        collected = self.job / "collected"
        collected.mkdir()
        fresh_json(collected / "isolation.json", {
            "checks": {name: True for name in ISOLATION_CHECKS}, "exit_code": 0,
            "probe_sha256": claim["deployed_hashes"]["public/isolation_probe.py"]})
        fresh_json(collected / "failure.json", {
            "error_type": "KeyError", "scored": False})
        fresh_json(collected / "candidate-stderr.json", {
            "origin": "candidate_controlled_stderr", "bytes": 0,
            "sha256": hashlib.sha256(b"").hexdigest(), "encoding": "utf-8",
            "text": "", "truncated": False, "independent_diagnosis": False})
        fresh_json(self.job / "cleanup-01.json", {"sandbox_id": "fixture",
            "kill_acknowledged": True, "cost_reconciliation": "test receipt"})
        with self.assertRaisesRegex(ValueError, "terminal command evidence"):
            verify_candidate_failure(self.job)

    def test_e2b_nonzero_exception_preserves_terminal_diagnostics(self):
        from e2b.sandbox.commands.command_handle import CommandExitException
        error = CommandExitException(stderr="trusted runner error", stdout="partial",
                                     exit_code=7, error=None)
        self.assertEqual(terminal_nonzero_result(error), {
            "exit_code": 7,
            "stdout": "partial",
            "stderr": "trusted runner error",
        })
        self.assertIsNone(terminal_nonzero_result(TimeoutError("ambiguous transport")))


if __name__ == "__main__":
    unittest.main()
