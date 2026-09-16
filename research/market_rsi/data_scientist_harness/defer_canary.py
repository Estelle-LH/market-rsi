"""Actual Codex source-only defer after a bad ID; synthetic replies, zero provider."""
import argparse
from pathlib import Path
from data_scientist_harness import fixtures
from data_scientist_harness.canary import ScriptedBackend,call
from data_scientist_harness.store import create,Store
from data_scientist_harness.run_controller import run_session
from market_rsi import load_json,digest,file_hash,fresh_json
from paid_budget import PaidBudget


def run(root):
    bootstrap=root.parent/(root.name+'-fixture');fixtures.workspace(bootstrap,failed=True)
    quality=load_json(bootstrap/'workspace.json')['quality']
    findings=[{'id':'fixture-only','reason':'No source admitted. This is synthetic mechanics.'}]
    manifest=create(root,quality=quality,findings=findings,allowed_dates=[],purpose='canary',network=False)
    backend=ScriptedBackend(findings,root)
    backend.responses=[call('inspect_harness',{}),call('acknowledge_current_findings',
        {'finding_sha256':digest(findings),'responses':[{'id':'fixture-only','handling':'No fitting',
        'next_evidence':'Real source QA'}]}),call('submit_research_decision',
        {'action':'defer','trial_id':'not-a-trained-candidate','reason':'Synthetic error-path test'}),
        call('submit_research_decision',{'action':'defer','trial_id':'','reason':'Synthetic successful defer; no source admitted.'})]
    budget=PaidBudget.create(root/'fixture-budget',{'experiment_id':'fixture-'+root.name,
        'cap_usd':'10','target_usd':'10','buckets_usd':{'learning':'10'},'authority':'Synthetic only; no provider.'})
    a=run_session(root,manifest,backend,budget,'synthetic_transport_fixture');records=Store(root,manifest).records()
    if not (a['valid'] and a['turns']==4 and len(records)==4 and records[2]['status']=='error'
            and 'empty string' in records[2]['result']['error']
            and records[3]['result']['selected'] is None and not (root/'trials').exists()):
        raise ValueError('source-only error/defer loop did not complete')
    result={'passed':True,'actual_tinker_calls':0,'actual_codex_cli':True,'scripted_samples':4,
        'fits':0,'source_admitted':False,'model_authorship_proven':False,
        'assessment_sha256':file_hash(root/'session/assessment.json'),'manifest_sha256':manifest}
    fresh_json(root/'defer-canary.json',result);print(result)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output.resolve())
