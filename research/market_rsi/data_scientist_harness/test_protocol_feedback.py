"""Malformed paid output remains immutable; only bounded explicit feedback runs."""
import json
from pathlib import Path
import tempfile
import unittest

from data_scientist_harness.broker import Broker, TOOLS, ALLOWED_TOOLS
from data_scientist_harness import fixtures
from codex_glm_provider import ControllerSession
from paid_budget import PaidBudget
from market_rsi import load_json
from glm_canary import MODEL

BAD='<tool_call>record_research-obj-1</arg_value></tool_call>'


class Backend:
    def __init__(self): self.samples=0
    def encode(self, turn):
        return {'rendered_prompt':'synthetic','token_ids':[1,2,3],'tokenizer_repo':'fixture',
            'tokenizer_revision':'fixture','chat_template_sha256':'a'*64}
    def sample(self,*args):
        self.samples+=1
        return {'text':BAD,'output_tokens':[4,5],'cached_input_tokens':0,'finish_reason':'stop','provider':{}}


class ProtocolFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/'work'
        self.b=Broker(self.root,fixtures.workspace(self.root))
        self.budget=PaidBudget.create(Path(self.tmp.name)/'budget',{'experiment_id':'fixture',
            'cap_usd':'10','target_usd':'10','buckets_usd':{'learning':'10'},'authority':'synthetic only'})
        self.backend=Backend()
        self.session=ControllerSession(session_id='fixture-feedback',output=self.root/'session',
            backend=self.backend,budget=self.budget,budget_bucket='learning',allowed_tools=ALLOWED_TOOLS,
            submit_tool='submit_research_decision',protocol_error_tool='report_protocol_error',max_protocol_feedback=2)
        self.request={'model':MODEL,'stream':True,'store':False,'instructions':'synthetic',
            'input':[{'type':'message','role':'user','content':'fixture'}],
            'tools':[{'type':'function','name':'mcp__controller_tools__'+t['name'],
                'description':t['description'],'parameters':t['inputSchema']} for t in TOOLS]}

    def tearDown(self): self.tmp.cleanup()

    def step(self):
        result=self.session.handle(self.request)
        call=result[-1]['response']['output'][0]
        self.assertEqual(call['name'],'report_protocol_error')
        args=json.loads(call['arguments'])
        receipt=self.b.call(call['name'],args)
        self.request['input'] += [call,{'type':'function_call_output','call_id':call['call_id'],
            'output':json.dumps(receipt)}]
        return receipt,args

    def test_original_response_metered_and_never_executed(self):
        receipt,args=self.step()
        self.assertFalse(receipt['original_action_executed'])
        self.assertFalse(receipt['model_authored_tool_call'])
        self.assertEqual(self.backend.samples,1)
        self.assertEqual(load_json(self.root/'session/turn-001/response.json')['text'],BAD)
        self.assertEqual([r['tool'] for r in self.b.store.records()],['report_protocol_error'])
        self.assertEqual(next(iter(self.budget.snapshot()['jobs'].values()))['state'],'metered_terminal')
        with self.assertRaisesRegex(ValueError,'already delivered'):self.b.call('report_protocol_error',args)

    def test_third_bad_completion_stops_without_fourth_sample(self):
        self.step();self.step()
        with self.assertRaisesRegex(ValueError,'forbidden wire tool'):self.session.handle(self.request)
        self.assertTrue(self.session.failed);self.assertEqual(self.backend.samples,3)
        with self.assertRaisesRegex(ValueError,'terminal'):self.session.handle(self.request)
        self.assertEqual(self.backend.samples,3)
        self.assertEqual(len(self.budget.snapshot()['jobs']),3)

    def test_changed_response_or_fabricated_receipt_is_rejected(self):
        result=self.session.handle(self.request);call=result[-1]['response']['output'][0]
        args=json.loads(call['arguments']);args['receipt_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'does not match'):self.b.call('report_protocol_error',args)


if __name__=='__main__':unittest.main()
