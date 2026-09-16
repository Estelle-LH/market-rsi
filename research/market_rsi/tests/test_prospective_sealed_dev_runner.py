import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from market_rsi import digest
from prospective_data_lifecycle import ProspectiveDataLifecycle
from prospective_sealed_dev_runner import run_once
from test_sealed_dev_runner import SealedDevRunnerTests


class ProspectiveSealedDevRunnerTests(SealedDevRunnerTests):
    def setUp(self):
        super().setUp()
        lifecycle = ProspectiveDataLifecycle.create(self.root / "prospective-lifecycle",
            experiment_id="experiment", rounds=[{
                "round_id": "round-01",
                "train_datasets": [{"dataset_id": "train-open", "content_sha256": "1" * 64}],
                "dev_datasets": [{"dataset_id": "dev-sealed", "content_sha256": "2" * 64}],
            }], transfer_policy_sha256="3" * 64)
        config = json.loads(self.config.read_text())
        config["lifecycle_root"] = str(lifecycle.root)
        config["controller_view_sha256"] = digest(lifecycle.controller_view("round-01"))
        self.config.write_text(json.dumps(config, sort_keys=True, separators=(",", ":")))
        self.lifecycle = lifecycle

    def test_dev_runs_once_only_after_session_exit_and_promotes(self):
        score = {"evaluation_role": "sealed_dev", "primary": {"valid": True},
                 "coverage": {"coverage_fraction": 1.0}}
        with patch("sealed_dev_runner.run_job", AsyncMock(return_value=score)):
            outcome = asyncio.run(run_once(
                self.workspace, self.config, self.root / "sealed-dev-round-01"))
        self.assertEqual(outcome["schema"],
                         "market_controller_prospective_sealed_dev_outcome_v2")
        self.assertEqual(self.lifecycle.audit()["completed_rounds"], ["round-01"])
        self.assertFalse(self.lifecycle.audit()["transfer_materialized"])

    def test_controller_must_be_reaped_before_dev_can_open(self):
        assessment = json.loads(self.session_assessment.read_text())
        assessment["process_reaped"] = False
        self.session_assessment.write_text(json.dumps(
            assessment, sort_keys=True, separators=(",", ":")))
        with self.assertRaisesRegex(ValueError, "finish and exit"):
            asyncio.run(run_once(
                self.workspace, self.config, self.root / "sealed-dev-round-01"))
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


del SealedDevRunnerTests


if __name__ == "__main__":
    unittest.main()
