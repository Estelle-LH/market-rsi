"""Synthetic original receipts and filings; no candidate/provider execution."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import earnings_open_author_followthrough as flow
from edgar_forecast_tools import FilingTools
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_open_researcher as evidence_fixture
import test_earnings_research_state as state_fixture


class Author14ColdProbeTests(unittest.TestCase):
    def setUp(self):
        data=state_fixture.ResearchStateTests(); data.setUp(); self.addCleanup(data.doCleanups)
        self.root,self.company,self.files=data.root,data.company,data.files
        self.number=0
        self.source=evidence_fixture.SOURCE
        self.authored={'decision_sha256':'a'*64,'source_text':self.source,'test_text':'CASES=[]'}
        original={'status':'completed','error':None,'output':[{'type':'message','role':'assistant',
            'content':[{'type':'output_text','text':json.dumps(self.authored)}]}]}
        self.original=engine.save(self.root/'author-original.json',original)
        self.runtime=engine.save(self.root/'runtime.json',{'root':str(self.root/'probe-owner')})
        self.prepared=engine.save(self.root/'prepared.json',{'grant':engine.save(self.root/'grant.json',{'synthetic':True}),
            'runtime':self.runtime})
        self.result={'prepared':self.prepared,'original':self.original,'owner_terminal':{'synthetic':True}}
        self.advice={'historical_cells':[{'invented':True,'value':100,'quote':self.files['filings/old.md']}]}

    def completed_probe(self, *, advice=None, requests=None):
        self.number+=1
        runner=evidence_fixture.ScriptedReceiptRunner(self.root/f'runner-{self.number}',[
            {'research_requests':requests if requests is not None else evidence_fixture.REQUESTS},
            self.advice if advice is None else advice])
        payload=flow.cold_payload(self.company)
        execution=flow.researcher.run(runner,self.source,payload,FilingTools(self.company))
        value={'author_original':self.original,'source_sha256':flow.e.digest(self.source.encode()),
            'payload':payload,'execution':execution}
        return engine.save(self.root/f'probe-{self.number}.json',value),value,runner

    def test_exact14_authority_requires_approved_rejected12_and_unchanged_window_credit(self):
        window={'issued_utc':'2026-10-15T20:57:14Z','cutoff_utc':'2026-10-15T22:26:14Z',
            'deadline_utc':'2026-10-15T22:27:14Z'}
        scope={'schema':'earnings_author_followthrough_authority_v1','human_authorization':flow.AUTHORIZATION,
            'author_id':'edgar-research-20261015-14','forecast_id':'edgar-research-20261015-15',
            'parent':'edgar-feedback-20261015-11','parent_result':{'sha256':flow.PARENT_RESULT_SHA},
            'parent_audit':{'sha256':flow.PARENT_AUDIT_SHA},'baseline_row':4283,'no_retry':True,
            'continuation_cumulative_cap_nano_usd':10_000_000_000,'original_total_cap_nano_usd':200_000_000_000,
            'window':window,'requires_cold_probe':True,
            'continuation_human_approval':'允许，新ID修复后测试和独立审查，通过才预测',
            'failed_author_result':{'path':'synthetic-failed12','sha256':'f'*64},
            'failed_candidate_review':{'path':'synthetic-review12',
                'sha256':'bff68c403a47cd125ac16de73140b877acd5726d9172575b95eba7c6932af3dd'}}
        failed={'original':{'sha256':'9a08f43110c5b0837763cb451b96c5704a5d417376d4869e91b797af5b533334'}}
        rejected={'verdict':'REJECT_AUTHOR_CANDIDATE_ONE_FORECAST'}
        def read(binding):
            if binding.get('path')=='synthetic-failed12': return failed
            if binding.get('path')=='synthetic-review12': return rejected
            return engine.read(binding)
        changes=[None,{'author_id':'edgar-research-20261015-16'},
            {'forecast_id':'edgar-research-20261015-13'},{'continuation_human_approval':'unapproved'},
            {'requires_cold_probe':False},{'no_retry':False},{'baseline_row':4632},
            {'continuation_cumulative_cap_nano_usd':11_000_000_000},
            {'original_total_cap_nano_usd':201_000_000_000},
            {'window':dict(window,deadline_utc='2099-01-01T00:00:00Z')}]
        with mock.patch.object(flow,'read',side_effect=read),mock.patch.object(flow.fresh,'policy',return_value={'window':window}),\
                mock.patch.object(flow.fresh,'pilot_cap',return_value=10_000_000_000):
            for i,change in enumerate(changes):
                path=self.root/f'scope-{i}.json'; engine.save(path,dict(scope,**(change or {})))
                with self.subTest(change=change),mock.patch.object(flow,'SCOPE',path):
                    if change is None: self.assertEqual(flow.authority(),scope)
                    else:
                        with self.assertRaises(ValueError): flow.authority()
            path=self.root/'scope-bad-evidence.json'; engine.save(path,scope)
            with mock.patch.object(flow,'SCOPE',path):
                failed['original']['sha256']='0'*64
                with self.assertRaises(ValueError): flow.authority()
                failed['original']['sha256']='9a08f43110c5b0837763cb451b96c5704a5d417376d4869e91b797af5b533334'
                rejected['verdict']='PASS_AUTHOR_CANDIDATE_ONE_FORECAST'
                with self.assertRaises(ValueError): flow.authority()

    def test_shared80_includes_closed12_and_new14_review_probe_and15_failed_roots(self):
        scope={'author_id':'edgar-research-20261015-14','forecast_id':'edgar-research-20261015-15',
            'requires_cold_probe':True}
        roots=[('12','code',10),('12','review-code',9),('14','code',20),('14','review-code',20),
            ('14','cold-probe-code',10),('15','code',10)]
        for identifier,name,count in roots:
            home=self.root/'attempts'/('edgar-research-20261015-'+identifier)/name
            home.mkdir(parents=True)
            for n in range(count):
                call=home/f'call-{n:032x}'; call.mkdir()
                engine.save(call/'result.json',{'status':'FAILED_NO_RETRY'})
        with mock.patch.object(flow,'ROOT',self.root),mock.patch.object(flow,'authority',return_value=scope):
            self.assertEqual(flow.containers_remaining(),1)
            (self.root/'attempts/edgar-research-20261015-14/cold-probe-code'/('call-'+'f'*32)).mkdir()
            with self.assertRaises(ValueError): flow.containers_remaining()

    def test_cold_payload_contains_exact_original_questions_index_and_empty_records(self):
        self.assertEqual(flow.cold_payload(self.company),{'stage':'forecast','questions':self.files['questions.md'],
            'filing_index':self.files['filing_index.tsv'],'records':[]})
        path=Path(self.company['visible_root'])/'filings/old.md'; path.write_text('changed snapshot')
        with self.assertRaises(ValueError): flow.cold_payload(self.company)

    def test_actual_cold_probe_uses_original_filingtools_and_same_source_twice(self):
        runner=evidence_fixture.ScriptedReceiptRunner(self.root/'probe-owner/cold-probe-code',[
            {'research_requests':evidence_fixture.REQUESTS},self.advice])
        with mock.patch.object(flow,'owner_terminal',return_value=self.result['owner_terminal']),\
                mock.patch.object(flow.original_capacity,'task',return_value=(self.company,{})),\
                mock.patch.object(flow,'containers_remaining',return_value=37),\
                mock.patch.object(flow,'DockerRunner',return_value=runner) as constructor,\
                mock.patch.object(flow.researcher,'run',wraps=flow.researcher.run) as run:
            result_binding=engine.save(self.root/'author-result.json',self.result)
            binding=flow.cold_probe(result_binding)
            constructor.assert_called_once_with(self.root/'probe-owner/cold-probe-code',max_calls=37)
            self.assertEqual(run.call_count,1); self.assertIsInstance(run.call_args.args[3],FilingTools)
            self.assertEqual(flow.cold_probe_check(binding,self.result),self.advice)
        self.assertEqual([item['source'] for item in runner.invocations],[self.source,self.source])
        self.assertEqual(runner.invocations[0]['payload']['records'],[])
        observations=runner.invocations[1]['payload']['research_observations']
        self.assertEqual(observations[0]['output']['text'],self.files['filings/old.md'])
        self.assertEqual(runner.calls,2)

    def test_empty_cells_and_search_only_advice_are_not_cold_start_success(self):
        variants=[({'historical_cells':[]},None),(self.advice,[evidence_fixture.REQUESTS[1]])]
        for path,offset in (('questions.md',0),('filing_index.tsv',0),
                ('filings/old.md',len(self.files['filings/old.md']))):
            variants.append((self.advice,[{'tool':'read_file','arguments':{
                'path':path,'offset':offset,'characters':20000}}]))
        with mock.patch.object(flow.original_capacity,'task',return_value=(self.company,{})):
            for advice,requests in variants:
                binding,_,_=self.completed_probe(advice=advice,requests=requests)
                with self.assertRaises(ValueError): flow.cold_probe_check(binding,self.result)

    def test_forged_source_original_payload_observations_and_raw_receipt_rejected(self):
        with mock.patch.object(flow.original_capacity,'task',return_value=(self.company,{})):
            for field in ('source_sha256','author_original','payload','observations','input','stdout'):
                binding,value,runner=self.completed_probe()
                self.assertEqual(flow.cold_probe_check(binding,self.result),self.advice)
                bad=deepcopy(value)
                if field=='source_sha256': bad[field]='0'*64
                elif field=='author_original': bad[field]=self.prepared
                elif field=='payload': bad[field]['records']=[{'injected':True}]
                elif field=='observations': bad['execution']['research_observations'][0]['output']['text']='forged'
                else:
                    name='input.json' if field=='input' else 'stdout.bin'
                    (Path(runner.invocations[1]['receipt']['path']).parent/name).write_bytes(b'forged')
                forged=engine.save(self.root/f'forged-{self.number}.json',bad)
                with self.subTest(field=field),self.assertRaises(ValueError): flow.cold_probe_check(forged,self.result)

    def test_forecast_requires_probe_binding_identical_to_distinct_candidate_review(self):
        binding,_,_=self.completed_probe()
        review=engine.save(self.root/'candidate-review.json',{'cold_probe':{'path':'other','sha256':'0'*64}})
        value={'stage':'forecast','cold_probe':binding,'author_result':engine.save(self.root/'result.json',self.result),
            'candidate_specification':engine.save(self.root/'spec.json',{}),'candidate_review':review}
        with mock.patch.object(flow,'validate_prepared',return_value=(value,{})),\
                mock.patch.object(flow,'candidate_gate',return_value=(self.authored,{})),\
                mock.patch.object(flow,'authority',return_value={'requires_cold_probe':True}),\
                mock.patch.object(flow,'cold_probe_check',return_value=self.advice) as probe,\
                mock.patch.object(flow,'open_capacity_runtime') as owner:
            with self.assertRaises(ValueError): flow.run_forecast({'synthetic':'prepared'},{'synthetic':'review'})
            probe.assert_called_once_with(binding,self.result); owner.assert_not_called()

    def test_prepare_requires_exact_reviewed_probe_before_home_or_archive_creation(self):
        author_id='edgar-research-20261015-14'; forecast_id='edgar-research-20261015-15'
        home=self.root/'attempts'/author_id; home.mkdir(parents=True)
        engine.save(home/'author-result.json',self.result); engine.save(home/'candidate-specification.json',{})
        probe=engine.save(home/'cold-probe.json',{'synthetic':'probe'})
        engine.save(self.root/'AUTHOR14-CANDIDATE-REVIEW.json',{'cold_probe':{'wrong':'binding'}})
        grant=engine.save(self.root/'old-grant.json',{'ledger':str(self.root/'unused-ledger'),'python':{'synthetic':True}})
        old={'handoff':{'old_runtime':engine.save(self.root/'old-runtime.json',{}),
            'old_episode':engine.save(self.root/'old-episode.json',{'grant':grant})}}
        scope={'author_id':author_id,'forecast_id':forecast_id,'requires_cold_probe':True}
        with mock.patch.object(flow,'ROOT',self.root),mock.patch.object(flow,'authority',return_value=scope),\
                mock.patch.object(flow,'prior',return_value=old),mock.patch.object(flow,'accounting'),\
                mock.patch.object(flow,'verify_current_python'),mock.patch.object(flow.namespace,'native_paths',return_value={}),\
                mock.patch.object(flow.subprocess,'run',side_effect=[SimpleNamespace(stdout=b''),SimpleNamespace(stdout='c'*40)]),\
                mock.patch.object(flow,'source_bindings',return_value={}),mock.patch.object(flow,'verify_sources'),\
                mock.patch.object(flow,'candidate_gate',return_value=(self.authored,{})),\
                mock.patch.object(flow,'cold_probe_check',return_value=self.advice) as check:
            with self.assertRaises(ValueError): flow.prepare('forecast')
            check.assert_called_once_with(probe,self.result)
        self.assertFalse((self.root/'inputs'/forecast_id).exists())


if __name__=='__main__': unittest.main()
