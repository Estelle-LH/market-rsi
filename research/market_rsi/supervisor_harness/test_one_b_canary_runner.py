"""Offline fake-only parent/child accounting checks; never call E2B or GLM."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from paid_budget import PaidBudget
from supervisor_harness import one_b_canary_runner as runner
from supervisor_harness.global_state_gate import SupervisorGlobalState
from supervisor_harness.test_one_b_live_adapter import FakeSandbox, FakeSession


PRIOR = {"controller_led_result": False, "formal_admission": False,
         "review_sha256": "a" * 64, "source_manifest_sha256": "b" * 64}
GUEST = Path(runner.one_b_live_adapter.__file__).with_name("directional_guest_worker.py")


class OneBParentRunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        decision = self.base / "decision.md"
        decision.write_text("fixed market_one_b_canary_decision_v1 supervisor decision\n")
        self.state = SupervisorGlobalState(self.base / "state", decision)
        self.head = self.state.initialize()["head_sha256"]
        self.budget = PaidBudget.create(self.base / "budget", {
            "experiment_id": "one-b-parent-fake", "cap_usd": "1.00",
            "target_usd": "1.00", "buckets_usd": {
                "setup": "0.30", "model": "0.70"},
            "authority": "offline fake test only"})
        self.root = self.base / "cycle-one-b-01"
        self.source_sha = runner._source_sha256()
        self.sandbox = FakeSandbox()
        self.creates = 0
        self.keys = 0
        self.accounts = []
        self.child_error = None
        self.args = dict(
            root=self.root, budget=self.budget, state=self.state,
            expected_head_sha256=self.head,
            prior_fixture_root=self.base / "prior-fixture",
            release_tag="market-rsi-protocol-v0.1.4",
            expected_source_sha256=self.source_sha,
            public_source="offline synthetic public source",
            guest_source_path=GUEST, env_file=self.base / "never-read.env",
            load_key=self.load_key, check_account_clear=self.account,
            invoke=self.invoke, dispatch_enabled=True)
        fixture = patch.object(runner.one_b_canary_entry.research_cycle_gate,
                               "verify_fixture_canary", return_value=PRIOR)
        publication = patch.object(runner.protocol_source_release,
                                   "verify_published", return_value={
                                       "commit": "c" * 40,
                                       "source_sha256": self.source_sha})
        fixture.start()
        publication.start()
        self.addCleanup(fixture.stop)
        self.addCleanup(publication.stop)

    def load_key(self):
        self.keys += 1
        return "offline-fake-key"

    def account(self, key, expected_id):
        self.assertEqual(key, "offline-fake-key")
        self.accounts.append(expected_id)
        clear = expected_id is None or self.sandbox.killed
        return {"clear": clear, "checked_sandbox_id": expected_id,
                "active_market_rsi_ids": [] if clear else [self.sandbox.sandbox_id]}

    def create(self, key):
        self.assertEqual(key, "offline-fake-key")
        self.creates += 1
        return self.sandbox

    def launch(self, sandbox, command):
        session = FakeSession(sandbox, command)
        sandbox.session = session
        return session

    def invoke(self, command, **options):
        self.assertEqual(command, runner._child_command(
            root=self.root, budget=self.budget, state=self.state,
            guest_source_path=GUEST, public_source=self.args["public_source"],
            env_file=self.args["env_file"]))
        self.assertEqual(options, {"capture_output": True, "text": True,
                                   "timeout": runner.CHILD_TIMEOUT_SECONDS,
                                   "check": False})
        try:
            runner.run_child(
                root=self.root, budget=self.budget, state=self.state,
                public_source=self.args["public_source"], guest_source_path=GUEST,
                load_key=self.load_key, create_sandbox=self.create,
                check_account_clear=self.account, launch_guest=self.launch)
            code = 0
        except Exception as exc:
            self.child_error = exc
            code = 1
        return SimpleNamespace(returncode=code, stdout="", stderr="")

    def test_default_disabled_before_claim_or_key(self):
        with self.assertRaisesRegex(RuntimeError, "live dispatch disabled"):
            runner.run_parent(**{**self.args, "dispatch_enabled": False})
        self.assertEqual(self.keys, 0)
        self.assertEqual(self.budget.snapshot()["jobs"], {})
        self.assertIsNone(self.state.snapshot()["active_cycle"])

    def test_cli_requires_explicit_live_flag_before_key_or_claim(self):
        argv = ["one_b_canary_runner.py", "--output", str(self.root),
                "--budget", str(self.budget.root), "--state-root", str(self.state.root),
                "--decision-doc", str(self.state.decision_doc),
                "--guest-source", str(GUEST), "--public-source", "public fixture",
                "--env-file", str(self.base / "never-read.env")]
        with patch.object(sys, "argv", argv):
            with self.assertRaisesRegex(RuntimeError, "explicit --admit-live"):
                runner.main()
        self.assertEqual(self.keys, 0)
        self.assertEqual(self.budget.snapshot()["jobs"], {})

    def test_cli_rejects_nonlocal_output_before_credentials(self):
        argv = ["one_b_canary_runner.py", "--output", str(self.root),
                "--budget", str(self.budget.root), "--state-root", str(self.state.root),
                "--decision-doc", str(self.state.decision_doc),
                "--guest-source", str(GUEST), "--public-source", "public fixture",
                "--env-file", str(self.base / "never-read.env"), "--admit-live"]
        with patch.object(sys, "argv", argv), patch.object(runner, "_require_live_runtime"):
            with self.assertRaisesRegex(ValueError, "local MarketRSI path"):
                runner.main()
        self.assertEqual(self.keys, 0)
        self.assertEqual(self.budget.snapshot()["jobs"], {})

    def test_parent_owns_claim_child_dispatch_and_conservative_terminal(self):
        terminal = runner.run_parent(**self.args)
        self.assertEqual(terminal["outcome"], "synthetic_transport_observed")
        self.assertEqual(terminal["cost_status"], "uncertain_upper_bound_not_invoice")
        self.assertFalse(terminal["model_authorship_proven"])
        self.assertFalse(terminal["isolation_proven"])
        self.assertEqual(self.creates, 1)
        self.assertEqual(self.sandbox.kill_calls, 1)
        self.assertEqual(self.accounts, [None, None, self.sandbox.sandbox_id,
                                         self.sandbox.sandbox_id])
        self.assertEqual(self.keys, 2)
        self.assertEqual(self.budget.snapshot()["jobs"][self.root.name]["state"],
                         "uncertain_terminal")
        self.assertEqual(self.budget.snapshot()["effective_cost_usd"], "0.20")
        self.assertIsNone(self.state.snapshot()["active_cycle"])
        self.assertTrue((self.root / "parent-terminal.json").is_file())

    def test_missing_key_cancels_only_pre_dispatch_hold(self):
        with self.assertRaisesRegex(ValueError, "credential unavailable"):
            runner.run_parent(**{**self.args, "load_key": lambda: None})
        self.assertEqual(self.creates, 0)
        self.assertEqual(self.budget.snapshot()["jobs"][self.root.name]["state"],
                         "cancelled_before_dispatch")
        self.assertIsNone(self.state.snapshot()["active_cycle"])

    def test_unacknowledged_exact_kill_leaves_hold_and_claim_unresolved(self):
        self.sandbox.mode = "kill_false"
        with self.assertRaisesRegex(ValueError, "exact B kill"):
            runner.run_parent(**self.args)
        self.assertEqual(self.creates, 1)
        self.assertEqual(self.sandbox.kill_calls, 1)
        self.assertEqual(self.budget.snapshot()["jobs"][self.root.name]["state"],
                         "dispatched")
        self.assertEqual(self.state.snapshot()["active_cycle"], self.root.name)

    def test_independent_account_failure_leaves_hold_and_claim_unresolved(self):
        original = self.account
        def fourth_check(key, expected_id):
            if len(self.accounts) == 3:
                self.accounts.append(expected_id)
                return {"clear": False, "checked_sandbox_id": expected_id,
                        "active_market_rsi_ids": [expected_id]}
            return original(key, expected_id)
        with self.assertRaisesRegex(RuntimeError, "independent E2B account-clear"):
            runner.run_parent(**{**self.args, "check_account_clear": fourth_check})
        self.assertEqual(self.sandbox.kill_calls, 1)
        self.assertEqual(self.budget.snapshot()["jobs"][self.root.name]["state"],
                         "dispatched")
        self.assertEqual(self.state.snapshot()["active_cycle"], self.root.name)

    def test_source_change_before_parent_settlement_leaves_hold_unresolved(self):
        original_invoke = self.invoke
        def mutate_after_child(command, **options):
            result = original_invoke(command, **options)
            changed = patch.object(runner, "_source_sha256", return_value="0" * 64)
            changed.start()
            self.addCleanup(changed.stop)
            return result
        with self.assertRaisesRegex(ValueError, "source/input changed"):
            runner.run_parent(**{**self.args, "invoke": mutate_after_child})
        self.assertEqual(self.budget.snapshot()["jobs"][self.root.name]["state"],
                         "dispatched")
        self.assertEqual(self.state.snapshot()["active_cycle"], self.root.name)

    def test_reaped_failure_with_verified_kill_still_settles_upper(self):
        self.sandbox.mode = "wrong_ack"
        terminal = runner.run_parent(**self.args)
        self.assertEqual(terminal["outcome"], "failed")
        self.assertIsNotNone(self.child_error)
        self.assertEqual(self.sandbox.kill_calls, 1)
        self.assertEqual(self.budget.snapshot()["jobs"][self.root.name]["state"],
                         "uncertain_terminal")
        self.assertIsNone(self.state.snapshot()["active_cycle"])

    def test_optional_policy_echo_omission_is_only_failed_diagnostic(self):
        original = self.sandbox.get_info
        def missing_allow_out(**options):
            info = original(**options)
            info.network = {"deny_out": ["0.0.0.0/0"],
                            "allow_public_traffic": False}
            return info
        with patch.object(self.sandbox, "get_info", side_effect=missing_allow_out):
            terminal = runner.run_parent(**self.args)
        self.assertEqual(terminal["outcome"],
                         "synthetic_transport_diagnostic_policy_unconfirmed")
        self.assertFalse(terminal["policy_echo_accepted"])
        self.assertFalse(terminal["isolation_proven"])
        self.assertEqual(self.budget.snapshot()["jobs"][self.root.name]["state"],
                         "uncertain_terminal")
        self.assertIsNone(self.state.snapshot()["active_cycle"])

    def test_timeout_without_cleanup_stays_unresolved(self):
        def timeout(_command, **_options):
            # Fake TimeoutExpired models subprocess.run's reaped direct child.
            self.budget.dispatch(self.root.name)
            raise subprocess.TimeoutExpired("fake-child", 1)
        with self.assertRaisesRegex(ValueError, "receipt"):
            runner.run_parent(**{**self.args, "invoke": timeout})
        self.assertEqual(self.budget.snapshot()["jobs"][self.root.name]["state"],
                         "dispatched")
        self.assertEqual(self.state.snapshot()["active_cycle"], self.root.name)


if __name__ == "__main__":
    unittest.main()
