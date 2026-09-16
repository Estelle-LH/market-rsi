from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from controller_execution_service import ControllerExecutionService
from controller_workspace import LITERATURE_SCHEMA, prepare_workspace
from market_rsi import canonical, digest, fresh_json


def row(name, game, day, mid, target):
    decision = day * 86_400_000 + int(mid * 1000)
    return {"row_id": name, "game_id": game, "market_id": game + "-market",
            "decision_ms": decision, "feature_available_ms": decision,
            "features": {"mid": mid}, "target": target,
            "label_available_ms": decision + 60_000}


class ControllerExecutionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        train = {"schema": "market_permitted_rows_v1", "experiment_id": "source",
                 "task_id": "task", "split": "train", "feature_names": ["mid"],
                 "rows": [row("t1", "train-game-1", 1, .4, .42),
                          row("t2", "train-game-2", 2, .5, .52)]}
        dev = {"schema": "market_permitted_rows_v1", "experiment_id": "source",
               "task_id": "task", "split": "dev", "feature_names": ["mid"],
               "rows": [row("d", "dev-game", 3, .6, .58)]}
        self.train, self.dev = self.root / "train.json", self.root / "dev.json"
        self.train.write_text(canonical(train)); self.dev.write_text(canonical(dev))
        abstract = "A frozen public abstract."
        manifest = prepare_workspace(self.workspace, session_id="session-fixture",
            experiment_id="experiment-fixture", task_id="task", arm="learn",
            train_path=self.train, dev_path=self.dev, own_history={"rounds": []},
            literature_snapshot={"schema": LITERATURE_SCHEMA, "papers": [{
                "paper_id": "p", "title": "Paper", "url": "https://example.org/p",
                "year": 2020, "abstract": abstract,
                "content_sha256": hashlib.sha256(abstract.encode()).hexdigest()}]},
            opaque_test_commitment="b" * 64)
        source = "def fit(train_rows, feature_names): return None\ndef predict(model, row): return .5\n"
        (self.workspace / "candidate.py").write_text(source)
        self.request = {"schema": "market_controller_execution_request_v1",
            "execution_id": "session-fixture-execution-01", "session_id": "session-fixture",
            "experiment_id": "experiment-fixture", "task_id": "task",
            "candidate_name": "candidate.py",
            "candidate_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "workspace_manifest_sha256": digest(manifest), "evaluation_role": "train_cv",
            "automatic_retry": False}
        fresh_json(self.workspace / "execution-requests" / "session-fixture-execution-01.json",
                   self.request)
        config = {"schema": "market_controller_runner_v1", "session_id": "session-fixture",
            "experiment_id": "experiment-fixture", "task_id": "task",
            "train_path": str(self.train.resolve()),
            "train_sha256": hashlib.sha256(self.train.read_bytes()).hexdigest(),
            "budget_path": str((self.root / "budget").resolve()),
            "env_file": str((self.root / ".env").resolve()),
            "budget_bucket": "setup", "evidence_class": "synthetic"}
        self.config_path = self.root / "runner-config.json"
        self.config_path.write_text(canonical(config))

    def tearDown(self):
        self.temp.cleanup()

    def test_completed_execution_is_bound_and_aggregate(self):
        score = {"evaluation_role": "train_cv",
                 "primary": {"valid": True, "candidate_all_rows_mse": .01},
                 "coverage": {"coverage_fraction": 1.0},
                 "score_sha256": "c" * 64, "claim_boundary": "diagnostic"}
        service = ControllerExecutionService(self.workspace, self.config_path,
                                             self.root / "executions")
        with patch("controller_execution_service.run_job", AsyncMock(return_value=score)):
            result = service.execute_request(
                self.workspace / "execution-requests/session-fixture-execution-01.json")
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["execution_verified"])
        self.assertEqual(result["evaluation_role"], "train_cv")
        self.assertFalse(result["future_test_used"])
        self.assertEqual(result["score"], score)

    def test_infrastructure_failure_is_not_relabelled_as_candidate_failure(self):
        service = ControllerExecutionService(self.workspace, self.config_path,
                                             self.root / "executions")
        with patch("controller_execution_service.run_job", AsyncMock(side_effect=OSError("infra"))), \
                patch("controller_execution_service.verify_candidate_failure",
                      side_effect=ValueError("no verified candidate failure")):
            result = service.execute_request(
                self.workspace / "execution-requests/session-fixture-execution-01.json")
        self.assertEqual(result["status"], "infrastructure_failed")
        self.assertFalse(result["execution_verified"])
        self.assertFalse(result["automatic_retry"])


if __name__ == "__main__":
    unittest.main()
