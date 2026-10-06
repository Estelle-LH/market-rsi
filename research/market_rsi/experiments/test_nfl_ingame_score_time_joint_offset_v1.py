"""Synthetic-only exact original score-time recipe tests."""
from dataclasses import replace
import copy
import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import numpy as np
from experiments import nfl_ingame_score_time_joint_offset_v1 as c
from experiments import test_nfl_ingame_market_temperature_offset as fixtures
from experiments import test_nfl_ingame_candidate_evidence_adapter as adapter_fixtures
from experiments import test_nfl_ingame_temperature_possession_pressure_entry as parent_fixtures

def synthetic_binding(directory):
    binding = c.harness.held_c7_binding()
    own = str(Path(c.__file__).resolve())
    binding.update(candidate_id=c.TASK_ID, arm=c.ARM_CANDIDATE, feature_names=c.FEATURE_NAMES,
        candidate_source_path=own, candidate_source_sha256=c.common._sha256(Path(own)),
        attribution="synthetic original Controller recipe fixture",
        research_parent={"candidate_id": c.parent.TASK_ID, "runner_sha256": c.harness.C7_SHA256})
    contract = Path(directory) / "candidate_contract.json"
    c.common.base._atomic_json(contract, {"candidate_id": c.TASK_ID, "research_parent": binding["research_parent"],
        "fixed_predictive_information": {"feature_names": c.FEATURE_NAMES},
        "comparison_incumbent_sha256": binding["comparison_incumbent_sha256"], "attribution": binding["attribution"]})
    binding.update(candidate_contract_path=str(contract), candidate_contract_sha256=c.common._sha256(contract),
        callback_source_bindings={name: own for name in ("prepare_features", "fit_predict", "replay_predictor")})
    binding["dependency_source_hashes"][own] = binding["candidate_source_sha256"]
    return binding

class ScoreTimeTests(unittest.TestCase):
    def setUp(self):
        rows, _ = fixtures.expanded_problem()
        self.fit, self.check = rows[:106], rows[106:132]
        self.context = {"fold_id": 1, "parent_state": {"beta": 999., "fit_events": 106}}

    def test_scalar_orientation_clipping_and_invalid(self):
        for score, seconds, expected in [(14, 1800, .5), (-14, 1800, -.5), (0, 100, 0), (28, 900, .75), (3.5, 2700, .0625), (14, -1, 1), (14, 4000, 0)]:
            self.assertEqual(c.derived_feature(score, seconds), expected)
        for value in [True, np.bool_(False), "1", None, float("nan"), float("inf")]:
            with self.assertRaises(ValueError): c.derived_feature(value, 1)
            with self.assertRaises(ValueError): c.derived_feature(1, value)

    def test_analytic_gradient(self):
        matrix = c.columns(self.fit); y = np.asarray([r.trusted["outcome"] for r in self.fit]); theta = np.array([.1, -.2])
        _, gradient = c.objective_gradient(theta, matrix, y)
        for index in range(2):
            delta = np.eye(2)[index] * 1e-5
            numeric = (c.objective_gradient(theta + delta, matrix, y)[0] - c.objective_gradient(theta - delta, matrix, y)[0]) / 2e-5
            self.assertAlmostEqual(gradient[index], numeric, places=7)

    def test_home_token_joint_orientation(self):
        row = self.check[0]; p = .75
        home = replace(row, trusted={**row.trusted, "market_probability": p},
            market_features=(math.log(p / (1 - p)), *row.market_features[1:]),
            state_features=(7., 900., *row.state_features[2:]))
        away = replace(home, trusted={**home.trusted, "market_probability": 1-p},
            market_features=(math.log((1-p) / p), *home.market_features[1:]),
            state_features=(-7., 900., *home.state_features[2:]))
        q, _ = c.probabilities([.2, .7], [home]); opposite, _ = c.probabilities([.2, .7], [away])
        self.assertAlmostEqual(q[0], 1-opposite[0], places=15)

    def test_single_call_exact_replay_no_parent_warmstart_check_label_isolation(self):
        with mock.patch.object(c, "minimize", wraps=c.minimize) as solve:
            values, trainer = c.fit_predict(self.fit, self.check, self.context)
        self.assertEqual(solve.call_count, 1); self.assertEqual(trainer["optimizer"]["initial"], [0., 0.])
        self.assertEqual((values, trainer["bounding"]), c.replay_predictor(trainer["primitive_prediction_state"], self.check, self.context))
        poisoned = [replace(r, trusted={**r.trusted, "outcome": float("nan")}) for r in self.check]
        values2, trainer2 = c.fit_predict(self.fit, poisoned, {"fold_id": 1, "parent_state": {"beta": -999.}})
        self.assertEqual(values, values2); self.assertEqual(trainer["primitive_prediction_state"], trainer2["primitive_prediction_state"])

    def test_invalid_inputs_before_solver_and_no_fallback(self):
        bad = replace(self.fit[0], state_features=(True, *self.fit[0].state_features[1:]))
        with mock.patch.object(c, "minimize") as solve, self.assertRaises(ValueError):
            c.fit_predict([bad, *self.fit[1:]], self.check, self.context)
        solve.assert_not_called()
        with mock.patch.object(c, "minimize", side_effect=RuntimeError("synthetic failure")) as solve, self.assertRaises(c.parent.FitFailure) as caught:
            c.fit_predict(self.fit, self.check, self.context)
        self.assertEqual(solve.call_count, 1); self.assertEqual(caught.exception.receipt["optimization_calls_completed"], 0)

    def test_replay_rejects_recipe_or_matrix_drift(self):
        _, trainer = c.fit_predict(self.fit, self.check, self.context); state = trainer["primitive_prediction_state"]
        for key, value in [("epsilon", .001), ("formula", "wrong"), ("beta", -2.), ("fold_id", True)]:
            bad = copy.deepcopy(state); bad[key] = value
            with self.assertRaises(ValueError): c.replay_predictor(bad, self.check, self.context)
        changed = replace(self.check[0], state_features=(7., 10., *self.check[0].state_features[2:]))
        with self.assertRaises(ValueError): c.replay_predictor(state, [changed, *self.check[1:]], self.context)

    def test_fourfold_h1_execution_semantic_gate_before_fits_and_no_overwrite(self):
        from supervisor_harness import derived_feature_semantic_contract_v1 as semantic
        with tempfile.TemporaryDirectory() as directory, adapter_fixtures.synthetic_environment(directory) as environment:
            source, rows, folds, frozen, _ = environment
            binding = synthetic_binding(directory); parents, states = parent_fixtures.numeric_parent(rows, folds)
            with mock.patch.object(c.harness, "load_parent", return_value=(parents, states)):
                with mock.patch.object(semantic, "validate_feature", side_effect=ValueError("injected semantic disagreement")), mock.patch.object(c, "minimize") as solve:
                    with self.assertRaises(ValueError): c.run(source, Path(directory) / "blocked", binding, allow_test_paths=True)
                    solve.assert_not_called()
                with mock.patch.object(c, "minimize", wraps=c.minimize) as solve, mock.patch.object(semantic, "validate_feature", wraps=semantic.validate_feature) as gate:
                    manifest = c.run(source, Path(directory) / "complete", binding, allow_test_paths=True)
                self.assertEqual(solve.call_count, 4); self.assertEqual(gate.call_count, 1)
                self.assertEqual(manifest["model_fits"], 4)
                card = c.common.settlement._strict_json(Path(directory) / "complete/scorecard.json")
                self.assertEqual(card["source_denominator"]["check_events"], 87)
                with self.assertRaises(FileExistsError): c.run(source, Path(directory) / "complete", binding, allow_test_paths=True)

if __name__ == "__main__": unittest.main()
