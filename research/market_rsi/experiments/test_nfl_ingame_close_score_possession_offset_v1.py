"""Synthetic close-score possession semantics, replay and comparison-only execution."""
from dataclasses import replace
import copy
import tempfile
from pathlib import Path
import unittest
from unittest import mock
import numpy as np
from experiments import nfl_ingame_close_score_possession_offset_v1 as c
from experiments import test_nfl_ingame_market_temperature_offset as fixtures
from experiments import test_nfl_ingame_candidate_evidence_adapter as inherited
from experiments import test_nfl_ingame_candidate_evidence_adapter_v2 as v2fixtures

class CloseScoreTests(unittest.TestCase):
    def setUp(self):
        rows, _ = fixtures.expanded_problem(); self.fit, self.check = rows[:106], rows[106:132]
        self.context = {"features": {}, "fold_id": 1, "parent_reference": {"comparison_only": True}}

    def test_feature_exact_semantics_and_invalid(self):
        self.assertEqual(c.validate_feature()["statistical_fits"], 0)
        for score in (-28., -14., -7., 0., 7., 14., 28.):
            x = c.derived_feature(score, 1)
            self.assertTrue(0 <= x <= 1); self.assertEqual(x, -c.derived_feature(score, 0))
            if abs(score) >= 14: self.assertEqual(x, 0)
        for bad in (True, np.bool_(False), None, "0", float("nan"), float("inf")):
            with self.assertRaises(ValueError): c.derived_feature(bad, 1)
            with self.assertRaises(ValueError): c.derived_feature(0, bad)
        with self.assertRaises(ValueError): c.derived_feature(0, .5)

    def test_gradient_and_single_fit_exact_replay_check_label_isolation(self):
        matrix = c.columns(self.fit); y = np.array([r.trusted["outcome"] for r in self.fit]); theta = np.array([.1, -.2])
        _, g = c.objective_gradient(theta, matrix, y)
        for index in range(2):
            d = np.eye(2)[index]*1e-5
            numeric = (c.objective_gradient(theta+d, matrix, y)[0]-c.objective_gradient(theta-d, matrix, y)[0])/2e-5
            self.assertAlmostEqual(g[index], numeric, places=7)
        with mock.patch.object(c, "minimize", wraps=c.minimize) as solver:
            values, trainer = c.fit_predict(self.fit, self.check, self.context)
        self.assertEqual(solver.call_count, 1)
        self.assertEqual((values, trainer["bounding"]), c.replay_predictor(trainer["primitive_prediction_state"], self.check, self.context))
        poisoned = [replace(r, trusted={**r.trusted, "outcome": float("nan")}) for r in self.check]
        changed, second = c.fit_predict(self.fit, poisoned, self.context)
        self.assertEqual(values, changed); self.assertEqual(trainer["primitive_prediction_state"], second["primitive_prediction_state"])

    def test_failures_before_solver_no_retry_and_replay_drift(self):
        bad = replace(self.fit[0], state_features=(0., 0., .5, *self.fit[0].state_features[3:]))
        with mock.patch.object(c, "minimize") as solver, self.assertRaises(ValueError):
            c.fit_predict([bad, *self.fit[1:]], self.check, self.context)
        solver.assert_not_called()
        with mock.patch.object(c, "minimize", side_effect=RuntimeError("synthetic failure")) as solver, self.assertRaises(c.harness.c7.FitFailure):
            c.fit_predict(self.fit, self.check, self.context)
        self.assertEqual(solver.call_count, 1)
        _, trainer = c.fit_predict(self.fit, self.check, self.context); state = trainer["primitive_prediction_state"]
        for key, value in [("formula", "wrong"), ("beta", -2.), ("epsilon", .001), ("fold_id", True)]:
            altered = copy.deepcopy(state); altered[key] = value
            with self.assertRaises(ValueError): c.replay_predictor(altered, self.check, self.context)

    def test_fourfold_model_agnostic_parent_path_and_invalid_parent_before_fit(self):
        with tempfile.TemporaryDirectory() as directory, inherited.synthetic_environment(directory) as env:
            source, rows, folds, frozen, controls = env
            binding, _ = v2fixtures.fixture_binding(Path(directory).resolve(), rows, folds, frozen, controls, parent_id="InGameTemperatureScoreTimeJointOffset-v1")
            # This is synthetic original evidence, not live historical acceptance.
            binding["accepted_reference"]["reference"]["runner"]["sha256"] = c.PARENT_SHA
            original = Path(binding["accepted_reference"]["reference"]["runner"]["path"])
            actual = c.common._sha256(original)
            with mock.patch.object(c, "PARENT_SHA", actual):
                binding["accepted_reference"]["reference"]["runner"]["sha256"] = actual
                contract_path = Path(binding["candidate_contract_path"]); contract = c.common.settlement._strict_json(contract_path)
                own = str(Path(c.__file__).resolve())
                contract.update(candidate_id=c.TASK_ID, fixed_predictive_information={"feature_names": c.FEATURE_NAMES})
                c.common.base._atomic_json(contract_path, contract)
                binding.update(candidate_id=c.TASK_ID, arm=c.ARM_CANDIDATE, feature_names=c.FEATURE_NAMES,
                    candidate_source_path=own, candidate_source_sha256=c.common._sha256(Path(own)), candidate_contract_sha256=c.common._sha256(contract_path),
                    callback_source_bindings={name: own for name in ("prepare_features", "fit_predict", "replay_predictor")})
                binding["dependency_source_hashes"][own] = binding["candidate_source_sha256"]
                with mock.patch.object(c, "minimize", wraps=c.minimize) as solver:
                    result = c.run(source, Path(directory)/"complete", binding, allow_test_paths=True)
                self.assertEqual(solver.call_count, 4); self.assertEqual(result["check_events"], 87)
                broken = copy.deepcopy(binding); broken["accepted_reference"]["acceptance_binding"]["sha256"] = "f"*64
                with mock.patch.object(c, "minimize") as solver, self.assertRaises(ValueError):
                    c.run(source, Path(directory)/"blocked", broken, allow_test_paths=True)
                solver.assert_not_called()

    def test_native_admission_one_isolated_child_and_closed_mismatch(self):
        output = Path("/tmp/synthetic-native/runs/c1")
        grant = {"batch_id": c.BATCH, "start_utc": "2026-10-06T00:00:00Z", "deadline_utc": "2026-10-07T00:00:00Z"}
        request = {"attempt_id": "c1", "candidate_id": c.TASK_ID, "module": c.MODULE, "max_fits": 4,
            "spec_sha256": "a"*64, "runtime_pair_sha256": "b"*64}
        binding = {"candidate_contract_sha256": "a"*64}
        native = {"batch_id": c.BATCH, "max_attempts": 1, "deadline_utc": grant["deadline_utc"], "micro_evolution": {},
            "branches": [{"attempt_id": "c1", "candidate_id": c.TASK_ID, "stage": "execution_claimed", "claim_id": "c1-claim"}]}
        def load(path):
            return {"authorization.json": grant, "c1.request.json": request, "binding.json": binding}[Path(path).name]
        with mock.patch.object(c.worker, "sha", return_value=c.AUTH_SHA), mock.patch.object(c.worker, "validate"), \
                mock.patch.object(c.common.settlement, "_strict_json", side_effect=load), \
                mock.patch.object(c, "ContinuousDiscoveryBatch") as batch, mock.patch.object(c, "micro_pair_hash", return_value="b"*64), \
                mock.patch.object(c.harness, "validate_binding"):
            batch.return_value.snapshot.return_value = native
            self.assertIs(c.require_admission(c.worker.TRAIN, output), binding)
            for key, value in [("max_attempts", 3), ("batch_id", "closedoldbatch"), ("deadline_utc", "2020-01-01T00:00:00Z")]:
                broken = copy.deepcopy(native); broken[key] = value; batch.return_value.snapshot.return_value = broken
                with self.assertRaises(ValueError): c.require_admission(c.worker.TRAIN, output)

if __name__ == "__main__": unittest.main()
