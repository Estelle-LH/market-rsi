from __future__ import annotations

from datetime import datetime, timezone
import json
import tempfile
import unittest
from pathlib import Path

from literature_catalog import literature_snapshot
from market_rsi import fresh_json
from objective_discovery_workspace import prepare_workspace, validate_workspace


DATES = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"]


def source() -> dict:
    rows = []
    for day in range(1, 5):
        base = int(datetime(2026, 9, day, tzinfo=timezone.utc).timestamp() * 1000)
        for second in range(0, 181, 15):
            mid = 0.40 + second / 10_000
            rows.append({
                "row_id": f"{day}-{second}", "game_id": f"game-{day}",
                "market_id": f"market-{day}", "decision_ms": base + second * 1000,
                "features": {"mid": mid}, "target": min(1.0, mid + 0.005),
            })
    return {"schema": "polymarket_midpoint_labels_v1", "rows": rows}


class ObjectiveDiscoveryWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "opened-train.json"
        fresh_json(self.source, source())
        self.workspace = self.root / "workspace"
        self.manifest = prepare_workspace(
            self.workspace,
            session_id="objective-discovery-fixture",
            experiment_id="objective-fixture",
            source_path=self.source,
            opened_train_utc_dates=DATES,
            literature_snapshot=literature_snapshot(),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_workspace_has_train_evidence_but_no_dev(self):
        self.assertTrue(validate_workspace(self.workspace))
        self.assertFalse(self.manifest["dev_artifact_present"])
        names = {path.name for path in self.workspace.iterdir()}
        self.assertFalse(any("dev" in name for name in names))
        audit = json.loads((self.workspace / "automatic-objective-audit.json").read_text())
        self.assertEqual(audit["status"], "completed")

    def test_source_mutation_is_detected(self):
        self.source.write_text("{}\n")
        with self.assertRaisesRegex(ValueError, "source changed"):
            validate_workspace(self.workspace)


if __name__ == "__main__":
    unittest.main()
