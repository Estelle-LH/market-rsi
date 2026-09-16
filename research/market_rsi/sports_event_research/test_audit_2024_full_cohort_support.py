import csv
from datetime import datetime
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sports_event_research import audit_2024_full_cohort_support as audit


class FullCohortSupportTests(unittest.TestCase):
    def test_horizon_and_stale_boundary(self):
        self.assertEqual(audit.reason(1000, [], 60), "no_prior_trade")
        self.assertEqual(audit.reason(1000, [699, 1030], 60), "stale_prior_trade")
        self.assertEqual(audit.reason(1000, [700, 1061], 60), "no_new_trade")
        self.assertEqual(audit.reason(1000, [700, 1061], 300), "covered")
        self.assertEqual(audit.reason(1000, [1000], 60), "no_new_trade")

    def test_full_audit_preserves_quiet_game_in_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selections = [{"nflverse_game_id": "g1", "event_start_utc": "2024-09-01T00:00:00Z",
                           "clob_token_ids": ["a1", "b1"]},
                          {"nflverse_game_id": "g2", "event_start_utc": "2024-09-02T00:00:00Z",
                           "clob_token_ids": ["a2", "b2"]}]
            plan_path = root / "cohort_plan.json"
            audit.write_json(plan_path, {"schema": "polymarket_2024_full_train_source_plan_v1",
                "planned_games": 2, "batch_count": 1, "batch_size": 24,
                "mapping_sha256": "mapping", "selections": selections, "train_admitted": False})
            plan_hash = audit.sha(plan_path)
            pbp = root / "pbp.csv.gz"
            with gzip.open(pbp, "wt", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["game_id", "play_id", "play_type", "time_of_day"])
                writer.writeheader()
                writer.writerow({"game_id": "g1", "play_id": "p1", "play_type": "pass",
                                 "time_of_day": "2024-09-01T00:16:40Z"})
                writer.writerow({"game_id": "g2", "play_id": "p2", "play_type": "pass",
                                 "time_of_day": "2024-09-02T00:16:40Z"})
            batch = root / "batch"
            batch.mkdir()
            lock_path = batch / "pre_fetch_lock.json"
            audit.write_json(lock_path, {"schema": "polymarket_2024_full_train_source_batch_lock_v1",
                "cohort_plan_sha256": plan_hash,
                "planned_games": ["g1", "g2"]})
            receipts = []
            for index, selection in enumerate(selections):
                game_root = batch / selection["nflverse_game_id"]
                game_root.mkdir()
                selection_path = game_root / "selection.json"
                audit.write_json(selection_path, selection)
                play = int(datetime.fromisoformat(selection["event_start_utc"].replace("Z", "+00:00")).timestamp()) + 1000
                trades = [play - 50, play + (30 if index == 0 else 120)]
                safe_path = game_root / "trade_window.csv"
                with safe_path.open("w", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=["asset", "timestamp"])
                    writer.writeheader()
                    for value in trades:
                        writer.writerow({"asset": selection["clob_token_ids"][0], "timestamp": value})
                manifest_path = game_root / "manifest.json"
                audit.write_json(manifest_path, {"schema": "polymarket_2024_nfl_trade_canary_manifest_v1",
                    "selection_sha256": audit.sha(selection_path),
                    "mapping_sha256": "mapping", "safe_trade_window_sha256": audit.sha(safe_path),
                    "train_admitted": False})
                receipts.append({"game_id": selection["nflverse_game_id"],
                                 "manifest_sha256": audit.sha(manifest_path), "trade_rows": 2})
            audit.write_json(batch / "manifest.json", {
                "schema": "polymarket_2024_full_train_source_batch_manifest_v1",
                "batch_index": 0, "complete": True,
                "planned_games": 2, "completed_games": 2, "automatic_retries": 0,
                "train_admitted": False, "route_dev_opened": False,
                "sealed_final_opened": False,
                "cohort_plan_sha256": plan_hash,
                "pre_fetch_lock_sha256": audit.sha(lock_path), "receipts": receipts})
            with (patch.object(audit, "EXPECTED_NFLVERSE", audit.sha(pbp)),
                  patch.object(audit, "EXPECTED_COHORT_PLAN", plan_hash),
                  patch.object(audit, "GAMES", 2), patch.object(audit, "BATCHES", 1),
                  patch.object(audit, "published_release", return_value={"tag": "synthetic"})):
                result = audit.audit(pbp, plan_path, [batch], root / "release.json", root / "output")
            self.assertEqual(result["games"], 2)
            self.assertEqual(result["timed_typed_plays"], 2)
            self.assertEqual(result["reasons_by_horizon"]["60"]["covered"], 1)
            self.assertEqual(result["reasons_by_horizon"]["60"]["no_new_trade"], 1)
            self.assertEqual(result["reasons_by_horizon"]["300"]["covered"], 2)
            self.assertFalse(result["train_admitted"])


if __name__ == "__main__":
    unittest.main()
