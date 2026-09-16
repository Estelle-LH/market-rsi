"""Bounded earlier-fit/later-score tabular learners for the separate pilot."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import pickle
import sys
import time
import warnings

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'audit_tools')]
import numpy as np
from sklearn.linear_model import Ridge,ElasticNet
from sklearn.ensemble import RandomForestRegressor,HistGradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from scipy.stats import spearmanr
from historical_grid_learning import validate_model,MODEL_FIELDS
from market_rsi import load_json,fresh_json,file_hash,digest

FEATURES=('lag_delta','abs_lag','signed_sqrt_lag','cubic_lag','mid_centered','spread',
          'log_past_quote_count','lag_times_spread','lag_times_mid_centered')
BASE=dict(features=['lag_delta'],model=dict(algorithm='ridge',parameters=dict(alpha=0.,fit_intercept=False)),normalizer='none')


def validate(plan,parent=None):
    if not isinstance(plan,dict) or set(plan)!={'features','model','normalizer'}:raise ValueError('exact plan keys: features, model, normalizer')
    f=plan['features']
    if not isinstance(f,list) or not 1<=len(f)<=len(FEATURES) or len(set(f))!=len(f) or any(v not in FEATURES for v in f):
        raise ValueError('unique supported feature names required')
    validate_model(plan['model'])
    if plan['normalizer'] not in ('none','fit_mean_std'):raise ValueError('explicit normalizer required')
    if parent is not None:
        changed=int(f!=parent['features'])+int((plan['model'],plan['normalizer'])!=(parent['model'],parent['normalizer']))
        if changed!=1:raise ValueError('change exactly features OR trainer/normalizer versus declared parent')
    return plan


def matrix(raw,names):
    x=raw[:,0];mid=raw[:,1]-.5;spread=raw[:,2]
    values={'lag_delta':lambda:x,'abs_lag':lambda:np.abs(x),'signed_sqrt_lag':lambda:np.sign(x)*np.sqrt(np.abs(x)),
        'cubic_lag':lambda:x**3,'mid_centered':lambda:mid,'spread':lambda:spread,
        'log_past_quote_count':lambda:np.log1p(raw[:,3]),'lag_times_spread':lambda:x*spread,
        'lag_times_mid_centered':lambda:x*mid}
    result=np.column_stack([values[n]() for n in names])
    if not np.isfinite(result).all():raise ValueError('nonfinite feature; no silent rows dropped')
    return result


def read_cache(record):
    path=Path(record['path']);h=load_json(path/'header.json')
    if (file_hash(path/'header.json')!=record['header_sha256'] or h['sha256']!=record['cache_sha256']
            or file_hash(path/'rows.f64')!=h['sha256'] or h['shape'][1]!=6
            or h['bytes']!=48*h['shape'][0] or (path/'rows.f64').stat().st_size!=h['bytes']):
        raise ValueError('immutable cache commitment differs')
    if not h['old_kernel_mask_unchanged'] or not h['valid_zero_labels_retained'] or not h['features_causal']:
        raise ValueError('source-specific cache sanity missing')
    raw=np.memmap(path/'rows.f64',dtype='<f8',mode='r',shape=tuple(h['shape']))
    if not np.isfinite(raw).all() or not len(raw):raise ValueError('empty/nonfinite cache')
    return raw,h


def fit(plan,records):
    validate(plan)
    if not records or len({r['date'] for r in records})!=len(records):raise ValueError('distinct Train dates required')
    xs=[];ys=[];ns=[]
    for r in records:
        raw,_=read_cache(r);xs.append(matrix(raw,plan['features']));ys.append(np.array(raw[:,4]));ns.append(len(raw))
    x=np.concatenate(xs);y=np.concatenate(ys);del xs,ys
    if len(x)<max(3,x.shape[1]+1) or len(x)>12000000:raise ValueError('fit row bound; no subsampling')
    scaler=StandardScaler().fit(x) if plan['normalizer']=='fit_mean_std' else None
    if scaler:x=scaler.transform(x)
    name=plan['model']['algorithm'];p=plan['model']['parameters']
    if name=='ridge':model=Ridge(**p,solver='svd')
    elif name=='elastic_net':model=ElasticNet(**p,random_state=23,selection='cyclic')
    elif name=='random_forest':model=RandomForestRegressor(**p,random_state=23,n_jobs=1)
    else:model=HistGradientBoostingRegressor(**p,random_state=23,early_stopping=False)
    with warnings.catch_warnings(record=True) as found:
        warnings.simplefilter('always');model.fit(x,y)
    return dict(plan=plan,model=model,scaler=scaler,train=records),dict(fit_rows=len(x),per_file_rows=ns,
        train_dates=[r['date'] for r in records],features=plan['features'],uniform_train_weights=True,
        transformed_feature_min=np.min(x,axis=0).tolist(),transformed_feature_max=np.max(x,axis=0).tolist(),
        coefficients=model.coef_.tolist() if hasattr(model,'coef_') else None,
        warnings=[dict(category=w.category.__name__,message=str(w.message)[:500]) for w in found])


def score(y,p,groups):
    if len(y)!=len(p) or not np.isfinite(p).all():raise ValueError('invalid paired predictions')
    e=(y-p)**2;b=y*y;mse=float(np.mean(e));mse0=float(np.mean(b));var=float(np.var(p))
    ic=float(np.corrcoef(y,p)[0,1]) if np.var(y)>0 and var>0 else None
    rank=float(spearmanr(y,p).statistic) if np.var(y)>0 and var>0 else None
    slope=float(np.mean((y-y.mean())*(p-p.mean()))/var) if var>0 else None
    unique,inverse=np.unique(groups,return_inverse=True);n=np.bincount(inverse)
    eb=np.bincount(inverse,weights=b);ec=np.bincount(inverse,weights=e)
    metrics=[dict(market_index=int(g),n=int(n[i]),baseline_sse=float(eb[i]),candidate_sse=float(ec[i])) for i,g in enumerate(unique)]
    return dict(n=len(y),baseline_mse=mse0,candidate_mse=mse,zero_prediction_skill=1-mse/mse0 if mse0 else None,
        baseline_rmse_price_bps=10000*np.sqrt(mse0),candidate_rmse_price_bps=10000*np.sqrt(mse),
        pearson_ic=ic,rank_ic=rank,calibration_slope=slope,
        calibration_intercept=float(y.mean()-slope*p.mean()) if slope is not None else None,
        zero_labels=int(np.sum(y==0)),markets=len(unique),markets_improved=sum(a['candidate_sse']<a['baseline_sse'] for a in metrics),
        top_baseline_sse_markets=sorted(metrics,key=lambda v:v['baseline_sse'],reverse=True)[:5],
        market_scores=metrics,no_iid_confidence_interval=True)


def evaluate(fitted,record,destination):
    if record['date']<=max(r['date'] for r in fitted['train']):raise ValueError('evaluation must be later than all fit dates')
    raw,h=read_cache(record);x=matrix(raw,fitted['plan']['features']);scaler=fitted['scaler']
    if scaler:x=scaler.transform(x)
    p=fitted['model'].predict(x)
    with Path(destination).open('xb') as f:np.save(f,p,allow_pickle=False)
    r=score(raw[:,4],p,raw[:,5]);r.update(date=record['date'],cache_sha256=h['sha256'],paired_rows_sha256=h['paired_rows_sha256'],
        predictions_sha256=file_hash(destination),fit_on_check=False)
    return r


def work(request,output):
    start=time.monotonic();output=Path(output)
    if (output/'result.json').exists():raise ValueError('result already exists')
    fitted,details=fit(request['plan'],request['train'])
    checkpoint=output/'model.pkl'
    with checkpoint.open('xb') as f:pickle.dump(fitted,f,protocol=5)
    scores=[evaluate(fitted,r,output/('predictions-'+r['date']+'.npy')) for r in request['check']]
    result=dict(plan=request['plan'],fit=details,scores=scores,checkpoint_sha256=file_hash(checkpoint),
        elapsed_seconds=time.monotonic()-start,source_and_request_sha256=digest(request),
        packages={k:importlib.metadata.version(k) for k in ('numpy','scipy','scikit-learn')},seed=23,provider_calls=0)
    fresh_json(output/'result.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--request',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();work(load_json(a.request),a.output)
