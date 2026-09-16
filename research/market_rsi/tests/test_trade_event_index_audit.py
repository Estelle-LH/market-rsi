import tempfile
import unittest
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from audit_tools.audit_trade_event_index import inspect_arrays, reconcile_source


class TradeEventAuditTests(unittest.TestCase):
    def fixture(self):
        t = int(np.datetime64('2026-04-04', 'ms').astype(np.int64))
        a = {'received_ms': np.array([t, t, t+1]), 'event_ms': np.array([t-1, t-2, t]),
             'aggregate_trade_id': np.array([1, 2, 3]), 'price': np.array([2., 3., 4.]),
             'quantity': np.array([3., 4., 5.]), 'reported_quote_volume': np.array([6., 12., 20.]),
             'reported_maker': np.array([0, 1, 0]), 'source_index': np.zeros(3, dtype=np.int16),
             'row_ordinal': np.arange(3), 'quality_bits': np.zeros(3, dtype=np.uint8)}
        return a, ['2026-04-04'], [{'full_source_rows_scanned': 3}]

    def test_ties_and_records_are_retained(self):
        a, dates, sources = self.fixture()
        r = inspect_arrays(a, dates, sources)
        self.assertEqual(r['rows'], 3)
        self.assertEqual(r['recorded_receipt_tie_excess'], 1)

    def test_duplicate_physical_key_invalid_flag_and_date_rejected(self):
        for column, index, value, message in [('row_ordinal', 1, 0, 'physical'),
                ('quality_bits', 0, 1, 'quality'), ('received_ms', 2, 0, 'date')]:
            a, dates, sources = self.fixture()
            a[column][index] = value
            with self.assertRaisesRegex(ValueError, message):
                inspect_arrays(a, dates, sources)

    def test_independent_physical_comparison_catches_value_and_missing_row(self):
        a, dates, _ = self.fixture()
        raw = {'received_at': a['received_ms'], 'trade_time': a['event_ms'],
               'trade_id': a['aggregate_trade_id'], 'price': a['price'].copy(),
               'quantity': a['quantity'], 'quote_volume': a['reported_quote_volume'],
               'is_buyer_maker': a['reported_maker']}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'raw.parquet'
            pq.write_table(pa.table(raw), path, row_group_size=2)
            self.assertEqual(reconcile_source(path, 0, a, dates)['byte_identical_values'], 21)
            a['price'][1] = 7.
            with self.assertRaisesRegex(ValueError, 'byte-identical'):
                reconcile_source(path, 0, a, dates)
            a['price'][1] = 3.
            with self.assertRaisesRegex(ValueError, 'physical row'):
                reconcile_source(path, 0, {k: v[:2] for k, v in a.items()}, dates)

    def test_nan_product_has_both_price_and_amount_flags(self):
        a, dates, sources = self.fixture()
        a['price'][0] = np.nan
        a['quality_bits'][0] = 5
        r = inspect_arrays(a, dates, sources)
        self.assertEqual(r['quality_counts']['invalid_price_or_quantity'], 1)
        self.assertEqual(r['quality_counts']['invalid_quote_amount'], 1)


if __name__ == '__main__':
    unittest.main()
