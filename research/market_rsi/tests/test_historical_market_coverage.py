import unittest
import pyarrow as pa

from historical_market_coverage import Coverage


class MarketCoverageTests(unittest.TestCase):
    start = 1770890400
    slug = 'btc-updown-15m-1770890400'

    def setup_coverage(self):
        return Coverage([{"market_slug": self.slug, "up_token_id": "up", "down_token_id": "down"}])

    def batch(self, assets, seconds=None, bids=None, asks=None):
        n = len(assets)
        return pa.table({"market_slug": [self.slug]*n, "asset_id": assets,
            "ingest_ts_ms": [(self.start+s)*1000 for s in (seconds or [0]*n)],
            "best_bid": bids or [.4]*n, "best_ask": asks or [.6]*n})

    def test_quiet_identical_quotes_preserved_but_event_bins_not_row_count(self):
        c = self.setup_coverage();c.consume(self.batch(['up', 'up', 'down']))
        r = c.result();m = r['markets'][0]
        self.assertEqual(r['rows'], 3)
        self.assertEqual(m['up_seconds_with_event'], 1)
        self.assertEqual(m['seconds_with_two_sided_quotes_for_both_tokens'], 1)
        self.assertFalse(r['continuous_executable_quote_coverage_proven'])

    def test_wrong_token_not_reassigned(self):
        c = self.setup_coverage();c.consume(self.batch(['wrong']))
        m = c.result()['markets'][0]
        self.assertEqual(m['identity_mismatch_rows'], 1)
        self.assertEqual(m['up_seconds_with_event'], 0)

    def test_crossed_quote_not_counted_as_valid(self):
        c = self.setup_coverage();c.consume(self.batch(['up'], bids=[.7], asks=[.6]))
        m = c.result()['markets'][0]
        self.assertEqual(m['crossed_rows'], 1)
        self.assertEqual(m['up_seconds_with_event'], 1)
        self.assertEqual(m['up_seconds_with_two_sided_quote'], 0)

    def test_window_end_exclusive_and_preopen_retained(self):
        c = self.setup_coverage();c.consume(self.batch(['up']*3, seconds=[-1, 899, 900]))
        m = c.result()['markets'][0]
        self.assertEqual(m['rows'], 3)
        self.assertEqual(m['before_nominal_window_rows'], 1)
        self.assertEqual(m['after_nominal_window_rows'], 1)
        self.assertEqual(m['up_seconds_with_event'], 1)

    def test_unknown_market_does_not_use_last_metadata_row(self):
        c = self.setup_coverage();t = self.batch(['up'])
        t = t.set_column(0, 'market_slug', pa.array(['unknown']))
        c.consume(t)
        self.assertEqual(c.result()['unknown_market_rows'], 1)
        self.assertEqual(c.result()['observed_markets'], 0)


if __name__ == '__main__':
    unittest.main()
