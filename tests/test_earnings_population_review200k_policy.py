"""Inactive Review-only resource resolver; invented authority bytes, no ledger/API.

The production authority path/hash constants are asserted separately. Portable
positive fixtures substitute ONLY those constants with a synthetic temporary
document; they prove resolver checks, not real authority/runtime activation.
"""
from copy import deepcopy
import hashlib
import inspect
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import earnings_open_resources as resources
from earnings_loop_policy import LIMITS


class Review200PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.path=self.root/'TRAIN25-DIRECT-REVIEW200K-REUSE37-AUTHORITY.json'
        self.document=dict(schema='earnings_training25_direct_review200k_reuse37_authority_v1',
            old_review_max_input_tokens=32000,new_review_max_input_tokens=200000,
            status='DIRECTLY_AUTHORIZED_NOT_IMPLEMENTED_OR_ACTIVATED',
            unchanged=dict(model='gpt-6.1-sol',controller_input_tokens=32000,Author_input_tokens=96000,
                Author_output_tokens=49152,Review_output_tokens=16384,Review_wall_seconds=900,
                window_minutes=90,stage_additional_nano_usd=200000000000,
                cumulative_cap_nano_usd=400000000000,named_model_cap_nano_usd=300000000000))
        self.bound=self.save(self.document)
        self.root_patch=patch.object(resources,'REVIEW200_ROOT',self.root);self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.binding_patch=patch.object(resources,'REVIEW200_AUTHORITY',self.bound);self.binding_patch.start()
        self.addCleanup(self.binding_patch.stop)

    def save(self,value):
        self.path.write_text(json.dumps(value,sort_keys=True))
        return dict(path=str(self.path),sha256=hashlib.sha256(self.path.read_bytes()).hexdigest())

    def value(self):return dict(review_input_policy=resources.REVIEW200_POLICY)

    def test_production_pin_and_default_function_body_remain_exact(self):
        self.binding_patch.stop();self.root_patch.stop()
        self.assertEqual(resources.REVIEW200_AUTHORITY['sha256'],
            'aef9fa092ceeb4afe4b1ee22f288df5b9d660f8419fdd84f2b866ae8885aa959')
        self.assertEqual(Path(resources.REVIEW200_AUTHORITY['path']).name,self.path.name)
        self.assertEqual(inspect.getsource(resources.role_limits),
            "def role_limits():\n"
            "    return {'controller':dict(deepcopy(LIMITS),max_input_tokens=32000,wall_seconds=900),\n"
            "        'review':dict(deepcopy(LIMITS),max_input_tokens=32000,wall_seconds=900),\n"
            "        'author':{'max_input_tokens':96000,'max_output_tokens':49152,'wall_seconds':1200}}\n")

    def test_absent_marker_is_legacy_and_reads_no_authority(self):
        with patch.object(resources.e,'checked',side_effect=AssertionError('No legacy authority read')):
            self.assertIsNone(resources.review_input_policy({}))
            self.assertEqual(resources.population_role_limits({}),resources.role_limits())

    def test_only_exact_explicit_string_policy_selects_overlay(self):
        for bad in (None,True,False,200000,200000.0,'','review_input_200001_v1',{},[]):
            with self.subTest(value=bad),patch.object(resources.e,'checked',
                    side_effect=AssertionError('Bad marker read authority')):
                with self.assertRaises(ValueError):
                    resources.population_role_limits(dict(review_input_policy=bad))

    def test_nonobject_is_not_a_missing_marker(self):
        for bad in (None,True,32000,[],resources.REVIEW200_POLICY):
            with self.subTest(value=bad),self.assertRaises(ValueError):
                resources.population_role_limits(bad)

    def test_authorized_copy_changes_only_review_input(self):
        original=resources.role_limits();efforts=deepcopy(resources.ROLE_EFFORTS);generic=deepcopy(LIMITS)
        value=self.value();before=deepcopy(value)
        selected=resources.population_role_limits(value);expected=deepcopy(original)
        expected['review']['max_input_tokens']=200000
        self.assertEqual(resources.review_input_policy(value),resources.REVIEW200_POLICY)
        self.assertEqual(selected,expected);self.assertEqual(value,before)
        self.assertEqual(resources.ROLE_EFFORTS,efforts);self.assertEqual(LIMITS,generic)
        selected['author']['max_output_tokens']=1;selected['review']['wall_seconds']=1
        self.assertEqual(resources.role_limits(),original)
        self.assertEqual(resources.population_role_limits(value),expected)

    def test_derivation_does_not_accept_caller_supplied_limits_or_grant_credit(self):
        value=dict(self.value(),limits={'author':{'max_input_tokens':200000}},additional_cap_nano_usd=10**30)
        selected=resources.population_role_limits(value)
        self.assertEqual(selected['author']['max_input_tokens'],96000)
        self.assertEqual(set(selected),{'controller','author','review'})
        self.assertEqual(selected['review'],dict(LIMITS,max_input_tokens=200000,wall_seconds=900))
        # This is a derived expected map, not validation of arbitrary runtime fields.
        self.assertNotEqual(value['limits'],selected)

    def test_source_bound_authority_byte_tamper_refuses(self):
        raw=self.path.read_bytes();before=self.path.stat();self.path.write_bytes(raw.replace(b'200000',b'200001',1))
        os.utime(self.path,ns=(before.st_atime_ns,before.st_mtime_ns))
        with self.assertRaises(ValueError):resources.population_role_limits(self.value())

    def test_authority_hash_and_binding_shape_refuse(self):
        for bad in ({'path':str(self.path),'sha256':'f'*64},
                    {'path':str(self.path),'sha256':self.bound['sha256'],'extra':True},
                    {'sha256':self.bound['sha256']},{'path':str(self.path),'sha256':True}):
            with self.subTest(binding=bad),patch.object(resources,'REVIEW200_AUTHORITY',bad):
                with self.assertRaises(ValueError):resources.population_role_limits(self.value())

    def test_noncanonical_or_wrong_authority_name_refuses_before_read(self):
        for name in (str(self.root/'wrong.json'),str(self.root)+'/./'+self.path.name):
            with self.subTest(path=name),patch.object(resources,'REVIEW200_AUTHORITY',dict(self.bound,path=name)),\
                    patch.object(resources.e,'checked',side_effect=AssertionError('Read foreign path')):
                with self.assertRaises(ValueError):resources.population_role_limits(self.value())

    def test_symlink_and_hardlink_refuse_before_read(self):
        original=self.root/'original.json';self.path.rename(original);self.path.symlink_to(original)
        with patch.object(resources.e,'checked',side_effect=AssertionError('Read alias')):
            with self.assertRaises(ValueError):resources.population_role_limits(self.value())
        self.path.unlink();os.link(original,self.path)
        with patch.object(resources.e,'checked',side_effect=AssertionError('Read hardlink')):
            with self.assertRaises(ValueError):resources.population_role_limits(self.value())

    def test_missing_or_directory_authority_refuses_before_read(self):
        self.path.unlink()
        with patch.object(resources.e,'checked',side_effect=AssertionError('Read missing')):
            with self.assertRaises(ValueError):resources.population_role_limits(self.value())
        self.path.mkdir()
        with patch.object(resources.e,'checked',side_effect=AssertionError('Read directory')):
            with self.assertRaises(ValueError):resources.population_role_limits(self.value())

    def test_rebound_synthetic_authority_cannot_change_other_settings(self):
        changes=[('new_review_max_input_tokens',200001),('new_review_max_input_tokens',True),
            ('old_review_max_input_tokens',20000),('schema','wrong'),('status','ACTIVATED')]
        changes += [('unchanged.'+k,v) for k,v in [('model','other'),('controller_input_tokens',200000),
            ('Author_input_tokens',200000),('Author_output_tokens',200000),('Review_output_tokens',200000),
            ('Review_wall_seconds',1200),('window_minutes',180),('stage_additional_nano_usd',300000000000),
            ('cumulative_cap_nano_usd',600000000000),('named_model_cap_nano_usd',True)]]
        for key,value in changes:
            with self.subTest(field=key):
                doc=deepcopy(self.document)
                if key.startswith('unchanged.'):doc['unchanged'][key.split('.',1)[1]]=value
                else:doc[key]=value
                bound=self.save(doc)
                with patch.object(resources,'REVIEW200_AUTHORITY',bound):
                    with self.assertRaises(ValueError):resources.population_role_limits(self.value())


if __name__=='__main__':unittest.main()
