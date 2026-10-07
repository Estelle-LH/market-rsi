"""Real committed synthetic sources/native recorder; candidate processes mocked.

No resident Train reads, account calls, estimator fits or live ledger mutation.
Dependency subprocess parity is independently tested in the preflight suite.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from experiments import nfl_ingame_prediction_reference as reference
from experiments.test_nfl_ingame_prediction_reference import synthetic_fixture
from supervisor_harness import account_controller_feedback_consumer as c
from supervisor_harness import candidate_production_preflight as p
from supervisor_harness import continuous_candidate_handoff as legacy
from supervisor_harness import continuous_candidate_handoff_v2 as h
from supervisor_harness import opened_train_discovery_worker as w
from supervisor_harness import test_account_controller_feedback_consumer as cf
from supervisor_harness import test_continuous_candidate_handoff as old_fixture
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch

PYTHON = Path('/Users/estelle/Library/Application Support/MarketRSI/runtimes/ds-py312-20260912-01/bin/python')


class HandoffV2Tests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.spec, _, _, self.acceptance, _, _ = synthetic_fixture(Path(temporary.name).resolve())
        with patch.object(cf, 'PARENT', self.spec['runner']['sha256']):
            self.old = old_fixture.HandoffTests(); self.old.setUp()
        self.addCleanup(self.old.doCleanups)
        self.old.f.git.stop()
        self.batch = self.old.batch
        self.repo = self.old.f.f.repo
        self.metadata_path = h.PREFIX + 'synthetic-parent-support.json'
        self.request = {**self.old.request, 'python': str(PYTHON), 'python_sha256': w.sha(PYTHON)}
        for module, relative in ((reference, p.MODES['accepted_prediction_reference']),
                (p, h.PREFIX + 'candidate_production_preflight.py'),
                (h, h.PREFIX + 'continuous_candidate_handoff_v2.py')):
            target = self.repo / relative; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(Path(module.__file__).read_bytes())
            self.request['files'][relative] = w.sha(target)
        metadata = {'schema': 'candidate_parent_support_v1',
            'candidate_id': self.request['candidate_id'], 'module': self.request['module'],
            'contract_sha256': self.old.contract_binding['sha256'],
            'research_parent_sha256': self.spec['runner']['sha256'],
            'comparison_incumbent_sha256': self.old.decision['comparison_incumbent_sha256'],
            'mode': 'accepted_prediction_reference',
            'adapter_sources': {p.MODES['accepted_prediction_reference']:
                self.request['files'][p.MODES['accepted_prediction_reference']]},
            'accepted_reference': {'reference': self.spec, 'acceptance_binding': self.acceptance}}
        (self.repo / self.metadata_path).write_text(json.dumps(metadata))
        self.request['files'][self.metadata_path] = w.sha(self.repo / self.metadata_path)
        self.git('init', '-q'); self.git('add', '.')
        self.git('-c', 'user.name=Synthetic', '-c', 'user.email=test@invalid', 'commit', '-qm', 'fixture')
        self.request['source_commit'] = self.git('rev-parse', 'HEAD').strip()
        self.rebind()

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo, text=True)

    def rebind(self, review_changes=None):
        self.request_binding = self.old.write('v2-request', self.request)
        self.review = {**self.old.review, 'request_sha256': self.request_binding['sha256'],
                       'files': self.request['files'], 'source_commit': self.request['source_commit']}
        self.review.update(review_changes or {})
        self.review_binding = self.old.write('v2-review', self.review)

    def probe(self, *_):
        return {'versions': p.EXPECTED_VERSIONS, 'executable': str(PYTHON),
                'prefix': str(PYTHON.parent.parent)}

    def invoke(self, prepare=False):
        function = h.prepare if prepare else h.handoff
        return function(self.batch, self.old.selection, self.request_binding, self.review_binding,
            self.old.contract_binding, self.old.f.directory, self.old.f.authority_binding,
            self.repo, parent_check=self.metadata_path)

    @contextmanager
    def launches(self, effect=None):
        """Mock only candidate launches, retaining real committed Git checks."""
        original = subprocess.Popen
        candidate = Mock(side_effect=effect)
        def launch(command, *args, **kwargs):
            if '--output' in command:
                return candidate(command, *args, **kwargs)
            return original(command, *args, **kwargs)
        with patch.object(w.subprocess, 'Popen', side_effect=launch):
            yield candidate

    def test_prepare_checks_original_without_native_or_global_admission(self):
        before = self.batch.snapshot()
        with patch.object(p, '_probe', side_effect=self.probe) as probe:
            result = self.invoke(prepare=True)
        self.assertTrue(result['passed']); probe.assert_called_once()
        self.assertEqual(self.batch.snapshot(), before)
        self.assertFalse((self.batch.root / 'preflight_handoff').exists())
        self.assertFalse((self.batch.root / 'worker').exists())

    def test_fresh_original_preflight_then_native_worker_exact_lineage(self):
        with patch.object(p, '_probe', side_effect=self.probe), \
                self.launches(self.old.f.completed_child) as launch:
            result = self.invoke()
        launch.assert_called_once(); self.assertEqual(result['outcome'], 'succeeded')
        branch = self.batch.snapshot()['branches'][0]
        self.assertEqual(branch['research_parent_sha256'], self.spec['runner']['sha256'])
        self.assertEqual(branch['comparison_incumbent_sha256'], self.old.decision['comparison_incumbent_sha256'])
        self.assertEqual(self.batch.snapshot()['incumbent']['candidate_sha256'], cf.INCUMBENT)

    def test_probe_failure_does_not_spend_native_attempt_or_fit_reservation(self):
        with patch.object(p, '_probe', side_effect=ValueError('synthetic import failure')), \
                self.launches() as launch:
            with self.assertRaisesRegex(ValueError, 'synthetic import'): self.invoke()
        launch.assert_not_called(); self.assertEqual(self.batch.snapshot()['branches'], [])
        self.assertFalse((self.batch.root / 'preflight_handoff/a.json').exists())
        self.assertFalse((self.batch.root / 'worker').exists())

    def test_original_semantic_review_denied_before_import_or_selection(self):
        for change in ({'passed': 1}, {'semantic_source_matches_decision': False}, {'files': {}},
                       {'selection_sha256': 'f' * 64}, {'extra': True}):
            self.rebind(change)
            with patch.object(p, '_probe') as probe:
                with self.assertRaisesRegex(ValueError, 'original scientific'): self.invoke()
                probe.assert_not_called()
        self.assertEqual(self.batch.snapshot()['branches'], [])

    def test_outer_cutoff_crossed_during_import_prevents_native_admission(self):
        def probe(*_):
            self.batch._clock = lambda: c.CUTOFF
            return self.probe()
        with patch.object(p, '_probe', side_effect=probe), self.launches() as launch:
            with self.assertRaisesRegex(ValueError, 'selection stop'): self.invoke()
        launch.assert_not_called(); self.assertEqual(self.batch.snapshot()['branches'], [])

    def test_completed_recovery_after_deadline_does_not_import_read_head_or_spawn(self):
        with patch.object(p, '_probe', side_effect=self.probe), \
                self.launches(self.old.f.completed_child): first = self.invoke()
        self.old.f.f.write('authority', {'closed': True})
        self.batch = ContinuousDiscoveryBatch(self.batch.root, allow_temporary=True,
            test_clock=lambda: datetime(2026, 10, 6, tzinfo=timezone.utc), allow_test_clock=True)
        with patch.object(p, '_probe', side_effect=AssertionError('no probe')), \
                patch.object(w.subprocess, 'check_output', side_effect=AssertionError('no HEAD')), \
                self.launches() as launch:
            second = self.invoke()
        self.assertEqual(first, second); launch.assert_not_called()

    def test_failed_worker_retained_and_not_automatically_retried(self):
        child = Mock(pid=1234, wait=Mock(return_value=7), poll=Mock(return_value=7))
        with patch.object(p, '_probe', side_effect=self.probe), \
                self.launches(lambda *_args, **_kwargs: child) as launch:
            first = self.invoke(); second = self.invoke()
        self.assertEqual(first, second); launch.assert_called_once()
        self.assertEqual(first['outcome'], 'failed')

    def test_uncertain_worker_claim_remains_nonretryable(self):
        with patch.object(p, '_probe', side_effect=self.probe), \
                self.launches(KeyboardInterrupt('uncertain')) as launch:
            with self.assertRaises(KeyboardInterrupt): self.invoke()
            with self.assertRaisesRegex(RuntimeError, 'incomplete original claim'): self.invoke()
        launch.assert_called_once()

    def test_interrupted_preflight_record_not_a_fresh_admission_or_retry_permission(self):
        with patch.object(p, '_probe', side_effect=self.probe), \
                patch.object(legacy, 'handoff', side_effect=KeyboardInterrupt('before native selection')):
            with self.assertRaises(KeyboardInterrupt): self.invoke()
        with patch.object(p, '_probe') as probe, self.launches() as launch:
            with self.assertRaisesRegex(RuntimeError, 'inspect without retry'): self.invoke()
        probe.assert_not_called(); launch.assert_not_called()

    def test_unbound_selected_legacy_original_not_implicitly_adopted(self):
        self.batch.select_controller_pool([self.old.selection])
        with patch.object(p, '_probe') as probe:
            with self.assertRaisesRegex(RuntimeError, 'no automatic v2 adoption'): self.invoke()
        probe.assert_not_called()

    def test_receipt_and_entry_source_drift_denies_cached_recovery(self):
        with patch.object(p, '_probe', side_effect=self.probe), \
                self.launches(self.old.f.completed_child): self.invoke()
        path = self.batch.root / 'preflight_handoff/a.json'
        record = json.loads(path.read_text()); record['preflight']['passed'] = False
        path.write_text(json.dumps(record))
        with self.launches() as launch:
            with self.assertRaisesRegex(ValueError, 'stored original preflight'): self.invoke()
        launch.assert_not_called()

    def test_concurrent_original_calls_execute_once(self):
        results, errors = [], []
        def call():
            try: results.append(self.invoke())
            except BaseException as error: errors.append(error)
        with patch.object(p, '_probe', side_effect=self.probe), \
                self.launches(self.old.f.completed_child) as launch:
            threads = [threading.Thread(target=call) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
        self.assertEqual(errors, []); self.assertEqual(results[0], results[1]); launch.assert_called_once()


if __name__ == '__main__': unittest.main()
