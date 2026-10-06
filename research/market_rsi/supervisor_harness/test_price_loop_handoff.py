"""Native synthetic handoffs only: no Train read, real Controller or fitting."""
from copy import deepcopy
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

from supervisor_harness import price_loop_handoff as h
from supervisor_harness import feedback_loop_runtime as r
from supervisor_harness import test_coevo_pilot_configuration as fixtures
from supervisor_harness import test_continuous_discovery_batch as batch_fixtures
from supervisor_harness.test_coevo_pilot_transaction import Clock
from supervisor_harness.test_account_controller_feedback_consumer import PARENT, INCUMBENT
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
from data_scientist_harness import test_micro_evolution as micro


class HandoffTests(TestCase):
    def setUp(self):
        self.f = fixtures.ConfigurationTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.root, self.repo = self.f.root, self.f.f.repo
        self.f.ledger['authorization_sha256'] = self.f.authorization_binding['sha256']
        self.f.write('ledger', self.f.ledger)
        self.runtime = r.PilotRuntime(self.root, self.repo, self.f.authorization_binding, self.f.configuration_binding)
        self.batch_class = ContinuousDiscoveryBatch
        for mock in (patch.object(r, 'datetime', Clock), patch.object(h.t, 'ROOT', self.root),
                     patch.object(h.t.c, '_transport', self.f.transport),
                     patch.object(h.b, 'ContinuousDiscoveryBatch', side_effect=self.batch),
                     patch.object(h.w.subprocess, 'check_output', return_value='fixture-commit\n')):
            mock.start(); self.addCleanup(mock.stop)
        response = self.runtime.controller({'outputs': {'input': {
            'input': self.f.input_binding, 'authorization': self.f.authorization_binding,
            'configuration': self.f.configuration_binding, 'review': self.f.review_binding}}})
        self.response = response['decision']
        self.runner = self.repo / ('research/market_rsi/' + h.MODULE.replace('.', '/') + '.py')
        self.runner.parent.mkdir(parents=True, exist_ok=True)
        self.runner.write_text('# inert runner fixture\n')
        self.candidate = self.runner.with_name('fixture_price_candidate.py')
        self.candidate.write_text("raise AssertionError('candidate must never be imported by compiler')\n")
        self.plan = self.f.write('price-plan', {'task_id': h.TASK, 'horizon_choice': {'seconds': 300}})
        self.reference = self.f.write('ordinary-reference', {'task_id': h.TASK, 'complete': True, 'model_fits': 4})
        self.memory = self.f.write('price-memory', {'synthetic': True, 'last_result': 'valid negative'})
        identity = micro.config()
        identity['fixed_context'].update(authority_sha256=self.runtime.authority['sha256'],
            resource_policy_sha256=self.runtime.configuration['sha256'], evaluation_sha256=self.plan['sha256'])
        archive = batch_fixtures.ContinuousDiscoveryBatchTests().archived_parent()
        archive.update(candidate_sha256=PARENT, research_credit=2, research_outcome='refute', route_action='branch')
        self.spec = {'native_name': 'price-native-fixture', 'attempt_id': 'price-attempt-fixture',
            'candidate_binding': r.pin(self.candidate), 'source_commit': 'fixture-commit',
            'files': {str(path.relative_to(self.repo)): h.w.sha(path) for path in (self.runner, self.candidate)},
            'python_binding': r.pin(self.f.f.python), 'memory_binding': self.memory,
            'plan_binding': self.plan, 'ordinary_reference_binding': self.reference,
            'initial_incumbent': {'candidate_id': 'B0-NoPriceChange', 'candidate_sha256': INCUMBENT,
                'scorecard_sha256': 'b' * 64, 'review_sha256': 'c' * 64},
            'archived_parents': [archive], 'identity_configuration': identity,
            'method_family': 'synthetic-different-method', 'max_wall_seconds': 10}

    def batch(self, path):
        return self.batch_class(path, allow_temporary=True, test_clock=Clock.now, allow_test_clock=True)

    def prepare(self):
        return h.prepare(self.runtime, self.response, self.spec)

    def review(self, prepared, **changes):
        core = h.t.c._read(prepared['operation_core'])
        return self.f.write('price-execution-review', {'passed': True,
            'authorization_sha256': self.runtime.authority['sha256'],
            'request_sha256': prepared['request']['sha256'],
            'execution_source_sha256': h.w.sha(r.__file__),
            'operation_core_sha256': h.operation_commitment(core), **changes})

    def no_native(self):
        self.assertFalse((self.root / self.spec['native_name']).exists())
        self.assertEqual(h.t._file(self.root / 'ledger.json')['attempts'], [])

    def test_valid_revert_parent_distinct_from_incumbent_without_claim_or_import(self):
        before = h.t._file(self.root / 'ledger.json')
        with patch.object(h.w.subprocess, 'Popen') as launch:
            prepared = self.prepare()
            finalized = h.finalize(self.runtime, prepared, self.review(prepared))
            self.assertFalse(launch.called)
        state = self.batch(self.root / prepared['native_name']).snapshot()
        self.assertEqual(state['incumbent']['candidate_sha256'], INCUMBENT)
        self.assertEqual(state['initial_archived_parents'][0]['candidate_sha256'], PARENT)
        self.assertEqual(state['branches'], [])
        self.assertEqual(state['attempts_claimed'], 0)
        self.assertEqual(h.t._file(self.root / 'ledger.json'), before)
        selection = h.t.c._read(prepared['selection'])
        self.assertEqual(selection['research_parent_sha256'], PARENT)
        self.assertEqual(selection['controller_decision_sha256'], h.t.c._digest(self.response))
        self.assertEqual(selection['allocation'], 'exploration')
        self.assertFalse(selection['resource_hint']['authority_granted'])
        request = h.t.c._read(prepared['request'])
        operation = h.t.c._read(finalized['artifacts'][0])
        self.assertEqual(request['spec_sha256'], h.operation_commitment(operation))
        self.assertEqual(operation['review'], finalized['review'])
        self.assertEqual(request['max_fits'], 4)
        self.assertEqual(self.f.calls, 1)  # Only synthetic original fixture transport.

    def test_existing_preparation_and_finalization_never_overwrite(self):
        prepared = self.prepare()
        with self.assertRaises(FileExistsError): self.prepare()
        review = self.review(prepared)
        first = h.finalize(self.runtime, prepared, review)
        with self.assertRaises(FileExistsError): h.finalize(self.runtime, prepared, review)
        self.assertEqual(h.t.c._read(first['artifacts'][0])['review'], review)

    def test_wrong_parent_comparator_or_absent_original_fails_before_native(self):
        for field in ('actual_parent_sha256', 'comparison_incumbent_sha256'):
            response = deepcopy(self.response); response['candidate'][field] = 'f' * 64
            with self.subTest(field=field), self.assertRaises(ValueError):
                h.prepare(self.runtime, response, self.spec)
            self.no_native()
        ledger = h.t._file(self.root / 'ledger.json'); ledger['controller_decisions'] = []
        self.f.write('ledger', ledger)
        with self.assertRaisesRegex(ValueError, 'completed original'): self.prepare()
        self.no_native()

    def test_ineligible_archive_or_incumbent_substitution_fails_before_native(self):
        original = deepcopy(self.spec)
        for key, value in (('research_credit', 0), ('route_action', 'stop'), ('authority_granted', True)):
            self.spec = deepcopy(original); self.spec['archived_parents'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.prepare()
            self.no_native()
        self.spec = deepcopy(original); self.spec['initial_incumbent']['candidate_sha256'] = PARENT
        with self.assertRaisesRegex(ValueError, 'incumbent drift'): self.prepare()
        self.no_native()

    def test_credit_one_archive_cannot_reset_followup_allowance(self):
        self.spec['archived_parents'][0].update(research_credit=1, research_outcome='inconclusive',
            route_action='bounded_followup')
        with self.assertRaisesRegex(ValueError, 'credit-1'): self.prepare()
        self.no_native()

    def test_duplicate_archive_and_symlink_root_rejected_before_native(self):
        self.spec['archived_parents'].append(deepcopy(self.spec['archived_parents'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate archived'): self.prepare()
        self.no_native()
        self.spec['archived_parents'].pop()
        link = self.root / self.spec['native_name']; link.symlink_to(self.repo, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'canonical'): self.prepare()
        self.assertEqual(h.t._file(self.root / 'ledger.json')['attempts'], [])

    def test_deadline_closed_cap_uncertainty_and_reused_attempt_before_mutation(self):
        original = h.t._file(self.root / 'ledger.json')
        for update in ({'status': 'closed'}, {'attempts': [{'attempt_id': 'other', 'status': 'uncertain', 'fits_reserved': 4}]},
                       {'attempts': [{'attempt_id': str(i), 'status': 'succeeded', 'fits_reserved': 4} for i in range(3)]}):
            ledger = {**deepcopy(original), **update}; self.f.write('ledger', ledger)
            with self.subTest(update=update), self.assertRaises(RuntimeError): self.prepare()
            self.assertFalse((self.root / self.spec['native_name']).exists())
        self.f.write('ledger', original)
        with patch.object(r.datetime, 'now', return_value=h.t.c._time(self.runtime.fixed_grant['deadline_utc'])):
            with self.assertRaises(RuntimeError): self.prepare()
        self.no_native()
        ledger = deepcopy(original)
        ledger['attempts'] = [{'attempt_id': self.spec['attempt_id'], 'status': 'succeeded', 'fits_reserved': 4}]
        self.f.write('ledger', ledger)
        with self.assertRaisesRegex(ValueError, 'reused'): self.prepare()

    def test_source_candidate_runtime_memory_and_plan_drift_before_native(self):
        for role in ('candidate_binding', 'python_binding', 'memory_binding', 'plan_binding', 'ordinary_reference_binding'):
            spec = deepcopy(self.spec); spec[role]['sha256'] = 'e' * 64
            with self.subTest(role=role), self.assertRaises(ValueError): h.prepare(self.runtime, self.response, spec)
            self.no_native()
        spec = deepcopy(self.spec); spec['source_commit'] = 'different'
        with self.assertRaisesRegex(ValueError, 'source commit'): h.prepare(self.runtime, self.response, spec)
        spec = deepcopy(self.spec); spec['files'].pop(str(self.candidate.relative_to(self.repo)))
        with self.assertRaisesRegex(ValueError, 'candidate missing'): h.prepare(self.runtime, self.response, spec)
        self.no_native()

    def test_frozen_task_and_fixed_authority_resource_evaluation_identity(self):
        for key in ('authority_sha256', 'resource_policy_sha256', 'evaluation_sha256'):
            spec = deepcopy(self.spec); spec['identity_configuration']['fixed_context'][key] = 'f' * 64
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'fixed identity'):
                h.prepare(self.runtime, self.response, spec)
            self.no_native()
        spec = deepcopy(self.spec); spec['plan_binding'] = self.f.write('different-plan',
            {'task_id': h.TASK, 'horizon_choice': {'seconds': 60}})
        with self.assertRaisesRegex(ValueError, 'frozen price'): h.prepare(self.runtime, self.response, spec)
        self.no_native()

    def test_duration_root_and_unknown_fields_rejected(self):
        for change in ({'max_wall_seconds': True}, {'max_wall_seconds': 901}, {'native_name': '../escape'},
                       {'native_name': 'a/b'}, {'unknown': 'not admitted'}):
            spec = {**self.spec, **change}
            with self.subTest(change=change), self.assertRaises(ValueError): h.prepare(self.runtime, self.response, spec)
            self.no_native()
        self.runtime.fixed_grant['limits']['per_attempt_seconds'] = 1
        with self.assertRaises(ValueError): self.prepare()

    def test_review_failed_wrong_hash_or_bool_never_creates_operation(self):
        prepared = self.prepare()
        for change in ({'passed': False}, {'passed': 1}, {'authorization_sha256': 'f' * 64},
                       {'request_sha256': 'f' * 64}, {'execution_source_sha256': 'f' * 64},
                       {'operation_core_sha256': 'f' * 64}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'independent'):
                h.finalize(self.runtime, prepared, self.review(prepared, **change))
            self.assertFalse((self.root / prepared['native_name'] / (self.spec['attempt_id'] + '.price_operation.json')).exists())

    def test_prepared_source_or_native_state_drift_blocks_finalize(self):
        prepared = self.prepare(); review = self.review(prepared)
        altered = deepcopy(prepared); altered['request']['path'] = str(self.root / 'elsewhere.json')
        with self.assertRaisesRegex(ValueError, 'manifest'): h.finalize(self.runtime, altered, review)
        self.candidate.write_text('# changed candidate\n')
        with self.assertRaisesRegex(ValueError, 'bound file'): h.finalize(self.runtime, prepared, review)

    def test_pool_activated_before_finalize_is_rejected(self):
        prepared = self.prepare(); review = self.review(prepared)
        batch = self.batch(self.root / prepared['native_name'])
        selection = h.t.c._read(prepared['selection'])
        state = batch.select_controller_pool([selection])
        self.assertEqual(state['branches'][0]['research_parent_sha256'], PARENT)
        self.assertEqual(state['branches'][0]['comparison_incumbent_sha256'], INCUMBENT)
        with self.assertRaisesRegex(ValueError, 'native state changed'):
            h.finalize(self.runtime, prepared, review)


if __name__ == '__main__': main()
