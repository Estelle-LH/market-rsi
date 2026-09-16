"""Bounded, permanently claimed two-pass replay of the concentrated Sep09 file."""
import argparse
import base64
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
TAG='pm-concentration-audit-v0.1.0'
OLD=ROOT/'artifacts/preliminary-comparison-20260913-01/2026-09-09/report.json'


def modules():
    from run_preliminary_comparison import modules as prior
    return prior()+[('concentration_audit','audit_tools/concentration_audit.py')]


def sources():
    return sorted({p for _,p in modules()}|{'audit_tools/run_concentration_audit.py',
        'audit_tools/run_preliminary_comparison.py','audit_tools/run_typed_raw_profile.py',
        'audit_tools/test_concentration_audit.py','CONCENTRATION_AUDIT_2026-09-13.md'})


def publication():
    from market_rsi import file_hash
    from data_scientist_harness.release import git
    repo=ROOT.parents[1];names=[str((ROOT/p).relative_to(repo)) for p in sources()]
    commit=git(repo,'rev-parse','HEAD').decode().strip();ref='refs/tags/'+TAG
    if git(repo,'remote','get-url','origin').decode().strip()!='https://github.com/Estelle-LH/RSIBench-Data.git':raise ValueError('wrong origin')
    if git(repo,'status','--porcelain','--',*names).strip():raise ValueError('dirty audit source')
    for path,name in zip(sources(),names):
        if hashlib.sha256(git(repo,'show',commit+':'+name)).hexdigest()!=file_hash(ROOT/path):raise ValueError('source differs')
    if git(repo,'cat-file','-t',ref).decode().strip()!='tag' or git(repo,'rev-parse',ref+'^{commit}').decode().strip()!=commit:raise ValueError('annotated version required')
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
    return (code+'SPEC='+repr(spec)+'\n__file__="/tmp/concentration_stdin.py"\n'+Path(__file__).read_text()).encode()


def remote(spec):
    import resource
    from market_rsi import digest
    from typed_raw_profile import Profile
    from concentration_audit import Detail,summarize
    from single_object_stream import stream_object
    resource.setrlimit(resource.RLIMIT_AS,(768*1024**2,768*1024**2))
    def stop(*_):raise TimeoutError('bounded audit deadline')
    signal.signal(signal.SIGALRM,stop);signal.signal(signal.SIGTERM,stop);signal.alarm(590)
    def emit(v):print(json.dumps(v,sort_keys=True,allow_nan=False),flush=True)
    start=time.monotonic();passes=[];failure=None;result=None;stage='profile'
    p=Profile(spec['contract'],spec['day_start_ms'])
    emit(dict(stage='started',pid=os.getpid(),synthetic_only=spec['synthetic_only']))
    def stream(consume):
        def callback(line,n):
            consume(line,n)
            if n%100000==0:emit(dict(stage=stage,records=n,elapsed_seconds=time.monotonic()-start))
        t=stream_object(spec['path'],advertised_bytes=spec['compressed_bytes'],max_input_bytes=spec['compressed_bytes'],
            max_decoded_bytes=2147483648,wall_seconds=570,consume=callback,decoder_memory_bytes=256*1024**2)
        passes.append(t)
        if not t['complete'] or t['compressed_sha256']!=spec['expected_compressed_sha256']:raise ValueError('source incomplete or changed')
    try:
        stream(p.consume)
        q=p.summary()
        if digest(q)!=spec['expected_quality_sha256']:raise ValueError('old profile not reproduced')
        selected=[list(p.entities)[i] for i in spec['selected_source_indices']]
        d=Detail(selected);stage='detail';stream(d.consume)
        result=summarize(p,d,spec['selected_source_indices'],spec['beta'],spec['expected_scores'])
    except BaseException as exc:failure=type(exc).__name__
    finally:signal.alarm(0)
    emit(dict(stage='terminal',report=dict(schema='concentration_replay_run_v1',complete=failure is None,
        failure_type=failure,last_stage=stage,transports=passes,audit=result,spec=spec,elapsed_seconds=time.monotonic()-start,
        peak_self_rss_kib_linux=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,provider_calls=0,fits=0,
        old_result_unchanged=True,source_admitted=False)))


def run(output,synthetic):
    import fcntl
    import uuid
    from market_rsi import load_json,file_hash,digest,fresh_json
    from run_typed_raw_profile import exchange
    if output.exists():raise ValueError('fresh output only')
    with (ROOT/'artifacts/concentration-audit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        old=load_json(OLD);old_sha=file_hash(OLD)
        if not old['complete'] or digest({k:v for k,v in old.items() if k!='report_sha256'})!=old['report_sha256']:raise ValueError('old result corrupt')
        e=old['evaluation'];rank=sorted(range(len(e['anonymous_asset_metrics'])),key=lambda i:e['anonymous_asset_metrics'][i]['moments']['sum_yy'],reverse=True)[:2]
        source_indices=[i for i,a in enumerate(e['quality']['anonymous_asset_statistics']) if a.get('numerically_available',0)>0]
        spec={k:old['spec'][k] for k in ('path','compressed_bytes','contract','day_start_ms','beta')}
        spec.update(expected_compressed_sha256=old['transport']['compressed_sha256'],expected_quality_sha256=digest(e['quality']),
            selected_source_indices=[source_indices[i] for i in rank],expected_scores=[e['anonymous_asset_metrics'][i] for i in rank],
            synthetic_only=synthetic,old_report_sha256=old_sha,selection='post-result top two baseline SSE tokens; diagnosis only',
            authority='user go: concentrated-gain audit before memory comparison')
        if synthetic:
            from test_concentration_audit import fixture
            from concentration_audit import summarize
            p,d,expected,rows=fixture();raw=b''.join((json.dumps(r)+'\n').encode() for r in rows)
            compressed=subprocess.run(['zstd','-q','-c'],input=raw,stdout=subprocess.PIPE,check=True).stdout
            spec.update(path='/__SYNTHETIC_DIRECTORY__/fixture.zst',compressed_bytes=len(compressed),expected_compressed_sha256=hashlib.sha256(compressed).hexdigest(),
                expected_quality_sha256=digest(p.summary()),day_start_ms=p.day_start,beta=-.2,selected_source_indices=[0,1],expected_scores=expected)
            expected_result=digest(summarize(p,d,[0,1],-.2,expected));body=program(spec).decode()
            code=('import tempfile,pathlib,base64,json\nwith tempfile.TemporaryDirectory(prefix="market-rsi-concentration-") as tmp:\n'
                ' p=pathlib.Path(tmp)/"fixture.zst";p.write_bytes(base64.b64decode('+repr(base64.b64encode(compressed).decode())+'))\n'
                ' exec('+repr(body)+'.replace("/__SYNTHETIC_DIRECTORY__",tmp),{"__name__":"__main__"})\n'
                'print(json.dumps({"stage":"cleanup","temporary_directory_removed":not pathlib.Path(tmp).exists()}))\n').encode()
            published=dict(synthetic_only=True,source_hashes={p:file_hash(ROOT/p) for p in sources()})
        else:
            published=publication();canary_path=ROOT/'artifacts/concentration-canary-20260913-01/canary.json';c=load_json(canary_path)
            if not c['complete'] or not c['temporary_directory_removed'] or c['publication']['source_hashes']!=published['source_hashes']:raise ValueError('same-source canary required')
            code=program(spec)
        output.mkdir(parents=True)
        claim=dict(spec=spec,publication=published,program_sha256=hashlib.sha256(code).hexdigest(),nonce=uuid.uuid4().hex)
        if not synthetic:
            claims=ROOT/'artifacts/concentration-audit-claims';claims.mkdir(exist_ok=True);fresh_json(claims/(TAG+'.json'),dict(**claim,output=str(output)))
        fresh_json(output/'claim.json',claim)
        r=exchange(code,output)
        if synthetic and (not r['complete'] or not r['temporary_directory_removed'] or digest(r['audit'])!=expected_result):raise ValueError('synthetic result differs')
        if file_hash(OLD)!=old_sha or any(file_hash(ROOT/p)!=s for p,s in published['source_hashes'].items()):raise ValueError('old result/source mutated')
        r['publication']=published;r['report_sha256']=digest(r);fresh_json(output/('canary.json' if synthetic else 'report.json'),r)
        print(json.dumps(dict(complete=r['complete'],result_sha256=r['report_sha256'],audit=r['audit'])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--remote',action='store_true');p.add_argument('--canary',action='store_true');p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.remote:remote(SPEC)
    else:run(a.output.resolve(),a.canary)
