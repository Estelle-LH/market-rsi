import unittest

from audit_tools.prepare_sports_live_timing_feedback_controller import (
    build_live_findings,
)


def audit():
    return {
        "evidence_status": "post_hoc_existing_case",
        "counts": {"distinct_games": 1, "live_delta_rows": 62},
        "clock_fields": {"live_delta_with_provider_publish": 0},
        "feature_fields": {"live_delta_with_win_probability": 0},
        "provider_event_start_to_receive_descriptive_ms": {"p50": 48000},
        "scoring_event_start_to_receive_descriptive_ms": {"p50": 41000},
        "http_round_trip_descriptive_ms": {"p50": 122},
        "claim_boundaries": {
            "market_lead_proven": False,
            "independent_confirmation": False,
        },
    }


class SportsLiveTimingFeedbackTests(unittest.TestCase):
    def test_replaces_prior_next_step_and_keeps_post_hoc_boundary(self):
        prior = [
            {"id": "earlier-evidence"},
            {"id": "next-controller-decision", "instructions": "old"},
        ]
        findings = build_live_findings(
            prior, audit(), {"jobs": {"private": {}}, "available_usd": "10"})
        self.assertEqual(sum(row["id"] == "next-controller-decision"
                             for row in findings), 1)
        post_hoc = next(row for row in findings
                        if row["id"] == "post-hoc-live-capture-audit")
        self.assertEqual(post_hoc["evidence_status"], "post_hoc_existing_case")
        self.assertIn("not independent", post_hoc["boundary"])
        self.assertNotIn("jobs", findings[-1]["budget"])
        public = next(row for row in findings
                      if row["id"] == "public-source-capability-research")
        self.assertEqual(len(public["sources"]), 4)
        self.assertTrue(all(
            source["evidence_type"] == "runner_verified_primary_source_fact"
            for source in public["sources"]))

    def test_controller_is_not_forced_to_one_horizon_or_method(self):
        prior = [{"id": "old-next"}]
        findings = build_live_findings(prior, audit(), {"jobs": {}})
        instruction = findings[-1]["instructions"]
        self.assertIn("Do not assume 5s, 30s, 60s or 90%", instruction)
        self.assertIn("better option", instruction)
        self.assertIn("one changed stage", instruction)
        self.assertIn("cannot collect feeds, fit, train", instruction)


if __name__ == "__main__":
    unittest.main()
