"""Opt-in public submission/advice comparison, never scorer answers or traces."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import re

from earnings_entry import checked, strict_json, strict_predictions
from earnings_population_diagnostics import from_trial
from edgar_forecast_model_pilot import strict_single_number
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine

POLICY = 'public_prediction_comparison_v1'
DEV = frozenset({'CIK0000003545', 'CIK0000004457', 'CIK0000017313'})
TARGETS = [f'T{i:03d}' for i in range(1, 6)]


def policy(value):
    if value is not None and (type(value) is not str or value != POLICY):
        raise ValueError('Exact opt-in public prediction feedback policy required')
    return value


def runtime_scope(runtime, study=None, *, historical_reader=None):
    """Current typed receiving scope, not a replacement for full admission."""
    if type(runtime) is not dict:
        raise ValueError('Original population runtime object required')
    if 'clean_slate_policy' in runtime:
        from earnings_population_clean_slate import enabled, read_task
        enabled(runtime)
        if historical_reader is not None:
            raise ValueError('Clean-slate is not a legacy historical reader route')
        if study is not None and study != _read(runtime['forecast_study']):
            raise ValueError('Clean study binding changed')
        return read_task(runtime)[1]
    if 'training_policy' not in runtime:
        if type(study) is dict and 'training_state_link' in study:
            raise ValueError('Training link requires explicit runtime policy')
        return None
    from earnings_population_training25 import POLICY as TRAINING, load_scope, admit, entry_plan, PLAN
    from earnings_population_budget import amendment_binding
    from earnings_entry import REPO
    if (runtime.get('schema') != 'earnings_population_runtime_v1'
            or type(runtime['training_policy']) is not str or runtime['training_policy'] != TRAINING
            or runtime.get('budget_amendment') != amendment_binding()
            or type(runtime.get('model_budget_amendment')) is not dict
            or type(runtime.get('companies')) is not list or len(runtime['companies']) != 1):
        raise ValueError('Exact forward cumulative400 training runtime required')
    saved = _read(runtime['forecast_study'])
    if study is not None and study != saved:
        raise ValueError('Training study differs from its original binding')
    study = saved
    if (type(study) is not dict or study.get('campaign') is None or study.get('campaign_resume') is None
            or study.get('continuation') is not None or study.get('training_state_link') is None):
        raise ValueError('Original resumed training study/link required')
    campaign = _read(study['campaign']); link = _read(study['training_state_link'])
    if (type(campaign) is not dict or type(link) is not dict
            or set(link) != {'schema','policy','split','comparator','previous_population','population_sha256',
                             'previous_feedback','last_scored_feedback','panel','completed_origin'}
            or type(campaign.get('contract')) is not dict
            or campaign.get('training_state_link') != study['training_state_link']
            or link.get('schema') != 'earnings_training25_state_link_v1'
            or link.get('policy') != TRAINING or link.get('completed_origin') is None
            or link.get('panel') != runtime['companies'] or campaign.get('panel') != runtime['companies']
            or campaign.get('source_plan') != runtime.get('sources', {}).get(PLAN)):
        raise ValueError('Training study/campaign/link/panel identity differs')
    scope = load_scope(link['split'])
    for cik in [*runtime['companies'], campaign.get('validation_company_id'),
                campaign.get('contract', {}).get('company_id')]:
        admit(scope, cik)  # Before any resident or contract artifact recursion.
    if (campaign['validation_company_id'] != runtime['companies'][0]
            or campaign['contract']['company_id'] != runtime['companies'][0]):
        raise ValueError('Current training case differs from admitted panel')
    entry_plan(campaign['source_plan'], REPO,
               **({} if historical_reader is None else {'historical_reader':historical_reader}))
    return scope


def runtime_policy(runtime, study=None, *, historical_reader=None):
    if type(runtime) is not dict:
        raise ValueError('Original population runtime object required')
    if 'public_feedback_policy' not in runtime:
        return None  # Original runtime means original projection, even today.
    value = runtime['public_feedback_policy']
    from earnings_population_budget import amendment_binding
    scope = runtime_scope(runtime, study,
                          **({} if historical_reader is None else {'historical_reader':historical_reader}))
    if 'clean_slate_policy' in runtime:
        if value != POLICY or runtime.get('budget_amendment') != amendment_binding():
            raise ValueError('Clean public feedback still requires original financial opt-in')
        return value
    if (value is None or policy(value) != POLICY
            or runtime.get('schema') != 'earnings_population_runtime_v1'
            or runtime.get('budget_amendment') != amendment_binding()
            or type(runtime.get('companies')) is not list or not 1 <= len(runtime['companies']) <= 2
            or scope is None and any(type(cik) is not str or cik not in DEV for cik in runtime['companies'])
            or study is not None and (type(study) is not dict or study.get('campaign') is None
                or study.get('campaign_resume') is None or study.get('continuation') is not None)):
        raise ValueError('Public prediction feedback requires explicit cumulative400 resumed DEV runtime')
    return value


def company(cik, *, training_scope=None):
    # Metadata only: do not reopen another company's body or decode any QA.
    if training_scope is not None:
        from earnings_population_training25 import admit
        admit(training_scope, cik)
    elif type(cik) is not str or cik not in DEV:
        raise ValueError('Public prediction feedback is development-only')
    from earnings_population_tasks import _universe
    plan, manifest, _ = _universe()
    rows = [row for row in plan['companies'] if row['cik'] == cik]
    targets = [row for row in manifest['instances'] if row['cik'] == cik]
    if (len(rows) != 1 or len(targets) != 1 or targets[0]['target_count'] != 5
            or rows[0]['target_accession'] != targets[0]['target_accession']):
        raise ValueError('Original public company/target identity required')
    return deepcopy(rows[0])


def _read(bound):
    if (type(bound) is not dict or set(bound) != {'path', 'sha256'}
            or type(bound['path']) is not str or type(bound['sha256']) is not str
            or re.fullmatch('[0-9a-f]{64}', bound['sha256']) is None):
        raise ValueError('Exact public original binding required')
    path = Path(bound['path'])
    if (not path.is_absolute() or str(path.resolve()) != bound['path'] or path.is_symlink()
            or not path.is_file() or path.stat().st_nlink != 1 or path.stat().st_size > 16_000_000):
        raise ValueError('Canonical bounded unaliased public original required')
    return strict_json(checked(bound))


def project(public_binding, evidence, version, company, *, training_scope=None):
    """Return verified diagnostics and five public values; never copy raw JSON."""
    if training_scope is not None:
        from earnings_population_training25 import admit
        admit(training_scope, company.get('cik') if type(company) is dict else None)
        if company != globals()['company'](company['cik'], training_scope=training_scope):
            raise ValueError('Training public descriptor differs from original metadata')
    elif type(company) is not dict or type(company.get('cik')) is not str or company['cik'] not in DEV:
        raise ValueError('Public prediction feedback is development-only')
    public = _read(public_binding)
    parent = Path(public_binding['path']).parent
    if (Path(public_binding['path']).name != 'population-public-feedback.json'
            or public.get('schema') != 'earnings_population_public_trial_v1'
            or public.get('company_id') != company['cik'] or public.get('version_id') != version['id']
            or public.get('pool_sources') != {axis: version[axis]['sha256'] for axis in ('R', 'H')}
            or type(public.get('target_scores')) is not list or len(public['target_scores']) != 5
            or any(type(row) is not dict or set(row) != {'target_id', 'points_awarded'}
                or type(row['points_awarded']) not in (int, float) or row['points_awarded'] not in (0, .5, 1)
                for row in public['target_scores'])
            or [row.get('target_id') for row in public['target_scores']] != TARGETS
            or sum(row['points_awarded'] for row in public['target_scores']) != public.get('points')):
        raise ValueError('Exact public trial/company/version/source/five awards required')
    diagnostics = from_trial(public_binding, evidence, version, company)
    if [row['target_id'] for row in diagnostics['reported_target_completion']] != TARGETS:
        raise ValueError('Original five public question identities required')

    def original(name):
        rows = [b for b in evidence if b.get('path') == str(parent/name)]
        if len(rows) != 1:
            raise ValueError('Exactly one bound public forecast original required')
        return _read(rows[0]), rows[0]

    observed, originally_bound = {}, []
    def physical(path):
        rows = [b for b in evidence if b.get('path') == str(path)]
        if len(rows) > 1:
            raise ValueError('One physical observation or original binding required')
        bound = rows[0] if rows else engine.pin(path)
        if rows:
            originally_bound.append(path.name)
        observed[path.name] = bound['sha256']
        return _read(bound), bound

    result, result_binding = original('result.json')
    turns = result.get('turns')
    if (result.get('status') != 'COMPLETED_SCORED' or type(turns) is not int or not 1 <= turns <= 24
            or result.get('planned_targets') != 5 or result.get('scored_targets') != 5):
        raise ValueError('Completed original five-target forecast required')
    predictions, predictions_binding = original('predictions.json')
    response, response_binding = original(f'{turns:02d}-response.json')
    request, request_binding = original(f'{turns:02d}-request.json')
    if (strict_predictions(response, TARGETS) != predictions
            or request.get('payload', {}).get('model') != 'gpt-6.1-sol'
            or response.get('model') != 'gpt-6.1-sol'
            or type(request.get('request_id')) is not str or not request['request_id']
            or type(request.get('reserved_nano_usd')) is not int or request['reserved_nano_usd'] <= 0):
        raise ValueError('Final submitted predictions/response/model/reservation differ')
    matches = []
    for path in parent.glob('http-*.intent.json'):
        value = _read(engine.pin(path))
        if value.get('endpoint') == '/v1/responses' and value.get('budget_request_id') == request['request_id']:
            matches.append((path, value))
    if len(matches) != 1:
        raise ValueError('One original physical final generation required')
    path, intent = matches[0]
    pinned_intent, intent_binding = physical(path)
    if pinned_intent != intent:
        raise ValueError('Physical final intent differs from observed or bound evidence')
    maximum = intent.get('payload', {}).get('max_output_tokens')
    if (intent.get('complete_reservation') != request or intent.get('request_receipt_sha256') != request_binding['sha256']
            or intent.get('retry_allowed') is not False or type(maximum) is not int or maximum <= 0
            or intent['payload'] != dict(request['payload'], max_output_tokens=maximum, service_tier='default', store=False)):
        raise ValueError('Original physical final request differs')
    sibling = lambda suffix: path.with_name(path.name.removesuffix('.intent.json') + suffix)
    sent, sent_binding = physical(sibling('.response.json'))
    raw, raw_binding = physical(sibling('.raw.bin'))
    if sent != response or dict(raw, _request_id=sent.get('_request_id')) != sent:
        raise ValueError('Original physical final response differs')
    program, program_binding = original('program-executions.json')
    execution = program['R']
    if (diagnostics['source_sha256'] != version['R']['sha256']
            or diagnostics['execution_sha256'] != execution['receipt']['sha256']):
        raise ValueError('Explicit advice differs from verified consumed R execution')
    advice, seen = {}, set()
    value = execution['value']
    targets = value.get('targets', []) if type(value) is dict else []
    for row in targets if type(targets) is list else []:
        if type(row) is dict and type(row.get('target_id')) is str:
            if row['target_id'] in seen:
                raise ValueError('Duplicate top-level R advice identity')
            seen.add(row['target_id'])
        if type(row) is not dict or row.get('status') != 'complete' or 'predicted_value' not in row:
            continue  # No inference from nested or incomplete program reports.
        ident = row.get('target_id')
        if ident not in TARGETS or ident in advice or strict_single_number({'predictions': [row]}, [ident]):
            raise ValueError('Explicit complete R advice must have a unique ID and finite number')
        advice[ident] = row['predicted_value']
    submitted = {row['target_id']: row['predicted_value'] for row in predictions['predictions']}
    awards = {row['target_id']: row['points_awarded'] for row in public['target_scores']}
    rows = [dict(target_id=ident, predicted_value=submitted[ident], R_advice_value=advice.get(ident),
        matches_R_advice=Decimal(str(submitted[ident])) == Decimal(str(advice[ident])) if ident in advice else None,
        points_awarded=awards[ident]) for ident in TARGETS]
    return diagnostics, dict(schema='earnings_population_public_predictions_v1', company_id=company['cik'],
        version_id=version['id'], source_sha256=version['R']['sha256'], R_execution=deepcopy(execution['receipt']),
        R_output_sha256=digest(execution['value']), targets=rows,
        evidence=dict(slot=str(parent), originals={Path(bound['path']).name: bound['sha256'] for bound in
            (public_binding, predictions_binding, result_binding, public['effective_input'], request_binding,
             response_binding, program_binding)}, readonly_physical_observation=dict(
                 files=observed, originally_bound_files=sorted(originally_bound),
                 qualification='Retrospective read-only wire alignment with frozen numbered request/response; observed hashes are not proof these bytes were historically pinned unless listed as originally bound.')),
        limitation='Own public submissions, awards and explicit complete top-level R advice only. Numeric equality is not causal following, financial correctness, generalization or predictive improvement.')
