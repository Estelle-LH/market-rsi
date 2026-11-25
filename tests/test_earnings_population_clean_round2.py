"""No provider/scorer/Native/ledger: origin projection + synthetic saved-score comparisons.

The origin tests hash/read the authorized saved public Round1 metadata and parent
code bytes (never execute that code). Negative semantic tests substitute a copied
JSON value in memory. Comparison fixtures mock completed evidence explicitly.
"""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

import earnings_entry as e
import earnings_population_clean_slate as clean
import earnings_population_runtime as runtime
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_clean_slate as fixtures


def deny_network(event,args):
    if event in ('socket.connect','socket.bind'):raise AssertionError('OFFLINE network forbidden')
sys.addaudithook(deny_network)


class Round2OriginTests(unittest.TestCase):
    def setUp(self):
        self.value=dict(clean_slate_policy=clean.POLICY,clean_learning_round=2,
            sources={clean.ROUND2_PLAN:engine.pin(e.REPO/clean.ROUND2_PLAN)})
        self.plan=e.strict_json(e.checked(self.value['sources'][clean.ROUND2_PLAN]))
        self.origin=engine.read(self.plan['origin'])

    def altered(self,binding,value):
        original=runtime._local
        return patch.object(runtime,'_local',side_effect=lambda b:deepcopy(value) if b==binding else original(b))

    def test_actual_saved_complete125_feedback_and_adopted_pair(self):
        origin=clean.round2_origin(self.value);feedback=engine.read(origin['public_feedback'])
        self.assertEqual(sum(len(r['targets']) for r in feedback['rows']),125)
        self.assertEqual(sum(r['points'] for r in feedback['rows']),78)
        self.assertEqual(origin['parent']['id'],'21c5dabadd4c3feb029cb94a3471937f7671d42c06ac99017218fe0e5255a56e')
        self.assertEqual(origin['parent']['id'],origin['original_candidate']['id'])
        self.assertIsNone(origin['parent']['parent'])
        self.assertIsNotNone(origin['original_candidate']['parent'])  # original genealogy preserved, no fabricated reset

    def test_partial_missing_duplicate_feedback_is_rejected(self):
        feedback=engine.read(self.origin['public_feedback'])
        for rows in (feedback['rows'][:-1],feedback['rows'][:-1]+feedback['rows'][:1]):
            wrong=deepcopy(feedback);wrong['rows']=rows
            with self.altered(self.origin['public_feedback'],wrong),self.assertRaises(ValueError):clean.round2_origin(self.value)

    def test_prediction_or_award_substitution_rejected(self):
        feedback=engine.read(self.origin['public_feedback'])
        for key,other in (('predicted_value','invented'),('points_awarded',.2)):
            wrong=deepcopy(feedback);wrong['rows'][0]['targets'][0][key]=other
            with self.altered(self.origin['public_feedback'],wrong),self.assertRaises(ValueError):clean.round2_origin(self.value)

    def test_unadopted_or_incomplete_prior_round_cannot_be_parent(self):
        full=engine.read(self.origin['prior_comparison'])
        for key,other in (('decision','RETAIN_ROUND0'),('scored',24),('candidate_mean',3.0)):
            wrong=deepcopy(full);wrong['comparison'][key]=other
            with self.altered(self.origin['prior_comparison'],wrong),self.assertRaises(ValueError):clean.round2_origin(self.value)

    def test_scored25_header_cannot_hide_short_or_reordered_comparison(self):
        full=engine.read(self.origin['prior_comparison'])
        for rows in (full['comparison']['rows'][:-1],list(reversed(full['comparison']['rows']))):
            wrong=deepcopy(full);wrong['comparison']['rows']=rows
            with self.altered(self.origin['prior_comparison'],wrong),self.assertRaises(ValueError):clean.round2_origin(self.value)

    def test_frozen_round_marker_must_match_real_proposal_in_both_directions(self):
        descriptor=engine.read(self.origin['prior_descriptor'])
        value=dict(source_commit=descriptor['source_commit'],sources={clean.PLAN:descriptor['authority'],**descriptor['forecast_sources']},
            rates=descriptor['rates'],limits=dict(forecast=descriptor['forecast_limits']))
        for actual_second,claimed_second in ((True,False),(False,True)):
            claimed=deepcopy(descriptor);actual=deepcopy(value)
            if actual_second:actual['clean_learning_round']=2
            if claimed_second:claimed.update(learning_round=2,parent_basis=self.plan['origin'])
            proof=dict(runtime=actual,candidate=claimed['candidate'],task=dict(round2_origin=self.plan['origin']))
            binding=dict(path=str(clean.training.ROOT/'synthetic-frozen-never-saved.json'),sha256=('a' if actual_second else 'b')*64)
            with self.altered(binding,claimed),patch.object(clean,'closed_evidence',return_value=proof),\
                    self.assertRaisesRegex(ValueError,'logical round'):clean.load_frozen(binding)

    def test_wrong_parent_identity_or_round_marker_rejected(self):
        wrong=deepcopy(self.origin);wrong['parent']['id']='0'*64
        with self.altered(self.plan['origin'],wrong),self.assertRaises(ValueError):clean.round2_origin(self.value)
        for marker in (True,1,3,'2'):
            wrong=deepcopy(self.value);wrong['clean_learning_round']=marker
            with self.assertRaises(ValueError):clean.enabled(wrong)

    def test_honest_objective_and_legacy_source_set_unchanged(self):
        self.assertEqual(clean.research_task({}),clean.TASK)
        self.assertIn('adopted',clean.research_task(self.value));self.assertIn('3.12',clean.research_task(self.value))
        old=runtime.source_paths(model_budget=True,training=True,clean_slate=True)
        new=runtime.source_paths(model_budget=True,training=True,clean_slate=True,clean_round2=True)
        self.assertNotIn(clean.ROUND2_PLAN,old);self.assertEqual(set(new)-set(old),{clean.ROUND2_PLAN})
        with self.assertRaises(ValueError):runtime.source_paths(clean_round2=True)

    def test_scaffold_reanchors_same_adopted_bytes_not_empty_programs(self):
        sources=runtime.source_paths(clean_slate=True)
        pinned={k:engine.pin(Path(v)) for k,v in sources.items() if k in (
            'configs/earnings_coevolution/program_R0.py','configs/earnings_coevolution/program_H0.py','forecaster')}
        state=clean.scaffold(pinned,self.origin)
        self.assertEqual(state['stable_id'],self.origin['parent']['id'])
        self.assertEqual(len(state['versions']),1)
        self.assertEqual(state['versions'][state['stable_id']]['R'],self.origin['original_candidate']['R'])


class Round2ComparisonTests(unittest.TestCase):
    def setUp(self):
        fixtures.ComparisonTests.setUp(self)  # Existing inert saved-output fixture, not its test methods.
        self.baseline[0]['points']=4;self.baseline[0]['targets'][3]['points_awarded']=1
        self.baseline[1]['points']=4;self.baseline[1]['targets'][3]['points_awarded']=1
        self.baseline[2]['points']=4;self.baseline[2]['targets'][3]['points_awarded']=1
        feedback=engine.save(self.root/'parent-public.json',dict(rows=self.baseline))
        origin=engine.save(self.root/'origin.json',dict(public_feedback=feedback,prior_mean=3.12,parent=dict(id='adopted-parent')))
        self.descriptor.update(learning_round=2,parent_basis=origin)
        self.stack.enter_context(patch.object(clean,'round0_feedback',side_effect=AssertionError('No baseline reread/rerun for Round2 comparison')))

    def set_improved_companies(self,count):
        for i in range(count):
            path=self.root/str(i)/'population-public-feedback.json';saved=json.loads(path.read_bytes())
            saved['points']=4;saved['target_scores'][-1]['points_awarded']=1
            path.write_text(json.dumps(saved))
            self.verified[self.windows[i]['path']]['result']['result']['results'][0]['result']['points']=4

    def test_improvement_over_round0_but_below_parent_is_not_adopted(self):
        self.set_improved_companies(1);result=clean.compare(self.descriptor_binding,self.windows)
        self.assertEqual(result['candidate_mean'],3.04);self.assertEqual(result['parent_mean'],3.12)
        self.assertEqual(result['decision'],'RETAIN_ADOPTED_PARENT');self.assertFalse(result['next_mutation_allowed'])
        self.assertIn('parent_prediction',result['rows'][0]['targets'][0])
        self.assertNotIn('round0_prediction',result['rows'][0]['targets'][0])

    def test_full_parent_tie_retains_adopted_pair(self):
        self.set_improved_companies(3)
        self.assertEqual(clean.compare(self.descriptor_binding,self.windows)['decision'],'RETAIN_ADOPTED_PARENT')

    def test_only_full_strict_parent_improvement_adopts(self):
        self.set_improved_companies(4);result=clean.compare(self.descriptor_binding,self.windows)
        self.assertEqual(result['candidate_mean'],3.16);self.assertEqual(result['decision'],'ADOPT_CANDIDATE')
        self.assertFalse(result['next_mutation_allowed'])

    def test_partial_cannot_select_even_if_observed_companies_good(self):
        self.set_improved_companies(4);result=clean.compare(self.descriptor_binding,self.windows[:4])
        self.assertIsNone(result['candidate_mean']);self.assertEqual(result['decision'],'INCOMPLETE_NO_SELECTION')


class Round2AuthorReceivingTests(unittest.TestCase):
    def setUp(self):
        fixtures.AuthorReceivingTests.setUp(self)  # Actual DeltaAuthor/PreviewBroker/PopulationBroker, inert transport.
        from market_rsi import digest
        self.summary.update(logical_round=1,version_id=self.parent['id'],company_equal_mean=3.12)
        self.parent['method']='Adopted complete25 fixture parent, not empty scaffold or old control'
        Path(self.feedback['path']).write_text(json.dumps(self.summary));self.feedback=engine.pin(Path(self.feedback['path']))
        self.task['feedback']=self.feedback;self.chosen['feedback_sha256']=digest(self.feedback)
        self.context.update(feedback_binding=self.feedback,feedback_sha256=digest(self.feedback),
            task=clean.ROUND2_TASK,scaffold_semantics='Adopted previous complete25 R/H')
        self.context_path.write_text(json.dumps(self.context));self.base.population_context_binding=engine.pin(self.context_path)
        path=Path(self.runtime['path']);path.write_text(json.dumps(dict(clean_slate_policy=clean.POLICY,clean_learning_round=2)))
        self.base.clean_slate_runtime_binding=engine.pin(path)

    def test_real_author_broker_path_receives_all_prior125_and_adopted_parent(self):
        from earnings_open_program import program
        self.author.author(self.chosen,program(self.r.read_bytes(),'R'),str(self.root/'author-slot'),parent_binding=self.parent['R'])
        context=self.received[0]['research_context']
        self.assertEqual(context['training_comparator'],self.summary)
        self.assertEqual(sum(len(r['targets']) for r in context['training_comparator']['rows']),125)
        self.assertEqual(context['parent_version_id'],self.parent['id'])
        self.assertEqual(context['task'],clean.ROUND2_TASK)
        self.assertNotIn('prior_candidate',context)

    def test_stale_prior_feedback_cannot_reach_author_transport(self):
        from earnings_open_program import program
        wrong=deepcopy(self.context);wrong['feedback']['logical_round']=0
        self.context_path.write_text(json.dumps(wrong));self.base.population_context_binding=engine.pin(self.context_path)
        with self.assertRaises(ValueError):
            self.author.author(self.chosen,program(self.r.read_bytes(),'R'),str(self.root/'author-slot'),parent_binding=self.parent['R'])
        self.assertEqual(self.received,[])


if __name__=='__main__':unittest.main()
