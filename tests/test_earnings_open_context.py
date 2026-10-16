"""Offline context preparation, not provider success or predictive evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from earnings_open_context import encoded,pack,project
from edgar_forecast_budget import BudgetStop


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.request={'instructions':'unchanged','tools':[{'name':'synthetic'}],
            'input':[{'role':'user','content':'immutable packet'},
                {'type':'function_call','call_id':'call1','name':'inspect_trace','arguments':'{}'},
                {'type':'function_call_output','call_id':'call1','output':'界'*20000}]}
        self.original=deepcopy(self.request);self.client=Mock()
        self.limits={'max_input_tokens':10000}

    def test_only_observations_projected_originals_unchanged(self):
        result,receipt=project(self.request,100)
        self.assertEqual(self.request,self.original)
        self.assertEqual(result['input'][:2],self.original['input'][:2])
        self.assertEqual(result['tools'],self.original['tools'])
        body=json.loads(result['input'][2]['output'])
        self.assertTrue(body['truncated']);self.assertEqual(body['original_output_bytes'],60000)
        self.assertEqual(body['original_output_sha256'],hashlib.sha256(('界'*20000).encode()).hexdigest())
        self.assertEqual(receipt[0]['call_id'],'call1')

    def test_actual_overflow_prepared_before_any_generation(self):
        self.client.post.side_effect=[{'input_tokens':23027},{'input_tokens':7200}]
        result=pack(self.client,self.request,self.limits,self.root,2)
        self.assertEqual(self.client.post.call_count,2)
        self.assertTrue(all(call.args[0]=='/v1/responses/input_tokens' for call in self.client.post.call_args_list))
        self.assertTrue(json.loads(result['input'][2]['output'])['truncated'])
        self.assertEqual(self.request,self.original)
        self.assertEqual(len(list(self.root.glob('*-count.json'))),2)

    def test_already_fitting_count_keeps_exact_request(self):
        self.client.post.return_value={'input_tokens':9000}
        self.assertEqual(pack(self.client,self.request,self.limits,self.root,1),self.original)
        self.assertEqual(self.client.post.call_count,1)

    def test_unfit_model_authored_source_fails_without_rewriting_or_generation(self):
        self.request['input'][1]['arguments']='authored source '*4000
        self.client.post.return_value={'input_tokens':20000}
        with self.assertRaises(BudgetStop):pack(self.client,self.request,self.limits,self.root,1)
        self.assertLessEqual(self.client.post.call_count,4)
        for call in self.client.post.call_args_list:
            self.assertEqual(call.args[1]['input'][1],self.request['input'][1])

    def test_count_failure_not_retried_and_no_bad_count_accepted(self):
        self.client.post.side_effect=TimeoutError('synthetic')
        with self.assertRaises(TimeoutError):pack(self.client,self.request,self.limits,self.root,1)
        self.assertEqual(self.client.post.call_count,1)
        self.client.post.side_effect=None;self.client.post.return_value={'input_tokens':True}
        with self.assertRaises(ValueError):pack(self.client,self.request,self.limits,self.root,2)

    def test_small_request_retains_original_count_path(self):
        self.request['input'][2]['output']='small'
        self.assertEqual(pack(self.client,self.request,self.limits,self.root,1),self.request)
        self.client.post.assert_not_called()


if __name__=='__main__':unittest.main()
