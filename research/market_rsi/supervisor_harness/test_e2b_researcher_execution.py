"""Local subprocess/object-shaped tests; not live E2B or GLM evidence."""
from __future__ import annotations

import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from supervisor_harness import broker_handoff, e2b_researcher_execution
from supervisor_harness.global_state_gate import SupervisorGlobalState


class Files:
    def __init__(self, root):
        self.root = root

    def path(self, guest_path):
        return self.root / guest_path.lstrip("/")

    def write(self, guest_path, value):
        path = self.path(guest_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def read(self, guest_path):
        return self.path(guest_path).read_text(encoding="utf-8")


class Sandbox:
    def __init__(self, sandbox_id, root, *, force_failure=False):
        self.sandbox_id = sandbox_id
        self.files = Files(root)
        self.commands = self
        self.force_failure = force_failure
        self.runs = []
        self.timeouts = []

    def run(self, command, *, timeout):
        self.runs.append(command)
        self.timeouts.append(timeout)
        if self.force_failure:
            return SimpleNamespace(exit_code=17, stdout="", stderr="failed")
        args = shlex.split(command)
        mapped = [str(self.files.path(value)) if value.startswith("/tmp/") else value
                  for value in args]
        mapped[0] = sys.executable
        finished = subprocess.run(mapped, timeout=timeout, capture_output=True,
                                  text=True, check=False)
        return SimpleNamespace(exit_code=finished.returncode, stdout=finished.stdout,
                               stderr=finished.stderr)


class BrokeredResearcherExecutionTests(unittest.TestCase):
    def setup_cycle(self, root):
        doc = root / "decision.md"
        doc.write_text("frozen\n")
        state = SupervisorGlobalState(root / "state", doc)
        head = state.initialize()["head_sha256"]
        state.claim("cycle-01", expected_head_sha256=head,
                    source_sha256="b" * 64, prior_canary_sha256="c" * 64)
        a = Sandbox("controller-A", root / "a")
        b = Sandbox("researcher-B", root / "b")
        handoff = broker_handoff.BrokerHandoff(
            controller_sandbox=a, researcher_sandbox=b, state=state,
            cycle_id="cycle-01", input_sha256="a" * 64,
            receipt_root=root / "handoff")
        a.files.write(broker_handoff.A_DECISION, json.dumps({
            "schema": "market_research_decision_v1", "cycle_id": "cycle-01",
            "input_sha256": "a" * 64, "task_id": "hash-public-canary",
            "task_type": "code_canary", "data_role": "synthetic_fixture",
            "question": "Can B hash the public string?", "hypothesis": "It matches.",
            "expected_evidence": "Host-verified hash", "stop_rule": "Once",
            "max_seconds": 7, "cost_bound_usd": "0", "public_text": "harmless public string"}))
        handoff.freeze_and_deliver()
        return state, a, b, handoff

    def test_real_local_worker_and_host_feedback_still_not_e2b_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state, a, b, handoff = self.setup_cycle(root)
            receipt = e2b_researcher_execution.execute_brokered_canary(
                handoff=handoff, researcher_sandbox=b, receipt_root=root / "execution")
            self.assertTrue(receipt["synthetic_only"])
            self.assertFalse(receipt["isolation_proven"])
            self.assertEqual(len(b.runs), 1)
            self.assertEqual(b.timeouts, [7])
            self.assertEqual(handoff.stage, "complete")
            self.assertEqual(json.loads(a.files.read(broker_handoff.A_FEEDBACK))[
                "verdict"], "accept")
            self.assertFalse(b.files.path(broker_handoff.A_FEEDBACK).exists())
            self.assertEqual(state.snapshot()["active_cycle"], "cycle-01")
            with self.assertRaises(ValueError):
                e2b_researcher_execution.execute_brokered_canary(
                    handoff=handoff, researcher_sandbox=b, receipt_root=root / "again")

    def test_mismatched_b_rejected_before_any_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, b, handoff = self.setup_cycle(root)
            other = Sandbox(b.sandbox_id, root / "other")
            with self.assertRaisesRegex(ValueError, "exact observed researcher"):
                e2b_researcher_execution.execute_brokered_canary(
                    handoff=handoff, researcher_sandbox=other,
                    receipt_root=root / "execution")
            self.assertFalse((root / "execution").exists())

    def test_failed_guest_command_never_delivers_feedback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, a, b, handoff = self.setup_cycle(root)
            b.force_failure = True
            with self.assertRaisesRegex(RuntimeError, "researcher command failed"):
                e2b_researcher_execution.execute_brokered_canary(
                    handoff=handoff, researcher_sandbox=b,
                    receipt_root=root / "execution")
            self.assertTrue((root / "execution/failure.json").is_file())
            self.assertFalse(a.files.path(broker_handoff.A_FEEDBACK).exists())
            self.assertEqual(len(b.runs), 1)
            self.assertEqual(handoff.stage, "failed")
            with self.assertRaisesRegex(ValueError, "frozen order required"):
                e2b_researcher_execution.execute_brokered_canary(
                    handoff=handoff, researcher_sandbox=b,
                    receipt_root=root / "retry")
            self.assertEqual(len(b.runs), 1)

    def test_changed_guest_order_fails_before_command_and_cannot_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, a, b, handoff = self.setup_cycle(root)
            b.files.write(broker_handoff.B_ORDER, "{}")
            with self.assertRaisesRegex(ValueError, "order changed"):
                e2b_researcher_execution.execute_brokered_canary(
                    handoff=handoff, researcher_sandbox=b,
                    receipt_root=root / "execution")
            self.assertEqual(b.runs, [])
            self.assertEqual(handoff.stage, "failed")
            self.assertFalse(a.files.path(broker_handoff.A_FEEDBACK).exists())


if __name__ == "__main__":
    unittest.main()
