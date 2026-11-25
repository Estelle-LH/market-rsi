"""Synthetic16 authority and cumulative container accounting only."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import earnings_open_author_followthrough as flow
from supervisor_harness import capacity_feedback_engine as engine


APPROVAL='允许，用新 ID 让 Author 修复这两条解析规则和测试预期，补真实财报表格测试，独立审查通过后才预测。沿用当前窗口和剩余额度，数据、scorer 和原 $200 总预算不变，每个改动单独提交，失败先诊断，不自动重试。'
ORIGINAL14='ac37fa7729796edb19b18c5c66cbf3cfafdbb7f4e14ced415d47cc9ff0b950ba'
REVIEW14='d0cdab3bd66d0c26cbca234506670bbbad1ad64f250f81155eee362dd20b91e2'


class Author16FollowthroughTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve(); self.number=0
        self.window={'issued_utc':'2026-10-15T20:57:14Z','cutoff_utc':'2026-10-15T22:26:14Z',
            'deadline_utc':'2026-10-15T22:27:14Z'}
        self.scope={'schema':'earnings_author_followthrough_authority_v1','human_authorization':flow.AUTHORIZATION,
            'author_id':'edgar-research-20261015-16','forecast_id':'edgar-research-20261015-17',
            'parent':'edgar-feedback-20261015-11','parent_result':{'sha256':flow.PARENT_RESULT_SHA},
            'parent_audit':{'sha256':flow.PARENT_AUDIT_SHA},'baseline_row':4283,'no_retry':True,
            'continuation_cumulative_cap_nano_usd':10_000_000_000,'original_total_cap_nano_usd':200_000_000_000,
            'window':self.window,'requires_cold_probe':True,'continuation_human_approval':APPROVAL,
            'failed_author_result':{'path':'synthetic-author14','sha256':'f'*64},
            'failed_candidate_review':{'path':'synthetic-review14','sha256':REVIEW14}}

    def authority(self, scope, *, original=ORIGINAL14, verdict='REJECT_AUTHOR_CANDIDATE_ONE_FORECAST'):
        self.number+=1; path=self.root/f'scope-{self.number}.json'; engine.save(path,scope)
        def read(binding):
            if binding.get('path')=='synthetic-author14': return {'original':{'sha256':original}}
            if binding.get('path')=='synthetic-review14': return {'verdict':verdict}
            return engine.read(binding)
        with mock.patch.object(flow,'SCOPE',path),mock.patch.object(flow,'read',side_effect=read),\
                mock.patch.object(flow.fresh,'policy',return_value={'window':self.window}),\
                mock.patch.object(flow.fresh,'pilot_cap',return_value=10_000_000_000):
            return flow.authority()

    def test_exact16_17_pass_and_approval_pair_window_budget_resets_rejected(self):
        self.assertEqual(self.authority(self.scope),self.scope)
        changes=[{'continuation_human_approval':'允许，新ID修复后测试和独立审查，通过才预测'},
            {'author_id':'edgar-research-20261015-18'},{'forecast_id':'edgar-research-20261015-15'},
            {'requires_cold_probe':False},{'no_retry':False},{'baseline_row':4632},
            {'continuation_cumulative_cap_nano_usd':11_000_000_000},
            {'original_total_cap_nano_usd':201_000_000_000},
            {'window':dict(self.window,deadline_utc='2099-01-01T00:00:00Z')},
            {'window':dict(self.window,cutoff_utc='2099-01-01T00:00:00Z')}]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.authority(dict(self.scope,**change))

    def test_exact_closed14_source_review_identity_and_rejection_required(self):
        with self.assertRaises(ValueError): self.authority(self.scope,original='0'*64)
        with self.assertRaises(ValueError): self.authority(self.scope,verdict='PASS_AUTHOR_CANDIDATE_ONE_FORECAST')
        bad=deepcopy(self.scope); bad['failed_candidate_review']['sha256']='0'*64
        with self.assertRaises(ValueError): self.authority(bad)
        bad=deepcopy(self.scope); bad['continuation_human_approval']='unapproved'
        with self.assertRaises(ValueError): self.authority(bad)

    def test_shared80_includes_failed12_14_and_current16_17_without_rebase(self):
        roots=[('12','code',5),('12','review-code',5),('14','code',10),('14','review-code',10),
            ('14','cold-probe-code',10),('16','code',10),('16','review-code',10),
            ('16','cold-probe-code',10),('17','code',9)]
        for identifier,name,count in roots:
            home=self.root/'attempts'/('edgar-research-20261015-'+identifier)/name
            home.mkdir(parents=True)
            for number in range(count):
                call=home/f'call-{number:032x}'; call.mkdir()
                engine.save(call/'result.json',{'status':'FAILED_NO_RETRY'})
        with mock.patch.object(flow,'ROOT',self.root),mock.patch.object(flow,'authority',return_value=self.scope):
            self.assertEqual(flow.containers_remaining(),1)
            (self.root/'attempts/edgar-research-20261015-14/cold-probe-code'/('call-'+'f'*32)).mkdir()
            with self.assertRaises(ValueError): flow.containers_remaining()


if __name__=='__main__': unittest.main()
