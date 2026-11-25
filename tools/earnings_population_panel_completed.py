"""Fully scored frozen-panel slices, never population origins or fake stages."""
from copy import deepcopy
import hashlib
from pathlib import Path
import re

import earnings_population as pool
import earnings_population_completed as completed
import earnings_population_continuation as history
import earnings_population_frozen_panel as panel
import earnings_population_public_predictions as public
import earnings_population_runtime as runtime_module
import earnings_population_tasks as tasks
from earnings_native_failure import _cleanup
from earnings_population_panel_budget import ceiling
from market_rsi import digest

SCHEMA = 'earnings_training25_scored_panel_window_v1'
RESULT_SCHEMA = 'earnings_training25_frozen_panel_window_result_v1'


def _identity(binding, root, ledger, repo):
    if (type(binding) is not dict or set(binding) != {'path','sha256'}
            or type(binding.get('path')) is not str or type(binding.get('sha256')) is not str
            or re.fullmatch('[0-9a-f]{64}',binding['sha256']) is None):
        raise ValueError('Exact original scored-panel result binding required')
    path = Path(binding['path']); ident = path.parent.name
    if (root != completed.bootstrap.OWNED or ledger != completed.bootstrap.LEDGER
            or repo != completed.bootstrap.REPO
            or any(p.resolve() != p for p in (root,ledger,repo,path))
            or path != root/'attempts'/ident/'frozen-panel-window-result.json'
            or re.fullmatch('edgar-population-20261016-[0-9]{2}',ident) is None):
        raise ValueError('Canonical original frozen-panel result required')
    return path,ident


def load_window(binding, *, root, ledger, repo):
    """Authenticate every selected scored leaf or refuse the entire finite slice."""
    path,ident = _identity(binding,root,ledger,repo); attempt = path.parent
    reader = history._Reader(root,ledger,repo,ident)
    result = reader.read(binding)
    if (type(result) is not dict or set(result) != {'schema','runtime','status','result','budget',
            'improvement_proven','retry_allowed'} or result['schema'] != RESULT_SCHEMA
            or result['status'] != 'COMPLETED_FROZEN_PANEL_WINDOW'
            or result['retry_allowed'] is not False or result['improvement_proven'] is not False
            or (attempt/'frozen-panel-window-failure.json').exists()
            or (attempt/'population-run-result.json').exists() or (attempt/'loop').exists()):
        raise ValueError('Only a fully scored forecast-only panel slice transfers')
    registry = ledger.parent/'.capacity-runtime-claims'; token = hashlib.sha256(ident.encode()).hexdigest()
    claim_bound = reader.pin(registry/(token+'.json')); owner_bound = reader.pin(registry/(token+'.result.json'))
    reader.extra.update(Path(b['path']) for b in (claim_bound,owner_bound,tasks.FULL_PLAN,tasks.SCORER))
    claim,owner = reader.read(claim_bound),reader.read(owner_bound)
    runtime_bound = result['runtime']; runtime = reader.read(runtime_bound)
    directory = root/'inputs'/ident
    if (runtime_bound != owner.get('runtime') or runtime_bound.get('path') != str(directory/'runtime-reviewed.json')
            or owner.get('status') != 'COMPLETED_COMPONENT_CONTEXT' or owner.get('error_type') is not None
            or owner.get('retry_allowed') is not False or claim.get('runtime') != runtime_bound
            or claim.get('id') != ident or claim.get('source_commit') != runtime.get('source_commit')
            or claim.get('retry_allowed') is not False or runtime.get('schema') != 'earnings_population_runtime_v1'
            or runtime.get('id') != ident or runtime.get('root') != str(attempt)
            or runtime.get('ledger') != str(ledger) or runtime.get('frozen_panel_policy') != panel.POLICY
            or runtime.get('public_feedback_policy') != public.POLICY
            or type(runtime.get('forecast_study')) is not dict
            or runtime['forecast_study'].get('path') != str(directory/'study.json')
            or type(runtime.get('initial_population')) is not dict
            or runtime['initial_population'].get('path') != str(directory/'initial-population.json')):
        raise ValueError('Exact completed panel owner/runtime/claim required')
    reader.register_sources(runtime)
    reader.extra.update(Path(runtime[k]['path']) for k in ('review','budget_amendment','model_budget_amendment'))
    study = reader.read(runtime['forecast_study'])
    scope,_ = completed._training(reader,runtime,study,preview=True)  # Membership before task/body recursion.
    if scope is None: raise ValueError('Explicit original training admission required')
    selected = runtime_module._panel_metadata(runtime,study)
    verified = panel.load_descriptor(runtime['frozen_panel'],policy=runtime['frozen_panel_policy'],
        root=root,ledger=ledger,repo=repo)
    descriptor,base = verified['descriptor'],verified['base_origin']
    window = selected['window']
    if (selected['descriptor'] != descriptor or selected['scope'] != scope
            or window['descriptor'] != runtime['frozen_panel'] or window['company_id'] != runtime['companies'][0]
            or descriptor['origin']['completed_result'] != base['previous_result']):
        raise ValueError('Original frozen descriptor/window/predecessor differs')
    reader.extra.add(Path(runtime['frozen_panel']['path']))  # Exact P1-authenticated root metadata only.
    reader.read(runtime['frozen_panel'],binary=True)
    completed._register(reader,base,training_scope=scope)
    _,evidence = completed._training(reader,runtime,study,inherited=base)
    resident = tasks.resident(window['company_id'])
    company_row = next(r for r in descriptor['companies'] if r['company_id'] == window['company_id'])
    if (company_row['case'] != resident['case'] or company_row['kernel'] != resident['kernel']
            or study.get('cases') != [resident['case']] or study.get('runtime_config') != resident['runtime']
            or study.get('data') != tasks.FULL_PLAN or study.get('scorer') != tasks.SCORER
            or study.get('sole_ledger') != str(ledger) or runtime.get('rates') !=
                descriptor['financial_policy']['model_rates'] or runtime['rates'] != resident['runtime']['models']['gpt-6.1-sol']
            or runtime.get('limits',{}).get('forecast') != descriptor['financial_policy']['forecast_limits']
            or any(runtime['sources'].get(k,{}).get('sha256') != b['sha256']
                for k,b in descriptor['financial_policy']['forecast_sources'].items())):
        raise ValueError('Original frozen company/task/data/model/forecast policy differs')
    reader.extra.add(Path(resident['kernel']['qa']['path']))
    summary = result['result']
    if (type(summary) is not dict or set(summary) != {'descriptor','window','company_id','results'}
            or summary['descriptor'] != runtime['frozen_panel'] or summary['window'] != runtime['frozen_panel_window']
            or summary['company_id'] != window['company_id'] or type(summary['results']) is not list
            or [r.get('arm') if type(r) is dict else None for r in summary['results']] != window['arms']):
        raise ValueError('Every selected original arm must have exactly one ordered scored result')
    expected = {}
    for arm,slot,wrapped in zip(window['arms'],window['slots'],summary['results'],strict=True):
        if set(wrapped) != {'arm','result'}: raise ValueError('Exact original arm wrapper required')
        row = wrapped['result']; pool.validate_result(row)
        selection = runtime_module.panel_selection(runtime,slot)
        if (selection['arm'] != arm or selection['version'] != descriptor['members'][arm]
                or row['version_id'] != selection['version']['id'] or not row['evidence']
                or row['evidence'][0].get('path') != str(Path(slot)/'population-public-feedback.json')):
            raise ValueError('Exact original selected version/slot/public result required')
        expected[Path(slot).name] = dict(role='forecast',company_id=window['company_id'],
            version=selection['version'],forecast_result=row)
    for role in ('controller','author','review'):
        if any(Path(slot).exists() for slot in runtime['slots'][role]):
            raise ValueError('A frozen panel cannot contain new Controller/Author/Review outputs')
    review = reader.read(runtime['review'])
    if (review.get('verdict') != 'PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY'
            or review.get('blocking_findings') != [] or review.get('source_commit') != reader.commit
            or str(review.get('reviewer','')).strip().lower() in ('','root','/root')
            or review.get('reviewed_configuration_sha256') != digest({k:v for k,v in runtime.items() if k != 'review'})):
        raise ValueError('Original distinct panel configuration/Source review differs')
    clock = reader.pair(attempt/'clock.json')
    if (clock != reader.read(owner['clock']) or clock.get('source_commit') != reader.commit
            or clock.get('cutoff_utc') != runtime['cutoff_utc'] or clock.get('deadline_utc') != runtime['deadline_utc']):
        raise ValueError('Original sealed panel clock differs')
    ceiling(runtime,historical_reader=reader)
    reader.scan(runtime); reader.scan(study); reader.scan(result)
    evidence += completed._budget(reader,runtime,owner,result)
    evidence += [row['result'] for row in _cleanup(attempt)]
    python = completed._literal(reader,runtime['sources']['tools/earnings_population_run.py'],'PYTHON')
    evidence += completed._native(reader,Path('/private/tmp')/('market-rsi-'+ident),runtime_bound,
        runtime,expected,resident,python,training_scope=scope)
    outcomes = []
    for wrapped in summary['results']:
        arm,row = wrapped['arm'],wrapped['result']
        diagnostics,projection = public.project(row['evidence'][0],row['evidence'],descriptor['members'][arm],
            resident['company'],training_scope=scope)
        if sum(r['points_awarded'] for r in projection['targets']) != row['points']:
            raise ValueError('Original public awards differ from scored leaf')
        outcomes.append(dict(arm=arm,company_id=window['company_id'],version_id=row['version_id'],status='SCORED',
            points=row['points'],diagnostics=diagnostics,public_predictions=projection,evidence=deepcopy(row['evidence'])))
    return dict(schema=SCHEMA,policy=panel.POLICY,result=deepcopy(binding),runtime=deepcopy(runtime_bound),
        descriptor=deepcopy(runtime['frozen_panel']),window=deepcopy(runtime['frozen_panel_window']),
        company_id=window['company_id'],outcomes=outcomes,
        coverage=dict(selected_arms=deepcopy(window['arms']),scored_leaves=len(outcomes),full25_means_available=False),
        scope='Verified finite scored slice only; no new population origin, adoption, full-panel coverage or next-model use.',
        evidence=[binding,runtime_bound,claim_bound,owner_bound,runtime['review'],runtime['frozen_panel'],
            runtime['frozen_panel_window'],*evidence,*base['evidence']])
