from __future__ import annotations

from collections import defaultdict
import copy
import csv
import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np

from experiments import nfl_ingame_market_temperature_offset as candidate
from experiments import test_nfl_ingame_market_freshness_interaction_offset as old_tests
from experiments import test_nfl_ingame_market_state_confidence_link_hgb as artifact_tests


def problem():
    return old_tests.synthetic_problem()


def expanded_problem():
    templates, folds, _, _ = problem()
    per_date = [5] * 20 + [3] * 2 + [6, 5, 5, 5, 5] + [4, 3, 3, 3, 3] + [6, 6, 6, 5, 5] + [4, 4, 3, 3, 3]
    rows = []
    for template, count in zip(templates, per_date, strict=True):
        for ordinal in range(count):
            game_id = f"{template.game_id}-{ordinal}"
            rows.append(candidate.common.base.InGameRow(game_id, template.game_date, template.game_week,
                {**template.trusted, "event_id": game_id, "market_id": f"market-{game_id}"},
                template.market_features, template.state_features, {**template.source_receipt, "game_id": game_id}))
    rows.sort(key=lambda row: row.key)
    return rows, folds


def isotonic_state(fold):
    """Direct numeric thresholds, not a fitted scientific parent."""
    return {"schema": "identity_blended_isotonic_numeric_state_v1",
        "constructor_params": dict(candidate.parent_module.ISOTONIC_PARAMS),
        "blend_weight": .25, "sample_weight": None,
        "fit_events": (106, 132, 148, 176)[fold - 1],
        "X_thresholds_": [.2, .8], "y_thresholds_": [.1, .9],
        "X_min_": .2, "X_max_": .8}


def synthetic_parent(rows, folds):
    by_date = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    probabilities, states = {}, {}
    for fold in folds:
        state = isotonic_state(fold["fold"])
        states[fold["fold"]] = state
        check = sorted([row for day in fold["check_dates"] for row in by_date[day]], key=lambda row: row.key)
        raw = candidate.parent_module.raw_probabilities(check)
        values = candidate.parent_module.replay_isotonic(state, raw)
        probabilities.update({row.key: p for row, p in zip(check, values, strict=True)})
    return probabilities, states


def full_parent_loader(contract, controls, frozen):
    anchors = {state["game_id"]: state for state in frozen["anchors"]}
    cohort = candidate.common.base._validate_source(None)
    rows = [candidate.common.base._load_dynamic_market(None, item, anchors[item["game_id"]])
        for item in cohort if "exclusion" not in item]
    rows.sort(key=lambda row: row.key)
    return synthetic_parent(rows, frozen["folds"])


def synthetic_parent_artifacts(root):
    evidence, controls, frozen, expected_key = artifact_tests.synthetic_parent_artifacts(root)
    frozen.update({"hashes": {}, "receipts": {"pbp_receipts": [], "materialized_receipts": []}})
    states = {"task_id": candidate.parent_module.TASK_ID, "folds": []}
    card = {"task_id": candidate.parent_module.TASK_ID, "folds": []}
    for fold in range(1, 5):
        state = isotonic_state(fold)
        digest = candidate.common._digest(state)
        states["folds"].append({"fold": fold, "state": state, "state_sha256": digest})
        card["folds"].append({"fold": fold, "fit_events": state["fit_events"],
            "trainer": {"predictor_state_sha256": digest}})
    rows = candidate.common.frozen_v0._read_csv(root / "predictions.csv")
    for row in rows:
        state = states["folds"][int(row["fold"]) - 1]["state"]
        row["candidate_probability"] = str(candidate.parent_module.replay_isotonic(state,
            [float(row["raw_market_probability"])])[0])
    with (root / "predictions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    receipts = {"task_id": candidate.parent_module.TASK_ID,
        "runner_sha256": "489d8268bd5243d94df9396f6dd5d616acfeab2d23f29d0e9e5903b7f156cce5",
        "controller_contract_sha256": candidate.parent_module.CONTRACT_SHA256,
        "v0_artifact_hashes": frozen["hashes"], **frozen["receipts"], **candidate.common.BOUNDARY_FLAGS}
    lock = {"task_id": candidate.parent_module.TASK_ID,
        "controller_contract_sha256": candidate.parent_module.CONTRACT_SHA256}
    exclusions = {"source_events": 195, "materialized_events": 193, "excluded_events": 2,
        "exclusions": [{"game_id": game_id, "reason": reason}
            for game_id, reason in candidate.common.identity.EXPECTED_EXCLUSIONS]}
    for name, value in (("predictor_states", states), ("scorecard", card), ("input_receipts", receipts),
            ("pre_score_lock", lock), ("exclusions", exclusions)):
        candidate.common.base._atomic_json(root / f"{name}.json", value)
    manifest = candidate.common.settlement._strict_json(root / "manifest.json")
    manifest["task_id"] = candidate.parent_module.TASK_ID
    for name in ("predictor_states", "scorecard", "input_receipts", "pre_score_lock", "exclusions"):
        manifest[f"{name}_sha256"] = candidate.common._sha256(root / f"{name}.json")
    manifest["predictions_sha256"] = candidate.common._sha256(root / "predictions.csv")
    candidate.common.base._atomic_json(root / "manifest.json", manifest)
    files = ("manifest.json", "input_receipts.json", "pre_score_lock.json", "exclusions.json",
        "predictor_states.json", "scorecard.json", "predictions.csv")
    hashes = {name: candidate.common._sha256(root / name) for name in files}
    evidence["research_parent"].update({"candidate_id": candidate.parent_module.TASK_ID,
        "runner_sha256": receipts["runner_sha256"], "artifact_hashes": hashes,
        "state_schema": "identity_blended_isotonic_numeric_state_v1",
        "controller_contract_sha256": candidate.parent_module.CONTRACT_SHA256,
        "state_sha256_by_fold": [item["state_sha256"] for item in states["folds"]],
        **{name.split(".")[0] + "_sha256": digest for name, digest in hashes.items()}})
    return evidence, controls, frozen, expected_key


class MarketTemperatureOffsetTests(unittest.TestCase):
    def test_objective_gradient_hessian_finite_differences_and_identity_prior(self):
        logits = np.asarray([-2., -.7, .1, .8, 2.4])
        y = np.asarray([0., 1., 0., 1., 1.])
        beta, step = .21, 1e-5
        value, gradient, hessian = candidate.objective_gradient_hessian(beta, logits, y)
        eta = (1 + beta) * logits
        q = 1 / (1 + np.exp(-eta))
        expected = float(np.sum(np.logaddexp(0, eta) - y * eta) + 8 * beta ** 2)
        self.assertAlmostEqual(value, expected, places=14)
        self.assertAlmostEqual(gradient, float(np.sum((q - y) * logits) + 16 * beta), places=14)
        self.assertAlmostEqual(hessian, float(np.sum(q * (1 - q) * logits ** 2) + 16), places=14)
        hi = candidate.objective_gradient_hessian(beta + step, logits, y)
        lo = candidate.objective_gradient_hessian(beta - step, logits, y)
        self.assertAlmostEqual(gradient, (hi[0] - lo[0]) / (2 * step), places=7)
        self.assertAlmostEqual(hessian, (hi[1] - lo[1]) / (2 * step), places=7)
        self.assertGreaterEqual(hessian, 16)
        self.assertAlmostEqual(candidate.objective_gradient_hessian(0., logits, y)[0],
            float(np.sum(np.logaddexp(0, logits) - y * logits)), places=14)

    def test_interior_fit_exact_bracket_stationarity_determinism_and_one_call(self):
        logits = np.asarray([-2., -.7, .1, .8, 2.4])
        y = np.asarray([0., 1., 0., 1., 1.])
        with mock.patch.object(candidate, "objective_gradient_hessian", wraps=candidate.objective_gradient_hessian) as evaluate:
            beta, receipt = candidate.solve_temperature(logits, y)
        self.assertEqual((beta, receipt), candidate.solve_temperature(logits, y))
        value, gradient, hessian = candidate.objective_gradient_hessian(beta, logits, y)
        self.assertGreater(beta, -1)
        self.assertLessEqual(abs(gradient), 1e-8)
        self.assertGreaterEqual(hessian, 16)
        self.assertLessEqual(value, candidate.objective_gradient_hessian(0., logits, y)[0] + 1e-8)
        self.assertTrue(receipt["converged"])
        self.assertLessEqual(receipt["bisection_steps"], 200)
        self.assertEqual(receipt["initial_bracket"], [-1., 1 + float(np.sum(np.abs(logits))) / 16])
        self.assertEqual(receipt["evaluations"], evaluate.call_count)
        self.assertEqual((receipt["optimization_calls_started"], receipt["optimization_calls_completed"]), (1, 1))
        lower, upper = receipt["initial_bracket"]
        self.assertLess(candidate.objective_gradient_hessian(lower, logits, y)[1], 0)
        self.assertGreater(candidate.objective_gradient_hessian(upper, logits, y)[1], 0)

    def test_lower_bound_KKT_and_all_zero_logits_identity(self):
        logits, y = np.full(30, 4.), np.zeros(30)
        beta, receipt = candidate.solve_temperature(logits, y)
        self.assertEqual(beta, -1)
        value, gradient, hessian = candidate.objective_gradient_hessian(beta, logits, y)
        self.assertGreaterEqual(gradient, 0)
        self.assertEqual(max(0., -gradient), 0.)
        self.assertGreaterEqual(hessian, 16)
        self.assertTrue(receipt["converged"])
        self.assertEqual(receipt["bisection_steps"], 0)
        zero, zero_receipt = candidate.solve_temperature(np.zeros(8), np.arange(8) % 2)
        self.assertEqual(zero, 0.)
        self.assertTrue(zero_receipt["converged"])
        self.assertLessEqual(value, candidate.objective_gradient_hessian(0., logits, y)[0])

    def test_bounded_iteration_failure_preserves_truth_and_never_retries(self):
        def nonstationary(beta, logits, y):
            return 1., (-1. if beta == -1 else 1.), 16.
        with mock.patch.object(candidate, "objective_gradient_hessian", side_effect=nonstationary) as evaluate, \
                self.assertRaises(candidate.FitFailure) as failure:
            candidate.solve_temperature([1., -1.], [1., 0.])
        receipt = failure.exception.receipt
        self.assertFalse(receipt["converged"])
        self.assertLessEqual(receipt["bisection_steps"], 200)
        self.assertEqual(receipt["evaluations"], evaluate.call_count)
        self.assertEqual(receipt["optimization_calls_started"], 1)
        self.assertEqual(receipt["optimization_calls_completed"], 0)

    def test_nonfinite_bad_curvature_or_throw_terminal_without_fallback(self):
        for invalid in ((math.nan, 0., 16.), (1., math.nan, 16.), (1., 0., math.inf), (1., 0., 15.)):
            with self.subTest(invalid=invalid), mock.patch.object(candidate, "objective_gradient_hessian", return_value=invalid) as evaluate, \
                    self.assertRaises(candidate.FitFailure) as failure:
                candidate.solve_temperature([1.], [1.])
            self.assertFalse(failure.exception.receipt["converged"])
            self.assertEqual(failure.exception.receipt["evaluations"], evaluate.call_count)
            self.assertEqual(evaluate.call_count, 1)
        with mock.patch.object(candidate, "objective_gradient_hessian", side_effect=ValueError("synthetic evaluation throw")) as evaluate, \
                self.assertRaises(candidate.FitFailure) as failure:
            candidate.solve_temperature([1.], [1.])
        self.assertEqual(evaluate.call_count, 1)
        self.assertEqual(failure.exception.receipt["evaluations"], 1)

    def test_invalid_optimizer_inputs_fail_closed(self):
        for logits, y in (([], []), ([math.nan], [1.]), ([1.], [math.nan]), ([1.], [.2]), ([1.], [1., 0.])):
            with self.subTest(logits=logits, y=y), self.assertRaises(ValueError):
                candidate.solve_temperature(logits, y)

    def test_synthetic_fit_numeric_replay_zero_identity_probability_bounds(self):
        rows, _, _, _ = problem()
        values, report = candidate.fit_temperature(rows[:22], rows[22:])
        self.assertEqual((values, report), candidate.fit_temperature(rows[:22], rows[22:]))
        state = report["primitive_prediction_state"]
        self.assertEqual(values, candidate.replay_predictor(state, rows[22:])[0])
        self.assertEqual(state["temperature"], 1 + state["beta"])
        self.assertEqual((state["alpha"], state["intercept"], state["normalization"], state["sample_weights"]), (16, 0, "none", None))
        self.assertEqual(state["feature_columns"], ["market_logit"])
        self.assertEqual(report["predictor_state_sha256"], candidate.common._digest(state))
        raw = [row.trusted["market_probability"] for row in rows[22:]]
        self.assertEqual(candidate.probabilities(0., rows[22:])[0], raw)
        boundary, _ = candidate.probabilities(-1., rows[22:])
        self.assertEqual(boundary, [.5] * len(boundary))
        extreme, bound = candidate.probabilities(1000., rows[22:])
        epsilon = candidate.common.probability_contract.DEFAULT_PROBABILITY_POLICY.epsilon
        self.assertTrue(all(epsilon <= q <= 1 - epsilon for q in extreme))
        self.assertGreater(bound["clipped_rows"], 0)
        self.assertEqual(bound["rows_removed"], 0)
        # Training is unbounded logit NLL; only final scored probabilities clamp.
        selected = [rows[0], rows[-1]]
        logits = np.asarray([row.market_features[0] for row in selected])
        outcomes = np.asarray([1., 0.])
        objective = candidate.objective_gradient_hessian(1000., logits, outcomes)[0]
        bounded, _ = candidate.probabilities(1000., selected)
        scored_nll = float(np.sum(-outcomes * np.log(bounded) - (1 - outcomes) * np.log1p(-np.asarray(bounded))))
        self.assertGreater(objective - 8 * 1000 ** 2, scored_nll + 100)
        with self.assertRaises(ValueError):
            candidate.probabilities(-1.0001, rows[22:])

    def test_check_labels_state_future_and_check_prices_do_not_change_fit(self):
        rows, _, _, _ = problem()
        _, first = candidate.fit_temperature(rows[:22], rows[22:])
        poison = [candidate.common.base.InGameRow(row.game_id, row.game_date, row.game_week,
            {**row.trusted, "outcome": 1 - row.trusted["outcome"], "future_final_score": np.nan},
            row.market_features, (np.nan,) * 9, {"future": True}) for row in rows[22:]]
        _, second = candidate.fit_temperature(rows[:22], poison)
        changed = [candidate.common.base.InGameRow(row.game_id, row.game_date, row.game_week,
            {**row.trusted, "market_probability": .5}, (0.,), row.state_features, row.source_receipt) for row in poison]
        _, third = candidate.fit_temperature(rows[:22], changed)
        a, b, c = [item["primitive_prediction_state"] for item in (first, second, third)]
        self.assertEqual(a, b)
        self.assertEqual({key: value for key, value in a.items() if key != "raw_check_sha256"},
            {key: value for key, value in c.items() if key != "raw_check_sha256"})
        self.assertNotEqual(a["raw_check_sha256"], c["raw_check_sha256"])

    def test_saved_predictor_and_raw_logit_drift_fail_closed(self):
        rows, _, _, _ = problem()
        _, report = candidate.fit_temperature(rows[:22], rows[22:])
        state = report["primitive_prediction_state"]
        for change in ({"beta": math.nan}, {"temperature": 99.}, {"alpha": 8.}, {"intercept": .1},
                {"normalization": "fit_std"}, {"lower_bound": -2.}, {"sample_weights": [1.]}, {"feature_columns": ["future"]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                candidate.replay_predictor({**state, **change}, rows[22:])
        for field in ("KKT", "hessian", "F", "F_zero", "gradient"):
            for invalid in (math.nan, math.inf):
                bad = copy.deepcopy(state)
                bad["optimizer"][field] = invalid
                with self.subTest(field=field, invalid=invalid), self.assertRaises(ValueError):
                    candidate.replay_predictor(bad, rows[22:])
        for field, value in (("KKT", -1.), ("gradient", 1.)):
            bad = copy.deepcopy(state)
            bad["optimizer"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                candidate.replay_predictor(bad, rows[22:])
        altered = candidate.common.base.InGameRow(rows[0].game_id, rows[0].game_date, rows[0].game_week,
            rows[0].trusted, (rows[0].market_features[0] + .1,), rows[0].state_features, rows[0].source_receipt)
        with self.assertRaises(ValueError):
            candidate.fit_temperature([altered, *rows[1:22]], rows[22:])

    def test_postsolver_probability_failure_keeps_converged_receipt(self):
        rows, _, _, _ = problem()
        with mock.patch.object(candidate, "probabilities", side_effect=ValueError("synthetic output failure")), \
                self.assertRaisesRegex(candidate.FitFailure, "output failure") as failure:
            candidate.fit_temperature(rows[:22], rows[22:])
        self.assertTrue(failure.exception.receipt["converged"])
        returned = {"converged": True, "optimization_calls_started": 1,
            "optimization_calls_completed": 1, "evaluations": 4, "bisection_steps": 1}
        with mock.patch.object(candidate, "solve_temperature", return_value=(math.nan, returned)) as solve, \
                self.assertRaisesRegex(candidate.FitFailure, "invalid beta") as failure:
            candidate.fit_temperature(rows[:22], rows[22:])
        self.assertEqual(solve.call_count, 1)
        self.assertTrue(failure.exception.receipt["converged"])
        self.assertEqual(failure.exception.receipt["optimization_calls_completed"], 1)
        self.assertIn("post_optimization_prediction_error", failure.exception.receipt)

    def test_C1_exact_parent_interpolation_no_fit_and_numeric_drift(self):
        rows, folds = expanded_problem()
        parent, states = synthetic_parent(rows, folds)
        with mock.patch.object(candidate.parent_module, "fit_isotonic", side_effect=AssertionError("no parentfit")):
            receipt = candidate.replay_parent(rows, folds, parent, states)
        self.assertEqual((receipt["parent_rows_replayed"], receipt["parent_refits"]), (87, 0))
        for mode in ("state", "probability", "missing"):
            bad_state, bad_parent = copy.deepcopy(states), dict(parent)
            if mode == "state":
                bad_state[1]["y_thresholds_"][0] += .01
            elif mode == "probability":
                bad_parent[next(iter(bad_parent))] += .01
            else:
                bad_state.pop(1)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                candidate.replay_parent(rows, folds, bad_parent, bad_state)

    def test_portable_seven_parent_files_four_states_control_receipt_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            contract, controls, frozen, expected_key = synthetic_parent_artifacts(Path(directory))
            with mock.patch.object(candidate.common.frozen_v0, "EXPECTED_CHECK_KEY_SHA256", expected_key):
                parent, states = candidate.load_parent(contract, controls, frozen)
                self.assertEqual((len(parent), len(states)), (87, 4))
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
                    changed = copy.deepcopy(controls)
                    changed[next(iter(changed))][field] += value
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        candidate.load_parent(contract, changed, frozen)
                changed = copy.deepcopy(frozen)
                changed["hashes"] = {"drift": "0" * 64}
                with self.assertRaises(ValueError):
                    candidate.load_parent(contract, controls, changed)

    def test_full195_synthetic_fourfits87_replay_dates_paired_original_judge(self):
        contract = candidate.common.settlement._strict_json(candidate.CONTRACT)
        with mock.patch.object(candidate.common, "run", side_effect=candidate.run), \
                mock.patch.object(candidate, "require_dependencies", return_value=contract), \
                mock.patch.object(candidate, "load_parent", side_effect=full_parent_loader), \
                mock.patch.object(candidate, "solve_temperature", wraps=candidate.solve_temperature) as solve, \
                mock.patch.object(candidate.parent_module, "fit_isotonic", side_effect=AssertionError("no parentfit")), \
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
        self.assertEqual(len(card["aggregate"]), 5)
        for item in artifacts["predictor_states.json"]["folds"]:
            check = [p["row"] for p in predictions if p["fold"] == item["fold"]]
            self.assertEqual(candidate.replay_predictor(item["state"], check)[0],
                [p[candidate.ARM_CANDIDATE] for p in predictions if p["fold"] == item["fold"]])
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
        evidence = card["per_schedule_date_correction_diagnostics"]
        self.assertEqual(len(evidence), 20)
        self.assertEqual(sum(item["events"] for item in evidence), 87)
        for item in evidence:
            block = [p for p in predictions if p["row"].game_date == item["game_date"]]
            self.assertEqual(item["events"], len(block))
            for arm, result in item["arms"].items():
                energy = np.mean([(p[arm] - p[candidate.ARM_RAW]) ** 2 for p in block])
                alignment = np.mean([2 * (p[arm] - p[candidate.ARM_RAW])
                    * (p[candidate.ARM_RAW] - p["row"].trusted["outcome"]) for p in block])
                delta = np.mean([(p[arm] - p["row"].trusted["outcome"]) ** 2
                    - (p[candidate.ARM_RAW] - p["row"].trusted["outcome"]) ** 2 for p in block])
                self.assertAlmostEqual(result["equal_event_correction_energy"], float(energy), places=15)
                self.assertAlmostEqual(result["equal_event_signed_alignment"], float(alignment), places=15)
                self.assertAlmostEqual(result["equal_event_brier_delta_raw_identity"], float(delta), places=15)
                self.assertAlmostEqual(float(energy + alignment), float(delta), places=15)
        for key, value in candidate.common.BOUNDARY_FLAGS.items():
            self.assertEqual(card[key], value)

    def test_full_synthetic_fit_failure_partial_receipt_no_retry_or_scorecard(self):
        contract = candidate.common.settlement._strict_json(candidate.CONTRACT)
        partial = {"converged": False, "optimization_calls_started": 1,
            "optimization_calls_completed": 0, "evaluations": 1, "bisection_steps": 0,
            "error": "synthetic scalar fit failure"}
        with mock.patch.object(candidate.common, "run", side_effect=candidate.run), \
                mock.patch.object(candidate, "require_dependencies", return_value=contract), \
                mock.patch.object(candidate, "load_parent", side_effect=full_parent_loader), \
                mock.patch.object(candidate, "solve_temperature", side_effect=candidate.FitFailure("synthetic fit failure", partial)) as solve, \
                mock.patch.object(candidate.common.base, "_atomic_json", wraps=candidate.common.base._atomic_json) as write, \
                self.assertRaisesRegex(candidate.FitFailure, "synthetic fit failure"):
            old_tests.FreshnessInteractionOffsetTests().test_complete_synthetic_run_has_exact87_predictions_and_hash_bound_artifacts()
        self.assertEqual(solve.call_count, 1)
        artifacts = {call.args[0].name: call.args[1] for call in write.call_args_list}
        failure = artifacts["failure.json"]
        self.assertEqual(failure["automatic_retries"], 0)
        self.assertEqual(failure["fit_progress"]["fit_calls_entered"], 1)
        self.assertEqual(failure["fit_progress"]["fit_calls_completed"], 0)
        self.assertEqual(failure["optimizer_partial_receipt"], partial)
        self.assertNotIn("scorecard.json", artifacts)

    def test_admission_failure_before_fit_and_no_output_overwrite(self):
        with mock.patch.object(candidate.parent_module, "require_dependencies"), \
                mock.patch.object(candidate.common, "_sha256", return_value="0" * 64), self.assertRaises(ValueError):
            candidate.require_dependencies()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "failed"
            with mock.patch.object(candidate.common.base, "_validate_roots"), \
                    mock.patch.object(candidate, "require_dependencies", side_effect=ValueError("synthetic source drift")), \
                    mock.patch.object(candidate, "fit_temperature", side_effect=AssertionError("must not fit")), \
                    self.assertRaisesRegex(ValueError, "source drift"):
                candidate.run(Path(directory), output, allow_test_paths=True)
            with mock.patch.object(candidate.common.base, "_validate_roots"), self.assertRaises(FileExistsError):
                candidate.run(Path(directory), output, allow_test_paths=True)


if __name__ == "__main__":
    unittest.main()
