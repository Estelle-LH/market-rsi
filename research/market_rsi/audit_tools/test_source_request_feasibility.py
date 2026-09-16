import copy
import unittest
from audit_source_request_feasibility import summarize_inventory
from market_rsi import digest


class RequestInventoryTests(unittest.TestCase):
    def setUp(self):
        self.i = {'schema': 'openmarket_frozen_partition_inventory_v1', 'dataset': 'fixture',
            'revision': 'fixture', 'files': [
                {'path': 'unified/ticks/date=2026-05-15/part-000001.parquet', 'bytes': 100},
                {'path': 'unified/metadata/unpartitioned/part-000001.parquet', 'bytes': 20}]}
        self.r = {'earliest_utc_date': '2026-05-16', 'latest_utc_date': '2026-06-30'}
        self.seal()

    def seal(self):
        self.i['inventory_sha256'] = digest({k:v for k,v in self.i.items() if k != 'inventory_sha256'})

    def test_no_partition_does_not_prove_no_events_or_freshness(self):
        r = summarize_inventory(self.i, self.r)
        self.assertEqual(r['advertised_objects_in_requested_window'], 0)
        self.assertFalse(r['event_time_coverage_from_partition_names'])
        self.assertFalse(r['freshness_proven']); self.assertFalse(r['acquisition_admitted'])

    def test_matching_partition_still_not_download_permission(self):
        self.r['earliest_utc_date'] = '2026-05-15'
        r = summarize_inventory(self.i, self.r)
        self.assertEqual(r['advertised_objects_in_requested_window'], 1)
        self.assertFalse(r['acquisition_admitted'])

    def test_advertised_bytes_are_not_new_downloads(self):
        r = summarize_inventory(self.i, self.r)
        self.assertEqual(r['all_advertised_unified_bytes_not_downloaded'], 120)
        self.assertEqual(r['new_downloads'], 0)

    def test_hash_mutation_fails(self):
        self.i['files'][0]['bytes'] += 1
        with self.assertRaisesRegex(ValueError, 'inventory hash'):
            summarize_inventory(self.i, self.r)

    def test_duplicate_path_fails(self):
        self.i['files'].append(copy.deepcopy(self.i['files'][0])); self.seal()
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            summarize_inventory(self.i, self.r)

    def test_bad_partition_date_fails(self):
        self.i['files'][0]['path'] = 'unified/ticks/date=2026-02-30/part-000001.parquet'; self.seal()
        with self.assertRaises(ValueError):
            summarize_inventory(self.i, self.r)

    def test_path_escape_fails(self):
        self.i['files'][0]['path'] = 'unified/../../elsewhere'; self.seal()
        with self.assertRaisesRegex(ValueError, 'relative unified'):
            summarize_inventory(self.i, self.r)


if __name__ == '__main__':
    unittest.main()
