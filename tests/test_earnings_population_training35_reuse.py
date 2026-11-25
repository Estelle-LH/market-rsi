"""Independent successful-prefix attachment boundaries, never completed35.

Only temporary public/source/ledger fixtures are permitted here. Original
driver, binding, split, literal assembly and marker verifiers are exercised;
explicit old-ancestry/admission/case seams are not actual Native authority.
No model, network, Docker, candidate/scorer execution or real ledger is used.
"""
from contextlib import ExitStack
from copy import deepcopy
import json
import hashlib
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import earnings_population_continuation as history
import earnings_population_recovery as recovery
import earnings_population_training25 as training
import earnings_population_services as services
import earnings_population_forecast_failure as forecast_failure
import earnings_population as pool
import earnings_population_run as run
import earnings_population_campaign_admission as admission
import earnings_population_campaign as campaign
import earnings_population_completed as completed
import earnings_population_rejection as rejection
import earnings_population_tasks as tasks
import earnings_population_budget as budget
import earnings_population_campaign_resume as original_resume
import earnings_entry as entry
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness import feedback_linked_loop as driver
from supervisor_harness.continuous_discovery_batch import BatchStoppedError
import test_earnings_population_rejection as prefix_fixture
import test_earnings_population_review_reuse as reuse_fixture
import test_earnings_population_case as case_fixture


MODE = 'training25_reviewed_candidate_preclaim_deadline_v1'
COMPANY = 'CIK0000021076'


class ScopeFixture(unittest.TestCase):
    """Real split/admit validation against an explicitly invented frozen file."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='training35-independent-')
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.root, self.repo = self.home/'owned', self.home/'repo'
        self.root.mkdir(); self.repo.mkdir()
        ids = sorted(training.KNOWN3 | {COMPANY})
        ids += [f'CIK{1000000+n:010d}' for n in range(21)]
        self.heldout = [f'CIK{2000000+n:010d}' for n in range(25)]
        self.split = engine.save(self.root/'split.json', {
            'schema':'edgar_retrospective_prospectively_sealed_split_v1',
            'status':'FROZEN_RETROSPECTIVE_PROSPECTIVE_SEAL',
            'historical_isolation_certified':False, 'training':ids, 'heldout':self.heldout})
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        for name, value in [('ROOT',self.root), ('SPLIT',Path(self.split['path'])),
                            ('SPLIT_SHA',self.split['sha256'])]:
            self.stack.enter_context(patch.object(training,name,value))
        self.scope = training.load_scope(self.split)
        self.stack.enter_context(patch('socket.socket',side_effect=AssertionError('No network')))


class SplitBoundaryTests(ScopeFixture):
    def test_real_frozen_split_current_company_and_scope_are_not_caller_assertions(self):
        self.assertEqual(training.admit(self.scope,COMPANY),COMPANY)
        for scope,cik in [(dict(self.scope,training=self.scope['training']+[self.heldout[0]]),COMPANY),
                          (self.scope,self.heldout[0]),(self.scope,'CIK9999999999'),
                          (self.scope,None),(self.scope,True)]:
            with self.subTest(cik=cik), self.assertRaises(ValueError):
                training.admit(scope,cik)

    def test_wrong_split_hash_alias_and_label_refuse_before_any_new_body_read(self):
        cases = [dict(self.split,sha256='0'*64),
                 dict(self.split,path=str(self.root/'..'/'owned'/'split.json')),
                 dict(self.split,path=str(self.home/'foreign.json'))]
        with patch.object(training,'_read',side_effect=AssertionError('Forbidden body')) as read:
            for bound in cases:
                with self.subTest(bound=bound),self.assertRaises(ValueError):
                    training.load_scope(bound)
        read.assert_not_called()


class AttachmentPolicyTests(ScopeFixture):
    """Real A1 source-plan lookup; temporary authority is not a human grant."""
    def setUp(self):
        super().setUp()
        self.authority = engine.save(self.root/'direct-authority.json',{'synthetic_direct_authority':True})
        stage = engine.save(self.root/'stage-authority.json',{
            'schema':'edgar_training_stage_authority_record_v1',
            'direct_human_instruction':training.AUTHORIZATION,
            'stage_start':dict(ledger_rows=6401,booked_nano_usd=187429960800,
                ledger_prefix_sha256='0c343c36c21c496b7f6263ba4ec9afb8ffb5dcb347b0e4195e63349112ce252a',
                pending_requests=0,fixed_model_booked_nano_usd=79944786300)})
        for name,value in [('STAGE_AUTHORITY',stage),('STAGE_ATTACHMENT_AUTHORITY',self.authority)]:
            self.stack.enter_context(patch.object(training,name,value))
        self.input = engine.save(self.root/'attachment-input.json',{'synthetic_attachment_metadata':True})
        self.id = 'edgar-population-20261016-36'
        self.spec = dict(mode=MODE,apply_to_attempt=self.id,company_id=COMPANY,
                         input=self.input,authority=self.authority)
        self.base = dict(schema='supervisor_bottleneck_plan_v1',
            id='earnings-population-training25-20261019',human_authorization=training.AUTHORIZATION,
            training_policy=training.POLICY,split=self.split,stage_authority=stage,
            max_decisions=1,scope=training.SCOPE)
        (self.repo/training.PLAN).parent.mkdir(parents=True)

    def plan(self, value=None):
        path = self.repo/training.PLAN
        path.write_text(json.dumps(dict(self.base,successful_stage_attachment=self.spec)
                                   if value is None else value))
        return engine.pin(path)

    def lookup(self, bound, **changes):
        kwargs = dict(repo=self.repo,attempt_id=self.id,company_id=COMPANY,
                      attachment_binding=self.input)
        kwargs.update(changes)
        return training.stage_attachment_policy(bound,**kwargs)

    def test_targeted_policy_is_metadata_only_exact_and_not_reused_next_window(self):
        bound = self.plan()
        with patch.object(training,'_bytes',wraps=training._bytes) as reads:
            returned = self.lookup(bound)
        self.assertEqual(returned,self.spec)
        self.assertNotIn(self.input,[call.args[0] for call in reads.call_args_list])
        returned['input']['sha256'] = '0'*64
        self.assertEqual(self.lookup(bound),self.spec)
        # No explicit input is a policy lookup for upstream marker-erasure checks,
        # not permission for the producer to silently add the attachment.
        self.assertEqual(self.lookup(bound,attachment_binding=None),self.spec)
        self.assertIsNone(self.lookup(bound,attempt_id='edgar-population-20261016-37',
                                      attachment_binding=None))
        with self.assertRaises(ValueError):
            self.lookup(bound,attempt_id='edgar-population-20261016-37')

    def test_absent_policy_preserves_plain_shape_and_rejects_explicit_attachment(self):
        bound = self.plan(self.base)
        self.assertEqual(training.entry_plan(bound,self.repo),self.base)
        self.assertIsNone(self.lookup(bound,attachment_binding=None))
        with self.assertRaises(ValueError): self.lookup(bound)

    def test_wrong_target_company_input_and_bad_policy_types_fail_closed(self):
        bound = self.plan()
        for changes in ({'company_id':self.heldout[0]}, {'company_id':'CIK0000004457'},
                        {'attachment_binding':dict(self.input,sha256='0'*64)}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.lookup(bound,**changes)
        policies = [None,False,[],dict(self.spec,mode='other'),
            dict(self.spec,apply_to_attempt='edgar-population-20261016-35'),
            dict(self.spec,company_id='CIK0000004457'),dict(self.spec,extra=True),
            dict(self.spec,input=dict(self.input,sha256=True)),
            dict(self.spec,input=dict(self.input,path=str(self.home/'foreign.json')))]
        for spec in policies:
            with self.subTest(spec=spec),self.assertRaises(ValueError):
                self.lookup(self.plan(dict(self.base,successful_stage_attachment=spec)))

    def test_current_plan_hash_alias_and_historical_registered_source_are_distinct(self):
        bound = self.plan()
        raw = Path(bound['path']).read_bytes()
        reader = history._Reader(self.root,self.home/'inert.sqlite3',self.repo,self.id)
        reader.register_sources(dict(source_commit='a'*40,sources={training.PLAN:bound}))
        Path(bound['path']).write_text('{"not_the_original_plan":true}')
        with self.assertRaises(ValueError): self.lookup(bound)
        with patch.object(history,'_git',return_value=raw) as git:
            self.assertEqual(self.lookup(bound,historical_reader=reader),self.spec)
            reader.sources.clear()
            with self.assertRaises(ValueError): self.lookup(bound,historical_reader=reader)
        git.assert_called_once()
        Path(bound['path']).write_bytes(raw)
        alias = dict(bound,path=str(self.repo/'..'/'repo'/training.PLAN))
        with self.assertRaises(ValueError): self.lookup(alias)

    def test_routing_view_copies_but_never_replaces_scientific_predecessor(self):
        previous = engine.save(self.root/'original-completed.json',{'synthetic_previous':True})
        child = {'id':'b'*64}
        base = dict(previous_result=previous,population={'stable_id':'a'*64},
                    feedback={'exact_original_latest':True},last_scored_feedback={'exact_original_score':True},
                    evidence=[previous])
        receipt = dict(schema=training.STAGE_ATTACHMENT_RECEIPT,mode=MODE,input=self.input,
            authority=self.authority,completed_origin=previous,company_id=COMPANY,candidate_id=child['id'],
            author_stage_reuse={'candidate':child},review_stage_reuse={'candidate':deepcopy(child)},
            delivery_diagnosis={'unscored':True},evidence=[self.input])
        original = deepcopy((base,receipt))
        routed = training.stage_routing_origin(base,receipt)
        for key in ('previous_result','population','feedback','last_scored_feedback'):
            self.assertEqual(routed[key],base[key])
        self.assertEqual(routed['training_stage_attachment'],self.input)
        self.assertEqual(routed['evidence'],[previous,self.input])
        routed['population']['stable_id']='0'*64
        self.assertEqual((base,receipt),original)
        for update in ({'schema':'other'},{'mode':'other'},{'company_id':self.heldout[0]},
                       {'completed_origin':self.input},{'candidate_id':'c'*64},
                       {'review_stage_reuse':{'candidate':{'id':'c'*64}}}):
            with self.subTest(update=update),self.assertRaises(ValueError):
                training.stage_routing_origin(base,dict(receipt,**update))
        with self.assertRaises(ValueError):
            training.stage_routing_origin(dict(base,author_stage_reuse={}),receipt)


class PrefixFixture(unittest.TestCase):
    """Original once-only driver produces exactly fourdone then executefailed."""
    def setUp(self):
        self.f = prefix_fixture.RejectionPrefixContracts(methodName='runTest')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.reader,self.runtime,self.attempt = self.f.reader,self.f.runtime,self.f.attempt
        campaign_source = engine.save(self.f.root/'tools/earnings_population_campaign.py',
                                      {'synthetic_original_campaign':True})
        self.campaign = engine.save(self.f.root/'campaign.json',{'synthetic_original_campaign':True})
        self.runtime['sources']['tools/earnings_population_campaign.py'] = campaign_source
        self.runtime['forecast_study'] = engine.save(self.f.root/'study.json',{'campaign':self.campaign})
        self.runtime['training_policy'] = training.POLICY
        for row in self.f.identity.values():
            row.update(campaign_policy=campaign_source,campaign=self.campaign)

    def build(self, exception_type):
        def fail(context):
            raise exception_type('deadline_reached: synthetic no-claim boundary')
        self.f.handlers['execute'] = fail
        with self.assertRaises(driver.LoopHalted):
            driver.run(self.attempt/'loop',self.f.handlers,seed=self.f.seed,
                       admit=lambda ctx:True,max_rounds=1,
                       handler_identity=lambda:self.f.identity)


class LegacyPrefixTests(PrefixFixture):
    def test_actual_driver_is_four_done_before_execute_not_five(self):
        self.build(BatchStoppedError)
        stages = list(driver.STAGES[:driver.STAGES.index('execute')])
        self.assertEqual(stages,['input','controller','implement','source_review'])
        self.assertEqual(sorted(p.name for p in (self.attempt/'loop').glob('*.done.json')),
                         sorted(f'round-0001-{s}.done.json' for s in stages))
        with self.assertRaisesRegex(ValueError,'failure record differs'):
            recovery._prefix(self.reader,self.runtime,self.attempt,failed_stage='execute')
        self.assertFalse((self.attempt/'loop/round-0001-execute.done.json').exists())

    def test_absent_new_mode_preserves_original_runtimeerror_prefix(self):
        self.build(RuntimeError)
        before = {p:p.read_bytes() for p in (self.attempt/'loop').iterdir() if p.is_file()}
        seed,outputs,evidence = recovery._prefix(self.reader,self.runtime,self.attempt,failed_stage='execute')
        self.assertEqual(seed,self.f.seed)
        self.assertEqual(list(outputs),list(driver.STAGES[:driver.STAGES.index('execute')]))
        self.assertEqual(before,{p:p.read_bytes() for p in before})
        self.assertTrue(evidence)


class TypedPrefixTests(PrefixFixture):
    def test_exact_typed_execute_exception_is_separate_from_legacy_default(self):
        self.build(BatchStoppedError)
        before = {p:p.read_bytes() for p in (self.attempt/'loop').iterdir() if p.is_file()}
        seed,outputs,evidence = recovery._prefix(self.reader,self.runtime,self.attempt,
            failed_stage='execute',failure_kind=MODE)
        self.assertEqual(seed,self.f.seed)
        self.assertEqual(list(outputs),list(driver.STAGES[:driver.STAGES.index('execute')]))
        self.assertEqual(before,{p:p.read_bytes() for p in before})
        self.assertTrue(evidence)
        with self.assertRaises(ValueError):
            recovery._prefix(self.reader,self.runtime,self.attempt,failed_stage='execute')

    def test_typed_route_refuses_wrong_exception_or_scope_without_mutating_originals(self):
        self.build(RuntimeError)
        with self.assertRaises(ValueError):
            recovery._prefix(self.reader,self.runtime,self.attempt,
                             failed_stage='execute',failure_kind=MODE)
        for runtime,stage,kind in [
            (self.runtime,'source_review',MODE),
            (dict(self.runtime,training_policy='other'),'execute',MODE),
            (dict(self.runtime,companies=['CIK0000004457']),'execute',MODE),
            (self.runtime,'execute','other'),(self.runtime,'execute',True)]:
            with self.subTest(stage=stage,kind=kind),self.assertRaises(ValueError):
                recovery._prefix(self.reader,runtime,self.attempt,failed_stage=stage,failure_kind=kind)


class ReusedPrimitiveTests(unittest.TestCase):
    def setUp(self):
        self.f = reuse_fixture.ReusedStageTests(methodName='runTest')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)

    def test_original_v1_assembly_routes_newfeedback_without_rewriting_original_science(self):
        original = deepcopy((self.f.state,self.f.bundle))
        self.f.drive_reuse()
        routed = engine.read(engine.pin(self.f.owner.root/'roles/controller-01/population-decision.json'))
        selected = self.f.owner.authored[self.f.child['id']]['decision']
        self.assertNotEqual(routed['feedback_sha256'],self.f.bundle['scientific_decision']['feedback_sha256'])
        self.assertEqual(selected,self.f.bundle['scientific_decision'])
        self.assertEqual(Path(self.f.child['R']['path']).read_text(),
                         self.f.owner.authored[self.f.child['id']]['source'])
        self.assertEqual(self.f.child['H'],self.f.parent_h)
        self.assertEqual((self.f.state,self.f.bundle),original)
        self.f.role.propose.assert_not_called(); self.f.role.author.assert_not_called()
        self.assertFalse(self.f.marker.exists())

    def test_explicit_training_v1_requires_both_durable_stage_bindings(self):
        self.f.drive_reuse()
        rows = {stage:engine.read(engine.pin(self.f.owner.root/'loop'/
                    f'round-0001-{stage}.done.json'))['output'] for stage in driver.STAGES}
        reader = prefix_fixture.BoundReader()
        origin = {'author_stage_reuse':self.f.bundle,
                  'training_stage_attachment':{'schema':'earnings_training25_verified_stage_attachment_v1',
                                               'mode':MODE}}
        recovery.verify_reused_stages(reader,self.f.owner.root,rows,origin)
        for stage in ('controller','implement'):
            for field in ('stage_reuse','artifacts'):
                altered = deepcopy(rows); altered[stage].pop(field)
                with self.subTest(stage=stage,field=field),self.assertRaises(ValueError):
                    recovery.verify_reused_stages(reader,self.f.owner.root,altered,origin)
        # Absent attachment retains original legacy v1/baseNone expectations.
        legacy = deepcopy(rows)
        for stage in ('controller','implement'):
            legacy[stage].pop('stage_reuse'); legacy[stage].pop('artifacts')
        recovery.verify_reused_stages(reader,self.f.owner.root,legacy,
                                     {'author_stage_reuse':self.f.bundle})

    def test_raw_parent_scientific_digest_source_or_tests_tamper_refuse_inertly(self):
        selected = self.f.bundle['scientific_decision']
        raw = engine.read(self.f.raw)
        public = json.loads(raw['output'][0]['content'][0]['text'])
        for update in ({'decision_sha256':'0'*64},{'parent_source_sha256':'0'*64},
                       {'edits':[{'kind':'replace','old_text':'absent anchor','new_text':'bad'}]},
                       {'test_text':'not valid python ('}):
            changed = deepcopy(raw)
            changed['output'][0]['content'][0]['text'] = json.dumps(dict(public,**update))
            with self.subTest(update=update),self.assertRaises((ValueError,SyntaxError)):
                business = services.assemble(self.f.parent_r,selected,changed)
                services.candidate(business,services.program(Path(self.f.parent_r['path']).read_bytes(),'R'),selected)
        self.assertFalse(self.f.marker.exists())


class AcceptedReviewPrimitiveTests(unittest.TestCase):
    """Real existing Review marker verifier; no original-review authority claim."""
    def setUp(self):
        self.f = reuse_fixture.ReusedStageTests(methodName='runTest')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        folder = self.f.root/'roles/review-01'
        folder.mkdir(parents=True)
        (self.f.root/'loop').mkdir()
        business = dict(candidate_id=self.f.child['id'],accepted_for_exploration=True,
                        rationale='Explicit synthetic research-code review, not a score.')
        raw = engine.save(folder/'response.json', {'status':'completed','output':[
            {'type':'message','role':'assistant','content':[
                {'type':'output_text','text':json.dumps(business)}]}]})
        projection = engine.save(folder/'review.json',dict(original=raw,review=business))
        role = engine.save(folder/'result.json',dict(status='COMPLETED_REVIEW',
                                                    error_type=None,retry_allowed=False))
        self.evidence = [raw,self.f.assembly]
        done = engine.save(self.f.root/'loop/round-0001-source_review.done.json',{
            'output':dict(accepted_for_exploration=True,evidence=self.evidence)})
        self.review = dict(schema='earnings_population_review_stage_reuse_v1',
            mode=forecast_failure.REUSE, source_attempt=self.f.bundle['failed_attempt'],
            candidate=self.f.child, scientific_decision_sha256=digest(self.f.bundle['scientific_decision']),
            original_response=raw,review_projection=projection,role_result=role,
            source_review_output=done,evidence=self.evidence,new_model_Review_called=False)
        self.slot = self.f.owner.root/'roles/review-01'

    def receipt(self, review=None):
        return forecast_failure.reuse_receipt(self.review if review is None else review,
            self.f.bundle,self.f.child,self.slot)

    def test_original_accepted_review_has_explicit_no_new_model_attribution(self):
        original = deepcopy((self.review,self.f.bundle))
        marker = self.receipt()
        self.assertIs(marker['new_model_called'],False)
        self.assertEqual(marker['candidate_id'],self.f.child['id'])
        self.assertEqual(marker['original_response'],self.review['original_response'])
        self.assertEqual((self.review,self.f.bundle),original)
        self.assertFalse(self.slot.exists())

    def test_changed_source_candidate_science_mode_or_original_sibling_refuses(self):
        other_raw = engine.save(self.f.root/'copied-response.json',engine.read(self.review['original_response']))
        for update in ({'candidate':dict(self.f.child,id='0'*64)},
                       {'scientific_decision_sha256':'0'*64},{'mode':'other'},
                       {'new_model_Review_called':True},{'original_response':other_raw}):
            with self.subTest(update=update),self.assertRaises(ValueError):
                self.receipt(dict(self.review,**update))

    def test_durable_marker_and_no_extra_model_receipts_are_both_required(self):
        self.slot.mkdir(parents=True)
        bound = engine.save(self.slot/'review-stage-reuse.json',self.receipt())
        rows = {'implement':{'candidate':self.f.child},
                'source_review':dict(accepted_for_exploration=True,evidence=[bound,*self.evidence])}
        origin = {'author_stage_reuse':self.f.bundle,'review_stage_reuse':self.review}
        reader = prefix_fixture.BoundReader()
        forecast_failure.verify_reused_review(reader,self.f.owner.root,rows,origin)
        missing = deepcopy(rows); missing['source_review']['evidence'].pop(0)
        with self.assertRaises(ValueError):
            forecast_failure.verify_reused_review(reader,self.f.owner.root,missing,origin)
        for name in ('response.json','result.json','01-request.json','http-extra.intent.json'):
            path = self.slot/name; path.write_text('{}')
            with self.subTest(name=name),self.assertRaises(ValueError):
                forecast_failure.verify_reused_review(reader,self.f.owner.root,rows,origin)
            path.unlink()


class ProducerReceiverFixture(unittest.TestCase):
    """Real new-file producer/admission; old ancestry and incident body are seams.

    The public A loader is NOT mocked. Its private incident verifier is supplied
    an invented receipt only after the original completed-loader fixture returns.
    No full history, Native authority or financial activation is claimed.
    """
    needs_A2 = True
    def setUp(self):
        self.p = AttachmentPolicyTests(methodName='runTest')
        self.p.setUp(); self.addCleanup(self.p.doCleanups)
        self.r = AcceptedReviewPrimitiveTests(methodName='runTest')
        self.r.setUp(); self.addCleanup(self.r.doCleanups)
        self.f = self.r.f
        self.root,self.repo,self.id,self.scope = self.p.root,self.p.repo,self.p.id,self.p.scope
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.public = case_fixture.PopulationCaseTests(methodName='runTest')
        self.public.setUp(); self.addCleanup(self.public.doCleanups)
        self.resident = self.public.company(COMPANY)
        self.resident['runtime'] = {'max_input_tokens':100000,'max_output_tokens':25000,
            'company_wall_seconds':1800,'models':{'gpt-6.1-sol':{'api_model':'gpt-6.1-sol',
                'effort':'max','input':'2','cached':'0.1','write':'2.5','output':'10'}}}
        self.control = pool.version(self.f.source('fixed-control.py',
            "PROGRAM={'axis':'R'}\ndef run(p): return {'method':'control'}\n"),self.f.parent_h)
        self.parent = dict(self.f.parent,parent=self.control['id'],axis='R')
        state = pool.initialize(self.control,{'K':'a'*64,'M':'b'*64,'C':'c'*64})
        self.state = pool.retain(state,self.parent,reason='Synthetic prior accepted explorer',
                                 evidence=[self.parent['R']])
        self.ledger = self.root/'pilot/api-budget.sqlite3'
        self.cumulative = engine.save(self.root/'cumulative.json',{'synthetic_400_grant':True})
        self.model = engine.save(self.root/'named-model.json',{'synthetic_300_grant':True})
        self.comparator = engine.save(self.root/'comparator.json',{'synthetic_25_plain_rows':True})
        for obj,name,value in [(run,'ROOT',self.root),(entry,'REPO',self.repo),
                (entry,'PILOT',self.ledger.parent),(admission,'ROOT',self.root),
                (admission,'REPO',self.repo),(services,'REPO',self.repo),
                (rejection,'LEDGER',self.ledger),(rejection,'PARENT',self.control['id']),
                (original_resume,'LEDGER',self.ledger),(original_resume,'REPO',self.repo),
                (original_resume,'OWNED',self.root),
                (run,'FULL_PLAN',self.public.data),(run,'SCORER',self.public.scorer),
                (tasks,'FULL_PLAN',self.public.data),(tasks,'SCORER',self.public.scorer)]:
            self.stack.enter_context(patch.object(obj,name,value))
        self.stack.enter_context(patch.object(training,'load_comparator',return_value={
            'schema':'explicit_synthetic_comparator_seam','rows':[]}))
        self.stack.enter_context(patch.object(training,'DRIVER',engine.save(
            self.root/'inert-plain-driver.py',{'synthetic_driver_bytes_only':True})))
        self.stack.enter_context(patch.object(budget,'amendment_binding',return_value=self.cumulative))
        self.stack.enter_context(patch.object(tasks,'resident',side_effect=self.resident_for))
        self.stack.enter_context(patch.object(run,'resident',side_effect=self.resident_for))
        self.contract = admission.scientific_contract(self.resident,training_scope=self.scope)
        old = self.root/'attempts/edgar-population-20261016-34'; old.mkdir(parents=True)
        previous_input = self.root/'inputs/edgar-population-20261016-34'; previous_input.mkdir(parents=True)
        self.population = engine.save(old/'population-01.json',self.state)
        frozen = engine.save(old/'frozen-pool-01.json',self.state)
        public_seed = engine.save(self.root/'original-seed.json',{'synthetic_public_seed':True})
        chosen = dict(axis='R',parent_pair_sha256=self.control['id'],hypothesis='Synthetic original',
                      feedback_sha256='b'*64)
        decision = engine.save(old/'original-decision.json',chosen)
        original_campaign = engine.save(previous_input/'campaign.json',dict(
            schema='earnings_population_campaign_v1',panel=[COMPANY],max_decisions=1,
            baseline_version_id=self.control['id'],contract=self.contract))
        measured = dict(company_id=COMPANY,results=[dict(version_id=v['id'],points=1,
            evidence=[v['R']]) for v in (self.control,self.parent)])
        feedback = campaign.feedback(engine.read(original_campaign),
            {'feedback':public_seed,'last_scored_feedback':public_seed},chosen,self.parent,
            {'accepted_for_exploration':True,'evidence':[self.parent['R']]},measured,1,decision)
        self.feedback = engine.save(old/'feedback-01.json',feedback)
        record = engine.save(old/'decision-01.json',dict(schema='earnings_population_campaign_decision_v1',
            round_index=1,feedback=self.feedback,population_sha256=digest(self.state),frozen=frozen,
            campaign=original_campaign,kind=feedback['kind'],score_state=feedback['score_state'],
            parent_id=feedback['chosen_parent_id'],baseline_version_id=self.control['id'],
            candidate_id=self.parent['id']))
        self.previous = engine.save(old/'population-run-result.json',dict(
            status='COMPLETED_DISCOVERY_PILOT',retry_allowed=False,result=dict(status='completed',
            completed_rounds=1,result=dict(artifacts=[self.population,self.feedback,record],company_id=COMPANY,
            decision_record=record,feedback=self.feedback,last_scored_feedback=self.feedback,
            latest_feedback=self.feedback,population=self.state))))
        self.origin = dict(previous_result=self.previous,population=self.state,feedback=self.feedback,
            research_feedback=feedback,last_scored_feedback=self.feedback,reference_candidate={
                'parent':self.parent['id'],'axis':'R','source':self.parent['R']},
            original_research_feedback=feedback,evidence=[self.previous,self.population,self.feedback])
        # Only public metadata is authentic here. Incident source/receipt/fee/
        # Native bytes below are intentionally deferred to the private-body seam.
        authority_path = Path(self.p.authority['path'])
        authority_path.write_text(json.dumps({
            'schema':'earnings_training25_closed_successful_stage_attachment_authority_v1',
            'human_answer':'授权窄化复用35候选，审查通过后直接预测',
            'candidate_pair':self.f.child['id'],'researcher_sha256':self.f.child['R']['sha256'],
            'failed_attempt':'edgar-population-20261016-35'}))
        self.p.authority = engine.pin(authority_path)
        self.stack.enter_context(patch.object(training,'STAGE_ATTACHMENT_AUTHORITY',self.p.authority))
        old35 = self.root/'attempts/edgar-population-20261016-35'
        metadata = dict(schema=training.STAGE_ATTACHMENT_SCHEMA,mode=MODE,authority=self.p.authority,
            completed_origin=self.previous,company_id=COMPANY,candidate_id=self.f.child['id'],
            failed_attempt=dict(path=str(old35/'population-run-failure.json'),sha256='d'*64),
            source=dict(path=str(old35/'roles/author-01/candidate.py'),sha256=self.f.child['R']['sha256']),
            tests=dict(path=str(old35/'roles/author-01/cases.py'),sha256=self.f.bundle['tests']['sha256']),
            accepted_review=dict(path=str(old35/'roles/review-01/review.json'),sha256='e'*64),
            closed_failure_audit=dict(path=str(self.root/'closure.json'),sha256='f'*64),
            stage_delivery_audit=dict(path=str(self.root/'delivery.json'),sha256='a'*64))
        Path(self.p.input['path']).write_text(json.dumps(metadata))
        self.p.input = engine.pin(Path(self.p.input['path']))
        self.p.spec.update(input=self.p.input,authority=self.p.authority)
        self.receipt = dict(schema=training.STAGE_ATTACHMENT_RECEIPT,mode=MODE,input=self.p.input,
            authority=self.p.authority,completed_origin=self.previous,company_id=COMPANY,
            candidate_id=self.f.child['id'],author_stage_reuse=self.f.bundle,
            review_stage_reuse=self.r.review,delivery_diagnosis={'unscored':True},
            evidence=[self.f.bundle['failed_attempt'],self.f.assembly])
        self.plan = self.p.plan()
        (self.repo/'tools').mkdir(exist_ok=True)
        self.forecaster = engine.save(self.repo/'tools/edgar_forecast_openai.py',{'synthetic_forecaster':True})
        self.restore_plan = engine.save(self.repo/run.PLAN,{'synthetic_restore_plan':True})
        manifest = engine.save(self.root/'adopted-manifest.json',{'manifest':{
            'components':{'R':{'sources':{'researcher_child_01.py':
                'c3296f1b75cc10a6e67f746b0137f99f2f6765740b19f59b716acd29fa3907be'}}},
            'model':dict(requested_model='gpt-6.1-sol',serving_snapshot='unknown',serving_snapshot_verified=False)}})
        self.stack.enter_context(patch.object(run,'MANIFEST',Path(manifest['path'])))
        paths = {'forecaster':self.forecaster['path'],run.PLAN:self.restore_plan['path'],
                 training.PLAN:self.plan['path']}
        self.stack.enter_context(patch.object(run,'source_paths',return_value=paths))
        self.stack.enter_context(patch.object(run.subprocess,'run',side_effect=lambda cmd,**kw:
            SimpleNamespace(stdout='a'*40+'\n' if cmd[1]=='rev-parse' else
                            (self.repo/cmd[2].split(':',1)[1]).read_bytes())))
        self.baseline = dict(run.EXTRA_BASELINE,max_rowid=7105,request_count=7105,
                             charged_nano_usd=200906318200,rows_sha256='b'*64)
        self.stack.enter_context(patch.object(run,'idle_snapshot',return_value=self.baseline))
        self.stack.enter_context(patch.object(engine.activation,'_read',return_value=b'inert interpreter'))
        # Only the full runtime wrapper is intercepted; its actual trusted
        # training admission is called below with prepare's emitted files.
        self.stack.enter_context(patch.object(run,'preflight',side_effect=self.capture_admission))
        self.old_loader = self.stack.enter_context(patch.object(completed,'load',return_value=deepcopy(self.origin)))
        self.private_body = (self.stack.enter_context(patch.object(recovery,'_verify_training_stage_attachment',
            side_effect=lambda binding,**kwargs:deepcopy(self.receipt))) if self.needs_A2 else None)
        self.admitted = []

    def resident_for(self,cik):
        if cik != COMPANY:raise AssertionError('No other company body permitted')
        return deepcopy(self.resident)

    def capture_admission(self,binding,**kwargs):
        value = engine.read(binding); study = engine.read(value['forecast_study'])
        state = engine.read(value['initial_population'])
        residents = admission._training_validate(value,study,state)
        self.admitted.append((binding,deepcopy(residents)))
        return value

    def prepare(self,identifier=None,attachment=True):
        return run.prepare(identifier or self.id,company_count=1,campaign_from=self.previous['path'],
            cumulative400=True,window_minutes=90,training_cik=COMPANY,training_split=self.p.split,
            training_comparator=self.comparator,model_budget_amendment=self.model,
            training_stage_attachment=self.p.input if attachment else None)


class PublicAttachmentOrderTests(ProducerReceiverFixture):
    def load(self,**changes):
        kwargs = dict(completed_result=self.previous,training_scope=self.scope,company_id=COMPANY,
            attempt_id=self.id,root=self.root,ledger=self.ledger,repo=self.repo,plan_binding=self.plan)
        kwargs.update(changes)
        return recovery.load_training_stage_attachment(self.p.input,**kwargs)

    def test_real_public_predecessor_order_then_only_private_incident_seam(self):
        order = []
        def completed_first(*args,**kwargs):
            order.append('original_completed_predecessor_fixture')
            self.private_body.assert_not_called()
            return deepcopy(self.origin)
        def incident_second(binding,**kwargs):
            order.append('private_incident_body_fixture')
            self.assertEqual(kwargs['base_origin'],self.origin)
            self.assertEqual(kwargs['attempt_id'],self.id)
            self.assertEqual(binding,self.p.input)
            return deepcopy(self.receipt)
        self.old_loader.side_effect = completed_first
        self.private_body.side_effect = incident_second
        value = self.load()
        self.assertEqual(order,['original_completed_predecessor_fixture','private_incident_body_fixture'])
        self.assertEqual(value,dict(base_origin=self.origin,stage_attachment=self.receipt))
        self.old_loader.assert_called_once_with(self.previous,root=self.root,ledger=self.ledger,repo=self.repo)

    def test_original_predecessor_failure_propagates_without_reading_incident_body(self):
        self.old_loader.side_effect = ValueError('Original prior closure refused')
        with self.assertRaisesRegex(ValueError,'Original prior closure refused'):self.load()
        self.private_body.assert_not_called()

    def test_real_scope_membership_refuses_before_attachment_or_foreign_body(self):
        read = training._read
        def split_only(binding):
            if binding != self.p.split:raise AssertionError('No attachment or task body before admission')
            return read(binding)
        with patch.object(training,'_read',side_effect=split_only), \
             patch.object(tasks,'resident',side_effect=AssertionError('No task body')):
            for changes in ({'company_id':self.p.heldout[0]},
                            {'training_scope':dict(self.scope,training=self.scope['training']+self.p.heldout)},
                            {'company_id':True}):
                with self.subTest(changes=changes),self.assertRaises(ValueError):self.load(**changes)
        self.old_loader.assert_not_called(); self.private_body.assert_not_called()

    def test_same_training_but_other_company_and_wrong_roots_or_target_refuse(self):
        for changes in ({'company_id':'CIK0000004457'}, {'root':self.root/'foreign'},
                        {'ledger':self.root/'foreign.sqlite3'}, {'repo':self.repo/'foreign'},
                        {'attempt_id':'edgar-population-20261016-35'},
                        {'completed_result':dict(self.previous,sha256='0'*64)}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.load(**changes)
        self.old_loader.assert_not_called(); self.private_body.assert_not_called()

    def test_legitimately_repinned_bad_public_metadata_still_refuses_before_predecessor(self):
        metadata = engine.read(self.p.input)
        mutations = [dict(metadata,candidate_id='0'*64),dict(metadata,mode='other'),
            dict(metadata,extra=True),dict(metadata,source=dict(metadata['source'],sha256='0'*64)),
            dict(metadata,tests=dict(metadata['tests'],sha256=True)),
            dict(metadata,accepted_review=dict(metadata['accepted_review'],path=str(self.root/'other-review.json'))),
            dict(metadata,failed_attempt=dict(metadata['failed_attempt'],path=str(self.root/'attempts/other/failure.json')))]
        for changed in mutations:
            Path(self.p.input['path']).write_text(json.dumps(changed))
            self.p.input = engine.pin(Path(self.p.input['path']))
            self.p.spec['input'] = self.p.input; self.plan = self.p.plan()
            with self.subTest(changed=changed),self.assertRaises(ValueError):self.load()
        self.old_loader.assert_not_called(); self.private_body.assert_not_called()


class PreparedAttachmentTests(ProducerReceiverFixture):
    def test_emitted_sibling_goes_through_real_training_admission_without_origin_enrichment(self):
        bound = self.prepare()
        value = engine.read(bound); study = engine.read(value['forecast_study'])
        self.assertEqual(engine.read(study['campaign_origin']),self.origin)
        self.assertEqual(engine.read(value['initial_population']),self.state)
        self.assertEqual(engine.read(study['training_stage_attachment']),self.receipt)
        resume = engine.read(study['campaign_resume'])
        self.assertEqual(set(resume),{'schema','previous_result','plan','repair'})
        self.assertEqual(resume['previous_result'],self.previous)
        self.assertEqual(len(self.admitted),1)
        self.assertEqual(self.old_loader.call_count,2)  # Real public A once per producer/admission.
        self.assertEqual(self.private_body.call_count,2)
        self.assertEqual(value['baseline'],self.baseline)
        self.assertEqual(value['window_minutes'],90)
        self.assertEqual(value['additional_cap_nano_usd'],5000000000)

    def test_target_missing_explicit_input_stops_before_inputs_or_previous_loader(self):
        with self.assertRaisesRegex(ValueError,'explicit exact producer input'):
            self.prepare(attachment=False)
        self.assertFalse((self.root/'inputs'/self.id).exists())
        self.old_loader.assert_not_called(); self.private_body.assert_not_called()

    def test_emitted_missing_or_altered_receipt_wrong_origin_and_marker_erasure_refuse(self):
        bound = self.prepare(); value = engine.read(bound); study = engine.read(value['forecast_study'])
        for changed in (dict(study,training_stage_attachment=None),
                        {k:v for k,v in study.items() if k!='training_stage_attachment'},
                        dict(study,training_stage_attachment=self.p.input)):
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                admission._training_validate(value,changed,self.state)
        receipt_path = Path(study['training_stage_attachment']['path'])
        receipt_path.write_text(json.dumps(dict(self.receipt,candidate_id='0'*64)))
        forged = dict(study,training_stage_attachment=engine.pin(receipt_path))
        with self.assertRaisesRegex(ValueError,'Saved successful-stage receipt differs'):
            admission._training_validate(value,forged,self.state)


class CompletedReceiverOrderTests(ProducerReceiverFixture):
    """Real current completed dispatcher through private-A entry, then stop.

    Only predecessor recursion and historical model grant are temp fixtures;
    stopping before Native/scoring is deliberate, never an admission success.
    """
    def records(self,*,tamper_receipt=False):
        value = engine.read(self.prepare())
        self.attempt = self.root/'attempts'/self.id; self.attempt.mkdir(parents=True)
        if tamper_receipt:
            study = engine.read(value['forecast_study'])
            receipt_path = Path(study['training_stage_attachment']['path'])
            receipt_path.write_text(json.dumps(dict(self.receipt,candidate_id='0'*64)))
            study['training_stage_attachment'] = engine.pin(receipt_path)
            path = Path(value['forecast_study']['path']); path.write_text(json.dumps(study))
            value['forecast_study'] = engine.pin(path)
        inputs = self.root/'inputs'/self.id
        value['review'] = engine.save(inputs/'independent-review.json',{'synthetic_source_review':True})
        runtime = engine.save(inputs/'runtime-reviewed.json',value)
        registry = self.ledger.parent/'.capacity-runtime-claims'; registry.mkdir(parents=True)
        self.ledger.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.ledger) as db: db.execute('CREATE TABLE inert(value INTEGER)')
        stamp = hashlib.sha256(self.id.encode()).hexdigest()
        engine.save(registry/(stamp+'.json'),dict(id=self.id,runtime=runtime,
            retry_allowed=False,source_commit=value['source_commit']))
        engine.save(registry/(stamp+'.result.json'),dict(status='COMPLETED_COMPONENT_CONTEXT',
            error_type=None,retry_allowed=False,runtime=runtime,budget_summary={}))
        result = engine.save(self.attempt/'population-run-result.json',dict(
            status='COMPLETED_DISCOVERY_PILOT',retry_allowed=False,improvement_proven=False))
        self.old_loader.reset_mock(); self.private_body.reset_mock()
        return result

    def enter(self,result,*,reject_predecessor=False,stop_private=True):
        original_current = completed._load
        order = []
        class AttachmentReached(Exception):pass
        def recurse(binding,root,ledger,repo,seen):
            if binding == self.previous:
                order.append('original_predecessor_fixture')
                if reject_predecessor:raise ValueError('Original predecessor failed')
                return deepcopy(self.origin)
            return original_current(binding,root,ledger,repo,seen)
        def private(binding,**kwargs):
            order.append('private_attachment')
            self.assertEqual(kwargs['base_origin'],self.origin)
            self.assertIsInstance(kwargs['historical_reader'],history._Reader)
            if stop_private:raise AttachmentReached()
            return deepcopy(self.receipt)
        self.private_body.side_effect = private
        with patch.object(completed,'_load',side_effect=recurse), \
             patch.object(completed,'_model_grant',return_value=[]), \
             patch.object(history,'_git',side_effect=lambda repo,commit,name:(repo/name).read_bytes()), \
             patch.object(tasks,'resident',side_effect=AssertionError('No current body before attachment')):
            if reject_predecessor:
                with self.assertRaisesRegex(ValueError,'Original predecessor failed'):
                    original_current(result,self.root,self.ledger,self.repo,set())
            elif stop_private:
                with self.assertRaises(AttachmentReached):
                    original_current(result,self.root,self.ledger,self.repo,set())
            else:
                with self.assertRaisesRegex(ValueError,'Completed training stage receipt differs'):
                    original_current(result,self.root,self.ledger,self.repo,set())
        return order

    def test_actual_completed_receiver_replays_predecessor_before_attachment_and_body(self):
        order = self.enter(self.records())
        self.assertEqual(order,['original_predecessor_fixture','private_attachment'])

    def test_predecessor_failure_prevents_attachment_reentry(self):
        self.assertEqual(self.enter(self.records(),reject_predecessor=True),
                         ['original_predecessor_fixture'])
        self.private_body.assert_not_called()

    def test_receiver_reconstructs_and_refuses_changed_saved_receipt_before_task_body(self):
        self.assertEqual(self.enter(self.records(tamper_receipt=True),stop_private=False),
                         ['original_predecessor_fixture','private_attachment'])


class ServicesAttachmentTests(ProducerReceiverFixture):
    """Actual C/A/Review methods, no model; cases/forecast/admission are fixtures."""
    needs_A2 = False

    def setUp(self):
        super().setUp()
        self.inputs = self.root/'inputs'/self.id; self.inputs.mkdir(parents=True)
        self.origin_binding = engine.save(self.inputs/'campaign-origin.json',self.origin)
        self.saved_receipt = engine.save(self.inputs/'training-stage-attachment.json',self.receipt)
        link = engine.save(self.inputs/'training-state-link.json',training.link_state(
            training.POLICY,self.p.split,self.comparator,self.population,self.feedback,
            panel=[COMPANY],completed_origin=self.previous))
        latest = engine.save(self.inputs/'rejection-feedback.json',self.origin['research_feedback'])
        self.campaign = engine.save(self.inputs/'campaign.json',dict(
            schema='earnings_population_campaign_v1',source_plan=self.plan,panel=[COMPANY],
            baseline_version_id=self.control['id'],max_decisions=1,
            initial_population_sha256=digest(self.state),initial_feedback=latest,
            last_scored_feedback=self.feedback,contract=self.contract,validation_company_id=COMPANY,
            comparison_policy=campaign.PARENT_COMPARISON,training_state_link=link,
            **training.feedback_contracts(self.origin,self.scope)))
        resume = engine.save(self.inputs/'campaign-resume.json',dict(
            schema='earnings_population_campaign_resume_v1',previous_result=self.previous,
            plan=self.plan,repair=None))
        self.study = dict(campaign_origin=self.origin_binding,campaign_resume=resume,
                          training_stage_attachment=self.saved_receipt,campaign=self.campaign,
                          training_state_link=link)
        self.study_binding = engine.save(self.inputs/'study.json',self.study)
        self.owner = self.f.owner
        self.owner.root = self.root/'attempts'/self.id
        self.owner.runtime = dict(id=self.id,companies=[COMPANY],forecast_study=self.study_binding,
                                  sources={training.PLAN:self.plan})
        self.owner._training_scope = Mock(return_value=self.scope)
        self.f.role.review.side_effect = AssertionError('No new Review provider call')
        self.context = deepcopy(self.f.context)
        self.context.update(origin=self.origin_binding,training_scope=self.scope,
                            training_comparator={'explicit_synthetic':True},training_state={},
                            feedback_binding=self.feedback,campaign=engine.read(self.campaign))

    def drive(self):
        self.forecasted = []
        def forecast(version,company,slot):
            self.forecasted.append((version['id'],company,Path(slot).name))
            return dict(version_id=version['id'],points=1,evidence=[self.f.assembly])
        with patch.object(services,'public_feedback',return_value={'company_id':COMPANY}), \
             patch('earnings_population_campaign_context.prepare',return_value=deepcopy(self.context)):
            import earnings_population_loop as original_loop
            result = original_loop.run(self.owner.root,self.state,[COMPANY],{
                'controller':self.owner.controller,'author':self.owner.author,
                'review':self.owner.review,'forecast':forecast},admit=lambda ctx:True,max_rounds=1,
                identity=lambda:{s:{'explicit_inert_identity':s} for s in driver.STAGES},campaign=self.campaign)
        self.rows = {stage:engine.read(engine.pin(self.owner.root/'loop'/
            f'round-0001-{stage}.done.json'))['output'] for stage in driver.STAGES}
        return result

    def test_real_services_all_three_reused_stages_never_call_providers(self):
        original = deepcopy((self.state,self.origin,self.receipt))
        result = self.drive()
        self.assertEqual(result['status'],'completed')
        self.assertEqual([row[0] for row in self.forecasted],
                         [self.control['id'],self.parent['id'],self.f.child['id']])
        self.assertTrue(all(row[1]==COMPANY for row in self.forecasted))
        self.assertEqual([row[2] for row in self.forecasted],
                         ['forecast-01-00','forecast-01-01','forecast-01-02'])
        for method in (self.f.role.propose,self.f.role.author,self.f.role.review):
            method.assert_not_called()
        self.assertEqual((self.state,self.origin,self.receipt),original)
        self.assertEqual(engine.read(self.origin_binding),self.origin)
        self.assertEqual(self.owner.authored[self.f.child['id']]['decision'],
                         self.f.bundle['scientific_decision'])
        self.assertFalse(self.f.marker.exists())
        ephemeral = training.stage_routing_origin(self.origin,self.receipt)
        recovery.verify_reused_stages(prefix_fixture.BoundReader(),self.owner.root,self.rows,ephemeral)
        for role in ('controller','author','review'):
            folder = self.owner.root/'roles'/(role+'-01')
            self.assertFalse(list(folder.glob('http-*')))
            self.assertFalse(list(folder.glob('[0-9][0-9]-request.json')))
            self.assertFalse((folder/'response.json').exists())
            self.assertFalse((folder/'result.json').exists())
            marker = engine.read(engine.pin(folder/(role+'-stage-reuse.json')))
            self.assertIs(marker['new_model_called'],False)

    def test_retired_chosen_parent_remains_archived_and_is_really_compared(self):
        chosen = engine.read(self.f.bundle['decision'])
        chosen['retire_branch_id'] = self.parent['id']
        self.f.bundle['decision'] = engine.save(self.f.root/'original-retiring-decision.json',chosen)
        path = Path(self.saved_receipt['path']); path.write_text(json.dumps(self.receipt))
        self.saved_receipt = engine.pin(path)
        self.study['training_stage_attachment'] = self.saved_receipt
        study_path = Path(self.study_binding['path']); study_path.write_text(json.dumps(self.study))
        self.owner.runtime['forecast_study'] = engine.pin(study_path)
        result = self.drive()
        selected = result['result']['population']
        self.assertNotIn(self.parent['id'],selected['explorers'])
        self.assertIn(self.parent['id'],selected['versions'])
        self.assertEqual([row[0] for row in self.forecasted],
                         [self.control['id'],self.parent['id'],self.f.child['id']])
        self.assertEqual(self.owner.authored[self.f.child['id']]['decision'],
                         self.f.bundle['scientific_decision'])

    def test_training_bundle_without_sibling_is_rejected_and_next_id_does_not_autoimport(self):
        ordinary = dict(self.study); ordinary.pop('training_stage_attachment')
        plain = self.owner._reuse_origin(ordinary)
        self.assertEqual(plain,self.origin)
        self.owner.campaign_context = self.context
        self.owner.runtime['id']='edgar-population-20261016-37'
        self.owner.runtime['forecast_study'] = engine.save(self.inputs/'ordinary-study.json',ordinary)
        self.assertIsNone(self.owner.reused_author())
        with self.assertRaisesRegex(ValueError,'Canonical admitted'):
            self.owner._reuse_origin(self.study)
        enriched = training.stage_routing_origin(self.origin,self.receipt)
        bad = dict(ordinary,campaign_origin=engine.save(self.inputs/'bad-origin.json',enriched))
        self.owner.runtime['forecast_study'] = engine.save(self.inputs/'bad-study.json',bad)
        with self.assertRaisesRegex(ValueError,'genuine new'):
            self.owner.reused_author()

    def test_real_durable_training_markers_reject_missing_and_paid_regeneration(self):
        self.drive(); ephemeral = training.stage_routing_origin(self.origin,self.receipt)
        reader = prefix_fixture.BoundReader()
        for role,stage in [('controller','controller'),('author','implement')]:
            changed = deepcopy(self.rows); changed[stage].pop('stage_reuse')
            with self.subTest(role=role),self.assertRaises(ValueError):
                recovery.verify_reused_stages(reader,self.owner.root,changed,ephemeral)
        for role in ('controller','author','review'):
            path = self.owner.root/'roles'/(role+'-01')/'01-request.json'
            path.write_text('{"synthetic_forbidden_new_generation":true}')
            with self.subTest(role=role),self.assertRaises(ValueError):
                recovery.verify_reused_stages(reader,self.owner.root,self.rows,ephemeral)
            path.unlink()

    def test_driver_feedback_enters_actual_next_prepare_without_reimport(self):
        driven = self.drive(); final = driven['result']
        # Source/owner/Native completion is not invented: this wrapper and the
        # predecessor loader are explicit fixtures for the next producer only.
        previous = engine.save(self.owner.root/'population-run-result.json',dict(
            status='COMPLETED_DISCOVERY_PILOT',retry_allowed=False,result=driven))
        next_origin = dict(self.origin,previous_result=previous,population=final['population'],
            feedback=final['feedback'],research_feedback=engine.read(final['feedback']),
            last_scored_feedback=final['last_scored_feedback'],
            evidence=[previous,*final['artifacts']])
        self.old_loader.return_value = deepcopy(next_origin)
        bound = run.prepare('edgar-population-20261016-37',company_count=1,
            campaign_from=previous['path'],cumulative400=True,window_minutes=90,
            training_cik=COMPANY,training_split=self.p.split,training_comparator=self.comparator,
            model_budget_amendment=self.model)
        value = engine.read(bound); study = engine.read(value['forecast_study'])
        self.assertNotIn('training_stage_attachment',study)
        self.assertEqual(engine.read(study['campaign_origin']),next_origin)
        self.assertEqual(engine.read(value['initial_population']),final['population'])
        manifest = engine.read(study['campaign'])
        self.assertEqual(engine.read(manifest['initial_feedback']),engine.read(final['feedback']))
        self.assertEqual(engine.read(study['campaign_resume'])['previous_result'],previous)
        for method in (self.f.role.propose,self.f.role.author,self.f.role.review):
            method.assert_not_called()


if __name__ == '__main__':
    unittest.main()
