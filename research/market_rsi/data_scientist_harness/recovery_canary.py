"""Actual Codex continuation after one synthetic malformed output; no provider."""
import argparse
from pathlib import Path
from data_scientist_harness.canary import ScriptedBackend
from data_scientist_harness import fixtures
from data_scientist_harness.run_controller import run_session
from data_scientist_harness.store import Store
from market_rsi import load_json,file_hash,fresh_json
from paid_budget import PaidBudget


def run(root):
    sha=fixtures.workspace(root,network=True)
    budget=PaidBudget.create(root/'fixture-budget',{'experiment_id':'fixture-'+root.name,
        'cap_usd':'10','target_usd':'10','buckets_usd':{'learning':'10'},'authority':'Synthetic only; no provider.'})
    backend=ScriptedBackend(load_json(root/'findings.json'),root)
    backend.responses.insert(1,'<tool_call>record_research-obj-1</arg_value></tool_call>')
    # The runner control receipt consumes record0002; keep original fixture
    # references aligned, without changing any scientific fixture values.
    import re
    backend.responses=[re.sub(r'(?<![0-9])000([2-8])(?![0-9])',
        lambda m:f'{int(m.group(0))+1:04d}',s) for s in backend.responses]
    assessment=run_session(root,sha,backend,budget,'synthetic_transport_fixture')
    records=Store(root,sha).records()
    if not (assessment['valid'] and backend.sample_calls==19 and len(records)==19
            and assessment['runner_protocol_feedbacks']==1
            and sum(r['tool']=='train_candidate' and r['status']=='ok' for r in records)==4):
        raise ValueError('exact one-error/continued Codex loop required')
    result={'passed':True,'actual_tinker_calls':0,'actual_codex_cli':True,'scripted_samples':19,
        'runner_protocol_feedbacks':1,'actual_cpu_fits':4,'model_authorship_proven':False,
        'assessment_sha256':file_hash(root/'session/assessment.json'),'manifest_sha256':sha}
    fresh_json(root/'recovery-canary.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    print(run(p.parse_args().output.resolve()))
