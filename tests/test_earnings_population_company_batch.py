"""Real spawned process/RPC/SQLite tests; NO experiment API/Native/scorer.

Reuses the disclosed temporary model-grant fixture (historical400/Git seams).
The original prospective300 implementation and all reservation arithmetic run.
"""
from contextlib import closing
from copy import deepcopy
import json
import multiprocessing as mp
import os
from pathlib import Path
import time
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import earnings_population_company_batch as batch
import earnings_population_model_budget as model
from edgar_forecast_budget import BudgetStop
from test_earnings_population_model_budget import Fixture, G
from supervisor_harness import capacity_feedback_engine as engine


def synthetic_company(connection, company, request_id, barrier, seconds):
    """Invented local workload, not a provider/model/forecast substitute."""
    proxy=batch.BudgetProxy(connection)
    proxy.active();proxy.reserve(request_id,model.MODEL,G)
    if barrier is not None:barrier.wait(timeout=15)
    proxy.check_reserved(request_id,model.MODEL,G)
    start=time.monotonic();time.sleep(seconds);end=time.monotonic()
    proxy.check_reserved(request_id,model.MODEL,G);proxy.settle(request_id,1)
    proxy.active();proxy.summary()
    connection.send(dict(kind='done',error_type=None,result=dict(
        company_id=company,pid=os.getpid(),start=start,end=end,synthetic=True),checkpoint=None))
    connection.close()


def disconnect_after_budget_message(connection):
    connection.send(dict(kind='budget',operation='active',args=()))
    connection.close()


def synthetic_adapter(connection,binding,candidate,company,slot,contexts,clock,transport):
    synthetic_company(connection,company,'adapter-'+company,None,.3)


class CompanyBatchTests(unittest.TestCase):
    def setUp(self):
        self.f=Fixture();self.addCleanup(self.f.close);self.f.activate()
        self.budget=self.f.budget(optin=True);self.addCleanup(self.budget.close)
        self.companies=['CIK%010d'%i for i in range(1,5)]
        self.root=self.f.root/'batch';self.root.mkdir()
        (self.root/'companies').mkdir()
        self.value=dict(clean_slate_policy='round0_clean_slate_v1',clean_company_concurrency=batch.POLICY,
            companies=self.companies,root=str(self.root),rates=dict(api_model=model.MODEL),
            slots=dict(forecast=[str(self.root/'roles'/f'forecast-01-{i:02d}') for i in range(4)]))
        self.binding=dict(path=str(self.root/'runtime.json'),sha256='a'*64)
        self.store=batch.OwnedReservations(self.budget,self.binding,self.value)

    def reserve(self,i,amount=G,request=None):
        request=request or 'request-'+str(i)
        self.store.call(self.companies[i],'reserve',(request,model.MODEL,amount))
        return request

    def test_four_owned_loans_and_shared_window_cap_include_all_full_reservations(self):
        for i in range(4):self.reserve(i)
        self.assertEqual(self.budget.db.execute("SELECT SUM(reserved) FROM requests WHERE status='reserved'").fetchone()[0],4*G)
        for i in range(4):self.store.call(self.companies[i],'check_reserved',('request-'+str(i),model.MODEL,G))
        with self.assertRaises(BudgetStop):self.reserve(0,1,'another-own')
        self.store.call(self.companies[0],'settle',('request-0',1))
        with self.assertRaises(BudgetStop):self.reserve(0,2*G,'over-window')
        with self.assertRaises(BudgetStop):self.reserve(0,G,'request-0')

    def test_other_company_or_unknown_or_changed_owner_refused(self):
        request=self.reserve(0)
        with self.assertRaises(BudgetStop):self.store.call(self.companies[1],'settle',(request,1))
        with self.assertRaises(ValueError):self.store.call('CIK9999999999','reserve',('foreign',model.MODEL,G))
        owner=self.root/'request-ownership'/(request+'.json');owner.write_text('{}')
        with self.assertRaises((BudgetStop,ValueError)):self.store.active()

    def test_uncertain_or_unowned_pending_blocks_further_dispatch_and_retains_liability(self):
        request=self.reserve(0);self.store.call(self.companies[0],'uncertain',(request,))
        with self.assertRaises(BudgetStop):self.reserve(1)
        self.assertEqual(self.budget.db.execute('SELECT reserved,charged,status FROM requests WHERE id=?',(request,)).fetchone(),(G,0,'uncertain'))

    def test_missing_known_owner_is_not_admitted_as_normal_concurrency(self):
        self.f.insert('foreign-pending',model.MODEL,G,pending=True)
        with self.assertRaises(BudgetStop):self.store.active()

    def test_five_or_eight_and_no_explicit_policy_refused(self):
        for n in (5,8):
            value=deepcopy(self.value);value['companies']=self.companies+['extra']*(n-4)
            with self.assertRaises(ValueError):batch.enabled(value)
        self.assertFalse(batch.enabled(dict(clean_slate_policy='round0_clean_slate_v1')))

    def _wave(self,companies,prefix,barrier=None):
        context=mp.get_context('spawn');jobs=[];started=time.monotonic()
        for i,company in enumerate(companies):
            parent,child=context.Pipe()
            process=context.Process(target=synthetic_company,args=(child,company,prefix+str(i),barrier,.3))
            process.start();child.close()
            jobs.append(dict(company=company,slot=self.store.slots[company],process=process,connection=parent,done=None))
        rows,workers,events,errors=batch.serve(self.store,jobs)
        self.assertEqual(errors,[]);self.assertTrue(all(w['true_exit_code']==0 for w in workers))
        return time.monotonic()-started,rows,workers,events

    def test_real_four_spawned_process_overlap_with_parent_only_single_sqlite(self):
        context=mp.get_context('spawn')
        parallel,rows,workers,events=self._wave(self.companies,'parallel-',context.Barrier(4))
        self.assertEqual(len({w['pid'] for w in workers}),4)
        self.assertEqual(max(e['pending_count'] for e in events),4)
        values=[r['result'] for r in rows]
        self.assertLess(max(v['start'] for v in values),min(v['end'] for v in values))
        serial=0
        for i,company in enumerate(self.companies):
            elapsed,_,_,_=self._wave([company],'serial-'+str(i)+'-');serial+=elapsed
        self.store.active()
        self.assertEqual(self.budget.db.execute("SELECT COUNT(*) FROM requests WHERE status='reserved'").fetchone()[0],0)
        print(json.dumps(dict(test='REAL_LOCAL_PROCESS_RPC_SQLITE_NOT_MODEL',parallel_seconds=parallel,
            serial_seconds=serial,ratio=serial/parallel,unique_child_pids=[w['pid'] for w in workers],
            peak_pending=4,synthetic_delay_seconds=.3,production_api_calls=0,production_ledger_writes=0),sort_keys=True))

    def test_disconnected_worker_does_not_release_owner_before_other_workers_exit(self):
        context=mp.get_context('spawn');jobs=[]
        for i,company in enumerate(self.companies):
            parent,child=context.Pipe()
            target=disconnect_after_budget_message if i==0 else synthetic_company
            args=(child,) if i==0 else (child,company,'drain-'+str(i),None,.3)
            process=context.Process(target=target,args=args);process.start();child.close()
            jobs.append(dict(company=company,slot=self.store.slots[company],process=process,connection=parent,done=None))
        rows,workers,events,errors=batch.serve(self.store,jobs)
        self.assertIn(self.companies[0],errors)
        self.assertEqual(len(rows),3)
        self.assertTrue(all(not j['process'].is_alive() for j in jobs))
        self.assertTrue(all(w['true_exit_code']==0 for w in workers[1:]))
        self.store.active()

    def test_mid_spawn_failure_still_drains_started_work_and_preserves_partial_results(self):
        context=mp.get_context('spawn');counter=[0];started=[]
        def process_factory(**kwargs):
            process=context.Process(**kwargs);counter[0]+=1
            if counter[0]==2:
                process.start=lambda:(_ for _ in ()).throw(OSError('synthetic start failure'))
            else:started.append(process)
            return process
        fake_context=SimpleNamespace(Pipe=context.Pipe,Process=process_factory)
        value=deepcopy(self.value);newroot=self.f.root/'launch-test';newroot.mkdir()
        value['root']=str(newroot)
        value['slots']['forecast']=[str(newroot/'roles'/f'forecast-01-{i:02d}') for i in range(4)]
        service=SimpleNamespace(runtime=value,binding=self.binding,transport_policy={})
        live=dict(budget=self.budget,context_bindings={},clock_binding={})
        with patch.object(batch.mp,'get_context',return_value=fake_context),patch.object(batch,'_company_worker',synthetic_adapter),\
                patch('earnings_population_clean_slate.read_task',return_value=(dict(mode='evaluate'),{})):
            with self.assertRaisesRegex(RuntimeError,'Company batch failed'):batch.run(service,live,{})
        self.assertTrue(all(not p.is_alive() for p in started))
        saved=json.loads((newroot/'company-batch-execution.json').read_text())
        self.assertEqual(len(saved['completed_results']),1)
        self.assertEqual(len(saved['failed_companies']),3)
        self.assertEqual(saved['workers'][0]['true_exit_code'],0)


class IsolatedCleanupTests(unittest.TestCase):
    def test_company_code_receipts_are_checked_not_skipped(self):
        from earnings_native_failure import _cleanup
        import earnings_entry as entry
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();call=root/'code'/'forecast-01-03'/('call-'+'a'*32)
            call.mkdir(parents=True)
            source='Synthetic source bytes, never executed'
            supplied=engine.save(call/'input.json',dict(source=source,payload={}))
            (call/'stdout.bin').write_bytes(b'fixture stdout');(call/'stderr.bin').write_bytes(b'')
            result=dict(status='COMPLETED',cleanup_verified=True,host_candidate_execution=False,
                source_integrity_verified=True,retry_allowed=False,source_sha256=entry.digest(source.encode()),
                input_sha256=supplied['sha256'],stdout_sha256=engine.pin(call/'stdout.bin')['sha256'],
                stderr_sha256=engine.pin(call/'stderr.bin')['sha256'])
            engine.save(call/'result.json',result)
            self.assertEqual(len(_cleanup(root)),1)
            (call/'stdout.bin').write_bytes(b'tampered')
            with self.assertRaises(ValueError):_cleanup(root)

    def test_fifth_company_code_directory_is_not_silently_accepted(self):
        from earnings_native_failure import _cleanup
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();(root/'code'/'forecast-01-04').mkdir(parents=True)
            with self.assertRaises(ValueError):_cleanup(root)


if __name__=='__main__':unittest.main()
