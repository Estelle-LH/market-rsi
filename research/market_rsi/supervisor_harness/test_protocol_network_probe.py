"""Offline protocol-probe tests; no E2B network claim is made here."""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from supervisor_harness import protocol_network_probe as probe


PUBLIC = "https://example.org/public-canary"
PEER = "https://3000-peer-sandbox.e2b.app/marker"
MARKER = hashlib.sha256(b"peer-canary-marker").hexdigest()


def failure():
    return {"http_response": False, "status": None, "body_sha256": None,
            "body_truncated": False, "error_type": "URLError"}


def response(body: bytes, status: int = 200):
    return {"http_response": True, "status": status,
            "body_sha256": hashlib.sha256(body).hexdigest(),
            "body_truncated": False, "error_type": None}


def report(public=None, peer=None):
    return {"schema": probe.SCHEMA,
            "url_sha256": {"public": probe._sha(PUBLIC), "peer": probe._sha(PEER)},
            "observations": {
                "public": {"environment_proxy": (public or failure()),
                           "direct_no_proxy": failure()},
                "peer": {"environment_proxy": (peer or failure()),
                         "direct_no_proxy": failure()}}}


class ProbeTests(unittest.TestCase):
    def test_both_roles_urls_get_proxy_and_direct_attempts(self):
        with patch.object(probe, "_bounded_get", return_value=failure()) as get:
            value = probe.observe(PUBLIC, PEER)
        self.assertEqual(get.call_count, 4)
        self.assertEqual({(call.args[0], call.kwargs["direct"]) for call in get.call_args_list},
                         {(PUBLIC, False), (PUBLIC, True), (PEER, False), (PEER, True)})
        self.assertEqual(value["url_sha256"]["peer"], probe._sha(PEER))

    def test_each_attempt_has_atomic_start_and_complete_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            prefix = Path(temp) / "progress"
            output = io.StringIO()
            with patch.object(probe, "_bounded_get", side_effect=[
                    failure(), response(b"public"), failure(),
                    response(b"peer-canary-marker")]) as get, redirect_stdout(output):
                final = probe.observe(PUBLIC, PEER, progress_prefix=prefix)
            self.assertEqual(get.call_count, 4)
            receipts = []
            for index in range(4):
                for phase in ("start", "complete"):
                    path = probe.progress_path(prefix, index, phase)
                    self.assertTrue(path.is_file())
                    receipts.append(json.loads(path.read_text()))
            self.assertEqual([json.loads(line) for line in output.getvalue().splitlines()],
                             receipts)
            self.assertNotIn(PUBLIC, output.getvalue())
            self.assertNotIn(PEER, output.getvalue())
            self.assertNotIn("peer-canary-marker", output.getvalue())
            self.assertEqual(final["observations"]["peer"]["direct_no_proxy"],
                             response(b"peer-canary-marker"))
            partial = probe.review_progress(
                receipts, public_url=PUBLIC, peer_url=PEER,
                peer_marker_sha256=MARKER)
            self.assertTrue(partial["all_four_completed"])
            self.assertTrue(partial["public_http_response_observed"])
            self.assertTrue(partial["peer_marker_observed"])
            self.assertFalse(partial["isolation_proven"])

    def test_interrupted_attempt_preserves_prior_receipts_without_negative_verdict(self):
        with tempfile.TemporaryDirectory() as temp:
            prefix = Path(temp) / "progress"
            output = io.StringIO()
            with patch.object(probe, "_bounded_get", side_effect=[
                    failure(), TimeoutError("interrupted")]), redirect_stdout(output):
                with self.assertRaises(TimeoutError):
                    probe.observe(PUBLIC, PEER, progress_prefix=prefix)
            receipts = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual([(item["index"], item["phase"]) for item in receipts],
                             [(0, "start"), (0, "complete"), (1, "start")])
            self.assertFalse(probe.progress_path(prefix, 1, "complete").exists())
            partial = probe.review_progress(
                receipts, public_url=PUBLIC, peer_url=PEER,
                peer_marker_sha256=MARKER)
            self.assertEqual(partial["attempts_started"], [0, 1])
            self.assertEqual(partial["attempts_completed"], [0])
            self.assertFalse(partial["all_four_completed"])
            self.assertFalse(partial["public_http_response_observed"])
            self.assertFalse(partial["isolation_proven"])

    def test_progress_review_rejects_forged_or_missing_start(self):
        start = {"schema": probe.PROGRESS_SCHEMA, "phase": "start", "index": 0,
                 "label": "public", "mode": "environment_proxy",
                 "url_sha256": {"public": probe._sha(PUBLIC),
                                "peer": probe._sha(PEER)}}
        complete = {**start, "phase": "complete", "observation": response(b"ok")}
        kwargs = {"public_url": PUBLIC, "peer_url": PEER,
                  "peer_marker_sha256": MARKER}
        for receipts in ([complete], [start, start],
                         [start, {**complete, "url_sha256": {**start["url_sha256"],
                                                              "peer": "0" * 64}}],
                         [start, {**complete, "observation": {
                             **response(b"ok"), "body_sha256": "z" * 64}}]):
            with self.subTest(receipts=receipts), self.assertRaises(ValueError):
                probe.review_progress(receipts, **kwargs)

    def test_existing_progress_receipt_stops_before_network(self):
        with tempfile.TemporaryDirectory() as temp:
            prefix = Path(temp) / "progress"
            probe.progress_path(prefix, 2, "complete").write_text("old")
            with patch.object(probe, "_bounded_get") as get, self.assertRaises(FileExistsError):
                probe.observe(PUBLIC, PEER, progress_prefix=prefix)
            get.assert_not_called()

    def test_bounded_get_uses_child_deadline_and_validates_result(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(failure()).encode(), stderr=b"")
        with patch.object(probe.subprocess, "run", return_value=completed) as run:
            item = probe._bounded_get(PEER, direct=False)
        self.assertEqual(item, failure())
        args, kwargs = run.call_args
        self.assertEqual(args[0][:3], [sys.executable, "-I", str(Path(probe.__file__).resolve())])
        self.assertEqual(args[0][3:], ["--single-get", PEER, "environment_proxy"])
        self.assertEqual(kwargs["timeout"], probe.ATTEMPT_WALL_TIMEOUT_SECONDS)
        self.assertIs(kwargs["stdout"], subprocess.PIPE)
        self.assertIs(kwargs["stderr"], subprocess.PIPE)

    def test_deadline_is_inconclusive_in_progress_and_final_review(self):
        timeout = {"http_response": False, "status": None, "body_sha256": None,
                   "body_truncated": False, "error_type": "AttemptDeadlineExpired"}
        with patch.object(probe.subprocess, "run", side_effect=subprocess.TimeoutExpired(
                cmd=["python3"], timeout=probe.ATTEMPT_WALL_TIMEOUT_SECONDS)):
            self.assertEqual(probe._bounded_get(PEER, direct=False), timeout)
        with tempfile.TemporaryDirectory() as temp:
            output = io.StringIO()
            with patch.object(probe, "_bounded_get", side_effect=[
                    failure(), failure(), timeout, failure()]), redirect_stdout(output):
                value = probe.observe(PUBLIC, PEER, progress_prefix=Path(temp) / "progress")
            receipts = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(len(receipts), 8)
            partial = probe.review_progress(receipts, public_url=PUBLIC, peer_url=PEER,
                                            peer_marker_sha256=MARKER)
            self.assertEqual(partial["attempts_timed_out"], [2])
            self.assertTrue(partial["all_four_completed"])
            with self.assertRaisesRegex(ValueError, "wall-deadline"):
                probe.review(value, public_url=PUBLIC, peer_url=PEER,
                             peer_marker_sha256=MARKER)

    def test_bounded_child_failure_or_invalid_output_fails_closed(self):
        for child in (subprocess.CompletedProcess([], 1, b"", b""),
                      subprocess.CompletedProcess([], 0, b"not-json", b""),
                      subprocess.CompletedProcess([], 0, b"x" * 1025, b""),
                      subprocess.CompletedProcess([], 0, json.dumps(failure()).encode(),
                                                  b"unexpected stderr")):
            with self.subTest(child=child), patch.object(probe.subprocess, "run",
                                                        return_value=child):
                with self.assertRaises(RuntimeError):
                    probe._bounded_get(PUBLIC, direct=True)

    def test_single_get_child_mode_emits_one_bounded_observation(self):
        output = io.StringIO()
        with (patch.object(sys, "argv", ["probe.py", "--single-get", PEER,
                                        "direct_no_proxy"]),
              patch.object(probe, "_one_get", return_value=failure()) as get,
              redirect_stdout(output)):
            probe.main()
        get.assert_called_once_with(PEER, direct=True)
        self.assertEqual(json.loads(output.getvalue()), failure())

    def test_http_error_is_a_response_not_a_block(self):
        error = HTTPError(PUBLIC, 403, "Forbidden", {}, io.BytesIO(b"gateway"))
        with patch.object(probe, "build_opener", return_value=SimpleNamespace(
                open=lambda *args, **kwargs: (_ for _ in ()).throw(error))):
            item = probe._one_get(PUBLIC, direct=True)
        self.assertTrue(item["http_response"])
        self.assertEqual(item["status"], 403)
        self.assertEqual(item["body_sha256"], hashlib.sha256(b"gateway").hexdigest())

    def test_connection_error_is_not_called_application_response(self):
        with patch.object(probe, "build_opener", return_value=SimpleNamespace(
                open=lambda *args, **kwargs: (_ for _ in ()).throw(URLError("blocked")))):
            item = probe._one_get(PUBLIC, direct=False)
        self.assertFalse(item["http_response"])
        self.assertEqual(item["error_type"], "URLError")

    def test_review_never_claims_isolation_and_detects_marker(self):
        blocked = probe.review(report(), public_url=PUBLIC, peer_url=PEER,
                               peer_marker_sha256=MARKER)
        self.assertFalse(blocked["public_http_response_observed"])
        self.assertFalse(blocked["isolation_proven"])
        reached = probe.review(report(public=response(b"public"),
                                      peer=response(b"peer-canary-marker")),
                               public_url=PUBLIC, peer_url=PEER,
                               peer_marker_sha256=MARKER)
        self.assertTrue(reached["public_http_response_observed"])
        self.assertTrue(reached["peer_marker_observed"])
        self.assertFalse(reached["isolation_proven"])

    def test_rejects_changed_url_or_missing_mode(self):
        value = report()
        with self.assertRaises(ValueError):
            probe.review(value, public_url=PUBLIC + "-changed", peer_url=PEER,
                         peer_marker_sha256=MARKER)
        del value["observations"]["peer"]["direct_no_proxy"]
        with self.assertRaises(ValueError):
            probe.review(value, public_url=PUBLIC, peer_url=PEER,
                         peer_marker_sha256=MARKER)
        corrupt = report(public={**response(b"public"), "body_sha256": "z" * 64})
        with self.assertRaises(ValueError):
            probe.review(corrupt, public_url=PUBLIC, peer_url=PEER,
                         peer_marker_sha256=MARKER)

    def test_rejects_credentials_or_non_https(self):
        for value in ("http://example.org/", "https://user:pass@example.org/",
                      "https://example.org:444/", "https://example.org/#fragment"):
            with self.subTest(url=value), self.assertRaises(ValueError):
                probe._url(value)


if __name__ == "__main__":
    unittest.main()
