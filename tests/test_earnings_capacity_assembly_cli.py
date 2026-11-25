"""Real CLI -> actual roles -> measured selection -> feedback -> cold replay.

Financial data and raw HTTPS replies are explicitly invented. No dispatcher,
engine, role-success, scorer result or Native selection is supplied by a mock
in the full trace. Compatibility-only dispatch mocks are separately labelled.
"""
from contextlib import contextmanager, ExitStack, redirect_stdout
from copy import deepcopy
from hashlib import sha256
import io
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import earnings_capacity_assembly as assembly
import earnings_capacity_runtime as runtime
import earnings_capacity_task as task_module
import earnings_clock as clock
import earnings_completed_replay as closure
import earnings_controller as controller
import earnings_entry as entry
import earnings_feedback_loop as flow
from earnings_capacity_adapter import author_payload
from earnings_research_state import ResearchState
from market_rsi import digest
from supervisor_harness import continuous_discovery_batch as native
from supervisor_harness import capacity_feedback_engine as engine
from test_earnings_capacity_assembly import AssemblyFixture


PRIVATE_FAILURE = 'OWNED_FIXTURE_PRIVATE_CHILD_FAILURE_NOT_FOR_FEEDBACK'


class ActualRoleReplies:
    """Invent only original provider envelopes, conditional on actual inputs."""
    def __init__(self, fixture, *, axes=('H', 'R')):
        self.fixture, self.axes = fixture, list(axes)
        self.controller_inputs, self.controller_payloads = [], []
        self.decisions, self.author_inputs, self.authored = [], [], []

    def message(self, value):
        return self.fixture.raw.response([{'type': 'message', 'role': 'assistant', 'status': 'completed',
            'content': [{'type': 'output_text', 'text': json.dumps(value)}]}])

    def choose(self, payload):
        if payload['text']['format']['name'] != 'earnings_capacity_decision_v1':
            raise AssertionError('Actual Controller request expected')
        safe = json.loads(payload['input'][0]['content'])
        axis = self.axes[len(self.controller_inputs)]
        component = 'tool_interface' if axis == 'H' else 'research_policy' if axis == 'R' else 'none'
        metric = 'tool_return_characters' if axis == 'H' else 'input_tokens'
        criterion = (f'earnings-shadow-v1|{component}|{metric}|lower|1|'
                     'score_nonregression|matched_trial_only')
        decision = {'schema': 'earnings_capacity_decision_v1', 'axis': axis,
            'component': component, 'parent_pair_sha256': safe['parent_pair_sha256'],
            'feedback_sha256': safe['feedback_sha256'],
            'hypothesis': 'Invented provider reply exercises the declared one-field pathway',
            'expected_effect': 'Continue without a new mutation' if axis == 'continue' else criterion}
        self.controller_inputs.append(deepcopy(safe))
        self.controller_payloads.append(deepcopy(payload))
        self.decisions.append(deepcopy(decision))
        return self.message(decision)

    def author(self, payload):
        if payload['text']['format']['name'] != 'earnings_capacity_author_v1':
            raise AssertionError('Actual Author request expected')
        safe = json.loads(payload['input'][0]['content'])
        decision = safe['decision']
        if decision != self.decisions[-1] or safe['decision_sha256'] != digest(decision):
            raise AssertionError('Author did not receive the unchanged actual Controller decision')
        profile = deepcopy(safe['before_profile'])
        if decision['axis'] == 'H':
            field, value = 'read_chunk_limit', 1000
        else:
            field, value = 'research_instructions', 'Check signs with calculate and cite the provided filing.'
        profile[field] = value
        authored = {'decision_sha256': safe['decision_sha256'],
            'source_text': 'PROFILE = ' + repr(profile) + '\n',
            'test_text': 'CASES = ' + repr([{'field': field, 'expected': value}]) + '\n'}
        self.author_inputs.append(deepcopy(safe))
        self.authored.append(deepcopy(authored))
        return self.message(authored)

    def sequence(self):
        result = []
        for axis in self.axes:
            result.append(self.choose)
            if axis != 'continue': result.append(self.author)
            forecasts = 1 if axis == 'continue' else 3
            for _ in range(forecasts):
                result.extend([self.fixture.raw.research(), self.fixture.raw.final()])
        return result


class CapacityAssemblyCLITests(unittest.TestCase):
    def fixture(self, *, rounds=2):
        return AssemblyFixture(self, rounds=rounds)

    def arguments(self, fixture, *extra):
        return ['--envelope', fixture.episode_binding['path'], '--assembly', fixture.assembly_binding['path'], *extra]

    def admission(self, fixture):
        def admit(envelope):
            if (envelope != fixture.envelope or envelope['study'] != fixture.raw.study_binding
                    or envelope['evaluation_kernel'] != fixture.raw.kernel):
                raise ValueError('Only the exact invented financial fixture is admitted')
            engine.read(envelope['initial_state'])
            return fixture.raw.company, ResearchState(fixture.raw.company, envelope['id'])
        return admit

    def owned_tree(self, fixture):
        result = fixture.retained_tree()
        for path in fixture.raw.data.root.rglob('*'):
            if path.is_symlink(): result[str(path)] = ('link', str(path.readlink()))
            elif path.is_file(): result[str(path)] = ('file', path.read_bytes())
        return result

    @contextmanager
    def actual_run(self, fixture, replies):
        with fixture.exchange(replies), \
                patch.object(entry, 'preflight_capacity_episode', side_effect=self.admission(fixture)) as admission:
            yield admission

    def main_result(self, arguments, *, client_factory=None):
        output = io.StringIO()
        with redirect_stdout(output):
            flow.main(arguments, client_factory=client_factory)
        return json.loads(output.getvalue())

    def done(self, fixture, index, stage):
        return engine.driver._read_pair(fixture.root / 'loop' / f'round-{index:04d}-{stage}.done.json')['output']

    def snapshot(self, fixture):
        return engine.read(engine.pin(fixture.paths['batch_root'] / 'batch.json'))

    def terminal(self, fixture):
        path = Path(fixture.runtime['ledger']).parent / '.capacity-runtime-claims' / (
            sha256(fixture.id.encode()).hexdigest() + '.result.json')
        return engine.read(engine.pin(path))

    def assert_cold_without_callbacks_or_writes(self, fixture, expected):
        before = self.owned_tree(fixture)
        arguments = ['--envelope', fixture.episode_binding['path'], '--completed-replay',
                     str(fixture.root / 'completed-replay.json')]
        with ExitStack() as stack:
            checks = [
                (assembly, '_native'), (assembly, 'open_capacity_runtime'),
                (entry, 'preflight_capacity_episode'), (clock, 'capture_or_load'),
                (sqlite3, 'connect'), (native.ContinuousDiscoveryBatch, '__init__'),
                (native.ContinuousDiscoveryBatch, 'snapshot'),
                (native.ContinuousDiscoveryBatch, '_recover_pending_journal'),
                (engine.driver.c, 'save'), (entry, 'durable_json')]
            spies = [stack.enter_context(patch.object(target, name,
                side_effect=AssertionError('Cold replay must not call ' + name))) for target, name in checks]
            actual = self.main_result(arguments)
        self.assertEqual(actual, expected)
        for spy in spies: spy.assert_not_called()
        self.assertEqual(self.owned_tree(fixture), before)
        self.assertTrue(all(client.timeout == fixture.raw.runtime['request_timeout_seconds']
                            for client in fixture.clients))

    def test_actual_cli_two_round_H_adoption_R_rejection_shared_owner_feedback_and_cold_closure(self):
        fixture = self.fixture()
        replies = ActualRoleReplies(fixture)
        created, closed = [], []
        original_init, original_close = runtime.NightBudget.__init__, runtime.NightBudget.close
        def initialize(budget, *args, **kwargs):
            created.append(budget)
            return original_init(budget, *args, **kwargs)
        def close(budget):
            closed.append(budget)
            return original_close(budget)
        with self.actual_run(fixture, replies.sequence()) as admission, \
                patch.object(runtime.NightBudget, '__init__', new=initialize), \
                patch.object(runtime.NightBudget, 'close', new=close), \
                patch.object(entry, 'NightBudget', side_effect=AssertionError('No forecast budget reopen')), \
                patch.object(controller, 'NightBudget', side_effect=AssertionError('No role budget reopen')):
            result = self.main_result(self.arguments(fixture), client_factory=fixture.client_factory)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['completed_rounds'], 2)
        self.assertEqual(len(created), 1)
        self.assertEqual(closed, created)
        self.assertGreaterEqual(admission.call_count, 2)
        self.assertEqual(len(fixture.raw.calls), 32)
        self.assertEqual(len(replies.controller_inputs), 2)
        self.assertEqual(len(replies.author_inputs), 2)
        self.assertEqual(fixture.factory_calls, 10)
        rows = fixture.ledger_rows()
        self.assertEqual(len(rows) - fixture.runtime['baseline']['request_count'], 16)
        self.assertTrue(all(row[4] == 'settled' and row[3] > 0 for row in rows))
        self.assertTrue(all(payload['model'] == fixture.raw.rate['api_model']
            and payload['reasoning'] == {'effort': fixture.raw.rate['effort']} for _, payload in fixture.raw.calls))
        self.assertTrue(all(connection.closed for connection in fixture.raw.connections))
        snapshot = self.snapshot(fixture)
        micro = snapshot['micro_evolution']
        self.assertEqual(len(snapshot['capacity_work']), 6)
        self.assertTrue(all(row['status'] == 'completed' for row in snapshot['capacity_work']))
        self.assertEqual([row['review']['decision'] for row in micro['history']], ['accept', 'reject'])
        self.assertEqual([row['review']['reason'] for row in micro['history']],
                         ['MATCHED_OPERATIONAL_BENEFIT', 'NO_MATCHED_BENEFIT'])
        self.assertEqual(micro['active_pair'], micro['history'][0]['proposal']['pair'])
        self.assertIsNone(micro['pending'])
        self.assertNotEqual(micro['active_pair'], micro['anchor_pair'])
        self.assertEqual(result['result']['pair_sha256'], digest(micro['active_pair']))
        for index, decision in enumerate(replies.decisions, 1):
            author_original = engine.read(engine.pin(Path(fixture.slots[index-1]['author']) / 'response.json'))
            self.assertEqual(author_payload(author_original), replies.authored[index-1])
            row = fixture.review['slots'][fixture.slots[index-1]['review']]
            target = fixture.paths['source_root'] / row[decision['axis']]
            self.assertEqual(target.read_bytes(), replies.authored[index-1]['source_text'].encode())
            source_review = engine.read(engine.pin(Path(fixture.slots[index-1]['review']) / 'response.json'))
            self.assertIsNone(source_review['review_receipt'])
            self.assertEqual(source_review['proposal']['problem_evidence_sha256'], decision['feedback_sha256'])
            self.assertEqual(source_review['proposal']['behavior_change'], decision['expected_effect'])
        first = self.done(fixture, 1, 'reconcile')
        second_prompt = replies.controller_inputs[1]
        self.assertEqual(second_prompt['feedback'], first['feedback'])
        self.assertEqual(second_prompt['feedback_sha256'], digest(first))
        self.assertEqual(second_prompt['parent_pair_sha256'], first['pair_sha256'])
        self.assertEqual(first['state'], self.done(fixture, 1, 'execute')['state'])
        diagnostics = second_prompt['feedback']['research_diagnostics']
        self.assertEqual(diagnostics['review']['verdict'], 'accept')
        self.assertEqual(diagnostics['review']['reason'], 'MATCHED_OPERATIONAL_BENEFIT')
        self.assertEqual(diagnostics['review']['metric'], 'tool_return_characters')
        self.assertLessEqual(diagnostics['review']['observed_delta'], -1)
        self.assertEqual(diagnostics['review']['score_delta'], 0)
        self.assertEqual(diagnostics['execution']['score_out_of_5'], 5)
        self.assertEqual(diagnostics['execution']['turns'], 2)
        for payload in replies.controller_payloads:
            self.assertIn('earnings-shadow-v1|', payload['instructions'])
            self.assertIn('no forced sequence', payload['instructions'])
        controller_count = engine.read(engine.pin(Path(fixture.slots[1]['controller']) / '01-request.json'))
        self.assertEqual(json.loads(controller_count['payload']['input'][0]['content']), second_prompt)
        for index, row in enumerate(fixture.plan_rows, 1):
            for arm in ('parent', 'candidate', 'downstream'):
                effective = engine.read(engine.pin(Path(row[arm]) / 'effective-capacity.json'))
                expected_state = fixture.initial if index == 1 else first['state']
                self.assertEqual(effective['initial_state']['sha256'], expected_state['sha256'])
                self.assertEqual(Path(effective['initial_state']['path']).read_bytes(),
                                 Path(expected_state['path']).read_bytes())
                if arm == 'downstream':
                    self.assertNotIn('shadow', effective)
                    self.assertEqual(effective['context']['tool_bounds']['read_chunk_limit'], 1000)
                    self.assertTrue(all(receipt['selected_pair_sha256'] == digest(micro['active_pair'])
                                        and not receipt['shadow'] for receipt in effective['context']['receipts']))
                elif arm == 'candidate': self.assertIn('shadow', effective)
        manifest = engine.read(engine.pin(fixture.root / 'loop' / 'manifest.json'))
        self.assertTrue(all(value['task']['preflight']['module'] == engine.pin(task_module.__file__)
                            for value in manifest['handler_identity'].values()))
        terminal = self.terminal(fixture)
        self.assertEqual(terminal['status'], 'COMPLETED_COMPONENT_CONTEXT')
        self.assertIsNone(terminal['error_type'])
        self.assertIs(terminal['retry_allowed'], False)
        self.assertIs(terminal['budget_summary']['blocked'], False)
        self.assertEqual(terminal['budget_summary']['unresolved_reserved_usd'], 0)
        retained = engine.read(engine.pin(fixture.root / 'completed-replay.json'))
        self.assertEqual(retained['outcome'], result)
        self.assertIs(retained['claims']['runtime_owner_verified'], True)
        self.assertEqual(retained['claims']['model_authorship'], False)
        self.assertEqual(retained['claims']['predictive_gain'], False)
        self.assertEqual(result['result']['claims'],
                         {'mode': 'offline_replay', 'learning': False, 'live_RH_authorship': False})
        self.assert_cold_without_callbacks_or_writes(fixture, result)

    def test_actual_preflight_only_uses_default_task_but_no_owner_native_factory_or_api(self):
        fixture = self.fixture()
        before = self.owned_tree(fixture)
        with fixture.scope(), \
                patch.object(entry, 'preflight_capacity_episode', side_effect=self.admission(fixture)) as admission, \
                patch.object(assembly, '_native', side_effect=AssertionError('No Native construction')) as construct, \
                patch.object(assembly, 'open_capacity_runtime', side_effect=AssertionError('No owner')) as owner:
            result = self.main_result(self.arguments(fixture, '--preflight-only'), client_factory=fixture.client_factory)
        self.assertEqual(result, {'status': 'OFFLINE_CAPACITY_ASSEMBLY_PREFLIGHT_PASS', 'new_provider_calls': 0})
        admission.assert_called_once_with(fixture.envelope)
        construct.assert_not_called()
        owner.assert_not_called()
        self.assertEqual(self.owned_tree(fixture), before)
        self.assertEqual(fixture.factory_calls, 0)
        self.assertEqual(fixture.raw.calls, [])

    def test_missing_capacity_assembly_or_transport_refuses_at_cli_before_admission_and_owners(self):
        for missing in ('assembly', 'factory'):
            fixture = self.fixture()
            arguments = (['--envelope', fixture.episode_binding['path']] if missing == 'assembly'
                         else self.arguments(fixture))
            factory = fixture.client_factory if missing == 'assembly' else None
            before = self.owned_tree(fixture)
            with fixture.scope(), \
                    patch.object(entry, 'preflight_capacity_episode', side_effect=AssertionError('No data admission')) as admission, \
                    patch.object(assembly, '_native', side_effect=AssertionError('No Native construction')) as construct, \
                    patch.object(assembly, 'open_capacity_runtime', side_effect=AssertionError('No owner')) as owner:
                with self.assertRaises(ValueError): self.main_result(arguments, client_factory=factory)
            for spy in (admission, construct, owner): spy.assert_not_called()
            self.assertEqual(self.owned_tree(fixture), before)
            self.assertEqual(fixture.factory_calls, 0)

    def test_compatibility_only_capacity_dispatch_forwards_explicit_arguments_and_rejects_legacy_factories(self):
        # Dispatcher-only test: the marker is not evidence of pipeline success.
        fixture = self.fixture()
        marker = {'scope': 'DISPATCH_ONLY_NOT_ENGINE_EXECUTION'}
        with patch.object(assembly, 'run_assembled_capacity', return_value=marker) as dispatch:
            self.assertEqual(flow.run(fixture.episode_binding, assembly_binding=fixture.assembly_binding,
                client_factory=fixture.client_factory, task=fixture.task), marker)
        dispatch.assert_called_once_with(fixture.episode_binding, fixture.assembly_binding,
                                         client_factory=fixture.client_factory, task=fixture.task)
        for kwargs in ({}, {'assembly_binding': fixture.assembly_binding, 'controller_factory': fixture.client_factory},
                       {'assembly_binding': fixture.assembly_binding, 'forecast_factory': fixture.client_factory}):
            with self.subTest(kwargs=sorted(kwargs)), self.assertRaises(ValueError):
                flow.run(fixture.episode_binding, **kwargs)

    def test_compatibility_only_legacy_route_keeps_legacy_driver_and_factory_arguments(self):
        # Deliberately mocked legacy dependencies prove dispatch compatibility,
        # not source/data admission, a role trajectory or completed research.
        fixture = self.fixture(rounds=1)
        legacy = {'schema': 'earnings_feedback_episode_legacy_fixture', 'root': str(fixture.home / 'legacy'),
                  'source_commit': fixture.envelope['source_commit'], 'baseline_config': {}}
        binding = fixture.save('legacy-dispatch-only', legacy)
        controller_factory, forecast_factory = object(), object()
        marker = {'scope': 'LEGACY_DISPATCH_ONLY'}
        handlers = {name: object() for name in engine.driver.STAGES}
        with patch.object(flow.policy, 'validate_envelope', return_value=None) as validate, \
                patch.object(flow.clock, 'capture_or_load', return_value=({}, {})) as capture, \
                patch.object(flow, 'baseline_seed', return_value={}) as seed, \
                patch.object(flow, 'handlers', return_value=handlers) as adapters, \
                patch.object(flow.driver, 'run', return_value=marker) as driver:
            self.assertEqual(flow.run(binding, controller_factory=controller_factory,
                                      forecast_factory=forecast_factory), marker)
        validate.assert_called_once_with(legacy)
        capture.assert_called_once_with(legacy['root'], legacy['baseline_config'])
        seed.assert_called_once_with(legacy['baseline_config'])
        adapters.assert_called_once_with(legacy, binding, controller_factory=controller_factory,
                                         forecast_factory=forecast_factory)
        self.assertEqual(driver.call_args.args, (legacy['root'], handlers))
        self.assertEqual(driver.call_args.kwargs['max_rounds'], 2)
        for kwargs in ({'assembly_binding': fixture.assembly_binding}, {'client_factory': fixture.client_factory},
                       {'task': fixture.task}):
            with self.subTest(kwargs=sorted(kwargs)), self.assertRaises(ValueError): flow.run(binding, **kwargs)

    def assert_warm_retry_closed(self, fixture):
        before, calls = self.owned_tree(fixture), len(fixture.raw.calls)
        factories = fixture.factory_calls
        with fixture.scope(), \
                patch.object(entry, 'preflight_capacity_episode', side_effect=AssertionError('Consumed ID cannot readmit')), \
                patch.object(assembly, 'open_capacity_runtime', side_effect=AssertionError('Consumed owner cannot reopen')):
            with self.assertRaises(ValueError):
                self.main_result(self.arguments(fixture), client_factory=fixture.client_factory)
        self.assertEqual(self.owned_tree(fixture), before)
        self.assertEqual(len(fixture.raw.calls), calls)
        self.assertEqual(fixture.factory_calls, factories)

    def test_actual_raw_child_failure_between_arms_preserves_parent_and_uncertainty_without_retry(self):
        fixture = self.fixture()
        replies = ActualRoleReplies(fixture)
        sequence = replies.sequence()
        sequence[4] = OSError(PRIVATE_FAILURE)  # H Controller/Author/parent two turns precede the child.
        with self.actual_run(fixture, sequence):
            with self.assertRaises(engine.driver.LoopHalted):
                self.main_result(self.arguments(fixture), client_factory=fixture.client_factory)
        snapshot = self.snapshot(fixture)
        self.assertEqual([row['status'] for row in snapshot['capacity_work']], ['completed', 'claimed'])
        self.assertEqual(snapshot['micro_evolution']['active_pair'], snapshot['micro_evolution']['anchor_pair'])
        self.assertIsNotNone(snapshot['micro_evolution']['pending'])
        self.assertEqual(snapshot['micro_evolution']['history'], [])
        self.assertEqual(len(replies.controller_inputs), 1)
        self.assertEqual(len(fixture.raw.calls), 10)
        failures = list((fixture.root / 'shadow').rglob('failed.json'))
        self.assertEqual(len(failures), 1)
        failure = engine.read(engine.pin(failures[0]))
        self.assertEqual(failure['status'], 'FAILED_NO_RETRY')
        self.assertIs(failure['retry_allowed'], False)
        self.assertEqual(set(failure['completed_outputs']), {'parent'})
        self.assertNotIn(PRIVATE_FAILURE, json.dumps(failure))
        self.assertTrue((fixture.root / 'loop' / 'round-0001-execute.failed.json').is_file())
        self.assertFalse((fixture.root / 'loop' / 'round-0001-execute.done.json').exists())
        self.assertFalse((fixture.root / 'completed-replay.json').exists())
        terminal = self.terminal(fixture)
        self.assertEqual(terminal['status'], 'FAILED_NO_RETRY')
        self.assertTrue(terminal['budget_summary']['blocked'])
        self.assertTrue(any(row[4] != 'settled' for row in fixture.ledger_rows()))
        self.assert_warm_retry_closed(fixture)

    def test_native_complete_ahead_of_driver_seal_stays_failed_and_cannot_cold_replay(self):
        fixture = self.fixture()
        replies = ActualRoleReplies(fixture)
        original = engine.driver._save_pair
        failed = []
        def publish(path, value):
            if Path(path).name == 'round-0001-execute.done.json':
                failed.append(deepcopy(value))
                raise OSError('Owned fixture completion publication interrupted')
            return original(path, value)
        with self.actual_run(fixture, replies.sequence()), patch.object(engine.driver, '_save_pair', new=publish):
            with self.assertRaises(engine.driver.LoopHalted):
                self.main_result(self.arguments(fixture), client_factory=fixture.client_factory)
        self.assertEqual(len(failed), 1)
        snapshot = self.snapshot(fixture)
        self.assertEqual(len(snapshot['capacity_work']), 3)
        self.assertTrue(all(row['status'] == 'completed' for row in snapshot['capacity_work']))
        self.assertEqual(snapshot['micro_evolution']['history'][0]['review']['decision'], 'accept')
        self.assertEqual(len(replies.controller_inputs), 1)
        self.assertEqual(len(fixture.raw.calls), 16)
        self.assertFalse((fixture.root / 'completed-replay.json').exists())
        self.assertFalse((fixture.root / 'loop' / 'round-0001-execute.done.json').exists())
        self.assertTrue((fixture.root / 'loop' / 'round-0001-execute.failed.json').exists())
        self.assertEqual(self.terminal(fixture)['status'], 'FAILED_NO_RETRY')
        before = self.owned_tree(fixture)
        with patch.object(sqlite3, 'connect', side_effect=AssertionError('No ledger reopen')), \
                patch.object(native.ContinuousDiscoveryBatch, '__init__', side_effect=AssertionError('No Native reconstruction')):
            with self.assertRaises(engine.driver.LoopHalted):
                engine.driver.replay_completed(fixture.root / 'loop',
                    manifest_binding=engine.pin(fixture.root / 'loop' / 'manifest.json'))
        self.assertEqual(self.owned_tree(fixture), before)
        self.assert_warm_retry_closed(fixture)

    def test_cli_default_data_admission_failure_does_not_initialize_native_or_owner(self):
        fixture = self.fixture()
        before = self.owned_tree(fixture)
        with fixture.scope(), \
                patch.object(entry, 'preflight_capacity_episode', side_effect=ValueError('Original admission stopped')) as admission, \
                patch.object(assembly, '_native', side_effect=AssertionError('No Native')) as construct, \
                patch.object(assembly, 'open_capacity_runtime', side_effect=AssertionError('No owner')) as owner:
            with self.assertRaisesRegex(ValueError, 'Original admission stopped'):
                self.main_result(self.arguments(fixture), client_factory=fixture.client_factory)
        admission.assert_called_once_with(fixture.envelope)
        construct.assert_not_called()
        owner.assert_not_called()
        self.assertEqual(self.owned_tree(fixture), before)
        self.assertEqual(fixture.factory_calls, 0)

    def test_completed_replay_cli_rejects_any_warm_transport_assembly_or_preflight(self):
        fixture = self.fixture()
        base = ['--envelope', fixture.episode_binding['path'], '--completed-replay',
                str(fixture.root / 'completed-replay.json')]
        for extra, factory in ((['--assembly', fixture.assembly_binding['path']], None),
                               (['--preflight-only'], None), ([], fixture.client_factory)):
            with self.subTest(extra=extra, factory=factory is not None), \
                    patch.object(closure, 'replay_completed', side_effect=AssertionError('No replay callback')) as replay:
                with self.assertRaisesRegex(ValueError, 'callback-free'):
                    self.main_result([*base, *extra], client_factory=factory)
                replay.assert_not_called()


if __name__ == '__main__':
    unittest.main()
