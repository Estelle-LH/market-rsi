import copy
import json
import unittest
from quote_source.test_reconstruct import delta,snap,T
from message_clock_origin import MessageClockProfile,difference_bucket


class MessageClockTests(unittest.TestCase):
    def run_profile(self,rows):
        p=MessageClockProfile(wrapper_day_start_ms=T//86400000*86400000)
        for i,row in enumerate(rows,1):p.consume(json.dumps(row).encode(),i)
        return p.summary()

    def test_old_rest_snapshot_following_fresh_ws_attributed(self):
        a=delta();b=snap(t=T+1);b['src']='rest';b['m']['timestamp']=str(T-10*86400000)
        c=delta(t=T+2);s=self.run_profile([a,b,c])
        self.assertEqual(s['source_regression_transition_counts'],{'price_change -> rest_snapshot':1})
        self.assertEqual(s['within_kind_source_regressions'],{})
        self.assertEqual(s['wrapper_minus_source_numeric_difference']['rest_snapshot'],{'>86400000ms':1})
        self.assertFalse(s['latency_measured']);self.assertEqual(s['quote_rows_deleted'],0)

    def test_genuine_within_ws_regression_stays_visible(self):
        a,b=delta(),delta(t=T+1);b['m']['timestamp']=str(T-1)
        s=self.run_profile([a,b]);self.assertEqual(s['within_kind_source_regressions'],{'price_change':1})

    def test_duplicate_asset_inner_updates_counted_not_collapsed(self):
        r=delta();r['m']['price_changes'].append(copy.deepcopy(r['m']['price_changes'][0]))
        s=self.run_profile([r]);self.assertEqual(s['quote_event_counts_by_kind']['price_change']['quote_events'],2)
        self.assertEqual(s['entities'],1)

    def test_missing_source_not_invented(self):
        r=delta();del r['m']['timestamp'];s=self.run_profile([r])
        self.assertEqual(s['quote_event_counts_by_kind']['price_change']['invalid_source_timestamp'],1)
        self.assertEqual(s['min_source_ms_by_kind'],{})

    def test_disallowed_wrapper_day_refused(self):
        with self.assertRaisesRegex(ValueError,'outside allowed'):self.run_profile([delta(t=T+2*86400000)])

    def test_trade_counted_but_not_quote_event(self):
        r=snap(t=T);r['m']['event_type']='last_trade_price';s=self.run_profile([r])
        self.assertEqual(s['message_counts'],{'last_trade_price':1});self.assertEqual(s['entities'],0)

    def test_multiple_messages_source_time_vs_wrapper(self):
        r=delta();m=copy.deepcopy(r['m']);m['timestamp']=str(T+1);r['m']=[r['m'],m]
        s=self.run_profile([r]);self.assertEqual(s['wrapper_minus_source_numeric_difference']['price_change'],{'zero':1,'negative':1})
        self.assertFalse(s['clock_semantics_attested'])

    def test_no_prices_or_ids_in_output(self):
        r=delta();r['m']['price_changes'][0]['asset_id']='private-example-token'
        text=json.dumps(self.run_profile([r]));self.assertNotIn('private-example-token',text);self.assertNotIn('best_bid',text)

    def test_bounds(self):
        self.assertEqual([difference_bucket(x) for x in [-1,0,1000,60000,3600000,86400000,86400001]],
            ['negative','zero','1..1000ms','1001..60000ms','60001..3600000ms','3600001..86400000ms','>86400000ms'])


if __name__=='__main__':unittest.main()
