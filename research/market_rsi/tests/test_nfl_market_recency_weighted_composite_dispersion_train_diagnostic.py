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

from experiments import nfl_market_recency_weighted_composite_dispersion_train_diagnostic as dispersion
from research.market_rsi.tests.test_nfl_market_orthogonal_price_path_train_diagnostic import (
    _nondegenerate_rows,
    _vary_synthetic_decision_market,
)
from research.market_rsi.tests.test_nfl_market_recent_composite_path_train_diagnostic import (
    _stationarize_synthetic_price_paths,
)
from research.market_rsi.tests import (
    test_nfl_market_all_prior_decay_composite_path_train_diagnostic as all_prior_test,
)
from research.market_rsi.tests.test_nfl_settlement_probability_train_diagnostic import (
    _make_source,
)


parent = dispersion.parent
incumbent = dispersion.incumbent
recent = dispersion.recent
base = dispersion.base
offset = dispersion.offset
calibration = dispersion.calibration
prior = dispersion.prior


def _with_dispersion(rows: list, *, phase: float = 0.0) -> list:
    indices = dispersion._feature_indices(dispersion.DISPERSION_FEATURES)
    varied = []
    for ordinal, row in enumerate(rows):
        features = list(row.features)
        for horizon, index in enumerate(indices):
            features[index] = (
                0.01 + phase + .002 * ((ordinal + 2 * horizon) % 5)
                + .0003 * ordinal ** 2
            )
        varied.append(replace(row, features=tuple(features)))
    return varied


def _set_dispersion_values(rows: list, values: np.ndarray) -> list:
    indices = dispersion._feature_indices(dispersion.DISPERSION_FEATURES)
    result = []
    for row, value in zip(rows, values, strict=True):
        features = list(row.features)
        for index in indices:
            features[index] = float(value)
        result.append(replace(row, features=tuple(features)))
    return result


class DispersionMathTests(unittest.TestCase):
    def test_frozen_identity_feature_formula_and_transform_are_fit_only(self) -> None:
        dispersion._validate_frozen_specs()
        identity = dispersion._validate_execution_identity()
        self.assertEqual(
            identity["parent_result_review_sha256"],
            "c5b706e474af4ef1fac34eab1c19567f03c300f0c77f03bafcd129d09913f882",
        )
        self.assertEqual(
            base._digest(dict(dispersion.CANDIDATE_SPEC)),
            dispersion.EXPECTED_CANDIDATE_SPEC_SHA256,
        )
        selected = _with_dispersion(_nondegenerate_rows(0, 24))
        older = _with_dispersion(_nondegenerate_rows(30, 6), phase=.003)
        check = _with_dispersion(_nondegenerate_rows(40, 7), phase=.006)
        raw = dispersion.dispersion_raw(selected)
        matrix = np.asarray([row.features for row in selected])
        np.testing.assert_array_equal(
            raw,
            np.mean(matrix[:, dispersion._feature_indices(
                dispersion.DISPERSION_FEATURES
            )], axis=1),
        )
        base_transform = recent.fit_recent_composite_transform(selected, older, check)
        first = dispersion.fit_dispersion_transform(
            base_transform, selected, older, check
        )
        changed_check = _with_dispersion(check, phase=.15)
        second = dispersion.fit_dispersion_transform(
            recent.fit_recent_composite_transform(selected, older, changed_check),
            selected, older, changed_check,
        )
        self.assertEqual(first["parameters"], second["parameters"])
        np.testing.assert_array_equal(
            first["selected"]["z_dispersion"],
            second["selected"]["z_dispersion"],
        )
        flipped = [replace(row, trusted={
            **row.trusted, "outcome": 1 - row.trusted["outcome"]
        }) for row in selected]
        third = dispersion.fit_dispersion_transform(
            recent.fit_recent_composite_transform(flipped, older, check),
            flipped, older, check,
        )
        self.assertEqual(first["parameters"], third["parameters"])
        orthogonal = first["parameters"]["dispersion_selected_fit_orthogonality"]
        self.assertLess(orthogonal["absolute_residual_mean"], 1e-12)
        self.assertLess(orthogonal["absolute_mean_z_market_times_residual"], 1e-12)
        self.assertLess(orthogonal["absolute_mean_z_composite_times_residual"], 1e-12)

    def test_two_parameter_weighted_objective_gradient_and_market_nesting(self) -> None:
        design = np.asarray([[-1.1, .2], [-.3, -1.2], [.5, .6], [1.4, 1.1]])
        labels = np.asarray([0., 1., 0., 1.])
        market = np.asarray([.2, .45, .6, .8])
        logits = np.log(market / (1 - market))
        weights = np.asarray([.25, .5, 1., 1.])
        theta = np.asarray([.17, -.09])
        value, gradient = dispersion.weighted_objective_gradient(
            theta, design, labels, logits, weights
        )
        eta = logits + design @ theta
        expected = np.sum(weights * (np.logaddexp(0, eta) - labels * eta)) / np.sum(weights)
        expected += .5 * float(theta @ theta)
        self.assertAlmostEqual(value, float(expected), places=14)
        epsilon = 1e-6
        numerical = np.asarray([
            (
                dispersion.weighted_objective_gradient(
                    theta + np.eye(2)[column] * epsilon,
                    design, labels, logits, weights,
                )[0]
                - dispersion.weighted_objective_gradient(
                    theta - np.eye(2)[column] * epsilon,
                    design, labels, logits, weights,
                )[0]
            ) / (2 * epsilon) for column in range(2)
        ])
        np.testing.assert_allclose(gradient, numerical, rtol=0, atol=1e-8)
        scaled = dispersion.weighted_objective_gradient(
            theta, design, labels, logits, weights * 13
        )
        self.assertAlmostEqual(value, scaled[0], places=14)
        np.testing.assert_allclose(gradient, scaled[1], rtol=0, atol=1e-15)
        first, first_report = dispersion.fit_weighted_dispersion(
            design, labels, logits, weights
        )
        second, second_report = dispersion.fit_weighted_dispersion(
            design, labels, logits, weights
        )
        np.testing.assert_array_equal(first, second)
        self.assertEqual(first_report, second_report)
        nested = dispersion.dispersion_probabilities(
            np.zeros(2), design, logits, market
        )
        self.assertTrue(np.array_equal(nested, market))
        with self.assertRaisesRegex(ValueError, "logits differ"):
            dispersion.dispersion_probabilities(
                np.zeros(2), design, logits + .1, market
            )

    def test_rank_inactive_nonfinite_and_incumbent_decision_paths(self) -> None:
        selected = _with_dispersion(_nondegenerate_rows(0, 24))
        older = _with_dispersion(_nondegenerate_rows(30, 6), phase=.003)
        check = _with_dispersion(_nondegenerate_rows(40, 7), phase=.006)
        rank_bad = recent.fit_recent_composite_transform(selected, older, check)
        params = rank_bad["parameters"]
        for name in ("selected", "older", "check"):
            z_market = (
                rank_bad[name]["logits"] - params["market_scaler_mean"]
            ) / params["market_scaler_scale"]
            rank_bad[name]["z_composite"] = z_market.copy()
        with self.assertRaises(offset.InvalidDataQuality):
            dispersion.fit_dispersion_transform(
                rank_bad, selected, older, check
            )

        base_transform = recent.fit_recent_composite_transform(selected, older, check)
        params = base_transform["parameters"]
        adjusted = {}
        for name, rows in (("selected", selected), ("older", older), ("check", check)):
            z_market = (
                base_transform[name]["logits"] - params["market_scaler_mean"]
            ) / params["market_scaler_scale"]
            exact_linear = (
                .02 + .003 * z_market + .004 * base_transform[name]["z_composite"]
            )
            adjusted[name] = _set_dispersion_values(rows, exact_linear)
        inactive = dispersion.fit_dispersion_transform(
            base_transform, adjusted["selected"], adjusted["older"], adjusted["check"]
        )
        self.assertTrue(inactive["parameters"]["dispersion_inactive"])
        for name in ("selected", "older", "check"):
            np.testing.assert_array_equal(
                inactive[name]["z_dispersion"],
                np.zeros(len(adjusted[name])),
            )

        features = list(selected[0].features)
        features[dispersion._feature_indices(dispersion.DISPERSION_FEATURES)[0]] = float("nan")
        nonfinite = [replace(selected[0], features=tuple(features)), *selected[1:]]
        with self.assertRaises(offset.InvalidDataQuality):
            dispersion.dispersion_raw(nonfinite)

        aggregate = {
            "market": {"brier": .20, "log_loss": .50},
            "ordinary": {"brier": .30, "log_loss": .70},
            "archived_attempt3": {"brier": .19, "log_loss": .48},
            "candidate": {"brier": .18, "log_loss": .47},
        }
        folds = [{
            "market": {"brier": .20}, "ordinary": {"brier": .30},
            "archived_attempt3": {"brier": .19}, "candidate": {"brier": .18},
        } for _ in range(4)]
        self.assertEqual(dispersion.diagnostic_keep(aggregate, folds)[0], "KEEP")
        worse = {**aggregate, "candidate": {"brier": .195, "log_loss": .49}}
        self.assertEqual(dispersion.diagnostic_keep(worse, folds)[0], "REVERT")
        two_wins = [dict(item) for item in folds]
        for index in (2, 3):
            two_wins[index] = {
                **two_wins[index], "archived_attempt3": {"brier": .17}
            }
        self.assertEqual(dispersion.diagnostic_keep(aggregate, two_wins)[0], "REVERT")


class DispersionEndToEndTests(unittest.TestCase):
    def _parent_archive(self, source: Path, root: Path) -> Path:
        attempt3 = all_prior_test.AllPriorEndToEndTests()._parent_archive(source, root)
        archive = root / "attempt4-archive"
        parent.run(
            source, archive, expected_events=42, expected_dates=42,
            allow_test_paths=True, minimum_recent_rows=3,
            generated_utc="2026-09-29T19:45:00+00:00",
            archived_parent_root=attempt3,
        )
        return archive

    def test_four_fits_nine_arms_archive_parity_and_no_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "synthetic-train"
            source.mkdir()
            _make_source(source, tie_index=3)
            _vary_synthetic_decision_market(source)
            _stationarize_synthetic_price_paths(source)
            with mock.patch.object(socket, "socket",
                                   side_effect=AssertionError("network used")):
                archive = self._parent_archive(source, root)
                output = root / "dispersion"
                original_fit = dispersion.fit_weighted_dispersion
                with mock.patch.object(
                        dispersion, "fit_weighted_dispersion",
                        wraps=original_fit) as fit_call, \
                        mock.patch.object(incumbent, "minimize",
                                          wraps=incumbent.minimize) as minimize_call, \
                        mock.patch.object(parent, "_fit_and_predict",
                                          side_effect=AssertionError("Attempt-4 refit")), \
                        mock.patch.object(incumbent, "_fit_and_predict",
                                          side_effect=AssertionError("Attempt-3 refit")), \
                        mock.patch.object(recent, "fit_recent_composite",
                                          side_effect=AssertionError("Attempt-2 refit")), \
                        mock.patch.object(offset, "fit_offset_ridge",
                                          side_effect=AssertionError("offset refit")), \
                        mock.patch.object(calibration.LogisticRegression, "fit",
                                          side_effect=AssertionError("ordinary refit")), \
                        mock.patch.object(calibration, "_fit_fold_models",
                                          side_effect=AssertionError("calibration refit")), \
                        mock.patch.object(prior, "_fit_fold_models",
                                          side_effect=AssertionError("Attempt-1 refit")), \
                        mock.patch.object(offset, "_fit_and_predict",
                                          side_effect=AssertionError("full-offset refit")):
                    manifest = dispersion.run(
                        source, output, expected_events=42, expected_dates=42,
                        allow_test_paths=True, minimum_recent_rows=3,
                        generated_utc="2026-09-29T19:46:00+00:00",
                        archived_parent_root=archive,
                    )
            self.assertEqual(fit_call.call_count, 4)
            self.assertEqual(minimize_call.call_count, 4)
            self.assertEqual(manifest["candidate_fits"], 4)
            self.assertEqual(manifest["control_refits"], 0)
            score = json.loads((output / "scorecard.json").read_text())
            self.assertEqual(len(score["arms"]), 9)
            self.assertEqual(set(score["arms"]), {
                "market", "ordinary", "market_only_calibration",
                "archived_full_offset", "archived_attempt1", "archived_attempt2",
                "archived_attempt3", "archived_attempt4", "candidate",
            })
            self.assertTrue(score["identical_masks"]["all_arms_share_one_complete_mask"])
            self.assertEqual(score["control_parity"]["control_refits"], 0)
            with (archive / "predictions.csv").open(newline="") as stream:
                frozen = list(csv.DictReader(stream))
            with (output / "predictions.csv").open(newline="") as stream:
                observed = list(csv.DictReader(stream))
            self.assertEqual(
                [row["all_prior_decay_candidate_probability"] for row in frozen],
                [row["all_prior_decay_candidate_probability"] for row in observed],
            )

    def test_prefit_and_optimizer_failure_receipts_are_truthful(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "synthetic-train"
            source.mkdir()
            _make_source(source, tie_index=3)
            _vary_synthetic_decision_market(source)
            _stationarize_synthetic_price_paths(source)
            archive = self._parent_archive(source, root)
            prefit = root / "prefit-invalid"
            with self.assertRaises(offset.InvalidDataQuality):
                dispersion.run(
                    source, prefit, expected_events=42, expected_dates=42,
                    allow_test_paths=True, archived_parent_root=archive,
                )
            receipt = json.loads((prefit / "failure.json").read_text())
            self.assertFalse(receipt["fit_started"])
            self.assertFalse(receipt["scoring_started"])
            failed = root / "optimizer-failed"
            with mock.patch.object(
                    dispersion, "fit_weighted_dispersion",
                    side_effect=RuntimeError("synthetic optimizer failure")):
                with self.assertRaisesRegex(RuntimeError, "optimizer failure"):
                    dispersion.run(
                        source, failed, expected_events=42, expected_dates=42,
                        allow_test_paths=True, minimum_recent_rows=3,
                        archived_parent_root=archive,
                    )
            receipt = json.loads((failed / "failure.json").read_text())
            self.assertTrue(receipt["fit_started"])
            self.assertFalse(receipt["scoring_started"])


if __name__ == "__main__":
    unittest.main()
