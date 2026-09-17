"""Offline checks for the local B Docker boundary; no daemon required."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from supervisor_harness.local_b_container import (
    GUEST_ROOT, LocalBFiles, docker_command, docker_ready)


class LocalBContainerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "guest.py"
        self.source.write_text("print('synthetic only')\n")
        self.work = self.root / "work"
        self.work.mkdir()

    def test_command_has_bounded_isolation_and_only_two_mounts(self):
        command = docker_command(container_name="market-rsi-b-test01",
                                 source=self.source, work=self.work,
                                 uid=501, gid=20)
        self.assertEqual(command[:5], ["docker", "run", "--rm", "--pull", "never"])
        for flag, value in (("--network", "none"), ("--cap-drop", "ALL"),
                            ("--security-opt", "no-new-privileges"),
                            ("--pids-limit", "64"), ("--memory", "512m"),
                            ("--cpus", "1"), ("--user", "501:20")):
            self.assertEqual(command[command.index(flag) + 1], value)
        self.assertIn("--read-only", command)
        self.assertEqual(command.count("--mount"), 2)
        self.assertIn(f"type=bind,src={self.source.resolve()},dst=/opt/market-rsi/directional_guest_worker.py,readonly", command)
        self.assertIn(f"type=bind,src={self.work.resolve()},dst=/work/directional", command)
        self.assertNotIn("--privileged", command)
        self.assertNotIn("--env-file", command)
        self.assertNotIn("--publish", command)

    def test_rejects_reused_work_and_symlink_mounts(self):
        (self.work / "old").write_text("previous run")
        with self.assertRaises(ValueError):
            docker_command(container_name="market-rsi-b-test01",
                           source=self.source, work=self.work, uid=501, gid=20)
        (self.work / "old").unlink()
        link = self.root / "source-link.py"
        link.symlink_to(self.source)
        with self.assertRaises(ValueError):
            docker_command(container_name="market-rsi-b-test01",
                           source=link, work=self.work, uid=501, gid=20)

    def test_rejects_bad_name_and_root_identity(self):
        for name in ("B", "market-rsi-b-../oops", "market-rsi-b-evil;echo"):
            with self.assertRaises(ValueError):
                docker_command(container_name=name, source=self.source,
                               work=self.work, uid=501, gid=20)
        with self.assertRaises(ValueError):
            docker_command(container_name="market-rsi-b-test01",
                           source=self.source, work=self.work, uid=0, gid=20)

    def test_readiness_is_read_only_and_fail_closed(self):
        calls = []

        def ready(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, stdout="27.0\n")

        self.assertTrue(docker_ready(run=ready))
        self.assertEqual(calls[0][0][:2], ["docker", "version"])
        self.assertFalse(docker_ready(run=lambda *_args, **_kwargs:
            subprocess.CompletedProcess([], 1, stdout="")))

    def test_broker_files_are_bounded_to_orders_and_results(self):
        files = LocalBFiles(self.work)
        self.addCleanup(files.close)
        files.write(GUEST_ROOT + "/orders/000.json", '{"task":1}')
        self.assertEqual((self.work / "orders/000.json").read_text(), '{"task":1}')
        with self.assertRaises(FileExistsError):
            files.write(GUEST_ROOT + "/orders/000.json", '{"task":2}')
        with self.assertRaises(ValueError):
            files.write(GUEST_ROOT + "/acks/001.json", "bad")
        with self.assertRaises(ValueError):
            files.read(GUEST_ROOT + "/orders/000.json")
        with self.assertRaises(ValueError):
            files.read(GUEST_ROOT + "/../../secret/000.json")
        (self.work / "acks").mkdir()
        (self.work / "acks/000.json").write_text('{"ack":1}')
        self.assertEqual(files.read(GUEST_ROOT + "/acks/000.json"), '{"ack":1}')

    def test_broker_refuses_guest_symlinks(self):
        outside = self.root / "outside.json"
        outside.write_text('{"secret":true}')
        (self.work / "acks").symlink_to(self.root)
        files = LocalBFiles(self.work)
        self.addCleanup(files.close)
        with self.assertRaises(OSError):
            files.read(GUEST_ROOT + "/acks/000.json")
        (self.work / "acks").unlink()
        (self.work / "acks").mkdir()
        (self.work / "acks/000.json").symlink_to(outside)
        with self.assertRaises(OSError):
            files.read(GUEST_ROOT + "/acks/000.json")


if __name__ == "__main__":
    unittest.main()
