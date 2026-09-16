"""Reconstruct a conservative exposure inventory from existing receipts only.

This is a retrospective audit, not a replacement for the original access logs.
Neither a missing access record nor runner-only QA admits a date as fresh Test.
No raw market files, prediction arrays or label arrays are opened.
"""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller_activity_log import read_activity_events, verify_activity_log
from market_rsi import canonical, digest, file_hash, fresh_json, load_json


def possible_utc_dates(lower_ms, upper_ms):
    """Inclusive clock bounds, never partition-name dates or observed-row proof."""
    if (type(lower_ms) is not int or type(upper_ms) is not int
            or lower_ms < 0 or upper_ms < lower_ms):
        raise ValueError('invalid receipt-clock interval')
    first = datetime.fromtimestamp(lower_ms / 1000, timezone.utc).date()
    last = datetime.fromtimestamp(upper_ms / 1000, timezone.utc).date()
    if (last - first).days > 366:
        raise ValueError('unexpectedly broad source interval')
    return [(first + timedelta(days=i)).isoformat()
            for i in range((last - first).days + 1)]


def summarize(calendar_dates, declared_open, selected_train, selected_check, scans):
    if len(calendar_dates) != len(set(calendar_dates)):
        raise ValueError('duplicate calendar dates')
    if set(selected_train) & set(selected_check):
        raise ValueError('selected fit/check dates overlap')
    known = set(declared_open) | set(selected_train) | set(selected_check)
    possible = {d for item in scans for d in item['possible_utc_dates']}
    return {
        'known_open_dates_lower_bound': sorted(known),
        'selected_fit_dates': sorted(selected_train),
        'selected_adaptively_inspected_check_dates': sorted(selected_check),
        'runner_full_scan_possible_dates': sorted(possible),
        'runner_scan_possible_dates_outside_selected_six': sorted(
            possible - set(selected_train) - set(selected_check)),
        'per_date': [{'utc_date': d,
                      'known_open_not_fresh': d in known,
                      'metadata_exposed_to_controller': True,
                      'runner_full_scan_possible': d in possible,
                      'fresh_holdout_admitted': False}
                     for d in sorted(set(calendar_dates) | known | possible)],
        'exposure_audit_complete': False,
        'fresh_holdout_dates_admitted': [],
        'limits': [
            'Metadata exposure is not evidence that the controller saw raw prices or labels.',
            'A full-file runner scan is not automatically controller label exposure.',
            'Clock-bound date unions are possible read scope, not exact per-row read dates.',
            'Legacy declared-open dates lack a complete reconstructed access history.',
            'This inventories named receipts, not every past process or human access.',
            'Unrecorded exposure is unknown, never proof of untouched holdout status.',
        ],
    }


def run(artifacts, output):
    if output.exists():
        raise ValueError('fresh exposure audit required')
    inputs = {}

    def read(relative):
        path = artifacts / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError('regular evidence file required')
        before = file_hash(path)
        obj = load_json(path)
        if file_hash(path) != before:
            raise ValueError('evidence changed during read')
        inputs[str(path.resolve())] = before
        return obj

    def mounted(workspace, name, manifest):
        obj = read(workspace + '/' + name)
        if manifest['files'][name] != inputs[str((artifacts / workspace / name).resolve())]:
            raise ValueError('frozen workspace evidence changed')
        return obj

    def activity(workspace, name):
        path = artifacts / workspace / name
        before = file_hash(path)
        verification = verify_activity_log(path)
        events = read_activity_events(path)
        if file_hash(path) != before:
            raise ValueError('activity changed during read')
        inputs[str(path.resolve())] = before
        return {'path': str(path.resolve()), 'verification': verification,
                'events': [{'tool': e.get('tool'), 'status': e.get('status')} for e in events]}

    data_ws = 'historical-data-use-controller-20260909-02/workspace'
    objective_ws = 'historical-grid-objective-controller-20260910-03/workspace'
    learning_ws = 'historical-grid-learning-controller-20260910-14/workspace'
    manifest = read(data_ws + '/workspace.json')
    calendar = mounted(data_ws, 'coverage-calendar.json', manifest)
    constraints = mounted(data_ws, 'constraints.json', manifest)
    data_activity = activity(data_ws, 'data-use-activity.jsonl')
    if not any(e == {'tool': 'inspect_coverage_calendar', 'status': 'ok'}
               for e in data_activity['events']):
        raise ValueError('no successful controller calendar inspection')

    material = 'historical-six-day-materialization-20260909-02'
    claim = read(material + '/claim.json')
    result = read(material + '/result.json')
    if not result['source_scan_complete'] or not result['full_six_day_dataset_built']:
        raise ValueError('materialization receipt incomplete')
    receipts = {item['path']: item for item in result['all_source_receipts']}
    if len(receipts) != len(result['all_source_receipts']):
        raise ValueError('duplicate source receipt')
    scans = []
    for entry in claim['selected_files']:
        item = entry['item']
        receipt = receipts[item['path']]
        if receipt['source_sha256'] != item['lfs_sha256']:
            raise ValueError('scanned source commitment mismatch')
        scans.append({'source_path': item['path'], 'source_sha256': item['lfs_sha256'],
                      'full_source_rows_scanned': receipt['full_source_rows_scanned'],
                      'possible_utc_dates': possible_utc_dates(
                          entry['min_possible_available_ms'], entry['max_possible_available_ms']),
                      'actor': 'trusted_materializer',
                      'controller_raw_or_label_access_proven': False})
    if set(receipts) != {s['source_path'] for s in scans}:
        raise ValueError('claimed and completed sources differ')

    selected = read(learning_ws + '/frozen-grid-learning-plan.json')
    decision = read(learning_ws + '/submitted-grid-learning-decision.json')
    if decision['action'] != 'select' or decision['trial_id'] != selected['trial_id']:
        raise ValueError('completed selection required')
    trials = []
    for path in sorted((artifacts / learning_ws / 'trials').glob('*/result.json')):
        trial = read(str(path.relative_to(artifacts)))
        plan = trial['plan']
        if (plan['train_utc_dates'] != selected['plan']['train_utc_dates']
                or plan['check_utc_dates'] != selected['plan']['check_utc_dates']):
            raise ValueError('unexpected trial split')
        trials.append({'trial_id': trial['trial_id'], 'result_sha256': trial['result_sha256']})
    plan = selected['plan']
    if set(result['controller_requested_utc_dates']) != set(
            plan['train_utc_dates'] + plan['check_utc_dates']):
        raise ValueError('selected split differs from opened materialization')
    audit = summarize([r['utc_date'] for r in calendar['dates']],
                      constraints['known_opened_dates_not_fresh_holdout'],
                      plan['train_utc_dates'], plan['check_utc_dates'], scans)
    audit.update({'schema': 'historical_retrospective_exposure_audit_v1',
                  'audit_time_utc': datetime.now(timezone.utc).isoformat(),
                  'retrospective_not_original_access_log': True,
                  'selected_trial_id': decision['trial_id'], 'prediction_trials': trials,
                  'source_scan_receipts': scans,
                  'controller_activity': [data_activity,
                      activity(objective_ws, 'objective-activity.jsonl'),
                      activity(learning_ws, 'learning-activity.jsonl')],
                  'new_raw_prices_or_labels_read': False,
                  'new_model_fits': 0, 'new_provider_calls': 0, 'new_downloads': 0,
                  'input_hashes': inputs, 'auditor_sha256': file_hash(Path(__file__))})
    for path, expected in inputs.items():
        if file_hash(Path(path)) != expected:
            raise ValueError('evidence changed before audit publication')
    audit['result_sha256'] = digest(audit)
    output.mkdir(parents=True, exist_ok=False)
    fresh_json(output / 'audit.json', audit)
    return audit


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(canonical(run(args.artifacts.resolve(), args.output.resolve())))
