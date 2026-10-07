from __future__ import annotations

import math
import os
import unittest
from unittest import mock

import numpy as np

from experiments import nfl_ingame_identity_anchored_market_calibration as candidate
from experiments import nfl_ingame_win_probability_train_diagnostic as base


class IdentityAnchoredMarketCalibrationTests(unittest.TestCase):
    def test_objective_gradient_hessian_and_penalty_are_exact(self) -> None:
        logits = np.asarray([-1.1, -0.2, 0.4, 1.3])
        z_market = np.asarray([-1.2, -0.3, 0.5, 1.0])
        outcomes = np.asarray([0, 1, 0, 1], dtype=float)
        theta = np.asarray([0.17, -0.23])
        value, gradient, hessian = candidate.identity_objective_gradient_hessian(
            theta, logits, z_market, outcomes
        )
        eta = logits + theta[0] + theta[1] * z_market
        expected = float(np.sum(np.logaddexp(0, eta) - outcomes * eta))
        expected += 0.5 * 16 * float(theta @ theta)
        self.assertAlmostEqual(value, expected, places=13)
        epsilon = 1e-6
        numerical_gradient = []
        numerical_hessian = []
        for index in range(2):
            upper, lower = theta.copy(), theta.copy()
            upper[index] += epsilon
            lower[index] -= epsilon
            high = candidate.identity_objective_gradient_hessian(
                upper, logits, z_market, outcomes
            )
            low = candidate.identity_objective_gradient_hessian(
                lower, logits, z_market, outcomes
            )
            numerical_gradient.append((high[0] - low[0]) / (2 * epsilon))
            numerical_hessian.append((high[1] - low[1]) / (2 * epsilon))
        np.testing.assert_allclose(gradient, numerical_gradient, atol=1e-8, rtol=1e-7)
        np.testing.assert_allclose(
            hessian, np.asarray(numerical_hessian).T, atol=1e-7, rtol=1e-7
        )
        self.assertTrue(np.all(np.linalg.eigvalsh(hessian) >= 16))

    def test_fit_only_standardization_never_uses_check_distribution(self) -> None:
        fit = np.asarray([0.1, 0.2, 0.7, 0.9])
        check = np.asarray([0.3, 0.8])
        z_fit, z_check, report = candidate.fit_only_market_standardization(fit, check)
        changed = np.asarray([0.000001, 0.999999])
        changed_fit, changed_check, changed_report = (
            candidate.fit_only_market_standardization(fit, changed)
        )
        np.testing.assert_array_equal(z_fit, changed_fit)
        self.assertEqual(report, changed_report)
        self.assertFalse(np.array_equal(z_check, changed_check))
        self.assertAlmostEqual(float(z_fit.mean()), 0.0, places=15)
        self.assertAlmostEqual(float(z_fit.std(ddof=0)), 1.0, places=15)
        with self.assertRaisesRegex(ValueError, "zero or invalid scale"):
            candidate.fit_only_market_standardization([0.5, 0.5], [0.4])

    def test_damped_newton_is_deterministic_converged_and_no_retry(self) -> None:
        probabilities = np.asarray([
            0.08, 0.14, 0.22, 0.31, 0.42, 0.55, 0.67, 0.76, 0.85, 0.93,
        ])
        outcomes = np.asarray([0, 0, 0, 1, 0, 1, 1, 0, 1, 1])
        first = candidate.fit_identity_anchored(probabilities, outcomes)
        second = candidate.fit_identity_anchored(probabilities, outcomes)
        np.testing.assert_array_equal(first[0], second[0])
        self.assertEqual(first[1:], second[1:])
        self.assertLessEqual(first[2]["iterations"], 50)
        self.assertLessEqual(first[2]["gradient_infinity_norm"], 1e-8)
        self.assertEqual(first[2]["retry_count"], 0)
        self.assertEqual(first[2]["penalty"], 16.0)

    def test_four_outer_fits_and_all_frozen_arms_share_each_check_row(self) -> None:
        rows, folds, controls = [], [], {}
        for fold in range(1, 5):
            fit_date, check_date = f"2025-01-{fold * 2 - 1:02d}", f"2025-01-{fold * 2:02d}"
            folds.append({"fold": fold, "fit_dates": [fit_date], "check_dates": [check_date]})
            for kind, game_date, base_time in (
                ("fit", fit_date, fold * 10_000), ("check", check_date, fold * 10_000 + 5_000)
            ):
                for outcome in (0, 1):
                    game_id = f"2025_{fold:02d}_{kind}_{outcome}"
                    cutoff = base_time + outcome
                    probability = .30 + .35 * outcome
                    trusted = {
                        "event_id": game_id, "market_id": f"market-{game_id}",
                        "cutoff_ms": cutoff, "feature_available_ms": cutoff,
                        "market_probability": probability,
                        "outcome_available_ms": (
                            cutoff + 1 if kind == "check" else fold * 10_000 + 100
                        ),
                        "outcome": outcome,
                    }
                    row = base.InGameRow(
                        game_id=game_id, game_date=game_date, game_week=str(fold),
                        trusted=trusted,
                        market_features=(math.log(probability / (1 - probability)),),
                        state_features=(), source_receipt={},
                    )
                    rows.append(row)
                    if kind == "check":
                        controls[row.key] = {
                            "fold": fold, "game_id": game_id,
                            "game_date": game_date, "game_week": str(fold),
                            "outcome": outcome, candidate.ARM_RAW: probability,
                            candidate.ARM_ORDINARY: probability + .01,
                            candidate.ARM_PARENT: probability - .01,
                        }
        calls = []

        def fake_fit(probabilities, outcomes):
            calls.append((tuple(probabilities), tuple(outcomes)))
            return np.zeros(2), {"fit_logit_mean": 0.0, "fit_logit_scale": 1.0}, {
                "converged": True, "iterations": 0, "retry_count": 0,
            }

        with mock.patch.object(candidate, "fit_identity_anchored", side_effect=fake_fit):
            predictions, reports = candidate._fit_and_predict(rows, folds, controls)
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(reports), 4)
        self.assertEqual(len(predictions), 8)
        self.assertEqual(set(item["row"].key for item in predictions), set(controls))
        self.assertTrue(all(item[candidate.ARM_ORDINARY]
                            == controls[item["row"].key][candidate.ARM_ORDINARY]
                            for item in predictions))
        self.assertTrue(all(item[candidate.ARM_PARENT]
                            == controls[item["row"].key][candidate.ARM_PARENT]
                            for item in predictions))

    def test_candidate_is_exact_identity_at_zero_adjustment(self) -> None:
        values = np.asarray([0.01, 0.2, 0.55, 0.9, 0.999])
        _, _, scaling = candidate.fit_only_market_standardization(values, values)
        actual = candidate.identity_probabilities(np.zeros(2), values, scaling)
        np.testing.assert_allclose(actual, values, atol=1e-15, rtol=0)

    def test_controller_bindings_and_frozen_v0_mask_pass_without_fit(self) -> None:
        candidate._require_dependencies()
        frozen = candidate.frozen_v0._validate_v0_artifact(
            candidate.V0_ARTIFACT_ROOT
        )
        controls = candidate._frozen_controls(frozen)
        self.assertEqual(len(controls), 87)
        self.assertEqual(
            candidate._digest([list(key) for key in controls]),
            candidate.EXPECTED_CHECK_KEY_SHA256,
        )
        self.assertEqual(candidate.MODEL_FITS, 4)
        self.assertEqual(candidate.COMPONENT_SPEC_DIGEST,
                         "128321cc21f68b649b7e631c1f29891e3b9dbca4190aa11dc6e7d37b096623d4")
        self.assertEqual(
            candidate._digest(candidate.SCHEDULER_BRANCH_BINDING),
            candidate.SCHEDULER_BRANCH_BINDING_SHA256,
        )
        self.assertEqual(
            candidate._digest(candidate.COMPONENT_SPEC),
            candidate.IMPLEMENTATION_COMPONENT_SPEC_SHA256,
        )

    def test_exact_decision_support_refute_and_inconclusive(self) -> None:
        def aggregate(candidate_brier=.18, candidate_log=.48):
            return {
                candidate.ARM_RAW: {"brier": .20, "log_loss": .52},
                candidate.ARM_ORDINARY: {"brier": .21, "log_loss": .54},
                candidate.ARM_PARENT: {"brier": .205, "log_loss": .53},
                candidate.ARM_CANDIDATE: {
                    "brier": candidate_brier, "log_loss": candidate_log,
                },
            }

        def folds(raw_wins: int, ordinary_wins: int):
            result = []
            for index in range(4):
                result.append({"arms": {
                    candidate.ARM_RAW: {"brier": .20},
                    candidate.ARM_ORDINARY: {"brier": .21},
                    candidate.ARM_CANDIDATE: {
                        "brier": .19 if index < raw_wins else (
                            .205 if index < ordinary_wins else .22
                        )
                    },
                }})
            return result

        def paired(upper: float):
            return {f"candidate_minus_{candidate.ARM_RAW}": {"brier": {
                "schedule_date_interval": {"interval_95": [-.04, upper]},
                "observed_game_week_interval": {"interval_95": [-.05, upper]},
            }}}

        self.assertEqual(candidate.calibration_decision(
            aggregate(), folds(3, 3), paired(-.001)
        )[0], "IDENTITY_ANCHORED_MARKET_CALIBRATION_KEEP")
        self.assertEqual(candidate.calibration_decision(
            aggregate(.201, .48), folds(1, 3), paired(.01)
        )[0], "IDENTITY_ANCHORED_MARKET_CALIBRATION_REFUTED_REVERT")
        self.assertEqual(candidate.calibration_decision(
            aggregate(), folds(2, 3), paired(.01)
        )[0], "IDENTITY_ANCHORED_MARKET_CALIBRATION_INCONCLUSIVE_REVERT")

    def test_paired_evidence_wires_three_comparators_date_week_10k(self) -> None:
        records = []
        for index in range(4):
            record = {
                "game_id": f"g{index}", "game_date": f"2025-01-0{index + 1}",
                "game_week": str(index // 2 + 1),
            }
            for arm in (candidate.ARM_RAW, candidate.ARM_ORDINARY, candidate.ARM_PARENT):
                for metric in ("brier", "log_loss"):
                    record[f"candidate_minus_{arm}_{metric}"] = (index - 1.5) / 100
            records.append(record)
        calls = []

        def fake(rows, group, value, *, seed, replicates):
            calls.append((group, value, seed, replicates, len(rows)))
            return {"interval_95": [-.1, .1]}

        with mock.patch.object(candidate.base, "_group_bootstrap", side_effect=fake):
            evidence = candidate._paired_evidence(records)
        self.assertEqual(len(evidence), 3)
        self.assertEqual(len(calls), 12)
        self.assertEqual({item[0] for item in calls}, {"game_date", "game_week"})
        self.assertTrue(all(item[2:] == (20260929, 10_000, 4) for item in calls))

    def test_one_thread_boundary_is_fail_closed(self) -> None:
        contract = candidate.THREAD_ENV_CONTRACT
        names = tuple(contract)
        with mock.patch.dict(os.environ, contract, clear=False):
            candidate._require_single_thread_environment()
        with mock.patch.dict(os.environ, {names[0]: "2"}, clear=False):
            with self.assertRaisesRegex(ValueError, "one-thread resource cap"):
                candidate._require_single_thread_environment()

    def test_boundaries_and_no_real_run_or_retry_are_static(self) -> None:
        self.assertEqual(candidate.SCHEDULER_BRANCH_BINDING["attempt_id"], "attempt-02")
        self.assertFalse(candidate.SCHEDULER_BRANCH_BINDING["resource_hint"]["authority_granted"])
        self.assertEqual(candidate.SCHEDULER_BRANCH_BINDING["resource_hint"]["max_cost_usd"], 0.0)
        self.assertEqual(candidate.COMPONENT_SPEC["retries"], 0)
        self.assertEqual(candidate.COMPONENT_SPEC["outer_fits"], 4)
        self.assertEqual(candidate.COMPONENT_SPEC["maximum_iterations"], 50)
        self.assertEqual(candidate.COMPONENT_SPEC["gradient_infinity_tolerance"], 1e-8)


if __name__ == "__main__":
    unittest.main()
