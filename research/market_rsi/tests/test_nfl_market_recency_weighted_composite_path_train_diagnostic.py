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

from experiments import nfl_market_recency_weighted_composite_path_train_diagnostic as weighted
from research.market_rsi.tests.test_nfl_market_orthogonal_price_path_train_diagnostic import (
    _nondegenerate_rows,
    _vary_synthetic_decision_market,
)
from research.market_rsi.tests import (
    test_nfl_market_recent_composite_path_train_diagnostic as recent_test,
)
from research.market_rsi.tests.test_nfl_market_recent_composite_path_train_diagnostic import (
    _stationarize_synthetic_price_paths, _week_row,
)
from research.market_rsi.tests.test_nfl_settlement_probability_train_diagnostic import (
    _make_source,
)


parent = weighted.parent
base = weighted.base
offset = weighted.offset
calibration = weighted.calibration
prior = weighted.prior


class WeightAndMathTests(unittest.TestCase):
    def test_frozen_specs_identity_and_parent_archive_binding(self) -> None:
        weighted._validate_frozen_specs()
        identity = weighted._validate_execution_identity()
        self.assertEqual(
            identity["controller_proposal_sha256"],
            weighted.EXPECTED_CONTROLLER_PROPOSAL_SHA256,
        )
        self.assertEqual(
            identity["parent_result_review_sha256"],
            weighted.EXPECTED_PARENT_RESULT_REVIEW_SHA256,
        )
        self.assertEqual(
            base._digest(dict(weighted.CANDIDATE_SPEC)),
            weighted.EXPECTED_CANDIDATE_SPEC_SHA256,
        )

    def test_weight_mapping_uses_week_labels_not_row_order_and_reports_totals(self) -> None:
        rows = [
            _week_row(0, 7), _week_row(1, 5), _week_row(2, 6),
            _week_row(3, 7), _week_row(4, 6), _week_row(5, 7),
        ]
        values, report = weighted.recency_weights(
            rows, ("2025_05", "2025_06", "2025_07"), expected_total=4.25
        )
        np.testing.assert_array_equal(values, [1.0, .25, .5, 1.0, .5, 1.0])
        self.assertEqual([item["events"] for item in report["per_week"]], [1, 2, 3])
        self.assertEqual(report["weight_sum"], 4.25)
        self.assertEqual(report["squared_weight_sum"], 3.5625)
        self.assertAlmostEqual(report["kish_effective_rows"], 4.25 ** 2 / 3.5625)
        self.assertEqual(report["weight_totals_by_class"], {"0": 2.0, "1": 2.25})
        self.assertEqual(
            [item["ordinal"] for item in report["selected_event_weight_ledger"]],
            list(range(6)),
        )
        self.assertEqual(
            [item["game_id"] for item in report["selected_event_weight_ledger"]],
            [row.game_id for row in rows],
        )
        self.assertEqual(
            [item["event_weight"] for item in report["selected_event_weight_ledger"]],
            list(values),
        )
        with self.assertRaises(offset.InvalidDataQuality):
            weighted.recency_weights(rows, ("2025_07", "2025_06", "2025_05"))
        with self.assertRaises(offset.InvalidDataQuality):
            weighted.recency_weights(rows, ("2025_05", "2025_06", "2025_07"),
                                     expected_total=99.0)

    def test_weighted_objective_gradient_scale_invariance_and_grad_zero_identity(self) -> None:
        z = np.asarray([-1.3, -.2, .4, 1.8])
        y = np.asarray([0., 1., 0., 1.])
        market = np.asarray([.2, .45, .6, .8])
        logits = np.log(market / (1 - market))
        weights = np.asarray([.25, .5, 1., 1.])
        theta = np.asarray([.17])
        value, gradient = weighted.weighted_objective_gradient(
            theta, z, y, logits, weights
        )
        eta = logits + theta[0] * z
        expected = np.sum(weights * (np.logaddexp(0, eta) - y * eta)) / np.sum(weights)
        expected += .5 * theta[0] ** 2
        self.assertAlmostEqual(value, float(expected), places=14)
        epsilon = 1e-6
        numerical = (
            weighted.weighted_objective_gradient(theta + epsilon, z, y, logits, weights)[0]
            - weighted.weighted_objective_gradient(theta - epsilon, z, y, logits, weights)[0]
        ) / (2 * epsilon)
        self.assertAlmostEqual(float(gradient[0]), float(numerical), places=8)
        scaled = weighted.weighted_objective_gradient(theta, z, y, logits, weights * 17)
        self.assertAlmostEqual(value, scaled[0], places=14)
        np.testing.assert_allclose(gradient, scaled[1], rtol=0, atol=1e-15)
        gradient_zero = weighted.weighted_objective_gradient(
            np.zeros(1), z, y, logits, weights
        )[1][0]
        moment = np.sum(weights * z * (y - market)) / np.sum(weights)
        self.assertAlmostEqual(float(gradient_zero), -float(moment), places=15)

    def test_transform_is_exact_parent_and_fit_is_deterministic(self) -> None:
        selected = _nondegenerate_rows(0, 22)
        older = _nondegenerate_rows(30, 6)
        check = _nondegenerate_rows(40, 5)
        first = parent.fit_recent_composite_transform(selected, older, check)
        second = parent.fit_recent_composite_transform(selected, older, check)
        for group in ("selected", "older", "check"):
            for key in first[group]:
                np.testing.assert_array_equal(first[group][key], second[group][key])
        labels = np.asarray([row.trusted["outcome"] for row in selected])
        weeks = ("2025_05", "2025_06", "2025_07")
        weighted_rows = [replace(row, game_id=f"2025_{5 + index % 3:02d}_BAL_KC")
                         for index, row in enumerate(selected)]
        weights, _ = weighted.recency_weights(weighted_rows, weeks)
        a, ar = weighted.fit_weighted_composite(
            first["selected"]["z_composite"], labels,
            first["selected"]["logits"], weights,
        )
        b, br = weighted.fit_weighted_composite(
            first["selected"]["z_composite"], labels,
            first["selected"]["logits"], weights,
        )
        np.testing.assert_array_equal(a, b)
        self.assertEqual(ar, br)
        market = np.asarray([row.trusted["market_probability"] for row in check])
        nested = parent.recent_probabilities(
            np.zeros(1), first["check"]["z_composite"],
            first["check"]["logits"], market,
        )
        self.assertTrue(np.array_equal(nested, market))
        flipped = [replace(row, trusted={**row.trusted,
                                         "outcome": 1 - row.trusted["outcome"]})
                   for row in check]
        changed = parent.fit_recent_composite_transform(selected, older, flipped)
        np.testing.assert_array_equal(
            first["check"]["z_composite"], changed["check"]["z_composite"]
        )


class WeightedEndToEndTests(unittest.TestCase):
    def _parent_archive(self, source: Path, root: Path) -> Path:
        attempt1 = recent_test.RecentEndToEndTests()._prior_archive(source, root)
        archive = root / "attempt2-archive"
        parent.run(
            source, archive, expected_events=42, expected_dates=42,
            allow_test_paths=True, minimum_recent_rows=3,
            generated_utc="2026-09-29T19:00:00+00:00",
            archived_prior_root=attempt1,
        )
        return archive

    def test_deterministic_four_fits_zero_control_refits_archive_parity_and_no_network(self) -> None:
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
                output_a, output_b = root / "weighted-a", root / "weighted-b"
                original_fit = weighted.fit_weighted_composite
                with mock.patch.object(
                        weighted, "fit_weighted_composite", wraps=original_fit) as fit_call, \
                        mock.patch.object(weighted, "minimize", wraps=weighted.minimize) as minimize_call, \
                        mock.patch.object(parent, "fit_recent_composite",
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
                    first = weighted.run(
                        source, output_a, expected_events=42, expected_dates=42,
                        allow_test_paths=True, minimum_recent_rows=3,
                        generated_utc="2026-09-29T19:01:00+00:00",
                        archived_parent_root=archive,
                    )
                    self.assertEqual(fit_call.call_count, 4)
                    self.assertEqual(minimize_call.call_count, 4)
                    second = weighted.run(
                        source, output_b, expected_events=42, expected_dates=42,
                        allow_test_paths=True, minimum_recent_rows=3,
                        generated_utc="2026-09-29T19:01:00+00:00",
                        archived_parent_root=archive,
                    )
                    self.assertEqual(fit_call.call_count, 8)
                    self.assertEqual(minimize_call.call_count, 8)
            self.assertEqual(first, second)
            self.assertEqual(first["candidate_fits"], 4)
            self.assertEqual(first["control_refits"], 0)
            score_a = json.loads((output_a / "scorecard.json").read_text())
            score_b = json.loads((output_b / "scorecard.json").read_text())
            self.assertEqual(score_a, score_b)
            self.assertEqual(set(score_a["arms"]), {
                "market", "ordinary", "market_only_calibration",
                "archived_full_offset", "archived_attempt1",
                "archived_attempt2", "candidate",
            })
            self.assertTrue(score_a["identical_masks"]["all_arms_share_one_complete_mask"])
            self.assertEqual(score_a["control_parity"]["control_refits"], 0)
            with (archive / "predictions.csv").open(newline="") as stream:
                frozen = list(csv.DictReader(stream))
            with (output_a / "predictions.csv").open(newline="") as stream:
                observed = list(csv.DictReader(stream))
            self.assertEqual(
                [row["recent_composite_candidate_probability"] for row in frozen],
                [row["recent_composite_candidate_probability"] for row in observed],
            )
            for fold in score_a["folds"]:
                report = fold["recency_weighting"]
                self.assertAlmostEqual(
                    report["gradient_at_zero"],
                    -report["weighted_mean_z_times_y_minus_market"], places=15,
                )
                self.assertTrue(report["gradient_at_zero_equals_negative_weighted_moment"])

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
                weighted.run(
                    source, prefit, expected_events=42, expected_dates=42,
                    allow_test_paths=True, archived_parent_root=archive,
                )
            prefit_receipt = json.loads((prefit / "failure.json").read_text())
            self.assertFalse(prefit_receipt["fit_started"])
            self.assertFalse(prefit_receipt["scoring_started"])
            failed = root / "optimizer-failed"
            with mock.patch.object(
                    weighted, "fit_weighted_composite",
                    side_effect=RuntimeError("synthetic optimizer failure")):
                with self.assertRaisesRegex(RuntimeError, "optimizer failure"):
                    weighted.run(
                        source, failed, expected_events=42, expected_dates=42,
                        allow_test_paths=True, minimum_recent_rows=3,
                        archived_parent_root=archive,
                    )
            failed_receipt = json.loads((failed / "failure.json").read_text())
            self.assertTrue(failed_receipt["fit_started"])
            self.assertFalse(failed_receipt["scoring_started"])


if __name__ == "__main__":
    unittest.main()
