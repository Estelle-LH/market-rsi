"""Free end-to-end actual Codex + live public sources + four CPU trainers.

All model responses and market rows are synthetic mechanics fixtures. This is
not GLM research, a simulator, a signal result or authorization for a formal run.
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data_scientist_harness import fixtures
from data_scientist_harness.run_controller import run_session, source_hashes, harness, MODEL
from data_scientist_harness.store import Store, create
from data_scientist_harness.broker import Broker
from market_rsi import canonical, digest, file_hash, fresh_json
from paid_budget import PaidBudget


def call(name, args):
    return "<tool_call>mcp__controller_tools__"+name+"".join(
        "<arg_key>"+k+"</arg_key><arg_value>"+(v if isinstance(v,str) else json.dumps(v))+"</arg_value>"
        for k,v in args.items())+"</tool_call>"


class ScriptedBackend:
    def __init__(self, findings, root):
        self.root = root
        notes={"question":"Does preprocessing stay fit-only?","read_records":["0002"],
            "applicability":"Reuse the same train-fitted scaling on later rows, in a synthetic code fixture only.",
            "limitations":"This passage does not establish profitability or market coverage.",
            "alternatives":"Persistence baseline; no predictive claim.","proposed_test":"Four bounded CPU implementations."}
        steps=[("inspect_harness",{}),
            ("read_public_source",{"url":"https://scikit-learn.org/1.6/common_pitfalls.html","offset":0}),
            ("search_literature_live",{"query":"catch22 CAnonical Time-series CHaracteristics Lubba 2019"}),
            ("record_research",dict(notes,layer="feature_engineering")),
            ("record_research",dict(notes,layer="trainer_engineering")),
            ("profile_raw_series",{}),
            ("profile_candidate_feature",{"spec":fixtures.plan()["features"][0],"research_record":"0004"}),
            ("review_feature_set",{"profile_records":["0007"],"dispositions":[
                {"profile_record":"0007","reason":"Synthetic mechanics path","risk":"No market validity"}]}),
            ("acknowledge_current_findings",{"finding_sha256":digest(findings),"responses":[
                {"id":"fixture-only","handling":"Canary only","next_evidence":"Real source QA"}]})]
        for n,algorithm in enumerate(fixtures.MODELS):
            steps.append(("train_candidate",{"trial_id":f"t{n}","parent_trial_id":"t0" if n else "",
                "plan":fixtures.plan(algorithm),"feature_review":"0008","trainer_research":"0005",
                "experiment":fixtures.experiment('t0' if n else '')}))
            steps.append(('reflect_candidate',{'trial_id':f't{n}','outcome_sha256':f'OUTCOME_t{n}',
                'conclusion':'inconclusive','interpretation':'Synthetic mechanics fixture, not market improvement.',
                'next_step':'Validate the real source adapter before any market experiment.'}))
        steps.append(("submit_research_decision",{"action":"select","trial_id":"t0","reason":"Fixture completion, not a research winner"}))
        self.responses=[call(name,args) for name,args in steps]; self.sample_calls=0

    def encode(self, turn):
        return {"rendered_prompt":"Synthetic transport fixture; no tokenizer or provider",
            "token_ids":[1,2,3],"tokenizer_repo":"fixture","tokenizer_revision":"fixture","chat_template_sha256":"a"*64}

    def sample(self,token_ids,max_output_tokens,timeout_seconds):
        if not self.responses: raise RuntimeError("unexpected extra sample; no retry")
        self.sample_calls+=1
        response=self.responses.pop(0)
        for n in range(4):
            if f'OUTCOME_t{n}' in response:
                response=response.replace(f'OUTCOME_t{n}',file_hash(self.root/f'trials/t{n}/result.json'))
        return {"text":response,"output_tokens":[4,5],"cached_input_tokens":1,"finish_reason":"stop",
            "provider":{"reported_model":MODEL,"session_id":"synthetic-fixture","sampling_session_id":"synthetic-fixture"}}


def run(root):
    manifest=fixtures.workspace(root,network=True)
    store=Store(root,manifest)
    budget=PaidBudget.create(root/"fixture-budget",{"experiment_id":"fixture-"+root.name,
        "cap_usd":"10","target_usd":"10","buckets_usd":{"learning":"10"},
        "authority":"Synthetic token counters only. No provider charges or real budget access."})
    fresh_json(root/"fixture-only-claim.json",{"actual_tinker_calls":0,"credentials_loaded":False,
        "scripted_model":True,"market_data":"synthetic mechanics fixture","public_http":"live"})
    backend=ScriptedBackend(__import__("json").loads((root/"findings.json").read_text()),root)
    try:
        assessment=run_session(root,manifest,backend,budget,"synthetic_transport_fixture")
        records=store.records()
        if (backend.sample_calls!=18 or assessment["tool_calls"]!=18 or len(records)!=18
                or any(r["status"]!="ok" for r in records)):
            raise ValueError("exact eighteen successful tool steps required")
        for name in ("read_public_source","search_literature_live"):
            if store.records(name)[0]["result"]["receipt"]["mode"]!="live_public_http":
                raise ValueError("actual live reading/search receipt required")
        aggregate_input = root.parent / (root.name + "-aggregate-adapter-input.json")
        fresh_json(aggregate_input, {
            "schema": "synthetic_aggregate_adapter_fixture_v1",
            "research_result": False,
            "route_dev_opened": False,
            "sealed_final_opened": False,
        })
        aggregate_root = root.parent / (root.name + "-aggregate-adapter")
        aggregate_findings = [{"id": "aggregate-fixture", "fact": "Synthetic aggregate boundary only"}]
        aggregate_manifest = create(
            aggregate_root,
            quality=None,
            findings=aggregate_findings,
            allowed_dates=[],
            purpose="aggregate_research",
            network=False,
            aggregate_receipts=[{
                "path": str(aggregate_input.resolve()),
                "sha256": file_hash(aggregate_input),
            }],
        )
        aggregate_store = Store(aggregate_root, aggregate_manifest)
        try:
            aggregate_store.quality_before_training()
        except RuntimeError as error:
            if "cannot train" not in str(error):
                raise
        else:
            raise ValueError("aggregate-only adapter admitted training")
        aggregate_broker = Broker(aggregate_root, aggregate_manifest)
        aggregate_status = aggregate_broker.call("inspect_harness", {})
        aggregate_broker.call("acknowledge_current_findings", {
            "finding_sha256": aggregate_status["finding_sha256"],
            "responses": [{
                "id": "aggregate-fixture",
                "handling": "Boundary canary only",
                "next_evidence": "Use a fresh real aggregate workspace",
            }],
        })
        aggregate_broker.call("submit_research_decision", {
            "action": "defer",
            "trial_id": "",
            "reason": "Synthetic adapter canary; no empirical decision",
        })
        if (len(aggregate_store.records()) != 3
                or aggregate_status["quality"]["training_allowed"] is not False
                or not (aggregate_root / "round-archive.json").is_file()):
            raise ValueError("aggregate-only adapter canary failed")
        result={"schema":"data_scientist_codex_canary_v1","passed":True,"actual_codex_cli":True,
            "actual_tinker_calls":0,"model_authorship_proven":False,"provider_cost_usd":"0",
            "source_hashes":source_hashes(store),"manifest_sha256":manifest,
            "assessment_sha256":file_hash(root/"session/assessment.json"),"codex_sha256":file_hash(harness.CODEX),
            "actual_cpu_fits":4,"live_public_reads":1,"live_metadata_searches":1,
            "scripted_samples":18,"tool_calls":18,"fixture_ledger_is_not_provider_cost":True,
            "pre_result_intents":4,"post_result_reflections":4,
            "research_trace_sha256":file_hash(root/'research-trace.json'),
            "aggregate_adapter_tool_calls":3,
            "aggregate_adapter_training_allowed":False,
            "new_dev_test_admitted":False,"synthetic_market_rows":12}
        result["result_sha256"]=digest(result); fresh_json(root/"canary.json",result)
        return result
    except Exception as error:
        fresh_json(root/"canary-failure.json",{"error_type":type(error).__name__,"error":str(error)[:1200],
            "actual_tinker_calls":0,"automatic_retry":False})
        raise


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--output",type=Path,required=True)
    print(canonical(run(p.parse_args().output.resolve())))
