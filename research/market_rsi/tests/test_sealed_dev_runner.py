from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from controller_tools_mcp import Broker, REQUIRED_DECISION_FIELDS
from controller_workspace import LITERATURE_SCHEMA, prepare_workspace
from data_lifecycle import DataLifecycle
from market_rsi import canonical, digest, fresh_json
from sealed_dev_runner import run_once


DAY = 86_400_000


def row(name, game, day, mid, target):
    decision = day * DAY + int(mid * 1000)
    return {"row_id": name, "game_id": game, "market_id": game + "-market",
            "decision_ms": decision, "feature_available_ms": decision,
            "features": {"mid": mid}, "target": target,
            "label_available_ms": decision + 60_000}


class SealedDevRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        train = {"schema": "market_permitted_rows_v1", "experiment_id": "source",
                 "task_id": "task", "split": "train", "feature_names": ["mid"],
                 "rows": [row("t1", "train-1", 1, .4, .42),
                          row("t2", "train-2", 2, .5, .52)]}
        dev = {"schema": "market_permitted_rows_v1", "experiment_id": "source",
               "task_id": "task", "split": "dev", "feature_names": ["mid"],
               "rows": [row("d1", "dev-1", 3, .6, .58)]}
        self.train_path, self.dev_path = self.root / "train.json", self.root / "dev.json"
        self.train_path.write_text(canonical(train))
        self.dev_path.write_text(canonical(dev))
        prepare_workspace(self.workspace, session_id="session", experiment_id="experiment",
            task_id="task", arm="archive", train_path=self.train_path,
            dev_path=self.dev_path, own_history={"rounds": []},
            literature_snapshot={"schema": LITERATURE_SCHEMA, "papers": []},
            opaque_test_commitment="a" * 64)
        broker = Broker(self.workspace, "formal")
        broker.call("write_candidate", {"name": "candidate.py",
            "content": ("def fit(train_rows, feature_names): return None\n"
                        "def predict(model, public_row): return .5\n"),
            "algorithm_family": "fixture", "hypothesis": "fixture hypothesis",
            "literature_ids": [], "change_summary": "fixture"})

        def cv_runner():
            for _ in range(200):
                requests = list((self.workspace / "execution-requests").glob("*.json"))
                if requests:
                    request = json.loads(requests[0].read_text())
                    fresh_json(self.workspace / "execution-results" / requests[0].name, {
                        "schema": "market_controller_execution_result_v1",
                        "execution_id": request["execution_id"],
                        "request_sha256": digest(request),
                        "candidate_sha256": request["candidate_sha256"],
                        "evaluation_role": "train_cv", "execution_verified": True,
                        "future_test_used": False, "automatic_retry": False,
                        "status": "completed", "score": {
                            "primary": {"valid": True},
                            "prediction_sha256": "c" * 64},
                    })
                    return
                time.sleep(.01)

        thread = threading.Thread(target=cv_runner)
        thread.start()
        broker.call("run_train_cv_candidate", {"name": "candidate.py"})
        thread.join()
        decision = {key: "fixture" for key in REQUIRED_DECISION_FIELDS}
        decision["action"] = "select"
        decision["candidate_artifact"] = "candidate.py"
        broker.call("submit_decision", {"decision": decision})

        self.lifecycle = DataLifecycle.create(self.root / "lifecycle",
            experiment_id="experiment", rounds=[{
                "round_id": "round-01",
                "train_datasets": [{"dataset_id": "train-open", "content_sha256": "1" * 64}],
                "dev_datasets": [{"dataset_id": "dev-sealed", "content_sha256": "2" * 64}],
            }], transfer_datasets=[{
                "dataset_id": "transfer-sealed", "content_sha256": "3" * 64,
            }])
        view = self.lifecycle.controller_view("round-01")
        self.session_assessment = self.root / "session-assessment.json"
        fresh_json(self.session_assessment, {"valid": True, "process_reaped": True,
                                             "submitted_decision_present": True,
                                             "controller_integrity": {
                                                 "valid": True}})
        self.config = self.root / "sealed-config.json"
        fresh_json(self.config, {
            "schema": "market_controller_sealed_dev_runner_v1", "session_id": "session",
            "experiment_id": "experiment", "task_id": "task",
            "train_path": str(self.train_path.resolve()),
            "train_sha256": hashlib.sha256(self.train_path.read_bytes()).hexdigest(),
            "dev_path": str(self.dev_path.resolve()),
            "dev_sha256": hashlib.sha256(self.dev_path.read_bytes()).hexdigest(),
            "lifecycle_root": str(self.lifecycle.root), "round_id": "round-01",
            "controller_view_sha256": digest(view),
            "train_dataset_ids": ["train-open"], "dev_dataset_ids": ["dev-sealed"],
            "session_assessment_path": str(self.session_assessment.resolve()),
            "budget_path": str((self.root / "budget").resolve()),
            "env_file": str((self.root / ".env").resolve()),
            "budget_bucket": "learning", "evidence_class": "diagnostic",
        })

    def tearDown(self):
        self.temp.cleanup()

    def test_dev_runs_once_only_after_session_exit_and_promotes(self):
        score = {"evaluation_role": "sealed_dev", "primary": {"valid": True},
                 "coverage": {"coverage_fraction": 1.0}}
        with patch("sealed_dev_runner.run_job", AsyncMock(return_value=score)):
            outcome = asyncio.run(run_once(
                self.workspace, self.config, self.root / "sealed-dev-round-01"))
        self.assertEqual(outcome["score_receipt"]["score"], score)
        self.assertFalse(outcome["score_receipt"]["score_visible_to_same_session"])
        self.assertEqual(self.lifecycle.audit()["completed_rounds"], ["round-01"])
        self.assertEqual(self.lifecycle.audit()["promoted_dev_ids"], ["dev-sealed"])
        self.assertTrue((self.workspace / "sealed-dev-result.json").is_file())
        claim = json.loads(next((self.root / "sealed-dev-round-01").glob(
            "*/claim.json")).read_text())
        self.assertEqual(claim["job_id"],
                         "session-sealed-dev-round-01-execution")
        with self.assertRaisesRegex(ValueError, "already exists"):
            asyncio.run(run_once(self.workspace, self.config, self.root / "another-output"))

    def test_controller_must_be_reaped_before_dev_can_open(self):
        self.session_assessment.write_text(canonical({
            "valid": True, "process_reaped": False,
            "submitted_decision_present": True,
            "controller_integrity": {"valid": True},
        }))
        with self.assertRaisesRegex(ValueError, "finish and exit"):
            asyncio.run(run_once(self.workspace, self.config, self.root / "sealed-dev-round-01"))
        self.assertEqual(self.lifecycle.audit()["completed_rounds"], [])
        self.assertIsNone(self.lifecycle.audit()["active_dev_claim"])

    def test_local_job_preflight_failure_is_durable_and_does_not_call_provider(self):
        output = self.root / "sealed-dev-round-01"
        with patch("sealed_dev_runner.prepare_sealed_dev_job",
                   side_effect=ValueError("fixture preflight")), \
                patch("sealed_dev_runner.run_job", AsyncMock()) as run_job:
            with self.assertRaisesRegex(RuntimeError, "local preflight failed"):
                asyncio.run(run_once(self.workspace, self.config, output))
        run_job.assert_not_awaited()
        failure = json.loads((output / "infrastructure-failure.json").read_text())
        self.assertEqual(failure["stage"], "local_job_preparation")
        self.assertFalse(failure["provider_called"])
        self.assertFalse(failure["dev_score_completed"])
        self.assertIsNotNone(self.lifecycle.audit()["active_dev_claim"])


if __name__ == "__main__":
    unittest.main()
