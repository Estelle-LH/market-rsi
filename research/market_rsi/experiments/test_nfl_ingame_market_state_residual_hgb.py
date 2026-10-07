from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

import numpy as np

from experiments import nfl_ingame_market_state_residual_hgb as candidate
from experiments import test_nfl_ingame_market_freshness_interaction_offset as old_tests
from experiments.test_nfl_ingame_market_residual_hgb import synthetic_problem


class MarketStateResidualHGBTests(unittest.TestCase):
    def test_only_nine_frozen_state_columns_added_and_constructor_identical(self):
        rows, _, _ = synthetic_problem()
        shared = candidate.shared
        market = shared.feature_matrix(rows, include_state=False)
        state = shared.feature_matrix(rows, include_state=True)
        np.testing.assert_array_equal(state[:, :2], market)
        np.testing.assert_array_equal(state[:, 2:], [row.state_features for row in rows])
        _, market_report = shared.fit_hgb_residual(rows[:32] * 3, rows[32:], include_state=False)
        _, state_report = shared.fit_hgb_residual(rows[:32] * 3, rows[32:], include_state=True)
        self.assertEqual(market_report["constructor_params"], state_report["constructor_params"])
        self.assertEqual((market_report["n_iter"], state_report["n_iter"]), (64, 64))
        self.assertEqual((market_report["input_columns"], state_report["input_columns"]), (2, 11))
        self.assertEqual(state_report["primitive_prediction_state"]["feature_names"][2:], list(shared.common.base.STATE_FEATURE_NAMES))

    def test_four_synthetic_state_fits_frozen_mask_and_parent_not_incumbent(self):
        rows, folds, controls = synthetic_problem()
        shared = candidate.shared
        parent = {key: value[shared.ARM_RAW] - .002 for key, value in controls.items()}
        with mock.patch.object(shared, "fit_hgb_residual", wraps=shared.fit_hgb_residual) as fit:
            predictions, reports = shared.fit_and_predict(rows, folds, controls, parent,
                include_state=True, arm=candidate.ARM_CANDIDATE)
        self.assertEqual(fit.call_count, 4)
        self.assertEqual({item["row"].key for item in predictions}, set(controls))
        self.assertTrue(all(item["trainer"]["input_columns"] == 11 for item in reports))
        for item in predictions:
            self.assertEqual(item[shared.ARM_RESEARCH_PARENT], parent[item["row"].key])

    def test_thin_wrapper_has_separate_recipe_parent_arm_and_no_sibling_read(self):
        with mock.patch.object(candidate.shared, "run_recipe", return_value={}) as run:
            candidate.run(Path("source"), Path("out"), allow_test_paths=True)
        self.assertEqual(run.call_args.kwargs["candidate_id"], candidate.TASK_ID)
        self.assertEqual(run.call_args.kwargs["arm"], candidate.ARM_CANDIDATE)
        self.assertTrue(run.call_args.kwargs["include_state"])
        self.assertNotEqual(candidate.TASK_ID, candidate.shared.TASK_ID)
        source = Path(candidate.shared.__file__).read_text()
        self.assertNotIn("import pickle", source)
        self.assertNotIn("import joblib", source)
        self.assertNotIn("/runs/attempt-02", source)
        self.assertNotIn("requests", source)

    def test_check_label_poisoning_does_not_change_state_trainer(self):
        rows, _, _ = synthetic_problem()
        shared = candidate.shared
        fit, check = rows[:32] * 3, rows[32:]
        poisoned = [shared.common.base.InGameRow(row.game_id, row.game_date, row.game_week,
            {**row.trusted, "outcome": 1 - row.trusted["outcome"], "terminal_score": 999},
            row.market_features, row.state_features, row.source_receipt) for row in check]
        first, report = shared.fit_hgb_residual(fit, check, include_state=True)
        second, second_report = shared.fit_hgb_residual(fit, poisoned, include_state=True)
        self.assertEqual(first, second)
        self.assertEqual(report["primitive_prediction_state"], second_report["primitive_prediction_state"])

    def test_complete_synthetic_state195_run87_predictions_and_four_primitive_states(self):
        shared = candidate.shared
        rows, folds, controls = synthetic_problem()
        states = {row.game_id: {"game_id": row.game_id} for row in rows}
        contract = shared.common.settlement._strict_json(shared.CONTRACT)
        recipe = next(item for item in contract["candidates"] if item["candidate_id"] == candidate.TASK_ID)
        def parent_loader(recipe, controls, frozen):
            return {key: control[shared.ARM_RAW] - .002 for key, control in controls.items()}
        with mock.patch.object(old_tests, "synthetic_problem", return_value=(rows, folds, controls, states)), \
                mock.patch.object(shared.common, "run", side_effect=candidate.run), \
                mock.patch.object(shared, "require_dependencies", return_value=(contract, recipe)), \
                mock.patch.object(shared, "load_parent_predictions", side_effect=parent_loader), \
                mock.patch.object(shared, "fit_hgb_residual", wraps=shared.fit_hgb_residual) as fit, \
                mock.patch.object(shared.common.base, "_atomic_json", wraps=shared.common.base._atomic_json) as write:
            old_tests.FreshnessInteractionOffsetTests().test_complete_synthetic_run_has_exact87_predictions_and_hash_bound_artifacts()
            self.assertEqual(fit.call_count, 4)
            predictor_calls = [call for call in write.call_args_list if call.args[0].name == "predictor_states.json"]
            self.assertEqual(len(predictor_calls), 1)
            artifact = predictor_calls[0].args[1]
            self.assertEqual(len(artifact["folds"]), 4)
            self.assertTrue(all(len(item["state"]["trees"]) == 64 for item in artifact["folds"]))
            self.assertTrue(all(len(item["state"]["feature_names"]) == 11 for item in artifact["folds"]))


if __name__ == "__main__":
    unittest.main()
