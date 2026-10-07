"""Price launches are mocked; real subprocess checks only show help/list tests."""
from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from market_rsi import cli, checks


class CommandTests(unittest.TestCase):
    def test_check_delegates_options_and_exit_status(self):
        with mock.patch.object(checks, "main", return_value=7) as run:
            self.assertEqual(cli.main(["check", "--suite", "price", "--list", "--verbose"]), 7)
        run.assert_called_once_with(["--suite", "price", "--list", "--verbose"])

    def test_check_listing_does_not_start_a_child(self):
        with mock.patch.object(cli.subprocess, "run") as run, redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(["check", "--list"]), 0)
        run.assert_not_called()
        self.assertEqual(out.getvalue().splitlines(), list(checks.SUITES["smoke"]))

    def test_price_delegates_current_interpreter_cwd_and_arguments_once(self):
        argv = ["price", "--batch-config", "config file.json",
                "--initial-feedback", "feedback file.json", "--preflight"]
        before = dict(os.environ)
        with mock.patch.object(cli.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
            self.assertEqual(cli.main(argv), 0)
        run.assert_called_once_with(
            [sys.executable, "-B", "-m", "supervisor_harness.run_price_discovery",
             "--batch-config", str(Path("config file.json").absolute()),
             "--initial-feedback", str(Path("feedback file.json").absolute()), "--preflight"],
            cwd=checks.PROJECT_ROOT, check=False,
        )
        self.assertEqual(before, dict(os.environ))

    def test_price_preserves_absolute_inputs_and_failure_without_retry(self):
        for status, expected in ((1, 1), (7, 7), (-15, 143)):
            with self.subTest(status=status), mock.patch.object(
                cli.subprocess, "run", return_value=mock.Mock(returncode=status)
            ) as run:
                self.assertEqual(cli.main(["price", "--batch-config", "/tmp/config.json",
                                          "--initial-feedback", "/tmp/feedback.json"]), expected)
                self.assertEqual(run.call_args.args[0][-4:],
                                 ["--batch-config", "/tmp/config.json",
                                  "--initial-feedback", "/tmp/feedback.json"])
                run.assert_called_once()

    def test_uncertain_price_launch_is_not_retried(self):
        with mock.patch.object(cli.subprocess, "run", side_effect=OSError("cannot launch")) as run:
            with self.assertRaises(OSError):
                cli.main(["price", "--batch-config", "a.json", "--initial-feedback", "b.json"])
        run.assert_called_once()

    def test_price_does_not_resolve_caller_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            link = Path(directory) / "config.json"
            link.symlink_to(Path(directory) / "missing-original.json")
            with mock.patch.object(cli.subprocess, "run", return_value=mock.Mock(returncode=1)) as run:
                cli.main(["price", "--batch-config", str(link), "--initial-feedback", "b.json"])
            self.assertEqual(run.call_args.args[0][5], str(link))

    def test_missing_or_unknown_arguments_fail_before_launch(self):
        cases = ([], ["unknown"], ["check", "--suite", "live"], ["price"],
                 ["price", "--batch-config", "a", "--initial-feedback", "b", "--retry"])
        for argv in cases:
            with self.subTest(argv=argv), mock.patch.object(cli.subprocess, "run") as run:
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    cli.main(argv)
                self.assertEqual(error.exception.code, 2)
                run.assert_not_called()

    def test_price_help_does_not_launch(self):
        with mock.patch.object(cli.subprocess, "run") as run, redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                cli.main(["price", "--help"])
        self.assertEqual(error.exception.code, 0)
        run.assert_not_called()

    def test_module_and_compatibility_listing_work_from_another_cwd(self):
        environment = checks.test_environment()
        environment["PYTHONPATH"] = str(checks.CHECKOUT_ROOT)
        commands = (
            [sys.executable, "-B", "-m", "market_rsi", "check", "--suite", "price", "--list"],
            [sys.executable, "-B", str(checks.CHECKOUT_ROOT / "tools" / "check.py"),
             "--suite", "price", "--list"],
        )
        with tempfile.TemporaryDirectory() as directory:
            for command in commands:
                with self.subTest(command=command):
                    result = subprocess.run(command, cwd=directory, env=environment,
                                            text=True, capture_output=True, timeout=10, check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.splitlines(), list(checks.SUITES["price"]))


if __name__ == "__main__":
    unittest.main()
