"""Offline synthetic process/Pipe/SQLite, plus saved public partial-proof reads.

No API/Native/scorer/candidate execution or production ledger writes. Original
grant fixture explicitly mocks historical grant/Git prefixes; money arithmetic,
normal reservations/settlements, spawn/exit and parent dispatch are real.
"""
from copy import deepcopy
import multiprocessing as mp
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

import earnings_population_company_batch as batch
import earnings_population_clean_slate as clean
import earnings_population_runtime as runtime
from edgar_forecast_budget import BudgetStop
import test_earnings_population_rolling as old
import test_earnings_population_slot_rebind as slot_tests
from test_earnings_population_model_budget import Fixture, G
from supervisor_harness import capacity_feedback_engine as e


def deny_network(event,args):
    if event in ('socket.connect','socket.bind'):raise AssertionError('OFFLINE: no network')
sys.addaudithook(deny_network)


class PendingArithmeticTests(unittest.TestCase):
    def setUp(self):
        self.f=Fixture();self.addCleanup(self.f.close);self.f.activate()
        self.b=self.f.budget(optin=True);self.addCleanup(self.b.close)
        self.root=self.f.root/'pending';self.root.mkdir()
        self.companies=[f'CIK{i:010d}' for i in range(8)]
        self.value=dict(clean_slate_policy=clean.POLICY,clean_learning_round=3,
            clean_company_concurrency=batch.ROLLING8,root=str(self.root),companies=self.companies,
            rates=dict(api_model='gpt-6.1-sol'),slots=dict(forecast=[str(self.root/f's{i}') for i in range(8)]))
        self.store=batch.OwnedReservations(self.b,dict(path=str(self.root/'r.json'),sha256='a'*64),self.value)

    def reserve(self,i,amount,ident):return self.store.call(self.companies[i],'reserve',(ident,'gpt-6.1-sol',amount))
    def waiting(self,i=1,amount=2*G,ident='next'):
        return self.store.reservation_wait(self.companies[i],(ident,'gpt-6.1-sol',amount))

    def test_only_normal_owned_pending_defers_without_creating_a_reservation(self):
        self.reserve(0,4*G,'first');before=self.f.snapshot()
        wait=self.waiting();self.assertEqual(wait['pending_full_nano_usd'],4*G)
        self.assertEqual(before,self.f.snapshot());self.assertNotIn('next',self.store.assignments)
        self.assertIsNone(self.b.db.execute("SELECT 1 FROM requests WHERE id='next'").fetchone())
        self.store.call(self.companies[0],'settle',('first',1))
        self.assertIsNone(self.waiting());self.reserve(1,2*G,'next')
        self.assertEqual(self.b.db.execute("SELECT reserved FROM requests WHERE id='next'").fetchone(),(2*G,))
        with self.assertRaises(BudgetStop):self.waiting()

    def test_booked_window_exhaustion_is_fatal_not_waitable(self):
        self.reserve(0,4*G,'spent');self.store.call(self.companies[0],'settle',('spent',4*G))
        self.reserve(2,G//2,'other');self.assertIsNone(self.waiting())
        with self.assertRaises(BudgetStop):self.reserve(1,2*G,'next')

    def test_request_larger_than_total_window_never_waits(self):
        self.reserve(0,G,'other');self.assertIsNone(self.waiting(amount=5*G+1))
        with self.assertRaises(BudgetStop):self.reserve(1,5*G+1,'next')

    def test_unknown_pending_is_not_a_waitable_credit_source(self):
        self.f.insert('foreign','gpt-6.1-sol',4*G,pending=True)
        with self.assertRaises(BudgetStop):self.waiting()

    def test_uncertain_and_blocked_are_fatal(self):
        self.reserve(0,4*G,'first');self.store.call(self.companies[0],'uncertain',('first',))
        with self.assertRaises(BudgetStop):self.waiting()

    def test_changed_owner_or_old_request_never_waits(self):
        self.reserve(0,4*G,'first')
        with self.assertRaises(BudgetStop):self.waiting(i=0)
        with self.assertRaises(BudgetStop):self.waiting(ident='first')
        (self.root/'request-ownership'/'first.json').write_text('{}')
        with self.assertRaises((BudgetStop,ValueError)):self.waiting()

    def test_original_deadline_is_not_extended_by_pending(self):
        self.reserve(0,4*G,'first');self.b.monotonic_deadline=time.monotonic()-1
        with self.assertRaisesRegex(BudgetStop,'deadline'):self.waiting()

    def test_old_four_company_policy_keeps_original_fatal_semantics(self):
        self.store.value['clean_company_concurrency']=batch.ROLLING
        self.reserve(0,4*G,'first');self.assertIsNone(self.waiting())
        with self.assertRaises(BudgetStop):self.reserve(1,2*G,'next')


def pending_worker(conn,company,ident,root,amount=G,release=None):
    sys.addaudithook(deny_network);proxy=batch.BudgetProxy(conn);error=None;result=None
    try:
        proxy.reserve(ident,'gpt-6.1-sol',amount)
        if release is not None:
            if not release.wait(timeout=10):raise RuntimeError('Synthetic dispatch wait was not observed')
        else:time.sleep(.8)  # More than5 simultaneous full loans must wait under5.
        proxy.check_reserved(ident,'gpt-6.1-sol',amount);proxy.settle(ident,1)
        result=dict(synthetic=True,company_id=company)
    except BaseException as exc:error=type(exc).__name__
    cp=e.save(Path(root)/'companies'/(company+'.json'),dict(synthetic=True,company_id=company,
        status='COMPLETED_SCORED' if error is None else 'FAILED_NO_RETRY',worker_pid=os.getpid(),result=result,error_type=error))
    conn.send(dict(kind='done',error_type=error,result=result,checkpoint=cp));conn.close()


class PendingProcessTests(unittest.TestCase):
    setUp=old.RollingTests.setUp
    resize_queue=old.RollingTests.resize_queue

    def execute_pending(self,guard_failure=False,delayed_spawn=False):
        self.value.update(clean_company_concurrency=batch.ROLLING8,clean_learning_round=3)
        self.resize_queue(9);ctx=mp.get_context('spawn')
        release=ctx.Event()
        def factory(company,slot):
            if len(self.jobs)==1 and not release.is_set():
                # Ensure the FIRST request is ready before constructing worker2;
                # do not race a .8s loan against eight OS import/spawn timings.
                deadline=time.monotonic()+10
                while not self.jobs[0]['connection'].poll():
                    if time.monotonic()>=deadline:raise RuntimeError('Synthetic first request did not arrive')
                    time.sleep(.005)
            first=not self.jobs
            amount=(5*G if delayed_spawn else 4*G) if first else (G if delayed_spawn else 2*G)
            parent,child=ctx.Pipe();p=ctx.Process(target=pending_worker,args=(child,company,'hold-'+company,str(self.root),amount,release if first else None))
            job=dict(company=company,slot=slot,process=p,connection=parent,child=child,done=None);self.jobs.append(job);return job
        def verify(job):
            self.assertEqual(job['process'].exitcode,0);self.assertFalse(job['process'].is_alive())
            self.checked.append(job['company'])
            return e.save(self.root/'companies'/(job['company']+'-closed.json'),dict(
                synthetic=True,checkpoint=job['done']['checkpoint'],fees=self.store.settled_company(job['company'])))
        def guard():
            kinds={e.read(e.pin(p)).get('kind') for p in (self.root/'rolling-events').glob('*.json')}
            if 'reservation_wait' in kinds:
                release.set()
                if guard_failure:raise BudgetStop('synthetic unchanged cutoff/source guard')
            elif delayed_spawn and 'dispatch_capacity_wait' in kinds:
                release.set()  # Only AFTER a real unchanged-ledger capacity wait.
        output=batch.serve_rolling(self.store,list(self.store.slots.items()),factory,verify,guard)
        self.assertTrue(all(not j['process'].is_alive() for j in self.jobs));return output

    def test_eight_workers_hold_unsent_rpc_settle_and_refill_ninth(self):
        rows,workers,events,errors,unstarted=self.execute_pending()
        self.assertEqual((errors,unstarted),([],[]));self.assertEqual(len(rows),9)
        batch.verify_rolling_events(self.companies,events,workers,limit=8)
        self.assertTrue(any(x['kind']=='reservation_wait' for x in events))
        self.assertTrue(any(x['kind']=='reservation_wait_finished' for x in events))
        self.assertEqual(len({x['pid'] for x in workers}),9)
        self.assertEqual(self.budget.db.execute("SELECT COUNT(*),SUM(charged) FROM requests WHERE id LIKE 'hold-%'").fetchone(),(9,9))
        self.assertEqual(sum(x['kind']=='budget' and x.get('operation')=='reserve' for x in events),9)
        self.assertEqual(self.budget.db.execute("SELECT COUNT(*) FROM requests WHERE status='reserved'").fetchone()[0],0)

    def test_waiting_guard_failure_stops_new_dispatch_and_drains(self):
        rows,workers,events,errors,unstarted=self.execute_pending(True)
        self.assertTrue(errors);self.assertIn(self.companies[-1],unstarted)
        self.assertTrue(any(x['kind']=='reservation_wait_cancelled' for x in events))
        self.assertEqual(self.budget.db.execute("SELECT COUNT(*) FROM requests WHERE status='reserved'").fetchone()[0],0)

    def test_exactly_full_pending_defers_spawn_without_fatal_budget_stop(self):
        rows,workers,events,errors,unstarted=self.execute_pending(delayed_spawn=True)
        self.assertEqual((errors,unstarted),([],[]));self.assertEqual(len(rows),9)
        self.assertTrue(any(x['kind']=='dispatch_capacity_wait' and x['probe_only_no_request_or_reservation'] for x in events))
        self.assertEqual(self.budget.db.execute("SELECT COUNT(*) FROM requests WHERE id LIKE 'unreserved-spawn-probe-%'").fetchone()[0],0)
        batch.verify_rolling_events(self.companies,events,workers,limit=8)


class BackpressureRebindTests(slot_tests.ExecutionRebindTests):
    def setUp(self):
        super().setUp();self.authority=runtime._local(clean.BACKPRESSURE_AUTHORITY)
        self.receipt.update(schema='edgar25_pending_backpressure_execution_rebind_v1',authority=clean.BACKPRESSURE_AUTHORITY)
        self.rb=dict(self.rb,path=str(clean.training.ROOT/'TRAIN25-CLEAN71-EXECUTION-REBIND.json'))
        self.binding=dict(self.binding,path=str(clean.training.ROOT/'TRAIN25-CLEAN71-REBIND-FROZEN-CANDIDATE.json'))
        self.descriptor['execution_rebind']=self.rb

    def test_rebind_and_authority_are_in_per_send_input_guards(self):
        original=e.read
        with patch.object(e,'read',side_effect=lambda b: self.descriptor if b==self.binding else original(b)):
            got=clean.frozen_inputs(self.binding)
        self.assertIn(clean.BACKPRESSURE_AUTHORITY,got);self.assertIn(self.authority['partial_closure'],got)
        self.assertIn(clean.SLOT_REBIND_AUTHORITY,got);self.assertIn(self.rb,got)


class SavedPartialPublicEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.authority=e.read(clean.BACKPRESSURE_AUTHORITY)
        self.descriptor=e.read(self.authority['accepted_descriptor'])

    def test_real_original_seven_archive_rows_read_only_no_gate(self):
        with patch.object(clean,'closed_evidence',side_effect=AssertionError('Never rerun70 gate')):
            rows=clean.preserved70_rows(self.descriptor,self.authority['partial_closure'])
        self.assertEqual([r['company_id'] for r in rows],self.authority['preserve_completed_companies'])
        self.assertEqual(sum(r['points'] for r in rows),20.5)
        self.assertTrue(all(r['source_commit']==self.authority['previous_execution_source'] and r['preserved_partial'] for r in rows))
        self.assertEqual(sum(len(r['targets']) for r in rows),35)

    def test_wrong_partial_or_candidate_or_resource_refused(self):
        with self.assertRaises(ValueError):clean.preserved70_rows(self.descriptor,self.authority['accepted_closure'])
        for key,wrong in [('candidate',dict(self.descriptor['candidate'],id='0'*64)),('forecast_limits',{})]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                clean.preserved70_rows(dict(self.descriptor,**{key:wrong}),self.authority['partial_closure'])

    def synthetic_compare(self,extra):
        ids=self.descriptor['training'];binding=dict(path=str(clean.training.ROOT/'TRAIN25-CLEAN71-REBIND-FROZEN-CANDIDATE.json'),sha256='1'*64)
        row=lambda c:dict(company_id=c,points=3.5,targets=[dict(target_id=f'T{i:03d}') for i in range(1,6)])
        preserved=[row(c) for c in ids[:7]]
        value=dict(source_commit='b'*40,companies=extra,slots=dict(forecast=['synthetic-'+c for c in extra]))
        verified=dict(runtime=value,task=dict(frozen_candidate=binding,company_ids=extra),result=dict(
            runtime=dict(path='synthetic-runtime',sha256='2'*64),result=dict(results=[dict(result={}) for c in extra])))
        with patch.object(clean,'load_frozen',return_value=self.descriptor),\
                patch.object(clean,'preserved70_rows',return_value=preserved),\
                patch.object(clean,'closed_evidence',return_value=verified),\
                patch.object(clean,'_comparison_row',side_effect=lambda d,r,c,*a:row(c)):
            return clean.compare(binding,[dict(path='synthetic-result',sha256='3'*64)],preserved_partial=self.authority['partial_closure'])

    def test_seven_plus18_unique_full25_required_for_selection(self):
        result=self.synthetic_compare(self.descriptor['training'][7:])
        self.assertEqual(result['scored'],25);self.assertEqual(result['candidate_mean'],3.5)
        self.assertEqual(result['decision'],'ADOPT_CANDIDATE');self.assertFalse(result['next_mutation_allowed'])
        incomplete=self.synthetic_compare(self.descriptor['training'][7:-1])
        self.assertEqual(incomplete['scored'],24);self.assertIsNone(incomplete['candidate_mean'])
        self.assertEqual(incomplete['decision'],'INCOMPLETE_NO_SELECTION')

    def test_duplicate_company_across_old_and_new_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            self.synthetic_compare(self.descriptor['training'][6:])


if __name__=='__main__':unittest.main()
