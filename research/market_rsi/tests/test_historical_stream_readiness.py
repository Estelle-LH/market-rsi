from datetime import date, datetime, timezone
from pathlib import Path
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

from historical_stream_readiness import audit_file, coverage, partition, DAY_MS
from market_rsi import file_hash


class HistoricalClockAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.day = date(2026, 2, 12)
        self.start = int(datetime(2026, 2, 12, tzinfo=timezone.utc).timestamp() * 1000)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, rows, stream="binance_ticks_ms"):
        path = self.root / "fixture.parquet"
        pq.write_table(pa.Table.from_pylist(rows), path)
        item = {"path": f"unified/{stream}/date=2026-02-12/part-000001.parquet",
                "lfs_sha256": file_hash(path), "bytes": path.stat().st_size}
        return path, item

    def ticks(self, receipts=(100, 200, 300)):
        return [{"source_ts_ms": self.start + v - 50, "ingest_ts_ms": self.start + v,
                 "trade_time_ms": self.start + v - 50, "date": self.day}
                for v in receipts]

    def candles(self):
        return [{"candle_start": self.start, "candle_end": self.start + 59_999,
                 "created_at": self.start + 2 * DAY_MS, "date": self.day}]

    def test_sparse_partition_never_claims_full_day(self):
        report = audit_file(*self.fixture(self.ticks()), batch_size=1)
        cov = report["coverage"]["source_ts_ms"]
        self.assertEqual(cov["occupied_bins"], 1)
        self.assertEqual(cov["possible_bins_in_partition_day"], 1440)
        self.assertFalse(cov["continuous_quote_or_full_session_coverage_proven"])
        self.assertFalse(report["training_admitted"])
        self.assertFalse(report["label_values_opened"])

    def test_batch_boundaries_include_reversals_and_ties(self):
        report = audit_file(*self.fixture(self.ticks((200, 100, 100))), batch_size=1)
        self.assertEqual(report["clock_fields"]["ingest_ts_ms"]["raw_order_reversals"], 1)
        self.assertEqual(report["clock_fields"]["ingest_ts_ms"]["adjacent_equal_timestamps"], 1)

    def test_candle_backfill_is_recorded_not_moved_to_start(self):
        path, item = self.fixture(self.candles(), "binance_candles_1m")
        before = path.read_bytes()
        report = audit_file(path, item)
        self.assertEqual(report["counts"]["receipt_lag_over_1d_rows"], 1)
        self.assertEqual(report["coverage"]["created_at"]["occupied_bins"], 0)
        self.assertEqual(report["candle_policy"], "never_use_final_ohlcv_at_candle_start")
        self.assertIn("recorded_receipt_over_one_day_late", report["flags"])
        self.assertEqual(before, path.read_bytes())

    def test_partial_candle_cannot_be_treated_as_final(self):
        rows = self.candles()
        rows[0]["created_at"] = self.start + 10
        report = audit_file(*self.fixture(rows, "binance_candles_1m"))
        self.assertEqual(report["counts"]["receipt_before_event_or_candle_close_rows"], 1)

    def test_native_candle_interval_not_one_minute_expected_density(self):
        rows = [{"candle_start": self.start + i * 3_600_000,
                 "candle_end": self.start + (i + 1) * 3_600_000 - 1,
                 "created_at": self.start + (i + 1) * 3_600_000 + 200,
                 "date": self.day} for i in range(24)]
        report = audit_file(*self.fixture(rows, "binance_candles_1h"))
        self.assertEqual(report["coverage"]["candle_start"]["occupied_fraction"], 1.)
        self.assertFalse(report["training_admitted"])

    def test_candle_duration_and_alignment_mismatch(self):
        rows = self.candles()
        rows[0]["candle_start"] += 2
        report = audit_file(*self.fixture(rows, "binance_candles_1m"))
        self.assertIn("candle_interval_mismatch", report["flags"])

    def test_epoch_seconds_and_microseconds_rejected(self):
        for transform in (lambda v: v // 1000, lambda v: v * 1000):
            rows = self.ticks()
            rows[0]["source_ts_ms"] = transform(rows[0]["source_ts_ms"])
            with self.assertRaisesRegex(ValueError, "epoch-ms"):
                audit_file(*self.fixture(rows))

    def test_null_clock_rejected(self):
        rows = self.ticks()
        rows[0]["ingest_ts_ms"] = None
        with self.assertRaisesRegex(ValueError, "null clock"):
            audit_file(*self.fixture(rows))

    def test_partition_time_mismatch_flagged(self):
        rows = self.ticks()
        rows[0]["source_ts_ms"] -= DAY_MS
        report = audit_file(*self.fixture(rows))
        self.assertIn("partition_clock_mismatch", report["flags"])

    def test_negative_receipt_latency_flagged(self):
        rows = self.ticks()
        rows[0]["ingest_ts_ms"] -= 100
        report = audit_file(*self.fixture(rows))
        self.assertIn("receipt_precedes_event_or_final_candle_close", report["flags"])

    def test_hash_mutation_fails_before_scanning(self):
        path, item = self.fixture(self.ticks())
        item["lfs_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            audit_file(path, item)

    def test_unsafe_path_rejected(self):
        for path in ("/unified/t/date=2026-02-12/f", "unified/../date=2026-02-12/f"):
            with self.assertRaises(ValueError):
                partition({"path": path})

    def test_coverage_includes_empty_edges_and_not_outside_bins(self):
        first = self.start // 60_000
        report = coverage({first - 1, first + 1, first + 2, first + 4},
                          day_start=self.start, width_ms=60_000)
        self.assertEqual(report["occupied_bins"], 3)
        self.assertEqual(report["observed_bins_outside_partition_day"], 1)
        self.assertEqual(report["longest_empty_run_ms_including_day_edges"], 1435 * 60_000)
        self.assertEqual(report["occupied_ranges_ms_half_open"],
                         [[self.start + 60_000, self.start + 180_000],
                          [self.start + 240_000, self.start + 300_000]])

    def test_trades_use_trade_and_receipt_not_binance_tick_clock(self):
        rows = [{"trade_time": self.start + 100, "received_at": self.start + 200,
                 "date": self.day}]
        report = audit_file(*self.fixture(rows, "binance_trades"))
        self.assertEqual(set(report["clock_fields"]), {"trade_time", "received_at"})
        self.assertEqual(report["recorded_receipt_minus_reference_ms"]["max"], 100)

    def test_hive_only_date_is_explicit_not_a_missing_clock(self):
        rows = [{"trade_time": self.start + 100, "received_at": self.start + 200}]
        report = audit_file(*self.fixture(rows, "binance_trades"))
        self.assertFalse(report["partition_clock_hypotheses"]["date_column_present"])
        self.assertIn("partition_date_only_in_path_not_inline", report["flags"])
        self.assertFalse(report["training_admitted"])

    def test_local_partition_does_not_get_silently_declared_utc(self):
        rows = self.ticks((DAY_MS + 100, DAY_MS + 200))
        report = audit_file(*self.fixture(rows))
        self.assertEqual(report["counts"]["event_time_outside_partition_day_rows"], 2)
        self.assertEqual(report["counts"]["event_time_outside_new_york_partition_hypothesis_rows"], 0)
        self.assertFalse(report["partition_clock_hypotheses"]["timezone_selected"])


if __name__ == "__main__":
    unittest.main()
