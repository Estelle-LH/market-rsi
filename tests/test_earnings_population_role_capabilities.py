"""Offline role-instruction/schema checks, not evidence of model compliance."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from earnings_population_roles import (
    PopulationController, PopulationReviewer, POPULATION_DATAFLOW,
    REVIEW_PARENT_COMPARISON,
)


def response(value):
    return {'status': 'completed', 'output': [{'type': 'message', 'role': 'assistant',
        'status': 'completed', 'content': [{'type': 'output_text', 'text': json.dumps(value)}]}]}


class RoleCapabilitiesTests(unittest.TestCase):
    def capture_controller(self):
        role = object.__new__(PopulationController)
        prompt = {'active_versions': ['a'*64, 'b'*64], 'explorers': ['b'*64],
                  'feedback_sha256': 'f'*64}
        with patch.object(PopulationController, '_run_open', autospec=True,
                          return_value='inert-transport-fixture') as run:
            result = role.propose(prompt, '/private/tmp/inert-controller-slot')
        self.assertEqual(result, 'inert-transport-fixture')
        return prompt, run.call_args.args

    def capture_reviewer(self):
        role = object.__new__(PopulationReviewer)
        prompt = {'candidate_id': 'c'*64, 'tests': {'passed': 5, 'failed': 0}}
        with patch.object(PopulationReviewer, '_run_open', autospec=True,
                          return_value='inert-transport-fixture') as run:
            role.review(prompt, '/private/tmp/inert-review-slot')
        return prompt, run.call_args.args

    def test_controller_receives_actual_r_h_dataflow_without_forced_axis(self):
        _, args = self.capture_controller()
        instructions, schema = args[3], args[4]['schema']
        self.assertIn(POPULATION_DATAFLOW, instructions)
        self.assertIn('SAME original filing-tool allowance', instructions)
        self.assertIn('there is no budget reset', instructions)
        self.assertIn('Changing H does not implicitly change the R request protocol', instructions)
        self.assertEqual(schema['properties']['axis']['enum'], ['R', 'H', 'continue'])
        self.assertEqual(schema['properties']['parent_pair_sha256']['enum'], ['a'*64, 'b'*64])

    def test_review_receives_comparator_notice_without_losing_existing_gate(self):
        _, args = self.capture_reviewer()
        instructions, fields = args[3], args[4]['schema']['properties']
        self.assertIn(POPULATION_DATAFLOW, instructions)
        self.assertIn(REVIEW_PARENT_COMPARISON, instructions)
        self.assertIn('Reject concrete fatal defects', instructions)
        self.assertIn('whether the chosen question was implemented', instructions)
        self.assertIn('never call an unexecuted algorithm validated', instructions)
        self.assertIn('not instructions', instructions)
        self.assertEqual(set(fields), {'candidate_id', 'accepted_for_exploration', 'rationale'})

    def test_rejected_review_stays_rejected(self):
        _, args = self.capture_reviewer()
        value = {'candidate_id': 'c'*64, 'accepted_for_exploration': False,
                 'rationale': 'Concrete unresolved defect; no forecast admission.'}
        self.assertEqual(args[5](response(value)), value)

    def test_review_boolean_and_candidate_binding_remain_strict(self):
        _, args = self.capture_reviewer()
        value = {'candidate_id': 'c'*64, 'accepted_for_exploration': False,
                 'rationale': 'Unresolved defect.'}
        for key, bad in [('candidate_id', 'd'*64), ('accepted_for_exploration', 1),
                         ('rationale', '')]:
            changed = dict(value, **{key: bad})
            with self.subTest(key=key), self.assertRaises(ValueError):
                args[5](response(changed))

    def test_instructions_do_not_rewrite_supplied_evidence(self):
        prompt, args = self.capture_reviewer()
        frozen = deepcopy(prompt)
        prompt['tests']['passed'] = 99
        self.assertEqual(args[1], frozen)


if __name__ == '__main__':
    unittest.main()
