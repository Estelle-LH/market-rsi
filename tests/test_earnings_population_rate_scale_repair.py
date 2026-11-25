"""Finite once68 admission guards; AST/data only, never execute candidates."""
from copy import deepcopy
from unittest.mock import patch
import unittest
import earnings_population_clean_slate as c
from supervisor_harness import capacity_feedback_engine as e

class OnceRateScaleRepair(unittest.TestCase):
    def setUp(self):
        self.binding=e.pin(c.training.ROOT/'clean67-rate-scale-repair/repair-review-final.json')
        self.fixed=e.read(self.binding)

    def call(self,fixed=None,validation=None):
        original=e.read
        def read(bound):
            if bound==self.binding and fixed is not None:return fixed
            if bound==self.fixed['validation'] and validation is not None:return validation
            return original(bound)
        with patch.object(e,'read',side_effect=read):
            return c.repair_metadata(self.binding,c.RATE_SCALE_REVIEW_ID)

    def test_exact_authorized_descriptor(self):
        value=self.call();self.assertEqual(value['candidate']['parent'],value['original_candidate']['id'])
        self.assertEqual(value['candidate']['H'],value['original_candidate']['H'])

    def test_next_id_is_not_an_auto_retry_permission(self):
        with self.assertRaises(ValueError):c.repair_metadata(self.binding,'edgar-population-20261016-69')

    def test_68_cannot_use_legacy_or_missing_marker(self):
        for marker in (1,2,4,None,True,3.0):
            with self.assertRaises(ValueError):c._rate_scale_route(c.RATE_SCALE_REVIEW_ID,marker,True)
        c._rate_scale_route(c.RATE_SCALE_REVIEW_ID,3,True)

    def test_68_cannot_be_a_normal_CA_proposal(self):
        with self.assertRaises(ValueError):c._rate_scale_route(c.RATE_SCALE_REVIEW_ID,3,False)
        c._rate_scale_route('edgar-population-20261016-69',3,False)

    def test_wrong_descriptor_path(self):
        with self.assertRaises(ValueError):c.repair_metadata(dict(self.binding,path='/unknown/repair.json'),c.RATE_SCALE_REVIEW_ID)

    def test_strategy_change_rejected(self):
        value=deepcopy(self.fixed);value['candidate']['method']='a new strategy'
        with self.assertRaises(ValueError):self.call(value)

    def test_H_change_rejected(self):
        value=deepcopy(self.fixed);value['candidate']['H']=value['candidate']['R']
        with self.assertRaises(ValueError):self.call(value)

    def test_parent_relabel_rejected(self):
        value=deepcopy(self.fixed);value['candidate']['parent']='21c5'
        with self.assertRaises(ValueError):self.call(value)

    def test_extra_function_change_rejected(self):
        original=c.e.checked
        def checked(bound):
            data=original(bound)
            return data+b'\ndef unauthorized_extra():\n return 1\n' if bound==self.fixed['candidate']['R'] else data
        with patch.object(c.e,'checked',side_effect=checked):
            with self.assertRaisesRegex(ValueError,'Only rate'):self.call()

    def test_missing_or_failed_boundary_case_rejected(self):
        value=e.read(self.fixed['validation']);value['extra_isolated_tests'].pop()
        with self.assertRaises(ValueError):self.call(validation=value)
        value=e.read(self.fixed['validation']);value['extra_isolated_tests'][0]['passed']=False
        with self.assertRaises(ValueError):self.call(validation=value)

    def test_host_candidate_or_paid_validation_rejected(self):
        for field,value in [('host_candidate_execution',True),('model_calls',1),('ledger_writes',1),('heldout_read',True)]:
            v=e.read(self.fixed['validation']);v[field]=value
            with self.assertRaises(ValueError):self.call(validation=v)

    def test_legacy_authorities_not_replaced(self):
        self.assertNotEqual(c.repair_authority(c.RATE_SCALE_REVIEW_ID),c.REPAIR_AUTHORITY)
        self.assertEqual(c.repair_authority(c.ANCHOR_REVIEW_ID),c.ANCHOR_REPAIR_AUTHORITY)
        self.assertEqual(c.repair_authority(c.CONCISE_REVIEW_ID),c.REPAIR_AUTHORITY)

if __name__=='__main__':unittest.main()
