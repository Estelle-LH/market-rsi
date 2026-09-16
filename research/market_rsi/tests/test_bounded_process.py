"""Real local subprocess checks with human-written harmless fixtures, no SDK."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

from bounded_process import run_bounded_process
from market_rsi import file_hash
from researcher_worker import GLMTransport


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.env = {"PATH": os.defpath, "LANG": "C.UTF-8"}

    def tearDown(self):
        self.tmp.cleanup()

    def run_fixture(self, source, data=b"", **limits):
        return run_bounded_process([sys.executable, "-I", "-c", source], data, self.env,
            self.root / "process", wall_seconds=limits.pop("wall_seconds", 3), **limits)

    def test_echo_input_and_exact_output_hashes_and_private_files(self):
        r = self.run_fixture("import sys; sys.stdout.buffer.write(sys.stdin.buffer.read()); sys.stderr.write('note')", b"public fixture")
        self.assertTrue(r["process_reaped"])
        self.assertTrue(r["input_complete"])
        self.assertEqual(r["exit_code"], 0)
        self.assertEqual(r["stdout_sha256"], file_hash(self.root / "process/stdout.bin"))
        self.assertEqual((self.root / "process/stdout.bin").read_bytes(), b"public fixture")
        self.assertEqual((self.root / "process/stdout.bin").stat().st_mode & 0o777, 0o600)
        self.assertFalse(r["remote_cancellation_established"])
        self.assertFalse(r["unused_budget_released"])
        self.assertIsNone(r["remote_request_terminal"])

    def test_hung_process_is_killed_reaped_and_not_called_remote_terminal(self):
        began = time.monotonic()
        r = self.run_fixture("import time; time.sleep(20)", wall_seconds=.15)
        self.assertLess(time.monotonic() - began, 2)
        self.assertEqual(r["failure"], "local_wall_timeout")
        self.assertTrue(r["process_reaped"])
        self.assertLess(r["exit_code"], 0)
        with self.assertRaises(ProcessLookupError):
            os.kill(r["pid"], 0)
        self.assertIsNone(r["remote_request_terminal"])

    def test_stdout_flood_preserves_bounded_prefix_and_marks_incomplete(self):
        r = self.run_fixture("import sys; sys.stdout.write('x'*100000)", max_stdout_bytes=128)
        self.assertEqual(r["failure"], "stdout_limit")
        self.assertEqual(r["stdout_bytes"], 128)
        self.assertFalse(r["output_complete"])
        self.assertTrue(r["process_reaped"])

    def test_stderr_flood_is_also_bounded(self):
        r = self.run_fixture("import sys; sys.stderr.write('x'*100000)", max_stderr_bytes=128)
        self.assertEqual(r["failure"], "stderr_limit")
        self.assertEqual(r["stderr_bytes"], 128)

    def test_bidirectional_large_pipes_do_not_deadlock(self):
        r = self.run_fixture("import sys; sys.stdout.write('x'*100000); sys.stdout.flush(); n=len(sys.stdin.buffer.read()); print(n)",
            b"z" * 262144, max_stdout_bytes=131072)
        self.assertEqual(r["exit_code"], 0)
        self.assertIsNone(r["failure"])
        self.assertTrue(r["input_complete"])
        self.assertTrue((self.root / "process/stdout.bin").read_bytes().endswith(b"262144\n"))

    def test_same_group_descendant_cannot_hold_pipe_after_parent_exit(self):
        source = "import os,time; pid=os.fork(); time.sleep(20) if pid == 0 else os._exit(0)"
        r = self.run_fixture(source, wall_seconds=2)
        self.assertEqual(r["exit_code"], 0)
        self.assertIsNone(r["failure"])
        self.assertLess(r["elapsed_seconds"], 1)

    def test_spawn_failure_still_has_receipt(self):
        r = run_bounded_process(["/definitely/missing/fixture-command"], b"", self.env,
                               self.root / "process", wall_seconds=1)
        self.assertEqual(r["failure"], "local_FileNotFoundError")
        self.assertFalse(r["process_reaped"])
        self.assertIsNone(r["pid"])

    def test_exclusive_receipt_directory_prevents_repeated_process(self):
        self.run_fixture("pass")
        with self.assertRaises(FileExistsError):
            self.run_fixture("raise RuntimeError('must not launch')")

    def test_env_values_are_not_written_to_claim_or_input(self):
        self.env["RSI_FIXTURE_SECRET"] = "FAKE_PRIVATE_VALUE_NOT_A_CREDENTIAL"
        self.run_fixture("pass")
        all_saved = b"".join(p.read_bytes() for p in (self.root / "process").iterdir())
        self.assertNotIn(self.env["RSI_FIXTURE_SECRET"].encode(), all_saved)
        self.assertIn(b"RSI_FIXTURE_SECRET", all_saved)

    def test_invalid_bounds_and_symlink_directory_rejected_before_spawn(self):
        for wall in (float('nan'), float('inf'), 0, True):
            with self.assertRaises(ValueError):
                self.run_fixture("pass", wall_seconds=wall)
        (self.root / "target").mkdir()
        (self.root / "process").symlink_to(self.root / "target", target_is_directory=True)
        with self.assertRaises(ValueError):
            self.run_fixture("pass")

    def test_glm_transport_requires_bound_dispatch_and_cannot_rebind(self):
        transport = GLMTransport("fake-not-a-credential", self.root / "absent-cache")
        with self.assertRaises(ValueError):
            transport.encode([])
        transport.bind_process_deadline(self.root / "job", time.monotonic() + 10)
        with self.assertRaises(ValueError):
            transport.bind_process_deadline(self.root / "job", time.monotonic() + 20)

    def test_actual_glm_subprocess_refuses_closed_admission_before_tokenizer_or_api(self):
        transport = GLMTransport("fake-not-a-credential", self.root / "absent-cache")
        transport.bind_process_deadline(self.root / "job", time.monotonic() + 10)
        with self.assertRaisesRegex(RuntimeError, "bounded provider operation failed"):
            transport.encode([{"role": "user", "content": "human admission test, no model call"}])
        directory = self.root / "job/encode-process"
        r = json.loads((directory / "receipt.json").read_text())
        self.assertTrue(r["process_reaped"])
        self.assertEqual(r["exit_code"], 1)
        self.assertEqual(json.loads((directory / "stderr.bin").read_text())["error_type"], "RuntimeError")
        self.assertNotIn("RSI_TINKER_API_KEY", (directory / "claim.json").read_text())
        self.assertFalse((self.root / "job/sample-process").exists())


if __name__ == "__main__":
    unittest.main()
