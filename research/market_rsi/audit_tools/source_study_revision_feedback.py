"""Independent, hash-bound review of revision 1. No raw data or paid calls.

Only feedback/context changes. The controller chooses any revised research
design. Prior primary-source research is reused, not claimed as a new search.
"""
import argparse
from pathlib import Path
from market_rsi import digest, file_hash, fresh_json, load_json
from data_scientist_harness.store import Store
from data_scientist_harness.source_study import current
from source_inventory_context import finding as inventory_finding
from source_study_feedback import validate

PARENT_MANIFEST="5edec63f559c78d45e1dcad7793900d7d48e5af9b6258e20ac5e68d43d864c98"
PROPOSAL_FILE="c6b0e98cfdc5979bfb7cae2902336c9dfbdf56e545ae411abb060df7c1f09659"
AUDIT_RESULT="cffc40faed7690105d7a24e170d94772215822c7f6115321879f9bad7352c321"


def build(parent,audit_path):
    parent,audit_path=Path(parent).resolve(),Path(audit_path).resolve()
    store=Store(parent,PARENT_MANIFEST);store.verify();store.require_release()
    proposal=current(store); audit=load_json(audit_path)
    if proposal is None or proposal["sha256"]!=PROPOSAL_FILE:
        raise ValueError("review pins the exact revision-1 proposal")
    if (audit.get("result_sha256")!=AUDIT_RESULT
            or digest({k:v for k,v in audit.items() if k!="result_sha256"})!=AUDIT_RESULT
            or audit["assessment_sha256"]!=file_hash(parent/"session/assessment.json")
            or audit["manifest_sha256"]!=PARENT_MANIFEST
            or not audit["controller_valid"] or not audit["process_reaped"]):
        raise ValueError("exact audited terminal revision required")
    inventory=inventory_finding(store.config["planning_context"])
    value={"schema":"source_study_independent_feedback_v1",
        "review_origin":"human_directed_independent_review","parent_manifest_sha256":PARENT_MANIFEST,
        "proposal":proposal,"audit_ref":{"path":str(audit_path),"sha256":file_hash(audit_path)},
        "parent_archive":{"path":str(parent/"round-archive.json"),"sha256":file_hash(parent/"round-archive.json")},
        "source_admitted":False,"new_market_data_read":False,"fits":0,"provider_calls":0,
        "judgment":"Revision improved source choice and claim limits, but did not establish observable labels; metadata handoff also omitted missing-file dates.",
        "findings":[
            {"id":"runner-file-inventory-omission","evidence":inventory,
             "required_response":"Use the newly supplied per-day inventory when choosing the split and scope. Aug23/24 have no files observed here; Aug22 has4 and Aug25 has22. This was missing from your input, not proof you ignored known gaps. File presence does not prove complete sessions. State which supported objects/date coverage you need; do not invent missing data or access protected dates."},
            {"id":"asof-does-not-attest-freshness",
             "evidence":"The registered rule calls a no-update window a genuine possibly-zero market fact when no gap violation was detected. A missing update or silent connection can produce the same observed records as an unchanged book. pandas backward asof only chooses the last key<=query; it does not establish a continuously valid quote. Boundary windows with no later observation can also evade an internal-gap check.",
             "required_response":"Define label availability separately from a numerical asof value. Specify the evidence and/or explicit statistical estimand needed for each accepted row; distinguish recorded-state assumptions from verified market-state claims. Unknown coverage cannot silently become a true zero. Choose and justify your own validity policy, including tail/no-message cases; reviewer is not prescribing a tolerance."},
            {"id":"causal-ties-and-clock",
             "evidence":"The proposed start uses the last record at timestamp t, but does not say whether the decision is after observing that entire group. Multiple later records can share the same millisecond. Completed audit reports34.6088% adjacent same-ms and1,282 source-clock regressions. Observed timestamp order cannot attest exchange/receipt clock meaning. Analysis host is a copy destination; its file times do not resolve this.",
             "required_response":"Give an exact decision watermark and deterministic (file,record,inner-event) order; features cannot use records past that watermark. State which archived clock defines the statistical question, how regressions/missing clocks are handled, and whether any unavailable capture provenance prevents the claim. Do not claim capture-time attestation from a larger statistical scan."},
            {"id":"actual-change-and-clipping",
             "evidence":"Parent chose reconstructed BBO; revision chose directly supplied BBO, but comparison text still claims source unchanged. Current checked_learning.py computes clip_to_probability_delta_bounds as clip(delta,-mid,1-mid), not clip(delta,0,1). Constant-zero versus fitted lag ridge is still a baseline comparison, not a same-trainer feature ablation.",
             "required_response":"Record the actual source/context changes and narrow attribution. You may retain output_transform none, but correct the description of the existing signed clipping option. Do not attribute any future difference to features alone when source or scoring population changed."},
            {"id":"bounded-next-operation",
             "evidence":"Revision asks for whole-day audits on all8dates including2with no files, and for unavailable original-capture evidence. Another broad request does not resolve missing definitions. The already completed Aug21T00 audit must not be repeated just to obtain the same statistics.",
             "required_response":"In existing proposal text fields, specify the smallest independently executable next evidence operation (input objects, outputs, deterministic rules and stop conditions), or clearly state the exact external evidence blocking it. A different targeted diagnostic on previously opened objects may answer a genuinely new question; no new download/source access is granted. No fit, source admission or data gate pass is implied by registering this proposal. Do not ask for an unavailable receipt-clock fact to be inferred from file counts."},
            {"id":"reading-record",
             "evidence":"Revision actually read pandas merge_asof[0,9828) and sklearn cross_validation[0,12000):2URLs,4successful reads,21,828 delivered chars,0 searches; one URLfragment request rejected. Earlier source docs delivered realtime12,000/46,312chars and prices12,000/29,111chars with a gap. Unread amounts were34,312 and17,111, not~28k/~11k. Reading an asof definition is not evidence of quote validity.",
             "required_response":"Keep accurate source-reading quantities and limitations; preserve earlier invalid requests/failed assumptions in the archive. New research is optional where existing sources answer the question, not a paper-count target."},
        ],
        "primary_sources":[
            {"url":"https://pandas.pydata.org/docs/reference/api/pandas.merge_asof.html",
             "read":"backward direction, exact-match and tolerance semantics; reused from2026-09-11 review",
             "finding":"record selection is not market-state validity proof",
             "limits":"No financial capture-completeness guarantee; does not select a tolerance for this study."},
            {"url":"https://scikit-learn.org/stable/common_pitfalls.html#data-leakage",
             "read":"data leakage and train-only preprocessing; reused from2026-09-11 review",
             "finding":"prediction features must be available before the decision; do not fit using later checks",
             "limits":"Generic principle, not original-source clock attestation."}],
        "review_date":"2026-09-11",
        "next_scope":"One inventory-informed feedback revision, unchanged DSHv1.3.0 and original$200 ledger. Controller chooses design, source restrictions and justification; no new raw data, Test, fits or provider calls in this review."}
    value["result_sha256"]=digest(value);validate(value,store);return value


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("parent","audit","output"):p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError("fresh review path required")
    value=build(a.parent,a.audit);a.output.parent.mkdir(parents=True,exist_ok=True)
    fresh_json(a.output,value)
    print({k:value[k] for k in ("result_sha256","judgment","fits","provider_calls")})
