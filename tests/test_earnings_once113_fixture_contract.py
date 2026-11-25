"""Exact finite113 source/test/feedback boundaries; no provider/Native execution."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import json,unittest
import earnings_population_clean_slate as clean
import earnings_population_coevolution as policy
from supervisor_harness import capacity_feedback_engine as engine

class Once113(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bound=clean.FIXTURE_REVIEW_DESCRIPTOR;cls.fixed=engine.read(cls.bound)
        cls.real_read=staticmethod(engine.read)
        cls.plan=engine.read(engine.pin(clean.training.ROOT/'TRAIN25-FRONTIER-ROUND12-SOURCE-PLAN-V4.json'))
    def modified(self,bound,change):
        value=deepcopy(self.real_read(bound));change(value)
        return patch.object(engine,'read',side_effect=lambda b:deepcopy(value) if b==bound else self.real_read(b))
    def test_exact_unchanged_PROGRAM_and_parent(self):
        fixed=clean.repair_metadata(self.bound,clean.FIXTURE_REVIEW_ID)
        self.assertEqual(fixed['candidate'],fixed['original_candidate'])
        self.assertEqual(fixed['candidate']['parent'],self.plan['group_parent_id'])
        self.assertEqual(fixed['candidate']['axis'],'H')
        self.assertEqual(clean.repair_authority(clean.FIXTURE_REVIEW_ID),policy.AUTHORITY)
    def test_original_private_blobs(self):
        clean.case_expectation_originals(self.fixed)
    def test_only_exact113_Review_route(self):
        with patch.object(policy,'PLAN',str(clean.training.ROOT/'TRAIN25-FRONTIER-ROUND12-SOURCE-PLAN-V4.json')):
            policy.route(clean.FIXTURE_REVIEW_ID,12,False,True)
            for n,frozen,repair in ((12,False,False),(12,True,True),(11,False,True)):
                with self.assertRaises(ValueError):policy.route(clean.FIXTURE_REVIEW_ID,n,frozen,repair)
            for ident in ('edgar-population-20261016-112','edgar-population-20261016-114'):
                with self.assertRaises(ValueError):policy.route(ident,12,False,True)
                with self.assertRaises(ValueError):clean.repair_metadata(self.bound,ident)
    def test_descriptor_hash_tamper(self):
        with self.assertRaises(ValueError):clean.fixture_contract_metadata(dict(self.bound,sha256='0'*64))
    def test_code_or_parent_tamper(self):
        for change in (lambda v:v.update(PROGRAM_unchanged=False),lambda v:v['candidate'].update(parent='03a'),
                       lambda v:v['candidate']['H'].update(sha256='0'*64)):
            with self.modified(self.bound,change):
                with self.assertRaises(ValueError):clean.fixture_contract_metadata(self.bound)
    def test_prior_fee_exit_or_paid_review_rejection(self):
        for bound,change in ((self.fixed['closure'],lambda v:v.update(pending_count=1)),
            (self.fixed['closure'],lambda v:v.update(original_true_exit=1)),
            (self.fixed['closure'],lambda v:v.update(all_owned_settled=False)),
            (self.fixed['original_review'],lambda v:v.update(rationale='MODEL_REVIEW_REJECTED'))):
            with self.modified(bound,change):
                with self.assertRaises(ValueError):clean.fixture_contract_metadata(self.bound)
    def test_test_cap_equality_and_diagnostics_required(self):
        for bound,change in ((self.fixed['validation'],lambda v:v.update(test_bytes=32769)),
            (self.fixed['validation'],lambda v:v.update(run_cases_exact_equality_unchanged=False)),
            (self.fixed['validation'],lambda v:v.update(host_candidate_execution=True)),
            (self.fixed['full_diagnostic'],lambda v:v.update(rows=v['rows'][:4])),
            (self.fixed['distinct_financial_review'],lambda v:v.update(verdict='UNKNOWN')),
            (self.fixed['exact_saved_replay'],lambda v:v.update(all4_exact_equal=False))):
            with self.modified(bound,change):
                with self.assertRaises(ValueError):clean.fixture_contract_metadata(self.bound)
    def test_four_full_exact_cases_not_fake_six_passes(self):
        raw=clean.e.checked(self.fixed['tests']);cases=json.loads(raw)
        self.assertEqual(len(raw),32731);self.assertEqual(len(cases),4)
        self.assertEqual(len(engine.read(self.fixed['full_diagnostic'])['rows']),6)
        self.assertTrue(all(set(c)=={'input','expected'} for c in cases))
        from earnings_open_program import run_cases
        fake=SimpleNamespace(run=lambda source,payload:dict(value=dict(a=1,extra=2)))
        self.assertFalse(run_cases(fake,'not executed',[dict(input={},expected=dict(a=1))])[0]['passed'])
    def test_nonreview_role_denied(self):
        task=dict(mode='repair_review',repair=self.bound)
        manager=SimpleNamespace(value=dict(id=clean.FIXTURE_REVIEW_ID,slots=dict(author=['offline-slot'])))
        with patch.object(clean,'read_task',return_value=(task,{})):
            with self.assertRaises(ValueError):clean.selection(manager,'author',({}, {},'offline-slot'),{})
    def test_actual_prepare_passes_exact113_round_guard_before_source_boundary(self):
        # Admission/Git/source transport are explicit seams; no runtime is saved.
        class AtSourceBoundary(Exception):pass
        with TemporaryDirectory(prefix='edgar113-prepare-boundary-') as td, \
             patch('earnings_population_runtime.ROOT',Path(td)), \
             patch.object(clean,'_rate_scale_route'),patch.object(clean,'_final_followup_route'), \
             patch.object(clean,'repair_metadata',return_value=self.fixed), \
             patch.object(clean.training,'load_scope',return_value={}),patch.object(clean.training,'admit'), \
             patch('earnings_population_run.idle_snapshot',return_value={}), \
             patch.object(clean.subprocess,'run',return_value=SimpleNamespace(stdout='offline-source')), \
             patch('earnings_population_runtime.source_paths',side_effect=AtSourceBoundary):
            with self.assertRaises(AtSourceBoundary):
                clean.prepare(clean.FIXTURE_REVIEW_ID,company_id='CIK0000003545',learning_round=12,repair=self.bound)
            for identifier,n in ((clean.FIXTURE_REVIEW_ID,11),('edgar-population-20261016-114',12)):
                with self.assertRaises(ValueError):
                    clean.prepare(identifier,company_id='CIK0000003545',learning_round=n,repair=self.bound)
            self.assertEqual(list(Path(td).iterdir()),[])
    def test_actual_original_Services_Reviewer_prompt(self):
        from earnings_population_services import Services
        from earnings_population_roles import PopulationReviewer
        origin=engine.read(self.plan['origin']);feedback=engine.read(origin['public_feedback'])
        task=dict(company_id='CIK0000003545',repair=self.bound,feedback=origin['public_feedback'],
            scaffold=engine.read(origin['carried_population']))
        with TemporaryDirectory(prefix='edgar113-actual-prompt-') as td:
            root=Path(td);slot=str(root/'review-01');service=Services.__new__(Services)
            service.runtime=engine.read(engine.read(self.fixed['closure'])['runtime'])
            service.runtime.update(id=clean.FIXTURE_REVIEW_ID,root=td)
            service.runtime['slots']['review']=[slot];service.native_root=root;service.authored={};service.runner=object()
            service.case=lambda child,where:dict(company=dict(cik=task['company_id']),
                state_api=SimpleNamespace(tools=SimpleNamespace(files={'questions.md':'Synthetic public question'})))
            reviewer=PopulationReviewer.__new__(PopulationReviewer)
            reviewer.broker=SimpleNamespace(references=lambda:deepcopy(service.role_versions));service.role=lambda *a:reviewer
            seen=[]
            def capture(prompt,where,instructions,response_format,decode,artifact,status):
                seen.append(prompt);Path(where).mkdir()
                raw=engine.save(Path(where)/'offline-response.json',dict(synthetic_transport=True))
                engine.save(Path(where)/'review.json',dict(original=raw,review=dict(candidate_id=prompt['candidate_id'],accepted_for_exploration=False,rationale='Offline capture only')))
                return raw
            with patch.object(clean,'round2_origin',return_value=origin),patch.object(reviewer,'_run_open',side_effect=capture), \
                 patch('earnings_population_services.run_cases',return_value=[dict(passed=True)]*4):
                clean.repair_review(service,dict(roles=dict(review=service.review)),task)
            self.assertEqual(len(seen),1)
            extra=seen[0]['human_authorized_minimal_interface_repair']
            self.assertEqual(extra['complete_public_feedback'],feedback)
            self.assertEqual(extra['full_corrected_fixture_diagnostic'],engine.read(self.fixed['full_diagnostic']))
            self.assertEqual(len(extra['full_corrected_fixture_diagnostic']['rows']),6)
            self.assertEqual(extra['original_case_results'],self.fixed['original_case_results'])
            self.assertEqual(extra['distinct_synthetic_financial_review'],engine.read(self.fixed['distinct_financial_review']))
            self.assertEqual(seen[0]['declared_frontier_test'],policy.declared_test(origin))
            self.assertEqual(service.authored[self.fixed['candidate']['id']]['source'],clean.e.checked(self.fixed['source']).decode())

if __name__=='__main__':unittest.main()
