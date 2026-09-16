from __future__ import annotations

from datetime import date
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

from bounded_historical_ingest import audit_parquet, download_file, verify_file


class Response(io.BytesIO):
    status = 200

    def __init__(self, body, length=None):
        super().__init__(body)
        self.headers = {} if length is None else {"content-length": str(length)}


class BoundedIngestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def item(self, body=b"fixture"):
        return {"path": "unified/polymarket_ticks_ms/date=2026-02-22/part-000001.parquet",
                "bytes": len(body), "lfs_sha256": hashlib.sha256(body).hexdigest()}

    def test_download_is_verified_before_final_name(self):
        item = self.item()
        target = self.root / "raw.parquet"
        with patch("bounded_historical_ingest.urlopen", return_value=Response(b"fixture", 7)):
            self.assertEqual(download_file(item, target), 7)
        verify_file(target, item)
        self.assertFalse(target.with_name(target.name + ".partial").exists())

    def test_wrong_hash_stays_partial(self):
        target = self.root / "raw.parquet"
        with patch("bounded_historical_ingest.urlopen", return_value=Response(b"fixturX")):
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                download_file(self.item(), target)
        self.assertFalse(target.exists())
        with self.assertRaisesRegex(ValueError, "partial transfer"):
            download_file(self.item(), target)

    def test_oversize_aborts(self):
        with patch("bounded_historical_ingest.urlopen", return_value=Response(b"fixture extra")):
            with self.assertRaisesRegex(ValueError, "exceeds"):
                download_file(self.item(), self.root / "raw.parquet")

    def test_short_file_aborts(self):
        with patch("bounded_historical_ingest.urlopen", return_value=Response(b"fix")):
            with self.assertRaisesRegex(ValueError, "size/hash mismatch"):
                download_file(self.item(), self.root / "raw.parquet")

    def make_parquet(self, *, asset="token1", crossed=False, source=(1000, 2000)):
        rows = [
            {"id": i, "source_ts_ms": source[i], "ingest_ts_ms": [2200, 2100][i],
             "market_slug": "market1", "asset_id": asset, "event_type": "price_change",
             "price": .4, "best_bid": .5 if crossed else .39, "best_ask": .41,
             "size": 1., "date": date(2026, 2, 22)} for i in range(2)]
        path = self.root / "source.parquet"
        pq.write_table(pa.Table.from_pylist(rows), path)
        item = self.item(path.read_bytes())
        return path, item

    def test_qa_reports_limitations_not_clean_training_claim(self):
        path, item = self.make_parquet()
        report = audit_parquet(path, item, {"market1": {"token1", "token2"}})
        self.assertEqual(report["rows"], 2)
        self.assertEqual(report["arrival_order_reversals"], 1)
        self.assertTrue(report["initial_streaming_qa_pass"])
        self.assertFalse(report["training_admitted"])
        self.assertIn("not_yet", report["global_id_uniqueness"])

    def test_token_must_belong_to_actual_market_not_any_market(self):
        path, item = self.make_parquet(asset="token3")
        with self.assertRaisesRegex(ValueError, "its row's market"):
            audit_parquet(path, item, {"market1": {"token1"}, "market2": {"token3"}})

    def test_crossed_quote_rejected_without_modifying_raw(self):
        path, item = self.make_parquet(crossed=True)
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "crossed"):
            audit_parquet(path, item, {"market1": {"token1"}})
        self.assertEqual(path.read_bytes(), before)

    def test_negative_latency_rejected(self):
        path, item = self.make_parquet(source=(3000, 4000))
        with self.assertRaisesRegex(ValueError, "negative ingest"):
            audit_parquet(path, item, {"market1": {"token1"}})

    def test_crossed_quote_raw_qa_flags_without_approval_or_mutation(self):
        path, item = self.make_parquet(crossed=True)
        before = path.read_bytes()
        result = audit_parquet(path, item, {"market1": {"token1"}},
                               quote_policy="preserve_and_flag_no_training_admission")
        self.assertEqual(result["crossed_quote_rows"], 2)
        self.assertTrue(result["quarantine_required"])
        self.assertFalse(result["training_admitted"])
        self.assertFalse(result["initial_streaming_qa_pass"])
        self.assertEqual(len(result["crossed_quote_examples"]), 2)
        self.assertEqual(before, path.read_bytes())

    def test_invalid_quote_policy_does_not_silently_relax_checks(self):
        path, item = self.make_parquet(crossed=True)
        with self.assertRaisesRegex(ValueError, "quote policy"):
            audit_parquet(path, item, {"market1": {"token1"}}, quote_policy="ignore")

    def test_flagging_preserves_bad_identity_and_never_admits_training(self):
        path, item = self.make_parquet(asset="token3")
        before = path.read_bytes()
        report = audit_parquet(path, item, {"market1": {"token1"}},
                               identity_policy="preserve_and_flag_no_training_admission")
        self.assertEqual(report["identity_mismatch_rows"], 2)
        self.assertTrue(report["quarantine_required"])
        self.assertFalse(report["initial_streaming_qa_pass"])
        self.assertFalse(report["training_admitted"])
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
