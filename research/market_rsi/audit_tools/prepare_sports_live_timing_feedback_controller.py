"""Prepare aggregate-only live-timing feedback for the next NFL controller.

No raw event, game/play identifier, split lock, Route-Dev, Final or training
entrypoint is copied. The adapter binds a post-hoc aggregate audit to the
published Data Scientist Harness release and lets the controller choose one
next scientific stage; it does not execute that choice.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_tools.prepare_sports_aggregate_controller import (
    BUDGET,
    EXPECTED as ORIGINAL_EXPECTED,
    load_frozen_run,
)
from audit_tools.prepare_sports_aggregate_feedback_controller import (
    FEEDBACK_EXPECTED,
    load_feedback_run,
)
from audit_tools.prepare_sports_robustness_feedback_controller import (
    ROBUSTNESS_EXPECTED,
    build_findings as build_robustness_findings,
    load_robustness,
    public_receipts,
)
from data_scientist_harness.store import create
from market_rsi import file_hash, fresh_json, load_json
from paid_budget import PaidBudget


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "artifacts/nfl-live-timing-posthoc-denkc-20260916-02/audit.json"
AUDIT_EXPECTED = {
    "path": AUDIT,
    "file_sha256": "dd181ef2573ced25a7dea3b695b911572faa727f4550072ea9a1bdeccb92f2b4",
    "report_sha256": "139af69888a37b613cd7550732dbe4788ec0e900490fe1e1de131551ea5fb162",
    "schema": "live_pbp_capture_audit_v1",
}


def load_live_audit(spec=AUDIT_EXPECTED):
    path = Path(spec["path"]).resolve()
    if file_hash(path) != spec["file_sha256"]:
        raise ValueError("live timing audit file changed")
    body = load_json(path)
    if (body.get("schema") != spec["schema"]
            or body.get("report_sha256") != spec["report_sha256"]):
        raise ValueError("live timing audit identity changed")
    if body.get("evidence_status") != "post_hoc_existing_case":
        raise ValueError("live timing feedback must preserve post-hoc boundary")
    access = body.get("data_access", {})
    if (access.get("train_opened") is not False
            or access.get("dev_opened") is not False
            or access.get("final_opened") is not False
            or access.get("prediction_fit_run") is not False
            or str(access.get("provider_cost_usd")) not in {"0", "0.0"}):
        raise ValueError("live timing feedback must be zero-score aggregate evidence")
    if body.get("identifiers_exported") is not False:
        raise ValueError("identifier-free audit required")
    return body, {"path": str(path), "sha256": spec["file_sha256"]}


def build_live_findings(prior, audit, budget):
    budget_public = {key: value for key, value in budget.items() if key != "jobs"}
    return prior[:-1] + [
        {
            "id": "post-hoc-live-capture-audit",
            "evidence_status": audit["evidence_status"],
            "counts": audit["counts"],
            "clock_fields": audit["clock_fields"],
            "feature_fields": audit["feature_fields"],
            "provider_event_start_to_receive_descriptive_ms": (
                audit["provider_event_start_to_receive_descriptive_ms"]),
            "scoring_event_start_to_receive_descriptive_ms": (
                audit["scoring_event_start_to_receive_descriptive_ms"]),
            "http_round_trip_descriptive_ms": audit["http_round_trip_descriptive_ms"],
            "claim_boundaries": audit["claim_boundaries"],
            "observed": (
                "The existing public ESPN capture mechanically recorded 62 live plays "
                "with local receive time, but none had provider publish time, start/end "
                "state, win probability, or an explicit correction schema. Event-start "
                "to receive is descriptive and cannot measure strict feed latency."
            ),
            "boundary": (
                "This is one already-opened game. It is post-hoc source diagnosis, not "
                "independent confirmation, a latency SLA, prediction evidence or PnL."
            ),
        },
        {
            "id": "public-source-capability-research",
            "accessed_utc_date": "2026-09-16",
            "sources": [
                {
                    "evidence_type": "runner_verified_primary_source_fact",
                    "url": "https://developer.sportradar.com/football/reference/nfl-play-by-play",
                    "read": "Update Frequency",
                    "finding": "Official NFL PBP says live in-progress TTL is 3 seconds and recommends requests every 3 seconds.",
                    "transfer_limit": "Documentation is not our measured receive latency or account entitlement.",
                },
                {
                    "evidence_type": "runner_verified_primary_source_fact",
                    "url": "https://developer.sportradar.com/football/v6/reference/nfl-push-events",
                    "read": "Product summary, subscription example and data points",
                    "finding": "Push Events is described as real-time and exposes created_at, updated_at, wall_clock and review/reversal fields.",
                    "transfer_limit": "Access, SLA, cost and field completeness need a prospective canary.",
                },
                {
                    "evidence_type": "runner_verified_primary_source_fact",
                    "url": "https://docs.polymarket.com/api-reference/wss/market",
                    "read": "Market channel messages",
                    "finding": "Market messages carry provider timestamps; local receive still must be recorded separately.",
                    "transfer_limit": "Timestamp presence alone does not prove synchronized clocks, fills or PnL.",
                },
                {
                    "evidence_type": "runner_verified_primary_source_fact",
                    "url": "https://github.com/nflverse/nflverse-data/blob/main/README.Rmd",
                    "read": "Play by Play update schedule",
                    "finding": "Raw JSON usually appears 1-2 hours after a game.",
                    "transfer_limit": "Useful for history/backfill, not live market-lead timing.",
                },
            ],
        },
        {
            "id": "harness-v1.6.5-boundary",
            "rules": [
                "Separate event-start, provider-publish, local-receive, decision and label clocks.",
                "Treat capture integrity, strict latency, market lead and independent confirmation as separate gates.",
                "Opened-Train may compare a finite predeclared horizon grid; freeze the grid, selection rule and primary reward before stage score.",
                "Protected confirmation carries exactly one frozen horizon; never select a horizon after its protected score.",
                "A synthetic contract probe does not admit a source, support a threshold or prove market lead.",
            ],
        },
        {
            "id": "next-controller-decision",
            "budget": budget_public,
            "instructions": (
                "Choose exactly one next executable scientific stage after researching "
                "relevant primary sources. You may (A) define a prospective parallel "
                "source canary, (B) propose a live-feasible representation that excludes "
                "unavailable state_wp_delta, (C) propose a target/horizon grid or fixed "
                "new algorithm that addresses an observed failure mode, or propose a "
                "better option. Do not assume 5s, 30s, 60s or 90% is correct. Freeze the "
                "unchanged parent, one changed stage, finite horizon scope, primary "
                "reward, support/refutation rule, data boundary and cost bound before "
                "score. Name what result would change direction. This aggregate-only "
                "workspace cannot collect feeds, fit, train or open Route-Dev/Final; "
                "archive one proposal and defer."
            ),
        },
    ]


def prepare(output, release, original_expected=ORIGINAL_EXPECTED,
            feedback_expected=FEEDBACK_EXPECTED,
            robustness_expected=ROBUSTNESS_EXPECTED,
            audit_expected=AUDIT_EXPECTED, budget_path=BUDGET):
    output, release = Path(output).resolve(), Path(release).resolve()
    if output.exists():
        raise ValueError("fresh workspace required")
    grid = load_frozen_run(original_expected["grid"])
    same = load_frozen_run(original_expected["same"])
    representation = load_feedback_run(feedback_expected["representation"])
    trainer = load_feedback_run(feedback_expected["trainer"])
    robustness = load_robustness(robustness_expected)
    audit, audit_receipt = load_live_audit(audit_expected)
    budget = PaidBudget(Path(budget_path).resolve()).snapshot()
    if any(value["state"] == "dispatched" and "-turn-" in job
           for job, value in budget["jobs"].items()):
        raise ValueError("active or unresolved model dispatch; never duplicate")
    prior = build_robustness_findings(
        grid, same, representation, trainer, robustness, budget)
    findings = build_live_findings(prior, audit, budget)
    receipts = public_receipts(
        grid, same, representation, trainer, robustness) + [audit_receipt]
    manifest = create(
        output, quality=None, findings=findings, allowed_dates=[],
        purpose="aggregate_research", network=True, release_path=release,
        aggregate_receipts=receipts,
    )
    receipt = {
        "schema": "sports_live_timing_feedback_controller_preparation_v2",
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
