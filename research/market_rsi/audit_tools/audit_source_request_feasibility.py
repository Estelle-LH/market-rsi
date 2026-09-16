"""Offline feasibility audit of a request against already-cached source metadata.

Partition names are not event dates. This never downloads, reads Parquet, assigns
splits, or proves source-clock coverage/untouchedness. No authority is added.
"""
import argparse
from collections import defaultdict
from datetime import date
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from market_rsi import canonical, digest, file_hash, fresh_json, load_json


def require(value, message):
    if not value:
        raise ValueError(message)


def summarize_inventory(inventory, request):
    require(inventory.get('schema') == 'openmarket_frozen_partition_inventory_v1', 'inventory schema')
    require(inventory['inventory_sha256'] == digest({k:v for k,v in inventory.items()
                                                   if k != 'inventory_sha256'}), 'inventory hash')
    first, last = date.fromisoformat(request['earliest_utc_date']), date.fromisoformat(request['latest_utc_date'])
    require(first <= last, 'request window')
    tables = defaultdict(lambda: {'objects': 0, 'advertised_bytes': 0, 'partition_dates': set(),
                                 'requested_window_objects': [], 'undated_objects': 0})
    seen = set()
    for item in inventory['files']:
        name = item['path']; path = Path(name)
        require(name.startswith('unified/') and not path.is_absolute() and '..' not in path.parts,
                'relative unified object path required')
        require(name not in seen, 'duplicate inventory path'); seen.add(name)
        require(type(item['bytes']) is int and item['bytes'] >= 0, 'advertised object bytes')
        table = path.parts[1]; result = tables[table]
        result['objects'] += 1; result['advertised_bytes'] += item['bytes']
        match = re.search(r'/date=(\d{4}-\d{2}-\d{2})/', name)
        if match:
            day = date.fromisoformat(match.group(1)); result['partition_dates'].add(day.isoformat())
            if first <= day <= last:
                result['requested_window_objects'].append(name)
        else:
            result['undated_objects'] += 1
    report = {}
    for name, data in sorted(tables.items()):
        days = sorted(data.pop('partition_dates'))
        report[name] = {**data, 'advertised_partition_date_count': len(days),
                       'earliest_advertised_partition': days[0] if days else None,
                       'latest_advertised_partition': days[-1] if days else None}
    return {'dataset': inventory['dataset'], 'revision': inventory['revision'],
        'cached_unified_objects': len(seen),
        'all_advertised_unified_bytes_not_downloaded': sum(t['advertised_bytes'] for t in report.values()),
        'request_window': [first.isoformat(), last.isoformat()], 'tables': report,
        'advertised_objects_in_requested_window': sum(len(t['requested_window_objects']) for t in report.values()),
        'remote_revision_requeried': False, 'inventory_pagination_receipts_independently_verified': False,
        'event_time_coverage_from_partition_names': False, 'freshness_proven': False,
        'acquisition_admitted': False, 'new_downloads': 0, 'new_price_or_label_reads': False,
        'interpretation': 'No matching cached partition is not a proof that an older-named file contains '
            'no later events, nor proof about another dataset revision. It provides no executable '
            'acquisition plan for this request; raising the download cap alone does not establish feasibility.'}


def run(session, inventories, output):
    require(not output.exists(), 'fresh audit output required')
    assessment = load_json(session / 'session/assessment.json')
    require(assessment['valid'] is True and assessment['process_reaped'] is True, 'completed controller required')
    decision = load_json(session / 'workspace/submitted-validation-decision.json')
    require(decision['action'] == 'defer' and decision['artifact_id'], 'exact terminal missing-data request required')
    record_path = session / 'workspace/data-requests' / decision['artifact_id'] / 'result.json'
    record = load_json(record_path)
    require(digest(record) == decision['artifact_sha256'], 'request decision binding')
    require(record['download_authorized'] is False and record['execution_admitted'] is False, 'request not authority')
    request = record['body']; inputs = {}
    lists = []
    for path in inventories:
        inventory = load_json(path)
        lists.append(inventory)
        summarize_inventory(inventory, request)
        inputs[str(path)] = file_hash(path)
    require(bool(lists), 'cached inventory required')
    expected = lists[0]
    require(all((i['dataset'],i['revision'],digest(i['files'])) ==
                (expected['dataset'],expected['revision'],digest(expected['files'])) for i in lists),
            'cached inventories disagree; do not select one')
    source = load_json(session / 'workspace/source-contract.json')
    # This audit is for the active, exact source request, not source replacement.
    require(expected['dataset'] == 'gregyoung14/openmarket-btc-polymarket'
            and expected['revision'] == '74502466d1a7cef56395bfd8d0b465fbebc849cf'
            and request['source_contract_sha256'] == source['contract_sha256'], 'pinned request/source mismatch')
    result = summarize_inventory(expected, request)
    result.update({'schema': 'historical_cached_source_request_feasibility_v1',
        'passed': True, 'request_id': request['request_id'], 'matching_inventory_copies': len(lists),
        'cached_file_list_sha256': digest(expected['files']), 'inputs': inputs,
        'request_result_sha256': file_hash(record_path),
        'advertised_download_ceiling_not_authorized': request['max_new_download_bytes'],
        'audit_scope': 'Existing unified-object inventory only; no source acquisition or evaluation.',
        'source_collector_sha256': file_hash(ROOT / 'openmarket_partition_canary.py'),
        'source_collector_behavior': 'fetch_inventory exhausts recursive pinned list_repo_tree and retains '
            'unified/ entries with nonnegative integer sizes; no raw HTTP pagination receipt was saved.',
        'auditor_sha256': file_hash(Path(__file__))})
    result['result_sha256'] = digest(result)
    output.mkdir(parents=True, exist_ok=False); fresh_json(output / 'audit.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    result = run(a.session.resolve(), [p.resolve() for p in a.inventory], a.output.resolve())
    print(canonical(result))
