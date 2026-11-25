"""Explicit repair-base identities, using inert original-format receipts.

No source execution, model, Docker or production ledger. Existing receipt,
assembly, role, broker and packing code is exercised; scripted transport and
case/origin seams are disclosed rather than presented as live admission.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from edgar_forecast_budget import BudgetStop
from edgar_forecast_tools import function
import earnings_open_context as packing
import earnings_open_roles as open_roles
import earnings_population_delta_author as delta
import earnings_population as pool
import earnings_population_campaign as campaign
import earnings_population_completed as completed
from earnings_population_broker import PopulationBroker
from earnings_population_diagnostics import project
import earnings_population_services as services
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_roles as transport_fixture
import test_earnings_open_researcher as receipt_fixture
import test_earnings_population_case as native_fixture
from test_earnings_population_delta_author import choice, reply


class ImplementationBaseTests(unittest.TestCase):
    def setUp(self):
        self.f = native_fixture.PopulationCaseTests(); self.f.setUp()
        self.addCleanup(self.f.doCleanups); self.root = self.f.root
        self.parent = self.f.version
        self.parent_source = Path(self.parent['R']['path']).read_text()
        self.source = "PROGRAM={'axis':'R'}\ndef run(p): return {'method':'rejected'}\n"
        self.old = dict(choice(), parent_pair_sha256=self.parent['id'])
        self.author = self.root/'rejected'/'roles'/'author-01'; self.author.mkdir(parents=True)
        self.raw = engine.save(self.author/'response.json', reply({
            'decision_sha256': digest(self.old), 'parent_source_sha256': self.parent['R']['sha256'],
            'edits': [{'kind':'replace','old_text':self.parent_source,'new_text':self.source}],
            'test_text': "CASES=[{'input':{},'expected':{'method':'rejected'}}]"}))
        self.business = delta.assemble(self.parent['R'], self.old, engine.read(self.raw))
        (self.author/'candidate.py').write_text(self.source)
        (self.author/'cases.py').write_text(self.business['test_text'])
        self.source_binding, self.tests_binding = (engine.pin(self.author/n) for n in ('candidate.py','cases.py'))
        self.projection = engine.save(self.author/'scientific-decision-projection.json', {
            'scientific_decision': self.old, 'scientific_decision_sha256': digest(self.old)})
        self.assembly = engine.save(self.author/'delta-assembly.json', {
            'schema':'earnings_population_delta_assembly_v1','axis':'R',
            'parent_version_id':self.parent['id'],'parent_source':self.parent['R'],
            'raw_patch_response':self.raw,'scientific_decision':self.projection,
            'scientific_decision_sha256':digest(self.old),'source':self.source_binding,
            'tests':self.tests_binding,'assembled_business_sha256':digest(self.business)})
        self.child = services.describe(self.source_binding, self.parent['H'], parent=self.parent['id'],
            axis='R', method='Synthetic rejected method', author='model:DeltaAuthor',
            evidence=[self.raw,self.projection,self.assembly])
        runner = receipt_fixture.ScriptedReceiptRunner(self.root/'original-code', [
            {'method':'rejected'}, {'coverage':{},'targets':[]}, {'coverage':{},'targets':[]}])
        case_execution = runner.run(self.source, {})
        self.cases = engine.save(self.root/'rejected'/'review-01-cases.json', {
            'candidate_id':self.child['id'],'results':[{'passed':True,'execution':case_execution}]})
        self.probes = []
        for stage in ('forecast','controller'):
            payload = {'stage':stage,'questions':'\n'.join(f'### T{i:03d} | Invented public question' for i in range(1,6)),
                'filing_index':'invented public index','records':[]}
            run = runner.run(self.source,payload)
            self.probes.append(engine.save(self.root/'rejected'/('review-01-'+stage+'-probe.json'), {
                'company_id':self.f.resident['company']['cik'],'input':payload,'execution':run,
                'diagnostics':project(run['value'],source_sha256=self.source_binding['sha256'],
                    execution_sha256=run['receipt']['sha256'],target_ids=[f'T{i:03d}' for i in range(1,6)])}))
        review = {'candidate_id':self.child['id'],'accepted_for_exploration':False,
            'rationale':'Synthetic quality rejection, not a score.'}
        self.outcome = engine.save(self.root/'rejected'/'review-01-outcome.json',
            dict(schema='earnings_population_exploration_review_v1',**review))
        (self.root/'rejected'/'roles'/'review-01').mkdir()
        self.review_raw = engine.save(self.root/'rejected'/'roles'/'review-01'/'response.json',reply(review))
        self.feedback = {'schema':'earnings_population_campaign_feedback_v1','kind':'review_rejected',
            'score_state':'unscored','results':[],'candidate':deepcopy(self.child),
            'company_id':self.f.resident['company']['cik'],
            'exploration_review':{'accepted_for_exploration':False,
                'evidence':[self.outcome,self.review_raw,self.cases,*self.probes]}}
        self.reference = dict(axis='R',id=self.child['id'],parent=self.parent['id'],
            source=deepcopy(self.source_binding),reference_only=True,source_delivery='paged_reference')
        self.refresh()

    def refresh(self):
        path=self.root/'rejected'/'feedback-01.json'
        path.write_text(json.dumps(self.feedback,sort_keys=True))
        self.feedback_binding = engine.pin(path)
        self.chosen = dict(choice(),parent_pair_sha256=self.parent['id'],
            feedback_sha256=digest(self.feedback_binding))

    def repin(self,binding,value):
        path=Path(binding['path']);path.write_text(json.dumps(value,sort_keys=True))
        return engine.pin(path)

    def base(self):
        return delta.implementation_base(self.chosen,self.parent,self.feedback_binding,self.reference)

    def new_patch(self, **changes):
        value = dict(decision_sha256=digest(self.chosen),
            comparison_parent_source_sha256=self.parent['R']['sha256'],
            implementation_base_source_sha256=self.source_binding['sha256'],
            edits=[{'kind':'replace','old_text':"'rejected'",'new_text':"'repaired'"}],
            test_text="CASES=[{'input':{},'expected':{'method':'repaired'}}]")
        value.update(changes); return value

    def test_exact_original_proofs_resolve_inert_base_not_active_adoption(self):
        before=deepcopy(self.feedback); base=self.base()
        self.assertEqual(base['source'],self.source_binding)
        self.assertEqual(base['comparison_parent'],{k:self.parent[k] for k in ('id','R','H')})
        self.assertFalse(base['adopted']); self.assertEqual(self.feedback,before)
        self.assertFalse(self.f.marker.exists())

    def test_small_new_delta_preview_final_and_index_use_same_base(self):
        base=self.base(); patch_value=self.new_patch(); raw=reply(patch_value)
        preview=delta.preview(self.parent['R'],self.chosen,json.dumps(patch_value['edits']),implementation_base=base)
        business=delta.assemble(self.parent['R'],self.chosen,raw,implementation_base=base)
        self.assertEqual(business['source_text'],self.source.replace("'rejected'","'repaired'"))
        self.assertEqual(preview['source_sha256'],hashlib.sha256(business['source_text'].encode()).hexdigest())
        self.assertTrue(preview['source_valid']); self.assertFalse(preview['code_executed'])
        self.assertEqual(preview['implementation_base_source_sha256'],self.source_binding['sha256'])
        self.assertNotIn('parent_source_sha256',preview)
        slot=self.root/'new-author'; slot.mkdir()
        original=engine.save(slot/'response.json',raw)
        (slot/'candidate.py').write_text(business['source_text']); (slot/'cases.py').write_text(business['test_text'])
        source,tests=(engine.pin(slot/n) for n in ('candidate.py','cases.py'))
        assembly=engine.save(slot/'delta-assembly.json',dict(schema='earnings_population_delta_assembly_v2',
            axis='R',parent_version_id=self.parent['id'],parent_source=self.parent['R'],
            comparison_parent_version_id=self.parent['id'],comparison_parent_source=self.parent['R'],
            implementation_base=base,raw_patch_response=original,source=source,tests=tests,
            scientific_decision_sha256=digest(self.chosen),assembled_business_sha256=digest(business)))
        index=delta.review_index(self.parent['R'],self.chosen,original,source,
            version_id='c'*64,assembly_binding=assembly)
        self.assertEqual(index['schema'],'earnings_population_review_index_v2')
        self.assertEqual(index['parent'],self.source_binding)
        self.assertEqual(index['comparison_parent'],self.parent['R'])
        self.assertEqual(index['implementation_base_version_id'],self.child['id'])
        self.assertEqual(index['range_basis'],'implementation_base')

    def test_v2_wrong_hash_extra_fields_and_no_source_change_refused(self):
        base=self.base()
        for changes in ({'comparison_parent_source_sha256':'f'*64},
                {'implementation_base_source_sha256':'f'*64},{'source_text':self.source},
                {'edits':[{'kind':'replace','old_text':self.source,'new_text':self.parent_source}]},
                {'edits':[{'kind':'replace','old_text':"'rejected'",'new_text':"'rejected'"}]}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                delta.assemble(self.parent['R'],self.chosen,reply(self.new_patch(**changes)),implementation_base=base)
        with self.assertRaises(ValueError):
            delta.assemble(self.parent['R'],self.chosen,reply(self.new_patch()))

    def test_noneligible_H_other_parent_legacy_and_failed_tests_stay_default(self):
        other=dict(self.chosen,parent_pair_sha256='e'*64)
        self.assertIsNone(delta.implementation_base(other,self.parent,self.feedback_binding,self.reference))
        self.assertIsNone(delta.implementation_base(dict(self.chosen,axis='H',component='tool_interface'),
            self.parent,self.feedback_binding,self.reference))
        self.feedback['candidate']['author']='model:OpenAuthor';self.refresh();self.assertIsNone(self.base())
        self.feedback['candidate']['author']='model:DeltaAuthor';self.refresh()
        cases=engine.read(self.cases);cases['results'][0]['passed']=False
        self.feedback['exploration_review']['evidence'][2]=self.repin(self.cases,cases)
        self.refresh();self.assertIsNone(self.base())

    def test_stale_feedback_or_reference_ancestry_source_axis_refused(self):
        original=deepcopy(self.chosen);self.chosen['feedback_sha256']='f'*64
        with self.assertRaises(ValueError):self.base()
        self.chosen=original
        for changes in ({'parent':'f'*64},{'source':self.parent['R']},{'axis':'H'},{'reference_only':False}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                delta.implementation_base(self.chosen,self.parent,self.feedback_binding,dict(self.reference,**changes))
        self.feedback['candidate']['H']=self.f.file('foreign-H.py',"PROGRAM={'axis':'H','tools':[]}\ndef run(p): return {}\n#other\n")
        self.refresh()
        with self.assertRaises(ValueError):self.base()

    def test_missing_modern_proof_and_tampered_review_probe_raw_refused(self):
        for label,binding in [('review',self.review_raw),('probe',self.probes[0]),('raw',self.raw)]:
            raw=Path(binding['path']).read_bytes()
            Path(binding['path']).write_bytes(raw+b' ')
            with self.subTest(label=label),self.assertRaises(ValueError):self.base()
            Path(binding['path']).write_bytes(raw)
        self.feedback['candidate']['evidence'].remove(self.assembly);self.refresh()
        with self.assertRaisesRegex(ValueError,'assembly'):self.base()

    def test_repinned_v2_provenance_cannot_silently_reconstruct_v1(self):
        assembly=engine.read(self.assembly)
        assembly.update(schema='earnings_population_delta_assembly_v2',
            comparison_parent_source=self.parent['R'],comparison_parent_version_id=self.parent['id'])
        self.feedback['candidate']['evidence'][-1]=self.repin(self.assembly,assembly);self.refresh()
        with self.assertRaisesRegex(ValueError,'v2 comparison-parent'):self.base()

    def test_preview_broker_binds_base_and_active_parent_and_refuses_drift(self):
        base=self.base()
        class Broker:
            definitions=[]
            def current_programs(inner):return {'R':{'source_sha256':self.parent['R']['sha256']}}
        wrapper=delta._PreviewBroker(Broker())
        wrapper.activate(self.parent['R'],self.chosen,implementation_base=base)
        observation=wrapper.dispatch('preview_delta_source',{'edits_json':json.dumps(self.new_patch()['edits'])})['value']
        actual=delta.assemble(self.parent['R'],self.chosen,reply(self.new_patch()),implementation_base=base)
        self.assertEqual(observation['source_sha256'],hashlib.sha256(actual['source_text'].encode()).hexdigest())
        wrapper.implementation_base['source']=self.parent['R']
        with self.assertRaisesRegex(RuntimeError,'drift'):
            wrapper.dispatch('preview_delta_source',{'edits_json':json.dumps(self.new_patch()['edits'])})

    def test_forged_case_pass_flag_cannot_replace_original_execution(self):
        cases=engine.read(self.cases);cases['results'][0]['execution']['value']={'wrong':'not stdout'}
        self.feedback['exploration_review']['evidence'][2]=self.repin(self.cases,cases)
        self.refresh()
        with self.assertRaises(ValueError):self.base()
        cases['results'][0]['execution']['value']={'method':'rejected'}
        run=cases['results'][0]['execution'];receipt=engine.read(run['receipt'])
        receipt['source_sha256']='f'*64
        cases['results'][0]['execution']['receipt']=self.repin(run['receipt'],receipt)
        self.feedback['exploration_review']['evidence'][2]=self.repin(self.cases,cases)
        self.refresh()
        with self.assertRaises(ValueError):self.base()

    def context(self,base):
        return {'schema':'earnings_population_author_context_v1','parent_version_id':self.parent['id'],
            'feedback_binding':self.feedback_binding,'feedback_sha256':digest(self.feedback_binding),
            'prior_candidate':self.reference,'implementation_base':base,
            'implementation_base_decision':self.chosen,'task':'Synthetic integration only'}

    def test_real_broker_rejects_stale_or_foreign_base_without_repointing_native(self):
        base=self.base();case=self.f.prepare();counter=0
        def broker(context):
            nonlocal counter
            counter+=1
            obj=PopulationBroker(self.root/f'broker-{counter}',company=case['company'],
                capacity=case['capacity'],runner=Mock(),literature=Mock(),trace_slots={},
                versions={self.parent['id']:self.parent})
            context.update(campaign=self.f.authority,parent_programs=obj.current_programs())
            obj.population_context_binding=engine.save(self.root/f'context-{counter}.json',context)
            return obj
        good=broker(self.context(base));value=good.research_context(include_source=True)
        self.assertEqual(value['implementation_base'],base)
        self.assertEqual(good.current_sources()['R'],self.parent_source)
        bad=self.context(dict(base,source=self.parent['R']))
        with self.assertRaises(ValueError):broker(bad).research_context(include_source=True)
        bad=self.context(base);bad['feedback_binding']=self.f.authority
        with self.assertRaises(ValueError):broker(bad).research_context(include_source=True)
        self.assertFalse(self.f.marker.exists())

    def test_original_Author_and_Services_deliver_v2_not_forged_full_source(self):
        base=self.base();t=transport_fixture.OpenRoleTests();t.setUp();self.addCleanup(t.doCleanups)
        original=t.service(author=True,max_turns=1,limits={
            'max_input_tokens':64000,'max_output_tokens':49152,'wall_seconds':1200})
        owner=services.Services.__new__(services.Services);owner.authored={};owner.native_root=self.root
        owner.runtime={'forecast_study':engine.save(self.root/'study.json',{})}
        owner.prior_feedback={'company_id':self.feedback['company_id']}
        owner.campaign_context={'feedback_binding':self.feedback_binding,'prior_candidate':self.reference,
            'campaign':self.f.authority,'original_R_evidence_abi':{'synthetic':True},
            'research_context':{'verification':'Synthetic original ABI','observations':{}},
            'failure_evidence_context':None}
        owner.case=Mock(return_value={'synthetic':'case seam is not admission proof'})
        class Broker:
            definitions=[]
            def current_programs(inner):return {'R':{'source_sha256':self.parent['R']['sha256']}}
            def research_context(inner,*,include_source=False):return engine.read(owner.author_context)
        def role(name,kind,case,slot):
            return kind(original.binding,broker=Broker(),budget=t.budget,client_factory=t.factory,max_turns=1)
        owner.role=role;t.generations=[t.message(self.new_patch())]
        state=pool.initialize(self.parent,{'K':'a'*64,'M':'b'*64,'C':'c'*64})
        before=deepcopy(state)
        with patch.object(open_roles,'budgeted_response',side_effect=t.fake_paid):
            child=owner.author(self.chosen,state,str(t.slot))
        self.assertEqual(state,before);self.assertEqual(child['parent'],self.parent['id'])
        self.assertEqual(child['H'],self.parent['H']);self.assertNotEqual(child['id'],self.child['id'])
        initial=json.loads(t.requests[0]['input'][0]['content'])
        self.assertEqual(initial['implementation_base_source_text'],self.source)
        self.assertEqual(initial['comparison_parent']['source'],self.parent['R'])
        self.assertEqual(t.requests[0]['text']['format']['name'],delta.BASE_FORMAT)
        self.assertEqual(set(t.requests[0]['text']['format']['schema']['properties']),delta.BASE_FIELDS)
        self.assertIn('implementation_base_source_sha256',t.requests[0]['instructions'])
        assembly=engine.read(engine.pin(t.slot/'delta-assembly.json'))
        self.assertEqual(assembly['schema'],'earnings_population_delta_assembly_v2')
        self.assertEqual(assembly['parent_version_id'],self.parent['id'])
        self.assertEqual(assembly['implementation_base'],base)
        self.assertEqual(engine.read(engine.pin(t.slot/'delta.json'))['delta'],self.new_patch())
        self.assertNotIn('source_text',self.new_patch());self.assertFalse(self.f.marker.exists())
        # Original completed receiver consumes this actual Services-produced v2
        # child. The Reader and old public-award seam are synthetic; this is not
        # full historical runtime/ledger/Native admission or a quality verdict.
        attempt=self.root/'completed-v2';attempt.mkdir()
        chosen_binding=engine.save(attempt/'decision.json',self.chosen)
        packet=engine.save(attempt/'packet.json',dict(population=state,feedback=self.feedback_binding,
            round_index=1,company_id=self.feedback['company_id']))
        frozen=engine.save(attempt/'frozen.json',state)
        seed=dict(population=state,feedback=self.feedback_binding,last_scored_feedback=self.f.authority)
        manifest=dict(baseline_version_id=self.parent['id'],contract={'synthetic':True})
        reviewed=dict(accepted_for_exploration=False,evidence=[self.outcome])
        measured=dict(company_id=self.feedback['company_id'],frozen=frozen,results=[])
        new_feedback=engine.save(attempt/'feedback.json',campaign.feedback(manifest,seed,self.chosen,
            child,reviewed,measured,1,chosen_binding))
        final=dict(population=state,feedback=new_feedback,latest_feedback=new_feedback,
            last_scored_feedback=seed['last_scored_feedback'])
        rows=dict(input={'packet':packet},controller={'decision':chosen_binding},
            implement={'candidate':child},source_review=reviewed,execute=measured,
            result_review={'feedback':new_feedback,'last_scored_feedback':seed['last_scored_feedback']},
            reconcile=final)
        engine.save(attempt/'population-01.json',state)
        reader=Mock();reader.read.side_effect=engine.read;reader.pin.side_effect=engine.pin
        reader.pair.side_effect=lambda p:dict(output=rows[next(s for s in completed.history.STAGES if '-'+s+'.done' in str(p))])
        with patch('earnings_population_broker.public_feedback',return_value={'synthetic_award_seam':True}):
            actual,expected=completed._rounds(reader,attempt,{'companies':[self.feedback['company_id']]},{},manifest,seed)
        self.assertEqual(actual,final)
        self.assertEqual(expected['author-01']['version'],self.parent)
        self.assertEqual(expected['review-01']['version'],child)
        self.assertNotIn(self.child['id'],actual['population']['versions'])
        self.assertEqual(actual['last_scored_feedback'],seed['last_scored_feedback'])
        # A later tested rejection can itself remain an implementation base.
        # These are inert original-format receipts, not a real model review/run.
        new_source=Path(child['R']['path']).read_text()
        runner=receipt_fixture.ScriptedReceiptRunner(self.root/'second-source-code',
            [{'method':'repaired'},{'coverage':{},'targets':[]},{'coverage':{},'targets':[]}])
        case_run=runner.run(new_source,{})
        cases=engine.save(attempt/'review-01-cases.json',dict(candidate_id=child['id'],
            results=[dict(passed=True,execution=case_run)]))
        probes=[]
        for stage in ('forecast','controller'):
            payload=deepcopy(engine.read(self.probes[0])['input']);payload['stage']=stage
            run=runner.run(new_source,payload)
            probes.append(engine.save(attempt/f'review-01-{stage}-probe.json',dict(
                company_id=self.feedback['company_id'],input=payload,execution=run,
                diagnostics=project(run['value'],source_sha256=child['R']['sha256'],
                    execution_sha256=run['receipt']['sha256'],target_ids=[f'T{i:03d}' for i in range(1,6)]))))
        review=dict(candidate_id=child['id'],accepted_for_exploration=False,rationale='Invented second quality rejection')
        outcome=engine.save(attempt/'review-01-outcome.json',dict(schema='earnings_population_exploration_review_v1',**review))
        (attempt/'roles/review-01').mkdir(parents=True)
        review_raw=engine.save(attempt/'roles/review-01/response.json',reply(review))
        next_body=campaign.feedback(manifest,seed,self.chosen,child,
            dict(accepted_for_exploration=False,evidence=[outcome,review_raw,cases,*probes]),
            measured,1,chosen_binding)
        next_binding=engine.save(attempt/'tested-feedback.json',next_body)
        next_choice=dict(self.chosen,feedback_sha256=digest(next_binding))
        reference=dict(axis='R',id=child['id'],parent=self.parent['id'],source=child['R'],
            reference_only=True,source_delivery='paged_reference')
        next_base=delta.implementation_base(next_choice,self.parent,next_binding,reference)
        self.assertEqual(next_base['source'],child['R'])
        self.assertEqual(next_base['original_assembly'],engine.pin(t.slot/'delta-assembly.json'))
        self.assertEqual(next_base['comparison_parent']['id'],self.parent['id'])
        self.assertFalse(next_base['adopted']);self.assertFalse(self.f.marker.exists())

    def test_v2_every_real_pack_fallback_and_final_snapshot_retains_full_base(self):
        base=self.base();initial=json.dumps({'implementation_base':base,
            'comparison_parent':self.parent,'implementation_base_source_text':self.source+'#public\n'*4000})
        request={'instructions':'Synthetic immutable v2','tool_choice':'none',
            'text':{'format':{'name':delta.BASE_FORMAT,'schema':{'properties':{k:{} for k in delta.BASE_FIELDS}}}},
            'input':[{'role':'user','content':initial},
                {'type':'function_call','call_id':'parent','name':'read_current_program','arguments':'{}'},
                {'type':'function_call_output','call_id':'parent','output':json.dumps({'source_text':self.parent_source})},
                {'type':'function_call','call_id':'old','name':'inspect_trace','arguments':'{}'},
                {'type':'function_call_output','call_id':'old','output':'invented output '*4000},
                {'type':'reasoning','id':'opaque-not-read'}]}
        seen=[]
        def count(endpoint,payload):
            seen.append(deepcopy(payload));return {'input_tokens':64001 if len(seen)<4 else 63000}
        directory=self.root/'packing';directory.mkdir()
        packed=packing.pack(SimpleNamespace(post=count),request,{'max_input_tokens':64000},directory,2,author_final=True)
        self.assertEqual(len(seen),4)
        for payload in seen:self.assertEqual(payload['input'][0]['content'],initial)
        self.assertEqual(json.loads(packed['input'][1]['content'])['schema'],'earnings_author_final_public_snapshot_v1')
        with self.assertRaises(BudgetStop):
            packing.pack(SimpleNamespace(post=lambda *a:{'input_tokens':64001}),request,
                {'max_input_tokens':64000},directory,3,author_final=True)

    @unittest.skipUnless(os.environ.get('RUN_ACTUAL18_IMPLEMENTATION_BASE')=='1',
                         'Root-only guarded actual18 source proof; no live execution')
    def test_actual18_readonly_source_receipt_bridge_not_full_runtime_admission(self):
        root=Path('/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/edgar-population-20261016')
        feedback=engine.pin(root/'attempts/edgar-population-20261016-18/feedback-01.json')
        body=engine.read(feedback);state=engine.read(engine.pin(root/'inputs/edgar-population-20261016-18/initial-population.json'))
        parent=state['versions'][body['candidate']['parent']]
        chosen=dict(choice(),parent_pair_sha256=parent['id'],feedback_sha256=digest(feedback))
        reference=dict(axis='R',id=body['candidate']['id'],parent=parent['id'],
            source=body['candidate']['R'],reference_only=True,source_delivery='paged_reference')
        with (patch('socket.socket',side_effect=AssertionError('No network')),
              patch('sqlite3.connect',side_effect=AssertionError('No ledger'))):
            base=delta.implementation_base(chosen,parent,feedback,reference)
        self.assertEqual(base['source']['sha256'],'466cc46f7b6e148df71038852c30213b2521ba391bf63479d2f5e7a5de9011c7')
        self.assertFalse(base['adopted'])


if __name__=='__main__':unittest.main()
