"""Bind verified repair aggregates to a fresh, unchanged DSH controller workspace.

Preparation only. No provider calls, raw rows, new data or implicit fit admission.
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_rsi import file_hash, fresh_json, load_json
from data_scientist_harness.store import create
from paid_budget import PaidBudget
from quote_repair_evidence import audit
from controller_dependency_preflight import inspect
from prepare_tonight_design import verify_dependency_receipt

ROOT = Path(__file__).resolve().parents[1]


def prepare(output, run, release, dependency):
    if output.exists(): raise ValueError("fresh workspace required")
    parent = ROOT/"artifacts/source-repair-followup-20260911-01"
    if file_hash(parent/"workspace.json") != "db26ceab18e08cd7a2f18a06c90aa3164b65e832078052798a06e32baed89dd6":
        raise ValueError("parent manifest changed")
    config = load_json(parent/"workspace.json")
    for path, sha in config["files"].items():
        if file_hash(path) != sha: raise ValueError("frozen parent changed")
    assessment = load_json(parent/"session/assessment.json")
    if assessment.get("valid") is not True or assessment.get("process_reaped") is not True:
        raise ValueError("previous controller not complete")
    verified, findings = audit(run)
    verify_dependency_receipt(load_json(dependency), inspect(release, ROOT/"artifacts/tokenizer-cache"))
    budget = PaidBudget(ROOT/"artifacts/kalshi-research-glm53-20260907-01/budget").snapshot()
    if any(v["state"] == "dispatched" and "-turn-" in k for k, v in budget["jobs"].items()):
        raise ValueError("unresolved model call; do not duplicate")
    findings.append({"id": "unchanged-harness-budget-and-current-purpose",
        "harness": "dsh-v1.2.4", "source_adapter": "pm-source-quotes-v0.1.0",
        "budget": {k: v for k, v in budget.items() if k != "jobs"},
        "instructions": "Continue from archived research and NEW verified engineering results. "
            "Source BBO repair has been implemented and measured, so do not ask to repeat the same case study. "
            "Use the evidence to decide the next useful data-science work. Explain what remains missing and "
            "what would make an experiment informative. A source quality issue is not proof of weak learner performance. "
            "No runner-selected target, horizon or trainer is supplied. No data is admitted to fit. "
            "Archive the first supported decision; do not reinterpret archive assertions as current QA.",
        "authorization": "Same original $200 Tinker budget and previously authorized project summaries/plans/budget/paths/archive/session. "
            "No keys, raw market rows or hidden tests are model inputs. No additional model/provider authorization inferred.",
        "protected_budget": "Final $50 and repair $20 remain protected. Reservation is not consumption."})
    archive = parent/"round-archive.json"
    manifest = create(output, quality=config["quality"], findings=findings, allowed_dates=[],
        purpose="source_research", network=True, release_path=release,
        prior_archives=[{"path": str(archive), "sha256": file_hash(archive)}])
    receipt = {"schema": "quote_repair_workspace_preparation_v1", "manifest_sha256": manifest,
        "report_sha256": verified["report_file_sha256"], "parent_archive_sha256": file_hash(archive),
        "preparer_sha256": file_hash(__file__), "evidence_adapter_sha256": file_hash(Path(__file__).with_name("quote_repair_evidence.py")),
        "dependency_receipt_sha256": file_hash(dependency), "provider_calls": 0, "fits": 0,
        "raw_rows_uploaded": 0, "source_admitted": False}
    fresh_json(output/"preparation.json", receipt)
    return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "run", "release", "dependency"): p.add_argument("--"+name, type=Path, required=True)
    a = p.parse_args(); print(prepare(a.output.resolve(), a.run.resolve(), a.release.resolve(), a.dependency.resolve()))
