"""Fresh bounded clock-origin diagnosis on one pinned copy; not a score retry."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
TAG='pm-message-clock-origin-v0.1.0'
PRIOR=ROOT/'artifacts/single-object-source-audit-20260913-01/report.json'
PRIOR_SHA='cce9daa54943deb190bfc4ef4386cafa3e2c630ef31c5577d3561885312d2902'


def module(name,path):
    return 'm=types.ModuleType('+repr(name)+');sys.modules[m.__name__]=m\nexec('+repr(path.read_text())+',m.__dict__)\n'


def program(spec):
    code='import sys,types\np=types.ModuleType("quote_source");p.__path__=[];sys.modules[p.__name__]=p\n'
    for name,path in [('quote_source.reconstruct',ROOT/'quote_source/reconstruct.py'),
        ('message_clock_origin',ROOT/'audit_tools/message_clock_origin.py'),('single_object_stream',ROOT/'audit_tools/single_object_stream.py')]:
        code+=module(name,path)
    return (code+'SPEC='+repr(spec)+'\n__file__="/tmp/message_clock_origin_stdin.py"\n'+Path(__file__).read_text()).encode()


def remote(spec):
    import resource
    from message_clock_origin import MessageClockProfile
    from single_object_stream import stream_object
    resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
    def stop(*_):raise TimeoutError('clock audit deadline')
    signal.signal(signal.SIGALRM,stop);signal.signal(signal.SIGTERM,stop);signal.alarm(590)
    profile=MessageClockProfile(wrapper_day_start_ms=spec['wrapper_day_start_ms'])
    def packet(v):print(json.dumps(v,sort_keys=True),flush=True)
    packet({'stage':'started','pid':os.getpid(),'diagnostic':'clock_origin_by_message_kind'})
    result=None;failure=None;began=time.monotonic()
    try:
        result=stream_object(Path(spec['path']),advertised_bytes=spec['compressed_bytes'],
            max_input_bytes=spec['compressed_bytes'],max_decoded_bytes=spec['decoded_bytes'],
            wall_seconds=580,consume=profile.consume,decoder_memory_bytes=256*1024**2)
        if (not result['complete'] or result['compressed_sha256']!=spec['compressed_sha256']
                or result['decoded_sha256']!=spec['decoded_sha256'] or result['decoded_records']!=spec['records']):
            failure='PinnedContentOrCompletionMismatch'
    except BaseException as exc:failure=type(exc).__name__
    finally:signal.alarm(0)
    packet({'stage':'terminal','report':{'schema':'message_clock_origin_run_v1','complete':failure is None,
        'failure_type':failure,'transport':result,'profile':profile.summary(),'spec':spec,
        'elapsed_seconds':time.monotonic()-began,'peak_self_rss_kib_linux':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'source_admitted':False,'fits':0,'provider_calls':0,'raw_rows_exported':0,'new_test_opened':False}})


def publication():
    from market_rsi import file_hash
    repo=ROOT.parents[1]
    def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],timeout=30).decode().strip()
    paths=[ROOT/'quote_source/reconstruct.py',ROOT/'audit_tools/single_object_stream.py',
        ROOT/'CLOCK_ORIGIN_AND_SAMPLES_2026-09-13.md',Path(__file__).resolve(),
        ROOT/'audit_tools/message_clock_origin.py',ROOT/'audit_tools/test_message_clock_origin.py']
    names=[str(p.relative_to(repo)) for p in paths]
    if git('status','--porcelain','--',*names):raise ValueError('uncommitted operation source')
    commit=git('rev-parse','HEAD');ref='refs/tags/'+TAG
    for p,name in zip(paths,names):
        if hashlib.sha256(subprocess.check_output(['git','-C',str(repo),'show',commit+':'+name],timeout=30)).hexdigest()!=file_hash(p):
            raise ValueError('HEAD source mismatch')
    if git('remote','get-url','origin')!='https://github.com/Estelle-LH/RSIBench-Data.git':raise ValueError('wrong origin')
    if git('cat-file','-t',ref)!='tag' or git('rev-parse',ref+'^{commit}')!=commit:raise ValueError('annotated version required')
    tag=git('rev-parse',ref);refs={line.split()[1]:line.split()[0] for line in git('ls-remote','origin',ref,ref+'^{}').splitlines()}
    if refs!={ref:tag,ref+'^{}':commit}:raise ValueError('version not published')
    return {'tag':TAG,'tag_object':tag,'commit':commit,'sources':{str(p.relative_to(ROOT)):file_hash(p) for p in paths}}


def exchange(code,output):
    from market_rsi import fresh_json
    command='flock -n /tmp/market-rsi-population-quote.lock nice -n 10 timeout --signal=TERM --kill-after=5s 600s python3 -u - --remote'
    p=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','root@173.255.231.4',command],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    fresh_json(output/'process.json',{'ssh_pid':p.pid})
    p.stdin.write(code);p.stdin.close();os.set_blocking(p.stdout.fileno(),False)
    selector=selectors.DefaultSelector();selector.register(p.stdout,selectors.EVENT_READ)
    pending=b'';total=seq=0;terminal=None;deadline=time.monotonic()+630;error=None;temporary_cleanup=None
    try:
        while True:
            if time.monotonic()>deadline:raise TimeoutError('transport deadline')
            if not selector.select(1):continue
            data=os.read(p.stdout.fileno(),65536)
            if not data:break
            total+=len(data);pending+=data
            if total>1024*1024:raise ValueError('aggregate output bound')
            while b'\n' in pending:
                line,pending=pending.split(b'\n',1);packet=json.loads(line)
                fresh_json(output/f'progress-{seq:03d}.json',packet);seq+=1
                if packet['stage']=='terminal':terminal=packet['report']
                else:
                    if packet['stage']=='cleanup':temporary_cleanup=packet.get('temporary_directory_removed')
                    print(packet,flush=True)
        code=p.wait(timeout=10)
        if code or pending or terminal is None:raise ValueError('terminal missing')
        terminal.update(ssh_reaped=True,exit_code=code,temporary_directory_removed=temporary_cleanup)
    except BaseException as exc:error=type(exc).__name__
    finally:
        if p.poll() is None:p.terminate()
        try:p.wait(timeout=10)
        except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
        selector.close();p.stdout.close()
    if error:
        fresh_json(output/'failure.json',{'failure_type':error,'ssh_reaped':True,'remote_exit_verified':terminal is not None,'retry':False})
        raise RuntimeError('clock audit transport did not finish')
    return terminal


def run(output,canary):
    from market_rsi import digest,file_hash,fresh_json,load_json
    output=output.resolve()
    if output.exists():raise ValueError('fresh output required')
    if canary:
        from quote_source.test_reconstruct import delta,snap,T
        a=delta();b=snap(t=T+1);b['src']='rest';b['m']['timestamp']=str(T-10*86400000)
        raw=b''.join((json.dumps(r)+'\n').encode() for r in [a,b,delta(t=T+2)])
        encoded=subprocess.run(['zstd','-q','-c'],input=raw,stdout=subprocess.PIPE,check=True).stdout
        spec={'path':'/__SYNTHETIC_DIRECTORY__/fixture.zst','compressed_bytes':len(encoded),'decoded_bytes':len(raw),
            'records':3,'compressed_sha256':hashlib.sha256(encoded).hexdigest(),'decoded_sha256':hashlib.sha256(raw).hexdigest(),
            'wrapper_day_start_ms':T//86400000*86400000,'synthetic_only':True}
        actual=program(spec).decode()
        code=('import tempfile,pathlib,base64,json\nwith tempfile.TemporaryDirectory(prefix="market-rsi-clock-canary-") as tmp:\n'
            ' p=pathlib.Path(tmp)/"fixture.zst";p.write_bytes(base64.b64decode('+repr(base64.b64encode(encoded).decode())+'))\n'
            ' exec('+repr(actual)+'.replace("/__SYNTHETIC_DIRECTORY__",tmp),{"__name__":"__main__"})\n'
            'print(json.dumps({"stage":"cleanup","temporary_directory_removed":not pathlib.Path(tmp).exists()}))\n').encode()
        published={'synthetic_only':True,'runner_sha256':file_hash(__file__)}
    else:
        if file_hash(PRIOR)!=PRIOR_SHA:raise ValueError('prior pinned source receipt changed')
        r=load_json(PRIOR)
        if r['result_sha256']!=digest({k:v for k,v in r.items() if k!='result_sha256'}) or not r['complete']:raise ValueError('prior incomplete')
        t=r['transport'];obj=r['scope']['object']
        spec={'path':str(Path(obj['source_root'])/obj['relative_path']),'compressed_bytes':t['compressed_bytes_read'],
            'decoded_bytes':t['decoded_bytes'],'records':t['decoded_records'],'compressed_sha256':t['compressed_sha256'],
            'decoded_sha256':t['decoded_sha256'],'wrapper_day_start_ms':1788825600000,'synthetic_only':False,
            'prior_audit_sha256':PRIOR_SHA,'purpose':'new attribution by message kind, not a rerun of quote validity or a score retry'}
        published=publication();code=program(spec)
    output.mkdir(parents=True)
    claim={'schema':'clock_origin_claim_v1','spec':spec,'publication':published,'program_sha256':hashlib.sha256(code).hexdigest()}
    if not canary:
        claims=ROOT/'artifacts/message-clock-origin-claims';claims.mkdir(exist_ok=True)
        fresh_json(claims/(PRIOR_SHA+'.json'),{**claim,'output':str(output)})
    fresh_json(output/'claim.json',claim)
    result=exchange(code,output)
    if canary and (not result['complete'] or result['temporary_directory_removed'] is not True
            or result['profile']['source_regression_transition_counts']!={'price_change -> rest_snapshot':1}):
        raise ValueError('synthetic clock attribution wrong')
    result.update(publication=published,claim_sha256=file_hash(output/'claim.json'),synthetic_only=canary)
    result['result_sha256']=digest(result);fresh_json(output/('canary.json' if canary else 'report.json'),result)
    print({'complete':result['complete'],'result_sha256':result['result_sha256'],'elapsed_seconds':result['elapsed_seconds']})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--remote',action='store_true');p.add_argument('--canary',action='store_true');p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.remote:remote(SPEC)
    else:
        if a.output is None:p.error('--output required')
        run(a.output,a.canary)
