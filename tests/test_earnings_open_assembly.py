"""Full real engine/owner/scorer with invented admission, HTTP and code outputs.

This proves wiring, not actual provider authorship or Docker correctness. Those
boundaries have separate focused tests. Never accesses the production ledger.
"""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import earnings_open_admission as admission
import earnings_open_assembly as assembly
import earnings_open_task as task_module
from earnings_research_state import ResearchState
from earnings_open_admission import slots
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from test_earnings_capacity_assembly import AssemblyFixture
from test_earnings_open_worker import ReceiptFixtureRunner


class OpenAssemblyTests(unittest.TestCase):
    def fixture(self):
        f=AssemblyFixture(self)
        f.copy('researcher_v1.py',admission.e.REPO/'configs/earnings_coevolution/program_R0.py')
        f.copy('harness_v1.py',admission.e.REPO/'configs/earnings_coevolution/program_H0.py')
        component=lambda axis,name:{'sources':{name:f.copies[name]},
            'configuration_sha256':f.native['baseline']['components'][axis]['configuration_sha256']}
        f.rebuild_baseline(researcher=component('R','researcher_v1.py'),harness=component('H','harness_v1.py'))
        f.native['micro_config']['pair']=engine.activation.pair(f.native['baseline'])
        f.envelope.update(schema=admission.SCHEMA,mode='real_provider',window={
            k:f.runtime[k] for k in ('cutoff_utc','deadline_utc')})
        runtime_source=f.save('runtime-source',f.raw.runtime)
        grant={k:f.runtime[k] for k in ('id','root','source_commit','ledger','baseline','cutoff_utc','deadline_utc','additional_cap_nano_usd')}
        grant.update(runtime=runtime_source,sources=f.envelope['sources'])
        f.envelope['grant']=f.save('invented-admission-only',grant)
        f.runtime['sources'].update({'factory_'+role:engine.pin(assembly.__file__)
            for role in ('controller','author','review','forecast')})
        f.seal()
        f.runtime['slots']=slots(f.envelope,f.plan)
        f.runtime_binding=f.save('open-runtime',f.runtime)
        f.native['micro_config']['fixed_context']['resource_policy_sha256']=digest(f.runtime_binding)
        policy=f.save('open-policy',{'schema':'edgar_foreground_slow_call_policy_v1',
            'source_commit':f.runtime['source_commit'],'original_runtime_request_timeout_seconds':f.raw.runtime['request_timeout_seconds'],
            'effective_socket_timeout_seconds':600,'role_and_global_deadlines_unchanged':True,'retry_allowed':False})
        f.assembly.update(schema='earnings_open_assembly_v1',runtime=f.runtime_binding,
            native=f.save('open-native',f.native),constructors=assembly.constructors(),
            transport=engine.source_of(f.client_factory),transport_policy=policy,
            independent_review=f.save('invented-independent-review-only',{'verdict':'PASS_FOR_BOUNDED_OPEN_RESEARCH',
                'blocking_findings':[],'reviewed_sources':f.envelope['sources'],'reviewer':'explicit-fixture-not-real-review',
                'episode':f.episode_binding}))
        f.assembly.pop('mode')
        review=engine.read(f.assembly['independent_review'])
        review['reviewed_configuration_sha256']=digest({k:v for k,v in f.assembly.items() if k!='independent_review'})
        f.assembly['independent_review']=f.save('configuration-bound-fixture-review',review)
        f.assembly_binding=f.save('open-assembly',f.assembly)
        return f

    @contextmanager
    def scope(self,f):
        def invented_admission(envelope):
            if envelope!=f.envelope:raise ValueError('Only exact invented task admitted')
            return f.raw.company,ResearchState(f.raw.company,envelope['id'])
        with ExitStack() as stack:
            stack.enter_context(f.scope())
            # Admission/grants are explicitly invented in this fixture. Keep
            # production Python source identity checks, but do not require a
            # private historical human-authority JSON to test mocked wiring.
            public_sources = [name for name in task_module.sources() if name.endswith('.py')]
            stack.enter_context(patch.object(task_module, 'sources', return_value=public_sources))
            for module in (admission,assembly,task_module):
                stack.enter_context(patch.object(module,'admit',side_effect=invented_admission))
            stack.enter_context(patch.object(assembly,'provider_client',f.client_factory))
            stack.enter_context(patch.object(assembly,'DockerRunner',side_effect=lambda root,**_:ReceiptFixtureRunner(root)))
            yield

    def message(self,f,value):
        return f.raw.response([{'type':'message','role':'assistant','content':[{'type':'output_text','text':json.dumps(value)}]}])

    def choose(self,f,axis):
        def reply(payload):
            prompt=json.loads(payload['input'][0]['content'])
            return self.message(f,{'schema':'earnings_capacity_decision_v1','axis':axis,
                'component':'none' if axis=='continue' else 'tool_interface',
                'parent_pair_sha256':prompt['parent_pair_sha256'],'feedback_sha256':prompt['feedback_sha256'],
                'hypothesis':'Explicit invented response exercises wiring, not autonomous research',
                'expected_effect':'Keep parent' if axis=='continue' else
                    'earnings-shadow-v1|tool_interface|tool_return_characters|lower|1|score_nonregression|matched_trial_only'})
        return reply

    def author(self,f,payload):
        prompt=json.loads(payload['input'][0]['content'])
        definition={'name':'extract_numbers','description':'Sum signed historical values in a supplied file',
            'parameters':{'type':'object','properties':{'path':{'type':'string'}},'required':['path'],'additionalProperties':False}}
        source='PROGRAM='+repr({'axis':'H','tools':[definition]})+'\nimport re\ndef run(p):\n    return {"value":sum(float(x) for x in re.findall(r"-?\\d+", p["files"][p["arguments"]["path"]]))}\n'
        return self.message(f,{'decision_sha256':prompt['decision_sha256'],'source_text':source,
            'test_text':"CASES=[{'input':{'tool':'extract_numbers','arguments':{'path':'filings/test.md'},'files':{'filings/test.md':'100 -5'}},'expected':{'value':95}}]"})

    def research(self,f,payload):
        reply=f.raw.research()
        if 'extract_numbers' in {t['name'] for t in payload['tools']}:
            reply['output'][1].update(name='extract_numbers',arguments=json.dumps({'path':'filings/old.md'}))
        return reply

    def test_complete_open_continue_delivers_actual_final_feedback_to_next_controller(self):
        f=self.fixture()
        inspect=f.raw.response([{'type':'function_call','call_id':'outer-inspect','name':'inspect_trace',
            'arguments':json.dumps({'label':'forecast-01','max_events':3,'max_output_chars':300,'offset':0})}])
        sequence=[f.raw.research(),f.raw.final(),inspect,self.choose(f,'continue'),f.raw.research(),f.raw.final(),self.choose(f,'continue')]
        with self.scope(f),f.exchange(sequence):
            result=engine.read(assembly.run(f.episode_binding,f.assembly_binding))
        self.assertEqual(result['outcome']['completed_rounds'],2)
        terminal=engine.read(result['next_actual_controller'])
        packet=engine.read(terminal['packet'])
        self.assertEqual(packet['feedback'],result['outcome']['result']['feedback'])
        self.assertEqual(packet['feedback_sha256'],digest(result['outcome']['result']))
        self.assertFalse(terminal['applied'])
        self.assertTrue(all(row[4]=='settled' for row in f.ledger_rows()))
        self.assertEqual(len(f.raw.calls),14)
        action=engine.read(engine.pin(f.root/'research-actions'/'0001'/'intent.json'))
        self.assertEqual(action['name'],'inspect_trace')

    def test_H_program_native_adoption_is_executed_by_new_ordinary_worker(self):
        f=self.fixture()
        sequence=[f.raw.research(),f.raw.final(),self.choose(f,'H'),lambda p:self.author(f,p),
            lambda p:self.research(f,p),f.raw.final(),lambda p:self.research(f,p),f.raw.final(),
            lambda p:self.research(f,p),f.raw.final(),self.choose(f,'continue')]
        with self.scope(f),f.exchange(sequence):
            result=engine.read(assembly.run(f.episode_binding,f.assembly_binding))
        state=engine.read(engine.pin(f.paths['batch_root']/'batch.json'))
        self.assertEqual(state['micro_evolution']['history'][0]['review']['decision'],'accept')
        self.assertEqual(len(state['capacity_work']),4)
        next_slot=Path(f.slots[1]['forecast'])
        executions=engine.read(engine.pin(next_slot/'program-executions.json'))
        self.assertEqual(len(executions['H']),1)
        self.assertEqual(executions['H'][0]['input']['tool'],'extract_numbers')
        self.assertEqual(result['outcome']['result']['feedback']['research_diagnostics']['review']['verdict'],'accept')
        self.assertTrue(all(row[4]=='settled' for row in f.ledger_rows()))


if __name__=='__main__':unittest.main()
