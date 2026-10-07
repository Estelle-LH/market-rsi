"""Portable synthetic constant-intercept math, states and complete CLI admission."""
from __future__ import annotations
from contextlib import ExitStack, contextmanager
import copy
from datetime import datetime, timezone
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
import numpy as np
from scipy.special import expit
from experiments import nfl_ingame_temperature_intercept_joint_offset as candidate
from experiments import test_nfl_ingame_candidate_evidence_adapter as adapter_tests
from experiments import test_nfl_ingame_temperature_possession_pressure_entry as parent_tests

common, harness = candidate.common, candidate.harness
NOW = datetime(2026, 10, 5, 18, tzinfo=timezone.utc)

@contextmanager
def entry_fixture(directory):
    root = Path(directory)
    repo, pilot = root / "repo", root / "pilot"
    repo.mkdir()
    output = pilot / "runs/synthetic-d3"
    request_path = pilot / "worker/synthetic-d3.request.json"
    request_path.parent.mkdir(parents=True)
    real_repo = Path(candidate.__file__).parents[3]
    contract = common.settlement._strict_json(candidate.CONTRACT)
    paths = {str(Path(path).relative_to(real_repo)): digest for path, digest in harness.held_c7_binding()["dependency_source_hashes"].items()}
    paths.update(contract["reuse_helpers"])
    paths.update(candidate.IMPORT_ONLY_SOURCE)
    paths.update({candidate.CONTRACT_RELATIVE: candidate.CONTRACT_SHA256,
        candidate.SOURCE_REVIEW: candidate.SOURCE_REVIEW_SHA256, candidate.PARITY_REVIEW: candidate.PARITY_REVIEW_SHA256,
        str(harness.CONTRACT.relative_to(real_repo)): harness.CONTRACT_SHA256,
        str(Path(candidate.__file__).relative_to(real_repo)): common._sha256(Path(candidate.__file__))})
    for relative in paths:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(real_repo / relative, target)
    memory = root / "memory.json"
    common.base._atomic_json(memory, {"synthetic": True})
    request = {"attempt_id": output.name, "candidate_id": candidate.TASK_ID, "module": candidate.MODULE,
        "source_commit": "synthetic-reviewed-checkpoint", "files": paths,
        "python": contract["resources"]["python"], "python_sha256": contract["resources"]["python_sha256"],
        "memory": str(memory), "memory_sha256": common._sha256(memory), "runtime_pair_sha256": "a" * 64,
        "spec_sha256": candidate.CONTRACT_SHA256, "max_fits": 4, "max_wall_seconds": 900}
    common.base._atomic_json(request_path, request)
    with adapter_tests.synthetic_environment(root) as environment, ExitStack() as stack:
        source, rows, folds, frozen, controls = environment
        parents, states = parent_tests.numeric_parent(rows, folds)
        stack.enter_context(mock.patch.object(harness, "load_parent", return_value=(parents, states)))
        stack.enter_context(mock.patch.object(candidate, "REPO", repo))
        stack.enter_context(mock.patch.object(candidate, "utc_now", return_value=NOW))
        stack.enter_context(mock.patch.object(candidate.worker, "TRAIN", source))
        # Only the Git checkpoint is synthetic; original worker hashes all source/runtime/memory bytes.
        stack.enter_context(mock.patch.object(candidate.worker.subprocess, "check_output", return_value="synthetic-reviewed-checkpoint\n"))
        features, _ = candidate.prepare_features(rows, frozen, states)
        yield dict(source=source, rows=rows, folds=folds, frozen=frozen, states=states, features=features,
            repo=repo, output=output, request=request, request_path=request_path)

def fold_rows(fixture, ordinal=0):
    fold = fixture["folds"][ordinal]
    fit = sorted([row for row in fixture["rows"] if row.game_date in fold["fit_dates"]], key=lambda row: row.key)
    check = sorted([row for row in fixture["rows"] if row.game_date in fold["check_dates"]], key=lambda row: row.key)
    return fit, check, {**fixture["features"], "fold_id": fold["fold"], "parent_state": fixture["states"][fold["fold"]]}

class TemperatureInterceptTests(unittest.TestCase):
    def test_exact_generic_objective_penalized_intercept_derivatives_and_fit_only_brackets(self):
        logits, ones, y = np.array([-4., -1., .7, 3.]), np.ones(4), np.array([0., 1., 0., 1.])
        theta = np.array([.1, -.2])
        value, gradient, hessian = candidate.objective_gradient_hessian(theta, logits, ones, y)
        eta = (1 + theta[0]) * logits + theta[1]
        self.assertAlmostEqual(value, np.sum(np.logaddexp(0., eta) - y * eta) + 8 * (theta @ theta), places=13)
        self.assertAlmostEqual(gradient[1], np.sum(expit(eta) - y) + 16 * theta[1], places=13)
        step = 1e-5
        fd_g, fd_h = [], []
        for index in range(2):
            delta = np.eye(2)[index] * step
            plus = candidate.objective_gradient_hessian(theta + delta, logits, ones, y)
            minus = candidate.objective_gradient_hessian(theta - delta, logits, ones, y)
            fd_g.append((plus[0] - minus[0]) / (2 * step))
            fd_h.append((plus[1] - minus[1]) / (2 * step))
        np.testing.assert_allclose(gradient, fd_g, atol=1e-7, rtol=0)
        np.testing.assert_allclose(hessian, np.asarray(fd_h).T, atol=1e-7, rtol=0)
        fitted, receipt = candidate.solve_joint(logits, ones, y, .1)
        self.assertEqual(receipt["fit_only_brackets"], [[-1., 1 + sum(abs(logits)) / 16], [-1.25, 1.25]])
        self.assertLessEqual(receipt["KKT"], 1e-8)
        self.assertGreaterEqual(np.linalg.eigvalsh(receipt["hessian"]).min(), 16 - 1e-10)
        self.assertLessEqual(receipt["F"], receipt["F_warmstart"] + 1e-8)
        self.assertEqual((receipt["retry_count"], receipt["fallback_count"]), (0, 0))
        self.assertIs(candidate.solve_joint, candidate.math_recipe.solve_joint)
        zero, _ = candidate.solve_joint(np.zeros(4), np.zeros(4), y, 0.)
        np.testing.assert_array_equal(zero, [0., 0.])

    def test_exact_ones_preparation_no_age_PBP_or_labels_and_no_fitted_scaling(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            changed = copy.deepcopy(f["rows"])
            for row in changed:
                row.source_receipt.clear()
                row.trusted["outcome"] = 1 - row.trusted["outcome"]
                row.trusted.update(final_score=999, future_play="ignored")
            features, receipt = candidate.prepare_features(changed, {}, f["states"])
            self.assertEqual(features, f["features"])
            self.assertEqual(receipt["normalization"], "none")
            self.assertFalse(receipt["new_data_fields_used"])
            np.testing.assert_array_equal(candidate.constant_column(changed, features), np.ones(193))
            bad = copy.deepcopy(features)
            bad["constant_one"][changed[0].game_id] = .999
            with self.assertRaises(ValueError):
                candidate.constant_column(changed, bad)
            for rows, states in ((changed[:-1], f["states"]), (changed, {1: f["states"][1]})):
                with self.assertRaises(ValueError):
                    candidate.prepare_features(rows, {}, states)

    def test_gamma_zero_exact_C7_boundary_constant_not_half_and_bounding(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            rows, features = f["rows"], f["features"]
            for beta in (-1., -.7, 0., .1, 5.):
                self.assertEqual(candidate.probabilities(beta, 0., rows, features), candidate.parent.probabilities(beta, rows))
            self.assertEqual(candidate.probabilities(0., 0., rows, features)[0], [row.trusted["market_probability"] for row in rows])
            values, bounds = candidate.probabilities(-1., -1., rows, features)
            np.testing.assert_array_equal(values, [float(expit(-1.))] * 193)
            self.assertNotEqual(values[0], .5)
            self.assertEqual(bounds["rows_removed"], 0)
            for gamma in (-1e6, 1e6):
                values, bounds = candidate.probabilities(-1., gamma, rows, features)
                self.assertEqual(bounds["clipped_rows"], 193)
                self.assertTrue(all(candidate.parent.EPSILON <= value <= 1 - candidate.parent.EPSILON for value in values))
            for beta, gamma in ((-1.01, 0.), (float("nan"), 0.), (0., float("inf"))):
                with self.assertRaises(ValueError):
                    candidate.probabilities(beta, gamma, rows, features)
            boundary, receipt = candidate.solve_joint(np.ones(80) * 3, np.ones(80), np.zeros(80), 0.)
            self.assertEqual(boundary[0], -1.)
            self.assertNotEqual(boundary[1], 0.)
            self.assertLessEqual(receipt["KKT"], 1e-8)

    def test_check_labels_and_future_fields_do_not_change_fit(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            fit, check, context = fold_rows(f)
            values, report = candidate.fit_predict(fit, check, context)
            changed = copy.deepcopy(check)
            for row in changed:
                row.trusted["outcome"] = 1 - row.trusted["outcome"]
                row.source_receipt.clear()
            other_values, other = candidate.fit_predict(fit, changed, context)
            self.assertEqual(values, other_values)
            self.assertEqual(report["primitive_prediction_state"], other["primitive_prediction_state"])
            with mock.patch.object(candidate, "solve_joint", side_effect=AssertionError("no refit")):
                self.assertEqual(candidate.replay_predictor(report["primitive_prediction_state"], check, context), (values, report["bounding"]))

    def test_state_source_intercept_penalty_brackets_nonfinite_and_input_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            fit, check, context = fold_rows(f)
            _, report = candidate.fit_predict(fit, check, context)
            original = report["primitive_prediction_state"]
            for key, value in (("source_sha256", "0" * 64), ("contract_sha256", "0" * 64), ("intercept", 99.),
                    ("intercept_penalized", False), ("normalization", "fitstd"), ("parent_state_sha256", "0" * 64),
                    ("gamma", float("nan")), ("fit_events", 105), ("constant_check_sha256", "0" * 64)):
                state = copy.deepcopy(original)
                state[key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    candidate.replay_predictor(state, check, context)
            for key in ("F", "F_warmstart", "KKT", "gradient", "hessian"):
                state = copy.deepcopy(original)
                state["optimizer"][key] = [[float("nan"), 0.], [0., 16.]] if key == "hessian" else ([float("nan"), 0.] if key == "gradient" else float("nan"))
                with self.subTest(optimizer=key), self.assertRaises(ValueError):
                    candidate.replay_predictor(state, check, context)
            state = copy.deepcopy(original)
            state["optimizer"]["fit_only_brackets"][1] = [-99., 99.]
            state["optimizer_sha256"] = common._digest(state["optimizer"])
            with self.assertRaises(ValueError):
                candidate.replay_predictor(state, check, context)

    def test_exact_CLI_full195_four_synthetic_fits87_replay_and_unchanged_judge(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f, \
                mock.patch.object(candidate, "solve_joint", wraps=candidate.solve_joint) as solve, \
                mock.patch.object(candidate.worker, "validate", wraps=candidate.worker.validate) as validate, \
                mock.patch("sys.argv", [candidate.MODULE, "--source-root", str(f["source"]), "--output", str(f["output"])]), mock.patch("builtins.print"):
            candidate.main()
            self.assertEqual((solve.call_count, validate.call_count), (4, 1))
            manifest = common.settlement._strict_json(f["output"] / "manifest.json")
            card = common.settlement._strict_json(f["output"] / "scorecard.json")
            states = common.settlement._strict_json(f["output"] / "predictor_states.json")
            csv = common.frozen_v0._read_csv(f["output"] / "predictions.csv")
            self.assertEqual((manifest["source_events"], manifest["materialized_events"], manifest["excluded_events"], manifest["check_events"], manifest["model_fits"]), (195, 193, 2, 87, 4))
            self.assertEqual(card["actual_research_parent_id"], candidate.parent.TASK_ID)
            self.assertEqual((len(card["aggregate"]), len(card["per_schedule_date_correction_diagnostics"])), (5, 20))
            self.assertEqual([r["fit_events"] for r in card["folds"]], [106, 132, 148, 176])
            self.assertEqual([r["check_events"] for r in card["folds"]], [26, 16, 28, 17])
            self.assertEqual(card["parent_replay"]["parent_refits"], 0)
            self.assertEqual((card["scientific_decision"], card["operational_decision"], card["decision_conditions"]), common.decision(card["aggregate"], card["folds"], card["paired_grouped_evidence"], candidate.ARM_CANDIDATE))
            self.assertEqual([item["state"]["optimizer"]["fit_only_brackets"][1][1] for item in states["folds"]], [7.625, 9.25, 10.25, 12.])
            with mock.patch.object(candidate, "solve_joint", side_effect=AssertionError("no refits")):
                for saved in states["folds"]:
                    _, check, context = fold_rows(f, saved["fold"] - 1)
                    self.assertEqual(candidate.replay_predictor(saved["state"], check, context)[0], [float(row["candidate_probability"]) for row in csv if int(row["fold"]) == saved["fold"]])
            before = (f["output"] / "manifest.json").read_bytes()
            with self.assertRaises(FileExistsError):
                candidate.run(f["source"], f["output"])
            self.assertEqual(before, (f["output"] / "manifest.json").read_bytes())

    def test_request_runtime_spec_clock_core_and_source_review_coverage_fail_prefit(self):
        mutations = {"attempt_id": "other", "candidate_id": "other", "module": "experiments.nfl_ingame_other", "spec_sha256": "0" * 64,
            "source_commit": "changed", "max_fits": 3, "max_wall_seconds": 901, "python_sha256": "0" * 64, "python": "/not-approved"}
        for key, value in mutations.items():
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f, mock.patch.object(candidate, "solve_joint") as solve:
                f["request"][key] = value
                common.base._atomic_json(f["request_path"], f["request"])
                with self.assertRaises(ValueError):
                    candidate.run(f["source"], f["output"])
                self.assertEqual(solve.call_count, 0)
                self.assertEqual(common.settlement._strict_json(f["output"] / "failure.json")["model_fits"], 0)
        for now in (datetime(2026, 10, 5, 15, tzinfo=timezone.utc), datetime(2026, 10, 5, 19, 27, 11, tzinfo=timezone.utc)):
            with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f, mock.patch.object(candidate, "utc_now", return_value=now), self.assertRaisesRegex(ValueError, "authority"):
                candidate.run(f["source"], f["output"])
        paths = list(common.settlement._strict_json(candidate.CONTRACT)["reuse_helpers"]) + [candidate.SOURCE_REVIEW, candidate.PARITY_REVIEW,
            candidate.CONTRACT_RELATIVE, str(Path(candidate.__file__).relative_to(Path(candidate.__file__).parents[3]))]
        for relative in paths:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f, mock.patch.object(candidate, "solve_joint") as solve:
                f["request"]["files"][relative] = "0" * 64
                common.base._atomic_json(f["request_path"], f["request"])
                with self.assertRaises(ValueError):
                    candidate.run(f["source"], f["output"])
                self.assertEqual(solve.call_count, 0)

    def test_review_payload_false_or_boolean_count_cannot_override_hash_checks(self):
        for relative, key, value in ((candidate.SOURCE_REVIEW, "passed", False), (candidate.PARITY_REVIEW, "predictions_exact", False),
                (candidate.PARITY_REVIEW, "fit_calls_completed", True), (candidate.PARITY_REVIEW, "control_refits", 1)):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
                path = f["repo"] / relative
                payload = common.settlement._strict_json(path)
                payload[key] = value
                common.base._atomic_json(path, payload)
                digest = common._sha256(path)
                f["request"]["files"][relative] = digest
                common.base._atomic_json(f["request_path"], f["request"])
                patched = "SOURCE_REVIEW_SHA256" if relative == candidate.SOURCE_REVIEW else "PARITY_REVIEW_SHA256"
                with mock.patch.object(candidate, patched, digest), self.assertRaises(ValueError):
                    candidate.run(f["source"], f["output"])

    def test_partial_solver_and_post_prediction_failure_truth_no_retry(self):
        for mode in ("fit", "output"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
                partial = {"converged": False, "optimization_calls_started": 1, "optimization_calls_completed": 0}
                patch = mock.patch.object(candidate, "solve_joint", side_effect=candidate.FitFailure("synthetic fit failure", partial)) if mode == "fit" else mock.patch.object(candidate, "probabilities", side_effect=ValueError("synthetic output failure"))
                with patch, self.assertRaises(candidate.FitFailure):
                    candidate.run(f["source"], f["output"])
                failure = common.settlement._strict_json(f["output"] / "failure.json")
                self.assertEqual((failure["fit_progress"]["fit_calls_entered"], failure["fit_progress"]["fit_calls_completed"]), (1, 0))
                self.assertEqual(failure["optimizer_partial_receipt"]["optimization_calls_completed"], int(mode == "output"))
                self.assertFalse((f["output"] / "scorecard.json").exists())

    def test_compiled_contract_direct_callback_bindings_and_exact_import_provenance(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            binding = candidate.require_admission(f["source"], f["output"])
            self.assertEqual(binding["candidate_contract_sha256"], candidate.CONTRACT_SHA256)
            self.assertEqual(binding["feature_names"], ["market_logit", "constant_one"])
            self.assertTrue(all(path == str(Path(candidate.__file__).resolve()) for path in binding["callback_source_bindings"].values()))
            self.assertEqual(binding["dependency_source_hashes"][str(Path(candidate.math_recipe.__file__).resolve())], "c57ed002b507e219c788c256b33e0f853fc418ea41713fbfbc845bcb7782d838")
            (f["repo"] / candidate.CONTRACT_RELATIVE).write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "compiled"):
                candidate.run(f["source"], f["output"])

if __name__ == "__main__":
    unittest.main()
