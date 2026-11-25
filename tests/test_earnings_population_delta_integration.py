"""Delta delivery through original counted transport and Services, all inert.

HTTP count/generation replies are invented bytes on an owned temporary ledger.
Services' case seam is synthetic, not Native/live admission evidence. No model,
financial body, Docker, scorer, credential or candidate execution is used.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from edgar_forecast_tools import function
import earnings_open_context as context
import earnings_open_roles as roles
from earnings_population_delta_author import DeltaAuthor, FORMAT_NAME
import earnings_population_services as services
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from test_earnings_author_parent_context import outputs
from test_earnings_capacity_controller_transport import _TransportFixture, _wire


class DeltaIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='delta-integration-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.marker = self.root/'CANDIDATE_MUST_NOT_EXECUTE'
        self.parent_source = ("PROGRAM={'axis':'R'}\nfrom pathlib import Path\n"
            f"Path({str(self.marker)!r}).write_text('executed')\n"
            + '# synthetic inherited source\n'*1200
            + "def run(p): return {'method':'old'}\n")
        self.parent_r = self.source('R.py', self.parent_source)
        self.parent_h = self.source('H.py', "PROGRAM={'axis':'H','tools':[]}\ndef run(p): return {}\n")
        self.parent = services.describe(self.parent_r, self.parent_h)
        self.state = {'versions': {self.parent['id']: self.parent},
                      'stable_id': self.parent['id'], 'explorers': []}
        self.chosen = {'schema': 'earnings_capacity_decision_v1', 'axis': 'R',
            'component': 'research_policy', 'parent_pair_sha256': self.parent['id'],
            'feedback_sha256': 'b'*64, 'hypothesis': 'Synthetic algorithm delivery',
            'expected_effect': 'Synthetic contract only', 'retire_branch_id': 'none'}

    def source(self, name, text):
        path = self.root/name
        path.write_text(text)
        return engine.pin(path)

    def transport(self):
        fixture = _TransportFixture(self, self.root/'transport')
        fixture.rates['effort'] = 'high'
        self.slot = fixture.root/'roles'/'author-01'
        limits = {'max_input_tokens': 48000, 'max_output_tokens': 49152, 'wall_seconds': 900}
        value = dict(fixture.context, schema='earnings_capacity_author_transport_v1',
                     rates=fixture.rates, limits=limits, slots=[str(self.slot)])
        binding = engine.save(fixture.root/'author-context.json', value)
        parent = self.parent_source
        source_hash = self.parent_r['sha256']

        class Broker:
            definitions = [function('read_current_program', 'Read exact synthetic parent',
                                    {'axis': {'type': 'string', 'enum': ['R', 'H']}})]

            def current_programs(self):
                return {'R': {'source_sha256': source_hash}}

            def dispatch(self, name, arguments):
                if (name, arguments) != ('read_current_program', {'axis': 'R'}):
                    raise AssertionError('Unexpected synthetic tool call')
                return {'value': {'source_text': parent, 'source_sha256': source_hash}}

        return fixture, binding, Broker()

    def drive(self, *, turns=2, unfit=False, bad_patch=False):
        fixture, binding, broker = self.transport()
        business = {'decision_sha256': digest(services.scientific(self.chosen)),
            'parent_source_sha256': self.parent_r['sha256'], 'edits': [{'kind': 'replace',
                'old_text': 'missing unique anchor' if bad_patch else "return {'method':'old'}",
                'new_text': "return {'method':'new'}"}],
            'test_text': "CASES=[{'input':{},'expected':{'method':'new'}}]"}
        first = fixture.response()
        first['output'] = [
            {'type': 'reasoning', 'id': 'opaque_synthetic', 'summary': []},
            {'type': 'function_call', 'call_id': 'parent', 'name': 'read_current_program',
             'arguments': '{"axis":"R"}'}]
        generations = [first, fixture.response(business)]
        generated, counts = [], []
        test = self

        class Connection:
            def __init__(self, host, timeout):
                test.assertEqual(host, 'api.openai.com')
                self.timeout = timeout

            def request(self, method, endpoint, body, headers):
                test.assertEqual(method, 'POST')
                self.endpoint, self.payload = endpoint, json.loads(body)

            def getresponse(self):
                if self.endpoint == '/v1/responses/input_tokens':
                    counts.append(deepcopy(self.payload))
                    snapshot = (len(self.payload['input']) == 2 and
                        self.payload['input'][1].get('role') == 'user' and
                        json.loads(self.payload['input'][1]['content']).get('schema') ==
                        'earnings_author_final_public_snapshot_v1')
                    count = 100 if not generated or (snapshot and not unfit) else 48001
                    raw = _wire({'object': 'response.input_tokens', 'input_tokens': count})
                elif self.endpoint == '/v1/responses':
                    generated.append(deepcopy(self.payload))
                    if len(generated) > len(generations):
                        raise AssertionError('No generation retry allowed')
                    raw = _wire(generations[len(generated)-1])
                else:
                    raise AssertionError('Unexpected synthetic HTTP endpoint')
                return Mock(status=200, getheader=Mock(return_value='req_delta_inert'),
                            read=Mock(side_effect=lambda limit: raw[:limit]))

            def close(self):
                pass

        owner = services.Services.__new__(services.Services)
        owner.authored, owner.pending, owner.traces = {}, [], {}
        owner.case = Mock(return_value={'synthetic': 'not Native admission'})
        def role(name, kind, case, slot):
            self.assertEqual((name, kind), ('author', DeltaAuthor))
            return kind(binding, broker=broker, budget=fixture.budget,
                        client_factory=fixture.factory, max_turns=turns)
        owner.role = role
        state_before = deepcopy(self.state)
        with patch('earnings_http.http.client.HTTPSConnection', side_effect=Connection):
            if unfit or bad_patch:
                with self.assertRaisesRegex(RuntimeError, 'BudgetStop' if unfit else 'ValueError'):
                    owner.author(self.chosen, self.state, str(self.slot))
                child = None
            else:
                child = owner.author(self.chosen, self.state, str(self.slot))
        self.assertEqual(self.state, state_before)
        self.assertFalse(self.marker.exists())
        settled = fixture.budget.db.execute(
            "SELECT status FROM requests WHERE id!='fixture-prior'").fetchall()
        self.assertEqual(settled, [('settled',)]*len(generated))
        return owner, child, business, generated, counts

    def test_original_counted_final_delta_assembles_and_binds_inherited_source(self):
        owner, child, business, generated, counts = self.drive()
        self.assertEqual(len(generated), 2)
        final = generated[-1]
        self.assertEqual(final['tool_choice'], 'none')
        self.assertEqual(final['model'], 'gpt-6.1-sol')
        self.assertEqual(final['reasoning'], {'effort': 'high'})
        self.assertEqual(final['max_output_tokens'], 49152)
        self.assertEqual(final['text']['format']['name'], FORMAT_NAME)
        self.assertEqual(set(final['text']['format']['schema']['properties']),
                         {'decision_sha256', 'parent_source_sha256', 'edits', 'test_text'})
        self.assertIn('do not return source_text', final['instructions'])
        self.assertNotIn(roles.FINAL_AUTHOR, final['instructions'])
        self.assertEqual(json.loads(outputs(final)['parent'])['value']['source_text'], self.parent_source)
        for counted in counts:
            if 'parent' in outputs(counted):
                self.assertEqual(json.loads(outputs(counted)['parent'])['value']['source_text'], self.parent_source)
        expected = self.parent_source.replace("return {'method':'old'}", "return {'method':'new'}")
        self.assertEqual(Path(child['R']['path']).read_text(), expected)
        self.assertEqual(child['H'], self.parent['H'])
        self.assertEqual(child['author'], 'model:DeltaAuthor')
        assembly = engine.read(engine.pin(self.slot/'delta-assembly.json'))
        self.assertEqual(assembly['parent_source'], self.parent_r)
        self.assertEqual(assembly['source'], child['R'])
        self.assertEqual(assembly['tests'], engine.pin(self.slot/'cases.py'))
        self.assertFalse(assembly['host_candidate_execution'])
        raw = engine.read(assembly['raw_patch_response'])
        self.assertEqual(services.assemble(self.parent_r, services.scientific(self.chosen), raw),
            {'decision_sha256': business['decision_sha256'], 'source_text': expected,
             'test_text': business['test_text']})
        saved = engine.read(engine.pin(self.slot/'delta.json'))
        self.assertEqual(saved, {'delta': business, 'original': assembly['raw_patch_response']})
        self.assertNotIn('source_text', saved['delta'])
        self.assertIn(assembly['raw_patch_response'], owner.authored[child['id']]['originals'])

    def test_prospective_early_completion_uses_delta_final_instruction(self):
        _, child, _, generated, _ = self.drive(turns=3)
        self.assertIsNotNone(child)
        self.assertEqual(len(generated), 2)  # Closed tools early; no third request.
        self.assertEqual(generated[-1]['tool_choice'], 'none')
        self.assertIn('do not return source_text', generated[-1]['instructions'])
        self.assertNotIn(roles.FINAL_AUTHOR, generated[-1]['instructions'])
        self.assertTrue(json.loads((self.slot/'02-context-04.json').read_bytes())['early_finalization'])

    def test_unfit_protected_source_still_fails_without_completion_generation(self):
        owner, child, _, generated, _ = self.drive(unfit=True)
        self.assertIsNone(child)
        self.assertEqual(len(generated), 1)
        self.assertEqual(owner.authored, {})
        self.assertFalse((self.slot/'candidate.py').exists())
        self.assertFalse(json.loads((self.slot/'result.json').read_bytes())['retry_allowed'])

    def test_invalid_returned_delta_is_preserved_but_never_becomes_candidate(self):
        owner, child, _, generated, _ = self.drive(bad_patch=True)
        self.assertIsNone(child)
        self.assertEqual(len(generated), 2)
        self.assertTrue((self.slot/'02-response.json').exists())
        self.assertFalse((self.slot/'candidate.py').exists())
        self.assertFalse((self.slot/'delta-assembly.json').exists())
        self.assertEqual(owner.authored, {})

    def test_wrong_current_parent_is_refused_before_client_or_slot(self):
        fixture, binding, broker = self.transport()
        broker.current_programs = lambda: {'R': {'source_sha256': 'f'*64}}
        role = DeltaAuthor(binding, broker=broker, budget=fixture.budget,
                           client_factory=fixture.factory, max_turns=2)
        with self.assertRaisesRegex(ValueError, 'exact current broker'):
            role.author(services.scientific(self.chosen), {'axis': 'R'},
                        str(self.slot), parent_binding=self.parent_r)
        fixture.factory.assert_not_called()
        self.assertFalse(self.slot.exists())

    def test_services_H_delta_preserves_R_and_binds_exact_H_parent(self):
        # This test's role generation is a stub; assembly/metadata/provenance are real.
        owner = services.Services.__new__(services.Services)
        owner.authored = {}
        owner.case = Mock(return_value={'synthetic': 'not Native admission'})
        chosen = dict(self.chosen, axis='H', component='tool_interface')
        slot = self.root/'h-author'

        def author(selected, before, output, *, parent_binding):
            self.assertEqual(parent_binding, self.parent_h)
            self.assertEqual(before, {'axis': 'H', 'tools': []})
            Path(output).mkdir()
            value = {'decision_sha256': digest(selected),
                'parent_source_sha256': self.parent_h['sha256'],
                'edits': [{'kind': 'replace', 'old_text': 'return {}',
                           'new_text': "return {'tool':'synthetic'}"}],
                'test_text': "CASES=[{'input':{},'expected':{'tool':'synthetic'}}]"}
            return engine.save(Path(output)/'response.json', {'status': 'completed',
                'output': [{'type': 'message', 'role': 'assistant', 'content': [
                    {'type': 'output_text', 'text': json.dumps(value)}]}]})

        def role(name, kind, case, output):
            self.assertEqual((name, kind), ('author', DeltaAuthor))
            return Mock(author=author)
        owner.role = role
        child = owner.author(chosen, self.state, str(slot))
        self.assertEqual(child['R'], self.parent_r)
        self.assertNotEqual(child['H']['sha256'], self.parent_h['sha256'])
        assembly = engine.read(engine.pin(slot/'delta-assembly.json'))
        self.assertEqual(assembly['axis'], 'H')
        self.assertEqual(assembly['parent_source'], self.parent_h)
        self.assertEqual(assembly['source'], child['H'])
        self.assertFalse(self.marker.exists())

    def test_only_exact_old_or_delta_format_gets_author_source_protection(self):
        template = {'input': [{'role': 'user', 'content': '{}'},
            {'type': 'function_call', 'name': 'read_current_program', 'arguments': '{}', 'call_id': 'old'},
            {'type': 'function_call_output', 'call_id': 'old', 'output': '{}'},
            {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'public'}]}],
            'tool_choice': 'none'}
        for name, fields, expected in [
            ('earnings_open_author_v1', {'decision_sha256', 'source_text', 'test_text'}, {'old'}),
            (FORMAT_NAME, {'decision_sha256', 'parent_source_sha256', 'edits', 'test_text'}, {'old'}),
            (FORMAT_NAME, {'decision_sha256', 'source_text', 'test_text'}, set()),
            ('unrelated', {'decision_sha256', 'parent_source_sha256', 'edits', 'test_text'}, set())]:
            request = deepcopy(template)
            request['text'] = {'format': {'name': name, 'schema': {'properties': {key: {} for key in fields}}}}
            with self.subTest(name=name, fields=fields):
                self.assertEqual(context.author_preserved_outputs(request), frozenset(expected))
                if expected:
                    context.author_final_view(request, 100, preserve_call_ids=frozenset(expected))
                else:
                    with self.assertRaises(ValueError): context.author_final_view(request, 100)
