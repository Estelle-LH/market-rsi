"""Stream existing capture locally on Linode; return QA aggregates, never rows.

This is a diagnostic audit, not model fitting or source admission. The controller
requested Aug21..Sep09. Protect the previous experiment's Aug27..Sep05 range
plus a day each side until its exact row-level exposure map is reconciled.
No exclusion is based on price movement. No final-Test claim is made.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime,timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

SAFE_DATES=('2026-08-21','2026-08-22','2026-08-23','2026-08-24','2026-08-25',
            '2026-09-07','2026-09-08','2026-09-09')
PROTECTED=('2026-08-26','2026-09-06')


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while block:=f.read(1024*1024):h.update(block)
    return h.hexdigest()


def audit_quote(path,day):
    before=path.stat();source_hash=sha(path)
    counts=Counter();missing=Counter();venues=Counter();minutes=set();groups={};min_t=max_t=None
    with gzip.open(path,'rt',newline='',encoding='utf-8-sig') as f:
        reader=csv.DictReader(f)
        required={'ts_utc','ts_ms','venue','market','outcome','bid','ask','bid_size','ask_size','mid','spread'}
        if set(reader.fieldnames or [])!=required:raise ValueError('quote schema changed')
        for ordinal,row in enumerate(reader,1):
            if ordinal>50_000_000:raise ValueError('bounded quote row count exceeded')
            counts['all_rows']+=1;venues[row['venue']]+=1
            if row['venue'].lower()!='polymarket':continue
            counts['polymarket_rows']+=1
            try:
                t=int(row['ts_ms']);dt=datetime.fromtimestamp(t/1000,timezone.utc)
                embedded=dt.strftime('%Y-%m-%d')
                # Stop before using quote fields if old experiment data appears.
                if PROTECTED[0]<=embedded<=PROTECTED[1]:raise RuntimeError('protected prior experiment timestamp encountered')
                if embedded!=day:counts['timestamp_outside_directory_day']+=1
                other=datetime.fromisoformat(row['ts_utc'].replace('Z','+00:00'))
                if other.tzinfo is None or other.utcoffset().total_seconds()!=0:counts['utc_clock_not_explicit']+=1
                elif abs(other.timestamp()*1000-t)>1:counts['clock_disagreement_over_1ms']+=1
            except (ValueError,OverflowError,OSError):counts['invalid_clock']+=1;continue
            min_t=t if min_t is None else min(min_t,t);max_t=t if max_t is None else max(max_t,t)
            minutes.add(t//60000)
            key=(row['market'],row['outcome'])
            if not all(key):counts['missing_market_or_outcome']+=1
            if key not in groups:
                if len(groups)>=100_000:raise ValueError('bounded entity count exceeded')
                groups[key]={'rows':0,'last_t':None,'last_mid':None,'equal_pairs':0,'valid_pairs':0,
                    'max_gap_ms':0,'unchanged_span_start':None,'max_observed_unchanged_span_ms':0}
            g=groups[key];g['rows']+=1;values={}
            for field in ('bid','ask','bid_size','ask_size','mid','spread'):
                try:
                    v=float(row[field])
                    if not math.isfinite(v):raise ValueError('nonfinite')
                    values[field]=v
                except (TypeError,ValueError):missing[field]+=1
            for field in ('bid','ask','mid'):
                if field in values and not 0<=values[field]<=1:counts[field+'_outside_probability_range']+=1
            for field in ('bid_size','ask_size'):
                if values.get(field,0)<0:counts[field+'_negative']+=1
            if 'bid' in values and 'ask' in values:
                if values['bid']>values['ask']:counts['crossed_book']+=1
                if 'mid' in values and abs(values['mid']-(values['bid']+values['ask'])/2)>1e-9:
                    counts['mid_not_bid_ask_average']+=1
                if 'spread' in values and abs(values['spread']-(values['ask']-values['bid']))>1e-9:
                    counts['spread_not_ask_minus_bid']+=1
            if g['last_t'] is not None:
                gap=t-g['last_t']
                if gap<0:counts['backward_entity_clock']+=1
                if gap==0:counts['same_timestamp_entity_pair']+=1
                g['max_gap_ms']=max(g['max_gap_ms'],gap)
                if 'mid' in values and g['last_mid'] is not None:
                    g['valid_pairs']+=1
                    if values['mid']==g['last_mid'] and gap>=0:
                        g['equal_pairs']+=1
                        if g['unchanged_span_start'] is None:g['unchanged_span_start']=g['last_t']
                        g['max_observed_unchanged_span_ms']=max(g['max_observed_unchanged_span_ms'],t-g['unchanged_span_start'])
                    else:g['unchanged_span_start']=None
                else:g['unchanged_span_start']=None
            g['last_t']=t;g['last_mid']=values.get('mid')
    after=path.stat()
    if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
        raise ValueError('source changed during audit')
    valid_pairs=sum(g['valid_pairs'] for g in groups.values());equal_pairs=sum(g['equal_pairs'] for g in groups.values())
    return {'date':day,'filename':path.name,'file_bytes':before.st_size,'file_sha256':source_hash,
        'counts':dict(counts),'venues':dict(venues),'missing_or_nonfinite':dict(missing),
        'probability_range_is_not_unit_proof':True,'market_outcome_pairs':len(groups),
        'utc_minutes_with_observations':len(minutes),'min_timestamp_ms':min_t,'max_timestamp_ms':max_t,
        'file_mtime_ge_max_timestamp':None if max_t is None else before.st_mtime_ns//1_000_000>=max_t,
        'valid_adjacent_mid_pairs':valid_pairs,'equal_adjacent_mid_pairs':equal_pairs,
        'equal_adjacent_mid_fraction':equal_pairs/valid_pairs if valid_pairs else None,
        'max_observed_pair_gap_ms':max((g['max_gap_ms'] for g in groups.values()),default=None),
        'max_observed_unchanged_span_ms':max((g['max_observed_unchanged_span_ms'] for g in groups.values()),default=None),
        'raw_rows_exported':0,'labels_built':0,'source_admitted':False,
        'unknown':['Gamma identity mapping','exchange versus receive clock semantics','trade size units',
            'independent sample size','quiet versus outage classification from heartbeat evidence'],
        'limitations':['Flat spans can cross gaps: not evidence of continuous unchanged prices.',
            'Timestamp-derived observed minutes are not complete exchange sessions.',
            'No future-price filtering or automatic correction.']}


def remote():
    root=Path('/opt/d10/research');results=[]
    for day in SAFE_DATES:
        path=root/day/f'topofbook_{day}.csv.gz'
        if path.is_symlink() or not path.is_file():raise ValueError('exact archived source missing')
        results.append(audit_quote(path,day))
        print(json.dumps({'completed_day':day,'polymarket_rows':results[-1]['counts'].get('polymarket_rows',0),
            'day_result':results[-1]}),file=sys.stderr,flush=True)
    return {'schema':'capture_quote_diagnostic_v1','requested_window':['2026-08-21','2026-09-09'],
        'audited_dates':SAFE_DATES,'protected_interval':PROTECTED,'results':results,
        'raw_rows_exported':0,'labels_built':0,'fits':0,'source_admitted':False,'new_test_opened':False}


def remote_day(day):
    if day not in SAFE_DATES:raise ValueError('date outside fixed unprotected audit scope')
    path=Path('/opt/d10/research')/day/f'topofbook_{day}.csv.gz'
    if path.is_symlink() or not path.is_file():raise ValueError('exact archived source missing')
    return audit_quote(path,day)


def completed_day_evidence(stderr):
    """Recover whole-day aggregates on capped exit; never certify a partial day.

    The remote stream flushes each completed day. The caller persists those
    packets after SSH returns, including its remote timeout exit. This is NOT
    crash-durable checkpointing if the local supervisor itself is killed.
    """
    if len(stderr)>1_000_000:raise ValueError('bounded progress output exceeded')
    results=[]
    for line in stderr.decode(errors='strict').splitlines():
        try:packet=json.loads(line)
        except json.JSONDecodeError:continue  # SSH diagnostics are not evidence.
        if not isinstance(packet,dict) or 'completed_day' not in packet:continue
        i=len(results)
        if i>=len(SAFE_DATES) or packet['completed_day']!=SAFE_DATES[i]:
            raise ValueError('completed-day sequence mismatch')
        result=packet.get('day_result')
        if not isinstance(result,dict):raise ValueError('completed-day aggregate missing')
        if (result.get('date')!=SAFE_DATES[i] or result.get('source_admitted') is not False
            or result.get('raw_rows_exported')!=0 or result.get('labels_built')!=0
            or packet.get('polymarket_rows')!=result.get('counts',{}).get('polymarket_rows',0)):
            raise ValueError('completed-day aggregate mismatch')
        results.append(result)
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--remote',action='store_true')
    p.add_argument('--remote-day',choices=SAFE_DATES)
    p.add_argument('--output',type=Path);a=p.parse_args()
    if a.remote and a.remote_day:raise ValueError('choose one remote scope')
    if a.remote_day:print(json.dumps(remote_day(a.remote_day),sort_keys=True));sys.exit(0)
    if a.remote:print(json.dumps(remote(),sort_keys=True));sys.exit(0)
    if not a.output or a.output.exists():raise ValueError('fresh output required')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from market_rsi import fresh_json,file_hash,digest
    local_timeout=False
    try:
        response=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','root@173.255.231.4',
            'timeout 1200s python3 - --remote'],input=Path(__file__).read_bytes(),capture_output=True,timeout=1220)
    except subprocess.TimeoutExpired as error:
        local_timeout=True
        response=subprocess.CompletedProcess(error.cmd,124,stdout=error.stdout or b'',stderr=error.stderr or b'')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    progress=completed_day_evidence(response.stderr);receipts=[]
    for day_result in progress:
        receipt=a.output.parent/('day-'+day_result['date']+'.json')
        fresh_json(receipt,{'schema':'capture_completed_day_v1','reader_sha256':file_hash(__file__),
            'result':day_result,'result_sha256':digest(day_result),'full_window_complete':False})
        receipts.append({'path':str(receipt),'sha256':file_hash(receipt)})
    if response.returncode or len(response.stdout)>1_000_000:
        fresh_json(a.output,{'status':'failed','exit_code':response.returncode,'automatic_retry':False,
            'reader_sha256':file_hash(__file__),'local_timeout':local_timeout,
            'completed_day_receipts':receipts,'full_window_complete':False,
            'stderr_tail':response.stderr.decode(errors='replace')[-1800:],'source_admitted':False})
        raise RuntimeError('quote audit failed; preserved receipt, no retry')
    value=json.loads(response.stdout);value.update(reader_sha256=file_hash(__file__),
        transport_response_bytes=len(response.stdout)+len(response.stderr),completed_day_receipts=receipts,
        progress=[{'completed_day':r['date'],'polymarket_rows':r['counts'].get('polymarket_rows',0)} for r in progress])
    if value['results']!=progress or len(progress)!=len(SAFE_DATES):
        raise ValueError('terminal report and completed-day receipts disagree')
    value['result_sha256']=digest(value);fresh_json(a.output,value)
    print({'days':len(value['results']),'polymarket_rows':sum(r['counts'].get('polymarket_rows',0) for r in value['results']),
        'source_admitted':False,'result_sha256':value['result_sha256']})
