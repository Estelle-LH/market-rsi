"""Synthetic accounting fixtures only; never open the production ledger.

Git/authority blobs and the audited prefix are deliberately fixture-bound. These
tests prove budget mechanics, not independent review or activation permission.
"""
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import earnings_population_budget as b
from edgar_forecast_budget import BudgetStop, PilotBudget
from edgar_forecast_full_budget import FullBudget
from earnings_night_budget import NightBudget, history_snapshot, utc_epoch

MODEL = 'gpt-6.1-sol'
COMMIT = 'a' * 40
DEADLINE = '2026-10-18T00:00:00Z'
NANO = 1_000_000_000


class PopulationBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.path = self.root/'sole.sqlite3'
        self.lock = self.root/'.capacity-runtime.lock'
        self.lock.touch(mode=0o600)
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.addCleanup(self.db.close)
        self.db.executescript('''
            CREATE TABLE config(id INTEGER PRIMARY KEY,cap INTEGER,model_cap INTEGER,blocked INTEGER);
            CREATE TABLE requests(id TEXT PRIMARY KEY,model TEXT,reserved INTEGER,charged INTEGER,status TEXT);
            CREATE TABLE reconciliations(request_id TEXT PRIMARY KEY,evidence_sha256 TEXT NOT NULL,
                prior_status TEXT NOT NULL,prior_charge INTEGER NOT NULL,ceiling INTEGER NOT NULL,
                policy TEXT NOT NULL,recorded_utc TEXT);
        ''')
        self.db.execute('INSERT INTO config VALUES(1,?,?,0)', (b.OLD_CAP, b.FULL_MODEL_CAP))
        self.db.execute("INSERT INTO requests VALUES('prior',?,?,?,'settled')", (MODEL, 5*NANO, 3*NANO))
        self.db.execute("INSERT INTO requests VALUES('prior-unknown','historical-model',?,?, 'settled_upper_bound')", (NANO, NANO))
        self.db.execute("INSERT INTO reconciliations VALUES('prior-unknown',?,'uncertain',0,?,'operator_full_ceiling_actual_charge_unknown','fixed-fixture-time')", ('c'*64, NANO))
        self.initial = history_snapshot(self.db)
        self.saved_requests = self.db.execute('SELECT rowid,* FROM requests').fetchall()
        self.saved_reconciliations = self.db.execute('SELECT rowid,* FROM reconciliations').fetchall()
        self.implementation = Path(b.__file__).read_bytes()
        self.plan = dict(schema='supervisor_bottleneck_plan_v1', id=b.GRANT,
            human_authorization=b.AUTHORIZATION, budget_authority=dict(grant_id=b.GRANT,
                sole_ledger=str(self.path), old_cap_nano_usd=b.OLD_CAP,
                new_cap_nano_usd=b.CAP, model_cap_nano_usd=b.FULL_MODEL_CAP))
        self.authority = self.root/b.PLAN
        self.authority.parent.mkdir(parents=True)
        self.authority.write_bytes(b._encoded(self.plan)+b'\n')
        self.authority_raw = self.authority.read_bytes()
        self.bound = dict(path=str(self.authority), sha256=hashlib.sha256(self.authority_raw).hexdigest())
        for name, value in [('LEDGER', self.path), ('REPO', self.root), ('ORIGINAL_PREFIX', self.initial)]:
            p = patch.object(b, name, value)
            p.start()
            self.addCleanup(p.stop)
        git_patch = patch.object(b, '_git', side_effect=self.git_blob)
        self.git = git_patch.start()
        self.addCleanup(git_patch.stop)
        self.wall = utc_epoch(DEADLINE)-1000
        self.mono = 10

    def git_blob(self, commit, name):
        self.assertEqual(commit, COMMIT)
        if name == b.PLAN:
            return self.authority_raw
        self.assertEqual(name, 'tools/earnings_population_budget.py')
        return self.implementation

    def activate(self, **changes):
        kwargs = dict(authority_binding=self.bound, source_commit=COMMIT,
                      expected_prefix=history_snapshot(self.db))
        kwargs.update(changes)
        return b.activate(self.path, **kwargs)

    def open(self, **changes):
        kwargs = dict(amendment_binding=b.amendment_binding(), baseline=history_snapshot(self.db),
            deadline_utc=DEADLINE, clock=lambda: self.wall, monotonic=lambda: self.mono,
            additional_cap_nano_usd=5*NANO)
        kwargs.update(changes)
        budget = b.PopulationBudget(self.path, **kwargs)
        self.addCleanup(budget.close)
        return budget

    def assert_unactivated(self):
        self.assertEqual(self.db.execute('SELECT cap,model_cap,blocked FROM config').fetchone(), (b.OLD_CAP, b.FULL_MODEL_CAP, 0))
        self.assertFalse((self.root/b.NAME).exists())
        self.assertFalse(self.db.execute("SELECT 1 FROM sqlite_master WHERE name='population_budget_amendments'").fetchone())

    def test_old_cap_validation_is_read_only_and_legacy_defaults_unchanged(self):
        before = self.db.total_changes
        self.assertEqual(b.validate_cap(self.db), b.OLD_CAP)
        self.assertEqual(before, self.db.total_changes)
        self.assert_unactivated()
        old = FullBudget(self.path)
        self.addCleanup(old.close)
        self.assertEqual(old.summary()['cap_usd'], 200)
        self.assertEqual(old.summary()['model_cap_usd'], 100)
        self.assertEqual(PilotBudget.RECONCILIATION_MODEL_CAP, 10*NANO)

    def test_atomic_activation_preserves_every_prior_row_and_records_authority(self):
        binding = self.activate()
        self.assertEqual(b.validate_cap(self.db, amendment=binding), b.CAP)
        self.assertEqual(self.db.execute('SELECT rowid,* FROM requests').fetchall(), self.saved_requests)
        self.assertEqual(self.db.execute('SELECT rowid,* FROM reconciliations').fetchall(), self.saved_reconciliations)
        grant = json.loads((self.root/b.NAME).read_bytes())
        self.assertEqual(grant['authority'], self.bound)
        self.assertEqual(grant['prefix'], self.initial)
        self.assertEqual(grant['source_commit'], COMMIT)
        self.assertEqual(grant['implementation_sha256'], hashlib.sha256(self.implementation).hexdigest())
        self.assertEqual((self.root/b.NAME).stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM population_budget_amendments').fetchone()[0], 1)
        with self.assertRaises(BudgetStop):
            self.activate()
        with self.assertRaises(BudgetStop):
            FullBudget(self.path)
        with self.assertRaises(BudgetStop):
            NightBudget(self.path, baseline=self.initial, deadline_utc=DEADLINE, clock=lambda: self.wall)

    def test_activation_accepts_new_settled_rows_but_keeps_audited_original_anchor(self):
        self.db.execute("INSERT INTO requests VALUES('later',?,?,?,'settled')", (MODEL, NANO, NANO))
        self.activate()
        self.assertEqual(b.validate_cap(self.db), b.CAP)
        self.db.execute("UPDATE requests SET charged=0 WHERE id='prior'")
        with self.assertRaises(BudgetStop):
            b.validate_cap(self.db)

    def test_existing_refund_cannot_be_legitimized_by_new_expected_prefix(self):
        self.db.execute("UPDATE requests SET charged=0 WHERE id='prior'")
        with self.assertRaises(BudgetStop):
            self.activate()
        self.assert_unactivated()

    def test_wrong_expected_prefix_and_boolean_fields_stop_before_write(self):
        for value in [dict(self.initial, charged_nano_usd=0), dict(self.initial, max_rowid=True)]:
            with self.subTest(value=value), self.assertRaises(BudgetStop):
                self.activate(expected_prefix=value)
            self.assert_unactivated()

    def test_pending_and_blocked_stop_without_grant(self):
        self.db.execute("INSERT INTO requests VALUES('pending',?,1,0,'reserved')", (MODEL,))
        with self.assertRaises(BudgetStop):
            self.activate()
        self.db.execute("DELETE FROM requests WHERE id='pending'")  # synthetic fixture only
        self.db.execute('UPDATE config SET blocked=1')
        with self.assertRaises(BudgetStop):
            self.activate()
        self.assertFalse((self.root/b.NAME).exists())

    def test_missing_or_occupied_shared_lock_prevents_writes(self):
        with self.lock.open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.activate()
        self.lock.unlink()  # synthetic fixture only
        with self.assertRaises(BudgetStop):
            self.activate()
        self.assert_unactivated()

    def test_wrong_authority_text_caps_source_and_model_cap_rejected(self):
        original = self.authority_raw
        for mutate in [lambda p: p.update(human_authorization='not a human grant'),
                       lambda p: p['budget_authority'].update(new_cap_nano_usd=500*NANO),
                       lambda p: p['budget_authority'].update(sole_ledger='/another.sqlite3')]:
            p = deepcopy(self.plan)
            mutate(p)
            self.authority_raw = b._encoded(p)+b'\n'
            self.authority.write_bytes(self.authority_raw)
            bad = dict(path=str(self.authority), sha256=hashlib.sha256(self.authority_raw).hexdigest())
            with self.assertRaises(ValueError):
                self.activate(authority_binding=bad)
            self.assert_unactivated()
        self.authority_raw = original
        self.authority.write_bytes(original)
        with self.assertRaises(ValueError):
            self.activate(authority_binding=dict(self.bound, sha256='0'*64))
        self.implementation = b'different committed implementation'
        with self.assertRaises(ValueError):
            self.activate()
        self.implementation = Path(b.__file__).read_bytes()
        self.db.execute('UPDATE config SET model_cap=?', (10*NANO,))
        with self.assertRaises(BudgetStop):
            self.activate()

    def test_current_checkout_authority_required_at_activation_not_afterward(self):
        self.authority.write_bytes(b'changed current plan')
        with self.assertRaises(ValueError):
            self.activate()
        self.authority.write_bytes(self.authority_raw)
        self.activate()
        self.authority.write_bytes(b'changed later metadata')
        self.assertEqual(b.validate_cap(self.db), b.CAP)  # exact historical Git blob retained

    def test_prior_overcharge_invalid_integer_and_model_liability_rejected(self):
        for reserved, charged in [(1, 2), (0, 0), (1, -1), (1, 0.5), (101*NANO, 101*NANO)]:
            with self.subTest(reserved=reserved, charged=charged):
                self.db.execute("INSERT INTO requests VALUES('bad','legacy',?,?,'settled')", (reserved, charged))
                with self.assertRaises(BudgetStop):
                    self.activate()
                self.db.execute("DELETE FROM requests WHERE id='bad'")  # synthetic fixture only
                self.assert_unactivated()

    def test_prior_global_liability_cannot_be_erased_by_larger_cap(self):
        for i in range(3):
            self.db.execute("INSERT INTO requests VALUES(?,?,?,?,'settled')", (f'legacy{i}', f'legacy-model{i}', 70*NANO, 70*NANO))
        with self.assertRaises(BudgetStop):
            self.activate()
        self.assert_unactivated()

    def test_interrupted_activation_rolls_back_sql_and_preserves_orphan_file(self):
        original = b.validate_cap
        def fail_after_update(db, **kwargs):
            if db.execute('SELECT cap FROM config').fetchone()[0] == b.CAP:
                raise BudgetStop('synthetic post-write interruption')
            return original(db, **kwargs)
        with patch.object(b, 'validate_cap', side_effect=fail_after_update), self.assertRaises(BudgetStop):
            self.activate()
        self.assertTrue((self.root/b.NAME).is_file())
        self.assertEqual(self.db.execute('SELECT cap FROM config').fetchone()[0], b.OLD_CAP)
        self.assertFalse(self.db.execute("SELECT 1 FROM sqlite_master WHERE name='population_budget_amendments'").fetchone())
        for action in [lambda: b.validate_cap(self.db), self.activate]:
            with self.assertRaises(BudgetStop):
                action()
        self.assertEqual(self.db.execute('SELECT rowid,* FROM requests').fetchall(), self.saved_requests)

    def test_400_without_grant_and_wrong_runtime_binding_are_rejected(self):
        self.db.execute('UPDATE config SET cap=?', (b.CAP,))
        with self.assertRaises(BudgetStop):
            b.validate_cap(self.db)
        self.db.execute('UPDATE config SET cap=?', (b.OLD_CAP,))
        binding = self.activate()
        with self.assertRaises(BudgetStop):
            b.validate_cap(self.db, amendment=dict(binding, sha256='0'*64))
        for bad in [None, {}, dict(binding, path='/another-grant.json')]:
            with self.assertRaises(ValueError):
                self.open(amendment_binding=bad)

    def test_receipt_row_reconciliation_and_source_corruption_fail_closed(self):
        binding = self.activate()
        path = self.root/b.NAME
        saved = path.read_bytes()
        path.write_bytes(saved+b' ')
        with self.assertRaises(BudgetStop):
            b.validate_cap(self.db)
        path.write_bytes(saved)
        self.db.execute("UPDATE population_budget_amendments SET receipt_sha256='wrong'")
        with self.assertRaises(BudgetStop):
            b.validate_cap(self.db)
        self.db.execute('UPDATE population_budget_amendments SET receipt_sha256=?', (binding['sha256'],))
        self.db.execute("UPDATE reconciliations SET policy='refund'")
        with self.assertRaises(BudgetStop):
            b.validate_cap(self.db)
        self.db.execute("UPDATE reconciliations SET policy='operator_full_ceiling_actual_charge_unknown'")
        self.implementation = b'wrong historic source'
        with self.assertRaises(BudgetStop):
            b.validate_cap(self.db)

    def test_foreign_attached_and_symlink_ledger_are_rejected(self):
        foreign = sqlite3.connect(self.root/'foreign.sqlite3', isolation_level=None)
        self.addCleanup(foreign.close)
        with self.assertRaises(BudgetStop):
            b.validate_cap(foreign)
        self.db.execute('ATTACH DATABASE ? AS other', (str(self.root/'other.sqlite3'),))
        with self.assertRaises(BudgetStop):
            b.validate_cap(self.db)
        self.db.execute('DETACH DATABASE other')
        alias = self.root/'alias.sqlite3'
        alias.symlink_to(self.path)
        with self.assertRaises(ValueError):
            b.activate(alias, authority_binding=self.bound, source_commit=COMMIT, expected_prefix=self.initial)

    def test_reserve_check_settle_and_summary_preserve_total_history(self):
        self.activate()
        budget = self.open()
        budget.reserve('new', MODEL, NANO)
        budget.check_reserved('new', MODEL, NANO)
        with self.assertRaises(BudgetStop):
            budget.check_reserved('wrong', MODEL, NANO)
        with self.assertRaises(BudgetStop):
            self.open()
        budget.settle('new', NANO//2)
        result = budget.summary()
        self.assertEqual((result['cap_usd'], result['model_cap_usd']), (400, 100))
        self.assertEqual(result['charged_upper_bound_usd'], 4.5)
        self.assertEqual(result['night_charged_upper_bound_usd'], 0.5)
        self.assertEqual(result['night_cap_usd'], 5)
        self.assertEqual(result['prior_history_sha256'], self.initial['rows_sha256'])
        with self.assertRaises(BudgetStop):
            budget.reserve('new', MODEL, 1)
        with self.assertRaises(BudgetStop):
            budget.reconcile_uncertain_at_ceiling('new', 'a'*64)

    def test_new_owner_can_cross_old200_while_model100_remains(self):
        # Fixture legacy models exercise cumulative accounting, not new model admission.
        self.db.execute("INSERT INTO requests VALUES('large1','legacy1',?,?, 'settled')", (98*NANO, 98*NANO))
        self.db.execute("INSERT INTO requests VALUES('large2','legacy2',?,?, 'settled')", (97*NANO, 97*NANO))
        self.activate()  # original cumulative199, including original4
        budget = self.open()
        budget.reserve('cross200', MODEL, 2*NANO)
        budget.check_reserved('cross200', MODEL, 2*NANO)
        budget.settle('cross200', 2*NANO)
        self.assertEqual(budget.summary()['charged_upper_bound_usd'], 201)
        self.db.execute("INSERT INTO requests VALUES('model-near',?,?,?, 'settled')", (MODEL, 95*NANO, 95*NANO))
        model_budget = self.open()
        with self.assertRaises(BudgetStop):
            model_budget.reserve('model-over100', MODEL, 1)

    def test_global400_and_window_allowance_are_independent(self):
        self.activate()
        for i in range(4):
            self.db.execute("INSERT INTO requests VALUES(?,?,?,?,'settled')", (f'post{i}', f'post-model{i}', 98*NANO, 98*NANO))
        # Synthetic post-grant rows isolate global boundary, each model stays below100.
        budget = self.open(additional_cap_nano_usd=5*NANO)
        budget.reserve('to400', MODEL, 4*NANO)
        budget.check_reserved('to400', MODEL, 4*NANO)
        budget.settle('to400', 4*NANO)
        self.assertEqual(budget.summary()['charged_upper_bound_usd'], 400)
        with self.assertRaises(BudgetStop):
            budget.reserve('over400', MODEL, 1)

    def test_tranche_boundary_and_new_role_preserve_spend(self):
        self.activate()
        budget = self.open(additional_cap_nano_usd=NANO)
        budget.reserve('first', MODEL, NANO)
        budget.settle('first', NANO)
        with self.assertRaises(BudgetStop):
            budget.reserve('overtranche', MODEL, 1)
        other = self.open(baseline=self.initial, additional_cap_nano_usd=NANO)
        with self.assertRaises(BudgetStop):
            other.reserve('other-role', MODEL, 1)

    def test_deadline_wall_rollback_history_and_invalid_values_still_stop(self):
        self.activate()
        budget = self.open(captured_deadline=self.mono+10)
        self.wall -= 3600
        self.mono += 11
        with self.assertRaises(BudgetStop):
            budget.reserve('late', MODEL, 1)
        for amount in [True, 0, -1, 20*NANO+1]:
            with self.assertRaises(ValueError):
                self.open(additional_cap_nano_usd=amount)
        for method in [budget.reserve, budget.check_reserved]:
            for values in [('', MODEL, 1), ('new', 'unapproved', 1), ('new', MODEL, True)]:
                with self.assertRaises(ValueError):
                    method(*values)

    def test_uncertain_and_overcharge_remain_blocked_without_refund_or_retry(self):
        self.activate()
        budget = self.open()
        budget.reserve('unknown', MODEL, 10)
        budget.uncertain('unknown')
        with self.assertRaises(BudgetStop):
            budget.reserve('retry', MODEL, 1)
        with self.assertRaises(BudgetStop):
            budget.reconcile_uncertain_at_ceiling('unknown', 'a'*64)
        self.assertEqual(self.db.execute("SELECT reserved,charged,status FROM requests WHERE id='unknown'").fetchone(), (10, 0, 'uncertain'))

    def test_observed_overcharge_is_preserved_and_stops(self):
        self.activate()
        budget = self.open()
        budget.reserve('overcharge', MODEL, 10)
        with self.assertRaises(BudgetStop):
            budget.settle('overcharge', 11)
        self.assertEqual(self.db.execute("SELECT charged,status FROM requests WHERE id='overcharge'").fetchone(), (11, 'settled'))
        self.assertEqual(self.db.execute('SELECT blocked FROM config').fetchone(), (1,))
        self.assertEqual(budget.summary()['charged_upper_bound_usd'], 4+11/NANO)
        self.assertTrue(budget.summary()['blocked'])
        with self.assertRaises(BudgetStop):
            budget.reserve('retry', MODEL, 1)

    def test_after_deadline_settle_and_uncertain_record_fees_but_never_dispatch(self):
        self.activate()
        budget = self.open()
        budget.reserve('late-finish', MODEL, 10)
        self.wall = utc_epoch(DEADLINE)
        budget.settle('late-finish', 7)
        self.assertEqual(budget.summary()['charged_upper_bound_usd'], 4+7/NANO)
        with self.assertRaises(BudgetStop):
            budget.reserve('late-dispatch', MODEL, 1)
        self.wall -= 100
        budget.reserve('late-unknown', MODEL, 10)
        self.wall = utc_epoch(DEADLINE)
        budget.uncertain('late-unknown')
        self.assertTrue(budget.summary()['blocked'])
        self.assertEqual(budget.summary()['unresolved_reserved_usd'], 10/NANO)
        with self.assertRaises(BudgetStop):
            budget.check_reserved('late-unknown', MODEL, 10)


if __name__ == '__main__':
    unittest.main()
