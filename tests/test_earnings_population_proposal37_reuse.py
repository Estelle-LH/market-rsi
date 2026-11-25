"""Failed37 prefix contracts on invented temporary artifacts, never a live run.

Original driver seals, SHA/Git reader, literal Delta assembly, seven isolated
receipt checks and cold receipt verifier execute. Completed36/training/financial/
Native admission, actual incident constants and wire generation are explicit
fixtures. Separate tests exercise original physical counting/settlement on temp
SQLite. No candidate Python, scorer, real ledger or original history is run.
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
import test_earnings_population_proposal_completed as legacy
from test_earnings_population_proposal_completed import ProposalFixture, reply
from test_earnings_population_rejection import BoundReader
from test_earnings_open_researcher import ScriptedReceiptRunner


class FailedFixture(ProposalFixture):
    def __init__(self):
        super().__init__(changed=True,axis='R')
        f=self.f; author=self.attempt/'roles/author-01'; review=self.attempt/'roles/review-01'
        original_save=f.save
        f.save=lambda path,value:self.rewrite(path,value) if path.exists() else original_save(path,value)
        self.stack.enter_context(patch.object(proposal,'FAILED37_COMPANY',self.company))
        self.runtime['limits']['review']['max_input_tokens']=32000
        self.runtime['rates']={'api_model':'synthetic-model'}
        self.review=f.save(self.inputs/'runtime-review.json',dict(verdict='PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY',
            blocking_findings=[],reviewer='/independent',source_commit=self.commit,
            reviewed_configuration_sha256=digest({k:v for k,v in self.runtime.items() if k!='review'})))
        self.runtime['review']=self.review; self.runtime_bound=self.rewrite(Path(self.runtime_bound['path']),self.runtime)
        self.owner.update(status='FAILED_NO_RETRY',error_type='LoopHalted',runtime=self.runtime_bound)
        f.save(self.owner_path,self.owner); f.save(self.claim_path,dict(runtime=self.runtime_bound,id=self.ident,
            source_commit=self.commit,retry_allowed=False))
        selected=proposal.scientific(self.chosen)
        raw=f.save(author/'response.json',reply(dict(decision_sha256=digest(selected),parent_source_sha256=self.parent['R']['sha256'],
            edits=[dict(kind='replace',old_text='return 0',new_text='return 1')],
            test_text='CASES='+repr([dict(input={'case':i},expected=1) for i in range(7)]))))
        business=proposal.assemble(self.parent['R'],selected,engine.read(raw))
        source=f.source(author/'candidate.py',business['source_text']); tests=f.source(author/'cases.py',business['test_text'])
        assembly=engine.read(engine.pin(author/'delta-assembly.json'))
        assembly.update(raw_patch_response=raw,source=source,tests=tests,assembled_business_sha256=digest(business))
        assembly_bound=self.rewrite(author/'delta-assembly.json',assembly)
        f.save(author/'delta.json',dict(original=raw,delta=proposal.message(engine.read(raw))))
        self.child=proposal.pool.version(source,self.parent['H'],parent=self.parent['id'],axis='R',
            method=self.chosen['hypothesis'],author='model:DeltaAuthor',
            evidence=[raw,assembly['scientific_decision'],assembly_bound])
        f.save(review/'effective-input.json',dict(candidate_id=self.child['id'],decision=selected))
        runner=ScriptedReceiptRunner(self.native/'seven-cases',[1]*7)
        f.save(self.native/'review-01-cases.json',dict(candidate_id=self.child['id'],results=[
            dict(passed=True,execution=runner.run(business['source_text'],{'case':i})) for i in range(7)]))
        self.files={'questions.md':'Synthetic training questions','filing_index.tsv':'Synthetic index'}
        self.stack.enter_context(patch.object(proposal,'FilingTools',return_value=type('Tools',(),{'files':self.files})()))
        for stage in ('forecast','controller'):
            payload=dict(stage=stage,records=[],questions=self.files['questions.md'],filing_index=self.files['filing_index.tsv'])
            child_execution=ScriptedReceiptRunner(self.native/(stage+'-child'),[1]).run(business['source_text'],payload)
            parent_execution=ScriptedReceiptRunner(self.native/(stage+'-parent'),[0]).run(Path(self.parent['R']['path']).read_text(),payload)
            f.save(self.native/f'review-01-{stage}-probe.json',dict(company_id=self.company,input=payload,
                execution=child_execution,diagnostics={'synthetic':True}))
            f.save(self.native/f'review-01-parent-{stage}-comparison.json',dict(input=payload,
                parent_version_id=self.parent['id'],execution=parent_execution))
        (self.native/'review-01-outcome.json').unlink(); (review/'review.json').unlink()
        for role,n in (('controller',8),('author',8),('review',4)):
            folder=self.attempt/'roles'/(role+'-01')
            raw_reply=engine.read(engine.pin(folder/'response.json')) if role!='review' else reply({'uncompleted_tool_observation':True})
            for i in range(1,n+1):
                f.save(folder/f'{i:02d}-request.json',{'synthetic_wire':i})
                f.save(folder/f'{i:02d}-response.json',raw_reply)
            f.save(folder/'response.json',raw_reply)
            f.save(folder/'result.json',dict(status='FAILED_NO_RETRY' if role=='review' else
                'COMPLETED_DECISION' if role=='controller' else 'COMPLETED_CANDIDATE',
                turns=5 if role=='review' else 8,tool_calls=4 if role=='review' else 7,
                error_type='BudgetStop' if role=='review' else None,retry_allowed=False,
                final_numbered_response=f'{n:02d}-response.json',wall_seconds=1))
        f.save(self.attempt/'roles/controller-01/decision.json',dict(
            original=engine.pin(self.attempt/'roles/controller-01/response.json'),decision=self.chosen))
        for variant,count in (('01',32976),('04',33290)):
            payload=dict(model=self.runtime['rates']['api_model'],input=[dict(role='user',
                content=json.dumps(engine.read(engine.pin(review/'effective-input.json'))))])
            counted={'input_tokens':count,'_request_id':'count-'+variant}
            f.save(review/f'05-context-{variant}-count.json',counted)
            f.save(review/f'05-context-{variant}.json',dict(schema='earnings_context_preparation_v1',generation_not_sent=True,
                max_input_tokens=32000,effective_request_sha256=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()))
            f.save(review/f'http-failed-{variant}.intent.json',dict(endpoint='/v1/responses/input_tokens',payload=payload))
            f.save(review/f'http-failed-{variant}.response.json',counted)
            f.save(review/f'http-failed-{variant}.raw.bin',{'input_tokens':count})
        # Replay the ORIGINAL driver into a real three-done + failed fourth
        # journal. Only temporary fixture files are replaced, never old37.
        for path in (self.attempt/'loop').iterdir():path.unlink()
        def fail_review(ctx):raise RuntimeError('Synthetic original pack failure')
        self.handlers['source_review']=fail_review
        with unittest.TestCase().assertRaises(driver.LoopHalted):
            driver.run(self.attempt/'loop',self.handlers,seed=self.seed,admit=lambda ctx:True,
                max_rounds=1,handler_identity=lambda:self.identities)
        Path(self.binding['path']).unlink()
        self.failure=f.save(self.attempt/'training-proposal-failure.json',dict(schema='earnings_training25_proposal_failure_v1',
            status='FAILED_NO_RETRY',error_type='LoopHalted',native_closure=None,retry_allowed=False,runtime=self.runtime_bound))
        authority=f.save(f.root/'reuse37-authority.json',dict(schema='earnings_training25_direct_review200k_reuse37_authority_v1',
            direct_human_answer='make it 200k?',reuse_scope=dict(failed_attempt=self.ident,failure_sha256=self.failure['sha256'],
                actual_parent=self.parent['id'],candidate_id=self.child['id'],R_sha256=self.child['R']['sha256'],
                H_sha256=self.child['H']['sha256'],tests_sha256=tests['sha256'])))
        for name,value in (('FAILED37',self.failure),('FAILED37_AUTHORITY',authority),
                ('FAILED37_ANCHORS',{name:engine.pin(self.attempt/name)['sha256'] for name in proposal.FAILED37_ANCHORS}),
                ('FAILED37_NATIVE_ANCHORS',{name:engine.pin(self.native/name)['sha256'] for name in proposal.FAILED37_NATIVE_ANCHORS})):
            self.stack.enter_context(patch.object(proposal,name,value))

    def load(self,consumer='edgar-population-20261016-38'):
        return proposal.load_failed37_prefix(self.failure,consumer_attempt_id=consumer,
            root=self.f.root,ledger=self.ledger,repo=self.f.repo)


class Failed37AdmissionTests(unittest.TestCase):
    def fixture(self):
        f=FailedFixture.__new__(FailedFixture)
        self.addCleanup(lambda:f.close() if hasattr(f,'f') else None)
        f.__init__();return f

    def test_real_three_done_failed_fourth_preserves_literal_CA_not_review_success(self):
        f=self.fixture(); value=f.load()
        self.assertEqual(value['schema'],proposal.FAILED37_SCHEMA)
        self.assertEqual(value['base_origin'],f.base); self.assertEqual(value['candidate'],f.child)
        self.assertEqual(value['original_completed_generations'],dict(controller=8,author=8,review=4))
        self.assertEqual(value['review_assessment'],'not_completed')
        self.assertNotIn('review_stage_reuse',value);self.assertNotIn('accepted',value)
        self.assertNotIn('previous_result',value);self.assertNotIn('population',value)
        self.assertFalse(value['author_stage_reuse']['new_model_Author_called'])
        self.assertEqual(f.physical.call_args.kwargs['completed_generations']['review'],4)
        self.assertEqual(f.physical.call_args.args[-1]['review']['turns'],5)
        self.assertEqual(set(f.native_check.call_args.args[4]),{'controller-01','author-01','review-01'})
        self.assertFalse((f.attempt/'loop/round-0001-source_review.done.json').exists())

    def test_consumer_new_id_and_same_company_metadata_are_mandatory(self):
        f=self.fixture()
        for ident in (f.ident,'edgar-population-20261016-36','../38',None,'edgar-population-20261016-038'):
            with self.subTest(ident=ident),self.assertRaises(ValueError):f.load(ident)
        with self.assertRaises(ValueError):proposal.failed37_policy('edgar-population-20261016-38',company_id='CIK9999999999')
        self.assertEqual(f.load()['consumer_attempt_id'],'edgar-population-20261016-38')

    def test_foreign_failure_or_authority_bytes_fail_before_old_history(self):
        f=self.fixture()
        with self.assertRaises(ValueError):proposal.load_failed37_prefix(dict(f.failure,sha256='a'*64),
            consumer_attempt_id='edgar-population-20261016-38',root=f.f.root,ledger=f.ledger,repo=f.f.repo)
        Path(proposal.FAILED37_AUTHORITY['path']).write_text('{}')
        with self.assertRaises(ValueError):f.load()
        f.old.assert_not_called()

    def test_original_completed_predecessor_failure_propagates(self):
        f=self.fixture();f.old.side_effect=ValueError('Original36 denied')
        with self.assertRaisesRegex(ValueError,'Original36 denied'):f.load()
        f.native_check.assert_not_called()

    def test_training_admission_precedes_candidate_role_and_old_history_bodies(self):
        f=self.fixture();f.training.side_effect=ValueError('Training scope denied')
        original=proposal.history._Reader.read
        def guarded(reader,bound,**kwargs):
            if bound['path'] in {str(f.attempt/name) for name in proposal.FAILED37_ANCHORS}:
                raise AssertionError('Candidate/role body before training admission')
            return original(reader,bound,**kwargs)
        with patch.object(proposal.history._Reader,'read',guarded):
            with self.assertRaisesRegex(ValueError,'Training scope denied'):f.load()
        f.old.assert_not_called();f.native_check.assert_not_called()

    def test_fixed_producer_anchor_rejects_coherent_rewrite_before_ancestry(self):
        f=self.fixture();path=f.attempt/'roles/controller-01/effective-input.json'
        f.rewrite(path,dict(engine.read(engine.pin(path)),scientific_rewrite=True))
        with self.assertRaisesRegex(ValueError,'hash differs'):f.load()
        f.old.assert_not_called()

    def test_literal_candidate_or_tests_byte_drift_is_never_reassembled_as_new_author(self):
        for name in ('candidate.py','cases.py'):
            with self.subTest(name=name):
                f=self.fixture();(f.attempt/'roles/author-01'/name).write_text('# altered')
                with self.assertRaises(ValueError):f.load()

    def test_failed_review_cannot_grow_fifth_generation_verdict_or_fourth_done(self):
        for folder,name in (('roles/review-01','05-request.json'),('roles/review-01','review.json'),
                ('loop','round-0001-source_review.done.json')):
            with self.subTest(name=name):
                f=self.fixture();f.f.save(f.attempt/folder/name,{})
                with self.assertRaises(ValueError):f.load()

    def test_score_or_forecast_output_forbids_failed_unscored_prefix(self):
        f=self.fixture();f.f.save(f.attempt/'unexpected/score.json',{})
        with self.assertRaisesRegex(ValueError,'unscored proposal'):f.load()

    def test_review_last_tool_response_is_not_a_verdict_and_must_match_numbered04(self):
        f=self.fixture();self.assertEqual(f.load()['review_assessment'],'not_completed')
        f.rewrite(f.attempt/'roles/review-01/response.json',reply({'changed':True}))
        with self.assertRaisesRegex(ValueError,'no completed Review'):f.load()

    def test_failed_fifth_counts_keep_32k_ceiling_and_original_physical_payload(self):
        f=self.fixture();path=f.attempt/'roles/review-01/05-context-04-count.json'
        f.rewrite(path,{'input_tokens':31999,'_request_id':'count-04'})
        with self.assertRaises(ValueError):f.load()

    def test_real_cases_and_matched_cold_receipts_are_verified_not_just_pass_flags(self):
        f=self.fixture();path=f.native/'review-01-cases.json';value=engine.read(engine.pin(path))
        value['results'][0]['passed']=False;f.rewrite(path,value)
        # Rebind only the invented incident anchor to reach original verifier.
        with patch.dict(proposal.FAILED37_NATIVE_ANCHORS,{'review-01-cases.json':engine.pin(path)['sha256']}):
            with self.assertRaisesRegex(ValueError,'isolated source/input/case'):f.load()

    def test_cold_parent_input_must_equal_child_and_remain_empty(self):
        f=self.fixture();path=f.native/'review-01-parent-forecast-comparison.json';value=engine.read(engine.pin(path))
        value['input']['records']=[{'wrong':'warm'}];f.rewrite(path,value)
        with patch.dict(proposal.FAILED37_NATIVE_ANCHORS,{path.name:engine.pin(path)['sha256']}):
            with self.assertRaisesRegex(ValueError,'matched cold payload'):f.load()

    def test_financial_native_and_physical_original_denials_remain_fatal(self):
        f=self.fixture()
        for boundary in (f.budget,f.native_check,f.physical):
            with self.subTest(boundary=str(boundary)):
                boundary.side_effect=ValueError('Original boundary denied')
                with self.assertRaisesRegex(ValueError,'Original boundary denied'):f.load()
                boundary.side_effect=None


class Failed37PhysicalPrimitiveTests(unittest.TestCase):
    def test_original_temp_sqlite_review_count_can_be_attempted2_completed1_without_rewrite(self):
        harness=legacy.OriginalPhysicalPrimitiveTests();self.addCleanup(harness.doCleanups)
        fixture,runtime,task,summary=harness.physical(False,role='review',packet={'synthetic':'review'})
        roles={'review':{'turns':2}}
        with self.assertRaises(ValueError):proposal._physical(BoundReader(fixture.f.ledger),runtime,task,summary,roles)
        evidence=proposal._physical(BoundReader(fixture.f.ledger),runtime,task,summary,roles,completed_generations={'review':1})
        self.assertGreaterEqual(len(evidence),6);self.assertEqual(roles['review']['turns'],2)
        for counts in ({'review':0},{'review':True},{'review':3},{'author':1}):
            with self.subTest(counts=counts),self.assertRaises(ValueError):
                proposal._physical(BoundReader(fixture.f.ledger),runtime,task,summary,roles,completed_generations=counts)
        self.assertEqual(len(fixture.wire_calls),2)

    def test_original_temp_settled_generation_cannot_be_counted_twice(self):
        harness=legacy.OriginalPhysicalPrimitiveTests();self.addCleanup(harness.doCleanups)
        fixture,runtime,task,summary=harness.physical(False)
        owned=proposal._owned_requests(runtime)
        with patch.object(proposal,'_owned_requests',return_value=owned+owned):
            with self.assertRaisesRegex(ValueError,'duplicate'):
                proposal._physical(BoundReader(fixture.f.ledger),runtime,task,summary,{'controller':{'turns':2}})


if __name__=='__main__':unittest.main()
