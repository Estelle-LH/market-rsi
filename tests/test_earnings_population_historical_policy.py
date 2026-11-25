"""Historical registered policy bytes versus current Source, all temporary.

No actual ancestry/model/ledger/Native proof: reuse only the portable fixture
metadata builders. The original policy projection, Reader and entry_plan run;
Git stdout is invented and every source/authority/data file is temporary.
"""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import earnings_population_continuation as history
import earnings_population_public_predictions as public
import earnings_population_training25 as training
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_training35_reuse as reused


class HistoricalPolicyTests(unittest.TestCase):
    def setUp(self):
        self.f = reused.ServicesAttachmentTests(methodName='runTest')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.repo,self.root,self.scope = self.f.repo,self.f.root,self.f.scope
        self.plan = self.f.p.plan(self.f.p.base)  # Original plan had no new36 block.
        self.old_raw = Path(self.plan['path']).read_bytes()
        campaign = engine.read(self.f.campaign); campaign['source_plan'] = self.plan
        path = Path(self.f.campaign['path']); path.write_text(json.dumps(campaign))
        study = deepcopy(self.f.study); study.pop('training_stage_attachment')
        study['campaign'] = engine.pin(path)
        resume = engine.read(study['campaign_resume']); resume['plan'] = self.plan
        path = Path(study['campaign_resume']['path']); path.write_text(json.dumps(resume))
        study['campaign_resume'] = engine.pin(path)
        path = Path(self.f.study_binding['path']); path.write_text(json.dumps(study))
        self.study = study
        self.runtime = dict(schema='earnings_population_runtime_v1',training_policy=training.POLICY,
            budget_amendment=self.f.cumulative,model_budget_amendment=self.f.model,
            companies=[reused.COMPANY],forecast_study=engine.pin(path),
            sources={training.PLAN:self.plan},public_feedback_policy=public.POLICY)
        self.reader = history._Reader(self.root,self.f.ledger,self.repo,'edgar-population-20261016-34')
        self.reader.register_sources(dict(source_commit='a'*40,sources={training.PLAN:self.plan}))
        self.f.p.plan()  # Current committed plan now has optional new36 attachment.
        self.assertNotEqual(Path(self.plan['path']).read_bytes(),self.old_raw)

    def test_default_current_route_still_rejects_old_binding_after_source_change(self):
        with patch.object(history,'_git',side_effect=AssertionError('Current route cannot use Git fallback')):
            for call in (public.runtime_scope,public.runtime_policy):
                with self.subTest(call=call.__name__),self.assertRaises(ValueError):
                    call(self.runtime,self.study)

    def test_registered_historical_reader_resolves_old_policy_after_current_change(self):
        with patch.object(history,'_git',return_value=self.old_raw) as git:
            self.assertEqual(public.runtime_scope(self.runtime,self.study,historical_reader=self.reader),self.scope)
            self.assertEqual(public.runtime_policy(self.runtime,self.study,historical_reader=self.reader),public.POLICY)
        git.assert_called_once_with(self.repo,'a'*40,training.PLAN)

    def test_fake_and_unregistered_readers_are_not_fallback_authority(self):
        fake = SimpleNamespace(repo=self.repo,root=self.root,sources=self.reader.sources,
                               read=lambda bound:json.loads(self.old_raw))
        with patch.object(history,'_git',side_effect=AssertionError('No unregistered Git')):
            with self.assertRaises(ValueError):
                public.runtime_scope(self.runtime,self.study,historical_reader=fake)
            self.reader.sources.clear()
            with self.assertRaises(ValueError):
                public.runtime_policy(self.runtime,self.study,historical_reader=self.reader)

    def test_registered_reader_wrong_repo_or_root_is_refused(self):
        with patch.object(history,'_git',side_effect=AssertionError('No foreign historical Git')):
            for field in ('root','repo'):
                old = getattr(self.reader,field); setattr(self.reader,field,old/'foreign')
                with self.subTest(field=field),self.assertRaises(ValueError):
                    public.runtime_scope(self.runtime,self.study,historical_reader=self.reader)
                setattr(self.reader,field,old)

    def test_historical_wrong_bytes_and_study_drift_still_fail_closed(self):
        with patch.object(history,'_git',return_value=b'{"different_original":true}'):
            with self.assertRaisesRegex(ValueError,'hash differs'):
                public.runtime_scope(self.runtime,self.study,historical_reader=self.reader)
        changed = dict(self.study,unbound_extra=True)
        with self.assertRaisesRegex(ValueError,'study differs'):
            public.runtime_policy(self.runtime,changed,historical_reader=self.reader)

    def test_current_matching_plan_defaults_keep_original_result_without_reader(self):
        Path(self.plan['path']).write_bytes(self.old_raw)
        with patch.object(history,'_git',side_effect=AssertionError('No historical fallback for current')):
            self.assertEqual(public.runtime_scope(self.runtime,self.study),self.scope)
            self.assertEqual(public.runtime_policy(self.runtime,self.study),public.POLICY)
            self.assertEqual(public.runtime_policy(self.runtime,self.study,historical_reader=None),public.POLICY)

    def test_absent_public_policy_stays_exact_legacy_and_malformed_optin_refuses(self):
        self.assertIsNone(public.runtime_policy({'schema':'original_no_optin'}))
        self.assertIsNone(public.runtime_scope({'schema':'original_no_training'}))
        with patch.object(history,'_git',return_value=self.old_raw):
            for value in (None,False,'unknown'):
                with self.subTest(value=value),self.assertRaises(ValueError):
                    public.runtime_policy(dict(self.runtime,public_feedback_policy=value),
                                          self.study,historical_reader=self.reader)


if __name__ == '__main__':
    unittest.main()
