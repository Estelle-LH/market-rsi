"""Proposal-only prepare/metadata/stop contracts with explicit origin seams.

No live model/ledger/Native/candidate/scorer. Real producer and current metadata
are used on invented training fixtures; execution tests retain the original
once-only driver with inert handlers rather than invent seven-stage completion.
"""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch
import unittest

import earnings_population_run as run
import earnings_population_runtime as runtime
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness import feedback_linked_loop as driver
from test_earnings_population_frozen_panel_runtime import PanelFixture
import test_earnings_population_run as entry_fixture


class ProducerTests(PanelFixture):
    def setUp(self):
        super().setUp()
        self.authority=engine.save(self.root/'TRAIN25-DIRECT-NEW-CANDIDATE-AUTHORITY.json',
            dict(human_answer='让 Author 根据完整25家公司 Round0反馈提出新候选，旧34–36仅归档参考'))
        self.stack.enter_context(patch.object(runtime,'PROPOSAL_AUTHORITY',self.authority))
        self.stack.enter_context(patch.object(runtime,'PROPOSAL_ROUND0',self.comparator))
        self.stack.enter_context(patch.object(runtime,'PROPOSAL_ORIGIN',self.previous))

    def prepare_proposal(self,**changes):
        return self.prepare_panel(frozen_panel=None,new_panel_proposal=True,**changes)

    def test_new_task_exact25_round0_and_smoke_without_scores_or_pool_mutation(self):
        value=engine.read(self.prepare_proposal());study=engine.read(value['forecast_study'])
        task=runtime.proposal_task(value)
        self.assertEqual(task,runtime._proposal_metadata(value,study))
        self.assertEqual(task['training_companies'],self.scope['training'])
        self.assertEqual(task['round0_manifest'],self.comparator)
        self.assertEqual(task['authority'],self.authority)
        self.assertTrue(task['smoke_only']);self.assertEqual(task['smoke_company_id'],value['companies'][0])
        self.assertIn('all25',task['primary_task'])
        self.assertNotIn('frozen_panel_policy',value)
        self.assertEqual(value['additional_cap_nano_usd'],5_000_000_000)
        self.assertEqual(engine.read(value['initial_population']),self.origin['population'])
        self.assertFalse((self.root/'attempts'/self.id).exists())
        self.p1.assert_not_called()

    def test_mode_cannot_use_stage_attachment_panel_or_wrong_origin(self):
        for changes in ({'training_stage_attachment':{}},{'frozen_panel':self.descriptor_binding},
                        {'campaign_from':str(self.root/'attempts/edgar-population-20261016-99/population-run-result.json')}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                kw=dict(frozen_panel=None,new_panel_proposal=True);kw.update(changes)
                self.prepare_panel(**kw)
            self.assertFalse((self.root/'inputs'/self.id).exists())

    def test_heldout_refuses_before_input_or_task_contents(self):
        with self.assertRaises(ValueError):self.prepare_proposal(training_cik=self.p.heldout[0])
        self.old_loader.assert_not_called();self.assertFalse((self.root/'inputs'/self.id).exists())

    def test_legacy_absence_is_inert_and_new_marker_erasure_refuses(self):
        value=engine.read(self.prepare(identifier=self.id,attachment=False))
        self.assertIsNone(runtime.proposal_task(value))
        self.id='edgar-population-20261016-38'
        value=engine.read(self.prepare_proposal());study=engine.read(value['forecast_study'])
        for where in ('runtime','study'):
            v,s=deepcopy(value),deepcopy(study)
            (v if where=='runtime' else s).pop('training_proposal_policy' if where=='runtime' else 'training_proposal_task')
            with self.subTest(where=where),self.assertRaises(ValueError):runtime._proposal_metadata(v,s)
        v,s=deepcopy(value),deepcopy(study)
        v.pop('training_proposal_policy');s.pop('training_proposal_task')
        with self.assertRaises(ValueError):runtime._proposal_metadata(v,s)

    def test_task_tamper_reorder_or_primary_wording_drift_refuses(self):
        value=engine.read(self.prepare_proposal());study=engine.read(value['forecast_study'])
        task=engine.read(study['training_proposal_task']);path=Path(study['training_proposal_task']['path'])
        for key,bad in (('training_companies',task['training_companies'][::-1]),('smoke_only',False),
                ('primary_task','Optimize only this one company'),('authority',None),('archive_only_version_ids',[])):
            changed=deepcopy(task);changed[key]=bad
            path.write_text(json.dumps(changed));s=deepcopy(study);s['training_proposal_task']=engine.pin(path)
            with self.subTest(key=key),self.assertRaises(ValueError):runtime._proposal_metadata(value,s)


class StopBeforeExecuteTests(unittest.TestCase):
    def setUp(self):
        self.f=entry_fixture.ExecutionContracts(methodName='runTest');self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.value=self.f.value;self.root=self.f.root;self.owner=self.f.owner;self.loop=self.f.loop
        self.value['training_proposal_policy']='round0_new_panel_candidate_v1'
        self.value['companies']=self.f.ciks[:1]
        self.stack=self.enterContext(__import__('contextlib').ExitStack())
        self.stack.enter_context(patch.object(run,'preflight',return_value=self.value))
        self.real_driver_events=[]
        self.loop.side_effect=self.prefix

    def prefix(self,root,initial,companies,roles,*,admit,**kwargs):
        # Stage callbacks are invented; original driver/admit/claims/seals are
        # real. No source/Native/model attribution is inferred from callbacks.
        identity={s:{'inert_handler':s} for s in driver.STAGES}
        def handler(stage):
            def invoke(ctx):
                self.real_driver_events.append(stage)
                if stage=='implement':return {'candidate':None}
                if stage=='source_review':return {'accepted_for_exploration':False,'evidence':[]}
                return {'inert_stage':stage}
            return invoke
        return driver.run(root/'loop',{s:handler(s) for s in driver.STAGES},seed={},
            admit=admit,max_rounds=1,handler_identity=lambda:identity)

    def test_original_driver_stops_before_claim_and_receipt_is_not_completion(self):
        result=engine.read(run.execute(self.f.bound()))
        self.assertEqual(result['schema'],'earnings_training25_proposal_result_v1')
        self.assertEqual(result['status'],'PROPOSAL_NOT_ACCEPTED')
        self.assertEqual(self.real_driver_events,list(driver.STAGES[:4]))
        self.assertEqual(result['result'],dict(status='stopped',completed_rounds=0,round_index=1,stage='execute'))
        self.assertEqual(len(result['proposal_stages']),4)
        self.assertFalse((self.root/'loop/round-0001-execute.claim.json').exists())
        self.assertFalse((self.root/'population-run-result.json').exists())
        self.assertTrue(self.f.closed)

    # Do not inherit unrelated default-execution assertions under new mode.
    def test_fresh_proposal_owner_failure_is_not_ordinary_population_failure(self):
        self.f.owner_enter_failure=True
        with self.assertRaisesRegex(RuntimeError,'owner admission'):run.execute(self.f.bound())
        failure=engine.read(engine.pin(self.root/'training-proposal-failure.json'))
        self.assertFalse(failure['retry_allowed'])
        self.assertFalse((self.root/'population-run-failure.json').exists())

    def test_no_redundant_replay_for_a_stage_that_will_not_be_claimed(self):
        # This is only the no-action branch; actual Review/owner terminal
        # expiry guards remain original and are not waived by this fixture.
        def before_actions(binding):
            if len(self.real_driver_events)==4:
                raise AssertionError('No further stage may be admitted after the four-stage proposal')
            return self.value
        with patch.object(run,'preflight',side_effect=before_actions):
            result=engine.read(run.execute(self.f.bound()))
        self.assertEqual(result['status'],'PROPOSAL_NOT_ACCEPTED')
        self.assertEqual(self.real_driver_events,list(driver.STAGES[:4]))
        self.assertFalse((self.root/'loop/round-0001-execute.claim.json').exists())


if __name__=='__main__':unittest.main()
