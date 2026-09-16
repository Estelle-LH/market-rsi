"""One permanently claimed raw-file profile; never training or source admission."""
import argparse
import base64
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
TAG='pm-typed-raw-profile-v0.1.0'
WORKSPACE=ROOT/'artifacts/sample-contract-controller-20260913-01'
REQUEST_SHA='da4a0f88f052d254cdb7616cc63b2aeb0cdb3543f4b1beeaebc28c6b9dd0ad53'
PROPOSAL_SHA='7ea606e5bbe83dc6f9fb0bf64056695ca42033bd847be4443748ae5ce1a54d7b'
MODULES=[('market_rsi','market_rsi.py'),('quote_source.reconstruct','quote_source/reconstruct.py'),
    ('data_scientist_harness.temporal_contract','data_scientist_harness/temporal_contract.py'),
    ('data_scientist_harness.event_sample_kernel','data_scientist_harness/event_sample_kernel.py'),
    ('data_scientist_harness.sample_contract','data_scientist_harness/sample_contract.py'),
    ('typed_raw_profile','audit_tools/typed_raw_profile.py'),('single_object_stream','audit_tools/single_object_stream.py')]


def program(spec):
    code='import types,sys\n'
    for name in ('quote_source','data_scientist_harness'):
        code+='m=types.ModuleType('+repr(name)+');m.__path__=[];sys.modules[m.__name__]=m\n'
    for name,path in MODULES:
        code+='m=types.ModuleType('+repr(name)+');m.__file__='+repr(path)+';sys.modules[m.__name__]=m\n'
        code+='exec('+repr((ROOT/path).read_text())+',m.__dict__)\n'
    return (code+'SPEC='+repr(spec)+'\n__file__="/tmp/typed_raw_profile_stdin.py"\n'+Path(__file__).read_text()).encode()


def remote(spec):
    import resource
    from typed_raw_profile import Profile
    from single_object_stream import stream_object
    resource.setrlimit(resource.RLIMIT_AS,(768*1024**2,768*1024**2))
    def stop(*_):raise TimeoutError('bounded profile deadline')
    signal.signal(signal.SIGALRM,stop);signal.signal(signal.SIGTERM,stop);signal.alarm(590)
    def emit(v):print(json.dumps(v,sort_keys=True,allow_nan=False),flush=True)
    p=Profile(spec['contract'],spec['day_start_ms']);start=time.monotonic();transport=profile=None;failure=None
    emit({'stage':'started','pid':os.getpid(),'kind':'typed_raw_sample_profile','synthetic_only':spec['synthetic_only']})
    def consume(line,n):
        p.consume(line,n)
        if n%50000==0:emit({'stage':'decode_progress','records':n,'elapsed_seconds':time.monotonic()-start})
    try:
        transport=stream_object(spec['path'],advertised_bytes=spec['compressed_bytes'],
            max_input_bytes=spec['compressed_bytes'],max_decoded_bytes=spec['max_decoded_bytes'],
            wall_seconds=580,consume=consume,decoder_memory_bytes=256*1024**2)
        if not transport['complete']:raise ValueError('incomplete raw transport')
        profile=p.summary(lambda a,b:emit({'stage':'sample_progress','entities_done':a,'entities_total':b}))
    except BaseException as exc:failure=type(exc).__name__
    finally:signal.alarm(0)
    emit({'stage':'terminal','report':{'schema':'typed_raw_profile_run_v1','complete':failure is None,
        'failure_type':failure,'transport':transport,'profile':profile,'spec':spec,
        'partial_counts_on_failure':dict(p.counts) if failure else None,
        'last_attempted_record':p.last_ordinal,'elapsed_seconds':time.monotonic()-start,
        'peak_self_rss_kib_linux':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'fits':0,'provider_calls':0,'source_admitted':False,'new_dev_test_opened':False}})


def exchange(code,output):
    from market_rsi import fresh_json
    command='flock -n /tmp/market-rsi-population-quote.lock nice -n 10 timeout --signal=TERM --kill-after=5s 600s python3 -u - --remote'
    p=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','root@173.255.231.4',command],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    fresh_json(output/'process.json',{'ssh_pid':p.pid})
    p.stdin.write(code);p.stdin.close();os.set_blocking(p.stdout.fileno(),False)
    selector=selectors.DefaultSelector();selector.register(p.stdout,selectors.EVENT_READ,data='stdout')
    selector.register(p.stderr,selectors.EVENT_READ,data='stderr')
    pending=b'';stderr=b'';total=seq=0;terminal=None;deadline=time.monotonic()+630;error=None;cleanup=None
    remote_exit_code=None;open_streams=2
    try:
        while True:
            if time.monotonic()>deadline:raise TimeoutError('transport deadline')
            events=selector.select(1)
            if not events:continue
            for key,_ in events:
                data=os.read(key.fileobj.fileno(),65536)
                if not data:
                    selector.unregister(key.fileobj);open_streams-=1
                    continue
                if key.data=='stderr':
                    stderr+=data
                    if len(stderr)>64*1024:raise ValueError('aggregate stderr bound')
                    continue
                total+=len(data);pending+=data
                if total>8*1024**2:raise ValueError('aggregate output bound')
                while b'\n' in pending:
                    line,pending=pending.split(b'\n',1);packet=json.loads(line)
                    fresh_json(output/f'progress-{seq:03d}.json',packet);seq+=1
                    if packet['stage']=='terminal':terminal=packet['report']
                    else:
                        if packet['stage']=='cleanup':cleanup=packet['temporary_directory_removed']
                        print(json.dumps(packet),flush=True)
            if open_streams==0:break
        remote_exit_code=p.wait(timeout=10)
        if remote_exit_code or pending or terminal is None:raise ValueError('terminal missing')
        terminal.update(ssh_reaped=True,exit_code=remote_exit_code,temporary_directory_removed=cleanup)
    except BaseException as exc:error=type(exc).__name__
    finally:
        if p.poll() is None:p.terminate()
        try:p.wait(timeout=10)
        except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
        selector.close();p.stdout.close();p.stderr.close()
    if error:
        reason=('scan_lock_unavailable' if total==0 and not stderr and remote_exit_code==1
            else 'remote_stderr' if stderr else 'transport_or_protocol_failure')
        fresh_json(output/'failure.json',{'failure_type':error,'reason':reason,
            'ssh_reaped':True,'remote_exit_code':remote_exit_code,
            'remote_exit_verified':terminal is not None,'stdout_bytes':total,
            'stderr_bytes':len(stderr),'stderr_sha256':hashlib.sha256(stderr).hexdigest(),
            'stderr_tail':stderr.decode('utf-8','replace')[-4096:],'retry':False})
        raise RuntimeError('typed profile did not return verified terminal evidence')
    return terminal


def publication():
    from market_rsi import file_hash
    from data_scientist_harness.release import git
    repo=ROOT.parents[1]
    paths=sorted({path for _,path in MODULES}|{'audit_tools/run_typed_raw_profile.py',
        'audit_tools/test_typed_raw_profile.py','TYPED_RAW_RUN_2026-09-13.md'})
    names=[str((ROOT/p).relative_to(repo)) for p in paths]
    commit=git(repo,'rev-parse','HEAD').decode().strip();ref='refs/tags/'+TAG
    if git(repo,'status','--porcelain','--',*names).strip():raise ValueError('uncommitted operation sources')
    for p,n in zip(paths,names):
        if hashlib.sha256(git(repo,'show',commit+':'+n)).hexdigest()!=file_hash(ROOT/p):raise ValueError('source differs')
    if git(repo,'remote','get-url','origin').decode().strip()!='https://github.com/Estelle-LH/RSIBench-Data.git':raise ValueError('wrong origin')
    if git(repo,'cat-file','-t',ref).decode().strip()!='tag' or git(repo,'rev-parse',ref+'^{commit}').decode().strip()!=commit:
        raise ValueError('new annotated source tag required')
    tag=git(repo,'rev-parse',ref).decode().strip()
    refs={v.split()[1]:v.split()[0] for v in git(repo,'ls-remote','origin',ref,ref+'^{}').decode().splitlines()}
    if refs!={ref:tag,ref+'^{}':commit}:raise ValueError('tag not published')
    return {'tag':TAG,'commit':commit,'tag_object':tag,'source_hashes':{p:file_hash(ROOT/p) for p in paths}}


def prepare_spec():
    from market_rsi import file_hash,load_json
    from review_clock_feedback import exact_object
    from source_inventory_context import INVENTORY,SHA
    from data_scientist_harness.store import Store
    from data_scientist_harness.sample_contract import bound_probe
    if file_hash(WORKSPACE/'records/0015.json')!=REQUEST_SHA or file_hash(WORKSPACE/'source-study-proposal.json')!=PROPOSAL_SHA:
        raise ValueError('frozen controller request changed')
    if file_hash(INVENTORY)!=SHA:raise ValueError('inventory changed')
    store=Store(WORKSPACE,file_hash(WORKSPACE/'workspace.json'));store.verify()
    assessment=load_json(WORKSPACE/'session/assessment.json')
    if not assessment['valid'] or not assessment['process_reaped']:raise ValueError('controller not complete')
    proposal=load_json(WORKSPACE/'source-study-proposal.json')
    bound=bound_probe(store,'0010',proposal['typed_temporal_contract']['contract'])
    if bound!=proposal['typed_sample_contract']:raise ValueError('sample binding differs')
    r=load_json(WORKSPACE/'records/0015.json');request=json.loads(r['arguments']['verification_needed'])
    if r['result']['activated'] is not False or bound['contract_sha256'] not in r['arguments']['verification_needed']:
        raise ValueError('request already activated or sample hash missing')
    obj=exact_object(request,load_json(INVENTORY))
    return {'path':obj['path'],'compressed_bytes':obj['advertised_bytes'],'max_decoded_bytes':request['max_decoded_bytes'],
        'contract':bound['contract'],'contract_sha256':bound['contract_sha256'],
        'day_start_ms':int(datetime.fromisoformat(obj['date']).replace(tzinfo=timezone.utc).timestamp()*1000),
        'synthetic_only':False,'request_sha256':REQUEST_SHA,'proposal_sha256':PROPOSAL_SHA,
        'scope':'single-object typed sample availability; not training or source admission'}


def run(output,canary):
    from market_rsi import digest,file_hash,fresh_json,load_json
    from typed_raw_profile import Profile
    output=output.resolve()
    if output.exists():raise ValueError('fresh output required')
    spec=prepare_spec();expected=None
    if canary:
        from test_typed_raw_profile import message,T
        rows=[message(T+t) for t in [0,30000,60000,120000,120001,180001,180002]]
        raw=b''.join((json.dumps(r)+'\n').encode() for r in rows)
        encoded=subprocess.run(['zstd','-q','-c'],input=raw,stdout=subprocess.PIPE,check=True).stdout
        p=Profile(spec['contract'],T)
        for i,r in enumerate(rows,1):p.consume(json.dumps(r).encode(),i)
        expected=digest(p.summary())
        spec.update(path='/__SYNTHETIC_DIRECTORY__/fixture.zst',compressed_bytes=len(encoded),max_decoded_bytes=len(raw),
            day_start_ms=T,synthetic_only=True)
        body=program(spec).decode()
        code=('import tempfile,pathlib,base64,json\nwith tempfile.TemporaryDirectory(prefix="market-rsi-typed-canary-") as tmp:\n'
            ' p=pathlib.Path(tmp)/"fixture.zst";p.write_bytes(base64.b64decode('+repr(base64.b64encode(encoded).decode())+'))\n'
            ' exec('+repr(body)+'.replace("/__SYNTHETIC_DIRECTORY__",tmp),{"__name__":"__main__"})\n'
            'print(json.dumps({"stage":"cleanup","temporary_directory_removed":not pathlib.Path(tmp).exists()}))\n').encode()
        published={'synthetic_only':True,'sources':{p:file_hash(ROOT/p) for _,p in MODULES},'runner_sha256':file_hash(__file__)}
    else:published=publication();code=program(spec)
    output.mkdir(parents=True)
    claim={'schema':'typed_raw_profile_claim_v1','spec':spec,'publication':published,'program_sha256':hashlib.sha256(code).hexdigest()}
    if not canary:
        claims=ROOT/'artifacts/typed-raw-profile-claims';claims.mkdir(exist_ok=True)
        fresh_json(claims/(REQUEST_SHA+'.json'),{**claim,'output':str(output)})
    fresh_json(output/'claim.json',claim)
    r=exchange(code,output)
    if canary and (not r['complete'] or r['temporary_directory_removed'] is not True or digest(r['profile'])!=expected):
        raise ValueError('remote fixture or cleanup differs')
    r.update(publication=published,claim_sha256=file_hash(output/'claim.json'),synthetic_only=canary)
    r['result_sha256']=digest(r);fresh_json(output/('canary.json' if canary else 'report.json'),r)
    print(json.dumps({'complete':r['complete'],'result_sha256':r['result_sha256'],
        'elapsed_seconds':r['elapsed_seconds'],'fits':r['fits']}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--remote',action='store_true');p.add_argument('--canary',action='store_true');p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.remote:remote(SPEC)
    else:
        if a.output is None:p.error('--output required')
        run(a.output,a.canary)
