"""Broker boundaries with invented files and inert compute/literature adapters."""
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock

from earnings_open_broker import ResearchBroker
from earnings_open_code import CandidateExecutionFailure,DockerRunner,encoded,start_marker
from earnings_http import save_bytes
import test_earnings_open_worker as fixture


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.ProgramWorkerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.runner=Mock();self.runner.run.return_value={'value':7,'receipt':{'synthetic':True}}
        self.literature=Mock();self.literature.dispatch.return_value={'retrieval_level':'METADATA_ABSTRACT'}
        self.broker=ResearchBroker(self.f.root/'broker',company=self.f.data.company,
            capacity=self.f.native.capacity,runner=self.runner,literature=self.literature,trace_slots={})

    def test_only_original_files_and_selected_program_sources(self):
        value=self.broker.dispatch('read_file',{'path':'filings/old.md','offset':0,'characters':2000})
        self.assertIn('100',value['value']['text'])
        source=self.broker.dispatch('read_current_program',{'axis':'R'})['value']['source_text']
        self.assertEqual(source,(self.f.native.source/'R0.py').read_text())
        for path in ('../qa.json','/tmp/secret','filings/hidden.md'):
            with self.assertRaises(ValueError):
                self.broker.dispatch('read_file',{'path':path,'offset':0,'characters':100})

    def test_dispatch_real_interfaces_and_preserve_exact_intent_result(self):
        self.broker.dispatch('search_literature',{'query':'method research','limit':2})
        self.literature.dispatch.assert_called_once_with('search_literature',{'query':'method research','limit':2})
        self.broker.dispatch('run_python',{'source':'def run(p): return p+1','payload_json':'6'})
        self.runner.run.assert_called_once_with('def run(p): return p+1',6)
        self.assertTrue((self.broker.root/'0002'/'intent.json').is_file())
        self.assertTrue((self.broker.root/'0002'/'result.json').is_file())

    def test_failed_action_is_retained_and_cannot_be_automatically_repeated(self):
        self.runner.run.side_effect=RuntimeError('synthetic failure')
        args={'source':'def run(p): raise ValueError()','payload_json':'{}'}
        with self.assertRaises(RuntimeError):self.broker.dispatch('run_python',args)
        with self.assertRaisesRegex(ValueError,'stays closed'):self.broker.dispatch('run_python',args)
        self.assertEqual(self.runner.run.call_count,1)
        self.assertTrue((self.broker.root/'0001'/'failure.json').is_file())

    def candidate_error(self,source,payload,change=None):
        # Invented immutable originals. Actual Docker recovery is tested below.
        self.runner.root=self.f.root/'mock-code';self.runner.root.mkdir()
        self.runner.blocked=False
        call=self.runner.root/('call-'+'a'*32);call.mkdir()
        sha=lambda x:hashlib.sha256(x).hexdigest()
        detail={'error_type':'NameError','message':'undefined public variable','source_line':1}
        request=encoded({'source':source,'payload':payload});out=encoded({'ok':False,'candidate_exception':detail})
        err=start_marker(sha(source.encode()))
        intent={'source_sha256':sha(source.encode()),'input_sha256':sha(request),
            'image':'synthetic','guest_sha256':'a'*64,'command':[],'docker':{},
            'timeout_seconds':20,'container_name':'synthetic','container_token':'a'*32,
            'retry_allowed':False,'start_command':[]}
        receipt={**intent,'status':'FAILED_NO_RETRY','failure_classification':'RECOVERABLE_GUEST_EXCEPTION',
            'execution_started':True,'cleanup_verified':True,'source_integrity_verified':True,
            'host_candidate_execution':False,'stdout_sha256':sha(out),'stderr_sha256':sha(err),
            'exit_code':2,'candidate_diagnostic':detail}
        if change:receipt.update(change)
        for name,value in [('input.json',request),('stdout.bin',out),('stderr.bin',err),
                ('intent.json',encoded(intent)),('result.json',encoded(receipt))]:save_bytes(call/name,value)
        return CandidateExecutionFailure({'path':str(call/'result.json'),'sha256':sha(encoded(receipt))})

    def test_verified_candidate_error_and_changed_code_not_same_action_retry(self):
        source='def run(p): return missing'
        error=self.candidate_error(source,{'x':1})
        self.runner.run.side_effect=[error,{'value':2,'receipt':{'synthetic':True}}]
        first=self.broker.dispatch('run_python',{'source':source,'payload_json':'{"x":1}'})
        self.assertEqual(first['error']['status'],'CANDIDATE_FAILED_NO_RETRY')
        self.assertFalse(first['error']['same_action_retry_allowed'])
        self.assertFalse((self.broker.root/'0001'/'result.json').exists())
        for text in ('{"x":1}','{ "x" : 1 }'):
            with self.assertRaises(ValueError):self.broker.dispatch('run_python',{'source':source,'payload_json':text})
        second=self.broker.dispatch('run_python',{'source':'def run(p): return p["x"]+1','payload_json':'{"x":1}'})
        self.assertEqual(second['value']['value'],2);self.assertEqual(self.runner.run.call_count,2)

    def test_typed_but_unverified_candidate_failure_is_fatal(self):
        source='def run(p): return missing'
        self.runner.run.side_effect=self.candidate_error(source,{},change={'cleanup_verified':False})
        with self.assertRaises(RuntimeError):self.broker.dispatch('run_python',{'source':source,'payload_json':'{}'})

    def test_tampered_intent_is_fatal(self):
        source='def run(p): return missing';error=self.candidate_error(source,{})
        intent=Path(error.receipt['path']).with_name('intent.json')
        intent.write_bytes(b'{}')
        self.runner.run.side_effect=error
        with self.assertRaises(RuntimeError):self.broker.dispatch('run_python',{'source':source,'payload_json':'{}'})

    def test_guest_exit_mismatch_stays_fatal(self):
        source='def run(p): return missing'
        self.runner.run.side_effect=self.candidate_error(source,{},change={'exit_code':0})
        with self.assertRaises(RuntimeError):self.broker.dispatch('run_python',{'source':source,'payload_json':'{}'})

    def test_guest_diagnostic_must_match_preserved_stdout(self):
        source='def run(p): return missing'
        self.runner.run.side_effect=self.candidate_error(source,{},change={'candidate_diagnostic':{
            'error_type':'NameError','message':'invented different message','source_line':1}})
        with self.assertRaises(RuntimeError):self.broker.dispatch('run_python',{'source':source,'payload_json':'{}'})

    @unittest.skipUnless(os.getenv('EARNINGS_OPEN_DOCKER_TESTS')=='1','Explicit actual Docker canary only')
    def test_actual_docker_failed_code_observation_then_new_code_result(self):
        self.broker.runner=DockerRunner(self.f.root/'actual-code')
        failed=self.broker.dispatch('run_python',{'source':'def run(p): return missing_public_name','payload_json':'1'})
        self.assertEqual(failed['error']['error_type'],'NameError')
        self.assertEqual(failed['error']['source_line'],1)
        saved=json.loads(Path(failed['research_receipt']['path']).read_bytes())
        receipt=json.loads(Path(saved['execution']['path']).read_bytes())
        self.assertTrue(receipt['cleanup_verified']);self.assertTrue(receipt['source_integrity_verified'])
        fixed=self.broker.dispatch('run_python',{'source':'def run(p): return p+1','payload_json':'1'})
        self.assertEqual(fixed['value']['value'],2)
        self.assertEqual(self.broker.runner.calls,2)

    def test_no_undeclared_tool_trace_host_path_or_schema_extensions(self):
        for name,args in [('read_current_program',{'axis':'K'}),('inspect_trace',{
            'label':'/tmp/qa','max_events':1,'max_output_chars':100}),('shell',{}),
            ('run_python',{'source':'x','payload_json':'{}','host_path':'/tmp'})]:
            with self.subTest(name=name),self.assertRaises(ValueError):self.broker.dispatch(name,args)
        self.runner.run.assert_not_called()


if __name__=='__main__':unittest.main()
