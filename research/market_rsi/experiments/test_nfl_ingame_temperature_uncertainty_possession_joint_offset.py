"""Synthetic original-entry, weighted possession semantics, isolation and replay."""
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
from experiments import nfl_ingame_temperature_uncertainty_possession_joint_offset as candidate
from experiments import test_nfl_ingame_candidate_evidence_adapter as adapter_tests
from experiments import test_nfl_ingame_temperature_possession_pressure_entry as parent_tests

common, harness = candidate.common, candidate.harness
NOW = datetime(2026, 10, 6, 15, 15, tzinfo=timezone.utc)


def with_possession(row, value, poison=False):
    fields = [float("nan") if poison else item for item in row.state_features]
    fields[2] = value
    return replace(row, state_features=tuple(fields))


@contextmanager
def entry_fixture(directory):
    root, real_repo = Path(directory), Path(candidate.__file__).parents[3]
    repo, pilot = root / "repo", root / "pilot"
    repo.mkdir(); output = pilot / "runs/synthetic-a1"
    request_path = pilot / "worker/synthetic-a1.request.json"
    request_path.parent.mkdir(parents=True)
    spec = common.settlement._strict_json(real_repo / candidate.EXECUTION_SPEC_RELATIVE)
    paths = {str(Path(path).relative_to(real_repo)): digest for path, digest in harness.held_c7_binding()["dependency_source_hashes"].items()}
    paths.update(spec["reuse_helpers"]); paths.update(candidate.PROVENANCE_SOURCE)
    paths.update({candidate.CONTRACT_RELATIVE: candidate.CONTRACT_SHA256,
        candidate.EXECUTION_SPEC_RELATIVE: candidate.EXECUTION_SPEC_SHA256, candidate.RULE_RELATIVE: candidate.RULE_SHA256,
        candidate.SOURCE_REVIEW: candidate.SOURCE_REVIEW_SHA256, candidate.PARITY_REVIEW: candidate.PARITY_REVIEW_SHA256,
        str(harness.CONTRACT.relative_to(real_repo)): harness.CONTRACT_SHA256,
        str(Path(candidate.__file__).relative_to(real_repo)): common._sha256(Path(candidate.__file__))})
    for relative in paths:
        target = repo / relative; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(real_repo / relative, target)
    memory = root / "memory.json"; common.base._atomic_json(memory, {"synthetic": True})
    request = {"attempt_id": output.name, "candidate_id": candidate.TASK_ID, "module": candidate.MODULE,
        "source_commit": "synthetic-reviewed-checkpoint", "files": paths,
        "python": spec["resources"]["python"], "python_sha256": spec["resources"]["python_sha256"],
        "memory": str(memory), "memory_sha256": common._sha256(memory), "runtime_pair_sha256": "a" * 64,
        "spec_sha256": candidate.CONTRACT_SHA256, "max_fits": 4, "max_wall_seconds": 900}
    common.base._atomic_json(request_path, request)
    with adapter_tests.synthetic_environment(root) as environment, ExitStack() as stack:
        source, originals, folds, frozen, controls = environment
        rows = [with_possession(row, float(index % 2)) for index, row in enumerate(originals)]
        by_game = {row.game_id: row for row in rows}
        for anchor in frozen["anchors"]:
            if anchor["game_id"] in by_game:
                anchor["possession_is_home"] = str(int(by_game[anchor["game_id"]].state_features[2]))
        def materialize(root, item, anchor):
            if "exclusion" in item:
                raise common.settlement.EventExclusion(item["exclusion"], "frozen synthetic exclusion")
            return by_game[item["game_id"]]
        parents, states = parent_tests.numeric_parent(rows, folds)
        for owner, name, kwargs in ((common.base, "_load_dynamic_market", {"side_effect": materialize}),
                (harness, "load_parent", {"return_value": (parents, states)}),
                (candidate, "REPO", {"new": repo}), (candidate, "utc_now", {"return_value": NOW}),
                (candidate.worker, "TRAIN", {"new": source}),
                (candidate.worker.subprocess, "check_output", {"return_value": "synthetic-reviewed-checkpoint\n"})):
            stack.enter_context(mock.patch.object(owner, name, **kwargs))
        features, _ = candidate.prepare_features(rows, frozen, states)
        yield dict(source=source, rows=rows, folds=folds, frozen=frozen, states=states,
            features=features, repo=repo, output=output, request=request, request_path=request_path)


def fold_rows(fixture, ordinal=0):
    fold = fixture["folds"][ordinal]
    fit = sorted([row for row in fixture["rows"] if row.game_date in fold["fit_dates"]], key=lambda row: row.key)
    check = sorted([row for row in fixture["rows"] if row.game_date in fold["check_dates"]], key=lambda row: row.key)
    return fit, check, {**fixture["features"], "fold_id": fold["fold"], "parent_state": fixture["states"][fold["fold"]]}


def probes(template, probabilities, possessions):
    rows = []
    for index, (p, h) in enumerate(zip(probabilities, possessions, strict=True)):
        row = copy.deepcopy(template); row.trusted["market_probability"] = p
        row = with_possession(row, h)
        rows.append(replace(row, game_id=f"probe-{index}", market_features=(math.log(p / (1 - p)), *row.market_features[1:])))
    return rows, {"possession_by_game_id": {row.game_id: h for row, h in zip(rows, possessions, strict=True)}}


class UncertaintyPossessionTests(unittest.TestCase):
    def test_actual_frozen_formula_bounds_sign_and_joint_complements(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            p, h = [.125, .25, .5, .75, .875], [0, 1, 0, 1, 0]
            rows, features = probes(f["rows"][0], p, h)
            z = candidate.uncertainty_column(rows, features)
            self.assertEqual(z.tolist(), [(2 * v - 1) * 4 * q * (1 - q) for q, v in zip(p, h)])
            self.assertTrue(np.all(np.abs(z) <= 1)); self.assertEqual(z[2], -1.)
            opposite, context = probes(f["rows"][0], [1 - q for q in p], [1 - v for v in h])
            np.testing.assert_array_equal(candidate.uncertainty_column(opposite, context), -z)
            for beta, gamma in ((-.4, .3), (-1., -2.), (.05, 100.)):
                q = candidate.probabilities(beta, gamma, rows, features)[0]
                reverse = candidate.probabilities(beta, gamma, opposite, context)[0]
                np.testing.assert_allclose(q, 1 - np.asarray(reverse), atol=1e-15, rtol=0)
                self.assertTrue(all(candidate.parent.EPSILON <= v <= 1 - candidate.parent.EPSILON for v in q))

    def test_exact_binary_causal_anchor_semantics_and_probability_logit_consistency(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            row = f["rows"][0]
            for h in (0., 1.):
                self.assertEqual(candidate.possession_value(with_possession(row, h), {"possession_is_home": str(h)}), h)
            for h in (None, True, np.bool_(False), .5, -1., 2., float("nan"), float("inf"), "0"):
                with self.subTest(h=h), self.assertRaises(ValueError): candidate.possession_value(with_possession(row, h))
            for anchor in ({}, {"possession_is_home": True}, {"possession_is_home": "bad"}, {"possession_is_home": 1.}):
                with self.assertRaises(ValueError): candidate.possession_value(with_possession(row, 0.), anchor)
            with self.assertRaises(ValueError): candidate.possession_value(replace(row, state_features=()))
            names = list(common.base.STATE_FEATURE_NAMES); names[2] = "future_possession"
            with mock.patch.object(common.base, "STATE_FEATURE_NAMES", tuple(names)), self.assertRaises(ValueError):
                candidate.possession_value(row)
            bad = replace(row, market_features=(row.market_features[0] + .001, *row.market_features[1:]))
            with self.assertRaisesRegex(ValueError, "logit"): candidate.uncertainty_column([bad], f["features"])

    def test_no_other_predictive_fields_or_outcomes_enter_features(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            changed = copy.deepcopy(f["rows"])
            for row in changed:
                row.trusted["outcome"] = 1 - row.trusted["outcome"]
                row.trusted.update(final_score=999, future_play="forbidden")
                row.source_receipt.clear()
            changed = [with_possession(row, row.state_features[2], poison=True) for row in changed]
            frozen = copy.deepcopy(f["frozen"])
            for anchor in frozen["anchors"]: anchor.update(yards_to_go=None, yards_gained_future=999)
            features, receipt = candidate.prepare_features(changed, frozen, f["states"])
            self.assertEqual(features, f["features"])
            self.assertEqual(receipt["fitted_weight_parameters"], 0)
            self.assertFalse(receipt["other_predictive_state_fields_used"])
            for rows, states in ((changed[:-1], f["states"]), (changed, {1: f["states"][1]})):
                with self.assertRaises(ValueError): candidate.prepare_features(rows, frozen, states)

    def test_gamma_zero_exact_C7_and_beta_gamma_zero_exact_raw(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            for beta in (-1., -.4, 0., .04, 5.):
                self.assertEqual(candidate.probabilities(beta, 0., f["rows"], f["features"]), candidate.parent.probabilities(beta, f["rows"]))
            self.assertEqual(candidate.probabilities(0., 0., f["rows"], f["features"])[0], [r.trusted["market_probability"] for r in f["rows"]])
            for beta, gamma in ((-1.1, 0.), (float("nan"), 0.), (0., float("inf"))):
                with self.assertRaises(ValueError): candidate.probabilities(beta, gamma, f["rows"], f["features"])

    def test_unchanged_optimizer_derivatives_bounds_zero_column_and_KKT(self):
        self.assertIs(candidate.solve_joint, candidate.math_recipe.solve_joint)
        self.assertIs(candidate.objective_gradient_hessian, candidate.math_recipe.objective_gradient_hessian)
        l, p, h, y = np.array([-4., -1., .7, 3.]), np.array([.02, .25, .65, .95]), np.array([0., 1., 0., 1.]), np.array([0., 1., 0., 1.])
        z, theta = (2 * h - 1) * 4 * p * (1 - p), np.array([.1, -.2])
        value, g, H = candidate.objective_gradient_hessian(theta, l, z, y)
        eta = (1 + theta[0]) * l + theta[1] * z
        self.assertAlmostEqual(value, float(np.sum(np.logaddexp(0., eta) - y * eta) + 8 * (theta @ theta)), places=13)
        step, fg, fh = 1e-5, [], []
        for index in range(2):
            delta = np.eye(2)[index] * step
            plus, minus = [candidate.objective_gradient_hessian(point, l, z, y) for point in (theta + delta, theta - delta)]
            fg.append((plus[0] - minus[0]) / (2 * step)); fh.append((plus[1] - minus[1]) / (2 * step))
        np.testing.assert_allclose(g, fg, atol=1e-7, rtol=0); np.testing.assert_allclose(H, np.asarray(fh).T, atol=1e-7, rtol=0)
        fitted, receipt = candidate.solve_joint(l, z, y, .1)
        self.assertEqual(receipt["fit_only_brackets"], [[-1., 1 + sum(abs(l)) / 16], [-1 - sum(abs(z)) / 16, 1 + sum(abs(z)) / 16]])
        self.assertLessEqual(receipt["KKT"], 1e-8); self.assertGreaterEqual(np.linalg.eigvalsh(receipt["hessian"]).min(), 16 - 1e-10)
        self.assertLessEqual(receipt["F"], receipt["F_warmstart"] + 1e-8)
        beta, _ = candidate.parent.solve_temperature(l, y)
        nested, _ = candidate.solve_joint(l, np.zeros(4), y, beta)
        self.assertEqual(nested[1], 0.); self.assertAlmostEqual(nested[0], beta, places=8)

    def test_check_label_isolation_and_saved_state_exact_replay_no_refit(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
            fit, check, features = fold_rows(f)
            values, report = candidate.fit_predict(fit, check, features)
            changed = copy.deepcopy(check)
            for row in changed: row.trusted["outcome"] = 1 - row.trusted["outcome"]
            changed = [with_possession(row, row.state_features[2], poison=True) for row in changed]
            other, second = candidate.fit_predict(fit, changed, features)
            self.assertEqual(values, other); self.assertEqual(report["primitive_prediction_state"], second["primitive_prediction_state"])
            with mock.patch.object(candidate, "solve_joint", side_effect=AssertionError("no refit")):
                self.assertEqual(candidate.replay_predictor(report["primitive_prediction_state"], check, features), (values, report["bounding"]))
            for key, value in (("contract_sha256", "0" * 64), ("execution_spec_sha256", "0" * 64),
                    ("transform", "constant"), ("column_index", 7), ("fit_z_absolute_sum", float("inf")),
                    ("fit_logit_absolute_sum", -1), ("z_check_sha256", "0" * 64), ("gamma", float("nan"))):
                state = copy.deepcopy(report["primitive_prediction_state"]); state[key] = value
                with self.subTest(key=key), self.assertRaises(ValueError): candidate.replay_predictor(state, check, features)

    def test_exact_entry_four_synthetic_fits195_denominator87_predictions_no_control_refit(self):
        with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f, mock.patch.object(candidate, "solve_joint", wraps=candidate.solve_joint) as solve:
            candidate.run(f["source"], f["output"])
            self.assertEqual(solve.call_count, 4)
            manifest = common.settlement._strict_json(f["output"] / "manifest.json")
            card = common.settlement._strict_json(f["output"] / "scorecard.json")
            self.assertEqual((manifest["source_events"], manifest["materialized_events"], manifest["excluded_events"], manifest["check_events"], manifest["model_fits"]), (195, 193, 2, 87, 4))
            self.assertEqual(card["parent_replay"]["parent_refits"], 0)
            self.assertEqual([fold["fit_events"] for fold in card["folds"]], [106, 132, 148, 176])
            self.assertEqual((card["scientific_decision"], card["operational_decision"], card["decision_conditions"]), common.decision(card["aggregate"], card["folds"], card["paired_grouped_evidence"], candidate.ARM_CANDIDATE))
            states = common.settlement._strict_json(f["output"] / "predictor_states.json")
            csv = common.frozen_v0._read_csv(f["output"] / "predictions.csv")
            for saved in states["folds"]:
                fit, check, features = fold_rows(f, saved["fold"] - 1)
                self.assertEqual(saved["state"]["contract_sha256"], candidate.CONTRACT_SHA256)
                self.assertEqual(saved["state"]["fit_z_absolute_sum"], math.fsum(abs(v) for v in candidate.uncertainty_column(fit, features)))
                self.assertEqual(candidate.replay_predictor(saved["state"], check, features)[0], [float(row["candidate_probability"]) for row in csv if int(row["fold"]) == saved["fold"]])
            with self.assertRaises(FileExistsError): candidate.run(f["source"], f["output"])

    def test_missing_inconsistent_anchor_invalidates_whole_candidate_prefit(self):
        for value in (None, True, .5, "bad", float("nan")):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f, mock.patch.object(candidate, "solve_joint") as solve:
                f["frozen"]["anchors"][0]["possession_is_home"] = value
                with self.assertRaisesRegex(ValueError, "possession"): candidate.run(f["source"], f["output"])
                self.assertEqual(solve.call_count, 0)
                failure = common.settlement._strict_json(f["output"] / "failure.json")
                self.assertEqual(failure["fit_progress"]["fit_calls_entered"], 0)
                self.assertFalse((f["output"] / "predictions.csv").exists())

    def test_clock_request_and_both_contract_sources_fail_prefit(self):
        for key, value in (("spec_sha256", "0" * 64), ("max_fits", True), ("max_fits", 3), ("max_wall_seconds", 901), ("source_commit", "other")):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f, mock.patch.object(candidate, "solve_joint") as solve:
                f["request"][key] = value; common.base._atomic_json(f["request_path"], f["request"])
                with self.assertRaises(ValueError): candidate.run(f["source"], f["output"])
                self.assertEqual(solve.call_count, 0)
        for relative in (candidate.CONTRACT_RELATIVE, candidate.EXECUTION_SPEC_RELATIVE, candidate.RULE_RELATIVE):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
                f["request"]["files"][relative] = "0" * 64; common.base._atomic_json(f["request_path"], f["request"])
                with self.assertRaises(ValueError): candidate.run(f["source"], f["output"])
        for time in (datetime(2026, 10, 6, 15, tzinfo=timezone.utc), datetime(2026, 10, 6, 16, 34, 53, tzinfo=timezone.utc)):
            with tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f, mock.patch.object(candidate, "utc_now", return_value=time):
                with self.assertRaisesRegex(ValueError, "authority"): candidate.run(f["source"], f["output"])

    def test_partial_optimizer_and_postfit_failures_preserve_truthful_receipts(self):
        for mode in ("optimizer", "output"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory, entry_fixture(directory) as f:
                target = mock.patch.object(candidate.math_recipe, "objective_gradient_hessian", side_effect=ValueError("synthetic optimizer failure")) if mode == "optimizer" else mock.patch.object(candidate, "probabilities", side_effect=ValueError("synthetic postfit failure"))
                with target, self.assertRaises(candidate.FitFailure): candidate.run(f["source"], f["output"])
                failure = common.settlement._strict_json(f["output"] / "failure.json")
                self.assertEqual((failure["fit_progress"]["fit_calls_entered"], failure["fit_progress"]["fit_calls_completed"]), (1, 0))
                self.assertEqual(failure["optimizer_partial_receipt"]["optimization_calls_started"], 1)
                self.assertEqual(failure["optimizer_partial_receipt"]["optimization_calls_completed"], int(mode == "output"))
                self.assertFalse((f["output"] / "scorecard.json").exists())


if __name__ == "__main__": unittest.main()
