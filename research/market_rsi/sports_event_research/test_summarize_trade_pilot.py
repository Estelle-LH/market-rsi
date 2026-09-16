import unittest

from sports_event_research.summarize_trade_pilot import summarize


class SummarizeTradePilotTests(unittest.TestCase):
    def test_weighted_coverage_and_change(self):
        trades = [{"selection_sha256": "a", "canonical_game": {"split_role": "market_train"},
                   "possibly_truncated_at_20000": False, "scientific_score": False,
                   "frozen_window": {"trades": 3, "distinct_timestamps": 2}}]
        alignments = [{"selection_sha256": "a", "scientific_score": False,
                       "summary": {"plays": 4, "covered_30s": 2, "coverage_30s": .5,
                                   "mean_absolute_change_30s": .1,
                                   "covered_60s": 4, "coverage_60s": 1,
                                   "mean_absolute_change_60s": .2,
                                   "covered_300s": 4, "coverage_300s": 1,
                                   "mean_absolute_change_300s": .3}}]
        result = summarize(trades, alignments)
        self.assertEqual(result["window_trades"], 3)
        self.assertEqual(result["horizons"]["30s"]["coverage"], .5)
        self.assertAlmostEqual(result["horizons"]["60s"]["play_weighted_mean_absolute_price_change"], .2)

    def test_rejects_nontrain_or_truncated(self):
        trades = [{"selection_sha256": "a", "canonical_game": {"split_role": "sealed_final"},
                   "possibly_truncated_at_20000": False, "scientific_score": False,
                   "frozen_window": {"trades": 0, "distinct_timestamps": 0}}]
        with self.assertRaisesRegex(ValueError, "non-Train"):
            summarize(trades, [{"selection_sha256": "a", "scientific_score": False, "summary": {}}])


if __name__ == "__main__":
    unittest.main()
