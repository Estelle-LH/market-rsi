import json
import copy
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from codex_glm_provider import successful_submission
from historical_grid_learning import read_inputs
from historical_grid_learning_controller import Broker,FILES,TOOLS,assess_activity,failed_pre_fit_evidence,carry_completed_diagnostic
from historical_grid_learning_controller import pairing_audit_evidence
from historical_grid_learning_controller import RECORDED_FILES,validate_workspace,require_recorded_compatibility
from historical_trade_windows import RecordedTradeWindows,SOURCE
from historical_learning_diagnostics import missing_profiles, plan_difference, diagnose
from market_rsi import digest,file_hash,fresh_json,load_json
import test_historical_grid_learning as fixtures


class GridLearningBrokerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.inputs,self.plan=fixtures.GridLearningTests().fixture()
        i=self.inputs;x=i['x'];y=i['y'];n=len(x['row_id'])
        for name in ['features','trials']:(self.root/name).mkdir()
        np.savez_compressed(self.root/'current-inputs.npz',
            **{k:x[k] for k in ['row_id','entity','decision_ms','date','values']},field_names=np.array(i['names']))
        np.savez_compressed(self.root/'primary-labels.npz',
            row_id=x['row_id'],decision_ms=x['decision_ms'],delta_probability=y['delta_probability'],
            delta_probability_bps=y['delta_probability']*10000,label_available_ms=y['label_available_ms'],
            available=y['available'],future_observation_count=np.ones(n,dtype=np.int64),reason=np.array(['covered']*n))
        spec={'window_end_ms':60000}
        objective={'primary_query_id':'q1','queries':{'q1':{'spec':spec}},'primary_metric':'mse_skill_vs_persistence'}
        objective['proposal_sha256']=digest(objective);fresh_json(self.root/'objective-proposal.json',objective)
        data={'plan':{'open_train_utc_dates':sorted(set(x['date'])),'cadence_ms':60000}}
        data['proposal_sha256']=digest(data);fresh_json(self.root/'data-use-proposal.json',data)
        results={'input-result.json':{'complete':True,'labels_present':False,'fresh_holdout':False,'panel_sha256':'a'*64,
                     'archive_sha256':file_hash(self.root/'current-inputs.npz'),'rows':n,'field_names':i['names']},
                 'label-result.json':{'complete':True,'training_admitted':False,'fresh_holdout':False,'panel_sha256':'a'*64,
                     'proposal_sha256':objective['proposal_sha256'],'primary_query_id':'q1','queries':{'q1':{'spec':spec,
                     'archive_sha256':file_hash(self.root/'primary-labels.npz'),'rows':n}}},
                 'panel-result.json':{'fresh_holdout':False,'panel_sha256':'a'*64,'summary':{'entity_mapping':[
                     {'entity_code':0,'market_slug':'a'},{'entity_code':1,'market_slug':'b'}]}}}
        for name,v in results.items():v['result_sha256']=digest(v);fresh_json(self.root/name,v)
        fresh_json(self.root/'archive.json',{})
        fresh_json(self.root/'literature.json',{'mode':'frozen_notes','papers':[]})
        fresh_json(self.root/'workspace.json',{'schema':'historical_grid_learning_workspace_v1',
            'files':{n:file_hash(self.root/n) for n in FILES},'dev_present':False,'test_present':False})
        self.broker=Broker(self.root)

    def tearDown(self):self.temp.cleanup()

    def inspect(self):
        self.broker.call('inspect_learning_contract',{});self.broker.call('inspect_learning_library',{})

    def profile(self,spec=None,name='f1'):
        return self.broker.call('profile_feature',{'query_id':name,'spec':spec or self.plan['features'][0],'rationale':'fixture'})

    def trial(self,name='t1',parent='',plan=None):
        return self.broker.call('evaluate_learning_plan',{'trial_id':name,'parent_trial_id':parent,'plan':plan or self.plan})

    def test_real_fit_and_first_terminal_handshake(self):
        self.inspect();self.profile();result=self.trial()
        self.assertEqual(result['report']['fit_rows'],6)
        terminal=self.broker.call('submit_grid_learning_decision',{'action':'select','trial_id':'t1','reason':'fixture'})
        request={'input':[{'type':'function_call','call_id':'c1','name':'submit_grid_learning_decision','namespace':'mcp__controller_tools'},
            {'type':'function_call_output','call_id':'c1','output':json.dumps(terminal)}]}
        self.assertEqual(successful_submission(request,'submit_grid_learning_decision'),'c1')
        self.assertTrue(assess_activity(self.root)['valid'])
        with self.assertRaisesRegex(ValueError,'already submitted'):self.trial('t2')

    def test_library_exposes_exact_nested_model_shape(self):
        lib=self.broker.call('inspect_learning_library',{})
        self.assertEqual(set(lib['model_schema']['required']),{'algorithm','parameters'})
        self.assertEqual(set(lib['model_schema']['properties']),{'algorithm','parameters'})

    def test_conditional_tool_claims_diagnostic_without_prediction_refit(self):
        from unittest.mock import patch
        self.inspect();self.profile();self.trial()
        before={p.name:file_hash(p) for p in (self.root/'trials/t1').iterdir()}
        arguments={'query_id':'d1','trial_id':'t1','feature_name':'x','control_names':[], 'rationale':'synthetic mechanics test'}
        with patch('historical_grid_learning_controller.evaluate',side_effect=AssertionError('prediction refit')):
            r=self.broker.call('diagnose_feature_controls',arguments)
        self.assertEqual(r['nuisance_regressions_fitted'],4)
        self.assertEqual(r['prediction_model_trials_started'],0)
        self.assertEqual(before,{p.name:file_hash(p) for p in (self.root/'trials/t1').iterdir()})
        self.assertEqual(len(list((self.root/'trials').iterdir())),1)
        self.assertTrue(load_json(self.root/'conditional-diagnostics/d1/claim.json')['frozen_before_execution'])
        with self.assertRaisesRegex(ValueError,'already claimed'):
            self.broker.call('diagnose_feature_controls',{**arguments,'query_id':'d2'})
        self.broker.call('submit_grid_learning_decision',{'action':'defer','trial_id':'t1','reason':'test'})
        self.assertTrue(assess_activity(self.root)['valid'])

    def test_conditional_result_mutation_rejected(self):
        self.inspect();self.profile();self.trial()
        a={'query_id':'d1','trial_id':'t1','feature_name':'x','control_names':[], 'rationale':'test'}
        self.broker.call('diagnose_feature_controls',a)
        p=self.root/'conditional-diagnostics/d1/result.json';value=load_json(p)
        value['check']['raw_pearson_ic']=.333
        p.write_text(json.dumps(value))
        with self.assertRaises(ValueError):self.broker.call('inspect_learning_library',{})

    def test_conditional_failure_retains_claim_and_forbids_retry(self):
        from unittest.mock import patch
        self.inspect();self.profile();self.trial()
        a={'query_id':'d1','trial_id':'t1','feature_name':'x','control_names':[], 'rationale':'test'}
        with patch('historical_grid_learning_controller.diagnose_conditional',side_effect=ValueError('fixture failure')):
            with self.assertRaisesRegex(ValueError,'fixture failure'):self.broker.call('diagnose_feature_controls',a)
        self.assertTrue((self.root/'conditional-diagnostics/d1/failure.json').exists())
        with self.assertRaisesRegex(ValueError,'already claimed'):
            self.broker.call('diagnose_feature_controls',{**a,'query_id':'d2'})

    def test_error_balance_attachment_binds_all_trials_and_original_metrics(self):
        from historical_grid_learning_controller import error_balance_evidence
        self.inspect();self.profile();trial=self.trial()
        with tempfile.TemporaryDirectory() as directory:
            session=Path(directory)/'prior';old=session/'workspace';shutil.copytree(self.root,old)
            output=Path(directory)/'balance';output.mkdir()
            files=[old/n for n in ('current-inputs.npz','primary-labels.npz','workspace.json')]
            files.extend((old/'trials/t1').iterdir())
            fresh_json(output/'claim.json',{'input_hashes':{str(p.resolve()):file_hash(p) for p in files}})
            audit={'schema':'historical_prediction_error_balance_v1','passed':True,'session_id':session.name,
                'claim_sha256':file_hash(output/'claim.json'),'new_prediction_fits':0,'new_nuisance_fits':0,
                'new_provider_calls':0,'rows_removed':0,'prediction_values_changed':False,'fresh_holdout':False,
                'trials':[{'trial_id':'t1','trial_result_sha256':trial['result_sha256'],
                    'all':{k:trial['report']['score'][k] for k in ('model_mse_probability','persistence_mse_probability')}}]}
            def write(value):
                value.pop('result_sha256',None);value['result_sha256']=digest(value)
                (output/'audit.json').write_text(json.dumps(value))
            write(audit)
            attached=error_balance_evidence(output/'audit.json',session,self.root)
            self.assertEqual(attached['evidence'],audit)
            wrong=copy.deepcopy(audit);wrong['trials'][0]['all']['model_mse_probability']+=.1;write(wrong)
            with self.assertRaisesRegex(ValueError,'score changed'):
                error_balance_evidence(output/'audit.json',session,self.root)
            missing=copy.deepcopy(audit);missing['trials']=[];write(missing)
            with self.assertRaisesRegex(ValueError,'all original trial'):
                error_balance_evidence(output/'audit.json',session,self.root)
            write(audit)
            with (old/'trials/t1/predictions.npz').open('ab') as stream:stream.write(b'changed')
            with self.assertRaisesRegex(ValueError,'original inputs changed'):
                error_balance_evidence(output/'audit.json',session,self.root)

    def test_alias_error_identifies_exact_missing_spec_without_changing_gate(self):
        self.inspect();p=self.profile();plan=copy.deepcopy(self.plan)
        plan['features'][0]['name']='cosmetic-new-name'
        before=digest(plan)
        with self.assertRaisesRegex(ValueError,'cosmetic-new-name.*same_formula_different_names'):
            self.trial(plan=plan)
        self.assertEqual(digest(plan),before)
        self.assertFalse((self.root/'protocol.json').exists())
        self.assertEqual(list((self.root/'trials').iterdir()),[])
        self.assertEqual(missing_profiles(plan['features'],[p])[0]
            ['same_formula_different_names'][0]['profiled_name'],p['spec']['name'])
        # Correct formula is not automatically substituted. Existing exact spec still succeeds.
        self.trial()

    def test_different_parameter_is_not_a_cosmetic_alias(self):
        spec=copy.deepcopy(self.plan['features'][0]);other=copy.deepcopy(spec)
        other['minimum_window_coverage']=0.5
        missing=missing_profiles([other],[{'query_id':'old','spec':spec}])
        self.assertEqual(missing[0]['same_formula_different_names'],[])

    def test_existing_trial_explanation_does_not_refit_or_change_predictions(self):
        from unittest.mock import patch
        self.inspect();self.profile();trial=self.trial()
        paths=list((self.root/'trials/t1').iterdir());before={p.name:file_hash(p) for p in paths}
        with patch('historical_grid_learning_controller.evaluate',side_effect=AssertionError('unexpected refit')):
            report=self.broker.call('inspect_learning_trial',{'trial_id':'t1'})
        self.assertEqual(report['fits'],0)
        self.assertEqual(report['check']['population_rows'],6)
        self.assertEqual(report['check']['labelled_rows'],6)
        self.assertIsNone(report['projection']['actual_clipped_rows'])
        self.assertEqual(report['trial_result_sha256'],trial['result_sha256'])
        self.assertEqual(before,{p.name:file_hash(p) for p in paths})
        with self.assertRaises(ValueError):self.broker.call('inspect_learning_trial',{'trial_id':'../escape'})

    def test_parent_diff_reports_removal_and_addition_not_just_additions(self):
        parent=copy.deepcopy(self.plan);candidate=copy.deepcopy(parent)
        candidate['features'][0]['name']='replacement'
        diff=plan_difference(parent,candidate)
        self.assertEqual(diff['added_features'],['replacement'])
        self.assertEqual(diff['removed_features'],[parent['features'][0]['name']])
        self.assertEqual(diff['changed_nonfeature_fields'],[])

    def test_protocol_closure_never_profiles_or_fits(self):
        from unittest.mock import patch
        self.inspect();self.profile();self.trial()
        archive=load_json(self.root/'archive.json');archive['terminal_protocol_recovery']={'fixture':True}
        (self.root/'archive.json').write_text(json.dumps(archive))
        manifest=load_json(self.root/'workspace.json');manifest['files']['archive.json']=file_hash(self.root/'archive.json')
        (self.root/'workspace.json').write_text(json.dumps(manifest))
        with patch('historical_grid_learning_controller.verify_recovery_files'):
            with self.assertRaisesRegex(ValueError,'protocol closure only'):self.profile(name='forbidden')
            with self.assertRaisesRegex(ValueError,'protocol closure only'):self.trial('t2','t1')
            with self.assertRaisesRegex(ValueError,'protocol closure only'):
                self.broker.call('diagnose_feature_controls',{'query_id':'forbidden','trial_id':'t1',
                    'feature_name':'x','control_names':[],'rationale':'test'})
            self.assertEqual([p.name for p in (self.root/'trials').iterdir()],['t1'])
            report=self.broker.call('inspect_learning_trial',{'trial_id':'t1'})
            self.assertEqual(report['fits'],0)
            self.broker.call('submit_grid_learning_decision',{'action':'defer','trial_id':'t1','reason':'fixture'})

    def test_diagnostics_denominators_and_overlapping_missingness_are_explicit(self):
        # A pure explanation fixture: no fit and no inference that missing==zero.
        inputs=copy.deepcopy(self.inputs);plan=copy.deepcopy(self.plan)
        plan['features'].append(dict(plan['features'][0],name='same-source-copy'))
        x=inputs['x'];check=np.isin(x['date'],plan['check_utc_dates'])
        at=np.flatnonzero(check)[0];x['values'][at,1]=np.nan
        inputs['y']['available'][np.flatnonzero(check)[1]]=False
        inputs['y']['delta_probability'][np.flatnonzero(check)[2]]=0
        # Two identical source columns are jointly missing, never each the sole blocker.
        from historical_recorded_features import derive
        finite=np.isfinite(derive(x['entity'],x['decision_ms'],x['values'],inputs['names'],
            spec=plan['features'][0],cadence_ms=inputs['cadence_ms'])['values'])
        fit=np.isin(x['date'],plan['train_utc_dates']) & finite & inputs['y']['available']
        pred=np.full(len(check),np.nan);pred[check]=0
        arrays={'row_id':x['row_id'],'check':check,'fit':fit,
                'check_model_prediction':check & finite,'prediction_delta_probability':pred}
        result=diagnose(inputs,{'plan':plan,'trial_id':'fixture','result_sha256':'a'*64},arrays)
        self.assertEqual(result['check']['population_rows'],6)
        self.assertEqual(result['check']['labelled_rows'],5)
        self.assertEqual(result['check']['missing_input_rows'],1)
        for f in result['per_feature']:
            self.assertEqual(f['populations']['check_all']['missing_rows'],1)
            self.assertEqual(f['populations']['check_all']['only_this_feature_missing_rows'],0)

    def test_recorded_capability_profiles_then_fits_with_explicit_choices(self):
        times=np.unique(self.inputs['x']['decision_ms'])
        events=np.unique(np.r_[times-120000,times-30000,times])
        n=len(events)
        self.broker.inputs['recorded_events']=RecordedTradeWindows({
            'received_ms':events,'event_ms':events-1,'quantity':np.ones(n),
            'reported_quote_volume':np.ones(n)*10,'reported_maker':np.arange(n)%2,
            'quality_bits':np.zeros(n,dtype=np.uint8)},
            sorted(set(events.astype('datetime64[ms]').astype('datetime64[D]').astype(str))))
        self.broker.inputs['recorded_event_binding']={'fixture':'explicit test capability, not a real source receipt'}
        self.inspect();self.profile();self.trial()
        feature={'name':'recorded-test','source':SOURCE,'statistic':'quantity_sum',
                 'window_ms':60000,'minimum_records':1,'maximum_recorded_gap_ms':60000}
        profile=self.profile(feature,'event-profile')
        self.assertIn('recorded_event_binding',profile)
        self.assertIn('missing_reason_counts',profile)
        plan=copy.deepcopy(self.plan);plan['features'].append(feature)
        result=self.trial('event-test','t1',plan)
        self.assertEqual(result['report']['check_population_rows'],6)
        self.assertEqual(load_json(self.root/'trials/event-test/claim.json')['stage_changed'],'raw_features')

    def test_unmanifested_event_context_and_removed_ancestry_rejected(self):
        (self.root/'recorded-trades').mkdir()
        with self.assertRaisesRegex(ValueError,'unmanifested'):validate_workspace(self.root)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError,'context changed'):
                require_recorded_compatibility(self.root,Path(temporary))

    def test_composed_feature_is_profiled_and_fitted_as_one_feature_only_change(self):
        self.inspect();self.profile();self.trial()
        primitive=copy.deepcopy(self.plan['features'][0])
        composed={'name':'joint','operator':'product','operands':[primitive,primitive]}
        profile=self.profile(composed,'f-composed')
        self.assertFalse(profile['diagnostic']['model_fitted'])
        plan=copy.deepcopy(self.plan);plan['features'].append(composed)
        result=self.trial('t2','t1',plan)
        self.assertEqual(result['report']['check_population_rows'],6)
        self.assertEqual(load_json(self.root/'trials/t2/claim.json')['stage_changed'],'raw_features')

    def test_pairing_audit_binds_prior_and_current_bytes_without_model_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent=Path(temporary).resolve()/'prior';(parent/'session').mkdir(parents=True)
            shutil.copytree(self.root,parent/'workspace')
            fresh_json(parent/'session/assessment.json',{'valid':True,'process_reaped':True})
            audit={'schema':'historical_open_train_pairing_audit_v1','session_id':parent.name,
                'assessment_sha256':file_hash(parent/'session/assessment.json'),
                'fits':0,'provider_calls':0,'rows_removed':0,'labels_changed':False,
                'fresh_holdout_opened':False,'input_hashes':{str(parent/'workspace'/n):file_hash(parent/'workspace'/n)
                    for n in ['current-inputs.npz','primary-labels.npz','panel-result.json']}}
            audit['result_sha256']=digest(audit);path=Path(temporary)/'audit.json';fresh_json(path,audit)
            evidence=pairing_audit_evidence(path,parent,self.root)
            self.assertEqual(evidence['audit_sha256'],file_hash(path))
            with self.assertRaises(ValueError):pairing_audit_evidence(path,None,self.root)
            (parent/'workspace/current-inputs.npz').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'inputs differ'):
                pairing_audit_evidence(path,parent,self.root)

    def test_tool_schema_explains_first_parent_and_complete_plan(self):
        tool=next(t for t in TOOLS if t['name']=='evaluate_learning_plan')
        fields=tool['inputSchema']['properties']
        self.assertIn('empty string ""',fields['parent_trial_id']['description'])
        schema=fields['plan']
        self.assertEqual(set(schema['properties']),set(self.plan))
        self.assertEqual(set(schema['required']),set(self.plan))
        self.assertEqual(schema['properties']['rationale']['minLength'],1)
        lib=self.broker.call('inspect_learning_library',{})
        self.assertEqual(lib['evaluate_learning_plan_arguments'],tool['inputSchema'])
        self.assertEqual(lib['initial_parent_trial_id'],'')

    def test_actual_missing_parent_value_error_is_actionable(self):
        self.inspect();self.profile()
        for bad in ['none','null','t1-ridge-base']:
            with self.assertRaisesRegex(ValueError,'parent_trial_id=""'):
                self.trial(parent=bad)
            self.assertFalse((self.root/'protocol.json').exists())
            self.assertEqual(list((self.root/'trials').iterdir()),[])
        # Correcting serialization does not mutate any scientific plan value.
        before=digest(self.plan);self.trial(parent='');self.assertEqual(digest(self.plan),before)

    def test_empty_rationale_does_not_blame_valid_parameters(self):
        self.inspect();self.profile();self.plan['rationale']=''
        with self.assertRaisesRegex(ValueError,'plan.rationale must be a nonempty'):
            self.trial()
        self.assertFalse((self.root/'protocol.json').exists())

    def test_failure_chain_preserves_and_verifies_original_profiles(self):
        self.inspect();profile=self.profile()
        for bad in ['none','null','fake']:
            with self.assertRaises(ValueError):self.trial(parent=bad)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);first=root/'failed01';second=root/'failed02'
            def snapshot(session):
                (session/'session').mkdir();(session/'source-snapshot').mkdir()
                fresh_json(session/'session/assessment.json',{'valid':False,'process_reaped':True})
                source=Path(__file__).parents[1]/'historical_grid_features.py'
                shutil.copyfile(source,session/'source-snapshot'/source.name)
                fresh_json(session/'preparation.json',{'source_hashes':{source.name:file_hash(source)}})
            shutil.copytree(self.root,first/'workspace');snapshot(first)
            inherited=failed_pre_fit_evidence(first,self.root)
            self.assertEqual(inherited['profiles'],[profile])
            shutil.copytree(self.root,second/'workspace');snapshot(second)
            workspace=second/'workspace'
            archive={'interface_repair':{'failed_session_id':'failed01',
                'assessment_sha256':file_hash(first/'session/assessment.json'),
                'activity_sha256':file_hash(first/'workspace/learning-activity.jsonl'),
                'successful_feature_profiles_reused_without_recomputation':[profile]}}
            (workspace/'archive.json').write_text(json.dumps(archive))
            manifest=load_json(workspace/'workspace.json');manifest['files']['archive.json']=file_hash(workspace/'archive.json')
            (workspace/'workspace.json').write_text(json.dumps(manifest))
            (workspace/'learning-activity.jsonl').unlink()
            broker=Broker(workspace);broker.call('inspect_learning_contract',{});broker.call('inspect_learning_library',{})
            for bad in ['none','null','fake']:
                with self.assertRaises(ValueError):
                    broker.call('evaluate_learning_plan',{'trial_id':'t1','parent_trial_id':bad,'plan':self.plan})
            evidence=failed_pre_fit_evidence(second,self.root)
            self.assertEqual(evidence['profiles'],[profile])
            self.assertEqual([h['session_id'] for h in evidence['history']],['failed01','failed02'])
            # The new session cannot hide a changed ancestor behind a copied profile.
            with (first/'workspace/features/f1/result.json').open('a') as stream:stream.write(' ')
            changed=load_json(first/'workspace/features/f1/result.json');changed['query_id']='changed'
            (first/'workspace/features/f1/result.json').write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError,'prior successful feature evidence changed'):
                failed_pre_fit_evidence(second,self.root)

    def test_actual_failed_alias_shape_reports_correct_keys(self):
        self.inspect();self.profile()
        self.plan['model']={'name':'ridge','params':{'alpha':1,'fit_intercept':True}}
        with self.assertRaisesRegex(ValueError,'EXACT keys algorithm and parameters'):
            self.trial()
        self.assertFalse((self.root/'protocol.json').exists())

    def test_archived_profile_reuse_without_new_computation(self):
        from unittest.mock import patch
        from historical_grid_learning_controller import Broker
        self.inspect();prior=self.profile()
        archive={'interface_repair':{'successful_feature_profiles_reused_without_recomputation':[prior]}}
        (self.root/'archive.json').write_text(json.dumps(archive))
        manifest=load_json(self.root/'workspace.json');manifest['files']['archive.json']=file_hash(self.root/'archive.json')
        (self.root/'workspace.json').write_text(json.dumps(manifest))
        # Simulate a new session that has seen only the frozen archived evidence.
        (self.root/'learning-activity.jsonl').unlink()
        broker=Broker(self.root);broker.call('inspect_learning_contract',{});broker.call('inspect_learning_library',{})
        with patch('historical_grid_learning_controller.raw_feature_diagnostic',side_effect=AssertionError('must not reprofile')):
            broker.call('evaluate_learning_plan',{'trial_id':'t1','parent_trial_id':'','plan':self.plan})
        claim=load_json(self.root/'trials/t1/claim.json')
        self.assertEqual(claim['prior_feature_evidence'],{'f1':prior['result_sha256']})

    def test_completed_defer_carries_parent_without_reexecution_or_protocol_reset(self):
        self.inspect();self.profile();result=self.trial()
        diagnostic=self.broker.call('diagnose_feature_controls',{'query_id':'d1','trial_id':'t1',
            'feature_name':'x','control_names':[],'rationale':'synthetic carryover check'})
        self.broker.call('submit_grid_learning_decision',{'action':'defer','trial_id':'t1','reason':'need native missing input method'})
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory)/'prior';shutil.copytree(self.root,parent/'workspace')
            (parent/'session').mkdir();(parent/'source-snapshot').mkdir()
            fresh_json(parent/'session/assessment.json',{'valid':True,'process_reaped':True})
            source=Path(__file__).parents[1]/'historical_grid_features.py'
            shutil.copyfile(source,parent/'source-snapshot'/source.name)
            fresh_json(parent/'preparation.json',{'source_hashes':{source.name:file_hash(source)}})
            audit={'passed':True,'session_id':'prior','assessment_sha256':file_hash(parent/'session/assessment.json'),
                'activity':assess_activity(parent/'workspace'),'decision':load_json(parent/'workspace/submitted-grid-learning-decision.json'),
                'trials':[{'trial_id':'t1','result_sha256':result['result_sha256']}]}
            audit['result_sha256']=digest(audit);fresh_json(parent/'audit.json',audit)
            new=Path(directory)/'new';shutil.copytree(self.root,new)
            for name in ['submitted-grid-learning-decision.json','protocol.json','learning-activity.jsonl']:(new/name).unlink()
            shutil.rmtree(new/'trials');(new/'trials').mkdir()
            shutil.rmtree(new/'conditional-diagnostics')
            archive={'completed_diagnostic':carry_completed_diagnostic(parent,parent/'audit.json',new)}
            self.assertEqual(archive['completed_diagnostic']['prior_conditional_diagnostics'][0]['result'],diagnostic)
            (new/'archive.json').write_text(json.dumps(archive))
            manifest=load_json(new/'workspace.json');manifest['files']['archive.json']=file_hash(new/'archive.json')
            (new/'workspace.json').write_text(json.dumps(manifest))
            broker=Broker(new);contract=broker.call('inspect_learning_contract',{});library=broker.call('inspect_learning_library',{})
            self.assertEqual(contract['available_parent_trial_ids'],['t1'])
            self.assertIsNone(library['initial_parent_trial_id'])
            with self.assertRaisesRegex(ValueError,'duplicate scientific'):
                broker.call('evaluate_learning_plan',{'trial_id':'again','parent_trial_id':'t1','plan':self.plan})
            frozen_result=load_json(parent/'workspace/trials/t1/result.json')
            self.plan['model']['parameters']['alpha']=2
            broker.call('evaluate_learning_plan',{'trial_id':'t2','parent_trial_id':'t1','plan':self.plan})
            self.assertEqual(load_json(new/'trials/t1/result.json'),frozen_result)
            self.assertEqual(load_json(new/'protocol.json'),load_json(parent/'workspace/protocol.json'))
            # A SECOND completed carryover must retain the original feature profile
            # even when the intermediate session did not call profile_feature.
            broker.call('submit_grid_learning_decision',{'action':'defer','trial_id':'t2','reason':'another concrete capability'})
            second=Path(directory)/'second';shutil.copytree(new,second/'workspace')
            (second/'session').mkdir();(second/'source-snapshot').mkdir()
            fresh_json(second/'session/assessment.json',{'valid':True,'process_reaped':True})
            shutil.copyfile(source,second/'source-snapshot'/source.name)
            fresh_json(second/'preparation.json',{'source_hashes':{source.name:file_hash(source)},
                'workspace_sha256':file_hash(second/'workspace/workspace.json')})
            audit2={'passed':True,'session_id':'second','assessment_sha256':file_hash(second/'session/assessment.json'),
                'activity':assess_activity(second/'workspace'),'decision':load_json(second/'workspace/submitted-grid-learning-decision.json'),
                'trials':[{'trial_id':name,'result_sha256':load_json(second/'workspace/trials'/name/'result.json')['result_sha256']}
                          for name in ['t1','t2']]}
            audit2['result_sha256']=digest(audit2);fresh_json(second/'audit.json',audit2)
            third=Path(directory)/'third';shutil.copytree(new,third)
            for name in ['submitted-grid-learning-decision.json','protocol.json','learning-activity.jsonl']:(third/name).unlink()
            shutil.rmtree(third/'trials');(third/'trials').mkdir()
            shutil.rmtree(third/'conditional-diagnostics')
            evidence=carry_completed_diagnostic(second,second/'audit.json',third)
            self.assertEqual(evidence['prior_conditional_diagnostics'][0]['result'],diagnostic)
            self.assertEqual(file_hash(third/'conditional-diagnostics/d1/result.json'),
                file_hash(parent/'workspace/conditional-diagnostics/d1/result.json'))
            self.assertEqual(len(evidence['successful_feature_profiles_reused_without_recomputation']),1)
            self.assertEqual([h['session_id'] for h in evidence['verified_completed_history']],['prior','second'])
            self.assertEqual(sorted(evidence['all_prior_trials']),['t1','t2'])
            # Changing a grandparent is not hidden by copying its profile into a child.
            with (parent/'workspace/features/f1/claim.json').open('a') as stream:stream.write(' ')
            with self.assertRaises(ValueError):
                from historical_grid_learning_controller import completed_profile_evidence
                completed_profile_evidence(second,third)

    def test_inspect_and_each_raw_feature_required_before_fit(self):
        with self.assertRaisesRegex(ValueError,'inspect'):self.profile()
        self.inspect()
        with self.assertRaisesRegex(ValueError,'profile every'):self.trial()
        self.assertFalse((self.root/'protocol.json').exists())

    def test_duplicate_scientific_trial_is_not_a_new_id(self):
        self.inspect();self.profile();self.trial()
        self.plan['rationale']='changed prose only'
        with self.assertRaisesRegex(ValueError,'duplicate scientific'):self.trial('t2','t1')

    def test_metric_and_boundary_cannot_change_after_first_result(self):
        self.inspect();self.profile();self.trial();self.plan['score_aggregation']='equal_day'
        with self.assertRaisesRegex(ValueError,'boundary or metric'):self.trial('t2','t1')

    def test_cannot_change_features_and_trainer_together(self):
        self.inspect();self.profile();self.trial()
        feature={**self.plan['features'][0],'name':'square','transform':'square'}
        self.profile(feature,'f2');self.plan['features']=[feature];self.plan['model']['parameters']['alpha']=2
        with self.assertRaisesRegex(ValueError,'one stage'):self.trial('t2','t1')

    def test_one_prediction_change_succeeds_and_records_parent(self):
        self.inspect();self.profile();self.trial();self.plan['model']['parameters']['alpha']=2
        self.trial('t2','t1')
        claim=load_json(self.root/'trials/t2/claim.json')
        self.assertEqual(claim['parent_trial_id'],'t1');self.assertEqual(claim['stage_changed'],'prediction_training')

    def test_changed_inputs_or_prediction_artifacts_fail_closed(self):
        self.inspect();self.profile();self.trial()
        with (self.root/'trials/t1/predictions.npz').open('ab') as f:f.write(b'bad')
        with self.assertRaisesRegex(ValueError,'changed'):
            self.broker.call('submit_grid_learning_decision',{'action':'select','trial_id':'t1','reason':'fixture'})

    def test_can_defer_without_inventing_missing_capability(self):
        self.inspect();self.broker.call('submit_grid_learning_decision',{'action':'defer','trial_id':'','reason':'need exact missing field'})
        self.assertTrue(assess_activity(self.root)['valid'])

    def test_real_stdio_mcp_lists_tools_and_input_without_model_calls(self):
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize'}, {'jsonrpc':'2.0','id':2,'method':'tools/list'},
            {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'inspect_learning_contract','arguments':{}}}]
        run=subprocess.run([sys.executable,str(Path(__file__).parents[1]/'historical_grid_learning_controller.py'),
            '--workspace',str(self.root)],input=''.join(json.dumps(v)+'\n' for v in requests),text=True,
            capture_output=True,timeout=15)
        self.assertEqual(run.returncode,0,run.stderr)
        responses=[json.loads(v) for v in run.stdout.splitlines()]
        self.assertEqual(responses[1]['result']['tools'],TOOLS)
        self.assertFalse(responses[2]['result']['isError'])

    def test_real_stdio_conditional_tool_on_synthetic_existing_trial(self):
        self.inspect();self.profile();self.trial()
        before=file_hash(self.root/'trials/t1/predictions.npz')
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize'},
            {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{
                'name':'diagnose_feature_controls','arguments':{'query_id':'stdio-d1',
                    'trial_id':'t1','feature_name':'x','control_names':[],'rationale':'synthetic transport canary'}}}]
        run=subprocess.run([sys.executable,str(Path(__file__).parents[1]/'historical_grid_learning_controller.py'),
            '--workspace',str(self.root)],input=''.join(json.dumps(v)+'\n' for v in requests),
            text=True,capture_output=True,timeout=15)
        self.assertEqual(run.returncode,0,run.stderr)
        responses=[json.loads(v) for v in run.stdout.splitlines()]
        self.assertFalse(responses[1]['result']['isError'])
        result=json.loads(responses[1]['result']['content'][0]['text'])
        self.assertEqual(result['prediction_model_trials_started'],0)
        self.assertEqual(result['paid_provider_calls'],0)
        self.assertEqual(result['nuisance_regressions_fitted'],4)
        self.assertEqual(file_hash(self.root/'trials/t1/predictions.npz'),before)


if __name__=='__main__':unittest.main()
