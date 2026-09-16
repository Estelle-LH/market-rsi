import copy
import json
import random
import unittest

from data_scientist_harness.sample_contract import Samples
from typed_raw_profile import Profile,canonical_kernel,sample_at,DAY

T=1787270400000
FIXTURE_CONTRACT={
    'check_cutoff':'label_maturity_strictly_before_cutoff','claim':'recorded_observation_only',
    'clock_regression':'reject_segment',
    'coverage':{'minimum_coverage_per_mille':0,'mode':'anchor_and_gap_only','slot_ms':0,'tolerance_ms':0},
    'feature':{'count_observations':'valid_quotes','day_boundary':'purge','lookback_ms':60000,
        'lookup_tolerance_ms':59999,'max_gap_ms':60000,'minimum_observations':2,'window_edges':'both'},
    'label_max_gap_ms':0,'quote_rules':{'book':'exclude','price_change':'direct_bbo','rest_snapshot':'exclude'},
    'tail_closure':'strictly_later_observed_record',
    'temporal':{'claim':'recorded_observation_only','clock':'source_ms','decision_rule':'after_timestamp_group',
        'endpoint_rule':'backward_asof','endpoint_tolerance_ms':59999,'horizon_ms':60000,
        'invalid_quote':'invalidate','label_origin':'decision_time','missing_endpoint':'unavailable'},
    'train_cutoff':'label_maturity_strictly_before_cutoff','unavailable':'count_do_not_zero'}


def contract():return copy.deepcopy(FIXTURE_CONTRACT)


def message(t,asset='fixture-token',bid='.2',ask='.3',market='fixture-market'):
    return {'t':t,'src':'ws','m':{'event_type':'price_change','timestamp':str(t),'market':market,
        'price_changes':[{'asset_id':asset,'best_bid':bid,'best_ask':ask}]}}


class TypedProfileTests(unittest.TestCase):
    def test_exact_contract_only(self):
        c=contract();c['feature']['minimum_observations']=3
        with self.assertRaises(ValueError):Profile(c,T)

    def test_parity_all_decisions_seed23(self):
        rng=random.Random(23);c=contract()
        for case in range(100):
            t=T;rows=[]
            for i in range(40):
                t+=rng.choice([0,0,1,1000,30000,60000,120000]);valid=rng.random()>.2
                rows.append({'key':[0,i,0,0],'entity':'one-series','clock_domain':'declared-source-ms',
                    'source_kind':'price_change','time_ms':t,'valid':valid,
                    'value':rng.choice([.2,.2,.21,.8]) if valid else None})
            k=canonical_kernel(rows,c);published=Samples(rows,c,entity='one-series',
                clock_domain='declared-source-ms',max_rows=200000)
            prefix=[0]
            for row in rows:prefix.append(prefix[-1]+int(row['valid']))
            for i in range(len(rows)):
                a,b=sample_at(k,i,c,prefix,T+DAY)
                self.assertEqual(a,published.feature_at(i),(case,i))
                self.assertEqual(b,published.label_at(i,cutoff_ms=T+DAY),(case,i))

    def profile(self,records,**limits):
        p=Profile(contract(),T,**limits)
        for i,r in enumerate(records,1):p.consume(json.dumps(r).encode(),i)
        return p,p.summary()

    def test_zero_and_tail_separate(self):
        p,r=self.profile([message(T+t) for t in [0,30000,60000,120000,120001]])
        self.assertEqual(r['counts']['numerically_available'],1)
        self.assertEqual(r['counts']['fresh_equal_zero'],1)
        # 30s has a closed label but lacks its past anchor; only the final2 decisions have no future closure.
        self.assertEqual(r['label_reason_counts']['unbounded_tail'],2)
        self.assertEqual(r['paired_label_span_ms_counts'],{'60000':1})
        self.assertNotIn('fixture-token',json.dumps(r));self.assertNotIn('fixture-market',json.dumps(r))
        self.assertFalse(r['source_admitted']);self.assertEqual(r['fits'],0)

    def test_invalid_last_endpoint_not_replaced(self):
        records=[message(T+t) for t in [0,30000,60000,119999,120000,120001]]
        records[4]['m']['price_changes'][0]['best_ask']='invalid'
        _,r=self.profile(records)
        self.assertGreater(r['label_reason_counts'].get('invalid_endpoint_quote',0),0)

    def test_regression_rejects_whole_segment_not_sorted(self):
        _,r=self.profile([message(T+t) for t in [0,30000,20000,60000,120000,120001]])
        self.assertEqual(r['counts']['rejected_segments'],1)
        self.assertEqual(r['counts'].get('numerically_available',0),0)
        self.assertEqual(r['counts']['observations_in_rejected_segments'],6)

    def test_identity_discontinuity_fail_closed(self):
        with self.assertRaises(ValueError):self.profile([message(T),message(T+1,market='different')])

    def test_source_outside_day_is_not_silently_purged(self):
        r=message(T);r['m']['timestamp']=str(T-1)
        with self.assertRaises(ValueError):self.profile([r])

    def test_missing_identity_is_not_dropped(self):
        r=message(T);del r['m']['price_changes'][0]['asset_id']
        with self.assertRaises(ValueError):self.profile([r])

    def test_other_kinds_excluded_before_timestamp(self):
        r=message(T);r['m']['event_type']='book';r['m']['timestamp']='invalid'
        _,v=self.profile([r]);self.assertEqual(v['counts']['excluded_kind_messages'],1)

    def test_resource_limit_not_partial_success(self):
        with self.assertRaises(ValueError):self.profile([message(T),message(T+1)],max_total_rows=1)
        with self.assertRaises(ValueError):self.profile([message(T),message(T+1,'other')],max_entities=1)

    def test_same_ms_inner_order_preserved(self):
        r=message(T);r['m']['price_changes'].append({'asset_id':'fixture-token','best_bid':'.8','best_ask':'.9'})
        p,v=self.profile([r,message(T+1)])
        rows=next(iter(p.entities.values())).rows()
        self.assertEqual(rows[0]['key'],[0,1,0,0]);self.assertEqual(rows[1]['key'],[0,1,0,1])
        self.assertEqual(v['observed_gap_ms_counts']['0'],1)
        self.assertEqual(v['counts']['eligible_decisions'],1)

    def test_day_wrapper_and_ordinal_fail_closed(self):
        p=Profile(contract(),T);p.consume(json.dumps(message(T)).encode(),1)
        with self.assertRaises(ValueError):p.consume(json.dumps(message(T+1)).encode(),1)
        with self.assertRaises(ValueError):self.profile([message(T+DAY)])

    def test_field_presence_does_not_make_invalid_quote_valid(self):
        _,v=self.profile([message(T,bid='.8',ask='.2')])
        self.assertEqual(v['counts']['both_quote_fields_present'],1)
        self.assertEqual(v['counts']['valid_quotes'],0)
        self.assertEqual(v['counts']['invalid_quotes'],1)

    def test_day_end_cutoff_equivalent_to_day_purge(self):
        rows=[{'key':[0,i,0,0],'entity':'one-series','clock_domain':'declared-source-ms',
            'source_kind':'price_change','time_ms':T+v,'valid':True,'value':.25}
            for i,v in enumerate([DAY-180001,DAY-120001,DAY-60001,DAY-1])]
        p=Samples(rows,contract(),entity='one-series',clock_domain='declared-source-ms',max_rows=20)
        for i in range(len(rows)):
            self.assertEqual(p.label_at(i,cutoff_ms=T+DAY),p.label_at(i,cutoff_ms=T+2*DAY))


if __name__=='__main__':unittest.main()
