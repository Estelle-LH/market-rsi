from __future__ import annotations

from collections import defaultdict
import copy
import csv
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np
from sklearn.linear_model import Ridge

from experiments import nfl_ingame_market_state_ridge_residual_link as candidate
from experiments import test_nfl_ingame_market_state_confidence_link_hgb as parent_tests
from experiments import test_nfl_ingame_market_residual_hgb as hgb_tests
from experiments import test_nfl_ingame_market_freshness_interaction_offset as old_tests


def problem():
    return hgb_tests.synthetic_problem()


def parent_state(fold):
    """Direct numerical tree fixture; never fit a scientific parent."""
    return {"schema": "hgb_numeric_prediction_state_v1", "baseline_prediction": fold / 100,
        "feature_names": ["market_logit", "market_staleness_seconds", *candidate.common.base.STATE_FEATURE_NAMES],
        "constructor_params": dict(candidate.shared.HGB_PARAMS), "stage_count": 64,
        "leaf_values_include_learning_rate": True,
        "trees": [[{"value": .001, "feature_idx": 0, "num_threshold": 0., "left": 0, "right": 0,
            "is_leaf": 1, "missing_go_to_left": 1}] for _ in range(64)]}


def synthetic_parent(rows, folds):
    by_date = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    probabilities, states, prelink = {}, {}, {}
    for fold in folds:
        state = parent_state(fold["fold"])
        states[fold["fold"]] = state
        check = sorted([row for day in fold["check_dates"] for row in by_date[day]], key=lambda row: row.key)
        residual = candidate.shared.predict_primitive(state, candidate.shared.feature_matrix(check, include_state=True))
        values = candidate.parent_module.link_probabilities([row.trusted["market_probability"] for row in check], residual)[0]
        for row, p, f in zip(check, values, residual, strict=True):
            probabilities[row.key] = p
            prelink[row.key] = {"fold": fold["fold"], "residual": float(f)}
    return probabilities, states, prelink


def synthetic_parent_artifacts(root):
    evidence, controls, frozen, expected_key = parent_tests.synthetic_parent_artifacts(root)
    frozen.update({"hashes": {}, "receipts": {"pbp_receipts": [], "materialized_receipts": []}})
    states = candidate.common.settlement._strict_json(root / "predictor_states.json")
    states["task_id"] = candidate.parent_module.TASK_ID
    reports = candidate.common.settlement._strict_json(root / "scorecard.json")
    reports["task_id"] = candidate.parent_module.TASK_ID
    rows = candidate.common.frozen_v0._read_csv(root / "predictions.csv")
    residuals = []
    for row in rows:
        state = states["folds"][int(row["fold"]) - 1]["state"]
        f = float(candidate.shared.predict_primitive(state, np.zeros((1, 11)))[0])
        row["candidate_probability"] = str(candidate.parent_module.link_probabilities([float(row["raw_market_probability"])], [f])[0][0])
        residuals.append({"key": list(candidate.common.identity._control_key(row)), "fold": int(row["fold"]), "residual": f})
    with (root / "predictions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    receipts = {"task_id": candidate.parent_module.TASK_ID, "runner_sha256": candidate.PARENT_SOURCE_SHA256,
        "controller_contract_sha256": candidate.parent_module.CONTRACT_SHA256,
        "shared_hgb_source_sha256": candidate.parent_module.SHARED_SOURCE_SHA256,
        "v0_artifact_hashes": frozen["hashes"], **frozen["receipts"], **candidate.common.BOUNDARY_FLAGS}
    lock = {"task_id": candidate.parent_module.TASK_ID,
        "controller_contract_sha256": candidate.parent_module.CONTRACT_SHA256}
    exclusions = {"source_events": 195, "materialized_events": 193, "excluded_events": 2,
        "exclusions": [{"game_id": game_id, "reason": reason} for game_id, reason in candidate.common.identity.EXPECTED_EXCLUSIONS]}
    for name, value in (("predictor_states", states), ("scorecard", reports), ("input_receipts", receipts),
            ("pre_score_lock", lock), ("prelink_residuals", {"task_id": candidate.parent_module.TASK_ID, "rows": residuals}),
            ("exclusions", exclusions)):
        candidate.common.base._atomic_json(root / f"{name}.json", value)
    manifest = candidate.common.settlement._strict_json(root / "manifest.json")
    manifest["task_id"] = candidate.parent_module.TASK_ID
    for name in ("predictor_states", "scorecard", "input_receipts", "pre_score_lock", "prelink_residuals", "exclusions"):
        manifest[f"{name}_sha256"] = candidate.common._sha256(root / f"{name}.json")
    manifest["predictions_sha256"] = candidate.common._sha256(root / "predictions.csv")
    candidate.common.base._atomic_json(root / "manifest.json", manifest)
    files = ("manifest.json", "input_receipts.json", "pre_score_lock.json", "exclusions.json",
        "predictor_states.json", "prelink_residuals.json", "scorecard.json", "predictions.csv")
    hashes = {name: candidate.common._sha256(root / name) for name in files}
    evidence["research_parent"].update({"candidate_id": candidate.parent_module.TASK_ID,
        "artifact_hashes": hashes, "state_schema": "hgb_numeric_prediction_state_v1",
        "controller_contract_sha256": candidate.parent_module.CONTRACT_SHA256,
        "state_sha256_by_fold": [item["state_sha256"] for item in states["folds"]],
        **{name.split(".")[0] + "_sha256": digest for name, digest in hashes.items()}})
    evidence["fixed_information_and_output"] = {"feature_names": states["folds"][0]["state"]["feature_names"]}
    return evidence, controls, frozen, expected_key


def full_parent_loader(contract, controls, frozen):
    anchors = {state["game_id"]: state for state in frozen["anchors"]}
    cohort = candidate.common.base._validate_source(None)
    rows = [candidate.common.base._load_dynamic_market(None, item, anchors[item["game_id"]])
        for item in cohort if "exclusion" not in item]
    rows.sort(key=lambda row: row.key)
    return synthetic_parent(rows, frozen["folds"])


class MarketStateRidgeResidualLinkTests(unittest.TestCase):
    def test_population_fit_only_normalization_constants_retained_no_positive_floor(self):
        fit = np.arange(55, dtype=float).reshape(5, 11)
        fit[:, 2], fit[:, 3] = 0., 1200.
        fit[:, 4] = np.arange(5) * 1e-14
        check = fit[:2].copy()
        check[:, 2] = [1., 2.]
        z, q, moments = candidate.fit_transform(fit, check)
        mean, std = fit.mean(axis=0), fit.std(axis=0, ddof=0)
        np.testing.assert_array_equal(moments["mean"], mean)
        np.testing.assert_array_equal(moments["population_std"], std)
        np.testing.assert_array_equal(moments["constant_columns"], std == 0)
        scale = np.where(std > 0, std, 1.)
        np.testing.assert_array_equal(moments["scale"], scale)
        np.testing.assert_array_equal(z, (fit - mean) / scale)
        np.testing.assert_array_equal(q, (check - mean) / scale)
        self.assertEqual(z.shape, (5, 11))
        self.assertEqual(q.shape, (2, 11))
        self.assertTrue(moments["fit_only"])
        self.assertTrue(0 < scale[4] < 1e-10)
        np.testing.assert_array_equal(q[:, 2], [1., 2.])
        self.assertEqual(moments, candidate.fit_transform(fit, check * 100)[2])

    def test_closed_form_matches_installed_sklearn_ridge_and_independent_equations(self):
        rows, _, _ = problem()
        native = candidate.shared.feature_matrix(rows[:22], include_state=True)
        z, _, moments = candidate.fit_transform(native, native)
        residual = np.asarray([row.trusted["outcome"] - row.trusted["market_probability"] for row in rows[:22]])
        b, theta, receipt = candidate.solve_ridge(z, residual)
        model = Ridge(alpha=16., fit_intercept=True, solver="cholesky")
        model.fit(z, residual)
        np.testing.assert_allclose(theta, model.coef_, rtol=0, atol=1e-14)
        self.assertAlmostEqual(b, float(model.intercept_), places=14)
        a, rhs = z.T @ z + 16 * np.eye(11), z.T @ (residual - residual.mean())
        np.testing.assert_allclose(a @ theta, rhs, rtol=0, atol=1e-12)
        self.assertEqual(b, float(residual.mean()))
        self.assertTrue(np.all(np.linalg.eigvalsh(a) > 0))
        value, slope, intercept = candidate.ridge_objective_gradient(b, theta, z, residual)
        self.assertAlmostEqual(value, float(.5 * np.sum((b + z @ theta - residual) ** 2) + 8 * theta @ theta), places=14)
        self.assertLessEqual(float(np.max(np.abs(slope))), 1e-8)
        self.assertLessEqual(abs(intercept), 1e-8)
        self.assertTrue(receipt["converged"])
        constants = np.asarray(moments["constant_columns"], dtype=bool)
        np.testing.assert_array_equal(theta[constants], np.zeros(np.count_nonzero(constants)))

    def test_slope_intercept_gradients_finite_differences(self):
        rng = np.random.default_rng(20260929)
        z, residual = rng.normal(size=(17, 11)), rng.normal(size=17)
        theta, b, h = rng.normal(size=11) / 10, .03, 1e-5
        _, slope, intercept = candidate.ridge_objective_gradient(b, theta, z, residual)
        for j in range(11):
            delta = np.eye(11)[j] * h
            high = candidate.ridge_objective_gradient(b, theta + delta, z, residual)[0]
            low = candidate.ridge_objective_gradient(b, theta - delta, z, residual)[0]
            self.assertAlmostEqual(slope[j], (high - low) / (2 * h), places=7)
        high = candidate.ridge_objective_gradient(b + h, theta, z, residual)[0]
        low = candidate.ridge_objective_gradient(b - h, theta, z, residual)[0]
        self.assertAlmostEqual(intercept, (high - low) / (2 * h), places=7)

    def test_real_synthetic_fit_determinism_native_scaled_replay_and_zero_link(self):
        rows, _, _ = problem()
        values, report = candidate.fit_ridge(rows[:22], rows[22:])
        self.assertEqual((values, report), candidate.fit_ridge(rows[:22], rows[22:]))
        state = report["primitive_prediction_state"]
        self.assertEqual(values, candidate.replay_predictor(state, rows[22:])[0])
        residual = candidate.replay_residual(state, rows[22:])
        native = candidate.shared.feature_matrix(rows[22:], include_state=True)
        np.testing.assert_allclose(residual, state["native_intercept"] + native @ np.asarray(state["native_coefficients"]), rtol=0, atol=2e-14)
        raw = [row.trusted["market_probability"] for row in rows[22:]]
        self.assertEqual(values, candidate.parent_module.link_probabilities(raw, residual)[0])
        self.assertEqual(candidate.parent_module.link_probabilities(raw, np.zeros(len(raw)))[0], raw)
        self.assertEqual(state["alpha"], 16)
        self.assertEqual(state["output_factor"], 4)
        self.assertEqual(state["sample_weights"], None)
        self.assertEqual(len(state["coefficients"]), 11)
        self.assertEqual(report["predictor_state_sha256"], candidate.common._digest(state))

    def test_check_labels_future_fields_and_changed_check_inputs_leave_fit_identical(self):
        rows, _, _ = problem()
        fit, check = rows[:22], rows[22:]
        _, first = candidate.fit_ridge(fit, check)
        changed = [candidate.common.base.InGameRow(row.game_id, row.game_date, row.game_week,
            {**row.trusted, "outcome": 1 - row.trusted["outcome"], "future_final_score": np.nan},
            row.market_features, (row.state_features[0] + 1, *row.state_features[1:]), row.source_receipt) for row in check]
        _, second = candidate.fit_ridge(fit, changed)
        one, two = first["primitive_prediction_state"], second["primitive_prediction_state"]
        ignored = {"native_check_feature_sha256", "normalized_check_feature_sha256"}
        self.assertEqual({key: value for key, value in one.items() if key not in ignored},
            {key: value for key, value in two.items() if key not in ignored})
        self.assertNotEqual(one["native_check_feature_sha256"], two["native_check_feature_sha256"])
        self.assertEqual(one["normalization"], two["normalization"])

    def test_link_factor_bounds_and_saved_predictor_drift_fail_closed(self):
        rows, _, _ = problem()
        _, report = candidate.fit_ridge(rows[:22], rows[22:])
        state = report["primitive_prediction_state"]
        values, bounding = candidate.parent_module.link_probabilities([.5, .5], [-100., 100.])
        epsilon = candidate.common.probability_contract.DEFAULT_PROBABILITY_POLICY.epsilon
        self.assertEqual(values, [epsilon, 1 - epsilon])
        self.assertEqual((bounding["clipped_rows"], bounding["rows_removed"], bounding["factor"]), (2, 0, 4))
        for change in ({"alpha": 8}, {"output_factor": 2}, {"sample_weights": [1.]},
                {"coefficients": [np.nan] * 11}, {"native_intercept": np.nan}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                candidate.replay_predictor({**state, **change}, rows[22:])
        for key, value in (("scale", [0.] * 11), ("fit_only", False), ("mean", [np.nan] * 11)):
            bad = copy.deepcopy(state)
            bad["normalization"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                candidate.replay_residual(bad, rows[22:])

    def test_invalid_inputs_and_bad_solve_terminal_no_retry(self):
        with self.assertRaises(ValueError):
            candidate.fit_transform(np.full((3, 11), np.nan), np.zeros((1, 11)))
        with self.assertRaises(ValueError):
            candidate.fit_transform(np.zeros((0, 11)), np.zeros((1, 11)))
        rng = np.random.default_rng(23)
        z = rng.normal(size=(20, 11))
        z -= z.mean(axis=0)
        residual = rng.normal(size=20)
        with mock.patch.object(candidate.np.linalg, "solve", return_value=np.ones(11) * 10) as solve, \
                self.assertRaises(candidate.FitFailure) as failed:
            candidate.solve_ridge(z, residual)
        self.assertEqual(solve.call_count, 1)
        self.assertFalse(failed.exception.receipt["converged"])
        with mock.patch.object(candidate.np.linalg, "solve", return_value=np.full(11, np.nan)), \
                self.assertRaises(candidate.FitFailure):
            candidate.solve_ridge(z, residual)

    def test_postsolve_probability_failure_retains_converged_receipt(self):
        rows, _, _ = problem()
        with mock.patch.object(candidate.parent_module, "link_probabilities", side_effect=ValueError("synthetic probability failure")), \
                self.assertRaisesRegex(candidate.FitFailure, "probability failure") as failed:
            candidate.fit_ridge(rows[:22], rows[22:])
        self.assertTrue(failed.exception.receipt["converged"])

    def test_physical_solve_return_counter_separate_from_valid_fit(self):
        rng = np.random.default_rng(23)
        z = rng.normal(size=(20, 11))
        z -= z.mean(axis=0)
        residual = rng.normal(size=20)
        for returned in (np.full(11, np.nan), np.ones(11) * 10):
            with self.subTest(returned=returned[0]), mock.patch.object(candidate.np.linalg, "solve", return_value=returned) as solve, \
                    self.assertRaises(candidate.FitFailure) as failed:
                candidate.solve_ridge(z, residual)
            self.assertEqual(solve.call_count, 1)
            self.assertEqual(failed.exception.receipt["solve_calls_started"], 1)
            self.assertEqual(failed.exception.receipt["solve_calls_completed"], 1)
            self.assertFalse(failed.exception.receipt["converged"])
        with mock.patch.object(candidate.np.linalg, "solve", side_effect=np.linalg.LinAlgError("synthetic solve exception")) as solve, \
                self.assertRaises(candidate.FitFailure) as failed:
            candidate.solve_ridge(z, residual)
        self.assertEqual(solve.call_count, 1)
        self.assertEqual(failed.exception.receipt["solve_calls_started"], 1)
        self.assertEqual(failed.exception.receipt["solve_calls_completed"], 0)
        self.assertFalse(failed.exception.receipt["converged"])

    def test_b3_tree_prelink_parent_replay_no_refits_and_drift(self):
        rows, folds, _ = problem()
        parent, states, prelink = synthetic_parent(rows, folds)
        with mock.patch.object(candidate.shared, "fit_hgb_residual", side_effect=AssertionError("no parent fit")):
            receipt = candidate.replay_parent(rows, folds, parent, states, prelink)
        self.assertEqual((receipt["parent_rows_replayed"], receipt["parent_refits"]), (20, 0))
        for mode in ("state", "prelink", "probability", "missing"):
            bad_states, bad_prelink, bad_parent = copy.deepcopy(states), copy.deepcopy(prelink), dict(parent)
            if mode == "state":
                bad_states[1]["baseline_prediction"] += .01
            elif mode == "prelink":
                bad_prelink[next(iter(prelink))]["residual"] += .01
            elif mode == "probability":
                bad_parent[next(iter(parent))] += .01
            else:
                bad_prelink.pop(next(iter(prelink)))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                candidate.replay_parent(rows, folds, bad_parent, bad_states, bad_prelink)

    def test_portable_eight_file_parent_states_prelink_controls_source_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            contract, controls, frozen, expected_key = synthetic_parent_artifacts(Path(directory))
            with mock.patch.object(candidate.common.frozen_v0, "EXPECTED_CHECK_KEY_SHA256", expected_key):
                parent, states, residual = candidate.load_parent(contract, controls, frozen)
                self.assertEqual((len(parent), len(states), len(residual)), (87, 4, 87))
                for name in contract["research_parent"]["artifact_hashes"]:
                    bad = copy.deepcopy(contract)
                    bad["research_parent"]["artifact_hashes"][name] = "0" * 64
                    with self.subTest(name=name), self.assertRaises(ValueError):
                        candidate.load_parent(bad, controls, frozen)
                bad = copy.deepcopy(contract)
                bad["research_parent"]["state_sha256_by_fold"][0] = "0" * 64
                with self.assertRaises(ValueError):
                    candidate.load_parent(bad, controls, frozen)
                for field, value in (("outcome", 1), (candidate.ARM_RAW, .01), (candidate.ARM_ORDINARY, .01), (candidate.ARM_PARENT, .01)):
                    altered = copy.deepcopy(controls)
                    altered[next(iter(altered))][field] += value
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        candidate.load_parent(contract, altered, frozen)
                changed = copy.deepcopy(frozen)
                changed["hashes"] = {"drift": "0" * 64}
                with self.assertRaises(ValueError):
                    candidate.load_parent(contract, controls, changed)

    def test_full195_synthetic_fourfits87_exact_replay_and_original_judge(self):
        rows, folds, controls = problem()
        anchors = {row.game_id: {"game_id": row.game_id} for row in rows}
        contract = candidate.common.settlement._strict_json(candidate.CONTRACT)
        with mock.patch.object(old_tests, "synthetic_problem", return_value=(rows, folds, controls, anchors)), \
                mock.patch.object(candidate.common, "run", side_effect=candidate.run), \
                mock.patch.object(candidate, "require_dependencies", return_value=contract), \
                mock.patch.object(candidate, "load_parent", side_effect=full_parent_loader), \
                mock.patch.object(candidate, "solve_ridge", wraps=candidate.solve_ridge) as solve, \
                mock.patch.object(candidate.shared, "fit_hgb_residual", side_effect=AssertionError("no parent fit")), \
                mock.patch.object(candidate.common.base, "_atomic_json", wraps=candidate.common.base._atomic_json) as write, \
                mock.patch.object(candidate.shared, "write_predictions", wraps=candidate.shared.write_predictions) as csv_write:
            old_tests.FreshnessInteractionOffsetTests().test_complete_synthetic_run_has_exact87_predictions_and_hash_bound_artifacts()
        self.assertEqual(solve.call_count, 4)
        artifacts = {call.args[0].name: call.args[1] for call in write.call_args_list}
        card, predictions = artifacts["scorecard.json"], csv_write.call_args.args[1]
        self.assertEqual(card["source_denominator"]["events"], 195)
        self.assertEqual(card["source_denominator"]["excluded_events"], 2)
        self.assertEqual(card["actual_research_parent_id"], candidate.parent_module.TASK_ID)
        self.assertEqual(artifacts["input_receipts.json"]["parent_replay"]["parent_rows_replayed"], 87)
        for item in artifacts["predictor_states.json"]["folds"]:
            check = [prediction["row"] for prediction in predictions if prediction["fold"] == item["fold"]]
            self.assertEqual(candidate.replay_predictor(item["state"], check)[0],
                [prediction[candidate.ARM_CANDIDATE] for prediction in predictions if prediction["fold"] == item["fold"]])
        with mock.patch.object(candidate.common.base, "_group_bootstrap", return_value={"interval_95": [-.1, .1]}) as draws:
            paired = candidate.shared.paired_evidence(predictions, candidate.ARM_CANDIDATE)
        self.assertEqual(draws.call_count, 16)
        metrics, reports = card["aggregate"], card["folds"]
        decision = candidate.common.decision(metrics, reports, paired, candidate.ARM_CANDIDATE)
        changed = {**metrics, candidate.ARM_RESEARCH_PARENT: {"brier": 0., "log_loss": 0.}}
        self.assertEqual(decision, candidate.common.decision(changed, reports, paired, candidate.ARM_CANDIDATE))
        for metric in ("brier", "log_loss"):
            self.assertAlmostEqual(paired[f"candidate_minus_{candidate.ARM_RESEARCH_PARENT}"][metric]["equal_event_mean"],
                metrics[candidate.ARM_CANDIDATE][metric] - metrics[candidate.ARM_RESEARCH_PARENT][metric], places=15)
        date_diagnostics = card["per_schedule_date_correction_diagnostics"]
        self.assertEqual(len(date_diagnostics), 20)
        self.assertEqual(sum(item["events"] for item in date_diagnostics), 87)
        for item in date_diagnostics:
            block = [prediction for prediction in predictions if prediction["row"].game_date == item["game_date"]]
            self.assertEqual(item["events"], len(block))
            for arm, evidence in item["arms"].items():
                self.assertIn(arm, (candidate.ARM_CANDIDATE, candidate.ARM_RESEARCH_PARENT))
                energy = np.mean([(prediction[arm] - prediction[candidate.ARM_RAW]) ** 2 for prediction in block])
                alignment = np.mean([2 * (prediction[arm] - prediction[candidate.ARM_RAW])
                    * (prediction[candidate.ARM_RAW] - prediction["row"].trusted["outcome"]) for prediction in block])
                delta = np.mean([(prediction[arm] - prediction["row"].trusted["outcome"]) ** 2
                    - (prediction[candidate.ARM_RAW] - prediction["row"].trusted["outcome"]) ** 2 for prediction in block])
                self.assertAlmostEqual(evidence["equal_event_correction_energy"], float(energy), places=15)
                self.assertAlmostEqual(evidence["equal_event_signed_alignment"], float(alignment), places=15)
                self.assertAlmostEqual(evidence["equal_event_brier_delta_raw_identity"], float(delta), places=15)
                self.assertAlmostEqual(evidence["equal_event_correction_energy"]
                    + evidence["equal_event_signed_alignment"], float(delta), places=15)
        for key, value in candidate.common.BOUNDARY_FLAGS.items():
            self.assertEqual(card[key], value)

    def test_full_synthetic_firstfit_failure_partial_receipt_no_retry(self):
        rows, folds, controls = problem()
        anchors = {row.game_id: {"game_id": row.game_id} for row in rows}
        contract = candidate.common.settlement._strict_json(candidate.CONTRACT)
        partial = {"converged": False, "model_fits": 1, "retry_count": 0, "error": "synthetic direct solve failure"}
        with mock.patch.object(old_tests, "synthetic_problem", return_value=(rows, folds, controls, anchors)), \
                mock.patch.object(candidate.common, "run", side_effect=candidate.run), \
                mock.patch.object(candidate, "require_dependencies", return_value=contract), \
                mock.patch.object(candidate, "load_parent", side_effect=full_parent_loader), \
                mock.patch.object(candidate, "solve_ridge", side_effect=candidate.FitFailure("synthetic fit failure", partial)) as solve, \
                mock.patch.object(candidate.common.base, "_atomic_json", wraps=candidate.common.base._atomic_json) as write, \
                self.assertRaisesRegex(candidate.FitFailure, "synthetic fit failure"):
            old_tests.FreshnessInteractionOffsetTests().test_complete_synthetic_run_has_exact87_predictions_and_hash_bound_artifacts()
        self.assertEqual(solve.call_count, 1)
        artifacts = {call.args[0].name: call.args[1] for call in write.call_args_list}
        failure = artifacts["failure.json"]
        self.assertEqual(failure["automatic_retries"], 0)
        self.assertEqual(failure["fit_progress"]["fit_calls_entered"], 1)
        self.assertEqual(failure["fit_progress"]["fit_calls_completed"], 0)
        self.assertEqual(failure["solve_partial_receipt"], partial)
        self.assertNotIn("scorecard.json", artifacts)

    def test_admission_failure_before_fit_and_no_output_overwrite(self):
        with mock.patch.object(candidate.parent_module, "require_dependencies"), \
                mock.patch.object(candidate.common, "_sha256", return_value="0" * 64), self.assertRaises(ValueError):
            candidate.require_dependencies()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "failed"
            with mock.patch.object(candidate.common.base, "_validate_roots"), \
                    mock.patch.object(candidate, "require_dependencies", side_effect=ValueError("synthetic source drift")), \
                    mock.patch.object(candidate, "fit_ridge", side_effect=AssertionError("must not fit")), \
                    self.assertRaisesRegex(ValueError, "source drift"):
                candidate.run(Path(directory), output, allow_test_paths=True)
            with mock.patch.object(candidate.common.base, "_validate_roots"), self.assertRaises(FileExistsError):
                candidate.run(Path(directory), output, allow_test_paths=True)


if __name__ == "__main__":
    unittest.main()
