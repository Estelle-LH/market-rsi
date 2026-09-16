import csv
from pathlib import Path
import tempfile
import unittest

from sports_event_research.run_feature_availability_audit import (
    NANOSECONDS,
    collect_time_rows,
)


class FeatureAvailabilityAuditAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.panel = Path(self.tmp.name) / "panel.csv"
        with self.panel.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=(
                "play_id", "play_timestamp", "home_price_60s_timestamp", "home_change_60s"))
            writer.writeheader()
            writer.writerow({"play_id": "p1", "play_timestamp": 100,
                             "home_price_60s_timestamp": 159, "home_change_60s": 0.1})
            writer.writerow({"play_id": "p2", "play_timestamp": 200,
                             "home_price_60s_timestamp": "", "home_change_60s": ""})

    def tearDown(self):
        self.tmp.cleanup()

    def test_collects_exact_eligible_population_and_60s_label_boundary(self):
        rows = [{"game": "g1", "play_id": "p1"}]
        result = collect_time_rows(rows, [{"game": "g1", "panel_path": str(self.panel)}])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["label_start_ns"], 159 * NANOSECONDS)
        self.assertEqual(result[0]["label_end_ns"] - result[0]["decision_ns"],
                         60 * NANOSECONDS)

    def test_population_mismatch_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "population"):
            collect_time_rows([{"game": "g1", "play_id": "other"}],
                              [{"game": "g1", "panel_path": str(self.panel)}])


if __name__ == "__main__":
    unittest.main()
