"""Freeze a source-review workspace and run a read-only real-STDIO canary.

Only existing metadata and previously open research are copied. No original
market objects, model loading, public network calls or paid provider calls.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import controller_source_review as review
from controller_activity_log import read_activity_events, verify_activity_log
from data_source_catalog import data_source_catalog
from market_rsi import canonical, digest, file_hash, fresh_json, load_json
from paid_budget import PaidBudget
from proof_store import read_pinned_json


def checked_audit(path):
    audit = load_json(path)
    if audit.get('passed') is not True or audit.get('result_sha256') != digest(
            {k:v for k,v in audit.items() if k != 'result_sha256'}):
        raise ValueError('unchanged completed audit required')
    return audit


def prepare(output, purpose):
    if output.exists():
        raise ValueError('fresh permanent source-review ID required')
    old = ROOT / 'artifacts/historical-independent-validation-controller-20260910-01'
    prep = load_json(old / 'preparation.json')
    if (not (old / 'dispatch-claim.json').is_file()
            or load_json(old / 'session/assessment.json')['valid'] is not True):
        raise ValueError('completed claimed prior controller required')
    for name, expected in prep['source_hashes'].items():
        if file_hash(ROOT / name) != expected or file_hash(old / 'source-snapshot' / name) != expected:
            raise ValueError('prior frozen source changed')
    ws = old / 'workspace'
    old_manifest = read_pinned_json(ws, 'workspace.json', prep['workspace_sha256'])
    old_visible = {name: read_pinned_json(ws, name, sha) for name, sha in old_manifest['files'].items()}
    catalog_path = ROOT / 'artifacts/historical-source-review-20260910-01/catalog.json'
    receipt_path = ROOT / 'artifacts/historical-public-source-metadata-20260910-01/result.json'
    audit_path = ROOT / 'artifacts/historical-independent-validation-result-audit-20260910-01/audit.json'
    feasibility_path = ROOT / 'artifacts/historical-source-request-feasibility-20260910-01/audit.json'
    transfer_path = ROOT / 'artifacts/historical-transfer-accounting-20260910-01/audit.json'
    catalog = load_json(catalog_path); receipt = checked_audit(receipt_path)
    audit = checked_audit(audit_path); feasibility = checked_audit(feasibility_path)
    transfer = checked_audit(transfer_path)
    if file_hash(receipt_path.parent / 'response.body.json') != receipt['response_body_sha256']:
        raise ValueError('public metadata response changed')
    if receipt['inspector_sha256'] != file_hash(ROOT / 'audit_tools/public_source_metadata.py'):
        raise ValueError('public metadata inspector changed from receipt')
    source = next((s for s in catalog['sources'] if s['id'] == receipt['dataset']), None)
    if (source is None or source['file_metadata_result_sha256'] != receipt['result_sha256']
            or source['observed_revision'] != receipt['revision']):
        raise ValueError('review catalog/remote directory receipt mismatch')
    known, _ = review.receipt_objects([receipt])
    for item in source['advertised_objects']:
        key = (source['id'], source['observed_revision'], item['path'])
        if known[key] != {'bytes': item['bytes'], 'sha256': item['sha256']}:
            raise ValueError('review catalog advertised object changed')
    decision_path = ws / 'submitted-validation-decision.json'; decision = load_json(decision_path)
    if file_hash(decision_path) != audit['decision_sha256'] or audit['session_id'] != old.name:
        raise ValueError('prior terminal decision/audit mismatch')
    request_path = ws / 'data-requests' / decision['artifact_id'] / 'result.json'
    request = load_json(request_path)
    if digest(request) != decision['artifact_sha256'] or file_hash(request_path) != feasibility['request_result_sha256']:
        raise ValueError('prior missing-data request binding mismatch')
    budget_path = ROOT / 'artifacts/kalshi-research-glm53-20260907-01/budget'
    budget = PaidBudget(budget_path).snapshot(); context = old_visible['context.json']
    if (file_hash(budget_path / 'authorization.json') != context['budget_authorization_sha256']
            or budget['cap_usd'] != context['budget_cap_usd']
            or budget['experiment_id'] != context['experiment_id']):
        raise ValueError('original experiment budget identity changed')
    if any(v['state'] == 'dispatched' and '-turn-' in k for k,v in budget['jobs'].items()):
        raise ValueError('another model turn is active; do not prepare duplicate work')
    visible = {'context.json': context, 'source-contract.json': old_visible['source-contract.json'],
        'archive.json': {'all_prior_open_research': old_visible['archive.json'],
            'prior_validation_design': {'decision': decision, 'data_request': request,
                'independent_audit': {k:v for k,v in audit.items() if k not in ('inputs', 'budget_snapshot')}},
            'controller_prose_is_not_independent_evidence': True},
        'source-review-catalog.json': catalog, 'prior-source-catalog.json': data_source_catalog(),
        'literature.json': old_visible['literature.json'], 'limits.json': review.LIMITS,
        'evidence.json': {'directory_receipts': [receipt], 'cached_feasibility_audit': feasibility,
            'prior_exposure_audit': old_visible['exposure.json'],
            'retained_coverage_audit': old_visible['inventory.json'],
            'catalog_notes_are_assistant_reviewed_publisher_claims_not_raw_qa': True},
        'readiness.json': {
            'compatible_untouched_sessions_admitted': 0,
            'old_validation_adapter_canary_completed_before_prior_model_call': True,
            'source_review_runtime_canary_receipts_must_be_supplied_by_dispatcher': True,
            'prior_readiness_snapshot_is_historical_not_current_transport_status': True,
            'source_changes_are_possible_only_as_separate_proposals_not_t7_test': True,
            'budget_snapshot_not_spend': {k:v for k,v in budget.items() if k != 'jobs'},
            'transfer_accounting': transfer, 'authorized_raw_download_headroom_bytes': 0,
            'no_training_or_evaluation_tools': True,
            'metadata_only_network_maximum': {'calls': 4, 'bytes_per_call': 524288},
            'source_catalog_not_exhaustive_or_a_winner': True}}
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    paths = [catalog_path, receipt_path, receipt_path.parent / 'response.body.json', audit_path,
        feasibility_path, transfer_path, decision_path, request_path, old / 'preparation.json',
        old / 'dispatch-claim.json', old / 'session/assessment.json', budget_path / 'authorization.json']
    sources = list(ROOT.glob('*.py'))
    sources += [p for p in (ROOT / 'validation_tools').glob('*.py') if not p.name.startswith('test_')]
    sources += [ROOT / 'audit_tools/public_source_metadata.py']
    sources += [p for p in (ROOT / 'source_review_tools').glob('*.py') if not p.name.startswith('test_')]
    hashes = {}
    for source_path in sorted(sources):
        name = str(source_path.relative_to(ROOT)); hashes[name] = file_hash(source_path)
        target = output / 'source-snapshot' / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target)
        if file_hash(target) != hashes[name]: raise ValueError('source copy changed')
    manifest_sha = review.make_workspace(output / 'workspace', visible, output.name, purpose)
    result = {'schema': 'historical_source_review_preparation_v1', 'purpose': purpose,
        'old_session_id': old.name, 'old_source_files_preserved': len(prep['source_hashes']),
        'source_hashes': hashes, 'workspace_sha256': manifest_sha, 'context_sha256': context['context_sha256'],
        'inputs': {str(p.resolve()): file_hash(p) for p in paths},
        'new_model_calls': 0, 'new_raw_download_bytes': 0, 'new_public_metadata_calls': 0,
        'execution_admitted': False, 'paid_dispatch_ready': False,
        'model_authorship_proven': False, 'source_selected': False}
    for name, expected in hashes.items():
        if file_hash(ROOT / name) != expected: raise ValueError('source changed during preparation')
    fresh_json(output / 'preparation.json', result)
    return result


def canary(prepared):
    prep = load_json(prepared / 'preparation.json')
    if prep['purpose'] != 'transport_canary' or (prepared / 'transport-canary-claim.json').exists():
        raise ValueError('fresh transport-only canary required')
    for name, expected in prep['source_hashes'].items():
        if file_hash(ROOT / name) != expected or file_hash(prepared / 'source-snapshot' / name) != expected:
            raise ValueError('canary source differs from frozen source')
    ws = prepared / 'workspace'; review.validate_workspace(ws, prep['workspace_sha256'])
    fresh_json(prepared / 'transport-canary-claim.json', {'preparation_sha256': file_hash(prepared / 'preparation.json'),
        'scope': 'real stdio, existing metadata only, no terminal scientific decision'})
    requests = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'},
                {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}]
    for i, name in enumerate(('inspect_source_context', 'inspect_source_readiness', 'inspect_source_archive'), 3):
        requests.append({'jsonrpc': '2.0', 'id': i, 'method': 'tools/call', 'params': {'name': name, 'arguments': {}}})
    try:
        p = subprocess.run([sys.executable, str(prepared / 'source-snapshot/source_review_tools/controller_source_review.py'),
            '--workspace', str(ws), '--manifest-sha256', prep['workspace_sha256']],
            input=''.join(canonical(r)+'\n' for r in requests), text=True, capture_output=True, timeout=30)
        if p.returncode: raise ValueError('stdio canary failed: ' + p.stderr[-2000:])
        responses = [json.loads(line) for line in p.stdout.splitlines()]
        if (len(responses) != 5 or responses[1]['result']['tools'] != review.TOOLS
                or any(r.get('error') or r['result'].get('isError') for r in responses)):
            raise ValueError('real stdio tool inventory or calls failed')
        served = json.loads(responses[2]['result']['content'][0]['text'])
        if served['context']['context_sha256'] != prep['context_sha256']:
            raise ValueError('served wrong old-model context')
        if ((ws / review.DECISION).exists() or any(list((ws / k).iterdir())
                for k in ('plans', 'metadata-requests', 'public-metadata'))):
            raise ValueError('read-only canary unexpectedly proposed or accessed network')
        review.validate_workspace(ws, prep['workspace_sha256'])
        events = read_activity_events(ws / review.LOG)
        if len(events) != 3: raise ValueError('unexpected canary activity')
        result = {'schema': 'historical_source_review_stdio_canary_v1', 'passed': True,
            'actual_stdio_child': True, 'transport_calls': 5, 'actual_tools': 3,
            'source_files_verified': len(prep['source_hashes']), 'context_sha256': prep['context_sha256'],
            'preparation_sha256': file_hash(prepared / 'preparation.json'),
            'activity': verify_activity_log(ws / review.LOG), 'new_model_calls': 0,
            'new_public_metadata_calls': 0, 'new_raw_download_bytes': 0, 'new_fits': 0,
            'new_test': False, 'model_authorship_proven': False, 'execution_admitted': False,
            'paid_dispatch_ready': False}
        result['result_sha256'] = digest(result); fresh_json(prepared / 'transport-canary.json', result)
        return result
    except Exception as error:
        fresh_json(prepared / 'transport-canary-failure.json', {'error': str(error), 'retry_same_id': False})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    p = sub.add_parser('prepare'); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--purpose', choices=['source_review', 'transport_canary'], required=True)
    c = sub.add_parser('canary'); c.add_argument('--prepared', type=Path, required=True)
    a = parser.parse_args()
    result = prepare(a.output.resolve(), a.purpose) if a.operation == 'prepare' else canary(a.prepared.resolve())
    print(canonical({k:v for k,v in result.items() if k not in ('source_hashes', 'inputs')}))
