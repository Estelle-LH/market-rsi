"""Replay exact closed21 input counts; never count or generate on a provider.

The saved request is opaque except for its public user/tool evidence. Production
packing writes only temporary test artifacts. No QA, ledger or model execution.
"""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from edgar_forecast_budget import BudgetStop
from earnings_http import strict_json
import earnings_open_context as context
from earnings_open_resources import role_limits
from market_rsi import digest
from test_earnings_population_author_input16 import SavedCountClient, public_outputs, token


ROOT = Path('/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/'
            'edgar-population-20261016/attempts/edgar-population-20261016-21/roles/author-01')
CAPTURES = (
    (1, 66307, '73268ab47b7e277046fb25a741ba8e7882f89bbd49b7463c133a190126fc1d6e',
     'e5dbb6f5a563f7acf1a04df7dda275c794c09941fabb178f001e0f3b9e0e041a'),
    (4, 67013, 'd0888c53744b498bb8d1abf95a94ad9a080842896e7cb9dd0fd6086aab8b5d7a',
     'd65f15f93dcf1d66f6cc4d99efe725f9224daf49339c85245d05a8b0bf013bc9'))


def saved21():
    intents = []
    for path in ROOT.glob('http-*.intent.json'):
        value = strict_json(path.read_bytes())
        if value.get('endpoint') == '/v1/responses/input_tokens':
            intents.append((path, value))
    views, counts, preparations = [], [], []
    for step, count, prep_sha, count_sha in CAPTURES:
        prefix = ROOT/f'03-context-{step:02d}'
        prep_raw = prefix.with_suffix('.json').read_bytes()
        count_raw = Path(str(prefix)+'-count.json').read_bytes()
        if (hashlib.sha256(prep_raw).hexdigest() != prep_sha
                or hashlib.sha256(count_raw).hexdigest() != count_sha):
            raise ValueError('Exact sealed21 count/preparation bytes required')
        prep, counted = strict_json(prep_raw), strict_json(count_raw)
        matches = [(path, value) for path, value in intents
                   if token(value['payload']) == prep['effective_request_sha256']]
        if len(matches) != 1 or counted['input_tokens'] != count:
            raise ValueError('One physical21 count origin required')
        path, intent = matches[0]
        stem = str(path)[:-len('.intent.json')]
        sidecar = strict_json(Path(stem+'.response.json').read_bytes())
        raw = strict_json(Path(stem+'.raw.bin').read_bytes())
        stripped = dict(sidecar)
        stripped.pop('_request_id', None)
        if sidecar != counted or stripped != raw:
            raise ValueError('Original21 count/raw/response join differs')
        views.append(deepcopy(intent['payload']))
        counts.append(counted)
        preparations.append(prep)
    request = views[0]
    completion = dict(deepcopy(request), instructions=views[-1]['instructions'], tool_choice='none')
    if (token(request) != preparations[0]['original_request_sha256']
            or token(completion) != preparations[-1]['finalization_request_sha256']):
        raise ValueError('Original21 ordinary/final request identities differ')
    return request, completion, views, counts


class Portable96kBoundary(unittest.TestCase):
    def test_exact96k_boundary_preserves_other_resources(self):
        self.assertEqual(role_limits()['author'], dict(max_input_tokens=96000,
                         max_output_tokens=49152, wall_seconds=1200))
        request = dict(model='gpt-6.1-sol', reasoning={'effort':'high'},
                       input=[dict(role='user', content='x'*25000)])
        original = deepcopy(request)
        for count in (96000, 96001):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as folder:
                client = Mock()
                client.post.return_value = dict(input_tokens=count, synthetic_fixture=True)
                if count == 96000:
                    self.assertEqual(context.pack(client, request, role_limits()['author'],
                                                  Path(folder), 1), original)
                else:
                    with self.assertRaises(BudgetStop):
                        context.pack(client, request, role_limits()['author'], Path(folder), 1)
                self.assertTrue(all(call.args[0] == '/v1/responses/input_tokens'
                                    for call in client.post.call_args_list))
                self.assertEqual(request, original)


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_AUTHOR_INPUT21') == '1',
                     'Explicit read-only own21 saved-count replay')
class Original21CountReplay(unittest.TestCase):
    def test_old64_fails_new96_keeps_exact_base_patch_and_both_real_returns(self):
        request, completion, views, counts = saved21()
        original = deepcopy(request)
        packet = strict_json(request['input'][0]['content'])
        delta = packet['research_context']['prior_delivery_failure']['public_failed_delta']
        self.assertEqual(digest(delta), '995fa166e77b3d93cb5d32531dc39bd117802d6b28af157cfc268cc0d952472e')
        self.assertEqual(len(delta['edits']), 12)
        self.assertEqual(len(delta['test_text'].encode()), 15129)
        self.assertEqual(len(packet['implementation_base_source_text'].encode()), 63490)
        outputs = public_outputs(request)
        self.assertEqual(sorted(len(value.encode()) for value in outputs.values()), [9053, 43446])
        self.assertEqual(set(hashlib.sha256(value.encode()).hexdigest() for value in outputs.values()), {
            '10fb2fc65f92bf4edd51e17835a0b594306d864d1fd653b3451c2c084e15151d',
            '442822cbe7a046e2f75a930aa87698695720d61dfa544629117d8cdfd6cc7f14'})
        for ceiling in (64000, 96000):
            with self.subTest(ceiling=ceiling), tempfile.TemporaryDirectory() as folder:
                client = SavedCountClient(views, counts)
                if ceiling == 64000:
                    with self.assertRaises(BudgetStop):
                        context.pack(client, request, {'max_input_tokens':ceiling}, Path(folder), 3,
                                     completion_request=completion)
                    self.assertEqual([token(x) for x in client.calls], [token(x) for x in views])
                else:
                    packed = context.pack(client, request, {'max_input_tokens':ceiling}, Path(folder), 3,
                                          completion_request=completion)
                    self.assertEqual(packed, original)
                    self.assertEqual(len(client.calls), 1)
                    self.assertEqual(public_outputs(packed), outputs)
                    self.assertEqual(token(strict_json(packed['input'][0]['content'])[
                        'research_context']['prior_delivery_failure']['public_failed_delta']), token(delta))
                self.assertEqual(request, original)


if __name__ == '__main__':
    unittest.main()
