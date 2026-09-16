import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sports_event_research.fetch_polymarket_2024_nfl_catalog import fetch


def event(event_id="1", start="2024-09-27T00:15:00Z"):
    return {
        "id": event_id,
        "slug": "nfl-nyg-dal-2024-09-26",
        "seriesSlug": "nfl",
        "startTime": start,
        "gameId": None,
        "markets": [{"sportsMarketType": "moneyline", "outcomes": '["A","B"]'}],
    }


class Catalog2024Tests(unittest.TestCase):
    def run_fetch(self, responses, max_pages=10):
        with tempfile.TemporaryDirectory() as directory:
            raw = [(json.dumps(value).encode(), f"https://example.test/{index}")
                   for index, value in enumerate(responses)]
            with patch("sports_event_research.fetch_polymarket_2024_nfl_catalog.get",
                       side_effect=raw) as mocked:
                result = fetch(Path(directory) / "fresh", max_pages=max_pages)
                self.assertEqual(mocked.call_count, len(raw))
                self.assertEqual(result["catalog_sha256"], __import__("hashlib").sha256(
                    (Path(directory) / "fresh" / "events.catalog.json").read_bytes()).hexdigest())
                return result

    def test_two_pages_are_archived_without_claiming_training_admission(self):
        result = self.run_fetch([
            [{"id": "1", "slug": "nfl"}],
            {"events": [event()], "next_cursor": "cursor-1"},
            {"events": [event("2", "2024-10-01T00:00:00Z")]},
        ])
        self.assertEqual(result["events"], 2)
        self.assertEqual(result["game_slug_candidates_not_mapped"], 2)
        self.assertEqual(result["two_outcome_moneyline_markets_on_candidates"], 2)
        self.assertEqual(result["events_with_game_id"], 0)
        self.assertFalse(result["train_admitted"])
        self.assertFalse(result["prices_opened"])

    def test_rejects_duplicate_events(self):
        with tempfile.TemporaryDirectory() as directory:
            responses = iter([
                (b'[{"id":"1","slug":"nfl"}]', "series"),
                (json.dumps({"events": [event(), event()]}).encode(), "events"),
            ])
            with patch("sports_event_research.fetch_polymarket_2024_nfl_catalog.get",
                       side_effect=lambda *_: next(responses)):
                with self.assertRaisesRegex(ValueError, "duplicated"):
                    fetch(Path(directory) / "fresh")

    def test_rejects_out_of_window(self):
        with tempfile.TemporaryDirectory() as directory:
            responses = iter([
                (b'[{"id":"1","slug":"nfl"}]', "series"),
                (json.dumps({"events": [event(start="2025-09-01T00:00:00Z")]}).encode(),
                 "events"),
            ])
            with patch("sports_event_research.fetch_polymarket_2024_nfl_catalog.get",
                       side_effect=lambda *_: next(responses)):
                with self.assertRaisesRegex(ValueError, "outside frozen"):
                    fetch(Path(directory) / "fresh")

    def test_rejects_truncated_pagination(self):
        with tempfile.TemporaryDirectory() as directory:
            responses = iter([
                (b'[{"id":"1","slug":"nfl"}]', "series"),
                (json.dumps({"events": [event()], "next_cursor": "more"}).encode(), "events"),
            ])
            with patch("sports_event_research.fetch_polymarket_2024_nfl_catalog.get",
                       side_effect=lambda *_: next(responses)):
                with self.assertRaisesRegex(ValueError, "partial catalog"):
                    fetch(Path(directory) / "fresh", max_pages=1)


if __name__ == "__main__":
    unittest.main()
