"""Synthetic short-yardage interaction tests; no resident data."""
import copy
from dataclasses import replace
import tempfile
from pathlib import Path
import unittest
from unittest import mock
import numpy as np
from experiments import nfl_ingame_short_yardage_possession_offset_v1 as c
from experiments import test_nfl_ingame_market_temperature_offset as fixtures
from experiments import test_nfl_ingame_candidate_evidence_adapter as inherited
from experiments import test_nfl_ingame_candidate_evidence_adapter_v2 as v2fixtures

class ShortYardageTests(unittest.TestCase):
    def setUp(self):
        rows, _ = fixtures.expanded_problem(); self.fit, self.check = rows[:106], rows[106:132]
        self.context = {"features": {}, "fold_id": 1, "parent_reference": {"comparison_only": True,
            "runner_sha256": c.PARENT_SHA, "candidate_id": "InGameTemperatureCloseScorePossessionJointOffset-v1", "reference_sha256": "a"*64}}

    def test_exact_semantics_and_invalid_inputs(self):
        self.assertEqual(c.validate_feature()["statistical_fits"], 0)
        for yards, expected in [(0., 1.), (10., .5), (20., 0.), (40., 0.)]:
            self.assertEqual(c.derived_feature(yards, 1), expected)
            self.assertEqual(c.derived_feature(yards, 0), -expected)
        for bad in (True, np.bool_(False), None, "0", float("nan"), float("inf"), -1.):
            with self.assertRaises(ValueError): c.derived_feature(bad, 1)
        for bad in (True, .5, float("nan")):
            with self.assertRaises(ValueError): c.derived_feature(0, bad)
        for bad in (True, -.01, 1.01, float("inf")):
            row = replace(self.fit[0], trusted={**self.fit[0].trusted, "market_probability": bad})
            with self.assertRaises(ValueError): c.columns([row])

    def test_gradient_single_fit_replay_and_check_label_isolation(self):
        matrix = c.columns(self.fit); y = np.array([r.trusted["outcome"] for r in self.fit]); theta = np.array([.1, -.2])
        _, gradient = c.objective_gradient(theta, matrix, y)
        for i in range(2):
            d = np.eye(2)[i]*1e-5
            numeric = (c.objective_gradient(theta+d, matrix, y)[0]-c.objective_gradient(theta-d, matrix, y)[0])/2e-5
            self.assertAlmostEqual(gradient[i], numeric, places=7)
        with mock.patch.object(c, "minimize", wraps=c.minimize) as solver:
            values, trainer = c.fit_predict(self.fit, self.check, self.context)
        self.assertEqual(solver.call_count, 1)
        state = trainer["primitive_prediction_state"]
        self.assertEqual((values, trainer["bounding"]), c.replay_predictor(state, self.check, self.context))
        poisoned = [replace(r, trusted={**r.trusted, "outcome": float("nan")}) for r in self.check]
        self.assertEqual((values, trainer["bounding"]), c.replay_predictor(state, poisoned, self.context))
        changed, again = c.fit_predict(self.fit, poisoned, self.context)
        self.assertEqual(values, changed); self.assertEqual(state, again["primitive_prediction_state"])

    def test_fail_closed_inputs_parent_no_retry_and_state_drift(self):
        bad = replace(self.fit[0], state_features=(*self.fit[0].state_features[:7], -1., self.fit[0].state_features[8]))
        with mock.patch.object(c, "minimize") as solver, self.assertRaises(ValueError):
            c.fit_predict([bad, *self.fit[1:]], self.check, self.context)
        solver.assert_not_called()
        context = copy.deepcopy(self.context); context["parent_reference"]["runner_sha256"] = "b"*64
        with mock.patch.object(c, "minimize") as solver, self.assertRaises(ValueError): c.fit_predict(self.fit, self.check, context)
        solver.assert_not_called()
        with mock.patch.object(c, "minimize", side_effect=RuntimeError("synthetic failure")) as solver, self.assertRaises(c.harness.c7.FitFailure):
            c.fit_predict(self.fit, self.check, self.context)
        self.assertEqual(solver.call_count, 1)
        _, trainer = c.fit_predict(self.fit, self.check, self.context)
        for key, value in [("formula", "wrong"), ("yards_divisor", 10.), ("beta", -2.), ("fold_id", True), ("parent_identity", {})]:
            state = copy.deepcopy(trainer["primitive_prediction_state"]); state[key] = value
            with self.assertRaises(ValueError): c.replay_predictor(state, self.check, self.context)

    def test_output_expit_not_silently_clipped(self):
        values, bounding = c.probabilities([0., 0.], self.check)
        self.assertEqual(bounding["clipped_rows"], 0)
        self.assertTrue(all(0 < v < 1 for v in values))
        with self.assertRaises(ValueError): c.probabilities([100., 0.], self.check)

    def test_fourfold_saved_negative_parent_comparison(self):
        with tempfile.TemporaryDirectory() as directory, inherited.synthetic_environment(directory) as env:
            source, rows, folds, frozen, controls = env
            binding, _ = v2fixtures.fixture_binding(Path(directory).resolve(), rows, folds, frozen, controls,
                parent_id="InGameTemperatureCloseScorePossessionJointOffset-v1")
            actual = binding["accepted_reference"]["reference"]["runner"]["sha256"]
            with mock.patch.object(c, "PARENT_SHA", actual):
                contract_path = Path(binding["candidate_contract_path"]); contract = c.common.settlement._strict_json(contract_path)
                own = str(Path(c.__file__).resolve())
                contract.update(candidate_id=c.TASK_ID, fixed_predictive_information={"feature_names": c.FEATURE_NAMES})
                c.common.base._atomic_json(contract_path, contract)
                binding.update(candidate_id=c.TASK_ID, arm=c.ARM_CANDIDATE, feature_names=c.FEATURE_NAMES,
                    candidate_source_path=own, candidate_source_sha256=c.common._sha256(Path(own)),
                    candidate_contract_sha256=c.common._sha256(contract_path),
                    callback_source_bindings={name: own for name in ("prepare_features", "fit_predict", "replay_predictor")})
                binding["dependency_source_hashes"][own] = binding["candidate_source_sha256"]
                with mock.patch.object(c, "minimize", wraps=c.minimize) as solver:
                    result = c.run(source, Path(directory)/"complete", binding, allow_test_paths=True)
                self.assertEqual(solver.call_count, 4); self.assertEqual(result["check_events"], 87)
                broken = copy.deepcopy(binding); broken["accepted_reference"]["acceptance_binding"]["sha256"] = "f"*64
                with mock.patch.object(c, "minimize") as solver, self.assertRaises(ValueError):
                    c.run(source, Path(directory)/"blocked", broken, allow_test_paths=True)
                solver.assert_not_called()

if __name__ == "__main__": unittest.main()
