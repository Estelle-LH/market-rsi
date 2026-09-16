"""Explain audited original predictions without refitting or choosing a successor."""
import argparse
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from historical_grid_learning import read_inputs
from historical_grid_learning_controller import Broker
from historical_learning_diagnostics import diagnose
from market_rsi import canonical, digest, file_hash, fresh_json, load_json


def run(session, audit, output):
    checked = load_json(audit)
    if (not checked.get('passed') or checked['session_id'] != session.name or output.exists()
            or checked['assessment_sha256'] != file_hash(session/'session/assessment.json')
            or checked['result_sha256'] != digest({k:v for k,v in checked.items() if k!='result_sha256'})):
        raise ValueError('exact completed independent audit and fresh output required')
    workspace = session/'workspace'; broker = Broker(workspace)
    paths = [workspace/n for n in ['current-inputs.npz','primary-labels.npz','workspace.json']]
    for t in checked['trials']:
        paths.extend(workspace/'trials'/t['trial_id']/n for n in ['result.json','claim.json','predictions.npz'])
    before = {str(p):file_hash(p) for p in paths}
    source = Path(__file__).resolve().parents[1]
    sources = {n:file_hash(source/n) for n in ['historical_learning_diagnostics.py',
        'historical_recorded_features.py','historical_trade_windows.py',
        'historical_feature_composition.py','historical_grid_features.py']}
    output.mkdir(parents=True,exist_ok=False)
    fresh_json(output/'claim.json',{'session':session.name,'audit_sha256':file_hash(audit),
        'input_hashes':before,'diagnostic_sources':sources,'fits':0,'model_selection':False})
    reports = []
    for t in checked['trials']:
        trial = broker._trial(t['trial_id']);root=workspace/'trials'/t['trial_id']
        if trial['result_sha256'] != t['result_sha256']:
            raise ValueError('trial differs from independently audited original')
        claim=load_json(root/'claim.json')
        parent=broker._trial(claim['parent_trial_id']) if claim['parent_trial_id'] else None
        with np.load(root/'predictions.npz',allow_pickle=False) as a:
            arrays={k:a[k] for k in a.files}
        reports.append(diagnose(broker.inputs,trial,arrays,parent))
    if before != {str(p):file_hash(p) for p in paths}:
        raise ValueError('original artifact changed during explanation')
    if sources != {n:file_hash(source/n) for n in sources}:
        raise ValueError('diagnostic code changed during explanation')
    result={'passed':True,'schema':'historical_learning_explanation_audit_v1',
        'session_id':session.name,'claim_sha256':file_hash(output/'claim.json'),
        'result_audit_sha256':file_hash(audit),'trials':reports,
        'fits':0,'provider_calls':0,'source_values_imputed':False,'rows_removed':0,
        'fresh_holdout_opened':False,'auditor_sha256':file_hash(Path(__file__))}
    result['result_sha256']=digest(result);fresh_json(output/'audit.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('session','audit','output'):p.add_argument('--'+n,type=Path,required=True)
    result=run(**vars(p.parse_args()))
    print(canonical({k:result[k] for k in ['passed','session_id','result_sha256','fits','provider_calls']}))
