"""Pure public-proposal decoder parity; no role execution or network."""
from copy import deepcopy
import json
import unittest

from earnings_population_roles import decode_proposal


class ProposalDecoderTests(unittest.TestCase):
    def setUp(self):
        self.prompt = dict(active_versions=['a'*64, 'b'*64, 'c'*64],
                           explorers=['b'*64, 'c'*64], feedback_sha256='d'*64)
        self.choice = dict(schema='earnings_capacity_decision_v1', axis='R',
            component='research_policy', parent_pair_sha256='b'*64,
            feedback_sha256='d'*64, hypothesis='Repair real evidence acquisition.',
            expected_effect='Preserve correct fallback while reading full tables.',
            retire_branch_id='c'*64)

    def raw(self, value=None):
        return dict(status='completed', error=None, output=[dict(type='message', role='assistant',
            status='completed', content=[dict(type='output_text', text=json.dumps(
                self.choice if value is None else value))])])

    def test_exact_public_decode_leaves_inputs_unchanged(self):
        raw = self.raw(); original = deepcopy((raw, self.prompt))
        self.assertEqual(decode_proposal(raw, self.prompt), self.choice)
        self.assertEqual((raw, self.prompt), original)

    def test_none_only_normalizes_retirement_when_no_replacement_needed(self):
        self.prompt['explorers'] = ['b'*64]
        self.choice['retire_branch_id'] = 'none'
        expected = {k:v for k,v in self.choice.items() if k != 'retire_branch_id'}
        self.assertEqual(decode_proposal(self.raw(), self.prompt), expected)

    def test_stale_parent_feedback_retirement_and_extra_fields_reject(self):
        for changes in ({'parent_pair_sha256':'e'*64}, {'feedback_sha256':'e'*64},
                        {'retire_branch_id':'a'*64}, {'retire_branch_id':'none'},
                        {'extra':'not a proposal field'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                decode_proposal(self.raw(dict(self.choice, **changes)), self.prompt)

    def test_noncompleted_multi_message_and_tools_reject(self):
        raw = self.raw()
        variants = [dict(raw, status='incomplete'), dict(raw, error={'message':'bad'}),
                    dict(raw, output=raw['output']*2),
                    dict(raw, output=[dict(type='function_call')]), dict(raw, output=[])]
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ValueError):
                decode_proposal(value, self.prompt)

    def test_assignment_scope_remains_the_original_decoder_rule(self):
        self.prompt['repair_assignment'] = dict(parent_version_id='b'*64)
        self.assertEqual(decode_proposal(self.raw(), self.prompt), self.choice)
        value = dict(self.choice, axis='H', component='tool_interface')
        with self.assertRaises(ValueError):
            decode_proposal(self.raw(value), self.prompt)


if __name__ == '__main__':
    unittest.main()
