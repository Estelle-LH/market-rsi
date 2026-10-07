from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning

from experiments import nfl_ingame_win_probability_train_diagnostic as ingame
from experiments import nfl_settlement_probability_train_diagnostic as settlement


class InGameWinProbabilityTrainDiagnosticTests(unittest.TestCase):
    def test_increment_rule_is_frozen_and_does_not_use_raw_market_gate(self) -> None:
        aggregate = {
            "raw_market": {"brier": 0.10, "log_loss": 0.30},
            "market_model": {"brier": 0.22, "log_loss": 0.64},
            "market_plus_state_model": {"brier": 0.20, "log_loss": 0.60},
        }
        folds = []
        for state, market in ((0.19, 0.20), (0.21, 0.22), (0.20, 0.21), (0.23, 0.22)):
            folds.append({"arms": {
                "market_model": {"brier": market},
                "market_plus_state_model": {"brier": state},
            }})
        decision, conditions = ingame.increment_decision(aggregate, folds)
        self.assertEqual(decision, "PBP_INCREMENT_SUPPORTED")
        self.assertEqual(conditions["fold_brier_wins"], [True, True, True, False])
        # The raw market remains a required comparison arm, but it cannot
        # change the isolated state-vs-market-model information test.
        aggregate["raw_market"] = {"brier": 0.99, "log_loss": 2.0}
        self.assertEqual(ingame.increment_decision(aggregate, folds)[0], decision)

    def test_group_resample_recomputes_equal_event_metric(self) -> None:
        records = [
            {"game_date": "a", "delta": 1.0},
            {"game_date": "a", "delta": 3.0},
            {"game_date": "b", "delta": 5.0},
        ]
        report = ingame._group_bootstrap(
            records, "game_date", "delta", replicates=100
        )
        self.assertEqual(report["groups"], 2)
        self.assertEqual(report["events"], 3)
        self.assertEqual(report["point_equal_event_mean"], 3.0)
        self.assertIn("equal-event", report["resampling_rule"])

    def test_market_and_state_arms_use_same_model_class_and_fixed_features(self) -> None:
        self.assertEqual(ingame.MODEL_SPEC["class"], "sklearn.linear_model.LogisticRegression")
        self.assertEqual(len(set(ingame.STATE_FEATURE_NAMES)), len(ingame.STATE_FEATURE_NAMES))
        forbidden = {"result", "home_score", "away_score", "terminal_score", "scoring_play"}
        self.assertFalse(forbidden.intersection(ingame.STATE_FEATURE_NAMES))
        self.assertEqual(ingame.MAX_TRADE_STALENESS_SECONDS, 300)
        vector = ingame._state_feature_vector({
            "home_score_diff_pre": "-3", "regulation_seconds_remaining": "1370",
            "possession_is_home": "1", "down": "3", "yards_to_go": "7",
            "home_possession_field_advantage": "0.4",
        })
        self.assertEqual(vector[3:7], (0.0, 0.0, 1.0, 0.0))

    def test_r_extractor_uses_order_sequence_and_omits_target_fields(self) -> None:
        source = ingame.EXTRACTOR.read_text(encoding="utf-8")
        self.assertIn("orderSequence", source)
        self.assertIn("completed_order < decision_order", source)
        self.assertIn("anyDuplicated(numeric_order[causal_identity])", source)
        self.assertIn("anyDuplicated(play_ids)", source)
        self.assertNotIn("homePointsTotal", source)
        self.assertNotIn("visitorPointsTotal", source)
        self.assertNotIn("playDescription[[selected]]", source)
        self.assertNotIn("scoringPlay[[selected]]", source)

    def test_same_second_trade_and_staleness_edges_fail_closed(self) -> None:
        trades = [
            {"timestamp": 99, "size": 1.0, "home_probability": 0.2},
            {"timestamp": 100, "size": 1.0, "home_probability": 0.4},
            {"timestamp": 101, "size": 1.0, "home_probability": 0.9},
        ]
        # For an event in integer second 101, the runner passes cutoff 100;
        # the same event-second print at 101 is not eligible.
        probability, latest_ms = ingame._market_snapshot(trades, 100)
        self.assertEqual(probability, 0.4)
        self.assertEqual(latest_ms, 100_000)
        exact = datetime.fromtimestamp(400, timezone.utc)
        self.assertEqual(ingame._staleness_seconds(exact, 100_000), 300.0)
        with self.assertRaisesRegex(settlement.EventExclusion, "300.001"):
            ingame._staleness_seconds(
                datetime.fromtimestamp(400.001, timezone.utc), 100_000
            )

    def test_only_continuous_columns_are_scaled(self) -> None:
        fit = np.asarray([
            [0.1, -3, 1400, 1, 1, 0, 0, 0, 7, 0.4],
            [0.3, 7, 1200, 0, 0, 1, 0, 0, 4, -0.2],
        ], dtype=float)
        check = np.asarray([[0.2, 1, 1300, 1, 0, 0, 1, 0, 8, 0.1]], dtype=float)
        transformed_fit, transformed_check = ingame._scale_continuous(
            fit, check, ingame.COMBINED_CONTINUOUS_INDICES
        )
        np.testing.assert_array_equal(transformed_fit[:, 3:8], fit[:, 3:8])
        np.testing.assert_array_equal(transformed_check[:, 3:8], check[:, 3:8])

    def test_convergence_warning_is_terminal(self) -> None:
        class WarningModel:
            def fit(self, matrix, outcomes):
                warnings.warn("did not converge", ConvergenceWarning)

        with mock.patch.object(ingame, "LogisticRegression", return_value=WarningModel()):
            with self.assertRaises(ConvergenceWarning):
                ingame._fit_logistic(np.ones((4, 1)), np.asarray([0, 1, 0, 1]))

    def test_fit_predict_preserves_one_row_per_game_and_same_masks(self) -> None:
        start = date(2025, 1, 1)
        dates = [(start + timedelta(days=index)).isoformat() for index in range(42)]
        rows = []
        for index, split_date in enumerate(dates):
            cutoff_ms = (index + 1) * 1_000_000
            probability = 0.25 + 0.5 * ((index % 7) / 6)
            market = tuple(
                probability + feature * 0.001 + (index % 3) * 0.0001
                for feature in range(len(ingame.MARKET_FEATURE_NAMES))
            )
            state = tuple(
                ((index + feature) % 11) / 10
                for feature in range(len(ingame.STATE_FEATURE_NAMES))
            )
            trusted = {
                "event_id": f"event-{index}",
                "market_id": f"market-{index}",
                "cutoff_ms": cutoff_ms,
                "feature_available_ms": cutoff_ms,
                "market_probability": probability,
                "outcome_available_ms": cutoff_ms + 1,
                "outcome": index % 2,
            }
            rows.append(ingame.InGameRow(
                game_id=f"2025_{index + 1:02d}_A_B",
                game_date=split_date,
                game_week=f"{index + 1:02d}",
                trusted=trusted,
                market_features=market,
                state_features=state,
                source_receipt={},
            ))
        folds = settlement.chronological_date_folds(dates)
        predictions, reports = ingame._fit_and_predict(rows, folds)
        self.assertEqual(len(predictions), 20)
        self.assertEqual(len(reports), 4)
        self.assertEqual(len({item["row"].game_id for item in predictions}), 20)
        self.assertTrue(all(report["same_rows_labels_trainer_and_budget"] for report in reports))
        self.assertTrue(all(
            "fit_label_unavailable_game_ids_sha256" in report for report in reports
        ))

        # A prior-date label unavailable at the first check cutoff is omitted
        # and explicitly named rather than silently entering the fit.
        rows[0].trusted["outcome_available_ms"] = rows[22].trusted["cutoff_ms"]
        _, unavailable_reports = ingame._fit_and_predict(rows, folds)
        self.assertEqual(
            unavailable_reports[0]["fit_label_unavailable_game_ids"],
            [rows[0].game_id],
        )

    def test_actual_opened_train_preflight_has_exact_attrition_and_prior_score(self) -> None:
        if not ingame.SOURCE_ROOT.is_dir():
            self.skipTest("opened Train source is not present")
        cohort = ingame._validate_source(
            ingame.SOURCE_ROOT, expected_events=195, expected_dates=42,
            allow_test_paths=False,
        )
        self.assertEqual(len(ingame._validate_pbp_receipts(ingame.SOURCE_ROOT, cohort)), 195)
        with tempfile.TemporaryDirectory() as directory:
            states = ingame._extract_state_rows(
                ingame.SOURCE_ROOT, Path(directory) / "states.csv"
            )
            # This anchor is itself a BUF touchdown.  The emitted -14 is the
            # strictly prior 13-27 score, not the current play's 19-27 state.
            self.assertEqual(states["2025_01_BAL_BUF"]["play_id"], "2394")
            self.assertEqual(float(states["2025_01_BAL_BUF"]["home_score_diff_pre"]), -14.0)
            materialized, excluded = [], []
            for item in cohort:
                try:
                    materialized.append(ingame._load_dynamic_market(
                        ingame.SOURCE_ROOT, item, states[item["game_id"]]
                    ))
                except settlement.EventExclusion as error:
                    excluded.append((item["game_id"], error.code))
        self.assertEqual(len(materialized), 193)
        self.assertEqual(excluded, [
            ("2025_04_GB_DAL", "unresolved_outcome"),
            ("2025_05_TEN_ARI", "market_trade_too_stale"),
        ])

    def test_persistent_path_guard_rejects_temporary_and_cloud_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            with self.assertRaisesRegex(ValueError, "persistent"):
                ingame._validate_roots(ingame.SOURCE_ROOT, temporary / "new", allow_test_paths=False)
        cloud = ingame.PERSISTENT_ARTIFACT_ROOT / "Google Drive" / "new"
        with self.assertRaisesRegex(ValueError, "cloud"):
            ingame._validate_roots(ingame.SOURCE_ROOT, cloud, allow_test_paths=False)


if __name__ == "__main__":
    unittest.main()
