"""Offline boundaries for public historical-price availability diagnostics."""

import unittest

from supervisor_harness.screen_2023_price_history_canary import summarize


class PriceHistoryCanaryTests(unittest.TestCase):
    def test_constant_samples_are_not_changes(self) -> None:
        raw = b'{"history":[{"t":100,"p":0.5},{"t":160,"p":0.5},{"t":220,"p":0.6}]}'
        result = summarize(raw, 100, 200, 300)
        self.assertEqual((result["points"], result["unique_price_values"],
                          result["consecutive_price_changes"], result["max_flat_run_points"]),
                         (3, 2, 1, 2))
        self.assertEqual(result["game_to_plus_five_hours_points"], 1)
        self.assertEqual(result["median_gap_seconds"], 60)

    def test_even_number_of_gaps_uses_true_median(self) -> None:
        raw = b'{"history":[{"t":100,"p":0.5},{"t":160,"p":0.5},{"t":280,"p":0.5}]}'
        self.assertEqual(summarize(raw, 100, 200, 300)["median_gap_seconds"], 90)

    def test_invalid_range_and_nonmonotonic_fail(self) -> None:
        with self.assertRaises(ValueError):
            summarize(b'{"history":[{"t":99,"p":0.5}]}', 100, 200, 300)
        with self.assertRaises(ValueError):
            summarize(b'{"history":[{"t":120,"p":0.5},{"t":100,"p":0.4}]}',
                      100, 200, 300)


if __name__ == "__main__":
    unittest.main()
