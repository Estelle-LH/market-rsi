import copy
import unittest
from audit_validation_design_result import verify_turn, response_calls
from codex_glm_provider import CHAT_TEMPLATE_SHA256, HF_MODEL, TOKENIZER_REVISION
from glm_canary import MODEL, RATES
from market_rsi import digest


class ValidationReceiptTests(unittest.TestCase):
    def setUp(self):
        self.request = {'token_ids': [1,2,3], 'input_tokens': 3, 'tokenizer_repo': HF_MODEL,
            'tokenizer_revision': TOKENIZER_REVISION, 'chat_template_sha256': CHAT_TEMPLATE_SHA256}
        receipt = {'prompt_tokens': 3, 'output_tokens': 2, 'cache_hit_prompt_tokens': 1,
            'model': MODEL, 'rates': RATES, 'provider': 'tinker', 'terminal': True,
            'metered_cost_usd': '0.000034992'}
        self.response = {'tokens': [4,5], 'receipt': receipt}
        self.job = {'state': 'metered_terminal', 'bucket': 'learning',
            'metered_usd': '0.000034992', 'input_sha256': digest([1,2,3]), 'receipt_sha256': digest(receipt)}

    def test_frozen_rates_independently_reproduce_charge(self):
        self.assertEqual(str(verify_turn(self.request, self.response, self.job)), '0.000034992')

    def test_reserved_amount_never_treated_as_spent(self):
        self.job['state'] = 'reserved'
        with self.assertRaisesRegex(ValueError, 'metered cost'):
            verify_turn(self.request, self.response, self.job)

    def test_output_length_tamper_rejected(self):
        self.response['tokens'].append(6)
        with self.assertRaisesRegex(ValueError, 'token lengths'):
            verify_turn(self.request, self.response, self.job)

    def test_invoice_or_receipt_replacement_not_silent(self):
        self.job['receipt_sha256'] = 'b' * 64
        with self.assertRaisesRegex(ValueError, 'receipt binding'):
            verify_turn(self.request, self.response, self.job)

    def test_fixture_tokenizer_rejected_as_real_model(self):
        self.request['tokenizer_repo'] = 'fixture'
        with self.assertRaisesRegex(ValueError, 'tokenizer identity'):
            verify_turn(self.request, self.response, self.job)

    def test_single_and_parallel_replies_both_audited(self):
        one = '<tool_call>mcp__controller_tools__inspect_validation_context</tool_call>'
        self.assertEqual(len(response_calls(one)), 1)
        self.assertEqual(len(response_calls(one + one)), 2)

    def test_narrative_is_not_a_tool_submission(self):
        with self.assertRaisesRegex(ValueError, 'submitted tool calls'):
            response_calls('I submitted it.')


if __name__ == '__main__':
    unittest.main()
