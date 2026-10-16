import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import earnings_open_code as code
from earnings_open_code import CandidateExecutionFailure, DockerRunner, canonical, encoded, start_marker


class _Pipe(io.BytesIO):
    read1 = io.BytesIO.read


class _Process:
    def __init__(self,stdout,stderr,exit_code):
        self.stdout,self.stderr = _Pipe(stdout),_Pipe(stderr)
        self.returncode,self.exit_code = None,exit_code

    def poll(self): return self.returncode

    def wait(self,timeout=None):
        if self.returncode is None: self.returncode=self.exit_code
        return self.returncode

    def terminate(self): self.returncode=-15

    def kill(self): self.returncode=-9


class _Selector:
    def __init__(self): self.items={}

    def __enter__(self): return self

    def __exit__(self,*args): return False

    def register(self,stream,event,data): self.items[stream]=Mock(fileobj=stream,data=data)

    def unregister(self,stream): self.items.pop(stream)

    def get_map(self): return self.items

    def select(self,timeout=None): return [(item,1) for item in list(self.items.values())]


class CandidateExceptionTests(unittest.TestCase):
    """Invented local lifecycle/receipts, not actual Docker evidence."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.source='def run(p): return absent_name\n'
        self.binding=Mock(cli='/synthetic/docker')
        self.binding.environment_dict.return_value={}
        self.binding.public_receipt.return_value={'synthetic':True}

    def exercise(self,body=None,*,marker=True,cleanup=True,exit_code=2,create=False,
                 guest_drift=False,client_drift=False,launch_error=None,tamper_file=None):
        if body is None:
            body=encoded({'ok':False,'candidate_exception':{'error_type':'NameError',
                'message':"name 'absent_name' is not defined",'source_line':1}})
        process=_Process(body,start_marker(hashlib.sha256(self.source.encode()).hexdigest()) if marker else b'',exit_code)
        control=Mock(return_value=Mock(returncode=1 if create else 0,stdout='synthetic-id',stderr=''))
        factory=Mock(side_effect=launch_error) if launch_error else Mock(return_value=process)
        runner=DockerRunner(self.root/'runner',binding=self.binding,control_run=control,process_factory=factory)
        checks=([False,False] if create else
                [False,True,False] if cleanup else [False,True,RuntimeError('unknown cleanup')])
        verify=Mock(side_effect=[None,RuntimeError('client drift')]) if client_drift else Mock()
        if tamper_file is not None:
            def tamper(binding,run):
                if runner.calls:
                    next(runner.root.glob('call-*/'+tamper_file)).write_bytes(b'fixture drift')
            verify=Mock(side_effect=tamper)
        with patch.object(code,'_verify_docker_client',verify),\
                patch.object(runner,'_remaining_container',side_effect=checks),\
                patch.object(code.selectors,'DefaultSelector',_Selector):
            if guest_drift:
                guest=code.GUEST.read_bytes()
                with patch.object(code,'GUEST',Mock(read_bytes=Mock(side_effect=[guest,b'drift']))):
                    with self.assertRaises(RuntimeError) as caught: runner.run(self.source,{})
            else:
                with self.assertRaises(KeyboardInterrupt if isinstance(launch_error,KeyboardInterrupt) else RuntimeError) as caught:
                    runner.run(self.source,{})
        receipt=json.loads(next(runner.root.glob('call-*/result.json')).read_bytes())
        return runner,caught.exception,receipt

    def test_only_started_clean_ordinary_exception_is_typed(self):
        runner,error,receipt=self.exercise()
        self.assertIs(type(error),CandidateExecutionFailure)
        self.assertEqual(receipt['failure_classification'],'RECOVERABLE_GUEST_EXCEPTION')
        self.assertEqual(receipt['candidate_diagnostic']['error_type'],'NameError')
        self.assertEqual(receipt['candidate_diagnostic']['source_line'],1)
        self.assertTrue(receipt['execution_started']);self.assertTrue(receipt['cleanup_verified'])
        self.assertTrue(receipt['source_integrity_verified']);self.assertFalse(runner.blocked)
        self.assertEqual(receipt['status'],'FAILED_NO_RETRY')
        self.assertEqual(hashlib.sha256(Path(error.receipt['path']).read_bytes()).hexdigest(),error.receipt['sha256'])

    def test_no_start_marker_is_fatal_even_with_valid_error_and_cleanup(self):
        _,error,receipt=self.exercise(marker=False)
        self.assertNotIsInstance(error,CandidateExecutionFailure)
        self.assertEqual(receipt['failure_classification'],'FATAL_EXECUTION_FAILURE')
        self.assertIsNone(receipt['candidate_diagnostic'])

    def test_unknown_cleanup_is_fatal_even_after_normal_guest_exception(self):
        runner,error,receipt=self.exercise(cleanup=False)
        self.assertTrue(runner.blocked);self.assertNotIsInstance(error,CandidateExecutionFailure)
        self.assertFalse(receipt['cleanup_verified'])

    def test_guest_source_drift_is_fatal_after_normal_guest_exception(self):
        runner,error,receipt=self.exercise(guest_drift=True)
        self.assertTrue(runner.blocked);self.assertNotIsInstance(error,CandidateExecutionFailure)
        self.assertFalse(receipt['source_integrity_verified'])

    def test_client_drift_is_fatal_after_normal_guest_exception(self):
        _,error,receipt=self.exercise(client_drift=True)
        self.assertNotIsInstance(error,CandidateExecutionFailure)
        self.assertFalse(receipt['source_integrity_verified'])

    def test_input_drift_is_fatal_after_normal_guest_exception(self):
        _,error,receipt=self.exercise(tamper_file='input.json')
        self.assertNotIsInstance(error,CandidateExecutionFailure)
        self.assertFalse(receipt['source_integrity_verified'])

    def test_intent_drift_is_fatal_after_normal_guest_exception(self):
        _,error,receipt=self.exercise(tamper_file='intent.json')
        self.assertNotIsInstance(error,CandidateExecutionFailure)
        self.assertFalse(receipt['source_integrity_verified'])

    def test_create_failure_is_fatal_without_candidate_execution(self):
        _,error,receipt=self.exercise(create=True)
        self.assertNotIsInstance(error,CandidateExecutionFailure)
        self.assertFalse(receipt['execution_started'])

    def test_host_process_error_is_fatal(self):
        _,error,receipt=self.exercise(launch_error=OSError('host failure never returned as guest diagnostic'))
        self.assertNotIsInstance(error,CandidateExecutionFailure)
        self.assertIsNone(receipt['candidate_diagnostic'])

    def test_host_interrupt_remains_interrupt_and_is_retained(self):
        _,error,receipt=self.exercise(launch_error=KeyboardInterrupt())
        self.assertIsInstance(error,KeyboardInterrupt)
        self.assertEqual(receipt['error_type'],'KeyboardInterrupt')
        self.assertFalse(receipt['execution_started'])

    def test_malformed_output_is_fatal_even_after_start(self):
        _,error,receipt=self.exercise(body=b'not JSON',exit_code=0)
        self.assertNotIsInstance(error,CandidateExecutionFailure)
        self.assertIsNone(receipt['candidate_diagnostic'])

    def test_output_limit_remains_fatal(self):
        _,error,receipt=self.exercise(body=b'x'*(code.MAX_RESULT_BYTES+2),exit_code=0)
        self.assertNotIsInstance(error,CandidateExecutionFailure)
        self.assertLessEqual(next((self.root/'runner').glob('call-*/stdout.bin')).stat().st_size,code.MAX_RESULT_BYTES+1)
        self.assertIsNone(receipt['candidate_diagnostic'])

    def test_local_timeout_remains_fatal(self):
        with patch.object(code.time,'monotonic',side_effect=[100,100.1,200,201]):
            _,error,receipt=self.exercise(body=b'x'*8192,exit_code=0)
        self.assertNotIsInstance(error,CandidateExecutionFailure)
        self.assertEqual(receipt['error_type'],'TimeoutError')

    def test_guest_control_exception_is_not_reclassified(self):
        body=encoded({'ok':False,'candidate_exception':{'error_type':'KeyboardInterrupt','message':'','source_line':1}})
        _,error,receipt=self.exercise(body=body)
        self.assertNotIsInstance(error,CandidateExecutionFailure)
        self.assertIsNone(receipt['candidate_diagnostic'])


class CodeBoundaryTests(unittest.TestCase):
    def test_canonical_refuses_relative_and_alias(self):
        with self.assertRaises(ValueError):
            canonical(Path('relative'))
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            alias = root/'alias'
            alias.symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError):
                canonical(alias)

    def test_input_limits_before_docker(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            with patch('earnings_open_code.freeze_docker_client', return_value=object()):
                runner = DockerRunner(root/'run')
            for source, value in [('', {}), ('x'*65_537, {}), ('def run(x): return x', float('nan')),
                                  ('def run(x): return x', 'x'*2_200_000)]:
                with self.assertRaises(ValueError):
                    runner.run(source, value)
            self.assertEqual(runner.calls, 0)

    def test_owned_root_consumed_and_bounds(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            with self.assertRaises(FileExistsError):
                DockerRunner(root)
            for options in ({'max_calls':0}, {'max_calls':True}, {'timeout_seconds':31}):
                with self.assertRaises(ValueError):
                    DockerRunner(root/'invalid', **options)

    def test_finite_encoding(self):
        self.assertEqual(json.loads(encoded({'x': 2})), {'x': 2})
        with self.assertRaises(ValueError):
            encoded({'x': float('inf')})


@unittest.skipUnless(os.environ.get('EARNINGS_OPEN_DOCKER_TESTS') == '1', 'Explicit actual Docker canary only')
class ActualDockerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.runner = DockerRunner(self.root/'runner')

    def tearDown(self):
        self.temp.cleanup()

    def test_actual_new_algorithm_and_isolation(self):
        source = ('import math, os, socket\n'
                  'def helper(xs): return math.fsum(xs)/len(xs)\n'
                  'def run(p):\n'
                  '    try:\n'
                  '        socket.create_connection(("1.1.1.1",443),timeout=.2)\n'
                  '        network=True\n'
                  '    except OSError: network=False\n'
                  '    return {"mean":helper(p), "uid":os.getuid(), "network":network, '
                  '"key":os.environ.get("OPENAI_API_KEY"), "host":os.path.exists("/Users/estelle")}\n')
        result = self.runner.run(source, [2,4,9])
        self.assertEqual(result['value'], {'mean':5.0, 'uid':65534, 'network':False, 'key':None, 'host':False})
        receipt = json.loads(Path(result['receipt']['path']).read_bytes())
        self.assertEqual(receipt['source_sha256'], hashlib.sha256(source.encode()).hexdigest())
        self.assertTrue(receipt['cleanup_verified'])
        self.assertNotIn('--mount', receipt['command'])

    def test_failed_source_retained_and_no_retry(self):
        with self.assertRaises(RuntimeError):
            self.runner.run('def run(p): raise ValueError("bad")', {})
        attempts = list((self.root/'runner').iterdir())
        self.assertEqual(len(attempts), 1)
        receipt = json.loads((attempts[0]/'result.json').read_bytes())
        self.assertEqual(receipt['status'], 'FAILED_NO_RETRY')
        self.assertTrue(receipt['cleanup_verified'])

    def test_ordinary_name_error_then_explicitly_different_good_code(self):
        broken='def run(p): return misspelled_variable\n'
        corrected='def run(p): return sum(p["values"])/len(p["values"])\n'
        payload={'values':[2,4,9]}
        with self.assertRaises(CandidateExecutionFailure) as caught:
            self.runner.run(broken,payload)
        failed_path=Path(caught.exception.receipt['path'])
        failed_bytes=failed_path.read_bytes()
        failed=json.loads(failed_bytes)
        self.assertEqual(failed['candidate_diagnostic']['error_type'],'NameError')
        self.assertEqual(failed['failure_classification'],'RECOVERABLE_GUEST_EXCEPTION')
        self.assertTrue(failed['execution_started']);self.assertTrue(failed['cleanup_verified'])
        self.assertNotEqual(hashlib.sha256(broken.encode()).hexdigest(),hashlib.sha256(corrected.encode()).hexdigest())
        self.assertEqual(self.runner.run(corrected,payload)['value'],5.0)
        self.assertEqual(failed_path.read_bytes(),failed_bytes)
        self.assertEqual(self.runner.calls,2)
        self.assertEqual(len(list(self.runner.root.glob('call-*'))),2)
        # Explicit scripted different action; not model autonomy or same-code retry.

    def test_flood_bounded(self):
        with self.assertRaises(RuntimeError):
            self.runner.run('import os\ndef run(p):\n    while True: os.write(1,b"x"*8192)', {})
        call = next((self.root/'runner').iterdir())
        self.assertLessEqual((call/'stdout.bin').stat().st_size, code.MAX_RESULT_BYTES+1)
        self.assertTrue(json.loads((call/'result.json').read_bytes())['cleanup_verified'])

    def test_timeout_owned_cleanup(self):
        self.runner.timeout = .8
        with self.assertRaises(RuntimeError):
            self.runner.run('def run(p):\n    while True: pass', {})
        call = next((self.root/'runner').iterdir())
        receipt = json.loads((call/'result.json').read_bytes())
        self.assertEqual(receipt['error_type'], 'TimeoutError')
        self.assertTrue(receipt['cleanup_verified'])


if __name__ == '__main__':
    unittest.main()
