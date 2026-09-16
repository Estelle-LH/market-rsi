"""Exact learning Codex/MCP + local tokenizer probe, with NO provider sampling."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from codex_glm_model_catalog import model_catalog
from codex_glm_provider import TinkerGLMBackend
from codex_glm_responses_adapter import responses_request_to_glm
from codex_harness_wire_canary import FIXED_TEXT,_events
from historical_grid_learning_controller import ALLOWED_TOOLS,BASE_INSTRUCTIONS
from market_rsi import canonical,file_hash,fresh_json,load_json
from run_codex_glm_controller import codex_command,make_handler


def run(failed,output):
    assessment=load_json(failed/'session/assessment.json')
    if assessment['turns']!=0 or not assessment['process_reaped'] or assessment['valid']:
        raise ValueError('reaped pre-first-sample failure required')
    output.mkdir(parents=True,exist_ok=False)
    workspace=output/'workspace';shutil.copytree(failed/'workspace',workspace)
    prep=load_json(failed/'preparation.json');old=prep['command']
    tokenizer_cache=Path(old[old.index('--tokenizer-cache')+1])
    catalog=model_catalog(BASE_INSTRUCTIONS);fresh_json(output/'model-catalog.json',catalog)
    (output/'model-instructions.md').write_text(BASE_INSTRUCTIONS)
    diagnostics=[]
    class Probe:
        def handle(self,request):
            fresh_json(output/f'request-{len(diagnostics)+1:02}.json',request)
            note={'model':request.get('model'),'tool_types':[t.get('type') for t in request.get('tools',[])],
                  'tool_names':[t.get('name') for t in request.get('tools',[])],
                  'provider_calls':0,'input_conversion_ok':False,'tokenizer_ok':False}
            try:
                converted=responses_request_to_glm(request,ALLOWED_TOOLS);note['input_conversion_ok']=True
                # Loading the pinned local tokenizer cannot create a sampling client.
                backend=TinkerGLMBackend('unused-local-fixture-not-provider-credential',tokenizer_cache)
                encoded=backend.encode(converted);note['input_tokens']=len(encoded['token_ids']);note['tokenizer_ok']=True
            except Exception as exc:
                note.update(error_type=type(exc).__name__,error=str(exc))
            diagnostics.append(note);fresh_json(output/f'diagnostic-{len(diagnostics):02}.json',note)
            return _events('resp_local_probe','msg_local_probe',FIXED_TEXT)
    bearer=secrets.token_urlsafe(32)
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(Probe(),bearer,catalog))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        command=codex_command(workspace=workspace,answer=output/'last-message.txt',
            base_url=f'http://127.0.0.1:{server.server_address[1]}/v1',catalog=output/'model-catalog.json',
            instructions=output/'model-instructions.md',tool_mode='canary',controller_stage='grid_learning')
        fresh_json(output/'command.json',{'args':command})
        env={k:os.environ.get(k,'') for k in ('PATH','HOME','TMPDIR')};env['CODEX_GLM_LOOPBACK_KEY']=bearer
        process=subprocess.run(command,input=(failed/'prompt.txt').read_text(),text=True,capture_output=True,env=env,timeout=45)
        (output/'events.jsonl').write_text(process.stdout);(output/'stderr.log').write_text(process.stderr)
        report={'exit_code':process.returncode,'requests':len(diagnostics),'diagnostics':diagnostics,
            'provider_calls':0,'fits':0,'old_failed_artifacts_modified':False,
            'exact_learning_prompt_sha256':file_hash(failed/'prompt.txt'),
            'source_sha256':file_hash(Path(__file__))}
        fresh_json(output/'result.json',report);return report
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('failed','output'):p.add_argument('--'+key,type=Path,required=True)
    args=p.parse_args();print(canonical(run(args.failed.resolve(),args.output.resolve())))
