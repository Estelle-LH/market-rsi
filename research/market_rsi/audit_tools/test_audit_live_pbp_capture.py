import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from audit_live_pbp_capture import audit, distribution


def row(play_id="p1", mode="live_delta", seconds=2, **changes):
    value = {
        "record_type": "play",
        "observation_mode": mode,
        "event_id": "secret-game-id",
        "play_id": play_id,
        "provider_wallclock": "2026-01-01T00:00:00Z",
        "capture_received_utc": f"2026-01-01T00:00:0{seconds}Z",
        "http_rtt_ms": 125.0,
        "scoring_play": play_id == "p2",
    }
    value.update(changes)
    return value


class LivePbpCaptureAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "capture.jsonl.gz"

    def tearDown(self):
        self.temp.cleanup()

    def write(self, rows):
        with gzip.open(self.path, "wt", encoding="utf-8") as handle:
            for value in rows:
                handle.write(json.dumps(value, sort_keys=True) + "\n")
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def test_event_clock_is_not_strict_feed_latency(self):
        digest = self.write([row(), row("p2", seconds=4)])
        report = audit(self.path, digest, "post_hoc_existing_case")
        self.assertEqual(report["counts"]["live_delta_rows"], 2)
        self.assertEqual(
            report["provider_event_start_to_receive_descriptive_ms"]["p50"], 3000.0
        )
        self.assertTrue(
            report["claim_boundaries"]["raw_capture_mechanical_integrity_observed"]
        )
        self.assertFalse(report["claim_boundaries"]["capture_integrity_proven"])
        self.assertFalse(report["claim_boundaries"]["strict_feed_latency_proven"])
        self.assertFalse(report["claim_boundaries"]["market_lead_proven"])
        self.assertNotIn("secret-game-id", json.dumps(report))

    def test_publish_and_state_fields_are_counted_but_do_not_prove_market_lead(self):
        digest = self.write([row(
            provider_published_utc="2026-01-01T00:00:01Z",
            start_state={}, end_state={}, home_win_probability=0.5,
        )])
        report = audit(self.path, digest, "prospective_unopened_capture")
        self.assertTrue(report["clock_fields"]["provider_publish_clock_observed"])
        self.assertTrue(
            report["claim_boundaries"]["state_wp_delta_live_materialization_proven"]
        )
        self.assertFalse(report["claim_boundaries"]["market_lead_proven"])

    def test_source_hash_mismatch_is_rejected(self):
        self.write([row()])
        with self.assertRaises(ValueError):
            audit(self.path, "0" * 64, "post_hoc_existing_case")

    def test_empty_distribution(self):
        self.assertEqual(distribution([])["n"], 0)
        self.assertIsNone(distribution([])["p99"])


if __name__ == "__main__":
    unittest.main()
