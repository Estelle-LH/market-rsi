"""Services proposal input/transport tests; no provider, QA or candidate execution.

Root's prospective runtime.proposal_task and full training admission are explicit
metadata seams. Real Services, open-role packing/decoding and literal assembly
are used; scripted paid transport is not physical provider or ledger evidence.
"""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from edgar_forecast_tools import FilingTools
import earnings_open_context as packing
import earnings_open_roles as roles
import earnings_population_campaign_context as context
import earnings_population_runtime as runtime
import earnings_population_services as services
import earnings_population_training25 as training
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_roles as transport_fixture
import test_earnings_population_case as case_fixture
import test_earnings_population_parent_probe as probe_fixture
import test_earnings_population_training35_reuse as scope_fixture


class ProposalServicesTests(unittest.TestCase):
    def setUp(self):
        self.scope_fixture=scope_fixture.ScopeFixture(); self.scope_fixture.setUp()
        self.addCleanup(self.scope_fixture.doCleanups); self.scope=self.scope_fixture.scope
        self.f=case_fixture.PopulationCaseTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.company=self.f.company(scope_fixture.COMPANY)['company']
        self.task=dict(schema='earnings_training25_new_panel_proposal_task_v1',
            policy='round0_new_panel_candidate_v1',authority=dict(
                path=str(training.ROOT/'TRAIN25-DIRECT-NEW-CANDIDATE-AUTHORITY.json'),
                sha256='4aa5c123d6ab86c65673abd9502d7e59a9cd88cb5e6031016d9192c1b71933df'),
            split=deepcopy(self.scope['split']),round0_manifest=dict(
                path=str(training.ROOT/'TRAIN25-PLAIN-COMPARATOR-MANIFEST.json'),
                sha256='7a43ee9cac7204ef664d134c2e5effac14e2422aa9cedc207f66fcfe55ef07a3'),
            training_companies=deepcopy(self.scope['training']),
            primary_task='One fresh transferable R/H method informed by all125 original Round0 public prediction/award pairs; success decided by same frozen code across all25, no per-company mutation',
            smoke_company_id=self.company['cik'],smoke_only=True,archive_only_version_ids=[
                '1167a7efab99330677db3a80690bd44a6f17d1e77120f90f2b182771ad2f3b33',
                '3392fd6008ee9dd1ce779d3c27a8cd0283209659b664d25db3681767211bd6b9'])
        self.summary=dict(schema='earnings_training25_public_summary_v1',split=self.task['split'],
            manifest=self.task['round0_manifest'],target_order=['T%03d'%i for i in range(1,6)],
            rows=[dict(company_id=cik,points=3,targets=[dict(target_id='T%03d'%i,
                predicted_value=str(index*10+i),points_awarded=1 if i<4 else 0) for i in range(1,6)])
                for index,cik in enumerate(self.scope['training'])])
        self.origin=engine.save(self.f.root/'origin.json',{'scientific_predecessor':'invented immutable metadata'})
        self.study=engine.save(self.f.root/'study.json',dict(campaign_origin=self.origin,continuation=None))
        self.feedback=dict(company_id=self.company['cik'],scope='Invented prior feedback; not baseline Native')
        self.feedback_bound=engine.save(self.f.root/'feedback.json',self.feedback)
        self.campaign=dict(campaign=self.f.authority,origin=self.origin,feedback_binding=self.feedback_bound,
            original_R_evidence_abi={'synthetic':True},prior_candidate={'reference_only':True},
            failure_evidence_context=None,training_scope=deepcopy(self.scope),
            training_comparator=deepcopy(self.summary),training_state={'synthetic_prior_state':True},
            research_context=dict(schema='earnings_repair_context_v1',human_task='Old training task',
                prior_candidate={'reference_only':True},verification='Synthetic ABI',non_claims='No gain',
                observations=dict(training_comparator=deepcopy(self.summary),feedback_binding=self.feedback_bound)))
        self.owner=services.Services.__new__(services.Services)
        self.owner.runtime=dict(training_proposal_policy=self.task['policy'],companies=[self.company['cik']],
            forecast_study=self.study,sources={},root=str(self.f.root),id='edgar-population-20261016-37')
        self.owner._training_scope=Mock(return_value=self.scope)
        self.owner.native_root=self.f.root; self.owner.authored={}; self.owner.traces={}
        self.owner.current=self.company['cik']; self.owner.runner=Mock(); self.owner.literature=Mock()
        self.owner.campaign_context=deepcopy(self.campaign); self.owner.prior_feedback=deepcopy(self.feedback)
        self.case=dict(company=self.company,state_api=SimpleNamespace(tools=FilingTools(self.company)))
        self.owner.case=Mock(return_value=self.case)
        self.api=patch.object(runtime,'proposal_task',create=True,return_value=deepcopy(self.task))
        self.api_mock=self.api.start(); self.addCleanup(self.api.stop)
        self.state=dict(stable_id=self.f.version['id'],explorers=[self.task['archive_only_version_ids'][1]],
            versions={self.f.version['id']:deepcopy(self.f.version),
                self.task['archive_only_version_ids'][1]:dict(deepcopy(self.f.version),
                    id=self.task['archive_only_version_ids'][1])})

    def transport(self,role):
        t=transport_fixture.OpenRoleTests(); t.setUp(); self.addCleanup(t.doCleanups)
        base=t.service(author=role=='author',max_turns=2,limits=dict(
            max_input_tokens=96000 if role=='author' else 32000,
            max_output_tokens=49152 if role=='author' else 16384,wall_seconds=1200 if role=='author' else 900))
        t.factory.return_value.post.return_value={'input_tokens':100}
        owner=self.owner; source={a:Path(self.f.version[a]['path']).read_text() for a in ('R','H')}
        class Broker(transport_fixture.Broker):
            def current_sources(inner):return deepcopy(source)
            def current_programs(inner):return services.program_references(source)
            def references(inner):return {ident:services.program_references(source) for ident in owner.state['versions']}
            def available_traces(inner):return {}
            def research_context(inner,*,include_source=False):
                return engine.read(owner.author_context) if hasattr(owner,'author_context') else deepcopy(owner.campaign_context['research_context'])
            def dispatch(inner,name,args):
                if name=='read_current_program':return {'value':{'source_text':source[args['axis']]}}
                return super().dispatch(name,args)
        broker=Broker(); owner.state=self.state
        def make(name,kind,case,slot):
            return kind(base.binding,budget=t.budget,client_factory=t.factory,broker=broker,max_turns=2)
        owner.role=Mock(side_effect=make)
        return t

    def choice(self,transport):
        value=transport.choice(); value.update(parent_pair_sha256=self.f.version['id'],
            feedback_sha256=digest(self.feedback_bound),retire_branch_id=self.state['explorers'][0])
        return value

    def assert_pairs(self,value):
        self.assertEqual(value,self.summary)
        self.assertEqual(len(value['rows']),25)
        self.assertEqual(sum(len(row['targets']) for row in value['rows']),125)

    def test_real_controller_first_and_final_requests_keep_whole25_task_and125_pairs(self):
        t=self.transport('controller'); choice=self.choice(t)
        t.generations=[t.tool_response(t.call('read','read_current_program',{'axis':'R'})),t.message(choice)]
        packet=dict(company_id=self.company['cik'],population=self.state,round_index=1,
            feedback=self.feedback_bound,parent_feedback_sha256=digest(self.feedback_bound),scope='Prior single company')
        with patch.object(services,'public_feedback',return_value=deepcopy(self.feedback)), \
             patch.object(context,'prepare',return_value=deepcopy(self.campaign)), \
             patch.object(roles,'budgeted_response',side_effect=t.fake_paid):
            bound=self.owner.controller(packet,str(t.slot))
        self.assertEqual(engine.read(bound)['parent_pair_sha256'],self.f.version['id'])
        self.assertEqual(len(t.requests),2); self.assertEqual(t.requests[-1]['tool_choice'],'none')
        for request in t.requests:
            prompt=json.loads(request['input'][0]['content'])
            self.assertEqual(prompt['proposal_task'],self.task)
            self.assertIn(self.task['primary_task'],prompt['research_objective'])
            self.assertIn('smoke only',prompt['scope'])
            self.assert_pairs(prompt['research_context']['observations']['training_comparator'])
            self.assertNotIn(self.task['archive_only_version_ids'][1],prompt['active_versions'])
            self.assertIn(self.task['archive_only_version_ids'][1],prompt['explorers'])

    def test_real_author_first_and_final_requests_fresh_literal_source_and125_pairs(self):
        t=self.transport('author'); chosen=self.choice(t); chosen.pop('retire_branch_id')
        before=Path(self.f.r['path']).read_text(); after=before.replace('return {}',"return {'fresh_method': True}")
        reply=dict(decision_sha256=digest(chosen),parent_source_sha256=self.f.r['sha256'],
            edits=[dict(kind='replace',old_text='return {}',new_text="return {'fresh_method': True}")],
            test_text="CASES=[{'input':{},'expected':{'fresh_method':True}}]")
        t.generations=[t.tool_response(t.call('parent','read_current_program',{'axis':'R'})),t.message(reply)]
        with patch.object(roles,'budgeted_response',side_effect=t.fake_paid), \
             patch.object(services,'implementation_base',return_value=None):
            child=self.owner.author(chosen,self.state,str(t.slot))
        self.assertEqual(child['parent'],self.f.version['id'])
        self.assertNotIn(child['id'],self.state['versions'])
        self.assertEqual(Path(child['R']['path']).read_text(),after)
        self.assertEqual(len(t.requests),2); self.assertEqual(t.requests[-1]['tool_choice'],'none')
        for request in t.requests:
            supplied=json.loads(request['input'][0]['content'])['research_context']
            self.assertEqual(supplied['proposal_task'],self.task)
            self.assertIn(self.task['primary_task'],supplied['task'])
            self.assertIn('integration smoke only',supplied['task'])
            self.assert_pairs(supplied['training_comparator'])
        self.assertFalse(self.f.marker.exists())

    def test_present_malformed_task_or_scope_refuses_before_case_or_model(self):
        variants=[None,dict(self.task,authority=dict(self.task['authority'],sha256='0'*64)),
            dict(self.task,training_companies=self.task['training_companies'][:-1]),
            dict(self.task,split=None),dict(self.task,smoke_only=False),dict(self.task,primary_task=''),
            dict(self.task,round0_manifest=None),dict(self.task,archive_only_version_ids=[])]
        for task in variants:
            self.api_mock.return_value=task
            with self.subTest(task=task),self.assertRaises(ValueError):self.owner._proposal_task()
        self.owner.case.assert_not_called()

    def test_exact125_missing_or_reordered_pairs_refuse(self):
        for mutate in (lambda s:s['rows'].pop(),lambda s:s['rows'][0]['targets'].pop(),
                       lambda s:s['rows'].reverse()):
            self.owner.campaign_context=deepcopy(self.campaign)
            mutate(self.owner.campaign_context['training_comparator'])
            with self.assertRaises(ValueError):self.owner._proposal_context(self.task)

    def test_archive_parent_refused_before_author_case_or_tool(self):
        for ident in self.task['archive_only_version_ids']:
            with self.subTest(parent=ident),self.assertRaisesRegex(ValueError,'archive|Archive'):
                self.owner.author(dict(parent_pair_sha256=ident),self.state,str(self.f.root/'not-created'))
        self.owner.case.assert_not_called()

    def test_old_stage_attachment_or_reused_origin_refuses(self):
        for value in (dict(campaign_origin=self.origin,training_stage_attachment={}),
                      dict(campaign_origin=engine.save(self.f.root/'reused-origin.json',{'author_stage_reuse':{}}))):
            self.owner.runtime['forecast_study']=engine.save(self.f.root/('study-'+digest(value)+'.json'),value)
            with self.assertRaisesRegex(ValueError,'cannot reuse'):self.owner.reused_author()

    def test_legacy_absent_marker_does_not_call_prospective_receiver_or_change_context(self):
        del self.owner.runtime['training_proposal_policy']
        original=deepcopy(self.owner.campaign_context)
        self.assertIsNone(self.owner._proposal_task())
        self.owner._proposal_context(None)
        self.api_mock.assert_not_called(); self.assertEqual(self.owner.campaign_context,original)

    def test_present_marker_never_treats_missing_future_receiver_as_success(self):
        self.api_mock.side_effect=RuntimeError('future receiver unavailable')
        with self.assertRaisesRegex(RuntimeError,'future receiver unavailable'):self.owner._proposal_task()

    def test_original_pack_fallback_preserves_first_and_final_full_task_and_pairs(self):
        self.owner._proposal_context(self.task)
        for author in (False,True):
            for final in (False,True):
                packet=dict(research_context=deepcopy(self.owner.campaign_context['research_context']),
                    proposal_task=deepcopy(self.task))
                fmt={'name':'earnings_population_delta_author_v1' if author else 'earnings_population_decision_v1',
                    'schema':{'properties':{k:{} for k in ('decision_sha256','parent_source_sha256','edits','test_text')}}}
                request=dict(model='gpt-6.1-sol',text={'format':fmt},tool_choice='none' if final else 'auto',
                    input=[dict(role='user',content=json.dumps(packet)),dict(type='function_call',call_id='old',
                        name='search_literature',arguments='{}'),dict(type='function_call_output',call_id='old',output='x'*90000),
                        dict(type='function_call',call_id='new',name='read_current_program',arguments='{"axis":"R"}'),
                        dict(type='function_call_output',call_id='new',output='{"value":{"source_text":"PROGRAM={}"}}')])
                count=iter([96001]*3+[100] if author and final else [96001,100])
                client=SimpleNamespace(post=lambda *_:{'input_tokens':next(count)})
                out=self.f.root/f'pack-{author}-{final}';out.mkdir()
                packed=packing.pack(client,request,{'max_input_tokens':96000 if author else 32000},out,1,
                    author_final=author and final)
                self.assertEqual(json.loads(packed['input'][0]['content']),packet)


class ProposalReviewSmokeTests(unittest.TestCase):
    def test_original_scripted_probes_and_review_preserve_smoke_only_goal(self):
        fixture=probe_fixture.MatchedParentProbeTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        task=dict(primary_task='Evaluate ONE transferable method across all25 after freezing code.',
            archive_only_version_ids=[],smoke_company_id=fixture.company['cik'])
        fixture.owner._proposal_task=Mock(return_value=task)
        fixture.owner.reused_author=Mock(return_value=None)
        result=fixture.invoke()
        prompt=fixture.prompts[0]
        self.assertEqual(prompt['proposal_task'],task)
        self.assertIn('smoke only',prompt['evaluation_scope'])
        self.assertIn('not full25',prompt['evaluation_scope'])
        self.assertEqual(result['accepted_for_exploration'],False)
        controller_payload=fixture.owner.runner.invocations[2]['payload']
        self.assertIn(task['primary_task'],controller_payload['research_objective'])
        self.assertIn('integration smoke only',controller_payload['research_objective'])
        self.assertFalse(fixture.fixture.marker.exists())


if __name__=='__main__':unittest.main()
