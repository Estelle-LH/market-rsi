"""Carry a closed first-review delivery failure as evidence, never adoption.

Only the original completed seed and three completed stages transfer. The
failed attempt stays closed; its unreviewed R is a paged reference. This does
not recover a partially scored window or invent an independent rejection.
"""
from copy import deepcopy
from contextlib import closing
from contextvars import ContextVar
import hashlib
from pathlib import Path
import re
import sqlite3

import earnings_population as pool
import earnings_population_continuation as history
import earnings_population_campaign_resume as resume
import earnings_population_tasks as tasks
from earnings_native_failure import _cleanup, _owned_requests
from earnings_night_budget import history_snapshot
from market_rsi import digest

PLAN = 'configs/earnings_coevolution/population_recovery_plan.json'
_FAILURE_ANCESTRY = ContextVar('earnings_population_failure_ancestry', default=())


def _prefix(reader, runtime, attempt, *, failed_stage='source_review', failure_kind=None):
    if failed_stage not in {'implement','source_review','execute'}:
        raise ValueError('Only exact first-round Author or Review failure prefix is supported')
    if failure_kind is not None:
        from earnings_population_training25 import STAGE_ATTACHMENT_MODE, POLICY
        if (failure_kind != STAGE_ATTACHMENT_MODE or failed_stage != 'execute'
                or runtime.get('training_policy') != POLICY or runtime.get('companies') != ['CIK0000021076']):
            raise ValueError('Only the typed same-training-task preclaim deadline prefix is supported')
    path = attempt/'loop'
    with history._journal_lock(path):
        manifest = reader.pair(path/'manifest.json')
        seed = manifest['seed']
        if (manifest.get('schema') != 'feedback_linked_loop_v1'
                or manifest.get('max_rounds') != len(runtime['companies'])
                or manifest.get('seed_sha256') != digest(seed)
                or seed['companies'] != runtime['companies']
                or seed['population'] != reader.read(runtime['initial_population'])
                or manifest['driver_source_sha256'] != runtime['sources'][history.DRIVER]['sha256']
                or set(manifest['handler_identity']) != set(history.STAGES)):
            raise ValueError('Original failed campaign seed/driver identity differs')
        study = reader.read(runtime['forecast_study'])
        for stage, identity in manifest['handler_identity'].items():
            expected = dict(stage=stage, adapter=runtime['sources']['tools/earnings_population_loop.py'],
                admission={'function': 'execute.<locals>.admit', 'module': runtime['sources']['tools/earnings_population_run.py']},
                services=history.expected_services(runtime),
                campaign_policy=runtime['sources']['tools/earnings_population_campaign.py'], campaign=study['campaign'])
            if identity != expected:
                raise ValueError('Original failed campaign handler identity differs')
        outputs, files, evidence = {}, set(), [reader.pin(path/'manifest.json')]
        for stage in history.STAGES[:history.STAGES.index(failed_stage)+1]:
            prefix = path/f'round-0001-{stage}'
            claim, done = prefix.with_suffix('.claim.json'), prefix.with_suffix('.done.json')
            current = dict(round_index=1, seed=seed, previous_result=seed,
                previous_feedback_sha256=digest(seed), outputs=outputs)
            if reader.read(reader.pin(claim)) != dict(round_index=1, stage=stage,
                    context_sha256=digest(current), manifest_sha256=evidence[0]['sha256'],
                    previous_feedback_sha256=digest(seed)):
                raise ValueError('Original failed-prefix claim changed')
            files.add(claim.name); evidence.append(reader.pin(claim))
            if stage == failed_stage:
                failed = prefix.with_suffix('.failed.json')
                if reader.read(reader.pin(failed)) != dict(claim_sha256=reader.pin(claim)['sha256'],
                        exception_type='RuntimeError' if failure_kind is None else 'BatchStoppedError', retry_allowed=False):
                    raise ValueError('Original review failure record differs' if failed_stage == 'source_review'
                                     else 'Original implement failure record differs')
                files.add(failed.name); evidence.append(reader.pin(failed))
                break
            row = reader.pair(done)
            if (set(row) != {'claim_sha256', 'output', 'output_sha256'}
                    or row['claim_sha256'] != reader.pin(claim)['sha256']
                    or row['output_sha256'] != digest(row['output'])):
                raise ValueError('Original completed prefix seal differs')
            reader.scan(row['output']); outputs[stage] = row['output']
            files.update((done.name, done.with_suffix('.binding.json').name)); evidence.append(reader.pin(done))
        if {p.name for p in path.glob('round-*')} != files:
            raise ValueError('Only first-review failure before any scored/reconciled round may transfer'
                             if failed_stage == 'source_review' else
                             'Only exact first implement failure before any scored/reconciled round may transfer')
    return seed, outputs, evidence


def _plan_matches(binding, repo, historical_reader):
    if historical_reader is None:
        return binding.get('path') == str(repo/PLAN)
    try:
        return history.source_name(binding.get('path'), repo) == PLAN
    except ValueError:
        return False


def _read_plan(binding, *, root, ledger, repo, historical_reader=None):
    from earnings_entry import checked, strict_json
    if historical_reader is None:
        return strict_json(checked(binding))
    if (type(historical_reader) is not history._Reader
            or (historical_reader.root,historical_reader.ledger,historical_reader.repo) != (root,ledger,repo)
            or type(historical_reader.commit) is not str
            or re.fullmatch('[0-9a-f]{40}',historical_reader.commit) is None
            or not _plan_matches(binding, repo, historical_reader)
            or (binding.get('path'),binding.get('sha256')) not in historical_reader.sources):
        raise ValueError('Exact original campaign Git reader/plan binding required')
    return historical_reader.read(binding)


def _legacy_load(binding, *, root, ledger, repo, plan_binding, historical_reader=None):
    for bound in (binding, plan_binding):
        if (type(bound) is not dict or set(bound) != {'path','sha256'}
                or type(bound['path']) is not str or type(bound['sha256']) is not str
                or re.fullmatch(r'[0-9a-f]{64}', bound['sha256']) is None):
            raise ValueError('Exact failure/plan bindings required before any read')
    root, ledger, repo = map(Path, (root, ledger, repo))
    path = Path(binding['path']); ident = path.parent.name
    if (root != resume.OWNED or ledger != resume.LEDGER or repo != resume.REPO
            or any(p.resolve() != p for p in (root, ledger, repo))
            or not re.fullmatch(r'edgar-population-20261016-[0-9]{2}', ident)
            or path != root/'attempts'/ident/'population-run-failure.json'
            or path.resolve() != path or not _plan_matches(plan_binding, repo, historical_reader)):
        raise ValueError('Canonical owned failed attempt and committed recovery plan required')
    reader = history._Reader(root, ledger, repo, ident)
    from earnings_entry import checked, strict_json
    plan = _read_plan(plan_binding,root=root,ledger=ledger,repo=repo,historical_reader=historical_reader)
    audit_binding = plan['closed_failure_audit']
    from earnings_population_budget import AUTHORIZATION
    if (plan.get('schema') != 'supervisor_bottleneck_plan_v1'
            or plan.get('id') != 'earnings-population-review-recovery-20261016'
            or plan.get('human_authorization') != AUTHORIZATION
            or plan.get('failed_attempt') != binding
            or Path(audit_binding['path']).parent != root):
        raise ValueError('Exact source-bound diagnosed failure plan required')
    registry = ledger.parent/'.capacity-runtime-claims'; token = hashlib.sha256(ident.encode()).hexdigest()
    owner_bound, claim_bound = reader.pin(registry/(token+'.result.json')), reader.pin(registry/(token+'.json'))
    reader.extra.update(Path(b['path']) for b in (audit_binding, owner_bound, claim_bound))
    failure, audit = reader.read(binding), reader.read(audit_binding)
    owner, claim = reader.read(owner_bound), reader.read(claim_bound)
    runtime_bound = owner['runtime']; runtime = reader.read(runtime_bound); attempt = path.parent
    reader.extra.add(Path(runtime['review']['path']))
    if (failure != dict(status='FAILED_NO_RETRY', error_type='LoopHalted', native_closure=None, retry_allowed=False)
            or (attempt/'population-run-result.json').exists() or any((attempt/'roles').glob('forecast-*'))
            or any(attempt.rglob('score.json')) or owner.get('status') != 'FAILED_NO_RETRY'
            or owner.get('error_type') != 'LoopHalted' or owner.get('retry_allowed') is not False
            or claim.get('runtime') != runtime_bound or claim.get('id') != ident
            or claim.get('source_commit') != runtime.get('source_commit') or claim.get('retry_allowed') is not False
            or runtime.get('schema') != 'earnings_population_runtime_v1' or runtime.get('id') != ident
            or runtime.get('root') != str(attempt) or runtime.get('ledger') != str(ledger)
            or runtime.get('companies') not in ([resume.COMPANY], [resume.COMPANY]*2)
            or audit.get('schema') != 'earnings_population_live_physical_link_audit_v1'
            or audit.get('run_id') != ident or audit.get('auditor') in ('', 'root', '/root', None)
            or audit.get('status') != 'SEALED_FAILED_NO_RETRY_AT_REVIEW_INPUT'
            or audit.get('runtime') != runtime_bound or audit.get('source_commit') != runtime['source_commit']
            or audit['terminal_failure']['binding'] != binding
            or audit['accounting']['owner']['binding'] != owner_bound):
        raise ValueError('Closed unreviewed original failure/owner/audit differs')
    reader.register_sources(runtime)
    study = reader.read(runtime['forecast_study']); resumed = reader.read(study['campaign_resume'])
    inherited = resume.load(resumed['previous_result'], root=root, ledger=ledger, repo=repo)
    reader.ids.update({'edgar-population-20261016-01', 'edgar-population-20261016-02', resume.IDENT})
    reader.extra.update(Path(b['path']) for b in inherited['evidence'])
    reader.extra.update(Path(b['path']) for b in (tasks.FULL_PLAN, tasks.SCORER))
    from earnings_population_budget import amendment_binding
    if runtime.get('budget_amendment') != amendment_binding():
        raise ValueError('Exact existing cumulative400 grant required for recovery')
    reader.extra.add(Path(runtime['budget_amendment']['path']))
    resident = tasks.resident(resume.COMPANY); reader.extra.add(Path(resident['kernel']['qa']['path']))
    if (reader.read(study['campaign_origin']) != inherited
            or study.get('data') != tasks.FULL_PLAN or study.get('scorer') != tasks.SCORER
            or study.get('runtime_config') != resident['runtime']
            or study.get('cases') != [resident['case']]*len(runtime['companies'])
            or study.get('sole_ledger') != str(ledger)
            or runtime.get('rates') != resident['runtime']['models']['gpt-6.1-sol']):
        raise ValueError('Original verified seed/data/scorer/model differs')
    reader.scan(runtime); reader.scan(study)
    configuration_review = reader.read(runtime['review'])
    if (configuration_review.get('verdict') != 'PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY'
            or configuration_review.get('blocking_findings') != []
            or configuration_review.get('source_commit') != reader.commit
            or configuration_review.get('reviewed_configuration_sha256') != digest({k:v for k,v in runtime.items() if k != 'review'})):
        raise ValueError('Original failed configuration review differs')
    seed, outputs, evidence = _prefix(reader, runtime, attempt)
    state = pool.validate(inherited['population']); child = outputs['implement']['candidate']
    chosen = reader.read(outputs['controller']['decision'])
    if (seed['population'] != state or seed['feedback'] != reader.read(study['campaign'])['initial_feedback']
            or child['axis'] != 'R' or child['parent'] != chosen['parent_pair_sha256']
            or child['parent'] not in [state['stable_id'], *state['explorers']]
            or child['H'] != state['versions'][child['parent']]['H'] or child['id'] in state['versions']
            or child != pool.version(**{k:child[k] for k in ('R','H','parent','axis','method','author','evidence')})):
        raise ValueError('Only exact unretained authored R and unchanged seed may transfer')
    reviewer = attempt/'roles/review-01'; review = reader.read(reader.pin(reviewer/'result.json'))
    count = reader.read(reader.pin(reviewer/'01-context-01-count.json'))
    if (review.get('status') != 'FAILED_NO_RETRY' or review.get('error_type') != 'BudgetStop'
            or review.get('final_numbered_response') is not None or review.get('tool_calls') != 0
            or any(reviewer.glob('[0-9][0-9]-request.json')) or any(reviewer.glob('[0-9][0-9]-response.json'))
            or count['input_tokens'] <= runtime['limits']['review']['max_input_tokens']):
        raise ValueError('Only proven pre-generation review input failure may transfer')
    requests = _owned_requests(runtime); closing_state = audit['accounting']['ledger_closed']
    with closing(sqlite3.connect(ledger.as_uri()+'?mode=ro', uri=True)) as db:
        if (history_snapshot(db, runtime['baseline']['max_rowid']) != runtime['baseline']
                or history_snapshot(db, closing_state['max_rowid']) != closing_state
                or {row[0] for row in db.execute('SELECT id FROM requests WHERE rowid>? AND rowid<=?',
                    (runtime['baseline']['max_rowid'], closing_state['max_rowid']))} != {r['request_id'] for r in requests}
                or sum(r['charged_nano_usd'] for r in requests) != audit['accounting']['own_charge_nano_usd']
                or round(owner['budget_summary']['charged_upper_bound_usd']*1e9) != closing_state['charged_nano_usd']
                or owner['budget_summary'].get('unresolved_reserved_usd') != 0):
            raise ValueError('Original closed accounting prefix/owned settlement differs')
    cleanup = _cleanup(attempt)
    expected_calls = audit['container_original_receipts']['receipts']
    if ([{'file':str(Path(r['result']['path']).relative_to(attempt/'code')), 'sha256':r['result']['sha256']}
            for r in cleanup] != [{'file':r['file'],'sha256':r['sha256']} for r in expected_calls]):
        raise ValueError('Original cold-execution closure differs')
    for case in audit['native_metadata_closure']:
        reader.scan(case)
        snapshot = reader.read(case['batch'])
        if (case['pure_replay_equal'] is not True or snapshot['attempts_claimed'] != 0
                or snapshot['active_attempt_ids'] or snapshot['active_attempt_id'] is not None
                or snapshot['micro_evolution']['pending'] is not None):
            raise ValueError('Original Native context remains occupied')
    probes = []
    native = Path('/private/tmp')/('market-rsi-'+ident)
    for stage in ('forecast', 'controller'):
        bound = reader.pin(native/f'review-01-{stage}-probe.json'); probe = reader.read(bound)
        if (probe.get('company_id') != resume.COMPANY or probe['input']['stage'] != stage
                or probe['input']['records'] != [] or probe['diagnostics']['source_sha256'] != child['R']['sha256']):
            raise ValueError('Exact real empty-state candidate probes required')
        probes.append(dict(company_id=resume.COMPANY, stage=stage, receipt=bound,
                           diagnostics=deepcopy(probe['diagnostics'])))
    result = deepcopy(inherited)
    result['reference_candidate'] = dict(axis='R', source=deepcopy(child['R']), source_delivery='paged_reference',
        reference_only=True, id=child['id'], parent=child['parent'], tests=reader.pin(attempt/'roles/author-01/cases.py'))
    result['recovery_context'] = dict(schema='earnings_population_delivery_failure_v1',
        failed_attempt=deepcopy(binding), audit=deepcopy(audit_binding), candidate_id=child['id'],
        stage='source_review', error_type='BudgetStop', observed_input_tokens=count['input_tokens'],
        prior_input_limit=runtime['limits']['review']['max_input_tokens'], review_assessment='not_generated',
        score_state='unscored', probes=probes,
        scope='Actual failed delivery and public cold tests, not an independent quality rejection, acceptance or score. Inspect period/unit/metric binding and genuine parent fallback; program-reported numeric cells alone do not prove repair. Controller may choose any active parent and R/H approach.')
    scientific_binding = plan['scientific_audit']
    if Path(scientific_binding['path']).parent != root:
        raise ValueError('Owned scientific audit reference required')
    reader.extra.add(Path(scientific_binding['path'])); scientific = reader.read(scientific_binding)
    if (scientific.get('schema') != 'earnings_population_candidate_scientific_audit_v1'
            or scientific.get('attempt_id') != ident or scientific.get('company_id') != resume.COMPANY
            or scientific['lineage']['candidate_source_sha256'] != child['R']['sha256']
            or scientific['lineage']['cases_sha256'] != result['reference_candidate']['tests']['sha256']
            or scientific['actual_cold_probes']['forecast_probe_sha256'] != probes[0]['receipt']['sha256']
            or scientific['actual_cold_probes']['controller_probe_sha256'] != probes[1]['receipt']['sha256']):
        raise ValueError('Scientific diagnostic lost actual candidate/probe joins')
    result['recovery_context']['independent_offline_observations'] = dict(
        receipt=deepcopy(scientific_binding), summary=deepcopy(scientific['summary']),
        fallback_static_finding=deepcopy(scientific['static_implementation']['fallback_static_finding']),
        qualification='Static/public cold-output audit, not the absent model review or a forecast score.')
    result['evidence'] += [binding, audit_binding, owner_bound, claim_bound, runtime_bound, *evidence,
        *[r['result'] for r in cleanup], *[r['receipt'] for r in probes]]
    return result


REVIEW_REUSE = 'review_existing_candidate_v1'
AUTHOR_CAPACITY = 'author_assembly_capacity_feedback_v1'
AUTHOR_BASE_CAPACITY = 'author_implementation_base_capacity_feedback_v1'
AUTHOR_INPUT_CAPACITY = 'author_input_capacity_feedback_v1'


def _base_capacity_delta(parent, selected, raw, *, implementation_base):
    """Verify rejected-base edits as inert text, never admit oversized code."""
    from earnings_population_delta_author import checked_base, _edit_source, _original
    from earnings_population_roles import message
    bound = checked_base(implementation_base, selected, parent)
    patch = message(raw)
    if (type(patch) is not dict or set(patch) != {'decision_sha256',
            'comparison_parent_source_sha256','implementation_base_source_sha256','edits','test_text'}
            or patch['decision_sha256'] != digest(selected)
            or patch['comparison_parent_source_sha256'] != parent['sha256']
            or patch['implementation_base_source_sha256'] != bound['sha256']
            or type(patch['test_text']) is not str
            or not 1 <= len(patch['test_text'].encode()) <= 32768):
        raise ValueError('Exact completed public implementation-base Delta required')
    original = _original(bound)
    source = _edit_source(original.decode(), patch['edits']).encode()
    if len(source) <= 65536:
        raise ValueError('A fitting program is not evidence of base source-capacity failure')
    edits = [dict(kind=row['kind'], **{key+'_utf8_bytes':len(row[key].encode())
        for key in ('old_text','new_text')}, **{key+'_sha256':hashlib.sha256(row[key].encode()).hexdigest()
        for key in ('old_text','new_text')}) for row in patch['edits']]
    return deepcopy(patch), dict(comparison_parent_utf8_bytes=len(_original(parent)),
        implementation_base_utf8_bytes=len(original), implementation_base_source_sha256=bound['sha256'],
        assembled_utf8_bytes=len(source), assembled_source_sha256=hashlib.sha256(source).hexdigest(),
        source_limit_utf8_bytes=65536,excess_utf8_bytes=len(source)-65536,
        edit_count=len(edits),edits=edits,test_text_utf8_bytes=len(patch['test_text'].encode()),
        test_text_sha256=hashlib.sha256(patch['test_text'].encode()).hexdigest())


def _closed_author_delivery(reader, attempt, runtime_bound, runtime, owner_bound, owner, audit, delivery, *, input_mode=False):
    """Read-only projection of the distinct sealed20 audit, not a new receipt."""
    terminal=audit['terminal_evidence']; final=audit['checkpoints'][-1]
    legacy=audit.get('schema')==('earnings_population_live21_closure_audit_v1' if input_mode else 'earnings_population_live20_closure_audit_v1')
    schemas=({'earnings_population_live21_closure_audit_v1','earnings_population_input_capacity_closure_audit_v1'}
             if input_mode else {'earnings_population_live20_closure_audit_v1','earnings_population_base_capacity_closure_audit_v1'})
    status=('SEALED_FAILED_AUTHOR_INPUT_BUDGETSTOP_ALL_10_FEES_SETTLED' if legacy else 'SEALED_FAILED_AUTHOR_INPUT_BUDGETSTOP_ALL_FEES_SETTLED') if input_mode else (
        'SEALED_FAILED_AUTHOR_VALUEERROR_ALL_16_FEES_SETTLED' if legacy else 'SEALED_FAILED_AUTHOR_VALUEERROR_ALL_FEES_SETTLED')
    if (audit.get('schema') not in schemas or audit.get('status') != status
            or audit.get('attempt_id') != runtime['id'] or audit.get('runtime') != runtime_bound
            or audit.get('source_commit') != runtime['source_commit']
            or str(audit.get('auditor','')).lower() in {'','root','/root'}
            or terminal['owner_terminal'] != dict(binding=owner_bound,value=owner)
            or final['owner_terminal'] != terminal['owner_terminal']
            or final['runtime'] != runtime_bound or final['source_commit'] != runtime['source_commit']
            or terminal['candidate_files'] != {'candidate.py':None,'cases.py':None}
            or terminal['code_entries'] or terminal['code_cleanup_receipts']
            or len(final['requests']) != len(final['prepared_counts'])
            or delivery.get('status') != ('SEALED_FAILED_AUTHOR_INPUT_CAPACITY_BEFORE_CODE' if input_mode
                                         else 'SEALED_FAILED_SOURCE_CAPACITY_BEFORE_CANDIDATE_REVIEW_FORECAST')
            or delivery.get('attempt_id') != runtime['id'] or delivery.get('source_commit') != runtime['source_commit']
            or delivery.get('runtime_reviewed_sha256') != runtime_bound['sha256']):
        raise ValueError('Exact sealed base-capacity failure closure required')
    roles=[]; requests=[]
    for name,key in [('controller-01','controller' if input_mode else 'controller_terminal_transport'),('author-01','author_terminal')]:
        row=delivery[key]; bound=reader.pin(attempt/'roles'/name/'result.json')
        if row['result'] != bound or row['result_value'] != reader.read(bound) or row['result_value'] != final['roles'][name]['result']:
            raise ValueError('Sealed base-capacity role result differs')
        original=row['result_value']; completed=original['turns']
        if input_mode and name=='author-01':
            final_response=original.get('final_numbered_response','')
            if re.fullmatch('[0-9]{2}-response.json',final_response) is None:
                raise ValueError('Exact last completed Author response required')
            completed=int(final_response[:2])
            if type(original['turns'])is not int or original['turns'] != completed+1:
                raise ValueError('Input stop must be the next ungenerated Author turn')
        roles.append(dict(role=name,result=bound,value=original,
                          **({'completed_turns':completed} if input_mode else {})))
    if any(type(r['value']['turns']) is not int or not 1<=r['value']['turns']<=8 for r in roles):
        raise ValueError('Exact completed bounded role turn set required')
    if len(final['requests']) != sum(r.get('completed_turns',r['value']['turns']) for r in roles):
        raise ValueError('Exact completed bounded role turn set required')
    for row in final['requests']:
        path=Path(row['binding']['path']); folder=path.parent; number=path.name[:2]
        prep=[r for r in final['prepared_counts'] if r['role']==folder.name and r['number']==number]
        if len(prep)!=1: raise ValueError('One sealed prepared count per generation required')
        prep=prep[0]; reused=reader.read(prep['reuse_binding'])
        if (prep['actual_generation_request'] != row['binding'] or prep['actual_generation_completed'] is not True
                or prep['reuse_binding'] != reader.pin(folder/(number+'-prepared-count-reuse.json'))
                or reused.get('schema') != 'earnings_prepared_count_handoff_v1'
                or reused.get('new_count_http_request') is not False or reused.get('reused_original_provider_count') is not True
                or reused.get('slot') != str(folder) or type(reused.get('turn')) is not int
                or reused['turn'] != int(number) or row['physical']['failure'] is not None):
            raise ValueError('Original prepared count/generation join differs')
        for key in ('source_context','context_receipt','count_receipt','provider_count_intent',
                    'provider_count_response','provider_count_raw','producer_source','consumer_source'):
            if reused[key] is not None: reader.read(reused[key],binary=True)
        from earnings_entry import strict_json
        import json
        payload=reader.read(row['binding'])['payload']
        counted=reader.read(reader.pin(folder/(number+'-count.json')))
        marker=reader.read(prep['consumed_marker']['binding'])
        if (reused['source_context'] != reader.pin(attempt/('context-'+folder.name.split('-')[0]+'.json'))
                or reused['producer_source'] != runtime['sources']['tools/earnings_open_context.py']
                or reused['consumer_source'] != runtime['sources']['tools/edgar_forecast_openai.py']
                or reused['request_sha256'] != hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
                or reader.read(reused['provider_count_intent'])['payload'] != payload
                or reader.read(reused['provider_count_response']) != counted or reader.read(reused['count_receipt']) != counted
                or strict_json(reader.read(reused['provider_count_raw'],binary=True)) != {k:v for k,v in counted.items() if k!='_request_id'}
                or marker != prep['consumed_marker']['value']
                or prep['consumed_marker']['binding'] != reader.pin(folder/(number+'-prepared-count-consumed.json'))
                or marker.get('schema') != 'earnings_prepared_count_consumed_v1'
                or marker.get('phase') != 'consumed_before_validation_and_reservation'):
            raise ValueError('Sealed original prepared-count receipts differ')
        requests.append(dict(request=row['binding'],count=reader.pin(folder/(number+'-count.json')),
            response=row['physical']['numbered_response'],intent=row['physical']['intent'],raw=row['physical']['raw'],
            conservative_charged_nano_usd=row['usage']['expected_conservative_charge_nano_usd'],
            matching_actual_count_origins=[reused['provider_count_intent']]))
    return dict(schema='earnings_population_live_closure_audit_v1',attempt_id=runtime['id'],
        auditor=audit['auditor'],status='SEALED_TERMINAL_IMPLEMENTATION_DELIVERY_FAILURE_ALL_FEES_SETTLED',
        terminal_evidence=dict(owner=terminal['owner_terminal'],runtime=runtime_bound,source_commit=runtime['source_commit'],
            failure=terminal['root_results']['population-run-failure.json'],roles=roles,requests=requests,
            implement_stage_failure=dict(binding=reader.pin(attempt/'loop/round-0001-implement.failed.json')),
            accounting=dict(opening=final['accounting']['opening_prefix'],closing=final['accounting']['snapshot']),
            code_execution_results=terminal['code_cleanup_receipts'],code_activation_directories=len(terminal['code_entries']),
            Native_batches=[dict(context=r['context'],batch=r['batch'],journal=r['journals']) for r in terminal['Native_batches']]))


def _base_capacity_closure(*args):
    return _closed_author_delivery(*args)


def _input_capacity_closure(*args):
    return _closed_author_delivery(*args,input_mode=True)


def _capacity_delta(parent, selected, raw):
    """One observed complete-public-append overflow; no candidate execution."""
    from earnings_population_roles import message
    patch = message(raw)
    if (type(patch) is not dict or set(patch) != {'decision_sha256','parent_source_sha256','edits','test_text'}
            or patch['decision_sha256'] != digest(selected)
            or patch['parent_source_sha256'] != parent['sha256']
            or type(patch['edits']) is not list or len(patch['edits']) != 1
            or type(patch['test_text']) is not str or not 1 <= len(patch['test_text'].encode()) <= 32768):
        raise ValueError('Exact completed public single-append Delta required')
    edit = patch['edits'][0]
    if (type(edit) is not dict or set(edit) != {'kind','old_text','new_text'}
            or edit['kind'] != 'append' or edit['old_text'] != ''
            or type(edit['new_text']) is not str or not 1 <= len(edit['new_text'].encode()) <= 65536):
        raise ValueError('Only exact nonempty original final append capacity failure is supported')
    from earnings_entry import checked
    from earnings_open_program import program
    original = checked(parent); program(original, selected['axis'])
    size = len(original)+len(edit['new_text'].encode())
    if size <= 65536:
        raise ValueError('A fitting program is not evidence of source-capacity failure')
    return deepcopy(patch), dict(parent_utf8_bytes=len(original),append_utf8_bytes=len(edit['new_text'].encode()),
        assembled_utf8_bytes=size,source_limit_utf8_bytes=65536,excess_utf8_bytes=size-65536,
        test_text_utf8_bytes=len(patch['test_text'].encode()))


def _capacity_requests(reader, runtime, audit, *, base_mode=False):
    """Verify sealed original counted physical generations and actual charges."""
    from edgar_forecast_openai import unit, token
    requests = _owned_requests(runtime)
    rows = audit['terminal_evidence']['requests']
    turns=({r['role']:r.get('completed_turns',r['value']['turns']) for r in audit['terminal_evidence']['roles']}
           if base_mode else {'controller-01':8,'author-01':8})
    if (set(turns)!={'controller-01','author-01'} or any(type(v)is not int or not 1<=v<=8 for v in turns.values())):
        raise ValueError('Exact original completed role counts required')
    expected={str(Path(runtime['root'])/'roles'/role/f'{turn:02d}-request.json')
              for role in turns for turn in range(1,turns[role]+1)}
    if (len(rows) != len(expected) or len(requests) != len(expected) or {r['request']['path'] for r in requests} != expected
            or {r['request']['path'] for r in rows} != expected):
        raise ValueError('Sealed original settled request set differs')
    evidence = []
    for own in requests:
        row = next(r for r in rows if r['request'] == own['request'])
        request = reader.read(own['request']); folder = Path(own['request']['path']).parent
        role = folder.name.split('-')[0]; limits = runtime['limits'][role]
        count = reader.read(row['count']); response = reader.read(row['response'])
        intent = reader.read(row['intent']); raw = reader.read(row['raw'])
        payload = dict(request['payload'],max_output_tokens=limits['max_output_tokens'],service_tier='default',store=False)
        if (role not in {'controller','author'} or folder.parent != Path(runtime['root'])/'roles'
                or row['count']['path'] != str(folder/(Path(own['request']['path']).name[:2]+'-count.json'))
                or row['response']['path'] != str(folder/(Path(own['request']['path']).name[:2]+'-response.json'))
                or Path(row['intent']['path']).parent != folder
                or row['raw']['path'] != row['intent']['path'].replace('.intent.json','.raw.bin')
                or intent.get('endpoint') != '/v1/responses' or intent.get('retry_allowed') is not False
                or intent.get('budget_request_id') != own['request_id']
                or intent.get('request_receipt_sha256') != own['request']['sha256']
                or intent.get('complete_reservation') != request or intent.get('payload') != payload
                or {k:v for k,v in response.items() if k!='_request_id'} != {k:v for k,v in raw.items() if k!='_request_id'}
                or response.get('status') != 'completed' or response.get('error') is not None
                or response.get('model') != runtime['rates']['api_model'] or response.get('service_tier') != 'default'
                or request['payload'].get('model') != runtime['rates']['api_model']
                or request['payload'].get('reasoning') != {'effort':runtime['role_efforts'][role]}
                or history.e.strict_json(request['payload']['input'][0]['content']) !=
                    reader.read(reader.pin(folder/'effective-input.json'))):
            raise ValueError('Exact original physical model response/role/reservation differs')
        count = token(count['input_tokens']); usage = response['usage']
        inp,out,cached = (token(usage['input_tokens']),token(usage['output_tokens']),
                          token(usage['input_tokens_details']['cached_tokens']))
        rates = runtime['rates']; rate = max(unit(rates[k]) for k in ('input','cached','write') if rates[k] is not None)
        if (count > limits['max_input_tokens'] or inp > count or cached > inp or out > limits['max_output_tokens']
                or token(usage['total_tokens']) != inp+out
                or request['reserved_nano_usd'] != count*rate+limits['max_output_tokens']*unit(rates['output'])
                or own['status'] != 'settled' or own['charged_nano_usd'] != (inp-cached)*rate+cached*unit(rates['cached'])+out*unit(rates['output'])
                or row['conservative_charged_nano_usd'] != own['charged_nano_usd']):
            raise ValueError('Original actual usage/count/settled charge differs')
        origins = row['matching_actual_count_origins']
        if not origins: raise ValueError('Original count has no physical origin')
        for bound in origins:
            counted = reader.read(bound)
            result = reader.read(reader.pin(Path(bound['path'].replace('.intent.json','.raw.bin'))))
            if (Path(bound['path']).parent != folder or counted.get('endpoint') != '/v1/responses/input_tokens'
                    or counted.get('payload') != request['payload'] or result.get('input_tokens') != count):
                raise ValueError('Original physical input-count origin differs')
        evidence += [own['request'],row['count'],row['response'],row['intent'],row['raw'],*origins]
    return evidence


def _capacity_origin(reader, runtime, study, *, root, ledger, repo):
    """Reconstruct the actual saved producer origin, including a prior failure."""
    from earnings_population_completed import load as completed, _register
    resumed=reader.read(study['campaign_resume'])
    if resumed.get('prior_failed_attempt') is not None:
        inherited=load(resumed['prior_failed_attempt'],root=root,ledger=ledger,repo=repo,
                       plan_binding=resumed['plan'],historical_reader=reader)
    else:
        inherited=completed(resumed['previous_result'],root=root,ledger=ledger,repo=repo)
    if inherited.get('previous_result') != resumed['previous_result']:
        raise ValueError('Recovered failure changed the exact completed predecessor')
    _register(reader,inherited)
    if reader.read(study['campaign_origin']) != inherited:
        raise ValueError('Exact replayed failed-window producer origin differs')
    return inherited


def _attach_capacity_failure(inherited, failure):
    """Only the newest failure carries raw edits; older ones become lessons."""
    result=deepcopy(inherited)
    if inherited.get('recovery_context',{}).get('mode') in {AUTHOR_CAPACITY,AUTHOR_BASE_CAPACITY}:
        from earnings_population_completed import _delivery_lessons
        result['delivery_lessons']=_delivery_lessons(inherited)
    result['recovery_context']=deepcopy(failure)
    return result


def latest_failed_attempt(origin):
    context=origin['recovery_context']
    return deepcopy(context.get('controller_delivery_diagnosis',context.get('input_delivery_diagnosis',context))['failed_attempt'])


def _attach_input_capacity(inherited, diagnosis):
    if (inherited.get('recovery_context',{}).get('mode') not in {AUTHOR_CAPACITY,AUTHOR_BASE_CAPACITY}
            or diagnosis.get('mode') != AUTHOR_INPUT_CAPACITY):
        raise ValueError('Verified source repair plus distinct input-delivery diagnosis required')
    result=deepcopy(inherited)
    if 'input_delivery_diagnosis' in result['recovery_context']:
        from earnings_population_completed import _delivery_lessons
        result['delivery_lessons']=_delivery_lessons(inherited)
    result['recovery_context']['input_delivery_diagnosis']=deepcopy(diagnosis)
    return result


def _input_capacity_diagnosis(reader, attempt, runtime, author_result, author_input, *, delivery):
    """Verify the blocked original count, not a new failed model generation."""
    import json
    author=attempt/'roles/author-01';turn=author_result['turns'];last=author_result['final_numbered_response']
    if (type(turn)is not int or not 2<=turn<=8 or last!=f'{turn-1:02d}-response.json'
            or author_result.get('status')!='FAILED_NO_RETRY' or author_result.get('error_type')!='BudgetStop'
            or any((author/f'{turn:02d}-{name}.json').exists() for name in ('request','response','prepared-count-reuse','prepared-count-consumed'))):
        raise ValueError('Exact ungenerated next Author input stop required')
    rows=delivery['author_terminal'][f'failed_turn{turn:02d}_contexts']
    counts=delivery['author_terminal'][f'failed_turn{turn:02d}_counts']
    actual_contexts=set(author.glob(f'{turn:02d}-context-*.json'))-{Path(r['binding']['path'])for r in counts}
    if (not rows or len(rows)!=len(actual_contexts) or len(counts)!=len(rows)
            or type(runtime['limits']['author']['max_input_tokens'])is not int
            or runtime['limits']['author']['max_input_tokens']<=0
            or {Path(r['binding']['path'])for r in rows}!=actual_contexts
            or {Path(r['binding']['path'])for r in counts}!=set(author.glob(f'{turn:02d}-context-*-count.json'))):
        raise ValueError('Exact saved failing packing context/count set required')
    intents=[(p,reader.read(reader.pin(p)))for p in author.glob('http-*.intent.json')]
    if len([p for p,x in intents if x['endpoint']=='/v1/responses'])!=turn-1:
        raise ValueError('Blocked Author turn has a generation intent')
    originals=[]
    for row,count in zip(rows,counts):
        path=Path(row['binding']['path']);context=reader.read(row['binding'])
        value=reader.read(count['binding'])
        if (path.parent!=author or re.fullmatch(f'{turn:02d}-context-[0-9]{{2}}.json',path.name)is None
                or count['binding']['path']!=str(path.with_name(path.stem+'-count.json'))
                or context!=row['value'] or context.get('schema')!='earnings_context_preparation_v1'
                or context.get('generation_not_sent')is not True
                or type(context.get('max_input_tokens'))is not int
                or context.get('max_input_tokens')!=runtime['limits']['author']['max_input_tokens']
                or type(value.get('input_tokens'))is not int or value['input_tokens']<=context['max_input_tokens']
                or value['input_tokens']!=count['input_tokens']):
            raise ValueError('Exact original overflowing Author context count required')
        matches=[(p,x)for p,x in intents if x['endpoint']=='/v1/responses/input_tokens' and
            hashlib.sha256(json.dumps(x['payload'],sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()==context['effective_request_sha256']]
        if len(matches)!=1:raise ValueError('One exact original blocked count transport required')
        p,intent=matches[0];payload=intent['payload'];raw=reader.pin(p.with_name(p.name.replace('.intent.json','.raw.bin')))
        response=reader.pin(p.with_name(p.name.replace('.intent.json','.response.json')))
        if (intent.get('retry_allowed')is not False or payload.get('model')!=runtime['rates']['api_model']
                or payload.get('reasoning')!={'effort':runtime['role_efforts']['author']}
                or history.e.strict_json(payload['input'][0]['content'])!=author_input
                or reader.read(response)!=value or reader.read(raw)!={k:v for k,v in value.items()if k!='_request_id'}):
            raise ValueError('Original overflowing payload/raw/model/input differs')
        originals.append(dict(context=row['binding'],count=count['binding'],intent=reader.pin(p),raw=raw,response=response,input_tokens=value['input_tokens']))
    return dict(schema='earnings_population_input_delivery_diagnosis_v1',mode=AUTHOR_INPUT_CAPACITY,
        blocked_turn=turn,completed_generations=turn-1,input_limit=runtime['limits']['author']['max_input_tokens'],
        observed_input_tokens=[r['input_tokens']for r in originals],count_originals=originals,
        source_context=reader.pin(attempt/'context-author.json'),stage='implement',error_type='BudgetStop',
        score_state='unscored',quality_assessment='not_run',candidate_created=False,
        scope='Original packing count exceeded its historical input ceiling before another generation. No new Delta, candidate, quality rejection or score; existing source-repair patch remains unchanged.')


def _load_author_capacity(binding, *, root, ledger, repo, plan, base_mode=False, input_mode=False):
    from earnings_population_completed import load as completed, _register, _literal, _native, _budget
    from earnings_population_roles import scientific, message
    from earnings_population_budget import AUTHORIZATION, amendment_binding
    root,ledger,repo = map(Path,(root,ledger,repo)); attempt = Path(binding['path']).parent; ident = attempt.name
    if (plan.get('id') != 'earnings-population-review-recovery-20261016'
            or plan.get('human_authorization') != AUTHORIZATION or plan.get('failed_attempt') != binding
            or base_mode and plan.get('recovery_mode') != AUTHOR_BASE_CAPACITY
            or input_mode and plan.get('recovery_mode') != AUTHOR_INPUT_CAPACITY):
        raise ValueError('Exact committed capacity-failure authority required')
    audit_bound,delivery_bound = plan['closed_failure_audit'],plan['stage_delivery_audit']
    if any(Path(b['path']).parent != root for b in (audit_bound,delivery_bound)):
        raise ValueError('Owned sealed failure and delivery audits required')
    reader = history._Reader(root,ledger,repo,ident)
    registry=ledger.parent/'.capacity-runtime-claims'; stamp=hashlib.sha256(ident.encode()).hexdigest()
    owner_bound,claim_bound=reader.pin(registry/(stamp+'.result.json')),reader.pin(registry/(stamp+'.json'))
    reader.extra.update(Path(b['path']) for b in (owner_bound,claim_bound,audit_bound,delivery_bound))
    owner,claim,audit,delivery=[reader.read(b) for b in (owner_bound,claim_bound,audit_bound,delivery_bound)]
    runtime_bound=owner['runtime']; runtime=reader.read(runtime_bound)
    if base_mode or input_mode:
        reader.register_sources(runtime)
        audit=(_input_capacity_closure if input_mode else _base_capacity_closure)(
            reader,attempt,runtime_bound,runtime,owner_bound,owner,audit,delivery)
    terminal=audit['terminal_evidence']
    if (reader.read(binding) != dict(status='FAILED_NO_RETRY',error_type='LoopHalted',native_closure=None,retry_allowed=False)
            or owner.get('status') != 'FAILED_NO_RETRY' or owner.get('error_type') != 'LoopHalted'
            or owner.get('retry_allowed') is not False or claim.get('retry_allowed') is not False
            or claim.get('runtime') != runtime_bound or claim.get('id') != ident
            or claim.get('source_commit') != runtime.get('source_commit')
            or runtime.get('schema') != 'earnings_population_runtime_v1' or runtime.get('id') != ident
            or runtime.get('root') != str(attempt) or runtime.get('ledger') != str(ledger)
            or runtime.get('companies') not in ([resume.COMPANY],[resume.COMPANY]*2)
            or runtime.get('budget_amendment') != amendment_binding()
            or audit.get('schema') != 'earnings_population_live_closure_audit_v1' or audit.get('attempt_id') != ident
            or str(audit.get('auditor','')).lower() in {'','root','/root'}
            or audit.get('status') != 'SEALED_TERMINAL_IMPLEMENTATION_DELIVERY_FAILURE_ALL_FEES_SETTLED'
            or terminal['owner'] != dict(binding=owner_bound,value=owner)
            or terminal['runtime'] != runtime_bound or terminal['source_commit'] != runtime['source_commit']
            or terminal['failure']['binding'] != binding
            or not (base_mode or input_mode) and delivery.get('status') != 'COMPLETE_FAILED_IMPLEMENT_UNSCORED'
            or delivery.get('attempt_id') != ident
            or delivery.get('source_commit') != runtime['source_commit']
            or delivery.get('runtime_reviewed_sha256') != runtime_bound['sha256']
            or not (base_mode or input_mode) and delivery['run_terminal']['population_run_failure_sha256'] != binding['sha256']
            or (attempt/'population-run-result.json').exists() or (attempt/'roles/review-01').exists()
            or any((attempt/'roles').glob('forecast-*')) or any(attempt.rglob('score.json'))):
        raise ValueError('Exact closed unscored local Author failure/owner differs')
    reader.register_sources(runtime)
    reader.extra.update(Path(runtime[k]['path']) for k in ('review','budget_amendment'))
    study=reader.read(runtime['forecast_study'])
    inherited=_capacity_origin(reader,runtime,study,root=root,ledger=ledger,repo=repo)
    resident=tasks.resident(resume.COMPANY)
    reader.extra.update(Path(b['path']) for b in (tasks.FULL_PLAN,tasks.SCORER,resident['kernel']['qa']))
    if (reader.read(study['campaign_origin']) != inherited or study.get('data') != tasks.FULL_PLAN
            or study.get('scorer') != tasks.SCORER or study.get('runtime_config') != resident['runtime']
            or study.get('cases') != [resident['case']]*len(runtime['companies'])
            or runtime.get('rates') != resident['runtime']['models']['gpt-6.1-sol']):
        raise ValueError('Verified scientific predecessor or fixed task/model differs')
    reader.scan(runtime);reader.scan(study)
    reviewed=reader.read(runtime['review']);clock=reader.pair(attempt/'clock.json')
    if (reviewed.get('verdict') != 'PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY'
            or reviewed.get('blocking_findings') != [] or reviewed.get('source_commit') != reader.commit
            or reviewed.get('reviewed_configuration_sha256') != digest({k:v for k,v in runtime.items() if k!='review'})
            or clock != reader.read(owner['clock']) or clock.get('source_commit') != reader.commit
            or clock.get('cutoff_utc') != runtime['cutoff_utc'] or clock.get('deadline_utc') != runtime['deadline_utc']):
        raise ValueError('Original reviewed configuration/source/clock differs')
    seed,outputs,evidence=_prefix(reader,runtime,attempt,failed_stage='implement')
    if terminal['implement_stage_failure']['binding'] != reader.pin(attempt/'loop/round-0001-implement.failed.json'):
        raise ValueError('Sealed exact failed implement record differs')
    state=pool.validate(inherited['population']);chosen_bound=outputs['controller']['decision'];chosen=reader.read(chosen_bound)
    selected=scientific(chosen);parent=state['versions'].get(chosen['parent_pair_sha256'])
    if (seed['population'] != state or reader.read(seed['feedback']) != inherited['research_feedback']
            or seed['last_scored_feedback'] != inherited['last_scored_feedback']
            or selected['axis'] != 'R' or parent is None or parent['id'] not in state['explorers']
            or inherited['reference_candidate']['parent'] != parent['id']
            or selected['feedback_sha256'] != digest(seed['feedback'])):
        raise ValueError('Exact unchanged scientific seed/active failed-parent lineage required')
    control,author=attempt/'roles/controller-01',attempt/'roles/author-01'
    results={row['role']:row for row in terminal['roles']}
    for name in ('controller-01','author-01'):
        row=results[name]
        if reader.pin(attempt/'roles'/name/'result.json') != row['result'] or reader.read(row['result']) != row['value']:
            raise ValueError('Sealed actual role result differs')
    if (set(results) != {'controller-01','author-01'} or results['controller-01']['value']['status'] != 'COMPLETED_DECISION'
            or results['author-01']['value']['status'] != 'FAILED_NO_RETRY'
            or results['author-01']['value']['error_type'] != ('BudgetStop' if input_mode else 'ValueError')
            or any(results[n]['value'].get('final_numbered_response') != (
                f"{results[n].get('completed_turns',results[n]['value']['turns']):02d}-response.json"
                if base_mode or input_mode else '08-response.json') for n in results)
            or any((author/name).exists() for name in ('candidate.py','cases.py','delta.json','delta-assembly.json'))):
        raise ValueError('Only complete public reply with failed local assembly, never a candidate, may transfer')
    raw_bound=reader.pin(author/'response.json');raw=reader.read(raw_bound)
    control_raw=reader.read(reader.pin(control/'response.json'))
    author_final=results['author-01']['value']['final_numbered_response']
    control_final=results['controller-01']['value']['final_numbered_response']
    if (reader.read(reader.pin(control/'decision.json')) != dict(decision=chosen,original=reader.pin(control/'response.json'))
            or message(control_raw) != chosen or reader.read(reader.pin(author/author_final)) != raw
            or reader.read(reader.pin(control/control_final)) != control_raw):
        raise ValueError('Original Controller decision or final Author response alias differs')
    author_input=reader.read(reader.pin(author/'effective-input.json'))
    if base_mode or input_mode:
        from earnings_population_delta_author import implementation_base, _original
        base=implementation_base(selected,parent,seed['feedback'],inherited['reference_candidate'])
        if (base is None or author_input.get('decision') != selected or author_input.get('implementation_base') != base
                or author_input.get('comparison_parent') != dict(version_id=parent['id'],source=parent['R'])
                or author_input.get('comparison_parent_source_sha256') != parent['R']['sha256']
                or author_input.get('implementation_base_source_sha256') != base['source']['sha256']
                or author_input.get('implementation_base_source_text') != _original(base['source']).decode()):
            raise ValueError('Exact original tested implementation base and active comparison required')
        if input_mode:
            if author_input.get('research_context',{}).get('prior_delivery_failure') != inherited.get('recovery_context'):
                raise ValueError('Exact original source-repair diagnosis must remain available')
            diagnosis=_input_capacity_diagnosis(reader,attempt,runtime,results['author-01']['value'],author_input,delivery=delivery)
        else:
            patch,capacity=_base_capacity_delta(parent['R'],selected,raw,implementation_base=base)
            sealed=delivery['failed_public_delta']
            if (sealed['raw_response_alias'] != raw_bound or sealed['original_numbered_response'] != reader.pin(author/author_final)
                    or sealed['public_delta_sha256'] != digest(patch)
                    or sealed['mechanically_reconstructed_source_utf8_bytes'] != capacity['assembled_utf8_bytes']
                    or sealed['mechanically_reconstructed_source_sha256'] != capacity['assembled_source_sha256']
                    or sealed['test_text_sha256'] != capacity['test_text_sha256']):
                raise ValueError('Sealed exact public base Delta/capacity differs')
    else:
        if (author_input.get('decision') != selected or author_input.get('parent_source') != parent['R']
                or author_input.get('parent_source_sha256') != parent['R']['sha256']):
            raise ValueError('Failed Delta must remain bound to original selected parent/decision')
        patch,capacity=_capacity_delta(parent['R'],selected,raw)
    if (not (base_mode or input_mode) and delivery['author_terminal']['final_numbered_response_sha256'] != raw_bound['sha256']
            or (delivery['controller']['decision'] != chosen_bound if input_mode else
                delivery['controller_result']['population_decision_sha256'] != chosen_bound['sha256'])):
        raise ValueError('Sealed original model delivery audit differs')
    evidence+=_capacity_requests(reader,runtime,audit,base_mode=base_mode or input_mode)
    evidence+=_budget(reader,runtime,owner,{'budget':reader.read(reader.pin(author/'budget-summary.json'))})
    if (terminal['accounting']['opening'] != runtime['baseline']
            or terminal['accounting']['closing']['charged_nano_usd'] != round(owner['budget_summary']['charged_upper_bound_usd']*1e9)
            or _cleanup(attempt) or terminal['code_execution_results'] or terminal['code_activation_directories'] != 0):
        raise ValueError('Original settled/no-execution failure closure differs')
    python=_literal(reader,runtime['sources']['tools/earnings_population_run.py'],'PYTHON')
    expected={name:dict(role=role,round_index=1,company_id=resume.COMPANY,version=version) for name,role,version in
        [('controller-01','controller',state['versions'][state['stable_id']]),('author-01','author',parent)]}
    native_evidence=_native(reader,Path('/private/tmp')/('market-rsi-'+ident),runtime_bound,runtime,expected,resident,python)
    sealed_native=[b for row in terminal['Native_batches'] for b in (row['context'],row['batch'])]
    if native_evidence != sealed_native:
        raise ValueError('Original sealed Native context/snapshot bindings differ')
    for row in terminal['Native_batches']: reader.scan(row['journal'])
    evidence+=native_evidence
    if input_mode:
        diagnosis.update(failed_attempt=deepcopy(binding),audit=audit_bound,original_decision=chosen_bound,
                         original_scientific_decision_sha256=digest(selected))
        result=_attach_input_capacity(inherited,diagnosis)
        result['evidence']+=[binding,audit_bound,delivery_bound,owner_bound,claim_bound,runtime_bound,chosen_bound,raw_bound,*evidence,
            *[b for row in diagnosis['count_originals']for k,b in row.items()if k!='input_tokens']]
        return result
    failure=dict(schema='earnings_population_delivery_failure_v1',mode=AUTHOR_BASE_CAPACITY if base_mode else AUTHOR_CAPACITY,
        failed_attempt=deepcopy(binding),audit=audit_bound,stage='implement',error_type='ValueError',
        score_state='unscored',quality_assessment='not_run',failed_parent=dict(version_id=parent['id'],source=deepcopy(parent['R'])),
        original_decision=chosen_bound,original_decision_public=deepcopy(chosen),
        original_scientific_decision_sha256=digest(selected),raw_patch_response=raw_bound,public_failed_delta=patch,
        public_failed_delta_sha256=digest(patch),capacity=capacity,
        scope='Complete original public model edits/tests failed local source capacity, not a valid candidate, independent quality rejection or score. New Controller chooses any admitted active parent and R/H/continue; old Delta remains tied to its original parent. Author may compact/refactor based on actual reference and behavior evidence; no cap raise, forced removal, adoption or gain.')
    if base_mode:
        failure['implementation_base']=deepcopy(base)
    result=_attach_capacity_failure(inherited,failure)
    result['evidence']+=[binding,audit_bound,delivery_bound,owner_bound,claim_bound,runtime_bound,chosen_bound,raw_bound,*evidence]
    return result


def _reuse_accounting(reader, runtime, owner, settlement):
    from earnings_population_reconcile import inspect_evidence
    from earnings_population_budget import validate_cap, CAP
    proof, original, request = inspect_evidence(settlement['operator_return']['evidence'])
    closed = settlement['operator_return']['after']
    if (original != runtime or settlement.get('id') != runtime['id']
            or settlement.get('original_owner_result_preserved') is not True
            or settlement['operator_return']['actual_charge_known'] is not False
            or settlement['operator_return']['refund_nano_usd'] != 0
            or settlement['operator_return']['retry_allowed'] is not False
            or settlement['operator_return']['request_id'] != request['request_id']
            or settlement['operator_return']['before'] != proof['ledger_before']
            or settlement['operator_return']['conservative_charge_nano_usd'] != request['reserved_nano_usd']
            or round(owner['budget_summary']['unresolved_reserved_usd']*1e9) != request['reserved_nano_usd']):
        raise ValueError('Exact separate conservative settlement/original pending owner required')
    requests = _owned_requests(runtime)
    ids = {row['request_id'] for row in requests}
    with closing(sqlite3.connect(reader.ledger.as_uri()+'?mode=ro', uri=True)) as db:
        db.execute('BEGIN')
        reconciliation = db.execute('SELECT evidence_sha256,prior_status,prior_charge,ceiling,policy '
            'FROM reconciliations WHERE request_id=?', (request['request_id'],)).fetchall()
        if (validate_cap(db, amendment=runtime['budget_amendment']) != CAP
                or history_snapshot(db, runtime['baseline']['max_rowid']) != runtime['baseline']
                or history_snapshot(db, closed['max_rowid']) != closed
                or {row[0] for row in db.execute('SELECT id FROM requests WHERE rowid>? AND rowid<=?',
                    (runtime['baseline']['max_rowid'], closed['max_rowid']))} != ids
                or len(ids) != len(requests)
                or reconciliation != [(settlement['operator_return']['evidence']['sha256'],
                    'uncertain', 0, request['reserved_nano_usd'], 'operator_full_ceiling_actual_charge_unknown')]
                or sum(row['charged_nano_usd'] for row in requests) != settlement['own10_charged_upper_bound_nano_usd']
                or closed['charged_nano_usd'] != runtime['baseline']['charged_nano_usd']+
                    sum(row['charged_nano_usd'] for row in requests)):
            raise ValueError('Exact historical settled request prefix/reconciliation differs')
    return [row['request'] for row in requests]


def _sealed_delivery(reader, attempt, runtime_bound, runtime, audit, delivery, chosen_bound, child):
    """Join saved model business to independently sealed physical originals."""
    from earnings_population_roles import message
    if (delivery.get('schema') != 'earnings_population_live_role_links_audit_v1'
            or delivery.get('attempt_id') != runtime['id']
            or delivery['runtime']['binding'] != runtime_bound
            or delivery['runtime']['source_commit'] != runtime['source_commit']
            or delivery['runtime']['run_closed'] is not True):
        raise ValueError('Sealed original stage-delivery identity differs')
    roles = {row['role']:row for row in audit['roles']}
    if len(roles) != 3 or set(roles) != {'controller-01','author-01','review-01'}:
        raise ValueError('Sealed original role set differs')
    for name, row in roles.items():
        if (reader.pin(attempt/'roles'/name/'result.json') != row['result']
                or reader.read(row['result']) != row['value']):
            raise ValueError('Sealed original role-result binding differs')
    c, a = delivery['controller_rounds'][0], delivery['author_rounds'][0]
    if (len(delivery['controller_rounds']) != 1 or len(delivery['author_rounds']) != 1
            or c['decision'] != chosen_bound or c['status'] != roles['controller-01']['value']['status']
            or a['result_sha256'] != roles['author-01']['result']['sha256']):
        raise ValueError('Sealed Controller/Author decision delivery differs')
    for name, final in [('controller-01',c['final_generation']),
                        ('author-01',a['completed_request_source_retention'][-1])]:
        folder = attempt/'roles'/name
        row = [r for r in audit['own_request_joins'] if r['role']==name and r['turn']==8]
        if len(row) != 1:
            raise ValueError('Exact original final-generation request required')
        row = row[0]; raw_bound = reader.pin(folder/(final['physical_prefix']+'.raw.bin'))
        request = reader.read(reader.pin(folder/'08-request.json'))
        response = reader.read(reader.pin(folder/'08-response.json'))
        intent = reader.read(row['physical_intent'])
        if (reader.pin(folder/'08-request.json')['sha256'] != final['request_sha256']
                or reader.pin(folder/'08-response.json')['sha256'] != final['response_sha256']
                or row['numbered_request_sha256'] != final['request_sha256']
                or row['response_sha256'] != final['response_sha256']
                or row['raw_sha256'] != final['physical_raw_sha256'] or raw_bound['sha256'] != row['raw_sha256']
                or row['physical_intent']['sha256'] != final['physical_intent_sha256']
                or intent['budget_request_id'] != row['request_id'] or request['request_id'] != row['request_id']
                or intent['payload'] != dict(request['payload'],max_output_tokens=runtime['limits'][name.split('-')[0]]['max_output_tokens'],
                    service_tier='default',store=False)):
            raise ValueError('Sealed original physical request/response joins differ')
        from earnings_entry import strict_json
        raw = strict_json(reader.read(raw_bound,binary=True))
        if {k:v for k,v in response.items() if k!='_request_id'} != {k:v for k,v in raw.items() if k!='_request_id'}:
            raise ValueError('Original physical response business differs')
    control = attempt/'roles/controller-01'
    projected = reader.read(reader.pin(control/'decision.json'))
    if (projected != dict(decision=reader.read(chosen_bound),original=reader.pin(control/'response.json'))
            or message(reader.read(projected['original'])) != projected['decision']
            or projected['original']['sha256'] != c['final_generation']['response_sha256']):
        raise ValueError('Original Controller raw/projection/chosen joins differ')
    fields = a['delta_delivery_and_assembly']; author = attempt/'roles/author-01'
    expected = dict(original_raw_response=reader.pin(author/'response.json'),delta_artifact=reader.pin(author/'delta.json'),
        assembly_artifact=reader.pin(author/'delta-assembly.json'),candidate_source=child['R'],test_source=reader.pin(author/'cases.py'))
    if (fields['candidate_id'] != child['id'] or any(fields[k] != v for k,v in expected.items())
            or fields['scientific_decision_projection_sha256'] != reader.pin(author/'scientific-decision-projection.json')['sha256']):
        raise ValueError('Sealed Author Delta/assembly/source/cases joins differ')


def _sealed_cleanup(audit, cleanup):
    if ([r['result'] for r in cleanup] != [r['receipt'] for r in audit['code_cleanup_receipts']]
            or any(r['cleanup_verified'] is not True or r['source_integrity_verified'] is not True
                   for r in audit['code_cleanup_receipts'])):
        raise ValueError('Sealed original code/case/probe cleanup receipt differs')


def _load_review_reuse(binding, *, root, ledger, repo, plan_binding, plan):
    from earnings_population_completed import load as completed, _register, _literal, _native
    from earnings_population_delta_author import assemble
    from earnings_population_roles import scientific, message
    from earnings_open_program import candidate, program
    from earnings_population_budget import AUTHORIZATION, amendment_binding
    from earnings_entry import checked
    root, ledger, repo = map(Path, (root, ledger, repo))
    attempt = Path(binding['path']).parent; ident = attempt.name
    reader = history._Reader(root, ledger, repo, ident)
    if (plan.get('id') != 'earnings-population-review-recovery-20261016'
            or plan.get('human_authorization') != AUTHORIZATION or plan.get('failed_attempt') != binding
            or plan.get('recovery_mode') != REVIEW_REUSE):
        raise ValueError('Exact source-bound review-only recovery authority required')
    audit_bound, settlement_bound, delivery_bound = plan['closed_failure_audit'], plan['settlement'], plan['stage_delivery_audit']
    if any(Path(b['path']).parent != root for b in (audit_bound, settlement_bound, delivery_bound)):
        raise ValueError('Owned immutable closure/settlement receipts required')
    registry = ledger.parent/'.capacity-runtime-claims'; token = hashlib.sha256(ident.encode()).hexdigest()
    owner_bound, claim_bound = reader.pin(registry/(token+'.result.json')), reader.pin(registry/(token+'.json'))
    reader.extra.update(Path(b['path']) for b in (owner_bound, claim_bound, audit_bound, settlement_bound, delivery_bound))
    owner, claim, audit, settlement = [reader.read(b) for b in
        (owner_bound, claim_bound, audit_bound, settlement_bound)]
    runtime_bound = owner['runtime']; runtime = reader.read(runtime_bound)
    delivery = reader.read(delivery_bound)
    if (runtime.get('id') != ident or runtime.get('root') != str(attempt)
            or runtime.get('ledger') != str(ledger) or runtime.get('schema') != 'earnings_population_runtime_v1'
            or runtime.get('companies') not in ([resume.COMPANY], [resume.COMPANY]*2)
            or owner.get('status') != 'FAILED_NO_RETRY' or owner.get('error_type') != 'LoopHalted'
            or owner.get('retry_allowed') is not False or claim.get('runtime') != runtime_bound
            or claim.get('id') != ident or claim.get('source_commit') != runtime.get('source_commit')
            or claim.get('retry_allowed') is not False
            or reader.read(binding) != dict(status='FAILED_NO_RETRY', error_type='LoopHalted',
                native_closure=None, retry_allowed=False)
            or (attempt/'population-run-result.json').exists() or any((attempt/'roles').glob('forecast-*'))
            or any(attempt.rglob('score.json')) or runtime.get('budget_amendment') != amendment_binding()
            or audit.get('schema') != 'earnings_population_live_closure_audit_v1'
            or audit.get('attempt_id') != ident or audit.get('auditor') in ('', 'Root', 'root', '/root', None)
            or audit['loop_failure']['binding'] != binding or audit['owner']['binding'] != owner_bound
            or audit['runtime_and_clock']['runtime'] != runtime_bound):
        raise ValueError('Exact closed unscored Review-delivery failure/owner required')
    reader.register_sources(runtime)
    reader.extra.update(Path(runtime[k]['path']) for k in ('review','budget_amendment'))
    study = reader.read(runtime['forecast_study']); resumed = reader.read(study['campaign_resume'])
    inherited = completed(resumed['previous_result'], root=root, ledger=ledger, repo=repo)
    _register(reader, inherited)
    if reader.read(study['campaign_origin']) != inherited:
        raise ValueError('Exact completed scientific predecessor changed')
    resident = tasks.resident(resume.COMPANY)
    reader.extra.update(Path(b['path']) for b in (tasks.FULL_PLAN, tasks.SCORER, resident['kernel']['qa']))
    if (study.get('data') != tasks.FULL_PLAN or study.get('scorer') != tasks.SCORER
            or study.get('runtime_config') != resident['runtime']
            or study.get('cases') != [resident['case']]*len(runtime['companies'])
            or runtime.get('rates') != resident['runtime']['models']['gpt-6.1-sol']):
        raise ValueError('Original development task/data/scorer/model changed')
    reader.scan(runtime); reader.scan(study)
    review = reader.read(runtime['review'])
    if (review.get('verdict') != 'PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY'
            or review.get('blocking_findings') != [] or review.get('source_commit') != reader.commit
            or review.get('reviewed_configuration_sha256') != digest({k:v for k,v in runtime.items() if k != 'review'})
            or reader.pair(attempt/'clock.json') != reader.read(owner['clock'])):
        raise ValueError('Original configuration/source/clock review differs')
    seed, outputs, evidence = _prefix(reader, runtime, attempt)
    state = pool.validate(inherited['population']); child = outputs['implement']['candidate']
    chosen = reader.read(outputs['controller']['decision']); parent = state['versions'].get(child['parent'])
    if (seed['population'] != state or seed['feedback'] != reader.read(study['campaign'])['initial_feedback']
            or parent is None or parent['id'] not in [state['stable_id'],*state['explorers']]
            or child['axis'] != 'R' or child['parent'] != chosen['parent_pair_sha256']
            or child['H'] != parent['H'] or child['id'] in state['versions']
            or child != pool.version(**{k:child[k] for k in ('R','H','parent','axis','method','author','evidence')})
            or child['author'] != 'model:DeltaAuthor'):
        raise ValueError('Exact successful unretained R candidate and active parent required')
    author = attempt/'roles/author-01'; reviewer = attempt/'roles/review-01'
    role_results = {name:reader.read(reader.pin(attempt/'roles'/name/'result.json'))
                    for name in ('controller-01','author-01','review-01')}
    _sealed_delivery(reader,attempt,runtime_bound,runtime,audit,delivery,outputs['controller']['decision'],child)
    if (role_results['controller-01'].get('status') != 'COMPLETED_DECISION'
            or role_results['author-01'].get('status') != 'COMPLETED_CANDIDATE'
            or role_results['review-01'].get('status') != 'FAILED_NO_RETRY'
            or role_results['review-01'].get('error_type') != 'BudgetStop'
            or role_results['review-01'].get('final_numbered_response') != '07-response.json'
            or role_results['review-01'].get('wall_seconds',0) < runtime['limits']['review']['wall_seconds']
            or (reviewer/'08-response.json').exists() or (reviewer/'review.json').exists()
            or reader.read(reader.pin(reviewer/'08-count.json'))['input_tokens'] > runtime['limits']['review']['max_input_tokens']):
        raise ValueError('Only completed Author and absent final Review verdict may transfer')
    raw_bound = reader.pin(author/'response.json'); raw = reader.read(raw_bound)
    projection = reader.read(reader.pin(author/'scientific-decision-projection.json'))
    selected = scientific(chosen); assembly_bound = reader.pin(author/'delta-assembly.json')
    assembly = reader.read(assembly_bound); tests = reader.pin(author/'cases.py')
    business = assemble(parent['R'], selected, raw)
    if (reader.read(reader.pin(author/'08-response.json')) != raw
            or reader.read(reader.pin(author/'delta.json')) != dict(delta=message(raw), original=raw_bound)
            or projection['population_decision'] != chosen or projection['scientific_decision'] != selected
            or assembly.get('parent_source') != parent['R'] or assembly.get('parent_version_id') != parent['id']
            or assembly.get('raw_patch_response') != raw_bound or assembly.get('source') != child['R']
            or assembly.get('tests') != tests or assembly.get('assembled_business_sha256') != digest(business)
            or assembly.get('scientific_decision_sha256') != digest(selected)
            or assembly['assembly_source']['module'] != runtime['sources']['tools/earnings_population_delta_author.py']
            or reader.read(child['R'], binary=True) != business['source_text'].encode()
            or reader.read(tests, binary=True) != business['test_text'].encode()):
        raise ValueError('Original raw Delta/decision/parent/assembly/source/tests joins differ')
    parsed = candidate(business, program(checked(parent['R']),'R'), selected)
    if plan.get('successful_candidate') != dict(id=child['id'], source_sha256=child['R']['sha256'],
            tests_sha256=tests['sha256'], raw_patch_sha256=raw_bound['sha256'], assembly_sha256=assembly_bound['sha256']):
        raise ValueError('Exact committed successful candidate bytes/provenance differ')
    probes = []
    native = Path('/private/tmp')/('market-rsi-'+ident)
    cases_bound = reader.pin(native/'review-01-cases.json'); cases = reader.read(cases_bound)
    if (cases['candidate_id'] != child['id'] or len(cases['results']) != len(parsed['cases'])
            or not cases['results'] or not all(r['passed'] is True for r in cases['results'])):
        raise ValueError('Original authored cases did not pass')
    import earnings_open_researcher as researcher
    for case, result in zip(parsed['cases'], cases['results']):
        if digest(researcher.execution_value(result['execution'],business['source_text'],case['input'])) != digest(case['expected']):
            raise ValueError('Original source/input/output case receipt differs')
    for stage in ('forecast','controller'):
        bound = reader.pin(native/f'review-01-{stage}-probe.json'); probe = reader.read(bound)
        if (probe.get('company_id') != resume.COMPANY or probe['input']['stage'] != stage
                or probe['input']['records'] != [] or probe['diagnostics']['source_sha256'] != child['R']['sha256']):
            raise ValueError('Original exact-source empty-state cold probes required')
        researcher.verify(probe['execution'], business['source_text'], probe['input'], resident['company'])
        if probe['diagnostics']['execution_sha256'] != probe['execution']['receipt']['sha256']:
            raise ValueError('Original cold-probe execution binding differs')
        probes.append(dict(company_id=resume.COMPANY, stage=stage, receipt=bound, diagnostics=deepcopy(probe['diagnostics'])))
    cleanup = _cleanup(attempt)
    _sealed_cleanup(audit,cleanup)
    for row in audit['native_batches']:
        reader.scan(row)
    python = _literal(reader,runtime['sources']['tools/earnings_population_run.py'],'PYTHON')
    expected = {name:dict(role=role, round_index=1, company_id=resume.COMPANY, version=version)
        for name,role,version in [('controller-01','controller',state['versions'][state['stable_id']]),
            ('author-01','author',parent),('review-01','review',child)]}
    evidence += _native(reader,native,runtime_bound,runtime,expected,resident,python)
    evidence += _reuse_accounting(reader,runtime,owner,settlement)
    bundle = dict(schema='earnings_population_author_stage_reuse_v1', mode=REVIEW_REUSE,
        candidate=deepcopy(child), decision=outputs['controller']['decision'], scientific_decision=selected,
        raw_patch_response=raw_bound, assembly=assembly_bound, tests=tests, source=child['R'],
        parent_source=parent['R'], cases=cases_bound, probes=probes, failed_attempt=deepcopy(binding),
        new_model_Controller_called=False, new_model_Author_called=False)
    result = deepcopy(inherited)
    result.update(author_stage_reuse=bundle, pre_recovery_reference_candidate=deepcopy(inherited['reference_candidate']),
        reference_candidate=dict(axis='R', source=child['R'],
        source_delivery='paged_reference', reference_only=True, id=child['id'], parent=child['parent'], tests=tests),
        recovery_context=dict(schema='earnings_population_delivery_failure_v1', failed_attempt=deepcopy(binding),
            audit=audit_bound, candidate_id=child['id'], stage='source_review', error_type='BudgetStop',
            observed_input_tokens=reader.read(reader.pin(reviewer/'08-count.json'))['input_tokens'],
            prior_input_limit=runtime['limits']['review']['max_input_tokens'], review_assessment='not_completed',
            completed_Review_generations=7, score_state='unscored', probes=probes,
            scope='Failed final Review delivery, not quality rejection or score. Successful Author stage reused explicitly; fresh real review/tests required.'))
    result['evidence'] += [binding,audit_bound,settlement_bound,delivery_bound,owner_bound,claim_bound,runtime_bound,
        raw_bound,assembly_bound,tests,cases_bound,*[p['receipt'] for p in probes],
        *[r['result'] for r in cleanup],*evidence]
    return result


def _dispatch_load(binding, *, root, ledger, repo, plan_binding, historical_reader=None):
    # Preserve the original05 verifier and original historical Git-plan bytes.
    # Scope malformed callers through the unchanged legacy early guards.
    if (type(binding) is not dict or set(binding) != {'path','sha256'}
            or type(plan_binding) is not dict or set(plan_binding) != {'path','sha256'}
            or any(type(b.get('sha256')) is not str or re.fullmatch('[0-9a-f]{64}',b['sha256']) is None
                   for b in (binding,plan_binding))
            or Path(root) != resume.OWNED or Path(ledger) != resume.LEDGER or Path(repo) != resume.REPO
            or not _plan_matches(plan_binding, Path(repo), historical_reader)
            or type(binding.get('path')) is not str
            or Path(binding['path']).parent.parent != resume.OWNED/'attempts'
            or Path(binding['path']).resolve() != Path(binding['path'])
            or Path(binding['path']).name != 'population-run-failure.json'):
        return _legacy_load(binding,root=root,ledger=ledger,repo=repo,plan_binding=plan_binding,historical_reader=historical_reader)
    plan = _read_plan(plan_binding,root=Path(root),ledger=Path(ledger),repo=Path(repo),historical_reader=historical_reader)
    from earnings_population_controller_import import MODE as CONTROLLER_IMPORT,load as controller_import
    if plan.get('recovery_mode') == CONTROLLER_IMPORT:
        return controller_import(binding,root=root,ledger=ledger,repo=repo,plan=plan)
    from earnings_population_reused_review_failure import MODE as REUSED_REVIEW_FAILURE, load as reused_review_failure
    if plan.get('recovery_mode') == REUSED_REVIEW_FAILURE:
        return reused_review_failure(binding,root=root,ledger=ledger,repo=repo,plan=plan)
    from earnings_population_forecast_failure import MODE as FORECAST_FAILURE, load as forecast_failure
    if plan.get('recovery_mode') == FORECAST_FAILURE:
        return forecast_failure(binding,root=root,ledger=ledger,repo=repo,plan=plan)
    if plan.get('recovery_mode') == REVIEW_REUSE:
        from earnings_population_review23_origin import IDENT as REVIEW23, load as review23
        if (type(plan.get('failed_attempt')) is dict
                and plan['failed_attempt'].get('path') == str(Path(root)/'attempts'/REVIEW23/'population-run-failure.json')):
            return review23(binding,root=root,ledger=ledger,repo=repo,plan=plan)
        return _load_review_reuse(binding,root=root,ledger=ledger,repo=repo,plan_binding=plan_binding,plan=plan)
    if plan.get('recovery_mode') == AUTHOR_CAPACITY:
        return _load_author_capacity(binding,root=root,ledger=ledger,repo=repo,plan=plan)
    if plan.get('recovery_mode') == AUTHOR_BASE_CAPACITY:
        return _load_author_capacity(binding,root=root,ledger=ledger,repo=repo,plan=plan,base_mode=True)
    if plan.get('recovery_mode') == AUTHOR_INPUT_CAPACITY:
        return _load_author_capacity(binding,root=root,ledger=ledger,repo=repo,plan=plan,input_mode=True)
    return _legacy_load(binding,root=root,ledger=ledger,repo=repo,plan_binding=plan_binding,historical_reader=historical_reader)


def load(binding, *, root, ledger, repo, plan_binding, historical_reader=None):
    """Bound one nested failure chain, including interleaved completed replay."""
    path=binding.get('path') if type(binding)is dict else None
    if type(path)is not str:
        return _dispatch_load(binding,root=root,ledger=ledger,repo=repo,
                              plan_binding=plan_binding,historical_reader=historical_reader)
    chain=_FAILURE_ANCESTRY.get()
    if path in chain or len(chain)>=50:
        raise ValueError('Canonical noncyclic bounded failed-window ancestry required')
    token=_FAILURE_ANCESTRY.set((*chain,path))
    try:
        return _dispatch_load(binding,root=root,ledger=ledger,repo=repo,
                              plan_binding=plan_binding,historical_reader=historical_reader)
    finally:
        _FAILURE_ANCESTRY.reset(token)


def verify_reused_stages(reader, attempt, rows, origin):
    """Replay explicit trusted stage reuse, never infer two new model calls."""
    bundle = origin.get('author_stage_reuse')
    if bundle is None:
        return
    packet_bound = rows['input']['packet']; packet = reader.read(packet_bound)
    chosen_bound = rows['controller']['decision']; chosen = reader.read(chosen_bound)
    expected = reader.read(bundle['decision']); expected['feedback_sha256'] = digest(packet['feedback'])
    c = attempt/'roles/controller-01'; a = attempt/'roles/author-01'
    if bundle.get('implementation_base') is not None or origin.get('training_stage_attachment') is not None:
        c_bound, a_bound = reader.pin(c/'controller-stage-reuse.json'), reader.pin(a/'author-stage-reuse.json')
        if (rows['controller'].get('stage_reuse') != c_bound
                or rows['controller'].get('artifacts') != [chosen_bound, c_bound]
                or rows['implement'].get('stage_reuse') != a_bound
                or rows['implement'].get('artifacts') != [a_bound]):
            raise ValueError('New v2 reused stages require durable original receipt bindings')
    control = reader.read(reader.pin(c/'controller-stage-reuse.json'))
    author = reader.read(reader.pin(a/'author-stage-reuse.json'))
    if (chosen != expected or rows['implement']['candidate'] != bundle['candidate']
            or control.get('schema') != 'earnings_population_Controller_stage_reuse_v1'
            or control.get('mode') != bundle['mode'] or author.get('mode') != bundle['mode']
            or control.get('new_model_called') is not False or control.get('routing_author') != 'trusted_recovery_adapter'
            or control.get('original_decision') != bundle['decision'] or control.get('decision') != chosen_bound
            or control.get('packet') != packet_bound or control.get('source_attempt') != bundle['failed_attempt']
            or author.get('schema') != 'earnings_population_Author_stage_reuse_v1'
            or author.get('new_model_called') is not False or author.get('candidate_id') != bundle['candidate']['id']
            or author.get('original_decision') != bundle['decision'] or author.get('source_attempt') != bundle['failed_attempt']
            or author.get('scientific_decision_sha256') != digest(bundle['scientific_decision'])
            or any(author.get(key) != bundle[key] for key in ('raw_patch_response','assembly','source','tests'))
            or any(author.get(key) != bundle.get(key) for key in ('implementation_base','original_controller_import'))
            or any(p.exists() for path in (c,a) for name in ('response.json','result.json') for p in [path/name])
            or any(list(path.glob('http-*')) or list(path.glob('[0-9][0-9]-request.json')) for path in (c,a))):
        raise ValueError('Explicit successful-stage reuse/unchanged science/no-model evidence differs')
    if origin.get('review_stage_reuse') is not None:
        from earnings_population_forecast_failure import verify_reused_review
        verify_reused_review(reader,attempt,rows,origin)


def _training_attachment_input(binding, *, completed_result, training_scope, company_id,
                               attempt_id, root, ledger, repo, plan_binding, historical_reader=None):
    import earnings_population_training25 as training
    training.admit(training_scope,company_id)  # Before input or any task/source body.
    root,ledger,repo = map(Path,(root,ledger,repo))
    if (root != training.ROOT or ledger != resume.LEDGER or repo != resume.REPO
            or any(p.resolve() != p for p in (root,ledger,repo))):
        raise ValueError('Exact existing training owner roots required')
    spec = training.stage_attachment_policy(plan_binding,repo=repo,attempt_id=attempt_id,
        company_id=company_id,attachment_binding=binding,historical_reader=historical_reader)
    if spec is None:raise ValueError('Explicit same-task stage attachment authority required')
    value = training._read(binding);authority = training._read(spec['authority'])
    fields = {'schema','mode','authority','completed_origin','failed_attempt','closed_failure_audit',
              'stage_delivery_audit','company_id','candidate_id','source','tests','accepted_review'}
    if (type(value) is not dict or set(value) != fields or value['schema'] != training.STAGE_ATTACHMENT_SCHEMA
            or any(type(value[k]) is not dict or set(value[k]) != {'path','sha256'} or type(value[k]['path']) is not str
                   or type(value[k]['sha256']) is not str or re.fullmatch('[0-9a-f]{64}',value[k]['sha256']) is None
                   for k in ('authority','completed_origin','failed_attempt','closed_failure_audit','stage_delivery_audit','source','tests','accepted_review'))
            or value['mode'] != training.STAGE_ATTACHMENT_MODE or value['authority'] != spec['authority']
            or value['completed_origin'] != completed_result or value['company_id'] != company_id
            or type(authority) is not dict or authority.get('schema') != 'earnings_training25_closed_successful_stage_attachment_authority_v1'
            or authority.get('human_answer') != '授权窄化复用35候选，审查通过后直接预测'
            or authority.get('candidate_pair') != value['candidate_id']
            or authority.get('researcher_sha256') != value['source'].get('sha256')):
        raise ValueError('Exact public successful-stage attachment metadata differs')
    attempt = root/'attempts'/authority['failed_attempt']
    expected = {'failed_attempt':attempt/'population-run-failure.json','source':attempt/'roles/author-01/candidate.py',
                'tests':attempt/'roles/author-01/cases.py','accepted_review':attempt/'roles/review-01/review.json'}
    for name,path in expected.items():
        if type(value[name]) is not dict or set(value[name]) != {'path','sha256'} or value[name]['path'] != str(path):
            raise ValueError('Exact original successful-stage sibling required')
    if (type(completed_result) is not dict or Path(completed_result['path']).parent.parent != root/'attempts'
            or Path(completed_result['path']).name != 'population-run-result.json'
            or any(type(value[k]) is not dict or Path(value[k]['path']).parent != root
                   for k in ('closed_failure_audit','stage_delivery_audit'))):
        raise ValueError('Completed predecessor and original owned audits required')
    return value


def _training_attachment_physical(reader, runtime, audit):
    from edgar_forecast_openai import token,unit
    owned = _owned_requests(runtime);rows = audit['requests'];evidence = []
    if len(rows) != len(owned) or len(rows) != sum(v['generations'] for v in audit['role_totals'].values()):
        raise ValueError('Exact complete settled original role transcript required')
    for own in owned:
        folder = Path(own['request']['path']).parent;number = Path(own['request']['path']).name[:2];role = folder.name.split('-')[0]
        matches = [r for r in rows if r['role'] == folder.name and type(r['turn']) is int and r['turn'] == int(number)]
        if len(matches) != 1:raise ValueError('One original physical row required')
        row = matches[0];request = reader.read(own['request']);payload = request['payload'];limits = runtime['limits'][role]
        def original(key):
            bound = dict(path=str(folder/row[key]['filename']),sha256=row[key]['sha256'])
            if Path(bound['path']).parent != folder:raise ValueError('Original physical sibling required')
            return bound,reader.read(bound)
        request_bound,_ = original('request');intent_bound,intent = original('physical_intent')
        raw_bound,raw = original('physical_raw');response_bound,response = original('response');sidecar_bound,sidecar = original('physical_response')
        if (request_bound != own['request'] or row['request_id'] != own['request_id']
                or intent.get('endpoint') != '/v1/responses' or intent.get('retry_allowed') is not False
                or intent.get('complete_reservation') != request or intent.get('budget_request_id') != own['request_id']
                or intent.get('request_receipt_sha256') != own['request']['sha256']
                or intent.get('payload') != dict(payload,max_output_tokens=limits['max_output_tokens'],service_tier='default',store=False)
                or raw_bound['path'] != intent_bound['path'].replace('.intent.json','.raw.bin')
                or sidecar_bound['path'] != intent_bound['path'].replace('.intent.json','.response.json')
                or response_bound != reader.pin(folder/(number+'-response.json')) or response != sidecar
                or {k:v for k,v in response.items() if k != '_request_id'} != raw
                or response.get('status') != 'completed' or response.get('model') != runtime['rates']['api_model']
                or payload.get('reasoning') != {'effort':runtime['role_efforts'][role]}
                or history.e.strict_json(payload['input'][0]['content']) != reader.read(reader.pin(folder/'effective-input.json'))):
            raise ValueError('Original physical request/payload/source/response differs')
        counted = reader.read(reader.pin(folder/(number+'-count.json')));count = token(counted['input_tokens'])
        usage = response['usage'];inp,out,cached = token(usage['input_tokens']),token(usage['output_tokens']),token(usage['input_tokens_details']['cached_tokens'])
        rates = runtime['rates'];rate = max(unit(rates[k]) for k in ('input','cached','write') if rates[k] is not None)
        charge = (inp-cached)*rate+cached*unit(rates['cached'])+out*unit(rates['output'])
        if (count > limits['max_input_tokens'] or inp > count or cached > inp or out > limits['max_output_tokens']
                or token(usage['total_tokens']) != inp+out or own['status'] != 'settled'
                or request['reserved_nano_usd'] != count*rate+limits['max_output_tokens']*unit(rates['output'])
                or own['charged_nano_usd'] != charge or row['computed_conservative_nano_usd'] != charge):
            raise ValueError('Original count/reservation/usage/settlement differs')
        reused_bound = reader.pin(folder/(number+'-prepared-count-reuse.json'));reused = reader.read(reused_bound)
        marker_bound = reader.pin(folder/(number+'-prepared-count-consumed.json'));marker = reader.read(marker_bound)
        if (reused.get('schema') != 'earnings_prepared_count_handoff_v1' or reused.get('slot') != str(folder)
                or type(reused.get('turn')) is not int or reused['turn'] != int(number)
                or reused.get('new_count_http_request') is not False or reused.get('reused_original_provider_count') is not True
                or reused['source_context'] != reader.pin(Path(runtime['root'])/('context-'+role+'.json'))
                or reused['producer_source'] != runtime['sources']['tools/earnings_open_context.py']
                or reused['consumer_source'] != runtime['sources']['tools/edgar_forecast_openai.py']
                or reused['request_sha256'] != hashlib.sha256(__import__('json').dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
                or reader.read(reused['provider_count_intent'])['payload'] != payload
                or reader.read(reused['provider_count_response']) != counted or reader.read(reused['count_receipt']) != counted
                or reader.read(reused['provider_count_raw']) != {k:v for k,v in counted.items() if k != '_request_id'}
                or marker.get('phase') != 'consumed_before_validation_and_reservation'):
            raise ValueError('Original prepared-count source/single-use provenance differs')
        reader.scan(reused);evidence += [request_bound,intent_bound,raw_bound,response_bound,sidecar_bound,reused_bound,marker_bound]
    return evidence


def _training_attachment_native(reader, runtime_bound, runtime, expected, resident, scope):
    import fcntl,os
    from earnings_population_completed import _native_identity,_literal
    from earnings_population_window import start_utc
    from supervisor_harness.continuous_discovery_batch import ContinuousDiscoveryBatch
    from supervisor_harness import capacity_feedback_engine as engine
    native = Path('/private/tmp')/('market-rsi-'+runtime['id']);paths = sorted(native.glob('*/context.json'));evidence = []
    if {p.parent.name for p in paths} != set(expected):raise ValueError('Exactly four original empty Native contexts required')
    python = _literal(reader,runtime['sources']['tools/earnings_population_run.py'],'PYTHON')
    for path in paths:
        selected = expected[path.parent.name];value = reader.read(reader.pin(path))
        if (value.get('authority') != runtime_bound or value.get('source_commit') != runtime['source_commit']
                or value.get('pool_version') != selected['version']
                or value.get('window') != dict(start_utc=start_utc(runtime),deadline_utc=runtime['deadline_utc'])
                or str(Path(runtime['root'])/'roles'/path.parent.name) not in runtime['slots'][selected['role']]):
            raise ValueError('Original empty Native authority/selection/window differs')
        fixed = _native_identity(reader,path,value,selected,runtime_bound,runtime,resident,python,training_scope=scope)
        batch = ContinuousDiscoveryBatch(path.parent/'batch',allow_temporary=True)
        with os.fdopen(os.open(batch.lock_path,os.O_RDONLY|os.O_NOFOLLOW),'rb') as stream:
            fcntl.flock(stream,fcntl.LOCK_SH|fcntl.LOCK_NB)
            records = batch._read_records();saved = batch._read_snapshot();replayed = batch._replay(records)
        if (saved != replayed or not saved['initialized'] or saved['attempts_claimed'] != 0
                or saved['active_attempt_ids'] or saved['active_attempt_id'] is not None or saved.get('capacity_work',[])
                or saved['micro_evolution']['pending'] is not None
                or saved['micro_evolution']['active_pair'] != engine.activation.pair(value['manifest'])
                or saved['micro_evolution']['fixed_context'] != fixed):
            raise ValueError('All original Native roles must be independently empty, not failed/completed work')
        evidence += [reader.pin(path),reader.pin(batch.snapshot_path)]
    return evidence


def _verify_training_stage_attachment(binding, *, base_origin, training_scope, company_id,
        attempt_id, root, ledger, repo, plan_binding, historical_reader=None):
    """Private: caller must have just completed the trusted predecessor replay."""
    import earnings_population_training25 as training
    from earnings_population_completed import _register,_training,_budget
    from earnings_population_delta_author import assemble
    from earnings_population_roles import message,scientific
    from earnings_open_program import candidate,program
    from earnings_population_forecast_failure import _accepted
    import earnings_open_researcher as researcher
    value = _training_attachment_input(binding,completed_result=base_origin['previous_result'],training_scope=training_scope,
        company_id=company_id,attempt_id=attempt_id,root=root,ledger=ledger,repo=repo,plan_binding=plan_binding,historical_reader=historical_reader)
    root,ledger,repo = map(Path,(root,ledger,repo));attempt = Path(value['failed_attempt']['path']).parent
    reader = history._Reader(root,ledger,repo,attempt.name);reader.extra.update(Path(value[k]['path']) for k in ('closed_failure_audit','stage_delivery_audit','authority'))
    audit,delivery = [reader.read(value[k]) for k in ('closed_failure_audit','stage_delivery_audit')]
    identity = audit['current_role_identity_and_owner'];owner_bound,claim_bound = identity['owner_terminal'],identity['owner_claim']
    registry = ledger.parent/'.capacity-runtime-claims';stamp = hashlib.sha256(attempt.name.encode()).hexdigest()
    if (owner_bound['path'] != str(registry/(stamp+'.result.json')) or claim_bound['path'] != str(registry/(stamp+'.json'))):
        raise ValueError('Exact original owner registry receipts required')
    reader.extra.update(Path(b['path']) for b in (owner_bound,claim_bound));owner,claim = reader.read(owner_bound),reader.read(claim_bound)
    runtime_bound = audit['runtime'];runtime = reader.read(runtime_bound);failure = reader.read(value['failed_attempt'])
    if (runtime.get('schema') != 'earnings_population_runtime_v1' or runtime.get('id') != attempt.name or runtime.get('root') != str(attempt) or runtime.get('companies') != [company_id]
            or runtime.get('training_policy') != training.POLICY or runtime.get('ledger') != str(ledger)
            or owner.get('runtime') != runtime_bound or owner.get('status') != 'FAILED_NO_RETRY'
            or owner.get('error_type') != 'LoopHalted' or owner.get('retry_allowed') is not False
            or claim.get('id') != attempt.name or claim.get('retry_allowed') is not False
            or claim.get('runtime') != runtime_bound or claim.get('source_commit') != runtime['source_commit']
            or failure != dict(status='FAILED_NO_RETRY',error_type='LoopHalted',retry_allowed=False,native_closure=dict(error_type='ValueError',status='UNRESOLVED_NO_RETRY'))
            or audit.get('schema') != 'earnings_training25_live_closure_audit_v1'
            or audit.get('status') != 'SEALED_FAILED_BEFORE_FORECAST_CLAIM_ALL_FEES_SETTLED_NO_ACTIVE_NATIVE_WORK'
            or audit.get('attempt_id') != attempt.name or audit.get('source_commit') != runtime['source_commit']
            or str(audit.get('auditor','')).lower() in {'','root','/root'}
            or set(audit.get('role_totals',{})) != {'controller-01','author-01','review-01'}
            or audit.get('owner_failure') != value['failed_attempt'] or audit.get('owner_failure_metadata') != failure
            or audit.get('root_process_terminal_confirmed') is not True or audit.get('forecast_generation_count') != 0
            or audit.get('own_pending_nano_usd') != 0 or audit.get('all_pending_count') != 0
            or delivery.get('schema') != 'earnings_training25_live_role_links_v1'
            or delivery.get('status') != 'SEALED_FAILED_BEFORE_FIRST_FORECAST_CLAIM_REVIEW_ACCEPTED_NO_SCORES'
            or delivery.get('runtime') != runtime_bound or delivery.get('source_commit') != runtime['source_commit']):
        raise ValueError('Exact closed preclaim training failure and independently sealed evidence required')
    reader.register_sources(runtime);_register(reader,base_origin,training_scope=training_scope)
    study = reader.read(runtime['forecast_study']);_training(reader,runtime,study,inherited=base_origin)
    resident = tasks.resident(company_id);reader.extra.update(Path(b['path']) for b in (tasks.FULL_PLAN,tasks.SCORER,resident['kernel']['qa']))
    seed,outputs,evidence = _prefix(reader,runtime,attempt,failed_stage='execute',failure_kind=training.STAGE_ATTACHMENT_MODE)
    state = pool.validate(base_origin['population']);chosen_bound = outputs['controller']['decision'];chosen = reader.read(chosen_bound);child = outputs['implement']['candidate']
    packet = reader.read(outputs['input']['packet'])
    parent = state['versions'].get(chosen.get('parent_pair_sha256'));folder = attempt/'roles/author-01'
    if (seed['population'] != state or reader.read(seed['feedback']) != base_origin['research_feedback']
            or seed['last_scored_feedback'] != base_origin['last_scored_feedback'] or parent is None
            or packet.get('population') != state or packet.get('feedback') != seed['feedback']
            or packet.get('company_id') != company_id or packet.get('round_index') != 1
            or packet.get('parent_feedback_sha256') != digest(seed['feedback'])
            or chosen.get('axis') != 'R' or chosen.get('feedback_sha256') != digest(seed['feedback'])
            or parent['id'] not in [state['stable_id'],*state['explorers']] or child['parent'] != parent['id']
            or child['axis'] != chosen['axis'] or child['method'] != chosen['hypothesis'] or child['H'] != parent['H'] or child['id'] != value['candidate_id'] or child['id'] in state['versions']
            or child['R'] != value['source'] or child['author'] != 'model:DeltaAuthor'
            or child != pool.version(**{k:child[k] for k in ('R','H','parent','axis','method','author','evidence')})):
        raise ValueError('Exact unchanged completed pool and unadopted active-parent R candidate required')
    selected = scientific(chosen);raw = reader.pin(folder/'response.json');assembly_bound = reader.pin(folder/'delta-assembly.json');assembly = reader.read(assembly_bound)
    projection = reader.pin(folder/'scientific-decision-projection.json');business = assemble(parent['R'],selected,reader.read(raw));parsed = candidate(business,program(reader.read(parent['R'],binary=True),'R'),selected)
    nc = delivery['observed_actual']['new_candidate'];control = attempt/'roles/controller-01';cp = reader.read(reader.pin(control/'decision.json'))
    if (cp != dict(original=reader.pin(control/'response.json'),decision=chosen) or message(reader.read(cp['original'])) != chosen
            or nc['assembly'] != assembly_bound or nc['source'] != child['R'] or nc['tests'] != value['tests']
            or assembly.get('schema') != 'earnings_population_delta_assembly_v1' or assembly.get('implementation_base') is not None
            or assembly.get('parent_source') != parent['R'] or assembly.get('parent_version_id') != parent['id'] or assembly.get('raw_patch_response') != raw
            or assembly.get('assembly_source') != dict(function='assemble',module=runtime['sources']['tools/earnings_population_delta_author.py'])
            or assembly.get('host_candidate_execution') is not False
            or assembly.get('source') != child['R'] or assembly.get('tests') != value['tests']
            or assembly.get('scientific_decision_sha256') != digest(selected) or assembly.get('scientific_decision') != projection
            or assembly.get('assembled_business_sha256') != digest(business)
            or reader.read(projection) != dict(population_decision=chosen,scientific_decision=selected,scientific_decision_sha256=digest(selected),
                scope='Explicitly removed retirement field only; no parent or feedback rewrite')
            or reader.read(reader.pin(folder/'delta.json')) != dict(original=raw,delta=message(reader.read(raw)))
            or reader.read(child['R'],binary=True) != business['source_text'].encode() or reader.read(value['tests'],binary=True) != business['test_text'].encode()):
        raise ValueError('Exact original v1 model Delta/assembly/source/tests required')
    native = Path('/private/tmp')/('market-rsi-'+attempt.name);cases_bound = reader.pin(native/'review-01-cases.json');cases = reader.read(cases_bound)
    if cases.get('candidate_id') != child['id'] or len(cases['results']) != len(parsed['cases']):raise ValueError('Exact authored cases required')
    for case,row in zip(parsed['cases'],cases['results']):
        if row.get('passed') is not True or digest(researcher.execution_value(row['execution'],business['source_text'],case['input'])) != digest(case['expected']):
            raise ValueError('Original actual case execution differs')
    probes = []
    for stage in ('forecast','controller'):
        p,c = [reader.pin(native/name) for name in (f'review-01-{stage}-probe.json',f'review-01-parent-{stage}-comparison.json')]
        probe,comparison = reader.read(p),reader.read(c)
        if (probe.get('company_id') != company_id or comparison.get('company_id') != company_id
                or comparison.get('parent_version_id') != parent['id'] or probe['input'] != comparison['input']
                or probe['input']['records'] != [] or probe['input']['stage'] != stage):raise ValueError('Matched cold task identities differ')
        researcher.verify(probe['execution'],business['source_text'],probe['input'],resident['company'])
        researcher.verify(comparison['execution'],reader.read(parent['R'],binary=True).decode(),comparison['input'],resident['company'])
        evidence += [p,c];probes.append(dict(company_id=company_id,stage=stage,receipt=p,diagnostics=probe['diagnostics']))
    bundle = dict(schema='earnings_population_author_stage_reuse_v1',mode=REVIEW_REUSE,candidate=child,decision=chosen_bound,scientific_decision=selected,
        raw_patch_response=raw,assembly=assembly_bound,tests=value['tests'],source=child['R'],parent_source=parent['R'],cases=cases_bound,probes=probes,
        failed_attempt=value['failed_attempt'],implementation_base=None,new_model_Controller_called=False,new_model_Author_called=False)
    review_result = reader.pin(attempt/'roles/review-01/result.json');terminal = dict(role_results={'review':dict(binding=review_result,value=reader.read(review_result))})
    review,_ = _accepted(reader,attempt,runtime,terminal,outputs['source_review'],bundle)
    if review['review_projection'] != value['accepted_review']:raise ValueError('Exact accepted Review required')
    for role,expected_status in [('controller','COMPLETED_DECISION'),('author','COMPLETED_CANDIDATE'),('review','COMPLETED_REVIEW')]:
        path = attempt/'roles'/(role+'-01');row = reader.read(reader.pin(path/'result.json'));turns = row.get('turns');sealed = audit['role_totals'][role+'-01']
        if (sealed['result'] != reader.pin(path/'result.json') or row.get('status') != expected_status or row.get('retry_allowed') is not False
                or type(turns) is not int or not 1 <= turns <= 8 or turns != sealed['generations']
                or {p.name for p in path.glob('[0-9][0-9]-request.json')} != {f'{i:02d}-request.json' for i in range(1,turns+1)}
                or {p.name for p in path.glob('[0-9][0-9]-response.json')} != {f'{i:02d}-response.json' for i in range(1,turns+1)}
                or row.get('final_numbered_response') != f'{turns:02d}-response.json' or reader.read(reader.pin(path/'response.json')) != reader.read(reader.pin(path/row['final_numbered_response']))):
            raise ValueError('Exact genuine completed original role required')
    evidence += _training_attachment_physical(reader,runtime,audit)+_budget(reader,runtime,owner,dict(budget=owner['budget_summary']))
    reader.extra.update(Path(runtime[key]['path']) for key in ('review','budget_amendment'))
    reader.scan(runtime);reader.scan(study)
    config = reader.read(runtime['review']);clock = reader.pair(attempt/'clock.json')
    if (config.get('verdict') != 'PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY' or config.get('blocking_findings') != []
            or config.get('source_commit') != runtime['source_commit']
            or config.get('reviewed_configuration_sha256') != digest({k:v for k,v in runtime.items() if k != 'review'})
            or clock != reader.read(owner['clock']) or clock.get('source_commit') != runtime['source_commit']
            or clock.get('cutoff_utc') != runtime['cutoff_utc'] or clock.get('deadline_utc') != runtime['deadline_utc']):
        raise ValueError('Exact original source review and clock required')
    cleanup = _cleanup(attempt);sealed_cleanup = audit['native_receipt_audit']['code_calls']
    if len(cleanup) != len(sealed_cleanup) or {digest(r['result']) for r in cleanup} != {digest(r['result']) for r in sealed_cleanup}:
        raise ValueError('Original isolated cleanup set differs')
    expected = {name:dict(role=role,round_index=1,company_id=company_id,version=version) for name,role,version in (
        ('controller-01','controller',state['versions'][state['stable_id']]),('author-01','author',parent),('review-01','review',child),
        ('forecast-01-00','forecast',state['versions'][reader.read(study['campaign'])['baseline_version_id']]))}
    evidence += _training_attachment_native(reader,runtime_bound,runtime,expected,resident,training_scope)
    frozen = deepcopy(state)
    if chosen.get('retire_branch_id') is not None:frozen = pool.retire(frozen,chosen['retire_branch_id'],reason=chosen['hypothesis'],evidence=[chosen_bound])
    frozen = pool.retain(frozen,child,reason=chosen['hypothesis'],evidence=outputs['source_review']['evidence'])
    if (reader.read(reader.pin(attempt/'frozen-pool-01.json')) != frozen or any((attempt/'roles').glob('forecast-*'))
            or any(list(attempt.rglob(n)) for n in ('population-run-result.json','predictions.json','score.json','population-public-feedback.json'))):
        raise ValueError('Only preserved temporary trial and no forecast/completed result required')
    return dict(schema=training.STAGE_ATTACHMENT_RECEIPT,mode=training.STAGE_ATTACHMENT_MODE,input=deepcopy(binding),authority=value['authority'],
        completed_origin=base_origin['previous_result'],company_id=company_id,candidate_id=child['id'],author_stage_reuse=bundle,review_stage_reuse=review,
        delivery_diagnosis=dict(stage='execute',error_type='BatchStoppedError',native_closure=deepcopy(failure['native_closure']),score_state='unscored',
            original_model_generations={k:v['generations'] for k,v in audit['role_totals'].items()},new_model_calls=0,review_assessment='accepted_for_exploration'),
        evidence=[binding,value['failed_attempt'],value['closed_failure_audit'],value['stage_delivery_audit'],owner_bound,claim_bound,runtime_bound,raw,assembly_bound,projection,cases_bound,*review['evidence'],*[r['result'] for r in cleanup],*evidence])


def load_training_stage_attachment(binding, *, completed_result, training_scope, company_id,
        attempt_id, root, ledger, repo, plan_binding, historical_reader=None):
    _training_attachment_input(binding,completed_result=completed_result,training_scope=training_scope,company_id=company_id,
        attempt_id=attempt_id,root=root,ledger=ledger,repo=repo,plan_binding=plan_binding,historical_reader=historical_reader)
    from earnings_population_completed import load as completed
    base = completed(completed_result,root=root,ledger=ledger,repo=repo)
    receipt = _verify_training_stage_attachment(binding,base_origin=base,training_scope=training_scope,company_id=company_id,
        attempt_id=attempt_id,root=root,ledger=ledger,repo=repo,plan_binding=plan_binding,historical_reader=historical_reader)
    return dict(base_origin=base,stage_attachment=receipt)
