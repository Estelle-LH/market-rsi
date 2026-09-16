import hashlib
import unittest
from pinned_source_document import document_url,verify_document


class PinnedDocumentTests(unittest.TestCase):
    def setUp(self):
        self.body=b'CREATE TABLE fixture (id INTEGER);\n'
        self.obj={'path':'schema.sql','type':'file','advertised_bytes':len(self.body),
            'git_oid':hashlib.sha1(b'blob '+str(len(self.body)).encode()+b'\x00'+self.body).hexdigest(),
            'advertised_sha256':None}
        self.receipt={'dataset':'a/b','revision':'a'*40,'objects':[self.obj]}
        self.request={'body':{'public_metadata_urls':['https://huggingface.co/datasets/a/b/raw/main/schema.sql']}}

    def test_pin_requested_doc_and_verify_blob(self):
        url,obj=document_url(self.receipt,self.request,'schema.sql')
        self.assertIn('/'+'a'*40+'/',url);self.assertNotIn('/main/',url)
        self.assertEqual(verify_document(self.body,obj),obj['git_oid'])

    def test_no_data_sample_path_or_arbitrary_doc(self):
        for name in ('x.parquet','samples/schema.sql','../schema.sql','OTHER.md'):
            with self.assertRaises(ValueError):document_url(self.receipt,self.request,name)

    def test_wrong_source_and_request_rejected(self):
        self.request['body']['public_metadata_urls']=['https://evil.example/datasets/a/b/raw/main/schema.sql']
        with self.assertRaisesRegex(ValueError,'requested'):document_url(self.receipt,self.request,'schema.sql')

    def test_body_length_hash_encoding_fail_closed(self):
        for body in (self.body+b'x',b'x'*len(self.body),b'\xff'*len(self.body)):
            with self.assertRaises(ValueError):verify_document(body,self.obj)

    def test_bound_checked_before_network(self):
        self.obj['advertised_bytes']=65537
        with self.assertRaisesRegex(ValueError,'bounded'):document_url(self.receipt,self.request,'schema.sql')


if __name__=='__main__':unittest.main()
