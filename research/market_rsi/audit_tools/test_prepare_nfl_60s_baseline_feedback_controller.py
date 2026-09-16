"""Boundary tests for the aggregate-only 60-second controller handoff."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from audit_tools.prepare_nfl_60s_baseline_feedback_controller import (
    build_findings, load_baseline, load_data_screen,
)
from market_rsi import file_hash


def fixture():
    lock = {
        "schema": "nfl_deterministic_60s_baseline_lock_v1",
        "target": "home_change_60s", "train_population": {"games": 163, "eligible_rows": 23709},
        "folds": [{}, {}, {}], "route_dev_opened": False,
        "sealed_final_opened": False, "provider_cost_usd": "0",
    }
    metrics = {"equal_game_candidate_mse": .0015, "equal_game_calibration_slope": 1.0,
               "positive_game_fraction": .8}
    result = {
        "schema": "nfl_deterministic_60s_baseline_result_v1",
        "methods": {name: dict(metrics) for name in
                    ("ridge", "random_forest", "hist_gradient_boosting")},
        "train_only_selected_method": "hist_gradient_boosting",
        "relative_mse_improvement_vs_ridge": .18,
        "folds": [{"method_mse": {name: .0015 for name in
                                  ("ridge", "random_forest", "hist_gradient_boosting")}}] * 3,
        "formal_claim": False, "route_dev_opened": False,
        "sealed_final_opened": False, "provider_cost_usd": "0",
    }
    return lock, result


class Nfl60sBaselineFeedbackTest(unittest.TestCase):
    def test_load_binds_three_receipts_and_rejects_dev(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            lock, result = fixture()
            (root / "pre_score_lock.json").write_text(json.dumps(lock))
            lock_hash = file_hash(root / "pre_score_lock.json")
            result["pre_score_lock_sha256"] = lock_hash
            (root / "result.json").write_text(json.dumps(result))
            result_hash = file_hash(root / "result.json")
            manifest = {"schema": "nfl_deterministic_60s_baseline_manifest_v1",
                        "complete": True, "pre_score_lock_sha256": lock_hash,
                        "result_sha256": result_hash, "route_dev_opened": False,
                        "sealed_final_opened": False}
            (root / "manifest.json").write_text(json.dumps(manifest))
            expected = {name: file_hash(root / name) for name in
                        ("pre_score_lock.json", "result.json", "manifest.json")}
            loaded = load_baseline(root, expected)
            self.assertEqual(len(loaded["receipts"]), 2)
            self.assertNotIn("pre_score_lock.json", [Path(r["path"]).name for r in loaded["receipts"]])
            result["route_dev_opened"] = True
            (root / "result.json").write_text(json.dumps(result))
            expected["result.json"] = file_hash(root / "result.json")
            manifest["result_sha256"] = expected["result.json"]
            (root / "manifest.json").write_text(json.dumps(manifest))
            expected["manifest.json"] = file_hash(root / "manifest.json")
            with self.assertRaisesRegex(ValueError, "Dev or Final"):
                load_baseline(root, expected)

    def test_data_screen_rejects_unadmitted_or_changed_counts(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            value = {"schema": "nfl_2024_pbp_trade_timing_support_v1",
                     "train_admitted": False, "scientific_score": False,
                     "historical_event_clock_only": True,
                     "totals": {"covered_60s": 1400, "timed_typed_play_rows": 2027}}
            path.write_text(json.dumps(value))
            self.assertEqual(load_data_screen(path, file_hash(path)), value)
            value["train_admitted"] = True
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "scope or coverage"):
                load_data_screen(path, file_hash(path))

    def test_findings_are_aggregate_and_budget_jobs_hidden(self):
        _, result = fixture()
        screen = {"totals": {"covered_60s": 1400, "timed_typed_play_rows": 2027}}
        findings = build_findings({"result": result},
                                  {"jobs": {"secret": {}}, "available_usd": "10"}, screen)
        self.assertEqual([item["id"] for item in findings],
                         ["fixed-60s-baseline-screen", "data-and-time-blockers",
                          "next-research-decision"])
        self.assertEqual(findings[0]["selected_provisional_fixed_baseline"],
                         "hist_gradient_boosting")
        self.assertNotIn("jobs", findings[-1]["budget"])
        self.assertIn("cannot fit", findings[-1]["instruction"])


if __name__ == "__main__":
    unittest.main()
