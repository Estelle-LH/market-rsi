from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_source_review_v2 as runner
from market_rsi import canonical,digest,file_hash,fresh_json,load_json
from paid_budget import PaidBudget
from test_source_review_v2 import fixture_v2


class DispatcherV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        self.prepared=self.root/'fixture-v2';self.prepared.mkdir()
        self.budget=PaidBudget.create(self.root/'budget',{'experiment_id':'fixture-study','cap_usd':'200',
            'target_usd':'200','buckets_usd':{'learning':'130','final':'50','repair':'20'},'authority':'Unit fixture only.'})
        self.live=self.root/'live/source_review_tools/run_source_review_v2.py';self.live.parent.mkdir(parents=True)
        self.live.write_text('fixture v2 source');self.code=self.root/'codex';self.code.write_text('fixture runtime')
        name='source_review_tools/run_source_review_v2.py';sources={name:file_hash(self.live)}
        snap=self.prepared/'source-snapshot'/name;snap.parent.mkdir(parents=True);snap.write_bytes(self.live.read_bytes())
        visible,_,_=fixture_v2();ctx=visible['context.json'];ctx['budget_authorization_sha256']=file_hash(self.root/'budget/authorization.json')
        ctx['context_sha256']=digest({k:v for k,v in ctx.items() if k!='context_sha256'})
        sha=runner.review.core.make_workspace(self.prepared/'workspace',visible,self.prepared.name,'source_review')
        prep={'schema':'historical_source_review_v2_preparation_v1','source_review_interface_version':2,
            'purpose':'source_review','source_hashes':sources,'workspace_sha256':sha,'inputs':{},
            'context_sha256':ctx['context_sha256'],'followup_sha256':'c'*64}
        fresh_json(self.prepared/'preparation.json',prep)
        self.stdio=self.root/'stdio/transport-canary.json';self.stdio.parent.mkdir()
        fresh_json(self.stdio.parent/'preparation.json',{'purpose':'transport_canary','source_hashes':sources})
        self.seal(self.stdio,{'schema':'historical_source_review_v2_stdio_canary_v1','passed':True,
            'actual_stdio_child':True,'actual_tools':5,'full_plan_schema_served':True,
            'new_model_calls':0,'new_public_metadata_calls':0,'context_sha256':ctx['context_sha256'],
            'followup_sha256':'c'*64,'preparation_sha256':file_hash(self.stdio.parent/'preparation.json')})
        self.full=self.root/'full/codex-fixture-canary.json';self.full.parent.mkdir()
        fresh_json(self.full.parent/'preparation.json',{'purpose':'transport_canary','source_hashes':sources})
        (self.full.parent/'session').mkdir()
        fresh_json(self.full.parent/'session/assessment.json',{'valid':True,'process_reaped':True,'turns':2,
            'tool_calls':4,'model_authorship_proven':False,'evidence_mode':'synthetic_transport_fixture'})
        fresh_json(self.full.parent/'fixture-only-claim.json',{'fixture':True})
        self.seal(self.full,{'schema':'historical_source_review_v2_codex_fixture_v1','passed':True,
            'actual_codex_cli':True,'actual_tinker_calls':0,'source_hashes':sources,
            'followup_sha256':'c'*64,'context_sha256':ctx['context_sha256'],
            'preparation_sha256':file_hash(self.full.parent/'preparation.json'),
            'assessment_sha256':file_hash(self.full.parent/'session/assessment.json'),
            'fixture_claim_sha256':file_hash(self.full.parent/'fixture-only-claim.json'),
            'codex_cli_sha256':file_hash(self.code),'python_sha256':file_hash(Path(sys.executable))})
        self.patches=[patch.object(runner,'ROOT',self.root/'live'),patch.object(runner,'__file__',str(self.live)),
            patch.object(runner.harness,'CODEX',str(self.code))]
        for p in self.patches:p.start()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()

    @staticmethod
    def seal(path,payload):
        v={k:x for k,x in payload.items() if k!='result_sha256'};v['result_sha256']=digest(v)
        path.write_text(canonical(v))

    def check(self):return runner.preflight(self.prepared,self.root/'budget',self.stdio,self.full)

    def test_free_preflight_not_spend_or_authority(self):
        r=self.check();self.assertEqual(r['controller_stage'],'source_review_v2')
        self.assertFalse(r['new_raw_download_admitted']);self.assertFalse(r['new_test_admitted'])
        self.assertEqual(self.budget.snapshot()['jobs'],{})
        self.assertFalse((self.prepared/'dispatch-claim.json').exists())

    def test_duplicate_claim_prevents_dispatch(self):
        fresh_json(self.prepared/'dispatch-claim.json',{'fixture':True})
        with self.assertRaisesRegex(ValueError,'already claimed'):self.check()

    def test_binary_or_source_change_fails(self):
        self.live.write_text('changed')
        with self.assertRaisesRegex(ValueError,'source changed'):self.check()

    def test_wrong_followup_or_old_canary_rejected(self):
        v=load_json(self.full);v['followup_sha256']='d'*64;self.seal(self.full,v)
        with self.assertRaisesRegex(ValueError,'actual Codex fixture'):self.check()

    def test_reserved_upper_not_metered(self):
        self.budget.reserve('fixture-held','learning','123','fixture','a'*64)
        with self.assertRaisesRegex(ValueError,'upper exceeds'):self.check()
        self.assertEqual(self.budget.snapshot()['metered_usd'],'0')

    def test_active_model_prevents_second(self):
        self.budget.reserve('fixture-turn-001','learning','1','fixture','a'*64);self.budget.dispatch('fixture-turn-001')
        with self.assertRaisesRegex(ValueError,'unresolved model'):self.check()

    def test_fake_backend_cannot_claim_real_authorship(self):
        with self.assertRaisesRegex(ValueError,'pinned paid backend'):
            runner.run_session(prepared=self.prepared,backend=object(),budget=self.budget,
                prompt='fixture',evidence_mode='paid_controller')


if __name__=='__main__':unittest.main()
