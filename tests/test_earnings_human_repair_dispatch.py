"""Offline invented dispatch/request fixtures, never repair or improvement proof."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest import mock

import earnings_open_roles as roles
from earnings_open_broker import ResearchBroker
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_roles as role_fixture
import test_earnings_research_state as state_fixture


DISPATCH = {'schema':'earnings_human_repair_dispatch_v1',
    'human_authorization':'允许修正任务派发后测试', 'axis':'R', 'component':'research_policy',
    'scope':'first_declared_controller_slot', 'adoption':'unchanged_independent_selection'}
ABSENT = object()


class HumanRepairDispatchTests(unittest.TestCase):
    def setUp(self):
        self.data = state_fixture.ResearchStateTests()
        self.data.setUp(); self.addCleanup(self.data.doCleanups)
        self.root, self.number = self.data.root, 0
        self.source = self.root/'invented-failed-R.py'
        self.source.write_text("PROGRAM={'axis':'R'}\ndef run(p): return {}\n")
        self.base = {'schema':'earnings_repair_context_v1',
            'human_task':'Diagnose an invented extraction problem.',
            'prior_candidate':{'axis':'R','status':'rejected','source':engine.pin(self.source),
                               'parent_score_out_of_5':1.5,'score_out_of_5':1.0},
            'observations':['Invented empty extraction.'], 'verification':['Keep original selection.'],
            'non_claims':['No autonomous repair or score gain established.']}
        self.runner = mock.Mock()

    def broker(self, marker=ABSENT):
        self.number += 1
        body = deepcopy(self.base)
        if marker is not ABSENT: body['dispatch'] = deepcopy(marker)
        binding = engine.save(self.root/f'context-{self.number}.json', body)
        return ResearchBroker(self.root/f'broker-{self.number}', company=self.data.company,
            capacity=mock.Mock(), runner=self.runner, literature=mock.Mock(), trace_slots={},
            research_context_binding=binding)

    def fixture(self, broker=None, which=0):
        f = role_fixture.OpenRoleTests(); f.setUp(); self.addCleanup(f.doCleanups)
        if broker is not None: f.broker = broker
        f.service(max_turns=1)  # Build only its independently owned synthetic transport context.
        body = json.loads(f.context_path.read_bytes())
        body['slots'] = [str(f.root/'roles'/name) for name in (
            'controller-01','controller-02','controller-terminal')]
        f.context_path.write_text(json.dumps(body))
        service = roles.OpenController(engine.pin(f.context_path), budget=f.budget,
            client_factory=f.factory, broker=f.broker, max_turns=1)
        f.slot = Path(body['slots'][which])
        if broker is not None: f.prompt['research_context'] = broker.research_context()
        return f, service

    def invoke(self, f, service):
        with mock.patch.object(roles, 'pack', side_effect=lambda _c, request, *_a, **_k:deepcopy(request)), \
                mock.patch.object(roles, 'budgeted_response', side_effect=f.fake_paid):
            return service.propose(f.prompt, str(f.slot))

    def fields(self, f):
        return f.requests[0]['text']['format']['schema']['properties']

    def test_bound_optional_marker_roundtrips_exactly_and_legacy_stays_six_fields(self):
        broker = self.broker(DISPATCH)
        self.assertEqual(broker.research_context()['dispatch'], DISPATCH)
        self.assertEqual(set(broker.research_context()), set(self.base)|{'dispatch'})
        self.assertEqual(broker.research_context()['prior_candidate']['source'], self.base['prior_candidate']['source'])
        self.assertEqual(self.broker().research_context(), self.base)
        self.runner.run.assert_not_called()

    def test_marker_requires_exact_schema_scope_types_and_no_extra_fields(self):
        bad = [None, True, [], dict(DISPATCH, schema='other'),
               dict(DISPATCH, human_authorization='yes'), dict(DISPATCH, axis='H'),
               dict(DISPATCH, component='memory_policy'), dict(DISPATCH, scope=True),
               dict(DISPATCH, scope='all_slots'), dict(DISPATCH, adoption='automatic'),
               dict(DISPATCH, extra=False), {k:v for k,v in DISPATCH.items() if k!='adoption'}]
        for marker in bad:
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                self.broker(marker).research_context()

    def test_first_slot_actual_request_narrows_axis_component_and_retains_bound_packet(self):
        broker = self.broker(DISPATCH)
        f, service = self.fixture(broker)
        f.generations = [f.message(f.choice('R'))]
        result = self.invoke(f, service)
        fields = self.fields(f)
        self.assertEqual(fields['axis']['enum'], ['R'])
        self.assertEqual(fields['component']['enum'], ['research_policy'])
        self.assertEqual(json.loads(f.requests[0]['input'][0]['content']), f.prompt)
        self.assertEqual(json.loads((f.slot/'effective-input.json').read_bytes()), f.prompt)
        self.assertEqual(json.loads(Path(result['path']).read_bytes()), f.message(f.choice('R')))
        self.assertEqual(json.loads((f.slot/'decision.json').read_bytes())['decision'], f.choice('R'))
        self.assertEqual(len(f.requests), 1)

    def test_noncompliant_originals_fail_once_unchanged_without_decision_or_retry(self):
        for axis, component in (('continue','none'), ('H','tool_interface'), ('R','memory_policy')):
            f, service = self.fixture(self.broker(DISPATCH))
            wrong = f.choice(axis); wrong['component'] = component
            original = f.message(wrong); f.generations = [deepcopy(original)]
            with self.subTest(axis=axis, component=component), self.assertRaises(RuntimeError):
                self.invoke(f, service)
            self.assertEqual(len(f.requests), 1)
            self.assertEqual(f.generations, [])
            numbered = (f.slot/'01-response.json').read_bytes()
            self.assertEqual(json.loads(numbered), original)
            self.assertEqual((f.slot/'response.json').read_bytes(), numbered)
            self.assertFalse((f.slot/'decision.json').exists())
            failure = json.loads((f.slot/'result.json').read_bytes())
            self.assertEqual(failure['status'], 'FAILED_NO_RETRY')
            self.assertIs(failure['retry_allowed'], False)
            self.assertEqual(failure['turns'], 1)

    def test_later_and_terminal_slots_keep_default_decision_freedom(self):
        for which, axis in ((1,'continue'), (2,'H')):
            f, service = self.fixture(self.broker(DISPATCH), which)
            f.generations = [f.message(f.choice(axis))]
            self.invoke(f, service)
            self.assertEqual(self.fields(f)['axis']['enum'], ['R','H','continue'])
            self.assertEqual(self.fields(f)['component']['enum'],
                             ['research_policy','memory_policy','tool_interface','none'])
            self.assertEqual(json.loads((f.slot/'decision.json').read_bytes())['decision'], f.choice(axis))

    def test_legacy_no_method_and_bound_no_marker_keep_default_first_slot(self):
        for broker in (None, self.broker()):
            f, service = self.fixture(broker)
            f.generations = [f.message(f.choice('continue'))]
            self.invoke(f, service)
            self.assertEqual(self.fields(f)['axis']['enum'], ['R','H','continue'])

    def test_prompt_only_spoof_missing_or_changed_bound_packet_rejected_before_provider(self):
        for mode in ('spoof','missing','changed'):
            broker = None if mode=='spoof' else self.broker(DISPATCH)
            f, service = self.fixture(broker)
            if mode=='spoof': f.prompt['research_context'] = dict(deepcopy(self.base), dispatch=deepcopy(DISPATCH))
            elif mode=='missing': f.prompt.pop('research_context')
            else: f.prompt['research_context']['human_task'] += ' mismatch'
            with self.subTest(mode=mode), self.assertRaises(ValueError): self.invoke(f, service)
            self.assertEqual(f.requests, [])
            f.factory.assert_not_called()

    def test_bound_context_or_source_hash_drift_rejected_before_provider(self):
        for target in ('context','source'):
            broker = self.broker(DISPATCH)
            f, service = self.fixture(broker)
            path = Path(broker.research_context_binding['path']) if target=='context' else self.source
            original = path.read_bytes(); path.write_bytes(original+b' ')
            with self.subTest(target=target), self.assertRaises(ValueError): self.invoke(f, service)
            path.write_bytes(original)
            self.assertEqual(f.requests, []); f.factory.assert_not_called()
        self.runner.run.assert_not_called()

    def test_planner_request_and_role_finalizers_keep_implementation_with_author(self):
        f, service = self.fixture()
        f.generations = [f.message(f.choice('continue'))]
        self.invoke(f, service)
        self.assertIn('Author', f.requests[0]['instructions'])
        for finalizer in (roles.FINALIZE, roles.FINAL_CONTROLLER):
            self.assertNotIn('source_text', finalizer)
            self.assertNotIn('test_text', finalizer)
            self.assertNotIn('Python', finalizer)
        self.assertIn('hypothesis', roles.FINAL_CONTROLLER)
        self.assertIn('expected_effect', roles.FINAL_CONTROLLER)
        for field in ('source_text','test_text','PROGRAM/run(payload)'):
            self.assertIn(field, roles.FINAL_AUTHOR)
        self.assertNotIn('source_text', self.fields(f))

    def test_selected_R_decision_reaches_actual_mocked_author_without_rewrite(self):
        broker = self.broker(DISPATCH)
        f, controller = self.fixture(broker)
        f.generations = [f.message(f.choice('R'))]
        self.invoke(f, controller)
        chosen = json.loads((f.slot/'decision.json').read_bytes())['decision']
        author = f.service(author=True, max_turns=1)
        f.generations = [f.message({'decision_sha256':digest(chosen),
            'source_text':"PROGRAM={'axis':'R'}\ndef run(p): return {}\n",
            'test_text':"CASES=[{'input':{},'expected':{}}]"})]
        with mock.patch.object(roles, 'pack', side_effect=lambda _c, request, *_a, **_k:deepcopy(request)), \
                mock.patch.object(roles, 'budgeted_response', side_effect=f.fake_paid):
            author.author(chosen, {'axis':'R'}, str(f.slot))
        payload = json.loads(f.requests[-1]['input'][0]['content'])
        self.assertEqual(payload['decision'], chosen)
        self.assertEqual(payload['decision_sha256'], digest(chosen))
        self.assertEqual(payload['research_context']['dispatch'], DISPATCH)
        self.assertEqual(payload['research_context']['prior_candidate']['source_text'], self.source.read_text())
        self.assertEqual(set(f.requests[-1]['text']['format']['schema']['properties']),
                         {'decision_sha256','source_text','test_text'})
        self.runner.run.assert_not_called()


if __name__=='__main__':
    unittest.main()
