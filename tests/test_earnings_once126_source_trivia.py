"""Exact first126 Review metadata/source/route regressions; no API/Native/run()."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import ast,json,unittest
import earnings_population_clean_slate as clean
import earnings_population_coevolution as policy
import earnings_population_source_trivia as trivia
from supervisor_harness import capacity_feedback_engine as engine

class Once126(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bound=trivia.DESCRIPTOR;cls.fixed=engine.read(cls.bound);cls.real_read=staticmethod(engine.read)
        cls.plan=engine.read(engine.pin(clean.training.ROOT/'TRAIN25-FRONTIER-ROUND14-03A-SOURCE-PLAN-REVIEW126.json'))
    def modified(self,bound,change):
        value=deepcopy(self.real_read(bound));change(value)
        return patch.object(engine,'read',side_effect=lambda b:deepcopy(value) if b==bound else self.real_read(b))
    def test_exact_ast_parent_source_identity_and_original5cases(self):
        fixed=clean.repair_metadata(self.bound,clean.SOURCE_TRIVIA_REVIEW_ID)
        self.assertEqual(fixed['candidate']['parent'],self.plan['group_parent_id'])
        self.assertEqual(clean.repair_authority(trivia.REVIEW_ID),policy.AUTHORITY)
        before=engine.read(fixed['original_source'])['source_text'];after=clean.e.checked(fixed['source']).decode()
        self.assertEqual((len(before.encode()),len(after.encode())),(65571,65492))
        self.assertEqual(ast.dump(ast.parse(before)),ast.dump(ast.parse(after)))
        self.assertEqual(len(engine.read(fixed['tests'])),5)
    def test_selected_original_private_blobs(self):clean.case_expectation_originals(self.fixed)
    def test_only_exact126_firstreview_route_no_CA_forecast_or_retry_ID(self):
        with patch.object(policy,'PLAN',str(clean.training.ROOT/'TRAIN25-FRONTIER-ROUND14-03A-SOURCE-PLAN-REVIEW126.json')):
            policy.route(trivia.REVIEW_ID,14,False,True)
            for n,frozen,repair in ((14,False,False),(14,True,True),(13,False,True),
                    (1,False,True),(None,False,True),(True,False,True),(14.0,False,True),
                    (14,None,True),(14,False,1)):
                with self.assertRaises(ValueError):policy.route(trivia.REVIEW_ID,n,frozen,repair)
            for ident in ('edgar-population-20261016-125','edgar-population-20261016-127'):
                with self.assertRaises(ValueError):policy.route(ident,14,False,True)
                with self.assertRaises(ValueError):clean.repair_metadata(self.bound,ident)
    def test_exact_descriptor_not_generic_switch(self):
        with self.assertRaises(ValueError):trivia.metadata(dict(self.bound,sha256='0'*64))
    def test_no_logic_parent_H_identity_or_regeneration_mutation(self):
        for change in (lambda v:v.update(PROGRAM_AST_unchanged=False),lambda v:v.update(C_A_regeneration=True),
            lambda v:v['candidate'].update(parent='03a'),lambda v:v['candidate']['R'].update(sha256='0'*64),
            lambda v:v['candidate']['H'].update(sha256='0'*64),lambda v:v.update(source_axis='H')):
            with self.modified(self.bound,change):
                with self.assertRaises(ValueError):trivia.metadata(self.bound)
    def test_fee_exit_and_fullpending_fail_closed(self):
        for change in (lambda v:v.update(pending_count=1),lambda v:v.update(pending_full_reserved_nano_usd=1),
            lambda v:v.update(original_true_exit=0),lambda v:v.update(all_owned_settled=False),
            lambda v:v.update(owned_generations=17),lambda v:v.update(owned_cost_nano_usd=0)):
            with self.modified(self.fixed['closure'],change):
                with self.assertRaises(ValueError):trivia.metadata(self.bound)
    def test_prior_Review_or_implemented125_denies_firstreview(self):
        real_exists=Path.exists
        for suffix in ('roles/review-01','loop/round-0001-implement.done.json'):
            target=clean.training.ROOT/'attempts/edgar-population-20261016-125'/suffix
            with patch.object(Path,'exists',lambda p:True if p==target else real_exists(p)):
                with self.assertRaises(ValueError):trivia.metadata(self.bound)
    def test_proof_caps_semantics_and_no_execution_assertions(self):
        for change in (lambda v:v.update(PROGRAM_AST_unchanged=False),lambda v:v.update(original_cases_unchanged=False),
            lambda v:v.update(normalized_bytes=65537),lambda v:v.update(limit_bytes=70000),
            lambda v:v.update(removed_UTF8_bytes=80),lambda v:v.update(model_calls=1),
            lambda v:v.update(Native_calls=1),lambda v:v.update(host_candidate_execution=True)):
            with self.modified(self.fixed['validation'],change):
                with self.assertRaises(ValueError):trivia.metadata(self.bound)
    def test_original_cases_and_decision_not_rewritten(self):
        with self.modified(self.fixed['tests'],lambda v:v.pop()):
            with self.assertRaises(ValueError):trivia.metadata(self.bound)
        with self.modified(self.fixed['original_decision'],lambda v:v['decision'].update(hypothesis='replacement')):
            with self.assertRaises(ValueError):trivia.metadata(self.bound)
    def test_nonreview_roles_denied(self):
        task=dict(mode='repair_review',repair=self.bound)
        for role in ('controller','author','forecast'):
            manager=SimpleNamespace(value=dict(id=trivia.REVIEW_ID,slots={role:['offline-slot']}))
            with patch.object(clean,'read_task',return_value=(task,{})):
                with self.assertRaises(ValueError):clean.selection(manager,role,({}, {},'offline-slot'),{})
    def test_prepare_exact126_guard_before_source_boundary(self):
        class AtSourceBoundary(Exception):pass
        with TemporaryDirectory(prefix='edgar126-prepare-') as td, \
            patch('earnings_population_runtime.ROOT',Path(td)),patch.object(clean,'_rate_scale_route'), \
            patch.object(clean,'_final_followup_route'),patch.object(clean,'repair_metadata',return_value=self.fixed), \
            patch.object(clean.training,'load_scope',return_value={}),patch.object(clean.training,'admit'), \
            patch('earnings_population_run.idle_snapshot',return_value={}), \
            patch.object(clean.subprocess,'run',return_value=SimpleNamespace(stdout='offline-source')), \
            patch('earnings_population_runtime.source_paths',side_effect=AtSourceBoundary):
            with self.assertRaises(AtSourceBoundary):
                clean.prepare(trivia.REVIEW_ID,company_id='CIK0000003545',learning_round=14,repair=self.bound)
            for identifier,n in ((trivia.REVIEW_ID,13),('edgar-population-20261016-127',14)):
                with self.assertRaises(ValueError):clean.prepare(identifier,company_id='CIK0000003545',learning_round=n,repair=self.bound)
            for n in (1,None,True,14.0):
                with self.assertRaises(ValueError):
                    clean.prepare(trivia.REVIEW_ID,company_id='CIK0000003545',learning_round=n,repair=self.bound)
            for repair,frozen in ((None,None),(dict(self.bound,sha256='0'*64),None),(self.bound,{})):
                with self.assertRaises(ValueError):
                    clean.prepare(trivia.REVIEW_ID,company_id='CIK0000003545',learning_round=14,repair=repair,frozen_candidate=frozen)
            self.assertEqual(list(Path(td).iterdir()),[])
    def test_Services_Reviewer_receives_real_failure_fullfeedback_and_AST_qualification(self):
        from earnings_population_services import Services
        from earnings_population_roles import PopulationReviewer
        origin=engine.read(self.plan['origin']);feedback=engine.read(origin['public_feedback'])
        task=dict(mode='repair_review',company_id='CIK0000003545',repair=self.bound,feedback=origin['public_feedback'],
            scaffold=engine.read(origin['carried_population']),round2_origin=self.plan['origin'],primary_task='Synthetic transport only')
        with TemporaryDirectory(prefix='edgar126-prompt-') as td:
            root=Path(td);slot=str(root/'review-01');service=Services.__new__(Services)
            service.runtime=engine.read(engine.read(self.fixed['closure'])['runtime']);service.runtime.update(id=trivia.REVIEW_ID,root=td)
            service.runtime['slots']['review']=[slot];service.native_root=root;service.authored={};service.runner=object()
            service.case=lambda *a:dict(company=dict(cik=task['company_id']),state_api=SimpleNamespace(tools=SimpleNamespace(files={'questions.md':'Synthetic question','filing_index.tsv':'Synthetic index'})))
            service.matched_parent_probes=lambda *a:([],[])
            reviewer=PopulationReviewer.__new__(PopulationReviewer);reviewer.broker=SimpleNamespace(references=lambda:deepcopy(service.role_versions))
            service.role=lambda *a:reviewer;seen=[]
            def capture(prompt,where,*args):
                seen.append(prompt);Path(where).mkdir();raw=engine.save(Path(where)/'offline-response.json',dict(synthetic_transport=True))
                engine.save(Path(where)/'review.json',dict(original=raw,review=dict(candidate_id=prompt['candidate_id'],accepted_for_exploration=False,rationale='Offline capture only')))
                return raw
            with patch.object(clean,'round2_origin',return_value=origin),patch.object(clean,'read_task',return_value=(task,{})), \
                patch.object(reviewer,'_run_open',side_effect=capture),patch('earnings_population_services.run_cases',return_value=[dict(passed=True)]*5), \
                patch('earnings_population_services.researcher.run',return_value=dict(receipt=dict(sha256='0'*64))), \
                patch('earnings_population_services.researcher.verify',return_value={}),patch('earnings_population_services.project',return_value={}), \
                patch('earnings_population_services.review_probe_output',return_value=dict(synthetic=True)):
                clean.repair_review(service,dict(roles=dict(review=service.review)),task)
            self.assertEqual(len(seen),1);extra=seen[0]['human_authorized_minimal_interface_repair']
            self.assertEqual(extra['complete_public_feedback'],feedback);self.assertTrue(extra['PROGRAM_AST_unchanged'])
            self.assertEqual(extra['original_implementation_failure']['status'],'FAILED_NO_RETRY')
            self.assertNotIn('original_review',extra);self.assertIn('no prior',extra['attribution'])
            self.assertEqual(seen[0]['declared_frontier_test'],policy.declared_test(origin))
    def test_no_resource_model_budget_or_scheduler_source_changes(self):
        old=engine.read(engine.pin(clean.training.ROOT/'TRAIN25-FRONTIER-ROUND14-03A-SOURCE-PLAN125.json'))
        for key in ('max_concurrent_companies','max_inflight_per_company','minimum_next_liability_nano_usd',
            'rolling_yield_authority','automatic_retry','budget_change','heldout_access','adoption_rule'):
            self.assertEqual(self.plan[key],old[key])
        claim=engine.read(engine.read(self.plan['origin'])['frontier_expansion'])
        progress=engine.read(claim['generation_progress'])
        self.assertEqual(len(progress['outcomes']),1)
        self.assertEqual(progress['outcomes'][0]['hypothesis_id'],'5e22-origin-complete-quarter-vintage-acquisition')
        self.assertEqual(claim['hypothesis_id'],'03a-financial-entity-and-row-binding')

if __name__=='__main__':unittest.main()
