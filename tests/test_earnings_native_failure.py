"""Known Native failure closure on real temp journal + invented owned receipts."""
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sqlite3
import unittest

from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine
from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
import test_earnings_capacity_adapter as native_fixture


def sha(raw):return hashlib.sha256(raw).hexdigest()


class FailureFixture:
    """No process/code execution: only inert request/receipt/ledger originals."""
    def __init__(self,test):
        self.native=native_fixture.EarningsCapacityTests('test_earnings_reject_keeps_parent_and_history')
        self.native.setUp(); test.addCleanup(self.native.doCleanups)
        self.batch=self.native.batch; self.home=self.native.root; self.root=self.home/'owned-forecast'
        self.root.mkdir(); self.ledger=self.home/'owned.sqlite3'
        self.db=sqlite3.connect(self.ledger); test.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE config (id INTEGER PRIMARY KEY,cap INTEGER,model_cap INTEGER,blocked INTEGER)')
        self.db.execute('INSERT INTO config VALUES (1,200000000000,100000000000,0)')
        self.db.execute('CREATE TABLE requests (id TEXT PRIMARY KEY,model TEXT,reserved INTEGER,charged INTEGER,status TEXT)')
        self.db.executemany('INSERT INTO requests VALUES (?,?,?,?,?)',[
            ('prior-other','other-model',1000,900,'settled'),
            ('owned-one','gpt-6.1-sol',1000,700,'settled'),('owned-two','gpt-6.1-sol',1000,1000,'settled_upper_bound')])
        self.db.commit()
        self.slot=self.root/'roles/forecast-01'; self.slot.mkdir(parents=True)
        self.runtime={'schema':'earnings_capacity_runtime_v2','purpose':'capacity_episode',
            'id':'synthetic-failed-forecast26','root':str(self.root),'source_commit':'c'*40,
            'ledger':str(self.ledger),'slots':{'forecast':[str(self.slot)]},
            'rates':{'api_model':'gpt-6.1-sol'},'cutoff_utc':'2000-01-01T00:00:00Z',
            'deadline_utc':'2000-01-01T00:01:00Z'}
        self.runtime_binding=engine.save(self.home/'runtime.json',self.runtime)
        self.claim_root=self.home/'.capacity-runtime-claims'; self.claim_root.mkdir()
        identity=sha(self.runtime['id'].encode())
        self.claim=self.claim_root/(identity+'.json'); self.terminal=self.claim_root/(identity+'.result.json')
        self.claim_value={'runtime':self.runtime_binding,'id':self.runtime['id'],'source_commit':'c'*40,
            'retry_allowed':False,'scope':'unverified_runtime_component'}
        self.terminal_value={'status':'FAILED_NO_RETRY','error_type':'BudgetStop','retry_allowed':False,
            'runtime':self.runtime_binding,'budget_summary':{'blocked':False,'unresolved_reserved_usd':0},
            'clock':None,'scope':'unverified_runtime_component','model_authorship_verified':False}
        engine.save(self.claim,self.claim_value); engine.save(self.terminal,self.terminal_value)
        for turn,identifier in ((1,'owned-one'),(2,'owned-two')):
            engine.save(self.slot/f'{turn:02d}-request.json',{'request_id':identifier,'reserved_nano_usd':1000,
                'payload':{'model':'gpt-6.1-sol'}})
        self.code=self.root/'code'/('call-'+'a'*32); self.code.mkdir(parents=True)
        source="PROGRAM={'axis':'R'}\ndef run(p): return {}\n"  # Inert, never executed/imported.
        request=json.dumps({'source':source,'payload':{'synthetic':True}},sort_keys=True).encode()
        stdout=b'{"ok":true,"value":{}}'; stderr=b''
        for name,raw in (('input.json',request),('stdout.bin',stdout),('stderr.bin',stderr)):(self.code/name).write_bytes(raw)
        self.code_value={'status':'COMPLETED','cleanup_verified':True,'host_candidate_execution':False,
            'source_integrity_verified':True,'source_sha256':sha(source.encode()),'input_sha256':sha(request),
            'stdout_sha256':sha(stdout),'stderr_sha256':sha(stderr),'error_type':None,'retry_allowed':False}
        engine.save(self.code/'result.json',self.code_value)
        self.pair=digest(self.batch.snapshot()['micro_evolution']['active_pair'])
        self.work='candidate-'+digest({'synthetic-runtime':self.runtime['id']})
        self.batch.record_capacity_work('claim',work_id=self.work,pair_sha256=self.pair,evidence_sha256='a'*64,
            expected_state_sha256=self.batch.snapshot()['state_sha256'])
        self.output=self.root/'native-failure'

    def replace(self,path,value):
        # Mutable invented fixtures only; never change actual runtime artifacts.
        Path(path).write_text(json.dumps(value))

    def close(self,**changes):
        args={'runtime_binding':self.runtime_binding,'work_id':self.work,'pair_sha256':self.pair,
            'output_root':self.output,'error_type':'BudgetStop'}; args.update(changes)
        return importlib.import_module('earnings_native_failure').close_failed_work(self.batch,**args)

    def journal(self):return {p.name:p.read_bytes() for p in self.batch.journal_dir.iterdir() if p.is_file()}


class NativeFailureTests(unittest.TestCase):
    def fixture(self):return FailureFixture(self)

    def test_known_BudgetStop_archives_exact_prefix_and_marks_failed_without_success_or_refund(self):
        f=self.fixture(); before=f.batch.snapshot(); raw=(f.batch.root/'batch.json').read_bytes(); prefix=f.journal()
        rows=f.db.execute('SELECT * FROM requests ORDER BY id').fetchall()
        result=engine.read(f.close()); after=f.batch.snapshot()
        self.assertEqual(result['status'],'FAILED_WORK_CLOSED_NO_RETRY')
        self.assertEqual(result['work_id'],f.work); self.assertFalse(result['candidate_adopted']); self.assertFalse(result['retry_allowed'])
        self.assertEqual(result['own_request_count'],2); self.assertEqual(result['own_charge_nano_usd'],1700)
        self.assertEqual(result['owner_terminal'],engine.pin(f.terminal))
        self.assertEqual(Path(result['before_native_snapshot']['path']).read_bytes(),raw)
        archived=engine.read(result['before_native_journal'])
        for name,data in prefix.items():
            self.assertEqual((f.batch.journal_dir/name).read_bytes(),data)
            self.assertIn(sha(data),json.dumps(archived))
        row=after['capacity_work'][-1]
        self.assertEqual(row['status'],'failed'); self.assertEqual(row['failure_evidence_sha256'],result['failure_evidence']['sha256'])
        self.assertIn('failed_at_utc',row); self.assertNotIn('output_evidence_sha256',row)
        self.assertEqual(after['active_attempt_ids'],[])
        for key in ('attempts_claimed','branches','incumbent','micro_evolution'):
            self.assertEqual(after[key],before[key])
        self.assertEqual(f.db.execute('SELECT * FROM requests ORDER BY id').fetchall(),rows)
        self.assertEqual(engine.read(result['after_native_snapshot']),after)
        cold=ContinuousDiscoveryBatch(f.batch.root,allow_temporary=True,test_clock=lambda:native_fixture.BASE,allow_test_clock=True)
        self.assertEqual(cold.snapshot(),after)
        self.assertEqual(engine.read(engine.pin(f.output/'before-native-batch.json')),before)

    def test_ordinary_failure_can_close_but_duplicate_cannot_append_or_reopen(self):
        f=self.fixture(); terminal=dict(f.terminal_value,error_type='RuntimeError'); f.replace(f.terminal,terminal)
        f.replace(f.code/'result.json',dict(f.code_value,status='FAILED_NO_RETRY',error_type='ValueError'))
        f.close(error_type='RuntimeError'); before=f.batch.snapshot(); prefix=f.journal()
        with self.assertRaises((ValueError,FileExistsError)):f.close(error_type='RuntimeError')
        self.assertEqual(f.batch.snapshot(),before); self.assertEqual(f.journal(),prefix)
        with self.assertRaises(ValueError):
            f.batch.record_capacity_work('complete',work_id=f.work,pair_sha256=f.pair,evidence_sha256='b'*64,
                expected_state_sha256=before['state_sha256'])
        self.assertEqual(f.batch.snapshot(),before)

    def test_zero_cost_known_closed_failure_needs_no_fabricated_request_or_code_credit(self):
        f=self.fixture()
        for name in ('01-request.json','02-request.json'):(f.slot/name).unlink()
        for name in ('input.json','stdout.bin','stderr.bin','result.json'):(f.code/name).unlink()
        f.code.rmdir()
        f.db.execute("DELETE FROM requests WHERE id IN ('owned-one','owned-two')"); f.db.commit()
        rows=f.db.execute('SELECT * FROM requests').fetchall()
        result=engine.read(f.close())
        self.assertEqual(result['own_request_count'],0); self.assertEqual(result['own_charge_nano_usd'],0)
        self.assertEqual(f.batch.snapshot()['capacity_work'][-1]['status'],'failed')
        self.assertEqual(f.db.execute('SELECT * FROM requests').fetchall(),rows)

    def test_missing_uncertain_or_forged_owner_proof_leaves_claim_and_prefix_unchanged(self):
        for kind in ('missing','success','uncertain','blocked','wrong-runtime','wrong-source','retry','wrong-error'):
            f=self.fixture(); before=f.batch.snapshot(); prefix=f.journal()
            if kind=='missing':f.terminal.unlink()
            elif kind=='wrong-source':f.replace(f.claim,dict(f.claim_value,source_commit='d'*40))
            else:
                terminal=deepcopy(f.terminal_value)
                if kind=='success':terminal['status']='COMPLETED_COMPONENT_CONTEXT'
                elif kind=='uncertain':terminal['budget_summary']['unresolved_reserved_usd']=0.1
                elif kind=='blocked':terminal['budget_summary']['blocked']=True
                elif kind=='wrong-runtime':terminal['runtime']=dict(f.runtime_binding,sha256='0'*64)
                elif kind=='retry':terminal['retry_allowed']=True
                elif kind=='wrong-error':terminal['error_type']='UnrelatedError'
                f.replace(f.terminal,terminal)
            with self.subTest(kind=kind),self.assertRaises((ValueError,FileNotFoundError)):f.close()
            self.assertEqual(f.batch.snapshot(),before); self.assertEqual(f.journal(),prefix)

    def test_unsettled_missing_model_mismatch_or_duplicate_owned_requests_remain_claimed(self):
        for kind in ('uncertain','missing','different-model','duplicate','unreserved'):
            f=self.fixture(); before=f.batch.snapshot(); prefix=f.journal()
            if kind=='uncertain':f.db.execute("UPDATE requests SET status='uncertain' WHERE id='owned-one'")
            elif kind=='missing':f.db.execute("DELETE FROM requests WHERE id='owned-one'")
            elif kind=='different-model':f.db.execute("UPDATE requests SET model='other-model' WHERE id='owned-one'")
            elif kind=='duplicate':f.replace(f.slot/'02-request.json',engine.read(engine.pin(f.slot/'01-request.json')))
            else:f.replace(f.slot/'01-request.json',{'request_id':'owned-one','payload':{'model':'gpt-6.1-sol'}})
            f.db.commit()
            with self.subTest(kind=kind),self.assertRaises(ValueError):f.close()
            self.assertEqual(f.batch.snapshot(),before); self.assertEqual(f.journal(),prefix)

    def test_partial_cleanup_or_code_hash_drift_never_releases_occupancy(self):
        for kind in ('cleanup','host','input','source','stdout','stderr','missing-result','partial-call'):
            f=self.fixture(); before=f.batch.snapshot(); prefix=f.journal()
            value=deepcopy(f.code_value)
            if kind=='cleanup':value['cleanup_verified']=False
            elif kind=='host':value['host_candidate_execution']=True
            elif kind=='source':value['source_sha256']='0'*64
            elif kind in ('input','stdout','stderr'):
                target={'input':'input.json','stdout':'stdout.bin','stderr':'stderr.bin'}[kind]
                (f.code/target).write_bytes(b'changed original')
            elif kind=='missing-result':(f.code/'result.json').unlink()
            else:(f.root/'code'/('call-'+'b'*32)).mkdir()
            if kind in ('cleanup','host','source'):f.replace(f.code/'result.json',value)
            with self.subTest(kind=kind),self.assertRaises((ValueError,FileNotFoundError)):f.close()
            self.assertEqual(f.batch.snapshot(),before); self.assertEqual(f.journal(),prefix)

    def test_wrong_pair_runtime_root_work_or_stale_Native_state_cannot_close(self):
        for kind in ('pair','work','output','runtime-drift','not-claimed'):
            f=self.fixture(); changes={}
            if kind=='pair':changes['pair_sha256']='0'*64
            elif kind=='work':changes['work_id']='other-work'
            elif kind=='output':changes['output_root']=f.home/'unowned-output'
            elif kind=='runtime-drift':f.replace(Path(f.runtime_binding['path']),dict(f.runtime,id='different-id'))
            else:
                f.batch.record_capacity_work('complete',work_id=f.work,pair_sha256=f.pair,evidence_sha256='b'*64,
                    expected_state_sha256=f.batch.snapshot()['state_sha256'])
            before=f.batch.snapshot(); prefix=f.journal()
            with self.subTest(kind=kind),self.assertRaises(ValueError):f.close(**changes)
            self.assertEqual(f.batch.snapshot(),before); self.assertEqual(f.journal(),prefix)


if __name__=='__main__':unittest.main()
