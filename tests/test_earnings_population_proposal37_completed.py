"""Typed imported-C/A + fresh Review closures on temporary public fixtures.

The original failed37 authenticator, literal assembly, four-stage driver seals,
reused-stage verifier, SHA reader and new case/probe checks run. Expensive old36,
training, financial/Native/wire boundaries inherit explicit fixture seams. The
not-yet-integrated runtime metadata API is deliberately patched, never inferred
from a missing API. No provider, real ledger, candidate/scorer or history run.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import earnings_population_proposal_completed as proposal
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness import feedback_linked_loop as driver
from market_rsi import digest
from test_earnings_population_proposal37_reuse import FailedFixture
from test_earnings_population_proposal_completed import ProposalFixture, reply
from test_earnings_open_researcher import ScriptedReceiptRunner

ORIGINAL_METADATA=getattr(proposal.runtime_module,'_proposal_prefix_metadata',None)

class ImportedFixture:
    def __init__(self, *, accepted=True, failed_cases=False):
        original_register=proposal.completed._register
        self.f=FailedFixture();f=self.f;store=f.f;self.stack=f.stack
        # Original registration of an already-authenticated predecessor is real
        # here; it must add old37 before the current journal/body is inspected.
        def register(reader,inherited,**kwargs):
            original_register(reader,inherited,**kwargs)
            f.register(reader,inherited,**kwargs)  # Invented root-level parent files.
        self.stack.enter_context(patch.object(proposal.completed,'_register',register))
        self.receipt=f.load(); self.old_failure=deepcopy(f.failure)
        self.ident='edgar-population-20261016-38';self.attempt=store.root/'attempts'/self.ident
        self.inputs=store.root/'inputs'/self.ident
        self.bound=store.save(self.inputs/'proposal-prefix-reuse.json',self.receipt)
        self.study=dict(f.study,training_proposal_task=store.save(self.inputs/'training-proposal-task.json',f.task),
                        proposal_prefix_reuse=self.bound)
        self.study_bound=store.save(self.inputs/'study.json',self.study)
        self.initial=store.save(self.inputs/'initial-population.json',f.state)
        self.feedback=store.save(self.inputs/'rejection-feedback.json',f.base['research_feedback'])
        self.seed=dict(f.seed,feedback=self.feedback,latest_feedback=self.feedback)
        self.runtime=dict(f.runtime,id=self.ident,root=str(self.attempt),forecast_study=self.study_bound,
            initial_population=self.initial,proposal_prefix_reuse=self.bound,review_input_policy='review_input_200000_v1',
            limits={**f.runtime['limits'],'review':dict(f.runtime['limits']['review'],max_input_tokens=200000)})
        self.runtime.pop('review')
        self.runtime_review=store.save(self.inputs/'runtime-review.json',dict(verdict='PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY',
            blocking_findings=[],reviewer='/independent',source_commit=f.commit,reviewed_configuration_sha256=digest(self.runtime)))
        self.runtime['review']=self.runtime_review
        self.runtime_bound=store.save(self.inputs/'runtime-reviewed.json',self.runtime)
        self.clock=store.save(self.attempt/'clock.json',dict(source_commit=f.commit,cutoff_utc=self.runtime['cutoff_utc'],deadline_utc=self.runtime['deadline_utc']))
        store.save(self.attempt/'clock.binding.json',self.clock)
        registry=f.ledger.parent/'.capacity-runtime-claims';key=hashlib.sha256(self.ident.encode()).hexdigest()
        self.owner_path=registry/(key+'.result.json')
        store.save(self.owner_path,dict(status='COMPLETED_COMPONENT_CONTEXT',error_type=None,retry_allowed=False,
            runtime=self.runtime_bound,clock=self.clock,budget_summary={'synthetic':True}))
        store.save(registry/(key+'.json'),dict(runtime=self.runtime_bound,id=self.ident,source_commit=f.commit,retry_allowed=False))
        self.packet=store.save(self.attempt/'packet-01.json',dict(engine.read(f.packet),feedback=self.feedback,
            parent_feedback_sha256=digest(self.feedback)))
        self.chosen=dict(f.chosen,feedback_sha256=digest(self.feedback))
        self.choice=store.save(self.attempt/'roles/controller-01/population-decision.json',self.chosen)
        bundle=self.receipt['author_stage_reuse']
        self.control_marker=store.save(self.attempt/'roles/controller-01/controller-stage-reuse.json',dict(
            schema='earnings_population_Controller_stage_reuse_v1',mode=bundle['mode'],new_model_called=False,
            routing_author='trusted_recovery_adapter',original_decision=bundle['decision'],decision=self.choice,
            packet=self.packet,source_attempt=bundle['failed_attempt']))
        self.author_marker=store.save(self.attempt/'roles/author-01/author-stage-reuse.json',dict(
            schema='earnings_population_Author_stage_reuse_v1',mode=bundle['mode'],new_model_called=False,
            source_attempt=bundle['failed_attempt'],candidate_id=f.child['id'],original_decision=bundle['decision'],
            scientific_decision_sha256=digest(bundle['scientific_decision']),
            **{k:bundle[k] for k in ('raw_patch_response','assembly','source','tests')}))
        self.native=f.native.parent/('market-rsi-'+self.ident);self.native.mkdir()
        source=Path(f.child['R']['path']).read_text(); cases=[]
        for i in range(7):
            value=0 if failed_cases and i==0 else 1
            execution=ScriptedReceiptRunner(self.native/f'case-{i}',[value]).run(source,{'case':i})
            cases.append(dict(passed=value==1,execution=execution))
        self.cases=store.save(self.native/'review-01-cases.json',dict(candidate_id=f.child['id'],results=cases))
        rationale='MODEL_CASES_FAILED; original isolated receipt' if failed_cases else 'A real fixture Review decision, not a whole25 score.'
        business=dict(candidate_id=f.child['id'],accepted_for_exploration=False if failed_cases else accepted,rationale=rationale)
        self.outcome=store.save(self.native/'review-01-outcome.json',dict(schema='earnings_population_exploration_review_v1',**business))
        if not failed_cases:
            folder=self.attempt/'roles/review-01'
            store.save(folder/'effective-input.json',dict(candidate_id=f.child['id'],decision=bundle['scientific_decision']))
            raw=store.save(folder/'response.json',reply(business));store.save(folder/'review.json',dict(original=raw,review=business))
            store.save(folder/'01-response.json',engine.read(raw));store.save(folder/'01-request.json',{'synthetic_wire':True})
            store.save(folder/'result.json',dict(status='COMPLETED_REVIEW',error_type=None,retry_allowed=False,
                turns=1,wall_seconds=1,final_numbered_response='01-response.json'))
            for stage in ('forecast','controller'):
                payload=dict(stage=stage,records=[],questions=f.files['questions.md'],filing_index=f.files['filing_index.tsv'])
                child_run=ScriptedReceiptRunner(self.native/(stage+'-child'),[1]).run(source,payload)
                parent_run=ScriptedReceiptRunner(self.native/(stage+'-parent'),[0]).run(Path(f.parent['R']['path']).read_text(),payload)
                store.save(self.native/f'review-01-{stage}-probe.json',dict(input=payload,execution=child_run))
                store.save(self.native/f'review-01-parent-{stage}-comparison.json',dict(input=payload,
                    execution=parent_run,parent_version_id=f.parent['id']))
        handlers={s:(lambda ctx,s=s:{}) for s in driver.STAGES}
        handlers.update(input=lambda ctx:dict(packet=self.packet,artifacts=[self.packet]),
            controller=lambda ctx:dict(decision=self.choice,packet_sha256=self.packet['sha256'],
                stage_reuse=self.control_marker,artifacts=[self.choice,self.control_marker]),
            implement=lambda ctx:dict(candidate=f.child,stage_reuse=self.author_marker,artifacts=[self.author_marker]),
            source_review=lambda ctx:dict(accepted_for_exploration=business['accepted_for_exploration'],evidence=[self.outcome,self.cases]))
        stopped=driver.run(self.attempt/'loop',handlers,seed=self.seed,admit=lambda ctx:ctx['stage']!='execute',
            max_rounds=1,handler_identity=lambda:f.identities)
        self.result=dict(schema='earnings_training25_proposal_result_v1',runtime=self.runtime_bound,
            status='PROPOSAL_REVIEWED_ACCEPTED' if business['accepted_for_exploration'] else 'PROPOSAL_NOT_ACCEPTED',
            result=stopped,proposal_stages=[engine.pin(self.attempt/'loop'/('round-0001-'+s+'.done.json')) for s in proposal.STAGES],
            budget={'synthetic':True},improvement_proven=False,retry_allowed=False)
        self.binding=store.save(self.attempt/'training-proposal-result.json',self.result)
        self.metadata=self.stack.enter_context(patch.object(proposal.runtime_module,'_proposal_prefix_metadata',
            return_value=deepcopy(self.receipt),create=True))

    def close(self):self.f.close()
    def load(self):return proposal.load_proposal(self.binding,root=self.f.f.root,ledger=self.f.ledger,repo=self.f.f.repo)
    def rewrite(self,path,value):return self.f.rewrite(path,value)
    def reseal(self,stage,change):
        """Only rewrite a final output used by a test; no later context depends on it."""
        if stage!='source_review':raise AssertionError('Use original driver for earlier output changes')
        path=self.attempt/'loop/round-0001-source_review.done.json';row=engine.read(engine.pin(path))
        row['output'].update(change);row['output_sha256']=digest(row['output'])
        bound=self.rewrite(path,row);self.rewrite(path.with_suffix('.binding.json'),bound)
        self.result['proposal_stages'][-1]=bound;self.binding=self.rewrite(Path(self.binding['path']),self.result)


class ImportedProposalClosureTests(unittest.TestCase):
    def fixture(self,**kwargs):
        f=ImportedFixture.__new__(ImportedFixture)
        self.addCleanup(lambda:f.close() if hasattr(f,'f') else None)
        f.__init__(**kwargs);return f

    def test_original_failed37_auth_plus_current_driver_fresh_review_acceptance(self):
        f=self.fixture();value=f.load()
        self.assertTrue(value['accepted']);self.assertEqual(value['schema'],proposal.SCHEMA)
        self.assertEqual(value['candidate'],f.f.child);self.assertEqual(value['base_origin'],f.f.base)
        self.assertNotIn('previous_result',value);self.assertNotIn('population',value)
        self.assertEqual(set(f.f.physical.call_args.args[-1]),{'review'})
        self.assertEqual(set(f.f.native_check.call_args.args[4]),{'controller-01','author-01','review-01'})
        self.assertEqual(value['stage_attribution']['review_assessment'],'fresh_model_review')
        self.assertFalse(value['stage_attribution']['new_model_Controller_called'])
        self.assertFalse(value['stage_attribution']['new_model_Author_called'])
        self.assertTrue(value['stage_attribution']['new_model_Review_called'])
        self.assertEqual(engine.read(f.old_failure)['status'],'FAILED_NO_RETRY')
        self.assertNotEqual(value['decision']['feedback_sha256'],f.receipt['scientific_decision']['feedback_sha256'])
        self.assertFalse((f.attempt/'loop/round-0001-execute.claim.json').exists())

    def test_genuine_new_model_rejection_stays_unaccepted(self):
        f=self.fixture(accepted=False);value=f.load()
        self.assertFalse(value['accepted']);self.assertTrue(value['stage_attribution']['new_model_Review_called'])

    def test_original_isolated_case_negative_needs_no_forced_review_or_zero_score(self):
        f=self.fixture(failed_cases=True);value=f.load()
        self.assertFalse(value['accepted']);self.assertNotIn('points',value)
        self.assertEqual(value['stage_attribution']['review_assessment'],'authored_cases_failed_no_model_review')
        self.assertFalse(value['stage_attribution']['new_model_Review_called'])
        self.assertEqual(f.f.physical.call_args.args[-1],{})

    def test_explicit_prefix_cannot_succeed_with_missing_future_metadata_receiver(self):
        f=self.fixture()
        with patch.object(proposal.runtime_module,'_proposal_prefix_metadata',None):
            with self.assertRaisesRegex(ValueError,'not implemented'):f.load()

    def test_actual_metadata_api_reads_canonical_receipt_with_only_authority_task_seams(self):
        f=self.fixture();self.assertTrue(callable(ORIGINAL_METADATA))
        link=f.f.f.save(f.inputs/'training-state-link.json',{'split':f.f.scope['split']})
        runtime=dict(f.runtime,training_policy='frozen_training25_v1')
        study=dict(f.study,training_state_link=link)
        # Real metadata/file/split/consumer/receipt checks; only current Source
        # authority/resource policy and exact task construction are fixtures.
        with patch.object(proposal.runtime_module,'ROOT',f.f.f.root), \
             patch.object(proposal.runtime_module,'review_input_policy',return_value='review_input_200000_v1'), \
             patch.object(proposal.runtime_module,'_proposal_expected',return_value=f.f.task):
            self.assertEqual(ORIGINAL_METADATA(runtime,study,company_id=f.f.company),f.receipt)
            with self.assertRaises(ValueError):ORIGINAL_METADATA(dict(runtime,proposal_prefix_reuse=None),study,company_id=f.f.company)

    def test_metadata_saved_receipt_and_original_authenticator_must_all_agree(self):
        f=self.fixture();f.metadata.return_value=dict(f.receipt,consumer_attempt_id='edgar-population-20261016-39')
        with self.assertRaisesRegex(ValueError,'original failed37'):f.load()
        f.metadata.return_value=deepcopy(f.receipt)
        with patch.object(proposal,'load_failed37_prefix',side_effect=ValueError('Original failed37 denied')):
            with self.assertRaisesRegex(ValueError,'Original failed37 denied'):f.load()

    def test_exact_mirror_and_local_file_prevent_marker_erasure_fallback(self):
        f=self.fixture()
        for runtime,study in (({k:v for k,v in f.runtime.items() if k!='proposal_prefix_reuse'},f.study),
                              (f.runtime,{k:v for k,v in f.study.items() if k!='proposal_prefix_reuse'}),
                              ({k:v for k,v in f.runtime.items() if k!='proposal_prefix_reuse'},
                               {k:v for k,v in f.study.items() if k!='proposal_prefix_reuse'})):
            with self.subTest(runtime_marker='proposal_prefix_reuse' in runtime,study_marker='proposal_prefix_reuse' in study):
                reader=proposal.history._Reader(f.f.f.root,f.f.ledger,f.f.f.repo,f.ident)
                with self.assertRaisesRegex(ValueError,'mirrored'):
                    proposal._proposal_prefix(reader,runtime,study,f.f.task,root=f.f.f.root,ledger=f.f.ledger,repo=f.f.f.repo)

    def test_old_scientific_hash_not_new_routed_hash_is_used_for_new_review(self):
        f=self.fixture();path=f.attempt/'roles/review-01/effective-input.json'
        f.rewrite(path,dict(candidate_id=f.f.child['id'],decision=proposal.scientific(f.chosen)))
        with self.assertRaisesRegex(ValueError,'review physical packet'):f.load()

    def test_reuse_markers_cannot_claim_new_models_or_change_original_source(self):
        for role,name,key,value in (('controller','controller-stage-reuse.json','new_model_called',True),
            ('author','author-stage-reuse.json','source',{'path':'/foreign','sha256':'a'*64})):
            with self.subTest(role=role):
                f=self.fixture();path=f.attempt/'roles'/(role+'-01')/name
                # Direct original verifier reaches content check independently
                # of its separately mandatory immutable done-stage binding.
                original=engine.read(engine.pin(path));f.rewrite(path,dict(original,**{key:value}))
                with self.assertRaises(ValueError):f.load()

    def test_no_numbered_response_http_or_result_may_appear_in_imported_CA_slots(self):
        for role,name in (('controller','01-response.json'),('author','result.json'),('author','http-x.intent.json')):
            with self.subTest(role=role,name=name):
                f=self.fixture();f.f.f.save(f.attempt/'roles'/(role+'-01')/name,{})
                with self.assertRaises(ValueError):f.load()

    def test_old_review_reuse_marker_cannot_replace_a_new_review(self):
        f=self.fixture();f.f.f.save(f.attempt/'roles/review-01/review-stage-reuse.json',{'old':True})
        with self.assertRaisesRegex(ValueError,'old Review'):f.load()

    def test_stage_marker_must_be_bound_in_exact_done_artifacts(self):
        f=self.fixture();outputs={s:engine.read(engine.pin(f.attempt/'loop'/('round-0001-'+s+'.done.json')))['output'] for s in proposal.STAGES}
        outputs['implement'].pop('stage_reuse')
        reader=proposal.history._Reader(f.f.f.root,f.f.ledger,f.f.f.repo,f.ident)
        reader.ids.add(f.f.ident);reader.extra.update(Path(b['path']) for b in f.receipt['evidence'])
        with self.assertRaises(ValueError):proposal._reused_authored(reader,f.attempt,outputs,f.f.base,f.receipt,f.f.child)

    def test_fake_accepted_case_negative_without_fresh_review_is_not_admitted(self):
        f=self.fixture(failed_cases=True);outcome=engine.read(f.outcome);outcome['accepted_for_exploration']=True
        new=f.rewrite(Path(f.outcome['path']),outcome);f.result['status']='PROPOSAL_REVIEWED_ACCEPTED'
        f.reseal('source_review',dict(accepted_for_exploration=True,evidence=[new,f.cases]))
        with self.assertRaisesRegex(ValueError,'Failed cases'):f.load()

    def test_new_physical_financial_native_cleanup_denial_is_not_cached_as_success(self):
        f=self.fixture()
        with patch.object(proposal,'_physical',side_effect=ValueError('Physical boundary refused')):
            with self.assertRaisesRegex(ValueError,'Physical boundary refused'):f.load()
        f.f.native_check.side_effect=ValueError('Native denied')
        with self.assertRaisesRegex(ValueError,'Native denied'):f.load()

    def test_absent_marker_fresh_only_path_needs_no_future_metadata_api(self):
        f=ProposalFixture(changed=True,accepted=True,axis='H');self.addCleanup(f.close)
        with patch.object(proposal.runtime_module,'_proposal_prefix_metadata',side_effect=AssertionError('Legacy must not call'),create=True):
            value=f.load()
        self.assertTrue(value['accepted']);self.assertNotIn('stage_attribution',value)


if __name__=='__main__':unittest.main()
