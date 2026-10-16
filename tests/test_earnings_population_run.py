"""Entry/preparation contract probes with inert services, no live admission."""
from contextlib import contextmanager, ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

import earnings_clock as clock
import earnings_entry as entry
import earnings_native_failure as native_failure
import earnings_population_run as run
import earnings_population_services as services
from supervisor_harness import capacity_feedback_engine as engine
from test_earnings_population_runtime import Fixture, save

ORIGINAL_IDLE_SNAPSHOT = run.idle_snapshot


class PreparationContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        self.owned, self.repo = self.home / 'owned', self.home / 'repo'
        self.adopted, self.old = self.home / 'adopted', self.home / 'old'
        self.id = 'edgar-population-20261016-01'
        self.commit = 'a' * 40
        self.baseline = dict(run.EXTRA_BASELINE, max_rowid=9000, request_count=9000,
                             charged_nano_usd=160000000000, rows_sha256='b' * 64)
        self.source = self.repo / 'tools/edgar_forecast_openai.py'
        source = save(self.source, {'synthetic_source': True})
        self.plan = save(self.repo / run.PLAN, {'synthetic_plan': True})
        self.manifest = save(self.adopted / 'manifest.json', {'entrypoints': {
            'R': 'researcher_child_01.py', 'H': 'harness_v0.py'}, 'manifest': {
            'components': {'R': {'sources': {'researcher_child_01.py':
                'c3296f1b75cc10a6e67f746b0137f99f2f6765740b19f59b716acd29fa3907be'}},
                'H': {'sources': {'harness_v0.py': 'c' * 64}}},
            'M': 'd' * 64, 'model': {'requested_model': 'gpt-6.1-sol',
                'serving_snapshot': 'unknown', 'serving_snapshot_verified': False}}})
        for name in ['researcher_child_01.py', 'harness_v0.py']:
            save(self.adopted / 'source' / name, {'synthetic_program': name})
        save(self.old / 'ACTUAL09-FINAL-REVIEW.json', {'synthetic_review': True})
        self.original_runtime = {'max_input_tokens': 100000, 'max_output_tokens': 25000,
            'company_wall_seconds': 1800, 'models': {'gpt-6.1-sol': {
                'api_model': 'gpt-6.1-sol', 'effort': 'max', 'input': '2',
                'cached': '0.1', 'write': '2.5', 'output': '10'}}}
        self.ciks = ['CIK0000004457', 'CIK0000017313']
        self.prepared = []
        self.original_checked = entry.checked
        stack = ExitStack()
        self.addCleanup(stack.close)
        for target, name, value in [(run, 'ROOT', self.owned), (entry, 'REPO', self.repo),
                                    (run, 'ADOPTED', self.adopted), (run, 'OLD', self.old),
                                    (run, 'MANIFEST', Path(self.manifest['path']))]:
            stack.enter_context(patch.object(target, name, value))
        self.idle = stack.enter_context(patch.object(run, 'idle_snapshot', return_value=self.baseline))
        stack.enter_context(patch.object(run, 'source_paths', return_value={
            'forecaster': str(self.source), run.PLAN: self.plan['path']}))
        self.git = stack.enter_context(patch.object(run.subprocess, 'run', side_effect=self.git_read))
        stack.enter_context(patch.object(entry, 'checked', side_effect=self.checked))
        stack.enter_context(patch.object(engine.activation, '_read', return_value=b'synthetic interpreter'))
        stack.enter_context(patch.object(run, 'select_companies', return_value=self.ciks))
        stack.enter_context(patch.object(run, 'resident', side_effect=lambda cik: {
            'runtime': self.original_runtime, 'case': {'cik': cik, 'synthetic_public': True}}))
        self.preflight = stack.enter_context(patch.object(run, 'preflight', side_effect=self.capture))
        stack.enter_context(patch('socket.socket', side_effect=AssertionError('network forbidden')))

    def git_read(self, command, **kwargs):
        if command == ['git', 'rev-parse', 'HEAD']:
            return SimpleNamespace(stdout=self.commit + '\n')
        name = command[2].split(':', 1)[1]
        return SimpleNamespace(stdout=(self.repo / name).read_bytes())

    def checked(self, bound):
        path = Path(bound['path'])
        if path.is_relative_to(self.adopted / 'source'):
            # Historical source reader is inert; no real adoption proof here.
            return path.read_bytes()
        return self.original_checked(bound)

    def capture(self, bound, **kwargs):
        self.prepared.append((engine.read(bound), kwargs))
        return self.prepared[-1][0]

    def test_preparation_preserves_bookkeeping_fixed_companies_slots_and_no_review(self):
        bound = run.prepare(self.id)
        value, options = self.prepared[-1]
        self.assertEqual(options, {'require_review': False})
        self.assertEqual(value, engine.read(bound))
        self.assertEqual(value['baseline'], self.baseline)
        self.assertEqual(value['original_extra_baseline'], run.EXTRA_BASELINE)
        self.assertEqual(value['original_extra_cap_nano_usd'], 50000000000)
        self.assertEqual(value['additional_cap_nano_usd'], 5000000000)
        self.assertEqual(value['companies'], self.ciks)
        self.assertIsNone(value['review'])
        self.assertEqual(len(value['slots']['forecast']), 6)
        for role in ['controller', 'author', 'review']:
            self.assertEqual(value['slots'][role], [str(self.owned / 'attempts' / self.id / 'roles' /
                                                     f'{role}-{i:02d}') for i in (1, 2)])
        self.assertEqual(len({p for slots in value['slots'].values() for p in slots}), 12)
        self.assertFalse((self.owned / 'attempts' / self.id).exists())
        cutoff = datetime.fromisoformat(value['cutoff_utc'].replace('Z', '+00:00'))
        terminal = datetime.fromisoformat(value['deadline_utc'].replace('Z', '+00:00'))
        self.assertEqual((terminal - cutoff).total_seconds(), 60)
        initial = engine.read(value['initial_population'])
        self.assertEqual(initial['exposed_companies'], ['CIK0000003545'])
        self.assertEqual(initial['explorers'], [])
        self.assertEqual(initial['anchor_id'], initial['stable_id'])

    def test_old_input_or_attempt_id_never_reopens(self):
        for kind in ['inputs', 'attempts']:
            path = self.owned / kind / self.id
            path.mkdir(parents=True)
            sentinel = path / 'preserved'
            sentinel.write_bytes(b'old attempt')
            with self.subTest(kind=kind), self.assertRaises(FileExistsError):
                run.prepare(self.id)
            self.assertEqual(sentinel.read_bytes(), b'old attempt')
            self.idle.assert_not_called()
            self.id = 'edgar-population-20261016-02'

    def test_source_drift_fails_before_writing_input_directory(self):
        self.git.side_effect = lambda command, **kwargs: SimpleNamespace(
            stdout=self.commit + '\n' if command[1] == 'rev-parse' else b'uncommitted drift')
        with self.assertRaisesRegex(ValueError, 'Uncommitted'):
            run.prepare(self.id)
        self.assertFalse((self.owned / 'inputs' / self.id).exists())
        self.assertFalse((self.owned / 'attempts' / self.id).exists())
        self.preflight.assert_not_called()

    def test_invalid_id_and_pending_accounting_stop_before_inputs(self):
        with self.assertRaises(ValueError):
            run.prepare('edgar-research-20261016-28')
        self.idle.assert_not_called()
        self.idle.side_effect = RuntimeError('pending synthetic fee')
        with self.assertRaises(RuntimeError):
            run.prepare(self.id)
        self.assertFalse((self.owned / 'inputs' / self.id).exists())


class ExecutionContracts(Fixture):
    def setUp(self):
        super().setUp()
        self.events, self.instances = [], []
        self.closed, self.owner_enter_failure, self.owner_exit_failure = False, False, False
        self.loop_failure, self.pending, self.closure_failure = None, False, False
        case = self
        class Budget:
            def active(self):
                case.assertFalse(case.closed)
                case.events.append('budget_active')
            def summary(self):
                case.assertFalse(case.closed, 'summary attempted after close')
                case.events.append('budget_summary')
                return {'original_global_cap_usd': 200, 'original_extra_cap_usd': 50,
                        'new_cap_usd': 5, 'synthetic': True}
        self.budget = Budget()
        class FakeServices:
            def __init__(self, binding, **kwargs):
                self.pending, self.contexts = [], {}
                case.instances.append(self)
                case.events.append('construct_services')
            def factories(self):
                return {role: lambda *args, **kwargs: None for role in case.value['slots']}
            def start_execution(self):
                case.assertTrue((case.root / 'clock.json').is_file())
                case.assertIn('owner_entered', case.events)
                case.events.append('start_execution')
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(run, 'Services', FakeServices))
        self.idle = stack.enter_context(patch.object(run, 'idle_snapshot', return_value=self.synthetic_original))
        self.owner = stack.enter_context(patch.object(run, 'open_capacity_runtime', side_effect=self.open_owner))
        self.loop = stack.enter_context(patch.object(run, 'loop', side_effect=self.run_loop))
        stack.enter_context(patch.object(clock, 'boot_id', return_value='11111111-1111-1111-1111-111111111111'))
        self.closure = stack.enter_context(patch.object(native_failure, 'close_failed_work', side_effect=self.close_native))
        stack.enter_context(patch.object(entry, 'credential', side_effect=AssertionError('credential forbidden')))

    @contextmanager
    def open_owner(self, binding, **kwargs):
        if self.owner_enter_failure:
            raise RuntimeError('synthetic owner admission failure')
        # Real original clock admission: an early policy/code directory would
        # fail here. Boot identity alone is mocked; no Native/ledger owner used.
        value = engine.read(binding)
        _, bound = clock.capture_or_load(self.root, {'source_commit': value['source_commit'],
            'new_request_cutoff_utc': value['cutoff_utc'], 'deadline_utc': value['deadline_utc']})
        self.events.append('owner_entered')
        try:
            yield {'clock_binding': bound, 'roles': {role: lambda: None for role in self.value['slots']},
                   'budget': self.budget}
        finally:
            self.closed = True
            self.events.append('owner_closed')
        if self.owner_exit_failure:
            raise RuntimeError('synthetic terminal failure')

    def run_loop(self, root, initial, companies, roles, *, admit, max_rounds):
        self.assertEqual(root, self.root)
        self.assertEqual(companies, self.ciks)
        self.assertEqual(max_rounds, 2)
        self.assertTrue(admit(None))
        self.assertTrue((self.root / 'transport-policy.json').is_file())
        self.events.append('loop')
        if self.pending:
            self.instances[0].pending.append(({'capacity': SimpleNamespace(batch='synthetic-batch'),
                                               'pair_sha256': 'f' * 64}, 'synthetic-work-id'))
        if self.loop_failure is not None:
            raise self.loop_failure
        return {'synthetic_completed_rounds': 2, 'not_real_model_or_feedback': True}

    def close_native(self, *args, **kwargs):
        self.assertTrue(self.closed, 'Native closure happened before owner accounting closed')
        self.events.append('native_closure')
        if self.closure_failure:
            raise ValueError('synthetic unresolved closure')
        return {'status': 'synthetic-closed', 'retry_allowed': False}

    def test_completion_real_clock_order_and_summary_before_close(self):
        result = engine.read(run.execute(self.bound()))
        self.assertEqual(result['status'], 'COMPLETED_DISCOVERY_PILOT')
        self.assertFalse(result['improvement_proven'])
        self.assertFalse(result['retry_allowed'])
        self.assertLess(self.events.index('owner_entered'), self.events.index('start_execution'))
        self.assertLess(self.events.index('budget_summary'), self.events.index('owner_closed'))
        self.assertFalse((self.root / 'population-run-failure.json').exists())
        self.owner.assert_called_once()
        self.loop.assert_called_once()

    def test_missing_actual_review_stops_before_owner_or_services(self):
        # Uses actual population preflight under inherited inert source/ledger
        # fixtures, not a mocked successful review/admission function.
        with self.assertRaises(ValueError):
            run.execute(self.bound(reviewed=False))
        self.assertEqual(self.instances, [])
        self.idle.assert_not_called()
        self.owner.assert_not_called()

    def test_pending_shared_fees_stop_before_owner(self):
        self.idle.side_effect = RuntimeError('pending fees')
        with self.assertRaises(RuntimeError):
            run.execute(self.bound())
        self.assertEqual(self.instances, [])
        self.owner.assert_not_called()

    def test_actual_idle_snapshot_is_read_only_and_rejects_pending_or_busy_lock(self):
        lock_path = self.ledger.parent / '.capacity-runtime.lock'
        lock_path.write_bytes(b'owned synthetic lock')
        before = self.ledger.read_bytes()
        self.assertEqual(ORIGINAL_IDLE_SNAPSHOT(), self.synthetic_original)
        self.assertEqual(self.ledger.read_bytes(), before)
        self.db.execute("INSERT INTO requests VALUES ('pending','gpt-6.1-sol',1,0,'reserved')")
        self.db.commit()
        with self.assertRaisesRegex(RuntimeError, 'Pending shared fees'):
            ORIGINAL_IDLE_SNAPSHOT()
        self.db.execute("DELETE FROM requests WHERE id='pending'")
        self.db.commit()
        with lock_path.open('rb') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                with self.assertRaises(BlockingIOError):
                    ORIGINAL_IDLE_SNAPSHOT()
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def test_failure_closes_owner_before_native_and_preserves_no_retry(self):
        self.loop_failure, self.pending = ValueError('PRIVATE_DIAGNOSTIC_MUST_NOT_LEAK'), True
        with self.assertRaises(ValueError):
            run.execute(self.bound())
        result = engine.read(engine.pin(self.root / 'population-run-failure.json'))
        self.assertEqual(result['status'], 'FAILED_NO_RETRY')
        self.assertEqual(result['error_type'], 'ValueError')
        self.assertEqual(result['native_closure']['status'], 'synthetic-closed')
        self.assertNotIn('PRIVATE_DIAGNOSTIC', str(result))
        self.assertFalse(result['retry_allowed'])
        self.assertLess(self.events.index('owner_closed'), self.events.index('native_closure'))
        self.assertFalse((self.root / 'population-run-result.json').exists())
        self.owner.assert_called_once()
        self.loop.assert_called_once()

    def test_unresolved_native_closure_stays_explicit(self):
        self.loop_failure, self.pending, self.closure_failure = RuntimeError('synthetic'), True, True
        with self.assertRaises(RuntimeError):
            run.execute(self.bound())
        result = engine.read(engine.pin(self.root / 'population-run-failure.json'))
        self.assertEqual(result['native_closure'], {'status': 'UNRESOLVED_NO_RETRY', 'error_type': 'ValueError'})

    def test_owner_entry_and_terminal_failure_not_false_completion(self):
        self.owner_enter_failure = True
        with self.assertRaises(RuntimeError):
            run.execute(self.bound())
        self.assertEqual(engine.read(engine.pin(self.root / 'population-run-failure.json'))['status'],
                         'FAILED_NO_RETRY')
        self.assertFalse((self.root / 'population-run-result.json').exists())

    def test_owner_terminal_failure_blocks_success_after_valid_summary(self):
        self.owner_exit_failure = True
        with self.assertRaises(RuntimeError):
            run.execute(self.bound())
        self.assertIn('budget_summary', self.events)
        self.assertTrue(self.closed)
        self.assertFalse((self.root / 'population-run-result.json').exists())
        self.assertTrue((self.root / 'population-run-failure.json').exists())

    def test_real_services_constructor_and_factories_write_no_files(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp', prefix='market-rsi-entry-contract-') as home:
            native = Path(home) / 'new-native-root'
            bound = self.bound()
            before = sorted(p.relative_to(self.home) for p in self.home.rglob('*'))
            with patch.object(services, 'DockerRunner', side_effect=AssertionError('execution not entered')):
                actual = services.Services(bound, native_root=native, python_binding=run.PYTHON)
                self.assertEqual(set(actual.factories()), {'controller', 'author', 'review', 'forecast'})
                with self.assertRaises(ValueError):
                    actual.start_execution()
            self.assertEqual(before, sorted(p.relative_to(self.home) for p in self.home.rglob('*')))
            self.assertFalse(native.exists())


if __name__ == '__main__':
    unittest.main()
