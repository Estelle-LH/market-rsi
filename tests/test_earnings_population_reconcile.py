"""Inert temporary accounting fixtures; no real ledger or provider calls."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import earnings_population_reconcile as m
from earnings_night_budget import history_snapshot
from edgar_forecast_budget import BudgetStop


class Conservative400Operator(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.tmp = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.root, self.ledger = self.tmp/'edgar-population-20261016', self.tmp/'pilot-01/api-budget.sqlite3'
        self.ledger.parent.mkdir(); (self.ledger.parent/'.capacity-runtime.lock').touch()
        self.stack.enter_context(patch.object(m, 'ROOT', self.root))
        self.stack.enter_context(patch.object(m.authority, 'LEDGER', self.ledger))
        # The explicit grant-verifier seam is inert; production never skips it.
        self.grant = self.stack.enter_context(patch.object(m.authority, 'validate_cap', return_value=m.authority.CAP))
        self.db = sqlite3.connect(self.ledger, isolation_level=None)
        self.addCleanup(self.db.close)
        self.db.executescript('CREATE TABLE config(id INTEGER,cap INTEGER,model_cap INTEGER,blocked INTEGER);'
            'CREATE TABLE requests(id TEXT PRIMARY KEY,model TEXT,reserved INTEGER,charged INTEGER,status TEXT);'
            'CREATE TABLE reconciliations(request_id TEXT PRIMARY KEY,evidence_sha256 TEXT,prior_status TEXT,prior_charge INTEGER,ceiling INTEGER,policy TEXT,recorded_utc TEXT DEFAULT CURRENT_TIMESTAMP);')
        self.db.execute('INSERT INTO config VALUES(1,400000000000,100000000000,1)')
        self.db.executemany('INSERT INTO requests VALUES(?,?,?,?,?)', [
            ('old-other', 'gpt-5.5-2026-04-23', 100000000000,100000000000,'settled'),
            ('old-same', 'gpt-6.1-sol',64000000000,64000000000,'settled'),
            ('known', 'gpt-6.1-sol',221252100,221252100,'settled'),
            ('uncertain', 'gpt-6.1-sol',581900000,0,'uncertain')])
        self.runtime = dict(id='edgar-population-20261016-99',root=str(self.root/'attempts/edgar-population-20261016-99'),
            ledger=str(self.ledger),baseline=dict(charged_nano_usd=164000000000),additional_cap_nano_usd=5000000000,
            budget_amendment={'path':'synthetic-grant-only','sha256':'a'*64},slots={})
        self.request = dict(request_id='uncertain',reserved_nano_usd=581900000,payload=dict(model='gpt-6.1-sol'))
        self.proof = dict(ledger_before=history_snapshot(self.db),_binding=dict(path='synthetic-evidence-only',sha256='b'*64))

    def refresh(self):
        self.proof['ledger_before'] = history_snapshot(self.db)

    def book(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            result = m._book(self.db,self.proof,self.runtime,self.request)
            self.db.execute('COMMIT'); return result
        except BaseException:
            self.db.execute('ROLLBACK'); raise

    def save(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True)
        raw=json.dumps(value,sort_keys=True,indent=2).encode(); path.write_bytes(raw)
        return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())

    def evidence(self):
        ident=self.runtime['id']; slot=Path(self.runtime['root'])/'roles/author-01'
        self.runtime['slots']={'author':[str(slot)]}
        runtime=self.save(self.root/'inputs'/ident/'runtime-reviewed.json',self.runtime)
        owner=self.save(self.ledger.parent/'.capacity-runtime-claims'/(hashlib.sha256(ident.encode()).hexdigest()+'.result.json'),
            dict(runtime=runtime,status='FAILED_NO_RETRY',retry_allowed=False,error_type='LoopHalted',
                budget_summary=dict(blocked=True,cap_usd=400,model_cap_usd=100,unresolved_reserved_usd=.5819,
                    charged_upper_bound_usd=self.proof['ledger_before']['charged_nano_usd']/1e9,
                    generation_requests_reserved=self.proof['ledger_before']['request_count'])))
        request=self.save(slot/'08-request.json',self.request)
        stem='http-00000000-0000-0000-0000-000000000001'
        intent=self.save(slot/(stem+'.intent.json'),dict(endpoint='/v1/responses',complete_reservation=self.request,
            request_receipt_sha256=request['sha256'],budget_request_id='uncertain',retry_allowed=False))
        failure=self.save(slot/(stem+'.failed.json'),dict(exception_type='BudgetStop',retry_allowed=False))
        return self.save(self.root/('FEE-EVIDENCE-'+ident+'.json'),dict(schema='earnings_population_fee_evidence_v1',
            id=ident,runtime=runtime,owner_result=owner,request=request,http_intent=intent,http_failure=failure,
            ledger_before=self.proof['ledger_before'],actual_charge_known=False,retry_allowed=False))

    def test_book_entire_reservation_preserves_every_old_row_and_caps(self):
        before=self.db.execute('SELECT * FROM requests WHERE id!=?',('uncertain',)).fetchall()
        result=self.book()
        self.assertEqual(self.db.execute('SELECT * FROM requests WHERE id!=?',('uncertain',)).fetchall(),before)
        self.assertEqual(self.db.execute('SELECT charged,status FROM requests WHERE id=?',('uncertain',)).fetchone(),(581900000,'settled_upper_bound'))
        self.assertEqual(result['after']['charged_nano_usd']-result['before']['charged_nano_usd'],581900000)
        self.assertIs(result['actual_charge_known'],False);self.assertEqual(result['refund_nano_usd'],0)
        self.assertEqual(self.db.execute('SELECT cap,model_cap,blocked FROM config').fetchone(),(400000000000,100000000000,0))
        self.assertEqual(self.db.execute('SELECT policy FROM reconciliations').fetchone()[0],'operator_full_ceiling_actual_charge_unknown')
        self.grant.assert_called_once_with(self.db,amendment=self.runtime['budget_amendment'])
        with self.assertRaises(BudgetStop):self.book()

    def test_original_locked_wrapper_and_real_fixture_receipt_joins(self):
        result=m.reconcile_at_ceiling(self.evidence())
        self.assertEqual(result['conservative_charge_nano_usd'],581900000)
        self.assertFalse(result['actual_charge_known'])

    def test_foreign_evidence_refused_before_any_read(self):
        with patch.object(m,'_read',side_effect=AssertionError('must not read')):
            with self.assertRaises(ValueError):m.inspect_evidence(dict(path='/foreign/FEE.json',sha256='a'*64))

    def test_received_response_or_mutated_receipt_refuses_unknown_fee_path(self):
        bound=self.evidence(); value=json.loads(Path(bound['path']).read_text())
        request=Path(value['request']['path']); response=request.with_name('08-response.json'); response.touch()
        with self.assertRaises(ValueError):m.inspect_evidence(bound)
        response.unlink()
        Path(value['http_failure']['path']).write_text('{}')
        with self.assertRaises(ValueError):m.inspect_evidence(bound)

    def test_changed_prefix_never_overwrites_new_activity(self):
        self.db.execute('UPDATE requests SET charged=charged-1 WHERE id=?',('known',))
        with self.assertRaises(BudgetStop):self.book()
        self.assertEqual(self.db.execute('SELECT charged FROM requests WHERE id=?',('uncertain',)).fetchone(),(0,))

    def test_other_pending_or_known_overcharge_stays_blocked(self):
        self.db.execute("INSERT INTO requests VALUES('foreign','gpt-6.1-sol',1,0,'reserved')");self.refresh()
        with self.assertRaises(BudgetStop):self.book()
        self.db.execute("DELETE FROM requests WHERE id='foreign'")
        self.db.execute("UPDATE requests SET charged=reserved+1 WHERE id='known'");self.refresh()
        with self.assertRaises(BudgetStop):self.book()
        self.assertEqual(self.db.execute('SELECT blocked FROM config').fetchone(),(1,))

    def test_wrong_caps_status_charge_or_duplicate_reconciliation_refused(self):
        for query in ("UPDATE config SET cap=200000000000", "UPDATE config SET blocked=0",
                      "UPDATE requests SET status='reserved' WHERE id='uncertain'",
                      "UPDATE requests SET charged=1 WHERE id='uncertain'",
                      "INSERT INTO reconciliations(request_id) VALUES('uncertain')"):
            with self.subTest(query=query):
                self.db.execute('SAVEPOINT variant');self.db.execute(query);self.refresh()
                with self.assertRaises(BudgetStop):m._book(self.db,self.proof,self.runtime,self.request)
                self.db.execute('ROLLBACK TO variant');self.db.execute('RELEASE variant');self.refresh()

    def test_full_global_model_and_window_liability_checked(self):
        for query in ("UPDATE requests SET reserved=335500000000,charged=335500000000 WHERE id='old-other'",
                      "UPDATE requests SET reserved=99900000000,charged=99900000000 WHERE id='old-same'"):
            with self.subTest(query=query):
                self.db.execute('SAVEPOINT variant');self.db.execute(query);self.refresh()
                with self.assertRaises(BudgetStop):m._book(self.db,self.proof,self.runtime,self.request)
                self.db.execute('ROLLBACK TO variant');self.db.execute('RELEASE variant');self.refresh()
        self.runtime['additional_cap_nano_usd']=500000000
        with self.assertRaises(BudgetStop):self.book()


if __name__=='__main__':unittest.main()
