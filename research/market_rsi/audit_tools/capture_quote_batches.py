"""Controller-requested QA, two low-priority readers, durable completed-day files.

Original immutable capture only. This does not activate a model tool or approve
the controller's outage/unit claims, Train dates, target or source admission.
Each day is attempted once. A fresh batch ID is mandatory; no automatic retry.
No more than 1200 seconds per batch and 600 seconds per remote reader. A stopped
local supervisor can leave remote readers alive until their own bounded timeout.
Completed local day receipts are fsynced as each reader returns, not at batch end.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_rsi import digest,file_hash,fresh_json,load_json
from capture_quote_audit import SAFE_DATES,PROTECTED

BATCH_SECONDS=1200
DAY_SECONDS=600
WORKERS=2


def durable_json(path,value):
    fresh_json(path,value)
    with path.open('rb') as stream:os.fsync(stream.fileno())
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def selected_dates(dates):
    if not dates or len(set(dates))!=len(dates) or any(d not in SAFE_DATES for d in dates):
        raise ValueError('unique dates within existing unprotected scope required')
    return tuple(sorted(dates))


def audit_one(day,source,deadline,run=subprocess.run,clock=time.monotonic):
    if day not in SAFE_DATES:raise ValueError('protected or unapproved date')
    cap=min(DAY_SECONDS,int(deadline-clock())-25)
    base={'date':day,'source_reader_sha256':hashlib.sha256(source).hexdigest(),
        'source_admitted':False,'labels_built':0,'fits':0,'raw_rows_exported':0,'automatic_retry':False}
    if cap<1:return {**base,'status':'not_started','reason':'batch wall cap'}
    command=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','root@173.255.231.4',
        f'nice -n 10 timeout {cap}s python3 - --remote-day {day}']
    started=clock()
    try:
        response=run(command,input=source,capture_output=True,timeout=cap+15)
    except subprocess.TimeoutExpired:
        return {**base,'status':'failed','failure':'local_transport_timeout',
            'remote_timeout_seconds':cap,'remote_exit_unverified':True,'elapsed_seconds':clock()-started}
    base.update(exit_code=response.returncode,elapsed_seconds=clock()-started,remote_timeout_seconds=cap,
        response_bytes=len(response.stdout)+len(response.stderr),transport_finished=True)
    if response.returncode or len(response.stdout)>1_000_000:
        return {**base,'status':'failed','failure':'remote_exit_or_response_bound',
            'stderr_tail':response.stderr.decode(errors='replace')[-1000:]}
    try:
        value=json.loads(response.stdout)
        if (value.get('date')!=day or value.get('source_admitted') is not False
            or value.get('raw_rows_exported')!=0 or value.get('labels_built')!=0):
            raise ValueError('scope mismatch')
    except (ValueError,TypeError,AttributeError):
        return {**base,'status':'failed','failure':'invalid_day_receipt'}
    return {**base,'status':'complete_day','result':value,'result_sha256':digest(value)}


def run_batch(output,controller,dates):
    output=output.resolve();controller=controller.resolve();dates=selected_dates(dates)
    if output.exists():raise ValueError('fresh output directory required')
    assessment=load_json(controller/'session/assessment.json')
    proposal=load_json(controller/'records/0013.json')
    if (assessment.get('valid') is not True or assessment.get('process_reaped') is not True
        or load_json(controller/'submitted-decision.json').get('action')!='defer'
        or proposal.get('status')!='ok' or proposal.get('tool')!='request_capability'
        or proposal['arguments'].get('name')!='d10_polymarket_topofbook_schema_audit_reader'):
        raise ValueError('exact terminated controller audit proposal required')
    output.parent.mkdir(parents=True,exist_ok=True)
    with (output.parent/'capture-quote-batches.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        output.mkdir()
        reader=Path(__file__).with_name('capture_quote_audit.py');source=reader.read_bytes()
        claim={'schema':'capture_quote_batch_claim_v1','pid':os.getpid(),'claimed_unix_ns':time.time_ns(),
            'dates':dates,'protected_interval':PROTECTED,'reader_sha256':hashlib.sha256(source).hexdigest(),
            'supervisor_sha256':file_hash(__file__),'controller_proposal_sha256':file_hash(controller/'records/0013.json'),
            'controller_decision_sha256':file_hash(controller/'submitted-decision.json'),
            'max_workers':WORKERS,'batch_seconds':BATCH_SECONDS,'max_remote_seconds':DAY_SECONDS,
            'nice_priority':10,'source_admitted':False,'source_scope':'existing topofbook CSV only',
            'not_implemented':['historical Gamma identity','trade size units','raw-message replay',
                'quiet/outage classification','causality proof','independent sample size'],
            'controller_claims_not_accepted':['file absence implies outage','probabilities described as cents',
                'mtime and matching serialized timestamps prove event/receipt semantics']}
        durable_json(output/'claim.json',claim)
        started=time.monotonic();deadline=started+BATCH_SECONDS;records=[]
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            work={pool.submit(audit_one,day,source,deadline):day for day in dates}
            for future in as_completed(work):
                day=work[future]
                try:value=future.result()
                except Exception as error:
                    value={'date':day,'status':'failed','failure':type(error).__name__,
                        'source_admitted':False,'automatic_retry':False}
                path=output/('day-'+day+'.json');durable_json(path,value)
                records.append({'date':day,'status':value['status'],'path':str(path),'sha256':file_hash(path)})
                print(json.dumps({'completed_day_receipt':day,'status':value['status']}),flush=True)
        report={'schema':'capture_quote_batch_v1','claim_sha256':file_hash(output/'claim.json'),
            'records':sorted(records,key=lambda r:r['date']),'elapsed_seconds':time.monotonic()-started,
            'all_requested_days_complete':all(r['status']=='complete_day' for r in records),
            'source_admitted':False,'fits':0,'new_test_opened':False,'raw_rows_exported':0,
            'automatic_retry':False,'local_reader_pool_reaped':True}
        report['result_sha256']=digest(report);durable_json(output/'report.json',report)
        return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--controller-workspace',type=Path,required=True)
    p.add_argument('--dates',nargs='+',default=SAFE_DATES,choices=SAFE_DATES)
    a=p.parse_args();r=run_batch(a.output,a.controller_workspace,a.dates)
    print(json.dumps({k:v for k,v in r.items() if k!='records'}))
