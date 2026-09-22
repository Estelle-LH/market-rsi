import csv
import json
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from supervisor_harness.build_p0_gate0_inventory import make_inventory
from supervisor_harness.reserve_prospective_final_candidate import run as reserve


class P0AdmissionInventoryTests(unittest.TestCase):
    def test_exposure_unknown_is_never_fresh(self):
        mapping = [{"game_id": f"game-{i:03}", "game_date": f"2025-{1 + i // 30:02}-01"}
                   for i in range(285)]
        audit = {"role_game_counts": {"market_train": 195, "route_dev": 50, "sealed_final": 40},
                 "role_distinct_date_counts": {"market_train": 7, "route_dev": 3,
                                               "sealed_final": 2}}
        ledger = make_inventory(mapping, audit, proven_open_game="game-000")
        self.assertEqual(ledger["per_game_counts"],
                         {"opened": 1, "verified_not_opened": 0, "unknown": 284})
        self.assertFalse(ledger["formal_final_admitted"])

    def test_future_selection_is_schedule_only_and_fresh(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "schedule.csv", root / "candidate.json"
            with source.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["game_id", "season", "game_type", "gameday"])
                writer.writeheader()
                for i in range(22):
                    writer.writerow({"game_id": f"future-{i}", "season": "2026",
                                     "game_type": "REG",
                                     "gameday": (date(2026, 9, 20) + timedelta(days=i)).isoformat()})
            receipt = reserve(source, output)
            candidate = json.loads(output.read_text())
            self.assertEqual(receipt["date_count"], 20)
            self.assertEqual(receipt["game_count"], 20)
            self.assertFalse(candidate["formal_final_admitted"])
            self.assertFalse(candidate["labels_read"])
            with self.assertRaises(FileExistsError):
                reserve(source, output)


if __name__ == "__main__":
    unittest.main()
