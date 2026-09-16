from pathlib import Path
import tempfile
import unittest
from audit_capture_batch_result import audit
from market_rsi import digest,file_hash,fresh_json


def fixture(root,crossed=1):
    # The production supervisor stores canonical absolute paths (macOS /var is a symlink).
    root=root.resolve()
    date='2026-08-21';reader='0'*64
    claim={'dates':[date],'protected_interval':['2026-08-26','2026-09-06'],'reader_sha256':reader}
    fresh_json(root/'claim.json',claim)
    result={'date':date,'counts':{'polymarket_rows':2,'crossed_book':crossed},'valid_adjacent_mid_pairs':1,
        'equal_adjacent_mid_pairs':1,'source_admitted':False,'raw_rows_exported':0,'labels_built':0,
        'utc_minutes_with_observations':1,'market_outcome_pairs':1,'file_sha256':'1'*64}
    path=root/('day-'+date+'.json')
    fresh_json(path,{'date':date,'status':'complete_day','result':result,'result_sha256':digest(result),
        'source_reader_sha256':reader})
    report={'claim_sha256':file_hash(root/'claim.json'),
        'records':[{'date':date,'status':'complete_day','path':str(path),'sha256':file_hash(path)}]}
    report['result_sha256']=digest(report);fresh_json(root/'report.json',report)
    return path


class ResultTests(unittest.TestCase):
    def test_integrity_does_not_admit_bad_data(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture(root);result=audit(root)
            self.assertTrue(result['receipt_integrity_passed'])
            self.assertEqual(result['totals']['crossed_fraction'],0.5)
            self.assertFalse(result['source_admitted'])

    def test_changed_day_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=fixture(root);path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):audit(root)

    def test_consistently_hashed_but_impossible_counters_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture(root,crossed=3)
            with self.assertRaisesRegex(ValueError,'inconsistent counters'):audit(root)


if __name__=='__main__':unittest.main()
