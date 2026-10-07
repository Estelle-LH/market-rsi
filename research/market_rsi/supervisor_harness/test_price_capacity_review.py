"""Source/review/real Python smoke integration, synthetic decisions/account only."""
from copy import deepcopy
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import Mock, patch

from supervisor_harness import price_independent_review as r
from supervisor_harness import price_account_roles as roles
from supervisor_harness import test_price_capacity_services as fixtures


class CapacityReviewTests(TestCase):
    def setUp(self):
        self.f = fixtures.CapacityAuthorTests()
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        before = self.f.before
        self.f.before = fixtures.s.identity.manifest(kernel=before['components']['K'], model=before['model'],
            predictor=before['components']['C'], harness=before['components']['H'], researcher=before['components']['R'],
            memory=before['memory_sha256'], runtime={'python': r.r.pin(Path('/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12')),
                'dependencies': {}})
        self.f.start()
        ordinary = self.f.role
        def author(*args, **kwargs):
            result = ordinary(*args, **kwargs)
            directory = self.f.root / 'role_calls/author' / result['call_id']; directory.mkdir(parents=True)
            r.w.save(directory / 'schema.json', args[2])
            r.w.save(directory / 'claim.json', {'authorization': self.f.runtime.authority, 'role': 'author',
                'role_id': result['call_id'], 'schema_sha256': r.t.c._digest(args[2])})
            self.author_result = result
            return result
        self.f.transport.side_effect = author
        self.material = self.f.author_once()
        self.calls = []; self.review_transport = Mock(side_effect=self.review_role)
        self.reviewer = r.IndependentPriceReviewer(self.f.runtime, self.review_transport,
            role_grant_binding=self.f.runtime.authority)
        self.replay = patch.object(roles, '_recover', side_effect=lambda directory, claim, schema: self.author_result)
        self.replay_mock = self.replay.start(); self.addCleanup(self.replay.stop)
        # Account native replay is mocked here; separate native-wire regressions cover it.

    def review_role(self, role, packet, schema, **kwargs):
        self.calls.append((role, deepcopy(packet), kwargs))
        response = {'schema': 'market_rsi_independent_price_verdict_v1',
            'input_sha256': schema['properties']['input_sha256']['const'], 'stage': 'source', 'verdict': 'PASS',
            'finding': 'Synthetic independent source verdict; no scientific/capacity gain claim.',
            'evidence': ['Supplied source and original-bound synthetic artifact hashes'], 'research_credit': 0,
            'research_outcome': 'not_applicable', 'route_action': 'not_applicable'}
        return {'response': response, 'call_id': kwargs['operation_id'], 'usage': {'synthetic': True}, 'serving_snapshot': 'unknown',
            **{key + '_binding': self.f.h.write('synthetic-review-' + key, {'synthetic': True})
                for key in ('input', 'response', 'process', 'completion')}}

    def review(self):
        return self.reviewer.review('source', self.material)

    def test_separate_source_verdict_then_real_synthetic_test_and_single_axis_identity(self):
        binding = self.review(); receipt = r.t.c._read(binding)
        self.assertTrue(receipt['passed']); self.assertEqual(receipt['research_credit'], 0)
        self.assertNotEqual(receipt['reviewer_id'], receipt['proposer_id'])
        self.assertNotEqual(receipt['original_account_call']['call_id'], self.author_result['call_id'])
        account = self.calls[0][1]['material']
        self.assertEqual(fixtures.s.identity.change_axis(account['before_identity'], account['after_identity']), 'R')
        self.assertEqual(account['entrypoints']['H'], self.f.before_paths['H'])
        self.assertEqual(account['entrypoints']['R'], str(Path(self.material['source']['path']).relative_to(self.f.repo)))
        self.assertFalse(self.calls[0][1]['trusted_checks']['capacity_activation_performed'])
        smoke = r.t.c._read(receipt['generated_test_receipt'])
        self.assertEqual(smoke['exit_code'], 0); self.assertEqual(smoke['train_fits'], 0)
        self.assertTrue(smoke['synthetic_inputs_only']); self.assertFalse(smoke['arbitrary_code_containment_claim'])
        self.assertTrue(self.replay_mock.called)
        self.assertEqual(r.t._file(self.f.root / 'ledger.json')['attempts'], [])
        with self.assertRaises(FileExistsError): self.review()
        self.assertEqual(len(self.calls), 1)

    def test_source_test_or_original_role_drift_denied_before_independent_call(self):
        original = deepcopy(self.material)
        for field in ('source', 'test', 'files', 'commit', 'claim'):
            self.material = deepcopy(original)
            if field in ('source', 'test'):
                path = Path(self.material[field]['path']); old = path.read_text(); path.write_text(old + '# mutated\n')
            elif field == 'files': self.material['files'].pop(self.f.before_paths['K'])
            elif field == 'commit': self.material['source_commit'] = 'f' * 40
            else:
                path = self.f.root / 'role_calls/author' / self.author_result['call_id'] / 'claim.json'
                old = path.read_text(); claim = r.t._file(path); claim['authorization'] = {}; path.write_text(r.json.dumps(claim))
            try:
                with self.subTest(field=field), self.assertRaises((ValueError, r.subprocess.CalledProcessError)):
                    self.review()
            finally:
                if field in ('source', 'test', 'claim'): path.write_text(old)
        self.assertEqual(len(self.calls), 0)

    def test_author_cannot_self_sign_and_reject_never_executes_generated_code(self):
        ordinary = self.review_role
        def self_signed(*args, **kwargs):
            value = ordinary(*args, **kwargs); value['call_id'] = self.author_result['call_id']; return value
        self.review_transport.side_effect = self_signed
        with patch.object(self.reviewer, '_tests') as tested, self.assertRaises(ValueError): self.review()
        self.assertFalse(tested.called)

    def test_rejection_preserved_without_test_activation_or_retry(self):
        ordinary = self.review_role
        def reject(*args, **kwargs):
            value = ordinary(*args, **kwargs); value['response']['verdict'] = 'REJECT'; return value
        self.review_transport.side_effect = reject
        with patch.object(self.reviewer, '_tests') as tested, self.assertRaises(RuntimeError): self.review()
        self.assertFalse(tested.called)
        receipt = r.t._file(next((self.f.root / 'independent-reviews').glob('*/review.json')))
        self.assertFalse(receipt['passed'])
        with self.assertRaises(FileExistsError): self.review()
        self.assertEqual(len(self.calls), 1)

    def test_generated_test_mutated_after_verdict_cannot_launch(self):
        ordinary = self.review_role
        def mutate(*args, **kwargs):
            value = ordinary(*args, **kwargs)
            path = Path(self.material['test']['path']); path.write_text(path.read_text() + '# after verdict\n')
            return value
        self.review_transport.side_effect = mutate
        with patch.object(r.subprocess, 'Popen', wraps=r.subprocess.Popen) as launched, self.assertRaises(ValueError): self.review()
        self.assertTrue(all(call.args[0][0] == 'git' for call in launched.call_args_list))
        self.assertEqual(len(self.calls), 1)

    def test_sampler_exception_reaps_exact_child_preserves_failure_not_zero_rss(self):
        with patch.object(r.w, 'sample_rss', side_effect=PermissionError('synthetic sampler denial')):
            with self.assertRaises(PermissionError): self.review()
        receipt = r.t._file(next((self.f.root / 'independent-reviews').glob('*/candidate-test.json')))
        self.assertTrue(receipt['process_reaped']); self.assertIsNone(receipt['sampled_peak_rss_bytes'])
        self.assertEqual(receipt['diagnostic_error_type'], 'PermissionError')
        self.assertIsNotNone(receipt['exit_code']); self.assertEqual(receipt['train_fits'], 0)
        self.assertFalse(list((self.f.root / 'independent-reviews').glob('*/review.json')))


if __name__ == '__main__': main()
