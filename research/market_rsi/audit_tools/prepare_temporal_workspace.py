"""Fresh DSH v1.4.0 workspace with checked v1.3.0 history; no paid dispatch."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_rsi import digest, file_hash, fresh_json, load_json
from data_scientist_harness.store import create
from data_scientist_harness.io_preflight import require_budget_resident
from paid_budget import PaidBudget
from archived_source_session import ArchivedSourceSession
from controller_dependency_preflight import inspect
from prepare_source_study_revision_workspace import merge_findings
from source_inventory_context import finding as inventory_finding
from source_study_object_scope import finding_for_parent
from finding_aliases import alias_findings

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT/"artifacts/source-study-inventory-controller-20260911-01"
AUDIT = ROOT/"artifacts/source-study-inventory-controller-audit-20260911-01/audit.json"
RELEASE = ROOT/"artifacts/releases/dsh-v1.4.0/release.json"
BUDGET = ROOT/"artifacts/kalshi-research-glm53-20260907-01/budget"
AUTH = "d5bcc2d00a3b574485252693c4ba07b3a4a3ab9e083ac3bbbc1d8b30e556a8f9"


def failed_interface_finding():
    from data_scientist_harness.store import Store
    path=ROOT/"artifacts/temporal-source-controller-audit-20260913-02/audit.json"
    value=load_json(path)
    if (value["result_sha256"]!="4563c9db8e6cb90868ec2ff294d76ab0df5b080e005fccb17aadfa3e6012d32b"
            or value["result_sha256"]!=digest({k:v for k,v in value.items() if k!="result_sha256"})
            or value["controller_valid"] is not False or value["process_reaped"] is not True
            or value["fits_completed"]!=0 or value["decision_sha256"] is not None):
        raise ValueError("exact terminated interface failure required")
    old=Store(Path(value["workspace"]),value["manifest_sha256"])
    if file_hash(old.root/"session/assessment.json")!=value["assessment_sha256"]:
        raise ValueError("failure assessment changed")
    records=old.records()
    if len([r for r in records if r["tool"]=="acknowledge_current_findings" and r["status"]=="error"])!=3:
        raise ValueError("failure evidence differs")
    return {"id":"prior-interface-failure-not-research-result", "audit_ref":{"path":str(path),"sha256":file_hash(path)},
        "observed":{"turns":len(value["turns"]),"tools":value["tools"],"metered_usd":value["session_metered_usd"],
            "uncertain_usd":value["session_uncertain_upper_usd"],"proposal":None,"fits":0},
        "cause":"All18 responses were supplied, but two long historical IDs repeatedly omitted one character in a64-character hash. "
            "After3identical failures the supervisor paused the child, let the current reply fully meter, then ended the session. "
            "There was no candidate/score or valid proposal to select or resample.",
        "human_repair":"This NEW workspace uses short top-level IDs. The nested original finding and full hash are unchanged evidence. "
            "Use each top-level fNNN id once and current finding_sha256. Old files/failed replies are preserved, not rewritten; "
            "this summary does not claim to deliver every old response body."}


def feedback(parent, budget):
    return [
        {"id":"temporal-tool-version-handoff", "verified_history":parent.receipt,
         "registered_parent_proposal":load_json(parent.proposal_ref["path"])["proposal"],
         "instruction":"This is a human-engineered upgrade from DSH1.3.0 to1.4.0, NOT a measured model improvement. "
             "Keep the entire previous archive as historical evidence, not a current QA pass. Read current findings, use public research as needed, "
             "then choose and run probe_temporal_contract with your explicit policy. Register the first valid proposal citing its passing record, then defer. "
             "You choose the source/target/horizon/tolerance/baseline/model/dates; the runner is not supplying those choices. "
             "Unsupported mechanics may be proposed via request_capability. No raw rows, fits, new Dev/Test or source admission are enabled."},
        {"id":"actual-decision-time-not-group-time",
         "evidence":"The parent waits for a strictly later timestamp to close a group but starts the target from the old group timestamp. "
             "That target begins before the prediction could be available. Its text also has incompatible missing/invalid-quote clauses.",
         "required_response":"Test your explicit decision/origin/endpoint/missing-state definitions, inspect the returned cases and limitations, "
             "and make all proposal prose agree with the tested fields. Choose a finite tolerance yourself; do not treat a synthetic PASS as real-source evidence. "
             "Forward lookup may define a future LABEL, not a prediction-time feature. Later timestamp is not proof of completeness or an exchange watermark."},
        {"id":"recorded-quote-not-continuity",
         "evidence":"Source/wrapper clock meanings, capture heartbeat and full-day identity/coverage remain unverified. "
             "A larger scan cannot by itself supply capture provenance. Original QA remains incomplete.",
         "required_response":"State exactly which evidence your claim needs, its remaining unknowns, and the smallest executable next evidence request. "
             "List explicit object scope and computational/byte limits if requesting work. Do not repeat the finished Aug21T00 audit or claim "
             "directory listings are content hashes. A missing endpoint is unavailable, not zero; a fresh equal quote may legitimately be zero."},
        {"id":"actual-reading-history-not-invented-counts",
         "evidence":"The last actual session had one successful pandas merge_asof read [0,6000) of9828 characters, "
             "two failed reads, no search, one corrected missing finding acknowledgement,9turns/9tools/0fits. "
             "Later proposal text incorrectly combined reading counts. Tool receipts, not retrospective prose, establish what was read.",
         "required_response":"Keep failed/partial reads visible and describe only the actual retrieved ranges. Do not invent cumulative evidence or say all issues resolved."},
        {"id":"budget-before-feedback-revision", "budget":{k:v for k,v in budget.items() if k!="jobs"},
         "limits":"Original$200; final50/repair20 protected. Pre-reservation is not consumption. No keys/raw quotes/hiddenTest may go to the controller."},
        inventory_finding(parent.config["planning_context"]),
        finding_for_parent(parent, load_json(parent.proposal_ref["path"])["proposal"]),
    ]


def prepare(output):
    output=Path(output).resolve()
    if output.exists(): raise ValueError("fresh cross-version workspace required")
    require_budget_resident(BUDGET)
    if file_hash(BUDGET/"authorization.json") != AUTH: raise ValueError("original authorization changed")
    budget=PaidBudget(BUDGET).snapshot()
    if any(v["state"]=="dispatched" and "-turn-" in k for k,v in budget["jobs"].items()):
        raise ValueError("active or unresolved model dispatch")
    parent=ArchivedSourceSession(PARENT,AUDIT,budget)
    dependency=inspect(RELEASE,ROOT/"artifacts/tokenizer-cache")
    originals=merge_findings(load_json(PARENT/"findings.json"),feedback(parent,budget)+[failed_interface_finding()],parent.expected)
    findings=alias_findings(originals)
    manifest=create(output,quality=parent.config["quality"],findings=findings,allowed_dates=[],
        purpose="source_research",prior_archives=[parent.receipt["archive"]],network=True,
        release_path=RELEASE,planning_context=parent.config["planning_context"])
    fresh_json(output/"dependency-preflight.json",dependency)
    receipt={"schema":"temporal_workspace_preparation_v1","manifest_sha256":manifest,
        "historical_verification":parent.receipt,"preparer_sha256":file_hash(__file__),
        "verifier_sha256":file_hash(Path(__file__).with_name("archived_source_session.py")),
        "adapter_source_hashes":{name:file_hash(Path(__file__).with_name(name)) for name in (
            "prepare_temporal_workspace.py","archived_source_session.py","controller_dependency_preflight.py",
            "prepare_source_study_revision_workspace.py","source_inventory_context.py","source_study_object_scope.py",
            "source_study_feedback.py","finding_aliases.py")},
        "finding_alias_map":[{"id":f["id"],"original_id":f["source_finding"]["id"],
            "original_sha256":f["source_finding_sha256"]} for f in findings],
        "dependency_sha256":file_hash(output/"dependency-preflight.json"),
        "release_sha256":load_json(RELEASE)["release_sha256"],"same_harness":False,
        "new_provider_calls":0,"fits":0,"source_admitted":False,"new_dev_test_admitted":False}
    receipt["result_sha256"]=digest(receipt);fresh_json(output/"preparation.json",receipt)
    return receipt


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();r=prepare(a.output)
    print({k:r[k] for k in ("manifest_sha256","result_sha256","new_provider_calls","fits")})
