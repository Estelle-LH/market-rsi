import ast
import unittest
from decimal import Decimal

from e2b_coder_probe import (EXECUTION_COMMAND, HARNESS, RATES, TIMEOUT, UPPER_USD,
                             REQUIRED_CHECKS, assessment_passes, require_passed)


class E2BProbeTests(unittest.TestCase):
    def test_os_network_namespace_and_unprivileged_execution(self):
        self.assertEqual(EXECUTION_COMMAND,
            "unshare --net -- setpriv --reuid=65534 --regid=65534 --clear-groups --no-new-privs -- python3 -I /tmp/check.py")
        self.assertIn('"unprivileged_uid"', HARNESS)
        self.assertIn('"only_loopback_interface"', HARNESS)
        self.assertIn("socket.if_nameindex()", HARNESS)
        self.assertNotIn('os.listdir("/sys/class/net")', HARNESS)
        ast.parse(HARNESS)

    def test_published_maximum_resources_fit_reservation(self):
        maximum = TIMEOUT * (8 * Decimal(RATES["vcpu_second"])
                            + 8 * Decimal(RATES["gib_second"]))
        self.assertLess(maximum, Decimal(UPPER_USD))

    def test_every_boundary_check_is_required(self):
        report = dict.fromkeys(REQUIRED_CHECKS, True)
        self.assertTrue(assessment_passes(report, 0))
        for key in REQUIRED_CHECKS:
            for value in (False, "true", 1, None):
                self.assertFalse(assessment_passes({**report, key: value}, 0))
            self.assertFalse(assessment_passes({k: v for k, v in report.items() if k != key}, 0))
        self.assertFalse(assessment_passes(report, 1))
        self.assertFalse(assessment_passes(report, False))

    def test_failed_assessment_raises_instead_of_successful_exit(self):
        require_passed({"passed": True})
        for value in (False, "true", 1, None):
            with self.assertRaisesRegex(ValueError, "assessment failed"):
                require_passed({"passed": value})

    def test_preserve_assessment_before_rejecting_with_cleanup_in_finally(self):
        import inspect
        import e2b_coder_probe
        source = inspect.getsource(e2b_coder_probe.main)
        self.assertLess(source.index('fresh_json(root / "assessment.json"'),
                        source.index("require_passed(report)"))
        self.assertIn("finally:", source)
        self.assertIn("sandbox.kill()", source)

    def test_failed_run_keeps_receipts_and_kills_exact_mock_sandbox(self):
        import json
        import tempfile
        from datetime import datetime, timezone
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch
        import e2b_coder_probe as probe

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            coder = root / "coder"
            coder.mkdir()
            (coder / "assessment.json").write_text(json.dumps({"passed": True}))
            (coder / "response.json").write_text(json.dumps({"code": "# fixture only"}))
            sandbox = MagicMock()
            sandbox.sandbox_id = "fixture-not-real-sandbox"
            sandbox.get_info.return_value = SimpleNamespace(template_id="fixture", cpu_count=2,
                memory_mb=512, started_at=datetime.now(timezone.utc),
                end_at=datetime.now(timezone.utc), envd_version="fixture", allow_internet_access=False)
            sandbox.commands.run.return_value = SimpleNamespace(exit_code=0, stdout="", stderr="")
            report = dict.fromkeys(REQUIRED_CHECKS, True)
            report["direct_ipv4_connection_blocked"] = False
            sandbox.files.read.return_value = json.dumps(report)
            sandbox.kill.return_value = True
            provider = MagicMock()
            provider.create.return_value = sandbox
            args = SimpleNamespace(output=root / "probe-failed", coder=coder,
                                   budget=root / "budget", env_file=root / "not-an-env-file")
            with patch.dict("sys.modules", {
                "e2b": SimpleNamespace(Sandbox=provider),
                "dotenv": SimpleNamespace(dotenv_values=lambda _: {"E2B_API_KEY": "fixture-not-a-key"})
            }), patch.object(probe, "PaidBudget"), patch("builtins.print"):
                with self.assertRaisesRegex(ValueError, "assessment failed"):
                    probe.main(args)
            sandbox.kill.assert_called_once_with()
            self.assertFalse(json.loads((args.output / "assessment.json").read_text())["passed"])
            self.assertTrue(json.loads((args.output / "cleanup.json").read_text())["kill_acknowledged"])
            self.assertTrue((args.output / "failure.json").exists())


if __name__ == "__main__":
    unittest.main()
