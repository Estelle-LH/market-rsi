from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from market_rsi import fresh_json
from objective_contract import build_objective_contract
from project_selected_objective import project


class SelectedObjectiveProjectionTests(unittest.TestCase):
    def test_projects_only_nonnull_frozen_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = build_objective_contract(
                experiment_id="experiment-1",
                objective_id="future-midpoint-window-mean-270-330s-v1",
                train_diagnostics_sha256="a" * 64,
                literature_snapshot_sha256="b" * 64,
                literature_ids=[],
                evidence_class="diagnostic",
            )
            fresh_json(root / "contract.json", contract)
            base = {
                "game_id": "g", "market_id": "m", "game_start_ms": 1,
                "decision_ms": 2, "feature_available_ms": 2,
                "label_available_ms": 400_000, "features": {"mid": 0.5},
                "input_source": {"sha256": "c" * 64},
            }
            source = {
                "schema": "polymarket_objective_labels_v1",
                "scientific_admission": False, "future_test_used": False,
                "source_bundle_sha256": "d" * 64,
                "rows": [
                    {**base, "row_id": "one", "target_candidates": {
                        contract["objective_id"]: 0.6}},
                    {**base, "row_id": "two", "target_candidates": {
                        contract["objective_id"]: None}},
                ],
            }
            fresh_json(root / "source.json", source)
            result = project([root / "source.json"], root / "contract.json")
            self.assertEqual(len(result["rows"]), 1)
            self.assertEqual(result["rows"][0]["target"], 0.6)
            self.assertEqual(result["rows"][0]["label_available_ms"], 330_002)
            self.assertEqual(result["label_delay_bounds_ms"], [330_000, 330_000])
            self.assertFalse(result["test_opened"])


if __name__ == "__main__":
    unittest.main()
