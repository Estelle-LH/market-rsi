"""Selected hooks actually change the next bound packet; local fixtures only."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main

from supervisor_harness import price_capacity_loop as hooks
from supervisor_harness import test_price_capacity_trial as fixtures


class HookTests(TestCase):
    def setUp(self):
        self.f = fixtures.TrialTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        trial = fixtures.trial
        runtime = self.f.runtime
        config = {'schema': 'price_capacity_loop_configuration_v1', 'baseline': self.f.f.f.before,
            'entrypoints': self.f.f.f.entrypoints, 'replay_cases': self.f.f.f.packet['source_context']['capacity_replay_cases'],
            'hook_seconds': 2}
        binding = self.f.f.f.h.write('hook-config', config)
        def save(ctx, role, value): return self.f.f.f.h.write('hook-round-' + role, value)
        self.service = SimpleNamespace(runtime=runtime, base={'identity_configuration': self.f.f.f.packet['action_context']['identity_configuration'],
            'python_binding': config['baseline']['runtime']['python']}, _save=save)
        self.hooks = hooks.PriceCapacityLoop(self.service, binding, self.f.f.f.author, self.f.f.reviewer, _test_adapter=self.f.adapter)

    def packet(self):
        return deepcopy(self.f.f.f.packet)

    def test_same_packet_actual_selected_version_consumption_and_restore(self):
        measured = fixtures.trial.execute(self.f.runtime, self.f.prepare(), self.f.adapter)
        reviewed = fixtures.trial.t.c._read(self.f.result_review(measured))
        self.f.adapter.review(reviewed['capacity_activation_review'], expected_state_sha256=self.f.batch.snapshot()['state_sha256'])
        packet = self.packet()
        result = self.hooks.packet({'round_index': 2}, packet, invoke=True)
        self.assertTrue(result['overhead']['capacity_hooks_resolved'])
        proof = result['source_context']['capacity_hook_outputs']
        source = fixtures.trial.t.c._read(self.f.f.material['author_receipt'])['source']
        receipt = fixtures.trial.t.c._read(proof['actual_invocations']['H']['receipt'])
        self.assertEqual(receipt['source'], source)
        self.assertEqual(proof['selected_pair'], self.f.batch.snapshot()['micro_evolution']['active_pair'])
        self.assertEqual(fixtures.trial.t.c._read(result['bindings']['source_context']), result['source_context'])
        self.assertEqual(result['action_context']['identity_configuration']['pair'], proof['selected_pair'])
        self.assertIn('remaining_questions', proof['actual_invocations']['H']['output'])
        self.assertEqual(fixtures.trial.t._file(self.f.runtime.root / 'ledger.json')['attempts'], [])

    def test_preflight_has_no_child_and_no_invocation_claim(self):
        from unittest.mock import patch
        with patch.object(hooks.replay, 'invoke') as child:
            packet = self.hooks.packet({'round_index': 1}, self.packet())
        self.assertFalse(child.called); self.assertFalse(packet['overhead']['capacity_hooks_resolved'])
        self.assertEqual(packet['schema'], 'controller_price_feedback_input_v2')


if __name__ == '__main__': main()
