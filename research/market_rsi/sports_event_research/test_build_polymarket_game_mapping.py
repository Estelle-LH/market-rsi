import csv
import json
from pathlib import Path
import tempfile
import unittest

from sports_event_research.build_polymarket_game_mapping import map_catalog


class PolymarketGameMappingTests(unittest.TestCase):
    def test_only_exact_game_slug_maps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); master = root / "master.csv"; catalog = root / "catalog.json"
            with master.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["game_date", "away_team", "home_team",
                    "nflverse_game_id", "sportradar_game_id", "split_role", "scheduled_utc"])
                writer.writeheader(); writer.writerow({"game_date": "2025-09-18", "away_team": "MIA",
                    "home_team": "BUF", "nflverse_game_id": "g", "sportradar_game_id": "s",
                    "split_role": "market_train", "scheduled_utc": "t"})
            catalog.write_text(json.dumps([{"id": "e", "gameId": 1, "slug": "nfl-mia-buf-2025-09-18",
                "markets": [{"sportsMarketType": "moneyline"}]},
                {"id": "x", "gameId": 2, "slug": "season-market", "markets": []}]))
            rows, failures = map_catalog(master, catalog)
            self.assertEqual(rows[0]["nflverse_game_id"], "g")
            self.assertEqual(failures[0]["reason"], "slug_shape")

    def test_explicit_provider_aliases_map_without_fuzzy_matching(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); master = root / "master.csv"; catalog = root / "catalog.json"
            with master.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["game_date", "away_team", "home_team",
                    "nflverse_game_id", "sportradar_game_id", "split_role", "scheduled_utc"])
                writer.writeheader(); writer.writerow({"game_date": "2025-09-21", "away_team": "HOU",
                    "home_team": "JAC", "nflverse_game_id": "g1", "sportradar_game_id": "s1",
                    "split_role": "market_train", "scheduled_utc": "t"})
                writer.writerow({"game_date": "2025-09-21", "away_team": "LAR",
                    "home_team": "PHI", "nflverse_game_id": "g2", "sportradar_game_id": "s2",
                    "split_role": "market_train", "scheduled_utc": "t"})
            catalog.write_text(json.dumps([
                {"id": "e1", "gameId": 1, "slug": "nfl-hou-jax-2025-09-21", "markets": []},
                {"id": "e2", "gameId": 2, "slug": "nfl-la-phi-2025-09-21", "markets": []},
            ]))
            rows, failures = map_catalog(master, catalog)
            self.assertEqual({row["nflverse_game_id"] for row in rows}, {"g1", "g2"})
            self.assertEqual(rows[0]["polymarket_home_team"], "JAX")
            self.assertFalse(failures)

    def test_adjacent_date_requires_exact_unique_team_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); master = root / "master.csv"; catalog = root / "catalog.json"
            with master.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["game_date", "away_team", "home_team",
                    "nflverse_game_id", "sportradar_game_id", "split_role", "scheduled_utc"])
                writer.writeheader(); writer.writerow({"game_date": "2026-01-03", "away_team": "SEA",
                    "home_team": "SF", "nflverse_game_id": "g", "sportradar_game_id": "s",
                    "split_role": "sealed_final", "scheduled_utc": "t"})
            catalog.write_text(json.dumps([{"id": "e", "gameId": 1,
                "slug": "nfl-sea-sf-2026-01-04", "markets": []}]))
            rows, failures = map_catalog(master, catalog)
            self.assertEqual(rows[0]["date_resolution"], "exact_teams_adjacent_date")
            self.assertFalse(failures)


if __name__ == "__main__":
    unittest.main()
