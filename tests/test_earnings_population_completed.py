"""Completed-window inheritance tests migrated from reviewed private draft v2.

Production engineering modules are loaded from their current source. Transition unit tests
mock population byte validation/public awards; accounting uses only :memory:
SQLite and a declared grant-verifier seam. Separate explicitly opted-in tests exercise real historical origins and admission.
"""
from contextlib import ExitStack, nullcontext
from copy import deepcopy
import ast
import builtins
import importlib.util
import io
import json
import os
import re
import sqlite3
import socket
import subprocess
import sys
import tempfile
import types
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from market_rsi import digest

A = Path('/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/edgar-population-20261016')
S = Path(__file__).resolve().parents[1]


def apply_in_memory():
    # Production integration of the independently reviewed private v2 draft.
    names = ('earnings_population_completed', 'earnings_population_run',
             'earnings_population_campaign_admission', 'earnings_population_campaign',
             'earnings_population_recovery')
    result = {f'tools/{name}.py': (S/'tools'/(name+'.py')).read_text() for name in names}
    for source in result.values(): ast.parse(source)
    return result


def module_from_source(name, source):
    module = types.ModuleType(name); module.__file__ = str(A/(name+'.py'))
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


class CompletedDraftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = apply_in_memory()
        cls.module = module_from_source('earnings_population_completed', cls.sources['tools/earnings_population_completed.py'])

    def test_all_draft_hunks_match_current_sources_without_writing_them(self):
        self.assertEqual(set(self.sources), {'tools/earnings_population_completed.py',
            'tools/earnings_population_run.py', 'tools/earnings_population_campaign_admission.py',
            'tools/earnings_population_campaign.py','tools/earnings_population_recovery.py'})
        self.assertTrue((S/'tools/earnings_population_completed.py').is_file())

    def test_completed_status_scope_foreign_and_cycle_rejected_before_reader(self):
        m = self.module
        exact = {'path': str(m.bootstrap.OWNED/'attempts/edgar-population-20261016-07/population-run-result.json'), 'sha256': 'a'*64}
        for bad, seen in [(dict(exact, path='/private/tmp/foreign/population-run-result.json'), set()),
                          (dict(exact, sha256='bad'), set()),
                          (dict(exact, path=exact['path'].replace('result.json','failure.json')), set()),
                          (exact, {'edgar-population-20261016-07'})]:
            with self.subTest(binding=bad), self.assertRaises(ValueError):
                m._identity(bad, m.bootstrap.OWNED, m.bootstrap.LEDGER, m.bootstrap.REPO, seen)

    def test_register_observed_ancestor_QA_is_exact_opaque_and_development_only(self):
        m=self.module;reader=Mock();reader.extra=set();reader.ids=set();reader.root=Path('/synthetic')
        inherited=dict(evidence=[],population=dict(observations=[{'company_id':'CIK0000004457'}]))
        qa={'path':'/synthetic/ancestor-qa.json','sha256':'b'*64}
        with patch.object(m.tasks,'resident',return_value={'kernel':{'qa':qa}}) as resident:
            m._register(reader,inherited)
        resident.assert_called_once_with('CIK0000004457')
        reader.read.assert_called_once_with(qa,binary=True)
        self.assertIn(Path(qa['path']),reader.extra)
        inherited['population']['observations'].append({'company_id':'CIK0000021076'})
        with patch.object(m.tasks,'resident',side_effect=AssertionError('No held-out access')):
            with self.assertRaisesRegex(ValueError,'development companies only'):m._register(reader,inherited)

    def round_fixture(self, kind='scored_dev', axis='H'):
        m = self.module; base, chosen_parent, child_id = 'a'*64, 'b'*64, 'c'*64
        version=lambda ident:{'id':ident,'R':{'sha256':ident},'H':{'sha256':'6'*64}}
        state = {'stable_id': 'd'*64, 'explorers': [base, chosen_parent],
                 'versions':{ident:version(ident) for ident in (base,chosen_parent,'d'*64)}, 'history': []}
        seed = {'population': state, 'feedback': {'path': '/synthetic/prior.json','sha256':'e'*64},
                'last_scored_feedback': {'path':'/synthetic/old-score.json','sha256':'f'*64}}
        decision_binding = {'path':'/synthetic/decision.json','sha256':'1'*64}
        feedback_binding = {'path':'/synthetic/latest.json','sha256':'2'*64}
        frozen_binding = {'path':'/synthetic/frozen.json','sha256':'3'*64}
        packet_binding = {'path':'/synthetic/packet.json','sha256':'4'*64}
        chosen = {'axis':'continue' if kind=='no_change' else axis, 'parent_pair_sha256':chosen_parent,
            'feedback_sha256':digest(seed['feedback']), 'hypothesis':'Inert changed-parent method',
            'retire_branch_id':chosen_parent}
        child = None if kind=='no_change' else dict(version(child_id),parent=chosen_parent,axis=axis)
        review = {'accepted_for_exploration':kind=='scored_dev','evidence':[]}
        selected = deepcopy(state)
        if kind=='scored_dev':
            selected['explorers'] = [base, child_id]; selected['versions'][child_id] = child
            selected['history'] = ['explicit retire', 'retain child']
        measured = {'company_id':'CIK0000017313', 'frozen':frozen_binding,
            'results':[] if kind!='scored_dev' else [{'version_id':ident,'points':3.5,'evidence':[
                {'path':f'/synthetic/attempt/roles/forecast-01-{arm:02d}/program-executions.json','sha256':'9'*64}]}
                for arm,ident in enumerate((base,chosen_parent,child_id))]}
        manifest = {'baseline_version_id':base, 'comparison_policy':'chosen_parent_and_fixed_control','contract':{'synthetic':True}}
        with patch.object(m.campaign,'validate_result',side_effect=lambda row:row):
            feedback = m.campaign.feedback(manifest,seed,chosen,child,review,measured,1,decision_binding)
        last = feedback_binding if kind=='scored_dev' else seed['last_scored_feedback']
        final = {'population':selected, 'feedback':feedback_binding,'latest_feedback':feedback_binding,'last_scored_feedback':last}
        rows = {'input':{'packet':packet_binding}, 'controller':{'decision':decision_binding},
            'implement':{'candidate':child},'source_review':review,'execute':measured,
            'result_review':{'feedback':feedback_binding,'last_scored_feedback':last},'reconcile':final}
        values = {packet_binding['path']:{'population':state,'feedback':seed['feedback'],
                                        'round_index':1,'company_id':'CIK0000017313'},
            decision_binding['path']:chosen, frozen_binding['path']:selected, feedback_binding['path']:feedback,
            '/synthetic/attempt/population-01.json':selected}
        reader = Mock(); reader.read.side_effect=lambda bound:deepcopy(values[bound['path']])
        reader.pin.side_effect=lambda path:{'path':str(path),'sha256':'5'*64}
        reader.pair.side_effect=lambda path:{'output':rows[next(stage for stage in m.history.STAGES if f'-{stage}.done' in str(path))]}
        return reader,seed,rows,manifest,final

    def rounds(self, fixture, *, native=False):
        m=self.module; reader,seed,rows,manifest,final=fixture
        def retire(state,*args,**kwargs):
            value=deepcopy(state);value['explorers'].remove(args[0]);value['history'].append('explicit retire');return value
        def retain(state,child,**kwargs):
            value=deepcopy(state);value['explorers'].append(child['id']);value['versions'][child['id']]=child
            value['history'].append('retain child');return value
        with patch.object(m.pool,'validate',side_effect=lambda state:state), \
             patch.object(m.pool,'retire',side_effect=retire), patch.object(m.pool,'retain',side_effect=retain), \
             patch.object(m.campaign,'validate_result',side_effect=lambda row:row), \
             patch('earnings_population_broker.public_feedback',return_value={'synthetic_public_awards':True}):
            result=m._rounds(reader,Path('/synthetic/attempt'),{'companies':['CIK0000017313']},{},manifest,seed)
            return result if native else result[0]

    def test_actual_reconcile_pointers_for_scored_rejected_and_no_change(self):
        for kind in ('scored_dev','review_rejected','no_change'):
            for axis in ('R','H'):
                if kind=='review_rejected' and axis=='H': continue
                fixture=self.round_fixture(kind,axis)
                with self.subTest(kind=kind,axis=axis):
                    actual=self.rounds(fixture);self.assertEqual(actual,fixture[-1])
                    expected=actual['feedback'] if kind=='scored_dev' else fixture[1]['last_scored_feedback']
                    self.assertEqual(actual['last_scored_feedback'],expected)
                    self.assertEqual(actual['population'],fixture[-1]['population'])

    def test_reset_last_score_or_wrong_feedback_parent_is_refused(self):
        for mutate in ('last_score','parent'):
            fixture=self.round_fixture();reader,seed,rows,manifest,final=fixture
            if mutate=='last_score': rows['reconcile']['last_scored_feedback']=seed['last_scored_feedback']
            else:
                original=reader.read.side_effect
                def changed(bound):
                    value=original(bound)
                    if bound['path']=='/synthetic/decision.json':value['parent_pair_sha256']='0'*64
                    return value
                reader.read.side_effect=changed
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):self.rounds(fixture)

    def test_scored_initial_copy_preserves_original_last_score_pointer(self):
        source=self.sources['tools/earnings_population_campaign.py']
        self.assertIn('valid_last = last_scored == initial_feedback',source)
        self.assertNotIn("expected_last = (value['initial_feedback']",source)
        # Payload equality is only structural; admission still compares original
        # last_scored_feedback against the independently reconstructed predecessor.
        admission=self.sources['tools/earnings_population_campaign_admission.py']
        self.assertIn("manifest['last_scored_feedback'] != original['last_scored_feedback']",admission)

    def test_normal_continuation_has_no_03_repair_reassignment(self):
        run=self.sources['tools/earnings_population_run.py']; admission=self.sources['tools/earnings_population_campaign_admission.py']
        self.assertIn('repair = None if recover_from is not None or completed',run)
        self.assertIn("if completed and resumed['repair'] is not None:",admission)
        self.assertIn('from earnings_population_completed import load',run)
        self.assertIn('from earnings_population_completed import load',admission)

    def budget_fixture(self, count):
        m=self.module
        class KeptConnection(sqlite3.Connection):
            def close(self): pass  # Let the test inspect immutable rows after helper closure.
        db=sqlite3.connect(':memory:',factory=KeptConnection)
        self.addCleanup(lambda:sqlite3.Connection.close(db))
        db.execute('CREATE TABLE requests(id TEXT,model TEXT,reserved INTEGER,charged INTEGER,status TEXT)')
        db.executemany('INSERT INTO requests VALUES(?,?,?,?,?)',
                       [('old0','gpt-6.1-sol',10,10,'settled'),('old1','gpt-6.1-sol',20,20,'settled')])
        extra=m.history_snapshot(db,1);baseline=m.history_snapshot(db,2);requests=[]
        for index in range(count):
            ident=f'own-{index}';charge=index+7
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?)',(ident,'gpt-6.1-sol',charge,charge,'settled'))
            requests.append({'request_id':ident,'charged_nano_usd':charge,
                'request':{'path':'/synthetic/'+ident+'.json','sha256':'a'*64}})
        closed=m.history_snapshot(db,2+count);charge=sum(row['charged_nano_usd'] for row in requests)
        db.execute("INSERT INTO requests VALUES('later-unrelated','other',100,0,'reserved')")
        amendment={'path':'/synthetic/grant.json','sha256':'b'*64}
        runtime={'budget_amendment':amendment,'baseline':baseline,'additional_cap_nano_usd':5000000000}
        summary={'cap_usd':400,'model_cap_usd':100,'blocked':False,'unresolved_reserved_usd':0,
            'night_cap_usd':5,'prior_history_sha256':baseline['rows_sha256'],
            'charged_upper_bound_usd':closed['charged_nano_usd']/1e9,'night_charged_upper_bound_usd':charge/1e9}
        return db,extra,requests,amendment,runtime,summary

    def budget(self, fixture):
        m=self.module;db,extra,requests,amendment,runtime,summary=fixture
        db.commit()  # Close fixture setup transaction before the real read transaction.
        with patch.object(m,'_owned_requests',return_value=requests), \
             patch.object(m.history,'EXTRA_BASELINE',extra), \
             patch.object(m.sqlite3,'connect',return_value=db), \
             patch('earnings_population_budget.amendment_binding',return_value=amendment), \
             patch('earnings_population_budget.validate_cap',return_value=400000000000):
            return m._budget(types.SimpleNamespace(ledger=Path('/synthetic/sole.sqlite3')),
                             runtime,{'budget_summary':summary},{'budget':deepcopy(summary)})

    def test_variable_settled_prefix_preserves_costs_and_ignores_later_unrelated_reservation(self):
        for count in (1,3):
            fixture=self.budget_fixture(count);db=fixture[0]
            before=db.execute('SELECT rowid,* FROM requests').fetchall()
            with self.subTest(count=count):self.assertEqual(len(self.budget(fixture)),count)
            self.assertEqual(db.execute('SELECT rowid,* FROM requests').fetchall(),before)

    def test_original_charge_or_own_id_cannot_be_replaced(self):
        for kind in ('charge','identity'):
            fixture=self.budget_fixture(2);db=fixture[0]
            if kind=='charge':db.execute("UPDATE requests SET charged=8 WHERE id='own-0'")
            else:fixture[2][0]['request_id']='old0'
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.budget(fixture)

    def native_fixture(self, role='controller'):
        from earnings_research_state import sha as state_sha
        from supervisor_harness import capacity_feedback_engine as engine
        m=self.module;runtime={'path':'/synthetic/runtime.json','sha256':'c'*64}
        version={'id':'a'*64,'R':{'sha256':'b'*64},'H':{'sha256':'c'*64}}
        name='forecast-01-00' if role=='forecast' else 'controller-01'
        path=Path('/synthetic')/name/'context.json';slot=Path('/synthetic/attempt/roles')/name
        config={'root':'/synthetic/attempt','source_commit':'d'*40,'cutoff_utc':'2026-10-17T03:00:00Z',
            'deadline_utc':'2026-10-17T03:01:00Z','slots':{role:[str(slot)]},
            'sources':{'forecaster':{'path':'/synthetic/forecaster.py','sha256':'d'*64}}}
        expected={name:{'role':role,'round_index':1,'company_id':'CIK0000017313','version':version}}
        company={'cik':'CIK0000017313','cutoff':'2026-02-01','visible_root':'/synthetic/Capital',
                 'target_accession':'original-only','allowed_files':[]}
        data={'path':'/synthetic/original-data.json','sha256':'e'*64}
        kernel={'scorer':{'path':'/synthetic/scorer.py','sha256':'e'*64},
                'qa':{'path':'/synthetic/qa.json','sha256':'f'*64}}
        case={'cik':company['cik'],'cutoff':company['cutoff'],'evaluation_kernel':kernel,
              'target_accession':company['target_accession'],'allowed_manifest_sha256':'1'*64}
        resident={'company':company,'data_binding':data,'kernel':kernel,'case':case,
                  'runtime':{'max_input_tokens':100000,'max_output_tokens':25000,'company_wall_seconds':1800}}
        python={'path':'/synthetic/python','sha256':'2'*64}
        task='population-case-'+digest([str(path.parent),company['cik'],version['id']])[:24]
        empty=dict(schema='earnings_research_state_v1',task_id=task,cik=company['cik'],cutoff=company['cutoff'],records=[])
        initial={'path':str(path.parent/'initial-state'/(state_sha(empty)+'.json')),'sha256':state_sha(empty)}
        tokens={'researcher_v0.py':'b'*64,'harness_v0.py':'c'*64,'predictor.py':'d'*64,
                'evaluation_scorer.py':'e'*64,'evaluation_qa.json':'f'*64}
        component=lambda names,cfg:dict(sources={n:tokens[n] for n in names},configuration_sha256=digest(cfg))
        manifest=engine.identity.manifest(
            kernel=component(['evaluation_scorer.py','evaluation_qa.json'],dict(kernel=kernel,case=case,data=data)),
            predictor=component(['predictor.py'],dict(output='original_five_numeric_predictions')),
            harness=component(['harness_v0.py'],dict(population_component='H')),
            researcher=component(['researcher_v0.py'],dict(population_component='R')),
            memory=initial['sha256'],model=dict(requested_model='gpt-6.1-sol',serving_snapshot='unknown',
                serving_snapshot_verified=False),runtime=dict(python=python,dependencies={}))
        pair=engine.activation.pair(manifest)
        fixed=dict(model_sha256=manifest['M'],evaluation_sha256=manifest['K'],
            data_scope_sha256=digest(dict(company=case,data=data)),authority_sha256=digest(runtime),
            resource_policy_sha256=digest(resident['runtime']))
        state={'initialized':True,'attempts_claimed':0,'active_attempt_ids':[],'active_attempt_id':None,
            'micro_evolution':{'pending':None,'active_pair':pair,'fixed_context':fixed},'capacity_work':[]}
        batch=Mock(lock_path=Path('/synthetic/.batch.lock'),snapshot_path=Path('/synthetic/batch.json'))
        reader=Mock();reader.pin.side_effect=lambda path:{'path':str(path),
            'sha256':tokens.get(path.name,'9'*64)}
        reader.read.return_value={'schema':'earnings_population_native_case_v1',
            'company':deepcopy(company),'authority':runtime,'source_commit':'d'*40,
            'pool_version':deepcopy(version),'manifest':manifest,'data':deepcopy(data),'kernel':deepcopy(kernel),
            'case':deepcopy(case),'runtime':deepcopy(resident['runtime']),'python':deepcopy(python),'initial_state':initial,
            'window':{'start_utc':'2026-10-17T01:30:00Z','deadline_utc':'2026-10-17T03:01:00Z'}}
        values={initial['path']:empty}
        if role=='forecast':
            names=('population-public-feedback.json','result.json','score.json','effective-capacity.json','research-state-output.json')
            bound={n:reader.pin(slot/n) for n in names};terminal=reader.pin(slot/'terminal-state.json')
            row=dict(version_id=version['id'],points=3.5,evidence=[bound[n] for n in names]+[terminal])
            expected[name]['forecast_result']=row
            values[bound[names[0]]['path']]=dict(native_pair_sha256=digest(pair),effective_input=bound[names[3]],
                pool_sources={a:version[a]['sha256'] for a in ('R','H')},version_id=version['id'],
                company_id=company['cik'],points=3.5)
            copied=dict(path=str(path.parent/'forecast-state'/(initial['sha256']+'.json')),
                        sha256=initial['sha256'])
            values[copied['path']]=deepcopy(empty)
            values[bound[names[3]]['path']]=dict(initial_state=copied)
            values[bound[names[4]]['path']]=dict(state=terminal)
            verified=dict(result=bound[names[1]],score=bound[names[2]],state=terminal,
                consumed=dict(pair_sha256=digest(pair),state_sha256=initial['sha256']),artifacts=row['evidence'][1:])
            state['capacity_work']=[dict(work_id='capacity-'+digest([str(slot),version['id'],company['cik']])[:32],
                pair_sha256=digest(pair),evidence_sha256=digest(dict(context=reader.pin(path),slot=str(slot),version=version)),
                status='completed',output_evidence_sha256=digest(verified),event_time_utc='2026-10-17T02:00:00Z',
                completed_at_utc='2026-10-17T02:10:00Z')]
        reader.read.side_effect=lambda binding:deepcopy(values[binding['path']]) if binding['path'] in values else reader.read.return_value
        batch._read_records.return_value=[];batch._replay.return_value=deepcopy(state)
        batch._read_snapshot.return_value=deepcopy(state)
        native=Mock();native.glob.return_value=[path]
        return reader,native,runtime,config,expected,batch,state,resident,python,values

    def native(self, fixture):
        m=self.module;reader,native,runtime,config,expected,batch,state,resident,python,values=fixture
        with patch.object(m,'ContinuousDiscoveryBatch',return_value=batch), \
             patch.object(m.os,'open',return_value=42),patch.object(m.os,'fdopen',return_value=nullcontext(Mock())), \
             patch.object(m.fcntl,'flock'):
            return m._native(reader,native,runtime,config,expected,resident,python)

    def test_native_idle_guard_uses_pure_replay_not_mutating_snapshot(self):
        fixture=self.native_fixture();self.assertEqual(len(self.native(fixture)),2)
        fixture[5].snapshot.assert_not_called()
        fixture[5]._read_snapshot.return_value=dict(fixture[6],active_attempt_ids=['pending'])
        with self.assertRaises(ValueError):self.native(fixture)

    def test_missing_extra_wrong_round_or_undeclared_native_slot_is_refused(self):
        for kind in ('missing','extra','round','undeclared'):
            fixture=self.native_fixture();reader,native,runtime,config,expected,batch,state=fixture[:7]
            if kind=='missing':native.glob.return_value=[]
            elif kind=='extra':native.glob.return_value.append(Path('/synthetic/author-99/context.json'))
            elif kind=='round':native.glob.return_value=[Path('/synthetic/controller-02/context.json')]
            else:config['slots']['controller']=[]
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.native(fixture)

    def test_wrong_native_version_copy_manifest_company_or_pending_pair_is_refused(self):
        for kind in ('version','source','manifest','company','pair'):
            fixture=self.native_fixture();reader,native,runtime,config,expected,batch,state=fixture[:7]
            if kind=='version':reader.read.return_value['pool_version']['id']='0'*64
            elif kind=='source':reader.pin.side_effect=lambda path:{'path':str(path),'sha256':'0'*64}
            elif kind=='manifest':reader.read.return_value['manifest']['components']['R']['sources']['researcher_v0.py']='0'*64
            elif kind=='company':reader.read.return_value['company']['cik']='CIK0000021076'
            else:batch._replay.return_value['micro_evolution']['active_pair']['researcher_sha256']='0'*64
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.native(fixture)

    def test_rounds_produce_exact_parent_and_forecast_arm_native_versions(self):
        final,expected=self.rounds(self.round_fixture(),native=True)
        self.assertEqual(set(expected),{'controller-01','author-01','review-01',
            'forecast-01-00','forecast-01-01','forecast-01-02'})
        self.assertEqual(expected['controller-01']['version']['id'],'d'*64)
        self.assertEqual(expected['author-01']['version']['id'],'b'*64)
        self.assertEqual(expected['review-01']['version']['id'],'c'*64)
        self.assertEqual([expected[f'forecast-01-{i:02d}']['version']['id'] for i in range(3)],
                         ['a'*64,'b'*64,'c'*64])
        self.assertTrue(all(row['round_index']==1 for row in expected.values()))

    def test_inactive_rejected_H_fails_closed_instead_of_losing_source_reference(self):
        with self.assertRaisesRegex(ValueError,'inactive H reference paging is unsupported'):
            self.rounds(self.round_fixture('review_rejected','H'))

    def test_forecast_requires_one_exact_completed_owned_work_not_vacuous_empty(self):
        fixture=self.native_fixture('forecast');self.assertEqual(len(self.native(fixture)),2)
        for kind in ('missing','extra','work_id','pair_sha256','evidence_sha256','output_evidence_sha256','status'):
            fixture=self.native_fixture('forecast');batch=fixture[5]
            state=batch._replay.return_value
            if kind=='missing':state['capacity_work']=[]
            elif kind=='extra':state['capacity_work']*=2
            else:state['capacity_work'][0][kind]='wrong' if kind=='status' else '0'*64
            batch._read_snapshot.return_value=deepcopy(state)
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'owned forecast claim/completion'):
                self.native(fixture)

    def test_forecast_case_result_state_or_evidence_cannot_borrow_completed_work(self):
        for kind in ('company','points','state','missing_artifact'):
            fixture=self.native_fixture('forecast');reader,native,runtime,config,expected,batch,state,resident,python,values=fixture
            if kind in ('company','points'):
                public=next(value for name,value in values.items() if name.endswith('population-public-feedback.json'))
                public['company_id' if kind=='company' else 'points']='CIK0000003545' if kind=='company' else 4
            elif kind=='state':
                effective=next(value for name,value in values.items() if name.endswith('effective-capacity.json'))
                effective['initial_state']=dict(effective['initial_state'],sha256='0'*64)
            else:expected['forecast-01-00']['forecast_result']['evidence'].pop(1)
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.native(fixture)

    def test_nonforecast_native_role_cannot_invent_work(self):
        fixture=self.native_fixture();fixture[5]._replay.return_value['capacity_work']=[{'status':'completed'}]
        fixture[5]._read_snapshot.return_value=deepcopy(fixture[5]._replay.return_value)
        with self.assertRaisesRegex(ValueError,'Nonforecast Native role'):self.native(fixture)

    def test_forecast_requires_original_state_copy_path_and_identical_empty_payload(self):
        for kind in ('wrong_path','changed_records'):
            fixture=self.native_fixture('forecast');values=fixture[-1]
            effective=next(value for name,value in values.items() if name.endswith('effective-capacity.json'))
            if kind=='wrong_path':
                effective['initial_state']=dict(effective['initial_state'],path='/synthetic/unrelated/state.json')
            else:
                values[effective['initial_state']['path']]['records']=[{'kind':'invented'}]
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'public result/Native'):
                self.native(fixture)

    def test_all_original_native_financial_and_protected_identities_are_required(self):
        for kind in ('data','kernel','case','runtime','python','empty_state','predictor','scorer','qa','model','fixed_context'):
            fixture=self.native_fixture();reader=fixture[0];value=reader.read.return_value
            if kind=='data':value['data']['sha256']='0'*64
            elif kind=='kernel':value['kernel']['qa']['sha256']='0'*64
            elif kind=='case':value['case']['target_accession']='different'
            elif kind=='runtime':value['runtime']['max_input_tokens']+=1
            elif kind=='python':value['python']['sha256']='0'*64
            elif kind=='empty_state':value['initial_state']=dict(value['initial_state'],sha256='0'*64)
            elif kind in ('predictor','scorer','qa'):
                name={'predictor':'predictor.py','scorer':'evaluation_scorer.py','qa':'evaluation_qa.json'}[kind]
                pin=reader.pin.side_effect
                reader.pin.side_effect=lambda path,pin=pin,name=name:dict(pin(path),sha256='0'*64) if path.name==name else pin(path)
            elif kind=='model':value['manifest']['M']='0'*64
            else:
                fixture[5]._replay.return_value['micro_evolution']['fixed_context']['evaluation_sha256']='0'*64
                fixture[5]._read_snapshot.return_value=deepcopy(fixture[5]._replay.return_value)
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.native(fixture)

    def test_historical_recovery_plan_uses_verified_Git_not_current_disk(self):
        import earnings_entry
        m=self.module
        recovery=module_from_source('private_historical_recovery',self.sources['tools/earnings_population_recovery.py'])
        raw=b'{"schema":"synthetic_old_recovery_plan","original":true}'
        binding={'path':str(m.bootstrap.REPO/recovery.PLAN),'sha256':__import__('hashlib').sha256(raw).hexdigest()}
        reader=m.history._Reader(m.bootstrap.OWNED,m.bootstrap.LEDGER,m.bootstrap.REPO,'edgar-population-20261016-07')
        reader.commit='a'*40;reader.sources={(binding['path'],binding['sha256'])}
        with patch.object(m.history,'_git',return_value=raw) as git, \
             patch.object(earnings_entry,'checked',side_effect=AssertionError('Do not reopen edited current plan')):
            value=recovery._read_plan(binding,root=m.bootstrap.OWNED,ledger=m.bootstrap.LEDGER,
                repo=m.bootstrap.REPO,historical_reader=reader)
        self.assertTrue(value['original']);git.assert_called_once_with(m.bootstrap.REPO,'a'*40,recovery.PLAN)

    def test_historical_recovery_plan_rejects_wrong_reader_source_or_Git_bytes(self):
        m=self.module
        recovery=module_from_source('private_historical_recovery',self.sources['tools/earnings_population_recovery.py'])
        binding={'path':str(m.bootstrap.REPO/recovery.PLAN),'sha256':'b'*64}
        for kind in ('reader','source','commit','bytes'):
            reader=m.history._Reader(m.bootstrap.OWNED,m.bootstrap.LEDGER,m.bootstrap.REPO,'edgar-population-20261016-07')
            reader.commit='a'*40;reader.sources={(binding['path'],binding['sha256'])}
            if kind=='reader':reader=types.SimpleNamespace(read=lambda b:{'fabricated':True})
            elif kind=='source':reader.sources=set()
            elif kind=='commit':reader.commit='not-a-commit'
            with self.subTest(kind=kind),patch.object(m.history,'_git',return_value=b'{}'),self.assertRaises(ValueError):
                recovery._read_plan(binding,root=m.bootstrap.OWNED,ledger=m.bootstrap.LEDGER,
                    repo=m.bootstrap.REPO,historical_reader=reader)

    def test_original_recovery_default_still_reads_current_source_bound_plan(self):
        import earnings_entry
        m=self.module
        recovery=module_from_source('private_historical_recovery',self.sources['tools/earnings_population_recovery.py'])
        binding={'path':str(m.bootstrap.REPO/recovery.PLAN),'sha256':'b'*64}
        with patch.object(earnings_entry,'checked',return_value=b'{"fresh":true}') as current:
            self.assertEqual(recovery._read_plan(binding,root=m.bootstrap.OWNED,ledger=m.bootstrap.LEDGER,
                repo=m.bootstrap.REPO),{'fresh':True})
        current.assert_called_once_with(binding)


@unittest.skipUnless(os.environ.get('MARKET_RSI_PRIVATE_VERIFY_CLOSED03')=='1',
                     'Explicit bounded real03 read-only guarded audit required')
class Actual03Compatibility(unittest.TestCase):
    def test_generic_dispatch_preserves_strict_actual03_result_under_read_guards(self):
        module=module_from_source('earnings_population_completed',apply_in_memory()['tools/earnings_population_completed.py'])
        m=module;opened=[];residents=[];connections=[];git_calls=[]
        original_resident=m.tasks.resident;original_connect=sqlite3.connect;original_run=subprocess.run
        def resident(cik):
            if cik not in m.DEV:raise AssertionError('Forbidden non-development resident '+str(cik))
            residents.append(cik);return original_resident(cik)
        def guarded_open(function):
            def checked(path,*args,**kwargs):
                if not isinstance(path,int):
                    text=os.fsdecode(path)
                    if set(re.findall(r'CIK[0-9]{10}',text))-m.DEV:
                        raise AssertionError('Forbidden non-development file open '+text)
                    opened.append(text)
                return function(path,*args,**kwargs)
            return checked
        def connect(path,*args,**kwargs):
            self.assertTrue(str(path).endswith('?mode=ro'));self.assertIs(kwargs.get('uri'),True)
            connections.append(str(path));return original_connect(path,*args,**kwargs)
        def command(command,*args,**kwargs):
            self.assertEqual(command[:2],['git','show']);git_calls.append(command[:])
            return original_run(command,*args,**kwargs)
        binding={'path':str(m.bootstrap.OWNED/'attempts'/m.bootstrap.IDENT/'population-run-result.json'),
                 'sha256':m.bootstrap.RESULT_SHA}
        strict=m.bootstrap.load
        with ExitStack() as stack:
            stack.enter_context(patch.object(m.tasks,'resident',side_effect=resident))
            for owner in (builtins,io,os):stack.enter_context(patch.object(owner,'open',guarded_open(owner.open)))
            stack.enter_context(patch.object(sqlite3,'connect',side_effect=connect))
            stack.enter_context(patch.object(subprocess,'run',side_effect=command))
            stack.enter_context(patch.object(socket,'create_connection',side_effect=AssertionError('No network')))
            called=stack.enter_context(patch.object(m.bootstrap,'load',wraps=strict))
            result=m.load(binding,root=m.bootstrap.OWNED,ledger=m.bootstrap.LEDGER,repo=m.bootstrap.REPO)
            audited=m.bootstrap.history.e.strict_json(m.bootstrap.history.e.checked(m.bootstrap.AUDIT))
        called.assert_called_once_with(binding,root=m.bootstrap.OWNED,ledger=m.bootstrap.LEDGER,repo=m.bootstrap.REPO)
        self.assertEqual(digest(result['population']),'b4b657f387462a49f6a52bc964d8922d73d886b90fd6b6e95ad6f596a7370ce9')
        self.assertEqual(result['feedback'],audited['retained_state_and_next_use']['latest_feedback'])
        self.assertEqual(result['research_feedback']['kind'],'review_rejected')
        self.assertEqual(result['research_feedback']['score_state'],'unscored')
        self.assertEqual(result['research_feedback']['results'],[])
        self.assertEqual(result['research_feedback']['last_scored_feedback'],result['last_scored_feedback'])
        self.assertEqual(result['previous_result'],binding)
        self.assertTrue(residents);self.assertTrue(opened);self.assertTrue(connections)
        print('ACTUAL03_GUARDED',json.dumps({'pool_sha256':digest(result['population']),
            'latest_feedback':result['feedback'],'last_scored_feedback':result['last_scored_feedback'],
            'resident_CIKs':sorted(set(residents)),'file_opens':len(opened),'readonly_db_connections':len(connections),
            'historical_git_calls':len(git_calls),'strict03_delegate_calls':called.call_count},sort_keys=True))


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_COMPLETED07')=='1',
                     'Explicit bounded real07 read-only origin and inert driver check required')
class Actual07CompletedOrigin(unittest.TestCase):
    def test_real07_origin_then_original_driver_receives_exact_pool_latest_and_last_score(self):
        import earnings_population_completed as m
        import earnings_population_loop as loop
        from supervisor_harness import capacity_feedback_engine as engine
        opened=[];residents=[];connections=[];git_calls=[];opaque=set()
        original_resident=m.tasks.resident;original_connect=sqlite3.connect
        original_run=subprocess.run;original_decode=json.loads
        def resident(cik):
            if cik not in m.DEV:raise AssertionError('Forbidden nondevelopment resident')
            value=original_resident(cik);opaque.add(value['kernel']['qa']['sha256'])
            residents.append(cik);return value
        def guarded_open(function):
            def checked(path,*args,**kwargs):
                if not isinstance(path,int):
                    text=os.fsdecode(path)
                    if set(re.findall(r'CIK[0-9]{10}',text))-m.DEV:
                        raise AssertionError('Forbidden nondevelopment file open')
                    mode=args[0] if args else kwargs.get('mode','r')
                    if isinstance(mode,str) and any(c in mode for c in ('w','a','x','+')):
                        raise AssertionError('No historical writes')
                    opened.append(text)
                return function(path,*args,**kwargs)
            return checked
        def decode(value,*args,**kwargs):
            raw=value.encode() if isinstance(value,str) else value
            if isinstance(raw,(bytes,bytearray)) and __import__('hashlib').sha256(raw).hexdigest() in opaque:
                raise AssertionError('QA may not be decoded')
            return original_decode(value,*args,**kwargs)
        def connect(path,*args,**kwargs):
            self.assertTrue(str(path).endswith('?mode=ro'));self.assertIs(kwargs.get('uri'),True)
            connections.append(str(path));return original_connect(path,*args,**kwargs)
        def command(command,*args,**kwargs):
            self.assertEqual(command[:2],['git','show']);git_calls.append(command[:])
            return original_run(command,*args,**kwargs)
        binding={'path':str(m.bootstrap.OWNED/'attempts/edgar-population-20261016-07/population-run-result.json'),
                 'sha256':'5ec42e22ff34dbc4a48a6bca57af04f8ccfd0f5fca059e5c49f7e1b21026d466'}
        with ExitStack() as stack:
            stack.enter_context(patch.object(m.tasks,'resident',side_effect=resident))
            for owner in (builtins,io,os):stack.enter_context(patch.object(owner,'open',guarded_open(owner.open)))
            stack.enter_context(patch.object(sqlite3,'connect',side_effect=connect))
            stack.enter_context(patch.object(subprocess,'run',side_effect=command))
            stack.enter_context(patch.object(json,'loads',side_effect=decode))
            stack.enter_context(patch.object(socket.socket,'connect',side_effect=AssertionError('No network')))
            origin=m.load(binding,root=m.bootstrap.OWNED,ledger=m.bootstrap.LEDGER,repo=m.bootstrap.REPO)
            attempt=Path(binding['path']).parent
            last=engine.read(engine.pin(attempt/'loop/round-0002-reconcile.done.json'))['output']
            prior_manifest=engine.read(engine.pin(m.bootstrap.OWNED/'inputs/edgar-population-20261016-07/campaign.json'))
            self.assertEqual(origin['population'],last['population'])
            self.assertEqual(origin['feedback'],last['latest_feedback'])
            self.assertEqual(origin['last_scored_feedback'],last['last_scored_feedback'])
            self.assertNotEqual(origin['feedback'],origin['last_scored_feedback'])
            self.assertEqual(Path(origin['feedback']['path']).name,'feedback-02.json')
            self.assertEqual(Path(origin['last_scored_feedback']['path']).name,'feedback-01.json')
            self.assertEqual(origin['research_feedback']['kind'],'review_rejected')
            self.assertEqual(origin['research_feedback']['score_state'],'unscored')
            self.assertEqual(origin['research_feedback']['results'],[])
            self.assertEqual(origin['reference_candidate']['id'],origin['research_feedback']['candidate']['id'])
            self.assertNotIn(origin['reference_candidate']['id'],origin['population']['versions'])
            accepted='29ac9cbd7166c6e83cb1866028485264d6649fcfe152da9414ec5c3b163742b3'
            self.assertIn(accepted,origin['population']['explorers'])
        # This is a temporary original-driver contract check, NOT live admission.
        # Actual prepare/preflight needs a committed source and belongs to Root.
        packets=[];unused=[]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve()
            copied=engine.save(root/'initial-feedback.json',origin['research_feedback'])
            manifest=dict(prior_manifest,max_decisions=1,initial_population_sha256=digest(origin['population']),
                initial_feedback=copied,last_scored_feedback=origin['last_scored_feedback'],
                initial_feedback_contract_sha256=origin['research_feedback']['campaign_contract_sha256'])
            bound=engine.save(root/'campaign.json',manifest)
            def controller(packet,slot):
                packets.append(deepcopy(packet))
                return engine.save(root/'continue.json',dict(axis='continue',
                    parent_pair_sha256=accepted,feedback_sha256=digest(packet['feedback']),
                    hypothesis='Synthetic no-change transport check; no score or model claim.'))
            def forbidden(*args):unused.append(args);raise AssertionError('No Author/review/forecast in inert check')
            result=loop.run(root/'loop-run',origin['population'],m.campaign.PANEL,
                dict(controller=controller,author=forbidden,review=forbidden,forecast=forbidden),
                admit=lambda ctx:True,max_rounds=1,campaign=bound)
            self.assertEqual(len(packets),1);self.assertFalse(unused)
            self.assertEqual(packets[0]['population'],origin['population'])
            self.assertEqual(engine.read(packets[0]['feedback']),origin['research_feedback'])
            self.assertEqual(packets[0]['last_scored_feedback'],origin['last_scored_feedback'])
            self.assertEqual(result['result']['population'],origin['population'])
            self.assertEqual(result['result']['last_scored_feedback'],origin['last_scored_feedback'])
        print('ACTUAL07_GUARDED',json.dumps(dict(pool_sha256=digest(origin['population']),
            latest_feedback=origin['feedback'],last_scored_feedback=origin['last_scored_feedback'],
            explorers=origin['population']['explorers'],reference_id=origin['reference_candidate']['id'],
            resident_CIKs=sorted(set(residents)),file_opens=len(opened),readonly_db_connections=len(connections),
            historical_git_calls=len(git_calls),original_driver_first_packet='PASS_TEMP_INERT_NOT_LIVE_ADMISSION'),sort_keys=True))


if __name__=='__main__':unittest.main(verbosity=2)
