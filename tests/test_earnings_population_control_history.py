"""Historical contract bridge; invented replay origins, no API/scorer execution.

Optional actual14/11/07 structural replay reads only saved public own artifacts;
it is explicitly not full live admission, source authority or model consumption.
"""
from copy import deepcopy
import builtins
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import unittest
from unittest.mock import patch

import earnings_population_campaign as campaign
import earnings_population_campaign_admission as admission
import earnings_population_run as run
import earnings_population_tasks as tasks
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_campaign as fixtures


class HistoryBridgeTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.CampaignContracts();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.owned=self.f.root/'owned';self.ident='edgar-population-20261016-07'
        self.f.loop_root=self.owned/'attempts'/self.ident
        self.current={'schema':'synthetic_fixed_contract','data':{'fixed':'original'},
            'model':{'fixed':'original'},'limits':{
                'controller':{'wall_seconds':900,'max_input_tokens':32000,'max_output_tokens':16384},
                'review':{'wall_seconds':900,'max_input_tokens':20000,'max_output_tokens':16384},
                'author':{'wall_seconds':1200,'max_input_tokens':48000,'max_output_tokens':49152},
                'forecast':{'wall_seconds':1800,'max_input_tokens':100000,'max_output_tokens':25000}}}
        self.historical=deepcopy(self.current)
        for role,wall in (('controller',600),('review',600),('author',900)):
            self.historical['limits'][role]['wall_seconds']=wall
        self.f.contract=self.historical;self.f.accepted=[True,False];self.f.retire_latest=True
        self.result=self.f.run_campaign()['result'];self.state=self.result['population']
        self.score=self.result['last_scored_feedback'];self.latest=self.result['feedback']
        self.original_scored_feedback=engine.read(self.score)
        self.inputs=self.owned/'inputs'/self.ident
        self.serial=0
        self.old_manifest=engine.read(self.f.manifest())
        self.runtime_binding=self.history_runtime(self.old_manifest)
        self.origin={'population':self.state,'research_feedback':engine.read(self.latest),
            'last_scored_feedback':self.score,'evidence':[self.runtime_binding,self.runtime_binding]}
        self.root_patch=patch.object(admission,'ROOT',self.owned);self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def save(self,name,value):
        self.serial+=1
        path=self.f.root/f'case-{self.serial}'/name;path.parent.mkdir(parents=True)
        return engine.save(path,value)

    def history_runtime(self,manifest,**changes):
        # All canonical historical inputs are fresh fixture files, not production.
        self.inputs.mkdir(parents=True,exist_ok=True)
        def save(name,value):
            path=self.inputs/name
            path.write_text(json.dumps(value,sort_keys=True));return engine.pin(path)
        study=save('study.json',{'campaign':save('campaign.json',manifest)})
        return save('runtime-reviewed.json',dict(id=self.ident,root=str(self.f.loop_root),forecast_study=study,**changes))

    def origin_for_contract(self,contract):
        runtime=self.history_runtime(dict(self.old_manifest,contract=deepcopy(contract)))
        score=dict(self.original_scored_feedback,campaign_contract_sha256=digest(contract))
        Path(self.score['path']).write_text(json.dumps(score))
        return dict(self.origin,evidence=[runtime,runtime],last_scored_feedback=engine.pin(Path(self.score['path'])))

    def manifest(self,**changes):
        value=dict(self.old_manifest,initial_population_sha256=digest(self.state),initial_feedback=self.latest,
            last_scored_feedback=self.score,contract=deepcopy(self.current),comparison_policy=campaign.PARENT_COMPARISON,
            **run._feedback_contract_fields(self.origin,self.current))
        value.update(changes)
        return self.save('campaign.json',value)

    def load(self,binding):return campaign.load(binding,self.state,campaign.PANEL*2,2)

    def test_producer_structural_consumer_preserve_distinct_immutable_contracts(self):
        bound=self.manifest();value=self.load(bound)
        self.assertEqual(value['last_scored_contract_sha256'],digest(self.historical))
        self.assertEqual(value['initial_feedback_contract_sha256'],digest(self.historical))
        self.assertEqual(value['contract'],self.current)
        self.assertEqual(engine.read(self.score)['campaign_contract_sha256'],digest(self.historical))
        self.assertEqual(engine.read(self.latest)['results'],[])
        self.assertEqual(engine.read(self.score)['results'],self.f.feedback_at(1)['results'])

    def test_old_no_field_manifest_retains_original_same_contract_rule(self):
        value=engine.read(self.manifest());value.pop('last_scored_contract_sha256')
        with self.assertRaisesRegex(ValueError,'scored/matched'):self.load(self.save('campaign.json',value))
        value['contract']=self.historical
        self.load(self.save('campaign.json',value))

    def test_future_unscored_current_contract_keeps_separate_older_score(self):
        latest=deepcopy(self.origin['research_feedback']);latest['campaign_contract_sha256']=digest(self.current)
        self.origin['research_feedback']=latest;self.latest=self.save('feedback-02.json',latest)
        value=self.load(self.manifest())
        self.assertEqual(value['initial_feedback_contract_sha256'],digest(self.current))
        self.assertEqual(value['last_scored_contract_sha256'],digest(self.historical))
        self.assertEqual(value['last_scored_feedback'],self.score)

    def test_digest_types_forgery_and_nonresumed_policy_refused(self):
        valid=engine.read(self.manifest())
        for token in (None,True,{},'bad','f'*64):
            with self.subTest(token=token),self.assertRaises(ValueError):
                self.load(self.save('campaign.json',dict(valid,last_scored_contract_sha256=token)))
        value=deepcopy(valid);value.pop('comparison_policy')
        with self.assertRaises(ValueError):self.load(self.save('campaign.json',value))

    def test_original_runtime_binding_must_be_unique_exact_and_attempt_owned(self):
        for evidence in ([],[dict(self.runtime_binding,sha256='f'*64)],
                         [self.runtime_binding,dict(self.runtime_binding,sha256='e'*64)]):
            with self.subTest(evidence=evidence),self.assertRaises(ValueError):
                run._feedback_contract_fields(dict(self.origin,evidence=evidence),self.current)
        value=engine.read(self.runtime_binding);value['id']='edgar-population-20261016-99'
        Path(self.runtime_binding['path']).write_text(json.dumps(value))
        origin=dict(self.origin,evidence=[engine.pin(Path(self.runtime_binding['path']))])
        with self.assertRaisesRegex(ValueError,'attempt mismatch'):
            run._feedback_contract_fields(origin,self.current)

    def test_fixed_task_model_token_forecast_or_nonexact_wall_transition_refused(self):
        mutations=[('data',{'fixed':'changed'}),('model',{'fixed':'changed'})]
        for key,value in mutations:
            changed=deepcopy(self.current);changed[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'fixed task'):
                run._feedback_contract_fields(self.origin,changed)
        for role,key,value in [('author','max_input_tokens',48001),('forecast','wall_seconds',1801),
                               ('review','wall_seconds',901),('controller','wall_seconds',600)]:
            changed=deepcopy(self.current);changed['limits'][role][key]=value
            with self.subTest(role=role,key=key),self.assertRaises(ValueError):
                run._feedback_contract_fields(self.origin,changed)

    def test_wrong_score_company_and_original_contract_digest_refused(self):
        original=engine.read(self.score)
        for changes in ({'company_id':'CIK0000021076'},{'campaign_contract_sha256':'a'*64},
                        {'kind':'review_rejected'},{'score_state':'unscored'}):
            Path(self.score['path']).write_text(json.dumps(dict(original,**changes)))
            altered=dict(self.origin,last_scored_feedback=engine.pin(Path(self.score['path'])))
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                run._feedback_contract_fields(altered,self.current)

    def test_foreign_score_and_source_study_are_refused_without_following_alias(self):
        foreign=dict(self.score,path=str(self.f.root/'foreign'/'feedback-01.json'))
        with patch.object(campaign,'_read',side_effect=AssertionError('Must refuse before read')):
            with self.assertRaises(ValueError):
                run._feedback_contract_fields(dict(self.origin,last_scored_feedback=foreign),self.current)
        runtime=engine.read(self.runtime_binding)
        runtime['forecast_study']=self.save('study.json',{'campaign':self.f.manifest()})
        Path(self.runtime_binding['path']).write_text(json.dumps(runtime))
        with self.assertRaisesRegex(ValueError,'Canonical source-bound'):
            run._feedback_contract_fields(dict(self.origin,evidence=[engine.pin(Path(self.runtime_binding['path']))]),self.current)

    def test_equal_current_and_historical_contract_needs_no_counterfactual_relabel(self):
        self.assertEqual(admission.last_scored_contract_sha256(self.origin,self.historical),digest(self.historical))

    def test_float_bool_wall_or_other_numeric_type_drift_refused(self):
        for role,wall in (('controller',900.0),('review',True),('author',1200.0)):
            changed=deepcopy(self.current);changed['limits'][role]['wall_seconds']=wall
            with self.subTest(role=role),self.assertRaisesRegex(ValueError,'integer'):
                run._feedback_contract_fields(self.origin,changed)
        changed=deepcopy(self.current);changed['limits']['author']['max_input_tokens']=48000.0
        with self.assertRaisesRegex(ValueError,'integer'):
            run._feedback_contract_fields(self.origin,changed)

    def test_forward_Author_input_is_independent_of_existing_exact_wall_transition(self):
        # Eighteen independent (old/equal-new/forward) combinations. Metadata and
        # scored awards are synthetic, while original evidence-bound joins run.
        for old_walls,new_walls in ((False,False),(False,True),(True,True)):
            for before,after in ((48000,48000),(48000,64000),(64000,64000),
                                 (48000,96000),(64000,96000),(96000,96000)):
                old=deepcopy(self.current if old_walls else self.historical)
                new=deepcopy(self.current if new_walls else self.historical)
                old['limits']['author']['max_input_tokens']=before
                new['limits']['author']['max_input_tokens']=after
                origin=self.origin_for_contract(old);saved=Path(origin['last_scored_feedback']['path']).read_bytes()
                with self.subTest(old_walls=old_walls,new_walls=new_walls,before=before,after=after):
                    self.assertEqual(admission.last_scored_contract_sha256(origin,new),digest(old))
                    self.assertEqual(Path(origin['last_scored_feedback']['path']).read_bytes(),saved)
                    self.assertEqual(engine.read(origin['last_scored_feedback'])['results'],self.original_scored_feedback['results'])

    def test_Author_input_downgrade_other_values_or_numeric_types_refused(self):
        for before,after in ((64000,48000),(96000,64000),(96000,48000),(48000,96001),
                             (48000,95000),(64000,100000),(40000,96000),(48000,96000.0),
                             (48000,48001),(48000,64001),(40000,64000),
                             (48000,64000.0),(48000,True),(48000.0,48000.0),(64000.0,64000),
                             (False,False)):
            old=deepcopy(self.current);new=deepcopy(self.current)
            old['limits']['author']['max_input_tokens']=before;new['limits']['author']['max_input_tokens']=after
            origin=self.origin_for_contract(old)
            with self.subTest(before=before,after=after),self.assertRaises(ValueError):
                admission.last_scored_contract_sha256(origin,new)

    def test_permitted_input_transition_does_not_waive_other_task_or_resource_changes(self):
        origin=self.origin_for_contract(self.current)
        for role,key,value in (('author','max_output_tokens',49153),('controller','max_input_tokens',32001),
                               ('review','max_input_tokens',20001),('forecast','max_input_tokens',100001),
                               ('author','wall_seconds',1201)):
            new=deepcopy(self.current);new['limits']['author']['max_input_tokens']=96000
            new['limits'][role][key]=value
            with self.subTest(role=role,key=key),self.assertRaises(ValueError):
                admission.last_scored_contract_sha256(origin,new)
        for key in ('data','model'):
            new=deepcopy(self.current);new['limits']['author']['max_input_tokens']=96000
            new[key]={'fixed':'tampered'}
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'fixed task'):
                admission.last_scored_contract_sha256(origin,new)

    def test_historical_float_wall_refused_even_when_current_contract_is_identical(self):
        historical=deepcopy(self.historical);historical['limits']['controller']['wall_seconds']=600.0
        manifest=dict(self.old_manifest,contract=historical)
        runtime=self.history_runtime(manifest)
        score=dict(engine.read(self.score),campaign_contract_sha256=digest(historical))
        Path(self.score['path']).write_text(json.dumps(score))
        origin=dict(self.origin,evidence=[runtime],last_scored_feedback=engine.pin(Path(self.score['path'])))
        for current in (self.current,historical):
            with self.subTest(equal=current==historical),self.assertRaisesRegex(ValueError,'integer'):
                run._feedback_contract_fields(origin,current)

    def test_trusted_admission_receiver_rejects_forged_digest_after_original_join(self):
        # The already-existing synthetic original replay seam stays explicit.
        # This tests receiving order/comparison, not real historical admission.
        import test_earnings_population_resume03_integration as resume_fixtures
        f=resume_fixtures.ResumeAdmission();f.setUp();self.addCleanup(f.doCleanups)
        f.refresh(feedback=f.origin['research_feedback'],manifest_changes={
            'comparison_policy':campaign.PARENT_COMPARISON,
            'initial_feedback_contract_sha256':f.origin['research_feedback']['campaign_contract_sha256'],
            'last_scored_contract_sha256':'f'*64})
        f.study['campaign_resume']=f.resume_binding
        with patch.object(admission,'last_scored_contract_sha256',return_value='a'*64) as original_contract, \
             patch.object(campaign,'load') as structural:
            with self.assertRaisesRegex(ValueError,'independently replayed original'):
                admission.validate(f.value,f.study,f.state)
        f.resume_loader.assert_called_once()
        original_contract.assert_called_once_with(f.origin,admission.scientific_contract(f.resident))
        structural.assert_not_called()


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_CONTROL_HISTORY')=='1',
                     'Explicit own14/11/07 public structural audit opt-in required')
class ActualHistoryBridge(unittest.TestCase):
    def test_original14_failure_to_verified11_origin_and07_score_structural_join(self):
        root=admission.ROOT;inputs=root/'inputs'/'edgar-population-20261016-14'
        opened=[];original_io=io.open;original_builtin=builtins.open
        def guard(original):
            def guarded(file,mode='r',*args,**kwargs):
                if any(flag in mode for flag in 'wax+'):raise AssertionError('No writes')
                if isinstance(file,(str,os.PathLike)):
                    path=Path(file);name=str(path).lower()
                    if ('qa' in path.name.lower() or path.name.lower()=='score.json') and mode!='rb':
                        raise AssertionError('Only existing opaque hash validation, never QA/raw score decode')
                    if 'cik0000021076' in name:
                        raise AssertionError('No held-out company body')
                    opened.append(str(path))
                return original(file,mode,*args,**kwargs)
            return guarded
        with patch.object(io,'open',guard(original_io)),patch.object(builtins,'open',guard(original_builtin)), \
             patch.object(socket,'socket',side_effect=AssertionError('No network')), \
             patch.object(sqlite3,'connect',side_effect=AssertionError('No ledger')):
            origin=engine.read(engine.pin(inputs/'campaign-origin.json'))
            manifest=engine.read(engine.pin(inputs/'campaign.json'))
            state=engine.read(engine.pin(inputs/'initial-population.json'))
            self.assertEqual(origin['previous_result']['sha256'],'f824117406c21e252c0c234a0c593f114b5e2eecf678f036b2dea124b006a96a')
            self.assertEqual(origin['last_scored_feedback']['sha256'],'170098840c76fd15e192b626526baede6a9d5214e762a73a27cd580f4a8a46b9')
            self.assertEqual(state,origin['population'])
            self.assertEqual(engine.read(manifest['initial_feedback']),origin['research_feedback'])
            self.assertEqual(origin['research_feedback']['score_state'],'unscored')
            self.assertEqual(origin['research_feedback']['results'],[])
            with self.assertRaisesRegex(ValueError,'scored/matched'):
                campaign.load(engine.pin(inputs/'campaign.json'),state,campaign.PANEL*manifest['max_decisions'],manifest['max_decisions'])
            fields=run._feedback_contract_fields(origin,manifest['contract'])
            self.assertEqual(fields['last_scored_contract_sha256'],'03a2962c91fb8e5f37ea21e58819f5b0dfe23d994154dd4b31654aebb75467cc')
            # Exercise the actual prospective96k contract through original07
            # score/runtime/study/campaign bindings, not a mocked feedback seam.
            origin21=engine.read(engine.pin(root/'inputs/edgar-population-20261016-21/campaign-origin.json'))
            current96=admission.scientific_contract(tasks.resident(campaign.PANEL[0]))
            self.assertEqual(current96['limits']['author']['max_input_tokens'],96000)
            fields96=run._feedback_contract_fields(origin21,current96)
            self.assertEqual(fields96['last_scored_contract_sha256'],fields['last_scored_contract_sha256'])
            self.assertEqual(origin21['last_scored_feedback'],origin['last_scored_feedback'])
        # A prospective manifest is materialized only in a temporary test root.
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            candidate=engine.save(Path(temp)/'prospective.json',dict(manifest,**fields))
            with patch.object(io,'open',guard(original_io)),patch.object(builtins,'open',guard(original_builtin)), \
                 patch.object(socket,'socket',side_effect=AssertionError('No network')), \
                 patch.object(sqlite3,'connect',side_effect=AssertionError('No ledger')):
                actual=campaign.load(candidate,state,campaign.PANEL*manifest['max_decisions'],manifest['max_decisions'])
            self.assertEqual(actual['last_scored_feedback'],origin['last_scored_feedback'])
            self.assertEqual(actual['initial_feedback'],manifest['initial_feedback'])
            self.assertEqual(actual['contract'],manifest['contract'])
        self.assertTrue(any('/edgar-population-20261016-07/campaign.json' in path for path in opened))


if __name__=='__main__':unittest.main()
