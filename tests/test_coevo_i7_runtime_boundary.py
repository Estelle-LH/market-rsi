"""I7 actual common entry; temporary native journal and zero-provider roles.

Missing enforcement is an ordinary failure, never an expectedFailure. These
tests do not manufacture an execution claim or mock a native busy snapshot.
"""
from pathlib import Path
import unittest

from supervisor_harness import capacity_feedback_engine as engine
import test_capacity_feedback_engine as fixture


class NativeRequestedTask(fixture.LocalTask):
    """A task can request empirical mode; common entry must guard its authority."""
    def preflight(self, envelope):
        if envelope['mode'] != 'native_empirical':
            raise ValueError('Wrong synthetic requested-mode fixture')
        engine.read(self.data)
        engine.read(self.expected)


class RuntimeBoundaryTests(fixture.CommonEngineTests):
    def setUp(self):
        super().setUp()
        # Legacy fixture's forecast flag shadows unittest.TestCase.fail.
        # This suite does not use its forecaster; retain real assertion errors.
        del self.fail

    def one_round(self, *, continue_only=False):
        self.setup_task()
        self.envelope['max_rounds'] = 1
        self.bound = engine.save(self.root / 'i7-envelope.json', self.envelope)
        self.axes = ['continue'] if continue_only else ['R']
        services = self.services()
        # The base fixture feedback-controller deliberately chooses R/H.
        services['controller'] = self.controller_role
        return services

    def capture_entry(self, services):
        try:
            return engine.run(self.bound, self.native.restore(), self.task,
                              services=services), None
        except (ValueError, engine.driver.LoopHalted) as exc:
            return None, exc

    def busy(self, snapshot):
        return bool(snapshot.get('active_attempt_ids') or any(
            row['stage'] == 'execution_claimed' for row in snapshot['branches']))

    def test_absent_shared_runtime_contract_refused_before_any_role(self):
        services = self.one_round(continue_only=True)
        self.task = NativeRequestedTask(self, 'sum', restore=True)
        self.envelope['mode'] = 'native_empirical'
        self.bound = engine.save(self.root / 'i7-native-request-envelope.json', self.envelope)
        outcome, error = self.capture_entry(services)
        summary = {key: outcome[key] for key in ('status', 'completed_rounds')} if outcome else None
        self.assertIsNotNone(error, 'REPLAN: actual common entry accepted native_empirical '
                             'without a shared clock/accounting contract: ' + repr(summary))
        cause = error.__cause__ or error
        self.assertIsInstance(cause, ValueError)
        self.assertRegex(str(cause), r'(?i)(runtime|clock|account|offline|contract)')
        self.assertEqual((self.packets, self.authored, self.reviewed, self.task.calls),
                         ([], [], [], []), 'refusal must precede all role work')

    def test_native_activation_refused_inside_actual_execute_service(self):
        services = self.one_round(continue_only=True)
        before, after = self.native.propose('R')
        receipt = self.native.review_receipt(before, after)
        observed = {}

        def execute(worker, slot):
            state = worker.capacity.batch.snapshot()
            observed['busy'] = self.busy(state)
            try:
                worker.capacity.review(receipt, expected_state_sha256=state['state_sha256'])
                observed['accepted'] = True
            except ValueError as exc:
                observed['refusal'] = str(exc)
            return worker.execute(slot)

        services['execute'] = execute
        self.capture_entry(services)
        self.assertEqual(len(self.task.calls), 1, 'actual local worker must execute')
        self.assertIn('refusal', observed, 'REPLAN: native activation accepted while '
                      'actual common execute service was running: ' + repr(observed))
        self.assertRegex(observed['refusal'], r'(?i)(idle|busy|active|execution)')
        self.assertEqual(self.native.batch.snapshot()['micro_evolution']['active_pair'],
                         engine.activation.pair(before))

    def test_native_rollback_refused_inside_actual_execute_service(self):
        services = self.one_round()
        observed = {}

        def execute(worker, slot):
            state = worker.capacity.batch.snapshot()
            observed['busy'] = self.busy(state)
            check = self.native.artifact({'passed': True,
                'from_pair': state['micro_evolution']['active_pair'],
                'to_pair': state['micro_evolution']['previous_pair'],
                'before_state_sha256': state['state_sha256']})
            receipt = self.native.artifact({'receipt': {
                'reviewer_id': 'independent-auditor', 'reason': 'I7 fixture rollback',
                'evidence_sha256': check['sha256']}, 'evidence': check})
            try:
                worker.capacity.rollback(receipt, expected_state_sha256=state['state_sha256'])
                observed['accepted'] = True
            except ValueError as exc:
                observed['refusal'] = str(exc)
            return worker.execute(slot)

        services['execute'] = execute
        self.capture_entry(services)
        self.assertEqual(len(self.task.calls), 1, 'actual local worker must execute')
        self.assertIn('refusal', observed, 'REPLAN: native rollback accepted while '
                      'actual common execute service was running: ' + repr(observed))
        self.assertRegex(observed['refusal'], r'(?i)(idle|busy|active|execution)')

    def uncertain_entry(self):
        services = self.one_round()

        def execute(worker, slot):
            worker.execute(slot)
            raise RuntimeError('I7 synthetic uncertain work; diagnosis required')

        services['execute'] = execute
        outcome, error = self.capture_entry(services)
        self.assertIsInstance(error, engine.driver.LoopHalted)
        self.assertIsNone(outcome)
        return services

    def test_uncertain_native_work_remains_claimed_until_diagnosis(self):
        self.uncertain_entry()
        state = self.native.batch.snapshot()
        self.assertTrue(self.busy(state), 'REPLAN: uncertain common worker left native '
                        'activation journal idle; active_attempt_ids=' +
                        repr(state.get('active_attempt_ids')) + ', branches=' +
                        repr(state['branches']))

    def test_uncertain_stage_claim_and_original_survive_without_retry(self):
        services = self.uncertain_entry()
        prefix = self.root / 'episode/loop/round-0001-execute'
        claim, failure = prefix.with_suffix('.claim.json'), prefix.with_suffix('.failed.json')
        original = Path(self.envelope['slots'][0]['forecast']) / 'result.json'
        hashes = [engine.pin(path)['sha256'] for path in (claim, failure, original)]
        _, error = self.capture_entry(services)
        self.assertIsInstance(error, engine.driver.LoopHalted)
        self.assertEqual(len(self.task.calls), 1)
        self.assertEqual([engine.pin(path)['sha256'] for path in (claim, failure, original)], hashes)
        self.assertFalse(prefix.with_suffix('.done.json').exists())

    def test_missing_execute_service_has_no_paid_fallback_or_role_work(self):
        services = self.one_round()
        services.pop('execute')
        before = self.native.batch.snapshot()['state_sha256']
        with self.assertRaisesRegex(ValueError, 'no paid fallback'):
            engine.run(self.bound, self.native.restore(), self.task, services=services)
        self.assertEqual((self.packets, self.authored, self.reviewed, self.task.calls),
                         ([], [], [], []))
        self.assertEqual(self.native.batch.snapshot()['state_sha256'], before)


for _name in dir(fixture.CommonEngineTests):
    if _name.startswith('test_'):
        setattr(RuntimeBoundaryTests, _name, None)


if __name__ == '__main__':
    unittest.main()
