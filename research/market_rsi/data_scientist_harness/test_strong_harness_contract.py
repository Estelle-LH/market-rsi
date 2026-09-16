import unittest

from data_scientist_harness.data_acquisition_contract import procurement_readiness
from data_scientist_harness.strong_harness_contract import (
    current_data_bottleneck,
    select_one,
    validate_proposal,
)


def proposal(identifier, component="data_acquisition", kernel_changes=None):
    return {
        "candidate_id": identifier,
        "parent_harness_version": "h0",
        "observation_ids": ["nfl-effective-sample-and-actionability-20260915"],
        "changed_component": component,
        "hypothesis": "A quote/sample workflow turns the observed data shortage into an action.",
        "implementation_scope": "Add need, provider sample and procurement readiness contracts.",
        "replay_cases": ["2025 NFL weak-data trajectory"],
        "new_canaries": ["unlicensed source is rejected"],
        "requested_kernel_changes": kernel_changes or [],
        "external_side_effects": [],
        "estimated_patch_lines": 100,
    }


def receipt(identifier, lines=100, cost=0.0, kernel=True):
    return {
        "candidate_id": identifier,
        "source_compiles": True,
        "unit_tests_passed": True,
        "historical_replays_passed": 1,
        "historical_replays_total": 1,
        "new_canaries_passed": 1,
        "new_canaries_total": 1,
        "negative_canary_passed": True,
        "unrelated_regressions_passed": True,
        "protected_kernel_unchanged": kernel,
        "sealed_data_opened": False,
        "external_side_effect_executed": False,
        "measured_patch_lines": lines,
        "estimated_next_round_cost_usd": cost,
    }


class StrongHarnessContractTests(unittest.TestCase):
    def test_protected_kernel_change_is_rejected(self):
        observation = current_data_bottleneck()
        with self.assertRaisesRegex(ValueError, "protected kernel"):
            validate_proposal(
                proposal("bad", kernel_changes=["sealed_final_access"]),
                {observation.observation_id: observation},
            )

    def test_only_fully_validated_candidate_can_be_selected(self):
        observation = current_data_bottleneck()
        proposals = [proposal("large"), proposal("small")]
        receipts = [receipt("large", lines=200), receipt("small", lines=80)]
        result = select_one("h0", [observation], proposals, receipts)
        self.assertEqual(result["selected_candidate_id"], "small")
        self.assertFalse(result["predictive_score_used_for_selection"])
        self.assertFalse(result["sealed_data_used_for_selection"])

    def test_failed_kernel_check_disqualifies_candidate(self):
        observation = current_data_bottleneck()
        result = select_one(
            "h0", [observation], [proposal("bad")], [receipt("bad", kernel=False)]
        )
        self.assertIsNone(result["selected_candidate_id"])

    def test_data_source_needs_sample_license_quote_and_coverage(self):
        need = {
            "need_id": "nfl-more-games-v1",
            "research_question": "Does more independent NFL history improve response prediction?",
            "independent_unit": "game",
            "venues": ["polymarket", "kalshi"],
            "start_date": "2024-09-01",
            "end_date": "2026-02-28",
            "required_fields": ["event", "trade", "bid", "ask", "timestamp"],
            "timestamp_resolution_ms": 1000,
            "minimum_independent_units": 300,
            "minimum_regime_counts": {"scoring_play": 100, "late_game": 100},
            "maximum_quote_usd": 200.0,
            "allowed_use": "research training with local derived-artifact storage",
            "sealed_evaluation_data_requested": False,
        }
        source = {
            "source_id": "vendor-a",
            "provider": "example",
            "source_url": "https://example.com",
            "coverage_start": "2024-09-01",
            "coverage_end": "2026-02-28",
            "acquisition_method": "vendor_sample",
            "provider_trial_terms_reviewed": True,
            "multiple_account_evasion": False,
            "trial_account_owner": None,
            "account_owner_consent_verified": False,
            "provider_terms_allow_team_member_trial": False,
            "organization_trial_limit_respected": True,
            "sample_received": True,
            "sample_sha256": "a" * 64,
            "sample_independent_units": 5,
            "schema_complete": True,
            "timestamp_semantics_verified": True,
            "duplicate_rate": 0.0,
            "missing_rate": 0.01,
            "license_reviewed": True,
            "license_allows_research_storage": False,
            "quote_received": True,
            "quote_usd": 150.0,
            "estimated_total_independent_units": 400,
            "purchase_executed": False,
        }
        blocked = procurement_readiness(need, source)
        self.assertFalse(blocked["ready_to_request_human_purchase_approval"])
        source["license_allows_research_storage"] = True
        ready = procurement_readiness(need, source)
        self.assertTrue(ready["ready_to_request_human_purchase_approval"])
        self.assertFalse(ready["purchase_authorized"])

    def test_multiple_account_trial_evasion_is_rejected(self):
        need = {
            "need_id": "nfl-more-games-v1",
            "research_question": "more games",
            "independent_unit": "game",
            "venues": ["polymarket"],
            "start_date": "2024-09-01",
            "end_date": "2026-02-28",
            "required_fields": ["trade", "timestamp"],
            "timestamp_resolution_ms": 1000,
            "minimum_independent_units": 10,
            "minimum_regime_counts": {"scoring": 3},
            "maximum_quote_usd": 200.0,
            "allowed_use": "research",
            "sealed_evaluation_data_requested": False,
        }
        source = {
            "source_id": "bad-trials", "provider": "example",
            "source_url": "https://example.com", "coverage_start": "2024-09-01",
            "coverage_end": "2026-02-28", "acquisition_method": "single_authorized_trial",
            "provider_trial_terms_reviewed": False, "multiple_account_evasion": True,
            "trial_account_owner": "requester", "account_owner_consent_verified": True,
            "provider_terms_allow_team_member_trial": False,
            "organization_trial_limit_respected": False,
            "sample_received": True, "sample_sha256": "a" * 64,
            "sample_independent_units": 5, "schema_complete": True,
            "timestamp_semantics_verified": True, "duplicate_rate": 0.0,
            "missing_rate": 0.0, "license_reviewed": False,
            "license_allows_research_storage": False, "quote_received": False,
            "quote_usd": 0.0, "estimated_total_independent_units": 10,
            "purchase_executed": False,
        }
        with self.assertRaisesRegex(ValueError, "multiple-account"):
            procurement_readiness(need, source)

    def test_authorized_teammate_trial_is_allowed_with_consent_and_terms(self):
        need = {
            "need_id": "nfl-team-trial-v1", "research_question": "more games",
            "independent_unit": "game", "venues": ["polymarket"],
            "start_date": "2024-09-01", "end_date": "2026-02-28",
            "required_fields": ["trade", "timestamp"], "timestamp_resolution_ms": 1000,
            "minimum_independent_units": 10, "minimum_regime_counts": {"scoring": 3},
            "maximum_quote_usd": 200.0, "allowed_use": "research",
            "sealed_evaluation_data_requested": False,
        }
        source = {
            "source_id": "authorized-teammate-trial", "provider": "example",
            "source_url": "https://example.com", "coverage_start": "2024-09-01",
            "coverage_end": "2026-02-28",
            "acquisition_method": "authorized_team_member_trial",
            "provider_trial_terms_reviewed": True, "multiple_account_evasion": False,
            "trial_account_owner": "authorized_teammate",
            "account_owner_consent_verified": True,
            "provider_terms_allow_team_member_trial": True,
            "organization_trial_limit_respected": True,
            "sample_received": True, "sample_sha256": "b" * 64,
            "sample_independent_units": 5, "schema_complete": True,
            "timestamp_semantics_verified": True, "duplicate_rate": 0.0,
            "missing_rate": 0.0, "license_reviewed": True,
            "license_allows_research_storage": True, "quote_received": True,
            "quote_usd": 0.0, "estimated_total_independent_units": 10,
            "purchase_executed": False,
        }
        readiness = procurement_readiness(need, source)
        self.assertTrue(readiness["checks"]["authorized_team_trial"])
        self.assertTrue(readiness["ready_to_request_human_purchase_approval"])

    def test_teammate_trial_without_consent_is_rejected(self):
        need = {
            "need_id": "nfl-team-trial-v1", "research_question": "more games",
            "independent_unit": "game", "venues": ["polymarket"],
            "start_date": "2024-09-01", "end_date": "2026-02-28",
            "required_fields": ["trade", "timestamp"], "timestamp_resolution_ms": 1000,
            "minimum_independent_units": 10, "minimum_regime_counts": {"scoring": 3},
            "maximum_quote_usd": 200.0, "allowed_use": "research",
            "sealed_evaluation_data_requested": False,
        }
        source = {
            "source_id": "unapproved-teammate-trial", "provider": "example",
            "source_url": "https://example.com", "coverage_start": "2024-09-01",
            "coverage_end": "2026-02-28",
            "acquisition_method": "authorized_team_member_trial",
            "provider_trial_terms_reviewed": True, "multiple_account_evasion": False,
            "trial_account_owner": "authorized_teammate",
            "account_owner_consent_verified": False,
            "provider_terms_allow_team_member_trial": True,
            "organization_trial_limit_respected": True,
            "sample_received": True, "sample_sha256": "c" * 64,
            "sample_independent_units": 5, "schema_complete": True,
            "timestamp_semantics_verified": True, "duplicate_rate": 0.0,
            "missing_rate": 0.0, "license_reviewed": True,
            "license_allows_research_storage": True, "quote_received": True,
            "quote_usd": 0.0, "estimated_total_independent_units": 10,
            "purchase_executed": False,
        }
        with self.assertRaisesRegex(ValueError, "owner's consent"):
            procurement_readiness(need, source)


if __name__ == "__main__":
    unittest.main()
