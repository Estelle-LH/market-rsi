"""Trusted bounded CPU worker; recheck QA and frozen inputs before fitting."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_scientist_harness.store import Store
from data_scientist_harness.release import attribution
from historical_grid_learning import read_inputs
from data_scientist_harness.checked_learning import evaluate
from data_scientist_harness.sanity import read_contract
from data_scientist_harness.trajectory import trial_attribution
from market_rsi import digest, file_hash, fresh_json, identifier, load_json
from materialize_selected_grid_objective import write_archive


def run(root, manifest, trial_id, claim_sha256):
    identifier(trial_id)
    store = Store(root, manifest)
    store.quality_before_training()
    path = store.root/"trials"/trial_id
    if file_hash(path/"claim.json") != claim_sha256:
        raise ValueError("reserved claim changed")
    claim = load_json(path/"claim.json")
    if file_hash(path/"intent.json") != claim["intent_sha256"]:
        raise ValueError("pre-result research intent changed")
    if claim.get("attribution") != trial_attribution(store.config, claim["plan"],claim['experiment']):
        raise ValueError("reserved experiment version/components changed")
    if claim["manifest_sha256"] != manifest or (path/"result.json").exists() or (path/"failure.json").exists():
        raise ValueError("fresh claimed worker only")
    if claim["semantic_plan_sha256"] != digest({k:v for k,v in claim["plan"].items() if k != "rationale"}):
        raise ValueError("reserved plan changed")
    reviewed = store.get(claim["feature_review"], "review_feature_set")["result"]
    if reviewed["features"] != claim["plan"]["features"]:
        raise ValueError("unreviewed features")
    research = store.get(claim["trainer_research"], "record_research")
    if research["arguments"]["layer"] != "trainer_engineering":
        raise ValueError("trainer research missing")
    from threadpoolctl import threadpool_limits
    contract = read_contract(store.root/"inputs",store.config["input_manifest_sha256"],store.config["purpose"])
    with threadpool_limits(limits=1):
        report, arrays = evaluate(read_inputs(store.root/"inputs"), claim["plan"], claim["experiment"],contract,path/"sanity")
    store.verify()
    if file_hash(path/"claim.json") != claim_sha256:
        raise ValueError("claim mutated during fit")
    write_archive(path/"predictions.npz", arrays)
    fresh_json(path/"result.json", {"plan":claim["plan"],"report":report,
        "sanity_reports":{str(p.relative_to(path)):file_hash(p) for p in sorted((path/"sanity").glob("*/*.json"))},
        "attribution":claim["attribution"],
        "claim_sha256":file_hash(path/"claim.json"),"predictions_sha256":file_hash(path/"predictions.npz"),
        "provider_cost_usd":"0", "fresh_holdout":False})


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--workspace",type=Path,required=True)
    p.add_argument("--manifest-sha256",required=True)
    p.add_argument("--trial-id",required=True)
    p.add_argument("--claim-sha256",required=True)
    a = p.parse_args(); run(a.workspace,a.manifest_sha256,a.trial_id,a.claim_sha256)
