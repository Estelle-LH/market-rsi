"""Offline bounds for the stratified on-chain fill screen."""

import unittest
from datetime import datetime, timezone

from supervisor_harness.screen_2023_stratified_fills import month_partitions


class MonthPartitionTests(unittest.TestCase):
    def test_one_month(self) -> None:
        start = int(datetime(2023, 8, 15, 12, tzinfo=timezone.utc).timestamp())
        first = month_partitions(start, start + 3600)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0][0], "2023-08")

    def test_cross_month_and_invalid_window(self) -> None:
        start = int(datetime(2023, 8, 31, 23, 30, tzinfo=timezone.utc).timestamp())
        result = month_partitions(start, start + 7200)
        self.assertEqual([month for month, _ in result], ["2023-08", "2023-09"])
        with self.assertRaises(ValueError):
            month_partitions(1, 1)


if __name__ == "__main__":
    unittest.main()
