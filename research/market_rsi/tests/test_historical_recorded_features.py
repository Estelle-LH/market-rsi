import unittest

import numpy as np

import historical_feature_composition as old
from historical_recorded_features import derive, feature_engine_sha256, validate_feature
from historical_trade_windows import RecordedTradeWindows, SOURCE


class RecordedFeatureTests(unittest.TestCase):
    def setUp(self):
        self.t = int(np.datetime64('2026-04-04', 'ms').astype(np.int64))
        self.entity = np.array([0, 1, 0, 1]); self.times = self.t+np.array([20, 20, 70, 70])
        self.values = np.array([[1.], [-1.], [0.], [1.]])
        self.primitive = {'name': 'role', 'source': 'role', 'transform': 'identity',
                          'lookback_ms': 0, 'minimum_observations': 1, 'minimum_window_coverage': 1}
        self.window = {'name': 'flow', 'source': SOURCE, 'statistic': 'maker0_minus_maker1_quantity',
                       'window_ms': 20, 'minimum_records': 1, 'maximum_recorded_gap_ms': 20}
        times = self.t+np.array([0, 10, 10, 20])
        self.engine = RecordedTradeWindows({'received_ms': times, 'event_ms': times-1,
            'quantity': np.array([1., 2., 3., 5.]), 'reported_quote_volume': np.array([10., 20., 30., 50.]),
            'reported_maker': np.array([0, 0, 1, 0]), 'quality_bits': np.zeros(4, dtype=np.uint8)}, ['2026-04-04'])

    def test_legacy_outputs_and_hashes_unchanged(self):
        for spec in [self.primitive, {'name': 'square', 'operator': 'product', 'operands': [self.primitive]*2}]:
            kwargs = dict(spec=spec, cadence_ms=10)
            a = derive(self.entity, self.times, self.values, ['role'], **kwargs)
            b = old.derive(self.entity, self.times, self.values, ['role'], **kwargs)
            for k in ('values', 'available', 'observations_used', 'feature_available_ms'):
                self.assertEqual(a[k].tobytes(), b[k].tobytes())
            self.assertEqual(feature_engine_sha256(spec), old.feature_engine_sha256(spec))

    def test_recorded_leaf_and_mixed_composition_preserve_missing(self):
        spec = {'name': 'chosen', 'operator': 'product', 'operands': [self.primitive, self.window]}
        r = derive(self.entity, self.times, self.values, ['role'], spec=spec, cadence_ms=10, recorded_events=self.engine)
        np.testing.assert_allclose(r['values'], [4., -4., np.nan, np.nan], equal_nan=True)
        self.assertFalse(r['future_labels_used'])
        self.assertEqual(len(feature_engine_sha256(spec)), 64)

    def test_missing_attachment_and_hidden_spec_fail(self):
        with self.assertRaisesRegex(ValueError, 'not attached'):
            derive(self.entity, self.times, self.values, ['role'], spec=self.window, cadence_ms=10)
        with self.assertRaises(ValueError): validate_feature(self.window | {'secret': 1}, ['role'], 10)
        spec = self.window
        for i in range(4): spec = {'name': 'too-deep', 'operator': 'sum', 'operands': [spec, self.primitive]}
        with self.assertRaises(ValueError): validate_feature(spec, ['role'], 10)


if __name__ == '__main__': unittest.main()
