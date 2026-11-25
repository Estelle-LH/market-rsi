"""Original invented filing -> H-provided initial Author packet; all HTTP mocked."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import earnings_open_broker as broker_module
import earnings_open_context as context_module
import earnings_open_roles as roles
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_roles as role_fixture


class AuthorInitialEvidenceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='invented-initial-evidence-')
        self.addCleanup(temp.cleanup); self.root=Path(temp.name).resolve(); self.number=0
        self.body='PREFIX_界\n'+('| Period | Invented USD |\n| 2025 | (17) |\n'*400)+'REAL_FIXTURE_TAIL'
        self.files={'questions.md':'### T001 | Invented quantity',
            'filing_index.tsv':'date_filed\tform_type\taccession\tpath\n2026-01-01\t10-Q\told\tfilings/old.md\n',
            'filings/old.md':self.body}
        self.company={'visible_root':str(self.root/'visible'),'target_accession':'hidden',
            'cutoff':'2026-02-01','allowed_files':[]}
        for name,text in self.files.items():
            path=self.root/'visible'/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text)
            self.company['allowed_files'].append({'path':name,'bytes':len(text.encode()),
                'sha256':hashlib.sha256(text.encode()).hexdigest()})
        self.reference=self.root/'invented-reference.py'
        self.reference.write_text("PROGRAM={'axis':'R'}\ndef run(p): return {}\n")
        self.hint={'tool':'read_file','arguments':{'path':'filings/old.md','offset':9,'characters':10000}}
        self.base={'schema':'earnings_repair_context_v1','human_task':'Inspect this invented original table.',
            'prior_candidate':{'axis':'R','source':engine.pin(self.reference),'source_delivery':'paged_reference'},
            'observations':{'actual_original_read_locations':[self.hint]},
            'verification':['Check original units and periods.'],'non_claims':['Not a model-chosen read.']}
        self.runner,self.literature,self.capacity=mock.Mock(),mock.Mock(),mock.Mock()

    def broker(self, *, locations='default', no_context=False, context=None):
        self.number+=1; binding=None
        if not no_context:
            value=deepcopy(self.base if context is None else context)
            if locations!='default': value['observations']={'actual_original_read_locations':locations}
            binding=engine.save(self.root/f'context-{self.number}.json',value)
        return broker_module.ResearchBroker(self.root/f'broker-{self.number}',company=self.company,
            capacity=self.capacity,runner=self.runner,literature=self.literature,trace_slots={},research_context_binding=binding)

    def role(self,broker):
        fixture=role_fixture.OpenRoleTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        fixture.broker=broker
        chosen=fixture.choice('R')
        fixture.generations=[fixture.message({'decision_sha256':digest(chosen),
            'source_text':"PROGRAM={'axis':'R'}\ndef run(p): return {}\n",
            'test_text':"CASES=[{'input':{},'expected':{}}]"})]
        service=fixture.service(author=True,max_turns=1,
            limits={'max_input_tokens':10000,'max_output_tokens':32768,'wall_seconds':900})
        return fixture,service,chosen

    def test_empty_original_read_stops_before_Author_factory_retains_receipt_and_no_reread(self):
        hint=deepcopy(self.hint); hint['arguments']['offset']=len(self.body)+1
        broker=self.broker(locations=[hint]); f,service,chosen=self.role(broker)
        with mock.patch.object(roles,'pack',side_effect=lambda _c,request,*_a,**_k:deepcopy(request)),\
                mock.patch.object(roles,'budgeted_response',side_effect=f.fake_paid) as paid:
            with self.assertRaises(ValueError): service.author(chosen,{'axis':'R'},str(f.slot))
            paid.assert_not_called()
        f.factory.assert_not_called()
        saved=engine.read(engine.pin(broker.root/'0001/result.json'))
        self.assertEqual(saved['value']['text'],''); self.assertEqual(broker.files.calls,1)
        with self.assertRaises(ValueError): broker.research_context(include_source=True)
        self.assertEqual((broker.calls,broker.files.calls),(1,1))

    def test_first_declared_read_exact_body_offset_fullfile_sha_receipt_and_counters(self):
        second={'tool':'read_file','arguments':{'path':'filings/hidden.md','offset':0,'characters':100}}
        broker=self.broker(locations=[self.hint,second])
        actual=broker.research_context(include_source=True)['initial_original_evidence']
        expected={'path':'filings/old.md','offset':9,'total_characters':len(self.body),
            'text':self.body[9:10009],'next_offset':10009}
        self.assertEqual(actual['schema'],'earnings_author_initial_original_evidence_v1')
        self.assertEqual(actual['provided_by'],'harness_preparation_not_model_tool_choice')
        self.assertIs(actual['untrusted_evidence'],True)
        self.assertEqual(actual['request'],self.hint); self.assertEqual(actual['result']['value'],expected)
        self.assertEqual(actual['source_sha256'],hashlib.sha256(self.body.encode()).hexdigest())
        self.assertEqual(engine.read(actual['result']['research_receipt']),{'value':expected,'untrusted_evidence':True})
        self.assertEqual((broker.calls,broker.files.calls),(1,1))
        self.assertEqual(broker.files.returned,len(json.dumps(expected)))
        self.assertEqual(broker.returned,len(json.dumps(expected,allow_nan=False).encode()))
        intent=engine.read(engine.pin(broker.root/'0001/intent.json'))
        self.assertEqual(intent,{'name':'read_file','arguments':self.hint['arguments'],'retry_allowed':False})
        self.runner.run.assert_not_called(); self.literature.dispatch.assert_not_called(); self.capacity.resolve.assert_not_called()

    def test_cached_second_view_no_reread_and_defensive_copy(self):
        broker=self.broker(); first=broker.research_context(include_source=True)
        expected=deepcopy(first); counts=(broker.calls,broker.returned,broker.files.calls,broker.files.returned)
        first['initial_original_evidence']['result']['value']['text']='mutated returned view'
        first['initial_original_evidence']['request']['arguments']['offset']=0
        with mock.patch.object(broker,'dispatch',side_effect=AssertionError('Unexpected cached reread')):
            self.assertEqual(broker.research_context(include_source=True),expected)
        self.assertEqual((broker.calls,broker.returned,broker.files.calls,broker.files.returned),counts)

    def test_default_no_hint_and_Controller_views_do_not_seed_or_expand_tools(self):
        no_hint=deepcopy(self.base); no_hint['observations']=['No explicit location.']
        for broker in (self.broker(no_context=True),self.broker(context=no_hint),self.broker()):
            plain=broker.research_context()
            self.assertTrue(plain is None or 'initial_original_evidence' not in plain)
            self.assertEqual((broker.calls,broker.files.calls),(0,0))
        broker=self.broker(context=no_hint)
        self.assertNotIn('initial_original_evidence',broker.research_context(include_source=True))
        self.assertEqual((broker.calls,broker.files.calls),(0,0))
        self.assertEqual([tool['name'] for tool in broker.definitions],
            [tool['name'] for tool in broker_module.DEFINITIONS]+['read_reference_program'])

    def test_context_reference_cached_source_request_and_receipt_drift_fail_closed(self):
        for kind in ('context','reference','source','request','receipt'):
            broker=self.broker(); broker.research_context(include_source=True)
            if kind=='context': Path(broker.research_context_binding['path']).write_bytes(b'{}')
            elif kind=='reference': self.reference.write_text('# changed reference')
            elif kind=='source': broker.files.files['filings/old.md']+=' changed loaded source'
            elif kind=='request': broker._author_evidence_cache['request']['arguments']['offset']+=1
            else: Path(broker._author_evidence_cache['result']['research_receipt']['path']).write_bytes(b'{}')
            with self.subTest(kind=kind),self.assertRaises(ValueError): broker.research_context(include_source=True)
            self.assertEqual((broker.calls,broker.files.calls),(1,1))
            if kind=='reference': self.reference.write_text("PROGRAM={'axis':'R'}\ndef run(p): return {}\n")

    def test_failed_original_read_is_retained_and_never_automatically_retried(self):
        broker=self.broker()
        with mock.patch.object(broker.files,'dispatch',side_effect=RuntimeError('invented read failure')) as dispatch:
            with self.assertRaises(RuntimeError): broker.research_context(include_source=True)
            with self.assertRaisesRegex(ValueError,'failed once'): broker.research_context(include_source=True)
            dispatch.assert_called_once_with('read_file',self.hint['arguments'])
        self.assertEqual(broker.calls,1)
        self.assertEqual(engine.read(engine.pin(broker.root/'0001/failure.json')),
            {'error_type':'RuntimeError','retry_allowed':False})

    def test_invalid_hint_tool_hidden_path_extra_arguments_and_original_bounds_deny(self):
        variants=[{'tool':'calculate','arguments':{'expression':'1+1'}},
            {'tool':'read_file','arguments':{'path':'filings/hidden.md','offset':0,'characters':10}},
            {'tool':'read_file','arguments':{'path':'questions.md','offset':0,'characters':10}}]
        for update in ({'extra':True},{'offset':-1},{'offset':True},{'characters':0},
                {'characters':20001},{'characters':True},{'characters':'10000'}):
            variants.append({'tool':'read_file','arguments':dict(self.hint['arguments'],**update)})
        for hint in variants:
            broker=self.broker(locations=[hint])
            with self.subTest(hint=hint),self.assertRaises(ValueError): broker.research_context(include_source=True)
            self.assertLessEqual(broker.calls,1)
        self.runner.run.assert_not_called(); self.literature.dispatch.assert_not_called()

    def test_original_filing80_and_return2million_and_broker64_caps_unchanged(self):
        broker=self.broker(); broker.files.calls=79
        broker.research_context(include_source=True); self.assertEqual(broker.files.calls,80)
        broker.research_context(include_source=True); self.assertEqual(broker.files.calls,80)
        for field in ('filing_calls','filing_returned','broker_calls','broker_returned'):
            broker=self.broker()
            if field=='filing_calls': broker.files.calls=80
            elif field=='filing_returned': broker.files.returned=2_000_000
            elif field=='broker_calls': broker.calls=64
            else: broker.returned=2_000_000
            with self.subTest(field=field),self.assertRaises(ValueError): broker.research_context(include_source=True)
            before=(broker.calls,broker.files.calls,broker.returned,broker.files.returned)
            with self.assertRaises(ValueError): broker.research_context(include_source=True)
            self.assertEqual((broker.calls,broker.files.calls,broker.returned,broker.files.returned),before)

    def test_actual_mocked_Author_initial_effective_input_and_first_request_match_H_evidence(self):
        broker=self.broker(); f,service,chosen=self.role(broker)
        with mock.patch.object(roles,'pack',side_effect=lambda _c,request,*_a,**_k:deepcopy(request)),\
                mock.patch.object(roles,'budgeted_response',side_effect=f.fake_paid):
            service.author(chosen,{'axis':'R'},str(f.slot))
        effective=json.loads((f.slot/'effective-input.json').read_bytes())
        request=f.requests[0]; self.assertEqual(json.loads(request['input'][0]['content']),effective)
        evidence=effective['research_context']['initial_original_evidence']
        self.assertEqual(evidence,broker.research_context(include_source=True)['initial_original_evidence'])
        self.assertEqual(evidence['result']['value']['text'],self.body[9:10009])
        self.assertEqual(evidence['provided_by'],'harness_preparation_not_model_tool_choice')
        self.assertEqual(json.loads((f.slot/'result.json').read_bytes())['tool_calls'],0)
        self.assertEqual((broker.calls,broker.files.calls),(1,1))
        self.assertEqual(request['model'],'gpt-6.1-sol'); self.assertEqual(service.context['limits']['max_input_tokens'],10000)
        self.runner.run.assert_not_called(); self.literature.dispatch.assert_not_called(); self.capacity.resolve.assert_not_called()

    def test_initial_evidence_body_is_full_in_later_and_final_context_views(self):
        broker=self.broker(); initial={'role':'user','content':json.dumps({
            'research_context':broker.research_context(include_source=True)})}
        request={'tool_choice':'none','text':{'format':{'name':'earnings_open_author_v1',
            'schema':{'properties':{key:{} for key in ('decision_sha256','source_text','test_text')}}}},
            'input':[initial,{'type':'function_call','call_id':'later','name':'calculate','arguments':'{"expression":"1+1"}'},
                {'type':'function_call_output','call_id':'later','output':'{"value":2}'}]}
        projected,_=context_module.project(request,100)
        final,_=context_module.author_final_view(request,100,preserve_call_ids=context_module.author_preserved_outputs(request))
        self.assertEqual(projected['input'][0],initial); self.assertEqual(final['input'][0],initial)
        for view in (projected,final):
            body=json.loads(view['input'][0]['content'])['research_context']['initial_original_evidence']['result']['value']['text']
            self.assertEqual(body,self.body[9:10009])
        self.assertEqual((broker.calls,broker.files.calls),(1,1))


if __name__=='__main__': unittest.main()
