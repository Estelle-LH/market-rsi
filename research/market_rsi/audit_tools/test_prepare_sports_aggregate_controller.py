from pathlib import Path
import json
import tempfile
import unittest

from audit_tools.prepare_sports_aggregate_controller import (
    build_findings, load_frozen_run,
)
from market_rsi import file_hash, fresh_json


def method(improvement, folds):
    return {
        "relative_mse_improvement": improvement,
        "fold_relative_mse_improvements": folds,
        "equal_game_calibration_slope": 1.0,
        "positive_game_fraction": 0.75,
    }


def target(improvement=0.06):
    return {
        "profile": {"full_population_coverage": 0.8, "exact_zero_fraction": 0.1},
        "methods": {
            "ridge": method(improvement, [0.04, 0.05, 0.06]),
            "random_forest": method(improvement + 0.01, [0.05, 0.06, 0.07]),
        },
    }


def grid_target(improvement=0.06):
    value = target(improvement)
    folds = {name: method_values.pop("fold_relative_mse_improvements")
             for name, method_values in value["methods"].items()}
    value["fold_relative_mse_improvements"] = folds
    return value


class SportsAggregatePreparationTests(unittest.TestCase):
    def test_frozen_run_requires_cross_bound_train_only_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock = {"schema": "lock", "route_dev_opened": False,
                    "sealed_final_opened": False, "provider_cost_usd": "0",
                    "discovery_only": True}
            fresh_json(root / "pre_score_lock.json", lock)
            lock_sha = file_hash(root / "pre_score_lock.json")
            result = {"schema": "result", "route_dev_opened": False,
                      "sealed_final_opened": False, "provider_cost_usd": "0",
                      "pre_score_lock_sha256": lock_sha}
            (root / "result.json").write_text(json.dumps(result, sort_keys=True))
            result_sha = file_hash(root / "result.json")
            fresh_json(root / "manifest.json", {"schema": "manifest",
                "result_sha256": result_sha, "pre_score_lock_sha256": lock_sha})
            spec = {"root": root, "result": result_sha,
                    "manifest": file_hash(root / "manifest.json"), "lock": lock_sha,
                    "result_schema": "result", "manifest_schema": "manifest",
                    "lock_schema": "lock"}
            loaded = load_frozen_run(spec)
            self.assertEqual(len(loaded["receipts"]), 3)
            result["route_dev_opened"] = True
            (root / "result.json").write_text(json.dumps(result, sort_keys=True))
            spec["result"] = file_hash(root / "result.json")
            with self.assertRaisesRegex(ValueError, "cross-receipts"):
                load_frozen_run(spec)

    def test_findings_keep_train_discovery_and_next_decision_separate(self):
        table = {name: grid_target() for name in (
            "elapsed_15s_delta", "elapsed_20s_delta", "elapsed_30s_delta",
            "elapsed_45s_delta", "elapsed_60s_delta", "event_5trades_delta")}
        lock = {"question": "which target", "numeric_features": ["price"],
                "categorical_features": ["play_type"], "methods": {"ridge": {}},
                "rolling_design": {"blocks": 3}}
        grid = {"lock": lock, "result": {"public_summary": table,
            "opened_train_shortlist": [{"target": "elapsed_30s_delta"}]}}
        same_table = {name: target() for name in table if name.startswith("elapsed_")}
        same = {"lock": {"question": "same rows"}, "result": {
            "public_summary": same_table,
            "rankings": {"ridge": [{"target": "elapsed_30s_delta"}]}}}
        findings = build_findings(grid, same, {"jobs": {"secret": {}}, "available_usd": "10"})
        self.assertEqual([finding["id"] for finding in findings], [
            "target-grid-result", "same-support-result", "representation-and-algorithm-gap",
            "event-time-candidate", "evaluation-boundary", "next-controller-decision"])
        self.assertNotIn("jobs", findings[-1]["budget"])
        self.assertIn("cannot train", findings[-1]["instructions"])
        self.assertIn("No Route-Dev result", findings[-2]["rules"][0])


if __name__ == "__main__":
    unittest.main()
