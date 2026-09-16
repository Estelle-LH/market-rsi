import gzip
from pathlib import Path
import tempfile
import unittest

from audit_historical_materialization import compare_prefix, nominal_scope


class MaterializationOutputAuditTests(unittest.TestCase):
    def test_nominal_window_end_is_exclusive_without_settlement_claim(self):
        slug='btc-updown-15m-1770890400';start=1770890400000
        self.assertEqual(nominal_scope(slug,start-1),'before_nominal_window')
        self.assertEqual(nominal_scope(slug,start),'within_nominal_window')
        self.assertEqual(nominal_scope(slug,start+899999),'within_nominal_window')
        self.assertEqual(nominal_scope(slug,start+900000),'after_nominal_window')
        self.assertEqual(nominal_scope('unknown',start),'unknown_nominal_window')

    def test_partial_prefix_is_losslessly_preserved(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'old').write_bytes(b'one\ntwo\n')
            with gzip.open(p/'new.gz','wb') as f:f.write(b'one\ntwo\nthree\n')
            self.assertEqual(compare_prefix(p/'old',p/'new.gz'),8)

    def test_any_changed_or_missing_old_row_fails(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'old').write_bytes(b'one\ntwo\n')
            with gzip.open(p/'new.gz','wb') as f:f.write(b'one\nNEW\n')
            with self.assertRaisesRegex(ValueError,'changed row content'):compare_prefix(p/'old',p/'new.gz')


if __name__=='__main__':unittest.main()
