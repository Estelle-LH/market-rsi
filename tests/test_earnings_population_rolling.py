"""Real local spawn/Pipe/SQLite; synthetic scores, NO API/Native/scorer/data.

Existing grant fixture seams remain explicit: historical prefix/Git proof mocked,
but original reservation/settlement/liability arithmetic and real OS exits run.
"""
from copy import deepcopy
import fcntl
import json
import multiprocessing as mp
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import earnings_population_company_batch as batch
from edgar_forecast_budget import BudgetStop
from test_earnings_population_model_budget import Fixture, G
from supervisor_harness import capacity_feedback_engine as engine


def deny_network(event,args):
    if event in ('socket.connect','socket.bind'):raise AssertionError('OFFLINE: network forbidden')

sys.addaudithook(deny_network)

def synthetic_worker(connection,company,request_id,barrier,seconds,tail,mode,root,amount=G):
    sys.addaudithook(deny_network)
    proxy=batch.BudgetProxy(connection);error=None;row=None
    started=time.monotonic()
    try:
        proxy.reserve(request_id,'gpt-6.1-sol',amount)
        if barrier is not None:barrier.wait(timeout=15)
        time.sleep(seconds)
        if mode=='eof':connection.close();return
        if mode=='direct_failure':raise RuntimeError('known failed done without settlement')
        if mode=='uncertain':proxy.uncertain(request_id);raise RuntimeError('synthetic uncertain fee')
        if mode=='cross':
            try:proxy.settle('not-my-request',1)
            finally:proxy.settle(request_id,1)
        elif mode!='unsettled':proxy.settle(request_id,1)
        if mode=='fail':raise RuntimeError('synthetic forecast failure')
        row=dict(synthetic=True,company_id=company,pid=os.getpid(),start=started,end=time.monotonic())
    except BaseException as caught:error=type(caught).__name__
    checkpoint=engine.save(Path(root)/'companies'/(company+'.json'),dict(
        company_id=company,status='COMPLETED_SCORED' if error is None else 'FAILED_NO_RETRY',
        worker_pid=os.getpid(),result=row,synthetic=True,error_type=error))
    connection.send(dict(kind='done',error_type=error,result=row,checkpoint=checkpoint));connection.close()
    time.sleep(tail)  # done is deliberately sent BEFORE the process actually exits.
    if mode=='post_done_exit':os._exit(7)


class RollingTests(unittest.TestCase):
    def setUp(self):
        self.f=Fixture();self.addCleanup(self.f.close);self.f.activate()
        self.budget=self.f.budget(optin=True);self.addCleanup(self.budget.close)
        self.root=self.f.root/'rolling';self.root.mkdir();(self.root/'companies').mkdir()
        self.companies=[f'CIK{i:010d}' for i in range(1,6)]
        self.value=dict(clean_slate_policy='round0_clean_slate_v1',clean_company_concurrency=batch.ROLLING,
            companies=self.companies,root=str(self.root),rates=dict(api_model='gpt-6.1-sol'),
            slots=dict(forecast=[str(self.root/'roles'/f'forecast-01-{i:02d}') for i in range(5)]))
        self.binding=dict(path=str(self.root/'runtime.json'),sha256='a'*64)
        self.store=batch.OwnedReservations(self.budget,self.binding,self.value)
        self.jobs=[];self.checked=[];self.guard_calls=0

    def resize_queue(self,n):
        self.companies=[f'CIK{i:010d}' for i in range(1,n+1)]
        self.value['companies']=self.companies
        self.value['slots']['forecast']=[str(self.root/'roles'/f'forecast-01-{i:02d}') for i in range(n)]
        self.store.value=deepcopy(self.value)
        self.store.slots=dict(zip(self.companies,self.value['slots']['forecast']))

    def execute(self,*,mode='ok',tail=.05,verify_failure=False,guard_failure=False,spawn_failure=False,event_failure=False,
                late_failure=False,mechanical_failure=False,late_exit_failure=False,admission_delay=False):
        context=mp.get_context('spawn');initial=min(batch.concurrency_limit(self.value),len(self.companies));barrier=context.Barrier(initial)
        def factory(company,slot):
            i=self.companies.index(company)
            if spawn_failure and i==4:raise OSError('synthetic fifth spawn failure')
            parent,child=context.Pipe()
            seconds=.005 if late_exit_failure and i==1 else (.02 if i in (0,4) or len(self.companies)>5 else .7)
            if mechanical_failure and i>0:seconds=.7  # Inject before any sibling can release capacity.
            own_tail=.5 if late_exit_failure and i==1 else (tail if i==0 else 0)
            own_mode=mode if i==0 else ('post_done_exit' if late_exit_failure and i==1 else (
                'direct_failure' if (late_failure or admission_delay) and i==1 else 'ok'))
            process=context.Process(target=synthetic_worker,args=(child,company,'request-'+str(i),
                barrier if i<initial else None,seconds,own_tail,own_mode,str(self.root),getattr(self,'amount',G)))
            job=dict(company=company,slot=slot,process=process,connection=parent,child=child,done=None)
            self.jobs.append(job);return job
        def verify(job):
            self.assertFalse(job['process'].is_alive());self.assertEqual(job['process'].exitcode,0)
            saved=engine.read(job['done']['checkpoint'])
            self.assertEqual(saved['status'],'COMPLETED_SCORED');self.assertTrue(saved['synthetic'])
            self.assertEqual(saved['worker_pid'],job['process'].pid)
            if verify_failure and job['company']==self.companies[0]:raise ValueError('synthetic Native/cleanup or scored-checkpoint rejection')
            if (late_failure or late_exit_failure) and job['company']==self.companies[0]:time.sleep(.9)
            self.checked.append(job['company'])
            return engine.save(self.root/'companies'/(job['company']+'-closed.json'),
                dict(synthetic=True,checkpoint=job['done']['checkpoint'],fees=self.store.settled_company(job['company'])))
        def guard():
            self.guard_calls+=1
            if guard_failure and self.checked:raise BudgetStop('synthetic current clock/source rejection')
            if admission_delay and self.checked:time.sleep(.9)
        original=engine.save
        def save(path,value):
            if event_failure and value.get('kind')=='closed':raise OSError('synthetic event write failure')
            if mechanical_failure and value.get('kind')=='dispatch' and value['company_id']==self.companies[0]:
                # Patch only AFTER spawn. A local method attached before start is
                # unpicklable and tests admission, not parent-control drainage.
                process=self.jobs[0]['process'];join=process.join;failed=[False]
                def injected_join(*args,**kwargs):
                    if not failed[0]:failed[0]=True;raise RuntimeError('synthetic parent control failure')
                    return join(*args,**kwargs)
                process.join=injected_join
            return original(path,value)
        with (self.f.root/'one-owner.lock').open('w+b') as lock,patch.object(engine,'save',save):
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with (self.f.root/'one-owner.lock').open('rb') as second:
                with self.assertRaises(BlockingIOError):fcntl.flock(second,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.output=batch.serve_rolling(self.store,list(self.store.slots.items()),factory,verify,guard)
            self.assertTrue(all(not j['process'].is_alive() for j in self.jobs))
        evidence=os.environ.get('EDGAR_ROLLING_EVIDENCE_DIR')
        if evidence:
            Path(evidence).mkdir(parents=True,exist_ok=True)
            engine.save(Path(evidence)/(self._testMethodName+'.json'),dict(test=self.id(),synthetic=True,
                production_api_calls=0,production_ledger_writes=0,owner_pid=os.getpid(),
                events=self.output[2],errors=self.output[3],not_measured=self.output[4],
                workers=self.output[1],checked=self.checked,ledger=self.f.snapshot()))
        return self.output

    def assert_stopped(self,result):
        self.assertTrue(result[3]);self.assertEqual(result[4],[self.companies[4]])
        self.assertEqual(len(self.jobs),4)
        self.assertTrue(all(not j['process'].is_alive() for j in self.jobs))
        with self.assertRaises(ValueError):batch.verify_rolling_events(self.companies,result[2])

    def test_fifth_refills_after_true_exit_fees_and_close_before_slow_siblings(self):
        rows,workers,events,errors,unstarted=self.execute(tail=.2)
        self.assertEqual((errors,unstarted),([],[]));batch.verify_rolling_events(self.companies,events)
        self.assertEqual([r['company_id'] for r in rows],self.companies)
        first=self.companies[0];fifth=self.companies[4]
        instant=lambda kind,c:next(e['monotonic'] for e in events if e['kind']==kind and e['company_id']==c)
        self.assertLess(instant('worker_done',first),instant('process_exit',first))
        self.assertGreaterEqual(instant('process_exit',first)-instant('worker_done',first),.15)
        self.assertLess(instant('closed',first),instant('dispatch',fifth))
        self.assertLess(instant('dispatch',fifth),instant('process_exit',self.companies[1]))
        self.assertEqual(max(e['active_count'] for e in events if e['kind']=='dispatch'),4)
        self.assertEqual(len(workers),5);self.assertEqual(self.budget.db.execute("SELECT COUNT(*) FROM requests WHERE status!='settled'").fetchone()[0],0)
        changed=deepcopy(events);changed[0]['active_count']=8
        with self.assertRaises(ValueError):batch.verify_rolling_events(self.companies,changed)
        print(json.dumps(dict(test='ACTUAL_SYNTHETIC_ROLLING_NOT_MODEL',done_to_true_exit_seconds=instant('process_exit',first)-instant('worker_done',first),
            close_to_refill_seconds=instant('dispatch',fifth)-instant('closed',first),peak_processes=4,
            fifth_started_before_slow_sibling_exit=True,production_api_calls=0)))

    def test_done_then_nonzero_exit_blocks_refill(self):self.assert_stopped(self.execute(mode='post_done_exit'))
    def test_unsettled_company_keeps_full_liability_and_blocks_refill(self):
        self.assert_stopped(self.execute(mode='unsettled'))
        self.assertEqual(self.budget.db.execute("SELECT reserved,status FROM requests WHERE id='request-0'").fetchone(),(G,'reserved'))
    def test_uncertain_stops_refill_but_other_started_fees_still_settle(self):
        self.assert_stopped(self.execute(mode='uncertain'))
        self.assertEqual(self.budget.db.execute("SELECT COUNT(*) FROM requests WHERE status='settled' AND id LIKE 'request-%'").fetchone()[0],3)
        self.assertEqual(self.budget.db.execute("SELECT reserved,status FROM requests WHERE id='request-0'").fetchone(),(G,'uncertain'))
    def test_cross_company_rpc_error_latches_stop_and_drains(self):self.assert_stopped(self.execute(mode='cross'))
    def test_missing_done_checkpoint_eof_stops_and_drains(self):self.assert_stopped(self.execute(mode='eof'))
    def test_forecast_error_stops_new_dispatch(self):self.assert_stopped(self.execute(mode='fail'))
    def test_closure_native_cleanup_or_checkpoint_failure_stops(self):self.assert_stopped(self.execute(verify_failure=True))
    def test_current_input_or_clock_guard_failure_stops(self):self.assert_stopped(self.execute(guard_failure=True))
    def test_spawn_failure_drains_without_retry(self):self.assert_stopped(self.execute(spawn_failure=True))
    def test_event_write_failure_drains_without_dispatching_fifth(self):self.assert_stopped(self.execute(event_failure=True))
    def test_failure_queued_during_close_is_processed_before_refill(self):self.assert_stopped(self.execute(late_failure=True))
    def test_done_sibling_later_nonzero_exit_during_other_close_blocks_refill(self):
        self.assert_stopped(self.execute(late_exit_failure=True))
    def test_failure_arriving_during_admission_guard_is_processed_before_spawn(self):
        self.assert_stopped(self.execute(admission_delay=True))
    def test_unexpected_parent_control_error_drains_started_processes(self):
        with self.assertRaisesRegex(RuntimeError,'parent control failure'):self.execute(mechanical_failure=True)
        self.assertEqual(len(self.jobs),4)
        self.assertTrue(all(not j['process'].is_alive() for j in self.jobs))
        self.assertEqual(self.budget.db.execute("SELECT COUNT(*) FROM requests WHERE status='settled' AND id LIKE 'request-%'").fetchone()[0],4)
        failed=engine.read(engine.pin(self.root/'company-batch-execution.json'))
        self.assertEqual(failed['parent_control_error'],'RuntimeError')
        self.assertEqual(len(failed['completed_results']),4)
        self.assertEqual(failed['not_measured'],[self.companies[4]])
        self.assertEqual([w['true_exit_code'] for w in failed['workers']],[0]*4)

    def test_singleton_rolling_queue(self):
        self.resize_queue(1)
        rows,workers,events,errors,unstarted=self.execute()
        self.assertEqual((errors,unstarted),([],[]));self.assertEqual(len(rows),1)
        batch.verify_rolling_events(self.companies,events,workers)

    def test_full25_logical_slots_keep_four_process_ceiling(self):
        self.resize_queue(25)
        rows,workers,events,errors,unstarted=self.execute(tail=0)
        self.assertEqual((errors,unstarted),([],[]));self.assertEqual(len(rows),25)
        self.assertEqual([r['company_id'] for r in rows],self.companies)
        self.assertEqual(max(e['active_count'] for e in events if e['kind']=='dispatch'),4)
        batch.verify_rolling_events(self.companies,events,workers)

    def test_persistent_events_missing_tamper_pid_or_closure_are_rejected(self):
        self.resize_queue(1)
        _,workers,events,errors,_=self.execute()
        saved=dict(events=events,workers=workers)
        batch._rolling_event_evidence(self.root,self.value,saved)
        path=self.root/'rolling-events'/'0000.json';original=path.read_bytes()
        path.unlink()
        with self.assertRaisesRegex(ValueError,'Missing/extra'):batch._rolling_event_evidence(self.root,self.value,saved)
        path.write_bytes(original+b' ')
        # Exact JSON formatting is pinned by each evidence consumer; semantic
        # event identity must also agree with the batch's immutable saved list.
        tampered=json.loads(original);tampered['pid']+=1;path.write_text(json.dumps(tampered))
        with self.assertRaisesRegex(ValueError,'Persistent'):batch._rolling_event_evidence(self.root,self.value,saved)
        path.write_bytes(original)
        for field,replacement in (('pid',-1),('closure',dict(path='wrong',sha256='0'*64))):
            wrong=deepcopy(workers);wrong[0][field]=replacement
            with self.assertRaises(ValueError):batch.verify_rolling_events(self.companies,events,wrong)

    def test_slot_ceiling_is_prospective_rolling_only(self):
        from earnings_population_runtime import _slot_ceiling
        self.assertEqual(_slot_ceiling(self.value,'forecast',True),25)
        self.assertEqual(_slot_ceiling(self.value,'author',True),3)
        self.assertEqual(_slot_ceiling(self.value,'forecast',False),6)
        old=deepcopy(self.value);old.pop('clean_company_concurrency')
        self.assertEqual(_slot_ceiling(old,'forecast',True),6)

    def test_cleanup_declared_fifth_slot_not_active_sibling_or_unknown(self):
        from earnings_native_failure import _cleanup
        active=self.root/'code'/'forecast-01-00'/'call-broken-active';active.mkdir(parents=True)
        own=self.root/'code'/'forecast-01-04';own.mkdir()
        self.assertEqual(_cleanup(self.root,runtime=self.value,selected_slot=own.name),[])
        with self.assertRaises(ValueError):_cleanup(self.root)
        (self.root/'code'/'forecast-01-25').mkdir()
        with self.assertRaises(ValueError):_cleanup(self.root,runtime=self.value,selected_slot=own.name)

    def test_production_closure_rejects_other_role_or_slot_before_native(self):
        company=self.companies[0];slot=self.value['slots']['forecast'][0];candidate=dict(id='f'*64)
        result=dict(version_id=candidate['id'],points=1)
        checkpoint=engine.save(self.root/'companies'/'wrong-guard.json',dict(runtime=self.binding,company_id=company,
            slot=slot,candidate_id=candidate['id'],worker_pid=123,status='COMPLETED_SCORED',error_type=None,
            result=result,retry_allowed=False))
        directory=self.root/'role-validation';directory.mkdir()
        report=dict(runtime=self.binding,role='author',slot=slot,selected_version_id=candidate['id'],entry_full_audit='PASS',
            exit_full_audit='PASS',exit_current_guard='PASS',output_accepted=True)
        engine.save(directory/(Path(slot).name+'.json'),report)
        job=dict(slot=slot,company=company,process=SimpleNamespace(pid=123),done=dict(checkpoint=checkpoint,result=result))
        # Result shape is orthogonal to copied guard rejection; Native/public
        # scorers are intentionally never instantiated by this negative test.
        with patch('earnings_population.validate_result',side_effect=lambda x:x):
            with self.assertRaisesRegex(ValueError,'role guard'):batch._rolling_closed(
                SimpleNamespace(runtime=self.value,binding=self.binding),candidate,job)

    def test_legacy_wave_stays_bounded_and_new_queue_needs_optin(self):
        self.assertTrue(batch.enabled(self.value))
        old=deepcopy(self.value);old['clean_company_concurrency']=batch.POLICY
        with self.assertRaises(ValueError):batch.enabled(old)
        for n in (0,26):
            wrong=deepcopy(self.value);wrong['companies']=['x']*n
            with self.assertRaises(ValueError):batch.enabled(wrong)
        duplicate=list(self.store.slots.items());duplicate[-1]=duplicate[0]
        with self.assertRaises(ValueError):batch.serve_rolling(self.store,duplicate,None,None,None)

    def test_all_pending_and_charged_costs_still_share_original_window(self):
        for i,company in enumerate(self.companies[:4]):self.store.call(company,'reserve',(f'cap-{i}','gpt-6.1-sol',G))
        with self.assertRaises(BudgetStop):self.store.call(self.companies[4],'reserve',('fifth','gpt-6.1-sol',G))
        self.store.call(self.companies[0],'settle',('cap-0',G))
        with self.assertRaises(BudgetStop):self.store.call(self.companies[4],'reserve',('too-large','gpt-6.1-sol',2*G))
        self.assertEqual(self.budget.db.execute('SELECT SUM(charged) FROM requests WHERE id LIKE ?',(r'cap-%',)).fetchone()[0],G)

    def use_eight(self,n=9):
        self.value['clean_company_concurrency']=batch.ROLLING8
        self.resize_queue(n)
        self.amount=G//4  # Same original $5 fixture cap, NOT a larger window.

    def test_eight_real_processes_and_ninth_refill(self):
        self.use_eight()
        rows,workers,events,errors,unstarted=self.execute(tail=.15)
        self.assertEqual((errors,unstarted),([],[]));self.assertEqual(len(rows),9)
        self.assertEqual(max(e['active_count'] for e in events if e['kind']=='dispatch'),8)
        batch.verify_rolling_events(self.companies,events,workers,limit=8)
        with self.assertRaises(ValueError):batch.verify_rolling_events(self.companies,events,workers)
        ninth=next(e for e in events if e['kind']=='dispatch' and e['company_id']==self.companies[8])
        self.assertTrue(any(e['kind']=='closed' and e['monotonic']<ninth['monotonic'] for e in events))
        self.assertTrue(any(e['kind']=='process_exit' and e['company_id'] in self.companies[:8]
            and e['monotonic']>ninth['monotonic'] for e in events))
        batch._rolling_event_evidence(self.root,self.value,dict(events=events,workers=workers))

    def test_full25_eight_ceiling(self):
        self.use_eight(25)
        rows,workers,events,errors,unstarted=self.execute(tail=0)
        self.assertEqual((errors,unstarted),([],[]));self.assertEqual(len(rows),25)
        self.assertEqual([r['company_id'] for r in rows],self.companies)
        self.assertEqual(max(e['active_count'] for e in events if e['kind']=='dispatch'),8)
        batch.verify_rolling_events(self.companies,events,workers,limit=8)

    def test_eight_loans_ninth_blocked_and_same_original_cap(self):
        self.use_eight()
        for i,c in enumerate(self.companies[:8]):self.store.call(c,'reserve',(f'eight-{i}','gpt-6.1-sol',G//2))
        self.store.active()
        with self.assertRaises(BudgetStop):self.store.call(self.companies[8],'reserve',('ninth','gpt-6.1-sol',1))
        self.store.call(self.companies[0],'settle',('eight-0',G//2))
        with self.assertRaises(BudgetStop):self.store.call(self.companies[8],'reserve',('over-cap','gpt-6.1-sol',2*G))
        self.store.call(self.companies[8],'reserve',('fits','gpt-6.1-sol',G//2))
        self.assertEqual(self.budget.additional_cap_nano_usd,5*G)

    def test_eight_error_stops_ninth_and_drains(self):
        self.use_eight()
        rows,workers,events,errors,unstarted=self.execute(mode='fail')
        self.assertTrue(errors);self.assertEqual(unstarted,[self.companies[8]])
        self.assertEqual(len(workers),8)
        self.assertTrue(all(not j['process'].is_alive() for j in self.jobs))

    def test_eight_parent_error_inventory_keeps_policy(self):
        self.use_eight()
        with self.assertRaisesRegex(RuntimeError,'parent control failure'):self.execute(mechanical_failure=True)
        failed=engine.read(engine.pin(self.root/'company-batch-execution.json'))
        self.assertEqual(failed['policy'],batch.ROLLING8);self.assertEqual(failed['max_companies'],8)
        self.assertEqual(failed['not_measured'],[self.companies[8]])
        self.assertTrue(all(not j['process'].is_alive() for j in self.jobs))

    def test_policy_explicit_optin_and_legacy_defaults(self):
        self.assertEqual(batch.preparation_policy(False),batch.POLICY)
        self.assertEqual(batch.preparation_policy(True),batch.ROLLING)
        self.assertEqual(batch.preparation_policy(True,8),batch.ROLLING8)
        self.assertEqual(batch.concurrency_limit(self.value),4)
        for flag,limit in ((False,8),(True,9),(True,True),(True,8.0)):
            with self.assertRaises(ValueError):batch.preparation_policy(flag,limit)
        for limit in (0,9,True,8.0):
            with self.assertRaises(ValueError):batch.verify_rolling_events([],[],limit=limit)
        nine=[dict(sequence=i,kind='dispatch',company_id=c,monotonic=i,pid=i,active_count=i+1)
            for i,c in enumerate(['company'+str(i) for i in range(9)])]
        with self.assertRaisesRegex(ValueError,'exceeds policy'):
            batch.verify_rolling_events([e['company_id'] for e in nine],nine,limit=8)
        wrong=deepcopy(self.value);wrong['clean_company_concurrency']='clean_frozen_company_rolling9_v1'
        with self.assertRaises(ValueError):batch.concurrency_limit(wrong)


if __name__=='__main__':
    started=time.monotonic()
    if '--with-regressions' in sys.argv:
        sys.argv.remove('--with-regressions')
        modules=['__main__.RollingTests',
            'test_earnings_population_company_batch','test_earnings_population_model_budget',
            'test_earnings_population_clean_slate','test_earnings_population_runtime',
            'test_earnings_population_runtime_continued','test_earnings_population_role_validation',
            'test_earnings_native_failure','test_earnings_native_failure_entry',
            'test_earnings_native_failure_population400']
        program=SimpleNamespace(result=unittest.TextTestRunner(verbosity=2 if '-v' in sys.argv else 1).run(
            unittest.defaultTestLoader.loadTestsFromNames(modules)))
    else:program=unittest.main(exit=False)
    evidence=os.environ.get('EDGAR_ROLLING_EVIDENCE_DIR')
    if evidence:
        Path(evidence).mkdir(parents=True,exist_ok=True)
        result=program.result
        engine.save(Path(evidence)/'suite-result.json',dict(schema='rolling_offline_test_result_v1',
            synthetic=True,tests_run=result.testsRun,successful=result.testsRun>0 and result.wasSuccessful(),
            failures=[dict(test=str(t),traceback=s) for t,s in result.failures],
            errors=[dict(test=str(t),traceback=s) for t,s in result.errors],
            skipped=[dict(test=str(t),reason=s) for t,s in result.skipped],
            elapsed_seconds=time.monotonic()-started,python=sys.version,production_api_calls=0,
            production_ledger_writes=0,scope='real spawn/temporary ledger; synthetic model/Native/scorer'))
    sys.exit(not (program.result.testsRun>0 and program.result.wasSuccessful()))
