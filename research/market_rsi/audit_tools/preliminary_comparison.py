"""One frozen no-intercept OLS predictor; paired diagnostic scoring, not RSI."""
from array import array
import hashlib
import math
import struct

from market_rsi import digest
from typed_raw_profile import canonical_kernel, sample_at, DAY


def moments(x, y):
    if len(x) != len(y) or not x:
        raise ValueError('nonempty paired observations required')
    if any(not math.isfinite(v) for a in (x, y) for v in a):
        raise ValueError('nonfinite observation')
    return dict(n=len(x), sum_x=math.fsum(x), sum_y=math.fsum(y),
                sum_xx=math.fsum(v*v for v in x), sum_yy=math.fsum(v*v for v in y),
                sum_xy=math.fsum(a*b for a,b in zip(x,y)))


def fit(m):
    if type(m['n']) is not int or m['n'] <= 0 or m['sum_xx'] <= 0:
        raise ValueError('unidentifiable one-parameter fit')
    if any(not math.isfinite(v) for v in m.values()):
        raise ValueError('nonfinite moments')
    b=m['sum_xy']/m['sum_xx']
    return dict(model='one_feature_OLS', beta=b, intercept=0.0, alpha=0.0,
                normalization='none', sign_constraint='none', clipping='none',
                sample_weight='uniform', seed=23, train_moments=m, parameters_fitted=1)


def pearson(m):
    n=m['n']; vx=m['sum_xx']-m['sum_x']**2/n; vy=m['sum_yy']-m['sum_y']**2/n
    if vx <= 0 or vy <= 0:
        return None
    return max(-1.0,min(1.0,(m['sum_xy']-m['sum_x']*m['sum_y']/n)/math.sqrt(vx*vy)))


def ranks(values):
    order=sorted(range(len(values)),key=values.__getitem__); result=array('d',[0])*len(values)
    i=0
    while i < len(order):
        j=i+1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j+=1
        rank=(i+j-1)/2+1
        for k in range(i,j):
            result[order[k]]=rank
        i=j
    return result


def score(x,y,beta,with_rank=True):
    if not math.isfinite(beta):
        raise ValueError('finite frozen coefficient required')
    m=moments(x,y); n=m['n']
    predictions=array('d',(beta*a for a in x))
    mse0=m['sum_yy']/n
    mse1=math.fsum((b-p)**2 for b,p in zip(y,predictions))/n
    analytical=(m['sum_yy']-2*beta*m['sum_xy']+beta*beta*m['sum_xx'])/n
    if not math.isclose(mse1,analytical,rel_tol=1e-10,abs_tol=1e-16):
        raise ValueError('direct and moment residuals disagree')
    pm=moments(predictions,y); constant_prediction=max(predictions)==min(predictions)
    variance=0.0 if constant_prediction else pm['sum_xx']-pm['sum_x']**2/n
    slope=(pm['sum_xy']-pm['sum_x']*pm['sum_y']/n)/variance if variance>0 else None
    rank_ic=pearson(moments(ranks(predictions),ranks(y))) if with_rank else None
    return dict(n=n, moments=m, baseline_mse=mse0, candidate_mse=mse1,
                improvement=mse0-mse1, relative_improvement=(mse0-mse1)/mse0 if mse0 else None,
                baseline_rmse_price_bps=10000*math.sqrt(mse0),
                candidate_rmse_price_bps=10000*math.sqrt(mse1),
                candidate_pearson_ic=None if constant_prediction or max(y)==min(y) else pearson(pm), candidate_rank_ic=rank_ic,
                raw_feature_pearson_ic=pearson(m), baseline_pearson_ic=None, baseline_rank_ic=None,
                candidate_calibration_slope=slope,
                candidate_calibration_intercept=pm['sum_y']/n-slope*pm['sum_x']/n if slope is not None else None,
                zero_labels=sum(v==0 for v in y), rank_computed=with_rank)


def evaluate(profile,beta,progress=lambda *_:None):
    # Keep all published quality/missingness accounting; never repair or impute.
    quality=profile.summary(progress)
    all_x=array('d'); all_y=array('d'); assets=[]
    sample_hash=hashlib.sha256(); pred0=hashlib.sha256(); pred1=hashlib.sha256()
    for number,(asset,s) in enumerate(profile.entities.items()):
        if s.gaps['negative']:
            continue  # Published whole-segment exclusion, counted in quality.
        rows=s.rows(); kernel=canonical_kernel(rows,profile.contract); del rows
        prefix=[0]
        for valid in s.valid:
            prefix.append(prefix[-1]+int(valid))
        x=array('d'); y=array('d'); identity=hashlib.sha256(asset.encode()).digest()
        for i in range(1,len(s.t)):
            if s.t[i]==s.t[i-1]:
                continue
            a,b=sample_at(kernel,i,profile.contract,prefix,profile.day_start+DAY)
            if not (a['available'] and b['available']):
                continue
            u,v=a['feature'],b['label']; x.append(u); y.append(v)
            key=identity+struct.pack('>qQII',s.t[i],s.ordinal[i],s.message[i],s.inner[i])
            sample_hash.update(key+struct.pack('>dd',u,v))
            pred0.update(key+struct.pack('>d',0.0)); pred1.update(key+struct.pack('>d',beta*u))
        if x:
            assets.append(score(x,y,beta,with_rank=False)); all_x.extend(x); all_y.extend(y)
        if number%250==0:
            progress(number+1,len(profile.entities))
    scored=score(all_x,all_y,beta)
    if scored['n'] != quality['counts']['numerically_available']:
        raise ValueError('paired mask differs from frozen sample kernel')
    for name,value in scored['moments'].items():
        if not math.isclose(value,quality['paired_moments'][name],rel_tol=1e-8,abs_tol=1e-8):
            raise ValueError('sample moment parity failure')
    return dict(quality=quality, metrics=scored, anonymous_asset_metrics=assets,
                tokens_with_paired_samples=len(assets), tokens_improved=sum(a['improvement']>0 for a in assets),
                tokens_worse=sum(a['improvement']<0 for a in assets), tokens_tied=sum(a['improvement']==0 for a in assets),
                paired_rows_sha256=sample_hash.hexdigest(), baseline_predictions_sha256=pred0.hexdigest(),
                candidate_predictions_sha256=pred1.hexdigest(), same_rows_both_arms=True,
                beta=beta, fits_on_check=0, raw_rows_exported=0)


def aggregate(reports,expected_dates):
    seen=[r['spec']['date'] for r in reports]
    if seen != expected_dates or not all(r['complete'] for r in reports):
        return dict(complete=False, reason='all four predeclared files must complete', planned_dates=expected_dates, observed_dates=seen)
    m=[r['evaluation']['metrics'] for r in reports]
    if any(a['n']<=0 for a in m):
        raise ValueError('empty scored file')
    b=math.fsum(a['baseline_mse'] for a in m)/len(m)
    c=math.fsum(a['candidate_mse'] for a in m)/len(m)
    return dict(complete=True, aggregation='equal selected hour per date', dates=seen,
                baseline_mse=b,candidate_mse=c,relative_improvement=(b-c)/b if b else None,
                baseline_rmse_price_bps=10000*math.sqrt(b),candidate_rmse_price_bps=10000*math.sqrt(c),
                dates_improved=sum(a['improvement']>0 for a in m), dates_total=len(m),
                paired_rows=sum(a['n'] for a in m), independent_final_test=False, promotion_allowed=False)
