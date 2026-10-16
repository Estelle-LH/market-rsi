from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from earnings_open_capacity import ProgramCapacity
from earnings_open_source_review import ProgramSourceReview
from earnings_open_program import candidate
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
from supervisor_harness import research_capacity_identity as identity


class ProgramCapacityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.source=self.root/'source';self.source.mkdir()
        files={'kernel.py':'pass\n','predictor.py':'pass\n','python':'fixture-runtime',
            'R0.py':"PROGRAM={'axis':'R'}\ndef run(p): return {}\n",
            'H0.py':"PROGRAM={'axis':'H','tools':[]}\ndef run(p): return {}\n"}
        for name,text in files.items(): (self.source/name).write_text(text)
        component=lambda name:{'sources':{name:engine.pin(self.source/name)['sha256']},'configuration_sha256':digest('fixed')}
        self.before=identity.manifest(kernel=component('kernel.py'),predictor=component('predictor.py'),
            harness=component('H0.py'),researcher=component('R0.py'),memory=digest('empty'),
            model={'requested_model':'gpt-6.1-sol','serving_snapshot':'unknown','serving_snapshot_verified':False},
            runtime={'python':engine.pin(self.source/'python'),'dependencies':{}})
        self.entries={'R':'R0.py','H':'H0.py'}
        now=datetime(2026,10,14,tzinfo=timezone.utc)
        self.batch=ContinuousDiscoveryBatch(self.root/'batch',allow_temporary=True,test_clock=lambda:now,allow_test_clock=True)
        self.batch.initialize(batch_id='program-fixture',start_utc=now,deadline_utc=now+timedelta(hours=1),
            max_attempts=9,active_pool_capacity=2,learning_checkpoint_version=1,
            initial_incumbent={'candidate_id':'fixture','candidate_sha256':self.before['C'],
                              'scorecard_sha256':digest('score'),'review_sha256':'0'*64})
        self.micro={'pair':engine.activation.pair(self.before),'fixed_context':{
            'model_sha256':self.before['M'],'evaluation_sha256':self.before['K'],
            'data_scope_sha256':digest('public'),'authority_sha256':digest('synthetic'),
            'resource_policy_sha256':digest('zero-paid')},
            'allowed_write_paths':{'researcher':['R0.py','R1.py'],'harness':['H0.py','H1.py']},
            'protected_paths':['kernel.py','predictor.py','python'],'reviewer_id':'host-reviewer'}
        self.batch.record_micro_evolution('initialize',self.micro,expected_state_sha256=self.batch.snapshot()['state_sha256'])
        self.capacity=self.restore()

    def restore(self):
        return ProgramCapacity(self.batch,source_root=self.source,registry_root=self.root/'versions',
                               baseline=self.before,entrypoints=self.entries)

    def specification(self, *, passed=True):
        self.chosen={'schema':'earnings_capacity_decision_v1','axis':'R','component':'research_policy',
            'parent_pair_sha256':digest(self.micro['pair']),'feedback_sha256':digest('feedback'),
            'hypothesis':'Try a new executable algorithm','expected_effect':'Fixture research program returns2'}
        source="PROGRAM={'axis':'R'}\nimport statistics\ndef helper(xs): return statistics.median(xs)\ndef run(p): return helper(p)\n"
        authored={'decision_sha256':digest(self.chosen),'source_text':source,
                  'test_text':"CASES=[{'input':[1,2,8],'expected':2}]"}
        parsed=candidate(authored,{'axis':'R'},self.chosen)
        descriptor={'parent_identity':self.before,'parent_entrypoints':self.entries,
            'parent_pair_sha256':self.chosen['parent_pair_sha256'],'decision_sha256':digest(self.chosen),
            'candidate':engine.save(self.root/'candidate.json',parsed),
            'author_original':engine.save(self.root/'author.json',authored),
            'micro_evolution':self.batch.snapshot()['micro_evolution']}
        class FixtureRunner:
            blocked=False
            def run(self, text, payload):
                return {'value':2 if passed else 9,'receipt':{'synthetic':True}}
        slot=str(self.root/'review')
        service=ProgramSourceReview(self.source,slots={slot:{'candidate_id':'new-program','R':'R1.py','H':'H1.py'}},
            proposer_id='actual-author-fixture',reviewer_id='host-reviewer',runner=FixtureRunner())
        return service.review(self.chosen,authored,descriptor,slot)

    def test_new_functions_materialized_exactly_and_resolved_without_host_import(self):
        spec=self.specification()
        self.assertIsNone(spec['review_receipt'])
        self.capacity.propose(spec['after'],spec['proposal'],spec['entrypoints'],static_review=spec['static_review'],
                              expected_state_sha256=self.batch.snapshot()['state_sha256'])
        pending=self.batch.snapshot()['micro_evolution']['pending']
        child=self.capacity.resolve('R',expected_pair_sha256=digest(self.micro['pair']),
                                    shadow_proposal_sha256=pending['record_sha256'])
        self.assertEqual(child['receipt']['source']['sha256'],engine.pin(self.source/'R1.py')['sha256'])
        self.assertFalse(child['receipt']['model_code_executed'])
        self.assertEqual(self.restore().resolve('R',expected_pair_sha256=digest(self.micro['pair']))['receipt']['source']['path'],str(self.source/'R0.py'))

    def test_failed_candidate_cases_rejected_by_native_keep_parent(self):
        spec=self.specification(passed=False)
        self.assertIsNotNone(spec['review_receipt'])
        self.capacity.propose(spec['after'],spec['proposal'],spec['entrypoints'],static_review=spec['static_review'],
                              expected_state_sha256=self.batch.snapshot()['state_sha256'])
        self.capacity.review(spec['review_receipt'],expected_state_sha256=self.batch.snapshot()['state_sha256'])
        state=self.batch.snapshot()['micro_evolution']
        self.assertEqual(state['active_pair'],self.micro['pair'])
        self.assertEqual(state['history'][-1]['review']['reason'],'PROGRAM_CASES_FAILED')
        self.assertTrue((self.source/'R1.py').is_file())

    def test_immutable_source_and_stale_pair_fail_closed(self):
        with self.assertRaises(ValueError):self.capacity.resolve('R',expected_pair_sha256='0'*64)
        (self.source/'R0.py').write_text("PROGRAM={'axis':'R'}\ndef run(p): return 'changed'\n")
        with self.assertRaises(ValueError):self.restore()

    def test_kernel_and_other_axis_preserved_in_program_proposal(self):
        spec=self.specification()
        self.assertEqual(identity.change_axis(self.before,spec['after']),'R')
        for key in ('K','C','M','H'):
            self.assertEqual(self.before[key],spec['after'][key])
        self.assertEqual(self.before['runtime'],spec['after']['runtime'])

    def test_synthetic_adoption_cold_resolution_and_real_native_rollback(self):
        spec=self.specification()
        self.capacity.propose(spec['after'],spec['proposal'],spec['entrypoints'],static_review=spec['static_review'],
                              expected_state_sha256=self.batch.snapshot()['state_sha256'])
        micro=self.batch.snapshot()['micro_evolution'];pending=micro['pending']
        binding={'proposal_sha256':pending['record_sha256'],'before_identity_sha256':digest(self.before),
            'after_identity_sha256':digest(spec['after']),'tested_pair_sha256':digest(pending['pair']),
            'anchor_pair_sha256':digest(micro['anchor_pair'])}
        checks=engine.save(self.root/'synthetic-checks.json', {'synthetic':True,'binding':binding,
            'checks':{name:True for name in engine.activation.micro.MICRO_CHECKS}})
        benefit=engine.save(self.root/'synthetic-benefit.json',dict(binding,matched_outputs_sha256=checks['sha256'],
            effect=pending['behavior_change'],benefit_observed=True,synthetic=True))
        review=engine.save(self.root/'synthetic-accept.json',{'review':{
            'reviewer_id':'host-reviewer','proposal_sha256':pending['record_sha256'],'decision':'accept',
            'reason':'SYNTHETIC_TRANSITION_FIXTURE_ONLY','tested_pair_sha256':binding['tested_pair_sha256'],
            'anchor_pair_sha256':binding['anchor_pair_sha256'],'checks':{name:{'passed':True,'evidence_sha256':checks['sha256']}
                for name in engine.activation.micro.MICRO_CHECKS},'benefit_observed':True,
            'benefit_evidence_sha256':benefit['sha256'],'actual_write_paths':pending['write_paths']},
            'evidence':{checks['sha256']:checks['path'],benefit['sha256']:benefit['path']}})
        self.capacity.review(review,expected_state_sha256=self.batch.snapshot()['state_sha256'])
        cold=self.restore()
        packet=cold.prepare(expected_pair_sha256=digest(pending['pair']),questions='public questions')
        self.assertEqual(packet['receipts'][0]['source']['path'],str(self.source/'R1.py'))
        state=self.batch.snapshot()
        proof=engine.save(self.root/'rollback-proof.json',{'passed':True,'from_pair':pending['pair'],
            'to_pair':self.micro['pair'],'before_state_sha256':state['state_sha256']})
        rollback=engine.save(self.root/'rollback.json',{'receipt':{'reviewer_id':'host-reviewer',
            'reason':'SYNTHETIC_ROLLBACK_FIXTURE','evidence_sha256':proof['sha256']},'evidence':proof})
        cold.rollback(rollback,expected_state_sha256=state['state_sha256'])
        self.assertEqual(self.batch.snapshot()['micro_evolution']['active_pair'],self.micro['pair'])
        self.assertEqual(len(self.batch.snapshot()['micro_evolution']['history']),2)


if __name__=='__main__':unittest.main()
