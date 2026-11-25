"""Input-delivery overlay, not a new Delta, model trial or accounting write.

Fast fixtures save invented original-format counts and use a synthetic Reader.
Services/packing reuse real receivers with scripted provider replies. Only the
explicit actual21 opt-in replays original history, guarded read-only/no QA.
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
import earnings_population_completed as completed
import earnings_population_campaign_context as contexts
import earnings_population_run as run
import earnings_population_tasks as tasks
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_base_capacity_recovery as base_tests
import test_earnings_population_author_capacity_recovery as old


class InputCapacityProofTests(unittest.TestCase):
    def fixture(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name).resolve();author=root/'roles/author-01';author.mkdir(parents=True)
        saved=lambda p,v:engine.save(p,v)
        user={'public_repair':'Original20 patch remains exact','valid_base':'inert source'}
        runtime=dict(limits={'author':{'max_input_tokens':64000}},rates={'api_model':'gpt-6.1-sol'},role_efforts={'author':'high'})
        result=dict(status='FAILED_NO_RETRY',error_type='BudgetStop',turns=3,final_numbered_response='02-response.json')
        saved(root/'context-author.json',{'historical_limit':64000})
        for turn in (1,2):saved(author/f'http-gen{turn}.intent.json',{'endpoint':'/v1/responses'})
        rows=[];counts=[]
        for step,tokens in ((1,66307),(4,67013)):
            payload=dict(model='gpt-6.1-sol',reasoning={'effort':'high'},input=[{'role':'user','content':json.dumps(user)}],
                         tool_choice='auto'if step==1 else'none')
            encoded=json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()
            context=dict(schema='earnings_context_preparation_v1',generation_not_sent=True,
                max_input_tokens=64000,effective_request_sha256=hashlib.sha256(encoded).hexdigest(),preview_bytes=None if step==1 else 100)
            count={'input_tokens':tokens,'_request_id':f'synthetic-{step}'}
            prefix=author/f'03-context-{step:02d}'
            cb=saved(prefix.with_suffix('.json'),context);tb=saved(author/(prefix.name+'-count.json'),count)
            hp=author/f'http-count{step}.intent.json';saved(hp,dict(endpoint='/v1/responses/input_tokens',retry_allowed=False,payload=payload))
            saved(hp.with_name(hp.name.replace('.intent.json','.raw.bin')),{'input_tokens':tokens})
            saved(hp.with_name(hp.name.replace('.intent.json','.response.json')),count)
            rows.append({'binding':cb,'value':context});counts.append({'binding':tb,'input_tokens':tokens})
        delivery={'author_terminal':{'failed_turn03_contexts':rows,'failed_turn03_counts':counts}}
        reader=Mock();reader.read.side_effect=lambda b,**k:engine.read(b);reader.pin.side_effect=engine.pin
        return root,author,runtime,result,user,delivery,reader

    def check(self,fixture):
        root,_,runtime,result,user,delivery,reader=fixture
        return recovery._input_capacity_diagnosis(reader,root,runtime,result,user,delivery=delivery)

    def test_original67013_count_is_blocked_pre_generation_not_a_failed_Delta(self):
        value=self.check(self.fixture())
        self.assertEqual(value['blocked_turn'],3);self.assertEqual(value['completed_generations'],2)
        self.assertEqual(value['input_limit'],64000);self.assertEqual(value['observed_input_tokens'],[66307,67013])
        self.assertFalse(value['candidate_created']);self.assertEqual(value['quality_assessment'],'not_run')
        self.assertNotIn('public_failed_delta',value)

    def test_count_source_payload_turn_or_generation_forgery_refused(self):
        for kind in ('fitting','bool-limit','changed-user','turn','generation-file','generation-intent','missing-view','hash'):
            f=self.fixture();root,author,runtime,result,user,delivery,_=f
            if kind=='fitting':
                path=Path(delivery['author_terminal']['failed_turn03_counts'][0]['binding']['path'])
                path.write_text(json.dumps({'input_tokens':64000}));delivery['author_terminal']['failed_turn03_counts'][0]['binding']=engine.pin(path)
            elif kind=='bool-limit':runtime['limits']['author']['max_input_tokens']=True
            elif kind=='changed-user':user['public_repair']='wrong repair'
            elif kind=='turn':result['turns']=2
            elif kind=='generation-file':engine.save(author/'03-request.json',{'forbidden':True})
            elif kind=='generation-intent':engine.save(author/'http-gen3.intent.json',{'endpoint':'/v1/responses'})
            elif kind=='missing-view':delivery['author_terminal']['failed_turn03_contexts'].pop()
            else:Path(delivery['author_terminal']['failed_turn03_contexts'][0]['binding']['path']).write_text('{}')
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.check(f)


class InputOverlayReceivingTests(unittest.TestCase):
    def fixture(self):
        f=base_tests.BaseCapacityFeedbackTests();f.setUp();self.addCleanup(f.doCleanups)
        inherited=dict(recovery_context=f.failure(),delivery_lessons=[],population={'unchanged':'pool'},
            previous_result=f.f.f.authority,research_feedback={'unchanged':'latest18'},last_scored_feedback=f.f.f.authority)
        bound=engine.save(f.f.root/'failed21.json',{'synthetic21':True})
        diagnosis=dict(schema='earnings_population_input_delivery_diagnosis_v1',mode=recovery.AUTHOR_INPUT_CAPACITY,
            failed_attempt=bound,audit=f.f.f.authority,original_decision=f.f.f.authority,
            original_scientific_decision_sha256='a'*64,source_context=f.f.f.authority,
            blocked_turn=3,completed_generations=2,input_limit=64000,observed_input_tokens=[66307,67013])
        return f,inherited,diagnosis

    def test_latestproducer21_not20_and_later_source22_does_not_keep_stale_pointer(self):
        f,origin,diagnosis=self.fixture();before=deepcopy(origin)
        result=recovery._attach_input_capacity(origin,diagnosis)
        self.assertEqual(origin,before);self.assertEqual(recovery.latest_failed_attempt(result),diagnosis['failed_attempt'])
        self.assertEqual(result['recovery_context']['public_failed_delta'],origin['recovery_context']['public_failed_delta'])
        self.assertEqual(result['recovery_context']['failed_attempt'],origin['recovery_context']['failed_attempt'])
        next_failure=f.failure();next_failure['failed_attempt']=engine.save(f.f.root/'failed22.json',{'synthetic22':True})
        next_origin=recovery._attach_capacity_failure(result,next_failure)
        self.assertEqual(recovery.latest_failed_attempt(next_origin),next_failure['failed_attempt'])
        self.assertEqual({r['failed_attempt']['path']for r in next_origin['delivery_lessons']},
            {origin['recovery_context']['failed_attempt']['path'],diagnosis['failed_attempt']['path']})
        self.assertNotIn('FAILED_V2_PUBLIC',json.dumps(next_origin['delivery_lessons']))
        self.assertEqual(next_origin['research_feedback'],origin['research_feedback'])

    def test_original_C_and_A_receivers_keep_numeric21_and_exact20patch(self):
        f,origin,diagnosis=self.fixture();result=recovery._attach_input_capacity(origin,diagnosis)
        full=result['recovery_context']
        view=contexts.controller_view(dict(schema='earnings_repair_context_v1',observations={'prior_delivery_failure':full}))
        projected=view['observations']['prior_delivery_failure']
        self.assertEqual(projected['input_delivery_diagnosis'],diagnosis);self.assertNotIn('public_failed_delta',projected)
        # Reuse the actual Services→DeltaAuthor→original packing receiver test,
        # changing only its previously verified public failure fixture.
        f.failure=lambda:deepcopy(full)
        f.test_original_services_DeltaAuthor_receiver_gets_exact_failure_and_one_valid_inline_base()

    def test_real_prepare_binds_newest21_while_current_source_repair_stays20(self):
        original=old.CapacityPreparationTests();f,origin,_,fixed,parent=original.fixture();self.addCleanup(original.doCleanups)
        failed21=old.entry_fixture.save(f.owned/'attempts/edgar-population-20261016-21/population-run-failure.json',{'input_stop':True})
        origin['recovery_context']['input_delivery_diagnosis']={'mode':recovery.AUTHOR_INPUT_CAPACITY,'failed_attempt':failed21}
        with patch.object(recovery,'load',return_value=deepcopy(origin)),patch.object(old.rejection,'PARENT',fixed['id']), \
             patch.object(old.admission,'scientific_contract',return_value={'synthetic_contract':True}), \
             patch.object(run,'_feedback_contract_fields',return_value={'initial_feedback_contract_sha256':'d'*64}):
            value=engine.read(run.prepare('edgar-population-20261016-22',recover_from=failed21['path'],company_count=1))
        study=engine.read(value['forecast_study']);resumed=engine.read(study['campaign_resume'])
        self.assertEqual(resumed['prior_failed_attempt'],failed21)
        self.assertEqual(engine.read(study['campaign_origin']),origin)
        self.assertIsNone(resumed['repair']);self.assertNotIn('reuse_mode',resumed)

    def test_compact_input_lesson_rejects_fake_score_code_or_fitting_count(self):
        _,origin,diagnosis=self.fixture();result=recovery._attach_input_capacity(origin,diagnosis)
        lessons=completed._delivery_lessons(result);item=[x for x in lessons if x['mode']==recovery.AUTHOR_INPUT_CAPACITY][0]
        self.assertEqual(item['observed_input_tokens'],[66307,67013])
        self.assertEqual(completed._delivery_lessons({'delivery_lessons':lessons}),lessons)
        for kind in ('code','count','bool'):
            bad=deepcopy(item)
            if kind=='code':bad['source_text']='Not a lesson'
            elif kind=='count':bad['observed_input_tokens']=[64000]
            else:bad['completed_generations']=True
            with self.subTest(kind=kind),self.assertRaises(ValueError):completed._delivery_lessons({'delivery_lessons':[bad]})


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_INPUT_CAPACITY21')=='1','Root-only guarded original21→20→18 replay')
class ActualInputCapacity21(unittest.TestCase):
    def test_original21_input_stop_preserves_verified20_source_repair(self):
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
                if not isinstance(path,int)and set(re.findall(r'CIK[0-9]{10}',os.fsdecode(path)))-allowed:raise AssertionError('No nondev')
                return function(path,*a,**kw)
            return guarded
        def ro_db(path,*a,**kw):
            if '?mode=ro'not in str(path)or kw.get('uri')is not True:raise AssertionError('Read-only SQLite')
            return database(path,*a,**kw)
        with ExitStack()as stack:
            stack.enter_context(patch.object(tasks,'resident',side_effect=dev));stack.enter_context(patch.object(json,'loads',side_effect=public))
            stack.enter_context(patch.object(sqlite3,'connect',side_effect=ro_db));stack.enter_context(patch.object(socket.socket,'connect',side_effect=AssertionError('No network')))
            for module in (builtins,io,os):stack.enter_context(patch.object(module,'open',readonly(module.open)))
            # The prospective plan now advances to22; preserve the exact21
            # recovery test through its original committed plan, as20 does.
            historical=recovery.history._Reader(recovery.resume.OWNED,recovery.resume.LEDGER,
                recovery.resume.REPO,'edgar-population-20261016-22')
            historical.commit='3d5b59b34c872b672417097d956704833babeef7'
            original_plan=recovery.history._git(recovery.resume.REPO,historical.commit,recovery.PLAN)
            original_binding=dict(path=str(recovery.resume.REPO/recovery.PLAN),
                sha256=hashlib.sha256(original_plan).hexdigest())
            historical.sources={(original_binding['path'],original_binding['sha256'])}
            value=recovery.load(engine.pin(recovery.resume.OWNED/'attempts/edgar-population-20261016-21/population-run-failure.json'),
                root=recovery.resume.OWNED,ledger=recovery.resume.LEDGER,repo=recovery.resume.REPO,
                plan_binding=original_binding,historical_reader=historical)
        context=value['recovery_context'];diagnosis=context['input_delivery_diagnosis']
        self.assertEqual(context['mode'],recovery.AUTHOR_BASE_CAPACITY)
        self.assertEqual(context['public_failed_delta_sha256'],'995fa166e77b3d93cb5d32531dc39bd117802d6b28af157cfc268cc0d952472e')
        self.assertEqual(diagnosis['observed_input_tokens'],[66307,67013]);self.assertEqual(diagnosis['input_limit'],64000)
        self.assertEqual(recovery.latest_failed_attempt(value),diagnosis['failed_attempt'])
        self.assertTrue(diagnosis['failed_attempt']['path'].endswith('-21/population-run-failure.json'))
        self.assertEqual(value['last_scored_feedback']['sha256'],'170098840c76fd15e192b626526baede6a9d5214e762a73a27cd580f4a8a46b9')
        self.assertEqual(value['reference_candidate']['source']['sha256'],'466cc46f7b6e148df71038852c30213b2521ba391bf63479d2f5e7a5de9011c7')
        self.assertNotIn('author_stage_reuse',value)


if __name__=='__main__':unittest.main()
