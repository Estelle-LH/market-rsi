"""No-network checks for the 2025 schedule identity screen."""

import unittest

from supervisor_harness.screen_2025_schedule import match, schedule_identities


class ScheduleScreenTests(unittest.TestCase):
    def test_reads_only_2025_identity_fields(self) -> None:
        raw = ("game_id,season,gameday,away_team,home_team,away_score,home_score\n"
               "2024_01_X_Y,2024,2024-09-07,X,Y,1,2\n"
               "2025_01_HOU_LA,2025,2025-09-07,HOU,LA,99,0\n").encode()
        self.assertEqual(schedule_identities(raw), [{"game_id": "2025_01_HOU_LA",
                                                    "game_date": "2025-09-07",
                                                    "away_team": "HOU", "home_team": "LAR"}])

    def test_alias_match_ignores_outcome_and_preserves_failure(self) -> None:
        games = [{"game_id": "2025_01_HOU_LAR", "game_date": "2025-09-07",
                  "away_team": "HOU", "home_team": "LAR"}]
        events = [{"id": "1", "slug": "nfl-hou-la-2025-09-07", "markets": [{
            "id": "m", "sportsMarketType": "moneyline", "conditionId": "c",
            "outcomes": '["Texans","Rams"]', "clobTokenIds": '["a","b"]'}]},
                  {"id": "2", "slug": "nfl-other-team-2025-09-08", "markets": []}]
        mapped, failures = match(events, games)
        self.assertEqual([row["game_id"] for row in mapped], ["2025_01_HOU_LAR"])
        self.assertEqual(failures, [{"event_id": "2", "reason": "schedule_missing_or_ambiguous"}])


if __name__ == "__main__":
    unittest.main()
