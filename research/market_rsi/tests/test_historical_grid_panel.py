import copy
from datetime import datetime, timezone
import gzip
import tempfile
from pathlib import Path
import unittest

import numpy as np

from historical_grid_panel import bounded_rows, panel_from_rows
from historical_phase_annotations import annotate
from historical_source_contract import CLOCK_ASSUMPTION
from market_rsi import digest


class GridPanelLoaderTests(unittest.TestCase):
    start=1775260800000

    def fixture(self):
        plan={'clock_assumption':CLOCK_ASSUMPTION,'primary_observation':'pm_reported_bbo',
            'market_time_scope':'observed_arrival_interval','cadence_ms':60000,'max_age_ms':300000,
            'open_train_utc_dates':['2026-04-04']}
        rows=[]
        for index in range(3):
            when=self.start+index*60000
            row={'market_slug':f'btc-updown-15m-{self.start//1000}','asset_id':'up-token',
                'decision_ms':when,'utc_date':datetime.fromtimestamp(when/1000,timezone.utc).date().isoformat(),
                'training_admitted':False,'target':None,'pm_events_since_previous_grid_tick':index,
                'observations':{'polymarket_ticks_ms':{'reason':'recorded_source_only_not_execution_proof',
                    'values':{'reported_bid':.4,'reported_ask':.6,'midpoint_from_reported_bbo':.5},
                    'available_ms':when-100,'max_source_age_ms':200,'sources':[]}}}
            row['row_id']=digest({k:row[k] for k in ['market_slug','asset_id','decision_ms']});rows.append(row)
        return plan,rows

    def load(self,rows,plan=None,side=None,count=None):
        return panel_from_rows(iter(rows),iter(side if side is not None else [annotate(r) for r in rows]),
            plan or self.fixture()[0],len(rows) if count is None else count)

    def test_preserves_population_and_both_source_clocks(self):
        plan,rows=self.fixture();before=copy.deepcopy(rows);panel,ids,summary=self.load(rows,plan)
        self.assertEqual(summary['rows'],3);self.assertEqual(summary['finite_midpoint_rows'],3)
        np.testing.assert_array_equal(panel.quote_age_ms,[200,200,200]);self.assertEqual(rows,before)
        self.assertEqual(ids.tolist(),[r['row_id'] for r in rows])

    def test_missing_quote_not_filled_or_dropped(self):
        _,rows=self.fixture();rows[1]['observations']['polymarket_ticks_ms']={
            'values':{},'reason':'observation exceeds declared staleness','sources':[]}
        panel,_,summary=self.load(rows)
        self.assertEqual(summary['rows'],3);self.assertEqual(summary['finite_midpoint_rows'],2)
        self.assertTrue(np.isnan(panel.midpoint[1]));self.assertTrue(np.isnan(panel.quote_age_ms[1]))

    def test_sidecar_order_mismatch_rejected(self):
        _,rows=self.fixture()
        with self.assertRaisesRegex(ValueError,'annotation'):self.load(rows,side=[annotate(r) for r in reversed(rows)])

    def test_short_sidecar_rejected(self):
        _,rows=self.fixture()
        with self.assertRaises(ValueError):self.load(rows,side=[annotate(rows[0])])

    def test_truncated_both_inputs_rejected(self):
        _,rows=self.fixture()
        with self.assertRaisesRegex(ValueError,'incomplete'):self.load(rows[:2],count=3)

    def test_extra_row_is_not_truncated(self):
        _,rows=self.fixture()
        with self.assertRaisesRegex(ValueError,'never truncate'):self.load(rows,count=2)

    def test_duplicate_or_changed_identity_rejected(self):
        _,rows=self.fixture()
        with self.assertRaisesRegex(ValueError,'identity'):self.load([rows[0],rows[0]])
        rows[0]['asset_id']='different'
        with self.assertRaisesRegex(ValueError,'identity'):self.load(rows)

    def test_date_not_from_filename_or_new_holdout(self):
        plan,rows=self.fixture();plan['open_train_utc_dates']=['2026-04-05']
        with self.assertRaisesRegex(ValueError,'open Train dates'):self.load(rows,plan)

    def test_stale_event_not_refreshed_by_recent_receipt(self):
        _,rows=self.fixture();rows[0]['observations']['polymarket_ticks_ms']['max_source_age_ms']=300001
        with self.assertRaisesRegex(ValueError,'staleness'):self.load(rows)

    def test_midpoint_not_an_arbitrary_price_alias(self):
        _,rows=self.fixture();rows[0]['observations']['polymarket_ticks_ms']['values']['midpoint_from_reported_bbo']=.7
        with self.assertRaisesRegex(ValueError,'co-reported'):self.load(rows)

    def test_existing_target_must_not_enter_source_panel(self):
        _,rows=self.fixture();rows[0]['target']=.1
        with self.assertRaisesRegex(ValueError,'unlabelled'):self.load(rows)

    def test_compression_does_not_bypass_logical_byte_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'rows.gz'
            with gzip.open(path,'wb') as handle:handle.write(b'{"a":1}\n'*10)
            with self.assertRaisesRegex(ValueError,'bounded'):list(bounded_rows(path,10))


if __name__=='__main__':unittest.main()
