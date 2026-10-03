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

from experiments import nfl_ingame_market_state_confidence_link_hgb as candidate
from experiments import test_nfl_ingame_market_freshness_interaction_offset as old_tests
from experiments.test_nfl_ingame_market_residual_hgb import synthetic_problem


def synthetic_frozen_parent(rows, folds):
    by_date = defaultdict(list)
    for row in rows:
        by_date[row.game_date].append(row)
    probabilities, states, reports = {}, {}, {}
    for fold in folds:
        check = sorted([row for day in fold["check_dates"] for row in by_date.get(day, [])], key=lambda row: row.key)
        fit, _ = candidate.shared.common.nested._strict_prior_rows(by_date, fold["fit_dates"], check)
        values, report = candidate.shared.fit_hgb_residual(fit, check, include_state=True)
        states[fold["fold"]] = report["primitive_prediction_state"]
        reports[fold["fold"]] = report
        probabilities.update({row.key: value for row, value in zip(check, values, strict=True)})
    return probabilities, states, reports


def synthetic_parent_artifacts(root):
    names = ["market_logit", "market_staleness_seconds", *candidate.shared.common.base.STATE_FEATURE_NAMES]
    task = "InGameMarketStateResidualHGB-v1"
    artifact = {"schema": "hgb_numeric_prediction_states_v1", "task_id": task, "folds": []}
    scorecard = {"task_id": task, "folds": []}
    for fold in (1, 2, 3, 4):
        state = {"schema": "hgb_numeric_prediction_state_v1", "baseline_prediction": fold / 100,
            "feature_names": names, "constructor_params": dict(candidate.shared.HGB_PARAMS),
            "stage_count": 64, "leaf_values_include_learning_rate": True,
            "trees": [[{"value": .001, "feature_idx": 0, "num_threshold": 0., "left": 0,
                "right": 0, "is_leaf": 1, "missing_go_to_left": 1}] for _ in range(64)]}
        digest = candidate.shared.common._digest(state)
        artifact["folds"].append({"fold": fold, "state_sha256": digest, "state": state})
        scorecard["folds"].append({"fold": fold, "trainer": {"predictor_state_sha256": digest}})
    rows, controls, frozen = [], {}, {"predictions": []}
    for fold, count in enumerate((26, 16, 28, 17), start=1):
        state = artifact["folds"][fold - 1]["state"]
        f = candidate.shared.predict_primitive(state, np.zeros((1, 11)))[0]
        parent_probability = candidate.shared.bound_probabilities([.5], [f])[0][0]
        for ordinal in range(count):
            index = len(rows)
            key = (f"synthetic-event-{index}", f"synthetic-market-{index}", (10000 + index) * 1000)
            row = {"fold": str(fold), "game_id": f"synthetic-game-{index}", "game_date": f"2025-01-{fold:02}",
                "game_week": str(fold), "event_id": key[0], "market_id": key[1], "cutoff_ms": str(key[2]),
                "outcome_available_ms": str(key[2] + 1), "outcome": str(ordinal % 2),
                "raw_market_probability": ".5", "frozen_v0_ordinary_market_only_probability": ".51",
                "frozen_v0_market_plus_state_parent_probability": ".49", "candidate_probability": str(parent_probability)}
            rows.append(row)
            controls[key] = {"fold": fold, "game_id": row["game_id"], "game_date": row["game_date"],
                "game_week": row["game_week"], "outcome": int(row["outcome"]), candidate.ARM_RAW: .5,
                candidate.ARM_ORDINARY: .51, candidate.ARM_PARENT: .49}
            frozen["predictions"].append({"event_id": key[0], "market_id": key[1], "cutoff_ms": str(key[2]),
                "outcome_available_ms": str(key[2] + 1)})
    with (root / "predictions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for name, value in (("pre_score_lock", {"synthetic": True, "feature_names": names}),
            ("predictor_states", artifact), ("scorecard", scorecard)):
        candidate.shared.common.base._atomic_json(root / f"{name}.json", value)
    manifest = {"complete": True, "task_id": task, "model_fits": 4, "check_events": 87,
        **{f"{name}_sha256": candidate.shared.common._sha256(root / f"{name}.{suffix}") for name, suffix in (
            ("predictions", "csv"), ("scorecard", "json"), ("pre_score_lock", "json"), ("predictor_states", "json"))}}
    candidate.shared.common.base._atomic_json(root / "manifest.json", manifest)
    contract = {"research_parent": {"candidate_id": task, "artifact_root": str(root),
        "manifest_sha256": candidate.shared.common._sha256(root / "manifest.json"),
        **{key: value for key, value in manifest.items() if key.endswith("_sha256")}},
        "fixed_training_recipe": {"feature_names": names}}
    expected_key = candidate.shared.common._digest([list(candidate.shared.common.identity._control_key(row)) for row in rows])
    return contract, controls, frozen, expected_key


class MarketStateConfidenceLinkTests(unittest.TestCase):
    def test_exact_zero_raw_sign_endpoint_bounds_and_nonfinite_rejection(self):
        raw = [.15, .251, .81]
        self.assertEqual(candidate.link_probabilities(raw, [0., 0., 0.])[0], raw)
        positive = candidate.link_probabilities(raw, [.1] * 3)[0]
        negative = candidate.link_probabilities(raw, [-.1] * 3)[0]
        self.assertTrue(all(value > baseline for value, baseline in zip(positive, raw)))
        self.assertTrue(all(value < baseline for value, baseline in zip(negative, raw)))
        values, report = candidate.link_probabilities([.5, .5], [-100., 100.])
        epsilon = candidate.shared.common.probability_contract.DEFAULT_PROBABILITY_POLICY.epsilon
        self.assertEqual(values, [epsilon, 1 - epsilon])
        self.assertEqual((report["clipped_rows"], report["rows_removed"]), (2, 0))
        for residual in ([math.nan], [math.inf], []):
            with self.assertRaises(ValueError):
                candidate.link_probabilities([.5], residual)
        with self.assertRaisesRegex(ValueError, "misaligned"):
            candidate.link_probabilities([.5], [.1, .2])

    def test_local_derivative_bound_and_finite_f_not_linear_approximation(self):
        h = 1e-6
        for raw in (.1, .25, .5, .8):
            high = candidate.link_probabilities([raw], [h])[0][0]
            low = candidate.link_probabilities([raw], [-h])[0][0]
            self.assertAlmostEqual((high - low) / (2 * h), 4 * raw * (1 - raw), places=8)
            for f in (-.2, .2):
                q = candidate.link_probabilities([raw], [f])[0][0]
                expected = candidate.expit(math.log(raw / (1 - raw)) + 4 * f)
                self.assertEqual(q, float(expected))
                high = candidate.link_probabilities([raw], [f + h])[0][0]
                low = candidate.link_probabilities([raw], [f - h])[0][0]
                derivative = (high - low) / (2 * h)
                self.assertGreater(derivative, 0)
                self.assertLessEqual(derivative, 1 + 1e-9)
                self.assertLessEqual(abs(q - raw), abs(f) + 1e-15)
        raw, f = .1, .2
        mapped = candidate.link_probabilities([raw], [f])[0][0]
        self.assertNotAlmostEqual(mapped, raw + 4 * raw * (1 - raw) * f, places=6)

    def test_four_synthetic_fits_exact_states_and_prelink_parent_parity(self):
        rows, folds, controls = synthetic_problem()
        parent, states, _ = synthetic_frozen_parent(rows, folds)
        with mock.patch.object(candidate.shared, "fit_hgb_residual", wraps=candidate.shared.fit_hgb_residual) as fit:
            predictions, reports = candidate.fit_and_predict(rows, folds, controls, parent, states)
        self.assertEqual(fit.call_count, 4)
        self.assertEqual({item["row"].key for item in predictions}, set(controls))
        self.assertEqual(sum(item["trainer"]["prelink_rows_checked"] for item in reports), 20)
        self.assertTrue(all(item["trainer"]["canonical_b2_state_exact"] for item in reports))
        for item in reports:
            self.assertEqual(item["trainer"]["predictor_state_sha256"], candidate.shared.common._digest(states[item["fold"]]))
            self.assertEqual(item["trainer"]["constructor_params"], candidate.shared.HGB_PARAMS)
            self.assertEqual((item["trainer"]["n_iter"], item["trainer"]["input_columns"]), (64, 11))
        for item in predictions:
            self.assertEqual(item[candidate.ARM_RESEARCH_PARENT], parent[item["row"].key])
            self.assertEqual(item[candidate.ARM_CANDIDATE], candidate.link_probabilities(
                [item[candidate.ARM_RAW]], [item["prelink_residual"]])[0][0])

    def test_state_residual_and_parent_probability_parity_drift_fail_closed(self):
        rows, folds, controls = synthetic_problem()
        parent, states, reports = synthetic_frozen_parent(rows, folds)
        changed = copy.deepcopy(states)
        changed[1]["baseline_prediction"] += .01
        with self.assertRaisesRegex(ValueError, "canonical state"):
            candidate.fit_and_predict(rows, folds, controls, parent, changed)
        changed_parent = dict(parent)
        changed_parent[next(iter(changed_parent))] += .001
        with self.assertRaisesRegex(ValueError, "probability parity"):
            candidate.fit_and_predict(rows, folds, controls, changed_parent, states)
        checks = sorted([row for row in rows if row.game_date in folds[0]["check_dates"]], key=lambda row: row.key)
        residual = candidate.shared.predict_primitive(states[1], candidate.shared.feature_matrix(checks, include_state=True))
        report = copy.deepcopy(reports[1])
        values = [parent[row.key] for row in checks]
        with mock.patch.object(candidate.shared, "fit_hgb_residual", return_value=(values, report)), \
                mock.patch.object(candidate.shared, "predict_primitive", side_effect=[residual, residual + .001]):
            with self.assertRaisesRegex(ValueError, "residual"):
                candidate.fit_and_predict(rows, folds, controls, parent, states)

    def test_synthetic_parent_metadata_hash_binding_and_four_states(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract, controls, frozen, expected_key = synthetic_parent_artifacts(root)
            with mock.patch.object(candidate.shared.common.frozen_v0, "EXPECTED_CHECK_KEY_SHA256", expected_key):
                parent, states = candidate.load_parent(contract, controls, frozen)
                self.assertEqual((len(parent), len(states)), (87, 4))
                for field in ("manifest", "pre_score_lock", "predictor_states", "scorecard", "predictions"):
                    bad = copy.deepcopy(contract)
                    bad["research_parent"][f"{field}_sha256"] = "0" * 64
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        candidate.load_parent(bad, controls, frozen)
                bad_controls = copy.deepcopy(controls)
                key = next(iter(bad_controls))
                bad_controls[key]["outcome"] = 1 - bad_controls[key]["outcome"]
                with self.assertRaisesRegex(ValueError, "label"):
                    candidate.load_parent(contract, bad_controls, frozen)
                bad_controls = copy.deepcopy(controls)
                bad_controls[key][candidate.ARM_ORDINARY] += .01
                with self.assertRaisesRegex(ValueError, "comparator"):
                    candidate.load_parent(contract, bad_controls, frozen)
                missing = dict(controls)
                missing.pop(key)
                with self.assertRaisesRegex(ValueError, "key"):
                    candidate.load_parent(contract, missing, frozen)
                # Rebind only synthetic outer file hashes to exercise inner state/task/binding checks.
                for mode in ("state_hash", "state_count", "artifact_task", "manifest_task", "prelock_binding", "file_bytes"):
                    contract, controls, frozen, _ = synthetic_parent_artifacts(root)
                    artifact = candidate.shared.common.settlement._strict_json(root / "predictor_states.json")
                    manifest = candidate.shared.common.settlement._strict_json(root / "manifest.json")
                    if mode == "state_hash":
                        artifact["folds"][0]["state"]["baseline_prediction"] += .001
                    elif mode == "state_count":
                        artifact["folds"].pop()
                    elif mode == "artifact_task":
                        artifact["task_id"] = "wrong-task"
                    elif mode == "manifest_task":
                        manifest["task_id"] = "wrong-task"
                    elif mode == "prelock_binding":
                        manifest["pre_score_lock_sha256"] = "0" * 64
                    elif mode == "file_bytes":
                        candidate.shared.common.base._atomic_json(root / "pre_score_lock.json", {"changed": True})
                    candidate.shared.common.base._atomic_json(root / "predictor_states.json", artifact)
                    state_hash = candidate.shared.common._sha256(root / "predictor_states.json")
                    manifest["predictor_states_sha256"] = state_hash
                    contract["research_parent"]["predictor_states_sha256"] = state_hash
                    candidate.shared.common.base._atomic_json(root / "manifest.json", manifest)
                    contract["research_parent"]["manifest_sha256"] = candidate.shared.common._sha256(root / "manifest.json")
                    with self.subTest(mode=mode), self.assertRaises(ValueError):
                        candidate.load_parent(contract, controls, frozen)

    def test_energy_alignment_identity_parent_pairing_and_unchanged_keep(self):
        rows, folds, controls = synthetic_problem()
        parent, states, _ = synthetic_frozen_parent(rows, folds)
        predictions, reports = candidate.fit_and_predict(rows, folds, controls, parent, states)
        metrics = candidate.shared.aggregate(predictions, candidate.ARM_CANDIDATE)
        diagnostics = candidate.correction_diagnostics(predictions)
        for arm in (candidate.ARM_CANDIDATE, candidate.ARM_RESEARCH_PARENT):
            self.assertAlmostEqual(diagnostics[arm]["equal_event_brier_delta_raw_identity"],
                metrics[arm]["brier"] - metrics[candidate.ARM_RAW]["brier"], places=15)
        with mock.patch.object(candidate.shared.common.base, "_group_bootstrap", return_value={"interval_95": [-.1, .1]}) as bootstrap:
            paired = candidate.shared.paired_evidence(predictions, candidate.ARM_CANDIDATE)
        self.assertEqual(bootstrap.call_count, 16)
        decision = candidate.shared.common.decision(metrics, reports, paired, candidate.ARM_CANDIDATE)
        altered = {**metrics, candidate.ARM_RESEARCH_PARENT: {"brier": 0., "log_loss": 0.}}
        self.assertEqual(candidate.shared.common.decision(altered, reports, paired, candidate.ARM_CANDIDATE), decision)
        for metric in ("brier", "log_loss"):
            self.assertAlmostEqual(paired[f"candidate_minus_{candidate.ARM_RESEARCH_PARENT}"][metric]["equal_event_mean"],
                metrics[candidate.ARM_CANDIDATE][metric] - metrics[candidate.ARM_RESEARCH_PARENT][metric], places=15)

    def test_contract_source_drift_failure_preservation_no_output_overwrite(self):
        with mock.patch.object(candidate.shared, "require_dependencies"), \
                mock.patch.object(candidate.shared.common, "_sha256", return_value="0" * 64):
            with self.assertRaisesRegex(ValueError, "source/contract changed"):
                candidate.require_dependencies()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "failure"
            with mock.patch.object(candidate.shared.common.base, "_validate_roots"), \
                    mock.patch.object(candidate, "require_dependencies", side_effect=ValueError("source drift")):
                with self.assertRaises(ValueError):
                    candidate.run(Path(directory) / "source", output, allow_test_paths=True)
            self.assertTrue((output / "failure.json").is_file())
            with mock.patch.object(candidate.shared.common.base, "_validate_roots"), self.assertRaises(FileExistsError):
                candidate.run(Path(directory) / "source", output, allow_test_paths=True)

    def test_complete_synthetic195_run87_predictions_four_state_and_residual_artifacts(self):
        rows, folds, controls = synthetic_problem()
        states = {row.game_id: {"game_id": row.game_id} for row in rows}
        contract = candidate.shared.common.settlement._strict_json(candidate.CONTRACT)
        def parent_loader(contract, controls, frozen):
            anchors = {state["game_id"]: state for state in frozen["anchors"]}
            cohort = candidate.shared.common.base._validate_source(None)
            full_rows = [candidate.shared.common.base._load_dynamic_market(None, item, anchors[item["game_id"]])
                for item in cohort if "exclusion" not in item]
            parent, states, _ = synthetic_frozen_parent(full_rows, frozen["folds"])
            fit.reset_mock()  # Candidate ceiling is four; synthetic frozen parent construction is separate.
            return parent, states
        with mock.patch.object(old_tests, "synthetic_problem", return_value=(rows, folds, controls, states)), \
                mock.patch.object(candidate.shared.common, "run", side_effect=candidate.run), \
                mock.patch.object(candidate, "require_dependencies", return_value=contract), \
                mock.patch.object(candidate, "load_parent", side_effect=parent_loader), \
                mock.patch.object(candidate.shared, "fit_hgb_residual", wraps=candidate.shared.fit_hgb_residual) as fit, \
                mock.patch.object(candidate.shared.common.base, "_atomic_json", wraps=candidate.shared.common.base._atomic_json) as write:
            old_tests.FreshnessInteractionOffsetTests().test_complete_synthetic_run_has_exact87_predictions_and_hash_bound_artifacts()
            self.assertEqual(fit.call_count, 4)
            artifacts = {call.args[0].name: call.args[1] for call in write.call_args_list}
            self.assertEqual(len(artifacts["predictor_states.json"]["folds"]), 4)
            self.assertEqual(len(artifacts["prelink_residuals.json"]["rows"]), 87)
            self.assertEqual(artifacts["scorecard.json"]["parent_parity"]["prelink_rows_exact"], 87)
            self.assertIn("prelink_residuals_sha256", artifacts["manifest.json"])
            self.assertIn("predictor_states_sha256", artifacts["manifest.json"])


if __name__ == "__main__":
    unittest.main()
