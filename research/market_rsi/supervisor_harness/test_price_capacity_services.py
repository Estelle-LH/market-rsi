"""Saved original transaction + real temporary Git, mocked account and no Train."""
from copy import deepcopy
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import Mock, patch

from supervisor_harness import price_capacity_services as s
from supervisor_harness.test_coevo_pilot_transaction import TypedActionTests
from supervisor_harness.test_price_capacity_source import SOURCE, TEST


class CapacityAuthorTests(TestCase):
    def setUp(self):
        self.fixture = TypedActionTests(); self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.h = self.fixture.h; self.repo, self.root = self.h.f.repo, self.h.root
        self.packet = self.fixture.packet
        self.namespace = 'research/market_rsi/research_capacities/' + self.h.authorization['batch_id'] + '/'
        self.before_paths = {'R': self.namespace + 'r1/capacity.py', 'H': self.namespace + 'h1/capacity.py',
            'K': 'kernel.py', 'C': 'predictor.py'}
        texts = {'R': SOURCE, 'H': 'def apply(context):\n    return {}\n', 'K': '# inert kernel\n', 'C': '# inert predictor\n'}
        for axis, name in self.before_paths.items():
            path = self.repo / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(texts[axis])
        self.fixed = self.repo / 'fixed.py'; self.fixed.write_text('# inherited trusted source\n')
        for command in (['git', 'init', '-q'], ['git', 'config', 'user.name', 'SyntheticFixture'],
                ['git', 'config', 'user.email', 'fixture@invalid.test'],
                ['git', 'add', '--', 'fixed.py', *self.before_paths.values()], ['git', 'commit', '-qm', 'synthetic baseline']):
            subprocess.run(command, cwd=self.repo, check=True, capture_output=True)
        binding = lambda axis: {'sources': {self.before_paths[axis]: s.w.sha(self.repo / self.before_paths[axis])},
            'configuration_sha256': 'f' * 64}
        self.before = s.identity.manifest(kernel=binding('K'), predictor=binding('C'), harness=binding('H'),
            researcher=binding('R'), memory='e' * 64,
            model={'requested_model': s.t.c.MODEL, 'serving_snapshot': 'unknown', 'serving_snapshot_verified': False},
            runtime={'python': s.r.pin(self.h.f.python), 'dependencies': {}})
        self.entrypoints = {axis: self.before_paths[axis] for axis in ('H', 'R')}
        config = self.packet['action_context']['identity_configuration']
        config['pair'] = s.activation.pair(self.before); config['fixed_context']['model_sha256'] = self.before['M']
        config['allowed_write_paths'] = {kind: [self.before_paths[axis], self.namespace + name + '/capacity.py',
            self.namespace + name + '/test_capacity.py'] for kind, axis, name in (('researcher', 'R', 'r2'), ('harness', 'H', 'h2'))}
        self.h.authorization['account_transfer']['max_input_bytes'] = 262144
        self.h.authorization['account_roles'] = {'capacity_changes_approved': True, 'max_input_bytes': 262144}
        self.calls = []; self.transport = Mock(side_effect=self.role)

    def start(self, *, axis='researcher', history=None, limit=262144):
        self.fixture.action = axis
        self.h.authorization['account_roles']['max_input_bytes'] = limit
        self.h.authorization_binding = self.h.write('authorization', self.h.authorization)
        self.packet['authority'] = self.h.authorization
        self.packet['action_context']['identity_configuration']['fixed_context']['authority_sha256'] = self.h.authorization_binding['sha256']
        self.packet['source_context'] = {'capacity_identity': self.before, 'capacity_entrypoints': self.entrypoints}
        self.packet['bindings']['source_context'] = self.h.write('capacity-source-context', self.packet['source_context'])
        if history is not None: self.packet['history'] = history
        self.fixture.bind()
        def response(packet):
            value = self.fixture.response(packet)
            value['capacity']['write_paths'] = packet['action_context']['identity_configuration']['allowed_write_paths'][axis]
            return value
        self.h.response = response
        decision = self.h.call()
        self.runtime = SimpleNamespace(root=self.root, repo=self.repo, authority=self.h.authorization_binding,
            configuration=self.h.configuration_binding, config=self.h.config, fixed_grant=self.h.authorization,
            admit=Mock(return_value=True))
        self.ctx = {'round_index': 1, 'outputs': {'input': {'input': self.h.input_binding,
            'authorization': self.h.authorization_binding, 'configuration': self.h.configuration_binding,
            'review': self.h.review_binding}, 'controller': {'decision': decision}}, 'previous_result': {}}
        self.author = s.CapacityAuthor(self.runtime, {'fixed.py': s.w.sha(self.fixed)}, self.runtime.authority,
            role_call=self.transport)
        return self.ctx

    def role(self, role, body, schema, **kwargs):
        self.calls.append((role, deepcopy(body), kwargs))
        decision = body['original_controller_decision']
        response = {'decision_sha256': s.t.c._digest(decision), 'change_id': decision['capacity']['change_id'],
            'source_path': schema['properties']['source_path']['enum'][0], 'test_path': schema['properties']['test_path']['enum'][0],
            'capacity_source': SOURCE, 'test_source': TEST, 'implementation_notes': 'Synthetic source only, not a model finding.'}
        return {'response': response, 'call_id': kwargs['role_id'], 'usage': {'synthetic': True}, 'serving_snapshot': 'unknown',
            'input_binding': self.h.write('synthetic-author-input', {'role': role, 'role_id': kwargs['role_id'], 'payload': body}),
            'response_binding': self.h.write('synthetic-author-response', response),
            **{name + '_binding': self.h.write('synthetic-author-' + name, {'synthetic': True}) for name in ('process', 'completion')}}

    def author_once(self):
        return self.author.author(self.ctx, self.before, self.entrypoints)

    def test_R_and_H_source_service_preserves_original_version_not_import_or_activate(self):
        self.start()
        before_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=self.repo, text=True).strip()
        with patch('importlib.util.spec_from_file_location') as imported:
            authored = self.author_once()
        self.assertFalse(imported.called); self.assertEqual(authored['kind'], 'capacity')
        self.assertNotEqual(authored['source_commit'], before_commit)
        self.assertEqual(self.calls[0][1]['original_controller_decision'], self.ctx['outputs']['controller']['decision'])
        self.assertNotIn('candidate', self.calls[0][1]['original_controller_decision']['capacity'])
        receipt = s.t.c._read(authored['author_receipt'])
        self.assertEqual(receipt['axis'], 'R'); self.assertFalse(receipt['generated_tests_executed'])
        self.assertFalse(receipt['activation_performed']); self.assertTrue(receipt['awaiting_independent_source_review'])
        self.assertEqual((self.repo / self.before_paths['R']).read_text(), SOURCE)
        for name, token in authored['files'].items():
            content = subprocess.check_output(['git', 'show', authored['source_commit'] + ':' + name], cwd=self.repo)
            self.assertEqual(s.hashlib.sha256(content).hexdigest(), token)
        with self.assertRaises(FileExistsError): self.author_once()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(s.t._file(self.root / 'ledger.json')['attempts'], [])

    def test_harness_original_has_same_bounded_service_without_prediction(self):
        self.start(axis='harness'); authored = self.author_once()
        self.assertEqual(s.t.c._read(authored['author_receipt'])['axis'], 'H')
        self.assertIsNone(self.calls[0][1]['original_controller_decision']['candidate'])
        self.assertTrue(authored['source']['path'].startswith(str(self.repo / self.namespace / 'h2')))

    def test_unsafe_author_original_preserved_without_import_retry_or_source_write(self):
        self.start()
        ordinary = self.role
        def bad(*args, **kwargs):
            result = ordinary(*args, **kwargs); result['response']['capacity_source'] += '\nimport os\n'; return result
        self.transport.side_effect = bad
        with self.assertRaises(ValueError): self.author_once()
        failure = s.t._file(next(self.root.glob('capacity-author-*/failure.json')))
        self.assertFalse(failure['retry_allowed']); self.assertFalse(failure['performance_evidence'])
        self.assertFalse((self.repo / self.namespace / 'r2').exists())
        with self.assertRaises(FileExistsError): self.author_once()
        self.assertEqual(len(self.calls), 1)

    def test_uncertain_call_no_retry_and_no_fit_refund(self):
        self.start(); self.transport.side_effect = RuntimeError('synthetic uncertain completion')
        with self.assertRaises(RuntimeError): self.author_once()
        with self.assertRaises(FileExistsError): self.author_once()
        self.assertEqual(self.transport.call_count, 1)
        self.assertEqual(s.t._file(self.root / 'ledger.json')['attempts'], [])

    def test_unauthorized_closed_wrong_round_source_and_original_drift_before_role(self):
        self.start()
        for field in ('closed', 'round', 'decision', 'grant', 'source'):
            with self.subTest(field=field):
                if field == 'closed':
                    self.runtime.admit.return_value = False
                    with self.assertRaises(ValueError): self.author_once()
                    self.runtime.admit.return_value = True
                elif field == 'round':
                    self.ctx['round_index'] = True
                    with self.assertRaises(ValueError): self.author_once()
                    self.ctx['round_index'] = 1
                elif field == 'decision':
                    old = deepcopy(self.ctx['outputs']['controller']['decision'])
                    self.ctx['outputs']['controller']['decision']['capacity']['proposal'] += ' forged'
                    with self.assertRaises(ValueError): self.author_once()
                    self.ctx['outputs']['controller']['decision'] = old
                elif field == 'grant':
                    self.author.grant = self.h.write('foreign-grant', self.h.authorization)
                    with self.assertRaises(ValueError): self.author_once()
                    self.author.grant = self.runtime.authority
                else:
                    self.fixed.write_text('# changed\n')
                    with self.assertRaises(ValueError): self.author_once()
        self.assertFalse(self.transport.called)

    def test_missing_capacity_author_opt_in_and_original_evidence_rejected(self):
        self.h.authorization['account_roles']['capacity_changes_approved'] = False
        self.start()
        with self.assertRaises(ValueError): self.author_once()
        self.assertFalse(self.transport.called)

    def test_larger_author_context_and_old_budget_without_call(self):
        self.start(history={'synthetic': 'x' * 40000}, limit=262144)
        self.author_once()
        self.assertGreater(len(s.json.dumps(self.calls[0][1]).encode()), 32768)
        self.assertEqual(len(self.calls), 1)

    def test_old_role_budget_rejects_large_context_without_role_or_author_attempt(self):
        self.start(history={'synthetic': 'x' * 40000}, limit=32768)
        with self.assertRaisesRegex(ValueError, 'input byte budget'): self.author_once()
        self.assertFalse(self.transport.called); self.assertFalse(list(self.root.glob('capacity-author-*')))


if __name__ == '__main__': main()
