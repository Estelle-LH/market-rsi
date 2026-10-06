"""Actual version activation drives next loop callbacks; all science is synthetic."""
from pathlib import Path
from unittest import TestCase, main

from market_rsi import digest
from supervisor_harness import feedback_linked_loop as loop
from supervisor_harness import research_capacity_activation as activation
from supervisor_harness import test_research_capacity_activation as fixtures
from supervisor_harness import account_controller_feedback_consumer as c


class CapacityFeedbackIntegrationTests(TestCase):
    def setUp(self):
        self.f = fixtures.CapacityActivationTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def test_negative_feedback_activates_R_then_H_and_changes_next_callback(self):
        f = self.f
        observed, changes = [], []

        def selected():
            return digest(f.batch.snapshot()['micro_evolution']['active_pair'])

        def prepare(ctx):
            # The callback implementation is frozen; selected reviewed policy
            # versions are state, not silently replaced callback source.
            R = f.adapter.resolve('R', expected_pair_sha256=selected())
            H = f.adapter.resolve('H', expected_pair_sha256=selected())
            previous = ctx['previous_result']
            feedback = H.deliver(previous['feedback'])
            choice = R.choose(previous['history'])
            return {'choice':choice, 'feedback':feedback, 'pair':selected(),
                    'prior_observation_sha256':ctx['previous_feedback_sha256']}

        def controller(ctx):
            packet = ctx['outputs']['input']
            if ctx['round_index'] == 2:
                self.assertEqual(packet['feedback']['parent_id'], 'a')
                self.assertEqual(packet['feedback']['cause'], 'negative_prediction')
                self.assertEqual(packet['prior_observation_sha256'], digest(observed[0]))
            return {'candidate':packet['choice'], 'proposer':'synthetic-policy-fixture',
                    'real_Controller_decisions':0}

        def execute(ctx):
            candidate = ctx['outputs']['controller']['candidate']
            predictions = [.2,.8] if candidate == 'a' else [.8,.2]
            return {'candidate':candidate, 'predictions':predictions, 'labels':[1,0],
                    'synthetic':True, 'real_Train_fits':0}

        def review(ctx):
            result = ctx['outputs']['execute']
            score = sum((p-y)**2 for p,y in zip(result['predictions'],result['labels'])) / 2
            return {**result, 'score':score, 'valid':True}

        def reconcile(ctx):
            result = ctx['outputs']['result_review']
            feedback = {'score':result['score'], 'parent_id':result['candidate'],
                        'cause':'negative_prediction' if result['score'] > .5 else 'improved_fixture'}
            if ctx['round_index'] == 1:
                # Two separately attributed native proposals, each independently
                # reviewed using actual matched synthetic before/after behavior.
                # No autonomous LLM authorship or scientific effectiveness claim.
                before, after_R = f.propose('R')
                receipt = f.review_receipt(before, after_R)
                f.adapter.review(receipt, expected_state_sha256=f.batch.snapshot()['state_sha256'])
                changes.append({'axis':'R','reason':feedback['cause'], 'before':activation.pair(before),
                                'after':activation.pair(after_R), 'review':receipt})
                before, after_H = f.propose('H', after_R)
                receipt = f.review_receipt(before, after_H)
                f.adapter.review(receipt, expected_state_sha256=f.batch.snapshot()['state_sha256'])
                changes.append({'axis':'H','reason':'matched causal-feedback loss',
                                'before':activation.pair(before),'after':activation.pair(after_H),
                                'review':receipt})
                # Restore the real adapter from unchanged immutable registry and
                # journal before the next callback, rather than reuse old modules.
                f.adapter = f.restore()
            output = {'history':ctx['previous_result']['history']+[result['candidate']],
                      'feedback':feedback, 'selected_pair':selected(),
                      'changes':list(changes), 'synthetic':True, 'real_Train_fits':0}
            observed.append(output)
            return output

        handlers = {'input':prepare, 'controller':controller,
            'implement':lambda ctx:dict(ctx['outputs']['controller']),
            'source_review':lambda ctx:{'synthetic_trusted_fixture':True},
            'execute':execute, 'result_review':review, 'reconcile':reconcile}
        sources = [Path(loop.__file__),Path(activation.__file__),Path(__file__)]
        identity = lambda:{stage:{'sources':[{'path':str(p.resolve()),'sha256':c.sha(p)} for p in sources],
            'registered_policy_sources':{name:fixtures.sha(text) for name,text in f.files.items()}}
            for stage in loop.STAGES}
        seed = {'history':[], 'feedback':{'score':None,'parent_id':'seed','cause':'initial'}}
        result = loop.run(f.root/'loop',handlers,seed=seed,admit=lambda ctx:True,
                          max_rounds=2,handler_identity=identity)
        self.assertEqual(result['completed_rounds'],2)
        self.assertEqual([x['history'][-1] for x in observed],['a','b'])
        self.assertGreater(observed[0]['feedback']['score'],observed[1]['feedback']['score'])
        self.assertEqual(changes[0]['before']['harness_sha256'],changes[0]['after']['harness_sha256'])
        self.assertEqual(changes[1]['before']['researcher_sha256'],changes[1]['after']['researcher_sha256'])
        self.assertEqual(len(f.batch.snapshot()['micro_evolution']['history']),2)
        replay = loop.run(f.root/'loop',handlers,seed=seed,admit=lambda ctx:False,
                          max_rounds=2,handler_identity=identity)
        self.assertEqual(replay,result)
        self.assertEqual(len(observed),2)


if __name__ == '__main__': main()
