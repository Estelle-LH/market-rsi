import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

import test_historical_grid_objective_controller as fixtures
from market_rsi import file_hash, fresh_json, load_json
from materialize_selected_grid_objective import materialize, prior_day_label_mask, write_archive


class SelectedGridLabelTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.GridObjectiveControllerTests()
        self.fixture.setUp()
        f = self.fixture
        self.root = f.root
        f.inspect(); f.query()
        f.broker.call('propose_objective', f.proposal_args())
        f.broker.call('submit_grid_objective_decision',
                      {'action': 'select', 'proposal_id': 'p1', 'reason': 'fixture'})
        (self.root / 'session').mkdir()
        fresh_json(self.root / 'session/assessment.json',
                   {'valid': True, 'process_reaped': True, 'exit_code': 0,
                    'controller_stage': 'grid_objective', 'codex_harness_runtime_unchanged': True,
                    'final_message_origin': 'codex_harness_terminal_handshake'})
        fresh_json(self.root / 'prompt.txt', {'fixture': True})
        source = Path(__file__).resolve().parents[1]
        names = ['historical_grid_objectives.py', 'historical_grid_objective_controller.py',
                 'run_codex_glm_controller.py']
        (self.root / 'source-snapshot').mkdir()
        for name in names:
            (self.root / 'source-snapshot' / name).write_bytes((source / name).read_bytes())
        fresh_json(self.root / 'preparation.json',
                   {'source_hashes': {n: file_hash(source / n) for n in names},
                    'workspace_sha256': file_hash(f.workspace / 'workspace.json'),
                    'prompt_sha256': file_hash(self.root / 'prompt.txt')})
        fresh_json(self.root / 'dispatch-claim.json',
                   {'preparation_sha256': file_hash(self.root / 'preparation.json')})
        # Must be outside the controller directory; production never mutates it.
        self.output = self.root.parent / (self.root.name + '-labels')

    def tearDown(self):
        if self.output.exists():
            import shutil
            shutil.rmtree(self.output)  # Exact test-created temporary output only.
        self.fixture.tearDown()

    def test_selected_only_round_trip_preserves_missing_rows(self):
        value = materialize(self.root, self.output)
        self.assertEqual(set(value['queries']), {'q1'})
        self.assertEqual(value['queries']['q1']['rows'], 4)
        self.assertEqual(value['queries']['q1']['covered_rows'], 1)
        self.assertFalse(value['training_admitted'])
        self.assertFalse(value['fresh_holdout'])
        self.assertEqual(value['new_model_calls'], 0)
        with np.load(self.output / 'q1.npz', allow_pickle=False) as labels:
            np.testing.assert_array_equal(labels['row_id'], self.fixture.arrays['row_id'])
            self.assertEqual(int(labels['available'].sum()), 1)
            self.assertEqual(int(np.isnan(labels['delta_probability']).sum()), 3)
            self.assertTrue(np.all(labels['label_available_ms'] > labels['decision_ms']))
        with self.assertRaises(FileExistsError):
            materialize(self.root, self.output)

    def test_source_snapshot_mutation_is_rejected_before_output(self):
        (self.root / 'source-snapshot/historical_grid_objectives.py').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            materialize(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_handshake_required(self):
        path = self.root / 'session/assessment.json'; value = load_json(path)
        value['final_message_origin'] = 'unverified_text'; path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'terminal handshake'):
            materialize(self.root, self.output)

    def test_cannot_write_inside_completed_controller(self):
        with self.assertRaisesRegex(ValueError, 'must not modify'):
            materialize(self.root, self.root / 'new-labels')

    def test_profile_mismatch_preserves_failed_claim(self):
        with patch('materialize_selected_grid_objective.profile', return_value={'wrong': True}):
            with self.assertRaisesRegex(ValueError, 'does not reproduce'):
                materialize(self.root, self.output)
        self.assertTrue((self.output / 'claim.json').exists())
        self.assertTrue((self.output / 'failure.json').exists())
        self.assertFalse((self.output / 'result.json').exists())

    def test_d_minus_one_gate_blocks_cross_midnight_labels(self):
        d = 86400000
        observed = np.array([d-100, d-100, d+100, d-100], dtype=np.int64)
        labels = np.array([d-1, d, d+200, d-1], dtype=np.int64)
        available = np.array([True, True, True, False])
        result = prior_day_label_mask(observed, labels, available, d+1000)
        np.testing.assert_array_equal(result, [True, False, False, False])

    def test_past_or_misaligned_labels_cannot_pass_causal_gate(self):
        with self.assertRaisesRegex(ValueError, 'future-only'):
            prior_day_label_mask(np.array([10]), np.array([9]), np.array([True]), 86400000)
        with self.assertRaises(ValueError):
            prior_day_label_mask(np.array([10]), np.array([20]), np.array([1]), 86400000)

    def test_pickle_and_overwrite_blocked(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, 'object arrays'):
            write_archive(self.output / 'bad.npz', {'a': np.array([{}], dtype=object)})
        path = self.output / 'good.npz'; write_archive(path, {'a': np.array([1])})
        original = file_hash(path)
        with self.assertRaises(FileExistsError):
            write_archive(path, {'a': np.array([2])})
        self.assertEqual(file_hash(path), original)


if __name__ == '__main__':
    unittest.main()
