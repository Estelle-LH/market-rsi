"""Independent payload-delivery tests; token counts/generations are invented.

Real population roles, context packing and numbered request persistence run on
portable fixtures. No provider, production ledger, candidate, Docker or scorer
executes. Optional04 checks read only its preserved public transport originals.
Passing synthetic counts demonstrates semantics, not real token headroom.
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
import earnings_open_context as packing
import earnings_open_roles as roles
import earnings_population_campaign_context as campaign_context
import earnings_population_services as services
from earnings_population_roles import PopulationController, PopulationReviewer
from earnings_open_resources import role_limits
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_roles as role_fixture
from test_earnings_population_campaign_integration import CampaignIntegrationFixture, CAPITAL

DECISION_FIELDS = {'schema', 'axis', 'component', 'parent_pair_sha256',
                   'feedback_sha256', 'hypothesis', 'expected_effect', 'retire_branch_id'}
REVIEW_FIELDS = {'candidate_id', 'accepted_for_exploration', 'rationale'}


def response_format(name, fields):
    return {'type': 'json_schema', 'name': name, 'strict': True,
            'schema': {'type': 'object', 'properties': {k: {'type': 'string'} for k in fields},
                       'required': sorted(fields), 'additionalProperties': False}}


def output(token, value):
    return {'type': 'function_call_output', 'call_id': token,
            'output': json.dumps(value, sort_keys=True)}


def complete_failure():
    """Invented bounded public excerpts, not financial execution evidence."""
    samples = []
    for i in range(3):
        text = f'FULL_NEARBY_ONLY_{i} ' + 'synthetic financial table row\n'*90
        args = {'path': 'filings/10-Q_public.md', 'offset': i*4000, 'characters': len(text)}
        hit = {'path': args['path'], 'line': 100+i, 'text': f'ORIGINAL_UNALTERED_SEARCH_CROP_{i}'}
        samples.append(dict(request_index=i, hit_index=0,
            request={'tool': 'search_files', 'arguments': {'query': f'metric-{i}', 'max_hits': 50}},
            observed_hit=hit, observed_hit_sha256=digest(hit),
            outer_public_context=dict(provided_by='harness_preparation_not_R_observation',
                source_sha256='a'*64, read_arguments=args,
                read_result=dict(path=args['path'], offset=args['offset'], total_characters=40000,
                    text=text, next_offset=args['offset']+len(text)),
                text_sha256=hashlib.sha256(text.encode()).hexdigest(), untrusted_evidence=True)))
    pair = [deepcopy(samples[0]), deepcopy(samples[0])]
    pair[1]['request']['arguments']['query'] = 'a different query on same source line'
    pair[1]['observed_hit']['text'] = 'A_DIFFERENT_CROP_NOT_A_DIFFERENT_SOURCE'
    pair[1]['observed_hit_sha256'] = digest(pair[1]['observed_hit'])
    return dict(schema='earnings_population_failure_context_v1', company_id=CAPITAL,
        stage='forecast', cutoff='2026-02-01', allowed_manifest_sha256='b'*64,
        probe={'path': '/synthetic/review-forecast-probe.json', 'sha256': 'c'*64},
        source={'path': '/synthetic/rejected-R.py', 'sha256': 'd'*64},
        first_execution={'path': '/synthetic/request-result.json', 'sha256': 'e'*64},
        final_execution={'path': '/synthetic/final-result.json', 'sha256': 'f'*64},
        original_observations_sha256='a'*64, original_request_count=8,
        original_returned_hit_count=206, examples=samples, distinct_query_crops_same_line=pair,
        selection={'serialized_bytes_max': 24576}, scope='Invented public payload fixture only.')


def sample_rows(context):
    packet = context['observations']['public_failure_examples']
    return packet['examples']+packet['distinct_query_crops_same_line']


def assert_compact(test, original, compact):
    test.assertEqual(set(compact), set(original)|{'planning_view'})
    test.assertEqual(compact['planning_view']['original_context_sha256'], digest(original))
    test.assertIn('Author', compact['planning_view']['notice'])
    for key in set(original)-{'observations'}:
        test.assertEqual(compact[key], original[key])
    for key in set(original['observations'])-{'public_failure_examples'}:
        test.assertEqual(compact['observations'][key], original['observations'][key])
    expected = deepcopy(original['observations']['public_failure_examples'])
    lengths = []
    for sample in expected['examples']+expected['distinct_query_crops_same_line']:
        if 'outer_public_context' not in sample:
            continue
        near = sample['outer_public_context']
        lengths.append(len(near['read_result'].pop('text')))
        near.update(read_tool='read_prior_file', text_omitted_from_controller_view=True)
    test.assertEqual(compact['observations']['public_failure_examples'], expected)
    test.assertEqual(compact['planning_view']['omitted_nearby_text_characters'], lengths)


class ControllerPlanningDelivery(CampaignIntegrationFixture):
    def setUp(self):
        super().setUp()
        self.full_failure = complete_failure()
        self.failure_projector.return_value = deepcopy(self.full_failure)

    def test_compact_copy_retains_all_packet_hits_offsets_abi_feedback_and_omission_provenance(self):
        full = self.context()['research_context']
        before = deepcopy(full)
        view = campaign_context.controller_view(full)
        assert_compact(self, full, view)
        self.assertEqual(full, before)
        self.assertEqual(len(sample_rows(view)), 5)
        for original, compact in zip(sample_rows(full), sample_rows(view)):
            self.assertEqual(compact['request'], original['request'])
            self.assertEqual(compact['observed_hit'], original['observed_hit'])
            self.assertEqual(compact['outer_public_context']['read_arguments'],
                             original['outer_public_context']['read_arguments'])
            self.assertNotIn('text', compact['outer_public_context']['read_result'])
        self.assertLess(len(json.dumps(view)), len(json.dumps(full)))
        view['observations']['public_failure_examples']['examples'][0]['observed_hit']['text'] = 'mutated view'
        self.assertEqual(full, before)

    def test_malformed_or_already_compact_context_is_not_silently_reprojected(self):
        full = self.context()['research_context']
        bad = deepcopy(full)
        bad['observations']['public_failure_examples']['examples'][0]['outer_public_context']['read_result']['text'] = 7
        for context in ({'schema': 'wrong', 'observations': {}},
                        dict(full, observations=None), bad, campaign_context.controller_view(full)):
            before = deepcopy(context)
            with self.subTest(schema=context.get('schema')), self.assertRaises(ValueError):
                campaign_context.controller_view(context)
            self.assertEqual(context, before)

    def test_real_services_delivers_compact_controller_but_full_author_and_broker_context(self):
        case = self.fixture.prepare(resident=self.resident)
        owner = services.Services.__new__(services.Services)
        owner.runtime, owner.native_root = self.runtime, self.root
        owner.runner, owner.literature, owner.traces, owner.authored = Mock(), Mock(), {}, {}
        owner.case = Mock(return_value=case)
        controller = role_fixture.OpenRoleTests()
        controller.setUp(); self.addCleanup(controller.doCleanups)
        controller_role = controller.service(max_turns=1, limits=role_limits()['controller'])
        controller.factory.return_value.post.return_value = {'input_tokens': 100, 'synthetic_count': True}
        choice = dict(controller.choice(), parent_pair_sha256=self.version['id'],
                      feedback_sha256=digest(self.feedback_binding), retire_branch_id='none')
        controller.generations = [controller.message(choice)]
        owner.contexts = {'controller': (controller_role.binding,
            {'budget': controller.budget, 'client_factory': controller.factory})}
        with patch.object(services, 'resident', return_value=deepcopy(self.resident)), \
             patch.object(roles, 'budgeted_response', side_effect=controller.fake_paid):
            decision_binding = owner.controller(self.packet, str(controller.slot))
        planning = engine.read(engine.pin(controller.slot/'effective-input.json'))
        full = owner.campaign_context['research_context']
        assert_compact(self, full, planning['research_context'])
        self.assertEqual(engine.read(owner.reference_context_binding), full)
        self.assertEqual(planning['feedback_binding'], self.feedback_binding)
        self.assertEqual(planning['original_R_evidence_abi'], self.abi)
        self.assertEqual(controller_role.context['limits']['max_input_tokens'], 32000)
        self.assertEqual(json.loads(controller.requests[0]['input'][0]['content']), planning)

        author = role_fixture.OpenRoleTests()
        author.setUp(); self.addCleanup(author.doCleanups)
        author_role = author.service(author=True, max_turns=1, limits=role_limits()['author'])
        author.factory.return_value.post.return_value = {'input_tokens': 100, 'synthetic_count': True}
        owner.contexts['author'] = (author_role.binding,
            {'budget': author.budget, 'client_factory': author.factory})
        chosen = engine.read(decision_binding)
        source = "PROGRAM={'axis':'R'}\ndef run(p): return {'synthetic_delivery_only':True}\n"
        author.generations = [author.message({'decision_sha256': digest(chosen),
            'parent_source_sha256': self.version['R']['sha256'],
            'edits': [{'kind': 'replace', 'old_text': Path(self.version['R']['path']).read_text(),
                       'new_text': source}],
            'test_text': "CASES=[{'input':{},'expected':{'synthetic_delivery_only':True}}]"})]
        with patch.object(services, 'resident', return_value=deepcopy(self.resident)), \
             patch.object(roles, 'budgeted_response', side_effect=author.fake_paid):
            child = owner.author(chosen, self.state, str(author.slot))
        delivered = engine.read(engine.pin(author.slot/'effective-input.json'))['research_context']
        # The shared historical-origin fixture explicitly mocks both evidence
        # projectors. Preserve the whole original body plus its separately
        # bounded request-return extension; this is not real receipt evidence.
        self.assertEqual(delivered['failure_evidence_context'],
                         dict(self.full_failure, request_return_examples=self.request_examples))
        self.assertEqual(full['observations']['public_failure_examples'],
                         delivered['failure_evidence_context'])
        self.assertEqual(owner.campaign_context['research_context'], full)
        self.assertEqual(engine.read(owner.reference_context_binding), full)
        self.assertNotIn('planning_view', delivered)
        self.assertEqual(delivered['feedback_binding'], self.feedback_binding)
        self.assertEqual(delivered['original_R_evidence_abi'], self.abi)
        self.assertEqual(child['parent'], self.version['id'])
        self.assertFalse(self.fixture.marker.exists())


class NewestPopulationObservation(unittest.TestCase):
    def request(self, name='earnings_population_decision_v1', fields=DECISION_FIELDS):
        return {'model': 'gpt-6.1-sol', 'reasoning': {'effort': 'max'},
            'instructions': 'Unchanged population planning instructions', 'tool_choice': 'auto',
            'tools': [{'type': 'function', 'name': 'synthetic_no_dispatch'}],
            'text': {'format': response_format(name, fields)},
            'input': [{'role': 'user', 'content': 'Frozen synthetic scientific packet'},
                {'type': 'function_call', 'call_id': 'old', 'name': 'read_reference_program', 'arguments': '{}'},
                output('old', {'value': {'text': 'already-delivered-'*2000}}),
                {'type': 'function_call', 'call_id': 'new', 'name': 'read_population_program', 'arguments': '{}'},
                output('new', {'research_receipt': {'path': '/synthetic/'+'prefix-'*60, 'sha256': 'a'*64},
                    'value': {'source_sha256': 'b'*64, 'offset': 4000, 'next_offset': 4090,
                              'text': 'NEWEST_REQUESTED_PROGRAM_TEXT_MUST_REACH_CONSUMER'}})]}

    def test_exact_population_formats_keep_only_latest_unseen_batch(self):
        for name, fields in [('earnings_population_decision_v1', DECISION_FIELDS),
                             ('earnings_population_review_v1', REVIEW_FIELDS)]:
            request = self.request(name, fields)
            before = deepcopy(request)
            with self.subTest(format=name):
                expected = {'old','new'} if name == 'earnings_population_review_v1' else {'new'}
                self.assertEqual(packing.author_preserved_outputs(request), frozenset(expected))
                request['input'].append(output('new-second', {'value': {'text': 'second unseen result'}}))
                self.assertEqual(packing.author_preserved_outputs(request), frozenset(expected | {'new-second'}))
                self.assertEqual(request['input'][:-1], before['input'])

    def test_legacy_and_same_name_wrong_fields_are_not_population_opt_in(self):
        for name, fields in [('earnings_capacity_decision_v1', DECISION_FIELDS),
                             ('earnings_population_decision_v1', REVIEW_FIELDS),
                             ('earnings_population_review_v1', DECISION_FIELDS),
                             ('unrelated_role', DECISION_FIELDS)]:
            with self.subTest(format=name, fields=fields):
                self.assertEqual(packing.author_preserved_outputs(self.request(name, fields)), frozenset())

    def test_author_keeps_its_existing_old_reference_and_latest_policy(self):
        request = self.request('earnings_open_author_v1', {'decision_sha256', 'source_text', 'test_text'})
        self.assertEqual(packing.author_preserved_outputs(request), frozenset({'old', 'new'}))

    def test_old100_byte_projection_reproduces_loss_but_policy_preserves_exact_code(self):
        request = self.request()
        old, _ = packing.project(request, 100)
        lost = json.loads(old['input'][-1]['output'])
        self.assertTrue(lost['truncated'])
        self.assertNotIn('NEWEST_REQUESTED_PROGRAM_TEXT', lost['preview'])
        self.assertNotIn('value', lost)
        fixed, _ = packing.project(request, 100,
            preserve_call_ids=packing.author_preserved_outputs(request))
        self.assertEqual(fixed['input'][-1], request['input'][-1])
        self.assertTrue(json.loads(fixed['input'][2]['output'])['truncated'])

    def test_unfit_newest_output_still_stops_under_original_count_gate(self):
        request = self.request()
        before = deepcopy(request)
        with tempfile.TemporaryDirectory() as temporary:
            client = Mock()
            client.post.return_value = {'input_tokens': 16001, 'synthetic_count': True}
            with self.assertRaises(BudgetStop):
                packing.pack(client, request, {'max_input_tokens': 16000}, Path(temporary), 1)
            self.assertLessEqual(client.post.call_count, 4)
            for call in client.post.call_args_list:
                self.assertEqual(call.args[0], '/v1/responses/input_tokens')
                self.assertEqual(call.args[1]['input'][-1], before['input'][-1])
            self.assertEqual(request, before)

    def physical_role(self, reviewer=False):
        fixture = role_fixture.OpenRoleTests()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        limits = deepcopy(role_limits()['review' if reviewer else 'controller'])
        self.assertEqual(limits['max_input_tokens'], 32000)
        template = fixture.service(max_turns=3, limits=deepcopy(role_limits()['controller']) if reviewer else limits)
        binding, slot = template.binding, fixture.slot
        if reviewer:
            context = deepcopy(template.context)
            slot = fixture.root/'roles/review-01'
            context.update(schema='earnings_capacity_review_transport_v1', slots=[str(slot)], limits=deepcopy(limits))
            binding = engine.save(fixture.root/'synthetic-review-context.json', context)
        fixture.broker.definitions.append(function('read_population_program', 'Synthetic exact code read',
            {'version_id': {'type': 'string'}, 'axis': {'type': 'string'},
             'offset': {'type': 'integer'}, 'characters': {'type': 'integer'}}))
        latest = {'research_receipt': {'path': '/synthetic/'+'receipt-prefix-'*35, 'sha256': 'c'*64},
            'value': {'source_sha256': 'd'*64, 'offset': 4000, 'next_offset': 4100,
                      'text': 'PHYSICAL_NEWEST_CODE_TEXT\n'+'def reusable_algorithm(p): return p\n'*30}}
        fixture.broker.handler = lambda name, args: (deepcopy(latest) if name == 'read_population_program'
                                                     else {'value': {'text': 'old-public-text-'*3000}})
        counted = []
        def observations(request):
            items = request['input']
            if len(items) == 2 and items[1].get('role') == 'user':
                snapshot = json.loads(items[1]['content'])
                if snapshot.get('schema') == 'earnings_review_final_public_snapshot_v1':
                    items = snapshot['records']
            return {item['call_id']: item['output'] for item in items
                    if item.get('type') == 'function_call_output'}
        def count(endpoint, request):
            self.assertEqual(endpoint, '/v1/responses/input_tokens')
            counted.append(deepcopy(request))
            returns = observations(request)
            if 'new-read' not in returns:
                return {'input_tokens': 100, 'synthetic_count': True}
            old = json.loads(returns['old-read'])
            fits = old.get('truncated') is True and len(old['preview'].encode()) <= 100
            return {'input_tokens': limits['max_input_tokens']-100 if fits
                    else limits['max_input_tokens']+1, 'synthetic_count': True}
        fixture.factory.return_value.post.side_effect = count
        role = (PopulationReviewer if reviewer else PopulationController)(binding,
            broker=fixture.broker, budget=fixture.budget, client_factory=fixture.factory, max_turns=3)
        prompt = dict(active_versions=['a'*64], explorers=[], stable_id='a'*64,
            feedback_sha256='b'*64, feedback_binding={'path': '/synthetic/feedback.json', 'sha256': 'e'*64},
            feedback={'score_state': 'unscored', 'synthetic': True}, company_id='CIK0000017313')
        business = ({'candidate_id': 'f'*64, 'accepted_for_exploration': False,
                     'rationale': 'Synthetic public-output delivery test, no financial judgment.'}
                    if reviewer else dict(fixture.choice('continue'), retire_branch_id='none'))
        if reviewer:
            prompt['candidate_id'] = business['candidate_id']
        fixture.generations = [fixture.tool_response(fixture.call('old-read')),
            fixture.tool_response(fixture.call('new-read', 'read_population_program',
                {'version_id': 'a'*64, 'axis': 'R', 'offset': 4000, 'characters': 4000})),
            fixture.message(business)]
        with patch.object(roles, 'budgeted_response', side_effect=fixture.fake_paid):
            (role.review if reviewer else role.propose)(prompt, str(slot))
        sent = engine.read(engine.pin(slot/'03-request.json'))
        self.assertTrue(sent['synthetic'])
        physical = sent['payload']
        delivered = observations(physical)
        self.assertEqual(json.loads(delivered['new-read']), latest)
        self.assertTrue(json.loads(delivered['old-read'])['truncated'])
        self.assertEqual(json.loads(physical['input'][0]['content']), prompt)
        self.assertEqual(physical['model'], 'gpt-6.1-sol')
        self.assertEqual(physical['reasoning'], {'effort': 'max'})
        self.assertEqual(role.context['limits'], limits)
        self.assertEqual(len(fixture.requests), 3)
        self.assertEqual(physical, fixture.requests[-1])
        last_preparation = engine.read(engine.pin(slot/'03-context-04.json'))
        self.assertEqual(last_preparation['max_input_tokens'], limits['max_input_tokens'])
        self.assertEqual([item['call_id'] for item in last_preparation['preserved_observations']], ['new-read'])
        self.assertTrue(counted)

    def test_controller_newest_source_text_reaches_actual_saved_generation_request(self):
        self.physical_role()

    def test_reviewer_newest_source_text_reaches_actual_saved_generation_request(self):
        self.physical_role(reviewer=True)


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_CONTROLLER_HEADROOM_04') == '1',
                     'Explicit read-only closed04 public transport audit opt-in required')
class Actual04PublicTransport(unittest.TestCase):
    root = Path('/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/edgar-population-20261016/attempts/edgar-population-20261016-04/roles/controller-01')

    def test_actual_initial_context_only_drops_rereadable_nearby_bodies(self):
        path = self.root/'effective-input.json'
        before = path.read_bytes()
        packet = json.loads(before)
        context = packet['research_context']
        compact = campaign_context.controller_view(context)
        assert_compact(self, context, compact)
        self.assertLess(len(json.dumps(compact).encode()), len(json.dumps(context).encode()))
        self.assertEqual(packet['feedback_binding'], context['observations']['feedback_binding'])
        self.assertEqual(packet['original_R_evidence_abi'], context['observations']['original_R_evidence_abi'])
        self.assertEqual(path.read_bytes(), before)

    def test_actual04_newest_read_was_stored_but_only_preview_reached_next_request(self):
        sent = json.loads((self.root/'02-request.json').read_bytes())['payload']
        calls = {item['call_id']: item for item in sent['input'] if item.get('type') == 'function_call'}
        returns = [item for item in sent['input'] if item.get('type') == 'function_call_output']
        self.assertTrue(returns)
        latest = returns[-1]
        self.assertEqual(calls[latest['call_id']]['name'], 'read_population_program')
        preview = json.loads(latest['output'])
        self.assertEqual(preview['schema'], 'earnings_tool_observation_projection_v1')
        self.assertTrue(preview['truncated'])
        self.assertNotIn('value', preview)
        originals = [json.loads(path.read_bytes()) for path in self.root.glob('01-tool-*.json')]
        matching = [item for item in originals if item['call_id'] == latest['call_id']]
        self.assertEqual(len(matching), 1)
        exact = json.loads(matching[0]['output'])
        self.assertIsInstance(exact['value']['text'], str)
        self.assertTrue(exact['value']['text'])
        self.assertEqual(preview['original_output_sha256'], hashlib.sha256(matching[0]['output'].encode()).hexdigest())
        self.assertNotIn(exact['value']['text'], latest['output'])


if __name__ == '__main__':
    unittest.main()
