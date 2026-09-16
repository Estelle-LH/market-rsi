from pathlib import Path
import tempfile
import unittest
import json
import subprocess
import sys
from unittest.mock import patch

from historical_data_use_controller import prepare_workspace, Broker, assess_activity, validate_proposal
from historical_source_contract import contract, CLOCK_ASSUMPTION
from market_rsi import digest, file_hash, fresh_json, load_json


class DataUseControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        coverage=self.root/'coverage.json'
        fresh_json(coverage,{'rows':10,'observed_markets':2,'actual_utc_receipt_day_event_bins':[
            {'utc_date':'2026-02-12','minutes_with_events':10},{'utc_date':'2026-02-13','minutes_with_events':20}]})
        feedback={'source_plan_sha256':'a'*64,'acquisition':{'pm_tick_rows':10},
                  'source_artifact_sha256':{'coverage':file_hash(coverage)}}
        fresh_json(self.root/'feedback.json',{**feedback,'feedback_sha256':digest(feedback)})
        canary=self.root/'canary';canary.mkdir()
        fresh_json(canary/'result.json',{'canary_pass':True,'training_admitted':False})
        source=Path(__file__).parents[1]/'historical_source_contract.py'
        fresh_json(canary/'claim.json',{'plan_sha256':'a'*64,'contract_source_sha256':file_hash(source)})
        fresh_json(canary/'source-contract.json',contract())
        self.workspace=self.root/'workspace'
        prepare_workspace(self.workspace,feedback=self.root/'feedback.json',coverage=coverage,
            source_canary=canary,session_id='test-use',experiment_id='test-experiment')
        self.broker=Broker(self.workspace)

    def tearDown(self):self.temp.cleanup()

    def plan(self):
        return {'purpose':'diagnostic_learning_pilot','open_train_utc_dates':['2026-02-13','2026-02-12'],
            'primary_observation':'pm_reported_bbo','context_streams':['binance_trades'],
            'cadence_ms':10000,'max_age_ms':1000,'market_time_scope':'nominal_15m_window',
            'max_materialized_rows':50000,'clock_assumption':CLOCK_ASSUMPTION,
            'feature_ideas':['lagged reported midpoint'], 'rationale':'Test pipeline on existing data.',
            'limitations':'No full-day or execution guarantees.'}

    def inspect(self):
        for name in ['inspect_data_readiness','inspect_source_contract','inspect_coverage_calendar']:
            self.broker.call(name,{})

    def test_first_valid_controller_selection_is_logged_not_executed(self):
        self.inspect();proposal=self.broker.call('propose_data_use',{'proposal_id':'p1','plan':self.plan()})
        self.assertEqual(proposal['plan']['open_train_utc_dates'],['2026-02-12','2026-02-13'])
        self.assertFalse(proposal['materializer_execution_verified'])
        submitted=self.broker.call('submit_data_use_decision',{'action':'select','proposal_id':'p1','reason':'Diagnostic only.'})
        from codex_glm_provider import successful_submission
        request={'input':[
            {'type':'function_call','call_id':'chosen','name':'submit_data_use_decision','namespace':'mcp__controller_tools'},
            {'type':'function_call_output','call_id':'chosen','output':json.dumps(submitted)}]}
        self.assertEqual(successful_submission(request,'submit_data_use_decision'),'chosen')
        self.assertGreater(submitted['bytes'],0)
        self.assertTrue(assess_activity(self.workspace)['valid'])
        with self.assertRaisesRegex(ValueError,'already submitted'):
            self.broker.call('inspect_data_readiness',{})

    def test_bad_dates_fail_before_selection(self):
        plan=self.plan();plan['open_train_utc_dates']=['2026-01-01','2026-01-02']
        with self.assertRaisesRegex(ValueError,'available UTC'):
            validate_proposal(plan,self.workspace)

    def test_new_data_source_or_pm_trade_cannot_be_fabricated(self):
        plan=self.plan();plan['context_streams']=['pm_trades']
        with self.assertRaisesRegex(ValueError,'context stream'):
            validate_proposal(plan,self.workspace)

    def test_new_download_field_rejected(self):
        plan=self.plan();plan['download_url']='https://example.com/data'
        with self.assertRaisesRegex(ValueError,'fields'):
            validate_proposal(plan,self.workspace)

    def test_unbounded_rows_rejected(self):
        plan=self.plan();plan['max_materialized_rows']=10000000
        with self.assertRaisesRegex(ValueError,'500000'):
            validate_proposal(plan,self.workspace)

    def test_formal_claim_rejected(self):
        plan=self.plan();plan['purpose']='profitable_trading_proven'
        with self.assertRaisesRegex(ValueError,'diagnostic'):
            validate_proposal(plan,self.workspace)

    def test_cannot_decide_without_reading_real_coverage(self):
        with self.assertRaisesRegex(ValueError,'inspect quality'):
            self.broker.call('submit_data_use_decision',{'action':'defer','proposal_id':'','reason':'Need more data.'})

    def test_defer_is_valid_without_model_resampling(self):
        self.inspect();self.broker.call('submit_data_use_decision',{'action':'defer','proposal_id':'','reason':'Causal policy not justified.'})
        self.assertEqual(assess_activity(self.workspace)['action'],'defer')

    def test_real_stdio_mcp_protocol_no_model(self):
        requests = [
            {'jsonrpc':'2.0','id':1,'method':'initialize'},
            {'jsonrpc':'2.0','id':2,'method':'tools/list'},
            {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{
                'name':'inspect_source_contract','arguments':{}}},
        ]
        completed=subprocess.run([sys.executable,str(Path(__file__).parents[1]/'historical_data_use_controller.py'),
            '--workspace',str(self.workspace)],input=''.join(json.dumps(r)+'\n' for r in requests),
            text=True,capture_output=True,timeout=15,check=True)
        replies=[json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual([r['id'] for r in replies],[1,2,3])
        self.assertEqual(len(replies[1]['result']['tools']),6)
        self.assertFalse(replies[2]['result']['isError'])

    def test_preparation_freezes_source_without_dispatch(self):
        from prepare_historical_data_use_session import prepare
        env=self.root/'fixture.env';env.write_text('')
        tokenizer=self.root/'tokenizer';tokenizer.mkdir()
        state={'jobs':{},'buckets':{'setup':{'available_usd':'2'}},'experiment_id':'test-experiment'}
        args=dict(feedback=self.root/'feedback.json',coverage=self.root/'coverage.json',
            source_canary=self.root/'canary',budget=self.root/'budget',runtime=Path(sys.executable),
            env_file=env,tokenizer=tokenizer)
        with patch('prepare_historical_data_use_session.PaidBudget') as mocked:
            mocked.return_value.snapshot.return_value=state
            with patch('prepare_historical_data_use_session.subprocess.Popen') as popen:
                result=prepare(self.root/'new-session',**args)
                popen.assert_not_called()
            self.assertEqual(result['command'][-1],'data_use')
            self.assertFalse(result['paid_controller_started'])
            self.assertIn('historical_source_contract.py',result['source_hashes'])
            for name,sha in result['source_hashes'].items():
                self.assertEqual(file_hash(self.root/'new-session/source-snapshot'/name),sha)
            with self.assertRaises(FileExistsError):prepare(self.root/'new-session',**args)

    def test_unresolved_paid_turn_blocks_preparation(self):
        from prepare_historical_data_use_session import prepare
        env=self.root/'fixture.env';env.write_text('')
        state={'jobs':{'old-turn-001':{'state':'dispatched'}},
            'buckets':{'setup':{'available_usd':'2'}},'experiment_id':'test-experiment'}
        with patch('prepare_historical_data_use_session.PaidBudget') as mocked:
            mocked.return_value.snapshot.return_value=state
            with self.assertRaisesRegex(ValueError,'unresolved controller'):
                prepare(self.root/'blocked-session',feedback=self.root/'feedback.json',
                    coverage=self.root/'coverage.json',source_canary=self.root/'canary',
                    budget=self.root/'budget',runtime=Path(sys.executable),env_file=env,tokenizer=self.root)

    def test_materialized_train_dates_cannot_be_presented_as_fresh_holdout(self):
        report=load_json(self.root/'feedback.json');report.pop('feedback_sha256')
        report['open_train_materialization']={'opened_utc_dates':['2026-02-12']}
        report['feedback_sha256']=digest(report)
        fresh_json(self.root/'next-feedback.json',report)
        new=self.root/'next-workspace'
        prepare_workspace(new,feedback=self.root/'next-feedback.json',coverage=self.root/'coverage.json',
            source_canary=self.root/'canary',session_id='next-use',experiment_id='test-experiment')
        self.assertIn('2026-02-12',load_json(new/'constraints.json')['known_opened_dates_not_fresh_holdout'])


if __name__=='__main__':unittest.main()
