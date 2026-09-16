from pathlib import Path
import tempfile
import unittest
import pyarrow as pa
import pyarrow.parquet as pq

from inspect_historical_key_collisions import inspect_stream
from market_rsi import file_hash


class KeyCollisionInspectionTests(unittest.TestCase):
    def test_same_id_different_events_preserved_with_locations(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            items = []
            for day, time in [("2026-02-12", 1000), ("2026-02-13", 2000)]:
                rel = f"unified/polymarket_ticks_ms/date={day}/part-000001.parquet"
                path = root / "raw" / rel; path.parent.mkdir(parents=True)
                pq.write_table(pa.table({"id": [7], "source_ts_ms": [time], "price": [0.5]}), path)
                items.append({"path": rel, "bytes": path.stat().st_size, "lfs_sha256": file_hash(path)})
            report = inspect_stream(root, items, stream="polymarket_ticks_ms",
                                    examples=[{"source_key": 7, "occurrences": 2}])
            self.assertEqual(report["keys_with_multiple_event_payloads"], 1)
            self.assertEqual(len(report["examples"][0]["hits"]), 2)
            self.assertEqual(report["examples"][0]["hits"][0]["raw_row_ordinal"], 0)
            self.assertFalse(report["automatic_deduplication"])
            for item in items:
                self.assertEqual(file_hash(root / "raw" / item["path"]), item["lfs_sha256"])

    def test_unbounded_examples_rejected(self):
        with self.assertRaisesRegex(ValueError, "bound"):
            inspect_stream(Path("unused"), [], stream="polymarket_ticks_ms",
                           examples=[{"source_key": 1, "occurrences": 9999}])


if __name__ == "__main__":
    unittest.main()
