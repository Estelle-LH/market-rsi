"""Offline public metadata + inert real Author chain; no API/scorer/Native/ledger."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import earnings_entry as e
import earnings_population_clean_slate as clean
import earnings_population_runtime as runtime
from supervisor_harness import capacity_feedback_engine as engine
from market_rsi import digest
import test_earnings_population_clean_slate as fixtures
import test_earnings_population_clean_round2 as prior

def offline(event,args):
    if event in ('socket.connect','socket.bind'):raise AssertionError('OFFLINE: no network')
sys.addaudithook(offline)

class FollowupOriginTests(unittest.TestCase):
    def setUp(self):
        self.value=dict(clean_slate_policy=clean.POLICY,clean_learning_round=3,
            sources={clean.FOLLOWUP_PLANS[3]:engine.pin(e.REPO/clean.FOLLOWUP_PLANS[3])})
        self.plan=engine.read(self.value['sources'][clean.FOLLOWUP_PLANS[3]])
        self.origin=engine.read(self.plan['origin'])
    def altered(self,binding,value):
        original=runtime._local
        return patch.object(runtime,'_local',side_effect=lambda b:deepcopy(value) if b==binding else original(b))
    def test_actual_latest125_rejected_feedback_separate_from_retained125_parent(self):
        self.assertTrue(clean.enabled(self.value));origin=clean.round2_origin(self.value)
        latest=engine.read(origin['public_feedback']);parent=engine.read(origin['parent_feedback'])
        self.assertEqual(sum(r['points'] for r in latest['rows']),77)
        self.assertEqual(sum(r['points'] for r in parent['rows']),78)
        self.assertEqual(sum(len(r['targets']) for r in latest['rows']),125)
        self.assertNotEqual(latest['version_id'],origin['parent']['id'])
        self.assertEqual(parent['version_id'],origin['parent']['id'])
        self.assertEqual(latest['actual_R_diagnostic']['reported_calibrated_targets'],0)
        self.assertEqual(origin['parent']['R'],origin['original_candidate']['R'])
        self.assertIsNone(origin['parent']['parent']);self.assertIsNotNone(origin['original_candidate']['parent'])
    def test_missing_duplicate_or_changed_latest_predictions_refused(self):
        feedback=engine.read(self.origin['public_feedback'])
        for mode in ('missing','duplicate','prediction','award'):
            wrong=deepcopy(feedback)
            if mode=='missing':wrong['rows'].pop()
            elif mode=='duplicate':wrong['rows'][-1]=deepcopy(wrong['rows'][0])
            else:wrong['rows'][0]['targets'][0]['predicted_value' if mode=='prediction' else 'points_awarded']='invented'
            with self.altered(self.origin['public_feedback'],wrong),self.assertRaises(ValueError):clean.round2_origin(self.value)
    def test_parent_feedback_not_rejected_trial_points(self):
        wrong=engine.read(self.origin['public_feedback'])
        with self.altered(self.origin['parent_feedback'],wrong),self.assertRaises(ValueError):clean.round2_origin(self.value)
    def test_false_promotion_or_partial_prior_refused(self):
        stable=engine.read(self.origin['prior_stable']);latest=engine.read(self.origin['prior_comparison'])
        wrong=deepcopy(stable);wrong['selected']=latest['frozen']
        with self.altered(self.origin['prior_stable'],wrong),self.assertRaises(ValueError):clean.round2_origin(self.value)
        for key,other in (('scored',24),('candidate_mean',4.0),('parent_mean',3.0)):
            wrong=deepcopy(latest);wrong['comparison'][key]=other
            with self.altered(self.origin['prior_comparison'],wrong),self.assertRaises(ValueError):clean.round2_origin(self.value)
    def test_no_unbounded_round_marker_or_accidental_source_plan(self):
        for n in (True,1,5,'3',3.0):
            wrong=deepcopy(self.value);wrong['clean_learning_round']=n
            with self.assertRaises(ValueError):clean.enabled(wrong)
        wrong=deepcopy(self.value);wrong['sources']={}
        with self.assertRaises(ValueError):clean.enabled(wrong)
        for kwargs in (dict(clean_followup=5),dict(clean_followup=3),dict(clean_slate=True,clean_round2=True,clean_followup=3)):
            with self.assertRaises(ValueError):runtime.source_paths(**kwargs)
    def test_research_task_does_not_impose_rejected_method_or_empty_parent(self):
        task=clean.research_task(self.value)
        self.assertIn('Round3',task);self.assertIn('3.12',task);self.assertIn('R or H',task)
        self.assertIn('NOT the code parent',task);self.assertEqual(clean.feedback_name(self.value),'round2-public-feedback.json')

class FollowupComparisonTests(prior.Round2ComparisonTests):
    def setUp(self):
        super().setUp();self.descriptor['learning_round']=3
        origin=engine.read(self.descriptor['parent_basis'])
        # Latest losing trial is deliberately NOT the adoption comparator.
        bad=deepcopy(self.baseline)
        for row in bad:row['points']=0
        latest=engine.save(self.root/'latest-trial.json',dict(rows=bad))
        binding=engine.save(self.root/'followup-origin.json',dict(origin,public_feedback=latest,parent_feedback=origin['public_feedback']))
        self.descriptor['parent_basis']=binding
    def test_dynamic_parent_threshold_not_hardcoded_3_12(self):
        origin=engine.read(self.descriptor['parent_basis']);origin['prior_mean']=3.2
        self.descriptor['parent_basis']=engine.save(self.root/'higher-parent.json',origin)
        self.set_improved_companies(4)
        result=clean.compare(self.descriptor_binding,self.windows)
        self.assertEqual(result['candidate_mean'],3.16);self.assertEqual(result['parent_mean'],3.2)
        self.assertEqual(result['decision'],'RETAIN_ADOPTED_PARENT');self.assertEqual(result['logical_round'],3)

class FollowupAuthorReceivingTests(unittest.TestCase):
    def setUp(self):
        fixtures.AuthorReceivingTests.setUp(self)
        self.summary.update(logical_round=2,version_id='rejected-trial',decision='RETAIN_ADOPTED_PARENT',
            adopted_parent=dict(version_id=self.parent['id'],rows=deepcopy(self.summary['rows'])),
            actual_R_diagnostic=dict(reported_calibrated_targets=0,reported_targets=125))
        Path(self.feedback['path']).write_text(json.dumps(self.summary));self.feedback=engine.pin(Path(self.feedback['path']))
        self.task['feedback']=self.feedback;self.chosen['feedback_sha256']=digest(self.feedback)
        self.context.update(feedback=self.summary,training_comparator=self.summary,feedback_binding=self.feedback,
            feedback_sha256=digest(self.feedback),task='Choose R or H from complete feedback, not rejected code')
        self.context_path.write_text(json.dumps(self.context));self.base.population_context_binding=engine.pin(self.context_path)
        path=Path(self.runtime['path']);path.write_text(json.dumps(dict(clean_slate_policy=clean.POLICY,clean_learning_round=3,
            sources={clean.FOLLOWUP_PLANS[3]:engine.pin(e.REPO/clean.FOLLOWUP_PLANS[3])})))
        self.base.clean_slate_runtime_binding=engine.pin(path)
    def test_actual_broker_chain_receives_latest_and_parent125_with_activation_diagnostic(self):
        from earnings_open_program import program
        self.author.author(self.chosen,program(self.r.read_bytes(),'R'),str(self.root/'author-slot'),parent_binding=self.parent['R'])
        context=self.received[0]['research_context'];feedback=context['training_comparator']
        self.assertEqual(sum(len(r['targets']) for r in feedback['rows']),125)
        self.assertEqual(sum(len(r['targets']) for r in feedback['adopted_parent']['rows']),125)
        self.assertEqual(feedback['version_id'],'rejected-trial')
        self.assertEqual(context['parent_version_id'],self.parent['id'])
        self.assertEqual(feedback['actual_R_diagnostic']['reported_calibrated_targets'],0)
        self.assertNotIn('prior_candidate',context)

if __name__=='__main__':unittest.main()
