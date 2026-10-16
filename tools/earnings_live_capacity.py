"""Explicit bounded real R/H admission; no offline-to-paid fallback."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess

import earnings_entry as e
import earnings_loop_policy as policy
import edgar_live_feedback as original
from earnings_night_budget import history_snapshot, utc_epoch

SCHEMA = 'earnings_capacity_episode_v3'
ROOT = e.PILOT.parent.parent/'edgar-real-rh-20261014'/'attempts'
AUTHORIZATION = '好，按这个计划开始执行。每次小改动单独提交并验证，跑真实 R/H 共演化，证明新版本确实被下一轮使用。数据和 scorer 不变，第一批新增费用不超过 $10，计入原来的 $200 总预算。'
EGRESS = ['public_questions_and_allowed_filings', 'bounded_RH_profiles_and_candidates',
          'aggregate_feedback_and_public_grounded_state']
FIELDS = {'schema','id','root','source_commit','sources','python','data','runtime','scorer','qa','cik',
          'ledger','baseline','cutoff_utc','deadline_utc','additional_cap_nano_usd',
          'human_authorization','allowed_egress','bootstrap_no_model_call'}
_COMMITTED_SOURCES = set()  # Immutable Git object checks only, never authority/data/accounting.


def live(envelope):
    return type(envelope) is dict and envelope.get('schema') == SCHEMA and envelope.get('mode') == 'real_provider'


def sources():
    return sorted(set((*policy.capacity_sources(), *original.SOURCES,
                       'tools/earnings_live_capacity.py', 'tools/prepare_earnings_live_capacity.py', 'market_rsi/__init__.py')))


def read(binding):
    return e.strict_json(e.checked(binding).decode())


def provider_client():
    """Called only by the admitted shared owner, never by preflight."""
    return e.RawOpenAIHTTP(e.credential(),timeout=600)


def task(grant):
    """Recheck the exact original five-target public task; answers stay host-side."""
    required = {'data': {'path':str(e.PILOT/'pilot-plan.json'),'sha256':e.PLAN_HASH},
        'runtime': {'path':str(e.REPO/'benchmarks/edgar_forecast/openai_runtime.json'),'sha256':original.RUNTIME_SHA},
        'scorer': {'path':str(original.RECOVERY/'upstream-git-01/scripts/edgar_forecast_bench.py'), 'sha256':original.SCORER_SHA}}
    if any(grant[name] != value for name,value in required.items()) or grant['cik'] != 'CIK0000003545':
        raise ValueError('Original resident task/runtime/scorer bindings required')
    plan, runtime = read(grant['data']), read(grant['runtime'])
    company = next(row for row in plan['companies'] if row['cik'] == grant['cik'])
    tools = e.FilingTools(company)
    metadata = read({'path':str(original.RECOVERY/'upstream-metadata-v2.json'),'sha256':original.METADATA_SHA})
    if metadata['sha'] != original.REVISION or runtime['models']['gpt-6.1-sol'] != original.RATE:
        raise ValueError('Original dataset revision and fixed max model/rates required')
    dataset = original.RECOVERY/'upstream-git-01'
    from edgar_forecast_audit import git_blob
    def public_file(name,binding):
        if binding['path'] != str(dataset/name): raise ValueError('Original public task path required')
        data=e.checked(binding)
        row=next(row for row in metadata['siblings'] if row['rfilename']==name)
        if len(data)!=row['size'] or git_blob(data)!=row['blobId']:
            raise ValueError('Original public task bytes changed')
        return e.strict_json(data.decode()) if name.endswith('.json') else None
    manifest_name='benchmark_manifest.json'
    manifest=public_file(manifest_name, original.pin(dataset/manifest_name))
    instance=next(row for row in manifest['instances'] if row['cik']==company['cik'])
    if instance['target_accession'] != company['target_accession']: raise ValueError('Original target accession required')
    qa=public_file(instance['staged_bundle_path']+'/forecast_benchmark_qa.json',grant['qa'])
    public_file('scripts/edgar_forecast_bench.py',grant['scorer'])
    targets=re.findall(r'^### (T\d+) \|',tools.files['questions.md'],re.M)
    if targets!=['T001','T002','T003','T004','T005'] or [row['target_id'] for row in qa['targets']]!=targets:
        raise ValueError('Original five targets required')
    return company,runtime


def admit(envelope):
    """Static source/task/ledger-prefix validation; no key, owner or network."""
    if (not live(envelope) or set(envelope)!=policy.CAPACITY_FIELDS
            or type(envelope['max_rounds']) is not int or envelope['max_rounds']!=3
            or envelope['role_limits']!={'controller':policy.LIMITS,'author':policy.LIMITS,'review':policy.LIMITS}
            or any(type(v) is not int for role in envelope['role_limits'].values() for v in role.values())):
        raise ValueError('Exact baseline-plus-two-decisions live envelope required')
    grant=read(envelope['grant'])
    if (type(grant) is not dict or set(grant)!=FIELDS or grant['schema']!='earnings_real_rh_grant_v1'
            or grant['human_authorization']!=AUTHORIZATION or grant['allowed_egress']!=EGRESS
            or grant['bootstrap_no_model_call'] is not True
            or type(grant['additional_cap_nano_usd']) is not int or not 1<=grant['additional_cap_nano_usd']<=10_000_000_000
            or type(grant['id']) is not str or not re.fullmatch(r'edgar-real-rh-20261014-[0-9]{2}',grant['id'])
            or grant['root']!=str(ROOT/grant['id']) or Path(grant['root']).resolve()!=Path(grant['root'])
            or not re.fullmatch(r'[0-9a-f]{40}',grant['source_commit'])
            or any(envelope[key]!=grant[key] for key in ('id','root','source_commit','sources','cik'))
            or envelope['window']!={key:grant[key] for key in ('cutoff_utc','deadline_utc')}
            or set(grant['sources'])!=set(sources())):
        raise ValueError('Exact fresh human/data/source/resource grant required')
    cutoff,deadline=utc_epoch(grant['cutoff_utc']),utc_epoch(grant['deadline_utc'])
    if not cutoff<=deadline<=cutoff+60: raise ValueError('Original fixed cutoff and terminal grace required')
    commitment=(str(e.REPO),grant['source_commit'],tuple(sorted(grant['sources'].items())))
    for name,token in grant['sources'].items():
        if commitment not in _COMMITTED_SOURCES:
            data=subprocess.run(['git','show',grant['source_commit']+':'+name],cwd=e.REPO,check=True,capture_output=True).stdout
            if hashlib.sha256(data).hexdigest()!=token: raise ValueError('Committed live source drift')
        path=e.REPO/name
        if path.resolve()!=path or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=token:
            raise ValueError('Actual committed live source drift')
    _COMMITTED_SOURCES.add(commitment)
    if grant['python']!=original.pin(Path(e.sys.executable).absolute()): raise ValueError('Exact existing Python required')
    company,runtime=task(grant)
    study=read(envelope['study'])
    kernel={'scorer':grant['scorer'],'qa':grant['qa']}
    expected_case={key:company[key] for key in ('cik','cutoff','target_accession','visible_root')}
    expected_case.update(evaluation_kernel=kernel,allowed_manifest_sha256=e.digest(json.dumps(company['allowed_files'],sort_keys=True,separators=(',',':')).encode()))
    if (envelope['evaluation_kernel']!=kernel or study.get('schema')!='earnings_coevolution_study_v1'
            or study.get('data')!=grant['data'] or study.get('scorer')!=grant['scorer']
            or study.get('runtime_config')!=runtime or study.get('python')!=grant['python']
            or study.get('sole_ledger')!=grant['ledger'] or study.get('cases')!=[expected_case]
            or study.get('model')!={'requested_model':'gpt-6.1-sol','serving_snapshot':'unknown','serving_snapshot_verified':False}
            or read(study['prior_batch'])!={'schema':'original_runtime_snapshot_v1','source':grant['runtime'],'config':runtime}):
        raise ValueError('Fresh original-runtime study/kernel required; no old xhigh substitution')
    from earnings_research_state import ResearchState
    state=ResearchState(company,envelope['id'])
    if state.load(envelope['initial_state'])!=state.empty(): raise ValueError('Fresh empty comparable state required')
    ledger=Path(grant['ledger'])
    if ledger!=e.PILOT/'api-budget.sqlite3' or ledger.resolve()!=ledger or not ledger.is_file():
        raise ValueError('Sole existing cumulative ledger required')
    with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        if (db.execute('SELECT * FROM config').fetchall()!=[(1,200_000_000_000,100_000_000_000,0)]
                or history_snapshot(db,grant['baseline']['max_rowid'])!=grant['baseline']):
            raise ValueError('Original accounting configuration or prefix drift')
    rows=envelope['slots']
    if (type(rows) is not list or len(rows)!=3
            or any(type(row) is not dict or set(row)!={'controller','author','review','forecast'} for row in rows)):
        raise ValueError('Three exact finite role rows required')
    locations=[raw for row in rows for raw in row.values()]
    if (len(set(locations))!=len(locations) or any(type(raw) is not str or Path(raw).parent!=Path(envelope['root'])/'roles'
            or not Path(raw).is_absolute() or Path(raw).resolve()!=Path(raw) for raw in locations)):
        raise ValueError('Unique canonical new role slots required')
    return company,state
