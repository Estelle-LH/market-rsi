import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

import zstandard

from canary_sqlite_fixture import build_fixture
from canary_sqlite_observations import inspect_archive
from guarded_sqlite_decode import decode, storage_plan


class StoragePlanTests(unittest.TestCase):
    def test_existing_compressed_bytes_not_double_counted(self):
        r = storage_plan(free_bytes=100, decoded_upper_bound_bytes=80, reserve_bytes=20)
        self.assertTrue(r["fits"])
        self.assertEqual(r["required_free_bytes"], 100)

    def test_planned_transfer_and_intermediates_are_additional(self):
        r = storage_plan(free_bytes=100, decoded_upper_bound_bytes=80, reserve_bytes=20,
                         compressed_bytes_not_yet_present=5, additional_working_bytes=7)
        self.assertFalse(r["fits"])
        self.assertEqual(r["required_free_bytes"], 112)

    def test_negative_bool_or_unknown_space_terms_refused(self):
        for value in (-1, True, None, "20"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                storage_plan(free_bytes=100, decoded_upper_bound_bytes=80, reserve_bytes=value)


@unittest.skipUnless(shutil.which("zstd"), "native zstd required for real decoder tests")
class GuardedDecodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        raw = self.root / "synthetic.sqlite"
        self.raw_hash, self.raw_size = build_fixture(raw)
        self.archive = self.root / "synthetic.sqlite.zst"
        self.archive.write_bytes(zstandard.ZstdCompressor(write_checksum=True).compress(raw.read_bytes()))
        self.archive.chmod(0o444)
        self.binary = Path(shutil.which("zstd")).resolve()
        self.binary_hash = hashlib.sha256(self.binary.read_bytes()).hexdigest()

    def tearDown(self):
        self.temp.cleanup()

    def run_decode(self, name="decode", **kwargs):
        options = dict(expected_sha256=hashlib.sha256(self.archive.read_bytes()).hexdigest(),
                       expected_bytes=self.archive.stat().st_size, decoder=self.binary,
                       expected_decoder_sha256=self.binary_hash,
                       decoded_upper_bound_bytes=self.raw_size, reserve_bytes=1_000_000,
                       max_seconds=10, free_bytes_at=lambda _: 100_000_000)
        options.update(kwargs)
        return decode(self.archive, self.root / name, **options)

    def failure(self, name="decode"):
        report = json.loads((self.root / name / "failure.json").read_text())
        self.assertFalse(report["passed"])
        self.assertTrue(report["process_reaped"])
        self.assertFalse((self.root / name / "result.json").exists())
        self.assertFalse((self.root / name / "payload.sqlite").exists())
        return report

    def test_exact_round_trip_then_readonly_activity(self):
        before = self.archive.read_bytes()
        r = self.run_decode()
        self.assertEqual(r["decoded_sha256"], self.raw_hash)
        self.assertEqual(r["decoded_bytes"], self.raw_size)
        self.assertEqual(self.archive.read_bytes(), before)
        self.assertTrue(r["process_reaped"])
        self.assertFalse(r["acquisition_admitted"])
        self.assertFalse((self.root / "decode/payload.partial").exists())
        data = inspect_archive(Path(r["decoded_file"]), expected_sha256=self.raw_hash,
                               expected_bytes=self.raw_size, start_ms=0, end_ms=180_000,
                               recorder_scope="synthetic-only")
        self.assertTrue(data["all_window_queries_complete"])
        self.assertFalse(data["fresh_validation_admitted"])

    def test_low_disk_refuses_before_child(self):
        with self.assertRaisesRegex(ValueError, "insufficient"):
            self.run_decode(free_bytes_at=lambda _: 2)
        self.assertIsNone(self.failure()["decoder_pid"])
        self.assertFalse((self.root / "decode/payload.partial").exists())

    def test_reserve_reached_midstream_stops_exact_child(self):
        free = iter([100_000_000, 0])
        with self.assertRaisesRegex(ValueError, "reserve reached"):
            self.run_decode(free_bytes_at=lambda _: next(free))
        report = self.failure()
        self.assertIsInstance(report["decoder_pid"], int)
        self.assertTrue((self.root / "decode/payload.partial").exists())

    def test_expansion_bound_stops_decoder(self):
        with self.assertRaisesRegex(ValueError, "byte bound"):
            self.run_decode(decoded_upper_bound_bytes=16)
        self.failure()

    def test_truncated_frame_never_published(self):
        self.archive.chmod(0o644)
        self.archive.write_bytes(self.archive.read_bytes()[:-1])
        self.archive.chmod(0o444)
        with self.assertRaisesRegex(ValueError, "decoder failed"):
            self.run_decode()
        self.failure()

    def test_checksum_corruption_never_published(self):
        self.archive.chmod(0o644)
        body = bytearray(self.archive.read_bytes())
        body[-1] ^= 0xFF
        self.archive.write_bytes(body)
        self.archive.chmod(0o444)
        with self.assertRaisesRegex(ValueError, "decoder failed"):
            self.run_decode()
        self.failure()

    def test_non_sqlite_content_never_published(self):
        self.archive.chmod(0o644)
        self.archive.write_bytes(zstandard.ZstdCompressor().compress(b"not a SQLite file at all"))
        self.archive.chmod(0o444)
        with self.assertRaisesRegex(ValueError, "not a SQLite"):
            self.run_decode()
        self.failure()

    def test_wrong_compressed_hash_stops_before_child(self):
        with self.assertRaisesRegex(ValueError, "source hash"):
            self.run_decode(expected_sha256="0" * 64)
        self.assertIsNone(self.failure()["decoder_pid"])

    def test_wrong_binary_never_claimed(self):
        with self.assertRaisesRegex(ValueError, "decoder hash"):
            self.run_decode(expected_decoder_sha256="0" * 64)
        self.assertFalse((self.root / "decode").exists())

    def test_duplicate_run_id_preserved(self):
        self.run_decode()
        before = (self.root / "decode/result.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_decode()
        self.assertEqual(before, (self.root / "decode/result.json").read_bytes())

    def test_busy_cooperative_device_lock_refuses(self):
        lock = self.root / f".sqlite-decode-device-{self.root.stat().st_dev}.lock"
        with lock.open("w") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.run_decode()
        self.assertIsNone(self.failure()["decoder_pid"])

    def test_tiny_deadline_does_not_claim_success(self):
        with self.assertRaises(TimeoutError):
            self.run_decode(max_seconds=0.000001)
        self.failure()


if __name__ == "__main__":
    unittest.main()
