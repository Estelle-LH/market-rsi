"""Saved public evidence read-only, with explicitly mocked prospective Git.

No original gate/Native/model/scorer/ledger writes or evidence regeneration.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import earnings_population_additional_execution as a
import earnings_population_clean_slate as clean
import earnings_population_runtime as runtime
import earnings_population_budget as budget
from supervisor_harness import capacity_feedback_engine as e


class FinancialExecutionTests(unittest.TestCase):
    def setUp(self):
        self.old=e.read(a.OLD)
        self.rb=dict(path=str(a.ROOT/a.RECEIPT),sha256='a'*64)
        self.bound=dict(path=str(a.ROOT/a.NAME),sha256='b'*64)
        self.descriptor=dict(self.old,source_commit='c'*40,execution_rebind=self.rb)
        # The old financial-only bridge is intentionally NOT a generic current
        # Source alias. Pin its real154-source map after later idle policy edits.
        self.sources=deepcopy(e.read(e.pin(a.ROOT/a.RECEIPT))['sources'])
        self.receipt=dict(schema='edgar25_additional100_round15_execution_rebind_v1',authority=a.HUMAN,
            original_descriptor=a.OLD,original_source_commit=a.SOURCE,new_source_commit='c'*40,sources=self.sources)
        self.original_read=e.read;self.original_git=budget._git

    def verify(self):
        def read(b):return deepcopy(self.receipt) if b==self.rb else self.original_read(b)
        def git(commit,name):
            if commit=='c'*40:return self.original_git('f467c11678fb75097d1d448eefc2a2aff33fa388',name)
            return self.original_git(commit,name)
        original_checked=a.checked
        def checked(bound):
            matches=[name for name,b in self.sources.items() if b==bound]
            if matches:
                relative=str(Path(bound['path']).relative_to(budget.REPO))
                raw=self.original_git('f467c11678fb75097d1d448eefc2a2aff33fa388',relative)
                if hashlib.sha256(raw).hexdigest()!=bound['sha256']:raise ValueError('Archived financial source differs')
                return raw
            return original_checked(bound)
        real_run=a.subprocess.run
        def run(args,**kwargs):
            if args[:3]==['git','diff','--name-only']:
                return SimpleNamespace(stdout='\n'.join(sorted(a.PRODUCTION|a.TESTS))+'\n')
            return real_run(args,**kwargs)
        with patch.object(e,'read',side_effect=read),patch.object(a,'checked',side_effect=checked),patch.object(budget,'_git',side_effect=git),patch.object(a.subprocess,'run',side_effect=run):
            return a.verify(self.bound,self.descriptor)

    def test_authentic_archived137_and138_preserve_failed_gate_and_scientific_identity(self):
        result=self.verify()
        self.assertEqual(result['candidate'],self.old['candidate'])
        self.assertEqual(result['runtime']['source_commit'],'772e5a6746513666902c52f64924476196ee8c7b')
        closure=e.read(clean.NATIVE137_CLOSURE)
        self.assertFalse(closure['original_accepted_gate_passed'])
        self.assertTrue(closure['corrected_native_metadata_gate_passed'])

    def test_substitute_candidate_parent_R_H_resources_or_round_fails(self):
        for key,value in [('candidate',dict(self.old['candidate'],id='0'*64)),
                          ('candidate',dict(self.old['candidate'],parent='0'*64)),
                          ('candidate',dict(self.old['candidate'],H={})),
                          ('forecast_limits',dict(self.old['forecast_limits'],wall_seconds=1801)),
                          ('forecast_sources',{}),('rates',{}),('learning_round',14),('parent_basis',self.rb)]:
            before=self.descriptor;self.descriptor=dict(self.descriptor,**{key:value})
            with self.subTest(key=key),self.assertRaises(ValueError):self.verify()
            self.descriptor=before

    def test_unapproved_source_and_nonfinite_descriptor_rejected(self):
        self.sources['forecaster']=dict(self.sources['forecaster'],sha256='0'*64)
        with self.assertRaises(ValueError):self.verify()
        self.bound=dict(self.bound,path=self.bound['path']+'-foreign')
        with self.assertRaises(ValueError):self.verify()

    def test_exact_authority_and_old_source_are_required(self):
        for key,value in [('authority',self.rb),('original_source_commit','0'*40),('original_descriptor',self.rb)]:
            before=deepcopy(self.receipt);self.receipt[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.verify()
            self.receipt=before

    def test_per_send_binding_preserves_direct_authority_and_archives(self):
        with patch.object(e,'read',return_value=self.descriptor):
            bound=clean.frozen_inputs(self.bound)
        self.assertIn(a.HUMAN,bound);self.assertIn(a.OLD,bound)
        self.assertIn(clean.NATIVE137_CLOSURE,bound);self.assertIn(clean.NATIVE137_ARCHIVE,bound)


if __name__=='__main__':unittest.main()
