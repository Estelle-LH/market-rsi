"""Offline checks for fixed 2023 trade-canary sample and kickoff rules."""

import unittest

from supervisor_harness.screen_2023_fill_canary import fixed_sample, partition_for


class Archive2023FillCanaryTests(unittest.TestCase):
    def test_first_middle_last_is_deterministic(self) -> None:
        rows = [{"game_id": str(i), "game_date": f"2023-09-{i:02d}"}
                for i in (5, 1, 3, 2, 4)]
        self.assertEqual([r["game_id"] for r in fixed_sample(rows)], ["1", "3", "5"])

    def test_sample_partition_and_cross_month_guard(self) -> None:
        key, url = partition_for(1694132400)
        self.assertEqual(key, "2023-09")
        self.assertIn("/year=2023/month=09.parquet", url)
        with self.assertRaises(ValueError):
            partition_for(1696118400)


if __name__ == "__main__":
    unittest.main()
