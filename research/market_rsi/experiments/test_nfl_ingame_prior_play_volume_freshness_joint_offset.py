from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np
from scipy.special import expit

from experiments import nfl_ingame_prior_play_volume_freshness_joint_offset as candidate
from experiments import test_nfl_ingame_identity_blended_isotonic as parent_tests
from experiments import test_nfl_ingame_market_freshness_interaction_offset as old_tests
from experiments import test_nfl_ingame_prior_play_volume_offset as volume_tests


def problem():
    rows, folds, controls, _ = old_tests.synthetic_problem()
    features = candidate.volume.validate_features(volume_tests.synthetic_indicators(rows), rows)
    return rows, folds, controls, features


def synthetic_control_artifacts(root):
    parent_root, secondary_root = root / "C2", root / "A1"
    parent_root.mkdir()
    secondary_root.mkdir()
    parent, controls, frozen, expected_key = parent_tests.synthetic_parent(parent_root, candidate.volume.TASK_ID)
    secondary, _, _, _ = parent_tests.synthetic_parent(secondary_root, candidate.common.TASK_ID)
    states = {"task_id": candidate.volume.TASK_ID, "folds": []}
    reports = {"task_id": candidate.volume.TASK_ID, "folds": []}
    for fold in (1, 2, 3, 4):
        state = {"formula": candidate.volume.FORMULA, "beta": fold / 100., "penalty": 16,
            "market_coefficient": 1, "intercept": False, "standardization": "none"}
        digest = candidate.common._digest(state)
        states["folds"].append({"fold": fold, "state": state, "state_sha256": digest})
        reports["folds"].append({"fold": fold, "trainer": {"predictor_state_sha256": digest}})
    for name, value in (("predictor_states", states), ("scorecard", reports)):
        candidate.common.base._atomic_json(parent_root / f"{name}.json", value)
    manifest = candidate.common.settlement._strict_json(parent_root / "manifest.json")
    for name in ("predictor_states", "scorecard"):
        manifest[f"{name}_sha256"] = candidate.common._sha256(parent_root / f"{name}.json")
        parent["research_parent"][f"{name}_sha256"] = manifest[f"{name}_sha256"]
    candidate.common.base._atomic_json(parent_root / "manifest.json", manifest)
    parent["research_parent"]["manifest_sha256"] = candidate.common._sha256(parent_root / "manifest.json")
    return {"research_parent": parent["research_parent"],
        "secondary_feature_provenance_and_control": secondary["research_parent"]}, controls, frozen, expected_key


class PriorPlayVolumeFreshnessJointOffsetTests(unittest.TestCase):
    def test_true2d_objective_gradient_hessian_finite_differences_and_fit(self):
        rows, _, _, features = problem()
        design, _, _ = candidate.joint_design(rows[:22], rows[22:], features)
        y = np.asarray([row.trusted["outcome"] for row in rows[:22]])
        logits = np.asarray([row.market_features[0] for row in rows[:22]])
        theta = np.asarray([.31, -.13])
        value, gradient, hessian = candidate.common.scaffold.objective_gradient_hessian(theta, design, y, logits)
        eta, h = logits + design @ theta, 1e-5
        p = expit(eta)
        self.assertAlmostEqual(value, np.sum(np.logaddexp(0., eta) - y * eta) + 8 * theta @ theta, places=13)
        np.testing.assert_allclose(gradient, design.T @ (p - y) + 16 * theta, rtol=0, atol=1e-13)
        np.testing.assert_allclose(hessian, design.T @ (design * (p * (1 - p))[:, None]) + 16 * np.eye(2), rtol=0, atol=1e-13)
        for coordinate in (0, 1):
            shift = np.eye(2)[coordinate] * h
            high = candidate.common.scaffold.objective_gradient_hessian(theta + shift, design, y, logits)
            low = candidate.common.scaffold.objective_gradient_hessian(theta - shift, design, y, logits)
            self.assertAlmostEqual(gradient[coordinate], (high[0] - low[0]) / (2 * h), places=8)
            np.testing.assert_allclose(hessian[:, coordinate], (high[1] - low[1]) / (2 * h), rtol=0, atol=1e-8)
        values, report = candidate.fit_joint(rows[:22], rows[22:], features)
        repeated, repeat_report = candidate.fit_joint(rows[:22], rows[22:], features)
        self.assertEqual((values, report), (repeated, repeat_report))
        self.assertEqual(report["input_columns"], 2)
        state = report["primitive_prediction_state"]
        self.assertLessEqual(state["stationarity"]["gradient_infinity_norm"], 1e-8)
        self.assertTrue(all(value > 0 for value in state["stationarity"]["hessian_eigenvalues"]))
        self.assertEqual(values, candidate.replay_joint(state, rows[22:], features))

    def test_exact_zero_and_nested_c2_a1_coordinate_probability_identities(self):
        rows, _, _, features = problem()
        _, design, normalizer = candidate.joint_design(rows[:22], rows[22:], features)
        raw, logits = [row.trusted["market_probability"] for row in rows[22:]], [row.market_features[0] for row in rows[22:]]
        self.assertEqual(candidate.probabilities([0., 0.], design, logits, raw), raw)
        for coordinate, beta in ((0, .31), (1, -.13)):
            theta = np.zeros(2)
            theta[coordinate] = beta
            expected = candidate.common.candidate_probabilities(beta, design[:, coordinate], logits, raw_probabilities=raw)
            self.assertEqual(candidate.probabilities(theta, design, logits, raw), expected)
        _, report = candidate.fit_joint(rows[:22], rows[22:], features)
        state = report["primitive_prediction_state"]
        self.assertEqual(state["freshness_normalization"], normalizer)
        self.assertEqual(state["column_order"], candidate.COLUMNS)
        self.assertEqual(report["legacy_beta_low_high_column_order"],
            {"beta_low": candidate.COLUMNS[0], "beta_high": candidate.COLUMNS[1]})

    def test_check_labels_features_ages_future_state_cannot_change_fitted_state(self):
        rows, _, _, features = problem()
        _, first = candidate.fit_joint(rows[:22], rows[22:], features)
        changed = []
        for row in rows[22:]:
            receipt = {**row.source_receipt, "market_staleness_seconds": 299.,
                "latest_trade_epoch_ms": row.trusted["cutoff_ms"] - 299000, "future_label": 1}
            changed.append(candidate.common.base.InGameRow(row.game_id, row.game_date, row.game_week,
                {**row.trusted, "outcome": 1 - row.trusted["outcome"], "future_final": np.nan},
                row.market_features, (np.nan,) * 9, receipt))
        altered_features = {**features, **{row.game_id: -.8 for row in changed}}
        # A legal but extreme check age cannot alter fitting; output must still
        # obey the old epsilon validator rather than gaining a new clipping rule.
        _, _, normalizer = candidate.joint_design(rows[:22], changed, altered_features)
        self.assertEqual(first["primitive_prediction_state"]["freshness_normalization"], normalizer)
        with self.assertRaisesRegex(ValueError, "epsilon policy"):
            candidate.fit_joint(rows[:22], changed, altered_features)
        moderate = [candidate.common.base.InGameRow(row.game_id, row.game_date, row.game_week,
            row.trusted, row.market_features, row.state_features,
            {**row.source_receipt, "market_staleness_seconds": 40.,
                "latest_trade_epoch_ms": row.trusted["cutoff_ms"] - 40000}) for row in changed]
        _, second = candidate.fit_joint(rows[:22], moderate, altered_features)
        self.assertEqual(first["predictor_state_sha256"], second["predictor_state_sha256"])
        self.assertEqual(first["optimizer"], second["optimizer"])

    def test_invalid_coverage_causal_age_zero_scale_features_and_states_fail_closed(self):
        rows, _, _, features = problem()
        with mock.patch.object(candidate.volume, "load_features", return_value=(features, {})):
            values, receipts = candidate.load_features(Path("synthetic"), {}, {}, rows)
            self.assertEqual(values, features)
            self.assertEqual(receipts["causal_age_rows_validated"], len(rows))
        missing = dict(features)
        missing.pop(rows[0].game_id)
        with mock.patch.object(candidate.volume, "load_features", return_value=({**missing, "extra-game": .1}, {})), \
                self.assertRaisesRegex(ValueError, "coverage"):
            candidate.load_features(Path("synthetic"), {}, {}, rows)
        invalid_age = candidate.common.base.InGameRow(rows[0].game_id, rows[0].game_date, rows[0].game_week,
            rows[0].trusted, rows[0].market_features, rows[0].state_features, {**rows[0].source_receipt, "market_staleness_seconds": 301.})
        with mock.patch.object(candidate.volume, "load_features", return_value=(features, {})), self.assertRaises(ValueError):
            candidate.load_features(Path("synthetic"), {}, {}, [invalid_age, *rows[1:]])
        same_age = [candidate.common.base.InGameRow(row.game_id, row.game_date, row.game_week,
            row.trusted, row.market_features, row.state_features, {**row.source_receipt, "market_staleness_seconds": 1.,
                "latest_trade_epoch_ms": row.trusted["cutoff_ms"] - 1000}) for row in rows[:22]]
        with self.assertRaisesRegex(ValueError, "scale"):
            candidate.fit_joint(same_age, rows[22:], features)
        for value in (np.nan, np.inf, 1., -1.):
            with self.subTest(value=value), self.assertRaises(ValueError):
                candidate.fit_joint(rows[:22], rows[22:], {**features, rows[0].game_id: value})
        _, report = candidate.fit_joint(rows[:22], rows[22:], features)
        state = report["primitive_prediction_state"]
        for change in ({"column_order": list(reversed(candidate.COLUMNS))}, {"coefficients": [0., np.nan]},
                {"penalty_per_coordinate": 8}, {"freshness_normalization": {"fit_age_mean": 2., "fit_age_std_ddof0": 0., "fit_only": True}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                candidate.replay_joint({**state, **change}, rows[22:], features)

    def test_portable_c2_a1_87_hash_control_label_state_and_task_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            contract, controls, frozen, expected_key = synthetic_control_artifacts(Path(directory))
            with mock.patch.object(candidate.common.frozen_v0, "EXPECTED_CHECK_KEY_SHA256", expected_key):
                parent, secondary = candidate.load_controls(contract, controls, frozen)
                self.assertEqual((len(parent), len(secondary)), (87, 87))
                for name in ("manifest", "scorecard", "predictions", "pre_score_lock", "predictor_states"):
                    bad = copy.deepcopy(contract)
                    bad["research_parent"][f"{name}_sha256"] = "0" * 64
                    with self.subTest(name=name), self.assertRaises(ValueError):
                        candidate.load_controls(bad, controls, frozen)
                bad = copy.deepcopy(contract)
                bad["secondary_feature_provenance_and_control"]["predictions_sha256"] = "0" * 64
                with self.assertRaises(ValueError):
                    candidate.load_controls(bad, controls, frozen)
                for field, value in (("outcome", 1), (candidate.ARM_ORDINARY, .01)):
                    bad_controls = copy.deepcopy(controls)
                    key = next(iter(bad_controls))
                    bad_controls[key][field] += value
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        candidate.load_controls(contract, bad_controls, frozen)
                root = Path(contract["research_parent"]["artifact_root"])
                states = candidate.common.settlement._strict_json(root / "predictor_states.json")
                states["folds"][0]["state"]["beta"] += .01
                candidate.common.base._atomic_json(root / "predictor_states.json", states)
                digest = candidate.common._sha256(root / "predictor_states.json")
                manifest = candidate.common.settlement._strict_json(root / "manifest.json")
                manifest["predictor_states_sha256"] = digest
                candidate.common.base._atomic_json(root / "manifest.json", manifest)
                contract["research_parent"].update({"predictor_states_sha256": digest,
                    "manifest_sha256": candidate.common._sha256(root / "manifest.json")})
                with self.assertRaisesRegex(ValueError, "canonical numeric state"):
                    candidate.load_controls(contract, controls, frozen)

    def test_full195_four_true_joint_fits87_predictions_states_secondary_and_unchanged_judge(self):
        contract = candidate.common.settlement._strict_json(candidate.CONTRACT)
        def controls_loader(contract, controls, frozen):
            return ({key: item[candidate.ARM_RAW] for key, item in controls.items()},
                {key: item[candidate.ARM_ORDINARY] for key, item in controls.items()})
        def volume_loader(source, frozen, contract, rows):
            values = candidate.volume.validate_features(volume_tests.synthetic_indicators(rows), rows)
            return values, {"all_materialized_rows_validated": len(values)}
        with mock.patch.object(candidate.common, "run", side_effect=candidate.run), \
                mock.patch.object(candidate, "require_dependencies", return_value=contract), \
                mock.patch.object(candidate, "load_controls", side_effect=controls_loader), \
                mock.patch.object(candidate.volume, "load_features", side_effect=volume_loader), \
                mock.patch.object(candidate, "fit_joint", wraps=candidate.fit_joint) as fit, \
                mock.patch.object(candidate.common.base, "_atomic_json", wraps=candidate.common.base._atomic_json) as write, \
                mock.patch.object(candidate, "write_predictions", wraps=candidate.write_predictions) as csv_write:
            old_tests.FreshnessInteractionOffsetTests().test_complete_synthetic_run_has_exact87_predictions_and_hash_bound_artifacts()
        self.assertEqual(fit.call_count, 4)
        predictions = csv_write.call_args.args[1]
        self.assertEqual(len(predictions), 87)
        artifacts = {call.args[0].name: call.args[1] for call in write.call_args_list}
        self.assertEqual(len(artifacts["predictor_states.json"]["folds"]), 4)
        self.assertEqual(artifacts["input_receipts.json"]["feature_receipts"]["causal_age_rows_validated"], 193)
        self.assertEqual(artifacts["scorecard.json"]["actual_research_parent_id"], candidate.volume.TASK_ID)
        self.assertEqual(artifacts["scorecard.json"]["secondary_reference_id"], candidate.common.TASK_ID)
        for item in artifacts["predictor_states.json"]["folds"]:
            check = [prediction["row"] for prediction in predictions if prediction["fold"] == item["fold"]]
            # Reconstruct the exact synthetic all-population feature mapping used before fitting.
            calls = fit.call_args_list[item["fold"] - 1]
            values = candidate.replay_joint(item["state"], check, calls.args[2])
            self.assertEqual(values, [prediction[candidate.ARM_CANDIDATE] for prediction in predictions if prediction["fold"] == item["fold"]])
        metrics, reports = artifacts["scorecard.json"]["aggregate"], artifacts["scorecard.json"]["folds"]
        with mock.patch.object(candidate.common.base, "_group_bootstrap", return_value={"interval_95": [-.1, .1]}) as draws:
            paired = candidate.paired_evidence(predictions)
        self.assertEqual(draws.call_count, 20)
        decision = candidate.common.decision(metrics, reports, paired, candidate.ARM_CANDIDATE)
        altered = {**metrics, candidate.ARM_RESEARCH_PARENT: {"brier": 0., "log_loss": 0.},
            candidate.ARM_SECONDARY: {"brier": 0., "log_loss": 0.}}
        self.assertEqual(decision, candidate.common.decision(altered, reports, paired, candidate.ARM_CANDIDATE))
        for arm in (candidate.ARM_RESEARCH_PARENT, candidate.ARM_SECONDARY):
            for name in ("brier", "log_loss"):
                self.assertAlmostEqual(paired[f"candidate_minus_{arm}"][name]["equal_event_mean"],
                    metrics[candidate.ARM_CANDIDATE][name] - metrics[arm][name], places=15)
        for arm, diagnostic in artifacts["scorecard.json"]["correction_diagnostics"].items():
            self.assertAlmostEqual(diagnostic["equal_event_brier_delta_raw_identity"], metrics[arm]["brier"] - metrics[candidate.ARM_RAW]["brier"], places=15)
        self.assertTrue(artifacts["scorecard.json"]["conditional_question_annotation"]["annotation_only_not_keep_judge"])

    def test_source_drift_terminal_fit_failure_and_no_output_overwrite(self):
        with mock.patch.object(candidate.sibling, "require_dependencies"), mock.patch.object(candidate.common, "_sha256", return_value="0" * 64):
            with self.assertRaisesRegex(ValueError, "source/contract"):
                candidate.require_dependencies()
        rows, _, _, features = problem()
        with mock.patch.object(candidate.common.scaffold, "fit_stratified_offset", side_effect=RuntimeError("bounded nonconvergence")) as fit:
            with self.assertRaises(RuntimeError):
                candidate.fit_joint(rows[:22], rows[22:], features)
        self.assertEqual(fit.call_count, 1)
        _, report = candidate.fit_joint(rows[:22], rows[22:], features)
        theta = report["primitive_prediction_state"]["coefficients"]
        for coefficients, changes in ((theta, {"converged": False}), ([3., 3.], {}), (theta, {"penalty": 8})):
            optimizer = {**report["optimizer"], **changes}
            with mock.patch.object(candidate.common.scaffold, "fit_stratified_offset", return_value=(coefficients, optimizer)), \
                    self.subTest(changes=changes, coefficients=coefficients), self.assertRaisesRegex(ValueError, "stationarity"):
                candidate.fit_joint(rows[:22], rows[22:], features)
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


if __name__ == "__main__":
    unittest.main()
