"""User-approved, CPU-only preliminary comparison; no formal gate override."""
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
TAG='pm-preliminary-comparison-v0.1.0'
TRAIN_SHA='1bde962eacd34d858228f0f24aa711ac5617e6ec064082b70da5bf87a1b552ff'
TRAIN=ROOT/'artifacts/typed-raw-profile-20260913-01/report.json'
FILES=[('2026-08-25',35120175),('2026-09-07',16365581),('2026-09-08',13166507),('2026-09-09',18153334)]


def modules():
    from run_typed_raw_profile import MODULES
    return MODULES+[('preliminary_comparison','audit_tools/preliminary_comparison.py')]


def program(spec):
    code='import types,sys\n'
    for name in ('quote_source','data_scientist_harness'):
        code+='m=types.ModuleType('+repr(name)+');m.__path__=[];sys.modules[m.__name__]=m\n'
    for name,path in modules():
        code+='m=types.ModuleType('+repr(name)+');m.__file__='+repr(path)+';sys.modules[m.__name__]=m\n'
        code+='exec('+repr((ROOT/path).read_text())+',m.__dict__)\n'
    return (code+'SPEC='+repr(spec)+'\n__file__="/tmp/preliminary_comparison_stdin.py"\n'+Path(__file__).read_text()).encode()


def remote(spec):
    import resource
    from typed_raw_profile import Profile
    from preliminary_comparison import evaluate
    from single_object_stream import stream_object
    resource.setrlimit(resource.RLIMIT_AS,(768*1024**2,768*1024**2))
    def stop(*_):raise TimeoutError('bounded diagnostic deadline')
    signal.signal(signal.SIGALRM,stop);signal.signal(signal.SIGTERM,stop);signal.alarm(590)
    def emit(v):print(json.dumps(v,sort_keys=True,allow_nan=False),flush=True)
    start=time.monotonic();transport=result=None;failure=None
    p=Profile(spec['contract'],spec['day_start_ms'])
    emit(dict(stage='started',pid=os.getpid(),date=spec['date'],synthetic_only=spec['synthetic_only']))
    def consume(line,n):
        p.consume(line,n)
        if n%50000==0:emit(dict(stage='decode_progress',records=n,elapsed_seconds=time.monotonic()-start))
    try:
        transport=stream_object(spec['path'],advertised_bytes=spec['compressed_bytes'],max_input_bytes=spec['compressed_bytes'],
            max_decoded_bytes=spec['max_decoded_bytes'],wall_seconds=580,consume=consume,decoder_memory_bytes=256*1024**2)
        if not transport['complete']:raise ValueError('incomplete source')
        if spec.get('expected_compressed_sha256') and transport['compressed_sha256']!=spec['expected_compressed_sha256']:
            raise ValueError('previously bound source differs')
        result=evaluate(p,spec['beta'],lambda a,b:emit(dict(stage='scoring_progress',entities_done=a,entities_total=b)))
    except BaseException as exc:failure=type(exc).__name__
    finally:signal.alarm(0)
    emit(dict(stage='terminal',report=dict(schema='preliminary_file_comparison_v1',complete=failure is None,
        failure_type=failure,transport=transport,evaluation=result,spec=spec,
        partial_counts_on_failure=dict(p.counts) if failure else None,last_attempted_record=p.last_ordinal,
        elapsed_seconds=time.monotonic()-start,peak_self_rss_kib_linux=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        fits_on_check=0,provider_calls=0,source_admitted=False,formal_experiment_activated=False)))


def publication():
    from market_rsi import file_hash
    from data_scientist_harness.release import git
    repo=ROOT.parents[1]
    paths=sorted({p for _,p in modules()}|{'audit_tools/run_preliminary_comparison.py',
        'audit_tools/run_typed_raw_profile.py','audit_tools/test_preliminary_comparison.py',
        'PRELIMINARY_COMPARISON_2026-09-13.md'})
    names=[str((ROOT/p).relative_to(repo)) for p in paths]
    commit=git(repo,'rev-parse','HEAD').decode().strip();ref='refs/tags/'+TAG
    if git(repo,'status','--porcelain','--',*names).strip():raise ValueError('uncommitted operation source')
    for p,n in zip(paths,names):
        if hashlib.sha256(git(repo,'show',commit+':'+n)).hexdigest()!=file_hash(ROOT/p):raise ValueError('source differs')
    if git(repo,'remote','get-url','origin').decode().strip()!='https://github.com/Estelle-LH/RSIBench-Data.git':raise ValueError('wrong origin')
    if git(repo,'cat-file','-t',ref).decode().strip()!='tag' or git(repo,'rev-parse',ref+'^{commit}').decode().strip()!=commit:
        raise ValueError('new annotated source tag required')
    tag=git(repo,'rev-parse',ref).decode().strip()
    refs={v.split()[1]:v.split()[0] for v in git(repo,'ls-remote','origin',ref,ref+'^{}').decode().splitlines()}
    if refs!={ref:tag,ref+'^{}':commit}:raise ValueError('tag not published')
    return dict(tag=TAG,commit=commit,tag_object=tag,source_hashes={p:file_hash(ROOT/p) for p in paths})


def prepare():
    from market_rsi import load_json,digest,file_hash
    from typed_raw_profile import CONTRACT_SHA
    from run_typed_raw_profile import WORKSPACE,PROPOSAL_SHA
    r=load_json(TRAIN)
    if r['result_sha256']!=TRAIN_SHA or digest({k:v for k,v in r.items() if k!='result_sha256'})!=TRAIN_SHA:
        raise ValueError('training evidence altered')
    if not r['complete'] or r['synthetic_only'] or not r['ssh_reaped'] or not r['transport']['source_unchanged_verified']:
        raise ValueError('training evidence incomplete')
    if r['profile']['counts']['numerically_available']!=r['profile']['paired_moments']['n']:
        raise ValueError('training counts differ')
    if r['profile']['counts'].get('rejected_segments',0) or r['profile']['counts'].get('invalid_quotes',0):
        raise ValueError('training sanity evidence changed')
    if digest(r['spec']['contract'])!=CONTRACT_SHA or file_hash(WORKSPACE/'source-study-proposal.json')!=PROPOSAL_SHA:
        raise ValueError('method binding changed')
    invpath=ROOT/'artifacts/capture-raw-inventory-20260911-01/report.json'
    if file_hash(invpath)!='eff3f1a9ff2019874ffc92a6762075073890d25e4cbd1c095d7ae88b8ed2b89d':
        raise ValueError('inventory changed')
    inventory=load_json(invpath);objects=[]
    for date,size in FILES:
        name='polymarket-'+date.replace('-','')+'T12.jsonl.zst'
        if [a for a in inventory['files'] if a['filename']==name]!=[dict(date=date,filename=name,compressed_bytes=size)]:
            raise ValueError('source not exactly inventoried')
        start=int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp()*1000)
        if start<=r['profile']['cutoff_ms']:raise ValueError('check not strictly later')
        objects.append(dict(date=date,path='/opt/d10/raw/data/polymarket/'+name,compressed_bytes=size,
            max_decoded_bytes=2147483648,day_start_ms=start,
            expected_compressed_sha256='353c3cb29bd277e84a4f614d84ac81f030df36090c430c33fb90891f8436b7f0' if date=='2026-09-08' else None))
    return r,objects


def canary(output):
    from market_rsi import digest,fresh_json,file_hash
    from preliminary_comparison import evaluate
    from typed_raw_profile import Profile
    from test_typed_raw_profile import message,T,contract
    from run_typed_raw_profile import exchange
    p=Profile(contract(),T);rows=[]
    for i,t in enumerate(range(0,240001,10000),1):
        v=.2+(.01 if i%3 else -.01);r=message(T+t,bid=str(v),ask=str(v+.02));rows.append(r)
        p.consume(json.dumps(r).encode(),i)
    expected=digest(evaluate(p,-.2));raw=b''.join((json.dumps(r)+'\n').encode() for r in rows)
    encoded=subprocess.run(['zstd','-q','-c'],input=raw,stdout=subprocess.PIPE,check=True).stdout
    spec=dict(contract=contract(),day_start_ms=T,date='synthetic',path='/__SYNTHETIC_DIRECTORY__/fixture.zst',
              compressed_bytes=len(encoded),max_decoded_bytes=len(raw),beta=-.2,synthetic_only=True)
    body=program(spec).decode()
    code=('import tempfile,pathlib,base64,json\nwith tempfile.TemporaryDirectory(prefix="market-rsi-compare-canary-") as tmp:\n'
        ' p=pathlib.Path(tmp)/"fixture.zst";p.write_bytes(base64.b64decode('+repr(base64.b64encode(encoded).decode())+'))\n'
        ' exec('+repr(body)+'.replace("/__SYNTHETIC_DIRECTORY__",tmp),{"__name__":"__main__"})\n'
        'print(json.dumps({"stage":"cleanup","temporary_directory_removed":not pathlib.Path(tmp).exists()}))\n').encode()
    output.mkdir(parents=True,exist_ok=False);r=exchange(code,output)
    if not r['complete'] or not r['temporary_directory_removed'] or digest(r['evaluation'])!=expected:
        raise ValueError('canary result or cleanup differs')
    r['program_sha256']=hashlib.sha256(code).hexdigest()
    r['sources']={p:file_hash(ROOT/p) for _,p in modules()}
    r['runner_sha256']=file_hash(__file__);fresh_json(output/'canary.json',r)
    print(json.dumps(dict(canary_passed=True,paired_rows=r['evaluation']['metrics']['n'])),flush=True)


def run(output):
    import fcntl
    import importlib.util
    import uuid
    from market_rsi import digest,file_hash,fresh_json
    from preliminary_comparison import fit,aggregate
    from run_typed_raw_profile import exchange
    with (ROOT/'artifacts/preliminary-comparison.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if output.exists():raise ValueError('fresh experiment identity required')
        published=publication();train,objects=prepare()
        receipt=ROOT/'artifacts/preliminary-comparison-canary-20260913-01/canary.json'
        evidence=json.loads(receipt.read_text())
        if not evidence['complete'] or not evidence['temporary_directory_removed'] or evidence['runner_sha256']!=file_hash(__file__):
            raise ValueError('exact current canary required')
        if any(file_hash(ROOT/p)!=s for p,s in evidence['sources'].items()):raise ValueError('canary source drift')
        output.mkdir(parents=True)
        spec=dict(schema='preliminary_comparison_spec_v1',approval='user sure: separate preliminary comparison without capture logs',
            frozen_at_utc=datetime.now(timezone.utc).isoformat(),objects=objects,train_result_sha256=TRAIN_SHA,
            train_file_sha256=file_hash(TRAIN),contract=train['spec']['contract'],publication=published,
            canary_sha256=file_hash(receipt),scope='opened historical diagnostic only',formal_experiment_activated=False)
        fresh_json(output/'spec.json',spec)
        claims=ROOT/'artifacts/preliminary-comparison-claims';claims.mkdir(exist_ok=True)
        fresh_json(claims/(TAG+'.json'),dict(output=str(output),spec_sha256=file_hash(output/'spec.json'),nonce=uuid.uuid4().hex))
        # This is the only empirical fit; later objects are not inputs to fit().
        checkpoint=fit(train['profile']['paired_moments']);checkpoint.update(train_result_sha256=TRAIN_SHA,spec_sha256=file_hash(output/'spec.json'))
        fresh_json(output/'checkpoint.json',checkpoint);checkpoint_sha=file_hash(output/'checkpoint.json')
        stages=('raw_data','raw_indicator_signal','prediction','objective','pnl')
        baseline=dict(zip(stages,('fixed_objects','rev6_past_delta','zero','equal_file_MSE','not_evaluated')))
        candidate={**baseline,'prediction':checkpoint_sha}
        validation=dict(declared_changed_stage='prediction',baseline_component_ids=baseline,candidate_component_ids=candidate,
            development_dates=['2026-08-21'],diagnostic_dates=[d for d,_ in FILES],final_test_dates=[],imputation_policy='forbidden',expected_sign=None)
        # This validator explicitly checks JSON key order, so retain its stage
        # order rather than the project's otherwise canonical sorted-key writer.
        with (output/'evaluation-spec.json').open('x') as f:
            json.dump(validation,f,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
        path=Path('/Users/estelle/.codex/skills/indicator-prediction-evals/scripts/validate_experiment_spec.py')
        module_spec=importlib.util.spec_from_file_location('evaluation_spec_validator',path);validator=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(validator)
        validator.validate_component_ids(baseline,candidate,'prediction')
        try:validator.validate(output/'evaluation-spec.json')
        except ValueError as exc:rejection=str(exc)
        else:raise ValueError('diagnostic unexpectedly promoted')
        if rejection!='final_test_dates must contain at least 20 unique sessions':
            raise ValueError('unexpected evaluation-spec validation failure')
        fresh_json(output/'pre-score-lock.json',dict(checkpoint_sha256=checkpoint_sha,spec_sha256=file_hash(output/'spec.json'),
            component_check='PASS',final_promotion='BLOCKED',reason=rejection,validator_sha256=file_hash(path),fits=1,provider_calls=0))
        reports=[]
        for obj in objects:
            if file_hash(output/'checkpoint.json')!=checkpoint_sha:raise ValueError('checkpoint mutation')
            if any(file_hash(ROOT/p)!=s for p,s in published['source_hashes'].items()):raise ValueError('source mutation')
            directory=output/obj['date'];directory.mkdir()
            item=dict(**obj,contract=spec['contract'],beta=checkpoint['beta'],checkpoint_sha256=checkpoint_sha,synthetic_only=False)
            code=program(item)
            fresh_json(directory/'claim.json',dict(spec=item,program_sha256=hashlib.sha256(code).hexdigest()))
            r=exchange(code,directory);r['report_sha256']=digest(r);fresh_json(directory/'report.json',r);reports.append(r)
            print(json.dumps(dict(date=obj['date'],complete=r['complete'],metrics=r['evaluation']['metrics'] if r['evaluation'] else None)),flush=True)
            if not r['complete']:break
        if file_hash(output/'checkpoint.json')!=checkpoint_sha or any(file_hash(ROOT/p)!=s for p,s in published['source_hashes'].items()):
            raise ValueError('post-run source/checkpoint mutation')
        summary=aggregate(reports,[d for d,_ in FILES]);summary.update(checkpoint_sha256=checkpoint_sha,fit_count=1,new_tinker_calls=0)
        summary['report_sha256']=digest(summary);fresh_json(output/'result.json',summary)
        print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--remote',action='store_true');p.add_argument('--canary',action='store_true');p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.remote:remote(SPEC)
    elif a.canary:canary(a.output.resolve())
    else:run(a.output.resolve())
