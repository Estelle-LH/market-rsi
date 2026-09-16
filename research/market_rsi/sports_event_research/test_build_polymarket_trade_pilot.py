import csv
import json
from pathlib import Path
import tempfile
import unittest

from sports_event_research.build_polymarket_trade_pilot import even_indices, select


class TradePilotSelectionTests(unittest.TestCase):
    def test_even_indices_include_chronological_endpoints(self):
        self.assertEqual(even_indices(10, 4), [0, 3, 6, 9])

    def test_only_train_is_selected_without_market_performance_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); mapping = root / "mapping.csv"; catalog = root / "catalog.json"
            fields = ["split_role", "polymarket_event_id", "scheduled_utc", "nflverse_game_id",
                      "sportradar_game_id", "home_team", "away_team"]
            with mapping.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
                for index, role in enumerate(("market_train", "market_train", "sealed_final")):
                    writer.writerow({"split_role": role, "polymarket_event_id": str(index),
                                     "scheduled_utc": f"2025-09-0{index + 1}T00:00:00Z",
                                     "nflverse_game_id": f"g{index}", "sportradar_game_id": f"s{index}",
                                     "home_team": "H", "away_team": "A"})
            events = []
            for index in range(3):
                events.append({"id": str(index), "gameId": index, "slug": f"e{index}",
                               "eventStartTime": f"2025-09-0{index + 1}T00:00:00Z",
                               "volume": 999999 if index == 2 else 0,
                               "markets": [{"id": f"m{index}", "sportsMarketType": "moneyline",
                                            "conditionId": f"c{index}", "outcomes": '["A","H"]',
                                            "clobTokenIds": '["a","h"]'}]})
            catalog.write_text(json.dumps(events))
            rows = select(mapping, catalog, 2)
            self.assertEqual([row["nflverse_game_id"] for row in rows], ["g0", "g1"])
            self.assertTrue(all(row["split_role"] == "market_train" for row in rows))
            self.assertTrue(all("volume" not in row for row in rows))


if __name__ == "__main__":
    unittest.main()
