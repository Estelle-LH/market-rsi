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

from experiments import nfl_market_orthogonal_price_path_train_diagnostic as candidate
from research.market_rsi.tests.test_nfl_market_offset_ridge_train_diagnostic import _row
from research.market_rsi.tests.test_nfl_settlement_probability_train_diagnostic import (
    _make_source,
    _sha,
    _write_json,
)


base = candidate.base
offset = candidate.offset
calibration = candidate.calibration


def _with_path(row, *, vwaps: tuple[float, float, float],
               moves: tuple[float, float, float],
               unused_shift: float = 0.0):
    features = list(row.features)
    for index, value in zip(candidate._feature_indices(candidate.VWAP_FEATURES), vwaps):
        features[index] = value
    for index, value in zip(candidate._feature_indices(candidate.MOVE_FEATURES), moves):
        features[index] = value
    used = {0, *candidate._feature_indices(candidate.VWAP_FEATURES),
            *candidate._feature_indices(candidate.MOVE_FEATURES)}
    for index in range(len(features)):
        if index not in used:
            features[index] += unused_shift
    return replace(row, features=tuple(features))


def _nondegenerate_rows(start: int, count: int):
    rows = []
    for index in range(start, start + count):
        row = _row(index)
        p = row.trusted["market_probability"]
        phase = float(index % 7) / 100
        rows.append(_with_path(
            row,
            vwaps=(p - 0.02 + phase, p - 0.01 - phase / 2, p + phase / 3),
            moves=(0.02 - phase, -0.01 + phase / 2, phase / 4),
        ))
    return rows


def _vary_synthetic_decision_market(source: Path) -> None:
    """Make only this test's generated source nondegenerate in market logit."""
    for index, game_root in enumerate(sorted((source / "trades").iterdir())):
        path = game_root / "trade_window.csv"
        with path.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        probability = 0.30 + 0.40 * ((index % 11) / 10)
        # The final causal second has one home and one away-token row.  Setting
        # both oriented home probabilities to p makes the decision-time market
        # exactly p while retaining every source row and fold.
        rows[-3]["price"] = str(probability)
        rows[-2]["price"] = str(1.0 - probability)
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=base.TRADE_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        manifest_path = game_root / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["trade_window_sha256"] = _sha(path)
        _write_json(manifest_path, manifest)


class PricePathTransformTests(unittest.TestCase):
    def test_frozen_spec_and_execution_bindings(self) -> None:
        candidate._validate_frozen_specs()
        identity = candidate._validate_execution_identity()
        self.assertEqual(
            base._digest(dict(candidate.CANDIDATE_SPEC)),
            candidate.EXPECTED_CANDIDATE_SPEC_SHA256,
        )
        self.assertEqual(
            identity["controller_proposal_sha256"],
            candidate.EXPECTED_CONTROLLER_PROPOSAL_SHA256,
        )

    def test_exact_named_column_formulas(self) -> None:
        row = _with_path(
            _row(3), vwaps=(0.2, 0.4, 0.6), moves=(-0.3, 0.1, 0.5)
        )
        observed = candidate.price_path_families([row])[0]
        expected = np.asarray([
            row.trusted["market_probability"] - 0.4,
            (-0.3 + 0.1 + 0.5) / 3,
        ])
        np.testing.assert_allclose(observed, expected, rtol=0, atol=1e-15)

    def test_transform_is_fit_only_label_free_and_check_changes_do_not_refit(self) -> None:
        fit = _nondegenerate_rows(0, 22)
        check = _nondegenerate_rows(22, 5)
        first = candidate.fit_price_path_transform(fit, check)
        changed_fit = [
            replace(row, trusted={**row.trusted, "outcome": 1 - row.trusted["outcome"]})
            for row in fit
        ]
        changed_fit_result = candidate.fit_price_path_transform(changed_fit, check)
        self.assertEqual(first["parameters"], changed_fit_result["parameters"])
        np.testing.assert_array_equal(
            first["fit_design"], changed_fit_result["fit_design"]
        )
        changed_check = [
            _with_path(
                replace(row, trusted={**row.trusted, "outcome": 1 - row.trusted["outcome"]}),
                vwaps=(0.05, 0.95, 0.15), moves=(0.8, -0.7, 0.6),
            ) for row in check
        ]
        second = candidate.fit_price_path_transform(fit, changed_check)
        self.assertEqual(first["parameters"], second["parameters"])
        np.testing.assert_array_equal(first["fit_design"], second["fit_design"])
        self.assertNotEqual(
            changed_check[0].trusted["outcome"], check[0].trusted["outcome"]
        )

    def test_fit_residuals_are_orthogonal_rank_two(self) -> None:
        fit = _nondegenerate_rows(0, 30)
        check = _nondegenerate_rows(30, 8)
        result = candidate.fit_price_path_transform(fit, check)
        market_z = result["fit_design"][:, 0]
        design = np.column_stack((np.ones(len(fit)), market_z))
        np.testing.assert_allclose(
            design.T @ result["residual_fit"], np.zeros((2, 2)), atol=2e-14
        )
        self.assertEqual(result["parameters"]["rank"], 2)

    def test_rank_failure_is_closed(self) -> None:
        prototype = _row(0)
        rows = []
        for index in range(4):
            trusted = dict(prototype.trusted)
            trusted.update({"event_id": str(index), "market_id": str(index),
                            "outcome": index % 2})
            rows.append(replace(prototype, trusted=trusted))
        with self.assertRaisesRegex(
                offset.InvalidDataQuality, "market_residualization_rank_failure") as caught:
            candidate.fit_price_path_transform(rows, rows[:2])
        self.assertEqual(caught.exception.report["status"], "INVALID_DATA_QUALITY")
        self.assertEqual(caught.exception.report["observed_rank"], 1)

    def test_shape_and_nonfinite_feature_failures_are_invalid_data_quality(self) -> None:
        valid = _row(0)
        cases = (
            replace(valid, features=valid.features[:-1]),
            replace(valid, features=(valid.features[0], float("nan"), *valid.features[2:])),
        )
        for row in cases:
            with self.subTest(feature_count=len(row.features)), \
                    self.assertRaises(offset.InvalidDataQuality) as caught:
                candidate.price_path_families([row])
            self.assertEqual(caught.exception.report["status"], "INVALID_DATA_QUALITY")
            self.assertEqual(
                caught.exception.report["reason"],
                "feature_matrix_shape_or_nonfinite",
            )

    def test_inactive_fit_family_is_zero_for_fit_and_check(self) -> None:
        fit = []
        check = []
        for target, indices in ((fit, range(20)), (check, range(20, 25))):
            for index in indices:
                row = _row(index)
                p = row.trusted["market_probability"]
                # Both raw families are exactly affine in market logit on fit.
                logit = row.features[0]
                target.append(_with_path(
                    row, vwaps=(p - (0.1 + 0.02 * logit),) * 3,
                    moves=(0.03 - 0.01 * logit,) * 3,
                ))
        result = candidate.fit_price_path_transform(fit, check)
        self.assertEqual(result["parameters"]["inactive_families_g_d"], [True, True])
        np.testing.assert_array_equal(result["fit_design"][:, 1:], 0.0)
        np.testing.assert_array_equal(result["check_design"][:, 1:], 0.0)

    def test_unused_feature_columns_do_not_change_candidate_design(self) -> None:
        fit = _nondegenerate_rows(0, 22)
        check = _nondegenerate_rows(22, 5)
        shifted_fit = [
            _with_path(row,
                       vwaps=tuple(row.features[i] for i in candidate._feature_indices(candidate.VWAP_FEATURES)),
                       moves=tuple(row.features[i] for i in candidate._feature_indices(candidate.MOVE_FEATURES)),
                       unused_shift=1000.0)
            for row in fit
        ]
        shifted_check = [
            _with_path(row,
                       vwaps=tuple(row.features[i] for i in candidate._feature_indices(candidate.VWAP_FEATURES)),
                       moves=tuple(row.features[i] for i in candidate._feature_indices(candidate.MOVE_FEATURES)),
                       unused_shift=-1000.0)
            for row in check
        ]
        first = candidate.fit_price_path_transform(fit, check)
        second = candidate.fit_price_path_transform(shifted_fit, shifted_check)
        np.testing.assert_array_equal(first["fit_design"], second["fit_design"])
        np.testing.assert_array_equal(first["check_design"], second["check_design"])


class CandidateMathAndIntegrityTests(unittest.TestCase):
    def test_per_fold_stage_order_and_exact_fit_semantics(self) -> None:
        fit = _nondegenerate_rows(0, 22)
        check = _nondegenerate_rows(22, 5)
        order = []
        original_fit = offset.fit_offset_ridge
        original_diagnostics = candidate.information_diagnostics

        def tracked_fit(features, outcomes, logits):
            order.append(f"offset_fit_{np.asarray(features).shape[1]}_columns")
            return original_fit(features, outcomes, logits)

        def tracked_diagnostics(raw, residual, standardized, market_logits,
                                outcomes, market, dates):
            order.append(f"information_{len(raw)}_rows")
            return original_diagnostics(
                raw, residual, standardized, market_logits,
                outcomes, market, dates,
            )

        with mock.patch.object(offset, "fit_offset_ridge", side_effect=tracked_fit), \
                mock.patch.object(candidate, "information_diagnostics",
                                  side_effect=tracked_diagnostics):
            candidate._fit_fold_models(fit, check)
        self.assertEqual(order, [
            "offset_fit_1_columns",  # calibration control
            "information_22_rows",  # measured before candidate fit
            "offset_fit_3_columns",  # candidate
            "information_5_rows",   # check diagnostics after prediction
        ])

    def test_check_labels_cannot_change_candidate_fit_or_predictions(self) -> None:
        fit = _nondegenerate_rows(0, 22)
        check = _nondegenerate_rows(22, 5)
        first = candidate._fit_fold_models(fit, check)
        flipped = [
            replace(row, trusted={**row.trusted, "outcome": 1 - row.trusted["outcome"]})
            for row in check
        ]
        second = candidate._fit_fold_models(fit, flipped)
        self.assertEqual(first["candidate_parameters"], second["candidate_parameters"])
        np.testing.assert_array_equal(
            first["candidate_values"], second["candidate_values"]
        )
        self.assertNotEqual(
            first["check_information_diagnostics"],
            second["check_information_diagnostics"],
        )

    def test_diagnostics_are_non_gating_and_cannot_tune_predictions_or_keep(self) -> None:
        fit = _nondegenerate_rows(0, 22)
        check = _nondegenerate_rows(22, 5)
        first = candidate._fit_fold_models(fit, check)
        arbitrary = {"families": {"tampered": True}, "not_used_by_model": True}
        with mock.patch.object(
                candidate, "information_diagnostics", return_value=arbitrary):
            second = candidate._fit_fold_models(fit, check)
        self.assertEqual(first["candidate_parameters"], second["candidate_parameters"])
        np.testing.assert_array_equal(
            first["candidate_values"], second["candidate_values"]
        )
        # KEEP receives proper scores/fold wins only; no diagnostics argument.
        keep_a = offset.diagnostic_keep(
            {"brier": .19, "log_loss": .55}, {"brier": .20, "log_loss": .56},
            {"brier": .22, "log_loss": .62}, [True] * 4, [True] * 4,
        )
        keep_b = offset.diagnostic_keep(
            {"brier": .19, "log_loss": .55}, {"brier": .20, "log_loss": .56},
            {"brier": .22, "log_loss": .62}, [True] * 4, [True] * 4,
        )
        self.assertEqual(keep_a, keep_b)

    def test_zero_parameters_recover_market_and_zero_families_recover_calibration(self) -> None:
        fit = _nondegenerate_rows(0, 22)
        check = _nondegenerate_rows(22, 5)
        transform = candidate.fit_price_path_transform(fit, check)
        market = np.asarray([row.trusted["market_probability"] for row in check])
        np.testing.assert_allclose(
            offset.offset_probabilities(
                np.zeros(4), transform["check_design"], transform["check_logits"]
            ), market, rtol=0, atol=np.finfo(np.float64).eps,
        )
        controls = calibration._fit_fold_models(fit, check)
        b = controls["calibration_parameters"]["b"]
        w = controls["calibration_parameters"]["w"]
        values = offset.offset_probabilities(
            np.asarray([b, w, 0.0, 0.0]),
            transform["check_design"], transform["check_logits"],
        )
        np.testing.assert_allclose(values, controls["calibration_values"], atol=2e-16)

    def test_four_parameter_gradient_penalty_and_fit_are_deterministic(self) -> None:
        rng = np.random.default_rng(29)
        design = rng.normal(size=(19, 3))
        labels = np.asarray([0, 1] * 9 + [1], dtype=np.float64)
        logits = rng.normal(size=19)
        theta = rng.normal(scale=0.2, size=4)
        objective, gradient = offset.offset_objective_gradient(
            theta, design, labels, logits
        )
        linear = logits + theta[0] + design @ theta[1:]
        expected = np.mean(np.logaddexp(0, linear) - labels * linear)
        expected += 0.5 * theta @ theta
        self.assertAlmostEqual(objective, expected, places=14)
        numerical = np.empty(4)
        epsilon = 1e-6
        for index in range(4):
            step = np.zeros(4)
            step[index] = epsilon
            numerical[index] = (
                offset.offset_objective_gradient(theta + step, design, labels, logits)[0]
                - offset.offset_objective_gradient(theta - step, design, labels, logits)[0]
            ) / (2 * epsilon)
        np.testing.assert_allclose(gradient, numerical, rtol=2e-7, atol=2e-8)
        first, _ = offset.fit_offset_ridge(design, labels, logits)
        second, _ = offset.fit_offset_ridge(design, labels, logits)
        np.testing.assert_array_equal(first, second)

    def test_mask_label_time_staleness_resampling_and_keep_are_reused(self) -> None:
        passing = _row(0, staleness=600)
        offset.require_staleness_gate(
            offset.staleness_inventory([passing], {passing.game_id: 0}),
            expected_binary_rows=1,
        )
        failing = _row(1, staleness=601)
        with self.assertRaises(offset.InvalidDataQuality):
            offset.require_staleness_gate(
                offset.staleness_inventory([failing], {failing.game_id: 1}),
                expected_binary_rows=1,
            )
        rows = [_row(index) for index in range(42)]
        plan = calibration._fold_plan(
            rows, base.chronological_date_folds([row.split_date for row in rows])
        )
        self.assertEqual(
            [(len(item["fit_rows"]), len(item["check_rows"])) for item in plan],
            [(22, 5), (27, 5), (32, 5), (37, 5)],
        )
        report = calibration._group_delta_detail(
            [10.0, 1.0, 3.0], ["small", "large", "large"]
        )
        self.assertAlmostEqual(report["point_estimate"], 14 / 3)
        decision, _ = offset.diagnostic_keep(
            {"brier": .19, "log_loss": .55},
            {"brier": .20, "log_loss": .56},
            {"brier": .22, "log_loss": .62},
            [True, True, True, False], [True, True, True, False],
        )
        self.assertEqual(decision, "KEEP")

    def test_information_diagnostics_handle_ties_and_one_game_dates(self) -> None:
        raw = np.asarray([[1., 2.], [2., 2.], [3., 4.]])
        residual = np.asarray([[-1., 0.], [0., 0.], [1., 0.]])
        standardized = residual.copy()
        report = candidate.information_diagnostics(
            raw, residual, standardized, np.asarray([-1., 0., 1.]),
            [0, 1, 1], [.2, .5, .8], ["a", "b", "b"],
        )
        family = report["families"]["g_market_minus_mean_vwap"]
        self.assertEqual(family["pearson_z_with_y_minus_market"]["count"], 3)
        self.assertEqual(family["per_schedule_date_moment"][0]["events"], 1)
        inactive = report["families"]["d_mean_price_move"]
        self.assertEqual(inactive["spearman_z_with_y_minus_market"]["reason"],
                         "constant_input")


class CandidateEndToEndTests(unittest.TestCase):
    def _calibration_archive(self, source: Path, root: Path) -> Path:
        first, archived_offset = root / "offset-a", root / "offset-archive"
        fixed = "2026-09-29T18:00:00+00:00"
        offset.run(source, first, expected_events=42, expected_dates=42,
                   allow_test_paths=True, generated_utc=fixed)
        offset.run(
            source, archived_offset, expected_events=42, expected_dates=42,
            allow_test_paths=True, generated_utc=fixed,
            parent_predictions_path=first / "predictions.csv",
        )
        archive = root / "calibration-archive"
        calibration.run(
            source, archive, expected_events=42, expected_dates=42,
            allow_test_paths=True, generated_utc=fixed,
            archived_offset_root=archived_offset,
        )
        return archive

    def test_runner_is_deterministic_no_network_and_controls_archive_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "synthetic-train"
            source.mkdir()
            _make_source(source, tie_index=3)
            _vary_synthetic_decision_market(source)
            with mock.patch.object(
                    socket, "socket", side_effect=AssertionError("network used")):
                archive = self._calibration_archive(source, root)
                first_root, second_root = root / "candidate-a", root / "candidate-b"
                original_fit = offset.fit_offset_ridge
                original_ordinary_fit = calibration.LogisticRegression.fit
                offset_widths = []
                ordinary_widths = []

                def tracked_offset_fit(features, outcomes, logits):
                    offset_widths.append(np.asarray(features).shape[1])
                    return original_fit(features, outcomes, logits)

                def tracked_ordinary_fit(estimator, features, outcomes, *args, **kwargs):
                    ordinary_widths.append(np.asarray(features).shape[1])
                    return original_ordinary_fit(
                        estimator, features, outcomes, *args, **kwargs
                    )

                with mock.patch.object(
                        offset, "fit_offset_ridge", side_effect=tracked_offset_fit), \
                        mock.patch.object(
                            calibration.LogisticRegression, "fit",
                            new=tracked_ordinary_fit,
                        ):
                    first = candidate.run(
                        source, first_root, expected_events=42, expected_dates=42,
                        allow_test_paths=True,
                        generated_utc="2026-09-29T18:01:00+00:00",
                        archived_calibration_root=archive,
                    )
                    self.assertEqual(offset_widths.count(1), 4)
                    self.assertEqual(offset_widths.count(3), 4)
                    self.assertEqual(len(offset_widths), 8)
                    self.assertEqual(ordinary_widths, [len(base.FEATURE_NAMES)] * 4)
                second = candidate.run(
                    source, second_root, expected_events=42, expected_dates=42,
                    allow_test_paths=True,
                    generated_utc="2026-09-29T18:01:00+00:00",
                    archived_calibration_root=archive,
                )
            self.assertEqual(first, second)
            self.assertEqual(first["model_fits"], 12)
            self.assertEqual(first["candidate_fits"], 4)
            self.assertEqual(first["calibration_fits"], 4)
            self.assertEqual(first["ordinary_reference_fits"], 4)
            self.assertEqual(first["archived_full_offset_refits"], 0)
            score_a = json.loads((first_root / "scorecard.json").read_text())
            score_b = json.loads((second_root / "scorecard.json").read_text())
            self.assertEqual(score_a, score_b)
            self.assertEqual(set(score_a["arms"]), {
                "market", "ordinary_reference", "market_only_calibration",
                "archived_full_offset", "candidate",
            })
            self.assertLessEqual(
                score_a["control_parity"]["maximum_calibration_absolute_difference"],
                1e-10,
            )
            with (archive / "predictions.csv").open(newline="") as stream:
                frozen = list(csv.DictReader(stream))
            with (first_root / "predictions.csv").open(newline="") as stream:
                observed = list(csv.DictReader(stream))
            self.assertEqual(
                [row["market_only_calibration_probability"] for row in frozen],
                [row["market_only_calibration_probability"] for row in observed],
            )

    def test_rank_failure_persists_invalid_data_quality_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "constant-market-source"
            source.mkdir()
            _make_source(source, tie_index=3)
            archive = self._calibration_archive(source, root)
            output = root / "candidate-invalid"
            with self.assertRaises(offset.InvalidDataQuality):
                candidate.run(
                    source, output, expected_events=42, expected_dates=42,
                    allow_test_paths=True,
                    generated_utc="2026-09-29T18:02:00+00:00",
                    archived_calibration_root=archive,
                )
            failure = json.loads((output / "failure.json").read_text())
            self.assertEqual(failure["status"], "INVALID_DATA_QUALITY")
            self.assertEqual(
                failure["data_quality_report"]["reason"],
                "market_residualization_rank_failure",
            )
            self.assertTrue(failure["fit_started"])
            self.assertFalse(failure["scoring_started"])


if __name__ == "__main__":
    unittest.main()
