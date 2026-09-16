"""Pinned independent review of a completed proposal, not source admission.

Human-authored review facts are explicitly separate from controller decisions.
See SOURCE_STUDY_BRIDGE_2026-09-11.md for primary references and limitations.
No provider, raw-data reader, worker or QA writer is called by this module.
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_rsi import digest, file_hash, fresh_json, load_json
from data_scientist_harness.store import Store
from data_scientist_harness.source_study import current

PARENT_MANIFEST = "26518817a81f27bc45f0d93fda3ed76c71d3a2b4cb56665f1d478fd6d4ac825b"
PROPOSAL_FILE = "cb2d17a135d513ac379e577348f2ec9a839f146a4612a6d8b5b0445a2805ab2e"
AUDIT_RESULT = "118748b546b9278b1445743c9c31f7d5c8171b46bc7f6094bd5fa3f339d72eee"


def build(parent, audit_path):
    parent, audit_path = Path(parent).resolve(), Path(audit_path).resolve()
    store = Store(parent, PARENT_MANIFEST); store.verify()
    proposal = current(store)
    if proposal is None or proposal["sha256"] != PROPOSAL_FILE:
        raise ValueError("review is for the exact first registered proposal only")
    audit = load_json(audit_path)
    if (audit["result_sha256"] != AUDIT_RESULT or audit["result_sha256"] != digest({k:v for k,v in audit.items() if k != "result_sha256"})
            or audit["assessment_sha256"] != file_hash(parent/"session/assessment.json")
            or audit["manifest_sha256"] != PARENT_MANIFEST or not audit["controller_valid"] or not audit["process_reaped"]):
        raise ValueError("exact terminal audited parent required")
    value = {"schema":"source_study_independent_feedback_v1", "review_origin":"human_directed_independent_review",
        "parent_manifest_sha256":PARENT_MANIFEST, "proposal":proposal,
        "audit_ref":{"path":str(audit_path),"sha256":file_hash(audit_path)},
        "parent_archive":{"path":str(parent/"round-archive.json"),"sha256":file_hash(parent/"round-archive.json")},
        "judgment":"concrete proposal exists; executable definitions still incomplete; no scientific score",
        "source_admitted":False,"new_market_data_read":False,"fits":0,"provider_calls":0,
        "findings":[
            {"id":"quote-layer", "evidence":"Registered source/objective says reconstructed BBO. Earlier audited hour separates source BBO (zero crossed) from local depth (33,312 crossed); comparable pairs differ2.77094%. A book anchor alone does not certify subsequent depth reconstruction.",
             "required_response":"Name the exact quote series and event fields, explain why chosen, and specify an independently testable validity rule. Do not conflate direct quote fields with locally reconstructed depth or treat mismatch as proof the direct quote is wrong. Runner will not choose a replacement for you."},
            {"id":"executable-window", "evidence":"Proposal names t and t+60000ms at event times, but does not decide exact-match vs as-of endpoint selection, tie order, endpoint freshness, which clock schedules the horizon, or the meaning of minimum window coverage1.0. Gap and unanchored exclusions do not fill these definitions.",
             "required_response":"Define deterministic causal start/feature and endpoint rules, including ties, clock regressions and no message at the endpoint. Separate label unavailable from a zero label and count unavailable outcomes. Specify known vs unattested requirements; do not certify them yourself."},
            {"id":"baseline-and-attribution", "evidence":"The first invalid draft and research record call ridge on current mid equivalent to zero change. That is false in general. The registered plan corrected baseline to literal zero but still says same ridge trainer and changed_layer=features. A constant predictor versus a fitted lag model is a baseline comparison, not by itself a feature-only ablation of a fitted parent.",
             "required_response":"Resolve which comparisons and claims you actually intend, with explicit predictions and fit rules. State signed target/output units and any output transform. Do not claim a feature-only effect without a suitable same-trainer parent. Do not silently apply probability[0,1] clipping to a signed price change."},
            {"id":"failed-evidence-not-negative-score", "evidence":"Registered refutes_if groups candidate MSE>=baseline and a gate failure preventing clean scoring.",
             "required_response":"Distinguish a scored unsupported hypothesis from an untested/inconclusive result caused by data or execution failure. No failure-to-fit should become evidence that the feature lacks signal."},
            {"id":"source-proof-and-scope", "evidence":"Day-scale timestamp counts cannot attest capture-time semantics. A current Gamma response hash cannot establish historical mapping. The accessed analysis host's daily-sync.sh copies raw WS files from another host; its mtime is not receipt time. A different local raw-market-event.v1 collector does not establish this archive's t/m envelope. Registered dates are an allowed planning scope, not admitted or measured complete days.",
             "required_response":"Specify which identity/clock evidence this proposed study actually needs, which may be unnecessary given its explicit claim, and how unknowns stop or limit it. Do not request unrelated Gamma/sum-to-one invariants or repeat a completed hour. No protected dates, new download or access is granted."},
            {"id":"reading-and-proposal-drift", "evidence":"Four reads delivered24,000characters from TWO URLs: realtime[0,12000), prices[0,6000)and[12000,18000). No search was called. The record says three pages and implies prices[0,18000), which are not proved. Unread content cannot be dismissed as repetitive without reading it. Research note fitAug21-25/checkSep7-9 differs from the registered plan fitAug21-24/checkAug25+Sep7-9; first valid registered proposal is authoritative, not the earlier note.",
             "required_response":"Correct the reading/accounting claims and explicitly record any revision relative to the registered parent. Documentation of hashes does not prove a gap-free historical book. Retain all prior failures and decisions, not just the revised plan."},
        ],
        "primary_sources":[
            {"url":"https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html", "read":"objective function, alpha=0 and fit_intercept parameters", "finding":"alpha0 is least squares, not a forced zero predictor", "limits":"definition of estimator, not evidence of financial predictability"},
            {"url":"https://scikit-learn.org/stable/modules/generated/sklearn.dummy.DummyRegressor.html", "read":"strategy and constant parameters", "finding":"explicit constant strategy gives a fixed prediction", "limits":"clarifies semantics, does not choose controller's baseline implementation"},
            {"url":"https://scikit-learn.org/stable/common_pitfalls.html#data-leakage", "read":"data leakage and preprocessing sections", "finding":"choices/transform fitting must not use later evaluation data", "limits":"general leakage rule; does not by itself define a market-time split"},
        ],
        "review_date":"2026-09-11", "next_scope":"One feedback revision under unchanged published DSH; no fit or source approval. Controller may explain a limitation or retain a justified choice; reviewer does not prescribe a signal/horizon/trainer."}
    value["result_sha256"] = digest(value); return value


def validate(value, parent):
    if (value.get("schema") != "source_study_independent_feedback_v1"
            or value.get("result_sha256") != digest({k:v for k,v in value.items() if k != "result_sha256"})
            or value.get("parent_manifest_sha256") != parent.expected
            or value.get("source_admitted") is not False or value.get("fits") != 0
            or value.get("new_market_data_read") is not False or value.get("provider_calls") != 0
            or value.get("review_origin") != "human_directed_independent_review"
            or value.get("proposal") != current(parent)):
        raise ValueError("current bound independent review required")
    for key in ("audit_ref", "parent_archive"):
        ref = value[key]
        if file_hash(ref["path"]) != ref["sha256"]: raise ValueError("review evidence changed")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "audit", "output"): p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args()
    if a.output.exists(): raise ValueError("fresh review path required")
    value=build(a.parent,a.audit); a.output.parent.mkdir(parents=True,exist_ok=True)
    fresh_json(a.output,value); print({k:value[k] for k in ("result_sha256","judgment","fits","provider_calls")})
