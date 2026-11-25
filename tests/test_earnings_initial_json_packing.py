"""Lossless initial C JSON packing; synthetic transport, no provider or model."""
from copy import deepcopy
import json
import unittest
from unittest import mock
import earnings_open_roles as roles
import test_earnings_open_roles as transport_fixture


class InitialJSON(unittest.TestCase):
    def packet(self, n=14):
        return {'feedback': {'schema': 'earnings_training25_public_summary_v1', 'logical_round': n,
                'rows': [{'company': 'synthetic', 'targets': [{'value': 1.25, 'award': .5}]}]},
                'literal': '  keep inner spaces, \n quotes " 中文 and : , unchanged  ', 'empty': [], 'null': None}

    def test_lossless_all_fields_and_literal_strings(self):
        original=self.packet(); before=deepcopy(original)
        content,policy=roles._initial_user_json(original,'controller')
        self.assertEqual(json.loads(content),original); self.assertEqual(original,before)
        self.assertEqual(policy,'lossless_compact_initial_json_v1')
        self.assertLess(len(content.encode()),len(json.dumps(original,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()))

    def test_legacy_and_other_roles_remain_byte_exact(self):
        cases=[(self.packet(13),'controller'),(self.packet(),'author'),(self.packet(),'review'),
               ({'feedback':{'logical_round':14}},'controller'),(self.packet(True),'controller')]
        for packet,role in cases:
            with self.subTest(role=role,packet=packet):
                content,policy=roles._initial_user_json(packet,role)
                self.assertEqual(content,json.dumps(packet,sort_keys=True,ensure_ascii=False,allow_nan=False))
                self.assertIsNone(policy)

    def test_current_future_rounds_bounded_by_exact_feedback_type(self):
        self.assertEqual(roles._initial_user_json(self.packet(15),'controller')[1],'lossless_compact_initial_json_v1')
        for n in (14.0,'14',None): self.assertIsNone(roles._initial_user_json(self.packet(n),'controller')[1])
        bad=self.packet();bad['feedback']['schema']='unrelated'
        self.assertIsNone(roles._initial_user_json(bad,'controller')[1])

    def test_nonfinite_rejected_not_serialized_as_new_data(self):
        packet=self.packet();packet['invalid']=float('nan')
        with self.assertRaises(ValueError):roles._initial_user_json(packet,'controller')

    def test_real_open_loop_two_turns_preserves_feedback_and_observation(self):
        fixture=transport_fixture.OpenRoleTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.prompt.update(self.packet());original=deepcopy(fixture.prompt)
        fixture.broker.handler=lambda *_:{'literal':'  public observation unchanged  '}
        fixture.generations=[fixture.tool_response(fixture.call()),fixture.message(fixture.choice())]
        service=fixture.service(limits={'max_input_tokens':32000,'max_output_tokens':16384,'wall_seconds':900})
        with mock.patch.object(roles,'pack',side_effect=lambda client,request,*args,**kwargs:request), \
             mock.patch.object(roles,'budgeted_response',side_effect=fixture.fake_paid):
            service.propose(fixture.prompt,str(fixture.slot))
        self.assertEqual(fixture.prompt,original);self.assertEqual(len(fixture.requests),2)
        for request in fixture.requests:
            self.assertEqual(json.loads(request['input'][0]['content']),original)
            self.assertEqual(request['input'][0]['content'],roles._initial_user_json(original,'controller')[0])
        output=next(x for x in fixture.requests[1]['input'] if x.get('type')=='function_call_output')
        self.assertEqual(json.loads(output['output'])['literal'],'  public observation unchanged  ')
        identity=json.loads((fixture.slot/'identity.json').read_text())
        self.assertEqual(identity['initial_user_serialization'],'lossless_compact_initial_json_v1')
        self.assertEqual(json.loads((fixture.slot/'effective-input.json').read_text()),original)
        self.assertEqual(service.context['limits'],{'max_input_tokens':32000,'max_output_tokens':16384,'wall_seconds':900})


if __name__=='__main__':unittest.main()
