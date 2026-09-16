"""Synthetic contract checks; no protected market labels are loaded."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from prediction_benchmark_v0.score import digest, score


def write_csv(path: Path, columns: list[str], rows: list[list[object]]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)


class PredictionBenchmarkScoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / "manifest.json"
        self.labels = self.root / "labels.csv"
        self.baselines = self.root / "baselines.csv"
        self.candidate = self.root / "candidate.csv"
        self.rows = [{"row_id": f"r{n}", "game_id": f"g{n}",
                      "date": f"2026-09-{n+1:02d}"} for n in range(20)]
        write_csv(self.labels, ["row_id", "target"], [[row["row_id"], ".2"] for row in self.rows])
        write_csv(self.baselines, ["row_id", "b0", "b1", "b2", "strong"],
                  [[row["row_id"], "0", ".025", ".05", ".1"] for row in self.rows])
        write_csv(self.candidate, ["row_id", "candidate"],
                  [[row["row_id"], ".2"] for row in self.rows])
        self.freeze()

    def freeze(self, *, coverage: float = 1.0) -> None:
        self.manifest.write_text(json.dumps({
            "schema": "prediction_benchmark_v0", "horizon_seconds": 60,
            "baseline_sha256": digest(self.baselines), "min_label_coverage": coverage,
            "candidate_sha256": digest(self.candidate),
            "source_sha256": "a" * 64, "label_rule_sha256": "b" * 64,
            "fit_through_date": "2026-08-31",
            "rows": self.rows,
        }))

    def evaluate(self) -> dict:
        return score(self.manifest, self.labels, self.baselines, self.candidate, draws=200)

    def test_paired_full_cohort_beats_frozen_baseline(self) -> None:
        result = self.evaluate()
        self.assertTrue(result["beat_benchmark"])
        self.assertAlmostEqual(result["equal_game_mse"]["strong"], .01)
        self.assertAlmostEqual(result["equal_game_mse"]["candidate"], 0)
        self.assertAlmostEqual(result["equal_game_rmse_probability_points"]["strong"], 10)
        self.assertAlmostEqual(result["candidate_gain_vs_strong"], 1)
        for endpoint in result["paired_date_block_95pct_interval"]:
            self.assertAlmostEqual(endpoint, -.01)

    def test_missing_label_is_not_fabricated_zero(self) -> None:
        label_rows = [[row["row_id"], ".2"] for row in self.rows]
        label_rows[0][1] = ""
        write_csv(self.labels, ["row_id", "target"], label_rows)
        self.freeze(coverage=.95)
        with self.assertRaisesRegex(ValueError, "game with no observed labels"):
            self.evaluate()

    def test_partial_missing_label_preserves_coverage(self) -> None:
        self.rows.append({"row_id": "extra", "game_id": "g0", "date": "2026-09-01"})
        write_csv(self.labels, ["row_id", "target"],
                  [[row["row_id"], "" if row["row_id"] == "extra" else ".2"] for row in self.rows])
        write_csv(self.baselines, ["row_id", "b0", "b1", "b2", "strong"],
                  [[row["row_id"], "0", ".025", ".05", ".1"] for row in self.rows])
        write_csv(self.candidate, ["row_id", "candidate"],
                  [[row["row_id"], ".2"] for row in self.rows])
        self.freeze(coverage=.95)
        result = self.evaluate()
        self.assertEqual(result["cohort_rows"], 21)
        self.assertEqual(result["labelled_rows"], 20)
        self.assertAlmostEqual(result["per_game"][0]["label_coverage"], .5)
        self.assertAlmostEqual(result["equal_game_mse"]["strong"], .01)

    def test_full_prediction_population_is_mandatory(self) -> None:
        write_csv(self.candidate, ["row_id", "candidate"],
                  [[row["row_id"], ".2"] for row in self.rows[:-1]])
        self.freeze()
        with self.assertRaisesRegex(ValueError, "every frozen row"):
            self.evaluate()

    def test_changed_baseline_is_rejected(self) -> None:
        write_csv(self.baselines, ["row_id", "b0", "b1", "b2", "strong"],
                  [[row["row_id"], "0", ".025", ".05", ".19"] for row in self.rows])
        with self.assertRaisesRegex(ValueError, "changed after freeze"):
            self.evaluate()

    def test_changed_candidate_is_rejected(self) -> None:
        write_csv(self.candidate, ["row_id", "candidate"],
                  [[row["row_id"], ".19"] for row in self.rows])
        with self.assertRaisesRegex(ValueError, "candidate forecasts changed"):
            self.evaluate()

    def test_beating_ridge_but_not_strong_does_not_pass(self) -> None:
        write_csv(self.candidate, ["row_id", "candidate"],
                  [[row["row_id"], ".075"] for row in self.rows])
        self.freeze()
        result = self.evaluate()
        self.assertLess(result["equal_game_mse"]["candidate"], result["equal_game_mse"]["b2"])
        self.assertGreater(result["equal_game_mse"]["candidate"], result["equal_game_mse"]["strong"])
        self.assertFalse(result["beat_benchmark"])

    def test_training_date_overlap_is_rejected(self) -> None:
        record = json.loads(self.manifest.read_text())
        record["fit_through_date"] = "2026-09-01"
        self.manifest.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "overlaps training"):
            self.evaluate()

    def test_not_enough_dates_stays_pilot(self) -> None:
        self.rows = self.rows[:19]
        write_csv(self.labels, ["row_id", "target"], [[row["row_id"], ".2"] for row in self.rows])
        write_csv(self.baselines, ["row_id", "b0", "b1", "b2", "strong"],
                  [[row["row_id"], "0", ".025", ".05", ".1"] for row in self.rows])
        write_csv(self.candidate, ["row_id", "candidate"],
                  [[row["row_id"], ".2"] for row in self.rows])
        self.freeze()
        result = self.evaluate()
        self.assertFalse(result["beat_benchmark"])
        self.assertFalse(result["gates"]["at_least_20_dates"])


if __name__ == "__main__":
    unittest.main()
