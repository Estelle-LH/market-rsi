import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_validation_design as runner
from controller_design import make_workspace
from market_rsi import canonical, digest, file_hash, fresh_json, load_json
from paid_budget import PaidBudget
from test_controller_design import visible_fixture


class ValidationCommandTests(unittest.TestCase):
    def setUp(self):
        self.kw = {'workspace': Path('/tmp/fixture-workspace'), 'answer': Path('/tmp/fixture-answer'),
                   'base_url': 'http://127.0.0.1:1234/v1', 'catalog': Path('/tmp/fixture-catalog'),
                   'instructions': Path('/tmp/fixture-instructions')}

    def test_only_exact_mcp_route_changes(self):
        old = runner.harness.codex_command(**self.kw, tool_mode='canary', controller_stage='grid_learning')
        new = runner.command_for_validation(**self.kw, broker_script=Path('/tmp/controller_design.py'))
        changes = [(x, y) for x, y in zip(old, new) if x != y]
        self.assertEqual(len(old), len(new)); self.assertEqual(len(changes), 1)
        self.assertTrue(changes[0][0].startswith('mcp_servers.controller_tools.args='))
        self.assertIn('controller_design.py', changes[0][1])

    def test_no_retry_isolation_and_model_flags_preserved(self):
        new = runner.command_for_validation(**self.kw, broker_script=Path('/tmp/controller_design.py'))
        for value in ['model_providers.tinker_glm_loopback.request_max_retries=0',
                      'model_providers.tinker_glm_loopback.stream_max_retries=0',
                      'mcp_servers.controller_tools.required=true',
                      'shell_environment_policy.inherit="none"', 'web_search="disabled"',
                      '--ignore-user-config', '--strict-config', '--ephemeral', 'shell_tool']:
            self.assertIn(value, new)
        self.assertEqual(new[new.index('--model') + 1], runner.MODEL)
        self.assertNotIn('danger-full-access', ' '.join(new))

    def test_ambiguous_route_rejected(self):
        with patch.object(runner.harness, 'codex_command', return_value=['fixture']):
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                runner.command_for_validation(**self.kw, broker_script=Path('/tmp/new.py'))

    def test_changed_template_target_rejected(self):
        command = runner.harness.codex_command(**self.kw, tool_mode='canary', controller_stage='grid_learning')
        prefix = 'mcp_servers.controller_tools.args='
        index = next(i for i, v in enumerate(command) if v.startswith(prefix))
        command[index] = prefix + json.dumps(['/tmp/wrong.py', '--workspace', str(self.kw['workspace'])])
        with patch.object(runner.harness, 'codex_command', return_value=command):
            with self.assertRaisesRegex(ValueError, 'template changed'):
                runner.command_for_validation(**self.kw, broker_script=Path('/tmp/new.py'))

    def test_mcp_only_canary_never_becomes_paid_preparation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fresh_json(root / 'preparation.json', {'purpose': 'transport_canary'})
            with self.assertRaisesRegex(ValueError, 'cannot become a paid'):
                runner.preflight(root, root / 'no-budget', root / 'mcp-canary', root / 'codex-canary')

    def test_permanent_claim_stops_before_budget_or_credentials(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fresh_json(root / 'preparation.json', {'purpose': 'controller_design'})
            fresh_json(root / 'dispatch-claim.json', {'fixture': True})
            with self.assertRaisesRegex(ValueError, 'already claimed'):
                runner.preflight(root, root / 'no-budget', root / 'canary', root / 'codex-canary')

    def test_fake_backend_cannot_claim_paid_model_authorship(self):
        with self.assertRaisesRegex(ValueError, 'exact pinned'):
            runner.run_session(prepared=Path('/tmp/unused'), backend=object(), budget=None,
                               prompt='fixture', evidence_mode='paid_controller')

    def test_fixture_mode_cannot_charge_existing_real_budget(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            visible, _, _ = visible_fixture()
            make_workspace(root / 'workspace', visible, 'fixture-session', 'transport_canary')
            budget = PaidBudget.create(root / 'budget', {'experiment_id': 'real-named-study',
                'cap_usd': '10', 'target_usd': '10', 'buckets_usd': {'learning': '10'},
                'authority': 'unit test only; ensures naming guard'})
            with self.assertRaisesRegex(ValueError, 'fixture ledger'):
                runner.run_session(prepared=root, backend=object(), budget=budget,
                                   prompt='fixture', evidence_mode='synthetic_transport_fixture')
            self.assertEqual(budget.snapshot()['jobs'], {})


class ValidationPreflightTests(unittest.TestCase):
    """All receipts below are synthetic unit fixtures; no CLI or provider run."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.prepared = self.root / 'fixture-prepared'; self.prepared.mkdir()
        self.budget = PaidBudget.create(self.root / 'budget', {'experiment_id': 'fixture-study',
            'cap_usd': '200', 'target_usd': '200',
            'buckets_usd': {'learning': '130', 'final': '50', 'repair': '20'},
            'authority': 'Synthetic unit fixture, not real authorization.'})
        self.live = self.root / 'live/validation_tools/run_validation_design.py'
        self.live.parent.mkdir(parents=True); self.live.write_text('fixture dispatcher bytes')
        self.code = self.root / 'fixture-codex'; self.code.write_text('fixture runtime')
        name = 'validation_tools/run_validation_design.py'
        self.sources = {name: file_hash(self.live)}
        snap = self.prepared / 'source-snapshot' / name
        snap.parent.mkdir(parents=True); snap.write_bytes(self.live.read_bytes())
        visible, _, _ = visible_fixture()
        context = visible['context.json']
        context['budget_authorization_sha256'] = file_hash(self.root / 'budget/authorization.json')
        context['context_sha256'] = digest({k: v for k, v in context.items() if k != 'context_sha256'})
        make_workspace(self.prepared / 'workspace', visible, self.prepared.name, 'controller_design')
        preparation = {'purpose': 'controller_design', 'source_hashes': self.sources,
            'context_sha256': context['context_sha256'],
            'workspace_sha256': file_hash(self.prepared / 'workspace/workspace.json')}
        fresh_json(self.prepared / 'preparation.json', preparation)
        self.mcp = self.root / 'fixture-mcp/transport-canary.json'; self.mcp.parent.mkdir()
        fresh_json(self.mcp.parent / 'preparation.json', {'source_hashes': self.sources})
        self.seal(self.mcp, {'passed': True, 'real_stdio_child': True, 'new_controller_calls': 0,
            'context_sha256': context['context_sha256'],
            'source_preparation_sha256': file_hash(self.mcp.parent / 'preparation.json')})
        self.full = self.root / 'fixture-full/codex-fixture-canary.json'; self.full.parent.mkdir()
        fresh_json(self.full.parent / 'preparation.json', {'purpose': 'transport_canary',
            'source_hashes': self.sources})
        (self.full.parent / 'session').mkdir()
        fresh_json(self.full.parent / 'session/assessment.json', {'valid': True,
            'evidence_mode': 'synthetic_transport_fixture', 'model_authorship_proven': False,
            'process_reaped': True, 'turns': 2, 'tool_calls': 4})
        fresh_json(self.full.parent / 'fixture-only-claim.json', {'unit_fixture': True})
        import sys
        self.seal(self.full, {'schema': 'historical_validation_codex_fixture_canary_v1',
            'passed': True, 'actual_codex_cli': True, 'actual_tinker_calls': 0,
            'source_hashes': self.sources, 'context_sha256': context['context_sha256'],
            'source_preparation_sha256': file_hash(self.full.parent / 'preparation.json'),
            'assessment_sha256': file_hash(self.full.parent / 'session/assessment.json'),
            'fixture_claim_sha256': file_hash(self.full.parent / 'fixture-only-claim.json'),
            'codex_cli_sha256': file_hash(self.code), 'python_sha256': file_hash(Path(sys.executable))})
        self.p1 = patch.object(runner, '__file__', str(self.live)); self.p1.start()
        self.p2 = patch.object(runner.harness, 'CODEX', str(self.code)); self.p2.start()

    def tearDown(self):
        self.p2.stop(); self.p1.stop(); self.tmp.cleanup()

    @staticmethod
    def seal(path, payload):
        payload = {k: v for k, v in payload.items() if k != 'result_sha256'}
        payload['result_sha256'] = digest(payload)
        path.write_text(canonical(payload))

    def check(self):
        return runner.preflight(self.prepared, self.root / 'budget', self.mcp, self.full)

    def test_valid_preflight_does_not_reserve_spend_or_dispatch(self):
        result = self.check()
        self.assertFalse(result['new_test_admitted'])
        self.assertFalse(result['new_download_admitted'])
        self.assertEqual(result['controller_stage'], 'validation_design')
        self.assertEqual(self.budget.snapshot()['jobs'], {})
        self.assertFalse((self.prepared / 'dispatch-claim.json').exists())

    def test_live_source_changed_after_snapshot_rejected(self):
        self.live.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'frozen stage source'):
            self.check()

    def test_codex_binary_changed_after_canary_rejected(self):
        self.code.write_text('different runtime')
        with self.assertRaisesRegex(ValueError, 'same-source/runtime'):
            self.check()

    def test_tampered_canary_receipt_rejected(self):
        payload = load_json(self.full); payload['context_sha256'] = 'a' * 64
        self.seal(self.full, payload)
        with self.assertRaisesRegex(ValueError, 'same-source/runtime'):
            self.check()

    def test_fake_authorship_in_canary_cannot_pass(self):
        path = self.full.parent / 'session/assessment.json'
        assessment = load_json(path); assessment['model_authorship_proven'] = True
        path.write_text(canonical(assessment))
        payload = load_json(self.full); payload['assessment_sha256'] = file_hash(path)
        self.seal(self.full, payload)
        with self.assertRaisesRegex(ValueError, 'assessment'):
            self.check()

    def test_reserved_cost_blocks_upper_but_is_not_actual_spend(self):
        self.budget.reserve('fixture-held-job', 'learning', '123', 'fixture', 'a' * 64)
        with self.assertRaisesRegex(ValueError, 'whole controller upper'):
            self.check()
        self.assertEqual(self.budget.snapshot()['metered_usd'], '0')

    def test_outstanding_controller_dispatch_blocks_another(self):
        self.budget.reserve('fixture-controller-turn-001', 'learning', '1', 'fixture', 'a' * 64)
        self.budget.dispatch('fixture-controller-turn-001')
        with self.assertRaisesRegex(ValueError, 'unresolved controller'):
            self.check()

    def test_workspace_change_cannot_bypass_context(self):
        path = self.prepared / 'workspace/context.json'
        value = load_json(path); value['budget_cap_usd'] = '300'
        path.write_text(canonical(value))
        with self.assertRaisesRegex(ValueError, 'frozen metadata input'):
            self.check()


if __name__ == '__main__':
    unittest.main()
