"""Read-only handoff of the exact closed ID02 review rejection, never resume."""
from contextlib import closing
from copy import deepcopy
import hashlib
from pathlib import Path
import sqlite3

import earnings_population_continuation as history
import earnings_population as pool
import earnings_population_tasks as tasks
import earnings_open_researcher as researcher
from earnings_night_budget import history_snapshot
from earnings_population_runtime import CONTINUATION_AUTHORIZATION
from edgar_forecast_tools import FilingTools, TOOLS
from market_rsi import digest

OWNED, LEDGER, REPO = history.OWNED, history.LEDGER, history.REPO
IDENT = 'edgar-population-20261016-02'
COMMIT = 'c1b644bac8eed20d3376f0ea28a6eae00dcdf044'
FAILURE_SHA = 'd8456f6e15bd19f5c96ef932ac8f71670d3fed706aa9d0fe667e7147eab6d7a3'
RUNTIME_SHA = '256c61b9b4386f20cc522ee76183401c386dd78013757a16b4bbd225fd0e6750'
AUDIT = {'path': str(OWNED/'CONTINUATION-LIVE-FINAL-AUDIT-02.json'),
         'sha256': '8fd7443e111bec44f82abf67e2bf3fef16c2c2d119237c463d0acc1365072966'}
PARENT = '11cebd96927bc57b5a8800769d5e6dfbaeb0ace8f6b8715456c6daabb7e1a127'
COMPANY, VALIDATION = 'CIK0000017313', 'CIK0000021076'
STAGES = ('input', 'controller', 'implement', 'source_review')


class _SealedHistoryReader(history._Reader):
    """Check saved metadata, never reopen the one now-sealed historical case.

    The exact old runtime, study and audit still undergo ordinary binding
    verification. This does not reverify the sealed QA/body bytes themselves.
    No synthetic bytes are substituted for those files.
    """
    sealed_qa = None

    def read(self, bound, *, binary=False):
        if (type(bound) is dict and self.sealed_qa is not None
                and bound.get('path') == self.sealed_qa['path']):
            raise ValueError('Sealed historical QA may only remain metadata')
        return super().read(bound, binary=binary)

    def pin(self, path):
        if self.sealed_qa is not None and path == Path(self.sealed_qa['path']):
            raise ValueError('Sealed historical QA must not be reopened for hashing')
        return super().pin(path)

    def scan(self, value):
        if (type(value) is dict and set(value) == {'path', 'sha256'}
                and self.sealed_qa is not None and value['path'] == self.sealed_qa['path']):
            if value != self.sealed_qa:
                raise ValueError('Sealed historical QA metadata changed')
            return
        return super().scan(value)


def _sealed_resident(reader, study):
    """Exact hash-bound closed02 case identity; not fresh resident validation."""
    if (digest(study.get('cases')) != '36ad0b0fd741a6b7dab3dde7dfa5d97e252e6990aef5b08bcfd697f3c5f071b7'
            or digest(study.get('runtime_config')) != '2be6ad933e419a593da52ba861441cfc4c7846eb1165c7fdcacd325f73d382a5'):
        raise ValueError('Exact sealed closed02 case/runtime metadata required')
    case = study['cases'][0]
    reader.sealed_qa = deepcopy(case['evaluation_kernel']['qa'])
    return dict(case=case, runtime=study['runtime_config'])


def _prefix(reader, runtime, attempt):
    path = attempt/'loop'
    with history._journal_lock(path):
        manifest = reader.pair(path/'manifest.json')
        if (set(manifest) != {'schema', 'seed', 'seed_sha256', 'handler_identity', 'driver_source_sha256', 'max_rounds'}
                or manifest['schema'] != 'feedback_linked_loop_v1' or manifest['max_rounds'] != 1
                or manifest['seed_sha256'] != digest(manifest['seed'])
                or manifest['seed']['companies'] != runtime['companies']
                or manifest['seed']['population'] != reader.read(runtime['initial_population'])
                or manifest['driver_source_sha256'] != runtime['sources'][history.DRIVER]['sha256']
                or set(manifest['handler_identity']) != set(history.STAGES)):
            raise ValueError('Exact original rejected-prefix manifest required')
        for stage, item in manifest['handler_identity'].items():
            if item != dict(stage=stage, adapter=runtime['sources']['tools/earnings_population_loop.py'],
                    admission={'function': 'execute.<locals>.admit', 'module': runtime['sources']['tools/earnings_population_run.py']},
                    services={role: {'function': 'Services.'+role, 'module': runtime['sources']['tools/earnings_population_services.py']}
                              for role in ('controller', 'author', 'review', 'forecast')}):
                raise ValueError('Original rejected-prefix source/admission identity differs')
        reader.scan(manifest)
        outputs, expected, evidence = {}, set(), [reader.pin(path/'manifest.json')]
        for stage in STAGES:
            prefix = path/f'round-0001-{stage}'
            claim, done = prefix.with_suffix('.claim.json'), prefix.with_suffix('.done.json')
            expected.update([claim.name, done.name, done.with_suffix('.binding.json').name])
            context = dict(round_index=1, seed=manifest['seed'], previous_result=manifest['seed'],
                           previous_feedback_sha256=digest(manifest['seed']), outputs=outputs)
            if reader.read(reader.pin(claim)) != dict(round_index=1, stage=stage, context_sha256=digest(context),
                    manifest_sha256=evidence[0]['sha256'], previous_feedback_sha256=digest(manifest['seed'])):
                raise ValueError('Rejected-prefix claim/context changed')
            value = reader.pair(done)
            if (set(value) != {'claim_sha256', 'output', 'output_sha256'} or type(value['output']) is not dict
                    or value['claim_sha256'] != reader.pin(claim)['sha256'] or value['output_sha256'] != digest(value['output'])):
                raise ValueError('Rejected-prefix completed output changed')
            reader.scan(value['output']); outputs[stage] = value['output']; evidence.append(reader.pin(done))
        if {p.name for p in path.glob('round-*')} != expected or reader.pair(path/'manifest.json') != manifest:
            raise ValueError('Only four completed stages, no execute claim/failure, may transfer')
    return manifest['seed'], outputs, evidence


def _ledger(reader, runtime, owner, audit, attempt):
    accounting = audit['accounting']
    with closing(sqlite3.connect(reader.ledger.as_uri()+'?mode=ro', uri=True)) as db:
        db.execute('BEGIN')
        config = db.execute('SELECT cap,model_cap FROM config WHERE id=1').fetchone()
        if config == (400_000_000_000, 100_000_000_000):
            from earnings_population_budget import validate_cap
            validate_cap(db)  # prospective grant; frozen historical owner/result remain200
        elif config != (200_000_000_000, 100_000_000_000):
            raise ValueError('Historical caps or explicit prospective amendment changed')
        if (history_snapshot(db, history.EXTRA_BASELINE['max_rowid']) != history.EXTRA_BASELINE
                or history_snapshot(db, runtime['baseline']['max_rowid']) != runtime['baseline']):
            raise ValueError('Original/opening accounting prefix changed')
        closed = history_snapshot(db, accounting['closing_rows'])
        if (closed['rows_sha256'] != accounting['closing_rows_sha256']
                or closed['charged_nano_usd'] != accounting['closing_charged']
                or closed['request_count'] != accounting['closing_rows']):
            raise ValueError('Original closed accounting prefix changed')
        requests = [reader.read(reader.pin(p)) for p in sorted((attempt/'roles').glob('*/*-request.json'))]
        ids = [v['request_id'] for v in requests]
        rows = db.execute('SELECT id,model,reserved,charged,status FROM requests WHERE rowid>? AND rowid<=? ORDER BY rowid',
                          (runtime['baseline']['max_rowid'], accounting['closing_rows'])).fetchall()
        if (len(ids) != 24 or len(set(ids)) != 24 or set(ids) != {r[0] for r in rows}
                or any(r[1] != 'gpt-6.1-sol' or r[4] not in ('settled', 'settled_upper_bound') for r in rows)
                or sum(r[3] for r in rows) != accounting['own_charge']
                or round(owner['budget_summary']['charged_upper_bound_usd']*1e9) != closed['charged_nano_usd']):
            raise ValueError('Exact own 24 requests must be settled; later rows cannot replace them')


def _closures(reader, attempt, native, audit):
    evidence, calls = [], sorted((attempt/'code').glob('call-*/result.json'))
    if len(calls) != 8:
        raise ValueError('Exact original eight saved executions required')
    for path in calls:
        bound = reader.pin(path); value = reader.read(bound)
        if (value.get('status') != 'COMPLETED' or value.get('cleanup_verified') is not True
                or value.get('host_candidate_execution') is not False or value.get('exit_code') != 0):
            raise ValueError('Original execution/cleanup remains uncertain')
        for name, key in [('input.json', 'input_sha256'), ('stdout.bin', 'stdout_sha256'), ('stderr.bin', 'stderr_sha256')]:
            if reader.pin(path.parent/name)['sha256'] != value[key]:
                raise ValueError('Original execution bytes changed')
        original = reader.read(reader.pin(path.parent/'input.json'))
        if hashlib.sha256(original['source'].encode()).hexdigest() != value['source_sha256']:
            raise ValueError('Original execution source differs')
        evidence.append(bound)
    if digest(evidence) != audit['native_and_execution_closure']['code_receipt_manifest_sha256']:
        raise ValueError('Original audited execution receipt manifest changed')
    for role, expected in audit['native_and_execution_closure']['role_batch_sha256'].items():
        bound = reader.pin(native/role/'batch/batch.json')
        if bound['sha256'] != expected:
            raise ValueError('Original audited idle Native batch changed')
        evidence.append(bound)
    return evidence


def _probes(reader, reviewed, candidate, company):
    source = reader.read(candidate['R'], binary=True).decode()
    tools, result = FilingTools(company), []
    for stage in ('forecast', 'controller'):
        expected = Path('/private/tmp')/('market-rsi-'+IDENT)/f'review-01-{stage}-probe.json'
        matches = [b for b in reviewed['evidence'] if b['path'] == str(expected)]
        if len(matches) != 1:
            raise ValueError('Both original prior-company empty-state probes required')
        bound = matches[0]; probe = reader.read(bound); payload = probe['input']
        if (payload.get('stage') != stage or payload.get('records') != []
                or payload.get('questions') != tools.files['questions.md']
                or payload.get('filing_index') != tools.files['filing_index.tsv']):
            raise ValueError('Probe must be original Capital public empty-state input')
        value = researcher.verify(probe['execution'], source, payload, company)
        rows = probe['execution'].get('research_observations', [])
        coverage = value['coverage']
        if (any(type(n) is not int or not 0 <= n <= 1_000_000_000 for n in coverage.values())
                or len(rows) != 8 or any(row['request']['tool'] != 'search_files' for row in rows)
                or coverage.get('accepted_searches') != 8 or coverage.get('failed_requests') != 0):
            raise ValueError('Preserve successful search acquisition, not a transport-failure claim')
        result.append(dict(stage=stage, company_id=COMPANY, receipt=bound,
            source_sha256=candidate['R']['sha256'], execution_sha256=probe['execution']['receipt']['sha256'],
            coverage=deepcopy(coverage), search_hits=sum(len(row['output']['hits']) for row in rows),
            incomplete_targets=sum(t['status'] == 'incomplete' for t in value['targets']),
            reason_codes=sorted({reason for t in value['targets'] for reason in t['failure_reasons']})))
    return result, tools.files['questions.md']


def load_closed_review_rejection(failure_binding, *, root, ledger, repo, sealed_history=False):
    if type(sealed_history) is not bool:
        raise ValueError('Explicit boolean sealed-history opt-in required')
    root, ledger, repo = map(Path, (root, ledger, repo))
    attempt, native = root/'attempts'/IDENT, Path('/private/tmp')/('market-rsi-'+IDENT)
    if (root != OWNED or ledger != LEDGER or repo != REPO or any(p.resolve() != p for p in (root, ledger, repo))
            or failure_binding != {'path': str(attempt/'population-run-failure.json'), 'sha256': FAILURE_SHA}):
        raise ValueError('Only exact canonical closed02 rejection may transfer')
    reader = (_SealedHistoryReader if sealed_history else history._Reader)(root, ledger, repo, IDENT)
    token = hashlib.sha256(IDENT.encode()).hexdigest(); registry = ledger.parent/'.capacity-runtime-claims'
    claim_bound, owner_bound = reader.pin(registry/(token+'.json')), reader.pin(registry/(token+'.result.json'))
    reader.extra.update([Path(AUDIT['path']), Path(claim_bound['path']), Path(owner_bound['path']),
                         Path(tasks.FULL_PLAN['path']), Path(tasks.SCORER['path'])])
    failure, audit = reader.read(failure_binding), reader.read(AUDIT)
    claim, owner = reader.read(claim_bound), reader.read(owner_bound)
    runtime_bound = owner['runtime']; runtime = reader.read(runtime_bound); budget = owner['budget_summary']
    if (failure != dict(status='FAILED_NO_RETRY', error_type='ValueError', native_closure=None, retry_allowed=False)
            or (attempt/'population-run-result.json').exists() or any((attempt/'roles').glob('forecast-*'))
            or any(native.glob('forecast-*')) or any(attempt.rglob('score.json'))
            or owner.get('status') != 'FAILED_NO_RETRY' or owner.get('error_type') != 'ValueError'
            or owner.get('retry_allowed') is not False or claim.get('retry_allowed') is not False
            or claim.get('id') != IDENT or claim.get('runtime') != runtime_bound
            or claim.get('source_commit') != COMMIT or runtime_bound['sha256'] != RUNTIME_SHA
            or runtime.get('source_commit') != COMMIT or runtime.get('id') != IDENT
            or runtime.get('schema') != 'earnings_population_runtime_v1' or runtime.get('root') != str(attempt)
            or runtime.get('ledger') != str(ledger) or runtime.get('companies') != [VALIDATION]
            or audit.get('verdict') != 'PASS_AUDITED_REJECTION_AND_FAILURE_CLOSURE_NO_FORECAST'
            or owner_bound['sha256'] != audit['native_and_execution_closure']['owner_terminal_receipt_sha256']
            or budget.get('blocked') is not False or budget.get('unresolved_reserved_usd') != 0
            or budget.get('cap_usd') != 200 or budget.get('model_cap_usd') != 100
            or budget.get('night_cap_usd') != 5 or budget.get('prior_history_sha256') != runtime['baseline']['rows_sha256']):
        raise ValueError('Exact historically audited review-rejected terminal required')
    reader.register_sources(runtime)
    study = reader.read(runtime['forecast_study']); continued = reader.read(study['continuation'])
    inherited, ids, qa = history._load(continued['previous_result'], root, ledger, repo, {IDENT})
    reader.ids.update(ids); reader.extra.update(Path(b['path']) for b in inherited['evidence']+qa)
    if sealed_history:
        resident = _sealed_resident(reader, study)
    else:
        resident = tasks.resident(VALIDATION); reader.extra.add(Path(resident['kernel']['qa']['path']))
    state = pool.validate(inherited['population'])
    if (reader.read(runtime['initial_population']) != state or continued['population_sha256'] != digest(state)
            or continued['feedback'] != inherited['feedback'] or continued['evidence'] != inherited['evidence']
            or continued.get('repair') != dict(schema='earnings_population_human_repair_v1', parent_version_id=PARENT,
                                             human_authorization=CONTINUATION_AUTHORIZATION)
            or PARENT not in state['explorers'] or study.get('data') != tasks.FULL_PLAN
            or study.get('scorer') != tasks.SCORER or study.get('runtime_config') != resident['runtime']
            or study.get('cases') != [resident['case']] or study.get('sole_ledger') != str(ledger)
            or study.get('model') != {'requested_model': 'gpt-6.1-sol', 'serving_snapshot': 'unknown', 'serving_snapshot_verified': False}
            or runtime.get('rates') != resident['runtime']['models']['gpt-6.1-sol']
            or runtime.get('original_extra_baseline') != history.EXTRA_BASELINE
            or runtime.get('original_extra_cap_nano_usd') != history.EXTRA_CAP):
        raise ValueError('Verified completed01 pool and exact historical human repair required')
    reader.scan(runtime); reader.scan(study)
    review = reader.read(runtime['review'])
    if (review.get('verdict') != 'PASS_POPULATION_RUNTIME_SOURCE_INPUT_ONLY' or review.get('blocking_findings') != []
            or review.get('source_commit') != COMMIT or type(review.get('reviewer')) is not str
            or not review['reviewer'].strip() or review['reviewer'].strip().lower() in ('root', '/root')
            or review.get('reviewed_configuration_sha256') != digest({k: v for k, v in runtime.items() if k != 'review'})):
        raise ValueError('Original source/input runtime review differs')
    clock = reader.pair(attempt/'clock.json')
    if (reader.read(owner['clock']) != clock or clock.get('source_commit') != COMMIT
            or clock.get('cutoff_utc') != runtime['cutoff_utc'] or clock.get('deadline_utc') != runtime['deadline_utc']):
        raise ValueError('Original rejected owner clock differs')
    seed, outputs, prefix_evidence = _prefix(reader, runtime, attempt)
    if (seed['population'] != state or seed['feedback'] != inherited['feedback']
            or [b['sha256'] for b in prefix_evidence[1:]]
                != [row['sha256'] for row in audit['actual_trajectory']['completed_stages']]):
        raise ValueError('Original rejected-prefix seed changed')
    chosen, child, reviewed = reader.read(outputs['controller']['decision']), outputs['implement']['candidate'], outputs['source_review']
    if (reviewed.get('accepted_for_exploration') is not False or chosen.get('axis') != 'R'
            or chosen.get('parent_pair_sha256') != PARENT or chosen.get('feedback_sha256') != digest(inherited['feedback'])
            or child.get('parent') != PARENT or child.get('axis') != 'R' or child['id'] in state['versions']
            or child['id'] != audit['real_feedback_and_author_delivery']['candidate_id']
            or child['R']['sha256'] != audit['real_feedback_and_author_delivery']['candidate_source_sha256']
            or child != pool.version(**{k: child[k] for k in ('R', 'H', 'parent', 'axis', 'method', 'author', 'evidence')})
            or child['H'] != state['versions'][PARENT]['H']):
        raise ValueError('Explicit false review of the exact new R child required')
    outcome_bound = reader.pin(native/'review-01-outcome.json'); outcome = reader.read(outcome_bound)
    if (outcome_bound not in reviewed['evidence'] or outcome.get('candidate_id') != child['id']
            or outcome_bound['sha256'] != audit['independent_rejection_and_real_probes']['review_outcome_sha256']
            or outcome.get('accepted_for_exploration') is not False or type(outcome.get('rationale')) is not str):
        raise ValueError('Actual independent rejection outcome required')
    _ledger(reader, runtime, owner, audit, attempt)
    closure = _closures(reader, attempt, native, audit)
    probes, questions = _probes(reader, reviewed, child, tasks.resident(COMPANY)['company'])
    reference = dict(axis='R', source=child['R'], source_delivery='paged_reference', reference_only=True,
                     id=child['id'], parent=PARENT, tests=reader.pin(attempt/'roles/author-01/cases.py'))
    feedback = dict(schema='earnings_population_rejection_feedback_v1', kind='review_rejected', score_state='unscored',
        company_id=COMPANY, population_sha256=digest(state), active_parent_id=PARENT,
        last_scored_feedback=inherited['feedback'], rejected_candidate=reference,
        review=dict(binding=outcome_bound, accepted_for_exploration=False, rationale=outcome['rationale'], evidence=reviewed['evidence']),
        probes=probes, original_questions=questions,
        tool_abi=dict(schema='earnings_original_R_evidence_abi_v1', request_phases=1, max_requests=8, tools=deepcopy(TOOLS),
            same_program_rerun=True, observation_fields=['request', 'output'], max_read_characters=20000,
            max_search_query_characters=200, max_search_hits=50, max_shared_tool_calls=80, max_return_characters=2000000,
            search_hit_fields=['path', 'line', 'text'], search_has_source_sha256=False, search_has_character_offset=False,
            search_line_base=1, read_offset_base=0,
            read_result_fields=['path', 'offset', 'total_characters', 'text', 'next_offset'], read_has_source_sha256=False,
            author_prior_file_hash_is_not_R_observation_hash=True, second_request_phase_allowed=False),
        qualifications=['Searches succeeded; zero extracted facts is not transport failure.',
            'Both original cold probes already use the prior Capital company; preserve original rationale without endorsing its prior-probe-absence wording.',
            'Coverage and parse reasons are program reports from verified executions, not independently verified financial correctness.'],
        scope='Closed rejected code is reference only; no forecast, score, adoption, gain, new permission or old-ID retry.')
    evidence = [failure_binding, AUDIT, runtime_bound, claim_bound, owner_bound, runtime['initial_population'],
                *prefix_evidence, *reviewed['evidence'], *closure, *inherited['evidence']]
    return dict(population=deepcopy(state), research_feedback=feedback, last_scored_feedback=inherited['feedback'],
                reference_candidate=reference, evidence=list({digest(b): b for b in evidence}.values()))
