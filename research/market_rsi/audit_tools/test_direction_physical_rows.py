from pathlib import Path
import tempfile
import unittest
import pyarrow as pa
import pyarrow.parquet as pq
from canary_direction_fields import physical_rows


class PhysicalRowsTests(unittest.TestCase):
    def test_ordinal_not_repeated_id_and_exact_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sample.parquet'
            pq.write_table(pa.table({'id':[1]*12,'marker':list(range(12))}),path,row_group_size=3)
            rows=physical_rows(path,[11,0,4,4],['marker'])
            self.assertEqual(rows,{0:{'marker':0},4:{'marker':4},11:{'marker':11}})
            for ordinals in ([],[-1],[12]):
                with self.assertRaises(ValueError):physical_rows(path,ordinals,['marker'])

    def test_multiple_batches_do_not_reset_row_ordinal(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sample.parquet'
            pq.write_table(pa.table({'marker':list(range(40000))}),path,row_group_size=20000)
            chosen=[1,16385,19999,20000,36385,39999]
            self.assertEqual(physical_rows(path,chosen,['marker']),{i:{'marker':i} for i in chosen})


if __name__=='__main__':unittest.main()
