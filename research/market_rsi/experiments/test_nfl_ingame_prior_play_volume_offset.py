from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np
from scipy.special import expit

from experiments import nfl_ingame_prior_play_volume_offset as candidate
from experiments import test_nfl_ingame_identity_blended_isotonic as sibling_tests
from experiments import test_nfl_ingame_market_freshness_interaction_offset as old_tests


def synthetic_indicators(rows):
    return {row.game_id: {"home_eligible_plays": 30 + index % 17,
        "away_eligible_plays": 25 + index % 11, "signal": np.nan, "future_final_score": 999}
        for index, row in enumerate(rows)}


class PriorPlayVolumeOffsetTests(unittest.TestCase):
    def test_ratio_exact_sign_bounds_integer_rejection_future_success_ignored(self):
        for home, away in ((30, 30), (50, 25), (25, 50), (1, 99)):
            value = candidate.volume_ratio({"home_eligible_plays": home, "away_eligible_plays": away,
                "signal": np.nan, "home_successes": 999, "future_label": 1})
            self.assertEqual(value, (home - away) / (home + away))
            self.assertGreater(value, -1)
            self.assertLess(value, 1)
        for home in (0, -1, 1.5, 30., True, np.nan, np.inf):
            with self.subTest(home=home), self.assertRaises(ValueError):
                candidate.volume_ratio({"home_eligible_plays": home, "away_eligible_plays": 30})
        with self.assertRaisesRegex(ValueError, "required"):
            candidate.volume_ratio({"home_eligible_plays": 30})

    def test_all193_coverage_missing_extra_and_non_count_poisoning(self):
        template = old_tests.synthetic_problem()[0][0]
        rows = [candidate.common.base.InGameRow(f"synthetic-{index}", template.game_date, template.game_week,
            template.trusted, template.market_features, template.state_features, template.source_receipt) for index in range(193)]
        indicators = synthetic_indicators(rows)
        features = candidate.validate_features(indicators, rows)
        self.assertEqual(len(features), 193)
        altered = {key: {**value, "signal": 0., "home_successes": -999, "future_final": np.inf}
            for key, value in indicators.items()}
        self.assertEqual(candidate.validate_features(altered, rows), features)
        missing = dict(indicators)
        missing.pop(next(iter(missing)))
        for bad in (missing, {**indicators, "extra-game": next(iter(indicators.values()))},
                {**missing, "extra-game": next(iter(indicators.values()))}):
            with self.assertRaisesRegex(ValueError, "coverage"):
                candidate.validate_features(bad, rows)

    def test_exact_nll_gradient_hessian_newton_zero_raw_and_numeric_replay(self):
        rows = old_tests.synthetic_problem()[0]
        features = candidate.validate_features(synthetic_indicators(rows), rows)
        values, report = candidate.fit_offset(rows[:22], rows[22:], features)
        state = report["primitive_prediction_state"]
        self.assertEqual(values, candidate.replay_offset(state, rows[22:], features))
        x = np.asarray([features[row.game_id] for row in rows[:22]])
        y = np.asarray([row.trusted["outcome"] for row in rows[:22]])
        offsets = np.asarray([row.market_features[0] for row in rows[:22]])
        beta = .31
        objective, gradient, hessian = candidate.common.objective_gradient_hessian(beta, x, y, offsets)
        eta = offsets + beta * x
        p = expit(eta)
        self.assertAlmostEqual(objective, np.sum(np.logaddexp(0., eta) - y * eta) + 8 * beta * beta, places=13)
        self.assertAlmostEqual(gradient, x @ (p - y) + 16 * beta, places=13)
        self.assertAlmostEqual(hessian, np.sum(x * x * p * (1 - p)) + 16, places=13)
        h = 1e-5
        plus = candidate.common.objective_gradient_hessian(beta + h, x, y, offsets)
        minus = candidate.common.objective_gradient_hessian(beta - h, x, y, offsets)
        self.assertAlmostEqual(gradient, (plus[0] - minus[0]) / (2 * h), places=8)
        self.assertAlmostEqual(hessian, (plus[1] - minus[1]) / (2 * h), places=8)
        self.assertLessEqual(report["analytic_gradient_absolute"], 1e-8)
        self.assertEqual(report["optimizer"]["unused_zero_column_coefficient"], 0.)
        self.assertEqual(candidate.replay_offset({**state, "beta": 0.}, rows[22:], features),
            [row.trusted["market_probability"] for row in rows[22:]])

    def test_check_label_feature_state_future_changes_do_not_fit_or_scale(self):
        rows = old_tests.synthetic_problem()[0]
        features = candidate.validate_features(synthetic_indicators(rows), rows)
        _, first = candidate.fit_offset(rows[:22], rows[22:], features)
        check = [candidate.common.base.InGameRow(row.game_id, row.game_date, row.game_week,
            {**row.trusted, "outcome": 1 - row.trusted["outcome"], "future_final_score": np.nan},
            row.market_features, (np.nan,) * 9, {}) for row in rows[22:]]
        altered = {**features, **{row.game_id: -.8 for row in check}}
        _, second = candidate.fit_offset(rows[:22], check, altered)
        self.assertEqual(first["predictor_state_sha256"], second["predictor_state_sha256"])
        self.assertEqual(first["optimizer"], second["optimizer"])
        self.assertEqual(second["primitive_prediction_state"]["standardization"], "none")

    def test_feature_artifact_source_receipt_and_validator_drift_fail_closed(self):
        rows = old_tests.synthetic_problem()[0]
        indicators = synthetic_indicators(rows)
        expected = {"file": "synthetic-hash"}
        recipe = {"feature_artifact": {"root": "/portable/synthetic/unused", "hashes": expected}}
        receipt = {"source_manifest_sha256": "source", "cohort_sha256": "cohort", "pbp_receipts_sha256": "pbp", "pbp_games": 195}
        def digest(path):
            return candidate.SIBLING_SOURCE_SHA256 if Path(path).name == Path(candidate.sibling.__file__).name else candidate.UNCERTAINTY_SOURCE_SHA256
        with mock.patch.object(candidate.common, "_sha256", side_effect=digest), \
                mock.patch.object(candidate.uncertainty, "_validate_parent_artifact", return_value={"hashes": expected}) as validator, \
                mock.patch.object(candidate.common.frozen_v0, "_validate_source_and_receipts", return_value=receipt), \
                mock.patch.object(candidate.common.settlement, "_strict_json", return_value=receipt), \
                mock.patch.object(candidate.common.frozen_v0, "_load_indicators", return_value=indicators):
            features, evidence = candidate.load_features(Path("source"), {}, recipe, rows)
            self.assertEqual(features, candidate.validate_features(indicators, rows))
            self.assertFalse(evidence["extractor_rerun"])
            validator.assert_called_once_with(Path("/portable/synthetic/unused"), expected_hashes=expected)
            with mock.patch.object(candidate.common.settlement, "_strict_json", return_value={**receipt, "pbp_receipts_sha256": "changed"}), \
                    self.assertRaisesRegex(ValueError, "source/cohort/PBP"):
                candidate.load_features(Path("source"), {}, recipe, rows)
            with mock.patch.object(candidate.uncertainty, "_validate_parent_artifact", return_value={"hashes": {}}), \
                    self.assertRaisesRegex(ValueError, "artifact changed"):
                candidate.load_features(Path("source"), {}, recipe, rows)
        with mock.patch.object(candidate.common, "_sha256", return_value="0" * 64), self.assertRaisesRegex(ValueError, "source changed"):
            candidate.load_features(Path("source"), {}, recipe, rows)

    def test_full195_run_four_exact_parent_trainer_fits87_predictions_state_hashes(self):
        def features_loader(source, frozen, recipe, rows):
            features = candidate.validate_features(synthetic_indicators(rows), rows)
            return features, {"all_materialized_rows_validated": len(features), "formula": candidate.FORMULA}
        with mock.patch.object(candidate, "fit_offset", wraps=candidate.fit_offset) as fit:
            artifacts = sibling_tests.complete_synthetic_run(candidate, feature_loader=features_loader)
        self.assertEqual(fit.call_count, 4)
        self.assertEqual(artifacts["scorecard.json"]["actual_research_parent_id"], "InGameCausalPossessionPressureOffset-v1")
        self.assertEqual(len(artifacts["predictor_states.json"]["folds"]), 4)
        self.assertEqual(artifacts["input_receipts.json"]["feature_receipts"]["all_materialized_rows_validated"], 193)
        self.assertIn("predictor_states_sha256", artifacts["manifest.json"])
        self.assertEqual(artifacts["input_receipts.json"]["dependency_source_hashes"][candidate.uncertainty.__name__], candidate.UNCERTAINTY_SOURCE_SHA256)
        self.assertTrue(all(report["trainer"]["analytic_gradient_absolute"] <= 1e-8 for report in artifacts["scorecard.json"]["folds"]))

    def test_portable_actual_parent87_is_a2_not_isotonic_parent_and_control_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence, controls, frozen, expected_key = sibling_tests.synthetic_parent(Path(directory),
                task="InGameCausalPossessionPressureOffset-v1")
            with mock.patch.object(candidate.common.frozen_v0, "EXPECTED_CHECK_KEY_SHA256", expected_key):
                parent = candidate.sibling.shared.load_parent_predictions(evidence, controls, frozen)
                self.assertEqual(len(parent), 87)
                bad = copy.deepcopy(controls)
                key = next(iter(bad))
                bad[key][candidate.ARM_PARENT] += .01
                with self.assertRaisesRegex(ValueError, "comparator"):
                    candidate.sibling.shared.load_parent_predictions(evidence, bad, frozen)
                bad_evidence = copy.deepcopy(evidence)
                bad_evidence["research_parent"]["candidate_id"] = "InGameMarketResidualHGB-v1"
                with self.assertRaisesRegex(ValueError, "completion"):
                    candidate.sibling.shared.load_parent_predictions(bad_evidence, controls, frozen)

    def test_nonconvergence_and_numeric_feature_state_drift_are_invalid_not_retry(self):
        rows = old_tests.synthetic_problem()[0]
        features = candidate.validate_features(synthetic_indicators(rows), rows)
        _, report = candidate.fit_offset(rows[:22], rows[22:], features)
        beta = report["primitive_prediction_state"]["beta"]
        for change in ({"converged": False}, {"penalty": 8}, {"unused_zero_column_coefficient": .01}):
            optimizer = {**report["optimizer"], **change}
            with mock.patch.object(candidate.common, "fit_single_offset", return_value=(beta, optimizer)) as fit, \
                    self.subTest(change=change), self.assertRaisesRegex(ValueError, "convergence"):
                candidate.fit_offset(rows[:22], rows[22:], features)
            self.assertEqual(fit.call_count, 1)
        state = report["primitive_prediction_state"]
        for change in ({"beta": np.nan}, {"formula": "future"}, {"intercept": True}, {"penalty": 8}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                candidate.replay_offset({**state, **change}, rows[22:], features)
        for value in (np.nan, np.inf, 1., -1.):
            altered = {**features, rows[0].game_id: value}
            with self.subTest(value=value), self.assertRaises(ValueError):
                candidate.fit_offset(rows[:22], rows[22:], altered)

    def test_fit_failure_preservation_no_overwrite_no_hidden_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "failed"
            with mock.patch.object(candidate.common.base, "_validate_roots"), \
                    mock.patch.object(candidate.sibling, "require_dependencies", side_effect=RuntimeError("bounded failure")) as execute:
                with self.assertRaises(RuntimeError):
                    candidate.run(Path(directory) / "source", output, allow_test_paths=True)
            self.assertEqual(execute.call_count, 1)
            failure = candidate.common.settlement._strict_json(output / "failure.json")
            self.assertEqual(failure["task_id"], candidate.TASK_ID)
            self.assertEqual((failure["automatic_retries"], failure["model_fits_maximum"]), (0, 4))
            with mock.patch.object(candidate.common.base, "_validate_roots"), self.assertRaises(FileExistsError):
                candidate.run(Path(directory) / "source", output, allow_test_paths=True)
        rows = old_tests.synthetic_problem()[0]
        features = candidate.validate_features(synthetic_indicators(rows), rows)
        with mock.patch.object(candidate.common, "fit_single_offset", side_effect=RuntimeError("nonconverged")) as fit:
            with self.assertRaises(RuntimeError):
                candidate.fit_offset(rows[:22], rows[22:], features)
        self.assertEqual(fit.call_count, 1)


if __name__ == "__main__":
    unittest.main()
