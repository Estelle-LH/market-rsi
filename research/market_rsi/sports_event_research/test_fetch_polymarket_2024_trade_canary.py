import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sports_event_research.fetch_polymarket_2024_trade_canary import choose, fetch


FIELDS = ("polymarket_event_id", "event_slug", "event_start_utc", "nflverse_game_id",
          "condition_id", "tokens_json", "slug_order")


def write_mapping(path: Path) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow({"polymarket_event_id": "late", "event_slug": "nfl-b-c-2024-09-08",
                         "event_start_utc": "2024-09-08T17:00:00Z", "nflverse_game_id": "g2",
                         "condition_id": "condition-late", "tokens_json": '["x","y"]',
                         "slug_order": "away_home"})
        writer.writerow({"polymarket_event_id": "early", "event_slug": "nfl-a-b-2024-09-05",
                         "event_start_utc": "2024-09-06T00:20:00Z", "nflverse_game_id": "g1",
                         "condition_id": "condition-early", "tokens_json": '["a","b"]',
                         "slug_order": "home_away"})


class TradeCanary2024Tests(unittest.TestCase):
    def test_selection_uses_time_not_input_order_or_volume(self):
        with tempfile.TemporaryDirectory() as directory:
            mapping = Path(directory) / "mapping.csv"
            write_mapping(mapping)
            selected = choose(mapping)
            self.assertEqual(selected["event_id"], "early")
            self.assertEqual(selected["condition_id"], "condition-early")

    def test_raw_and_safe_trade_are_archived_but_not_admitted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mapping = root / "mapping.csv"
            write_mapping(mapping)
            trade = {"conditionId": "condition-early", "asset": "a", "timestamp": 1725582000,
                     "price": 0.55, "size": 10, "side": "BUY", "transactionHash": "tx1",
                     "proxyWallet": "must-not-be-in-safe-output"}
            with patch("sports_event_research.fetch_polymarket_2024_trade_canary.fetch_page",
                       return_value=(json.dumps([trade]).encode(), "https://example.test")):
                result = fetch(mapping, root / "output")
            self.assertEqual(result["retrieved_query_summary"]["trades"], 1)
            self.assertFalse(result["train_admitted"])
            self.assertTrue((root / "output" / "trades-page-0.raw.json").exists())
            self.assertNotIn("proxyWallet", (root / "output" / "trade_window.csv").read_text())


if __name__ == "__main__":
    unittest.main()
