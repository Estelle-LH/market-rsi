"""Explicit operator-only conservative settlement for the existing400 grant.

Never called by a runtime budget. No retry, refund, invoice claim or new ledger.
The original200 operator and all runtime authority remain unchanged.
"""
from contextlib import closing
import fcntl
import hashlib
from pathlib import Path
import re
import sqlite3

import earnings_population_budget as authority
from earnings_entry import checked, strict_json
from earnings_night_budget import history_snapshot
from edgar_forecast_budget import BudgetStop
from edgar_forecast_full_budget import connect_existing
from edgar_forecast_openai import unit

ROOT = authority.LEDGER.parents[2]/'edgar-population-20261016'
RECEIVED_SCHEMA = 'earnings_population_received_raw_fee_evidence_v1'
RECEIVED_MODE = 'received_completed_raw_postguard_failure_v1'
RECEIVED_POLICY = 'operator_full_ceiling_received_completed_raw_actual_charge_unknown'
SOURCE_GUARD_SCHEMA = 'earnings_population_received_source_guard_fee_evidence_v1'
SOURCE_GUARD_MODE = 'received_completed_raw_source_integrity_failure_v1'
SOURCE_GUARD_POLICY = 'operator_full_ceiling_received_completed_raw_source_integrity_failure_actual_charge_unknown'
SOURCE_GUARD_ID = 'edgar-population-20261016-30'
SOURCE_GUARD_COMMIT = '591f241ef2c24a0804bc812b438fd0e632fdf60b'
SOURCE_GUARD_REQUEST = '1a05683a-d9cc-43c9-8d75-16eaac84fc23'
SOURCE_GUARD_PREFIX = dict(request_count=6278, max_rowid=6278, charged_nano_usd=183252166200,
    rows_sha256='42aa504142b37ef78d9e670fb54485167036da66c58b080dcd2ecca67b6747a9')
SOURCE_GUARD_MISSING = ('configs/earnings_coevolution/harness_v0.py',
    'configs/earnings_coevolution/researcher_v0.py',
    'research/market_rsi/supervisor_harness/research_capacity_activation.py',
    'tools/earnings_clock.py', 'tools/earnings_controller_archive.py', 'tools/earnings_feedback.py',
    'tools/earnings_http.py', 'tools/earnings_research_state.py')
SOURCE_GUARD_PINS = {
    'runtime':'10cc9b09ae36610205f0fb68979f9a661d660ee6dcbb8ef13f23aea81ff9814e',
    'owner_result':'89ced9e94b66c7ee15958324701ebce093f9c6c9ee8b195897f831ee263e57f3',
    'request':'5291c58648e02090fbf4ec7b2e40de004cd518fa96cd698b5d8b539a8604e927',
    'http_intent':'2ba5ca166c92d2252c9eed9ef66313c44d25357fdffcdbdc7640190c21fc61b7',
    'http_failure':'d44e3aa594ba64f8b659e4bb71e84f56975309fa5f5bb7913773d76c142ffcd8',
    'raw_response':'7abf7b0762996f015cedfc339b6247361618f3e0a8eb364f93dbc53109586cdc',
    'role_result':'747bdb5b89828650df09a20886f29d290772822804ea59109d13bffe7a6919ff',
    'role_identity':'e4ac2971c338ba1641845d0890780c2542cce5e473e345aa26bb19796ddb93d2',
    'input_count':'9deb40090d036705476936b219908c432531c8fc934b302a3d5e796751a5c89d',
    'last_numbered_response':'a7ac41c06610506aede23bc3e334436e380a94e94239439594acf9e90f9b96da',
    'source_incident':'ed62a9bac63e32b6b9a8f83ce4b7fcc40eb721953af6aaf25e21a0db270c67a4',
    'closure_audit':'958ebd36f65f03c97ae8164e52e642052037212f7361b3531a961635c4ce11e3',
    'role_boundary':'589a150fadc67e21e11b4a184603cf243ba6b90bebdcb6df06cd0acc5e886b78'}


def _read(binding):
    if (type(binding) is not dict or set(binding) != {'path', 'sha256'}
            or type(binding['path']) is not str or type(binding['sha256']) is not str
            or re.fullmatch('[a-f0-9]{64}', binding['sha256']) is None):
        raise ValueError('Exact immutable receipt binding required')
    path = Path(binding['path'])
    if (not path.is_absolute() or path.resolve() != path or not path.is_file()
            or path.is_symlink() or path.stat().st_nlink != 1):
        raise ValueError('Canonical single-link original receipt required')
    return strict_json(checked(binding))


def inspect_evidence(binding):
    """Validate exact own failed request originals without touching accounting."""
    return _inspect_evidence(binding, received_raw=False)


def inspect_received_raw_evidence(binding):
    """Explicit completed-raw/postguard-failure proof; never infer an invoice."""
    return _inspect_evidence(binding, received_raw=True)


def inspect_source_guard_received_raw_evidence(binding):
    """Only the pinned actual30 post-response Source incident, not any ValueError."""
    return _inspect_evidence(binding, received_raw=True, source_guard=True)


def _inspect_evidence(binding, *, received_raw, source_guard=False):
    if (type(binding) is not dict or type(binding.get('path')) is not str
            or re.fullmatch(re.escape(str(ROOT))+r'/FEE-EVIDENCE-edgar-population-20261016-[0-9]{2,}\.json', binding['path']) is None):
        raise ValueError('Only own saved fee evidence may be opened')
    proof = _read(binding)
    ident = proof.get('id', '')
    schema = SOURCE_GUARD_SCHEMA if source_guard else RECEIVED_SCHEMA if received_raw else 'earnings_population_fee_evidence_v1'
    mode = SOURCE_GUARD_MODE if source_guard else RECEIVED_MODE
    if (proof.get('schema') != schema or received_raw and proof.get('mode') != mode
            or re.fullmatch('edgar-population-20261016-[0-9]{2,}', ident) is None
            or binding['path'] != str(ROOT/('FEE-EVIDENCE-'+ident+'.json'))
            or proof.get('actual_charge_known') is not False or proof.get('retry_allowed') is not False):
        raise ValueError('Exact own explicit unknown-fee evidence required')
    if source_guard and (ident != SOURCE_GUARD_ID or any(
            type(proof.get(key)) is not dict or proof[key].get('sha256') != sha
            for key, sha in SOURCE_GUARD_PINS.items())):
        raise ValueError('Only immutable actual30 Source-guard originals may use this mode')
    runtime_binding = proof['runtime']
    if runtime_binding['path'] != str(ROOT/'inputs'/ident/'runtime-reviewed.json'):
        raise ValueError('Exact original owned runtime binding required')
    runtime = _read(runtime_binding); attempt = ROOT/'attempts'/ident
    token = hashlib.sha256(ident.encode()).hexdigest()
    if (runtime.get('id') != ident or runtime.get('root') != str(attempt)
            or runtime.get('ledger') != str(authority.LEDGER)
            or proof['owner_result']['path'] != str(authority.LEDGER.parent/'.capacity-runtime-claims'/(token+'.result.json'))):
        raise ValueError('Exact original runtime/owner/sole ledger required')
    owner = _read(proof['owner_result'])
    if (owner.get('runtime') != runtime_binding or owner.get('status') != 'FAILED_NO_RETRY'
            or owner.get('retry_allowed') is not False or owner.get('error_type') is None):
        raise ValueError('Original failed owner must be terminal before accounting')
    request_path = Path(proof['request']['path']); slot = request_path.parent
    slots = [path for paths in runtime['slots'].values() for path in paths]
    if (str(slot) not in slots or slot.parent != attempt/'roles'
            or re.fullmatch(r'[0-9]{2}-request\.json', request_path.name) is None):
        raise ValueError('Request must belong to one exact original owned role slot')
    request = _read(proof['request'])
    intent_path = Path(proof['http_intent']['path'])
    if (intent_path.parent != slot or re.fullmatch(r'http-[a-f0-9-]{36}\.intent\.json', intent_path.name) is None
            or proof['http_failure']['path'] != str(intent_path.with_name(intent_path.name.removesuffix('.intent.json')+'.failed.json'))):
        raise ValueError('Exact same physical failed-generation receipts required')
    intent, failure = (_read(proof[key]) for key in ('http_intent', 'http_failure'))
    if (intent.get('endpoint') != '/v1/responses' or intent.get('complete_reservation') != request
            or intent.get('request_receipt_sha256') != proof['request']['sha256']
            or intent.get('budget_request_id') != request.get('request_id')
            or intent.get('retry_allowed') is not False or failure.get('retry_allowed') is not False
            or type(failure.get('exception_type')) is not str
            or request.get('payload', {}).get('model') != 'gpt-6.1-sol'
            or type(request.get('reserved_nano_usd')) is not int or request['reserved_nano_usd'] <= 0):
        raise ValueError('Original physical request/reservation/failure differs')
    absent = [slot/(request_path.name.removesuffix('-request.json')+'-response.json')]
    absent += [intent_path.with_name(intent_path.name.removesuffix('.intent.json')+suffix)
               for suffix in (('.response.json',) if received_raw else ('.raw.bin', '.response.json'))]
    summary = owner['budget_summary']; amount = request['reserved_nano_usd']
    if (any(path.exists() for path in absent) or summary.get('blocked') is not True
            or summary.get('cap_usd') != 400 or summary.get('model_cap_usd') != 100
            or round(summary['unresolved_reserved_usd']*1e9) != amount):
        raise ValueError('Received response, foreign uncertainty or changed original caps')
    authority._prefix(proof['ledger_before'])
    if (round(summary['charged_upper_bound_usd']*1e9) != proof['ledger_before']['charged_nano_usd']
            or summary['generation_requests_reserved'] != proof['ledger_before']['request_count']):
        raise ValueError('Original owner failure and saved closing prefix differ')
    if received_raw:
        if source_guard:
            _source_guard_incident(proof, runtime, owner, request, attempt)
        _received_raw(proof, runtime, request, intent, failure, request_path, intent_path,
                      expected_error='ValueError' if source_guard else 'BudgetStop')
    if 'model_budget_amendment' in runtime:
        with closing(sqlite3.connect(authority.LEDGER.as_uri()+'?mode=ro',uri=True)) as db:
            db.execute('BEGIN')
            _model_budget(db, proof, runtime)
    return proof, runtime, request


def _model_budget(db, proof, runtime):
    """Historical committed authority; never current-file replacement or credit."""
    from earnings_population_model_budget import (MODEL, PLAN, IMPLEMENTATIONS,
        read_grant, _authority, authorized_liabilities, dispatch_totals)
    from earnings_population_source_history import source_name
    from earnings_population_window import minutes
    bound = runtime['model_budget_amendment']
    if (type(bound) is not dict or set(bound) != {'path','sha256'}
            or runtime.get('schema') != 'earnings_population_runtime_v1'
            or type(runtime.get('additional_cap_nano_usd')) is not int
            or not 1 <= runtime['additional_cap_nano_usd'] <= 5_000_000_000 or minutes(runtime) != 90):
        raise ValueError('Exact prospective model grant and unchanged window5/90 required')
    owner = _read(proof['owner_result'])
    summary = owner.get('budget_summary', {})
    if (_read(proof['runtime']) != runtime or owner.get('runtime') != proof['runtime']
            or owner.get('status') != 'FAILED_NO_RETRY' or owner.get('retry_allowed') is not False
            or summary.get('model_cap_usd') != 100 or summary.get('model_budget_optin') != bound
            or authority._encoded(summary.get('dispatch_model_caps_usd')) != authority._encoded({MODEL:300,'other_models':100})):
        raise ValueError('Original failed owner summary/model grant differs')
    grant = read_grant(db, required_binding=bound)
    sources = runtime.get('sources', {})
    if grant is None or sources.get(PLAN) != grant['authority']:
        raise ValueError('Historical runtime authority differs from activated grant')
    _authority(sources[PLAN], runtime['source_commit'])  # Git bytes, not mutable current prose.
    for name in IMPLEMENTATIONS:
        binding = sources.get(name)
        if (type(binding) is not dict or set(binding) != {'path','sha256'}
                or source_name(binding['path'],authority.REPO) != name
                or binding['sha256'] != grant['implementations'][name]
                or hashlib.sha256(authority._git(runtime['source_commit'],name)).hexdigest() != binding['sha256']):
            raise ValueError('Historical financial implementation commitment differs')
    authorized_liabilities(db, authority.CAP)
    dispatch_totals(db, MODEL, 0, bound)  # Own uncertain reservation is already counted ONCE.
    return grant['new_model_cap_nano_usd']


def _source_guard_incident(proof, runtime, owner, request, attempt):
    """Authenticate the known incident; historical source paths are metadata only."""
    paths = {'source_incident':ROOT/'ROOT-SOURCE-INCIDENT30.json',
             'closure_audit':ROOT/'CUMULATIVE400-LIVE30-CLOSURE-AUDIT.json',
             'role_boundary':attempt/'role-validation/author-01.json'}
    if any(proof[key].get('path') != str(path) for key, path in paths.items()):
        raise ValueError('Exact owned incident/closure/role-boundary paths required')
    incident, closure, boundary = (_read(proof[key]) for key in paths)
    old_source = '/private/tmp/market-rsi-earnings-overnight-FGRfBI/checkout'
    inventory = incident.get('source_inventory', {})
    missing_names = sorted(('clock', *SOURCE_GUARD_MISSING))
    unaccepted = closure.get('transport_verification', {}).get('raw_received_unaccepted', {})
    physical = unaccepted.get('physical', {})
    if (runtime.get('source_commit') != SOURCE_GUARD_COMMIT or owner.get('error_type') != 'LoopHalted'
            or request.get('request_id') != SOURCE_GUARD_REQUEST or request.get('reserved_nano_usd') != 599450000
            or proof['ledger_before'] != SOURCE_GUARD_PREFIX
            or incident.get('schema') != 'earnings_owned_source_incident_v1'
            or incident.get('attempt') != SOURCE_GUARD_ID or incident.get('owner') != 'Root'
            or incident.get('source_commit') != SOURCE_GUARD_COMMIT or incident.get('checkout') != old_source
            or type(incident.get('true_exit_code')) is not int or incident['true_exit_code'] != 1
            or incident.get('failure_class') != 'POST_RESPONSE_SOURCE_INTEGRITY_FAILURE'
            or inventory.get('bound_names') != 133 or inventory.get('unchanged_present_names') != 124
            or inventory.get('changed_present_names') != [] or inventory.get('missing_names') != 9
            or sorted(inventory.get('missing_unique_files', [])) != sorted(SOURCE_GUARD_MISSING)
            or any(runtime.get('sources', {}).get(name, {}).get('path') != old_source+'/'+name
                   for name in SOURCE_GUARD_MISSING)
            or runtime.get('sources', {}).get('clock') != runtime.get('sources', {}).get('tools/earnings_clock.py')
            or closure.get('runtime') != proof['runtime'] or closure.get('source_commit') != SOURCE_GUARD_COMMIT
            or closure.get('original_owner', {}).get('binding') != proof['owner_result']
            or closure.get('accounting', {}).get('snapshot') != proof['ledger_before']
            or sorted(closure.get('source_verification', {}).get('missing_binding_names', [])) != missing_names
            or unaccepted.get('binding') != proof['request'] or unaccepted.get('request_id') != SOURCE_GUARD_REQUEST
            or physical.get('intent') != proof['http_intent'] or physical.get('raw') != proof['raw_response']
            or physical.get('failure', {}).get('binding') != proof['http_failure']
            or physical.get('numbered_response') is not None or physical.get('sidecar') is not None
            or closure.get('per_role', {}).get('author-01', {}).get('result_binding') != proof['role_result']
            or boundary.get('runtime') != proof['runtime'] or boundary.get('role') != 'author'
            or boundary.get('slot') != str(attempt/'roles/author-01')
            or boundary.get('schema') != 'earnings_population_role_validation_v1'
            or boundary.get('entry_full_audit') != 'PASS' or boundary.get('exit_full_audit') != 'FAILED'
            or boundary.get('audit_error') != 'ValueError' or boundary.get('original_error') != 'RuntimeError'
            or boundary.get('output_accepted') is not False or boundary.get('retry_allowed') is not False):
        raise ValueError('Pinned post-response Source-integrity incident differs')


def _received_raw(proof, runtime, request, intent, failure, request_path, intent_path, *, expected_error='BudgetStop'):
    """Join original completed wire bytes to an undelivered final role response."""
    slot, turn = request_path.parent, int(request_path.name[:2])
    role = next((name for name, slots in runtime['slots'].items() if str(slot) in slots), None)
    previous = f'{turn-1:02d}-response.json'
    expected = {'raw_response': intent_path.with_name(intent_path.name.removesuffix('.intent.json')+'.raw.bin'),
                'input_count': slot/f'{turn:02d}-count.json', 'role_result': slot/'result.json',
                'role_identity': slot/'identity.json', 'last_numbered_response': slot/previous}
    if (role not in ('controller', 'author', 'review') or turn != 8
            or any(proof[key]['path'] != str(path) for key, path in expected.items())):
        raise ValueError('Exact final original role/physical response paths required')
    if not 0 < expected['raw_response'].stat().st_size <= 16_000_000:
        raise ValueError('Original bounded successful wire response required')
    result, identity = _read(proof['role_result']), _read(proof['role_identity'])
    if identity.get('context', {}).get('path') != str(slot.parent.parent/f'context-{role}.json'):
        raise ValueError('Exact original role context required')
    context = _read(identity['context']); _read(proof['last_numbered_response'])
    limits, rates = runtime['limits'][role], dict(runtime['rates'], effort=runtime['role_efforts'][role])
    if (result.get('status') != 'FAILED_NO_RETRY' or result.get('error_type') != expected_error
            or result.get('retry_allowed') is not False or type(result.get('turns')) is not int
            or result['turns'] != turn or result.get('final_numbered_response') != previous
            or failure.get('exception_type') != expected_error
            or identity.get('source_commit') != runtime['source_commit']
            or identity.get('max_turns') != 8 or context.get('source_commit') != runtime['source_commit']
            or context.get('root') != runtime['root'] or context.get('slots') != runtime['slots'][role]
            or context.get('schema') not in (f'earnings_capacity_{role}_transport_v1', f'earnings_capacity_{role}_transport_v2')
            or type(runtime.get('additional_cap_nano_usd')) is not int
            or not 0 < runtime['additional_cap_nano_usd'] <= 5_000_000_000
            or context.get('rates') != rates or context.get('limits') != limits
            or rates != dict(api_model='gpt-6.1-sol', input='2', cached='0.1', write='2.5', output='10',
                             effort=runtime['role_efforts'][role])
            or request['payload'].get('reasoning') != {'effort':rates['effort']}
            or intent.get('payload') != dict(request['payload'], max_output_tokens=limits['max_output_tokens'],
                                           service_tier='default', store=False)):
        raise ValueError('Original failed role/source/context/physical payload differs')
    count = _read(proof['input_count']).get('input_tokens')
    if (type(count) is not int or not 0 <= count <= limits['max_input_tokens']
            or request['reserved_nano_usd'] != count*max(unit(rates[k]) for k in ('input','cached','write'))
                +limits['max_output_tokens']*unit(rates['output'])):
        raise ValueError('Original counted token reservation differs')
    raw = _read(proof['raw_response'])
    if type(raw) is not dict:
        raise ValueError('Exact completed raw object required')
    usage = raw.get('usage', {})
    if (raw.get('status') != 'completed' or raw.get('error') is not None
            or raw.get('object') != 'response' or raw.get('model') != rates['api_model']
            or raw.get('service_tier') != 'default' or raw.get('incomplete_details') is not None
            or type(raw.get('id')) is not str or not re.fullmatch(r'resp_[A-Za-z0-9_-]+', raw['id'])
            or any(type(raw.get(key)) is not int or raw[key] < 0 for key in ('created_at','completed_at'))
            or raw['completed_at'] < raw['created_at'] or type(usage) is not dict
            or authority._encoded(proof.get('received_usage')) != authority._encoded(usage)):
        raise ValueError('Exact completed raw response/public usage required')
    inp, out, total = (usage.get(key) for key in ('input_tokens','output_tokens','total_tokens'))
    if (type(usage.get('input_tokens_details')) is not dict
            or type(usage.get('output_tokens_details', {})) is not dict):
        raise ValueError('Malformed completed raw usage detail objects')
    cached = usage.get('input_tokens_details', {}).get('cached_tokens')
    write = usage.get('input_tokens_details', {}).get('cache_write_tokens', 0)
    reasoning = usage.get('output_tokens_details', {}).get('reasoning_tokens', 0)
    if (any(type(value) is not int or value < 0 for value in (inp,out,total,cached,write,reasoning))
            or inp > count or out > limits['max_output_tokens'] or total != inp+out
            or cached > inp or write > inp or reasoning > out):
        raise ValueError('Malformed or unreserved completed raw usage')
    output = raw.get('output')
    if (type(output) is not list or not output or any(type(item) is not dict for item in output)
            or any(item.get('type') != 'reasoning' for item in output[:-1])):
        raise ValueError('One final completed raw message required')
    message = output[-1]; content = message.get('content')
    if (message.get('type') != 'message' or message.get('role') != 'assistant'
            or message.get('status') != 'completed' or type(content) is not list or not content
            or any(type(item) is not dict or item.get('type') != 'output_text'
                   or type(item.get('text')) is not str or not item['text'] for item in content)):
        raise ValueError('One final completed raw message required')


def _book(db, proof, runtime, request):
    """Original full-ceiling policy, with exact activated400 rather than200."""
    if authority.validate_cap(db, amendment=runtime['budget_amendment']) != authority.CAP:
        raise BudgetStop('Original activated400 grant required')
    before = history_snapshot(db)
    if before != proof['ledger_before']:
        raise BudgetStop('Accounting changed since saved evidence; diagnose again')
    config = db.execute('SELECT cap,model_cap,blocked FROM config WHERE id=1').fetchone()
    row = db.execute('SELECT id,model,reserved,charged,status FROM requests WHERE id=?',
                     (request['request_id'],)).fetchone()
    expected = (request['request_id'], 'gpt-6.1-sol', request['reserved_nano_usd'], 0, 'uncertain')
    if (config != (authority.CAP, authority.FULL_MODEL_CAP, 1) or row != expected
            or db.execute("SELECT id,model,reserved,charged,status FROM requests WHERE status NOT IN ('settled','settled_upper_bound')").fetchall() != [expected]
            or db.execute('SELECT 1 FROM reconciliations WHERE request_id=?', (request['request_id'],)).fetchone()):
        raise BudgetStop('Only the untouched sole uncertain request may settle')
    authority._liabilities(db, authority.CAP)
    model_cap = (_model_budget(db, proof, runtime) if 'model_budget_amendment' in runtime
                 else authority.FULL_MODEL_CAP)
    amount = request['reserved_nano_usd']
    model = db.execute('SELECT COALESCE(SUM(charged),0) FROM requests WHERE model=?', ('gpt-6.1-sol',)).fetchone()[0]
    if (before['charged_nano_usd']+amount > authority.CAP or model+amount > model_cap
            or before['charged_nano_usd']+amount-runtime['baseline']['charged_nano_usd'] > runtime['additional_cap_nano_usd']):
        raise BudgetStop('Full liability exceeds original global/model/window allowance')
    received = proof.get('schema') == RECEIVED_SCHEMA and proof.get('mode') == RECEIVED_MODE
    source_guard = proof.get('schema') == SOURCE_GUARD_SCHEMA and proof.get('mode') == SOURCE_GUARD_MODE
    policy = SOURCE_GUARD_POLICY if source_guard else RECEIVED_POLICY if received else 'operator_full_ceiling_actual_charge_unknown'
    db.execute('INSERT INTO reconciliations(request_id,evidence_sha256,prior_status,prior_charge,ceiling,policy) VALUES(?,?,?,?,?,?)',
        (request['request_id'], proof['_binding']['sha256'], 'uncertain', 0, amount,
         policy))
    db.execute("UPDATE requests SET charged=reserved,status='settled_upper_bound' WHERE id=?", (request['request_id'],))
    db.execute('UPDATE config SET blocked=0 WHERE id=1')
    result = dict(request_id=request['request_id'], conservative_charge_nano_usd=amount,
        actual_charge_known=False, refund_nano_usd=0, retry_allowed=False,
        evidence=proof['_binding'], before=before, after=history_snapshot(db))
    if received: result.update(mode=RECEIVED_MODE, policy=policy, provider_usage_received=True)
    if source_guard:
        result.update(mode=SOURCE_GUARD_MODE, policy=policy, provider_usage_received=True,
                      source_incident=proof['source_incident'])
    return result


def reconcile_at_ceiling(evidence_binding):
    """One deliberate operator action under the original nonblocking shared lock."""
    proof, runtime, request = inspect_evidence(evidence_binding)
    return _reconcile(evidence_binding, proof, runtime, request)


def reconcile_received_raw_at_ceiling(evidence_binding):
    """Distinct explicit operator action: keep raw, book entire original ceiling."""
    proof, runtime, request = inspect_received_raw_evidence(evidence_binding)
    return _reconcile(evidence_binding, proof, runtime, request)


def reconcile_source_guard_received_raw_at_ceiling(evidence_binding):
    """Explicit actual30 action only; retain raw and charge the full old ceiling."""
    proof, runtime, request = inspect_source_guard_received_raw_evidence(evidence_binding)
    return _reconcile(evidence_binding, proof, runtime, request)


def _reconcile(evidence_binding, proof, runtime, request):
    proof['_binding'] = dict(evidence_binding)
    lock = authority.LEDGER.parent/'.capacity-runtime.lock'
    if lock.resolve() != lock or lock.is_symlink() or not lock.is_file():
        raise BudgetStop('Existing canonical shared execution lock required')
    with lock.open('rb') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with closing(connect_existing(authority.LEDGER)) as db:
            try:
                db.execute('BEGIN IMMEDIATE')
                result = _book(db, proof, runtime, request)
                db.execute('COMMIT')
            except BaseException:
                if db.in_transaction: db.execute('ROLLBACK')
                raise
    return result
