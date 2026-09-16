from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import prepare_archive_carryover_canary as module
from market_rsi import digest


class PrepareArchiveCarryoverCanaryTests(unittest.TestCase):
    def test_prepare_validates_current_source_before_creating_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_round = root / "polymarket-rsi-round1-20260907-01"
            (source_round / "runner").mkdir(parents=True)
            train = root / "train.json"
            dev = root / "dev.json"
            train.write_text("{}")
            dev.write_text("{}")
            task_id = "fixture-task"
            (source_round / "runner" / "config.json").write_text(json.dumps({
                "task_data": {task_id: {
                    "train_path": str(train), "dev_path": str(dev),
                }},
            }))
            task_root = root / "polymarket-rsi-round1-20260907-01-data" / "freeze-v8"
            task_root.mkdir(parents=True)
            (task_root / "tasks.json").write_text(json.dumps([{
                "task_id": task_id, "opaque_test_commitment": "f" * 64,
            }]))
            current_source = {
                "schema": "market_controller_source_manifest_v1",
                "sources": {"fixture.py": "a" * 64},
            }
            history = {
                "source_manifest_sha256": digest(current_source),
                "snapshots": [{"snapshot_sha256": "b" * 64}],
            }
            history_path = root / "history.json"
            history_path.write_text(json.dumps(history))

            budget = unittest.mock.Mock()
            budget.snapshot.return_value = {"experiment_id": "fixture-experiment"}
            output = root / "new-session"
            with (patch.object(module, "validate_history", return_value={
                    "legacy_empty": False, "snapshots": 1}),
                  patch.object(module, "source_manifest", return_value=current_source),
                  patch.object(module, "PaidBudget", return_value=budget),
                  patch.object(module, "prepare_workspace", return_value={
                      "schema": "fixture-workspace"}),
                  patch.object(module, "literature_snapshot", return_value={
                      "schema": "fixture-literature"}),
                  patch.object(module, "freeze_source_manifest",
                               return_value=current_source)):
                receipt = module.prepare(
                    output, source_round, history_path, root / "budget",
                    root / ".env", root / "cache", Path(sys.executable), task_id)

            self.assertEqual(receipt["model_calls"], 0)
            self.assertEqual(receipt["source_manifest_sha256"], digest(current_source))
            self.assertEqual(receipt["prior_snapshot_sha256"], "b" * 64)
            self.assertTrue((output / "preparation.json").is_file())


if __name__ == "__main__":
    unittest.main()
