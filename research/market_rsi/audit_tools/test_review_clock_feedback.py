import copy
import unittest
from review_clock_feedback import exact_object,closure_example
from test_causal_event_samples import C


def fixture():
    inv={'host':'authorized','source_root':'/raw','files':[{'filename':'hour.zst','date':'2026-08-21','compressed_bytes':10}]}
    req={'exact_objects':[{'host':'authorized','source_root':'/raw','relative_path':'hour.zst','date':'2026-08-21','advertised_bytes':10}],
        'max_input_bytes':10,'max_decoded_bytes':100,'wall_seconds':600,'memory_bytes':1024}
    return req,inv


class ReviewTests(unittest.TestCase):
    def test_exact_inventory_not_remote_proof(self):
        v=exact_object(*fixture());self.assertEqual(v['path'],'/raw/hour.zst')
        self.assertFalse(v['current_remote_availability_verified'])
    def test_different_host_rejected(self):
        r,i=fixture();r['exact_objects'][0]['host']='other'
        with self.assertRaises(ValueError):exact_object(r,i)
    def test_path_escape_rejected(self):
        r,i=fixture();r['exact_objects'][0]['relative_path']='../hour.zst'
        with self.assertRaises(ValueError):exact_object(r,i)
    def test_size_change_rejected(self):
        r,i=fixture();r['exact_objects'][0]['advertised_bytes']=11
        with self.assertRaises(ValueError):exact_object(r,i)
    def test_scope_expansion_rejected(self):
        r,i=fixture();r['exact_objects']*=2
        with self.assertRaises(ValueError):exact_object(r,i)
    def test_resource_overrun_rejected(self):
        r,i=fixture();r['wall_seconds']=601
        with self.assertRaises(ValueError):exact_object(r,i)
    def test_exact_endpoint_still_needs_closure(self):
        v=closure_example(copy.deepcopy(C))
        self.assertFalse(v['target_extends_past_last_observation'])
        self.assertFalse(v['typed_kernel_label']['available'])
        self.assertEqual(v['typed_kernel_label']['reason'],'unbounded_tail')


if __name__=='__main__':unittest.main()
