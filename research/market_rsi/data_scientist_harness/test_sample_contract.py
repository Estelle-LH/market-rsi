import copy
import unittest
from data_scientist_harness.sample_contract import Samples,validate,quote,probe,SCHEMA
from data_scientist_harness.source_study_canary import fixture_samples
from data_scientist_harness.broker import validate_shape


def policy():
    c=fixture_samples();c['temporal'].update(horizon_ms=60,endpoint_tolerance_ms=59)
    c['feature'].update(lookback_ms=60,lookup_tolerance_ms=59,max_gap_ms=60)
    c['label_max_gap_ms']=60;return c


def rows(items):
    return [{'key':[i,0,0],'entity':'s','clock_domain':'ws','source_kind':'price_change',
        'time_ms':t,'valid':v is not None,'value':v} for i,(t,v) in enumerate(items)]


def kernel(r,c=None):return Samples(r,policy() if c is None else c,entity='s',clock_domain='ws',max_rows=1000)


class SampleContractTests(unittest.TestCase):
    def test_all_explicit_fields_and_no_default(self):
        c=policy();validate_shape(c,SCHEMA);validate(c)
        for name in c:
            broken=copy.deepcopy(c);del broken[name]
            with self.assertRaises(ValueError):validate(broken)

    def test_ambiguous_or_extra_prose_not_executable(self):
        c=policy();c['coverage']['near']='somewhat'
        with self.assertRaises(ValueError):validate(c)
        c=policy();c['coverage']['mode']='ws_shot_gap'
        with self.assertRaises(ValueError):validate(c)

    def test_bad_types_not_coerced(self):
        for v in (True,'60',60.5,None):
            c=policy();c['feature']['lookback_ms']=v
            with self.assertRaises(ValueError):validate(c)

    def test_unsafe_or_unattested_domain_mixture_rejected(self):
        c=policy();c['quote_rules']['rest_snapshot']='book_levels'
        with self.assertRaisesRegex(ValueError,'cannot share'):validate(c)
        c['temporal']['clock']='wrapper_ms';validate(c) # Declaration only, not attestation.

    def test_empty_source_rejected(self):
        c=policy();c['quote_rules']={k:'exclude' for k in c['quote_rules']}
        with self.assertRaises(ValueError):validate(c)

    def test_unsafe_temporal_flags_rejected(self):
        for key,val in (('missing_endpoint','zero'),('label_origin','group_time'),('invalid_quote','carry_last_valid')):
            c=policy();c['temporal'][key]=val
            with self.assertRaises(ValueError):validate(c)

    def test_date_only_cutoff_and_fill_rejected(self):
        for key,val in (('train_cutoff','date_only'),('check_cutoff','date_only'),('tail_closure','date_cutoff'),('unavailable','zero')):
            c=policy();c[key]=val
            with self.assertRaises(ValueError):validate(c)

    def test_disabled_grid_has_no_hidden_parameters(self):
        c=policy();c['coverage']['slot_ms']=10
        with self.assertRaises(ValueError):validate(c)

    def test_grid_cost_bounded_before_loop(self):
        c=policy();c['feature']['lookback_ms']=86400000
        c['coverage']={'mode':'explicit_backward_slots','slot_ms':1,'tolerance_ms':0,'minimum_coverage_per_mille':1000}
        with self.assertRaisesRegex(ValueError,'1024'):validate(c)

    def test_direct_fields_never_fallback_to_book(self):
        p={'bids':[{'price':'.2','size':'1'}],'asks':[{'price':'.4','size':'1'}]}
        c=policy();c['quote_rules']['book']='direct_bbo'
        self.assertFalse(quote('book',p,c['quote_rules'])['valid'])
        c['quote_rules']['book']='book_levels'
        self.assertEqual(quote('book',p,c['quote_rules'])['value'],.3)

    def test_book_best_levels_no_sort_assumption_and_zero_size(self):
        p={'bids':[{'price':'.9','size':'0'},{'price':'.1','size':'2'},{'price':'.3','size':'1'}],
            'asks':[{'price':'.8','size':'1'},{'price':'.5','size':'1'}]}
        self.assertEqual(quote('book',p,policy()['quote_rules'])['value'],.4)

    def test_missing_empty_crossed_and_nan_quotes_invalid(self):
        for payload in ({},{'best_bid':'NaN','best_ask':'.4'},{'best_bid':'.5','best_ask':'.4'},
                        {'best_bid':True,'best_ask':1},{'best_bid':-.1,'best_ask':.4}):
            q=quote('price_change',payload,policy()['quote_rules'])
            self.assertTrue(q['included']);self.assertFalse(q['valid']);self.assertIsNone(q['value'])
        self.assertFalse(quote('book',{'bids':[],'asks':[]},policy()['quote_rules'])['valid'])

    def test_excluded_quote_is_countable_not_value(self):
        q=quote('rest_snapshot',{'best_bid':'.1','best_ask':'.2'},policy()['quote_rules'])
        self.assertFalse(q['included']);self.assertIsNone(q['value'])

    def test_window_edges_and_count_kind_change_explicitly(self):
        r=rows([(0,.2),(30,None),(60,.3)]);c=policy()
        self.assertEqual(kernel(r,c).feature_at(2)['window_observations'],3)
        c['feature'].update(window_edges='right',count_observations='valid_quotes')
        self.assertEqual(kernel(r,c).feature_at(2)['reason'],'insufficient_window_observations')
        c['feature']['minimum_observations']=1
        self.assertAlmostEqual(kernel(r,c).feature_at(2)['feature'],.1)

    def test_slot_coverage_uses_last_past_validity_no_backward_skip(self):
        r=rows([(0,.2),(30,None),(60,.3)]);c=policy()
        c['coverage']={'mode':'explicit_backward_slots','slot_ms':30,'tolerance_ms':30,'minimum_coverage_per_mille':1000}
        f=kernel(r,c).feature_at(2);self.assertEqual((f['covered_slots'],f['coverage_slots']),(2,3))
        self.assertEqual(f['reason'],'insufficient_slot_coverage')
        c['coverage']['minimum_coverage_per_mille']=666
        self.assertTrue(kernel(r,c).feature_at(2)['available'])

    def test_future_mutation_and_prefix_invariance(self):
        r=rows([(0,.2),(30,.3),(60,.4),(60,.9),(120,.2),(121,.3)])
        f=kernel(r).feature_at(2);self.assertEqual(f,kernel(r[:3]).feature_at(2))
        for x in r[3:]:x['value']=.99
        self.assertEqual(f,kernel(r).feature_at(2))

    def test_exact_endpoint_without_close_unavailable(self):
        k=kernel(rows([(0,.2),(60,.3),(120,.4)]))
        self.assertEqual(k.label_at(1,cutoff_ms=10000)['reason'],'unbounded_tail')

    def test_label_cutoff_is_strict_at_real_maturity(self):
        k=kernel(rows([(0,.2),(60,.3),(120,.4),(125,.5)]))
        self.assertEqual(k.label_at(1,cutoff_ms=125)['reason'],'label_not_mature_before_cutoff')
        y=k.label_at(1,cutoff_ms=126);self.assertTrue(y['available']);self.assertEqual(y['label_available_after_ms'],125)
        with self.assertRaises(ValueError):k.label_at(1,cutoff_ms=True)

    def test_invalid_endpoint_not_skipped(self):
        k=kernel(rows([(0,.2),(60,.3),(119,.4),(120,None),(121,.5)]))
        self.assertEqual(k.label_at(1,cutoff_ms=122)['reason'],'invalid_endpoint_quote')

    def test_fresh_equal_zero_vs_tail(self):
        k=kernel(rows([(0,.2),(60,.3),(120,.3),(121,.4)]))
        self.assertEqual(k.label_at(1,cutoff_ms=122)['label'],0)
        self.assertIsNone(k.label_at(3,cutoff_ms=999)['label'])

    def test_label_gap_and_explicit_disable(self):
        r=rows([(0,.2),(60,.3),(120,.4),(121,.5)]);c=policy();c['label_max_gap_ms']=59
        self.assertEqual(kernel(r,c).label_at(1,cutoff_ms=122)['reason'],'label_gap_exceeded')
        c['label_max_gap_ms']=0;self.assertTrue(kernel(r,c).label_at(1,cutoff_ms=122)['available'])

    def test_forward_endpoint_supported(self):
        c=policy();c['temporal'].update(endpoint_rule='forward_asof',endpoint_tolerance_ms=5)
        k=kernel(rows([(0,.2),(60,.3),(119,.4),(125,.5)]),c)
        self.assertAlmostEqual(k.label_at(1,cutoff_ms=126)['label'],.2)

    def test_ties_and_scoped_entity_are_not_reordered(self):
        c=policy();c['temporal']['decision_rule']='after_timestamp_group'
        r=rows([(0,.2),(0,.3),(60,.4),(60,.5),(120,.6),(121,.7)])
        result=kernel(r,c).materialize(cutoff_ms=200)
        self.assertEqual([x['decision_key'][0] for x in result],[2,4,5])
        r[2]['time_ms']=-1
        with self.assertRaises(ValueError):kernel(r,c)

    def test_samples_do_not_grant_source_admission(self):
        r=kernel(rows([(0,.2),(60,.3),(120,.4),(121,.5)])).materialize(cutoff_ms=122)
        self.assertTrue(any(x['numerically_available'] for x in r));self.assertTrue(all(not x['source_admitted'] for x in r))

    def test_probe_is_parameter_bound_not_policy_selection(self):
        for direction in ('backward_asof','forward_asof'):
            for decision in ('after_each_record','after_timestamp_group'):
                c=policy();c['temporal'].update(endpoint_rule=direction,decision_rule=decision)
                v=probe(c);self.assertTrue(v['checks_passed']);self.assertEqual(v['contract'],c)
                self.assertFalse(v['source_admitted']);self.assertEqual(v['fits'],0)


if __name__=='__main__':unittest.main()
