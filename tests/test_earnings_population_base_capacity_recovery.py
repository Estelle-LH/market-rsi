"""V2 failed-delivery feedback; inert source/role fixtures, never model execution.

Portable tests reuse original-format base proofs and scripted transport. The
actual20 opt-in is a separate guarded read-only historical loader check, not a
fresh runtime admission, model reply, test execution or financial score.
"""
from contextlib import ExitStack
from copy import deepcopy
import builtins
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from edgar_forecast_budget import BudgetStop
import earnings_open_context as packing
import earnings_open_roles as roles
import earnings_population as pool
import earnings_population_campaign_context as contexts
import earnings_population_completed as completed
import earnings_population_delta_author as delta
import earnings_population_recovery as recovery
import earnings_population_services as services
import earnings_population_tasks as tasks
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_author_capacity_recovery as old
import test_earnings_population_implementation_base as bases
import test_earnings_open_roles as transports


class BaseCapacityFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.f=bases.ImplementationBaseTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.base=self.f.base()
        self.patch=self.f.new_patch(edits=[dict(kind='append',old_text='',new_text='\n# FAILED_V2_PUBLIC\n'+'q'*65500)])
        self.raw=old.response(self.patch)
        self.public,self.capacity=recovery._base_capacity_delta(self.f.parent['R'],self.f.chosen,
            self.raw,implementation_base=self.base)

    def failure(self):
        bound=self.f.f.authority
        return dict(schema='earnings_population_delivery_failure_v1',mode=recovery.AUTHOR_BASE_CAPACITY,
            failed_attempt=bound,audit=bound,stage='implement',error_type='ValueError',score_state='unscored',
            quality_assessment='not_run',failed_parent=dict(version_id=self.f.parent['id'],source=self.f.parent['R']),
            implementation_base=deepcopy(self.base),original_decision=bound,
            original_decision_public=deepcopy(self.f.chosen),original_scientific_decision_sha256=digest(self.f.chosen),
            raw_patch_response=bound,public_failed_delta=deepcopy(self.public),
            public_failed_delta_sha256=digest(self.public),capacity=deepcopy(self.capacity))

    def test_real_rejected_base_proof_and_literal_capacity_never_adopt_or_execute(self):
        self.assertEqual(self.public,self.patch)
        self.assertEqual(self.capacity['implementation_base_source_sha256'],self.base['source']['sha256'])
        self.assertEqual(self.capacity['comparison_parent_utf8_bytes'],len(self.f.parent_source.encode()))
        self.assertEqual(self.capacity['assembled_utf8_bytes'],len(self.f.source.encode())+len(self.patch['edits'][0]['new_text'].encode()))
        self.assertGreater(self.capacity['excess_utf8_bytes'],0)
        self.assertFalse(self.base['adopted']);self.assertFalse(self.f.f.marker.exists())

    def test_wrong_basis_hash_decision_shape_or_fitting_patch_refused(self):
        changes=[{'decision_sha256':'a'*64},{'comparison_parent_source_sha256':'b'*64},
            {'implementation_base_source_sha256':'c'*64},{'extra':True},{'test_text':'x'*32769},
            {'edits':[dict(kind='append',old_text='',new_text='# fits')]}]
        for change in changes:
            with self.subTest(change=list(change)),self.assertRaises(ValueError):
                recovery._base_capacity_delta(self.f.parent['R'],self.f.chosen,
                    old.response(dict(self.patch,**change)),implementation_base=self.base)
        base=dict(self.base,source=self.f.parent['R'])
        with self.assertRaises(ValueError):
            recovery._base_capacity_delta(self.f.parent['R'],self.f.chosen,self.raw,implementation_base=base)

    def test_controller_compacts_only_failed_bodies_and_keeps_original_free_choice(self):
        original=dict(schema='earnings_repair_context_v1',observations={'prior_delivery_failure':self.failure()})
        before=deepcopy(original);view=contexts.controller_view(original)
        actual=view['observations']['prior_delivery_failure']
        self.assertEqual(original,before);self.assertNotIn('public_failed_delta',actual)
        self.assertEqual(actual['original_decision_public'],self.f.chosen)
        self.assertEqual(actual['implementation_base'],self.base)
        self.assertEqual(actual['public_failed_delta_summary']['implementation_base_source_sha256'],self.base['source']['sha256'])
        self.assertNotIn('FAILED_V2_PUBLIC',json.dumps(view));self.assertNotIn('read_tool',actual)
        self.assertTrue(actual['public_failed_delta_omitted_from_controller_view'])
        altered=deepcopy(original);altered['observations']['prior_delivery_failure']['public_failed_delta']['test_text']+=' '
        with self.assertRaises(ValueError):contexts.controller_view(altered)

    def test_compact_distinct_base_lesson_survives_windows_once_without_code(self):
        failure=self.failure();before=deepcopy(failure)
        lessons=completed._delivery_lessons({'recovery_context':failure})
        self.assertEqual(failure,before);self.assertEqual(len(lessons),1)
        self.assertEqual(lessons[0]['implementation_base'],dict(version_id=self.base['version_id'],source=self.base['source']))
        self.assertNotIn('FAILED_V2_PUBLIC',json.dumps(lessons));self.assertNotIn('public_failed_delta',lessons[0])
        self.assertEqual(completed._delivery_lessons({'delivery_lessons':lessons}),lessons)
        self.assertEqual(completed._delivery_lessons({'delivery_lessons':lessons,'recovery_context':failure}),lessons)
        for kind in ('float','code','source','arithmetic'):
            corrupt=deepcopy(lessons)
            if kind=='float':corrupt[0]['capacity']['edit_count']=1.0
            elif kind=='code':corrupt[0]['public_failed_delta']=self.patch
            elif kind=='source':corrupt[0]['implementation_base']['source']=self.f.parent['R']
            else:corrupt[0]['capacity']['excess_utf8_bytes']+=1
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                completed._delivery_lessons({'delivery_lessons':corrupt})

    def test_original_services_DeltaAuthor_receiver_gets_exact_failure_and_one_valid_inline_base(self):
        f=self.f;t=transports.OpenRoleTests();t.setUp();self.addCleanup(t.doCleanups)
        original=t.service(author=True,max_turns=1,limits={
            'max_input_tokens':64000,'max_output_tokens':49152,'wall_seconds':1200})
        t.factory.return_value.post.return_value={'input_tokens':100,'synthetic_count':True}
        owner=services.Services.__new__(services.Services);owner.authored={};owner.native_root=f.root
        owner.runtime={'forecast_study':engine.save(f.root/'study-capacity.json',{})}
        owner.prior_feedback={'company_id':f.feedback['company_id']}
        owner.campaign_context={'feedback_binding':f.feedback_binding,'prior_candidate':f.reference,
            'campaign':f.f.authority,'original_R_evidence_abi':{'synthetic':True},
            'research_context':{'verification':'Synthetic original ABI',
                'observations':{'prior_delivery_failure':self.failure()}},'failure_evidence_context':None}
        owner.case=Mock(return_value={'synthetic':'case seam, not historical admission'})
        class Broker:
            definitions=[]
            def current_programs(inner):return {'R':{'source_sha256':f.parent['R']['sha256']}}
            def research_context(inner,*,include_source=False):return engine.read(owner.author_context)
        owner.role=lambda name,kind,case,slot:kind(original.binding,broker=Broker(),budget=t.budget,
            client_factory=t.factory,max_turns=1)
        t.generations=[t.message(f.new_patch())]
        state=pool.initialize(f.parent,{'K':'a'*64,'M':'b'*64,'C':'c'*64})
        with patch.object(roles,'budgeted_response',side_effect=t.fake_paid):
            child=owner.author(f.chosen,state,str(t.slot))
        request=t.requests[0];initial=json.loads(request['input'][0]['content'])
        self.assertEqual(initial['implementation_base_source_text'],f.source)
        self.assertEqual(initial['comparison_parent']['source'],f.parent['R'])
        self.assertEqual(initial['research_context']['prior_delivery_failure'],self.failure())
        self.assertEqual(request['text']['format']['name'],delta.BASE_FORMAT)
        self.assertEqual(child['parent'],f.parent['id']);self.assertFalse(f.f.marker.exists())
        # Original pack and final snapshot; only count values/old output invented.
        request['tool_choice']='none';request['input'].extend([
            dict(type='function_call',call_id='old',name='inspect_trace',arguments='{}'),
            dict(type='function_call_output',call_id='old',output='synthetic old output '*8000),
            dict(type='reasoning',id='opaque-not-interpreted')])
        seen=[]
        def counted(endpoint,payload):
            seen.append(deepcopy(payload));return {'input_tokens':64001 if len(seen)<4 else 63000}
        directory=f.root/'capacity-pack';directory.mkdir()
        packed=packing.pack(SimpleNamespace(post=counted),request,{'max_input_tokens':64000},directory,1,author_final=True)
        self.assertEqual(len(seen),4)
        for value in seen:self.assertEqual(json.loads(value['input'][0]['content']),initial)
        self.assertEqual(json.loads(packed['input'][0]['content'])['research_context']['prior_delivery_failure'],self.failure())
        with self.assertRaises(BudgetStop):
            packing.pack(SimpleNamespace(post=lambda *a:{'input_tokens':64001}),request,
                {'max_input_tokens':64000},directory,2,author_final=True)

    def producer(self, *, prior_failure=True):
        """Saved producer metadata; only expensive history verifiers are seams."""
        f=self.f
        scientific=dict(population=pool.initialize(f.parent,{'K':'a'*64,'M':'b'*64,'C':'c'*64}),
            previous_result=f.f.authority,feedback=f.feedback_binding,research_feedback=f.feedback,
            last_scored_feedback=f.f.authority,reference_candidate=f.reference,evidence=[f.f.authority])
        inherited=recovery._attach_capacity_failure(scientific,self.failure()) if prior_failure else scientific
        self.producer_count=getattr(self,'producer_count',0)+1
        directory=f.root/f'producer-{self.producer_count}';directory.mkdir()
        failed=engine.save(directory/'previous-failure.json',{'synthetic_failed':True})
        plan=engine.save(directory/'original-recovery-plan.json',{'synthetic_original_plan':True})
        resumed=dict(previous_result=inherited['previous_result'],plan=plan,
            **({'prior_failed_attempt':failed} if prior_failure else {}))
        study=dict(campaign_resume=engine.save(directory/'resume-producer.json',resumed),
            campaign_origin=engine.save(directory/'saved-producer-origin.json',inherited))
        reader=Mock(root=f.root);reader.read.side_effect=engine.read
        return inherited,failed,plan,study,reader

    def test_second_failed_producer_replays_prior_failure_then_compacts_before_attachment(self):
        inherited,failed,plan,study,reader=self.producer()
        before=deepcopy(inherited)
        with patch.object(recovery,'load',return_value=deepcopy(inherited))as recovered, \
             patch.object(completed,'load')as ordinary:
            actual=recovery._capacity_origin(reader,{},study,root=self.f.root,
                ledger=self.f.root/'ledger',repo=self.f.root/'repo')
        recovered.assert_called_once_with(failed,root=self.f.root,ledger=self.f.root/'ledger',
            repo=self.f.root/'repo',plan_binding=plan,historical_reader=reader)
        ordinary.assert_not_called();self.assertEqual(actual,before)
        newest=self.failure();newest['failed_attempt']=engine.save(self.f.root/'newest-failure.json',{'new_failure':True})
        transferred=recovery._attach_capacity_failure(actual,newest)
        self.assertEqual(inherited,before);self.assertEqual(transferred['recovery_context'],newest)
        self.assertEqual(transferred['population'],before['population'])
        self.assertEqual(transferred['research_feedback'],before['research_feedback'])
        self.assertEqual(transferred['last_scored_feedback'],before['last_scored_feedback'])
        self.assertEqual(transferred['delivery_lessons'][0]['failed_attempt'],before['recovery_context']['failed_attempt'])
        self.assertNotIn('public_failed_delta',transferred['delivery_lessons'][0])
        self.assertNotIn('FAILED_V2_PUBLIC',json.dumps(transferred['delivery_lessons']))

    def test_failed_producer_refuses_changed_completed_predecessor_or_saved_origin(self):
        for kind in ('predecessor','saved-origin'):
            inherited,failed,plan,study,reader=self.producer()
            loaded=deepcopy(inherited)
            if kind=='predecessor':loaded['previous_result']=failed
            else:loaded['research_feedback']=dict(loaded['research_feedback'],forged=True)
            with self.subTest(kind=kind),patch.object(recovery,'load',return_value=loaded), \
                 self.assertRaisesRegex(ValueError,'predecessor|producer origin'):
                recovery._capacity_origin(reader,{},study,root=self.f.root,
                    ledger=self.f.root/'ledger',repo=self.f.root/'repo')

    def test_no_prior_failure_keeps_original_completed_route_and_attachment_shape(self):
        inherited,_,_,study,reader=self.producer(prior_failure=False)
        with patch.object(completed,'load',return_value=deepcopy(inherited))as ordinary, \
             patch.object(recovery,'load')as failed:
            actual=recovery._capacity_origin(reader,{},study,root=self.f.root,
                ledger=self.f.root/'ledger',repo=self.f.root/'repo')
        ordinary.assert_called_once_with(inherited['previous_result'],root=self.f.root,
            ledger=self.f.root/'ledger',repo=self.f.root/'repo');failed.assert_not_called()
        attached=recovery._attach_capacity_failure(actual,self.failure())
        self.assertEqual(attached,dict(inherited,recovery_context=self.failure()))

    def test_public_failure_guard_survives_nested_reentry_and_resets_after_error(self):
        args=dict(root=self.f.root,ledger=self.f.root/'ledger',repo=self.f.root/'repo',plan_binding=self.f.f.authority)
        bound={'path':str(self.f.root/'same-failure.json'),'sha256':'a'*64}
        def recurse(*a,**kw):return recovery.load(bound,**args)
        with patch.object(recovery,'_dispatch_load',side_effect=recurse),self.assertRaisesRegex(ValueError,'noncyclic'):
            recovery.load(bound,**args)
        self.assertEqual(recovery._FAILURE_ANCESTRY.get(),())
        with patch.object(recovery,'_dispatch_load',return_value={'synthetic_new_call':True}):
            self.assertEqual(recovery.load(bound,**args),{'synthetic_new_call':True})


class BaseCapacityReceivingAdmissionTests(unittest.TestCase):
    def test_existing_prepare_and_admission_accept_only_exact_verified_active_ancestry(self):
        # Loader is deliberately an inherited, already-verified-origin seam.
        test=old.CapacityAdmissionTests()
        f,parent=test.fixture();self.addCleanup(test.doCleanups)
        f.origin['recovery_context']['mode']=recovery.AUTHOR_BASE_CAPACITY
        f.study['campaign_origin']=old.admission_fixture.save(f.inputs/'campaign-origin.json',f.origin)
        self.assertEqual(len(old.admission.validate(f.value,f.study,f.state)),2)
        f.origin['recovery_context']['failed_parent']['source']=f.version['R']
        with self.assertRaisesRegex(ValueError,'ancestry'):old.admission.validate(f.value,f.study,f.state)


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_BASE_CAPACITY20')=='1',
                     'Root-only guarded actual20→18 replay; no new runtime/model admission')
class ActualBaseCapacity20(unittest.TestCase):
    def test_exact_failure_keeps18_pool_reference_score_and_public_Delta(self):
        tempfile.gettempdir();allowed={'CIK0000003545','CIK0000004457','CIK0000017313'};qa_hashes=set()
        resident=tasks.resident;decode=json.loads;database=sqlite3.connect
        def dev(cik):
            if cik not in allowed:raise AssertionError('No held-out resident')
            result=resident(cik);qa_hashes.add(result['kernel']['qa']['sha256']);return result
        def public_json(raw,*a,**kw):
            data=raw.encode()if isinstance(raw,str)else raw
            if isinstance(data,(bytes,bytearray))and hashlib.sha256(data).hexdigest()in qa_hashes:
                raise AssertionError('No QA decode')
            return decode(raw,*a,**kw)
        def readonly(function):
            def guarded(path,*a,**kw):
                mode=kw.get('mode',a[0]if a else'r')
                if type(mode)is str and any(c in mode for c in 'wax+'):raise AssertionError('No writes')
                if type(mode)is int and mode&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):raise AssertionError('No writable fd')
                if not isinstance(path,int):
                    import re
                    if set(re.findall(r'CIK[0-9]{10}',os.fsdecode(path)))-allowed:raise AssertionError('No nondev body')
                return function(path,*a,**kw)
            return guarded
        def ro_db(path,*a,**kw):
            if '?mode=ro'not in str(path)or kw.get('uri')is not True:raise AssertionError('Read-only SQLite')
            return database(path,*a,**kw)
        with ExitStack()as stack:
            stack.enter_context(patch.object(tasks,'resident',side_effect=dev));stack.enter_context(patch.object(json,'loads',side_effect=public_json))
            stack.enter_context(patch.object(sqlite3,'connect',side_effect=ro_db));stack.enter_context(patch.object(socket.socket,'connect',side_effect=AssertionError('No network')))
            for module in (builtins,io,os):stack.enter_context(patch.object(module,'open',readonly(module.open)))
            # Current configuration advances to failed21. Replay20 through its
            # exact original Git-bound plan, not by editing production config.
            historical=recovery.history._Reader(recovery.resume.OWNED,recovery.resume.LEDGER,
                recovery.resume.REPO,'edgar-population-20261016-21')
            historical.commit='2f38477a6eca7a2e90cc8a1f2b5d813dddd04179'
            original_plan=recovery.history._git(recovery.resume.REPO,historical.commit,recovery.PLAN)
            original_binding=dict(path=str(recovery.resume.REPO/recovery.PLAN),
                sha256=hashlib.sha256(original_plan).hexdigest())
            historical.sources={(original_binding['path'],original_binding['sha256'])}
            value=recovery.load(engine.pin(recovery.resume.OWNED/'attempts/edgar-population-20261016-20/population-run-failure.json'),
                root=recovery.resume.OWNED,ledger=recovery.resume.LEDGER,repo=recovery.resume.REPO,
                plan_binding=original_binding,historical_reader=historical)
        self.assertEqual(value['previous_result']['sha256'],'78b11c5ca06b5a69bc2c2a043887fa301050eacb2db57f78f9f1862d006d8baf')
        self.assertEqual(value['last_scored_feedback']['sha256'],'170098840c76fd15e192b626526baede6a9d5214e762a73a27cd580f4a8a46b9')
        self.assertEqual(value['reference_candidate']['source']['sha256'],'466cc46f7b6e148df71038852c30213b2521ba391bf63479d2f5e7a5de9011c7')
        self.assertNotIn('author_stage_reuse',value);failure=value['recovery_context']
        self.assertEqual(failure['mode'],recovery.AUTHOR_BASE_CAPACITY)
        self.assertEqual(failure['capacity']['assembled_utf8_bytes'],69160)
        self.assertEqual(failure['capacity']['excess_utf8_bytes'],3624)
        self.assertEqual(failure['public_failed_delta_sha256'],digest(failure['public_failed_delta']))
        self.assertNotIn('source_text',failure);self.assertNotIn('implementation_base_source_text',failure)


if __name__=='__main__':unittest.main()
