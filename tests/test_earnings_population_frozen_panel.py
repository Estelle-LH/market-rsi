"""Portable P1 identities: invented data only, no Native execution or history admission.

Positive seams are the expensive completed.load and resident functions, plus
temporary expected-identity constants. File/hash/split/comparator/final parsing
and public-award checks remain original. No QA file is created or read.
"""
from contextlib import ExitStack
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import earnings_population as population
from supervisor_harness import capacity_feedback_engine as engine
import earnings_population_frozen_panel as panel
from earnings_open_feedback import project_target_scores
from market_rsi import digest


class PanelFixture:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix='frozen-panel-')
        self.home = Path(self.temp.name).resolve()
        self.root, self.repo = self.home/'owned', self.home/'repo'
        self.root.mkdir(); self.repo.mkdir()
        self.stack = ExitStack()
        self.training = ['CIK%010d'%n for n in range(1,26)]
        self.heldout = ['CIK%010d'%n for n in range(101,126)]
        self.events = []
        t, tasks = panel.training, panel.tasks
        self.split = self.save(self.root/'split.json',dict(
            schema='edgar_retrospective_prospectively_sealed_split_v1',
            status='FROZEN_RETROSPECTIVE_PROSPECTIVE_SEAL',
            historical_isolation_certified=False,training=self.training,heldout=self.heldout))
        self.data = self.save(self.root/'data.json',{'inert':'data binding'})
        self.scorer = self.source(self.root/'scorer.py','# Inert synthetic scorer identity only.\n')
        self.driver = self.source(self.root/'driver.py','# Inert synthetic plain-driver identity only.\n')
        self.fixed = dict(models={t.MODEL:dict(api_model=t.MODEL,effort='max',input='2',
            cached='.1',output='10',write='2.5')},max_input_tokens=100000,
            max_output_tokens=25000,max_turns_per_company=24,company_wall_seconds=1800,
            request_timeout_seconds=180,service_tier='default')
        self.runtime = self.save(self.root/'forecast-runtime.json',self.fixed)
        for module, values in ((t,dict(ROOT=self.root,SPLIT=Path(self.split['path']),
                SPLIT_SHA=self.split['sha256'],KNOWN3=set(self.training[:3]),
                FULL_PLAN=self.data,SCORER=self.scorer,RUNTIME=self.runtime,DRIVER=self.driver)),
                (tasks,dict(FULL_PLAN=self.data,SCORER=self.scorer,RUNTIME=self.runtime))):
            for key,value in values.items(): self.stack.enter_context(patch.object(module,key,value))
        self.comparator = self.comparator_files()
        receipt = self.save(self.root/'source-evidence.json',{'synthetic':'not execution'})
        h = self.source(self.root/'H.py','# Synthetic observation adapter, never executed.\n')
        versions = []
        for i in range(4):
            r = self.source(self.root/('R%d.py'%i),'# Synthetic R%d identity, never executed.\n'%i)
            versions.append(population.version(r,h,parent=None if not versions else versions[-1]['id'],
                axis='baseline' if not versions else 'R',method='synthetic-%d'%i,
                author='portable fixture',evidence=[receipt]))
        seed, self.control, self.parent, self.child = versions
        state = population.initialize(seed,{k:digest(k) for k in ('K','M','C')})
        for value in (self.control,self.parent):
            state = population.retain(state,value,reason='synthetic archive',evidence=[receipt])
        for value in (self.control,self.parent):
            state = population.retire(state,value['id'],reason='archive not deletion',evidence=[receipt])
        self.state = population.retain(state,self.child,reason='synthetic selected child',evidence=[receipt])
        self.attempt = self.root/'attempts'/'edgar-population-20261016-36'
        pool = self.save(self.attempt/'population-01.json',self.state)
        feedback_value = dict(baseline_version_id=self.control['id'],synthetic=True)
        feedback = self.save(self.attempt/'feedback-01.json',feedback_value)
        self.origin = self.save(self.attempt/'population-run-result.json',dict(
            status='COMPLETED_DISCOVERY_PILOT',result=dict(status='completed',completed_rounds=1,
                result=dict(population=self.state,feedback=feedback,latest_feedback=feedback,
                    last_scored_feedback=feedback,artifacts=[pool,feedback]))))
        names = ('forecaster','tools/earnings_entry.py','tools/earnings_open_worker.py',
                 'tools/earnings_population_execution.py')
        sources = {name:self.source(self.repo/name,'# Synthetic forecasting source identity.\n') for name in names}
        original_runtime = self.save(self.root/'inputs'/self.attempt.name/'runtime-reviewed.json',dict(
            schema='earnings_population_runtime_v1',id=self.attempt.name,source_commit='b'*40,
            rates=self.fixed['models'][t.MODEL],role_efforts={'forecast':'max'},
            limits={'forecast':dict(max_input_tokens=100000,max_output_tokens=25000,wall_seconds=1800)},
            sources=sources))
        self.base = dict(population=self.state,feedback=feedback,research_feedback=feedback_value,
            last_scored_feedback=feedback,previous_result=self.origin,evidence=[original_runtime,self.origin])
        self.authority = self.save(self.root/'authority.json',dict(
            schema='earnings_training25_direct_full_candidate_panel_authority_v1',
            Round0={'manifest_sha256':self.comparator['sha256']},first_panel_candidate=dict(
                id=self.child['id'],actual_parent=self.parent['id'],R=self.child['R']['sha256'],
                parent_R=self.parent['R']['sha256'],H=h['sha256'])))
        for name,value in dict(AUTHORITY=self.authority,ORIGIN=self.origin,ROUND0=self.comparator,
                CONTROL_ID=self.control['id'],CONTROL_R=self.control['R']['sha256']).items():
            self.stack.enter_context(patch.object(panel,name,value))
        self.residents = {cik:self.resident(cik) for cik in self.training}
        self.completed = self.stack.enter_context(patch.object(panel.completed,'load',side_effect=self.old_origin))
        self.resident_mock = self.stack.enter_context(patch.object(tasks,'resident',side_effect=self.get_resident))
        self.stack.enter_context(patch('socket.socket',side_effect=AssertionError('No network in P1 tests')))

    def close(self):
        self.stack.close(); self.temp.cleanup()

    def save(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True)
        engine.save(path,value)
        return engine.pin(path)

    def source(self,path,text):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text)
        return engine.pin(path)

    def comparator_files(self):
        t = panel.training
        ident = 'PORTABLE-PLAIN25'
        out = self.root/'training-baseline'/ident
        config = self.save(self.root/(ident+'.config.json'),dict(
            schema='edgar_train25_plain_baseline_window_v1',split=self.split,driver=self.driver,
            source_commit=t.SOURCE,model=t.MODEL,runtime=self.runtime,data=self.data,scorer=self.scorer,
            retries=False,execution='plain_original_forecast_no_capacity_worker_no_recipe',
            companies=self.training,identifier=ident,output=str(out)))
        review = self.save(self.root/'review.json',dict(status='PASS',config=config,driver=self.driver))
        checkpoint = self.save(self.root/'checkpoint.json',dict(config=config,driver=self.driver,
            review=review,commit='1'*40))
        window = self.save(out/'identity.json',dict(config=config,review=review,checkpoint=checkpoint))
        rows = []
        for index,cik in enumerate(self.training,1):
            slot = out/('%02d-'%index+cik)
            identity = self.save(slot/'identity.json',dict(cik=cik,case={'cik':cik},config=config,
                model=t.MODEL,runtime=self.runtime,source_commit=t.SOURCE,
                researcher_capacity_worker=None,research_recipe=None))
            predictions = {'predictions':[dict(target_id=tid,predicted_value=str(index)) for tid in t.TARGETS]}
            pred = self.save(slot/'predictions.json',predictions)
            score_value = dict(target_count=5,prediction_count=5,duplicate_prediction_ids=[],
                unknown_prediction_ids=[],score_out_of_5=3,per_target=[dict(target_id=tid,
                    points_awarded=1 if i<3 else 0) for i,tid in enumerate(t.TARGETS)])
            score = self.save(slot/'score.json',score_value)
            public = self.save(slot/'public-feedback.json',dict(cik=cik,score_out_of_5=3,
                per_target=project_target_scores(score_value,t.HEADERS)))
            result = self.save(slot/'result.json',dict(status='COMPLETED_SCORED',cik=cik,
                scored_targets=5,turns=1,public_feedback=public,points=3))
            request = self.save(slot/'01-request.json',dict(payload={'model':t.MODEL},
                request_id='synthetic-%d'%index,reserved_nano_usd=1))
            response = self.save(slot/'01-response.json',dict(status='completed',model=t.MODEL,
                service_tier='default',output=[dict(type='message',role='assistant',
                    content=[dict(type='output_text',text=json.dumps(predictions))])]))
            rows.append(dict(cik=cik,window_config=config,window_identity=window,identity=identity,
                result=result,predictions=pred,final_request=request,final_response=response,
                score=score,public_feedback=public))
        return self.save(self.root/'comparator.json',dict(
            schema='earnings_plain_training_comparator_manifest_v1',split=self.split,rows=rows))

    def resident(self,cik):
        accession = 'invented-accession-'+cik
        company = dict(cik=cik,cutoff='2026-02-01',target_accession=accession,
            visible_root=str(self.home/'visible'/cik),allowed_files=[
                dict(path=name,sha256=digest(cik+name)) for name in ('questions.md','filing_index.tsv')])
        kernel = dict(scorer=self.scorer,qa=dict(path=str(self.home/'dataset'/cik/'benchmarks'/accession/
            'forecast_benchmark_qa.json'),sha256=digest(cik)))
        case = {k:company[k] for k in ('cik','cutoff','target_accession','visible_root')}
        case.update(evaluation_kernel=kernel,allowed_manifest_sha256=digest(company['allowed_files']))
        return dict(company=company,case=case,kernel=kernel,data_binding=self.data,runtime=self.fixed)

    def old_origin(self,*args,**kwargs):
        self.events.append('completed')
        return deepcopy(self.base)

    def get_resident(self,cik):
        self.events.append(cik)
        return deepcopy(self.residents[cik])

    def freeze(self):
        return panel.freeze_descriptor(self.origin,split_binding=self.split,
            comparator_binding=self.comparator,authority_binding=self.authority,
            root=self.root,ledger=self.root/'unused.sqlite',repo=self.repo)

    def load(self,value):
        binding = self.save(self.root/('descriptor-'+digest(value)+'.json'),value)
        return panel.load_descriptor(binding,policy=panel.POLICY,root=self.root,
            ledger=self.root/'unused.sqlite',repo=self.repo)


class FrozenPanelTests(unittest.TestCase):
    def setUp(self):
        self.f = PanelFixture()
        self.addCleanup(self.f.close)

    def test_freezes_all25_and_archived_original_members_without_mutation(self):
        before = deepcopy(self.f.base)
        value = self.f.freeze()
        self.assertEqual(value['base_origin'],before)
        self.assertEqual(self.f.base,before)
        descriptor = value['descriptor']
        self.assertEqual(set(descriptor),panel.FIELDS)
        self.assertEqual([r['company_id'] for r in descriptor['companies']],self.f.training)
        self.assertEqual(descriptor['members']['parent'],self.f.parent)
        self.assertEqual(descriptor['members']['control'],self.f.control)
        self.assertNotIn(self.f.parent['id'],self.f.state['explorers'])
        self.assertEqual(descriptor['round0']['kind'],'plain_original_forecast_comparator')
        self.assertEqual(descriptor['round0']['targets'],125)
        self.assertTrue(all(r['initial_state_template']['records']==[] for r in descriptor['companies']))
        self.assertEqual(len({r['kernel']['qa']['path'] for r in descriptor['companies']}),25)
        self.f.completed.assert_called_once_with(self.f.origin,root=self.f.root,
            ledger=self.f.root/'unused.sqlite',repo=self.f.repo)
        self.assertEqual(self.f.events[0],'completed')
        self.assertEqual(self.f.events[1:],self.f.training)

    def test_round_trip_reauthenticates_once_and_returns_original_base(self):
        value = self.f.freeze()['descriptor']
        self.f.completed.reset_mock(); self.f.resident_mock.reset_mock()
        result = self.f.load(value)
        self.assertEqual(result['descriptor'],value)
        self.assertEqual(result['base_origin'],self.f.base)
        self.f.completed.assert_called_once()
        self.assertEqual(self.f.resident_mock.call_count,25)

    def test_no_policy_legacy_is_inert_and_other_policy_states_refuse_before_read(self):
        kwargs = dict(root=self.f.root,ledger=self.f.root/'unused.sqlite',repo=self.f.repo)
        with patch.object(panel.training,'_read',side_effect=AssertionError('must not read')):
            self.assertIsNone(panel.load_descriptor(None,**kwargs))
            for policy,binding in [(None,{}),(False,{}),('',{}),('unknown',{}),(panel.POLICY,None)]:
                with self.subTest(policy=policy,binding=binding),self.assertRaises(ValueError):
                    panel.load_descriptor(binding,policy=policy,**kwargs)

    def test_exact_identity_refusal_precedes_completed_and_resident(self):
        for field in ('completed_result','split_binding','comparator_binding','authority_binding'):
            args = dict(completed_result=self.f.origin,split_binding=self.f.split,
                comparator_binding=self.f.comparator,authority_binding=self.f.authority,
                root=self.f.root,ledger=self.f.root/'unused.sqlite',repo=self.f.repo)
            args[field] = dict(path='/not/read.json',sha256='0'*64)
            with self.subTest(field=field),self.assertRaises(ValueError): panel.freeze_descriptor(**args)
        self.f.completed.assert_not_called(); self.f.resident_mock.assert_not_called()

    def test_original_completed_failure_prevents_following_source_and_task_bodies(self):
        self.f.completed.side_effect = ValueError('original admission rejected')
        with patch.object(panel,'checked',side_effect=AssertionError('source read too early')):
            with self.assertRaisesRegex(ValueError,'original admission rejected'): self.f.freeze()
        self.f.resident_mock.assert_not_called()

    def test_all25_admitted_before_first_resident(self):
        admitted = set()
        original = panel.training.admit
        def admit(scope,cik):
            result = original(scope,cik); admitted.add(cik); return result
        def resident(cik):
            self.assertEqual(admitted,set(self.f.training))
            return deepcopy(self.f.residents[cik])
        self.f.resident_mock.side_effect = resident
        with patch.object(panel.training,'admit',side_effect=admit): self.f.freeze()

    def test_company_substitution_missing_duplicate_foreign_and_order_refuse_before_origin(self):
        value = self.f.freeze()['descriptor']
        variants = []
        for cik in (self.f.heldout[0],'CIK9999999999',self.f.training[0]):
            new = deepcopy(value); new['companies'][-1]['company_id']=cik; variants.append(new)
        variants.extend([dict(value,companies=value['companies'][:-1]),
            dict(value,companies=list(reversed(value['companies'])))])
        self.f.completed.reset_mock(); self.f.resident_mock.reset_mock()
        for new in variants:
            with self.subTest(ids=[r['company_id'] for r in new['companies']]),self.assertRaises(ValueError):
                self.f.load(new)
        self.f.completed.assert_not_called(); self.f.resident_mock.assert_not_called()

    def test_descriptor_schema_extra_null_and_erased_policy_refuse(self):
        value = self.f.freeze()['descriptor']
        for key,change in [('schema','wrong'),('policy',None),('companies',None),('origin',None),('extra',1)]:
            new = deepcopy(value); new[key]=change
            with self.subTest(key=key),self.assertRaises(ValueError): self.f.load(new)
        new = deepcopy(value); del new['policy']
        with self.assertRaises(ValueError): self.f.load(new)

    def test_frozen_member_and_initial_state_or_financial_metadata_cannot_be_rebound(self):
        value = self.f.freeze()['descriptor']
        mutations = [lambda v:v['members'].__setitem__('parent',deepcopy(self.f.control)),
            lambda v:v['members']['candidate'].__setitem__('parent',self.f.control['id']),
            lambda v:v['companies'][0]['kernel'].__setitem__('qa',deepcopy(v['companies'][1]['kernel']['qa'])),
            lambda v:v['companies'][0]['initial_state_template'].__setitem__('records',[{}]),
            lambda v:v['financial_policy']['forecast_limits'].__setitem__('wall_seconds',1801),
            lambda v:v['financial_policy'].__setitem__('original_source_commit','c'*40),
            lambda v:v['origin'].__setitem__('latest_feedback',deepcopy(v['origin']['population']))]
        for i,mutate in enumerate(mutations):
            new = deepcopy(value); mutate(new)
            with self.subTest(mutation=i),self.assertRaises(ValueError): self.f.load(new)

    def test_same_size_source_tamper_with_restored_mtime_refuses(self):
        path = Path(self.f.child['R']['path']); old = path.read_bytes(); stat = path.stat()
        path.write_bytes(old.replace(b'R3',b'R9'))
        os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        with self.assertRaisesRegex(ValueError,'Bound artifact changed'): self.f.freeze()
        self.f.resident_mock.assert_not_called()

    def test_actual_comparator_final_and_award_tamper_are_not_hidden_by_old_origin_mock(self):
        manifest = panel.training._read(self.f.comparator)
        path = Path(manifest['rows'][0]['final_response']['path'])
        original = path.read_bytes(); value=json.loads(original)
        value['output'][0]['content'][0]['text']=json.dumps({'predictions':[]})
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'Bound artifact changed'): self.f.freeze()
        self.f.resident_mock.assert_not_called()

    def test_trusted_resident_cross_company_case_kernel_or_runtime_drift_refuses(self):
        cik = self.f.training[0]
        for key in ('company','case','kernel','runtime'):
            old = deepcopy(self.f.residents[cik]); new = deepcopy(old)
            if key=='runtime':new[key]['company_wall_seconds']=1801
            else:new[key]=deepcopy(self.f.residents[self.f.training[1]][key])
            self.f.residents[cik]=new
            with self.subTest(field=key),self.assertRaises(ValueError): self.f.freeze()
            self.f.residents[cik]=old

    def test_descriptor_binding_bytes_and_symlink_are_checked(self):
        value = self.f.freeze()['descriptor']
        binding = self.f.save(self.f.root/'descriptor.json',value)
        Path(binding['path']).write_bytes(Path(binding['path']).read_bytes()+b' ')
        with self.assertRaises(ValueError): panel.load_descriptor(binding,policy=panel.POLICY,
            root=self.f.root,ledger=self.f.root/'unused.sqlite',repo=self.f.repo)
        alias = self.f.root/'alias.json'; alias.symlink_to(binding['path'])
        with self.assertRaises(ValueError): panel.load_descriptor(dict(path=str(alias),sha256=binding['sha256']),
            policy=panel.POLICY,root=self.f.root,ledger=self.f.root/'unused.sqlite',repo=self.f.repo)


if __name__ == '__main__': unittest.main()
