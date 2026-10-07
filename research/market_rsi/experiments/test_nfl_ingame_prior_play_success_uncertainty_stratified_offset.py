from __future__ import annotations

from datetime import date, timedelta
import math
import os
from pathlib import Path
import unittest
from unittest import mock

import numpy as np

from experiments import nfl_ingame_prior_play_success_uncertainty_stratified_offset as candidate
from experiments import nfl_ingame_win_probability_train_diagnostic as base
from experiments import nfl_ingame_identity_anchored_market_calibration as identity
from experiments import nfl_settlement_probability_train_diagnostic as settlement


class UncertaintyStratifiedOffsetTests(unittest.TestCase):
    def test_exact_threshold_formula_and_zero_signal_rows(self) -> None:
        signals = np.asarray([1.0, 2.0, 0.0, -3.0])
        probabilities = np.asarray([0.1, 0.25, 0.75, 0.9])
        observed = candidate.stratified_features(signals, probabilities)
        np.testing.assert_array_equal(observed, np.asarray([
            [1.0, 0.0], [0.0, 2.0], [0.0, 0.0], [-3.0, 0.0]
        ]))
        with self.assertRaisesRegex(ValueError, "aligned finite"):
            candidate.stratified_features([1.0], [math.nan])

    def test_objective_gradient_hessian_no_intercept_and_ridge16(self) -> None:
        x = np.asarray([[1., 0.], [0., 2.], [-1., 0.], [0., -.5]])
        y = np.asarray([1., 0., 0., 1.]); offsets = np.asarray([.2, -.1, .5, -.4])
        theta = np.asarray([.3, -.2])
        value, gradient, hessian = candidate.objective_gradient_hessian(theta, x, y, offsets)
        eta = offsets + x @ theta
        expected = np.sum(np.logaddexp(0, eta) - y * eta) + .5 * 16 * (theta @ theta)
        self.assertAlmostEqual(value, float(expected), places=12)
        numerical = []
        for index in range(2):
            hi, lo = theta.copy(), theta.copy(); hi[index] += 1e-6; lo[index] -= 1e-6
            numerical.append((candidate.objective_gradient_hessian(hi, x, y, offsets)[0]
                              - candidate.objective_gradient_hessian(lo, x, y, offsets)[0]) / 2e-6)
        np.testing.assert_allclose(gradient, numerical, rtol=1e-6, atol=1e-7)
        np.testing.assert_allclose(hessian, hessian.T, rtol=0, atol=0)

    def test_damped_newton_is_deterministic_converged_and_no_retry(self) -> None:
        x = np.asarray([[1., 0.], [0., 1.], [-1., 0.], [0., -1.]] * 10)
        y = np.asarray([1., 1., 0., 0.] * 10); offsets = np.zeros(40)
        first, report = candidate.fit_stratified_offset(x, y, offsets)
        second, second_report = candidate.fit_stratified_offset(x, y, offsets)
        np.testing.assert_array_equal(first, second)
        self.assertLessEqual(report["gradient_infinity_norm"], 1e-8)
        self.assertEqual(report, second_report); self.assertEqual(report["retry_count"], 0)
        self.assertFalse(report["intercept"])

    def test_exact_four_fits_zero_control_refits_and_common_mask(self) -> None:
        rows, folds, indicators, controls = self._problem()
        calls = []; original = candidate.fit_stratified_offset
        def counted(*args, **kwargs):
            calls.append(len(args[0])); return original(*args, **kwargs)
        with mock.patch.object(candidate, "fit_stratified_offset", side_effect=counted), \
                mock.patch.object(identity, "fit_identity_anchored", side_effect=AssertionError("controls are read-only")):
            predictions, reports = candidate._fit_and_predict(rows, folds, indicators, controls)
        self.assertEqual(len(calls), 4); self.assertEqual(len(predictions), 20)
        self.assertEqual(set(item["row"].key for item in predictions), set(controls))
        self.assertTrue(all(report["fit_low_events"] + report["fit_high_events"] == report["fit_events"] for report in reports))

    def test_feature_missing_and_check_control_missing_fail_closed(self) -> None:
        rows, folds, indicators, controls = self._problem()
        missing = dict(indicators); missing.pop(next(iter(missing)))
        with self.assertRaisesRegex(ValueError, "all 193 materialized"):
            candidate._fit_and_predict(rows, folds, missing, controls)
        missing_control = dict(controls); missing_control.pop(next(iter(missing_control)))
        with self.assertRaisesRegex(ValueError, "differs from frozen"):
            candidate._fit_and_predict(rows, folds, indicators, missing_control)

    def test_decision_exact_support_refute_and_inconclusive(self) -> None:
        def fold(c, r, o):
            return {"arms": {candidate.ARM_CANDIDATE: {"brier": c}, candidate.ARM_RAW: {"brier": r}, candidate.ARM_ORDINARY: {"brier": o}}}
        aggregate = {candidate.ARM_CANDIDATE: {"brier": .18, "log_loss": .48},
            candidate.ARM_RAW: {"brier": .20, "log_loss": .52},
            candidate.ARM_ORDINARY: {"brier": .19, "log_loss": .50},
            candidate.ARM_PARENT: {"brier": .195, "log_loss": .51}}
        folds = [fold(.18, .20, .19)] * 3 + [fold(.21, .20, .19)]
        self.assertEqual(candidate.decision(aggregate, folds, self._paired(-.001))[:2], ("SUPPORTED", "KEEP"))
        bad = {**aggregate, candidate.ARM_CANDIDATE: {"brier": .201, "log_loss": .48}}
        self.assertEqual(candidate.decision(bad, folds, self._paired(-.001))[:2], ("REFUTED", "REVERT"))
        self.assertEqual(candidate.decision(aggregate, folds, self._paired(.001))[:2], ("INCONCLUSIVE", "REVERT"))

    def test_frozen_193_feature_and_controller_bindings_pass_without_fit(self) -> None:
        candidate._require_dependencies()
        frozen = candidate.prior._validate_v0_artifact(candidate.V0_ARTIFACT_ROOT)
        artifact = candidate.uncertainty._validate_parent_artifact(candidate.FEATURE_ARTIFACT_ROOT)
        indicators = candidate.prior._load_indicators(candidate.FEATURE_ARTIFACT_ROOT / "prior_play_success.csv", frozen)
        self.assertEqual(len(indicators), 193)
        self.assertEqual(artifact["hashes"]["prior_play_success.csv"], candidate.FEATURE_SHA256)
        self.assertEqual(candidate._digest(candidate.COMPONENT_SPEC), candidate.IMPLEMENTATION_COMPONENT_SPEC_SHA256)
        self.assertEqual(candidate._digest(candidate.SCHEDULER_BRANCH_BINDING), candidate.SCHEDULER_BRANCH_BINDING_SHA256)

    def test_paired_bootstrap_and_static_boundaries(self) -> None:
        rows, folds, indicators, controls = self._problem()
        predictions, _ = candidate._fit_and_predict(rows, folds, indicators, controls)
        calls = []
        def fake(records, group, value, *, seed, replicates):
            calls.append((group, value, seed, replicates)); return {"interval_95": [-.1, .1]}
        with mock.patch.object(base, "_group_bootstrap", side_effect=fake):
            evidence = candidate._paired_evidence(predictions)
        self.assertEqual(len(evidence), 3); self.assertEqual(len(calls), 12)
        self.assertTrue(all(call[2:] == (20260929, 10_000) for call in calls))
        source = Path(candidate.__file__).read_text()
        for forbidden in ("import requests", "import httpx", "import socket", "boto3"):
            self.assertNotIn(forbidden, source)
        self.assertIn('"network_bytes": 0', source); self.assertIn('"provider_calls": 0', source)

    @staticmethod
    def _paired(upper):
        return {f"candidate_minus_{candidate.ARM_RAW}": {"brier": {
            "schedule_date_interval": {"interval_95": [-.01, upper]},
            "observed_game_week_interval": {"interval_95": [-.01, upper]}}}}

    @classmethod
    def _problem(cls):
        dates = [(date(2025, 1, 1) + timedelta(days=i)).isoformat() for i in range(42)]
        rows = [cls._row(i, day) for i, day in enumerate(dates)]
        folds = settlement.chronological_date_folds(dates)
        indicators = {row.game_id: {"signal": math.sin(i * .4)} for i, row in enumerate(rows)}
        controls = {}
        for fold in folds:
            for row in rows:
                if row.game_date in fold["check_dates"]:
                    raw = row.trusted["market_probability"]
                    controls[row.key] = {"fold": fold["fold"], "game_id": row.game_id,
                        "game_date": row.game_date, "game_week": row.game_week,
                        "outcome": row.trusted["outcome"], identity.ARM_RAW: raw,
                        identity.ARM_ORDINARY: min(.95, raw + .01), identity.ARM_PARENT: max(.05, raw - .01)}
        return rows, folds, indicators, controls

    @staticmethod
    def _row(index, day):
        p = .15 + .7 * ((index % 11) / 10); cutoff = (10_000 + index) * 1000
        trusted = {"event_id": f"event-{index}", "market_id": f"market-{index}", "cutoff_ms": cutoff,
            "feature_available_ms": cutoff, "outcome_available_ms": cutoff + 1,
            "outcome": int(index % 3 == 0), "market_probability": p}
        return base.InGameRow(f"game-{index}", day, str(index // 6 + 1), trusted,
            (math.log(p / (1 - p)),), (0.,) * 9, {})


if __name__ == "__main__": unittest.main()
