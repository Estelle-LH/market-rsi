"""Actual immutable public feedback plus offline synthetic accounting/transport.

No model, candidate, scorer, Native, original ledger write or network. Existing
process tests use temporary SQLite and disclosed historical grant fixture seams.
"""
from copy import deepcopy
import unittest
from unittest.mock import patch
import earnings_entry as e
import earnings_population_clean_slate as clean
import earnings_population_runtime as runtime
import earnings_population_company_batch as batch
from supervisor_harness import capacity_feedback_engine as engine
from test_earnings_population_pending_backpressure import PendingArithmeticTests,PendingProcessTests
from test_earnings_population_slot_rebind import SlotProjectionTests


class FinalOriginTests(unittest.TestCase):
    def setUp(self):
        self.value=dict(clean_slate_policy=clean.POLICY,clean_learning_round=4,
            sources={clean.FOLLOWUP_PLANS[4]:engine.pin(e.REPO/clean.FOLLOWUP_PLANS[4])})
        self.plan=engine.read(self.value['sources'][clean.FOLLOWUP_PLANS[4]])
        self.origin=engine.read(self.plan['origin'])

    def test_complete_latest125_and_separate_parent125_no_rejected_code(self):
        origin=clean.round2_origin(self.value);feedback=engine.read(origin['public_feedback'])
        self.assertEqual(sum(r['points'] for r in feedback['rows']),73.5)
        self.assertEqual(sum(r['points'] for r in feedback['adopted_parent']['rows']),78)
        self.assertEqual(sum(len(r['targets']) for r in feedback['rows']),125)
        self.assertEqual(feedback['actual_R_diagnostic']['reported_numeric_driver_values'],0)
        original=engine.read(origin['prior_descriptor'])['candidate']
        self.assertEqual(origin['parent']['id'],original['id'])
        for axis in ('R','H'):self.assertEqual(origin['parent'][axis],original[axis])
        self.assertNotEqual(origin['parent']['id'],feedback['version_id'])
        self.assertIn('R or H',clean.research_task(self.value))
        self.assertEqual(clean.feedback_name(self.value),'round3-public-feedback.json')

    def test_correct_group_count_and_only_exact_final_authority(self):
        authority=engine.read(clean.FINAL_FOLLOWUP_AUTHORITY)
        self.assertEqual([a['id'] for a in authority['counted_prior_attempts']],
            ['edgar-population-20261016-67','edgar-population-20261016-68'])
        self.assertTrue(clean._followup_authorized(authority,clean.FINAL_FOLLOWUP_AUTHORITY,4))
        for key,other in [('max_new_candidates',4),('prior_group_attempts',1),
                ('final_attempt_ordinal',2),('final_proposal_id','edgar-population-20261016-74')]:
            self.assertFalse(clean._followup_authorized(dict(authority,**{key:other}),clean.FINAL_FOLLOWUP_AUTHORITY,4))
        self.assertFalse(clean._followup_authorized(authority,dict(clean.FINAL_FOLLOWUP_AUTHORITY,sha256='0'*64),4))
        self.assertFalse(clean._followup_authorized(authority,clean.FINAL_FOLLOWUP_AUTHORITY,3))

    def test_missing_or_altered_public_feedback_refused(self):
        original=runtime._local;bound=self.origin['public_feedback']
        for mode in ('missing','duplicate','award'):
            bad=engine.read(bound)
            if mode=='missing':bad['rows'].pop()
            elif mode=='duplicate':bad['rows'][-1]=deepcopy(bad['rows'][0])
            else:bad['rows'][0]['targets'][0]['points_awarded']='invented'
            with patch.object(runtime,'_local',side_effect=lambda b:bad if b==bound else original(b)),self.assertRaises(ValueError):
                clean.round2_origin(self.value)

    def test_only73_generation_never_extra_candidate_or_repair(self):
        clean._final_followup_route('edgar-population-20261016-73',4,False,False)
        clean._final_followup_route('edgar-population-20261016-74',4,True,False)
        for ident,frozen,repair in [('74',False,False),('73',False,True),('74',True,True)]:
            with self.assertRaises(ValueError):clean._final_followup_route('edgar-population-20261016-'+ident,4,frozen,repair)
        for marker in (None,1,3,True,4.0):
            with self.assertRaises(ValueError):clean._final_followup_route('edgar-population-20261016-73',marker,False,False)
        with self.assertRaises(ValueError):clean._final_followup_route('edgar-population-20261016-73',4,True,False)


class FinalPendingArithmeticTests(PendingArithmeticTests):
    def setUp(self):
        super().setUp();self.value['clean_learning_round']=4;self.store.value['clean_learning_round']=4


class FinalPendingProcessTests(PendingProcessTests):
    def resize_queue(self,n):
        super().resize_queue(n);self.value['clean_learning_round']=4


class FinalSlotProjectionTests(SlotProjectionTests):
    def resize(self,n):
        super().resize(n);self.value['clean_learning_round']=4


if __name__=='__main__':unittest.main()
