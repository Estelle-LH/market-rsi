import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

from data_scientist_harness import fixtures, sanity, checked_learning, trajectory
from data_scientist_harness.store import Store
from data_scientist_harness.broker import Broker
from ds_harness_core.research_gate import QualityGateError
from historical_grid_learning import read_inputs, evaluate as legacy_evaluate
from market_rsi import file_hash, load_json, digest


class GridSanityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name).resolve()/'run'
        self.sha=fixtures.workspace(self.root); self.store=Store(self.root,self.sha)
        self.inputs=read_inputs(self.root/'inputs')
        self.contract=sanity.read_contract(self.root/'inputs',self.store.config['input_manifest_sha256'],'canary')

    def tearDown(self): self.tmp.cleanup()

    def run_checked(self, name='ridge', inputs=None, contract=None, experiment=None):
        return checked_learning.evaluate(inputs or self.inputs,fixtures.plan(name),experiment or fixtures.experiment(),
            contract or self.contract,self.root/('sanity-'+name))

    def test_four_trainers_exact_reports_and_prediction_arrays(self):
        # Initialize the process-wide CPU probe before either arm. Its first
        # macOS fallback warning is not a trainer difference; the separate
        # subprocess parity canary still compares complete warning lists.
        from joblib import cpu_count
        cpu_count(only_physical_cores=True)
        for name in fixtures.MODELS:
            with self.subTest(name=name):
                expected, arrays=legacy_evaluate(self.inputs,fixtures.plan(name))
                actual, checked=self.run_checked(name)
                self.assertEqual({k:v for k,v in expected.items() if k!='elapsed_seconds'},
                                 {k:v for k,v in actual.items() if k!='elapsed_seconds'})
                for key in arrays:
                    self.assertEqual(arrays[key].dtype,checked[key].dtype)
                    self.assertEqual(arrays[key].tobytes(),checked[key].tobytes())
                reports=list((self.root/('sanity-'+name)).glob('*/quality_gate.json'))
                self.assertEqual(len(reports),4)
                self.assertTrue(all(load_json(p)['status']=='PASS' for p in reports))

    def test_raw_inf_blocks_scaler_and_estimator(self):
        self.inputs['x']['values'][1,1]=np.inf
        with patch.object(checked_learning.StandardScaler,'fit') as scaler, patch.object(checked_learning.Ridge,'fit') as fit:
            with self.assertRaises(QualityGateError): self.run_checked()
            scaler.assert_not_called(); fit.assert_not_called()
        r=load_json(self.root/'sanity-ridge/raw/quality_gate.json')
        self.assertEqual(r['data_level']['raw']['raw_numeric_counts'][1]['positive_inf'],1)

    def test_transformed_nan_cannot_be_hidden_before_estimator(self):
        with patch.object(checked_learning.StandardScaler,'transform',side_effect=lambda a:np.full(a.shape,np.nan)), \
             patch.object(checked_learning.Ridge,'fit') as fit:
            with self.assertRaises(QualityGateError): self.run_checked()
            fit.assert_not_called()
        self.assertEqual(load_json(self.root/'sanity-ridge/normalized/quality_gate.json')['status'],'FAIL')

    def test_misordered_grid_rows_not_sorted_into_pass(self):
        self.inputs['x']['decision_ms'][2]=self.inputs['x']['decision_ms'][0]
        with patch.object(checked_learning.Ridge,'fit') as fit:
            with self.assertRaises(QualityGateError): self.run_checked()
            fit.assert_not_called()

    def test_known_grid_gap_blocks_before_fit(self):
        self.inputs['x']['decision_ms'][5]+=60000
        with patch.object(checked_learning.Ridge,'fit') as fit:
            with self.assertRaises(QualityGateError): self.run_checked()
            fit.assert_not_called()

    def test_quiet_gap_does_not_have_to_be_corruption(self):
        self.inputs['x']['decision_ms'][5]+=60000
        c=copy.deepcopy(self.contract); c['time_series']['max_gap_ns']*=2
        raw=sanity.raw_panel(self.inputs,c)
        called=[]
        _, report=sanity.guard(raw=raw,transformed=raw,c=c,
            lineage_map={n:[n] for n in self.inputs['names']},path=self.root/'quiet',stage='fit',
            operation=lambda _:called.append(True))
        self.assertEqual(called,[True]); self.assertEqual(report['status'],'PASS')
        self.assertEqual(report['time_series_level']['raw']['features'][0]['gaps_excluded_from_pairs'],1)

    def test_grid_has_no_fabricated_submillisecond_order(self):
        raw=sanity.raw_panel(self.inputs,self.contract)
        self.assertTrue(np.all(raw.batch['decision_ns']%1_000_000==0))
        self.assertTrue(np.all(raw.batch['event_ordinal']==0))
        self.assertEqual(raw.spec.clock_domain,sanity.CLOCK)

    def test_clock_conversion_rejects_both_overflow_directions(self):
        for extreme in (np.iinfo(np.int64).min,np.iinfo(np.int64).max):
            with self.subTest(extreme=extreme):
                self.inputs['x']['decision_ms'][0]=extreme
                with self.assertRaisesRegex(ValueError,'representable'):
                    sanity.raw_panel(self.inputs,self.contract)

    def test_future_source_mutation_does_not_change_earlier_features(self):
        first=sanity.derived_panel(self.inputs,fixtures.plan(),fixtures.experiment(),self.contract)
        changed=copy.deepcopy(self.inputs); changed['x']['values'][5:,1]*=1000
        second=sanity.derived_panel(changed,fixtures.plan(),fixtures.experiment(),self.contract)
        np.testing.assert_array_equal(first.batch['values'][:5],second.batch['values'][:5])

    def test_synthetic_source_proof_never_admits_real_work(self):
        with self.assertRaisesRegex(ValueError,'synthetic'):
            sanity.read_contract(self.root/'inputs',self.store.config['input_manifest_sha256'],'opened_train_research')

    def test_missing_stale_and_mutated_adapter_proof_rejected(self):
        p=self.root/'inputs/sanity-evidence-source_units_clock.json'; p.write_text('{}')
        with self.assertRaisesRegex(ValueError,'changed'):
            sanity.read_contract(self.root/'inputs',self.store.config['input_manifest_sha256'],'canary')

    def test_constant_rejection_needs_explicit_exception(self):
        c=copy.deepcopy(self.contract); c['raw_rules']['flat']['allow_constant']=False
        with patch.object(checked_learning.Ridge,'fit') as fit:
            with self.assertRaises(QualityGateError): self.run_checked(contract=c)
            fit.assert_not_called()


class ResearchTraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name).resolve()/'run'
        self.sha=fixtures.workspace(self.root,network=True)
        self.b=Broker(self.root,self.sha,transport=fixtures.fake_transport)
        status=self.b.call('inspect_harness',{})
        read=self.b.call('read_public_source',{'url':'https://example.org/test','offset':0})
        notes=dict(question='Synthetic test',read_records=[read['record_id']],applicability='Mechanics only',
            limitations='Not real research',alternatives='Unchanged baseline',proposed_test='Compare outputs')
        feat=self.b.call('record_research',dict(notes,layer='feature_engineering'))
        trainer=self.b.call('record_research',dict(notes,layer='trainer_engineering'))
        self.b.call('profile_raw_series',{})
        prof=self.b.call('profile_candidate_feature',dict(spec=fixtures.plan()['features'][0],research_record=feat['record_id']))
        review=self.b.call('review_feature_set',dict(profile_records=[prof['record_id']],dispositions=[
            dict(profile_record=prof['record_id'],reason='Synthetic',risk='No market evidence')]))
        self.b.call('acknowledge_current_findings',dict(finding_sha256=status['finding_sha256'],responses=[
            dict(id='fixture-only',handling='Synthetic only',next_evidence='Real data checks')]))
        self.args=dict(trial_id='t0',parent_trial_id='',plan=fixtures.plan(),feature_review=review['record_id'],
            trainer_research=trainer['record_id'],experiment=fixtures.experiment())

    def tearDown(self): self.tmp.cleanup()

    def test_missing_hypothesis_cannot_create_claim_or_worker(self):
        self.args['experiment'].pop('hypothesis')
        with patch('data_scientist_harness.broker.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError,'pre-result'): self.b.call('train_candidate',self.args)
            spawn.assert_not_called()
        self.assertFalse((self.root/'trials/t0').exists())

    def test_intent_exists_before_actual_worker_and_result(self):
        import subprocess
        original=subprocess.Popen
        def check(*args,**kwargs):
            path=self.root/'trials/t0'
            self.assertTrue((path/'intent.json').exists()); self.assertFalse((path/'result.json').exists())
            self.assertEqual(load_json(path/'intent.json')['phase'],'before_worker_or_result')
            return original(*args,**kwargs)
        with patch('data_scientist_harness.broker.subprocess.Popen',side_effect=check):
            self.b.call('train_candidate',self.args)

    def test_reflection_required_and_round_preserves_full_numeric_result(self):
        result=self.b.call('train_candidate',self.args)
        with self.assertRaisesRegex(ValueError,'reflection'):
            self.b.call('submit_research_decision',dict(action='select',trial_id='t0',reason='Synthetic'))
        self.b.call('reflect_candidate',fixtures.reflection(self.root,'t0'))
        self.b.call('submit_research_decision',dict(action='select',trial_id='t0',reason='Synthetic'))
        trace=load_json(self.root/'research-trace.json')
        self.assertEqual(trace['all_trial_count'],1)
        metrics=trace['trials'][0]['reflection']['observed']['candidate_metrics']
        self.assertEqual(metrics,result['report']['score'])
        self.assertIn('model_rmse_probability_bps',metrics)
        rendered=(self.root/'research-trace.md').read_text()
        self.assertIn('RMSE（概率 bp）',rendered)
        self.assertIn('运行前的想法',rendered)
        self.assertIn('输入和模型回复是测试夹具',rendered)
        archive=load_json(self.root/'round-archive.json')
        self.assertEqual(archive['trial_summaries'][0]['observed']['candidate_metrics'],metrics)
        self.assertEqual(len(archive['data_science_evidence']['raw_profiles']),1)
        self.assertEqual(len(archive['data_science_evidence']['source_research']),2)

    def test_reflection_cannot_rewrite_or_use_wrong_outcome(self):
        self.b.call('train_candidate',self.args)
        args=fixtures.reflection(self.root,'t0'); wrong=dict(args,outcome_sha256='0'*64)
        with self.assertRaisesRegex(ValueError,'exact observed'): self.b.call('reflect_candidate',wrong)
        self.b.call('reflect_candidate',args)
        with self.assertRaisesRegex(ValueError,'append-only'): self.b.call('reflect_candidate',args)

    def test_changed_sanity_receipt_not_selectable(self):
        self.b.call('train_candidate',self.args)
        (self.root/'trials/t0/sanity/raw/data_check.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'sanity report changed'): self.b.completed_candidate('t0')

    def test_parent_policy_not_loosened_after_score(self):
        self.b.call('train_candidate',self.args)
        args=copy.deepcopy(self.args); args.update(trial_id='t1',parent_trial_id='t0',plan=fixtures.plan('random_forest'),experiment=fixtures.experiment('t0'))
        args['experiment']['feature_rules']['x']['allow_constant']=True
        with self.assertRaisesRegex(ValueError,'cannot be loosened'): self.b.call('train_candidate',args)
        self.assertFalse((self.root/'trials/t1').exists())

    def test_failed_worker_is_preserved_reflected_and_not_a_scientific_score(self):
        with patch('data_scientist_harness.broker.subprocess.Popen',side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError): self.b.call('train_candidate',self.args)
        args=fixtures.reflection(self.root,'t0')
        self.b.call('reflect_candidate',args)
        self.b.call('submit_research_decision',dict(action='defer',trial_id='',reason='Synthetic failure'))
        observed=load_json(self.root/'research-trace.json')['trials'][0]['reflection']['observed']
        self.assertEqual(observed['status'],'failed'); self.assertIsNone(observed['scientific_conclusion'])
        self.assertIn('没有有效分数',(self.root/'research-trace.md').read_text())


if __name__=='__main__': unittest.main()
