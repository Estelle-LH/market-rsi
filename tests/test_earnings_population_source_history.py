"""Exact source-label relocation contracts; no historical execution or Git.

Synthetic Git blobs are explicitly supplied to the real Reader. Production
Source namespace/hash/plan/authority checks run unchanged; no ledger, provider,
candidate, held-out body or QA is opened. Root owns the actual29 replay.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import earnings_population_source_history as source
import earnings_population_continuation as history
import earnings_population_recovery as recovery
import earnings_population_budget as budget
import earnings_population_runtime as runtime
import earnings_population_tasks as tasks


def sha(raw): return hashlib.sha256(raw).hexdigest()


class SourceHistoryContracts(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.home=Path(temporary.name).resolve();self.repo=self.home/'repo';self.repo.mkdir()
        self.reader=history._Reader(self.home/'owned',self.home/'ledger.sqlite3',self.repo,'edgar-population-20261016-29')
        self.raw=b'{"synthetic_original_source":true}'
        self.bound={'path':str(source.LEGACY_REPO/'tools/synthetic.py'),'sha256':sha(self.raw)}
        self.original={'source_commit':'a'*40,'sources':{'tools/synthetic.py':self.bound}}

    def test_exact_current_and_original_labels_no_sibling_or_traversal(self):
        self.assertEqual(source.source_name(self.bound['path'],self.repo),'tools/synthetic.py')
        self.assertEqual(source.source_name(self.repo/'tools/a.py',self.repo),'tools/a.py')
        for path in ('relative.py',str(source.LEGACY_REPO)+'-foreign/tools/a.py',
                     str(source.LEGACY_REPO)+'/../secret',str(source.LEGACY_REPO)+'//tools/a.py',
                     '/foreign/company/qa.json',str(source.LEGACY_REPO)):
            with self.subTest(path=path),self.assertRaises(ValueError):source.source_name(path,self.repo)

    def test_registration_is_one_exact_namespace_and_preserves_binding(self):
        before=deepcopy(self.original);self.reader.register_sources(self.original)
        self.assertEqual(self.original,before)
        self.assertEqual(self.reader.sources,{(self.bound['path'],self.bound['sha256'])})
        mixed=deepcopy(self.original);mixed['sources']['current']={'path':str(self.repo/'a.py'),'sha256':'b'*64}
        with self.assertRaisesRegex(ValueError,'Mixed'):self.reader.register_sources(mixed)
        for change in ({'source_commit':True},{'source_commit':'bad'},{'sources':{}},
                       {'sources':{'bad':dict(self.bound,sha256=False)}},
                       {'sources':{'bad':dict(self.bound,path='/foreign/a.py')}}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.reader.register_sources(dict(self.original,**change))

    def test_registered_legacy_read_is_git_only_no_old_filesystem_calls(self):
        self.reader.register_sources(self.original)
        resolve,read_bytes=Path.resolve,Path.read_bytes
        def deny_legacy(fn):
            def call(path,*a,**k):
                if path.is_relative_to(source.LEGACY_REPO):raise AssertionError('Never touch old Source filesystem')
                return fn(path,*a,**k)
            return call
        with patch.object(history,'_git',return_value=self.raw) as git, \
             patch.object(Path,'resolve',deny_legacy(resolve)), \
             patch.object(Path,'read_bytes',deny_legacy(read_bytes)):
            self.assertEqual(self.reader.read(self.bound),{'synthetic_original_source':True})
            self.assertEqual(self.reader.read(self.bound,binary=True),self.raw)
        git.assert_called_once_with(self.repo,'a'*40,'tools/synthetic.py')

    def test_unregistered_wrong_hash_and_wrong_commit_blob_fail(self):
        self.reader.register_sources(self.original)
        with patch.object(history,'_git',return_value=b'wrong'):
            with self.assertRaisesRegex(ValueError,'hash differs'):self.reader.read(self.bound)
        self.reader.sources.clear()
        with patch.object(history,'_git',side_effect=AssertionError('Unregistered source must not reach Git')):
            with self.assertRaisesRegex(ValueError,'Unregistered'):self.reader.read(self.bound)

    def test_current_source_keeps_canonical_symlink_guard_and_git_bytes(self):
        path=self.repo/'source.json';path.write_bytes(b'{"current_disk":true}')
        bound={'path':str(path),'sha256':sha(self.raw)}
        self.reader.register_sources({'source_commit':'a'*40,'sources':{'source':bound}})
        with patch.object(history,'_git',return_value=self.raw):self.assertEqual(self.reader.read(bound,binary=True),self.raw)
        real=self.repo/'real.json';real.write_bytes(self.raw);path.unlink();path.symlink_to(real)
        with self.assertRaisesRegex(ValueError,'Canonical'):self.reader.read(bound)

    def test_registration_commit_change_does_not_reuse_old_blob_cache(self):
        self.reader.register_sources(self.original)
        with patch.object(history,'_git',return_value=self.raw)as git:
            self.reader.read(self.bound)
            self.reader.register_sources(dict(self.original,source_commit='b'*40))
            self.reader.read(self.bound)
        self.assertEqual([call.args[1]for call in git.call_args_list],['a'*40,'b'*40])

    def test_legacy_runtime_metadata_exact_name_and_fixed_bytes(self):
        self.reader.register_sources(self.original)
        metadata=Path(tasks.RUNTIME['path']).read_bytes()
        self.assertEqual(sha(metadata),source.RUNTIME_SHA256)
        bound={'path':str(source.LEGACY_REPO/source.RUNTIME_NAME),'sha256':source.RUNTIME_SHA256}
        with patch.object(history,'_git',return_value=metadata):
            self.assertEqual(self.reader.read(bound),json.loads(metadata))
        for changed in (dict(bound,sha256='b'*64),dict(bound,path=str(source.LEGACY_REPO/'other.json'))):
            with self.assertRaisesRegex(ValueError,'Unregistered'):self.reader.read(changed)

    def test_foreign_artifacts_do_not_gain_source_or_extra_root_authority(self):
        self.reader.register_sources(self.original)
        foreign=self.home/'company-foreign/qa.json';foreign.parent.mkdir();foreign.write_bytes(self.raw)
        bound={'path':str(foreign),'sha256':sha(self.raw)}
        with self.assertRaisesRegex(ValueError,'outside exact owned roots'):self.reader.read(bound)
        with self.assertRaisesRegex(ValueError,'Canonical existing'):self.reader.pin(Path(self.bound['path']))

    def test_original_callback_identity_keeps_old_binding_not_relabelled_current(self):
        service=deepcopy(self.bound)
        result=history.expected_services({'sources':{'tools/earnings_population_services.py':service}})
        self.assertEqual(result['author']['module'],service)
        self.assertTrue(result['author']['module']['path'].startswith(str(source.LEGACY_REPO)))

    def test_original_plan_is_registered_git_but_current_plan_is_not_relocated(self):
        plan={'path':str(source.LEGACY_REPO/recovery.PLAN),'sha256':sha(b'{"original_plan":true}')}
        self.reader.register_sources({'source_commit':'a'*40,'sources':{recovery.PLAN:plan}})
        with patch.object(history,'_git',return_value=b'{"original_plan":true}'):
            received=recovery._read_plan(plan,root=self.reader.root,ledger=self.reader.ledger,
                repo=self.repo,historical_reader=self.reader)
        self.assertEqual(received,{'original_plan':True})
        self.assertFalse(recovery._plan_matches(plan,self.repo,None))
        self.assertTrue(recovery._plan_matches({'path':str(self.repo/recovery.PLAN)},self.repo,None))
        for changed in (dict(plan,sha256='b'*64),dict(plan,path=str(source.LEGACY_REPO/'configs/wrong.json'))):
            with self.assertRaises(ValueError):
                recovery._read_plan(changed,root=self.reader.root,ledger=self.reader.ledger,repo=self.repo,historical_reader=self.reader)

    def test_budget_grant_historical_authority_unchanged_but_activation_stays_current(self):
        value=dict(schema='supervisor_bottleneck_plan_v1',id=budget.GRANT,
            human_authorization=budget.AUTHORIZATION,budget_authority=dict(grant_id=budget.GRANT,
                sole_ledger=str(budget.LEDGER),old_cap_nano_usd=budget.OLD_CAP,
                new_cap_nano_usd=budget.CAP,model_cap_nano_usd=budget.FULL_MODEL_CAP))
        raw=json.dumps(value).encode();bound={'path':str(source.LEGACY_REPO/budget.PLAN),'sha256':sha(raw)}
        with patch.object(budget,'REPO',self.repo),patch.object(budget,'_git',return_value=raw):
            budget._authority(bound,'a'*40)
            with self.assertRaises(ValueError):budget._authority(bound,'a'*40,current=True)
            with self.assertRaises(ValueError):budget._authority(dict(bound,sha256='b'*64),'a'*40)
            with self.assertRaises(ValueError):budget._authority(dict(bound,path='/foreign/'+budget.PLAN),'a'*40)

    def test_executed_helper_is_in_existing_source_glob(self):
        paths=runtime.source_paths();name='tools/earnings_population_source_history.py'
        self.assertEqual(paths[name],str(Path(source.__file__).resolve()))


if __name__=='__main__':unittest.main()
