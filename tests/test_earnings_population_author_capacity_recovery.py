"""Failed public Delta feedback, never candidate execution or live model proof.

Portable fixtures invent historical seals, budget/generation and resident data.
The explicit actual15 opt-in replays originals using read-only ledger, no network,
no code execution or QA decoding; it is not new-window runtime/model admission.
"""
from contextlib import ExitStack
from copy import deepcopy
import builtins
import hashlib
import io
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

import earnings_population_recovery as recovery
import earnings_population_campaign_context as contexts
import earnings_population_services as services
import earnings_population_tasks as tasks
import earnings_open_roles as roles
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_recovery as prefix_fixture
import test_earnings_population_recovery_author as receiving_fixture
import test_earnings_open_roles as role_fixture
import test_earnings_population_resume03_integration as admission_fixture
import test_earnings_population_run as entry_fixture
import earnings_population_run as run
import earnings_population_rejection as rejection
import earnings_population_completed as completed
import earnings_population as pool
import earnings_population_campaign as campaign
import earnings_population_campaign_admission as admission
from earnings_population_budget import AUTHORIZATION


def response(value):
    return {'status':'completed','error':None,'output':[{'type':'message','role':'assistant',
        'status':'completed','content':[{'type':'output_text','text':json.dumps(value)}]}]}


class CapacityFailureUnitTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name).resolve()
        self.marker=self.root/'MUST_NOT_EXECUTE'
        self.source='PROGRAM={"axis":"R"}\ndef run(payload):\n    raise AssertionError("DO NOT EXECUTE")\n#'+'p'*40000+'\n'
        p=self.root/'parent.py';p.write_text(self.source);self.parent=engine.pin(p)
        self.selected={'schema':'earnings_capacity_decision_v1','axis':'R','component':'research_policy',
            'parent_pair_sha256':'a'*64,'feedback_sha256':'b'*64,'hypothesis':'Synthetic capacity diagnosis.',
            'expected_effect':'earnings-shadow-v1|research_policy|input_tokens|lower|1|score_nonregression|matched_trial_only'}
        self.delta={'decision_sha256':digest(self.selected),'parent_source_sha256':self.parent['sha256'],
            'edits':[{'kind':'append','old_text':'','new_text':'\n#'+'q'*28000+'\n'}],
            'test_text':'CASES=[{"input":{},"expected":None}]'}

    def test_complete_public_append_has_exact_byte_diagnosis_without_execution(self):
        before=deepcopy(self.delta)
        public,capacity=recovery._capacity_delta(self.parent,self.selected,response(self.delta))
        self.assertEqual(public,before);self.assertEqual(self.delta,before)
        self.assertEqual(capacity['assembled_utf8_bytes'],len(self.source.encode())+len(self.delta['edits'][0]['new_text'].encode()))
        self.assertEqual(capacity['excess_utf8_bytes'],capacity['assembled_utf8_bytes']-65536)
        self.assertGreater(capacity['excess_utf8_bytes'],0);self.assertFalse(self.marker.exists())

    def test_wrong_parent_decision_fields_test_bound_or_noncompleted_reply_refused(self):
        for changes in ({'parent_source_sha256':'c'*64},{'decision_sha256':'d'*64},
                        {'test_text':'x'*32769},{'test_text':None},{'extra':'not permitted'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                recovery._capacity_delta(self.parent,self.selected,response(dict(self.delta,**changes)))
        with self.assertRaises(ValueError):
            recovery._capacity_delta(self.parent,self.selected,dict(response(self.delta),status='incomplete'))

    def test_unsupported_or_fitting_edit_is_not_silently_recovered(self):
        for edit in ({'kind':'replace','old_text':'run','new_text':'new'},
                     {'kind':'append','old_text':'old','new_text':'q'*28000},
                     {'kind':'append','old_text':'','new_text':'# fits'},
                     {'kind':'append','old_text':'','new_text':'x'*65537}):
            with self.subTest(edit=edit['kind']),self.assertRaises(ValueError):
                recovery._capacity_delta(self.parent,self.selected,response(dict(self.delta,edits=[edit])))

    def test_utf8_capacity_uses_bytes_not_character_count(self):
        delta=dict(self.delta,edits=[dict(kind='append',old_text='',new_text='λ'*15000)])
        _,capacity=recovery._capacity_delta(self.parent,self.selected,response(delta))
        self.assertEqual(capacity['append_utf8_bytes'],30000)

    def failure(self):
        return dict(schema='earnings_population_delivery_failure_v1',mode=recovery.AUTHOR_CAPACITY,
            stage='implement',score_state='unscored',public_failed_delta=deepcopy(self.delta),
            public_failed_delta_sha256=digest(self.delta),capacity={'source_limit_utf8_bytes':65536},
            original_decision_public=deepcopy(self.selected),original_scientific_decision_sha256=digest(self.selected))

    def test_controller_omits_only_bodies_while_author_original_and_hypothesis_remain_exact(self):
        context={'schema':'earnings_repair_context_v1','observations':{'prior_delivery_failure':self.failure()},
            'prior_candidate':{'reference_only':True},'human_task':'Free new scientific choice.',
            'verification':'Exact evidence','non_claims':'No quality verdict'}
        before=deepcopy(context);view=contexts.controller_view(context)
        compact=view['observations']['prior_delivery_failure']
        self.assertEqual(context,before);self.assertNotIn('public_failed_delta',compact)
        self.assertEqual(compact['original_decision_public'],self.selected)
        self.assertEqual(compact['original_scientific_decision_sha256'],digest(self.selected))
        self.assertEqual(compact['public_failed_delta_sha256'],digest(self.delta))
        self.assertEqual(compact['public_failed_delta_summary']['edits'][0]['new_text_sha256'],
            hashlib.sha256(self.delta['edits'][0]['new_text'].encode()).hexdigest())
        self.assertNotIn(self.delta['edits'][0]['new_text'],json.dumps(view))
        self.assertNotIn('read_tool',compact);self.assertTrue(compact['public_failed_delta_omitted_from_controller_view'])

    def test_planning_copy_refuses_forged_public_body_hash(self):
        failed=self.failure();failed['public_failed_delta']['edits'][0]['new_text']='tampered'
        with self.assertRaises(ValueError):contexts.controller_view({'schema':'earnings_repair_context_v1',
            'observations':{'prior_delivery_failure':failed}})


class AuthorFailurePrefixTests(unittest.TestCase):
    def fixture(self):
        f=prefix_fixture.FailedPrefixContracts();f.setUp();self.addCleanup(f.doCleanups)
        for p in f.path.glob('round-0001-source_review.*'):p.unlink()
        for suffix in ('.done.json','.done.binding.json'):
            (f.path/('round-0001-implement'+suffix)).unlink()
        f.replace(f.path/'round-0001-implement.failed.json',{
            'claim_sha256':engine.pin(f.path/'round-0001-implement.claim.json')['sha256'],
            'exception_type':'RuntimeError','retry_allowed':False})
        return f

    def test_only_two_complete_stages_and_original_implement_failure_transfer(self):
        f=self.fixture();_,outputs,_=recovery._prefix(f.reader,f.runtime,f.attempt,failed_stage='implement')
        self.assertEqual(set(outputs),{'input','controller'})

    def test_orphan_extra_stage_or_changed_failed_claim_refused(self):
        for kind in ('extra','hash','done'):
            f=self.fixture()
            if kind=='extra':f.replace(f.path/'round-0001-source_review.claim.json',{})
            elif kind=='done':f.replace(f.path/'round-0001-implement.done.json',{})
            else:f.replace(f.path/'round-0001-implement.failed.json',{'claim_sha256':'f'*64,
                'exception_type':'RuntimeError','retry_allowed':False})
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                recovery._prefix(f.reader,f.runtime,f.attempt,failed_stage='implement')


class CapacityOriginalReceivingTests(unittest.TestCase):
    def fixture(self):
        f=receiving_fixture.RecoveryAuthorDelivery();f.setUp();self.addCleanup(f.doCleanups)
        selected={'schema':'earnings_capacity_decision_v1','axis':'R','component':'research_policy',
            'parent_pair_sha256':f.version['id'],'feedback_sha256':digest(f.feedback_binding),
            'hypothesis':'Existing public capacity failure, not a forced new scientific decision.',
            'expected_effect':'Research another justified implementation.'}
        delta=dict(decision_sha256=digest(selected),parent_source_sha256=f.version['R']['sha256'],
            edits=[dict(kind='append',old_text='',new_text='# FAILED_PUBLIC_APPEND\n'+'q'*20000)],
            test_text='CASES=[{"input":{},"expected":None}]')
        f.recovery=dict(schema='earnings_population_delivery_failure_v1',mode=recovery.AUTHOR_CAPACITY,
            failed_attempt=f.public_evidence,audit=f.public_evidence,stage='implement',error_type='ValueError',
            score_state='unscored',quality_assessment='not_run',public_failed_delta=delta,
            public_failed_delta_sha256=digest(delta),capacity={'assembled_utf8_bytes':68326,
                'source_limit_utf8_bytes':65536,'excess_utf8_bytes':2790},
            original_decision=f.public_evidence,original_decision_public=selected,
            original_scientific_decision_sha256=digest(selected))
        f.origin['recovery_context']=deepcopy(f.recovery);f.refresh()
        return f

    def test_existing_services_broker_delta_author_receives_exact_failure_without_reuse(self):
        f=self.fixture()
        # Existing genuine Services/Broker/role path and counted fake HTTP, not
        # mocked Services.author or successful-stage reuse. Generations invented.
        f.test_services_author_first_physical_request_gets_exact_offline_diagnosis()
        self.assertNotIn('author_stage_reuse',f.origin)

    def test_existing_services_controller_receives_compact_failure_and_free_choice(self):
        f=self.fixture();case=f.fixture.prepare(resident=f.resident)
        owner=services.Services.__new__(services.Services)
        owner.runtime,owner.native_root=f.runtime,f.root
        owner.runner,owner.literature,owner.traces,owner.authored=Mock(),Mock(),{},{}
        owner.case=Mock(return_value=case)
        transport=role_fixture.OpenRoleTests();transport.setUp();self.addCleanup(transport.doCleanups)
        template=transport.service(max_turns=1)
        chosen=dict(transport.choice('continue'),parent_pair_sha256=f.version['id'],
                    feedback_sha256=digest(f.feedback_binding),retire_branch_id='none')
        transport.generations=[transport.message(chosen)]
        owner.contexts={'controller':(template.binding,{'budget':transport.budget,'client_factory':transport.factory})}
        with patch.object(services,'resident',return_value=deepcopy(f.resident)), \
             patch.object(roles,'budgeted_response',side_effect=transport.fake_paid):
            result=owner.controller(f.packet,str(transport.slot))
        actual=json.loads(transport.requests[0]['input'][0]['content'])
        failed=actual['research_context']['observations']['prior_delivery_failure']
        self.assertNotIn('public_failed_delta',failed)
        self.assertEqual(failed['original_decision_public'],f.recovery['original_decision_public'])
        self.assertEqual(engine.read(result)['axis'],'continue')
        self.assertNotIn('repair_assignment',actual)
        self.assertEqual(actual['feedback_binding'],f.feedback_binding)
        self.assertEqual(actual['feedback']['probes'],owner.prior_feedback['probes'])
        self.assertEqual(owner.campaign_context['research_context']['observations']['prior_delivery_failure'],f.recovery)
        self.assertFalse(f.fixture.marker.exists())


class CapacityAdmissionTests(unittest.TestCase):
    """Real receiving admission; historical loader is an explicit inert seam."""
    def fixture(self):
        f=admission_fixture.ResumeAdmission();f.setUp();self.addCleanup(f.doCleanups)
        r=f.fixture.file('second-retained-R.py',Path(f.version['R']['path']).read_text()+'\n# second explorer\n')
        retained=pool.version(r,f.version['H'],parent=f.version['id'],axis='R',
            method='Synthetic active R7 counterpart',evidence=[f.public_evidence])
        f.state=pool.retain(f.state,retained,reason='Synthetic existing explorer',evidence=[f.public_evidence])
        f.origin['population']=f.state;f.origin['reference_candidate']['parent']=retained['id']
        f.origin['recovery_context']=dict(mode=recovery.AUTHOR_CAPACITY,
            failed_attempt=f.public_evidence,failed_parent=dict(version_id=retained['id'],source=r))
        f.sources[recovery.PLAN]=admission_fixture.save(f.repo/recovery.PLAN,{
            'schema':'supervisor_bottleneck_plan_v1','id':'earnings-population-review-recovery-20261016',
            'human_authorization':AUTHORIZATION})
        f.refresh(feedback=f.origin['research_feedback'],manifest_changes={
            'comparison_policy':campaign.PARENT_COMPARISON,
            'initial_feedback_contract_sha256':f.origin['research_feedback']['campaign_contract_sha256']})
        f.study['campaign_resume']=admission_fixture.save(f.inputs/'campaign-resume.json',{
            'schema':'earnings_population_campaign_resume_v1','previous_result':f.origin['previous_result'],
            'plan':f.sources[recovery.PLAN],'repair':None,'prior_failed_attempt':f.public_evidence})
        f.stack.enter_context(patch.object(recovery,'load',side_effect=lambda *a,**k:deepcopy(f.origin)))
        return f,retained

    def test_exact_R7_reference_ancestry_does_not_force_R1_baseline_or_old_choice(self):
        f,parent=self.fixture();before=deepcopy(f.state)
        self.assertNotEqual(parent['id'],f.version['id'])
        self.assertEqual(len(admission.validate(f.value,f.study,f.state)),2)
        self.assertEqual(f.state,before);self.assertNotIn('author_stage_reuse',f.origin)

    def test_forged_failed_parent_source_or_nonactive_parent_stops_at_receiving_boundary(self):
        for mutation in ('source','parent','reuse'):
            f,_=self.fixture()
            if mutation=='source':f.origin['recovery_context']['failed_parent']['source']=f.version['R']
            elif mutation=='parent':f.origin['recovery_context']['failed_parent']['version_id']=f.state['stable_id']
            else:f.origin['author_stage_reuse']={'mode':recovery.REVIEW_REUSE}
            expected='successful Author reuse' if mutation=='reuse' else 'failed-parent/reference ancestry'
            with self.subTest(mutation=mutation),self.assertRaisesRegex(ValueError,expected):
                admission.validate(f.value,f.study,f.state)


class CapacityPhysicalRequestsTests(unittest.TestCase):
    """Synthetic saved originals + owned-ledger seam, never paid evidence."""
    def fixture(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name).resolve()
        rates=dict(api_model='gpt-6.1-sol',input='2',cached='0.5',write='2',output='10')
        limits={role:dict(max_input_tokens=100,max_output_tokens=20) for role in ('controller','author')}
        runtime=dict(root=str(root),rates=rates,limits=limits,role_efforts=dict(controller='max',author='high'))
        owned=[];rows=[]
        def save(path,value):
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,sort_keys=True));return engine.pin(path)
        for role in ('controller','author'):
            folder=root/'roles'/(role+'-01');effective={'synthetic_role':role}
            save(folder/'effective-input.json',effective)
            for turn in range(1,9):
                prefix=f'{turn:02d}';identifier=role+prefix
                payload={'model':'gpt-6.1-sol','reasoning':{'effort':runtime['role_efforts'][role]},
                    'input':[{'role':'user','content':json.dumps(effective)}]}
                wrapper=dict(payload=payload,request_id=identifier,reserved_nano_usd=260000)
                request=save(folder/(prefix+'-request.json'),wrapper)
                count=save(folder/(prefix+'-count.json'),{'input_tokens':30})
                raw={'status':'completed','error':None,'model':'gpt-6.1-sol','service_tier':'default',
                    'usage':{'input_tokens':25,'output_tokens':5,'total_tokens':30,
                             'input_tokens_details':{'cached_tokens':5}}}
                response=save(folder/(prefix+'-response.json'),dict(raw,_request_id='public-header-'+identifier))
                rawbound=save(folder/(prefix+'-generation.raw.bin'),raw)
                intent=save(folder/(prefix+'-generation.intent.json'),dict(endpoint='/v1/responses',retry_allowed=False,
                    budget_request_id=identifier,request_receipt_sha256=request['sha256'],complete_reservation=wrapper,
                    payload=dict(payload,max_output_tokens=20,service_tier='default',store=False)))
                countintent=save(folder/(prefix+'-count.intent.json'),dict(endpoint='/v1/responses/input_tokens',payload=payload))
                save(folder/(prefix+'-count.raw.bin'),{'input_tokens':30})
                owned.append(dict(request=request,request_id=identifier,status='settled',charged_nano_usd=92500))
                rows.append(dict(request=request,count=count,response=response,intent=intent,raw=rawbound,
                    conservative_charged_nano_usd=92500,matching_actual_count_origins=[countintent]))
        reader=Mock();reader.read.side_effect=engine.read;reader.pin.side_effect=engine.pin
        return runtime,owned,{'terminal_evidence':{'requests':rows}},reader,save

    def check(self,runtime,owned,audit,reader):
        with patch.object(recovery,'_owned_requests',return_value=owned):
            return recovery._capacity_requests(reader,runtime,audit)

    def test_all_sixteen_physical_counts_usage_aliases_and_charges_join(self):
        runtime,owned,audit,reader,_=self.fixture()
        self.assertEqual(len(self.check(runtime,owned,audit,reader)),16*6)

    def test_unsettled_missing_set_charge_or_count_drift_refused(self):
        for kind in ('uncertain','missing-request','charge','reserved','count','usage','missing-origin'):
            runtime,owned,audit,reader,save=self.fixture();row=audit['terminal_evidence']['requests'][-1]
            if kind=='uncertain':owned[-1]['status']='uncertain'
            elif kind=='missing-request':owned.pop()
            elif kind=='charge':owned[-1]['charged_nano_usd']+=1
            elif kind=='reserved':
                bad=engine.read(owned[-1]['request']);bad['reserved_nano_usd']+=1
                owned[-1]['request']=save(Path(owned[-1]['request']['path']),bad);row['request']=owned[-1]['request']
            elif kind=='count':row['count']=save(Path(row['count']['path']),{'input_tokens':31})
            elif kind=='usage':
                bad=engine.read(row['response']);bad['usage']['total_tokens']=99
                row['response']=save(Path(row['response']['path']),bad)
                row['raw']=save(Path(row['raw']['path']),{k:v for k,v in bad.items() if k!='_request_id'})
            else:row['matching_actual_count_origins']=[]
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.check(runtime,owned,audit,reader)

    def test_payload_model_effort_count_origin_or_finalresponse_tamper_refused(self):
        for kind in ('payload','model','effort','count-origin','response-missing','raw-mismatch'):
            runtime,owned,audit,reader,save=self.fixture();row=audit['terminal_evidence']['requests'][-1]
            if kind=='payload':
                bad=engine.read(row['intent']);bad['payload']['store']=True
                row['intent']=save(Path(row['intent']['path']),bad)
            elif kind=='effort':runtime['role_efforts']['author']='max'
            elif kind=='count-origin':
                b=row['matching_actual_count_origins'][0];bad=engine.read(b);bad['payload']['model']='foreign'
                row['matching_actual_count_origins']=[save(Path(b['path']),bad)]
            elif kind=='response-missing':Path(row['response']['path']).unlink()
            else:
                bad=engine.read(row['response']);bad['model']='foreign'
                row['response']=save(Path(row['response']['path']),bad)
                if kind=='model':row['raw']=save(Path(row['raw']['path']),{k:v for k,v in bad.items() if k!='_request_id'})
            with self.subTest(kind=kind),self.assertRaises((ValueError,FileNotFoundError)):
                self.check(runtime,owned,audit,reader)


class CapacityPreparationTests(unittest.TestCase):
    """Real prepare producer with declared synthetic origin/preflight seams."""
    def fixture(self):
        f=entry_fixture.PreparationContracts();f.setUp();self.addCleanup(f.doCleanups)
        saved=lambda name,value:entry_fixture.save(f.owned/name,value)
        stable=pool.version(saved('stable-R.py',{'synthetic':'stable'}),saved('H.py',{'synthetic':'H'}))
        state=pool.initialize(stable,{'K':'a'*64,'M':'b'*64,'C':'c'*64})
        versions=[]
        for index in (1,7):
            v=pool.version(saved(f'R{index}.py',{'synthetic':index}),stable['H'],
                parent=stable['id'],axis='R',method='Synthetic retained',evidence=[f.manifest])
            state=pool.retain(state,v,reason='Synthetic origin',evidence=[f.manifest]);versions.append(v)
        fixed,parent=versions
        original=saved('attempts/edgar-population-20261016-11/population-run-result.json',{'synthetic':True})
        failure=saved('attempts/edgar-population-20261016-15/population-run-failure.json',{'synthetic_failure':True})
        feedback=dict(schema='earnings_population_campaign_feedback_v1',campaign_contract_sha256='d'*64)
        origin=dict(population=state,previous_result=original,research_feedback=feedback,
            last_scored_feedback=saved('old-scored.json',{'synthetic_scored':True}),
            reference_candidate=dict(parent=parent['id'],source=saved('rejected-R9.py',{'reference_only':True})),
            recovery_context=dict(mode=recovery.AUTHOR_CAPACITY,failed_attempt=failure,
                failed_parent=dict(version_id=parent['id'],source=parent['R'])))
        for name in (run.RECOVERY_PLAN,run.CAMPAIGN_PLAN):
            bound=entry_fixture.save(f.repo/name,{'human_authorization':AUTHORIZATION})
            run.source_paths.return_value[name]=bound['path']
        return f,origin,failure,fixed,parent

    def test_prepare_inherits_R7_failed_parent_without_changing_R1_control_or_forcing_repair(self):
        f,origin,failure,fixed,_=self.fixture()
        with patch.object(recovery,'load',return_value=deepcopy(origin)) as loader, \
             patch.object(rejection,'PARENT',fixed['id']), \
             patch.object(admission,'scientific_contract',return_value={'synthetic_contract':True}), \
             patch.object(run,'_feedback_contract_fields',return_value={
                 'initial_feedback_contract_sha256':'d'*64}):
            bound=run.prepare('edgar-population-20261016-16',recover_from=failure['path'],company_count=1)
        value=engine.read(bound);study=engine.read(value['forecast_study'])
        manifest=engine.read(study['campaign']);resumed=engine.read(study['campaign_resume'])
        self.assertEqual(engine.read(value['initial_population']),origin['population'])
        self.assertEqual(manifest['baseline_version_id'],fixed['id']);self.assertIsNone(resumed['repair'])
        self.assertNotIn('reuse_mode',resumed);self.assertEqual(engine.read(study['campaign_origin']),origin)
        self.assertEqual(resumed['prior_failed_attempt'],failure);self.assertEqual(loader.call_count,1)

    def test_prepare_refuses_wrong_failed_parent_source_before_runtime_preflight(self):
        f,origin,failure,fixed,_=self.fixture()
        origin['recovery_context']['failed_parent']['source']=fixed['R']
        with patch.object(recovery,'load',return_value=origin),patch.object(rejection,'PARENT',fixed['id']), \
             patch.object(admission,'scientific_contract',return_value={'synthetic_contract':True}), \
             patch.object(run,'_feedback_contract_fields',return_value={}),self.assertRaisesRegex(ValueError,'ancestry'):
            run.prepare('edgar-population-20261016-16',recover_from=failure['path'],company_count=1)
        f.preflight.assert_not_called()


class CompactCapacityLessonsTests(unittest.TestCase):
    """Pure already-verified-origin metadata, not completion admission proof."""
    def failure(self):
        bound=lambda name:{'path':'/private/tmp/synthetic-replayed/'+name,'sha256':'a'*64}
        return dict(schema='earnings_population_delivery_failure_v1',mode=recovery.AUTHOR_CAPACITY,
            failed_attempt=bound('population-run-failure.json'),audit=bound('audit.json'),
            failed_parent=dict(version_id='b'*64,source=bound('parent.py')),
            original_decision=bound('population-decision.json'),original_scientific_decision_sha256='c'*64,
            raw_patch_response=bound('response.json'),public_failed_delta_sha256='d'*64,
            public_failed_delta={'edits':[{'new_text':'DO_NOT_COPY_FULL_FAILED_CODE'}],
                                 'test_text':'DO_NOT_COPY_FULL_FAILED_TESTS'},
            capacity=dict(parent_utf8_bytes=42024,append_utf8_bytes=26302,assembled_utf8_bytes=68326,
                source_limit_utf8_bytes=65536,excess_utf8_bytes=2790,test_text_utf8_bytes=11746))

    def test_new_capacity_completion_preserves_inherited_legacy_and_compacts_only_once(self):
        old=dict(schema='earnings_population_delivery_failure_v1',stage='source_review',
                 failed_attempt={'path':'/private/tmp/synthetic-older/failure.json','sha256':'e'*64},
                 probes=[{'original_public_diagnostics':True}])
        inherited={'delivery_lessons':[old],'recovery_context':self.failure()};before=deepcopy(inherited)
        lessons=completed._delivery_lessons(inherited)
        self.assertEqual(inherited,before);self.assertEqual(lessons[0],old);self.assertEqual(len(lessons),2)
        text=json.dumps(lessons);self.assertNotIn('DO_NOT_COPY',text);self.assertNotIn('public_failed_delta"',text)
        self.assertEqual(lessons[1]['capacity']['excess_utf8_bytes'],2790)
        next_origin={'delivery_lessons':lessons}
        self.assertEqual(completed._delivery_lessons(next_origin),lessons)
        self.assertEqual(completed._delivery_lessons(dict(next_origin,recovery_context=self.failure())),lessons)
        repeated=deepcopy(lessons);repeated.append(deepcopy(lessons[1]))
        self.assertEqual(completed._delivery_lessons({'delivery_lessons':repeated}),lessons)

    def test_old_reuse_and_old_ordinary_shapes_are_exactly_unchanged(self):
        legacy={'schema':'earnings_population_delivery_failure_v1','stage':'source_review',
                'probes':[{'old_full_diagnostic':True}],'failed_attempt':{'old':'legacy'}}
        self.assertEqual(completed._delivery_lessons({'author_stage_reuse':{},'recovery_context':legacy}),[legacy])
        self.assertIsNone(completed._delivery_lessons({}))
        self.assertIsNone(completed._delivery_lessons({'delivery_lessons':[legacy]}))
        self.assertIsNone(completed._delivery_lessons({'recovery_context':legacy}))

    def test_compact_shape_conflicting_duplicate_or_numeric_type_drift_refused(self):
        original=completed._delivery_lessons({'recovery_context':self.failure()})[0]
        for kind in ('extra-code','field','capacity','float','bool','hash','binding','mode','unknown','conflict'):
            item=deepcopy(original);rows=[item]
            if kind=='extra-code':item['public_failed_delta']={'edits':[]}
            elif kind=='field':item.pop('raw_patch_response')
            elif kind=='capacity':item['capacity']['excess_utf8_bytes']=2789
            elif kind=='float':item['capacity']['source_limit_utf8_bytes']=65536.0
            elif kind=='bool':item['capacity']['test_text_utf8_bytes']=True
            elif kind=='hash':item['public_failed_delta_sha256']='not-a-digest'
            elif kind=='binding':item['audit']['path']='relative.json'
            elif kind=='mode':item['mode']='invented'
            elif kind=='unknown':rows.append({'schema':'invented'})
            else:rows=[original,item];item['raw_patch_response']['sha256']='f'*64
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                completed._delivery_lessons({'delivery_lessons':rows})
        with self.assertRaises(ValueError):completed._delivery_lessons({'delivery_lessons':{},'recovery_context':self.failure()})
        with self.assertRaises(ValueError):completed._delivery_lessons({'delivery_lessons':[original]*51})


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_AUTHOR_CAPACITY15')=='1','Explicit actual15 read-only origin replay opt-in')
class ActualAuthorCapacity15(unittest.TestCase):
    def test_verified15_failure_preserves_completed11_science_and_public_originals(self):
        tempfile.gettempdir();allowed={'CIK0000003545','CIK0000004457','CIK0000017313'};qa_hashes=set();opened=[]
        original_resident=tasks.resident
        def resident(cik):
            if cik not in allowed:raise AssertionError('No held-out resident')
            v=original_resident(cik);qa_hashes.add(v['kernel']['qa']['sha256']);return v
        original_json=json.loads
        def decode(raw,*args,**kwargs):
            data=raw.encode() if isinstance(raw,str) else raw
            if isinstance(data,(bytes,bytearray)) and hashlib.sha256(data).hexdigest() in qa_hashes:
                raise AssertionError('No QA decode')
            return original_json(raw,*args,**kwargs)
        def guard(function):
            def call(path,*args,**kwargs):
                mode=kwargs.get('mode',args[0] if args else 'r')
                if isinstance(mode,str) and any(c in mode for c in 'wax+'):raise AssertionError('No writes')
                if type(mode) is int and mode&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
                    raise AssertionError('No writable descriptor')
                if not isinstance(path,int):
                    text=os.fsdecode(path)
                    if set(re.findall(r'CIK[0-9]{10}',text))-allowed:raise AssertionError('No nondev body')
                    opened.append(text)
                return function(path,*args,**kwargs)
            return call
        original_db=sqlite3.connect
        def database(path,*args,**kwargs):
            if '?mode=ro' not in str(path) or kwargs.get('uri') is not True:raise AssertionError('Read-only SQLite only')
            return original_db(path,*args,**kwargs)
        with ExitStack() as stack:
            stack.enter_context(patch.object(tasks,'resident',side_effect=resident))
            stack.enter_context(patch.object(json,'loads',side_effect=decode))
            stack.enter_context(patch.object(sqlite3,'connect',side_effect=database))
            stack.enter_context(patch.object(socket.socket,'connect',side_effect=AssertionError('No network')))
            for module in (builtins,io,os):stack.enter_context(patch.object(module,'open',guard(module.open)))
            # The prospective plan now names failed20. Replay failed15 with
            # its exact previously committed v1 plan, never the edited disk
            # plan and never by overwriting current production configuration.
            historical=recovery.history._Reader(recovery.resume.OWNED,recovery.resume.LEDGER,
                recovery.resume.REPO,'edgar-population-20261016-20')
            historical.commit='4a7b79adb6a4cff0932c922c9eaa07afa7cd7528'
            original_plan=recovery.history._git(recovery.resume.REPO,historical.commit,recovery.PLAN)
            original_binding=dict(path=str(recovery.resume.REPO/recovery.PLAN),
                sha256=hashlib.sha256(original_plan).hexdigest())
            historical.sources={(original_binding['path'],original_binding['sha256'])}
            value=recovery.load(engine.pin(recovery.resume.OWNED/'attempts/edgar-population-20261016-15/population-run-failure.json'),
                root=recovery.resume.OWNED,ledger=recovery.resume.LEDGER,repo=recovery.resume.REPO,
                plan_binding=original_binding,historical_reader=historical)
        self.assertEqual(value['previous_result']['sha256'],'f824117406c21e252c0c234a0c593f114b5e2eecf678f036b2dea124b006a96a')
        self.assertEqual(value['feedback']['sha256'],'f763d4fe26cf01e19a2c4ec1429f00d1c665e3794a9bcbd8296395f88da00097')
        self.assertEqual(value['last_scored_feedback']['sha256'],'170098840c76fd15e192b626526baede6a9d5214e762a73a27cd580f4a8a46b9')
        self.assertNotIn('author_stage_reuse',value)
        self.assertEqual(value['reference_candidate']['source']['sha256'],'b3935bed3bfcbde0f7192a06d8bcaabafafbae4b75d6b498545c93556c689b0d')
        failure=value['recovery_context'];self.assertEqual(failure['capacity']['excess_utf8_bytes'],2790)
        self.assertEqual(failure['capacity']['assembled_utf8_bytes'],68326)
        self.assertEqual(failure['public_failed_delta_sha256'],digest(failure['public_failed_delta']))
        self.assertEqual(failure['original_scientific_decision_sha256'],digest(recovery.history.e.strict_json(json.dumps({
            k:v for k,v in failure['original_decision_public'].items() if k!='retire_branch_id'}))))
        self.assertTrue(opened)


if __name__=='__main__':unittest.main()
