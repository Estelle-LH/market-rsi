from __future__ import annotations

import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np

from experiments import nfl_ingame_market_residual_hgb as candidate
from experiments import test_nfl_ingame_market_freshness_interaction_offset as old_tests
from experiments import test_nfl_ingame_market_freshness_brier_offset as parent_tests


def synthetic_problem():
    rows, folds, controls, _ = old_tests.synthetic_problem()
    valid = []
    for index, row in enumerate(rows):
        possession, down, distance, field = index % 2, index % 4 + 1, index % 12, index % 95
        state = (float(index % 15 - 7), 1200., float(possession),
            *(float(value == down) for value in (1, 2, 3, 4)), float(distance),
            (2 * possession - 1) * (1 - field / 100))
        valid.append(candidate.common.base.InGameRow(row.game_id, row.game_date, row.game_week,
            row.trusted, row.market_features, state, row.source_receipt))
    return valid, folds, controls


class MarketResidualHGBTests(unittest.TestCase):
    def test_exact_market_basis_state_width_and_no_future_fields(self):
        rows, _, _ = synthetic_problem()
        market = candidate.feature_matrix(rows, include_state=False)
        state = candidate.feature_matrix(rows, include_state=True)
        self.assertEqual(market.shape, (42, 2))
        self.assertEqual(state.shape, (42, 11))
        np.testing.assert_array_equal(state[:, :2], market)
        np.testing.assert_array_equal(market[:, 0], [row.market_features[0] for row in rows])
        np.testing.assert_array_equal(state[:, 2:], [row.state_features for row in rows])
        poisoned = [candidate.common.base.InGameRow(row.game_id, row.game_date, row.game_week,
            {**row.trusted, "final_score": 999, "future_play": math.nan}, row.market_features,
            row.state_features, {**row.source_receipt, "post_play_outcome": "touchdown"}) for row in rows]
        np.testing.assert_array_equal(candidate.feature_matrix(poisoned, include_state=True), state)
        altered = candidate.common.base.InGameRow(rows[0].game_id, rows[0].game_date, rows[0].game_week,
            rows[0].trusted, (0.,), rows[0].state_features, rows[0].source_receipt)
        with self.assertRaisesRegex(ValueError, "logit"):
            candidate.feature_matrix([altered], include_state=False)

    def test_state_physical_bounds_and_missing_nonfinite_ages_fail_closed(self):
        row = synthetic_problem()[0][0]
        for index, value in ((0, 101), (1, 0), (2, .5), (3, .5), (7, 101), (8, 2), (0, math.nan)):
            state = list(row.state_features)
            state[index] = value
            altered = candidate.common.base.InGameRow(row.game_id, row.game_date, row.game_week,
                row.trusted, row.market_features, tuple(state), row.source_receipt)
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, "causal state"):
                candidate.feature_matrix([altered], include_state=True)
        missing = candidate.common.base.InGameRow(row.game_id, row.game_date, row.game_week,
            row.trusted, row.market_features, row.state_features, {})
        with self.assertRaisesRegex(ValueError, "incomplete"):
            candidate.feature_matrix([missing], include_state=False)

    def test_real_synthetic_hgb64_stages_determinism_target_and_safe_replay(self):
        rows, _, _ = synthetic_problem()
        fit, check = rows[:32] * 3, rows[32:]
        probabilities, report = candidate.fit_hgb_residual(fit, check, include_state=False)
        second, second_report = candidate.fit_hgb_residual(fit, check, include_state=False)
        self.assertEqual(probabilities, second)
        self.assertEqual(report, second_report)
        self.assertEqual(report["constructor_params"], candidate.HGB_PARAMS)
        self.assertFalse(report["constructor_params"]["early_stopping"])
        self.assertEqual(report["n_iter"], 64)
        self.assertEqual(report["input_columns"], 2)
        state = report["primitive_prediction_state"]
        self.assertEqual(len(state["trees"]), 64)
        self.assertTrue(all(len(tree) <= 7 for tree in state["trees"]))
        self.assertEqual(state["baseline_prediction"], float(np.mean(
            [row.trusted["outcome"] - row.trusted["market_probability"] for row in fit])))
        raw = [row.trusted["market_probability"] for row in check]
        replay = candidate.predict_primitive(state, candidate.feature_matrix(check, include_state=False))
        self.assertEqual(candidate.bound_probabilities(raw, replay)[0], probabilities)
        self.assertEqual(candidate.common._digest(state), report["predictor_state_sha256"])
        self.assertTrue(report["primitive_replay_exact"])
        self.assertNotIn("pickle", str(state))

    def test_check_labels_and_features_do_not_affect_training_state(self):
        rows, _, _ = synthetic_problem()
        fit, check = rows[:32] * 3, rows[32:]
        _, original = candidate.fit_hgb_residual(fit, check, include_state=False)
        changed = []
        for row in check:
            receipt = {**row.source_receipt, "latest_trade_epoch_ms": row.trusted["cutoff_ms"] - 200_000,
                "market_staleness_seconds": 200.}
            changed.append(candidate.common.base.InGameRow(row.game_id, row.game_date, row.game_week,
                {**row.trusted, "outcome": 1 - row.trusted["outcome"]}, row.market_features, row.state_features, receipt))
        _, poisoned = candidate.fit_hgb_residual(fit, changed, include_state=False)
        self.assertEqual(poisoned["primitive_prediction_state"], original["primitive_prediction_state"])

    def test_probability_clipping_counts_without_mask_change(self):
        values, report = candidate.bound_probabilities([.5, .5, .5], [-.8, .8, 0.])
        epsilon = candidate.common.probability_contract.DEFAULT_PROBABILITY_POLICY.epsilon
        self.assertEqual(values, [epsilon, 1 - epsilon, .5])
        self.assertEqual((report["clipped_rows"], report["lower_clipped_rows"], report["upper_clipped_rows"], report["rows_removed"]), (2, 1, 1, 0))
        with self.assertRaises(ValueError):
            candidate.bound_probabilities([.5], [math.nan])
        with self.assertRaises(ValueError):
            candidate.bound_probabilities([.5], [.1, .2])

    def test_non64_stage_failure_is_terminal_no_retry(self):
        rows, _, _ = synthetic_problem()
        model = mock.Mock()
        model.get_params.return_value = dict(candidate.HGB_PARAMS)
        model.n_iter_ = 63
        with mock.patch.object(candidate, "HistGradientBoostingRegressor", return_value=model) as constructor:
            with self.assertRaisesRegex(RuntimeError, "exactly64"):
                candidate.fit_hgb_residual(rows[:32], rows[32:], include_state=False)
        self.assertEqual(constructor.call_count, 1)
        self.assertEqual(model.fit.call_count, 1)
        model.predict.assert_not_called()

    def test_four_synthetic_fits_frozen_parent_predictions_and_prior_label_guard(self):
        rows, folds, controls = synthetic_problem()
        parent = {key: value[candidate.ARM_RAW] + .002 for key, value in controls.items()}
        with mock.patch.object(candidate, "fit_hgb_residual", wraps=candidate.fit_hgb_residual) as fit:
            predictions, reports = candidate.fit_and_predict(rows, folds, controls, parent,
                include_state=False, arm=candidate.ARM_CANDIDATE)
        self.assertEqual(fit.call_count, 4)
        self.assertEqual({item["row"].key for item in predictions}, set(controls))
        self.assertTrue(all(item["trainer"]["n_iter"] == 64 for item in reports))
        for item in predictions:
            self.assertEqual(item[candidate.ARM_RESEARCH_PARENT], parent[item["row"].key])
        altered = dict(parent)
        altered.pop(next(iter(altered)))
        with mock.patch.object(candidate, "fit_hgb_residual", side_effect=AssertionError("no fit")):
            with self.assertRaisesRegex(ValueError, "common mask"):
                candidate.fit_and_predict(rows, folds, controls, altered, include_state=False, arm=candidate.ARM_CANDIDATE)
        row = rows[0]
        unavailable = candidate.common.base.InGameRow(row.game_id, row.game_date, row.game_week,
            {**row.trusted, "outcome_available_ms": rows[-1].trusted["cutoff_ms"]}, row.market_features, row.state_features, row.source_receipt)
        with self.assertRaisesRegex(ValueError, "strictly available"):
            candidate.fit_and_predict([unavailable, *rows[1:]], folds, controls, parent,
                include_state=False, arm=candidate.ARM_CANDIDATE)

    def test_generic_actual_parent87_hash_key_label_controls_and_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old, controls, frozen, items = parent_tests.FreshnessBrierOffsetTests._parent_fixture(root)
            recipe = {"research_parent": {**old["research_parent"], "artifact_root": str(root),
                "candidate_id": candidate.common.TASK_ID}}
            digest = candidate.common._digest([list(candidate.common.identity._control_key(item)) for item in items])
            with mock.patch.object(candidate.common.frozen_v0, "EXPECTED_CHECK_KEY_SHA256", digest):
                parent = candidate.load_parent_predictions(recipe, controls, frozen)
                self.assertEqual(len(parent), 87)
                self.assertEqual(set(parent.values()), {.501})
                changed = {**recipe, "research_parent": {**recipe["research_parent"], "predictions_sha256": "0" * 64}}
                with self.assertRaisesRegex(ValueError, "hash changed"):
                    candidate.load_parent_predictions(changed, controls, frozen)
                wrong = dict(controls)
                key = next(iter(wrong))
                wrong[key] = {**wrong[key], "outcome": 0}
                with self.assertRaisesRegex(ValueError, "label"):
                    candidate.load_parent_predictions(recipe, wrong, frozen)
                wrong_identity = {**recipe, "research_parent": {**recipe["research_parent"], "candidate_id": "wrong-parent"}}
                with self.assertRaisesRegex(ValueError, "identity"):
                    candidate.load_parent_predictions(wrong_identity, controls, frozen)

    def test_parent_scoring_pairing_csv_and_frozen_judge(self):
        rows, folds, controls = synthetic_problem()
        parent = {key: value[candidate.ARM_RAW] + .002 for key, value in controls.items()}
        predictions, reports = candidate.fit_and_predict(rows, folds, controls, parent, include_state=False, arm=candidate.ARM_CANDIDATE)
        metrics = candidate.aggregate(predictions, candidate.ARM_CANDIDATE)
        with mock.patch.object(candidate.common.base, "_group_bootstrap", return_value={"interval_95": [-.1, .1]}) as grouped:
            paired = candidate.paired_evidence(predictions, candidate.ARM_CANDIDATE)
        self.assertEqual(grouped.call_count, 16)
        for metric in ("brier", "log_loss"):
            expected = math.fsum(candidate.common.identity._loss(item["row"].trusted["outcome"], item[candidate.ARM_CANDIDATE], metric)
                - candidate.common.identity._loss(item["row"].trusted["outcome"], item[candidate.ARM_RESEARCH_PARENT], metric)
                for item in predictions) / len(predictions)
            self.assertEqual(paired[f"candidate_minus_{candidate.ARM_RESEARCH_PARENT}"][metric]["equal_event_mean"], expected)
        decision = candidate.common.decision(metrics, reports, paired, candidate.ARM_CANDIDATE)
        altered = {**metrics, candidate.ARM_RESEARCH_PARENT: {"brier": 0., "log_loss": 0.}}
        self.assertEqual(candidate.common.decision(altered, reports, paired, candidate.ARM_CANDIDATE), decision)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.csv"
            candidate.write_predictions(path, predictions, candidate.ARM_CANDIDATE)
            for item in candidate.common.frozen_v0._read_csv(path):
                self.assertEqual(float(item["frozen_actual_parent_probability"]), parent[candidate.common.identity._control_key(item)])

    def test_contract_drift_failure_preservation_and_full_synthetic195_run(self):
        with mock.patch.object(candidate.common, "require_dependencies"), mock.patch.object(candidate.common, "_sha256", return_value="0" * 64):
            with self.assertRaisesRegex(ValueError, "hash-changed"):
                candidate.require_dependencies(candidate.TASK_ID)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "failure"
            with mock.patch.object(candidate.common.base, "_validate_roots"), \
                    mock.patch.object(candidate, "require_dependencies", side_effect=ValueError("source drift")):
                with self.assertRaises(ValueError):
                    candidate.run(Path(directory) / "source", output, allow_test_paths=True)
            self.assertTrue((output / "failure.json").is_file())
            with mock.patch.object(candidate.common.base, "_validate_roots"), self.assertRaises(FileExistsError):
                candidate.run(Path(directory) / "source", output, allow_test_paths=True)
        contract = candidate.common.settlement._strict_json(candidate.CONTRACT)
        recipe = next(item for item in contract["candidates"] if item["candidate_id"] == candidate.TASK_ID)
        def parent_loader(recipe, controls, frozen):
            return {key: control[candidate.ARM_RAW] + .002 for key, control in controls.items()}
        with mock.patch.object(candidate.common, "run", side_effect=candidate.run), \
                mock.patch.object(candidate, "require_dependencies", return_value=(contract, recipe)), \
                mock.patch.object(candidate, "load_parent_predictions", side_effect=parent_loader), \
                mock.patch.object(candidate, "fit_hgb_residual", wraps=candidate.fit_hgb_residual) as fit:
            old_tests.FreshnessInteractionOffsetTests().test_complete_synthetic_run_has_exact87_predictions_and_hash_bound_artifacts()
            self.assertEqual(fit.call_count, 4)


if __name__ == "__main__":
    unittest.main()
