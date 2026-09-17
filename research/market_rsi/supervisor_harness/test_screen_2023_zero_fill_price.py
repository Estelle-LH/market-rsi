"""Offline zero-fill case selection guard."""

import unittest

from supervisor_harness.screen_2023_zero_fill_price import zero_fill_game


class ZeroFillSelectionTests(unittest.TestCase):
    def test_uses_zero_full_window_not_postseason(self) -> None:
        rows = [{"game_id": "2023_19_A_B", "stratum": "weeks_19_22", "window_fills": 0},
                {"game_id": "2023_14_C_D", "stratum": "weeks_13_18", "window_fills": 0},
                {"game_id": "2023_13_E_F", "stratum": "weeks_13_18", "window_fills": 1}]
        self.assertEqual(zero_fill_game(rows), "2023_14_C_D")

    def test_none_fails(self) -> None:
        with self.assertRaises(ValueError):
            zero_fill_game([{"game_id": "2023_01_A_B", "stratum": "weeks_01_06",
                             "window_fills": 1}])


if __name__ == "__main__":
    unittest.main()
