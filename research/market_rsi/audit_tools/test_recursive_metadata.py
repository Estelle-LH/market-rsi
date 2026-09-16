import unittest
from market_rsi import canonical
from public_recursive_metadata import parse_inventory,normalized_path


def obj(path='orderbook/2026-01-01.parquet',size=123):
    return {'path':path,'type':'file','size':size,'oid':'a'*40,'lfs':{'size':size,'oid':'b'*64}}


class RecursiveMetadataTests(unittest.TestCase):
    def test_family_bytes_not_downloads_or_coverage(self):
        r=parse_inventory(canonical([obj(),obj('orderbook_1min/2026-01-01.parquet',10)]).encode(),{})
        self.assertEqual(r['families']['orderbook']['advertised_bytes'],123)
        self.assertEqual(r['families']['orderbook_1min']['advertised_bytes'],10)
        self.assertTrue(r['inventory_complete_by_http_pagination'])
        self.assertFalse(r['acquisition_admitted']);self.assertFalse(r['event_time_coverage_verified'])

    def test_partial_page_is_not_complete(self):
        r=parse_inventory(canonical([obj()]).encode(),{'pagination_link':'next'})
        self.assertFalse(r['inventory_complete_by_http_pagination']);self.assertFalse(r['pagination_followed'])

    def test_unsafe_paths_rejected(self):
        for path in ('../x','/x','a//b','a/./b','a/../b','a\\b','a/%2e','a/','x\n'):
            with self.subTest(path=path),self.assertRaises(ValueError):normalized_path(path)

    def test_duplicate_or_lfs_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):parse_inventory(canonical([obj(),obj()]).encode(),{})
        bad=obj();bad['lfs']['size']=1
        with self.assertRaisesRegex(ValueError,'LFS'):parse_inventory(canonical([bad]).encode(),{})

    def test_whole_body_and_record_bounds(self):
        for body in (b'x'*524289,b'{}',canonical([obj()]*1001).encode(),b'[{"path":"x","path":"y"}]'):
            with self.assertRaises(ValueError):parse_inventory(body,{})


if __name__=='__main__':unittest.main()
