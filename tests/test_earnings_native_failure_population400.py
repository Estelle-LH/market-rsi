"""Synthetic population400 failure closure; no production ledger or execution.

The grant validator is an explicit unit seam; its real source/provenance checks
are covered separately by test_earnings_population_budget. Native closure uses
the original temporary journal fixture, never a provider, Docker or candidate.
"""
from copy import deepcopy
import hashlib
import unittest
from unittest.mock import patch

from edgar_forecast_budget import BudgetStop
import earnings_native_failure as failure
import earnings_population_budget as amendment_api
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_native_failure as original

CAP400 = 400_000_000_000


class Population400FailureClosure(unittest.TestCase):
    def fixture(self, *, population400=True):
        f = original.FailureFixture(self)
        if population400:
            f.db.execute('UPDATE config SET cap=?', (CAP400,))
            f.db.commit()
            f.runtime.update(schema='earnings_population_runtime_v1', budget_amendment={
                'path': str(f.home/'synthetic-cumulative400-grant.json'), 'sha256': 'd'*64})
        return f

    def ledger_bytes(self, f):
        return hashlib.sha256(f.ledger.read_bytes()).hexdigest()

    def test_legacy_exact200_path_never_uses_population_grant_validator(self):
        f = self.fixture(population400=False)
        before = self.ledger_bytes(f)
        with patch.object(amendment_api, 'validate_cap', side_effect=AssertionError('Legacy path unchanged')) as verify:
            rows = failure._owned_requests(f.runtime)
        verify.assert_not_called()
        self.assertEqual([r['request_id'] for r in rows], ['owned-one', 'owned-two'])
        self.assertEqual(sum(r['charged_nano_usd'] for r in rows), 1700)
        self.assertEqual(self.ledger_bytes(f), before)

    def test_explicit_population400_joins_exact_original_rows_read_only(self):
        f = self.fixture()
        before = self.ledger_bytes(f)
        original_rows = f.db.execute('SELECT * FROM requests ORDER BY id').fetchall()
        def validate(db, *, amendment):
            self.assertEqual(amendment, f.runtime['budget_amendment'])
            self.assertTrue(db.in_transaction)
            self.assertEqual(db.execute('PRAGMA database_list').fetchone()[2], str(f.ledger))
            return CAP400
        with patch.object(amendment_api, 'validate_cap', side_effect=validate) as verify:
            rows = failure._owned_requests(f.runtime)
        self.assertEqual(verify.call_count, 1)
        self.assertEqual([r['request_id'] for r in rows], ['owned-one', 'owned-two'])
        self.assertEqual([r['charged_nano_usd'] for r in rows], [700, 1000])
        self.assertEqual(f.db.execute('SELECT * FROM requests ORDER BY id').fetchall(), original_rows)
        self.assertEqual(self.ledger_bytes(f), before)

    def test_400_missing_or_malformed_explicit_binding_is_rejected_before_validator(self):
        f = self.fixture()
        for binding in (None, {}, 'pretend-grant', {'path': 'foreign'},
                        {'path': True, 'sha256': 'd'*64}, {'path': 'foreign', 'sha256': 'not-sha256'}):
            runtime = dict(f.runtime, budget_amendment=binding)
            with self.subTest(binding=binding), patch.object(amendment_api, 'validate_cap') as verify:
                with self.assertRaises(ValueError):
                    failure._owned_requests(runtime)
                verify.assert_not_called()
        runtime = deepcopy(f.runtime)
        runtime.pop('budget_amendment')
        with patch.object(amendment_api, 'validate_cap') as verify, self.assertRaises(ValueError):
            failure._owned_requests(runtime)
        verify.assert_not_called()

    def test_400_requires_exact_population_runtime_schema(self):
        f = self.fixture()
        for schema in ('earnings_capacity_runtime_v2', None, 'earnings_population_runtime_v2'):
            with self.subTest(schema=schema), patch.object(amendment_api, 'validate_cap') as verify:
                with self.assertRaises(ValueError):
                    failure._owned_requests(dict(f.runtime, schema=schema))
                verify.assert_not_called()

    def test_invalid_or_unactivated_grant_cannot_release_owned_work(self):
        f = self.fixture()
        before = self.ledger_bytes(f)
        for output in (200_000_000_000, None):
            with self.subTest(output=output), patch.object(amendment_api, 'validate_cap', return_value=output):
                with self.assertRaises(ValueError):
                    failure._owned_requests(f.runtime)
        with patch.object(amendment_api, 'validate_cap', side_effect=BudgetStop('Synthetic invalid grant')):
            with self.assertRaises(BudgetStop):
                failure._owned_requests(f.runtime)
        self.assertEqual(self.ledger_bytes(f), before)

    def test_blocked_wrong_model_cap_and_other_cap_rejected_before_validator(self):
        f = self.fixture()
        for cap, model, blocked in ((CAP400, 100_000_000_000, 1),
                                     (CAP400, 10_000_000_000, 0),
                                     (CAP400+1, 100_000_000_000, 0),
                                     (200_000_000_000, 100_000_000_000, 1)):
            f.db.execute('UPDATE config SET cap=?,model_cap=?,blocked=?', (cap, model, blocked))
            f.db.commit()
            before = self.ledger_bytes(f)
            with self.subTest(config=(cap, model, blocked)), patch.object(amendment_api, 'validate_cap') as verify:
                with self.assertRaises(ValueError):
                    failure._owned_requests(f.runtime)
                verify.assert_not_called()
            self.assertEqual(self.ledger_bytes(f), before)

    def test_pending_uncertain_and_changed_original_reservation_still_rejected(self):
        mutations = ["UPDATE requests SET status='reserved',charged=0 WHERE id='owned-one'",
                     "UPDATE requests SET status='uncertain',charged=0 WHERE id='owned-one'",
                     "UPDATE requests SET reserved=1001 WHERE id='owned-one'",
                     "UPDATE requests SET charged=1001 WHERE id='owned-one'",
                     "UPDATE requests SET charged=-1 WHERE id='owned-one'",
                     "UPDATE requests SET model='different-model' WHERE id='owned-one'",
                     "UPDATE requests SET charged=999 WHERE id='owned-two'",
                     "DELETE FROM requests WHERE id='owned-one'"]
        for mutation in mutations:
            f = self.fixture()
            f.db.execute(mutation)
            f.db.commit()
            before = self.ledger_bytes(f)
            with self.subTest(mutation=mutation), patch.object(amendment_api, 'validate_cap', return_value=CAP400):
                with self.assertRaises(ValueError):
                    failure._owned_requests(f.runtime)
            self.assertEqual(self.ledger_bytes(f), before)

    def test_duplicate_owned_request_receipts_are_not_new_credit(self):
        f = self.fixture()
        f.replace(f.slot/'02-request.json', engine.read(engine.pin(f.slot/'01-request.json')))
        with patch.object(amendment_api, 'validate_cap') as verify, self.assertRaises(ValueError):
            failure._owned_requests(f.runtime)
        verify.assert_not_called()

    def test_later_unrelated_rows_do_not_replace_owned_settlement_evidence(self):
        f = self.fixture()
        f.db.execute("INSERT INTO requests VALUES('later-unrelated','other-model',100,0,'reserved')")
        f.db.commit()
        before = self.ledger_bytes(f)
        with patch.object(amendment_api, 'validate_cap', return_value=CAP400):
            rows = failure._owned_requests(f.runtime)
        self.assertEqual([r['request_id'] for r in rows], ['owned-one', 'owned-two'])
        self.assertEqual(self.ledger_bytes(f), before)

    def test_whole_native_failure_closure_preserves_400_ledger_and_releases_only_own_claim(self):
        f = self.fixture()
        f.runtime_binding = engine.save(f.home/'runtime400.json', f.runtime)
        f.claim_value['runtime'] = f.runtime_binding
        f.terminal_value['runtime'] = f.runtime_binding
        f.replace(f.claim, f.claim_value)
        f.replace(f.terminal, f.terminal_value)
        before = f.batch.snapshot()
        ledger = self.ledger_bytes(f)
        with patch.object(amendment_api, 'validate_cap', return_value=CAP400) as verify:
            result = engine.read(f.close())
        self.assertEqual(verify.call_count, 1)
        self.assertEqual(result['status'], 'FAILED_WORK_CLOSED_NO_RETRY')
        self.assertEqual((result['own_request_count'], result['own_charge_nano_usd']), (2, 1700))
        self.assertFalse(result['candidate_adopted'])
        self.assertFalse(result['retry_allowed'])
        after = f.batch.snapshot()
        self.assertEqual(after['active_attempt_ids'], [])
        self.assertEqual(after['capacity_work'][-1]['status'], 'failed')
        for key in ('attempts_claimed', 'branches', 'incumbent', 'micro_evolution'):
            self.assertEqual(after[key], before[key])
        self.assertEqual(self.ledger_bytes(f), ledger)
        self.assertEqual(f.db.execute('SELECT cap,model_cap,blocked FROM config').fetchone(),
                         (CAP400, 100_000_000_000, 0))


if __name__ == '__main__':
    unittest.main()
