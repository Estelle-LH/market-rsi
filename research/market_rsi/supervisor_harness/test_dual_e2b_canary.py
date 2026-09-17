"""Offline tests: these fakes are not evidence of E2B isolation or model authorship."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import dual_e2b_canary as canary

REAL_REQUIRE_LOCAL_RUNTIME = canary._require_local_runtime


class FakeBudget:
    def __init__(self, root: Path, available: str = "1"):
        self.root = root
        self.available = available
        self.events = []

    def snapshot(self):
        return {"available_usd": self.available,
                "buckets": {"setup": {"available_usd": self.available}}}

    def reserve(self, *args):
        self.events.append(("reserve", args))

    def dispatch(self, *args):
        self.events.append(("dispatch", args))

    def settle_uncertain_at_upper(self, *args):
        self.events.append(("settle_upper", args))


class FakeSandbox:
    def __init__(self, sandbox_id: str, *, failing_check: str | None = None,
                 kill_ack: bool = True, public_network: bool = False):
        self.sandbox_id = sandbox_id
        self.failing_check = failing_check
        self.kill_ack = kill_ack
        self.public_network = public_network
        self.files = self
        self.commands = self
        self.content = {}
        self.killed = False

    def get_info(self):
        return SimpleNamespace(template_id="fake-base",
                               allow_internet_access=self.public_network,
                               cpu_count=2, memory_mb=4096,
                               envd_version="fake-envd")

    def write(self, path, data):
        self.content[path] = data

    def read(self, path):
        return self.content[path]

    def run(self, command, timeout):
        assert timeout == 25
        role = command.split()[3]
        payload = json.loads(self.content["/tmp/market_input.json"])
        checks = {"peer_marker_absent": True, "paid_keys_absent": True,
                  "host_home_absent": True, "direct_public_network_blocked": True}
        if self.failing_check:
            checks[self.failing_check] = False
        if role == "controller":
            output = {"schema": "scripted_controller_decision_v1",
                      "input_sha256": payload["input_sha256"],
                      "task": "hash the admitted synthetic task"}
        else:
            output = {"schema": "scripted_researcher_output_v1",
                      "decision_sha256": payload["decision_sha256"],
                      "task_sha256": hashlib.sha256(payload["task"].encode()).hexdigest()}
        self.content["/tmp/market_output.json"] = json.dumps(output)
        self.content["/tmp/market_report.json"] = json.dumps(
            {"role": role, "checks": checks})
        return SimpleNamespace(exit_code=0 if all(checks.values()) else 17,
                               stdout="", stderr="")

    def kill(self):
        self.killed = True
        return self.kill_ack


class FakePager:
    def __init__(self, items):
        self.items = items

    @property
    def has_next(self):
        return self.items is not None

    def next_items(self):
        items, self.items = self.items, None
        return items


class DualE2BCanaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "dual-e2b-canary-test01"
        self.budget = FakeBudget(self.base / "budget")
        self.paths = patch.object(canary, "_local_root",
                                  side_effect=lambda path, label: Path(path).resolve())
        self.runtime = patch.object(canary, "_require_local_runtime")
        self.paths.start()
        self.runtime.start()
        self.addCleanup(self.paths.stop)
        self.addCleanup(self.runtime.stop)

    def test_two_distinct_roles_complete_with_one_bound_handoff(self):
        created = {}

        def factory(role, job_id):
            self.assertEqual(job_id, self.root.name)
            created[role] = FakeSandbox(f"{role}-id")
            return created[role]

        review = canary.run_pair(self.root, self.budget, factory)
        self.assertTrue(review["isolation_checks_passed"])
        self.assertFalse(review["controller_led_result"])
        self.assertEqual([e[0] for e in self.budget.events],
                         ["reserve", "dispatch", "settle_upper"])
        self.assertTrue(all(s.killed for s in created.values()))
        decision = json.loads((self.root / "decision.json").read_text())
        output = json.loads((self.root / "output.json").read_text())
        self.assertEqual(output["decision_sha256"], canary.digest(decision))
        self.assertTrue((self.root / "cleanup.json").is_file())

    def test_same_sandbox_id_fails_and_preserves_failure(self):
        created = []

        def factory(role, job_id):
            item = FakeSandbox("reused-id")
            created.append(item)
            return item

        with self.assertRaisesRegex(ValueError, "reused one E2B sandbox ID"):
            canary.run_pair(self.root, self.budget, factory)
        self.assertEqual(len(created), 2)
        self.assertTrue(all(s.killed for s in created))
        self.assertTrue((self.root / "failure.json").is_file())
        self.assertFalse((self.root / "review.json").exists())

    def test_cross_role_access_probe_failure_is_not_accepted(self):
        created = {}

        def factory(role, job_id):
            created[role] = FakeSandbox(role, failing_check=(
                "peer_marker_absent" if role == "researcher" else None))
            return created[role]

        with self.assertRaisesRegex(ValueError, "researcher isolation probe failed"):
            canary.run_pair(self.root, self.budget, factory)
        self.assertTrue(all(s.killed for s in created.values()))
        self.assertFalse((self.root / "review.json").exists())

    def test_budget_stops_before_claim_or_creation(self):
        self.budget.available = "0.01"
        with self.assertRaisesRegex(ValueError, "budget cannot cover"):
            canary.run_pair(self.root, self.budget,
                            lambda role, job_id: self.fail("must not create"))
        self.assertFalse(self.root.exists())
        self.assertEqual(self.budget.events, [])

    def test_public_network_configuration_fails_and_kills_exact_instance(self):
        created = []

        def factory(role, job_id):
            item = FakeSandbox(role, public_network=(role == "controller"))
            created.append(item)
            return item

        with self.assertRaisesRegex(ValueError, "network or compute bounds"):
            canary.run_pair(self.root, self.budget, factory)
        self.assertEqual(len(created), 1)
        self.assertTrue(created[0].killed)
        self.assertFalse((self.root / "review.json").exists())

    def test_incomplete_cleanup_never_creates_passing_review(self):
        def factory(role, job_id):
            return FakeSandbox(role, kill_ack=(role == "controller"))

        with self.assertRaisesRegex(RuntimeError, "incomplete E2B cleanup"):
            canary.run_pair(self.root, self.budget, factory)
        self.assertFalse((self.root / "review.json").exists())
        self.assertEqual([e[0] for e in self.budget.events], ["reserve", "dispatch"])

    def test_uncertain_second_creation_preserves_hold(self):
        created = []

        def factory(role, job_id):
            if role == "researcher":
                raise RuntimeError("remote create status unknown")
            item = FakeSandbox("controller-id")
            created.append(item)
            return item

        with self.assertRaisesRegex(RuntimeError, "remote create status unknown"):
            canary.run_pair(self.root, self.budget, factory)
        self.assertTrue(created[0].killed)
        self.assertEqual([e[0] for e in self.budget.events], ["reserve", "dispatch"])
        self.assertFalse((self.root / "review.json").exists())

    def test_wrong_e2b_version_fails_before_any_paid_action(self):
        with patch.object(canary.sys, "executable",
                          "/Users/estelle/Library/Application Support/MarketRSI/fake/bin/python3"):
            with patch.object(canary.importlib.metadata, "version", return_value="0.0.0"):
                with self.assertRaisesRegex(ValueError, "E2B SDK version differs"):
                    REAL_REQUIRE_LOCAL_RUNTIME()
        self.assertFalse(self.root.exists())
        self.assertEqual(self.budget.events, [])

    def test_active_market_sandbox_blocks_before_paid_action(self):
        listing = SimpleNamespace(list=lambda **kwargs: FakePager([
            SimpleNamespace(metadata={"experiment_id": "market-rsi-other-run"})]))
        with self.assertRaisesRegex(RuntimeError, "still active"):
            canary._require_no_active_market_sandboxes(listing, "dummy-key")
        self.assertFalse(self.root.exists())
        self.assertEqual(self.budget.events, [])


if __name__ == "__main__":
    unittest.main()
