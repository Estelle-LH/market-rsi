from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from controller_activity_log import append_activity, verify_activity_log
from market_rsi import canonical


class ControllerActivityLogTests(unittest.TestCase):
    def test_append_and_verify_hash_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "activity.jsonl"
            first = append_activity(path, {"kind": "searched", "query": "calibration"})
            second = append_activity(path, {"kind": "candidate", "source_sha256": "a" * 64})
            assessment = verify_activity_log(path)
            self.assertEqual(assessment["records"], 2)
            self.assertEqual(second["previous_record_sha256"], first["record_sha256"])

    def test_mutation_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "activity.jsonl"
            append_activity(path, {"kind": "searched", "query": "calibration"})
            record = json.loads(path.read_text())
            record["event"]["query"] = "changed"
            path.write_text(canonical(record) + "\n")
            with self.assertRaisesRegex(ValueError, "hash chain changed"):
                verify_activity_log(path)

    def test_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.jsonl"
            target.write_text("")
            link = root / "activity.jsonl"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlinked"):
                verify_activity_log(link)


if __name__ == "__main__":
    unittest.main()
