import gzip
import json
from pathlib import Path
import tempfile
import unittest

from sports_event_research.build_play_trade_canary import (align, field_yards_to_goal,
    home_trade_series, plays, summarize)


class PlayTradeAlignmentTests(unittest.TestCase):
    def test_alignment_uses_only_past_print_at_each_horizon(self):
        rows = align([{"play_id": "p", "play_timestamp": 100, "home_points": 0,
                       "away_points": 0}], [90, 120, 160], [.4, .5, .6])
        self.assertEqual(rows[0]["home_price_pre"], .4)
        self.assertAlmostEqual(rows[0]["home_change_30s"], .1)
        self.assertAlmostEqual(rows[0]["home_change_60s"], .2)
        self.assertEqual(summarize(rows)["covered_300s"], 1)

    def test_stale_pretrade_is_unavailable(self):
        rows = align([{"play_id": "p", "play_timestamp": 1000, "home_points": 0,
                       "away_points": 0}], [1, 1010], [.4, .5])
        self.assertEqual(rows[0]["home_price_pre"], "")
        self.assertEqual(rows[0]["home_change_30s"], "")

    def test_preplay_print_is_not_reused_as_postplay_zero_change(self):
        rows = align([{"play_id": "p", "play_timestamp": 100, "home_points": 0,
                       "away_points": 0}], [90], [.4])
        self.assertEqual(rows[0]["home_price_pre"], .4)
        self.assertEqual(rows[0]["home_price_30s"], "")
        self.assertEqual(rows[0]["home_change_300s"], "")

    def test_field_position_is_from_possession_perspective(self):
        self.assertEqual(field_yards_to_goal("BUF", {"alias": "BUF", "yardline": 35}), 65)
        self.assertEqual(field_yards_to_goal("MIA", {"alias": "BUF", "yardline": 47}), 47)

    def test_play_rows_expose_only_preplay_state_for_features(self):
        game = {"summary": {"home": {"alias": "BUF"}, "away": {"alias": "MIA"}},
                "periods": [{"number": 1, "pbp": [{"type": "play", "id": "p",
                    "sequence": 1, "clock": "14:00", "wall_clock": "2025-01-01T00:00:00Z",
                    "play_type": "rush", "home_points": 7, "away_points": 0, "official": True,
                    "scoring_play": True, "description": "x", "details": [{"category": "touchdown"}],
                    "start_situation": {"down": 2, "yfd": 4,
                        "possession": {"alias": "BUF"},
                        "location": {"alias": "MIA", "yardline": 20}},
                    "end_situation": {"clock": "13:50", "down": 1, "yfd": 10,
                        "possession": {"alias": "MIA"},
                        "location": {"alias": "BUF", "yardline": 25}}}]}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "game.json.gz"
            with gzip.open(path, "wt") as stream:
                json.dump(game, stream)
            row = plays(path)[0]
        self.assertEqual(row["regulation_seconds_remaining"], 3540)
        self.assertEqual(row["possession_is_home"], 1)
        self.assertEqual(row["yards_to_goal"], 20)
        self.assertEqual(row["home_points_pre"], 0)
        self.assertEqual(row["home_score_diff_pre"], 0)
        self.assertEqual(row["post_regulation_seconds_remaining"], 3530)
        self.assertEqual(row["post_home_score_diff"], 7)
        self.assertEqual(row["post_possession_is_home"], 0)
        self.assertEqual(row["post_yards_to_goal"], 25)

    def test_explicit_team_names_prove_mixed_alias_outcome_order(self):
        selection = {"event_title": "Rams vs. Panthers", "outcomes": ["LAR", "Panthers"],
                     "away_team": "LAR", "home_team": "CAR", "clob_token_ids": ["a", "h"]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trades.csv"
            path.write_text("asset,price,timestamp\na,0.4,1\nh,0.7,2\n")
            times, prices = home_trade_series(path, selection)
        self.assertEqual(times, [1, 2])
        self.assertEqual(prices, [.6, .7])

    def test_unknown_or_reversed_team_name_is_rejected(self):
        selection = {"event_title": "Panthers vs. Rams", "outcomes": ["Panthers", "Rams"],
                     "away_team": "LAR", "home_team": "CAR", "clob_token_ids": ["a", "h"]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trades.csv"; path.write_text("asset,price,timestamp\n")
            with self.assertRaisesRegex(ValueError, "explicit NFL names"):
                home_trade_series(path, selection)


if __name__ == "__main__":
    unittest.main()
