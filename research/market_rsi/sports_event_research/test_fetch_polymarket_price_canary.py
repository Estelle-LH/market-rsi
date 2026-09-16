import csv
import json
from pathlib import Path
import tempfile
import unittest

from sports_event_research.fetch_polymarket_price_canary import bind_game, read_selection, validate_history


class PriceCanaryTests(unittest.TestCase):
    def test_canary_maps_to_nonfinal_game(self):
        selection = {"event_slug": "nfl-mia-buf-2025-09-18"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "master.csv"
            fields = ["game_date", "away_team", "home_team", "split_role", "nflverse_game_id"]
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
                writer.writerow({"game_date": "2025-09-18", "away_team": "MIA", "home_team": "BUF",
                                 "split_role": "market_train", "nflverse_game_id": "g"})
            self.assertEqual(bind_game(selection, path)["nflverse_game_id"], "g")

    def test_final_game_is_rejected(self):
        selection = {"event_slug": "nfl-mia-buf-2025-09-18"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "master.csv"
            fields = ["game_date", "away_team", "home_team", "split_role"]
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
                writer.writerow({"game_date": "2025-09-18", "away_team": "MIA", "home_team": "BUF",
                                 "split_role": "sealed_final"})
            with self.assertRaisesRegex(ValueError, "sealed Final"):
                bind_game(selection, path)

    def test_price_quality_rejects_duplicate_timestamps(self):
        raw = json.dumps({"history": {"a": [{"t": 1, "p": .4}, {"t": 1, "p": .5}], "b": []}}).encode()
        with self.assertRaisesRegex(ValueError, "duplicated"):
            validate_history(raw, ["a", "b"])

    def test_pilot_selection_binds_by_frozen_game_id(self):
        selection = {"nflverse_game_id": "g", "sportradar_game_id": "s",
                     "home_team": "LAR", "away_team": "SEA", "scheduled_utc": "t",
                     "split_role": "market_train", "event_slug": "nfl-sea-la-2025-01-01"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "master.csv"
            fields = ["game_date", "away_team", "home_team", "split_role", "nflverse_game_id",
                      "sportradar_game_id", "scheduled_utc"]
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
                writer.writerow({"game_date": "2025-01-01", "away_team": "SEA", "home_team": "LAR",
                                 "split_role": "market_train", "nflverse_game_id": "g",
                                 "sportradar_game_id": "s", "scheduled_utc": "t"})
            self.assertEqual(bind_game(selection, path)["nflverse_game_id"], "g")

    def test_pilot_selection_rejects_dev_even_when_marked_train(self):
        selection = {"nflverse_game_id": "g", "sportradar_game_id": "s",
                     "home_team": "H", "away_team": "A", "scheduled_utc": "t",
                     "split_role": "market_train", "event_slug": "nfl-a-h-2025-01-01"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "master.csv"
            fields = ["away_team", "home_team", "split_role", "nflverse_game_id",
                      "sportradar_game_id", "scheduled_utc"]
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
                writer.writerow({"away_team": "A", "home_team": "H", "split_role": "route_dev",
                                 "nflverse_game_id": "g", "sportradar_game_id": "s", "scheduled_utc": "t"})
            with self.assertRaisesRegex(ValueError, "market_train"):
                bind_game(selection, path)

    def test_read_selection_accepts_only_unopened_train_pilot(self):
        value = {"schema": "polymarket_nfl_trade_pilot_selection_v1", "split_role": "market_train",
                 "price_history_opened": False, "trades_opened": False, "clob_token_ids": ["a", "b"]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "selection.json"; path.write_text(json.dumps(value))
            self.assertEqual(read_selection(path)["split_role"], "market_train")
            value["trades_opened"] = True; path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "unopened"):
                read_selection(path)

    def test_route_dev_requires_explicit_role_and_never_opens_final(self):
        value = {"schema": "polymarket_nfl_route_dev_selection_v1", "split_role": "route_dev",
                 "price_history_opened": False, "trades_opened": False,
                 "clob_token_ids": ["a", "b"]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "selection.json"; path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "market_train"):
                read_selection(path)
            self.assertEqual(read_selection(path, "route_dev")["split_role"], "route_dev")
            value["schema"] = "polymarket_nfl_route_dev_selection_v1"
            value["split_role"] = "sealed_final"; path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "sealed Final"):
                read_selection(path, "sealed_final")

    def test_route_dev_binding_requires_exact_declared_role(self):
        selection = {"nflverse_game_id": "g", "sportradar_game_id": "s",
                     "home_team": "H", "away_team": "A", "scheduled_utc": "t",
                     "split_role": "route_dev"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "master.csv"
            fields = ["away_team", "home_team", "split_role", "nflverse_game_id",
                      "sportradar_game_id", "scheduled_utc"]
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
                writer.writerow({"away_team": "A", "home_team": "H", "split_role": "route_dev",
                                 "nflverse_game_id": "g", "sportradar_game_id": "s",
                                 "scheduled_utc": "t"})
            self.assertEqual(bind_game(selection, path, "route_dev")["nflverse_game_id"], "g")
            with self.assertRaisesRegex(ValueError, "market_train"):
                bind_game(selection, path)


if __name__ == "__main__":
    unittest.main()
