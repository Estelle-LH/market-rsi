"""Public SYNTHETIC fixtures only; no Docker, network, sleeps, or threads."""

import hashlib
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from subprocess import TimeoutExpired
from unittest.mock import Mock, call, patch

import identity_diag as diag


CLI = "SYNTHETIC_CLI_INITIAL"
CONTEXT = "SYNTHETIC_CONTEXT_INITIAL"
DAEMON = "SYNTHETIC_DAEMON_INITIAL"
OTHER_CONTEXT = "SYNTHETIC_CONTEXT_CHANGED"
OTHER_DAEMON = "SYNTHETIC_DAEMON_CHANGED"
SECRET_ERROR = "SYNTHETIC_PRIVATE_ERROR_MESSAGE"


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class IdentityDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="synthetic-identity-test-", dir=Path(__file__).parent)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def runner(self, context=CONTEXT, daemon=DAEMON):
        self.context = context if isinstance(context, Mock) else Mock(return_value=context)
        self.daemon = daemon if isinstance(daemon, Mock) else Mock(return_value=daemon)
        return diag.IdentityDiagnostic(CLI, CONTEXT, DAEMON,
                                       self.context, self.daemon, self.directory)

    def receipt(self, path):
        return json.loads(path.read_text(encoding="ascii"))

    def assert_observers_once(self):
        self.context.assert_called_once_with(timeout_seconds=8)
        self.daemon.assert_called_once_with(timeout_seconds=8)

    def assert_no_raw_leakage(self):
        for path in self.directory.iterdir():
            self.assertNotIn("SYNTHETIC", path.name)
            text = path.read_text(encoding="ascii")
            for raw in (CLI, CONTEXT, DAEMON, OTHER_CONTEXT, OTHER_DAEMON, SECRET_ERROR):
                self.assertNotIn(raw, text)

    def test_stable_persists_hashes_and_cli_is_not_observed(self):
        runner = self.runner()
        path = runner.before_create()
        receipt = self.receipt(path)
        self.assertIs(receipt["passed"], True)
        self.assertEqual(receipt["result"], "STABLE")
        self.assertEqual(receipt["failures"], [])
        self.assertEqual(receipt["timeout_seconds"], 8)
        self.assertEqual(receipt["initial_hashes"],
                         {"cli": digest(CLI), "context": digest(CONTEXT), "daemon": digest(DAEMON)})
        self.assertEqual(receipt["observed_hashes"],
                         {"cli": None, "context": digest(CONTEXT), "daemon": digest(DAEMON)})
        self.assertEqual(receipt["observations"],
                         {"cli": "NOT_OBSERVED", "context": "MATCH", "daemon": "MATCH"})
        self.assert_observers_once()
        self.assert_no_raw_leakage()
        with self.assertRaises(FrozenInstanceError):
            runner.initial_hashes.context = digest(OTHER_CONTEXT)

    def test_each_drift_and_combined_drift_persist_before_raise(self):
        cases = ((OTHER_CONTEXT, DAEMON, ["CONTEXT_DRIFT"], "CONTEXT_DRIFT"),
                 (CONTEXT, OTHER_DAEMON, ["DAEMON_DRIFT"], "DAEMON_DRIFT"),
                 (OTHER_CONTEXT, OTHER_DAEMON, ["CONTEXT_DRIFT", "DAEMON_DRIFT"],
                  "CONTEXT_AND_DAEMON_DRIFT"))
        for context, daemon, failures, result in cases:
            with self.subTest(result=result):
                runner = self.runner(context, daemon)
                with self.assertRaises(diag.IdentityCheckError) as caught:
                    runner.before_create()
                receipt = self.receipt(caught.exception.receipt_path)
                self.assertEqual(list(caught.exception.codes), failures)
                self.assertEqual(receipt["failures"], failures)
                self.assertEqual(receipt["result"], result)
                self.assertIs(receipt["passed"], False)
                self.assertEqual(receipt["observed_hashes"]["context"], digest(context))
                self.assertEqual(receipt["observed_hashes"]["daemon"], digest(daemon))
                self.assert_observers_once()
        self.assert_no_raw_leakage()

    def test_each_timeout_keeps_observation_unknown_and_never_retries(self):
        for label in ("context", "daemon"):
            with self.subTest(label=label):
                timed_out = Mock(side_effect=TimeoutError(SECRET_ERROR))
                runner = self.runner(**{label: timed_out})
                with self.assertRaises(diag.IdentityCheckError) as caught:
                    runner.before_create()
                receipt = self.receipt(caught.exception.receipt_path)
                self.assertEqual(receipt["result"], label.upper() + "_TIMEOUT")
                self.assertIsNone(receipt["observed_hashes"][label])
                self.assertEqual(receipt["observations"][label], "TIMEOUT")
                other = "daemon" if label == "context" else "context"
                self.assertEqual(receipt["observations"][other], "MATCH")
                self.assert_observers_once()
        self.assert_no_raw_leakage()

    def assert_subprocess_timeout(self, label):
        private_output = b"SYNTHETIC_PRIVATE_TIMEOUT_STDOUT"
        private_stderr = b"SYNTHETIC_PRIVATE_TIMEOUT_STDERR"
        timeout = TimeoutExpired(cmd=SECRET_ERROR, timeout=8,
                                 output=private_output, stderr=private_stderr)
        self.assertIn(SECRET_ERROR, str(timeout))
        runner = self.runner(**{label: Mock(side_effect=timeout)})
        frozen = runner.initial_hashes
        fake_create = Mock()
        real_fsync = diag.os.fsync
        with patch("identity_diag.os.fsync", wraps=real_fsync) as synced:
            with self.assertRaises(diag.IdentityCheckError) as caught:
                runner.guarded_create(fake_create)
            self.assertEqual(synced.call_count, 2)
        fake_create.assert_not_called()
        self.assert_observers_once()
        self.assertIs(runner.initial_hashes, frozen)
        receipt = self.receipt(caught.exception.receipt_path)
        expected = label.upper() + "_TIMEOUT"
        self.assertEqual(caught.exception.codes, (expected,))
        self.assertEqual(receipt["result"], expected)
        self.assertEqual(receipt["failures"], [expected])
        self.assertIs(receipt["passed"], False)
        self.assertEqual(receipt["timeout_seconds"], 8)
        self.assertIsNone(receipt["observed_hashes"][label])
        self.assertEqual(receipt["observations"][label], "TIMEOUT")
        other = "daemon" if label == "context" else "context"
        self.assertEqual(receipt["observations"][other], "MATCH")
        self.assertEqual(receipt["observed_hashes"][other],
                         digest(DAEMON if other == "daemon" else CONTEXT))
        self.assertIsNone(receipt["observed_hashes"]["cli"])
        self.assertEqual(receipt["observations"]["cli"], "NOT_OBSERVED")
        self.assertEqual(receipt["initial_hashes"],
                         {"cli": digest(CLI), "context": digest(CONTEXT), "daemon": digest(DAEMON)})
        serialized = caught.exception.receipt_path.read_text(encoding="ascii")
        for private in (str(timeout), private_output.decode("ascii"), private_stderr.decode("ascii")):
            self.assertNotIn(private, serialized)
        self.assert_no_raw_leakage()

    def test_context_timeout_expired_is_persisted_as_timeout_and_blocks_create(self):
        self.assert_subprocess_timeout("context")

    def test_daemon_timeout_expired_is_persisted_as_timeout_and_blocks_create(self):
        self.assert_subprocess_timeout("daemon")

    def test_both_timeouts_and_timeout_plus_drift_remain_distinct(self):
        for daemon, expected in ((Mock(side_effect=TimeoutError(SECRET_ERROR)), "DAEMON_TIMEOUT"),
                                 (OTHER_DAEMON, "DAEMON_DRIFT")):
            runner = self.runner(context=Mock(side_effect=TimeoutError(SECRET_ERROR)), daemon=daemon)
            with self.assertRaises(diag.IdentityCheckError) as caught:
                runner.before_create()
            receipt = self.receipt(caught.exception.receipt_path)
            self.assertEqual(receipt["failures"], ["CONTEXT_TIMEOUT", expected])
            self.assertEqual(receipt["result"], "MULTIPLE_FAILURES")
            self.assertIsNone(receipt["observed_hashes"]["context"])
            self.assert_observers_once()

    def test_unexpected_errors_and_malformed_results_are_not_drift_or_timeout(self):
        for label in ("context", "daemon"):
            for observer in (Mock(side_effect=RuntimeError(SECRET_ERROR)),
                             Mock(return_value=None), Mock(return_value=42)):
                with self.subTest(label=label):
                    runner = self.runner(**{label: observer})
                    with self.assertRaises(diag.IdentityCheckError) as caught:
                        runner.before_create()
                    receipt = self.receipt(caught.exception.receipt_path)
                    self.assertEqual(receipt["failures"], [label.upper() + "_OBSERVER_ERROR"])
                    self.assertIsNone(receipt["observed_hashes"][label])
                    self.assertEqual(receipt["observations"][label], "ERROR")
                    self.assertNotIn(SECRET_ERROR, str(caught.exception))
                    self.assert_observers_once()
        self.assert_no_raw_leakage()

    def test_multiple_stable_checks_then_drift_never_refresh_baseline(self):
        runner = self.runner(context=Mock(side_effect=[CONTEXT, CONTEXT, OTHER_CONTEXT]))
        frozen = runner.initial_hashes
        first = runner.before_create()
        first_bytes = first.read_bytes()
        second = runner.before_create()
        with self.assertRaises(diag.IdentityCheckError) as caught:
            runner.before_create()
        third = caught.exception.receipt_path
        self.assertEqual(len({first, second, third}), 3)
        self.assertEqual(first.read_bytes(), first_bytes)
        self.assertIs(runner.initial_hashes, frozen)
        for path in (first, second, third):
            self.assertEqual(self.receipt(path)["initial_hashes"]["context"], digest(CONTEXT))
        self.assertEqual(self.receipt(third)["failures"], ["CONTEXT_DRIFT"])
        self.assertEqual(self.context.call_args_list, [call(timeout_seconds=8)] * 3)
        self.assertEqual(self.daemon.call_args_list, [call(timeout_seconds=8)] * 3)
        self.assertFalse(list(self.directory.glob("*.tmp")))
        self.assert_no_raw_leakage()

    def test_guarded_create_occurs_after_file_fsync_publication_and_directory_fsync(self):
        runner = self.runner()
        events = []
        real_fsync, real_link = diag.os.fsync, diag.os.link

        def fsync(fd):
            events.append("fsync")
            return real_fsync(fd)

        def link(source, target):
            events.append("publish")
            return real_link(source, target)

        def fake_create():
            self.assertEqual(events, ["fsync", "publish", "fsync"])
            receipts = list(self.directory.glob("*.json"))
            self.assertEqual(len(receipts), 1)
            self.assertIs(self.receipt(receipts[0])["passed"], True)
            events.append("SYNTHETIC_CREATE")
            return "SYNTHETIC_CREATED"

        with patch("identity_diag.os.fsync", side_effect=fsync), \
                patch("identity_diag.os.link", side_effect=link):
            self.assertEqual(runner.guarded_create(fake_create), "SYNTHETIC_CREATED")
        self.assertEqual(events[-1], "SYNTHETIC_CREATE")

    def test_create_never_called_on_any_observation_failure(self):
        cases = ((OTHER_CONTEXT, DAEMON), (CONTEXT, OTHER_DAEMON),
                 (OTHER_CONTEXT, OTHER_DAEMON),
                 (Mock(side_effect=TimeoutError(SECRET_ERROR)), DAEMON),
                 (CONTEXT, Mock(side_effect=TimeoutError(SECRET_ERROR))),
                 (Mock(side_effect=ValueError(SECRET_ERROR)), DAEMON),
                 (CONTEXT, Mock(side_effect=ValueError(SECRET_ERROR))))
        for context, daemon in cases:
            runner = self.runner(context, daemon)
            fake_create = Mock()
            with self.assertRaises(diag.IdentityCheckError):
                runner.guarded_create(fake_create)
            fake_create.assert_not_called()
            self.assert_observers_once()

    def test_persistence_failure_blocks_even_stable_create(self):
        for fsync_results in ([OSError(SECRET_ERROR)], [None, OSError(SECRET_ERROR)]):
            runner = self.runner()
            fake_create = Mock()
            with patch("identity_diag.os.fsync", side_effect=fsync_results):
                with self.assertRaises(diag.ReceiptPersistenceError) as caught:
                    runner.guarded_create(fake_create)
            fake_create.assert_not_called()
            self.assertNotIn(SECRET_ERROR, str(caught.exception))
            self.assert_observers_once()
        self.assertFalse(list(self.directory.glob("*.tmp")))
        self.assert_no_raw_leakage()

    def test_atomic_publication_failure_blocks_and_cleans_temporary(self):
        runner = self.runner()
        fake_create = Mock()
        with patch("identity_diag.os.link", side_effect=FileExistsError(SECRET_ERROR)):
            with self.assertRaises(diag.ReceiptPersistenceError):
                runner.guarded_create(fake_create)
        fake_create.assert_not_called()
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_persistence_failure_does_not_get_hidden_by_drift(self):
        runner = self.runner(OTHER_CONTEXT, OTHER_DAEMON)
        fake_create = Mock()
        with patch("identity_diag._persist_receipt", side_effect=OSError(SECRET_ERROR)) as persist:
            with self.assertRaises(diag.ReceiptPersistenceError):
                runner.guarded_create(fake_create)
        fake_create.assert_not_called()
        self.assertEqual(persist.call_count, 1)
        self.assertEqual(persist.call_args.args[1]["failures"], ["CONTEXT_DRIFT", "DAEMON_DRIFT"])
        self.assert_observers_once()


if __name__ == "__main__":
    unittest.main()
