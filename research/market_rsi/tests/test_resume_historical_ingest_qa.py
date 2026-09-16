from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_rsi import fresh_json
from resume_historical_ingest_qa import verify_stopped_source


class RawQAResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.previous = self.root / "previous"
        self.previous.mkdir()
        self.ingest = self.root / "ingest"
        self.ingest.mkdir()
        fresh_json(self.previous / "failure.json", {"error": "crossed PM quote"})
        fresh_json(self.previous / "watcher-process.json", {"pid": 123})
        fresh_json(self.ingest / "claim.json", {"plan_sha256": "frozen"})

    def tearDown(self):
        self.temp.cleanup()

    def check(self, *, alive=False, last_error="crossed PM quote", plan="frozen"):
        with patch("resume_historical_ingest_qa.os.kill",
                   side_effect=None if alive else ProcessLookupError), \
             patch("resume_historical_ingest_qa.read_controller_plan", return_value={"plan_sha256": plan}), \
             patch("resume_historical_ingest_qa.read_activity_events", return_value=[{"error": last_error}]):
            return verify_stopped_source(self.root / "session", self.ingest, self.previous)

    def test_exact_stopped_source_can_continue(self):
        self.assertEqual(self.check()["plan_sha256"], "frozen")

    def test_live_process_blocks(self):
        with self.assertRaisesRegex(ValueError, "still alive"):
            self.check(alive=True)

    def test_changed_plan_blocks(self):
        with self.assertRaisesRegex(ValueError, "claim differs"):
            self.check(plan="changed")

    def test_already_resumed_ledger_blocks(self):
        with self.assertRaisesRegex(ValueError, "no longer"):
            self.check(last_error=None)

    def test_completed_ingest_blocks(self):
        fresh_json(self.ingest / "completion.json", {})
        with self.assertRaisesRegex(ValueError, "completed ingest"):
            self.check()

    def test_partial_transfer_blocks(self):
        (self.ingest / "file.partial").touch()
        with self.assertRaisesRegex(ValueError, "partial file"):
            self.check()


if __name__ == "__main__":
    unittest.main()
