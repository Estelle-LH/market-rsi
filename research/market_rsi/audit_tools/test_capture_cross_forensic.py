import copy
import gzip
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import capture_cross_forensic as f

T = 1787270400000


def snapshot(src=None):
    r = {'t': T, 'm': {'event_type': 'book', 'asset_id': 'a', 'market': 'm',
        'bids': [{'price': '.4', 'size': '2'}],
        'asks': [{'price': '.6', 'size': '2'}, {'price': '.8', 'size': '2'}]}}
    if src: r['src'] = src
    return r


def delta():
    return {'t': T+1, 'm': {'event_type': 'price_change', 'market': 'm', 'price_changes': [
        {'asset_id': 'a', 'side': 'BUY', 'price': '.7', 'size': '2', 'best_bid': '.7', 'best_ask': '.8'},
        {'asset_id': 'a', 'side': 'SELL', 'price': '.6', 'size': '0', 'best_bid': '.7', 'best_ask': '.8'}]}}


def meta(records):
    return [{'ordinal': i+1, 'record': r, 'raw_record_sha256': f.digest(r)} for i, r in enumerate(records)]


class ForensicTests(unittest.TestCase):
    def test_first_crossing_not_largest_or_latest(self):
        head = 'ts_utc,ts_ms,venue,market,outcome,bid,bid_size,ask,ask_size,mid,spread\n'
        rows = [f'2026-08-21T00:00:00Z,{T},polymarket,m,a,.4,2,.6,2,.5,.2\n',
                f'2026-08-21T00:00:00.001Z,{T+1},polymarket,m,a,.7,2,.6,2,.65,-.1\n',
                f'2026-08-21T00:00:00.002Z,{T+2},polymarket,m,a,.9,2,.4,2,.65,-.5\n']
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'test.gz'
            with gzip.open(p, 'wt') as out: out.write(head+''.join(rows))
            with patch.object(f, 'CSV_HASH', f.file_hash(p)):
                target, receipt = f.locate_csv(p)
        self.assertEqual(target['ordinal'], 2)
        self.assertEqual(receipt['case']['spread_probability_bps'], '-1000.0')
        self.assertNotIn('outcome', str(receipt))

    def test_strict_cross_not_locked(self):
        self.assertEqual(f.status('.5', '.5'), 'locked')
        self.assertEqual(f.status('.6', '.5'), 'crossed')
        self.assertEqual(f.status(None, '.5'), 'one_sided')
        with self.assertRaises(ValueError): f.status('NaN', '.5')

    def test_identity_filter_preserves_original(self):
        r = delta(); r['m']['price_changes'].insert(1, {'asset_id': 'other'})
        before = copy.deepcopy(r)
        result = f.target_record(r, 'a', 'm')
        self.assertEqual(len(result['m']['price_changes']), 2)
        self.assertEqual(r, before)
        with self.assertRaisesRegex(ValueError, 'disagreement'): f.target_record(r, 'a', 'wrong')

    def test_date_checked_before_interpreting_prices(self):
        r = {'t': 1787875200000, 'm': {'bad': 'schema'}}
        with self.assertRaisesRegex(ValueError, 'date'): f.target_record(r, 'a', 'm')

    def test_partial_update_can_cross_then_complete_uncrossed(self):
        states, _, _ = f.replay(meta([snapshot(), delta()]), True)
        self.assertEqual([s['status'] for s in states], ['uncrossed', 'crossed', 'uncrossed', 'uncrossed'])
        self.assertEqual(states[1]['source_bbo_status'], 'uncrossed')
        self.assertFalse(states[1]['replay_matches_source_bbo'])
        self.assertTrue(states[2]['replay_matches_source_bbo'])

    def test_ignored_snapshot_remains_unanchored(self):
        states, _, counts = f.replay(meta([snapshot(), delta()]), False)
        self.assertEqual(counts['ws_snapshot'], 1)
        self.assertTrue(all(s['status'] == 'unanchored' for s in states))

    def test_snapshot_reset_exposes_extra_level(self):
        partial = delta(); partial['m']['price_changes'] = partial['m']['price_changes'][:1]
        replacement = snapshot(); replacement['t'] = T+2
        replacement['m']['bids'] = [{'price': '.7', 'size': '2'}]
        replacement['m']['asks'] = [{'price': '.8', 'size': '2'}]
        _, checks, _ = f.replay(meta([snapshot(), partial, replacement]), True)
        self.assertEqual(checks[-1]['old_status'], 'crossed')
        self.assertEqual(checks[-1]['new_status'], 'uncrossed')
        self.assertEqual(checks[-1]['extra_levels'], 2)

    def test_public_summary_does_not_export_identity_or_raw_price(self):
        states, _, _ = f.replay(meta([snapshot(), delta()]), True)
        summary = f.public_state(states[1], {'bid': '.7', 'ask': '.6'})
        self.assertTrue(summary['replay_matches_csv_price_pair'])
        self.assertFalse(summary['source_matches_csv_price_pair'])
        self.assertNotIn('source_bid', summary)
        self.assertNotIn('bid', summary)

    def test_bad_etl_source_not_executed(self):
        with self.assertRaisesRegex(ValueError, 'ETL source changed'):
            f.legacy_rows([], b'raise RuntimeError("do not execute")')


if __name__ == '__main__': unittest.main()
