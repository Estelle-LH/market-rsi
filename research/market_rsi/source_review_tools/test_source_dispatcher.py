import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_source_review as runner
from codex_source_fixture import ScriptedBackend
from market_rsi import canonical, digest, file_hash, fresh_json, load_json
from paid_budget import PaidBudget
from test_controller_source_review import fixture


class SourceCommandTests(unittest.TestCase):
    def setUp(self):
        self.kw = {'workspace': Path('/tmp/ws'), 'answer': Path('/tmp/answer'),
            'base_url': 'http://127.0.0.1:1234/v1', 'catalog': Path('/tmp/catalog'),
            'instructions': Path('/tmp/instructions')}

    def command(self, sha='a' * 64):
        return runner.command_for_source_review(**self.kw, manifest_sha256=sha,
                                                broker_script=Path('/tmp/source.py'))

    def test_only_mcp_route_and_its_manifest_argument_change(self):
        old = runner.harness.codex_command(**self.kw, tool_mode='canary', controller_stage='grid_learning')
        new = self.command()
        changes = [(x,y) for x,y in zip(old,new) if x != y]
        self.assertEqual(len(old),len(new)); self.assertEqual(len(changes),1)
        self.assertEqual(json.loads(changes[0][1].split('=',1)[1]),
            ['/tmp/source.py','--workspace','/tmp/ws','--manifest-sha256','a'*64])
        for value in ['--ignore-user-config','--strict-config','--ephemeral',
                'shell_environment_policy.inherit="none"','web_search="disabled"',
                'mcp_servers.controller_tools.required=true',
                'model_providers.tinker_glm_loopback.request_max_retries=0',
                'model_providers.tinker_glm_loopback.stream_max_retries=0']:
            self.assertIn(value,new)
        self.assertEqual(new[new.index('--model')+1],runner.MODEL)

    def test_manifest_hash_required(self):
        for value in ('','../wrong','A'*64,'a'*63):
            with self.subTest(value=value), self.assertRaises(ValueError): self.command(value)

    def test_ambiguous_route_rejected(self):
        with patch.object(runner,'command_for_validation',return_value=['bad']):
            with self.assertRaisesRegex(ValueError,'exactly one'): self.command()

    def test_changed_route_template_rejected(self):
        with patch.object(runner,'command_for_validation',return_value=[
                'mcp_servers.controller_tools.args=["wrong"]']):
            with self.assertRaisesRegex(ValueError,'template changed'): self.command()

    def test_permanent_claim_checked_before_budget(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve(); fresh_json(root/'dispatch-claim.json',{'fixture':True})
            with self.assertRaisesRegex(ValueError,'already claimed'):
                runner.preflight(root,root/'budget',root/'stdio',root/'full')

    def test_fake_model_cannot_claim_paid_authorship(self):
        with self.assertRaisesRegex(ValueError,'exact pinned'):
            runner.run_session(prepared=Path('/unused'),backend=ScriptedBackend(),budget=None,
                               prompt='fixture',evidence_mode='paid_controller')

    def test_scripted_backend_cannot_fallback_or_retry(self):
        b=ScriptedBackend()
        for _ in range(2): b.sample([1,2,3],100,1)
        with self.assertRaisesRegex(RuntimeError,'third'): b.sample([1,2,3],100,1)


class SourcePreflightTests(unittest.TestCase):
    """Synthetic metadata receipts only: no model, actual Codex or network."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name).resolve()
        self.prepared=self.root/'fixture-prepared'; self.prepared.mkdir()
        self.budget=PaidBudget.create(self.root/'budget',{'experiment_id':'fixture-study',
            'cap_usd':'200','target_usd':'200',
            'buckets_usd':{'learning':'130','final':'50','repair':'20'},'authority':'Unit fixture only.'})
        self.live=self.root/'live/source_review_tools/run_source_review.py'
        self.live.parent.mkdir(parents=True); self.live.write_text('fixture source')
        self.code=self.root/'fixture-codex'; self.code.write_text('fixture binary')
        name='source_review_tools/run_source_review.py'; self.sources={name:file_hash(self.live)}
        snap=self.prepared/'source-snapshot'/name; snap.parent.mkdir(parents=True)
        snap.write_bytes(self.live.read_bytes())
        visible,_,_=fixture(); context=visible['context.json']
        context['budget_authorization_sha256']=file_hash(self.root/'budget/authorization.json')
        context['context_sha256']=digest({k:v for k,v in context.items() if k!='context_sha256'})
        sha=runner.review.make_workspace(self.prepared/'workspace',visible,self.prepared.name,'source_review')
        self.prep={'schema':'historical_source_review_preparation_v1','purpose':'source_review',
            'source_hashes':self.sources,'context_sha256':context['context_sha256'],
            'workspace_sha256':sha,'inputs':{}}
        fresh_json(self.prepared/'preparation.json',self.prep)
        self.mcp=self.root/'stdio/transport-canary.json'; self.mcp.parent.mkdir()
        fresh_json(self.mcp.parent/'preparation.json',{'purpose':'transport_canary','source_hashes':self.sources})
        self.seal(self.mcp,{'schema':'historical_source_review_stdio_canary_v1',
            'passed':True,'actual_stdio_child':True,'new_model_calls':0,'new_public_metadata_calls':0,
            'context_sha256':context['context_sha256'],
            'preparation_sha256':file_hash(self.mcp.parent/'preparation.json')})
        self.full=self.root/'full/codex-fixture-canary.json'; self.full.parent.mkdir()
        fresh_json(self.full.parent/'preparation.json',{'purpose':'transport_canary','source_hashes':self.sources})
        (self.full.parent/'session').mkdir()
        fresh_json(self.full.parent/'session/assessment.json',{'valid':True,
            'evidence_mode':'synthetic_transport_fixture','model_authorship_proven':False,
            'process_reaped':True,'turns':2,'tool_calls':4})
        fresh_json(self.full.parent/'fixture-only-claim.json',{'fixture':True})
        self.seal(self.full,{'schema':'historical_source_review_codex_fixture_canary_v1',
            'passed':True,'actual_codex_cli':True,'actual_tinker_calls':0,'source_hashes':self.sources,
            'context_sha256':context['context_sha256'],
            'preparation_sha256':file_hash(self.full.parent/'preparation.json'),
            'assessment_sha256':file_hash(self.full.parent/'session/assessment.json'),
            'fixture_claim_sha256':file_hash(self.full.parent/'fixture-only-claim.json'),
            'codex_cli_sha256':file_hash(self.code),'python_sha256':file_hash(Path(sys.executable))})
        self.patches=[patch.object(runner,'ROOT',self.root/'live'),
            patch.object(runner,'__file__',str(self.live)),patch.object(runner.harness,'CODEX',str(self.code))]
        for p in self.patches:p.start()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()

    @staticmethod
    def seal(path,payload):
        payload={k:v for k,v in payload.items() if k!='result_sha256'}
        payload['result_sha256']=digest(payload); path.write_text(canonical(payload))

    def check(self):return runner.preflight(self.prepared,self.root/'budget',self.mcp,self.full)

    def test_preflight_does_not_spend_dispatch_or_authorize_download(self):
        r=self.check(); self.assertEqual(r['controller_stage'],'source_review')
        self.assertFalse(r['new_raw_download_admitted']); self.assertFalse(r['new_test_admitted'])
        self.assertEqual(self.budget.snapshot()['jobs'],{})
        self.assertFalse((self.prepared/'dispatch-claim.json').exists())

    def test_source_mutation_rejected(self):
        self.live.write_text('changed')
        with self.assertRaisesRegex(ValueError,'frozen source'): self.check()

    def test_binary_change_rejected(self):
        self.code.write_text('changed')
        with self.assertRaisesRegex(ValueError,'same-source/runtime'):self.check()

    def test_manifest_swap_rejected(self):
        p=self.prepared/'workspace/workspace.json'; v=load_json(p);v['purpose']='transport_canary'
        p.write_text(canonical(v))
        with self.assertRaises(ValueError):self.check()

    def test_consumed_workspace_rejected(self):
        runner.review.Broker(self.prepared/'workspace',self.prep['workspace_sha256']).call('inspect_source_context',{})
        with self.assertRaisesRegex(ValueError,'unconsumed'):self.check()

    def test_fixture_authorship_rejected_even_resealed(self):
        p=self.full.parent/'session/assessment.json'; v=load_json(p);v['model_authorship_proven']=True
        p.write_text(canonical(v)); r=load_json(self.full);r['assessment_sha256']=file_hash(p)
        self.seal(self.full,r)
        with self.assertRaisesRegex(ValueError,'fixture must prove'):self.check()

    def test_wrong_stdio_context_rejected(self):
        v=load_json(self.mcp);v['context_sha256']='a'*64;self.seal(self.mcp,v)
        with self.assertRaisesRegex(ValueError,'STDIO canary'):self.check()

    def test_reservation_blocks_but_is_not_spend(self):
        self.budget.reserve('fixture-held','learning','123','fixture','a'*64)
        with self.assertRaisesRegex(ValueError,'whole controller upper'):self.check()
        self.assertEqual(self.budget.snapshot()['metered_usd'],'0')

    def test_active_model_turn_prevents_duplicate(self):
        self.budget.reserve('fixture-turn-001','learning','1','fixture','a'*64)
        self.budget.dispatch('fixture-turn-001')
        with self.assertRaisesRegex(ValueError,'unresolved model'):self.check()

    def test_fixture_never_charges_real_ledger(self):
        manifest={'purpose':'transport_canary'}
        with patch.object(runner,'verify_preparation',return_value=(self.prep,manifest,{})):
            budget=PaidBudget.create(self.root/'other-budget',{'experiment_id':'real-study',
                'cap_usd':'10','target_usd':'10','buckets_usd':{'learning':'10'},'authority':'Test only.'})
            with self.assertRaisesRegex(ValueError,'fixture ledger'):
                runner.run_session(prepared=self.prepared,backend=ScriptedBackend(),budget=budget,
                    prompt='fixture',evidence_mode='synthetic_transport_fixture')
            self.assertEqual(budget.snapshot()['jobs'],{})


if __name__=='__main__':unittest.main()
