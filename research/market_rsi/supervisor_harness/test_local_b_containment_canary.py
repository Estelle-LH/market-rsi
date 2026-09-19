"""Offline fake-process checks for the synthetic local-B containment canary."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

from market_rsi import canonical, digest, load_json
from supervisor_harness import local_b_containment_canary as canary


class LocalBContainmentCanaryTests(unittest.TestCase):
    def setUp(self):
        self.cycle_id = "local-b-containment-" + uuid.uuid4().hex[:20]
        self.root = Path("/private/tmp") / (self.cycle_id + "-offline-test")
        self.assertFalse(self.root.exists())
        self.addCleanup(lambda: shutil.rmtree(self.root) if self.root.exists() else None)
        self.commands = []
        self.tamper = False
        self.inspect_error = False

    def fake_process(self, command, **options):
        self.commands.append(command)
        self.assertEqual(options, {"capture_output": True, "text": True,
                                   "timeout": canary.HOST_TIMEOUT_SECONDS,
                                   "check": False})
        self.assertEqual(command[command.index("--network") + 1], "none")
        self.assertEqual(command[command.index("--pull") + 1], "never")
        self.assertIn(canary.local_b_container.IMAGE, command)
        self.assertEqual(command.count("--mount"), 2)
        order = load_json(self.root / "order.json")
        event = {"schema": "market_local_b_containment_event_v1",
                 "cycle_id": self.cycle_id, "order_sha256": digest(order),
                 "public_text_sha256": hashlib.sha256(order["public_text"].encode()).hexdigest(),
                 "decoy_reads_denied": {name: True for name in canary.DECOYS},
                 "decoy_read_error_types": {name: "FileNotFoundError" for name in canary.DECOYS},
                 "root_write_denied": True, "root_write_error_type": "OSError",
                 "test_net_connect_denied": True, "test_net_error_type": "OSError",
                 "positive_work_write_and_read": True,
                 "synthetic_only": True, "model_authorship_proven": False,
                 "full_isolation_proven": False}
        if self.tamper:
            event["decoy_reads_denied"]["key"] = False
        events = self.root / "work" / "events"
        events.mkdir()
        (events / "000.json").write_text(canonical(event) + "\n")
        (self.root / "work" / "positive-control.txt").write_text(order["public_text"])
        return subprocess.CompletedProcess(command, 0, stdout=canonical(event) + "\n",
                                           stderr="")

    def fake_control(self, command, **options):
        self.assertEqual(options["check"], False)
        if self.inspect_error:
            return subprocess.CompletedProcess(command, 1, stdout="",
                                               stderr="permission denied")
        self.assertEqual(command[:2], ["docker", "inspect"])
        return subprocess.CompletedProcess(command, 1, stdout="",
            stderr=f"Error: No such object: market-rsi-b-{self.cycle_id}")

    def _run(self):
        return canary.run(root=self.root, cycle_id=self.cycle_id,
                          ready=lambda: True, run_process=self.fake_process,
                          control_run=self.fake_control)

    def test_no_daemon_rejects_before_artifact_or_container(self):
        with self.assertRaisesRegex(RuntimeError, "Docker daemon unavailable"):
            canary.run(root=self.root, cycle_id=self.cycle_id,
                       ready=lambda: False, run_process=self.fake_process)
        self.assertFalse(self.root.exists())
        self.assertEqual(self.commands, [])

    def test_fake_receipts_require_denials_positive_control_and_exact_cleanup(self):
        result = self._run()
        self.assertTrue(result["passed_selected_checks"])
        self.assertTrue(result["exact_container_cleanup_verified"])
        self.assertFalse(result["formal_admission"])
        self.assertFalse(result["model_authorship_proven"])
        self.assertFalse(result["full_isolation_proven"])
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(load_json(self.root / "cleanup.json")["final_inspection"],
                         "absent")

    def test_one_decoy_read_success_fails_review(self):
        self.tamper = True
        result = self._run()
        self.assertFalse(result["passed_selected_checks"])
        self.assertEqual(result["reason"], "guest_denial_or_positive_control_failed")
        self.assertTrue(result["exact_container_cleanup_verified"])

    def test_permission_denied_inspection_never_counts_as_cleanup(self):
        self.inspect_error = True
        result = self._run()
        self.assertFalse(result["passed_selected_checks"])
        self.assertFalse(result["exact_container_cleanup_verified"])
        self.assertEqual(result["reason"], "exact_container_cleanup_unverified")

    def test_owned_residual_container_is_stopped_by_exact_label_only(self):
        calls = []
        name = "market-rsi-b-" + self.cycle_id
        def control(command, **_options):
            calls.append(command)
            if command[:2] == ["docker", "stop"]:
                return subprocess.CompletedProcess(command, 0, stdout=name + "\n", stderr="")
            if len(calls) == 1:
                return subprocess.CompletedProcess(command, 0, stdout=name + "\n", stderr="")
            return subprocess.CompletedProcess(command, 1, stdout="",
                                               stderr=f"Error: No such object: {name}")
        cleanup = canary._cleanup_exact(name, control_run=control)
        self.assertEqual(cleanup["initial_inspection"], "owned")
        self.assertTrue(cleanup["stop_acknowledged"])
        self.assertTrue(cleanup["exact_container_cleanup_verified"])
        self.assertEqual(calls[1], ["docker", "stop", "--time", "2", name])


if __name__ == "__main__":
    unittest.main()
