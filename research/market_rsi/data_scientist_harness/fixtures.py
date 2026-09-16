"""Small synthetic mechanics fixture, NEVER empirical market evidence."""
from pathlib import Path
from dataclasses import asdict
import numpy as np

from data_science_tools import pipeline as p
from data_scientist_harness.store import create, input_files
from market_rsi import digest, file_hash, fresh_json


def quality_rule(constant=False):
    from ds_harness_core.quality_checks import FeatureRule
    return asdict(FeatureRule(rationale="Synthetic fixture only; not a market policy",allow_constant=constant))


def experiment(parent="", names=("x",), normalizer="fit_mean_std"):
    return {"question":"Does this explicitly selected CPU trainer execute correctly?",
        "hypothesis":"Synthetic mechanics only; unchanged inputs reproduce the reference implementation.",
        "supports_if":"All prediction arrays match the legacy reference on these synthetic rows.",
        "refutes_if":"Any prediction, row or mask differs beyond exact equality.",
        "next_if_unsupported":"Preserve the failure and inspect the changed code; do not retry for score.",
        "changed_layer":"trainer" if parent else "baseline",
        "feature_units":dict.fromkeys(names,"synthetic_unit"),
        "feature_rules":{name:quality_rule() for name in names},
        "normalized_units":dict.fromkeys(names,"standardized" if normalizer=="fit_mean_std" else "synthetic_unit"),
        "normalized_rules":{name:quality_rule() for name in names}}


def reflection(root, trial):
    from market_rsi import load_json
    root=Path(root); path=root/'trials'/trial
    failed=(path/'failure.json').exists()
    return {'trial_id':trial,'outcome_sha256':file_hash(path/('failure.json' if failed else 'result.json')),
        'conclusion':'inconclusive','interpretation':'Synthetic fixture: no financial inference.',
        'next_step':'Run independent real-source adapter checks before any market experiment.'}


MODELS = {
    "ridge":{"alpha":1.,"fit_intercept":True},
    "elastic_net":{"alpha":.001,"l1_ratio":.5,"fit_intercept":True,"max_iter":100,"tol":1e-5},
    "random_forest":{"n_estimators":2,"max_depth":2,"min_samples_leaf":1,"max_features":1.},
    "hist_gradient_boosting":{"learning_rate":.1,"max_iter":2,"max_leaf_nodes":3,
                              "l2_regularization":1.,"min_samples_leaf":2},
}


def plan(algorithm="ridge"):
    return {"features":[{"name":"x","source":"x","transform":"identity","lookback_ms":0,
                "minimum_observations":1,"minimum_window_coverage":1}],
            "model":{"algorithm":algorithm,"parameters":dict(MODELS[algorithm])},
            "normalizer":"fit_mean_std","train_utc_dates":["1970-01-02"],
            "check_utc_dates":["1970-01-03"],"train_weighting":"equal_row",
            "score_aggregation":"equal_row","missing_input_action":"persistence",
            "output_transform":"none","seed":23,"rationale":"Synthetic mechanics fixture only"}


def workspace(root, failed=False, network=False):
    root = Path(root).resolve()
    source = root.parent/(root.name+"-fixture-inputs"); source.mkdir()
    n=12; t=np.r_[86400000+np.arange(6)*60000,172800000+np.arange(6)*60000].astype(np.int64)
    rows=np.array([str(i) for i in range(n)]); names=["polymarket_ticks_ms.midpoint_from_reported_bbo","x","flat"]
    values=np.column_stack([np.linspace(.2,.8,n),np.linspace(-1,1,n),np.ones(n)])
    dates=np.array(["1970-01-02"]*6+["1970-01-03"]*6)
    np.savez_compressed(source/"current-inputs.npz",row_id=rows,decision_ms=t,date=dates,
        entity=np.r_[np.zeros(6),np.ones(6)].astype(np.int64),field_names=np.array(names),values=values)
    target=.1*values[:,1]
    np.savez_compressed(source/"primary-labels.npz",row_id=rows,decision_ms=t,delta_probability=target,
        delta_probability_bps=target*10000,label_available_ms=t+60000,available=np.ones(n,dtype=bool),
        future_observation_count=np.ones(n,dtype=np.int64),reason=np.array(["synthetic"]*n))
    spec={"window_end_ms":60000}
    objective={"primary_query_id":"q1","queries":{"q1":{"spec":spec}},"primary_metric":"mse_skill_vs_persistence"}
    objective["proposal_sha256"]=digest(objective); fresh_json(source/"objective-proposal.json",objective)
    data={"plan":{"open_train_utc_dates":sorted(set(dates)),"cadence_ms":60000}}
    data["proposal_sha256"]=digest(data); fresh_json(source/"data-use-proposal.json",data)
    for name, value in {
        "input-result.json":{"complete":True,"labels_present":False,"fresh_holdout":False,"panel_sha256":"a"*64,
            "archive_sha256":file_hash(source/"current-inputs.npz"),"rows":n,"field_names":names},
        "label-result.json":{"complete":True,"training_admitted":False,"fresh_holdout":False,"panel_sha256":"a"*64,
            "proposal_sha256":objective["proposal_sha256"],"primary_query_id":"q1",
            "queries":{"q1":{"spec":spec,"archive_sha256":file_hash(source/"primary-labels.npz"),"rows":n}}},
        "panel-result.json":{"fresh_holdout":False,"panel_sha256":"a"*64,"summary":{"entity_mapping":[
            {"entity_code":0,"market_slug":"a"},{"entity_code":1,"market_slug":"b"}]}}
    }.items():
        value["result_sha256"]=digest(value); fresh_json(source/name,value)
    qa=root.parent/(root.name+"-fixture-qa"); qa.mkdir()
    fresh_json(qa/"evidence.json",{"synthetic_fixture":True,"not_real_source_QA":True})
    bindings=dict.fromkeys(p.BINDINGS,"a"*64)
    bindings.update(source_plan=file_hash(source/"data-use-proposal.json"),
        raw_manifest=digest({k:file_hash(v) for k,v in input_files(source).items()}))
    s={"schema":p.SCHEMA,"scope_id":root.name,"bindings":bindings,"controls":p.CONTROLS,
       "controller_owns":["source","sampling","features","objective","model"],"pipeline_policy_sha256":p.policy_sha256()}
    s["spec_sha256"]=p.digest(s)
    checks=[{"check_id":check,"status":"fail" if failed and check=="actual_day_market_coverage" else "pass",
             "scope_id":s["scope_id"],"bindings":{k:bindings[k] for k in stage[2]},
             "reason":"Synthetic QA fixture, not real data acceptance", "reviewer_role":"trusted_runner_review",
             "evidence_refs":[{"path":str(qa/"evidence.json"),"sha256":file_hash(qa/"evidence.json")}]}
             for stage in p.STAGES for check in stage[3]]
    fresh_json(qa/"spec.json",s); fresh_json(qa/"checks.json",checks)
    quality={"spec_path":str(qa/"spec.json"),"spec_sha256":file_hash(qa/"spec.json"),
             "review_path":str(qa/"checks.json"),"review_sha256":file_hash(qa/"checks.json")}
    from data_scientist_harness import sanity
    implementation=sanity.implementation_hash()
    units={name:'probability' if name==names[0] else 'synthetic_unit' for name in names}
    evidence={}
    for check in sanity.CHECKS:
        proof={'check':check,'status':'PASS','input_manifest_sha256':bindings['raw_manifest'],
            'implementation_sha256':implementation,'evidence_mode':'synthetic_fixture',
            'units':units,'clock_domain':sanity.CLOCK,'session_timezone':sanity.SESSION}
        path=qa/(check+'.json'); fresh_json(path,proof)
        evidence[check]={'path':str(path),'sha256':file_hash(path)}
    fresh_json(source/'sanity-contract.json',{'schema':'market_grid_sanity_contract_v1',
        'input_manifest_sha256':bindings['raw_manifest'],'implementation_sha256':implementation,
        'clock_domain':sanity.CLOCK,'session_timezone':sanity.SESSION,'evidence':evidence,
        'raw_units':units,'raw_rules':{name:quality_rule(name=='flat') for name in names},
        'expected_groups':[['a','1970-01-02'],['b','1970-01-03']],
        'allowed_unavailable_reasons':['unavailable_grid_or_window'],'min_rows_per_group':3,
        'time_series':{'max_gap_ns':60000*1000000,'rationale':'Synthetic one-minute grid',
                       'event_lags':[1,2],'elapsed_bins':2,'max_pair_gap_ns':60000*1000000}})
    return create(root,data_root=source,quality=quality,findings=[{"id":"fixture-only","fact":"Synthetic data, not research results"}],
                  allowed_dates=sorted(set(dates)),purpose="canary",network=network)


def fake_transport(url):
    import json
    raw=(json.dumps({"message":{"items":[{"title":["Synthetic paper"],"DOI":"10.0/fixture"}]}}).encode()
         if "api.crossref.org" in url else b"<html><h1>Synthetic research source</h1><p>Methods and limitations, not a real paper.</p></html>")
    return raw,{"requested_url":url,"final_url":url,"content_type":"application/json" if "api.crossref.org" in url else "text/html",
                "body_sha256":__import__("hashlib").sha256(raw).hexdigest(),"body_bytes":len(raw),
                "mode":"synthetic_transport_not_live_http"}
