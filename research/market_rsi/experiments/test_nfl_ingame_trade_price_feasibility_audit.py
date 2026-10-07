import unittest

from experiments.nfl_ingame_trade_price_feasibility_audit import count_window, market_tokens


class TradePriceFeasibilityAuditTests(unittest.TestCase):
    def test_strict_endpoint_and_ties(self):
        self.assertEqual(count_window([69, 70, 70, 99, 100], 100), 3)

    def test_empty_window_is_not_forward_filled(self):
        self.assertEqual(count_window([1, 200], 100), 0)

    def test_orientation_uses_raw_market_not_reordered_receipt(self):
        raw = {"markets": [{"id": "1", "conditionId": "c", "clobTokenIds": '["b", "a"]'}]}
        receipt = {"market_id": "1", "condition_id": "c", "tokens": ["a", "b"]}
        self.assertEqual(market_tokens(raw, receipt), ["b", "a"])

    def test_mismatched_token_set_rejected(self):
        raw = {"markets": [{"id": "1", "conditionId": "c", "clobTokenIds": '["b", "z"]'}]}
        with self.assertRaises(ValueError):
            market_tokens(raw, {"market_id": "1", "condition_id": "c", "tokens": ["a", "b"]})

    def test_wrong_condition_rejected(self):
        raw = {"markets": [{"id": "1", "conditionId": "wrong", "clobTokenIds": '["b", "a"]'}]}
        with self.assertRaises(ValueError):
            market_tokens(raw, {"market_id": "1", "condition_id": "c", "tokens": ["a", "b"]})


if __name__ == "__main__":
    unittest.main()
