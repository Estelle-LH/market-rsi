"""Actual bounded pure Python, synthetic JSON only; no account/Train."""
from pathlib import Path
import sys
import tempfile
from unittest import TestCase, main
from unittest.mock import patch

from supervisor_harness import price_capacity_replay as replay


class ReplayTests(TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.source = self.root / 'capacity.py'
        self.source.write_text("def apply(context):\n    return {'lesson': context['lesson']}\n")

    def run_child(self, name='run', **kwargs):
        return replay.invoke(replay.pin(self.source), replay.pin(Path(sys.executable)), {'lesson': 'negative result'},
            self.root / name, seconds=kwargs.get('seconds', 2), rss_bytes=1073741824)

    def test_measured_child_and_no_same_directory_retry(self):
        result = self.run_child(); self.assertTrue(result['succeeded'])
        self.assertEqual(result['output'], {'lesson': 'negative result'})
        receipt = replay.json.loads(replay.read(result['receipt']))
        self.assertTrue(receipt['process_reaped']); self.assertEqual(receipt['exit_code'], 0)
        self.assertEqual(receipt['train_fits'], 0); self.assertEqual(receipt['account_calls'], 0)
        self.assertEqual(receipt['source'], replay.pin(self.source))
        self.assertGreater(receipt['wall_seconds'], 0)
        self.assertFalse(receipt['arbitrary_code_containment_claim'])
        with self.assertRaises(FileExistsError): self.run_child()

    def test_known_execution_failure_saved_not_performance_evidence(self):
        self.source.write_text("def apply(context):\n    return {'bad': 1 / 0}\n")
        result = self.run_child(); self.assertFalse(result['succeeded']); self.assertIsNone(result['output'])
        receipt = replay.json.loads(replay.read(result['receipt']))
        self.assertNotEqual(receipt['exit_code'], 0); self.assertTrue(receipt['process_reaped'])

    def test_hang_is_bounded_and_reaped(self):
        self.source.write_text("def apply(context):\n    while True:\n        pass\n    return {}\n")
        result = self.run_child(seconds=.15); self.assertFalse(result['succeeded'])
        receipt = replay.json.loads(replay.read(result['receipt']))
        self.assertEqual(receipt['stop_reason'], 'timeout'); self.assertTrue(receipt['process_reaped'])

    def test_sampler_failure_saved_as_unknown_not_zero_and_reaped(self):
        with patch('supervisor_harness.opened_train_discovery_worker.sample_rss', side_effect=PermissionError('synthetic denial')):
            result = self.run_child()
        receipt = replay.json.loads(replay.read(result['receipt']))
        self.assertFalse(result['succeeded']); self.assertIsNone(receipt['sampled_peak_rss_bytes'])
        self.assertEqual(receipt['error_type'], 'PermissionError'); self.assertTrue(receipt['process_reaped'])

    def test_static_denial_and_binding_drift_before_launch(self):
        binding = replay.pin(self.source); self.source.write_text('import os\n')
        with patch.object(replay.subprocess, 'Popen') as child:
            with self.assertRaises(ValueError):
                replay.invoke(binding, replay.pin(Path(sys.executable)), {}, self.root / 'invalid', seconds=1, rss_bytes=1024)
        self.assertFalse(child.called); self.assertFalse((self.root / 'invalid').exists())


if __name__ == '__main__': main()
