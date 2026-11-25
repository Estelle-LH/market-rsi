"""Program shadow/cold Native plumbing with invented HTTP and runner outputs."""
from copy import deepcopy
from types import MethodType
import unittest

from earnings_capacity_checks import MechanicalProbes
from earnings_open_worker import ProgramWorker
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_shadow_trial as trial_fixture
import test_earnings_open_worker as program_fixture


class OpenTrialTests(unittest.TestCase):
    def test_program_shadow_forecasts_and_eight_real_mechanical_probes(self):
        programs=program_fixture.ProgramWorkerTests()
        programs.setUp();self.addCleanup(programs.doCleanups)
        pending=programs.pending_H()
        trials=trial_fixture.MatchedShadowTrialTests()
        self.addCleanup(trials.doCleanups)
        fixture=trials.fixture()
        fixture.native=programs.native
        fixture.capacity=programs.native.capacity
        snapshot=fixture.native.batch.snapshot()
        fixture.active=digest(snapshot['micro_evolution']['active_pair'])
        fixture.token=pending
        fixture.tested=digest(snapshot['micro_evolution']['pending']['pair'])
        constructed=[]
        def make_worker(task, task_id, capacity, pair, root, state, **kwargs):
            worker=ProgramWorker(task.company,task_id,capacity,pair,root,state,
                runner=programs.runner,**kwargs)
            constructed.append(worker)
            return worker
        fixture.task.make_worker=MethodType(make_worker,fixture.task)
        fixture.task.worker_type=ProgramWorker
        before=deepcopy(fixture.native.batch.snapshot()['micro_evolution'])
        measured=trials.invoke(fixture)
        self.assertTrue(engine.read(engine.read(measured)['trial_claim'])['sources']['worker']['path'].endswith('earnings_open_worker.py'))
        self.assertEqual(len(constructed),2)
        self.assertEqual(constructed[0].tested_pair,fixture.active)
        self.assertEqual(constructed[1].tested_pair,fixture.tested)
        probe=MechanicalProbes(fixture.task).run(fixture.capacity,measured,fixture.role_root/'effects'/'program-probe')
        proof=engine.read(probe)
        self.assertEqual(len(proof['observations']),8)
        for name,value in proof['observations'].items():
            self.assertTrue(all(value['facts'].values()),name)
        self.assertEqual(len(constructed),3)
        self.assertNotEqual(constructed[1].r_execution['receipt'],constructed[2].r_execution['receipt'])
        self.assertEqual(constructed[1].context,constructed[2].context)
        self.assertEqual(fixture.native.batch.snapshot()['micro_evolution'],before)
        self.assertEqual(programs.runner.calls,3)


if __name__=='__main__':unittest.main()
