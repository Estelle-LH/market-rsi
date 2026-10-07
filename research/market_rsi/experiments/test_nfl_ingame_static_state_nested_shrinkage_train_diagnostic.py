from __future__ import annotations

from datetime import date, timedelta
import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np

from experiments import nfl_ingame_static_state_nested_shrinkage_train_diagnostic as candidate
from experiments import nfl_ingame_market_offset_score_time_train_diagnostic as linear
from experiments import nfl_ingame_win_probability_train_diagnostic as base
from experiments import nfl_settlement_probability_train_diagnostic as settlement


class InGameStaticStateNestedShrinkageTests(unittest.TestCase):
    def test_objective_gradient_lambda_and_unpenalized_intercept_are_exact(self) -> None:
        features = np.asarray([
            [0.2, -0.5], [1.0, 0.3], [-0.7, 1.2], [0.4, 0.8]
        ], dtype=float)
        outcomes = np.asarray([0, 1, 1, 0], dtype=float)
        offsets = np.asarray([-0.4, 0.7, 0.1, -0.2], dtype=float)
        theta = np.asarray([0.15, -0.2, 0.35], dtype=float)
        value, gradient = candidate.nested_objective_gradient(
            theta, features, outcomes, offsets, penalty_lambda=4.0
        )
        eta = offsets + theta[0] + features @ theta[1:]
        expected = np.sum(np.logaddexp(0.0, eta) - outcomes * eta)
        expected += 0.5 * 4.0 * float(theta[1:] @ theta[1:])
        self.assertAlmostEqual(value, float(expected), places=12)
        numerical = []
        epsilon = 1e-6
        for index in range(theta.size):
            upper, lower = theta.copy(), theta.copy()
            upper[index] += epsilon
            lower[index] -= epsilon
            high = candidate.nested_objective_gradient(
                upper, features, outcomes, offsets, penalty_lambda=4.0
            )[0]
            low = candidate.nested_objective_gradient(
                lower, features, outcomes, offsets, penalty_lambda=4.0
            )[0]
            numerical.append((high - low) / (2 * epsilon))
        np.testing.assert_allclose(gradient, numerical, rtol=1e-6, atol=1e-7)
        intercept_only = np.asarray([2.5])
        empty = np.empty((4, 0), dtype=float)
        low = linear.offset_objective_gradient(
            intercept_only, empty, outcomes, offsets, penalty_lambda=0.25
        )
        high = linear.offset_objective_gradient(
            intercept_only, empty, outcomes, offsets, penalty_lambda=64.0
        )
        self.assertEqual(low[0], high[0])
        np.testing.assert_array_equal(low[1], high[1])
        with self.assertRaisesRegex(ValueError, "frozen grid"):
            candidate.nested_objective_gradient(
                theta, features, outcomes, offsets, penalty_lambda=2.0
            )

    def test_inner_dates_are_last_six_as_three_strict_two_date_checks(self) -> None:
        dates = [f"2025-01-{index:02d}" for index in range(1, 23)]
        splits = candidate.inner_date_splits(dates)
        self.assertEqual([item["check_dates"] for item in splits], [
            ["2025-01-17", "2025-01-18"],
            ["2025-01-19", "2025-01-20"],
            ["2025-01-21", "2025-01-22"],
        ])
        self.assertEqual([len(item["fit_dates"]) for item in splits], [16, 18, 20])
        self.assertTrue(all(
            max(item["fit_dates"]) < min(item["check_dates"]) for item in splits
        ))
        with self.assertRaisesRegex(ValueError, "sorted, unique"):
            candidate.inner_date_splits(dates[:6])
        with self.assertRaisesRegex(ValueError, "sorted, unique"):
            candidate.inner_date_splits(list(reversed(dates)))

    def test_exact_ties_choose_largest_lambda_and_grid_drift_fails(self) -> None:
        self.assertEqual(candidate.select_lambda({
            0.25: 0.2, 1.0: 0.19, 4.0: 0.18, 16.0: 0.18, 64.0: 0.18,
        }), 64.0)
        self.assertEqual(candidate.select_lambda({
            0.25: 0.2, 1.0: 0.17, 4.0: 0.18, 16.0: 0.19, 64.0: 0.21,
        }), 1.0)
        with self.assertRaisesRegex(ValueError, "exact lambda grid"):
            candidate.select_lambda({0.25: 0.2})

    def test_scaling_is_applicable_fit_only_and_binary_columns_remain_raw(self) -> None:
        fit = np.asarray([
            [-1, 1200, 0, 1, 0, 0, 0, 5, -0.2],
            [3, 1400, 1, 0, 1, 0, 0, 9, 0.4],
        ], dtype=float)
        check = np.asarray([[101, 1300, 1, 0, 0, 1, 0, 7, 0.1]], dtype=float)
        scaled_fit, scaled_check, report = linear._scale_fold(
            fit, check, linear.ARM_LINEAR
        )
        np.testing.assert_array_equal(scaled_fit[:, 2:7], fit[:, 2:7])
        np.testing.assert_array_equal(scaled_check[:, 2:7], check[:, 2:7])
        self.assertEqual(report["means"][0], 1.0)
        self.assertAlmostEqual(scaled_check[0, 0], 50.0)
        changed = check.copy()
        changed[0, 0] = -999.0
        _, _, changed_report = linear._scale_fold(fit, changed, linear.ARM_LINEAR)
        self.assertEqual(report, changed_report)

    def test_exact_static_features_fixed_market_offset_and_fit_budget(self) -> None:
        self.assertEqual(candidate.FEATURE_NAMES, base.STATE_FEATURE_NAMES)
        self.assertEqual(candidate.CONTINUOUS_INDICES, (0, 1, 7, 8))
        self.assertNotIn("score_time_ratio_k4", candidate.FEATURE_NAMES)
        self.assertEqual(candidate.SOLVER_SPEC["market_logit_coefficient"], 1.0)
        self.assertFalse(candidate.SOLVER_SPEC["intercept_penalized"])
        self.assertEqual(candidate.SOLVER_SPEC["automatic_retries"], 0)
        self.assertEqual(
            len(candidate.LAMBDA_GRID) * candidate.INNER_SPLITS * 4 + 4,
            candidate.MAX_MODEL_FITS,
        )

    def test_nested_execution_is_exactly_64_candidate_fits_and_zero_control_refits(self) -> None:
        rows, folds, controls = self._synthetic_problem()
        calls = []
        original = candidate.fit_nested_offset

        def counted(*args, **kwargs):
            calls.append(float(kwargs["penalty_lambda"]))
            return original(*args, **kwargs)

        with mock.patch.object(candidate, "fit_nested_offset", side_effect=counted), \
                mock.patch.object(
                    linear, "fit_offset_arm",
                    side_effect=AssertionError("frozen control must not refit"),
                ):
            predictions, reports = candidate._fit_and_predict(rows, folds, controls)
        self.assertEqual(len(calls), 64)
        self.assertEqual(len(reports), 4)
        self.assertEqual(len(predictions), 20)
        self.assertEqual(len({item["row"].key for item in predictions}), 20)
        self.assertEqual(set(item["row"].key for item in predictions), set(controls))
        self.assertTrue(all(len(report["inner_splits"]) == 3 for report in reports))
        self.assertTrue(all(
            report["pooled_inner_events_per_lambda"] == 6 for report in reports
        ))
        self.assertTrue(all(
            report["selected_lambda"] in candidate.LAMBDA_GRID for report in reports
        ))
        self.assertTrue(all(
            inner["fit_label_unavailable_game_ids"] == []
            for report in reports for inner in report["inner_splits"]
        ))

    def test_future_or_unavailable_inner_labels_fail_closed(self) -> None:
        rows, folds, _ = self._synthetic_problem()
        first = rows[0]
        trusted = dict(first.trusted)
        trusted["outcome_available_ms"] = 10**15
        rows[0] = base.InGameRow(
            game_id=first.game_id, game_date=first.game_date,
            game_week=first.game_week, trusted=trusted,
            market_features=first.market_features, state_features=first.state_features,
            source_receipt=first.source_receipt,
        )
        by_date = {row.game_date: [row] for row in rows}
        check = [row for row in rows if row.game_date in folds[0]["check_dates"]]
        with self.assertRaisesRegex(ValueError, "not strictly available"):
            candidate._strict_prior_rows(by_date, folds[0]["fit_dates"], check)

    def test_decision_rule_support_refute_and_inconclusive_are_exact(self) -> None:
        def fold(candidate_brier: float, raw: float, control: float) -> dict:
            return {"arms": {
                candidate.ARM_CANDIDATE: {"brier": candidate_brier},
                candidate.ARM_RAW: {"brier": raw},
                candidate.ARM_CONTROL: {"brier": control},
            }}

        aggregate = {
            candidate.ARM_CANDIDATE: {"brier": .18, "log_loss": .48},
            candidate.ARM_RAW: {"brier": .20, "log_loss": .52},
            candidate.ARM_CONTROL: {"brier": .19, "log_loss": .50},
        }
        support_folds = [
            fold(.18, .20, .19), fold(.18, .20, .19),
            fold(.18, .20, .19), fold(.21, .20, .19),
        ]
        self.assertEqual(
            candidate.nested_shrinkage_decision(aggregate, support_folds)[0],
            "STATIC_STATE_NESTED_SHRINKAGE_SUPPORTED",
        )
        refuted = dict(aggregate)
        refuted[candidate.ARM_CANDIDATE] = {"brier": .201, "log_loss": .48}
        self.assertEqual(
            candidate.nested_shrinkage_decision(refuted, support_folds)[0],
            "STATIC_STATE_NESTED_SHRINKAGE_REFUTED",
        )
        inconclusive_folds = [
            fold(.18, .20, .19), fold(.18, .20, .19),
            fold(.21, .20, .22), fold(.21, .20, .22),
        ]
        self.assertEqual(
            candidate.nested_shrinkage_decision(aggregate, inconclusive_folds)[0],
            "STATIC_STATE_NESTED_SHRINKAGE_INCONCLUSIVE",
        )

    def test_paired_evidence_wires_complete_date_and_week_10k_bootstraps(self) -> None:
        records = []
        for index in range(4):
            record = {
                "game_id": f"game-{index}",
                "game_date": f"2025-01-{index + 1:02d}",
                "game_week": f"{index // 2 + 1:02d}",
            }
            for comparison in (
                "candidate_minus_raw_market",
                "candidate_minus_frozen_control",
                "frozen_control_minus_raw_market",
            ):
                for metric in ("brier", "log_loss"):
                    record[f"{comparison}_{metric}"] = (index - 1.5) / 100
            records.append(record)
        calls = []

        def fake_bootstrap(rows, group, value, *, seed, replicates):
            calls.append((group, value, seed, replicates, len(rows)))
            return {"group": group, "bootstrap_seed": seed,
                    "bootstrap_replicates": replicates}

        with mock.patch.object(base, "_group_bootstrap", side_effect=fake_bootstrap):
            result = candidate._paired_evidence(records)
        self.assertEqual(len(result), 3)
        self.assertEqual(len(calls), 12)
        self.assertEqual({item[0] for item in calls}, {"game_date", "game_week"})
        self.assertTrue(all(item[2] == 20260929 for item in calls))
        self.assertTrue(all(item[3] == 10_000 for item in calls))
        self.assertTrue(all(item[4] == 4 for item in calls))

    def test_frozen_control_and_controller_bindings_pass_without_training(self) -> None:
        candidate._validate_frozen_dependencies()
        control = candidate._validate_v1_control()
        self.assertEqual(len(control["rows_by_key"]), 87)
        self.assertEqual(
            control["manifest"]["predictions_sha256"],
            "f79a3f61a8bdcb71bcdf0f673bb87cfffe5a600a52ed523ec854978fa01fda54",
        )
        self.assertEqual(
            candidate._sha256(candidate.CONTROLLER_LOG), candidate.CONTROLLER_LOG_SHA256
        )

    def test_actual_opened_train_nested_masks_and_chronology_preflight_without_fit(self) -> None:
        if not candidate.SOURCE_ROOT.is_dir():
            self.skipTest("opened Train source is not present")
        cohort = base._validate_source(
            candidate.SOURCE_ROOT, expected_events=195, expected_dates=42,
            allow_test_paths=False,
        )
        with tempfile.TemporaryDirectory(dir="/private/tmp") as directory:
            state_path = Path(directory) / "checkpoint_state.csv"
            states = base._extract_state_rows(candidate.SOURCE_ROOT, state_path)
            rows, excluded = [], []
            for item in cohort:
                try:
                    rows.append(base._load_dynamic_market(
                        candidate.SOURCE_ROOT, item, states[item["game_id"]]
                    ))
                except settlement.EventExclusion as error:
                    excluded.append((item["game_id"], error.code))
        self.assertEqual(len(rows), 193)
        self.assertEqual(excluded, [
            ("2025_04_GB_DAL", "unresolved_outcome"),
            ("2025_05_TEN_ARI", "market_trade_too_stale"),
        ])
        rows.sort(key=lambda row: row.key)
        folds = settlement.chronological_date_folds(
            [item["game_date"] for item in cohort], expected_dates=42
        )
        by_date = {}
        for row in rows:
            by_date.setdefault(row.game_date, []).append(row)
        checks, fit_counts = [], []
        for fold in folds:
            outer_check = sorted([
                row for split_date in fold["check_dates"]
                for row in by_date.get(split_date, [])
            ], key=lambda row: row.key)
            outer_fit, unavailable = candidate._strict_prior_rows(
                by_date, fold["fit_dates"], outer_check
            )
            self.assertEqual(unavailable, [])
            fit_counts.append(len(outer_fit))
            checks.extend(outer_check)
            for inner in candidate.inner_date_splits(fold["fit_dates"]):
                inner_check = sorted([
                    row for split_date in inner["check_dates"]
                    for row in by_date.get(split_date, [])
                ], key=lambda row: row.key)
                inner_fit, unavailable = candidate._strict_prior_rows(
                    by_date, inner["fit_dates"], inner_check
                )
                self.assertTrue(inner_fit)
                self.assertTrue(inner_check)
                self.assertEqual(unavailable, [])
        self.assertEqual(tuple(fit_counts), candidate.EXPECTED_FIT_EVENTS)
        self.assertEqual(len(checks), 87)
        self.assertEqual(
            settlement._digest([list(row.key) for row in checks]),
            candidate.EXPECTED_CHECK_KEY_SHA256,
        )
        control = candidate._validate_v1_control()["rows_by_key"]
        self.assertEqual(set(row.key for row in checks), set(control))
        for row in checks:
            frozen = control[row.key]
            self.assertEqual(frozen["outcome"], row.trusted["outcome"])
            self.assertEqual(
                frozen["raw_market_probability"], row.trusted["market_probability"]
            )

    def test_control_mask_or_hash_mutation_fails_closed(self) -> None:
        rows, _, controls = self._synthetic_problem()
        removed = dict(controls)
        removed.pop(next(iter(removed)))
        folds = settlement.chronological_date_folds([row.game_date for row in rows])
        with self.assertRaisesRegex(ValueError, "missing from frozen v1 control"):
            candidate._fit_and_predict(rows, folds, removed)

    def test_persistent_boundary_and_static_no_network_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "persistent"):
                base._validate_roots(
                    candidate.SOURCE_ROOT, Path(directory) / "new",
                    allow_test_paths=False,
                )
        source = Path(candidate.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "import requests", "import httpx", "import aiohttp", "import socket",
            "import subprocess", "boto3", "route_dev_opened\": True",
            "sealed_final_opened\": True", "paid_provider\": True",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn('"network_bytes": 0', source)
        self.assertIn('"provider_calls": 0', source)
        self.assertIn('"provider_cost_usd": "0"', source)

    @classmethod
    def _synthetic_problem(cls):
        start = date(2025, 1, 1)
        dates = [(start + timedelta(days=index)).isoformat() for index in range(42)]
        rows = [cls._row(index, split_date) for index, split_date in enumerate(dates)]
        folds = settlement.chronological_date_folds(dates)
        controls = {}
        for fold in folds:
            for row in rows:
                if row.game_date not in fold["check_dates"]:
                    continue
                raw = row.trusted["market_probability"]
                control_probability = 1.0 / (
                    1.0 + math.exp(-(row.market_features[0] + 0.05 * ((int(row.game_week) % 3) - 1)))
                )
                controls[row.key] = {
                    "fold": fold["fold"], "game_id": row.game_id,
                    "game_date": row.game_date, "game_week": row.game_week,
                    "outcome": row.trusted["outcome"],
                    "raw_market_probability": raw,
                    "control_probability": control_probability,
                }
        return rows, folds, controls

    @staticmethod
    def _row(index: int, split_date: str) -> base.InGameRow:
        probability = 0.30 + 0.40 * ((index % 7) / 6)
        cutoff_ms = (index + 10) * 1_000_000
        down = index % 4
        state = (
            float((index * 3) % 17 - 8),
            1100.0 + (index % 9) * 30,
            float((index // 2) % 2),
            *(1.0 if down == value else 0.0 for value in range(4)),
            float(1 + (index * 3) % 10),
            -0.45 + (index % 10) / 10,
        )
        outcome = int(((index * 7 + index // 3) % 5) in (0, 1))
        trusted = {
            "event_id": f"event-{index}", "market_id": f"market-{index}",
            "cutoff_ms": cutoff_ms, "feature_available_ms": cutoff_ms,
            "market_probability": probability,
            "outcome_available_ms": cutoff_ms + 1_000,
            "outcome": outcome,
        }
        return base.InGameRow(
            game_id=f"2025_{index + 1:02d}_A_B", game_date=split_date,
            game_week=f"{index // 3 + 1:02d}", trusted=trusted,
            market_features=(math.log(probability / (1.0 - probability)),),
            state_features=state, source_receipt={},
        )


if __name__ == "__main__":
    unittest.main()
