"""Real production boundary calls, synthetic transport/child only; zero Train."""
from copy import deepcopy
import json
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import Mock, patch

from supervisor_harness import feedback_loop_runtime as r
from supervisor_harness import feedback_linked_loop as loop
from supervisor_harness import coevo_pilot_transaction as t
from supervisor_harness import opened_train_discovery_worker as w
from supervisor_harness import test_coevo_pilot_configuration as configuration_tests
from supervisor_harness.test_coevo_pilot_transaction import Clock
from supervisor_harness.test_account_controller_feedback_consumer import PARENT, INCUMBENT
from supervisor_harness import test_continuous_discovery_batch as batch_tests
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
from data_scientist_harness import test_micro_evolution as micro
from data_scientist_harness.co_evolution_loop import micro_pair_hash


class RuntimeTests(TestCase):
    def setUp(self):
        self.h = configuration_tests.ConfigurationTests(); self.h.setUp(); self.addCleanup(self.h.doCleanups)
        self.root, self.repo = self.h.root, self.h.f.repo
        self.h.ledger['authorization_sha256'] = self.h.authorization_binding['sha256']
        self.h.write('ledger', self.h.ledger)
        self.runtime = r.PilotRuntime(self.root, self.repo, self.h.authorization_binding,
                                      self.h.configuration_binding)
        for p in (patch.object(r, 'datetime', Clock), patch.object(w, 'datetime', Clock),
                  patch.object(t, 'ROOT', self.root), patch.object(t.c, '_transport', self.h.transport)):
            p.start(); self.addCleanup(p.stop)

    def prepared(self):
        return {'input': self.h.input_binding, 'authorization': self.h.authorization_binding,
                'review': self.h.review_binding, 'configuration': self.h.configuration_binding}

    def context(self, stage='controller'):
        return {'stage': stage, 'outputs': {'input': self.prepared()}}

    def test_real_original_transaction_once_and_closed_ledger(self):
        result = self.runtime.controller(self.context())
        self.assertEqual(result['decision']['schema'], 'controller_coevolution_proposal_v1')
        self.assertEqual(self.h.calls, 1)
        self.assertEqual(len(t._file(self.root / 'ledger.json')['controller_decisions']), 1)
        self.h.ledger['status'] = 'closed'; self.h.write('ledger', self.h.ledger)
        self.assertFalse(self.runtime.admit(self.context()))

    def test_stage_specific_caps_permit_finishing_not_extra_call(self):
        ledger = t._file(self.root / 'ledger.json')
        ledger['controller_decisions'] = [{'status': 'completed'}] * 3
        self.h.write('ledger', ledger)
        self.assertFalse(self.runtime.admit(self.context('controller')))
        self.assertTrue(self.runtime.admit(self.context('implement')))
        ledger['attempts'] = [{'status':'succeeded','fits_reserved':4}] * 3
        ledger['status'] = 'closed_at_attempt_cap'; self.h.write('ledger', ledger)
        self.assertFalse(self.runtime.admit(self.context('execute')))
        self.assertTrue(self.runtime.admit(self.context('result_review')))
        self.assertTrue(self.runtime.admit(self.context('reconcile')))

    def test_unresolved_authority_and_tools_drift_fail_closed(self):
        ledger = t._file(self.root / 'ledger.json')
        ledger['attempts'] = [{'status':'uncertain','fits_reserved':4}]
        self.h.write('ledger', ledger)
        self.assertFalse(self.runtime.admit(self.context('input')))
        self.h.authorization['account_transfer']['tools_enabled'] = True
        bad = self.h.write('authorization', self.h.authorization)
        with self.assertRaises(ValueError):
            r.PilotRuntime(self.root, self.repo, bad, self.h.configuration_binding)

    def test_original_failure_remains_reserved_no_retry(self):
        def failed(*args):
            self.h.calls += 1
            raise RuntimeError('uncertain original')
        with patch.object(t.c, '_transport', failed), self.assertRaises(RuntimeError):
            self.runtime.controller(self.context())
        self.assertFalse(self.runtime.admit(self.context()))
        self.assertEqual(self.h.calls, 1)

    def test_automatic_controller_feedback_continuation(self):
        # Two actual original-transaction code paths. Scientist/fit callbacks are
        # deterministic synthetic fixtures, not claimed model authorship/Train.
        self.h.response = lambda packet: self.response(packet)
        choices, reviewed = [], []
        def prepare(ctx):
            packet = deepcopy(self.h.packet)
            packet['memory']['previous_observation'] = ctx['previous_result']
            feedback_path = self.root / f"feedback-round-{ctx['round_index']}.json"
            t.c.save(feedback_path, {'observed':ctx['previous_result']})
            packet['bindings']['feedback'] = r.pin(feedback_path)
            packet['provided_source_sha256'].append(r.pin(feedback_path)['sha256'])
            input_path = self.root / f"input-round-{ctx['round_index']}.json"
            t.c.save(input_path, packet)
            review = {**self.h.review, 'input_sha256': r.pin(input_path)['sha256']}
            review_path = self.root / f"review-round-{ctx['round_index']}.json"
            t.c.save(review_path, review)
            return {**self.prepared(), 'input':r.pin(input_path), 'review':r.pin(review_path)}
        def implement(ctx):
            choice = ctx['outputs']['controller']['decision']['candidate']['recipe']
            choices.append(choice)
            return {'recipe':choice}
        def predict(ctx):
            recipe = ctx['outputs']['implement']['recipe']
            p = [0.8,0.2] if recipe == 'correct_negative' else [0.2,0.8]
            return {'predictions':p, 'brier':sum((a-y)**2 for a,y in zip(p,[1,0]))/2,
                    'synthetic':True, 'real_Train_fits':0}
        def review(ctx):
            result = ctx['outputs']['execute']; reviewed.append(result['brier'])
            return {**result,'independently_recomputed':True}
        handlers = self.runtime.handlers(input=prepare, implement=implement,
            source_review=lambda ctx:{'synthetic_source_check':True},
            result_review=review, reconcile=lambda ctx:{**ctx['outputs']['result_review'],
                'negative':ctx['outputs']['result_review']['brier'] > .5})
        handlers['execute'] = predict  # Explicit synthetic prediction callback.
        identity = lambda:{s:{'runtime_source':r.pin(Path(r.__file__)), 'fixture':s} for s in loop.STAGES}
        result = loop.run(self.root / 'loop', handlers, seed={'negative':False},
            admit=self.runtime.admit, max_rounds=2, handler_identity=identity)
        self.assertEqual(result['completed_rounds'],2)
        self.assertEqual(choices,['initial_negative','correct_negative'])
        self.assertEqual(self.h.calls,2)
        self.assertGreater(reviewed[0],reviewed[1])
        # Replay does not issue another Controller original, even after closure.
        ledger=t._file(self.root/'ledger.json'); ledger['status']='closed'; self.h.write('ledger',ledger)
        replay=loop.run(self.root/'loop',handlers,seed={'negative':False},admit=self.runtime.admit,
                        max_rounds=2,handler_identity=identity)
        self.assertEqual(replay,result); self.assertEqual(self.h.calls,2)

    def response(self, packet):
        value = configuration_tests.ConfigurationTests.response(self.h, packet)
        negative = packet['memory']['previous_observation']['negative']
        value['candidate']['recipe'] = 'correct_negative' if negative else 'initial_negative'
        return value

    def native(self):
        response = self.runtime.controller(self.context())['decision']
        native = self.root / 'native'
        batch = ContinuousDiscoveryBatch(native, allow_temporary=True,
            test_clock=lambda:Clock.now(), allow_test_clock=True)
        archive = batch_tests.ContinuousDiscoveryBatchTests().archived_parent()
        archive['candidate_sha256'] = PARENT
        batch.initialize(batch_id=self.h.authorization['batch_id'], start_utc=self.h.authorization['start_utc'],
            deadline_utc=self.h.authorization['deadline_utc'], max_attempts=1,
            initial_incumbent={'candidate_id':'market','candidate_sha256':INCUMBENT,
                'scorecard_sha256':'b'*64,'review_sha256':'c'*64}, active_pool_capacity=2,
            scheduling_policy='final-singleton-v1', initial_archived_parents=[archive])
        batch.record_micro_evolution('initialize',micro.config(),expected_state_sha256=batch.snapshot()['state_sha256'])
        runner='research/market_rsi/experiments/nfl_ingame_synthetic.py'
        path=self.repo/runner; path.parent.mkdir(parents=True,exist_ok=True); path.write_text('# synthetic fixture\n')
        memory=self.root/'native-memory.json'; t.c.save(memory,{'synthetic':True})
        req={'attempt_id':'synthetic-a','candidate_id':response['candidate']['candidate_id'],
            'module':'experiments.nfl_ingame_synthetic','source_commit':'synthetic-commit',
            'files':{runner:w.sha(path)},'python':str(self.h.f.python),'python_sha256':w.sha(self.h.f.python),
            'memory':str(memory),'memory_sha256':w.sha(memory),'runtime_pair_sha256':micro_pair_hash(batch.snapshot()['micro_evolution']),
            'spec_sha256':'e'*64,'max_fits':4,'max_wall_seconds':10}
        selection=batch_tests.ContinuousDiscoveryBatchTests().pool_member('synthetic-a',parent=PARENT,allocation='exploration')
        selection.update(candidate_id=req['candidate_id'],controller_decision_sha256=t.c._digest(response))
        for name,obj in (('ready_request.json',req),('selection.json',selection)):
            t.c.save(native/name,obj)
        review=self.root/'execution-review.json'
        t.c.save(review,{'passed':True,'authorization_sha256':self.h.authorization_binding['sha256'],
            'request_sha256':w.sha(native/'ready_request.json'),'execution_source_sha256':w.sha(r.__file__)})
        return batch,req,{'outputs':{'controller':{'decision':response},'implement':{'native_name':'native'},
                                     'source_review':{'review':r.pin(review)}}}

    def test_actual_native_worker_shared_reservation_completion_no_retry(self):
        batch,req,ctx=self.native()
        def child(*args,**kwargs):
            out=batch.root/'runs'/req['attempt_id']; out.mkdir()
            manifest={'complete':True,'model_fits':4}
            for n in ('pre_score_lock','input_receipts','exclusions','predictions','scorecard'):
                p=out/(n+('.csv' if n=='predictions' else '.json')); p.write_text('{}')
                manifest[n+'_sha256']=w.sha(p)
            t.c.save(out/'manifest.json',manifest)
            t.c.save(out/'fit_progress.json',{'fit_calls_entered':4,'fit_calls_completed':4})
            return Mock(pid=1234,wait=Mock(return_value=0),poll=Mock(return_value=0))
        with patch.object(r,'ContinuousDiscoveryBatch',return_value=batch),\
             patch.object(w.subprocess,'check_output',return_value='synthetic-commit\n'),\
             patch.object(w,'sample_rss',return_value=128),\
             patch.object(w.subprocess,'Popen',side_effect=child) as launch:
            output=self.runtime.execute(ctx)
            self.assertEqual(output['receipt']['outcome'],'succeeded')
            self.assertEqual(launch.call_count,1)
            with self.assertRaises(RuntimeError):self.runtime.execute(ctx)
            self.assertEqual(launch.call_count,1)
        row=t._file(self.root/'ledger.json')['attempts'][0]
        self.assertEqual(row['actual_fits'],4); self.assertEqual(row['fits_reserved'],4)
        self.assertEqual(batch.snapshot()['attempts_claimed'],1)


if __name__ == '__main__': main()
