"""Exact first119 Review route, saved evidence and synthetic prompt; no API/Native."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import json,unittest
import earnings_population_clean_slate as clean
import earnings_population_coevolution as policy
from supervisor_harness import capacity_feedback_engine as engine

class Once119(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bound=clean.ACQUISITION_REVIEW_DESCRIPTOR;cls.fixed=engine.read(cls.bound)
        cls.real_read=staticmethod(engine.read)
        cls.plan=engine.read(engine.pin(clean.training.ROOT/'TRAIN25-FRONTIER-ROUND13-SIBLING2-SOURCE-PLAN-REVIEW119.json'))
    def modified(self,bound,change):
        value=deepcopy(self.real_read(bound));change(value)
        return patch.object(engine,'read',side_effect=lambda b:deepcopy(value) if b==bound else self.real_read(b))
    def test_exact_same_PROGRAM_parent_and_authority(self):
        fixed=clean.repair_metadata(self.bound,clean.ACQUISITION_REVIEW_ID)
        self.assertEqual(fixed['candidate'],fixed['original_candidate'])
        self.assertEqual(fixed['candidate']['parent'],self.plan['group_parent_id'])
        self.assertEqual(fixed['candidate']['axis'],'R')
        self.assertEqual(clean.repair_authority(clean.ACQUISITION_REVIEW_ID),policy.AUTHORITY)
    def test_original_private_blobs(self):
        clean.case_expectation_originals(self.fixed)
    def test_exact119_review_only_not_generic_retry(self):
        with patch.object(policy,'PLAN',str(clean.training.ROOT/'TRAIN25-FRONTIER-ROUND13-SIBLING2-SOURCE-PLAN-REVIEW119.json')):
            policy.route(clean.ACQUISITION_REVIEW_ID,13,False,True)
            for n,frozen,repair in ((13,False,False),(13,True,True),(12,False,True)):
                with self.assertRaises(ValueError):policy.route(clean.ACQUISITION_REVIEW_ID,n,frozen,repair)
            for ident in ('edgar-population-20261016-118','edgar-population-20261016-120'):
                with self.assertRaises(ValueError):policy.route(ident,13,False,True)
                with self.assertRaises(ValueError):clean.repair_metadata(self.bound,ident)
    def test_descriptor_hash_tamper(self):
        with self.assertRaises(ValueError):clean.acquisition_fixture_metadata(dict(self.bound,sha256='0'*64))
    def test_no_PROGRAM_parent_or_identity_mutation(self):
        for change in (lambda v:v.update(PROGRAM_unchanged=False),lambda v:v['candidate'].update(parent='03a'),
            lambda v:v['candidate']['R'].update(sha256='0'*64),lambda v:v.update(source_axis='H')):
            with self.modified(self.bound,change):
                with self.assertRaises(ValueError):clean.acquisition_fixture_metadata(self.bound)
    def test_exit_fee_pending_previous_paid_Review_fail_closed(self):
        for bound,change in ((self.fixed['closure'],lambda v:v.update(pending_count=1)),
            (self.fixed['closure'],lambda v:v.update(pending_full_reserved_nano_usd=1)),
            (self.fixed['closure'],lambda v:v.update(original_true_exit=1)),
            (self.fixed['closure'],lambda v:v.update(all_owned_settled=False)),
            (self.fixed['original_review'],lambda v:v.update(rationale='MODEL_REVIEW_REJECTED'))):
            with self.modified(bound,change):
                with self.assertRaises(ValueError):clean.acquisition_fixture_metadata(self.bound)
        real_exists=Path.exists
        target=clean.training.ROOT/'attempts/edgar-population-20261016-118/roles/review-01'
        with patch.object(Path,'exists',lambda p:True if p==target else real_exists(p)):
            with self.assertRaises(ValueError):clean.acquisition_fixture_metadata(self.bound)
    def test_cap_exact_equality_all8_and_independent_review(self):
        for bound,change in ((self.fixed['validation'],lambda v:v.update(test_bytes=32769)),
            (self.fixed['validation'],lambda v:v.update(run_cases_exact_equality_unchanged=False)),
            (self.fixed['validation'],lambda v:v.update(new_candidate_execution=True)),
            (self.fixed['validation'],lambda v:v.update(original_paid_Review_calls=1)),
            (self.fixed['exact_saved_replay'],lambda v:v.update(all8_exact_equal=False)),
            (self.fixed['exact_saved_replay'],lambda v:v.update(rows=v['rows'][:7])),
            (self.fixed['distinct_financial_review'],lambda v:v.update(verdict='UNKNOWN'))):
            with self.modified(bound,change):
                with self.assertRaises(ValueError):clean.acquisition_fixture_metadata(self.bound)
    def test_full8_exact_and_synthetic_only(self):
        raw=clean.e.checked(self.fixed['tests']);cases=json.loads(raw)
        self.assertEqual(len(raw),32244);self.assertEqual(len(cases),8)
        from earnings_open_program import run_cases
        fake=SimpleNamespace(run=lambda source,payload:dict(value=dict(a=1,extra=2)))
        self.assertFalse(run_cases(fake,'not executed',[dict(input={},expected=dict(a=1))])[0]['passed'])
        for index,count in ((6,2),(7,0)):
            t=cases[index]['expected']['anchor_history_research']['targets'][0]
            self.assertEqual(t['verified_periods'],count);self.assertEqual(t['selection'],'retain_parent')
            self.assertIsNone(t['recommendation'])
    def test_nonreview_role_denied(self):
        task=dict(mode='repair_review',repair=self.bound)
        manager=SimpleNamespace(value=dict(id=clean.ACQUISITION_REVIEW_ID,slots=dict(author=['offline-slot'])))
        with patch.object(clean,'read_task',return_value=(task,{})):
            with self.assertRaises(ValueError):clean.selection(manager,'author',({}, {},'offline-slot'),{})
    def test_prepare_exact119_guard_before_source_boundary(self):
        class AtSourceBoundary(Exception):pass
        with TemporaryDirectory(prefix='edgar119-prepare-') as td, \
            patch('earnings_population_runtime.ROOT',Path(td)),patch.object(clean,'_rate_scale_route'), \
            patch.object(clean,'_final_followup_route'),patch.object(clean,'repair_metadata',return_value=self.fixed), \
            patch.object(clean.training,'load_scope',return_value={}),patch.object(clean.training,'admit'), \
            patch('earnings_population_run.idle_snapshot',return_value={}), \
            patch.object(clean.subprocess,'run',return_value=SimpleNamespace(stdout='offline-source')), \
            patch('earnings_population_runtime.source_paths',side_effect=AtSourceBoundary):
            with self.assertRaises(AtSourceBoundary):
                clean.prepare(clean.ACQUISITION_REVIEW_ID,company_id='CIK0000003545',learning_round=13,repair=self.bound)
            for identifier,n in ((clean.ACQUISITION_REVIEW_ID,12),('edgar-population-20261016-120',13)):
                with self.assertRaises(ValueError):clean.prepare(identifier,company_id='CIK0000003545',learning_round=n,repair=self.bound)
            self.assertEqual(list(Path(td).iterdir()),[])
    def test_original_Services_Reviewer_prompt_literal_evidence(self):
        from earnings_population_services import Services
        from earnings_population_roles import PopulationReviewer
        origin=engine.read(self.plan['origin']);feedback=engine.read(origin['public_feedback'])
        task=dict(mode='repair_review',company_id='CIK0000003545',repair=self.bound,feedback=origin['public_feedback'],
            scaffold=engine.read(origin['carried_population']),round2_origin=self.plan['origin'],primary_task='Synthetic transport only')
        with TemporaryDirectory(prefix='edgar119-prompt-') as td:
            root=Path(td);slot=str(root/'review-01');service=Services.__new__(Services)
            service.runtime=engine.read(engine.read(self.fixed['closure'])['runtime'])
            service.runtime.update(id=clean.ACQUISITION_REVIEW_ID,root=td);service.runtime['slots']['review']=[slot]
            service.native_root=root;service.authored={};service.runner=object()
            service.case=lambda *a:dict(company=dict(cik=task['company_id']),state_api=SimpleNamespace(tools=SimpleNamespace(files={'questions.md':'Synthetic question','filing_index.tsv':'Synthetic index'})))
            service.matched_parent_probes=lambda *a:([],[])
            reviewer=PopulationReviewer.__new__(PopulationReviewer)
            reviewer.broker=SimpleNamespace(references=lambda:deepcopy(service.role_versions));service.role=lambda *a:reviewer
            seen=[]
            def capture(prompt,where,instructions,response_format,decode,artifact,status):
                seen.append(prompt);Path(where).mkdir()
                raw=engine.save(Path(where)/'offline-response.json',dict(synthetic_transport=True))
                engine.save(Path(where)/'review.json',dict(original=raw,review=dict(candidate_id=prompt['candidate_id'],accepted_for_exploration=False,rationale='Offline capture only')))
                return raw
            with patch.object(clean,'round2_origin',return_value=origin),patch.object(clean,'read_task',return_value=(task,{})), \
                patch.object(reviewer,'_run_open',side_effect=capture),patch('earnings_population_services.run_cases',return_value=[dict(passed=True)]*8), \
                patch('earnings_population_services.researcher.run',return_value=dict(receipt=dict(sha256='0'*64))), \
                patch('earnings_population_services.researcher.verify',return_value={}),patch('earnings_population_services.project',return_value={}), \
                patch('earnings_population_services.review_probe_output',return_value=dict(synthetic=True)):
                clean.repair_review(service,dict(roles=dict(review=service.review)),task)
            self.assertEqual(len(seen),1);extra=seen[0]['human_authorized_minimal_interface_repair']
            self.assertEqual(extra['complete_public_feedback'],feedback)
            self.assertEqual(extra['distinct_synthetic_financial_review'],engine.read(self.fixed['distinct_financial_review']))
            self.assertIn('placeholders',extra['validation_summary'])
            self.assertEqual(extra['fixture_diagnosis'],engine.read(self.fixed['validation']))
            self.assertEqual(seen[0]['declared_frontier_test'],policy.declared_test(origin))
            self.assertEqual(service.authored[self.fixed['candidate']['id']]['source'],clean.e.checked(self.fixed['source']).decode())

if __name__=='__main__':unittest.main()
