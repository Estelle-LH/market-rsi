"""Offline contract tests for open-ended, non-executable data-gap proposals."""
import copy
import unittest

from market_rsi import digest
from supervisor_harness.p0_data_gap_proposal import (
    GAP_SCHEMA, PROPOSAL_SCHEMA, FEEDBACK_SCHEMA,
    archive_proposal, next_controller_input,
)


class DataGapProposalTests(unittest.TestCase):
    def setUp(self):
        self.gap = {
            "schema": GAP_SCHEMA,
            "gap_id": "missing-2023-trades",
            "evidence_sha256": "a" * 64,
            "summary": "2023 market identities and real trade coverage are incomplete.",
            "scope": "public_or_opened_train",
            "sealed_values_exposed": False,
        }
        self.proposal = {
            "schema": PROPOSAL_SCHEMA,
            "proposal_id": "new-public-archive-001",
            "gap_sha256": digest(self.gap),
            "kind": "new_source",
            "hypothesis": "A separately versioned public archive may contain real fills.",
            "candidate_source": "A new public archive not in the current registry",
            "method": "Check source rights and one outcome-blind game sample.",
            "fixed_sample_rule": "First game by schedule identity, before outcomes.",
            "expected_evidence": "Source revision, rights, raw fill hashes and misses.",
            "stop_rule": "Stop after a rights failure or first bounded sample.",
            "max_requests": 3,
            "max_bytes": 1000000,
            "max_minutes": 10,
            "max_provider_cost_usd": "0",
        }

    def _feedback(self, archive):
        return {
            "schema": FEEDBACK_SCHEMA,
            "proposal_sha256": archive["proposal_sha256"],
            "auditor_receipt_sha256": "b" * 64,
            "outcome": "inconclusive",
            "summary": "Rights remain unknown; no source was admitted.",
            "actual_cost_usd": "0",
            "sealed_values_exposed": False,
        }

    def test_novel_source_is_archived_but_never_executable(self):
        archived = archive_proposal(self.gap, self.proposal)
        self.assertEqual(archived["status"], "review_required")
        for field in ("executable", "network_authorized", "purchase_authorized",
                      "formal_data_admitted", "dev_or_final_access_authorized"):
            self.assertIs(archived[field], False)
        self.assertNotIn("task", archived)
        self.assertNotIn("handler_id", archived)

    def test_gap_digest_must_match_exact_report(self):
        changed = copy.deepcopy(self.proposal)
        changed["gap_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            archive_proposal(self.gap, changed)

    def test_sealed_gap_rejected(self):
        changed = copy.deepcopy(self.gap)
        changed["sealed_values_exposed"] = True
        with self.assertRaises(ValueError):
            archive_proposal(changed, self.proposal)

    def test_new_source_requires_candidate(self):
        changed = copy.deepcopy(self.proposal)
        changed["candidate_source"] = ""
        with self.assertRaises(ValueError):
            archive_proposal(self.gap, changed)

    def test_hard_bounds_and_exact_integer_types(self):
        for field, value in (("max_requests", 21), ("max_requests", True),
                             ("max_bytes", 5000001), ("max_minutes", 31),
                             ("max_provider_cost_usd", "0.06")):
            with self.subTest(field=field, value=value):
                changed = copy.deepcopy(self.proposal)
                changed[field] = value
                with self.assertRaises(ValueError):
                    archive_proposal(self.gap, changed)

    def test_feedback_is_bound_and_does_not_admit_data(self):
        archived = archive_proposal(self.gap, self.proposal)
        result = next_controller_input(archived, self._feedback(archived))
        self.assertEqual(result["previous_gap_sha256"], digest(self.gap))
        self.assertTrue(result["next_controller_decision_required"])
        self.assertFalse(result["formal_data_admitted"])

    def test_modified_archive_rejected(self):
        archived = archive_proposal(self.gap, self.proposal)
        changed = copy.deepcopy(archived)
        changed["proposal"]["method"] = "Different method"
        with self.assertRaises(ValueError):
            next_controller_input(changed, self._feedback(archived))

    def test_unbound_or_sealed_feedback_rejected(self):
        archived = archive_proposal(self.gap, self.proposal)
        for field, value in (("proposal_sha256", "0" * 64),
                             ("sealed_values_exposed", True)):
            with self.subTest(field=field):
                changed = self._feedback(archived)
                changed[field] = value
                with self.assertRaises(ValueError):
                    next_controller_input(archived, changed)

    def test_feedback_cannot_exceed_proposed_cost_bound(self):
        archived = archive_proposal(self.gap, self.proposal)
        changed = self._feedback(archived)
        changed["actual_cost_usd"] = "0.01"
        with self.assertRaises(ValueError):
            next_controller_input(archived, changed)

    def test_extra_fields_rejected(self):
        changed = copy.deepcopy(self.proposal)
        changed["network_authorized"] = True
        with self.assertRaises(ValueError):
            archive_proposal(self.gap, changed)


if __name__ == "__main__":
    unittest.main()
