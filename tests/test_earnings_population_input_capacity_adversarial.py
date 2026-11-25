"""Independent input-capacity boundaries and read-only proof adversaries.

Fixtures are invented temporary bytes and counted lookup replies, never new
provider requests, real ledger writes, candidate execution or historical replay.
Every patched full-proof boundary is explicit in its individual test.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from edgar_forecast_budget import BudgetStop
import earnings_open_context as packing
import earnings_open_program as programs
import earnings_open_resources as resources
import earnings_population_recovery as recovery
import earnings_population_completed as completed
from earnings_open_roles import _format
from earnings_loop_policy import LIMITS
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_author_input16 as input_fixture
import test_earnings_population_base_capacity_adversarial as base_fixture
import test_earnings_population_author_capacity_recovery as preparation_fixture
import test_earnings_population_control_history as history_fixture
from test_earnings_population_delta_author import R, choice


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,sort_keys=True))
    return engine.pin(path)


class IndependentProspectiveInputBoundaries(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='input21-adversarial-')
        self.addCleanup(temporary.cleanup);self.root=Path(temporary.name).resolve()

    def request(self):
        return {'model':'gpt-6.1-sol','reasoning':{'effort':'high'},'instructions':'Unchanged protocol',
            'tools':[],'tool_choice':'auto','input':[{'role':'user','content':'public preserved '*2000}]}

    def test_exact96000_fits_but96001_fails_without_model_generation(self):
        original=self.request();untouched=deepcopy(original)
        for count,passes in ((96000,True),(96001,False)):
            folder=self.root/str(count);folder.mkdir();client=Mock()
            client.post.return_value={'input_tokens':count,'synthetic_lookup':True}
            with self.subTest(count=count):
                if passes:
                    actual=packing.pack(client,original,{'max_input_tokens':96000},folder,3)
                    self.assertEqual(actual,untouched)
                else:
                    with self.assertRaises(BudgetStop):
                        packing.pack(client,original,{'max_input_tokens':96000},folder,3)
            self.assertTrue(all(c.args[0]=='/v1/responses/input_tokens' for c in client.post.call_args_list))
            self.assertLessEqual(client.post.call_count,4)
        self.assertEqual(original,untouched)

    def test_synthetic21_shape_old64_rejects_new96_selects_same_first_request(self):
        request=self.request();before=deepcopy(request)
        for ceiling,passes in ((64000,False),(96000,True)):
            folder=self.root/str(ceiling);folder.mkdir();client=Mock()
            client.post.return_value={'input_tokens':66307,'synthetic_not_actual21_count':True}
            if passes:
                result=packing.pack(client,request,{'max_input_tokens':ceiling},folder,3)
                self.assertEqual(result,before);self.assertEqual(client.post.call_count,1)
            else:
                with self.assertRaises(BudgetStop):
                    packing.pack(client,request,{'max_input_tokens':ceiling},folder,3)
        self.assertEqual(request,before)

    def test_count_types_and_provider_count_failure_fail_closed(self):
        for index,value in enumerate((True,'96000',96000.0,-1)):
            folder=self.root/f'bad-{index}';folder.mkdir();client=Mock()
            client.post.return_value={'input_tokens':value,'synthetic_lookup':True}
            with self.subTest(value_type=type(value).__name__),self.assertRaises(ValueError):
                packing.pack(client,self.request(),{'max_input_tokens':96000},folder,3)
            self.assertEqual(client.post.call_count,1)
        folder=self.root/'large-positive-count';folder.mkdir();client=Mock()
        client.post.return_value={'input_tokens':2**63,'synthetic_lookup':True}
        with self.assertRaises(BudgetStop):
            packing.pack(client,self.request(),{'max_input_tokens':96000},folder,3)
        self.assertLessEqual(client.post.call_count,4)
        folder=self.root/'count-failed';folder.mkdir();client=Mock()
        failure=RuntimeError('invented original count transport failure');client.post.side_effect=failure
        with self.assertRaises(RuntimeError)as caught:
            packing.pack(client,self.request(),{'max_input_tokens':96000},folder,3)
        self.assertIs(caught.exception,failure);self.assertEqual(client.post.call_count,1)

    def test_actual_role_constructor_only_input_increased_other_settings_unchanged(self):
        f=input_fixture.PortableInputCeilingTests();f.setUp();self.addCleanup(f.doCleanups)
        self.assertEqual(resources.role_limits(),{
            'author':{'max_input_tokens':96000,'max_output_tokens':49152,'wall_seconds':1200},
            'controller':{'max_input_tokens':32000,'max_output_tokens':16384,'wall_seconds':900},
            'review':{'max_input_tokens':32000,'max_output_tokens':16384,'wall_seconds':900}})
        self.assertEqual(resources.ROLE_EFFORTS,{'author':'high','controller':'max','review':'max','forecast':'max'})
        self.assertEqual(LIMITS,{'max_input_tokens':10000,'max_output_tokens':16384,'wall_seconds':600})
        limits=resources.role_limits()['author']
        self.assertEqual(f.construct(input_fixture.OpenAuthor,limits).context['limits'],limits)
        for key,value in (('max_input_tokens',96001),('max_input_tokens',True),
                ('max_input_tokens',96000.0),('max_output_tokens',49153),('wall_seconds',1201)):
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                f.construct(input_fixture.OpenAuthor,dict(limits,**{key:value}))

    def test_source_and_case_byte_caps_remain65536_and32768_and_are_ast_only(self):
        marker=self.root/'MUST_NOT_EXECUTE'
        header=("PROGRAM={'axis':'R'}\nfrom pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('NO EXECUTION')\n"
            "def run(p):return 1\n")
        source=header+'#'+'x'*(65536-len(header.encode())-1)
        self.assertEqual(len(source.encode()),65536)
        self.assertEqual(programs.program(source.encode(),'R'),{'axis':'R'})
        with self.assertRaises(ValueError):programs.program((source+'x').encode(),'R')
        chosen=choice();cases="CASES=[{'input':{},'expected':1}]\n"
        exact=cases+'#'+'x'*(32768-len(cases.encode())-1)
        business={'decision_sha256':digest(chosen),'source_text':header,'test_text':exact}
        parsed=programs.candidate(business,{'axis':'R'},chosen)
        self.assertFalse(parsed['tests_executed'])
        with self.assertRaises(ValueError):programs.candidate(dict(business,test_text=exact+'x'),{'axis':'R'},chosen)
        self.assertFalse(marker.exists())


class IndependentInputClosureAdversaries(unittest.TestCase):
    """Saved invented counted originals; owned fee rows are an explicit seam."""
    def fixture(self):
        helper=base_fixture.V2ClosureAdversaries();f=helper.fixture();self.addCleanup(helper.doCleanups)
        reader,attempt,_,runtime,_,owner,audit,delivery,owned,saved=f
        author=attempt/'roles/author-01'
        for number in range(3,9):
            for path in author.glob(f'{number:02d}-*'):path.unlink()  # Temporary fixture files only.
        runtime['id']='edgar-population-20261016-21'
        runtime_bound=saved(attempt/'runtime.json',runtime)
        owner['runtime']=runtime_bound;owner_bound=saved(attempt/'owner-result.json',owner)
        terminal=audit['terminal_evidence'];final=audit['checkpoints'][-1]
        audit.update(schema='earnings_population_live21_closure_audit_v1',
            status='SEALED_FAILED_AUTHOR_INPUT_BUDGETSTOP_ALL_10_FEES_SETTLED',
            attempt_id=runtime['id'],runtime=runtime_bound)
        terminal['owner_terminal']={'binding':owner_bound,'value':owner}
        final.update(owner_terminal=deepcopy(terminal['owner_terminal']),runtime=runtime_bound)
        keep=lambda row:row['role']=='controller-01' or int(row['number'])<=2
        final['prepared_counts']=[r for r in final['prepared_counts'] if keep(r)]
        final['requests']=[r for r in final['requests'] if Path(r['binding']['path']).parent.name=='controller-01'
            or int(Path(r['binding']['path']).name[:2])<=2]
        owned=[r for r in owned if Path(r['request']['path']).parent.name=='controller-01'
            or int(Path(r['request']['path']).name[:2])<=2]
        result={'status':'FAILED_NO_RETRY','error_type':'BudgetStop','turns':3,
            'final_numbered_response':'02-response.json','retry_allowed':False}
        result_binding=saved(author/'result.json',result)
        final['roles']['author-01']['result']=result
        delivery.update(status='SEALED_FAILED_AUTHOR_INPUT_CAPACITY_BEFORE_CODE',
            attempt_id=runtime['id'],runtime_reviewed_sha256=runtime_bound['sha256'],
            author_terminal={'result':result_binding,'result_value':result})
        delivery['controller']=delivery.pop('controller_terminal_transport')
        return reader,attempt,runtime_bound,runtime,owner_bound,owner,audit,delivery,owned,saved

    def project(self,f):return recovery._input_capacity_closure(*f[:8])

    def test_input_stop_preserves_attempted3_but_joins_only_two_completed_author_calls(self):
        f=self.fixture();before=deepcopy(f[6:8]);projected=self.project(f)
        result=next(r for r in projected['terminal_evidence']['roles'] if r['role']=='author-01')
        self.assertEqual(result['value']['turns'],3);self.assertEqual(result['completed_turns'],2)
        with patch.object(recovery,'_owned_requests',return_value=f[8]):
            evidence=recovery._capacity_requests(f[0],f[3],projected,base_mode=True)
        self.assertEqual(len(evidence),10*6);self.assertEqual(len(projected['terminal_evidence']['requests']),10)
        self.assertEqual(f[6:8],before);self.assertFalse((f[1]/'roles/author-01/03-request.json').exists())
        with self.assertRaises(ValueError):recovery._base_capacity_closure(*f[:8])

    def test_wrong_original_count_source_owner_or_fake_candidate_closure_refused(self):
        for kind in ('source','owner','candidate','code','missing-request','completed3','wrong-turn'):
            f=self.fixture();audit,delivery=f[6:8];final=audit['checkpoints'][-1]
            if kind=='source':audit['source_commit']='f'*40
            elif kind=='owner':audit['terminal_evidence']['owner_terminal']['value']=dict(f[5],status='RUNNING')
            elif kind=='candidate':audit['terminal_evidence']['candidate_files']['candidate.py']=f[2]
            elif kind=='code':audit['terminal_evidence']['code_entries']=['invented-executed-source']
            elif kind=='missing-request':final['requests'].pop()
            else:
                result=deepcopy(delivery['author_terminal']['result_value'])
                if kind=='completed3':result['final_numbered_response']='03-response.json'
                else:result['turns']=2
                delivery['author_terminal']['result']=f[9](Path(delivery['author_terminal']['result']['path']),result)
                delivery['author_terminal']['result_value']=result;final['roles']['author-01']['result']=result
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.project(f)

    def test_unknown_fees_missing_request_wrong_charge_or_count_drift_refused(self):
        for kind in ('unknown','missing','charge','count','origin'):
            f=self.fixture();projected=self.project(f);row=projected['terminal_evidence']['requests'][-1]
            if kind=='unknown':f[8][-1]['status']='uncertain'
            elif kind=='missing':f[8].pop()
            elif kind=='charge':f[8][-1]['charged_nano_usd']+=1
            elif kind=='count':row['count']=f[9](Path(row['count']['path']),{'input_tokens':31})
            else:row['matching_actual_count_origins']=[]
            with self.subTest(kind=kind),patch.object(recovery,'_owned_requests',return_value=f[8]),\
                    self.assertRaises(ValueError):
                recovery._capacity_requests(f[0],f[3],projected,base_mode=True)


class IndependentBlockedCountProofs(unittest.TestCase):
    """Real pack/hash reader with invented saved transport, not HTTP execution."""
    def fixture(self):
        temporary=tempfile.TemporaryDirectory(prefix='input21-blocked-proof-')
        self.addCleanup(temporary.cleanup);root=Path(temporary.name).resolve()
        attempt=root/'attempts/edgar-population-20261016-21';author=attempt/'roles/author-01'
        author.mkdir(parents=True)
        runtime={'limits':{'author':{'max_input_tokens':64000}},
            'rates':{'api_model':'gpt-6.1-sol'},'role_efforts':{'author':'high'}}
        author_input={'public_failed_delta':'INERT_ORIGINAL20_PATCH',
            'implementation_base_source_text':'inert-original18-base '*1600}
        request={'model':'gpt-6.1-sol','reasoning':{'effort':'high'},'instructions':'Original instructions',
            'tools':[],'tool_choice':'auto','input':[{'role':'user','content':json.dumps(author_input)}]}
        fields={k:{'type':'string'}for k in ('decision_sha256','comparison_parent_source_sha256',
            'implementation_base_source_sha256','test_text')}
        fields['edits']={'type':'array','items':{'type':'object','properties':{
            k:{'type':'string'}for k in ('kind','old_text','new_text')},
            'required':['kind','old_text','new_text'],'additionalProperties':False}}
        request['text']={'format':_format('earnings_population_delta_author_v2',fields)}
        completion=dict(deepcopy(request),instructions='Original instructions; final declaration',tool_choice='none')
        context=save(attempt/'context-author.json',{'synthetic_context':True,'limits':runtime['limits']['author']})
        class SavedTransport:
            calls=0
            def post(inner,endpoint,payload):
                if endpoint!='/v1/responses/input_tokens':raise AssertionError('Only count fixture')
                inner.calls+=1;stem=author/f'http-count-{inner.calls:02d}'
                value={'input_tokens':67013 if payload.get('tool_choice')=='none' else 66307,
                    '_request_id':f'synthetic-{inner.calls:02d}'}
                save(Path(str(stem)+'.intent.json'),{'endpoint':endpoint,'payload':deepcopy(payload),'retry_allowed':False})
                save(Path(str(stem)+'.response.json'),value)
                save(Path(str(stem)+'.raw.bin'),{k:v for k,v in value.items() if k!='_request_id'})
                return value
        client=SavedTransport()
        with self.assertRaises(BudgetStop):
            packing.pack(client,request,runtime['limits']['author'],author,3,completion_request=completion)
        self.assertEqual(client.calls,2)
        for number in (1,2):
            save(author/f'http-generation-{number:02d}.intent.json',
                {'endpoint':'/v1/responses','payload':{'declared_synthetic_completed_generation':number}})
        rows=[{'binding':engine.pin(p),'value':engine.read(engine.pin(p))}
            for p in sorted(author.glob('03-context-[0-9][0-9].json'))]
        counts=[{'binding':engine.pin(p),'input_tokens':engine.read(engine.pin(p))['input_tokens']}
            for p in sorted(author.glob('03-context-*-count.json'))]
        delivery={'author_terminal':{'failed_turn03_contexts':rows,'failed_turn03_counts':counts}}
        result={'status':'FAILED_NO_RETRY','error_type':'BudgetStop','turns':3,
            'final_numbered_response':'02-response.json','retry_allowed':False}
        reader=recovery.history._Reader(root,root/'synthetic-budget.sqlite3',root/'repo',attempt.name)
        return dict(root=root,attempt=attempt,author=author,runtime=runtime,author_input=author_input,
            delivery=delivery,result=result,reader=reader,source_context=context)

    def check(self,f):
        return recovery._input_capacity_diagnosis(f['reader'],f['attempt'],f['runtime'],
            f['result'],f['author_input'],delivery=f['delivery'])

    def test_original64k_diagnosis_survives_current96k_without_new_generation_or_patch(self):
        f=self.fixture();before=deepcopy(f['author_input']);value=self.check(f)
        self.assertEqual(value['schema'],'earnings_population_input_delivery_diagnosis_v1')
        self.assertEqual(value['mode'],recovery.AUTHOR_INPUT_CAPACITY)
        self.assertEqual(value['input_limit'],64000);self.assertEqual(resources.role_limits()['author']['max_input_tokens'],96000)
        self.assertEqual(value['observed_input_tokens'],[66307,67013])
        self.assertEqual(value['completed_generations'],2);self.assertEqual(value['blocked_turn'],3)
        self.assertEqual(value['source_context'],f['source_context'])
        self.assertFalse(value['candidate_created']);self.assertEqual(value['score_state'],'unscored')
        self.assertFalse(set(value)&{'public_failed_delta','source_text','test_text'})
        self.assertEqual(f['author_input'],before)
        for row in value['count_originals']:
            self.assertEqual(f['reader'].read(row['count'])['input_tokens'],row['input_tokens'])
        self.assertFalse((f['author']/'03-request.json').exists())

    def test_wrong_count_source_binding_model_effort_or_initial_packet_refused(self):
        for kind in ('count-summary','count-bool','context-bytes','model','effort','first-user','foreign-context'):
            f=self.fixture();row=f['delivery']['author_terminal']['failed_turn03_contexts'][0]
            if kind=='count-summary':f['delivery']['author_terminal']['failed_turn03_counts'][0]['input_tokens']+=1
            elif kind=='count-bool':
                counted=f['delivery']['author_terminal']['failed_turn03_counts'][0]
                counted['binding']=save(Path(counted['binding']['path']),{'input_tokens':True})
            elif kind=='context-bytes':Path(row['binding']['path']).write_bytes(Path(row['binding']['path']).read_bytes()+b' ')
            elif kind=='foreign-context':row['binding']=dict(row['binding'],path=str(f['root']/'foreign.json'))
            else:
                path=f['author']/'http-count-01.intent.json';intent=engine.read(engine.pin(path))
                if kind=='model':intent['payload']['model']='wrong-model'
                elif kind=='effort':intent['payload']['reasoning']['effort']='max'
                else:intent['payload']['input'][0]['content']=json.dumps({'wrong':'same public origin not retained'})
                save(path,intent)
                prep=deepcopy(row['value']);prep['effective_request_sha256']=hashlib.sha256(packing.encoded(intent['payload'])).hexdigest()
                row['binding']=save(Path(row['binding']['path']),prep);row['value']=prep
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.check(f)

    def test_generated_third_turn_duplicate_count_missing_row_and_fitting_count_refused(self):
        for kind in ('request3','intent3','duplicate-count','missing-count','fitting','wrong-error'):
            f=self.fixture();author=f['author'];terminal=f['delivery']['author_terminal']
            if kind=='request3':save(author/'03-request.json',{'fake_generation':True})
            elif kind=='intent3':save(author/'http-generation-03.intent.json',{'endpoint':'/v1/responses'})
            elif kind=='duplicate-count':save(author/'http-duplicate.intent.json',engine.read(engine.pin(author/'http-count-01.intent.json')))
            elif kind=='missing-count':terminal['failed_turn03_counts'].pop()
            elif kind=='wrong-error':f['result']['error_type']='ValueError'
            else:
                terminal['failed_turn03_counts'][0]['binding']=save(Path(terminal['failed_turn03_counts'][0]['binding']['path']),{'input_tokens':64000})
                terminal['failed_turn03_counts'][0]['input_tokens']=64000
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.check(f)


class IndependentInputCompositionAdversaries(unittest.TestCase):
    """Original producer helpers; historical full-loader proofs remain seams."""
    def fixture(self):
        prior=base_fixture.ChainedOriginProducerAdversaries();prior.setUp();self.addCleanup(prior.doCleanups)
        proof=IndependentBlockedCountProofs();f=proof.fixture();self.addCleanup(proof.doCleanups)
        diagnosis=proof.check(f)
        diagnosis.update(failed_attempt=save(prior.root/'attempts/edgar-population-20261016-21/population-run-failure.json',
                {'synthetic':'verified input21 boundary'}),audit=prior.failure['audit'],
            original_decision=prior.failure['original_decision'],
            original_scientific_decision_sha256=prior.failure['original_scientific_decision_sha256'])
        return prior,diagnosis

    def test_input21_adds_only_numeric_diagnosis_and_latest_pointer_preserving20_raw_and18_pool(self):
        prior,diagnosis=self.fixture();before=deepcopy(prior.verified20)
        actual=recovery._attach_input_capacity(prior.verified20,diagnosis)
        self.assertEqual(prior.verified20,before)
        retained=deepcopy(actual['recovery_context']);self.assertEqual(retained.pop('input_delivery_diagnosis'),diagnosis)
        self.assertEqual(retained,before['recovery_context'])
        self.assertEqual(actual['recovery_context']['public_failed_delta'],prior.failure['public_failed_delta'])
        self.assertEqual(actual['recovery_context']['implementation_base'],prior.failure['implementation_base'])
        for key in ('population','previous_result','reference_candidate','feedback','last_scored_feedback'):
            self.assertEqual(actual[key],before[key])
        self.assertEqual(recovery.latest_failed_attempt(actual),diagnosis['failed_attempt'])
        self.assertNotEqual(recovery.latest_failed_attempt(actual),actual['recovery_context']['failed_attempt'])
        result=recovery.latest_failed_attempt(actual);result['sha256']='f'*64
        self.assertEqual(recovery.latest_failed_attempt(actual),diagnosis['failed_attempt'])
        with self.assertRaises(ValueError):
            recovery._attach_input_capacity(prior.verified20,dict(diagnosis,mode=recovery.AUTHOR_BASE_CAPACITY))

    def test_new_source_failure22_supersedes_input21_pointer_and_retains_two_compact_lessons(self):
        prior,diagnosis=self.fixture();input21=recovery._attach_input_capacity(prior.verified20,diagnosis)
        failure22=deepcopy(prior.failure)
        failure22['failed_attempt']=save(prior.root/'attempts/edgar-population-20261016-22/population-run-failure.json',
            {'synthetic':'verified source22 boundary'})
        actual=recovery._attach_capacity_failure(input21,failure22)
        self.assertEqual(recovery.latest_failed_attempt(actual),failure22['failed_attempt'])
        self.assertNotIn('input_delivery_diagnosis',actual['recovery_context'])
        self.assertEqual(len(actual['delivery_lessons']),2)
        self.assertEqual({row['failed_attempt']['path'] for row in actual['delivery_lessons']},
            {prior.failure['failed_attempt']['path'],diagnosis['failed_attempt']['path']})
        self.assertNotIn('TOKEN_00',json.dumps(actual['delivery_lessons']))
        self.assertFalse(any(set(row)&{'public_failed_delta','source_text','test_text'} for row in actual['delivery_lessons']))

    def test_repeated_input_stop_keeps_current20_patch_but_compacts_old21_input_diagnosis(self):
        prior,diagnosis=self.fixture();first=recovery._attach_input_capacity(prior.verified20,diagnosis)
        next_diagnosis=deepcopy(diagnosis)
        next_diagnosis['failed_attempt']=save(prior.root/'attempts/edgar-population-20261016-22/population-run-failure.json',
            {'synthetic':'verified later input22 boundary'})
        second=recovery._attach_input_capacity(first,next_diagnosis)
        self.assertEqual(recovery.latest_failed_attempt(second),next_diagnosis['failed_attempt'])
        self.assertEqual(second['recovery_context']['public_failed_delta'],prior.failure['public_failed_delta'])
        self.assertEqual(len(second['delivery_lessons']),2)
        all_lessons=completed._delivery_lessons(second)
        self.assertEqual(len(all_lessons),3)
        self.assertEqual(completed._delivery_lessons({'delivery_lessons':all_lessons}),all_lessons)
        self.assertNotIn('TOKEN_00',json.dumps(all_lessons));self.assertNotIn('CASES=',json.dumps(all_lessons))

    def test_numeric_input_lesson_rejects_raw_bodies_bool_counts_wrong_limit_and_conflicts(self):
        prior,diagnosis=self.fixture();origin=recovery._attach_input_capacity(prior.verified20,diagnosis)
        lessons=completed._delivery_lessons(origin)
        for kind in ('body','bool','fitting','completed','relative','hash','conflict'):
            corrupt=deepcopy(lessons);row=next(r for r in corrupt if r['mode']==recovery.AUTHOR_INPUT_CAPACITY)
            if kind=='body':row['public_failed_delta']=prior.failure['public_failed_delta']
            elif kind=='bool':row['blocked_turn']=True
            elif kind=='fitting':row['observed_input_tokens'][0]=row['input_limit']
            elif kind=='completed':row['completed_generations']=3
            elif kind=='relative':row['source_context']=dict(row['source_context'],path='relative.json')
            elif kind=='hash':row['original_scientific_decision_sha256']='bad'
            else:corrupt.append(dict(row,observed_input_tokens=[90000]))
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                completed._delivery_lessons({'delivery_lessons':corrupt})

    def test_next_origin_replays_latest21_and_refuses_stale20_saved_origin(self):
        prior,diagnosis=self.fixture();origin=recovery._attach_input_capacity(prior.verified20,diagnosis)
        prior.resumed['prior_failed_attempt']=diagnosis['failed_attempt'];prior.refresh(origin=origin)
        with patch.object(recovery,'load',return_value=deepcopy(origin)) as loader:
            self.assertEqual(prior.origin(),origin)
        self.assertEqual(loader.call_args.args[0],diagnosis['failed_attempt'])
        prior.refresh(origin=prior.verified20)
        with patch.object(recovery,'load',return_value=deepcopy(origin)),self.assertRaises(ValueError):prior.origin()

    def test_actual_prepare_producer_saves21_pointer_not20_patch_origin(self):
        holder=preparation_fixture.CapacityPreparationTests();f,origin,_,fixed,_=holder.fixture()
        self.addCleanup(holder.doCleanups)
        _,diagnosis=self.fixture()
        failure20=save(f.owned/'attempts/edgar-population-20261016-20/population-run-failure.json',{'synthetic':'source20'})
        failure21=save(f.owned/'attempts/edgar-population-20261016-21/population-run-failure.json',{'synthetic':'input21'})
        origin['recovery_context'].update(failed_attempt=failure20,public_failed_delta={'synthetic':'exact retained20'})
        diagnosis['failed_attempt']=failure21
        origin=recovery._attach_input_capacity(origin,diagnosis)
        run=preparation_fixture.run
        with patch.object(recovery,'load',return_value=deepcopy(origin)),\
             patch.object(preparation_fixture.rejection,'PARENT',fixed['id']),\
             patch.object(preparation_fixture.admission,'scientific_contract',return_value={'synthetic_contract':True}),\
             patch.object(run,'_feedback_contract_fields',return_value={'initial_feedback_contract_sha256':'d'*64}):
            bound=run.prepare('edgar-population-20261016-22',recover_from=failure21['path'],company_count=1)
        value=engine.read(bound);study=engine.read(value['forecast_study'])
        resumed=engine.read(study['campaign_resume'])
        self.assertEqual(resumed['prior_failed_attempt'],failure21)
        self.assertEqual(engine.read(study['campaign_origin']),origin)
        self.assertEqual(engine.read(value['initial_population']),origin['population'])
        self.assertIsNone(resumed['repair']);self.assertNotIn('reuse_mode',resumed)


class IndependentInputRecursionGuard(unittest.TestCase):
    """Actual public guard; full closure/recovery dispatcher is a fixture."""
    def test_input_route_cycle_depth_and_exception_reset_use_existing_guard(self):
        f=base_fixture.ConsecutiveFailureDispatchAdversaries();f.setUp();self.addCleanup(f.doCleanups)
        for kind in ('cycle','depth'):
            calls=[]
            def transfer(binding,**kwargs):
                self.assertIs(kwargs.get('input_mode'),True)
                calls.append(binding)
                if len(calls)>=51:return {'fixture':'missing guard hard stop'}
                return f.call(binding if kind=='cycle' else f.binding(len(calls)+1))
            with self.subTest(kind=kind),\
                 patch.object(recovery,'_read_plan',return_value={'recovery_mode':recovery.AUTHOR_INPUT_CAPACITY}),\
                 patch.object(recovery,'_load_author_capacity',side_effect=transfer):
                with self.assertRaises(ValueError):f.call(f.binding(1))
            self.assertLessEqual(len(calls),1 if kind=='cycle' else 50)
        with patch.object(recovery,'_read_plan',return_value={'recovery_mode':recovery.AUTHOR_INPUT_CAPACITY}),\
             patch.object(recovery,'_load_author_capacity',return_value={'fresh':'independent fixture'}):
            self.assertEqual(f.call(f.binding(1)),{'fresh':'independent fixture'})


class Independent96kHistoryBridge(unittest.TestCase):
    """Original metadata join over an existing invented scored-history fixture."""
    def test_only_exact_declared_input_and_wall_bridges_preserve_full_scored_contract(self):
        f=history_fixture.HistoryBridgeTests();f.setUp();self.addCleanup(f.doCleanups)
        admission=history_fixture.admission
        # Add a fixed scorer identity so an allowed resource transition cannot
        # silently waive it. No actual scorer/data body is read or executed.
        f.current['scorer']={'fixed':'original'};f.historical['scorer']={'fixed':'original'}
        for old_walls,new_walls in ((False,False),(False,True),(True,True)):
            for before,after in ((48000,64000),(48000,96000),(64000,96000)):
                old=deepcopy(f.current if old_walls else f.historical)
                new=deepcopy(f.current if new_walls else f.historical)
                old['limits']['author']['max_input_tokens']=before
                new['limits']['author']['max_input_tokens']=after
                origin=f.origin_for_contract(old);saved=Path(origin['last_scored_feedback']['path']).read_bytes()
                with self.subTest(old_walls=old_walls,new_walls=new_walls,before=before,after=after):
                    self.assertEqual(admission.last_scored_contract_sha256(origin,new),digest(old))
                    self.assertEqual(Path(origin['last_scored_feedback']['path']).read_bytes(),saved)
                    self.assertEqual(engine.read(origin['last_scored_feedback'])['results'],f.original_scored_feedback['results'])
        for before,after in ((96000,64000),(96000,48000),(64000,48000),(48001,96000),
                (40000,96000),(48000,96001),(64000,96001),(96000,128000),
                (48000,96000.0),(64000.0,96000),(True,96000)):
            old=deepcopy(f.current);new=deepcopy(f.current)
            old['limits']['author']['max_input_tokens']=before;new['limits']['author']['max_input_tokens']=after
            origin=f.origin_for_contract(old)
            with self.subTest(before=before,after=after),self.assertRaises(ValueError):
                admission.last_scored_contract_sha256(origin,new)
        old=deepcopy(f.current);old['limits']['author']['max_input_tokens']=48000
        origin=f.origin_for_contract(old)
        for role,key,value in (('author','max_output_tokens',49153),('author','wall_seconds',1201),
                ('author','wall_seconds',1200.0),('controller','max_input_tokens',32001),
                ('review','wall_seconds',True),('forecast','max_input_tokens',100001),
                ('forecast','max_output_tokens',25001),('forecast','wall_seconds',1801)):
            new=deepcopy(f.current);new['limits']['author']['max_input_tokens']=96000
            new['limits'][role][key]=value
            with self.subTest(role=role,key=key),self.assertRaises(ValueError):
                admission.last_scored_contract_sha256(origin,new)
        for key in ('data','model','scorer','undeclared_waiver'):
            new=deepcopy(f.current);new['limits']['author']['max_input_tokens']=96000
            new[key]={'fixed':'changed'}
            with self.subTest(key=key),self.assertRaises(ValueError):
                admission.last_scored_contract_sha256(origin,new)


if __name__=='__main__':unittest.main()
