"""On-demand open-Train objective primitives for recorded quote GRID states.

No default target or horizon is selected here. A researcher must supply a full
spec. These are probability-quote forecasting diagnostics, not executable PnL
or a substitute for a missing trade tape. Future observations are labels only.
"""
from collections import Counter
from dataclasses import dataclass
import math

import numpy as np


FAMILIES={'point_delta','forward_mean_delta','forward_median_delta','forward_ewma_delta'}
SPEC_FIELDS={'family','window_start_ms','window_end_ms','half_life_ms',
             'minimum_observations','minimum_window_coverage','label_max_age_ms'}


def validate_spec(spec, cadence_ms, source_max_age_ms):
    if type(cadence_ms) is not int or cadence_ms<=0 or type(source_max_age_ms) is not int or source_max_age_ms<0:
        raise ValueError('positive grid cadence and nonnegative source age required')
    if not isinstance(spec,dict) or set(spec)!=SPEC_FIELDS:raise ValueError('complete typed objective spec required')
    if spec['family'] not in FAMILIES:raise ValueError('objective family needs an executable extension')
    for key in ['window_start_ms','window_end_ms','minimum_observations','label_max_age_ms']:
        if type(spec[key]) is not int or spec[key]<(0 if key=='label_max_age_ms' else 1):
            raise ValueError('positive integer window/count and nonnegative label age required')
    start,end=spec['window_start_ms'],spec['window_end_ms']
    if start>end or start%cadence_ms or end%cadence_ms:
        raise ValueError('target times must align to the actual recorded grid; no dense-time fabrication')
    n=(end-start)//cadence_ms+1
    if n>128 or end>86400000:raise ValueError('bounded objective query supports128 grid points and at most one day')
    if spec['minimum_observations']>n:raise ValueError('minimum observations exceeds declared window')
    if (type(spec['minimum_window_coverage']) not in (float,int)
            or not 0<spec['minimum_window_coverage']<=1):raise ValueError('explicit window coverage in(0,1] required')
    if spec['label_max_age_ms']>source_max_age_ms:raise ValueError('cannot resurrect source-rejected stale labels')
    if spec['family']=='point_delta' and (start!=end or spec['minimum_observations']!=1):
        raise ValueError('point target requires exactly one actual grid point')
    if spec['family']=='forward_ewma_delta':
        if type(spec['half_life_ms']) is not int or spec['half_life_ms']<=0:
            raise ValueError('controller-selected positive forward EWMA half life required')
    elif spec['half_life_ms'] is not None:raise ValueError('half life is only defined for forward EWMA')
    return spec


@dataclass
class GridPanel:
    entity: np.ndarray
    time_ms: np.ndarray
    midpoint: np.ndarray
    quote_age_ms: np.ndarray
    date: np.ndarray
    phase: np.ndarray
    cadence_ms: int
    max_age_ms: int

    def validate(self):
        n=len(self.time_ms)
        arrays=[self.entity,self.time_ms,self.midpoint,self.quote_age_ms,self.date,self.phase]
        if any(not isinstance(v,np.ndarray) or v.ndim!=1 for v in arrays):
            raise ValueError('one dimensional numpy columns required')
        if not 0<n<=500000 or any(len(v)!=n for v in [self.entity,self.midpoint,self.quote_age_ms,self.date,self.phase]):
            raise ValueError('bounded aligned nonempty grid panel required')
        if (not np.issubdtype(self.time_ms.dtype,np.signedinteger) or np.any(self.time_ms<0)
                or np.any(self.time_ms>np.iinfo(np.int64).max-86400000)):
            raise ValueError('bounded signed integer millisecond clock required')
        if type(self.cadence_ms) is not int or self.cadence_ms<=0 or np.any(self.time_ms%self.cadence_ms):
            raise ValueError('aligned actual grid clock required')
        if type(self.max_age_ms) is not int or self.max_age_ms<0:
            raise ValueError('nonnegative source age required')
        if np.any(self.entity<0) or not np.issubdtype(self.entity.dtype,np.integer):raise ValueError('stable entity codes required')
        if np.any(np.isinf(self.midpoint)):raise ValueError('infinite midpoint is invalid, not missing')
        if np.any(np.isfinite(self.midpoint)&((self.midpoint<0)|(self.midpoint>1))):raise ValueError('probability midpoint range invalid')
        if np.any(np.isfinite(self.midpoint)&(~np.isfinite(self.quote_age_ms)|(self.quote_age_ms<0)|(self.quote_age_ms>self.max_age_ms))):
            raise ValueError('source-invalid/stale midpoint must remain unavailable')
        if not set(self.phase)<= {'before_nominal_window','within_nominal_window','after_nominal_window'}:
            raise ValueError('explicit nominal-phase annotations required')
        keys=np.stack([self.entity,self.time_ms],axis=1)
        if len(np.unique(keys,axis=0))!=n:raise ValueError('duplicate entity/time row')


def targets(panel, spec):
    """Return one outcome slot per original row; missing labels stay NaN with reason."""
    panel.validate();validate_spec(spec,panel.cadence_ms,panel.max_age_ms)
    n=len(panel.time_ms);start,end=spec['window_start_ms'],spec['window_end_ms']
    offsets=np.arange(start,end+1,panel.cadence_ms,dtype=np.int64)
    # Lookup whole existing rows by SAME entity and exact future grid time. No
    # cross-asset/market join and no nearest-row substitution through gaps.
    lo=int(panel.time_ms.min());span=int(panel.time_ms.max())-lo+end+panel.cadence_ms
    if int(panel.entity.max())*span+span>=np.iinfo(np.int64).max:raise ValueError('bounded lookup key overflow')
    keys=panel.entity.astype(np.int64)*span+panel.time_ms-lo
    order=np.argsort(keys);ordered=keys[order]
    observations=[]
    for offset in offsets:
        desired=keys+offset;where=np.searchsorted(ordered,desired)
        safe=np.minimum(where,n-1);idx=order[safe]
        found=(where<n)&(ordered[safe]==desired)
        usable=found&np.isfinite(panel.midpoint[idx])&(panel.quote_age_ms[idx]<=spec['label_max_age_ms'])
        observations.append(np.where(usable,panel.midpoint[idx],np.nan))
    matrix=np.stack(observations,axis=1)
    present=np.isfinite(matrix);count=present.sum(axis=1)
    required=max(spec['minimum_observations'],math.ceil(len(offsets)*spec['minimum_window_coverage']))
    covered=count>=required
    # Centre BEFORE averaging. Averaging repeated .49-like levels and then
    # subtracting the current level can invent a tiny nonzero target for an
    # exactly constant path. This algebraic repair adds no economic deadband.
    constant_path=np.all(~present|(matrix==panel.midpoint[:,None]),axis=1)&(count>0)
    matrix-=panel.midpoint[:,None]
    level=np.full(n,np.nan)
    if spec['family'] in {'point_delta','forward_mean_delta'}:
        np.divide(np.nansum(matrix,axis=1),count,out=level,where=count>0)
    elif spec['family']=='forward_median_delta':
        eligible=np.flatnonzero((count>0)&np.isfinite(panel.midpoint))
        level[eligible]=np.nanmedian(matrix[eligible],axis=1)
    else:
        # Forward weighting is LABEL construction, never a causal input feature.
        weights=np.exp2((offsets-end)/spec['half_life_ms'])
        denominators=(present*weights).sum(axis=1)
        np.divide(np.nansum(matrix*weights,axis=1),denominators,out=level,where=denominators>0)
    current=np.isfinite(panel.midpoint)
    available=current&covered
    delta=np.where(available,level,np.nan)
    reason=np.full(n,'covered',dtype=object)
    reason[~covered]='insufficient_future_grid_coverage'
    reason[~current]='current_quote_unavailable'
    return {'delta_probability':delta,'delta_probability_bps':delta*10000,
            'label_available_ms':panel.time_ms+end,'available':available,
            'future_observation_count':count,'required_future_observations':required,
            'all_observed_future_quotes_equal_current':constant_path&available,
            'reason':reason,'spec':dict(spec),'full_population_rows':n}


def profile(panel, spec):
    result=targets(panel,spec);delta=result['delta_probability'];usable=result['available']
    def summary(mask):
        covered=mask&usable;values=delta[covered]
        return {'population_rows':int(mask.sum()),'covered_rows':int(covered.sum()),
            'coverage_fraction':float(covered.sum()/mask.sum()) if mask.any() else None,
            'unchanged_fraction_among_covered':float(np.mean(values==0)) if len(values) else None,
            'all_observed_future_quotes_equal_current_fraction':float(np.mean(result['all_observed_future_quotes_equal_current'][covered])) if len(values) else None,
            'persistence_mae_probability_bps':float(np.mean(np.abs(values))*10000) if len(values) else None,
            'persistence_mse_probability':float(np.mean(values**2)) if len(values) else None,
            'persistence_rmse_probability_bps':float(np.sqrt(np.mean(values**2))*10000) if len(values) else None}
    all_rows=summary(np.ones(len(delta),dtype=bool))
    return {'schema':'historical_open_train_grid_objective_profile_v1','spec':dict(spec),
        'all_rows':all_rows,'missing_label_reasons':dict(Counter(result['reason'])),
        'by_nominal_phase':{phase:summary(panel.phase==phase) for phase in sorted(set(panel.phase))},
        'by_open_train_date':{day:summary(panel.date==day) for day in sorted(set(panel.date))},
        'unit_definition':'one probability basis point=0.0001 absolute probability, not relative price return',
        'baseline':'zero future probability delta, equivalent to persistence of current midpoint',
        'labels_are_future_only_not_features':True,'phase_counts_are_not_verified_settlement':True,
        'filter_by_future_movement':False,'candidate_model_evaluated':False,
        'final_objective_selected':False,'profitability_evidence':False,
        'scale_free_model_skill_requires_nonzero_persistence_mse':True}
