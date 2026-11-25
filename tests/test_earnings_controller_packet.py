"""Synthetic first-packet composition and stock temporary-ledger transport.

No candidate source is executed; synthetic receipts are explicitly marked.
Invented count replies test enforcement, not measured tokenizer fit.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import earnings_capacity_runtime as runtime
import earnings_open_broker as broker_module
import earnings_open_roles as roles
import earnings_open_task as task_module
from earnings_open_code import encoded
from earnings_open_program import program
from edgar_forecast_tools import FilingTools
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_capacity_controller_transport as transport_fixture
import test_earnings_research_state as state_fixture


class SyntheticRunner:
    """Original-format synthetic files, never import/exec/compile supplied code."""
    def __init__(self, root, guidance, evidence=False):
        self.root,self.guidance,self.evidence,self.calls=root,guidance,evidence,[]

    def run(self, source, payload):
        self.calls.append({'source':source,'payload':deepcopy(payload)})
        value = ({'research_requests':[{'tool':'read_file','arguments':{
            'path':'filings/old.md','offset':0,'characters':2000}}]}
            if self.evidence and 'research_observations' not in payload else deepcopy(self.guidance))
        home=self.root/str(len(self.calls)); home.mkdir(parents=True)
        request=encoded({'source':source,'payload':payload}); stdout=encoded({'ok':True,'value':value})
        for name, raw in [('input.json',request),('stdout.bin',stdout),('stderr.bin',b''),
                          ('intent.json',encoded({'synthetic':True})),('create.stdout',b''),('create.stderr',b'')]:
            (home/name).write_bytes(raw)
        sha=lambda raw:hashlib.sha256(raw).hexdigest()
        receipt=engine.save(home/'result.json',{'synthetic':True,'status':'COMPLETED',
            'cleanup_verified':True,'host_candidate_execution':False,'exit_code':0,
            'source_sha256':sha(source.encode()),'input_sha256':sha(request),
            'stdout_sha256':sha(stdout),'stderr_sha256':sha(b'')})
        return {'value':value,'receipt':receipt,'fixture_metadata':{'value':'retain-nested-execution-value'}}


class ControllerPacketTests(unittest.TestCase):
    def setUp(self):
        self.data=state_fixture.ResearchStateTests(); self.data.setUp(); self.addCleanup(self.data.doCleanups)
        self.root=self.data.root
        self.sources={}
        for axis,meta in (('R',{'axis':'R'}),('H',{'axis':'H','tools':[]})):
            prefix='PROGRAM = '+repr(meta)+"\ndef run(payload): return {}\n# μ "+axis+' '
            source=prefix+'x'*(65000-len(prefix.encode('utf-8')))
            self.assertEqual(len(source.encode('utf-8')),65000)
            self.assertEqual(program(source.encode('utf-8'),axis),meta)  # Static literal/AST validation only.
            self.sources[axis]=source
        self.bindings={}
        for axis,source in self.sources.items():
            path=self.root/(axis+'.py'); path.write_bytes(source.encode()); self.bindings[axis]=engine.pin(path)
        self.active_pair={'researcher_sha256':'a'*64,'harness_sha256':'b'*64}
        self.capacity=mock.Mock()
        self.capacity.batch.snapshot.return_value={'micro_evolution':{'active_pair':self.active_pair}}
        def resolve(axis,*,expected_pair_sha256):
            self.assertEqual(expected_pair_sha256,digest(self.active_pair))
            return {'receipt':{'source':deepcopy(self.bindings[axis])}}
        self.capacity.resolve.side_effect=resolve
        self.guidance={'public_marker':'EXACT_SINGLE_GUIDANCE_SENTINEL','text':'g'*12000,
                       'value':{'preserve_nested_guidance':True}}
        self.runner=SyntheticRunner(self.root/'runner',self.guidance)
        self.broker=broker_module.ResearchBroker(self.root/'broker',company=self.data.company,
            capacity=self.capacity,runner=self.runner,literature=mock.Mock(),trace_slots={})
        self.feedback={'observation':{'status':'COMPLETED_SCORED','score_out_of_5':1.5},
                       'nested_evidence':{'value':{'preserve_feedback':True}},
                       'target_scores':[{'target_id':'T001','points_awarded':0.5}]}
        self.ctx={'previous_result':{'state':{'synthetic_state_binding':True},'feedback':self.feedback},
                  'previous_feedback_sha256':digest(self.feedback)}
        self.profiles={'R':{'axis':'R'},'H':{'axis':'H','tools':[]}}

    def descriptors(self):
        return {axis:{'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
            'source_utf8_bytes':65000,'read_tool':'read_current_program','arguments':{'axis':axis}}
            for axis,source in self.sources.items()}

    def packet(self, broker=None):
        task=task_module.OpenTask()
        task.company=self.data.company
        task.capacity,task.runner,task.broker=self.capacity,self.runner,broker or self.broker
        task.state_api=SimpleNamespace(tools=FilingTools(self.data.company))
        task.load_state=mock.Mock(return_value={'records':[]})
        return task.packet({'id':'invented-initial-controller'},deepcopy(self.ctx),
                           deepcopy(self.profiles),digest(self.active_pair))

    def test_near_64k_sources_get_exact_utf8_descriptors_and_readable_hashes(self):
        self.assertEqual(self.broker.current_programs(),self.descriptors())
        self.assertLess(len(self.sources['R']),65000)  # Byte count, not character count.
        for axis in ('R','H'):
            reference=self.broker.current_programs()[axis]
            result=self.broker.dispatch(reference['read_tool'],reference['arguments'])
            value=result['value']
            self.assertEqual(value['source_text'],self.sources[axis])
            self.assertEqual(value['source_sha256'],reference['source_sha256'])
            self.assertEqual(value['source_utf8_bytes'],65000)
            self.assertEqual(value['axis'],axis)
            self.assertEqual(engine.read(result['research_receipt'])['value'],value)
        self.assertEqual(self.runner.calls,[])

    def test_initial_packet_has_one_exact_guidance_and_preserves_all_identities(self):
        original_ctx,original_profiles=deepcopy(self.ctx),deepcopy(self.profiles)
        packet=self.packet()
        self.assertEqual(packet['program_sources'],self.descriptors())
        for key in ('feedback_sha256','parent_feedback_sha256'):
            self.assertEqual(packet[key],digest(self.feedback))
        self.assertEqual(packet['parent_pair_sha256'],digest(self.active_pair))
        self.assertEqual(packet['feedback'],self.feedback)
        self.assertEqual(packet['profiles'],self.profiles)
        self.assertEqual(packet['questions'],self.data.files['questions.md'])
        self.assertEqual(packet['researcher_guidance'],self.guidance)
        self.assertNotIn('value',packet['guidance_execution'])
        self.assertEqual(packet['guidance_execution']['value_sha256'],digest(self.guidance))
        self.assertEqual(packet['guidance_execution']['fixture_metadata']['value'],'retain-nested-execution-value')
        serialized=json.dumps(packet,ensure_ascii=False)
        self.assertEqual(serialized.count('EXACT_SINGLE_GUIDANCE_SENTINEL'),1)
        for source in self.sources.values(): self.assertNotIn(source,serialized)
        self.assertEqual(self.ctx,original_ctx); self.assertEqual(self.profiles,original_profiles)
        self.assertEqual(len(self.runner.calls),1)
        self.assertEqual(self.runner.calls[0]['source'],self.sources['R'])
        origin=Path(packet['guidance_execution']['receipt']['path']).parent
        self.assertEqual(json.loads((origin/'input.json').read_bytes())['source'],self.sources['R'])
        self.assertEqual(json.loads((origin/'stdout.bin').read_bytes())['value'],self.guidance)
        self.assertEqual(engine.read(packet['guidance_execution']['receipt'])['source_sha256'],self.bindings['R']['sha256'])

    def test_evidence_phase_keeps_original_request_execution_and_nested_values(self):
        self.runner.evidence=True
        packet=self.packet(); execution=packet['guidance_execution']
        self.assertEqual(len(self.runner.calls),2)
        self.assertEqual(execution['request_execution']['value']['research_requests'],[
            {'tool':'read_file','arguments':{'path':'filings/old.md','offset':0,'characters':2000}}])
        self.assertEqual(execution['research_observation_count'],1)
        self.assertNotIn('research_observations',execution)
        self.assertEqual(execution['value_sha256'],digest(packet['researcher_guidance']))
        for original in (execution['request_execution'],execution):
            self.assertTrue(Path(original['receipt']['path']).is_file())
            self.assertEqual(original['fixture_metadata']['value'],'retain-nested-execution-value')
        self.assertEqual(packet['researcher_guidance']['value'],{'preserve_nested_guidance':True})

    def test_legacy_broker_without_current_programs_gets_same_descriptor_packet(self):
        legacy=SimpleNamespace(files=self.broker.files,current_sources=self.broker.current_sources,
                               available_traces=lambda:[])
        packet=self.packet(legacy)
        self.assertEqual(packet['program_sources'],self.descriptors())
        self.assertEqual(packet['researcher_guidance'],self.guidance)
        self.assertEqual(packet['guidance_execution']['value_sha256'],digest(self.guidance))

    def test_bound_selected_source_drift_rejected_before_execution_or_source_delivery(self):
        Path(self.bindings['R']['path']).write_bytes(b'changed invented source')
        with self.assertRaises(ValueError): self.broker.current_programs()
        with self.assertRaises(ValueError): self.broker.dispatch('read_current_program',{'axis':'R'})
        with self.assertRaises(ValueError): self.packet()
        self.assertEqual(self.runner.calls,[])

    def test_descriptor_helper_refuses_unknown_missing_nontext_and_oversized_sources(self):
        for value in ({'R':self.sources['R']},dict(self.sources,K='x'),dict(self.sources,R=None),
                      dict(self.sources,R=''),dict(self.sources,R='x'*65537)):
            with self.subTest(value_type=type(value)),self.assertRaises(ValueError):
                broker_module.program_references(value)

    def test_view_refuses_mismatched_guidance_including_python_bool_numeric_equality(self):
        packet=self.packet()
        raw=deepcopy(packet); raw['program_sources']=deepcopy(self.sources)
        raw['guidance_execution'].pop('value_sha256')
        for guidance,duplicate in (({'value':1},{'value':2}),({'value':1},{'value':True})):
            changed=deepcopy(raw); changed['researcher_guidance']=guidance
            changed['guidance_execution']['value']=duplicate; original=deepcopy(changed)
            with self.subTest(guidance=guidance,duplicate=duplicate),self.assertRaises(ValueError):
                task_module.controller_packet_view(changed)
            self.assertEqual(changed,original)

    def test_first_zero_tool_output_request_uses_stock_count_reserve_send_settle(self):
        packet=self.packet()
        f=transport_fixture._TransportFixture(self,self.root/'temporary-accounting')
        f.prompt=deepcopy(packet); f.rates['effort']='max'
        f.limits={'max_input_tokens':16000,'max_output_tokens':16384,'wall_seconds':600}
        f.context.update(limits=f.limits,rates=f.rates)
        f.context_binding=engine.save(f.root/'packet-context.json',f.context)
        def check(loan):
            rows=f.budget.db.execute("SELECT id,model,reserved FROM requests WHERE status='reserved'").fetchall()
            self.assertEqual(rows,[] if loan is None else [loan])
        owned=runtime._OwnedHTTP(f.http,check,{slot:f.limits for slot in f.slots},f.rates)
        f.factory.side_effect=lambda:owned
        service=roles.OpenController(f.context_binding,budget=f.budget,client_factory=f.factory,
                                     broker=self.broker,max_turns=1)
        f.count_raw=transport_fixture._wire({'input_tokens':15000})  # Synthetic count, not tokenizer evidence.
        response=f.response(f.decision('continue'))
        response['usage'].update(input_tokens=15000,total_tokens=15007)
        f.invoke(response,prompt=packet,service=service)
        self.assertEqual([endpoint for endpoint,_ in f.calls],['/v1/responses/input_tokens','/v1/responses'])
        counted,physical=f.calls[0][1],f.calls[1][1]
        self.assertEqual(counted,{k:v for k,v in physical.items() if k not in {'max_output_tokens','service_tier','store'}})
        self.assertEqual(len(physical['input']),1)
        self.assertFalse(any(item.get('type')=='function_call_output' for item in physical['input']))
        self.assertEqual(json.loads(physical['input'][0]['content']),packet)
        self.assertEqual(physical['input'][0]['content'].count('EXACT_SINGLE_GUIDANCE_SENTINEL'),1)
        for source in self.sources.values(): self.assertNotIn(source,physical['input'][0]['content'])
        self.assertEqual(f.budget.db.execute("SELECT status FROM requests WHERE id!='fixture-prior'").fetchall(),[('settled',)])
        self.assertEqual(f.budget.summary()['unresolved_reserved_usd'],0)
        reserved=json.loads((Path(f.slots[0])/'01-request.json').read_bytes())['payload']
        self.assertEqual(reserved,counted)


if __name__=='__main__': unittest.main()
