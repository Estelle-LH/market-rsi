"""Read-only result audit; independent score arithmetic, no refitting or selection.

This file is not imported by the controller. It does not alter its frozen source.
The main population is never filtered by observed future movement; quiet/moving
breakdowns are additive post-hoc diagnostics on already-open Train only.
"""
import argparse
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller_activity_log import read_activity_events
from historical_recorded_features import derive
from historical_grid_learning import read_inputs, validate_plan
from historical_grid_learning_controller import assess_activity
from market_rsi import canonical, digest, file_hash, fresh_json, load_json
from paid_budget import PaidBudget


def require(condition, message):
    if not condition:raise ValueError(message)


def independently_score(target,prediction,dates,markets,aggregation):
    require(len(target)>0 and np.all(np.isfinite(target)) and np.all(np.isfinite(prediction)),
            'all covered targets need finite predictions')
    # Group-mean then unweighted mean, independently of the scorer's per-row weights.
    keys=(np.zeros(len(target),dtype=int) if aggregation=='equal_row'
          else dates if aggregation=='equal_day' else markets)
    losses=[];baselines=[];maes=[]
    for key in np.unique(keys):
        mask=keys==key;y=target[mask];p=prediction[mask]
        losses.append(float(np.mean((p-y)**2)))
        baselines.append(float(np.mean(y*y)));maes.append(float(np.mean(np.abs(p-y))))
    mse=float(np.mean(losses));base=float(np.mean(baselines))
    return {'model_mse_probability':mse,'persistence_mse_probability':base,
        'mse_skill_vs_persistence':1-mse/base if base>0 else None,
        'model_rmse_probability_bps':float(np.sqrt(mse)*10000),
        'persistence_rmse_probability_bps':float(np.sqrt(base)*10000),
        'model_mae_probability_bps':float(np.mean(maes)*10000)}


def trial_audit(root, inputs):
    result=load_json(root/'result.json');claim=load_json(root/'claim.json')
    require(result['result_sha256']==digest({k:v for k,v in result.items() if k!='result_sha256'}),'result digest')
    require(result['claim_sha256']==file_hash(root/'claim.json'),'claim changed')
    require(result['predictions_sha256']==file_hash(root/'predictions.npz'),'predictions changed')
    plan=result['plan'];validate_plan(plan,inputs);report=result['report'];x=inputs['x'];y=inputs['y']
    require(plan==claim['plan'] and digest(plan)==report['plan_sha256'],'plan mismatch')
    require(claim['semantic_plan_sha256']==digest({k:v for k,v in plan.items() if k!='rationale'}),'semantic plan mismatch')
    require(claim['frozen_before_execution'] is True,'missing pre-execution claim')
    with np.load(root/'predictions.npz',allow_pickle=False) as a:arrays={k:a[k] for k in a.files}
    require(set(arrays)=={'row_id','check','fit','prediction_delta_probability','check_model_prediction'},'prediction schema')
    n=len(x['row_id']);require(all(v.shape==(n,) for v in arrays.values()),'prediction shapes')
    require(np.array_equal(arrays['row_id'],x['row_id']),'row identity/order changed')
    check=np.isin(x['date'],plan['check_utc_dates']);train=np.isin(x['date'],plan['train_utc_dates'])
    cutoff=int(np.datetime64(min(plan['check_utc_dates']),'ms').astype(np.int64))
    causal=y['available'] & (x['decision_ms']<cutoff) & (y['label_available_ms']<cutoff)
    no_overlap=~np.isin(x['market'],np.unique(x['market'][check]))
    # Feature engine is reused only to reconstruct availability masks, not score or refit.
    matrix=np.column_stack([derive(x['entity'],x['decision_ms'],x['values'],inputs['names'],
        spec=f,cadence_ms=inputs['cadence_ms'],recorded_events=inputs.get('recorded_events'))['values'] for f in plan['features']])
    finite=np.all(np.isfinite(matrix),axis=1)
    supported=np.ones(n,dtype=bool) if plan['missing_input_action']=='native_nan' else finite
    fit=train & causal & no_overlap & supported
    require(np.array_equal(arrays['check'],check),'check population changed')
    require(np.array_equal(arrays['fit'],fit),'fit mask not prior-day/group isolated')
    require(np.array_equal(arrays['check_model_prediction'],check & supported),'model availability mismatch')
    prediction=arrays['prediction_delta_probability'];covered=check & y['available']
    require(np.all(np.isnan(prediction[~check])),'predictions outside declared check')
    require(np.all(np.isfinite(prediction[check])),'missing check prediction')
    require(np.all(prediction[check & ~supported]==0),'declared persistence fallback changed')
    if plan['output_transform']=='clip_to_probability_delta_bounds':
        mid=x['values'][:,inputs['names'].index('polymarket_ticks_ms.midpoint_from_reported_bbo')]
        mask=check & np.isfinite(mid)
        require(np.all(prediction[mask]>=-mid[mask]) and np.all(prediction[mask]<=1-mid[mask]),'output bounds')
    counts={'fit_rows':int(fit.sum()),'check_population_rows':int(check.sum()),
        'check_model_prediction_rows':int((check & supported).sum()),
        'check_persistence_fallback_rows':int((check & ~supported).sum()),
        'train_label_or_day_purged_rows':int((train & ~causal).sum()),
        'train_cross_check_market_rows':int((train & ~no_overlap).sum()),
        'train_missing_input_rows':int((train & ~finite).sum())}
    require(all(report[k]==v for k,v in counts.items()),'reported population counts mismatch')
    require(report['first_check_day_ms']==cutoff and report['last_fit_label_available_ms']<cutoff,'fit cutoff mismatch')
    require(not set(x['market'][fit]) & set(x['market'][check]),'Train/check market overlap')
    scores={}
    for key,mask in [('all',covered)]+[(d,covered & (x['date']==d)) for d in plan['check_utc_dates']]:
        score=independently_score(y['delta_probability'][mask],prediction[mask],x['date'][mask],x['market'][mask],plan['score_aggregation'])
        expected=report['score'] if key=='all' else report['by_check_date'][key]
        require(int(mask.sum())==expected['label_rows'],'covered label count')
        for metric,value in score.items():
            if value is None:require(expected[metric] is None,'undefined skill must remain undefined')
            else:require(np.isclose(expected[metric],value,rtol=1e-11,atol=1e-13),'independent score mismatch: '+metric)
        scores[key]=score
    # Audit D-1 normalizer statistics without refitting any predictor.
    if plan['normalizer']=='fit_mean_std':
        w=np.ones(int(fit.sum()))
        if plan['train_weighting']!='equal_row':
            keys=x['date'][fit] if plan['train_weighting']=='equal_day' else x['market'][fit]
            _,inv,c=np.unique(keys,return_inverse=True,return_counts=True);w=1/c[inv]
        mean=np.average(matrix[fit],axis=0,weights=w)
        require(np.allclose(report['normalizer_mean'],mean,rtol=1e-10,atol=1e-13),'Train-only normalizer means')
    subgroups={}
    for label,mask in [('unchanged_label',covered & (y['delta_probability']==0)),
                       ('changed_label',covered & (y['delta_probability']!=0)),
                       ('model_supported',covered & supported),('persistence_fallback',covered & ~supported),
                       ('complete_inputs',covered & finite),('missing_inputs',covered & ~finite)]:
        subgroups[label]={'rows':int(mask.sum()),'row_share':float(mask.sum()/covered.sum()),
            'equal_row_model_mse':float(np.mean((prediction[mask]-y['delta_probability'][mask])**2)) if mask.any() else None,
            'equal_row_persistence_mse':float(np.mean(y['delta_probability'][mask]**2)) if mask.any() else None}
    return {'trial_id':result['trial_id'],'result_sha256':result['result_sha256'],
        'prediction_sha256':result['predictions_sha256'],'counts':counts,'independent_scores':scores,
        'post_hoc_subgroups_not_selection_filters':subgroups,'refits':0,'passed':True,
        'claim':'adaptive opened-Train diagnostic; not untouched OOS or PnL'}


def run(session, output, budget):
    require(not output.exists(),'fresh audit output required')
    assessment=load_json(session/'session/assessment.json')
    require(assessment.get('valid') is True and assessment.get('process_reaped') is True,'completed valid reaped session required')
    require(assessment.get('terminal_handshake') is not None,'terminal handshake required')
    preparation=load_json(session/'preparation.json');source_root=Path(__file__).resolve().parents[1]
    for name,sha in preparation['source_hashes'].items():
        require(file_hash(session/'source-snapshot'/name)==sha,'source snapshot changed')
        require(file_hash(source_root/name)==sha,'controller source changed during/after run')
    workspace=session/'workspace';activity=assess_activity(workspace);inputs=read_inputs(workspace)
    trials=[p.name for p in sorted((workspace/'trials').iterdir()) if (p/'result.json').exists()]
    reports=[trial_audit(workspace/'trials'/t,inputs) for t in trials]
    state=PaidBudget(budget).snapshot();jobs={k:v for k,v in state['jobs'].items() if k.startswith(session.name+'-')}
    require(jobs and all(v['state'] in {'metered_terminal','uncertain_terminal','cancelled_before_dispatch'} for v in jobs.values()),'unresolved controller dispatch')
    result={'passed':True,'session_id':session.name,'source_files_verified':len(preparation['source_hashes']),
        'assessment_sha256':file_hash(session/'session/assessment.json'),'activity':activity,
        'decision':load_json(workspace/'submitted-grid-learning-decision.json'),'trials':reports,
        'budget_snapshot':{k:v for k,v in state.items() if k!='jobs'},
        'session_costs':{k:{n:v.get(n) for n in ['state','metered_usd','uncertain_upper_usd']} for k,v in jobs.items()},
        'new_model_calls':0,'refits':0,'fresh_dev_test_opened':False,'profitability_evidence':False,
        'auditor_sha256':file_hash(Path(__file__))}
    result['result_sha256']=digest(result);output.mkdir(parents=True,exist_ok=False)
    fresh_json(output/'audit.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['session','output','budget']:parser.add_argument('--'+name,type=Path,required=True)
    print(canonical(run(**vars(parser.parse_args()))))
