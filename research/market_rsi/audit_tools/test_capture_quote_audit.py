import gzip
import json
from pathlib import Path
import tempfile
import unittest
from capture_quote_audit import audit_quote,completed_day_evidence

HEAD='ts_utc,ts_ms,venue,market,outcome,bid,bid_size,ask,ask_size,mid,spread\n'


class QuoteAuditTests(unittest.TestCase):
    def write(self,path,text):
        with gzip.open(path,'wt') as f:f.write(HEAD+text)

    def test_real_clock_and_crossed_rows_reported_not_fixed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'quotes.csv.gz'
            self.write(p,'2026-09-07T00:00:00Z,1788739200000,polymarket,m,y,0.4,2,0.6,3,0.5,0.2\n'
                '2026-09-07T00:00:01Z,1788739201000,polymarket,m,y,0.6,2,0.4,3,0.5,-0.2\n')
            r=audit_quote(p,'2026-09-07')
            self.assertEqual(r['counts']['crossed_book'],1)
            self.assertEqual(r['equal_adjacent_mid_fraction'],1)
            self.assertEqual(r['counts'].get('clock_disagreement_over_1ms',0),0)
            self.assertFalse(r['source_admitted'])

    def test_protected_dates_stop_before_price_analysis(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'quotes.csv.gz'
            self.write(p,'2026-09-06T00:00:00Z,1788652800000,polymarket,m,y,,,,,,\n')
            with self.assertRaisesRegex(RuntimeError,'protected'):audit_quote(p,'2026-09-07')

    def test_header_only_is_not_quiet_market(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'quotes.csv.gz';self.write(p,'')
            r=audit_quote(p,'2026-09-07')
            self.assertIsNone(r['equal_adjacent_mid_fraction'])
            self.assertIsNone(r['max_timestamp_ms'])
            self.assertFalse(r['source_admitted'])

    def test_timeout_progress_preserves_finished_day_only(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'quotes.csv.gz';self.write(p,'')
            result=audit_quote(p,'2026-08-21')
            packet={'completed_day':'2026-08-21','polymarket_rows':0,'day_result':result}
            stream=(json.dumps(packet)+'\nSSH connection closed\n').encode()
            self.assertEqual(completed_day_evidence(stream),[result])

    def test_progress_rejects_missing_aggregate_and_wrong_date(self):
        with self.assertRaisesRegex(ValueError,'aggregate missing'):
            completed_day_evidence(b'{"completed_day":"2026-08-21","polymarket_rows":10}\n')
        with self.assertRaisesRegex(ValueError,'sequence'):
            completed_day_evidence(b'{"completed_day":"2026-08-22"}\n')


if __name__=='__main__':unittest.main()
