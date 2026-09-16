"""Typed event-sample policy, executable on bounded synthetic/canonical segments.

No raw reader, source admission or trainer. The controller chooses every policy
field. Prose cannot override these fields. See SAMPLE_CONTRACT_2026-09-13.md.
"""
from bisect import bisect_left,bisect_right
from copy import deepcopy
from decimal import Decimal,InvalidOperation
from market_rsi import digest,file_hash
from data_scientist_harness import temporal_contract
from data_scientist_harness.event_sample_kernel import SampleKernel


def obj(fields):return {'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}
E=temporal_contract.enum
I={'type':'integer'}
QUOTES=obj({'book':E('exclude','direct_bbo','book_levels'),
    'price_change':E('exclude','direct_bbo'),'rest_snapshot':E('exclude','direct_bbo','book_levels')})
FEATURE=obj({'lookback_ms':I,'lookup_tolerance_ms':I,'minimum_observations':I,'max_gap_ms':I,
    'window_edges':E('both','right'),'count_observations':E('all_records','valid_quotes'),
    'day_boundary':E('purge','allow')})
COVERAGE=obj({'mode':E('anchor_and_gap_only','explicit_backward_slots'),
    'slot_ms':I,'tolerance_ms':I,'minimum_coverage_per_mille':I})
SCHEMA=obj({'temporal':temporal_contract.SCHEMA,'quote_rules':QUOTES,'feature':FEATURE,'coverage':COVERAGE,
    'label_max_gap_ms':I,'tail_closure':E('strictly_later_observed_record'),
    'train_cutoff':E('label_maturity_strictly_before_cutoff'),
    'check_cutoff':E('label_maturity_strictly_before_cutoff'),
    'clock_regression':E('reject_segment'),'unavailable':E('count_do_not_zero'),
    'claim':E('recorded_observation_only')})


def validate(c):
    # Local import avoids the schema/broker import cycle; one served vocabulary.
    from data_scientist_harness.broker import validate_shape
    validate_shape(c,SCHEMA,'sample_contract');temporal_contract.validate(c['temporal'])
    t=c['temporal'];f=c['feature'];g=c['coverage'];q=c['quote_rules']
    if (t['label_origin']!='decision_time' or t['missing_endpoint']!='unavailable'
            or t['invalid_quote']!='invalidate' or t['claim']!='recorded_observation_only'):
        raise ValueError('unsafe temporal policy; no implicit fallback')
    kinds=[k for k,v in q.items() if v!='exclude']
    if not kinds:raise ValueError('choose at least one quote source kind')
    if t['clock']=='source_ms' and 'rest_snapshot' in kinds and len(kinds)>1:
        raise ValueError('REST snapshot and WS source clocks cannot share one declared domain; request another adapter')
    if not 4<=f['lookback_ms']<=86400000 or not 0<=f['lookup_tolerance_ms']<f['lookback_ms']:
        raise ValueError('explicit lookback4ms..1day and smaller nonnegative tolerance required')
    if not 1<=f['minimum_observations']<=100000 or not 1<=f['max_gap_ms']<=86400000:
        raise ValueError('explicit bounded observation count and gap required')
    if not 0<=c['label_max_gap_ms']<=86400000:
        raise ValueError('label gap0(disabled)..1day required')
    if g['mode']=='anchor_and_gap_only':
        if any(g[k]!=0 for k in ('slot_ms','tolerance_ms','minimum_coverage_per_mille')):
            raise ValueError('disabled extra grid requires explicit zero grid parameters')
    elif (not 1<=g['slot_ms']<=f['lookback_ms'] or not 0<=g['tolerance_ms']<=f['lookback_ms']
            or not 0<=g['minimum_coverage_per_mille']<=1000 or f['lookback_ms']//g['slot_ms']+1>1024):
        raise ValueError('explicit grid width/tolerance/coverage required; at most1024slots per probe window')
    return kinds


def number(x):
    if type(x) not in (str,int,float):raise ValueError('numeric quote field required')
    try:v=Decimal(str(x))
    except InvalidOperation as e:raise ValueError('malformed decimal') from e
    if not v.is_finite():raise ValueError('nonfinite decimal')
    return v


def quote(kind,payload,rules):
    """One already-unwrapped message/inner entry. No reconstruction/fallback."""
    if kind not in rules:raise ValueError('unknown quote kind')
    mode=rules[kind]
    if mode=='exclude':return {'included':False,'valid':False,'value':None,'reason':'excluded_kind'}
    try:
        if mode=='direct_bbo':bid,ask=number(payload['best_bid']),number(payload['best_ask'])
        elif mode=='book_levels':
            sides=[]
            for name in ('bids','asks'):
                prices=[]
                for level in payload[name]:
                    price,size=number(level['price']),number(level['size'])
                    if not 0<=price<=1 or size<0:raise ValueError('invalid book level')
                    if size>0:prices.append(price)
                if not prices:raise ValueError('empty book side')
                sides.append(prices)
            bid,ask=max(sides[0]),min(sides[1])
        else:raise ValueError('unsupported extraction rule')
        if not 0<=bid<=ask<=1:raise ValueError('crossed or out-of-range quote')
        return {'included':True,'valid':True,'value':float((bid+ask)/2),'reason':'observed_quote'}
    except (KeyError,TypeError,ValueError):
        return {'included':True,'valid':False,'value':None,'reason':'invalid_quote_fields'}


class Samples:
    """Bounded canonical SINGLE entity/domain; no fit, raw adapter or source QA."""
    def __init__(self,rows,contract,*,entity,clock_domain,max_rows):
        self.contract=deepcopy(contract);kinds=validate(self.contract)
        self.kernel=SampleKernel(rows,entity=entity,clock_domain=clock_domain,
            clock_field=contract['temporal']['clock'],allowed_kinds=kinds,max_rows=max_rows)
        self.keys=[r['key'] for r in self.kernel.rows]
        self.valid_prefix=[0]
        for r in self.kernel.rows:self.valid_prefix.append(self.valid_prefix[-1]+int(r['valid']))

    def feature_at(self,i):
        f=self.contract['feature'];g=self.contract['coverage'];k=self.kernel
        # This core check has no hidden grid/count choice; override count below.
        core={n:f[n] for n in ('lookback_ms','lookup_tolerance_ms','max_gap_ms')}
        core.update(minimum_observations=1,same_utc_day=f['day_boundary']=='purge')
        result=k.feature_at(i,core)
        if not result['available']:return result
        query=result['query_ms'];start=(bisect_left if f['window_edges']=='both' else bisect_right)(k.times,query,hi=i+1)
        count=(i+1-start if f['count_observations']=='all_records' else self.valid_prefix[i+1]-self.valid_prefix[start])
        result['window_observations']=count
        def missing(reason):return {**result,'available':False,'feature':None,'reason':reason}
        if count<f['minimum_observations']:return missing('insufficient_window_observations')
        if g['mode']=='explicit_backward_slots':
            # Decision-aligned slots including decision, stepping back within lookback.
            slots=range(k.times[i],query-1,-g['slot_ms']);covered=total=0
            for slot in slots:
                j=bisect_right(k.times,slot,hi=i+1)-1;total+=1
                if j>=0 and k.rows[j]['valid'] and slot-k.times[j]<=g['tolerance_ms']:covered+=1
            result.update(coverage_slots=total,covered_slots=covered)
            if covered*1000<total*g['minimum_coverage_per_mille']:return missing('insufficient_slot_coverage')
        return result

    def label_at(self,i,*,cutoff_ms):
        if type(cutoff_ms) is not int:raise ValueError('explicit integer cutoff required')
        c=self.contract;k=self.kernel
        result=k.label_at(i,c['temporal'],same_utc_day=c['feature']['day_boundary']=='purge')
        if not result['available']:return result
        if result['label_available_after_ms']>=cutoff_ms:
            return {**result,'available':False,'label':None,'reason':'label_not_mature_before_cutoff'}
        endpoint=bisect_left(self.keys,result['endpoint_key'])
        if c['label_max_gap_ms'] and k.gap_max(i,endpoint)>c['label_max_gap_ms']:
            return {**result,'available':False,'label':None,'reason':'label_gap_exceeded'}
        return result

    def materialize(self,*,cutoff_ms):
        k=self.kernel;t=self.contract['temporal']
        indices=range(len(k.rows)) if t['decision_rule']=='after_each_record' else (i for i in range(1,len(k.rows)) if k.times[i]>k.times[i-1])
        results=[]
        for i in indices:
            x=self.feature_at(i);y=self.label_at(i,cutoff_ms=cutoff_ms)
            results.append({'decision_key':k.rows[i]['key'],'feature':x,'outcome':y,
                'numerically_available':x['available'] and y['available'],'source_admitted':False})
        return results


def probe(c):
    kinds=validate(c);t=c['temporal'];h=t['horizon_ms'];lookback=c['feature']['lookback_ms']
    # Finite software examples, not sampled markets or controller-chosen scores.
    times=sorted(set([0,lookback//2,lookback,lookback+h,lookback+h+1]))
    rows=[{'key':[i,0,0],'entity':'fixture','clock_domain':'fixture','source_kind':kinds[0],
        'time_ms':ms,'valid':True,'value':.25} for i,ms in enumerate(times)]
    def kernel(rr):return Samples(rr,c,entity='fixture',clock_domain='fixture',max_rows=100)
    k=kernel(rows);i=times.index(lookback);cutoff=times[-1]+1
    x=k.feature_at(i);y=k.label_at(i,cutoff_ms=cutoff)
    prefix=kernel(rows[:i+1]).feature_at(i)
    changed=deepcopy(rows)
    for r in changed[i+1:]:r['value']=.9
    checks={'prefix_invariance':x==prefix,'future_mutation_invariance':x==kernel(changed).feature_at(i),
        'fresh_equal_zero_or_explicit_unavailability':y['label']==0 if y['available'] else y['reason'] in ('label_gap_exceeded','day_boundary'),
        'cutoff_equality_excluded':k.label_at(i,cutoff_ms=times[-1])['available'] is False,
        'exact_endpoint_without_closure_unavailable':kernel(rows[:-1]).label_at(i,cutoff_ms=cutoff)['reason']=='unbounded_tail'}
    quotes={kind:{'empty':quote(kind,{},c['quote_rules']),
        'example':quote(kind,{'best_bid':'.2','best_ask':'.4','bids':[{'price':'.2','size':'1'}],
            'asks':[{'price':'.4','size':'1'}]},c['quote_rules'])} for kind in c['quote_rules']}
    checks['explicit_quote_rules']=all(v['example']['included']==(c['quote_rules'][kind]!='exclude') for kind,v in quotes.items())
    v={'schema':'sample_contract_probe_v1','contract':c,'contract_sha256':digest(c),'checks':checks,
        'checks_passed':all(checks.values()),'fixture_sha256':digest(rows),'examples':{'feature':x,'label':y,'quotes':quotes},
        'implementation_sha256':file_hash(__file__),'kernel_sha256':file_hash(__file__.replace('sample_contract.py','event_sample_kernel.py')),
        'synthetic_only':True,'source_admitted':False,'raw_market_rows_read':0,'provider_calls':0,'fits':0,
        'limitations':'Finite single-entity tests; not source clock/identity/coverage attestation, raw parser integration, a fitted model or predictive evidence. '
            'Feature unavailable on a sparse fixture is not a scientific rejection. Slots check recorded coverage, never heartbeat/outage. '
            'Canonical clock domain must be supplied by independently audited runner. No arbitrary code or prose override.'}
    v['result_sha256']=digest(v);return v


def bound_probe(store,record,temporal):
    r=store.get(record,'probe_sample_contract');v=r['result']
    if (not v.get('checks_passed') or v['contract']!=r['arguments']['contract']
            or v['contract_sha256']!=digest(v['contract']) or v['contract']['temporal']!=temporal
            or v['implementation_sha256']!=file_hash(__file__)
            or v['kernel_sha256']!=file_hash(__file__.replace('sample_contract.py','event_sample_kernel.py'))
            or v['result_sha256']!=digest({k:x for k,x in v.items() if k not in {'result_sha256','record_id'}})):
        raise ValueError('passing exact sample/temporal contract required; no prose substitute')
    return {'record_id':record,'record_sha256':file_hash(store.root/'records'/(record+'.json')),
        'contract':v['contract'],'contract_sha256':v['contract_sha256'],
        'authority':'Sole executable sample policy. Prose/requests cannot change fields, grant waivers or source admission.',
        'source_admitted':False}
