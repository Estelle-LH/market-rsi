"""Prepare source-scoped D10 evidence in the unchanged published DSH; no call.

Do not use old repair/tonight preparation scripts for this source continuation:
they inherited the Vantage quality pointer. Old frozen workspaces stay intact.
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_scientist_harness.store import create
from market_rsi import file_hash, fresh_json, load_json
from paid_budget import PaidBudget
from controller_dependency_preflight import inspect
from source_scoped_population_review import read_bundle, verify_current_quality

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT/"artifacts/quote-repair-controller-20260911-01"
PARENT_SHA = "c47e6027e4ebf0546699706ee3ccb797a07d2acfcdfe68f51fcfd8dcc915a2cd"


def prepare(output, bundle_path, bundle_sha, release):
    output, bundle_path, release = (Path(v).resolve() for v in (output, bundle_path, release))
    if output.exists(): raise ValueError("fresh workspace required")
    bundle = read_bundle(bundle_path, bundle_sha)
    if file_hash(PARENT/"workspace.json") != PARENT_SHA: raise ValueError("parent manifest changed")
    config = load_json(PARENT/"workspace.json")
    for path, sha in config["files"].items():
        if file_hash(path) != sha: raise ValueError("frozen parent changed")
    assessment = load_json(PARENT/"session/assessment.json")
    if assessment.get("valid") is not True or assessment.get("process_reaped") is not True:
        raise ValueError("previous controller not terminal")
    dependency = inspect(release, ROOT/"artifacts/tokenizer-cache")
    budget = PaidBudget(ROOT/"artifacts/kalshi-research-glm53-20260907-01/budget").snapshot()
    if any(v["state"] == "dispatched" and "-turn-" in k for k, v in budget["jobs"].items()):
        raise ValueError("active/unresolved model turn; never duplicate")
    population = load_json(bundle["audit"]["path"])
    measured = load_json(bundle["report"]["path"])["profile"]
    findings = [
        {"id": "current-d10-source-scoped-qa", "source_id": bundle["source_id"],
         "scope_id": bundle["scope_id"], "raw_manifest": bundle["raw_manifest"],
         "audited_population": population, "qa_bundle_sha256": bundle_sha,
         "aggregate_event_counts": measured["totals"], "message_kind_counts": measured["message_kinds"],
         "source_report_sha256": bundle["report"]["sha256"],
         "interpretation": "This complete raw hourly object is new aggregate evidence from already opened data, "
             "not a complete day or a training source. Every unresolved DSH check remains unknown. "
             "No source_plan/objective/replay/features/split/trainer was invented by the runner."},
        {"id": "stale-source-review-correction", "history": bundle["historical_source_review"],
         "problem": "Previous workspace quality pointed to Vantage/oraclemangle source-plan QA. "
             "Its six candidate dates and 617 event-minutes are not current D10 coverage. "
             "Old controller responses and archives are preserved, not retroactively repaired.",
         "handling": "inspect_harness now receives this D10-specific diagnostic QA. "
             "No check was changed to pass. The new preparation path rejects other source/scope bindings."},
        {"id": "independent-review-of-prior-capability-request",
         "observations": [
             "A complete first-hour all-token audit has now executed. Do not request the identical pilot/case again.",
             "The requested whole-day/multi-day auditor is not complete; no historical clock/identity attestation is supplied.",
             "Observed gaps or absent files do not identify outages without capture/heartbeat evidence.",
             "File mtime does not prove event/receipt-clock semantics; current Gamma does not prove historical mappings.",
             "Yes/No quotes are not required to sum exactly to one; source BBO is distinct from reconstructed sizes.",
             "Market WSS and RTDS/sports endpoints must not be treated as one shared connection without evidence.",
             "Equal adjacent midpoints, including same-ms pairs, are not future-target no-change labels or effective N."],
         "authority": "Runner engineering review, not a rewritten controller response. Unknowns remain unknown."},
        {"id": "budget-and-next-decision", "budget": {k: v for k, v in budget.items() if k != "jobs"},
         "instructions": "Use current evidence and the archive to propose the next verifiable data-science action. "
             "State what is measured, still missing, and which evidence would change the next decision. "
             "Do not interpret a fixed adapter or a source defect as proof of predictive improvement/weakness. "
             "The controller retains responsibility for source/sampling/objective/features/model choices. "
             "No admitted cache, fit, sealed Test, new data purchase or further budget is authorized by this preparation.",
         "bounds": "Previously opened diagnostic dates only Aug21..25/Sep07..09; protect Aug26..Sep06. "
             "Final requires at least20 untouched sessions. Original $200 ledger, final50/repair20 protected; reservation is not spend."},
    ]
    archive = PARENT/"round-archive.json"
    manifest = create(output, quality=bundle["quality"], findings=findings, allowed_dates=[],
        purpose="source_research", network=True, release_path=release,
        prior_archives=[{"path": str(archive), "sha256": file_hash(archive)}])
    current = load_json(output/"workspace.json")
    verify_current_quality(current["quality"], expected_scope=bundle["scope_id"],
                           expected_raw_manifest_sha=bundle["raw_manifest"]["sha256"])
    fresh_json(output/"dependency-preflight.json", dependency)
    receipt = {"schema": "population_source_workspace_preparation_v1", "manifest_sha256": manifest,
        "qa_bundle_sha256": bundle_sha, "parent_manifest_sha256": PARENT_SHA,
        "parent_archive_sha256": file_hash(archive), "preparer_sha256": file_hash(__file__),
        "review_adapter_sha256": file_hash(Path(__file__).with_name("source_scoped_population_review.py")),
        "dependency_receipt_sha256": file_hash(output/"dependency-preflight.json"),
        "source_admitted": False, "provider_calls": 0, "fits": 0, "raw_rows_uploaded": 0,
        "prepared_not_dispatched": True, "next_paid_call_requires_actionable_new_evidence_and_budget_gate": True}
    fresh_json(output/"preparation.json", receipt)
    return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "bundle", "release"): p.add_argument("--"+name, type=Path, required=True)
    p.add_argument("--bundle-sha256", required=True)
    a = p.parse_args(); print(prepare(a.output, a.bundle, a.bundle_sha256, a.release))
