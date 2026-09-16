import copy
import json
import unittest
from quote_source.test_reconstruct import delta, T
from source_clock_profile import SourceProfile, gap_bucket


class SourceClockTests(unittest.TestCase):
    def profile(self, records):
        p=SourceProfile()
        for i,r in enumerate(records,1): p.consume(json.dumps(r).encode()+b'\n',i)
        return p

    def test_unchanged_quotes_not_deleted(self):
        p=self.profile([delta(t=T),delta(t=T),delta(t=T+1)])
        s=p.summary()
        self.assertEqual(s['population']['totals']['counts']['equal_mid_pairs'],2)
        self.assertEqual(s['source_clock_totals']['consecutive_equal_source_ms_run_sizes'],{'1':1,'2':1})
        self.assertFalse(s['zero_change_rows_filtered'])

    def test_source_clock_not_capture_clock(self):
        a,b=delta(t=T),delta(t=T+1000)
        b['m']['timestamp']=str(T)
        s=self.profile([a,b]).summary()
        self.assertEqual(s['source_clock_totals']['adjacent_gap_histogram'],{'0ms':1})
        self.assertEqual(s['population']['totals']['counts']['pair_gap_1..1000ms'],1)

    def test_missing_and_regression_not_sorted_or_bridged(self):
        rows=[delta(t=T+i) for i in range(5)]
        for r,t in zip(rows,[T+10,T+5,None,T+9,T+11]): r['m']['timestamp']=str(t) if t else None
        s=self.profile(rows).summary()['source_clock_totals']
        self.assertEqual(s['adjacent_gap_histogram'],{'regression':1,'1..1000ms':1})
        self.assertEqual(s['counts']['below_prior_highwater_rows'],2)
        self.assertEqual(s['counts']['missing_or_invalid_source_ms'],1)

    def test_multiple_entities_and_inner_events_have_unique_keys(self):
        r=delta(); b=copy.deepcopy(r['m']['price_changes'][0]);b['asset_id']='secret-b'
        r['m']['price_changes'] += [b,copy.deepcopy(r['m']['price_changes'][0])]
        p=self.profile([r]);s=p.summary()
        self.assertEqual(len(s['source_clock_entities']),2)
        self.assertEqual(s['source_clock_totals']['counts']['quote_rows'],3)
        self.assertNotIn('secret-b',json.dumps(s))
        self.assertNotIn('"bid":',json.dumps(s))
        self.assertNotIn('"asset_id":',json.dumps(s))

    def test_snapshot_is_nondestructive(self):
        p=self.profile([delta()]);one=p.summary();self.assertEqual(one,p.summary())
        p.consume(json.dumps(delta(t=T+1)).encode(),2)
        self.assertEqual(one['source_clock_totals']['counts']['quote_rows'],1)

    def test_invalid_quote_still_in_clock_population(self):
        s=self.profile([delta(),delta(bid='1.5',t=T+1)]).summary()
        self.assertEqual(s['source_clock_totals']['counts']['quote_rows'],2)
        self.assertEqual(s['population']['totals']['issues']['malformed_source_bbo'],1)
        self.assertFalse(s['labels_computed'])

    def test_bucket_boundaries(self):
        self.assertEqual([gap_bucket(x) for x in [-1,0,1,1000,1001,10000,10001,60000,60001]],
            ['regression','0ms','1..1000ms','1..1000ms','1001..10000ms','1001..10000ms',
             '10001..60000ms','10001..60000ms','>60000ms'])


if __name__=='__main__':unittest.main()
