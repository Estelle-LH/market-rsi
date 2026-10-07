"""Portable synthetic D2 math, replay and actual CLI/request admission checks."""
from __future__ import annotations
from contextlib import ExitStack, contextmanager
import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
import numpy as np
from experiments import nfl_ingame_temperature_receipt_age_slope_offset as candidate
from experiments import test_nfl_ingame_candidate_evidence_adapter as adapter_tests
from experiments import test_nfl_ingame_temperature_possession_pressure_entry as parent_tests

common, harness = candidate.common, candidate.harness
NOW = datetime(2026, 10, 5, 17, tzinfo=timezone.utc)

@contextmanager
def entry_fixture(directory):
    root = Path(directory)
    repo, pilot = root / "repo", root / "pilot"
    repo.mkdir()
    output = pilot / "runs/synthetic-d2"
    request_path = pilot / "worker/synthetic-d2.request.json"
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
        # Only Git's synthetic checkpoint is mocked. Original worker.validate hashes every file/runtime/memory.
        stack.enter_context(mock.patch.object(candidate.worker.subprocess, "check_output", return_value="synthetic-reviewed-checkpoint\n"))
        features, _ = candidate.prepare_features(rows, frozen, states)
        yield dict(source=source, rows=rows, folds=folds, frozen=frozen, states=states, features=features,
            repo=repo, output=output, request=request, request_path=request_path)

def fold_rows(fixture, ordinal=0):
    fold = fixture["folds"][ordinal]
    fit = sorted([row for row in fixture["rows"] if row.game_date in fold["fit_dates"]], key=lambda row: row.key)
    check = sorted([row for row in fixture["rows"] if row.game_date in fold["check_dates"]], key=lambda row: row.key)
    context = {**fixture["features"], "fold_id": fold["fold"], "parent_state": fixture["states"][fold["fold"]]}
    return fit, check, context

class ReceiptAgeSlopeTests(unittest.TestCase):
    def test_generic_derivatives_z_above_one_and_nested_zero_columns(self):
        logits, z, y = np.array([-4., -1., .7, 3.]), np.array([-6., 0., 4., 12.]), np.array([0., 1., 0., 1.])
        theta = np.array([.1, -.2])
        value, gradient, hessian = candidate.objective_gradient_hessian(theta, logits, z, y)
        step = 1e-5
        fd_g, fd_h = [], []
        for index in range(2):
            delta = np.eye(2)[index] * step
            plus = candidate.objective_gradient_hessian(theta + delta, logits, z, y)
            minus = candidate.objective_gradient_hessian(theta - delta, logits, z, y)
            fd_g.append((plus[0] - minus[0]) / (2 * step))
            fd_h.append((plus[1] - minus[1]) / (2 * step))
        np.testing.assert_allclose(gradient, fd_g, atol=1e-7, rtol=0)
        np.testing.assert_allclose(hessian, np.asarray(fd_h).T, atol=1e-7, rtol=0)
        fitted, receipt = candidate.solve_joint(logits, z, y, .1)
        self.assertLessEqual(receipt["KKT"], 1e-8)
        self.assertGreaterEqual(np.linalg.eigvalsh(receipt["hessian"]).min(), 16 - 1e-10)
        self.assertLessEqual(receipt["F"], receipt["F_warmstart"] + 1e-8)
        self.assertEqual((receipt["retry_count"], receipt["fallback_count"]), (0, 0))
        beta, scalar = candidate.parent.solve_temperature(logits, y)
        nested, _ = candidate.solve_joint(logits, np.zeros(4), y, beta)
        self.assertEqual(nested[1], 0.)
        self.assertAlmostEqual(nested[0], beta, places=8)
        zero, _ = candidate.solve_joint(np.zeros(4), np.zeros(4), y, 0.)
        np.testing.assert_array_equal(zero, [0., 0.])

    def test_fractional_age_fixed_interaction_causality_and_missing_receipts(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            row = copy.deepcopy(f["rows"][0])
            latest = row.source_receipt["latest_trade_epoch_ms"]
            event = datetime.fromtimestamp(latest / 1000, timezone.utc) + timedelta(seconds=2.25)
            row.source_receipt.update(pbp_checkpoint_event_time_utc=event.isoformat(),
                market_feature_cutoff_epoch_s=int(event.timestamp()) - 1, market_staleness_seconds=2.25)
            self.assertEqual(candidate.age_basis.causal_age(row.source_receipt), 2.25)
            features = {"age_seconds": {row.game_id: 2.25}, "z_by_game_id": {row.game_id: 2.25 / 300 * row.market_features[0]}}
            self.assertEqual(candidate.interaction([row], features)[0], features["z_by_game_id"][row.game_id])
            for field, value in (("market_staleness_seconds", 301.), ("latest_trade_epoch_ms", latest + 4000),
                    ("market_feature_cutoff_epoch_s", int(event.timestamp())), ("latest_trade_epoch_ms", latest + 1)):
                bad = copy.deepcopy(row)
                bad.source_receipt[field] = value
                with self.subTest(field=field), self.assertRaises(ValueError):
                    candidate.interaction([bad], features)
            del row.source_receipt["market_staleness_seconds"]
            with self.assertRaises(ValueError):
                candidate.interaction([row], features)

    def test_gamma_zero_exact_C7_zero_identity_bounds_and_unrestricted_gamma(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            rows, features = f["rows"], f["features"]
            for beta in (-1., -.7, 0., .1, 5.):
                self.assertEqual(candidate.probabilities(beta, 0., rows, features), candidate.parent.probabilities(beta, rows))
            values, bounds = candidate.probabilities(.1, -50., rows, features)
            self.assertEqual(len(values), 193)
            self.assertEqual(bounds["rows_removed"], 0)
            self.assertTrue(all(candidate.parent.EPSILON <= p <= 1 - candidate.parent.EPSILON for p in values))
            self.assertEqual(candidate.probabilities(0., 0., rows, features)[0], [row.trusted["market_probability"] for row in rows])
            for beta, gamma in ((-1.01, 0.), (float("nan"), 0.), (0., float("inf"))):
                with self.assertRaises(ValueError):
                    candidate.probabilities(beta, gamma, rows, features)
            high = copy.deepcopy(rows[0])
            high.trusted["market_probability"] = .99
            latest = high.source_receipt["latest_trade_epoch_ms"]
            event = datetime.fromtimestamp(latest / 1000, timezone.utc) + timedelta(seconds=300)
            high.source_receipt.update(pbp_checkpoint_event_time_utc=event.isoformat(),
                market_feature_cutoff_epoch_s=int(event.timestamp()) - 1, market_staleness_seconds=300.)
            high = replace(high, market_features=(math.log(.99 / (1 - .99)), *high.market_features[1:]))
            high_features = {"age_seconds": {high.game_id: 300.}, "z_by_game_id": {high.game_id: high.market_features[0]}}
            self.assertGreater(candidate.interaction([high], high_features)[0], 1.)
            self.assertEqual(candidate.probabilities(.1, 0., [high], high_features), candidate.parent.probabilities(.1, [high]))
            self.assertEqual(len(candidate.probabilities(.1, -.2, [high], high_features)[0]), 1)

    def test_checklabel_futurefield_isolation_and_state_replay_without_fit(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            fit, check, context = fold_rows(f)
            values, report = candidate.fit_predict(fit, check, context)
            changed = copy.deepcopy(check)
            for row in changed:
                row.trusted["outcome"] = 1 - row.trusted["outcome"]
                row.source_receipt.update(final_score=999, future_play="ignored")
            other_values, other = candidate.fit_predict(fit, changed, context)
            self.assertEqual(values, other_values)
            self.assertEqual(report["primitive_prediction_state"], other["primitive_prediction_state"])
            with mock.patch.object(candidate, "solve_joint", side_effect=AssertionError("no refit")):
                self.assertEqual(candidate.replay_predictor(report["primitive_prediction_state"], check, context), (values, report["bounding"]))

    def test_state_recipe_source_parent_primitive_nonfinite_and_input_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            fit, check, context = fold_rows(f)
            _, report = candidate.fit_predict(fit, check, context)
            original = report["primitive_prediction_state"]
            for key, value in (("source_sha256", "0" * 64), ("contract_sha256", "0" * 64), ("fixed_divisor_seconds", 299.),
                    ("normalization", "fitstd"), ("parent_state_sha256", "0" * 64), ("gamma", float("nan")),
                    ("fit_events", 105), ("z_check_sha256", "0" * 64)):
                state = copy.deepcopy(original)
                state[key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    candidate.replay_predictor(state, check, context)
            for key in ("F", "F_warmstart", "KKT", "gradient", "hessian"):
                state = copy.deepcopy(original)
                state["optimizer"][key] = [[float("nan"), 0.], [0., 16.]] if key == "hessian" else ([float("nan"), 0.] if key == "gradient" else float("nan"))
                with self.subTest(optimizer=key), self.assertRaises(ValueError):
                    candidate.replay_predictor(state, check, context)
            bad = copy.deepcopy(context)
            bad["z_by_game_id"][check[0].game_id] += .01
            with self.assertRaises(ValueError):
                candidate.replay_predictor(original, check, bad)

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
                    _, check, context = fold_rows(f, saved["fold"] - 1)
                    self.assertEqual(candidate.replay_predictor(saved["state"], check, context)[0], [float(row["candidate_probability"]) for row in csv if int(row["fold"]) == saved["fold"]])
            before = (f["output"] / "manifest.json").read_bytes()
            with self.assertRaises(FileExistsError):
                candidate.run(f["source"], f["output"])
            self.assertEqual(before, (f["output"] / "manifest.json").read_bytes())

    def test_request_identity_runtime_spec_clock_and_source_coverage_fail_prefit(self):
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

    def test_compiled_contract_callback_binding_and_exact_core_dependencies(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            binding = candidate.require_admission(f["source"], f["output"])
            self.assertEqual(binding["candidate_contract_sha256"], candidate.CONTRACT_SHA256)
            self.assertEqual(binding["feature_names"], candidate.FEATURE_NAMES)
            self.assertTrue(all(path == str(Path(candidate.__file__).resolve()) for path in binding["callback_source_bindings"].values()))
            self.assertEqual(binding["dependency_source_hashes"][str(Path(candidate.math_recipe.__file__).resolve())], "c57ed002b507e219c788c256b33e0f853fc418ea41713fbfbc845bcb7782d838")
            (f["repo"] / candidate.CONTRACT_RELATIVE).write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "compiled"):
                candidate.run(f["source"], f["output"])

if __name__ == "__main__":
    unittest.main()
