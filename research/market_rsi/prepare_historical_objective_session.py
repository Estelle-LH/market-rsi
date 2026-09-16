"""Exclusive source-bound launch of one GLM open-Train objective decision."""
import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import time

from historical_grid_objective_controller import BASE_INSTRUCTIONS, prepare_workspace
from market_rsi import canonical, file_hash, fresh_json, identifier
from paid_budget import PaidBudget, money


def prepare(output,*,panel_directory,proposal,annotations,budget,runtime,env_file,tokenizer,execute=False,
            numerical_audit=None,previous_controller=None,prior_failed_session=None):
    output=output.absolute();runtime=runtime.absolute();identifier(output.name)
    if not runtime.is_file() or not os.access(runtime,os.X_OK) or not env_file.is_file() or not tokenizer.is_dir():
        raise ValueError('existing verified runtime, credential file and tokenizer required')
    state=PaidBudget(budget).snapshot()
    if any(key.startswith(output.name+'-') for key in state['jobs']):raise ValueError('permanent session ID already used')
    if money(state['buckets']['setup']['available_usd'])<money('1'):
        raise ValueError('insufficient existing setup allocation for a bounded next controller turn')
    if any(job['state']=='dispatched' and '-turn-' in key for key,job in state['jobs'].items()):
        raise ValueError('unresolved prior controller request; reconcile first')
    root=Path(__file__).absolute().parent
    lock=(root/'artifacts/historical-ingest-controller.lock').open('a+')
    try:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('another historical controller owns the shared lock')
        output.mkdir(parents=True,exist_ok=False,mode=0o700)
        prepare_workspace(output/'workspace',panel_directory=panel_directory,proposal=proposal,
            annotations=annotations,session_id=output.name,experiment_id=state['experiment_id'],
            numerical_audit=numerical_audit,previous_controller=previous_controller,prior_failed_session=prior_failed_session)
        prompt=BASE_INSTRUCTIONS
        if numerical_audit is not None:
            prompt+=' Your previous objective decision was stopped before training by a new independent arithmetic audit. '
            prompt+='Call inspect_numerical_correction before research/selection. It preserves every original query and decision '
            prompt+='alongside corrected diagnostics. This is new evidence after a causal numerical fix, not resampling the same prompt. '
            prompt+='You may retain or revise your objective on corrected evidence, or defer. Read numeric endpoints rather than misleading query names.'
            prompt+=' Prior query IDs do not exist in this new session. To retain an audited prior target, first call '
            prompt+='reuse_corrected_objective_query with its source_query_id, a fresh query_id, and a rationale. '
            prompt+='Then propose using the fresh query IDs. This reuses verified results without redoing target computation.'
        if prior_failed_session is not None:
            prompt+=' The previous corrective session ended without a valid decision because the new workspace could not '
            prompt+='reference old query IDs. That exact interface failure is archived in inspect_numerical_correction. '
            prompt+='This fresh run uses the tested explicit reuse tool; failed proposal texts are not imported as a decision.'
        (output/'prompt.txt').write_text(prompt,encoding='utf-8')
        command=[str(runtime),str(root/'run_codex_glm_controller.py'),'--session-id',output.name,
            '--output',str(output/'session'),'--workspace',str(output/'workspace'),'--prompt',str(output/'prompt.txt'),
            '--budget',str(budget.absolute()),'--budget-bucket','setup','--env-file',str(env_file.absolute()),
            '--tokenizer-cache',str(tokenizer.absolute()),'--tool-mode','canary','--controller-stage','grid_objective']
        sources={path.name:file_hash(path) for path in sorted(root.glob('*.py'))}
        snapshot=output/'source-snapshot';snapshot.mkdir()
        for name,sha in sources.items():
            (snapshot/name).write_bytes((root/name).read_bytes())
            if file_hash(snapshot/name)!=sha:raise ValueError('source changed during exact snapshot')
        receipt={'schema':'historical_grid_objective_preparation_v1','command':command,'source_hashes':sources,
            'source_snapshot_directory':str(snapshot),'runtime_sha256':file_hash(runtime),
            'workspace_sha256':file_hash(output/'workspace/workspace.json'),'prompt_sha256':file_hash(output/'prompt.txt'),
            'budget_before':{k:v for k,v in state.items() if k!='jobs'},
            'paid_controller_started':False,'download_started':False,'formal_experiment_started':False}
        fresh_json(output/'preparation.json',receipt)
        if not execute:return receipt
        fresh_json(output/'dispatch-claim.json',{'session_id':output.name,'claimed_unix_ns':time.time_ns(),
            'preparation_sha256':file_hash(output/'preparation.json')})
        if any(file_hash(root/name)!=sha for name,sha in sources.items()):raise ValueError('loaded source changed before dispatch')
        with (output/'runner.log').open('x') as log:
            process=subprocess.Popen(command,cwd=root,stdout=log,stderr=subprocess.STDOUT,
                start_new_session=True,pass_fds=(lock.fileno(),))
        fresh_json(output/'runner-process.json',{'pid':process.pid,'process_group':process.pid,'command':command,
            'lock_inherited':True,'started_unix_ns':time.time_ns()})
        return {'pid':process.pid,'session_id':output.name,'output':str(output),'paid_controller_started':True}
    finally:lock.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['output','panel-directory','proposal','annotations','budget','runtime','env-file','tokenizer']:
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--numerical-audit',type=Path)
    parser.add_argument('--previous-controller',type=Path)
    parser.add_argument('--prior-failed-session',type=Path)
    args=parser.parse_args();print(canonical(prepare(**vars(args))))
