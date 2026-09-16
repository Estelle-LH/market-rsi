import unittest

from sports_event_research.fetch_polymarket_trade_canary import validate


class TradeCanaryTests(unittest.TestCase):
    def setUp(self):
        self.selection = {"condition_id": "c", "clob_token_ids": ["a", "b"]}

    def test_valid_trade_summary(self):
        result = validate([{"conditionId": "c", "asset": "a", "timestamp": 2,
                            "price": .4, "size": 10}], self.selection)
        self.assertEqual(result["trades"], 1)
        self.assertEqual(result["reported_token_notional"], 4)

    def test_other_condition_and_token_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "another condition"):
            validate([{"conditionId": "x", "asset": "a", "timestamp": 2,
                       "price": .4, "size": 10}], self.selection)
        with self.assertRaisesRegex(ValueError, "selected outcome"):
            validate([{"conditionId": "c", "asset": "x", "timestamp": 2,
                       "price": .4, "size": 10}], self.selection)


if __name__ == "__main__":
    unittest.main()
