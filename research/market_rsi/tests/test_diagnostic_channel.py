import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from diagnostic_channel import DiagnosticLineChannel, MAX_STDERR_BYTES, stderr_receipt
import sandbox_development_runner


class ChannelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.path = self.root / "candidate-stderr.log"
        self.channels = []

    def tearDown(self):
        for channel in self.channels:
            channel.close()
        self.tmp.cleanup()

    def channel(self, fixture):
        channel = DiagnosticLineChannel([sys.executable, "-I", "-c", fixture], self.root, self.path)
        self.channels.append(channel)
        return channel

    def test_warning_preserved_separately_from_prediction_protocol(self):
        channel = self.channel("import sys,json; r=json.loads(input()); print('fixture warning', file=sys.stderr, flush=True); print(json.dumps(r),flush=True)")
        self.assertEqual(channel.exchange({"x": 1}, 2), {"x": 1})
        channel.close()
        result = channel.diagnostic()
        self.assertEqual(result["text"], "fixture warning\n")
        self.assertEqual(result["origin"], "candidate_controlled_stderr")
        self.assertFalse(result["independent_diagnosis"])
        self.assertFalse(result["truncated"])
        self.assertEqual(channel.events[-1]["type"], "response")

    def test_import_error_keeps_original_candidate_traceback(self):
        channel = self.channel("import __rsi_nonexistent_fixture_package_0933")
        with self.assertRaises(ValueError):
            channel.exchange({"x": 1}, 2)
        channel.close()
        result = channel.diagnostic()
        self.assertIn("ModuleNotFoundError", result["text"])
        self.assertIn("__rsi_nonexistent_fixture_package_0933", result["text"])
        self.assertIsNotNone(channel.process.poll())

    def test_timeout_preserves_prior_diagnostic_and_reaps_exact_child(self):
        channel = self.channel("import sys,time; input(); print('entered fixture loop', file=sys.stderr,flush=True); time.sleep(30)")
        with self.assertRaises(TimeoutError):
            channel.exchange({"x": 1}, .25)
        channel.close()
        self.assertIn("entered fixture loop", channel.diagnostic()["text"])
        self.assertIsNotNone(channel.process.poll())

    def test_stderr_flood_uses_file_limit_not_an_unbounded_pipe_buffer(self):
        channel = self.channel("import resource,os; resource.setrlimit(resource.RLIMIT_FSIZE,(65536,65536)); os.write(2,b'x'*1000000)")
        with self.assertRaises(ValueError):
            channel.exchange({"x": 1}, 2)
        channel.close()
        result = channel.diagnostic()
        self.assertEqual(result["bytes"], 65536)
        self.assertEqual(len(result["text"]), 65536)

    def test_diagnostic_not_available_until_closed(self):
        channel = self.channel("input()")
        with self.assertRaises(ValueError):
            channel.diagnostic()

    def test_diagnostic_file_is_exclusive_and_private(self):
        self.channel("input()")
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        with self.assertRaises(FileExistsError):
            self.channel("input()")

    def test_invalid_utf8_marks_replacement_but_preserves_raw_bytes(self):
        self.path.write_bytes(b"\xff\x00fixture")
        value = stderr_receipt(self.path)
        self.assertIn("replace", value["encoding"])
        self.assertEqual(self.path.read_bytes(), b"\xff\x00fixture")
        self.assertEqual(value["bytes"], 9)

    def test_oversized_receipt_rejected_without_reading_all_bytes(self):
        with self.path.open("wb") as stream:
            stream.truncate(MAX_STDERR_BYTES + 1)
        with self.assertRaises(ValueError):
            stderr_receipt(self.path)

    def test_symlink_diagnostic_rejected(self):
        target = self.root / "other"
        target.write_text("fixture")
        self.path.symlink_to(target)
        with self.assertRaises(ValueError):
            stderr_receipt(self.path)

    def test_production_runner_refuses_execution_on_mac(self):
        with patch.object(sandbox_development_runner.sys, "platform", "darwin"):
            with self.assertRaisesRegex(RuntimeError, "never the Mac"):
                sandbox_development_runner.main()


if __name__ == "__main__":
    unittest.main()
