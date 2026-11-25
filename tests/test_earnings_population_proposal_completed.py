"""Invented stopped proposals: real prefix/assembly, no paid/history authority.

The public fixture explicitly substitutes expensive predecessor/training,
financial/Native and physical transcript admission; those are NOT proofs of
actual36 or a live proposal. Separate primitive tests use original driver,
literal assembly and default physical HTTP receipts on a temporary ledger.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import earnings_population_proposal_completed as proposal
import earnings_population as pool
import earnings_population_delta_author as delta
import earnings_population_campaign_context as context
import earnings_open_roles as roles
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness import feedback_linked_loop as driver
from test_earnings_population_frozen_panel import PanelFixture
from test_earnings_population_rejection import BoundReader
from test_earnings_open_researcher import ScriptedReceiptRunner


def reply(value):
    return dict(status='completed',error=None,output=[dict(type='message',role='assistant',
        content=[dict(type='output_text',text=json.dumps(value))])])


class ProposalFixture:
    def __init__(self, *, changed=False, accepted=False, axis='H'):
        self.f=PanelFixture(); f=self.f; self.stack=f.stack
        self.ident='edgar-population-20261016-37'; self.attempt=f.root/'attempts'/self.ident
        self.inputs=f.root/'inputs'/self.ident; self.ledger=f.root/'unused.sqlite'; self.commit='c'*40
        self.company=f.training[0]
        import earnings_population_training25 as training
        self.scope=training.load_scope(f.split)
        self.parent=pool.version(f.source(f.root/'valid-R.py',"PROGRAM={'axis':'R'}\ndef run(p): return 0\n"),
            f.source(f.root/'valid-H.py',"PROGRAM={'axis':'H','tools':[]}\ndef run(p): return 0\n"))
        self.state=pool.initialize(self.parent,{k:digest(k) for k in ('K','M','C')})
        self.base=deepcopy(f.base); self.base['population']=self.state
        self.base['previous_result']=f.origin
        self.feedback=f.save(self.inputs/'rejection-feedback.json',self.base['research_feedback'])
        self.initial=f.save(self.inputs/'initial-population.json',self.state)
        self.campaign=f.save(self.inputs/'campaign.json',{'invented_training_campaign':True})
        self.task=dict(schema='earnings_training25_new_panel_proposal_task_v1',policy='round0_new_panel_candidate_v1',
            primary_task='One transferable whole25 hypothesis.',smoke_company_id=self.company,
            archive_only_version_ids=['a'*64,'b'*64],training_companies=f.training)
        self.task_bound=f.save(self.inputs/'training-proposal-task.json',self.task)
        self.study=dict(campaign=self.campaign,training_proposal_task=self.task_bound)
        self.study_bound=f.save(self.inputs/'study.json',self.study)
        names=(proposal.history.DRIVER,'tools/earnings_population_loop.py','tools/earnings_population_run.py',
            'tools/earnings_population_services.py','tools/earnings_population_campaign.py','tools/earnings_population_delta_author.py')
        self.source_bytes={name:(Path(driver.__file__).read_bytes() if name==proposal.history.DRIVER else
            ("PYTHON={'path':'/synthetic/python','sha256':'"+'a'*64+"'}\n").encode()) for name in names}
        sources={name:f.source(f.repo/name,raw.decode()) for name,raw in self.source_bytes.items()}
        grant=f.save(f.root/'budget-grant.json',{'not_a_real_grant':True})
        self.runtime=dict(schema='earnings_population_runtime_v1',id=self.ident,root=str(self.attempt),
            ledger=str(self.ledger),source_commit=self.commit,forecast_study=self.study_bound,initial_population=self.initial,
            training_proposal_policy=self.task['policy'],companies=[self.company],sources=sources,
            budget_amendment=grant,model_budget_amendment=grant,
            cutoff_utc='2026-10-20T04:00:00Z',deadline_utc='2026-10-20T04:01:00Z',
            limits={r:dict(wall_seconds=1200,max_input_tokens=96000,max_output_tokens=49152) for r in ('controller','author','review')})
        self.clock=f.save(self.attempt/'clock.json',dict(source_commit=self.commit,
            cutoff_utc=self.runtime['cutoff_utc'],deadline_utc=self.runtime['deadline_utc']))
        f.save(self.attempt/'clock.binding.json',self.clock)
        self.review=f.save(self.inputs/'runtime-review.json',dict(verdict='PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY',
            blocking_findings=[],reviewer='/independent',source_commit=self.commit,reviewed_configuration_sha256=digest(self.runtime)))
        self.runtime['review']=self.review; self.runtime_bound=f.save(self.inputs/'runtime-reviewed.json',self.runtime)
        registry=self.ledger.parent/'.capacity-runtime-claims'; token=hashlib.sha256(self.ident.encode()).hexdigest()
        self.owner_path=registry/(token+'.result.json'); self.claim_path=registry/(token+'.json')
        self.owner=dict(status='COMPLETED_COMPONENT_CONTEXT',error_type=None,retry_allowed=False,
            runtime=self.runtime_bound,clock=self.clock,budget_summary={'synthetic':True})
        f.save(self.owner_path,self.owner);f.save(self.claim_path,dict(runtime=self.runtime_bound,id=self.ident,
            source_commit=self.commit,retry_allowed=False))
        self.seed=dict(population=self.state,feedback=self.feedback,companies=[self.company],campaign=self.campaign,
            latest_feedback=self.feedback,last_scored_feedback=self.base['last_scored_feedback'])
        self.packet=f.save(self.attempt/'packet-01.json',dict(population=self.state,feedback=self.feedback,
            company_id=self.company,round_index=1,parent_feedback_sha256=digest(self.feedback),campaign=self.campaign))
        self.chosen=dict(schema='earnings_capacity_decision_v1',axis=axis if changed else 'continue',
            component=('tool_interface' if axis=='H' else 'research_policy') if changed else 'none',parent_pair_sha256=self.parent['id'],
            feedback_sha256=digest(self.feedback),hypothesis='Test one whole25 method.',expected_effect='Bounded test.')
        raw_choice=dict(self.chosen,retire_branch_id='none')
        self.control_raw=f.save(self.attempt/'roles/controller-01/response.json',reply(raw_choice))
        self.choice=f.save(self.attempt/'roles/controller-01/population-decision.json',self.chosen)
        f.save(self.attempt/'roles/controller-01/decision.json',dict(original=self.control_raw,decision=self.chosen))
        self.effective=f.save(self.attempt/'roles/controller-01/effective-input.json',dict(active_versions=[self.parent['id']],
            explorers=[],feedback_sha256=digest(self.feedback)))
        self.native=self.attempt/'inert-native-parent'/('market-rsi-'+self.ident); self.native.mkdir(parents=True)
        self.child=None; output_review=dict(accepted_for_exploration=False,evidence=[])
        if changed:
            folder=self.attempt/'roles/author-01'; selected=proposal.scientific(self.chosen)
            f.save(folder/'effective-input.json',dict(decision=selected,decision_sha256=digest(selected),
                parent_source=self.parent[axis],parent_source_sha256=self.parent[axis]['sha256']))
            raw=f.save(folder/'response.json',reply(dict(decision_sha256=digest(selected),
                parent_source_sha256=self.parent[axis]['sha256'],edits=[dict(kind='replace',old_text='return 0',new_text='return 1')],
                test_text="CASES=[{'input':{},'expected':1}]")))
            business=delta.assemble(self.parent[axis],selected,engine.read(raw))
            source=f.source(folder/'candidate.py',business['source_text']);tests=f.source(folder/'cases.py',business['test_text'])
            projection=f.save(folder/'scientific-decision-projection.json',dict(population_decision=self.chosen,
                scientific_decision=selected,scientific_decision_sha256=digest(selected),
                scope='Explicitly removed retirement field only; no parent or feedback rewrite'))
            f.save(folder/'delta.json',dict(original=raw,delta=proposal.message(engine.read(raw))))
            assembly=f.save(folder/'delta-assembly.json',dict(schema='earnings_population_delta_assembly_v1',axis=axis,
                parent_version_id=self.parent['id'],parent_source=self.parent[axis],raw_patch_response=raw,
                source=source,tests=tests,scientific_decision=projection,scientific_decision_sha256=digest(selected),
                assembled_business_sha256=digest(business),host_candidate_execution=False,
                assembly_source=dict(function='assemble',module=sources['tools/earnings_population_delta_author.py'])))
            self.child=pool.version(**{**{a:self.parent[a] for a in ('R','H')},axis:source},parent=self.parent['id'],axis=axis,
                method=self.chosen['hypothesis'],author='model:DeltaAuthor',evidence=[raw,projection,assembly])
            runner=ScriptedReceiptRunner(self.native/'runner',[1]); executed=runner.run(business['source_text'],{})
            cases=f.save(self.native/'review-01-cases.json',dict(candidate_id=self.child['id'],results=[dict(passed=True,execution=executed)]))
            business_review=dict(candidate_id=self.child['id'],accepted_for_exploration=accepted,rationale='Synthetic smoke-only verdict.')
            f.save(self.attempt/'roles/review-01/effective-input.json',dict(candidate_id=self.child['id'],decision=selected))
            review_raw=f.save(self.attempt/'roles/review-01/response.json',reply(business_review))
            f.save(self.attempt/'roles/review-01/review.json',dict(original=review_raw,review=business_review))
            outcome=f.save(self.native/'review-01-outcome.json',dict(schema='earnings_population_exploration_review_v1',**business_review))
            output_review=dict(accepted_for_exploration=accepted,evidence=[outcome,review_raw,cases])
        self.handlers={s:(lambda ctx,s=s:{}) for s in driver.STAGES}
        self.handlers.update(input=lambda ctx:dict(packet=self.packet,artifacts=[self.packet]),
            controller=lambda ctx:dict(decision=self.choice,artifacts=[self.choice]),
            implement=lambda ctx:dict(candidate=self.child),source_review=lambda ctx:output_review)
        common=dict(adapter=sources['tools/earnings_population_loop.py'],admission=dict(function='execute.<locals>.admit',
            module=sources['tools/earnings_population_run.py']),services=proposal.history.expected_services(self.runtime),
            campaign_policy=sources['tools/earnings_population_campaign.py'],campaign=self.campaign)
        self.identities={stage:dict(common,stage=stage) for stage in driver.STAGES}
        stopped=driver.run(self.attempt/'loop',self.handlers,seed=self.seed,
            admit=lambda ctx:ctx['stage']!='execute',max_rounds=1,handler_identity=lambda:self.identities)
        self.roles={'controller':'COMPLETED_DECISION',**({'author':'COMPLETED_CANDIDATE','review':'COMPLETED_REVIEW'} if changed else {})}
        for role,status in self.roles.items():
            folder=self.attempt/'roles'/(role+'-01'); raw=engine.read(engine.pin(folder/'response.json'))
            f.save(folder/'01-response.json',raw); f.save(folder/'01-request.json',{'synthetic_transport_seam':True})
            f.save(folder/'result.json',dict(status=status,turns=1,wall_seconds=1,error_type=None,
                retry_allowed=False,final_numbered_response='01-response.json'))
        self.result=dict(schema='earnings_training25_proposal_result_v1',runtime=self.runtime_bound,
            status='PROPOSAL_REVIEWED_ACCEPTED' if changed and accepted else 'PROPOSAL_NOT_ACCEPTED',result=stopped,
            proposal_stages=[engine.pin(self.attempt/'loop'/('round-0001-'+s+'.done.json')) for s in proposal.STAGES],
            budget=self.owner['budget_summary'],improvement_proven=False,retry_allowed=False)
        self.binding=f.save(self.attempt/'training-proposal-result.json',self.result)
        for key,value in dict(OWNED=f.root,LEDGER=self.ledger,REPO=f.repo).items():self.stack.enter_context(patch.object(proposal.completed.bootstrap,key,value))
        self.stack.enter_context(patch.object(proposal.runtime_module,'PROPOSAL_ORIGIN',f.origin))
        self.stack.enter_context(patch.object(proposal.runtime_module,'proposal_task',return_value=self.task))
        self.stack.enter_context(patch.object(proposal.history,'_git',side_effect=lambda repo,commit,name:self.source_bytes[name]))
        self.old=self.stack.enter_context(patch.object(proposal.completed,'load',return_value=self.base))
        self.training=self.stack.enter_context(patch.object(proposal.completed,'_training',side_effect=self.admit))
        self.stack.enter_context(patch.object(proposal.completed,'_register',side_effect=self.register))
        self.budget=self.stack.enter_context(patch.object(proposal.completed,'_budget',return_value=[]))
        self.native_check=self.stack.enter_context(patch.object(proposal.completed,'_native',return_value=[]))
        self.stack.enter_context(patch.object(proposal,'_cleanup',return_value=[]))
        self.physical=self.stack.enter_context(patch.object(proposal,'_physical',return_value=[]))
        self.stack.enter_context(patch.object(context,'_training_context',return_value={'training_comparator':{'invented125':True}}))
        self.stack.enter_context(patch.object(proposal,'Path',side_effect=self.path_constructor))

    def path_constructor(self,*args,**kwargs):
        # Redirect only the internally fixed Native test root; no other path policy changes.
        original=Path(*args,**kwargs)
        return self.native.parent if original==Path('/private/tmp') else original

    def register(self,reader,base,**kwargs):
        reader.extra.update(Path(b['path']) for b in (self.parent['R'],self.parent['H']))

    def admit(self,reader,runtime,study,*,preview=False,inherited=None):
        import earnings_population_training25 as training
        training.admit(self.scope,runtime['companies'][0])
        if not preview and inherited!=self.base:raise ValueError('Wrong predecessor')
        return self.scope,[]

    def close(self):self.f.close()
    def load(self):return proposal.load_proposal(self.binding,root=self.f.root,ledger=self.ledger,repo=self.f.repo)
    def rewrite(self,path,value):path.write_text(json.dumps(value,sort_keys=True));return engine.pin(path)


class ProposalClosureTests(unittest.TestCase):
    def fixture(self,**kwargs):
        f=ProposalFixture(**kwargs);self.addCleanup(f.close);return f

    def test_real_four_stage_driver_continue_has_no_fabricated_author_or_completion(self):
        f=self.fixture();value=f.load()
        self.assertFalse(value['accepted']);self.assertIsNone(value['candidate']);self.assertEqual(value['base_origin'],f.base)
        self.assertNotIn('previous_result',value);self.assertNotIn('population',value)
        self.assertFalse((f.attempt/'loop/round-0001-execute.claim.json').exists())
        self.assertEqual(set(f.native_check.call_args.args[4]),{'controller-01'})

    def test_fresh_H_literal_assembly_cases_and_review_preserved_without_host_execution(self):
        f=self.fixture(changed=True,accepted=True);value=f.load()
        self.assertTrue(value['accepted']);self.assertEqual(value['candidate'],f.child)
        self.assertEqual(value['parent'],f.parent);self.assertEqual(value['candidate']['R'],f.parent['R'])
        self.assertEqual(set(f.native_check.call_args.args[4]),{'controller-01','author-01','review-01'})
        self.assertTrue(value['review']['accepted_for_exploration']);f.old.assert_called_once()

    def test_model_rejection_stays_rejection_not_retry_or_adoption(self):
        f=self.fixture(changed=True,accepted=False);value=f.load()
        self.assertFalse(value['accepted']);self.assertEqual(value['candidate'],f.child)
        self.assertEqual(value['base_origin']['population'],f.state)

    def test_real_R_literal_assembly_primitive_keeps_other_axis_without_execution(self):
        f=self.fixture(changed=True,accepted=True,axis='R')
        values=proposal._authored(BoundReader(),f.attempt,f.state,f.chosen,f.child,f.runtime)
        self.assertEqual(values[0],f.parent);self.assertEqual(f.child['H'],f.parent['H'])
        self.assertEqual(values[3]['cases'][0]['expected'],1)

    def test_wrong_predecessor_or_heldout_refuses_before_prefix_candidate_bodies(self):
        f=self.fixture();f.old.side_effect=ValueError('old origin rejected')
        with patch.object(proposal,'_prefix',side_effect=AssertionError('too early')):
            with self.assertRaisesRegex(ValueError,'old origin rejected'):f.load()
        f.native_check.assert_not_called()

    def test_execute_claim_or_later_stage_or_score_is_not_a_clean_proposal(self):
        f=self.fixture();engine.save(f.attempt/'loop/round-0001-execute.claim.json',{'forged':True})
        with self.assertRaisesRegex(ValueError,'BEFORE execute'):f.load()

    def test_wrong_ordered_done_binding_or_modified_claim_refuses(self):
        f=self.fixture();f.result['proposal_stages'].reverse();f.binding=f.rewrite(Path(f.binding['path']),f.result)
        with self.assertRaises(ValueError):f.load()

    def test_false_accepted_envelope_or_nonoriginal_controller_decision_refuses(self):
        f=self.fixture();f.result['status']='PROPOSAL_REVIEWED_ACCEPTED';f.binding=f.rewrite(Path(f.binding['path']),f.result)
        with self.assertRaisesRegex(ValueError,'Controller/parent/proposal outcome'):f.load()

    def test_real_literal_source_and_tests_byte_tamper_refuses(self):
        f=self.fixture(changed=True,accepted=True)
        Path(f.child['H']['path']).write_text('changed')
        with self.assertRaises(ValueError):f.load()

    def test_original_native_financial_or_physical_denials_propagate(self):
        f=self.fixture()
        for boundary in (f.native_check,f.budget,f.physical):
            boundary.side_effect=ValueError('original verifier refused')
            with self.assertRaisesRegex(ValueError,'original verifier refused'):f.load()
            boundary.side_effect=None

    def test_author_packet_cannot_substitute_decision_digest_or_parent(self):
        f=self.fixture(changed=True,accepted=True);path=f.attempt/'roles/author-01/effective-input.json'
        original=engine.read(engine.pin(path))
        for key,value in dict(decision={'different':True},decision_sha256='a'*64,
                              parent_source=f.parent['R'],parent_source_sha256='b'*64).items():
            with self.subTest(field=key):
                f.rewrite(path,dict(original,**{key:value}))
                with self.assertRaisesRegex(ValueError,'author physical packet'):f.load()
        f.rewrite(path,original);self.assertTrue(f.load()['accepted'])

    def test_review_packet_must_judge_actual_child_and_selected_decision(self):
        f=self.fixture(changed=True,accepted=True);path=f.attempt/'roles/review-01/effective-input.json'
        original=engine.read(engine.pin(path))
        for key,value in dict(candidate_id='d'*64,decision={'different':True}).items():
            with self.subTest(field=key):
                f.rewrite(path,dict(original,**{key:value}))
                with self.assertRaisesRegex(ValueError,'review physical packet'):f.load()
        f.rewrite(path,original);self.assertTrue(f.load()['accepted'])


class OriginalPhysicalPrimitiveTests(unittest.TestCase):
    def physical(self,prepared,*,role='controller',packet=None,response=None):
        # Real ReceiptHTTP/DeadlineHTTP/RawHTTP, real reserve/settle and own RO
        # request scan. Only HTTPS bytes are invented; no production ledger.
        from test_earnings_prepared_count_handoff import PreparedCountHandoffTests
        import earnings_open_context as packing
        import earnings_entry as entry
        from edgar_forecast_openai import budgeted_response
        fixture=PreparedCountHandoffTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        task={'primary_task':'Whole25 transferable proposal'};summary={'invented125':True}
        if role!='controller':
            fixture.slot=fixture.f.root/'roles'/(role+'-01');fixture.slot.mkdir(parents=True)
            fixture.f.slots=[str(fixture.slot)];fixture.owned.slots={str(fixture.slot):fixture.f.limits}
            from earnings_night_budget import DeadlineHTTP
            fixture.http=entry.ReceiptHTTP(DeadlineHTTP(fixture.owned,deadline_utc='2099-01-01T00:00:00Z',rollout_seconds=120),fixture.slot)
        if response is not None:
            original_response=fixture.f.response;fixture.f.response=lambda:original_response(response)
        if packet is None:packet=dict(proposal_task=task,research_objective=task['primary_task'],
            research_context={'observations':{'training_comparator':summary}},padding='x'*26000 if prepared else '')
        request=fixture.request();request['input']=[dict(role='user',content=json.dumps(packet))]
        context_path=fixture.f.root/('context-'+role+'.json')
        context_path.write_bytes(Path(fixture.f.context_binding['path']).read_bytes())
        fixture.f.context_binding=engine.pin(context_path)
        entry.durable_json(fixture.slot/'effective-input.json',packet)
        if prepared:
            effective,handle=packing.pack(fixture.http,request,fixture.f.limits,fixture.slot,1,
                prepared_count_context=fixture.f.context_binding)
            budgeted_response(fixture.http,effective,fixture.f.rates,fixture.f.limits,fixture.f.budget,
                fixture.slot,1,prepared_count=handle)
        else:
            budgeted_response(fixture.http,request,fixture.f.rates,fixture.f.limits,fixture.f.budget,fixture.slot,1)
        runtime=dict(root=str(fixture.f.root),ledger=str(fixture.f.ledger),rates=fixture.f.rates,
            limits={role:fixture.f.limits},slots={role:fixture.f.slots},role_efforts={role:'xhigh'},
            sources={name:engine.pin(entry.REPO/name) for name in ('tools/earnings_open_context.py','tools/edgar_forecast_openai.py')})
        evidence=proposal._physical(BoundReader(fixture.f.ledger),runtime,task,summary,{role:{'turns':1}})
        self.assertEqual(len(fixture.wire_calls),2);self.assertGreaterEqual(len(evidence),6)
        return fixture,runtime,task,summary

    def test_real_default_count_path_without_prepared_marker_is_legal(self):
        fixture,_,_,_=self.physical(False)
        self.assertFalse((fixture.slot/'01-prepared-count-reuse.json').exists())

    def test_real_prepared_count_path_with_original_single_use_proof_is_legal(self):
        fixture,_,_,_=self.physical(True)
        self.assertTrue((fixture.slot/'01-prepared-count-reuse.json').exists())

    def test_physical_semantic_or_count_drift_refuses_without_making_new_requests(self):
        fixture,runtime,task,summary=self.physical(False)
        path=fixture.slot/'01-count.json';value=json.loads(path.read_bytes());value['input_tokens']=21
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):proposal._physical(BoundReader(fixture.f.ledger),runtime,task,summary,{'controller':{'turns':1}})
        self.assertEqual(len(fixture.wire_calls),2)

    def test_original_physical_review_of_wrong_child_cannot_authorize_other_child(self):
        selected={'axis':'H','parent_pair_sha256':'a'*64};child={'id':'c'*64}
        packet=dict(candidate_id='d'*64,decision=selected)
        fixture,_,_,_=self.physical(False,role='review',packet=packet,
            response=dict(candidate_id=child['id'],accepted_for_exploration=True,rationale='Invented smoke review.'))
        first=json.loads(engine.read(engine.pin(fixture.slot/'01-request.json'))['payload']['input'][0]['content'])
        self.assertEqual(first,engine.read(engine.pin(fixture.slot/'effective-input.json')))
        self.assertEqual(proposal.message(engine.read(engine.pin(fixture.slot/'01-response.json')))['candidate_id'],child['id'])
        with self.assertRaisesRegex(ValueError,'review physical packet'):
            proposal._packet_identity(first,'review',selected,{},child)
        self.assertEqual(len(fixture.wire_calls),2)


if __name__=='__main__':unittest.main()
