"""Synthetic approved18 authority, immutable evidence joins and shared80."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import earnings_open_author_followthrough as flow
from supervisor_harness import capacity_feedback_engine as engine


APPROVAL='先核清这 $0.3502 的未决费用，再给具体计划，开新的90分钟窗口，用新 ID 让 Author 修复解析规则和测试预期，补真实表格测试，独立审查通过后验证下一轮真实预测使用了新版本。沿用剩余额度和原 $200 累计预算，数据、scorer 不变，每个改动单独提交，失败先诊断，不自动重试。'
OPERATOR_APPROVAL='允许全额保守记账后继续；子额度约余 $0.88'
ORIGINAL14='ac37fa7729796edb19b18c5c66cbf3cfafdbb7f4e14ced415d47cc9ff0b950ba'
REVIEW14='d0cdab3bd66d0c26cbca234506670bbbad1ad64f250f81155eee362dd20b91e2'
FAILURE16='d621fe610cce92de1d1552a081562b5ca5a48032614afe7c4d154945e0b4c7ce'


class Author18FollowthroughTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve(); self.number=0
        self.window={'issued_utc':'2026-10-15T23:50:19Z','cutoff_utc':'2026-10-16T01:19:19Z',
            'deadline_utc':'2026-10-16T01:20:19Z'}
        self.scope={'schema':'earnings_author_followthrough_authority_v1','human_authorization':flow.AUTHORIZATION,
            'author_id':'edgar-research-20261015-18','forecast_id':'edgar-research-20261015-19',
            'parent':'edgar-feedback-20261015-11','parent_result':{'sha256':flow.PARENT_RESULT_SHA},
            'parent_audit':{'sha256':flow.PARENT_AUDIT_SHA},'baseline_row':4283,'no_retry':True,
            'continuation_cumulative_cap_nano_usd':10_000_000_000,'original_total_cap_nano_usd':200_000_000_000,
            'window':self.window,'requires_cold_probe':True,'continuation_human_approval':APPROVAL,
            'operator_human_approval':OPERATOR_APPROVAL,
            'failed_author_result':{'path':'synthetic-author14','sha256':'f'*64},
            'failed_candidate_review':{'path':'synthetic-review14','sha256':REVIEW14},
            'closed16_failure_review':{'path':'synthetic-failure16','sha256':FAILURE16}}
        self.observed={'request_id':'fa1f085d-9093-4cbe-ae3d-1c9ffcfb776c',
            'full_liability_nano_usd':350207500,'actual_invoice':'UNKNOWN','no_duplicate_operator_call':True}
        self.review={'verdict':'PASS_OBSERVED_FULL_CEILING_DISPOSITION_ONLY','blocking_findings':[],
            'reviewer':'distinct-synthetic-accounting-reviewer'}
        self.priors={'synthetic-author14':{'original':{'sha256':ORIGINAL14}},
            'synthetic-review14':{'verdict':'REJECT_AUTHOR_CANDIDATE_ONE_FORECAST'},
            'synthetic-failure16':{'verdict':'VERIFIED_CUTOFF_FAILURE_UNRESOLVED_FINANCIAL_LIABILITY_NO_RETRY'}}

    def authority(self, *, scope_changes=None, observed_changes=None, review_changes=None, prior_changes=None):
        self.number+=1; home=self.root/f'check-{self.number}'; home.mkdir()
        observed=engine.save(home/'observed.json',dict(self.observed,**(observed_changes or {})))
        review=dict(self.review,observed_reconciliation=observed); review.update(review_changes or {})
        scope=deepcopy(self.scope); scope.update(observed_reconciliation=observed,
            reconciliation_review=engine.save(home/'review.json',review)); scope.update(scope_changes or {})
        scope_path=home/'scope.json'; engine.save(scope_path,scope)
        priors=deepcopy(self.priors); priors.update(prior_changes or {})
        def read(binding):
            if binding.get('path') in priors: return priors[binding['path']]
            return engine.read(binding)
        with mock.patch.object(flow,'SCOPE',scope_path),mock.patch.object(flow,'read',side_effect=read),\
                mock.patch.object(flow.fresh,'policy',return_value={'window':self.window}),\
                mock.patch.object(flow.fresh,'pilot_cap',return_value=10_000_000_000):
            return flow.authority()

    def test_valid18_preserves_fixed_window_baseline_and_caps(self):
        actual=self.authority()
        for field in self.scope: self.assertEqual(actual[field],self.scope[field])
        self.assertEqual(actual['window']['deadline_utc'],'2026-10-16T01:20:19Z')

    def test_wrong_approvals_old_pairs_window_and_budget_resets_rejected(self):
        changes=[{'continuation_human_approval':'unapproved'},{'operator_human_approval':'continue'},
            {'author_id':'edgar-research-20261015-20'},
            {'author_id':'edgar-research-20261015-16','forecast_id':'edgar-research-20261015-17'},
            {'author_id':'edgar-research-20261015-14','forecast_id':'edgar-research-20261015-15'},
            {'forecast_id':'edgar-research-20261015-17'},{'requires_cold_probe':False},{'no_retry':False},
            {'baseline_row':4650},{'continuation_cumulative_cap_nano_usd':11_000_000_000},
            {'original_total_cap_nano_usd':201_000_000_000}]
        changes.extend({'window':dict(self.window,**{key:'2099-01-01T00:00:00Z'})} for key in self.window)
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError): self.authority(scope_changes=change)

    def test_rejected14_and_closed16_exact_identity_verdicts_required(self):
        for name in ('failed_candidate_review','closed16_failure_review'):
            binding=dict(self.scope[name],sha256='0'*64)
            with self.subTest(name=name),self.assertRaises(ValueError): self.authority(scope_changes={name:binding})
        for name,value in (('synthetic-author14',{'original':{'sha256':'0'*64}}),
                ('synthetic-review14',{'verdict':'PASS_AUTHOR_CANDIDATE_ONE_FORECAST'}),
                ('synthetic-failure16',{'verdict':'COMPLETED'})):
            with self.subTest(name=name),self.assertRaises(ValueError): self.authority(prior_changes={name:value})

    def test_full_liability_unknown_invoice_and_once_only_disposition_required(self):
        changes=[{'request_id':'other'},{'full_liability_nano_usd':350207499},
            {'full_liability_nano_usd':0},{'actual_invoice':350207500},
            {'actual_invoice':'KNOWN'},{'no_duplicate_operator_call':False}]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError): self.authority(observed_changes=change)
        with self.assertRaises(ValueError):
            self.authority(scope_changes={'observed_reconciliation':{'path':'not-bound','sha256':'0'*64}})

    def test_distinct_nonempty_reviewer_and_exact_observed_binding_required(self):
        for reviewer in (None,False,0,[],{},'', ' ', 'Root',' /root '):
            with self.subTest(reviewer=reviewer),self.assertRaises(ValueError):
                self.authority(review_changes={'reviewer':reviewer})
        for change in ({'blocking_findings':['unresolved']},{'verdict':'PASS'},
                {'observed_reconciliation':{'path':'other','sha256':'0'*64}}):
            with self.assertRaises(ValueError): self.authority(review_changes=change)

    def test_all_prior_failed12_14_16_and_current18_19_share_original80(self):
        roots=[('12','code'),('12','review-code')]
        roots.extend((identifier,name) for identifier in ('14','16','18')
            for name in ('code','review-code','cold-probe-code'))
        roots.append(('19','code'))
        for index,(identifier,name) in enumerate(roots):
            home=self.root/'attempts'/('edgar-research-20261015-'+identifier)/name; home.mkdir(parents=True)
            for number in range(13 if index==len(roots)-1 else 6):
                call=home/f'call-{number:032x}'; call.mkdir()
                engine.save(call/'result.json',{'status':'FAILED_NO_RETRY'})
        with mock.patch.object(flow,'ROOT',self.root),mock.patch.object(flow,'authority',return_value=self.scope):
            self.assertEqual(flow.containers_remaining(),1)
            (self.root/'attempts/edgar-research-20261015-16/cold-probe-code'/('call-'+'f'*32)).mkdir()
            with self.assertRaises(ValueError): flow.containers_remaining()


if __name__=='__main__': unittest.main()
