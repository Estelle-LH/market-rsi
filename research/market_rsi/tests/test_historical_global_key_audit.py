from pathlib import Path
import tempfile
import unittest

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from historical_global_key_audit import audit_stream, shard_numbers, summarize_shard
from market_rsi import file_hash


class GlobalSourceKeyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def file(self, values, day, stream="polymarket_ticks_ms", key="id"):
        rel = f"unified/{stream}/date={day}/part-000001.parquet"
        path = self.root / "raw" / rel
        path.parent.mkdir(parents=True)
        pq.write_table(pa.table({key: pa.array(values, type=pa.int64())}), path)
        return {"path": rel, "bytes": path.stat().st_size, "lfs_sha256": file_hash(path)}

    def test_duplicates_across_files_and_batches_are_exact(self):
        items = [self.file([1, 2, 3, 3], "2026-02-12"), self.file([3, 4, 4, 5], "2026-02-13")]
        result = audit_stream(self.root, items, self.root / "audit", shards=4, batch_rows=1)
        self.assertEqual(result["rows"], 8)
        self.assertEqual(result["unique_keys"], 5)
        self.assertEqual(result["excess_occurrences"], 3)
        self.assertEqual(result["repeated_distinct_keys"], 2)
        self.assertEqual({x['source_key']: x['occurrences'] for x in result['examples']}, {3:3, 4:2})
        self.assertFalse(result["identical_observation_dedup_proven"])
        self.assertFalse(result["training_admitted"])
        for item in items:
            self.assertEqual(file_hash(self.root / "raw" / item["path"]), item["lfs_sha256"])

    def test_identical_keys_always_share_shard(self):
        values = np.array([0, -1, 1, np.iinfo(np.int64).max, -1, 0], dtype=np.int64)
        shards = shard_numbers(values, 128)
        self.assertEqual(shards[0], shards[-1])
        self.assertEqual(shards[1], shards[4])
        self.assertTrue(np.all((shards >= 0) & (shards < 128)))

    def test_bad_shard_count_rejected(self):
        with self.assertRaisesRegex(ValueError, "power-of-two"):
            shard_numbers(np.array([1]), 3)

    def test_oversized_shard_rejected_without_unbounded_sort(self):
        item = self.file([7] * 5, "2026-02-12")
        with self.assertRaisesRegex(ValueError, "RAM bound"):
            audit_stream(self.root, [item], self.root / "audit", shards=2,
                         max_shard_rows=4, batch_rows=3)

    def test_empty_shard_valid(self):
        p = self.root / "empty.i64"; p.touch()
        result = summarize_shard(p, 0)
        self.assertEqual(result["unique_keys"], 0)
        self.assertEqual(result["repeated_distinct_keys"], 0)

    def test_wrong_shard_size_fails(self):
        p = self.root / "empty.i64"; p.touch()
        with self.assertRaisesRegex(ValueError, "size/count"):
            summarize_shard(p, 1)

    def test_null_keys_not_filled(self):
        item = self.file([1, None], "2026-02-12")
        with self.assertRaisesRegex(ValueError, "null source key"):
            audit_stream(self.root, [item], self.root / "audit", shards=2)

    def test_candles_are_scoped_by_interval(self):
        item = self.file([1000, 1000, 2000], "2026-02-12", "binance_candles_1s", "candle_start")
        result = audit_stream(self.root, [item], self.root / "audit", shards=2)
        self.assertEqual(result["key"], "candle_start")
        self.assertEqual(result["excess_occurrences"], 1)

    def test_mixed_streams_not_compared_as_one_id_space(self):
        items = [self.file([1], "2026-02-12"),
                 self.file([1], "2026-02-12", "binance_ticks_ms")]
        with self.assertRaisesRegex(ValueError, "one supported"):
            audit_stream(self.root, items, self.root / "audit")

    def test_existing_audit_not_overwritten(self):
        item = self.file([1], "2026-02-12")
        out = self.root / "audit"; out.mkdir()
        with self.assertRaises(FileExistsError):
            audit_stream(self.root, [item], out)


if __name__ == "__main__":
    unittest.main()
