import json
from pathlib import Path
import tempfile
import unittest

from sports_event_research.capture_sportradar_push_canary import capture_lines, payload_summary


class SportradarPushCanaryTests(unittest.TestCase):
    def test_extracts_live_clock_and_correction_coverage(self):
        payload = {"game": {"id": "g", "status": "inprogress", "entry_mode": "LDE"},
                   "payload": {"event": {"id": "p", "type": "play", "clock": "12:00",
                                            "sequence": 3, "created_at": "2026-09-16T00:00:00Z",
                                            "updated_at": "2026-09-16T00:00:01Z",
                                            "wall_clock": "2026-09-16T00:00:00Z",
                                            "official": False}}}
        result = payload_summary(payload)
        self.assertEqual(result["play_objects"], 1)
        self.assertEqual(result["play_created_at"], 1)
        self.assertEqual(result["review_fields"], 1)
        self.assertEqual(result["entry_modes"], ["LDE"])
        self.assertEqual(result["game_ids"], ["g"])

    def test_capture_preserves_raw_bytes_and_separate_receive_receipt(self):
        body = json.dumps({"type": "play", "id": "p", "clock": "1:00", "sequence": 1,
                           "created_at": "2026-09-16T00:00:00Z"}, separators=(",", ":")).encode()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            times = iter([2_000_000_000])
            monotonic = iter([10])
            result = capture_lines([body + b"\n"], root / "raw.ndjson",
                                   root / "receipts.jsonl", 3,
                                   receive_clock=lambda: next(times),
                                   monotonic_clock=lambda: next(monotonic))
            self.assertEqual((root / "raw.ndjson").read_bytes(), body + b"\n")
            receipt = json.loads((root / "receipts.jsonl").read_text())
            self.assertNotIn("raw_json", receipt)
            self.assertEqual(receipt["local_receive_unix_ns"], 2_000_000_000)
            self.assertEqual(result["counts"]["messages"], 1)
            self.assertEqual(result["counts"]["play_created_at"], 1)

    def test_message_bound_is_hard(self):
        rows = [b'{"x":1}\n', b'{"x":2}\n']
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = capture_lines(rows, root / "raw.ndjson", root / "receipts.jsonl", 1)
            self.assertEqual(result["counts"]["messages"], 1)
            self.assertEqual(len((root / "receipts.jsonl").read_text().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
