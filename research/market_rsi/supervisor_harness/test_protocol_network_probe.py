"""Offline protocol-probe tests; no E2B network claim is made here."""
from __future__ import annotations

import hashlib
import io
import unittest
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
        with patch.object(probe, "_one_get", return_value=failure()) as get:
            value = probe.observe(PUBLIC, PEER)
        self.assertEqual(get.call_count, 4)
        self.assertEqual({(call.args[0], call.kwargs["direct"]) for call in get.call_args_list},
                         {(PUBLIC, False), (PUBLIC, True), (PEER, False), (PEER, True)})
        self.assertEqual(value["url_sha256"]["peer"], probe._sha(PEER))

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
