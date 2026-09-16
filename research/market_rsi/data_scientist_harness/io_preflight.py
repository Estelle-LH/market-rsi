"""Metadata-only residency check. Never hydrates, changes or trusts file contents."""
import argparse
from pathlib import Path
import stat
from market_rsi import digest, fresh_json


def inspect_paths(paths):
    failures=[];total=0
    for path in paths:
        path=Path(path);total+=1
        try:
            s=path.lstat()
            if not stat.S_ISREG(s.st_mode):reason="not_regular_or_symlink"
            elif getattr(s,"st_flags",0)&0x40000000:reason="cloud_placeholder_not_resident"
            else:continue
        except OSError as exc:reason=type(exc).__name__
        failures.append({"path":str(path),"reason":reason})
    return {"files_inspected":total,"ready_for_content_checks":not failures,"failures":failures,
        "contents_read":False,"integrity_verified":False,
        "limits":"Metadata readiness is not an integrity check or a guarantee against later I/O stalls. No cloud files are downloaded, removed, restored or rewritten."}


def budget_files(root):
    root=Path(root).resolve()
    # Include required files even when missing; include all existing receipts.
    required={root/"authorization.json",root/"journal.jsonl"}
    return sorted(required|set(root.glob("*.metering.json"))|set(root.glob("*.uncertain.json")))


def require_budget_resident(root):
    value=inspect_paths(budget_files(root))
    if not value["ready_for_content_checks"]:
        raise ValueError("budget files unavailable locally; no paid work: "+str(value["failures"][:3]))
    return value


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--budget",type=Path,required=True)
    p.add_argument("--workspace",type=Path)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError("fresh I/O report required")
    paths=budget_files(a.budget)
    if a.workspace:paths += [a.workspace/"workspace.json",a.workspace/"source-study-proposal.json",a.workspace/"round-archive.json"]
    value={"schema":"market_rsi_io_residency_v1",**inspect_paths(paths),"paid_calls":0,"fits":0}
    value["result_sha256"]=digest(value)
    a.output.parent.mkdir(parents=True,exist_ok=True);fresh_json(a.output,value)
    print({k:v for k,v in value.items() if k!="failures"})
    print({"first_failures":value["failures"][:5],"failure_count":len(value["failures"])})
