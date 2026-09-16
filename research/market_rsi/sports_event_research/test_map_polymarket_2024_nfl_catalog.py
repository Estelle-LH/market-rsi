import unittest

from sports_event_research.map_polymarket_2024_nfl_catalog import map_events


def game(game_id="2024_01_BAL_KC", game_date="2024-09-05"):
    return {"season": 2024, "nflverse_game_id": game_id, "game_date": game_date,
            "away_team": "BAL", "home_team": "KC"}


def event(event_id="event-1", slug="nfl-bal-kc-2024-09-05"):
    return {"id": event_id, "slug": slug, "startTime": "2024-09-06T00:20:00Z",
            "markets": [{"id": "market-1", "sportsMarketType": "moneyline",
                         "conditionId": "condition-1", "outcomes": '["Chiefs","Ravens"]',
                         "clobTokenIds": '["token-1","token-2"]'}]}


class Map2024CatalogTests(unittest.TestCase):
    def test_exact_identity_maps_without_guessing_outcome_orientation(self):
        rows, failures = map_events([event()], [game()])
        self.assertEqual(failures, [])
        self.assertEqual(rows[0]["nflverse_game_id"], "2024_01_BAL_KC")
        self.assertEqual(rows[0]["slug_order"], "away_home")
        self.assertEqual(rows[0]["date_resolution"], "exact")
        self.assertEqual(rows[0]["tokens_json"], '["token-1","token-2"]')

    def test_home_away_slug_is_bound_by_schedule_not_assumed_order(self):
        rows, failures = map_events([event(slug="nfl-kc-bal-2024-09-05")], [game()])
        self.assertEqual(failures, [])
        self.assertEqual(rows[0]["slug_order"], "home_away")
        self.assertEqual(rows[0]["away_team"], "BAL")
        self.assertEqual(rows[0]["home_team"], "KC")

    def test_both_orientations_matching_different_games_is_ambiguous(self):
        opposite = {**game("opposite"), "away_team": "KC", "home_team": "BAL"}
        rows, failures = map_events([event()], [game(), opposite])
        self.assertEqual(rows, [])
        self.assertEqual(failures[0]["reason"], "game_ambiguous_or_missing")

    def test_older_team_aliases_are_explicit(self):
        raiders = {**game("2024_01_LV_LAC"), "away_team": "LV", "home_team": "LAC"}
        rows, failures = map_events([event(slug="nfl-lac-las-2024-09-05")], [raiders])
        self.assertEqual(failures, [])
        self.assertEqual(rows[0]["away_team"], "LV")
        commanders = {**game("2024_01_WAS_TB"), "away_team": "WAS", "home_team": "TB"}
        rows, failures = map_events([event(slug="nfl-tb-wsh-2024-09-05")], [commanders])
        self.assertEqual(failures, [])
        self.assertEqual(rows[0]["away_team"], "WAS")

    def test_only_unique_adjacent_date_is_allowed(self):
        rows, failures = map_events([event()], [game(game_date="2024-09-06")])
        self.assertEqual(failures, [])
        self.assertEqual(rows[0]["date_resolution"], "adjacent")
        rows, failures = map_events([event()], [game("a", "2024-09-04"),
                                                game("b", "2024-09-06")])
        self.assertEqual(rows, [])
        self.assertEqual(failures[0]["reason"], "game_ambiguous_or_missing")

    def test_duplicate_event_for_same_game_is_not_counted_twice(self):
        rows, failures = map_events([event(), event(event_id="event-2")], [game()])
        self.assertEqual(len(rows), 1)
        self.assertEqual(failures[0]["reason"], "duplicate_event_for_game")

    def test_missing_moneyline_does_not_admit_game(self):
        candidate = event()
        candidate["markets"] = []
        rows, failures = map_events([candidate], [game()])
        self.assertEqual(rows, [])
        self.assertEqual(failures[0]["reason"], "moneyline_missing_or_ambiguous")

    def test_out_of_window_is_rejected(self):
        candidate = event()
        candidate["startTime"] = "2025-09-06T00:20:00Z"
        with self.assertRaisesRegex(ValueError, "outside frozen"):
            map_events([candidate], [game()])


if __name__ == "__main__":
    unittest.main()
