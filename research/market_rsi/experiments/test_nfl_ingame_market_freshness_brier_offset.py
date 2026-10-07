from __future__ import annotations

import csv
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

from experiments import nfl_ingame_market_freshness_brier_offset as candidate
from experiments import test_nfl_ingame_market_freshness_interaction_offset as parent_tests
from experiments.test_nfl_ingame_market_freshness_interaction_offset import synthetic_problem


def synthetic_parent(rows, folds):
    result = {}
    for fold in folds:
        fit = sorted([row for row in rows if row.game_date in fold["fit_dates"]], key=lambda row: row.key)
        check = sorted([row for row in rows if row.game_date in fold["check_dates"]], key=lambda row: row.key)
        _, features, _ = candidate.common.freshness_features(fit, check, states={})
        for row, feature in zip(check, features, strict=True):
            result[row.key] = {"feature": float(feature), "probability": row.trusted["market_probability"] + .002}
    return result


class FreshnessBrierOffsetTests(unittest.TestCase):
    def test_brier_sum_ridge16_analytic_gradient_and_finite_difference(self):
        beta = .2
        x, y, offsets = np.array([1., -1., .5, 2.]), np.array([1., 0., 0., 1.]), np.array([.2, -.3, .1, -.1])
        value, gradient = candidate.brier_objective_gradient([beta], x, y, offsets)
        q = candidate.expit(offsets + beta * x)
        self.assertAlmostEqual(value, float(np.sum((q - y) ** 2) + .5 * 16 * beta ** 2), places=12)
        self.assertAlmostEqual(gradient[0], float(2 * np.sum(x * (q - y) * q * (1 - q)) + 16 * beta), places=12)
        h = 1e-6
        numerical = (candidate.brier_objective_gradient([beta + h], x, y, offsets)[0]
            - candidate.brier_objective_gradient([beta - h], x, y, offsets)[0]) / (2 * h)
        self.assertAlmostEqual(gradient[0], numerical, places=7)
        for theta, feature, labels in (([math.nan], x, y), ([0., 1.], x, y), ([0.], [math.nan], [1.]),
                ([0.], x, [1., 0., .5, 1.]), ([0.], x, [1., 0.])):
            with self.assertRaises(ValueError):
                candidate.brier_objective_gradient(theta, feature, labels, offsets)

    def test_synthetic_fit_exact_optimizer_flags_and_strict_no_retry(self):
        with mock.patch.object(candidate, "minimize", wraps=candidate.minimize) as minimize:
            beta, report = candidate.fit_brier_offset([1., -1.] * 10, [1., 0.] * 10, [0.] * 20)
        self.assertTrue(math.isfinite(beta))
        self.assertLessEqual(report["absolute_analytic_gradient"], 1e-8)
        self.assertEqual(minimize.call_count, 1)
        self.assertEqual(minimize.call_args.kwargs["method"], "L-BFGS-B")
        self.assertTrue(minimize.call_args.kwargs["jac"])
        self.assertEqual(minimize.call_args.kwargs["options"], {"maxiter": 500, "gtol": 1e-8, "ftol": 1e-12})
        np.testing.assert_array_equal(minimize.call_args.args[1], [0.])
        self.assertEqual(report["retry_count"], 0)
        self.assertFalse(report["global_optimum_claim"])
        self.assertNotIn("bounds", minimize.call_args.kwargs)
        for success, beta, value in ((False, 0., 1.), (True, 1., 1.), (True, 0., math.nan)):
            fake = SimpleNamespace(success=success, x=np.array([beta]), fun=value)
            with mock.patch.object(candidate, "minimize", return_value=fake) as minimize:
                with self.assertRaisesRegex(RuntimeError, "convergence failed"):
                    candidate.fit_brier_offset([1., -1.], [1., 0.], [0., 0.])
                self.assertEqual(minimize.call_count, 1)

    def test_feature_and_transform_exact_a1_reuse_and_four_synthetic_fits(self):
        rows, folds, controls, _ = synthetic_problem()
        parent = synthetic_parent(rows, folds)
        with mock.patch.object(candidate, "fit_brier_offset", wraps=candidate.fit_brier_offset) as fit:
            predictions, reports = candidate.fit_and_predict(rows, folds, controls, parent)
        self.assertEqual(fit.call_count, 4)
        self.assertEqual(len(predictions), 20)
        self.assertEqual({item["row"].key for item in predictions}, set(controls))
        for item in predictions:
            self.assertEqual(item["feature"], parent[item["row"].key]["feature"])
            self.assertEqual(item[candidate.ARM_RESEARCH_PARENT], parent[item["row"].key]["probability"])
        for fold, report in zip(folds, reports, strict=True):
            fit_rows = sorted([row for row in rows if row.game_date in fold["fit_dates"]], key=lambda row: row.key)
            checks = sorted([row for row in rows if row.game_date in fold["check_dates"]], key=lambda row: row.key)
            self.assertEqual(report["feature_transform"], candidate.common.freshness_features(fit_rows, checks, states={})[2])
        missing = dict(parent)
        missing.pop(next(iter(missing)))
        with mock.patch.object(candidate, "fit_brier_offset", side_effect=AssertionError("no fit")):
            with self.assertRaisesRegex(ValueError, "before fit"):
                candidate.fit_and_predict(rows, folds, controls, missing)

    def test_parent_additional_pairing_arithmetic_and_unchanged_judge(self):
        rows, folds, controls, _ = synthetic_problem()
        parent = synthetic_parent(rows, folds)
        predictions, reports = candidate.fit_and_predict(rows, folds, controls, parent)
        aggregate = candidate.aggregate(predictions)
        self.assertEqual(aggregate[candidate.ARM_RESEARCH_PARENT]["brier"],
            candidate.common.settlement._simple_metrics([row["row"].trusted["outcome"] for row in predictions],
                [row[candidate.ARM_RESEARCH_PARENT] for row in predictions])["brier"])
        calls = []
        def bootstrap(records, group, value, *, seed, replicates):
            calls.append((group, seed, replicates))
            return {"interval_95": [-.1, .1]}
        with mock.patch.object(candidate.common.base, "_group_bootstrap", side_effect=bootstrap):
            paired = candidate.paired_evidence(predictions)
        self.assertEqual(len(calls), 16)
        self.assertTrue(all(item[1:] == (20260929, 10000) for item in calls))
        parent_pair = paired[f"candidate_minus_{candidate.ARM_RESEARCH_PARENT}"]
        for metric in ("brier", "log_loss"):
            expected = math.fsum(candidate.common.identity._loss(item["row"].trusted["outcome"], item[candidate.ARM_CANDIDATE], metric)
                - candidate.common.identity._loss(item["row"].trusted["outcome"], item[candidate.ARM_RESEARCH_PARENT], metric)
                for item in predictions) / len(predictions)
            self.assertEqual(parent_pair[metric]["equal_event_mean"], expected)
            self.assertEqual(len(parent_pair[metric]["by_schedule_date"]), 20)
        decision = candidate.common.decision(aggregate, reports, paired, candidate.ARM_CANDIDATE)
        # A1 is not introduced as an additional KEEP judge.
        altered = {**aggregate, candidate.ARM_RESEARCH_PARENT: {"brier": 0., "log_loss": 0.}}
        self.assertEqual(candidate.common.decision(altered, reports, paired, candidate.ARM_CANDIDATE), decision)

    def test_zero_beta_and_frozen_source_or_contract_drift(self):
        rows = synthetic_problem()[0][:4]
        raw = [row.trusted["market_probability"] for row in rows]
        self.assertEqual(candidate.common.candidate_probabilities(0., [1.] * 4,
            [row.market_features[0] for row in rows], raw_probabilities=raw), raw)
        with mock.patch.object(candidate.common, "require_dependencies"), \
                mock.patch.object(candidate.common, "_sha256", return_value="0" * 64):
            with self.assertRaisesRegex(ValueError, "hash-changed"):
                candidate.require_dependencies()

    def test_parent_csv_preserves_original_frozen_probabilities(self):
        rows, folds, controls, _ = synthetic_problem()
        parent = synthetic_parent(rows, folds)
        predictions, _ = candidate.fit_and_predict(rows, folds, controls, parent)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.csv"
            candidate.write_predictions(path, predictions)
            written = candidate.common.frozen_v0._read_csv(path)
            self.assertEqual(len(written), 20)
            for item in written:
                key = candidate.common.identity._control_key(item)
                self.assertEqual(float(item["frozen_a1_parent_probability"]), parent[key]["probability"])

    def test_exact87_parent_hash_key_label_and_control_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract, controls, frozen, items = self._parent_fixture(root)
            expected_key = candidate.common._digest([list(candidate.common.identity._control_key(item)) for item in items])
            with mock.patch.object(candidate.common.frozen_v0, "EXPECTED_CHECK_KEY_SHA256", expected_key):
                result = candidate.load_parent_predictions(contract, controls, frozen)
                self.assertEqual(len(result), 87)
                for item in items:
                    key = candidate.common.identity._control_key(item)
                    self.assertEqual(result[key]["probability"], float(item["candidate_probability"]))
                bad_hash = {**contract, "research_parent": {**contract["research_parent"], "predictions_sha256": "0" * 64}}
                with self.assertRaisesRegex(ValueError, "hash changed"):
                    candidate.load_parent_predictions(bad_hash, controls, frozen)
                for column, replacement in (("outcome", "0"), ("raw_market_probability", ".7"),
                        ("fold", "2"), ("candidate_feature", "nan")):
                    changed = [dict(item) for item in items]
                    changed[0][column] = replacement
                    rebound = self._write_parent(root, changed)
                    with self.subTest(column=column), self.assertRaises(ValueError):
                        candidate.load_parent_predictions(rebound, controls, frozen)
                duplicated = [dict(item) for item in items]
                duplicated[-1] = duplicated[0]
                with self.assertRaisesRegex(ValueError, "mask"):
                    candidate.load_parent_predictions(self._write_parent(root, duplicated), controls, frozen)

    def test_failure_preserved_and_no_output_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "attempt"
            with mock.patch.object(candidate.common.base, "_validate_roots"), \
                    mock.patch.object(candidate, "require_dependencies", side_effect=ValueError("parent/source drift")):
                with self.assertRaisesRegex(ValueError, "parent/source drift"):
                    candidate.run(Path(directory) / "source", output, allow_test_paths=True)
            self.assertEqual(candidate.common.settlement._strict_json(output / "failure.json")["error"], "parent/source drift")
            with mock.patch.object(candidate.common.base, "_validate_roots"), self.assertRaises(FileExistsError):
                candidate.run(Path(directory) / "source", output, allow_test_paths=True)

    def test_complete_c3_synthetic195_population87_predictions_and_manifest(self):
        contract = candidate.common.settlement._strict_json(candidate.CONTRACT)
        def parent_loader(contract, controls, frozen):
            states = {state["game_id"]: state for state in frozen["anchors"]}
            cohort = candidate.common.base._validate_source(None)
            rows = [candidate.common.base._load_dynamic_market(None, item, states[item["game_id"]])
                for item in cohort if "exclusion" not in item]
            return synthetic_parent(rows, frozen["folds"])
        with mock.patch.object(candidate.common, "run", side_effect=candidate.run), \
                mock.patch.object(candidate, "require_dependencies", return_value=contract), \
                mock.patch.object(candidate, "load_parent_predictions", side_effect=parent_loader), \
                mock.patch.object(candidate, "fit_brier_offset", wraps=candidate.fit_brier_offset) as fit:
            # Reuse the frozen synthetic population fixture; its run now executes C3.
            parent_tests.FreshnessInteractionOffsetTests().test_complete_synthetic_run_has_exact87_predictions_and_hash_bound_artifacts()
            self.assertEqual(fit.call_count, 4)

    @classmethod
    def _parent_fixture(cls, root):
        items, controls, frozen = [], {}, {"predictions": []}
        for index in range(87):
            key = (f"event-{index}", f"market-{index}", (10000 + index) * 1000)
            item = {"fold": "1", "game_id": f"game-{index}", "game_date": "2025-01-01", "game_week": "1",
                "event_id": key[0], "market_id": key[1], "cutoff_ms": str(key[2]),
                "outcome_available_ms": str(key[2] + 1), "outcome": "1", "raw_market_probability": ".5",
                "frozen_v0_ordinary_market_only_probability": ".51",
                "frozen_v0_market_plus_state_parent_probability": ".49",
                "candidate_feature": str(index / 100), "candidate_probability": ".501"}
            items.append(item)
            controls[key] = {"fold": 1, "game_id": item["game_id"], "game_date": item["game_date"],
                "game_week": "1", "outcome": 1, candidate.ARM_RAW: .5,
                candidate.ARM_ORDINARY: .51, candidate.ARM_PARENT: .49}
            frozen["predictions"].append({"event_id": key[0], "market_id": key[1], "cutoff_ms": str(key[2]),
                "outcome_available_ms": str(key[2] + 1)})
        return cls._write_parent(root, items), controls, frozen, items

    @staticmethod
    def _write_parent(root, items):
        path = root / "predictions.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(items[0]))
            writer.writeheader()
            writer.writerows(items)
        candidate.common.base._atomic_json(root / "scorecard.json", {"synthetic": True})
        manifest = {"complete": True, "task_id": candidate.common.TASK_ID, "model_fits": 4, "check_events": 87,
            "predictions_sha256": candidate.common._sha256(path),
            "scorecard_sha256": candidate.common._sha256(root / "scorecard.json")}
        candidate.common.base._atomic_json(root / "manifest.json", manifest)
        return {"research_parent": {"predictions_path": str(path), "predictions_sha256": manifest["predictions_sha256"],
            "scorecard_sha256": manifest["scorecard_sha256"], "manifest_sha256": candidate.common._sha256(root / "manifest.json")}}


if __name__ == "__main__":
    unittest.main()
