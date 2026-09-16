import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from canary_sqlite_fixture import build_fixture, run
from canary_sqlite_observations import inspect_archive
import canary_sqlite_observations as reader


class SQLiteActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / "fixture.sqlite"
        self.digest, self.size = build_fixture(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def read(self, path=None, **kwargs):
        options = dict(expected_sha256=self.digest, expected_bytes=self.size,
                       start_ms=0, end_ms=180_000, recorder_scope="synthetic-one-recorder")
        options.update(kwargs)
        return inspect_archive(path or self.path, **options)

    def change(self, query):
        self.path.chmod(0o644)
        with sqlite3.connect(self.path) as connection:
            connection.execute(query)
        self.path.chmod(0o444)
        self.digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.size = self.path.stat().st_size

    def test_three_tables_unchanged_no_sidecars_or_payload_parsing(self):
        before = sorted(self.root.iterdir())
        r = self.read()
        self.assertTrue(r["source_unchanged"])
        self.assertTrue(r["all_window_queries_complete"])
        self.assertEqual(r["observations"]["minutes_with_heartbeat_but_no_pm_message"], 1)
        self.assertEqual(r["observations"]["minutes_overlapping_any_recorded_gap"], 1)
        self.assertEqual(r["observations"]["recorded_gap_groups"][0]["source"], "cex")
        self.assertEqual(len(r["observations"]["pm_identity_groups"]), 2)
        self.assertFalse(r["raw_payloads_read"])
        self.assertFalse(r["clean_session_admitted"])
        self.assertEqual(sorted(self.root.iterdir()), before)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), self.digest)

    def test_partial_prefix_never_called_complete(self):
        r = self.read(max_rows_per_table=1)
        self.assertFalse(r["all_window_queries_complete"])
        self.assertFalse(r["queries"]["pm_events"]["window_query_complete"])
        self.assertEqual(r["queries"]["pm_events"]["rows_counted"], 1)
        self.assertEqual(r["queries"]["pm_events"]["rows_read_including_limit_probe"], 2)
        self.assertFalse(r["fresh_validation_admitted"])

    def test_exact_bound_not_falsely_truncated(self):
        self.assertTrue(self.read(max_rows_per_table=3)["all_window_queries_complete"])

    def test_wrong_hash_or_size(self):
        for kwargs in ({"expected_sha256": "0" * 64}, {"expected_bytes": self.size + 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.read(**kwargs)

    def test_archive_mutation_during_inspection_discards_result(self):
        original = reader._schema

        def change_after_schema(connection):
            result = original(connection)
            self.path.chmod(0o644)
            with self.path.open("ab") as stream:
                stream.write(b"synthetic mutation")
            self.path.chmod(0o444)
            return result

        with patch("canary_sqlite_observations._schema", side_effect=change_after_schema):
            with self.assertRaisesRegex(ValueError, "changed during"):
                self.read()

    def test_writable_file_rejected(self):
        self.path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "read-only"):
            self.read()

    def test_symlink_rejected(self):
        link = self.root / "link.sqlite"
        link.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, "canonical"):
            self.read(path=link)

    def test_sidecars_rejected(self):
        for suffix in ("-wal", "-shm", "-journal"):
            side = Path(str(self.path) + suffix)
            side.touch()
            with self.subTest(suffix=suffix), self.assertRaisesRegex(ValueError, "sidecar"):
                self.read()
            side.unlink()

    def test_missing_table_rejected(self):
        self.change("DROP TABLE heartbeats")
        with self.assertRaisesRegex(ValueError, "ordinary table"):
            self.read()

    def test_view_substitution_rejected(self):
        self.change("ALTER TABLE heartbeats RENAME TO old_hb")
        self.change("CREATE VIEW heartbeats AS SELECT * FROM old_hb")
        with self.assertRaisesRegex(ValueError, "ordinary table"):
            self.read()

    def test_column_rename_rejected(self):
        self.change("ALTER TABLE heartbeats RENAME COLUMN emitted_at_ms TO time_seconds")
        with self.assertRaisesRegex(ValueError, "missing/wrong/generated"):
            self.read()

    def test_empty_window_not_proof_of_clean_data(self):
        r = self.read(start_ms=600_000, end_ms=660_000)
        self.assertTrue(r["all_window_queries_complete"])
        self.assertEqual(r["observations"]["minutes_with_neither_message_nor_heartbeat"], 1)
        self.assertFalse(r["clean_session_admitted"])

    def test_invalid_limits_refused_before_open(self):
        for kwargs in ({"max_rows_per_table": True}, {"max_rows_per_table": 100001},
                       {"max_seconds": float("nan")}, {"start_ms": 1}, {"recorder_scope": ""}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.read(**kwargs)

    def test_expired_deadline_is_not_a_result(self):
        with patch("canary_sqlite_observations.time.monotonic", side_effect=[0, 100]):
            with self.assertRaises(TimeoutError):
                self.read(max_seconds=1)

    def test_reversed_gap_rejected(self):
        self.change("UPDATE gaps SET gap_start_ms=100000, gap_end_ms=90000")
        with self.assertRaisesRegex(ValueError, "reversed"):
            self.read()

    def test_standalone_fixture_has_durable_receipt_no_id_reuse(self):
        output = self.root / "saved-canary"
        report = run(output)
        self.assertTrue(report["passed"])
        self.assertEqual(report["real_market_rows_read"], 0)
        self.assertTrue((output / "canary.json").is_file())
        with self.assertRaises(FileExistsError):
            run(output)


if __name__ == "__main__":
    unittest.main()
