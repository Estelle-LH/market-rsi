"""Forward-only public feedback contracts, with synthetic saved originals.

The existing researcher.verify and physical-delivery verifier run unchanged on
ScriptedReceiptRunner records. No candidate code, Docker, provider, QA/scorer
or production ledger is executed. Metadata/resident seams are named explicitly.
"""
from copy import deepcopy
from contextlib import ExitStack
import builtins
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

import earnings_population_broker as broker
import earnings_population_campaign_context as context
import earnings_population_completed as completed
import earnings_open_context as packing
import earnings_open_roles as open_roles
import earnings_population_public_predictions as public
import earnings_population_run as run
import earnings_population_services as services
import earnings_population_tasks as tasks
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_diagnostics as diagnostic_fixture
import test_earnings_population_run as prepare_fixture
import test_earnings_open_roles as role_fixture
import test_earnings_population_completed as completed_fixture

CAPITAL = 'CIK0000017313'


class PublicFixture:
    def __init__(self, owner):
        self.f = diagnostic_fixture.DiagnosticExecutionVerificationTests()
        self.f.setUp(); owner.addCleanup(self.f.doCleanups)
        self.company = self.f.fixture.company(CAPITAL)['company']
        self.f.company = self.company
        from edgar_forecast_tools import FilingTools
        self.f.tools = FilingTools(self.company)
        self.f.payload.update(questions=self.f.tools.files['questions.md'],
                              filing_index=self.f.tools.files['filing_index.tsv'])
        self.version = self.f.fixture.version

    def make(self, *, value=...):
        values = ['1648.400', '19600', '49800', '53.5', '310.0']
        predictions = {'predictions': [dict(target_id=ident, predicted_value=value)
            for ident, value in zip(public.TARGETS, values)]}
        if value is ...:
            value = dict(coverage={'extracted_cells': 92}, evidence=[],
                arbitrary_quote='PRIVATE_UNRELATED_NOT_COPIED',
                targets=[dict(target_id=ident, status='complete', predicted_value=advice)
                    for ident, advice in zip(public.TARGETS, ['1648.4','19567','49966.7','51.1','334.1'])])
            value['targets'][1].update(status='incomplete', missing=['validation'])
            value['nested'] = {'targets': [{'target_id':'T002','predicted_value':'19567'}]}
        self.f.value = lambda: deepcopy(value)
        def response(original):
            original['output'] = [{'type':'reasoning','summary':[{'text':'PRIVATE_REASONING_NOT_COPIED'}]},
                {'type':'message','role':'assistant','content':[{'type':'output_text','text':json.dumps(predictions)}]}]
        bound, programs, runner = self.f.trial(final=True, response_mutator=response, public_changes={
            'schema':'earnings_population_public_trial_v1', 'points':3.5,
            'target_scores':[dict(target_id=ident,points_awarded=award)
                for ident,award in zip(public.TARGETS,[1,0,1,1,.5])]})
        trial = self.f.trials[programs['path']]; root = trial['root']
        result = engine.save(root/'result.json', dict(status='COMPLETED_SCORED',turns=1,
            planned_targets=5,scored_targets=5,points=3.5))
        prediction = engine.save(root/'predictions.json', predictions)
        evidence = [*self.f.evidence(programs), result, prediction,
                    trial['intent'],trial['physical_response'],trial['raw']]
        hidden = engine.save(root/'score.json', {'actual_value':'PRIVATE_SCORE_NOT_COPIED'})
        evidence.append(hidden)
        feedback = engine.save(root/'feedback.json', dict(schema='earnings_population_feedback_v1',
            company_id=CAPITAL, round_index=1, stable_id=self.version['id'], scope='Synthetic DEV',
            results=[dict(version_id=self.version['id'],points=3.5,evidence=[bound,*evidence])]))
        return dict(public=bound,evidence=evidence,version=self.version,company=self.company,
                    feedback=feedback,trial=trial,runner=runner,predictions=predictions)


class PublicPredictionTests(unittest.TestCase):
    def setUp(self): self.f = PublicFixture(self)
    def project(self, row):
        return public.project(row['public'], row['evidence'], row['version'], row['company'])

    def test_real_original_synthetic_receipts_public_only_and_exact_numeric_strings(self):
        row = self.f.make(); before = deepcopy(row['evidence'])
        diagnostics, result = self.project(row)
        self.assertEqual(result['schema'],'earnings_population_public_predictions_v1')
        self.assertEqual([z['target_id'] for z in result['targets']],public.TARGETS)
        self.assertEqual(result['targets'][0],dict(target_id='T001',predicted_value='1648.400',
            R_advice_value='1648.4',matches_R_advice=True,points_awarded=1))
        self.assertIsNone(result['targets'][1]['R_advice_value'])
        self.assertIsNone(result['targets'][1]['matches_R_advice'])
        self.assertEqual(result['targets'][4]['R_advice_value'],'334.1')
        self.assertEqual(result['targets'][4]['predicted_value'],'310.0')
        self.assertFalse(result['targets'][4]['matches_R_advice'])
        self.assertEqual(len(result['evidence']['originals']),7)
        self.assertEqual(len(result['evidence']['readonly_physical_observation']['originally_bound_files']),3)
        self.assertEqual(diagnostics['source_sha256'],self.f.version['R']['sha256'])
        self.assertNotIn('PRIVATE_',json.dumps(result))
        self.assertEqual(row['evidence'],before); self.assertEqual(row['runner'].calls,1)
        self.assertFalse(self.f.f.fixture.marker.exists())

    def test_absent_or_arbitrary_R_advice_is_null_not_inferred(self):
        row=self.f.make(value={'custom_algorithm':{'nested_prediction':'PRIVATE_NOT_ADVICE'}})
        _,result=self.project(row)
        self.assertTrue(all(z['R_advice_value'] is None for z in result['targets']))
        self.assertNotIn('PRIVATE_',json.dumps(result))

    def test_legal_nonobject_R_output_has_no_explicit_advice(self):
        for value in (None, [], 42, 'custom JSON advice'):
            with self.subTest(value=value):
                row=self.f.make(value=value)
                diagnostics,result=self.project(row)
                self.assertEqual(len(result['targets']),5)
                self.assertTrue(all(z['R_advice_value'] is None and z['matches_R_advice'] is None
                                    for z in result['targets']))
                self.assertEqual(diagnostics['source_sha256'],self.f.version['R']['sha256'])

    def test_changed_prediction_refused_and_legacy_unbound_wire_is_observation(self):
        row=self.f.make(); path=Path(row['trial']['root'])/'predictions.json'
        old=path.read_bytes(); path.write_bytes(old.replace(b'310.0',b'311.0'))
        with self.assertRaises(ValueError):self.project(row)
        row=self.f.make()
        wire=[row['trial'][key] for key in ('intent','physical_response','raw')]
        row['evidence']=[b for b in row['evidence'] if b not in wire]
        _,result=self.project(row)
        observation=result['evidence']['readonly_physical_observation']
        self.assertEqual(observation['originally_bound_files'],[])
        self.assertEqual(len(observation['files']),3)
        self.assertIn('not proof',observation['qualification'])
        raw=Path(row['trial']['raw']['path']);value=json.loads(raw.read_bytes())
        value['model']='wrong-model';raw.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'physical response'):self.project(row)

    def test_complete_nonfinite_and_duplicate_advice_refused(self):
        for targets in ([dict(target_id='T001',status='complete',predicted_value='NaN')],
                        [dict(target_id='T001',status='complete',predicted_value='1')]*2):
            with self.subTest(targets=targets):
                row=self.f.make(value={'targets':targets})
                with self.assertRaises(ValueError):self.project(row)

    def test_wrong_company_and_H_source_refused(self):
        row=self.f.make()
        with self.assertRaises(ValueError):public.project(row['public'],row['evidence'],row['version'],dict(row['company'],cik='CIK0000021076'))
        wrong=deepcopy(row['version']);wrong['H']['sha256']='a'*64
        with self.assertRaises(ValueError):public.project(row['public'],row['evidence'],wrong,row['company'])

    def test_legacy_shape_identical_and_opt_in_broker_projection(self):
        row=self.f.make(); versions={self.f.version['id']:self.f.version}
        with patch.object(tasks,'resident',return_value={'company':self.f.company}), \
             patch.object(public,'company',return_value=self.f.company):
            legacy=broker.public_feedback(row['feedback'],versions)
            explicit=broker.public_feedback(row['feedback'],versions,policy=None)
            new=broker.public_feedback(row['feedback'],versions,policy=public.POLICY)
        self.assertEqual(legacy,explicit)
        self.assertNotIn('public_predictions',legacy['results'][0])
        self.assertEqual(new['results'][0]['public_predictions']['targets'][4]['predicted_value'],'310.0')
        self.assertNotIn('PRIVATE_',json.dumps(new))
        with self.assertRaises(ValueError):broker.public_feedback(row['feedback'],versions,policy='unknown')

    def test_later_unscored_carries_optional_values_without_invented_new_scores(self):
        row=self.f.make(); versions={self.f.version['id']:self.f.version}; decision=engine.save(row['trial']['root']/'decision.json',{})
        body=dict(schema='earnings_population_campaign_feedback_v1',kind='no_change',score_state='unscored',
            company_id=CAPITAL,round_index=2,decision=decision,chosen_parent_id=self.f.version['id'],
            baseline_version_id=self.f.version['id'],candidate=None,exploration_review=dict(accepted_for_exploration=False,evidence=[]),
            results=[],previous_feedback=row['feedback'],campaign_contract_sha256='a'*64,last_scored_feedback=row['feedback'],scope='Synthetic')
        with patch.object(public,'company',return_value=self.f.company):
            received=context.project(body,versions,lambda x,v:broker._public_scored(x,v,policy=public.POLICY))
        self.assertNotIn('results',received)
        prior=received['last_scored_observation']['results'][0]
        self.assertEqual(prior['points'],3.5)
        self.assertEqual(prior['public_predictions']['targets'][4]['predicted_value'],'310.0')


class PolicyTests(unittest.TestCase):
    def test_exact_forward_policy_and_absent_legacy(self):
        from earnings_population_budget import amendment_binding
        runtime=dict(schema='earnings_population_runtime_v1',public_feedback_policy=public.POLICY,
            budget_amendment=amendment_binding(),companies=[CAPITAL])
        study={'campaign':{},'campaign_resume':{}}
        self.assertIsNone(public.runtime_policy({}))
        self.assertEqual(public.runtime_policy(runtime,study),public.POLICY)
        for value in (None,False,True,1,'unknown',{},[]):
            with self.subTest(value=value),self.assertRaises(ValueError):
                public.runtime_policy(dict(runtime,public_feedback_policy=value),study)
        for changed in (dict(runtime,schema='wrong'),dict(runtime,companies=['CIK0000021076']),
                        dict(runtime,budget_amendment=None)):
            with self.assertRaises(ValueError):public.runtime_policy(changed,study)
        with self.assertRaises(ValueError):public.runtime_policy(runtime,dict(study,continuation={}))

    def test_prepare_bad_opt_in_stops_before_idle_or_inputs(self):
        f=prepare_fixture.PreparationContracts();f.setUp();self.addCleanup(f.doCleanups)
        for options in ({'public_predictions':True},{'public_predictions':True,'continue_from':'old'},
                        {'public_predictions':1},{'public_predictions':True,'cumulative400':True}):
            with self.subTest(options=options),self.assertRaises(ValueError):run.prepare(f.id,**options)
        f.idle.assert_not_called();self.assertFalse((f.owned/'inputs'/f.id).exists())

    def test_completed_round_uses_that_original_runtime_policy_not_todays_default(self):
        from earnings_population_budget import amendment_binding
        f=completed_fixture.CompletedDraftTests();f.module=completed
        for opted in (False,True):
            reader,seed,rows,manifest,expected=f.round_fixture(kind='no_change')
            runtime={'companies':[CAPITAL]};study={}
            if opted:
                runtime.update(schema='earnings_population_runtime_v1',public_feedback_policy=public.POLICY,
                               budget_amendment=amendment_binding())
                study.update(campaign={},campaign_resume={})
            # Explicit metadata/award seams isolate policy routing, not historical admission.
            with patch.object(completed.pool,'validate',side_effect=lambda x:x), \
                 patch.object(broker,'public_feedback') as project:
                completed._rounds(reader,Path('/synthetic/attempt'),runtime,study,manifest,seed)
            self.assertEqual(project.call_args.kwargs,{'policy':public.POLICY if opted else None})


class ReceivingTests(unittest.TestCase):
    def setUp(self): self.f=PublicFixture(self)
    def projected(self):
        row=self.f.make()
        with patch.object(public,'company',return_value=self.f.company):
            view=broker.public_feedback(row['feedback'],{self.f.version['id']:self.f.version},policy=public.POLICY)
        return row,view

    def test_original_context_pack_keeps_complete_rows_in_first_and_final_views(self):
        row,feedback=self.projected()
        # Controlled offline counts deliberately force existing fallback paths;
        # they do not estimate actual provider counts or establish live headroom.
        for author in (False,True):
            for final in (False,True):
                fmt={'name':'earnings_population_delta_author_v1' if author else 'earnings_population_decision_v1',
                    'schema':{'properties':{k:{} for k in ({'decision_sha256','parent_source_sha256','edits','test_text'}
                        if author else {'schema','axis','component','parent_pair_sha256','feedback_sha256','hypothesis','expected_effect','retire_branch_id'})}}}
                packet={'feedback':feedback,'comparison_parent':self.f.version['id']}
                request={'model':'gpt-6.1-sol','instructions':'Original synthetic packing test','text':{'format':fmt},
                    'tool_choice':'none' if final else 'auto','input':[{'role':'user','content':json.dumps(packet)},
                    {'type':'function_call','name':'search_literature','call_id':'old','arguments':'{}'},
                    {'type':'function_call_output','call_id':'old','output':'x'*90000},
                    {'type':'function_call','name':'read_current_program','call_id':'new','arguments':'{"axis":"R"}'},
                    {'type':'function_call_output','call_id':'new','output':json.dumps({'value':{'source_text':self.f.f.source}})}]}
                ceiling=96000 if author else 32000
                counts=iter([ceiling+1]*3+[100] if author and final else [ceiling+1,100])
                client=SimpleNamespace(post=lambda *_:dict(input_tokens=next(counts)))
                output=self.f.f.fixture.root/f'pack-{author}-{final}';output.mkdir()
                received=packing.pack(client,request,{'max_input_tokens':ceiling},output,1,author_final=author and final)
                self.assertEqual(json.loads(received['input'][0]['content']),packet)
                self.assertEqual(request['model'],received['model'])
                self.assertEqual(received['tool_choice'],request['tool_choice'])
                self.assertEqual(json.loads(received['input'][0]['content'])['feedback']['results'][0]
                    ['public_predictions']['targets'],feedback['results'][0]['public_predictions']['targets'])

    def test_real_services_author_first_and_final_transport_keep_cached_comparison(self):
        row,feedback=self.projected();transport=role_fixture.OpenRoleTests();transport.setUp()
        self.addCleanup(transport.doCleanups)
        base=transport.service(author=True,max_turns=2,limits={'max_input_tokens':96000,'max_output_tokens':49152,'wall_seconds':1200})
        owner=services.Services.__new__(services.Services)
        case=self.f.f.fixture.prepare(resident=self.f.f.fixture.company(CAPITAL))
        owner.case=Mock(return_value=case);owner.native_root=self.f.f.fixture.root
        owner.runner,owner.literature=Mock(),Mock();owner.traces,owner.authored={},{}
        owner.prior_feedback=feedback
        owner.contexts={'author':(base.binding,{'budget':transport.budget,'client_factory':transport.factory,'max_turns':2})}
        chosen=transport.choice();chosen['parent_pair_sha256']=self.f.version['id'];chosen['feedback_sha256']=digest(row['feedback'])
        source="PROGRAM={'axis':'R'}\ndef run(payload): return {'synthetic_repair':True}\n"
        reply={'decision_sha256':digest(chosen),'parent_source_sha256':self.f.version['R']['sha256'],
            'edits':[{'kind':'replace','old_text':self.f.f.source,'new_text':source}],
            'test_text':"CASES=[{'input':{},'expected':{'synthetic_repair':True}}]"}
        transport.generations=[transport.tool_response(transport.call('parent','read_current_program',{'axis':'R'})),transport.message(reply)]
        state={'stable_id':self.f.version['id'],'explorers':[],'versions':{self.f.version['id']:self.f.version}}
        with patch.object(services,'resident',return_value={'company':self.f.company}), \
             patch.object(open_roles,'budgeted_response',side_effect=transport.fake_paid):
            owner.author(chosen,state,str(transport.slot))
        self.assertEqual(len(transport.requests),2)
        for request in transport.requests:
            effective=json.loads(request['input'][0]['content'])
            self.assertEqual(effective['research_context']['feedback'],feedback)
        self.assertEqual(transport.requests[-1]['tool_choice'],'none')
        self.assertFalse(self.f.f.fixture.marker.exists())


@unittest.skipUnless(os.environ.get('RUN_ACTUAL29_PUBLIC_PREDICTIONS')=='1',
                     'Opt-in bounded actual29 public projection, not history/admission')
class Actual29PublicProjection(unittest.TestCase):
    def assert_three_arm_original_pack_retention(self, root, state, feedback):
        """Actual public originals, prospective insertion, synthetic counts only.

        Initial public packets come from actual29. Replacing their old feedback
        is a packing fixture, not a valid new runtime/parent-choice admission.
        Only the first user packet is read; no private continuity is inspected.
        """
        expected=[row['public_predictions']['targets'] for row in feedback['results']]
        self.assertEqual(len(expected),3)
        self.assertEqual(sum(map(len,expected)),15)
        with tempfile.TemporaryDirectory() as temporary:
            for author in (False,True):
                role='author' if author else 'controller'
                original=root/'roles'/f'{role}-01'/'01-request.json'
                request=json.loads(original.read_bytes())['payload']
                packet=json.loads(request['input'][0]['content'])
                if author:
                    packet['research_context']['feedback']=deepcopy(feedback)
                    parent=state['versions'][packet['decision']['parent_pair_sha256']]
                    source=public.checked(parent['R']).decode()
                    self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),packet['parent_source_sha256'])
                else:
                    packet['feedback']=deepcopy(feedback)
                request['input']=[{'role':'user','content':json.dumps(packet)}]
                ceiling=96000 if author else 32000
                for final in (False,True):
                    with self.subTest(role=role,final=final):
                        prospective=deepcopy(request)
                        if final:
                            prospective['tool_choice']='none'
                            prospective['input'] += [
                                {'type':'function_call','name':'search_literature','call_id':'older','arguments':'{}'},
                                {'type':'function_call_output','call_id':'older','output':'x'*90000}]
                            if author:
                                prospective['input'] += [
                                    {'type':'function_call','name':'read_current_program','call_id':'parent','arguments':'{"axis":"R"}'},
                                    {'type':'function_call_output','call_id':'parent','output':json.dumps({'value':{'source_text':source}})}]
                            else:
                                # The newest unseen batch stays complete by
                                # design; only an older seen return may shrink.
                                prospective['input'] += [
                                    {'type':'function_call','name':'calculate','call_id':'newest','arguments':'{"expression":"1+1"}'},
                                    {'type':'function_call_output','call_id':'newest','output':'{"value":2}'}]
                        counts=[]
                        def count(endpoint,payload):
                            self.assertEqual(endpoint,'/v1/responses/input_tokens')
                            counts.append(digest(payload))
                            return {'input_tokens':ceiling+1 if final and len(counts)<4 else 100}
                        output=Path(temporary)/f'{role}-{final}';output.mkdir()
                        received=packing.pack(SimpleNamespace(post=count),prospective,
                            {'max_input_tokens':ceiling},output,1,author_final=author and final)
                        actual_packet=json.loads(received['input'][0]['content'])
                        actual=actual_packet['research_context']['feedback'] if author else actual_packet['feedback']
                        self.assertEqual(actual,feedback)
                        self.assertEqual([row['public_predictions']['targets'] for row in actual['results']],expected)
                        self.assertIn('48.9167',actual['exploration_review']['rationale'])
                        self.assertEqual(received['model'],prospective['model'])
                        self.assertEqual(received['tool_choice'],prospective['tool_choice'])
                        if final:
                            self.assertEqual(len(counts),4)
                        if author and final:
                            snapshot=json.loads(received['input'][1]['content'])
                            self.assertEqual(snapshot['schema'],'earnings_author_final_public_snapshot_v1')
                            returned=[json.loads(item['output'])['value']['source_text']
                                for item in snapshot['records']
                                if item.get('type')=='function_call_output' and item.get('call_id')=='parent']
                            self.assertEqual(returned,[source])

    def test_exact_original29_legacy_unchanged_and_forward_public_values(self):
        root=Path('/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/edgar-population-20261016/attempts/edgar-population-20261016-29')
        state=json.loads((root/'population-01.json').read_bytes())
        bound={'path':str(root/'feedback-01.json'),'sha256':'ed2df489037129d6816c675b5bc90a0f88d65838d99224ef8c4dc400cd1b7d58'}
        resident,loads=tasks.resident,json.loads
        qa={resident(CAPITAL)['kernel']['qa']['sha256']}
        def public_decode(raw,*a,**k):
            value=raw.encode() if isinstance(raw,str) else raw
            if isinstance(value,(bytes,bytearray)) and hashlib.sha256(value).hexdigest() in qa:raise AssertionError('No QA decode')
            return loads(raw,*a,**k)
        def only_dev(cik):
            if cik!=CAPITAL:raise AssertionError('Only own Capital public body')
            return resident(cik)
        def readonly(fn):
            def call(path,*a,**k):
                mode=k.get('mode',a[0] if a else 'r')
                if type(mode)is str and any(x in mode for x in 'wax+'):raise AssertionError('No writes')
                if type(mode)is int and mode&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):raise AssertionError('No writes')
                if not isinstance(path,int) and set(re.findall(r'CIK[0-9]{10}',os.fsdecode(path)))-{CAPITAL}:raise AssertionError('No nonDEV body')
                return fn(path,*a,**k)
            return call
        with ExitStack() as stack:
            stack.enter_context(patch.object(tasks,'resident',side_effect=only_dev))
            stack.enter_context(patch.object(json,'loads',side_effect=public_decode))
            for target,name in ((builtins,'open'),(Path,'open'),(os,'open')):
                stack.enter_context(patch.object(target,name,readonly(getattr(target,name))))
            stack.enter_context(patch.object(engine,'save',side_effect=AssertionError('No writes')))
            stack.enter_context(patch.object(socket.socket,'connect',side_effect=AssertionError('No network')))
            stack.enter_context(patch.object(subprocess,'run',side_effect=AssertionError('No processes')))
            old=broker.public_feedback(bound,state['versions'])
            # Sealed role audit used explicit UTF-8 JSON, unlike digest()'s
            # default ASCII escaping of the literal non-ASCII Review rationale.
            old_audit_bytes=json.dumps(old,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
            self.assertEqual(hashlib.sha256(old_audit_bytes).hexdigest(),
                             'feeaad09765a9e1bf0ff6d55e2ff5e0dbf6e9a257f4a186fbf3f7b771bc06021')
            new=broker.public_feedback(bound,state['versions'],policy=public.POLICY)
            self.assertEqual([z['points'] for z in new['results']],[3,3,3.5])
            self.assertEqual([z['public_predictions']['targets'][4]['predicted_value'] for z in new['results']],['345.0','320.0','310.0'])
            self.assertEqual([z['public_predictions']['targets'][4]['R_advice_value'] for z in new['results']],[None,'334.1','334.1'])
            self.assertTrue(all(z['public_predictions']['targets'][1]['R_advice_value'] is None for z in new['results']))
            self.assertIn('48.9167',new['exploration_review']['rationale'])
        # All original reads/projecting above were under the no-write guard;
        # pack now writes ONLY its synthetic count receipts in this tempdir.
        self.assert_three_arm_original_pack_retention(root,state,new)


if __name__=='__main__': unittest.main()
