"""Finite final03a attempt; saved full125 inputs and real offline rolling probes.
No model/API/production-ledger/Native/scorer. Historical grants/Git identity in
inherited process fixtures are mocked; spawn/Pipe/exit/tempSQLite are real.
"""
from copy import deepcopy
from pathlib import Path
import json
import unittest
from unittest.mock import patch
import earnings_entry as e
import earnings_population_clean_slate as clean
import earnings_population_runtime as runtime
import earnings_population_company_batch as batch
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_clean_round5 as previous
import test_earnings_population_clean_followup as followup

def sources():return {clean.FOLLOWUP_PLANS[7]:engine.pin(e.REPO/clean.FOLLOWUP_PLANS[7])}

class FinalOriginTests(unittest.TestCase):
    def setUp(self):
        self.value=dict(clean_slate_policy=clean.POLICY,clean_learning_round=7,sources=sources())
        self.origin=clean.round2_origin(self.value)
    def test_same03a_parent_not_latest_losing430f_full125(self):
        self.assertTrue(clean.enabled(self.value));origin=self.origin;feedback=engine.read(origin['public_feedback'])
        self.assertEqual(origin['parent']['id'],'03a87b7b84629aed9dc5fc738b3f2be42e7c49fda8aba346718d8e7359ca67da')
        self.assertNotEqual(feedback['version_id'],origin['parent']['id'])
        self.assertEqual(sum(r['points'] for r in feedback['rows']),77)
        self.assertEqual(sum(len(r['targets']) for r in feedback['rows']),125)
        self.assertEqual(sum(r['points'] for r in feedback['adopted_parent']['rows']),78.5)
        self.assertEqual(sum(len(r['targets']) for r in feedback['adopted_parent']['rows']),125)
        self.assertEqual(origin['prior_mean'],3.14);self.assertEqual(origin['group_attempt_ordinal'],3)
        self.assertEqual(feedback['actual_R_diagnostic']['coverage'],dict(targets=125,histories_sufficient=2,validated=0,departures=0))
        self.assertNotEqual(origin['parent']['R'],engine.read(engine.read(origin['prior_comparison'])['frozen'])['candidate']['R'])
    def test_no_partial_false_terminal_reset_or_overcount(self):
        original=runtime._local;bound=self.origin['group_progress']
        for key,value in [('count_used',0),('count_cap',4),('group_terminal',True),('attempts',[77,78]),('minimum_additional',1)]:
            bad=engine.read(bound);bad[key]=value
            with patch.object(runtime,'_local',side_effect=lambda b:bad if b==bound else original(b)),self.assertRaises(ValueError):
                clean.round2_origin(self.value)
    def test_missing_altered_latest_or_actual_parent_feedback_refused(self):
        original=runtime._local
        for key in ('public_feedback','parent_feedback'):
            bound=self.origin[key];bad=engine.read(bound);bad['rows']=bad['rows'][:-1]
            with patch.object(runtime,'_local',side_effect=lambda b:bad if b==bound else original(b)),self.assertRaises(ValueError):
                clean.round2_origin(self.value)
    def test_historical_seven_source_cannot_admit_unbound_continuation(self):
        self.assertTrue(clean._followup_authorized(engine.read(clean.STABLE03A_NEXT_AUTHORITY),clean.STABLE03A_NEXT_AUTHORITY,7))
        self.assertIn(clean.FOLLOWUP_PLANS[7],runtime.source_paths(clean_slate=True,clean_followup=7))
        for marker in (True,7.0,8,9):
            with self.assertRaises(ValueError):clean.enabled(dict(self.value,clean_learning_round=marker))
        for marker in (True,7.0,2):
            with self.assertRaises(ValueError):runtime.source_paths(clean_slate=True,clean_followup=marker)
        with self.assertRaises(ValueError):clean.enabled(dict(self.value,sources={}))
    def test_exact_once85_proposal_then_new_frozen_ids(self):
        clean._final_followup_route('edgar-population-20261016-85',7,False,False)
        clean._final_followup_route('edgar-population-20261016-86',7,True,False)
        for ident,n,frozen,repair in [('85',6,False,False),('85',7,True,False),('85',7,False,True),
                ('86',7,False,False),('84',7,True,False),('81',7,False,False),('85',7.0,False,False)]:
            with self.assertRaises(ValueError):clean._final_followup_route('edgar-population-20261016-'+ident,n,frozen,repair)
    def test_carry_exact_eight_yield_without_budget_or_reservation_changes(self):
        self.value['clean_company_concurrency']=batch.ROLLING8
        self.assertTrue(batch.window_yield_enabled(self.value))
        self.assertEqual(batch.window_yield_authority(self.value),clean.STABLE03A_ROUND7_YIELD_AUTHORITY)
        policy=engine.read(batch.window_yield_authority(self.value));old=engine.read(clean.STABLE03A_YIELD_AUTHORITY)
        for key in ('empirical_company_buffer_nano_usd','closing_admission_margin_seconds','max_companies',
                    'max_inflight_per_company','window_cap_nano_usd','window_minutes','no_reservation_reduction'):
            self.assertEqual(policy[key],old[key])

class FinalComparisonTests(previous.NextComparisonTests):
    def setUp(self):
        super().setUp();self.descriptor['learning_round']=7
    def test_parent_threshold_dynamic_not_legacy3_12(self):
        self.set_improved_companies(3);result=clean.compare(self.descriptor_binding,self.windows)
        self.assertEqual(result['parent_mean'],3.14);self.assertEqual(result['decision'],'RETAIN_ADOPTED_PARENT')
        self.assertEqual(result['logical_round'],7)

class FinalPendingArithmeticTests(previous.NextPendingArithmeticTests):
    def setUp(self):
        super().setUp();self.value.update(clean_learning_round=7,sources=sources());self.store.value=deepcopy(self.value)

class FinalPendingProcessTests(previous.NextPendingProcessTests):
    def resize_queue(self,n):
        super().resize_queue(n);self.value.update(clean_learning_round=7,sources=sources());self.store.value=deepcopy(self.value)

class FinalSlotProjectionTests(previous.NextSlotProjectionTests):
    def resize(self,n):
        super().resize(n);self.value.update(clean_learning_round=7,sources=sources())
    def test_cross_company_or_changed_parent_resources_are_rejected(self):
        for key,other in [('source_commit','b'*40),('root',str(self.root/'other')),('cutoff_utc','2027-01-01T00:00:00Z'),
                ('slots',self.slots[:-1]),('limits',dict(self.limits,wall_seconds=1801)),('rates',dict(self.rates,effort='high'))]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                batch.company_forecast_context(self.value,dict(self.parent,**{key:other}),self.ids[0],self.slots[0])
        with self.assertRaises(ValueError):batch.company_forecast_context(self.value,self.parent,self.ids[0],self.slots[1])
        for marker in (True,7.0,8):
            with self.assertRaises(ValueError):batch.company_forecast_context(dict(self.value,clean_learning_round=marker),self.parent,self.ids[0],self.slots[0])

class FinalWindowYieldTests(previous.NextWindowYieldTests):
    def enable_yield(self):
        super().enable_yield();self.value.update(clean_learning_round=7,sources=sources());self.store.value=deepcopy(self.value)

class FinalAuthorReceivingTests(followup.FollowupAuthorReceivingTests):
    def setUp(self):
        super().setUp();self.summary.update(logical_round=6,version_id='latest-losingfd9a',
            actual_R_diagnostic=dict(coverage=dict(targets=125,histories_sufficient=2,validated=0,departures=0),
                sign_coverage=dict(targets=125,supported=0,ambiguous=125),
                sign_reason_counts=dict(missing_cited_label=114,source_location_or_hash_missing=11)))
        Path(self.feedback['path']).write_text(json.dumps(self.summary));self.feedback=engine.pin(Path(self.feedback['path']))
        self.task['feedback']=self.feedback;self.chosen['feedback_sha256']=digest(self.feedback)
        self.context.update(feedback=self.summary,training_comparator=self.summary,feedback_binding=self.feedback,feedback_sha256=digest(self.feedback))
        self.context_path.write_text(json.dumps(self.context));self.base.population_context_binding=engine.pin(self.context_path)
        path=Path(self.runtime['path']);path.write_text(json.dumps(dict(clean_slate_policy=clean.POLICY,clean_learning_round=7,sources=sources())))
        self.base.clean_slate_runtime_binding=engine.pin(path)
    def test_actual_broker_chain_receives_latest_and_parent125_with_activation_diagnostic(self):
        from earnings_open_program import program
        self.author.author(self.chosen,program(self.r.read_bytes(),'R'),str(self.root/'author-slot'),parent_binding=self.parent['R'])
        context=self.received[0]['research_context'];feedback=context['training_comparator']
        self.assertEqual(sum(len(r['targets']) for r in feedback['rows']),125)
        self.assertEqual(sum(len(r['targets']) for r in feedback['adopted_parent']['rows']),125)
        self.assertEqual(feedback['version_id'],'latest-losingfd9a');self.assertEqual(context['parent_version_id'],self.parent['id'])
        self.assertEqual(feedback['actual_R_diagnostic']['coverage']['validated'],0)
        self.assertEqual(feedback['actual_R_diagnostic']['sign_coverage'],dict(targets=125,supported=0,ambiguous=125))
        self.assertEqual(feedback['actual_R_diagnostic']['sign_reason_counts']['source_location_or_hash_missing'],11)
        self.assertNotIn('prior_candidate',context)

if __name__=='__main__':unittest.main()
