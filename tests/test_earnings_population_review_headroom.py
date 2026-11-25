"""Reviewer capacity only: controlled counts/transport, not a paid model review."""
from copy import deepcopy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from edgar_forecast_budget import BudgetStop
from edgar_forecast_openai import PreparedCount
from edgar_forecast_tools import function
import earnings_open_context as packing
import earnings_open_resources as resources
import earnings_open_roles as roles
from earnings_loop_policy import LIMITS
from earnings_population_roles import PopulationReviewer


OBSERVED05_TOKENS = 14616  # Original saved count, not a new provider measurement.


class ReviewHeadroomTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.serial = 0

    def request(self):
        return {'model': 'gpt-6.1-sol', 'reasoning': {'effort': 'max'},
            'instructions': 'Unchanged synthetic independent review instructions',
            'tools': [], 'tool_choice': 'none', 'parallel_tool_calls': False,
            'text': {'format': {'name': 'earnings_population_review_v1'}},
            'input': [{'role': 'user', 'content': 'immutable-public-evidence-'*2000}]}

    def packed(self, count, ceiling):
        self.serial += 1
        output = self.root/('pack-'+str(self.serial)); output.mkdir()
        client = Mock(); client.post.return_value = {'input_tokens': count, 'synthetic_count': True}
        request = self.request(); before = deepcopy(request)
        try:
            result = packing.pack(client, request, {'max_input_tokens': ceiling}, output, 1)
        finally:
            self.assertEqual(request, before)
            self.assertEqual(client.post.call_count, 1)  # Immutable views deduplicate.
            endpoint, sent = client.post.call_args.args
            self.assertEqual(endpoint, '/v1/responses/input_tokens')
            self.assertEqual(sent, before)
        return result, before

    def reviewer(self, limits, count=OBSERVED05_TOKENS):
        self.serial += 1
        slot = self.root/'roles'/('review-'+str(self.serial))
        context = {'schema': 'earnings_capacity_review_transport_v1', 'source_commit': 'a'*40,
            'root': str(self.root), 'rates': {'api_model': 'gpt-6.1-sol', 'effort': 'max',
                'input': '2', 'cached': '0.1', 'write': '2.5', 'output': '10'},
            'limits': deepcopy(limits), 'slots': [str(slot)],
            'cutoff_utc': (dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'cutoff_monotonic': time.monotonic()+1200}
        path = self.root/('context-'+str(self.serial)+'.json')
        roles.e.durable_json(path, context)
        binding = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        budget = Mock(monotonic_deadline=time.monotonic()+1200)
        budget.summary.return_value = {'synthetic': True, 'production_accounting_tested': False}
        client = Mock(timeout=20)
        client.post.return_value = {'input_tokens': count, 'synthetic_count': True}
        factory = Mock(return_value=client)
        broker = Mock(definitions=[function('inspect_trace', 'Synthetic public evidence',
            {'slot': {'type': 'string'}})])
        role = PopulationReviewer(binding, budget=budget, client_factory=factory, broker=broker, max_turns=1)
        return role, slot, client, factory

    def invoke(self, limits, count=OBSERVED05_TOKENS, expect_failure=False):
        role, slot, client, _ = self.reviewer(limits, count)
        prompt = {'candidate_id': 'f'*64, 'public_evidence': 'immutable-public-evidence-'*2000}
        generated = []
        def fake_paid(http, request, rates, actual_limits, budget, output, turn, *, prepared_count=None):
            # Original packing is exercised; generation/accounting are invented.
            # This seam does not consume the handle. Its real consumption,
            # reservation and send are tested in prepared_count_handoff tests.
            self.assertIs(type(prepared_count), PreparedCount)
            generated.append(deepcopy(request))
            self.assertEqual(actual_limits, limits)
            body = {'candidate_id': 'f'*64, 'accepted_for_exploration': False,
                'rationale': 'Synthetic delivery only, not scientific review.'}
            response = {'status': 'completed', 'error': None, 'output': [{
                'type': 'message', 'role': 'assistant', 'status': 'completed',
                'content': [{'type': 'output_text', 'text': json.dumps(body)}]}]}
            roles.e.durable_json(output/f'{turn:02d}-request.json', {'payload': request, 'synthetic': True})
            roles.e.durable_json(output/f'{turn:02d}-response.json', response)
            return response
        with patch.object(roles, 'budgeted_response', side_effect=fake_paid):
            if expect_failure:
                with self.assertRaisesRegex(RuntimeError, 'BudgetStop'):
                    role.review(prompt, str(slot))
            else:
                role.review(prompt, str(slot))
        result = json.loads((slot/'result.json').read_bytes())
        self.assertEqual(client.post.call_count, 2 if expect_failure else 1)
        self.assertTrue(all(call.args[0] == '/v1/responses/input_tokens'
                            for call in client.post.call_args_list))
        self.assertEqual(json.loads((slot/'effective-input.json').read_bytes()), prompt)
        if expect_failure:
            self.assertEqual(generated, [])
            self.assertEqual(result['status'], 'FAILED_NO_RETRY')
            self.assertIsNone(result['final_numbered_response'])
        else:
            self.assertEqual(len(generated), 1)
            self.assertEqual(json.loads(generated[0]['input'][0]['content']), prompt)
            self.assertEqual(generated[0]['model'], 'gpt-6.1-sol')
            self.assertEqual(generated[0]['reasoning'], {'effort': 'max'})
            self.assertEqual(result['status'], 'COMPLETED_REVIEW')
            self.assertEqual(json.loads((slot/'01-request.json').read_bytes())['payload'], generated[0])
        self.assertFalse(result['retry_allowed'])
        self.assertEqual(result['tool_calls'], 0)

    def test_prospective_role_ceilings_and_generic_limits_remain_explicit(self):
        limits = resources.role_limits()
        self.assertEqual(limits['review'], dict(LIMITS, max_input_tokens=32000, wall_seconds=900))
        self.assertEqual(limits['controller'], dict(LIMITS, max_input_tokens=32000, wall_seconds=900))
        self.assertEqual(limits['author'], {'max_input_tokens': 96000, 'max_output_tokens': 49152, 'wall_seconds': 1200})
        self.assertEqual(LIMITS, {'max_input_tokens': 10000, 'max_output_tokens': 16384, 'wall_seconds': 600})
        self.assertEqual(resources.ROLE_EFFORTS, {'controller': 'max', 'author': 'high', 'review': 'max', 'forecast': 'max'})
        limits['review']['wall_seconds'] = 1
        self.assertEqual(resources.role_limits()['review']['wall_seconds'], 900)

    def test_observed_count_old_fails_new_fits_without_rewriting_immutable_packet(self):
        with self.assertRaises(BudgetStop): self.packed(OBSERVED05_TOKENS, 10000)
        result, before = self.packed(OBSERVED05_TOKENS, 20000)
        self.assertEqual(result, before)

    def test_exact_fitting_boundary_and_smallest_positive_cap_still_gate(self):
        for ceiling, count in [(14615, 14616), (20000, 20001), (1, 2)]:
            with self.subTest(ceiling=ceiling), self.assertRaises(BudgetStop): self.packed(count, ceiling)
        for ceiling, count in [(14616, 14616), (1, 1)]:
            with self.subTest(ceiling=ceiling):
                result, before = self.packed(count, ceiling); self.assertEqual(result, before)

    def test_invalid_review_limits_refused_before_factory_or_transport(self):
        for delta in [{'max_input_tokens': 0}, {'max_input_tokens': True}, {'max_input_tokens': 32001},
                      {'max_output_tokens': 16385}, {'wall_seconds': 901}]:
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                self.reviewer(dict(resources.role_limits()['review'], **delta))

    def test_real_role_pack_path_delivers_observed_size_under_new_ceiling(self):
        self.invoke(resources.role_limits()['review'])

    def test_real_role_old_ceiling_fails_before_generation(self):
        self.invoke(deepcopy(LIMITS), expect_failure=True)

    def test_legacy_explicit_10k_context_still_works_when_payload_fits(self):
        self.invoke(deepcopy(LIMITS), count=9999)

    def test_real_role_new_cap_does_not_admit_larger_payload_or_retry(self):
        self.invoke(resources.role_limits()['review'], count=32001, expect_failure=True)


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_REVIEW05_HEADROOM') == '1',
                     'Explicit read-only closed05 public transport audit opt-in required')
class Actual05PublicCount(unittest.TestCase):
    def test_saved_immutable_count_and_failure_are_exact_not_new_measurements(self):
        root = Path('/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/edgar-population-20261016/attempts/edgar-population-20261016-05/roles/review-01')
        expected = {'effective-input.json': '8e2d41e4da79f47739e5af679034fa4ccf54076ff2d4f8ab816fc8fa7999e3b6',
            '01-context-01-count.json': '315389afc03eff7bfb611c8d63c9d64f053608604a5c7e13b1bce9392486c696',
            'result.json': '89368d15e19b4143e918a1383787c47ad55a9b0b8f608e80b94564ce52aa2507'}
        saved = {}
        for name, token in expected.items():
            raw = (root/name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), token); saved[name] = json.loads(raw)
        count = saved['01-context-01-count.json']['input_tokens']
        self.assertEqual(count, OBSERVED05_TOKENS)
        self.assertGreater(count, LIMITS['max_input_tokens'])
        self.assertLessEqual(count, resources.role_limits()['review']['max_input_tokens'])
        self.assertEqual(saved['result.json']['error_type'], 'BudgetStop')
        self.assertEqual(saved['result.json']['tool_calls'], 0)
        self.assertIsNone(saved['result.json']['final_numbered_response'])
        self.assertIn('original_public_empty_state_probes', saved['effective-input.json'])


if __name__ == '__main__': unittest.main()
