"""Reference event-to-sample kernel, not a source loader or training admission.

Runner-owned canonical rows must have one explicit clock domain and entity.
Mixed domains/regressions fail; the kernel never picks a clock, filters a message
kind, repairs old plans, sorts late events or imputes missing labels. Source
attestation and real cache integration remain separate. All policy args required.
"""
from bisect import bisect_left,bisect_right
from math import isfinite
from data_scientist_harness.temporal_contract import validate


DAY=86400000


class SampleKernel:
    def __init__(self,rows,*,entity,clock_domain,clock_field,allowed_kinds,max_rows):
        if (not isinstance(entity,str) or not entity or not isinstance(clock_domain,str) or not clock_domain
                or clock_field not in ('source_ms','wrapper_ms')
                or not isinstance(allowed_kinds,(set,list,tuple)) or not allowed_kinds
                or any(not isinstance(k,str) or not k for k in allowed_kinds)
                or type(max_rows) is not int or max_rows<=0):
            raise ValueError('explicit bounded canonical scope required')
        if not rows or len(rows)>max_rows:raise ValueError('empty or oversized segment')
        self.rows=[];self.times=[];self.clock_field=clock_field
        for r in rows:
            if set(r)!={'key','entity','clock_domain','source_kind','time_ms','valid','value'}:
                raise ValueError('exact canonical row fields required')
            if r['entity']!=entity or r['clock_domain']!=clock_domain or r['source_kind'] not in allowed_kinds:
                raise ValueError('mixed entity/clock domain or unselected message kind; no silent filtering')
            key=tuple(r['key']);t=r['time_ms']
            if not key or any(type(k) is not int or k<0 for k in key) or type(t) is not int or t<0:
                raise ValueError('integer immutable key and clock required')
            if self.rows and (len(key)!=len(self.rows[-1]['key']) or key<=self.rows[-1]['key']):
                raise ValueError('arrival keys repeated or regressed')
            if self.times and t<self.times[-1]:raise ValueError('source clock regression; segment needs explicit upstream disposition')
            if type(r['valid']) is not bool:raise ValueError('explicit quote validity required')
            value=r['value']
            if r['valid'] and (type(value) not in (int,float) or not isfinite(value)):
                raise ValueError('valid quote needs finite value')
            self.rows.append({**r,'key':key});self.times.append(t)
        # Range max on adjacent gaps: no quadratic scan of dense windows.
        size=1
        while size<len(rows):size*=2
        self.size=size;self.tree=[0]*(size*2)
        for i in range(1,len(rows)):self.tree[size+i]=self.times[i]-self.times[i-1]
        for i in range(size-1,0,-1):self.tree[i]=max(self.tree[2*i],self.tree[2*i+1])

    def gap_max(self,first,last):
        left=self.size+first+1;right=self.size+last+1;value=0
        while left<right:
            if left&1:value=max(value,self.tree[left]);left+=1
            if right&1:right-=1;value=max(value,self.tree[right])
            left//=2;right//=2
        return value

    def check_index(self,i):
        if type(i) is not int or not 0<=i<len(self.rows):raise ValueError('explicit decision index required')

    def feature_at(self,i,spec):
        self.check_index(i)
        fields={'lookback_ms','lookup_tolerance_ms','minimum_observations','max_gap_ms','same_utc_day'}
        if set(spec)!=fields:raise ValueError('exact explicit feature policy required')
        for k in fields-{'same_utc_day'}:
            if type(spec[k]) is not int:raise ValueError('integer feature window parameters required')
        if (spec['lookback_ms']<=0 or not 0<=spec['lookup_tolerance_ms']<spec['lookback_ms']
                or spec['minimum_observations']<1 or spec['max_gap_ms']<=0 or type(spec['same_utc_day']) is not bool):
            raise ValueError('unsupported feature policy')
        d=self.rows[i];query=d['time_ms']-spec['lookback_ms']
        result={'available':False,'feature':None,'decision_key':d['key'],'decision_ms':d['time_ms'],
            'query_ms':query,'source_attested':False}
        def missing(reason):return {**result,'reason':reason}
        if not d['valid']:return missing('invalid_start_quote')
        anchor=bisect_right(self.times,query,hi=i+1)-1
        if anchor<0:return missing('no_prior_anchor')
        a=self.rows[anchor]
        if query-a['time_ms']>spec['lookup_tolerance_ms']:return missing('lookback_outside_tolerance')
        if not a['valid']:return missing('invalid_lookback_quote')
        count=i+1-bisect_left(self.times,query,hi=i+1)
        if count<spec['minimum_observations']:return missing('insufficient_window_observations')
        if self.gap_max(anchor,i)>spec['max_gap_ms']:return missing('lookback_gap_exceeded')
        if spec['same_utc_day'] and a['time_ms']//DAY!=d['time_ms']//DAY:return missing('day_boundary')
        return {**result,'available':True,'reason':'observed_lookback','feature':d['value']-a['value'],
            'anchor_key':a['key'],'anchor_ms':a['time_ms'],'actual_lookback_span_ms':d['time_ms']-a['time_ms'],
            'window_observations':count,'max_observed_gap_ms':self.gap_max(anchor,i)}

    def label_at(self,i,contract,*,same_utc_day):
        self.check_index(i);validate(contract)
        if (contract['clock']!=self.clock_field or contract['claim']!='recorded_observation_only' or contract['label_origin']!='decision_time'
                or contract['missing_endpoint']!='unavailable' or contract['invalid_quote']!='invalidate'
                or type(same_utc_day) is not bool):raise ValueError('unsafe or unsupported label policy')
        d=self.rows[i];target=d['time_ms']+contract['horizon_ms']
        result={'available':False,'label':None,'decision_key':d['key'],'decision_ms':d['time_ms'],
            'target_ms':target,'source_attested':False}
        def missing(reason):return {**result,'reason':reason}
        if not d['valid']:return missing('invalid_start_quote')
        closing=bisect_right(self.times,target,lo=i+1)
        if closing==len(self.rows):return missing('unbounded_tail')
        endpoint=(closing-1 if contract['endpoint_rule']=='backward_asof'
            else bisect_left(self.times,target,lo=i+1,hi=closing+1))
        if endpoint<=i:return missing('no_endpoint_observation')
        e=self.rows[endpoint];close=self.rows[closing]
        if abs(e['time_ms']-target)>contract['endpoint_tolerance_ms']:return missing('endpoint_outside_tolerance')
        if not e['valid']:return missing('invalid_endpoint_quote')
        if same_utc_day and close['time_ms']//DAY!=d['time_ms']//DAY:return missing('day_boundary')
        return {**result,'available':True,'reason':'observed_endpoint','label':e['value']-d['value'],
            'endpoint_key':e['key'],'endpoint_ms':e['time_ms'],'actual_span_ms':e['time_ms']-d['time_ms'],
            'label_available_after_key':close['key'],'label_available_after_ms':close['time_ms']}

    def materialize(self,contract,feature_spec):
        validate(contract)
        if contract['decision_rule']=='after_each_record':indices=range(len(self.rows))
        else:indices=[i for i in range(1,len(self.rows)) if self.times[i]>self.times[i-1]]
        result=[]
        for i in indices:
            f=self.feature_at(i,feature_spec);y=self.label_at(i,contract,same_utc_day=feature_spec['same_utc_day'])
            result.append({'decision_key':self.rows[i]['key'],'feature':f,'outcome':y,
                'numerically_available':f['available'] and y['available'],'source_admitted':False})
        return result
