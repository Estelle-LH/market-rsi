import csv
import json
from pathlib import Path
import tempfile
import unittest

from sports_event_research.build_route_dev_selection import build


class RouteDevSelectionTests(unittest.TestCase):
    def test_all_fifty_selected_without_scores_or_prices(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); mapping = root / "mapping.csv"; catalog = root / "catalog.json"
            fields = ["nflverse_game_id", "sportradar_game_id", "split_role", "scheduled_utc",
                      "home_team", "away_team", "polymarket_event_id"]
            with mapping.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
                for index in range(50):
                    writer.writerow({"nflverse_game_id": f"g{index:02d}",
                        "sportradar_game_id": f"s{index:02d}", "split_role": "route_dev",
                        "scheduled_utc": f"2025-12-{index // 2 + 1:02d}T00:00:00+00:00",
                        "home_team": "H", "away_team": "A", "polymarket_event_id": str(index)})
            catalog.write_text(json.dumps([{"id": index, "gameId": index,
                "slug": f"e{index}", "title": "A vs. H", "eventStartTime": "2025-12-01T00:00:00Z",
                "markets": [{"id": index, "sportsMarketType": "moneyline", "conditionId": f"c{index}",
                    "outcomes": '["A","H"]', "clobTokenIds": '["a","h"]'}]}
                for index in range(50)]))
            result = build(mapping, catalog, root / "out")
            self.assertEqual(result["selection_count"], 50)
            self.assertFalse(result["selection_used_price_trade_result_score_volume_or_model_output"])
            self.assertFalse(result["trades_opened"])
            self.assertFalse(result["labels_opened"])


if __name__ == "__main__":
    unittest.main()
