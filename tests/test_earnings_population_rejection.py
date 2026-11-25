"""Independent closed-rejection boundaries on inert preserved originals.

These are protocol fixtures, not an audit of actual closed ID02. The original
seven-stage driver, SHA bindings, public FilingTools and R receipt verifier run.
Candidate Python never executes; temporary SQLite is not the real API ledger.
Root/implementer owns unmocked actual-ID02 acceptance evidence.
"""
from copy import deepcopy
from contextlib import ExitStack
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from edgar_forecast_tools import FilingTools
from earnings_entry import checked
import earnings_open_researcher as researcher
import earnings_population_rejection as rejection
import earnings_population_continuation as history
from earnings_night_budget import history_snapshot
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness import feedback_linked_loop as driver
import test_earnings_open_researcher as receipt_fixture
import test_earnings_population_case as public_fixture


class BoundReader:
    """Actual byte-binding adapter; not historical Git or admission authority."""
    def __init__(self, ledger=None):
        self.ledger = ledger

    pin = staticmethod(engine.pin)
    scan = staticmethod(driver._artifacts)

    @staticmethod
    def read(binding, *, binary=False):
        return checked(binding) if binary else engine.read(binding)

    @staticmethod
    def pair(path):
        binding = engine.read(engine.pin(path.with_suffix('.binding.json')))
        if binding['path'] != str(path):
            raise ValueError('Synthetic historical seal path differs')
        return engine.read(binding)


class RejectionPrefixContracts(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.attempt = self.root/'attempt'
        self.attempt.mkdir()
        self.reader = BoundReader()
        self.sources = {}
        for name in (history.DRIVER, 'tools/earnings_population_loop.py',
                     'tools/earnings_population_run.py', 'tools/earnings_population_services.py'):
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            if name == history.DRIVER:
                path.write_bytes(Path(driver.__file__).read_bytes())
                self.sources[name] = engine.pin(path)
            else:
                self.sources[name] = engine.save(path, {'synthetic_source_identity': name})
        self.initial = engine.save(self.root/'initial.json', {'synthetic_population': True})
        self.runtime = {'companies': ['CIK0000021076'], 'initial_population': self.initial,
                        'sources': self.sources}
        self.seed = {'population': engine.read(self.initial), 'companies': self.runtime['companies'],
                     'feedback': {'synthetic_unscored_seed': True}}
        self.handlers = {stage: (lambda ctx, stage=stage: {'synthetic_stage': stage}) for stage in driver.STAGES}
        self.handlers['source_review'] = lambda ctx: {'accepted_for_exploration': False, 'evidence': []}
        common = {'adapter': self.sources['tools/earnings_population_loop.py'],
                  'admission': {'function': 'execute.<locals>.admit',
                                'module': self.sources['tools/earnings_population_run.py']},
                  'services': {role: {'function': 'Services.'+role,
                                     'module': self.sources['tools/earnings_population_services.py']}
                               for role in ('controller', 'author', 'review', 'forecast')}}
        self.identity = {stage: dict(common, stage=stage) for stage in driver.STAGES}

    def build(self, *, finish=False):
        result = driver.run(self.attempt/'loop', self.handlers, seed=self.seed,
                            admit=lambda ctx: finish or ctx['stage'] != 'execute',
                            max_rounds=1, handler_identity=lambda: self.identity)
        self.assertEqual(result['status'], 'completed' if finish else 'stopped')

    def load_prefix(self):
        return rejection._prefix(self.reader, self.runtime, self.attempt)

    def test_exact_four_sealed_stages_transfer_without_execute_claim_or_bytes_mutation(self):
        self.build()
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        seed, outputs, evidence = self.load_prefix()
        self.assertEqual(seed, self.seed)
        self.assertEqual(list(outputs), list(rejection.STAGES))
        self.assertFalse(outputs['source_review']['accepted_for_exploration'])
        self.assertEqual(len(evidence), 5)
        self.assertFalse((self.attempt/'loop/round-0001-execute.claim.json').exists())
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_missing_or_changed_stage_seal_is_not_a_transferable_rejection(self):
        self.build()
        path = self.attempt/'loop/round-0001-source_review.done.binding.json'
        path.rename(path.with_name('preserved-seal.json'))
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.load_prefix()

    def test_execute_claim_or_completed_execution_is_not_four_stage_rejection(self):
        self.build()
        engine.save(self.attempt/'loop/round-0001-execute.claim.json', {'synthetic': 'execution uncertainty'})
        with self.assertRaises(ValueError):
            self.load_prefix()

    def test_full_completed_journal_is_not_misclassified_as_review_rejection(self):
        self.build(finish=True)
        with self.assertRaises(ValueError):
            self.load_prefix()

    def test_wrong_pool_or_source_handler_binding_is_rejected(self):
        self.build()
        for field, replacement in (('initial_population', engine.save(self.root/'foreign-pool.json', {'foreign_pool': True})),
                                    ('sources', dict(self.sources, **{
                                        'tools/earnings_population_loop.py': self.sources['tools/earnings_population_run.py']}))):
            runtime = dict(self.runtime, **{field: replacement})
            with self.subTest(field=field), self.assertRaises(ValueError):
                rejection._prefix(self.reader, runtime, self.attempt)


class RejectionLedgerContracts(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.ledger = self.root/'synthetic-budget.sqlite3'
        self.attempt = self.root/'attempt'
        self.reader = BoundReader(self.ledger)
        with sqlite3.connect(self.ledger) as db:
            db.execute('CREATE TABLE config (id INTEGER PRIMARY KEY,cap INTEGER,model_cap INTEGER)')
            db.execute('INSERT INTO config VALUES(1,200000000000,100000000000)')
            db.execute('CREATE TABLE requests (id TEXT,model TEXT,reserved INTEGER,charged INTEGER,status TEXT)')
            self.opening = history_snapshot(db)
            for index in range(24):
                request_id = f'synthetic-own-{index:02d}'
                db.execute('INSERT INTO requests VALUES(?,?,?,?,?)',
                           (request_id, 'gpt-6.1-sol', 100, 100, 'settled'))
                path = self.attempt/'roles'/f'role-{index:02d}'/'01-request.json'
                path.parent.mkdir(parents=True)
                engine.save(path, {'request_id': request_id})
        self.runtime = {'baseline': self.opening}
        self.update_audit()
        self.baseline_patch = patch.object(history, 'EXTRA_BASELINE', deepcopy(self.opening))
        self.baseline_patch.start()
        self.addCleanup(self.baseline_patch.stop)

    def update_audit(self):
        with sqlite3.connect(self.ledger) as db:
            closed = history_snapshot(db, 24)
        self.audit = {'accounting': {'closing_rows': 24, 'closing_rows_sha256': closed['rows_sha256'],
                                    'closing_charged': closed['charged_nano_usd'],
                                    'own_charge': closed['charged_nano_usd']}}
        self.owner = {'budget_summary': {'charged_upper_bound_usd': closed['charged_nano_usd']/1e9}}

    def load_ledger(self):
        return rejection._ledger(self.reader, self.runtime, self.owner, self.audit, self.attempt)

    def test_exact_24_settled_requests_read_only_and_unrelated_later_settled_rows_do_not_replace_them(self):
        before = self.ledger.read_bytes()
        self.assertIsNone(self.load_ledger())
        self.assertEqual(self.ledger.read_bytes(), before)
        with sqlite3.connect(self.ledger) as db:
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?)', ('synthetic-later', 'gpt-6.1-sol', 1, 1, 'settled'))
        self.assertIsNone(self.load_ledger())

    def test_own_unknown_request_fee_hard_stops_even_with_recomputed_fixture_closing_hash(self):
        with sqlite3.connect(self.ledger) as db:
            db.execute("UPDATE requests SET status='reserved' WHERE id='synthetic-own-00'")
        self.update_audit()
        with self.assertRaises(ValueError):
            self.load_ledger()

    def test_prefix_charge_drift_or_request_set_substitution_is_rejected(self):
        with sqlite3.connect(self.ledger) as db:
            db.execute("UPDATE requests SET charged=99 WHERE id='synthetic-own-00'")
        with self.assertRaises(ValueError):
            self.load_ledger()
        self.update_audit()
        path = self.attempt/'roles/role-00/01-request.json'
        path.write_text('{"request_id":"synthetic-foreign-id"}')
        with self.assertRaises(ValueError):
            self.load_ledger()


class RejectionProbeContracts(unittest.TestCase):
    def setUp(self):
        self.fixture = public_fixture.PopulationCaseTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        native = tempfile.TemporaryDirectory(prefix='market-rsi-test-rejection-', dir='/private/tmp')
        self.addCleanup(native.cleanup)
        self.native = Path(native.name).resolve()
        self.ident = self.native.name.removeprefix('market-rsi-')
        self.ident_patch = patch.object(rejection, 'IDENT', self.ident)
        self.ident_patch.start()
        self.addCleanup(self.ident_patch.stop)
        self.reader, self.company = BoundReader(), self.fixture.resident['company']
        self.source = Path(self.fixture.r['path']).read_text()
        self.candidate = {'R': self.fixture.r}
        self.reviewed = {'evidence': []}
        self.runners = []

    def probes(self, *, payload_changes=None, coverage_changes=None):
        for stage in ('forecast', 'controller'):
            tools = FilingTools(self.company)
            filing = next(path for path in tools.files if path.startswith('filings/'))
            payload = {'stage': stage, 'questions': tools.files['questions.md'],
                       'filing_index': tools.files['filing_index.tsv'], 'records': []}
            payload.update(payload_changes or {})
            rows = [{'tool': 'search_files', 'arguments': {'query': 'revenue', 'path_prefix': filing,
                                                          'max_hits': 6}} for _ in range(8)]
            coverage = {'accepted_searches': 8, 'accepted_reads': 0, 'failed_requests': 0,
                        'extracted_cells': 0, 'facts': 0}
            coverage.update(coverage_changes or {})
            value = {'coverage': coverage, 'targets': [
                {'target_id': f'T{i:03d}', 'status': 'incomplete',
                 'failure_reasons': ['missing_source_hash_or_character_offset']} for i in range(1, 6)]}
            runner = receipt_fixture.ScriptedReceiptRunner(self.fixture.root/f'probe-runner-{stage}',
                                                           [{'research_requests': rows}, value])
            self.runners.append(runner)
            execution = researcher.run(runner, self.source, payload, tools)
            self.reviewed['evidence'].append(engine.save(self.native/f'review-01-{stage}-probe.json',
                {'input': payload, 'execution': execution, 'scope': 'Explicit synthetic no execution probe'}))

    def test_real_verifier_preserves_successful_searches_zero_cells_and_exact_reasons(self):
        self.probes()
        result, questions = rejection._probes(self.reader, self.reviewed, self.candidate, self.company)
        self.assertEqual(questions, FilingTools(self.company).files['questions.md'])
        self.assertEqual([row['stage'] for row in result], ['forecast', 'controller'])
        for row in result:
            self.assertEqual(row['coverage']['accepted_searches'], 8)
            self.assertEqual(row['coverage']['failed_requests'], 0)
            self.assertEqual(row['coverage']['extracted_cells'], 0)
            self.assertEqual(row['incomplete_targets'], 5)
            self.assertEqual(row['reason_codes'], ['missing_source_hash_or_character_offset'])
            self.assertEqual(row['source_sha256'], self.fixture.r['sha256'])
        self.assertEqual([runner.calls for runner in self.runners], [2, 2])
        self.assertFalse(self.fixture.marker.exists())

    def test_missing_probe_and_foreign_or_duplicate_binding_cannot_transfer(self):
        self.probes()
        for evidence in (self.reviewed['evidence'][:1], [*self.reviewed['evidence'], self.reviewed['evidence'][0]]):
            with self.subTest(count=len(evidence)), self.assertRaises(ValueError):
                rejection._probes(self.reader, {'evidence': evidence}, self.candidate, self.company)

    def test_wrong_public_questions_or_nonempty_state_is_not_old_failure_probe(self):
        self.probes(payload_changes={'records': [{'not_original': True}]})
        with self.assertRaises(ValueError):
            rejection._probes(self.reader, self.reviewed, self.candidate, self.company)

    def test_candidate_source_drift_is_rejected_by_original_execution_verifier(self):
        self.probes()
        other = engine.save(self.fixture.root/'other-source.py', {'synthetic': 'different source'})
        with self.assertRaises(ValueError):
            rejection._probes(self.reader, self.reviewed, {'R': other}, self.company)


class RejectionOuterOwnershipContracts(unittest.TestCase):
    def test_foreign_failure_or_scope_is_rejected_before_reader_or_accounting(self):
        bad = {'path': '/private/tmp/synthetic-foreign/population-run-failure.json', 'sha256': 'f'*64}
        with patch.object(history, '_Reader', side_effect=AssertionError('must not read foreign artifact')):
            with self.assertRaises(ValueError):
                rejection.load_closed_review_rejection(bad, root=rejection.OWNED,
                                                       ledger=rejection.LEDGER, repo=rejection.REPO)
            with self.assertRaises(ValueError):
                rejection.load_closed_review_rejection(bad, root=Path('/private/tmp/synthetic-owned'),
                                                       ledger=rejection.LEDGER, repo=rejection.REPO)

    def test_uncertain_owner_or_own_unresolved_fee_stops_before_history_prefix_or_scoring(self):
        for change in ('pending', 'blocked', 'running', 'wrong-error', 'retry'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
                home = Path(temporary).resolve()
                root, repo, ledger = home/'owned', home/'repo', home/'pilot/synthetic-ledger.sqlite3'
                repo.mkdir()
                ident = 'synthetic-rejection-'+home.name
                attempt = root/'attempts'/ident
                attempt.mkdir(parents=True)
                inputs = root/'inputs'/ident
                inputs.mkdir(parents=True)
                failure = engine.save(attempt/'population-run-failure.json', dict(
                    status='FAILED_NO_RETRY', error_type='ValueError', native_closure=None, retry_allowed=False))
                runtime = engine.save(inputs/'runtime.json', dict(
                    schema='earnings_population_runtime_v1', id=ident, root=str(attempt), ledger=str(ledger),
                    source_commit=rejection.COMMIT, companies=[rejection.VALIDATION],
                    baseline={'rows_sha256': 'b'*64}))
                registry = ledger.parent/'.capacity-runtime-claims'
                registry.mkdir(parents=True)
                token = hashlib.sha256(ident.encode()).hexdigest()
                engine.save(registry/(token+'.json'), {'id': ident, 'runtime': runtime,
                    'source_commit': rejection.COMMIT, 'retry_allowed': False})
                budget = {'blocked': False, 'unresolved_reserved_usd': 0, 'cap_usd': 200,
                          'model_cap_usd': 100, 'night_cap_usd': 5, 'prior_history_sha256': 'b'*64}
                owner = {'status': 'FAILED_NO_RETRY', 'error_type': 'ValueError', 'retry_allowed': False,
                         'runtime': runtime, 'budget_summary': budget}
                if change == 'pending': budget['unresolved_reserved_usd'] = 0.1
                elif change == 'blocked': budget['blocked'] = True
                elif change == 'running': owner['status'] = 'RUNNING'
                elif change == 'wrong-error': owner['error_type'] = 'TimeoutError'
                elif change == 'retry': owner['retry_allowed'] = True
                owner_bound = engine.save(registry/(token+'.result.json'), owner)
                audit = engine.save(root/'synthetic-audit.json', {
                    'verdict': 'PASS_AUDITED_REJECTION_AND_FAILURE_CLOSURE_NO_FORECAST',
                    'native_and_execution_closure': {'owner_terminal_receipt_sha256': owner_bound['sha256']}})
                for key, value in (('OWNED', root), ('REPO', repo), ('LEDGER', ledger), ('IDENT', ident),
                                   ('AUDIT', audit), ('FAILURE_SHA', failure['sha256']), ('RUNTIME_SHA', runtime['sha256'])):
                    stack.enter_context(patch.object(rejection, key, value))
                for name in ('_prefix', '_ledger', '_closures', '_probes'):
                    stack.enter_context(patch.object(rejection, name,
                        side_effect=AssertionError('uncertain owner must not reach heavy '+name)))
                stack.enter_context(patch.object(history, '_load',
                    side_effect=AssertionError('uncertain owner must not inherit prior state')))
                with self.assertRaises(ValueError):
                    rejection.load_closed_review_rejection(failure, root=root, ledger=ledger, repo=repo)

    def test_generic_completed_loader_still_rejects_failed_result_without_promoting_rejection(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            home = Path(temporary).resolve()
            root, repo, ledger = home/'owned', home/'repo', home/'pilot/synthetic-ledger.sqlite3'
            repo.mkdir()
            path = root/'attempts/edgar-population-20261016-02/population-run-result.json'
            path.parent.mkdir(parents=True)
            failure = engine.save(path, {'status': 'FAILED_NO_RETRY', 'error_type': 'ValueError', 'retry_allowed': False})
            for key, value in (('OWNED', root), ('REPO', repo), ('LEDGER', ledger)):
                stack.enter_context(patch.object(history, key, value))
            with self.assertRaisesRegex(ValueError, 'Failed/incomplete'):
                history.load(failure, root=root, ledger=ledger, repo=repo)


if __name__ == '__main__':
    unittest.main()
