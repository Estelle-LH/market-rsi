"""Reconstruct/export the controller-selected HistGB, not a new score trial.

One deterministic CPU fit of the ALREADY selected plan is necessary because
the original diagnostic discarded the fitted estimator. No parameter changes,
new labels or success-based retries. Require identical original predictions
before exporting. Only deserialize locally created bytes using an independently
trusted expected hash and the same pinned package versions.
"""
import argparse
import fcntl
import hashlib
import importlib.metadata
from pathlib import Path
import pickle
import sys
import time
from unittest.mock import patch

import numpy as np
from threadpoolctl import threadpool_limits

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import historical_grid_learning as learning
from historical_recorded_features import derive
from market_rsi import canonical,digest,file_hash,fresh_json,load_json


PACKAGES=('numpy','scipy','scikit-learn')


def versions():return {name:importlib.metadata.version(name) for name in PACKAGES}


def reconstruct(inputs,plan):
    if (plan['model']['algorithm']!='hist_gradient_boosting' or plan['normalizer']!='none'
            or plan['missing_input_action']!='native_nan'):
        raise ValueError('this reconstruction adapter is scoped to the selected native-NaN HistGB recipe')
    original=learning.HistGradientBoostingRegressor;captured=[]
    def capture(*args,**kwargs):
        estimator=original(*args,**kwargs);captured.append(estimator);return estimator
    with threadpool_limits(limits=1),patch.object(learning,'HistGradientBoostingRegressor',capture):
        report,arrays=learning.evaluate(inputs,plan)
    if len(captured)!=1:raise ValueError('exactly one deterministic reconstruction fit required')
    return captured[0],report,arrays


def require_identical_arrays(expected,actual):
    if set(expected)!=set(actual):raise ValueError('reconstruction prediction schema mismatch')
    for name,values in expected.items():
        other=actual[name]
        if (values.dtype!=other.dtype or values.shape!=other.shape
                or not np.array_equal(values,other,equal_nan=values.dtype.kind in 'fc')):
            raise ValueError('reconstruction differs from original artifact: '+name)


def load_trusted_bytes(path,expected_sha256,expected_versions):
    """expected_sha256 must come from a trusted runner receipt, not this file."""
    if versions()!=expected_versions:raise ValueError('same pinned runtime versions required')
    payload=path.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=expected_sha256:
        raise ValueError('model bytes changed; refuse deserialization')
    return pickle.loads(payload)


def predict_saved(estimator,inputs,plan,check):
    x=inputs['x'];matrix=np.column_stack([derive(x['entity'],x['decision_ms'],x['values'],inputs['names'],
        spec=s,cadence_ms=inputs['cadence_ms'],recorded_events=inputs.get('recorded_events'))['values'] for s in plan['features']])
    prediction=np.full(len(check),np.nan)
    with threadpool_limits(limits=1):prediction[check]=estimator.predict(matrix[check])
    before_projection=prediction.copy()
    if plan['output_transform']=='clip_to_probability_delta_bounds':
        mid=x['values'][:,inputs['names'].index('polymarket_ticks_ms.midpoint_from_reported_bbo')]
        mask=check&np.isfinite(mid);prediction[mask]=np.clip(prediction[mask],-mid[mask],1-mid[mask])
    return prediction,before_projection


def run(session,prior_audit,output):
    root=Path(__file__).resolve().parents[1]
    with (root/'artifacts/historical-ingest-controller.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if output.exists():raise ValueError('fresh permanent reconstruction claim required')
        audit=load_json(prior_audit);assessment=load_json(session/'session/assessment.json')
        workspace=session/'workspace';decision=load_json(workspace/'submitted-grid-learning-decision.json')
        if (not audit.get('passed') or audit['session_id']!=session.name or not assessment.get('valid')
                or not assessment.get('process_reaped') or decision!=audit['decision'] or decision['action']!='select'
                or audit['assessment_sha256']!=file_hash(session/'session/assessment.json')
                or audit['result_sha256']!=digest({k:v for k,v in audit.items() if k!='result_sha256'})):
            raise ValueError('exact audited completed controller selection required')
        preparation=load_json(session/'preparation.json')
        for name,sha in preparation['source_hashes'].items():
            if file_hash(root/name)!=sha or file_hash(session/'source-snapshot'/name)!=sha:
                raise ValueError('original frozen implementation changed')
        original=workspace/'trials'/decision['trial_id'];trial=load_json(original/'result.json')
        checked=next(t for t in audit['trials'] if t['trial_id']==decision['trial_id'])
        if (trial['result_sha256']!=checked['result_sha256']
                or file_hash(original/'predictions.npz')!=checked['prediction_sha256']
                or versions()!=trial['report']['runtime_packages']):
            raise ValueError('original trial/predictions/runtime changed')
        paths=[original/n for n in ('claim.json','result.json','predictions.npz')]
        paths.extend(workspace/n for n in ('current-inputs.npz','primary-labels.npz','workspace.json','submitted-grid-learning-decision.json'))
        binding={str(p.resolve()):file_hash(p) for p in paths}
        output.mkdir(parents=True,exist_ok=False,mode=0o700)
        fresh_json(output/'claim.json',{'session_id':session.name,'selected_trial_id':decision['trial_id'],
            'input_hashes':binding,'prior_audit_sha256':file_hash(prior_audit),
            'source_preparation_sha256':file_hash(session/'preparation.json'),
            'reconstructor_sha256':file_hash(Path(__file__)),'plan_sha256':digest(trial['plan']),
            'purpose':'one deterministic reconstruction of discarded selected estimator; not score optimization',
            'cpu_reconstruction_fits_authorized':1,'new_scientific_trial':False,'new_provider_calls':0,
            'new_dates_or_labels_allowed':False,'no_automatic_retry':True,'packages':versions()})
        try:
            started=time.monotonic();inputs=learning.read_inputs(workspace)
            with np.load(original/'predictions.npz',allow_pickle=False) as saved:
                expected={k:saved[k] for k in saved.files}
            estimator,report,arrays=reconstruct(inputs,trial['plan'])
            require_identical_arrays(expected,arrays)
            fresh_json(output/'selected-plan.json',trial['plan'])
            # This pickle contains only our trusted local sklearn object. Never
            # load a downloaded/controller-authored pickle or trust its self-hash.
            payload=pickle.dumps(estimator,protocol=5)
            with (output/'estimator.pkl').open('xb') as stream:stream.write(payload)
            model_sha=hashlib.sha256(payload).hexdigest()
            reloaded=load_trusted_bytes(output/'estimator.pkl',model_sha,versions())
            prediction,preclip=predict_saved(reloaded,inputs,trial['plan'],expected['check'])
            require_identical_arrays({'prediction':expected['prediction_delta_probability']},{'prediction':prediction})
            check=expected['check'];clipped=int(np.count_nonzero(preclip[check]!=prediction[check]))
            if any(file_hash(Path(p))!=h for p,h in binding.items()):raise ValueError('original evidence changed')
            result={'schema':'historical_selected_candidate_reconstruction_v1','passed':True,
                'selected_trial_id':decision['trial_id'],'source_session_id':session.name,
                'claim_sha256':file_hash(output/'claim.json'),'model_sha256':model_sha,
                'selected_plan_sha256':digest(trial['plan']),'selected_plan_file_sha256':file_hash(output/'selected-plan.json'),
                'original_predictions_sha256':file_hash(original/'predictions.npz'),
                'all_original_prediction_arrays_identical':True,'reload_predictions_identical':True,
                'original_estimator_was_persisted':False,'artifact_is_reconstructed_not_original':True,
                'cpu_reconstruction_fits':1,'new_scientific_trials':0,'new_provider_calls':0,
                'new_dev_test_opened':False,'new_dates_read':False,'rows_removed':0,'parameters_changed':False,
                'fit_rows':report['fit_rows'],'check_population_rows':report['check_population_rows'],
                'reconstructed_preprojection_clipped_rows':clipped,'elapsed_seconds':time.monotonic()-started,
                'packages':versions(),'formal_holdout_readiness':False,
                'limits':'A deterministic reconstruction, not recovery of the original in-memory object. '
                    'No original trial/result overwritten, no new candidate or improved score. '
                    'Future evaluation requires a separate exposure-audited, controller-owned protocol; '
                    'this model file alone does not authorize opening held-out labels. '
                    'Pickle is only for trusted runner-produced bytes in this exact pinned environment.'}
            result['result_sha256']=digest(result);fresh_json(output/'result.json',result);return result
        except Exception as exc:
            fresh_json(output/'failure.json',{'error':str(exc),'no_automatic_retry':True,
                'original_artifacts_written_by_reconstructor':False});raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('session','prior-audit','output'):p.add_argument('--'+name,type=Path,required=True)
    print(canonical(run(**{k:v.resolve() for k,v in vars(p.parse_args()).items()})))
