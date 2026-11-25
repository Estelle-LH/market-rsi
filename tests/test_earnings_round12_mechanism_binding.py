"""Saved-input/prospective-role boundaries only; no provider, Native or scorer."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import earnings_population_clean_slate as clean
import earnings_population_coevolution as policy
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine

class Round12(unittest.TestCase):
    def setUp(self):
        # Original112 is history, not the later unchanged-PROGRAM113 Review.
        historical=patch.object(policy,'PLAN',str(clean.training.ROOT/'TRAIN25-FRONTIER-ROUND12-SOURCE-PLAN-V3.json'))
        historical.start();self.addCleanup(historical.stop)
        self.plan=engine.read(engine.pin(policy.e.REPO/policy.PLAN))
        self.origin=engine.read(self.plan['origin'])
        self.feedback=engine.read(self.origin['public_feedback'])
        self.state=engine.read(self.origin['carried_population'])
        self.test=engine.read(self.plan['observable_mechanism_test'])
    def test_same_actual_compiler_parent_not_prediction_adoption(self):
        self.assertEqual(self.plan['logical_round'],12)
        self.assertTrue(self.origin['parent']['id'].startswith('09948'))
        self.assertTrue(self.state['stable_id'].startswith('03a87'))
        self.assertEqual(policy.selected_parent(self.state,self.origin),self.origin['parent'])
        self.assertEqual(policy.selection_threshold(self.origin),3.14)
        policy.validate_plan(self.plan,self.origin)
    def test_complete_feedback_and_failed_history_not_reset(self):
        for rows in (self.feedback['rows'],self.feedback['actual_parent']['rows'],self.feedback['selection_incumbent']['rows']):
            self.assertEqual([x['company_id'] for x in rows],self.origin['training'])
            self.assertEqual(sum(len(x['targets']) for x in rows),125)
        self.assertEqual(self.feedback['company_equal_mean'],2.92)
        self.assertEqual(self.feedback['actual_R_H_diagnostic']['observed']['bound_observations'],0)
        self.assertFalse(self.feedback['actual_R_H_diagnostic']['validated_learning'])
        self.assertIn('105 failure',self.feedback['prior_lessons'])
    def test_literal_lesson_and_observable_test_not_score_only(self):
        self.assertIn('USD thousands',str(self.feedback['specific_original_input_contract_diagnosis']))
        self.assertIn('first3',self.test['positive_sample'])
        self.assertIn('first2',self.test['positive_sample'])
        self.assertIn('public',self.test['support'])
        self.assertIn('Ready counts',self.test['support'])
        task=clean.research_task(dict(clean_learning_round=12,sources={policy.PLAN:engine.pin(policy.e.REPO/policy.PLAN)}))
        self.assertIn(self.test['discriminating_question'],task)
    def test_real_controller_producer_passes_complete_lesson(self):
        with TemporaryDirectory(prefix='edgar111-offline-controller-') as td:
            slot=str(Path(td)/'controller');seen=[]
            outer=self
            class Role:
                broker=SimpleNamespace(current_sources=lambda:dict(R='inert source',H='inert source'))
                def propose(self,prompt,where):
                    seen.append(prompt);Path(where).mkdir()
                    original=engine.save(Path(where)/'synthetic-response.json',dict(synthetic=True))
                    engine.save(Path(where)/'decision.json',dict(original=original,decision=dict(synthetic=True)))
                    return original
            service=SimpleNamespace(runtime=dict(clean_learning_round=12,sources={policy.PLAN:engine.pin(policy.e.REPO/policy.PLAN)}),
                case=lambda parent,where:dict(state_api=SimpleNamespace(tools=SimpleNamespace(files={'questions.md':'Inert question'}))),
                role=lambda *args:Role())
            packet=dict(company_id=self.origin['training'][0],population=self.state,feedback=self.origin['public_feedback'],
                parent_feedback_sha256=digest(self.feedback))
            with patch.object(clean,'read_task',return_value=(dict(mode='proposal',feedback=self.origin['public_feedback']),clean.training.load_scope(clean.SPLIT))):
                clean.controller(service,packet,slot)
            self.assertEqual(seen[0]['feedback'],self.feedback)
            self.assertEqual(seen[0]['active_versions'],[self.origin['parent']['id']])
            self.assertIn(self.test['discriminating_question'],seen[0]['research_objective'])
            self.assertFalse(seen[0]['feedback']['actual_R_H_diagnostic']['validated_learning'])
    def test_no_old_ID_review_reopen_or_retry_route(self):
        proposal=self.plan['proposal_id']
        policy.route(proposal,12,False,False)
        for ident,n,frozen,repair in (('edgar-population-20261016-107',11,False,True),
                ('edgar-population-20261016-111',12,False,False),(proposal,12,True,False),
                (proposal,12,False,True)):
            with self.assertRaises(ValueError):policy.route(ident,n,frozen,repair)
    def test_closed111_delivery_failure_preserved_not_code_parent(self):
        failure=self.feedback['public_engineering_failure']
        self.assertEqual(failure['assembled_unexecuted_source_bytes'],68287)
        self.assertEqual(failure['source_cap_bytes'],65536)
        self.assertEqual(failure['headroom_bytes'],5632)
        self.assertEqual(engine.read(failure['original'])['pending_count'],0)
        self.assertEqual(self.origin['parent']['H']['sha256'],'9fc9ba152f059e44d96c8587806bab6fbb13e9c5c095acd3ab391e25f6e155af')
        self.assertEqual(self.plan['proposal_id'],'edgar-population-20261016-112')
        self.assertEqual(engine.read(failure['original'])['owned_generations'],16)
    def test_existing_preview_caught_original_oversize_without_execution(self):
        diagnostic=engine.read(self.origin['source_navigation_diagnosis'])
        preview=diagnostic['Root_postclosure_existing_preview_diagnostic']
        self.assertFalse(preview['code_executed']);self.assertFalse(preview['candidate_saved'])
        self.assertEqual(preview['errors'],[dict(code='source_size_exceeded')])
        self.assertEqual(preview['excess_source_utf8_bytes'],2751)
        self.assertEqual(diagnostic['actual_model_preview_calls'],0)
        self.assertEqual(diagnostic['verified_actual_page_union'],[0,28000])
        self.assertTrue(all(row['offset']>=28000 for row in diagnostic['source_function_navigation']))
    def test_missing_latest_complete_or_substituted_parent_refused(self):
        for change in (dict(parent=self.state['versions'][self.state['stable_id']]),dict(prior_mean=3.14)):
            with self.assertRaises(ValueError):policy.expansion(dict(self.origin,**change),self.plan)
    def test_original_budget_and_resources_not_refreshed(self):
        self.assertFalse(self.plan['budget_change']);self.assertFalse(self.plan['automatic_retry'])
        self.assertFalse(self.plan['heldout_access']);self.assertEqual(self.plan['max_concurrent_companies'],8)
        self.assertEqual(policy.decision(339855082600,0,13000000000,meaningful_next=True),'CONTINUE')
        self.assertEqual(policy.decision(387429960800,1,1,meaningful_next=True),'STOP_ORIGINAL_BUDGET_INSUFFICIENT')

if __name__=='__main__':unittest.main()
