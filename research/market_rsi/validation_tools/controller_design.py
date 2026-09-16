"""Isolated metadata-only tools for a GLM independent-validation design.

No downloader, evaluator, Python execution, arbitrary file reader or paid
provider is exposed. Requests are proposals, never authority to acquire data.
"""
import argparse
from datetime import date
import fcntl
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller_activity_log import append_activity, read_activity_events, verify_activity_log
from market_rsi import canonical, digest, file_hash, fresh_json, identifier
from independent_validation import dates, positive_int, validate_proposal, verify_context
from paid_budget import money


BASE_INSTRUCTIONS = (
    'You are the GLM researcher in the existing Codex harness. Your last completed stage '
    'selected t7 as a small improvement on repeatedly opened diagnostic dates, not a fresh '
    'test or proof of RSI improvement. This is a NEW validation-design phase, not a DEFER '
    'learning continuation. Inspect the frozen predictor/source context and readiness first. '
    'You choose a defensible metadata-only validation proposal or explicitly request missing '
    'compatible data and defer. Do not choose dates from future price movements or scores. '
    'The model, features, target and scoring weights are fixed. Review all prior open research '
    'via the archive; do not infer unobserved periods are fresh. A scanned raw file, metadata '
    'view and label/score exposure are different facts. No current candidate dates have been '
    'admitted as fresh, and the retained corpus cannot supply twenty untouched future dates. '
    'Twenty closed UTC sessions is a minimum, not proof of statistical power for a .159% gain. '
    'You may specify a data request or explain an implementation gap; requests never authorize '
    'a purchase, cap increase, download or test. Dates/windows in requests are requirements, '
    'not newly frozen evaluation populations. A new venue/source contract needs a separately '
    'declared data-stage study, not silent substitution. All uncertainty and failed attempts '
    'stay in the archive. Literature search here uses a frozen catalog, not live web or full '
    'papers. Submit the first valid decision with submit_validation_decision and exit. Prose '
    'alone is not a submitted decision. Never claim training, testing or downloading happened.'
)
FILES = {'context.json', 'source-contract.json', 'selected-plan.json', 'readiness.json',
         'inventory.json', 'exposure.json', 'archive.json', 'literature.json', 'limits.json'}
TEXT = {'type': 'string', 'minLength': 1, 'maxLength': 12000}
ID = {'type': 'string', 'maxLength': 100}


def tool(name, description, properties=None):
    properties = properties or {}
    return {'name': name, 'description': description, 'inputSchema': {'type': 'object',
            'properties': properties, 'required': list(properties), 'additionalProperties': False}}


TOOLS = [
    tool('inspect_validation_context', 'Read immutable selected model/target/source and proposal shape.'),
    tool('inspect_validation_readiness', 'Read coverage, exposure limits and budget; not market prices or labels.'),
    tool('inspect_validation_archive', 'Read all supplied prior opened diagnostic research, not fresh results.'),
    tool('search_public_literature', 'Search the frozen primary-source notes; NOT live search.', {'query': TEXT}),
    tool('propose_validation_plan', 'Archive one valid metadata plan; it does NOT admit or execute a test.',
         {'proposal': {'type': 'object'}}),
    tool('request_validation_data', 'Record a bounded data requirement for review; never download or buy.',
         {'request': {'type': 'object'}}),
    tool('submit_validation_decision', 'Submit the first propose/defer decision and exit.',
         {'action': {'type': 'string', 'enum': ['propose', 'defer']},
          'artifact_id': ID, 'reason': TEXT}),
]
ALLOWED_TOOLS = tuple(t['name'] for t in TOOLS)
REQUEST_FIELDS = {'request_id', 'context_sha256', 'source_contract_sha256',
                  'minimum_sessions', 'earliest_utc_date', 'latest_utc_date',
                  'required_fields', 'max_new_download_bytes', 'max_vendor_spend_usd',
                  'reason', 'limitations'}
LOG = 'validation-design-activity.jsonl'
DECISION = 'submitted-validation-decision.json'


def load(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
        raise ValueError('bounded regular metadata JSON required')
    return json.loads(path.read_bytes())


def text(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 12000:
        raise ValueError('bounded nonempty rationale/text required')
    return value


def validate_workspace(root):
    if root.is_symlink():
        raise ValueError('workspace symlink forbidden')
    m = load(root / 'workspace.json')
    if (m.get('schema') != 'historical_validation_design_workspace_v1'
            or set(m.get('files', {})) != FILES or m.get('new_labels_present') is not False
            or m.get('purpose') not in ('controller_design', 'transport_canary')):
        raise ValueError('invalid validation-design workspace')
    for name, expected in m['files'].items():
        load(root / name)
        if file_hash(root / name) != expected:
            raise ValueError('frozen metadata input changed')
    context = verify_context(load(root / 'context.json'))
    if (load(root / 'source-contract.json')['contract_sha256'] != context['source_contract_sha256']
            or digest(load(root / 'selected-plan.json')) != context['selected_plan_sha256']):
        raise ValueError('selected plan/source differs from context')
    if load(root / 'limits.json') != {'max_tool_calls': 32, 'max_successful_plans': 1,
            'max_successful_data_requests': 1, 'max_claims_per_kind': 4,
            'authorized_download_headroom_bytes': 0, 'vendor_purchase_authorized': False,
            'execution_tools_present': False}:
        raise ValueError('planning scope or authority changed')
    return m


def make_workspace(output, visible, session_id, purpose):
    identifier(session_id)
    if set(visible) != FILES or purpose not in ('controller_design', 'transport_canary'):
        raise ValueError('exact metadata-only workspace required')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name, value in visible.items():
        fresh_json(output / name, value)
    for name in ('plans', 'data-requests'):
        (output / name).mkdir()
    fresh_json(output / 'workspace.json', {'schema': 'historical_validation_design_workspace_v1',
        'session_id': session_id, 'purpose': purpose, 'new_labels_present': False,
        'files': {name: file_hash(output / name) for name in visible}})
    return validate_workspace(output)


def validate_data_request(request, context):
    if not isinstance(request, dict) or set(request) != REQUEST_FIELDS:
        raise ValueError('exact data request fields required')
    identifier(request['request_id'])
    if (request['context_sha256'] != context['context_sha256']
            or request['source_contract_sha256'] != context['source_contract_sha256']):
        raise ValueError('request must state the frozen compatibility requirement')
    positive_int(request['minimum_sessions'], 'session count')
    if request['minimum_sessions'] < context['minimum_final_utc_days']:
        raise ValueError('requested final session count below minimum')
    first, last = request['earliest_utc_date'], request['latest_utc_date']
    dates([first] if first == last else [first, last])
    if first <= max(context['known_opened_dates_lower_bound']):
        raise ValueError('request overlaps known opened history')
    if (date.fromisoformat(last) - date.fromisoformat(first)).days + 1 < request['minimum_sessions']:
        raise ValueError('requested date window cannot contain requested UTC sessions')
    fields = request['required_fields']
    if not isinstance(fields, list) or not 1 <= len(fields) <= 100 or len(set(fields)) != len(fields):
        raise ValueError('bounded distinct required source fields required')
    for field in fields:
        text(field)
    positive_int(request['max_new_download_bytes'], 'requested download bound', allow_zero=True)
    money(request['max_vendor_spend_usd'])
    text(request['reason']); text(request['limitations'])
    return {'request_sha256': digest(request), 'request_valid': True,
            'download_authorized': False, 'purchase_authorized': False,
            'execution_admitted': False, 'fresh_dates_admitted': [],
            'new_authority_needed': request['max_new_download_bytes'] > 0
                or money(request['max_vendor_spend_usd']) > 0}


class Broker:
    def __init__(self, workspace):
        self.root = Path(workspace)
        validate_workspace(self.root)
        self.manifest_sha256 = file_hash(self.root / 'workspace.json')

    def call(self, name, arguments):
        with (self.root / '.tool.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            validate_workspace(self.root)
            if file_hash(self.root / 'workspace.json') != self.manifest_sha256:
                raise ValueError('workspace manifest changed during session')
            if (self.root / DECISION).exists():
                raise ValueError('decision already submitted; no continuation or resampling')
            events = read_activity_events(self.root / LOG)
            if len(events) >= 32:
                raise ValueError('validation design tool budget exhausted')
            if len(canonical(arguments).encode()) > 128000:
                raise ValueError('tool argument payload too large')
            try:
                if name not in ALLOWED_TOOLS or not isinstance(arguments, dict):
                    raise ValueError('unknown validation-design tool')
                expected = next(t['inputSchema']['properties'] for t in TOOLS if t['name'] == name)
                if set(arguments) != set(expected):
                    raise ValueError('unexpected tool argument fields')
                result = self._call(name, arguments, events)
            except Exception as exc:
                append_activity(self.root / LOG, {'tool': name, 'arguments': arguments,
                    'status': 'error', 'error': str(exc)})
                raise
            append_activity(self.root / LOG, {'tool': name, 'arguments': arguments,
                'status': 'ok', 'result': result})
            return result

    def _claim(self, kind, item_id, body):
        identifier(item_id)
        directory = self.root / kind
        if directory.is_symlink():
            raise ValueError('artifact directory symlink forbidden')
        existing = list(directory.iterdir())
        if len(existing) >= 4 or any((p / 'result.json').exists() for p in existing):
            raise ValueError('one successful artifact per kind; bounded failed claims retained')
        target = directory / item_id
        target.mkdir(exist_ok=False)
        fresh_json(target / 'claim.json', {'request': body, 'request_sha256': digest(body)})
        return target

    def _call(self, name, a, events):
        context = load(self.root / 'context.json')
        if name == 'inspect_validation_context':
            from independent_validation import PROPOSAL_KEYS
            return {'context': context, 'source_contract': load(self.root / 'source-contract.json'),
                'selected_plan': load(self.root / 'selected-plan.json'),
                'proposal_fields': sorted(PROPOSAL_KEYS), 'data_request_fields': sorted(REQUEST_FIELDS),
                'interval_fields': ['unit=utc_date', 'block_days', 'replicates', 'confidence'],
                'submitted_plan_is_not_execution_permission': True}
        if name == 'inspect_validation_readiness':
            return {k: load(self.root / (k + '.json')) for k in ('readiness', 'inventory', 'exposure', 'limits')}
        if name == 'inspect_validation_archive':
            return load(self.root / 'archive.json')
        if name == 'search_public_literature':
            terms = set(text(a['query']).lower().split())
            papers = load(self.root / 'literature.json')['papers']
            return {'mode': 'frozen_catalog_not_live_search', 'papers': sorted(papers,
                key=lambda p: -sum(t in canonical(p).lower() for t in terms))[:8]}
        if name in ('propose_validation_plan', 'request_validation_data'):
            is_plan = name == 'propose_validation_plan'
            body = a['proposal' if is_plan else 'request']
            if not isinstance(body, dict):
                raise ValueError('artifact body must be an object')
            item_id = body.get('proposal_id' if is_plan else 'request_id')
            target = self._claim('plans' if is_plan else 'data-requests', item_id, body)
            try:
                result = validate_proposal(body, context) if is_plan else validate_data_request(body, context)
                result = {**result, 'artifact_id': item_id, 'body': body,
                          'claim_sha256': file_hash(target / 'claim.json')}
                fresh_json(target / 'result.json', result)
                return result
            except Exception as exc:
                fresh_json(target / 'failure.json', {'error': str(exc), 'automatic_retry': False})
                raise
        if name == 'submit_validation_decision':
            seen = {e['tool'] for e in events if e['status'] == 'ok'}
            if not {'inspect_validation_context', 'inspect_validation_readiness'} <= seen:
                raise ValueError('inspect context and readiness before deciding')
            text(a['reason'])
            artifact = a['artifact_id']
            if a['action'] == 'propose':
                identifier(artifact)
                record = load(self.root / 'plans' / artifact / 'result.json')
                validate_proposal(record['body'], context)
                creation = 'propose_validation_plan'
            elif a['action'] == 'defer':
                if artifact:
                    identifier(artifact)
                    record = load(self.root / 'data-requests' / artifact / 'result.json')
                    validate_data_request(record['body'], context)
                    creation = 'request_validation_data'
                else:
                    record = None
            else:
                raise ValueError('action must be propose or defer')
            if record is not None:
                claim_path = self.root / ('plans' if a['action'] == 'propose' else 'data-requests') / artifact / 'claim.json'
                if record['claim_sha256'] != file_hash(claim_path):
                    raise ValueError('artifact claim changed')
                if not any(e['tool'] == creation and e['status'] == 'ok' and e['result'] == record for e in events):
                    raise ValueError('artifact lacks exact successful creation log')
            decision = {**a, 'context_sha256': context['context_sha256'],
                        'artifact_sha256': digest(record) if record else None,
                        'workspace_purpose': load(self.root / 'workspace.json')['purpose'],
                        'execution_admitted': False}
            fresh_json(self.root / DECISION, decision)
            # The unchanged provider terminal handshake requires a positive
            # persisted byte count. Without it Codex asks for another sample.
            return {'submitted': True, 'bytes': (self.root / DECISION).stat().st_size,
                    'decision': decision, 'execution_admitted': False}
        raise ValueError('unknown tool')


def assess_activity(root):
    validate_workspace(root)
    log = verify_activity_log(root / LOG)
    events = read_activity_events(root / LOG)
    submitted = [e for e in events if e['tool'] == 'submit_validation_decision' and e['status'] == 'ok']
    if len(submitted) != 1 or events[-1] != submitted[0]:
        raise ValueError('exactly one terminal decision required')
    decision = load(root / DECISION)
    if submitted[0]['result']['decision'] != decision:
        raise ValueError('submitted decision changed')
    if decision['artifact_id']:
        directory = root / ('plans' if decision['action'] == 'propose' else 'data-requests') / decision['artifact_id']
        record = load(directory / 'result.json')
        if digest(record) != decision['artifact_sha256'] or file_hash(directory / 'claim.json') != record['claim_sha256']:
            raise ValueError('terminal artifact or claim changed')
    return {'valid': True, 'log': log, 'action': decision['action'], 'execution_admitted': False,
            'model_authorship_proven_by_this_audit': False,
            'limits': 'Authorship requires the separate paid harness session/events; tools alone are not a model run.'}


def serve(broker):
    for line in sys.stdin:
        request = None
        try:
            if len(line.encode()) > 256000:
                raise ValueError('MCP line too large')
            request = json.loads(line)
            if 'id' not in request:
                continue
            method = request.get('method')
            if method == 'initialize':
                result = {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}},
                          'serverInfo': {'name': 'historical-validation-design', 'version': '1'}}
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                result = {'tools': TOOLS}
            elif method == 'tools/call':
                try:
                    params = request.get('params', {})
                    value = broker.call(params.get('name'), params.get('arguments', {})); failed = False
                except Exception as exc:
                    value = {'accepted': False, 'message': str(exc)}; failed = True
                result = {'content': [{'type': 'text', 'text': canonical(value)}], 'isError': failed}
            else:
                raise ValueError('unsupported MCP method')
            response = {'jsonrpc': '2.0', 'id': request['id'], 'result': result}
        except Exception as exc:
            if not isinstance(request, dict) or 'id' not in request:
                continue
            response = {'jsonrpc': '2.0', 'id': request['id'], 'error': {'code': -32602, 'message': str(exc)}}
        print(canonical(response), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    args = parser.parse_args()
    os.environ.clear()
    serve(Broker(args.workspace))
