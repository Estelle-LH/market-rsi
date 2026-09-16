import unittest

import numpy as np

from historical_trade_windows import RecordedTradeWindows, SOURCE, validate_spec
from audit_tools.canary_trade_windows import direct


class RecordedTradeWindowTests(unittest.TestCase):
    def setUp(self):
        self.t = int(np.datetime64('2026-04-04', 'ms').astype(np.int64))

    def fixture(self):
        receipt = self.t+np.array([0, 10, 10, 20, 30, 40, 100])
        return {'received_ms': receipt, 'event_ms': receipt-1,
                'quantity': np.array([9., 2., 3., 5., 0., 4., 1.]),
                'reported_quote_volume': np.array([90., 20., 30., 50., 0., 40., 10.]),
                'reported_maker': np.array([0, 0, 1, 0, 0, 1, 0]),
                'quality_bits': np.zeros(7, dtype=np.uint8)}

    def spec(self, stat, **kwargs):
        return {'name': 'mechanics-test', 'source': SOURCE, 'statistic': stat, 'window_ms': 20,
                'minimum_records': 1, 'maximum_recorded_gap_ms': 20} | kwargs

    def run_spec(self, stat, offsets, **kwargs):
        engine = RecordedTradeWindows(self.fixture(), ['2026-04-04'])
        return engine.derive(self.t+np.array(offsets), spec=self.spec(stat, **kwargs))

    def test_boundaries_all_ties_and_duplicate_decisions(self):
        r = self.run_spec('quantity_sum', [20, 20, 30])
        np.testing.assert_array_equal(r['values'], [10., 10., 5.])
        np.testing.assert_array_equal(r['observations_used'], [3, 3, 2])
        np.testing.assert_array_equal(r['feature_available_ms'], self.t+np.array([20, 20, 30]))

    def test_each_explicit_statistic(self):
        expected = {'record_count': 3., 'quantity_sum': 10., 'quote_volume_sum': 100.,
                    'recorded_vwap': 10., 'maker0_minus_maker1_quantity': 4.,
                    'maker0_minus_maker1_quote_volume': 40., 'maker_quantity_imbalance': .4,
                    'maker_quote_volume_imbalance': .4}
        for stat, value in expected.items():
            with self.subTest(stat=stat):
                self.assertAlmostEqual(self.run_spec(stat, [20])['values'][0], value)

    def test_future_receipt_values_do_not_change_past(self):
        a = self.fixture()
        prior = RecordedTradeWindows(a, ['2026-04-04']).derive(self.t+np.array([20]), spec=self.spec('quantity_sum'))
        a['quantity'][-1] = 9999999.
        after = RecordedTradeWindows(a, ['2026-04-04']).derive(self.t+np.array([20]), spec=self.spec('quantity_sum'))
        np.testing.assert_array_equal(prior['values'], after['values'])

    def test_empty_and_insufficient_do_not_become_zero(self):
        for r in [self.run_spec('record_count', [70]),
                  self.run_spec('record_count', [20], minimum_records=4)]:
            self.assertTrue(np.isnan(r['values'][0]))
            self.assertEqual(r['reason'][0], 3)

    def test_zero_amount_is_distinct_from_missing_and_zero_denominator(self):
        r = self.run_spec('quantity_sum', [30], window_ms=5, maximum_recorded_gap_ms=5)
        self.assertEqual(r['values'][0], 0.)
        r = self.run_spec('recorded_vwap', [30], window_ms=5, maximum_recorded_gap_ms=5)
        self.assertEqual(r['reason'][0], 6)
        self.assertTrue(np.isnan(r['values'][0]))

    def test_bad_record_or_future_event_invalidates_whole_window(self):
        for change in ('flag', 'event', 'quantity', 'maker'):
            a = self.fixture()
            if change == 'flag': a['quality_bits'][1] = 1
            elif change == 'event': a['event_ms'][1] = self.t+1000
            elif change == 'quantity': a['quantity'][1] = np.nan
            else: a['reported_maker'][1] = 4
            r = RecordedTradeWindows(a, ['2026-04-04']).derive(self.t+np.array([20]), spec=self.spec('quantity_sum'))
            self.assertEqual(r['reason'][0], 5)
            self.assertEqual(r['observations_used'][0], 3)
            self.assertTrue(np.isnan(r['values'][0]))

    def test_unopened_date_and_beginning_not_bridged(self):
        a = self.fixture()
        a['received_ms'] += 1000
        a['event_ms'] += 1000
        engine = RecordedTradeWindows(a, ['2026-04-04'])
        r = engine.derive(self.t+np.array([10, 1010, 86_400_010]), spec=self.spec('record_count'))
        np.testing.assert_array_equal(r['reason'], [1, 2, 1])

    def test_internal_and_end_gap_guards(self):
        r = self.run_spec('quantity_sum', [100, 55], maximum_recorded_gap_ms=10)
        np.testing.assert_array_equal(r['reason'], [4, 4])
        r = self.run_spec('record_count', [100], window_ms=100, maximum_recorded_gap_ms=20)
        self.assertEqual(r['reason'][0], 4)

    def test_explicit_parameters_and_schema_enforced(self):
        for kwargs in ({'window_ms': 0}, {'minimum_records': 0}, {'maximum_recorded_gap_ms': 21}, {'window_ms': True}):
            with self.assertRaises(ValueError): validate_spec(self.spec('quantity_sum', **kwargs))
        with self.assertRaises(ValueError): validate_spec(self.spec('quantity_sum') | {'hidden': 1})
        a = self.fixture(); a['received_ms'] = a['received_ms'][::-1]
        with self.assertRaises(ValueError): RecordedTradeWindows(a, ['2026-04-04'])

    def test_direct_reference_matches_all_windows_and_statistic_masks(self):
        from historical_trade_windows import STATISTICS
        a = self.fixture(); engine = RecordedTradeWindows(a, ['2026-04-04'])
        decisions = self.t+np.arange(0, 160, 3)
        for stat in STATISTICS:
            spec = self.spec(stat)
            got = engine.derive(decisions, spec=spec)
            for i, point in enumerate(decisions):
                value, reason, count = direct(a, ['2026-04-04'], int(point), spec)
                self.assertEqual(reason, got['reason'][i])
                self.assertEqual(count, got['observations_used'][i])
                if reason: self.assertTrue(np.isnan(got['values'][i]))
                else: self.assertAlmostEqual(value, got['values'][i])


if __name__ == '__main__':
    unittest.main()
