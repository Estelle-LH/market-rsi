"""Opt-in reviewed population admission; shared owner/transport stay unchanged."""
from contextlib import closing
import inspect
from pathlib import Path
import re
import sqlite3
import subprocess
import time

import earnings_capacity_runtime as owner
import earnings_entry as e
import earnings_population as pool
import earnings_population_tasks as tasks
from earnings_night_budget import history_snapshot, utc_epoch
from earnings_open_resources import ROLE_EFFORTS, role_limits
from edgar_forecast_budget import BudgetStop
from market_rsi import digest

ROOT = tasks.ARTIFACTS / 'edgar-population-20261016'
PLAN = 'configs/earnings_coevolution/population_restore_plan.json'
CONTINUATION_PLAN = 'configs/earnings_coevolution/population_continue_plan.json'
CONTINUATION_AUTHORIZATION = '继续把这两块补上，先给具体计划再执行。让解析失败的诊断自动进入下一轮，让 Author 自己修复；支持跨窗口继承版本池和反馈，再用新公司验证。数据、scorer 和原 $200 总预算不变，不动其他 Supervisor。'
AUTHORIZATION = '那就基于现有代码把这套机制恢复起来，先给具体计划再执行。保留一个稳定主版本和最多两个探索分支，让反馈自动进入下一轮，用新公司验证是否真的进步。数据、scorer 和原 $200 总预算不变，不动其他 Supervisor。'
EXTRA_BASELINE = {'max_rowid': 4283, 'request_count': 4283,
    'charged_nano_usd': 137542765000,
    'rows_sha256': '7ee9ae3ce1b56ddcd8972f58d40447b83082cf6f7a777a888b1ea22ec5ee5da8'}
EXTRA_CAP = 50_000_000_000
FIELDS = owner.FIELDS | {'forecast_study', 'role_efforts', 'population_plan',
    'initial_population', 'companies', 'original_extra_baseline',
    'original_extra_cap_nano_usd', 'review'}
ROLES = {'controller', 'author', 'review', 'forecast'}
_COMMITTED = set()


def source_paths():
    from earnings_open_admission import sources
    paths = set(sources()) | {str(p.relative_to(e.REPO))
        for p in (e.REPO / 'tools').glob('earnings_population*.py')} | {PLAN, CONTINUATION_PLAN}
    result = {name: str(e.REPO / name) for name in paths}
    result.update({name: str(Path(path).resolve()) for name, path in owner.CORE.items()})
    result.update(forecast_entry=str(Path(e.__file__).resolve()),
                  forecaster=str(Path(inspect.getsourcefile(e.forecast)).resolve()))
    result.update({'factory_' + role: str(e.REPO / 'tools/earnings_population_services.py')
                   for role in ROLES})
    return result


def _git_source(commit, name):
    return subprocess.run(['git', 'show', commit + ':' + name], cwd=e.REPO,
                          check=True, capture_output=True).stdout


def _sources(value):
    expected = source_paths()
    if type(value['sources']) is not dict or set(value['sources']) != set(expected):
        raise ValueError('Exact complete population source set required')
    commitment = (str(e.REPO), value['source_commit'], digest(value['sources']))
    for name, path in expected.items():
        bound = value['sources'][name]
        if type(bound) is not dict or bound.get('path') != path:
            raise ValueError('Population core/factory source substituted')
        raw = owner._read(bound)
        if commitment not in _COMMITTED:
            relative = str(Path(path).relative_to(e.REPO))
            if _git_source(value['source_commit'], relative) != raw:
                raise ValueError('Population committed source differs from current files')
    _COMMITTED.add(commitment)


def _local(bound):
    if type(bound) is not dict or type(bound.get('path')) is not str:
        raise ValueError('Exact own-population artifact binding required')
    if not Path(bound['path']).is_relative_to(ROOT):
        raise ValueError('Population input outside owned artifact root')
    return e.strict_json(owner._read(bound))


def _baseline(value):
    if (type(value) is not dict or set(value) != set(EXTRA_BASELINE)
            or any(type(value[k]) is not int or value[k] < 0
                   for k in ('max_rowid', 'request_count', 'charged_nano_usd'))
            or type(value['rows_sha256']) is not str
            or not re.fullmatch(r'[0-9a-f]{64}', value['rows_sha256'])):
        raise ValueError('Exact frozen original accounting prefix required')


def _ledger_checks(db, value, original=EXTRA_BASELINE):
    if (db.execute('SELECT * FROM config').fetchall()
            != [(1, 200_000_000_000, 100_000_000_000, 0)]
            or history_snapshot(db, original['max_rowid']) != original
            or history_snapshot(db, value['baseline']['max_rowid']) != value['baseline']
            or value['baseline']['max_rowid'] < original['max_rowid']):
        raise BudgetStop('Original accounting configuration or consumed prefix changed')
    rows = db.execute('SELECT model,reserved,charged,status FROM requests').fetchall()
    if any(type(n) is not int or n < 0 for row in rows for n in row[1:3]):
        raise BudgetStop('Invalid cumulative accounting values')
    total, models = 0, {}
    for model, reserved, charged, status in rows:
        amount = charged + (reserved if status not in ('settled', 'settled_upper_bound') else 0)
        total += amount
        models[model] = models.get(model, 0) + amount
    if (total > 200_000_000_000 or any(amount > 100_000_000_000 for amount in models.values())
            or total > original['charged_nano_usd'] + EXTRA_CAP
            or total > value['baseline']['charged_nano_usd'] + value['additional_cap_nano_usd']):
        raise BudgetStop('Population global/model/original-extra/tranche ceiling exceeded')


def _ledger(value):
    if value['ledger'] != str(e.PILOT / 'api-budget.sqlite3'):
        raise ValueError('Sole original cumulative ledger required')
    path = owner._path(value['ledger'], file=True)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('BEGIN')
        _ledger_checks(db, value)


def _study(value):
    if (value['population_plan'] != value['sources'][PLAN]
            or value['population_plan']['path'] != str(e.REPO / PLAN)):
        raise ValueError('Exact committed population plan source required')
    plan = e.strict_json(owner._read(value['population_plan']))
    if (plan.get('schema') != 'supervisor_bottleneck_plan_v1'
            or plan.get('id') != 'earnings-population-restore-20261016'
            or plan.get('human_authorization') != AUTHORIZATION):
        raise ValueError('Exact committed current human population authorization required')
    state = pool.validate(_local(value['initial_population']))
    companies = value['companies']
    if (type(companies) is not list or not 1 <= len(companies) <= 2
            or companies != tasks.select_companies(set(state['exposed_companies']) | {'CIK0000003545'}, len(companies))):
        raise ValueError('Exact next one/two resident-plan companies required')
    residents = [tasks.resident(cik) for cik in companies]
    study = _local(value['forecast_study'])
    original = residents[0]['runtime']
    if (study.get('schema') != 'earnings_coevolution_study_v1' or 'new_live_grant' in study
            or study.get('model') != {'requested_model': 'gpt-6.1-sol', 'serving_snapshot': 'unknown',
                                    'serving_snapshot_verified': False}
            or study.get('data') != tasks.FULL_PLAN or study.get('scorer') != tasks.SCORER
            or study.get('sole_ledger') != value['ledger'] or study.get('runtime_config') != original
            or study.get('cases') != [r['case'] for r in residents]
            or _local(study['prior_batch'])
                != {'schema': 'original_runtime_snapshot_v1', 'source': tasks.RUNTIME, 'config': original}
            or state['protected']['K'] != digest({'data': tasks.FULL_PLAN, 'scorer': tasks.SCORER})
            or value['rates'] != original['models']['gpt-6.1-sol']):
        raise ValueError('Original full50/scorer/model/runtime/company kernel changed')
    if study.get('continuation') is not None:
        from earnings_population_continuation import load
        continued = _local(study['continuation'])
        inherited = load(continued['previous_result'], root=ROOT,
            ledger=Path(value['ledger']), repo=e.REPO)
        if (set(continued) != {'schema', 'previous_result', 'population_sha256', 'feedback', 'evidence', 'plan', 'repair'}
                or continued['schema'] != 'earnings_population_continuation_v1'
                or continued['plan'] != value['sources'].get(CONTINUATION_PLAN)
                or continued['population_sha256'] != digest(state) or state != inherited['population']
                or continued['feedback'] != inherited['feedback'] or continued['evidence'] != inherited['evidence']):
            raise ValueError('Exact completed pool/history/last feedback continuation required')
        plan = e.strict_json(owner._read(continued['plan']))
        if (plan.get('schema') != 'supervisor_bottleneck_plan_v1'
                or plan.get('id') != 'earnings-population-continuation-20261016'
                or plan.get('human_authorization') != CONTINUATION_AUTHORIZATION):
            raise ValueError('Exact committed human continuation plan required')
        repair = continued['repair']
        if repair is not None and (type(repair) is not dict
                or set(repair) != {'schema', 'parent_version_id', 'human_authorization'}
                or repair['schema'] != 'earnings_population_human_repair_v1'
                or repair['parent_version_id'] not in state['explorers']
                or repair['human_authorization'] != CONTINUATION_AUTHORIZATION):
            raise ValueError('Explicit human R repair must bind an actual inherited explorer')
    elif state['observations']:
        raise ValueError('Nonempty history cannot be silently reset without a continuation binding')
    return original


def preflight(binding, *, require_review=True):
    value = _local(binding)
    if (type(value) is not dict or set(value) != FIELDS
            or value.get('schema') != 'earnings_population_runtime_v1'
            or value['purpose'] != 'capacity_episode'
            or type(value['id']) is not str or not re.fullmatch(r'edgar-population-20261016-[0-9]{2}', value['id'])
            or type(value['source_commit']) is not str or not re.fullmatch(r'[0-9a-f]{40}', value['source_commit'])
            or value['root'] != str(ROOT / 'attempts' / value['id'])
            or owner._path(value['root']) != ROOT / 'attempts' / value['id']
            or value['role_efforts'] != ROLE_EFFORTS
            or value['original_extra_baseline'] != EXTRA_BASELINE
            or value['original_extra_cap_nano_usd'] != EXTRA_CAP
            or type(value['additional_cap_nano_usd']) is not int
            or not 1 <= value['additional_cap_nano_usd'] <= 5_000_000_000):
        raise ValueError('Exact reviewed bounded population runtime authority required')
    _baseline(value['baseline'])
    cutoff, deadline = utc_epoch(value['cutoff_utc']), utc_epoch(value['deadline_utc'])
    if not time.time() < cutoff <= time.time() + 5400 or not cutoff <= deadline <= cutoff + 60:
        raise BudgetStop('Population fixed ninety-minute send window or terminal grace invalid')
    _sources(value)
    original = _study(value)
    limits = dict(role_limits(), forecast={'max_input_tokens': original['max_input_tokens'],
        'max_output_tokens': original['max_output_tokens'], 'wall_seconds': original['company_wall_seconds']})
    if (value['limits'] != limits or any(type(n) is not int for row in value['limits'].values() for n in row.values())
            or type(value['slots']) is not dict or set(value['slots']) != ROLES):
        raise ValueError('Original exact population role resources required')
    seen = set()
    for role, slots in value['slots'].items():
        if type(slots) is not list or not 1 <= len(slots) <= (6 if role == 'forecast' else 3):
            raise ValueError('Bounded declared population role slots required')
        for slot in slots:
            if owner._path(slot).parent != Path(value['root']) / 'roles' or slot in seen:
                raise ValueError('Unique own-root population role slots required')
            seen.add(slot)
    _ledger(value)
    if require_review:
        review = _local(value['review'])
        if (review.get('verdict') != 'PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY'
                or type(review.get('reviewer')) is not str or not review['reviewer'].strip()
                or review['reviewer'].strip().lower() in {'root', '/root'}
                or review.get('blocking_findings') != [] or type(review['blocking_findings']) is not list
                or review.get('source_commit') != value['source_commit']
                or review.get('reviewed_configuration_sha256') != digest({k: v for k, v in value.items() if k != 'review'})):
            raise ValueError('Exact independent population runtime configuration review required')
    return value
