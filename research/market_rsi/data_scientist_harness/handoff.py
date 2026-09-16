"""Runner-only preflight; never exposed as a controller tool or Test executor."""
from data_scientist_harness.broker import Broker
from data_science_tools.pipeline import check_independent_validation_after_data_science
from market_rsi import file_hash, load_json


def validation_preflight(*, root, manifest_sha256, quality, proposal, context, runner, budget):
    b=Broker(root,manifest_sha256)
    # Full eight-stage QA, not just the four gates used by Train-only fitting.
    checked=check_independent_validation_after_data_science(**quality,proposal=proposal,
        context=context,runner=runner,budget=budget)
    if b.store.config["purpose"]=="canary": raise ValueError("synthetic fixture is never formal evidence")
    b.store.require_release()
    decision=load_json(b.root/"submitted-decision.json")
    receipts=b._ok("submit_research_decision")
    if (len(receipts)!=1 or {k:v for k,v in receipts[0]["result"].items() if k!="bytes"}!=decision
            or decision["action"]!="select"):
        raise ValueError("one ledger-backed selected candidate required")
    selected=decision["selected"]; b.completed_candidate(selected["trial_id"])
    if selected["result_sha256"]!=file_hash(b.root/"trials"/selected["trial_id"]/"result.json"):
        raise ValueError("selected candidate changed")
    # The legacy runner must bind its exact candidate to the new selection.
    if runner.get("data_scientist_candidate_sha256")!=selected["result_sha256"]:
        raise ValueError("independent runner candidate differs from research selection")
    return {**checked,"data_scientist_selection":selected,"executes_evaluation":False}
