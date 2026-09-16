"""Metadata-only source research tools; separate from frozen t7 validation.

The controller may compare sources and request exact advertised objects. It
cannot buy/download those objects, change the old model, or access new labels.
Anonymous public *directory metadata* is the only optional network capability.
"""
import argparse
from datetime import date
import fcntl
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'validation_tools'), str(ROOT / 'audit_tools')]
from controller_activity_log import append_activity, read_activity_events, verify_activity_log
from independent_validation import verify_context
from market_rsi import canonical, digest, file_hash, fresh_json, identifier
from proof_store import read_pinned_json
from public_source_metadata import metadata_url, run as inspect_directory

FILES = {'context.json', 'source-contract.json', 'archive.json', 'source-review-catalog.json',
         'prior-source-catalog.json', 'evidence.json', 'readiness.json', 'literature.json', 'limits.json'}
LIMITS = {'max_tool_calls': 32, 'max_artifact_claims': 4, 'max_public_metadata_calls': 4,
          'max_metadata_response_bytes': 524288, 'authorized_raw_download_headroom_bytes': 0,
          'purchase_authorized': False, 'training_tools': False, 'evaluation_tools': False}
LOG = 'source-review-activity.jsonl'
DECISION = 'submitted-source-review-decision.json'
INSTRUCTIONS = (
    'You are the GLM researcher in the existing Codex harness, entering a separately declared '
    'DATA-SOURCE REVIEW, not rerunning t7 selection or silently changing its validation contract. '
    'The old source is archived; the previously requested later partitions were not found. '
    'Inspect current context, readiness, all prior archive and source alternatives. Additional '
    'source leads are non-exhaustive publisher claims, not a recommended winner or raw QA. '
    'Choose a defensible source/field compatibility study or explicitly request more metadata. '
    'You may inspect anonymous pinned public root-directory metadata; this never reads data rows. '
    'Other literature/source search uses supplied notes, not unrestricted live web. Request '
    'missing public documentation instead of inventing availability. All research actions are logged. '
    'You can propose source and clock changes, but they create a new data stage, not independent '
    'validation of unchanged t7. Preserve the selected predictor and objective. Do not fit, '
    'select dates from future movement, discard quiet raw records, infer zero activity from outages, '
    'or admit new Test dates. Data QA is opened Train-only diagnostic material. Later untouched '
    'evaluation requires separate pre-result design, whole-market/time isolation and at least '
    '20 complete sessions; 20 is not proof of adequate power. Calendar windows and advertised '
    'file dates do not prove complete event sessions. Map each required field and availability '
    'clock, distinguish documented/requires-raw-check/unavailable, and explain unresolved gaps. '
    'Exact advertised files determine payload size; do not invent a 100GB need. The remaining '
    'raw-download allowance is zero; every source proposal remains pending external authority '
    'and independent QA. No purchase or cap increase is authorized by your proposal. Submit '
    'the first valid source-review decision and exit, without resampling or selecting among replies.'
)


def bounded_text(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 12000:
        raise ValueError('bounded nonempty text required')
    return value


def texts(value, maximum=50):
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        raise ValueError('bounded nonempty text list required')
    for item in value:
        bounded_text(item)
    if len(set(value)) != len(value):
        raise ValueError('distinct text entries required')
    return value


def tool(name, description, properties=None):
    properties = properties or {}
    return {'name': name, 'description': description, 'inputSchema': {'type': 'object',
        'properties': properties, 'required': list(properties), 'additionalProperties': False}}


TEXT = {'type': 'string', 'minLength': 1, 'maxLength': 12000}
TOOLS = [
    tool('inspect_source_context', 'Read frozen model context, sources, plan shape and current scope.'),
    tool('inspect_source_readiness', 'Read current gaps, exact directory receipts, and authority limits.'),
    tool('inspect_source_archive', 'Read all supplied prior open research, decisions and corrections.'),
    tool('search_source_notes', 'Search frozen source/literature notes, NOT live web.', {'query': TEXT}),
    tool('inspect_public_source_directory', 'Anonymous root directory metadata only, never file contents.',
         {'dataset': TEXT, 'revision': TEXT}),
    tool('propose_source_plan', 'Propose a separate data study; exact payload bytes are derived, not permission.',
         {'plan': {'type': 'object'}}),
    tool('request_source_metadata', 'Record missing public documentation; no automatic network or download.',
         {'request': {'type': 'object'}}),
    tool('submit_source_review_decision', 'Submit the first propose/request_metadata/defer decision and exit.',
         {'action': {'type': 'string', 'enum': ['propose', 'request_metadata', 'defer']},
          'artifact_id': {'type': 'string', 'maxLength': 100}, 'reason': TEXT}),
]
ALLOWED_TOOLS = tuple(t['name'] for t in TOOLS)
PLAN_FIELDS = {'plan_id', 'context_sha256', 'review_catalog_sha256', 'stage', 'source_ids',
    'objects', 'requested_window', 'minimum_complete_sessions', 'question', 'source_contract_changes',
    'required_streams', 'field_mapping', 'clock_policy', 'gap_policy', 'coverage_policy',
    'unresolved_questions', 'artifact_use', 'quiet_rows', 'validation_claim'}
REQUEST_FIELDS = {'request_id', 'source_name', 'public_metadata_urls', 'questions', 'relevance'}


def validate_workspace(root, expected_manifest):
    root = Path(root)
    manifest = read_pinned_json(root, 'workspace.json', expected_manifest)
    if (set(manifest) != {'schema', 'session_id', 'purpose', 'files', 'new_labels_present'}
            or manifest['schema'] != 'historical_source_review_workspace_v1'
            or set(manifest['files']) != FILES or manifest['new_labels_present'] is not False
            or manifest['purpose'] not in ('source_review', 'transport_canary')):
        raise ValueError('exact metadata-only source workspace required')
    visible = {name: read_pinned_json(root, name, sha) for name, sha in manifest['files'].items()}
    verify_context(visible['context.json'])
    if (visible['limits.json'] != LIMITS or visible['source-contract.json']['contract_sha256']
            != visible['context.json']['source_contract_sha256']):
        raise ValueError('source context or authority changed')
    catalog = visible['source-review-catalog.json']
    if (catalog.get('schema') != 'historical_public_source_review_catalog_v1'
            or catalog.get('source_selected') is not None
            or catalog.get('acquisition_authorized') is not False):
        raise ValueError('review catalog cannot select or authorize')
    return manifest, visible


def make_workspace(output, visible, session_id, purpose):
    identifier(session_id)
    if set(visible) != FILES or purpose not in ('source_review', 'transport_canary'):
        raise ValueError('exact visible files and purpose required')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name, value in visible.items():
        fresh_json(output / name, value)
    for kind in ('plans', 'metadata-requests', 'public-metadata'):
        (output / kind).mkdir()
    fresh_json(output / 'workspace.json', {'schema': 'historical_source_review_workspace_v1',
        'session_id': session_id, 'purpose': purpose, 'new_labels_present': False,
        'files': {n: file_hash(output / n) for n in visible}})
    expected = file_hash(output / 'workspace.json')
    validate_workspace(output, expected)
    return expected


def receipt_objects(receipts):
    objects = {}; source_ids = set()
    for receipt in receipts:
        if (receipt.get('schema') != 'public_source_directory_metadata_review_v1'
                or receipt.get('passed') is not True or receipt.get('acquisition_admitted') is not False
                or receipt.get('result_sha256') != digest({k:v for k,v in receipt.items() if k != 'result_sha256'})):
            raise ValueError('unchanged reviewed directory receipt required')
        source = receipt['dataset']; metadata_url(source, receipt['revision']); source_ids.add(source)
        for obj in receipt['objects']:
            if obj['type'] != 'file' or not obj['advertised_sha256']:
                continue
            key = (source, receipt['revision'], obj['path'])
            value = {'sha256': obj['advertised_sha256'], 'bytes': obj['advertised_bytes']}
            if key in objects and objects[key] != value:
                raise ValueError('conflicting source directory evidence')
            objects[key] = value
    return objects, source_ids


def validate_plan(plan, visible, receipts):
    if not isinstance(plan, dict) or set(plan) != PLAN_FIELDS:
        raise ValueError('exact source-plan fields required')
    identifier(plan['plan_id'])
    context = visible['context.json']; catalog = visible['source-review-catalog.json']
    if (plan['context_sha256'] != context['context_sha256']
            or plan['review_catalog_sha256'] != digest(catalog)
            or plan['stage'] not in ('source_compatibility_audit', 'new_data_stage')):
        raise ValueError('separate source stage and exact prior-context binding required')
    if (plan['artifact_use'] != 'opened_data_qa_train_only'
            or plan['quiet_rows'] != 'preserve_raw_no_future_filter'
            or plan['validation_claim'] != 'none'):
        raise ValueError('no fresh-test claim, raw deletion or future-value filter allowed')
    objects, discovered = receipt_objects(receipts)
    ids = {s['id'] for s in catalog['sources']} | discovered
    ids |= {s['source_id'] for s in visible['prior-source-catalog.json']['sources']}
    selected = texts(plan['source_ids'], 3)
    if not set(selected) <= ids or 'synthetic-market-simulator' in selected:
        raise ValueError('known real source required; request metadata for another source')
    requested = plan['objects']
    if not isinstance(requested, list) or len(requested) > 20:
        raise ValueError('bounded exact advertised object list required')
    payload = 0; seen = set()
    for item in requested:
        if not isinstance(item, dict) or set(item) != {'source_id', 'revision', 'path', 'sha256', 'bytes'}:
            raise ValueError('exact object descriptor required')
        key = (item['source_id'], item['revision'], item['path'])
        if (key in seen or item['source_id'] not in selected or key not in objects
                or type(item['bytes']) is not int or item['bytes'] <= 0
                or objects[key] != {'sha256': item['sha256'], 'bytes': item['bytes']}):
            raise ValueError('object must match independent advertised hash and bytes exactly')
        seen.add(key); payload += item['bytes']
    window = plan['requested_window']
    if (not isinstance(window, list) or len(window) != 2
            or any(not isinstance(d, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', d) for d in window)):
        raise ValueError('UTC date window required')
    first, last = map(date.fromisoformat, window)
    minimum = plan['minimum_complete_sessions']
    if type(minimum) is not int or minimum < context['minimum_final_utc_days'] or (last-first).days+1 < minimum:
        raise ValueError('requested calendar cannot accommodate minimum complete sessions')
    for field in ('question', 'clock_policy', 'gap_policy', 'coverage_policy'):
        bounded_text(plan[field])
    for field in ('source_contract_changes', 'required_streams', 'unresolved_questions'):
        texts(plan[field])
    mappings = plan['field_mapping']
    if not isinstance(mappings, list) or not 1 <= len(mappings) <= 100:
        raise ValueError('bounded explicit field mappings required')
    for mapping in mappings:
        if (not isinstance(mapping, dict) or set(mapping) != {'required_field', 'proposed_field',
                'availability_clock', 'status', 'evidence'} or mapping['status'] not in
                ('documented', 'requires_raw_check', 'unavailable')):
            raise ValueError('explicit documented/unchecked/unavailable field status required')
        for field in ('required_field', 'proposed_field', 'availability_clock', 'evidence'):
            bounded_text(mapping[field])
    if len({m['required_field'] for m in mappings}) != len(mappings):
        raise ValueError('duplicate required field mapping')
    return {'proposal_valid': True, 'proposal_sha256': digest(plan),
        'advertised_payload_bytes_not_authority': payload,
        'unlisted_transfer_bytes_estimated': False, 'payload_bound_is_not_total_wire_cost': True,
        'objects_require_additional_authority': payload > 0,
        'raw_compatibility_verified': False, 'source_contract_changed_by_submission': False,
        'fresh_dates_admitted': [], 'acquisition_admitted': False, 'execution_admitted': False}


def validate_request(request):
    if not isinstance(request, dict) or set(request) != REQUEST_FIELDS:
        raise ValueError('exact metadata request fields required')
    identifier(request['request_id']); bounded_text(request['source_name']); bounded_text(request['relevance'])
    texts(request['questions']); texts(request['public_metadata_urls'], 10)
    from urllib.parse import urlsplit
    for url in request['public_metadata_urls']:
        parts = urlsplit(url)
        if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
            raise ValueError('public HTTPS documentation reference required')
    return {'request_valid': True, 'automatic_fetch': False, 'acquisition_admitted': False,
            'execution_admitted': False}


class Broker:
    def __init__(self, root, manifest_sha256, directory_inspector=inspect_directory):
        self.root = Path(root); self.manifest_sha256 = manifest_sha256
        self.directory_inspector = directory_inspector
        validate_workspace(self.root, self.manifest_sha256)

    def _receipts(self, visible, events):
        receipts = list(visible['evidence.json']['directory_receipts'])
        for event in events:
            if event['tool'] == 'inspect_public_source_directory' and event['status'] == 'ok':
                result = event['result']; path = self.root / 'public-metadata' / result['inspection_id'] / 'result.json'
                actual = read_pinned_json(self.root, str(path.relative_to(self.root)), result['receipt_file_sha256'])
                if actual != result['receipt']:
                    raise ValueError('public source receipt changed after logged inspection')
                receipts.append(actual)
        return receipts

    def _claim(self, kind, item_id, body):
        identifier(item_id); directory = self.root / kind
        if directory.is_symlink():
            raise ValueError('output directory symlink forbidden')
        existing = list(directory.iterdir())
        if len(existing) >= 4 or any((p / 'result.json').exists() for p in existing):
            raise ValueError('one valid artifact per kind; failed claims bounded and retained')
        target = directory / item_id; target.mkdir(exist_ok=False)
        fresh_json(target / 'claim.json', {'body': body, 'body_sha256': digest(body)})
        return target

    def call(self, name, arguments):
        lock_fd = os.open(self.root / '.tool.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(lock_fd, 'a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            manifest, visible = validate_workspace(self.root, self.manifest_sha256)
            if (self.root / DECISION).exists():
                raise ValueError('decision submitted; no continuation or resampling')
            events = read_activity_events(self.root / LOG)
            if len(events) >= LIMITS['max_tool_calls'] or len(canonical(arguments).encode()) > 128000:
                raise ValueError('tool or argument budget exceeded')
            try:
                expected = next((t['inputSchema']['properties'] for t in TOOLS if t['name'] == name), None)
                if expected is None or not isinstance(arguments, dict) or set(arguments) != set(expected):
                    raise ValueError('unknown tool or unexpected arguments')
                result = self._call(name, arguments, manifest, visible, events)
            except Exception as error:
                append_activity(self.root / LOG, {'tool': name, 'arguments': arguments,
                    'status': 'error', 'error': str(error)})
                raise
            append_activity(self.root / LOG, {'tool': name, 'arguments': arguments,
                'status': 'ok', 'result': result})
            return result

    def _call(self, name, a, manifest, visible, events):
        if name == 'inspect_source_context':
            return {'context': visible['context.json'], 'old_source_contract': visible['source-contract.json'],
                'prior_sources': visible['prior-source-catalog.json'], 'new_source_notes': visible['source-review-catalog.json'],
                'review_catalog_sha256': digest(visible['source-review-catalog.json']),
                'plan_fields': sorted(PLAN_FIELDS), 'request_fields': sorted(REQUEST_FIELDS),
                'field_mapping_fields': ['required_field', 'proposed_field', 'availability_clock', 'status', 'evidence'],
                'stage_choices': ['source_compatibility_audit', 'new_data_stage'],
                'fixed_plan_values': {'artifact_use': 'opened_data_qa_train_only',
                    'quiet_rows': 'preserve_raw_no_future_filter', 'validation_claim': 'none'},
                'source_selected': False}
        if name == 'inspect_source_readiness':
            return {n: visible[n + '.json'] for n in ('readiness', 'evidence', 'limits')}
        if name == 'inspect_source_archive':
            return visible['archive.json']
        if name == 'search_source_notes':
            terms = set(bounded_text(a['query']).lower().split())
            entries = (visible['source-review-catalog.json']['sources']
                       + visible['prior-source-catalog.json']['sources'] + visible['literature.json']['papers'])
            return {'mode': 'frozen_metadata_notes_not_live_web', 'matches': sorted(entries,
                key=lambda entry: -sum(t in canonical(entry).lower() for t in terms))[:8]}
        if name == 'inspect_public_source_directory':
            if manifest['purpose'] != 'source_review':
                raise ValueError('real network unavailable in transport canary')
            metadata_url(a['dataset'], a['revision'])
            directory = self.root / 'public-metadata'
            if directory.is_symlink():
                raise ValueError('metadata output directory symlink forbidden')
            previous = list(directory.iterdir())
            if len(previous) >= LIMITS['max_public_metadata_calls']:
                raise ValueError('public metadata request budget exhausted')
            if any(e['tool'] == name and e['arguments'] == a for e in events):
                raise ValueError('same source revision already inspected or failed; no duplicate request')
            inspection_id = f'directory-{len(previous)+1:03d}'
            target = directory / inspection_id
            receipt = self.directory_inspector(a['dataset'], a['revision'], target)
            return {'inspection_id': inspection_id, 'receipt': receipt,
                'receipt_file_sha256': file_hash(target / 'result.json'), 'acquisition_admitted': False}
        if name in ('propose_source_plan', 'request_source_metadata'):
            is_plan = name == 'propose_source_plan'; body = a['plan' if is_plan else 'request']
            if not isinstance(body, dict):
                raise ValueError('artifact object required')
            target = self._claim('plans' if is_plan else 'metadata-requests',
                                 body.get('plan_id' if is_plan else 'request_id'), body)
            try:
                result = (validate_plan(body, visible, self._receipts(visible, events))
                          if is_plan else validate_request(body))
                result = {**result, 'body': body, 'claim_sha256': file_hash(target / 'claim.json')}
                fresh_json(target / 'result.json', result)
                return result
            except Exception as error:
                fresh_json(target / 'failure.json', {'error': str(error), 'retry_same_id': False})
                raise
        if name == 'submit_source_review_decision':
            required = {'inspect_source_context', 'inspect_source_readiness'}
            if not required <= {e['tool'] for e in events if e['status'] == 'ok'}:
                raise ValueError('inspect current context and readiness before decision')
            bounded_text(a['reason']); action = a['action']; artifact = a['artifact_id']
            record = None
            if action in ('propose', 'request_metadata'):
                identifier(artifact); kind = 'plans' if action == 'propose' else 'metadata-requests'
                directory = self.root / kind / artifact
                # The successful creation event supplies the commitment; it is not guessed from a mutable file.
                creator = 'propose_source_plan' if action == 'propose' else 'request_source_metadata'
                matched = [e['result'] for e in events if e['tool'] == creator and e['status'] == 'ok'
                           and e['result']['body'].get('plan_id' if action == 'propose' else 'request_id') == artifact]
                if len(matched) != 1:
                    raise ValueError('exact successful artifact creation required')
                record = matched[0]
                if (file_hash(directory / 'result.json') != hashlib_json(record)
                        or file_hash(directory / 'claim.json') != record['claim_sha256']):
                    raise ValueError('submitted artifact or claim changed')
                if action == 'propose':
                    validate_plan(record['body'], visible, self._receipts(visible, events))
                else:
                    validate_request(record['body'])
            elif action != 'defer' or artifact != '':
                raise ValueError('defer has no artifact; otherwise choose propose/request_metadata')
            decision = {**a, 'context_sha256': visible['context.json']['context_sha256'],
                'artifact_sha256': digest(record) if record else None, 'workspace_manifest_sha256': self.manifest_sha256,
                'workspace_purpose': manifest['purpose'], 'execution_admitted': False, 'acquisition_admitted': False}
            fresh_json(self.root / DECISION, decision)
            return {'submitted': True, 'bytes': (self.root / DECISION).stat().st_size,
                    'decision': decision, 'execution_admitted': False}
        raise ValueError('unknown source-review tool')


def hashlib_json(value):
    # Match fresh_json's on-disk format; semantic integrity is additionally in the activity chain.
    import hashlib
    return hashlib.sha256((canonical(value) + '\n').encode()).hexdigest()


def assess_activity(root, manifest_sha256):
    validate_workspace(root, manifest_sha256)
    summary = verify_activity_log(root / LOG); events = read_activity_events(root / LOG)
    terminal = [e for e in events if e['tool'] == 'submit_source_review_decision' and e['status'] == 'ok']
    if len(terminal) != 1 or events[-1] != terminal[0]:
        raise ValueError('one terminal decision at end of log required')
    decision = read_pinned_json(root, DECISION, hashlib_json(terminal[0]['result']['decision']))
    if decision['workspace_manifest_sha256'] != manifest_sha256:
        raise ValueError('terminal workspace mismatch')
    if decision['artifact_id']:
        kind = 'plans' if decision['action'] == 'propose' else 'metadata-requests'
        directory = root / kind / decision['artifact_id']
        creator = 'propose_source_plan' if kind == 'plans' else 'request_source_metadata'
        records = [e['result'] for e in events if e['tool'] == creator and e['status'] == 'ok']
        if len(records) != 1 or digest(records[0]) != decision['artifact_sha256']:
            raise ValueError('terminal creation digest mismatch')
        if (file_hash(directory / 'result.json') != hashlib_json(records[0])
                or file_hash(directory / 'claim.json') != records[0]['claim_sha256']):
            raise ValueError('terminal source proposal changed')
    return {'valid': True, 'log': summary, 'action': decision['action'],
            'model_authorship_proven': False, 'execution_admitted': False, 'acquisition_admitted': False}


def serve(broker):
    for line in sys.stdin:
        request = None
        try:
            if len(line.encode()) > 256000:
                raise ValueError('MCP request too large')
            request = json.loads(line)
            if not isinstance(request, dict) or 'id' not in request:
                continue
            method = request.get('method')
            if method == 'initialize':
                result = {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}},
                          'serverInfo': {'name': 'historical-source-review', 'version': '1'}}
            elif method == 'ping': result = {}
            elif method == 'tools/list': result = {'tools': TOOLS}
            elif method == 'tools/call':
                try:
                    p = request.get('params', {}); value = broker.call(p.get('name'), p.get('arguments', {}))
                    failed = False
                except Exception as error:
                    value = {'accepted': False, 'message': str(error)}; failed = True
                result = {'content': [{'type': 'text', 'text': canonical(value)}], 'isError': failed}
            else: raise ValueError('unsupported MCP method')
            response = {'jsonrpc': '2.0', 'id': request['id'], 'result': result}
        except Exception as error:
            if not isinstance(request, dict) or 'id' not in request: continue
            response = {'jsonrpc': '2.0', 'id': request['id'], 'error': {'code': -32602, 'message': str(error)}}
        print(canonical(response), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    a = parser.parse_args(); os.environ.clear()
    serve(Broker(a.workspace, a.manifest_sha256))
