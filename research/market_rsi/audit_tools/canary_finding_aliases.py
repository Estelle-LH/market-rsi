"""Actual Codex,18 short finding IDs, temporal probe, scripted replies; zero Tinker."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_rsi import load_json,digest,file_hash,fresh_json
from data_scientist_harness.source_study_canary import workspace,fixture_contract,proposal
from data_scientist_harness.canary import ScriptedBackend,call
from data_scientist_harness.store import create,Store
from data_scientist_harness.run_controller import run_session
from paid_budget import PaidBudget
from finding_aliases import alias_findings


def run(root):
    bootstrap=root.parent/(root.name+"-bootstrap"); workspace(bootstrap)
    config=load_json(bootstrap/"workspace.json")
    originals=[{"id":"history:"+str(i).zfill(64)+":fixture","fact":"Synthetic software fixture, not a market finding"} for i in range(18)]
    findings=alias_findings(originals)
    manifest=create(root,quality=config["quality"],findings=findings,allowed_dates=[],purpose="canary",
        network=True,planning_context=config["planning_context"])
    store=Store(root,manifest);status={"quality":store.quality(),"finding_sha256":digest(findings),"planning_context":config["planning_context"]}
    backend=ScriptedBackend(findings,root)
    backend.responses=[call("inspect_harness",{}),
        call("read_public_source",{"url":"https://pandas.pydata.org/docs/reference/api/pandas.merge_asof.html","offset":0}),
        call("record_research",{"layer":"data_quality","question":"Synthetic alias and temporal tool test","read_records":["0002"],
            "applicability":"Bounded endpoint mechanics","limitations":"Not real market validation","alternatives":"Untested prose","proposed_test":"Probe then register"}),
        call("acknowledge_current_findings",{"finding_sha256":digest(findings),"responses":[
            {"id":f["id"],"handling":"Keep fixture status","next_evidence":"Real source checks"} for f in findings]}),
        call("probe_temporal_contract",{"contract":fixture_contract(),"research_record":"0003"}),
        call("propose_source_study",proposal(status,"0003")),
        call("submit_research_decision",{"action":"defer","trial_id":"","reason":"Synthetic interface check only"})]
    budget=PaidBudget.create(root/"fixture-budget",{"experiment_id":"fixture-"+root.name,"cap_usd":"10","target_usd":"10",
        "buckets_usd":{"learning":"10"},"authority":"Synthetic counters only; zero provider calls"})
    assessment=run_session(root,manifest,backend,budget,"synthetic_transport_fixture")
    records=store.records()
    assert assessment["valid"] and assessment["process_reaped"] and len(records)==7 and all(r["status"]=="ok" for r in records)
    assert records[4]["result"]["checks_passed"] and not (root/"trials").exists()
    assert [r["source_finding"] for r in load_json(root/"findings.json")]==originals
    value={"schema":"finding_alias_codex_canary_v1","passed":True,"actual_codex_cli":True,
        "scripted_model":True,"model_authorship_proven":False,"tool_calls":7,"findings":18,
        "original_findings_preserved":True,"temporal_probe_passed":True,"provider_calls":0,"fits":0,
        "manifest_sha256":manifest,"assessment_sha256":file_hash(root/"session/assessment.json"),
        "source_hashes":{"canary":file_hash(__file__),"aliases":file_hash(Path(__file__).with_name("finding_aliases.py"))}}
    value["result_sha256"]=digest(value);fresh_json(root/"canary.json",value);print(value)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);run(p.parse_args().output.resolve())
