"""Generic failed re-Review joins; no model, candidate execution or new score.

Portable transcripts and original Services/driver use disclosed synthetic fee,
admission/review/score boundaries. The opt-in original24 loader is unmocked.
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
from unittest.mock import patch

import earnings_population_reused_review_failure as origin
import earnings_population_tasks as tasks
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_review23_origin as fixture


def actual_plan():
    plan=fixture.actual_plan();root=origin.resume.OWNED
    plan.update(recovery_mode=origin.MODE,
        failed_attempt=dict(path=str(root/'attempts/edgar-population-20261016-24/population-run-failure.json'),sha256=fixture.origin.FAILURE_SHA),
        closed_failure_audit=dict(path=str(root/'CUMULATIVE400-LIVE24-CLOSURE-AUDIT.json'),sha256='923e9a21d3cc4ad61f61ce48482e6acd81929539f31206c8d603f335367849a2'),
        stage_delivery_audit=dict(path=str(root/'CUMULATIVE400-LIVE24-ROLE-LINKS.json'),sha256='a2fd5d09fc437e92659e66227a5156f50572d5601812c1594dcf51536e0eab75'))
    return plan


class TranscriptTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.PhysicalTranscriptTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root;self.reader=self.f.reader;self.runtime=self.f.runtime
        source=self.f.audit['checkpoints'][-1]
        self.audit={'checkpoints':[dict(requests=[r for r in source['requests']if r['role']=='review-01'and int(r['number'])<=3],
            prepared_counts=[r for r in source['prepared_counts']if r['role']=='review-01'and int(r['number'])<=3])]}
        self.owned=[r for r in self.f.owned if Path(r['request']['path']).parent.name=='review-01'and int(Path(r['request']['path']).name[:2])<=3]

    def run_physical(self,owned=None):
        with patch.object(origin,'_owned_requests',return_value=self.owned if owned is None else owned):
            return origin._physical(self.reader,self.runtime,self.audit,3)

    def test_only_three_Review_generations_no_fake_Controller_Author_fee_rows(self):
        self.assertEqual(len(self.run_physical()),15)

    def test_extra_C_A_unsettled_charge_and_missing_request_fail(self):
        for which in ('missing','extra','unsettled','charge'):
            own=deepcopy(self.owned)
            if which=='missing':own.pop()
            elif which=='extra':own.append(self.f.owned[0])
            elif which=='unsettled':own[0]['status']='uncertain'
            else:own[0]['charged_nano_usd']+=1
            with self.subTest(which=which),self.assertRaises(ValueError):self.run_physical(own)

    def test_model_sidecar_prepared_turn_source_and_payload_tamper_refuse(self):
        row=self.audit['checkpoints'][-1]['requests'][0];prep=self.audit['checkpoints'][-1]['prepared_counts'][0]
        mutations=[(row['physical']['intent'],lambda v:v['payload'].update(model='foreign')),
                   (row['physical']['raw'],lambda v:v.update(status='incomplete')),
                   (prep['reuse_binding'],lambda v:v.update(turn=True)),
                   (prep['reuse_binding'],lambda v:v.update(consumer_source={'path':'/foreign.py','sha256':'f'*64}))]
        for bound,mutate in mutations:
            value=deepcopy(engine.read(bound));mutate(value)
            original=self.reader.read
            def overlay(b,**kw):return deepcopy(value)if b==bound else original(b,**kw)
            with self.subTest(path=bound['path']),patch.object(self.reader,'read',side_effect=overlay),self.assertRaises(ValueError):self.run_physical()


class PackingTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.ReviewPackingTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root;self.folder=self.f.folder;self.reader=self.f.reader;self.runtime=self.f.runtime
        self.runtime['limits']['review']['wall_seconds']=900
        # New fixture belongs to attempted04 after three completed generations.
        for index in range(1,3):
            for suffix in ('.json','-count.json'):
                old=self.folder/f'07-context-{index:02d}{suffix}';old.rename(self.folder/f'04-context-{index:02d}{suffix}')
        for row in self.f.audit['terminal_evidence']['review_input_failure']:
            for key in ('context','count'):
                row[key]=engine.pin(Path(row[key]['path'].replace('07-context','04-context')))
        for turn in range(4,7):(self.folder/f'http-gen{turn}.intent.json').unlink()
        for path in self.folder.glob('http-count*.intent.json'):
            value=engine.read(engine.pin(path));path.write_text(json.dumps(dict(value,retry_allowed=False)))
        (self.folder/'06-response.json').rename(self.folder/'03-response.json')
        self.value=dict(status='FAILED_NO_RETRY',error_type='BudgetStop',retry_allowed=False,turns=4,
            final_numbered_response='03-response.json',wall_seconds=350.3)
        bound=engine.save(self.folder/'result.json',self.value)
        self.terminal=dict(self.f.audit['terminal_evidence'],roles=[dict(role='review-01',binding=bound,value=self.value)])

    def result(self):return origin._review_result(self.reader,self.root,self.runtime,self.terminal)
    def counts(self):return origin._blocked_counts(self.reader,self.root,self.runtime,self.terminal,3,4)

    def test_original_attempted4_completed3_and_saved_two_counts_not_generation_or_verdict(self):
        self.assertEqual(self.result(),(3,4));self.assertEqual(self.counts(),[1001,1002])

    def test_bool_wrong_turn_completed_quality_wall_or_fake_role_refuses(self):
        original=deepcopy(self.value)
        for changes in ({'turns':True},{'turns':5},{'status':'COMPLETED_REVIEW'},{'wall_seconds':900}):
            value=dict(original,**changes);(self.folder/'result.json').write_text(json.dumps(value))
            self.terminal['roles'][0]=dict(role='review-01',binding=engine.pin(self.folder/'result.json'),value=value)
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.result()
        self.terminal['roles'].append(dict(role='author-01',binding={},value={}))
        with self.assertRaises(ValueError):self.result()

    def test_missing_count_fitting_bool_model_or_extra_generation_refuses(self):
        rows=self.terminal['review_input_failure'];original=deepcopy(rows)
        self.terminal['review_input_failure']=rows[:1]
        with self.assertRaises(ValueError):self.counts()
        self.terminal['review_input_failure']=original
        for count in (1000,True):
            bound=rows[0]['count'];read=self.reader.read
            def overlay(b,**kw):return {'input_tokens':count}if b==bound else read(b,**kw)
            with self.subTest(count=count),patch.object(self.reader,'read',side_effect=overlay),self.assertRaises(ValueError):self.counts()
        engine.save(self.folder/'http-gen4.intent.json',dict(endpoint='/v1/responses',payload={}))
        with self.assertRaises(ValueError):self.counts()


class CarryAndReceivingTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.V2ReceivingTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.inherited=dict(author_stage_reuse=deepcopy(self.f.bundle),population=deepcopy(self.f.f.state),
            feedback={'original':'latest18'},last_scored_feedback={'original':'score07'},previous_result={'original':'completed18'},
            delivery_lessons=[{'original':'compact15'}],evidence=[],reference_candidate={'original':'A23reference'},
            recovery_context={'failed_attempt':self.f.bundle['failed_attempt']})
        self.latest=engine.save(self.f.root/'latest-failure.json',{'synthetic_latest_failure':True})

    def test_only_latest_delivery_changes_original_A23_C22_bundle_and_science_stay_exact(self):
        before=deepcopy(self.inherited)
        value=origin._attach(self.inherited,self.latest,audit={},completed=3,limit=20000,counts=[20107,20325],probes=[],evidence=[])
        self.assertEqual(self.inherited,before)
        for key in ('author_stage_reuse','population','feedback','last_scored_feedback','previous_result','delivery_lessons','reference_candidate'):
            self.assertEqual(value[key],before[key])
        self.assertEqual(origin.recovery.latest_failed_attempt(value),self.latest)
        self.assertEqual(value['author_stage_reuse']['failed_attempt'],before['author_stage_reuse']['failed_attempt'])
        self.assertNotEqual(value['recovery_context']['failed_attempt'],value['author_stage_reuse']['failed_attempt'])
        self.assertEqual(value['recovery_context']['review_assessment'],'not_completed')

    def test_original_Services_driver_receives_same_bundle_without_new_C_A_calls(self):
        value=origin._attach(self.inherited,self.latest,audit={},completed=3,limit=20000,counts=[20107,20325],probes=[],evidence=[])
        Path(self.f.saved_origin['path']).write_text(json.dumps(value));self.f.saved_origin=engine.pin(Path(self.f.saved_origin['path']))
        # Repin the fixture study/context after changing only the synthetic input.
        study=engine.read(self.f.owner.runtime['forecast_study']);study['campaign_origin']=self.f.saved_origin
        Path(self.f.owner.runtime['forecast_study']['path']).write_text(json.dumps(study))
        self.f.owner.runtime['forecast_study']=engine.pin(Path(self.f.owner.runtime['forecast_study']['path']))
        self.f.context['origin']=self.f.saved_origin
        result,rows=self.f.drive();self.assertEqual(result['status'],'completed')
        self.f.role.author.assert_not_called();self.f.role.propose.assert_not_called()
        self.assertEqual(self.f.reviewed[0]['source'],self.f.f.business['source_text'])
        origin.recovery.verify_reused_stages(self.f.f.reader,self.f.owner.root,rows,value)


class EarlyBoundaryTests(unittest.TestCase):
    def test_wrong_mode_foreign_path_and_malformed_binding_refuse_before_reader(self):
        plan=actual_plan();bound=plan['failed_attempt']
        cases=[(bound,dict(plan,recovery_mode='foreign')),({},plan),
               (dict(bound,path='/foreign/population-run-failure.json'),plan)]
        for binding,p in cases:
            with self.subTest(binding=binding),patch.object(origin.history,'_Reader',side_effect=AssertionError('No body read')),self.assertRaises(ValueError):
                origin.load(binding,root=origin.resume.OWNED,ledger=origin.resume.LEDGER,repo=origin.resume.REPO,plan=p)


class DispatchBoundaryTests(unittest.TestCase):
    def test_new_mode_routes_generic_and_original23_mode_keeps_historical_adapter(self):
        # Decoder/loader stubs prove only dispatch, not historical admission.
        # Old23 uses its immutable fixture, never the prospective on-disk plan.
        plan_binding=dict(path=str(origin.resume.REPO/origin.recovery.PLAN),sha256='a'*64)
        for current,expected in [(actual_plan(),'generic'),(fixture.actual_plan(),'original23')]:
            with (self.subTest(mode=current['recovery_mode']),
                  patch.object(origin.recovery,'_read_plan',return_value=deepcopy(current)) as read_plan,
                  patch.object(origin,'load',return_value={'receiver':'generic'}) as generic,
                  patch.object(fixture.origin,'load',return_value={'receiver':'original23'}) as original23,
                  patch.object(origin.recovery,'_legacy_load',side_effect=AssertionError('No legacy fallback')),
                  patch.object(origin.recovery,'_load_review_reuse',side_effect=AssertionError('No old10 fallback'))):
                value=origin.recovery.load(current['failed_attempt'],root=origin.resume.OWNED,
                    ledger=origin.resume.LEDGER,repo=origin.resume.REPO,plan_binding=plan_binding)
                self.assertEqual(value,{'receiver':expected})
                selected=generic if expected=='generic'else original23
                selected.assert_called_once_with(current['failed_attempt'],root=origin.resume.OWNED,
                    ledger=origin.resume.LEDGER,repo=origin.resume.REPO,plan=current)
                (original23 if expected=='generic'else generic).assert_not_called()
                read_plan.assert_called_once_with(plan_binding,root=origin.resume.OWNED,ledger=origin.resume.LEDGER,
                    repo=origin.resume.REPO,historical_reader=None)


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_REUSED_REVIEW24')=='1','Root-only guarded original24→23→22→21→20→18 proof')
class ActualReusedReview24(unittest.TestCase):
    def test_original_failed_reReview_keeps_original_A23_bundle_latest24_and_old_scores_separate(self):
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
            with origin.history.validation_epoch():
                value=origin.load(plan['failed_attempt'],root=origin.resume.OWNED,ledger=origin.resume.LEDGER,repo=origin.resume.REPO,plan=plan)
        bundle=value['author_stage_reuse'];self.assertNotIn('controller_stage_import',value)
        self.assertEqual(bundle['source']['sha256'],plan['successful_candidate']['source_sha256'])
        self.assertTrue(bundle['failed_attempt']['path'].endswith('-23/population-run-failure.json'))
        self.assertTrue(value['recovery_context']['failed_attempt']['path'].endswith('-24/population-run-failure.json'))
        self.assertEqual(value['recovery_context']['observed_input_tokens'],[20107,20325])
        self.assertEqual(value['recovery_context']['completed_Review_generations'],3)
        self.assertEqual(value['feedback']['sha256'],'238ca35f5c9a9644b5960e376ec7b14436895eeec1ae73910fea8a557aef6544')
        self.assertEqual(value['last_scored_feedback']['sha256'],'170098840c76fd15e192b626526baede6a9d5214e762a73a27cd580f4a8a46b9')
        self.assertNotIn(bundle['candidate']['id'],value['population']['versions'])


if __name__=='__main__':unittest.main()
