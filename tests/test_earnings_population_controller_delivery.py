"""Public-proposal import routing, not a new provider or predictive result.

Temporary files and source-only fake role/case seams; no API, Docker or QA.
The two-round driver test uses synthetic Author/review/score outputs explicitly.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import earnings_population as pool
import earnings_population_controller_delivery as delivery
import earnings_population_loop as loop
import earnings_population_services as services
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness import feedback_linked_loop as driver


class ControllerDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='controller-public-import-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.attempt = self.root/'new'
        self.attempt.mkdir()
        self.sources = {name:engine.save(self.root/(str(i)+'.json'), {'source_only_fixture':name})
            for i,name in enumerate((delivery.SOURCE, 'tools/earnings_population_roles.py',
                                     'tools/earnings_population_services.py'))}
        self.parent = pool.version(self.sources[delivery.SOURCE], self.sources['tools/earnings_population_roles.py'])
        self.state = pool.initialize(self.parent, {'K':'a'*64,'M':'b'*64,'C':'c'*64})
        self.old_prompt = dict(active_versions=[self.parent['id']], explorers=[], feedback_sha256='d'*64)
        self.proposal = dict(schema='earnings_capacity_decision_v1', axis='R', component='research_policy',
            parent_pair_sha256=self.parent['id'], feedback_sha256='d'*64,
            hypothesis='Repair source-linked financial table reading.', expected_effect='Preserve correct parent behavior.')
        raw = dict(status='completed', error=None, output=[dict(type='message', role='assistant',
            content=[dict(type='output_text', text=json.dumps(dict(self.proposal, retire_branch_id='none')))])])
        self.bundle = dict(schema='earnings_population_controller_proposal_import_v1', mode=delivery.MODE,
            new_model_called=False, original_prompt=engine.save(self.root/'old-prompt.json', self.old_prompt),
            raw_response=engine.save(self.root/'old-raw.json', raw), original_decision_public=self.proposal,
            original_feedback_sha256='d'*64, runtime=engine.save(self.root/'old-runtime.json', {'synthetic':True}),
            settlement=engine.save(self.root/'old-settlement.json', {'synthetic':True}),
            failed_attempt=engine.save(self.root/'old-failed.json', {'status':'FAILED_NO_RETRY'}))
        self.origin = engine.save(self.root/'origin.json', {'controller_stage_import':self.bundle})
        resumed = dict(controller_import_mode=delivery.MODE, prior_failed_attempt=self.bundle['failed_attempt'])
        self.resume = engine.save(self.root/'resume.json', resumed)
        self.study = engine.save(self.root/'study.json', dict(campaign_origin=self.origin, campaign_resume=self.resume))
        self.slot = self.attempt/'roles/controller-01'
        self.runtime = dict(forecast_study=self.study, slots={'controller':[str(self.slot)]},
                            sources=self.sources, companies=['development-company'])
        self.context = {'origin':self.origin}
        self.packet = dict(round_index=1, population=self.state, feedback={'synthetic_public':'new'},
                           parent_feedback_sha256=digest({'synthetic_public':'new'}))
        self.prompt = dict(self.old_prompt, feedback_sha256=self.packet['parent_feedback_sha256'])
        engine.save(self.attempt/'packet-01.json', self.packet)

    def route(self):
        return delivery.route(self.runtime, self.context, self.prompt, self.packet, str(self.slot))

    def test_import_is_explicit_new_receipt_no_ordinary_role_or_http(self):
        old = deepcopy(self.bundle)
        chosen = self.route()
        self.assertEqual(engine.read(chosen), dict(self.proposal,
            feedback_sha256=self.packet['parent_feedback_sha256']))
        self.assertEqual(self.bundle, old)
        receipt = engine.read(engine.pin(self.slot/'controller-proposal-import.json'))
        self.assertFalse(receipt['new_model_called'])
        self.assertEqual(receipt['original_raw'], self.bundle['raw_response'])
        self.assertEqual(receipt['new_feedback_sha256'], self.packet['parent_feedback_sha256'])
        self.assertEqual({p.name for p in self.slot.iterdir()},
            {'controller-proposal-import.json','population-decision.json'})
        imported = engine.pin(self.slot/'controller-proposal-import.json')
        rows = {'input':{'packet':engine.pin(self.attempt/'packet-01.json')},
                'controller':{'decision':chosen,'proposal_import':imported,'artifacts':[chosen,imported]}}
        reader = SimpleNamespace(read=engine.read, pin=engine.pin)
        delivery.verify(reader, self.attempt, rows, engine.read(self.origin), self.runtime)

    def test_same_slot_cannot_import_twice(self):
        self.route()
        with self.assertRaises(FileExistsError):
            self.route()

    def test_new_second_controller_is_not_replaced_by_import(self):
        packet = dict(self.packet, round_index=2)
        self.assertIsNone(delivery.route(self.runtime,self.context,self.prompt,packet,
                                         str(self.attempt/'roles/controller-02')))

    def test_missing_manifest_marker_or_foreign_failure_reject(self):
        for index,changes in enumerate(({'controller_import_mode':'other'}, {'prior_failed_attempt':self.bundle['runtime']})):
            resumed = engine.save(self.root/f'bad-resume-{index}.json', dict(engine.read(self.resume), **changes))
            self.runtime['forecast_study'] = engine.save(self.root/f'bad-study-{index}.json',
                dict(campaign_origin=self.origin,campaign_resume=resumed))
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.route()

    def test_altered_old_raw_public_decision_and_feedback_reject(self):
        for changes in ({'original_feedback_sha256':'e'*64},
                        {'original_decision_public':dict(self.proposal,hypothesis='human substitute')},
                        {'raw_response':self.bundle['settlement']}):
            with self.subTest(changes=changes),self.assertRaises((ValueError,KeyError)):
                delivery.selected(dict(self.bundle, **changes),self.packet,self.prompt)

    def test_current_parent_pool_packet_or_feedback_cannot_be_substituted(self):
        for changes in ({'active_versions':['e'*64]}, {'feedback_sha256':'e'*64}, {'explorers':['e'*64]}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                delivery.selected(self.bundle,self.packet,dict(self.prompt,**changes))
        with self.assertRaises(ValueError):
            delivery.selected(self.bundle,dict(self.packet,feedback={'different':True}),self.prompt)

    def test_history_rejects_invented_role_success_or_receipt_change(self):
        chosen = self.route()
        imported = engine.pin(self.slot/'controller-proposal-import.json')
        rows = {'input':{'packet':engine.pin(self.attempt/'packet-01.json')},
                'controller':{'decision':chosen,'proposal_import':imported,'artifacts':[chosen,imported]}}
        reader = SimpleNamespace(read=engine.read,pin=engine.pin)
        engine.save(self.slot/'result.json', {'status':'COMPLETED_DECISION'})
        with self.assertRaises(ValueError):
            delivery.verify(reader,self.attempt,rows,engine.read(self.origin),self.runtime)

    def test_two_round_original_driver_import_then_new_Author_then_feedback_Controller(self):
        # Fake research/evaluation outputs, original once-only seven-stage loop.
        # This proves handoff, not a model, financial test or score improvement.
        root = self.root/'driver'
        authored, observed, forecasted = [], [], []
        child_r = engine.save(self.root/'child-R.json', {'synthetic_new_source':True})
        runtime = dict(self.runtime, slots={'controller':[str(root/'roles/controller-01'),
                                                        str(root/'roles/controller-02')]})
        def control(packet, slot):
            prompt = dict(active_versions=[packet['population']['stable_id'], *packet['population']['explorers']],
                          explorers=packet['population']['explorers'], feedback_sha256=packet['parent_feedback_sha256'])
            routed = delivery.route(runtime,self.context,prompt,packet,slot)
            if routed is not None:
                return routed
            observed.append(deepcopy(packet))
            Path(slot).mkdir(parents=True)
            value = dict(self.proposal,axis='continue',component='none',
                         feedback_sha256=packet['parent_feedback_sha256'])
            return engine.save(Path(slot)/'population-decision.json',value)
        def author(chosen, state, slot):
            authored.append(deepcopy(chosen))
            return pool.version(child_r,self.parent['H'],parent=self.parent['id'],axis='R',
                                method=chosen['hypothesis'],author='synthetic-test-only')
        def review(child, state, slot):
            return dict(accepted_for_exploration=True,evidence=[child_r])
        def forecast(version, company, slot):
            forecasted.append((company,version['id']))
            return dict(version_id=version['id'],points=1,evidence=[child_r])
        result = loop.run(root,self.state,['synthetic-dev-1','synthetic-dev-2'],
            dict(controller=control,author=author,review=review,forecast=forecast),
            admit=lambda context:True,max_rounds=2,
            identity=lambda:{stage:{'fixture_only':stage} for stage in driver.STAGES})
        self.assertEqual(result['status'],'completed')
        self.assertEqual(len(authored),1)
        self.assertEqual(authored[0]['hypothesis'],self.proposal['hypothesis'])
        self.assertEqual(len(observed),1)
        first_feedback = engine.pin(root/'feedback-01.json')
        self.assertEqual(observed[0]['feedback'],first_feedback)
        self.assertEqual(observed[0]['parent_feedback_sha256'],digest(first_feedback))
        self.assertEqual(len(forecasted),4)
        self.assertTrue((root/'roles/controller-01/controller-proposal-import.json').is_file())
        self.assertFalse((root/'roles/controller-02/controller-proposal-import.json').exists())
        first = engine.read(engine.pin(root/'loop/round-0001-controller.done.json'))['output']
        second = engine.read(engine.pin(root/'loop/round-0002-controller.done.json'))['output']
        self.assertEqual(first['proposal_import'],engine.pin(root/'roles/controller-01/controller-proposal-import.json'))
        self.assertEqual(first['artifacts'],[first['decision'],first['proposal_import']])
        self.assertNotIn('proposal_import',second)
        self.assertEqual(second['artifacts'],[second['decision']])

    def test_import_history_requires_original_sealed_binding_and_unchanged_bytes(self):
        chosen = self.route(); path = self.slot/'controller-proposal-import.json'
        imported = engine.pin(path)
        control = dict(decision=chosen,proposal_import=imported,artifacts=[chosen,imported])
        rows = dict(input={'packet':engine.pin(self.attempt/'packet-01.json')},controller=control)
        reader=SimpleNamespace(read=engine.read,pin=engine.pin)
        for bad in ({'decision':chosen,'artifacts':[chosen]},
                    dict(control,proposal_import=self.bundle['settlement']),
                    dict(control,artifacts=[chosen])):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                delivery.verify(reader,self.attempt,dict(rows,controller=bad),engine.read(self.origin),self.runtime)
        raw=path.read_bytes(); path.write_bytes(raw+b' ')
        with self.assertRaises(ValueError):
            delivery.verify(reader,self.attempt,rows,engine.read(self.origin),self.runtime)
        path.unlink()
        with self.assertRaises((ValueError,FileNotFoundError)):
            delivery.verify(reader,self.attempt,rows,engine.read(self.origin),self.runtime)


if __name__ == '__main__':
    unittest.main()
