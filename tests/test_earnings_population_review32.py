"""Independent32k Review boundary/transport/history tests with invented data.

Only the saved24 count case reads original public metadata. It is structural,
not a new provider token measurement, scorer call or historical replay proof.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

import earnings_entry as entry
import earnings_open_context as packing
import earnings_open_resources as resources
import earnings_population_roles as roles
from earnings_capacity_runtime import _OwnedHTTP
from earnings_http import RawOpenAIHTTP
from earnings_night_budget import DeadlineHTTP
from edgar_forecast_budget import BudgetStop
from edgar_forecast_openai import budgeted_response
from edgar_forecast_tools import function
from market_rsi import digest
import test_earnings_capacity_controller_transport as transport_fixture
import test_earnings_population_control_history as history_fixture


class Review32Boundary(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='review32-inert-');self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve();self.f=transport_fixture._TransportFixture(self,self.root/'owned')
        self.constructor_serial=0
        self.slot=self.f.root/'roles/review-01';self.slot.mkdir(parents=True)
        self.rates=dict(self.f.rates,effort='max');self.limits=dict(max_input_tokens=32000,max_output_tokens=16384,wall_seconds=900)
        self.context=dict(self.f.context,schema='earnings_capacity_review_transport_v1',slots=[str(self.slot)],rates=self.rates,limits=self.limits)
        self.binding=transport_fixture._save(self.f.root/'review-context.json',self.context)
        fields=dict(candidate_id={'type':'string','enum':['c'*64]},accepted_for_exploration={'type':'boolean'},rationale={'type':'string'})
        self.packet=dict(candidate_id='c'*64,matched_parent='a'*64,public_initial_packet='EXACT PUBLIC INPUT '*2000)
        self.request=dict(model='gpt-6.1-sol',reasoning={'effort':'max'},input=[dict(role='user',content=json.dumps(self.packet))],
            instructions='Independent Review without forced acceptance',tools=[],tool_choice='none',parallel_tool_calls=False,
            text={'format':{'type':'json_schema','name':'earnings_population_review_v1','strict':True,
                'schema':{'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}}})

    def construct(self,**limits):
        context=deepcopy(self.context);context['limits'].update(limits)
        self.constructor_serial+=1
        binding=transport_fixture._save(self.f.root/f'constructor-context-{self.constructor_serial:02d}.json',context)
        broker=Mock(definitions=[function('inspect_trace','Read inert test trace',{'slot':{'type':'string'}})])
        return roles.PopulationReviewer(binding,budget=self.f.budget,client_factory=Mock(),broker=broker)

    def test_original_population_reviewer_accepts_exact32k_rejects32001_bool_float(self):
        role=self.construct();self.assertEqual(role.context['limits'],self.limits)
        self.assertEqual(role.context['rates'],self.rates);self.assertEqual(role.context['rates']['effort'],'max')
        for key,value in (('max_input_tokens',32001),('max_input_tokens',True),('max_input_tokens',32000.0),
                ('max_output_tokens',16385),('max_output_tokens',True),('wall_seconds',901),('wall_seconds',900.0)):
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.construct(**{key:value})

    def test_only_review_input_headroom_changes_other_role_limits_and_efforts_exact(self):
        self.assertEqual(resources.role_limits(),{
            'controller':dict(max_input_tokens=32000,max_output_tokens=16384,wall_seconds=900),
            'review':dict(max_input_tokens=32000,max_output_tokens=16384,wall_seconds=900),
            'author':dict(max_input_tokens=96000,max_output_tokens=49152,wall_seconds=1200)})
        self.assertEqual(resources.ROLE_EFFORTS,dict(controller='max',author='high',review='max',forecast='max'))

    def exchange(self,tokens,*,count_error=None):
        raw=RawOpenAIHTTP('',30);calls=[];owner=self
        class Connection:
            def __init__(inner,host,timeout):
                if host!='api.openai.com':raise AssertionError('Invented provider only')
            def request(inner,method,endpoint,body,headers):inner.endpoint=endpoint;calls.append((endpoint,json.loads(body)))
            def getresponse(inner):
                if inner.endpoint.endswith('input_tokens'):
                    if count_error is not None:raise count_error
                    value=dict(object='response.input_tokens',input_tokens=tokens)
                else:
                    value=dict(model='gpt-6.1-sol',service_tier='default',status='completed',error=None,
                        output=[dict(type='message',role='assistant',content=[dict(type='output_text',text=json.dumps(
                            dict(candidate_id='c'*64,accepted_for_exploration=False,rationale='Synthetic test verdict only')))])],
                        usage=dict(input_tokens=tokens,output_tokens=7,total_tokens=tokens+7,input_tokens_details=dict(cached_tokens=0)))
                wire=transport_fixture._wire(value)
                return Mock(status=200,getheader=Mock(return_value='req_review32_synthetic'),read=Mock(side_effect=lambda limit:wire[:limit]))
            def close(inner):pass
        def check(loan):
            if loan is None:owner.f.budget.active()
            else:owner.f.budget.check_reserved(*loan)
        owned=_OwnedHTTP(raw,check,{str(self.slot):self.limits},self.rates)
        deadline=DeadlineHTTP(owned,deadline_utc='2099-01-01T00:00:00Z',rollout_seconds=900)
        return entry.ReceiptHTTP(deadline,self.slot),calls,patch('earnings_http.http.client.HTTPSConnection',Connection)

    def test_synthetic20325_original_count_reservation_handoff_and_physical_payload(self):
        before=deepcopy(self.request);http,calls,wire=self.exchange(20325)
        with wire:
            selected,handoff=packing.pack(http,self.request,self.limits,self.slot,1,review_final=True,prepared_count_context=self.binding)
            budgeted_response(http,selected,self.rates,self.limits,self.f.budget,self.slot,1,prepared_count=handoff)
        self.assertEqual(self.request,before);self.assertEqual(selected,before)
        self.assertEqual([p for p,_ in calls],['/v1/responses/input_tokens','/v1/responses'])
        self.assertEqual(calls[0][1],before)
        self.assertEqual(calls[1][1],dict(before,max_output_tokens=16384,service_tier='default',store=False))
        reserved=json.loads((self.slot/'01-request.json').read_bytes())
        self.assertEqual(reserved['payload'],before);self.assertEqual(reserved['reserved_nano_usd'],20325*2500+16384*10000)
        reuse=json.loads((self.slot/'01-prepared-count-reuse.json').read_bytes())
        self.assertTrue(reuse['reused_original_provider_count']);self.assertFalse(reuse['new_count_http_request'])
        self.assertEqual(self.f.budget.db.execute("SELECT reserved,charged,status FROM requests WHERE id!='fixture-prior'").fetchall(),
            [(20325*2500+16384*10000,20325*2500+7*10000,'settled')])

    def test_synthetic32001_rejected_before_reservation_or_generation_without_retry(self):
        http,calls,wire=self.exchange(32001)
        with wire,self.assertRaises(BudgetStop):
            packing.pack(http,self.request,self.limits,self.slot,1,review_final=True,prepared_count_context=self.binding)
        self.assertTrue(calls);self.assertTrue(all(p=='/v1/responses/input_tokens'for p,_ in calls))
        self.assertLessEqual(len(calls),4)
        self.assertEqual(self.f.budget.db.execute("SELECT COUNT(*)FROM requests WHERE id!='fixture-prior'").fetchone(),(0,))
        self.assertFalse((self.slot/'01-request.json').exists())

    def test_count_failure_propagates_once_before_any_generation(self):
        http,calls,wire=self.exchange(20325,count_error=TimeoutError('Synthetic count timeout'))
        with wire,self.assertRaises(TimeoutError):
            packing.pack(http,self.request,self.limits,self.slot,1,review_final=True,prepared_count_context=self.binding)
        self.assertEqual(len(calls),1);self.assertEqual(calls[0][0],'/v1/responses/input_tokens')
        self.assertEqual(self.f.budget.db.execute("SELECT COUNT(*)FROM requests WHERE id!='fixture-prior'").fetchone(),(0,))

    @unittest.skipUnless(os.getenv('MARKET_RSI_VERIFY_REVIEW24_COUNTS')=='1','Opt-in original24 public count metadata only')
    def test_original24_saved_counts_are_historical_structural_evidence_only(self):
        slot=Path('/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/edgar-population-20261016/attempts/edgar-population-20261016-24/roles/review-01')
        files=[slot/'04-context-01-count.json',slot/'04-context-04-count.json']
        before=[hashlib.sha256(p.read_bytes()).hexdigest()for p in files]
        self.assertEqual([json.loads(p.read_bytes())['input_tokens']for p in files],[20107,20325])
        self.assertEqual([json.loads((slot/n).read_bytes())['max_input_tokens']for n in ('04-context-01.json','04-context-04.json')],[20000,20000])
        self.assertFalse((slot/'04-request.json').exists());self.assertFalse((slot/'04-response.json').exists())
        self.assertEqual(before,[hashlib.sha256(p.read_bytes()).hexdigest()for p in files])
        # No candidate/scorer/provider, new count, token-fit or quality claim.


class Review32HistoricalBridge(unittest.TestCase):
    def setUp(self):
        self.f=history_fixture.HistoryBridgeTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.current['scorer']={'fixed':'original'};self.f.historical['scorer']={'fixed':'original'}

    def test_exact20_to32_bridge_retains_old_feedback_full_contract_and_explicit_author_wall_bridges(self):
        for walls_before,walls_after in ((False,False),(False,True),(True,True)):
            for author_before,author_after in ((48000,48000),(48000,64000),(48000,96000),(64000,96000),(96000,96000)):
                old=deepcopy(self.f.current if walls_before else self.f.historical)
                new=deepcopy(self.f.current if walls_after else self.f.historical)
                old['limits']['author']['max_input_tokens']=author_before;new['limits']['author']['max_input_tokens']=author_after
                old['limits']['review']['max_input_tokens']=20000;new['limits']['review']['max_input_tokens']=32000
                origin=self.f.origin_for_contract(old);path=Path(origin['last_scored_feedback']['path']);saved=path.read_bytes()
                with self.subTest(walls_before=walls_before,walls_after=walls_after,author_before=author_before,author_after=author_after):
                    self.assertEqual(history_fixture.admission.last_scored_contract_sha256(origin,new),digest(old))
                    self.assertEqual(path.read_bytes(),saved)
                    self.assertEqual(json.loads(saved)['campaign_contract_sha256'],digest(old))

    def test_reverse_nearby_float_bool_and_undeclared_other_contract_drift_rejected(self):
        old=deepcopy(self.f.current);old['limits']['author']['max_input_tokens']=96000
        for before,after in ((32000,20000),(20001,32000),(19999,32000),(20000,32001),
                (20000.0,32000),(20000,32000.0),(True,32000),(20000,True)):
            original=deepcopy(old);new=deepcopy(old)
            original['limits']['review']['max_input_tokens']=before;new['limits']['review']['max_input_tokens']=after
            origin=self.f.origin_for_contract(original)
            with self.subTest(before=before,after=after),self.assertRaises(ValueError):
                history_fixture.admission.last_scored_contract_sha256(origin,new)
        origin=self.f.origin_for_contract(old)
        for role,key,value in (('review','max_output_tokens',16385),('review','wall_seconds',901),('review','wall_seconds',900.0),
                ('author','max_input_tokens',96001),('author','max_output_tokens',49153),('author','wall_seconds',1201),
                ('controller','max_input_tokens',32001),('forecast','max_input_tokens',100001),('forecast','max_output_tokens',25001),('forecast','wall_seconds',1801)):
            new=deepcopy(old);new['limits']['review']['max_input_tokens']=32000;new['limits'][role][key]=value
            with self.subTest(role=role,key=key),self.assertRaises(ValueError):
                history_fixture.admission.last_scored_contract_sha256(origin,new)
        for key in ('data','model','scorer','undeclared_waiver'):
            new=deepcopy(old);new['limits']['review']['max_input_tokens']=32000;new[key]={'fixed':'changed'}
            with self.subTest(key=key),self.assertRaises(ValueError):history_fixture.admission.last_scored_contract_sha256(origin,new)


if __name__=='__main__':unittest.main()
