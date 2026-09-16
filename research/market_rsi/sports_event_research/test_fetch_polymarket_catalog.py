import unittest

from sports_event_research.fetch_polymarket_catalog import choose_canary, market_rows


class PolymarketCatalogTests(unittest.TestCase):
    def test_deterministic_canary_does_not_use_volume_or_results(self):
        events = [{
            "id": "later", "gameId": "g2", "slug": "later", "title": "Later",
            "eventStartTime": "2025-09-08T00:00:00Z", "volume": 999999,
            "markets": [{"id": "m2", "sportsMarketType": "moneyline", "outcomes": '["A","B"]',
                         "clobTokenIds": '["t2a","t2b"]', "conditionId": "c2"}],
        }, {
            "id": "early", "gameId": "g1", "slug": "early", "title": "Early",
            "eventStartTime": "2025-09-07T00:00:00Z", "volume": 1,
            "markets": [{"id": "m1", "sportsMarketType": "moneyline", "outcomes": ["A", "B"],
                         "clobTokenIds": ["t1a", "t1b"], "conditionId": "c1"}],
        }]
        selected = choose_canary(events)
        self.assertEqual(selected["event_id"], "early")
        self.assertFalse(selected["price_history_opened"])
        self.assertNotIn("volume", selected)

    def test_index_preserves_outcome_and_token_order(self):
        event = {"id": "e", "gameId": "g", "markets": [{
            "id": "m", "outcomes": '["Home","Away"]', "clobTokenIds": '["h","a"]',
        }]}
        row = market_rows([event])[0]
        self.assertEqual(row["outcomes_json"], '["Home","Away"]')
        self.assertEqual(row["clob_token_ids_json"], '["h","a"]')


if __name__ == "__main__":
    unittest.main()
