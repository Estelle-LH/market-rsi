import copy
import unittest

import numpy as np

import test_historical_grid_panel as fixtures
from historical_feature_inputs import current_inputs, input_names, project_rows, source_fields
from historical_grid_panel import panel_from_rows
from historical_phase_annotations import annotate


class CurrentInputTests(unittest.TestCase):
    def setUp(self):
        self.plan, self.rows = fixtures.GridPanelLoaderTests().fixture()
        self.plan['context_streams'] = ['binance_candles_1s', 'binance_trades']
        for row in self.rows:
            when = row['decision_ms']
            for stream, values in {
                'binance_trades': {'trade_price': 60000., 'trade_quantity': .1},
                'binance_candles_1s': {'open_price': 60000., 'high_price': 60010.,
                                     'low_price': 59990., 'close_price': 60002.}
            }.items():
                row['observations'][stream] = {'reason': 'recorded_source_only_not_execution_proof',
                    'values': values, 'available_ms': when-100, 'max_source_age_ms': 200, 'sources': []}

    def project(self):
        side = [annotate(row) for row in self.rows]
        panel, ids, _ = panel_from_rows(self.rows, side, self.plan, len(self.rows))
        return project_rows(self.rows, side, self.plan, panel, ids)

    def test_no_targets_no_alias_no_mutation_and_quiet_rows_retained(self):
        before = copy.deepcopy(self.rows)
        values, names, _ = self.project()
        self.assertEqual(values.shape[0], 3)
        self.assertFalse(any('target' in n or 'label' in n for n in names))
        self.assertNotIn('binance_trades.midpoint', names)
        self.assertNotIn('binance_trades.signed_flow', names)
        self.assertEqual(values[0, names.index('quiet_since_previous_grid_tick')], 1)
        np.testing.assert_allclose(values[:, names.index('polymarket_ticks_ms.spread')], .2)
        self.assertEqual(self.rows, before)

    def test_unknown_and_conflicting_values_remain_nan(self):
        self.rows[1]['observations']['binance_trades'] = {
            'values': {}, 'reason': 'conflicting_same_receipt_timestamp_values', 'sources': []}
        values, names, _ = self.project()
        self.assertTrue(np.isnan(values[1, names.index('binance_trades.trade_price')]))
        self.assertEqual(values[1, names.index('binance_trades.ambiguous_same_receipt')], 1)
        self.assertEqual(values.shape[0], 3)

    def test_future_context_rejected(self):
        self.rows[0]['observations']['binance_trades']['available_ms'] = self.rows[0]['decision_ms']+1
        with self.assertRaisesRegex(ValueError, 'future'):
            self.project()

    def test_recent_receipt_cannot_refresh_old_event(self):
        self.rows[0]['observations']['binance_trades']['max_source_age_ms'] = 300001
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.project()

    def test_unrequested_stream_or_field_rejected(self):
        self.rows[0]['observations']['binance_trades']['values']['signed_flow'] = 1
        with self.assertRaisesRegex(ValueError, 'exact admitted'):
            self.project()
        with self.assertRaisesRegex(ValueError, 'no alias'):
            source_fields('invented_order_book')

    def test_labels_cannot_enter_cache(self):
        self.rows[0]['target'] = .4
        with self.assertRaisesRegex(ValueError, 'unlabelled'):
            self.project()

    def test_row_order_and_truncation_blocked(self):
        side = [annotate(row) for row in self.rows]
        panel, ids, _ = panel_from_rows(self.rows, side, self.plan, 3)
        with self.assertRaisesRegex(ValueError, 'panel order'):
            project_rows(self.rows[::-1], side[::-1], self.plan, panel, ids)
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            project_rows(self.rows[:1], side[:1], self.plan, panel, ids)

    def test_later_observation_cannot_change_earlier_input(self):
        before = current_inputs(self.rows[0], annotate(self.rows[0]), self.plan)
        self.rows[2]['observations']['binance_trades']['values']['trade_price'] = 999999
        after = current_inputs(self.rows[0], annotate(self.rows[0]), self.plan)
        self.assertEqual(before, after)

    def test_unknown_is_not_zero_filled(self):
        self.rows[0]['observations']['polymarket_ticks_ms'] = {
            'values': {}, 'reason': 'no_visible_observation', 'sources': []}
        values, names, _ = self.project()
        self.assertTrue(np.isnan(values[0, names.index('polymarket_ticks_ms.midpoint_from_reported_bbo')]))
        self.assertTrue(np.isnan(values[0, names.index('polymarket_ticks_ms.spread')]))
        self.assertEqual(values[0, names.index('polymarket_ticks_ms.missing')], 1)


if __name__ == '__main__':
    unittest.main()
