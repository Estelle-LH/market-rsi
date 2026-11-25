"""Immutable execution-context transfer through REAL Native proposal admission.

Only clocks/namespaces are injected. No mock of preview_proposal/propose, no
model, Docker, financial QA or candidate host execution. Case runner is inert.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import ast
import inspect
from pathlib import Path
import unittest
from unittest import mock

import earnings_candidate_transfer as transfer
import earnings_open_author_followthrough as flow
from earnings_open_capacity import ProgramCapacity
from earnings_open_source_review import ProgramSourceReview
from earnings_open_program import candidate
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
import test_earnings_open_capacity as fixture


class CandidateTransferTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.ProgramCapacityTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.root=self.f.root; self.number=0; self.now=datetime(2026,10,14,tzinfo=timezone.utc)
        old_micro=deepcopy(self.f.micro)
        old_micro['reviewer_id']=flow.REVIEWER
        old_micro['allowed_write_paths']['researcher']=['R0.py',flow.CHILD]
        self.old_batch=self.make_batch('original-batch',old_micro)
        self.old_capacity=ProgramCapacity(self.old_batch,source_root=self.f.source,
            registry_root=self.root/'original-versions',baseline=self.f.before,entrypoints=self.f.entries)
        chosen={'schema':'earnings_capacity_decision_v1','axis':'R','component':'research_policy',
            'parent_pair_sha256':digest(old_micro['pair']),'feedback_sha256':digest('invented feedback'),
            'hypothesis':'Synthetic source-specific median algorithm','expected_effect':'Synthetic literal case returns2'}
        source="PROGRAM={'axis':'R'}\nimport statistics\ndef run(p): return statistics.median(p)\n"
        authored={'decision_sha256':digest(chosen),'source_text':source,
            'test_text':"CASES=[{'input':[1,2,8],'expected':2}]"}
        decoded=candidate(authored,{'axis':'R'},chosen)
        descriptor={'parent_identity':self.f.before,'parent_entrypoints':self.f.entries,
            'parent_pair_sha256':chosen['parent_pair_sha256'],'decision_sha256':digest(chosen),
            'candidate':engine.save(self.root/'candidate-transfer-fixture.json',decoded),
            'author_original':engine.save(self.root/'author-transfer-fixture.json',authored),
            'micro_evolution':self.old_batch.snapshot()['micro_evolution']}
        class InertCases:
            blocked=False
            def run(self,text,payload):return {'value':2,'receipt':{'synthetic':True,'candidate_not_executed':True}}
        slot=str(self.root/'original-source-review')
        service=ProgramSourceReview(self.f.source,slots={slot:{'candidate_id':'reviewed-original',
            'R':flow.CHILD,'H':'H1.py'}},proposer_id='invented-original-author',reviewer_id=flow.REVIEWER,runner=InertCases())
        self.spec=service.review(chosen,authored,descriptor,slot)
        self.spec_binding=self.spec['original']; self.original_raw=Path(self.spec_binding['path']).read_bytes()
        self.old_proposal=deepcopy(self.spec['proposal'])
        self.old_capacity.preview_proposal(self.spec['after'],self.old_proposal,self.spec['entrypoints'],
            static_review=self.spec['static_review'],expected_state_sha256=self.old_batch.snapshot()['state_sha256'])
        self.old_state=self.old_batch.snapshot()
        self.scope={'author_id':'edgar-research-20261016-24','forecast_id':'synthetic-forecast27',
            'window':{'issued_utc':'2026-10-14T00:00:00Z','cutoff_utc':'2026-10-14T00:59:00Z',
                'deadline_utc':'2026-10-14T01:00:00Z'}}
        self.scope_binding=engine.save(self.root/'new-scope.json',self.scope)
        self.runtime={'id':self.scope['forecast_id'],'root':str(self.root/'never-live-root'),
            'source_commit':'c'*40,'limits':{'forecast':{'max_input_tokens':24000,'max_output_tokens':16384,'wall_seconds':600}},
            'rates':{'api_model':'gpt-6.1-sol','effort':'max'},'baseline':{'invented_original_row':4283},
            'additional_cap_nano_usd':2000,'role_efforts':{'forecast':'max'},
            **{key:self.scope['window'][key] for key in ('cutoff_utc','deadline_utc')}}
        self.runtime_binding=engine.save(self.root/'new-runtime.json',self.runtime)
        self.fixed=deepcopy(self.old_proposal['fixed_context'])
        self.fixed.update(authority_sha256=self.scope_binding['sha256'],resource_policy_sha256=digest({
            key:self.runtime[key] for key in ('limits','rates','baseline','additional_cap_nano_usd',
                'cutoff_utc','deadline_utc','role_efforts')}))
        selected={'manifest':self.f.before,'entrypoints':self.f.entries}
        selected_binding=engine.save(self.root/'versions/selected-transfer-fixture.json',selected)
        self.value={'scope':self.scope_binding,'runtime':self.runtime_binding,
            'candidate_specification':self.spec_binding,'study':engine.save(self.root/'new-study.json',{'cases':'public'}),
            'prior':{'selected':selected,'handoff':{'old_selected':selected_binding}}}
        self.assertEqual(flow.native_config(self.value)['fixed_context'],self.fixed)
        real_batch=ContinuousDiscoveryBatch
        def batch(root,**kwargs):
            return real_batch(root,allow_temporary=True,test_clock=lambda:self.now,allow_test_clock=True)
        with mock.patch.object(flow.namespace,'NATIVE_RUNTIME_ROOT',self.root/'owned-native-runtime'),\
                mock.patch.object(flow,'authority',return_value=self.scope),\
                mock.patch.object(flow,'ContinuousDiscoveryBatch',side_effect=batch):
            self.capacity=flow.native(self.value,create=True)
        self.batch=self.capacity.batch
        (self.capacity.source_root/flow.CHILD).write_bytes((self.f.source/flow.CHILD).read_bytes())
        self.sources=self.files(self.f.source); self.execution_sources=self.files(self.capacity.source_root)

    def make_batch(self,name,micro):
        batch=ContinuousDiscoveryBatch(self.root/name,allow_temporary=True,
            test_clock=lambda:self.now,allow_test_clock=True)
        batch.initialize(batch_id=name,start_utc=self.now,deadline_utc=self.now+timedelta(hours=1),
            max_attempts=9,active_pool_capacity=2,learning_checkpoint_version=1,
            initial_incumbent={'candidate_id':'fixture','candidate_sha256':self.f.before['C'],
                'scorecard_sha256':digest('score'),'review_sha256':'0'*64})
        batch.record_micro_evolution('initialize',micro,expected_state_sha256=batch.snapshot()['state_sha256'])
        return batch

    @staticmethod
    def files(root):return {str(path.relative_to(root)):path.read_bytes() for path in root.rglob('*') if path.is_file()}

    def derive(self,**changes):
        args={'scope_binding':self.scope_binding,'runtime_binding':self.runtime_binding,'fixed_context':self.fixed}
        args.update(changes); return transfer.derive(self.spec_binding,**args)

    def validate(self,binding,**changes):
        args={'specification_binding':self.spec_binding,'scope_binding':self.scope_binding,
            'runtime_binding':self.runtime_binding,'fixed_context':self.fixed}; args.update(changes)
        return transfer.validate(binding,**args)

    def admit(self,proposal,*,preview=False):
        return (self.capacity.preview_proposal if preview else self.capacity.propose)(self.spec['after'],proposal,
            self.spec['entrypoints'],static_review=self.spec['static_review'],
            expected_state_sha256=self.batch.snapshot()['state_sha256'])

    def saved(self,value):
        self.number+=1; return engine.save(self.root/f'transfer-{self.number}.json',value)

    def assert_originals(self):
        self.assertEqual(Path(self.spec_binding['path']).read_bytes(),self.original_raw)
        self.assertEqual(self.old_batch.snapshot(),self.old_state)
        self.assertEqual(self.files(self.f.source),self.sources)
        self.assertEqual(self.files(self.capacity.source_root),self.execution_sources)
        self.assertFalse(Path(self.runtime['root']).exists())

    def test_only_two_execution_hashes_change_original_proposal_and_sources_stay_exact(self):
        record=self.derive()
        self.assertEqual(set(record),{'schema','original_specification','scope','runtime','proposal'})
        self.assertEqual(record['schema'],'earnings_candidate_execution_transfer_v1')
        self.assertEqual(record['original_specification'],self.spec_binding)
        self.assertEqual(record['scope'],self.scope_binding); self.assertEqual(record['runtime'],self.runtime_binding)
        expected=deepcopy(self.old_proposal); expected['fixed_context']=self.fixed
        self.assertEqual(record['proposal'],expected)
        self.assertEqual({key for key in self.fixed if self.fixed[key]!=self.old_proposal['fixed_context'][key]},
            {'authority_sha256','resource_policy_sha256'})
        self.assertEqual(self.validate(self.saved(record)),record)
        self.assert_originals()

    def test_real_Native_rejects_old_or_one_field_stale_proposal_without_any_append(self):
        before=self.batch.snapshot(); prefix=self.files(self.batch.journal_dir); registry=self.files(self.capacity.registry)
        proposals=[self.old_proposal]
        for field in ('authority_sha256','resource_policy_sha256'):
            proposal=deepcopy(self.old_proposal); proposal['fixed_context'][field]=self.fixed[field]; proposals.append(proposal)
        for proposal in proposals:
            for preview in (True,False):
                with self.subTest(preview=preview,proposal=proposal),self.assertRaises(ValueError):self.admit(proposal,preview=preview)
                self.assertEqual(self.batch.snapshot(),before)
                self.assertEqual(self.files(self.batch.journal_dir),prefix); self.assertEqual(self.files(self.capacity.registry),registry)
        self.assert_originals()

    def test_exact_transfer_real_preview_propose_shadow_resolve_and_cold_replay(self):
        record=self.validate(self.saved(self.derive())); before=self.batch.snapshot(); prefix=self.files(self.batch.journal_dir)
        preview=self.admit(record['proposal'],preview=True)
        self.assertEqual(self.batch.snapshot(),before); self.assertEqual(self.files(self.batch.journal_dir),prefix)
        self.assertEqual(preview['projected_pending']['fixed_context'],self.fixed)
        self.admit(record['proposal']); after=self.batch.snapshot(); pending=after['micro_evolution']['pending']
        self.assertEqual(pending['fixed_context'],self.fixed)
        self.assertEqual(after['micro_evolution']['active_pair'],before['micro_evolution']['active_pair'])
        self.assertEqual(after['micro_evolution']['history'],before['micro_evolution']['history'])
        cold_batch=ContinuousDiscoveryBatch(self.batch.root,allow_temporary=True,test_clock=lambda:self.now,allow_test_clock=True)
        cold=ProgramCapacity(cold_batch,source_root=self.capacity.source_root,registry_root=self.capacity.registry,
            baseline=self.f.before,entrypoints=self.f.entries)
        self.assertEqual(cold_batch.snapshot(),after)
        selected=cold.resolve('R',expected_pair_sha256=digest(self.f.micro['pair']))
        shadow=cold.resolve('R',expected_pair_sha256=digest(self.f.micro['pair']),shadow_proposal_sha256=pending['record_sha256'])
        self.assertEqual(Path(selected['receipt']['source']['path']).name,'R0.py')
        self.assertEqual(Path(shadow['receipt']['source']['path']).name,flow.CHILD)
        self.assertFalse(shadow['receipt']['model_code_executed'])
        self.assertEqual(shadow['receipt']['source']['sha256'],engine.pin(self.f.source/flow.CHILD)['sha256'])
        self.assert_originals()

    def test_scientific_drift_or_unapproved_authority_resources_and_malformed_context_reject(self):
        values=[]
        for key in self.fixed:
            changed=deepcopy(self.fixed); changed[key]='a'*64; values.append(changed)
        for value in ('0'*64,'not-sha',True):
            changed=deepcopy(self.fixed); changed['authority_sha256']=value; values.append(changed)
        values += [{key:value for key,value in self.fixed.items() if key!='model_sha256'},dict(self.fixed,extra='a'*64)]
        before=self.batch.snapshot()
        for value in values:
            with self.subTest(context=value),self.assertRaises(ValueError):self.derive(fixed_context=value)
        self.assertEqual(self.batch.snapshot(),before); self.assert_originals()

    def test_transfer_record_lineage_or_proposal_tampering_is_rejected(self):
        original=self.derive()
        for kind in ('spec','scope','runtime','proposal','authority','resource','extra'):
            value=deepcopy(original)
            if kind in ('spec','scope','runtime'):
                key={'spec':'original_specification','scope':'scope','runtime':'runtime'}[kind]
                value[key]['sha256']='b'*64
            elif kind=='proposal':value['proposal']['parent_pair_sha256']='b'*64
            elif kind in ('authority','resource'):
                value['proposal']['fixed_context'][{'authority':'authority_sha256','resource':'resource_policy_sha256'}[kind]]='b'*64
            else:value['extra']='not an authorized transfer field'
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.validate(self.saved(value))
        self.assertIsNone(self.batch.snapshot()['micro_evolution']['pending']); self.assert_originals()

    def test_bound_specification_runtime_or_scope_drift_does_not_reopen_or_repair(self):
        record=self.saved(self.derive())
        for key,value in (('id','different-id'),('cutoff_utc','2026-10-14T00:58:00Z'),('deadline_utc','2026-10-14T00:59:59Z')):
            changed=deepcopy(self.runtime); changed[key]=value; bound=self.saved(changed)
            fixed=deepcopy(self.fixed); fixed['resource_policy_sha256']=digest({k:changed[k] for k in transfer.RESOURCE_FIELDS})
            with self.subTest(key=key),self.assertRaises(ValueError):self.derive(runtime_binding=bound,fixed_context=fixed)
        source=Path(self.spec_binding['path']); old=source.read_bytes(); source.write_bytes(old+b' ')
        try:
            with self.assertRaises(ValueError):self.validate(record)
        finally:source.write_bytes(old)
        self.assertIsNone(self.batch.snapshot()['micro_evolution']['pending']); self.assert_originals()

    def test_actual_entry_config_and_pure_preview_share_real_admitted_context(self):
        record=self.derive(); config=flow.native_config(self.value)
        self.assertEqual(config['fixed_context'],self.batch.snapshot()['micro_evolution']['fixed_context'])
        before=self.batch.snapshot(); projected=flow.preview_candidate(self.value,record)
        self.assertEqual(projected['pending']['fixed_context'],self.fixed)
        self.assertEqual(projected['pending'],self.admit(record['proposal'],preview=True)['projected_pending'])
        self.assertEqual(self.batch.snapshot(),before)
        for field in ('authority_sha256','resource_policy_sha256'):
            bad=deepcopy(record); bad['proposal']['fixed_context'][field]=self.old_proposal['fixed_context'][field]
            with self.subTest(field=field),self.assertRaises(ValueError):flow.preview_candidate(self.value,bad)
        # Supplement the real receiver test with the live entry's ordering/data
        # path, without invoking a live guard, factory, root or provider.
        tree=ast.parse(inspect.getsource(flow.run_forecast))
        calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call)]
        validation=[node for node in calls if isinstance(node.func,ast.Attribute)
            and isinstance(node.func.value,ast.Name) and node.func.value.id=='transfer' and node.func.attr=='validate']
        mkdir=[node for node in calls if isinstance(node.func,ast.Attribute)
            and isinstance(node.func.value,ast.Name) and node.func.value.id=='root' and node.func.attr=='mkdir']
        proposes=[node for node in calls if isinstance(node.func,ast.Attribute)
            and isinstance(node.func.value,ast.Name) and node.func.value.id=='capacity' and node.func.attr=='propose']
        self.assertEqual(len(validation),1); self.assertEqual(len(mkdir),1); self.assertEqual(len(proposes),1)
        self.assertLess(validation[0].lineno,mkdir[0].lineno)
        self.assertIsInstance(proposes[0].args[1],ast.Name); self.assertEqual(proposes[0].args[1].id,'proposal')
        self.assertIn("proposal=record['proposal']",inspect.getsource(flow.run_forecast))
        self.assertIn('micro=native_config(value)',inspect.getsource(flow.native))
        self.assert_originals()


if __name__=='__main__':unittest.main()
