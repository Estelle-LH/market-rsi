"""Offline identity and failure checks for the 2023 source-only screen."""

import unittest

from supervisor_harness.screen_2023_archive_catalog import match


class Archive2023ScreenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.games = [{"game_id": "2023_01_KC_DET", "game_date": "2023-09-07",
                       "away_team": "DET", "home_team": "KC"},
                      {"game_id": "2023_01_WAS_ARI", "game_date": "2023-09-10",
                       "away_team": "ARI", "home_team": "WAS"}]

    def test_exact_pair_and_alias_only(self) -> None:
        rows = [{"condition_id": "a", "slug": "nfl-kc-det-2023-09-07",
                 "token_ids": ["one", "two"]},
                {"condition_id": "b", "slug": "nfl-wsh-ari-2023-09-10",
                 "token_ids": ["three", "four"]}]
        matched, failures, unmatched = match(rows, self.games)
        self.assertEqual([m["game_id"] for m in matched],
                         ["2023_01_KC_DET", "2023_01_WAS_ARI"])
        self.assertEqual(failures, [])
        self.assertEqual(unmatched, [])

    def test_legacy_las_alias_is_las_vegas(self) -> None:
        games = [{"game_id": "2023_01_LV_DEN", "game_date": "2023-09-10",
                  "away_team": "LV", "home_team": "DEN"}]
        rows = [{"condition_id": "c", "slug": "nfl-den-las-2023-09-10",
                 "token_ids": ["one", "two"]}]
        matched, failures, unmatched = match(rows, games)
        self.assertEqual([m["game_id"] for m in matched], ["2023_01_LV_DEN"])
        self.assertEqual((failures, unmatched), ([], []))

    def test_missing_and_duplicate_games_remain_failures(self) -> None:
        rows = [{"condition_id": "a", "slug": "nfl-kc-det-2023-09-07",
                 "token_ids": ["one", "two"]},
                {"condition_id": "b", "slug": "nfl-det-kc-2023-09-07",
                 "token_ids": ["three", "four"]},
                {"condition_id": "c", "slug": "nfl-foo-bar-2023-09-10",
                 "token_ids": ["five", "six"]}]
        matched, failures, unmatched = match(rows, self.games)
        self.assertEqual(matched, [])
        self.assertEqual(len(unmatched), 2)
        self.assertEqual([f["reason"] for f in failures].count("multiple_markets_for_game"), 2)
        self.assertEqual([f["reason"] for f in failures].count("schedule_missing_or_ambiguous"), 1)


if __name__ == "__main__":
    unittest.main()
