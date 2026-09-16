from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from codex_glm_provider import successful_submission
from historical_grid_objective_controller import Broker, assess_activity, prepare_workspace, read_panel, numerical_feedback
from market_rsi import digest, file_hash, fresh_json, load_json
from paid_budget import PaidBudget
from prepare_historical_objective_session import prepare


class GridObjectiveControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.data=self.root/'data';self.data.mkdir();self.side=self.root/'annotations';self.side.mkdir()
        self.proposal=self.root/'proposal.json'
        chosen={'plan':{'open_train_utc_dates':['2026-04-04']},'proposal_sha256':None}
        chosen['proposal_sha256']=digest({k:v for k,v in chosen.items() if k!='proposal_sha256'})
        fresh_json(self.proposal,chosen)
        side={'proposal_sha256':chosen['proposal_sha256']};side['result_sha256']=digest(side)
        fresh_json(self.side/'result.json',side)
        self.arrays={'entity':np.zeros(4,dtype=np.int64),'time_ms':np.arange(1,5,dtype=np.int64)*60000,
            'midpoint':np.array([.4,.5,np.nan,.6]),'quote_age_ms':np.array([0,0,np.nan,0]),
            'date':np.array(['2026-04-04']*4),'phase':np.array(['within_nominal_window']*4),
            'row_id':np.array(['a','b','c','d']),'cadence_ms':np.array(60000),'max_age_ms':np.array(300000)}
        np.savez_compressed(self.data/'unlabelled-grid.npz',**self.arrays)
        result={'schema':'historical_unlabelled_grid_panel_v1','complete':True,'target_computed':False,
            'target_selected':False,'training_admitted':False,'fresh_holdout':False,'all_grid_rows_retained':True,
            'panel_sha256':file_hash(self.data/'unlabelled-grid.npz'),
            'input_hashes':{'proposal':file_hash(self.proposal),'annotations':file_hash(self.side/'result.json')},
            'summary':{'rows':4,'entities':1,'finite_midpoint_rows':3,
                'by_open_train_date':{'2026-04-04':4},'by_nominal_phase':{'within_nominal_window':4}}}
        result['result_sha256']=digest(result);fresh_json(self.data/'result.json',result)
        self.workspace=self.root/'workspace'
        prepare_workspace(self.workspace,panel_directory=self.data,proposal=self.proposal,annotations=self.side,
            session_id='fixture-objective',experiment_id='fixture-exp')
        self.broker=Broker(self.workspace)

    def tearDown(self):self.temp.cleanup()

    def inspect(self):
        self.broker.call('inspect_train_inventory',{});self.broker.call('inspect_objective_registry',{})

    def spec(self):
        return {'family':'point_delta','window_start_ms':60000,'window_end_ms':60000,'half_life_ms':None,
            'minimum_observations':1,'minimum_window_coverage':1,'label_max_age_ms':300000}

    def query(self,name='q1'):
        return self.broker.call('profile_objective',{'query_id':name,'spec':self.spec(),'rationale':'fixture only'})

    def proposal_args(self):
        return {'proposal_id':'p1','primary_query_id':'q1','diagnostic_query_ids':[],
            'primary_metric':'mse_skill_vs_persistence','rationale':'fixture choice','limitations':'not model skill'}

    def test_valid_select_has_actual_unpaid_handshake(self):
        self.inspect();q=self.query();self.broker.call('propose_objective',self.proposal_args())
        self.assertEqual(q['profile']['all_rows']['population_rows'],4)
        self.assertEqual(q['profile']['all_rows']['covered_rows'],1)
        result=self.broker.call('submit_grid_objective_decision',{'action':'select','proposal_id':'p1','reason':'done'})
        request={'input':[{'type':'function_call','call_id':'c1','name':'submit_grid_objective_decision','namespace':'mcp__controller_tools'},
            {'type':'function_call_output','call_id':'c1','output':json.dumps(result)}]}
        self.assertEqual(successful_submission(request,'submit_grid_objective_decision'),'c1')
        self.assertTrue(assess_activity(self.workspace)['valid'])
        with self.assertRaisesRegex(ValueError,'already submitted'):self.broker.call('inspect_train_inventory',{})

    def test_cannot_profile_before_inventory(self):
        with self.assertRaisesRegex(ValueError,'inspect data'):self.query()

    def test_bad_subgrid_spec_rejected_before_query_directory(self):
        self.inspect();spec=self.spec();spec['window_start_ms']=1000
        with self.assertRaisesRegex(ValueError,'actual recorded grid'):
            self.broker.call('profile_objective',{'query_id':'bad','spec':spec,'rationale':'fixture'})
        self.assertFalse((self.workspace/'queries/bad').exists())

    def test_query_persisted_before_computation(self):
        self.inspect()
        def check(panel,spec):
            self.assertTrue((self.workspace/'queries/q1/query.json').exists())
            raise RuntimeError('fixture interrupted computation')
        with patch('historical_grid_objective_controller.profile',side_effect=check):
            with self.assertRaises(RuntimeError):self.query()
        self.assertFalse((self.workspace/'queries/q1/result.json').exists())
        with self.assertRaises(FileExistsError):self.query()

    def test_reused_query_id_rejected(self):
        self.inspect();self.query()
        with self.assertRaises(FileExistsError):self.query()

    def test_hidden_filter_rejected(self):
        self.inspect()
        with self.assertRaisesRegex(ValueError,'hidden filters'):
            self.broker.call('profile_objective',{'query_id':'q','spec':self.spec(),'rationale':'fixture','moving_only':True})

    def test_first_defer_is_terminal_without_an_objective(self):
        self.inspect();self.broker.call('submit_grid_objective_decision',{'action':'defer','proposal_id':'','reason':'need unimplemented source'})
        self.assertFalse((self.workspace/'frozen-grid-objective-proposal.json').exists())
        self.assertEqual(assess_activity(self.workspace)['action'],'defer')

    def test_changed_input_is_rejected(self):
        with (self.workspace/'unlabelled-grid.npz').open('ab') as handle:handle.write(b'bad')
        with self.assertRaisesRegex(ValueError,'input changed'):self.broker.call('inspect_train_inventory',{})

    def test_changed_profile_cannot_be_selected(self):
        self.inspect();self.query();path=self.workspace/'queries/q1/result.json'
        value=load_json(path);value['profile']['all_rows']['covered_rows']=999;path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'hash mismatch'):self.broker.call('propose_objective',self.proposal_args())

    def test_no_undefined_skill_on_constant_label(self):
        self.inspect();self.broker.panel.midpoint[:]=.5;self.broker.panel.quote_age_ms[:]=0;self.query()
        with self.assertRaisesRegex(ValueError,'zero baseline'):self.broker.call('propose_objective',self.proposal_args())

    def test_duplicate_diagnostic_specs_rejected(self):
        self.inspect();self.query();self.query('q2');a=self.proposal_args();a['diagnostic_query_ids']=['q2']
        with self.assertRaisesRegex(ValueError,'must be distinct'):self.broker.call('propose_objective',a)

    def test_missing_midpoint_is_null_in_row_view(self):
        result=self.broker.call('inspect_train_rows',{'offset':0,'limit':4})
        self.assertIsNone(result['rows'][2]['midpoint']);self.assertEqual(len(result['rows']),4)

    def test_literature_is_explicit_frozen_notes(self):
        result=self.broker.call('search_public_literature',{'query':'noise'})
        self.assertEqual(result['mode'],'frozen_primary_source_notes_not_live_search')
        self.assertEqual(len(result['papers']),3)

    def test_real_stdio_mcp_transport_no_model(self):
        script=Path(__file__).parents[1]/'historical_grid_objective_controller.py'
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize'},
            {'jsonrpc':'2.0','id':2,'method':'tools/list'},
            {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'inspect_train_inventory','arguments':{}}}]
        run=subprocess.run([sys.executable,str(script),'--workspace',str(self.workspace)],
            input=''.join(json.dumps(v)+'\n' for v in requests),text=True,capture_output=True,timeout=15)
        self.assertEqual(run.returncode,0,run.stderr)
        responses=[json.loads(line) for line in run.stdout.splitlines()]
        self.assertEqual(len(responses[1]['result']['tools']),9)
        self.assertFalse(responses[2]['result']['isError'])

    def prepare_args(self):
        budget=PaidBudget.create(self.root/'budget',{'experiment_id':'fixture-exp','cap_usd':'5','target_usd':'5',
            'buckets_usd':{'setup':'5'},'authority':'unit test only'})
        env=self.root/'not-a-key.env';env.write_text('');token=self.root/'tokenizer';token.mkdir()
        return budget,{'panel_directory':self.data,'proposal':self.proposal,'annotations':self.side,'budget':budget.root,
            'runtime':Path(sys.executable),'env_file':env,'tokenizer':token}

    def test_prepare_copies_exact_source_without_dispatch(self):
        _,args=self.prepare_args();output=self.root/'session-plan'
        result=prepare(output,**args)
        self.assertFalse(result['paid_controller_started']);self.assertIn('grid_objective',result['command'])
        for name,sha in result['source_hashes'].items():self.assertEqual(file_hash(output/'source-snapshot'/name),sha)
        self.assertFalse((output/'dispatch-claim.json').exists())
        with self.assertRaises(FileExistsError):prepare(output,**args)

    def test_prepare_rejects_unresolved_paid_turn(self):
        budget,args=self.prepare_args();budget.reserve('prior-turn-001','setup','1','tinker','a'*64);budget.dispatch('prior-turn-001')
        with self.assertRaisesRegex(ValueError,'unresolved prior'):prepare(self.root/'fresh',**args)

    def test_prepare_rejects_permanent_run_id(self):
        budget,args=self.prepare_args();budget.reserve('fresh-turn-001','setup','1','tinker','a'*64)
        with self.assertRaisesRegex(ValueError,'permanent session'):prepare(self.root/'fresh',**args)

    def correction_fixture(self):
        self.inspect();self.query();self.broker.call('propose_objective',self.proposal_args())
        self.broker.call('submit_grid_objective_decision',{'action':'select','proposal_id':'p1','reason':'fixture'})
        (self.root/'session').mkdir();fresh_json(self.root/'session/assessment.json',{'valid':True,'process_reaped':True})
        directory=self.root/'numerical-audit';directory.mkdir()
        chosen=load_json(self.workspace/'frozen-grid-objective-proposal.json')
        claim={'panel_sha256':self.broker.result['panel_sha256'],
            'new_engine_sha256':file_hash(Path(__file__).parents[1]/'historical_grid_objectives.py'),
            'input_hashes':{str(self.workspace/'frozen-grid-objective-proposal.json'):file_hash(self.workspace/'frozen-grid-objective-proposal.json')}}
        fresh_json(directory/'claim.json',claim)
        correction={'query_id':'q1','corrected_profile':self.broker._query('q1')['profile']}
        correction['correction_sha256']=digest(correction);fresh_json(directory/'q1.json',correction)
        audit={'audit_pass':True,'claim_sha256':file_hash(directory/'claim.json'),'proposal_sha256':chosen['proposal_sha256'],
            'corrections':[{'query_id':'q1','correction_sha256':correction['correction_sha256']}]}
        audit['audit_sha256']=digest(audit);fresh_json(directory/'audit.json',audit)
        return directory

    def test_corrected_review_preserves_the_original_first_decision(self):
        directory=self.correction_fixture();new=self.root/'corrected-workspace'
        prepare_workspace(new,panel_directory=self.data,proposal=self.proposal,annotations=self.side,
            session_id='new-evidence',experiment_id='fixture-exp',numerical_audit=directory,previous_controller=self.root)
        broker=Broker(new);broker.call('inspect_train_inventory',{});broker.call('inspect_objective_registry',{})
        with self.assertRaisesRegex(ValueError,'inspect new numerical'):
            broker.call('profile_objective',{'query_id':'new','spec':self.spec(),'rationale':'fixture'})
        with self.assertRaisesRegex(ValueError,'inspect new numerical'):
            broker.call('submit_grid_objective_decision',{'action':'defer','proposal_id':'','reason':'fixture'})
        feedback=broker.call('inspect_numerical_correction',{})
        self.assertEqual(feedback['original_first_decision']['proposal_id'],'p1')
        self.assertTrue(feedback['new_evidence_not_a_score_retry'])
        broker.call('submit_grid_objective_decision',{'action':'defer','proposal_id':'','reason':'extension'})
        self.assertTrue(assess_activity(new)['valid'])

    def test_correction_bound_to_the_exact_repaired_engine(self):
        directory=self.correction_fixture()
        with patch('historical_grid_objective_controller.file_hash',return_value='wrong'):
            with self.assertRaises(ValueError):numerical_feedback(directory,self.root,self.broker.result)

    def test_missing_old_query_has_an_actionable_error(self):
        self.inspect()
        with self.assertRaisesRegex(ValueError,'reuse_corrected_objective_query'):
            self.broker.call('propose_objective',self.proposal_args())

    def test_verified_prior_query_reused_without_computation_or_faked_prescore(self):
        directory=self.correction_fixture();new=self.root/'reused-workspace'
        prepare_workspace(new,panel_directory=self.data,proposal=self.proposal,annotations=self.side,
            session_id='reused-evidence',experiment_id='fixture-exp',numerical_audit=directory,previous_controller=self.root)
        broker=Broker(new)
        for tool in ['inspect_train_inventory','inspect_objective_registry','inspect_numerical_correction']:broker.call(tool,{})
        with patch('historical_grid_objective_controller.profile',side_effect=AssertionError('must not recompute')):
            value=broker.call('reuse_corrected_objective_query',{'source_query_id':'q1','query_id':'new-q1','rationale':'same audited query'})
        self.assertFalse(value['new_target_computation'])
        claim=load_json(new/'queries/new-q1/query.json');self.assertFalse(claim['frozen_before_profile'])
        self.assertEqual(value['profile'],self.broker._query('q1')['profile'])
        args=self.proposal_args();args['primary_query_id']='new-q1'
        broker.call('propose_objective',args)
        broker.call('submit_grid_objective_decision',{'action':'select','proposal_id':'p1','reason':'same corrected target'})
        self.assertTrue(assess_activity(new)['valid'])

    def test_cannot_reuse_an_unaudited_target(self):
        self.inspect()
        with self.assertRaisesRegex(ValueError,'inspect source'):
            self.broker.call('reuse_corrected_objective_query',{'source_query_id':'q1','query_id':'new','rationale':'fixture'})
        self.broker.call('inspect_numerical_correction',{})
        with self.assertRaisesRegex(ValueError,'no independently audited'):
            self.broker.call('reuse_corrected_objective_query',{'source_query_id':'q1','query_id':'new','rationale':'fixture'})


if __name__=='__main__':unittest.main()
