"""No-network tests for the P0 public-metadata inventory."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from supervisor_harness import inventory_polymarket_nfl_metadata as inventory


def event(identifier: str, slug: str, market_type: str = "moneyline") -> dict:
    return {"id": identifier, "slug": slug, "markets": [{
        "id": "market-" + identifier, "sportsMarketType": market_type,
        "outcomes": '["Away","Home"]', "clobTokenIds": '["token-a","token-b"]',
        "conditionId": "condition-" + identifier,
    }]}


class InventoryTests(unittest.TestCase):
    def test_classification_does_not_count_spread_as_moneyline(self) -> None:
        rows = [event("1", "nfl-aaa-bbb-2021-09-12", "spread"),
                event("2", "nfl-ccc-ddd-2021-09-19"),
                event("3", "unrelated-election-2021-09-19")]
        result = inventory.classify(rows, 2021)
        self.assertEqual(result["events"], 3)
        self.assertEqual(result["game_slug_candidates_not_schedule_matched"], 2)
        self.assertEqual(result["events_with_one_tokenized_moneyline"], 1)
        self.assertEqual(result["market_type_counts_on_game_slugs"],
                         {"spread": 1, "moneyline": 1})

    def test_fetch_follows_cursor_and_preserves_source_receipts(self) -> None:
        def fake_get(path: str, params: dict, timeout: float) -> tuple[bytes, str]:
            if path == "/series":
                value = [{"id": "1", "slug": "nfl"}]
            elif "after_cursor" not in params:
                value = {"events": [event("1", "nfl-aaa-bbb-2021-09-12")],
                         "next_cursor": "next-page"}
            else:
                self.assertEqual(params["after_cursor"], "next-page")
                value = {"events": [event("2", "nfl-ccc-ddd-2021-09-19", "spread")],
                         "next_cursor": None}
            return json.dumps(value).encode(), "https://example.test" + path

        with TemporaryDirectory() as directory, patch.object(inventory, "get", fake_get):
            output = Path(directory) / "inventory"
            report = inventory.fetch(output, seasons=(2021,))
            self.assertEqual(report["seasons"]["2021"]["events"], 2)
            self.assertEqual(len(report["seasons"]["2021"]["pages"]), 2)
            self.assertTrue((output / "2021-page-001.raw.json").exists())
            self.assertFalse(report["formal_data_admitted"])

    def test_2025_uses_separate_series(self) -> None:
        seen = []

        def fake_get(path: str, params: dict, timeout: float) -> tuple[bytes, str]:
            seen.append((path, dict(params)))
            if path == "/series":
                value = [{"id": "2025-id", "slug": "nfl-2025"}]
            else:
                value = {"events": [event("1", "nfl-aaa-bbb-2025-09-12")],
                         "next_cursor": None}
            return json.dumps(value).encode(), "https://example.test" + path

        with TemporaryDirectory() as directory, patch.object(inventory, "get", fake_get):
            report = inventory.fetch(Path(directory) / "inventory", seasons=(2025,))
        self.assertEqual(seen[0][1]["slug"], "nfl-2025")
        self.assertEqual(seen[1][1]["series_id"], "2025-id")
        self.assertEqual(report["seasons"]["2025"]["events_with_one_tokenized_moneyline"], 1)


if __name__ == "__main__":
    unittest.main()
