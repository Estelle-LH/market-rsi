from __future__ import annotations

import unittest

from openmarket_partition_canary import (META_PATH, REVISION,
                                         inventory_and_selection)


def record(path, size=2_000_000, marker="a"):
    return {"path": path, "bytes": size, "lfs_sha256": marker * 64}


class OpenMarketPartitionCanaryTests(unittest.TestCase):
    def test_selection_is_deterministic_stratified_and_bounded(self):
        values = [
            record(META_PATH, 400_000, "f"),
            record("unified/polymarket_ticks_ms/date=2026-03-15/part-000001.parquet", marker="a"),
            record("unified/polymarket_ticks_ms/date=2026-04-21/part-000001.parquet", marker="b"),
            record("unified/polymarket_ticks_ms/date=2026-05-13/part-000001.parquet", marker="c"),
            record("unified/polymarket_ticks_ms/date=2026-05-14/part-000001.parquet", marker="d"),
        ]
        first = inventory_and_selection(values, plan_sha256="1" * 64)
        second = inventory_and_selection(list(reversed(values)), plan_sha256="1" * 64)
        self.assertEqual(first["selected"], second["selected"])
        self.assertEqual(len(first["selected"]), 3)
        self.assertLess(first["selected_bytes"], 1_000_000_000)
        self.assertEqual(first["polymarket_tick_coverage"]["last_before_documented_gap"],
                         "2026-04-21")
        self.assertEqual(first["polymarket_tick_coverage"]["first_after_documented_gap"],
                         "2026-05-13")

    def test_requires_files_on_both_sides_of_gap(self):
        values = [record(META_PATH, 400_000),
                  record("unified/polymarket_ticks_ms/date=2026-03-15/part-000001.parquet")]
        with self.assertRaisesRegex(ValueError, "both sides"):
            inventory_and_selection(values, plan_sha256="2" * 64)

    def test_revision_is_frozen(self):
        self.assertEqual(REVISION, "74502466d1a7cef56395bfd8d0b465fbebc849cf")


if __name__ == "__main__":
    unittest.main()
