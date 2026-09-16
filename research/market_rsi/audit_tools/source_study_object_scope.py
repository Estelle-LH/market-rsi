"""Resolve proposed dates to observed files before any expensive source scan.

Metadata-only dry run. Does not read market rows, admit a source, choose files
for the controller, or launch workers. An inventory is not a content manifest.
"""
import argparse
from pathlib import Path, PurePosixPath
from market_rsi import digest, file_hash, fresh_json, load_json
from data_scientist_harness.store import Store
from data_scientist_harness.source_study import current
from source_inventory_context import INVENTORY, SHA, summarize


def resolve(proposal, inventory, manifest, allowed_dates, previous_dates):
    summarize(inventory, allowed_dates)
    requested=proposal["evaluation"]["fit_dates"]+proposal["evaluation"]["check_dates"]
    if len(set(requested))!=len(requested) or not set(requested)<=set(allowed_dates):
        raise ValueError("unique opened fit/check dates required")
    if not set(previous_dates)<=set(allowed_dates):
        raise ValueError("previous dates outside same inventory")
    if manifest.get("source_id")!=proposal["source"]["source_id"]:
        raise ValueError("manifest belongs to another source")
    by_name={}
    for obj in manifest["objects"]:
        path=PurePosixPath(obj["path"])
        if (obj["host"]!=inventory["host"] or str(path.parent)!=inventory["source_root"]
                or path.name in by_name or type(obj["bytes"]) is not int or obj["bytes"]<=0
                or not isinstance(obj["sha256"],str) or len(obj["sha256"])!=64
                or any(c not in "0123456789abcdef" for c in obj["sha256"])):
            raise ValueError("invalid or duplicate manifest object")
        by_name[path.name]=obj
    chosen=[f for f in inventory["files"] if f["date"] in requested]
    prior=[f for f in inventory["files"] if f["date"] in previous_dates]
    bound=[];unbound=[]
    for f in chosen:
        obj=by_name.get(f["filename"])
        if obj is not None and obj["bytes"]!=f["compressed_bytes"]:
            raise ValueError("inventory and manifest size conflict")
        (bound if obj else unbound).append(f)
    return {"requested_dates":sorted(requested),"previous_dates":sorted(previous_dates),
        "requested_files":len(chosen),"previous_files":len(prior),
        "requested_compressed_bytes":sum(f["compressed_bytes"] for f in chosen),
        "previous_compressed_bytes":sum(f["compressed_bytes"] for f in prior),
        "removed_dates":sorted(set(previous_dates)-set(requested)),
        "removed_file_count":len({f["filename"] for f in prior}-{f["filename"] for f in chosen}),
        "manifest_bound_files":len(bound),"manifest_unbound_files":len(unbound),
        "manifest_bound_compressed_bytes":sum(f["compressed_bytes"] for f in bound),
        "manifest_unbound_compressed_bytes":sum(f["compressed_bytes"] for f in unbound),
        "bound_inventory_objects":bound,"unbound_inventory_objects":unbound,
        "no_files_observed_requested_dates":sorted(set(requested)-{f["date"] for f in chosen}),
        "all_requested_objects_bound":bool(chosen) and not unbound,
        "current_remote_availability_verified":False,"content_integrity_rechecked":False,
        "interpretation":"Date narrowing only shrinks work when observed objects are removed. Filename/size inventory is not a content hash. Even complete object bindings would not prove source quality or authorize execution."}


def require_full_binding(result):
    if not result["all_requested_objects_bound"]:
        raise ValueError("requested file set exceeds immutable content manifest; no scan admitted")


def scope_for_plan(store, proposal, previous_dates):
    if file_hash(INVENTORY)!=SHA:raise ValueError("pinned inventory changed")
    manifest_path=Path(store.config["quality"]["spec_path"]).parent/"raw-manifest.json"
    if file_hash(manifest_path)!=proposal["source"]["raw_manifest_sha256"]:
        raise ValueError("proposal content manifest mismatch")
    return resolve(proposal,load_json(INVENTORY),load_json(manifest_path),
        store.config["planning_context"]["opened_diagnostic_dates"],previous_dates)


def finding_for_parent(store, proposal):
    """Expose the actual content boundary, not just an opaque manifest hash."""
    scope=scope_for_plan(store,proposal,store.config["planning_context"]["opened_diagnostic_dates"])
    return {"id":"runner-content-manifest-and-work-scope",
        "inventory_sha256":SHA,"raw_manifest_sha256":proposal["source"]["raw_manifest_sha256"],
        "parent_requested_scope":{k:v for k,v in scope.items() if not k.endswith("inventory_objects")},
        "handoff_correction":"The inventory records observed names/sizes; the current content manifest pins only its listed objects. "
            "Prior inputs did not directly reconcile these scopes. This is a runner handoff correction, not a hidden controller failure. "
            "Planning permission for a date is neither proof its files exist nor a hash binding of their contents. "
            "Define exact next-operation object scope and limits; missing content commitments need independent acquisition/verification before any execution. "
            "Do not call a date-list change a reduced scan unless it actually removes files. The reviewer does not choose which files to use."}


def audit(workspace):
    workspace=Path(workspace).resolve()
    store=Store(workspace,file_hash(workspace/"workspace.json"));store.verify()
    ref=current(store)
    assessment=load_json(workspace/"session/assessment.json")
    if (ref is None or not assessment["valid"] or not assessment["process_reaped"]
            or assessment["exit_code"]!=0 or assessment["manifest_sha256"]!=store.expected):
        raise ValueError("completed valid planning session required")
    proposal=load_json(ref["path"])["proposal"]
    review=[f for f in load_json(workspace/"findings.json") if f["id"]=="independent-source-study-review"]
    if len(review)!=1:raise ValueError("one current parent review required")
    parent=review[0]["registered_parent_proposal"]["evaluation"]
    result=scope_for_plan(store,proposal,parent["fit_dates"]+parent["check_dates"])
    try:
        require_full_binding(result); error=None
    except ValueError as exc:
        error=str(exc)
    value={"schema":"source_study_object_scope_audit_v1","workspace_manifest_sha256":store.expected,
        "proposal":ref,"inventory_sha256":SHA,"raw_manifest_sha256":proposal["source"]["raw_manifest_sha256"],
        "audit_source_sha256":file_hash(__file__),"scope":result,"binding_guard_error":error,
        "raw_rows_read":0,"remote_calls":0,"provider_calls":0,"fits":0,
        "source_admitted":False,"execution_admitted":False,"new_test_opened":False}
    value["result_sha256"]=digest(value);return value


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError("fresh scope-audit output required")
    result=audit(a.workspace);a.output.parent.mkdir(parents=True,exist_ok=True);fresh_json(a.output,result)
    print({"result_sha256":result["result_sha256"],"binding_guard_error":result["binding_guard_error"],
        "scope":{k:v for k,v in result["scope"].items() if not k.endswith("inventory_objects")}})
