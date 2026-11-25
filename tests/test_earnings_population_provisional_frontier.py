"""Prospective human-policy regressions; saved/synthetic evidence, no paid work."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import earnings_population as pool
import earnings_population_coevolution as policy
from supervisor_harness import capacity_feedback_engine as e
from test_earnings_population_exact3 import ExactThreeTests as LegacyFixture


class ProvisionalFrontierTests(unittest.TestCase):
    def setUp(self):
        fixture=LegacyFixture();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.fixture=fixture;self.f=deepcopy(fixture.frontier)
        self.f.update(schema='edgar25_global_frontier_v3',
            provisional_authority=policy.PROVISIONAL_AUTHORITY,amendment_policy=policy.PROVISIONAL_POLICY,
            members=deepcopy(self.f['considered']),eligible_shortfall=0,
            frontier_status='READY_THREE_PARENT_FRONTIER',preceding_generation_complete=False,
            bootstrap_epoch=1,bootstrap=dict(bounded=False,generation_complete=False))
        budget_bound=e.pin(policy.training.ROOT/'TRAIN25-CLEAN-ROUND13-ALL-FEES.json')
        booked=e.read(budget_bound)['current_original_ledger']['charged_nano_usd']
        self.f['budget']=dict(evidence=budget_bound,stage_total_cap_nano_usd=387429960800,
            charged_nano_usd=booked,pending_full_reserved_nano_usd=0,
            remaining_nano_usd=387429960800-booked,planning_not_grant=True)
        for member in self.f['members']:
            if member['version_id']!=self.f['incumbent_id']:
                member.update(status='provisional',capability='Testable but not demonstrated improvement',
                    observed_use='Saved actual full25 evidence; no gain inferred',uncertainty='Gain unverified',
                    information_value='Distinct unresolved source/use test',opportunity_cost='Original budget only',
                    next_test='Synthetic bounded follow-up',exit_criterion='Stop this recipe if mechanism unchanged')
        for assessment in self.f['qualification']:
            assessment.update(eligible=True,demonstrated_improvement=False,
                eligibility=dict(safe=True,technically_valid=True,authentic_evaluation=True,
                    distinct_test=True,credible_test=True,estimated_next_test_nano_usd=13000000000),
                next_test=dict(question='A distinct mechanism question '+assessment['version_id'],
                    support_observation='Verified source/use change',refute_observation='No changed decision',
                    exit_criterion='No repeat without a new distinguishing observation'))
        self.replan()
        state=e.read(fixture.origin['carried_population'])
        self.state=pool.retain(state,e.read(fixture.child['descriptor'])['candidate'],
            reason='Offline fixture only',evidence=fixture.child['evidence'])

    def replan(self):
        self.f['expansions']=[dict(parent_id=m['version_id'],children=[dict(
            hypothesis_id=m['version_id']+'-'+str(i),question='Distinct child '+str(i),
            support_observation='Actual mechanism use',refute_observation='No mechanism change',
            estimated_cost_nano_usd=13000000000) for i in range(2)]) for m in self.f['members']]
        required=sum(c['estimated_cost_nano_usd'] for g in self.f['expansions'] for c in g['children'])
        self.f.update(estimated_expansion_cost_nano_usd=required,
            expansion_budget_shortfall_nano_usd=max(0,required-self.f['budget']['remaining_nano_usd']),
            expansion_budget_shortfall_reason='Conservative estimates exceed remaining original budget; not fees or grant')
        for assessment in self.f['qualification']:
            group=next((g for g in self.f['expansions'] if g['parent_id']==assessment['version_id']),None)
            test=group['children'][0] if group else dict(hypothesis_id='not-selected',question='Not selected',
                support_observation='No dispatch',refute_observation='No dispatch')
            assessment['next_test']={**{k:test[k] for k in
                ('hypothesis_id','question','support_observation','refute_observation')},'exit_criterion':'No mechanism change'}

    def make_shortfall(self):
        dropped=self.f['members'].pop()
        next(a for a in self.f['qualification'] if a['version_id']==dropped['version_id']).update(eligible=False)
        next(a for a in self.f['qualification'] if a['version_id']==dropped['version_id'])['eligibility']['distinct_test']=False
        self.f.update(eligible_shortfall=1,frontier_status='FRONTIER_SHORTFALL',
            shortfall_reason='One real evaluated state has no distinct next test, no invented seat',
            bootstrap=dict(bounded=True,generation_complete=False))
        self.replan()

    def test_lower_scoring_unproved_states_qualify_provisionally(self):
        policy.validate_frontier(self.f,self.state)
        self.assertEqual(len(self.f['members']),3)
        self.assertTrue(any(m['mean']<3.14 for m in self.f['members']))
        self.assertTrue(all(m['status']=='provisional' for m in self.f['members'] if m['mean']<3.14))

    def test_actual_round13_losing_candidate_is_safe_full25_not_a_gain_claim(self):
        report_bound=e.pin(policy.training.ROOT/'TRAIN25-CLEAN-ROUND13-FINAL-COMPARISON.json')
        report=e.read(report_bound);candidate=e.read(report['frozen'])['candidate']
        member=dict(version_id=candidate['id'],descriptor=report['frozen'],report=report_bound,
            mean=3.06,evidence=[report['actual_R_mechanism']])
        self.assertEqual(policy.complete_member(member,self.f['training']),candidate)
        assessment=deepcopy(self.f['qualification'][1])
        self.assertFalse(assessment['demonstrated_improvement'])
        self.assertTrue(policy.provisional_eligible(assessment,self.f['budget']['remaining_nano_usd']))

    def test_unsafe_invalid_unevaluated_or_non_distinct_cannot_fill_seat(self):
        for flag in ('safe','technically_valid','authentic_evaluation','distinct_test','credible_test'):
            bad=deepcopy(self.f);bad['qualification'][1]['eligibility'][flag]=False
            with self.subTest(flag=flag),self.assertRaisesRegex(ValueError,'eligibility'):
                policy.exact3_selection(bad)

    def test_affordability_does_not_increase_budget_or_discard_incumbent(self):
        assessment=self.f['qualification'][1]
        self.assertFalse(policy.provisional_eligible(assessment,1))
        self.assertTrue(policy.provisional_eligible(assessment,1,incumbent=True))
        bad=deepcopy(assessment);bad['eligibility']['safe']=False
        self.assertFalse(policy.provisional_eligible(bad,13000000000,incumbent=True))

    def test_unknown_gain_is_not_validated_improvement(self):
        self.f['members'][1]['status']='validated_within_scope'
        with self.assertRaisesRegex(ValueError,'provisional'):
            policy.exact3_selection(self.f)

    def test_cannot_borrow_another_nodes_validated_gain(self):
        member=self.f['members'][1];member['status']='validated_within_scope'
        assessment=self.f['qualification'][1];assessment['demonstrated_improvement']=True
        assessment['validated_gain_evidence']={'fixture':'saved_gain'}
        original=policy.saved
        finding={**{k:member[k] for k in ('version_id','descriptor','report')},
            'validated_learning':True,'actual_use':True,'measured_benefit':'Bounded synthetic identity test only'}
        with patch.object(policy,'saved',side_effect=lambda b: deepcopy(finding)
                if b==assessment['validated_gain_evidence'] else original(b)):
            policy.exact3_selection(self.f)
            for key in ('version_id','descriptor','report'):
                value=finding[key];finding[key]='another_node'
                with self.subTest(key=key),self.assertRaisesRegex(ValueError,'provisional'):
                    policy.exact3_selection(self.f)
                finding[key]=value

    def test_eligibility_test_must_be_the_actual_declared_child(self):
        for key in ('hypothesis_id','question','support_observation','refute_observation','cost'):
            bad=deepcopy(self.f)
            if key=='cost':bad['qualification'][1]['eligibility']['estimated_next_test_nano_usd']+=1
            else:bad['qualification'][1]['next_test'][key]='unrelated_test'
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'actual declared child'):
                policy.exact3_selection(bad)

    def test_missing_flags_or_vague_or_fake_tests_fail(self):
        for edit in ('bool','cost','question'):
            bad=deepcopy(self.f)
            if edit=='bool':bad['qualification'][1]['eligibility']['safe']='true'
            elif edit=='cost':bad['qualification'][1]['eligibility']['estimated_next_test_nano_usd']=True
            else:bad['qualification'][1]['next_test']['question']=''
            with self.subTest(edit=edit),self.assertRaises(ValueError):policy.exact3_selection(bad)

    def test_shortfall_is_bootstrap_not_complete_generation(self):
        self.make_shortfall();policy.validate_frontier(self.f,self.state)
        for edit in ('status','complete','preceding','epoch'):
            bad=deepcopy(self.f)
            if edit=='status':bad['frontier_status']='READY_THREE_PARENT_FRONTIER'
            elif edit=='complete':bad['bootstrap']['generation_complete']=True
            elif edit=='preceding':bad['preceding_generation_complete']=True
            else:bad['bootstrap_epoch']=0
            with self.subTest(edit=edit),self.assertRaisesRegex(ValueError,'bootstrap'):
                policy.exact3_selection(bad)

    def test_bootstrap_epoch_does_not_claim_next_completed_generation(self):
        previous=deepcopy(self.fixture.previous)
        previous.update(schema='edgar25_global_frontier_v3',frontier_status='FRONTIER_SHORTFALL',bootstrap_epoch=1)
        self.f.update(generation=previous['generation'],bootstrap_epoch=2)
        original=policy.saved
        with patch.object(policy,'saved',side_effect=lambda b: deepcopy(previous)
                if b==self.f['previous_frontier'] else original(b)),patch.object(
                policy,'generation_outcomes',return_value=[self.fixture.child]):
            policy.exact3_selection(self.f)
            self.f['generation']+=1
            with self.assertRaisesRegex(ValueError,'skipped'):policy.exact3_selection(self.f)

    def test_every_parent_requires_two_distinct_children(self):
        for count in (0,1,4):
            bad=deepcopy(self.f);group=bad['expansions'][1]
            group['children']=[dict(group['children'][0],hypothesis_id=str(i),question=str(i)) for i in range(count)]
            # Recompute the declaration so this checks child policy, not arithmetic.
            total=sum(c['estimated_cost_nano_usd'] for g in bad['expansions'] for c in g['children'])
            bad.update(estimated_expansion_cost_nano_usd=total,
                expansion_budget_shortfall_nano_usd=max(0,total-bad['budget']['remaining_nano_usd']))
            with self.subTest(count=count),self.assertRaises(ValueError):policy.validate_frontier(bad,self.state)
        bad=deepcopy(self.f);bad['expansions'].pop()
        total=sum(c['estimated_cost_nano_usd'] for g in bad['expansions'] for c in g['children'])
        bad.update(estimated_expansion_cost_nano_usd=total,
            expansion_budget_shortfall_nano_usd=max(0,total-bad['budget']['remaining_nano_usd']))
        with self.assertRaisesRegex(ValueError,'every retained|actual declared child'):policy.validate_frontier(bad,self.state)

    def test_no_global_selection_until_all_declared_children_terminal(self):
        progress=dict(frontier={'fixture':'current'},generation=self.f['generation'],outcomes=[])
        with self.assertRaisesRegex(ValueError,'every declared'):
            policy.generation_outcomes(self.f,progress,complete=True)

    def test_no_single_family_substitution_even_when_it_lost(self):
        ids=[m['version_id'] for m in self.f['members']]
        progress=dict(outcomes=[dict(parent_id=ids[0],hypothesis_id=self.f['expansions'][0]['children'][0]['hypothesis_id'])])
        with self.assertRaisesRegex(ValueError,'every retained parent'):
            policy.balanced_parent_expansion(self.f,progress,ids[0])
        policy.balanced_parent_expansion(self.f,progress,ids[1])
        progress['outcomes'].append(dict(parent_id=ids[1],hypothesis_id=self.f['expansions'][1]['children'][0]['hypothesis_id']))
        with self.assertRaises(ValueError):policy.balanced_parent_expansion(self.f,progress,ids[1])
        policy.balanced_parent_expansion(self.f,progress,ids[2])

    def test_original_cap_pending_and_exact_expansion_shortfall(self):
        for edit in ('cap','pending','booked','remaining','gap'):
            bad=deepcopy(self.f)
            if edit=='cap':bad['budget']['stage_total_cap_nano_usd']=400000000000
            elif edit=='pending':bad['budget']['pending_full_reserved_nano_usd']=1
            elif edit=='booked':bad['budget']['charged_nano_usd']+=1
            elif edit=='remaining':bad['budget']['remaining_nano_usd']+=1
            else:bad['expansion_budget_shortfall_nano_usd']=0
            with self.subTest(edit=edit),self.assertRaises(ValueError):policy.exact3_selection(bad)

    def test_duplicate_state_or_archived_backfill_cannot_invent_third(self):
        bad=deepcopy(self.f);bad['members'][2]=deepcopy(bad['members'][1])
        with self.assertRaises(ValueError):policy.validate_frontier(bad,self.state)
        bad=deepcopy(self.f);bad['considered'].pop()
        with self.assertRaisesRegex(ValueError,'surviving parents'):policy.exact3_selection(bad)

    def test_next_runtime_binds_policy_but_historical_source_paths_unchanged(self):
        from earnings_population_runtime import source_paths
        old=source_paths(training=True,clean_slate=True,clean_followup=13)
        new=source_paths(training=True,clean_slate=True,clean_followup=14)
        self.assertNotIn(policy.PROVISIONAL_PLAN,old)
        self.assertEqual(set(new)-set(old),{policy.PROVISIONAL_PLAN})
        for key in old:self.assertEqual(new[key],old[key])

    def test_round14_cannot_use_old_qualification_policy(self):
        plan=e.read(e.pin(policy.e.REPO/policy.PLAN));origin=e.read(plan['origin'])
        bound=policy.saved(origin['frontier_expansion'])['frontier'];old=policy.saved(bound)
        old=dict(old,schema='edgar25_global_frontier_v2');original=policy.saved
        with patch.object(policy,'saved',side_effect=lambda b:old if b==bound else original(b)),self.assertRaisesRegex(ValueError,'Round14'):
            policy.validate_plan(dict(plan,logical_round=14),dict(origin,logical_round=14))

    def test_old_history_and_strict_prediction_budget_rule_not_rewritten(self):
        self.assertEqual(e.read(self.fixture.previous_bound),self.fixture.previous)
        self.assertEqual(policy.decision(363324450400,0,13000000000,meaningful_next=True),'CONTINUE')
        self.assertEqual(policy.decision(386429960800,0,13000000000,meaningful_next=True),'STOP_ORIGINAL_BUDGET_INSUFFICIENT')
        self.assertEqual(policy.selection_threshold(self.fixture.origin),max(
            self.fixture.origin['prior_mean'],self.fixture.origin['incumbent_mean']))


if __name__=='__main__':unittest.main()
