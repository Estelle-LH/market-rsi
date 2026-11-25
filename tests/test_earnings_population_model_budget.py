"""Staged only. Temporary SQLite/grants; committed Git/old400 proof are fixtures.

Real new authority/grant/activation/liability/PopulationBudget code executes;
no production ledger, operator, API, original company/QA or active source write.
"""
from contextlib import ExitStack, closing
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import unittest
from unittest.mock import patch

import earnings_population_budget as p
import earnings_population_model_budget as m
from earnings_night_budget import history_snapshot

G = 1_000_000_000


class Fixture:
    def __init__(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory(prefix='model300-staged-')
        self.root = Path(self.temp.name).resolve()
        self.stack = ExitStack()
        self.ledger = self.root/'sole.sqlite3'
        self.repo = self.root/'repo'
        (self.repo/Path(m.PLAN).parent).mkdir(parents=True)
        (self.root/'.capacity-runtime.lock').touch(mode=0o600)
        self.patch(p, 'LEDGER', self.ledger)
        self.patch(p, 'REPO', self.repo)
        # Original cumulative400 verifier itself is NOT under test here. Its
        # immutable original grant is represented by unchanged fixture bytes.
        self.patch(p, 'validate_cap', lambda db, amendment=None:p.CAP)
        self.old_grant = self.root/p.NAME
        self.old_grant.write_bytes(b'{"old_model_cap":100,"fixture":true}\n')
        self.old_grant.chmod(0o600)
        self.old_bytes = self.old_grant.read_bytes()
        with sqlite3.connect(self.ledger) as db:
            db.executescript('CREATE TABLE config(id INTEGER PRIMARY KEY,cap INTEGER,model_cap INTEGER,blocked INTEGER);'
                'CREATE TABLE requests(id TEXT PRIMARY KEY,model TEXT,reserved INTEGER,charged INTEGER,status TEXT);'
                'CREATE TABLE reconciliations(request_id TEXT PRIMARY KEY,evidence_sha256 TEXT,prior_status TEXT,prior_charge INTEGER,ceiling INTEGER,policy TEXT);'
                'INSERT INTO config VALUES(1,400000000000,100000000000,0);')
            for ident, model, amount in [('gpt-prior',m.MODEL,79_944_786_300),('other-a',p.MODELS[0],70*G),('other-b',p.MODELS[1],37_485_174_500)]:
                db.execute('INSERT INTO requests VALUES(?,?,?, ?,?)',(ident,model,amount,amount,'settled'))
            db.execute('INSERT INTO reconciliations VALUES(?,?,?,?,?,?)',('old-reconc','fixture-sha','uncertain',0,1,'old-policy'))
            self.stage = history_snapshot(db)
        # Exactly disclosed synthetic prefix seam: three invented rows stand
        # for original6401. Real production STAGE constant is checked separately.
        self.patch(m, 'STAGE', self.stage)
        self.authority = dict(schema='edgar_train25_specific_model_cap_authority_v1', direct_human_answer=m.ANSWER,
            status='AUTHORIZED_NOT_ACTIVATED_STAGING_ONLY',
            model=m.MODEL, old_model_cap_nano_usd=m.OLD,new_model_cap_nano_usd=m.NAMED,
            other_models_cap_nano_usd=m.OLD,stage_additional_ceiling_nano_usd=m.STAGE_CAP,
            cumulative_cap_nano_usd=p.CAP,window_ceiling_nano_usd=m.WINDOW_CAP,
            stage_start_rows=self.stage['request_count'],stage_start_booked_nano_usd=self.stage['charged_nano_usd'],
            stage_start_prefix_sha256=self.stage['rows_sha256'],sole_ledger=str(self.ledger),
            no_global_model_cap_raise=True,no_refund_reset_new_ledger_or_inference_budget=True,
            preserve_historical100_grants_receipts=True,explicit_prospective_runtime_optin_required=True,
            heldout_authorization=False,other_Supervisor_access=False)
        self.commit='a'*40
        self.authority_file=self.repo/m.PLAN
        self.write_authority()
        def git(commit,name):
            if commit!=self.commit:raise ValueError('Unknown fixture commit')
            if name==m.PLAN:return self.authority_file.read_bytes()
            if name==m.IMPLEMENTATIONS[0]:return Path(m.__file__).read_bytes()
            if name==m.IMPLEMENTATIONS[1]:return Path(p.__file__).read_bytes()
            raise ValueError('Unknown fixture Git source')
        self.patch(p,'_git',git)

    def patch(self,obj,key,value):return self.stack.enter_context(patch.object(obj,key,value))
    def close(self):self.stack.close();self.temp.cleanup()
    def write_authority(self):
        self.authority_file.write_bytes(p._encoded(self.authority))
        self.auth=p._pin(self.authority_file)
    def snapshot(self):
        with sqlite3.connect(self.ledger) as db:return history_snapshot(db)
    def activate(self):
        return m.activate(self.ledger,authority_binding=self.auth,source_commit=self.commit,expected_prefix=self.snapshot())
    def insert(self,ident,model,amount,*,pending=False):
        with sqlite3.connect(self.ledger) as db:
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?)',(ident,model,amount,0 if pending else amount,'reserved' if pending else 'settled'))
    def budget(self,*,optin=False,amount=5*G,seconds=3000):
        return p.PopulationBudget(self.ledger,amendment_binding=p.amendment_binding(),
            model_amendment_binding=m.binding() if optin else None,baseline=self.snapshot(),
            deadline_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(time.time()+seconds)),
            additional_cap_nano_usd=amount)


class ModelBudgetTests(unittest.TestCase):
    def setUp(self):self.f=Fixture();self.addCleanup(self.f.close)

    def test_production_stage_contract_literal(self):
        # Fixture changes only our module variable; source literal stays actual.
        text=Path(m.__file__).read_text()
        self.assertIn('max_rowid=6401, request_count=6401, charged_nano_usd=187429960800',text)
        self.assertIn('0c343c36c21c496b7f6263ba4ec9afb8ffb5dcb347b0e4195e63349112ce252a',text)

    def test_legacy_no_grant_same_dispatch_and_summary(self):
        with closing(self.f.budget()) as b:
            b.reserve('legacy',m.MODEL,G);b.check_reserved('legacy',m.MODEL,G);b.settle('legacy',1)
            self.assertEqual(b.summary()['model_cap_usd'],100)
            self.assertNotIn('model_budget_optin',b.summary())

    def test_activation_preserves_config_oldgrant_history_once(self):
        before=self.f.snapshot();bound=self.f.activate()
        self.assertEqual(before,self.f.snapshot());self.assertEqual(self.f.old_bytes,self.f.old_grant.read_bytes())
        with sqlite3.connect(self.f.ledger) as db:
            self.assertEqual(db.execute('SELECT cap,model_cap,blocked FROM config').fetchone(),(400*G,100*G,0))
            self.assertEqual(m.read_grant(db,required_binding=bound)['model'],m.MODEL)
        with self.assertRaises(Exception):self.f.activate()

    def test_old100_dispatch_and_new300_liabilities_are_distinct(self):
        self.f.activate();self.f.insert('authorized-history',m.MODEL,22*G)
        with closing(self.f.budget()) as legacy:
            legacy.active()  # Valid existing named-model liability is not fraud.
            with self.assertRaises(p.BudgetStop):legacy.reserve('old-dispatch',m.MODEL,1)
        with closing(self.f.budget(optin=True)) as new:
            new.reserve('new-dispatch',m.MODEL,G);new.check_reserved('new-dispatch',m.MODEL,G)
            new.check_reserved('new-dispatch',m.MODEL,G)  # No double-count of own reservation.
            with self.assertRaises(p.BudgetStop):new.reserve('second',m.MODEL,1)
            new.settle('new-dispatch',G)
            self.assertEqual(new.summary()['model_cap_usd'],100)
            self.assertEqual(new.summary()['dispatch_model_caps_usd'],{m.MODEL:300,'other_models':100})

    def test_other_model_remains100(self):
        self.f.activate();self.f.insert('other-near100',p.MODELS[0],29*G)
        with closing(self.f.budget(optin=True)) as b:
            with self.assertRaises(p.BudgetStop):b.reserve('other-too-high',p.MODELS[0],2*G)

    def test_stage200_and_full_pending_liability(self):
        self.f.activate();self.f.insert('stage199',m.MODEL,199*G)
        with closing(self.f.budget(optin=True)) as b:
            with self.assertRaisesRegex(p.BudgetStop,'stage200'):b.reserve('stage201',m.MODEL,2*G)
        self.f.insert('pending2',m.MODEL,2*G,pending=True)
        with sqlite3.connect(self.f.ledger) as db:
            with self.assertRaisesRegex(p.BudgetStop,'stage200'):m.dispatch_totals(db,m.MODEL,0,m.binding())

    def test_window5_90minutes_and_exact_optin(self):
        self.f.activate()
        for amount,seconds in [(5*G+1,3000),(G,5402),(G,-1)]:
            with self.subTest(amount=amount,seconds=seconds),self.assertRaises(ValueError):self.f.budget(optin=True,amount=amount,seconds=seconds)
        with closing(self.f.budget(optin=True)) as b:
            with self.assertRaises(p.BudgetStop):b.reserve('window-excess',m.MODEL,5*G+1)
        with sqlite3.connect(self.f.ledger) as db:
            for optin in (None,{},dict(path=str(self.f.root/'foreign'),sha256='a'*64)):
                with self.assertRaises(p.BudgetStop):m.dispatch_totals(db,m.MODEL,1,optin)

    def test_cumulative_and_named_model_liabilities_refuse(self):
        self.f.activate();self.f.insert('total-over400',m.MODEL,213*G)
        with sqlite3.connect(self.f.ledger) as db:
            with self.assertRaises(p.BudgetStop):m.authorized_liabilities(db,p.CAP)
        with sqlite3.connect(self.f.ledger) as db:
            db.execute("DELETE FROM requests WHERE id='total-over400'")
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?)',('named-over300',m.MODEL,221*G,221*G,'settled'))
            # At this fixed fixture prefix, other models already cost107.49;
            # a named300 violation necessarily also violates cumulative400.
            with self.assertRaises(p.BudgetStop):m.authorized_liabilities(db,p.CAP)
            # Isolate the subordinate named-model check with an explicitly
            # synthetic liability projection, not a rewritten historical row.
            with patch.object(m,'_totals',lambda db:(399*G,{m.MODEL:301*G,p.MODELS[0]:98*G})):
                with self.assertRaises(p.BudgetStop):m.authorized_liabilities(db,p.CAP)

    def test_authority_typed_only_target_and_source_bound(self):
        for key,value in [('new_model_cap_nano_usd',300000000000.0),('model',p.MODELS[0]),('other_models_cap_nano_usd',300*G),('direct_human_answer','different'),('status','REVOKED')]:
            old=deepcopy(self.f.authority);self.f.authority[key]=value;self.f.write_authority()
            with self.subTest(key=key),self.assertRaises(ValueError):self.f.activate()
            self.f.authority=old;self.f.write_authority()
        with patch.object(p,'_git',lambda *a:b'wrong'),self.assertRaises(ValueError):self.f.activate()

    def test_pending_lock_and_wrong_oldcap_prevent_activation(self):
        self.f.insert('pending',m.MODEL,1,pending=True)
        with self.assertRaises(p.BudgetStop):self.f.activate()
        with sqlite3.connect(self.f.ledger) as db:db.execute("DELETE FROM requests WHERE id='pending'")
        with (self.f.root/'.capacity-runtime.lock').open('rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):self.f.activate()
        with patch.object(p,'validate_cap',lambda *a,**k:200*G),self.assertRaises(p.BudgetStop):self.f.activate()
        self.assertFalse((self.f.root/m.NAME).exists())

    def test_prepared_file_interrupt_blocks_without_repair(self):
        original=m.save_bytes
        def stopped(path,raw):original(path,raw);raise RuntimeError('fixture interrupt after file')
        with patch.object(m,'save_bytes',stopped),self.assertRaises(RuntimeError):self.f.activate()
        self.assertTrue((self.f.root/m.NAME).exists())
        with self.assertRaises(p.BudgetStop):self.f.activate()
        with sqlite3.connect(self.f.ledger) as db:self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(m.TABLE,)).fetchone())

    def test_tamper_file_sql_prefix_reconciliation_and_link_refuse(self):
        bound=self.f.activate();path=self.f.root/m.NAME;raw=path.read_bytes()
        path.write_bytes(raw+b' ')
        with sqlite3.connect(self.f.ledger) as db,self.assertRaises(p.BudgetStop):m.read_grant(db)
        path.write_bytes(raw)
        with sqlite3.connect(self.f.ledger) as db:
            db.execute("UPDATE requests SET charged=charged-1 WHERE id='gpt-prior'")
            with self.assertRaises(p.BudgetStop):m.read_grant(db)
            db.execute("UPDATE requests SET charged=charged+1 WHERE id='gpt-prior'")
            db.execute("UPDATE reconciliations SET policy='changed'")
            with self.assertRaises(p.BudgetStop):m.read_grant(db)
        self.assertEqual(self.f.old_grant.read_bytes(),self.f.old_bytes)

    def test_foreign_sql_receipt_and_typed_prefix_refuse(self):
        self.f.activate();path=self.f.root/m.NAME;raw=path.read_bytes()
        with sqlite3.connect(self.f.ledger) as db:
            db.execute('UPDATE '+m.TABLE+' SET receipt_sha256=?',('0'*64,))
            with self.assertRaises(p.BudgetStop):m.read_grant(db)
            db.execute('UPDATE '+m.TABLE+' SET receipt_sha256=?',(hashlib.sha256(raw).hexdigest(),))
            value=json.loads(raw);value['reconciliations']['max_rowid']=float(value['reconciliations']['max_rowid'])
            altered=p._encoded(value)+b'\n';path.write_bytes(altered)
            db.execute('UPDATE '+m.TABLE+' SET receipt_sha256=?,record_json=?',(hashlib.sha256(altered).hexdigest(),altered.decode()))
            with self.assertRaises(p.BudgetStop):m.read_grant(db)

    def test_aliased_or_missing_grant_refuses_even_legacy(self):
        self.f.activate();path=self.f.root/m.NAME;raw=path.read_bytes()
        path.unlink();path.symlink_to(self.f.root/'absent')
        with sqlite3.connect(self.f.ledger) as db,self.assertRaises(p.BudgetStop):m.read_grant(db)
        path.unlink();target=self.f.root/'alias-target';target.write_bytes(raw);target.chmod(0o600);path.symlink_to(target)
        with sqlite3.connect(self.f.ledger) as db,self.assertRaises(p.BudgetStop):m.read_grant(db)
        path.unlink()
        with sqlite3.connect(self.f.ledger) as db,self.assertRaises(p.BudgetStop):m.read_grant(db)

    def test_exact_own_loan_and_request_no_retry(self):
        self.f.activate()
        with closing(self.f.budget(optin=True)) as b:
            b.reserve('own',m.MODEL,G)
            for request,model,amount in [('other',m.MODEL,G),('own',p.MODELS[0],G),('own',m.MODEL,G+1)]:
                with self.subTest(request=request,model=model,amount=amount),self.assertRaises(p.BudgetStop):
                    m.dispatch_totals(b.db,model,amount,m.binding(),own_request=request)
            b.settle('own',G)
            with self.assertRaises(p.BudgetStop):b.reserve('own',m.MODEL,G)
            for amount in (-1,True,0.1):
                with self.assertRaises(p.BudgetStop):m.dispatch_totals(b.db,m.MODEL,amount,m.binding())

    def test_sole_ledger_and_both_current_implementations_required(self):
        with self.assertRaises(ValueError):m.activate(self.f.root/'foreign.sqlite3',authority_binding=self.f.auth,source_commit=self.f.commit,expected_prefix=self.f.snapshot())
        git=p._git
        for module in m.IMPLEMENTATIONS:
            def altered(commit,name):return b'uncommitted' if name==module else git(commit,name)
            with self.subTest(module=module),patch.object(p,'_git',altered),self.assertRaises(ValueError):self.f.activate()
        self.assertFalse((self.f.root/m.NAME).exists())


if __name__=='__main__':unittest.main(verbosity=2)
