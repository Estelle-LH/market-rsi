"""Prepare the next aggregate-only NFL controller after the Push entitlement block.

This adapter carries the immutable Train-only experiment summaries, the bounded
post-hoc live audit, and one exact entitlement preflight into a fresh workspace.
It also exposes runner-reviewed primary-source facts about legal source
alternatives.  It admits no raw rows, credentials, Route-Dev, Final, fitting,
capture, account creation, purchase, or provider side effect.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_tools.prepare_sports_aggregate_controller import BUDGET
from audit_tools.prepare_sports_live_timing_feedback_controller import (
    AUDIT_EXPECTED,
    ORIGINAL_EXPECTED,
    FEEDBACK_EXPECTED,
    ROBUSTNESS_EXPECTED,
    build_live_findings,
    load_frozen_run,
    load_feedback_run,
    load_live_audit,
    load_robustness,
    build_robustness_findings,
    public_receipts,
)
from data_scientist_harness.store import create
from market_rsi import file_hash, fresh_json, load_json
from paid_budget import PaidBudget


ROOT = Path(__file__).resolve().parents[1]
ENTITLEMENT = (
    ROOT / "artifacts/nfl-sportradar-push-entitlement-preflight-20260916-01/entitlement.json"
)
ENTITLEMENT_EXPECTED = {
    "path": ENTITLEMENT,
    "sha256": "c3d05a0799430b93ce376917e6d3694e31b6551b1e19412019278202726bc927",
    "schema": "sportradar_push_entitlement_preflight_v1",
}


def load_entitlement(spec=ENTITLEMENT_EXPECTED):
    path = Path(spec["path"]).resolve()
    if file_hash(path) != spec["sha256"]:
        raise ValueError("Push entitlement receipt changed")
    value = load_json(path)
    if value.get("schema") != spec["schema"]:
        raise ValueError("Push entitlement schema changed")
    required = {
        "access": "trial",
        "http_status": 403,
        "redirect_present": False,
        "stream_entitlement_observed": False,
        "api_key_persisted": False,
        "signed_redirect_persisted": False,
        "provider_sla_proven": False,
        "market_lead_proven": False,
    }
    if any(value.get(key) != expected for key, expected in required.items()):
        raise ValueError("Push entitlement boundary changed")
    if value.get("redirect_host") or value.get("redirect_scheme"):
        raise ValueError("blocked preflight cannot persist redirect details")
    return value, {"path": str(path), "sha256": spec["sha256"]}


def build_source_blocker_findings(prior, entitlement, budget):
    budget_public = {key: value for key, value in budget.items() if key != "jobs"}
    without_old_next = [row for row in prior if row["id"] != "next-controller-decision"]
    return without_old_next + [
        {
            "id": "push-entitlement-preflight",
            "observed": (
                "One exact Sportradar NFL Push Events trial preflight returned HTTP 403, "
                "with no redirect and no observed stream entitlement."
            ),
            "safe_handling": {
                "api_key_persisted": entitlement["api_key_persisted"],
                "signed_redirect_persisted": entitlement["signed_redirect_persisted"],
                "retry_count": 0,
            },
            "claim_boundary": (
                "This proves only that this trial lacked observed Push entitlement at that "
                "request. It does not refute Push product fields, measure latency, or show "
                "that another authorized product is unavailable."
            ),
        },
        {
            "id": "public-source-alternative-research",
            "accessed_utc_date": "2026-09-16",
            "sources": [
                {
                    "evidence_type": "runner_verified_primary_source_fact",
                    "url": "https://sportsdata.io/developers/apis",
                    "read": "Testing Options: Free Trial, Replay, Production Key",
                    "finding": (
                        "Free Trial data is scrambled; Replay serves authentic historical "
                        "play-by-play on the live-feed schedule in the production format."
                    ),
                    "transfer_limit": (
                        "Replay can test capture and update handling, not current-game market "
                        "lead, production entitlement, or live latency."
                    ),
                },
                {
                    "evidence_type": "runner_verified_primary_source_fact",
                    "url": "https://sportsdata.io/developers",
                    "read": "Discovery Lab, Leagues API, Vault / Historical Data",
                    "finding": (
                        "Discovery Lab offers real next-day NFL data and a free last-season "
                        "tier; deep real-time play-by-play requires the commercial Leagues API."
                    ),
                    "transfer_limit": (
                        "The public page does not establish exact NFL field coverage, research "
                        "storage rights for our use, provider timestamps, or a quoted price."
                    ),
                },
                {
                    "evidence_type": "runner_verified_primary_source_fact",
                    "url": "https://sportsdata.io/help/refresh-rates-feeds-and-timing",
                    "read": "Play-By-Play and Scores timing",
                    "finding": (
                        "The provider describes real-time PBP updates, a 3-second minimum cache, "
                        "and common updates 20-30 seconds from cable/OTA broadcast."
                    ),
                    "transfer_limit": (
                        "Documentation is not a measured publish-to-receive distribution, SLA, "
                        "clock-synchronization proof, or evidence of lead over our market."
                    ),
                },
                {
                    "evidence_type": "runner_verified_primary_source_fact",
                    "url": "https://developer.opticodds.com/docs/odds-api-getting-started-guide",
                    "read": "Real-time streaming, results stream, historical odds",
                    "finding": (
                        "OpticOdds documents SSE odds/results streams and timestamped historical "
                        "price changes, locks, unlocks, and settlements."
                    ),
                    "transfer_limit": (
                        "An odds/results stream is not a full NFL play-by-play source and does "
                        "not by itself provide the missing state primitives."
                    ),
                },
            ],
        },
        {
            "id": "next-controller-decision",
            "budget": budget_public,
            "instructions": (
                "Choose exactly one next high-information stage after reading relevant primary "
                "sources. The 403 blocks only the attempted Push trial. Consider a legal Replay "
                "capture canary, another source with sample/license/quote gates, a market-response "
                "stage using actually available clocks, a finite opened-Train target/horizon "
                "study, a fixed new algorithm addressing an observed failure, or a better option. "
                "Do not assume 5s, 30s, 60s, one-hour windows, a provider threshold, or one named "
                "method is correct. Archive the chosen proposal, unchanged parent, exactly one "
                "changed scientific stage, data boundary, reward chosen before score, support and "
                "refutation rules, cost bound, and direction flip. This aggregate-only workspace "
                "cannot collect feeds, fit, create accounts, purchase, or open Route-Dev/Final."
            ),
        },
    ]


def prepare(output, release, original_expected=ORIGINAL_EXPECTED,
            feedback_expected=FEEDBACK_EXPECTED,
            robustness_expected=ROBUSTNESS_EXPECTED,
            audit_expected=AUDIT_EXPECTED,
            entitlement_expected=ENTITLEMENT_EXPECTED, budget_path=BUDGET):
    output, release = Path(output).resolve(), Path(release).resolve()
    if output.exists():
        raise ValueError("fresh workspace required")
    grid = load_frozen_run(original_expected["grid"])
    same = load_frozen_run(original_expected["same"])
    representation = load_feedback_run(feedback_expected["representation"])
    trainer = load_feedback_run(feedback_expected["trainer"])
    robustness = load_robustness(robustness_expected)
    audit, audit_receipt = load_live_audit(audit_expected)
    entitlement, entitlement_receipt = load_entitlement(entitlement_expected)
    budget = PaidBudget(Path(budget_path).resolve()).snapshot()
    if any(value["state"] == "dispatched" and "-turn-" in job
           for job, value in budget["jobs"].items()):
        raise ValueError("active or unresolved model dispatch; never duplicate")
    robust = build_robustness_findings(
        grid, same, representation, trainer, robustness, budget)
    live = build_live_findings(robust, audit, budget)
    findings = build_source_blocker_findings(live, entitlement, budget)
    receipts = (
        public_receipts(grid, same, representation, trainer, robustness)
        + [audit_receipt, entitlement_receipt]
    )
    manifest = create(
        output, quality=None, findings=findings, allowed_dates=[],
        purpose="aggregate_research", network=True, release_path=release,
        aggregate_receipts=receipts,
    )
    receipt = {
        "schema": "sports_source_blocker_feedback_controller_preparation_v1",
        "manifest_sha256": manifest,
        "finding_count": len(findings),
        "aggregate_receipts": receipts,
        "preparer_sha256": file_hash(__file__),
        "raw_rows_admitted": 0,
        "split_identifiers_admitted": 0,
        "route_dev_opened": False,
        "sealed_final_opened": False,
        "provider_calls": 0,
        "fits": 0,
        "account_actions": 0,
        "purchases": 0,
        "prepared_not_dispatched": True,
    }
    fresh_json(output / "preparation.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.output, args.release))
