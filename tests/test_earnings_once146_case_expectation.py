"""Finite unchanged145 PROGRAM FIRST Review146; offline, no API/candidate run."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import importlib.util,json,unittest
import earnings_population_clean_slate as clean
import earnings_population_coevolution as policy
import earnings_population_case_expectation146 as repair
from supervisor_harness import capacity_feedback_engine as e

class Once146(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixed=e.read(repair.DESCRIPTOR);cls.real_read=staticmethod(e.read)
        cls.plan=e.read(e.pin(clean.training.ROOT/'TRAIN25-DEPTH7-ROUND16-SOURCE-PLAN146.json'))
    def changed(self,bound,change):
        v=deepcopy(self.real_read(bound));change(v)
        return patch.object(e,'read',side_effect=lambda b:deepcopy(v) if b==bound else self.real_read(b))
    def test_exact_metadata_private_originals(self):
        f=clean.repair_metadata(repair.DESCRIPTOR,repair.REVIEW_ID)
        clean.case_expectation_originals(f)
        self.assertEqual(f['candidate'],f['original_candidate']);self.assertEqual(f['candidate']['parent'],self.plan['group_parent_id'])
    def test_strict_route_before_legacy_return(self):
        with patch.object(policy,'PLAN',str(clean.training.ROOT/'TRAIN25-DEPTH7-ROUND16-SOURCE-PLAN146.json')):
            policy.route(repair.REVIEW_ID,16,False,True)
            for n,fr,r in ((1,False,True),(None,False,True),(True,False,True),(16.0,False,True),
                (15,False,True),(16,True,True),(16,None,True),(16,False,False),(16,False,1)):
                with self.assertRaises(ValueError):policy.route(repair.REVIEW_ID,n,fr,r)
    def test_prepare_rejects_invalid_before_output(self):
        for n,fr,r in ((1,None,repair.DESCRIPTOR),(True,None,repair.DESCRIPTOR),(16.0,None,repair.DESCRIPTOR),
            (None,None,repair.DESCRIPTOR),(16,{},repair.DESCRIPTOR),(16,None,None),(16,None,dict(repair.DESCRIPTOR,sha256='0'*64))):
            with self.assertRaises(ValueError):clean.prepare(repair.REVIEW_ID,company_id='CIK0000003545',learning_round=n,frozen_candidate=fr,repair=r)
    def test_unchanged_program_parent_cap_and_identity(self):
        for change in (lambda v:v.update(PROGRAM_unchanged=False),lambda v:v.update(C_A_regeneration=True),
            lambda v:v['candidate'].update(parent='03a'),lambda v:v['candidate']['R'].update(sha256='0'*64),
            lambda v:v['candidate']['H'].update(sha256='0'*64),lambda v:v.update(logical_round=16.0)):
            with self.changed(repair.DESCRIPTOR,change):
                with self.assertRaises(ValueError):repair.metadata(repair.DESCRIPTOR)
    def test_exact_input_and_other4_expected_guard(self):
        for change in (lambda v:v[0]['input'].update(stage='other'),lambda v:v[1]['expected'].update(extra=1),
            lambda v:v[0]['expected']['research_requests'].pop(),lambda v:v[0]['expected']['research_requests'][1]['arguments'].update(offset=40000)):
            with self.changed(self.fixed['tests'],change):
                with self.assertRaises(ValueError):repair.metadata(repair.DESCRIPTOR)
    def test_closed_fee_fullpending_exit_guard(self):
        for change in (lambda v:v.update(pending_count=1),lambda v:v.update(pending_full_reserved_nano_usd=1),
            lambda v:v.update(original_true_exit=1),lambda v:v.update(all_owned_settled=False),
            lambda v:v.update(owned_generations=17),lambda v:v.update(owned_cost_nano_usd=0)):
            with self.changed(self.fixed['closure'],change):
                with self.assertRaises(ValueError):repair.metadata(repair.DESCRIPTOR)
    def test_paid_review_not_native_directory_is_absent(self):
        original=Path.glob;target=clean.training.ROOT/'attempts/edgar-population-20261016-145/roles/review-01'
        with patch.object(Path,'glob',lambda p,pat:iter([target/'01-request.json']) if p==target else original(p,pat)):
            with self.assertRaises(ValueError):repair.metadata(repair.DESCRIPTOR)
    def test_original_feedback_not_relabelled(self):
        with self.changed(self.fixed['original_decision'],lambda v:v['decision'].update(feedback_sha256='0'*64)):
            with self.assertRaises(ValueError):repair.metadata(repair.DESCRIPTOR)
        self.assertNotEqual(self.fixed['original_feedback'],e.read(self.plan['origin'])['public_feedback'])
    def test_saved_proof_is_not_execution_or_learning(self):
        for key,change in (('validation',lambda v:v.update(host_candidate_execution=True)),
            ('validation',lambda v:v.update(test_bytes=32769)),('validation',lambda v:v.update(validated_learning=True)),
            ('exact_saved_replay',lambda v:v.update(not_a_fresh_execution=False)),
            ('exact_saved_replay',lambda v:v.update(all5_exact_equal=False))):
            with self.changed(self.fixed[key],change):
                with self.assertRaises(ValueError):repair.metadata(repair.DESCRIPTOR)
    def test_nonreview_roles_denied(self):
        task=dict(mode='repair_review',repair=repair.DESCRIPTOR)
        for role in ('controller','author','forecast'):
            manager=SimpleNamespace(value=dict(id=repair.REVIEW_ID,slots={role:['offline-slot']}))
            with patch.object(clean,'read_task',return_value=(task,{})):
                with self.assertRaises(ValueError):clean.selection(manager,role,({}, {},'offline-slot'),{})
    def test_original_Services_Reviewer_receives_fullfeedback_and_qualification(self):
        from earnings_population_services import Services
        from earnings_population_roles import PopulationReviewer
        origin=e.read(self.plan['origin']);feedback=e.read(origin['public_feedback'])
        task=dict(mode='repair_review',company_id='CIK0000003545',repair=repair.DESCRIPTOR,
            feedback=origin['public_feedback'],scaffold=e.read(origin['carried_population']),round2_origin=self.plan['origin'])
        with TemporaryDirectory(prefix='edgar146-prompt-') as td:
            root=Path(td);slot=str(root/'review-01');service=Services.__new__(Services)
            service.runtime=e.read(self.fixed['original_runtime']);service.runtime.update(id=repair.REVIEW_ID,root=td)
            service.runtime['slots']['review']=[slot];service.native_root=root;service.authored={};service.runner=object()
            service.case=lambda *a:dict(company=dict(cik=task['company_id']),state_api=SimpleNamespace(tools=SimpleNamespace(files={'questions.md':'Synthetic question','filing_index.tsv':'Synthetic index'})))
            service.matched_parent_probes=lambda *a:([],[])
            reviewer=PopulationReviewer.__new__(PopulationReviewer);reviewer.broker=SimpleNamespace(references=lambda:deepcopy(service.role_versions))
            service.role=lambda *a:reviewer;seen=[]
            def capture(prompt,where,*args):
                seen.append(prompt);Path(where).mkdir();raw=e.save(Path(where)/'offline-response.json',dict(synthetic_transport=True))
                e.save(Path(where)/'review.json',dict(original=raw,review=dict(candidate_id=prompt['candidate_id'],accepted_for_exploration=False,rationale='Offline capture only')))
                return raw
            with patch.object(clean,'round2_origin',return_value=origin),patch.object(clean,'read_task',return_value=(task,{})), \
                patch.object(reviewer,'_run_open',side_effect=capture),patch('earnings_population_services.run_cases',return_value=[dict(passed=True)]*5), \
                patch('earnings_population_services.researcher.run',return_value=dict(receipt=dict(sha256='0'*64))), \
                patch('earnings_population_services.researcher.verify',return_value={}),patch('earnings_population_services.project',return_value={}), \
                patch('earnings_population_services.review_probe_output',return_value=dict(synthetic=True)):
                clean.repair_review(service,dict(roles=dict(review=service.review)),task)
            self.assertEqual(len(seen),1);extra=seen[0]['human_authorized_minimal_interface_repair']
            self.assertEqual(extra['complete_public_feedback'],feedback);self.assertTrue(extra['PROGRAM_unchanged'])
            self.assertIn('no_targets',extra['validation_summary']);self.assertIn('not paid Review',extra['attribution'])
            self.assertEqual(seen[0]['declared_frontier_test'],policy.declared_test(origin))
            self.assertEqual(service.authored[self.fixed['candidate']['id']]['source'],clean.e.checked(self.fixed['candidate']['R']).decode())
    def test_helpers_exact_finite_deltas_only(self):
        for name,fn in (('close-clean146-first-review.py','closure_source'),('admit-clean146-first-review.py','admission_source')):
            path=clean.training.ROOT/name;spec=importlib.util.spec_from_file_location(name,path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);text=getattr(module,fn)()
            compile(text,str(path),'exec');self.assertIn("number==146",text);self.assertIn("mode=='repair_review'" if fn=='closure_source' else "task['mode']=='repair_review'",text)
            for forbidden in ('RawOpenAIHTTP','DockerRunner(','.create_response('):self.assertNotIn(forbidden,text)

if __name__=='__main__':unittest.main()
