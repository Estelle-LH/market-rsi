"""Synthetic follow-through orchestration; no host candidate execution or provider."""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import earnings_open_assembly as assembly
import earnings_open_author_followthrough as flow
import earnings_native_namespace as native_namespace
from earnings_capacity_adapter import author_payload
from earnings_open_program import candidate
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_capacity as native_fixture


class AuthorFollowthroughTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()
        self.chosen={'schema':'earnings_capacity_decision_v1','axis':'R','component':'research_policy',
            'parent_pair_sha256':'a'*64,'feedback_sha256':'b'*64,
            'hypothesis':'Implement one invented header-binding repair.',
            'expected_effect':'earnings-shadow-v2|research_policy|score_out_of_5|higher|0.5|score_nonregression|matched_trial_only'}
        self.authored={'decision_sha256':digest(self.chosen),
            'source_text':"PROGRAM={'axis':'R'}\ndef run(p): return {'invented': 2}\n",
            'test_text':"CASES=[{'input':{},'expected':{'invented':2}}]"}
        self.original={'status':'completed','error':None,'output':[{'type':'message','role':'assistant',
            'content':[{'type':'output_text','text':json.dumps(self.authored)}]}]}

    def gate_fixture(self):
        bound=engine.save(self.root/'original.json',self.original)
        decoded=candidate(self.original,{'axis':'R'},self.chosen)
        cases={'passed':True,'source_sha256':decoded['source_sha256'],'error_type':None,
               'cases':[{'passed':True,'case':decoded['cases'][0]}]}
        cases_binding=engine.save(self.root/'cases.json',cases)
        static=engine.save(self.root/'static.json',{'passed':True,'program_cases':cases_binding})
        result={'decision':self.chosen,'original':bound}
        spec={'static_review':static,'review_receipt':None,
              'after':{'components':{'R':{'sources':{flow.CHILD:decoded['source_sha256']}}}}}
        review={'verdict':'PASS_AUTHOR_CANDIDATE_ONE_FORECAST','blocking_findings':[],
                'reviewer':'independent-fixture-reviewer','author_original':bound,
                'candidate_source_sha256':decoded['source_sha256'],'test_source_sha256':decoded['test_source_sha256']}
        return result,spec,review,cases,decoded

    def test_factories_enable_only_assigned_role_and_forward_owned_dependencies(self):
        broker,study,kernel,clock,transport,budget,client=[object() for _ in range(7)]
        for enabled in ('author','forecast'):
            with mock.patch.object(assembly,'OpenAuthor') as author, mock.patch.object(assembly,'CapacityForecast') as forecast:
                factories=assembly.followthrough_factories(enabled=enabled,broker=broker,study=study,
                    kernel=kernel,clock=clock,transport=transport)
                self.assertEqual(set(factories),{'controller','author','review','forecast'})
                for role,factory in factories.items():
                    callback=factory('context',budget=budget,client_factory=client)
                    if role!=enabled:
                        with self.assertRaises(ValueError): callback('unused')
                if enabled=='author':
                    author.assert_called_once_with('context',budget=budget,client_factory=client,broker=broker,socket_timeout_seconds=900)
                    forecast.assert_not_called()
                else:
                    forecast.assert_called_once_with('context',budget=budget,client_factory=client,study_binding=study,
                        evaluation_kernel=kernel,clock_binding=clock,transport_policy_binding=transport)
                    author.assert_not_called()
        for mode in ('controller','review',None,True):
            with self.assertRaises(ValueError): assembly.followthrough_factories(enabled=mode,broker=broker,
                study=study,kernel=kernel,clock=clock,transport=transport)

    def author_run(self, response=None, failure=None):
        home=self.root/'author-stage'
        runtime={'id':'synthetic-author12','root':str(home),'source_commit':'c'*40,
            'cutoff_utc':'2099-01-01T00:00:00Z','deadline_utc':'2099-01-01T00:01:00Z',
            'slots':{'author':[str(home/'roles/author-01')]}}
        grant=engine.save(self.root/'grant.json',{'scorer':{'synthetic':True},'qa':{'synthetic':True}})
        value={'stage':'author','prior':{'decision':deepcopy(self.chosen)},'grant':grant,
            'study':{'synthetic':'study'},'runtime':{'synthetic':'runtime'},'forecast_transport':{'synthetic':'transport'}}
        context=self.root/'context.json'; context.write_text('{}')
        terminal=engine.save(self.root/'terminal.json',{'status':'COMPLETED_COMPONENT_CONTEXT'})
        seen={'owner_closed':False,'decisions':[]}
        parent=self
        class StubAuthor:
            def __init__(inner, context, **kwargs):
                seen['socket']=kwargs['socket_timeout_seconds']; seen['broker']=kwargs['broker']
            def author(inner, chosen, before, slot):
                seen['decisions'].append(deepcopy((chosen,before,slot)))
                if failure: raise failure
                Path(slot).mkdir(parents=True,exist_ok=False)
                return engine.save(Path(slot)/'response.json',response or parent.original)
        @contextmanager
        def owner(binding, *, client_factory, role_factories):
            self.assertEqual(binding,value['runtime'])
            callbacks={role:factory('owned-context',budget='owned-budget',client_factory='owned-client')
                       for role,factory in role_factories.items()}
            for role in ('controller','review','forecast'):
                with self.assertRaises(ValueError): callbacks[role]()
            try: yield {'roles':callbacks}
            finally: seen['owner_closed']=True
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(flow,'validate_prepared',return_value=(value,runtime)))
            stack.enter_context(mock.patch.object(flow,'capture_or_load',return_value=({},'clock-binding')))
            stack.enter_context(mock.patch.object(flow,'native',return_value=object()))
            stack.enter_context(mock.patch.object(flow.original_capacity,'task',return_value=({'synthetic':True},{})))
            for name in ('DockerRunner','ResearchBroker','LiteratureBroker'):
                stack.enter_context(mock.patch.object(flow,name,return_value=object()))
            stack.enter_context(mock.patch.object(flow,'containers_remaining',return_value=71))
            stack.enter_context(mock.patch.object(flow,'CONTEXT',context))
            stack.enter_context(mock.patch.object(flow,'open_capacity_runtime',side_effect=owner))
            stack.enter_context(mock.patch.object(flow,'owner_terminal',return_value=terminal))
            stack.enter_context(mock.patch.object(assembly,'OpenAuthor',StubAuthor))
            try: result=flow.run_author({'synthetic':'prepared'},{'synthetic':'review'})
            except Exception as error: return seen,home,error,None
        return seen,home,None,result

    def test_actual_orchestrator_uses_assembly_factories_exact_decision_and_unchanged_source(self):
        chosen=deepcopy(self.chosen)
        seen,home,error,binding=self.author_run()
        self.assertIsNone(error)
        result=engine.read(binding)
        self.assertEqual(seen['decisions'],[(chosen,{'axis':'R'},str(home/'roles/author-01'))])
        self.assertEqual(seen['socket'],900); self.assertTrue(seen['owner_closed'])
        self.assertEqual(author_payload(engine.read(result['original'])),self.authored)
        self.assertEqual(result['decision'],chosen)
        self.assertIs(result['candidate_applied'],False); self.assertEqual(result['new_forecasts'],0)
        self.assertEqual(self.chosen,chosen)

    def test_failed_or_incomplete_author_never_publishes_success_or_forecast(self):
        for i,incomplete in enumerate((False,True)):
            # Each failure uses its own synthetic owned root; no failed-ID retry.
            self.root=self.root/str(i); self.root.mkdir()
            response={'status':'incomplete','error':None,'incomplete_details':{'reason':'max_output_tokens'},'output':[]}
            seen,home,error,binding=self.author_run(response=response if incomplete else None,
                failure=None if incomplete else RuntimeError('synthetic fail-stop'))
            self.assertIsNotNone(error); self.assertIsNone(binding); self.assertTrue(seen['owner_closed'])
            self.assertFalse((home/'author-result.json').exists())
            self.assertFalse((home/'followthrough-result.json').exists())
            self.assertFalse((home/'code').exists())  # Stubbed runner did not execute anything.

    def test_candidate_gate_accepts_exact_literal_cases_source_and_distinct_review(self):
        result,spec,review,_,decoded=self.gate_fixture()
        authored,actual=flow.candidate_gate(result,spec,review)
        self.assertEqual(authored,self.authored); self.assertEqual(actual,decoded)

    def test_candidate_gate_rejects_failed_cases_wrong_source_review_or_ordinary_adoption(self):
        result,spec,review,_,_=self.gate_fixture()
        for change in ({'reviewer':'Root'},{'blocking_findings':['issue']},{'candidate_source_sha256':'0'*64},
                       {'test_source_sha256':'0'*64},{'author_original':{'path':'other','sha256':'0'*64}}):
            with self.subTest(change=change),self.assertRaises(ValueError): flow.candidate_gate(result,spec,dict(review,**change))
        for name,change in (('failed',{'passed':False}),('wrong-source',{'passed':True,'source_sha256':'0'*64}),
                            ('false-row',{'passed':True,'cases':[{'passed':False}]}),
                            ('case-count',{'cases':[]}),('case-error',{'error_type':'SyntheticFailure'})):
            bad=dict(spec); cases={'passed':True,'source_sha256':spec['after']['components']['R']['sources'][flow.CHILD],
                                 'error_type':None,'cases':[{'passed':True}]}; cases.update(change)
            cb=engine.save(self.root/(name+'-cases.json'),cases)
            bad['static_review']=engine.save(self.root/(name+'-static.json'),{'passed':True,'program_cases':cb})
            with self.subTest(name=name),self.assertRaises(ValueError): flow.candidate_gate(result,bad,review)
        bad=deepcopy(spec); bad['review_receipt']={'synthetic':'rejected'}
        with self.assertRaises(ValueError): flow.candidate_gate(result,bad,review)

    def test_prepared_task_resource_source_and_review_drift_rejected_before_owner(self):
        save=lambda name,value:engine.save(self.root/name,value)
        scope={'author_id':'synthetic-author12','forecast_id':'synthetic-forecast13'}
        scope_path=self.root/'scope.json'; scope_binding=engine.save(scope_path,scope)
        source=self.root/'owned.py'; source.write_text('inert synthetic trusted source')
        sources={'owned.py':engine.pin(source)}
        old_grant={key:'synthetic-'+key for key in ('data','runtime','qa','scorer','python','cik','ledger',
            'human_authorization','allowed_egress','bootstrap_no_model_call')}
        old_grant.update(baseline={'row':4283},additional_cap_nano_usd=10_000_000_000)
        old_runtime={'rates':{'synthetic':1},'limits':{'same':80},'role_efforts':{'author':'high'}}
        old_study={'cases':[{'invented':'same'}],'program_lineage':{'old':True}}
        old={'old_episode':save('old-episode.json',{'grant':save('old-grant.json',old_grant),
                    'study':save('old-study.json',old_study)}),
             'old_runtime':save('old-runtime.json',old_runtime)}
        previous={'handoff':old,'decision':self.chosen}
        home=self.root/'attempts'/scope['author_id']
        grant=dict(old_grant,id=scope['author_id'],root=str(home),source_commit='c'*40,
            sources={k:v['sha256'] for k,v in sources.items()},cutoff_utc='2099-01-01T00:00:00Z',
            deadline_utc='2099-01-01T00:01:00Z')
        gb=save('grant-checked.json',grant)
        study={'cases':old_study['cases'],'new_live_grant':gb,'new_episode_deadline':grant['deadline_utc']}
        sb=save('study-checked.json',study)
        runtime=dict(old_runtime,**{k:grant[k] for k in ('id','root','source_commit','ledger','baseline',
            'additional_cap_nano_usd','cutoff_utc','deadline_utc')},forecast_study=sb,
            slots={role:[str(home/'roles'/(role+'-01'))] for role in ('controller','author','review','forecast')})
        value={'stage':'author','scope':scope_binding,'prior':previous,'sources':sources,
            'source_commit':'c'*40,'runtime':save('runtime-checked.json',runtime),'grant':gb,'study':sb}
        with ExitStack() as stack:
            for name,replacement in (('ROOT',self.root),('SCOPE',scope_path)):
                stack.enter_context(mock.patch.object(flow,name,replacement))
            for name,returned in (('authority',scope),('prior',previous),('source_bindings',sources)):
                stack.enter_context(mock.patch.object(flow,name,return_value=returned))
            stack.enter_context(mock.patch.object(flow,'preflight_runtime',side_effect=engine.read))
            stack.enter_context(mock.patch.object(flow.fresh,'validate'))
            stack.enter_context(mock.patch.object(flow,'verify_sources'))
            stack.enter_context(mock.patch.object(flow,'accounting'))
            owner=stack.enter_context(mock.patch.object(flow,'open_capacity_runtime'))
            check_number=0
            def check(v,r,g,s,reviewer='independent-fixture-reviewer',expect_pass=False):
                nonlocal check_number
                check_number+=1
                check_root=self.root/('check-'+str(check_number)); check_root.mkdir()
                checked_save=lambda name,value:engine.save(check_root/name,value)
                v,r,g,s=deepcopy((v,r,g,s))
                v['grant']=checked_save('grant.json',g)
                s['new_live_grant']=v['grant']
                v['study']=checked_save('study.json',s)
                r['forecast_study']=v['study']
                v['runtime']=checked_save('runtime.json',r)
                bound=checked_save('prepared.json',v)
                rb=checked_save('stage-review.json',{'verdict':'PASS_AUTHOR_FOLLOWTHROUGH_STAGE','blocking_findings':[],
                    'reviewer':reviewer,'prepared':bound,'reviewed_sources':v['sources']})
                if expect_pass: self.assertEqual(flow.validate_prepared(bound,rb),(v,r))
                else:
                    with self.assertRaises(ValueError): flow.run_author(bound,rb)
                owner.assert_not_called()
            check(value,runtime,grant,study,expect_pass=True)
            check(value,runtime,grant,study,reviewer='Root')
            check(dict(value,sources={}),runtime,grant,study)
            for field in ('scorer','data','python','allowed_egress','baseline'):
                with self.subTest(field=field): check(value,runtime,dict(grant,**{field:'drift'}),study)
            for field in ('rates','limits','role_efforts','slots','root'):
                with self.subTest(field=field): check(value,dict(runtime,**{field:'drift'}),grant,study)
            check(value,runtime,grant,dict(study,cases=[{'invented':'different'}]))

    def test_source_verifier_rejects_file_or_commit_drift_without_git_execution(self):
        repo=self.root/'repo'; repo.mkdir(); source=repo/'owned.py'; source.write_text('synthetic source')
        bindings={'owned.py':engine.pin(source)}
        with mock.patch.object(flow.e,'REPO',repo), mock.patch.object(flow.subprocess,'run') as command:
            command.return_value.stdout=b'different committed bytes'
            with self.assertRaises(ValueError): flow.verify_sources(bindings,'c'*40)
            command.assert_called_once(); command.reset_mock()
            source.write_text('changed local source')
            with self.assertRaises(ValueError): flow.verify_sources(bindings,'c'*40)
            command.assert_not_called()

    def test_global_80_counts_failed_and_successful_roots_across_both_stage_ids(self):
        scope={'author_id':'author12','forecast_id':'forecast13'}
        roots=[self.root/'attempts/author12/code',self.root/'attempts/author12/review-code',
               self.root/'attempts/forecast13/code']
        for index,root in enumerate(roots):
            root.mkdir(parents=True)
            for i in range((20,30,29)[index]):
                home=root/f'call-{i:032x}'; home.mkdir()
                engine.save(home/'result.json',{'status':'FAILED_NO_RETRY' if i%2 else 'COMPLETED'})
        with mock.patch.object(flow,'ROOT',self.root),mock.patch.object(flow,'authority',return_value=scope):
            self.assertEqual(flow.containers_remaining(),1)
            (roots[2]/('call-'+'f'*32)).mkdir()
            with self.assertRaises(ValueError): flow.containers_remaining()

    def test_real_native_clone_keeps_names_configs_and_shared_resource_policy_for_12_13(self):
        f=native_fixture.ProgramCapacityTests(); f.setUp(); self.addCleanup(f.doCleanups)
        selected={'manifest':f.before,'entrypoints':f.entries}
        old_selected=engine.save(f.root/'versions/selected.json',selected)
        scope={'window':{'issued_utc':'2026-10-15T20:57:14Z'}}
        scope_binding=engine.save(self.root/'scope.json',scope)
        study=engine.save(self.root/'study.json',{'cases':[{'synthetic':'same-case'}]})
        create_batch=flow.ContinuousDiscoveryBatch
        clock=lambda:datetime(2026,10,15,21,tzinfo=timezone.utc)
        policies=[]
        for identifier,commit in (('author12','c'*40),('forecast13','d'*40)):
            artifact_root=self.root/'.codex/worktrees/synthetic/artifacts'/identifier
            native_root=self.root/'native-runtime'/identifier
            runtime={'id':identifier,'root':str(artifact_root),'source_commit':commit,
                'deadline_utc':'2026-10-15T22:27:14Z','cutoff_utc':'2026-10-15T22:26:14Z',
                'limits':{'synthetic':'same-limits'},'rates':{'synthetic':'same-rates'},
                'baseline':{'row':4283},'additional_cap_nano_usd':10_000_000_000,
                'role_efforts':{'author':'high','forecast':'max'}}
            value={'runtime':engine.save(self.root/(identifier+'.json'),runtime),'scope':scope_binding,
                'study':study,'prior':{'selected':selected,'handoff':{'old_selected':old_selected}}}
            with mock.patch.object(native_namespace,'NATIVE_RUNTIME_ROOT',self.root/'native-runtime'),\
                    mock.patch.object(flow,'authority',return_value=scope),mock.patch.object(flow,'ContinuousDiscoveryBatch',
                    side_effect=lambda path,**options:create_batch(path,**options,test_clock=clock,allow_test_clock=True)):
                capacity=flow.native(value,create=True)
            self.assertEqual(capacity.source_root,native_root/'source')
            self.assertEqual(capacity.registry,native_root/'versions')
            self.assertFalse(capacity.source_root.is_relative_to(artifact_root))
            self.assertFalse((artifact_root/'native').exists())
            self.assertEqual(capacity.baseline,f.before); self.assertEqual(capacity.initial_entrypoints,f.entries)
            for axis,name in f.entries.items():
                self.assertEqual((capacity.source_root/name).read_bytes(),(f.source/name).read_bytes())
                self.assertEqual(capacity.resolve(axis,expected_pair_sha256=digest(f.micro['pair']))['receipt']['source']['sha256'],f.before['components'][axis]['sources'][name])
            with self.assertRaises(ValueError): capacity.resolve('R',expected_pair_sha256='0'*64)
            micro=capacity.batch.snapshot()['micro_evolution']
            policies.append(micro['fixed_context']['resource_policy_sha256'])
            self.assertEqual(set(micro['allowed_write_paths']['researcher']),{f.entries['R'],flow.CHILD})
            self.assertIsNone(micro['pending'])
        self.assertEqual(policies[0],policies[1])

    def test_namespace_guard_still_rejects_native_under_protected_codex_ancestry(self):
        artifact=self.root/'.codex/worktrees/synthetic/artifacts/author12'
        with mock.patch.object(native_namespace,'NATIVE_RUNTIME_ROOT',self.root/'.codex/native-runtime'):
            with self.assertRaises(ValueError): native_namespace.native_paths(artifact,'author12')
        self.assertFalse((self.root/'.codex').exists())


if __name__=='__main__': unittest.main()
