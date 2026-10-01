from __future__ import annotations

import csv
from dataclasses import replace
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest import mock

import numpy as np

from experiments import nfl_market_only_ridge_calibration_train_diagnostic as calibration
from experiments import nfl_market_offset_ridge_train_diagnostic as offset
from research.market_rsi.tests.test_nfl_market_offset_ridge_train_diagnostic import _row
from research.market_rsi.tests.test_nfl_settlement_probability_train_diagnostic import (
    _make_source,
)


base = calibration.base


class FrozenCalibrationMathTests(unittest.TestCase):
    def test_specs_sources_runtime_and_archived_result_are_exact(self) -> None:
        calibration._validate_frozen_specs()
        identity = calibration._validate_execution_identity()
        self.assertEqual(identity["offset_runner_sha256"],
                         calibration.EXPECTED_OFFSET_RUNNER_SHA256)
        self.assertEqual(identity["offset_test_sha256"],
                         calibration.EXPECTED_OFFSET_TEST_SHA256)
        self.assertEqual(identity["controller_proposal_sha256"],
                         calibration.EXPECTED_CONTROLLER_PROPOSAL_SHA256)
        archived = calibration.validate_archived_offset_artifact(
            calibration.ARCHIVED_OFFSET_ROOT, verify_frozen_hashes=True
        )
        self.assertEqual(
            archived["artifact_hashes"], dict(calibration.ARCHIVED_OFFSET_SHA256)
        )
        self.assertEqual(archived["manifest_decision"], "REVERT")

    def test_one_column_analytic_gradient_and_zero_recovery(self) -> None:
        features = np.asarray([[-1.5], [-0.2], [0.4], [1.8]], dtype=np.float64)
        outcomes = np.asarray([0, 1, 0, 1], dtype=np.float64)
        market = np.asarray([0.2, 0.45, 0.6, 0.8], dtype=np.float64)
        logits = np.log(market / (1.0 - market))
        parameters = np.asarray([0.17, -0.23], dtype=np.float64)
        _, gradient = offset.offset_objective_gradient(
            parameters, features, outcomes, logits
        )
        epsilon = 1e-6
        numerical = np.empty_like(parameters)
        for index in range(2):
            step = np.zeros(2)
            step[index] = epsilon
            high = offset.offset_objective_gradient(
                parameters + step, features, outcomes, logits
            )[0]
            low = offset.offset_objective_gradient(
                parameters - step, features, outcomes, logits
            )[0]
            numerical[index] = (high - low) / (2 * epsilon)
        np.testing.assert_allclose(gradient, numerical, rtol=2e-7, atol=2e-8)
        np.testing.assert_allclose(
            offset.offset_probabilities(np.zeros(2), features, logits), market,
            rtol=0.0, atol=np.finfo(np.float64).eps,
        )

    def test_mean_nll_and_both_parameter_penalties_are_unchanged(self) -> None:
        features = np.asarray([[-1.0], [2.0]], dtype=np.float64)
        outcomes = np.asarray([0.0, 1.0], dtype=np.float64)
        logits = np.asarray([0.2, -0.4], dtype=np.float64)
        parameters = np.asarray([0.5, -0.25], dtype=np.float64)
        value, gradient = offset.offset_objective_gradient(
            parameters, features, outcomes, logits
        )
        eta = logits + parameters[0] + features[:, 0] * parameters[1]
        expected = float(np.mean(np.logaddexp(0.0, eta) - outcomes * eta))
        expected += 0.5 * float(parameters @ parameters)
        residual = 1.0 / (1.0 + np.exp(-eta)) - outcomes
        expected_gradient = np.asarray([
            np.mean(residual), np.mean(features[:, 0] * residual)
        ]) + parameters
        self.assertAlmostEqual(value, expected, places=14)
        np.testing.assert_allclose(gradient, expected_gradient, atol=1e-14, rtol=0)


class CalibrationIntegrityTests(unittest.TestCase):
    def test_one_column_scaler_matches_full_column_zero_and_ignores_other_check_columns(self) -> None:
        fit_rows = [_row(index) for index in range(22)]
        check_rows = [_row(22 + index) for index in range(5)]
        first = calibration._fit_fold_models(fit_rows, check_rows)
        changed = []
        for row in check_rows:
            features = (row.features[0], *(value + 10000.0 for value in row.features[1:]))
            changed.append(replace(row, features=features))
        second = calibration._fit_fold_models(fit_rows, changed)
        np.testing.assert_array_equal(
            first["calibration_values"], second["calibration_values"]
        )
        parameters = first["calibration_parameters"]
        self.assertLessEqual(
            parameters["single_vs_full_scaler_mean_absolute_difference"], 1e-12
        )
        self.assertLessEqual(
            parameters["single_vs_full_scaler_scale_absolute_difference"], 1e-12
        )
        self.assertEqual(len(first["optimizer"]["parameters"]), 2)

    def test_scaling_is_fit_only(self) -> None:
        fit_rows = [_row(index) for index in range(22)]
        check_rows = [_row(22 + index) for index in range(5)]
        first = calibration._fit_fold_models(fit_rows, check_rows)
        shifted_check = []
        for row in check_rows:
            probability = 0.99 - 0.01 * (int(row.trusted["event_id"]) % 3)
            trusted = dict(row.trusted)
            trusted["market_probability"] = probability
            logit = float(np.log(probability / (1 - probability)))
            shifted_check.append(replace(row, trusted=trusted,
                                         features=(logit, *row.features[1:])))
        shifted = calibration._fit_fold_models(fit_rows, shifted_check)
        for key in ("mu", "scale", "b", "w"):
            self.assertEqual(first["calibration_parameters"][key],
                             shifted["calibration_parameters"][key])

    def test_staleness_and_canonical_mask_contracts_are_reused(self) -> None:
        passing = _row(0, staleness=600)
        report = offset.staleness_inventory([passing], {passing.game_id: 0})
        offset.require_staleness_gate(report, expected_binary_rows=1)
        failing = _row(1, staleness=601)
        report = offset.staleness_inventory([failing], {failing.game_id: 1})
        with self.assertRaises(offset.InvalidDataQuality):
            offset.require_staleness_gate(report, expected_binary_rows=1)
        rows = [_row(0), _row(1), _row(2)]
        expected = offset.canonical_check_mask_sha256(rows)
        offset.require_expected_check_mask([rows[2], rows[0], rows[1]], expected)
        changed = dict(rows[1].trusted)
        changed["market_id"] = "changed-market"
        mutated = [rows[2], rows[0], replace(rows[1], trusted=changed)]
        with self.assertRaisesRegex(ValueError, "check mask differs"):
            offset.require_expected_check_mask(mutated, expected)

    def test_unequal_date_resampling_preserves_event_weighting_and_unit_sums(self) -> None:
        report = calibration._group_delta_detail(
            [10.0, 1.0, 3.0], ["small", "large", "large"]
        )
        self.assertAlmostEqual(report["point_estimate"], 14.0 / 3.0)
        records = {row["unit"]: row for row in report["per_unit_event_delta_records"]}
        self.assertEqual(records["large"], {
            "unit": "large", "events": 2, "delta_sum": 4.0, "delta_mean": 2.0
        })
        self.assertEqual(records["small"], {
            "unit": "small", "events": 1, "delta_sum": 10.0,
            "delta_mean": 10.0,
        })

    def test_keep_rule_is_calibration_vs_market_and_ordinary_only(self) -> None:
        candidate = {"brier": 0.19, "log_loss": 0.56}
        market = {"brier": 0.20, "log_loss": 0.58}
        ordinary = {"brier": 0.23, "log_loss": 0.64}
        self.assertEqual(offset.diagnostic_keep(
            candidate, market, ordinary,
            [True, True, True, False], [True, True, True, False],
        )[0], "KEEP")
        self.assertEqual(offset.diagnostic_keep(
            {"brier": 0.20, "log_loss": 0.56}, market, ordinary,
            [True] * 4, [True] * 4,
        )[0], "REVERT")


class CalibrationEndToEndTests(unittest.TestCase):
    def _synthetic_archive(self, source: Path, root: Path) -> Path:
        first = root / "offset-a"
        archive = root / "offset-archive"
        fixed = "2026-09-29T18:00:00+00:00"
        offset.run(
            source, first, expected_events=42, expected_dates=42,
            allow_test_paths=True, generated_utc=fixed,
        )
        offset.run(
            source, archive, expected_events=42, expected_dates=42,
            allow_test_paths=True, generated_utc=fixed,
            parent_predictions_path=first / "predictions.csv",
        )
        return archive

    def test_synthetic_runner_is_deterministic_no_network_and_never_refits_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "synthetic-train"
            source.mkdir()
            _make_source(source, tie_index=3)
            with mock.patch.object(
                    socket, "socket", side_effect=AssertionError("network used")):
                archive = self._synthetic_archive(source, root)
                first_output = root / "calibration-a"
                second_output = root / "calibration-b"
                original_fit = offset.fit_offset_ridge
                with mock.patch.object(
                        offset, "fit_offset_ridge", wraps=original_fit) as fit_call:
                    first = calibration.run(
                        source, first_output,
                        expected_events=42, expected_dates=42,
                        allow_test_paths=True,
                        generated_utc="2026-09-29T18:01:00+00:00",
                        archived_offset_root=archive,
                    )
                    self.assertEqual(fit_call.call_count, 4)
                second = calibration.run(
                    source, second_output,
                    expected_events=42, expected_dates=42,
                    allow_test_paths=True,
                    generated_utc="2026-09-29T18:01:00+00:00",
                    archived_offset_root=archive,
                )
            self.assertEqual(first, second)
            self.assertEqual(first["model_fits"], 8)
            self.assertEqual(first["calibration_fits"], 4)
            self.assertEqual(first["ordinary_reference_fits"], 4)
            self.assertEqual(first["archived_full_offset_refits"], 0)
            score_a = json.loads((first_output / "scorecard.json").read_text())
            score_b = json.loads((second_output / "scorecard.json").read_text())
            self.assertEqual(score_a, score_b)
            self.assertEqual(set(score_a["arms"]), {
                "market", "ordinary_reference", "market_only_calibration",
                "archived_full_offset",
            })
            self.assertTrue(score_a["archive_parity"]["identity_order_outcomes_exact"])
            self.assertFalse(score_a["archive_parity"]["archived_full_offset_refit"])
            self.assertEqual(
                score_a["corrected_grouped_inference"]["events"], 20
            )
            self.assertIn(
                "archived_full_offset_minus_market_only_calibration",
                score_a["aggregate"]["pairwise_deltas"],
            )
            with (archive / "predictions.csv").open(newline="") as stream:
                archived = list(csv.DictReader(stream))
            with (first_output / "predictions.csv").open(newline="") as stream:
                observed = list(csv.DictReader(stream))
            self.assertEqual(
                [row["candidate_probability"] for row in archived],
                [row["archived_full_offset_probability"] for row in observed],
            )

    def test_archived_identity_mutation_fails_closed(self) -> None:
        rows = [_row(index) for index in range(42)]
        plan = calibration._fold_plan(
            rows, base.chronological_date_folds([row.split_date for row in rows])
        )
        predictions, reports = calibration._fit_and_predict(plan)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "predictions.csv"
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=calibration.ARCHIVED_FIELDS)
                writer.writeheader()
                for index, item in enumerate(predictions):
                    row = item["row"]
                    writer.writerow({
                        "fold": item["fold"],
                        "game_id": row.game_id,
                        "split_date": row.split_date,
                        "game_week": offset.game_week(row.game_id),
                        "event_id": "changed" if index == 0 else row.trusted["event_id"],
                        "market_id": row.trusted["market_id"],
                        "cutoff_ms": row.trusted["cutoff_ms"],
                        "outcome_available_ms": row.trusted["outcome_available_ms"],
                        "outcome": row.trusted["outcome"],
                        "market_probability": row.trusted["market_probability"],
                        "ordinary_probability": item["ordinary"]["probability"],
                        "candidate_probability": item[
                            "market_only_calibration"
                        ]["probability"],
                    })
            with self.assertRaisesRegex(ValueError, "identity/order/outcome"):
                calibration.bind_archived_full_offset(
                    predictions, reports, path, verify_frozen_hash=False
                )


if __name__ == "__main__":
    unittest.main()
