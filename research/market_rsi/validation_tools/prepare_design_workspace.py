"""Prepare/check real metadata tools, without launching a paid controller."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller_design import TOOLS, FILES, make_workspace, validate_workspace
from controller_activity_log import read_activity_events, verify_activity_log
from independent_validation import verify_context
from market_rsi import canonical, digest, file_hash, fresh_json, load_json


def prepare(root, frozen_context, session, output, *, purpose):
    if output.exists():
        raise ValueError('fresh permanent validation design preparation required')
    context = load_json(frozen_context / 'context.json'); verify_context(context)
    bindings = load_json(frozen_context / 'input-bindings.json')
    if digest(bindings) != context['input_bindings_sha256']:
        raise ValueError('validation context bindings changed')
    for path, expected in bindings.items():
        if file_hash(Path(path)) != expected:
            raise ValueError('frozen selected context evidence changed')
    readiness = load_json(frozen_context / 'readiness.json')
    if readiness['context_sha256'] != context['context_sha256']:
        raise ValueError('context readiness mismatch')
    for name, expected in readiness['source_hashes'].items():
        if file_hash(root / 'validation_tools' / name) != expected:
            raise ValueError('frozen validation checker changed')
    if session.name != context['source_session_id']:
        raise ValueError('wrong selected controller session')
    reconstruction = root / 'artifacts/historical-selected-candidate-reconstruction-20260910-01'
    source_ws = root / 'artifacts/historical-data-use-controller-20260909-02/workspace'
    audit_path = root / 'artifacts/historical-grid-learning-result-audit-20260910-08/audit.json'
    audit = load_json(audit_path)
    if (audit['session_id'] != session.name or audit['passed'] is not True
            or audit['decision']['trial_id'] != context['selected_trial_id']
            or audit['result_sha256'] != digest({k: v for k, v in audit.items() if k != 'result_sha256'})
            or file_hash(audit_path) != load_json(reconstruction / 'claim.json')['prior_audit_sha256']):
        raise ValueError('selected diagnostic archive audit mismatch')
    old = session / 'workspace'
    old_manifest = load_json(old / 'workspace.json')
    for name in ('archive.json', 'literature.json'):
        if file_hash(old / name) != old_manifest['files'][name]:
            raise ValueError('old controller archive changed')
    paths = {
        'source-contract.json': source_ws / 'source-contract.json',
        'selected-plan.json': reconstruction / 'selected-plan.json',
        'inventory.json': root / 'artifacts/historical-validation-inventory-20260910-01/audit.json',
        'exposure.json': root / 'artifacts/historical-exposure-audit-20260910-01/audit.json',
        'literature.json': old / 'literature.json',
    }
    visible = {name: load_json(path) for name, path in paths.items()}
    visible.update({'context.json': context, 'readiness.json': readiness,
        'archive.json': {'prior_controller_archive': load_json(old / 'archive.json'),
            'selected_controller_audit': {k: v for k, v in audit.items() if k != 'budget_snapshot'},
            'all_check_dates_already_open_train': True,
            'controller_prose_is_not_independent_evidence': True},
        'limits.json': {'max_tool_calls': 32, 'max_successful_plans': 1,
            'max_successful_data_requests': 1, 'max_claims_per_kind': 4,
            'authorized_download_headroom_bytes': 0, 'vendor_purchase_authorized': False,
            'execution_tools_present': False}})
    assert set(visible) == FILES
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    sources = list(root.glob('*.py')) + [p for p in (root / 'validation_tools').glob('*.py')
                                       if not p.name.startswith('test_')]
    hashes = {}
    for source in sorted(sources):
        name = str(source.relative_to(root))
        hashes[name] = file_hash(source)
        target = output / 'source-snapshot' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if file_hash(target) != hashes[name]:
            raise ValueError('source snapshot copy mismatch')
    make_workspace(output / 'workspace', visible, output.name, purpose)
    result = {'schema': 'historical_validation_design_preparation_v1', 'purpose': purpose,
              'source_session_id': session.name, 'context_sha256': context['context_sha256'],
              'context_file_sha256': file_hash(frozen_context / 'context.json'),
              'workspace_sha256': file_hash(output / 'workspace/workspace.json'),
              'source_hashes': hashes, 'new_controller_call': False,
              'model_authorship_proven': False, 'new_data_read': False,
              'new_downloads': 0, 'new_fits': 0, 'execution_admitted': False,
              'dispatcher_source_present': 'validation_tools/run_validation_design.py' in hashes,
              'paid_dispatch_preflight_passed': False,
              'source_inputs': {str(p.resolve()): file_hash(p) for p in paths.values()}}
    for source, expected in hashes.items():
        if file_hash(root / source) != expected:
            raise ValueError('source changed during workspace preparation')
    fresh_json(output / 'preparation.json', result)
    return result


def canary(prepared):
    preparation = load_json(prepared / 'preparation.json')
    if preparation['purpose'] != 'transport_canary' or (prepared / 'transport-canary.json').exists():
        raise ValueError('fresh, explicitly canary-only prepared workspace required')
    workspace = prepared / 'workspace'
    if file_hash(workspace / 'workspace.json') != preparation['workspace_sha256']:
        raise ValueError('workspace commitment changed')
    validate_workspace(workspace)
    for name, expected in preparation['source_hashes'].items():
        if file_hash(prepared / 'source-snapshot' / name) != expected:
            raise ValueError('source snapshot changed')
    requests = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'},
                {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}]
    for index, name in enumerate(('inspect_validation_context', 'inspect_validation_readiness',
                                  'inspect_validation_archive'), 3):
        requests.append({'jsonrpc': '2.0', 'id': index, 'method': 'tools/call',
                         'params': {'name': name, 'arguments': {}}})
    child = subprocess.run([sys.executable, str(prepared / 'source-snapshot/validation_tools/controller_design.py'),
                            '--workspace', str(workspace)],
                           input=''.join(canonical(r) + '\n' for r in requests),
                           text=True, capture_output=True, timeout=30)
    if child.returncode:
        raise ValueError('real stdio child failed: ' + child.stderr[-1000:])
    responses = [json.loads(line) for line in child.stdout.splitlines()]
    if len(responses) != len(requests) or responses[1]['result']['tools'] != TOOLS:
        raise ValueError('real transport tool inventory mismatch')
    if any(r.get('error') or r['result'].get('isError') for r in responses):
        raise ValueError('transport tool call failed')
    seen_context = json.loads(responses[2]['result']['content'][0]['text'])['context']
    if seen_context['context_sha256'] != preparation['context_sha256']:
        raise ValueError('served selected context changed')
    if (list((workspace / 'plans').iterdir()) or list((workspace / 'data-requests').iterdir())
            or (workspace / 'submitted-validation-decision.json').exists()):
        raise ValueError('read-only canary unexpectedly proposed or decided')
    validate_workspace(workspace)
    log = verify_activity_log(workspace / 'validation-design-activity.jsonl')
    if len(read_activity_events(workspace / 'validation-design-activity.jsonl')) != 3:
        raise ValueError('canary activity count mismatch')
    result = {'schema': 'historical_validation_design_stdio_canary_v1', 'passed': True,
              'real_stdio_child': True, 'transport_calls': 5, 'actual_tool_calls': 3,
              'activity': log, 'context_sha256': preparation['context_sha256'],
              'source_files_verified': len(preparation['source_hashes']),
              'source_preparation_sha256': file_hash(prepared / 'preparation.json'),
              'actual_codex_glm_provider_call': False, 'new_controller_calls': 0,
              'new_scientific_decision': False, 'new_market_prices_or_labels_read': False,
              'new_fits': 0, 'new_downloads': 0, 'execution_admitted': False}
    result['result_sha256'] = digest(result)
    fresh_json(prepared / 'transport-canary.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    prepare_parser = sub.add_parser('prepare')
    for name in ('root', 'frozen-context', 'session', 'output'):
        prepare_parser.add_argument('--' + name, type=Path, required=True)
    prepare_parser.add_argument('--purpose', choices=('controller_design', 'transport_canary'), required=True)
    canary_parser = sub.add_parser('canary'); canary_parser.add_argument('--prepared', type=Path, required=True)
    args = vars(parser.parse_args()); operation = args.pop('operation')
    args = {k: v.resolve() if isinstance(v, Path) else v for k, v in args.items()}
    print(canonical(prepare(**args) if operation == 'prepare' else canary(**args)))
