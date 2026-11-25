"""Invented scoped-resource and original paid-transport accounting checks only."""
from copy import deepcopy
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import earnings_capacity_runtime as runtime
import earnings_controller as generic
import earnings_open_resources as resources
import earnings_open_roles as roles
from earnings_loop_policy import LIMITS
from edgar_forecast_openai import unit
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_capacity_controller_transport as transport_fixture
import test_earnings_capacity_runtime as runtime_fixture
import test_earnings_open_resources as resource_fixture
import test_earnings_open_roles as role_fixture


class ControllerHeadroomTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root, self.number = Path(temporary.name).resolve(), 0

    def resources(self):
        f = resource_fixture.ResourceTests(); f.setUp(); self.addCleanup(f.doCleanups)
        f.runtime['sources']['factory_controller'] = engine.pin(resources.e.REPO/'tools/earnings_open_assembly.py')
        return f

    def test_only_open_controller_input_grows_and_returned_limits_are_detached(self):
        self.assertEqual(LIMITS, {'max_input_tokens':10000,'max_output_tokens':16384,'wall_seconds':600})
        caps = resources.role_limits()
        self.assertEqual(caps['controller'], dict(LIMITS,max_input_tokens=16000))
        self.assertEqual(caps['review'], LIMITS)
        self.assertEqual(caps['author'], {'max_input_tokens':24000,'max_output_tokens':49152,'wall_seconds':900})
        f = self.resources()
        self.assertEqual(resources.controller_ceiling(f.runtime,f.study()), caps['controller'])
        caps['controller']['max_input_tokens'] = 1
        self.assertEqual(resources.role_limits()['controller']['max_input_tokens'],16000)
        self.assertEqual(LIMITS['max_input_tokens'],10000)

    def test_controller_headroom_requires_original_open_grant_and_both_factories(self):
        f = self.resources(); study = f.study()
        self.assertIsNone(resources.controller_ceiling(f.runtime,{}))
        self.assertIsNone(resources.controller_ceiling(dict(f.runtime,schema='earnings_capacity_runtime_v1'),study))
        for axis in ('controller','author'):
            changed = deepcopy(f.runtime)
            changed['sources']['factory_'+axis] = engine.pin(resources.e.REPO/'tools/earnings_capacity_assembly.py')
            with self.subTest(axis=axis), self.assertRaises(ValueError): resources.controller_ceiling(changed,study)
        for key, value in (('source_commit','b'*40),('additional_cap_nano_usd',1),('cutoff_utc','2099-01-01T00:00:00Z')):
            with self.subTest(key=key), self.assertRaises(ValueError):
                resources.controller_ceiling(dict(f.runtime,**{key:value}),study)
        bad = deepcopy(f.runtime); bad['sources']['factory_controller']['sha256']='0'*64
        with self.assertRaises(ValueError): resources.controller_ceiling(bad,study)
        Path(study['new_live_grant']['path']).write_bytes(b'{}')
        with self.assertRaises(ValueError): resources.controller_ceiling(f.runtime,study)
        f = self.resources(); f.grant['schema']='earnings_real_rh_grant_v1'
        self.assertIsNone(resources.controller_ceiling(f.runtime,f.study()))

    def preflight(self):
        owner = runtime_fixture.CapacityRuntimeOwnerTests(); owner.setUp(); self.addCleanup(owner.doCleanups)
        f = owner.fixture('synthetic-headroom-preflight')
        value = deepcopy(f.spec); value['schema']='earnings_capacity_runtime_v2'
        value['limits']['controller'] = resources.role_limits()['controller']
        assembly = engine.pin(resources.e.REPO/'tools/earnings_open_assembly.py')
        value['sources'].update(factory_controller=assembly,factory_author=deepcopy(assembly),
            forecast_entry=engine.pin(runtime.e.__file__),forecaster=engine.pin(inspect.getsourcefile(runtime.e.forecast)))
        original = {'max_input_tokens':10000,'max_output_tokens':1024,'company_wall_seconds':60,
            'max_turns_per_company':3,'request_timeout_seconds':600,'models':{f.rates['api_model']:f.rates}}
        grant = {key:value[key] for key in ('id','root','source_commit','ledger','baseline','cutoff_utc','deadline_utc','additional_cap_nano_usd')}
        grant['schema']='earnings_open_grant_v1'
        study = {'schema':'earnings_coevolution_study_v1',
            'model':{'requested_model':'gpt-6.1-sol','serving_snapshot':'unknown','serving_snapshot_verified':False},
            'runtime_config':original,'prior_batch':engine.save(f.home/'prior.json',{'config':original}),
            'new_live_grant':engine.save(f.home/'grant.json',grant)}
        value['forecast_study']=engine.save(f.home/'study.json',study)
        return owner, f, value

    def test_actual_runtime_preflight_scopes_16000_to_exact_controller_factory(self):
        owner, f, value = self.preflight()
        bound = engine.save(f.home/'open-runtime.json',value)
        before = f.rows()
        self.assertEqual(runtime.preflight_runtime(bound),value)
        self.assertEqual(f.rows(),before); self.assertEqual(owner.created,[])
        for role in ('controller','author','review'):
            changed = deepcopy(value); changed['limits'][role]['max_input_tokens']={'controller':16001,'author':24001,'review':10001}[role]
            with self.subTest(role=role), self.assertRaises(ValueError):
                runtime.preflight_runtime(engine.save(f.home/(role+'-over.json'),changed))
        foreign = deepcopy(value)
        foreign['sources']['factory_controller']=engine.pin(runtime_fixture.__file__)
        with self.assertRaises(ValueError): runtime.preflight_runtime(engine.save(f.home/'foreign.json',foreign))
        self.assertEqual(f.rows(),before); f.client_factory.assert_not_called()

    def transport(self, count, history=0, *, legacy=False):
        self.number += 1
        f = transport_fixture._TransportFixture(self,self.root/str(self.number))
        f.rates['effort']='max'
        f.limits = deepcopy(LIMITS if legacy else resources.role_limits()['controller'])
        f.slots[-1]=str(f.root/'roles/controller-terminal')
        f.context.update(limits=f.limits,rates=f.rates)
        f.context_binding = engine.save(f.root/'headroom-context.json',f.context)
        def guard(loan):
            pending=f.budget.db.execute("SELECT id,model,reserved FROM requests WHERE status='reserved'").fetchall()
            self.assertEqual(pending,[] if loan is None else [loan])
        owned=runtime._OwnedHTTP(f.http,guard,{slot:f.limits for slot in f.slots},f.rates)
        f.factory.side_effect=lambda:owned
        broker=role_fixture.Broker()
        broker.handler=lambda name,args:{'public_observation':'invented-'+args['slot']}
        service=(generic.CapacityController(f.context_binding,budget=f.budget,client_factory=f.factory)
            if legacy else roles.OpenController(f.context_binding,budget=f.budget,client_factory=f.factory,
                                               broker=broker,max_turns=history+1))
        responses=[]
        if history:
            f.prompt['feedback']['terminal_invented_observation']={'score_out_of_5':1.5,'status':'COMPLETED_SCORED'}
            f.prompt['feedback_sha256']=digest(f.prompt['feedback'])
            f.prompt['parent_feedback_sha256']=f.prompt['feedback_sha256']
        for i in range(history):
            response=f.response(); response['output']=[{'type':'reasoning','id':f'invented-{i}','summary':[]},
                {'type':'function_call','call_id':f'public-{i}','name':'inspect_trace',
                 'arguments':json.dumps({'slot':str(i)})}]
            responses.append(response)
        responses.append(f.response(f.decision('continue')))
        for response in responses:
            response['usage'].update(input_tokens=count,total_tokens=count+7)
        generated=[]
        class Connection:
            def __init__(inner,host,timeout): self.assertEqual(host,'api.openai.com')
            def request(inner,method,endpoint,body,headers):
                self.assertEqual(method,'POST'); inner.endpoint=endpoint; inner.payload=json.loads(body)
                f.calls.append((endpoint,deepcopy(inner.payload)))
            def getresponse(inner):
                if inner.endpoint.endswith('input_tokens'): raw=transport_fixture._wire({'input_tokens':count})
                else:
                    generated.append(deepcopy(inner.payload)); raw=transport_fixture._wire(responses[len(generated)-1])
                return mock.Mock(status=200,getheader=mock.Mock(return_value='invented-headroom'),
                    read=mock.Mock(side_effect=lambda limit:raw[:limit]))
            def close(inner): pass
        f.fake_connection=lambda _:Connection
        return f,service,generated,broker

    def test_observed_counts_and_exact_16000_use_actual_count_reserve_send_settle(self):
        for count in (10130,13553,16000):
            f,service,generated,_=self.transport(count)
            f.invoke(f.response(),service=service)
            self.assertEqual([endpoint for endpoint,_ in f.calls],['/v1/responses/input_tokens','/v1/responses'])
            self.assertEqual(len(generated),1)
            reserved=f.budget.db.execute("SELECT reserved,status FROM requests WHERE id!='fixture-prior'").fetchall()
            ceiling=max(unit(f.rates[key]) for key in ('input','cached','write'))
            self.assertEqual(reserved,[(count*ceiling+16384*unit(f.rates['output']),'settled')])
            self.assertEqual(f.budget.summary()['unresolved_reserved_usd'],0)
            self.assertEqual(f.budget.db.execute('SELECT * FROM config').fetchall(),[(1,200_000_000_000,100_000_000_000,0)])
            self.assertEqual(f.budget.db.execute("SELECT reserved,charged,status FROM requests WHERE id='fixture-prior'").fetchone(),(10000,1000,'settled'))
            self.assertEqual(f.context['cutoff_monotonic'],f.cutoff)
            self.assertEqual(f.limits['wall_seconds'],600)
            self.assertEqual(generated[0]['max_output_tokens'],16384)
            self.assertEqual(generated[0]['reasoning'],{'effort':'max'})
            self.assertIs(generated[0]['store'],False)
            self.assertEqual(generated[0]['model'],'gpt-6.1-sol')
            captured=json.loads((Path(f.slots[0])/'01-request.json').read_bytes())['payload']
            self.assertEqual(captured,{k:v for k,v in generated[0].items() if k not in {'max_output_tokens','service_tier','store'}})

    def test_16001_and_generic_10130_fail_before_reservation_or_generation_once(self):
        for count,legacy in ((16001,False),(10130,True)):
            f,service,generated,_=self.transport(count,legacy=legacy)
            with self.assertRaises(RuntimeError): f.invoke(f.response(),service=service)
            self.assertEqual([endpoint for endpoint,_ in f.calls],['/v1/responses/input_tokens'])
            self.assertEqual(generated,[])
            self.assertEqual(f.budget.db.execute("SELECT COUNT(*) FROM requests WHERE id!='fixture-prior'").fetchone()[0],0)
            result=json.loads((Path(f.slots[0])/'result.json').read_bytes())
            self.assertEqual(result['status'],'FAILED_NO_RETRY'); self.assertIs(result['retry_allowed'],False)

    def test_seven_public_tool_turns_and_terminal_feedback_hash_remain_exact(self):
        f,service,generated,broker=self.transport(13553,7)
        packet=deepcopy(f.prompt)
        f.invoke(f.response(),service=service,prompt=packet,slot=2)
        self.assertEqual(len(generated),8); self.assertEqual(len(broker.calls),7)
        final=generated[-1]
        self.assertEqual(json.loads(final['input'][0]['content']),packet)
        self.assertEqual(packet['feedback_sha256'],digest(packet['feedback']))
        slot=Path(f.slots[2]); original_history=[deepcopy(final['input'][0])]
        for i in range(1,8):
            original_history.extend(json.loads((slot/f'{i:02d}-response.json').read_bytes())['output'])
            original_history.append(json.loads(next(slot.glob(f'{i:02d}-tool-*.json')).read_bytes()))
        self.assertEqual(final['input'],original_history)
        self.assertEqual([x['call_id'] for x in final['input'] if x.get('type')=='function_call'],[f'public-{i}' for i in range(7)])
        self.assertEqual([x['call_id'] for x in final['input'] if x.get('type')=='function_call_output'],[f'public-{i}' for i in range(7)])
        self.assertEqual([x['id'] for x in final['input'] if x.get('type')=='reasoning'],[f'invented-{i}' for i in range(7)])
        self.assertEqual(final['tool_choice'],'none')
        self.assertEqual(f.budget.db.execute("SELECT COUNT(*) FROM requests WHERE id!='fixture-prior' AND status='settled'").fetchone()[0],8)
        self.assertEqual(f.budget.summary()['unresolved_reserved_usd'],0)


if __name__=='__main__': unittest.main()
