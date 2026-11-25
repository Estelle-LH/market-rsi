"""Public-WIP annotation; synthetic originals/temp ledger, never code execution.

The fee fixture substitutes incident pins/grant only. Receipt hashing, original
physical/decoder/settlement checks and literal edit assembly are real. Separate
receiving fixtures explicitly substitute historical proof and synthetic tokens.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import socket
import unittest
from unittest.mock import Mock, patch

import earnings_population_source_guard_repair as m
import earnings_population_campaign_context as contexts
import earnings_population_services as services
import earnings_population_roles as population_roles
import earnings_open_context as packing
import earnings_open_roles as roles
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_source_guard_reconcile as fee_fixture
import test_earnings_population_recovery_author as receiving
import test_earnings_open_roles as role_fixture


def response(value):
    return dict(status='completed', error=None, output=[dict(type='message', role='assistant',
        status='completed', content=[dict(type='output_text', text=json.dumps(value))])])


class RepairFixture:
    """Invented exact incident pins; no production state or expensive loader."""
    def __init__(self, test):
        f = self.fee = fee_fixture.SourceGuardOperator(); f.setUp(); test.addCleanup(f.doCleanups)
        self.root, self.save = f.root, f.save
        parent_path = self.root/'attempts/edgar-population-20261016-29/roles/author-01/candidate.py'
        source = "PROGRAM={'axis':'R'}\ndef run(payload): return None\n#"+'p'*61000+'\n'
        source += ''.join(f'# UNIQUE_{i}\n' for i in range(5))
        parent_path.parent.mkdir(parents=True, exist_ok=True); parent_path.write_text(source)
        r = engine.pin(parent_path)
        h = self.save(self.root/'H.py', {'inert': True})
        self.parent = dict(id=digest({'R':r['sha256'],'H':h['sha256']}),R=r,H=h)
        cslot = Path(f.runtime['root'])/'roles/controller-01'
        f.runtime['slots']['controller'] = [str(cslot)]
        f.runtime['limits']['controller'] = dict(max_input_tokens=32000,max_output_tokens=16384,wall_seconds=900)
        f.change('runtime',f.runtime)
        owner=f.read('owner_result');owner['runtime']=f.evidence['runtime'];f.change('owner_result',owner)
        boundary=f.read('role_boundary');boundary['runtime']=f.evidence['runtime'];f.change('role_boundary',boundary)
        prompt=dict(active_versions=[self.parent['id']],explorers=[self.parent['id']],feedback_sha256='b'*64)
        public=dict(schema='earnings_capacity_decision_v1',axis='R',component='research_policy',
            parent_pair_sha256=self.parent['id'],feedback_sha256='b'*64,hypothesis='Synthetic public parser repair.',
            expected_effect='earnings-shadow-v1|research_policy|input_tokens|lower|1|score_nonregression|matched_trial_only',
            retire_branch_id='none')
        raw=response(public); chosen=population_roles.decode_proposal(raw,prompt)
        self.selected=population_roles.scientific(chosen)
        self.patch=dict(decision_sha256=digest(self.selected),parent_source_sha256=r['sha256'],
            edits=[dict(kind='replace',old_text=f'# UNIQUE_{i}\n',new_text=f'# REPAIR_{i} '+'z'*1000+'\n')for i in range(5)],
            test_text="CASES=[{'input':{},'expected':None}]\n# PUBLIC_TEST_SENTINEL")
        effective=dict(decision=self.selected,decision_sha256=digest(self.selected),parent_source=r,
            parent_source_sha256=r['sha256'],research_context=dict(parent_version_id=self.parent['id']))
        f.request['payload']['input']=[dict(role='user',content=json.dumps(effective))]
        f.change('request',f.request)
        intent=f.read('http_intent');intent.update(complete_reservation=f.request,
            request_receipt_sha256=f.evidence['request']['sha256'],payload=dict(f.request['payload'],
                max_output_tokens=49152,service_tier='default',store=False));f.change('http_intent',intent)
        f.raw['output'][-1]['content'][0]['text']=json.dumps(self.patch)
        f.change('raw_response',f.raw)
        crequest=dict(payload=dict(model='gpt-6.1-sol',input=[dict(role='user',content=json.dumps(prompt))]),
            request_id='synthetic-controller',reserved_nano_usd=100)
        request=self.save(cslot/'01-request.json',crequest)
        rresponse=self.save(cslot/'01-response.json',raw)
        stem=cslot/'http-00000000-0000-0000-0000-000000000002'
        intent=self.save(stem.with_suffix('.intent.json'),dict(endpoint='/v1/responses',complete_reservation=crequest,
            request_receipt_sha256=request['sha256'],payload=dict(crequest['payload'],max_output_tokens=16384,
                service_tier='default',store=False)))
        physical_raw=self.save(stem.with_suffix('.raw.bin'),raw)
        sidecar=self.save(stem.with_suffix('.response.json'),raw)
        result=dict(status='COMPLETED_DECISION',turns=1,final_numbered_response='01-response.json')
        result_bound=self.save(cslot/'result.json',result)
        effective_bound=self.save(f.slot/'effective-input.json',effective)
        assembled=m._edit_source(source,self.patch['edits']).encode()
        self.audit=dict(attempt_id=f.runtime['id'],runtime=f.evidence['runtime'],source_commit=f.runtime['source_commit'],
            downstream_not_reached={key:False for key in ('candidate','model_Review','forecast','score','reconcile','new_feedback')},
            milestones=[dict(kind='CONTROLLER_COMPLETED_ALL_PHYSICAL_REQUESTS',result=dict(binding=result_bound,value=result),
                rows=[dict(request=request,response=rresponse,physical_intent=intent,physical_raw=physical_raw,physical_sidecar=sidecar)],
                public_decision=chosen,public_decision_sha256=digest(chosen))],
            author_first_completed=dict(effective_input=effective_bound,normalized_controller_choice=self.selected,
                normalized_choice_sha256=digest(self.selected),parent_source=r),
            inert_unaccepted_public_delta=dict(raw_response=f.evidence['raw_response'],parent_source=r,
                decision_sha256=digest(self.selected),parent_utf8_bytes=len(source.encode()),assembled_utf8_bytes=len(assembled),
                assembled_sha256=hashlib.sha256(assembled).hexdigest(),source_limit_utf8_bytes=65536,
                excess_utf8_bytes=len(assembled)-65536,literal_edit_count=5,
                test_utf8_bytes=len(self.patch['test_text'].encode()),test_sha256=hashlib.sha256(self.patch['test_text'].encode()).hexdigest(),
                candidate_executed=False,source_or_test_written=False))
        evidence=f.bound(); self.proof=json.loads(Path(evidence['path']).read_bytes())
        booked=m.fees.reconcile_source_guard_received_raw_at_ceiling(evidence)
        settlement=self.save(self.root/'SOURCE30-FEE-SETTLEMENT.json',dict(
            schema='earnings_actual30_root_settlement_result_v1',id=f.runtime['id'],evidence=evidence,
            actual_charge_known=False,retry_allowed=False,original_failure_preserved=True,operator_return=booked))
        self.config=dict(schema=m.POLICY,apply_to_attempt='edgar-population-20261016-31',round_index=1,
            previous_result=self.save(self.root/'attempts/edgar-population-20261016-29/population-run-result.json',{'complete':True}),
            parent_version_id=self.parent['id'],parent_source=r,fee_evidence=evidence,settlement=settlement,
            role_audit=self.save(self.root/'synthetic-role-audit.json',self.audit),human_authorization='Explicit synthetic human parser repair.')
        state=dict(versions={self.parent['id']:self.parent},stable_id='protected',explorers=[self.parent['id']])
        self.feedback=self.save(self.root/'feedback.json',dict(public_original=True))
        self.origin=dict(population=state,research_feedback=engine.read(self.feedback),previous_result=self.config['previous_result'])
        self.origin_bound=self.save(self.root/'origin.json',self.origin)
        self.runtime=dict(id=self.config['apply_to_attempt'],forecast_study=self.save(self.root/'study.json',dict(campaign_origin=self.origin_bound)))
        self.packet=dict(round_index=1,population=state,feedback=self.feedback)

    def delivery(self):
        return m._delivery(self.config,self.parent)


class PublicEvidenceTests(unittest.TestCase):
    def fixture(self):
        return RepairFixture(self)

    def test_exact_originals_literal_bytes_and_readonly_settlement_no_adoption(self):
        f=self.fixture(); before=f.fee.db.total_changes
        with patch.object(m.fees,'_book',side_effect=AssertionError('NO BOOKING')):
            delivered=f.delivery()
        self.assertEqual(f.fee.db.total_changes,before)
        self.assertEqual(delivered['public_failed_delta'],f.patch)
        self.assertEqual(delivered['original_decision_public'],f.selected)
        self.assertGreater(delivered['capacity']['excess_utf8_bytes'],0)
        self.assertEqual(delivered['delivery_status'],'received_but_unaccepted')
        self.assertNotIn('candidate',delivered);self.assertNotIn('author_stage_reuse',delivered)

    def test_closed_incident_or_public_decision_raw_parent_tamper_refuses(self):
        f=self.fixture()
        for path in (Path(f.config['role_audit']['path']),Path(f.config['parent_source']['path']),
                     Path(f.proof['raw_response']['path'])):
            original=path.read_bytes();path.write_bytes(original+b' ')
            with self.subTest(path=path.name),self.assertRaises(ValueError):f.delivery()
            path.write_bytes(original)
        changed=deepcopy(f.audit);changed['milestones'][0]['public_decision']['hypothesis']='forged'
        f.config['role_audit']=f.save(Path(f.config['role_audit']['path']),changed)
        with self.assertRaises(ValueError):f.delivery()

    def test_false_candidate_quality_or_inert_byte_diagnosis_refuses(self):
        f=self.fixture()
        for key in ('candidate','model_Review','forecast','score'):
            changed=deepcopy(f.audit);changed['downstream_not_reached'][key]=True
            f.config['role_audit']=f.save(Path(f.config['role_audit']['path']),changed)
            with self.subTest(key=key),self.assertRaises(ValueError):f.delivery()
        changed=deepcopy(f.audit);changed['inert_unaccepted_public_delta']['assembled_utf8_bytes']+=1
        f.config['role_audit']=f.save(Path(f.config['role_audit']['path']),changed)
        with self.assertRaises(ValueError):f.delivery()

    def test_settlement_wrong_policy_or_ledger_row_is_not_public_repair_authority(self):
        f=self.fixture();path=Path(f.config['settlement']['path']);original=engine.read(f.config['settlement'])
        for key,value in (('actual_charge_known',True),('refund_nano_usd',1),('policy','other')):
            altered=deepcopy(original);altered['operator_return'][key]=value
            f.config['settlement']=f.save(path,altered)
            with self.subTest(key=key),self.assertRaises(ValueError):f.delivery()
        f.config['settlement']=f.save(path,original)
        f.fee.db.execute('UPDATE requests SET charged=charged-1 WHERE id=?',(f.fee.request['request_id'],))
        with self.assertRaises(ValueError):f.delivery()

    def test_foreign_binding_refused_before_body_read(self):
        f=self.fixture();f.config['role_audit']=dict(path='/foreign/QA.json',sha256='a'*64)
        with self.assertRaises(ValueError):f.delivery()

    def test_exact_first_round_assignment_leaves_verified_origin_unchanged(self):
        f=self.fixture();before=deepcopy(f.origin)
        with patch.object(m,'_policy',return_value=f.config):result=m.repair_evidence(f.runtime,f.packet)
        self.assertEqual(result['repair_assignment']['parent_version_id'],f.parent['id'])
        self.assertEqual(engine.read(f.origin_bound),before);self.assertEqual(f.origin,before)
        self.assertEqual(result['delivery']['public_failed_delta'],f.patch)

    def test_absent_policy_other_window_and_later_round_are_legacy_noop(self):
        f=self.fixture()
        with patch.object(m,'_policy',return_value=None),patch.object(m,'_delivery',side_effect=AssertionError):
            self.assertIsNone(m.repair_evidence(f.runtime,f.packet))
        for runtime,packet in ((dict(f.runtime,id='edgar-population-20261016-32'),f.packet),
                               (f.runtime,dict(f.packet,round_index=2))):
            with patch.object(m,'_policy',return_value=f.config),patch.object(m,'_delivery',side_effect=AssertionError):
                self.assertIsNone(m.repair_evidence(runtime,packet))

    def test_wrong_current_parent_prior_result_and_nonexact_policy_refuse(self):
        f=self.fixture()
        for key,value in (('parent_version_id','a'*64),('parent_source',dict(f.parent['R'],sha256='b'*64)),
                          ('previous_result',dict(f.config['previous_result'],sha256='c'*64)),('round_index',True)):
            config=dict(f.config,**{key:value})
            with patch.object(m,'_policy',return_value=config),self.subTest(key=key),self.assertRaises(ValueError):
                m.repair_evidence(f.runtime,f.packet)

    def test_original_source_bound_plan_uses_git_not_later_current_file(self):
        from earnings_population_continuation import _git
        raw=json.dumps(dict(public_evidence_repair={'original':'policy'})).encode()
        bound=dict(path=str(Path(m.__file__).resolve().parents[1]/m.PLAN),sha256=hashlib.sha256(raw).hexdigest())
        runtime=dict(source_commit='a'*40,sources={m.PLAN:bound})
        with patch('earnings_population_continuation._git',return_value=raw)as git:
            self.assertEqual(m._policy(runtime),{'original':'policy'})
            self.assertEqual(git.call_args.args[1:],('a'*40,m.PLAN))
        with patch('earnings_population_continuation._git',return_value=raw+b' '),self.assertRaises(ValueError):m._policy(runtime)

    def test_compact_controller_full_author_and_first_final_pack_keep_exact_evidence(self):
        f=self.fixture();delivery=f.delivery()
        full=dict(schema='earnings_repair_context_v1',observations=dict(prior_delivery_failure=delivery))
        compact=contexts.controller_view(full);failed=compact['observations']['prior_delivery_failure']
        self.assertNotIn('public_failed_delta',failed);self.assertEqual(full['observations']['prior_delivery_failure'],delivery)
        self.assertEqual(failed['original_decision_public'],f.selected)
        self.assertNotIn(f.patch['test_text'],json.dumps(compact))
        # Original format and packer; counts are deliberately synthetic, not provider-fit proof.
        fmt=roles._format('earnings_population_delta_author_v1',{'decision_sha256':{'type':'string'},
            'parent_source_sha256':{'type':'string'},'edits':{'type':'array'},'test_text':{'type':'string'}})
        prompt=dict(research_context=dict(prior_delivery_failure=delivery),parent_source_text=Path(f.parent['R']['path']).read_text())
        request=dict(model='gpt-6.1-sol',instructions='Synthetic original Author instructions',tool_choice='none',text={'format':fmt},
            input=[dict(role='user',content=json.dumps(prompt)),dict(type='reasoning',id='opaque',encrypted_content='x'*40000),
                dict(type='function_call',name='search_literature',call_id='old',arguments='{}'),
                dict(type='function_call_output',call_id='old',output=json.dumps({'older_public_observation':'x'*10000})),
                dict(type='message',role='assistant',content=[dict(type='output_text',text='Public progress only.')])])
        client=Mock();client.post.side_effect=[{'input_tokens':96001}]*3+[{'input_tokens':50000}]
        packed=packing.pack(client,request,dict(max_input_tokens=96000),f.root,8,author_final=True)
        self.assertEqual(packed['input'][0],request['input'][0])
        delivered=json.loads(packed['input'][0]['content'])
        self.assertEqual(delivered['research_context']['prior_delivery_failure']['public_failed_delta'],f.patch)
        self.assertEqual(delivered['parent_source_text'],Path(f.parent['R']['path']).read_text())


class ExistingRoleReceivingTests(unittest.TestCase):
    def fixture(self):
        f=receiving.RecoveryAuthorDelivery();f.setUp();self.addCleanup(f.doCleanups)
        del f.origin['recovery_context'];f.refresh()
        selected=dict(schema='earnings_capacity_decision_v1',axis='R',component='research_policy',
            parent_pair_sha256=f.version['id'],feedback_sha256=digest(f.feedback_binding),
            hypothesis='Original public WIP hypothesis, not a new model response.',
            expected_effect='earnings-shadow-v1|research_policy|input_tokens|lower|1|score_nonregression|matched_trial_only')
        delta=dict(decision_sha256=digest(selected),parent_source_sha256=f.version['R']['sha256'],
            edits=[dict(kind='replace',old_text='SYNTHETIC_OLD_LITERAL',new_text='SYNTHETIC_PUBLIC_WIP_BODY')],
            test_text='CASES=[]\n# FULL_PUBLIC_FAILED_TESTS')
        delivery=dict(schema='earnings_population_public_wip_evidence_v1',mode=m.MODE,
            stage='implement',delivery_status='received_but_unaccepted',quality_assessment='not_run',
            public_failed_delta=delta,public_failed_delta_sha256=digest(delta),
            original_decision_public=selected,original_scientific_decision_sha256=digest(selected),
            capacity=dict(assembled_utf8_bytes=65570,excess_utf8_bytes=34,source_limit_utf8_bytes=65536))
        annotation=dict(delivery=delivery,repair_assignment=dict(schema='earnings_population_human_repair_v1',
            parent_version_id=f.version['id'],human_authorization='Explicit inert repair assignment.'))
        # Only historical incident authentication is substituted in this role
        # fixture. Above tests exercise the real authentication on temp originals.
        self.addCleanup(patch.stopall)
        patch.object(m,'repair_evidence',return_value=annotation).start()
        return f,annotation

    def test_existing_services_author_physical_payload_full_wip_and_normal_new_delta(self):
        f,annotation=self.fixture()
        f.recovery=deepcopy(annotation['delivery'])
        # Existing test invokes real Services, Native case, Broker, DeltaAuthor
        # and original role loop with explicitly synthetic counted generations.
        f.test_services_author_first_physical_request_gets_exact_offline_diagnosis()
        self.assertNotIn('recovery_context',f.origin)
        self.assertNotIn('author_stage_reuse',f.origin)
        self.assertEqual(f.context()['repair_assignment'],annotation['repair_assignment'])

    def test_existing_services_controller_physical_packet_summary_and_real_new_choice(self):
        import earnings_population as pool
        f,annotation=self.fixture()
        # Make the assigned source an actual active explorer, retaining the
        # original stable anchor. The case is registered for the stable C pair.
        r=f.fixture.file('active-repair-R.py',Path(f.version['R']['path']).read_text()+'\n# active repair explorer\n')
        child=pool.version(r,f.version['H'],parent=f.version['id'],axis='R',method='Synthetic active repair parent',
                           evidence=[f.public_evidence])
        f.state=pool.retain(f.state,child,reason='Synthetic retained explorer',evidence=[f.public_evidence])
        f.origin['population']=f.state;f.refresh()
        annotation['repair_assignment']['parent_version_id']=child['id']
        case=f.fixture.prepare(resident=f.resident)
        owner=services.Services.__new__(services.Services)
        owner.runtime,owner.native_root=f.runtime,f.root
        owner.runner,owner.literature,owner.traces,owner.authored=Mock(),Mock(),{},{}
        owner.case=Mock(return_value=case)
        transport=role_fixture.OpenRoleTests();transport.setUp();self.addCleanup(transport.doCleanups)
        template=transport.service(max_turns=1)
        chosen=dict(transport.choice(),parent_pair_sha256=child['id'],
                    feedback_sha256=digest(f.feedback_binding),retire_branch_id='none')
        transport.generations=[transport.message(chosen)]
        owner.contexts={'controller':(template.binding,{'budget':transport.budget,'client_factory':transport.factory})}
        with patch.object(services,'resident',return_value=deepcopy(f.resident)), \
             patch.object(roles,'budgeted_response',side_effect=transport.fake_paid):
            result=owner.controller(f.packet,str(transport.slot))
        actual=json.loads(transport.requests[0]['input'][0]['content'])
        delivered=actual['research_context']['observations']['prior_delivery_failure']
        self.assertEqual(actual['repair_assignment'],annotation['repair_assignment'])
        self.assertNotIn('public_failed_delta',delivered)
        self.assertEqual(delivered['original_decision_public'],annotation['delivery']['original_decision_public'])
        self.assertNotIn('SYNTHETIC_PUBLIC_WIP_BODY',json.dumps(actual))
        self.assertEqual(engine.read(result)['parent_pair_sha256'],child['id'])
        self.assertEqual(owner.campaign_context['research_context']['observations']['prior_delivery_failure'],annotation['delivery'])
        self.assertFalse((transport.slot/'controller-stage-reuse.json').exists())


@unittest.skipUnless(os.environ.get('RUN_SOURCE30_PUBLIC_REPAIR')=='1','explicit original30 public-only opt-in')
class ActualSource30PublicEvidence(unittest.TestCase):
    def test_original30_readonly_annotation_65570_34_no_candidate(self):
        repo=Path(m.__file__).resolve().parents[1]
        config=json.loads((repo/m.PLAN).read_bytes())['public_evidence_repair']
        origin=json.loads((m.fees.ROOT/'inputs/edgar-population-20261016-30/campaign-origin.json').read_bytes())
        parent=origin['population']['versions'][config['parent_version_id']]
        with patch.object(socket,'socket',side_effect=AssertionError('NO NETWORK')), \
             patch.object(m.fees,'_book',side_effect=AssertionError('NO ACCOUNTING WRITE')), \
             patch.object(Path,'write_bytes',side_effect=AssertionError('NO FILE WRITE')), \
             patch.object(Path,'write_text',side_effect=AssertionError('NO FILE WRITE')):
            result=m._delivery(config,parent)
        self.assertEqual(result['capacity']['assembled_utf8_bytes'],65570)
        self.assertEqual(result['capacity']['excess_utf8_bytes'],34)
        self.assertEqual(result['capacity']['literal_edit_count'],5)
        self.assertEqual(result['public_failed_delta']['test_text'].encode().__len__(),14451)
        self.assertEqual(result['delivery_status'],'received_but_unaccepted')
