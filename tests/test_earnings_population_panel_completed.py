"""Invented P2-shaped scored receipts; no historical, Native or ledger authority.

The strict outer reader/Source/claim/clock/arm envelope is real. Expensive
training-origin admission, Native, financial and public projection boundaries
are explicit seams and are tested for refusal propagation, not replaced proof.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import earnings_population_panel_completed as receiver
from test_earnings_population_frozen_panel import PanelFixture
from supervisor_harness import capacity_feedback_engine as engine
from market_rsi import digest


class WindowFixture:
    def __init__(self):
        self.f = PanelFixture(); self.stack = self.f.stack
        f=self.f; self.ident='edgar-population-20261016-37'; self.cik=f.training[0]
        self.attempt=f.root/'attempts'/self.ident; self.inputs=f.root/'inputs'/self.ident
        self.ledger=f.root/'unused.sqlite'
        # Opaque invented kernel bytes only, never a real QA body or answer.
        resident=f.residents[self.cik]
        qa=f.source(Path(resident['kernel']['qa']['path']),'opaque invented kernel bytes')
        resident['kernel']['qa']=qa; resident['case']['evaluation_kernel']=resident['kernel']
        self.verified=f.freeze(); self.descriptor=self.verified['descriptor']
        self.descriptor_bound=f.save(f.root/'frozen-panel.json',self.descriptor)
        self.scope=receiver.panel.training.load_scope(f.split)
        self.arms=list(receiver.panel.ARMS)
        self.slots=[str(self.attempt/'roles'/('forecast-01-%02d'%i)) for i in range(3)]
        self.window=dict(schema='earnings_training25_frozen_panel_window_v1',policy=receiver.panel.POLICY,
            descriptor=self.descriptor_bound,company_id=self.cik,arms=self.arms,
            versions=[self.descriptor['members'][a]['id'] for a in self.arms],slots=self.slots)
        self.window_bound=f.save(self.inputs/'frozen-panel-window.json',self.window)
        self.study=dict(cases=[resident['case']],runtime_config=resident['runtime'],data=f.data,
            scorer=f.scorer,sole_ledger=str(self.ledger))
        self.study_bound=f.save(self.inputs/'study.json',self.study)
        self.initial=f.save(self.inputs/'initial-population.json',f.state)
        self.commit='c'*40
        self.source_bytes={name:Path(bound['path']).read_bytes() for name,bound in
            self.descriptor['financial_policy']['forecast_sources'].items()}
        run_name='tools/earnings_population_run.py'
        run_bound=f.source(f.repo/run_name,"PYTHON = {'path': '/synthetic/python', 'sha256': '"+'a'*64+"'}\n")
        self.source_bytes[run_name]=Path(run_bound['path']).read_bytes()
        self.budget_bound=f.save(f.root/'budget-grant.json',{'synthetic':'not a grant'})
        self.model_bound=f.save(f.root/'model-grant.json',{'synthetic':'not a grant'})
        self.clock=f.save(self.attempt/'clock.json',dict(source_commit=self.commit,
            cutoff_utc='2026-10-20T03:00:00Z',deadline_utc='2026-10-20T03:01:00Z'))
        f.save(self.attempt/'clock.binding.json',self.clock)
        self.runtime=dict(schema='earnings_population_runtime_v1',id=self.ident,root=str(self.attempt),
            ledger=str(self.ledger),source_commit=self.commit,forecast_study=self.study_bound,
            initial_population=self.initial,frozen_panel_policy=receiver.panel.POLICY,
            public_feedback_policy=receiver.public.POLICY,frozen_panel=self.descriptor_bound,
            frozen_panel_window=self.window_bound,training_policy=receiver.panel.training.POLICY,
            companies=[self.cik],budget_amendment=self.budget_bound,model_budget_amendment=self.model_bound,
            rates=deepcopy(self.descriptor['financial_policy']['model_rates']),
            limits={'forecast':deepcopy(self.descriptor['financial_policy']['forecast_limits'])},
            sources={**self.descriptor['financial_policy']['forecast_sources'],run_name:run_bound},
            cutoff_utc='2026-10-20T03:00:00Z',deadline_utc='2026-10-20T03:01:00Z',
            slots=dict(forecast=self.slots,**{r:[str(self.attempt/'roles'/(r+'-01'))]
                for r in ('controller','author','review')}))
        self.review=f.save(self.inputs/'runtime-review.json',dict(
            verdict='PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY',blocking_findings=[],
            source_commit=self.commit,reviewer='/independent',reviewed_configuration_sha256=digest(self.runtime)))
        self.runtime['review']=self.review
        self.runtime_bound=f.save(self.inputs/'runtime-reviewed.json',self.runtime)
        registry=self.ledger.parent/'.capacity-runtime-claims'; token=hashlib.sha256(self.ident.encode()).hexdigest()
        self.claim_path=registry/(token+'.json'); self.owner_path=registry/(token+'.result.json')
        self.claim=dict(runtime=self.runtime_bound,id=self.ident,source_commit=self.commit,retry_allowed=False)
        self.budget=dict(blocked=False,unresolved_reserved_usd=0,synthetic=True)
        self.owner=dict(status='COMPLETED_COMPONENT_CONTEXT',error_type=None,retry_allowed=False,
            runtime=self.runtime_bound,clock=self.clock,budget_summary=self.budget)
        f.save(self.claim_path,self.claim); f.save(self.owner_path,self.owner)
        self.rows=[]
        for arm,slot in zip(self.arms,self.slots):
            bound=f.save(Path(slot)/'population-public-feedback.json',dict(synthetic=True,arm=arm))
            self.rows.append(dict(arm=arm,result=dict(version_id=self.descriptor['members'][arm]['id'],
                points=3,evidence=[bound])))
        self.result=dict(schema=receiver.RESULT_SCHEMA,runtime=self.runtime_bound,
            status='COMPLETED_FROZEN_PANEL_WINDOW',retry_allowed=False,improvement_proven=False,
            result=dict(descriptor=self.descriptor_bound,window=self.window_bound,company_id=self.cik,
                results=self.rows),budget=self.budget)
        self.binding=f.save(self.attempt/'frozen-panel-window-result.json',self.result)
        for key,value in dict(OWNED=f.root,LEDGER=self.ledger,REPO=f.repo).items():
            self.stack.enter_context(patch.object(receiver.completed.bootstrap,key,value))
        self.stack.enter_context(patch.object(receiver.history,'_git',side_effect=self.git_bytes))
        self.training=self.stack.enter_context(patch.object(receiver.completed,'_training',side_effect=self.admit))
        self.stack.enter_context(patch.object(receiver.completed,'_register'))
        self.p1=self.stack.enter_context(patch.object(receiver.panel,'load_descriptor',return_value=self.verified))
        self.stack.enter_context(patch.object(receiver.runtime_module,'_panel_metadata',return_value=dict(
            descriptor=self.descriptor,window=self.window,scope=self.scope)))
        self.selection=self.stack.enter_context(patch.object(receiver.runtime_module,'panel_selection',side_effect=self.select))
        self.financial=self.stack.enter_context(patch.object(receiver.completed,'_budget',side_effect=self.budget_check))
        self.native=self.stack.enter_context(patch.object(receiver.completed,'_native',return_value=[]))
        self.cleanup=self.stack.enter_context(patch.object(receiver,'_cleanup',return_value=[]))
        self.projection=self.stack.enter_context(patch.object(receiver.public,'project',side_effect=self.project))

    def close(self): self.f.close()

    def git_bytes(self,repo,commit,name):
        if repo!=self.f.repo or commit!=self.commit: raise ValueError('Synthetic Git identity differs')
        return self.source_bytes[name]

    def admit(self,reader,runtime,study,*,preview=False,inherited=None):
        receiver.panel.training.admit(self.scope,runtime['companies'][0])
        if not preview and inherited!=self.verified['base_origin']: raise ValueError('Wrong predecessor')
        return self.scope,[]

    def select(self,runtime,slot):
        index=self.slots.index(slot); arm=self.arms[index]
        return dict(company_id=self.cik,arm=arm,window=self.window,
            version=self.descriptor['members'][arm],bindings=[])

    def budget_check(self,reader,runtime,owner,result):
        summary=owner['budget_summary']
        if summary!=result['budget'] or summary['blocked'] or summary['unresolved_reserved_usd']!=0:
            raise ValueError('Synthetic delegated accounting refusal')
        return []

    def project(self,binding,evidence,version,company,*,training_scope):
        if training_scope!=self.scope or company['cik']!=self.cik: raise ValueError('Wrong public scope')
        targets=[dict(target_id='T%03d'%i,predicted_value=i,R_advice_value=None,
            points_awarded=1 if i<=3 else 0) for i in range(1,6)]
        return {'synthetic_diagnostics':True},dict(targets=targets,version_id=version['id'])

    def rewrite(self,path,value):
        path.write_text(json.dumps(value,sort_keys=True,allow_nan=False))
        return engine.pin(path)

    def save_result(self):
        self.binding=self.rewrite(Path(self.binding['path']),self.result)

    def change_runtime(self,mutate):
        mutate(self.runtime)
        review=json.loads(Path(self.review['path']).read_bytes())
        review['reviewed_configuration_sha256']=digest({k:v for k,v in self.runtime.items() if k!='review'})
        self.review=self.rewrite(Path(self.review['path']),review); self.runtime['review']=self.review
        self.runtime_bound=self.rewrite(Path(self.runtime_bound['path']),self.runtime)
        self.claim['runtime']=self.runtime_bound; self.owner['runtime']=self.runtime_bound
        self.rewrite(self.claim_path,self.claim); self.rewrite(self.owner_path,self.owner)
        self.result['runtime']=self.runtime_bound; self.save_result()

    def load(self):
        return receiver.load_window(self.binding,root=self.f.root,ledger=self.ledger,repo=self.f.repo)


class ScoredPanelWindowTests(unittest.TestCase):
    def setUp(self):
        self.w=WindowFixture(); self.addCleanup(self.w.close)

    def test_exact_original_shaped_scored_slice_is_distinct_not_a_population_origin(self):
        value=self.w.load()
        self.assertEqual(value['schema'],receiver.SCHEMA)
        self.assertEqual([r['arm'] for r in value['outcomes']],self.w.arms)
        self.assertEqual([r['status'] for r in value['outcomes']],['SCORED']*3)
        self.assertEqual(value['coverage']['scored_leaves'],3)
        self.assertFalse(value['coverage']['full25_means_available'])
        self.assertNotIn('population',value); self.assertNotIn('previous_result',value)
        self.w.p1.assert_called_once(); self.w.financial.assert_called_once(); self.w.native.assert_called_once()
        self.assertEqual(self.w.projection.call_count,3)
        expected=self.w.native.call_args.args[4]
        self.assertEqual(set(expected),{Path(s).name for s in self.w.slots})
        self.assertTrue(all(r['role']=='forecast' for r in expected.values()))

    def test_failures_partial_duplicate_trailing_and_reordered_results_refuse(self):
        original=deepcopy(self.w.result)
        for rows in (self.w.rows[:-1],self.w.rows+[self.w.rows[0]],
                     [self.w.rows[0],self.w.rows[0],self.w.rows[2]],list(reversed(self.w.rows))):
            self.w.result=deepcopy(original); self.w.result['result']['results']=deepcopy(rows); self.w.save_result()
            with self.subTest(rows=[r['arm'] for r in rows]),self.assertRaises(ValueError): self.w.load()
        self.w.result=deepcopy(original); self.w.result['status']='FAILED_NO_RETRY'; self.w.save_result()
        with self.assertRaises(ValueError): self.w.load()
        self.w.native.assert_not_called(); self.w.projection.assert_not_called()

    def test_failure_artifact_or_fake_loop_cannot_be_completed_slice(self):
        self.w.f.save(self.w.attempt/'frozen-panel-window-failure.json',{'status':'FAILED_NO_RETRY'})
        with self.assertRaises(ValueError): self.w.load()
        self.w.p1.assert_not_called()

    def test_heldout_refuses_before_descriptor_or_resident(self):
        self.w.change_runtime(lambda v:v.__setitem__('companies',[self.w.f.heldout[0]]))
        self.w.f.resident_mock.reset_mock()
        with self.assertRaisesRegex(ValueError,'Training admission'): self.w.load()
        self.w.p1.assert_not_called(); self.w.f.resident_mock.assert_not_called()

    def test_original_predecessor_refusal_is_not_silently_replaced(self):
        self.w.p1.side_effect=ValueError('original36 rejected')
        with self.assertRaisesRegex(ValueError,'original36 rejected'): self.w.load()
        self.w.financial.assert_not_called(); self.w.native.assert_not_called()

    def test_wrong_version_source_or_slot_refuses(self):
        self.w.result['result']['results'][0]['result']['version_id']=self.w.f.child['id']; self.w.save_result()
        with self.assertRaisesRegex(ValueError,'selected version'): self.w.load()
        self.w.native.assert_not_called()

    def test_source_bytes_not_registered_original_git_bytes_refuse(self):
        self.w.source_bytes['forecaster']=b'# Changed historical bytes\n'
        with self.assertRaisesRegex(ValueError,'Historical artifact/source hash differs'): self.w.load()
        self.w.native.assert_not_called()

    def test_forecast_policy_drift_refuses(self):
        self.w.change_runtime(lambda v:v['limits']['forecast'].__setitem__('wall_seconds',1801))
        with self.assertRaisesRegex(ValueError,'forecast policy'): self.w.load()
        self.w.native.assert_not_called()

    def test_wrong_claim_owner_or_clock_refuses(self):
        self.w.owner['status']='FAILED_NO_RETRY'; self.w.rewrite(self.w.owner_path,self.w.owner)
        with self.assertRaisesRegex(ValueError,'owner/runtime/claim'): self.w.load()
        self.w.owner['status']='COMPLETED_COMPONENT_CONTEXT'; self.w.rewrite(self.w.owner_path,self.w.owner)
        clock=json.loads(Path(self.w.clock['path']).read_bytes()); clock['deadline_utc']='changed'
        new=self.w.rewrite(Path(self.w.clock['path']),clock)
        self.w.rewrite(self.w.attempt/'clock.binding.json',new)
        self.w.owner['clock']=new; self.w.rewrite(self.w.owner_path,self.w.owner)
        with self.assertRaisesRegex(ValueError,'sealed panel clock'): self.w.load()

    def test_review_rejects_same_party_or_configuration_drift(self):
        review=json.loads(Path(self.w.review['path']).read_bytes()); review['reviewer']='/root'
        self.w.review=self.w.rewrite(Path(self.w.review['path']),review)
        self.w.change_runtime(lambda v:v.__setitem__('review',self.w.review))
        with self.assertRaisesRegex(ValueError,'distinct panel'): self.w.load()

    def test_new_controller_author_review_outputs_refuse(self):
        Path(self.w.runtime['slots']['author'][0]).mkdir(parents=True)
        with self.assertRaisesRegex(ValueError,'new Controller/Author/Review'): self.w.load()

    def test_original_fee_pending_native_active_and_projection_failures_propagate(self):
        for boundary,message in ((self.w.financial,'pending liability'),(self.w.native,'active Native work'),
                                 (self.w.projection,'strict final mismatch')):
            boundary.side_effect=ValueError(message)
            with self.subTest(boundary=message),self.assertRaisesRegex(ValueError,message): self.w.load()
            if boundary is self.w.financial: boundary.side_effect=self.w.budget_check
            elif boundary is self.w.native: boundary.side_effect=None

    def test_public_awards_must_equal_original_halfpoint_leaf(self):
        def wrong(*args,**kwargs):
            diagnostics,projection=self.w.project(*args,**kwargs)
            projection['targets'][0]['points_awarded']=0
            return diagnostics,projection
        self.w.projection.side_effect=wrong
        with self.assertRaisesRegex(ValueError,'public awards'): self.w.load()


if __name__=='__main__': unittest.main()
