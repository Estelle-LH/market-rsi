import json
import tempfile
import unittest
from pathlib import Path

from block_stability_audit import audit


class BlockStabilityAuditTests(unittest.TestCase):
    def test_builds_fixed_blocks_without_opening_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "run"
            root.mkdir()
            for date_index, date in enumerate(("2026-09-01", "2026-09-02",
                                                "2026-09-03", "2026-09-04")):
                for hour in range(5):
                    session = f"{date}T{hour:02d}"
                    data = root / "data" / session
                    data.mkdir(parents=True)
                    (data / "header.json").write_text(json.dumps({
                        "shape": [100, 6],
                        "market_hashes": [f"m-{date_index}", f"h-{hour}"],
                    }))
                    scores = {}
                    for arm, mse in {"baseline": 1.0, "fresh": 0.9,
                                     "archive": 0.8, "compact": 1.1}.items():
                        scores[arm] = {
                            "date": session, "n": 100, "zero_labels": 80,
                            "cache_sha256": "a" * 64, "candidate_mse": mse,
                            "calibration_slope": 1.0, "pearson_ic": 0.1,
                        }
                    (root / f"final-{session}.json").write_text(json.dumps(scores))
            output = Path(temp) / "audit"
            result = audit(root, output)
            self.assertEqual(result["summary"]["one_hour"]["blocks"], 20)
            self.assertEqual(result["summary"]["four_hour"]["blocks"], 4)
            self.assertEqual(result["summary"]["same_date_five_hour"]["blocks"], 4)
            self.assertFalse(result["full_utc_day_available"])
            self.assertEqual(result["summary"]["same_date_five_hour"]
                             ["archive_wins_vs_fresh"], 4)
            self.assertTrue((output / "complete.json").exists())


if __name__ == "__main__":
    unittest.main()
