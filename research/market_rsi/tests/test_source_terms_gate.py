from __future__ import annotations

import unittest

from source_terms_gate import (kalshi_research_terms_gate,
                               polymarket_research_terms_gate)


class SourceTermsGateTests(unittest.TestCase):
    def test_kalshi_research_is_rejected_before_data_access(self):
        report = kalshi_research_terms_gate(
            agreement_sha256="a" * 64,
            retrieved_at_utc="2026-09-09T16:00:00Z",
        )
        self.assertEqual(report["status"], "rejected_before_data_access")
        self.assertFalse(report["source_market_data_contacted"])
        self.assertFalse(report["full_download_authorized"])
        self.assertIn("3.1", report["agreement"]["relevant_sections"])

    def test_rejects_ambiguous_evidence_identity(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            kalshi_research_terms_gate(
                agreement_sha256="not-a-hash",
                retrieved_at_utc="2026-09-09T16:00:00Z",
            )
        with self.assertRaisesRegex(ValueError, "UTC"):
            kalshi_research_terms_gate(
                agreement_sha256="a" * 64,
                retrieved_at_utc="2026-09-09T16:00:00+02:00",
            )

    def test_polymarket_unresolved_reuse_terms_stop_new_data_requests(self):
        report = polymarket_research_terms_gate(
            institute_page_sha256="a" * 64,
            terms_page_sha256="b" * 64,
            retrieved_at_utc="2026-09-09T18:20:00Z",
            prior_canary_sha256="c" * 64,
        )
        self.assertEqual(report["status"], "rejected_before_data_access")
        self.assertFalse(report["source_market_data_contacted"])
        self.assertTrue(report["prior_bounded_canary"]["exists"])
        self.assertTrue(report["prior_bounded_canary"]["may_not_be_expanded"])


if __name__ == "__main__":
    unittest.main()
