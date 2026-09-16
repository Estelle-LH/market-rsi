import json
from pathlib import Path
import tempfile
import unittest
from market_rsi import digest,file_hash,load_json
from archived_failed_source_session import verify
from test_archived_source_session import fixture
from prepare_executable_source_workspace import prepare


class FailedHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()/'old'
        self.audit,self.budget,self.pins=fixture(self.root)
        for name in ('submitted-decision.json','source-study-proposal.json'):(self.root/name).unlink()
        events=[]
        for n,name in enumerate(('inspect_harness','request_capability'),1):
            p=self.root/'records'/f'{n:04d}.json';r=load_json(p);r.update(tool=name,arguments={},result={})
            p.write_text(json.dumps(r));e={'sequence':n,'previous':events[-1]['record_sha256'] if events else None,
                'tool':name,'record':{'path':str(p),'sha256':file_hash(p)}}
            e['record_sha256']=digest(e);events.append(e)
        (self.root/'activity.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        p=self.root/'session/assessment.json';a=load_json(p);a.update(valid=False,exit_code=-15);p.write_text(json.dumps(a))
        a=load_json(self.audit);a.update(controller_valid=False,decision_sha256=None,decision=None,
            assessment_sha256=file_hash(p),tools=[{'tool':t,'status':'ok','count':1} for t in ('inspect_harness','request_capability')])
        self.save_audit(a)

    def save_audit(self,a):
        a['result_sha256']=digest({k:v for k,v in a.items() if k!='result_sha256'})
        self.audit.write_text(json.dumps(a));self.pins['audit']=a['result_sha256']

    def tearDown(self):self.tmp.cleanup()

    def read(self):return verify(self.root,self.audit,self.budget,self.pins)

    def test_keeps_failed_status_without_executing_or_changing_history(self):
        before={p:file_hash(p) for p in self.root.rglob('*') if p.is_file()}
        r=self.read();self.assertFalse(r['receipt']['failure_reclassified_as_success'])
        self.assertFalse(r['receipt']['old_code_executed'])
        self.assertEqual(before,{p:file_hash(p) for p in before})

    def test_tampered_source_and_inflight_state_rejected(self):
        job=next(iter(self.budget['jobs'].values()));job['state']='dispatched'
        with self.assertRaises(ValueError):self.read()
        job['state']='metered_terminal';(self.root/'code/historical.py').write_text('pass\n')
        with self.assertRaises(ValueError):self.read()

    def test_uncertain_upper_is_preserved_and_new_receipt_blocks_migration(self):
        name=self.root.name+'-turn-002';self.budget['jobs'][name]={'state':'uncertain_terminal','uncertain_upper_usd':'0.5'}
        a=load_json(self.audit);a['turns'].append({'job_id':name,'state':'uncertain_terminal',
            'response_sha256':None,'uncertain_upper_usd':'0.5'});a['session_uncertain_upper_usd']='0.5';self.save_audit(a)
        self.assertEqual(self.read()['receipt']['uncertain_upper_usd'],'0.5')
        p=self.root/'session/turn-002';p.mkdir();(p/'response.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'reconciliation'):self.read()

    def test_existing_output_rejected_before_other_access(self):
        with self.assertRaisesRegex(ValueError,'fresh'):prepare(self.root)


if __name__=='__main__':unittest.main()
