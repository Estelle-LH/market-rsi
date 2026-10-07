"""Synthetic scoring checks; no resident Train data or fitted models."""
import copy
import math
import unittest

from experiments.nfl_ingame_price_score import B0, score


def row(key, game, label, day="2025-11-01", week="09", fold="check_1", forecastable=True):
    return {"row_id": key, "game_id": game, "game_date": day, "game_week": week,
            "fold": fold, "forecastable": forecastable,
            "p_current": 0.5 if forecastable else None, "label": label}


class PriceScoreTests(unittest.TestCase):
    def setUp(self):
        self.rows = [row("a1", "a", .1), row("a2", "a", .2), row("b", "b", -.1),
                     row("c", "c", 0, "2025-11-02", "10"), row("missing", "d", None),
                     row("cold", "e", None, forecastable=False),
                     row("fit", "initial", .9, "2025-10-01", "05", "initial_fit")]
        self.rows[-1]["p_current"] = .05
        self.predictions = {B0: {k: 0 for k in ("a1", "a2", "b", "c", "missing")},
                            "candidate": {k: .02 for k in ("a1", "a2", "b", "c", "missing")}}

    def result(self):
        return score(self.rows, self.predictions, draws=200)

    def test_game_equal_not_row_or_date_equal(self):
        result = self.result()
        self.assertAlmostEqual(result["equal_game_mse"][B0], (.025 + .01 + 0) / 3)
        self.assertAlmostEqual(result["equal_game_mae"][B0], (.15 + .1 + 0) / 3)
        self.assertEqual(result["coverage"]["full_population"]["population_games"], 6)
        self.assertEqual(result["coverage"]["checks"]["scorable_games"], 3)
        self.assertEqual(result["coverage"]["checks"]["zero_label_games"], ["d", "e"])
        dates = {x["game_date"]: x for x in result["per_date"]}
        self.assertAlmostEqual(dates["2025-11-01"]["equal_game_mse"][B0], .0175)
        self.assertAlmostEqual(result["equal_game_mse"]["candidate"], (.0194 + .0144 + .0004) / 3)

    def test_cluster_multiplicity_preserves_game_estimand(self):
        pair = self.result()["paired"][f"candidate_minus_{B0}"]
        self.assertAlmostEqual(pair["equal_game_mse_delta"], (-.0056 + .0044 + .0004) / 3)
        lo, hi = pair["week_block_95pct_interval"]
        self.assertAlmostEqual(lo, -.0006)
        self.assertAlmostEqual(hi, .0004)
        self.assertEqual(pair["week_block_95pct_interval"], pair["date_block_95pct_sensitivity"])

    def test_constant_correlation_is_null_and_primary_only(self):
        result = self.result()
        self.assertIsNone(result["equal_game_weighted_pearson"][B0])
        self.assertIsNone(result["equal_game_weighted_pearson"]["candidate"])
        self.assertEqual(result["primary_best_model"], "candidate")

    def test_weighted_correlation(self):
        for r in self.rows:
            if r["row_id"] in self.predictions["candidate"]:
                self.predictions["candidate"][r["row_id"]] = r["label"] or 0
        result = self.result()
        self.assertAlmostEqual(result["equal_game_weighted_pearson"]["candidate"], 1)
        self.assertEqual(result["equal_game_mse"]["candidate"], 0)

    def test_missing_prediction_for_unlabelled_is_failure(self):
        del self.predictions["candidate"]["missing"]
        with self.assertRaisesRegex(ValueError, "every forecastable"):
            self.result()

    def test_extra_fit_or_unforecastable_prediction_is_failure(self):
        self.predictions["candidate"]["fit"] = 0
        with self.assertRaises(ValueError):
            self.result()

    def test_nonfinite_predictions_never_change_mask(self):
        for bad in (math.nan, math.inf, True):
            self.predictions["candidate"]["missing"] = bad
            with self.assertRaises(ValueError):
                self.result()

    def test_nonfinite_label_or_current_is_failure(self):
        for field in ("label", "p_current"):
            rows = copy.deepcopy(self.rows)
            rows[0][field] = math.nan
            with self.assertRaises(ValueError):
                score(rows, self.predictions, draws=200)

    def test_zero_baseline_required_and_no_clipping(self):
        self.predictions[B0]["a1"] = .01
        with self.assertRaisesRegex(ValueError, "zero price"):
            self.result()
        self.predictions[B0]["a1"] = 0
        self.predictions["candidate"]["a1"] = 2
        self.assertGreater(self.result()["equal_game_mse"]["candidate"], .5)
        self.assertEqual(self.result()["prediction_diagnostics"]["candidate"]["implied_price_out_of_range_forecasts"], 1)

    def test_finite_prediction_with_overflowing_error_invalidates(self):
        self.predictions["candidate"]["a1"] = 1e308
        with self.assertRaisesRegex(ValueError, "squared prediction error"):
            self.result()

    def test_duplicate_and_game_identity_fail_closed(self):
        rows = self.rows + [copy.deepcopy(self.rows[0])]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            score(rows, self.predictions, draws=200)
        rows = copy.deepcopy(self.rows)
        rows[1]["game_week"] = "11"
        with self.assertRaisesRegex(ValueError, "game spans"):
            score(rows, self.predictions, draws=200)

    def test_fold_order_cannot_go_backward(self):
        rows = copy.deepcopy(self.rows)
        rows[3]["fold"] = "initial_fit"
        with self.assertRaisesRegex(ValueError, "chronological"):
            score(rows, self.predictions, draws=200)

    def test_single_week_no_false_precision(self):
        self.rows[3]["game_week"] = "09"
        result = self.result()
        self.assertIsNone(result["paired"][f"candidate_minus_{B0}"]["week_block_95pct_interval"])

    def test_deterministic_nonmutating(self):
        before = copy.deepcopy((self.rows, self.predictions))
        self.assertEqual(self.result(), self.result())
        self.assertEqual(before, (self.rows, self.predictions))


if __name__ == "__main__":
    unittest.main()
