"""No-paid-call canary of exact learning schemas and preserved pre-fit evidence."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

from historical_grid_learning import read_inputs, validate_plan
from historical_grid_learning_controller import TOOLS, failed_pre_fit_evidence
from market_rsi import canonical, digest, file_hash, fresh_json, load_json


def run(prepared, prior, completed=False):
    workspace=prepared/'workspace';root=Path(__file__).resolve().parent
    preparation=load_json(prepared/'preparation.json')
    if (prepared/'dispatch-claim.json').exists():raise ValueError('canary requires an undispatched prepared workspace')
    def sources():
        for name,sha in preparation['source_hashes'].items():
            if file_hash(root/name)!=sha or file_hash(prepared/'source-snapshot'/name)!=sha:
                raise ValueError('source freeze changed')
    sources()
    inputs=read_inputs(workspace)
    if completed:
        archive=load_json(workspace/'archive.json')['completed_diagnostic']
        prior_trial_ids=sorted(archive['all_prior_trials'])
        if set(prior_trial_ids)!={p.name for p in (workspace/'trials').iterdir()}:
            raise ValueError('complete prior trial inventory required')
        for name in prior_trial_ids:
            for file in ['claim.json','result.json','predictions.npz']:
                if file_hash(prior/'workspace/trials'/name/file)!=file_hash(workspace/'trials'/name/file):
                    raise ValueError('carried parent artifact changed')
        evidence={'profiles':archive['successful_feature_profiles_reused_without_recomputation'],
            'history':archive['verified_failure_history'],
            'first_unexecuted_request':{'plan':load_json(workspace/'trials'/prior_trial_ids[0]/'result.json')['plan'],
                                      'parent_trial_id':prior_trial_ids[0]}}
    else:
        prior_trial_ids=[];evidence=failed_pre_fit_evidence(prior,workspace)
    # Validate only: never submit or fit this copied request. Scientific values
    # are unchanged; the controller still makes its own first valid submission.
    request=copy.deepcopy(evidence['first_unexecuted_request'])
    fingerprint=digest(request['plan'])
    if not completed:request['parent_trial_id']=''
    validate_plan(request['plan'],inputs)
    if digest(request['plan'])!=fingerprint:raise ValueError('canary changed a scientific choice')
    profile_keys={digest(p['spec']) for p in evidence['profiles']}
    if any(digest(f) not in profile_keys for f in request['plan']['features']):
        raise ValueError('intended plan has unprofiled features')
    messages=[{'jsonrpc':'2.0','id':1,'method':'initialize'},
        {'jsonrpc':'2.0','id':2,'method':'tools/list'},
        {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'inspect_learning_library','arguments':{}}},
        {'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'inspect_learning_contract','arguments':{}}}]
    if completed:
        # Exercise the explanation on an existing original artifact, never execute a copied plan.
        messages.append({'jsonrpc':'2.0','id':5,'method':'tools/call','params':{
            'name':'inspect_learning_trial','arguments':{'trial_id':prior_trial_ids[-1]}}})
    child=subprocess.run([sys.executable,str(root/'historical_grid_learning_controller.py'),'--workspace',str(workspace)],
        input=''.join(canonical(m)+'\n' for m in messages),text=True,capture_output=True,timeout=45)
    if child.returncode:raise ValueError('stdio transport failed: '+child.stderr[-1000:])
    responses=[json.loads(line) for line in child.stdout.splitlines()]
    if len(responses)!=len(messages) or responses[1]['result']['tools']!=TOOLS:raise ValueError('wrong actual tool schemas')
    if any(r.get('error') or r['result'].get('isError') for r in responses):raise ValueError('tool transport error')
    explanation=None
    if completed:
        explanation=json.loads(responses[-1]['result']['content'][0]['text'])
        if (explanation['trial_id']!=prior_trial_ids[-1] or explanation['fits']!=0
                or explanation['trial_result_sha256']!=archive['all_prior_trials'][prior_trial_ids[-1]]['result_sha256']):
            raise ValueError('existing trial explanation changed evidence or fitted')
    sources()
    if sorted(p.name for p in (workspace/'trials').iterdir())!=prior_trial_ids or list((workspace/'features').iterdir()):
        raise ValueError('canary unexpectedly executed a feature or model')
    report={'passed':True,'real_stdio_transport':True,'source_snapshot_verified':True,
        'population_rows':len(inputs['x']['row_id']),'prior_feature_profiles':len(evidence['profiles']),
        'verified_failure_sessions':[h['session_id'] for h in evidence['history']],
        'original_plan_validates_without_scientific_change':True,'original_plan_sha256':fingerprint,
        'parent_trial_id_requirement':request['parent_trial_id'],
        'carried_prior_trials':prior_trial_ids,'prior_trials_reexecuted':False,
        'model_plan_submitted':False,'new_fits':0,'new_profiles':0,'new_model_calls':0,
        'existing_trial_explanation_sha256':digest(explanation) if explanation else None,
        'prior_assessment_sha256':file_hash(prior/'session/assessment.json')}
    report['result_sha256']=digest(report);fresh_json(prepared/'transport-canary.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared',type=Path,required=True);parser.add_argument('--prior',type=Path,required=True)
    parser.add_argument('--completed',action='store_true')
    print(canonical(run(**vars(parser.parse_args()))))
