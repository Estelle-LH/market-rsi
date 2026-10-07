from __future__ import annotations

from datetime import date, timedelta
import math
import os
from pathlib import Path
import unittest
from unittest import mock

import numpy as np

from experiments import nfl_ingame_pre_anchor_momentum_offset_logistic_train_diagnostic as candidate
from experiments import nfl_ingame_win_probability_train_diagnostic as base
from experiments import nfl_ingame_market_offset_score_time_train_diagnostic as offset
from experiments import nfl_settlement_probability_train_diagnostic as settlement


class InGamePreAnchorMomentumOffsetLogisticTests(unittest.TestCase):
    def test_objective_formula_gradient_and_unpenalized_intercept_are_exact(self) -> None:
        z = np.asarray([-1.2, -0.1, 0.4, 1.1], dtype=float)
        y = np.asarray([0, 1, 0, 1], dtype=float)
        market = np.asarray([-0.8, 0.3, -0.1, 1.0], dtype=float)
        theta = np.asarray([0.2, -0.35], dtype=float)
        value, gradient = candidate.momentum_objective_gradient(theta, z, y, market)
        eta = market + theta[0] + theta[1] * z
        expected = float(np.sum(np.logaddexp(0.0, eta) - y * eta) + 0.5 * theta[1] ** 2)
        self.assertAlmostEqual(value, expected, places=12)
        numerical = []
        for index in range(2):
            upper, lower = theta.copy(), theta.copy()
            upper[index] += 1e-6
            lower[index] -= 1e-6
            high = candidate.momentum_objective_gradient(upper, z, y, market)[0]
            low = candidate.momentum_objective_gradient(lower, z, y, market)[0]
            numerical.append((high - low) / 2e-6)
        np.testing.assert_allclose(gradient, numerical, rtol=1e-6, atol=1e-7)
        zero_beta = theta.copy(); zero_beta[1] = 0.0
        base_value = float(np.sum(np.logaddexp(0.0, market + zero_beta[0]) - y * (market + zero_beta[0])))
        self.assertAlmostEqual(
            candidate.momentum_objective_gradient(zero_beta, z, y, market)[0], base_value
        )

    def test_fit_only_standardization_has_no_check_or_label_leakage(self) -> None:
        fit = np.asarray([-2.0, -0.5, 0.5, 2.0])
        check = np.asarray([100.0, -100.0])
        z_fit, z_check, report = candidate.standardize_momentum(fit, check)
        changed_fit, _, changed_report = candidate.standardize_momentum(fit, check[::-1] * 99)
        np.testing.assert_array_equal(z_fit, changed_fit)
        self.assertEqual(report["mean"], changed_report["mean"])
        self.assertEqual(report["scale"], changed_report["scale"])
        self.assertAlmostEqual(float(np.mean(z_fit)), 0.0)
        self.assertAlmostEqual(float(np.std(z_fit)), 1.0)
        self.assertGreater(abs(z_check[0]), 1.0)
        with self.assertRaisesRegex(ValueError, "inactive"):
            candidate.standardize_momentum([1.0, 1.0], [1.0])
        with self.assertRaisesRegex(ValueError, "finite"):
            candidate.standardize_momentum([0.0, math.nan], [0.0])

    def test_probability_nests_raw_market_bitwise_at_zero_parameters(self) -> None:
        probabilities = np.asarray([0.13, 0.37, 0.61, 0.88], dtype=float)
        logits = np.log(probabilities / (1.0 - probabilities))
        observed = candidate.momentum_probabilities(np.zeros(2), np.arange(4.0), logits)
        # scipy expit(logit(p)) is numerically equal for these values; the frozen
        # candidate is not allowed to clip or replace a nonzero-parameter result.
        np.testing.assert_allclose(observed, probabilities, rtol=0.0, atol=2e-16)

    def test_all_materialized_rows_get_exact_parent_signal_without_labels(self) -> None:
        rows = [self._row(index, f"2025-01-{index + 1:02d}") for index in range(3)]
        cohort = [{"game_id": row.game_id} for row in rows]
        frozen = {"anchors": [{"game_id": row.game_id} for row in rows]}
        seen = []

        def fake_load(source_root, cohort_row, anchor, receipt):
            seen.append((cohort_row["game_id"], anchor["game_id"], receipt["sentinel"]))
            return [{"timestamp": 1}], {"source": cohort_row["game_id"]}

        def fake_signal(trades, decision_floor):
            index = decision_floor - 10_000
            probability = rows[index].trusted["market_probability"]
            return {"p_now": probability, "p_ref": probability - 0.01,
                    "signal": 0.1 + index, "decision_floor_epoch_s": decision_floor,
                    "current_latest_trade_epoch_s": decision_floor - 1,
                    "reference_cutoff_epoch_s": decision_floor - 120,
                    "reference_latest_trade_epoch_s": decision_floor - 121,
                    "reference_age_seconds": 1}

        with mock.patch.object(candidate.momentum, "_load_oriented_trades", side_effect=fake_load), \
                mock.patch.object(candidate.momentum, "market_momentum_signal", side_effect=fake_signal):
            signals, receipts = candidate._all_row_signals(Path("/unused"), rows, cohort, frozen)
            mutated = [self._replace_outcome(row, 1 - row.trusted["outcome"]) for row in rows]
            second, _ = candidate._all_row_signals(Path("/unused"), mutated, cohort, frozen)
        self.assertEqual(set(signals), {row.key for row in rows})
        self.assertEqual(signals, second)
        self.assertEqual(len(receipts), 3)
        self.assertEqual(len(seen), 6)

    def test_exact_four_candidate_fits_zero_control_refits_and_common_mask(self) -> None:
        rows, folds, signals, controls = self._synthetic_problem()
        calls = []
        original = candidate.fit_momentum_offset

        def counted(*args, **kwargs):
            calls.append(len(np.asarray(args[0])))
            return original(*args, **kwargs)

        with mock.patch.object(candidate, "fit_momentum_offset", side_effect=counted), \
                mock.patch.object(offset, "fit_offset_arm", side_effect=AssertionError("ordinary must remain archived")), \
                mock.patch.object(base, "_fit_logistic", side_effect=AssertionError("ordinary must remain archived")):
            predictions, reports = candidate._fit_and_predict(rows, folds, signals, controls)
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(reports), 4)
        self.assertEqual(len(predictions), 20)
        self.assertEqual(set(item["row"].key for item in predictions), set(controls))
        self.assertTrue(all(report["optimizer"]["retry_count"] == 0 for report in reports))
        self.assertTrue(all(report["optimizer"]["market_logit_coefficient_fixed"] == 1.0 for report in reports))

    def test_missing_fit_or_check_signal_and_control_fail_closed(self) -> None:
        rows, folds, signals, controls = self._synthetic_problem()
        missing_signal = dict(signals); missing_signal.pop(next(iter(missing_signal)))
        with self.assertRaisesRegex(ValueError, "complete materialized"):
            candidate._fit_and_predict(rows, folds, missing_signal, controls)
        missing_control = dict(controls); missing_control.pop(next(iter(missing_control)))
        with self.assertRaisesRegex(ValueError, "absent from frozen"):
            candidate._fit_and_predict(rows, folds, signals, missing_control)

    def test_decision_support_refute_inconclusive_and_keep_revert_are_exact(self) -> None:
        def fold(c: float, r: float, o: float) -> dict:
            return {"arms": {
                candidate.ARM_CANDIDATE: {"brier": c},
                candidate.ARM_RAW: {"brier": r},
                candidate.ARM_ORDINARY: {"brier": o},
            }}

        aggregate = {
            candidate.ARM_CANDIDATE: {"brier": .18, "log_loss": .48},
            candidate.ARM_RAW: {"brier": .20, "log_loss": .52},
            candidate.ARM_ORDINARY: {"brier": .19, "log_loss": .50},
        }
        paired = self._paired_interval(-0.001)
        folds = [fold(.18, .20, .19)] * 3 + [fold(.21, .20, .19)]
        self.assertEqual(candidate.momentum_offset_decision(aggregate, folds, paired)[:2],
                         ("PRE_ANCHOR_MOMENTUM_OFFSET_SUPPORTED", "KEEP"))
        bad = {**aggregate, candidate.ARM_CANDIDATE: {"brier": .201, "log_loss": .48}}
        self.assertEqual(candidate.momentum_offset_decision(bad, folds, paired)[:2],
                         ("PRE_ANCHOR_MOMENTUM_OFFSET_REFUTED", "REVERT"))
        crossing = self._paired_interval(0.001)
        self.assertEqual(candidate.momentum_offset_decision(aggregate, folds, crossing)[:2],
                         ("PRE_ANCHOR_MOMENTUM_OFFSET_INCONCLUSIVE", "REVERT"))

    def test_paired_evidence_uses_complete_date_and_week_10k_draws(self) -> None:
        records = []
        for index in range(4):
            row = {"game_id": str(index), "game_date": f"2025-01-0{index + 1}",
                   "game_week": str(index // 2 + 1)}
            for comparison in ("candidate_minus_raw_market", "candidate_minus_v0_ordinary", "v0_ordinary_minus_raw_market"):
                for metric in ("brier", "log_loss"):
                    row[f"{comparison}_{metric}"] = (index - 1.5) / 100
            records.append(row)
        calls = []

        def fake(rows, group, value, *, seed, replicates):
            calls.append((group, value, seed, replicates, len(rows)))
            return {"interval_95": [-0.1, 0.1]}

        with mock.patch.object(base, "_group_bootstrap", side_effect=fake):
            result = candidate._paired_evidence(records)
        self.assertEqual(len(result), 3)
        self.assertEqual(len(calls), 12)
        self.assertEqual({call[0] for call in calls}, {"game_date", "game_week"})
        self.assertTrue(all(call[2:] == (20260929, 10_000, 4) for call in calls))

    def test_frozen_bindings_ordinary_field_and_thread_contract(self) -> None:
        candidate._validate_execution_identity()
        frozen = candidate.prior._validate_v0_artifact(candidate.V0_ARTIFACT_ROOT)
        controls = candidate._v0_controls(frozen)
        self.assertEqual(len(controls), 87)
        first_source = frozen["predictions"][0]
        first_key = (first_source["event_id"], first_source["market_id"], int(first_source["cutoff_ms"]))
        self.assertEqual(controls[first_key]["ordinary_probability"], float(first_source["market_model_probability"]))
        self.assertEqual(candidate._digest(candidate.SCHEDULER_BRANCH_BINDING), candidate.SCHEDULER_BRANCH_BINDING_SHA256)
        self.assertEqual(candidate._digest(candidate.CANDIDATE_COMPONENT_SPEC), candidate.IMPLEMENTATION_COMPONENT_SPEC_SHA256)
        with mock.patch.dict(os.environ, {key: "1" for key in candidate.THREAD_ENV_CONTRACT}, clear=False):
            os.environ["PYTHONHASHSEED"] = "0"
            candidate._validate_thread_contract()
        with mock.patch.dict(os.environ, {"OMP_NUM_THREADS": "2"}, clear=False):
            with self.assertRaisesRegex(ValueError, "single-thread"):
                candidate._validate_thread_contract()

    def test_static_boundary_has_no_network_and_cli_is_source_output_only(self) -> None:
        source = Path(candidate.__file__).read_text(encoding="utf-8")
        for forbidden in ("import requests", "import httpx", "import aiohttp", "import socket", "boto3"):
            self.assertNotIn(forbidden, source)
        self.assertIn('"network_bytes": 0', source)
        self.assertIn('"provider_calls": 0', source)
        self.assertIn('parser.add_argument("--source-root"', source)
        self.assertIn('parser.add_argument("--output"', source)
        self.assertNotIn('parser.add_argument("--retry"', source)

    @staticmethod
    def _paired_interval(upper: float) -> dict:
        return {"candidate_minus_raw_market": {"brier": {
            "schedule_date_interval": {"interval_95": [-0.01, upper]},
            "observed_game_week_interval": {"interval_95": [-0.01, upper]},
        }}}

    @classmethod
    def _synthetic_problem(cls):
        start = date(2025, 1, 1)
        dates = [(start + timedelta(days=index)).isoformat() for index in range(42)]
        rows = [cls._row(index, split_date) for index, split_date in enumerate(dates)]
        folds = settlement.chronological_date_folds(dates)
        signals = {row.key: {
            "p_now": row.trusted["market_probability"], "p_ref": row.trusted["market_probability"] - .01,
            "signal": math.sin(index * .7) + index * .003,
            "reference_cutoff_epoch_s": int(row.trusted["cutoff_ms"]) // 1000 - 120,
            "reference_latest_trade_epoch_s": int(row.trusted["cutoff_ms"]) // 1000 - 121,
            "reference_age_seconds": 1,
        } for index, row in enumerate(rows)}
        controls = {}
        for fold in folds:
            for row in rows:
                if row.game_date in fold["check_dates"]:
                    controls[row.key] = {
                        "fold": fold["fold"], "game_id": row.game_id,
                        "game_date": row.game_date, "game_week": row.game_week,
                        "outcome": row.trusted["outcome"],
                        "raw_probability": row.trusted["market_probability"],
                        "ordinary_probability": min(.95, max(.05, row.trusted["market_probability"] + .01)),
                    }
        return rows, folds, signals, controls

    @staticmethod
    def _replace_outcome(row: base.InGameRow, outcome: int) -> base.InGameRow:
        trusted = dict(row.trusted); trusted["outcome"] = outcome
        return base.InGameRow(row.game_id, row.game_date, row.game_week, trusted,
                              row.market_features, row.state_features, row.source_receipt)

    @staticmethod
    def _row(index: int, split_date: str) -> base.InGameRow:
        probability = .25 + .5 * ((index % 9) / 8)
        logit = math.log(probability / (1 - probability))
        cutoff_s = 10_000 + index
        outcome = int((index * 7 + index // 3) % 5 in (0, 1))
        trusted = {"event_id": f"event-{index}", "market_id": f"market-{index}",
                   "cutoff_ms": cutoff_s * 1000, "feature_available_ms": cutoff_s * 1000,
                   "outcome_available_ms": cutoff_s * 1000 + 1,
                   "outcome": outcome, "market_probability": probability}
        return base.InGameRow(
            game_id=f"game-{index}", game_date=split_date, game_week=str(index // 6 + 1),
            trusted=trusted, market_features=(logit,), state_features=(0.0,) * 9,
            source_receipt={"sentinel": index, "latest_trade_epoch_ms": (cutoff_s - 1) * 1000},
        )


if __name__ == "__main__":
    unittest.main()
