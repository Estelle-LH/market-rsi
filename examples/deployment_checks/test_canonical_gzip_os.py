import gzip
import unittest
from canonical_gzip_os import canonical_gzip_os

class CanonicalGzip(unittest.TestCase):
    def setUp(self):
        self.payload=b'public synthetic bytes\x00'*37
        self.archive=gzip.compress(self.payload,mtime=0)
    def test_os_variants_have_same_independent_archive_bytes(self):
        outputs={canonical_gzip_os(self.archive[:9]+bytes([value])+self.archive[10:]) for value in (0,3,19,255)}
        self.assertEqual(len(outputs),1)
    def test_original_payload_stream_and_crc_length_trailer_are_preserved(self):
        result=canonical_gzip_os(self.archive)
        self.assertEqual(gzip.decompress(result),self.payload)
        self.assertEqual(result[:9],self.archive[:9]);self.assertEqual(result[10:],self.archive[10:])
    def test_already_canonical_is_idempotent(self):
        once=canonical_gzip_os(self.archive);self.assertEqual(canonical_gzip_os(once),once)
    def test_wrong_flags_time_compression_format_or_type_refuse(self):
        for value in (b'',self.archive[:17],bytearray(self.archive),self.archive[:3]+b'\x08'+self.archive[4:],
            self.archive[:4]+b'\x01'+self.archive[5:],b'PK'+self.archive[2:]):
            with self.subTest(value_type=type(value).__name__),self.assertRaises(ValueError):canonical_gzip_os(value)

if __name__=='__main__':unittest.main(verbosity=2)
