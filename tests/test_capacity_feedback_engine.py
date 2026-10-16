"""Non-financial executable task fixtures; real driver/native versions, no LLM."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from supervisor_harness import capacity_feedback_engine as engine
from market_rsi import digest
import earnings_capacity_adapter as profiles
import test_earnings_capacity_loop as loop_fixture


class LocalTask:
    """Trusted arithmetic/count scorer kept outside the fixture execution role."""
    def __init__(self, owner, kind, *, restore=False):
        self.owner, self.kind = owner, kind
        def materialize(name, body):
            path = owner.root / name
            return engine.pin(path) if restore else engine.save(path, body)
        self.data = materialize('public-data.json', {'numbers': [10, -3, 2]})
        self.expected = materialize('scoring-only.json', {'answer': 9 if kind == 'sum' else 3})
        self.initial = materialize('initial-state.json', {'task': kind, 'records': []})
        self.calls = []
        self.changed_feedback = False
        self.drop_previous_state = False

    def preflight(self, envelope):
        if envelope['mode'] != 'offline_replay' or envelope['task_kind'] != self.kind:
            raise ValueError('Wrong offline task contract')
        engine.read(self.data); engine.read(self.expected)

    def sources(self): return {'public': self.data, 'scoring_only': self.expected}
    def seed(self, envelope):
        return {'feedback': {'task': self.kind, 'observed': None}, 'state': self.initial, 'artifacts': [self.initial]}
    def role_slot(self, envelope, index, name):
        return envelope['slots'][index-1]['forecast' if name == 'execute' else name]
    def load_state(self, bound):
        state = engine.read(bound)
        if state['task'] != self.kind: raise ValueError('Cross-task state')
        return state
    def packet(self, envelope, ctx, selected_profiles, pair):
        feedback = deepcopy(ctx['previous_result']['feedback'])
        if self.changed_feedback: feedback['observed'] = 'invented replacement'
        return {'task_id': self.kind, 'parent_pair_sha256': pair,
                'feedback_sha256': ctx['previous_feedback_sha256'], 'feedback': feedback,
                'profiles': selected_profiles}
    def decision(self, original, prompt):
        return json.loads(original['output'][0]['content'][0]['text'])
    def candidate(self, original, before, choice):
        return profiles.author_candidate(original, before, choice)
    def worker(self, envelope, capacity, pair, state):
        if self.drop_previous_state and self.calls: state = self.initial
        return LocalWorker(self, capacity, pair, state)
    def execution(self, output, worker, slot):
        if set(output) != {'result', 'state', 'consumption'}: raise ValueError('Missing worker originals')
        for name in output:
            if output[name]['path'] != str(Path(slot) / (name + '.json')):
                raise ValueError('Worker original outside declared slot')
        result, consumption = engine.read(output['result']), engine.read(output['consumption'])
        if result['status'] != 'completed': raise RuntimeError('Preserve failed task, no retry')
        if (consumption['pair'] != worker.pair or consumption['parent_state'] != worker.parent
                or consumption['public_data'] != self.data): raise ValueError('Worker consumption differs')
        expected = engine.read(self.expected)['answer']
        # Actual calculation, not a prewritten increasing test score.
        score = engine.save(Path(slot) / 'score.json', {'squared_error': (result['prediction']-expected)**2})
        return dict(output, score=score, consumed={'pair_sha256': consumption['pair'],
                    'state_sha256': consumption['parent_state']['sha256']}, artifacts=[*output.values(), score])
    def feedback(self, output, envelope):
        return {'task': self.kind, 'observed': engine.read(output['score'])}


class LocalWorker:
    def __init__(self, task, capacity, pair, parent):
        self.task, self.capacity, self.pair, self.parent = task, capacity, pair, parent
        self.state = deepcopy(task.load_state(parent))
        self.context = capacity.prepare(expected_pair_sha256=pair, questions='Execute local '+task.kind,
            state_message={'role': 'user', 'content': json.dumps(self.state)})
    def execute(self, slot):
        root = Path(slot); root.mkdir(parents=True, exist_ok=False)
        values = engine.read(self.task.data)['numbers']
        result = sum(values) if self.task.kind == 'sum' else len(values)
        self.state['records'].append({'public_data': self.task.data, 'values': values})
        self.task.calls.append(self)
        return {name: engine.save(root / (name+'.json'), body) for name, body in {
            'result': {'status': 'completed', 'prediction': result}, 'state': self.state,
            'consumption': {'pair': self.pair, 'parent_state': self.parent, 'public_data': self.task.data,
                            'messages': self.context['messages'], 'tool_bounds': self.context['tool_bounds']}}.items()}


class CommonEngineTests(loop_fixture.CapacityLoopTests):
    def setup_task(self, kind='sum'):
        self.task = LocalTask(self, kind)
        self.envelope.update(mode='offline_replay', task_kind=kind, initial_state=self.task.initial)
        self.bound = engine.save(self.root/'generic-envelope.json', self.envelope)

    def feedback_controller(self, prompt, slot):
        # Deterministic test controller chooses from actual previous scored output.
        self.axes[len(self.packets)] = 'R' if prompt['feedback']['observed'] is None else 'H'
        return self.controller_role(prompt, slot)

    def execute_service(self, worker, slot): return worker.execute(slot)
    def services(self):
        return {'controller': self.feedback_controller, 'author': self.author_role,
                'review': self.review_role, 'execute': self.execute_service}
    def invoke_engine(self):
        return engine.run(self.bound, self.native.restore(), self.task, services=self.services())

    def assert_connected(self, kind):
        self.setup_task(kind)
        outcome = self.invoke_engine()
        self.assertEqual((outcome['status'], outcome['completed_rounds']), ('completed', 2))
        self.assertEqual(self.packets[1]['feedback']['observed'], {'squared_error': 0})
        previous = engine.driver._read_pair(self.root/'episode/loop/round-0001-reconcile.done.json')['output']
        self.assertEqual(self.packets[1]['feedback_sha256'], digest(previous))
        first, second = self.task.calls
        self.assertEqual(second.parent, previous['state'])
        self.assertEqual(second.state['records'][0], first.state['records'][0])
        self.assertEqual(second.context['tool_bounds']['read_chunk_limit'], 1000)
        self.assertEqual(first.context['messages'][1]['content'], 'Verify signs with calculate')
        self.assertEqual(len(self.native.batch.snapshot()['micro_evolution']['history']), 2)
        counts = (len(self.packets), len(self.task.calls), len(self.reviewed))
        self.assertEqual(self.invoke_engine(), outcome)
        self.assertEqual((len(self.packets), len(self.task.calls), len(self.reviewed)), counts)
        self.assertFalse(outcome['result']['claims']['learning'])

    def test_sum_task_has_actual_scores_versions_state_and_completed_restore(self): self.assert_connected('sum')
    def test_count_task_uses_the_same_engine_and_separate_state_scorer(self): self.assert_connected('count')

    def test_data_only_task_still_binds_actual_native_dependencies(self):
        self.setup_task(); self.invoke_engine()
        manifest = engine.driver._read_pair(self.root/'episode/loop/manifest.json')
        used = manifest['handler_identity']['execute']['native_dependencies']
        self.assertEqual(set(used), {'driver','driver_io','activation','identity',
                                     'micro_evolution','capacity','batch','digest'})
        self.assertEqual(used['activation'], engine.pin(engine.activation.__file__))
        self.assertEqual(used['batch'], engine.pin(engine.inspect.getsourcefile(type(self.native.batch))))
        self.assertEqual(used['capacity'], engine.pin(engine.inspect.getsourcefile(type(self.native.restore()))))

    def test_copied_hash_with_changed_feedback_is_refused_before_controller(self):
        self.setup_task(); self.task.changed_feedback = True
        with self.assertRaises(engine.driver.LoopHalted): self.invoke_engine()
        self.assertEqual(self.packets, [])

    def test_fake_review_is_refused_before_worker(self):
        self.setup_task(); self.fake_review = True
        with self.assertRaises(engine.driver.LoopHalted): self.invoke_engine()
        self.assertEqual(self.task.calls, [])

    def test_worker_silently_loading_initial_state_cannot_close_next_round(self):
        self.setup_task(); self.task.drop_previous_state = True
        with self.assertRaises(engine.driver.LoopHalted): self.invoke_engine()
        self.assertFalse((self.root/'episode/loop/round-0002-reconcile.done.json').exists())

    def test_corrupted_retained_state_refused_without_another_call(self):
        self.setup_task(); outcome = self.invoke_engine()
        bound = outcome['result']['state']
        Path(bound['path']).write_text('{}')
        before = len(self.task.calls)
        with self.assertRaises((ValueError, engine.driver.LoopHalted)): self.invoke_engine()
        self.assertEqual(len(self.task.calls), before)

    def test_failed_worker_stops_and_original_failure_is_not_retried(self):
        self.setup_task()
        def failed(worker, slot):
            result = worker.execute(slot)
            # Preserve separate failure output; never rewrite a successful original.
            return {'failure': engine.save(Path(slot)/'failure.json', {'error': 'fixture failure'})}
        services = dict(self.services(), execute=failed)
        for _ in range(2):
            with self.assertRaises(engine.driver.LoopHalted):
                engine.run(self.bound, self.native.restore(), self.task, services=services)
        self.assertEqual((len(self.packets), len(self.task.calls)), (1, 1))
        self.assertTrue(Path(self.envelope['slots'][0]['forecast']).joinpath('failure.json').is_file())

    def test_missing_service_has_no_automatic_fallback(self):
        self.setup_task()
        with self.assertRaisesRegex(ValueError, 'no paid fallback'):
            engine.run(self.bound, self.native.restore(), self.task, services={})


for _name in dir(loop_fixture.CapacityLoopTests):
    if _name.startswith('test_'): setattr(CommonEngineTests, _name, None)

if __name__ == '__main__': unittest.main()
