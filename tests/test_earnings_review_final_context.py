"""Independent public Review snapshot contracts; no real provider or ledger.

The opt-in23 case is structural only: saved historical counts are not a fresh
token estimate, and no candidate/financial code is executed by these tests.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

import earnings_open_context as packing
import earnings_open_roles as open_roles
import earnings_population_roles as population_roles
import earnings_entry as entry
from earnings_capacity_runtime import _OwnedHTTP
from earnings_http import RawOpenAIHTTP
from edgar_forecast_budget import PilotBudget,BudgetStop
from edgar_forecast_openai import budgeted_response
from edgar_forecast_tools import function
import test_earnings_capacity_controller_transport as original


class NeverInspectCarrier(str):
    def __deepcopy__(self,memo):raise AssertionError('Opaque reasoning carrier copied')
    def __str__(self):raise AssertionError('Opaque reasoning carrier rendered')


class ReviewFinalContextTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='review-final-context-');self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()
        self.source='INERT PUBLIC SOURCE 界\n'*1800
        self.fields=dict(candidate_id={'type':'string','enum':['c'*64]},accepted_for_exploration={'type':'boolean'},rationale={'type':'string'})
        self.request=dict(model='gpt-6.1-sol',reasoning={'effort':'max'},instructions='Exact independent Review instructions',
            tools=[function('read_population_program','Original inert source',{'axis':{'type':'string'}})],
            tool_choice='none',parallel_tool_calls=False,
            text={'format':{'type':'json_schema','name':'earnings_population_review_v1','strict':True,
                'schema':{'type':'object','properties':self.fields,'required':list(self.fields),'additionalProperties':False}}},
            input=[dict(role='user',content=json.dumps({'candidate_id':'c'*64,'matched_parent':'a'*64,'public':'immutable '*40})),
                dict(type='reasoning',encrypted_content='INVENTED_OPAQUE_ONLY'*2000),
                dict(type='function_call',call_id='source',name='read_population_program',arguments='{"axis":"R"}'),
                dict(type='function_call_output',call_id='source',output=self.source),
                dict(type='function_call',call_id='older',name='inspect_trace',arguments='{}'),
                dict(type='function_call_output',call_id='older',output='older observation '*1800),
                dict(type='message',role='assistant',content=[dict(type='output_text',text='Public unresolved tradeoff, not acceptance')]),
                dict(type='function_call',call_id='latest',name='inspect_trace',arguments='{}'),
                dict(type='function_call_output',call_id='latest',output='complete newest observation '*150)])

    def view(self,request=None):
        result,receipts=packing.review_final_view(self.request if request is None else request,100)
        return result,receipts,json.loads(result['input'][1]['content'])

    def test_initial_packet_settings_complete_source_all_public_calls_and_latest_output_exact(self):
        before=deepcopy(self.request);result,receipts,snapshot=self.view()
        self.assertEqual(self.request,before);self.assertEqual(result['input'][0],before['input'][0])
        self.assertEqual({k:v for k,v in result.items()if k!='input'},{k:v for k,v in before.items()if k!='input'})
        self.assertEqual(snapshot['schema'],'earnings_review_final_public_snapshot_v1');self.assertIn('Review',snapshot['notice'])
        records=snapshot['records'];calls={r['call_id']:r for r in records if r['type']=='function_call'}
        outputs={r['call_id']:r for r in records if r['type']=='function_call_output'}
        self.assertEqual(set(calls),{'source','older','latest'});self.assertEqual(set(outputs),set(calls))
        self.assertEqual(calls['source'],before['input'][2]);self.assertEqual(outputs['source']['output'],self.source)
        self.assertEqual(outputs['latest']['output'],before['input'][-1]['output'])
        projected=json.loads(outputs['older']['output']);self.assertTrue(projected['truncated'])
        self.assertEqual(projected['original_output_sha256'],hashlib.sha256(before['input'][5]['output'].encode()).hexdigest())
        self.assertEqual({r['input_index']for r in receipts},set(range(2,len(before['input']))))
        self.assertNotIn('INVENTED_OPAQUE_ONLY',json.dumps(result))

    def test_reasoning_is_selected_only_by_type_without_copy_render_or_per_item_hash(self):
        request=deepcopy(self.request);reasoning=dict(type='reasoning',encrypted_content=NeverInspectCarrier('OPAQUE_SENTINEL'))
        request['input'][1]=reasoning;encoded=packing.encoded
        def encode_public(value):
            if value is reasoning:raise AssertionError('Reasoning item serialized/hashed')
            return encoded(value)
        with patch.object(packing,'encoded',side_effect=encode_public):result,receipts,_=self.view(request)
        self.assertNotIn('OPAQUE_SENTINEL',json.dumps(result));self.assertNotIn(1,[x['input_index']for x in receipts])

    def test_all_old_current_reference_and_population_source_returns_are_preserved(self):
        for name in ('read_population_program','read_current_program','read_reference_program'):
            with self.subTest(name=name):
                request=deepcopy(self.request);request['input'][2]['name']=name
                _,_,snapshot=self.view(request)
                outputs={r['call_id']:r['output']for r in snapshot['records']if r['type']=='function_call_output'}
                self.assertEqual(outputs['source'],self.source)

    def test_review_only_three_field_format_tool_none_and_public_pairs_are_required(self):
        for variant in ('auto','author','extra_field','missing_field','first_not_user'):
            request=deepcopy(self.request)
            if variant=='auto':request['tool_choice']='auto'
            elif variant=='author':request['text']['format']['name']='earnings_open_author_v1'
            elif variant=='extra_field':request['text']['format']['schema']['properties']['score']={}
            elif variant=='missing_field':request['text']['format']['schema']['properties'].pop('rationale')
            else:request['input'][0]['role']='assistant'
            with self.subTest(variant=variant),self.assertRaises(ValueError):self.view(request)
        for items in ([self.request['input'][2]],[self.request['input'][3]],
                [self.request['input'][2],self.request['input'][3],self.request['input'][3]],
                [dict(type='custom_tool_call')],[dict(type='message',role='assistant',content=[dict(type='refusal')])]):
            request=deepcopy(self.request);request['input']=[request['input'][0],*deepcopy(items)]
            with self.subTest(items=items),self.assertRaises(ValueError):self.view(request)
        for invalid in (True,-1,'100'):
            with self.subTest(preview=invalid),self.assertRaises(ValueError):packing.review_final_view(self.request,invalid)

    def test_explicit_review_fourth_view_and_prospective_completion_are_receipted(self):
        original=deepcopy(self.request);original['tool_choice']='auto'
        final=dict(original,tool_choice='none',instructions=original['instructions']+' Finish only three Review fields.')
        client=Mock();client.post.side_effect=[dict(input_tokens=n)for n in (10001,10001,10001,20)]
        selected=packing.pack(client,original,{'max_input_tokens':10000},self.root,7,completion_request=final)
        self.assertEqual(len(client.post.call_args_list),4);self.assertEqual(selected,client.post.call_args_list[-1].args[1])
        self.assertEqual(selected['tool_choice'],'none');self.assertEqual(selected['input'][0],original['input'][0])
        self.assertEqual(json.loads(selected['input'][1]['content'])['schema'],'earnings_review_final_public_snapshot_v1')
        receipt=json.loads((self.root/'07-context-04.json').read_bytes())
        self.assertEqual(receipt['projection_policy'],'review_final_public_snapshot_v1');self.assertTrue(receipt['early_finalization'])
        self.assertTrue(receipt['generation_not_sent']);self.assertEqual(receipt['max_input_tokens'],10000)
        self.assertEqual(receipt['effective_request_sha256'],hashlib.sha256(packing.encoded(selected)).hexdigest())

    def test_prospective_completion_cannot_change_any_other_field_or_original_input(self):
        request=deepcopy(self.request);request['tool_choice']='auto'
        valid=dict(request,tool_choice='none',instructions=request['instructions']+' Exact final Review instruction')
        variants=[dict(valid,model='foreign'),dict(valid,reasoning={'effort':'high'}),dict(valid,tools=[]),
            dict(valid,parallel_tool_calls=True),dict(valid,input=[dict(role='user',content='replacement')]),
            dict(valid,text={}),dict(valid,instructions='replacement'),dict(valid,instructions=request['instructions'])]
        client=Mock()
        for changed in variants:
            with self.subTest(changed=changed.keys()),self.assertRaises(ValueError):
                packing.pack(client,request,{'max_input_tokens':10000},self.root,1,completion_request=changed)
        client.post.assert_not_called()

    def test_unfit_and_original_count_failure_fail_closed_without_generation_or_retry(self):
        for turn,last,error in ((1,dict(input_tokens=10001),BudgetStop),(2,TimeoutError('fixture count failed'),TimeoutError)):
            client=Mock();client.post.side_effect=[dict(input_tokens=10001)]*3+[last]
            with self.subTest(turn=turn),self.assertRaises(error):
                packing.pack(client,self.request,{'max_input_tokens':10000},self.root,turn,review_final=True)
            self.assertEqual(client.post.call_count,4)
            self.assertTrue(all(c.args[0]=='/v1/responses/input_tokens'for c in client.post.call_args_list))
            self.assertFalse(list(self.root.glob(f'{turn:02d}-request.json')))

    def test_default_packing_is_not_silently_promoted_to_review_snapshot(self):
        client=Mock();client.post.return_value=dict(input_tokens=10001)
        with self.assertRaises(BudgetStop):packing.pack(client,self.request,{'max_input_tokens':10000},self.root,1)
        for call in client.post.call_args_list:
            self.assertEqual(call.args[1]['input'][0],self.request['input'][0])
            self.assertEqual(call.args[1]['input'][1],self.request['input'][1])
        with self.assertRaises(ValueError):packing.pack(client,self.request,{'max_input_tokens':10000},self.root,2,review_final=True,author_final=True)
        for value in (1,'true',None):
            with self.subTest(review_final=value),self.assertRaises(ValueError):
                packing.pack(client,self.request,{'max_input_tokens':10000},self.root,2,review_final=value)

    def test_small_review_packet_keeps_stock_single_count_and_original_budget_path(self):
        request=deepcopy(self.request);request['input']=[request['input'][0]];calls=[]
        class Client:
            def post(inner,endpoint,payload):
                calls.append((endpoint,deepcopy(payload)))
                if endpoint.endswith('input_tokens'):return dict(input_tokens=20)
                return dict(model=request['model'],service_tier='default',status='completed',output=[],
                    usage=dict(input_tokens=20,output_tokens=1,total_tokens=21,input_tokens_details=dict(cached_tokens=0)))
        transport=entry.ReceiptHTTP(Client(),self.root);budget=PilotBudget(self.root/'inert-only.sqlite3');self.addCleanup(budget.close)
        limits=dict(max_input_tokens=10000,max_output_tokens=1024)
        rates=dict(api_model=request['model'],effort='max',input='2',cached='.1',write='2.5',output='10')
        selected=packing.pack(transport,request,limits,self.root,1,review_final=True)
        self.assertEqual(calls,[]);self.assertEqual(selected,request)
        budgeted_response(transport,selected,rates,limits,budget,self.root,1)
        self.assertEqual([p for p,_ in calls],['/v1/responses/input_tokens','/v1/responses'])
        self.assertEqual(budget.db.execute('SELECT status FROM requests').fetchall(),[('settled',)])

    def test_full_role_prepared_handoff_counts_winner_once_and_preserves_actual_wire(self):
        f=original._TransportFixture(self,self.root/'owned');slot=f.root/'roles/review-01'
        ctx=dict(f.context,schema='earnings_capacity_review_transport_v1',slots=[str(slot)])
        binding=original._save(f.root/'review-context.json',ctx)
        # This role's sole newest source output is preserved in all native
        # projections, so identical candidates are intentionally counted once.
        raw=RawOpenAIHTTP('',30);calls=[];counts=iter((20,10001,20));generation=0
        first=dict(model=original.MODEL,service_tier='default',status='completed',error=None,
            output=[dict(type='reasoning',encrypted_content='INVENTED_OPAQUE_CONTINUITY'*1800),
                dict(type='function_call',call_id='source',name='read_population_program',arguments='{"axis":"R"}')],
            usage=dict(input_tokens=20,output_tokens=7,total_tokens=27,input_tokens_details=dict(cached_tokens=0)))
        verdict=dict(candidate_id='c'*64,accepted_for_exploration=False,rationale='Synthetic completion, not financial correctness.')
        second=dict(first,output=[dict(type='message',role='assistant',content=[dict(type='output_text',text=json.dumps(verdict))])])
        class Connection:
            def __init__(inner,host,timeout):
                if host!='api.openai.com':raise AssertionError('Synthetic provider only')
            def request(inner,method,endpoint,body,headers):
                inner.endpoint=endpoint;calls.append((endpoint,json.loads(body)))
            def getresponse(inner):
                nonlocal generation
                if inner.endpoint.endswith('input_tokens'):value=dict(input_tokens=next(counts))
                else:value=first if generation==0 else second;generation+=1
                wire=original._wire(value)
                return Mock(status=200,getheader=Mock(return_value='req_review_final_fixture'),read=Mock(side_effect=lambda limit:wire[:limit]))
            def close(inner):pass
        def check(loan):
            if loan is None:f.budget.active()
            else:f.budget.check_reserved(*loan)
        owned=_OwnedHTTP(raw,check,{str(slot):f.limits},f.rates)
        broker=Mock(definitions=[function('read_population_program','Read inert public program',{'axis':{'type':'string'}})])
        broker.dispatch.return_value={'source_text':self.source}
        role=population_roles.PopulationReviewer(binding,budget=f.budget,client_factory=lambda:owned,broker=broker,max_turns=3)
        prompt=dict(candidate_id='c'*64,immutable_evidence='same public initial packet '*1400)
        with patch('earnings_http.http.client.HTTPSConnection',Connection):bound=role.review(prompt,str(slot))
        self.assertEqual(generation,2);self.assertEqual(len([p for p,_ in calls if p.endswith('input_tokens')]),3)
        self.assertEqual(len([p for p,_ in calls if p=='/v1/responses']),2)
        final=[v for p,v in calls if p=='/v1/responses'][-1]
        self.assertEqual(final['tool_choice'],'none');self.assertEqual(json.loads(final['input'][0]['content']),prompt)
        snapshot=json.loads(final['input'][1]['content']);self.assertEqual(snapshot['schema'],'earnings_review_final_public_snapshot_v1')
        source=[x for x in snapshot['records']if x['type']=='function_call_output'][0]
        self.assertEqual(json.loads(source['output']),{'source_text':self.source})
        self.assertNotIn('INVENTED_OPAQUE_CONTINUITY',json.dumps(final));self.assertEqual(final['text']['format']['name'],'earnings_population_review_v1')
        self.assertEqual(set(final['text']['format']['schema']['properties']),set(verdict))
        reuse=json.loads((slot/'02-prepared-count-reuse.json').read_bytes())
        self.assertTrue(reuse['reused_original_provider_count']);self.assertFalse(reuse['new_count_http_request'])
        self.assertTrue(reuse['context_receipt']['path'].endswith('02-context-04.json'))
        reserved=json.loads((slot/'02-request.json').read_bytes())
        self.assertEqual(final,dict(reserved['payload'],max_output_tokens=f.limits['max_output_tokens'],service_tier='default',store=False))
        self.assertEqual(json.loads(Path(bound['path']).read_bytes()),json.loads((slot/'02-response.json').read_bytes()))
        result=json.loads((slot/'review.json').read_bytes());self.assertEqual(result['review'],verdict)
        self.assertEqual(f.budget.db.execute("SELECT COUNT(*)FROM requests WHERE id!='fixture-prior'AND status='settled'").fetchone(),(2,))

    @unittest.skipUnless(os.getenv('MARKET_RSI_VERIFY_REVIEW23_PUBLIC_SNAPSHOT')=='1','Opt-in exact own23 structural transcript only')
    def test_actual23_public_numbered_responses_and_tool_observations_structural_replay(self):
        slot=Path('/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/edgar-population-20261016/attempts/edgar-population-20261016-23/roles/review-01')
        initial=json.loads((slot/'01-request.json').read_bytes())['payload'];prompt=json.loads((slot/'effective-input.json').read_bytes())
        self.assertEqual(json.loads(initial['input'][0]['content']),prompt)
        request={k:deepcopy(v)for k,v in initial.items()if k!='input'};items=[deepcopy(initial['input'][0])]
        originals=[];source_outputs={};call_count=0
        for turn in range(1,7):
            response_path=slot/f'{turn:02d}-response.json';raw=response_path.read_bytes();originals.append((response_path,hashlib.sha256(raw).hexdigest()))
            response=json.loads(raw);calls=[]
            for item in response['output']:
                if item.get('type')=='reasoning':
                    items.append({'type':'reasoning'})  # Never inspect/copy any original carrier fields.
                    continue
                items.append(deepcopy(item))
                if item.get('type')=='function_call':calls.append(item)
            for call in calls:
                path=slot/f"{turn:02d}-tool-{hashlib.sha256(call['call_id'].encode()).hexdigest()[:12]}.json"
                raw=path.read_bytes();originals.append((path,hashlib.sha256(raw).hexdigest()));output=json.loads(raw)
                self.assertEqual(output['call_id'],call['call_id']);items.append(output);call_count+=1
                if call['name']in{'read_population_program','read_current_program','read_reference_program'}:source_outputs[call['call_id']]=output['output']
        request.update(input=items,tool_choice='none',instructions=request['instructions']+' Explicit offline structural Review completion')
        projected,receipts=packing.review_final_view(request,100);snapshot=json.loads(projected['input'][1]['content'])
        outputs={x['call_id']:x['output']for x in snapshot['records']if x['type']=='function_call_output'}
        self.assertEqual(projected['input'][0],initial['input'][0]);self.assertEqual(call_count,6);self.assertTrue(source_outputs)
        for token,output in source_outputs.items():self.assertEqual(outputs[token],output)
        self.assertFalse(any(x.get('type')=='reasoning'for x in snapshot['records']))
        self.assertEqual([json.loads((slot/f'07-context-{i:02d}-count.json').read_bytes())['input_tokens']for i in range(1,5)],[24136,22843,20947,20131])
        for path,sha in originals:self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),sha)
        # No count/model call: this proves structural availability, NOT token fit.


if __name__=='__main__':unittest.main()
