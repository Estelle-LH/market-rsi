"""Finite direct03a parent/feedback plus real offline8rolling/tempSQLite tests.

No API/model/production-ledger/Native/scorer run. Reused fixture seams explicitly
mock historical grant/Git identity; actual process/Pipe/exit/accounting are real.
"""
from copy import deepcopy
from datetime import datetime,timezone
import json
import unittest
from unittest.mock import patch
import earnings_entry as e
import earnings_population_clean_slate as clean
import earnings_population_runtime as runtime
import earnings_population_company_batch as batch
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_clean_round2 as prior
import test_earnings_population_clean_followup as followup
from test_earnings_population_pending_backpressure import PendingArithmeticTests as _PendingArithmeticTests, PendingProcessTests as _PendingProcessTests
from test_earnings_population_slot_rebind import SlotProjectionTests as _SlotProjectionTests
from test_earnings_population_window_yield import WindowYieldTests as _WindowYieldTests


def sources():return {clean.FOLLOWUP_PLANS[5]:engine.pin(e.REPO/clean.FOLLOWUP_PLANS[5])}


class NextOriginTests(unittest.TestCase):
    def setUp(self):
        self.value=dict(clean_slate_policy=clean.POLICY,clean_learning_round=5,sources=sources())
        self.plan=engine.read(self.value['sources'][clean.FOLLOWUP_PLANS[5]]);self.origin=engine.read(self.plan['origin'])
    def test_adopted03a_complete125_literal_feedback_and_no_old_parent(self):
        self.assertTrue(clean.enabled(self.value));origin=clean.round2_origin(self.value)
        feedback=engine.read(origin['public_feedback']);self.assertEqual(sum(r['points'] for r in feedback['rows']),78.5)
        self.assertEqual(sum(len(r['targets']) for r in feedback['rows']),125)
        self.assertEqual(origin['prior_mean'],3.14);self.assertEqual(origin['parent']['id'],feedback['version_id'])
        self.assertEqual(origin['parent']['id'],origin['original_candidate']['id']);self.assertIsNone(origin['parent']['parent'])
        self.assertNotEqual(origin['parent']['id'],origin['original_candidate']['parent'])
        self.assertEqual(feedback['actual_R_diagnostic']['coverage']['validated'],0)
        self.assertEqual(feedback['actual_R_diagnostic']['coverage']['departures'],0)
        self.assertIn('R or H',clean.research_task(self.value));self.assertIn('3.14',clean.research_task(self.value))
    def test_exact_direct_authority_no_budget_reset_or_extra_round(self):
        authority=engine.read(clean.STABLE03A_NEXT_AUTHORITY)
        self.assertTrue(clean._followup_authorized(authority,clean.STABLE03A_NEXT_AUTHORITY,5))
        for key,value in [('starting_parent_mean',3.12),('starting_parent_id','21c'),('max_new_candidates',4),
                ('prior_group_attempts',1),('failed_paid_retry_authorized',True),('human_reply','foreign relay')]:
            self.assertFalse(clean._followup_authorized(dict(authority,**{key:value}),clean.STABLE03A_NEXT_AUTHORITY,5))
        wrong=deepcopy(authority);wrong['budget']['stage_total_nano_usd']+=1
        self.assertFalse(clean._followup_authorized(wrong,clean.STABLE03A_NEXT_AUTHORITY,5))
        self.assertFalse(clean._followup_authorized(authority,dict(clean.STABLE03A_NEXT_AUTHORITY,sha256='0'*64),5))
        for n in (True,5.0,6,7,8):
            with self.assertRaises(ValueError):clean.enabled(dict(self.value,clean_learning_round=n))
    def test_no_missing_duplicate_or_altered_feedback(self):
        original=runtime._local;bound=self.origin['public_feedback']
        for mode in ('missing','duplicate','prediction','award'):
            bad=engine.read(bound)
            if mode=='missing':bad['rows'].pop()
            elif mode=='duplicate':bad['rows'][-1]=deepcopy(bad['rows'][0])
            else:bad['rows'][0]['targets'][0]['predicted_value' if mode=='prediction' else 'points_awarded']='invented'
            with patch.object(runtime,'_local',side_effect=lambda b:bad if b==bound else original(b)),self.assertRaises(ValueError):clean.round2_origin(self.value)
    def test_only77_first_proposal_then_frozen_evaluation(self):
        clean._final_followup_route('edgar-population-20261016-77',5,False,False)
        clean._final_followup_route('edgar-population-20261016-78',5,True,False)
        for ident,n,frozen,repair in [('77',4,False,False),('77',5,True,False),('77',5,False,True),
                ('78',5,False,False),('76',5,True,False),('77',None,False,False),('77',True,False,False)]:
            with self.assertRaises(ValueError):clean._final_followup_route('edgar-population-20261016-'+ident,n,frozen,repair)


class NextComparisonTests(prior.Round2ComparisonTests):
    def setUp(self):
        super().setUp();self.descriptor['learning_round']=5
        self.baseline[3]['points']=3.5;self.baseline[3]['targets'][3]['points_awarded']=.5
        feedback=engine.save(self.root/'parent-public5.json',dict(rows=self.baseline))
        origin=engine.read(self.descriptor['parent_basis']);origin.update(prior_mean=3.14,public_feedback=feedback)
        self.descriptor['parent_basis']=engine.save(self.root/'new-group-origin.json',origin)
    def test_parent_threshold_dynamic_not_legacy3_12(self):
        self.set_improved_companies(3);result=clean.compare(self.descriptor_binding,self.windows)
        self.assertEqual(result['parent_mean'],3.14);self.assertEqual(result['decision'],'RETAIN_ADOPTED_PARENT')
        self.assertEqual(result['logical_round'],5)
    def test_improvement_over_round0_but_below_parent_is_not_adopted(self):
        self.set_improved_companies(1);result=clean.compare(self.descriptor_binding,self.windows)
        self.assertEqual(result['candidate_mean'],3.04);self.assertEqual(result['parent_mean'],3.14)
        self.assertEqual(result['decision'],'RETAIN_ADOPTED_PARENT')
    def test_full_parent_tie_retains_adopted_pair(self):
        self.set_improved_companies(3);path=self.root/'3'/'population-public-feedback.json';saved=json.loads(path.read_bytes())
        saved['points']=3.5;saved['target_scores'][-1]['points_awarded']=.5;path.write_text(json.dumps(saved))
        self.verified[self.windows[3]['path']]['result']['result']['results'][0]['result']['points']=3.5
        result=clean.compare(self.descriptor_binding,self.windows)
        self.assertEqual(result['candidate_mean'],3.14);self.assertEqual(result['decision'],'RETAIN_ADOPTED_PARENT')


class NextPendingArithmeticTests(_PendingArithmeticTests):
    def setUp(self):
        super().setUp();self.value.update(clean_learning_round=5,sources=sources());self.store.value=deepcopy(self.value)


class NextPendingProcessTests(_PendingProcessTests):
    def resize_queue(self,n):
        super().resize_queue(n);self.value.update(clean_learning_round=5,sources=sources(),
            rates=dict(api_model='gpt-6.1-sol',input='2',cached='.1',write='2.5',output='10'),
            limits=dict(forecast=dict(max_input_tokens=100000,max_output_tokens=25000,wall_seconds=1800)),
            cutoff_utc=datetime.fromtimestamp(self.budget.deadline,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
        self.store.value=deepcopy(self.value)


class NextSlotProjectionTests(_SlotProjectionTests):
    def resize(self,n):
        super().resize(n);self.value.update(clean_learning_round=5,sources=sources())
    def test_cross_company_or_changed_parent_resources_are_rejected(self):
        for key,other in [('source_commit','b'*40),('root',str(self.root/'other')),('cutoff_utc','2027-01-01T00:00:00Z'),
                ('slots',self.slots[:-1]),('limits',dict(self.limits,wall_seconds=1801)),('rates',dict(self.rates,effort='high'))]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                batch.company_forecast_context(self.value,dict(self.parent,**{key:other}),self.ids[0],self.slots[0])
        with self.assertRaises(ValueError):batch.company_forecast_context(self.value,self.parent,self.ids[0],self.slots[1])
        for marker in (True,5.0,6):
            with self.assertRaises(ValueError):batch.company_forecast_context(dict(self.value,clean_learning_round=marker),self.parent,self.ids[0],self.slots[0])


class NextWindowYieldTests(_WindowYieldTests):
    def enable_yield(self):
        super().enable_yield();self.value.update(clean_learning_round=5,sources=sources());self.store.value=deepcopy(self.value)


class NextAuthorReceivingTests(followup.FollowupAuthorReceivingTests):
    def setUp(self):
        super().setUp();self.summary.update(logical_round=4,version_id=self.parent['id'],decision='ADOPT_CANDIDATE',
            actual_R_diagnostic=dict(coverage=dict(targets=125,histories_sufficient=2,validated=0,departures=0)))
        from pathlib import Path
        from market_rsi import digest
        Path(self.feedback['path']).write_text(json.dumps(self.summary));self.feedback=engine.pin(Path(self.feedback['path']))
        self.task['feedback']=self.feedback;self.chosen['feedback_sha256']=digest(self.feedback)
        self.context.update(feedback=self.summary,training_comparator=self.summary,feedback_binding=self.feedback,feedback_sha256=digest(self.feedback))
        self.context_path.write_text(json.dumps(self.context));self.base.population_context_binding=engine.pin(self.context_path)
        path=Path(self.runtime['path']);path.write_text(json.dumps(dict(clean_slate_policy=clean.POLICY,clean_learning_round=5,sources=sources())))
        self.base.clean_slate_runtime_binding=engine.pin(path)
    def test_actual_broker_chain_receives_latest_and_parent125_with_activation_diagnostic(self):
        from earnings_open_program import program
        self.author.author(self.chosen,program(self.r.read_bytes(),'R'),str(self.root/'author-slot'),parent_binding=self.parent['R'])
        context=self.received[0]['research_context'];feedback=context['training_comparator']
        self.assertEqual(sum(len(r['targets']) for r in feedback['rows']),125)
        self.assertEqual(sum(len(r['targets']) for r in feedback['adopted_parent']['rows']),125)
        self.assertEqual(feedback['version_id'],self.parent['id']);self.assertEqual(context['parent_version_id'],self.parent['id'])
        self.assertEqual(feedback['actual_R_diagnostic']['coverage']['validated'],0)
        self.assertNotIn('prior_candidate',context)


del _PendingArithmeticTests,_PendingProcessTests,_SlotProjectionTests,_WindowYieldTests


if __name__=='__main__':unittest.main()
