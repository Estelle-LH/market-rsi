"""Schema gates for a strong-harness data-acquisition proposal.

This module never buys or downloads data.  It makes the need, sample evidence,
license, quote and approval states explicit before an external side effect.
"""
from __future__ import annotations


REQUIRED_NEED_FIELDS = {
    "need_id", "research_question", "independent_unit", "venues",
    "start_date", "end_date", "required_fields", "timestamp_resolution_ms",
    "minimum_independent_units", "minimum_regime_counts", "maximum_quote_usd",
    "allowed_use", "sealed_evaluation_data_requested",
}

REQUIRED_SOURCE_FIELDS = {
    "source_id", "provider", "source_url", "coverage_start", "coverage_end",
    "acquisition_method", "provider_trial_terms_reviewed", "multiple_account_evasion",
    "trial_account_owner", "account_owner_consent_verified",
    "provider_terms_allow_team_member_trial", "organization_trial_limit_respected",
    "sample_received", "sample_sha256", "sample_independent_units",
    "schema_complete", "timestamp_semantics_verified", "duplicate_rate",
    "missing_rate", "license_reviewed", "license_allows_research_storage",
    "quote_received", "quote_usd", "estimated_total_independent_units",
    "purchase_executed",
}


def validate_need(need: dict) -> None:
    if set(need) != REQUIRED_NEED_FIELDS:
        raise ValueError("data need must use the exact schema")
    if need["sealed_evaluation_data_requested"] is not False:
        raise ValueError("data acquisition cannot request sealed evaluation data")
    if need["minimum_independent_units"] <= 0 or need["timestamp_resolution_ms"] <= 0:
        raise ValueError("positive sample size and timestamp resolution required")
    if need["maximum_quote_usd"] < 0:
        raise ValueError("negative quote cap")
    if not need["venues"] or not need["required_fields"] or not need["minimum_regime_counts"]:
        raise ValueError("venues, fields and regime coverage are required")
    if not need["allowed_use"]:
        raise ValueError("intended data use must be explicit")


def validate_source(source: dict) -> None:
    if set(source) != REQUIRED_SOURCE_FIELDS:
        raise ValueError("source evidence must use the exact schema")
    if source["purchase_executed"] is not False:
        raise ValueError("source comparison must happen before purchase")
    if source["multiple_account_evasion"] is not False:
        raise ValueError("multiple-account trial evasion is not an allowed acquisition method")
    if source["acquisition_method"] not in {
        "public_archive", "official_public_api", "single_authorized_trial",
        "authorized_team_member_trial",
        "vendor_sample", "academic_research_access", "paid_slice", "owned_live_capture",
    }:
        raise ValueError("unknown acquisition method")
    if source["trial_account_owner"] not in {None, "requester", "authorized_teammate"}:
        raise ValueError("unknown trial account owner")
    if source["acquisition_method"] == "authorized_team_member_trial":
        if source["trial_account_owner"] != "authorized_teammate":
            raise ValueError("team-member trial must belong to an authorized teammate")
        if not source["account_owner_consent_verified"]:
            raise ValueError("team-member trial requires the account owner's consent")
        if not source["provider_trial_terms_reviewed"]:
            raise ValueError("team-member trial requires reviewed provider terms")
        if not source["provider_terms_allow_team_member_trial"]:
            raise ValueError("provider terms do not allow this team-member trial")
        if not source["organization_trial_limit_respected"]:
            raise ValueError("organization-level trial limit is not respected")
    if source["sample_received"] and not source["sample_sha256"]:
        raise ValueError("received sample needs a hash")
    for key in ("duplicate_rate", "missing_rate"):
        if not 0 <= source[key] <= 1:
            raise ValueError("data-quality rate must be in [0,1]")
    if source["quote_usd"] < 0 or source["estimated_total_independent_units"] < 0:
        raise ValueError("invalid quote or coverage")


def procurement_readiness(need: dict, source: dict) -> dict:
    validate_need(need)
    validate_source(source)
    checks = {
        "sample_received": source["sample_received"],
        "schema_complete": source["schema_complete"],
        "timestamp_semantics_verified": source["timestamp_semantics_verified"],
        "license_reviewed": source["license_reviewed"],
        "license_allows_research_storage": source["license_allows_research_storage"],
        "provider_trial_terms_reviewed": source["provider_trial_terms_reviewed"],
        "authorized_team_trial": (
            source["acquisition_method"] != "authorized_team_member_trial"
            or (
                source["trial_account_owner"] == "authorized_teammate"
                and source["account_owner_consent_verified"]
                and source["provider_terms_allow_team_member_trial"]
                and source["organization_trial_limit_respected"]
            )
        ),
        "quote_received": source["quote_received"],
        "within_quote_cap": source["quote_usd"] <= need["maximum_quote_usd"],
        "enough_independent_units": (
            source["estimated_total_independent_units"] >= need["minimum_independent_units"]
        ),
        "sample_has_multiple_units": source["sample_independent_units"] >= 3,
        "duplicate_rate_acceptable": source["duplicate_rate"] <= 0.01,
        "missing_rate_acceptable": source["missing_rate"] <= 0.10,
    }
    return {
        "schema": "data_procurement_readiness_v1",
        "need_id": need["need_id"],
        "source_id": source["source_id"],
        "checks": checks,
        "ready_to_request_human_purchase_approval": all(checks.values()),
        "purchase_authorized": False,
        "purchase_executed": False,
        "note": "Readiness is not purchase authorization or data admission.",
    }
