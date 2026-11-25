"""Lossless Author evidence handoff; counts and HTTP are explicitly synthetic."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import earnings_open_context as context
from edgar_forecast_budget import BudgetStop, PilotBudget
from edgar_forecast_openai import budgeted_response
from earnings_entry import ReceiptHTTP


def sha(value):
    return hashlib.sha256(value).hexdigest()


class AuthorObservationDeliveryTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='invented-author-observations-')
        self.addCleanup(temporary.cleanup); self.root=Path(temporary.name).resolve()
        self.limits={'max_input_tokens':10000,'max_output_tokens':32768}
        self.old=json.dumps({'old_result':'OLD_NONFILING_'*1500})
        self.filing=json.dumps({'path':'filings/invented.md','text':
            '| Year | Invented revenue USD |\n| 2025 | (17) |\n'*180+'FILING_TAIL_EXACT'})
        self.new=json.dumps({'ok':True,'value':{'source_text':
            'def invented(payload):\n    return payload\n'*220+'NEW_SOURCE_TAIL_EXACT'}})
        fields={name:{'type':'string'} for name in ('decision_sha256','source_text','test_text')}
        self.request={'model':'gpt-6.1-sol','reasoning':{'effort':'max'},'instructions':'Frozen Author instructions',
            'tools':[{'type':'function','name':'invented_tool','parameters':{'type':'object'}}],
            'parallel_tool_calls':False,'tool_choice':'auto',
            'text':{'format':{'type':'json_schema','name':'earnings_open_author_v1','strict':True,
                'schema':{'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}}},
            'input':[{'role':'user','content':'EXACT_INITIAL_PACKET'},
                {'type':'reasoning','id':'invented-reasoning-id','encrypted_content':'INVENTED_OPAQUE_'*2400},
                self.call('old','run_python',{'source':'invented old source','payload_json':'{}'}),
                self.output('old',self.old),self.message('Old non-filing result already consumed.'),
                self.call('filing','read_file',{'path':'filings/invented.md','offset':0,'characters':20000}),
                self.output('filing',self.filing),self.message('The original filing was consumed.'),
                self.call('new','run_python',{'source':'invented new source','payload_json':'{}'}),
                self.output('new',self.new)]}

    @staticmethod
    def call(identifier,name,arguments):
        return {'type':'function_call','call_id':identifier,'name':name,'arguments':json.dumps(arguments)}

    @staticmethod
    def output(identifier,text):
        return {'type':'function_call_output','call_id':identifier,'output':text}

    @staticmethod
    def message(text):
        return {'type':'message','role':'assistant','content':[{'type':'output_text','text':text}]}

    @staticmethod
    def outputs(request):
        return {item['call_id']:item['output'] for item in request['input'] if item.get('type')=='function_call_output'}

    def receipt(self,turn,step):
        return json.loads((self.root/f'{turn:02d}-context-{step:02d}.json').read_bytes())

    def test_new_source_delivered_full_before_first_consumption_old_output_projected(self):
        before=deepcopy(self.request); client=Mock()
        client.post.side_effect=[{'input_tokens':20000},{'input_tokens':9000}]
        selected=context.pack(client,self.request,self.limits,self.root,1)
        outputs=self.outputs(selected)
        self.assertEqual(outputs['new'],self.new); self.assertIn('NEW_SOURCE_TAIL_EXACT',outputs['new'])
        self.assertEqual(outputs['filing'],self.filing); self.assertIn('FILING_TAIL_EXACT',outputs['filing'])
        projected=json.loads(outputs['old'])
        self.assertTrue(projected['truncated']); self.assertEqual(projected['original_output_sha256'],sha(self.old.encode()))
        self.assertEqual(self.request,before)
        for index,item in enumerate(before['input']):
            if item.get('type')!='function_call_output': self.assertEqual(selected['input'][index],item)
        self.assertEqual({k:v for k,v in selected.items() if k!='input'},{k:v for k,v in before.items() if k!='input'})
        self.assertEqual(client.post.call_count,2)

    def test_entire_newest_contiguous_batch_preserved_with_exact_ids_and_hash_receipts(self):
        request=deepcopy(self.request)
        request['input'].insert(-1,self.call('new-two','read_reference_program',{'offset':0,'characters':6000}))
        second='SECOND_NEWEST_BODY_'*500+'SECOND_TAIL'
        request['input'].append(self.output('new-two',second))
        self.assertEqual(context.author_preserved_outputs(request),frozenset({'filing','new','new-two'}))
        client=Mock(); client.post.side_effect=[{'input_tokens':20000},{'input_tokens':9000}]
        selected=context.pack(client,request,self.limits,self.root,2)
        self.assertEqual(self.outputs(selected)['new-two'],second)
        self.assertEqual(self.outputs(selected)['new'],self.new)
        expected=[{'call_id':item['call_id'],'original_output_sha256':sha(item['output'].encode()),
            'original_output_bytes':len(item['output'].encode())} for item in request['input']
            if item.get('type')=='function_call_output' and item['call_id'] in {'filing','new','new-two'}]
        receipt=self.receipt(2,2)
        self.assertEqual(receipt['preserved_observations'],expected)
        self.assertEqual([row['call_id'] for row in receipt['projections']],['old'])
        self.assertEqual(receipt['effective_request_sha256'],sha(context.encoded(selected)))
        self.assertEqual(receipt['original_request_sha256'],sha(context.encoded(request)))

    def test_original_filing_survives_later_nonfiling_turn_but_consumed_source_can_project(self):
        request=deepcopy(self.request)
        request['input'].extend([self.message('New source has now reached its consumer.'),
            self.call('later','calculate',{'expression':'1+1'}),self.output('later','{"value":2}')])
        protected=context.author_preserved_outputs(request)
        self.assertEqual(protected,frozenset({'filing','later'}))
        selected,receipts=context.project(request,100,preserve_call_ids=protected)
        self.assertEqual(self.outputs(selected)['filing'],self.filing)
        self.assertTrue(json.loads(self.outputs(selected)['new'])['truncated'])
        self.assertEqual({row['call_id'] for row in receipts},{'old','new'})

    def test_final_and_early_fourth_snapshots_keep_full_filing_and_unseen_source(self):
        for turn,early in ((3,False),(4,True)):
            request=deepcopy(self.request)
            if not early: request['tool_choice']='none'
            completion=dict(deepcopy(request),tool_choice='none',instructions=request['instructions']+' FINAL')
            client=Mock(); client.post.side_effect=[{'input_tokens':n} for n in (22000,18000,15000,9000)]
            selected=context.pack(client,request,self.limits,self.root,turn,
                author_final=not early,completion_request=completion if early else None)
            self.assertEqual(client.post.call_count,4)
            self.assertEqual(selected['input'][0],request['input'][0]); self.assertEqual(selected['tool_choice'],'none')
            snapshot=json.loads(selected['input'][1]['content']); records=snapshot['records']
            outputs={row['call_id']:row['output'] for row in records if row['type']=='function_call_output'}
            self.assertEqual(outputs['filing'],self.filing); self.assertEqual(outputs['new'],self.new)
            self.assertTrue(json.loads(outputs['old'])['truncated'])
            self.assertNotIn('INVENTED_OPAQUE_',json.dumps(selected))
            receipt=self.receipt(turn,4)
            self.assertEqual({row['call_id'] for row in receipt['preserved_observations']},{'filing','new'})
            if early:
                self.assertIs(receipt['early_finalization'],True)
                self.assertEqual(receipt['finalization_request_sha256'],sha(context.encoded(completion)))
            by_index={row['input_index']:row for row in receipt['projections']}
            for index in (6,9):
                row=by_index[index]; self.assertEqual(row['observation_projections'],[])
                self.assertEqual(row['original_item_sha256'],sha(context.encoded(request['input'][index])))
                expected_record={k:request['input'][index][k] for k in ('type','call_id','output')}
                self.assertEqual(row['public_record_sha256'],sha(context.encoded(expected_record)))

    def test_explicit_preservation_helpers_keep_legacy_defaults_unchanged(self):
        old,receipts=context.project(self.request,100)
        self.assertEqual({row['call_id'] for row in receipts},{'old','filing','new'})
        self.assertTrue(json.loads(self.outputs(old)['new'])['truncated'])
        final=dict(deepcopy(self.request),tool_choice='none')
        default,_=context.author_final_view(final,100)
        preserved,_=context.author_final_view(final,100,preserve_call_ids=frozenset({'filing','new'}))
        def records(value): return json.loads(value['input'][1]['content'])['records']
        default_outputs={row['call_id']:row['output'] for row in records(default) if row['type']=='function_call_output'}
        preserved_outputs={row['call_id']:row['output'] for row in records(preserved) if row['type']=='function_call_output'}
        self.assertTrue(json.loads(default_outputs['filing'])['truncated'])
        self.assertEqual(preserved_outputs['filing'],self.filing)

    def test_nonAuthor_and_inexact_format_keep_old_projection_behavior(self):
        for turn,kind in enumerate(('controller','missing-property','extra-property','missing-format'),10):
            request=deepcopy(self.request)
            fmt=request['text']['format']
            if kind=='controller': fmt['name']='earnings_open_decision_v1'
            elif kind=='missing-property': del fmt['schema']['properties']['source_text']
            elif kind=='extra-property': fmt['schema']['properties']['extra']={'type':'string'}
            else: request.pop('text')
            self.assertEqual(context.author_preserved_outputs(request),frozenset())
            client=Mock(); client.post.side_effect=[{'input_tokens':20000},{'input_tokens':9000}]
            selected=context.pack(client,request,self.limits,self.root,turn)
            self.assertEqual(selected,context.project(request,2000)[0])
            self.assertNotIn('preserved_observations',self.receipt(turn,2))

    def test_unfit_preserved_body_stops_before_generation_without_retry_or_gate_relaxation(self):
        request=dict(deepcopy(self.request),tool_choice='none')
        request['input']=[request['input'][0],request['input'][1],request['input'][8],request['input'][9]]
        client=Mock(); client.post.return_value={'input_tokens':10001}
        with self.assertRaises(BudgetStop): context.pack(client,request,self.limits,self.root,20,author_final=True)
        # Projection views identical to native are deduplicated, not recounted.
        self.assertEqual(client.post.call_count,2)
        for call in client.post.call_args_list:
            self.assertEqual(call.args[0],'/v1/responses/input_tokens')
            candidate=call.args[1]
            text=candidate['input'][1].get('content')
            if text and text.startswith('{'):
                rows=json.loads(text)['records']; self.assertEqual(rows[-1]['output'],self.new)
            else: self.assertEqual(self.outputs(candidate)['new'],self.new)
        self.assertFalse(list(self.root.glob('*-request.json')))

    def test_count_failure_propagates_once_and_initial_packet_is_never_compacted(self):
        client=Mock(); client.post.side_effect=TimeoutError('invented count failure')
        with self.assertRaises(TimeoutError): context.pack(client,self.request,self.limits,self.root,21)
        self.assertEqual(client.post.call_count,1)
        request=dict(deepcopy(self.request),tool_choice='none')
        request['input'][0]['content']='IMMUTABLE_INITIAL_'*5000
        client=Mock(); client.post.return_value={'input_tokens':10001}
        with self.assertRaises(BudgetStop): context.pack(client,request,self.limits,self.root,22,author_final=True)
        self.assertEqual(client.post.call_count,4)
        self.assertTrue(all(call.args[1]['input'][0]==request['input'][0] for call in client.post.call_args_list))

    def test_small_request_keeps_original_stock_count_path_and_no_implicit_projection(self):
        request=deepcopy(self.request); request['input']=[request['input'][0],self.call('s','run_python',{}),self.output('s','small')]
        client=Mock(); self.assertEqual(context.pack(client,request,self.limits,self.root,23),request)
        client.post.assert_not_called(); self.assertFalse(list(self.root.iterdir()))

    def test_selected_new_body_matches_recount_reservation_and_mocked_physical_generation(self):
        calls=[]; counts=iter((22000,9000,9000)); before=deepcopy(self.request)
        class Client:
            def post(inner,endpoint,payload):
                calls.append((endpoint,deepcopy(payload)))
                if endpoint.endswith('input_tokens'): return {'input_tokens':next(counts)}
                return {'model':before['model'],'service_tier':'default','status':'completed','error':None,
                    'output':[],'usage':{'input_tokens':9000,'output_tokens':7,'total_tokens':9007,
                        'input_tokens_details':{'cached_tokens':0}}}
        transport=ReceiptHTTP(Client(),self.root)
        selected=context.pack(transport,self.request,self.limits,self.root,24)
        budget=PilotBudget(self.root/'invented-budget.sqlite3'); self.addCleanup(budget.close)
        rates={'api_model':before['model'],'effort':'max','input':'2','cached':'.1','write':'2.5','output':'10'}
        budgeted_response(transport,selected,rates,self.limits,budget,self.root,24)
        self.assertEqual([endpoint for endpoint,_ in calls],['/v1/responses/input_tokens']*3+['/v1/responses'])
        self.assertEqual(calls[1][1],selected); self.assertEqual(calls[2][1],selected)
        reserved=json.loads((self.root/'24-request.json').read_bytes())
        self.assertEqual(reserved['payload'],selected)
        self.assertEqual(calls[-1][1],dict(selected,max_output_tokens=32768,service_tier='default',store=False))
        self.assertEqual(self.outputs(calls[-1][1])['new'],self.new)
        self.assertEqual(self.outputs(calls[-1][1])['filing'],self.filing)
        self.assertEqual(budget.db.execute('SELECT status FROM requests').fetchall(),[('settled',)])
        self.assertEqual(budget.summary()['unresolved_reserved_usd'],0)
        self.assertEqual(self.request,before)


if __name__=='__main__': unittest.main()
