"""Frozen full-cohort aggregate controller handoff boundary tests."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from audit_tools.prepare_nfl_60s_baseline_feedback_controller import load_baseline
from audit_tools.prepare_nfl_full_cohort_feedback_controller import (
    build_findings, load_support,
)
from data_scientist_harness.release import source_files
from market_rsi import file_hash


def support_fixture():
    reasons = {
        "60": {"covered": 32384, "no_prior_trade": 0,
               "stale_prior_trade": 2583, "no_new_trade": 12908},
        "300": {"covered": 43506, "no_prior_trade": 0,
                "stale_prior_trade": 2583, "no_new_trade": 1786},
    }
    lock = {"schema": "nfl_2024_full_cohort_support_lock_v1",
            "mapped_games": 284, "model_fits": 0, "provider_cost_usd": "0",
            "denominator": "all timed, typed PBP plays in all 284 mapped games; quiet games retained",
            "train_admitted": False, "route_dev_opened": False,
            "sealed_final_opened": False}
    result = {"schema": "nfl_2024_full_cohort_support_result_v1",
              "games": 284, "games_with_trades": 284, "trade_rows": 407225,
              "timed_typed_plays": 47875, "model_fits": 0,
              "provider_cost_usd": "0", "reasons_by_horizon": reasons,
              "coverage_by_horizon": {"60": 32384 / 47875, "300": 43506 / 47875},
              "median_game_coverage_by_horizon": {"60": .72, "300": .98},
              "interpretation_boundary": "historical event-clock/trade-print support only; not provider publish/local receive, model score, Train admission or tradable edge",
              "train_admitted": False, "route_dev_opened": False,
              "sealed_final_opened": False}
    return lock, result


class FullCohortControllerHandoffTest(unittest.TestCase):
    def test_support_receipts_bound_and_unadmitted(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock, result = support_fixture()
            (root / "pre_analysis_lock.json").write_text(json.dumps(lock))
            lock_sha = file_hash(root / "pre_analysis_lock.json")
            result["pre_analysis_lock_sha256"] = lock_sha
            (root / "result.json").write_text(json.dumps(result))
            result_sha = file_hash(root / "result.json")
            manifest = {"schema": "nfl_2024_full_cohort_support_manifest_v1",
                        "complete": True, "model_fits": 0,
                        "provider_cost_usd": "0", "train_admitted": False,
                        "route_dev_opened": False, "sealed_final_opened": False,
                        "pre_analysis_lock_sha256": lock_sha,
                        "result_sha256": result_sha}
            (root / "manifest.json").write_text(json.dumps(manifest))
            expected = {name: file_hash(root / name) for name in
                        ("pre_analysis_lock.json", "result.json", "manifest.json")}
            got = load_support(root, expected)
            self.assertEqual(len(got["receipts"]), 2)
            result["train_admitted"] = True
            (root / "result.json").write_text(json.dumps(result))
            expected["result.json"] = file_hash(root / "result.json")
            manifest["result_sha256"] = expected["result.json"]
            (root / "manifest.json").write_text(json.dumps(manifest))
            expected["manifest.json"] = file_hash(root / "manifest.json")
            with self.assertRaisesRegex(ValueError, "unadmitted"):
                load_support(root, expected)

    def test_findings_are_aggregate_and_do_not_select_target(self):
        baseline = load_baseline()
        _, result = support_fixture()
        findings = build_findings(baseline, {"result": result},
                                  {"jobs": {"private": {}}, "available_usd": "9"})
        self.assertEqual(len(findings), 3)
        self.assertNotIn("jobs", findings[-1]["budget"])
        self.assertEqual(findings[1]["historical_target_support"]["60"]["count"]["covered"], 32384)
        self.assertEqual(findings[1]["historical_target_support"]["300"]["count"]["covered"], 43506)
        self.assertIn("choose one", findings[-1]["instruction"])
        self.assertIn("not admitted", findings[-1]["instruction"])
        self.assertNotIn("game_id", json.dumps(findings))
        self.assertNotIn("instance_id", json.dumps(findings))

    def test_preparer_is_in_release_source_set(self):
        names = {str(path) for path in source_files()}
        self.assertTrue(any(name.endswith("prepare_nfl_full_cohort_feedback_controller.py")
                            for name in names))
        self.assertTrue(any(name.endswith("prepare_nfl_60s_baseline_feedback_controller.py")
                            for name in names))


if __name__ == "__main__":
    unittest.main()
