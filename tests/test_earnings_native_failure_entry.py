"""Forecast entry's claim/owner/failure handoff; no transport or code execution."""
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import earnings_open_author_followthrough as flow
from edgar_forecast_budget import BudgetStop
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
import test_earnings_capacity_adapter as native_fixture


class NativeFailureEntryTests(unittest.TestCase):
    def run_fixture(self, *, error=None, proof_error=None, enter_error=None, exit_error=None, diagnostic_error=False):
        native=native_fixture.EarningsCapacityTests('test_earnings_reject_keeps_parent_and_history')
        native.setUp(); self.addCleanup(native.doCleanups)
        before,after=native.propose('R')
        batch=native.batch; home=native.root; root=home/'forecast-entry'
        source="PROGRAM={'axis':'R'}\ndef run(p): return {}\n"  # Never executed.
        binding=engine.save(home/'runtime-entry.json',{'id':'synthetic-forecast26','root':str(root),
            'source_commit':'c'*40,'ledger':str(home/'unused-owned.sqlite3'),
            'cutoff_utc':'2099-01-01T00:00:00Z','deadline_utc':'2099-01-01T00:01:00Z',
            'slots':{'forecast':[str(root/'roles/forecast-01')]}})
        runtime=engine.read(binding)
        original=engine.save(home/'invented-author-original.json',{'synthetic':True})
        spec=engine.save(home/'invented-spec.json',{'after':after,'proposal':{'synthetic':True},
            'entrypoints':native.entry,'static_review':{'synthetic':True}})
        candidate_source=home/'inert-candidate.py'; candidate_source.write_text(source)
        value={'stage':'forecast','runtime':binding,'author_result':original,'candidate_specification':spec,
            'candidate_review':engine.save(home/'invented-candidate-review.json',{'synthetic':True}),
            'candidate_git_source':engine.pin(candidate_source),'grant':engine.save(home/'invented-grant.json',
                {'scorer':{'synthetic':True},'qa':{'synthetic':True}}),
            'study':{'synthetic':'study'},'forecast_transport':{'synthetic':'transport'}}
        prepared=engine.save(home/'prepared-entry.json',value); review={'synthetic':'prepared-review'}
        capacity=SimpleNamespace(batch=batch,source_root=home,propose=mock.Mock())
        state={'owner_open':False,'owner_closed':False,'events':[],'helper_args':[],
            'before':batch.snapshot(),'runtime':runtime,'prepared':prepared,'root':root}
        state_api=mock.Mock(); state_api.empty.return_value={'synthetic':'empty'}
        state_api.save.side_effect=lambda path,value:engine.save(path.with_suffix('.json'),value)
        task=mock.Mock(); task.shadow_execution.return_value={'synthetic':'verified forecast'}
        output=engine.save(home/'invented-forecast-output.json',{'synthetic':True})
        def forecast(worker,slot):
            self.assertTrue(state['owner_open']); self.assertFalse(state['owner_closed'])
            self.assertEqual(slot,runtime['slots']['forecast'][0])
            self.assertEqual(batch.snapshot()['active_attempt_ids'],['candidate-'+digest(prepared)])
            state['events'].append('forecast')
            if error is not None:raise error
            return output
        @contextmanager
        def owner(bound,**kwargs):
            self.assertEqual(bound,binding)
            if enter_error is not None:raise enter_error
            state['owner_open']=True; state['events'].append('owner-enter')
            try:yield {'roles':{'forecast':forecast}}
            finally:
                state['owner_open']=False; state['owner_closed']=True; state['events'].append('owner-closed')
                if exit_error is not None:raise exit_error
        def close(batch_arg,**kwargs):
            self.assertIs(batch_arg,batch); self.assertTrue(state['owner_closed']); self.assertFalse(state['owner_open'])
            state['events'].append('close-failure'); state['helper_args'].append(kwargs)
            self.assertEqual(kwargs,{'runtime_binding':binding,'work_id':'candidate-'+digest(prepared),
                'pair_sha256':digest(state['before']['micro_evolution']['active_pair']),
                'output_root':root/'native-failure','error_type':type(error if error is not None else exit_error).__name__})
            if proof_error is not None:raise proof_error
            snapshot=batch.snapshot()
            batch.record_capacity_work('fail',work_id=kwargs['work_id'],pair_sha256=kwargs['pair_sha256'],
                evidence_sha256='f'*64,expected_state_sha256=snapshot['state_sha256'])
            directory=root/'native-failure'; directory.mkdir()
            return engine.save(directory/'result.json',{'synthetic':'entry handoff, not helper verification'})
        terminal=engine.save(home/'invented-owner-terminal.json',{'synthetic':True})
        state.update(task=task,capacity=capacity)
        caught,result=None,None
        original_save=engine.save
        with ExitStack() as stack:
            for name,returned in (('validate_prepared',(value,runtime)),('candidate_gate',({'source_text':source},
                    {'source_sha256':engine.pin(candidate_source)['sha256']})),('authority',{'requires_cold_probe':False}),
                    ('capture_or_load',({},'synthetic-clock')),('native',capacity),('containers_remaining',80),('owner_terminal',terminal)):
                stack.enter_context(mock.patch.object(flow,name,return_value=returned))
            stack.enter_context(mock.patch.object(flow.original_capacity,'task',return_value=({'synthetic':'company'},None)))
            stack.enter_context(mock.patch.object(flow,'ResearchState',return_value=state_api))
            stack.enter_context(mock.patch.object(flow,'OpenTask',return_value=task))
            stack.enter_context(mock.patch.object(flow,'DockerRunner',return_value=object()))
            stack.enter_context(mock.patch.object(flow,'ProgramWorker',return_value=object()))
            stack.enter_context(mock.patch.object(flow.assembly,'followthrough_factories',return_value={}))
            stack.enter_context(mock.patch.object(flow,'open_capacity_runtime',side_effect=owner))
            handler=stack.enter_context(mock.patch('earnings_native_failure.close_failed_work',side_effect=close))
            if hasattr(flow,'close_failed_work'):
                stack.enter_context(mock.patch.object(flow,'close_failed_work',handler))
            if diagnostic_error:
                def save(path,value):
                    if Path(path).name=='native-failure-unclosed.json':raise OSError('Invented diagnostic storage failure')
                    return original_save(path,value)
                stack.enter_context(mock.patch.object(flow.engine,'save',side_effect=save))
            try:result=flow.run_forecast(prepared,review)
            except BaseException as failure:caught=failure
        state.update(caught=caught,result=result,handler=handler,after=batch.snapshot())
        return state

    def test_BudgetStop_closes_only_after_owner_and_rethrows_original_not_success(self):
        error=BudgetStop('Invented budget cutoff'); state=self.run_fixture(error=error)
        self.assertIs(state['caught'],error); self.assertIsNone(state['result'])
        self.assertEqual(state['events'],['owner-enter','forecast','owner-closed','close-failure'])
        self.assertEqual(state['handler'].call_count,1)
        self.assertEqual(state['after']['capacity_work'][-1]['status'],'failed')
        self.assertEqual(state['after']['active_attempt_ids'],[])
        self.assertEqual(state['after']['micro_evolution'],state['before']['micro_evolution'])
        self.assertFalse((state['root']/'followthrough-result.json').exists())
        state['task'].shadow_execution.assert_not_called()

    def test_ordinary_failure_original_preserved_when_cleanup_or_fee_proof_refuses(self):
        error=RuntimeError('Invented original forecast failure')
        state=self.run_fixture(error=error,proof_error=ValueError('Invented uncertain cleanup'))
        self.assertIs(state['caught'],error); self.assertIsNone(state['result'])
        self.assertEqual(state['events'][-2:],['owner-closed','close-failure'])
        self.assertEqual(state['after']['capacity_work'][-1]['status'],'claimed')
        self.assertEqual(state['after']['active_attempt_ids'],['candidate-'+digest(state['prepared'])])
        self.assertEqual(state['after']['micro_evolution'],state['before']['micro_evolution'])
        self.assertFalse((state['root']/'followthrough-result.json').exists())
        diagnostic=engine.read(engine.pin(state['root']/'native-failure-unclosed.json'))
        self.assertEqual(diagnostic['original_error_type'],'RuntimeError')
        self.assertEqual(diagnostic['closure_error_type'],'ValueError'); self.assertFalse(diagnostic['retry_allowed'])

    def test_unknown_crash_with_missing_proof_remains_claimed_and_original_propagates(self):
        crash=SystemExit('Invented crash without terminal proof')
        state=self.run_fixture(error=crash,proof_error=ValueError('No closed owner proof'))
        self.assertIs(state['caught'],crash)
        self.assertEqual(state['after']['capacity_work'][-1]['status'],'claimed')
        self.assertTrue(state['owner_closed']); self.assertFalse(state['owner_open'])
        self.assertFalse((state['root']/'followthrough-result.json').exists())

    def test_diagnostic_write_failure_never_masks_original_forecast_exception(self):
        error=RuntimeError('Invented original research failure')
        state=self.run_fixture(error=error,proof_error=ValueError('No exact cleanup proof'),diagnostic_error=True)
        self.assertIs(state['caught'],error); self.assertIsNone(state['result'])
        self.assertEqual(state['after']['capacity_work'][-1]['status'],'claimed')
        self.assertFalse((state['root']/'followthrough-result.json').exists())
        self.assertTrue(getattr(error,'__notes__',[]))

    def test_owner_entry_failure_never_closes_unclaimed_work(self):
        error=RuntimeError('Invented owner entry rejection'); state=self.run_fixture(enter_error=error)
        self.assertIs(state['caught'],error); state['handler'].assert_not_called()
        self.assertNotIn('capacity_work',state['after'])
        self.assertFalse(state['owner_open']); state['task'].shadow_execution.assert_not_called()

    def test_owner_exit_failure_after_verified_output_never_gets_premature_success_credit(self):
        error=RuntimeError('Invented owner final guard failure')
        state=self.run_fixture(exit_error=error)
        self.assertIs(state['caught'],error); self.assertIsNone(state['result'])
        self.assertEqual(state['events'],['owner-enter','forecast','owner-closed','close-failure'])
        self.assertEqual(state['after']['capacity_work'][-1]['status'],'failed')
        self.assertNotIn('output_evidence_sha256',state['after']['capacity_work'][-1])
        state['task'].shadow_execution.assert_called_once()
        self.assertFalse((state['root']/'followthrough-result.json').exists())

    def test_success_completes_original_work_without_failure_helper_or_adoption(self):
        state=self.run_fixture(); self.assertIsNone(state['caught'])
        state['handler'].assert_not_called(); self.assertEqual(state['events'],['owner-enter','forecast','owner-closed'])
        self.assertEqual(state['after']['capacity_work'][-1]['status'],'completed')
        self.assertNotIn('failure_evidence_sha256',state['after']['capacity_work'][-1])
        self.assertEqual(state['after']['active_attempt_ids'],[])
        self.assertEqual(state['after']['micro_evolution'],state['before']['micro_evolution'])
        state['task'].shadow_execution.assert_called_once()
        self.assertFalse(engine.read(state['result'])['candidate_adopted'])


if __name__=='__main__':unittest.main()
