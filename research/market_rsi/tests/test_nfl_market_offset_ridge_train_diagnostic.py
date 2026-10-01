from __future__ import annotations

import csv
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest import mock

import numpy as np

from experiments import nfl_market_offset_ridge_train_diagnostic as offset
from experiments import nfl_settlement_probability_train_diagnostic as base
from research.market_rsi.tests.test_nfl_settlement_probability_train_diagnostic import (
    _make_source,
)


def _row(index: int, *, date_index: int | None = None,
         staleness: float = 10.0) -> base.DiagnosticRow:
    if date_index is None:
        date_index = index
    start = datetime(2025, 1, 1, 20, tzinfo=timezone.utc) + timedelta(days=date_index)
    cutoff_ms = int(start.timestamp() * 1000)
    probability = 0.25 + 0.5 * ((index % 11) / 10)
    market_logit = float(np.log(probability / (1.0 - probability)))
    features = (
        market_logit,
        staleness,
        *(float(((index + column * 3) % 17) - 8) / 8 for column in range(15)),
    )
    game_id = f"2025_{(date_index % 18) + 1:02d}_BAL_KC"
    return base.DiagnosticRow(
        game_id=game_id,
        game_date=start.date().isoformat(),
        split_date=start.date().isoformat(),
        trusted={
            "event_id": str(1000 + index),
            "market_id": str(2000 + index),
            "cutoff_ms": cutoff_ms,
            "feature_available_ms": cutoff_ms - int(staleness * 1000),
            "market_probability": probability,
            "outcome_available_ms": cutoff_ms + 60 * 60 * 1000,
            "outcome": index % 2,
        },
        features=features,
        source_receipt={"game_id": game_id},
    )


class FrozenMathTests(unittest.TestCase):
    def test_frozen_spec_hashes_match_controller_proposal(self) -> None:
        offset._validate_frozen_specs()
        identity = offset._validate_execution_identity()
        self.assertEqual(
            base._digest(dict(offset.CANDIDATE_SPEC)),
            offset.EXPECTED_CANDIDATE_SPEC_SHA256,
        )
        self.assertEqual(hashlib.sha256(Path(base.__file__).read_bytes()).hexdigest(),
                         offset.EXPECTED_PARENT_RUNNER_SHA256)
        self.assertEqual(identity["parent_test_sha256"],
                         offset.EXPECTED_PARENT_TEST_SHA256)
        self.assertEqual(identity["proper_scorer_sha256"],
                         offset.EXPECTED_PROPER_SCORER_SHA256)
        self.assertEqual(identity["probability_contract_sha256"],
                         offset.EXPECTED_PROBABILITY_CONTRACT_SHA256)
        self.assertEqual(identity["controller_proposal_sha256"],
                         offset.EXPECTED_CONTROLLER_PROPOSAL_SHA256)

    def test_analytic_gradient_matches_central_finite_difference(self) -> None:
        rng = np.random.default_rng(37)
        features = rng.normal(size=(13, 4)).astype(np.float64)
        outcomes = np.asarray([0, 1] * 6 + [1], dtype=np.float64)
        offsets = rng.normal(scale=0.7, size=13).astype(np.float64)
        parameters = rng.normal(scale=0.2, size=5).astype(np.float64)
        objective, gradient = offset.offset_objective_gradient(
            parameters, features, outcomes, offsets
        )
        self.assertTrue(np.isfinite(objective))
        epsilon = 1e-6
        numerical = np.empty_like(parameters)
        for index in range(parameters.size):
            step = np.zeros_like(parameters)
            step[index] = epsilon
            above = offset.offset_objective_gradient(
                parameters + step, features, outcomes, offsets
            )[0]
            below = offset.offset_objective_gradient(
                parameters - step, features, outcomes, offsets
            )[0]
            numerical[index] = (above - below) / (2 * epsilon)
        np.testing.assert_allclose(gradient, numerical, rtol=2e-7, atol=2e-8)

    def test_zero_residual_parameters_recover_market_probabilities(self) -> None:
        probabilities = np.asarray([0.2, 0.5, 0.675, 0.8], dtype=np.float64)
        logits = np.log(probabilities / (1.0 - probabilities))
        features = np.arange(20, dtype=np.float64).reshape(4, 5)
        result = offset.offset_probabilities(np.zeros(6), features, logits)
        np.testing.assert_array_equal(result, probabilities)

    def test_objective_uses_mean_loss_and_penalizes_intercept_and_weights(self) -> None:
        features = np.asarray([[1.0, -1.0], [3.0, 2.0]], dtype=np.float64)
        outcomes = np.asarray([0.0, 1.0], dtype=np.float64)
        offsets = np.asarray([0.2, -0.4], dtype=np.float64)
        parameters = np.asarray([0.5, -0.25, 0.75], dtype=np.float64)
        value, gradient = offset.offset_objective_gradient(
            parameters, features, outcomes, offsets
        )
        linear = offsets + parameters[0] + features @ parameters[1:]
        expected = float(np.mean(np.logaddexp(0, linear) - outcomes * linear))
        expected += 0.5 * float(parameters @ parameters)
        residual = 1.0 / (1.0 + np.exp(-linear)) - outcomes
        expected_gradient = np.r_[
            np.mean(residual), features.T @ residual / len(outcomes)
        ] + parameters
        self.assertAlmostEqual(value, expected, places=14)
        np.testing.assert_allclose(gradient, expected_gradient, rtol=0, atol=1e-14)


class IntegrityAndDecisionTests(unittest.TestCase):
    def test_check_mask_uses_scorer_canonical_order_and_rejects_key_mutation(self) -> None:
        canonical_rows = [_row(0), _row(1), _row(2)]
        noncanonical_rows = [canonical_rows[2], canonical_rows[0], canonical_rows[1]]
        expected = base._digest([
            list(row.key) for row in sorted(
                canonical_rows,
                key=lambda row: (
                    row.trusted["cutoff_ms"],
                    row.trusted["event_id"],
                    row.trusted["market_id"],
                ),
            )
        ])
        self.assertEqual(
            offset.require_expected_check_mask(noncanonical_rows, expected), expected
        )
        changed_trusted = dict(canonical_rows[1].trusted)
        changed_trusted["event_id"] = "mutated-event"
        mutated = list(noncanonical_rows)
        mutated[2] = replace(canonical_rows[1], trusted=changed_trusted)
        with self.assertRaisesRegex(ValueError, "check mask differs"):
            offset.require_expected_check_mask(mutated, expected)

    def test_staleness_600_passes_and_601_fails_closed(self) -> None:
        passing = _row(0, staleness=600)
        report = offset.staleness_inventory([passing], {passing.game_id: 0})
        offset.require_staleness_gate(report, expected_binary_rows=1)
        self.assertTrue(report["valid"])
        failing = _row(1, staleness=601)
        report = offset.staleness_inventory([failing], {failing.game_id: 1})
        with self.assertRaisesRegex(offset.InvalidDataQuality, "INVALID_DATA_QUALITY") as caught:
            offset.require_staleness_gate(report, expected_binary_rows=1)
        self.assertEqual(caught.exception.report["violations"][0]["reason"],
                         "staleness_limit_exceeded")
        self.assertEqual(caught.exception.report["actual_binary_rows_checked"], 1)

    def test_game_week_is_derived_exactly_and_rejects_bad_ids(self) -> None:
        self.assertEqual(offset.game_week("2025_08_BAL_KC"), "2025_08")
        self.assertEqual(offset.game_week("2025_14_LA_CAR"), "2025_14")
        for bad in ("2025_8_BAL_KC", "2025_08_BAL", "other"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    offset.game_week(bad)

    def test_cluster_resampling_recomputes_equal_event_not_equal_unit_mean(self) -> None:
        grouped = {"small": [10.0], "large": [1.0, 3.0]}
        observed = offset._means_for_cluster_draws(
            grouped,
            [["large", "large"], ["large", "small"], ["small", "small"]],
        )
        self.assertEqual(observed[0], 2.0)
        self.assertAlmostEqual(observed[1], 14.0 / 3.0)
        self.assertEqual(observed[2], 10.0)
        # Equal-unit averaging here would be (2 + 10) / 2 == 6, not 14/3.
        self.assertNotEqual(observed[1], 6.0)
        report = offset.cluster_resample_equal_event_delta(
            [10.0, 1.0, 3.0], ["small", "large", "large"],
            seed=23, replicates=40,
        )
        self.assertAlmostEqual(report["point_estimate"], 14.0 / 3.0)
        self.assertEqual(report["units"], 2)
        self.assertEqual(report["events"], 3)

    def test_keep_rule_requires_both_references_both_losses_and_fold_breadth(self) -> None:
        candidate = {"brier": 0.19, "log_loss": 0.56}
        market = {"brier": 0.20, "log_loss": 0.57}
        ordinary = {"brier": 0.21, "log_loss": 0.60}
        self.assertEqual(offset.diagnostic_keep(
            candidate, market, ordinary,
            [True, True, True, False], [True, True, True, False],
        )[0], "KEEP")
        tied = {"brier": market["brier"] - 5e-13, "log_loss": 0.56}
        self.assertEqual(offset.diagnostic_keep(
            tied, market, ordinary,
            [True, True, True, False], [True, True, True, False],
        )[0], "REVERT")
        self.assertEqual(offset.diagnostic_keep(
            candidate, market, ordinary,
            [True, True, False, False], [True, True, True, True],
        )[0], "REVERT")

    def test_real_exclusion_identity_includes_ordinal_date_game_and_reason(self) -> None:
        valid = [{
            "source_ordinal": 53,
            "game_id": "2025_04_GB_DAL",
            "game_date": "2025-09-28",
            "reason": "unresolved_outcome",
            "detail": "not exact",
        }]
        offset.validate_exact_real_exclusion(valid)
        for key, wrong in (
            ("source_ordinal", 52),
            ("game_id", "other"),
            ("game_date", "2025-09-29"),
            ("reason", "other"),
        ):
            changed = [dict(valid[0])]
            changed[0][key] = wrong
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "exact real exclusion"):
                    offset.validate_exact_real_exclusion(changed)

    def test_optimizer_failure_and_gradient_gate_fail_closed(self) -> None:
        features = np.asarray([[0.0], [1.0], [2.0], [3.0]], dtype=np.float64)
        outcomes = np.asarray([0, 1, 0, 1], dtype=np.float64)
        logits = np.zeros(4, dtype=np.float64)

        class Result:
            x = np.zeros(2, dtype=np.float64)
            success = False
            status = 2
            message = "synthetic optimizer failure"
            nit = 0
            nfev = 1

        with mock.patch.object(offset, "minimize", return_value=Result()):
            with self.assertRaisesRegex(RuntimeError, "optimizer failed"):
                offset.fit_offset_ridge(features, outcomes, logits)

        class BadGradientResult(Result):
            x = np.asarray([0.0, 5.0], dtype=np.float64)
            success = True
            status = 0
            message = "claims success"

        with mock.patch.object(offset, "minimize", return_value=BadGradientResult()):
            with self.assertRaisesRegex(RuntimeError, "grad_inf"):
                offset.fit_offset_ridge(features, outcomes, logits)


class FitAndEndToEndTests(unittest.TestCase):
    def test_scaler_is_fit_on_prior_fit_rows_only_and_candidate_is_deterministic(self) -> None:
        rows = [_row(index) for index in range(42)]
        folds = base.chronological_date_folds([row.split_date for row in rows])
        real_scaler = offset.StandardScaler
        seen_fit_means = []

        class TrackingScaler:
            def __init__(self) -> None:
                self._wrapped = real_scaler()

            def fit_transform(self, values: np.ndarray) -> np.ndarray:
                seen_fit_means.append(np.mean(values, axis=0))
                return self._wrapped.fit_transform(values)

            def transform(self, values: np.ndarray) -> np.ndarray:
                return self._wrapped.transform(values)

        with mock.patch.object(offset, "StandardScaler", TrackingScaler):
            first, reports = offset._fit_and_predict(rows, folds)
        second, second_reports = offset._fit_and_predict(rows, folds)
        expected_first_mean = np.mean(
            np.asarray([row.features for row in rows[:22]], dtype=np.float64), axis=0
        )
        np.testing.assert_allclose(seen_fit_means[0], expected_first_mean)
        self.assertFalse(np.allclose(
            seen_fit_means[0],
            np.mean(np.asarray([row.features for row in rows]), axis=0),
        ))
        self.assertEqual([r["fit_events"] for r in reports], [22, 27, 32, 37])
        self.assertEqual(
            [item["candidate"]["probability"] for item in first],
            [item["candidate"]["probability"] for item in second],
        )
        self.assertEqual(
            [r["optimizer"]["parameters"] for r in reports],
            [r["optimizer"]["parameters"] for r in second_reports],
        )

    def test_synthetic_runner_is_deterministic_masked_and_control_parity_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "synthetic-train"
            source.mkdir()
            _make_source(source, tie_index=3)
            first_output = root / "result-a"
            second_output = root / "result-b"
            fixed_time = "2026-09-29T17:30:00+00:00"
            with mock.patch.object(
                    socket, "socket", side_effect=AssertionError("network used")):
                first = offset.run(
                    source, first_output,
                    expected_events=42, expected_dates=42,
                    allow_test_paths=True, generated_utc=fixed_time,
                )
                second = offset.run(
                    source, second_output,
                    expected_events=42, expected_dates=42,
                    allow_test_paths=True, generated_utc=fixed_time,
                    parent_predictions_path=first_output / "predictions.csv",
                )
            self.assertEqual(first["diagnostic_decision"], second["diagnostic_decision"])
            self.assertEqual(first["check_events"], second["check_events"])
            self.assertEqual(first["model_fits"], 8)
            self.assertEqual(first["provider_cost_usd"], "0")
            score_a = json.loads((first_output / "scorecard.json").read_text())
            score_b = json.loads((second_output / "scorecard.json").read_text())
            masks = score_a["identical_masks"]
            self.assertEqual(len(set(masks.values())), 2)  # bool plus one shared digest
            self.assertTrue(masks["market_ordinary_candidate_check_keys_identical"])
            parity = score_b["control_parity"]
            self.assertTrue(parity["identity_order_mask_exact"])
            self.assertTrue(parity["market_probability_exact"])
            self.assertLessEqual(parity["maximum_ordinary_absolute_difference"], 1e-10)
            self.assertEqual(score_a["aggregate"], score_b["aggregate"])
            self.assertEqual(score_a["folds"], score_b["folds"])
            inference = score_a["corrected_grouped_inference"]
            self.assertEqual(inference["events"], 20)
            self.assertEqual(inference["schedule_dates"], 20)
            self.assertEqual(inference["game_weeks"], 20)
            self.assertEqual(
                inference["schedule_day_resample"]["candidate_minus_market"]["brier"][
                    "events"
                ],
                20,
            )
            week = inference["observed_game_week_cluster_sensitivity"]
            self.assertIn("not all clusters are complete", week["unit_definition"])
            self.assertEqual(week["right_edge_partial_week"], "2025_42")
            self.assertEqual(week["right_edge_partial_week_events"], 1)
            self.assertFalse(week["primary_denominator_changed"])
            lock = json.loads((first_output / "pre_score_lock.json").read_text())
            identity = lock["execution_identity"]
            self.assertEqual(identity["parent_runner_sha256"],
                             offset.EXPECTED_PARENT_RUNNER_SHA256)
            self.assertEqual(identity["proper_scorer_sha256"],
                             offset.EXPECTED_PROPER_SCORER_SHA256)
            self.assertEqual(identity["probability_contract_sha256"],
                             offset.EXPECTED_PROBABILITY_CONTRACT_SHA256)
            self.assertEqual(lock["incumbent_and_branch_semantics"]["ordinary_role"],
                             "ordinary reference; not Strong-Baseline-1")
            with (first_output / "predictions.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 20)

    def test_failure_receipt_marks_scoring_phase_truthfully(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "synthetic-train"
            source.mkdir()
            _make_source(source, tie_index=3)
            output = root / "result"
            one = _row(0)
            predictions = [{
                "fold": 1,
                "row": one,
                "ordinary": base._prediction_records([one], [0.55])[0],
                "candidate": base._prediction_records([one], [0.54])[0],
            }]
            reports = [{
                "fold": 1,
                "fit_events": 1,
                "check_events": 1,
                "fit_label_unavailable_events": [],
            }]
            with mock.patch.object(
                    offset, "_fit_and_predict", return_value=(predictions, reports)), \
                    mock.patch.object(base, "_score", side_effect=RuntimeError("score boom")):
                with self.assertRaisesRegex(RuntimeError, "score boom"):
                    offset.run(
                        source, output,
                        expected_events=42, expected_dates=42,
                        allow_test_paths=True,
                        generated_utc="2026-09-29T17:30:00+00:00",
                    )
            failure = json.loads((output / "failure.json").read_text())
            self.assertTrue(failure["fit_started"])
            self.assertTrue(failure["scoring_started"])

    def test_control_parity_rejects_changed_ordinary_prediction(self) -> None:
        rows = [_row(index) for index in range(42)]
        folds = base.chronological_date_folds([row.split_date for row in rows])
        predictions, _ = offset._fit_and_predict(rows, folds)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "controls.csv"
            fields = (
                "fold", "game_id", "split_date", "event_id", "market_id", "cutoff_ms",
                "outcome_available_ms", "outcome", "market_probability",
                "ordinary_probability", "candidate_probability",
            )
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for index, item in enumerate(predictions):
                    row = item["row"]
                    writer.writerow({
                        "fold": item["fold"], "game_id": row.game_id,
                        "split_date": row.split_date,
                        "event_id": row.trusted["event_id"],
                        "market_id": row.trusted["market_id"],
                        "cutoff_ms": row.trusted["cutoff_ms"],
                        "outcome_available_ms": row.trusted["outcome_available_ms"],
                        "outcome": row.trusted["outcome"],
                        "market_probability": row.trusted["market_probability"],
                        "ordinary_probability": (
                            item["ordinary"]["probability"] + (1e-8 if index == 0 else 0)
                        ),
                        "candidate_probability": item["candidate"]["probability"],
                    })
            with self.assertRaisesRegex(ValueError, "ordinary probability"):
                offset.validate_control_parity(
                    predictions, path, verify_parent_hash=False
                )


if __name__ == "__main__":
    unittest.main()
