"""Actual driver/native activation/forecaster; invented role originals/scorer."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import earnings_feedback_loop as flow
import earnings_capacity_adapter as a
import edgar_forecast_openai as forecast
import test_earnings_capacity_worker as worker_fixture
import earnings_transport_fixture as transport
from market_rsi import digest


class CapacityLoopTests(worker_fixture.CapacityWorkerTests):
    def setUp(self):
        super().setUp()
        self.axes=['R','H'];self.packets=[];self.executed=[];self.reviewed=[];self.authored=[]
        self.forecast_failure=False;self.bad_controller=False
        self.reject=False;self.fake_review=False
        questions='\n'.join(f'### T{i:03d} | invented amount' for i in range(1,6))
        q=Path(self.company['visible_root'])/'questions.md';q.write_text(questions)
        self.company['allowed_files'][0].update(bytes=len(questions.encode()),sha256=flow.e.digest(questions.encode()))
        from earnings_research_state import ResearchState
        self.task='earnings-coevolution-20261013-fixture-loop'
        self.api=ResearchState(self.company,self.task)
        self.envelope={'root':str(self.root/'episode'),'id':self.task,'mode':'offline_replay','cik':self.company['cik'],'max_rounds':2,
            'source_commit':'b'*40,'initial_state':self.api.save(self.root/'initial-memory',self.api.empty()),
            'evaluation_kernel':self.evaluation_kernel(),
            'slots':[{role:str(self.root/'episode/roles'/f'{role}-{n}') for role in ('controller','author','review','forecast')} for n in (1,2)]}
        self.bound=flow.save(self.root/'envelope.json',self.envelope)
        for fixture in (patch.object(flow.e,'preflight_capacity_episode',return_value=(self.company,self.api)),
                        patch.object(flow.policy,'capacity_sources',return_value=[])):
            fixture.start();self.addCleanup(fixture.stop)

    def evaluation_kernel(self):
        return transport.make_kernel(self.root)

    def record(self,slot,value):
        path=Path(slot);path.mkdir(parents=True,exist_ok=False)
        return flow.save(path/'response.json',value)

    def controller_role(self,prompt,slot):
        self.packets.append(prompt)
        axis=self.axes[len(self.packets)-1]
        choice={'schema':'earnings_capacity_decision_v1','axis':axis,
            'component':{'R':'research_policy','H':'tool_interface','continue':'none'}[axis],
            'parent_pair_sha256':prompt['parent_pair_sha256'],'feedback_sha256':prompt['feedback_sha256'],
            'hypothesis':'Fixture hook consumes a changed profile','expected_effect':'Delivery verified, not forecast gain'}
        text='not JSON' if self.bad_controller else json.dumps(choice)
        return self.record(slot,{'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':text}]}]})

    def author_role(self,choice,before,slot):
        self.authored.append(choice)
        name={'R':'researcher_v2.py','H':'harness_v2.py'}[choice['axis']]
        source=self.native.files[name]
        after=a.profile(source.encode(),choice['axis'])
        field='research_instructions' if choice['axis']=='R' else 'read_chunk_limit'
        value={'decision_sha256':digest(choice),'source_text':source,
               'test_text':'CASES = '+repr([{'field':field,'expected':after[field]}])+'\n'}
        return self.record(slot,value)

    def synthetic_review_receipt(self,before,after,entries,descriptor,proposal):
        """Pure projected lineage plus literal reads; invented compatibility only.

        This does not store a version, propose to the journal, resolve native
        capacity, execute a shadow, or measure a scientific benefit.
        """
        micro=descriptor['micro_evolution']
        pending=a.activation.micro.propose_micro_evolution(micro,proposal)['pending']
        active=digest(micro['active_pair']);axis=next(
            axis for axis in ('R','H') if before[axis]!=after[axis])
        def literal(manifest,entrypoints,selected,shadow):
            name=entrypoints[axis]
            binding={'path':str(self.root/name),'sha256':manifest['components'][axis]['sources'][name]}
            return {'profile':a.profile(a.activation._read(binding),axis),'receipt':{
                'axis':axis,'source':binding,'selected_pair_sha256':digest(selected),
                'active_pair_sha256':active,'shadow':shadow,'model_code_executed':False}}
        old=literal(before,descriptor['parent_entrypoints'],micro['active_pair'],False)
        new=literal(after,entries,pending['pair'],True)
        self.assertNotEqual(old['profile'],new['profile'])
        bound={'proposal_sha256':pending['record_sha256'],'before_identity_sha256':digest(before),
            'after_identity_sha256':digest(after),'tested_pair_sha256':digest(pending['pair']),
            'anchor_pair_sha256':digest(micro['anchor_pair'])}
        evidence=self.native.artifact({'synthetic':True,'outputs':{'old':old,'new':new},'binding':bound,
            'checks':{k:True for k in a.activation.micro.MICRO_CHECKS}})
        benefit=self.native.artifact({'proposal_sha256':pending['record_sha256'],
            'before_identity_sha256':digest(before),'after_identity_sha256':digest(after),
            'matched_outputs_sha256':evidence['sha256'],'effect':pending['behavior_change'],
            'benefit_observed':True})  # Existing invented fixture flag, not measured benefit.
        review={'reviewer_id':micro['reviewer_id'],'proposal_sha256':pending['record_sha256'],
            'decision':'reject' if self.reject else 'accept','reason':'Fixture-only hook compatibility',
            'tested_pair_sha256':digest(pending['pair']),'anchor_pair_sha256':bound['anchor_pair_sha256'],
            'checks':{k:{'passed':True,'evidence_sha256':evidence['sha256']} for k in a.activation.micro.MICRO_CHECKS},
            'benefit_observed':True,'benefit_evidence_sha256':benefit['sha256'],
            'actual_write_paths':pending['write_paths']}
        receipt=self.native.artifact({'review':review,
            'evidence':{evidence['sha256']:evidence['path'],benefit['sha256']:benefit['path']}})
        return receipt,[receipt,evidence,benefit]

    def review_role(self,choice,author,descriptor,slot):
        self.reviewed.append(choice)
        # The production engine passes JSON only, never the mutable capacity.
        self.assertEqual(json.loads(json.dumps(descriptor)),descriptor)
        self.assertEqual(descriptor['schema'],'capacity_review_context_v1')
        self.assertEqual(descriptor['decision_sha256'],digest(choice))
        self.assertEqual(descriptor['parent_pair_sha256'],choice['parent_pair_sha256'])
        self.assertEqual(flow.e.strict_json(flow.e.checked(descriptor['author_original']).decode()),author)
        if self.fake_review:
            body={'verdict':'reject'}
            return dict(body,original=self.record(slot,body),artifacts=[])
        before=descriptor['parent_identity']
        authored=a.author_payload(author)
        args=deepcopy(self.native.args)
        args['harness'],args['researcher']=before['components']['H'],before['components']['R']
        kind={'R':'researcher','H':'harness'}[choice['axis']];name=kind+'_v2.py'
        # Immutable original Author bytes, not a repaired source response.
        self.assertEqual((self.root/name).read_text(),authored['source_text'])
        args[kind]={'sources':{name:flow.e.digest(authored['source_text'].encode())},'configuration_sha256':self.native.args[kind]['configuration_sha256']}
        after=a.identity.manifest(**args)
        entries={axis:next(iter(after['components'][axis]['sources'])) for axis in ('R','H')}
        proposal={'candidate_id':kind+'-loop-child','proposer_id':'fixture-author','axis':kind,'component':choice['component'],
            'behavior_change':choice['expected_effect'],'problem_evidence_sha256':choice['feedback_sha256'],
            'parent_pair_sha256':choice['parent_pair_sha256'],'pair':a.activation.pair(after),
            'fixed_context':descriptor['micro_evolution']['fixed_context'],'write_paths':list(before['components'][choice['axis']]['sources'])+[name],
            'patch_sha256':a.activation.patch_digest(before,after)}
        scope=self.native.artifact({'passed':True,'reviewer_id':'independent-auditor','proposer_id':'fixture-author',
                                   'identity_sha256':digest(after),'entrypoints':entries})
        receipt,evidence=self.synthetic_review_receipt(before,after,entries,descriptor,proposal)
        body={'schema':'capacity_review_spec_v1','after':after,'proposal':proposal,'entrypoints':entries,
              'static_review':scope,'review_receipt':receipt}
        # Persist the exact spec before returning its original file binding.
        original=self.record(slot,body)
        return dict(body,original=original,artifacts=[scope,*evidence])

    def forecast_role(self,worker,slot):
        output=Path(slot);output.mkdir(parents=True,exist_ok=False)
        n=len(self.executed)+1;self.executed.append(worker)
        calls=[0]
        def reply(request):
            calls[0]+=1
            if calls[0]==1:
                if n==1:
                    action={'type':'function_call','call_id':'fact','name':'save_research_record',
                            'arguments':json.dumps({'record_json':json.dumps(self.data.fact)})}
                else:
                    action={'type':'function_call','call_id':'read','name':'read_file',
                            'arguments':json.dumps({'path':'filings/old.md','offset':0,'characters':5000})}
                return {'status':'completed','output':[action]}
            if self.forecast_failure:raise RuntimeError('fake uncertain provider failure')
            return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({
                'predictions':[{'target_id':f'T{i:03d}','predicted_value':100} for i in range(1,6)]})}]}]}
        try:
            result=transport.run_forecast(self,worker,output,reply)
            score=transport.score_payload(self.envelope['evaluation_kernel'],output)
            result.update(status='COMPLETED_SCORED',planned_targets=5,scored_targets=5,points=score['score_out_of_5'])
        except RuntimeError:
            result={'status':'FAILED_NO_RETRY','planned_targets':5,'scored_targets':0,'error_type':'RuntimeError'}
            score={}
        return {'result':flow.save(output/'result.json',result),'score':flow.save(output/'score.json',score)}

    def run_flow(self):
        return flow.run_capacity(self.bound,self.native.restore(),roles={'controller':self.controller_role,
            'author':self.author_role,'review':self.review_role,'forecast':self.forecast_role})

    def test_two_actual_driver_rounds_R_then_H_use_feedback_records_and_cold_replay(self):
        result=self.run_flow()
        self.assertEqual((result['status'],result['completed_rounds']),('completed',2))
        self.assertEqual(self.packets[1]['feedback']['observation']['prediction']['score_out_of_5'],5)
        previous=flow.driver._read_pair(self.root/'episode/loop/round-0001-reconcile.done.json')['output']
        self.assertEqual(self.packets[1]['feedback_sha256'],digest(previous))
        self.assertNotIn('NEVER_DELIVER_TO_CONTROLLER',json.dumps(self.packets))
        self.assertEqual(self.executed[1].state['records'][0]['record']['value'],100)
        self.assertEqual(self.executed[1].context['tool_bounds']['read_chunk_limit'],1000)
        self.assertEqual(self.executed[0].context['messages'][1]['content'],'Verify signs with calculate')
        self.assertEqual(len(self.native.batch.snapshot()['micro_evolution']['history']),2)
        self.assertFalse(result['result']['claims']['live_RH_authorship'])
        before=(len(self.packets),len(self.executed),len(self.reviewed))
        self.assertEqual(self.run_flow(),result)
        self.assertEqual((len(self.packets),len(self.executed),len(self.reviewed)),before)

    def test_continue_runs_without_forced_author_or_mutation(self):
        self.axes=['continue','continue']
        result=self.run_flow()
        self.assertEqual(result['completed_rounds'],2)
        self.assertEqual((self.authored,self.reviewed),([],[]))
        self.assertEqual(self.native.batch.snapshot()['micro_evolution']['history'],[])

    def test_rejected_candidates_keep_working_parent_but_retain_history(self):
        self.reject=True
        self.run_flow()
        self.assertEqual(self.native.batch.snapshot()['micro_evolution']['active_pair'],a.activation.pair(self.native.before))
        self.assertEqual(len(self.native.batch.snapshot()['micro_evolution']['history']),2)
        self.assertTrue(all(x.context['tool_bounds']['read_chunk_limit']==20000 for x in self.executed))

    def test_pretend_review_without_actual_native_closure_refused(self):
        self.fake_review=True
        with self.assertRaises(flow.driver.LoopHalted):self.run_flow()
        self.assertEqual(self.executed,[])

    def test_bad_controller_preserved_and_no_author_forecast_or_retry(self):
        self.bad_controller=True
        with self.assertRaises(flow.driver.LoopHalted):self.run_flow()
        with self.assertRaises(flow.driver.LoopHalted):self.run_flow()
        self.assertEqual((len(self.packets),self.authored,self.executed),(1,[],[]))
        self.assertTrue((self.root/'episode/roles/controller-1/response.json').is_file())

    def test_failed_forecast_preserves_fact_failure_and_blocks_second_controller(self):
        self.forecast_failure=True
        with self.assertRaises(flow.driver.LoopHalted):self.run_flow()
        with self.assertRaises(flow.driver.LoopHalted):self.run_flow()
        self.assertEqual((len(self.packets),len(self.executed)),(1,1))
        worker=self.executed[0]
        self.assertEqual(worker.state_api.load(worker.state_binding)['records'][0]['record']['value'],100)
        result=json.loads((self.root/'episode/roles/forecast-1/result.json').read_text())
        self.assertEqual(result['status'],'FAILED_NO_RETRY')

    def test_no_roles_has_no_paid_default(self):
        with self.assertRaisesRegex(ValueError,'no paid fallback'):
            flow.run_capacity(self.bound,self.native.adapter)


for _name in dir(worker_fixture.CapacityWorkerTests):
    if _name.startswith('test_'):setattr(CapacityLoopTests,_name,None)

if __name__=='__main__':unittest.main()
