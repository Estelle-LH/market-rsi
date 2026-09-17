"""Object-shaped role probes; never evidence of actual E2B isolation."""
from __future__ import annotations

import hashlib
import json
import shlex
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from supervisor_harness import e2b_role_network_component as component
from supervisor_harness import protocol_network_probe as probe


PUBLIC = "https://example.org/public-canary"


def unavailable():
    return {"http_response": False, "status": None, "body_sha256": None,
            "body_truncated": False, "error_type": "URLError"}


class Files:
    def __init__(self):
        self.contents = {}

    def write(self, path, value):
        self.contents[path] = value

    def read(self, path):
        return self.contents[path]


class Handle:
    pid = 1234

    def __init__(self):
        self.killed = False

    def kill(self):
        self.killed = True
        return True


class Sandbox:
    def __init__(self, sandbox_id, *, public_response=False, wrong_marker=False):
        self.sandbox_id = sandbox_id
        self.files = Files()
        self.commands = self
        self.handle = Handle()
        self.public_response = public_response
        self.wrong_marker = wrong_marker
        self.calls = []

    def get_host(self, port):
        return f"{port}-{self.sandbox_id}.e2b.app"

    def run(self, command, *, timeout, background=False):
        self.calls.append((command, timeout, background))
        if background:
            return self.handle
        if "--self-check" in command:
            marker = self.files.read(component.PEER_MARKER).encode()
            return SimpleNamespace(exit_code=0, stderr="", stdout=json.dumps({
                "schema": "market_rsi_peer_local_positive_v1",
                "port": component.PEER_PORT,
                "marker_sha256": hashlib.sha256(
                    b"wrong" if self.wrong_marker else marker).hexdigest(),
                "attempts": 1, "local_service_responded": True}))
        words = shlex.split(command)
        public_url = words[words.index("--public-url") + 1]
        peer_url = words[words.index("--peer-url") + 1]
        output = words[words.index("--output") + 1]
        report = {"schema": probe.SCHEMA,
                  "url_sha256": {"public": probe._sha(public_url),
                                 "peer": probe._sha(peer_url)},
                  "observations": {"public": {"environment_proxy": unavailable(),
                                              "direct_no_proxy": unavailable()},
                                   "peer": {"environment_proxy": unavailable(),
                                            "direct_no_proxy": unavailable()}}}
        if self.public_response:
            report["observations"]["public"]["environment_proxy"] = {
                "http_response": True, "status": 403,
                "body_sha256": hashlib.sha256(b"gateway").hexdigest(),
                "body_truncated": False, "error_type": None}
        self.files.write(output, json.dumps(report))
        return SimpleNamespace(exit_code=0, stderr="", stdout="")


class State:
    def snapshot(self):
        return {"active_cycle": "cycle-01"}


class RoleNetworkComponentTests(unittest.TestCase):
    def test_both_directions_keep_separate_observations(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Sandbox("controller-A"), Sandbox("researcher-B")
            root = Path(temp)
            first = component.observe_direction(
                source=a, target=b, state=State(), cycle_id="cycle-01",
                public_url=PUBLIC, receipt_root=root / "a-to-b")
            second = component.observe_direction(
                source=b, target=a, state=State(), cycle_id="cycle-01",
                public_url=PUBLIC, receipt_root=root / "b-to-a")
            self.assertNotEqual(first["attempt_sha256"], second["attempt_sha256"])
            self.assertTrue(a.handle.killed and b.handle.killed)
            self.assertEqual([call[1] for call in a.calls if "--public-url" in call[0]],
                             [component.PROBE_COMMAND_TIMEOUT_SECONDS])
            self.assertEqual([call[1] for call in b.calls if "--public-url" in call[0]],
                             [component.PROBE_COMMAND_TIMEOUT_SECONDS])
            self.assertEqual(json.loads((root / "a-to-b/attempt.json").read_text())[
                "source_sandbox_id"], "controller-A")
            self.assertEqual(json.loads((root / "b-to-a/attempt.json").read_text())[
                "source_sandbox_id"], "researcher-B")

    def test_provisional_direction_has_local_positive_and_exact_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Sandbox("controller-A"), Sandbox("researcher-B")
            root = Path(temp) / "probe-a-to-b"
            result = component.observe_direction(
                source=a, target=b, state=State(), cycle_id="cycle-01",
                public_url=PUBLIC, receipt_root=root)
            self.assertFalse(result["isolation_proven"])
            self.assertTrue(result["no_forbidden_application_payload_observed"])
            self.assertTrue((root / "peer-local-positive.json").is_file())
            self.assertTrue(b.handle.killed)
            self.assertTrue((root / "peer-process-cleanup.json").is_file())
            self.assertNotIn(component.PEER_MARKER, a.files.contents)

    def test_public_application_response_fails_closed_after_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Sandbox("controller-A", public_response=True), Sandbox("researcher-B")
            root = Path(temp) / "probe-a-to-b"
            with self.assertRaisesRegex(RuntimeError, "forbidden application-level"):
                component.observe_direction(
                    source=a, target=b, state=State(), cycle_id="cycle-01",
                    public_url=PUBLIC, receipt_root=root)
            self.assertTrue(b.handle.killed)
            self.assertEqual(json.loads((root / "failure.json").read_text())[
                "error_type"], "ForbiddenApplicationChannelObserved")
            self.assertFalse((root / "observation.json").exists())

    def test_failed_local_positive_never_probes_source(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Sandbox("controller-A"), Sandbox("researcher-B", wrong_marker=True)
            root = Path(temp) / "probe-a-to-b"
            with self.assertRaisesRegex(ValueError, "positive control"):
                component.observe_direction(
                    source=a, target=b, state=State(), cycle_id="cycle-01",
                    public_url=PUBLIC, receipt_root=root)
            self.assertTrue(b.handle.killed)
            self.assertEqual(a.calls, [])
            self.assertTrue((root / "failure.json").is_file())

    def test_same_sandbox_rejected_before_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            a = Sandbox("same-id")
            root = Path(temp) / "probe-a-to-b"
            with self.assertRaisesRegex(ValueError, "distinct"):
                component.observe_direction(
                    source=a, target=a, state=State(), cycle_id="cycle-01",
                    public_url=PUBLIC, receipt_root=root)
            self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
