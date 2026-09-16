import copy
import unittest
from causal_event_samples import SampleKernel,DAY
from data_scientist_harness.temporal_contract import evaluate,fixtures

C={'clock':'source_ms','decision_rule':'after_timestamp_group','label_origin':'decision_time',
    'horizon_ms':60,'endpoint_rule':'backward_asof','endpoint_tolerance_ms':59,
    'missing_endpoint':'unavailable','invalid_quote':'invalidate','claim':'recorded_observation_only'}
F={'lookback_ms':60,'lookup_tolerance_ms':59,'minimum_observations':2,'max_gap_ms':60,'same_utc_day':True}


def rows(items):
    return [{'key':[i,0,0],'entity':'synthetic','clock_domain':'synthetic-event','source_kind':'ws',
        'time_ms':t,'valid':v is not None,'value':v} for i,(t,v) in enumerate(items)]


def kernel(r):return SampleKernel(r,entity='synthetic',clock_domain='synthetic-event',clock_field='source_ms',allowed_kinds={'ws'},max_rows=10000)


class SampleTests(unittest.TestCase):
    def test_real_lookback_and_future_label_are_separate(self):
        k=kernel(rows([(0,.2),(30,.25),(60,.3),(120,.4),(121,.5)]))
        f=k.feature_at(2,F);y=k.label_at(2,C,same_utc_day=True)
        self.assertAlmostEqual(f['feature'],.1);self.assertAlmostEqual(y['label'],.1)
        self.assertLess(f['anchor_key'],y['decision_key']);self.assertGreater(y['endpoint_key'],y['decision_key'])

    def test_mutating_future_cannot_change_features(self):
        r=rows([(0,.2),(30,.25),(60,.3),(90,.4),(120,.4),(121,.5)])
        a=kernel(r).feature_at(2,F);r[3]['value']=.9;r[4]['value']=.1
        self.assertEqual(a,kernel(r).feature_at(2,F))
        self.assertEqual(a,kernel(r[:3]).feature_at(2,F))

    def test_same_ms_later_value_not_in_prediction(self):
        k=kernel(rows([(0,.2),(60,.3),(60,.8),(120,.4),(121,.5)]))
        self.assertAlmostEqual(k.feature_at(1,F)['feature'],.1)
        self.assertEqual([x['decision_key'] for x in k.materialize(C,F)],[(1,0,0),(3,0,0),(4,0,0)])

    def test_invalid_last_anchor_not_skipped(self):
        k=kernel(rows([(0,.2),(0,None),(60,.3)]))
        self.assertEqual(k.feature_at(2,F)['reason'],'invalid_lookback_quote')

    def test_invalid_last_endpoint_not_skipped(self):
        k=kernel(rows([(0,.2),(60,.3),(119,.4),(120,None),(121,.6)]))
        self.assertEqual(k.label_at(1,C,same_utc_day=True)['reason'],'invalid_endpoint_quote')

    def test_fresh_equal_is_zero_but_missing_tail_is_none(self):
        k=kernel(rows([(0,.2),(60,.3),(120,.3),(121,.5)]))
        self.assertEqual(k.label_at(1,C,same_utc_day=True)['label'],0)
        self.assertIsNone(k.label_at(3,C,same_utc_day=True)['label'])

    def test_no_strictly_later_close_is_unavailable(self):
        k=kernel(rows([(0,.2),(60,.3),(120,.4)]))
        self.assertEqual(k.label_at(1,C,same_utc_day=True)['reason'],'unbounded_tail')

    def test_label_maturity_tracks_closing_observation(self):
        k=kernel(rows([(0,.2),(60,.3),(120,.4),(125,.5)]))
        y=k.label_at(1,C,same_utc_day=True)
        self.assertEqual(y['endpoint_ms'],120);self.assertEqual(y['label_available_after_ms'],125)

    def test_mixed_clock_domains_not_silently_sorted_or_removed(self):
        r=rows([(0,.2),(1,.3)]);r[1]['clock_domain']='rest-snapshot'
        with self.assertRaisesRegex(ValueError,'mixed'):kernel(r)

    def test_clock_regression_refused(self):
        with self.assertRaisesRegex(ValueError,'regression'):kernel(rows([(2,.2),(1,.3)]))

    def test_entity_mixture_refused(self):
        r=rows([(0,.2),(1,.3)]);r[1]['entity']='other'
        with self.assertRaisesRegex(ValueError,'mixed'):kernel(r)

    def test_day_crossing_feature_and_label(self):
        k=kernel(rows([(DAY-60,.2),(DAY,.3),(DAY+60,.4),(DAY+61,.5)]))
        self.assertEqual(k.feature_at(1,F)['reason'],'day_boundary')
        self.assertEqual(k.label_at(0,C,same_utc_day=True)['reason'],'day_boundary')

    def test_gap_and_insufficient_history(self):
        k=kernel(rows([(0,.2),(120,.3)]));self.assertEqual(k.feature_at(1,F)['reason'],'lookback_outside_tolerance')
        k=kernel(rows([(0,.2),(60,.3)]));f={**F,'max_gap_ms':59}
        self.assertEqual(k.feature_at(1,f)['reason'],'lookback_gap_exceeded')

    def test_parity_with_published_probe_for_monotonic_cases(self):
        for name,rr in fixtures(C).items():
            if name=='regression':continue
            r=rows([(x['source_ms'],x['value'] if x['valid'] else None) for x in rr])
            k=kernel(r);actual=k.label_at(2,C,same_utc_day=True);expected=evaluate(rr,C)
            self.assertEqual(actual['available'],expected['available'],name)
            self.assertEqual(actual['label'],expected['label'],name)

    def test_caller_must_choose_supported_kinds(self):
        r=rows([(0,.2)]);r[0]['source_kind']='rest_snapshot'
        with self.assertRaisesRegex(ValueError,'unselected'):kernel(r)

    def test_unsafe_missing_zero_refused(self):
        k=kernel(rows([(0,.2),(60,.3)]))
        with self.assertRaises(ValueError):k.label_at(0,{**C,'missing_endpoint':'zero'},same_utc_day=True)

    def test_clock_field_cannot_silently_change_between_x_and_y(self):
        k=kernel(rows([(0,.2),(60,.3)]))
        with self.assertRaises(ValueError):k.label_at(0,{**C,'clock':'wrapper_ms'},same_utc_day=True)

    def test_input_rows_are_not_retrospectively_mutated(self):
        r=rows([(0,.2),(60,.3),(120,.4),(121,.5)]);k=kernel(r)
        before=k.feature_at(1,F);r[0]['value']=.9;r[0]['key'][0]=999
        self.assertEqual(before,k.feature_at(1,F))

    def test_forward_lookup_and_tolerance(self):
        k=kernel(rows([(0,.2),(60,.3),(119,.4),(125,.5)]))
        c={**C,'endpoint_rule':'forward_asof','endpoint_tolerance_ms':5}
        self.assertAlmostEqual(k.label_at(1,c,same_utc_day=True)['label'],.2)
        self.assertEqual(k.label_at(1,{**c,'endpoint_tolerance_ms':4},same_utc_day=True)['reason'],'endpoint_outside_tolerance')


if __name__=='__main__':unittest.main()
