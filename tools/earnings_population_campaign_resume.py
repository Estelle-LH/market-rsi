"""Read-only inheritance of audited closed03; no historical execution or grant."""
from contextlib import closing
from copy import deepcopy
import hashlib
from pathlib import Path
import sqlite3

import earnings_population as pool
import earnings_population_continuation as history
import earnings_population_rejection as rejection
import earnings_population_tasks as tasks
from earnings_night_budget import history_snapshot
from market_rsi import digest

OWNED, LEDGER, REPO = history.OWNED, history.LEDGER, history.REPO
IDENT = 'edgar-population-20261016-03'
COMMIT = '7a07d9f0077eb7c4e9b384ae32efbcd6ddde0f34'
RESULT_SHA = '44007cfe42a424c18b844c09ca97c52da008dcabb3acc9b1216b46866d0781ee'
RUNTIME_SHA = '110ff5d0d82de753b6e68e25d51725f72aa90c8ad66f65a2bf607ac979159415'
AUDIT = {'path': str(OWNED/'CAMPAIGN-FINAL-AUDIT-03.json'),
         'sha256': 'fc3862b86c5968af50ac8a7ab9ac7a5df2ce430d39ee1dfc88741e0273cedcf7'}
COMPANY, PARENT = rejection.COMPANY, rejection.PARENT


def _ledger(reader, runtime, owner, audit, attempt):
    """Only historical own rows must settle; a later live reservation is not ours."""
    accounting = audit['accounting']
    with closing(sqlite3.connect(reader.ledger.as_uri()+'?mode=ro', uri=True)) as db:
        db.execute('BEGIN')
        config = db.execute('SELECT cap,model_cap FROM config WHERE id=1').fetchone()
        if config == (400_000_000_000, 100_000_000_000):
            from earnings_population_budget import validate_cap
            validate_cap(db)  # old03 cap200 remains in immutable receipts
        elif config != (200_000_000_000, 100_000_000_000):
            raise ValueError('Historical caps or explicit prospective amendment changed')
        if (history_snapshot(db, history.EXTRA_BASELINE['max_rowid']) != history.EXTRA_BASELINE
                or history_snapshot(db, runtime['baseline']['max_rowid']) != runtime['baseline']):
            raise ValueError('Original accounting prefix/caps changed')
        closed = history_snapshot(db, 5800)
        if (accounting['closing_rows'] != 5800 or closed['request_count'] != 5800
                or closed['rows_sha256'] != accounting['closing_rows_sha256']
                or closed['charged_nano_usd'] != accounting['closing_charged_nano_usd']):
            raise ValueError('Audited closed03 accounting prefix changed')
        requests = [reader.read(reader.pin(p)) for p in sorted((attempt/'roles').glob('*/*-request.json'))]
        ids = [v['request_id'] for v in requests]
        rows = db.execute('SELECT id,model,reserved,charged,status FROM requests WHERE rowid>? AND rowid<=5800 ORDER BY rowid',
                          (runtime['baseline']['max_rowid'],)).fetchall()
        if (runtime['baseline']['max_rowid'] != 5776 or len(ids) != 24 or len(set(ids)) != 24
                or set(ids) != {r[0] for r in rows} or len(rows) != 24
                or any(r[1] != 'gpt-6.1-sol' or r[4] != 'settled' for r in rows)
                or sum(r[3] for r in rows) != accounting['total_own_charge_nano_usd']
                or sum(r[3] for r in rows) != 567187400
                or round(owner['budget_summary']['charged_upper_bound_usd']*1e9) != closed['charged_nano_usd']):
            raise ValueError('Exact original24 requests must remain settled, never replaced by later rows')


def _closure(reader, attempt, native, audit):
    evidence = []
    calls = sorted((attempt/'code').glob('call-*/result.json'))
    if len(calls) != 10:
        raise ValueError('Exact original10 closed03 execution receipts required')
    for path in calls:
        bound = reader.pin(path); value = reader.read(bound)
        if (value.get('status') != 'COMPLETED' or value.get('cleanup_verified') is not True
                or value.get('host_candidate_execution') is not False or value.get('exit_code') != 0):
            raise ValueError('Original candidate execution/cleanup remains uncertain')
        for name, key in [('input.json', 'input_sha256'), ('stdout.bin', 'stdout_sha256'), ('stderr.bin', 'stderr_sha256')]:
            if reader.pin(path.parent/name)['sha256'] != value[key]:
                raise ValueError('Original execution bytes changed')
        original = reader.read(reader.pin(path.parent/'input.json'))
        if hashlib.sha256(original['source'].encode()).hexdigest() != value['source_sha256']:
            raise ValueError('Original execution source changed')
        evidence.append(bound)
    closure = audit['execution_and_native_closure']
    if digest(evidence) != closure['code_receipt_manifest_sha256']:
        raise ValueError('Original execution receipt manifest changed')
    for role, expected in closure['native_batch_sha256'].items():
        bound = reader.pin(native/role/'batch/batch.json')
        if bound['sha256'] != expected:
            raise ValueError('Original audited Native role closure changed')
        evidence.append(bound)
    return evidence


def load(result_binding, *, root, ledger, repo):
    root, ledger, repo = map(Path, (root, ledger, repo))
    attempt, native = root/'attempts'/IDENT, Path('/private/tmp')/('market-rsi-'+IDENT)
    if (root != OWNED or ledger != LEDGER or repo != REPO or any(p.resolve() != p for p in (root, ledger, repo))
            or result_binding != {'path': str(attempt/'population-run-result.json'), 'sha256': RESULT_SHA}):
        raise ValueError('Only exact canonical audited closed03 result may transfer')
    prior_failure = dict(path=str(root/'attempts'/rejection.IDENT/'population-run-failure.json'),
                         sha256=rejection.FAILURE_SHA)
    inherited = rejection.load_closed_review_rejection(prior_failure, root=root, ledger=ledger, repo=repo,
                                                       sealed_history=True)
    reader = history._Reader(root, ledger, repo, IDENT)
    reader.ids.update({'edgar-population-20261016-01', rejection.IDENT})
    token = hashlib.sha256(IDENT.encode()).hexdigest(); registry = ledger.parent/'.capacity-runtime-claims'
    claim_bound, owner_bound = reader.pin(registry/(token+'.json')), reader.pin(registry/(token+'.result.json'))
    reader.extra.update(Path(b['path']) for b in [AUDIT, claim_bound, owner_bound, tasks.FULL_PLAN, tasks.SCORER,
                                                *inherited['evidence']])
    for cik in ('CIK0000004457', COMPANY):
        qa = tasks.resident(cik)['kernel']['qa']; reader.extra.add(Path(qa['path'])); reader.read(qa, binary=True)
    result, audit = reader.read(result_binding), reader.read(AUDIT)
    claim, owner = reader.read(claim_bound), reader.read(owner_bound)
    runtime_bound = owner['runtime']; runtime = reader.read(runtime_bound)
    if (result.get('status') != 'COMPLETED_DISCOVERY_PILOT' or result.get('retry_allowed') is not False
            or result.get('improvement_proven') is not False or (attempt/'population-run-failure.json').exists()
            or any((attempt/'roles').glob('forecast-*')) or any(native.glob('forecast-*')) or any(attempt.rglob('score.json'))
            or owner.get('status') != 'COMPLETED_COMPONENT_CONTEXT' or owner.get('error_type') is not None
            or owner.get('retry_allowed') is not False or claim.get('retry_allowed') is not False
            or claim.get('id') != IDENT or claim.get('runtime') != runtime_bound or claim.get('source_commit') != COMMIT
            or runtime_bound['sha256'] != RUNTIME_SHA or runtime.get('source_commit') != COMMIT
            or runtime.get('id') != IDENT or runtime.get('schema') != 'earnings_population_runtime_v1'
            or runtime.get('root') != str(attempt) or runtime.get('ledger') != str(ledger) or runtime.get('companies') != [COMPANY]
            or audit.get('verdict') != 'PASS_AUDITED_COMPLETED_REJECTION_NO_FORECAST_NO_GAIN'
            or audit.get('result') != result_binding
            or audit['source_runtime_and_stage_integrity']['owner_terminal'] != owner_bound):
        raise ValueError('Exact audited completed03 owner/result/source required')
    if len(runtime['sources']) != 113:
        raise ValueError('Original113 historical source bindings required')
    reader.register_sources(runtime)
    study = reader.read(runtime['forecast_study']); campaign = reader.read(study['campaign'])
    state = pool.validate(inherited['population']); resident = tasks.resident(COMPANY)
    if (reader.read(study['campaign_origin']) != inherited or reader.read(runtime['initial_population']) != state
            or campaign.get('schema') != 'earnings_population_campaign_v1' or campaign.get('panel') != [COMPANY]
            or campaign.get('max_decisions') != 1 or campaign.get('baseline_version_id') != PARENT
            or campaign.get('initial_population_sha256') != digest(state)
            or reader.read(campaign['initial_feedback']) != inherited['research_feedback']
            or campaign.get('last_scored_feedback') != inherited['last_scored_feedback']
            or study.get('data') != tasks.FULL_PLAN or study.get('scorer') != tasks.SCORER
            or study.get('cases') != [resident['case']] or study.get('sole_ledger') != str(ledger)
            or study.get('runtime_config') != resident['runtime']
            or runtime.get('rates') != resident['runtime']['models']['gpt-6.1-sol']
            or runtime.get('original_extra_baseline') != history.EXTRA_BASELINE or runtime.get('original_extra_cap_nano_usd') != history.EXTRA_CAP):
        raise ValueError('Original03 chain/panel/data/scorer/model context differs')
    review = reader.read(runtime['review'])
    if (review.get('verdict') != 'PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY' or review.get('blocking_findings') != []
            or review.get('source_commit') != COMMIT or review.get('reviewed_configuration_sha256') != digest({k: v for k, v in runtime.items() if k != 'review'})
            or type(review.get('reviewer')) is not str or review['reviewer'].strip().lower() in ('', 'root', '/root')):
        raise ValueError('Original source/input independent review differs')
    reader.scan(runtime); reader.scan(study); reader.scan(result)
    budget = owner['budget_summary']
    if (budget != result['budget'] or budget.get('blocked') is not False or budget.get('unresolved_reserved_usd') != 0
            or budget.get('cap_usd') != 200 or budget.get('model_cap_usd') != 100 or budget.get('night_cap_usd') != 5
            or budget.get('prior_history_sha256') != runtime['baseline']['rows_sha256']):
        raise ValueError('Original completed03 budget/zero-pending summary differs')
    clock = reader.pair(attempt/'clock.json')
    if (clock != reader.read(owner['clock']) or clock.get('source_commit') != COMMIT
            or clock.get('cutoff_utc') != runtime['cutoff_utc'] or clock.get('deadline_utc') != runtime['deadline_utc']):
        raise ValueError('Original03 sealed window differs')
    with history._journal_lock(attempt/'loop'):
        replay, seed = history._replay(attempt/'loop', reader, runtime)
        manifest = reader.pair(attempt/'loop/manifest.json')
    if (replay != result['result'] or replay['completed_rounds'] != 1 or seed['population'] != state
            or seed['feedback'] != campaign['initial_feedback'] or seed.get('campaign') != study['campaign']
            or seed.get('last_scored_feedback') != inherited['last_scored_feedback']):
        raise ValueError('Exact completed03 journal/seed chain differs')
    for stage, identity in manifest['handler_identity'].items():
        if identity != dict(stage=stage, adapter=runtime['sources']['tools/earnings_population_loop.py'],
                admission={'function': 'execute.<locals>.admit', 'module': runtime['sources']['tools/earnings_population_run.py']},
                services={role: {'function': 'Services.'+role, 'module': runtime['sources']['tools/earnings_population_services.py']}
                          for role in ('controller', 'author', 'review', 'forecast')},
                campaign_policy=runtime['sources']['tools/earnings_population_campaign.py'], campaign=study['campaign']):
            raise ValueError('Historical campaign handler identity differs')
    final = replay['result']; feedback = reader.read(final['feedback'])
    child = reader.pair(attempt/'loop/round-0001-implement.done.json')['output']['candidate']
    outcome_bound = reader.pin(native/'review-01-outcome.json'); outcome = reader.read(outcome_bound)
    if (final['population'] != state or reader.read(reader.pin(attempt/'population-01.json')) != state
            or final['latest_feedback'] != final['feedback'] or final['last_scored_feedback'] != inherited['last_scored_feedback']
            or final['feedback'] != audit['retained_state_and_next_use']['latest_feedback']
            or feedback.get('schema') != 'earnings_population_campaign_feedback_v1' or feedback.get('kind') != 'review_rejected'
            or feedback.get('score_state') != 'unscored' or feedback.get('results') != [] or feedback.get('company_id') != COMPANY
            or feedback.get('previous_feedback') != campaign['initial_feedback'] or feedback.get('candidate') != child
            or feedback.get('last_scored_feedback') != inherited['last_scored_feedback'] or feedback.get('chosen_parent_id') != PARENT
            or feedback.get('campaign_contract_sha256') != digest(campaign['contract'])
            or child['axis'] != 'R' or child['parent'] != PARENT or child['id'] in state['versions']
            or child['H'] != state['versions'][PARENT]['H'] or outcome.get('candidate_id') != child['id']
            or outcome.get('accepted_for_exploration') is not False
            or outcome_bound not in feedback['exploration_review']['evidence']
            or feedback['exploration_review']['accepted_for_exploration'] is not False
            or outcome_bound['sha256'] != audit['actual_candidate_and_scientific_result']['independent_model_outcome_sha256']
            or state['protected'] != {'K': digest({'data': tasks.FULL_PLAN, 'scorer': tasks.SCORER}),
                                     'M': digest(study['model']), 'C': runtime['sources']['forecaster']['sha256']}):
        raise ValueError('Retained pool/latest unscored rejection/old score/actual candidate differs')
    _ledger(reader, runtime, owner, audit, attempt)
    closure = _closure(reader, attempt, native, audit)
    reference = dict(axis='R', source=deepcopy(child['R']), source_delivery='paged_reference', reference_only=True,
                     id=child['id'], parent=PARENT, tests=reader.pin(attempt/'roles/author-01/cases.py'))
    evidence = [result_binding, AUDIT, runtime_bound, claim_bound, owner_bound, runtime['initial_population'],
        study['campaign'], study['campaign_origin'], reader.pin(attempt/'loop/manifest.json'), final['feedback'],
        runtime['review'], outcome_bound, *closure, *inherited['evidence']]
    return dict(population=deepcopy(state), feedback=deepcopy(final['feedback']), research_feedback=deepcopy(feedback),
        last_scored_feedback=deepcopy(inherited['last_scored_feedback']), reference_candidate=reference,
        original_research_feedback=deepcopy(inherited['research_feedback']),
        evidence=list({digest(b): b for b in evidence}.values()), previous_result=deepcopy(result_binding))
