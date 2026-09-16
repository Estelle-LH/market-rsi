"""Post-result diagnosis of two preselected tokens; never refit or filter scores."""
from collections import Counter
import hashlib
import json
import math

from market_rsi import digest
from preliminary_comparison import moments,score
from typed_raw_profile import canonical_kernel,sample_at,DAY
from data_scientist_harness.sample_contract import quote as declared_quote


def distribution(values):
    values=sorted(values)
    if not values:return dict(n=0)
    return dict(n=len(values),minimum=values[0],median=values[(len(values)-1)//2],
                p90=values[int((len(values)-1)*.9)],maximum=values[-1])


def number(v):
    if v is None:return None
    try:a=float(v)
    except (ValueError,TypeError):return None
    return a if math.isfinite(a) else None


class Detail:
    def __init__(self,assets):
        if len(assets)!=2 or len(set(assets))!=2:raise ValueError('two distinct bound tokens required')
        self.assets=assets;self.quotes={a:[] for a in assets};self.events={a:Counter() for a in assets}
        self.trade_prices={a:[] for a in assets};self.books={a:Counter() for a in assets}
        self.seen=set();self.duplicates=0;self.messages=0;self.pairs=[]

    def consume(self,line,ordinal):
        r=json.loads(line);ms=r['m'] if isinstance(r['m'],list) else [r['m']]
        for mi,m in enumerate(ms):
            kind=m.get('event_type');asset=m.get('asset_id')
            if kind=='price_change' and r.get('src')!='rest':
                selected=[(ci,c) for ci,c in enumerate(m['price_changes']) if c.get('asset_id') in self.quotes]
                if not selected:continue
                fingerprint=digest(m);self.messages+=1;self.duplicates+=fingerprint in self.seen;self.seen.add(fingerprint)
                paired={}
                for ci,c in selected:
                    a=c['asset_id'];bid=number(c.get('best_bid'));ask=number(c.get('best_ask'))
                    if bid is None or ask is None or not 0<=bid<=ask<=1:raise ValueError('target quotes changed validity')
                    # The frozen kernel averages decimal source fields before
                    # casting to float; recomputing in binary would change bytes.
                    mid=declared_quote('price_change',c,{'price_change':'direct_bbo'})
                    if not mid['valid']:raise ValueError('target parser rejected quote')
                    q=dict(key=(0,ordinal,mi,ci),time_ms=int(m['timestamp']),wrapper_ms=int(r['t']),bid=bid,ask=ask,
                           mid=mid['value'],spread=ask-bid,size=number(c.get('size')),side=c.get('side'))
                    self.quotes[a].append(q);paired[a]=q;self.events[a]['price_change']+=1
                if len(paired)==2:
                    x,y=(paired[a] for a in self.assets)
                    self.pairs.append(dict(same_time=x['time_ms']==y['time_ms'],
                        complement_error=max(abs(x['bid']+y['ask']-1),abs(x['ask']+y['bid']-1)),
                        mid_sum_error=abs(x['mid']+y['mid']-1)))
            elif asset in self.quotes:
                self.events[asset][str(kind)]+=1
                if kind=='last_trade_price':
                    v=number(m.get('price'))
                    if v is not None:self.trade_prices[asset].append(v)
                if kind in ('book','rest_snapshot'):
                    for side in ('bids','asks'):
                        if isinstance(m.get(side),list):
                            positive=sum(number(v.get('size')) is not None and number(v['size'])>0 for v in m[side])
                            self.books[asset][side+'_snapshots']+=1
                            self.books[asset][side+'_zero_positive_levels']+=positive==0


def summarize(profile,detail,indices,beta,expected):
    entries=list(profile.entities.items());results=[]
    markets=[]
    for selected,(index,old) in enumerate(zip(indices,expected)):
        asset,s=entries[index];markets.append(s.market);quotes=detail.quotes[asset]
        if len(quotes)!=len(s.t):raise ValueError('two-pass target count differs')
        mapping={q['key']:q for q in quotes}
        if len(mapping)!=len(quotes):raise ValueError('target immutable key duplicated')
        for i,q in enumerate(quotes):
            if q['time_ms']!=s.t[i] or q['mid']!=s.v[i] or q['key']!=(0,s.ordinal[i],s.message[i],s.inner[i]):
                raise ValueError('two-pass target content differs')
        k=canonical_kernel(s.rows(),profile.contract);prefix=[0]
        for valid in s.valid:prefix.append(prefix[-1]+int(valid))
        x=[];y=[];buckets={};scored_deltas=[]
        for i in range(1,len(s.t)):
            if s.t[i]==s.t[i-1]:continue
            f,l=sample_at(k,i,profile.contract,prefix,profile.day_start+DAY)
            if not(f['available'] and l['available']):continue
            a,b=f['feature'],l['label'];x.append(a);y.append(b)
            start=mapping[tuple(f['decision_key'])];end=mapping[tuple(l['endpoint_key'])]
            wide=max(start['spread'],end['spread'])>.10
            key='either_endpoint_spread_gt_10c' if wide else 'both_endpoint_spreads_le_10c'
            row=buckets.setdefault(key,dict(n=0,baseline_sse=0.,candidate_sse=0.))
            row['n']+=1;row['baseline_sse']+=b*b;row['candidate_sse']+=(b-beta*a)**2
            scored_deltas.append((f['decision_ms'],a,b))
        actual=score(x,y,beta,with_rank=False)
        if any(not math.isclose(v,old['moments'][key],rel_tol=1e-9,abs_tol=1e-10) for key,v in actual['moments'].items()):
            raise ValueError('old selected score not reproduced')
        jumps=[];changed=[];cancel_jumps=one_side_jumps=roundtrips=0
        for i,q in enumerate(quotes):
            if not changed or q['mid']!=changed[-1]['mid']:changed.append(q)
            if i and abs(q['mid']-quotes[i-1]['mid'])>=.10:
                jumps.append(abs(q['mid']-quotes[i-1]['mid']));cancel_jumps+=q['size']==0
                one_side_jumps+=(q['bid']==quotes[i-1]['bid'])!=(q['ask']==quotes[i-1]['ask'])
        for a,b,c in zip(changed,changed[1:],changed[2:]):
            roundtrips+=abs(a['mid']-b['mid'])>=.10 and abs(a['mid']-c['mid'])<1e-12 and c['time_ms']-a['time_ms']<=60000
        results.append(dict(source_entity_index=index,token_sha256=hashlib.sha256(asset.encode()).hexdigest(),
            market_sha256=hashlib.sha256(s.market.encode()).hexdigest(),old_score_reproduced=True,observations=len(quotes),
            event_kind_counts=dict(detail.events[asset]),book_counts=dict(detail.books[asset]),
            bid_distribution=distribution([q['bid'] for q in quotes]),ask_distribution=distribution([q['ask'] for q in quotes]),
            midpoint_distribution=distribution([q['mid'] for q in quotes]),spread_distribution=distribution([q['spread'] for q in quotes]),
            wrapper_minus_source_ms=distribution([q['wrapper_ms']-q['time_ms'] for q in quotes]),
            boundary_bid_zero=sum(q['bid']==0 for q in quotes),boundary_ask_one=sum(q['ask']==1 for q in quotes),
            spread_gt_10c=sum(q['spread']>.10 for q in quotes),zero_size_price_updates=sum(q['size']==0 for q in quotes),
            observed_trade_prices=distribution(detail.trade_prices[asset]),large_mid_jump_count=len(jumps),
            large_mid_jumps=distribution(jumps),large_jumps_with_zero_size_update=cancel_jumps,
            large_jumps_with_only_one_bbo_side_moving=one_side_jumps,rapid_exact_mid_roundtrips=roundtrips,
            diagnostic_score_buckets=buckets,scored_rows=len(x)))
    if not detail.pairs:raise ValueError('no same-message target pairs to inspect')
    return dict(schema='concentrated_token_audit_v1',tokens=results,same_market=markets[0]==markets[1],
        selected_price_change_messages=detail.messages,identical_full_message_repeats=detail.duplicates,
        messages_containing_both_tokens=len(detail.pairs),same_time_pairs=sum(p['same_time'] for p in detail.pairs),
        complementary_bbo_pairs=sum(p['complement_error']<1e-10 for p in detail.pairs),
        max_complement_error=max(p['complement_error'] for p in detail.pairs),
        no_new_fit=True,no_exclusions_changed=True,no_raw_rows_or_identifiers_exported=True,
        capture_completeness_proven=False,trade_execution_proven=False)
