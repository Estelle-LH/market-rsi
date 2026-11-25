"""Portable P2 producer/metadata/serial owner contracts, not live Native proof.

P1 authentication and old completed ancestry are explicit fixture seams. Real
prepare, canonical metadata receiver, training admission and execute are used;
the original clock is retained in the invented owner fixture. No provider,
production ledger, candidate/scorer execution or full history is invoked.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import earnings_population_frozen_panel as panel
import earnings_population_runtime as runtime
import earnings_population_run as run
import earnings_population as pool
import earnings_population_live_guard as guard
import earnings_population_campaign_admission as admission
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_population_training35_reuse as training_fixture
import test_earnings_population_run as entry_fixture


class PanelFixture(training_fixture.ProducerReceiverFixture):
    needs_A2 = False

    def setUp(self):
        super().setUp()
        self.id = 'edgar-population-20261016-37'
        self.stack.enter_context(patch.object(runtime, 'ROOT', self.root))
        Path(self.restore_plan['path']).write_text(json.dumps(dict(schema='supervisor_bottleneck_plan_v1',
            id='earnings-population-restore-20261016',human_authorization=runtime.AUTHORIZATION)))
        forecast_names=('forecaster','tools/earnings_entry.py','tools/earnings_open_worker.py',
                        'tools/earnings_population_execution.py')
        run.source_paths.return_value.update({name:self.forecaster['path'] for name in forecast_names})
        self.descriptor = dict(schema=panel.SCHEMA, policy=panel.POLICY,
            authority=self.p.authority, split=self.p.split,
            round0={'manifest':self.comparator},
            origin=dict(completed_result=self.previous,population=self.population,
                latest_feedback=self.feedback,last_scored_feedback=self.feedback),
            members=dict(control=self.control,parent=self.parent,candidate=self.f.child),
            companies=[{'company_id':c} for c in self.scope['training']],
            financial_policy=dict(model_rates=self.resident['runtime']['models']['gpt-6.1-sol'],
                forecast_limits=dict(max_input_tokens=100000,max_output_tokens=25000,wall_seconds=1800),
                forecast_sources={name:deepcopy(self.forecaster) for name in forecast_names}))
        self.descriptor_binding = engine.save(self.root/'frozen-panel.json',self.descriptor)
        self.p1 = self.stack.enter_context(patch.object(panel, 'load_descriptor',return_value={
            'descriptor':deepcopy(self.descriptor),'base_origin':deepcopy(self.origin)}))
        self.metadata = []

    def capture_admission(self,binding,**kwargs):
        value = super().capture_admission(binding,**kwargs)
        self.metadata.append(runtime._panel_metadata(value,engine.read(value['forecast_study'])))
        return value

    def prepare_panel(self,arms=None,**changes):
        kwargs = dict(company_count=1,campaign_from=self.previous['path'],cumulative400=True,
            window_minutes=90,training_cik=training_fixture.COMPANY,training_split=self.p.split,
            training_comparator=self.comparator,model_budget_amendment=self.model,
            frozen_panel=self.descriptor_binding,panel_arms=arms)
        kwargs.update(changes)
        return run.prepare(self.id,**kwargs)


class ProducerAndMetadataTests(PanelFixture):
    def test_real_prepare_to_training_admission_and_current_metadata_receiver(self):
        bound = self.prepare_panel(); value = engine.read(bound); study = engine.read(value['forecast_study'])
        self.assertEqual(len(self.metadata),1)
        self.assertEqual(value['frozen_panel_policy'],panel.POLICY)
        for key in ('frozen_panel_policy','frozen_panel','frozen_panel_window'):
            self.assertEqual(value[key],study[key])
        self.assertEqual(self.metadata[0]['window']['arms'],list(panel.ARMS))
        self.assertEqual(value['slots']['forecast'],self.metadata[0]['window']['slots'])
        self.assertEqual(engine.read(value['initial_population']),self.origin['population'])
        self.assertEqual(engine.read(study['campaign_origin']),self.origin)
        self.assertEqual(value['baseline'],self.baseline)
        self.assertEqual(value['additional_cap_nano_usd'],5_000_000_000)
        self.assertEqual(value['window_minutes'],90)
        self.assertEqual(value['model_budget_amendment'],self.model)
        self.assertEqual(value['limits'],dict(run.role_limits(),forecast=dict(
            max_input_tokens=100000,max_output_tokens=25000,wall_seconds=1800)))
        self.assertFalse((self.root/'attempts'/self.id).exists())
        # P1 producer result is reused; one separate old-ancestry replay remains
        # in actual training admission. Neither seam authenticates real36 here.
        self.p1.assert_called_once()
        self.old_loader.assert_called_once()
        self.assertNotIn('training_stage_attachment',study)

    def test_subset_preserves_original_arm_index_and_independent_selection(self):
        value = engine.read(self.prepare_panel(['candidate']))
        slot = str(self.root/'attempts'/self.id/'roles/forecast-01-02')
        self.assertEqual(value['slots']['forecast'],[slot])
        selected = runtime.panel_selection(value,slot)
        self.assertEqual(set(selected),{'company_id','arm','window','version','bindings'})
        self.assertEqual(selected['version'],self.f.child)
        self.assertEqual(selected['arm'],'candidate')
        with self.assertRaises(ValueError):runtime.panel_selection(value,slot.replace('-02','-00'))

    def test_actual_prepare_metadata_to_original_p3_selection_without_packet_or_frozen_pool(self):
        bound=self.prepare_panel();value=engine.read(bound)
        manager=guard.RoleValidation(bound,value,lambda:deepcopy(value))
        for arm,slot in zip(panel.ARMS,value['slots']['forecast']):
            version=self.descriptor['members'][arm]
            selected=manager._selection('forecast',(deepcopy(version),training_fixture.COMPANY,slot),{})
            self.assertEqual(selected['version'],version)
            self.assertEqual(selected['company'],training_fixture.COMPANY)
            self.assertIn(value['frozen_panel_window'],selected['bindings'])
        self.assertFalse(list((self.root/'attempts'/self.id).glob('packet-*.json')))
        self.assertFalse(list((self.root/'attempts'/self.id).glob('frozen-pool-*.json')))
        # Only actual current selection is exercised, not Native registration,
        # original financial admission or a full authenticated role invocation.

    def test_original_study_dispatch_authenticates_panel_before_normal_admission(self):
        value=engine.read(self.prepare_panel())
        class Reached(Exception):pass
        with patch.object(admission,'validate',side_effect=Reached('normal admission still required')) as normal:
            with self.assertRaises(Reached):runtime._study(value)
        normal.assert_called_once()
        self.p1.side_effect=ValueError('explicit P1 authentication refusal')
        with patch.object(admission,'validate',side_effect=AssertionError('unverified origin walked')) as normal:
            with self.assertRaisesRegex(ValueError,'P1 authentication'):runtime._study(value)
        normal.assert_not_called()

    def test_wrong_verified_origin_or_resource_refuses_before_normal_admission(self):
        value=engine.read(self.prepare_panel())
        wrong=deepcopy(self.p1.return_value);wrong['base_origin']['population']['stable_id']='f'*64
        self.p1.return_value=wrong
        with patch.object(admission,'validate',side_effect=AssertionError('unverified origin walked')):
            with self.assertRaisesRegex(ValueError,'origin/pool/model/resources'):runtime._study(value)
        self.p1.return_value={'descriptor':deepcopy(self.descriptor),'base_origin':deepcopy(self.origin)}
        value['limits']['forecast']['max_output_tokens']+=1
        with patch.object(admission,'validate',side_effect=AssertionError('resource drift walked')):
            with self.assertRaisesRegex(ValueError,'origin/pool/model/resources'):runtime._study(value)

    def test_changed_forecast_source_is_not_silently_labelled_matched(self):
        value=engine.read(self.prepare_panel())
        class Reached(Exception):pass
        for name in self.descriptor['financial_policy']['forecast_sources']:
            changed=deepcopy(value);changed['sources'][name]['sha256']='f'*64
            with self.subTest(source=name),patch.object(admission,'validate',side_effect=Reached('changed forecast source entered admission')) as normal:
                try:runtime._study(changed)
                except ValueError:pass
                except Reached:self.fail('Changed forecast Source reached normal admission before comparability refusal')
            normal.assert_not_called()

    def test_invalid_slice_and_heldout_stop_before_panel_or_resident_body(self):
        for arms in ([],['parent','control'],['candidate','candidate'],['other'],True):
            with self.subTest(arms=arms),self.assertRaises(ValueError):self.prepare_panel(arms)
        self.p1.assert_not_called()
        with self.assertRaises(ValueError):self.prepare_panel(training_cik=self.p.heldout[0])
        self.p1.assert_not_called()
        self.assertFalse((self.root/'inputs'/self.id).exists())

    def test_wrong_explicit_origin_refuses_before_input_or_foreign_result_read(self):
        foreign=self.root/'attempts/edgar-population-20261016-99/population-run-result.json'
        with self.assertRaisesRegex(ValueError,'origin/split/Round0'):
            self.prepare_panel(campaign_from=str(foreign))
        self.assertFalse((self.root/'inputs'/self.id).exists())
        self.old_loader.assert_not_called()

    def test_companion_erasure_null_and_alias_refuse_before_descriptor_read(self):
        value = engine.read(self.prepare_panel()); study = engine.read(value['forecast_study'])
        original = runtime._local
        def no_descriptor(binding):
            if binding == self.descriptor_binding:raise AssertionError('Descriptor read before marker checks')
            return original(binding)
        for key in ('frozen_panel_policy','frozen_panel','frozen_panel_window'):
            for where in ('runtime','study'):
                for null in (False,True):
                    v,s = deepcopy(value),deepcopy(study); target = v if where=='runtime' else s
                    if null:target[key]=None
                    else:target.pop(key)
                    with self.subTest(key=key,where=where,null=null),patch.object(runtime,'_local',side_effect=no_descriptor),self.assertRaises(ValueError):
                        runtime._panel_metadata(v,s)
        v,s=deepcopy(value),deepcopy(study)
        for key in ('frozen_panel_policy','frozen_panel','frozen_panel_window'):v.pop(key);s.pop(key)
        with self.assertRaises(ValueError):runtime._panel_metadata(v,s)  # Existing canonical marker refuses downgrade.
        alias=deepcopy(value['frozen_panel_window']);alias['path']=str(self.root/'inputs'/self.id/'..'/self.id/'frozen-panel-window.json')
        v,s=deepcopy(value),deepcopy(study);v['frozen_panel_window']=s['frozen_panel_window']=alias
        with self.assertRaises(ValueError):runtime._panel_metadata(v,s)

    def test_wrong_company_version_slot_source_or_origin_refuses(self):
        value = engine.read(self.prepare_panel()); study=engine.read(value['forecast_study'])
        selected=engine.read(value['frozen_panel_window'])
        path=Path(value['frozen_panel_window']['path']);original_bytes=path.read_bytes()
        for key,bad in [('company_id',self.scope['training'][0]),('versions',['f'*64]*3),('slots',[str(self.root/'foreign')])]:
            if key=='company_id' and bad==training_fixture.COMPANY:bad=self.scope['training'][-1]
            changed=deepcopy(selected);changed[key]=bad
            path=Path(value['frozen_panel_window']['path']);path.write_text(json.dumps(changed));binding=engine.pin(path)
            v,s=deepcopy(value),deepcopy(study);v['frozen_panel_window']=s['frozen_panel_window']=binding
            with self.subTest(key=key),self.assertRaises(ValueError):runtime._panel_metadata(v,s)
        # Changed source bytes without repinning remain refused by the checked reader.
        path.write_bytes(original_bytes)
        self.assertEqual(engine.pin(path),value['frozen_panel_window'])
        Path(self.descriptor_binding['path']).write_text('{}')
        with self.assertRaises(ValueError):runtime._panel_metadata(value,study)

    def test_no_policy_plain_prepare_keeps_legacy_shape(self):
        bound=self.prepare(identifier=self.id,attachment=False);value=engine.read(bound)
        self.assertIsNone(self.metadata[-1])
        self.assertFalse(any(k.startswith('frozen_panel') for k in value))
        self.assertEqual(len(value['slots']['forecast']),6)
        self.p1.assert_not_called()


class SerialExecutionTests(unittest.TestCase):
    def setUp(self):
        self.f=entry_fixture.ExecutionContracts(methodName='runTest');self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.stack=self.enterContext(__import__('contextlib').ExitStack())
        self.value=deepcopy(self.f.value);self.value['companies']=self.f.ciks[:1]
        self.value.update(frozen_panel_policy=panel.POLICY,frozen_panel={'path':'synthetic descriptor','sha256':'a'*64},
            frozen_panel_window={'path':'synthetic window','sha256':'b'*64})
        slots=[str(self.f.root/'roles'/f'forecast-01-{i:02d}') for i in range(3)]
        self.value['slots']['forecast']=slots
        state=engine.read(self.value['initial_population']);original=state['versions'][state['stable_id']]
        self.versions=[pool.version(engine.save(self.f.owned/f'arm{i}.json',{'inert_source':i}),original['H']) for i in range(3)]
        self.selected={s:dict(company_id=self.value['companies'][0],arm=arm,version=v,window={},bindings=[])
                       for s,arm,v in zip(slots,panel.ARMS,self.versions)}
        self.calls=[];self.fail_arm=None;self.wrong_version=False
        self.stack.enter_context(patch.object(run,'preflight',return_value=self.value))
        self.stack.enter_context(patch.object(run,'panel_selection',side_effect=lambda value,slot:deepcopy(self.selected[slot])))
        self.f.owner.side_effect=self.owner

    @contextmanager
    def owner(self,binding,**kwargs):
        with self.f.open_owner(binding,**kwargs) as live:
            self.forbidden={r:Mock(side_effect=AssertionError('No paid regeneration '+r)) for r in ('controller','author','review')}
            live['roles']=dict(self.forbidden,forecast=self.forecast)
            yield live

    def forecast(self,version,company,slot):
        arm=self.selected[slot]['arm'];self.calls.append(arm)
        self.assertEqual(self.f.instances[-1].current,company)
        self.assertEqual(version,self.selected[slot]['version'])
        self.assertFalse(self.f.closed)
        if arm==self.fail_arm:raise RuntimeError('synthetic measured role failure')
        return dict(version_id='f'*64 if self.wrong_version else version['id'],points=2.5,
                    evidence=[self.value['initial_population']])

    def test_only_serial_forecasts_distinct_receipt_and_original_owner_clock(self):
        result=run.execute(self.f.bound());value=engine.read(result)
        self.assertEqual(Path(result['path']).name,'frozen-panel-window-result.json')
        self.assertEqual(value['status'],'COMPLETED_FROZEN_PANEL_WINDOW')
        self.assertEqual([r['arm'] for r in value['result']['results']],list(panel.ARMS))
        self.assertEqual(self.calls,list(panel.ARMS));self.assertTrue(self.f.closed)
        for call in self.forbidden.values():call.assert_not_called()
        self.f.loop.assert_not_called()
        self.assertFalse((self.f.root/'population-run-result.json').exists())
        self.assertFalse(list(self.f.root.glob('packet-*.json')))
        self.assertLess(self.f.events.index('budget_summary'),self.f.events.index('owner_closed'))

    def test_partial_failure_preserves_completed_rows_no_retry_or_fake_completion(self):
        self.fail_arm='parent'
        with self.assertRaisesRegex(RuntimeError,'synthetic measured'):run.execute(self.f.bound())
        failure=engine.read(engine.pin(self.f.root/'frozen-panel-window-failure.json'))
        self.assertEqual(self.calls,['control','parent'])
        self.assertEqual([r['arm'] for r in failure['completed_results']],['control'])
        self.assertFalse(failure['retry_allowed']);self.assertTrue(self.f.closed)
        self.assertFalse((self.f.root/'population-run-failure.json').exists())
        self.assertFalse((self.f.root/'frozen-panel-window-result.json').exists())

    def test_wrong_version_fails_before_accepting_any_arm(self):
        self.wrong_version=True
        with self.assertRaisesRegex(ValueError,'another version'):run.execute(self.f.bound())
        failure=engine.read(engine.pin(self.f.root/'frozen-panel-window-failure.json'))
        self.assertEqual(failure['completed_results'],[])
        self.assertEqual(self.calls,['control'])


if __name__=='__main__':unittest.main()
