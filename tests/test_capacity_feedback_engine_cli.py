"""Actual separate local processes; synthetic roles only, no model transport."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('run_capacity_feedback_fixture.py')


class ProcessReplayTests(unittest.TestCase):
    def call(self, root, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), '--root', str(root), *args],
                              text=True, capture_output=True, timeout=30)

    def test_two_tasks_and_fresh_process_restores_without_service_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            for kind in ('sum', 'count'):
                with self.subTest(task=kind):
                    root = Path(temporary).resolve()/kind
                    first = self.call(root, '--task', kind)
                    self.assertEqual(first.returncode, 0, first.stderr)
                    original = json.loads(first.stdout)
                    self.assertEqual(original['completed_rounds'], 2)
                    self.assertEqual(original['service_calls'], dict.fromkeys(('controller','author','review','execute'), 2))
                    self.assertTrue(all(original['checks'].values()))
                    fresh = self.call(root, '--restore')
                    self.assertEqual(fresh.returncode, 0, fresh.stderr)
                    restored = json.loads(fresh.stdout)
                    self.assertEqual(restored['service_calls'], dict.fromkeys(('controller','author','review','execute'), 0))
                    self.assertTrue(all(restored['checks'].values()))
                    self.assertFalse(restored['learning_claim'])

    def test_mutated_restore_context_refused_without_reopening_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()/'sum'
            first = self.call(root)
            self.assertEqual(first.returncode, 0, first.stderr)
            path = root/'restore-context.json'
            path.write_text('{}')
            fresh = self.call(root, '--restore')
            self.assertNotEqual(fresh.returncode, 0)
            self.assertIn('file hash/path drift', fresh.stderr)
            self.assertEqual(len(list(root.rglob('round-*.claim.json'))), 14)

if __name__ == '__main__': unittest.main()
