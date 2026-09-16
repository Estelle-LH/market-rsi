"""Publish/canary-gated initial Train materialization. No Dev/Test entry point."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'audit_tools')]
TAG = 'pm-memory-data-v0.1.0'
FILES = [('2026-08-26',38540746),('2026-08-27',42874343),('2026-08-28',32048483)]
REMOTE_ROOT = '/opt/d10/derived/market-rsi-memory-data-20260913-01'


def modules():
    from run_typed_raw_profile import MODULES
    return MODULES + [('memory_materialize','memory_pilot/materialize.py')]


def sources():
    return sorted({p for _,p in modules()} | {'memory_pilot/run_materialize.py',
        'memory_pilot/test_materialize.py','audit_tools/run_typed_raw_profile.py',
        'MEMORY_PILOT_2026-09-13.md'})


def publication():
    from market_rsi import file_hash
    from data_scientist_harness.release import git
    repo=ROOT.parents[1]; commit=git(repo,'rev-parse',TAG+'^{commit}').decode().strip()
    names=[str((ROOT/p).relative_to(repo)) for p in sources()]
    if git(repo,'remote','get-url','origin').decode().strip()!='https://github.com/Estelle-LH/RSIBench-Data.git':
        raise ValueError('wrong origin')
    if git(repo,'status','--porcelain','--',*names).strip(): raise ValueError('dirty data source')
    for p,n in zip(sources(),names):
        if hashlib.sha256(git(repo,'show',commit+':'+n)).hexdigest()!=file_hash(ROOT/p):
            raise ValueError('source differs from frozen version')
    ref='refs/tags/'+TAG
    if git(repo,'cat-file','-t',ref).decode().strip()!='tag': raise ValueError('annotated tag required')
    tag=git(repo,'rev-parse',ref).decode().strip()
    refs={v.split()[1]:v.split()[0] for v in git(repo,'ls-remote','origin',ref,ref+'^{}').decode().splitlines()}
    if refs!={ref:tag,ref+'^{}':commit}:raise ValueError('version not published')
    return dict(commit=commit,tag=TAG,tag_object=tag,source_hashes={p:file_hash(ROOT/p) for p in sources()})


def program(spec):
    code='import types,sys\n'
    for name in ('quote_source','data_scientist_harness'):
        code+='m=types.ModuleType('+repr(name)+');m.__path__=[];sys.modules[m.__name__]=m\n'
    for name,path in modules():
        code+='m=types.ModuleType('+repr(name)+');m.__file__='+repr(path)+';sys.modules[m.__name__]=m\n'
        code+='exec('+repr((ROOT/path).read_text())+',m.__dict__)\n'
    return (code+'SPEC='+repr(spec)+'\n__file__="/tmp/memory_data_stdin.py"\n'+Path(__file__).read_text()).encode()


def remote(spec):
    import resource
    from market_rsi import fresh_json
    from memory_materialize import CacheProfile,write_cache
    from single_object_stream import stream_object
    resource.setrlimit(resource.RLIMIT_AS,(768*1024**2,768*1024**2))
    def stop(*_): raise TimeoutError('bounded materialization deadline')
    signal.signal(signal.SIGALRM,stop);signal.signal(signal.SIGTERM,stop);signal.alarm(590)
    def emit(v): print(json.dumps(v,sort_keys=True,allow_nan=False),flush=True)
    start=time.monotonic();failure=None;t=h=None;p=CacheProfile(spec['contract'],spec['day_start_ms'])
    output=Path(spec['output']);output.parent.mkdir(parents=True,exist_ok=True)
    # Permanent claim is exclusive even when materialization fails before cache creation.
    fresh_json(output.with_suffix('.claim.json'),dict(spec=spec,pid=os.getpid()))
    emit(dict(stage='started',pid=os.getpid(),date=spec['date'],synthetic_only=spec['synthetic_only']))
    def consume(line,n):
        p.consume(line,n)
        if n%100000==0:emit(dict(stage='decode',records=n,elapsed_seconds=time.monotonic()-start))
    try:
        t=stream_object(spec['path'],advertised_bytes=spec['compressed_bytes'],max_input_bytes=spec['compressed_bytes'],
            max_decoded_bytes=2147483648,wall_seconds=570,consume=consume,decoder_memory_bytes=256*1024**2)
        if not t['complete']: raise ValueError('incomplete source')
        h=write_cache(p,output,lambda a,b:emit(dict(stage='samples',entities_done=a,entities_total=b)))
    except BaseException as exc: failure=dict(type=type(exc).__name__,message=str(exc)[:500])
    finally:signal.alarm(0)
    emit(dict(stage='terminal',report=dict(schema='memory_materialize_run_v1',complete=failure is None,
        failure=failure,transport=t,header=h,spec=spec,elapsed_seconds=time.monotonic()-start,
        fits=0,provider_calls=0,raw_rows_exported=0,new_dev_test_opened=False)))


def canary(output):
    from test_typed_raw_profile import message,T,contract
    from memory_pilot.materialize import CacheProfile,write_cache
    from market_rsi import digest,fresh_json,file_hash
    from run_typed_raw_profile import exchange
    import tempfile
    rows=[message(T+i*10000,bid=str(.2+.01*(i%3)),ask=str(.6+.01*(i%3))) for i in range(26)]
    p=CacheProfile(contract(),T)
    for i,r in enumerate(rows,1):p.consume(json.dumps(r).encode(),i)
    with tempfile.TemporaryDirectory(prefix='memory-data-fixture-') as tmp:
        expected=digest(write_cache(p,Path(tmp)/'cache'))
    raw=b''.join((json.dumps(r)+'\n').encode() for r in rows)
    compressed=subprocess.run(['zstd','-q','-c'],input=raw,stdout=subprocess.PIPE,check=True).stdout
    spec=dict(contract=contract(),day_start_ms=T,date='synthetic',path='/__TMP__/raw.zst',
        output='/__TMP__/cache',compressed_bytes=len(compressed),synthetic_only=True)
    body=program(spec).decode()
    code=('import tempfile,pathlib,base64,json\nwith tempfile.TemporaryDirectory(prefix="memory-data-canary-") as tmp:\n'
        ' (pathlib.Path(tmp)/"raw.zst").write_bytes(base64.b64decode('+repr(base64.b64encode(compressed).decode())+'))\n'
        ' exec('+repr(body)+'.replace("/__TMP__",tmp),{"__name__":"__main__"})\n'
        'print(json.dumps({"stage":"cleanup","temporary_directory_removed":not pathlib.Path(tmp).exists()}))\n').encode()
    output.mkdir(parents=True);r=exchange(code,output)
    if not r['complete'] or not r['temporary_directory_removed'] or digest(r['header'])!=expected:
        raise ValueError('synthetic remote cache differs')
    r['source_hashes']={p:file_hash(ROOT/p) for p in sources()};fresh_json(output/'canary.json',r)
    print(json.dumps(dict(canary_passed=True,synthetic_rows=r['header']['shape'][0])),flush=True)


def run(output,canary_path):
    import fcntl
    from market_rsi import file_hash,fresh_json,load_json,digest
    from run_typed_raw_profile import exchange
    from paid_budget import PaidBudget
    with (ROOT/'artifacts/memory-materialize.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if output.exists():raise ValueError('fresh experiment ID required')
        pub=publication();c=load_json(canary_path)
        if not c['complete'] or not c['temporary_directory_removed'] or c['source_hashes']!=pub['source_hashes']:
            raise ValueError('same-source remote canary required')
        contract=load_json(ROOT/'artifacts/typed-raw-profile-20260913-01/report.json')['spec']['contract']
        bpath=ROOT/'artifacts/kalshi-research-glm53-20260907-01/budget';before=PaidBudget(bpath).snapshot()
        output.mkdir(parents=True)
        fresh_json(output/'claim.json',dict(publication=pub,files=FILES,remote_root=REMOTE_ROOT,
            canary_sha256=file_hash(canary_path),budget_snapshot_sha256=digest(before),
            scope='initial Train only; later Dev/Test price contents remain closed'))
        reports=[]
        for date,size in FILES:
            d=output/date;d.mkdir()
            spec=dict(date=date,path='/opt/d10/raw/data/polymarket/polymarket-'+date.replace('-','')+'T12.jsonl.zst',
                output=REMOTE_ROOT+'/'+date,compressed_bytes=size,contract=contract,
                day_start_ms=int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp()*1000),
                synthetic_only=False,publication_commit=pub['commit'])
            r=exchange(program(spec),d);fresh_json(d/'report.json',r)
            if not r['complete']:raise ValueError('source failed; do not replace date or retry automatically')
            target=d/'rows.f64'
            if target.exists():raise ValueError('derived cache overwrite denied')
            proc=subprocess.run(['scp','-o','BatchMode=yes','-o','ConnectTimeout=10',
                'root@173.255.231.4:'+spec['output']+'/rows.f64',str(target)],capture_output=True,timeout=180)
            receipt=dict(exit_code=proc.returncode,process_reaped=True,derived_cache_only=True)
            fresh_json(d/'transfer.json',receipt)
            if proc.returncode or target.stat().st_size!=r['header']['bytes'] or file_hash(target)!=r['header']['sha256']:
                raise ValueError('derived transfer/hash failed; preserve partial artifact')
            fresh_json(d/'header.json',r['header']);reports.append(dict(date=date,rows=r['header']['shape'][0],
                cache_sha256=r['header']['sha256'],source_sha256=r['transport']['compressed_sha256']))
            print(json.dumps(dict(stage='file_complete',date=date,rows=r['header']['shape'][0])),flush=True)
        if PaidBudget(bpath).snapshot()!=before:raise ValueError('budget changed during CPU-only work')
        fresh_json(output/'complete.json',dict(complete=True,files=reports,provider_calls=0,fits=0,publication=pub))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--remote',action='store_true');p.add_argument('--canary',action='store_true')
    p.add_argument('--output',type=Path);p.add_argument('--canary-receipt',type=Path);a=p.parse_args()
    if a.remote:remote(SPEC)
    elif a.canary:canary(a.output.resolve())
    else:run(a.output.resolve(),a.canary_receipt.resolve())
