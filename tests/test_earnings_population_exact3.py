"""Offline exact3 policy regressions, saved evidence only; no model/Native/ledger."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import earnings_population_coevolution as policy
from supervisor_harness import capacity_feedback_engine as e


class ExactThreeTests(unittest.TestCase):
    def setUp(self):
        A=policy.training.ROOT
        origin=e.read(e.pin(A/'TRAIN25-CLEAN-ROUND12-FRONTIER-ORIGIN-V4.json'))
        self.previous_bound=e.read(origin['frontier_expansion'])['frontier']
        self.origin=origin
        self.previous=e.read(self.previous_bound)
        report_bound=e.pin(A/'TRAIN25-CLEAN-ROUND12-FINAL-COMPARISON.json')
        report=e.read(report_bound);candidate=e.read(report['frozen'])['candidate']
        self.child=dict(version_id=candidate['id'],descriptor=report['frozen'],report=report_bound,
                        mean=2.96,evidence=[report['actual_H_behavior']])
        group=next(g for g in self.previous['expansions'] if g['children'])
        self.progress=dict(frontier=self.previous_bound,generation=4,outcomes=[dict(
            parent_id=group['parent_id'],hypothesis_id=group['children'][0]['hypothesis_id'],
            status='FULL25',member=self.child,checkpoint=e.pin(A/'TRAIN25-CLEAN-ROUND12-FINAL-GIT.json'),
            source_plan=e.pin(A/'TRAIN25-FRONTIER-ROUND12-SOURCE-PLAN-V4.json'))])
        self.progress_bound={'fixture':'progress'}
        self.frontier=deepcopy(self.previous)
        self.frontier.update(schema='edgar25_global_frontier_v2',generation=5,
            retention_authority=policy.EXACT3_AUTHORITY,previous_frontier=self.previous_bound,
            preceding_outcomes=self.progress_bound,considered=[*self.previous['members'],self.child],
            members=self.previous['members'][:1],eligible_shortfall=2,
            shortfall_reason='No numerical/public-use benefit qualifies either losing compiler node.')
        self.frontier['qualification']=[dict(version_id=m['version_id'],eligible=i==0,
            reason='Saved full25 incumbent' if i==0 else 'No validated numerical/public-use capability',
            prediction_quality=str(m['mean']),research_capability='Unverified, not score-derived',
            harness_capability='Unverified, not delivered-tool-derived',evidence=m['evidence'])
            for i,m in enumerate(self.frontier['considered'])]
        original=policy.saved
        replacement=patch.object(policy,'saved',side_effect=lambda b:
            deepcopy(self.progress) if b==self.progress_bound else original(b))
        replacement.start();self.addCleanup(replacement.stop)

    def test_actual_parent_plus_child_pool_and_explicit_two_seat_shortfall(self):
        policy.exact3_selection(self.frontier)
        self.assertEqual(len(self.frontier['members']),1)
        self.assertEqual(policy.generation_outcomes(self.previous,self.progress,complete=True),[self.child])

    def test_exact_three_if_three_qualify_including_surviving_parents(self):
        for a in self.frontier['qualification']:a['eligible']=True
        self.frontier.update(members=self.frontier['considered'],eligible_shortfall=0)
        policy.exact3_selection(self.frontier)
        self.frontier['members']=self.frontier['members'][:2]
        with self.assertRaisesRegex(ValueError,'exactly three'):policy.exact3_selection(self.frontier)

    def test_invented_third_or_unreported_shortfall_refused(self):
        self.frontier['members']=self.frontier['considered']
        with self.assertRaises(ValueError):policy.exact3_selection(self.frontier)
        self.frontier['members']=self.frontier['members'][:1]
        for changes in ({'eligible_shortfall':0},{'shortfall_reason':''}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                policy.exact3_selection(dict(self.frontier,**changes))

    def test_axes_and_evidence_must_remain_distinct_not_scalar_score(self):
        for field in ('prediction_quality','research_capability','harness_capability','evidence','reason'):
            bad=deepcopy(self.frontier);bad['qualification'][1][field]=''
            with self.subTest(field=field),self.assertRaises(ValueError):policy.exact3_selection(bad)

    def test_no_archived_node_fill_or_silent_parent_drop(self):
        for members in (self.frontier['considered'][:-1],self.frontier['considered'][1:]):
            with self.assertRaisesRegex(ValueError,'surviving parents'):
                policy.exact3_selection(dict(self.frontier,considered=members))

    def test_qualification_must_cover_every_candidate_once(self):
        self.frontier['qualification'][-1]=self.frontier['qualification'][0]
        with self.assertRaises(ValueError):policy.exact3_selection(self.frontier)

    def test_no_next_generation_before_all_declared_children_evaluated(self):
        self.progress['outcomes']=[]
        with self.assertRaisesRegex(ValueError,'every declared child'):policy.exact3_selection(self.frontier)

    def test_duplicates_wrong_parent_deferred_and_fake_full25_refused(self):
        for edit in ('duplicate','undeclared','deferred','checkpoint'):
            bad=deepcopy(self.progress)
            if edit=='duplicate':bad['outcomes']*=2
            elif edit=='undeclared':bad['outcomes'][0]['parent_id']='0'*64
            elif edit=='deferred':bad['outcomes'][0]['status']='DEFERRED_BUDGET'
            else:bad['outcomes'][0]['checkpoint']=self.previous['members'][0]['report']
            with self.subTest(edit=edit),self.assertRaises(ValueError):
                policy.generation_outcomes(self.previous,bad,complete=True)

    def test_rejected_child_is_terminal_not_qualified_full25(self):
        A=policy.training.ROOT
        plan=e.pin(A/'TRAIN25-FRONTIER-ROUND12-SOURCE-PLAN-V3.json')
        origin=e.read(e.read(plan)['origin']);claim=e.read(origin['frontier_expansion'])
        previous=e.read(claim['frontier'])
        bad=deepcopy(self.progress);bad['frontier']=claim['frontier']
        bad['outcomes'][0]=dict(parent_id=bad['outcomes'][0]['parent_id'],
            hypothesis_id=bad['outcomes'][0]['hypothesis_id'],status='TERMINAL_INELIGIBLE',
            closure=e.pin(A/'TRAIN25-CLEAN112-CLOSED-CLOSURE.json'),source_plan=plan)
        self.assertEqual(policy.generation_outcomes(previous,bad,complete=True),[])
        with self.assertRaisesRegex(ValueError,'exact actual frontier'):
            policy.generation_outcomes(self.previous,dict(bad,frontier=self.previous_bound),complete=True)

    def test_one_full25_child_cannot_fill_two_different_hypotheses(self):
        frontier=deepcopy(self.previous);progress=deepcopy(self.progress)
        group=next(g for g in frontier['expansions'] if g['children'])
        other=deepcopy(group['children'][0]);other['hypothesis_id']='different-child';group['children'].append(other)
        duplicate=deepcopy(progress['outcomes'][0]);duplicate['hypothesis_id']='different-child'
        progress['outcomes'].append(duplicate)
        with self.assertRaisesRegex(ValueError,'cannot fill two'):
            policy.generation_outcomes(frontier,progress,complete=True)

    def test_full25_result_of_another_hypothesis_is_not_substituted(self):
        frontier=deepcopy(self.previous);progress=deepcopy(self.progress)
        next(g for g in frontier['expansions'] if g['children'])['children'][0]['hypothesis_id']='different-child'
        progress['outcomes'][0]['hypothesis_id']='different-child'
        with self.assertRaisesRegex(ValueError,'exact actual frontier'):
            policy.generation_outcomes(frontier,progress,complete=True)

    def test_actual_accepted_review_must_identify_this_exact_child(self):
        descriptor=e.read(self.child['descriptor']);proposal=e.read(descriptor['proposal'])
        bound=proposal['proposal_stages'][0];original=policy.saved;record=e.read(bound)
        for field in ('candidate','accepted'):
            bad=deepcopy(record)
            if field=='candidate':bad['candidate']['id']='0'*64
            else:bad['review']['accepted_for_exploration']=False
            with self.subTest(field=field),patch.object(policy,'saved',side_effect=lambda b:
                    deepcopy(bad) if b==bound else original(b)),self.assertRaisesRegex(ValueError,'genuine accepted'):
                policy.generation_outcomes(self.previous,self.progress,complete=True)

    def test_immutable_source_plan_copy_must_match_actual_runtime(self):
        bad=deepcopy(self.progress)
        bad['outcomes'][0]['source_plan']=e.pin(policy.training.ROOT/'TRAIN25-FRONTIER-ROUND12-SOURCE-PLAN-V3.json')
        with self.assertRaises(ValueError):policy.generation_outcomes(self.previous,bad,complete=True)

    def test_budget_and_legacy_history_remain_unmodified(self):
        self.assertEqual(policy.decision(352135831600,0,13000000000,meaningful_next=True),'CONTINUE')
        self.assertEqual(policy.decision(386429960800,0,13000000000,meaningful_next=True),
                         'STOP_ORIGINAL_BUDGET_INSUFFICIENT')
        self.assertEqual(e.read(self.previous_bound),self.previous)

    def test_two_to_three_children_required_for_each_retained_parent(self):
        import earnings_population as pool
        state=e.read(self.origin['carried_population'])
        state=pool.retain(state,e.read(self.child['descriptor'])['candidate'],reason='offline fixture',evidence=self.child['evidence'])
        parent=self.frontier['members'][0]['version_id']
        self.frontier['expansions']=[dict(parent_id=parent,children=[dict(hypothesis_id=str(i),
            question='distinct question '+str(i),support_observation='observable support',refute_observation='observable failure') for i in range(2)])]
        policy.validate_frontier(self.frontier,state)
        for count in (0,1,4):
            bad=deepcopy(self.frontier)
            bad['expansions'][0]['children']=[dict(hypothesis_id=str(i),question=str(i),
                support_observation='support',refute_observation='failure') for i in range(count)]
            with self.subTest(count=count),self.assertRaises(ValueError):policy.validate_frontier(bad,state)
        self.frontier['expansions'][0]['children'][1]['question']='distinct question 0'
        with self.assertRaisesRegex(ValueError,'Distinct questions'):policy.validate_frontier(self.frontier,state)

    def test_future_plan_cannot_bypass_new_policy_with_legacy_optional_width(self):
        plan=e.read(e.pin(policy.training.ROOT/'TRAIN25-FRONTIER-ROUND12-SOURCE-PLAN-V4.json'))
        with self.assertRaisesRegex(ValueError,'Round13'):
            policy.validate_plan(dict(plan,logical_round=13),dict(self.origin,logical_round=13))

    def test_actual_incumbent_genealogy_does_not_rewrite_legacy_pool_metadata(self):
        plan=e.read(e.pin(policy.e.REPO/policy.PLAN));origin=e.read(plan['origin'])
        if origin['logical_round']<13:self.skipTest('Prospective actual origin not activated yet')
        state=e.read(origin['carried_population']);before=deepcopy(state)
        self.assertEqual(state['versions'][state['stable_id']]['axis'],'baseline')
        self.assertEqual(policy.selected_parent(state,origin),origin['parent'])
        self.assertEqual(origin['parent']['axis'],'R')
        self.assertIsNotNone(origin['parent']['parent'])
        self.assertEqual(state,before)
        bad=deepcopy(origin);bad['parent']['R']['sha256']='0'*64
        with self.assertRaises(ValueError):policy.selected_parent(state,bad)

    def test_real_author_role_guard_keeps_native_anchor_record_but_authenticates_actual_code(self):
        import test_earnings_population_clean_slate as fixtures
        import earnings_population_clean_slate as clean
        fixture=fixtures.CurrentGuardTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.stack.enter_context(patch('earnings_population_runtime._local',side_effect=e.read))
        state=fixture.task['scaffold'];registered=state['versions'][state['stable_id']]
        actual=deepcopy(registered);actual.update(axis='R',parent='synthetic-prior-code-id')
        from market_rsi import digest
        chosen=dict(parent_pair_sha256=registered['id'],feedback_sha256=digest(fixture.task['feedback']))
        args=(chosen,state,fixture.f.args('author')[-1])
        with patch.object(clean,'second_round',return_value=False),patch.object(clean,'selected_parent',return_value=actual):
            selected=clean.selection(fixture.f.manager,'author',args,{})
        self.assertEqual(selected['version'],registered)
        self.assertEqual({a:selected['version'][a] for a in ('R','H')},{a:actual[a] for a in ('R','H')})
        fixture.f.manager.current=selected
        fixture.f.manager.register_case(fixture.f.case(args[-1]))
        self.assertTrue(fixture.f.manager.current['registered'])
        wrong=deepcopy(actual);wrong['R']['sha256']='0'*64
        with patch.object(clean,'second_round',return_value=False),patch.object(clean,'selected_parent',return_value=wrong),self.assertRaises(ValueError):
            clean.selection(fixture.f.manager,'author',args,{})

    def test_existing_services_author_inherits_exact_registered_RH_without_pool_rewrite(self):
        import test_earnings_population_services as fixtures
        fixture=fixtures.PopulationAuthorAndFailureTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        registered=fixture.state['versions'][fixture.state['stable_id']]
        registered.update(axis='baseline',parent=None)
        before=deepcopy(fixture.state)
        fixture.test_author_original_projection_keeps_parent_feedback_and_changes_only_R_source()
        self.assertEqual(fixture.owner.case.call_args.args[0],registered)
        self.assertEqual(fixture.state,before)


if __name__=='__main__':unittest.main()
