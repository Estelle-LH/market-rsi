"""Saved16 count replay and portable ceilings, not a new provider success.

Original physical count payloads/responses are read only under an explicit opt-in.
pack() writes solely to temporary test directories. No ledger, provider, QA,
historical engine, candidate execution or manufactured physical HTTP receipt.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock

from edgar_forecast_budget import BudgetStop
from edgar_forecast_tools import function
from earnings_http import strict_json
import earnings_open_context as context
from earnings_open_resources import ROLE_EFFORTS, role_limits
from earnings_open_roles import OpenAuthor, OpenController
from earnings_population_roles import PopulationReviewer
from supervisor_harness import capacity_feedback_engine as engine


ROOT16 = Path('/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/'
              'edgar-population-20261016/attempts/edgar-population-20261016-16/roles/author-01')
COUNTS = (51800, 51361, 50354, 48743)
PREPARATION_SHAS = (
    'f9b193bcbb27b60b82364b01ffd87e70dc7b5b0671102030b8c3b14a0d373b5b',
    '172e06359f8079ae59aa0512a7ddd689f71dfb449d356ffee586c6cff15feb37',
    'b0dbb9b75f0c22e79a66835bf25493dc61196c1309d34e9d1bfb9e141c6197e8',
    '10d2be942294e86f1ea99d1e3f9e337338bc974aad022a8fc4b26c6362053ab5')
COUNT_SHAS = (
    'ebdaf0d19c2fab19095852f56fc8a9b504e658d9e35be0ef5e981cb2c714acb0',
    'e68eb1a85a1425b1079e4306df11e8f91dbc10db283f4802c26b8affc187f31d',
    'ba97f190d539586074f07f3c70b4a48cc315238137f68219d707bcffb1907e69',
    '0a12c14855f31551745fa0779bd7cda1439b715ef8f52c4b75568e25f29e3311')


def token(value):
    return hashlib.sha256(context.encoded(value)).hexdigest()


def public_outputs(request):
    items = request['input']
    if len(items) == 2 and items[1].get('role') == 'user':
        snapshot = strict_json(items[1]['content'])
        if snapshot.get('schema') == 'earnings_author_final_public_snapshot_v1':
            items = snapshot['records']
    return {item['call_id']: item['output'] for item in items
            if item.get('type') == 'function_call_output'}


def saved16():
    """Hash-join exact own16 preparation/count/raw payloads; open no references."""
    views, count_receipts, preparations = [], [], []
    intents = []
    for path in ROOT16.glob('http-*.intent.json'):
        value = strict_json(path.read_bytes())
        if value.get('endpoint') == '/v1/responses/input_tokens':
            intents.append((path, value))
    for step, (preparation_sha, count_sha) in enumerate(zip(PREPARATION_SHAS, COUNT_SHAS), 1):
        prefix = ROOT16/f'07-context-{step:02d}'
        preparation_bytes = prefix.with_suffix('.json').read_bytes()
        count_bytes = Path(str(prefix)+'-count.json').read_bytes()
        if (hashlib.sha256(preparation_bytes).hexdigest() != preparation_sha
                or hashlib.sha256(count_bytes).hexdigest() != count_sha):
            raise ValueError('Exact original16 preparation/count binding required')
        preparation, counted = strict_json(preparation_bytes), strict_json(count_bytes)
        matches = [(path, intent) for path, intent in intents
                   if token(intent['payload']) == preparation['effective_request_sha256']]
        if len(matches) != 1 or counted['input_tokens'] != COUNTS[step-1]:
            raise ValueError('Unique original16 physical count payload required')
        path, intent = matches[0]
        stem = str(path)[:-len('.intent.json')]
        sidecar = strict_json(Path(stem+'.response.json').read_bytes())
        raw = strict_json(Path(stem+'.raw.bin').read_bytes())
        stripped = dict(sidecar)
        stripped.pop('_request_id', None)
        if sidecar != counted or stripped != raw:
            raise ValueError('Original16 raw/response/count receipt mismatch')
        views.append(deepcopy(intent['payload']))
        count_receipts.append(counted)
        preparations.append(preparation)
    request = views[0]
    # The real final view changed only instructions/tool_choice before replacing
    # native history with a public snapshot. Recover those outer settings; pack()
    # itself must exactly reconstruct the captured final snapshot payload.
    completion = dict(deepcopy(request), instructions=views[3]['instructions'], tool_choice='none')
    if (token(request) != preparations[0]['original_request_sha256']
            or token(completion) != preparations[3]['finalization_request_sha256']):
        raise ValueError('Exact original16 native/completion request reconstruction required')
    return request, completion, views, count_receipts


class SavedCountClient:
    """Offline lookup by exact payload digest, never a new physical request."""
    def __init__(self, views, counts):
        self.known = {token(view): deepcopy(count) for view, count in zip(views, counts)}
        self.calls = []

    def post(self, endpoint, payload):
        if endpoint != '/v1/responses/input_tokens' or token(payload) not in self.known:
            raise AssertionError('Only an exact captured count view may be replayed offline')
        self.calls.append(deepcopy(payload))
        return deepcopy(self.known[token(payload)])


class PortableInputCeilingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='author-input16-inert-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def request(self):
        return {'model': 'gpt-6.1-sol', 'reasoning': {'effort': 'high'}, 'instructions': 'Unchanged',
            'tools': [], 'tool_choice': 'auto', 'input': [{'role': 'user', 'content': 'x'*25000}]}

    def test_synthetic_exact64000_fits_64001_fails_no_generation(self):
        request = self.request()
        before = deepcopy(request)
        for count, passes in ((64000, True), (64001, False)):
            folder = self.root/str(count)
            folder.mkdir()
            client = Mock()
            client.post.return_value = {'input_tokens': count, 'synthetic_fixture': True}
            if passes:
                result = context.pack(client, request, {'max_input_tokens': 64000}, folder, 7)
                self.assertEqual(token(result), token(before))
            else:
                with self.assertRaises(BudgetStop):
                    context.pack(client, request, {'max_input_tokens': 64000}, folder, 7)
            self.assertTrue(all(call.args[0] == '/v1/responses/input_tokens'
                                for call in client.post.call_args_list))
            self.assertLessEqual(client.post.call_count, 4)
        self.assertEqual(token(request), token(before))

    def test_synthetic_malformed_counts_fail_closed_not_coerced(self):
        for index, count in enumerate((True, 64000.0, '64000', -1)):
            folder = self.root/str(index)
            folder.mkdir()
            client = Mock()
            client.post.return_value = {'input_tokens': count, 'synthetic_fixture': True}
            with self.subTest(type=type(count).__name__), self.assertRaises(ValueError):
                context.pack(client, self.request(), {'max_input_tokens': 64000}, folder, 7)
            self.assertEqual(client.post.call_count, 1)

    def construct(self, role, limits):
        name = role.role
        value = dict(schema=f'earnings_capacity_{name}_transport_v1', source_commit='a'*40,
            root=str(self.root), rates=dict(api_model='gpt-6.1-sol', effort=ROLE_EFFORTS[name],
            input='2', cached='.1', write='2.5', output='10'), limits=limits,
            cutoff_utc='2099-01-01T00:00:00Z', cutoff_monotonic=time.monotonic()+60,
            slots=[str(self.root/'roles'/f'{name}-01')])
        path = self.root/f'{name}-{len(list(self.root.glob("*.json")))}.json'
        binding = engine.save(path, value)
        broker = Mock()
        broker.definitions = [function('synthetic', 'Inert fixture', {})]
        factory, budget = Mock(), Mock()
        result = role(binding, broker=broker, budget=budget, client_factory=factory)
        factory.assert_not_called()
        self.assertEqual(budget.mock_calls, [])
        return result

    def test_current_author96000_boundary_exact_integer_and_other_caps(self):
        limits = role_limits()['author']
        self.assertEqual(limits, {'max_input_tokens': 96000, 'max_output_tokens': 49152, 'wall_seconds': 1200})
        self.assertEqual(self.construct(OpenAuthor, limits).context['limits'], limits)
        self.assertEqual(self.construct(OpenAuthor, dict(limits, max_input_tokens=48000)).context['limits']['max_input_tokens'], 48000)
        for value in (96001, 96000.0, True, '96000'):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ValueError):
                self.construct(OpenAuthor, dict(limits, max_input_tokens=value))
        for key, value in (('max_output_tokens', 49153), ('wall_seconds', 1201)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.construct(OpenAuthor, dict(limits, **{key: value}))

    def test_other_role_settings_efforts_and_no_extra_input_headroom(self):
        expected = {'controller': {'max_input_tokens': 32000, 'max_output_tokens': 16384, 'wall_seconds': 900},
                    'review': {'max_input_tokens': 32000, 'max_output_tokens': 16384, 'wall_seconds': 900}}
        self.assertEqual(ROLE_EFFORTS, {'controller': 'max', 'author': 'high', 'review': 'max', 'forecast': 'max'})
        for role in (OpenController, PopulationReviewer):
            limits = expected[role.role]
            self.assertEqual(role_limits()[role.role], limits)
            self.construct(role, limits)
            with self.assertRaises(ValueError):
                self.construct(role, dict(limits, max_input_tokens=limits['max_input_tokens']+1))


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_AUTHOR_INPUT16') == '1',
                     'Explicit original16 public/count replay; no historical engine or network')
class Original16SavedCountReplay(unittest.TestCase):
    def test_exact_old48_failure_new64_first_view_and_full_evidence_retention(self):
        request, completion, views, counts = saved16()
        untouched = deepcopy(request)
        first_user_digest = token(request['input'][0])
        first_packet = strict_json(request['input'][0]['content'])
        failure = first_packet['research_context']['prior_delivery_failure']
        failed_delta = failure['public_failed_delta']
        self.assertEqual(set(failed_delta), {'decision_sha256', 'parent_source_sha256', 'edits', 'test_text'})
        self.assertTrue(failed_delta['edits'] and failed_delta['test_text'])
        failed_delta_digest = token(failed_delta)
        parent_call = next(x['call_id'] for x in request['input']
                           if x.get('type') == 'function_call' and x.get('name') == 'read_current_program')
        original_parent_output = public_outputs(request)[parent_call]
        self.assertEqual(hashlib.sha256(original_parent_output.encode()).hexdigest(),
                         '3e067b1efdb665cea04348c767f320dee54d2a348088394c0fa82dcfa9d3e29d')
        for ceiling in (48000, 64000):
            with tempfile.TemporaryDirectory(prefix=f'author16-count-{ceiling}-') as folder:
                client = SavedCountClient(views, counts)
                if ceiling == 48000:
                    with self.assertRaises(BudgetStop):
                        context.pack(client, request, {'max_input_tokens': ceiling}, Path(folder), 7,
                                     completion_request=completion)
                    self.assertEqual([token(x) for x in client.calls], [token(x) for x in views])
                    self.assertEqual([counts[i]['input_tokens'] for i in range(len(client.calls))], list(COUNTS))
                else:
                    selected = context.pack(client, request, {'max_input_tokens': ceiling}, Path(folder), 7,
                                            completion_request=completion)
                    self.assertEqual(len(client.calls), 1)
                    self.assertEqual(token(selected), token(request))
                    self.assertEqual(64000-counts[0]['input_tokens'], 12200)
                for observed in client.calls:
                    self.assertEqual(token(observed['input'][0]), first_user_digest)
                    packet = strict_json(observed['input'][0]['content'])
                    self.assertEqual(token(packet['research_context']['prior_delivery_failure']['public_failed_delta']), failed_delta_digest)
                    self.assertEqual(hashlib.sha256(public_outputs(observed)[parent_call].encode()).hexdigest(),
                                     hashlib.sha256(original_parent_output.encode()).hexdigest())
                    self.assertEqual(observed['model'], 'gpt-6.1-sol')
                    self.assertEqual(observed['reasoning'], {'effort': 'high'})
                    self.assertEqual(token(observed['tools']), token(request['tools']))
        self.assertEqual(token(request), token(untouched))
        self.assertFalse((ROOT16/'07-request.json').exists())
        self.assertFalse((ROOT16/'07-response.json').exists())

    def test_saved_count_lookup_refuses_changed_payload_no_invented_api_reply(self):
        request, _, views, counts = saved16()
        client = SavedCountClient(views, counts)
        request['model'] = 'different-model'
        with self.assertRaises(AssertionError):
            client.post('/v1/responses/input_tokens', request)
        with self.assertRaises(AssertionError):
            client.post('/v1/responses', views[0])
        self.assertEqual(client.calls, [])


if __name__ == '__main__':
    unittest.main()
