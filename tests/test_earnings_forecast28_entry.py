"""Forecast28 inert entry tests; real temporary Native proposal admission."""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import earnings_open_author_followthrough as flow
import earnings_open_fresh_grant as fresh
import earnings_candidate_transfer as transfer
from earnings_open_capacity import ProgramCapacity
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
import test_earnings_candidate_transfer as transfer_fixture
import test_earnings_forecast27_grant as grant_fixture


class Forecast28NativeEntryTests(unittest.TestCase):
    def setUp(self):
        self.t = transfer_fixture.CandidateTransferTests()
        self.t.setUp(); self.addCleanup(self.t.doCleanups)
        self.root = self.t.root
        self.scope = deepcopy(self.t.scope)
        self.scope['forecast_id'] = 'edgar-research-20261016-28'
        self.scope_binding = engine.save(self.root/'scope28.json', self.scope)
        self.runtime = dict(deepcopy(self.t.runtime), id=self.scope['forecast_id'],
            root=str(self.root/'attempt28'), slots={'forecast':[str(self.root/'attempt28/roles/forecast-01')]},
            ledger=str(self.root/'unused-invented-ledger.sqlite3'))
        self.runtime_binding = engine.save(self.root/'runtime28.json', self.runtime)
        self.value = dict(deepcopy(self.t.value), scope=self.scope_binding, runtime=self.runtime_binding,
            stage='forecast', author_result=engine.save(self.root/'author28.json', {'synthetic':True}),
            candidate_review=engine.save(self.root/'candidate-review28.json', {'synthetic':True}),
            candidate_git_source=engine.pin(self.t.f.source/flow.CHILD),
            grant=engine.save(self.root/'grant28.json', {'scorer':{'synthetic':True}, 'qa':{'synthetic':True}}),
            forecast_transport={'synthetic':True})
        self.fixed = flow.native_config(self.value)['fixed_context']
        self.record = transfer.derive(self.t.spec_binding, scope_binding=self.scope_binding,
            runtime_binding=self.runtime_binding, fixed_context=self.fixed)
        self.value['candidate_transfer'] = engine.save(self.root/'transfer28.json', self.record)
        self.prepared = engine.save(self.root/'prepared28.json', self.value)
        self.original_spec = Path(self.t.spec_binding['path']).read_bytes()
        self.old_journal = self.t.files(self.t.old_batch.journal_dir)

    def native_guards(self, stack):
        real_batch = ContinuousDiscoveryBatch
        stack.enter_context(mock.patch.object(flow.namespace, 'NATIVE_RUNTIME_ROOT', self.root/'native28'))
        stack.enter_context(mock.patch.object(flow, 'authority', return_value=self.scope))
        stack.enter_context(mock.patch.object(flow, 'ContinuousDiscoveryBatch', side_effect=lambda path, **kw:
            real_batch(path, allow_temporary=True, test_clock=lambda:self.t.now, allow_test_clock=True)))

    def exact_transfer(self):
        return transfer.validate(self.value['candidate_transfer'], specification_binding=self.t.spec_binding,
            scope_binding=self.scope_binding, runtime_binding=self.runtime_binding, fixed_context=self.fixed)

    def assert_old_unchanged(self):
        self.assertEqual(Path(self.t.spec_binding['path']).read_bytes(), self.original_spec)
        self.assertEqual(self.t.old_batch.snapshot(), self.t.old_state)
        self.assertEqual(self.t.files(self.t.old_batch.journal_dir), self.old_journal)
        self.assertEqual(self.t.files(self.t.f.source), self.t.sources)

    def test_exact28_transfer_real_propose_and_cold_shadow_resolution(self):
        with ExitStack() as stack:
            self.native_guards(stack)
            capacity = flow.native(self.value, create=True)
            (capacity.source_root/flow.CHILD).write_bytes((self.t.f.source/flow.CHILD).read_bytes())
            record = self.exact_transfer()
            projected = flow.preview_candidate(self.value, record)
            before = capacity.batch.snapshot()
            capacity.propose(self.t.spec['after'], record['proposal'], self.t.spec['entrypoints'],
                static_review=self.t.spec['static_review'], expected_state_sha256=before['state_sha256'])
            after = capacity.batch.snapshot(); pending = after['micro_evolution']['pending']
            self.assertEqual(pending, projected['pending'])
            self.assertEqual(after['micro_evolution']['active_pair'], before['micro_evolution']['active_pair'])
            cold = flow.native(self.value, create=False)
            self.assertEqual(cold.batch.snapshot(), after)
            resolved = cold.resolve('R', expected_pair_sha256=digest(before['micro_evolution']['active_pair']),
                                    shadow_proposal_sha256=pending['record_sha256'])
            self.assertEqual(resolved['receipt']['source']['sha256'], engine.pin(self.t.f.source/flow.CHILD)['sha256'])
            self.assertFalse(resolved['receipt']['model_code_executed'])
        self.assert_old_unchanged()

    def test_original_and_one_field_stale_proposals_fail_real_admission_without_append(self):
        with ExitStack() as stack:
            self.native_guards(stack)
            capacity = flow.native(self.value, create=True)
            (capacity.source_root/flow.CHILD).write_bytes((self.t.f.source/flow.CHILD).read_bytes())
            before = capacity.batch.snapshot(); journal = self.t.files(capacity.batch.journal_dir)
            variants = [deepcopy(self.t.old_proposal)]
            for field in ('authority_sha256','resource_policy_sha256'):
                stale = deepcopy(self.record['proposal'])
                stale['fixed_context'][field] = self.t.old_proposal['fixed_context'][field]
                variants.append(stale)
            for proposal in variants:
                with self.subTest(proposal=proposal), self.assertRaises(ValueError):
                    capacity.propose(self.t.spec['after'], proposal, self.t.spec['entrypoints'],
                        static_review=self.t.spec['static_review'], expected_state_sha256=before['state_sha256'])
                self.assertEqual(capacity.batch.snapshot(), before)
                self.assertEqual(self.t.files(capacity.batch.journal_dir), journal)
        self.assert_old_unchanged()

    def entry_guards(self, stack):
        self.native_guards(stack)
        source = (self.t.f.source/flow.CHILD).read_text()
        stack.enter_context(mock.patch.object(flow,'validate_prepared',return_value=(self.value,self.runtime)))
        stack.enter_context(mock.patch.object(flow,'candidate_gate',return_value=(
            {'source_text':source},{'source_sha256':engine.pin(self.t.f.source/flow.CHILD)['sha256']})))
        stack.enter_context(mock.patch.object(flow,'capture_or_load',return_value=({},'inert-clock')))
        stack.enter_context(mock.patch.object(flow.original_capacity,'task',return_value=({'synthetic':True},None)))
        state = mock.Mock(); state.empty.return_value = {'records':[]}
        state.save.side_effect = lambda path,value:engine.save(path.with_suffix('.json'), value)
        stack.enter_context(mock.patch.object(flow,'ResearchState',return_value=state))
        task = mock.Mock(); task.shadow_execution.return_value = {'synthetic':'verified result; not scored'}
        stack.enter_context(mock.patch.object(flow,'OpenTask',return_value=task))
        stack.enter_context(mock.patch.object(flow,'ProgramWorker',return_value=object()))
        stack.enter_context(mock.patch.object(flow,'DockerRunner',return_value=object()))
        stack.enter_context(mock.patch.object(flow,'containers_remaining',return_value=80))
        stack.enter_context(mock.patch.object(flow.assembly,'followthrough_factories',return_value={}))
        terminal = engine.save(self.root/'synthetic-owner-terminal.json', {'status':'COMPLETED_COMPONENT_CONTEXT'})
        stack.enter_context(mock.patch.object(flow,'owner_terminal',return_value=terminal))
        return task

    def test_actual_run_forecast_uses_real28_proposal_and_returns_exact_transfer(self):
        calls = []
        @contextmanager
        def owner(bound, **kwargs):
            self.assertEqual(bound, self.runtime_binding)
            def inert_forecast(worker, slot):
                calls.append(slot)
                return engine.save(self.root/'inert-forecast-output.json', {'synthetic':True})
            yield {'roles':{'forecast':inert_forecast}}
        with ExitStack() as stack:
            task = self.entry_guards(stack)
            stack.enter_context(mock.patch.object(flow,'open_capacity_runtime',side_effect=owner))
            result = engine.read(flow.run_forecast(self.prepared, {'synthetic':'prepared review'}))
            cold = flow.native(self.value, create=False)
            state = cold.batch.snapshot()
        self.assertEqual(calls, self.runtime['slots']['forecast'])
        self.assertEqual(result['candidate_transfer'], self.value['candidate_transfer'])
        self.assertFalse(result['candidate_adopted'])
        self.assertEqual(state['micro_evolution']['pending']['fixed_context'], self.fixed)
        self.assertEqual(state['capacity_work'][-1]['status'], 'completed')
        self.assertEqual(state['active_attempt_ids'], [])
        task.shadow_execution.assert_called_once()
        self.assert_old_unchanged()

    def test_transfer_tamper_stops_actual_entry_before_root_owner_and_Native(self):
        bad = deepcopy(self.record); bad['proposal']['fixed_context']['authority_sha256'] = 'f'*64
        self.value['candidate_transfer'] = engine.save(self.root/'forged-transfer28.json', bad)
        with ExitStack() as stack:
            self.entry_guards(stack)
            owner = stack.enter_context(mock.patch.object(flow,'open_capacity_runtime'))
            native = stack.enter_context(mock.patch.object(flow,'native'))
            with self.assertRaises(ValueError):flow.run_forecast(self.prepared, {'synthetic':'review'})
            owner.assert_not_called(); native.assert_not_called()
        self.assertFalse(Path(self.runtime['root']).exists())
        self.assert_old_unchanged()

    def test_actual_prepared_validator_requires_same28_transfer_and_distinct_exact_review(self):
        scope = dict(self.scope, author_max_input_tokens=24000, author_max_output_tokens=49152)
        scope_path = self.root/'validator-scope28.json'; scope_binding = engine.save(scope_path, scope)
        limits = {'controller':{'max_input_tokens':16000,'max_output_tokens':16384,'wall_seconds':600},
            'author':{'max_input_tokens':10000,'max_output_tokens':32768,'wall_seconds':900},
            'review':{'max_input_tokens':10000,'max_output_tokens':16384,'wall_seconds':600},
            'forecast':{'max_input_tokens':100000,'max_output_tokens':25000,'wall_seconds':600}}
        original_runtime = dict(self.runtime, limits=limits, role_efforts={'forecast':'max','author':'high'})
        original_grant = {key:'synthetic-'+key for key in ('data','runtime','qa','scorer','python','cik',
            'human_authorization','allowed_egress','bootstrap_no_model_call')}
        original_grant.update(ledger=self.runtime['ledger'], baseline=self.runtime['baseline'])
        original_study = {'cases':'public','program_lineage':{'historical':True}}
        old = deepcopy(self.value['prior'])
        old['handoff'].update(old_runtime=engine.save(self.root/'validator-original-runtime.json',original_runtime),
            old_episode=engine.save(self.root/'validator-original-episode.json',{
                'grant':engine.save(self.root/'validator-original-grant.json',original_grant),
                'study':engine.save(self.root/'validator-original-study.json',original_study)}))
        sources = {'inert':engine.pin(self.t.f.source/'kernel.py')}
        runtime = dict(deepcopy(original_runtime), root=str(self.root/'attempts'/scope['forecast_id']))
        runtime['limits']['author'].update(max_input_tokens=24000,max_output_tokens=49152)
        runtime['slots'] = {role:[str(Path(runtime['root'])/'roles'/(role+'-01'))]
                            for role in ('controller','author','review','forecast')}
        grant = dict(original_grant, **{key:runtime[key] for key in ('id','root','source_commit','ledger',
            'baseline','additional_cap_nano_usd','cutoff_utc','deadline_utc')},
            sources={key:bound['sha256'] for key,bound in sources.items()})
        grant_binding = engine.save(self.root/'validator-grant28.json',grant)
        study = {'cases':'public','new_live_grant':grant_binding,'new_episode_deadline':runtime['deadline_utc']}
        study_binding = engine.save(self.root/'validator-study28.json',study)
        runtime['forecast_study'] = study_binding
        runtime_binding = engine.save(self.root/'validator-runtime28.json',runtime)
        value = dict(self.value, prior=old, scope=scope_binding, runtime=runtime_binding,
            grant=grant_binding, study=study_binding, sources=sources, source_commit=runtime['source_commit'])
        record = transfer.derive(self.t.spec_binding,scope_binding=scope_binding,runtime_binding=runtime_binding,
                                  fixed_context=flow.native_config(value)['fixed_context'])
        value['candidate_transfer'] = engine.save(self.root/'validator-transfer28.json',record)
        binding = engine.save(self.root/'validator-prepared28.json',value)
        review = {'verdict':'PASS_AUTHOR_FOLLOWTHROUGH_STAGE','blocking_findings':[],
            'reviewer':'independent-synthetic-reviewer','prepared':binding,'reviewed_sources':sources}
        with ExitStack() as stack:
            for name,result in (('authority',scope),('prior',old),('source_bindings',sources)):
                stack.enter_context(mock.patch.object(flow,name,return_value=result))
            stack.enter_context(mock.patch.object(flow,'ROOT',self.root))
            stack.enter_context(mock.patch.object(flow,'SCOPE',scope_path))
            stack.enter_context(mock.patch.object(flow,'preflight_runtime',side_effect=engine.read))
            for module,name in ((flow,'verify_sources'),(flow,'accounting'),(fresh,'validate')):
                stack.enter_context(mock.patch.object(module,name))
            rb = engine.save(self.root/'validator-review28.json',review)
            self.assertEqual(flow.validate_prepared(binding,rb),(value,runtime))
            bad_review = engine.save(self.root/'validator-root-review28.json',dict(review,reviewer='Root'))
            with self.assertRaises(ValueError):flow.validate_prepared(binding,bad_review)
            record['proposal']['fixed_context']['resource_policy_sha256'] = 'b'*64
            bad_value = dict(value,candidate_transfer=engine.save(self.root/'validator-bad-transfer28.json',record))
            bad_binding = engine.save(self.root/'validator-bad-prepared28.json',bad_value)
            bad_review = engine.save(self.root/'validator-bad-review28.json',dict(review,prepared=bad_binding))
            with self.assertRaises(ValueError):flow.validate_prepared(bad_binding,bad_review)
        self.assertFalse(Path(runtime['root']).exists())
        self.assert_old_unchanged()


class Forecast28EntryGuardTests(unittest.TestCase):
    def setUp(self):
        self.g = grant_fixture.Forecast27GrantTests()
        self.g.setUp(); self.addCleanup(self.g.doCleanups)
        self.root = self.g.root

    def test_author_stage_denied_before_prior_preparation_or_provider(self):
        scope = {'author_id':fresh.AUTHOR24_IDS[0], 'forecast_id':'edgar-research-20261016-28'}
        with mock.patch.object(flow,'authority',return_value=scope), mock.patch.object(flow,'prior') as prior:
            with self.assertRaisesRegex(ValueError,'forecast-only'):flow.prepare('author')
            prior.assert_not_called()

    def test_actual_scope_requires_exact28_child_window_allocation_and_old_chain(self):
        body = deepcopy(self.g.body)
        for name,verdict in (('FORECAST27_CLOSURE',
                'VERIFIED_FORECAST27_CONTEXT_LIMIT_FAILURE_SOURCE_TRANSFER_AND_AUTOCLOSURE'),
                ('FORECAST28_HEADROOM_REVIEW','PASS_FORECAST28_HEADROOM_OFFLINE_ONLY')):
            bound = engine.save(self.root/(name+'-entry.json'),{'verdict':verdict,
                'reviewer':'independent-synthetic-reviewer','blocking_findings':[]})
            patcher = mock.patch.object(fresh,name,bound); patcher.start(); self.addCleanup(patcher.stop)
        child = {'human_authorization':fresh.FORECAST28_AUTHORIZATION,'forecast_id':fresh.FORECAST28_ID,
            'closed_forecast_review':fresh.FORECAST27_CLOSURE,'headroom_review':fresh.FORECAST28_HEADROOM_REVIEW,
            'allocation':{'opening':{'max_rowid':5603,'request_count':5603,
                'charged_nano_usd':164293917000,'rows_sha256':'a'*64},'max_new_nano_usd':2000000000,
                'author_id':fresh.AUTHOR24_IDS[0],'forecast_id':fresh.FORECAST28_ID},
            'window':{'issued_utc':'2099-01-01T00:00:00Z','cutoff_utc':'2099-01-01T01:29:00Z',
                      'deadline_utc':'2099-01-01T01:30:00Z'}}
        body['forecast_headroom_authority'] = child
        entry = self.g.old.entry_fixture(); entry.body = body
        entry.scope.update(forecast_id=fresh.FORECAST28_ID,
            continuation_human_approval=fresh.FORECAST28_AUTHORIZATION,window=deepcopy(child['window']),
            forecast_headroom_authority=deepcopy(child),candidate_transfer_authority=deepcopy(body['candidate_transfer_authority']),
            allocation=deepcopy(child['allocation']),opening_rows=5603,opening_rows_sha256='a'*64,
            continuation_cumulative_cap_nano_usd=fresh.pilot_cap(body))
        self.assertEqual(entry.authority(),entry.scope)
        for change in ({'forecast_id':fresh.FORECAST27_ID},{'author_id':fresh.AUTHOR22_IDS[0]},
                {'window':body['window']},{'continuation_human_approval':fresh.FORECAST27_AUTHORIZATION},
                {'forecast_headroom_authority':dict(child,forecast_id=fresh.FORECAST27_ID)},
                {'candidate_transfer_authority':None},{'allocation':body['forecast_recovery']['allocation']}):
            with self.subTest(change=change),self.assertRaises(ValueError):entry.authority(change)

    def test_forecaster_exception_only28_and_only_exact_reviewed_hash(self):
        repo = self.root/'source-binding28'; actual = Path(flow.__file__).resolve().parents[1]
        names = ['tools/edgar_forecast_openai.py','tools/earnings_open_author_followthrough.py',
            'tools/earnings_open_fresh_grant.py','tools/earnings_native_failure.py',
            'tools/earnings_candidate_transfer.py','tools/protected.py','configs/scope.json','configs/context.json']
        for name in names:
            target = repo/name; target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((actual/name).read_bytes() if (actual/name).is_file() else b'inert-protected')
        old = {'sources':{names[0]:dict(engine.pin(repo/names[0]),sha256='0'*64),
                          names[5]:engine.pin(repo/names[5])}}
        scope = {'author_id':fresh.AUTHOR24_IDS[0], 'forecast_id':'edgar-research-20261016-28'}
        with mock.patch.object(flow.e,'REPO',repo), mock.patch.object(flow,'__file__',str(repo/names[1])),\
                mock.patch.object(flow,'SCOPE',repo/names[6]), mock.patch.object(flow,'CONTEXT',repo/names[7]):
            pins = flow.source_bindings(old,scope=scope)
            self.assertEqual(pins[names[0]]['sha256'], '8bf7e32e7d3d4e73530b6458222a1ceb48add4ea3a18521aa7252282abaf0777')
            self.assertIn('tools/earnings_native_failure.py', pins)
            self.assertIn('tools/earnings_candidate_transfer.py', pins)
            for identifier in (fresh.FORECAST26_ID,fresh.FORECAST27_ID,fresh.AUTHOR24_IDS[1]):
                with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                    flow.source_bindings(old,scope=dict(scope,forecast_id=identifier))
            for name in (names[0],names[5]):
                target = repo/name; before = target.read_bytes(); target.write_bytes(before+b'\n# drift')
                with self.subTest(name=name), self.assertRaises(ValueError):flow.source_bindings(old,scope=scope)
                target.write_bytes(before)

    def test_original80_counts_closed27_failed_directories_and_never_refunds(self):
        scope = {'author_id':fresh.AUTHOR24_IDS[0], 'forecast_id':'edgar-research-20261016-28',
                 'requires_cold_probe':True}
        roots = [(fresh.AUTHOR24_IDS[0],'code',3),(fresh.AUTHOR24_IDS[0],'review-code',2),
            (fresh.AUTHOR24_IDS[0],'cold-probe-code',1),(fresh.AUTHOR24_IDS[1],'code',4),
            (fresh.FORECAST26_ID,'code',5),(fresh.FORECAST27_ID,'code',20),
            ('edgar-research-20261016-28','code',2),('edgar-research-20261015-12','code',1)]
        for identifier,name,count in roots:
            root = self.root/'attempts'/identifier/name; root.mkdir(parents=True,exist_ok=True)
            for number in range(count):(root/f'call-{number:032x}').mkdir()
        with mock.patch.object(flow,'ROOT',self.root), mock.patch.object(flow,'authority',return_value=scope):
            self.assertEqual(flow.containers_remaining(), 42)
            old = self.root/'attempts'/fresh.FORECAST27_ID/'code'
            for number in range(20,62):(old/f'call-{number:032x}').mkdir()
            with self.assertRaisesRegex(ValueError,'shared80'):flow.containers_remaining()


if __name__ == '__main__':
    unittest.main()
