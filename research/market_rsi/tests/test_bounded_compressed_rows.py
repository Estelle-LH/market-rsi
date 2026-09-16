import gzip
import json
from pathlib import Path
import tempfile
import unittest

from bounded_compressed_rows import CompressedRows


class CompressedRowsTests(unittest.TestCase):
    def test_lossless_including_empty_values_and_quiet_rows(self):
        rows=[{'row':i,'values':{},'source':{'path':'repeated_source.parquet'},'quiet':True} for i in range(100)]
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'rows.gz'
            with CompressedRows(p,max_logical_bytes=50000,max_stored_bytes=10000) as out:
                for row in rows:out.write_row(row)
                self.assertEqual(out.rows,100)
            with gzip.open(p,'rt') as f:observed=[json.loads(line) for line in f]
            self.assertEqual(observed,rows)

    def test_repeated_write_is_deterministic_but_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as t:
            files=[Path(t)/'a.gz',Path(t)/'b.gz']
            for p in files:
                with CompressedRows(p,max_logical_bytes=10000,max_stored_bytes=10000) as out:out.write_row({'x':[1,2,None]})
            self.assertEqual(files[0].read_bytes(),files[1].read_bytes())
            with self.assertRaises(FileExistsError):CompressedRows(files[0],max_logical_bytes=10000,max_stored_bytes=10000)

    def test_logical_limit_is_independent_of_good_compression(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError,'logical-byte'):
                with CompressedRows(Path(t)/'rows.gz',max_logical_bytes=20,max_stored_bytes=1000) as out:
                    out.write_row({'repeat':'x'*1000})

    def test_stored_limit_is_not_silently_exceeded(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'rows.gz'
            with self.assertRaisesRegex(ValueError,'stored-byte'):
                with CompressedRows(p,max_logical_bytes=10000,max_stored_bytes=30) as out:
                    out.write_row({'items':list(range(1000))})
            self.assertLessEqual(p.stat().st_size,30)


if __name__=='__main__':unittest.main()
