"""Full parent source through final Author packing; no live model or code execution."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from edgar_forecast_budget import BudgetStop
from edgar_forecast_tools import function
import earnings_open_context as context
import earnings_open_roles as roles
from market_rsi import digest
import test_earnings_open_roles as fixtures


def outputs(request):
    items = request['input']
    if len(items) == 2 and items[1].get('role') == 'user':
        value = json.loads(items[1]['content'])
        if value.get('schema') == 'earnings_author_final_public_snapshot_v1':
            items = value['records']
    return {item['call_id']: item['output'] for item in items
            if item.get('type') == 'function_call_output'}


class AuthorParentContextTests(unittest.TestCase):
    def request(self):
        request = {'model': 'gpt-6.1-sol', 'reasoning': {'effort': 'high'},
            'instructions': 'Unchanged Author instructions', 'tools': [], 'tool_choice': 'none',
            'text': {'format': {'name': 'earnings_open_author_v1', 'schema': {'properties':
                {key: {} for key in ('decision_sha256', 'source_text', 'test_text')}}}},
            'input': [{'role': 'user', 'content': 'Immutable synthetic decision'}]}
        for token, tool in [('current', 'read_current_program'), ('pool', 'read_population_program'),
                            ('reference', 'read_reference_program'), ('old', 'inspect_trace'),
                            ('new', 'inspect_trace')]:
            request['input'].extend([{'type': 'function_call', 'call_id': token,
                'name': tool, 'arguments': '{}'}, {'type': 'function_call_output',
                'call_id': token, 'output': json.dumps({'value': {'source_text': token+'-'+'x'*16000}})}])
        return request

    def test_author_protects_all_code_returns_and_latest_but_not_old_trace(self):
        request = self.request(); before = deepcopy(request)
        kept = context.author_preserved_outputs(request)
        self.assertEqual(kept, frozenset({'current', 'pool', 'reference', 'new'}))
        packed, _ = context.author_final_view(request, 100, preserve_call_ids=kept)
        actual = outputs(packed); original = outputs(request)
        for token in kept: self.assertEqual(actual[token], original[token])
        self.assertTrue(json.loads(actual['old'])['truncated'])
        self.assertEqual(request, before)

    def test_unrelated_roles_do_not_gain_old_parent_protection(self):
        for name, fields in [('earnings_population_decision_v1', {'schema', 'axis', 'component',
                'parent_pair_sha256', 'feedback_sha256', 'hypothesis', 'expected_effect', 'retire_branch_id'}),
                ('unrelated', {'decision_sha256', 'source_text', 'test_text'})]:
            request = self.request()
            request['text']['format'] = {'name': name, 'schema': {'properties': {key: {} for key in fields}}}
            with self.subTest(role=name):
                expected = frozenset({'new'}) if name.startswith('earnings_population_') else frozenset()
                self.assertEqual(context.author_preserved_outputs(request), expected)

    def test_protected_code_over_ceiling_fails_without_shrinking_or_retrying_generation(self):
        request = self.request(); before = deepcopy(request); client = Mock()
        client.post.return_value = {'input_tokens': 48001, 'synthetic_count': True}
        with tempfile.TemporaryDirectory() as temporary, self.assertRaises(BudgetStop):
            context.pack(client, request, {'max_input_tokens': 48000}, Path(temporary), 1, author_final=True)
        self.assertLessEqual(client.post.call_count, 4)
        for call in client.post.call_args_list:
            self.assertEqual(call.args[0], '/v1/responses/input_tokens')
            observed = outputs(call.args[1])
            for token in ('current', 'pool', 'reference'): self.assertEqual(observed[token], outputs(before)[token])
        self.assertEqual(request, before)

    def real_author_final(self, *, unfit=False):
        fixture = fixtures.OpenRoleTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        fixture.broker.definitions.append(function('read_population_program', 'Synthetic parent source page',
            {'version_id': {'type': 'string'}, 'axis': {'type': 'string'},
             'offset': {'type': 'integer'}, 'characters': {'type': 'integer'}}))
        role = fixture.service(author=True, max_turns=5, limits={
            'max_input_tokens': 48000, 'max_output_tokens': 49152, 'wall_seconds': 900})
        parent = "PROGRAM={'axis':'R'}\ndef working_fallback(p): return p\n"+'# parent-line\n'*2400
        page = parent[4000:8000]
        parent_hash = hashlib.sha256(parent.encode()).hexdigest()
        fixture.broker.handler = lambda name, args: (
            {'value': {'source_text': parent, 'source_sha256': parent_hash}} if name == 'read_current_program'
            else {'value': {'text': page, 'offset': 4000, 'source_sha256': parent_hash}}
            if name == 'read_population_program' else {'public_trace': 'trace-'*8000}
            if args['slot'] == 'old' else {'public_trace': 'newest small observation'})
        counted = []
        def count(endpoint, request):
            self.assertEqual(endpoint, '/v1/responses/input_tokens'); counted.append(deepcopy(request))
            if request['tool_choice'] != 'none': return {'input_tokens': 100, 'synthetic_count': True}
            old = json.loads(outputs(request)['old'])
            fits = old.get('truncated') is True and len(old['preview'].encode()) <= 100
            return {'input_tokens': 47900 if fits and not unfit else 48001, 'synthetic_count': True}
        fixture.factory.return_value.post.side_effect = count
        chosen = fixture.choice()
        fixture.generations = [
            fixture.tool_response(fixture.call('parent', 'read_current_program', {'axis': 'R'})),
            fixture.tool_response(fixture.call('page', 'read_population_program',
                {'version_id': 'a'*64, 'axis': 'R', 'offset': 4000, 'characters': 4000})),
            fixture.tool_response(fixture.call('old', arguments={'slot': 'old'})),
            fixture.tool_response(fixture.call('new', arguments={'slot': 'new'})),
            fixture.message({'decision_sha256': digest(chosen),
                'source_text': "PROGRAM={'axis':'R'}\ndef run(p): return p\n",
                'test_text': "CASES=[{'input':{},'expected':{}}]"})]
        with patch.object(roles, 'budgeted_response', side_effect=fixture.fake_paid):
            if unfit:
                with self.assertRaisesRegex(RuntimeError, 'BudgetStop'):
                    role.author(chosen, {'axis': 'R'}, str(fixture.slot))
            else: role.author(chosen, {'axis': 'R'}, str(fixture.slot))
        self.assertEqual(len(fixture.requests), 4 if unfit else 5)
        final_counted = [request for request in counted if request['tool_choice'] == 'none']
        self.assertEqual(len(final_counted), 4)
        for request in final_counted:
            actual = outputs(request)
            self.assertEqual(json.loads(actual['parent'])['value']['source_text'], parent)
            self.assertEqual(json.loads(actual['page'])['value']['text'], page)
        result = json.loads((fixture.slot/'result.json').read_bytes())
        self.assertFalse(result['retry_allowed'])
        if unfit:
            self.assertEqual(result['status'], 'FAILED_NO_RETRY')
            self.assertEqual(result['error_type'], 'BudgetStop')
            self.assertFalse((fixture.slot/'05-request.json').exists())
        else:
            saved = json.loads((fixture.slot/'05-request.json').read_bytes())['payload']
            self.assertEqual(saved, fixture.requests[-1])
            self.assertEqual(json.loads(outputs(saved)['parent'])['value']['source_text'], parent)
            self.assertEqual(json.loads(outputs(saved)['page'])['value']['text'], page)
            self.assertEqual(saved['model'], 'gpt-6.1-sol')
            self.assertEqual(saved['reasoning'], {'effort': 'max'})  # Existing fixture context, not a model change.
            self.assertEqual(result['status'], 'COMPLETED_CANDIDATE')
            self.assertEqual(json.loads(saved['input'][1]['content'])['schema'],
                             'earnings_author_final_public_snapshot_v1')

    def test_actual_author_final_saved_request_keeps_full_parent_and_source_page(self):
        self.real_author_final()

    def test_actual_author_final_overflow_still_stops_without_completion_retry(self):
        self.real_author_final(unfit=True)
