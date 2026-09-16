import copy
import tempfile
import unittest
from pathlib import Path

from polymarket_scoring import (PolymarketScoreContract, persistence_predictions,
                                score_contract_from_objective, score_polymarket)
from objective_contract import build_objective_contract


DAY_MS = 86_400_000


def row(index, *, game="game-a", day=1, midpoint=.5, target=.6):
    decision = day * DAY_MS + index * 1_000
    return {"row_id": f"row-{day}-{index}-{game}", "game_id": game,
            "market_id": f"market-{game}", "decision_ms": decision,
            "target_ms": decision + 60_000, "midpoint": midpoint,
            "target_midpoint": target}


def dev_contract():
    return PolymarketScoreContract(split="dev", evidence_class="synthetic")


def ok(rows, predictions):
    return [{"row_id": item["row_id"], "status": "ok", "prediction": prediction}
            for item, prediction in zip(rows, predictions, strict=True)]


class PolymarketScoringTests(unittest.TestCase):
    def test_persistence_is_current_midpoint_and_candidate_improvement(self):
        rows = [row(0, target=.6), row(1, target=.4)]
        self.assertEqual(persistence_predictions(rows, dev_contract()),
                         {rows[0]["row_id"]: .5, rows[1]["row_id"]: .5})
        result = score_polymarket(rows, ok(rows, [.6, .4]), dev_contract())
        self.assertTrue(result["primary"]["valid"])
        self.assertAlmostEqual(result["primary"]["baseline_all_rows_mse"], .01)
        self.assertEqual(result["primary"]["candidate_all_rows_mse"], 0)
        self.assertAlmostEqual(result["primary"]["relative_mse_improvement"], 1)
        self.assertAlmostEqual(
            result["primary"]["normalized_skill_score_vs_persistence"], 1)
        self.assertAlmostEqual(
            result["primary"]["baseline_rmse_probability_bps"], 1000)
        self.assertEqual(result["primary"]["candidate_rmse_probability_bps"], 0)
        self.assertEqual(result["primary"]["metric"], "equal_game_mse")
        difficulty = result["target_difficulty_diagnostic"]
        self.assertEqual(difficulty["moving_rows"], 2)
        self.assertEqual(difficulty["unchanged_rows"], 0)
        self.assertFalse(difficulty["selection_eligible"])

    def test_easy_target_is_visible_without_changing_primary_metric(self):
        rows = [row(0, midpoint=.5, target=.5),
                row(1, midpoint=.5, target=.5),
                row(2, midpoint=.5, target=.51)]
        result = score_polymarket(rows, ok(rows, [.5, .5, .51]), dev_contract())
        difficulty = result["target_difficulty_diagnostic"]
        self.assertEqual(difficulty["moving_rows"], 1)
        self.assertEqual(difficulty["unchanged_rows"], 2)
        self.assertAlmostEqual(difficulty["moving_fraction"], 1 / 3)
        self.assertAlmostEqual(
            difficulty["median_nonzero_absolute_move_probability_bps"], 100)
        self.assertEqual(result["primary"]["metric"], "equal_game_mse")

    def test_games_receive_equal_weight_not_rows(self):
        rows = [row(0, game="dense", target=.6), row(1, game="dense", target=.6),
                row(2, game="dense", target=.6), row(3, game="sparse", target=.9)]
        # Dense game MSE=.01, sparse game MSE=.16; equal-game mean=.085.
        result = score_polymarket(rows, ok(rows, [.6, .6, .6, .9]), dev_contract())
        self.assertAlmostEqual(result["primary"]["baseline_all_rows_mse"], .085)
        self.assertEqual(result["population"]["games"], 2)

    def test_temporal_robustness_reports_whole_game_days(self):
        rows = [row(0, game="early", day=1, target=.6),
                row(0, game="late", day=2, target=.6)]
        result = score_polymarket(rows, ok(rows, [.6, .55]), dev_contract())
        robust = result["temporal_robustness"]
        self.assertTrue(robust["valid"])
        self.assertEqual(robust["comparable_days"], 2)
        self.assertEqual(robust["improved_days"], 2)
        self.assertEqual(robust["worse_days"], 0)
        self.assertAlmostEqual(robust["worst_relative_mse_improvement"], .75)
        self.assertAlmostEqual(robust["median_relative_mse_improvement"], .875)

    def test_missing_is_not_zero_or_silently_dropped(self):
        rows = [row(0, target=.6), row(1, target=.4)]
        result = score_polymarket(rows, ok(rows[:1], [.6]), dev_contract())
        self.assertFalse(result["primary"]["valid"])
        self.assertIsNone(result["primary"]["candidate_all_rows_mse"])
        self.assertEqual(result["coverage"]["missing_rows"], 1)
        self.assertEqual(result["coverage"]["coverage_fraction"], .5)
        self.assertEqual(result["paired_success_diagnostic"]["rows"], 1)
        self.assertTrue(result["paired_success_diagnostic"]["same_mask"])
        self.assertIn({"row_id": rows[1]["row_id"], "game_id": "game-a", "status": "missing"},
                      result["row_outcomes"])

    def test_temporal_robustness_is_invalid_when_a_whole_game_is_missing(self):
        rows = [row(0, game="seen", day=1), row(0, game="missing", day=2)]
        result = score_polymarket(rows, ok(rows[:1], [.6]), dev_contract())
        robust = result["temporal_robustness"]
        self.assertFalse(robust["valid"])
        self.assertIsNone(robust["days"]["1970-01-03"]["candidate_equal_game_mse"])
        self.assertIsNone(robust["median_relative_mse_improvement"])

    def test_failure_is_retained_with_reason_and_invalidates_primary(self):
        rows = [row(0), row(1)]
        submissions = [{"row_id": rows[0]["row_id"], "status": "ok", "prediction": .6},
                       {"row_id": rows[1]["row_id"], "status": "failed", "failure_code": "timeout"}]
        result = score_polymarket(rows, submissions, dev_contract())
        self.assertFalse(result["primary"]["valid"])
        self.assertEqual(result["coverage"]["failed_rows"], 1)
        self.assertEqual(result["coverage"]["failure_codes"], {"timeout": 1})
        self.assertEqual(result["per_game"]["game-a"]["failed_rows"], 1)

    def test_paired_metrics_use_exact_success_rows_for_both_arms(self):
        rows = [row(0, target=.6), row(1, target=.9)]
        submissions = [{"row_id": rows[0]["row_id"], "status": "ok", "prediction": .6},
                       {"row_id": rows[1]["row_id"], "status": "failed", "failure_code": "bad_output"}]
        result = score_polymarket(rows, submissions, dev_contract())
        paired = result["paired_success_diagnostic"]
        self.assertEqual(paired["rows"], 1)
        self.assertAlmostEqual(paired["baseline_equal_game_mse"], .01)
        self.assertEqual(paired["candidate_equal_game_mse"], 0)
        # Full baseline retains the hard failed row; it is not the paired denominator.
        self.assertAlmostEqual(result["primary"]["baseline_all_rows_mse"], .085)

    def test_calibration_is_auxiliary_and_constant_forecast_is_undefined(self):
        rows = [row(0, midpoint=.4, target=.3), row(1, midpoint=.5, target=.5),
                row(2, midpoint=.6, target=.7)]
        result = score_polymarket(rows, ok(rows, [.4, .5, .6]), dev_contract())
        metrics = result["calibration_auxiliary"]["candidate_on_paired_success"]
        self.assertAlmostEqual(metrics["calibration_slope"], 2)
        self.assertAlmostEqual(metrics["calibration_intercept"], -.5)
        constant = score_polymarket(rows, ok(rows, [.5, .5, .5]), dev_contract())
        self.assertIsNone(constant["calibration_auxiliary"]["candidate_on_paired_success"]["calibration_slope"])

    def test_bad_horizon_order_values_and_submission_identity_fail_closed(self):
        original = [row(0), row(1)]
        mutations = []
        bad = copy.deepcopy(original); bad[0]["target_ms"] += 1; mutations.append(bad)
        bad = copy.deepcopy(original); bad[0]["midpoint"] = None; mutations.append(bad)
        bad = list(reversed(copy.deepcopy(original))); mutations.append(bad)
        for bad in mutations:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                score_polymarket(bad, [], dev_contract())
        with self.assertRaises(ValueError):
            score_polymarket(original, [{"row_id": "extra", "status": "ok", "prediction": .5}],
                               dev_contract())
        with self.assertRaises(ValueError):
            score_polymarket(original, ok(original, [.5, float("nan")]), dev_contract())

    def test_test_requires_commitment_untouched_twenty_games_and_one_gate(self):
        rows = [row(0, day=index + 1, game=f"game-{index}") for index in range(20)]
        import polymarket_scoring
        commitment = polymarket_scoring._digest(rows)
        contract = PolymarketScoreContract(split="test", evidence_class="untouched",
                                            test_commitment_sha256=commitment)
        with tempfile.TemporaryDirectory() as directory:
            gate = Path(directory) / "test-gate"
            result = score_polymarket(rows, ok(rows, [.6] * 20), contract, test_gate_dir=gate)
            self.assertTrue(result["test_policy"]["opened_once"])
            self.assertEqual(result["population"]["games"], 20)
            self.assertEqual(result["population"]["utc_days"], 20)
            self.assertTrue((gate / "opening.json").is_file())
            self.assertTrue((gate / "result.json").is_file())
            with self.assertRaises(FileExistsError):
                score_polymarket(rows, ok(rows, [.6] * 20), contract, test_gate_dir=gate)

    def test_failed_test_attempt_is_still_consumed(self):
        rows = [row(0, day=index + 1, game=f"game-{index}") for index in range(20)]
        import polymarket_scoring
        contract = PolymarketScoreContract(split="test", evidence_class="untouched",
                                            test_commitment_sha256=polymarket_scoring._digest(rows))
        bad_rows = copy.deepcopy(rows)
        bad_rows[0]["target_ms"] += 1
        with tempfile.TemporaryDirectory() as directory:
            gate = Path(directory) / "test-gate"
            with self.assertRaises(ValueError):
                score_polymarket(bad_rows, ok(rows, [.5] * 20), contract, test_gate_dir=gate)
            self.assertTrue((gate / "failure.json").is_file())
            with self.assertRaises(FileExistsError):
                score_polymarket(rows, ok(rows, [.5] * 20), contract, test_gate_dir=gate)

    def test_test_contract_rejects_diagnostic_short_or_uncommitted_use(self):
        with self.assertRaises(ValueError):
            PolymarketScoreContract(split="test", evidence_class="diagnostic",
                                    test_commitment_sha256="a" * 64)
        with self.assertRaises(ValueError):
            PolymarketScoreContract(split="dev", evidence_class="synthetic",
                                    test_commitment_sha256="a" * 64)
        short = [row(0)]
        import polymarket_scoring
        contract = PolymarketScoreContract(split="test", evidence_class="untouched",
                                            test_commitment_sha256=polymarket_scoring._digest(short))
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            score_polymarket(short, ok(short, [.5]), contract,
                               test_gate_dir=Path(directory) / "test-gate")

    def test_twenty_days_do_not_replace_twenty_independent_games(self):
        rows = [row(0, day=day, game="same-game") for day in range(1, 21)]
        import polymarket_scoring
        contract = PolymarketScoreContract(split="test", evidence_class="untouched",
                                            test_commitment_sha256=polymarket_scoring._digest(rows))
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "20 distinct"):
            score_polymarket(rows, ok(rows, [.5] * 20), contract,
                               test_gate_dir=Path(directory) / "test-gate")

    def test_twenty_games_on_one_day_do_not_replace_temporal_coverage(self):
        rows = [row(index, day=1, game=f"game-{index}") for index in range(20)]
        import polymarket_scoring
        contract = PolymarketScoreContract(
            split="test", evidence_class="untouched",
            test_commitment_sha256=polymarket_scoring._digest(rows),
        )
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(
                ValueError, "20 untouched UTC dates"):
            score_polymarket(rows, ok(rows, [.5] * 20), contract,
                             test_gate_dir=Path(directory) / "test-gate")

    def test_custom_objective_binds_window_and_label_availability(self):
        objective = build_objective_contract(
            experiment_id="experiment",
            objective_id="future-midpoint-window-mean-270-330s-v1",
            train_diagnostics_sha256="a" * 64,
            literature_snapshot_sha256="b" * 64,
            literature_ids=[], evidence_class="formal_learning",
        )
        contract = score_contract_from_objective(
            objective, split="dev", evidence_class="formal_learning"
        )
        self.assertEqual(contract.horizon_ms, 330_000)
        value = row(0)
        value["target_ms"] = value["decision_ms"] + 330_000
        result = score_polymarket([value], ok([value], [.6]), contract)
        self.assertEqual(result["target"]["objective_id"], objective["objective_id"])
        self.assertEqual(result["target"]["aggregation"], "uniform_mean")
        self.assertEqual(result["target"]["label_available_after_ms"], 330_000)


if __name__ == "__main__":
    unittest.main()
