import copy
import unittest
from unittest.mock import patch
import capture_cross_forensic as f
import capture_cross_window as w


def fixtures():
    snapshot = {'t': w.CASE_T-1, 'm': {'event_type': 'book', 'asset_id': 'a',
        'bids': [{'price': '.49', 'size': '2'}],
        'asks': [{'price': p, 'size': '2'} for p in ('.50', '.51', '.52')]}}
    rows = [(116000, snapshot, f.digest(snapshot))]
    for ordinal, side, px, size in ((116007, 'BUY', '.51', '2'),
                                   (116008, 'SELL', '.50', '0'), (116009, 'SELL', '.51', '0')):
        r = {'t': w.CASE_T, 'm': {'event_type': 'price_change', 'timestamp': str(w.CASE_T-1),
            'price_changes': [{'asset_id': 'a', 'side': side, 'price': px, 'size': size,
                              'best_bid': '.51', 'best_ask': '.52'}]}}
        rows.append((ordinal, r, f.digest(r)))
    snap = copy.deepcopy(snapshot); snap['t'] = w.CASE_T+4
    snap['m']['bids'].append({'price': '.51', 'size': '2'})
    snap['m']['asks'] = [{'price': '.52', 'size': '2'}]
    rows.append((116011, snap, f.digest(snap)))
    return rows


class WindowTests(unittest.TestCase):
    def run_trace(self, rows, expected=None):
        hashes = expected or {i: h for i, _, h in rows if i in (116007, 116008, 116009)}
        with patch.object(w, 'num', f.num, create=True), patch.object(w, 'status', f.status, create=True), \
             patch.object(w, 'RAW_CASE_HASHES', hashes):
            return w.trace_window(rows, 'a')

    def test_three_distinct_records_with_same_bbo(self):
        result = self.run_trace(fixtures())
        self.assertEqual([s['replay_status'] for s in result['trace']], ['crossed', 'locked', 'uncrossed'])
        self.assertEqual([s['operation'] for s in result['trace']], ['set_absolute_size', 'remove', 'remove'])
        self.assertTrue(result['source_bbo_identical_across_three_records'])
        self.assertTrue(result['source_timestamps_identical'])
        self.assertTrue(result['snapshot_checks'][0]['full_price_size_maps_equal_before_reset'])
        self.assertFalse(result['atomic_exchange_transaction_proven'])

    def test_changed_raw_hash_fails(self):
        with self.assertRaisesRegex(ValueError, 'raw case record changed'):
            self.run_trace(fixtures(), {i: 'wrong' for i in (116007, 116008, 116009)})

    def test_missing_case_fails(self):
        rows = fixtures(); hashes = {i: h for i, _, h in rows if i in (116007, 116008, 116009)}
        with self.assertRaisesRegex(ValueError, 'missing/repeated'):
            self.run_trace([r for r in rows if r[0] != 116008], hashes)

    def test_source_bbo_change_not_hidden_by_timestamp(self):
        rows = fixtures(); rows[2][1]['m']['price_changes'][0]['best_ask'] = '.53'
        rows = [(i, r, f.digest(r)) for i, r, _ in rows]
        result = self.run_trace(rows)
        self.assertFalse(result['source_bbo_identical_across_three_records'])


if __name__ == '__main__': unittest.main()
