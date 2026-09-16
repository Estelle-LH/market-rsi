"""Actual Codex source-planning path with synthetic replies and NO provider call."""
import argparse
from pathlib import Path
from data_scientist_harness import fixtures, source_study
from data_scientist_harness.canary import ScriptedBackend, call
from data_scientist_harness.store import create, Store
from data_scientist_harness.run_controller import run_session, source_hashes
from data_science_tools.pipeline import verify_review_files
from market_rsi import load_json, digest, file_hash, fresh_json
from paid_budget import PaidBudget


def workspace(root, network=False, history=False):
    root = Path(root).resolve()
    bootstrap = root.parent/(root.name+"-fixture"); fixtures.workspace(bootstrap, failed=True)
    quality = load_json(bootstrap/"workspace.json")["quality"]
    context = {"source_id": "synthetic-fixture", "raw_manifest_sha256": verify_review_files(**quality)["component_bindings"]["raw_manifest"],
               "opened_diagnostic_dates": ["1970-01-02", "1970-01-03"]}
    prior=[]
    if history:
        path=bootstrap/'synthetic-archive.json'
        fresh_json(path,{'schema':'data_scientist_round_archive_v1','session_id':'synthetic-history',
            'manifest_sha256':'0'*64,'note':'Synthetic history; not real research or permission'})
        prior=[{'path':str(path),'sha256':file_hash(path)}]
    return create(root, quality=quality, findings=[{"id": "fixture-only", "fact": "Synthetic mechanics, not an admitted source"}],
                  allowed_dates=[], purpose="canary", network=network, planning_context=context,prior_archives=prior)


def fixture_contract():
    return {"clock":"source_ms","decision_rule":"after_each_record","label_origin":"decision_time",
        "horizon_ms":60000,"endpoint_rule":"backward_asof","endpoint_tolerance_ms":1000,
        "missing_endpoint":"unavailable","invalid_quote":"invalidate","claim":"recorded_observation_only"}


def fixture_samples():
    return {'temporal':fixture_contract(),'quote_rules':{'book':'book_levels','price_change':'direct_bbo','rest_snapshot':'exclude'},
        'feature':{'lookback_ms':60000,'lookup_tolerance_ms':1000,'minimum_observations':2,'max_gap_ms':60000,
            'window_edges':'both','count_observations':'all_records','day_boundary':'purge'},
        'coverage':{'mode':'anchor_and_gap_only','slot_ms':0,'tolerance_ms':0,'minimum_coverage_per_mille':0},
        'label_max_gap_ms':60000,'tail_closure':'strictly_later_observed_record',
        'train_cutoff':'label_maturity_strictly_before_cutoff','check_cutoff':'label_maturity_strictly_before_cutoff',
        'clock_regression':'reject_segment','unavailable':'count_do_not_zero','claim':'recorded_observation_only'}


def proposal(status, research_record, temporal_probe_record="0005"):
    context = status["planning_context"]
    return {"proposal_id": "fixture-plan", "current_spec_sha256": status["quality"]["spec_sha256"],
        "finding_sha256": status["finding_sha256"], "research_record": research_record,"temporal_probe_record":temporal_probe_record,
        "sample_contract_record":"0006",
        "source": {"source_id": context["source_id"], "raw_manifest_sha256": context["raw_manifest_sha256"],
            "source_choice_reason": "Synthetic fixture only", "clock_basis_and_limits": "Unverified synthetic clock",
            "identity_basis_and_limits": "Synthetic entity", "sampling_rule": "Fixture row order",
            "missing_and_quiet_policy": "No fill or future filtering"},
        "question": "Can a source plan be declared without admitting data?",
        "hypothesis": "Planning preserves all failed QA and starts no process.",
        "objective": {"quantity": "Synthetic midpoint change", "units": "synthetic probability", "horizon_ms": 60000,
                      "availability_and_label_rule": "Fixture-only later observed value; not a market recipe"},
        "comparison": {"baseline": "Synthetic persistence", "candidate": "Synthetic lag", "changed_layer": "features", "held_fixed": "Fixture only"},
        "evaluation": {"fit_dates": ["1970-01-02"], "check_dates": ["1970-01-03"],
            "entity_split_and_purge": "Synthetic only, real policy unapproved", "primary_metric": "fixture MSE",
            "supports_if": "Recorded and no data loaded", "refutes_if": "QA cleared or worker started", "claim_limit": "No market/OOS claim"},
        "missing_evidence": ["Real data provenance and approved scientific contracts"],
        "next_if_unsupported": "Fix the adapter before any real research."}


def run(root):
    manifest = workspace(root, network=True, history=True); store = Store(root, manifest)
    findings = load_json(root/"findings.json"); context = store.config["planning_context"]
    status = {"planning_context": context, "quality": store.quality(), "finding_sha256": digest(findings)}
    backend = ScriptedBackend(findings, root)
    backend.responses = [call("inspect_harness", {}),
        call("read_public_source", {"url": "https://www.tensorflow.org/tfx/data_validation/get_started/", "offset": 0}),
        call("record_research", {"layer": "data_quality", "question": "Synthetic declaration versus validation test",
            "read_records": ["0002"], "applicability": "Schema expectation and validation are distinct",
            "limitations": "Fixture only; not market QA", "alternatives": "No planning path", "proposed_test": "Proposal without fitting"}),
        call("acknowledge_current_findings", {"finding_sha256": digest(findings), "responses": [
            {"id": "fixture-only", "handling": "Keep all source checks", "next_evidence": "Real source validation"}]}),
        call("probe_temporal_contract", {"contract":fixture_contract(),"research_record":"0003"}),
        call("probe_sample_contract", {"contract":fixture_samples(),"research_record":"0003"}),
        call("propose_source_study", proposal(status, "0003")),
        call("read_archive",{'archive_index':0,'offset':0}),
        call("submit_research_decision", {"action": "defer", "trial_id": "", "reason": "Synthetic proposed study awaiting validation"})]
    budget = PaidBudget.create(root/"fixture-budget", {"experiment_id": "fixture-"+root.name,
        "cap_usd": "10", "target_usd": "10", "buckets_usd": {"learning": "10"}, "authority": "Synthetic transport only; no provider"})
    assessment = run_session(root, manifest, backend, budget, "synthetic_transport_fixture")
    records = store.records(); ref = source_study.current(store)
    if not (assessment["valid"] and assessment["process_reaped"] and assessment["turns"] == 9
            and len(records) == 9 and all(r["status"] == "ok" for r in records)
            and records[4]["result"]["checks_passed"]
            and records[5]["result"]["checks_passed"]
            and records[7]['tool']=='read_archive' and records[7]['result']['all_pages_read_by_this_call']
            and not store.quality()["data_science_ready"] and not (root/"trials").exists()
            and load_json(root/"submitted-decision.json")["source_study_proposal"] == ref):
        raise ValueError("source-study transport canary failed")
    result = {"schema": "source_study_codex_canary_v1", "passed": True, "actual_codex_cli": True,
        "source_hashes": source_hashes(store), "manifest_sha256": manifest, "tool_calls": 9,
        "actual_tinker_calls": 0, "fits": 0, "model_authorship_proven": False,
        "source_admitted": False, "proposal": ref, "assessment_sha256": file_hash(root/"session/assessment.json")}
    result["result_sha256"] = digest(result); fresh_json(root/"source-study-canary.json", result)
    print({k: v for k, v in result.items() if k != "source_hashes"})


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--output", type=Path, required=True)
    run(p.parse_args().output.resolve())
