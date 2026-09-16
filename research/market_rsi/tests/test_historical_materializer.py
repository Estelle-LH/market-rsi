import copy
import unittest
import numpy as np
import pyarrow as pa

from historical_materializer import GridMaterializer, latest_indices, visible_state
from historical_source_contract import CLOCK_ASSUMPTION, project


class MaterializerTests(unittest.TestCase):
    now=1770890400000
    metadata=[{'market_slug':'m','up_token_id':'u','down_token_id':'d'}]

    def plan(self):
        return dict(purpose='diagnostic_learning_pilot',primary_observation='pm_reported_bbo',
            market_time_scope='observed_arrival_interval',clock_assumption=CLOCK_ASSUMPTION,
            open_train_utc_dates=['2026-02-12','2026-02-13'],cadence_ms=1000,max_age_ms=1500,
            context_streams=['binance_trades','binance_candles_1s'],max_materialized_rows=1000)

    def item(self, stream='polymarket_ticks_ms'):
        return {'path':f'unified/{stream}/date=2026-01-01/part-000001.parquet','lfs_sha256':'a'*64}

    def pm(self, ms, asset='u', bid=.4, ask=.6):
        return {'market_slug':'m','asset_id':asset,'id':1,'source_ts_ms':self.now+ms-1,
                'ingest_ts_ms':self.now+ms,'event_type':'price_change','price':.1,'size':2.,
                'best_bid':bid,'best_ask':ask}

    def build(self, rows, batch_size=100000, plan=None):
        m=GridMaterializer(plan or self.plan(),self.metadata)
        for start in range(0,len(rows),batch_size):m.consume(pa.Table.from_pylist(rows[start:start+batch_size]),self.item(),start)
        return m

    def test_latest_ties_vector_reduction(self):
        actual=latest_indices(np.array([1,1,1,1,2]),np.array([0,0,0,1,0]),np.array([9,3,9,1,11]))
        self.assertEqual(set(actual),{0,2,3,4})

    def test_chunk_boundaries_do_not_change_output_or_physical_ordinals(self):
        rows=[self.pm(0),self.pm(1000,ask=.7),self.pm(500),self.pm(1000,ask=.8),self.pm(3000)]
        a=list(self.build(rows).rows());b=list(self.build(rows,2).rows())
        self.assertEqual(a,b)
        at_one=[r for r in a if r['decision_ms']==self.now+1000 and r['asset_id']=='u'][0]
        self.assertEqual(at_one['observations']['polymarket_ticks_ms']['reason'],'conflicting_same_receipt_timestamp_values')

    def test_quiet_grid_rows_and_missing_other_token_remain(self):
        m=self.build([self.pm(0),self.pm(5000)])
        rows=list(m.rows())
        self.assertEqual(len(rows),12)
        quiet=[r for r in rows if r['decision_ms']==self.now+1000 and r['asset_id']=='u'][0]
        self.assertEqual(quiet['pm_events_since_previous_grid_tick'],0)
        self.assertEqual(quiet['observations']['polymarket_ticks_ms']['values']['midpoint_from_reported_bbo'],.5)
        self.assertTrue(all(not r['observations']['polymarket_ticks_ms']['values'] for r in rows if r['asset_id']=='d'))

    def test_invalid_latest_does_not_revive_previous_good_quote(self):
        rows=list(self.build([self.pm(0),self.pm(800,bid=.8),self.pm(2000)]).rows())
        at_one=next(r for r in rows if r['decision_ms']==self.now+1000 and r['asset_id']=='u')
        self.assertFalse(at_one['observations']['polymarket_ticks_ms']['values'])
        self.assertIn('flagged',at_one['observations']['polymarket_ticks_ms']['reason'])

    def test_no_future_data_and_clock_not_from_filename(self):
        rows=list(self.build([self.pm(0),self.pm(1001,ask=.8),self.pm(2000)]).rows())
        at_one=next(r for r in rows if r['decision_ms']==self.now+1000 and r['asset_id']=='u')
        self.assertEqual(at_one['utc_date'],'2026-02-12')
        self.assertEqual(at_one['observations']['polymarket_ticks_ms']['values']['midpoint_from_reported_bbo'],.5)
        self.assertEqual(at_one['pm_events_since_previous_grid_tick'],0)

    def test_row_budget_fails_without_silent_truncation(self):
        plan=self.plan();plan['max_materialized_rows']=5
        m=self.build([self.pm(0),self.pm(5000)],plan=plan)
        with self.assertRaisesRegex(ValueError,'no truncation'):list(m.rows())

    def test_mismatched_asset_stays_raw_not_relabelled(self):
        m=self.build([self.pm(0),self.pm(500,asset='wrong'),self.pm(1000)])
        self.assertEqual(m.summary()['counts']['identity_mismatch_rows'],1)
        self.assertEqual({r['asset_id'] for r in m.rows()},{'u','d'})

    def test_staleness_blocks_but_retains_grid_row(self):
        rows=list(self.build([self.pm(0),self.pm(5000)]).rows())
        stale=next(r for r in rows if r['decision_ms']==self.now+3000 and r['asset_id']=='u')
        self.assertIn('staleness',stale['observations']['polymarket_ticks_ms']['reason'])

    def test_candle_close_and_late_recorded_arrival_both_required(self):
        m=self.build([self.pm(0),self.pm(5000)])
        candle={'candle_start':self.now,'candle_end':self.now+999,'created_at':self.now+2500,
                'open_price':100.,'high_price':103.,'low_price':99.,'close_price':102.}
        m.consume(pa.Table.from_pylist([candle]),self.item('binance_candles_1s'))
        rows=list(m.rows())
        before=next(r for r in rows if r['decision_ms']==self.now+2000)
        self.assertFalse(before['observations']['binance_candles_1s']['values'])
        # Arrived at2500, but the underlying close is already older than the controller age1500 at3000.
        after=next(r for r in rows if r['decision_ms']==self.now+3000)
        self.assertIn('staleness',after['observations']['binance_candles_1s']['reason'])

    def test_reduction_matches_naive_all_rows_reference(self):
        rng=np.random.default_rng(23)
        raw=[self.pm(int(t),asset='u' if i%2 else 'd',bid=.4+(i%3)*.01)
             for i,t in enumerate(rng.integers(0,5000,100))]
        raw += [self.pm(0),self.pm(5000)]
        m=self.build(raw,7)
        projected=[project(r,self.item(),i,metadata={'m':{'u','d'}}) for i,r in enumerate(raw)]
        for r in m.rows():
            available=[p for p in projected if p['entity']==['m',r['asset_id']] and p['recorded_available_ms']<=r['decision_ms']]
            latest=max([p['recorded_available_ms'] for p in available],default=-1)
            selected=[p for p in available if p['recorded_available_ms']==latest]
            expected=visible_state(selected,r['decision_ms'],self.plan(),'polymarket_ticks_ms')
            self.assertEqual(r['observations']['polymarket_ticks_ms']['values'],expected['values'])
            self.assertEqual(r['observations']['polymarket_ticks_ms']['reason'],expected['reason'])
            self.assertEqual({s['physical_row_id'] for s in r['observations']['polymarket_ticks_ms']['sources']},
                             {s['physical_row_id'] for s in expected['sources']})


if __name__=='__main__':unittest.main()
