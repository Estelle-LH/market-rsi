import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from market_rsi import fresh_json
from run_training_sampling_diagnostic import fit_predict, metrics, run


class TrainingSamplingDiagnosticTests(unittest.TestCase):
    def test_full_sampling_matches_both_loss_normalizations(self):
        x = np.column_stack([np.ones(10), np.arange(10)])
        y = np.arange(10) * 0.001
        masks = [{"keep": True, "loss_weight": 1.} for _ in y]
        a, _ = fit_predict(x, y, x, masks, population_rows=10,
                           inverse_probability=True, alpha=.01)
        b, _ = fit_predict(x, y, x, masks, population_rows=10,
                           inverse_probability=False, alpha=.01)
        np.testing.assert_array_equal(a, b)

    def test_metric_includes_zero_future_moves(self):
        rows = [{"target": .5, "features": {"mid": .5}, "game_id": "a"},
                {"target": .6, "features": {"mid": .5}, "game_id": "b"}]
        result = metrics(rows, np.array([.6, .6]))
        self.assertEqual(result["rows"], 2)
        self.assertAlmostEqual(result["equal_game_mse_probability_squared"], .005)
        self.assertEqual(result["future_activity_diagnostics_only"]["flat_future"]["rows"], 1)

    def test_complete_offline_fixture_and_no_source_mutation(self):
        rows = []
        for day in range(8):
            for i in range(20):
                decision = 1787961600000 + day * 86400000 + i * 1000
                rows.append({
                    "row_id": f"{day}-{i}", "game_id": f"g{day}", "market_id": f"m{day}",
                    "decision_ms": decision, "feature_available_ms": decision,
                    "label_available_ms": decision + 330000,
                    "features": {"mid": .5, "bid": .49, "ask": .51, "spread": .02,
                                 "bid_size": 10., "ask_size": 10., "imbalance": 0.},
                    "target": .5 if i % 2 else .51})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "train.json"
            fresh_json(source, {"schema": "market_permitted_rows_v1", "split": "train", "rows": rows})
            before = source.read_bytes()
            result = run(source, root / "out")
            self.assertEqual(before, source.read_bytes())
            self.assertEqual(len(result["results"]), 7)
            self.assertFalse(result["promotion_eligible"])
            self.assertIsNone(result["selected_variant"])
            self.assertTrue(all(r["changed_states_dropped"] == 0 for r in result["results"]))
            self.assertEqual(len({r["score"]["rows"] for r in result["results"]}), 1)
            spec = json.loads((root / "out/pre-fit-spec.json").read_bytes())
            baseline = spec["baseline_component_ids"]
            for candidate in result["results"][1:]:
                changed = [s for s in baseline if baseline[s] != candidate["candidate_component_ids"][s]]
                self.assertEqual(changed, ["prediction"])
            with self.assertRaises(FileExistsError):
                run(source, root / "out")


if __name__ == "__main__":
    unittest.main()
