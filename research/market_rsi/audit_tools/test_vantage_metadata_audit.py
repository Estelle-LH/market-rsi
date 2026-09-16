import datetime as dt
from pathlib import Path
import sqlite3
import tempfile
import unittest

from vantage_metadata_audit import Audit, PARTITIONS


class MetadataAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name).resolve() / "fixture.sqlite"
        db = sqlite3.connect(self.path)
        for table, (key, clock, index) in PARTITIONS.items():
            db.execute(f"CREATE TABLE {table}(id INTEGER PRIMARY KEY,{key} TEXT NOT NULL,{clock} INTEGER NOT NULL)")
            db.execute(f"CREATE INDEX {index} ON {table}({key},{clock})")
        self.start = int(dt.datetime(2026, 6, 3, tzinfo=dt.timezone.utc).timestamp() * 1000)
        for key, delta in (("book", 0), ("book", 1000), ("price_change", 1000),
                           ("price_change", 60000), ("book", 86400000)):
            db.execute("INSERT INTO pm_events(event_type,received_at_ms) VALUES(?,?)", (key, self.start + delta))
        db.commit()
        db.close()
        self.path.chmod(0o444)

    def tearDown(self):
        self.temp.cleanup()

    def test_inventory_uses_covering_index_and_real_bounds(self):
        a = Audit(str(self.path))
        result = a.inventory()
        self.assertEqual([p["event_type"] for p in result["pm_events"]], ["book", "price_change"])
        self.assertEqual(result["pm_events"][0]["last_ms"], self.start + 86400000)
        self.assertEqual(result["gaps"], [])
        self.assertTrue(all(any("COVERING INDEX" in x for x in plan) for plan in a.plans))
        a.finish()

    def test_union_not_sum_and_half_open_day(self):
        a = Audit(str(self.path))
        p = a.day("2026-06-03")["tables"]["pm_events"]
        self.assertEqual(p["rows"], 4)
        self.assertEqual(p["occupied_minutes_union"], 2)
        self.assertEqual(sum(x["occupied_minutes"] for x in p["partitions"]), 3)
        self.assertEqual(p["absent_minutes"], 1438)
        self.assertEqual(a.day("2026-06-02")["tables"]["pm_events"]["rows"], 0)
        a.finish()

    def test_calendar_does_not_fill_gaps_between_endpoints(self):
        a = Audit(str(self.path))
        result = a.calendar()["tables"]
        self.assertEqual(result["pm_events"]["present_dates_union"], ["2026-06-03", "2026-06-04"])
        self.assertEqual(len(result["pm_events"]["absent_dates"]), 44)
        self.assertEqual(result["cex_trades"]["present_dates_union"], [])
        self.assertEqual(len(result["cex_trades"]["absent_dates"]), 46)
        a.finish()

    def test_sidecar_and_writable_archive_rejected(self):
        sidecar = Path(str(self.path) + "-wal")
        sidecar.touch()
        with self.assertRaisesRegex(ValueError, "sidecar"):
            Audit(str(self.path))
        sidecar.unlink()
        self.path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "read-only"):
            Audit(str(self.path))

    def test_wrong_size_and_date_rejected(self):
        with self.assertRaisesRegex(ValueError, "size"):
            Audit(str(self.path), expected_bytes=1)
        a = Audit(str(self.path))
        with self.assertRaisesRegex(ValueError, "outside"):
            a.day("2026-07-01")
        a.finish()

    def test_timeout_and_identity_mutation_rejected(self):
        a = Audit(str(self.path), seconds=-1)
        with self.assertRaises(TimeoutError):
            a.inventory()
        a.finish()
        a = Audit(str(self.path))
        self.path.chmod(0o400)
        with self.assertRaisesRegex(ValueError, "changed"):
            a.finish()


if __name__ == "__main__":
    unittest.main()
