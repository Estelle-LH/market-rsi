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
import earnings_population_window as window
from earnings_night_budget import history_snapshot
from earnings_open_resources import ROLE_EFFORTS, role_limits, population_role_limits, review_input_policy
from edgar_forecast_budget import BudgetStop
from market_rsi import digest

ROOT = tasks.ARTIFACTS / 'edgar-population-20261016'
PLAN = 'configs/earnings_coevolution/population_restore_plan.json'
CONTINUATION_PLAN = 'configs/earnings_coevolution/population_continue_plan.json'
CAMPAIGN_PLAN = 'configs/earnings_coevolution/population_campaign_plan.json'
RESUME_PLAN = 'configs/earnings_coevolution/population_resume03_plan.json'
BUDGET_PLAN = 'configs/earnings_coevolution/population_400_plan.json'
AFTER04_PLAN = 'configs/earnings_coevolution/population_after04_delivery_plan.json'
RECOVERY_PLAN = 'configs/earnings_coevolution/population_recovery_plan.json'
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
PROPOSAL_POLICY = 'round0_new_panel_candidate_v1'
PROPOSAL_AUTHORITY = dict(path=str(ROOT/'TRAIN25-DIRECT-NEW-CANDIDATE-AUTHORITY.json'),
    sha256='4aa5c123d6ab86c65673abd9502d7e59a9cd88cb5e6031016d9192c1b71933df')
PROPOSAL_ROUND0 = dict(path=str(ROOT/'TRAIN25-PLAIN-COMPARATOR-MANIFEST.json'),
    sha256='7a43ee9cac7204ef664d134c2e5effac14e2422aa9cedc207f66fcfe55ef07a3')
PROPOSAL_ORIGIN = dict(path=str(ROOT/'attempts/edgar-population-20261016-36/population-run-result.json'),
    sha256='15f7081a3463219c4fdd1ad9b79d0dfb4fb99953d56d8df4ba7354e12e8aa82b')
PROPOSAL_PRIMARY_TASK = ('One fresh transferable R/H method informed by all125 original Round0 public '
    'prediction/award pairs; success decided by same frozen code across all25, no per-company mutation. '
    'Diagnose common failure patterns, investigate literature and available tools, and deliver a testable '
    'new method. Old34–36 are archive references only; current-company tests are integration smoke. '
    'Do not force adoption or promise score gain.')
PROPOSAL_ARCHIVES = ['1167a7efab99330677db3a80690bd44a6f17d1e77120f90f2b182771ad2f3b33',
    '3392fd6008ee9dd1ce779d3c27a8cd0283209659b664d25db3681767211bd6b9']


def source_paths(*, model_budget=False, training=False, clean_slate=False, clean_round2=False, clean_followup=None):
    from earnings_open_admission import sources
    paths = set(sources()) | {str(p.relative_to(e.REPO))
        for p in (e.REPO / 'tools').glob('earnings_population*.py')} | {PLAN, CONTINUATION_PLAN, CAMPAIGN_PLAN, RESUME_PLAN, BUDGET_PLAN, AFTER04_PLAN, RECOVERY_PLAN}
    if model_budget:
        from earnings_population_model_budget import PLAN as model_plan, IMPLEMENTATIONS
        paths.update({model_plan, *IMPLEMENTATIONS})
        from earnings_population_additional_budget import PLAN as additional_plan
        paths.add(additional_plan)
    if training:
        from earnings_population_training25 import PLAN as training_plan
        paths.add(training_plan)
    if clean_slate:
        from earnings_population_clean_slate import PLAN as clean_plan
        paths.update({clean_plan,'tools/earnings_native_failure.py'})
    if clean_round2:
        if not clean_slate:raise ValueError('Round2 requires explicit clean adapter')
        from earnings_population_clean_slate import ROUND2_PLAN
        paths.add(ROUND2_PLAN)
    if clean_followup is not None:
        from earnings_population_coevolution import followup_round
        if not clean_slate or clean_round2 or not followup_round(clean_followup):
            raise ValueError('Exact directly authorized followup source plan required')
        from earnings_population_clean_slate import followup_plan
        paths.add(followup_plan(clean_followup))
        if clean_followup>=14:
            from earnings_population_coevolution import PROVISIONAL_PLAN
            paths.add(PROVISIONAL_PLAN)
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
    if 'training_policy' in value:
        options = {'clean_slate': True} if 'clean_slate_policy' in value else {}
        if value.get('clean_learning_round')==2:options['clean_round2']=True
        from earnings_population_coevolution import followup_round
        if followup_round(value.get('clean_learning_round')):options['clean_followup']=value['clean_learning_round']
        expected = source_paths(model_budget='model_budget_amendment' in value,training=True,**options)
    else:
        expected = source_paths(model_budget=True) if 'model_budget_amendment' in value else source_paths()
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


def _proposal_expected(scope, company):
    from copy import deepcopy
    from earnings_population_training25 import admit
    admit(scope,company)
    return dict(schema='earnings_training25_new_panel_proposal_task_v1',policy=PROPOSAL_POLICY,
        authority=deepcopy(PROPOSAL_AUTHORITY),split=deepcopy(scope['split']),round0_manifest=deepcopy(PROPOSAL_ROUND0),
        training_companies=deepcopy(scope['training']),primary_task=PROPOSAL_PRIMARY_TASK,
        smoke_company_id=company,smoke_only=True,archive_only_version_ids=deepcopy(PROPOSAL_ARCHIVES))


def _proposal_prefix_metadata(value, study, *, company_id):
    """Current-ID failed37 receipt metadata, never historical admission itself."""
    key='proposal_prefix_reuse';directory=ROOT/'inputs'/value['id']
    if not (key in value or key in study or (directory/'proposal-prefix-reuse.json').exists()):return None
    from earnings_open_resources import REVIEW200_POLICY
    from earnings_population_campaign import _training_input
    from earnings_population_training25 import load_scope,admit
    from earnings_population_proposal_completed import (FAILED37,FAILED37_AUTHORITY,
        FAILED37_MODE,FAILED37_SCHEMA,failed37_policy)
    if (key not in value or key not in study or value[key]!=study[key]
            or value.get('training_proposal_policy')!=PROPOSAL_POLICY or 'training_policy' not in value
            or review_input_policy(value)!=REVIEW200_POLICY or value.get('companies')!=[company_id]
            or 'training_stage_attachment' in study or 'frozen_panel_policy' in value):
        raise ValueError('Exact companion failed37/Review200k proposal markers required')
    _training_input(study.get('training_state_link'),'training-state-link.json',directory=directory)
    link=_local(study['training_state_link']);scope=load_scope(link['split']);admit(scope,company_id)
    policy=failed37_policy(value['id'],company_id=company_id)
    _training_input(value[key],'proposal-prefix-reuse.json',directory=directory)
    receipt=_local(value[key])
    fields={'schema','mode','policy','consumer_attempt_id','company_id','failed_attempt','authority',
        'completed_origin','base_origin','task','candidate','parent','original_decision','scientific_decision',
        'author_stage_reuse','review_assessment','original_completed_generations','evidence'}
    if (type(receipt) is not dict or set(receipt)!=fields or receipt.get('schema')!=FAILED37_SCHEMA
            or receipt.get('mode')!=FAILED37_MODE or receipt.get('policy')!=policy
            or receipt.get('consumer_attempt_id')!=value['id'] or receipt.get('company_id')!=company_id
            or receipt.get('failed_attempt')!=FAILED37 or receipt.get('authority')!=FAILED37_AUTHORITY
            or receipt.get('completed_origin')!=PROPOSAL_ORIGIN
            or any(type(receipt.get(k)) is not dict for k in ('base_origin','candidate','parent','author_stage_reuse'))
            or receipt['base_origin'].get('previous_result')!=PROPOSAL_ORIGIN
            or any(receipt['base_origin'].get(k) is not None for k in ('author_stage_reuse','review_stage_reuse'))
            or receipt.get('task')!=_proposal_expected(scope,company_id)
            or receipt.get('review_assessment')!='not_completed'
            or receipt.get('original_completed_generations')!={'controller':8,'author':8,'review':4}
            or receipt['author_stage_reuse'].get('failed_attempt')!=FAILED37
            or receipt['author_stage_reuse'].get('candidate')!=receipt['candidate']
            or receipt['author_stage_reuse'].get('decision')!=receipt['original_decision']
            or receipt['author_stage_reuse'].get('scientific_decision')!=receipt['scientific_decision']
            or receipt['candidate'].get('parent')!=receipt['parent'].get('id')
            or any(receipt['author_stage_reuse'].get(k) is not False for k in
                ('new_model_Controller_called','new_model_Author_called'))):
        raise ValueError('Exact authenticated37 prefix identity required before original replay')
    return receipt


def _proposal_metadata(value, study):
    """Typed current task only; caller still owes original full preflight."""
    directory=ROOT/'inputs'/value['id']; marker='training_proposal_policy'; task_key='training_proposal_task'
    if not (marker in value or task_key in study or 'proposal_prefix_reuse' in value
            or 'proposal_prefix_reuse' in study or (directory/'training-proposal-task.json').exists()
            or (directory/'proposal-prefix-reuse.json').exists()):return None
    if (value.get(marker) != PROPOSAL_POLICY or task_key not in study or marker not in value
            or 'training_policy' not in value or value.get('budget_amendment') is None
            or value.get('model_budget_amendment') is None or window.minutes(value) != 90
            or type(value.get('companies')) is not list or len(value['companies']) != 1
            or value.get('additional_cap_nano_usd') != 5_000_000_000
            or any(k in value for k in ('frozen_panel_policy','panel_window_budget_authority'))
            or 'training_stage_attachment' in study or study.get('continuation') is not None):
        raise ValueError('Exact new whole25 proposal-only training markers required')
    from earnings_population_campaign import _training_input
    from earnings_population_training25 import load_scope, admit
    _training_input(study.get('training_state_link'),'training-state-link.json',directory=directory)
    link=_local(study['training_state_link']);scope=load_scope(link['split'])
    company=admit(scope,value['companies'][0])  # BEFORE task/ancestor bodies.
    _training_input(study[task_key],'training-proposal-task.json',directory=directory)
    authority=_local(PROPOSAL_AUTHORITY)
    if authority.get('human_answer') != '让 Author 根据完整25家公司 Round0反馈提出新候选，旧34–36仅归档参考':
        raise ValueError('Exact direct new-candidate authority required')
    task=_local(study[task_key])
    if task != _proposal_expected(scope,company) or link.get('comparator') != PROPOSAL_ROUND0:
        raise ValueError('Original whole25 Round0 proposal task differs')
    _proposal_prefix_metadata(value,study,company_id=company)
    origin=_local(study['campaign_origin'])
    if origin.get('previous_result') != PROPOSAL_ORIGIN or origin.get('author_stage_reuse') is not None:
        raise ValueError('Fresh proposal must inherit authentic36 without reusing old stages')
    return task


def proposal_task(value):
    return _proposal_metadata(value,_local(value['forecast_study']))


def _panel_metadata(value, study):
    """Current metadata only; original full admission authenticates its origin."""
    keys = {'frozen_panel_policy', 'frozen_panel', 'frozen_panel_window'}
    directory = ROOT/'inputs'/value['id']
    if not (keys & set(value) or keys & set(study) or (directory/'frozen-panel-window.json').exists()):
        return None
    from earnings_population_frozen_panel import POLICY, SCHEMA, ARMS
    from earnings_population_training25 import load_scope, admit
    from earnings_population_campaign import _training_input
    if (not keys <= set(value) or not keys <= set(study)
            or any(value[k] != study[k] for k in keys)
            or type(value['frozen_panel_policy']) is not str or value['frozen_panel_policy'] != POLICY
            or 'training_policy' not in value or value.get('model_budget_amendment') is None
            or value.get('budget_amendment') is None or window.minutes(value) != 90
            or type(value.get('companies')) is not list or len(value['companies']) != 1
            or study.get('training_stage_attachment') is not None):
        raise ValueError('Exact companion frozen-panel training markers required')
    _training_input(study['training_state_link'], 'training-state-link.json', directory=directory)
    link = _local(study['training_state_link'])
    scope = load_scope(link['split'])
    company = admit(scope, value['companies'][0])  # Before descriptor/task or artifact recursion.
    _training_input(value['frozen_panel_window'], 'frozen-panel-window.json', directory=directory)
    selected, descriptor = _local(value['frozen_panel_window']), _local(value['frozen_panel'])
    if (type(descriptor) is not dict or descriptor.get('schema') != SCHEMA
            or descriptor.get('policy') != POLICY or descriptor.get('split') != scope['split']
            or type(descriptor.get('companies')) is not list
            or any(type(row) is not dict for row in descriptor['companies'])
            or [row.get('company_id') for row in descriptor['companies']] != scope['training']
            or type(descriptor.get('members')) is not dict or set(descriptor['members']) != set(ARMS)
            or any(type(v) is not dict or type(v.get('id')) is not str for v in descriptor['members'].values())
            or type(selected) is not dict or set(selected) != {'schema','policy','descriptor','company_id','arms','versions','slots'}
            or selected['schema'] != 'earnings_training25_frozen_panel_window_v1'
            or selected['policy'] != POLICY or selected['descriptor'] != value['frozen_panel']
            or selected['company_id'] != company or type(selected['arms']) is not list
            or not selected['arms'] or selected['arms'] != [arm for arm in ARMS if arm in selected['arms']]
            or selected['versions'] != [descriptor['members'][arm]['id'] for arm in selected['arms']]
            or selected['slots'] != [str(Path(value['root'])/'roles'/f'forecast-01-{ARMS.index(arm):02d}')
                                     for arm in selected['arms']]
            or value['slots']['forecast'] != selected['slots']):
        raise ValueError('Exact admitted one-company frozen arm slice required')
    return dict(descriptor=descriptor, window=selected, scope=scope)


def panel_selection(value, slot):
    """Independent current selection after the caller's original full preflight.

    This does not authenticate history or relax register_case/check/invoke.
    """
    study = _local(value['forecast_study'])
    result = _panel_metadata(value, study)
    if result is None:
        return None
    selected, descriptor = result['window'], result['descriptor']
    if str(slot) not in selected['slots']:
        raise ValueError('Forecast is outside the declared frozen-panel slice')
    index = selected['slots'].index(str(slot)); arm = selected['arms'][index]
    return dict(company_id=selected['company_id'], arm=arm, window=selected,
        version=descriptor['members'][arm], bindings=[value['forecast_study'], value['frozen_panel'],
            value['frozen_panel_window'], study['training_state_link'], descriptor['authority'],
            descriptor['split'], descriptor['round0']['manifest'], descriptor['origin']['completed_result'],
            descriptor['origin']['population'], descriptor['origin']['latest_feedback'],
            descriptor['origin']['last_scored_feedback']])


def _baseline(value):
    if (type(value) is not dict or set(value) != set(EXTRA_BASELINE)
            or any(type(value[k]) is not int or value[k] < 0
                   for k in ('max_rowid', 'request_count', 'charged_nano_usd'))
            or type(value['rows_sha256']) is not str
            or not re.fullmatch(r'[0-9a-f]{64}', value['rows_sha256'])):
        raise ValueError('Exact frozen original accounting prefix required')


def _ledger_checks(db, value, original=EXTRA_BASELINE):
    amended = value.get('budget_amendment')
    cap = 200_000_000_000
    if 'budget_amendment' in value:
        if type(amended) is not dict or set(amended) != {'path', 'sha256'}:
            raise ValueError('Present cumulative400 amendment must be an exact non-null binding')
        from earnings_population_budget import validate_cap, CAP
        cap = validate_cap(db, amendment=amended)
        if cap != CAP:
            raise BudgetStop('Explicit cumulative400 amendment not activated')
    if (db.execute('SELECT * FROM config').fetchall()
            != [(1, cap, 100_000_000_000, 0)]
            or history_snapshot(db, original['max_rowid']) != original
            or history_snapshot(db, value['baseline']['max_rowid']) != value['baseline']
            or value['baseline']['max_rowid'] < original['max_rowid']):
        raise BudgetStop('Original accounting configuration or consumed prefix changed')
    if 'additional_budget_amendment' in value:
        from earnings_population_additional_budget import runtime_grant,liabilities
        runtime_grant(db,value)
        total,_=liabilities(db)
        if total>value['baseline']['charged_nano_usd']+value['additional_cap_nano_usd']:
            raise BudgetStop('Additional100 still shares original window5')
        return
    model_grant = _model_budget(db, value) if 'model_budget_amendment' in value else None
    rows = db.execute('SELECT model,reserved,charged,status FROM requests').fetchall()
    if any(type(n) is not int or n < 0 for row in rows for n in row[1:3]):
        raise BudgetStop('Invalid cumulative accounting values')
    total, models = 0, {}
    for model, reserved, charged, status in rows:
        amount = charged + (reserved if status not in ('settled', 'settled_upper_bound') else 0)
        total += amount
        models[model] = models.get(model, 0) + amount
    if (total > cap or any(amount > (model_grant['new_model_cap_nano_usd']
            if model_grant is not None and model == model_grant['model'] else 100_000_000_000)
            for model, amount in models.items())
            or 'budget_amendment' not in value and total > original['charged_nano_usd'] + EXTRA_CAP
            or total > value['baseline']['charged_nano_usd'] + value['additional_cap_nano_usd']):
        raise BudgetStop('Population global/model/original-extra/tranche ceiling exceeded')


def _model_budget(db, value):
    """Explicit prospective authority only; absence never widens admission."""
    from earnings_population_model_budget import (MODEL, PLAN as model_plan,
        IMPLEMENTATIONS, read_grant, authorized_liabilities, dispatch_totals, _authority)
    bound = value['model_budget_amendment']
    if (type(bound) is not dict or set(bound) != {'path','sha256'}
            or 'budget_amendment' not in value or window.minutes(value) != 90
            or type(value['additional_cap_nano_usd']) is not int
            or not 1 <= value['additional_cap_nano_usd'] <= _window_ceiling(value)):
        raise ValueError('Exact named-model grant requires cumulative400 and authorized90-minute window')
    grant = read_grant(db, required_binding=bound)
    authority = value['sources'].get(model_plan)
    if (grant is None or authority != grant['authority']
            or any(value['sources'].get(name) != dict(path=str(e.REPO/name),sha256=grant['implementations'][name])
                   for name in IMPLEMENTATIONS)):
        raise ValueError('Runtime authority/financial source differs from activated grant')
    _authority(authority, value['source_commit'], current=True)
    authorized_liabilities(db, 400_000_000_000)
    dispatch_totals(db, MODEL, 0, bound)  # All charges plus pending count toward fixed stage200.
    return grant


def _ledger(value):
    if value['ledger'] != str(e.PILOT / 'api-budget.sqlite3'):
        raise ValueError('Sole original cumulative ledger required')
    path = owner._path(value['ledger'], file=True)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('BEGIN')
        _ledger_checks(db, value)


def _study(value):
    if 'clean_slate_policy' in value:
        from earnings_population_clean_slate import enabled, study
        if not enabled(value): raise ValueError('Explicit clean-slate policy required')
        return study(value)
    if (value['population_plan'] != value['sources'][PLAN]
            or value['population_plan']['path'] != str(e.REPO / PLAN)):
        raise ValueError('Exact committed population plan source required')
    plan = e.strict_json(owner._read(value['population_plan']))
    if (plan.get('schema') != 'supervisor_bottleneck_plan_v1'
            or plan.get('id') != 'earnings-population-restore-20261016'
            or plan.get('human_authorization') != AUTHORIZATION):
        raise ValueError('Exact committed current human population authorization required')
    # Only top-level, exact-hash metadata is needed to dispatch before the
    # initial state's recursive artifact walk. Keep the legacy walk/read order
    # below after this explicitly additional metadata peek.
    from earnings_population_campaign import _training_input
    from earnings_population_training25 import PLAN as training_plan, POLICY
    study_binding = value['forecast_study']
    directory = ROOT/'inputs'/value['id']
    if (type(study_binding) is dict and type(study_binding.get('path')) is str
            and Path(study_binding['path']).is_relative_to(ROOT/'inputs')):
        _training_input(study_binding,'study.json',directory=directory)
    metadata = _local(study_binding)
    if type(metadata) is not dict:
        raise ValueError('Original study metadata object required')
    budget_marker = 'panel_window_budget_authority'
    if budget_marker in value or budget_marker in metadata:
        if (budget_marker not in value or budget_marker not in metadata
                or value[budget_marker] != metadata[budget_marker]):
            raise ValueError('Exact companion panel-window budget authority required')
        _window_ceiling(value)
    _proposal_metadata(value,metadata)
    panel = _panel_metadata(value, metadata)
    campaign_metadata = {}
    if metadata.get('campaign') is not None:
        # A still-marked campaign cannot become legacy by erasing only its
        # upstream runtime/study/source-map tags. Check the exact metadata
        # namespace before this additional nonrecursive legacy dispatch peek.
        _training_input(metadata['campaign'],'campaign.json',directory=directory)
        campaign_metadata = _local(metadata['campaign'])
        if type(campaign_metadata) is not dict:
            raise ValueError('Original campaign metadata object required')
    campaign_plan = campaign_metadata.get('source_plan')
    training = ('training_policy' in value or 'training_state_link' in metadata
                or 'training_stage_attachment' in metadata
                or training_plan in value['sources']
                or 'training_state_link' in campaign_metadata or 'training_policy' in campaign_metadata
                or type(campaign_plan) is dict and campaign_plan.get('path') == str(e.REPO/training_plan))
    companies = value['companies']
    if training:
        study = metadata
        campaign = study.get('campaign')
        if (type(value.get('training_policy')) is not str or value['training_policy'] != POLICY
                or campaign is None or study.get('training_state_link') is None
                or 'model_budget_amendment' not in value):
            raise ValueError('Exact forward training task/link and model budget required')
        _training_input(study_binding,'study.json',directory=directory)
        _training_input(study['training_state_link'],'training-state-link.json',directory=directory)
        _training_input(campaign,'campaign.json',directory=directory)
        _training_input(value['initial_population'],'initial-population.json',directory=directory)
        state = _local(value['initial_population'])  # Metadata only, no artifact recursion.
        if panel is not None:
            from earnings_population_frozen_panel import load_descriptor
            verified = load_descriptor(value['frozen_panel'], policy=value['frozen_panel_policy'],
                root=ROOT, ledger=Path(value['ledger']), repo=e.REPO)
            if (verified['descriptor'] != panel['descriptor'] or state != verified['base_origin']['population']
                    or _local(study['campaign_origin']) != verified['base_origin']
                    or panel['descriptor']['financial_policy']['model_rates'] != value['rates']
                    or panel['descriptor']['financial_policy']['forecast_limits'] != value['limits']['forecast']
                    or panel['descriptor']['financial_policy']['forecast_sources'] != {name:value['sources'].get(name)
                        for name in ('forecaster','tools/earnings_entry.py','tools/earnings_open_worker.py',
                                     'tools/earnings_population_execution.py')}):
                raise ValueError('Frozen-panel origin/pool/model/resources differ')
        from earnings_population_campaign_admission import validate
        # Trusted admission joins this exact state to the independently replayed
        # original and campaign/link before its retained population validation.
        residents = validate(value, study, state)
        state = pool.validate(state)
    else:
        state = pool.validate(_local(value['initial_population']))
        study = _local(study_binding)
        campaign = study.get('campaign')
        if campaign is not None:
            from earnings_population_campaign_admission import validate
            residents = validate(value, study, state)
        else:
            if (type(companies) is not list or not 1 <= len(companies) <= 2
                    or companies != tasks.select_companies(set(state['exposed_companies']) | {'CIK0000003545'}, len(companies))):
                raise ValueError('Exact next one/two resident-plan companies required')
            residents = [tasks.resident(cik) for cik in companies]
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
    elif state['observations'] and campaign is None:
        raise ValueError('Nonempty history cannot be silently reset without a continuation binding')
    return original


def preflight(binding, *, require_review=True):
    # Current source/ledger/clock checks still run in the unchanged body; only
    # nested historical artifact reads share this call's verified snapshot.
    from earnings_population_continuation import validation_epoch
    with validation_epoch():
        return _preflight(binding, require_review=require_review)


def _window_ceiling(value):
    if 'panel_window_budget_authority' not in value:
        return 5_000_000_000
    from earnings_population_panel_budget import ceiling
    return ceiling(value)


def _slot_ceiling(value,role,clean):
    from earnings_population_company_batch import rolling
    return 25 if clean and role=='forecast' and rolling(value) else (6 if role=='forecast' else 3)


def _preflight(binding, *, require_review=True):
    value = _local(binding)
    extra = set(value) & {'budget_amendment', 'model_budget_amendment', 'additional_budget_amendment', 'training_policy', 'window_minutes', 'validation_policy', 'public_feedback_policy', 'frozen_panel_policy', 'frozen_panel', 'frozen_panel_window', 'panel_window_budget_authority', 'training_proposal_policy', 'review_input_policy', 'proposal_prefix_reuse', 'clean_slate_policy', 'clean_company_concurrency', 'clean_learning_round'} if type(value) is dict else set()
    if (type(value) is not dict or set(value) != FIELDS | extra
            or value.get('schema') != 'earnings_population_runtime_v1'
            or value['purpose'] != 'capacity_episode'
            or type(value['id']) is not str or not re.fullmatch(r'edgar-population-20261016-[0-9]{2,}', value['id'])
            or type(value['source_commit']) is not str or not re.fullmatch(r'[0-9a-f]{40}', value['source_commit'])
            or value['root'] != str(ROOT / 'attempts' / value['id'])
            or owner._path(value['root']) != ROOT / 'attempts' / value['id']
            or value['role_efforts'] != ROLE_EFFORTS
            or value['original_extra_baseline'] != EXTRA_BASELINE
            or value['original_extra_cap_nano_usd'] != EXTRA_CAP
            or type(value['additional_cap_nano_usd']) is not int
            or not 1 <= value['additional_cap_nano_usd'] <= _window_ceiling(value)):
        raise ValueError('Exact reviewed bounded population runtime authority required')
    clean = 'clean_slate_policy' in value
    if 'clean_learning_round' in value and not clean:raise ValueError('Round marker requires clean adapter')
    if 'clean_company_concurrency' in value and not clean:raise ValueError('Batch requires clean-slate route')
    if clean:
        from earnings_population_clean_slate import enabled, authority, read_task
        enabled(value); authority(value)
        clean_task, _ = read_task(value)
        if (set(value) & {'frozen_panel_policy','panel_window_budget_authority','training_proposal_policy','proposal_prefix_reuse'}
                or value.get('validation_policy') != 'role_scoped_history_v1'
                or value.get('training_policy') != 'frozen_training25_v1'
                or 'model_budget_amendment' not in value or 'budget_amendment' not in value
                or value.get('window_minutes') != 90):
            raise ValueError('Clean-slate cannot mix legacy lineage, reuse or wider resources')
    if review_input_policy(value) is not None and (
            (not clean and value.get('training_proposal_policy') != PROPOSAL_POLICY)
            or clean and clean_task['mode'] not in ('proposal','repair_review') or 'training_policy' not in value):
        raise ValueError('Review200k is confined to explicitly admitted training proposals')
    _baseline(value['baseline'])
    from earnings_population_live_guard import enabled
    role_scoped = enabled(value)
    window.check(value, time.time())
    _sources(value)
    if 'budget_amendment' in value:
        from earnings_population_budget import PLAN as grant_plan
        study = _local(value['forecast_study'])
        if (not clean and study.get('campaign_resume') is None
                or grant_plan != BUDGET_PLAN
                or value['sources'].get(BUDGET_PLAN, {}).get('path') != str(e.REPO/BUDGET_PLAN)):
            raise ValueError('Cumulative400 opt-in requires source-bound resumed development campaign')
    original = _study(value)
    from earnings_population_public_predictions import runtime_policy
    runtime_policy(value, _local(value['forecast_study']))
    if role_scoped and not clean:
        study = _local(value['forecast_study'])
        if study.get('campaign') is None or study.get('campaign_resume') is None or study.get('continuation') is not None:
            raise ValueError('Role-scoped validation requires an explicit resumed development campaign')
    limits = dict(population_role_limits(value), forecast={'max_input_tokens': original['max_input_tokens'],
        'max_output_tokens': original['max_output_tokens'], 'wall_seconds': original['company_wall_seconds']})
    if (value['limits'] != limits or any(type(n) is not int for row in value['limits'].values() for n in row.values())
            or type(value['slots']) is not dict or set(value['slots']) != ROLES):
        raise ValueError('Original exact population role resources required')
    seen = set()
    for role, slots in value['slots'].items():
        ceiling=_slot_ceiling(value,role,clean)
        if type(slots) is not list or not 1 <= len(slots) <= ceiling:
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
