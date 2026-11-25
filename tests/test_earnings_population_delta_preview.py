"""Source-only preview: synthetic transport/ledger and opt-in inert15 bytes.

No provider, candidate execution, financial tests, Native admission or QA reads.
The transport case uses original count/reserve/settle with invented HTTP replies.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from edgar_forecast_budget import BudgetStop
from edgar_forecast_tools import function
import earnings_population_delta_author as delta
from earnings_open_program import program
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from test_earnings_capacity_controller_transport import _TransportFixture, _wire
from test_earnings_population_delta_author import R, H, CASES, choice, reply


def edit(old='return 1', new='return 2'):
    return {'kind': 'replace', 'old_text': old, 'new_text': new}


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='delta-preview-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.chosen = choice()
        self.bind(R)

    def bind(self, text):
        self.source = text
        self.path = self.root/'parent.py'
        self.path.write_bytes(text.encode())
        self.bound = engine.pin(self.path)

    def preview(self, edits=None):
        return delta.preview(self.bound, self.chosen,
            json.dumps([edit()] if edits is None else edits, ensure_ascii=False))

    def final(self, edits=None, **changes):
        value = dict(decision_sha256=digest(self.chosen),
            parent_source_sha256=self.bound['sha256'], edits=[edit()] if edits is None else edits,
            test_text=CASES)
        value.update(changes)
        return delta.assemble(self.bound, self.chosen, reply(value))

    def test_shared_assembler_R_H_exact_bytes_and_no_approval(self):
        for axis, source in [('R', R), ('H', H)]:
            with self.subTest(axis=axis):
                self.chosen = choice(axis)
                self.bind(source)
                raw, decision_before = self.path.read_bytes(), deepcopy(self.chosen)
                result = self.preview()
                assembled = self.final()['source_text'].encode()
                self.assertTrue(result['source_valid'])
                self.assertEqual(result['source_utf8_bytes'], len(assembled))
                self.assertEqual(result['source_sha256'], hashlib.sha256(assembled).hexdigest())
                self.assertEqual(result['excess_source_utf8_bytes'], 0)
                self.assertEqual(result['errors'], [])
                for key in ('tests_validated', 'code_executed', 'candidate_saved', 'final_approval'):
                    self.assertIs(result[key], False)
                self.assertNotIn('source_text', result)
                self.assertEqual(self.path.read_bytes(), raw)
                self.assertEqual(self.chosen, decision_before)

    def test_UTF8_size_excess_and_original_final_ceiling(self):
        target = 65536
        suffix = '\n#' + 'x'*(target-len(R.encode())-2)
        edits = [{'kind': 'append', 'old_text': '', 'new_text': suffix}]
        self.assertTrue(self.preview(edits)['source_valid'])
        self.assertEqual(len(self.final(edits)['source_text'].encode()), target)
        edits[0]['new_text'] += '界'
        result = self.preview(edits)
        self.assertEqual(result['source_utf8_bytes'], target+3)
        self.assertEqual(result['excess_source_utf8_bytes'], 3)
        self.assertEqual(result['errors'], [{'code': 'source_size_exceeded'}])
        with self.assertRaises(ValueError):
            self.final(edits)

    def test_literal_errors_and_original_final_rejection(self):
        cases = [[], [edit(new='return 1')], [edit(old='missing')],
            [edit(), edit(old='turn 1', new='turn 3')], [edit()]*17,
            [{'kind': 'append', 'old_text': '', 'new_text': '# first\n'}, edit()],
            [dict(edit(), extra=True)]]
        self.bind(R+'# ambiguous ambiguous\n')
        cases.append([edit(old='ambiguous')])
        for edits in cases:
            with self.subTest(edits=edits):
                result = self.preview(edits)
                self.assertFalse(result['source_valid'])
                self.assertEqual(result['errors'][0]['code'], 'invalid_literal_edits')
                self.assertNotIn('missing', json.dumps(result))
                with self.assertRaises(ValueError):
                    self.final(edits)

    def test_syntax_metadata_invalid_json_and_cases_still_final(self):
        for edits, code in [([edit(new='return (')], 'invalid_python_syntax'),
            ([edit(old="'axis':'R'", new="'axis':'H'")], 'invalid_program_metadata')]:
            with self.subTest(code=code):
                result = self.preview(edits)
                self.assertEqual(result['errors'][0]['code'], code)
                self.assertNotIn('text', json.dumps(result))
                with self.assertRaises((ValueError, SyntaxError)):
                    self.final(edits)
        for raw in ('{', '[] trailing', '{"x":1,"x":2}'):
            result = delta.preview(self.bound, self.chosen, raw)
            self.assertEqual(result['errors'], [{'code': 'invalid_edits_json'}])
        self.assertTrue(self.preview()['source_valid'])
        with self.assertRaises(ValueError):
            self.final(test_text='CASES = []')

    def test_no_parent_or_candidate_execution_or_source_write(self):
        marker = self.root/'MUST_NOT_EXIST'
        self.bind(R+f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n")
        with patch('builtins.exec', side_effect=AssertionError('No execution')):
            self.assertTrue(self.preview()['source_valid'])
        self.assertFalse(marker.exists())
        self.assertEqual(self.path.read_bytes(), self.source.encode())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['parent.py'])

    def test_parent_decision_hash_alias_and_control_errors_not_diagnostics(self):
        foreign = self.root/'foreign.py'
        foreign.write_bytes(R.encode())
        link = self.root/'link.py'
        link.symlink_to(foreign)
        for bound in (dict(self.bound, sha256='f'*64),
            dict(self.bound, path=str(link)), dict(self.bound, path='relative.py')):
            with self.subTest(bound=bound), self.assertRaises(RuntimeError):
                delta.preview(bound, self.chosen, '[]')
        with self.assertRaises(RuntimeError):
            delta.preview(self.bound, {}, '[]')
        for failure in (KeyboardInterrupt(), SystemExit(), BudgetStop('test stop')):
            with self.subTest(type=type(failure).__name__), \
                 patch.object(delta, '_edit_source', side_effect=failure), \
                 self.assertRaises(type(failure)):
                self.preview()


class BrokerTests(unittest.TestCase):
    setUp = PreviewTests.setUp
    bind = PreviewTests.bind

    def broker(self):
        owner = self
        class Base:
            def __init__(self):
                self.calls, self.returned, self.seen = 0, 0, []
                self.definitions = self._definitions()
            def _definitions(self):
                return [function('read_current_program', 'Synthetic read',
                    {'axis': {'type': 'string', 'enum': ['R', 'H']}})]
            def current_programs(self):
                return {'R': {'source_sha256': owner.bound['sha256']}}
            def research_context(self, *, include_source=False):
                return {'include_source': include_source, 'synthetic': True}
            def available_traces(self):
                return ['synthetic-trace']
            def dispatch(self, name, args):
                self.seen.append((name, deepcopy(args)))
                self.calls += 1
                result = {'value': {'synthetic': True}}
                self.returned += len(json.dumps(result).encode())
                return result
        self.base = Base()
        return delta._PreviewBroker(self.base)

    def test_forwarding_original_definition_immutability_and_active_only(self):
        broker = self.broker()
        original = deepcopy(self.base.definitions)
        self.assertEqual(broker.current_programs(), self.base.current_programs())
        self.assertEqual(broker.research_context(include_source=True),
                         {'include_source': True, 'synthetic': True})
        self.assertEqual(broker.available_traces(), ['synthetic-trace'])
        self.assertEqual(len(broker.definitions), len(original)+1)
        with self.assertRaises(RuntimeError):
            broker.dispatch(broker.name, {'edits_json': json.dumps([edit()])})
        broker.activate(self.bound, self.chosen)
        result = broker.dispatch(broker.name, {'edits_json': json.dumps([edit()])})
        self.assertTrue(result['value']['source_valid'])
        self.assertEqual(self.base.calls, 0)
        self.assertEqual(broker.preview_calls, 1)
        self.assertEqual(self.base.definitions, original)
        self.assertEqual(broker.dispatch('read_current_program', {'axis': 'R'}),
                         {'value': {'synthetic': True}})
        self.assertEqual(self.base.seen, [('read_current_program', {'axis': 'R'})])

    def test_live_definition_current_parent_and_bound_bytes_drift_fail_closed(self):
        for kind in ('stored', 'generated', 'instance_producer', 'current', 'bytes'):
            with self.subTest(kind=kind):
                self.bind(R)
                broker = self.broker()
                broker.activate(self.bound, self.chosen)
                if kind == 'stored':
                    self.base.definitions[0]['description'] = 'drift'
                elif kind == 'generated':
                    with patch.object(type(self.base), '_definitions', return_value=[]), self.assertRaises(RuntimeError):
                        broker.dispatch(broker.name, {'edits_json': json.dumps([edit()])})
                    continue
                elif kind == 'instance_producer':
                    self.base._definitions = lambda: []
                elif kind == 'current':
                    self.base.current_programs = lambda: {'R': {'source_sha256': 'f'*64}}
                else:
                    self.path.write_text(R+'# drift\n')
                with self.assertRaises(RuntimeError):
                    broker.dispatch(broker.name, {'edits_json': json.dumps([edit()])})

    def test_exact_outer_protocol_and_original_shared_budgets(self):
        for args in ({}, {'edits_json': 4}, {'edits_json': '[]', 'parent': self.bound},
                     {'edits_json': 'x'*65536}):
            broker = self.broker()
            broker.activate(self.bound, self.chosen)
            with self.subTest(args_type=type(args).__name__), self.assertRaises(RuntimeError):
                broker.dispatch(broker.name, args)
        broker = self.broker()
        broker.activate(self.bound, self.chosen)
        self.base.calls = 63
        broker.dispatch(broker.name, {'edits_json': json.dumps([edit()])})
        with self.assertRaises(RuntimeError):
            broker.dispatch('read_current_program', {'axis': 'R'})
        self.assertEqual(self.base.calls, 63)
        broker = self.broker()
        broker.activate(self.bound, self.chosen)
        self.base.returned = 2_000_000
        with self.assertRaises(RuntimeError):
            broker.dispatch(broker.name, {'edits_json': json.dumps([edit()])})


class CountedPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='delta-preview-counted-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_original_turn_tool_definition_and_argument_limits_stay_fixed(self):
        fixture = _TransportFixture(self, self.root/'transport')
        ctx = dict(fixture.context, schema='earnings_capacity_author_transport_v1',
            limits=dict(max_input_tokens=48000, max_output_tokens=49152, wall_seconds=1200),
            rates=dict(fixture.rates, effort='high'), slots=[str(fixture.root/'roles'/'author-01')])
        binding = engine.save(fixture.root/'author-context.json', ctx)
        base = Mock()
        base.definitions = [function(f'fixture_tool_{i}', 'Synthetic', {}) for i in range(15)]
        role = delta.DeltaAuthor(binding, broker=base, budget=fixture.budget,
                                client_factory=fixture.factory)
        self.assertEqual((role.max_turns, role.max_tool_calls, len(role.definitions)), (8, 24, 16))
        spec = role.definitions[-1]['parameters']
        self.assertEqual(set(spec['properties']), {'edits_json'})
        self.assertEqual(spec['required'], ['edits_json'])
        self.assertIs(spec['additionalProperties'], False)
        for changes in ({'max_turns': 9}, {'max_tool_calls': 25}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                delta.DeltaAuthor(binding, broker=base, budget=fixture.budget,
                                  client_factory=fixture.factory, **changes)
        base.definitions.append(function('fixture_tool_15', 'Synthetic', {}))
        with self.assertRaises(ValueError):
            delta.DeltaAuthor(binding, broker=base, budget=fixture.budget,
                              client_factory=fixture.factory)
        fixture.factory.assert_not_called()

    def drive(self, *, drift=False):
        fixture = _TransportFixture(self, self.root/'transport')
        fixture.rates['effort'] = 'high'
        slot = fixture.root/'roles'/'author-01'
        limits = dict(max_input_tokens=48000, max_output_tokens=49152, wall_seconds=1200)
        ctx = dict(fixture.context, schema='earnings_capacity_author_transport_v1',
                   rates=fixture.rates, limits=limits, slots=[str(slot)])
        binding = engine.save(fixture.root/'author-context.json', ctx)
        parent = fixture.root/'parent.py'
        parent.write_bytes(R.encode())
        parent_binding, chosen = engine.pin(parent), choice()
        base = Mock()
        base.definitions = [function('read_current_program', 'Synthetic original read',
                                     {'axis': {'type': 'string', 'enum': ['R', 'H']}})]
        base.current_programs = Mock(return_value={'R': {'source_sha256': parent_binding['sha256']}})
        first = fixture.response()
        first['output'] = [{'type': 'function_call', 'name': 'preview_delta_source',
            'call_id': 'preview1', 'arguments': json.dumps({'edits_json': json.dumps([edit()])})}]
        final = fixture.response(dict(decision_sha256=digest(chosen),
            parent_source_sha256=parent_binding['sha256'], edits=[edit()], test_text=CASES))
        generations, counts = [], []
        owner = self
        class Connection:
            def __init__(self, host, timeout):
                owner.assertEqual(host, 'api.openai.com')
            def request(self, method, endpoint, body, headers):
                owner.assertEqual(method, 'POST')
                self.endpoint, self.payload = endpoint, json.loads(body)
            def getresponse(self):
                if self.endpoint == '/v1/responses/input_tokens':
                    counts.append(deepcopy(self.payload))
                    raw = _wire({'object': 'response.input_tokens', 'input_tokens': 100})
                elif self.endpoint == '/v1/responses':
                    generations.append(deepcopy(self.payload))
                    owner.assertLessEqual(len(generations), 2)
                    raw = _wire(first if len(generations) == 1 else final)
                    if drift and len(generations) == 1:
                        parent.write_bytes((R+'# mutation\n').encode())
                else:
                    raise AssertionError('Unexpected endpoint')
                return Mock(status=200, getheader=Mock(return_value='req_preview_invented'),
                            read=Mock(side_effect=lambda limit: raw[:limit]))
            def close(self):
                pass
        role = delta.DeltaAuthor(binding, broker=base, budget=fixture.budget,
            client_factory=fixture.factory, max_turns=2)
        with patch('earnings_http.http.client.HTTPSConnection', side_effect=Connection):
            if drift:
                with self.assertRaisesRegex(RuntimeError, 'RuntimeError'):
                    role.author(chosen, program(R.encode(), 'R'), str(slot), parent_binding=parent_binding)
                returned = None
            else:
                returned = role.author(chosen, program(R.encode(), 'R'), str(slot), parent_binding=parent_binding)
        settled = fixture.budget.db.execute(
            "SELECT status FROM requests WHERE id!='fixture-prior'").fetchall()
        self.assertEqual(settled, [('settled',)]*len(generations))
        self.assertIsNone(role.broker.active)
        return role, returned, slot, generations, counts

    def test_real_count_reserve_settle_delivers_preview_to_next_completed_generation(self):
        role, returned, slot, generations, counts = self.drive()
        self.assertIsNotNone(returned)
        self.assertEqual(len(generations), 2)
        self.assertGreaterEqual(len(counts), 2)
        final = generations[-1]
        observations = [x for x in final['input'] if x.get('type') == 'function_call_output']
        self.assertEqual(len(observations), 1)
        received = json.loads(observations[0]['output'])['value']
        self.assertTrue(received['source_valid'])
        self.assertEqual(received['source_utf8_bytes'], len(R.replace('return 1', 'return 2').encode()))
        self.assertFalse(received['final_approval'])
        self.assertEqual(role.broker.preview_calls, 1)
        self.assertEqual(final['text']['format']['name'], delta.FORMAT_NAME)
        self.assertEqual(final['tool_choice'], 'none')
        result = json.loads((slot/'result.json').read_bytes())
        self.assertEqual((result['turns'], result['tool_calls']), (2, 1))
        self.assertEqual(result['status'], 'COMPLETED_CANDIDATE')
        self.assertTrue(any(slot.glob('01-tool-*.json')))
        self.assertFalse((slot/'candidate.py').exists())

    def test_parent_drift_fatal_no_second_generation_and_original_response_preserved(self):
        _, returned, slot, generations, _ = self.drive(drift=True)
        self.assertIsNone(returned)
        self.assertEqual(len(generations), 1)
        self.assertTrue((slot/'01-response.json').exists())
        self.assertFalse((slot/'02-response.json').exists())
        self.assertFalse((slot/'delta.json').exists())
        result = json.loads((slot/'result.json').read_bytes())
        self.assertEqual(result['status'], 'FAILED_NO_RETRY')
        self.assertEqual(result['error_type'], 'RuntimeError')


class Actual15InertReplay(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_DELTA15_PREVIEW') == '1',
                         'Explicit local original15 inert source-byte replay only')
    def test_exact_completed15_delta_still_reports_68326_and_2790_excess(self):
        root = Path('/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/'
                    'edgar-population-20261016/attempts/edgar-population-20261016-15/roles/author-01')
        def exact(name, sha):
            data = (root/name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), sha)
            return json.loads(data)
        packet = exact('effective-input.json', '7ab7f97e5bfaa49ce6eb65323518a801d0e46778dab40adf2918e9cbe2a6e41c')
        raw = exact('08-response.json', '9d677da998be099342e3e389ba737d5169dddde8603b5fa770606f3c4ff5591d')
        bound = packet['parent_source']
        self.assertEqual(bound['sha256'], '631f8e214c01b476b6ae66e72baaaeb929bc2f827d77e7685362d450b518a026')
        before = Path(bound['path']).read_bytes()
        edits = delta.message(raw)['edits']  # Public final delta only, never private reasoning.
        result = delta.preview(bound, packet['decision'], json.dumps(edits, ensure_ascii=False))
        self.assertEqual((result['source_utf8_bytes'], result['excess_source_utf8_bytes']), (68326, 2790))
        self.assertEqual(result['errors'], [{'code': 'source_size_exceeded'}])
        self.assertFalse(result['source_valid'])
        with self.assertRaises(ValueError):
            delta.assemble(bound, packet['decision'], raw)
        self.assertEqual(Path(bound['path']).read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
