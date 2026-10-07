"""Measured same-input subprocesses/native journal; account roles synthetic."""
from copy import deepcopy
from unittest import TestCase, main
from unittest.mock import patch

from supervisor_harness import price_capacity_trial as trial
from supervisor_harness import test_price_capacity_review as fixtures


class TrialTests(TestCase):
    def setUp(self):
        cases = {name: {'history': [{'decision': 'REVERT', 'question': name}]} for name in trial.CASES}
        original = fixtures.fixtures.CapacityAuthorTests.start
        with patch.object(fixtures.fixtures.CapacityAuthorTests, 'start',
                new=lambda instance, **kwargs: original(instance, axis='harness', replay_cases=cases)):
            self.f = fixtures.CapacityReviewTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.runtime = self.f.f.runtime
        self.scope = self.f.review()
        from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
        self.batch = ContinuousDiscoveryBatch(self.runtime.root / 'capacity-native', allow_temporary=True,
            test_clock=lambda: trial.t.datetime.now(trial.t.timezone.utc), allow_test_clock=True)
        grant = self.runtime.fixed_grant
        self.batch.initialize(batch_id=grant['batch_id'], start_utc=grant['start_utc'], deadline_utc=grant['deadline_utc'],
            max_attempts=2, active_pool_capacity=2, learning_checkpoint_version=1,
            initial_incumbent={'candidate_id': 'synthetic-market', 'candidate_sha256': self.f.f.before['C'],
                'scorecard_sha256': 'a' * 64, 'review_sha256': '0' * 64})
        config = self.f.f.packet['action_context']['identity_configuration']
        self.batch.record_micro_evolution('initialize', config, expected_state_sha256=self.batch.snapshot()['state_sha256'])
        self.adapter = trial.cs.activation.CapacityActivation(self.batch, source_root=self.runtime.repo,
            registry_root=self.runtime.root / 'capacity-versions', baseline=self.f.f.before, entrypoints=self.f.f.entrypoints)

    def prepare(self):
        return trial.prepare(self.runtime, self.f.material, self.scope, self.f.reviewer, self.adapter)

    def test_actual_matched_outputs_and_replay_not_activation(self):
        prepared = self.prepare(); measured = trial.execute(self.runtime, prepared, self.adapter)
        evidence = trial.t.c._read(measured['measurement'])
        self.assertTrue(all(evidence['checks'].values())); self.assertEqual(len(evidence['outputs']), 11)
        self.assertEqual(evidence['outputs']['failure-before']['output'], {})
        self.assertEqual(evidence['outputs']['failure-after']['output']['remaining_questions'], ['failure'])
        expected, account, checks = trial.result_material(self.runtime, measured, self.f.reviewer)
        self.assertEqual(account['measurement'], evidence); self.assertEqual(checks, evidence['checks'])
        self.assertEqual(expected['execution_outcome'], 'succeeded')
        self.assertEqual(self.batch.snapshot()['micro_evolution']['active_pair'], trial.cs.activation.pair(self.f.f.before))
        self.assertIsNotNone(self.batch.snapshot()['micro_evolution']['pending'])
        self.assertEqual(trial.t._file(self.runtime.root / 'ledger.json')['attempts'], [])
        with self.assertRaises(FileExistsError): trial.execute(self.runtime, prepared, self.adapter)

    def test_tampered_output_denied_before_independent_result_call(self):
        measured = trial.execute(self.runtime, self.prepare(), self.adapter)
        evidence = trial.t.c._read(measured['measurement'])
        evidence['outputs']['success-after']['output'] = {'forged': 'benefit'}
        measured['measurement'] = self.f.f.h.write('tampered-measurement', evidence)
        with self.assertRaisesRegex(ValueError, 'actual measured child'):
            trial.result_material(self.runtime, measured, self.f.reviewer)

    def test_missing_frozen_context_and_foreign_source_verdict_do_not_propose(self):
        bad = trial.t.c._read(self.scope); bad['implementation_sha256'] = 'f' * 64
        review = self.f.f.h.write('bad-static-review', bad)
        with self.assertRaises(ValueError):
            trial.prepare(self.runtime, self.f.material, review, self.f.reviewer, self.adapter)
        self.assertIsNone(self.batch.snapshot()['micro_evolution']['pending'])

    def test_known_child_failure_keeps_parent_and_failure_receipts(self):
        ordinary = trial.replay.invoke
        count = [0]
        def fail(source, python, context, directory, **kwargs):
            count[0] += 1
            if count[0] == 2: kwargs['seconds'] = .00001
            return ordinary(source, python, context, directory, **kwargs)
        with patch.object(trial.replay, 'invoke', side_effect=fail):
            measured = trial.execute(self.runtime, self.prepare(), self.adapter)
        evidence = trial.t.c._read(measured['measurement'])
        self.assertEqual(measured['execution_outcome'], 'failed'); self.assertFalse(evidence['checks']['bounded_trial'])
        self.assertEqual(evidence['train_fits'], 0); self.assertEqual(len(evidence['outputs']), 2)
        self.assertEqual(self.batch.snapshot()['micro_evolution']['active_pair'], trial.cs.activation.pair(self.f.f.before))

    def result_review(self, measured, *, observed=True, verdict='PASS', compatibility=True, self_sign=False):
        ordinary = self.f.review_role
        def role(name, packet, schema, **kwargs):
            value = ordinary(name, packet, schema, **kwargs)
            value['response'].update(stage='result', verdict=verdict, benefit_observed=observed,
                compatibility_checks={name: compatibility for name in packet['trusted_checks']})
            value['response']['finding'] = 'Synthetic reviewer control of adoption, not empirical capability benefit.'
            if self_sign: value['call_id'] = self.f.author_result['call_id']
            return value
        self.f.review_transport.side_effect = role
        return self.f.reviewer.review('result', measured)

    def test_independent_acceptance_selects_version_and_actual_downstream_child_uses_it(self):
        measured = trial.execute(self.runtime, self.prepare(), self.adapter)
        binding = self.result_review(measured)
        receipt = trial.t.c._read(binding); self.assertEqual(receipt['capacity_decision'], 'accept')
        self.adapter.review(receipt['capacity_activation_review'], expected_state_sha256=self.batch.snapshot()['state_sha256'])
        selected = self.adapter._selected(self.batch.snapshot())
        source = self.runtime.repo / selected['entrypoints']['H']
        downstream = trial.replay.invoke(trial.replay.pin(source), selected['manifest']['runtime']['python'],
            {'history': [{'decision': 'REVERT', 'question': 'next actual input'}]}, self.runtime.root / 'actual-downstream',
            seconds=2, rss_bytes=1073741824)
        self.assertEqual(downstream['output']['remaining_questions'], ['next actual input'])
        restored = trial.cs.activation.CapacityActivation(self.batch, source_root=self.runtime.repo,
            registry_root=self.runtime.root / 'capacity-versions', baseline=self.f.f.before, entrypoints=self.f.f.entrypoints)
        self.assertEqual(restored._selected(self.batch.snapshot()), selected)
        self.assertEqual(len(self.batch.snapshot()['micro_evolution']['history']), 1)
        with self.assertRaises(FileExistsError): self.result_review(measured)

    def test_no_benefit_is_recorded_rejection_not_loop_exception_or_activation(self):
        measured = trial.execute(self.runtime, self.prepare(), self.adapter)
        binding = self.result_review(measured, observed=False)
        receipt = trial.t.c._read(binding); self.assertEqual(receipt['capacity_decision'], 'reject')
        self.adapter.review(receipt['capacity_activation_review'], expected_state_sha256=self.batch.snapshot()['state_sha256'])
        state = self.batch.snapshot()['micro_evolution']
        self.assertIsNone(state['pending']); self.assertEqual(state['active_pair'], trial.cs.activation.pair(self.f.f.before))
        self.assertEqual(state['history'][0]['review']['decision'], 'reject')

    def test_independent_REJECT_can_reconcile_but_cannot_adopt(self):
        measured = trial.execute(self.runtime, self.prepare(), self.adapter)
        receipt = trial.t.c._read(self.result_review(measured, verdict='REJECT'))
        self.assertFalse(receipt['passed']); self.assertEqual(receipt['capacity_decision'], 'reject')
        self.adapter.review(receipt['capacity_activation_review'], expected_state_sha256=self.batch.snapshot()['state_sha256'])
        self.assertEqual(self.batch.snapshot()['micro_evolution']['active_pair'], trial.cs.activation.pair(self.f.f.before))

    def test_author_cannot_self_sign_benefit(self):
        measured = trial.execute(self.runtime, self.prepare(), self.adapter)
        with self.assertRaisesRegex(ValueError, 'distinct original reviewer'):
            self.result_review(measured, self_sign=True)


if __name__ == '__main__': main()
