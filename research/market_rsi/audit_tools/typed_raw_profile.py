"""Bounded raw-message adapter for the already selected rev6 sample policy.

One object, one recorded UTC day. No training, source admission, repair, raw
export or silent policy choices. Canonical rules are regression-tested against
DSH1.5.0 Samples; its frozen files remain unchanged.
"""
from array import array
from bisect import bisect_left
from collections import Counter
import json
import math

from market_rsi import digest
from quote_source.reconstruct import timestamp
from data_scientist_harness.event_sample_kernel import SampleKernel
from data_scientist_harness.sample_contract import quote

CONTRACT_SHA='25c420d2e5e79f6e1e5eea850127cbecb7d1c2b1471614d81996640b5b6808bb'
DAY=86400000


class Series:
    def __init__(self,market):
        self.market=market
        self.t=array('q');self.v=array('d');self.valid=bytearray()
        self.ordinal=array('Q');self.message=array('I');self.inner=array('I')
        self.counts=Counter();self.gaps=Counter()

    def add(self,t,value,valid,key,present):
        if self.t:
            gap=t-self.t[-1]
            bucket=('negative' if gap<0 else '0' if gap==0 else '1..1000' if gap<=1000
                else '1001..10000' if gap<=10000 else '10001..60000' if gap<=60000 else '>60000')
            self.gaps[bucket]+=1
        self.t.append(t);self.v.append(value if valid else 0.0);self.valid.append(valid)
        self.ordinal.append(key[0]);self.message.append(key[1]);self.inner.append(key[2])
        self.counts['observations']+=1;self.counts['both_quote_fields_present']+=present
        self.counts['valid_quotes']+=valid;self.counts['invalid_quotes']+=not valid

    def rows(self):
        # Internal identities intentionally replaced only AFTER checking routing.
        return [{'key':[0,self.ordinal[i],self.message[i],self.inner[i]],'entity':'one-series',
            'clock_domain':'declared-source-ms','source_kind':'price_change','time_ms':t,
            'value':self.v[i] if self.valid[i] else None,'valid':bool(self.valid[i])}
            for i,t in enumerate(self.t)]


def canonical_kernel(rows,contract):
    if digest(contract)!=CONTRACT_SHA:raise ValueError('exact controller-selected contract required')
    return SampleKernel(rows,entity='one-series',clock_domain='declared-source-ms',
        clock_field=contract['temporal']['clock'],allowed_kinds=['price_change'],max_rows=200000)


def sample_at(kernel,i,contract,valid_prefix,cutoff_ms):
    """Exact rev6 subset; parity tests cover the published general Samples class."""
    f=contract['feature']
    x=kernel.feature_at(i,{'lookback_ms':f['lookback_ms'],'lookup_tolerance_ms':f['lookup_tolerance_ms'],
        'minimum_observations':1,'max_gap_ms':f['max_gap_ms'],'same_utc_day':True})
    if x['available']:
        left=bisect_left(kernel.times,x['query_ms'],hi=i+1)
        count=valid_prefix[i+1]-valid_prefix[left];x['window_observations']=count
        if count<f['minimum_observations']:
            x.update(available=False,feature=None,reason='insufficient_window_observations')
    y=kernel.label_at(i,contract['temporal'],same_utc_day=True)
    if y['available'] and y['label_available_after_ms']>=cutoff_ms:
        y.update(available=False,label=None,reason='label_not_mature_before_cutoff')
    return x,y


class Profile:
    def __init__(self,contract,day_start,*,max_entities=5000,max_total_rows=4000000,max_entity_rows=200000):
        if digest(contract)!=CONTRACT_SHA:raise ValueError('contract changed; new review required')
        if type(day_start) is not int or day_start%DAY:raise ValueError('explicit UTC midnight required')
        self.contract=contract;self.day_start=day_start
        self.max_entities=max_entities;self.max_total_rows=max_total_rows;self.max_entity_rows=max_entity_rows
        self.entities={};self.counts=Counter();self.last_ordinal=0

    def consume(self,line,ordinal):
        if type(ordinal) is not int or ordinal<=self.last_ordinal:raise ValueError('raw order invalid')
        self.last_ordinal=ordinal;r=json.loads(line)
        if not isinstance(r,dict):raise ValueError('raw object required')
        wrapper=timestamp(r.get('t'))
        if not self.day_start<=wrapper<self.day_start+DAY:raise ValueError('wrapper outside allowed day')
        self.counts['raw_records']+=1
        messages=r.get('m');messages=messages if isinstance(messages,list) else [messages]
        for mi,m in enumerate(messages):
            if not isinstance(m,dict):raise ValueError('message object required')
            if r.get('src')=='rest' or m.get('event_type')!='price_change':
                self.counts['excluded_kind_messages']+=1;continue
            t=timestamp(m.get('timestamp'))
            if not self.day_start<=t<self.day_start+DAY:
                raise ValueError('selected source timestamp outside declared day; no silent filtering')
            changes=m.get('price_changes');market=m.get('market')
            if not isinstance(changes,list) or not isinstance(market,str) or not market:
                raise ValueError('changes or market identity missing')
            self.counts['price_change_messages']+=1
            for ci,c in enumerate(changes):
                if not isinstance(c,dict):raise ValueError('change object required')
                asset=c.get('asset_id')
                if not isinstance(asset,str) or not asset:raise ValueError('asset identity missing')
                if asset not in self.entities:
                    if len(self.entities)>=self.max_entities:raise ValueError('entity resource limit')
                    self.entities[asset]=Series(market)
                s=self.entities[asset]
                if s.market!=market:raise ValueError('asset market identity discontinuity')
                if len(s.t)>=self.max_entity_rows or self.counts['selected_observations']>=self.max_total_rows:
                    raise ValueError('row resource limit; no silent truncation')
                q=quote('price_change',c,self.contract['quote_rules'])
                s.add(t,q['value'],q['valid'],(ordinal,mi,ci),'best_bid' in c and 'best_ask' in c)
                self.counts['selected_observations']+=1

    def summary(self,progress=lambda *_:None):
        counts=Counter(self.counts);fx=Counter();fy=Counter();joint=Counter();gaps=Counter();spans=Counter()
        per_asset=[];sxx=sxy=syy=sx=sy=0.0
        for number,s in enumerate(self.entities.values()):
            gaps.update(s.gaps);counts.update(s.counts)
            if s.gaps['negative']:
                counts['rejected_segments']+=1;counts['observations_in_rejected_segments']+=len(s.t)
                per_asset.append({**dict(s.counts),'segment_rejected':True,'source_regressions':s.gaps['negative']})
                continue
            rows=s.rows();k=canonical_kernel(rows,self.contract);del rows
            prefix=[0]
            for ok in s.valid:prefix.append(prefix[-1]+int(ok))
            eligible=scored=zero=0;asset_fx=Counter();asset_fy=Counter()
            for i in range(1,len(s.t)):
                if s.t[i]==s.t[i-1]:continue
                eligible+=1;x,y=sample_at(k,i,self.contract,prefix,self.day_start+DAY)
                asset_fx[x['reason']]+=1;asset_fy[y['reason']]+=1
                if not (x['available'] and y['available']):
                    joint[x['reason']+' / '+y['reason']]+=1;continue
                scored+=1;a,b=x['feature'],y['label'];zero+=b==0
                sx+=a;sy+=b;sxx+=a*a;sxy+=a*b;syy+=b*b
                span=y['actual_span_ms'];key=('1..5999' if span<6000 else '6000..19999'
                    if span<20000 else '20000..59999' if span<60000 else '60000')
                spans[key]+=1
            counts.update(eligible_decisions=eligible,numerically_available=scored,fresh_equal_zero=zero)
            fx.update(asset_fx);fy.update(asset_fy)
            per_asset.append({**dict(s.counts),'first_source_ms':s.t[0],'last_source_ms':s.t[-1],
                'eligible_decisions':eligible,'numerically_available':scored,'fresh_equal_zero':zero,
                'unbounded_tail':asset_fy['unbounded_tail'],'segment_rejected':False})
            if number%250==0:progress(number+1,len(self.entities))
        n=counts['numerically_available']
        if counts['observations']!=counts['selected_observations'] or sum(spans.values())!=n:
            raise ValueError('observation/sample accounting mismatch')
        return {'schema':'typed_raw_sample_profile_v1','counts':dict(counts),'entities':len(self.entities),
            'canonical_segment':'entire selected-object source-day series of one asset; reject on any within-series clock regression',
            'cutoff_ms':self.day_start+DAY,'cutoff_scope':'sole selected UTC-day end; equivalent to typed day purge; not a Train/Check split or admission',
            'feature_reason_counts':dict(fx),'label_reason_counts':dict(fy),'unavailable_reason_pairs':dict(joint),
            'observed_gap_ms_counts':dict(gaps),'paired_label_span_ms_counts':dict(spans),
            'anonymous_asset_statistics':per_asset,
            'target_rms_price_bps':10000*math.sqrt(syy/n) if n else None,
            'paired_moments':{'n':n,'sum_x':sx,'sum_y':sy,'sum_xx':sxx,'sum_xy':sxy,'sum_yy':syy},
            'source_admitted':False,'fits':0,'market_performance_claim':False,
            'original_capture_attested':False,'quiet_vs_outage_attested':False,
            'raw_identifiers_or_prices_exported':False,'training_cache_created':False}
