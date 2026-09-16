import gzip
from pathlib import Path
import tempfile
import unittest
from capture_schema_probe import header,probe


class SchemaProbeTests(unittest.TestCase):
    def test_only_header_returned_not_data_rows(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'topofbook_test.csv.gz'
            with gzip.open(p,'wb') as f:f.write(b'venue,timestamp\nprivate_row,123\n')
            value=header(p)
            self.assertEqual(value['columns'],['venue','timestamp'])
            self.assertEqual(value['csv_data_rows_parsed'],0)
            self.assertNotIn('private_row',str(value))

    def test_malformed_header_not_silently_admitted(self):
        with tempfile.TemporaryDirectory() as d:
            day=Path(d)/'2026-09-01';day.mkdir()
            (day/'trades_x.csv').write_bytes(b'x,x\n1,2\n')
            value=probe(Path(d),['2026-09-01'])
            self.assertEqual(value['files'][0]['status'],'failed')
            self.assertFalse(value['source_admitted'])

    def test_arbitrary_path_is_not_a_date(self):
        with self.assertRaises(ValueError):probe(Path('/tmp'),['../../etc'])


if __name__=='__main__':unittest.main()
