"""Attribute observed clock differences to message kinds, without clock attestation.

Raw quote events retain immutable order. No sorting, deleting, repairing, prices,
labels or inferred receipt timestamps. See CLOCK_ORIGIN_AND_SAMPLES_2026-09-13.md.
"""
from collections import Counter, defaultdict
import json
from quote_source.reconstruct import timestamp


KINDS={'book','price_change','best_bid_ask','last_trade_price','tick_size_change'}


def clock(value):
    try:return timestamp(value)
    except ValueError:return None


def difference_bucket(value):
    if value<0:return 'negative'
    if value==0:return 'zero'
    if value<=1000:return '1..1000ms'
    if value<=60000:return '1001..60000ms'
    if value<=3600000:return '60001..3600000ms'
    if value<=86400000:return '3600001..86400000ms'
    return '>86400000ms'


class MessageClockProfile:
    def __init__(self, *, wrapper_day_start_ms, max_entities=5000):
        self.day_start=wrapper_day_start_ms;self.max_entities=max_entities
        self.records=0;self.last_wrapper=None;self.last_ordinal=0
        self.wrapper_counts=Counter();self.messages=Counter();self.by_kind=defaultdict(Counter)
        self.offsets=defaultdict(Counter);self.transitions=Counter();self.within_kind=Counter()
        self.entities={};self.earliest={};self.latest={}

    def consume(self,line,ordinal):
        if type(ordinal) is not int or ordinal<=self.last_ordinal:raise ValueError('raw ordinal repeated or regressed')
        self.last_ordinal=ordinal
        r=json.loads(line)
        if not isinstance(r,dict):raise ValueError('record object required')
        wrapper=clock(r.get('t'))
        # Scope guard only. This does NOT attest what t physically measures.
        if wrapper is None:raise ValueError('cannot enforce allowed diagnostic day without numeric wrapper')
        if not self.day_start<=wrapper<self.day_start+86400000:raise ValueError('wrapper outside allowed diagnostic day')
        self.records+=1
        if self.last_wrapper is not None:
            self.wrapper_counts[difference_bucket(wrapper-self.last_wrapper)]+=1
        self.last_wrapper=wrapper
        messages=r.get('m');messages=messages if isinstance(messages,list) else [messages]
        for mi,m in enumerate(messages):
            if not isinstance(m,dict):raise ValueError('message object required')
            rawkind=m.get('event_type')
            kind='rest_snapshot' if r.get('src')=='rest' else rawkind if rawkind in KINDS else 'other'
            self.messages[kind]+=1;t=clock(m.get('timestamp'))
            if rawkind=='price_change':
                changes=m.get('price_changes')
                if not isinstance(changes,list) or any(not isinstance(c,dict) for c in changes):raise ValueError('invalid changes')
                assets=[c.get('asset_id') for c in changes]
            else:assets=[m.get('asset_id')]
            if rawkind in ('last_trade_price','tick_size_change') and r.get('src')!='rest':continue
            for ci,asset in enumerate(assets):
                if not isinstance(asset,str) or not asset:
                    self.by_kind[kind]['unroutable_identity_entries']+=1;continue
                market=m.get('market')
                if not isinstance(market,str) or not market:raise ValueError('market identity missing')
                if asset not in self.entities:
                    if len(self.entities)>=self.max_entities:raise ValueError('entity resource ceiling')
                    self.entities[asset]={'market':market,'prior':None,'highwater':None,'by_kind':{}}
                state=self.entities[asset]
                if state['market']!=market:raise ValueError('token changed market')
                stats=self.by_kind[kind];stats['quote_events']+=1
                if t is None:
                    stats['invalid_source_timestamp']+=1;state['prior']=None;state['by_kind'][kind]=None;continue
                stats['numeric_source_timestamp']+=1
                self.earliest[kind]=min(t,self.earliest.get(kind,t));self.latest[kind]=max(t,self.latest.get(kind,t))
                self.offsets[kind][difference_bucket(wrapper-t)]+=1
                stats['source_before_wrapper_day']+=int(t<self.day_start)
                stats['source_after_wrapper_day']+=int(t>=self.day_start+86400000)
                prior=state['prior']
                if prior is not None:
                    stats['adjacent_quote_pairs']+=1
                    if t<prior[0]:
                        stats['adjacent_source_regressions']+=1;self.transitions[prior[1]+' -> '+kind]+=1
                if state['highwater'] is not None and t<state['highwater']:stats['below_source_highwater']+=1
                pk=state['by_kind'].get(kind)
                if pk is not None and t<pk:self.within_kind[kind]+=1
                state['by_kind'][kind]=t;state['prior']=(t,kind);state['highwater']=max(t,state['highwater'] or t)

    def summary(self):
        return {'schema':'message_kind_clock_diagnostic_v1','raw_records':self.records,'entities':len(self.entities),
            'wrapper_day_start_ms':self.day_start,'wrapper_adjacent_difference_counts':dict(self.wrapper_counts),
            'message_counts':dict(self.messages),'quote_event_counts_by_kind':{k:dict(v) for k,v in self.by_kind.items()},
            'wrapper_minus_source_numeric_difference':{k:dict(v) for k,v in self.offsets.items()},
            'source_regression_transition_counts':dict(self.transitions),'within_kind_source_regressions':dict(self.within_kind),
            'min_source_ms_by_kind':dict(self.earliest),'max_source_ms_by_kind':dict(self.latest),
            'clock_semantics_attested':False,'latency_measured':False,'quote_rows_deleted':0,
            'source_admitted':False,'labels_computed':False,'fits':0,'raw_prices_or_identifiers_exported':0}
