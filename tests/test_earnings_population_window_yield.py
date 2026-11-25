"""Offline real spawn/exit/Pipe/tempSQLite; synthetic scores, NO API/Native.

Historical grant/Git fixture seams are disclosed by the reused tests. New
execution-rebind tests read original73 metadata but mock new-commit Git identity.
"""
from copy import deepcopy
from datetime import datetime,timezone
import multiprocessing as mp
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import earnings_population_company_batch as batch
import earnings_population_clean_slate as clean
import earnings_population_runtime as runtime
from edgar_forecast_budget import BudgetStop
from supervisor_harness import capacity_feedback_engine as e
import test_earnings_population_rolling as old
import test_earnings_population_pending_backpressure as pending


def yield_worker(connection,company,ident,root,barrier,fail):
    old.sys.addaudithook(old.deny_network);proxy=batch.BudgetProxy(connection);error=None;result=None
    try:
        proxy.reserve(ident,'gpt-6.1-sol',500000000)
        if barrier is not None:barrier.wait(timeout=15)
        proxy.settle(ident,400000000)
        if fail:raise ValueError('synthetic failed company, never normal yield')
        result=dict(synthetic=True,company_id=company)
    except BaseException as exc:error=type(exc).__name__
    cp=e.save(Path(root)/'companies'/(company+'.json'),dict(synthetic=True,error_type=error,result=result))
    connection.send(dict(kind='done',error_type=error,result=result,checkpoint=cp));connection.close()


class WindowYieldTests(unittest.TestCase):
    setUp=old.RollingTests.setUp
    resize_queue=old.RollingTests.resize_queue

    def enable_yield(self):
        self.value.update(id='synthetic-'+self.f.root.name,clean_learning_round=4,
            root=str(self.root),
            clean_company_concurrency=batch.ROLLING8,sources={clean.FOLLOWUP_PLANS[4]:e.pin(clean.e.REPO/clean.FOLLOWUP_PLANS[4])},
            rates=dict(api_model='gpt-6.1-sol',input='2',cached='.1',write='2.5',output='10'),
            limits=dict(forecast=dict(max_input_tokens=100000,max_output_tokens=25000,wall_seconds=1800)),
            cutoff_utc=datetime.fromtimestamp(self.budget.deadline,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
        self.resize_queue(25)

    def execute_yield(self,fail=False,queue=None):
        self.enable_yield()
        if queue is not None:
            self.companies=list(queue);self.value['companies']=self.companies
            self.value['slots']['forecast']=[str(self.root/'roles'/f'forecast-01-{i:02d}') for i in range(len(queue))]
            self.store.value=deepcopy(self.value);self.store.slots=dict(zip(self.companies,self.value['slots']['forecast']))
        ctx=mp.get_context('spawn');barrier=ctx.Barrier(min(8,len(self.companies)))
        def factory(company,slot):
            parent,child=ctx.Pipe();i=self.companies.index(company)
            process=ctx.Process(target=yield_worker,args=(child,company,'yield-'+company,str(self.root),barrier if i<8 else None,fail and i==0))
            job=dict(company=company,slot=slot,process=process,connection=parent,child=child,done=None)
            self.jobs.append(job);return job
        def verify(job):
            self.assertEqual(job['process'].exitcode,0);self.assertFalse(job['process'].is_alive())
            return e.save(self.root/'companies'/(job['company']+'-closed.json'),dict(fees=self.store.settled_company(job['company'])))
        return batch.serve_rolling(self.store,list(self.store.slots.items()),factory,verify,lambda:None)

    def test_fresh_original_windows_continue_only_unstarted_suffix_all25(self):
        remaining=None;all_rows=[];windows=0
        while remaining is None or remaining:
            if windows:
                self.root=self.f.root/f'rolling-window-{windows}';self.root.mkdir();(self.root/'companies').mkdir()
                self.budget=self.f.budget(optin=True);self.addCleanup(self.budget.close)
                self.binding=dict(path=str(self.root/'runtime.json'),sha256=str(windows)*64)
                self.store=batch.OwnedReservations(self.budget,self.binding,dict(self.value,root=str(self.root)))
            rows,workers,events,errors,remaining=self.execute_yield(queue=remaining)
            self.assertEqual(errors,[]);self.assertTrue(rows);all_rows+=rows;windows+=1
            self.assertLessEqual(windows,4)
        self.assertEqual(len(all_rows),25);self.assertEqual(len({r['company_id'] for r in all_rows}),25)
        self.assertGreater(windows,1)
        self.assertEqual(self.budget.db.execute("SELECT COUNT(*),SUM(charged) FROM requests WHERE id LIKE 'yield-%'").fetchone(),(25,10000000000))
        self.assertEqual(self.budget.db.execute("SELECT COUNT(*) FROM requests WHERE status='reserved'").fetchone()[0],0)

    def test_all25_declared_peak8_then_budget_yield_drains_not_failed(self):
        rows,workers,events,errors,suffix=self.execute_yield()
        self.assertEqual(errors,[]);self.assertTrue(suffix);self.assertGreaterEqual(len(rows),8)
        self.assertEqual([r['company_id'] for r in rows]+suffix,self.companies)
        self.assertTrue(all(j['process'].exitcode==0 for j in self.jobs))
        self.assertEqual(self.budget.db.execute("SELECT COUNT(*) FROM requests WHERE status='reserved'").fetchone()[0],0)
        self.assertLessEqual(sum(r[0] for r in self.budget.db.execute("SELECT charged FROM requests WHERE id LIKE 'yield-%'")),5000000000)
        self.assertEqual(max(r['active_count'] for r in events if r['kind']=='dispatch'),8)
        batch.verify_rolling_events(self.companies[:len(rows)],events,workers,limit=8)
        for company in suffix:e.save(self.root/'companies'/(company+'-not-measured.json'),dict(
            company_id=company,runtime=self.binding,status='NOT_MEASURED_WINDOW_YIELD',retry_allowed=False))
        saved=dict(runtime=self.binding,completed_results=rows,workers=workers,events=events,
            failed_companies=[],not_measured=suffix,normal_yield=dict(completed_prefix=self.companies[:len(rows)],remaining_suffix=suffix))
        self.assertEqual(batch.completed_companies(self.value,saved),self.companies[:len(rows)])
        for key,wrong in [('failed_companies',[self.companies[0]]),('not_measured',suffix[:-1]),
                ('normal_yield',dict(completed_prefix=self.companies[:len(rows)],remaining_suffix=suffix[::-1]))]:
            with self.assertRaises(ValueError):batch.completed_companies(self.value,dict(saved,**{key:wrong}))
        Path(self.store.slots[suffix[0]]).mkdir(parents=True)
        with self.assertRaisesRegex(ValueError,'already started'):batch.completed_companies(self.value,saved)

    def test_genuine_failure_is_not_normal_yield_and_no_new_dispatch(self):
        rows,workers,events,errors,suffix=self.execute_yield(True)
        self.assertTrue(errors);self.assertTrue(suffix)
        self.assertTrue(any(r['kind']=='stop_dispatch' for r in events))
        self.assertTrue(all(not j['process'].is_alive() for j in self.jobs))
        self.assertEqual(self.budget.db.execute("SELECT COUNT(*) FROM requests WHERE status='reserved'").fetchone()[0],0)

    def test_pending_only_wait_does_not_trigger_normal_yield(self):
        self.enable_yield()
        for i in range(5):self.store.call(self.companies[i],'reserve',('pending-'+str(i),'gpt-6.1-sol',1000000000))
        self.assertIsNone(self.store.dispatch_yield(self.companies[:5]))
        self.assertIsNotNone(self.store.reservation_wait(self.companies[5],('next','gpt-6.1-sol',500000000)))

    def test_original_time_admission_and_unknown_pending_not_hidden(self):
        self.enable_yield();self.store.value['cutoff_utc']=datetime.fromtimestamp(self.budget.clock()+100,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.assertEqual(self.store.dispatch_yield([])['reason'],'ORIGINAL_WALL_HEADROOM')
        self.f.insert('unknown','gpt-6.1-sol',1,pending=True)
        with self.assertRaises(BudgetStop):self.store.dispatch_yield([])


class WindowRebindTests(unittest.TestCase):
    def setUp(self):
        self.authority=e.read(clean.WINDOW_YIELD_AUTHORITY);self.old=e.read(self.authority['accepted_descriptor'])
        closure=e.read(self.authority['accepted_closure']);self.original=e.read(closure['runtime'])
        self.sources=deepcopy(self.original['sources'])
        for name in self.authority['allowed_production_changes']:self.sources[name]=e.pin(clean.e.REPO/name)
        self.rb=dict(path=str(clean.training.ROOT/'TRAIN25-CLEAN74-EXECUTION-REBIND.json'),sha256='c'*64)
        self.binding=dict(path=str(clean.training.ROOT/'TRAIN25-CLEAN74-REBIND-FROZEN-CANDIDATE.json'),sha256='d'*64)
        self.receipt=dict(authority=clean.WINDOW_YIELD_AUTHORITY,original_descriptor=self.authority['accepted_descriptor'],
            original_source_commit=self.old['source_commit'],new_source_commit='b'*40,sources=self.sources)
        self.descriptor=dict(deepcopy(self.old),source_commit='b'*40,execution_rebind=self.rb)
        self.local=runtime._local;self.subprocess=clean.subprocess.run

    def git(self,args,**kwargs):
        if args[1]=='diff':return SimpleNamespace(stdout='\n'.join(self.authority['allowed_production_changes']+self.authority['allowed_test_changes'])+'\n')
        if args[1]=='show' and args[2].startswith('b'*40+':'):
            return SimpleNamespace(stdout=(clean.e.REPO/args[2].split(':',1)[1]).read_bytes())
        return self.subprocess(args,**kwargs)  # Read-only original private Git blobs, no rerun.

    def verify(self):
        with patch.object(runtime,'_local',side_effect=lambda b:self.receipt if b==self.rb else self.local(b)),patch.object(clean.subprocess,'run',side_effect=self.git):
            return clean.window_execution_rebind(self.binding,self.descriptor)

    def test_actual_accepted73_same_RH_review_and_forecast_sources(self):
        got=self.verify();self.assertEqual(got['candidate'],self.old['candidate'])
        self.assertEqual(got['runtime']['source_commit'],self.old['source_commit'])
        with patch.object(e,'read',return_value=self.descriptor):
            self.assertEqual(clean.frozen_inputs(self.binding),[self.binding,self.rb,clean.WINDOW_YIELD_AUTHORITY])

    def test_candidate_resources_or_extra_forecast_source_refused(self):
        self.descriptor['forecast_limits']=dict(self.old['forecast_limits'],wall_seconds=1801)
        with self.assertRaises(ValueError):self.verify()
        self.descriptor=deepcopy(dict(self.old,source_commit='b'*40,execution_rebind=self.rb))
        self.sources['forecaster']=dict(self.sources['forecaster'],sha256='0'*64)
        with self.assertRaises(ValueError):self.verify()


if __name__=='__main__':unittest.main()
