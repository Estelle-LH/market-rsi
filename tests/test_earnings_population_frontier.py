"""Offline source-bound parent/feedback/pool tests; no API/scorer/Native/ledger.

Saved public artifacts are read for current-boundary tests. Inert role fixtures
test actual role guard and Author broker paths, not a fabricated model result.
"""
from copy import deepcopy
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import json
import unittest
from unittest.mock import patch

import earnings_population as pool
import earnings_population_clean_slate as clean
import earnings_population_coevolution as policy
import earnings_population_runtime as runtime
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population as pfixtures
import test_earnings_population_clean_slate as fixtures


class HistoricalGeneration1Tests(unittest.TestCase):
    def setUp(self):
        # Preserve this real generation1 regression after prospective routes advance.
        pinned=patch.object(policy,'PLAN',str(clean.training.ROOT/'TRAIN25-FRONTIER-ROUND9-SOURCE-PLAN-V2.json'))
        pinned.start();self.addCleanup(pinned.stop)
        self.plan=engine.read(engine.pin(policy.e.REPO/policy.PLAN))
        self.origin=engine.read(self.plan['origin']);self.claim=engine.read(self.origin['frontier_expansion'])
        self.frontier=engine.read(self.claim['frontier']);self.state=engine.read(self.origin['carried_population'])
    def altered(self,bound,value):
        original=policy.saved
        return patch.object(policy,'saved',side_effect=lambda b:deepcopy(value) if b==bound else original(b))
    def test_actual_new_selected_parent_not_incumbent_and_all375_feedback(self):
        origin=clean.round2_origin(dict(clean_learning_round=9,sources={policy.PLAN:engine.pin(policy.e.REPO/policy.PLAN)}))
        self.assertTrue(origin['parent']['id'].startswith('430f'));self.assertTrue(self.state['stable_id'].startswith('03a'))
        full=engine.read(origin['public_feedback'])
        for rows in (full['rows'],full['actual_parent']['rows'],full['selection_incumbent']['rows']):
            self.assertEqual(len(rows),25);self.assertEqual(sum(len(r['targets']) for r in rows),125)
        self.assertTrue(policy.feedback_expansion(full,self.state))
        self.assertEqual(policy.selection_threshold(origin),3.14)
        self.assertEqual(policy.selected_parent(self.state,origin)['id'],origin['parent']['id'])
        declared=policy.declared_test(origin)
        task=clean.research_task(dict(clean_learning_round=9,sources={policy.PLAN:engine.pin(policy.e.REPO/policy.PLAN)}))
        for key in ('hypothesis_id','question','support_observation','refute_observation'):
            self.assertIn(declared[key],task)
    def test_global_width_not_per_family_or_top_three_scalar(self):
        wrong=deepcopy(self.frontier);wrong['members']*=2
        with self.assertRaises(ValueError):policy.validate_frontier(wrong,self.state)
        wrong=deepcopy(self.frontier);wrong['incumbent_id']=wrong['members'][1]['version_id']
        with self.assertRaises(ValueError):policy.validate_frontier(wrong,self.state)
        self.assertEqual(policy.validate_frontier(self.frontier,self.state)['members'][1]['mean'],3.12)
    def test_provisional_evidence_next_test_exit_and_opportunity_cost_mandatory(self):
        for field in ('evidence','next_test','exit_criterion','opportunity_cost','observed_use','uncertainty'):
            bad=deepcopy(self.frontier);bad['members'][1][field]=[] if field=='evidence' else ''
            with self.subTest(field=field),self.assertRaises(ValueError):policy.validate_frontier(bad,self.state)
    def test_archived_nonmember_or_backfill_expansion_rejected(self):
        for changes in (dict(parent_id='0'*64),dict(historical_backfill=True),dict(prospective=False),dict(hypothesis_id='fill-missing-old-child')):
            with self.altered(self.origin['frontier_expansion'],dict(self.claim,**changes)),self.assertRaises(ValueError):policy.expansion(self.origin,self.plan)
    def test_incumbent_substitution_wrong_source_or_stale_feedback_rejected(self):
        for key,other in [('parent',self.state['versions'][self.state['stable_id']]),
                          ('prior_comparison',self.origin['parent_comparison'])]:
            with self.subTest(key=key),self.assertRaises(ValueError):policy.expansion(dict(self.origin,**{key:other}),self.plan)
        state=deepcopy(self.state);state['exposed_companies'].append('invented')
        with self.assertRaises(ValueError):policy.feedback_expansion(engine.read(self.origin['public_feedback']),state)
    def test_frontier_and_current_incumbent_cannot_diverge(self):
        for key,other in [('incumbent_descriptor',self.origin['prior_descriptor']),
                          ('incumbent_comparison',self.origin['parent_comparison']),('incumbent_mean',3.18),
                          ('group_start_stable',self.origin['parent_comparison'])]:
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'current prediction incumbent'):
                policy.expansion(dict(self.origin,**{key:other}),self.plan)
    def test_missing_full25_no_generation_transition(self):
        bound=self.frontier['members'][1]['report'];report=engine.read(bound);report['comparison']['scored']=24
        with self.altered(bound,report),self.assertRaises(ValueError):policy.validate_frontier(self.frontier,self.state)
    def test_missing_duplicate_or_fake_target_award_cannot_enter_frontier(self):
        bound=self.frontier['members'][1]['report']
        original=engine.read(bound)
        for targets in ([],original['comparison']['rows'][0]['targets'][:-1],
                        original['comparison']['rows'][0]['targets'][:-1]+original['comparison']['rows'][0]['targets'][:1]):
            bad=deepcopy(original);bad['comparison']['rows'][0]['targets']=targets
            with self.altered(bound,bad),self.assertRaisesRegex(ValueError,'all125'):policy.validate_frontier(self.frontier,self.state)
        for award in (True,.2,None):
            bad=deepcopy(original);bad['comparison']['rows'][0]['targets'][0]['candidate_award']=award
            with self.altered(bound,bad),self.assertRaisesRegex(ValueError,'all125'):policy.validate_frontier(self.frontier,self.state)
    def test_exact_existing_history_not_reinitialized_or_observations_faked(self):
        before=engine.read(self.frontier['preserved_population'])
        self.assertEqual(self.state['history'][:len(before['history'])],before['history'])
        self.assertEqual(self.state['observations'],before['observations'])
        self.assertEqual(self.state['exposed_companies'],before['exposed_companies'])
        with patch.object(pool,'initialize',side_effect=AssertionError('No initialization')):
            actual=clean.scaffold(dict(forecaster=engine.pin(policy.e.REPO/'tools/edgar_forecast_openai.py')),self.origin)
        self.assertEqual(actual,self.state)
    def test_two_parent_hypothesis_routes_declared_no_forced_third_seat(self):
        groups=self.frontier['expansions']
        self.assertEqual({g['parent_id'] for g in groups},{m['version_id'] for m in self.frontier['members']})
        self.assertTrue(all(len(g['children'])==2 for g in groups));self.assertEqual(len(self.frontier['members']),2)
    def test_budget_pending_and_retry_owner_paths_unchanged(self):
        self.assertEqual(policy.decision(304211145000,0,227840000,meaningful_next=True),'CONTINUE')
        self.assertEqual(policy.decision(387429960800,1,227840000,meaningful_next=True),'STOP_ORIGINAL_BUDGET_INSUFFICIENT')
        proposal=self.plan['proposal_id'];suffix=str(int(proposal.rsplit('-',1)[1])+1)
        policy.route(proposal,9,False,False)
        for ident,frozen,repair in [(proposal,True,False),('edgar-population-20261016-'+suffix,False,False),(proposal,False,True)]:
            with self.assertRaises(ValueError):policy.route(ident,9,frozen,repair)


class JournalTests(pfixtures.PopulationFixture):
    def test_two_actual_parents_children_preserve_archive_and_replay(self):
        state,explorer=self.retained()
        state=pool.project_frontier(state,self.stable['id'],[explorer['id']],reason='synthetic frontier',evidence=self.evidence)
        for parent in (self.stable,explorer):
            selected=policy.selected_parent(state,dict(logical_round=9,parent=parent))
            child=self.child(parent=selected,label=parent['id'])
            new=pool.retain(state,child,reason='distinct prospective child',evidence=self.evidence)
            self.assertEqual(new['versions'][child['id']]['parent'],parent['id'])
            self.assertEqual(pool.validate(new),new)
        parked=pool.project_frontier(state,self.stable['id'],[],reason='park other parent, not delete',evidence=self.evidence)
        self.assertEqual(parked['versions'],state['versions']);self.assertEqual(parked['observations'],state['observations'])
        self.assertEqual(parked['exposed_companies'],state['exposed_companies'])
        with self.assertRaises(ValueError):policy.selected_parent(parked,dict(logical_round=9,parent=explorer))
    def test_forged_projection_or_reset_not_accepted(self):
        state,explorer=self.retained();state=pool.project_frontier(state,self.stable['id'],[explorer['id']],reason='view',evidence=self.evidence)
        state['explorers']=[]
        with self.assertRaises(ValueError):pool.validate(state)
        with self.assertRaises(ValueError):pool.project_frontier(self.initial,self.stable['id'],['0'*64],reason='unknown',evidence=self.evidence)


class ParentRoleGuardTests(unittest.TestCase):
    def setUp(self):
        fixtures.CurrentGuardTests.setUp(self)
        self.child=deepcopy(self.f.population['versions'][self.f.population['stable_id']])
        source=self.f.save('explorer-R.py',{'not_executed':'distinct source'})
        self.child.update(R=source,parent=self.child['id'],axis='R')
        from market_rsi import digest
        self.child['id']=digest({a:self.child[a]['sha256'] for a in ('R','H')})
        self.task['scaffold']['versions'][self.child['id']]=self.child
        self.task['scaffold']['explorers']=[self.child['id']]
        self.f.packet['population']=deepcopy(self.task['scaffold']);self.f.save('packet-01.json',self.f.packet)
        self.f.manager.value['clean_learning_round']=9
        self.origin=dict(logical_round=9,parent=self.child)
        self.stack.enter_context(patch.object(clean,'round2_origin',return_value=self.origin))
        self.stack.enter_context(patch.object(runtime,'_local',side_effect=engine.read))
    def test_guard_selects_actual_explorer_for_controller_author_review_child(self):
        # Runtime's full binding list is separately checked by CurrentFrontierTests;
        # here focus the actual selection branch without a Native/model instance.
        with patch.object(clean,'second_round',return_value=False),patch.object(clean,'selected_parent',return_value=self.child):
            parent=clean.selection(self.f.manager,'controller',(self.f.packet,self.f.args('controller')[-1]),{})
            self.assertEqual(parent['version'],self.child)
    def test_wrong_parent_refused_before_author_or_review_execution(self):
        from market_rsi import digest
        chosen=dict(parent_pair_sha256=self.task['scaffold']['stable_id'],feedback_sha256=digest(self.task['feedback']))
        with patch.object(clean,'second_round',return_value=False),patch.object(clean,'selected_parent',return_value=self.child):
            with self.assertRaisesRegex(ValueError,'selected actual parent'):
                clean.selection(self.f.manager,'author',(chosen,self.f.packet['population'],self.f.args('author')[-1]),{})
    def test_review_native_selection_is_child_not_its_explorer_parent(self):
        from market_rsi import digest
        child=deepcopy(self.child);child['R']=self.f.save('new-child-R.py',{'different':'child'})
        child.update(parent=self.child['id'],id=digest({a:child[a]['sha256'] for a in ('R','H')}))
        with patch.object(clean,'second_round',return_value=False),patch.object(clean,'selected_parent',return_value=self.child):
            selected=clean.selection(self.f.manager,'review',(child,self.f.packet['population'],self.f.args('review')[-1]),{})
        self.assertEqual(selected['version'],child)
        wrong=deepcopy(child);wrong['parent']=self.task['scaffold']['stable_id']
        with patch.object(clean,'second_round',return_value=False),patch.object(clean,'selected_parent',return_value=self.child),self.assertRaises(ValueError):
            clean.selection(self.f.manager,'review',(wrong,self.f.packet['population'],self.f.args('review')[-1]),{})
    def test_actual_controller_case_and_prompt_two_distinct_selected_parents(self):
        from market_rsi import digest
        self.f.packet['parent_feedback_sha256']=digest(self.task['feedback'])
        captured=[]
        outer=self
        class Role:
            broker=SimpleNamespace(current_sources=lambda:dict(R='synthetic R',H='synthetic H'))
            def propose(self,prompt,slot):
                captured.append(prompt)
                original=outer.f.save('controller-response-'+str(len(captured))+'.json',{'synthetic':True})
                Path(slot).mkdir(parents=True)
                engine.save(Path(slot)/'decision.json',dict(original=original,decision=dict(parent_pair_sha256=prompt['active_versions'][0])))
                return original
        for parent in (self.child,self.task['scaffold']['versions'][self.task['scaffold']['stable_id']]):
            cases=[]
            def case(version,slot):
                cases.append(version)
                return dict(state_api=SimpleNamespace(tools=SimpleNamespace(files={'questions.md':'synthetic'})))
            service=SimpleNamespace(runtime={'clean_learning_round':9},case=case,role=lambda *args:Role())
            with patch.object(clean,'round2_origin',return_value=dict(logical_round=9,parent=parent)),patch.object(clean,'research_task',return_value='synthetic frontier question'):
                result=clean.controller(service,self.f.packet,str(self.f.root/('controller-case-'+str(len(captured)))))
            self.assertEqual(cases,[parent]);self.assertEqual(captured[-1]['active_versions'],[parent['id']])
            self.assertEqual(captured[-1]['stable_id'],self.task['scaffold']['stable_id'])
            self.assertEqual(engine.read(result)['parent_pair_sha256'],parent['id'])


class CompleteFeedbackLoopTests(unittest.TestCase):
    def test_multiversion_observation_exposure_seed_and_restart_keep_complete_feedback(self):
        import test_earnings_population_loop as fixture
        import earnings_population_loop as loop
        case=fixture.PopulationLoopTests();case.setUp();self.addCleanup(case.doCleanups)
        state,child=case.retained()
        state=case.observed(state,'synthetic-prior',{case.stable['id']:1,child['id']:1.5})
        full=case.artifact(dict(schema='earnings_training25_public_summary_v1',
            rows=[dict(company_id=str(i),targets=[dict(target_id=str(t)) for t in range(5)]) for i in range(25)]),'complete25')
        case.trace=['continue']
        def invoke():
            return loop.run(case.loop_root,state,['synthetic-exposed'],case.services(),
                admit=lambda ctx:ctx['stage']!='execute',max_rounds=1,identity=lambda:case.identities,initial_feedback=full)
        # Exact immutable opt-in is separately tested above using actual artifacts;
        # this inert callback fixture isolates loop precedence/restart behavior.
        with patch.object(policy,'feedback_expansion',return_value=True):
            result=invoke();counts={k:len(v) for k,v in case.calls.items()};again=invoke()
        self.assertEqual(result,again);self.assertEqual(counts,{k:len(v) for k,v in case.calls.items()})
        self.assertEqual(case.calls['controller'][0]['feedback'],full)
        self.assertEqual(case.calls['controller'][0]['population'],state)
        self.assertEqual(case.calls['forecast'],[]);self.assertEqual(result['stage'],'execute')
        self.assertIn('Reused training',case.calls['controller'][0]['scope'])


class CurrentSourcePagingTests(pfixtures.PopulationFixture):
    """Exercise actual broker dispatch/receipts; never execute synthetic sources."""
    def setUp(self):
        super().setUp()
        from earnings_population_broker import PopulationBroker
        self.text='#é\n'*13000
        self.parent=pool.version(self.artifact(self.text,'large-R'),self.h)
        self.broker=PopulationBroker.__new__(PopulationBroker)
        b=self.broker;b.root=self.root/'broker';b.root.mkdir()
        b.identity=(b.root.stat().st_dev,b.root.stat().st_ino)
        b.clean_slate_runtime_binding=self.artifact(dict(clean_slate_policy=clean.POLICY,clean_learning_round=9),'runtime')
        b.research_context_binding=None;b.prior_files=None;b.versions={self.parent['id']:self.parent}
        b.current_sources=lambda:{axis:Path(self.parent[axis]['path']).read_text() for axis in ('R','H')}
        b.calls=0;b.returned=0;b.failed=set();b.definitions=b._definitions()
    def test_bounded_default_and_existing_pages_losslessly_recover_exact_source(self):
        first=self.broker.dispatch('read_current_program',{'axis':'R'})
        row=first['value'];self.assertFalse(row['complete_source'])
        self.assertEqual(len(row['source_text']),4000)
        self.assertEqual(row['source_sha256'],self.parent['R']['sha256'])
        self.assertLess(len(json.dumps(row).encode()),len(json.dumps({'source_text':self.text}).encode())/2)
        text=row['source_text']
        while row['next_offset']<row['total_characters']:
            row=self.broker.dispatch('read_population_program',dict(version_id=self.parent['id'],axis='R',offset=row['next_offset'],characters=4000))['value']
            text+=row['text']
        self.assertEqual(text,self.text)
        self.assertEqual(engine.read(first['research_receipt'])['value']['source_text'],self.text[:4000])
    def test_wrong_native_pair_stays_closed_without_auto_retry(self):
        self.broker.current_sources=lambda:dict(R='changed',H=Path(self.h['path']).read_text())
        with self.assertRaisesRegex(ValueError,'Native pair'):self.broker.dispatch('read_current_program',{'axis':'R'})
        calls=self.broker.calls
        with self.assertRaisesRegex(ValueError,'stays closed'):self.broker.dispatch('read_current_program',{'axis':'R'})
        self.assertEqual(self.broker.calls,calls)
    def test_original_call_and_return_bounds_and_invalid_axis_remain(self):
        with self.assertRaises(ValueError):self.broker.dispatch('read_current_program',{'axis':'K'})
        self.assertEqual(self.broker.calls,0)
        self.broker.returned=2_000_000
        with self.assertRaisesRegex(ValueError,'return budget'):self.broker.dispatch('read_current_program',{'axis':'R'})
        self.broker.calls=64
        with self.assertRaisesRegex(ValueError,'budget drift'):self.broker.dispatch('read_current_program',{'axis':'H'})
    def test_legacy_current_getter_and_global_definitions_not_changed(self):
        from earnings_open_broker import ResearchBroker
        original=ResearchBroker._definitions(self.broker)
        self.assertNotEqual(next(t for t in original if t['name']=='read_current_program')['description'],
                            next(t for t in self.broker.definitions if t['name']=='read_current_program')['description'])
        self.broker.clean_slate_runtime_binding=None;self.broker.definitions=self.broker._definitions()
        value=self.broker.dispatch('read_current_program',{'axis':'R'})['value']
        self.assertEqual(value['source_text'],self.text);self.assertNotIn('complete_source',value)


class FrontierAuthorReceivingTests(unittest.TestCase):
    def setUp(self):
        pinned=patch.object(policy,'PLAN',str(clean.training.ROOT/'TRAIN25-FRONTIER-ROUND9-SOURCE-PLAN-V2.json'))
        pinned.start();self.addCleanup(pinned.stop)
        fixtures.AuthorReceivingTests.setUp(self)
        self.incumbent=deepcopy(self.parent);self.incumbent['id']='f'*64
        self.task['scaffold'].update(stable_id=self.incumbent['id'],explorers=[self.parent['id']])
        self.task['scaffold']['versions'][self.incumbent['id']]=self.incumbent
        self.base.versions=deepcopy(self.task['scaffold']['versions'])
        value=dict(clean_slate_policy=clean.POLICY,clean_learning_round=9,
            sources={policy.PLAN:engine.pin(policy.e.REPO/policy.PLAN)})
        Path(self.runtime['path']).write_text(json.dumps(value));self.base.clean_slate_runtime_binding=engine.pin(Path(self.runtime['path']))
        self.origin=dict(logical_round=9,parent=self.parent)
        actual_task=clean.research_task(dict(clean_learning_round=9,sources={policy.PLAN:engine.pin(policy.e.REPO/policy.PLAN)}))
        self.context['task']=actual_task
        self.context_path.write_text(json.dumps(self.context));self.base.population_context_binding=engine.pin(self.context_path)
        self.p2=patch.object(clean,'round2_origin',return_value=self.origin);self.p2.start();self.addCleanup(self.p2.stop)
    def test_actual_author_receives_selected_explorer_sources_and_complete_feedback(self):
        from earnings_open_program import program
        self.author.author(self.chosen,program(self.r.read_bytes(),'R'),str(self.root/'selected-parent-slot'),parent_binding=self.parent['R'])
        context=self.received[0]['research_context']
        self.assertEqual(context['parent_version_id'],self.parent['id'])
        self.assertNotEqual(context['parent_version_id'],self.incumbent['id'])
        self.assertEqual(sum(len(r['targets']) for r in context['feedback']['rows']),125)
        self.assertIn('430f-context-history',context['task'])
        self.assertIn('support_observation',context['task']);self.assertIn('refute_observation',context['task'])
    def test_incumbent_context_substitution_never_reaches_author_transport(self):
        self.context['parent_version_id']=self.incumbent['id']
        self.context['parent_programs']=self.base.references()[self.incumbent['id']]
        self.context_path.write_text(json.dumps(self.context));self.base.population_context_binding=engine.pin(self.context_path)
        with self.assertRaises(ValueError):self.base.research_context()
        self.assertEqual(self.received,[])

class CurrentFrontierBindingTests(unittest.TestCase):
    """Current prospective binding, independently of preserved historical fixtures."""
    def setUp(self):
        self.plan=engine.read(engine.pin(policy.e.REPO/policy.PLAN))
        self.origin=engine.read(self.plan['origin'])
        self.claim=engine.read(self.origin['frontier_expansion'])
        self.frontier=engine.read(self.claim['frontier'])
        self.state=engine.read(self.origin['carried_population'])
    def test_exact_current_parent_full_feedback_and_incumbent(self):
        self.assertEqual(policy.expansion(self.origin,self.plan),self.claim)
        self.assertEqual(policy.selected_parent(self.state,self.origin),self.origin['parent'])
        self.assertEqual(self.state['stable_id'],self.frontier['incumbent_id'])
        feedback=engine.read(self.origin['public_feedback'])
        for rows in (feedback['rows'],feedback['actual_parent']['rows'],feedback['selection_incumbent']['rows']):
            self.assertEqual([x['company_id'] for x in rows],self.frontier['training'])
            self.assertEqual(sum(len(x['targets']) for x in rows),125)
        self.assertTrue(policy.feedback_expansion(feedback,self.state))
    def test_current_route_has_no_old_proposal_or_automatic_retry(self):
        n=self.plan['logical_round'];identifier=self.plan['proposal_id']
        review_only=clean.case_contract_review(identifier)
        if review_only:
            descriptor={clean.FIXTURE_REVIEW_ID:clean.FIXTURE_REVIEW_DESCRIPTOR,
                clean.CASE_EXPECTATION_REVIEW_ID:clean.CASE_EXPECTATION_DESCRIPTOR,
                clean.ACQUISITION_REVIEW_ID:clean.ACQUISITION_REVIEW_DESCRIPTOR}[identifier]
            clean.repair_metadata(descriptor,identifier)
        policy.route(identifier,n,False,review_only)
        policy.route(identifier.rsplit('-',1)[0]+'-'+str(int(identifier.rsplit('-',1)[1])+1),n,True,False)
        for frozen,repair in ((True,False),(False,not review_only)):
            with self.assertRaises(ValueError):policy.route(identifier,n,frozen,repair)
        with self.assertRaises(ValueError):policy.route(identifier,n-1,False,False)
    def test_all_registered_history_and_exposure_preserved(self):
        before=engine.read(self.frontier['preserved_population'])
        self.assertEqual(self.state['history'][:len(before['history'])],before['history'])
        self.assertEqual(self.state['observations'],before['observations'])
        self.assertEqual(self.state['exposed_companies'],before['exposed_companies'])
        self.assertTrue(all(self.state['versions'][k]==v for k,v in before['versions'].items()))
        self.assertLessEqual(len(self.frontier['members']),3)
    def test_parent_not_silently_replaced_or_promoted(self):
        if self.origin['parent']['id']!=self.state['stable_id']:
            bad=dict(self.origin,parent=self.state['versions'][self.state['stable_id']])
            with self.assertRaises(ValueError):policy.expansion(bad,self.plan)
        self.assertEqual(policy.selection_threshold(self.origin),self.origin['incumbent_mean'])


class HistoricalGeneration2Tests(unittest.TestCase):
    def setUp(self):
        self.plan=engine.read(engine.pin(clean.training.ROOT/'TRAIN25-FRONTIER-ROUND10-SOURCE-PLAN.json'))
        self.origin=engine.read(self.plan['origin'])
        self.frontier=engine.read(engine.read(self.origin['frontier_expansion'])['frontier'])
    def test_losing_H_explorer_is_not_prediction_adoption(self):
        self.assertTrue(self.origin['parent']['id'].startswith('e8b689'))
        self.assertEqual(self.origin['prior_mean'],2.94)
        self.assertEqual(self.origin['incumbent_mean'],3.14)
        self.assertTrue(self.frontier['incumbent_id'].startswith('03a'))
        self.assertEqual(len(self.frontier['members']),2)
        for group in self.frontier['expansions']:
            self.assertLessEqual(len(group['children']),1)
            self.assertTrue(group['omitted_expansion_reason'])
    def test_no_model_or_budget_resource_change(self):
        before=engine.read(engine.pin(clean.training.ROOT/'TRAIN25-FRONTIER-ROUND9-SOURCE-PLAN-V2.json'))
        changed={'logical_round','proposal_id','origin','frontier_expansion','group_id','group_parent_id','group_parent_mean','discriminating_next'}
        self.assertEqual({k:v for k,v in before.items() if k not in changed},
                         {k:v for k,v in self.plan.items() if k not in changed})
        self.assertFalse(self.plan['budget_change']);self.assertFalse(self.plan['automatic_retry'])
        self.assertFalse(self.plan['heldout_access'])
        self.assertEqual((self.plan['max_concurrent_companies'],self.plan['max_inflight_per_company']),(8,1))
    def test_saved_H_execution_and_rejection_not_quality_claims(self):
        diagnostic=engine.read(self.origin['supervisor_diagnostic'])
        self.assertEqual((diagnostic['actual_H_execution_companies'],diagnostic['actual_isolated_H_calls'],diagnostic['public_H_call_attempts']),(22,107,110))
        self.assertEqual(len(diagnostic['pre_H_rejections']),3)
        self.assertEqual(diagnostic['current_R_reported_history_coverage'],dict(targets=125,histories_sufficient=7,validated=2,departures=0))
        self.assertIn('before',diagnostic['execution_order'])


if __name__=='__main__':unittest.main()
