"""Explain saved prediction MSE without fitting or applying a check-selected scale.

MSE(p,y) - MSE(0,y) = E[p**2] - 2 E[p*y]. All moments use the
original trial's score weights and full labelled check population. Subgroups
are additive accounting only, never filters or recommendations.
"""
import argparse
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from historical_grid_learning import read_inputs
from market_rsi import canonical, digest, file_hash, fresh_json, load_json


def balance(target, prediction, dates, markets, aggregation):
    target, prediction = np.asarray(target), np.asarray(prediction)
    n = len(target)
    if (not n or prediction.shape != target.shape or target.ndim != 1
            or len(dates) != n or len(markets) != n
            or not np.all(np.isfinite(target)) or not np.all(np.isfinite(prediction))):
        raise ValueError('same finite labelled population required')
    if aggregation not in {'equal_row','equal_day','equal_group'}:
        raise ValueError('unknown original score aggregation')
    keys = np.zeros(n, dtype=int) if aggregation == 'equal_row' else dates if aggregation == 'equal_day' else markets
    _, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
    weights = 1.0 / (len(counts) * counts[inverse])
    mean = lambda values: float(np.dot(weights, values))
    amplitude = mean(prediction ** 2); alignment = 2 * mean(prediction * target)
    baseline = mean(target ** 2); mse = mean((prediction-target)**2)
    delta = mse - baseline
    if not np.isclose(delta, amplitude-alignment, rtol=1e-10, atol=1e-15):
        raise ValueError('MSE decomposition failed')
    groups = {}
    for name, mask in [('quiet_label',target==0),('moving_label',target!=0)]:
        # ORIGINAL population weights: contributions add to the main metric.
        groups[name] = {'rows':int(mask.sum()), 'original_weight_share':float(weights[mask].sum()),
            'contribution_to_prediction_energy':float(np.dot(weights[mask],prediction[mask]**2)),
            'contribution_to_twice_target_alignment':float(2*np.dot(weights[mask],prediction[mask]*target[mask])),
            'contribution_to_mse_delta':float(np.dot(weights[mask],prediction[mask]**2-2*prediction[mask]*target[mask]))}
    return {'rows':n,'aggregation':aggregation,'model_mse_probability':mse,
        'persistence_mse_probability':baseline,'mse_delta_vs_persistence':delta,
        'prediction_energy':amplitude,'twice_target_alignment':alignment,
        'prediction_rms_probability_bps':float(np.sqrt(amplitude)*10000),
        'target_rms_probability_bps':float(np.sqrt(baseline)*10000),
        'mean_prediction_probability':mean(prediction),'mean_target_probability':mean(target),
        'identity_error':delta-(amplitude-alignment),'additive_subgroups':groups,
        'scaled_prediction_or_optimal_scale_computed':False}


def run(session, prior_audit, output):
    if output.exists():raise ValueError('fresh output directory required')
    audit=load_json(prior_audit)
    if (audit.get('passed') is not True or audit['session_id']!=session.name
            or audit['assessment_sha256']!=file_hash(session/'session/assessment.json')
            or audit['result_sha256']!=digest({k:v for k,v in audit.items() if k!='result_sha256'})):
        raise ValueError('matching valid completed result audit required')
    prep=load_json(session/'preparation.json')
    if any(file_hash(session/'source-snapshot'/n)!=h for n,h in prep['source_hashes'].items()):
        raise ValueError('original source snapshot changed')
    workspace=session/'workspace'
    paths=[workspace/n for n in ('current-inputs.npz','primary-labels.npz','workspace.json')]
    trials={r['trial_id']:r for r in audit['trials']}
    for name in sorted(trials):paths.extend((workspace/'trials'/name).iterdir())
    binding={str(p.resolve()):file_hash(p) for p in paths if p.is_file()}
    output.mkdir(parents=True,exist_ok=False)
    fresh_json(output/'claim.json',{'session_id':session.name,'prior_audit_sha256':file_hash(prior_audit),
        'input_hashes':binding,'auditor_sha256':file_hash(Path(__file__)),
        'purpose':'explain ALL previously scored model errors; no new fitted scale or selection',
        'frozen_before_analysis':True})
    try:
        inputs=read_inputs(workspace);x,y=inputs['x'],inputs['y'];reports=[]
        for name, original in sorted(trials.items()):
            root=workspace/'trials'/name;trial=load_json(root/'result.json');plan=trial['plan']
            if (trial['result_sha256']!=original['result_sha256']
                    or file_hash(root/'predictions.npz')!=original['prediction_sha256']):
                raise ValueError('audited trial changed')
            with np.load(root/'predictions.npz',allow_pickle=False) as archive:
                prediction=archive['prediction_delta_probability'];check=archive['check'];row_id=archive['row_id']
            if (not np.array_equal(row_id,x['row_id'])
                    or not np.array_equal(check,np.isin(x['date'],plan['check_utc_dates']))):
                raise ValueError('original population changed')
            labelled=check & y['available']
            def stats(mask):
                return balance(y['delta_probability'][mask],prediction[mask],x['date'][mask],
                               x['market'][mask],plan['score_aggregation'])
            all_rows=stats(labelled)
            for metric in ('model_mse_probability','persistence_mse_probability'):
                if not np.isclose(all_rows[metric],original['independent_scores']['all'][metric],rtol=1e-10,atol=1e-15):
                    raise ValueError('original independently scored metric changed')
            reports.append({'trial_id':name,'trial_result_sha256':trial['result_sha256'],
                'population_rows':int(check.sum()),'labelled_rows':int(labelled.sum()),
                'missing_label_rows':int((check & ~y['available']).sum()),
                'all':all_rows,'by_date':{d:stats(labelled & (x['date']==d)) for d in plan['check_utc_dates']}})
        if any(file_hash(Path(p))!=h for p,h in binding.items()):raise ValueError('input changed during analysis')
        result={'schema':'historical_prediction_error_balance_v1','passed':True,'session_id':session.name,
            'claim_sha256':file_hash(output/'claim.json'),'trials':reports,'new_prediction_fits':0,
            'new_nuisance_fits':0,'new_provider_calls':0,'rows_removed':0,'prediction_values_changed':False,
            'fresh_holdout':False,'limits':'Identity-based description of old opened-Train scores. '
                'Prediction energy exceeding twice target alignment explains the sign of MSE delta, '
                'not its causal origin or whether calibration will generalize. No check-optimal scale '
                'or rescaled score is computed. Quiet/moving contributions retain ORIGINAL weights '
                'and cannot be used as future-movement selection rules.'}
        result['result_sha256']=digest(result);fresh_json(output/'audit.json',result);return result
    except Exception as exc:
        fresh_json(output/'failure.json',{'error':str(exc),'original_artifacts_changed':False});raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('session','prior-audit','output'):p.add_argument('--'+name,type=Path,required=True)
    print(canonical(run(**{k:v.resolve() for k,v in vars(p.parse_args()).items()})))
