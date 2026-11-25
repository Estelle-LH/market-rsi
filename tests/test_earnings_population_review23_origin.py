"""Inert proof negatives; optional unmocked closed23 read-only reconstruction.

Portable cases reuse saved synthetic receipts, never execute candidate source.
The actual opt-in preserves the original loader and read-only/QA/dev guards.
"""
from contextlib import ExitStack
from copy import deepcopy
import builtins
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import earnings_population as pool
import earnings_population_review23_origin as origin
import earnings_population_delta_author as delta
import earnings_population_services as services
import earnings_population_loop as loop
import earnings_population_tasks as tasks
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness import feedback_linked_loop as driver
import test_earnings_population_implementation_base as base_fixture
from test_earnings_population_delta_author import reply


def actual_plan():
    from earnings_population_budget import AUTHORIZATION
    root = origin.resume.OWNED; attempt = root/'attempts'/origin.IDENT
    return dict(id='earnings-population-review-recovery-20261016',human_authorization=AUTHORIZATION,
        recovery_mode=origin.recovery.REVIEW_REUSE,
        failed_attempt=dict(path=str(attempt/'population-run-failure.json'),sha256=origin.FAILURE_SHA),
        closed_failure_audit=dict(path=str(root/'CUMULATIVE400-LIVE23-CLOSURE-AUDIT.json'),sha256=origin.AUDIT_SHA),
        stage_delivery_audit=dict(path=str(root/'CUMULATIVE400-LIVE23-ROLE-LINKS.json'),sha256=origin.DELIVERY_SHA),
        successful_candidate=dict(id='80d9428741890b72ab6bb91171e9a9e9118ead0e4a663ec933dd06b4495dfd40',
            source_sha256='392d7c7c3c5c1fbe3fe4245c873ef900182af503a647c4ed1db7e7ad52c1974b',
            tests_sha256='42b4dbd1f809339192073f8a6e251f76ac02c05ab3656fc0e848b45da347cf87',
            raw_patch_sha256='25ddac39acfa9507ec7e6986d66ec3610b1fcfc7b1ae530ce80c48e62ee003e5',
            assembly_sha256='dc75ea71281a70171e230eb25ee6732afe73577d0f421fde7fcc95c0832c62ed'))


class ReusedSourceTests(unittest.TestCase):
    def setUp(self):
        self.f = base_fixture.ImplementationBaseTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.attempt = self.f.root/'new'; self.folder = self.attempt/'roles/author-01'; self.folder.mkdir(parents=True)
        self.chosen = dict(self.f.chosen,retire_branch_id='none')
        self.selected = services.scientific(self.chosen)
        self.base = delta.implementation_base(self.selected,self.f.parent,self.f.feedback_binding,self.f.reference)
        raw = reply(self.f.new_patch(decision_sha256=digest(self.selected)))
        self.raw = engine.save(self.folder/'response.json',raw);engine.save(self.folder/'08-response.json',raw)
        self.business = delta.assemble(self.f.parent['R'],self.selected,raw,implementation_base=self.base)
        self.source = self.folder/'candidate.py'; self.source.write_text(self.business['source_text'])
        (self.folder/'cases.py').write_text(self.business['test_text'])
        self.source_binding, self.tests = (engine.pin(self.folder/n) for n in ('candidate.py','cases.py'))
        self.projection = engine.save(self.folder/'scientific-decision-projection.json',dict(
            population_decision=self.chosen,scientific_decision=self.selected,scientific_decision_sha256=digest(self.selected)))
        engine.save(self.folder/'delta.json',dict(delta=delta.message(raw),original=self.raw))
        self.module = dict(path='/synthetic/original-delta.py',sha256='a'*64)
        self.assembly_value = dict(schema='earnings_population_delta_assembly_v2',axis='R',
            parent_version_id=self.f.parent['id'],parent_source=self.f.parent['R'],
            comparison_parent_version_id=self.f.parent['id'],comparison_parent_source=self.f.parent['R'],
            implementation_base=self.base,raw_patch_response=self.raw,source=self.source_binding,tests=self.tests,
            scientific_decision=self.projection,scientific_decision_sha256=digest(self.selected),
            assembled_business_sha256=digest(self.business),assembly_source=dict(function='assemble',module=self.module))
        self.assembly = engine.save(self.folder/'delta-assembly.json',self.assembly_value)
        self.child = pool.version(self.source_binding,self.f.parent['H'],parent=self.f.parent['id'],axis='R',
            method=self.chosen['hypothesis'],author='model:DeltaAuthor',evidence=[self.raw,self.projection,self.assembly])
        self.state = pool.initialize(self.f.parent,{'K':'a'*64,'M':'b'*64,'C':'c'*64})
        self.reader = SimpleNamespace(read=lambda b,**kw: Path(b['path']).read_bytes() if kw.get('binary') else engine.read(b),pin=engine.pin)
        self.runtime = {'sources':{'tools/earnings_population_delta_author.py':self.module}}

    def run_authored(self):
        return origin._authored(self.reader,self.attempt,self.runtime,self.state,self.child,self.chosen)

    def test_original_v2_source_base_and_active_comparison_reconstruct_without_execution(self):
        result = self.run_authored()
        self.assertEqual(result[0],self.f.parent); self.assertEqual(result[5],self.base)
        self.assertEqual(result[6],self.business); self.assertNotIn(self.child['id'],self.state['versions'])
        self.assertFalse(self.f.f.marker.exists())

    def test_assembly_base_parent_raw_tests_source_and_projection_tampers_refuse(self):
        for key,value in [('parent_source',self.f.source_binding),('comparison_parent_source',self.f.source_binding),
                          ('raw_patch_response',self.f.raw),('tests',self.f.tests_binding),
                          ('source',self.f.source_binding),('scientific_decision_sha256','f'*64),
                          ('assembly_source',dict(function='different',module=self.module))]:
            bad=deepcopy(self.assembly_value);bad[key]=value
            (self.folder/'delta-assembly.json').write_text(json.dumps(bad))
            with self.subTest(key=key),self.assertRaises(ValueError):self.run_authored()
        (self.folder/'delta-assembly.json').write_text(json.dumps(self.assembly_value))
        self.source.write_text(self.business['source_text']+'# tampered\n')
        with self.assertRaises(ValueError):self.run_authored()

    def test_already_adopted_or_wrong_parent_or_other_axis_refuses(self):
        original=deepcopy(self.child)
        for changes in ({'parent':'f'*64},{'axis':'H'},{'H':self.f.source_binding}):
            self.child=dict(original,**changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.run_authored()
        self.child=original;self.state['versions'][self.child['id']]=self.child
        with self.assertRaises(ValueError):self.run_authored()


class ClosureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.reader=SimpleNamespace(read=engine.read,pin=engine.pin)
        self.audit={'terminal_evidence':{'roles':[]}}
        for role,value in [('author-01',dict(status='COMPLETED_CANDIDATE',error_type=None,turns=8,final_numbered_response='08-response.json',retry_allowed=False)),
                           ('review-01',dict(status='FAILED_NO_RETRY',error_type='BudgetStop',turns=7,final_numbered_response='06-response.json',retry_allowed=False))]:
            p=self.root/'roles'/role/'result.json';p.parent.mkdir(parents=True)
            b=engine.save(p,value);self.audit['terminal_evidence']['roles'].append(dict(role=role,binding=b,value=value))

    def test_no_invented_Controller_result_and_original_author_Review_statuses(self):
        value=origin._roles(self.reader,self.root,self.audit)
        self.assertEqual(set(value),{'author-01','review-01'});self.assertFalse((self.root/'roles/controller-01').exists())

    def test_missing_resealed_fake_Controller_status_and_boolturn_refuse(self):
        original=deepcopy(self.audit)
        variants=[dict(role='controller-01',binding={},value={})]
        bad=deepcopy(original);bad['terminal_evidence']['roles']+=variants
        with self.assertRaises(ValueError):origin._roles(self.reader,self.root,bad)
        bad=deepcopy(original);bad['terminal_evidence']['roles'][0]['binding']['sha256']='f'*64
        with self.assertRaises(ValueError):origin._roles(self.reader,self.root,bad)
        for key,value in [('status','COMPLETED_REVIEW'),('turns',True),('final_numbered_response','07-response.json')]:
            bad=deepcopy(original);row=bad['terminal_evidence']['roles'][1];row['value'][key]=value
            (self.root/'roles/review-01/result.json').write_text(json.dumps(row['value']))
            row['binding']=engine.pin(self.root/'roles/review-01/result.json')
            with self.subTest(key=key),self.assertRaises(ValueError):origin._roles(self.reader,self.root,bad)

    def test_early_identity_audit_source_and_authority_refuse_before_Reader(self):
        plan=actual_plan();bound=plan['failed_attempt']
        for change in ({'recovery_mode':'untyped'},{'human_authorization':'caller says yes'},
                       {'failed_attempt':dict(bound,sha256='f'*64)},
                       {'closed_failure_audit':dict(plan['closed_failure_audit'],sha256='f'*64)}):
            with (self.subTest(change=change),patch.object(origin.history,'_Reader',side_effect=AssertionError('No body read')),
                  self.assertRaises(ValueError)):
                origin.load(bound,root=origin.resume.OWNED,ledger=origin.resume.LEDGER,repo=origin.resume.REPO,plan=dict(plan,**change))

    def test_original_role_audit_has_flat_runtime_not_a_fabricated_nested_binding(self):
        bound=dict(path='/synthetic/runtime-reviewed.json',sha256='a'*64)
        value=dict(status='SEALED_FAILED_REVIEW_INPUT_CAPACITY_AFTER_GOOD_AUTHOR_NO_QUALITY_VERDICT',
            attempt_id=origin.IDENT,source_commit=origin.SOURCE,runtime=dict(bound,run_closed=True))
        self.assertTrue(origin._delivery_identity(value,bound))
        for runtime in (dict(binding=bound,run_closed=True),dict(bound,run_closed=False),dict(bound,sha256='b'*64,run_closed=True)):
            with self.subTest(runtime=runtime):self.assertFalse(origin._delivery_identity(dict(value,runtime=runtime),bound))


class ReviewPackingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.folder=self.root/'roles/review-01';self.folder.mkdir(parents=True)
        self.reader=SimpleNamespace(read=engine.read,pin=engine.pin)
        self.runtime=dict(rates={'api_model':'synthetic-model'},role_efforts={'review':'max'},limits={'review':{'max_input_tokens':1000}})
        self.effective=engine.save(self.folder/'effective-input.json',{'synthetic':'review'})
        self.last=dict(status='completed',output=[dict(type='function_call',name='read_population_program',call_id='synthetic',arguments='{}')])
        engine.save(self.folder/'06-response.json',self.last);engine.save(self.folder/'response.json',self.last)
        rows=[]
        for turn in range(1,7):
            engine.save(self.folder/f'http-gen{turn}.intent.json',dict(endpoint='/v1/responses',payload={'synthetic':turn}))
        for index in range(1,3):
            payload=dict(model='synthetic-model',reasoning={'effort':'max'},input=[dict(role='user',content=json.dumps(engine.read(self.effective)))],synthetic_projection=index)
            context=dict(schema='earnings_context_preparation_v1',generation_not_sent=True,max_input_tokens=1000,
                effective_request_sha256=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest())
            bound=engine.save(self.folder/f'07-context-{index:02d}.json',context)
            counted={'input_tokens':1000+index};count=engine.save(self.folder/f'07-context-{index:02d}-count.json',counted)
            engine.save(self.folder/f'http-count{index}.intent.json',dict(endpoint='/v1/responses/input_tokens',payload=payload))
            engine.save(self.folder/f'http-count{index}.raw.bin',counted)
            rows.append(dict(context=bound,count=count,input_tokens=1000+index,preparation=context))
        self.audit={'terminal_evidence':{'seventh_review_generation_sent':False,'review_input_failure':rows}}

    def run_stop(self):return origin._review_stop(self.reader,self.root,self.runtime,self.audit)

    def test_exact_completed_tool_alias_and_blocked_count_transports_are_not_a_verdict(self):
        self.assertEqual(self.run_stop(),[1001,1002])

    def test_changed_alias_completed_business_verdict_or_new_generation_refuses(self):
        original=(self.folder/'response.json').read_text()
        (self.folder/'response.json').write_text(json.dumps(dict(self.last,output=[])))
        with self.assertRaisesRegex(ValueError,'alias'):self.run_stop()
        (self.folder/'response.json').write_text(original)
        for name in ('07-request.json','07-response.json','review.json'):
            path=self.folder/name;path.write_text('{}')
            with self.subTest(name=name),self.assertRaises(ValueError):self.run_stop()
            path.unlink()

    def test_fitting_bool_count_model_drift_or_missing_original_count_refuses(self):
        row=self.audit['terminal_evidence']['review_input_failure'][0]
        for count in (1000,True):
            original=engine.read(row['count'])
            def read(b,**kw):return dict(input_tokens=count)if b==row['count']else engine.read(b)
            with self.subTest(count=count),patch.object(self.reader,'read',side_effect=read),self.assertRaises(ValueError):self.run_stop()
        self.runtime['role_efforts']['review']='high'
        with self.assertRaisesRegex(ValueError,'transport'):self.run_stop()


class PhysicalTranscriptTests(unittest.TestCase):
    """Invented saved provider receipts; only owned-ledger lookup is stubbed."""
    def setUp(self):
        from edgar_forecast_openai import unit
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.reader=SimpleNamespace(read=lambda b,**kw: Path(b['path']).read_bytes()if kw.get('binary')else engine.read(b),pin=engine.pin)
        self.runtime=dict(root=str(self.root),rates=dict(api_model='synthetic-model',input=1,cached=.5,write=None,output=2),
            role_efforts={'author':'high','review':'max'},limits={role:dict(max_input_tokens=1000,max_output_tokens=20)for role in ('author','review')},sources={})
        for name in ('tools/earnings_open_context.py','tools/edgar_forecast_openai.py'):
            p=self.root/Path(name).name;p.write_text('# synthetic original source\n');self.runtime['sources'][name]=engine.pin(p)
        self.audit={'checkpoints':[dict(requests=[],prepared_counts=[])]};self.owned=[]
        for role,turns in [('author',8),('review',6)]:
            folder=self.root/'roles'/(role+'-01');folder.mkdir(parents=True)
            effective=engine.save(folder/'effective-input.json',{'synthetic':role})
            source_context=engine.save(self.root/('context-'+role+'.json'),{'synthetic_context':role})
            for turn in range(1,turns+1):
                number=f'{turn:02d}';payload=dict(model='synthetic-model',reasoning={'effort':self.runtime['role_efforts'][role]},
                    input=[dict(role='user',content=json.dumps(engine.read(effective)))])
                counted=engine.save(folder/(number+'-count.json'),dict(input_tokens=100))
                request=dict(payload=payload,request_id=role+number,reserved_nano_usd=100*unit(1)+20*unit(2))
                bound=engine.save(folder/(number+'-request.json'),request)
                response=dict(status='completed',error=None,model='synthetic-model',service_tier='default',
                    usage=dict(input_tokens=90,output_tokens=2,total_tokens=92,input_tokens_details={'cached_tokens':10}),output=[])
                response_bound=engine.save(folder/(number+'-response.json'),response)
                intent=engine.save(folder/('http-gen-'+number+'.intent.json'),dict(endpoint='/v1/responses',retry_allowed=False,
                    complete_reservation=request,budget_request_id=request['request_id'],request_receipt_sha256=bound['sha256'],
                    payload=dict(payload,max_output_tokens=20,service_tier='default',store=False)))
                raw=engine.save(folder/('http-gen-'+number+'.raw.bin'),response)
                sidecar=engine.save(folder/('http-gen-'+number+'.response.json'),response)
                count_intent=engine.save(folder/('http-count-'+number+'.intent.json'),dict(endpoint='/v1/responses/input_tokens',payload=payload,retry_allowed=False))
                count_response=engine.save(folder/('http-count-'+number+'.response.json'),dict(input_tokens=100))
                count_raw=engine.save(folder/('http-count-'+number+'.raw.bin'),dict(input_tokens=100))
                preparation=engine.save(folder/(number+'-context-01.json'),dict(schema='earnings_context_preparation_v1',generation_not_sent=True,
                    effective_request_sha256=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest(),max_input_tokens=1000))
                reused=engine.save(folder/(number+'-prepared-count-reuse.json'),dict(schema='earnings_prepared_count_handoff_v1',
                    slot=str(folder),turn=turn,new_count_http_request=False,reused_original_provider_count=True,source_context=source_context,
                    producer_source=self.runtime['sources']['tools/earnings_open_context.py'],consumer_source=self.runtime['sources']['tools/edgar_forecast_openai.py'],
                    request_sha256=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest(),
                    provider_count_intent=count_intent,provider_count_response=count_response,provider_count_raw=count_raw,
                    count_receipt=counted,context_receipt=preparation))
                marker_value=dict(schema='earnings_prepared_count_consumed_v1',phase='consumed_before_validation_and_reservation')
                marker=engine.save(folder/(number+'-prepared-count-consumed.json'),marker_value)
                charge=80*unit(1)+10*unit(.5)+2*unit(2)
                self.owned.append(dict(request=bound,request_id=request['request_id'],status='settled',charged_nano_usd=charge))
                self.audit['checkpoints'][0]['requests'].append(dict(binding=bound,role=folder.name,number=number,
                    usage={'expected_conservative_charge_nano_usd':charge},physical=dict(failure=None,intent=intent,raw=raw,numbered_response=response_bound,sidecar=sidecar)))
                self.audit['checkpoints'][0]['prepared_counts'].append(dict(role=folder.name,number=number,reuse_binding=reused,
                    actual_generation_request=bound,actual_generation_completed=True,consumed_marker=dict(binding=marker,value=marker_value)))

    def run_physical(self, audit=None, owned=None):
        with patch.object(origin,'_owned_requests',return_value=self.owned if owned is None else owned):
            return origin._physical(self.reader,self.runtime,self.audit if audit is None else audit)

    def test_exact14_original_generations_no_Controller_or_synthetic_HTTP_send(self):
        self.assertEqual(len(self.run_physical()),70)
        self.assertFalse((self.root/'roles/controller-01').exists())
        row=self.audit['checkpoints'][0]['requests'][0]
        self.assertNotEqual(row['physical']['sidecar']['path'],row['physical']['numbered_response']['path'])
        self.assertEqual(row['physical']['sidecar']['sha256'],row['physical']['numbered_response']['sha256'])

    def test_missing_extra_unsettled_wrong_charge_or_reservation_refuses(self):
        for kind in ('missing','extra','unsettled','charge'):
            own=deepcopy(self.owned)
            if kind=='missing':own.pop()
            elif kind=='extra':own.append(own[0])
            elif kind=='unsettled':own[0]['status']='uncertain'
            else:own[0]['charged_nano_usd']+=1
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.run_physical(owned=own)

    def test_physical_and_prepared_provenance_tamper_refuses_before_return(self):
        # A Reader overlay supplies altered decoded JSON at an unchanged bound
        # path, so these tests target semantic checks beyond byte hashing.
        final=self.audit['checkpoints'][0];row=final['requests'][0];prep=final['prepared_counts'][0]
        mutations=[(row['physical']['intent'],lambda v:v['payload'].update(reasoning={'effort':'low'})),
                   (row['physical']['raw'],lambda v:v.update(status='incomplete')),
                   (prep['reuse_binding'],lambda v:v.update(turn=True)),
                   (prep['reuse_binding'],lambda v:v.update(new_count_http_request=True)),
                   (prep['consumed_marker']['binding'],lambda v:v.update(phase='not_consumed'))]
        for bound,mutate in mutations:
            value=deepcopy(engine.read(bound));mutate(value)
            def read(b,**kw):return deepcopy(value)if b==bound else engine.read(b)
            with self.subTest(binding=bound['path']),patch.object(self.reader,'read',side_effect=read),self.assertRaises(ValueError):self.run_physical()

    def test_sidecar_must_be_the_actual_HTTP_sibling_not_a_same_content_numbered_alias(self):
        bad=deepcopy(self.audit);row=bad['checkpoints'][0]['requests'][0]
        row['physical']['sidecar']=deepcopy(row['physical']['numbered_response'])
        with self.assertRaises(ValueError):self.run_physical(audit=bad)


class V2ReceivingTests(unittest.TestCase):
    """Real Services/driver reuse, synthetic admission/review/scores only."""
    def setUp(self):
        self.f=ReusedSourceTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.f.root/'prospective';self.root.mkdir()
        original=dict(self.f.chosen,retire_branch_id=None)
        decision=engine.save(self.root/'original-decision.json',original)
        failed=engine.save(self.root/'old-failure.json',{'synthetic_closed':True})
        imported=engine.save(self.root/'original-controller-import.json',{'new_model_called':False,'synthetic':True})
        self.bundle=dict(schema='earnings_population_author_stage_reuse_v1',mode=origin.recovery.REVIEW_REUSE,
            candidate=self.f.child,decision=decision,scientific_decision=self.f.selected,
            raw_patch_response=self.f.raw,assembly=self.f.assembly,tests=self.f.tests,source=self.f.source_binding,
            parent_source=self.f.f.parent['R'],implementation_base=self.f.base,original_controller_import=imported,
            failed_attempt=failed,cases={},probes=[],new_model_Controller_called=False,new_model_Author_called=False)
        self.saved_origin=engine.save(self.root/'origin.json',{'author_stage_reuse':self.bundle})
        resumed=engine.save(self.root/'resume.json',{'reuse_mode':origin.recovery.REVIEW_REUSE})
        study=engine.save(self.root/'study.json',{'campaign_origin':self.saved_origin,'campaign_resume':resumed})
        self.owner=services.Services.__new__(services.Services)
        self.owner.root=self.root/'run';self.owner.native_root=self.root/'native';self.owner.native_root.mkdir()
        self.owner.runtime={'forecast_study':study,'companies':['synthetic-unexposed']}
        self.owner.authored={};self.owner.pending=[];self.owner.traces={}
        self.owner.case=Mock(return_value={'state_api':SimpleNamespace(tools=SimpleNamespace(files={'questions.md':'Synthetic questions'}))})
        broker=Mock();broker.current_sources.return_value={axis:Path(self.f.f.parent[axis]['path']).read_text()for axis in ('R','H')}
        broker.references.return_value={};broker.available_traces.return_value={}
        self.role=Mock(broker=broker);self.role.propose.side_effect=AssertionError('No new C model')
        self.role.author.side_effect=AssertionError('No new A model');self.owner.role=Mock(return_value=self.role)
        self.context=dict(origin=self.saved_origin,campaign={},original_R_evidence_abi={'synthetic':True},
            feedback_binding=self.f.raw,prior_candidate={'reference_only':True},
            research_context={'schema':'earnings_repair_context_v1','verification':'Synthetic ABI','observations':{}})

    def drive(self):
        self.reviewed=[];self.forecasted=[]
        def review(child,state,slot):
            self.reviewed.append(deepcopy(self.owner.authored[child['id']]))
            return dict(accepted_for_exploration=True,evidence=[self.f.assembly])
        def forecast(version,company,slot):
            self.forecasted.append(version['id']);return dict(version_id=version['id'],points=1,evidence=[self.f.assembly])
        with (patch.object(services,'public_feedback',return_value={'synthetic_unscored':True}),
              patch('earnings_population_campaign_context.prepare',return_value=deepcopy(self.context)),
              patch.object(services,'implementation_base',side_effect=AssertionError('No fresh feedback/reference base selection on explicit reuse'))):
            result=loop.run(self.owner.root,self.f.state,['synthetic-unexposed'],dict(controller=self.owner.controller,
                author=self.owner.author,review=review,forecast=forecast),admit=lambda ctx:True,max_rounds=1,
                identity=lambda:{stage:{'synthetic':stage}for stage in driver.STAGES})
        rows={stage:engine.read(engine.pin(self.owner.root/'loop'/f'round-0001-{stage}.done.json'))['output']for stage in driver.STAGES}
        return result,rows

    def test_explicit_v2_reuse_does_not_reselect_current_feedback_reference_base_or_call_C_A(self):
        result,rows=self.drive();self.assertEqual(result['status'],'completed')
        self.role.propose.assert_not_called();self.role.author.assert_not_called()
        self.assertEqual(self.reviewed[0]['source'],self.f.business['source_text'])
        self.assertEqual(self.reviewed[0]['decision'],self.f.selected)
        self.assertEqual(self.forecasted,[self.f.f.parent['id'],self.f.child['id']])
        receipt=engine.read(rows['implement']['stage_reuse'])
        self.assertEqual(receipt['implementation_base'],self.f.base)
        self.assertEqual(receipt['original_controller_import'],self.bundle['original_controller_import'])
        origin.recovery.verify_reused_stages(self.f.reader,self.owner.root,rows,{'author_stage_reuse':self.bundle})
        self.assertEqual(rows['controller']['artifacts'],[rows['controller']['decision'],rows['controller']['stage_reuse']])
        self.assertEqual(rows['implement']['artifacts'],[rows['implement']['stage_reuse']])

    def test_v2_replay_refuses_missing_or_changed_durable_C_A_receipts(self):
        _,rows=self.drive()
        for stage in ('controller','implement'):
            for key in ('stage_reuse','artifacts'):
                bad=deepcopy(rows);bad[stage].pop(key)
                with self.subTest(stage=stage,key=key),self.assertRaisesRegex(ValueError,'durable'):
                    origin.recovery.verify_reused_stages(self.f.reader,self.owner.root,bad,{'author_stage_reuse':self.bundle})


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_REVIEW23_ORIGIN')=='1','Root-only original closed23→22→21→20→18 read-only proof')
class ActualReview23Origin(unittest.TestCase):
    def test_original_good_Author23_and_imported22_are_not_new_model_calls_or_adoption(self):
        tempfile.gettempdir();allowed={'CIK0000003545','CIK0000004457','CIK0000017313'};qa=set()
        resident=tasks.resident;decode=json.loads;database=sqlite3.connect
        def dev(cik):
            if cik not in allowed:raise AssertionError('No held-out resident')
            result=resident(cik);qa.add(result['kernel']['qa']['sha256']);return result
        def public(raw,*a,**kw):
            b=raw.encode()if isinstance(raw,str)else raw
            if isinstance(b,(bytes,bytearray))and hashlib.sha256(b).hexdigest()in qa:raise AssertionError('No QA decode')
            return decode(raw,*a,**kw)
        def readonly(function):
            def guarded(path,*a,**kw):
                mode=kw.get('mode',a[0]if a else'r')
                if type(mode)is str and any(c in mode for c in 'wax+'):raise AssertionError('No writes')
                if type(mode)is int and mode&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):raise AssertionError('No writable fd')
                if not isinstance(path,int)and set(__import__('re').findall(r'CIK[0-9]{10}',os.fsdecode(path)))-allowed:raise AssertionError('No nondev')
                return function(path,*a,**kw)
            return guarded
        def ro_db(path,*a,**kw):
            if '?mode=ro'not in str(path)or kw.get('uri')is not True:raise AssertionError('Read-only SQLite')
            return database(path,*a,**kw)
        with ExitStack()as stack:
            stack.enter_context(patch.object(tasks,'resident',side_effect=dev));stack.enter_context(patch.object(json,'loads',side_effect=public))
            stack.enter_context(patch.object(sqlite3,'connect',side_effect=ro_db));stack.enter_context(patch.object(socket.socket,'connect',side_effect=AssertionError('No network')))
            for module in (builtins,io,os):stack.enter_context(patch.object(module,'open',readonly(module.open)))
            plan=actual_plan()
            with origin.history.validation_epoch():
                value=origin.load(plan['failed_attempt'],root=origin.resume.OWNED,ledger=origin.resume.LEDGER,repo=origin.resume.REPO,plan=plan)
        self.assertNotIn('controller_stage_import',value)
        bundle=value['author_stage_reuse'];self.assertFalse(bundle['new_model_Controller_called']);self.assertFalse(bundle['new_model_Author_called'])
        self.assertEqual(bundle['source']['sha256'],plan['successful_candidate']['source_sha256'])
        self.assertEqual(bundle['implementation_base']['source']['sha256'],'466cc46f7b6e148df71038852c30213b2521ba391bf63479d2f5e7a5de9011c7')
        self.assertEqual(bundle['parent_source']['sha256'],'631f8e214c01b476b6ae66e72baaaeb929bc2f827d77e7685362d450b518a026')
        self.assertNotIn(bundle['candidate']['id'],value['population']['versions'])
        self.assertEqual(value['feedback']['sha256'],'238ca35f5c9a9644b5960e376ec7b14436895eeec1ae73910fea8a557aef6544')
        self.assertEqual(value['last_scored_feedback']['sha256'],'170098840c76fd15e192b626526baede6a9d5214e762a73a27cd580f4a8a46b9')
        self.assertEqual(value['recovery_context']['observed_input_tokens'],[24136,22843,20947,20131])
        self.assertEqual(value['recovery_context']['review_assessment'],'not_completed')


if __name__=='__main__':unittest.main()
