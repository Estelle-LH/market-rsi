"""Accepted Review reuse; portable receipt fixtures, no provider or code execution.

The opt-in original25 proof is Root-only, unmocked and guarded. Portable fee
lookup/Native batch seams are explicit and are not full runtime admission.
"""
from contextlib import ExitStack,nullcontext
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
from unittest.mock import Mock,patch

import earnings_population_forecast_failure as origin
import earnings_population_services as services
import earnings_population_loop as loop
import earnings_population_tasks as tasks
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness import feedback_linked_loop as driver
import test_earnings_population_review23_origin as fixture
import test_earnings_population_recovery as prefix_fixture
import test_earnings_population_completed as completed_fixture
import test_earnings_population_parent_probe as parent_fixture


def actual_plan():
    value=fixture.actual_plan();root=origin.resume.OWNED
    value.update(recovery_mode=origin.MODE,
        failed_attempt=dict(path=str(root/'attempts/edgar-population-20261016-25/population-run-failure.json'),sha256='447968989fc2371cf28135098a218daf55bce9f3fbbdd7b4f8d75418315c4ab8'),
        closed_failure_audit=dict(path=str(root/'CUMULATIVE400-LIVE25-CLOSURE-AUDIT.json'),sha256='59c15aa2440d84d03a3bd92571d03a6a6204ea998ef976b8b22c92ad5aa150b4'),
        stage_delivery_audit=dict(path=str(root/'CUMULATIVE400-LIVE25-ROLE-LINKS.json'),sha256='efc98577588c689cb29fc7aed11b87f114d1155c92e9a655e1658a20a80fede3'))
    return value


def accepted_fixture(root,child,scientific):
    folder=root/'roles/review-01';folder.mkdir(parents=True,exist_ok=True)
    (root/'loop').mkdir(parents=True,exist_ok=True)
    business=dict(candidate_id=child['id'],accepted_for_exploration=True,rationale='Synthetic bounded exploration only.')
    raw=dict(status='completed',output=[dict(type='message',content=[dict(type='output_text',text=json.dumps(business))])])
    response=engine.save(folder/'response.json',raw);engine.save(folder/'08-response.json',raw)
    projection=engine.save(folder/'review.json',dict(original=response,review=business))
    result=engine.save(folder/'result.json',dict(status='COMPLETED_REVIEW',error_type=None,retry_allowed=False,
        turns=8,tool_calls=7,final_numbered_response='08-response.json',wall_seconds=843.8))
    output=dict(accepted_for_exploration=True,evidence=[projection,response])
    done=engine.save(root/'loop/round-0001-source_review.done.json',dict(output=output))
    review=dict(schema='earnings_population_review_stage_reuse_v1',mode=origin.REUSE,
        source_attempt=engine.save(root/'population-run-failure.json',{'synthetic_failure':True}),candidate=deepcopy(child),
        scientific_decision_sha256=digest(scientific),original_response=response,review_projection=projection,
        role_result=result,source_review_output=done,evidence=deepcopy(output['evidence']),new_model_Review_called=False)
    return review


class AcceptedAndStopTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.native=tempfile.TemporaryDirectory(prefix='market-rsi-',dir='/private/tmp');self.addCleanup(self.native.cleanup)
        self.root=Path(self.temp.name)/Path(self.native.name).name.removeprefix('market-rsi-');self.root.mkdir()
        self.reader=SimpleNamespace(read=engine.read,pin=engine.pin)
        self.authored=dict(candidate={'id':'a'*64},scientific_decision={'axis':'R'})
        self.review=accepted_fixture(self.root,self.authored['candidate'],self.authored['scientific_decision'])
        public=engine.read(self.review['review_projection'])['review']
        outcome=engine.save(Path(self.native.name)/'review-01-outcome.json',dict(schema='earnings_population_exploration_review_v1',**public))
        self.output=dict(accepted_for_exploration=True,evidence=[outcome,self.review['original_response']])
        self.terminal=dict(role_results={'review':dict(binding=self.review['role_result'],value=engine.read(self.review['role_result']))})
        self.runtime={'limits':{'review':{'wall_seconds':900},'forecast':{'wall_seconds':1800}}}
        self.slot=self.root/'roles/forecast-01-00';self.slot.mkdir()
        for n in range(1,4):
            engine.save(self.slot/f'{n:02d}-request.json',{'synthetic_request':n})
            engine.save(self.slot/f'{n:02d}-response.json',{'synthetic_response':n})
        value=dict(status='FAILED_NO_RETRY',error_type='BudgetStop',retry_allowed=False,planned_targets=5,scored_targets=0,wall_seconds=1799.8)
        bound=engine.save(self.slot/'result.json',value);self.terminal['role_results']['forecast']=dict(binding=bound,value=value)

    def accepted(self):return origin._accepted(self.reader,self.root,self.runtime,self.terminal,self.output,self.authored)
    def stopped(self):return origin._forecast_result(self.reader,self.root,self.runtime,self.terminal)

    def test_exact_completed_review_and_unscored_first_arm_are_distinct(self):
        review,count=self.accepted();self.assertEqual(count,8);self.assertEqual(review['candidate'],self.authored['candidate'])
        self.assertFalse(review['new_model_Review_called']);self.assertEqual(self.stopped()[0],3)

    def test_rejected_fake_raw_alias_outcome_or_result_refuses(self):
        changes=[(self.review['original_response'],lambda d:d['output'][0]['content'][0].update(text='{}')),
                 (self.review['role_result'],lambda d:d.update(turns=True)),
                 (self.output['evidence'][0],lambda d:d.update(accepted_for_exploration=False))]
        for bound,mutate in changes:
            changed=deepcopy(engine.read(bound));mutate(changed);read=self.reader.read
            with self.subTest(path=bound['path']),patch.object(self.reader,'read',side_effect=lambda b:deepcopy(changed)if b==bound else read(b)),self.assertRaises(ValueError):self.accepted()

    def test_missing_originals_scores_predictions_or_other_arms_refuse(self):
        for name in ('predictions.json','score.json','population-public-feedback.json'):
            p=self.slot/name;engine.save(p,{})
            with self.subTest(name=name),self.assertRaises(ValueError):self.stopped()
            p.unlink()
        other=self.root/'roles/forecast-01-01';other.mkdir()
        with self.assertRaises(ValueError):self.stopped()
        other.rmdir();(self.slot/'02-response.json').unlink()
        with self.assertRaises(ValueError):self.stopped()

    def test_wrong_status_truthy_score_bool_wall_or_foreign_closed_result_refuse(self):
        bound=self.terminal['role_results']['forecast']['binding'];before=engine.read(bound)
        for change in ({'scored_targets':False},{'scored_targets':1},{'status':'COMPLETED'},{'wall_seconds':True},{'wall_seconds':float('inf')}):
            value=dict(before,**change)
            self.terminal['role_results']['forecast']['value']=value
            with self.subTest(change=change),patch.object(self.reader,'read',side_effect=lambda b:deepcopy(value)if b==bound else engine.read(b)),self.assertRaises(ValueError):self.stopped()


class PhysicalTests(unittest.TestCase):
    def setUp(self):
        from edgar_forecast_openai import unit
        self.f=fixture.PhysicalTranscriptTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.reader=self.f.reader;self.runtime=self.f.runtime;self.root=self.f.root
        self.runtime['slots']={'review':[str(self.root/'roles/review-01')],'forecast':[str(self.root/'roles/forecast-01-00')]}
        self.runtime['limits']['forecast']=dict(max_input_tokens=1000,max_output_tokens=20,wall_seconds=1800)
        self.runtime['role_efforts']['forecast']='max'
        snap=self.f.audit['checkpoints'][0]
        self.rows=[r for r in snap['requests']if r['role']=='review-01']
        self.owned=[r for r in self.f.owned if Path(r['request']['path']).parent.name=='review-01']
        self.audit={'checkpoints':[dict(requests=self.rows,prepared_counts=[r for r in snap['prepared_counts']if r['role']=='review-01'])]}
        folder=self.root/'roles/forecast-01-00';folder.mkdir()
        for n in range(1,4):
            no=f'{n:02d}';payload=dict(model='synthetic-model',reasoning={'effort':'max'},input=[{'role':'user','content':'Synthetic original prediction task'}])
            request=dict(payload=payload,request_id='forecast'+no,reserved_nano_usd=100*unit(1)+20*unit(2));bound=engine.save(folder/(no+'-request.json'),request)
            response=dict(status='completed',error=None,model='synthetic-model',service_tier='default',usage=dict(input_tokens=90,output_tokens=2,total_tokens=92,input_tokens_details={'cached_tokens':10}),output=[dict(type='function_call',name='read_file',arguments='{}')])
            rb=engine.save(folder/(no+'-response.json'),response);count=engine.save(folder/(no+'-count.json'),{'input_tokens':100})
            intent=engine.save(folder/('http-gen'+no+'.intent.json'),dict(endpoint='/v1/responses',retry_allowed=False,complete_reservation=request,
                budget_request_id=request['request_id'],request_receipt_sha256=bound['sha256'],payload=dict(payload,max_output_tokens=20,service_tier='default',store=False)))
            raw=engine.save(folder/('http-gen'+no+'.raw.bin'),response);side=engine.save(folder/('http-gen'+no+'.response.json'),response)
            cb=engine.save(folder/('http-count'+no+'.intent.json'),dict(endpoint='/v1/responses/input_tokens',payload=payload,retry_allowed=False))
            engine.save(folder/('http-count'+no+'.raw.bin'),{'input_tokens':100});charge=80*unit(1)+10*unit(.5)+2*unit(2)
            self.owned.append(dict(request=bound,request_id=request['request_id'],status='settled',charged_nano_usd=charge))
            self.rows.append(dict(binding=bound,role='forecast-01-00',number=no,usage={'expected_conservative_charge_nano_usd':charge},matching_actual_count_origins=[cb],physical=dict(failure=None,intent=intent,raw=raw,numbered_response=rb,sidecar=side)))

    def physical(self,owned=None):
        own=self.owned if owned is None else owned
        with patch.object(origin,'_owned_requests',return_value=own),patch.object(origin.prior,'_owned_requests',return_value=[r for r in own if Path(r['request']['path']).parent.name=='review-01']):
            return origin._physical(self.reader,self.runtime,self.audit,6,3)

    def test_real_saved_physical_count_usage_joins_with_explicit_ledger_lookup_seams(self):
        own,evidence=self.physical();self.assertEqual(len(own),9);self.assertEqual(len(evidence),45)

    def test_uncertain_missing_extra_charge_or_duplicate_owned_request_refuses(self):
        for kind in ('missing','extra','uncertain','charge'):
            own=deepcopy(self.owned)
            if kind=='missing':own.pop()
            elif kind=='extra':own.append(own[-1])
            elif kind=='uncertain':own[-1]['status']='uncertain'
            else:own[-1]['charged_nano_usd']+=1
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.physical(own)

    def test_raw_count_model_payload_or_final_prediction_counterfeit_refuses(self):
        row=self.rows[-1];targets=[(row['physical']['intent'],lambda d:d['payload'].update(model='foreign')),
            (row['physical']['raw'],lambda d:d.update(status='incomplete')),
            (row['physical']['numbered_response'],lambda d:d.update(output=[{'type':'message','content':[]}])) ,
            (row['matching_actual_count_origins'][0],lambda d:d['payload'].update(input=[]))]
        for bound,mutate in targets:
            changed=deepcopy(engine.read(bound));mutate(changed);read=self.reader.read
            with self.subTest(path=bound['path']),patch.object(self.reader,'read',side_effect=lambda b,**kw:deepcopy(changed)if b==bound else read(b,**kw)),self.assertRaises(ValueError):self.physical()


class ExecutePrefixTests(unittest.TestCase):
    def setUp(self):
        self.f=prefix_fixture.FailedPrefixContracts();self.f.setUp();self.addCleanup(self.f.doCleanups)
        seed,outputs,_=self.f.load();path=self.f.path
        (path/'round-0001-source_review.failed.json').unlink()
        claim=engine.pin(path/'round-0001-source_review.claim.json')
        output=dict(accepted_for_exploration=True,evidence=[])
        self.f.seal(path/'round-0001-source_review.done.json',dict(claim_sha256=claim['sha256'],output=output,output_sha256=digest(output)))
        outputs['source_review']=output
        context=dict(round_index=1,seed=seed,previous_result=seed,previous_feedback_sha256=digest(seed),outputs=outputs)
        claimed=dict(round_index=1,stage='execute',context_sha256=digest(context),manifest_sha256=engine.pin(path/'manifest.json')['sha256'],previous_feedback_sha256=digest(seed))
        self.f.replace(path/'round-0001-execute.claim.json',claimed)
        self.f.replace(path/'round-0001-execute.failed.json',dict(claim_sha256=engine.pin(path/'round-0001-execute.claim.json')['sha256'],exception_type='RuntimeError',retry_allowed=False))

    def test_exact_accepted_four_stage_prefix_then_execute_failure_not_completed_round(self):
        _,rows,_=origin.recovery._prefix(self.f.reader,self.f.runtime,self.f.attempt,failed_stage='execute')
        self.assertTrue(rows['source_review']['accepted_for_exploration']);self.assertNotIn('execute',rows)
        with self.assertRaises(ValueError):self.f.load()

    def test_later_round_reconcile_claim_fake_done_or_changed_failure_refuses(self):
        for name in ('round-0001-execute.done.json','round-0001-reconcile.claim.json','round-0002-input.claim.json'):
            path=self.f.path/name;self.f.replace(path,{})
            with self.subTest(name=name),self.assertRaises(ValueError):origin.recovery._prefix(self.f.reader,self.f.runtime,self.f.attempt,failed_stage='execute')
            path.unlink()


class ReceivingTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.V2ReceivingTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.review=accepted_fixture(self.f.root/'closed-review',self.f.bundle['candidate'],self.f.bundle['scientific_decision'])
        self.origin=dict(author_stage_reuse=deepcopy(self.f.bundle),review_stage_reuse=self.review)
        self.saved=engine.save(self.f.root/'origin-new.json',self.origin)
        study=engine.read(self.f.owner.runtime['forecast_study']);study['campaign_origin']=self.saved
        self.f.owner.runtime['forecast_study']=engine.save(self.f.root/'study-new.json',study);self.f.context['origin']=self.saved
        self.f.owner.case.return_value['context']={'path':'/synthetic/new/Native/context.json','sha256':'a'*64}

    def drive(self):
        self.forecasts=[]
        def forecast(version,company,slot):
            self.forecasts.append(version['id']);return dict(version_id=version['id'],points=1,evidence=[self.f.f.assembly])
        with (patch.object(services,'public_feedback',return_value={'synthetic_unscored':True}),
              patch('earnings_population_campaign_context.prepare',return_value=deepcopy(self.f.context)),
              patch.object(services,'implementation_base',side_effect=AssertionError('No new base selection')),
              patch.object(services,'run_cases',side_effect=AssertionError('Original accepted cases, not new host execution'))):
            result=loop.run(self.f.owner.root,self.f.f.state,['synthetic-unexposed'],dict(controller=self.f.owner.controller,
                author=self.f.owner.author,review=self.f.owner.review,forecast=forecast),admit=lambda c:True,max_rounds=1,
                identity=lambda:{s:{'synthetic':s}for s in driver.STAGES})
        rows={s:engine.read(engine.pin(self.f.owner.root/'loop'/f'round-0001-{s}.done.json'))['output']for s in driver.STAGES}
        return result,rows

    def test_original_services_driver_writes_honest_review_receipt_without_any_new_model_role(self):
        result,rows=self.drive();self.assertEqual(result['status'],'completed')
        self.f.role.propose.assert_not_called();self.f.role.author.assert_not_called();self.f.role.review.assert_not_called()
        marker=rows['source_review']['evidence'][0];receipt=engine.read(marker)
        self.assertFalse(receipt['new_model_called']);self.assertEqual(receipt['original_response'],self.review['original_response'])
        self.assertFalse((Path(marker['path']).parent/'review.json').exists())
        origin.recovery.verify_reused_stages(self.f.f.reader,self.f.owner.root,rows,self.origin)
        self.assertEqual(self.forecasts,[self.f.f.f.parent['id'],self.f.f.child['id']])
        # Completed._rounds already calls this exact verifier. Its ordinary
        # return constructor deliberately has no role-reuse fields; no mocked
        # completed-result object or new model-review response is manufactured.

    def test_durable_receipt_raw_source_decision_or_new_review_log_refuses(self):
        _,rows=self.drive();marker=rows['source_review']['evidence'][0]
        for kind in ('missing_marker','new_response','wrong_candidate','wrong_decision'):
            bad=deepcopy(self.origin);changed=deepcopy(rows)
            if kind=='missing_marker':changed['source_review']['evidence'].pop(0)
            elif kind=='new_response':engine.save(Path(marker['path']).parent/'response.json',{})
            elif kind=='wrong_candidate':bad['review_stage_reuse']['candidate']['id']='f'*64
            else:bad['review_stage_reuse']['scientific_decision_sha256']='f'*64
            with self.subTest(kind=kind),self.assertRaises(ValueError):origin.recovery.verify_reused_stages(self.f.f.reader,self.f.owner.root,changed,bad)
            p=Path(marker['path']).parent/'response.json'
            if p.exists():p.unlink()

    def test_legacy_author_only_path_stays_without_a_review_reuse_requirement(self):
        _,rows=self.drive();legacy={'author_stage_reuse':self.f.bundle}
        origin.recovery.verify_reused_stages(self.f.f.reader,self.f.owner.root,rows,legacy)


class IdleNativeSchemaTests(unittest.TestCase):
    """Original identity checks with an inert batch/lock fixture, not admission."""
    def fixture(self,role):
        f=completed_fixture.CompletedDraftTests();f.module=__import__('earnings_population_completed')
        reader,native,runtime,config,expected,batch,state,resident,python,values=f.native_fixture(role)
        state.pop('capacity_work',None)
        batch._read_snapshot.return_value=deepcopy(state);batch._replay.return_value=deepcopy(state)
        bound=lambda name:{'path':'/synthetic/'+name,'sha256':'9'*64}
        closure_bound,owner,claim=map(bound,('closure.json','owner.json','claim.json'))
        refs={k:bound(k+'.json')for k in ('failure_evidence','before_native_snapshot','after_native_snapshot','before_native_journal')}
        closure=dict(schema='earnings_native_failure_closure_v1',status='FAILED_WORK_CLOSED_NO_RETRY',runtime=runtime,
            owner_terminal=owner,own_request_count=0,own_charge_nano_usd=0,candidate_adopted=False,retry_allowed=False,
            work_id='synthetic-claimed-work',pair_sha256='a'*64,**refs)
        failure=dict(runtime=runtime,owner_terminal=owner,owner_claim=claim,owned_requests=[],cleanup=[],
            candidate_adopted=False,retry_allowed=False,error_type='LoopHalted',**{k:closure[k]for k in ('work_id','pair_sha256','before_native_snapshot','before_native_journal')})
        values.update({closure_bound['path']:closure,refs['failure_evidence']['path']:failure,
            refs['before_native_snapshot']['path']:deepcopy(state),refs['after_native_snapshot']['path']:deepcopy(state),refs['before_native_journal']['path']:[]})
        return reader,native,runtime,config,expected,batch,resident,python,closure_bound,owner,claim

    def run_native(self,fixture):
        reader,native,runtime,config,expected,batch,resident,python,closure,owner,claim=fixture
        with patch('supervisor_harness.continuous_discovery_batch.ContinuousDiscoveryBatch',return_value=batch),\
             patch.object(origin.os,'open',return_value=42),patch.object(origin.os,'fdopen',return_value=nullcontext(Mock())),patch.object(origin.fcntl,'flock'):
            return origin._native_failure(reader,native,runtime,config,expected,resident,python,closure,owner,[],claim_bound=claim,cleanup=[])

    def test_original_idle_nonforecast_schema_may_omit_capacity_work(self):
        self.assertEqual(len(self.run_native(self.fixture('controller'))),4)

    def test_forecast_schema_without_exact_failed_work_remains_rejected(self):
        with self.assertRaisesRegex(ValueError,'claim/failure journal'):
            self.run_native(self.fixture('forecast'))


class LegacyNoRuntimeTests(unittest.TestCase):
    def test_inert_legacy_review_without_runtime_keeps_original_matched_parent_path(self):
        f=parent_fixture.MatchedParentProbeTests();f.setUp();self.addCleanup(f.doCleanups)
        self.assertFalse(hasattr(f.owner,'runtime'))
        with patch.object(f.owner,'reused_author',side_effect=AssertionError('No opt-in runtime, no reuse lookup')):
            result=f.invoke()
        self.assertFalse(result['accepted_for_exploration'])
        self.assertEqual(len(f.prompts),1);self.assertEqual(f.owner.runner.calls,8)
        self.assertEqual(f.owner.runner.invocations[0]['payload'],f.owner.runner.invocations[4]['payload'])
        self.assertEqual(f.owner.runner.invocations[4]['source'],Path(f.parent['R']['path']).read_text())


class EarlyAndDispatchTests(unittest.TestCase):
    def test_invalid_mode_binding_or_foreign_path_refuses_before_reader(self):
        p=actual_plan()
        for bound,plan in [({},p),(p['failed_attempt'],dict(p,recovery_mode='foreign')),
                           (dict(p['failed_attempt'],path='/foreign/population-run-failure.json'),p)]:
            with self.subTest(bound=bound),patch.object(origin.history,'_Reader',side_effect=AssertionError('No body read')),self.assertRaises(ValueError):
                origin.load(bound,root=origin.resume.OWNED,ledger=origin.resume.LEDGER,repo=origin.resume.REPO,plan=plan)

    def test_only_exact_new_mode_dispatches_original_legacy_routes_are_not_coerced(self):
        plan=actual_plan();pb={'path':str(origin.resume.REPO/origin.recovery.PLAN),'sha256':'a'*64}
        with patch.object(origin.recovery,'_read_plan',return_value=plan),patch.object(origin,'load',return_value={'synthetic_verified_origin':True})as target:
            result=origin.recovery.load(plan['failed_attempt'],root=origin.resume.OWNED,ledger=origin.resume.LEDGER,repo=origin.resume.REPO,plan_binding=pb)
        self.assertTrue(result['synthetic_verified_origin']);target.assert_called_once_with(plan['failed_attempt'],root=origin.resume.OWNED,ledger=origin.resume.LEDGER,repo=origin.resume.REPO,plan=plan)


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_FORECAST25_ORIGIN')=='1','Root-only guarded original25→24→23 ancestry, no provider/QA decode/writes')
class ActualForecast25Origin(unittest.TestCase):
    def test_original_accepted_review_survives_unscored_fixed_control_deadline(self):
        tempfile.gettempdir();allowed={'CIK0000003545','CIK0000004457','CIK0000017313'};qa=set()
        resident=tasks.resident;decode=json.loads;database=sqlite3.connect
        def dev(cik):
            if cik not in allowed:raise AssertionError('No held-out resident')
            value=resident(cik);qa.add(value['kernel']['qa']['sha256']);return value
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
            with origin.history.validation_epoch():value=origin.load(plan['failed_attempt'],root=origin.resume.OWNED,ledger=origin.resume.LEDGER,repo=origin.resume.REPO,plan=plan)
        self.assertTrue(value['author_stage_reuse']['failed_attempt']['path'].endswith('-23/population-run-failure.json'))
        self.assertEqual(value['review_stage_reuse']['source_attempt'],plan['failed_attempt'])
        self.assertFalse(value['review_stage_reuse']['new_model_Review_called'])
        self.assertEqual(value['recovery_context']['stage'],'execute');self.assertEqual(value['recovery_context']['completed_forecast_generations'],19)
        self.assertEqual(value['feedback']['sha256'],'238ca35f5c9a9644b5960e376ec7b14436895eeec1ae73910fea8a557aef6544')
        self.assertEqual(value['last_scored_feedback']['sha256'],'170098840c76fd15e192b626526baede6a9d5214e762a73a27cd580f4a8a46b9')
        self.assertNotIn(value['author_stage_reuse']['candidate']['id'],value['population']['versions'])


if __name__=='__main__':unittest.main()
