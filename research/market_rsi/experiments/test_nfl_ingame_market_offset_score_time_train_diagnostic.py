from __future__ import annotations

from datetime import date, timedelta
import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np

from experiments import nfl_ingame_market_offset_score_time_train_diagnostic as candidate
from experiments import nfl_ingame_win_probability_train_diagnostic as base
from experiments import nfl_settlement_probability_train_diagnostic as settlement


class InGameMarketOffsetScoreTimeTests(unittest.TestCase):
    def test_analytic_gradient_matches_central_difference_and_sum_nll(self) -> None:
        features = np.asarray([[0.2, -0.5], [1.0, 0.3], [-0.7, 1.2]], dtype=float)
        outcomes = np.asarray([0, 1, 1], dtype=float)
        offsets = np.asarray([-0.4, 0.7, 0.1], dtype=float)
        theta = np.asarray([0.15, -0.2, 0.35], dtype=float)
        value, gradient = candidate.offset_objective_gradient(
            theta, features, outcomes, offsets
        )
        linear = offsets + theta[0] + features @ theta[1:]
        expected = np.sum(np.logaddexp(0, linear) - outcomes * linear)
        expected += 0.5 * np.dot(theta[1:], theta[1:])
        self.assertAlmostEqual(value, float(expected), places=12)
        numerical = []
        epsilon = 1e-6
        for index in range(len(theta)):
            upper, lower = theta.copy(), theta.copy()
            upper[index] += epsilon
            lower[index] -= epsilon
            high = candidate.offset_objective_gradient(
                upper, features, outcomes, offsets
            )[0]
            low = candidate.offset_objective_gradient(
                lower, features, outcomes, offsets
            )[0]
            numerical.append((high - low) / (2 * epsilon))
        np.testing.assert_allclose(gradient, numerical, rtol=1e-6, atol=1e-7)

    def test_intercept_is_excluded_from_penalty(self) -> None:
        features = np.empty((2, 0), dtype=float)
        outcomes = np.asarray([0, 1], dtype=float)
        offsets = np.asarray([-0.2, 0.3], dtype=float)
        theta = np.asarray([3.5], dtype=float)
        unpenalized = candidate.offset_objective_gradient(
            theta, features, outcomes, offsets, penalty_lambda=0
        )
        nominal = candidate.offset_objective_gradient(
            theta, features, outcomes, offsets, penalty_lambda=99
        )
        self.assertEqual(unpenalized[0], nominal[0])
        np.testing.assert_array_equal(unpenalized[1], nominal[1])

    def test_market_logit_coefficient_is_fixed_at_one(self) -> None:
        offsets = np.asarray([-2.0, 0.0, 2.0])
        features = np.empty((3, 0), dtype=float)
        probabilities = candidate.offset_probabilities(
            np.asarray([0.0]), features, offsets
        )
        np.testing.assert_allclose(probabilities, 1 / (1 + np.exp(-offsets)))
        self.assertEqual(candidate.SOLVER_SPEC["market_logit_coefficient"], 1.0)
        self.assertFalse(candidate.SOLVER_SPEC["intercept_penalized"])
        self.assertEqual(candidate.SOLVER_SPEC["retry_count"], 0)

    def test_score_time_uses_only_pre_anchor_score_and_time(self) -> None:
        row = self._row(0, "2025-01-01", probability=0.4)
        state = list(row.state_features)
        state[0], state[1] = -7.0, 1200.0
        row = base.InGameRow(
            game_id=row.game_id, game_date=row.game_date, game_week=row.game_week,
            trusted=row.trusted, market_features=row.market_features,
            state_features=tuple(state), source_receipt=row.source_receipt,
        )
        self.assertAlmostEqual(
            candidate._score_time_ratio_k4(row),
            -7 * math.exp(4 * (1 - 1200 / 3600)),
        )
        self.assertNotIn("result", candidate.SCORE_TIME_FEATURE_NAMES)
        self.assertNotIn("terminal_score", candidate.SCORE_TIME_FEATURE_NAMES)

    def test_scaler_is_fit_fold_only_and_binary_columns_are_unchanged(self) -> None:
        fit = np.asarray([
            [-1, 1200, 0, 1, 0, 0, 0, 5, -0.2],
            [3, 1400, 1, 0, 1, 0, 0, 9, 0.4],
        ], dtype=float)
        check = np.asarray([[101, 1300, 1, 0, 0, 1, 0, 7, 0.1]], dtype=float)
        scaled_fit, scaled_check, report = candidate._scale_fold(
            fit, check, candidate.ARM_LINEAR
        )
        np.testing.assert_array_equal(scaled_fit[:, 2:7], fit[:, 2:7])
        np.testing.assert_array_equal(scaled_check[:, 2:7], check[:, 2:7])
        self.assertEqual(report["means"][0], 1.0)
        self.assertAlmostEqual(scaled_check[0, 0], 50.0)
        self.assertTrue(report["fit_only"])

    def test_three_arms_four_folds_produce_exactly_twelve_fits_and_same_masks(self) -> None:
        start = date(2025, 1, 1)
        dates = [(start + timedelta(days=index)).isoformat() for index in range(42)]
        rows = [self._row(index, split_date) for index, split_date in enumerate(dates)]
        folds = settlement.chronological_date_folds(dates)
        calls = 0
        original = candidate.fit_offset_arm

        def counted(*args, **kwargs):
            nonlocal calls
            calls += 1
            return original(*args, **kwargs)

        with mock.patch.object(candidate, "fit_offset_arm", side_effect=counted):
            predictions, reports = candidate._fit_and_predict(rows, folds)
        self.assertEqual(calls, 12)
        self.assertEqual(len(reports), 4)
        self.assertEqual(len(predictions), 20)
        self.assertEqual(len({item["row"].key for item in predictions}), 20)
        self.assertTrue(all(
            report["same_rows_labels_offsets_trainer_and_budget"] for report in reports
        ))
        self.assertTrue(all(
            set(report["optimizer_reports"]) == set(candidate.OFFSET_ARMS)
            for report in reports
        ))

    def test_decision_rule_has_support_refute_and_inconclusive_routes(self) -> None:
        folds = [
            {"arms": {
                candidate.ARM_LINEAR: {"brier": linear},
                candidate.ARM_SCORE_TIME: {"brier": nonlinear},
            }}
            for nonlinear, linear in ((.18, .20), (.19, .20), (.17, .20), (.21, .20))
        ]
        aggregate = {
            "raw_market": {"brier": .195, "log_loss": .50},
            candidate.ARM_LINEAR: {"brier": .20, "log_loss": .52},
            candidate.ARM_SCORE_TIME: {"brier": .19, "log_loss": .49},
        }
        self.assertEqual(candidate.score_time_decision(aggregate, folds)[0],
                         "LINEAR_REPRESENTATION_FAILURE_SUPPORTED")
        aggregate[candidate.ARM_SCORE_TIME] = {"brier": .198, "log_loss": .51}
        self.assertEqual(candidate.score_time_decision(aggregate, folds)[0],
                         "SCORE_TIME_K4_NARROWING_INCONCLUSIVE")
        folds[-2]["arms"][candidate.ARM_SCORE_TIME]["brier"] = .22
        self.assertEqual(candidate.score_time_decision(aggregate, folds)[0],
                         "SCORE_TIME_K4_HYPOTHESIS_REFUTED")

    def test_frozen_parent_artifact_and_dependency_hashes_pass(self) -> None:
        if not candidate.V0_ARTIFACT_ROOT.is_dir():
            self.skipTest("frozen v0 artifact is not present")
        candidate._validate_frozen_dependencies()
        result = candidate._validate_v0_artifact()
        self.assertEqual(result["manifest"]["check_events"], 87)
        self.assertEqual(
            result["scorecard"]["identical_masks"]["check_key_sha256"],
            candidate.EXPECTED_CHECK_KEY_SHA256,
        )

    def test_actual_opened_train_reuses_exact_attrition_state_and_mask(self) -> None:
        if not candidate.SOURCE_ROOT.is_dir():
            self.skipTest("opened Train source is not present")
        cohort = base._validate_source(
            candidate.SOURCE_ROOT, expected_events=195, expected_dates=42,
            allow_test_paths=False,
        )
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "states.csv"
            states = base._extract_state_rows(candidate.SOURCE_ROOT, state_path)
            self.assertEqual(candidate._sha256(state_path),
                             candidate.EXPECTED_CHECKPOINT_STATE_SHA256)
            materialized, excluded = [], []
            for item in cohort:
                state = states[item["game_id"]]
                candidate._validate_extracted_score_time(state)
                try:
                    materialized.append(base._load_dynamic_market(
                        candidate.SOURCE_ROOT, item, state
                    ))
                except settlement.EventExclusion as error:
                    excluded.append((item["game_id"], error.code))
        self.assertEqual(len(materialized), 193)
        self.assertEqual(excluded, [
            ("2025_04_GB_DAL", "unresolved_outcome"),
            ("2025_05_TEN_ARI", "market_trade_too_stale"),
        ])
        folds = settlement.chronological_date_folds(
            [item["game_date"] for item in cohort]
        )
        by_date = {split_date: [] for split_date in {row.game_date for row in materialized}}
        for row in materialized:
            by_date[row.game_date].append(row)
        check = sorted(
            [row for fold in folds for split_date in fold["check_dates"]
             for row in by_date.get(split_date, [])], key=lambda row: row.key,
        )
        self.assertEqual(len(check), 87)
        self.assertEqual(
            settlement._digest([list(row.key) for row in check]),
            candidate.EXPECTED_CHECK_KEY_SHA256,
        )
        self.assertEqual(
            settlement._digest([list(row.key) for row in sorted(
                materialized, key=lambda row: row.key
            )]),
            candidate.EXPECTED_MATERIALIZED_KEY_SHA256,
        )
        fit_counts = []
        unavailable = []
        for fold in folds:
            check_rows = [row for split_date in fold["check_dates"]
                          for row in by_date.get(split_date, [])]
            first_check_cutoff = min(row.trusted["cutoff_ms"] for row in check_rows)
            fit_candidates = [row for split_date in fold["fit_dates"]
                              for row in by_date.get(split_date, [])]
            fit_counts.append(sum(
                row.trusted["outcome_available_ms"] < first_check_cutoff
                for row in fit_candidates
            ))
            unavailable.append(sum(
                row.trusted["outcome_available_ms"] >= first_check_cutoff
                for row in fit_candidates
            ))
        self.assertEqual(tuple(fit_counts), candidate.EXPECTED_FIT_EVENTS)
        self.assertEqual(unavailable, [0, 0, 0, 0])

    def test_persistent_output_guard_remains_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "persistent"):
                base._validate_roots(
                    candidate.SOURCE_ROOT, Path(directory) / "new",
                    allow_test_paths=False,
                )
        with self.assertRaisesRegex(ValueError, "cloud"):
            base._validate_roots(
                candidate.SOURCE_ROOT,
                candidate.PERSISTENT_ARTIFACT_ROOT / "Dropbox" / "new",
                allow_test_paths=False,
            )

    @staticmethod
    def _row(index: int, split_date: str, probability: float | None = None) -> base.InGameRow:
        probability = probability if probability is not None else 0.25 + 0.5 * ((index % 7) / 6)
        cutoff_ms = (index + 1) * 1_000_000
        down = index % 4
        state = (
            float((index % 13) - 6), 1200.0 + (index % 10) * 10,
            float(index % 2),
            *(1.0 if down == value else 0.0 for value in range(4)),
            float(1 + index % 10), -0.5 + (index % 11) / 10,
        )
        trusted = {
            "event_id": f"event-{index}", "market_id": f"market-{index}",
            "cutoff_ms": cutoff_ms, "feature_available_ms": cutoff_ms,
            "market_probability": probability,
            "outcome_available_ms": cutoff_ms + 1, "outcome": index % 2,
        }
        return base.InGameRow(
            game_id=f"2025_{index + 1:02d}_A_B", game_date=split_date,
            game_week=f"{index % 14 + 1:02d}", trusted=trusted,
            market_features=(math.log(probability / (1 - probability)),),
            state_features=state, source_receipt={},
        )


if __name__ == "__main__":
    unittest.main()
