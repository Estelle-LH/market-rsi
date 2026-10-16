"""Synthetic open-role tests: mocked generations/broker, no paid or Docker work."""
from copy import deepcopy
import datetime as dt
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

import earnings_open_roles as roles
from edgar_forecast_tools import function
from earnings_http import save_bytes
from market_rsi import digest


class Broker:
    def __init__(self):
        self.definitions = [
            function('inspect_trace','Read a registered synthetic trace.',{'slot':{'type':'string'}}),
            function('read_current_program','Read selected public program source.',{'axis':{'type':'string','enum':['R','H']}}),
            function('search_literature','Search scholarly methods.',{'query':{'type':'string'}})]
        self.calls = []
        self.handler = lambda name,args: {'synthetic':True,'name':name,'arguments':args}

    def dispatch(self,name,args):
        self.calls.append((name,deepcopy(args)))
        return self.handler(name,args)


class OpenRoleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.broker = Broker()
        self.budget = mock.Mock(monotonic_deadline=time.monotonic()+1200)
        self.budget.summary.return_value = {'synthetic':True,'paid_accounting_tested':False}
        self.factory = mock.Mock(return_value=mock.Mock(timeout=20))
        self.generations, self.requests = [], []
        self.prompt = {'parent_pair_sha256':'a'*64,'feedback_sha256':'b'*64,
                       'feedback':{'synthetic':True},'program_sources':{'R':'PROGRAM = ...'}}

    def service(self,author=False,limits=None,**options):
        name = 'author' if author else 'controller'
        self.slot = self.root/'roles'/(name+'-01')
        context = {'schema':'earnings_capacity_'+name+'_transport_v1','source_commit':'c'*40,
            'root':str(self.root),'rates':{'api_model':'gpt-6.1-sol','effort':'max','input':'2','cached':'0.1','write':'2.5','output':'10'},
            'limits':limits or {'max_input_tokens':10000,'max_output_tokens':16384,'wall_seconds':600},
            'cutoff_utc':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'cutoff_monotonic':time.monotonic()+1200,'slots':[str(self.slot)]}
        path = self.root/(name+'-context.json')
        roles.e.durable_json(path,context)
        binding = {'path':str(path),'sha256':roles.e.digest(path.read_bytes())}
        self.context_path = path
        return (roles.OpenAuthor if author else roles.OpenController)(binding,budget=self.budget,
            client_factory=self.factory,broker=self.broker,**options)

    def choice(self,axis='R'):
        return {'schema':'earnings_capacity_decision_v1','axis':axis,
            'component':{'R':'research_policy','H':'tool_interface','continue':'none'}[axis],
            'parent_pair_sha256':'a'*64,'feedback_sha256':'b'*64,
            'hypothesis':'Investigate a synthetic repeated failure.',
            'expected_effect':('Retain the current version.' if axis=='continue' else
                'earnings-shadow-v1|'+{'R':'research_policy','H':'tool_interface'}[axis]+'|input_tokens|lower|1|score_nonregression|matched_trial_only')}

    def message(self,value):
        return {'status':'completed','error':None,'output':[{'type':'message','role':'assistant','status':'completed',
            'content':[{'type':'output_text','text':json.dumps(value)}]}]}

    def call(self,token='call_1',name='inspect_trace',arguments=None):
        return {'type':'function_call','call_id':token,'name':name,
                'arguments':json.dumps({'slot':'forecast-01'} if arguments is None else arguments)}

    def tool_response(self,*calls):
        return {'status':'completed','error':None,'output':[{'type':'reasoning','id':'synthetic_reasoning'},*calls]}

    def fake_paid(self,client,request,rates,limits,budget,output,turn):
        # Deliberately mocked accounting: these are not original ledger/provider receipts.
        self.requests.append(deepcopy(request))
        value = self.generations.pop(0)
        if isinstance(value,BaseException):
            raise value
        if callable(value):
            value = value(output)
        roles.e.durable_json(output/f'{turn:02d}-count.json',{'input_tokens':1,'synthetic':True})
        roles.e.durable_json(output/f'{turn:02d}-request.json',{'payload':request,'synthetic':True})
        raw = (json.dumps(value,indent=3)+'\n\n').encode()
        save_bytes(output/f'{turn:02d}-response.json',raw)
        return value

    def invoke(self,service=None):
        service = self.service() if service is None else service
        with mock.patch.object(roles,'budgeted_response',side_effect=self.fake_paid):
            return service.propose(self.prompt,str(self.slot))

    def failure(self):
        return json.loads((self.slot/'result.json').read_text())

    def test_controller_drives_multiple_tools_then_exact_final_alias(self):
        self.generations = [self.tool_response(self.call(),self.call('call_2','search_literature',{'query':'seasonality methods'})),
                            self.message(self.choice())]
        bound = self.invoke()
        self.assertEqual(len(self.requests),2)
        self.assertEqual(len(self.broker.calls),2)
        self.assertEqual((self.slot/'response.json').read_bytes(),(self.slot/'02-response.json').read_bytes())
        self.assertEqual(bound['sha256'],roles.e.digest((self.slot/'02-response.json').read_bytes()))
        self.assertEqual([item['call_id'] for item in self.requests[1]['input'] if item.get('type')=='function_call_output'],['call_1','call_2'])
        self.assertEqual(self.requests[0]['text']['format']['type'],'json_schema')
        self.assertEqual(self.failure()['status'],'COMPLETED_DECISION')
        self.assertFalse(self.failure()['model_authorship_verified'])

    def test_actual_count_reservation_and_settlement_on_owned_temp_ledger(self):
        # Only HTTP bytes are invented. Use real counting, reservation, raw
        # receipts and settlement; active() must not reject our in-flight loan.
        from test_earnings_capacity_controller_transport import _TransportFixture
        fixture=_TransportFixture(self,self.root/'actual-accounting')
        service=roles.OpenController(fixture.context_binding,budget=fixture.budget,
            client_factory=fixture.factory,broker=self.broker)
        bound=fixture.invoke(fixture.response(),prompt=self.prompt,service=service)
        self.assertEqual(len(fixture.calls),2)
        self.assertEqual(fixture.budget.db.execute(
            "SELECT charged,status FROM requests WHERE id!='fixture-prior'").fetchall(),[(92800,'settled')])
        self.assertEqual(fixture.budget.summary()['unresolved_reserved_usd'],0)
        self.assertEqual(Path(bound['path']).read_bytes(),(Path(fixture.slots[0])/'01-response.json').read_bytes())

    def test_overflow_packing_then_owned_http_count_reserve_send_and_settle(self):
        # Real production transport/budget/raw receipt classes; invented HTTPS
        # bytes and an independently owned temporary ledger, never a real key.
        from test_earnings_capacity_controller_transport import _TransportFixture,_wire
        from earnings_capacity_runtime import _OwnedHTTP
        fixture=_TransportFixture(self,self.root/'packed-accounting')
        def check(loan):
            rows=fixture.budget.db.execute("SELECT id,model,reserved FROM requests WHERE status='reserved'").fetchall()
            if loan is None:
                self.assertEqual(rows,[]);fixture.budget.active()
            else:self.assertEqual(rows,[loan])
        owned=_OwnedHTTP(fixture.http,check,{p:fixture.limits for p in fixture.slots},fixture.rates)
        fixture.factory.side_effect=lambda:owned
        self.broker.handler=lambda *_:{'public_text':'x'*40000}
        replies=[fixture.response(),fixture.response(self.choice('continue'))]
        replies[0]['output']=[self.call()]
        generated=[]
        class Connection:
            def __init__(inner,host,timeout):self.assertEqual(host,'api.openai.com')
            def request(inner,method,endpoint,body,headers):
                self.assertEqual(method,'POST');inner.endpoint=endpoint;inner.payload=json.loads(body)
                fixture.calls.append((endpoint,deepcopy(inner.payload)))
            def getresponse(inner):
                if inner.endpoint.endswith('input_tokens'):
                    count=23027 if len(json.dumps(inner.payload['input']))>24000 else 100
                    raw=_wire({'input_tokens':count})
                else:
                    self.assertLess(len(generated),2)
                    raw=_wire(replies[len(generated)]);generated.append(deepcopy(inner.payload))
                return mock.Mock(status=200,getheader=mock.Mock(return_value='req_packed_fixture'),
                    read=mock.Mock(side_effect=lambda limit:raw[:limit]))
            def close(inner):pass
        fixture.fake_connection=lambda _:Connection
        service=roles.OpenController(fixture.context_binding,budget=fixture.budget,
            client_factory=fixture.factory,broker=self.broker)
        fixture.invoke(replies[-1],prompt=self.prompt,service=service)
        self.assertEqual(len(generated),2)
        output=next(item for item in generated[-1]['input'] if item.get('type')=='function_call_output')
        self.assertTrue(json.loads(output['output'])['truncated'])
        self.assertEqual(fixture.budget.db.execute(
            "SELECT status FROM requests WHERE id!='fixture-prior'").fetchall(),[('settled',),('settled',)])
        slot=Path(fixture.slots[0])
        self.assertEqual(json.loads((slot/'02-context-01-count.json').read_bytes())['input_tokens'],23027)
        self.assertEqual(json.loads((slot/'02-count.json').read_bytes())['input_tokens'],100)
        self.assertEqual(json.loads((slot/'02-request.json').read_bytes())['payload'],
            {k:v for k,v in generated[-1].items() if k not in {'max_output_tokens','store','service_tier'}})

    def test_author_reads_current_program_and_returns_executable_source_without_executing(self):
        service = self.service(author=True)
        chosen = self.choice()
        source = "PROGRAM = {'axis':'R'}\nimport math\ndef run(payload):\n    return {'value': math.fsum(payload['values'])}\n"
        payload = {'decision_sha256':digest(chosen),'source_text':source,
                   'test_text':"CASES = [{'input': {'values': [1, 2]}, 'expected': {'value': 3}}]"}
        self.generations = [self.tool_response(self.call(name='read_current_program',arguments={'axis':'R'})),self.message(payload)]
        with mock.patch.object(roles,'budgeted_response',side_effect=self.fake_paid):
            service.author(chosen,{'axis':'R'},str(self.slot))
        saved = json.loads((self.slot/'candidate.json').read_text())['candidate']
        self.assertEqual(saved['source_sha256'],roles.e.digest(source.encode()))
        self.assertFalse(saved['tests_executed'])
        self.assertEqual(self.broker.calls,[('read_current_program',{'axis':'R'})])
        self.assertEqual((self.slot/'response.json').read_bytes(),(self.slot/'02-response.json').read_bytes())

    def test_invalid_broker_arguments_are_explicit_rejection_observations(self):
        self.generations = [self.tool_response(self.call(arguments={'host_path':'/secret'})),self.message(self.choice('continue'))]
        self.invoke()
        self.assertEqual(self.broker.calls,[])
        observed = next(item for item in self.requests[1]['input'] if item.get('type')=='function_call_output')
        self.assertEqual(json.loads(observed['output'])['error_type'],'ValueError')

    def test_broker_value_error_is_retained_as_rejection_not_claimed_success(self):
        def reject(name,args):
            raise ValueError('private exception text must not be reflected')
        self.broker.handler = reject
        self.generations = [self.tool_response(self.call()),self.message(self.choice('continue'))]
        self.invoke()
        observed = next(item for item in self.requests[1]['input'] if item.get('type')=='function_call_output')
        self.assertNotIn('private exception text',observed['output'])
        self.assertIn('error',json.loads(observed['output']))

    def test_broker_runtime_failure_aborts_once_without_successful_observation(self):
        def fail(name,args):
            raise RuntimeError('Container cleanup state unknown')
        self.broker.handler = fail
        self.generations = [self.tool_response(self.call()),self.message(self.choice())]
        with self.assertRaises(RuntimeError):
            self.invoke()
        self.assertEqual(len(self.requests),1)
        self.assertEqual(list(self.slot.glob('*-tool-*.json')),[])
        self.assertEqual(self.failure()['error_type'],'RuntimeError')
        self.assertEqual((self.slot/'response.json').read_bytes(),(self.slot/'01-response.json').read_bytes())

    def test_candidate_failure_feedback_precedes_different_model_code_action(self):
        self.broker.definitions=[function('run_python','Synthetic isolated code.',
            {'source':{'type':'string'},'payload_json':{'type':'string'}})]
        bad='def run(p): return missing';good='def run(p): return p+1'
        self.broker.handler=lambda name,args:({'error':{'status':'CANDIDATE_FAILED_NO_RETRY',
            'error_type':'NameError','source_line':1,'same_action_retry_allowed':False}}
            if args['source']==bad else {'value':2,'synthetic':True})
        self.generations=[self.tool_response(self.call(name='run_python',arguments={'source':bad,'payload_json':'1'})),
            self.tool_response(self.call('call_2','run_python',{'source':good,'payload_json':'1'})),
            self.message(self.choice('continue'))]
        self.invoke()
        self.assertEqual([args['source'] for _,args in self.broker.calls],[bad,good])
        observed=next(item for item in self.requests[1]['input'] if item.get('type')=='function_call_output')
        self.assertEqual(json.loads(observed['output'])['error']['error_type'],'NameError')
        self.assertEqual(self.failure()['status'],'COMPLETED_DECISION')
        # Scripted model outputs establish handoff, not actual autonomous repair.

    def test_duplicate_ids_are_rejected_before_dispatch(self):
        self.generations = [self.tool_response(self.call(),self.call())]
        with self.assertRaises(RuntimeError):
            self.invoke()
        self.assertEqual(self.broker.calls,[])
        self.assertEqual(self.failure()['status'],'FAILED_NO_RETRY')

    def test_duplicate_ids_across_turns_stop_before_second_dispatch(self):
        self.generations = [self.tool_response(self.call()),self.tool_response(self.call())]
        with self.assertRaises(RuntimeError):
            self.invoke()
        self.assertEqual(len(self.broker.calls),1)
        self.assertEqual(len(self.requests),2)

    def test_final_turn_is_tool_free_and_attempted_calls_rejected(self):
        service = self.service(max_turns=1)
        self.generations = [self.tool_response(self.call())]
        with self.assertRaises(RuntimeError):
            self.invoke(service)
        self.assertEqual(self.requests[0]['tool_choice'],'none')
        self.assertEqual(self.broker.calls,[])

    def test_closing_instruction_only_on_final_turn_preserves_original_packet_model_and_schema(self):
        original=deepcopy(self.prompt)
        service=self.service(max_turns=2)
        self.generations=[self.tool_response(self.call()),self.message(self.choice('continue'))]
        self.invoke(service)
        first,last=self.requests
        self.assertNotIn(roles.FINALIZE,first['instructions'])
        self.assertEqual(last['instructions'],first['instructions']+roles.FINALIZE+roles.FINAL_CONTROLLER)
        self.assertEqual(first['tool_choice'],'auto');self.assertEqual(last['tool_choice'],'none')
        for key in ('model','reasoning','tools','text','parallel_tool_calls'):
            self.assertEqual(first[key],last[key])
        self.assertEqual(first['input'][0],last['input'][0])
        self.assertEqual(json.loads(last['input'][0]['content']),original)
        self.assertEqual(self.prompt,original)
        self.assertEqual(json.loads((self.slot/'decision.json').read_bytes())['decision'],self.choice('continue'))

    def test_author_finalization_documents_actual_schema_and_preserves_exact_candidate_fields(self):
        service=self.service(author=True,max_turns=1)
        chosen=self.choice()
        source="PROGRAM = {'axis':'R'}\ndef run(payload):\n    return {'advice': 'Check units'}\n"
        payload={'decision_sha256':digest(chosen),'source_text':source,
                 'test_text':"CASES = [{'input': {}, 'expected': {'advice': 'Check units'}}]"}
        self.generations=[self.message(payload)]
        with mock.patch.object(roles,'budgeted_response',side_effect=self.fake_paid):
            service.author(chosen,{'axis':'R'},str(self.slot))
        request=self.requests[0]
        self.assertEqual(request['instructions'],roles.AUTHOR+roles.FINALIZE+roles.FINAL_AUTHOR)
        self.assertEqual(request['tool_choice'],'none')
        self.assertEqual(set(request['text']['format']['schema']['properties']),
                         {'decision_sha256','source_text','test_text'})
        self.assertIn('permit ONLY type, properties, required, additionalProperties, items',roles.AUTHOR)
        self.assertIn('not a host regex',roles.AUTHOR)
        self.assertEqual(json.loads((self.slot/'response.json').read_bytes())['output'][0]['content'][0]['text'],json.dumps(payload))
        saved=json.loads((self.slot/'candidate.json').read_bytes())['candidate']
        self.assertEqual(saved['source_sha256'],roles.e.digest(source.encode()))
        self.assertFalse(saved['tests_executed'])

    def test_incomplete_provider_response_never_accepts_even_complete_business_fields(self):
        service=self.service(author=True,max_turns=1)
        chosen=self.choice()
        payload={'decision_sha256':digest(chosen),
            'source_text':"PROGRAM = {'axis':'R'}\ndef run(payload):\n    return 1\n",
            'test_text':"CASES = [{'input': {}, 'expected': 1}]"}
        incomplete=self.message(payload)
        incomplete.update(status='incomplete',incomplete_details={'reason':'max_output_tokens'})
        self.generations=[incomplete]
        with mock.patch.object(roles,'budgeted_response',side_effect=self.fake_paid),self.assertRaises(RuntimeError):
            service.author(chosen,{'axis':'R'},str(self.slot))
        self.assertEqual(len(self.requests),1)
        self.assertEqual(self.failure()['status'],'FAILED_NO_RETRY')
        self.assertFalse((self.slot/'candidate.json').exists())
        self.assertEqual((self.slot/'response.json').read_bytes(),(self.slot/'01-response.json').read_bytes())
        self.assertEqual(json.loads((self.slot/'response.json').read_bytes())['status'],'incomplete')

    def test_opt_in_author_completion_ceiling_does_not_widen_legacy_author(self):
        ceiling=roles.role_limits()['author']
        self.assertEqual(ceiling,{'max_input_tokens':24000,'max_output_tokens':49152,'wall_seconds':900})
        service=self.service(author=True,limits=ceiling)
        self.assertEqual(service.context['limits'],ceiling)
        from earnings_controller import CapacityAuthor
        with self.assertRaises(ValueError):
            CapacityAuthor(service.binding,budget=self.budget,client_factory=self.factory)
        self.factory.assert_not_called()

    def test_opt_in_author_above_completion_ceiling_is_rejected_before_factory(self):
        ceiling=dict(roles.role_limits()['author'],max_output_tokens=49153)
        with self.assertRaises(ValueError):
            self.service(author=True,limits=ceiling)
        self.factory.assert_not_called()

    def test_tool_ceiling_is_checked_before_batch_dispatch(self):
        service = self.service(max_tool_calls=1)
        self.generations = [self.tool_response(self.call(),self.call('call_2'))]
        with self.assertRaises(RuntimeError):
            self.invoke(service)
        self.assertEqual(self.broker.calls,[])

    def test_malformed_final_object_is_preserved_and_not_retried(self):
        self.generations = [self.message({'not':'a decision'})]
        with self.assertRaises(RuntimeError):
            self.invoke()
        self.assertEqual(len(self.requests),1)
        self.assertFalse((self.slot/'decision.json').exists())
        self.assertTrue((self.slot/'response.json').is_file())
        self.assertTrue((self.slot/'budget-summary.json').is_file())

    def test_consumed_slot_is_never_reopened(self):
        service = self.service()
        self.generations = [self.message(self.choice('continue'))]
        self.invoke(service)
        snapshot = {p.name:p.read_bytes() for p in self.slot.iterdir()}
        with self.assertRaises(FileExistsError):
            self.invoke(service)
        self.assertEqual(snapshot,{p.name:p.read_bytes() for p in self.slot.iterdir()})
        self.assertEqual(len(self.requests),1)

    def test_expired_budget_and_undeclared_slot_do_not_construct_client(self):
        service = self.service()
        self.budget.monotonic_deadline = time.monotonic()-1
        with self.assertRaises(roles.BudgetStop):
            self.invoke(service)
        self.factory.assert_not_called()
        self.assertFalse(self.slot.exists())
        with self.assertRaises(ValueError):
            service.propose(self.prompt,str(self.root/'other'))

    def test_context_drift_is_detected_before_client_factory(self):
        service = self.service()
        self.context_path.write_bytes(b'{}')
        with self.assertRaises(ValueError):
            self.invoke(service)
        self.factory.assert_not_called()

    def test_broker_definition_drift_during_tool_is_terminal(self):
        def drift(name,args):
            self.broker.definitions[0]['description'] = 'changed'
            return {'not':'accepted'}
        self.broker.handler = drift
        self.generations = [self.tool_response(self.call()),self.message(self.choice())]
        with self.assertRaises(RuntimeError):
            self.invoke()
        self.assertEqual(len(self.requests),1)
        self.assertFalse((self.slot/'decision.json').exists())

    def test_prior_artifact_changed_during_send_is_not_rebaselined(self):
        def corrupt(output):
            (output/'effective-input.json').write_bytes(b'{}')
            return self.message(self.choice())
        self.generations = [corrupt]
        with self.assertRaises(RuntimeError):
            self.invoke()
        self.assertEqual(self.failure()['error_type'],'ValueError')

    def test_invalid_constructor_and_continue_author_fail_before_send(self):
        for options in ({'max_turns':0},{'max_tool_calls':25},{'max_turns':True}):
            # Separate role contexts; no role execution or paid calls involved.
            path = self.root/'controller-context.json'
            if path.exists():
                path.unlink()
            with self.assertRaises(ValueError):
                self.service(**options)
        service = self.service(author=True)
        with self.assertRaises(ValueError):
            service.author(self.choice('continue'),{'axis':'R'},str(self.slot))
        self.factory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
