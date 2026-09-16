"""Paired three-round pilot; one dispatcher, first submissions, no score retries."""
import argparse
from datetime import datetime,timezone
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import pickle
import secrets
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'audit_tools')]
from market_rsi import fresh_json,load_json,file_hash,digest,canonical
from paid_budget import PaidBudget,money
from glm_canary import MODEL,cost
from controller_harness_contract import MAX_CUMULATIVE_INPUT_TOKENS,MAX_CUMULATIVE_OUTPUT_TOKENS
from memory_pilot.learning import BASE,read_cache,evaluate
from memory_pilot.broker import Broker,run_worker
from memory_pilot.controller import run_session,harness,TinkerGLMBackend
from data_scientist_harness.release import git,source_files

TAG='pm-memory-pilot-v0.1.0'
BUDGET=ROOT/'artifacts/kalshi-research-glm53-20260907-01/budget'
AUTH='d5bcc2d00a3b574485252693c4ba07b3a4a3ab9e083ac3bbbc1d8b30e556a8f9'
UPPER=cost(MAX_CUMULATIVE_INPUT_TOKENS,MAX_CUMULATIVE_OUTPUT_TOKENS)
INITIAL=ROOT/'artifacts/memory-train-data-20260913-01'
DEV=[('2026-08-29',16732142),('2026-08-30',13587594),('2026-08-31',36596070)]
FINAL=[('2026-09-10',18604061),('2026-09-11',25956837),('2026-09-12',26002086)]


def hashes():
    from memory_pilot.run_materialize import modules
    paths=set(source_files(ROOT))|{ROOT/p for _,p in modules()}|set((ROOT/'memory_pilot').glob('*.py'))
    paths|={ROOT/'audit_tools/run_typed_raw_profile.py',ROOT/'MEMORY_PILOT_EXECUTION_2026-09-13.md'}
    return {str(p.relative_to(ROOT)):file_hash(p) for p in sorted(paths)}


def publication():
    files=hashes();repo=ROOT.parents[1];ref='refs/tags/'+TAG
    commit=git(repo,'rev-parse',ref+'^{commit}').decode().strip()
    if git(repo,'remote','get-url','origin').decode().strip()!='https://github.com/Estelle-LH/RSIBench-Data.git':raise ValueError('wrong origin')
    names=['research/market_rsi/'+p for p in files]
    if git(repo,'status','--porcelain','--untracked-files=all','--',*names).strip():raise ValueError('dirty frozen source')
    for p,sha in files.items():
        if hashlib.sha256(git(repo,'show',commit+':research/market_rsi/'+p)).hexdigest()!=sha:raise ValueError('source not committed')
    if git(repo,'cat-file','-t',ref).decode().strip()!='tag':raise ValueError('annotated tag required')
    tag=git(repo,'rev-parse',ref).decode().strip()
    actual={v.split()[1]:v.split()[0] for v in git(repo,'ls-remote','origin',ref,ref+'^{}').decode().splitlines()}
    if actual!={ref:tag,ref+'^{}':commit}:raise ValueError('version not published')
    return dict(commit=commit,tag=TAG,tag_object=tag,source_hashes=files)


def cache_record(path,date):
    h=load_json(path/'header.json')
    record=dict(date=date,path=str(path),header_sha256=file_hash(path/'header.json'),cache_sha256=h['sha256'])
    read_cache(record)
    return record


def workspace(path,train,baseline,archive,round_number,arm,*,fixture=False):
    path.mkdir(parents=True,exist_ok=False);(path/'records').mkdir();(path/'trials').mkdir()
    qa=[]
    for r in train:
        h=load_json(Path(r['path'])/'header.json');q=h.get('quality',{})
        qa.append(dict(date=r['date'],rows=h['shape'][0],counts=q.get('counts',{}),
            feature_min=h.get('feature_minimum'),feature_max=h.get('feature_maximum'),
            target_rms_price_bps=q.get('target_rms_price_bps'),source_hash=r['cache_sha256']))
    config=dict(fixture=fixture,source_hashes=hashes(),train=train,baseline=baseline,archive=archive,
        public_context=dict(round=round_number,arm=arm,train_qa=qa,train_dates=[r['date'] for r in train],
            chronological_fit_dates=[r['date'] for r in train[:-1]],opened_train_check_date=train[-1]['date'],
            current_dev='runner-sealed until both submissions; unavailable through tools',final_test='opaque, closed',
            maximum_session_usd_not_spend=str(UPPER),maximum_three_session_arm_usd=str(3*UPPER),
            primary_final_selection='Round 3 submitted specification, refit on that rounds whole Train before Dev, then unchanged final test',
            common_findings='Earlier diagnostic gain was concentrated in two complementary outcomes of ONE market, with 40-cent median spreads. '
            'No identical full-message repeats there. Quote midpoint predictability is not executable profit. Do not delete rows or change target based on future spreads. '
            'Original capture/heartbeat provenance and quiet-versus-outage are unproven: this is an explicitly separate preliminary pilot, not formal source admission. '
            'Only fixed T12 hours are used; millions of overlapping rows are dependent.',
            supplied_research='Reuse scikit-learn1.6 common_pitfalls sections10.1-10.2: fit preprocessing only on earlier Train. '
            'TimeSeriesSplit requires chronological ordering and equally spaced rows for equal-duration folds; our irregular events use fixed date-file blocks instead. '
            'Reflexion section3 and4.2 motivate archive feedback without weight updates, not financial profitability. '
            'Model library implementations reuse prior tests of Ridge, ElasticNet, RandomForest and HistGradientBoosting; new data applicability is not established.',
            model=MODEL,component_change='features OR trainer per proposal; fixed target, weights, rows, seed, no clipping',
            operator_limit='Four initial tabular learners are an executable starting library, not every possible research method. Propose unsupported capabilities in notes; do not install during comparison.'))
    fresh_json(path/'config.json',config);return file_hash(path/'config.json')


def arm_cost(snapshot,prefix):
    jobs={k:v for k,v in snapshot['jobs'].items() if k.startswith(prefix+'-turn-')}
    metered=sum((money(v.get('metered_usd') or 0) for v in jobs.values()),money(0))
    uncertain=sum((money(v.get('uncertain_upper_usd') or 0) for v in jobs.values()),money(0))
    outstanding=sum((money(v['upper_usd']) for v in jobs.values() if v['state'] in ('reserved','dispatched')),money(0))
    return dict(metered_usd=str(metered),uncertain_upper_usd=str(uncertain),outstanding_usd=str(outstanding),turns=len(jobs))


def later_data(root,date,size,role,commitments):
    """Only coordinator calls this after both candidate commitments are present."""
    from memory_pilot.run_materialize import modules
    from run_typed_raw_profile import exchange
    heldout_gate(root,date,role,commitments)
    for c in commitments:
        if file_hash(c['path'])!=c['sha256']:raise ValueError('submission changed before held-out access')
    output=root/'data'/date;output.mkdir(parents=True,exist_ok=False)
    contract=load_json(INITIAL/'2026-08-26/report.json')['spec']['contract']
    remote_path='/opt/d10/derived/'+root.name+'/'+date
    spec=dict(date=date,path='/opt/d10/raw/data/polymarket/polymarket-'+date.replace('-','')+'T12.jsonl.zst',
        output=remote_path,compressed_bytes=size,contract=contract,role=role,
        day_start_ms=int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp()*1000),commitments=commitments)
    fresh_json(output/'exposure-claim.json',spec)
    code='import types,sys\n'
    for name in ('quote_source','data_scientist_harness'):
        code+='m=types.ModuleType('+repr(name)+');m.__path__=[];sys.modules[m.__name__]=m\n'
    for name,path in modules():
        code+='m=types.ModuleType('+repr(name)+');m.__file__='+repr(path)+';sys.modules[m.__name__]=m\n'
        code+='exec('+repr((ROOT/path).read_text())+',m.__dict__)\n'
    code+='SPEC='+repr(spec)+'\n'+(ROOT/'memory_pilot/heldout_worker.py').read_text()
    r=exchange(code.encode(),output);fresh_json(output/'report.json',r)
    if not r['complete']:raise ValueError('held-out source failed; no replacement or score retry')
    p=subprocess.run(['scp','-o','BatchMode=yes','-o','ConnectTimeout=10',
        'root@173.255.231.4:'+remote_path+'/rows.f64',str(output/'rows.f64')],capture_output=True,timeout=180)
    fresh_json(output/'transfer.json',dict(exit_code=p.returncode,process_reaped=True))
    if p.returncode or file_hash(output/'rows.f64')!=r['header']['sha256']:raise ValueError('held-out cache transfer failed')
    fresh_json(output/'header.json',r['header']);return cache_record(output,date)


def heldout_gate(root,date,role,commitments):
    root=Path(root)
    if role not in ('dev','final') or len(commitments)!=2 or len({c['path'] for c in commitments})!=2:
        raise ValueError('two distinct submissions required before data access')
    for c in commitments:
        if file_hash(c['path'])!=c['sha256']:raise ValueError('submission changed before held-out access')
    if role=='dev':
        dates=[d for d,_ in DEV]
        if date not in dates:raise ValueError('Dev date not predeclared')
        freeze=load_json(root/f'round-{dates.index(date)+1}'/'paired-freeze.json')
    else:
        if date not in [d for d,_ in FINAL]:raise ValueError('final date not predeclared')
        for i in range(1,4):
            if not load_json(root/f'round-{i}'/'promotion-to-train.json')['consumed']:
                raise ValueError('three completed paired rounds required')
        freeze=load_json(root/'final-model-freeze.json')
    if freeze['commitments']!=commitments or set(freeze['models'])!={'archive','independent','baseline'}:
        raise ValueError('paired model/submission freeze missing')


def study(root,canary_path,env_file,tokenizer_cache):
    root=Path(root)
    with (ROOT/'artifacts/historical-ingest-controller.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if root.exists():raise ValueError('permanent study ID already used; no duplicate/retry')
        pub=publication();canary=load_json(canary_path)
        if (not canary['passed'] or canary['source_hashes']!=pub['source_hashes'] or canary['actual_tinker_calls']!=0
                or canary['codex_sha256']!=file_hash(harness.CODEX) or canary['python_sha256']!=file_hash(sys.executable)):
            raise ValueError('same-source/runtime actual Codex canary required')
        for k,v in {'numpy':'1.26.4','scipy':'1.14.0','scikit-learn':'1.6.1','tinker':'0.25.0'}.items():
            if importlib.metadata.version(k)!=v:raise ValueError('pinned runtime differs: '+k)
        if file_hash(BUDGET/'authorization.json')!=AUTH:raise ValueError('original authorization changed')
        budget=PaidBudget(BUDGET);before=budget.snapshot()
        if money(before['cap_usd'])!=money(200) or any(v['state']=='dispatched' and '-turn-' in k for k,v in before['jobs'].items()):
            raise ValueError('budget or active provider dispatch gate')
        if min(money(before['available_usd']),money(before['buckets']['learning']['available_usd']))<6*UPPER:
            raise ValueError('six-session worst case does not fit available learning budget')
        initial=load_json(INITIAL/'complete.json')
        if not initial['complete'] or [r['date'] for r in initial['files']]!=['2026-08-26','2026-08-27','2026-08-28']:
            raise ValueError('all initial Train files required')
        train=[cache_record(INITIAL/r['date'],r['date']) for r in initial['files']]
        root.mkdir(parents=True);(root/'data').mkdir()
        fresh_json(root/'claim.json',dict(publication=pub,canary_sha256=file_hash(canary_path),nonce=secrets.token_hex(16),pid=os.getpid(),
            original_authorization_sha256=AUTH,budget_before=before,initial=train,dev=DEV,final=FINAL,
            session_cap_usd=str(UPPER),arm_cap_usd=str(3*UPPER),max_study_usd_not_spend=str(6*UPPER),
            final_selection='Round3 submitted, no hindsight best selection',study_kind='preliminary archive-memory pilot'))
        from dotenv import dotenv_values
        backend=TinkerGLMBackend(dotenv_values(env_file).get('TINKER_API_KEY'),tokenizer_cache)
        histories={'archive':[],'independent':[]};costs={'archive':[],'independent':[]};last_models={};last_commitments=[]
        try:
            for round_number,(date,size) in enumerate(DEV,1):
                if hashes()!=pub['source_hashes']:raise ValueError('study source mutated')
                rd=root/f'round-{round_number}';rd.mkdir()
                baseline=run_worker(dict(plan=BASE,train=train[:-1],check=train[-1:]),rd/'common-baseline-check')
                if not baseline['success']:raise ValueError('common baseline infrastructure failed')
                sessions={};commitments=[]
                # Alternating order is predeclared; no performance-dependent scheduling.
                for arm in (('archive','independent') if round_number%2 else ('independent','archive')):
                    prior=sum((money(c['metered_usd'])+money(c['uncertain_upper_usd'])+money(c['outstanding_usd']) for c in costs[arm]),money(0))
                    now=budget.snapshot()
                    if prior+UPPER>3*UPPER or min(money(now['available_usd']),money(now['buckets']['learning']['available_usd']))<UPPER:
                        raise ValueError('atomic session exceeds remaining arm/global budget')
                    session=root/(root.name+'-'+arm+f'-r{round_number:02d}')
                    manifest=workspace(session,train,baseline,histories[arm] if arm=='archive' else [],round_number,arm)
                    fresh_json(session/'dispatch-claim.json',dict(manifest_sha256=manifest,publication=pub,
                        canary_sha256=file_hash(canary_path),session_upper_not_spend=str(UPPER),nonce=secrets.token_hex(16)))
                    print(canonical(dict(stage='controller_started',round=round_number,arm=arm,path=str(session))),flush=True)
                    assessment=run_session(session,backend,budget)
                    costs[arm].append(arm_cost(budget.snapshot(),session.name))
                    fresh_json(session/'cost.json',costs[arm][-1])
                    submission=load_json(session/'submission.json')
                    sessions[arm]=session;commitments.append(dict(path=str(session/'submission.json'),sha256=file_hash(session/'submission.json')))
                    print(canonical(dict(stage='controller_complete',round=round_number,arm=arm,trial=submission['trial_id'],cost=costs[arm][-1])),flush=True)
                # Both submissions are now immutable. Refit on whole opened Train BEFORE Dev access.
                for arm,session in sessions.items():
                    chosen=load_json(session/'submission.json')['plan']
                    fitted=run_worker(dict(plan=chosen,train=train,check=[]),rd/(arm+'-refit'))
                    if not fitted['success']:raise ValueError('selected refit failed; do not replace model')
                    last_models[arm]=rd/(arm+'-refit')
                common=run_worker(dict(plan=BASE,train=train,check=[]),rd/'common-baseline-refit')
                if not common['success']:raise ValueError('baseline refit failed')
                last_models['baseline']=rd/'common-baseline-refit'
                fresh_json(rd/'paired-freeze.json',dict(commitments=commitments,models={a:file_hash(d/'model.pkl') for a,d in last_models.items()}))
                dev=later_data(root,date,size,'dev',commitments)
                scores={}
                for arm,d in last_models.items():
                    r=load_json(d/'result.json')
                    if file_hash(d/'model.pkl')!=r['checkpoint_sha256']:raise ValueError('owned model changed')
                    with (d/'model.pkl').open('rb') as f:model=pickle.load(f)
                    scores[arm]=evaluate(model,dev,rd/(arm+'-dev-predictions.npy'))
                fresh_json(rd/'dev-scores.json',scores)
                for arm,session in sessions.items():
                    histories[arm].append(dict(round=round_number,records=Broker(session,file_hash(session/'config.json')).records(),
                        submission=load_json(session/'submission.json'),own_dev={k:v for k,v in scores[arm].items() if k!='market_scores'},
                        common_baseline_dev={k:v for k,v in scores['baseline'].items() if k!='market_scores'},cost=costs[arm][-1]))
                fresh_json(rd/'promotion-to-train.json',dict(dev=dev,paired_submission_commitments=commitments,consumed=True))
                train.append(dev);last_commitments=commitments
                print(canonical(dict(stage='round_complete',round=round_number,dev_date=date,mse={a:s['candidate_mse'] for a,s in scores.items()})),flush=True)
            fresh_json(root/'final-model-freeze.json',dict(commitments=last_commitments,models={a:file_hash(d/'model.pkl') for a,d in last_models.items()},
                source_hashes=pub['source_hashes'],selection='Round3 submissions; no further model dispatch'))
            final=[]
            for date,size in FINAL:
                record=later_data(root,date,size,'final',last_commitments);scores={}
                for arm,d in last_models.items():
                    if file_hash(d/'model.pkl')!=load_json(d/'result.json')['checkpoint_sha256']:raise ValueError('final model changed')
                    with (d/'model.pkl').open('rb') as f:model=pickle.load(f)
                    scores[arm]=evaluate(model,record,root/(arm+'-final-'+date+'.npy'))
                fresh_json(root/('final-'+date+'.json'),scores);final.append(scores)
            report=dict(complete=True,rounds=3,final_dates=[d for d,_ in FINAL],final_mse={a:sum(s[a]['candidate_mse'] for s in final)/len(final) for a in last_models},
                zero_mse=sum(s['baseline']['baseline_mse'] for s in final)/len(final),costs=costs,
                publication=pub,pilot_only=True,formal_promotion=False,pnl_measured=False,source_unchanged=hashes()==pub['source_hashes'])
            fresh_json(root/'complete.json',report);print(canonical(report),flush=True)
        except BaseException as exc:
            fresh_json(root/'failure.json',dict(type=type(exc).__name__,message=str(exc)[:800],budget_after=budget.snapshot(),
                no_automatic_retry=True,partial_outcomes_preserved=True))
            raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--canary',type=Path,required=True)
    p.add_argument('--env-file',type=Path,required=True);p.add_argument('--tokenizer-cache',type=Path,required=True)
    a=p.parse_args();study(a.output.resolve(),a.canary.resolve(),a.env_file.resolve(),a.tokenizer_cache.resolve())
