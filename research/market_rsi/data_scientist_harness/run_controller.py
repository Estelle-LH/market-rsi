"""Codex/GLM adapter for the additive Data Scientist Harness.

The free canary uses actual Codex and tools but SCRIPTED model responses.
Paid dispatch requires a same-code canary, the original authorized ledger and
a fresh workspace. Neither mode exposes new Dev/Test or acquisition tools.
"""
import argparse
import fcntl
import os
from pathlib import Path
import secrets
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT),str(ROOT/"validation_tools"),str(ROOT/"source_review_tools")]
import run_codex_glm_controller as harness
from codex_glm_model_catalog import model_catalog
from codex_glm_provider import ControllerSession, TinkerGLMBackend
from controller_harness_contract import MAX_CUMULATIVE_INPUT_TOKENS, MAX_CUMULATIVE_OUTPUT_TOKENS
from glm_canary import MODEL, cost
from market_rsi import canonical, digest, file_hash, fresh_json, load_json
from paid_budget import PaidBudget, money
from run_source_review import command_for_source_review
from data_scientist_harness.broker import Broker, INSTRUCTIONS, ALLOWED_TOOLS, DECISION
from data_scientist_harness.store import Store
from data_scientist_harness.release import identity, verify_git_publication
from data_scientist_harness.io_preflight import require_budget_resident, require_local_execution


def source_hashes(store):
    return {str(Path(p).relative_to(store.root/"code")):h for p,h in store.config["files"].items()
            if Path(p).is_relative_to(store.root/"code")}


def verify_source(store):
    hashes = source_hashes(store)
    for relative, sha in hashes.items():
        if file_hash(ROOT/relative) != sha:
            raise ValueError("running controller source differs from frozen code")
    return hashes


def run_session(root, manifest, backend, budget, evidence_mode):
    store = Store(root,manifest); hashes = verify_source(store)
    fixture = evidence_mode == "synthetic_transport_fixture"
    if evidence_mode not in {"synthetic_transport_fixture","paid_controller"}:
        raise ValueError("explicit evidence mode required")
    if fixture:
        if store.config["purpose"] != "canary" or not budget.snapshot()["experiment_id"].startswith("fixture-"):
            raise ValueError("fixture workspace and isolated fake ledger required")
    elif (type(backend) is not TinkerGLMBackend or store.config["purpose"] == "canary"
          or not (store.root/"dispatch-claim.json").is_file()):
        raise ValueError("exact paid backend and permanent preflight claim required")
    if not fixture:
        store.require_release()
        if load_json(store.root/"dispatch-claim.json").get("harness_release") != identity(store.config):
            raise ValueError("dispatch claim does not bind the published harness version")
    output = store.root/"session"
    session = ControllerSession(session_id=store.root.name,output=output,backend=backend,budget=budget,
        budget_bucket="learning",submit_tool="submit_research_decision",allowed_tools=ALLOWED_TOOLS,
        protocol_error_tool="report_protocol_error",max_protocol_feedback=2)
    catalog = output/"model-catalog.json"; instructions=output/"model-instructions.md"
    fresh_json(catalog,model_catalog(INSTRUCTIONS))
    with instructions.open("x") as stream: stream.write(INSTRUCTIONS)
    bearer=secrets.token_urlsafe(32)
    server=harness.ThreadingHTTPServer(("127.0.0.1",0),harness.make_handler(session,bearer,model_catalog(INSTRUCTIONS)))
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        answer=output/"last-message.txt"
        command=command_for_source_review(workspace=store.root,answer=answer,
            base_url=f"http://127.0.0.1:{server.server_address[1]}/v1",catalog=catalog,instructions=instructions,
            manifest_sha256=manifest,broker_script=store.root/"code/data_scientist_harness/broker.py")
        # The worker gets 60s + cleanup; MCP must not abandon it at exactly 60s.
        command[1:1]=["-c","mcp_servers.controller_tools.tool_timeout_sec=90"]
        command=[v.replace("supports_parallel_tool_calls=true","supports_parallel_tool_calls=false") for v in command]
        fresh_json(output/"command.json",{"args":command})
        runtime=harness.codex_harness_identity(catalog=catalog,instructions=instructions,command=command)
        fresh_json(output/"harness-runtime.json",runtime)
        env={"PATH":os.environ.get("PATH","/usr/bin:/bin"),"HOME":os.environ.get("HOME",""),
             "TMPDIR":os.environ.get("TMPDIR","/tmp"),"CODEX_GLM_LOOPBACK_KEY":bearer}
        prompt=("Inspect current findings and quality. Research the next useful component, use the actual data-science "
                "tools where admitted, and archive your first supported decision. If coverage is inadequate, "
                "defer training and explain the missing evidence. Never substitute historical archive claims "
                "for current QA. This session cannot access new Dev/Test, purchase or download market data.")
        transport=harness.run_process(command,prompt,env,output)
        unresolved=harness.reconcile_unresolved_session_dispatches(session_id=store.root.name,
            budget=budget,output=output,transport=transport)
        store.verify(); verify_source(store)
        records=store.records()
        handshake=load_json(output/"terminal-handshake.json") if (output/"terminal-handshake.json").exists() else {}
        same=harness.codex_harness_identity(catalog=catalog,instructions=instructions,command=command)==runtime
        valid=(transport["exit_code"]==0 and transport["process_reaped"] and not session.failed and same
            and len([r for r in records if r["tool"]=="submit_research_decision" and r["status"]=="ok"])==1
            and (store.root/DECISION).exists() and answer.is_file()
            and answer.read_text().strip()=="Controller decision submitted; session complete."
            and handshake.get("provider_called") is False and handshake.get("paid_turn_added") is False)
        assessment={**transport,"schema":"data_scientist_controller_assessment_v1","valid":bool(valid),
            "evidence_mode":evidence_mode,"model":MODEL,"model_authorship_proven":bool(valid and not fixture),
            "turns":session.turns,"tool_calls":session.tool_calls,"failed":session.failed,
            "runner_protocol_feedbacks":session.protocol_feedback_count,
            "source_hashes":hashes,"manifest_sha256":manifest,"harness_runtime_unchanged":same,
            "harness_release":identity(store.config),
            "terminal_handshake":handshake,"unresolved_accounting":unresolved,
            "provider_budget":budget.snapshot(),"new_dev_test_admitted":False}
        fresh_json(output/"assessment.json",assessment)
        if not valid: raise RuntimeError("controller integration failed; preserve exact attempt")
        return assessment
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def paid_preflight(root, manifest, budget_path, authorization_sha256, canary_path):
    require_budget_resident(budget_path)  # BEFORE touching possibly cloud-backed receipts/locks.
    store=Store(root,manifest); hashes=verify_source(store)
    if (store.config["purpose"]=="canary" or store.events()
            or any((store.root/n).exists() for n in ("session","dispatch-claim.json",DECISION))):
        raise ValueError("fresh non-canary workspace required; no ID reuse")
    canary=load_json(canary_path)
    if (canary.get("schema")!="data_scientist_codex_canary_v1" or not canary.get("passed")
            or canary.get("source_hashes")!=hashes or canary.get("actual_tinker_calls")!=0
            or canary["result_sha256"]!=digest({k:v for k,v in canary.items() if k!="result_sha256"})
            or canary["assessment_sha256"]!=file_hash(canary_path.parent/"session/assessment.json")
            or canary["codex_sha256"]!=file_hash(harness.CODEX)):
        raise ValueError("passing exact-code/runtime real Codex canary required")
    tested=Store(canary_path.parent,canary["manifest_sha256"])
    assessment=load_json(canary_path.parent/"session/assessment.json")
    if (tested.config["purpose"]!="canary" or tested.config["runtime"]!=store.config["runtime"]
            or source_hashes(tested)!=hashes or assessment.get("valid") is not True
            or assessment.get("evidence_mode")!="synthetic_transport_fixture"
            or assessment.get("process_reaped") is not True or assessment.get("turns")!=18
            or assessment.get("tool_calls")!=18 or assessment.get("model_authorship_proven") is not False):
        raise ValueError("canary runtime/terminal proof differs from paid workspace")
    release = store.require_release()
    if release["canary"]["sha256"] != file_hash(canary_path):
        raise ValueError("canary is not the one bound to the published harness release")
    publication = verify_git_publication(hashes, root=ROOT, commit=release["publication"]["commit"])
    if file_hash(budget_path/"authorization.json")!=authorization_sha256:
        raise ValueError("original budget authorization required")
    snapshot=PaidBudget(budget_path).snapshot()
    if money(snapshot["cap_usd"])>money("200") or snapshot["experiment_id"].startswith("fixture-"):
        raise ValueError("original real <=200-dollar budget only")
    if any(v["state"]=="dispatched" and "-turn-" in k for k,v in snapshot["jobs"].items()):
        raise ValueError("active or unresolved model dispatch; do not duplicate")
    upper=cost(MAX_CUMULATIVE_INPUT_TOKENS,MAX_CUMULATIVE_OUTPUT_TOKENS)
    if min(money(snapshot["available_usd"]),money(snapshot["buckets"]["learning"]["available_usd"]))<upper:
        raise ValueError("whole controller bound exceeds available learning budget")
    return {"manifest_sha256":manifest,"budget_authorization_sha256":authorization_sha256,
        "harness_release":identity(store.config), "publication_rechecked":publication,
        "canary_sha256":file_hash(canary_path),"controller_upper_usd_not_spend":str(upper),
        "new_dev_test_admitted":False,"automatic_retry":False}


def main(a):
    root=a.workspace.resolve(); budget=a.budget.resolve()
    require_local_execution((ROOT,Path(sys.prefix),root,budget,a.canary,a.env_file,a.tokenizer_cache))
    # Share the existing dispatcher lock, not a separate lock per new adapter.
    with (root.parent/"historical-ingest-controller.lock").open("a+") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        checked=paid_preflight(root,a.manifest_sha256,budget,a.authorization_sha256,a.canary.resolve())
        fresh_json(root/"dispatch-claim.json",{**checked,"nonce":secrets.token_hex(16),"pid":os.getpid(),
            "claimed_unix_ns":time.time_ns()})
        from dotenv import dotenv_values
        backend=TinkerGLMBackend(dotenv_values(a.env_file).get("TINKER_API_KEY"),a.tokenizer_cache)
        result=run_session(root,a.manifest_sha256,backend,PaidBudget(budget),"paid_controller")
        print(canonical({k:v for k,v in result.items() if k!="provider_budget"}))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("workspace","budget","canary","env-file","tokenizer-cache"): p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--manifest-sha256",required=True); p.add_argument("--authorization-sha256",required=True)
    main(p.parse_args())
