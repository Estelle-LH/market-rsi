import hashlib
from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
import unittest
from single_object_stream import stream_object,open_source


class StreamTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name).resolve()/'source'
        self.raw=b'{"x":1}\n{"x":2}\n';self.path.write_bytes(self.raw)

    def tearDown(self):self.tmp.cleanup()

    def run_stream(self,consume=lambda *_:None,**overrides):
        kw=dict(advertised_bytes=len(self.raw),max_input_bytes=len(self.raw),max_decoded_bytes=1024,
            wall_seconds=5,consume=consume,decoder_command=(sys.executable,'-c',
                'import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())'))
        kw.update(overrides);return stream_object(self.path,**kw)

    def test_one_pass_hash_and_lines_complete(self):
        lines=[];r=self.run_stream(lambda b,n:lines.append((b,n)))
        self.assertTrue(r['complete']);self.assertEqual(r['compressed_sha256'],hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(r['decoded_records'],2);self.assertEqual(lines,[(b'{"x":1}\n',1),(b'{"x":2}\n',2)])
        self.assertTrue(r['decoder_reaped'] and r['feeder_reaped']);self.assertFalse(r['source_admitted'])

    def test_size_or_symlink_refused_before_read(self):
        with self.assertRaises(ValueError):self.run_stream(advertised_bytes=1)
        p=self.path.parent/'link';p.symlink_to(self.path)
        with self.assertRaises(ValueError):open_source(p,len(self.raw),len(self.raw))

    def test_decoded_limit_yields_partial_and_reaps(self):
        r=self.run_stream(max_decoded_bytes=3)
        self.assertFalse(r['complete']);self.assertTrue(r['partial_diagnostic_only'])
        self.assertTrue(r['decoder_reaped'] and r['feeder_reaped'])

    def test_parse_failure_stops_without_raw_error_text(self):
        def fail(*_):raise ValueError('private fixture row must not leak')
        r=self.run_stream(fail);self.assertFalse(r['complete']);self.assertNotIn('private',str(r))

    def test_input_mutation_cannot_complete(self):
        def mutate(*_):self.path.write_bytes(self.raw+b'changed')
        self.assertFalse(self.run_stream(mutate)['complete'])

    @unittest.skipUnless(shutil.which('zstd'),'zstd executable unavailable')
    def test_real_zstd_and_truncated_stream(self):
        original=self.raw
        encoded=subprocess.run(['zstd','-q','-c'],input=original,stdout=subprocess.PIPE,check=True).stdout
        self.raw=encoded;self.path.write_bytes(encoded)
        r=self.run_stream(decoder_command=('zstd','-dc'))
        self.assertTrue(r['complete']);self.assertEqual(r['decoded_sha256'],hashlib.sha256(original).hexdigest())
        self.raw=encoded[:-3];self.path.write_bytes(self.raw)
        r=self.run_stream(decoder_command=('zstd','-dc'))
        self.assertFalse(r['complete']);self.assertTrue(r['decoder_reaped'] and r['feeder_reaped'])


if __name__=='__main__':unittest.main()
