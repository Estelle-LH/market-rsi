import json
from pathlib import Path
import tempfile
import unittest

from public_source_metadata import MAX_BYTES, NoRedirect, metadata_url, parse_listing, run


class MetadataTests(unittest.TestCase):
    def item(self, **changes):
        return {'type': 'file', 'path': 'tape.db.zst', 'size': 42, 'oid': 'a' * 40,
                'lfs': {'oid': 'b' * 64, 'size': 42}, **changes}

    def parse(self, items, **headers):
        return parse_listing(json.dumps(items).encode(), headers)

    def test_only_exact_pinned_root_metadata_url(self):
        url = metadata_url('owner/data', 'a' * 40)
        self.assertIn('/api/datasets/owner/data/tree/', url)
        self.assertTrue(url.endswith('?recursive=false&expand=false'))
        for dataset, revision in [('owner/data', 'main'), ('owner/../file', 'a' * 40),
                                  ('owner/data?x', 'a' * 40), ('https://bad/data', 'a' * 40)]:
            with self.assertRaises(ValueError):
                metadata_url(dataset, revision)

    def test_advertised_size_is_not_download_or_content_proof(self):
        result = self.parse([self.item()])
        self.assertEqual(result['objects'][0]['advertised_bytes'], 42)
        for name in ('acquisition_admitted', 'source_selected', 'raw_contents_verified',
                     'fresh_test_admitted', 'event_time_coverage_verified', 'recursive_inventory_complete'):
            self.assertFalse(result[name])

    def test_pagination_not_silently_complete(self):
        self.assertFalse(self.parse([], pagination_link='next')['root_listing_complete_by_http_pagination'])

    def test_lfs_size_hash_and_boolean_size_rejected(self):
        for item in [self.item(size=True), self.item(size=-1),
                     self.item(lfs={'oid': 'b' * 64, 'size': 41}),
                     self.item(lfs={'oid': 'a' * 40, 'size': 42})]:
            with self.assertRaises(ValueError):
                self.parse([item])

    def test_duplicate_path_and_non_root_name_rejected(self):
        for items in [[self.item(), self.item()], [self.item(path='../x')],
                      [self.item(path='sample/rows.parquet')], [self.item(path='.')]]:
            with self.assertRaises(ValueError):
                self.parse(items)

    def test_duplicate_json_and_nonfinite_and_oversize_rejected(self):
        for body in [b'[{"type":"file","type":"directory"}]', b'[NaN]', b' ' * (MAX_BYTES+1)]:
            with self.assertRaises(ValueError):
                parse_listing(body, {})

    def test_redirect_rejected(self):
        with self.assertRaises(ValueError):
            NoRedirect().redirect_request(None, None, 302, '', {}, 'https://bad.test')

    def test_fresh_claim_and_no_repeat_even_after_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'inspection'
            calls = []
            def fake(url):
                calls.append(url)
                return b'not-json', {}
            with self.assertRaises(ValueError):
                run('owner/data', 'a' * 40, output, getter=fake)
            self.assertTrue((output / 'failure.json').exists())
            self.assertTrue((output / 'response.body.json').exists())
            with self.assertRaisesRegex(ValueError, 'fresh'):
                run('owner/data', 'a' * 40, output, getter=fake)
            self.assertEqual(len(calls), 1)

    def test_success_preserves_response_without_acquiring_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = json.dumps([self.item()]).encode()
            output = Path(tmp) / 'inspection'
            result = run('owner/data', 'a' * 40, output,
                         getter=lambda _: (body, {'metadata_http_body_bytes': len(body)}))
            self.assertEqual((output / 'response.body.json').read_bytes(), body)
            self.assertFalse((output / 'tape.db.zst').exists())
            self.assertEqual(result['new_market_data_download_bytes'], 0)


if __name__ == '__main__':
    unittest.main()
