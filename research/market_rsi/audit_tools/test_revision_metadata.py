from pathlib import Path
import tempfile
import unittest
from market_rsi import canonical,fresh_json
from public_revision_metadata import parse_info,run


class RevisionMetadataTests(unittest.TestCase):
    def test_exact_revision_not_coverage(self):
        r=parse_info(canonical({'id':'a/b','sha':'a'*40,'siblings':[{'rfilename':'x'}]}).encode(),'a/b')
        self.assertEqual(r['observed_revision'],'a'*40)
        self.assertFalse(r['recursive_inventory_verified']);self.assertFalse(r['source_selected'])

    def test_bad_body_rejected(self):
        for b in (b'[]',b'{"id":"a/b","sha":"main"}',
                b'{"id":"a/b","id":"a/b","sha":"main"}',
                canonical({'id':'wrong/source','sha':'a'*40}).encode(),b'x'*524289):
            with self.subTest(body=b[:60]),self.assertRaises(ValueError):parse_info(b,'a/b')

    def test_requested_url_receipt_and_no_reuse(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();req=root/'request.json'
            fresh_json(req,{'acquisition_admitted':False,
                'body':{'public_metadata_urls':['https://huggingface.co/api/datasets/a/b']}})
            body=canonical({'id':'a/b','sha':'b'*40}).encode()
            getter=lambda url:(body,{'status':200,'metadata_http_body_bytes':len(body)})
            r=run('a/b',req,root/'result',getter)
            self.assertEqual(r['raw_download_bytes'],0);self.assertFalse(r['acquisition_admitted'])
            with self.assertRaisesRegex(ValueError,'fresh'):run('a/b',req,root/'result',getter)
            with self.assertRaisesRegex(ValueError,'requested'):run('other/source',req,root/'bad',getter)


if __name__=='__main__':unittest.main()
