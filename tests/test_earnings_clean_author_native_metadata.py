"""Offline synthetic metadata and saved-public rebind transport tests only.

No model/Native/financial/scorer execution or ledger writes. Git transport is
mocked explicitly; real immutable saved public bindings are hashed/read only.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
import earnings_population_clean_slate as clean
import earnings_population_runtime as runtime
from supervisor_harness import capacity_feedback_engine as e


def deny_network(event,args):
    if event in ('socket.connect','socket.bind'):raise AssertionError('OFFLINE no network')
sys.addaudithook(deny_network)


class AuthorMetadataTests(unittest.TestCase):
    def setUp(self):
        self.seed=dict(id='p',R={'sha256':'r'},H={'sha256':'h'},axis='R',parent='old',method='same',evidence=[])
        self.registered=dict(self.seed,axis='baseline',parent=None)
        self.packet=dict(population={'versions':{'p':self.registered}},feedback={'path':'feedback','sha256':'x'})
        self.task=dict(scaffold=self.packet['population'],feedback=self.packet['feedback'])
        self.chosen=dict(parent_pair_sha256='p')
        self.stages=[{'output':{'packet':'p'}},{'output':{'decision':'d'}}]

    def verify(self):
        with patch.object(e,'read',side_effect=lambda b:{'p':self.packet,'d':self.chosen}[b]):
            return clean._registered_author_parent(self.task,self.stages,self.seed)

    def test_original_projection_and_identical_parent_are_accepted(self):
        self.assertEqual(self.verify(),self.registered)
        self.registered.update(self.seed)
        self.assertEqual(self.verify(),self.seed)

    def test_code_evidence_method_ancestry_extra_or_selected_parent_tamper_fail(self):
        for key,other in [('id','other'),('R',{'sha256':'wrong'}),('H',{'sha256':'wrong'}),
                          ('method','wrong'),('evidence',['fake']),('axis','H'),('parent','fake'),('extra',True)]:
            saved=deepcopy(self.registered);self.registered[key]=other
            with self.subTest(key=key),self.assertRaises(ValueError):self.verify()
            self.registered.clear();self.registered.update(saved)
        self.chosen['parent_pair_sha256']='wrong'
        with self.assertRaises(ValueError):self.verify()

    def test_source_has_only_registered_author_expected_value(self):
        import inspect
        text=inspect.getsource(clean.closed_evidence)
        self.assertIn("else _registered_author_parent(task,stages,seed) if role=='author' else seed)",text)
        self.assertIn('completed._native(',text)


class Native137RebindTests(unittest.TestCase):
    def setUp(self):
        self.closure=runtime._local(clean.NATIVE137_CLOSURE)
        self.old=runtime._local(self.closure['frozen'])
        self.original_runtime=runtime._local(self.closure['runtime'])
        self.sources=deepcopy(self.original_runtime['sources'])
        name='tools/earnings_population_clean_slate.py'
        self.sources[name]=e.pin(clean.e.REPO/name)
        self.rb=dict(path=str(clean.training.ROOT/'TRAIN25-CLEAN138-EXECUTION-REBIND.json'),sha256='b'*64)
        self.binding=dict(path=str(clean.training.ROOT/'TRAIN25-CLEAN138-REBIND-FROZEN-CANDIDATE.json'),sha256='c'*64)
        self.receipt=dict(schema='edgar25_native137_metadata_execution_rebind_v1',original_descriptor=self.closure['frozen'],
            corrected_closure=clean.NATIVE137_CLOSURE,archive=clean.NATIVE137_ARCHIVE,new_source_commit='d'*40,sources=self.sources)
        self.descriptor=dict(deepcopy(self.old),source_commit='d'*40,execution_rebind=self.rb)
        self.original_local=runtime._local

    def local(self,b):
        if b==self.rb:return deepcopy(self.receipt)
        if b==clean.NATIVE137_CLOSURE:return deepcopy(self.closure)
        return self.original_local(b)

    def git(self,args,**kw):
        self.assertEqual(args[0],'git');self.assertEqual(kw['cwd'],clean.e.REPO)
        if args[1]=='diff':return SimpleNamespace(stdout='tools/earnings_population_clean_slate.py\ntests/test_earnings_clean_author_native_metadata.py\n')
        self.assertEqual(args[1],'show')
        revision,path=args[2].split(':',1)
        original=clean.training.ROOT/path.removeprefix('original/') if path.startswith('original/') else clean.e.REPO/path
        return SimpleNamespace(stdout=original.read_bytes())

    def verify(self,binding=None,descriptor=None):
        with patch.object(runtime,'_local',side_effect=self.local),patch.object(clean.subprocess,'run',side_effect=self.git):
            return clean.native137_execution_rebind(binding or self.binding,descriptor or self.descriptor)

    def test_exact_saved_corrected_gate_and_same_code_resources(self):
        verified=self.verify()
        self.assertEqual(verified['candidate'],self.old['candidate'])
        self.assertEqual(verified['runtime'],self.original_runtime)
        self.assertFalse(self.closure['original_accepted_gate_passed'])
        self.assertTrue(self.closure['corrected_native_metadata_gate_passed'])

    def test_per_send_bindings_keep_original_archive_and_failed_gate(self):
        with patch.object(e,'read',return_value=self.descriptor):
            self.assertEqual(clean.frozen_inputs(self.binding),[self.binding,self.rb,clean.NATIVE137_CLOSURE,clean.NATIVE137_ARCHIVE])

    def test_failed_incomplete_or_false_unmodified_gate_claim_rejected(self):
        for key,other in [('status','FAILED_NO_RETRY'),('original_true_exit',1),('original_accepted_gate_passed',True),
                          ('corrected_native_metadata_gate_passed',False),('all_owned_settled',False),('pending_count',1),
                          ('pending_full_reserved_nano_usd',1)]:
            saved=deepcopy(self.closure);self.closure[key]=other
            with self.subTest(key=key),self.assertRaises(ValueError):self.verify()
            self.closure=saved

    def test_candidate_round_parent_resource_forecaster_substitution_rejected(self):
        for key,other in [('candidate',dict(self.old['candidate'],id='0'*64)),('learning_round',14),
                          ('parent_basis',self.rb),('proposal',self.rb),('forecast_sources',{}),
                          ('forecast_limits',dict(self.old['forecast_limits'],wall_seconds=1801)),('rates',{})]:
            with self.subTest(key=key),self.assertRaises(ValueError):self.verify(descriptor=dict(self.descriptor,**{key:other}))

    def test_nonfinite_path_and_unapproved_source_rejected(self):
        with self.assertRaises(ValueError):self.verify(binding=dict(self.binding,path=self.binding['path']+'x'))
        self.receipt['sources']['forecaster']=dict(self.sources['forecaster'],sha256='0'*64)
        with self.assertRaisesRegex(ValueError,'Only Native'):self.verify()

    def test_wrong_checkpoint_scope_and_blob_tamper_rejected(self):
        with patch.object(runtime,'_local',side_effect=self.local),patch.object(clean.subprocess,'run',return_value=SimpleNamespace(stdout=b'fake')):
            with self.assertRaisesRegex(ValueError,'immutable blob'):clean.native137_execution_rebind(self.binding,self.descriptor)
        original=self.git
        def broad(args,**kw):
            return SimpleNamespace(stdout='tools/earnings_entry.py\n') if args[1]=='diff' else original(args,**kw)
        with patch.object(runtime,'_local',side_effect=self.local),patch.object(clean.subprocess,'run',side_effect=broad):
            with self.assertRaisesRegex(ValueError,'checkpoint scope'):clean.native137_execution_rebind(self.binding,self.descriptor)


if __name__=='__main__':unittest.main()
