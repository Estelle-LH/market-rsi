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

from experiments import nfl_market_recent_composite_path_train_diagnostic as recent
from research.market_rsi.tests.test_nfl_market_offset_ridge_train_diagnostic import _row
from research.market_rsi.tests.test_nfl_market_orthogonal_price_path_train_diagnostic import (
    _nondegenerate_rows,
    _vary_synthetic_decision_market,
)
from research.market_rsi.tests.test_nfl_settlement_probability_train_diagnostic import (
    _make_source,
    _sha,
    _write_json,
)


base = recent.base
offset = recent.offset
calibration = recent.calibration
prior = recent.prior


def _week_row(index: int, week: int, *, date_index: int | None = None):
    row = _row(index, date_index=date_index)
    return replace(row, game_id=f"2025_{week:02d}_BAL_KC")


def _stationarize_synthetic_price_paths(source: Path) -> None:
    """Give every three-row recent fit a stable, nondegenerate path pattern."""
    phases = (-0.03, 0.02, -0.01, 0.04)
    for index, game_root in enumerate(sorted((source / "trades").iterdir())):
        path = game_root / "trade_window.csv"
        with path.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        decision_probability = float(rows[-3]["price"])
        rows[0]["price"] = str(decision_probability + phases[index % len(phases)])
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=base.TRADE_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        manifest_path = game_root / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["trade_window_sha256"] = _sha(path)
        _write_json(manifest_path, manifest)


class RecentSelectionTests(unittest.TestCase):
    def test_numeric_week_selection_excludes_same_check_week_and_is_label_blind(self) -> None:
        fit = []
        index = 0
        for week in (1, 2, 3, 4):
            for _ in range(4):
                fit.append(_week_row(index, week))
                index += 1
        # Outcome-known Thursday-like row in the first check week must not enter.
        fit.append(_week_row(index, 5))
        check = [_week_row(30, 5, date_index=30), _week_row(31, 6, date_index=31)]
        result = recent.select_recent_candidate_rows(fit, check, minimum_rows=3)
        self.assertEqual(
            result["report"]["selected_week_labels"], ("2025_02", "2025_03", "2025_04")
        )
        self.assertEqual(result["report"]["selected_rows"], 12)
        self.assertEqual(result["report"]["selected_rows_per_week"], (4, 4, 4))
        self.assertNotIn("2025_05_BAL_KC", [row.game_id for row in result["older_rows"]])
        self.assertIn(
            "2025_05_BAL_KC",
            [row.game_id for row in result["ineligible_same_or_later_week_rows"]],
        )
        flipped = [
            replace(row, trusted={**row.trusted, "outcome": 1 - row.trusted["outcome"]})
            for row in fit
        ]
        flipped_result = recent.select_recent_candidate_rows(
            flipped, check, minimum_rows=3
        )
        self.assertEqual(
            [row.game_id for row in result["selected_rows"]],
            [row.game_id for row in flipped_result["selected_rows"]],
        )

    def test_selection_count_class_and_invalid_week_fail_closed(self) -> None:
        check = [_week_row(30, 5, date_index=30)]
        fit = [_week_row(index, week) for index, week in enumerate((1, 2, 3))]
        with self.assertRaises(offset.InvalidDataQuality) as count_error:
            recent.select_recent_candidate_rows(fit, check, minimum_rows=4)
        self.assertEqual(
            count_error.exception.report["reason"], "fewer_than_minimum_recent_rows"
        )
        one_class = [
            replace(row, trusted={**row.trusted, "outcome": 1}) for row in fit
        ]
        with self.assertRaises(offset.InvalidDataQuality) as class_error:
            recent.select_recent_candidate_rows(one_class, check, minimum_rows=3)
        self.assertEqual(
            class_error.exception.report["reason"],
            "recent_rows_lack_both_outcome_classes",
        )
        with self.assertRaises(offset.InvalidDataQuality):
            recent._week_key("2025_2")

    def test_exact_expected_cohort_gate(self) -> None:
        fit = [_week_row(index, week) for index, week in enumerate((1, 2, 3, 4, 4, 4))]
        check = [_week_row(20, 5, date_index=20)]
        observed = recent.select_recent_candidate_rows(fit, check, minimum_rows=3)
        report = observed["report"]
        expected = {
            "weeks": report["selected_week_labels"],
            "rows": report["selected_rows"],
            "ones": report["selected_ones"],
            "zeros": report["selected_zeros"],
            "per_week": report["selected_rows_per_week"],
        }
        recent.select_recent_candidate_rows(
            fit, check, minimum_rows=3, expected=expected
        )
        with self.assertRaises(offset.InvalidDataQuality) as caught:
            recent.select_recent_candidate_rows(
                fit, check, minimum_rows=3, expected={**expected, "rows": 999}
            )
        self.assertEqual(
            caught.exception.report["reason"], "exact_real_recent_cohort_mismatch"
        )


class CompositeTransformAndMathTests(unittest.TestCase):
    def test_frozen_specs_and_identity(self) -> None:
        recent._validate_frozen_specs()
        identity = recent._validate_execution_identity()
        self.assertEqual(
            identity["controller_proposal_sha256"],
            recent.EXPECTED_CONTROLLER_PROPOSAL_SHA256,
        )
        self.assertEqual(
            identity["prior_result_review_sha256"],
            recent.EXPECTED_PRIOR_RESULT_REVIEW_SHA256,
        )
        self.assertEqual(
            base._digest(dict(recent.CANDIDATE_SPEC)),
            recent.EXPECTED_CANDIDATE_SPEC_SHA256,
        )

    def test_exact_composite_formula_and_fit_only_transform(self) -> None:
        selected = _nondegenerate_rows(0, 22)
        older = _nondegenerate_rows(30, 6)
        check = _nondegenerate_rows(40, 5)
        first = recent.fit_recent_composite_transform(selected, older, check)
        np.testing.assert_allclose(
            first["selected"]["composite_raw"],
            np.mean(first["selected"]["z_family"], axis=1),
            rtol=0, atol=0,
        )
        self.assertAlmostEqual(
            float(np.mean(first["selected"]["z_composite"])), 0.0, places=14
        )
        self.assertAlmostEqual(
            float(np.std(first["selected"]["z_composite"])), 1.0, places=14
        )
        orthogonality = first["parameters"]["selected_fit_residual_orthogonality"]
        self.assertLess(max(orthogonality["absolute_residual_means_g_d"]), 1e-12)
        self.assertLess(
            max(orthogonality["absolute_mean_z_market_times_residual_g_d"]),
            1e-12,
        )
        diagnostics = recent.information_diagnostics(first["selected"], selected)
        self.assertIn("raw_composite_variance", diagnostics["composite"])
        self.assertIn(
            "residual_over_raw_composite_variance_fraction",
            diagnostics["composite"],
        )
        self.assertIn(
            "residual_composite_correlation_with_market_logit",
            diagnostics["composite"],
        )
        changed_older = [
            replace(row, features=(
                        row.features[0],
                        *(value + 1000 for value in row.features[1:]),
                    ),
                    trusted={**row.trusted, "outcome": 1 - row.trusted["outcome"]})
            for row in older
        ]
        changed_check = [
            replace(row, trusted={**row.trusted, "outcome": 1 - row.trusted["outcome"]})
            for row in check
        ]
        second = recent.fit_recent_composite_transform(
            selected, changed_older, changed_check
        )
        self.assertEqual(first["parameters"], second["parameters"])
        np.testing.assert_array_equal(
            first["selected"]["z_composite"], second["selected"]["z_composite"]
        )
        np.testing.assert_array_equal(
            first["check"]["z_composite"], second["check"]["z_composite"]
        )

    def test_one_parameter_objective_gradient_and_zero_market_recovery(self) -> None:
        z = np.asarray([-1.3, -0.2, 0.4, 1.8], dtype=np.float64)
        outcomes = np.asarray([0, 1, 0, 1], dtype=np.float64)
        market = np.asarray([.2, .45, .6, .8], dtype=np.float64)
        logits = np.log(market / (1 - market))
        theta = np.asarray([.17])
        value, gradient = recent.recent_objective_gradient(
            theta, z, outcomes, logits
        )
        eta = logits + theta[0] * z
        expected = np.mean(np.logaddexp(0, eta) - outcomes * eta) + .5 * theta[0] ** 2
        self.assertAlmostEqual(value, expected, places=14)
        epsilon = 1e-6
        numerical = (
            recent.recent_objective_gradient(theta + epsilon, z, outcomes, logits)[0]
            - recent.recent_objective_gradient(theta - epsilon, z, outcomes, logits)[0]
        ) / (2 * epsilon)
        self.assertAlmostEqual(float(gradient[0]), float(numerical), places=8)
        np.testing.assert_allclose(
            recent.recent_probabilities(np.zeros(1), z, logits, market), market,
            rtol=0, atol=0,
        )
        self.assertTrue(np.array_equal(
            recent.recent_probabilities(np.zeros(1), z, logits, market), market
        ))

    def test_fit_is_deterministic_and_check_labels_cannot_change_predictions(self) -> None:
        selected = _nondegenerate_rows(0, 22)
        older = _nondegenerate_rows(30, 6)
        check = _nondegenerate_rows(40, 5)
        transform = recent.fit_recent_composite_transform(selected, older, check)
        y = np.asarray([row.trusted["outcome"] for row in selected])
        first, first_report = recent.fit_recent_composite(
            transform["selected"]["z_composite"], y,
            transform["selected"]["logits"],
        )
        second, second_report = recent.fit_recent_composite(
            transform["selected"]["z_composite"], y,
            transform["selected"]["logits"],
        )
        np.testing.assert_array_equal(first, second)
        self.assertEqual(first_report, second_report)
        values = recent.recent_probabilities(
            first, transform["check"]["z_composite"], transform["check"]["logits"],
            [row.trusted["market_probability"] for row in check],
        )
        flipped = [
            replace(row, trusted={**row.trusted, "outcome": 1 - row.trusted["outcome"]})
            for row in check
        ]
        changed = recent.fit_recent_composite_transform(selected, older, flipped)
        np.testing.assert_array_equal(
            values,
            recent.recent_probabilities(
                first, changed["check"]["z_composite"], changed["check"]["logits"],
                [row.trusted["market_probability"] for row in flipped],
            ),
        )

    def test_diagnostics_are_non_gating(self) -> None:
        selected = _nondegenerate_rows(0, 22)
        older = _nondegenerate_rows(30, 6)
        check = _nondegenerate_rows(40, 5)
        transformed = recent.fit_recent_composite_transform(selected, older, check)
        y = np.asarray([row.trusted["outcome"] for row in selected])
        parameter, _ = recent.fit_recent_composite(
            transformed["selected"]["z_composite"], y,
            transformed["selected"]["logits"],
        )
        before = recent.recent_probabilities(
            parameter, transformed["check"]["z_composite"],
            transformed["check"]["logits"],
            [row.trusted["market_probability"] for row in check],
        )
        with mock.patch.object(recent, "information_diagnostics",
                               return_value={"tampered": True}):
            after = recent.recent_probabilities(
                parameter, transformed["check"]["z_composite"],
                transformed["check"]["logits"],
                [row.trusted["market_probability"] for row in check],
            )
        np.testing.assert_array_equal(before, after)

    def test_out_of_policy_candidate_probability_is_rejected_not_clipped(self) -> None:
        row = _nondegenerate_rows(0, 1)[0]
        with self.assertRaisesRegex(ValueError, "epsilon policy"):
            base._prediction_records([row], [1.0 - 0.5e-6])


class RecentEndToEndTests(unittest.TestCase):
    def _prior_archive(self, source: Path, root: Path) -> Path:
        first, full = root / "offset-a", root / "offset-archive"
        fixed = "2026-09-29T18:00:00+00:00"
        offset.run(source, first, expected_events=42, expected_dates=42,
                   allow_test_paths=True, generated_utc=fixed)
        offset.run(
            source, full, expected_events=42, expected_dates=42,
            allow_test_paths=True, generated_utc=fixed,
            parent_predictions_path=first / "predictions.csv",
        )
        cal = root / "calibration-archive"
        calibration.run(
            source, cal, expected_events=42, expected_dates=42,
            allow_test_paths=True, generated_utc=fixed,
            archived_offset_root=full,
        )
        archive = root / "attempt1-archive"
        prior.run(
            source, archive, expected_events=42, expected_dates=42,
            allow_test_paths=True, generated_utc=fixed,
            archived_calibration_root=cal,
        )
        return archive

    def test_deterministic_four_fits_all_controls_archive_only_and_no_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "synthetic-train"
            source.mkdir()
            _make_source(source, tie_index=3)
            _vary_synthetic_decision_market(source)
            _stationarize_synthetic_price_paths(source)
            with mock.patch.object(
                    socket, "socket", side_effect=AssertionError("network used")):
                archive = self._prior_archive(source, root)
                output_a, output_b = root / "recent-a", root / "recent-b"
                original_fit = recent.fit_recent_composite
                with mock.patch.object(
                        recent, "fit_recent_composite", wraps=original_fit) as fit_call, \
                        mock.patch.object(
                            recent, "minimize", wraps=recent.minimize
                        ) as minimize_call, \
                        mock.patch.object(
                            offset, "fit_offset_ridge",
                            side_effect=AssertionError("control offset refit"),
                        ), mock.patch.object(
                            calibration.LogisticRegression, "fit",
                            side_effect=AssertionError("ordinary refit"),
                        ), mock.patch.object(
                            calibration, "_fit_fold_models",
                            side_effect=AssertionError("calibration control refit"),
                        ), mock.patch.object(
                            prior, "_fit_fold_models",
                            side_effect=AssertionError("Attempt-1 control refit"),
                        ), mock.patch.object(
                            offset, "_fit_and_predict",
                            side_effect=AssertionError("full-offset control refit"),
                        ):
                    first = recent.run(
                        source, output_a, expected_events=42, expected_dates=42,
                        allow_test_paths=True, minimum_recent_rows=3,
                        generated_utc="2026-09-29T18:01:00+00:00",
                        archived_prior_root=archive,
                    )
                    self.assertEqual(fit_call.call_count, 4)
                    self.assertEqual(minimize_call.call_count, 4)
                    second = recent.run(
                        source, output_b, expected_events=42, expected_dates=42,
                        allow_test_paths=True, minimum_recent_rows=3,
                        generated_utc="2026-09-29T18:01:00+00:00",
                        archived_prior_root=archive,
                    )
                    self.assertEqual(fit_call.call_count, 8)
                    self.assertEqual(minimize_call.call_count, 8)
            self.assertEqual(first, second)
            self.assertEqual(first["model_fits"], 4)
            self.assertEqual(first["candidate_fits"], 4)
            self.assertEqual(first["control_refits"], 0)
            score_a = json.loads((output_a / "scorecard.json").read_text())
            score_b = json.loads((output_b / "scorecard.json").read_text())
            self.assertEqual(score_a, score_b)
            self.assertEqual(set(score_a["arms"]), {
                "market", "ordinary", "market_only_calibration",
                "archived_full_offset", "archived_attempt1", "candidate",
            })
            self.assertTrue(score_a["identical_masks"]["all_arms_share_one_complete_mask"])
            self.assertEqual(score_a["control_parity"]["control_refits"], 0)
            self.assertEqual(score_a["corrected_grouped_inference"]["events"], 20)
            with (archive / "predictions.csv").open(newline="") as stream:
                frozen = list(csv.DictReader(stream))
            with (output_a / "predictions.csv").open(newline="") as stream:
                observed = list(csv.DictReader(stream))
            self.assertEqual(
                [row["candidate_probability"] for row in frozen],
                [row["candidate_probability"] for row in observed],
            )

    def test_recent_count_failure_persists_structured_invalid_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "synthetic-train"
            source.mkdir()
            _make_source(source, tie_index=3)
            _vary_synthetic_decision_market(source)
            archive = self._prior_archive(source, root)
            output = root / "recent-invalid"
            with self.assertRaises(offset.InvalidDataQuality):
                recent.run(
                    source, output, expected_events=42, expected_dates=42,
                    allow_test_paths=True,
                    generated_utc="2026-09-29T18:02:00+00:00",
                    archived_prior_root=archive,
                )
            failure = json.loads((output / "failure.json").read_text())
            self.assertEqual(failure["status"], "INVALID_DATA_QUALITY")
            self.assertEqual(
                failure["data_quality_report"]["reason"],
                "fewer_than_minimum_recent_rows",
            )
            self.assertFalse(failure["fit_started"])
            self.assertFalse(failure["scoring_started"])

            rank_output = root / "recent-rank-invalid"
            rank_error = offset.InvalidDataQuality(
                "INVALID_DATA_QUALITY: synthetic rank failure",
                {"schema": "test", "status": "INVALID_DATA_QUALITY",
                 "reason": "synthetic_rank_failure"},
            )
            with mock.patch.object(
                    recent, "fit_recent_composite_transform", side_effect=rank_error):
                with self.assertRaises(offset.InvalidDataQuality):
                    recent.run(
                        source, rank_output, expected_events=42, expected_dates=42,
                        allow_test_paths=True, minimum_recent_rows=3,
                        generated_utc="2026-09-29T18:02:00+00:00",
                        archived_prior_root=archive,
                    )
            rank_failure = json.loads((rank_output / "failure.json").read_text())
            self.assertFalse(rank_failure["fit_started"])
            self.assertFalse(rank_failure["scoring_started"])

            fit_output = root / "recent-fit-failed"
            with mock.patch.object(
                    recent, "fit_recent_composite",
                    side_effect=RuntimeError("synthetic optimizer failure")):
                with self.assertRaisesRegex(RuntimeError, "optimizer failure"):
                    recent.run(
                        source, fit_output, expected_events=42, expected_dates=42,
                        allow_test_paths=True, minimum_recent_rows=3,
                        generated_utc="2026-09-29T18:02:00+00:00",
                        archived_prior_root=archive,
                    )
            fit_failure = json.loads((fit_output / "failure.json").read_text())
            self.assertTrue(fit_failure["fit_started"])
            self.assertFalse(fit_failure["scoring_started"])

    def test_execution_identity_drift_gets_a_prefit_failure_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "synthetic-train"
            source.mkdir()
            _make_source(source, tie_index=3)
            output = root / "identity-invalid"
            with mock.patch.object(
                    recent, "_validate_execution_identity",
                    side_effect=RuntimeError("synthetic identity drift")):
                with self.assertRaisesRegex(RuntimeError, "identity drift"):
                    recent.run(
                        source, output, expected_events=42, expected_dates=42,
                        allow_test_paths=True,
                        archived_prior_root=root / "never-read-archive",
                    )
            failure = json.loads((output / "failure.json").read_text())
            self.assertEqual(failure["status"], "FAILED")
            self.assertFalse(failure["fit_started"])
            self.assertFalse(failure["scoring_started"])


if __name__ == "__main__":
    unittest.main()
