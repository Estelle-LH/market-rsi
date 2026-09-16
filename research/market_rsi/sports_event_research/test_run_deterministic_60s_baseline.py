"""Synthetic-only checks for the deterministic strong-baseline first step."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from sports_event_research.run_deterministic_60s_baseline import (
    METHOD_ORDER,
    fit_predict_fold,
    fold_matrices,
    preflight,
    select_train_only,
)
from sports_event_research.run_train_method_screen import NUMERIC_FEATURES


class DeterministicBaselineTest(unittest.TestCase):
    def test_all_fixed_methods_repeat_identically(self) -> None:
        rows = []
        for index in range(80):
            numeric = [float((index + column) % 7) for column in range(len(NUMERIC_FEATURES))]
            rows.append({"game": f"g{index // 4}", "numeric": numeric,
                         "categorical": ["pass" if index % 2 else "run"],
                         "target": float(index % 5) / 100})
        delta = np.asarray([float(index % 9) / 100 for index in range(80)])
        fit = np.arange(64)
        check = np.arange(64, 80)
        first = fit_predict_fold(rows, fit, check, delta)
        second = fit_predict_fold(rows, fit, check, delta)
        self.assertEqual(tuple(first), METHOD_ORDER)
        for method in METHOD_ORDER:
            np.testing.assert_array_equal(first[method], second[method])
            self.assertTrue(np.isfinite(first[method]).all())

    def test_check_block_cannot_change_fit_preprocessing(self) -> None:
        rows = [{"game": "fit", "numeric": [float(index)] * len(NUMERIC_FEATURES),
                 "categorical": ["pass"], "target": 0.1} for index in range(3)]
        rows.append({"game": "check", "numeric": [100.0] * len(NUMERIC_FEATURES),
                     "categorical": ["unknown"], "target": 0.2})
        delta = np.asarray([0.0, 0.1, 0.2, 10.0])
        before, _ = fold_matrices(rows, np.arange(3), np.asarray([3]), delta)
        rows[3]["numeric"] = [100000.0] * len(NUMERIC_FEATURES)
        delta[3] = 100000.0
        after, _ = fold_matrices(rows, np.arange(3), np.asarray([3]), delta)
        np.testing.assert_array_equal(before, after)

    def test_fixed_selection_rule_and_missing_method(self) -> None:
        summary = {name: {"equal_game_candidate_mse": value} for name, value in (
            ("ridge", .02), ("random_forest", .015), ("hist_gradient_boosting", .01))}
        self.assertEqual(select_train_only(summary), "hist_gradient_boosting")
        summary.pop("ridge")
        with self.assertRaisesRegex(ValueError, "all preregistered methods"):
            select_train_only(summary)

    def test_preflight_rejects_opened_or_non_train_manifest(self) -> None:
        with TemporaryDirectory() as location:
            path = Path(location) / "manifest.json"
            value = {"games": 163, "split_role": "market_train",
                     "route_dev_opened": False, "sealed_final_opened": False}
            path.write_text(json.dumps(value))
            self.assertEqual(preflight(path), value)
            value["sealed_final_opened"] = True
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "opened Train"):
                preflight(path)


if __name__ == "__main__":
    unittest.main()
