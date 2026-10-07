"""The developer entry selects tests only; all launches here are mocked."""
from contextlib import redirect_stdout, redirect_stderr
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from market_rsi import checks as check


class CheckRunnerTests(unittest.TestCase):
    def test_every_selected_module_exists_and_is_a_test(self):
        for name, modules in check.SUITES.items():
            with self.subTest(suite=name):
                self.assertEqual(len(modules), len(set(modules)))
                for module in modules:
                    self.assertTrue(module.split(".")[-1].startswith("test_"))
                    path = check.PROJECT_ROOT.joinpath(*module.split(".")).with_suffix(".py")
                    self.assertTrue(path.is_file(), str(path))
        self.assertTrue(set(check.SUITES["smoke"]).issubset(check.SUITES["price"]))

    def test_listing_does_not_launch_a_process(self):
        output = io.StringIO()
        with mock.patch.object(check.subprocess, "run") as run, redirect_stdout(output):
            self.assertEqual(check.main(["--suite", "price", "--list"]), 0)
        run.assert_not_called()
        self.assertEqual(output.getvalue().splitlines(), list(check.SUITES["price"]))

    def test_launch_uses_current_interpreter_and_resolved_project(self):
        with mock.patch.object(check.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
            self.assertEqual(check.main([]), 0)
        args, kwargs = run.call_args
        self.assertEqual(args[0], [sys.executable, "-B", "-m", "unittest", "-q",
                                   *check.SUITES["smoke"]])
        self.assertEqual(kwargs["cwd"], Path(check.__file__).resolve().parents[1] / "research" / "market_rsi")
        self.assertEqual(kwargs["timeout"], 300)
        self.assertIs(kwargs["check"], False)

    def test_verbose_launch_uses_the_requested_suite(self):
        with mock.patch.object(check.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
            self.assertEqual(check.main(["--suite", "price", "--verbose"]), 0)
        self.assertEqual(run.call_args.args[0][4:], ["-v", *check.SUITES["price"]])

    def test_environment_is_bounded_without_mutating_parent(self):
        with mock.patch.dict(os.environ, {"OMP_NUM_THREADS": "9", "CUSTOM_TEST_VALUE": "keep"}):
            before = dict(os.environ)
            environment = check.test_environment()
            self.assertEqual(dict(os.environ), before)
        self.assertEqual(environment["CUSTOM_TEST_VALUE"], "keep")
        for key in ("PYTHONDONTWRITEBYTECODE", "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
            self.assertEqual(environment[key], "1")

    def test_failure_exit_status_is_preserved_without_retry(self):
        with mock.patch.object(check.subprocess, "run", return_value=mock.Mock(returncode=7)) as run:
            self.assertEqual(check.run_suite("smoke"), 7)
        run.assert_called_once()

    def test_timeout_has_a_distinct_exit_status_without_retry(self):
        with mock.patch.object(check.subprocess, "run", side_effect=subprocess.TimeoutExpired("tests", 300)) as run:
            with redirect_stderr(io.StringIO()):
                self.assertEqual(check.run_suite("price"), 124)
        run.assert_called_once()

    def test_unknown_suite_is_rejected_before_launch(self):
        with mock.patch.object(check.subprocess, "run") as run, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                check.main(["--suite", "live"])
        self.assertEqual(raised.exception.code, 2)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
