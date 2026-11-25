"""Authorized result-cap contract; all Docker programs below are newly invented."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

import earnings_open_broker as broker
import earnings_open_code as code
import earnings_open_guest as guest
import earnings_open_roles as roles


class OutputCapacityTests(unittest.TestCase):
    def test_one_shared_integer_constant_and_unchanged_source_bound(self):
        self.assertIs(type(guest.MAX_RESULT_BYTES), int)
        self.assertEqual(guest.MAX_RESULT_BYTES, 131072)
        for consumer in (code, broker, roles):
            self.assertEqual(consumer.MAX_RESULT_BYTES, guest.MAX_RESULT_BYTES)
        with tempfile.TemporaryDirectory() as name:
            # Input-size validation precedes Docker-client verification.
            runner = code.DockerRunner(Path(name).resolve()/'runner', binding=object())
            with self.assertRaises(ValueError): runner.run('x'*65537, {})
            self.assertEqual(runner.calls, 0)


@unittest.skipUnless(os.environ.get('EARNINGS_OPEN_DOCKER_TESTS')=='1',
                     'Explicit restricted Docker integration only')
class ActualOutputCapacityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = "def run(p):\n    return 'x' * p\n"

    def test_seventy_k_and_exact_serialized_boundary_complete_with_cleanup(self):
        runner = code.DockerRunner(self.root/'runner', max_calls=2)
        overhead = len(json.dumps({'ok':True,'value':''}, allow_nan=False).encode())
        for size in (70000, guest.MAX_RESULT_BYTES-overhead):
            result = runner.run(self.source, size)
            self.assertEqual(result['value'], 'x'*size)
            receipt_path = Path(result['receipt']['path'])
            receipt = json.loads(receipt_path.read_bytes())
            output = (receipt_path.parent/'stdout.bin').read_bytes()
            self.assertGreater(len(output), 65536)
            self.assertEqual(len(output), overhead+size+1)  # print newline is not result JSON.
            self.assertLessEqual(len(output), guest.MAX_RESULT_BYTES+1)
            self.assertEqual(hashlib.sha256(receipt_path.read_bytes()).hexdigest(), result['receipt']['sha256'])
            self.assertEqual(receipt['status'], 'COMPLETED')
            self.assertTrue(receipt['cleanup_verified']); self.assertTrue(receipt['source_integrity_verified'])
            self.assertTrue(receipt['execution_started']); self.assertIs(receipt['retry_allowed'], False)
            self.assertFalse(receipt['host_candidate_execution']); self.assertFalse(runner.blocked)
        self.assertEqual(runner.calls, 2)
        self.assertEqual(len(list(runner.root.glob('call-*'))), 2)

    def test_oversized_result_stays_fatal_retained_bounded_and_not_retried(self):
        runner = code.DockerRunner(self.root/'runner', max_calls=1)
        with self.assertRaises(RuntimeError) as caught:
            runner.run(self.source, guest.MAX_RESULT_BYTES+1)
        self.assertNotIsInstance(caught.exception, code.CandidateExecutionFailure)
        attempts = list(runner.root.glob('call-*'))
        self.assertEqual(len(attempts), 1); self.assertEqual(runner.calls, 1)
        receipt = json.loads((attempts[0]/'result.json').read_bytes())
        self.assertEqual(receipt['status'], 'FAILED_NO_RETRY')
        self.assertEqual(receipt['failure_classification'], 'FATAL_EXECUTION_FAILURE')
        self.assertIsNone(receipt['candidate_diagnostic']); self.assertIs(receipt['retry_allowed'], False)
        self.assertTrue(receipt['cleanup_verified']); self.assertTrue(receipt['source_integrity_verified'])
        self.assertTrue(receipt['execution_started']); self.assertFalse(receipt['host_candidate_execution'])
        self.assertLessEqual((attempts[0]/'stdout.bin').stat().st_size, guest.MAX_RESULT_BYTES+1)
        self.assertLessEqual((attempts[0]/'stderr.bin').stat().st_size, 65536)
        self.assertEqual(receipt['timeout_seconds'], 20)
        for flag, value in (('--network','none'), ('--memory','512m'), ('--cpus','1')):
            self.assertEqual(receipt['command'][receipt['command'].index(flag)+1], value)
        self.assertEqual(len(list(runner.root.glob('call-*'))), 1)


if __name__=='__main__':
    unittest.main()
