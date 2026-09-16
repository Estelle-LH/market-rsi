import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sports_event_research.capture_sportsdataio_replay_canary import (
    AUTH_CONFIRMATION, AUTH_SCHEMA, ENDPOINT_SCHEMA, capture, load_endpoint,
    payload_observations,
)


class SportsDataIOReplayCanaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.endpoint = self.root / "endpoint.json"
        self.authorization = self.root / "authorization.json"
        self.url = "https://replay.sportsdata.io/v3/nfl/replay/json/PlayByPlay/42?format=json"
        self._write_private(self.endpoint, {"schema": ENDPOINT_SCHEMA, "url": self.url})
        endpoint_sha = __import__("hashlib").sha256(self.endpoint.read_bytes()).hexdigest()
        self._write_private(self.authorization, {
            "schema": AUTH_SCHEMA,
            "provider": "SportsDataIO",
            "authorization_source": "provider_account_terms",
            "operator_confirmation": AUTH_CONFIRMATION,
            "automated_replay_polling_allowed": True,
            "raw_research_storage_allowed": True,
            "authorized_endpoint_sha256": endpoint_sha,
            "approved_hosts": ["replay.sportsdata.io"],
            "confirmed_utc": "2026-09-16T12:00:00+00:00",
        })

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _write_private(path, value):
        path.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
        path.chmod(0o600)

    def _run(self, bodies, statuses=None):
        calls, statuses = [], statuses or [200] * len(bodies)
        iterator = iter(zip(statuses, bodies))

        def fetch(url, key, timeout, maximum_bytes):
            calls.append((url, key, timeout, maximum_bytes))
            status, body = next(iterator)
            return status, body, "application/json"

        wall = iter(range(1_000_000_000, 1_000_000_000 + 2 * len(bodies) + 2))
        mono = iter(range(10_000, 10_000 + 2 * len(bodies)))
        sleeps = []
        with patch.dict(os.environ, {"SPORTSDATAIO_API_KEY": "very-secret-key"}, clear=False):
            manifest = capture(self.root / "out", self.endpoint, self.authorization,
                3.0, len(bodies), 5.0, fetch=fetch, sleep=sleeps.append,
                wall_clock=lambda: next(wall), monotonic_clock=lambda: next(mono))
        return manifest, calls, sleeps

    def test_requires_explicit_polling_and_storage_authorization(self):
        value = json.loads(self.authorization.read_text())
        value["raw_research_storage_allowed"] = False
        self._write_private(self.authorization, value)
        with patch.dict(os.environ, {"SPORTSDATAIO_API_KEY": "secret"}, clear=False):
            with self.assertRaisesRegex(ValueError, "authorization"):
                capture(self.root / "out", self.endpoint, self.authorization, 3, 1, 5)
        self.assertFalse((self.root / "out").exists())

    def test_rejects_key_in_url_and_non_provider_host(self):
        self._write_private(self.endpoint, {
            "schema": ENDPOINT_SCHEMA,
            "url": "https://replay.sportsdata.io/nfl?key=secret",
        })
        with self.assertRaisesRegex(ValueError, "credentials"):
            load_endpoint(self.endpoint)
        self._write_private(self.endpoint, {
            "schema": ENDPOINT_SCHEMA,
            "url": "https://example.com/nfl",
        })
        with self.assertRaisesRegex(ValueError, "SportsDataIO"):
            load_endpoint(self.endpoint)

    def test_endpoint_and_authorization_files_must_be_private(self):
        self.endpoint.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "group/others"):
            load_endpoint(self.endpoint)

    def test_preserves_raw_bytes_local_clocks_and_never_persists_key_or_url(self):
        body = json.dumps({"Play": {"Created": "2026-09-16T00:00:00Z",
            "Updated": "2026-09-16T00:00:01Z", "IsOfficial": False}},
            separators=(",", ":")).encode()
        manifest, calls, sleeps = self._run([body])
        self.assertEqual((self.root / "out/raw/000001.bin").read_bytes(), body)
        receipt = json.loads((self.root / "out/receipts.jsonl").read_text())
        fields = json.loads((self.root / "out/field_observations.jsonl").read_text())
        self.assertIn("request_sent_unix_ns", receipt)
        self.assertIn("response_received_unix_ns", receipt)
        self.assertEqual(fields["clock_fields_verbatim"][0]["value"],
                         "2026-09-16T00:00:00Z")
        self.assertFalse(receipt["provider_publish_latency_computed"])
        self.assertFalse(manifest["provider_publish_latency_computed"])
        all_output = b"".join(path.read_bytes() for path in (self.root / "out").rglob("*")
                              if path.is_file())
        self.assertNotIn(b"very-secret-key", all_output)
        self.assertNotIn(self.url.encode(), all_output)
        self.assertEqual(len(calls), 1)
        self.assertEqual(sleeps, [])

    def test_counts_exact_duplicates_and_scheduled_polls(self):
        body = b'{"Sequence":1,"Clock":"12:00"}'
        manifest, calls, sleeps = self._run([body, body, b'{"Sequence":2,"Clock":"11:55"}'])
        self.assertEqual(manifest["summary"]["polls"], 3)
        self.assertEqual(manifest["summary"]["exact_duplicates"], 1)
        self.assertEqual(manifest["summary"]["unchanged_from_previous"], 1)
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [3.0, 3.0])

    def test_http_failure_is_preserved_then_stops_without_retry(self):
        manifest, calls, sleeps = self._run([b'{"error":"denied"}', b'{}'], [403, 200])
        self.assertEqual(manifest["summary"]["polls"], 1)
        self.assertEqual(manifest["summary"]["http_failures"], 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(sleeps, [])

    def test_provider_echo_of_key_is_never_persisted(self):
        def fetch(url, key, timeout, maximum_bytes):
            return 200, ("echo=" + key).encode(), "text/plain"
        with patch.dict(os.environ, {"SPORTSDATAIO_API_KEY": "very-secret-key"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "nothing persisted"):
                capture(self.root / "out", self.endpoint, self.authorization,
                    3, 1, 5, fetch=fetch)
        all_output = b"".join(path.read_bytes() for path in (self.root / "out").rglob("*")
                              if path.is_file())
        self.assertNotIn(b"very-secret-key", all_output)

    def test_json_escaped_session_url_is_never_persisted(self):
        escaped = self.url.replace("/", r"\/")
        def fetch(url, key, timeout, maximum_bytes):
            return 200, ('{"url":"' + escaped + '"}').encode(), "application/json; charset=utf-8"
        with patch.dict(os.environ, {"SPORTSDATAIO_API_KEY": "very-secret-key"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "nothing persisted"):
                capture(self.root / "out", self.endpoint, self.authorization,
                    3, 1, 5, fetch=fetch)
        all_output = b"".join(path.read_bytes() for path in (self.root / "out").rglob("*")
                              if path.is_file())
        self.assertNotIn(self.url.encode(), all_output)

    def test_bounds_are_hard(self):
        with patch.dict(os.environ, {"SPORTSDATAIO_API_KEY": "secret"}, clear=False):
            with self.assertRaisesRegex(ValueError, "poll interval"):
                capture(self.root / "out", self.endpoint, self.authorization, 2.99, 1, 5)
            with self.assertRaisesRegex(ValueError, "poll count"):
                capture(self.root / "out", self.endpoint, self.authorization, 3, 10001, 5)
            with self.assertRaisesRegex(ValueError, "duration"):
                capture(self.root / "out", self.endpoint, self.authorization,
                    60, 1000, 60, maximum_response_bytes=1)
            with self.assertRaisesRegex(ValueError, "raw output"):
                capture(self.root / "out", self.endpoint, self.authorization,
                    3, 129, 5, maximum_response_bytes=8 * 1024 * 1024)

    def test_observes_fields_but_does_not_assign_semantics(self):
        result = payload_observations({"Play": {"WallClock": "12:00", "Updated": "x",
            "Overturned": True, "Description": "pass"}})
        self.assertEqual({row["field_name"] for row in result["clock_fields_verbatim"]},
                         {"WallClock", "Updated"})
        self.assertEqual({row["field_name"] for row in result["correction_fields_verbatim"]},
                         {"Updated", "Overturned"})
        self.assertTrue(all("semantic_role" not in row
                            for rows in result.values() for row in rows))
        self.assertEqual(payload_observations({"Candidate": "x"})["clock_fields_verbatim"], [])


if __name__ == "__main__":
    unittest.main()
