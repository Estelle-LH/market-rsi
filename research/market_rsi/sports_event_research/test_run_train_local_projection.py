import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from sports_event_research.run_train_local_projection import (
    equal_game_weights,
    fit_clustered_wls,
    write_json,
)


class TrainLocalProjectionTests(unittest.TestCase):
    def test_equal_game_weights_give_each_game_same_mass(self):
        games = ["a", "a", "a", "b"]
        weights = equal_game_weights(games)
        self.assertAlmostEqual(weights[:3].sum(), weights[3:].sum())

    def test_clustered_wls_recovers_known_coefficients(self):
        design = np.asarray([
            [1.0, 0.0], [1.0, 1.0], [1.0, 2.0],
            [1.0, 3.0], [1.0, 4.0], [1.0, 5.0],
        ])
        outcome = 0.25 + 2.0 * design[:, 1]
        result = fit_clustered_wls(
            design, outcome, np.ones(6), ["a", "a", "a", "b", "b", "b"],
            ["intercept", "event"],
        )
        estimates = {row["feature"]: row for row in result["estimates"]}
        self.assertAlmostEqual(estimates["intercept"]["coefficient"], 0.25)
        self.assertAlmostEqual(estimates["event"]["coefficient"], 2.0)
        self.assertEqual(result["game_clusters"], 2)

    def test_rank_deficient_design_fails_closed(self):
        design = np.asarray([[1.0, 1.0], [1.0, 1.0], [1.0, 1.0], [1.0, 1.0]])
        with self.assertRaisesRegex(ValueError, "rank-deficient"):
            fit_clustered_wls(
                design, np.arange(4.0), np.ones(4), ["a", "a", "b", "b"],
                ["intercept", "constant"],
            )

    def test_json_writer_rejects_nan(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                write_json(Path(temporary) / "bad.json", {"value": float("nan")})

    def test_json_writer_produces_strict_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "good.json"
            write_json(path, {"value": None})
            loaded = json.loads(path.read_text(), parse_constant=lambda value: self.fail(value))
            self.assertIsNone(loaded["value"])


if __name__ == "__main__":
    unittest.main()
