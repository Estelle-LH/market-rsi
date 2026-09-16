"""Prove current real coverage failures block the new training entry point.

Reads existing QA/metadata receipts only. No prices, labels, fit or provider.
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data_scientist_harness.store import create
from data_scientist_harness.broker import Broker
from market_rsi import canonical,digest,file_hash,fresh_json,load_json


def run(output,review_dir,conclusion):
    evidence=load_json(conclusion)
    quality={"spec_path":str(review_dir/"spec.json"),"spec_sha256":file_hash(review_dir/"spec.json"),
        "review_path":str(review_dir/"reviewed-checks.json"),"review_sha256":file_hash(review_dir/"reviewed-checks.json")}
    findings=[{"id":"current-source-coverage","scope":evidence["scope"],
        "possible_session_count_upper_bound":evidence["possible_session_count_upper_bound"],
        "required_sessions":evidence["controller_minimum_complete_sessions"],
        "observed_event_minutes":evidence["total_distinct_utc_event_minutes"],
        "source_admitted":evidence["source_admitted"],
        "evidence":{"path":str(conclusion),"sha256":file_hash(conclusion)}}]
    sha=create(output,quality=quality,findings=findings,allowed_dates=[],purpose="source_research",network=False)
    b=Broker(output,sha); inspected=b.call("inspect_harness",{})
    blocked=False
    try:
        b.call("train_candidate",{"trial_id":"must-not-start","parent_trial_id":"","plan":{},
            "feature_review":"0001","trainer_research":"0001","experiment":{}})
    except RuntimeError as error:
        if "data quality must pass" not in str(error): raise
        blocked=True
    if not blocked or (output/"trials").exists(): raise ValueError("QA did not block before trial claim")
    b.call("acknowledge_current_findings",{"finding_sha256":inspected["finding_sha256"],"responses":[
        {"id":"current-source-coverage","handling":"Do not train on failed source coverage; preserve metadata evidence.",
         "next_evidence":"Controller must assess additional coverage; this audit chooses no replacement data."}]})
    b.call("submit_research_decision",{"action":"defer","trial_id":"","reason":"Runner-authored gate canary only; current coverage failed."})
    result={"schema":"data_scientist_actual_qa_canary_v1","passed":True,"training_blocked_before_claim":True,
        "new_fits":0,"new_provider_calls":0,"new_prices_labels_read":False,"model_authorship_proven":False,
        "manifest_sha256":sha,"observed_event_minutes":findings[0]["observed_event_minutes"],
        "possible_sessions":findings[0]["possible_session_count_upper_bound"],"required_sessions":findings[0]["required_sessions"]}
    result["result_sha256"]=digest(result); fresh_json(output/"qa-canary.json",result); return result


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("output","review-dir","conclusion"): p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args(); print(canonical(run(a.output.resolve(),a.review_dir.resolve(),a.conclusion.resolve())))
