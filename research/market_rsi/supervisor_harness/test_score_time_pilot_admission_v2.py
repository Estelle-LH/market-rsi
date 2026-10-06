"""Exact admission rehearsal: real source checks, mock child, no Train access."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch
from supervisor_harness import score_time_pilot_admission_v2 as admission
from supervisor_harness import opened_train_discovery_worker as worker
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch, DiscoveryBatchError
from data_scientist_harness import test_micro_evolution as fixture


class AdmissionTests(unittest.TestCase):
    def test_initialization_is_configured_and_restartable_before_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture_root = Path(directory).resolve()
            batch = ContinuousDiscoveryBatch(fixture_root, allow_temporary=True)
            now = datetime.now(timezone.utc)
            batch.initialize(batch_id='fixture', start_utc=now, deadline_utc=now + timedelta(minutes=15),
                max_attempts=1, initial_incumbent={'candidate_id': 'market', 'candidate_sha256': 'a'*64,
                    'scorecard_sha256': 'b'*64, 'review_sha256': 'c'*64},
                active_pool_capacity=3, learning_checkpoint_version=1)
            state = admission.configure(batch, fixture.config())
            self.assertIn('micro_evolution', state)
            self.assertEqual(state, ContinuousDiscoveryBatch(fixture_root, allow_temporary=True).snapshot())
            with self.assertRaises(DiscoveryBatchError):
                admission.configure(batch, fixture.config())

    def test_exact_prepared_admission_child_entry_terminal_and_no_retry(self):
        if os.environ.get('MARKET_RSI_EXACT_ADMISSION_REHEARSAL') != '1':
            self.skipTest('exact post-commit request not yet prepared')
        native = admission.ROOT / 'native'
        snapshot = ContinuousDiscoveryBatch(native).snapshot()
        request = admission.load(native / 'prepared_request.json')
        self.assertEqual(snapshot['attempts_claimed'], 0)
        self.assertFalse(snapshot['branches'])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / 'native'
            batch = ContinuousDiscoveryBatch(root, allow_temporary=True)
            grant = admission.load(native / 'authorization.json')
            batch.initialize(batch_id=grant['batch_id'], start_utc=grant['start_utc'],
                deadline_utc=grant['deadline_utc'], max_attempts=1,
                initial_incumbent={k: snapshot['incumbent'][k] for k in
                    ('candidate_id', 'candidate_sha256', 'scorecard_sha256', 'review_sha256')},
                active_pool_capacity=3, initial_archived_parents=admission.load(
                    admission.transaction.ROOT.parent / 'market-rsi-authorized-discovery-20261006-01/archive_imports.json')['archived_parents'],
                learning_checkpoint_version=1)
            admission.configure(batch, admission.load(native / 'evolution_configuration.json'))
            for name in ('authorization.json', 'binding.json', 'activation_memory.json'):
                shutil.copyfile(native / name, root / name)
            request = {**request, 'memory': str(root / 'activation_memory.json')}
            batch.select_controller_pool([admission.load(native / 'selection.json')])

            def synthetic_child(*args, **kwargs):
                output = root / 'runs' / request['attempt_id']
                # Constructor only relaxes temporary fixture paths, not admission predicates.
                with patch.object(admission.entry, 'ContinuousDiscoveryBatch',
                    side_effect=lambda p: ContinuousDiscoveryBatch(p, allow_temporary=True)):
                    binding = admission.entry.require_admission(worker.TRAIN, output)
                self.assertEqual(binding['candidate_id'], request['candidate_id'])
                output.mkdir()
                manifest = {'complete': True, 'model_fits': 4, 'fixture_only_no_actual_fits': True}
                for name in ('pre_score_lock', 'input_receipts', 'exclusions', 'predictions', 'scorecard'):
                    path = output / (name + ('.csv' if name == 'predictions' else '.json'))
                    path.write_text('{}')
                    manifest[name + '_sha256'] = worker.sha(path)
                (output / 'manifest.json').write_text(json.dumps(manifest))
                return Mock(pid=1234, poll=Mock(return_value=0), wait=Mock(return_value=0))

            with patch.object(worker.subprocess, 'Popen', side_effect=synthetic_child) as launch, \
                    patch.object(worker, 'sample_rss', return_value=128):
                receipt = worker.execute(batch, request, admission.REPO)
            self.assertEqual(receipt['outcome'], 'succeeded')
            launch.assert_called_once()
            self.assertEqual(batch.snapshot()['attempts_claimed'], 1)
            with patch.object(worker.subprocess, 'Popen') as retry:
                with self.assertRaisesRegex(RuntimeError, 'already claimed'):
                    worker.execute(batch, request, admission.REPO)
                retry.assert_not_called()
        self.assertEqual(ContinuousDiscoveryBatch(native).snapshot(), snapshot)


if __name__ == '__main__':
    unittest.main()
