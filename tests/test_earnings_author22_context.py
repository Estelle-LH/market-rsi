"""Author22 public evidence delivery; all token counts and HTTP are invented.

The archived source is read as inert text, never imported or executed. The
original public filing is copied to an owned fixture; no financial QA is read.
"""
from copy import deepcopy
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
import subprocess
from types import SimpleNamespace
import unittest
from unittest import mock

import earnings_open_broker as brokers
import earnings_open_context as context
import earnings_open_resources as resources
import earnings_open_roles as roles
import earnings_open_author_followthrough as flow
import earnings_open_fresh_grant as fresh
import earnings_capacity_runtime as runtime_module
from edgar_forecast_budget import BudgetStop, PilotBudget
from edgar_forecast_openai import budgeted_response
from earnings_entry import ReceiptHTTP
from earnings_loop_policy import LIMITS
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_roles as role_fixture
import test_earnings_author20_followthrough as historical_fixture
import test_earnings_controller_headroom as headroom_fixture


REPO=Path(__file__).resolve().parents[1]
LOGICAL='filings/10-Q_2025-02-12_0000003545-25-000030.md'
PUBLIC=Path('/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/edgar-model-scoring-20261007/pilot-01/visible/CIK0000003545')/LOGICAL
REFERENCE=REPO/'configs/earnings_coevolution/program_archive/edgar-research-20261015-18/researcher.py'
REFERENCE_SHA='ef007c3b5a0366d6406c113aea1293c9d4d44ec310249febf727e9e5fbb2ea0c'
BODY_SHA='78691775d1343e907c91b79c263e6fd7b635e4212a6db28b51096c22cc410ad7'
HISTORICAL22='58708dc677d3898b63806451cc0a299c2050a874'


def historical22(name):
    """Four explicitly authorized inert snapshots, never current24 fixtures."""
    if name not in {'configs/earnings_coevolution/author_followthrough_context.json',
            'configs/earnings_coevolution/author_followthrough_scope.json',
            'configs/earnings_coevolution/research_followup_authority.json','tools/earnings_open_resources.py'}:
        raise ValueError('Unapproved historical22 fixture path')
    return subprocess.run(['git','show',HISTORICAL22+':'+name],cwd=REPO,
        check=True,capture_output=True).stdout


def sha(value): return hashlib.sha256(value).hexdigest()
def call(token,name,args):
    return {'type':'function_call','call_id':token,'name':name,'arguments':json.dumps(args)}
def output(token,value):
    return {'type':'function_call_output','call_id':token,'output':json.dumps(value,sort_keys=True,ensure_ascii=False)}
def message(text): return {'type':'message','role':'assistant','content':[{'type':'output_text','text':text}]}
def outputs(request):
    items=request['input']
    if len(items)==2 and items[1].get('role')=='user':
        items=json.loads(items[1]['content'])['records']
    return {row['call_id']:row['output'] for row in items if row.get('type')=='function_call_output'}


class Author22ContextTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='invented-author22-')
        self.addCleanup(temp.cleanup); self.root=Path(temp.name).resolve()
        self.source=REFERENCE.read_text(); self.filing=PUBLIC.read_text()
        self.assertEqual(sha(REFERENCE.read_bytes()),REFERENCE_SHA)
        self.assertEqual(sha(self.filing[22000:32000].encode()),BODY_SHA)
        self.body=self.filing[22000:32000]
        files={'questions.md':'### T001 | Invented target, no answer',
            'filing_index.tsv':'date_filed\tform_type\taccession\tpath\n2025-02-12\t10-Q\t0000003545-25-000030\t'+LOGICAL+'\n',
            LOGICAL:self.filing}
        company={'visible_root':str(self.root/'visible'),'target_accession':'invented-hidden-target',
            'cutoff':'2025-06-01','allowed_files':[]}
        for name,text in files.items():
            path=self.root/'visible'/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text)
            company['allowed_files'].append({'path':name,'sha256':sha(text.encode()),'bytes':len(text.encode())})
        brief={'schema':'earnings_repair_context_v1','human_task':'Inspect the public reference and table.',
            'prior_candidate':{'axis':'R','source':engine.pin(REFERENCE),'source_delivery':'paged_reference'},
            'observations':{'actual_original_read_locations':[{'tool':'read_file','arguments':{
                'path':LOGICAL,'offset':22000,'characters':10000}}]},
            'verification':['Public provenance only.'],'non_claims':['No model discovery or predictive improvement claim.']}
        self.runner=mock.Mock(); self.literature=mock.Mock(); self.capacity=mock.Mock()
        self.broker=brokers.ResearchBroker(self.root/'broker',company=company,capacity=self.capacity,
            runner=self.runner,literature=self.literature,trace_slots={},
            research_context_binding=engine.save(self.root/'brief.json',brief))
        self.initial={'role':'user','content':json.dumps({'research_context':self.broker.research_context(include_source=True)})}
        fields={name:{'type':'string'} for name in ('decision_sha256','source_text','test_text')}
        self.request={'model':'gpt-6.1-sol','reasoning':{'effort':'high'},'instructions':'Exact Author instruction',
            'tools':deepcopy(self.broker.definitions),'parallel_tool_calls':False,'tool_choice':'auto',
            'text':{'format':{'type':'json_schema','name':'earnings_open_author_v1','strict':True,
                'schema':{'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}}},
            'input':[deepcopy(self.initial),{'type':'reasoning','id':'invented-opaque-id','encrypted_content':'INERT_CARRIER_'*3000},
                call('old','search_files',{'query':'invented','path_prefix':'filings/','max_hits':1}),
                output('old',{'text':'OLD_GENERIC_'*1600}),message('Already consumed.') ]}
        self.pages={}
        for index,offset in enumerate(range(0,len(self.source),6000)):
            token=f'page-{index}'; args={'offset':offset,'characters':6000}
            value=self.broker.dispatch('read_reference_program',args)
            self.pages[token]=value
            self.request['input'].extend([call(token,'read_reference_program',args),output(token,value),message('Page delivered.')])
        self.request['input'].extend([call('later','calculate',{'expression':'1+1'}),output('later',{'value':2})])
        self.limits=resources.role_limits()['author']

    def assert_evidence(self,request):
        self.assertEqual(request['input'][0],self.initial)
        evidence=json.loads(request['input'][0]['content'])['research_context']['initial_original_evidence']
        self.assertEqual(evidence['result']['value']['text'],self.body)
        self.assertEqual(evidence['provided_by'],'harness_preparation_not_model_tool_choice')
        self.assertEqual(evidence['source_sha256'],sha(self.filing.encode()))
        engine.read(evidence['result']['research_receipt'])
        actual=outputs(request)
        for token,value in self.pages.items(): self.assertEqual(json.loads(actual[token]),value)
        reconstructed=''.join(json.loads(actual[token])['value']['text'] for token in self.pages)
        self.assertEqual(reconstructed,self.source)
        self.assertEqual(sha(reconstructed.encode()),REFERENCE_SHA)

    def test_author_only_capacity_and_reference_pages_original_table_verified(self):
        self.assertEqual(self.limits,{'max_input_tokens':24000,'max_output_tokens':49152,'wall_seconds':900})
        self.assertEqual(resources.role_limits()['controller'],dict(LIMITS,max_input_tokens=16000))
        self.assertEqual(resources.role_limits()['review'],LIMITS); self.assertEqual(LIMITS['max_input_tokens'],10000)
        self.assertEqual(len(self.pages),4); self.assertNotIn('source_text',json.loads(self.initial['content'])['research_context']['prior_candidate'])
        self.assert_evidence(self.request)
        self.runner.run.assert_not_called(); self.capacity.resolve.assert_not_called(); self.literature.dispatch.assert_not_called()

    def test_ordinary_projection_keeps_all_old_pages_after_calculate_and_exact_hash_receipts(self):
        before=deepcopy(self.request); client=mock.Mock()
        client.post.side_effect=[{'input_tokens':24001},{'input_tokens':16000}]
        selected=context.pack(client,self.request,self.limits,self.root,1)
        self.assert_evidence(selected); self.assertTrue(json.loads(outputs(selected)['old'])['truncated'])
        self.assertEqual(self.request,before)
        self.assertEqual(selected['input'][1],before['input'][1])
        self.assertEqual({k:v for k,v in selected.items() if k!='input'},{k:v for k,v in before.items() if k!='input'})
        receipt=json.loads((self.root/'01-context-02.json').read_bytes())
        expected={token:sha(text.encode()) for token,text in outputs(before).items() if token in self.pages or token=='later'}
        self.assertEqual({row['call_id']:row['original_output_sha256'] for row in receipt['preserved_observations']},expected)
        self.assertEqual([row['call_id'] for row in receipt['projections']],['old'])

    def test_final_and_early_fourth_snapshot_keep_all_pages_and_table_together(self):
        for turn,early in ((2,False),(3,True)):
            request=deepcopy(self.request)
            if not early: request['tool_choice']='none'
            completion=dict(deepcopy(request),tool_choice='none',instructions=request['instructions']+' Complete now.')
            client=mock.Mock(); client.post.side_effect=[{'input_tokens':n} for n in (30000,28000,25000,16000)]
            selected=context.pack(client,request,self.limits,self.root,turn,author_final=not early,
                completion_request=completion if early else None)
            self.assert_evidence(selected); self.assertEqual(client.post.call_count,4)
            self.assertEqual(selected['tool_choice'],'none'); self.assertNotIn('INERT_CARRIER_',json.dumps(selected))
            receipt=json.loads((self.root/f'{turn:02d}-context-04.json').read_bytes())
            self.assertEqual(receipt['projection_policy'],'author_final_public_snapshot_v1')
            self.assertEqual(receipt['effective_request_sha256'],sha(context.encoded(selected)))
            self.assertEqual(receipt.get('early_finalization',False),early)
            if early: self.assertEqual(receipt['finalization_request_sha256'],sha(context.encoded(completion)))

    def test_controller_and_default_projection_do_not_gain_reference_preservation(self):
        plain,_=context.project(self.request,100)
        self.assertTrue(all(json.loads(outputs(plain)[token])['truncated'] for token in self.pages))
        request=deepcopy(self.request); request['text']['format']['name']='earnings_open_decision_v1'
        self.assertEqual(context.author_preserved_outputs(request),frozenset())
        client=mock.Mock(); client.post.side_effect=[{'input_tokens':24001},{'input_tokens':9000}]
        selected=context.pack(client,request,LIMITS,self.root,4)
        self.assertTrue(all(json.loads(outputs(selected)[token])['truncated'] for token in self.pages))
        self.assertEqual(selected['input'][0],self.initial)

    def test_unfit24001_and_narrow10000_stop_without_generation_or_retry(self):
        for turn,limit,count in ((5,24000,24001),(6,10000,15561)):
            request=dict(deepcopy(self.request),tool_choice='none'); client=mock.Mock()
            client.post.return_value={'input_tokens':count}
            with self.assertRaises(BudgetStop):
                context.pack(client,request,dict(self.limits,max_input_tokens=limit),self.root,turn,author_final=True)
            self.assertEqual(client.post.call_count,4)
            for called in client.post.call_args_list:
                self.assertEqual(called.args[0],'/v1/responses/input_tokens'); self.assert_evidence(called.args[1])
        self.assertFalse(list(self.root.glob('*-request.json')))

    def test_token_failure_once_and_initial_packet_never_compacted(self):
        client=mock.Mock(); client.post.side_effect=TimeoutError('Invented count failure')
        with self.assertRaises(TimeoutError):context.pack(client,self.request,self.limits,self.root,7)
        self.assertEqual(client.post.call_count,1)
        self.assertFalse(list(self.root.glob('07-request.json')))

    def test_stock24001_recount_refuses_before_reservation_and_Author24001_context_refused(self):
        client=mock.Mock(); client.post.return_value={'input_tokens':24001}
        transport=ReceiptHTTP(client,self.root)
        budget=PilotBudget(self.root/'invented-overflow.sqlite3'); self.addCleanup(budget.close)
        rates={'api_model':self.request['model'],'effort':'high','input':'2','cached':'.1','write':'2.5','output':'10'}
        with self.assertRaises(BudgetStop):
            budgeted_response(transport,self.request,rates,self.limits,budget,self.root,9)
        self.assertEqual(client.post.call_count,1)
        self.assertEqual(client.post.call_args.args[0],'/v1/responses/input_tokens')
        self.assertEqual(budget.db.execute('SELECT status FROM requests').fetchall(),[])
        f=role_fixture.OpenRoleTests(); f.setUp(); self.addCleanup(f.doCleanups)
        with self.assertRaises(ValueError):
            f.service(author=True,limits=dict(self.limits,max_input_tokens=24001))
        f.factory.assert_not_called()
        fresh=role_fixture.OpenRoleTests(); fresh.setUp(); self.addCleanup(fresh.doCleanups)
        narrow=fresh.service(author=True,limits=dict(self.limits,max_input_tokens=10000))
        self.assertEqual(narrow.context['limits']['max_input_tokens'],10000)

    def test_exact24000_stock_count_reservation_and_physical_payload_join(self):
        calls=[]; counts=iter((24001,24000,24000)); before=deepcopy(self.request)
        class Client:
            def post(inner,endpoint,payload):
                calls.append((endpoint,deepcopy(payload)))
                if endpoint.endswith('input_tokens'):return {'input_tokens':next(counts)}
                return {'model':before['model'],'service_tier':'default','status':'completed','error':None,'output':[],
                    'usage':{'input_tokens':24000,'output_tokens':7,'total_tokens':24007,'input_tokens_details':{'cached_tokens':0}}}
        transport=ReceiptHTTP(Client(),self.root); selected=context.pack(transport,self.request,self.limits,self.root,8)
        budget=PilotBudget(self.root/'invented.sqlite3'); self.addCleanup(budget.close)
        rates={'api_model':before['model'],'effort':'high','input':'2','cached':'.1','write':'2.5','output':'10'}
        budgeted_response(transport,selected,rates,self.limits,budget,self.root,8)
        self.assertEqual([endpoint for endpoint,_ in calls],['/v1/responses/input_tokens']*3+['/v1/responses'])
        self.assertEqual(calls[1][1],selected); self.assertEqual(calls[2][1],selected)
        self.assertEqual(json.loads((self.root/'08-request.json').read_bytes())['payload'],selected)
        self.assertEqual(calls[-1][1],dict(selected,max_output_tokens=49152,service_tier='default',store=False))
        self.assert_evidence(calls[-1][1]); self.assertEqual(budget.db.execute('SELECT status FROM requests').fetchall(),[('settled',)])
        self.assertEqual(budget.summary()['unresolved_reserved_usd'],0); self.assertEqual(self.request,before)

    def test_actual_OpenAuthor_loop_reads_four_pages_then_calculates_with_full_evidence(self):
        f=role_fixture.OpenRoleTests(); f.setUp(); self.addCleanup(f.doCleanups); f.broker=self.broker
        chosen=f.choice('R'); service=f.service(author=True,max_turns=4,limits=self.limits)
        page_calls=[f.call(token,'read_reference_program',{'offset':i*6000,'characters':6000}) for i,token in enumerate(self.pages)]
        f.generations=[f.tool_response(*page_calls),f.tool_response(f.call('calc-1','calculate',{'expression':'1+1'})),
            f.tool_response(f.call('calc-2','calculate',{'expression':'2+2'})),f.message({'decision_sha256':digest(chosen),
                'source_text':"PROGRAM={'axis':'R'}\ndef run(p): return {}\n",'test_text':"CASES=[{'input':{},'expected':{}}]"})]
        f.factory.return_value.post.return_value={'input_tokens':16000}
        with mock.patch.object(roles,'budgeted_response',side_effect=f.fake_paid):
            service.author(chosen,{'axis':'R'},str(f.slot))
        effective=json.loads((f.slot/'effective-input.json').read_bytes())
        self.assertEqual(json.loads(f.requests[0]['input'][0]['content']),effective)
        self.assertEqual(effective['research_context']['initial_original_evidence']['result']['value']['text'],self.body)
        self.assertNotIn('source_text',effective['research_context']['prior_candidate'])
        for request in f.requests[1:]:
            self.assertEqual(json.loads(request['input'][0]['content']),effective)
            actual=outputs(request)
            for token,value in self.pages.items():self.assertEqual(json.loads(actual[token])['value'],value['value'])
        self.assertEqual(len(f.requests),4); self.assertEqual(f.requests[-1]['tool_choice'],'none')
        self.assertEqual(json.loads((f.slot/'result.json').read_bytes())['status'],'COMPLETED_CANDIDATE')
        self.runner.run.assert_not_called(); self.capacity.resolve.assert_not_called(); self.literature.dispatch.assert_not_called()


class Author22EntryTests(unittest.TestCase):
    """Synthetic successor admission, with original source/accounting guards."""
    def setUp(self):
        self.old=historical_fixture.Author20EntryTests(); self.old.setUp(); self.addCleanup(self.old.doCleanups)
        self.root=self.old.root; self.number=0
        self.body=deepcopy(self.old.body)
        self.body['continuation']['successor']={'human_authorization':fresh.AUTHOR22_AUTHORIZATION,
            'author_id':'edgar-research-20261016-22','forecast_id':'edgar-research-20261016-23',
            'author_max_input_tokens':24000,'closed_author_review':deepcopy(fresh.AUTHOR20_CLOSURE)}
        self.scope=deepcopy(self.old.scope())
        self.scope.update(author_id='edgar-research-20261016-22',forecast_id='edgar-research-20261016-23',
            continuation_human_approval=fresh.AUTHOR22_AUTHORIZATION,author_max_input_tokens=24000,
            closed_author_review=deepcopy(fresh.AUTHOR20_CLOSURE))

    def authority(self, *, change=None, body_change=None, closure_change=None, original='961e18a652ad91cbc0494111a435866e6414bdcaf327d028add2673329a7b9c2', source=REFERENCE_SHA):
        self.number+=1; home=self.root/f'scope22-{self.number}'; home.mkdir()
        value=deepcopy(self.scope); value.update(change or {})
        context=deepcopy(self.old.context); context['prior_candidate']['source']['sha256']=source
        context_path=home/'context.json'; binding=engine.save(context_path,context)
        body=deepcopy(self.body); body['continuation']['research_context']=binding
        if body_change: body_change(body)
        policy_path=home/'policy.json'; engine.save(policy_path,body)
        scope_path=home/'scope.json'; engine.save(scope_path,value)
        closure={'verdict':'VERIFIED_AUTHOR20_CONTEXT_FAILURE_AND_ACCOUNTING_NO_RETRY',
            'blocking_findings':[],'reviewer':'independent-synthetic-reviewer'}
        closure.update(closure_change or {})
        def read(bound):
            if bound['path'].endswith('synthetic-author18.json'):return {'original':{'sha256':original}}
            if bound['path'].endswith('synthetic-review18.json'):return {'verdict':'REJECT_AUTHOR_CANDIDATE_ONE_FORECAST'}
            if bound['path']==fresh.AUTHOR20_CLOSURE['path']:return closure
            return engine.read(bound)
        with mock.patch.object(fresh,'CONFIG',policy_path),mock.patch.object(flow,'SCOPE',scope_path),\
                mock.patch.object(flow,'CONTEXT',context_path),mock.patch.object(flow,'read',side_effect=read):
            return flow.authority()

    def test_actual_config22_new_approved_window_keeps_original4955_allocation(self):
        snapshots={}
        for name in ('author_followthrough_context.json','author_followthrough_scope.json','research_followup_authority.json'):
            path=self.root/('historical22-'+name)
            path.write_bytes(historical22('configs/earnings_coevolution/'+name)); snapshots[name]=path
        with mock.patch.object(fresh,'CONFIG',snapshots['research_followup_authority.json']):actual=fresh.policy()
        scope=engine.read(engine.pin(snapshots['author_followthrough_scope.json']))
        self.assertEqual(actual['continuation']['research_context']['sha256'],engine.pin(snapshots['author_followthrough_context.json'])['sha256'])
        self.assertEqual(fresh.AUTHOR22_IDS,('edgar-research-20261016-22','edgar-research-20261016-23'))
        self.assertEqual(fresh.AUTHOR22_AUTHORIZATION,'允许。把 Author 输入上限改到 24k，补多页源码和真实表格同时保留的贯通测试，独立审查通过后用新 ID 跑真实 Author 修复和一个 Alico 预测，验证新版本确实被使用。沿用当前窗口和剩余额度，数据、scorer 和原 $200 总预算不变，每个改动单独提交，失败先诊断、不自动重试，不动其他 Supervisor。')
        window_record=engine.read({'path':str(fresh.ROOT/'AUTHOR22-NEW-WINDOW.json'),
            'sha256':'b945ba17c55d40f05601ade878dd38f147f83226586da3d1de699d8ae257220c'})
        self.assertEqual(actual['window'],window_record['window'])
        self.assertEqual(window_record['old_window'],{'issued_utc':'2026-10-16T03:56:39Z',
            'cutoff_utc':'2026-10-16T05:25:39Z','deadline_utc':'2026-10-16T05:26:39Z'})
        self.assertEqual(window_record['human_authorization'],'允许。确认在途费用已结清、共享运行空闲后，开新的90分钟窗口，用新ID跑真实Author修复，独立审查通过后跑一个Alico预测，验证新版本确实被使用。沿用剩余额度和原$200累计预算，数据、scorer不变，每个改动单独提交并测试，失败先诊断、不自动重试，不动其他Supervisor。')
        self.assertEqual(window_record['original_allocation'],fresh.allocation(actual))
        self.assertEqual(window_record['original_cumulative_cap_nano_usd'],19328538400)
        self.assertFalse(window_record['allocation_reset'])
        self.assertEqual(fresh.allocation(actual)['opening']['max_rowid'],4955)
        self.assertEqual((fresh.allocation(actual)['author_id'],fresh.allocation(actual)['forecast_id']),fresh.AUTHOR20_IDS)
        self.assertEqual(fresh.pilot_cap(actual),19328538400); self.assertEqual(actual['baseline'],fresh.BASELINE)
        self.assertEqual(scope['allocation'],fresh.allocation(actual)); self.assertEqual(scope['window'],actual['window'])
        self.assertEqual(scope['author_max_input_tokens'],24000)
        self.assertEqual(scope['closed_author_review']['sha256'],'b8be511944af87261f772ecee48b6f715594dec77de617aa36bd2df5db511741')

    def test_exact_successor_scope_and_closure_original18_source_pins_required(self):
        self.assertEqual(self.authority(),self.scope)
        for change in ({'author_id':fresh.AUTHOR20_IDS[0],'forecast_id':fresh.AUTHOR20_IDS[1]},
                {'forecast_id':'edgar-research-20261016-24'},{'continuation_human_approval':'unapproved'},
                {'author_max_input_tokens':24001},{'requires_cold_probe':False},
                {'closed_author_review':dict(fresh.AUTHOR20_CLOSURE,sha256='0'*64)},
                {'opening_rows':4808},{'allocation':dict(self.scope['allocation'],max_new_nano_usd=1)}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.authority(change=change)
        for change in ({'reviewer':'Root'},{'reviewer':' '},{'blocking_findings':['problem']},
                {'verdict':'PASS_NOT_CLOSED'}):
            with self.subTest(closure=change),self.assertRaises(ValueError):self.authority(closure_change=change)
        with self.assertRaises(ValueError):self.authority(original='0'*64)
        with self.assertRaises(ValueError):self.authority(source='0'*64)

    def test_successor_strict_fields_closedIDs_and_original_caps_not_rebased(self):
        self.old.f.body=deepcopy(self.body)
        for key,value in (('author_max_input_tokens',24001),('author_max_input_tokens',24000.0),
                ('author_max_input_tokens',True),('author_id',fresh.AUTHOR20_IDS[0]),
                ('forecast_id','edgar-research-20261016-24'),('human_authorization','unapproved'),
                ('closed_author_review',dict(fresh.AUTHOR20_CLOSURE,sha256='0'*64)),('extra',True)):
            body=deepcopy(self.body); body['continuation']['successor'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.old.f.policy(body)
        for identifier in (*fresh.AUTHOR20_IDS,*fresh.AUTHOR22_IDS):
            grant=dict(self.old.f.grant,id=identifier,root=str(self.root/'attempts'/identifier),
                additional_cap_nano_usd=14_500_000_000,
                **{key:self.body['window'][key] for key in ('cutoff_utc','deadline_utc')})
            if identifier in fresh.AUTHOR22_IDS:self.assertEqual(self.old.f.validate(grant),self.body)
            else:
                with self.assertRaises(ValueError):self.old.f.validate(grant)
        def new_opening(body):body['continuation']['allocation']['opening']['max_rowid']+=1
        with self.assertRaises(ValueError):self.authority(body_change=new_opening)
        for key,value in (('original_total_cap_nano_usd',201_000_000_000),
                ('original_per_model_cap_nano_usd',101_000_000_000),('new_subgrant_nano_usd',51_000_000_000)):
            body=deepcopy(self.body); body[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.old.f.policy(body)

    def test_shared80_includes_failed20_21_and_all_predecessors_without_reset(self):
        roots=[('edgar-research-20261015-12',name) for name in ('code','review-code')]
        roots += [('edgar-research-20261015-'+n,name) for n in ('14','16','18') for name in ('code','review-code','cold-probe-code')]
        roots += [('edgar-research-20261015-'+n,'code') for n in ('13','15','17','19')]
        for author,forecast in (fresh.AUTHOR20_IDS,fresh.AUTHOR22_IDS):
            roots += [(author,name) for name in ('code','review-code','cold-probe-code')]+[(forecast,'code')]
        self.assertEqual(len(roots),23)
        for index,(identifier,name) in enumerate(roots):
            directory=self.root/'attempts'/identifier/name; directory.mkdir(parents=True)
            for number in range(13 if index==22 else 3):
                action=directory/f'call-{number:032x}'; action.mkdir()
                engine.save(action/'result.json',{'status':'FAILED_NO_RETRY'})
        with mock.patch.object(flow,'ROOT',self.root),mock.patch.object(flow,'authority',return_value=self.scope):
            self.assertEqual(flow.containers_remaining(),1)
            (self.root/'attempts'/fresh.AUTHOR20_IDS[1]/'code'/('call-'+'f'*32)).mkdir()
            with self.assertRaises(ValueError):flow.containers_remaining()

    def test22_sourceclosure_exact_three_reviewed_Hpins_other_sources_protected(self):
        repo=self.root/'source22'; names=['tools/earnings_open_context.py','tools/earnings_open_resources.py',
            'tools/earnings_open_broker.py','tools/earnings_open_fresh_grant.py',
            'tools/earnings_open_author_followthrough.py','tools/protected.py','configs/scope.json','configs/context.json']
        for name in names:
            path=repo/name; path.parent.mkdir(parents=True,exist_ok=True)
            raw=(historical22(name) if name=='tools/earnings_open_resources.py' else
                ((REPO/name).read_bytes() if (REPO/name).is_file() else b'inert synthetic source'))
            path.write_bytes(raw)
        old={'sources':{name:dict(engine.pin(repo/name),sha256='0'*64) for name in names[:4]}}
        old['sources']['tools/protected.py']=engine.pin(repo/'tools/protected.py')
        with mock.patch.object(flow.e,'REPO',repo),mock.patch.object(flow,'__file__',str(repo/names[4])),\
                mock.patch.object(flow,'SCOPE',repo/'configs/scope.json'),mock.patch.object(flow,'CONTEXT',repo/'configs/context.json'):
            pins=flow.source_bindings(old,scope=self.scope)
            self.assertEqual({name:pins[name]['sha256'] for name in names[:3]},dict(zip(names[:3],[
                'ab025592fab39640422fbcce6ac8e27d7f917d9552ba8fec04d07c3342da7bd8',
                '2f2b646a77067ed72bfeb6f1511f0138de3a891715160f2704c4d04051616d27',
                'a2e6d408037a924d18cb881c404ad9169375ad460424a0375c806ab3316fdc88'])))
            for name in names[:3]+['tools/protected.py']:
                path=repo/name; raw=path.read_bytes(); path.write_bytes(raw+b'\n# synthetic drift')
                with self.subTest(name=name),self.assertRaises(ValueError):flow.source_bindings(old,scope=self.scope)
                path.write_bytes(raw)
            with self.assertRaises(ValueError):flow.source_bindings(old,scope={'author_id':fresh.AUTHOR20_IDS[0]})

    def prepared(self):
        self.old.f.path.write_text(json.dumps(self.body))
        original_limits={'controller':{'max_input_tokens':16000,'max_output_tokens':16384,'wall_seconds':600},
            'author':{'max_input_tokens':10000,'max_output_tokens':32768,'wall_seconds':900},
            'review':deepcopy(LIMITS),'forecast':{'max_input_tokens':10000,'max_output_tokens':1024,'wall_seconds':60}}
        oldgrant=dict(self.old.f.grant,ledger=str(self.root/'unused.sqlite3'),python={'synthetic':True})
        for key in ('data','runtime','qa','scorer','cik'):oldgrant[key]='synthetic-'+key
        oldruntime={'rates':{'api_model':'fixed-model'},'limits':original_limits,
            'role_efforts':{'author':'high','controller':'max','review':'max','forecast':'max'},
            'additional_cap_nano_usd':10_000_000_000,'ledger':oldgrant['ledger'],'baseline':deepcopy(fresh.BASELINE)}
        oldstudy={'cases':[{'synthetic':'unchanged'}],'runtime_config':{'request_timeout_seconds':180},'program_lineage':{'old':True}}
        old={'handoff':{'old_runtime':engine.save(self.root/'old-runtime22.json',oldruntime),
            'old_episode':engine.save(self.root/'old-episode22.json',{'grant':engine.save(self.root/'old-grant22.json',oldgrant),
                'study':engine.save(self.root/'old-study22.json',oldstudy)})}}
        scope_path=self.root/'prepare-scope22.json'; engine.save(scope_path,self.scope)
        trusted=engine.save(self.root/'inert22.json',{'inert':True}); sources={'inert':trusted}
        stack=ExitStack(); self.addCleanup(stack.close)
        for module,name,value in ((flow,'ROOT',self.root),(fresh,'ROOT',self.root),(fresh,'CONFIG',self.old.f.path),(flow,'SCOPE',scope_path),(flow,'CORE',{})):
            stack.enter_context(mock.patch.object(module,name,value))
        for name,value in (('authority',self.scope),('prior',old),('source_bindings',sources)):
            stack.enter_context(mock.patch.object(flow,name,return_value=value))
        for name in ('accounting','verify_current_python','verify_sources'):
            stack.enter_context(mock.patch.object(flow,name))
        stack.enter_context(mock.patch.object(flow.namespace,'native_paths',return_value={}))
        stack.enter_context(mock.patch.object(flow.subprocess,'run',side_effect=[SimpleNamespace(stdout=b''),SimpleNamespace(stdout='c'*40)]))
        stack.enter_context(mock.patch.object(flow,'preflight_runtime',side_effect=engine.read))
        owner=stack.enter_context(mock.patch.object(flow,'open_capacity_runtime'))
        binding=flow.prepare('author'); value=engine.read(binding)
        return value,oldruntime,owner

    def test_actual_prepare_and_validate_only_Author_input_changes_to24k(self):
        value,old,owner=self.prepared(); runtime=engine.read(value['runtime'])
        expected=deepcopy(old['limits']); expected['author']['max_input_tokens']=24000
        self.assertEqual(runtime['limits'],expected)
        self.assertEqual(runtime['role_efforts'],old['role_efforts']); self.assertEqual(runtime['rates'],old['rates'])
        self.assertEqual(runtime['additional_cap_nano_usd'],14_500_000_000)
        self.assertEqual(engine.read(value['grant'])['additional_cap_nano_usd'],14_500_000_000)
        def check(mutator=None):
            self.number+=1; home=self.root/f'prepared-check22-{self.number}'; home.mkdir()
            candidate=deepcopy(value); rr=deepcopy(runtime)
            if mutator:mutator(rr)
            candidate['runtime']=engine.save(home/'runtime.json',rr)
            binding=engine.save(home/'prepared.json',candidate)
            review=engine.save(home/'review.json',{'verdict':'PASS_AUTHOR_FOLLOWTHROUGH_STAGE',
                'blocking_findings':[],'reviewer':'independent-synthetic-reviewer','prepared':binding,'reviewed_sources':candidate['sources']})
            if mutator:
                with self.assertRaises(ValueError):flow.validate_prepared(binding,review)
            else:self.assertEqual(flow.validate_prepared(binding,review),(candidate,rr))
            owner.assert_not_called()
        check()
        for role,key,amount in (('author','max_input_tokens',24001),('author','max_output_tokens',32769),
                ('author','wall_seconds',901),('controller','max_input_tokens',16001),('review','max_input_tokens',10001)):
            with self.subTest(role=role,key=key):check(lambda rr,r=role,k=key,v=amount:rr['limits'][r].__setitem__(k,v))
        check(lambda rr:rr['rates'].__setitem__('api_model','drift'))
        check(lambda rr:rr['role_efforts'].__setitem__('author','max'))

    def test_expired_original_window_blocks_actual_runtime_before_factory_or_owner(self):
        f=headroom_fixture.ControllerHeadroomTests(); f.setUp(); self.addCleanup(f.doCleanups)
        owner,fixture,value=f.preflight()
        value.update(cutoff_utc='2026-10-16T05:25:39Z',deadline_utc='2026-10-16T05:26:39Z')
        bound=engine.save(fixture.home/'expired22-runtime.json',value)
        factories={role:mock.Mock() for role in ('controller','author','review','forecast')}
        with mock.patch.object(runtime_module.time,'time',return_value=runtime_module.utc_epoch('2026-10-16T05:26:40Z')),\
                mock.patch.object(runtime_module,'NightBudget') as budget_factory:
            with self.assertRaisesRegex(BudgetStop,'cutoff'):runtime_module.preflight_runtime(bound)
            with self.assertRaises(BudgetStop):
                with runtime_module.open_capacity_runtime(bound,client_factory=fixture.client_factory,role_factories=factories):pass
            budget_factory.assert_not_called()
        fixture.client_factory.assert_not_called(); self.assertEqual(owner.created,[])
        for factory in factories.values():factory.assert_not_called()

    def test_actual_runtime_preflight_accepts_only_source_bound_Author24k(self):
        f=headroom_fixture.ControllerHeadroomTests(); f.setUp(); self.addCleanup(f.doCleanups)
        owner,fixture,value=f.preflight()
        value['limits']['author']=resources.role_limits()['author']
        bound=engine.save(fixture.home/'author24k-runtime.json',value)
        self.assertEqual(runtime_module.preflight_runtime(bound),value)
        for number,(role,key,amount) in enumerate((('author','max_input_tokens',24001),
                ('author','max_input_tokens',24000.0),('author','max_output_tokens',49153),
                ('author','wall_seconds',901),('controller','max_input_tokens',16001),('review','max_input_tokens',10001))):
            changed=deepcopy(value); changed['limits'][role][key]=amount
            with self.subTest(role=role,key=key,amount=amount),self.assertRaises(ValueError):
                runtime_module.preflight_runtime(engine.save(fixture.home/f'author24k-over-{number}.json',changed))
        changed=deepcopy(value)
        changed['sources']['factory_author']=engine.pin(REPO/'tools/earnings_capacity_assembly.py')
        with self.assertRaises(ValueError):runtime_module.preflight_runtime(engine.save(fixture.home/'foreign-author24k.json',changed))
        fixture.client_factory.assert_not_called(); self.assertEqual(owner.created,[])


if __name__=='__main__':unittest.main()
