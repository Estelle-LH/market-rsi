"""Offline107 routing/unchanged-code/exact-case guards; no model/Native execution."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import json
import unittest
import earnings_population_clean_slate as clean
import earnings_population_coevolution as policy
from supervisor_harness import capacity_feedback_engine as engine

class Once107(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixed=engine.read(clean.CASE_EXPECTATION_DESCRIPTOR)
        cls.real_read=staticmethod(engine.read)
        # A historical107 regression must not silently use a later round's parent.
        cls.plan=engine.read(engine.pin(clean.training.ROOT/'TRAIN25-FRONTIER-ROUND11-SOURCE-PLAN-V3.json'))

    def modified(self,bound,change):
        value=deepcopy(self.real_read(bound));change(value)
        def read(other):return deepcopy(value) if other==bound else self.real_read(other)
        return patch.object(engine,'read',side_effect=read)

    def test_exact_metadata_and_same_R_H(self):
        fixed=clean.repair_metadata(clean.CASE_EXPECTATION_DESCRIPTOR,clean.CASE_EXPECTATION_REVIEW_ID)
        self.assertEqual(fixed['candidate'],fixed['original_candidate'])
        self.assertEqual(fixed['candidate']['axis'],'H')
        self.assertEqual(fixed['candidate']['parent'],self.plan['group_parent_id'])

    def test_exact_private_original_blobs(self):
        clean.case_expectation_originals(self.fixed)

    def test_route107_only_review(self):
        with patch.object(policy,'PLAN',str(clean.training.ROOT/'TRAIN25-FRONTIER-ROUND11-SOURCE-PLAN-V3.json')):
            policy.route(clean.CASE_EXPECTATION_REVIEW_ID,11,False,True)
            for n,frozen,repairing in ((11,False,False),(11,True,True),(12,False,True)):
                with self.assertRaises(ValueError):policy.route(clean.CASE_EXPECTATION_REVIEW_ID,n,frozen,repairing)

    def test_no_generic_repair_or_old_ID(self):
        for identifier in ('edgar-population-20261016-106','edgar-population-20261016-108'):
            with self.assertRaises(ValueError):policy.route(identifier,11,False,True)
            with self.assertRaises(ValueError):clean.repair_metadata(clean.CASE_EXPECTATION_DESCRIPTOR,identifier)

    def test_source_binding_tamper_rejected(self):
        bad=dict(clean.CASE_EXPECTATION_DESCRIPTOR,sha256='0'*64)
        with self.assertRaises(ValueError):clean.case_expectation_metadata(bad)

    def test_changed_PROGRAM_or_parent_rejected(self):
        for mutate in (lambda x:x.update(PROGRAM_unchanged=False),
                       lambda x:x['candidate'].update(parent='03a87b7b'),
                       lambda x:x['candidate']['H'].update(sha256='0'*64)):
            with self.modified(clean.CASE_EXPECTATION_DESCRIPTOR,mutate):
                with self.assertRaises(ValueError):clean.case_expectation_metadata(clean.CASE_EXPECTATION_DESCRIPTOR)

    def test_bad_original_exit_or_noncase_rejection_rejected(self):
        for bound,mutate in ((self.fixed['closure'],lambda x:x.update(original_true_exit=1)),
                             (self.fixed['closure'],lambda x:x.update(pending_count=1)),
                             (self.fixed['original_review'],lambda x:x.update(rationale='MODEL_REVIEW_REJECTED'))):
            with self.modified(bound,mutate):
                with self.assertRaises(ValueError):clean.case_expectation_metadata(clean.CASE_EXPECTATION_DESCRIPTOR)

    def test_incomplete_or_host_execution_validation_rejected(self):
        for mutate in (lambda x:x.update(host_candidate_execution=True),lambda x:x.update(test_bytes=32769),
                       lambda x:x.update(run_cases_exact_equality_unchanged=False)):
            with self.modified(self.fixed['validation'],mutate):
                with self.assertRaises(ValueError):clean.case_expectation_metadata(clean.CASE_EXPECTATION_DESCRIPTOR)
        with self.modified(self.fixed['exact_saved_replay'],lambda x:x.update(all6_exact_equal=False)):
            with self.assertRaises(ValueError):clean.case_expectation_metadata(clean.CASE_EXPECTATION_DESCRIPTOR)

    def test_six_full_tests_fit_original_cap(self):
        raw=clean.e.checked(self.fixed['tests']);cases=json.loads(raw)
        self.assertEqual(len(raw),27145);self.assertLessEqual(len(raw),32768)
        self.assertEqual(len(cases),6);self.assertTrue(all(set(c)=={'input','expected'} for c in cases))

    def test_nonreview_selection_rejected_before_execution(self):
        slot=str(clean.training.ROOT/'offline-only-uncreated-slot')
        task=dict(mode='repair_review',repair=clean.CASE_EXPECTATION_DESCRIPTOR)
        manager=SimpleNamespace(value=dict(id=clean.CASE_EXPECTATION_REVIEW_ID,slots=dict(author=[slot])))
        with patch.object(clean,'read_task',return_value=(task,{})):
            with self.assertRaises(ValueError):clean.selection(manager,'author',({}, {},slot),{})

    def test_H_profile_assembly_without_paid_callback(self):
        with TemporaryDirectory(prefix='edgar107-mocked-review-') as td:
            task=dict(company_id='CIK0000003545',repair=clean.CASE_EXPECTATION_DESCRIPTOR,
                feedback=self.fixed['original_feedback'],scaffold={})
            service=SimpleNamespace(runtime=dict(id=clean.CASE_EXPECTATION_REVIEW_ID,root=td,slots=dict(review=['offline-slot'])),authored={})
            seen=[]
            def review(child,state,slot):
                seen.append((child,state,slot));return dict(accepted_for_exploration=False,mocked_offline=True)
            clean.repair_review(service,dict(roles=dict(review=review)),task)
            authored=service.authored[self.fixed['candidate']['id']]
            self.assertEqual(authored['source'],clean.e.checked(self.fixed['candidate']['H']).decode())
            self.assertEqual(authored['parsed']['profile']['axis'],'H')
            self.assertEqual(len(authored['parsed']['cases']),6);self.assertEqual(len(seen),1)
            self.assertTrue(authored['human_interface_repair']['PROGRAM_unchanged'])

    def test_run_cases_exact_contract_unchanged(self):
        from earnings_open_program import run_cases
        fake=SimpleNamespace(run=lambda source,payload:dict(value=dict(a=1,extra=2)))
        self.assertFalse(run_cases(fake,'not executed',[dict(input={},expected=dict(a=1))])[0]['passed'])
        self.assertTrue(run_cases(fake,'not executed',[dict(input={},expected=dict(a=1,extra=2))])[0]['passed'])

    def test_actual_Services_and_Reviewer_prompt_contains_complete_feedback(self):
        """Real producer/Reviewer; only isolation and transport replaced, no API."""
        from earnings_population_services import Services
        from earnings_population_roles import PopulationReviewer
        with TemporaryDirectory(prefix='edgar107-actual-prompt-') as td:
            root=Path(td);slot=str(root/'review-01')
            service=Services.__new__(Services)
            service.runtime=engine.read(engine.pin(clean.training.ROOT/'inputs'/clean.CASE_EXPECTATION_REVIEW_ID/'runtime-unreviewed.json'))
            service.runtime['root']=str(root)
            service.runtime['slots']['review']=[slot]
            service.native_root=root;service.authored={};service.runner=object()
            service.case=lambda child,where:dict(company=dict(cik='CIK0000003545'),
                state_api=SimpleNamespace(tools=SimpleNamespace(files={'questions.md':'Public question fixture'})))
            reviewer=PopulationReviewer.__new__(PopulationReviewer)
            reviewer.broker=SimpleNamespace(references=lambda:deepcopy(service.role_versions))
            service.role=lambda *args:reviewer
            seen=[]
            def capture(prompt,where,instructions,response_format,decode,artifact,status):
                # This is the original _run_open initial user-message encoding.
                payload=dict(input=[dict(role='user',content=json.dumps(prompt,sort_keys=True,ensure_ascii=False,allow_nan=False))])
                seen.append(payload)
                Path(where).mkdir()
                raw=engine.save(Path(where)/'offline-response.json',dict(synthetic_transport=True))
                engine.save(Path(where)/'review.json',dict(original=raw,review=dict(
                    candidate_id=prompt['candidate_id'],accepted_for_exploration=False,rationale='Offline capture only')))
                return raw
            task=engine.read(engine.read(service.runtime['forecast_study'])['clean_slate_task'])
            feedback=engine.read(task['feedback'])
            with patch.object(clean,'round2_origin',return_value=engine.read(self.plan['origin'])), \
                 patch.object(reviewer,'_run_open',side_effect=capture), \
                 patch('earnings_population_services.run_cases',return_value=[dict(passed=True)]*6):
                clean.repair_review(service,dict(roles=dict(review=service.review)),task)
            self.assertEqual(len(seen),1)
            self.assertTrue(clean._contains_summary(seen[0],feedback))
            actual=json.loads(seen[0]['input'][0]['content'])
            delivered=actual['human_authorized_minimal_interface_repair']['complete_public_feedback']
            self.assertEqual(delivered,feedback)
            self.assertEqual(len(delivered['rows']),25)
            self.assertEqual(delivered['observable_mechanism_test'],feedback['observable_mechanism_test'])
            old_prompt=deepcopy(actual)
            del old_prompt['human_authorized_minimal_interface_repair']['complete_public_feedback']
            self.assertFalse(clean._contains_summary(dict(input=[dict(role='user',content=json.dumps(old_prompt))]),feedback))
            self.assertEqual(actual['declared_frontier_test'],policy.declared_test(engine.read(self.plan['origin'])))
            self.assertEqual(service.authored[self.fixed['candidate']['id']]['source'],clean.e.checked(self.fixed['candidate']['H']).decode())

    def test_closure_helper_only_finite_guard_delta(self):
        original=(clean.training.ROOT/'close-clean-continuous-v3.py').read_text()
        expected=original.replace("assert ident==f'edgar-population-20261016-{number}' and number>=89 and code in ('0','1')",
            "assert ident=='edgar-population-20261016-107' and number==107 and code in ('0','1')")
        expected=expected.replace("  and mode in ('proposal','evaluate'))  # read_task already verifies declared proposal/frozen route",
            "  and (mode in ('proposal','evaluate') or number==107 and logical_round==11 and mode=='repair_review'))  # exact once107 only")
        path=clean.training.ROOT/'close-clean107-review.py';source=path.read_text()
        self.assertEqual(source,expected);compile(source,str(path),'exec')

    def test_admission_helper_has_no_model_or_legacy_proposal_route(self):
        path=clean.training.ROOT/'admit-clean107-case-review.py';source=path.read_text()
        compile(source,str(path),'exec')
        self.assertIn("original['id']==ident=='edgar-population-20261016-107'",source)
        self.assertIn("assert task['mode']=='repair_review'",source)
        self.assertIn("for k in ('original_review','original_case_results')",source)
        for forbidden in ('RawOpenAIHTTP','DockerRunner(','.create_response('):self.assertNotIn(forbidden,source)

if __name__=='__main__':unittest.main()
