from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from paid_budget import PaidBudget
from run_codex_glm_controller import (codex_harness_identity,
                                      codex_command,
                                      _parse_owned_process_groups,
                                      _terminate_owned_process_tree,
                                      reconcile_unresolved_session_dispatches)


class ControllerProcessTreeTests(unittest.TestCase):
    def test_grid_learning_routes_to_delta_broker_with_bounded_threads(self):
        command=codex_command(workspace=Path('/tmp/workspace'),answer=Path('/tmp/answer'),
            base_url='http://127.0.0.1:1/v1',catalog=Path('/tmp/catalog'),instructions=Path('/tmp/instructions'),
            tool_mode='canary',controller_stage='grid_learning')
        joined=' '.join(command)
        self.assertIn('historical_grid_learning_controller.py',joined)
        self.assertNotIn('controller_tools_mcp.py',joined)
        self.assertIn('OMP_NUM_THREADS',joined)
        self.assertIn('mcp_servers.controller_tools.required=true',command)
        self.assertIn('mcp_servers.controller_tools.startup_timeout_sec=10',command)

    def test_grid_objective_uses_recorded_grid_broker_not_legacy_labels(self):
        command=codex_command(workspace=Path('/tmp/workspace'),answer=Path('/tmp/answer'),
            base_url='http://127.0.0.1:1/v1',catalog=Path('/tmp/catalog'),instructions=Path('/tmp/instructions'),
            tool_mode='canary',controller_stage='grid_objective')
        joined=' '.join(command)
        self.assertIn('historical_grid_objective_controller.py',joined)
        self.assertNotIn('objective_discovery_tools_mcp.py',joined)

    def test_data_use_stage_routes_to_read_only_data_use_broker(self):
        command = codex_command(workspace=Path('/tmp/workspace'), answer=Path('/tmp/answer'),
            base_url='http://127.0.0.1:1/v1', catalog=Path('/tmp/catalog'),
            instructions=Path('/tmp/instructions'), tool_mode='canary', controller_stage='data_use')
        joined=' '.join(command)
        self.assertIn('historical_data_use_controller.py',joined)
        self.assertNotIn('historical_ingest_controller.py',joined)

    def test_data_stage_routes_to_data_discovery_broker(self):
        command = codex_command(
            workspace=Path("/tmp/workspace"), answer=Path("/tmp/answer"),
            base_url="http://127.0.0.1:1/v1", catalog=Path("/tmp/catalog"),
            instructions=Path("/tmp/instructions"), tool_mode="canary",
            controller_stage="data",
        )
        joined = " ".join(command)
        self.assertIn("data_discovery_tools_mcp.py", joined)
        self.assertNotIn("objective_discovery_tools_mcp.py", joined)

    def test_codex_harness_identity_binds_binary_version_and_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            codex = root / "codex"
            catalog = root / "catalog.json"
            instructions = root / "instructions.md"
            codex.write_bytes(b"fixture-codex")
            catalog.write_text('{"models":[]}\n')
            instructions.write_text("fixed instructions\n")
            version = SimpleNamespace(stdout="codex-cli 1.2.3\n", stderr="",
                                      returncode=0)
            with patch("run_codex_glm_controller.CODEX", str(codex)), \
                    patch("run_codex_glm_controller.subprocess.run",
                          return_value=version) as run:
                first = codex_harness_identity(
                    catalog=catalog,
                    instructions=instructions,
                    command=[str(codex), "exec", "-"],
                )
                second = codex_harness_identity(
                    catalog=catalog,
                    instructions=instructions,
                    command=[str(codex), "exec", "-"],
                )
            self.assertEqual(first, second)
            self.assertEqual(first["schema"], "market_codex_harness_runtime_v1")
            self.assertEqual(first["codex_cli"]["version"], "codex-cli 1.2.3")
            self.assertEqual(len(first["codex_cli"]["sha256"]), 64)
            self.assertEqual(run.call_count, 2)

            instructions.write_text("changed instructions\n")
            with patch("run_codex_glm_controller.CODEX", str(codex)), \
                    patch("run_codex_glm_controller.subprocess.run",
                          return_value=version):
                changed = codex_harness_identity(
                    catalog=catalog,
                    instructions=instructions,
                    command=[str(codex), "exec", "-"],
                )
            self.assertNotEqual(
                first["model_instructions_sha256"],
                changed["model_instructions_sha256"],
            )

    def test_separate_mcp_like_child_group_is_stopped_with_controller(self):
        child = "import time; time.sleep(60)"
        parent = (
            "import subprocess,sys,time; "
            f"p=subprocess.Popen([sys.executable,'-c',{child!r}],start_new_session=True); "
            "print(p.pid,flush=True); time.sleep(60)"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", parent], stdout=subprocess.PIPE, text=True,
            start_new_session=True,
        )
        child_pid = int(process.stdout.readline().strip())
        try:
            listing = (f"{process.pid} {os.getpid()} {process.pid}\n"
                       f"{child_pid} {process.pid} {child_pid}\n"
                       f"99999 {os.getpid()} 99999\n")
            groups = _parse_owned_process_groups(process.pid, listing, os.getpgrp())
            self.assertIn(process.pid, groups)
            self.assertIn(child_pid, groups)
            with patch("run_codex_glm_controller._owned_process_groups",
                       return_value=groups):
                _terminate_owned_process_tree(process)
            self.assertIsNotNone(process.poll())
            for _ in range(50):
                try:
                    os.kill(child_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(.02)
            else:
                self.fail("separate child process group remained alive")
        finally:
            for group in (process.pid, child_pid):
                try:
                    os.killpg(group, 9)
                except ProcessLookupError:
                    pass
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
            process.stdout.close()

    def test_unresolved_provider_turn_is_conservatively_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            budget = PaidBudget.create(root / "budget", {
                "experiment_id": "fixture", "cap_usd": "2", "target_usd": "1",
                "buckets_usd": {"setup": "2"}, "authority": "fixture",
            })
            job = "fixture-session-turn-001"
            budget.reserve(job, "setup", "0.5", "tinker", "a" * 64)
            budget.dispatch(job)
            output = root / "session"
            output.mkdir()
            (output / "process.json").write_text('{"pid":123}\n')
            receipts = reconcile_unresolved_session_dispatches(
                session_id="fixture-session", budget=budget, output=output,
                transport={"process_reaped": True},
            )
            self.assertEqual(receipts[0]["job_id"], job)
            self.assertEqual(budget.snapshot()["jobs"][job]["state"],
                             "uncertain_terminal")


if __name__ == "__main__":
    unittest.main()
