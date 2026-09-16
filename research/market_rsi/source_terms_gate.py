#!/usr/bin/env python3
"""Archive a source terms decision before any market-data API request.

This is an engineering safety gate, not legal advice.  It records why a source
may or may not be used by this research pipeline; it never fetches market data.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from market_rsi import digest, fresh_json


SCHEMA = "market_source_terms_gate_controller_evidence_v1"
KALSHI_AGREEMENT_URL = (
    "https://kalshi-public-docs.s3.amazonaws.com/Kalshi-Developer-Agreement.pdf"
)
POLYMARKET_INSTITUTE_DATA_URL = "https://institute.polymarket.com/data"
POLYMARKET_TERMS_URL = "https://polymarket.com/tos"


def _sha256(value: str) -> str:
    if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value):
        raise ValueError("lowercase SHA-256 required")
    return value


def _utc(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("UTC retrieval timestamp required")
    return value


def kalshi_research_terms_gate(*, agreement_sha256: str,
                               retrieved_at_utc: str) -> dict:
    _sha256(agreement_sha256)
    _utc(retrieved_at_utc)
    body = {
        "schema": SCHEMA,
        "source_id": "kalshi-historical-api",
        "provider": "Kalshi",
        "status": "rejected_before_data_access",
        "formal_dataset_ready": False,
        "full_download_authorized": False,
        "source_market_data_contacted": False,
        "agreement": {
            "title": "Kalshi Developer Agreement",
            "version": "v1.1",
            "official_url": KALSHI_AGREEMENT_URL,
            "sha256": agreement_sha256,
            "retrieved_at_utc": retrieved_at_utc,
            "relevant_sections": ["3", "3.1"],
        },
        "reason_codes": [
            "api_use_limited_to_members_own_trading",
            "research_storage_not_permitted_without_prior_written_authorization",
        ],
        "decision": (
            "Do not request or store Kalshi market data for this academic model-research "
            "pipeline unless Kalshi gives prior written authorization for this use."
        ),
        "next_action": (
            "Return this rejection to the controller and choose a source whose license or "
            "terms permit reproducible research storage and model development."
        ),
        "legal_advice": False,
    }
    return {**body, "evidence_sha256": digest(body)}


def polymarket_research_terms_gate(*, institute_page_sha256: str,
                                   terms_page_sha256: str,
                                   retrieved_at_utc: str,
                                   prior_canary_sha256: str) -> dict:
    """Reject further API acquisition when storage/reuse rights stay unclear."""
    for value in (institute_page_sha256, terms_page_sha256, prior_canary_sha256):
        _sha256(value)
    _utc(retrieved_at_utc)
    body = {
        "schema": SCHEMA,
        "source_id": "polymarket-official-apis",
        "provider": "Polymarket",
        "status": "rejected_before_data_access",
        "formal_dataset_ready": False,
        "full_download_authorized": False,
        "source_market_data_contacted": False,
        "scope_note": "No new market-data request was made after the new plan was frozen.",
        "prior_bounded_canary": {
            "exists": True,
            "evidence_sha256": prior_canary_sha256,
            "may_not_be_expanded": True,
        },
        "terms_evidence": [
            {
                "official_url": POLYMARKET_INSTITUTE_DATA_URL,
                "sha256": institute_page_sha256,
                "retrieved_at_utc": retrieved_at_utc,
                "finding": "research_access_and_open_apis_advertised",
            },
            {
                "official_url": POLYMARKET_TERMS_URL,
                "sha256": terms_page_sha256,
                "retrieved_at_utc": retrieved_at_utc,
                "finding": "no_explicit_research_storage_or_redistribution_grant_verified",
            },
        ],
        "reason_codes": [
            "research_access_is_advertised",
            "reproducible_storage_and_redistribution_rights_remain_unresolved",
            "frozen_plan_requires_terms_to_be_resolved_not_pending",
        ],
        "decision": (
            "Do not make new Polymarket API market-data requests under this plan. The public "
            "research guide supports access, but the frozen canary requires an explicit, "
            "resolved basis for reproducible storage; that basis was not verified."
        ),
        "next_action": (
            "Return this rejection to the controller and prefer a versioned dataset with an "
            "explicit research-compatible license."
        ),
        "legal_advice": False,
    }
    return {**body, "evidence_sha256": digest(body)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("kalshi", "polymarket"), required=True)
    parser.add_argument("--agreement-sha256")
    parser.add_argument("--institute-page-sha256")
    parser.add_argument("--terms-page-sha256")
    parser.add_argument("--prior-canary-sha256")
    parser.add_argument("--retrieved-at-utc", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.source == "kalshi":
        if not args.agreement_sha256:
            parser.error("--agreement-sha256 is required for Kalshi")
        report = kalshi_research_terms_gate(
            agreement_sha256=args.agreement_sha256,
            retrieved_at_utc=args.retrieved_at_utc,
        )
    else:
        required = (args.institute_page_sha256, args.terms_page_sha256,
                    args.prior_canary_sha256)
        if not all(required):
            parser.error("Polymarket page and prior-canary hashes are required")
        report = polymarket_research_terms_gate(
            institute_page_sha256=args.institute_page_sha256,
            terms_page_sha256=args.terms_page_sha256,
            retrieved_at_utc=args.retrieved_at_utc,
            prior_canary_sha256=args.prior_canary_sha256,
        )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    fresh_json(args.output, report)
    print(report["evidence_sha256"])


if __name__ == "__main__":
    main()
