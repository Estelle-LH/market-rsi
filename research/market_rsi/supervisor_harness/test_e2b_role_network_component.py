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
    def __init__(self, *, progress_read_fail=False):
        self.contents = {}
        self.progress_read_fail = progress_read_fail

    def write(self, path, value):
        self.contents[path] = value

    def read(self, path, *, request_timeout=None):
        if self.progress_read_fail and path.startswith(component.PROBE_PROGRESS_PREFIX):
            raise OSError("simulated progress read failure")
        return self.contents[path]


class Handle:
    pid = 1234

    def __init__(self):
        self.killed = False

    def kill(self):
        self.killed = True
        return True


class TimeoutException(Exception):
    pass


class Sandbox:
    def __init__(self, sandbox_id, *, public_response=False, wrong_marker=False,
                 source_timeout=False, source_timeout_at=(0, "start"),
                 progress_read_fail=False, progress_public_response=None,
                 deadline_in_report=False):
        self.sandbox_id = sandbox_id
        self.files = Files(progress_read_fail=progress_read_fail)
        self.commands = self
        self.handle = Handle()
        self.public_response = public_response
        self.progress_public_response = (public_response if progress_public_response is None
                                         else progress_public_response)
        self.wrong_marker = wrong_marker
        self.source_timeout = source_timeout
        self.source_timeout_at = source_timeout_at
        self.deadline_in_report = deadline_in_report
        self.calls = []

    def get_host(self, port):
        return f"{port}-{self.sandbox_id}.e2b.app"

    def run(self, command, *, timeout, background=False, on_stdout=None):
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
        progress_prefix = words[words.index("--progress-prefix") + 1]
        progress_lines = []
        for index, (label, mode, url) in enumerate((
                ("public", "environment_proxy", public_url),
                ("public", "direct_no_proxy", public_url),
                ("peer", "environment_proxy", peer_url),
                ("peer", "direct_no_proxy", peer_url))):
            for phase in ("start", "complete"):
                item = {"schema": "market_rsi_protocol_probe_progress_v1",
                        "phase": phase, "index": index, "label": label,
                        "mode": mode,
                        "url_sha256": {"public": probe._sha(public_url),
                                       "peer": probe._sha(peer_url)}}
                if phase == "complete":
                    item["observation"] = (
                        {**unavailable(), "error_type": "AttemptDeadlineExpired"}
                        if self.deadline_in_report and index == 2 else
                        {"http_response": True, "status": 403,
                         "body_sha256": hashlib.sha256(b"gateway").hexdigest(),
                         "body_truncated": False, "error_type": None}
                        if self.progress_public_response and index == 0 else unavailable())
                progress_lines.append(json.dumps(item) + "\n")
                self.files.write(f"{progress_prefix}-{index:02d}-{phase}.json",
                                 json.dumps(item))
                if self.source_timeout and (index, phase) == self.source_timeout_at:
                    if on_stdout is not None:
                        on_stdout(progress_lines[-1][:14])
                        on_stdout(progress_lines[-1][14:])
                    raise TimeoutException("stream deadline")
                if on_stdout is not None:
                    on_stdout(progress_lines[-1])
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
        if self.deadline_in_report:
            report["observations"]["peer"]["environment_proxy"] = {
                **unavailable(), "error_type": "AttemptDeadlineExpired"}
        self.files.write(output, json.dumps(report))
        return SimpleNamespace(exit_code=0, stderr="", stdout="".join(progress_lines))


class State:
    def snapshot(self):
        return {"active_cycle": "cycle-01"}


class RoleNetworkComponentTests(unittest.TestCase):
    def test_inconclusive_deadline_preserves_raw_report_but_not_observation(self):
        with tempfile.TemporaryDirectory() as temp:
            a = Sandbox("controller-A", deadline_in_report=True)
            b = Sandbox("researcher-B")
            root = Path(temp) / "a-to-b"
            with self.assertRaisesRegex(ValueError, "wall-deadline"):
                component.observe_direction(
                    source=a, target=b, state=State(), cycle_id="cycle-01",
                    public_url=PUBLIC, receipt_root=root)
            self.assertTrue((root / "raw-report.json").is_file())
            self.assertTrue((root / "report.json").is_file())
            self.assertFalse((root / "review.json").exists())
            self.assertFalse((root / "observation.json").exists())
            self.assertEqual(json.loads((root / "failure.json").read_text())["stage"],
                             "source_guest_report_review")
            self.assertTrue(b.handle.killed)

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
            self.assertTrue((root / "source-command-dispatch.json").is_file())
            self.assertEqual(len(json.loads((root / "source-command-progress.json").read_text())[
                "guest_claimed_milestones"]), 8)
            recovery = json.loads((root / "guest-progress-recovery.json").read_text())
            self.assertEqual(recovery["read_receipts"], 8)
            self.assertTrue(recovery["partial_review"]["all_four_completed"])
            self.assertFalse(recovery["complete_application_verdict"])
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

    def test_sdk_source_timeout_is_inconclusive_and_cleans_peer(self):
        with tempfile.TemporaryDirectory() as temp:
            a = Sandbox("controller-A", source_timeout=True)
            b = Sandbox("researcher-B")
            root = Path(temp) / "probe-a-to-b"
            with self.assertRaises(TimeoutException):
                component.observe_direction(
                    source=a, target=b, state=State(), cycle_id="cycle-01",
                    public_url=PUBLIC, receipt_root=root)
            failure = json.loads((root / "failure.json").read_text())
            self.assertEqual(failure["stage"], "source_command_run")
            self.assertEqual(failure["failure_domain"], "sdk_stream_timeout")
            self.assertFalse(failure["complete_report_receipt_written"])
            progress = json.loads((root / "source-command-progress.json").read_text())
            self.assertEqual(progress["guest_claimed_milestones"], [
                {"index": 0, "phase": "start", "label": "public",
                 "mode": "environment_proxy"}])
            self.assertIsNone(progress["application_verdict"])
            recovery = json.loads((root / "guest-progress-recovery.json").read_text())
            self.assertEqual(recovery["read_receipts"], 1)
            self.assertEqual(recovery["partial_review"]["attempts_started"], [0])
            self.assertEqual(recovery["partial_review"]["attempts_completed"], [])
            self.assertFalse(recovery["partial_review"]["all_four_completed"])
            self.assertFalse(recovery["complete_application_verdict"])
            self.assertTrue((root / "source-command-dispatch.json").is_file())
            self.assertFalse((root / "report.json").exists())
            self.assertFalse((root / "observation.json").exists())
            self.assertTrue(b.handle.killed)
            self.assertTrue(json.loads((root / "peer-process-cleanup.json").read_text())[
                "kill_acknowledged"])

    def test_timeout_retains_positive_partial_stdout_when_guest_read_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            a = Sandbox("controller-A", public_response=True, source_timeout=True,
                        source_timeout_at=(0, "complete"), progress_read_fail=True)
            b = Sandbox("researcher-B")
            root = Path(temp) / "probe-a-to-b"
            with self.assertRaises(TimeoutException):
                component.observe_direction(
                    source=a, target=b, state=State(), cycle_id="cycle-01",
                    public_url=PUBLIC, receipt_root=root)
            progress = json.loads((root / "source-command-progress.json").read_text())
            self.assertEqual(progress["partial_review"]["attempts_completed"], [0])
            self.assertTrue(progress["partial_review"]["public_http_response_observed"])
            self.assertIsNone(progress["application_verdict"])
            recovery = json.loads((root / "guest-progress-recovery.json").read_text())
            self.assertEqual(recovery["first_unavailable"]["error_type"], "OSError")
            self.assertFalse(recovery["complete_application_verdict"])
            self.assertTrue(b.handle.killed)
            self.assertFalse((root / "observation.json").exists())

    def test_positive_progress_cannot_be_erased_by_negative_final_report(self):
        with tempfile.TemporaryDirectory() as temp:
            a = Sandbox("controller-A", progress_public_response=True)
            b = Sandbox("researcher-B")
            root = Path(temp) / "probe-a-to-b"
            with self.assertRaisesRegex(RuntimeError, "forbidden application-level"):
                component.observe_direction(
                    source=a, target=b, state=State(), cycle_id="cycle-01",
                    public_url=PUBLIC, receipt_root=root)
            self.assertFalse(json.loads((root / "review.json").read_text())[
                "public_http_response_observed"])
            self.assertTrue(json.loads((root / "source-command-progress.json").read_text())[
                "partial_review"]["public_http_response_observed"])
            self.assertTrue(b.handle.killed)
            self.assertFalse((root / "observation.json").exists())

    def test_invalid_stdout_progress_cannot_hide_positive_completion(self):
        class CorruptingSandbox(Sandbox):
            def __init__(self, *args, corruption, **kwargs):
                super().__init__(*args, **kwargs)
                self.corruption = corruption

            def run(self, command, *, timeout, background=False, on_stdout=None):
                if on_stdout is not None and self.corruption != "extra":
                    original = on_stdout
                    first = False

                    def corrupt(line):
                        nonlocal first
                        if not first:
                            first = True
                            if self.corruption == "duplicate":
                                original(line)
                            else:
                                original("malformed progress line\n")
                        original(line)

                    on_stdout = corrupt
                result = super().run(command, timeout=timeout, background=background,
                                     on_stdout=on_stdout)
                if on_stdout is not None and self.corruption == "extra":
                    extra = self.files.contents[
                        f"{component.PROBE_PROGRESS_PREFIX}-00-complete.json"] + "\n"
                    on_stdout(extra)
                    return SimpleNamespace(exit_code=result.exit_code,
                                           stderr=result.stderr, stdout=result.stdout + extra)
                return result

        for corruption in ("duplicate", "malformed", "extra"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as temp:
                a = CorruptingSandbox(
                    "controller-A", corruption=corruption,
                    progress_public_response=True, progress_read_fail=True)
                b = Sandbox("researcher-B")
                root = Path(temp) / "probe-a-to-b"
                with self.assertRaisesRegex(RuntimeError, "guest progress evidence invalid"):
                    component.observe_direction(
                        source=a, target=b, state=State(), cycle_id="cycle-01",
                        public_url=PUBLIC, receipt_root=root)
                progress = json.loads((root / "source-command-progress.json").read_text())
                self.assertEqual(progress["review_error_type"] == "ValueError",
                                 corruption == "duplicate")
                self.assertGreater(progress["unrecognized_stdout_lines"], 0)
                self.assertEqual(json.loads((root / "failure.json").read_text())[
                    "error_type"], "InvalidGuestProgressReceipt")
                self.assertFalse((root / "observation.json").exists())
                self.assertTrue(b.handle.killed)

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
