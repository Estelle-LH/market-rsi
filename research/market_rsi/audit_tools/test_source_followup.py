import unittest
from assemble_source_followup import inventory_summary


class SourceFollowupTests(unittest.TestCase):
    def test_missing_filename_is_not_verified_event_gap(self):
        r=inventory_summary([{'path':'orderbook/date=2026-05-16/data_0.parquet',
            'type':'file','advertised_bytes':10}],start='2026-05-16',end='2026-05-17')
        self.assertEqual(r['orderbook']['requested_window_files'],1)
        self.assertEqual(r['orderbook']['absent_filename_partitions_in_requested_window'],['2026-05-17'])
        self.assertFalse(r['orderbook']['event_dates_or_complete_sessions_verified'])
        self.assertFalse(r['orderbook']['subset_selected'])

    def test_bad_or_duplicate_partition_rejected(self):
        row={'path':'orderbook/date=2026-05-16/data_0.parquet','type':'file','advertised_bytes':10}
        for rows in ([row,row],[{**row,'path':'orderbook/date=2026-02-31/data_0.parquet'}],
                     [{**row,'path':'orderbook/unknown.parquet'}]):
            with self.assertRaises(ValueError):inventory_summary(rows)


if __name__=='__main__':unittest.main()
