from __future__ import annotations

from collections import defaultdict
import copy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np
from scipy.special import expit

from experiments import nfl_ingame_prior_play_volume_unit_scale_joint_offset as candidate
from experiments import test_nfl_ingame_identity_blended_isotonic as artifact_tests
from experiments import test_nfl_ingame_market_freshness_interaction_offset as old_tests


def features_for(rows):
    indicators = {row.game_id: {"home_eligible_plays": 30 + sum(map(ord, row.game_id)) % 13,
        "away_eligible_plays": 25 + sum(map(ord, row.game_id)) % 17} for row in rows}
    return candidate.volume.validate_features(indicators, rows)


def problem():
    rows, folds, controls, _ = old_tests.synthetic_problem()
    return rows, folds, controls, features_for(rows)


def synthetic_parent_states(rows, folds, features):
    """Author numeric parent fixtures directly: no parent training calls."""
    by_date = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    probabilities, states = {}, {}
    for fold in folds:
        check = sorted([row for day in fold["check_dates"] for row in by_date[day]], key=lambda row: row.key)
        fit, _ = candidate.common.nested._strict_prior_rows(by_date, fold["fit_dates"], check)
        matrix, _, normalizer = candidate.native.joint_design(fit, check, features)
        state = {"schema": "prior_play_volume_freshness_joint_numeric_state_v1", "column_order": candidate.native.COLUMNS,
            "volume_formula": candidate.volume.FORMULA, "freshness_formula": candidate.native.FRESHNESS_FORMULA,
            "coefficients": [.002, -.01], "freshness_normalization": normalizer, "market_coefficient": 1,
            "intercept": False, "penalty_per_coordinate": 16, "fit_events": len(fit),
            "fit_feature_sha256": candidate.common._digest(matrix.tolist()), "synthetic_fixture": True}
        states[fold["fold"]] = state
        values = candidate.native.replay_joint(state, check, features)
        probabilities.update({row.key: value for row, value in zip(check, values, strict=True)})
    return probabilities, states


def synthetic_parent_artifacts(root):
    evidence, controls, frozen, expected_key = artifact_tests.synthetic_parent(root, candidate.native.TASK_ID)
    frozen.update({"hashes": {}, "receipts": {"pbp_receipts": [], "materialized_receipts": []}})
    artifact = {"task_id": candidate.native.TASK_ID, "folds": []}
    card = {"task_id": candidate.native.TASK_ID, "folds": []}
    for fold, fit_count in enumerate((106, 132, 148, 176), start=1):
        state = {"schema": "prior_play_volume_freshness_joint_numeric_state_v1", "column_order": candidate.native.COLUMNS,
            "volume_formula": candidate.volume.FORMULA, "freshness_formula": candidate.native.FRESHNESS_FORMULA,
            "coefficients": [.002, -.01], "freshness_normalization": {"fit_age_mean": 10., "fit_age_std_ddof0": 2., "fit_only": True},
            "market_coefficient": 1, "intercept": False, "penalty_per_coordinate": 16,
            "fit_events": fit_count, "fit_feature_sha256": "0" * 64, "synthetic_fixture": True}
        digest = candidate.common._digest(state)
        artifact["folds"].append({"fold": fold, "state": state, "state_sha256": digest})
        card["folds"].append({"fold": fold, "trainer": {"predictor_state_sha256": digest}})
    receipts = {"task_id": candidate.native.TASK_ID, "runner_sha256": candidate.NATIVE_SOURCE_SHA256,
        "controller_contract_sha256": candidate.native.CONTRACT_SHA256, "v0_artifact_hashes": {},
        "pbp_receipts": [], "materialized_receipts": [], **candidate.common.BOUNDARY_FLAGS}
    exclusions = {"source_events": 195, "materialized_events": 193, "excluded_events": 2,
        "exclusions": [{"game_id": game_id, "reason": reason} for game_id, reason in candidate.common.identity.EXPECTED_EXCLUSIONS]}
    for name, value in (("predictor_states", artifact), ("scorecard", card), ("input_receipts", receipts),
            ("exclusions", exclusions), ("pre_score_lock", {"task_id": candidate.native.TASK_ID,
                "controller_contract_sha256": candidate.native.CONTRACT_SHA256})):
        candidate.common.base._atomic_json(root / f"{name}.json", value)
    manifest = candidate.common.settlement._strict_json(root / "manifest.json")
    for name in ("predictor_states", "scorecard", "input_receipts", "exclusions", "pre_score_lock"):
        manifest[f"{name}_sha256"] = candidate.common._sha256(root / f"{name}.json")
    candidate.common.base._atomic_json(root / "manifest.json", manifest)
    evidence["research_parent"].update({key: value for key, value in manifest.items() if key.endswith("_sha256")})
    evidence["research_parent"].update({"manifest_sha256": candidate.common._sha256(root / "manifest.json"),
        "state_schema": "prior_play_volume_freshness_joint_numeric_state_v1",
        "state_sha256_by_fold": [item["state_sha256"] for item in artifact["folds"]]})
    return evidence, controls, frozen, expected_key


class PriorPlayVolumeUnitScaleJointOffsetTests(unittest.TestCase):
    def test_scale_ddof0_fit_only_not_centered_and_natural_zero_preserved(self):
        rows, _, _, features = problem()
        features[rows[0].game_id] = 0.
        native_fit, native_check, fit, check, scale, norm = candidate.scaled_design(rows[:22], rows[22:], features)
        self.assertEqual(scale, float(native_fit[:, 0].std(ddof=0)))
        self.assertNotEqual(scale, float(native_fit[:, 0].std(ddof=1)))
        np.testing.assert_array_equal(fit[:, 0], native_fit[:, 0] / scale)
        np.testing.assert_array_equal(check[:, 0], native_check[:, 0] / scale)
        np.testing.assert_array_equal(fit[:, 1], native_fit[:, 1])
        np.testing.assert_array_equal(check[:, 1], native_check[:, 1])
        self.assertEqual(fit[0, 0], 0.)
        self.assertNotAlmostEqual(float(fit[:, 0].mean()), 0.)
        self.assertEqual(norm, candidate.native.joint_design(rows[:22], rows[22:], features)[2])
        with self.assertRaisesRegex(ValueError, "positive; no floor"):
            candidate.scaled_design(rows[:22], rows[22:], {row.game_id: .25 for row in rows})
        tiny = {row.game_id: index * 1e-14 for index, row in enumerate(rows)}
        tiny_native, _, _, _, tiny_scale, _ = candidate.scaled_design(rows[:22], rows[22:], tiny)
        self.assertEqual(tiny_scale, float(tiny_native[:, 0].std(ddof=0)))
        self.assertTrue(0 < tiny_scale < 1e-10)  # No implicit floor or pooled-scale rescue.

    def test_native_scaled_identity_effective_prior_zero_and_deterministic_real_synthetic_fit(self):
        rows, _, _, features = problem()
        native_fit, native_check, fit, check, scale, _ = candidate.scaled_design(rows[:22], rows[22:], features)
        raw, logits = [row.trusted["market_probability"] for row in rows[22:]], [row.market_features[0] for row in rows[22:]]
        theta = np.asarray([.11, -.02])
        beta = np.asarray([theta[0] / scale, theta[1]])
        normalized = candidate.native.probabilities(theta, check, logits, raw)
        unscaled = candidate.native.probabilities(beta, native_check, logits, raw)
        np.testing.assert_allclose(normalized, unscaled, rtol=0, atol=2e-15)
        self.assertAlmostEqual(8 * float(theta @ theta), 8 * scale * scale * beta[0] ** 2 + 8 * beta[1] ** 2, places=15)
        self.assertEqual(candidate.native.probabilities([0., 0.], check, logits, raw), raw)
        values, report = candidate.fit_unit(rows[:22], rows[22:], features)
        self.assertEqual((values, report), candidate.fit_unit(rows[:22], rows[22:], features))
        state = report["primitive_prediction_state"]
        self.assertEqual(state["native_volume_coefficient"], state["coefficients"][0] / scale)
        self.assertEqual(state["effective_native_volume_penalty"], 16 * scale * scale)
        self.assertEqual(state["native_fit_feature_sha256"], candidate.common._digest(native_fit.tolist()))
        self.assertEqual(state["normalized_fit_feature_sha256"], candidate.common._digest(fit.tolist()))
        self.assertEqual(values, candidate.replay_unit(state, rows[22:], features))

    def test_true2d_objective_gradient_hessian_and_stationarity(self):
        rows, _, _, features = problem()
        design = candidate.scaled_design(rows[:22], rows[22:], features)[2]
        y = np.asarray([row.trusted["outcome"] for row in rows[:22]])
        offsets = np.asarray([row.market_features[0] for row in rows[:22]])
        theta, h = np.asarray([.13, -.07]), 1e-5
        value, gradient, hessian = candidate.common.scaffold.objective_gradient_hessian(theta, design, y, offsets)
        eta = offsets + design @ theta
        p = expit(eta)
        self.assertAlmostEqual(value, np.sum(np.logaddexp(0., eta) - y * eta) + 8 * theta @ theta, places=13)
        np.testing.assert_allclose(gradient, design.T @ (p - y) + 16 * theta, rtol=0, atol=1e-13)
        np.testing.assert_allclose(hessian, design.T @ (design * (p * (1 - p))[:, None]) + 16 * np.eye(2), rtol=0, atol=1e-13)
        for coordinate in (0, 1):
            shift = np.eye(2)[coordinate] * h
            high = candidate.common.scaffold.objective_gradient_hessian(theta + shift, design, y, offsets)
            low = candidate.common.scaffold.objective_gradient_hessian(theta - shift, design, y, offsets)
            self.assertAlmostEqual(gradient[coordinate], (high[0] - low[0]) / (2 * h), places=7)
            np.testing.assert_allclose(hessian[:, coordinate], (high[1] - low[1]) / (2 * h), rtol=0, atol=1e-8)
        _, report = candidate.fit_unit(rows[:22], rows[22:], features)
        stationarity = report["primitive_prediction_state"]["stationarity"]
        self.assertLessEqual(stationarity["gradient_infinity_norm"], 1e-8)
        self.assertTrue(all(value > 0 for value in stationarity["hessian_eigenvalues"]))

    def test_check_isolation_keeps_fit_state_but_updates_check_provenance(self):
        rows, _, _, features = problem()
        _, first = candidate.fit_unit(rows[:22], rows[22:], features)
        changed = [candidate.common.base.InGameRow(row.game_id, row.game_date, row.game_week,
            {**row.trusted, "outcome": 1 - row.trusted["outcome"], "future_final": np.nan}, row.market_features, (np.nan,) * 9,
            {**row.source_receipt, "market_staleness_seconds": 20., "latest_trade_epoch_ms": row.trusted["cutoff_ms"] - 20000}) for row in rows[22:]]
        altered_features = {**features, **{row.game_id: -.5 for row in changed}}
        _, second = candidate.fit_unit(rows[:22], changed, altered_features)
        first_state, second_state = first["primitive_prediction_state"], second["primitive_prediction_state"]
        check_hashes = {"native_check_feature_sha256", "normalized_check_feature_sha256"}
        self.assertEqual({key: value for key, value in first_state.items() if key not in check_hashes},
            {key: value for key, value in second_state.items() if key not in check_hashes})
        self.assertEqual(first["optimizer"], second["optimizer"])
        self.assertNotEqual(first_state["native_check_feature_sha256"], second_state["native_check_feature_sha256"])
        self.assertNotEqual(first["predictor_state_sha256"], second["predictor_state_sha256"])

    def test_parent_numeric_replay_without_fit_normalizer_feature_probability_drift(self):
        rows, folds, _, features = problem()
        parent, states = synthetic_parent_states(rows, folds, features)
        with mock.patch.object(candidate.common.scaffold, "fit_stratified_offset", side_effect=AssertionError("no parent fit")):
            replay = candidate.replay_parent(rows, folds, features, parent, states)
        self.assertEqual((replay["parent_rows_replayed"], replay["parent_refits"]), (20, 0))
        for mode in ("normalizer", "features", "probability"):
            changed_states, changed_features, changed_parent = copy.deepcopy(states), dict(features), dict(parent)
            if mode == "normalizer":
                changed_states[1]["freshness_normalization"]["fit_age_mean"] += .01
            elif mode == "features":
                changed_features[rows[0].game_id] += .01
            else:
                changed_parent[next(iter(changed_parent))] += .01
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                candidate.replay_parent(rows, folds, changed_features, changed_parent, changed_states)

    def test_portable_parent_seven_receipts_four_canonical_states87_controls_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            contract, controls, frozen, expected_key = synthetic_parent_artifacts(Path(directory))
            with mock.patch.object(candidate.common.frozen_v0, "EXPECTED_CHECK_KEY_SHA256", expected_key):
                parent, states = candidate.load_parent(contract, controls, frozen)
                self.assertEqual((len(parent), len(states)), (87, 4))
                for name in ("manifest", "input_receipts", "pre_score_lock", "exclusions", "predictor_states", "scorecard", "predictions"):
                    bad = copy.deepcopy(contract)
                    bad["research_parent"][f"{name}_sha256"] = "0" * 64
                    with self.subTest(name=name), self.assertRaises(ValueError):
                        candidate.load_parent(bad, controls, frozen)
                bad = copy.deepcopy(contract)
                bad["research_parent"]["state_sha256_by_fold"][0] = "0" * 64
                with self.assertRaisesRegex(ValueError, "canonical state"):
                    candidate.load_parent(bad, controls, frozen)
                for field, value in (("outcome", 1), (candidate.ARM_ORDINARY, .01)):
                    bad_controls = copy.deepcopy(controls)
                    bad_controls[next(iter(bad_controls))][field] += value
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        candidate.load_parent(contract, bad_controls, frozen)
                missing = dict(controls)
                missing.pop(next(iter(missing)))
                with self.assertRaises(ValueError):
                    candidate.load_parent(contract, missing, frozen)

    def test_full195_four_fits87_parent_and_candidate_replays_and_unchanged_keep(self):
        contract = candidate.common.settlement._strict_json(candidate.CONTRACT)
        def parent_loader(contract, controls, frozen):
            anchors = {state["game_id"]: state for state in frozen["anchors"]}
            cohort = candidate.common.base._validate_source(None)
            rows = [candidate.common.base._load_dynamic_market(None, item, anchors[item["game_id"]]) for item in cohort if "exclusion" not in item]
            rows.sort(key=lambda row: row.key)
            return synthetic_parent_states(rows, frozen["folds"], features_for(rows))
        def volume_loader(source, frozen, contract, rows):
            return features_for(rows), {"all_materialized_rows_validated": len(rows)}
        with mock.patch.object(candidate.common, "run", side_effect=candidate.run), \
                mock.patch.object(candidate, "require_dependencies", return_value=contract), \
                mock.patch.object(candidate, "load_parent", side_effect=parent_loader), \
                mock.patch.object(candidate.volume, "load_features", side_effect=volume_loader), \
                mock.patch.object(candidate.common.scaffold, "fit_stratified_offset", wraps=candidate.common.scaffold.fit_stratified_offset) as fit, \
                mock.patch.object(candidate.common.base, "_atomic_json", wraps=candidate.common.base._atomic_json) as write, \
                mock.patch.object(candidate.shared, "write_predictions", wraps=candidate.shared.write_predictions) as csv_write:
            old_tests.FreshnessInteractionOffsetTests().test_complete_synthetic_run_has_exact87_predictions_and_hash_bound_artifacts()
        self.assertEqual(fit.call_count, 4)
        predictions = csv_write.call_args.args[1]
        artifacts = {call.args[0].name: call.args[1] for call in write.call_args_list}
        self.assertEqual(artifacts["input_receipts.json"]["parent_replay"]["parent_rows_replayed"], 87)
        self.assertEqual(artifacts["input_receipts.json"]["feature_receipts"]["causal_age_rows_validated"], 193)
        self.assertEqual(artifacts["scorecard.json"]["actual_research_parent_id"], candidate.native.TASK_ID)
        self.assertTrue(artifacts["scorecard.json"]["all_four_freshness_normalizers_equal_c3"])
        states = artifacts["predictor_states.json"]["folds"]
        self.assertEqual(len(states), 4)
        for item in states:
            check = [prediction["row"] for prediction in predictions if prediction["fold"] == item["fold"]]
            values = candidate.replay_unit(item["state"], check, features_for([prediction["row"] for prediction in predictions]))
            self.assertEqual(values, [prediction[candidate.ARM_CANDIDATE] for prediction in predictions if prediction["fold"] == item["fold"]])
        metrics, reports = artifacts["scorecard.json"]["aggregate"], artifacts["scorecard.json"]["folds"]
        with mock.patch.object(candidate.common.base, "_group_bootstrap", return_value={"interval_95": [-.1, .1]}) as draws:
            paired = candidate.shared.paired_evidence(predictions, candidate.ARM_CANDIDATE)
        self.assertEqual(draws.call_count, 16)
        decision = candidate.common.decision(metrics, reports, paired, candidate.ARM_CANDIDATE)
        changed = {**metrics, candidate.ARM_RESEARCH_PARENT: {"brier": 0., "log_loss": 0.}}
        self.assertEqual(decision, candidate.common.decision(changed, reports, paired, candidate.ARM_CANDIDATE))
        for name in ("brier", "log_loss"):
            self.assertAlmostEqual(paired[f"candidate_minus_{candidate.ARM_RESEARCH_PARENT}"][name]["equal_event_mean"],
                metrics[candidate.ARM_CANDIDATE][name] - metrics[candidate.ARM_RESEARCH_PARENT][name], places=15)
        for arm, diagnostic in artifacts["scorecard.json"]["correction_diagnostics"].items():
            self.assertAlmostEqual(diagnostic["equal_event_brier_delta_raw_identity"], metrics[arm]["brier"] - metrics[candidate.ARM_RAW]["brier"], places=15)

    def test_state_feature_source_convergence_failure_and_no_retry_or_overwrite(self):
        rows, _, _, features = problem()
        _, report = candidate.fit_unit(rows[:22], rows[22:], features)
        state = report["primitive_prediction_state"]
        for changes in ({"volume_scale": 0.}, {"scale_only": False}, {"scale_ddof": 1},
                {"native_volume_coefficient": np.nan}, {"penalty_per_coordinate": 8}, {"coefficients": [0., np.nan]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                candidate.replay_unit({**state, **changes}, rows[22:], features)
        for value in (np.nan, np.inf, 1., -1.):
            with self.subTest(value=value), self.assertRaises(ValueError):
                candidate.fit_unit(rows[:22], rows[22:], {**features, rows[0].game_id: value})
        for theta, change in ((state["coefficients"], {"converged": False}), ([3., 3.], {})):
            with mock.patch.object(candidate.common.scaffold, "fit_stratified_offset", return_value=(theta, {**report["optimizer"], **change})) as fit, \
                    self.assertRaisesRegex(ValueError, "stationarity"):
                candidate.fit_unit(rows[:22], rows[22:], features)
            self.assertEqual(fit.call_count, 1)
        with mock.patch.object(candidate.native, "require_dependencies"), mock.patch.object(candidate.common, "_sha256", return_value="0" * 64):
            with self.assertRaisesRegex(ValueError, "source/contract"):
                candidate.require_dependencies()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "failed"
            with mock.patch.object(candidate.common.base, "_validate_roots"), mock.patch.object(candidate, "require_dependencies", side_effect=ValueError("source drift")):
                with self.assertRaises(ValueError):
                    candidate.run(Path(directory) / "source", output, allow_test_paths=True)
            failure = candidate.common.settlement._strict_json(output / "failure.json")
            self.assertEqual((failure["automatic_retries"], failure["model_fits_maximum"]), (0, 4))
            with mock.patch.object(candidate.common.base, "_validate_roots"), self.assertRaises(FileExistsError):
                candidate.run(Path(directory) / "source", output, allow_test_paths=True)


if __name__ == "__main__":
    unittest.main()
