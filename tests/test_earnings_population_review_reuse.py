"""Explicit stage reuse, without HTTP/model/candidate execution.

The seven-stage test uses synthetic admission, cases, review and scores. It
proves routing/cache/feedback wiring only. The opt-in actual10 read-only test
checks immutable historical provenance and development-only file access.
"""
from contextlib import ExitStack
from copy import deepcopy
import builtins
import io
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import earnings_population as pool
import earnings_population_loop as loop
import earnings_population_recovery as recovery
import earnings_population_services as services
import earnings_population_tasks as tasks
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness import feedback_linked_loop as driver
from test_earnings_population_delta_integration import DeltaIntegrationTests


class SealedProvenanceTests(unittest.TestCase):
    def test_missing_foreign_or_resealed_role_result_is_not_original_success(self):
        runtime={'id':'synthetic10','source_commit':'a'*40}; bound={'path':'/synthetic/runtime','sha256':'b'*64}
        delivery={'schema':'earnings_population_live_role_links_audit_v1','attempt_id':'synthetic10',
            'runtime':{'binding':bound,'source_commit':runtime['source_commit'],'run_closed':True}}
        rows=[{'role':name,'result':{'path':'/synthetic/'+name,'sha256':'c'*64},'value':{'status':'original'}}
              for name in ('controller-01','author-01','review-01')]
        reader=Mock();reader.pin.return_value={'path':'/synthetic/resealed','sha256':'d'*64}
        with self.assertRaisesRegex(ValueError,'role-result binding'):
            recovery._sealed_delivery(reader,Path('/synthetic'),bound,runtime,{'roles':rows},delivery,{}, {})
        with self.assertRaisesRegex(ValueError,'role set'):
            recovery._sealed_delivery(reader,Path('/synthetic'),bound,runtime,{'roles':rows[:2]},delivery,{}, {})
        reader.read.assert_not_called()

    def test_cleanup_requires_sealed_exact_set_and_success_flags(self):
        bound={'path':'/synthetic/code/result.json','sha256':'a'*64}
        audit={'code_cleanup_receipts':[{'receipt':bound,'cleanup_verified':True,'source_integrity_verified':True}]}
        recovery._sealed_cleanup(audit,[{'result':bound}])
        for cleanup in ([],[{'result':dict(bound,sha256='b'*64)}],[{'result':bound},{'result':bound}]):
            with self.subTest(cleanup=cleanup),self.assertRaisesRegex(ValueError,'cleanup receipt'):
                recovery._sealed_cleanup(audit,cleanup)
        bad=deepcopy(audit);bad['code_cleanup_receipts'][0]['cleanup_verified']=False
        with self.assertRaisesRegex(ValueError,'cleanup receipt'):
            recovery._sealed_cleanup(bad,[{'result':bound}])


class ReusedStageTests(DeltaIntegrationTests):
    # Inherit only its portable setup/source helpers, not its test cases.
    def setUp(self):
        super().setUp()
        self.state = pool.initialize(self.parent, {'K':'a'*64,'M':'b'*64,'C':'c'*64})
        self.chosen.pop('retire_branch_id')
        self.original_decision = engine.save(self.root/'old-decision.json',self.chosen)
        self.raw = engine.save(self.root/'old-response.json',{'status':'completed','output':[
            {'type':'message','role':'assistant','content':[{'type':'output_text','text':json.dumps({
                'decision_sha256':digest(services.scientific(self.chosen)),
                'parent_source_sha256':self.parent_r['sha256'],
                'edits':[{'kind':'replace','old_text':"return {'method':'old'}",'new_text':"return {'method':'new'}"}],
                'test_text':"CASES=[{'input':{},'expected':{'method':'new'}}]"})}]}]})
        business = services.assemble(self.parent_r,services.scientific(self.chosen),engine.read(self.raw))
        source=self.source('old-candidate.py',business['source_text'])
        tests=self.source('old-cases.py',business['test_text'])
        self.assembly=engine.save(self.root/'old-assembly.json',{'synthetic_original':True})
        self.child=pool.version(source,self.parent_h,parent=self.parent['id'],axis='R',
            method=self.chosen['hypothesis'],author='model:DeltaAuthor',evidence=[self.raw])
        self.bundle=dict(schema='earnings_population_author_stage_reuse_v1',mode=recovery.REVIEW_REUSE,
            candidate=self.child,decision=self.original_decision,scientific_decision=services.scientific(self.chosen),
            raw_patch_response=self.raw,assembly=self.assembly,tests=tests,source=source,parent_source=self.parent_r,
            failed_attempt=engine.save(self.root/'old-failure.json',{'synthetic':True}),cases={},probes=[])
        self.origin=engine.save(self.root/'origin.json',{'author_stage_reuse':self.bundle})
        self.resume=engine.save(self.root/'resume.json',{'reuse_mode':recovery.REVIEW_REUSE})
        self.study=engine.save(self.root/'study.json',{'campaign_origin':self.origin,'campaign_resume':self.resume})
        self.owner=services.Services.__new__(services.Services)
        self.owner.root=self.root/'new'; self.owner.native_root=self.root/'native'
        self.owner.native_root.mkdir(); self.owner.authored={}; self.owner.pending=[]; self.owner.traces={}
        self.owner.runtime={'forecast_study':self.study,'companies':['synthetic-new-company']}
        self.owner.case=Mock(return_value={'state_api':SimpleNamespace(tools=SimpleNamespace(files={'questions.md':'synthetic questions'}))})
        broker=Mock();broker.current_sources.return_value={'R':self.parent_source,'H':Path(self.parent_h['path']).read_text()}
        broker.references.return_value={};broker.available_traces.return_value={}
        self.role=Mock(broker=broker);self.role.propose.side_effect=AssertionError('No new Controller model call')
        self.role.author.side_effect=AssertionError('No new Author model call')
        self.owner.role=Mock(return_value=self.role)
        self.context={'origin':self.origin,'campaign':{},'original_R_evidence_abi':{'synthetic':True},
            'research_context':{'schema':'earnings_repair_context_v1','verification':'synthetic evidence ABI','observations':{}},
            'feedback_binding':self.raw,'prior_candidate':{'reference_only':True}}

    def drive_reuse(self):
        self.reviewed=[];self.forecasted=[]
        def review(child,state,slot):
            self.reviewed.append((deepcopy(child),deepcopy(self.owner.authored[child['id']])))
            return {'accepted_for_exploration':True,'evidence':[self.assembly]}
        def forecast(version,company,slot):
            self.forecasted.append(version['id'])
            return dict(version_id=version['id'],points=1,evidence=[self.assembly])
        with patch.object(services,'public_feedback',return_value={'synthetic_unscored':True}), \
             patch('earnings_population_campaign_context.prepare',return_value=deepcopy(self.context)):
            result=loop.run(self.owner.root,self.state,['synthetic-new-company'],
                {'controller':self.owner.controller,'author':self.owner.author,'review':review,'forecast':forecast},
                admit=lambda context:True,max_rounds=1,identity=lambda:{s:{'inert':s} for s in driver.STAGES})
        return result

    def test_seven_stage_driver_reuses_exact_source_without_Controller_or_Author_HTTP(self):
        original=deepcopy(self.state); result=self.drive_reuse()
        self.assertEqual(result['status'],'completed');self.assertEqual(self.state,original)
        self.assertEqual(self.reviewed[0][0],self.child)
        cached=self.reviewed[0][1]
        self.assertEqual(cached['source'],Path(self.child['R']['path']).read_text())
        self.assertEqual(cached['decision'],self.bundle['scientific_decision'])
        self.assertEqual(cached['review_index_inputs']['original_binding'],self.raw)
        self.assertEqual(self.forecasted,[self.parent['id'],self.child['id']])
        self.role.propose.assert_not_called();self.role.author.assert_not_called()
        self.assertEqual(self.owner.role.call_count,1) # Controller construction only; no transport.
        self.assertFalse(self.marker.exists())
        rows={stage:engine.read(engine.pin(self.owner.root/'loop'/f'round-0001-{stage}.done.json'))['output']
              for stage in driver.STAGES}
        reader=SimpleNamespace(read=engine.read,pin=engine.pin)
        recovery.verify_reused_stages(reader,self.owner.root,rows,{'author_stage_reuse':self.bundle})
        final=result['result'];self.assertIn(self.child['id'],final['population']['explorers'])
        self.assertEqual(final['population']['observations'][-1]['feedback'],final['feedback'])
        for name in ('controller-01','author-01'):
            folder=self.owner.root/'roles'/name
            self.assertFalse((folder/'response.json').exists());self.assertFalse((folder/'result.json').exists())
            self.assertFalse(list(folder.glob('http-*')))

    def test_stage_replay_refuses_source_parent_mode_or_fabricated_new_model_result(self):
        self.drive_reuse()
        rows={stage:engine.read(engine.pin(self.owner.root/'loop'/f'round-0001-{stage}.done.json'))['output']
              for stage in driver.STAGES}
        reader=SimpleNamespace(read=engine.read,pin=engine.pin)
        receipt=self.owner.root/'roles/author-01/author-stage-reuse.json'
        original=json.loads(receipt.read_text())
        for changes in ({'mode':'other'},{'source':self.parent_r},{'original_decision':self.raw},
                        {'new_model_called':True}):
            receipt.write_text(json.dumps(dict(original,**changes)))
            with self.subTest(changes=changes),self.assertRaisesRegex(ValueError,'stage reuse'):
                recovery.verify_reused_stages(reader,self.owner.root,rows,{'author_stage_reuse':self.bundle})
        receipt.write_text(json.dumps(original))
        (receipt.parent/'result.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'stage reuse'):
            recovery.verify_reused_stages(reader,self.owner.root,rows,{'author_stage_reuse':self.bundle})

    def test_unadopted_candidate_cannot_silently_change_parent(self):
        self.bundle['candidate']['parent']='f'*64
        changed=deepcopy(self.chosen);changed['feedback_sha256']='c'*64
        with patch.object(self.owner,'reused_author',return_value=self.bundle):
            with self.assertRaisesRegex(ValueError,'change science/parent'):
                self.owner.author(changed,self.state,str(self.root/'bad/author-01'))
        self.assertFalse(self.marker.exists())


# Avoid running inherited Delta transport tests a second time in this module.
for _name in list(DeltaIntegrationTests.__dict__):
    if _name.startswith('test_'):
        setattr(ReusedStageTests,_name,None)


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_REVIEW_REUSE10')=='1','Explicit read-only actual10 opt-in')
class ActualReviewReuse10(unittest.TestCase):
    def test_guarded_actual10_preserves_exact07_state_and_sealed_successful_Author(self):
        # Initialize stdlib's temp-directory cache before forbidding all writes;
        # otherwise gettempdir itself performs an unrelated OS writability probe.
        tempfile.gettempdir()
        allowed={'CIK0000003545','CIK0000004457','CIK0000017313'}; opened=[]; qa_hashes=set()
        original=tasks.resident
        def resident(cik):
            if cik not in allowed:raise AssertionError('Non-dev resident forbidden')
            value=original(cik);qa_hashes.add(value['kernel']['qa']['sha256']);return value
        def guard(function):
            def wrapped(path,*args,**kwargs):
                mode=kwargs.get('mode',args[0] if args else 'r')
                if type(mode) is str and any(c in mode for c in 'wax+'):
                    raise AssertionError('Historical verifier must not write')
                if type(mode) is int and mode & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
                    raise AssertionError('Historical verifier must not open writable descriptors')
                if not isinstance(path,int):
                    text=os.fsdecode(path)
                    if set(re.findall(r'CIK[0-9]{10}',text))-allowed:raise AssertionError('Non-dev body forbidden')
                    opened.append(text)
                return function(path,*args,**kwargs)
            return wrapped
        original_json=json.loads
        def json_read(raw,*args,**kwargs):
            import hashlib
            data=raw.encode() if isinstance(raw,str) else raw
            if isinstance(data,(bytes,bytearray)) and hashlib.sha256(data).hexdigest() in qa_hashes:
                raise AssertionError('Opaque QA bytes must not be decoded')
            return original_json(raw,*args,**kwargs)
        original_db=sqlite3.connect
        def database(path,*args,**kwargs):
            if '?mode=ro' not in str(path) or kwargs.get('uri') is not True:
                raise AssertionError('Historical verifier may use only read-only SQLite')
            return original_db(path,*args,**kwargs)
        with ExitStack() as stack:
            stack.enter_context(patch.object(tasks,'resident',side_effect=resident))
            stack.enter_context(patch.object(json,'loads',side_effect=json_read))
            stack.enter_context(patch.object(sqlite3,'connect',side_effect=database))
            stack.enter_context(patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden')))
            for module in (builtins,io,os):stack.enter_context(patch.object(module,'open',guard(module.open)))
            v=recovery.load(engine.pin(recovery.resume.OWNED/'attempts/edgar-population-20261016-10/population-run-failure.json'),
                root=recovery.resume.OWNED,ledger=recovery.resume.LEDGER,repo=recovery.resume.REPO,
                plan_binding=engine.pin(recovery.resume.REPO/recovery.PLAN))
            plan=engine.read(engine.pin(recovery.resume.REPO/recovery.PLAN))
            audit=engine.read(plan['closed_failure_audit']);delivery=engine.read(plan['stage_delivery_audit'])
            runtime_bound=delivery['runtime']['binding'];runtime=engine.read(runtime_bound)
            attempt=Path(runtime['root']);reader=recovery.history._Reader(recovery.resume.OWNED,
                recovery.resume.LEDGER,recovery.resume.REPO,runtime['id'])
            args=(reader,attempt,runtime_bound,runtime,audit,delivery,v['author_stage_reuse']['decision'],v['author_stage_reuse']['candidate'])
            for which in ('role','Controller','Delta'):
                bad_audit=deepcopy(audit);bad_delivery=deepcopy(delivery)
                if which=='role':bad_audit['roles'][0]['result']['sha256']='f'*64
                elif which=='Controller':bad_delivery['controller_rounds'][0]['decision']['sha256']='f'*64
                else:bad_delivery['author_rounds'][0]['delta_delivery_and_assembly']['original_raw_response']['sha256']='f'*64
                with self.subTest(sealed_join=which),self.assertRaises(ValueError):
                    recovery._sealed_delivery(*args[:4],bad_audit,bad_delivery,*args[6:])
        self.assertEqual(digest(v['population']),'0de8249a69779acfd0d961da3a0e1a3429ea2fa95d3edc6ea9b703c5d286c232')
        self.assertEqual(v['feedback']['sha256'],'97219b1a70ea85c8195868417a21bfcae44d043cc569a77d4f08e466daf6c206')
        self.assertEqual(v['last_scored_feedback']['sha256'],'170098840c76fd15e192b626526baede6a9d5214e762a73a27cd580f4a8a46b9')
        self.assertEqual(v['author_stage_reuse']['source']['sha256'],'b3935bed3bfcbde0f7192a06d8bcaabafafbae4b75d6b498545c93556c689b0d')
        self.assertNotIn(v['reference_candidate']['id'],v['population']['versions'])
        self.assertEqual(v['recovery_context']['review_assessment'],'not_completed')
        self.assertTrue(opened)


if __name__=='__main__':unittest.main()
