"""Reuse the actual isolated Codex/GLM transport, with this pilot's MCP tools."""
import os
from pathlib import Path
import secrets
import sys
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'audit_tools'),str(ROOT/'source_review_tools'),str(ROOT/'validation_tools')]
import run_codex_glm_controller as harness
from codex_glm_provider import ControllerSession,TinkerGLMBackend
from codex_glm_model_catalog import model_catalog
from source_review_tools.run_source_review import command_for_source_review
from market_rsi import fresh_json,load_json,file_hash
from memory_pilot.broker import Broker,INSTRUCTIONS,ALLOWED
from glm_canary import MODEL


def run_session(root,backend,budget,*,fixture=False):
    root=Path(root);manifest=file_hash(root/'config.json');broker=Broker(root,manifest)
    if fixture:
        if not broker.config['fixture'] or not budget.snapshot()['experiment_id'].startswith('fixture-'):raise ValueError('isolated fixture required')
    elif broker.config['fixture'] or type(backend) is not TinkerGLMBackend or not (root/'dispatch-claim.json').is_file():
        raise ValueError('paid dispatch provenance required')
    output=root/'session'
    session=ControllerSession(session_id=root.name,output=output,backend=backend,budget=budget,budget_bucket='learning',
        submit_tool='submit_candidate',allowed_tools=ALLOWED,protocol_error_tool='report_protocol_error',max_protocol_feedback=2)
    catalog=output/'model-catalog.json';instructions=output/'instructions.md'
    fresh_json(catalog,model_catalog(INSTRUCTIONS))
    with instructions.open('x') as f:f.write(INSTRUCTIONS)
    bearer=secrets.token_urlsafe(32)
    server=harness.ThreadingHTTPServer(('127.0.0.1',0),harness.make_handler(session,bearer,model_catalog(INSTRUCTIONS)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        answer=output/'last-message.txt'
        command=command_for_source_review(workspace=root,answer=answer,base_url=f'http://127.0.0.1:{server.server_address[1]}/v1',
            catalog=catalog,instructions=instructions,manifest_sha256=manifest,broker_script=ROOT/'memory_pilot/broker.py')
        command[1:1]=['-c','mcp_servers.controller_tools.tool_timeout_sec=210']
        command=[v.replace('supports_parallel_tool_calls=true','supports_parallel_tool_calls=false') for v in command]
        fresh_json(output/'command.json',dict(args=command))
        runtime=harness.codex_harness_identity(catalog=catalog,instructions=instructions,command=command)
        fresh_json(output/'harness-runtime.json',runtime)
        env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'HOME':os.environ.get('HOME',''),
            'TMPDIR':os.environ.get('TMPDIR','/tmp'),'CODEX_GLM_LOOPBACK_KEY':bearer}
        prompt='Inspect the experiment and available own archive. Research and test a useful supported candidate on Train. Record what happened, then submit one model or retain baseline. Complete a real bounded experiment, not another general harness redesign.'
        transport=harness.run_process(command,prompt,env,output)
        unresolved=harness.reconcile_unresolved_session_dispatches(session_id=root.name,budget=budget,output=output,transport=transport)
        broker.verify();records=broker.records()
        handshake=load_json(output/'terminal-handshake.json') if (output/'terminal-handshake.json').exists() else {}
        same=harness.codex_harness_identity(catalog=catalog,instructions=instructions,command=command)==runtime
        valid=(transport['exit_code']==0 and transport['process_reaped'] and not session.failed and same
            and sum(r['tool']=='submit_candidate' and r['error'] is None for r in records)==1
            and (root/'submission.json').exists() and answer.is_file()
            and answer.read_text().strip()=='Controller decision submitted; session complete.'
            and handshake.get('provider_called') is False and handshake.get('paid_turn_added') is False)
        assessment=dict(**transport,valid=bool(valid),fixture=fixture,model=MODEL,model_authorship_proven=bool(valid and not fixture),
            turns=session.turns,tool_calls=session.tool_calls,manifest_sha256=manifest,harness_runtime_unchanged=same,
            unresolved_accounting=unresolved,terminal_handshake=handshake,record_count=len(records))
        fresh_json(output/'assessment.json',assessment)
        if not valid:raise RuntimeError('controller session failed; preserve exact attempt, no resampling')
        return assessment
    finally:server.shutdown();server.server_close();thread.join(timeout=5)
