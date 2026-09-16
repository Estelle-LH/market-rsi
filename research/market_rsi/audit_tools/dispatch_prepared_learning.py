"""Dispatch one frozen, canary-verified research continuation; never loop/retry."""
import argparse
import fcntl
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from historical_grid_learning_controller import validate_workspace
from market_rsi import canonical,file_hash,fresh_json,load_json
from paid_budget import PaidBudget,money


def run(prepared,prior,audit):
    root=Path(__file__).resolve().parents[1]
    with (root/'artifacts/historical-ingest-controller.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (prepared/'dispatch-claim.json').exists() or (prepared/'session').exists():
            raise ValueError('permanent session already dispatched')
        p=load_json(prepared/'preparation.json');command=p['command']
        for name,sha in p['source_hashes'].items():
            if file_hash(root/name)!=sha or file_hash(prepared/'source-snapshot'/name)!=sha:
                raise ValueError('prepared source freeze changed')
        if (file_hash(command[0])!=p['runtime_sha256']
                or file_hash(prepared/'prompt.txt')!=p['prompt_sha256']
                or file_hash(prepared/'workspace/workspace.json')!=p['workspace_sha256']):
            raise ValueError('prepared runtime or input changed')
        validate_workspace(prepared/'workspace')
        canary=load_json(prepared/'transport-canary.json')
        if not canary['passed'] or canary['new_fits'] or canary['new_model_calls']:
            raise ValueError('unpaid prepared-workspace canary required')
        assessment=load_json(prior/'session/assessment.json')
        checked=load_json(audit)
        archive=load_json(prepared/'workspace/archive.json')
        carry=archive['completed_diagnostic']
        if (not assessment['valid'] or not assessment['process_reaped']
                or checked.get('passed') is not True or checked['session_id']!=prior.name
                or checked['assessment_sha256']!=file_hash(prior/'session/assessment.json')
                or carry['completed_session_id']!=prior.name
                or carry['result_audit_sha256']!=file_hash(audit)
                or checked['decision']['action']!='defer'):
            raise ValueError('exact audited completed capability deferral required')
        prior_trials={t.name for t in (prior/'workspace/trials').iterdir()}
        if prior_trials!={t.name for t in (prepared/'workspace/trials').iterdir()} or len(prior_trials)>=8:
            raise ValueError('all existing model trials must carry within total trial budget')
        for trial in prior_trials:
            for name in ('claim.json','result.json','predictions.npz'):
                if file_hash(prior/'workspace/trials'/trial/name)!=file_hash(prepared/'workspace/trials'/trial/name):
                    raise ValueError('prior trial artifact changed')
        budget=PaidBudget(Path(command[command.index('--budget')+1]));state=budget.snapshot()
        if (any(k.startswith(prepared.name+'-') for k in state['jobs'])
                or any(v['state']=='dispatched' and '-turn-' in k for k,v in state['jobs'].items())):
            raise ValueError('existing session claim or unresolved controller dispatch')
        if money(state['buckets']['learning']['available_usd'])<money('2'):
            raise ValueError('insufficient existing learning allocation')
        rows=subprocess.check_output(['/bin/ps','-axo','pid=,command='],text=True).splitlines()
        if any(str(root/'run_codex_glm_controller.py') in row
               or str(root/'bounded_historical_ingest.py') in row for row in rows):
            raise ValueError('another exact controller or ingest worker is active')
        fresh_json(prepared/'dispatch-claim.json',{
            'session_id':prepared.name,'claimed_unix_ns':time.time_ns(),
            'preparation_sha256':file_hash(prepared/'preparation.json'),
            'transport_canary_sha256':file_hash(prepared/'transport-canary.json'),
            'prior_result_audit_sha256':file_hash(audit),
            'runner_evidence_sha256':archive.get('pairing_audit',{}).get('audit_sha256'),
            'dispatcher_sha256':file_hash(Path(__file__)),
            'budget_before':{k:v for k,v in state.items() if k!='jobs'},
            'same_plan_retry':False,'no_automatic_retry':True})
        with (prepared/'runner.log').open('x') as log:
            process=subprocess.Popen(command,cwd=root,stdout=log,stderr=subprocess.STDOUT,
                start_new_session=True,pass_fds=(lock.fileno(),))
        receipt={'pid':process.pid,'process_group':process.pid,'command':command,
                 'lock_inherited':True,'started_unix_ns':time.time_ns()}
        fresh_json(prepared/'runner-process.json',receipt)
        return {'pid':process.pid,'session_id':prepared.name,'launched_once':True}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('prepared','prior','audit'):p.add_argument('--'+n,type=Path,required=True)
    print(canonical(run(**{k:v.resolve() for k,v in vars(p.parse_args()).items()})))
