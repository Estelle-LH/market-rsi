from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np

from experiments import nfl_ingame_identity_blended_isotonic as candidate
from experiments import test_nfl_ingame_market_freshness_interaction_offset as old_tests
from experiments import test_nfl_ingame_market_state_confidence_link_hgb as parent_tests


def synthetic_parent(root, task="InGameMarketResidualHGB-v1"):
    evidence, controls, frozen, expected_key = parent_tests.synthetic_parent_artifacts(root)
    for name in ("manifest", "scorecard"):
        value = candidate.common.settlement._strict_json(root / f"{name}.json")
        value["task_id"] = task
        candidate.common.base._atomic_json(root / f"{name}.json", value)
    manifest = candidate.common.settlement._strict_json(root / "manifest.json")
    manifest["scorecard_sha256"] = candidate.common._sha256(root / "scorecard.json")
    candidate.common.base._atomic_json(root / "manifest.json", manifest)
    evidence["research_parent"].update({"candidate_id": task, "manifest_sha256": candidate.common._sha256(root / "manifest.json"),
        "scorecard_sha256": manifest["scorecard_sha256"]})
    return evidence, controls, frozen, expected_key


def complete_synthetic_run(module, *, feature_loader=None):
    contract = candidate.common.settlement._strict_json(candidate.CONTRACT)
    recipe = next(item for item in contract["candidates"] if item["candidate_id"] == module.TASK_ID)
    def parent_loader(recipe, controls, frozen):
        return {key: item[candidate.ARM_RAW] for key, item in controls.items()}
    with mock.patch.object(candidate.common, "run", side_effect=module.run), \
            mock.patch.object(candidate, "require_dependencies", return_value=(contract, recipe)), \
            mock.patch.object(candidate.shared, "load_parent_predictions", side_effect=parent_loader), \
            mock.patch.object(candidate.common.base, "_atomic_json", wraps=candidate.common.base._atomic_json) as write:
        if feature_loader is None:
            old_tests.FreshnessInteractionOffsetTests().test_complete_synthetic_run_has_exact87_predictions_and_hash_bound_artifacts()
        else:
            with mock.patch.object(module, "load_features", side_effect=feature_loader):
                old_tests.FreshnessInteractionOffsetTests().test_complete_synthetic_run_has_exact87_predictions_and_hash_bound_artifacts()
        artifacts = {call.args[0].name: call.args[1] for call in write.call_args_list}
    return artifacts


class IdentityBlendedIsotonicTests(unittest.TestCase):
    def test_real_synthetic_fit_exact_constructor_blend_thresholds_and_replay(self):
        rows = old_tests.synthetic_problem()[0]
        values, report = candidate.fit_isotonic(rows[:22], rows[22:])
        state = report["primitive_prediction_state"]
        self.assertEqual(report["constructor_params"], candidate.ISOTONIC_PARAMS)
        self.assertEqual((report["model_fits"], report["fit_events"], report["input_columns"]), (1, 22, 1))
        self.assertEqual(state["sample_weight"], None)
        self.assertTrue(np.all(np.diff(state["X_thresholds_"]) > 0))
        self.assertTrue(np.all(np.diff(state["y_thresholds_"]) >= 0))
        self.assertEqual(values, candidate.replay_isotonic(state, [row.trusted["market_probability"] for row in rows[22:]]))
        self.assertEqual(report["predictor_state_sha256"], candidate.common._digest(state))

    def test_interpolation_clipped_endpoints_single_threshold_and_nonfinite_rejection(self):
        state = {"X_thresholds_": [.3, .7], "y_thresholds_": [.2, .8], "X_min_": .3, "X_max_": .7,
            "constructor_params": candidate.ISOTONIC_PARAMS, "blend_weight": .25}
        raw = [.1, .3, .5, .7, .9]
        expected = (.75 * np.asarray(raw) + .25 * np.asarray([.2, .2, .5, .8, .8])).tolist()
        self.assertEqual(candidate.replay_isotonic(state, raw), expected)
        one = {**state, "X_thresholds_": [.4], "y_thresholds_": [.6], "X_min_": .4, "X_max_": .4}
        self.assertEqual(candidate.replay_isotonic(one, [.1, .9]), [.75 * .1 + .25 * .6, .75 * .9 + .25 * .6])
        for change in ({"X_thresholds_": [.7, .3]}, {"y_thresholds_": [.8, .2]}, {"blend_weight": .5},
                {"X_max_": .8}, {"y_thresholds_": [np.nan, .8]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                candidate.replay_isotonic({**state, **change}, raw)
        with self.assertRaises(ValueError):
            candidate.replay_isotonic(state, [np.inf])

    def test_no_check_label_state_age_or_future_columns_change_fit(self):
        rows = old_tests.synthetic_problem()[0]
        _, first = candidate.fit_isotonic(rows[:22], rows[22:])
        poisoned = [candidate.common.base.InGameRow(row.game_id, row.game_date, row.game_week,
            {**row.trusted, "outcome": 1 - row.trusted["outcome"], "future_final_score": 999},
            row.market_features, (np.nan,) * 9, {"future": True}) for row in rows[22:]]
        _, second = candidate.fit_isotonic(rows[:22], poisoned)
        self.assertEqual(first["predictor_state_sha256"], second["predictor_state_sha256"])
        changed_price = [candidate.common.base.InGameRow(row.game_id, row.game_date, row.game_week,
            {**row.trusted, "market_probability": .5}, (0.,), row.state_features, row.source_receipt) for row in poisoned]
        _, third = candidate.fit_isotonic(rows[:22], changed_price)
        self.assertEqual(first["predictor_state_sha256"], third["predictor_state_sha256"])

    def test_four_fits_parent_rows_scoring_and_parent_not_new_keep_judge(self):
        rows, folds, controls, _ = old_tests.synthetic_problem()
        parent = {key: row[candidate.ARM_RAW] for key, row in controls.items()}
        with mock.patch.object(candidate, "fit_isotonic", wraps=candidate.fit_isotonic) as fit:
            predictions, reports = candidate.fit_and_predict(rows, folds, controls, parent, fit_predict=fit)
        self.assertEqual(fit.call_count, 4)
        self.assertEqual({item["row"].key for item in predictions}, set(parent))
        metrics = candidate.shared.aggregate(predictions, candidate.ARM_CANDIDATE)
        with mock.patch.object(candidate.common.base, "_group_bootstrap", return_value={"interval_95": [-.1, .1]}) as draws:
            paired = candidate.shared.paired_evidence(predictions, candidate.ARM_CANDIDATE)
        self.assertEqual(draws.call_count, 16)
        decision = candidate.common.decision(metrics, reports, paired, candidate.ARM_CANDIDATE)
        changed = {**metrics, candidate.ARM_RESEARCH_PARENT: {"brier": 0., "log_loss": 0.}}
        self.assertEqual(decision, candidate.common.decision(changed, reports, paired, candidate.ARM_CANDIDATE))
        for metric in ("brier", "log_loss"):
            self.assertAlmostEqual(paired[f"candidate_minus_{candidate.ARM_RESEARCH_PARENT}"][metric]["equal_event_mean"],
                metrics[candidate.ARM_CANDIDATE][metric] - metrics[candidate.ARM_RESEARCH_PARENT][metric], places=15)
        bad = copy.deepcopy(controls)
        bad[next(iter(bad))]["outcome"] ^= 1
        with self.assertRaisesRegex(ValueError, "label"):
            candidate.fit_and_predict(rows, folds, bad, parent)
        with self.assertRaisesRegex(ValueError, "four"):
            candidate.fit_and_predict(rows, folds + folds[:1], controls, parent)

    def test_portable_synthetic87_parent_hash_key_label_control_task_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence, controls, frozen, expected_key = synthetic_parent(root)
            with mock.patch.object(candidate.common.frozen_v0, "EXPECTED_CHECK_KEY_SHA256", expected_key):
                self.assertEqual(len(candidate.shared.load_parent_predictions(evidence, controls, frozen)), 87)
                for name in ("manifest", "scorecard", "predictions"):
                    bad = copy.deepcopy(evidence)
                    bad["research_parent"][f"{name}_sha256"] = "0" * 64
                    with self.subTest(name=name), self.assertRaises(ValueError):
                        candidate.shared.load_parent_predictions(bad, controls, frozen)
                for field, change in (("outcome", 1), (candidate.ARM_ORDINARY, .01)):
                    bad = copy.deepcopy(controls)
                    key = next(iter(bad))
                    bad[key][field] += change
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        candidate.shared.load_parent_predictions(evidence, bad, frozen)
                missing = dict(controls)
                missing.pop(next(iter(missing)))
                with self.assertRaises(ValueError):
                    candidate.shared.load_parent_predictions(evidence, missing, frozen)
                manifest = candidate.common.settlement._strict_json(root / "manifest.json")
                manifest["task_id"] = "wrong-parent-task"
                candidate.common.base._atomic_json(root / "manifest.json", manifest)
                evidence["research_parent"]["manifest_sha256"] = candidate.common._sha256(root / "manifest.json")
                with self.assertRaises(ValueError):
                    candidate.shared.load_parent_predictions(evidence, controls, frozen)

    def test_contract_hash_constructor_source_drift_and_failure_no_overwrite(self):
        with mock.patch.object(candidate.shared, "require_dependencies"), mock.patch.object(candidate.common, "_sha256", return_value="0" * 64):
            with self.assertRaisesRegex(ValueError, "dependency/contract"):
                candidate.require_dependencies()
        rows = old_tests.synthetic_problem()[0]
        with mock.patch.object(candidate.IsotonicRegression, "get_params", return_value={}):
            with self.assertRaisesRegex(ValueError, "constructor"):
                candidate.fit_isotonic(rows[:22], rows[22:])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "failed"
            with mock.patch.object(candidate.common.base, "_validate_roots"), \
                    mock.patch.object(candidate, "require_dependencies", side_effect=ValueError("source drift")):
                with self.assertRaises(ValueError):
                    candidate.run(Path(directory) / "source", output, allow_test_paths=True)
            failure = candidate.common.settlement._strict_json(output / "failure.json")
            self.assertEqual((failure["automatic_retries"], failure["model_fits_maximum"]), (0, 4))
            with mock.patch.object(candidate.common.base, "_validate_roots"), self.assertRaises(FileExistsError):
                candidate.run(Path(directory) / "source", output, allow_test_paths=True)

    def test_complete_synthetic195_run_four_fits87_predictions_and_numeric_states(self):
        with mock.patch.object(candidate, "fit_isotonic", wraps=candidate.fit_isotonic) as fit:
            artifacts = complete_synthetic_run(candidate)
        self.assertEqual(fit.call_count, 4)
        self.assertEqual(len(artifacts["predictor_states.json"]["folds"]), 4)
        self.assertEqual(artifacts["scorecard.json"]["source_denominator"]["check_events"], 87)
        self.assertIn("predictor_states_sha256", artifacts["manifest.json"])
        self.assertEqual(artifacts["input_receipts.json"]["feature_receipts"]["all_materialized_rows_validated"], 193)


if __name__ == "__main__":
    unittest.main()
