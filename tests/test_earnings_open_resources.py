"""Prospective resource binding; invented grant, no ledger or provider."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import earnings_open_resources as resources
from earnings_loop_policy import LIMITS
from supervisor_harness import capacity_feedback_engine as e


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.runtime={'schema':'earnings_capacity_runtime_v2','id':'invented','root':str(self.root),
            'source_commit':'a'*40,'ledger':'invented-not-opened','baseline':{'invented':True},
            'cutoff_utc':'2026-10-15T00:20:32Z','deadline_utc':'2026-10-15T00:21:32Z',
            'additional_cap_nano_usd':6500000000,'sources':{
                'factory_author':e.pin(resources.e.REPO/'tools/earnings_open_assembly.py')}}
        self.grant={k:v for k,v in self.runtime.items() if k not in {'sources','schema'}}
        self.grant['schema']='earnings_open_grant_v1'

    def study(self):return {'new_live_grant':e.save(self.root/'grant.json',self.grant)}

    def test_declared_open_role_increases_not_global_budget_or_generic_roles(self):
        caps=resources.role_limits()
        self.assertEqual(caps['controller'],dict(LIMITS,max_input_tokens=16000));self.assertEqual(caps['review'],LIMITS)
        self.assertEqual(caps['author'],{'max_input_tokens':24000,'max_output_tokens':49152,'wall_seconds':900})
        caps['controller']['max_input_tokens']=1
        self.assertEqual(resources.role_limits()['controller'],dict(LIMITS,max_input_tokens=16000))
        self.assertEqual(LIMITS['max_input_tokens'],10000)
        self.assertEqual(resources.author_ceiling(self.runtime,self.study()),caps['author'])

    def test_legacy_or_missing_open_grant_does_not_raise_ceiling(self):
        self.assertIsNone(resources.author_ceiling(self.runtime,{}))
        self.assertIsNone(resources.author_ceiling(dict(self.runtime,schema='earnings_capacity_runtime_v1'),{}))
        self.grant['schema']='earnings_real_rh_grant_v1'
        self.assertIsNone(resources.author_ceiling(self.runtime,self.study()))

    def test_foreign_factory_and_drifted_authority_refused(self):
        study=self.study()
        for key,value in [('source_commit','b'*40),('additional_cap_nano_usd',7500000000),
                ('cutoff_utc','2026-10-15T01:20:32Z')]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                resources.author_ceiling(dict(self.runtime,**{key:value}),study)
        changed=deepcopy(self.runtime)
        changed['sources']['factory_author']=e.pin(resources.e.REPO/'tools/earnings_capacity_assembly.py')
        with self.assertRaises(ValueError):resources.author_ceiling(changed,study)


if __name__=='__main__':unittest.main()
