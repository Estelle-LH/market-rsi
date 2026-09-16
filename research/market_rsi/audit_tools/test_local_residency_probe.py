"""Unit tests use mocked metadata only: no cloud or market content reads."""

import errno
from pathlib import Path
import runpy
import stat
from types import SimpleNamespace
import unittest
from unittest.mock import patch


PROBE = runpy.run_path(str(Path(__file__).with_name("local_residency_probe.py")))
inspect_path = PROBE["inspect_path"]
make_report = PROBE["make_report"]


def metadata(*, flags=0, mode=stat.S_IFREG | 0o444, flag_available=True):
    values = dict(st_mode=mode, st_size=123, st_mtime_ns=456)
    if flag_available:
        values["st_flags"] = flags
    return SimpleNamespace(**values)


class ResidencyProbeTests(unittest.TestCase):
    def test_resident_reads_no_content(self):
        with patch.object(Path, "lstat", return_value=metadata()), \
             patch.object(Path, "open", side_effect=AssertionError("no reads")):
            result = inspect_path(Path("resident.py"))
        self.assertEqual(result["status"], "resident_at_stat")

    def test_dataless_reads_no_content(self):
        with patch.object(Path, "lstat", return_value=metadata(flags=0x40000000)), \
             patch.object(Path, "open", side_effect=AssertionError("no hydration")):
            result = make_report(["remote.py"])
        self.assertEqual(result["counts"], {"dataless": 1})
        self.assertFalse(result["preflight_clear_at_stat"])

    def test_symlink_not_followed(self):
        with patch.object(Path, "lstat", return_value=metadata(mode=stat.S_IFLNK)):
            self.assertEqual(inspect_path(Path("link"))["status"], "symlink_not_followed")

    def test_missing(self):
        with patch.object(Path, "lstat", side_effect=FileNotFoundError):
            self.assertEqual(inspect_path(Path("absent"))["status"], "missing")

    def test_stat_error(self):
        with patch.object(Path, "lstat", side_effect=PermissionError(errno.EACCES, "denied")):
            result = inspect_path(Path("denied"))
        self.assertEqual(result["status"], "stat_error")
        self.assertEqual(result["errno"], errno.EACCES)

    def test_unsupported_flags_do_not_pass(self):
        with patch.object(Path, "lstat", return_value=metadata(flag_available=False)):
            self.assertFalse(make_report(["unknown"])["preflight_clear_at_stat"])

    def test_directory_does_not_pass(self):
        with patch.object(Path, "lstat", return_value=metadata(mode=stat.S_IFDIR)):
            self.assertEqual(inspect_path(Path("directory"))["status"], "not_regular")

    def test_deduplication_does_not_claim_integrity(self):
        with patch.object(Path, "lstat", return_value=metadata()):
            result = make_report(["a", "a", "b"])
        self.assertEqual(result["file_count"], 2)
        self.assertTrue(result["preflight_clear_at_stat"])
        for key in ("scientific_hashes_verified", "budget_reconciled", "raw_download_authorized"):
            self.assertFalse(result[key])
        self.assertEqual(result["content_bytes_read"], 0)

    def test_empty_does_not_pass(self):
        self.assertFalse(make_report([])["preflight_clear_at_stat"])


if __name__ == "__main__":
    unittest.main()
