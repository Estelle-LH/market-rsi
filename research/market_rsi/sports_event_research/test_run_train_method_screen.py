import unittest
import json
from pathlib import Path
import tempfile

import numpy as np

from sports_event_research.run_train_method_screen import (
    block_interval,
    equal_game_weights,
    metrics,
    raw_signal_diagnostics,
    rolling_folds,
    write_json,
)


class TrainMethodScreenTests(unittest.TestCase):
    def test_frozen_rolling_folds_are_disjoint_and_expanding(self):
        games = [f"g{index:03d}" for index in range(163)]
        folds = rolling_folds(games)
        self.assertEqual([len(fold["fit_games"]) for fold in folds], [100, 121, 142])
        self.assertEqual([len(fold["check_games"]) for fold in folds], [21, 21, 21])
        checked = [game for fold in folds for game in fold["check_games"]]
        self.assertEqual(len(checked), len(set(checked)))
        self.assertEqual(checked, games[100:])

    def test_wrong_population_or_duplicate_game_fails(self):
        with self.assertRaisesRegex(ValueError, "frozen rolling design"):
            rolling_folds(["a", "b"], initial_games=1, block_games=1, blocks=2)
        games = [f"g{index:03d}" for index in range(162)] + ["g000"]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            rolling_folds(games)

    def test_equal_game_weights_do_not_overweight_long_games(self):
        rows = [{"game": "a"}, {"game": "a"}, {"game": "a"}, {"game": "b"}]
        weights = equal_game_weights(rows, np.arange(4))
        self.assertAlmostEqual(weights[:3].sum(), weights[3:].sum())

    def test_perfect_prediction_beats_zero_on_every_game(self):
        rows = [
            {"game": "a", "game_date": "2025-01-01", "target": value}
            for value in (0.1, -0.2, 0.3)
        ] + [
            {"game": "b", "game_date": "2025-01-02", "target": value}
            for value in (-0.1, 0.2, -0.3)
        ]
        target = np.asarray([row["target"] for row in rows])
        result = metrics(rows, np.arange(len(rows)), target)
        self.assertEqual(result["equal_game_candidate_mse"], 0.0)
        self.assertEqual(result["relative_mse_improvement"], 1.0)
        self.assertEqual(result["positive_game_fraction"], 1.0)
        self.assertEqual(result["positive_date_fraction"], 1.0)

    def test_date_block_interval_is_seeded_and_date_weighted(self):
        values = {"2025-01-01": [-1.0, -1.0], "2025-01-02": [1.0]}
        first = block_interval(values, draws=1000)
        second = block_interval(values, draws=1000)
        self.assertEqual(first, second)
        self.assertEqual(first["dates"], 2)
        self.assertEqual(first["unit"], "UTC_date_equal_weight")

    def test_constant_raw_feature_is_explicit_not_nan(self):
        rows = []
        for index in range(4):
            numeric = [float(index + feature) for feature in range(13)]
            numeric[8] = 1.0
            rows.append({"numeric": numeric, "target": float(index)})
        result = raw_signal_diagnostics(rows, np.arange(4))
        self.assertIn("official", result["constant_numeric_features"])
        official = 8
        self.assertIsNone(result["numeric_pairwise_correlation"][official][0])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "strict.json"
            write_json(path, result)
            json.loads(path.read_text(), parse_constant=lambda value: self.fail(value))

    def test_json_writer_rejects_nonfinite_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                write_json(Path(temporary) / "bad.json", {"value": float("nan")})


if __name__ == "__main__":
    unittest.main()
