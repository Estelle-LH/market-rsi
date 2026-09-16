"""A new published harness, the same measured data, and a controller-chosen plan.

No dataset selection/target/parameter is filled in by this preparer. Only the
previously authorized diagnostic boundary and exact current QA are supplied.
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_rsi import digest, file_hash, fresh_json, load_json
from data_scientist_harness.store import create
from data_scientist_harness.release import source_hashes
from controller_dependency_preflight import inspect
from source_scoped_population_review import read_bundle
from paid_budget import PaidBudget
from source_inventory_context import finding as inventory_finding

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT/"artifacts/population-source-controller-20260911-01"
PARENT_MANIFEST = "317931929cb883069a552c817a5de2aa711d1b33c1093c6e1f77df46e7ac8a57"
QA_PATH = ROOT/"artifacts/population-quote-source-qa-20260911-01/bundle.json"
QA_SHA = "8e97ad8104758187a2adbd2d900dc25ecf144adf229176810c6c716fae91be36"
DATES = ["2026-08-21", "2026-08-22", "2026-08-23", "2026-08-24", "2026-08-25", "2026-09-07", "2026-09-08", "2026-09-09"]


def verify_planning_canary(value, release):
    if (value.get("schema") != "source_study_codex_canary_v1" or value.get("passed") is not True
            or value.get("result_sha256") != digest({k: v for k, v in value.items() if k != "result_sha256"})
            or value.get("source_hashes") != source_hashes() or value["source_hashes"] != release["source_hashes"]
            or value.get("actual_codex_cli") is not True or value.get("actual_tinker_calls") != 0
            or value.get("tool_calls") != 6
            or value.get("fits") != 0 or value.get("source_admitted") is not False
            or value.get("model_authorship_proven") is not False):
        raise ValueError("same-source actual planning canary required")


def prepare(output, release_path, planning_canary):
    output, release_path, planning_canary = (Path(p).resolve() for p in (output, release_path, planning_canary))
    if output.exists(): raise ValueError("fresh source-study workspace required")
    bundle = read_bundle(QA_PATH, QA_SHA)
    config = load_json(PARENT/"workspace.json")
    if file_hash(PARENT/"workspace.json") != PARENT_MANIFEST: raise ValueError("old manifest changed")
    for path, sha in config["files"].items():
        if file_hash(path) != sha: raise ValueError("old frozen source/data changed")
    previous = load_json(ROOT/"artifacts/population-source-controller-audit-20260911-01/audit.json")
    if (previous.get("result_sha256") != "592879867adfe0ab8114a69c784ed79a8e475339f259619bdc45839057e0a38e"
            or previous["result_sha256"] != digest({k: v for k, v in previous.items() if k != "result_sha256"})
            or previous["assessment_sha256"] != file_hash(PARENT/"session/assessment.json")
            or previous["process_reaped"] is not True or previous["controller_valid"] is not True):
        raise ValueError("exact prior terminal audit required")
    dependency = inspect(release_path, ROOT/"artifacts/tokenizer-cache")
    release = load_json(release_path); canary = load_json(planning_canary)
    verify_planning_canary(canary, release)
    if canary["assessment_sha256"] != file_hash(planning_canary.parent/"session/assessment.json"):
        raise ValueError("planning canary assessment changed")
    assessment = load_json(planning_canary.parent/"session/assessment.json")
    if (assessment.get("valid") is not True or assessment.get("process_reaped") is not True
            or assessment.get("exit_code") != 0 or assessment.get("turns") != 6 or assessment.get("tool_calls") != 6
            or assessment.get("model_authorship_proven") is not False
            or assessment.get("evidence_mode") != "synthetic_transport_fixture"
            or assessment.get("manifest_sha256") != canary["manifest_sha256"]):
        raise ValueError("planning canary not valid and terminal")
    budget = PaidBudget(ROOT/"artifacts/kalshi-research-glm53-20260907-01/budget").snapshot()
    if any(v["state"] == "dispatched" and "-turn-" in k for k, v in budget["jobs"].items()):
        raise ValueError("another model call is active or unresolved")
    findings = [f for f in load_json(PARENT/"findings.json") if f["id"] != "budget-and-next-decision"]
    findings += [
        {"id": "source-study-planning-now-implemented", "release": release["publication"],
         "problem_fixed": "The prior source-only workbench had no structured source/objective/comparison proposal tool. "
             "New propose_source_study is actually implemented and has passed a real tool-chain canary. "
             "This is human-directed harness work, not your learning or predictive improvement.",
         "next_action": "Use the current aggregate evidence and your research to submit your first concrete study proposal. "
             "Choose the question, source use, target quantity and units, horizon, comparison, diagnostic dates, "
             "split/purge intent and support/refutation rule yourself. A method not yet executable may be proposed, "
             "but will require independent implementation review. Do not substitute another generic whole-day-auditor request for these definitions.",
         "scope": "planning_context lists allowed already-opened diagnostic dates, not measured availability or admitted data. "
             "source.raw_manifest_sha256 commits the evidence you saw, not a complete future training dataset. "
             "Actual selected objects must be enumerated and independently revalidated before execution. "
             "Fit/check dates in this proposal are open diagnostics, not an untouched Dev/Test split.",
         "gates_unchanged": "Proposal registration does not update QA, grant data access, fill missing values, "
             "read a new date or start a worker. End with defer pending independent review; do not claim training occurred."},
        {"id": "last-controller-claims-reviewed-not-rewritten",
         "corrections": [
             "This hour's measured message kinds are book/price_change/last_trade_price/rest_snapshot/tick_size_change. No equity/comment/sports frame was measured.",
             "No exact Yes+No quote invariant is defined. A Gamma response hash is not evidence that its mapping is historical.",
             "More rows cannot select your objective or establish receipt-clock semantics. Separate missing definitions, unavailable source attestations and missing measurements.",
             "The prior three reads delivered18kchars with16kunique; full-page understanding or complete reading was not proven.",
             "Prior research claims remain history; do not copy its unsupported checks as mandatory facts."],
         "instruction": "Address these corrections using evidence. You may read relevant primary methods or reuse actual archived readings with explicit limits. New record_research still needs a successful current read reference; no paper-count quota."},
        {"id": "current-budget-and-authority", "budget": {k: v for k, v in budget.items() if k != "jobs"},
         "limits": "Original $200 ledger, final50/repair20 protected. Actual model tokens are spend, reservations are not. "
             "Only project facts/plans/budgets/paths/history/session may go to Tinker-hosted GLM. No raw prices, keys or hiddenTest. "
             "No purchase or new capture authorized by this preparation. Simulator remains deferred."},
    ]
    archive = PARENT/"round-archive.json"
    context = {"source_id": bundle["source_id"], "raw_manifest_sha256": bundle["raw_manifest"]["sha256"],
               "opened_diagnostic_dates": DATES}
    findings.append(inventory_finding(context))
    manifest = create(output, quality=bundle["quality"], findings=findings, allowed_dates=[], purpose="source_research",
        network=True, release_path=release_path, planning_context=context,
        prior_archives=[{"path": str(archive), "sha256": file_hash(archive)}])
    fresh_json(output/"dependency-preflight.json", dependency)
    receipt = {"schema": "source_study_workspace_preparation_v1", "manifest_sha256": manifest,
        "qa_bundle_sha256": QA_SHA, "parent_manifest_sha256": PARENT_MANIFEST,
        "parent_archive_sha256": file_hash(archive), "preparer_sha256": file_hash(__file__),
        "planning_canary_sha256": file_hash(planning_canary), "planning_context_sha256": digest(context),
        "provider_calls": 0, "fits": 0, "source_admitted": False, "raw_market_data_loaded": False}
    fresh_json(output/"preparation.json", receipt); return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "release", "planning-canary"): p.add_argument("--"+name, type=Path, required=True)
    a = p.parse_args(); print(prepare(a.output, a.release, a.planning_canary))
