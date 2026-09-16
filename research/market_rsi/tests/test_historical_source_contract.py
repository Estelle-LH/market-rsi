import copy
import unittest

from historical_source_contract import (CLOCK_ASSUMPTION, contract, physical_reference,
    project, require_causal_feature, latest_reported_midpoint)


class HistoricalSourceContractTests(unittest.TestCase):
    now = 1770890400000

    def item(self, stream="polymarket_ticks_ms", day="2026-02-12"):
        return {"path": f"unified/{stream}/date={day}/part-000001.parquet", "lfs_sha256": "a" * 64}

    def pm(self, **changes):
        row = {"id": 1, "market_slug": "m", "asset_id": "a", "event_type": "price_change",
               "source_ts_ms": self.now, "ingest_ts_ms": self.now + 100,
               "price": .1, "size": 3., "best_bid": .4, "best_ask": .6}
        row.update(changes)
        return row

    def projected(self, ordinal=0, **changes):
        return project(self.pm(**changes), self.item(), ordinal, metadata={"m": {"a"}})

    def value(self, record, feature, when=None, age=2000):
        return require_causal_feature(record, feature, self.now+1000 if when is None else when,
                                      max_age_ms=age, clock_assumption=CLOCK_ASSUMPTION)

    def midpoint(self, records):
        return latest_reported_midpoint(records, ["m", "a"], self.now+1000,
                                        max_age_ms=2000, clock_assumption=CLOCK_ASSUMPTION)

    def test_physical_identity_never_uses_repeated_synthetic_id(self):
        a = physical_reference(self.item(), 0)
        b = physical_reference(self.item(day="2026-02-13"), 0)
        c = physical_reference(self.item(), 1)
        self.assertEqual(len({x["physical_row_id"] for x in (a,b,c)}), 3)

    def test_unsafe_reference_rejected(self):
        item = self.item();item['path'] = '/absolute/file.parquet'
        with self.assertRaises(ValueError):physical_reference(item, 0)
        with self.assertRaises(ValueError):physical_reference(self.item(), -1)

    def test_level_price_is_not_midpoint_or_trade(self):
        record = self.projected()
        self.assertEqual(self.value(record, 'reported_level_price'), .1)
        self.assertEqual(self.value(record, 'midpoint_from_reported_bbo'), .5)
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            self.value(record, 'trade_price')

    def test_original_timestamp_not_rewritten_from_filename(self):
        row = self.pm();before = copy.deepcopy(row)
        record = project(row, self.item(day="2026-03-01"), 0, metadata={"m": {"a"}})
        self.assertEqual(record['event_utc_date'], '2026-02-12')
        self.assertEqual(record['source_event_ms'], self.now)
        self.assertEqual(row, before)

    def test_identity_mismatch_not_relabelled(self):
        record = self.projected(asset_id='wrong')
        self.assertEqual(record['entity'], ['m','wrong'])
        with self.assertRaisesRegex(ValueError, 'flagged'):
            self.value(record, 'reported_bid')

    def test_crossed_quote_has_no_usable_midpoint(self):
        record = self.projected(best_bid=.7)
        self.assertNotIn('midpoint_from_reported_bbo', record['values'])
        self.assertIsNone(self.midpoint([record])['value'])

    def test_future_arrival_is_not_visible_even_if_source_time_is_earlier(self):
        record = self.projected(ingest_ts_ms=self.now+5000)
        with self.assertRaisesRegex(ValueError, 'not yet available'):
            self.value(record, 'reported_bid')
        self.assertEqual(self.midpoint([record])['reason'], 'no_visible_quote')

    def test_staleness_is_explicit(self):
        with self.assertRaisesRegex(ValueError, 'staleness'):
            self.value(self.projected(), 'reported_bid', age=50)

    def test_clock_assumption_cannot_be_omitted(self):
        with self.assertRaisesRegex(ValueError, 'assumption'):
            require_causal_feature(self.projected(), 'reported_bid', self.now+1000,
                                    max_age_ms=2000, clock_assumption='exchange_truth')

    def test_binance_trade_sample_is_not_midpoint(self):
        row = {'id': 1, 'source_ts_ms': self.now, 'trade_time_ms': self.now,
               'ingest_ts_ms': self.now+100, 'price': 50000., 'volume': .1}
        record = project(row, self.item('binance_ticks_ms'), 0)
        self.assertEqual(self.value(record, 'trade_price'), 50000.)
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            self.value(record, 'midpoint_from_reported_bbo')

    def candle(self, created):
        row = {'candle_start': self.now, 'candle_end': self.now+59999, 'created_at': created,
               'open_price': 100., 'high_price': 102., 'low_price': 99., 'close_price': 101.}
        return project(row, self.item('binance_candles_1m'), 0)

    def test_backfilled_close_not_available_at_candle_start(self):
        record = self.candle(self.now+86400000)
        with self.assertRaisesRegex(ValueError, 'not yet available'):
            self.value(record, 'close_price', when=self.now+60000)

    def test_partial_candle_stays_invalid_even_after_close(self):
        record = self.candle(self.now+1000)
        self.assertIn('candle_recorded_before_final_close', record['quality_flags'])
        with self.assertRaisesRegex(ValueError, 'flagged'):
            self.value(record, 'close_price', when=self.now+61000)

    def test_invalid_latest_quote_does_not_revive_older_good_quote(self):
        good = self.projected()
        bad = self.projected(ordinal=1, ingest_ts_ms=self.now+200, best_bid=.8)
        self.assertIsNone(self.midpoint([good,bad])['value'])

    def test_conflicting_same_time_quotes_have_no_invented_order(self):
        a, b = self.projected(), self.projected(ordinal=1, best_bid=.2)
        self.assertEqual(self.midpoint([b,a])['reason'], 'conflicting_same_receipt_timestamp_quotes')
        self.assertIsNone(self.midpoint([a,b])['value'])

    def test_identical_same_time_quotes_can_agree_without_claiming_exchange_order(self):
        a, b = self.projected(), self.projected(ordinal=1)
        result = self.midpoint([a,b])
        self.assertEqual(result['value'], .5)
        self.assertEqual(len(result['sources']), 2)
        self.assertFalse(a['training_admitted'])
        self.assertFalse(contract()['automatic_training_admission'])


if __name__ == '__main__':
    unittest.main()
