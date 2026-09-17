"""Offline one-B admission checks; no provider, key, sandbox or GLM call."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from market_rsi import digest
from paid_budget import PaidBudget
from supervisor_harness.global_state_gate import SupervisorGlobalState
from supervisor_harness import one_b_canary_entry as entry


PRIOR = {"controller_led_result": False, "formal_admission": False,
         "review_sha256": "a" * 64, "source_manifest_sha256": "b" * 64}
PUBLICATION = {"commit": "c" * 40, "source_sha256": "d" * 64}


class OneBCanaryEntryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.doc = self.root / "decision.md"
        self.doc.write_text("fixed supervisor decision: market_one_b_canary_decision_v1\n")
        self.state = SupervisorGlobalState(self.root / "state", self.doc)
        self.head = self.state.initialize()["head_sha256"]
        self.budget = PaidBudget.create(self.root / "budget", {
            "experiment_id": "one-b-fixture-budget", "cap_usd": "1.00",
            "target_usd": "1.00", "buckets_usd": {
                "setup": "0.30", "model": "0.70"}, "authority": "offline test"})
        self.output = self.root / "one-b-canary-01"
        self.arguments = dict(
            root=self.output, cycle_id=self.output.name,
            state=self.state, budget=self.budget,
            expected_head_sha256=self.head,
            prior_fixture_root=self.root / "unused-prior",
            release_tag="market-rsi-protocol-v0.1.3",
            expected_source_sha256=PUBLICATION["source_sha256"],
            input_sha256="e" * 64)
        self.fixture = patch.object(entry.research_cycle_gate,
                                    "verify_fixture_canary", return_value=PRIOR)
        self.release = patch.object(entry.protocol_source_release,
                                    "verify_published", return_value=PUBLICATION)
        self.fixture.start()
        self.release.start()
        self.addCleanup(self.fixture.stop)
        self.addCleanup(self.release.stop)

    def test_exact_claim_and_hold_without_dispatch(self):
        claim = entry.begin_one_b_canary(**self.arguments)
        self.assertTrue(claim["one_b_synthetic_transport_only"])
        self.assertFalse(claim["model_authorship_proven"])
        self.assertFalse(claim["isolation_proven"])
        self.assertEqual(claim["input_sha256"], "e" * 64)
        self.assertEqual(self.state.snapshot()["active_cycle"], self.output.name)
        job = self.budget.snapshot()["jobs"][self.output.name]
        self.assertEqual(job["state"], "reserved")
        self.assertEqual(job["input_sha256"], digest(claim))
        self.assertEqual(self.budget.snapshot()["effective_cost_usd"], "0")
        with self.assertRaises(ValueError):
            entry.begin_one_b_canary(**self.arguments)

    def test_stale_or_unpublished_rejected_before_claim(self):
        with patch.object(entry.protocol_source_release, "verify_published",
                          side_effect=ValueError("not published")):
            with self.assertRaisesRegex(ValueError, "not published"):
                entry.begin_one_b_canary(**self.arguments)
        with self.assertRaisesRegex(ValueError, "stale"):
            entry.begin_one_b_canary(**{**self.arguments,
                                        "expected_head_sha256": "0" * 64})
        self.assertIsNone(self.state.snapshot()["active_cycle"])
        self.assertEqual(self.budget.snapshot()["jobs"], {})
        self.assertFalse(self.output.exists())

    def test_invalid_input_hash_rejected_without_claim(self):
        with self.assertRaisesRegex(ValueError, "SHA256"):
            entry.begin_one_b_canary(**{**self.arguments,
                                        "input_sha256": "not-a-hash"})
        self.assertIsNone(self.state.snapshot()["active_cycle"])

    def test_hash_valid_old_topology_decision_is_not_authority(self):
        old_doc = self.root / "old-decision.md"
        old_doc.write_text("old two-E2B canary decision\n")
        old_state = SupervisorGlobalState(self.root / "old-state", old_doc)
        old_head = old_state.initialize()["head_sha256"]
        with self.assertRaisesRegex(ValueError, "one-B supervisor decision"):
            entry.begin_one_b_canary(**{**self.arguments,
                                        "state": old_state,
                                        "expected_head_sha256": old_head})
        self.assertIsNone(old_state.snapshot()["active_cycle"])

    def test_reservation_failure_closes_only_exact_undispatched_claim(self):
        with patch.object(self.budget, "reserve",
                          side_effect=ValueError("ledger rejected")):
            with self.assertRaisesRegex(ValueError, "ledger rejected"):
                entry.begin_one_b_canary(**self.arguments)
        snapshot = self.state.snapshot()
        self.assertIsNone(snapshot["active_cycle"])
        self.assertIn(self.output.name, snapshot["claimed_cycles"])
        self.assertEqual(self.budget.snapshot()["jobs"], {})
        self.assertTrue((self.output / "failure.json").is_file())

    def test_insufficient_setup_allocation_stops_before_claim(self):
        small = PaidBudget.create(self.root / "small-budget", {
            "experiment_id": "small-one-b", "cap_usd": "1.00",
            "target_usd": "1.00", "buckets_usd": {
                "setup": "0.10", "model": "0.90"}, "authority": "offline test"})
        with self.assertRaisesRegex(ValueError, "setup budget"):
            entry.begin_one_b_canary(**{**self.arguments, "budget": small})
        self.assertIsNone(self.state.snapshot()["active_cycle"])
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
