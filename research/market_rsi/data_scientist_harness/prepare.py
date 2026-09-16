"""Prepare a fresh trusted workspace without fitting or calling any provider."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data_scientist_harness.store import create, resident
from market_rsi import canonical, file_hash, load_json


def main(a):
    quality={"spec_path":str(a.quality_spec.resolve()),"spec_sha256":a.spec_sha256,
             "review_path":str(a.quality_review.resolve()),"review_sha256":a.review_sha256}
    findings=load_json(resident(a.findings.resolve(),8_388_608))
    if not isinstance(findings,list) or any(not isinstance(f,dict) or not f.get("id") for f in findings):
        raise ValueError("runner-reviewed current findings with unique IDs required")
    if len({f["id"] for f in findings})!=len(findings): raise ValueError("duplicate finding ID")
    dates=[]
    if a.data_root:
        dates=load_json(resident(a.data_root.resolve()/"data-use-proposal.json"))["plan"]["open_train_utc_dates"]
    prior=[]
    for path in a.prior_archive:
        path=resident(path.resolve(),8_388_608); prior.append({"path":str(path),"sha256":file_hash(path)})
    sha=create(a.output,data_root=a.data_root,quality=quality,findings=findings,allowed_dates=dates,
        purpose="opened_train_research" if a.data_root else "source_research",prior_archives=prior,
        network=not a.no_public_network, release_path=a.release)
    print(canonical({"workspace":str(a.output.resolve()),"manifest_sha256":sha,"new_fits":0,"new_provider_calls":0}))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("output","quality-spec","quality-review","findings"): p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--data-root",type=Path,help="Opened Train seven-file grid cache plus sanity-contract.json and its three runner evidence files")
    p.add_argument("--prior-archive",type=Path,action="append",default=[])
    p.add_argument("--spec-sha256",required=True); p.add_argument("--review-sha256",required=True)
    p.add_argument("--release",type=Path,required=True,help="Published Git release receipt; not a version label")
    p.add_argument("--no-public-network",action="store_true"); main(p.parse_args())
