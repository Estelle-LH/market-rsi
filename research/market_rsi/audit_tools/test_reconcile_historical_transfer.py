import copy
import unittest
from reconcile_historical_transfer import reconcile_ingest


class TransferAccountingTests(unittest.TestCase):
    def fixture(self):
        selected=[{'path':'a','bytes':10,'lfs_sha256':'a'*64},{'path':'b','bytes':20,'lfs_sha256':'b'*64}]
        events=[{'event':'download_started','path':'a','bytes':10},
            {'event':'file_acquired','path':'a','mode':'downloaded_public_frozen_object','new_payload_bytes':10,'sha256':'a'*64},
            {'event':'file_acquired','path':'b','mode':'copied_hash_verified_cache','new_payload_bytes':0,'sha256':'b'*64}]
        return selected,events

    def test_copies_are_not_transfers(self):
        s,e=self.fixture();r=reconcile_ingest(e,s)
        self.assertEqual(r['selected_object_bytes'],30);self.assertEqual(r['recorded_new_payload_bytes'],10)

    def test_unresolved_or_duplicate_transfers_fail(self):
        s,e=self.fixture()
        for changed in [e[:-1],e+[e[0]],e+[e[1]],e[1:]]:
            with self.assertRaises(ValueError):reconcile_ingest(changed,s)

    def test_changed_bytes_or_hash_fail(self):
        s,e=self.fixture()
        for index,field,value in [(0,'bytes',11),(1,'new_payload_bytes',9),(2,'new_payload_bytes',20),(1,'sha256','x')]:
            modified=copy.deepcopy(e);modified[index][field]=value
            with self.assertRaises(ValueError):reconcile_ingest(modified,s)
