"""No provider/network/Native/scorer or production-ledger writes."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import json
from pathlib import Path
import tempfile
import earnings_population_coevolution as policy
import earnings_population_clean_slate as clean
import earnings_population_runtime as runtime
import earnings_population_company_batch as batch
from supervisor_harness import capacity_feedback_engine as engine


class ContinuousPolicyTests(unittest.TestCase):
    def test_direct_authority_and_no_round_or_group_count_ceiling(self):
        direct=engine.read(policy.AUTHORITY)
        for n in (8,9,10,100,1000):
            self.assertTrue(policy.authorized(direct,policy.AUTHORITY,n))
            self.assertEqual(clean.followup_plan(n),policy.PLAN)
            value=dict(clean_slate_policy=clean.POLICY,clean_learning_round=n,sources={policy.PLAN:{}})
            self.assertTrue(clean.enabled(value));self.assertTrue(clean.second_round(value))
            self.assertIn(policy.PLAN,runtime.source_paths(clean_slate=True,clean_followup=n))
    def test_missing_bound_plan_bool_float_and_old_markers_fail(self):
        for n in (True,8.0,-1,0):
            self.assertFalse(policy.continuous_round(n))
            with self.assertRaises(ValueError):runtime.source_paths(clean_slate=True,clean_followup=n)
        with self.assertRaises(ValueError):clean.enabled(dict(clean_slate_policy=clean.POLICY,clean_learning_round=8,sources={}))
    def test_immutable_authority_rejects_scope_or_budget_mutation(self):
        for field,value in [('candidate_count_limit',3),('heldout_access',True),('failed_paid_retry_authorized',True),('max_concurrent_companies',9)]:
            direct=engine.read(policy.AUTHORITY);direct[field]=value
            self.assertFalse(policy.authorized(direct,policy.AUTHORITY,8))
        bad=dict(policy.AUTHORITY,sha256='0'*64)
        self.assertFalse(policy.authorized(engine.read(policy.AUTHORITY),bad,8))
    def test_actual_existing_costs_not_reset_and_pending_counts(self):
        self.assertEqual(policy.decision(291214887300,0,5000000000,meaningful_next=True),'CONTINUE')
        self.assertEqual(policy.decision(383000000000,0,5000000000,meaningful_next=True),'STOP_ORIGINAL_BUDGET_INSUFFICIENT')
        self.assertEqual(policy.decision(382000000000,1000000000,5000000000,meaningful_next=True),'STOP_ORIGINAL_BUDGET_INSUFFICIENT')
        self.assertEqual(policy.decision(386000000000,0,227840000,meaningful_next=True),'CONTINUE')
    def test_loss_rejection_archiving_or_three_attempts_is_not_stagnation(self):
        for reason in ('prediction_loss','Review_rejection','group3of3','publication_pending'):
            with self.assertRaises(ValueError):policy.decision(291214887300,0,5000000000,meaningful_next=False,stagnation=dict(reason=reason))
        self.assertEqual(policy.decision(291214887300,0,5000000000,meaningful_next=True,stagnation=dict(group3of3=True)),'CONTINUE')
    def test_all_six_real_evidence_bindings_required_for_learning_stop(self):
        keys=engine.read(policy.AUTHORITY)['learning_stagnation_requires']
        evidence={k:policy.AUTHORITY for k in keys}
        with self.assertRaises(ValueError):policy.decision(291214887300,0,5000000000,meaningful_next=False,stagnation=evidence)
        def saved(b):
            if b.startswith('iteration'):return json.dumps(dict(logical_round=int(b[-1]),comparison=dict(scored=25))).encode()
            return json.dumps(dict(schema='edgar25_learning_stagnation_evidence_v1',section=b,
                finding='Synthetic negative trajectory fixture, not actual research',completed_iteration_reports=['iteration6','iteration7'],budget_feasible_meaningful_next=False)).encode()
        with patch.object(policy.e,'checked',side_effect=saved):
            self.assertEqual(policy.decision(291214887300,0,227840000,meaningful_next=False,stagnation={k:k for k in keys}),'STOP_EVIDENCE_SUPPORTED_LEARNING_STAGNATION')
        for key in keys:
            missing=deepcopy(evidence);missing.pop(key)
            with self.assertRaises(ValueError):policy.decision(291214887300,0,5000000000,meaningful_next=False,stagnation=missing)
    def test_route_one_fresh_proposal_no_automatic_retry_no_99_id_ceiling(self):
        with patch.object(policy.e,'strict_json',return_value=dict(logical_round=8,proposal_id='edgar-population-20261016-89')),patch.object(policy.e.REPO.__class__,'read_bytes',return_value=b'{}'):
            policy.route('edgar-population-20261016-89',8,False,False)
            policy.route('edgar-population-20261016-100',8,True,False)
            for ident,frozen,repair in [('89',True,False),('90',False,False),('89',False,True)]:
                with self.assertRaises(ValueError):policy.route('edgar-population-20261016-'+ident,8,frozen,repair)
    def test_historical_finite_authorities_not_rewritten(self):
        old=engine.read(clean.STABLE03A_NEXT_AUTHORITY)
        self.assertEqual(old['max_new_candidates'],3)
        self.assertTrue(clean._followup_authorized(old,clean.STABLE03A_NEXT_AUTHORITY,7))
        self.assertFalse(clean._followup_authorized(old,clean.STABLE03A_NEXT_AUTHORITY,8))

    def test_actual_round8_origin_full125_latest_and_parent_not_reinitialized(self):
        bound=engine.pin(policy.e.REPO/policy.PLAN)
        original=policy.e.checked
        with patch.object(policy.e,'checked',side_effect=lambda b:json.dumps(historical_plan()).encode() if b==bound else original(b)):
            origin=clean.round2_origin(dict(clean_learning_round=8,sources={policy.PLAN:bound}))
        feedback=engine.read(origin['public_feedback'])
        self.assertEqual(origin['parent']['id'],origin['original_candidate']['id'])
        self.assertTrue(origin['parent']['id'].startswith('03a87b'))
        self.assertEqual(sum(len(r['targets']) for r in feedback['rows']),125)
        self.assertEqual(sum(len(r['targets']) for r in feedback['adopted_parent']['rows']),125)
        self.assertEqual(feedback['company_equal_mean'],3.02)
        self.assertEqual(origin['prior_mean'],3.14)
        self.assertEqual(feedback['actual_R_diagnostic']['coverage']['histories_sufficient'],0)
        old=engine.read(origin['carried_population'])
        with patch('earnings_population.initialize',side_effect=AssertionError('Do not reset the existing pool')):
            carried=clean.scaffold(dict(forecaster=engine.pin(policy.e.REPO/'tools/edgar_forecast_openai.py')),origin)
        self.assertEqual(carried,old)
        self.assertEqual(carried['history'],old['history'])

    def test_higher_incumbent_retained_without_changing_group_code_parent(self):
        import test_earnings_population_clean_round5 as previous
        case=previous.NextComparisonTests();case.setUp();self.addCleanup(case.doCleanups)
        case.descriptor['learning_round']=8
        origin=engine.read(case.descriptor['parent_basis'])
        origin.update(incumbent_mean=3.18,incumbent_descriptor=dict(path='best-complete',sha256='b'*64))
        case.descriptor['parent_basis']=engine.save(case.root/'continuous-origin.json',origin)
        case.set_improved_companies(4)
        result=clean.compare(case.descriptor_binding,case.windows)
        self.assertEqual(result['candidate_mean'],3.16)
        self.assertEqual(result['parent_mean'],3.14)
        self.assertEqual(result['selection_threshold'],3.18)
        self.assertEqual(result['decision'],'RETAIN_ADOPTED_PARENT')
        self.assertEqual(result['selection_incumbent_descriptor'],origin['incumbent_descriptor'])
        self.assertTrue(result['next_mutation_allowed'])


import test_earnings_population_clean_round5 as previous

def historical_plan():
    """Keep the old round8 regression independent of current prospective plan."""
    value=json.loads((policy.e.REPO/policy.PLAN).read_bytes())
    value.update(logical_round=8,proposal_id='edgar-population-20261016-90',
        origin=engine.pin(clean.training.ROOT/'TRAIN25-CLEAN-ROUND8-ORIGIN-V5.json'),
        group_parent_id='03a87b7b84629aed9dc5fc738b3f2be42e7c49fda8aba346718d8e7359ca67da',group_parent_mean=3.14)
    value.pop('frontier_expansion',None)
    return value

def current_sources():
    if not hasattr(current_sources,'binding'):
        current_sources.temporary=tempfile.TemporaryDirectory()
        current_sources.binding=engine.save(Path(current_sources.temporary.name).resolve()/'round8-plan.json',historical_plan())
    return {policy.PLAN:current_sources.binding}

class ContinuousRollingProcessTests(previous.NextPendingProcessTests):
    def resize_queue(self,n):
        super().resize_queue(n)
        self.value.update(clean_learning_round=8,sources=current_sources());self.store.value=deepcopy(self.value)

class ContinuousPendingArithmeticTests(previous.NextPendingArithmeticTests):
    def setUp(self):
        super().setUp()
        self.value.update(clean_learning_round=8,sources=current_sources());self.store.value=deepcopy(self.value)

class ContinuousSlotProjectionTests(previous.NextSlotProjectionTests):
    def resize(self,n):
        super().resize(n);self.value.update(clean_learning_round=8,sources=current_sources())
    def test_cross_company_or_changed_parent_resources_are_rejected(self):
        for key,other in [('source_commit','b'*40),('root',str(self.root/'other')),('cutoff_utc','2027-01-01T00:00:00Z'),
                ('slots',self.slots[:-1]),('limits',dict(self.limits,wall_seconds=1801)),('rates',dict(self.rates,effort='high'))]:
            with self.subTest(key=key),self.assertRaises(ValueError):batch.company_forecast_context(self.value,dict(self.parent,**{key:other}),self.ids[0],self.slots[0])
        with self.assertRaises(ValueError):batch.company_forecast_context(self.value,self.parent,self.ids[0],self.slots[1])
        for marker in (True,8.0,9):
            with self.assertRaises(ValueError):batch.company_forecast_context(dict(self.value,clean_learning_round=marker),self.parent,self.ids[0],self.slots[0])

class ContinuousWindowYieldTests(previous.NextWindowYieldTests):
    def enable_yield(self):
        super().enable_yield();self.value.update(clean_learning_round=8,sources=current_sources());self.store.value=deepcopy(self.value)


if __name__=='__main__':unittest.main()
