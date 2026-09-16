from pathlib import Path
import tempfile
import unittest

from market_rsi import digest, file_hash, fresh_json, load_json
from controller_harness_contract import MAX_TOOL_CALLS, MAX_TURNS
from memory_replication.broker import INSTRUCTIONS
from memory_replication.study import final_summary, heldout_gate, source_path
from scripts.validate_experiment_spec import validate


ROOT = Path(__file__).resolve().parents[1]


class ReplicationTests(unittest.TestCase):
    def test_controller_can_reach_submission_after_validation_recovery(self):
        self.assertEqual(MAX_TURNS, MAX_TOOL_CALLS)
        self.assertEqual(MAX_TURNS, 32)
        self.assertIn('Reserve the last four tool calls', INSTRUCTIONS)
        self.assertIn("third candidate's result is interpreted, submit immediately", INSTRUCTIONS)

    def test_frozen_spec(self):
        spec = validate(load_json(ROOT/'MEMORY_REPLICATION_SPEC_2026-09-14.json'))
        self.assertEqual(spec['rounds'], 8)
        self.assertEqual(len(spec['final']), 20)
        self.assertFalse(spec['formal_promotion'])
        self.assertEqual(source_path('2026-09-14T09'),
            '/opt/d10/raw/data/polymarket/polymarket-20260914T09.jsonl.zst')

    def test_reject_short_or_reused_final(self):
        original = load_json(ROOT/'MEMORY_REPLICATION_SPEC_2026-09-14.json')
        short = {**original, 'final': original['final'][:19]}
        with self.assertRaises(ValueError):
            validate(short)
        reused = {**original, 'prior_exposure': {**original['prior_exposure'],
            'opened_final_sessions': [original['final'][0]['session']]}}
        with self.assertRaises(ValueError):
            validate(reused)

    def test_final_summary_uses_equal_sessions(self):
        def arm(date, mse, n, market):
            return dict(date=date, candidate_mse=mse, n=n, pearson_ic=.1,
                rank_ic=.1, calibration_slope=1.,
                market_scores=[dict(market_index=0, candidate_sse=market)])
        rows = [dict(archive=arm('2026-01-01T00', 1., 1, 1.),
                     fresh=arm('2026-01-01T00', 2., 1, 2.),
                     baseline=arm('2026-01-01T00', 3., 1, 3.)),
                dict(archive=arm('2026-01-02T00', 3., 9, 3.),
                     fresh=arm('2026-01-02T00', 2., 9, 2.),
                     baseline=arm('2026-01-02T00', 4., 9, 4.))]
        result = final_summary(rows)
        self.assertEqual(result['equal_session_mse']['archive'], 2.)
        self.assertEqual(result['row_weighted_mse']['archive'], 2.8)
        self.assertEqual(result['archive_better_than_fresh_session_fraction'], .5)

    def test_final_gate_requires_all_rounds(self):
        spec = load_json(ROOT/'MEMORY_REPLICATION_SPEC_2026-09-14.json')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a = root/'a.json'
            b = root/'b.json'
            fresh_json(a, {'plan':'a'})
            fresh_json(b, {'plan':'b'})
            commitments = [dict(path=str(path), sha256=file_hash(path)) for path in (a,b)]
            (root/'round-1').mkdir()
            fresh_json(root/'round-1/paired-freeze.json', dict(commitments=commitments,
                models=dict(archive='a', fresh='b', baseline='c')))
            heldout_gate(root, spec['dev'][0]['session'], 'dev', commitments, spec)
            with self.assertRaises(FileNotFoundError):
                heldout_gate(root, spec['final'][0]['session'], 'final', commitments, spec)


if __name__ == '__main__':
    unittest.main()
