"""Trusted human-authored local process fixtures; no Codex or provider calls."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from bounded_process import run_bounded_process
from coder_worker import CodexCLITransport, minimal_environment, run_bounded
from market_rsi import digest, file_hash, fresh_json
from test_coder_worker import LIMITS
from worker_receipts import Receipts, verify_coder_preflights


class DeadlineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def transport(self, seconds=5):
        transport = CodexCLITransport(self.root / "unused-fixture-pin.json")
        transport.bind_process_deadline(self.root, time.monotonic() + seconds)
        return transport

    def test_fresh_transport_required_for_each_job(self):
        transport = self.transport()
        with self.assertRaisesRegex(RuntimeError, "one permanent job"):
            transport.bind_process_deadline(self.root, time.monotonic() + 60)

    def test_readiness_requires_prior_deadline_before_pin_read(self):
        transport = CodexCLITransport(self.root / "missing.json")
        with self.assertRaisesRegex(RuntimeError, "bind one coding deadline"):
            transport.check_ready()

    def test_expired_preflight_creates_no_process(self):
        transport = self.transport(seconds=1)
        with patch("coder_worker.run_bounded_process") as dispatch:
            with self.assertRaises(TimeoutError):
                transport._readiness_command("version", ["unused-fixture"], {})
        dispatch.assert_not_called()

    def test_two_preflights_share_original_deadline_not_two_fresh_caps(self):
        transport = CodexCLITransport(self.root / "unused-fixture-pin.json")
        transport.bind_process_deadline(self.root, 105)
        clock, calls = [100], []

        def fixture_process(command, input_bytes, env, root, **limits):
            calls.append(limits)
            root.mkdir()
            (root / "stdout.bin").write_bytes(b"fixture-version\n")
            (root / "stderr.bin").write_bytes(b"")
            clock[0] = 104
            return {"failure": None, "exit_code": 0, "process_reaped": True}

        with patch("coder_worker.time.monotonic", side_effect=lambda: clock[0]), patch(
                "coder_worker.run_bounded_process", side_effect=fixture_process):
            transport._readiness_command("version", ["fixture", "--version"], {})
            with self.assertRaises(TimeoutError):
                transport._readiness_command("auth", ["fixture", "login", "status"], {})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["wall_seconds"], 3)

    def test_actual_trusted_preflight_timeout_kills_and_reaps_only_its_process(self):
        transport = self.transport(seconds=2.2)
        command = [sys.executable, "-I", "-c", "import time; time.sleep(3)"]
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            transport._readiness_command("version", command, minimal_environment(os.environ))
        receipt = json.loads((self.root / "version-process" / "receipt.json").read_text())
        self.assertTrue(receipt["process_reaped"])
        self.assertEqual(receipt["failure"], "local_wall_timeout")
        self.assertLess(receipt["elapsed_seconds"], 1.5)
        self.assertIsNone(receipt["remote_request_terminal"])

    def test_generation_after_expired_setup_does_not_start_a_process(self):
        with patch("coder_worker.subprocess.Popen") as dispatch:
            result = run_bounded(["unused-fixture"], "fixture", {}, self.root, LIMITS,
                deadline_monotonic=time.monotonic() - 1)
        dispatch.assert_not_called()
        self.assertEqual(result["failure_type"], "TimeoutError")
        self.assertFalse(result["process_reaped"])
        self.assertIsNone(result["exit_code"])

    def test_generation_uses_remaining_fraction_without_rounding_up(self):
        result = run_bounded([sys.executable, "-I", "-c", "import time; time.sleep(3)"],
            "fixture", minimal_environment(os.environ), self.root, LIMITS,
            deadline_monotonic=time.monotonic() + .15)
        self.assertTrue(result["process_reaped"])
        self.assertEqual(result["failure_type"], "TimeoutError")
        self.assertLess(result["elapsed_seconds"], 1)


class PreflightReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.identity = {"cli_path": "/human-fixture-not-executable", "cli_version": "fixture-version"}
        for operation, suffix, output in (
                ("version", ["--version"], b"fixture-version\n"),
                ("auth", ["login", "status"], b"Logged in using ChatGPT\n")):
            root = self.root / (operation + "-process")
            root.mkdir()
            for name, body in (("input", b""), ("stdout", output), ("stderr", b"")):
                (root / (name + ".bin")).write_bytes(body)
            fresh_json(root / "claim.json", {"command_sha256": digest([self.identity["cli_path"], *suffix]),
                "input_sha256": hashlib.sha256(b"").hexdigest(), "environment_names": ["HOME", "PATH"],
                "supervisor_source_sha256": file_hash(Path(__file__).parents[1] / "bounded_process.py"),
                "wall_seconds": 2, "reap_seconds": 2, "remote_cancellation_established": False,
                "max_stdout_bytes": 65536, "max_stderr_bytes": 65536})
            fresh_json(root / "receipt.json", {"pid": 123, "process_reaped": True, "exit_code": 0,
                "failure": None, "elapsed_seconds": .01, "input_bytes_written": 0,
                "output_complete": True, "input_complete": True, "remote_request_terminal": None,
                "remote_cancellation_established": False, "unused_budget_released": False,
                "stdout_bytes": len(output), "stderr_bytes": 0,
                "stdout_sha256": hashlib.sha256(output).hexdigest(),
                "stderr_sha256": hashlib.sha256(b"").hexdigest()})

    def tearDown(self):
        self.tmp.cleanup()

    def change(self, name, update):
        path = self.root / name
        value = json.loads(path.read_text())
        update(value)
        path.write_text(json.dumps(value))

    def test_independent_readback_and_mutation_detection(self):
        reads = Receipts()
        verify_coder_preflights(self.root, self.identity, LIMITS, reads)
        reads.revalidate()
        self.assertEqual(len(reads.files), 10)
        (self.root / "auth-process" / "stdout.bin").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            reads.revalidate()

    def test_provider_key_environment_name_is_rejected(self):
        self.change("auth-process/claim.json", lambda x: x.update(environment_names=["OPENAI_API_KEY"]))
        with self.assertRaisesRegex(ValueError, "command/environment/bounds"):
            verify_coder_preflights(self.root, self.identity, LIMITS, Receipts())

    def test_unreaped_preflight_is_not_a_verified_identity(self):
        self.change("auth-process/receipt.json", lambda x: x.update(process_reaped=False))
        with self.assertRaisesRegex(ValueError, "independently terminal"):
            verify_coder_preflights(self.root, self.identity, LIMITS, Receipts())

    def test_changed_command_cannot_verify_same_model_identity(self):
        self.change("version-process/claim.json", lambda x: x.update(command_sha256="a" * 64))
        with self.assertRaises(ValueError):
            verify_coder_preflights(self.root, self.identity, LIMITS, Receipts())

    def test_preflight_times_cannot_each_consume_whole_request(self):
        for operation in ("version", "auth"):
            self.change(operation + "-process/receipt.json", lambda x: x.update(elapsed_seconds=3))
        with self.assertRaisesRegex(ValueError, "exhausted original"):
            verify_coder_preflights(self.root, self.identity, LIMITS, Receipts())


if __name__ == "__main__":
    unittest.main()
