"""Independent v2 capacity provenance tests: inert text, not model/code runs.

Portable source/probe/role/fee bytes are synthetic. Actual literal editing,
original checked-base proof (in its separate case), context and ledger-row
projection checks are exercised. No production ledger/API/QA/Docker/history
replay or candidate execution; explicitly patched boundaries are documented.
"""
from copy import deepcopy
import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import earnings_population_recovery as recovery
import earnings_population_delta_author as delta
import earnings_population_campaign_context as contexts
import earnings_population_completed as completed
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_author_capacity_recovery as legacy
import test_earnings_population_implementation_base as base_fixture
from test_earnings_population_delta_author import choice, reply


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))
    return engine.pin(path)


class BaseCapacityLiteralAdversaries(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='v2-capacity-independent-')
        self.addCleanup(temporary.cleanup); self.root = Path(temporary.name).resolve()
        self.marker = self.root/'MUST_NOT_EXECUTE'
        self.header = ("PROGRAM={'axis':'R'}\nfrom pathlib import Path\n"
            f"Path({str(self.marker)!r}).write_text('NO EXECUTION')\n"
            "def run(payload): return {'fixture':'base'}\n")
        body = self.header+''.join(f'# TOKEN_{i:02d}\n' for i in range(12))
        self.source = body+'#'+'p'*(63490-len(body.encode())-2)+'\n'
        self.assertEqual(len(self.source.encode()), 63490)
        self.base_source = self.root/'base.py'; self.base_source.write_text(self.source)
        self.parent_path = self.root/'active-R7.py'; self.parent_path.write_text(self.header+'# active comparator\n')
        self.base_binding, self.parent = engine.pin(self.base_source), engine.pin(self.parent_path)
        self.selected = choice()
        self.base = {'schema':'earnings_population_implementation_base_v1', 'source':self.base_binding,
            'comparison_parent':{'R':self.parent}, 'adopted':False}
        self.edits = [{'kind':'replace','old_text':f'TOKEN_{i:02d}',
            'new_text':f'TOKEN_{i:02d}'+'x'*(473 if i<6 else 472)} for i in range(12)]
        self.delta = {'decision_sha256':digest(self.selected),
            'comparison_parent_source_sha256':self.parent['sha256'],
            'implementation_base_source_sha256':self.base_binding['sha256'],
            'edits':deepcopy(self.edits),'test_text':'CASES=[{"input":{},"expected":{"fixture":"base"}}]'}

    def measure(self, patch_value=None, raw=None):
        # This one boundary is a declared already-verified-base seam. The
        # following class independently exercises real checked_base provenance.
        with patch.object(delta, 'checked_base', return_value=self.base_binding):
            return recovery._base_capacity_delta(self.parent, self.selected,
                reply(self.delta if patch_value is None else patch_value) if raw is None else raw,
                implementation_base=self.base)

    def test_twelve_disjoint_replacements_preserve_exact_base_not_active_parent(self):
        before = deepcopy(self.delta)
        public, capacity = self.measure()
        source = delta._edit_source(self.source, self.edits)
        self.assertEqual(public, before); self.assertEqual(self.delta, before)
        self.assertEqual(capacity['edit_count'], 12)
        self.assertEqual(capacity['implementation_base_utf8_bytes'], 63490)
        self.assertEqual(capacity['comparison_parent_utf8_bytes'], len(self.parent_path.read_bytes()))
        self.assertEqual(capacity['assembled_utf8_bytes'], 69160)
        self.assertEqual(capacity['excess_utf8_bytes'], 3624)
        self.assertEqual(capacity['source_limit_utf8_bytes'], 65536)
        self.assertEqual(capacity['assembled_source_sha256'], hashlib.sha256(source.encode()).hexdigest())
        self.assertEqual(capacity['implementation_base_source_sha256'], self.base_binding['sha256'])
        for original, row in zip(self.edits, capacity['edits']):
            for key in ('old_text','new_text'):
                self.assertEqual(row[key+'_utf8_bytes'], len(original[key].encode()))
                self.assertEqual(row[key+'_sha256'], hashlib.sha256(original[key].encode()).hexdigest())
        ast.parse(source)  # AST only, never import/exec.
        self.assertEqual(self.base_source.read_text(), self.source)
        self.assertFalse(self.marker.exists())

    def test_utf8_sizes_and_digest_do_not_use_character_lengths(self):
        edits = deepcopy(self.edits); edits[0]['new_text'] += 'λ'*500
        _, capacity = self.measure(dict(self.delta, edits=edits))
        self.assertEqual(capacity['assembled_utf8_bytes'], 70160)
        self.assertEqual(capacity['edits'][0]['new_text_utf8_bytes'], len(edits[0]['new_text'].encode()))
        self.assertGreater(capacity['edits'][0]['new_text_utf8_bytes'], len(edits[0]['new_text']))

    def test_wrong_base_comparison_decision_and_extra_v1_field_are_refused(self):
        for change in ({'decision_sha256':'a'*64}, {'comparison_parent_source_sha256':'b'*64},
                {'implementation_base_source_sha256':self.parent['sha256']},
                {'parent_source_sha256':self.parent['sha256']}, {'source_text':'invented'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.measure(dict(self.delta, **change))

    def test_fitting_program_is_not_a_capacity_failure(self):
        with self.assertRaisesRegex(ValueError, 'fitting program'):
            self.measure(dict(self.delta, edits=[dict(kind='replace',old_text='TOKEN_00',new_text='TOKEN_FIXED')]))

    def test_missing_ambiguous_overlap_noop_and_edit_limits_refused(self):
        variants = [[], self.edits+[deepcopy(self.edits[0])]*5,
            [{'kind':'replace','old_text':'MISSING','new_text':'q'*3000}],
            [{'kind':'replace','old_text':'p','new_text':'q'*3000}],
            [{'kind':'replace','old_text':'TOKEN_00','new_text':'q'*3000},
             {'kind':'replace','old_text':'# TOKEN_00','new_text':'q'*3000}],
            [{'kind':'replace','old_text':'TOKEN_00','new_text':'TOKEN_00'}],
            [{'kind':'append','old_text':'','new_text':'q'*65537}],
            [{'kind':'append','old_text':'','new_text':'#tail'}, *self.edits]]
        for index, edits in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.measure(dict(self.delta, edits=edits))

    def test_test_text_limit_and_incomplete_response_refused(self):
        for text in ('', None, 'x'*32769):
            with self.subTest(text_type=type(text).__name__), self.assertRaises(ValueError):
                self.measure(dict(self.delta, test_text=text))
        with self.assertRaises(ValueError):
            self.measure(raw=dict(reply(self.delta),status='incomplete'))

    def test_v2_is_not_silently_reinterpreted_by_old_v1_helper(self):
        with self.assertRaises(ValueError):
            recovery._capacity_delta(self.parent,self.selected,reply(self.delta))
        original = legacy.CapacityFailureUnitTests()
        original.setUp(); self.addCleanup(original.doCleanups)
        _, measured = recovery._capacity_delta(original.parent, original.selected, legacy.response(original.delta))
        self.assertEqual(set(measured), {'parent_utf8_bytes','append_utf8_bytes','assembled_utf8_bytes',
            'source_limit_utf8_bytes','excess_utf8_bytes','test_text_utf8_bytes'})
        self.assertFalse(original.marker.exists())


class RealBaseProvenanceAdversaries(unittest.TestCase):
    """Real checked_base over invented but hash/receipt-verified source history."""
    def setUp(self):
        self.f = base_fixture.ImplementationBaseTests()
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.base = self.f.base()
        self.patch = self.f.new_patch(edits=[dict(kind='append',old_text='',new_text='\n#'+'x'*65500+'\n')])

    def measure(self, *, base=None, selected=None):
        return recovery._base_capacity_delta(self.f.parent['R'], self.f.chosen if selected is None else selected,
            reply(self.patch), implementation_base=self.base if base is None else base)

    def test_actual_original_base_proof_is_used_not_active_source_or_execution(self):
        public, measured = self.measure()
        self.assertEqual(public, self.patch)
        self.assertEqual(measured['implementation_base_source_sha256'], self.f.source_binding['sha256'])
        self.assertGreater(measured['assembled_utf8_bytes'], 65536)
        self.assertFalse(self.f.f.marker.exists())

    def test_forged_base_adoption_source_or_feedback_is_refused(self):
        changes = ({'adopted':True},{'source':self.f.parent['R']},
                   {'feedback_binding':dict(self.base['feedback_binding'],sha256='f'*64)},
                   {'version_id':self.f.parent['id']})
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.measure(base=dict(self.base, **change))

    def test_wrong_comparison_or_decision_cannot_rebind_existing_base(self):
        wrong = deepcopy(self.base); wrong['comparison_parent']['R'] = self.f.source_binding
        with self.assertRaises(ValueError):
            self.measure(base=wrong)
        with self.assertRaises(ValueError):
            self.measure(selected=dict(self.f.chosen,feedback_sha256='a'*64))

    def test_changed_original_rejected_feedback_source_or_case_bytes_are_refused(self):
        for bound in (self.f.feedback_binding,self.f.source_binding,self.f.cases):
            path = Path(bound['path']); before = path.read_bytes(); path.write_bytes(before+b' ')
            with self.subTest(path=path.name), self.assertRaises(ValueError):
                self.measure()
            path.write_bytes(before)


class V2ClosureAdversaries(unittest.TestCase):
    def fixture(self):
        f = legacy.CapacityPhysicalRequestsTests()
        runtime, owned, original, reader, saved = f.fixture()
        self.addCleanup(f.doCleanups)
        attempt = Path(runtime['root'])
        runtime.update(id='edgar-population-20261016-20',source_commit='a'*40)
        runtime['sources']={name:saved(attempt/'synthetic-sources'/Path(name).name,{'synthetic_source':name})
            for name in ('tools/earnings_open_context.py','tools/edgar_forecast_openai.py')}
        contexts_by_role={name:saved(attempt/('context-'+name+'.json'),{'synthetic_context':name})
            for name in ('controller','author')}
        runtime_bound = saved(attempt/'runtime.json',runtime)
        owner = {'status':'FAILED_NO_RETRY','runtime':runtime_bound,'error_type':'LoopHalted',
                 'retry_allowed':False}
        owner_bound = saved(attempt/'owner-result.json',owner)
        reader.read.side_effect = lambda binding,binary=False: (Path(binding['path']).read_bytes()
            if binary else engine.read(binding))
        roles={}; delivery={'status':'SEALED_FAILED_SOURCE_CAPACITY_BEFORE_CANDIDATE_REVIEW_FORECAST',
            'attempt_id':runtime['id'],'source_commit':runtime['source_commit'],
            'runtime_reviewed_sha256':runtime_bound['sha256']}
        for name, status, key in [('controller-01','COMPLETED_DECISION','controller_terminal_transport'),
                ('author-01','FAILED_NO_RETRY','author_terminal')]:
            value={'status':status,'error_type':'ValueError' if name.startswith('author') else None,
                   'final_numbered_response':'08-response.json','retry_allowed':False,'turns':8}
            bound=saved(attempt/'roles'/name/'result.json',value)
            roles[name]={'result':value}; delivery[key]={'result':bound,'result_value':value}
        rows=[]; prepared=[]
        for old in original['terminal_evidence']['requests']:
            folder=Path(old['request']['path']).parent;number=Path(old['request']['path']).name[:2]
            context=contexts_by_role[folder.name.split('-')[0]]
            count_response=saved(folder/(number+'-count.response.json'),engine.read(old['count']))
            payload=engine.read(old['request'])['payload']
            reused=dict(schema='earnings_prepared_count_handoff_v1',new_count_http_request=False,
                reused_original_provider_count=True,slot=str(folder),turn=int(number),source_context=context,
                context_receipt=context,count_receipt=old['count'],provider_count_intent=old['matching_actual_count_origins'][0],
                provider_count_response=count_response,
                provider_count_raw=engine.pin(Path(old['matching_actual_count_origins'][0]['path'].replace('.intent.json','.raw.bin'))),
                producer_source=runtime['sources']['tools/earnings_open_context.py'],
                consumer_source=runtime['sources']['tools/edgar_forecast_openai.py'],
                request_sha256=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest())
            reuse=saved(folder/(number+'-prepared-count-reuse.json'),reused)
            marker={'schema':'earnings_prepared_count_consumed_v1',
                'phase':'consumed_before_validation_and_reservation'}
            marker_binding=saved(folder/(number+'-prepared-count-consumed.json'),marker)
            rows.append(dict(binding=old['request'],physical=dict(failure=None,numbered_response=old['response'],
                intent=old['intent'],raw=old['raw']),usage={'expected_conservative_charge_nano_usd':92500}))
            prepared.append(dict(role=folder.name,number=number,reuse_binding=reuse,
                actual_generation_request=old['request'],actual_generation_completed=True,
                consumed_marker={'binding':marker_binding,'value':marker}))
        final=dict(owner_terminal=dict(binding=owner_bound,value=owner),runtime=runtime_bound,
            source_commit=runtime['source_commit'],preview=[],requests=rows,prepared_counts=prepared,
            roles=roles,accounting={'opening_prefix':{'fixture':'opening'},'snapshot':{'fixture':'closing'}})
        terminal=dict(owner_terminal=final['owner_terminal'],candidate_files={'candidate.py':None,'cases.py':None},
            code_entries=[],code_cleanup_receipts=[],Native_batches=[],
            root_results={'population-run-failure.json':{'binding':saved(attempt/'population-run-failure.json',
                dict(status='FAILED_NO_RETRY',error_type='LoopHalted',native_closure=None,retry_allowed=False))}})
        saved(attempt/'loop/round-0001-implement.failed.json',{'fixture':'failed'})
        audit=dict(schema='earnings_population_live20_closure_audit_v1',
            status='SEALED_FAILED_AUTHOR_VALUEERROR_ALL_16_FEES_SETTLED',attempt_id=runtime['id'],
            runtime=runtime_bound,source_commit=runtime['source_commit'],auditor='independent-fixture',
            terminal_evidence=terminal,checkpoints=[final])
        return reader,attempt,runtime_bound,runtime,owner_bound,owner,audit,delivery,owned,saved

    def project(self, f):
        return recovery._base_capacity_closure(*f[:8])

    def test_current_actual_shape_projection_then_original_physical_fee_checks(self):
        f=self.fixture(); before=deepcopy(f[6:8]); result=self.project(f)
        with patch.object(recovery,'_owned_requests',return_value=f[8]):
            evidence=recovery._capacity_requests(f[0],f[3],result,base_mode=True)
        self.assertEqual(len(evidence),16*6)
        self.assertEqual(f[6:8],before)
        self.assertEqual(len(result['terminal_evidence']['requests']),16)

    def test_wrong_runtime_owner_source_auditor_or_delivery_status_refused(self):
        for kind in ('runtime','owner','source','auditor','delivery'):
            f=self.fixture(); audit,delivery=f[6:8]
            if kind=='runtime':audit['runtime']=dict(audit['runtime'],sha256='f'*64)
            elif kind=='owner':audit['terminal_evidence']['owner_terminal']['value']=dict(f[5],status='RUNNING')
            elif kind=='source':audit['source_commit']='b'*40
            elif kind=='auditor':audit['auditor']='/root'
            else:delivery['status']='SCORED'
            with self.subTest(kind=kind), self.assertRaises(ValueError):self.project(f)

    def test_executed_adopted_or_candidate_closure_counterfeits_refused(self):
        for kind in ('code','cleanup','candidate','not-completed','missing-request','missing-prepared'):
            f=self.fixture(); terminal=f[6]['terminal_evidence']; final=f[6]['checkpoints'][-1]
            if kind=='code':terminal['code_entries']=['executed-call']
            elif kind=='cleanup':terminal['code_cleanup_receipts']=[{'executed':True}]
            elif kind=='candidate':terminal['candidate_files']['candidate.py']=f[2]
            elif kind=='not-completed':final['prepared_counts'][0]['actual_generation_completed']=False
            elif kind=='missing-request':final['requests'].pop()
            else:final['prepared_counts'].pop()
            with self.subTest(kind=kind), self.assertRaises(ValueError):self.project(f)

    def test_unknown_wrong_charge_or_missing_physical_count_origin_refused(self):
        for kind in ('uncertain','charge','missing-origin','count-bool','usage'):
            f=self.fixture(); result=self.project(f); row=result['terminal_evidence']['requests'][-1]
            if kind=='uncertain':f[8][-1]['status']='uncertain'
            elif kind=='charge':f[8][-1]['charged_nano_usd']+=1
            elif kind=='missing-origin':row['matching_actual_count_origins']=[]
            elif kind=='count-bool':row['count']=f[9](Path(row['count']['path']),{'input_tokens':True})
            else:
                value=engine.read(row['response']);value['usage']['total_tokens']=31
                row['response']=f[9](Path(row['response']['path']),value)
                row['raw']=f[9](Path(row['raw']['path']),{k:v for k,v in value.items() if k!='_request_id'})
            with self.subTest(kind=kind), patch.object(recovery,'_owned_requests',return_value=f[8]):
                with self.assertRaises(ValueError):recovery._capacity_requests(f[0],f[3],result,base_mode=True)

    def test_prepared_receipt_body_source_payload_and_marker_mismatch_refused(self):
        for kind in ('hash','context','producer','raw','boolean-turn','new-count','marker','duplicate'):
            f=self.fixture();final=f[6]['checkpoints'][-1];prep=final['prepared_counts'][0]
            reuse=engine.read(prep['reuse_binding']);saved=f[9]
            if kind=='hash':reuse['request_sha256']='f'*64
            elif kind=='context':reuse['source_context']=reuse['producer_source']
            elif kind=='producer':reuse['producer_source']=reuse['consumer_source']
            elif kind=='raw':
                reuse['provider_count_raw']=saved(Path(reuse['provider_count_raw']['path']),{'input_tokens':31})
            elif kind=='boolean-turn':reuse['turn']=True
            elif kind=='new-count':reuse['new_count_http_request']=True
            elif kind=='marker':
                bad=dict(prep['consumed_marker']['value'],phase='post-generation')
                prep['consumed_marker']={'binding':saved(Path(prep['consumed_marker']['binding']['path']),bad),'value':bad}
            else:final['prepared_counts'][1]=deepcopy(prep)
            if kind not in ('marker','duplicate'):
                prep['reuse_binding']=saved(Path(prep['reuse_binding']['path']),reuse)
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.project(f)

    def test_role_turn_shape_stays_bounded_and_missing_physical_rows_are_not_invented(self):
        for turns in (True,0,9,1.0):
            f=self.fixture();role=f[7]['author_terminal'];bad=dict(role['result_value'],turns=turns)
            role['result']=f[9](Path(role['result']['path']),bad);role['result_value']=bad
            f[6]['checkpoints'][-1]['roles']['author-01']['result']=bad
            with self.subTest(turns=turns),self.assertRaises(ValueError):self.project(f)


class CapacityFeedbackCarryAdversaries(unittest.TestCase):
    """Consumer tests over verified synthetic base receipts, not live admission."""
    def setUp(self):
        self.f=base_fixture.ImplementationBaseTests();self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        base=self.f.base();patch_value=self.f.new_patch(edits=[
            dict(kind='append',old_text='',new_text='\n# FAILED_PUBLIC_WIP\n'+'x'*65500)])
        public,capacity=recovery._base_capacity_delta(self.f.parent['R'],self.f.chosen,
            reply(patch_value),implementation_base=base)
        bound=self.f.f.authority
        self.failure=dict(schema='earnings_population_delivery_failure_v1',
            mode=recovery.AUTHOR_BASE_CAPACITY,failed_attempt=bound,audit=bound,
            stage='implement',error_type='ValueError',score_state='unscored',quality_assessment='not_run',
            failed_parent={'version_id':self.f.parent['id'],'source':self.f.parent['R']},
            implementation_base=base,original_decision=bound,original_decision_public=self.f.chosen,
            original_scientific_decision_sha256=digest(self.f.chosen),raw_patch_response=bound,
            public_failed_delta=public,public_failed_delta_sha256=digest(public),capacity=capacity)

    def test_controller_summary_author_original_and_comparison_base_split_stay_distinct(self):
        original={'schema':'earnings_repair_context_v1','observations':{'prior_delivery_failure':self.failure},
            'human_task':'Free new parent and R/H choice; no forced algorithm.'}
        before=deepcopy(original);view=contexts.controller_view(original)
        compact=view['observations']['prior_delivery_failure']
        self.assertEqual(original,before)  # Existing Author path receives this unchanged object.
        self.assertEqual(compact['failed_parent'],self.failure['failed_parent'])
        self.assertEqual(compact['implementation_base'],self.failure['implementation_base'])
        self.assertNotEqual(compact['failed_parent']['source'],compact['implementation_base']['source'])
        self.assertEqual(compact['original_decision_public'],self.f.chosen)
        self.assertEqual(compact['score_state'],'unscored');self.assertEqual(compact['quality_assessment'],'not_run')
        self.assertNotIn('public_failed_delta',compact)
        summary=compact['public_failed_delta_summary']
        for key in ('comparison_parent_source_sha256','implementation_base_source_sha256'):
            self.assertEqual(summary[key],self.failure['public_failed_delta'][key])
        self.assertEqual(summary['edits'],self.failure['capacity']['edits'])
        self.assertNotIn('FAILED_PUBLIC_WIP',json.dumps(view))
        self.assertFalse(self.f.f.marker.exists())

    def test_controller_refuses_changed_public_patch_even_if_same_size(self):
        for kind in ('edit','test','comparison','decision'):
            failed=deepcopy(self.failure);p=failed['public_failed_delta']
            if kind=='edit':p['edits'][0]['new_text']=p['edits'][0]['new_text'].replace('WIP','BAD')
            elif kind=='test':p['test_text']=p['test_text'].replace('repaired','changed!')
            elif kind=='comparison':p['comparison_parent_source_sha256']='f'*64
            else:p['decision_sha256']='f'*64
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                contexts.controller_view({'schema':'earnings_repair_context_v1',
                    'observations':{'prior_delivery_failure':failed}})

    def test_multiple_windows_carry_one_exact_compact_lesson_without_wip_or_tests(self):
        original=deepcopy(self.failure)
        first=completed._delivery_lessons({'recovery_context':self.failure})
        second=completed._delivery_lessons({'delivery_lessons':first})
        third=completed._delivery_lessons({'delivery_lessons':second,'recovery_context':self.failure})
        self.assertEqual(first,second);self.assertEqual(second,third);self.assertEqual(len(third),1)
        self.assertEqual(self.failure,original)
        self.assertEqual(third[0]['implementation_base'],{k:self.failure['implementation_base'][k]
            for k in ('version_id','source')})
        self.assertEqual(third[0]['failed_parent'],self.failure['failed_parent'])
        self.assertEqual(third[0]['capacity'],self.failure['capacity'])
        self.assertTrue(third[0]['qualification'].endswith('or demonstrated repair.'))
        self.assertFalse(set(third[0])&{'public_failed_delta','source_text','test_text','edits'})
        self.assertNotIn('FAILED_PUBLIC_WIP',json.dumps(third))

    def test_carry_rejects_forged_arithmetic_bool_hash_body_and_conflicting_duplicate(self):
        original=completed._delivery_lessons({'recovery_context':self.failure})
        for kind in ('arithmetic','bool','edit-bytes','limit','base-sha','hash','body','conflict'):
            bad=deepcopy(original);capacity=bad[0]['capacity']
            if kind=='arithmetic':capacity['excess_utf8_bytes']+=1
            elif kind=='bool':capacity['edit_count']=True
            elif kind=='edit-bytes':capacity['edits'][0]['new_text_utf8_bytes']+=1
            elif kind=='limit':capacity['source_limit_utf8_bytes']=131072
            elif kind=='base-sha':bad[0]['implementation_base']['source']=self.f.parent['R']
            elif kind=='hash':capacity['assembled_source_sha256']='not-a-hash'
            elif kind=='body':bad[0]['public_failed_delta']=self.failure['public_failed_delta']
            else:
                duplicate=deepcopy(bad[0]);duplicate['raw_patch_response']=dict(duplicate['raw_patch_response'],sha256='f'*64)
                bad.append(duplicate)
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                completed._delivery_lessons({'delivery_lessons':bad})

    def test_ordinary_legacy_replay_shape_and_v1_compact_lesson_are_preserved(self):
        self.assertIsNone(completed._delivery_lessons({}))
        fixture=legacy.CapacityFailureUnitTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        public,size=recovery._capacity_delta(fixture.parent,fixture.selected,legacy.response(fixture.delta))
        v1=deepcopy(self.failure);v1.pop('implementation_base');v1['mode']=recovery.AUTHOR_CAPACITY
        v1.update(public_failed_delta=public,public_failed_delta_sha256=digest(public),capacity=size)
        # Different failed-attempt identity prevents intentional duplicate-conflict check.
        v1['failed_attempt']=dict(v1['failed_attempt'],sha256='e'*64)
        first=completed._delivery_lessons({'recovery_context':v1})
        both=completed._delivery_lessons({'delivery_lessons':first,'recovery_context':self.failure})
        self.assertEqual(both[0],first[0]);self.assertEqual(len(both),2)
        self.assertEqual(both[1]['mode'],recovery.AUTHOR_BASE_CAPACITY)
        self.assertNotIn('implementation_base',both[0])


class ConsecutiveFailureDispatchAdversaries(unittest.TestCase):
    """Public dispatcher cycle/depth checks; heavy historical replay is stubbed."""
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='failure-chain-dispatch-')
        self.addCleanup(temporary.cleanup);self.root=Path(temporary.name).resolve()
        self.repo=self.root/'repo';self.repo.mkdir();self.ledger=self.root/'budget.sqlite3'
        self.plan={'path':str(self.repo/recovery.PLAN),'sha256':'a'*64}
        for name,value in [('OWNED',self.root),('LEDGER',self.ledger),('REPO',self.repo)]:
            active=patch.object(recovery.resume,name,value);active.start();self.addCleanup(active.stop)

    def binding(self,number):
        return {'path':str(self.root/'attempts'/f'edgar-population-20261016-{number:02d}'/
            'population-run-failure.json'),'sha256':f'{number:064x}'}

    def call(self,binding):
        return recovery.load(binding,root=self.root,ledger=self.ledger,repo=self.repo,plan_binding=self.plan)

    def test_two_distinct_failures_dispatch_and_exception_does_not_poison_next_load(self):
        calls=[]
        def transfer(binding,**kwargs):
            calls.append(binding)
            if len(calls)==1:return self.call(self.binding(20))
            return {'synthetic_verified_origin':'same-scientific-predecessor'}
        with patch.object(recovery,'_read_plan',return_value={'recovery_mode':recovery.AUTHOR_BASE_CAPACITY}),\
             patch.object(recovery,'_load_author_capacity',side_effect=transfer):
            self.assertEqual(self.call(self.binding(21)),{'synthetic_verified_origin':'same-scientific-predecessor'})
            self.assertEqual(calls,[self.binding(21),self.binding(20)])
        with patch.object(recovery,'_read_plan',return_value={'recovery_mode':recovery.AUTHOR_BASE_CAPACITY}),\
             patch.object(recovery,'_load_author_capacity',side_effect=ValueError('invented failed historical proof')):
            with self.assertRaises(ValueError):self.call(self.binding(21))
        with patch.object(recovery,'_read_plan',return_value={'recovery_mode':recovery.AUTHOR_BASE_CAPACITY}),\
             patch.object(recovery,'_load_author_capacity',return_value={'subsequent':'independent invocation'}):
            self.assertEqual(self.call(self.binding(21)),{'subsequent':'independent invocation'})

    def test_repeated_failed_attempt_cycle_is_rejected_before_unbounded_replay(self):
        calls=[]
        def transfer(binding,**kwargs):
            calls.append(binding)
            # Bound the missing-guard baseline safely; do not rely on Python recursion failure.
            if len(calls)>=3:return {'unprotected_cycle':'wrongly accepted'}
            return self.call(binding)
        with patch.object(recovery,'_read_plan',return_value={'recovery_mode':recovery.AUTHOR_BASE_CAPACITY}),\
             patch.object(recovery,'_load_author_capacity',side_effect=transfer):
            with self.assertRaises(ValueError):self.call(self.binding(21))
        self.assertLessEqual(len(calls),2)

    def test_same_path_with_changed_hash_and_interleaved_completed_route_still_cycles(self):
        calls=[]
        def transfer(binding,**kwargs):
            calls.append(binding)
            if len(calls)>=3:return {'unprotected_cycle':'wrongly accepted'}
            # The completed-loader call is a declared heavy replay seam. It
            # re-enters recovery, as a real completed-window origin can do.
            return completed.load({'fixture':'interleaved completed boundary'},
                root=self.root,ledger=self.ledger,repo=self.repo)
        changed=dict(self.binding(21),sha256='f'*64)
        with patch.object(recovery,'_read_plan',return_value={'recovery_mode':recovery.AUTHOR_BASE_CAPACITY}),\
             patch.object(recovery,'_load_author_capacity',side_effect=transfer),\
             patch.object(completed,'load',side_effect=lambda *a,**k:self.call(changed)):
            with self.assertRaises(ValueError):self.call(self.binding(21))
        self.assertLessEqual(len(calls),2)

    def test_more_than_fifty_unique_failed_origins_is_rejected(self):
        calls=[]
        def transfer(binding,**kwargs):
            calls.append(binding)
            if len(calls)>=51:return {'unprotected_depth':'wrongly accepted'}
            return self.call(self.binding(len(calls)+1))
        with patch.object(recovery,'_read_plan',return_value={'recovery_mode':recovery.AUTHOR_BASE_CAPACITY}),\
             patch.object(recovery,'_load_author_capacity',side_effect=transfer):
            with self.assertRaises(ValueError):self.call(self.binding(1))
        self.assertLessEqual(len(calls),50)


class ChainedHistoricalPlanAdversaries(unittest.TestCase):
    """Real original-reader source checks; immutable Git bytes are invented."""
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='failure-chain-plan-')
        self.addCleanup(temporary.cleanup);self.root=Path(temporary.name).resolve()
        self.repo=self.root/'repo';self.repo.mkdir();self.ledger=self.root/'budget.sqlite3'
        self.value={'schema':'supervisor_bottleneck_plan_v1','failed_attempt':{'fixture':'prior20'},
            'recovery_mode':recovery.AUTHOR_BASE_CAPACITY}
        self.bound=save(self.repo/recovery.PLAN,self.value)
        self.original=Path(self.bound['path']).read_bytes()
        self.reader=recovery.history._Reader(self.root,self.ledger,self.repo,'edgar-population-20261016-21')
        self.reader.commit='a'*40;self.reader.sources={(self.bound['path'],self.bound['sha256'])}
        # This is the explicit historical Git-byte fixture seam, not real Git proof.
        self.reader.cache[recovery.PLAN]=self.original

    def read(self,*,bound=None,reader=None,**paths):
        return recovery._read_plan(self.bound if bound is None else bound,
            root=paths.get('root',self.root),ledger=paths.get('ledger',self.ledger),
            repo=paths.get('repo',self.repo),historical_reader=self.reader if reader is None else reader)

    def test_old_original_plan_bytes_survive_current_plan_replacement(self):
        Path(self.bound['path']).write_text('{"current_plan":"different"}')
        self.assertEqual(self.read(),self.value)

    def test_wrong_plan_binding_source_commit_or_reader_scope_refused(self):
        for kind in ('path','hash','unregistered','commit','reader','root','ledger','repo'):
            with self.subTest(kind=kind):
                args={};before_commit=self.reader.commit;before_sources=self.reader.sources
                if kind=='path':args['bound']=dict(self.bound,path=str(self.root/'foreign-plan.json'))
                elif kind=='hash':args['bound']=dict(self.bound,sha256='f'*64)
                elif kind=='unregistered':self.reader.sources=set()
                elif kind=='commit':self.reader.commit='not-a-commit'
                elif kind=='reader':args['reader']=Mock()
                else:args[kind]=self.root/('wrong-'+kind)
                with self.assertRaises(ValueError):self.read(**args)
                self.reader.commit=before_commit;self.reader.sources=before_sources

    def test_changed_original_historical_plan_bytes_refused_even_if_current_file_matches(self):
        self.reader.cache[recovery.PLAN]=self.original+b' '
        with self.assertRaisesRegex(ValueError,'hash differs'):self.read()


class ChainedOriginProducerAdversaries(unittest.TestCase):
    """Real origin reader/producer; only full predecessor loaders are seams."""
    def setUp(self):
        self.p=ChainedHistoricalPlanAdversaries();self.p.setUp();self.addCleanup(self.p.doCleanups)
        self.root,self.repo,self.ledger,self.reader=self.p.root,self.p.repo,self.p.ledger,self.p.reader
        self.reader.ids.update({'edgar-population-20261016-18','edgar-population-20261016-20'})
        self.previous=save(self.root/'attempts/edgar-population-20261016-18/population-run-result.json',
            {'fixture':'verified completed18 boundary'})
        self.prior=save(self.root/'attempts/edgar-population-20261016-20/population-run-failure.json',
            {'fixture':'verified failed20 boundary'})
        self.feedback=save(self.root/'attempts/edgar-population-20261016-18/feedback.json',
            {'kind':'review_rejected','score_state':'unscored','results':[]})
        self.last_score=save(self.root/'attempts/edgar-population-20261016-18/last-score-reference.json',
            {'fixture':'opaque prior score binding, no real QA/scorer'})
        self.bare={'population':{'observations':[],'stable_id':'synthetic unchanged active R7'},
            'previous_result':self.previous,'feedback':self.feedback,
            'research_feedback':engine.read(self.feedback),'last_scored_feedback':self.last_score,
            'reference_candidate':{'reference_only':True,'id':'synthetic rejected18'},
            'evidence':[self.previous,self.feedback,self.last_score]}
        literal=BaseCapacityLiteralAdversaries();literal.setUp();self.addCleanup(literal.doCleanups)
        public,capacity=literal.measure()
        bound=save(self.root/'prior20-audit.json',{'fixture':'verified audit boundary'})
        self.failure=dict(schema='earnings_population_delivery_failure_v1',
            mode=recovery.AUTHOR_BASE_CAPACITY,failed_attempt=self.prior,audit=bound,
            stage='implement',error_type='ValueError',score_state='unscored',quality_assessment='not_run',
            failed_parent={'version_id':'a'*64,'source':literal.parent},
            implementation_base={'version_id':'b'*64,'source':literal.base_binding,'adopted':False},
            original_decision=bound,original_decision_public=literal.selected,
            original_scientific_decision_sha256=digest(literal.selected),raw_patch_response=bound,
            public_failed_delta=public,public_failed_delta_sha256=digest(public),capacity=capacity)
        self.verified20=deepcopy(self.bare)
        self.verified20['recovery_context']=deepcopy(self.failure)
        self.verified20['evidence']+=[self.prior,bound]
        self.resumed={'schema':'earnings_population_campaign_resume_v1',
            'previous_result':self.previous,'prior_failed_attempt':self.prior,'plan':self.p.bound,'repair':None}
        self.runtime={'source_commit':self.reader.commit,'sources':{recovery.PLAN:self.p.bound}}
        self.refresh()

    def refresh(self,*,origin=None):
        folder=self.root/'inputs/edgar-population-20261016-21'
        self.study={'campaign_resume':save(folder/'campaign-resume.json',self.resumed),
            'campaign_origin':save(folder/'campaign-origin.json',self.verified20 if origin is None else origin)}

    def origin(self):
        return recovery._capacity_origin(self.reader,self.runtime,self.study,
            root=self.root,ledger=self.ledger,repo=self.repo)

    def recover(self,bound,**kwargs):
        self.reader.read(bound)  # Actual binding/path/byte check before the heavy replay seam.
        self.assertEqual(bound,self.prior)
        self.assertIs(kwargs['historical_reader'],self.reader)
        plan=recovery._read_plan(kwargs['plan_binding'],root=self.root,
            ledger=self.ledger,repo=self.repo,historical_reader=kwargs['historical_reader'])
        self.assertEqual(plan,self.p.value)
        return deepcopy(self.verified20)

    def test_second_failure_reads_exact_prior_recovery_not_bare_completed_predecessor(self):
        before=deepcopy(self.verified20)
        with patch.object(recovery,'load',side_effect=self.recover) as recovered,\
             patch.object(completed,'load',return_value=deepcopy(self.bare)) as ordinary:
            actual=self.origin()
        self.assertEqual(actual,before);self.assertEqual(self.verified20,before)
        recovered.assert_called_once();ordinary.assert_not_called()
        self.assertNotEqual(actual,self.bare)
        self.assertEqual(actual['previous_result'],self.previous)
        self.assertEqual(actual['last_scored_feedback'],self.last_score)

    def test_wrong_predecessor_original_plan_or_saved_origin_refused(self):
        for kind in ('previous-result','plan','prior-hash','prior-path','origin','resume-bytes','origin-bytes'):
            with self.subTest(kind=kind):
                original=deepcopy(self.resumed)
                if kind=='previous-result':self.resumed['previous_result']=dict(self.previous,sha256='f'*64)
                elif kind=='plan':self.resumed['plan']=dict(self.p.bound,sha256='f'*64)
                elif kind=='prior-hash':self.resumed['prior_failed_attempt']=dict(self.prior,sha256='f'*64)
                elif kind=='prior-path':self.resumed['prior_failed_attempt']=dict(self.prior,path=str(self.root/'foreign-failure.json'))
                self.refresh(origin=self.bare if kind=='origin' else None)
                if kind in ('resume-bytes','origin-bytes'):
                    key='campaign_resume' if kind=='resume-bytes' else 'campaign_origin'
                    path=Path(self.study[key]['path']);path.write_bytes(path.read_bytes()+b' ')
                with patch.object(recovery,'load',side_effect=self.recover),\
                     patch.object(completed,'load',return_value=deepcopy(self.bare)):
                    with self.assertRaises(ValueError):self.origin()
                self.resumed=original;self.refresh()

    def test_origin_without_prior_failure_keeps_original_completed_loader_route(self):
        self.resumed.pop('prior_failed_attempt');self.refresh(origin=self.bare)
        with patch.object(recovery,'load',side_effect=AssertionError('No invented failure replay')),\
             patch.object(completed,'load',return_value=deepcopy(self.bare)) as ordinary:
            self.assertEqual(self.origin(),self.bare)
        ordinary.assert_called_once_with(self.previous,root=self.root,ledger=self.ledger,repo=self.repo)

    def test_attaching_new_failure_preserves_prior20_only_as_exact_compact_lesson(self):
        before=deepcopy(self.verified20)
        new=deepcopy(self.failure)
        new['failed_attempt']=save(self.root/'attempts/edgar-population-20261016-21/population-run-failure.json',
            {'fixture':'new verified failed21 boundary'})
        new['raw_patch_response']=save(self.root/'attempts/edgar-population-20261016-21/public-response.json',
            {'fixture':'same literal patch from a distinct verified failed21 boundary'})
        actual=recovery._attach_capacity_failure(self.verified20,new)
        self.assertEqual(self.verified20,before);self.assertEqual(actual['recovery_context'],new)
        self.assertEqual(actual['population'],before['population'])
        self.assertEqual(actual['previous_result'],before['previous_result'])
        self.assertEqual(actual['feedback'],before['feedback'])
        self.assertEqual(actual['last_scored_feedback'],before['last_scored_feedback'])
        lesson=actual['delivery_lessons'];self.assertEqual(len(lesson),1)
        self.assertEqual(lesson[0]['failed_attempt'],self.prior)
        self.assertEqual(lesson[0]['capacity'],self.failure['capacity'])
        self.assertFalse(set(lesson[0])&{'public_failed_delta','test_text','source_text','edits'})
        self.assertNotIn('TOKEN_00',json.dumps(lesson));self.assertNotIn('CASES=',json.dumps(lesson))
        self.assertEqual(completed._delivery_lessons({'delivery_lessons':lesson}),lesson)
        newest=deepcopy(new)
        newest['failed_attempt']=save(self.root/'attempts/edgar-population-20261016-22/population-run-failure.json',
            {'fixture':'third verified failed22 boundary'})
        third=recovery._attach_capacity_failure(actual,newest)
        self.assertEqual(len(third['delivery_lessons']),2)
        self.assertEqual(third['delivery_lessons'][0],lesson[0])
        self.assertFalse(any('public_failed_delta' in row for row in third['delivery_lessons']))

    def test_attaching_failure_refuses_corrupt_inherited_compact_lesson(self):
        inherited=deepcopy(self.verified20)
        inherited['delivery_lessons']=completed._delivery_lessons(inherited)
        inherited['delivery_lessons'][0]['capacity']['excess_utf8_bytes']+=1
        with self.assertRaises(ValueError):recovery._attach_capacity_failure(inherited,self.failure)


if __name__ == '__main__':
    unittest.main()
