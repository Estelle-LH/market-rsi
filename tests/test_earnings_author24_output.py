"""Author-only49k output; invented transport/owned ledgers, no paid inference."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import earnings_open_author_followthrough as flow
import earnings_open_fresh_grant as fresh
import earnings_open_resources as resources
import earnings_open_roles as roles
from earnings_capacity_runtime import _OwnedHTTP
from earnings_loop_policy import LIMITS
from earnings_night_budget import history_snapshot
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_capacity_author_transport as author_fixture
import test_earnings_open_roles as role_fixture
import test_earnings_author24_grant as grant_fixture


class OutputFixture(author_fixture._AuthorFixture):
    def __init__(self,owner,root,output=49152):
        super().__init__(owner,root)
        self.rates['effort']='high'
        context=deepcopy(self.context); context['rates']=deepcopy(self.rates)
        context['limits']={'max_input_tokens':24000,'max_output_tokens':output,'wall_seconds':900}
        self.bind_context(context)
        self.broker=role_fixture.Broker()
        def check(loan):
            pending=self.budget.db.execute("SELECT id,model,reserved FROM requests WHERE status='reserved'").fetchall()
            owner.assertEqual(pending,[] if loan is None else [loan])
        owned=_OwnedHTTP(self.http,check,{slot:context['limits'] for slot in self.slots},self.rates)
        self.factory.side_effect=lambda:owned

    def service(self):
        return roles.OpenAuthor(self.context_binding,budget=self.budget,client_factory=self.factory,
            broker=self.broker,socket_timeout_seconds=900,max_turns=1)

    def public_candidate(self):
        return {'decision_sha256':digest(self.choice()),'source_text':"PROGRAM={'axis':'R'}\ndef run(p): return {}\n",
            'test_text':"CASES=[{'input':{},'expected':{}}]"}


class Author24TransportTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='synthetic-author24-output-'); self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()

    def test_only_Author_output_grows_input_wall_model_effort_and_otherroles_unchanged(self):
        self.assertEqual(resources.role_limits()['author'],{'max_input_tokens':24000,'max_output_tokens':49152,'wall_seconds':900})
        self.assertEqual(resources.role_limits()['controller'],dict(LIMITS,max_input_tokens=16000))
        self.assertEqual(resources.role_limits()['review'],LIMITS)
        self.assertEqual(LIMITS,{'max_input_tokens':10000,'max_output_tokens':16384,'wall_seconds':600})
        self.assertEqual(resources.ROLE_EFFORTS,{'author':'high','controller':'max','review':'max','forecast':'max'})

    def test_actual_stock_count_reserve_send49152_and_settle_exact_same_payload(self):
        f=OutputFixture(self,self.root/'complete')
        f.invoke(f.response(f.public_candidate()),before={'axis':'R'},service=f.service())
        self.assertEqual([endpoint for endpoint,_ in f.calls],['/v1/responses/input_tokens','/v1/responses'])
        counted,physical=[value for _,value in f.calls]
        self.assertEqual(physical,dict(counted,max_output_tokens=49152,service_tier='default',store=False))
        self.assertEqual(counted['model'],'gpt-6.1-sol'); self.assertEqual(counted['reasoning'],{'effort':'high'})
        self.assertEqual(f.rows(),[(20*2500+49152*10000,92800,'settled')])
        slot=Path(f.slots[0]); reserved=json.loads((slot/'01-request.json').read_bytes())
        self.assertEqual(reserved['payload'],counted)
        self.assertEqual(reserved['reserved_nano_usd'],20*2500+49152*10000)
        self.assertEqual(f.budget.summary()['unresolved_reserved_usd'],0)
        self.assertEqual(history_snapshot(f.budget.db,f.baseline['max_rowid']),f.baseline)
        self.assertEqual(json.loads((slot/'result.json').read_bytes())['status'],'COMPLETED_CANDIDATE')
        self.assertEqual(f.broker.calls,[])

    def test_incomplete49152_is_charged_once_not_uncertain_or_automatic_retry(self):
        f=OutputFixture(self,self.root/'incomplete')
        reply=f.response({}); reply.update(status='incomplete',output=[],incomplete_details={'reason':'max_output_tokens'})
        reply['usage'].update(output_tokens=49152,total_tokens=reply['usage']['input_tokens']+49152,
            output_tokens_details={'reasoning_tokens':49152})
        with mock.patch.object(roles,'candidate',side_effect=AssertionError('No public code to parse')) as parse:
            with self.assertRaises(RuntimeError):f.invoke(reply,before={'axis':'R'},service=f.service())
            parse.assert_not_called()
        self.assertEqual(f.rows(),[(20*2500+49152*10000,491542800,'settled')])
        self.assertEqual(len(f.calls),2); self.assertEqual(f.calls[-1][1]['max_output_tokens'],49152)
        self.assertFalse(f.budget.summary()['blocked']); self.assertEqual(f.budget.summary()['unresolved_reserved_usd'],0)
        slot=Path(f.slots[0]); saved=json.loads((slot/'response.json').read_bytes())
        self.assertEqual(saved['status'],'incomplete'); self.assertEqual(saved['output'],[])
        self.assertEqual(json.loads((slot/'result.json').read_bytes())['status'],'FAILED_NO_RETRY')
        self.assertFalse((slot/'candidate.json').exists())
        originals,rows=f.originals(),f.rows()
        with self.assertRaises(FileExistsError):f.invoke(reply,before={'axis':'R'},service=f.service())
        self.assertEqual(f.originals(),originals); self.assertEqual(f.rows(),rows); self.assertEqual(len(f.calls),2)

    def test_above49152_rejected_before_factory_but_narrow32768_stays_narrow(self):
        f=OutputFixture(self,self.root/'too-large',output=49153)
        with self.assertRaises(ValueError):f.service()
        f.factory.assert_not_called(); self.assertEqual(f.rows(),[])
        narrow=OutputFixture(self,self.root/'narrow',output=32768)
        narrow.invoke(narrow.response(narrow.public_candidate()),before={'axis':'R'},service=narrow.service())
        self.assertEqual(narrow.calls[-1][1]['max_output_tokens'],32768)
        self.assertEqual(narrow.rows(),[(20*2500+32768*10000,92800,'settled')])


class Author24EntryTests(unittest.TestCase):
    def setUp(self):
        self.g=grant_fixture.Author24GrantTests(); self.g.setUp(); self.addCleanup(self.g.doCleanups)
        self.base=self.g.old; self.root=self.base.root; self.number=0
        self.body=deepcopy(self.g.body); self.scope=deepcopy(self.base.scope)
        a=fresh.allocation(self.body)
        self.scope.update(author_id=fresh.AUTHOR24_IDS[0],forecast_id=fresh.AUTHOR24_IDS[1],
            continuation_human_approval=fresh.AUTHOR24_AUTHORIZATION,author_max_input_tokens=24000,
            author_max_output_tokens=49152,closed_author_review=deepcopy(fresh.AUTHOR22_CLOSURE),
            allocation=a,opening_rows=a['opening']['max_rowid'],opening_rows_sha256=a['opening']['rows_sha256'],
            continuation_cumulative_cap_nano_usd=fresh.pilot_cap(self.body))

    def authority(self,change=None,closure_change=None):
        self.number+=1; home=self.root/f'authority24-{self.number}'; home.mkdir()
        scope=deepcopy(self.scope); scope.update(change or {})
        context=deepcopy(self.base.old.context); context_path=home/'context.json'; cb=engine.save(context_path,context)
        body=deepcopy(self.body); body['continuation']['research_context']=cb
        policy=home/'policy.json'; engine.save(policy,body)
        sp=home/'scope.json'; engine.save(sp,scope)
        closure={'verdict':'VERIFIED_AUTHOR22_OUTPUT_LIMIT_FAILURE_AND_ACCOUNTING_NO_RETRY',
            'blocking_findings':[],'reviewer':'independent-synthetic-reviewer'}; closure.update(closure_change or {})
        def read(bound):
            if bound['path'].endswith('synthetic-author18.json'):return {'original':{'sha256':'961e18a652ad91cbc0494111a435866e6414bdcaf327d028add2673329a7b9c2'}}
            if bound['path'].endswith('synthetic-review18.json'):return {'verdict':'REJECT_AUTHOR_CANDIDATE_ONE_FORECAST'}
            if bound['path']==fresh.AUTHOR22_CLOSURE['path']:return closure
            return engine.read(bound)
        with mock.patch.object(fresh,'CONFIG',policy),mock.patch.object(flow,'SCOPE',sp),\
                mock.patch.object(flow,'CONTEXT',context_path),mock.patch.object(flow,'read',side_effect=read):
            return flow.authority()

    def test_exact24_25_closed22_independent_review_and_output_override_required(self):
        self.assertEqual(fresh.AUTHOR24_IDS,('edgar-research-20261016-24','edgar-research-20261016-25'))
        self.assertEqual(fresh.AUTHOR22_CLOSURE['sha256'],'8354ce06647ccea951dd0dd78d9ab9ccdae6738943e03220585e97cc7f756715')
        self.assertEqual(self.authority(),self.scope)
        for change in ({'author_id':fresh.AUTHOR22_IDS[0],'forecast_id':fresh.AUTHOR22_IDS[1]},
                {'author_max_output_tokens':49153},{'author_max_output_tokens':49152.0},
                {'author_max_input_tokens':24001},{'author_max_input_tokens':24000.0},
                {'author_max_output_tokens':True},{'continuation_human_approval':'unapproved'},
                {'closed_author_review':dict(fresh.AUTHOR22_CLOSURE,sha256='0'*64)},
                {'requires_cold_probe':False}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.authority(change)
        for change in ({'reviewer':'Root'},{'reviewer':''},{'blocking_findings':['problem']},{'verdict':'NOT_CLOSED'}):
            with self.subTest(closure=change),self.assertRaises(ValueError):self.authority(closure_change=change)

    def test_exact_reviewed24_sourcepins_and_all_protected_sources_fail_on_drift(self):
        repo=self.root/'source24'; original_repo=Path(__file__).resolve().parents[1]
        approved={'tools/earnings_open_context.py':'ab025592fab39640422fbcce6ac8e27d7f917d9552ba8fec04d07c3342da7bd8',
            'tools/earnings_open_broker.py':'a2e6d408037a924d18cb881c404ad9169375ad460424a0375c806ab3316fdc88',
            'tools/earnings_open_resources.py':'864a0ab4c8326d7c4542b3355373c9ad25bf497609bcf0630424b42f62658032',
            'tools/earnings_capacity_runtime.py':'9b37f21dbbf4541a96b3029ccd772741fbe9daa8af113e013b248a91d560ff28',
            'tools/earnings_night_budget.py':'0167e78735d6d886c695b3cf4dedd81675b859f05c73fb17c1fa60dd3549f923'}
        names=[*approved,'tools/earnings_open_fresh_grant.py','tools/earnings_open_author_followthrough.py',
            'tools/protected.py','configs/scope.json','configs/context.json']
        for name in names:
            path=repo/name; path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes((original_repo/name).read_bytes() if (original_repo/name).is_file() else b'inert synthetic source')
        old={'sources':{name:dict(engine.pin(repo/name),sha256='0'*64) for name in names[:6]}}
        old['sources']['tools/protected.py']=engine.pin(repo/'tools/protected.py')
        with mock.patch.object(flow.e,'REPO',repo),mock.patch.object(flow,'__file__',str(repo/'tools/earnings_open_author_followthrough.py')),\
                mock.patch.object(flow,'SCOPE',repo/'configs/scope.json'),mock.patch.object(flow,'CONTEXT',repo/'configs/context.json'):
            pins=flow.source_bindings(old,scope=self.scope)
            self.assertEqual({name:pins[name]['sha256'] for name in approved},approved)
            for name in [*approved,'tools/protected.py']:
                path=repo/name; raw=path.read_bytes(); path.write_bytes(raw+b'\n# synthetic drift')
                with self.subTest(name=name),self.assertRaises(ValueError):flow.source_bindings(old,scope=self.scope)
                path.write_bytes(raw)

    def test_actual_prepare_and_validate_change_only24_Author_output_to49152(self):
        self.base.body=deepcopy(self.body); self.base.scope=deepcopy(self.scope)
        value,old,owner=self.base.prepared(); rr=engine.read(value['runtime'])
        expected=deepcopy(old['limits']); expected['author'].update(max_input_tokens=24000,max_output_tokens=49152)
        self.assertEqual(rr['limits'],expected); self.assertEqual(rr['rates'],old['rates'])
        self.assertEqual(rr['role_efforts'],old['role_efforts'])
        self.assertEqual(rr['additional_cap_nano_usd'],21326993400)
        self.assertEqual(engine.read(value['grant'])['additional_cap_nano_usd'],21326993400)
        def check(mutator=None,reviewer='independent-synthetic-reviewer'):
            self.number+=1; home=self.root/f'prepared24-{self.number}'; home.mkdir()
            v=deepcopy(value); runtime=deepcopy(rr)
            if mutator:mutator(runtime)
            v['runtime']=engine.save(home/'runtime.json',runtime); vb=engine.save(home/'prepared.json',v)
            rb=engine.save(home/'review.json',{'verdict':'PASS_AUTHOR_FOLLOWTHROUGH_STAGE','blocking_findings':[],
                'reviewer':reviewer,'prepared':vb,'reviewed_sources':v['sources']})
            if mutator or reviewer=='Root':
                with self.assertRaises(ValueError):flow.validate_prepared(vb,rb)
            else:self.assertEqual(flow.validate_prepared(vb,rb),(v,runtime))
            owner.assert_not_called()
        check(); check(reviewer='Root')
        for role,key,amount in (('author','max_output_tokens',49153),('author','max_output_tokens',32768),
                ('author','max_input_tokens',24001),('author','wall_seconds',901),('controller','max_output_tokens',16385)):
            with self.subTest(role=role,key=key):check(lambda r,axis=role,k=key,n=amount:r['limits'][axis].__setitem__(k,n))
        check(lambda r:r['rates'].__setitem__('api_model','drift'))
        check(lambda r:r['role_efforts'].__setitem__('author','max'))

    def test_shared80_retains_closed22_23_and_all_predecessor_failed_roots(self):
        roots=[('edgar-research-20261015-12',name) for name in ('code','review-code')]
        roots += [('edgar-research-20261015-'+n,name) for n in ('14','16','18') for name in ('code','review-code','cold-probe-code')]
        roots += [('edgar-research-20261015-'+n,'code') for n in ('13','15','17','19')]
        for author,forecast in (fresh.AUTHOR20_IDS,fresh.AUTHOR22_IDS,fresh.AUTHOR24_IDS):
            roots += [(author,name) for name in ('code','review-code','cold-probe-code')]+[(forecast,'code')]
        self.assertEqual(len(roots),27)
        for index,(identifier,name) in enumerate(roots):
            path=self.root/'attempts'/identifier/name; path.mkdir(parents=True)
            for number in range(1 if index==26 else 3):
                action=path/f'call-{number:032x}'; action.mkdir(); engine.save(action/'result.json',{'status':'FAILED_NO_RETRY'})
        with mock.patch.object(flow,'ROOT',self.root),mock.patch.object(flow,'authority',return_value=self.scope):
            self.assertEqual(flow.containers_remaining(),1)
            (self.root/'attempts'/fresh.AUTHOR22_IDS[1]/'code'/('call-'+'f'*32)).mkdir()
            with self.assertRaises(ValueError):flow.containers_remaining()


if __name__=='__main__':unittest.main()
