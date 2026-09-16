"""Independently verify an already-selected conditional diagnostic, not a new query.

Uses unstandardized intercept OLS and independent prior mid-CDF construction;
does not call the broker's conditional summarize/diagnose implementation.
"""
import argparse
from pathlib import Path
import sys

import numpy as np
from scipy.stats import rankdata

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from historical_grid_learning import read_inputs
from historical_recorded_features import derive
from market_rsi import canonical,digest,file_hash,fresh_json,load_json


def correlation(a,b):
    if len(a)<3 or np.std(a)<=1e-12 or np.std(b)<=1e-12:return None
    return float(np.corrcoef(a,b)[0,1])


def midcdf(reference,values):
    unique,counts=np.unique(reference,return_counts=True)
    cumulative=np.r_[0,np.cumsum(counts)]
    location=np.searchsorted(unique,values,side='left')
    exact=(location<len(unique)) & (unique[np.minimum(location,len(unique)-1)]==values)
    mass=cumulative[location].astype(float)
    mass[exact]+=counts[location[exact]]/2
    return mass/len(reference)


def reference_statistics(matrix,target,fit,check,dates,groups):
    combined=np.column_stack([matrix,target])
    ranked=np.column_stack([midcdf(combined[fit,j],combined[:,j]) for j in range(combined.shape[1])])
    residuals={};coefficients={}
    for space,values in [('raw',combined),('prior_ecdf',ranked)]:
        controls=np.column_stack([np.ones(len(target)),values[:,1:-1]])
        outcomes=values[:,[0,-1]]
        coef=np.linalg.lstsq(controls[fit],outcomes[fit],rcond=None)[0]
        coefficients[space]=coef.tolist();residuals[space]=outcomes-controls@coef
    def stats(mask):
        n=int(mask.sum());x=matrix[mask,0];y=target[mask]
        raw=residuals['raw'][mask];ranked_residual=residuals['prior_ecdf'][mask]
        variance=np.var(x) if n else 0
        return {'rows':n,'raw_pearson_ic':correlation(x,y),
            'raw_rank_ic':correlation(rankdata(x),rankdata(y)),
            'prior_linear_residual_ic':correlation(raw[:,0],raw[:,1]),
            'prior_rank_residual_ic':correlation(ranked_residual[:,0],ranked_residual[:,1]),
            'candidate_residual_variance_fraction':float(np.var(raw[:,0])/variance) if variance>1e-24 else None}
    return {'fit':stats(fit),'check':stats(check),
        'check_by_date':{str(d):stats(check & (dates==d)) for d in sorted(set(dates[check]))},
        'check_by_market':{str(g):stats(check & (groups==g)) for g in sorted(set(groups[check]))},
        'verification_coefficients':coefficients}


def compare(reference,reported):
    for name,value in reference.items():
        if name not in reported:raise ValueError('missing reported statistic '+name)
        actual=reported[name]
        if value is None:
            if actual is not None:raise ValueError('undefined statistic reported as numeric '+name)
        elif actual is None or not np.isclose(actual,value,atol=2e-9,rtol=2e-8):
            raise ValueError('conditional statistic mismatch '+name)


def run(session,prior_audit,output):
    if output.exists():raise ValueError('fresh output required')
    audit=load_json(prior_audit)
    if (not audit.get('passed') or audit['session_id']!=session.name
            or audit['assessment_sha256']!=file_hash(session/'session/assessment.json')
            or audit['result_sha256']!=digest({k:v for k,v in audit.items() if k!='result_sha256'})):
        raise ValueError('matching completed result audit required')
    workspace=session/'workspace';prep=load_json(session/'preparation.json')
    if any(file_hash(session/'source-snapshot'/n)!=h for n,h in prep['source_hashes'].items()):
        raise ValueError('original source snapshot changed')
    paths=[workspace/n for n in ('current-inputs.npz','primary-labels.npz','workspace.json')]
    queries=sorted((workspace/'conditional-diagnostics').iterdir())
    if not queries:raise ValueError('no controller-selected diagnostic to verify')
    for p in queries:
        paths.extend([p/'claim.json',p/'result.json'])
        trial_id=load_json(p/'claim.json')['arguments']['trial_id']
        paths.append(workspace/'trials'/trial_id/'result.json')
    binding={str(p.resolve()):file_hash(p) for p in paths}
    output.mkdir(parents=True,exist_ok=False)
    fresh_json(output/'claim.json',{'session_id':session.name,'input_hashes':binding,
        'prior_audit_sha256':file_hash(prior_audit),'auditor_sha256':file_hash(Path(__file__)),
        'new_hypotheses':0,'purpose':'independent reconstruction of already-executed nuisance fits'})
    try:
        i=read_inputs(workspace);x,y=i['x'],i['y'];results=[]
        for path in queries:
            claim=load_json(path/'claim.json');a=claim['arguments'];r=load_json(path/'result.json')
            if (r['result_sha256']!=digest({k:v for k,v in r.items() if k!='result_sha256'})
                    or r['claim_sha256']!=file_hash(path/'claim.json')):raise ValueError('query result binding changed')
            trial=load_json(workspace/'trials'/a['trial_id']/'result.json');plan=trial['plan']
            named={s['name']:s for s in plan['features']};names=[a['feature_name']]+a['control_names']
            specs=[named[n] for n in names]
            if (r['selected_specs_sha256']!=digest(specs) or r['trial_result_sha256']!=trial['result_sha256']):
                raise ValueError('chosen trial/features changed')
            matrix=np.column_stack([derive(x['entity'],x['decision_ms'],x['values'],i['names'],spec=s,
                cadence_ms=i['cadence_ms'],recorded_events=i.get('recorded_events'))['values'] for s in specs])
            check=np.isin(x['date'],plan['check_utc_dates'])
            cutoff=int(np.datetime64(min(plan['check_utc_dates']),'ms').astype(np.int64))
            eligible=np.isin(x['date'],plan['train_utc_dates']) & y['available']
            eligible&=(x['decision_ms']<cutoff)&(y['label_available_ms']<cutoff)
            eligible&=~np.isin(x['market'],np.unique(x['market'][check]))
            finite=np.all(np.isfinite(matrix),axis=1);labels=y['available']&np.isfinite(y['delta_probability'])
            fit=eligible&finite&labels;use=check&finite&labels
            support={'causally_eligible_fit_rows':int(eligible.sum()),'nuisance_fit_rows':int(fit.sum()),
                'check_population_rows':int(check.sum()),'check_labelled_rows':int((check&labels).sum()),
                'check_diagnostic_rows':int(use.sum()),'check_labelled_missing_inputs':int((check&labels&~finite).sum()),
                'fit_mask_sha256':digest(np.flatnonzero(fit).tolist()),'check_mask_sha256':digest(np.flatnonzero(use).tolist())}
            if support!=r['support'] or int(y['label_available_ms'][fit].max())>=cutoff:
                raise ValueError('conditional support or earlier-label boundary changed')
            ref=reference_statistics(matrix,y['delta_probability'],fit,use,x['date'],x['market'])
            for label in ('fit','check'):compare(ref[label],r[label])
            for date,v in ref['check_by_date'].items():compare(v,r['check_by_date'][date])
            for metric in ('raw_pearson_ic','raw_rank_ic','prior_linear_residual_ic','prior_rank_residual_ic'):
                values=[v[metric] for v in ref['check_by_market'].values() if v[metric] is not None]
                expected={'defined':len(values),'positive':sum(v>0 for v in values),
                          'negative':sum(v<0 for v in values),'equal_group_mean':float(np.mean(values)) if values else None}
                compare(expected,r['check_market_breadth'][metric])
            results.append({'query_id':path.name,'query_result_sha256':r['result_sha256'],'passed':True,
                'support':support,'independent_fit':ref['fit'],'independent_check':ref['check'],
                'independent_by_date':ref['check_by_date'],'market_breadth_verified':True,
                'last_fit_label_available_ms':int(y['label_available_ms'][fit].max()),'strict_cutoff_ms':cutoff})
        if any(file_hash(Path(p))!=h for p,h in binding.items()):raise ValueError('input changed during verification')
        result={'schema':'historical_conditional_independent_audit_v1','passed':True,'session_id':session.name,
            'claim_sha256':file_hash(output/'claim.json'),'queries':results,
            'verification_nuisance_regressions':4*len(results),'new_prediction_fits':0,
            'new_scientific_queries':0,'new_provider_calls':0,'rows_removed':0,'fresh_holdout':False,
            'limits':'Recomputes existing nuisance fits only. A matched-subset correlation is not full-population '
                'prediction skill or causality. Mixed daily signs and market breadth remain part of the evidence; '
                'no confidence interval or untouched validation is added.'}
        result['result_sha256']=digest(result);fresh_json(output/'audit.json',result);return result
    except Exception as exc:
        fresh_json(output/'failure.json',{'error':str(exc),'auditor_writes_to_originals':False});raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('session','prior-audit','output'):p.add_argument('--'+name,type=Path,required=True)
    print(canonical(run(**{k:v.resolve() for k,v in vars(p.parse_args()).items()})))
