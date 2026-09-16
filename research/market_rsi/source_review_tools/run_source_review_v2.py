"""V2 source-review dispatcher; unchanged model/provider/ledger/CLI isolation."""
import argparse
import fcntl
import os
from pathlib import Path
import secrets
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'validation_tools')]
import run_codex_glm_controller as harness
import controller_source_review_v2 as review
from run_source_review import command_for_source_review
from codex_glm_model_catalog import model_catalog
from codex_glm_provider import ControllerSession,TinkerGLMBackend
from controller_harness_contract import MAX_CUMULATIVE_INPUT_TOKENS,MAX_CUMULATIVE_OUTPUT_TOKENS
from glm_canary import MODEL,cost
from market_rsi import canonical,digest,file_hash,fresh_json,load_json
from paid_budget import PaidBudget,money


def verify_preparation(prepared):
    p=load_json(prepared/'preparation.json')
    if p.get('schema')!='historical_source_review_v2_preparation_v1' or p.get('source_review_interface_version')!=2:
        raise ValueError('explicit v2 preparation required')
    manifest,visible=review.validate_workspace(prepared/'workspace',p['workspace_sha256'])
    if manifest['session_id']!=prepared.name or manifest['purpose']!=p['purpose']:raise ValueError('permanent ID/purpose mismatch')
    for name,sha in p['source_hashes'].items():
        if file_hash(ROOT/name)!=sha or file_hash(prepared/'source-snapshot'/name)!=sha:
            raise ValueError('frozen v2 source changed')
    for path,sha in p['inputs'].items():
        if file_hash(Path(path))!=sha:raise ValueError('frozen v2 input changed')
    if p['source_hashes'].get('source_review_tools/run_source_review_v2.py')!=file_hash(Path(__file__)):
        raise ValueError('actual dispatcher not in snapshot')
    return p,manifest,visible


def verify_canaries(prep,stdio_path,full_path):
    c=load_json(stdio_path);cp=load_json(stdio_path.parent/'preparation.json')
    if (c.get('schema')!='historical_source_review_v2_stdio_canary_v1' or c.get('passed') is not True
            or c.get('actual_stdio_child') is not True or c.get('actual_tools')!=5
            or c.get('full_plan_schema_served') is not True or c.get('new_model_calls')!=0
            or c.get('new_public_metadata_calls')!=0 or c.get('context_sha256')!=prep['context_sha256']
            or c.get('followup_sha256')!=prep['followup_sha256'] or cp['source_hashes']!=prep['source_hashes']
            or cp['purpose']!='transport_canary' or c['preparation_sha256']!=file_hash(stdio_path.parent/'preparation.json')
            or c['result_sha256']!=digest({k:v for k,v in c.items() if k!='result_sha256'})):
        raise ValueError('same-source v2 STDIO canary required')
    f=load_json(full_path);fp=load_json(full_path.parent/'preparation.json')
    if (f.get('schema')!='historical_source_review_v2_codex_fixture_v1' or f.get('passed') is not True
            or f.get('actual_codex_cli') is not True or f.get('actual_tinker_calls')!=0
            or fp['source_hashes']!=prep['source_hashes'] or f['source_hashes']!=prep['source_hashes']
            or fp['purpose']!='transport_canary' or f['followup_sha256']!=prep['followup_sha256']
            or f['context_sha256']!=prep['context_sha256']
            or f['preparation_sha256']!=file_hash(full_path.parent/'preparation.json')
            or f['assessment_sha256']!=file_hash(full_path.parent/'session/assessment.json')
            or f['fixture_claim_sha256']!=file_hash(full_path.parent/'fixture-only-claim.json')
            or f['codex_cli_sha256']!=file_hash(harness.CODEX) or f['python_sha256']!=file_hash(Path(sys.executable))
            or f['result_sha256']!=digest({k:v for k,v in f.items() if k!='result_sha256'})):
        raise ValueError('same-source/runtime v2 actual Codex fixture required')
    a=load_json(full_path.parent/'session/assessment.json')
    if (a.get('valid') is not True or a.get('process_reaped') is not True or a.get('turns')!=2
            or a.get('tool_calls')!=4 or a.get('model_authorship_proven') is not False
            or a.get('evidence_mode')!='synthetic_transport_fixture'):
        raise ValueError('two-sample four-tool fixture evidence required')


def preflight(prepared,budget_path,stdio_path,full_path):
    if (prepared/'dispatch-claim.json').exists() or (prepared/'session').exists():raise ValueError('permanent ID already claimed')
    p,manifest,visible=verify_preparation(prepared)
    if manifest['purpose']!='source_review':raise ValueError('fixture cannot become paid research')
    ws=prepared/'workspace'
    if (ws/review.LOG).exists() or (ws/review.DECISION).exists() or any(
            list((ws/k).iterdir()) for k in ('plans','metadata-requests','public-metadata')):
        raise ValueError('paid workspace must be unconsumed')
    verify_canaries(p,stdio_path,full_path)
    b=PaidBudget(budget_path).snapshot();ctx=visible['context.json']
    if (b['experiment_id']!=ctx['experiment_id'] or money(b['cap_usd'])!=money(ctx['budget_cap_usd'])
            or file_hash(budget_path/'authorization.json')!=ctx['budget_authorization_sha256']):
        raise ValueError('original budget changed')
    if any(v['state']=='dispatched' and '-turn-' in k for k,v in b['jobs'].items()):raise ValueError('another or unresolved model turn')
    upper=cost(MAX_CUMULATIVE_INPUT_TOKENS,MAX_CUMULATIVE_OUTPUT_TOKENS)
    if min(money(b['available_usd']),money(b['buckets']['learning']['available_usd']))<upper:
        raise ValueError('whole-session upper exceeds available budget')
    return {'controller_stage':'source_review_v2','model':MODEL,'session_id':prepared.name,
        'preparation_sha256':file_hash(prepared/'preparation.json'),'followup_sha256':p['followup_sha256'],
        'context_sha256':ctx['context_sha256'],'budget_authorization_sha256':ctx['budget_authorization_sha256'],
        'stdio_canary_sha256':file_hash(stdio_path),'codex_canary_sha256':file_hash(full_path),
        'controller_worst_case_usd_not_spend':str(upper),'budget_bucket':'learning',
        'new_raw_download_admitted':False,'new_test_admitted':False,
        'budget_snapshot_not_spend':{k:v for k,v in b.items() if k!='jobs'}}


def run_session(*,prepared,backend,budget,prompt,evidence_mode):
    if evidence_mode not in ('paid_controller','synthetic_transport_fixture'):raise ValueError('explicit evidence mode required')
    if evidence_mode=='paid_controller' and type(backend) is not TinkerGLMBackend:raise ValueError('exact pinned paid backend required')
    p,manifest,_=verify_preparation(prepared)
    if evidence_mode=='synthetic_transport_fixture':
        if manifest['purpose']!='transport_canary' or not budget.snapshot()['experiment_id'].startswith('fixture-'):
            raise ValueError('fixture workspace and separate fixture ledger required')
    elif manifest['purpose']!='source_review' or not (prepared/'dispatch-claim.json').is_file():
        raise ValueError('permanent paid preflight claim required')
    ws=prepared/'workspace';output=prepared/'session'
    session=ControllerSession(session_id=prepared.name,output=output,backend=backend,budget=budget,
        budget_bucket='learning',submit_tool='submit_source_review_decision',allowed_tools=review.ALLOWED_TOOLS)
    catalog=output/'model-catalog.json';instructions=output/'model-instructions.md'
    fresh_json(catalog,model_catalog(review.INSTRUCTIONS))
    with instructions.open('x',encoding='utf-8') as f:f.write(review.INSTRUCTIONS)
    bearer=secrets.token_urlsafe(32)
    server=harness.ThreadingHTTPServer(('127.0.0.1',0),harness.make_handler(session,bearer,model_catalog(review.INSTRUCTIONS)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        answer=output/'last-message.txt'
        cmd=command_for_source_review(workspace=ws,answer=answer,
            base_url=f'http://127.0.0.1:{server.server_address[1]}/v1',catalog=catalog,instructions=instructions,
            manifest_sha256=p['workspace_sha256'],broker_script=prepared/'source-snapshot/source_review_tools/controller_source_review_v2.py')
        fresh_json(output/'command.json',{'args':cmd,'controller_stage':'source_review_v2'})
        runtime=harness.codex_harness_identity(catalog=catalog,instructions=instructions,command=cmd)
        fresh_json(output/'harness-runtime.json',runtime)
        env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'HOME':os.environ.get('HOME',''),
             'TMPDIR':os.environ.get('TMPDIR','/tmp'),'CODEX_GLM_LOOPBACK_KEY':bearer}
        transport=harness.run_process(cmd,prompt,env,output)
        same_runtime=harness.codex_harness_identity(catalog=catalog,instructions=instructions,command=cmd)==runtime
        unresolved=harness.reconcile_unresolved_session_dispatches(session_id=prepared.name,budget=budget,output=output,transport=transport)
        try:activity=review.assess_activity(ws,p['workspace_sha256'])
        except Exception as e:activity={'valid':False,'error_type':type(e).__name__}
        ack=load_json(output/'terminal-handshake.json') if (output/'terminal-handshake.json').is_file() else None
        final=answer.read_text() if answer.is_file() else ''
        valid=(transport['exit_code']==0 and transport['process_reaped'] and not session.failed
            and same_runtime and activity['valid'] is True and final.strip()=='Controller decision submitted; session complete.'
            and isinstance(ack,dict) and ack.get('provider_called') is False and ack.get('paid_turn_added') is False)
        result={**transport,'schema':'historical_source_review_v2_controller_assessment_v1',
            'controller_stage':'source_review_v2','model':MODEL,'evidence_mode':evidence_mode,'valid':bool(valid),
            'turns':session.turns,'tool_calls':session.tool_calls,'failed':session.failed,'activity':activity,
            'harness_runtime_unchanged':same_runtime,'unresolved_accounting':unresolved,'terminal_handshake':ack,
            'model_authorship_proven':bool(valid and evidence_mode=='paid_controller'),'provider_budget':budget.snapshot(),
            'new_raw_download_admitted':False,'new_model_fit':False,'new_test_admitted':False}
        fresh_json(output/'assessment.json',result)
        if not valid:raise RuntimeError('v2 source review failed; preserve permanent attempt')
        return result
    finally:server.shutdown();server.server_close();thread.join(timeout=5)


def main(args):
    prepared=args.prepared.resolve()
    with (prepared.parent/'historical-ingest-controller.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        checked=preflight(prepared,args.budget.resolve(),args.canary.resolve(),args.codex_canary.resolve())
        fresh_json(prepared/'dispatch-claim.json',{**checked,'claimed_unix_ns':time.time_ns(),
            'nonce':secrets.token_hex(16),'pid':os.getpid(),'shared_lock_held':True,'automatic_retry':False})
        from dotenv import dotenv_values
        try:backend=TinkerGLMBackend(dotenv_values(args.env_file).get('TINKER_API_KEY'),args.tokenizer_cache)
        except Exception as e:
            fresh_json(prepared/'backend-initialization-failure.json',{'error_type':type(e).__name__,
                'message_sha256':digest(str(e)),'automatic_retry':False,'provider_sample_started':False});raise
        r=run_session(prepared=prepared,backend=backend,budget=PaidBudget(args.budget),evidence_mode='paid_controller',
            prompt='Inspect the requested pinned source evidence and repaired proposal schema. Review full '
            'publisher documents and exact file metadata as needed. Submit the first valid source-study '
            'proposal or a genuinely new missing-metadata request. No data downloads, samples, t7 changes, '
            'training or independent Test are allowed. Current raw-download headroom remains zero.')
        print(canonical({k:v for k,v in r.items() if k!='provider_budget'}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('prepared','budget','canary','codex-canary','env-file','tokenizer-cache'):p.add_argument('--'+n,type=Path,required=True)
    main(p.parse_args())
