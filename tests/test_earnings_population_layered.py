"""Saved evidence and synthetic v4 negatives; no models, gates or ledger writes."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import earnings_population as pool
import earnings_population_coevolution as policy
import earnings_population_layered as layered
import earnings_population_additional_budget as budget
from supervisor_harness import capacity_feedback_engine as e

A=policy.training.ROOT

def member(number):
    bound=e.pin(A/f'TRAIN25-CLEAN-ROUND{number}-FINAL-COMPARISON.json');report=e.read(bound)
    return dict(version_id=e.read(report['frozen'])['candidate']['id'],descriptor=report['frozen'],
        report=bound,mean=report['comparison']['candidate_mean'],evidence=[bound],status='provisional')

def fixture():
    report=e.read(layered.FINAL_REPORT);descriptor=e.read(report['frozen']);origin=e.read(descriptor['parent_basis'])
    preserved=origin['carried_population'];state=e.read(preserved)
    state=pool.retain(state,descriptor['candidate'],reason='Offline v4 fixture, no prediction adoption',evidence=[layered.FINAL_REPORT])
    previous_bound=e.read(origin['frontier_expansion'])['frontier'];previous=e.read(previous_bound)
    growth=[member(13),member(15)];inc=deepcopy(next(m for m in previous['members'] if m['version_id']==previous['incumbent_id']))
    prior=e.read(e.pin(A/'TRAIN25-FRONTIER-G6-BOOTSTRAP1-PROGRESS-AFTER-ROUND14.json'))
    for outcome in prior['outcomes']:
        if outcome['status']=='FULL25':
            archived=e.pin(A/'TRAIN25-FRONTIER-ROUND14-5E22-SOURCE-PLAN128.json')
            assert archived['sha256']==outcome['source_plan']['sha256']
            outcome['source_plan']=archived  # exact saved alias, never rewrite old progress
    prior['outcomes'].append(dict(parent_id=descriptor['candidate']['parent'],hypothesis_id='03a-nonquarterly-period-compatibility',
        status='FULL25',member=growth[1],checkpoint=layered.FINAL_GIT,
        source_plan=e.pin(A/'TRAIN25-FRONTIER-ROUND15-03A-SOURCE-PLAN137.json')))
    # Synthetic immutable progress binding is supplied by the test's saved shim.
    progress_bound={'fixture':'complete_g6'}
    outcomes=policy.generation_outcomes(previous,prior,complete=True)
    considered=list({m['version_id']:m for m in [*previous['members'],*outcomes]}.values())
    fees=e.read(report['all_fees']);snapshot=fees['current_original_ledger'];remaining=487429960800-snapshot['charged_nano_usd']
    f=dict(schema=layered.SCHEMA,generation=7,prospective=True,historical_backfill=False,
        direct_authority=policy.FRONTIER_AUTHORITY,no_backfill_authority=policy.NO_BACKFILL_AUTHORITY,
        layered_authority=layered.AUTHORITY,layered_policy=layered.POLICY,training=descriptor['training'],
        incumbent_id=inc['version_id'],prediction_reference=inc,members=growth,considered=considered,
        growth_depth=1,growth_root_id=inc['version_id'],growth_shortfall=0,layer_status='READY_DEPTH_LAYER',layer_complete=False,
        transition_from_legacy=True,historical_omissions='Old G6 had2 children per parent, not retroactively three.',
        previous_frontier=previous_bound,preceding_outcomes=progress_bound,preserved_population=preserved,
        previous_stable=e.pin(A/'TRAIN25-CLEAN-ROUND15-STABLE-BASIS.json'),prediction_decision=dict(selected=inc['descriptor']),
        budget=dict(evidence=report['all_fees'],stage_total_cap_nano_usd=487429960800,
            additional_budget_amendment=budget.binding(),charged_nano_usd=snapshot['charged_nano_usd'],
            pending_full_reserved_nano_usd=0,remaining_nano_usd=remaining,planning_not_grant=True),
        estimated_expansion_cost_nano_usd=78000000000,expansion_budget_shortfall_nano_usd=0)
    f['expansions']=[dict(parent_id=m['version_id'],children=[dict(hypothesis_id=m['version_id']+'-'+str(i),
        question='Distinct synthetic question '+m['version_id']+'-'+str(i),support_observation='Actual source and changed decision',
        refute_observation='No valid activation',exit_criterion='Do not repeat unchanged',estimated_cost_nano_usd=13000000000)
        for i in range(3)]) for m in growth]
    f['qualification']=[]
    for m in considered:
        group=next((g for g in f['expansions'] if g['parent_id']==m['version_id']),None)
        test=group['children'][0] if group else f['expansions'][0]['children'][0]
        f['qualification'].append(dict(version_id=m['version_id'],eligible=group is not None,demonstrated_improvement=False,
            prediction_quality='Historical full25, below champion',research_capability='Unresolved mechanism, not validated',
            harness_capability='Candidate H unchanged',evidence=[m['report']],next_test=test,
            eligibility=dict(safe=True,technically_valid=True,authentic_evaluation=True,distinct_test=group is not None,
                credible_test=True,estimated_next_test_nano_usd=13000000000)))
    return f,state,prior,progress_bound

class LayeredTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.base,cls.state,cls.progress,cls.progress_bound=fixture()
    def setUp(self):
        self.f=deepcopy(self.base);self.progress=deepcopy(type(self).progress);original=policy.saved
        self.shim=patch.object(policy,'saved',side_effect=lambda b:deepcopy(self.progress) if b==self.progress_bound else original(b))
        self.shim.start();self.addCleanup(self.shim.stop)
        original_layered=layered.saved
        self.shim2=patch.object(layered,'saved',side_effect=lambda b:deepcopy(self.progress) if b==self.progress_bound else original_layered(b))
        self.shim2.start();self.addCleanup(self.shim2.stop)
    def test_real_sibling_ancestry_and_two_provisional_growth_seats(self):
        policy.validate_frontier(self.f,self.state)
        self.assertEqual(len(self.f['members']),2)
        self.assertNotIn(self.f['incumbent_id'],[m['version_id'] for m in self.f['members']])
    def test_exactly_three_children_per_parent(self):
        for count in (0,1,2,4):
            bad=deepcopy(self.f);c=bad['expansions'][0]['children'];bad['expansions'][0]['children']=[dict(c[0],hypothesis_id=str(i)) for i in range(count)]
            with self.subTest(count=count),self.assertRaisesRegex(ValueError,'EXACTLY3'):policy.validate_frontier(bad,self.state)
    def test_no_duplicate_parent_or_prediction_seat(self):
        for value in (self.f['members'][0],self.f['prediction_reference']):
            bad=deepcopy(self.f);bad['members'].append(value)
            with self.assertRaisesRegex(ValueError,'growth parents'):policy.validate_frontier(bad,self.state)
    def test_same_depth_not_mixed_ancestors(self):
        bad=deepcopy(self.f);bad['growth_depth']=2
        with self.assertRaisesRegex(ValueError,'same-depth'):policy.validate_frontier(bad,self.state)
    def test_every_parent_expands_and_questions_distinct(self):
        bad=deepcopy(self.f);bad['expansions'].pop()
        with self.assertRaisesRegex(ValueError,'Every retained'):policy.validate_frontier(bad,self.state)
        bad=deepcopy(self.f);bad['expansions'][1]['children'][0]['question']=bad['expansions'][0]['children'][0]['question']
        with self.assertRaisesRegex(ValueError,'Duplicate'):policy.validate_frontier(bad,self.state)
    def test_test_affordability_and_non_gain_eligibility(self):
        self.assertTrue(all(m['status']=='provisional' for m in self.f['members']))
        for flag in ('safe','technically_valid','authentic_evaluation','distinct_test','credible_test'):
            bad=deepcopy(self.f);next(a for a in bad['qualification'] if a['eligible'])['eligibility'][flag]=False
            with self.subTest(flag=flag),self.assertRaisesRegex(ValueError,'affordable'):policy.validate_frontier(bad,self.state)
    def test_reason_fields_do_not_prove_validated_gain(self):
        self.f['members'][0]['status']='validated_within_scope'
        with self.assertRaisesRegex(ValueError,'actual use'):policy.validate_frontier(self.f,self.state)
    def test_no_old_missing_branch_backfill(self):
        bad=deepcopy(self.f);bad['considered'].pop()
        with self.assertRaisesRegex(ValueError,'backfill'):policy.validate_frontier(bad,self.state)
    def test_partial_old_outcomes_cannot_select_next_layer(self):
        self.progress['outcomes'].pop()
        try:
            with self.assertRaisesRegex(ValueError,'every declared'):policy.validate_frontier(self.f,self.state)
        finally:self.progress=deepcopy(type(self).progress)
    def test_no_old_caps_implicitly_expanded(self):
        self.assertEqual(policy.decision(388102258700,0,5000000000,meaningful_next=True),'STOP_ORIGINAL_BUDGET_INSUFFICIENT')
        self.assertEqual(policy.decision(388102258700,0,5000000000,meaningful_next=True,additional_budget_amendment=budget.binding()),'CONTINUE')
        self.f['budget'].pop('additional_budget_amendment')
        with self.assertRaisesRegex(ValueError,'cap required'):policy.validate_frontier(self.f,self.state)
    def test_full_pending_and_estimated_shortfall_are_counted(self):
        bad=deepcopy(self.f);bad['budget']['remaining_nano_usd']+=1
        with self.assertRaisesRegex(ValueError,'remaining'):policy.validate_frontier(bad,self.state)
        bad=deepcopy(self.f);bad['estimated_expansion_cost_nano_usd']-=1
        with self.assertRaisesRegex(ValueError,'shortfall'):policy.validate_frontier(bad,self.state)
    def test_balanced_expansion_prevents_single_chain(self):
        first,other=[m['version_id'] for m in self.f['members']]
        progress=dict(outcomes=[dict(parent_id=first,hypothesis_id=self.f['expansions'][0]['children'][0]['hypothesis_id'])])
        with self.assertRaisesRegex(ValueError,'every retained'):policy.balanced_parent_expansion(self.f,progress,first)
        policy.balanced_parent_expansion(self.f,progress,other)
    def test_finite_source_bridge_real_positive_and_generic_negative(self):
        descriptor=e.read(layered.FINANCIAL_DESCRIPTOR);runtime=e.read(e.read(descriptor['proposal'])['runtime'])
        m=dict(descriptor=layered.FINANCIAL_DESCRIPTOR,report=layered.FINAL_REPORT)
        self.assertTrue(layered.accepted_source(descriptor,runtime,m,layered.FINAL_GIT))
        for key in ('source_commit','parent_basis','candidate'):
            bad=deepcopy(descriptor);bad[key]='unrelated'
            self.assertFalse(layered.accepted_source(bad,runtime,m,layered.FINAL_GIT))
        self.assertFalse(layered.accepted_source(descriptor,runtime,m,dict(layered.FINAL_GIT,sha256='0'*64)))
    def test_unknown_code_ancestry_and_cycle_rejected(self):
        with self.assertRaises(ValueError):layered.code_depth('x','root',{'x':dict(parent='x')})
        with self.assertRaises(ValueError):layered.code_depth('x','root',{})
    def test_cannot_fabricate_shortfall_by_dropping_available_seats(self):
        for count in (0,1):
            bad=deepcopy(self.f);bad['members']=bad['members'][:count];bad['expansions']=bad['expansions'][:count]
            bad.update(growth_shortfall=2-count,layer_status='FRONTIER_SHORTFALL',shortfall_reason='Artificial omission',layer_complete=False)
            with self.subTest(count=count),self.assertRaisesRegex(ValueError,'manufacture'):policy.validate_frontier(bad,self.state)
    def test_generation_strict_integer(self):
        for value in (7.0,True,None):
            bad=deepcopy(self.f);bad['generation']=value
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'generation'):policy.validate_frontier(bad,self.state)
    def test_selected_member_must_equal_authenticated_pool_tuple(self):
        bad=deepcopy(self.f);bad['members'][0]['mean']+=.02
        with self.assertRaises(ValueError):policy.validate_frontier(bad,self.state)
        bad=deepcopy(self.f);bad['members'][0]['descriptor']=dict(bad['members'][0]['descriptor'],sha256='0'*64)
        with self.assertRaises(ValueError):policy.validate_frontier(bad,self.state)
    def test_next_depth_cannot_retain_ancestor_or_replace_root(self):
        previous=deepcopy(policy.saved(self.f['previous_frontier']))
        previous.update(schema=layered.SCHEMA,growth_depth=0,growth_root_id=self.f['growth_root_id'])
        original=layered.saved
        with patch.object(layered,'saved',side_effect=lambda b:previous if b==self.f['previous_frontier'] else original(b)):
            with self.assertRaisesRegex(ValueError,'Next depth'):policy.validate_frontier(self.f,self.state)
            self.f['growth_root_id']=self.f['members'][0]['version_id']
            with self.assertRaisesRegex(ValueError,'Next depth'):policy.validate_frontier(self.f,self.state)

if __name__=='__main__':unittest.main()
