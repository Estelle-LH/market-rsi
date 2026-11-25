"""Synthetic once-only human repair boundaries; no API/ledger/guest execution."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

import earnings_population_clean_slate as clean
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine


class RepairBoundaries(unittest.TestCase):
    def setUp(self):
        self.before=b"PROGRAM={'axis':'R'}\ndef _plan():return []\ndef run(payload):return {}\n"
        self.after=self.before.replace(b'return []',b'return [1]')
        self.r=dict(path='/fixture/oldR',sha256='1'*64);self.h=dict(path='/fixture/H',sha256='2'*64)
        self.new=dict(path='/fixture/newR',sha256='3'*64)
        self.old=dict(id=digest({'R':self.r['sha256'],'H':self.h['sha256']}),R=self.r,H=self.h,method='unchanged hypothesis',
            evidence=[{'path':'original-model-response'},{'path':'original-scientific-projection'}])
        self.child=dict(id=digest({'R':self.new['sha256'],'H':self.h['sha256']}),R=self.new,H=self.h,
            parent=self.old['id'],axis='R',method=self.old['method'],author='human_authorized_interface_repair_of_model:DeltaAuthor')
        self.closure=dict(path='/fixture/closure',sha256='b77ecb21c755cb68cffb48625bbb8a9fa9d938dada5627d2b7eba65d306892fd')
        self.audit=dict(candidate=self.old,status='PROPOSAL_NOT_ACCEPTED',original_exec_true_exit=0,current_pending_count=0)
        self.bound=dict(path=str(clean.training.ROOT/'clean50-minimal-repair/repair-review.json'),sha256='4'*64)
        self.fixed=dict(schema='earnings_clean50_interface_repair_v1',authority=clean.REPAIR_AUTHORITY,closure=self.closure,
            original_candidate=self.old,candidate=self.child,source=self.new,
            tests={'path':'/fixture/tests'},validation={'path':'/fixture/validation'},original_review={'path':'/fixture/review'})

    def metadata(self):
        with patch.object(engine,'read',side_effect=lambda b:self.audit if b==self.closure else self.fixed), \
             patch.object(clean.e,'checked',side_effect=lambda b:self.before if b==self.r else self.after if b==self.new else b'{}'):
            return clean.repair_metadata(self.bound,'edgar-population-20261016-51')

    def test_exact_parent_axis_and_human_attribution(self):
        self.assertEqual(self.metadata()['candidate'],self.child)
        for key,value in [('parent','other'),('axis','H'),('author','model:DeltaAuthor'),('method','new strategy')]:
            saved=self.child[key];self.child[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.metadata()
            self.child[key]=saved

    def test_other_scientific_function_change_refused(self):
        self.after=self.after.replace(b'return {}',b'return 17')
        with self.assertRaisesRegex(ValueError,'Only acquisition'):self.metadata()

    def test_unknown_exit_and_nonrejected_original_refused(self):
        for key,value in [('original_exec_true_exit',None),('status','RUNNING'),('current_pending_count',1)]:
            saved=self.audit[key];self.audit[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.metadata()
            self.audit[key]=saved

    def test_second_repair_id_and_unbound_path_refused(self):
        with self.assertRaisesRegex(ValueError,'Exactly one'):clean.repair_metadata(self.bound,'edgar-population-20261016-54')
        wrong=dict(self.bound,path='/fixture/unbound')
        with self.assertRaisesRegex(ValueError,'Exactly one'):clean.repair_metadata(wrong,'edgar-population-20261016-51')

    def test_repair_selection_forbids_controller_author_forecast(self):
        task=dict(mode='repair_review',repair=self.bound)
        slots={r:['/fixture/roles/'+r+'-01'] for r in ('controller','author','review','forecast')}
        manager=SimpleNamespace(value=dict(id='edgar-population-20261016-51',slots=slots))
        with patch.object(clean,'read_task',return_value=(task,{})),patch.object(clean,'repair_metadata',return_value=self.fixed):
            for role in ('controller','author','forecast'):
                with self.subTest(role=role),self.assertRaisesRegex(ValueError,'exactly one original Review'):
                    clean.selection(manager,role,({},slots[role][0]),{})

    def test_direct_producer_calls_review_only_and_preserves_false_verdict(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();slot=str(root/'roles/review-01')
            fixed=deepcopy(self.fixed);fixed['tests']={'path':'tests'}
            task=dict(mode='repair_review',repair=self.bound,company_id='fixture',feedback={'path':'feedback'},
                scaffold=dict(versions={},stable_id='old',explorers=[]))
            service=SimpleNamespace(runtime=dict(id='edgar-population-20261016-51',root=str(root),slots={'review':[slot]}),authored={})
            callback=Mock(return_value=dict(accepted_for_exploration=False,evidence=[{'fixture':True}]))
            def checked(bound):
                return b"CASES=[{'input':{},'expected':{}}]" if bound==fixed['tests'] else self.after
            with patch.object(clean,'repair_metadata',return_value=fixed),patch.object(clean.e,'checked',side_effect=checked), \
                 patch.object(engine,'read',side_effect=lambda b:{'scientific_decision':{'unchanged':'original'}}):
                saved=clean.repair_review(service,{'roles':{'review':callback}},task)
            self.assertEqual(callback.call_count,1)
            value=engine.read(saved)
            self.assertFalse(value['review']['accepted_for_exploration'])
            self.assertFalse(value['new_Controller_or_Author_called'])
            self.assertFalse((root/'roles/controller-01').exists())

    def test_original_services_builds_real_review_prompt_with_original_decision_and_public_probe(self):
        from earnings_population_services import Services
        import earnings_population_services as services
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();slot=root/'review-01';slot.mkdir()
            public={'bridges':[{'anchor':None}],'warnings':['anchor_missing']};seen=[]
            original=engine.save(slot/'response.json',{'fixture':'public response'})
            def review(prompt,location):
                seen.append(prompt)
                engine.save(Path(location)/'review.json',dict(original=original,review=dict(accepted_for_exploration=False,rationale='still missing anchors')))
                return original
            fake_role=SimpleNamespace(review=review,broker=SimpleNamespace(references=lambda:{}))
            stateapi=SimpleNamespace(tools=SimpleNamespace(files={'questions.md':'### T001 | test','filing_index.tsv':'fixture'}))
            case=dict(company={'cik':'fixture'},state_api=stateapi)
            service=Services.__new__(Services)
            service.authored={self.child['id']:dict(source=self.after.decode(),parsed={'cases':[{'input':{},'expected':{}}]},
                decision={'original':'scientific decision'},originals=[original],human_interface_repair={'attribution':'human only'})}
            service.native_root=root;service.runner=Mock();service.prior_feedback={};service.runtime={}
            service._proposal_task=lambda:None;service.reused_author=lambda:None
            service.case=lambda child,location:case;service.role=lambda *args:fake_role
            with patch.object(services,'run_cases',return_value=[{'passed':True}]), \
                 patch.object(services.researcher,'run',return_value={'receipt':{'sha256':'a'*64}}), \
                 patch.object(services.researcher,'verify',return_value=public),patch.object(services,'project',return_value={'cells':0}):
                result=Services.review(service,self.child,{},str(slot))
            self.assertFalse(result['accepted_for_exploration'])
            self.assertEqual(seen[0]['decision'],{'original':'scientific decision'})
            self.assertEqual(seen[0]['human_authorized_minimal_interface_repair'],{'attribution':'human only'})
            self.assertEqual(seen[0]['original_public_empty_state_probes'][0]['verified_public_R_output']['value'],public)
            self.assertEqual(clean.repair_state({'scaffold':{'exact':'unchanged'}},self.fixed),{'exact':'unchanged'})

    def test_once52_requires_closed_failure_and_exact_unchanged_candidate(self):
        closure={'path':'/fixture/failed51'};git={'path':'/fixture/closed51git'}
        authority=dict(schema='earnings_clean52_once_concise_review_authority_v1',id=clean.CONCISE_REVIEW_ID,
            failed_closure=closure,failed_private_git=git,failed_commit='closed51',repair_descriptor=self.bound,
            candidate=self.child['id'],R_sha256=self.new['sha256'],H_sha256=self.h['sha256'])
        audit=dict(original_exec_true_exit=1,decision='INCOMPLETE_NO_SELECTION',incomplete_details={'reason':'max_output_tokens'},
            pending_count=0,candidate=self.child,frozen=False,scientific_verdict=None)
        saved=dict(commit='closed51',true_exit_code=0,closure=closure)
        def read(bound):return authority if bound==clean.CONCISE_REVIEW_AUTHORITY else audit if bound==closure else saved
        with patch.object(engine,'read',side_effect=read):
            self.assertEqual(clean.concise_review_metadata(self.bound,self.fixed),authority)
            for key,value in [('original_exec_true_exit',None),('decision','ACCEPTED'),('pending_count',1),
                              ('frozen',True),('scientific_verdict',False)]:
                original=audit[key];audit[key]=value
                with self.subTest(key=key),self.assertRaises(ValueError):clean.concise_review_metadata(self.bound,self.fixed)
                audit[key]=original
            authority['R_sha256']='other'
            with self.assertRaises(ValueError):clean.concise_review_metadata(self.bound,self.fixed)

    def test_once52_concise_real_role_prompt_keeps_schema_and_old_roles_unchanged(self):
        from earnings_population_roles import PopulationReviewer,CONCISE_REVIEW_DELIVERY
        role=PopulationReviewer.__new__(PopulationReviewer);role.review_runtime=None
        role._run_open=Mock(return_value='captured')
        prompt={'candidate_id':self.child['id']}
        role.review(prompt,'fixture')
        legacy=role._run_open.call_args.args
        self.assertNotIn(CONCISE_REVIEW_DELIVERY,legacy[2])
        final=role._final_instruction()
        del role.review_runtime
        self.assertEqual(role._final_instruction(),final)
        role.review_runtime=dict(id='edgar-population-20261016-51')
        self.assertEqual(role._final_instruction(),final)
        role.review_runtime=dict(id=clean.CONCISE_REVIEW_ID,clean_slate_policy=clean.POLICY)
        with patch.object(clean,'read_task',return_value=({'mode':'repair_review'},{})):
            role.review(prompt,'fixture');short=role._run_open.call_args.args
            self.assertIn(CONCISE_REVIEW_DELIVERY,short[2])
            self.assertIn(CONCISE_REVIEW_DELIVERY,role._final_instruction())
            self.assertEqual(short[0],legacy[0]);self.assertEqual(short[3],legacy[3])
            self.assertEqual(short[5:],legacy[5:])
        with patch.object(clean,'read_task',return_value=({'mode':'evaluate'},{})),self.assertRaises(ValueError):
            role._final_instruction()
        role.review_runtime=dict(id=clean.CONCISE_REVIEW_ID)
        with self.assertRaises(ValueError):role._final_instruction()

    def test_once53_scope_parent_strategy_and_actual_validation_required(self):
        self.child['author']='human_authorized_anchor_date_repair_of_model:DeltaAuthor'
        fixed=dict(self.fixed,schema='earnings_clean52_anchor_date_repair_v1',authority=clean.ANCHOR_REPAIR_AUTHORITY,
            original_git={'path':'git'},prior_inputs_git={'path':'inputs'},scientific_decision={'path':'science'})
        authority=dict(review_id=clean.ANCHOR_REVIEW_ID,actual_parent=self.old['id'],rejected52_closure=self.closure)
        audit=dict(candidate=self.old,scientific_verdict=False,original_exec_true_exit=0,status='PROPOSAL_NOT_ACCEPTED',pending_count=0)
        validation=dict(source=self.child['R'],actual_parent=self.old['R'],host_candidate_execution=False,model_calls=0,real_training_probes=[{},{}])
        def read(b):
            if b==clean.ANCHOR_REPAIR_AUTHORITY:return authority
            if b==clean.ANCHOR_REPAIR_DESCRIPTOR:return fixed
            if b==self.closure:return audit
            if b==self.fixed['validation']:return validation
            raise AssertionError(b)
        with patch.object(engine,'read',side_effect=read),patch.object(clean.e,'checked',side_effect=lambda b:self.before if b==self.r else self.after if b==self.new else b'{}'):
            self.assertEqual(clean.repair_metadata(clean.ANCHOR_REPAIR_DESCRIPTOR,clean.ANCHOR_REVIEW_ID)['candidate'],self.child)
            original=self.child['method'];self.child['method']='new strategy'
            with self.assertRaises(ValueError):clean.anchor_date_repair_metadata(clean.ANCHOR_REPAIR_DESCRIPTOR)
            self.child['method']=original;validation['host_candidate_execution']=True
            with self.assertRaises(ValueError):clean.anchor_date_repair_metadata(clean.ANCHOR_REPAIR_DESCRIPTOR)
        with self.assertRaises(ValueError):clean.repair_metadata(self.bound,clean.ANCHOR_REVIEW_ID)

    def test_once53_concise_route_but_not_new_evaluation_or_general_retry(self):
        from earnings_population_roles import PopulationReviewer,CONCISE_REVIEW_DELIVERY
        role=PopulationReviewer.__new__(PopulationReviewer)
        role.review_runtime=dict(id=clean.ANCHOR_REVIEW_ID,clean_slate_policy=clean.POLICY)
        with patch.object(clean,'read_task',return_value=({'mode':'repair_review'},{})):
            self.assertIn(CONCISE_REVIEW_DELIVERY,role._final_instruction())
        with patch.object(clean,'read_task',return_value=({'mode':'evaluate'},{})),self.assertRaises(ValueError):role._final_instruction()


if __name__=='__main__':unittest.main()
