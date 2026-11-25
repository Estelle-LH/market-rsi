"""Observed06 count regression; synthetic counts are not a new model send."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from edgar_forecast_budget import BudgetStop
from earnings_open_context import pack
from earnings_open_resources import role_limits
from earnings_loop_policy import LIMITS
from test_earnings_population_controller_headroom import DECISION_FIELDS


class Controller32k(unittest.TestCase):
    def packed(self, count, ceiling):
        request = {'model':'gpt-6.1-sol', 'tool_choice':'auto', 'instructions':'unchanged',
            'text':{'format':{'name':'earnings_population_decision_v1',
                            'schema':{'properties':{k:{'type':'string'} for k in DECISION_FIELDS}}}},
            'input':[{'role':'user','content':'immutable diagnosis '*2000},
                {'type':'function_call','name':'read_prior_file','call_id':'current',
                 'arguments':json.dumps({'path':'filings/original.md','offset':0,'characters':6400})},
                {'type':'function_call_output','call_id':'current',
                 'output':json.dumps({'value':{'text':'PUBLIC_TABLE_'+'x'*6400}})}]}
        before = deepcopy(request); client = Mock()
        client.post.return_value = {'input_tokens':count,'synthetic_count':True}
        with tempfile.TemporaryDirectory() as home:
            try:
                result = pack(client, request, {'max_input_tokens':ceiling}, Path(home), 1)
            finally:
                self.assertEqual(request, before)
        return result, before

    def test_new_capacity_keeps_exact_latest_real_file_sized_output(self):
        result, original = self.packed(17457, role_limits()['controller']['max_input_tokens'])
        self.assertEqual(result, original)
        self.assertIn('PUBLIC_TABLE_', result['input'][-1]['output'])

    def test_original16k_failure_is_not_silently_rewritten_or_retried(self):
        with self.assertRaises(BudgetStop): self.packed(16122, 16000)

    def test_new_bound_and_legacy_explicit_fitting_context_still_enforced(self):
        with self.assertRaises(BudgetStop): self.packed(32001, 32000)
        result, original = self.packed(15999, 16000)
        self.assertEqual(result, original)

    def test_only_controller_input_changes_in_this_checkpoint(self):
        self.assertEqual(role_limits()['controller'], dict(LIMITS,max_input_tokens=32000))
        self.assertEqual(role_limits()['review'], dict(LIMITS,max_input_tokens=20000))
        self.assertEqual(role_limits()['author']['max_output_tokens'],49152)
        self.assertEqual(role_limits()['author']['wall_seconds'],900)
        self.assertEqual(LIMITS,{'max_input_tokens':10000,'max_output_tokens':16384,'wall_seconds':600})


@unittest.skipUnless(os.environ.get('MARKET_RSI_VERIFY_CONTROLLER06_HEADROOM')=='1',
                     'Explicit read-only closed06 count replay opt-in required')
class Actual06Count(unittest.TestCase):
    def test_original_counts_show_latest6400_cannot_fit16k(self):
        root=Path('/__LOCAL_RESEARCH_HOME__/.codex/worktrees/3c5e/self-evolving-v18-local/artifacts/edgar-population-20261016/attempts/edgar-population-20261016-06/roles/controller-01')
        expected=[13663,15619,17457,16773,16287,16122]
        names=['01-context-01-count.json','02-context-01-count.json',
               *[f'03-context-{i:02d}-count.json' for i in range(1,5)]]
        self.assertEqual([json.loads((root/n).read_text())['input_tokens'] for n in names],expected)
        self.assertEqual(len(list(root.glob('[0-9][0-9]-request.json'))),2)
        self.assertEqual(len(list(root.glob('[0-9][0-9]-response.json'))),2)
        self.assertEqual(json.loads((root/'result.json').read_text())['error_type'],'BudgetStop')
        self.assertGreater(min(expected[2:]),16000)
        self.assertLess(max(expected),role_limits()['controller']['max_input_tokens'])


if __name__=='__main__': unittest.main()
