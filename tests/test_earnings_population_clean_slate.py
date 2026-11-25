"""Synthetic fixtures only; no provider, real ledger, Native or scorer execution."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import earnings_population_clean_slate as clean
import earnings_population_runtime as runtime
from supervisor_harness import capacity_feedback_engine as engine
from test_earnings_population_role_validation import RoleFixture


class Round0Tests(unittest.TestCase):
    def setUp(self):
        self.ids = ['CIK%010d'%i for i in range(1,26)]
        self.scope = dict(training=self.ids,split=clean.SPLIT)
        self.values = {}; self.rows = []
        for cik in self.ids:
            row = {key:dict(path='/fixture/'+cik+'/'+key,sha256='a'*64)
                for key in clean.training.ROW_FIELDS-{'cik'}}
            row['cik'] = cik; self.rows.append(row)
            self.values[row['predictions']['path']] = dict(predictions=[dict(target_id=t,predicted_value='17')
                for t in clean.training.TARGETS])
            self.values[row['public_feedback']['path']] = dict(cik=cik,score_out_of_5=3,
                per_target=[dict(target_id=t,points_awarded=p) for t,p in zip(clean.training.TARGETS,[1,1,1,0,0])])
        self.manifest = dict(schema='earnings_plain_training_comparator_manifest_v1',split=clean.SPLIT,rows=self.rows)
        self.decoded = []; self.opaque = []

    def read(self,b):
        if b == clean.ROUND0: return deepcopy(self.manifest)
        self.decoded.append(b['path'])
        return deepcopy(self.values[b['path']])

    def patches(self):
        stack = ExitStack(); self.addCleanup(stack.close)
        stack.enter_context(patch.object(clean.training,'load_scope',return_value=self.scope))
        stack.enter_context(patch.object(clean.training,'admit',side_effect=lambda s,c:c if c in self.ids else (_ for _ in ()).throw(ValueError('sealed'))))
        stack.enter_context(patch.object(clean.training,'_read',side_effect=self.read))
        stack.enter_context(patch.object(clean.training,'_bytes',side_effect=lambda b:self.opaque.append(b)))

    def test_complete125_public_pairs_without_decoding_raw_scores_or_reasoning(self):
        self.patches(); summary = clean.round0_feedback()
        self.assertEqual(len(summary['rows']),25)
        self.assertEqual(sum(len(r['targets']) for r in summary['rows']),125)
        self.assertEqual(sum(r['points'] for r in summary['rows']),75)
        self.assertEqual(len(self.opaque),25*9)
        self.assertTrue(all(p.endswith(('/predictions','/public_feedback')) for p in self.decoded))
        self.assertNotIn('versions',summary)

    def test_reordered_missing_heldout_or_duplicated_company_refused_before_row_read(self):
        for transform in (lambda rows:rows[:-1],lambda rows:list(reversed(rows)),lambda rows:rows[:-1]+[rows[0]]):
            self.patches(); original=self.manifest['rows']; self.manifest['rows']=transform(original)
            with self.assertRaises(ValueError):clean.round0_feedback()
            self.assertEqual(self.decoded,[]);self.manifest['rows']=original

    def test_nonfractional_and_wrong_total_awards_refused(self):
        self.patches(); public=self.values[self.rows[0]['public_feedback']['path']]
        public['per_target'][0]['points_awarded']=.2
        with self.assertRaises(ValueError):clean.round0_feedback()

    def test_all_actual_user_inputs_must_contain_exact_complete_feedback(self):
        summary={'schema':'fixture_summary','rows':[{'prediction':'17','award':1}]}
        payload={'input':[{'role':'user','content':json.dumps({'research_context':{'feedback':summary}})}]}
        self.assertTrue(clean._contains_summary(payload,summary))
        payload['input'][0]['role']='assistant'
        self.assertFalse(clean._contains_summary(payload,summary))


class CurrentGuardTests(unittest.TestCase):
    def setUp(self):
        self.f=RoleFixture();self.addCleanup(self.f.close)
        for p in self.f.patches():p.start();self.addCleanup(p.stop)
        self.f.value.update(clean_slate_policy=clean.POLICY,
            model_budget_amendment=self.f.save('model-grant.json',{}))
        self.f.packet['round_index']=1;self.f.save('packet-01.json',self.f.packet)
        study=engine.read(self.f.value['forecast_study'])
        study['clean_slate_task']=self.f.save('clean-slate-task.json',{})
        Path(self.f.value['forecast_study']['path']).unlink()
        self.f.value['forecast_study']=self.f.save('study.json',study)
        self.f.binding=self.f.save('runtime.json',self.f.value)
        self.f.manager.value=deepcopy(self.f.value);self.f.manager.binding=self.f.binding
        self.task=dict(mode='proposal',company_id=self.f.packet['company_id'],feedback=self.f.feedback,
            scaffold=self.f.population,frozen_candidate=None)
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(clean,'read_task',return_value=(self.task,{'fixture':True})))
        self.stack.enter_context(patch.object(clean,'SPLIT',self.f.save('split.json',{})))
        self.stack.enter_context(patch.object(clean,'ROUND0',self.f.save('round0.json',{})))
        self.stack.enter_context(patch.object(clean.training,'admit',side_effect=lambda s,c:c))

    def test_constructor_checks_keep_current_guards_without_replaying_history(self):
        for _ in range(12):self.f.manager.check_owner()
        self.assertEqual(self.f.full_calls,[])
        self.assertEqual(len(self.f.ledger_calls),12)

    def test_real_role_still_has_full_entry_exit_and_current_http_guards(self):
        def callback(*args):
            self.f.manager.register_case(self.f.case(args[-1]))
            for _ in range(8):self.f.manager.check_owner()
            return 'fixture result'
        with patch('earnings_population_runtime._local',side_effect=lambda b:engine.read(b)):
            result=self.f.manager.wrap('controller',callback)(*self.f.args('controller'))
        self.assertEqual(result,'fixture result')
        self.assertEqual(len(self.f.full_calls),2)
        self.assertEqual(len(self.f.ledger_calls),9)

    def test_nonrole_runtime_source_and_feedback_drift_refused(self):
        for name,bound in [('runtime',self.f.binding),('source',self.f.metadata['forecaster']),('feedback',self.f.feedback)]:
            p=Path(bound['path']);original=p.read_bytes();p.write_bytes(b'changed')
            with self.subTest(name=name),self.assertRaises((ValueError,TypeError)):
                self.f.manager.check_owner()
            p.write_bytes(original)

    def test_legacy_cannot_silently_opt_into_light_checks(self):
        self.f.manager.value.pop('clean_slate_policy')
        with self.assertRaises(ValueError):self.f.manager.check_owner()

    def test_proposal_cannot_forecast_or_use_other_packet_company(self):
        with self.assertRaises(ValueError):clean.selection(self.f.manager,'forecast',self.f.args('forecast'),{})
        packet=deepcopy(self.f.packet);packet['company_id']='CIK9999999999'
        self.f.save('packet-01.json',packet)
        with self.assertRaises(ValueError):clean.selection(self.f.manager,'controller',(packet,self.f.args('controller')[-1]),{})

    def test_study_clean_dispatch_never_reads_old_plan_or_ancestry(self):
        with patch.object(clean,'study',return_value={'fixture':'original'}) as study:
            self.assertEqual(runtime._study({'clean_slate_policy':clean.POLICY}),{'fixture':'original'})
            study.assert_called_once()

    def test_clean_runtime_binds_changed_native_cleanup_without_expanding_legacy_sources(self):
        self.assertIn('tools/earnings_native_failure.py',runtime.source_paths(model_budget=True,training=True,clean_slate=True))
        self.assertNotIn('tools/earnings_native_failure.py',runtime.source_paths(model_budget=True,training=True))


class PhysicalIntentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.summary={'schema':'summary','rows':list(range(25))}
        self.payload={'input':[{'role':'user','content':json.dumps({'feedback':self.summary})}]}
        record=dict(request_id='fixture-id',payload=self.payload,reserved_nano_usd=19)
        request=engine.save(self.root/'01-request.json',record)
        engine.save(self.root/'http-generation.intent.json',dict(endpoint='/v1/responses',
            budget_request_id='fixture-id',request_receipt_sha256=request['sha256'],complete_reservation=record,
            retry_allowed=False,payload=dict(self.payload,max_output_tokens=5,service_tier='default',store=False)))
        response={'status':'completed','public':'fixture'}
        engine.save(self.root/'01-response.json',response);engine.save(self.root/'http-generation.response.json',response)
        (self.root/'http-generation.raw.bin').write_bytes(b'opaque fixture: never decoded')
        count={'input_tokens':17};engine.save(self.root/'01-count.json',count)
        engine.save(self.root/'http-count.intent.json',dict(endpoint='/v1/responses/input_tokens',payload=self.payload))
        engine.save(self.root/'http-count.response.json',count)

    def test_physical_count_generation_opaque_raw_and_response_rejoin(self):
        evidence=clean.physical_requests(self.root,summary=self.summary)
        self.assertTrue(any(b['path'].endswith('.raw.bin') for b in evidence))

    def test_actual_input_substitution_refused(self):
        request=engine.read(engine.pin(self.root/'http-generation.intent.json'))
        request['payload']={'input':[]}
        (self.root/'http-generation.intent.json').write_text(json.dumps(request))
        with self.assertRaises(ValueError):clean.physical_requests(self.root,summary=self.summary)

    def test_duplicate_generation_and_missing_count_refused(self):
        intent=engine.read(engine.pin(self.root/'http-generation.intent.json'))
        duplicate=self.root/'http-duplicate.intent.json';engine.save(duplicate,intent)
        with self.assertRaisesRegex(ValueError,'Unique actual HTTP'):
            clean.physical_requests(self.root)
        duplicate.unlink();(self.root/'01-count.json').unlink()
        with self.assertRaises(FileNotFoundError):clean.physical_requests(self.root)

    def test_saved_feedback_alone_is_not_physical_input(self):
        with self.assertRaisesRegex(ValueError,'feedback missing'):
            clean.physical_requests(self.root,summary={'different':'summary'})

    def test_missing_reservation_or_mismatched_numbered_response_is_refused(self):
        p=self.root/'http-generation.intent.json';intent=json.loads(p.read_text())
        intent.pop('complete_reservation');p.write_text(json.dumps(intent))
        with self.assertRaises(ValueError):clean.physical_requests(self.root)


class AuthorReceivingTests(unittest.TestCase):
    """Real DeltaAuthor -> PreviewBroker -> PopulationBroker, inert model transport."""
    def setUp(self):
        from earnings_population import version
        from earnings_population_broker import PopulationBroker
        from earnings_population_delta_author import DeltaAuthor, _PreviewBroker
        from market_rsi import digest
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.summary=dict(schema='earnings_training25_public_summary_v1',
            rows=[dict(company_id=str(i),targets=[dict(target_id=str(t),predicted_value='17',points_awarded=1)
                for t in range(5)]) for i in range(25)])
        self.feedback=engine.save(self.root/'feedback.json',self.summary)
        self.r=self.root/'R.py';self.r.write_text("PROGRAM={'axis':'R'}\ndef run(payload):\n    return {}\n")
        h=self.root/'H.py';h.write_text("PROGRAM={'axis':'H','tools':[]}\ndef run(payload):\n    return {}\n")
        self.parent=version(engine.pin(self.r),engine.pin(h),method='Unscored fixture scaffold')
        self.scope={'fixture':'training scope'};self.task=dict(mode='proposal',feedback=self.feedback,
            scaffold=dict(stable_id=self.parent['id'],versions={self.parent['id']:self.parent}))
        self.runtime=engine.save(self.root/'runtime.json',dict(clean_slate_policy=clean.POLICY))
        class Broker(PopulationBroker):
            def _definitions(inner):return []
            def current_programs(inner):
                return {axis:dict(source_sha256=self.parent[axis]['sha256']) for axis in ('R','H')}
        self.base=Broker.__new__(Broker)
        self.base.versions={self.parent['id']:self.parent};self.base.definitions=[]
        self.base.research_context_binding=None;self.base.training_scope=self.scope
        self.base.clean_slate_runtime_binding=self.runtime
        self.context=dict(schema='earnings_population_author_context_v1',parent_version_id=self.parent['id'],
            parent_programs=self.base.references()[self.parent['id']],feedback_binding=self.feedback,
            feedback_sha256=digest(self.feedback),feedback=self.summary,training_comparator=self.summary,
            clean_slate_policy=clean.POLICY,scaffold_semantics='Unscored ABI only')
        self.context_path=self.root/'author-context.json'
        self.base.population_context_binding=engine.save(self.context_path,self.context)
        self.author=DeltaAuthor.__new__(DeltaAuthor);self.author.broker=_PreviewBroker(self.base)
        self.chosen=dict(schema='earnings_capacity_decision_v1',axis='R',component='research_policy',
            parent_pair_sha256=self.parent['id'],feedback_sha256=digest(self.feedback),
            hypothesis='Fixture method',expected_effect='Test fixture effect')
        self.received=[]
        def fake_open(prompt,slot,instructions,format,decode,*statuses):
            self.received.append(prompt)
            response=dict(status='completed',error=None,output=[dict(type='message',role='assistant',
                status='completed',content=[dict(type='output_text',text=json.dumps(dict(
                    decision_sha256=digest(self.chosen),parent_source_sha256=self.parent['R']['sha256'],
                    edits=[dict(kind='replace',old_text='return {}',new_text="return {'signal':1}")],
                    test_text="CASES=[{'input':{},'expected':{'signal':1}}]")))])])
            decode(response)
            return engine.save(self.root/'model-reply-fixture.json',response)
        self.author._run_open=fake_open
        self.p=patch.object(clean,'read_task',return_value=(self.task,self.scope));self.p.start();self.addCleanup(self.p.stop)

    def test_actual_author_broker_chain_delivers_full125_pairs_without_legacy_context(self):
        from earnings_open_program import program
        self.author.author(self.chosen,program(self.r.read_bytes(),'R'),str(self.root/'author-slot'),
            parent_binding=self.parent['R'])
        context=self.received[0]['research_context']
        self.assertEqual(context['training_comparator'],self.summary)
        self.assertEqual(sum(len(r['targets']) for r in context['training_comparator']['rows']),125)
        self.assertNotIn('campaign',context);self.assertNotIn('prior_candidate',context)
        self.assertIsNone(self.author.broker.active)

    def test_old_history_or_incomplete_feedback_fails_before_model_transport(self):
        from earnings_open_program import program
        self.context['prior_candidate']={'forbidden':'old lineage'}
        self.context_path.write_text(json.dumps(self.context));self.base.population_context_binding=engine.pin(self.context_path)
        with self.assertRaisesRegex(ValueError,'only exact Round0'):
            self.author.author(self.chosen,program(self.r.read_bytes(),'R'),str(self.root/'author-slot'),
                parent_binding=self.parent['R'])
        self.assertEqual(self.received,[])


class ComparisonTests(unittest.TestCase):
    """Saved public evidence fixtures; neither model nor protected scorer runs."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.ids=['CIK%010d'%i for i in range(1,26)]
        self.descriptor_binding=dict(path='/fixture/new-frozen.json',sha256='a'*64)
        self.descriptor=dict(training=self.ids,candidate=dict(id='new-frozen-pair'))
        self.windows=[];self.verified={};self.baseline=[]
        for i,cik in enumerate(self.ids):
            slot=self.root/str(i);slot.mkdir()
            predictions=dict(predictions=[dict(target_id=t,predicted_value=str(i)) for t in clean.training.TARGETS])
            engine.save(slot/'predictions.json',predictions)
            engine.save(slot/'01-request.json',dict(fixture=True))
            response=dict(status='completed',error=None,output=[dict(type='message',role='assistant',status='completed',
                content=[dict(type='output_text',text=json.dumps(predictions))])])
            engine.save(slot/'01-response.json',response)
            engine.save(slot/'population-public-feedback.json',dict(version_id='new-frozen-pair',company_id=cik,
                points=3,target_scores=[dict(target_id=t,points_awarded=p)
                    for t,p in zip(clean.training.TARGETS,[1,1,0,1,0])]))
            bound=dict(path=str(slot/'clean-slate-window-result.json'),sha256='b'*64);self.windows.append(bound)
            self.verified[bound['path']]=dict(task=dict(company_id=cik,company_ids=[cik],frozen_candidate=self.descriptor_binding),
                runtime=dict(slots=dict(forecast=[str(slot)])),result=dict(result=dict(results=[dict(result=dict(points=3))])))
            self.baseline.append(dict(company_id=cik,points=3,targets=[dict(target_id=t,predicted_value='17',points_awarded=p)
                for t,p in zip(clean.training.TARGETS,[1,1,1,0,0])]))
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(clean,'load_frozen',return_value=self.descriptor))
        self.stack.enter_context(patch.object(clean,'closed_evidence',side_effect=lambda b,proposal:self.verified[b['path']]))
        self.stack.enter_context(patch.object(clean,'round0_feedback',return_value=dict(rows=self.baseline)))

    def test_partial_coverage_has_no_mean_selection_or_mutation(self):
        value=clean.compare(self.descriptor_binding,self.windows[:6])
        self.assertEqual((value['scored'],value['not_measured']),(6,19))
        self.assertIsNone(value['candidate_mean'])
        self.assertEqual(value['decision'],'INCOMPLETE_NO_SELECTION')
        self.assertFalse(value['next_mutation_allowed'])

    def test_full_tie_retains_round0_and_reports_target_regressions(self):
        value=clean.compare(self.descriptor_binding,self.windows)
        self.assertEqual(value['candidate_mean'],3)
        self.assertEqual(value['decision'],'RETAIN_ROUND0')
        self.assertEqual(value['rows'][0]['regressions'],['T003'])
        self.assertEqual([r['delta'] for r in value['rows'][0]['targets']],[0,0,-1,1,0])

    def test_only_complete_strict_improvement_selects_new_candidate(self):
        for i in range(25):
            slot=self.root/str(i);p=slot/'population-public-feedback.json';value=json.loads(p.read_text())
            value['points']=3.5;value['target_scores'][-1]['points_awarded']=.5;p.write_text(json.dumps(value))
            self.verified[self.windows[i]['path']]['result']['result']['results'][0]['result']['points']=3.5
        self.assertEqual(clean.compare(self.descriptor_binding,self.windows)['decision'],'ADOPT_CANDIDATE')

    def test_duplicate_wrong_candidate_and_prediction_substitution_refused(self):
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            clean.compare(self.descriptor_binding,[self.windows[0],self.windows[0]])
        record=self.verified[self.windows[0]['path']];record['task']['frozen_candidate']={}
        with self.assertRaisesRegex(ValueError,'Another frozen'):
            clean.compare(self.descriptor_binding,self.windows[:1])
        record['task']['frozen_candidate']=self.descriptor_binding
        (self.root/'0'/'predictions.json').write_text(json.dumps(dict(predictions=[])))
        with self.assertRaisesRegex(ValueError,'final prediction'):
            clean.compare(self.descriptor_binding,self.windows[:1])


if __name__=='__main__':unittest.main()
