import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from capture_quote_batches import audit_one,durable_json,selected_dates
from capture_quote_audit import remote_day


class BatchTests(unittest.TestCase):
    def test_protected_and_duplicate_scope_denied(self):
        for dates in ([],['2026-08-26'],['2026-09-07','2026-09-07']):
            with self.assertRaises(ValueError):selected_dates(dates)
        with self.assertRaises(ValueError):remote_day('2026-08-26')

    def test_success_and_scope_checked_before_day_is_saved(self):
        value={'date':'2026-09-07','source_admitted':False,'raw_rows_exported':0,'labels_built':0}
        calls=[]
        def run(cmd,**kwargs):
            calls.append((cmd,kwargs));return subprocess.CompletedProcess(cmd,0,json.dumps(value).encode(),b'')
        result=audit_one('2026-09-07',b'fixture',1200,run=run,clock=lambda:0)
        self.assertEqual(result['status'],'complete_day')
        self.assertIn('nice -n 10 timeout 600s',calls[0][0][-1])
        self.assertEqual(calls[0][1]['timeout'],615)
        value['date']='2026-08-26'
        self.assertEqual(audit_one('2026-09-07',b'fixture',1200,run=run,clock=lambda:0)['status'],'failed')

    def test_timeout_is_failure_not_retry(self):
        calls=[]
        def run(cmd,**kwargs):
            calls.append(cmd);raise subprocess.TimeoutExpired(cmd,kwargs['timeout'])
        result=audit_one('2026-09-07',b'fixture',1200,run=run,clock=lambda:0)
        self.assertEqual(len(calls),1);self.assertEqual(result['status'],'failed')
        self.assertFalse(result['automatic_retry']);self.assertTrue(result['remote_exit_unverified'])

    def test_batch_deadline_caps_or_skips_dispatch(self):
        def forbidden(*a,**k):raise AssertionError('must not launch')
        result=audit_one('2026-09-07',b'fixture',20,run=forbidden,clock=lambda:0)
        self.assertEqual(result['status'],'not_started')

    def test_independent_receipt_survives_missing_summary_and_is_exclusive(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'day.json';durable_json(path,{'status':'complete_day'})
            self.assertEqual(json.loads(path.read_text())['status'],'complete_day')
            self.assertFalse((path.parent/'report.json').exists())
            with self.assertRaises(FileExistsError):durable_json(path,{'status':'changed'})


if __name__=='__main__':unittest.main()
