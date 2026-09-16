"""One evidence-bound continuation of completed03, with unchanged DSH1.4.0.

Keep every prior finding/archive. Expose the real finite file inventory and
counterexample; do not pick a scientific target, tolerance, file, or trainer.
"""
import argparse
from pathlib import Path
from market_rsi import digest, file_hash, fresh_json, load_json
from data_scientist_harness.store import Store, create
from data_scientist_harness.source_study import current
from data_scientist_harness.io_preflight import require_budget_resident
from paid_budget import PaidBudget
from controller_dependency_preflight import inspect
from finding_aliases import alias_findings
from prepare_source_study_revision_workspace import merge_findings
from source_inventory_context import INVENTORY, SHA, summarize
from source_study_object_scope import scope_for_plan
from temporal_span_review import review as span_review

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "artifacts/temporal-source-controller-20260913-03"
MANIFEST = "13ecf5f7f73d81e91985a42831ee9fad735102e7148dc24732bf327e28474c2e"
PROPOSAL = "3eb1af0bc963d560479787248a4615e32a823e4bf8d8a278bdf1b68d744562d9"
AUDIT = ROOT / "artifacts/temporal-source-controller-audit-20260913-03/audit.json"
AUDIT_HASH = "e2230c1c4f6954a7f4ae35a64237cff01099aa74396e9552167f0c23f542958d"
SPAN = ROOT / "artifacts/temporal-span-review-20260913-03/review.json"
SPAN_HASH = "c64104586e95ccb99711593e368e47e2fa02e0f863d7b503251bb2b44d390114"
BUDGET = ROOT / "artifacts/kalshi-research-glm53-20260907-01/budget"
AUTH = "d5bcc2d00a3b574485252693c4ba07b3a4a3ab9e083ac3bbbc1d8b30e556a8f9"


def unalias(findings):
    originals = []
    for i, f in enumerate(findings, 1):
        if (set(f) != {"id", "source_finding", "source_finding_sha256", "id_scope"}
                or f["id"] != f"f{i:03d}"
                or f["source_finding_sha256"] != digest(f["source_finding"])):
            raise ValueError("exact verified parent aliases required")
        originals.append(f["source_finding"])
    if not originals or len({f["id"] for f in originals}) != len(originals):
        raise ValueError("unique nonempty original findings required")
    return originals


def checked_result(path, expected):
    v = load_json(path)
    if v.get("result_sha256") != expected or digest({k:x for k,x in v.items() if k!="result_sha256"}) != expected:
        raise ValueError("pinned result changed")
    return v


def prepare(output):
    output = Path(output).resolve()
    if output.exists(): raise ValueError("fresh feedback workspace required")
    require_budget_resident(BUDGET)
    if file_hash(BUDGET / "authorization.json") != AUTH: raise ValueError("budget authority changed")
    budget = PaidBudget(BUDGET).snapshot()
    if any(v["state"]=="dispatched" and "-turn-" in k for k,v in budget["jobs"].items()):
        raise ValueError("active or unresolved model dispatch")
    store = Store(PARENT, MANIFEST)
    audited = checked_result(AUDIT, AUDIT_HASH)
    assessment = load_json(PARENT / "session/assessment.json")
    if (current(store) != {"path":str(PARENT / "source-study-proposal.json"), "sha256":PROPOSAL}
            or audited["manifest_sha256"]!=MANIFEST or audited["fits_completed"]!=0
            or not audited["controller_valid"] or not audited["process_reaped"]
            or audited["assessment_sha256"]!=file_hash(PARENT / "session/assessment.json")
            or not assessment["valid"] or not assessment["process_reaped"] or assessment["exit_code"]!=0):
        raise ValueError("exact first proposal and terminal parent required")
    span = checked_result(SPAN, SPAN_HASH)
    if span != span_review(PARENT, "0007"): raise ValueError("counterexample cannot be reproduced")
    if file_hash(INVENTORY) != SHA: raise ValueError("inventory changed")
    inventory = load_json(INVENTORY)
    context = store.config["planning_context"]
    summarize(inventory, context["opened_diagnostic_dates"])
    proposal = load_json(PARENT / "source-study-proposal.json")["proposal"]
    scope = scope_for_plan(store, proposal, context["opened_diagnostic_dates"])
    review = {
        "id":"independent-temporal-executable-review",
        "origin":"human_directed_independent_review_not_controller_decision",
        "parent_manifest_sha256":MANIFEST, "parent_proposal":proposal,
        "audit_ref":{"path":str(AUDIT),"sha256":file_hash(AUDIT)},
        "span_counterexample":span,
        "object_scope":{k:v for k,v in scope.items() if not k.endswith("inventory_objects")},
        "issues":[
            "Horizon60000 with backward tolerance59999 allows actual observed span1ms, as the same-code counterexample proves. It is not necessarily a bad recorded-observation target, but it cannot be called an exact60s price. Explain/retain with an explicit variable-span claim OR revise with a research justification. Reviewer does not choose tolerance/horizon.",
            "The probe tests only start-quote availability and finite single-entity cases, not your actual60s lag builder, all clocks, multi-token ties, or full stream closure. Do not call it full feature causality evidence.",
            "Removing two dates with no files leaves exactly122files and11,889,232,674bytes. The proposed six-date replay is not a smaller executable next operation. Only one file is content-bound. Name an exact bounded operation, not another generic full replay.",
            "Hashing an existing file can establish its current content identity, but cannot prove original capture clocks or continuity. Distinguish original producer metadata/logs from a read-only hash operation and price statistics; identify which evidence your precise claim needs.",
            "Current trainer accepts admitted millisecond-grid inputs, not this raw recorded-event source. A new deterministic materializer and independently checked lag/label builder are still needed. Do not promise fitting immediately after the synthetic probe.",
        ],
        "next_instruction":"Use actual available tools to record research, test your chosen temporal policy, and register the first revised proposal. "
            "Keep old definitions/results intact and explicitly list changed definitions. ALSO use request_capability for ONE smallest useful next evidence operation. "
            "Put an executable JSON object in its verification_needed string: operation_kind, exact_objects (host,path,advertised_bytes), "
            "purpose, outputs, max_input_bytes, max_decoded_bytes, wall_seconds, memory_bytes, stop_conditions, "
            "why_this_reduces_a_named_blocker, excluded_work. Choose fields/objects/policy yourself; unsupported evidence may be explicitly unavailable. "
            "Use only the actual inventory below for raw objects; do not invent collector/log paths. A metadata-provenance discovery request may instead "
            "name already-known directories and strict limits without claiming historic provenance. Never repeat the completedAug21T00 population audit. "
            "This is an actionable handoff, not permission: runner must independently validate and implement the operation. "
            "Do not condition all preparation on20untouched final sessions: those are for final claims, not evidence acquisition or opened-Train diagnostics. "
            "Source/causality/unit checks still apply; no skipping QA or relabeling failed data. Then defer; this workspace has no admitted rows.",
        "runner_resource_ceilings_not_scientific_choices":{"max_input_bytes":1073741824,
            "max_decoded_bytes":2147483648,"wall_seconds":600,"memory_bytes":1073741824,
            "new_downloads":False,"new_test":False,"production_writes":False},
        "raw_inventory":{"ref":{"path":str(INVENTORY),"sha256":SHA},"host":inventory["host"],
            "source_root":inventory["source_root"],"files":inventory["files"],
            "note":"Old names/sizes only, not current remote availability or content hashes; files outside this opened list are not authorized by this request."},
        "research_reuse":"Same previously recorded pandas backward-asof/tolerance semantics and existing version/hash checks. No new method or new live search is claimed by the reviewer. Controller research remains separately logged.",
    }
    additions = [review, {"id":"budget-before-feedback-revision",
        "budget":{k:v for k,v in budget.items() if k!="jobs"},
        "limits":"Original200; final50/repair20 protected; holds are not spending."}]
    originals = merge_findings(unalias(load_json(PARENT / "findings.json")), additions, MANIFEST)
    findings = alias_findings(originals)
    release = store.require_release()
    release_path = ROOT / "artifacts/releases" / release["publication"]["tag"] / "release.json"
    dependency = inspect(release_path, ROOT / "artifacts/tokenizer-cache")
    manifest = create(output, quality=store.config["quality"], findings=findings, allowed_dates=[],
        purpose="source_research", prior_archives=[{"path":str(PARENT / "round-archive.json"),
            "sha256":file_hash(PARENT / "round-archive.json")}], network=True,
        release_path=release_path, planning_context=context)
    fresh_json(output / "dependency-preflight.json", dependency)
    receipt = {"schema":"temporal_feedback_preparation_v1","manifest_sha256":manifest,
        "parent_manifest_sha256":MANIFEST,"parent_proposal_sha256":PROPOSAL,
        "same_harness":True,"harness_release_sha256":release["release_sha256"],
        "source_hashes":{p:file_hash(Path(__file__).with_name(p)) for p in (
            Path(__file__).name,"finding_aliases.py","temporal_span_review.py",
            "prepare_source_study_revision_workspace.py","source_study_object_scope.py",
            "source_inventory_context.py","controller_dependency_preflight.py")},
        "findings":len(findings),"prior_findings_preserved":len(load_json(PARENT / "findings.json")),
        "provider_calls":0,"fits":0,"source_admitted":False,"new_test":False}
    receipt["result_sha256"] = digest(receipt)
    fresh_json(output / "preparation.json", receipt)
    return receipt


if __name__ == "__main__":
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True)
    result=prepare(p.parse_args().output)
    print({k:result[k] for k in ("manifest_sha256","result_sha256","findings","provider_calls")})
