"""Independent closed03 contracts on inert receipt/accounting fixtures.

No paid role, candidate execution, Docker, scorer or production ledger/Git is
used. Fixture SQLite is temporary. Scope/closure/accounting helpers run without
admission mocks; any top-level loader seams are explicitly named below.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import earnings_population_campaign_resume as resume
import earnings_population_continuation as history
import earnings_population_budget as budget
from edgar_forecast_budget import BudgetStop
from earnings_entry import checked
from earnings_night_budget import history_snapshot
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_researcher as execution_fixture


class BoundReader:
    """Byte binding only; not historical Git, resident data or paid authority."""
    def __init__(self, ledger=None):
        self.ledger = ledger

    pin = staticmethod(engine.pin)

    @staticmethod
    def read(binding, *, binary=False):
        return checked(binding) if binary else engine.read(binding)


class ResumeScopeContracts(unittest.TestCase):
    def test_foreign_result_hash_id_and_roots_fail_before_any_reader(self):
        exact = {'path': str(resume.OWNED/'attempts'/resume.IDENT/'population-run-result.json'),
                 'sha256': resume.RESULT_SHA}
        cases = [
            (dict(exact, path='/private/tmp/foreign/population-run-result.json'), {}),
            (dict(exact, sha256='0'*64), {}),
            (dict(exact, path=exact['path'].replace('-03/', '-04/')), {}),
            (dict(exact, path=exact['path'].replace('/attempts/', '/attempts/../attempts/')), {}),
            (exact, {'root': Path('/private/tmp/foreign-owned')}),
            (exact, {'ledger': Path('/private/tmp/foreign-ledger.sqlite3')}),
            (exact, {'repo': Path('/private/tmp/foreign-repo')}),
        ]
        with patch.object(history, '_Reader', side_effect=AssertionError('No unsafe history read')):
            for binding, changes in cases:
                args = dict(root=resume.OWNED, ledger=resume.LEDGER, repo=resume.REPO)
                args.update(changes)
                with self.subTest(changes=changes, binding=binding), self.assertRaises(ValueError):
                    resume.load(binding, **args)

    def test_known_closed_binding_is_not_a_generic_future_or_failed_run_loader(self):
        self.assertEqual(resume.IDENT, 'edgar-population-20261016-03')
        self.assertEqual(resume.RESULT_SHA, '44007cfe42a424c18b844c09ca97c52da008dcabb3acc9b1216b46866d0781ee')
        self.assertNotEqual(resume.RESULT_SHA, resume.rejection.FAILURE_SHA)

    def test_resume_explicitly_requests_sealed_history_before_any_resident_or_reader(self):
        class StoppedAtDeclaredOrigin(Exception):
            pass
        exact = {'path': str(resume.OWNED/'attempts'/resume.IDENT/'population-run-result.json'),
                 'sha256': resume.RESULT_SHA}
        with patch.object(resume.rejection, 'load_closed_review_rejection',
                          side_effect=StoppedAtDeclaredOrigin) as origin, \
             patch.object(history, '_Reader', side_effect=AssertionError('No reader before sealed origin')), \
             patch.object(resume.tasks, 'resident', side_effect=AssertionError('No resident read before sealed origin')):
            with self.assertRaises(StoppedAtDeclaredOrigin):
                resume.load(exact, root=resume.OWNED, ledger=resume.LEDGER, repo=resume.REPO)
        self.assertTrue(origin.call_args.kwargs['sealed_history'])
        self.assertEqual(origin.call_args.kwargs['root'], resume.OWNED)

    def test_missing_hash_or_wrong_result_filename_is_rejected_before_origin(self):
        exact = {'path': str(resume.OWNED/'attempts'/resume.IDENT/'population-run-result.json'),
                 'sha256': resume.RESULT_SHA}
        with patch.object(resume.rejection, 'load_closed_review_rejection',
                          side_effect=AssertionError('Invalid binding must not inherit origin')):
            for bad in ({'path': exact['path']}, dict(exact, path=exact['path'].replace('result.json', 'failure.json'))):
                with self.subTest(binding=bad), self.assertRaises(ValueError):
                    resume.load(bad, root=resume.OWNED, ledger=resume.LEDGER, repo=resume.REPO)


class ResumeLedgerContracts(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.ledger = self.root/'synthetic-only.sqlite3'
        self.attempt = self.root/'attempt'
        self.reader = BoundReader(self.ledger)
        with sqlite3.connect(self.ledger) as db:
            db.execute('CREATE TABLE config (id INTEGER PRIMARY KEY,cap INTEGER,model_cap INTEGER,blocked INTEGER)')
            db.execute('INSERT INTO config VALUES(1,200000000000,100000000000,0)')
            db.execute('CREATE TABLE requests (id TEXT,model TEXT,reserved INTEGER,charged INTEGER,status TEXT)')
            db.executemany('INSERT INTO requests VALUES(?,?,?,?,?)',
                [(f'synthetic-prior-{i:04d}', 'gpt-6.1-sol', 100, 100, 'settled') for i in range(5776)])
            self.extra = history_snapshot(db, 4283)
            self.runtime = {'baseline': history_snapshot(db, 5776)}
            for index in range(24):
                request_id = f'synthetic-own-{index:02d}'
                charge = 1000000 if index < 23 else 544187400
                db.execute('INSERT INTO requests VALUES(?,?,?,?,?)',
                           (request_id, 'gpt-6.1-sol', charge, charge, 'settled'))
                path = self.attempt/'roles'/f'role-{index:02d}'/'01-request.json'
                path.parent.mkdir(parents=True)
                engine.save(path, {'request_id': request_id})
        self.update_audit()
        p = patch.object(history, 'EXTRA_BASELINE', deepcopy(self.extra))
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(budget, 'LEDGER', self.ledger)
        p.start()
        self.addCleanup(p.stop)

    def update_audit(self):
        with sqlite3.connect(self.ledger) as db:
            closed = history_snapshot(db, 5800)
            charge = db.execute('SELECT SUM(charged) FROM requests WHERE rowid>5776 AND rowid<=5800').fetchone()[0]
        self.audit = {'accounting': dict(closing_rows=5800, closing_rows_sha256=closed['rows_sha256'],
            closing_charged_nano_usd=closed['charged_nano_usd'], total_own_charge_nano_usd=charge)}
        self.owner = {'budget_summary': {'charged_upper_bound_usd': closed['charged_nano_usd']/1e9,
            'cap_usd': 200, 'model_cap_usd': 100, 'night_cap_usd': 5}}

    def load(self):
        return resume._ledger(self.reader, self.runtime, self.owner, self.audit, self.attempt)

    def test_exact_own24_settled_rows_are_verified_without_mutating_temporary_ledger(self):
        before = self.ledger.read_bytes()
        self.assertIsNone(self.load())
        self.assertEqual(before, self.ledger.read_bytes())

    def test_later_unrelated_rows_do_not_replace_or_reopen_old03(self):
        with sqlite3.connect(self.ledger) as db:
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?)',
                       ('synthetic-later-unrelated', 'gpt-6.1-sol', 17, 0, 'reserved'))
        # Historical closure only. Fresh launch must independently require idle
        # and pending=0; this helper must not grant that permission.
        self.assertIsNone(self.load())

    def test_own_unsettled_or_wrong_model_rows_fail_even_if_fixture_audit_rehashed(self):
        for field, value in [('status', 'reserved'), ('status', 'settled_upper_bound'),
                             ('model', 'synthetic-other-model')]:
            with self.subTest(field=field, value=value):
                with sqlite3.connect(self.ledger) as db:
                    db.execute(f'UPDATE requests SET {field}=? WHERE id=?', (value, 'synthetic-own-00'))
                self.update_audit()
                with self.assertRaises(ValueError):
                    self.load()
                with sqlite3.connect(self.ledger) as db:
                    db.execute("UPDATE requests SET model='gpt-6.1-sol',status='settled' WHERE id='synthetic-own-00'")
                self.update_audit()

    def test_charge_drift_is_rejected_even_when_fixture_closing_hash_is_recomputed(self):
        with sqlite3.connect(self.ledger) as db:
            db.execute("UPDATE requests SET charged=999999 WHERE id='synthetic-own-00'")
        self.update_audit()
        with self.assertRaises((ValueError, BudgetStop)):
            self.load()

    def test_cap_or_historical_prefix_change_is_rejected(self):
        with sqlite3.connect(self.ledger) as db:
            db.execute('UPDATE config SET cap=400000000000')
        with self.assertRaises((ValueError, BudgetStop)):
            self.load()
        with sqlite3.connect(self.ledger) as db:
            db.execute('UPDATE config SET cap=200000000000')
            db.execute("UPDATE requests SET charged=101 WHERE id='synthetic-prior-0000'")
        with self.assertRaises(ValueError):
            self.load()

    def test_current_400_requires_declared_validator_seam_and_keeps_old_summary_unchanged(self):
        with sqlite3.connect(self.ledger) as db:
            db.execute('UPDATE config SET cap=400000000000')
        before, old_summary = self.ledger.read_bytes(), deepcopy(self.owner['budget_summary'])
        # Explicit grant-validation seam only: grant authenticity is covered by
        # the separate budget suite. Old prefix/own24 settlement checks stay real.
        with patch.object(budget, 'validate_cap', return_value=400000000000) as validator:
            self.assertIsNone(self.load())
        validator.assert_called_once()
        self.assertEqual(self.owner['budget_summary'], old_summary)
        self.assertEqual(self.owner['budget_summary']['cap_usd'], 200)
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_wrong_or_duplicate_request_identity_cannot_use_other_settled_rows(self):
        path = self.attempt/'roles/role-00/01-request.json'
        original = path.read_bytes()
        for request_id in ('synthetic-foreign-id', 'synthetic-own-01'):
            path.write_text(json.dumps({'request_id': request_id}))
            with self.subTest(request_id=request_id), self.assertRaises(ValueError):
                self.load()
        path.write_bytes(original)
        self.assertIsNone(self.load())


class ResumeExecutionClosureContracts(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.attempt, self.native = self.root/'attempt', self.root/'native'
        self.reader = BoundReader()
        # Actual original receipt verifier is NOT used to execute this code.
        # ScriptedReceiptRunner merely writes explicit synthetic JSON originals.
        runner = execution_fixture.ScriptedReceiptRunner(self.attempt/'code', [{}]*10)
        self.receipts = [runner.run("PROGRAM={'axis':'R'}\ndef run(p): return {}\n", {'fixture': i})['receipt']
                         for i in range(10)]
        batches = {}
        for role in ('controller-01', 'author-01', 'review-01'):
            path = self.native/role/'batch/batch.json'
            path.parent.mkdir(parents=True)
            batches[role] = engine.save(path, {'synthetic': True, 'role': role})['sha256']
        self.audit = {'execution_and_native_closure': dict(
            code_receipt_manifest_sha256=digest(self.receipts), native_batch_sha256=batches)}

    def load(self):
        return resume._closure(self.reader, self.attempt, self.native, self.audit)

    def test_exact_ten_original_receipts_and_three_batches_are_read_only(self):
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(len(self.load()), 13)
        self.assertEqual(before, {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()})

    def test_changed_stdout_source_or_missing_receipt_refuses_transfer(self):
        original = Path(self.receipts[0]['path']).parent/'stdout.bin'
        original.write_bytes(b'{"ok":true,"value":{"tampered":true}}')
        with self.assertRaises(ValueError):
            self.load()

    def test_missing_execution_or_changed_native_batch_is_not_closed(self):
        path = Path(self.receipts[0]['path'])
        data = path.read_bytes()
        path.unlink()
        with self.assertRaises(ValueError):
            self.load()
        path.write_bytes(data)
        batch = self.native/'author-01/batch/batch.json'
        batch.write_text('{"synthetic":"changed"}')
        with self.assertRaises(ValueError):
            self.load()

    def test_uncertain_cleanup_status_or_host_execution_is_refused(self):
        path = Path(self.receipts[0]['path'])
        original = engine.read(self.receipts[0])
        for field, value in [('status', 'FAILED_NO_RETRY'), ('cleanup_verified', False),
                             ('host_candidate_execution', True), ('exit_code', 1)]:
            path.write_text(json.dumps(dict(original, **{field: value})))
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.load()


class ResumeHistoricalSourceContracts(unittest.TestCase):
    """Real shared Reader; historical Git bytes are explicit inert fixtures."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.root, self.repo = self.home/'owned', self.home/'repo'
        self.path = self.repo/'tools/historical.py'
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b'# prospective current source, not historical\n')
        self.old = b'# exact historical fixture bytes\n'
        self.bound = {'path': str(self.path), 'sha256': hashlib.sha256(self.old).hexdigest()}
        self.reader = history._Reader(self.root, self.home/'synthetic-ledger.sqlite3', self.repo,
                                      'edgar-population-20261016-03')
        self.reader.commit = 'a'*40
        self.reader.sources = {(self.bound['path'], self.bound['sha256'])}

    def test_old_source_is_checked_against_historical_bytes_not_prospective_current_file(self):
        with patch.object(history, '_git', return_value=self.old) as historical_git:
            self.assertEqual(self.reader.read(self.bound, binary=True), self.old)
        historical_git.assert_called_once_with(self.repo, 'a'*40, 'tools/historical.py')

    def test_changed_historical_source_bytes_are_rejected(self):
        with patch.object(history, '_git', return_value=self.old+b'# changed'):
            with self.assertRaisesRegex(ValueError, 'hash differs'):
                self.reader.read(self.bound, binary=True)

    def test_unregistered_source_is_rejected_before_historical_git_or_file_read(self):
        bad = dict(self.bound, path=str(self.repo/'tools/unregistered.py'))
        with patch.object(history, '_git', side_effect=AssertionError('No unregistered source read')):
            with self.assertRaisesRegex(ValueError, 'Unregistered historical'):
                self.reader.read(bad, binary=True)

    def test_foreign_qa_path_is_refused_before_bytes_and_exact_registered_qa_stays_opaque(self):
        path = self.home/'foreign/forecast_benchmark_qa.json'
        path.parent.mkdir()
        opaque = b'synthetic opaque label fixture, deliberately invalid JSON'
        path.write_bytes(opaque)
        bound = engine.pin(path)
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Foreign bytes must not be read')):
            with self.assertRaisesRegex(ValueError, 'outside exact owned roots'):
                self.reader.read(bound, binary=True)
        self.reader.extra.add(path)
        with patch.object(history.e, 'strict_json', side_effect=AssertionError('Opaque bytes must not be decoded')):
            self.assertEqual(self.reader.read(bound, binary=True), opaque)


if __name__ == '__main__':
    unittest.main()
