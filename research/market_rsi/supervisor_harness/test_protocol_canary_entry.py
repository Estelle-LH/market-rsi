"""Offline admission tests; no provider key, E2B sandbox or live round."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from market_rsi import digest
from paid_budget import PaidBudget
from supervisor_harness.global_state_gate import SupervisorGlobalState
from supervisor_harness import protocol_canary_entry as entry


PRIOR = {"controller_led_result": False, "formal_admission": False,
         "review_sha256": "a" * 64, "source_manifest_sha256": "b" * 64}
PUBLICATION = {"commit": "c" * 40, "source_sha256": "d" * 64}


class ProtocolCanaryEntryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.doc = self.root / "decision.md"
        self.doc.write_text("unchanged supervisor decision\n")
        self.state = SupervisorGlobalState(self.root / "state", self.doc)
        self.head = self.state.initialize()["head_sha256"]
        self.budget = PaidBudget.create(self.root / "budget", {
            "experiment_id": "fixture-budget", "cap_usd": "1.00",
            "target_usd": "1.00", "buckets_usd": {
                "setup": "0.30", "model": "0.70"}, "authority": "offline test"})
        self.output = self.root / "canary-01"
        self.arguments = dict(root=self.output, cycle_id=self.output.name,
            state=self.state, budget=self.budget, expected_head_sha256=self.head,
            prior_fixture_root=self.root / "unused-prior", release_tag="market-rsi-protocol-v0.1.0",
            expected_source_sha256=PUBLICATION["source_sha256"])
        self.fixture = patch.object(entry.research_cycle_gate, "verify_fixture_canary",
                                    return_value=PRIOR)
        self.release = patch.object(entry.protocol_source_release, "verify_published",
                                    return_value=PUBLICATION)
        self.fixture.start()
        self.release.start()
        self.addCleanup(self.fixture.stop)
        self.addCleanup(self.release.stop)

    def test_claim_and_hold_are_bound_but_never_dispatched(self):
        claim = entry.begin_protocol_canary(**self.arguments)
        self.assertFalse(claim["model_authorship_proven"])
        self.assertFalse(claim["isolation_proven"])
        self.assertEqual(self.state.snapshot()["active_cycle"], "canary-01")
        job = self.budget.snapshot()["jobs"]["canary-01"]
        self.assertEqual(job["state"], "reserved")
        self.assertEqual(job["input_sha256"], digest(claim))
        self.assertEqual(self.budget.snapshot()["effective_cost_usd"], "0")
        with self.assertRaises(ValueError):
            entry.begin_protocol_canary(**self.arguments)

    def test_unpublished_and_stale_work_do_not_claim_or_reserve(self):
        with patch.object(entry.protocol_source_release, "verify_published",
                          side_effect=ValueError("not published")):
            with self.assertRaisesRegex(ValueError, "not published"):
                entry.begin_protocol_canary(**self.arguments)
        with self.assertRaisesRegex(ValueError, "stale"):
            entry.begin_protocol_canary(**{**self.arguments,
                                           "expected_head_sha256": "0" * 64})
        self.assertIsNone(self.state.snapshot()["active_cycle"])
        self.assertEqual(self.budget.snapshot()["jobs"], {})
        self.assertFalse(self.output.exists())

    def test_reservation_failure_closes_exact_claim_without_dispatch(self):
        with patch.object(self.budget, "reserve", side_effect=ValueError("ledger rejected")):
            with self.assertRaisesRegex(ValueError, "ledger rejected"):
                entry.begin_protocol_canary(**self.arguments)
        self.assertIsNone(self.state.snapshot()["active_cycle"])
        self.assertIn("canary-01", self.state.snapshot()["claimed_cycles"])
        self.assertEqual(self.budget.snapshot()["jobs"], {})
        self.assertTrue((self.output / "failure.json").is_file())

    def test_insufficient_setup_budget_stops_before_state_claim(self):
        small = PaidBudget.create(self.root / "small-budget", {
            "experiment_id": "small-fixture", "cap_usd": "1.00",
            "target_usd": "1.00", "buckets_usd": {
                "setup": "0.10", "model": "0.90"}, "authority": "offline test"})
        with self.assertRaisesRegex(ValueError, "setup budget"):
            entry.begin_protocol_canary(**{**self.arguments, "budget": small})
        self.assertIsNone(self.state.snapshot()["active_cycle"])
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
