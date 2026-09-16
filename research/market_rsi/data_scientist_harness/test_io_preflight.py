from pathlib import Path
import stat
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from data_scientist_harness.io_preflight import inspect_paths,require_budget_resident


class IOTests(unittest.TestCase):
    def test_placeholder_rejected_without_reading(self):
        with patch.object(Path,"lstat",return_value=SimpleNamespace(st_mode=stat.S_IFREG,st_flags=0x40000000)),patch.object(Path,"read_bytes") as read:
            result=inspect_paths([Path("/fixture/receipt.json")])
            self.assertFalse(result["ready_for_content_checks"]);read.assert_not_called()
            self.assertEqual(result["failures"][0]["reason"],"cloud_placeholder_not_resident")

    def test_regular_file_metadata_is_not_proof(self):
        with patch.object(Path,"lstat",return_value=SimpleNamespace(st_mode=stat.S_IFREG,st_flags=0)):
            result=inspect_paths([Path("/fixture/receipt.json")])
            self.assertTrue(result["ready_for_content_checks"])
            self.assertFalse(result["integrity_verified"])

    def test_missing_budget_fails_before_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError,"no paid work"):require_budget_resident(root)

    def test_symlink_rejected(self):
        with patch.object(Path,"lstat",return_value=SimpleNamespace(st_mode=stat.S_IFLNK,st_flags=0)):
            self.assertFalse(inspect_paths(["/fixture/link"])["ready_for_content_checks"])


if __name__=="__main__":unittest.main()
