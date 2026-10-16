"""Separate, prospective open-research admission; old paid grants stay closed."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

import earnings_live_capacity as original
from earnings_night_budget import history_snapshot, utc_epoch
from market_rsi import digest
from earnings_open_resources import role_limits

e=original.e
SCHEMA='earnings_open_episode_v1'
ROOT=e.PILOT.parent.parent/'edgar-open-research-20261014'
AUTHORIZATION='对，就按这个方向改。先给我基于现有代码的具体计划，然后执行，让外层真正能自主查文献、写代码、换算法和改工具。复用现有系统，数据和 scorer 不变，保留预算、版本和回退控制，每个改动单独提交并验证下一轮确实用上。'
EGRESS=['original_public_questions_filings_grounded_records','public_tool_trajectories_not_reasoning',
    'method_literature_metadata_or_text','model_authored_programs_and_container_outputs',
    'aggregate_feedback_not_labels']
BASELINE_CHARGED=133_562_557_700
BASELINE_ROWS=4111
PILOT_CAP=6_500_000_000
PILOT_WINDOW={'cutoff_utc':'2026-10-15T00:20:32Z','deadline_utc':'2026-10-15T00:21:32Z'}
_COMMITTED=set()


def sources():
    return sorted(set(original.sources()) | {
        str(path.relative_to(e.REPO)) for path in (e.REPO/'tools').glob('earnings_open_*.py')
    } | {str(path.relative_to(e.REPO)) for path in (e.REPO/'research/market_rsi/minimal_prediction_loop').glob('*.py')}
      | {'research/market_rsi/supervisor_harness/local_b_container.py',
         'tools/prepare_earnings_open.py','configs/earnings_coevolution/program_R0.py',
         'configs/earnings_coevolution/program_H0.py','configs/earnings_coevolution/research_followup_authority.json'})


def read(binding): return e.strict_json(e.checked(binding))


def slots(envelope, matched):
    count=envelope.get('max_rounds',2)
    if (type(count) is not int or count not in (1,2)
            or type(envelope.get('slots')) is not list or len(envelope['slots'])!=count
            or any(type(row) is not dict or set(row)!={'controller','author','review','forecast'} for row in envelope['slots'])
            or type(matched) is not dict or matched.get('schema')!='earnings_matched_plan_v1'
            or type(matched.get('rounds')) is not list or len(matched['rounds'])!=count):
        raise ValueError('Exact declared one/two-row open-program matched plan required')
    result={role:[row[role] for row in envelope['slots']] for role in ('controller','author','review')}
    result['controller'].append(str(Path(envelope['root'])/'roles'/'controller-terminal'))
    result['forecast']=[]
    for row,entry in zip(matched['rounds'],envelope['slots']):
        if set(row)!={'parent','candidate','downstream'} or row['downstream']!=entry['forecast']:
            raise ValueError('Exact original downstream plus prospective shadow slots required')
        result['forecast'].extend(row[name] for name in ('parent','candidate','downstream'))
    flat=[p for values in result.values() for p in values]
    if len(set(flat))!=len(flat) or any(type(p) is not str or str(Path(p))!=p or Path(p).resolve()!=Path(p)
            or Path(p).parent!=Path(envelope['root'])/'roles' for p in flat):
        raise ValueError('Unique canonical declared open-role slots required')
    return result


def admit(envelope):
    """No keys, Docker, provider, write or owner; recheck source/data/prefix."""
    if (type(envelope) is not dict or set(envelope)!=original.policy.CAPACITY_FIELDS
            or envelope.get('schema')!=SCHEMA or envelope.get('mode')!='real_provider'
            or type(envelope.get('max_rounds')) is not int or envelope['max_rounds'] not in (1,2)
            or envelope.get('role_limits')!=role_limits()):
        raise ValueError('Explicit finite open-program envelope required')
    grant=read(envelope['grant'])
    followup=type(grant) is dict and grant.get('schema')=='earnings_research_followup_grant_v1'
    if followup:
        from earnings_open_fresh_grant import validate,requested_rounds
        if envelope['max_rounds']!=requested_rounds(validate(grant)):
            raise ValueError('Round count must equal the exact human continuation authority')
    elif envelope['max_rounds']!=2:
        raise ValueError('Legacy open-program grants retain two rounds')
    if (type(grant) is not dict or set(grant)!=original.FIELDS
            or (not followup and (grant.get('schema')!='earnings_open_grant_v1'
                or grant.get('human_authorization')!=AUTHORIZATION or grant.get('allowed_egress')!=EGRESS
                or type(grant.get('additional_cap_nano_usd')) is not int
                or not 1<=grant['additional_cap_nano_usd']<=PILOT_CAP
                or type(grant.get('id')) is not str or not re.fullmatch(r'edgar-open-20261014-[0-9]{2}',grant['id'])
                or grant.get('root')!=str(ROOT/'attempts'/grant['id'])
                or envelope['window']!=PILOT_WINDOW))
            or grant.get('bootstrap_no_model_call') is not (not followup)
            or Path(grant['root']).resolve()!=Path(grant['root'])
            or type(grant.get('source_commit')) is not str or not re.fullmatch(r'[0-9a-f]{40}',grant['source_commit'])
            or any(envelope[k]!=grant[k] for k in ('id','root','source_commit','sources','cik'))
            or envelope['window']!={k:grant[k] for k in ('cutoff_utc','deadline_utc')}
            or set(grant['sources'])!=set(sources())):
        raise ValueError('Exact fresh open-method source/task/resource authority required')
    cutoff,deadline=utc_epoch(grant['cutoff_utc']),utc_epoch(grant['deadline_utc'])
    if not cutoff<=deadline<=cutoff+60:
        raise ValueError('Bounded original terminal grace required')
    commitment=(str(e.REPO),grant['source_commit'],tuple(sorted(grant['sources'].items())))
    for name,token in grant['sources'].items():
        if commitment not in _COMMITTED:
            raw=subprocess.run(['git','show',grant['source_commit']+':'+name],cwd=e.REPO,
                check=True,capture_output=True).stdout
            if hashlib.sha256(raw).hexdigest()!=token:
                raise ValueError('Open-program committed source drift')
        path=e.REPO/name
        if path.resolve()!=path or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=token:
            raise ValueError('Open-program actual source drift')
    _COMMITTED.add(commitment)
    if grant['python']!=original.original.pin(Path(sys.executable).absolute()):
        raise ValueError('Exact existing Python required')
    company,runtime=original.task(grant)
    study=read(envelope['study']);kernel={'scorer':grant['scorer'],'qa':grant['qa']}
    if followup and 'program_lineage' not in study:
        raise ValueError('This fresh grant requires verified adopted-source carry-forward')
    if 'program_lineage' in study:
        from earnings_open_continuation import verify
        lineage=verify(study['program_lineage'])
        selected=read(lineage['selected_version'])['manifest']
        if (selected['model']!=study['model'] or selected['runtime']['python']!=grant['python']
                or selected['components']['K']['configuration_sha256']!=digest(kernel)):
            raise ValueError('Carry-forward cannot alter protected financial/model/runtime context')
    case={key:company[key] for key in ('cik','cutoff','target_accession','visible_root')}
    case.update(evaluation_kernel=kernel,allowed_manifest_sha256=e.digest(json.dumps(company['allowed_files'],
        sort_keys=True,separators=(',',':')).encode()))
    if (envelope['evaluation_kernel']!=kernel or study.get('schema')!='earnings_coevolution_study_v1'
            or study.get('data')!=grant['data'] or study.get('scorer')!=grant['scorer']
            or study.get('runtime_config')!=runtime or study.get('python')!=grant['python']
            or study.get('sole_ledger')!=grant['ledger'] or study.get('cases')!=[case]
            or study.get('model')!={'requested_model':'gpt-6.1-sol','serving_snapshot':'unknown','serving_snapshot_verified':False}
            or read(study['prior_batch'])!={'schema':'original_runtime_snapshot_v1','source':grant['runtime'],'config':runtime}):
        raise ValueError('Original fixed financial definition/scorer/max model required')
    from earnings_research_state import ResearchState
    state=ResearchState(company,envelope['id'])
    if state.load(envelope['initial_state'])!=state.empty():
        raise ValueError('Fresh comparable empty task state required')
    ledger=Path(grant['ledger'])
    if ledger!=e.PILOT/'api-budget.sqlite3' or ledger.resolve()!=ledger or not ledger.is_file():
        raise ValueError('Sole cumulative original ledger required')
    with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        baseline=history_snapshot(db,grant['baseline']['max_rowid'] if followup else BASELINE_ROWS)
        if (db.execute('SELECT * FROM config').fetchall()!=[(1,200_000_000_000,100_000_000_000,0)]
                or baseline!=grant['baseline']
                or (not followup and (baseline['charged_nano_usd']!=BASELINE_CHARGED or baseline['request_count']!=BASELINE_ROWS))):
            raise ValueError('Original caps and already consumed pilot prefix must stay fixed')
    rows=envelope['slots']
    if (type(rows) is not list or len(rows)!=envelope['max_rounds'] or any(type(row) is not dict
            or set(row)!={'controller','author','review','forecast'} for row in rows)):
        raise ValueError('Exact declared ordinary round slots required')
    flat=[p for row in rows for p in row.values()]
    if len(set(flat))!=len(flat) or any(type(p) is not str or str(Path(p))!=p or Path(p).resolve()!=Path(p)
            or Path(p).parent!=Path(envelope['root'])/'roles' for p in flat):
        raise ValueError('Canonical role rows required')
    return company,state
