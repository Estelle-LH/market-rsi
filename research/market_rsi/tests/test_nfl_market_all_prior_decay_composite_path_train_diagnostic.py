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

from experiments import nfl_market_all_prior_decay_composite_path_train_diagnostic as all_prior
from research.market_rsi.tests.test_nfl_market_orthogonal_price_path_train_diagnostic import (
    _nondegenerate_rows,
    _vary_synthetic_decision_market,
)
from research.market_rsi.tests.test_nfl_market_recent_composite_path_train_diagnostic import (
    _stationarize_synthetic_price_paths,
    _week_row,
)
from research.market_rsi.tests import (
    test_nfl_market_recency_weighted_composite_path_train_diagnostic as weighted_test,
)
from research.market_rsi.tests.test_nfl_settlement_probability_train_diagnostic import (
    _make_source,
)


parent = all_prior.parent
recent = all_prior.recent
base = all_prior.base
offset = all_prior.offset
calibration = all_prior.calibration
prior = all_prior.prior


class AllPriorWeightAndMathTests(unittest.TestCase):
    def test_frozen_specs_identity_and_attempt3_review_binding(self) -> None:
        all_prior._validate_frozen_specs()
        identity = all_prior._validate_execution_identity()
        self.assertEqual(
            identity["controller_proposal_sha256"],
            all_prior.EXPECTED_CONTROLLER_PROPOSAL_SHA256,
        )
        self.assertEqual(
            identity["parent_result_review_sha256"],
            "016930f4d027be2ecee79b61beb76a914eb3198cc853c632cc79d764fcceb0ad",
        )
        self.assertEqual(
            base._digest(dict(all_prior.CANDIDATE_SPEC)),
            all_prior.EXPECTED_CANDIDATE_SPEC_SHA256,
        )

    def test_all_strictly_prior_weeks_use_exact_decay_independent_of_row_order(self) -> None:
        rows = [
            _week_row(0, 3), _week_row(1, 1), _week_row(2, 2),
            _week_row(3, 3), _week_row(4, 1), _week_row(5, 2),
        ]
        weights, report = all_prior.all_prior_decay_weights(rows, "2025_04")
        np.testing.assert_array_equal(weights, [1.0, .25, .5, 1.0, .25, .5])
        self.assertEqual(tuple(report["week_weight_mapping"]),
                         ("2025_01", "2025_02", "2025_03"))
        self.assertEqual([item["events"] for item in report["per_week"]], [2, 2, 2])
        self.assertEqual(report["weight_sum"], 3.5)
        self.assertEqual(report["squared_weight_sum"], 2.625)
        self.assertAlmostEqual(report["kish_effective_rows"], 3.5 ** 2 / 2.625)
        expected_class = {
            str(label): float(np.sum(weights[np.asarray([
                row.trusted["outcome"] == label for row in rows
            ], dtype=bool)])) for label in (0, 1)
        }
        self.assertEqual(report["weight_totals_by_class"], expected_class)
        self.assertEqual(
            [item["game_id"] for item in report["eligible_event_weight_ledger"]],
            [row.game_id for row in rows],
        )
        self.assertEqual(
            [item["event_weight"] for item in report["eligible_event_weight_ledger"]],
            list(weights),
        )
        reordered = [rows[index] for index in (4, 0, 5, 1, 3, 2)]
        reordered_weights, reordered_report = all_prior.all_prior_decay_weights(
            reordered, "2025_04"
        )
        by_id = dict(zip((row.game_id for row in reordered), reordered_weights, strict=True))
        self.assertEqual(
            by_id,
            dict(zip((row.game_id for row in rows), weights, strict=True)),
        )
        self.assertEqual(reordered_report["weight_sum"], report["weight_sum"])
        cross_year = [_week_row(10, 52), _week_row(11, 1)]
        cross_year[0] = replace(cross_year[0], game_id="2024_52_BAL_KC")
        cross_year[1] = replace(cross_year[1], game_id="2025_01_BAL_KC")
        cross_weights, _ = all_prior.all_prior_decay_weights(cross_year, "2025_02")
        np.testing.assert_array_equal(cross_weights, [.5, 1.0])
        with self.assertRaises(offset.InvalidDataQuality):
            all_prior.all_prior_decay_weights(
                [*rows, _week_row(6, 4)], "2025_04"
            )
        with self.assertRaises(offset.InvalidDataQuality):
            all_prior.all_prior_decay_weights(rows, "2025_04", expected={"rows": 99})

    def test_weighted_objective_gradient_normalization_and_fit_are_exact(self) -> None:
        z = np.asarray([-1.3, -.2, .4, 1.8])
        y = np.asarray([0., 1., 0., 1.])
        market = np.asarray([.2, .45, .6, .8])
        logits = np.log(market / (1 - market))
        weights = np.asarray([.125, .25, .5, 1.])
        theta = np.asarray([.17])
        value, gradient = all_prior.weighted_objective_gradient(
            theta, z, y, logits, weights
        )
        eta = logits + theta[0] * z
        expected = np.sum(weights * (np.logaddexp(0, eta) - y * eta)) / np.sum(weights)
        expected += .5 * theta[0] ** 2
        self.assertAlmostEqual(value, float(expected), places=14)
        epsilon = 1e-6
        numerical = (
            all_prior.weighted_objective_gradient(
                theta + epsilon, z, y, logits, weights
            )[0]
            - all_prior.weighted_objective_gradient(
                theta - epsilon, z, y, logits, weights
            )[0]
        ) / (2 * epsilon)
        self.assertAlmostEqual(float(gradient[0]), float(numerical), places=8)
        scaled = all_prior.weighted_objective_gradient(
            theta, z, y, logits, weights * 19
        )
        self.assertAlmostEqual(value, scaled[0], places=14)
        np.testing.assert_allclose(gradient, scaled[1], rtol=0, atol=1e-15)
        moment = np.sum(weights * z * (y - market)) / np.sum(weights)
        gradient_zero = all_prior.weighted_objective_gradient(
            np.zeros(1), z, y, logits, weights
        )[1][0]
        self.assertAlmostEqual(float(gradient_zero), -float(moment), places=15)
        first, first_report = all_prior.fit_all_prior_decay_composite(
            z, y, logits, weights
        )
        second, second_report = all_prior.fit_all_prior_decay_composite(
            z, y, logits, weights
        )
        np.testing.assert_array_equal(first, second)
        self.assertEqual(first_report, second_report)

    def test_transform_is_bitwise_parent_and_market_nesting_is_bitwise(self) -> None:
        selected = [
            replace(row, game_id=f"2025_{5 + index % 3:02d}_BAL_KC")
            for index, row in enumerate(_nondegenerate_rows(0, 22))
        ]
        older = [
            replace(row, game_id=f"2025_{1 + index % 4:02d}_BAL_KC")
            for index, row in enumerate(_nondegenerate_rows(30, 9))
        ]
        check = _nondegenerate_rows(50, 5)
        transformed = recent.fit_recent_composite_transform(selected, older, check)
        eligible = sorted([*older, *selected], key=lambda row: row.key)
        merged = all_prior._merge_transformed_groups(
            selected, older, transformed, eligible
        )
        for field in transformed["selected"]:
            keyed = {
                row.key: value
                for rows, values in (
                    (selected, transformed["selected"][field]),
                    (older, transformed["older"][field]),
                )
                for row, value in zip(rows, values, strict=True)
            }
            np.testing.assert_array_equal(
                merged[field], np.asarray([keyed[row.key] for row in eligible])
            )
        market = np.asarray([row.trusted["market_probability"] for row in check])
        nested = recent.recent_probabilities(
            np.zeros(1), transformed["check"]["z_composite"],
            transformed["check"]["logits"], market,
        )
        self.assertTrue(np.array_equal(nested, market))
        flipped = [replace(row, trusted={
            **row.trusted, "outcome": 1 - row.trusted["outcome"]
        }) for row in check]
        changed = recent.fit_recent_composite_transform(selected, older, flipped)
        for field in transformed["check"]:
            np.testing.assert_array_equal(
                transformed["check"][field], changed["check"][field]
            )


class AllPriorEndToEndTests(unittest.TestCase):
    def _parent_archive(self, source: Path, root: Path) -> Path:
        attempt2 = weighted_test.WeightedEndToEndTests()._parent_archive(source, root)
        archive = root / "attempt3-archive"
        parent.run(
            source, archive, expected_events=42, expected_dates=42,
            allow_test_paths=True, minimum_recent_rows=3,
            generated_utc="2026-09-29T19:30:00+00:00",
            archived_parent_root=attempt2,
        )
        return archive

    def test_deterministic_four_fits_all_prior_support_zero_refits_and_no_network(self) -> None:
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
                output_a, output_b = root / "all-prior-a", root / "all-prior-b"
                original_fit = all_prior.fit_all_prior_decay_composite
                with mock.patch.object(
                        all_prior, "fit_all_prior_decay_composite",
                        wraps=original_fit) as fit_call, \
                        mock.patch.object(parent, "minimize",
                                          wraps=parent.minimize) as minimize_call, \
                        mock.patch.object(parent, "_fit_and_predict",
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
                    first = all_prior.run(
                        source, output_a, expected_events=42, expected_dates=42,
                        allow_test_paths=True, minimum_recent_rows=3,
                        generated_utc="2026-09-29T19:31:00+00:00",
                        archived_parent_root=archive,
                    )
                    self.assertEqual(fit_call.call_count, 4)
                    self.assertEqual(minimize_call.call_count, 4)
                    second = all_prior.run(
                        source, output_b, expected_events=42, expected_dates=42,
                        allow_test_paths=True, minimum_recent_rows=3,
                        generated_utc="2026-09-29T19:31:00+00:00",
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
                "archived_full_offset", "archived_attempt1", "archived_attempt2",
                "archived_attempt3", "candidate",
            })
            self.assertTrue(score_a["identical_masks"]["all_arms_share_one_complete_mask"])
            self.assertEqual(score_a["control_parity"]["control_refits"], 0)
            with (archive / "predictions.csv").open(newline="") as stream:
                frozen = list(csv.DictReader(stream))
            with (output_a / "predictions.csv").open(newline="") as stream:
                observed = list(csv.DictReader(stream))
            self.assertEqual(
                [row["recency_weighted_candidate_probability"] for row in frozen],
                [row["recency_weighted_candidate_probability"] for row in observed],
            )
            for fold in score_a["folds"]:
                report = fold["all_prior_decay_weighting"]
                self.assertEqual(
                    report["events"],
                    fold["recent_selection"]["selected_rows"]
                    + fold["recent_selection"]["older_fit_rows"],
                )
                self.assertGreater(report["events"], fold["recent_selection"]["selected_rows"])
                self.assertEqual(report["week_weight_mapping"][report["latest_eligible_week"]], 1.0)
                self.assertAlmostEqual(
                    report["gradient_at_zero"],
                    -report["weighted_mean_z_times_y_minus_market"], places=15,
                )
                self.assertTrue(report["gradient_at_zero_equals_negative_weighted_moment"])

    def test_prefit_identity_and_optimizer_failure_receipts_are_truthful(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "synthetic-train"
            source.mkdir()
            _make_source(source, tie_index=3)
            _vary_synthetic_decision_market(source)
            _stationarize_synthetic_price_paths(source)
            archive = self._parent_archive(source, root)
            identity_failure = root / "identity-failure"
            with mock.patch.object(
                    all_prior, "EXPECTED_CONTROLLER_PROPOSAL_SHA256", "0" * 64):
                with self.assertRaisesRegex(RuntimeError, "execution identity"):
                    all_prior.run(
                        source, identity_failure, expected_events=42,
                        expected_dates=42, allow_test_paths=True,
                        minimum_recent_rows=3, archived_parent_root=archive,
                    )
            identity_receipt = json.loads((identity_failure / "failure.json").read_text())
            self.assertFalse(identity_receipt["fit_started"])
            self.assertFalse(identity_receipt["scoring_started"])
            prefit = root / "prefit-invalid"
            with self.assertRaises(offset.InvalidDataQuality):
                all_prior.run(
                    source, prefit, expected_events=42, expected_dates=42,
                    allow_test_paths=True, archived_parent_root=archive,
                )
            prefit_receipt = json.loads((prefit / "failure.json").read_text())
            self.assertEqual(prefit_receipt["status"], "INVALID_DATA_QUALITY")
            self.assertFalse(prefit_receipt["fit_started"])
            self.assertFalse(prefit_receipt["scoring_started"])
            failed = root / "optimizer-failed"
            with mock.patch.object(
                    all_prior, "fit_all_prior_decay_composite",
                    side_effect=RuntimeError("synthetic optimizer failure")):
                with self.assertRaisesRegex(RuntimeError, "optimizer failure"):
                    all_prior.run(
                        source, failed, expected_events=42, expected_dates=42,
                        allow_test_paths=True, minimum_recent_rows=3,
                        archived_parent_root=archive,
                    )
            failed_receipt = json.loads((failed / "failure.json").read_text())
            self.assertTrue(failed_receipt["fit_started"])
            self.assertFalse(failed_receipt["scoring_started"])


if __name__ == "__main__":
    unittest.main()
