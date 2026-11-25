"""Human-directed public WIP evidence, never a recovered origin or candidate.

Only the original bound policy enables this first-round annotation. Old pool,
feedback, role authorship and failed-response status are not rewritten.
"""
from contextlib import closing
from copy import deepcopy
import hashlib
from pathlib import Path
import re
import sqlite3

import earnings_entry as entry
import earnings_population_reconcile as fees
from earnings_population_roles import decode_proposal, message, scientific
from earnings_population_delta_author import FIELDS, _edit_source
from earnings_population_source_history import source_name
from market_rsi import digest
from supervisor_harness import capacity_feedback_engine as engine

POLICY = 'earnings_population_source_guard_public_repair_v1'
MODE = 'source_guard_public_evidence_v1'
PLAN = 'configs/earnings_coevolution/population_after04_delivery_plan.json'


def _policy(runtime):
    bound = runtime.get('sources', {}).get(PLAN)
    if bound is None:
        return None  # Original inert/legacy contexts without this source.
    from earnings_population_continuation import _git
    repo = Path(__file__).resolve().parents[1]
    if (source_name(bound['path'], repo) != PLAN
            or re.fullmatch('[0-9a-f]{40}', runtime.get('source_commit', '')) is None):
        raise ValueError('Original registered delivery-plan Source required')
    raw = _git(repo, runtime['source_commit'], PLAN)
    if hashlib.sha256(raw).hexdigest() != bound['sha256']:
        raise ValueError('Original delivery-plan Git bytes differ')
    return entry.strict_json(raw).get('public_evidence_repair')


def _read(bound, *, expected=None):
    path = Path(bound['path'])
    if (not path.is_relative_to(fees.ROOT) or expected is not None and path != expected):
        raise ValueError('Only exact owned public repair evidence required')
    return fees._read(bound)


def _settled(config, proof, runtime, request):
    saved = _read(config['settlement'])
    result = saved.get('operator_return', {})
    if (saved.get('schema') != 'earnings_actual30_root_settlement_result_v1'
            or saved.get('id') != proof['id'] or saved.get('evidence') != config['fee_evidence']
            or saved.get('actual_charge_known') is not False
            or saved.get('retry_allowed') is not False or saved.get('original_failure_preserved') is not True
            or result.get('request_id') != request['request_id']
            or result.get('evidence') != config['fee_evidence']
            or result.get('before') != proof['ledger_before']
            or result.get('conservative_charge_nano_usd') != request['reserved_nano_usd']
            or type(result.get('conservative_charge_nano_usd')) is not int
            or result.get('policy') != fees.SOURCE_GUARD_POLICY
            or result.get('mode') != fees.SOURCE_GUARD_MODE
            or result.get('source_incident') != proof['source_incident']
            or result.get('actual_charge_known') is not False or result.get('retry_allowed') is not False
            or result.get('provider_usage_received') is not True or result.get('refund_nano_usd') != 0):
        raise ValueError('Exact once-only conservative Source-failure settlement required')
    fees.authority._prefix(result['after'])
    from earnings_night_budget import history_snapshot
    ledger = Path(runtime['ledger'])
    with closing(sqlite3.connect(ledger.as_uri()+'?mode=ro', uri=True)) as db:
        db.execute('BEGIN')
        row = db.execute('SELECT model,reserved,charged,status FROM requests WHERE id=?',
                         (request['request_id'],)).fetchone()
        reconciliation = db.execute('SELECT evidence_sha256,prior_status,prior_charge,ceiling,policy '
            'FROM reconciliations WHERE request_id=?', (request['request_id'],)).fetchall()
        if (row != ('gpt-6.1-sol', request['reserved_nano_usd'], request['reserved_nano_usd'], 'settled_upper_bound')
                or reconciliation != [(config['fee_evidence']['sha256'], 'uncertain', 0,
                    request['reserved_nano_usd'], fees.SOURCE_GUARD_POLICY)]
                or history_snapshot(db, result['after']['max_rowid']) != result['after']):
            raise ValueError('Original full-ceiling settlement differs from read-only ledger')


def _delivery(config, parent):
    proof, runtime, request = fees.inspect_source_guard_received_raw_evidence(config['fee_evidence'])
    _settled(config, proof, runtime, request)
    attempt = fees.ROOT/'attempts'/proof['id']
    audit = _read(config['role_audit'])
    if (audit.get('attempt_id') != proof['id'] or audit.get('runtime') != proof['runtime']
            or audit.get('source_commit') != runtime['source_commit']
            or any(audit.get('downstream_not_reached', {}).get(key) is not False
                for key in ('candidate', 'model_Review', 'forecast', 'score', 'reconcile', 'new_feedback'))
            or any((attempt/'roles/author-01'/name).exists() for name in ('candidate.py', 'cases.py'))):
        raise ValueError('Exact failed public delivery, not an accepted candidate, required')
    completed = [row for row in audit['milestones']
                 if row.get('kind') == 'CONTROLLER_COMPLETED_ALL_PHYSICAL_REQUESTS']
    if len(completed) != 1:
        raise ValueError('One original accepted Controller public proposal required')
    controller = completed[0]
    result = _read(controller['result']['binding'], expected=attempt/'roles/controller-01/result.json')
    rows = controller['rows']
    if (result != controller['result']['value'] or result.get('status') != 'COMPLETED_DECISION'
            or type(result.get('turns')) is not int or result['turns'] != len(rows)
            or result.get('final_numbered_response') != f'{len(rows):02d}-response.json'):
        raise ValueError('Original accepted Controller terminal differs')
    last = rows[-1]
    req = _read(last['request'], expected=attempt/'roles/controller-01'/f'{len(rows):02d}-request.json')
    response = _read(last['response'], expected=attempt/'roles/controller-01'/result['final_numbered_response'])
    intent, raw, sidecar = (_read(last[key]) for key in ('physical_intent','physical_raw','physical_sidecar'))
    limits = runtime['limits']['controller']
    if (intent.get('endpoint') != '/v1/responses' or intent.get('complete_reservation') != req
            or intent.get('request_receipt_sha256') != last['request']['sha256']
            or intent.get('payload') != dict(req['payload'], max_output_tokens=limits['max_output_tokens'],
                service_tier='default', store=False)
            or sidecar != response or raw != {k:v for k,v in response.items() if k != '_request_id'}):
        raise ValueError('Original Controller physical public response differs')
    author = audit['author_first_completed']
    effective = _read(author['effective_input'], expected=attempt/'roles/author-01/effective-input.json')
    prompt = entry.strict_json(req['payload']['input'][0]['content'])
    chosen = decode_proposal(response, prompt)
    selected = scientific(chosen)
    if (chosen != controller['public_decision'] or digest(chosen) != controller['public_decision_sha256']
            or selected != author['normalized_controller_choice']
            or digest(selected) != author['normalized_choice_sha256']
            or selected != effective['decision'] or digest(selected) != effective['decision_sha256']
            or selected['axis'] != 'R' or selected['parent_pair_sha256'] != parent['id']
            or author['parent_source'] != parent['R'] or effective.get('parent_source') != parent['R']
            or effective.get('parent_source_sha256') != parent['R']['sha256']
            or effective['research_context']['parent_version_id'] != parent['id']
            or entry.strict_json(request['payload']['input'][0]['content']) != effective):
        raise ValueError('Original public decision/Author input/active repair parent differs')
    if not Path(parent['R']['path']).is_relative_to(fees.ROOT):
        raise ValueError('Only the exact owned active repair source is readable')
    from earnings_population_delta_author import _original
    source = _original(parent['R']).decode()
    if not 0 < len(source.encode()) <= 65536:
        raise ValueError('Original valid bounded R parent required')
    received = _read(proof['raw_response'])
    patch = message(received)
    if (type(patch) is not dict or set(patch) != FIELDS or patch['decision_sha256'] != digest(selected)
            or patch['parent_source_sha256'] != parent['R']['sha256']
            or type(patch['test_text']) is not str or not 0 < len(patch['test_text'].encode()) <= 32768
            or type(patch['edits']) is not list or not 1 <= len(patch['edits']) <= 16
            or any(type(edit) is not dict or edit.get('kind') != 'replace' for edit in patch['edits'])):
        raise ValueError('Exact original public literal replacement Delta required')
    assembled = _edit_source(source, patch['edits']).encode()
    diagnosis = dict(parent_utf8_bytes=len(source.encode()), assembled_utf8_bytes=len(assembled),
        assembled_sha256=hashlib.sha256(assembled).hexdigest(), source_limit_utf8_bytes=65536,
        excess_utf8_bytes=max(0,len(assembled)-65536), literal_edit_count=len(patch['edits']),
        test_utf8_bytes=len(patch['test_text'].encode()), test_sha256=hashlib.sha256(patch['test_text'].encode()).hexdigest())
    inert = audit['inert_unaccepted_public_delta']
    if (inert.get('raw_response') != proof['raw_response'] or inert.get('parent_source') != parent['R']
            or any(inert.get(key) != value for key,value in diagnosis.items())
            or inert.get('decision_sha256') != digest(selected)
            or inert.get('candidate_executed') is not False or inert.get('source_or_test_written') is not False
            or diagnosis['excess_utf8_bytes'] <= 0):
        raise ValueError('Original inert WIP diagnosis differs; no candidate may be invented')
    return dict(schema='earnings_population_public_wip_evidence_v1', mode=MODE,
        stage='implement', delivery_status='received_but_unaccepted', quality_assessment='not_run',
        source_attempt=proof['id'], runtime=proof['runtime'], fee_evidence=config['fee_evidence'],
        settlement=config['settlement'], role_audit=config['role_audit'], raw_response=proof['raw_response'],
        original_request=proof['request'], original_controller_response=last['response'],
        original_decision_public=selected, original_scientific_decision_sha256=digest(selected),
        parent=dict(version_id=parent['id'], source=parent['R'], other_axis=parent['H']),
        public_failed_delta=patch, public_failed_delta_sha256=digest(patch), capacity=diagnosis,
        qualification='Public evidence supplied under explicit human repair authorization, not recovered state, '
            'accepted Author output, candidate, stage import, Review or score. Source guard rejected delivery '
            'after provider returned. Byte excess is a separate inert diagnosis. New Controller/Author must '
            'produce and validate their own compliant repair; do not automatically apply the old decision/patch.')


def repair_evidence(runtime, packet):
    config = _policy(runtime)
    if config is None:
        return None
    fields = {'schema','apply_to_attempt','round_index','previous_result','parent_version_id',
              'parent_source','fee_evidence','settlement','role_audit','human_authorization'}
    if (type(config) is not dict or set(config) != fields or config.get('schema') != POLICY
            or type(config.get('round_index')) is not int or config['round_index'] != 1
            or type(config.get('human_authorization')) is not str or not config['human_authorization']):
        raise ValueError('Exact source-bound first-round human public-evidence repair policy required')
    if type(packet.get('round_index')) is not int:
        raise ValueError('Exact original round index required')
    if runtime['id'] != config['apply_to_attempt'] or packet['round_index'] != 1:
        return None
    study = engine.read(runtime['forecast_study'])
    origin = engine.read(study['campaign_origin'])
    state = packet['population']
    parent = state['versions'].get(config['parent_version_id'])
    if (origin.get('previous_result') != config['previous_result'] or origin['population'] != state
            or origin.get('author_stage_reuse') is not None or origin.get('controller_stage_import') is not None
            or parent is None or parent['id'] not in state['explorers'] or parent['R'] != config['parent_source']
            or parent['id'] != digest({axis:parent[axis]['sha256'] for axis in ('R','H')})
            or engine.read(packet['feedback']) != origin['research_feedback']):
        raise ValueError('Exact unchanged completed origin/active public repair parent required')
    delivery = _delivery(config, parent)
    return dict(repair_assignment=dict(schema='earnings_population_human_repair_v1',
        parent_version_id=parent['id'], human_authorization=config['human_authorization']), delivery=deepcopy(delivery))
