import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from sealed_jsonl_integrity import (
    inspect_jsonl_zst, source_identity, verify_materialization_transport,
)


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name).resolve() / "source.jsonl"

    def tearDown(self):
        self.temp.cleanup()

    def inspect(self, raw, **overrides):
        self.path.write_bytes(raw)
        options = dict(
            advertised_bytes=len(raw), max_input_bytes=len(raw),
            max_decoded_bytes=4096, wall_seconds=5,
            decoder_command=(sys.executable, "-c",
                "import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())"),
        )
        options.update(overrides)
        return inspect_jsonl_zst(self.path, **options)

    def test_valid_receipt_has_only_identity_not_rows(self):
        raw = b'{"private":"value"}\n{"x":2}\n'
        receipt = self.inspect(raw)
        self.assertTrue(receipt["complete"])
        self.assertEqual(receipt["json_object_records"], 2)
        self.assertEqual(receipt["compressed_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertNotIn("private", str(receipt))
        self.assertEqual(receipt["provider_calls"], 0)
        self.assertEqual(receipt["target_statistics_computed"], 0)

    def test_invalid_json_and_scalar_fail_closed(self):
        self.assertFalse(self.inspect(b'{"x":1}\n{"x":\n')["complete"])
        self.assertFalse(self.inspect(b'[1,2,3]\n')["complete"])

    def test_empty_and_wrong_expected_hash_fail_closed(self):
        with self.assertRaises(ValueError):
            self.inspect(b"")
        receipt = self.inspect(b'{"x":1}\n', expected_compressed_sha256="0" * 64)
        self.assertFalse(receipt["complete"])
        self.assertEqual(receipt["failure_type"], "CompressedHashMismatch")

    def test_materialization_must_reproduce_admitted_identity(self):
        raw = b'{"x":1}\n'
        receipt = self.inspect(raw)
        transport = {
            "complete": True,
            "compressed_bytes_read": receipt["compressed_bytes"],
            "compressed_sha256": receipt["compressed_sha256"],
            "decoded_bytes": receipt["decoded_bytes"],
            "decoded_sha256": receipt["decoded_sha256"],
            "decoded_records": receipt["json_object_records"],
            "source_initial_stat": receipt["source_initial_stat"],
        }
        self.assertTrue(verify_materialization_transport(receipt, transport))
        transport["decoded_records"] += 1
        with self.assertRaises(ValueError):
            verify_materialization_transport(receipt, transport)
        source_identity(receipt)

    @unittest.skipUnless(shutil.which("zstd"), "zstd executable unavailable")
    def test_truncated_zstd_fails_closed(self):
        raw = b'{"x":1}\n{"x":2}\n'
        encoded = subprocess.run(
            ["zstd", "-q", "-c"], input=raw,
            stdout=subprocess.PIPE, check=True,
        ).stdout
        receipt = self.inspect(encoded, decoder_command=("zstd", "-dc"))
        self.assertTrue(receipt["complete"])
        truncated = encoded[:-3]
        receipt = self.inspect(truncated, decoder_command=("zstd", "-dc"))
        self.assertFalse(receipt["complete"])
        self.assertTrue(receipt["decoder_reaped"] and receipt["feeder_reaped"])


if __name__ == "__main__":
    unittest.main()
