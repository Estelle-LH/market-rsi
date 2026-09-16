"""Independent partial raw-file audit; does NOT execute an invalid label request."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
TAG='pm-single-object-audit-v0.1.0'
REQUEST_SHA='93896ed226139a4d9c80b52ec460a1e34cf398a9b60d2133b79f0d2c669649d5'
STUDY_SHA='ccd61b133a4ebe2391a3ea58e1981f75dbb229723a8ae5c7333cb20ab95cd75d'
INVENTORY_SHA='eff3f1a9ff2019874ffc92a6762075073890d25e4cbd1c095d7ae88b8ed2b89d'
HOST='173.255.231.4'
SELECTED={'advertised_bytes':13166507,'date':'2026-09-08','hour':'12','host':HOST,
    'relative_path':'polymarket-20260908T12.jsonl.zst','source_root':'/opt/d10/raw/data/polymarket'}
LIMITS={'max_input_bytes':13166507,'max_decoded_bytes':2147483648,'memory_bytes':1073741824,'wall_seconds':600}


def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def partial_scope(request, inventory):
    """Extract ONLY independently valid, exact bounded identity; no JSON repair."""
    if request.get('tool')!='request_capability' or request.get('status')!='ok':
        raise ValueError('successful archived request required')
    payload=request['arguments']['verification_needed']
    if not isinstance(payload,str):raise ValueError('original request text required')
    try:json.loads(payload)
    except json.JSONDecodeError as exc:parse_error={'position':exc.pos,'message':exc.msg}
    else:raise ValueError('different request: review scope again')
    marker='"exact_objects":'
    if payload.count(marker)!=1:raise ValueError('ambiguous object declaration')
    objects,_=json.JSONDecoder().raw_decode(payload.split(marker,1)[1].lstrip())
    if objects!=[SELECTED]:raise ValueError('controller identity differs')
    for key,value in LIMITS.items():
        matches=re.findall(r'"'+key+r'"\s*:\s*([0-9]+)(?=\s*[,}])',payload)
        if matches!=[str(value)]:raise ValueError('controller resource declaration differs')
    entries=[f for f in inventory['files'] if f['filename']==SELECTED['relative_path']]
    if (len(entries)!=1 or entries[0]['date']!=SELECTED['date']
            or entries[0]['compressed_bytes']!=SELECTED['advertised_bytes']
            or inventory['host']!=HOST or inventory['source_root']!=SELECTED['source_root']):
        raise ValueError('inventory identity differs')
    return {'schema':'independent_partial_source_audit_scope_v1','object':SELECTED,**LIMITS,
        'original_request_json_valid':False,'original_request_parse_error':parse_error,
        'entire_request_executed':False,'label_rules_executed':False,
        'reason':'Only unambiguous source identity, hashing and raw descriptive counts; malformed/contradictory label contract not repaired.',
        'source_admitted':False,'new_test_opened':False,'automatic_retry':False,'provider_calls':0}


def module_source(name,path):
    return 'm=types.ModuleType('+repr(name)+');sys.modules[m.__name__]=m\nexec('+repr(path.read_text())+',m.__dict__)\n'


def remote_program(scope):
    source='import sys,types\np=types.ModuleType("quote_source");p.__path__=[];sys.modules[p.__name__]=p\n'
    for name,path in [('quote_source.reconstruct',ROOT/'quote_source/reconstruct.py'),
        ('population_quote_profile',ROOT/'audit_tools/population_quote_profile.py'),
        ('source_clock_profile',ROOT/'audit_tools/source_clock_profile.py'),
        ('single_object_stream',ROOT/'audit_tools/single_object_stream.py')]:source+=module_source(name,path)
    source+='SCOPE='+repr(scope)+'\n__file__="/tmp/single_object_audit_stdin.py"\n'+Path(__file__).read_text()
    return source.encode()


def remote(scope):
    import resource
    from single_object_stream import stream_object
    from source_clock_profile import SourceProfile
    resource.setrlimit(resource.RLIMIT_AS,(768*1024**2,768*1024**2))
    def deadline(*_):raise TimeoutError('owned remote deadline')
    signal.signal(signal.SIGALRM,deadline);signal.signal(signal.SIGTERM,deadline);signal.alarm(590)
    profile=SourceProfile();began=time.monotonic();attempted=0;decoded_consumed=0
    def packet(v):print(json.dumps(v,sort_keys=True),flush=True)
    def consume(line,ordinal):
        nonlocal attempted,decoded_consumed
        attempted=ordinal
        profile.consume(line,ordinal);decoded_consumed+=len(line)
        if ordinal%50000==0:packet({'stage':'progress','records':ordinal,'elapsed_seconds':time.monotonic()-began})
    packet({'stage':'started','pid':os.getpid(),'scope':'single object, raw diagnostics only'})
    transport=None;error=None
    try:
        transport=stream_object(Path(scope['object']['source_root'])/scope['object']['relative_path'],
            advertised_bytes=scope['object']['advertised_bytes'],max_input_bytes=scope['max_input_bytes'],
            max_decoded_bytes=scope['max_decoded_bytes'],wall_seconds=580,consume=consume,
            decoder_memory_bytes=256*1024**2)
    except BaseException as exc:error=type(exc).__name__
    finally:signal.alarm(0)
    result={'schema':'independent_single_object_audit_v1','scope':scope,
        'complete':transport is not None and transport['complete'],
        'transport':transport,'failure_type':error or (transport and transport['failure_type']),
        'last_attempted_record':attempted,'successfully_consumed_decoded_bytes':decoded_consumed,
        'profile':profile.summary(),'peak_self_rss_kib_linux':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'elapsed_seconds':time.monotonic()-began,'source_admitted':False,'qa_pass':False,
        'features_computed':False,'labels_computed':False,'fits':0,'provider_calls':0,
        'raw_rows_exported':0,'raw_identifiers_exported':0,'derived_rows_persisted':False,
        'new_test_opened':False,'request_fulfilled_in_full':False}
    packet({'stage':'terminal','report':result})


def publication():
    repo=ROOT.parents[1]
    def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],timeout=30).decode().strip()
    paths=[ROOT/'quote_source/reconstruct.py',ROOT/'quote_source/test_reconstruct.py',
        ROOT/'SINGLE_OBJECT_AUDIT_2026-09-13.md']
    paths += [ROOT/'audit_tools'/name for name in ('population_quote_profile.py','test_population_quote_profile.py',
        'single_object_stream.py','test_single_object_stream.py','canary_single_object_linux.py',
        'source_clock_profile.py','test_source_clock_profile.py','run_single_object_audit.py','test_run_single_object_audit.py',
        'canary_single_object_audit.py')]
    names=[str(p.relative_to(repo)) for p in paths]
    if git('status','--porcelain','--',*names):raise ValueError('uncommitted audit code or protocol')
    commit=git('rev-parse','HEAD')
    for p,n in zip(paths,names):
        if hashlib.sha256(subprocess.check_output(['git','-C',str(repo),'show',commit+':'+n],timeout=30)).hexdigest()!=file_hash(p):
            raise ValueError('audit source not at HEAD')
    if git('remote','get-url','origin')!='https://github.com/Estelle-LH/RSIBench-Data.git':raise ValueError('wrong origin')
    ref='refs/tags/'+TAG
    if git('cat-file','-t',ref)!='tag' or git('rev-parse',ref+'^{commit}')!=commit:raise ValueError('wrong source version')
    tag_object=git('rev-parse',ref)
    refs={line.split()[1]:line.split()[0] for line in git('ls-remote','origin',ref,ref+'^{}').splitlines()}
    if refs!={ref:tag_object,ref+'^{}':commit}:raise ValueError('version not published')
    return {'tag':TAG,'tag_object':tag_object,'commit':commit,
        'sources':{str(p.relative_to(ROOT)):file_hash(p) for p in paths},'human_directed_engineering':True}


def local(output):
    from market_rsi import digest,fresh_json,load_json
    workspace=ROOT/'artifacts/temporal-executable-controller-20260913-01'
    request=workspace/'records/0009.json';study=workspace/'source-study-proposal.json'
    inventory=ROOT/'artifacts/capture-raw-inventory-20260911-01/report.json'
    for path,expected in ((request,REQUEST_SHA),(study,STUDY_SHA),(inventory,INVENTORY_SHA)):
        if file_hash(path)!=expected:raise ValueError('frozen input commitment differs')
    assessment=load_json(workspace/'session/assessment.json')
    if not assessment['process_reaped'] or not assessment['valid']:raise ValueError('controller not terminal')
    scope=partial_scope(load_json(request),load_json(inventory));published=publication()
    program=remote_program(scope);output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    claim={'schema':'single_object_audit_claim_v1','scope':scope,'request_sha256':REQUEST_SHA,'study_sha256':STUDY_SHA,
        'inventory_sha256':INVENTORY_SHA,'publication':published,'program_sha256':hashlib.sha256(program).hexdigest()}
    claims=ROOT/'artifacts/single-object-audit-claims';claims.mkdir(exist_ok=True)
    fresh_json(claims/(REQUEST_SHA+'.json'),{'output':str(output),**claim})
    fresh_json(output/'claim.json',claim)
    command='flock -n /tmp/market-rsi-population-quote.lock nice -n 10 timeout --signal=TERM --kill-after=5s 600s python3 -u - --remote'
    process=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','root@'+HOST,command],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    fresh_json(output/'process.json',{'pid':process.pid,'remote_pid':None,'source_read_started':False})
    process.stdin.write(program);process.stdin.close();os.set_blocking(process.stdout.fileno(),False)
    selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
    pending=b'';received=seq=0;terminal=None;limit=time.monotonic()+630;error=None;code=None
    try:
        while True:
            if time.monotonic()>limit:raise TimeoutError('SSH deadline')
            if not selector.select(1):continue
            data=os.read(process.stdout.fileno(),65536)
            if not data:break
            received+=len(data);pending+=data
            if received>8*1024**2:raise ValueError('aggregate output exceeded bound')
            while b'\n' in pending:
                line,pending=pending.split(b'\n',1);packet=json.loads(line)
                fresh_json(output/f'progress-{seq:03d}.json',packet);seq+=1
                if packet.get('stage')=='terminal':terminal=packet['report']
                else:print(json.dumps(packet),flush=True)
        code=process.wait(timeout=10)
        if code!=0 or pending or terminal is None:raise ValueError('terminal evidence incomplete')
        terminal.update(publication=published,claim_sha256=file_hash(output/'claim.json'),ssh_reaped=True,exit_code=code)
        terminal['result_sha256']=digest(terminal);fresh_json(output/'report.json',terminal)
        print(json.dumps({'report':str(output/'report.json'),'complete':terminal['complete'],
            'raw_records':terminal['last_attempted_record'],'elapsed_seconds':terminal['elapsed_seconds']}),flush=True)
    except BaseException as exc:error=type(exc).__name__
    finally:
        if process.poll() is None:process.terminate()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        selector.close();process.stdout.close()
    if error:
        fresh_json(output/'failure.json',{'failure_type':error,'ssh_reaped':process.poll() is not None,
            'remote_exit_verified':terminal is not None,'no_automatic_retry':True,'received_packets':seq})
        raise RuntimeError('source audit did not return verified terminal evidence')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--remote',action='store_true');parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.remote:remote(SCOPE)
    else:
        if args.output is None:parser.error('--output required')
        local(args.output)
