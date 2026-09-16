import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from ds_harness_core.quality_checks import (
    DataSpec, FeatureRule, TimeSeriesSpec, batch_hash, check_data_level,
    check_time_series_level,
)
from ds_harness_core.research_gate import (
    PanelInput, QualityGateError, guarded_research, persist_quality_report,
    quality_report,
)


def panel(values=None, *, times=None, sessions=None, entities=None, rule=None):
    x = np.asarray(values if values is not None else np.arange(40.)/10., dtype=float)
    if x.ndim == 1:
        x = x[:, None]
    n, p = x.shape
    ts = np.arange(n, dtype='int64')*10 + 100 if times is None else np.asarray(times, dtype='int64')
    entity = np.array(['a']*n) if entities is None else np.array(entities)
    session = np.array(['s1']*n) if sessions is None else np.array(sessions)
    names = tuple(f'f{i}' for i in range(p))
    order = np.arange(n, dtype='int64')
    b = dict(schema='feature_batch_v1', row_id=np.array([f'r{i}' for i in range(n)]),
        entity_id=entity, session_id=session, decision_ns=ts, event_ordinal=order,
        feature_names=list(names), values=x, available=np.ones(x.shape, dtype=bool),
        feature_available_ns=np.repeat(ts[:, None], p, axis=1),
        feature_available_ordinal=np.repeat(order[:, None], p, axis=1))
    spec = DataSpec(feature_names=names, units={name:'unitless' for name in names},
        expected_groups=tuple(dict.fromkeys(zip(map(str, entity), map(str, session)))),
        source_hashes={'fixture':'a'*64}, clock_domain='fixture_ns', session_timezone='explicit_session',
        rules={name:rule or FeatureRule(rationale='synthetic regression fixture') for name in names},
        implementation_sha256='b'*64)
    observed = {k:copy.deepcopy(getattr(spec, k)) for k in
                ('units','source_hashes','clock_domain','session_timezone','implementation_sha256')}
    return PanelInput(b, spec, observed, np.full(x.shape, '', dtype='U32'))


SERIES = TimeSeriesSpec(max_gap_ns=100, rationale='fixture cadence known')


def evidence(p):
    return dict(implementation_sha256=p.spec.implementation_sha256, **{
        name:dict(status='PASS', receipt_sha256='c'*64)
        for name in ('source_units_clock','kernel_future_mutation','preprocessing_parity')})


def kwargs(raw=None, transformed=None):
    raw = panel() if raw is None else raw
    transformed = copy.deepcopy(raw) if transformed is None else transformed
    return dict(raw=raw, transformed=transformed, time_series=SERIES,
        lineage={n:[n] for n in transformed.batch['feature_names']},
        adapter_evidence=dict(raw=evidence(raw), transformed=evidence(transformed)))


def data(p):
    return check_data_level(p.batch, p.spec, p.observed, p.unavailable_reasons)


def time_series(p, spec=SERIES):
    return check_time_series_level(p.batch, p.spec, spec)


class DataLevelTests(unittest.TestCase):
    def test_clean_panel_passes_without_mutation(self):
        p=panel(); before=batch_hash(p.batch)
        self.assertEqual(data(p)['status'], 'PASS')
        self.assertEqual(batch_hash(p.batch), before)

    def test_inf_raw_counts_retained_and_failure(self):
        p=panel(); p.batch['values'][1,0]=np.inf
        report=data(p)
        self.assertEqual(report['status'],'FAIL')
        self.assertEqual(report['raw_numeric_counts'][0]['positive_inf'],1)
        self.assertEqual(report['raw_partition_counts'][0]['positive_inf'],1)
        self.assertTrue(np.isinf(p.batch['values'][1,0]))

    def test_nan_cannot_be_available(self):
        p=panel(); p.batch['values'][1,0]=np.nan
        self.assertEqual(data(p)['status'],'FAIL')

    def test_explained_bounded_warmup_is_not_filled(self):
        p=panel(rule=FeatureRule(rationale='known one-row warmup', min_available_fraction=.9, max_missing_fraction=.1))
        p=replace(p,spec=replace(p.spec,allowed_unavailable_reasons=('warmup',)))
        p.batch['values'][0,0]=np.nan; p.batch['available'][0,0]=False
        p.batch['feature_available_ns'][0,0]=-1; p.batch['feature_available_ordinal'][0,0]=-1
        p.unavailable_reasons[0,0]='warmup'
        self.assertEqual(data(p)['status'],'PASS')
        self.assertTrue(np.isnan(p.batch['values'][0,0]))

    def test_unexplained_or_excessive_warmup_fails(self):
        p=panel(); p.batch['available'][:10,0]=False
        p.unavailable_reasons[:10,0]='warmup'
        codes={i['code'] for i in data(p)['issues']}
        self.assertIn('unexplained_unavailable',codes); self.assertIn('available_coverage',codes)

    def test_duplicate_and_order_checks(self):
        for key in ('row_id','decision_ns'):
            p=panel(); p.batch[key][3]=p.batch[key][0]
            self.assertEqual(data(p)['status'],'FAIL')

    def test_equal_timestamp_distinct_ordinals_valid(self):
        p=panel(times=np.repeat(np.arange(20),2)*10+100)
        self.assertEqual(data(p)['status'],'PASS')

    def test_future_timestamp_and_ordinal_fail(self):
        for key in ('feature_available_ns','feature_available_ordinal'):
            p=panel(); p.batch[key][2,0]+=1
            self.assertEqual(data(p)['status'],'FAIL')

    def test_missing_expected_coverage(self):
        p=panel(); p=replace(p,spec=replace(p.spec,expected_groups=(('a','s1'),('a','s2'))))
        self.assertIn('coverage',{i['code'] for i in data(p)['issues']})

    def test_unit_clock_source_version_metadata_mismatch(self):
        for key in ('units','clock_domain','session_timezone','source_hashes','implementation_sha256'):
            p=panel(); p.observed[key]='wrong'
            self.assertEqual(data(p)['status'],'FAIL')

    def test_bounds_zero_and_constant(self):
        for p in [panel(np.zeros(40)), panel(rule=FeatureRule(rationale='bounded',upper=1.)),
                  panel(np.r_[np.zeros(20),np.arange(20.)],rule=FeatureRule(rationale='sparse limit',max_zero_fraction=.1))]:
            self.assertEqual(data(p)['status'],'FAIL')
        self.assertEqual(data(panel(np.zeros(40),rule=FeatureRule(rationale='explicitly expected constant',allow_constant=True)))['status'],'PASS')

    def test_invalid_configuration_fails_closed(self):
        p=panel(rule=FeatureRule(rationale='bad',max_missing_fraction=float('nan')))
        self.assertEqual(data(p)['status'],'FAIL')
        p=panel(); p=replace(p,spec=replace(p.spec,expected_groups=()))
        self.assertEqual(data(p)['status'],'FAIL')

    def test_all_unavailable_is_not_pass(self):
        p=panel(rule=FeatureRule(rationale='empty not acceptable',min_available_fraction=0))
        p=replace(p,spec=replace(p.spec,allowed_unavailable_reasons=('warmup',)))
        p.batch['available'][:]=False; p.unavailable_reasons[:]='warmup'
        self.assertEqual(data(p)['status'],'FAIL')


class TimeSeriesTests(unittest.TestCase):
    def test_textbook_lag1_on_complete_series(self):
        r=time_series(panel([-2.,-1.,0.,1.,2.]))['features'][0]
        self.assertAlmostEqual(r['event_acf'][0]['autocorrelation'],.4)
        self.assertEqual(r['event_acf'][0]['pairs'],4)

    def test_seeded_no_dependence_and_known_dependence(self):
        rng=np.random.default_rng(991)
        white=rng.normal(size=20000); ar=np.zeros(20000)
        for i in range(1,len(ar)): ar[i]=.9*ar[i-1]+white[i]
        a=time_series(panel(white))['features'][0]['event_acf'][0]['autocorrelation']
        b=time_series(panel(ar))['features'][0]['event_acf'][0]['autocorrelation']
        self.assertLess(abs(a),.04); self.assertGreater(b,.86); self.assertLess(b,.94)

    def test_irregular_gaps_not_connected(self):
        p=panel([1.,2.,3.,-4.,-5.,-6.],times=[100,110,120,1000,1010,1020])
        r=time_series(p)
        self.assertEqual(r['status'],'FAIL')
        self.assertEqual(r['features'][0]['adjacent_pairs'],4)
        self.assertEqual(r['features'][0]['sign_flips'],0)
        self.assertEqual(r['features'][0]['event_acf'][1]['pairs'],0)

    def test_permitted_quiet_gap_still_breaks_short_horizon_pairs(self):
        p=panel([1.,2.,3.,-4.,-5.,-6.],times=[100,110,120,1000,1010,1020])
        report=time_series(p,replace(SERIES,max_gap_ns=1000,max_pair_gap_ns=100))
        self.assertEqual(report['status'],'PASS')
        self.assertEqual(report['features'][0]['adjacent_pairs'],4)
        self.assertEqual(report['features'][0]['sign_flips'],0)
        self.assertEqual(report['features'][0]['gaps_excluded_from_pairs'],1)

    def test_unavailable_interruption_is_not_bridged(self):
        p=panel([1.,2.,100000.,-1.,-2.,-3.]); p.batch['available'][2,0]=False
        r=time_series(p)['features'][0]
        self.assertEqual(r['adjacent_pairs'],3); self.assertEqual(r['sign_flips'],0)
        p.batch['values'][2,0]=-1e9
        self.assertEqual(r,time_series(p)['features'][0])

    def test_sessions_not_connected_and_drift_reported(self):
        p=panel([1.,2.,3.,-1.,-2.,-3.],sessions=['s1']*3+['s2']*3,
                rule=FeatureRule(rationale='shift fixture',max_session_shift_iqr=1))
        report=time_series(p)
        self.assertEqual(len(report['features']),2)
        self.assertEqual(sum(r['sign_flips'] for r in report['features']),0)
        self.assertEqual(len(report['cross_session']),1)
        self.assertEqual(report['status'],'FAIL')

    def test_cross_session_scale_shift(self):
        p=panel(np.r_[np.arange(10.),np.arange(10.)*10],sessions=['s1']*10+['s2']*10,
                rule=FeatureRule(rationale='scale regime fixture',max_scale_ratio=2))
        report=time_series(p)
        self.assertAlmostEqual(report['cross_session'][0]['std_ratio'],10.)
        self.assertIn('cross_session_scale',{i['code'] for i in report['issues']})

    def test_flat_and_zero_runs_have_event_and_elapsed_length(self):
        p=panel([1.,0.,0.,0.,2.],times=[100,110,140,150,160],
                rule=FeatureRule(rationale='stale limit',max_flat_run_ns=30))
        report=time_series(p); r=report['features'][0]
        self.assertEqual(r['flat_run'],dict(events=3,elapsed_ns=40))
        self.assertEqual(r['zero_run'],dict(events=3,elapsed_ns=40))
        self.assertEqual(report['status'],'FAIL')

    def test_jumps_and_flip_rate(self):
        p=panel([1.,-1.,1.,-1.,1.],rule=FeatureRule(rationale='jump limit',max_abs_step=1))
        r=time_series(p)
        self.assertEqual(r['status'],'FAIL'); self.assertEqual(r['features'][0]['sign_flip_fraction'],1.)

    def test_time_bins_not_equal_row_count_bins(self):
        p=panel([1.,2.,3.,4.,5.],times=[100,101,102,103,190])
        bins=time_series(p)['features'][0]['elapsed_bins']
        self.assertEqual([b['rows'] for b in bins],[4,0,0,1])

    def test_half_session_shift(self):
        p=panel(np.r_[np.arange(50.),np.arange(50.)+100],
                rule=FeatureRule(rationale='distribution change limit',max_half_shift_iqr=2))
        r=time_series(p)
        self.assertIn('half_session_drift',{i['code'] for i in r['issues']})

    def test_equal_timestamp_not_fabricated_elapsed_time(self):
        p=panel([1.,1.,1.,2.,3.],times=[100,100,100,101,102])
        r=time_series(p)['features'][0]
        self.assertEqual(r['flat_run']['events'],3); self.assertEqual(r['flat_run']['elapsed_ns'],0)

    def test_invalid_time_policy_and_nan_arithmetic(self):
        self.assertEqual(time_series(panel(),replace(SERIES,max_gap_ns=0))['status'],'FAIL')
        self.assertEqual(time_series(panel([1e308,-1e308,1e308,-1e308]))['status'],'FAIL')

    def test_interleaved_entities_never_cross_pairs(self):
        p=panel([1.,-1.,2.,-2.,3.,-3.],entities=['a','b']*3)
        r=time_series(p)
        self.assertEqual(sum(f['sign_flips'] for f in r['features']),0)
        self.assertEqual(sum(f['adjacent_pairs'] for f in r['features']),4)


class BoundaryTests(unittest.TestCase):
    def invoke(self, args, callback=None):
        persisted=[]; calls=[]
        def operation(batch):
            calls.append(True)
            if callback: return callback(batch)
            return float(batch['values'].sum())
        try:
            value=guarded_research(stage='fit',persist=persisted.append,operation=operation,**args)
            return value,persisted,calls
        except QualityGateError as exc:
            return exc,persisted,calls

    def test_real_callback_blocked_by_raw_inf_even_after_fill(self):
        raw=panel(); processed=copy.deepcopy(raw)
        raw.batch['values'][2,0]=np.inf; processed.batch['values'][2,0]=0
        failure,records,calls=self.invoke(kwargs(raw,processed))
        self.assertIsInstance(failure,QualityGateError); self.assertEqual(calls,[])
        self.assertEqual(len(records),1); self.assertEqual(records[0]['status'],'FAIL')

    def test_real_callback_blocked_by_time_series_failure(self):
        p=panel([1.,2.,3.,4.],times=[100,110,120,10000])
        failure,records,calls=self.invoke(kwargs(p))
        self.assertIsInstance(failure,QualityGateError); self.assertEqual(calls,[])

    def test_success_callback_sees_same_readonly_values(self):
        args=kwargs(); original=args['transformed'].batch['values'].copy()
        def operation(batch):
            np.testing.assert_array_equal(batch['values'],original)
            self.assertFalse(batch['values'].flags.writeable)
            return batch['values'].T@batch['values']
        (answer,receipt),records,calls=self.invoke(args,operation)
        np.testing.assert_array_equal(answer,original.T@original)
        self.assertEqual(receipt['status'],'PASS'); self.assertEqual(len(calls),1)
        self.assertTrue(args['transformed'].batch['values'].flags.writeable)

    def test_rechecks_after_previous_pass(self):
        args=kwargs(); self.assertIsInstance(self.invoke(args)[0],tuple)
        args['raw'].batch['values'][0,0]=np.inf
        failure,_,calls=self.invoke(args)
        self.assertIsInstance(failure,QualityGateError); self.assertEqual(calls,[])

    def test_missing_failed_stale_adapter_evidence_blocks(self):
        for mutation in ('missing','failed','stale'):
            args=kwargs()
            if mutation=='missing': args['adapter_evidence']={}
            elif mutation=='failed': args['adapter_evidence']['raw']['kernel_future_mutation']['status']='FAIL'
            else: args['adapter_evidence']['raw']['implementation_sha256']='d'*64
            self.assertEqual(self.invoke(args)[2],[])

    def test_reordered_or_dropped_transformed_rows_block(self):
        for key in ('row_id','decision_ns'):
            args=kwargs(); args['transformed'].batch[key]=args['transformed'].batch[key][::-1].copy()
            self.assertEqual(self.invoke(args)[2],[])

    def test_unavailable_raw_cannot_be_silently_filled_available(self):
        raw=panel(rule=FeatureRule(rationale='warmup allowed',min_available_fraction=.9,max_missing_fraction=.1))
        raw=replace(raw,spec=replace(raw.spec,allowed_unavailable_reasons=('warmup',)))
        transformed=copy.deepcopy(raw)
        raw.batch['available'][0,0]=False; raw.unavailable_reasons[0,0]='warmup'
        self.assertEqual(data(raw)['status'],'PASS')
        failure,_,calls=self.invoke(kwargs(raw,transformed))
        self.assertIsInstance(failure,QualityGateError); self.assertEqual(calls,[])

    def test_explicit_combined_feature_lineage(self):
        raw=panel(np.column_stack([np.arange(40.),np.arange(40.)*2]))
        transformed=panel(np.arange(40.)*3)
        args=kwargs(raw,transformed); args['lineage']={'f0':['f0','f1']}
        self.assertEqual(self.invoke(args)[0][1]['status'],'PASS')

    def test_missing_lineage_or_persistence_blocks(self):
        args=kwargs(); args['lineage']={}
        self.assertEqual(self.invoke(args)[2],[])
        with self.assertRaises(ValueError):
            guarded_research(stage='score',persist=None,operation=lambda _:None,**kwargs())

    def test_transform_cannot_claim_availability_before_parent(self):
        args=kwargs(); args['transformed'].batch['feature_available_ns']-=1
        failure,_,calls=self.invoke(args)
        self.assertIsInstance(failure,QualityGateError); self.assertEqual(calls,[])

    def test_receipt_binds_policy_metadata_and_reasons(self):
        report=quality_report(**kwargs())
        r=report['data_level']['raw']
        self.assertIn('frozen_spec',r); self.assertIn('observed_metadata',r)
        self.assertEqual(len(r['unavailable_reasons_sha256']),64)

    def test_persistence_failure_prevents_callback(self):
        called=[]
        def fail(_): raise OSError('disk failure')
        with self.assertRaises(OSError):
            guarded_research(stage='score',persist=fail,operation=lambda _:called.append(True),**kwargs())
        self.assertEqual(called,[])

    def test_split_receipts_failures_and_no_overwrite(self):
        report=quality_report(**kwargs())
        with tempfile.TemporaryDirectory() as path:
            persist_quality_report(report,path)
            self.assertEqual({p.name for p in Path(path).iterdir()},
                             {'data_check.json','time_series_check.json','quality_gate.json'})
            self.assertEqual(json.loads((Path(path)/'quality_gate.json').read_text())['status'],'PASS')
            with self.assertRaises(FileExistsError): persist_quality_report(report,path)


if __name__=='__main__': unittest.main(verbosity=2)
