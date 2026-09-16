from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from market_rsi import load_json
from memory_policy.study_v4 import cleanup_remote_cache


class StudyV4Tests(unittest.TestCase):
    def test_cleanup_is_exact_and_requires_local_transfer(self):
        calls = []

        def transport(command, **kwargs):
            calls.append(command)
            return SimpleNamespace(
                returncode=0,
                stdout='{"removed": true, "relative_parts": '
                       '["memory-policy-v4-20990101-01", "2099-01-01T00"]}',
            )

        with tempfile.TemporaryDirectory() as temp:
            cleanup_remote_cache(
                Path("memory-policy-v4-20990101-01"), "2099-01-01T00",
                Path(temp), transport=transport)
            value = load_json(Path(temp) / "remote-cleanup.json")
            self.assertTrue(value["complete"])
            self.assertTrue(value["local_transfer_verified_before_cleanup"])
            self.assertFalse(value["raw_source_deleted"])
            self.assertEqual(len(calls), 1)

    def test_cleanup_rejects_non_v4_or_broad_target(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                cleanup_remote_cache(Path("memory-policy-v3-20990101-01"),
                                     "2099-01-01T00", Path(temp))
            with self.assertRaises(ValueError):
                cleanup_remote_cache(Path("memory-policy-v4-20990101-01"),
                                     "../raw", Path(temp))


if __name__ == "__main__":
    unittest.main()
