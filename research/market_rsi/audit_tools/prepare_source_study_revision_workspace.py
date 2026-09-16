"""Feed audited criticism back without changing the harness or parent artifacts."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_rsi import digest, file_hash, fresh_json, load_json
from data_scientist_harness.store import Store, create
from source_study_feedback import validate
from controller_dependency_preflight import inspect
from paid_budget import PaidBudget
from source_inventory_context import finding as inventory_finding
from source_study_object_scope import finding_for_parent

ROOT=Path(__file__).resolve().parents[1]


def merge_findings(previous, additions, parent_manifest):
    """Keep old evidence with unique IDs; replace only the current-role labels.

    This edits a fresh input, never a parent's frozen findings. Older reviews
    remain visible rather than disappearing when the next review arrives.
    """
    if len({f["id"] for f in previous}) != len(previous):
        raise ValueError("parent findings have duplicate IDs; do not silently repair history")
    if len({f["id"] for f in additions}) != len(additions):
        raise ValueError("new findings have duplicate IDs")
    current_ids = {f["id"] for f in additions}
    result = []
    for f in previous:
        if f["id"] in current_ids:
            f = {**f, "id": "history:" + parent_manifest + ":" + f["id"],
                 "historical_finding_id": f["id"],
                 "historical_parent_manifest_sha256": parent_manifest}
        result.append(f)
    result += additions
    if len({f["id"] for f in result}) != len(result):
        raise ValueError("historical finding ID collision")
    return result


def prepare(parent, manifest, feedback, output):
    parent, feedback, output = (Path(v).resolve() for v in (parent,feedback,output))
    if output.exists(): raise ValueError("fresh revision workspace required")
    store=Store(parent,manifest); store.verify(); release=store.require_release()
    review=load_json(feedback); validate(review,store)
    a=load_json(parent/"session/assessment.json")
    if not a["valid"] or not a["process_reaped"] or a["exit_code"]!=0:
        raise ValueError("terminal parent required, never duplicate")
    budget=PaidBudget(ROOT/"artifacts/kalshi-research-glm53-20260907-01/budget").snapshot()
    if any(v["state"]=="dispatched" and "-turn-" in k for k,v in budget["jobs"].items()):
        raise ValueError("active or unresolved model call")
    release_path=ROOT/"artifacts/releases"/release["publication"]["tag"]/"release.json"
    dependency=inspect(release_path,ROOT/"artifacts/tokenizer-cache")
    additions=[
        {"id":"independent-source-study-review", "feedback":review,
         "registered_parent_proposal":load_json(parent/"source-study-proposal.json")["proposal"],
         "revision_instruction":"Read the actual parent and independent review. Address each issue, retaining or revising choices with evidence. "
             "Then register the first valid revised proposal in this fresh workspace and defer for independent validation. "
             "Use new current findings hash and current research record. Express detailed executable definitions in the existing text fields; "
             "do not invent schema fields. This is a feedback revision, not a blind retry or selection from multiple scores. "
             "No source admission, fits or new data are available. Do not change parent files or claim that all issues passed."},
        {"id":"budget-before-feedback-revision","budget":{k:v for k,v in budget.items() if k!="jobs"},
         "limits":"Original$200, final50/repair20 protected. Reservations are not spend. No raw quotes/keys/hiddenTest may go to model."}]
    context=store.config["planning_context"]
    # Never rewrite an earlier workspace; only this fresh input gains the exact
    # already-recorded source-specific metadata. Keep one current inventory item.
    inventory=inventory_finding(context)
    content_scope=finding_for_parent(store,load_json(parent/"source-study-proposal.json")["proposal"])
    findings=merge_findings(load_json(parent/"findings.json"), additions+[inventory,content_scope], manifest)
    result=create(output,quality=store.config["quality"],findings=findings,allowed_dates=[],purpose="source_research",
        prior_archives=[review["parent_archive"]],network=True,release_path=release_path,planning_context=context)
    fresh_json(output/"dependency-preflight.json",dependency)
    receipt={"schema":"source_study_revision_preparation_v1","manifest_sha256":result,
        "parent_manifest_sha256":manifest,"feedback_sha256":file_hash(feedback),"preparer_sha256":file_hash(__file__),
        "same_harness":True,"harness_release_sha256":release["release_sha256"],"provider_calls":0,"fits":0,
        "source_admitted":False,"raw_market_data_loaded":False,"new_dev_test_admitted":False}
    fresh_json(output/"preparation.json",receipt); return receipt


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("parent","feedback","output"):p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--manifest-sha256",required=True)
    a=p.parse_args();print(prepare(a.parent,a.manifest_sha256,a.feedback,a.output))
