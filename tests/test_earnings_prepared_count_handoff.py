"""Original count/loan/wire/ledger path; only provider bytes are synthetic.

No production budget, key, company, candidate, network or Docker. Parent/base
strings are immutable public fixtures, not model-authored financial code.
"""
from contextlib import ExitStack
from copy import copy, deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from edgar_forecast_budget import BudgetStop
from edgar_forecast_openai import PreparedCount, budgeted_response
from edgar_forecast_tools import function
import earnings_entry as entry
from earnings_capacity_runtime import _OwnedHTTP
from earnings_http import RawOpenAIHTTP
from earnings_night_budget import DeadlineHTTP, history_snapshot
import earnings_open_context as packing
import earnings_open_roles as roles
import test_earnings_capacity_controller_transport as original


class PreparedCountHandoffTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()
        self.f=original._TransportFixture(self,self.root/'owned')
        self.slot=Path(self.f.slots[0]);self.slot.mkdir(parents=True)
        self.counts=[20];self.wire_calls=[];self.guards=[];self.generation_failure=None
        raw=RawOpenAIHTTP('',30)
        def check(loan):
            self.guards.append(loan)
            if loan is None:self.f.budget.active()
            else:self.f.budget.check_reserved(*loan)
        self.owned=_OwnedHTTP(raw,check,{p:self.f.limits for p in self.f.slots},self.f.rates)
        self.http=entry.ReceiptHTTP(DeadlineHTTP(self.owned,deadline_utc='2099-01-01T00:00:00Z',
            rollout_seconds=120),self.slot)
        owner=self
        class Connection:
            def __init__(inner,host,timeout):
                if host!='api.openai.com':raise AssertionError('Invented provider only')
            def request(inner,method,endpoint,body,headers):
                if method!='POST':raise AssertionError('Original POST required')
                inner.endpoint=endpoint;owner.wire_calls.append((endpoint,json.loads(body)))
            def getresponse(inner):
                if inner.endpoint.endswith('input_tokens'):
                    if not owner.counts:raise AssertionError('Unplanned duplicate count')
                    value={'input_tokens':owner.counts.pop(0),'whole_original_extra':'kept'}
                else:
                    if owner.generation_failure is not None:raise owner.generation_failure
                    value=owner.f.response()
                raw_bytes=original._wire(value)
                return Mock(status=200,getheader=Mock(return_value='req_count_handoff_fixture'),
                    read=Mock(side_effect=lambda limit:raw_bytes[:limit]))
            def close(inner):pass
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('earnings_http.http.client.HTTPSConnection',Connection))

    def request(self):
        return dict(model=original.MODEL,reasoning={'effort':'xhigh'},instructions='Fixed public fixture',
            tools=[],tool_choice='auto',parallel_tool_calls=False,
            input=[dict(role='user',content='public immutable evidence '*1300)])

    def prepare(self,request=None,**options):
        return packing.pack(self.http,self.request() if request is None else request,self.f.limits,
            self.slot,1,prepared_count_context=self.f.context_binding,**options)

    def send(self,request,handoff):
        return budgeted_response(self.http,request,self.f.rates,self.f.limits,self.f.budget,self.slot,1,
            prepared_count=handoff)

    def test_real_owner_loan_receipts_and_temp_ledger_one_count_one_generation(self):
        request,handoff=self.prepare();self.send(request,handoff)
        self.assertEqual([p for p,_ in self.wire_calls],['/v1/responses/input_tokens','/v1/responses'])
        self.assertEqual(len(self.guards),4)
        self.assertEqual(self.guards[:2],[None,None]);self.assertEqual(self.guards[2],self.guards[3])
        self.assertIsNotNone(self.guards[2])
        self.assertEqual(self.f.budget.db.execute("SELECT charged,status FROM requests WHERE id!='fixture-prior'").fetchall(),[(92800,'settled')])
        reuse=json.loads((self.slot/'01-prepared-count-reuse.json').read_bytes())
        self.assertTrue(reuse['reused_original_provider_count']);self.assertFalse(reuse['new_count_http_request'])
        self.assertEqual(reuse['source_context'],self.f.context_binding)
        self.assertEqual(json.loads((self.slot/'01-count.json').read_bytes()),
                         json.loads((self.slot/'01-context-01-count.json').read_bytes()))
        self.assertEqual(len(list(self.slot.glob('http-*.raw.bin'))),2)

    def test_winning_projection_not_initial_oversized_request_is_bound(self):
        self.counts=[10001,20]
        request=self.request();request['input']=[dict(role='user',content='fixed'),
            dict(type='function_call',call_id='x',name='inspect_trace',arguments='{}'),
            dict(type='function_call_output',call_id='x',output='original public output '*3000)]
        before=deepcopy(request);packed,handoff=self.prepare(request)
        self.assertNotEqual(packed,request);self.assertEqual(request,before)
        self.send(packed,handoff)
        self.assertEqual([p for p,_ in self.wire_calls],['/v1/responses/input_tokens']*2+['/v1/responses'])
        reuse=json.loads((self.slot/'01-prepared-count-reuse.json').read_bytes())
        self.assertTrue(reuse['context_receipt']['path'].endswith('01-context-02.json'))
        self.assertEqual(self.wire_calls[1][1],packed)

    def test_v2_author_final_snapshot_keeps_inline_base_and_comparison(self):
        self.counts=[10001,10001,10001,20]
        request=self.request();request['tool_choice']='none'
        fields={'decision_sha256','comparison_parent_source_sha256','implementation_base_source_sha256','edits','test_text'}
        request['text']={'format':{'name':'earnings_population_delta_author_v2',
            'schema':{'properties':{k:{} for k in fields}}}}
        initial=json.dumps(dict(implementation_base_source_text='exact rejected inert base '*1200,
            comparison_parent={'version_id':'a'*64,'source':{'sha256':'b'*64}}))
        request['input']=[dict(role='user',content=initial),
            dict(type='reasoning',id='opaque-not-interpreted'),
            dict(type='function_call',call_id='old',name='inspect_trace',arguments='{}'),
            dict(type='function_call_output',call_id='old',output='public observation '*3000),
            dict(type='message',role='assistant',content=[dict(type='output_text',text='Public partial draft')])]
        packed,handoff=self.prepare(request,author_final=True)
        self.assertEqual(packed['input'][0]['content'],initial)
        self.assertEqual(json.loads(packed['input'][1]['content'])['schema'],'earnings_author_final_public_snapshot_v1')
        self.send(packed,handoff)
        self.assertEqual(len(self.wire_calls),5)
        self.assertEqual(self.wire_calls[-2][1],packed)
        self.assertEqual(self.wire_calls[-1][1]['text'],request['text'])
        reuse=json.loads((self.slot/'01-prepared-count-reuse.json').read_bytes())
        self.assertTrue(reuse['context_receipt']['path'].endswith('01-context-04.json'))

    def test_real_open_role_activates_handoff_without_changed_model_or_bounds(self):
        self.slot.rmdir()  # This test's fresh empty invented directory only.
        broker=Mock(definitions=[function('inspect_trace','Invented public evidence',{'slot':{'type':'string'}})])
        role=roles.OpenController(self.f.context_binding,budget=self.f.budget,
            client_factory=lambda:self.owned,broker=broker,max_turns=1)
        prompt=dict(self.f.prompt,public_fixture='immutable public input '*1400)
        bound=role.propose(prompt,str(self.slot))
        self.assertEqual(json.loads(Path(bound['path']).read_bytes())['status'],'completed')
        self.assertEqual([p for p,_ in self.wire_calls],['/v1/responses/input_tokens','/v1/responses'])
        self.assertEqual(self.wire_calls[-1][1]['model'],original.MODEL)
        self.assertEqual(self.wire_calls[-1][1]['reasoning'],{'effort':'xhigh'})
        self.assertEqual(json.loads((self.slot/'effective-input.json').read_bytes()),prompt)

    def test_opaque_clone_and_durable_used_marker_refuse_second_reservation(self):
        request,handoff=self.prepare()
        with self.assertRaises(TypeError):copy(handoff)
        forged=object.__new__(PreparedCount)
        with self.assertRaises(ValueError):self.send(request,forged)
        self.send(request,handoff)
        self.assertTrue((self.slot/'01-prepared-count-consumed.json').is_file())
        before=history_snapshot(self.f.budget.db)
        with self.assertRaises(ValueError):self.send(request,handoff)
        self.assertEqual(history_snapshot(self.f.budget.db),before)
        self.assertEqual(len(self.wire_calls),2)

    def test_unknown_generation_preserves_original_uncertainty_and_consumption(self):
        request,handoff=self.prepare();self.generation_failure=TimeoutError('Invented no-response failure')
        with self.assertRaises(TimeoutError):self.send(request,handoff)
        self.assertEqual(self.f.budget.db.execute("SELECT status FROM requests WHERE id!='fixture-prior'").fetchall(),[('uncertain',)])
        self.assertTrue((self.slot/'01-prepared-count-consumed.json').is_file())
        self.assertTrue((self.slot/'01-prepared-count-reuse.json').is_file())
        self.assertEqual(len(self.wire_calls),2)


if __name__=='__main__':unittest.main()
