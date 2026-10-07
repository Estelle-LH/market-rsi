"""Portable synthetic anchor-down interaction, isolation, replay and CLI checks."""
from __future__ import annotations
from contextlib import ExitStack, contextmanager
import copy
from dataclasses import replace
from datetime import datetime, timezone
import math
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
import numpy as np
from experiments import nfl_ingame_temperature_down_slope_joint_offset as candidate
from experiments import test_nfl_ingame_candidate_evidence_adapter as adapter_tests
from experiments import test_nfl_ingame_temperature_possession_pressure_entry as parent_tests

common, harness = candidate.common, candidate.harness
NOW = datetime(2026, 10, 5, 21, 50, tzinfo=timezone.utc)

def with_down(row, value, *, poison_other_fields=False):
    values = [float("nan") if poison_other_fields and index not in (3, 4, 5, 6) else field
        for index, field in enumerate(row.state_features)]
    values[3:7] = [float(value == ordinal) for ordinal in (1, 2, 3, 4)]
    return replace(row, state_features=tuple(values))

@contextmanager
def entry_fixture(directory):
    root = Path(directory)
    repo, pilot = root / "repo", root / "pilot"
    repo.mkdir()
    output = pilot / "runs/synthetic-c1"
    request_path = pilot / "worker/synthetic-c1.request.json"
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
        source, originals, folds, frozen, controls = environment
        rows = [with_down(row, index % 4 + 1) for index, row in enumerate(originals)]
        down_map = {row.game_id: index % 4 + 1 for index, row in enumerate(rows)}
        for anchor in frozen["anchors"]:
            if anchor["game_id"] in down_map:
                anchor["down"] = str(down_map[anchor["game_id"]])
        by_game = {row.game_id: row for row in rows}
        def materialize(root, item, anchor):
            if "exclusion" in item:
                raise common.settlement.EventExclusion(item["exclusion"], "frozen synthetic exclusion")
            return by_game[item["game_id"]]
        parents, states = parent_tests.numeric_parent(rows, folds)
        stack.enter_context(mock.patch.object(common.base, "_load_dynamic_market", side_effect=materialize))
        stack.enter_context(mock.patch.object(harness, "load_parent", return_value=(parents, states)))
        stack.enter_context(mock.patch.object(candidate, "REPO", repo))
        stack.enter_context(mock.patch.object(candidate, "utc_now", return_value=NOW))
        stack.enter_context(mock.patch.object(candidate.worker, "TRAIN", source))
        # Original worker validates all source/runtime/memory bytes; only Git checkpoint is synthetic.
        stack.enter_context(mock.patch.object(candidate.worker.subprocess, "check_output", return_value="synthetic-reviewed-checkpoint\n"))
        features, _ = candidate.prepare_features(rows, frozen, states)
        yield dict(source=source, rows=rows, folds=folds, frozen=frozen, states=states, features=features,
            materialized=by_game, repo=repo, output=output, request=request, request_path=request_path)

def fold_rows(fixture, ordinal=0):
    fold = fixture["folds"][ordinal]
    fit = sorted([row for row in fixture["rows"] if row.game_date in fold["fit_dates"]], key=lambda row: row.key)
    check = sorted([row for row in fixture["rows"] if row.game_date in fold["check_dates"]], key=lambda row: row.key)
    return fit, check, {**fixture["features"], "fold_id": fold["fold"], "parent_state": fixture["states"][fold["fold"]]}

def probability_rows(template, probabilities, downs):
    rows = []
    for index, (probability, down) in enumerate(zip(probabilities, downs, strict=True)):
        row = copy.deepcopy(template)
        row.trusted["market_probability"] = probability
        row = with_down(row, down)
        rows.append(replace(row, game_id=f"probe-{index}", market_features=(math.log(probability / (1 - probability)), *row.market_features[1:])))
    return rows, {"down_by_game_id": {row.game_id: down for row, down in zip(rows, downs, strict=True)}}

class DownSlopeTests(unittest.TestCase):
    def test_generic_derivatives_binary_sign_brackets_boundary_and_zero_helper_identity(self):
        logits, z, y = np.array([-4., -1., .7, 3.]), np.array([-4., -1., .7, 3.]) * np.arange(4) / 3, np.array([0., 1., 0., 1.])
        theta = np.array([.1, -.2])
        value, gradient, hessian = candidate.objective_gradient_hessian(theta, logits, z, y)
        eta = (1 + theta[0]) * logits + theta[1] * z
        self.assertAlmostEqual(value, np.sum(np.logaddexp(0., eta) - y * eta) + 8 * (theta @ theta), places=13)
        step, fd_g, fd_h = 1e-5, [], []
        for index in range(2):
            delta = np.eye(2)[index] * step
            plus = candidate.objective_gradient_hessian(theta + delta, logits, z, y)
            minus = candidate.objective_gradient_hessian(theta - delta, logits, z, y)
            fd_g.append((plus[0] - minus[0]) / (2 * step))
            fd_h.append((plus[1] - minus[1]) / (2 * step))
        np.testing.assert_allclose(gradient, fd_g, atol=1e-7, rtol=0)
        np.testing.assert_allclose(hessian, np.asarray(fd_h).T, atol=1e-7, rtol=0)
        fitted, receipt = candidate.solve_joint(logits, z, y, .1)
        self.assertEqual(receipt["fit_only_brackets"], [[-1., 1 + sum(abs(logits)) / 16], [-1 - sum(abs(z)) / 16, 1 + sum(abs(z)) / 16]])
        self.assertLessEqual(receipt["KKT"], 1e-8)
        self.assertGreaterEqual(np.linalg.eigvalsh(receipt["hessian"]).min(), 16 - 1e-10)
        self.assertLessEqual(receipt["F"], receipt["F_warmstart"] + 1e-8)
        self.assertEqual((receipt["retry_count"], receipt["fallback_count"]), (0, 0))
        self.assertIs(candidate.solve_joint, candidate.math_recipe.solve_joint)
        beta, _ = candidate.parent.solve_temperature(logits, y)
        nested, _ = candidate.solve_joint(logits, np.zeros(4), y, beta)
        self.assertEqual(nested[1], 0.)  # Actual down1 representation is exactly the nested zero column.
        self.assertAlmostEqual(nested[0], beta, places=8)
        boundary, boundary_receipt = candidate.solve_joint(np.ones(240) * 7, np.ones(240), np.zeros(240), 0.)
        self.assertEqual(boundary[0], -1.)
        self.assertNotEqual(boundary[1], 0.)
        self.assertLessEqual(boundary_receipt["KKT"], 1e-8)

    def test_exact_anchor_integer_and_matching_frozen_onehot_validation(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            row = f["rows"][0]
            for value in (1, 2, 3, 4, 1., "2", "3.0", np.float64(4)):
                encoded = with_down(row, float(value))
                self.assertEqual(candidate.down_value(encoded, {"down": value}), int(float(value)))
            for value in (None, True, float("nan"), float("inf"), .5, 0, 5, "x", 1j):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    candidate.down_value(row, {"down": value})
            for state in ((), None, (*row.state_features[:3], 1., 1., 0., 0.)):
                with self.assertRaises(ValueError):
                    candidate.down_value(replace(row, state_features=state), {"down": 1})
            with self.assertRaises(ValueError):
                candidate.down_value(with_down(row, 2), {"down": 1})
            names = list(common.base.STATE_FEATURE_NAMES)
            names[3] = "future_down"
            with mock.patch.object(common.base, "STATE_FEATURE_NAMES", tuple(names)), self.assertRaises(ValueError):
                candidate.down_value(row, {"down": 1})
            expected = [((f["features"]["down_by_game_id"][r.game_id] - 1) / 3) * r.market_features[0] for r in f["rows"]]
            self.assertEqual(candidate.down_column(f["rows"], f["features"]).tolist(), expected)

    def test_invalid_anchor_fails_whole_run_prefit_no_drop_imputation_or_retry(self):
        for value in (None, float("nan"), .5, 5, True):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f, mock.patch.object(candidate, "solve_joint") as solve:
                f["frozen"]["anchors"][0]["down"] = value
                with self.assertRaisesRegex(ValueError, "down"):
                    candidate.run(f["source"], f["output"])
                self.assertEqual(solve.call_count, 0)
                failure = common.settlement._strict_json(f["output"] / "failure.json")
                self.assertEqual(failure["fit_progress"]["fit_calls_entered"], 0)
                self.assertFalse((f["output"] / "predictions.csv").exists())
                self.assertFalse((f["output"] / "manifest.json").exists())

    def test_no_other_state_age_pressure_tanh_labels_or_estimated_scaling(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            changed = copy.deepcopy(f["rows"])
            for row in changed:
                row.source_receipt.clear()
                row.trusted["outcome"] = 1 - row.trusted["outcome"]
                row.trusted.update(final_score=999, future_play="ignored")
            changed = [with_down(row, f["features"]["down_by_game_id"][row.game_id], poison_other_fields=True) for row in changed]
            features, receipt = candidate.prepare_features(changed, f["frozen"], f["states"])
            self.assertEqual(features, f["features"])
            self.assertEqual(receipt["normalization"], "none")
            self.assertFalse(receipt["other_state_fields_used"])
            for rows, states in ((changed[:-1], f["states"]), (changed, {1: f["states"][1]})):
                with self.assertRaises(ValueError):
                    candidate.prepare_features(rows, f["frozen"], states)

    def test_gamma_zero_exact_C7_joint_orientation_complement_and_finite_bounds(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            rows, features = f["rows"], f["features"]
            for beta in (-1., -.7, 0., .1, 5.):
                self.assertEqual(candidate.probabilities(beta, 0., rows, features), candidate.parent.probabilities(beta, rows))
            self.assertEqual(candidate.probabilities(0., 0., rows, features)[0], [row.trusted["market_probability"] for row in rows])
            p = [candidate.parent.EPSILON, .1, .49, .5, .51, .9, 1 - candidate.parent.EPSILON]
            s = [1, 2, 3, 4, 1, 2, 3]
            forward, ff = probability_rows(rows[0], p, s)
            reverse, rf = probability_rows(rows[0], [1 - value for value in p], s)
            for beta, gamma in ((0., 0.), (.04, .3), (-1., -.5), (.05, -2.), (0., 100.)):
                q = candidate.probabilities(beta, gamma, forward, ff)[0]
                complemented = candidate.probabilities(beta, gamma, reverse, rf)[0]
                np.testing.assert_allclose(q, 1 - np.asarray(complemented), atol=1e-15, rtol=0)
                self.assertTrue(all(candidate.parent.EPSILON <= value <= 1 - candidate.parent.EPSILON for value in q))
            for gamma in (-1e6, 1e6):
                values, bounds = candidate.probabilities(-1., gamma, forward, ff)
                self.assertGreater(bounds["clipped_rows"], 0)
                self.assertEqual(bounds["rows_removed"], 0)
            for beta, gamma in ((-1.01, 0.), (float("nan"), 0.), (0., float("inf"))):
                with self.assertRaises(ValueError):
                    candidate.probabilities(beta, gamma, rows, features)

    def test_check_labels_future_fields_and_other_state_do_not_change_fit_or_replay(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            fit, check, context = fold_rows(f)
            values, report = candidate.fit_predict(fit, check, context)
            changed = copy.deepcopy(check)
            for row in changed:
                row.trusted["outcome"] = 1 - row.trusted["outcome"]
                row.source_receipt.clear()
            changed = [with_down(row, f["features"]["down_by_game_id"][row.game_id], poison_other_fields=True) for row in changed]
            other_values, other = candidate.fit_predict(fit, changed, context)
            self.assertEqual(values, other_values)
            self.assertEqual(report["primitive_prediction_state"], other["primitive_prediction_state"])
            with mock.patch.object(candidate, "solve_joint", side_effect=AssertionError("no refit")):
                self.assertEqual(candidate.replay_predictor(report["primitive_prediction_state"], check, context), (values, report["bounding"]))

    def test_state_source_column_transform_bracket_nonfinite_and_input_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            fit, check, context = fold_rows(f)
            _, report = candidate.fit_predict(fit, check, context)
            original = report["primitive_prediction_state"]
            for key, value in (("source_sha256", "0" * 64), ("contract_sha256", "0" * 64), ("intercept", 99.),
                    ("transform", "weighted_pressure"), ("column_indices", [2]), ("normalization", "fitstd"),
                    ("parent_state_sha256", "0" * 64), ("gamma", float("nan")), ("fit_events", 105),
                    ("slope_check_sha256", "0" * 64), ("fit_z_absolute_sum", float("inf"))):
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
            with mock.patch.object(candidate, "solve_joint", side_effect=AssertionError("no refits")):
                for saved in states["folds"]:
                    fit, check, context = fold_rows(f, saved["fold"] - 1)
                    self.assertEqual(saved["state"]["fit_z_absolute_sum"], math.fsum(abs(value) for value in candidate.down_column(fit, context)))
                    self.assertEqual(saved["state"]["optimizer"]["fit_only_brackets"][1], [-1 - saved["state"]["fit_z_absolute_sum"] / 16, 1 + saved["state"]["fit_z_absolute_sum"] / 16])
                    self.assertEqual(candidate.replay_predictor(saved["state"], check, context)[0], [float(row["candidate_probability"]) for row in csv if int(row["fold"]) == saved["fold"]])
            before = (f["output"] / "manifest.json").read_bytes()
            with self.assertRaises(FileExistsError):
                candidate.run(f["source"], f["output"])
            self.assertEqual(before, (f["output"] / "manifest.json").read_bytes())

    def test_request_runtime_spec_clock_core_and_review_coverage_fail_prefit(self):
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
        for now in (datetime(2026, 10, 5, 15, tzinfo=timezone.utc), datetime(2026, 10, 5, 22, 39, 55, tzinfo=timezone.utc)):
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

    def test_partial_solver_post_prediction_failure_truth_no_retry_and_compiled_binding(self):
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
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            binding = candidate.require_admission(f["source"], f["output"])
            self.assertEqual(binding["candidate_contract_sha256"], candidate.CONTRACT_SHA256)
            self.assertEqual(binding["feature_names"], ["market_logit", "preplay_down_market_slope"])
            self.assertTrue(all(path == str(Path(candidate.__file__).resolve()) for path in binding["callback_source_bindings"].values()))
            self.assertEqual(binding["dependency_source_hashes"][str(Path(common.base.__file__).resolve())], "e61668c7e29cf4dda95f6cc315b248dbe6744a9dcc0ae0cd6077d880ca6265b7")
            (f["repo"] / candidate.CONTRACT_RELATIVE).write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "compiled"):
                candidate.run(f["source"], f["output"])

if __name__ == "__main__":
    unittest.main()

