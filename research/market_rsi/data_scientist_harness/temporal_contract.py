"""Small deterministic temporal-policy probes, never a market simulator or fit.

The controller chooses all policy fields. These finite probes demonstrate
mechanics; they do not certify capture completeness, clock meaning or profit.
"""
from copy import deepcopy
from market_rsi import digest, file_hash


def enum(*values):return {"type":"string","enum":list(values)}


FIELDS={
    "clock":enum("source_ms","wrapper_ms"),
    "decision_rule":enum("after_each_record","after_timestamp_group"),
    "label_origin":enum("decision_time","group_time"),
    "horizon_ms":{"type":"integer"},
    "endpoint_rule":enum("backward_asof","forward_asof"),
    "endpoint_tolerance_ms":{"type":"integer"},
    "missing_endpoint":enum("unavailable","zero"),
    "invalid_quote":enum("invalidate","carry_last_valid"),
    "claim":enum("recorded_observation_only","continuous_market_state"),
}
SCHEMA={"type":"object","properties":FIELDS,"required":list(FIELDS),"additionalProperties":False}


def validate(c):
    if not isinstance(c,dict) or set(c)!=set(FIELDS):raise ValueError("exact temporal contract fields required")
    for key,schema in FIELDS.items():
        if "enum" in schema and c[key] not in schema["enum"]:raise ValueError("unsupported "+key)
    if type(c["horizon_ms"]) is not int or not 4<=c["horizon_ms"]<=86400000:
        raise ValueError("probe supports horizon4ms..1day; other mechanics require a capability proposal")
    if (type(c["endpoint_tolerance_ms"]) is not int
            or not 0<=c["endpoint_tolerance_ms"]<c["horizon_ms"]):
        raise ValueError("explicit endpoint tolerance0..horizon-1 required; never reuse the start as its own future observation")


def unavailable(reason):return {"available":False,"reason":reason,"label":None}


def decision(rows,c):
    """Fixture stream is a single entity in immutable arrival order."""
    clock=c["clock"]; t=rows[0][clock]
    if c["decision_rule"]=="after_each_record":return 0,0
    last=0
    for i,row in enumerate(rows[1:],1):
        if row[clock]<t:return None,None
        if row[clock]>t:return i,last
        last=i
    return None,None


def evaluate(rows,c):
    validate(c)
    keys=[tuple(r["key"]) for r in rows]
    if keys!=sorted(set(keys)):raise ValueError("unique immutable arrival keys required; never sort only by timestamp")
    if any(type(r[c["clock"]]) is not int for r in rows):raise ValueError("clock unavailable")
    di,group_last=decision(rows,c)
    if di is None:return unavailable("timestamp_group_not_causally_closed")
    start=di if c["label_origin"]=="decision_time" else group_last
    origin=rows[start][c["clock"]]; dt=rows[di][c["clock"]]
    base={"decision_key":rows[di]["key"],"feature_last_key":rows[start]["key"],
          "decision_ms":dt,"label_origin_ms":origin,"target_ms":origin+c["horizon_ms"],
          "feature_value":rows[start]["value"]}
    if origin<dt:return {**base,**unavailable("target_starts_before_prediction_is_available")}
    if not rows[start]["valid"]:return {**base,**unavailable("invalid_start_quote")}
    clock=c["clock"]; target=base["target_ms"]
    # Detect regressions in arrival order through the first strictly-later
    # observation. No sorting/revising an earlier prediction using late data.
    last=dt; boundary=None
    for i in range(di+1,len(rows)):
        t=rows[i][clock]
        if t<last:return {**base,**unavailable("clock_regression")}
        last=t
        if t>target:boundary=i;break
    if boundary is None:return {**base,**unavailable("unbounded_tail")}
    eligible=[i for i in range(di+1,boundary+1)
        if (rows[i][clock]<=target if c["endpoint_rule"]=="backward_asof" else rows[i][clock]>=target)]
    if not eligible:return {**base,**unavailable("no_endpoint_observation")}
    ei=eligible[-1] if c["endpoint_rule"]=="backward_asof" else eligible[0]
    if abs(rows[ei][clock]-target)>c["endpoint_tolerance_ms"]:
        return {**base,**unavailable("endpoint_outside_tolerance")}
    if not rows[ei]["valid"]:return {**base,**unavailable("invalid_endpoint_quote")}
    return {**base,"available":True,"reason":"observed_endpoint",
        "endpoint_key":rows[ei]["key"],"endpoint_ms":rows[ei][clock],
        "actual_span_ms":rows[ei][clock]-dt,"label":rows[ei]["value"]-rows[start]["value"],
        "market_state_certified":False}


def fixtures(c):
    """Horizon-scaled software edge cases, not learned/real price trajectories."""
    d=0 if c["decision_rule"]=="after_each_record" else 1
    target=d+c["horizon_ms"]
    def rows(items):
        return [{"key":[0,i,0,0],"source_ms":t,"wrapper_ms":t,"value":v,"valid":ok}
                for i,(t,v,ok) in enumerate(items)]
    prefix=[(0,0.25,True),(0,0.5,True),(1,0.25,True)]
    return {
        "observed_equal":rows(prefix+[(target,0.25,True),(target+1,0.75,True)]),
        "observed_change":rows(prefix+[(target,0.75,True),(target+1,0.5,True)]),
        "missing_tail":rows(prefix),
        "invalid_endpoint":rows(prefix+[(target,None,False),(target+1,0.5,True)]),
        "regression":rows(prefix+[(target-1,0.5,True),(target-2,0.5,True),(target,0.75,True),(target+1,0.5,True)]),
        "stale_endpoint":rows(prefix[:1 if d==0 else 3]+[(target+c["endpoint_tolerance_ms"]+1,0.75,True)]),
    }


def probe(c):
    validate(c); cases=fixtures(c); outputs={name:evaluate(rows,c) for name,rows in cases.items()}
    errors=[]
    if c["claim"]!="recorded_observation_only":errors.append("continuous_market_state_requires_external_capture_evidence_not_fixtures")
    if c["missing_endpoint"]!="unavailable":errors.append("missing_observation_cannot_be_label_zero")
    if c["invalid_quote"]!="invalidate":errors.append("invalid_quote_cannot_silently_carry_previous_valid_state")
    if c["decision_rule"]=="after_timestamp_group" and c["label_origin"]!="decision_time":
        errors.append("group_closure_arrives_later_start_horizon_at_actual_decision")
    # Evaluate safe behavior even for a proposed unsafe flag; refused flags
    # are never executed. A refusal is not a fallback research policy.
    expectations={"observed_equal":True,"observed_change":True,"missing_tail":False,
                  "invalid_endpoint":False,"regression":False,"stale_endpoint":False}
    checks={name:outputs[name]["available"]==expected for name,expected in expectations.items()}
    if outputs["observed_equal"]["available"]:checks["fresh_equal_is_zero"]=outputs["observed_equal"]["label"]==0
    base=cases["observed_change"]; di,_=decision(base,c)
    changed=deepcopy(base)
    if di is not None:
        for row in changed[di+1:]:
            if row["valid"]:row["value"]=0.99
        a=evaluate(base,c); b=evaluate(changed,c)
        checks["future_values_do_not_change_features"]=(a.get("feature_value"),a.get("feature_last_key"))==(b.get("feature_value"),b.get("feature_last_key"))
    errors += ["fixture_failed:"+name for name,ok in checks.items() if not ok]
    value={"schema":"temporal_contract_probe_v1","contract":c,"contract_sha256":digest(c),
        "checks_passed":not errors,"errors":errors,"checks":checks,"cases":outputs,
        "fixture_sha256":digest(cases),"implementation_sha256":file_hash(__file__),
        "synthetic_only":True,"real_source_validated":False,"source_admitted":False,
        "fits":0,"provider_calls":0,"raw_market_rows_read":0,
        "limitations":"Finite single-entity mechanical tests only; only start-quote availability is probed, not arbitrary lag/feature builders. Numeric clock fields remain unattested. A later timestamp does not prove no late records or no outage. Both lookup directions require a strictly later closing observation in these probes. Endpoint tolerance defines a recorded-observation target, not continuous market price or executable PnL. No market candidate or tolerance is chosen by the runner."}
    value["result_sha256"]=digest(value);return value


def bound_probe(store,record,horizon):
    r=store.get(record,"probe_temporal_contract");value=r["result"]
    if (not value.get("checks_passed") or value.get("contract")!=r["arguments"]["contract"]
            or value.get("contract_sha256")!=digest(r["arguments"]["contract"])
            or value.get("implementation_sha256")!=file_hash(__file__)
            or value.get("result_sha256")!=digest({k:v for k,v in value.items() if k not in {"result_sha256","record_id"}})
            or value["contract"]["horizon_ms"]!=horizon):
        raise ValueError("passing same-horizon temporal probe required; no untested prose substitute")
    return {"record_id":record,"record_sha256":file_hash(store.root/"records"/(record+".json")),
            "contract":value["contract"],"contract_sha256":value["contract_sha256"],
            "authority":"Typed temporal fields govern mechanical interpretation; contradictory proposal prose must be corrected before real source admission.",
            "real_source_validated":False}
