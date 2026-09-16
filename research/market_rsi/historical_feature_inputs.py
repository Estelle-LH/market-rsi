"""Project previously audited current observations into an unlabelled input cache.

All source fields remain available to the researcher; this is not a selected
model feature set. No lag lengths, normalization, fit, weights or splits are
chosen. Unavailable values remain NaN, with explicit causal state indicators.
"""
import argparse
from collections import Counter
import fcntl
import math
from pathlib import Path

import numpy as np

from historical_grid_objective_controller import read_panel
from historical_grid_panel import bounded_rows
from historical_ingest_controller import _signed
from historical_phase_annotations import annotate
from historical_source_contract import CANDLE_MS
from market_rsi import canonical, digest, file_hash, fresh_json, identifier, load_json
from materialize_selected_grid_objective import write_archive


STATE_FIELDS = ('value_present', 'stale', 'ambiguous_same_receipt', 'missing', 'invalid_source')


def source_fields(stream):
    if stream == 'polymarket_ticks_ms':
        return ('reported_bid', 'reported_ask', 'midpoint_from_reported_bbo')
    if stream == 'binance_trades':
        return ('trade_price', 'trade_quantity')
    if stream in CANDLE_MS:
        return ('open_price', 'high_price', 'low_price', 'close_price')
    raise ValueError('source fields not implemented; no alias or fabricated depth/flow')


def input_names(plan):
    streams = ['polymarket_ticks_ms', *plan['context_streams']]
    if len(set(streams)) != len(streams):
        raise ValueError('distinct selected source streams required')
    names = ['nominal_offset_seconds', 'pm_recorded_events_since_previous_grid_tick',
             'quiet_since_previous_grid_tick']
    names += ['phase.' + p for p in ['before_nominal_window', 'within_nominal_window', 'after_nominal_window']]
    names += ['polymarket_ticks_ms.spread', 'polymarket_ticks_ms.spread_squared']
    for stream in streams:
        names += [stream + '.' + f for f in source_fields(stream)]
        names += [stream + '.' + f for f in ['arrival_age_ms', 'source_event_age_ms', *STATE_FIELDS]]
    return sorted(names)


def current_inputs(row, annotation, plan):
    """No future rows/labels accepted by this API; derived quantities are current."""
    if row.get('target') is not None or row.get('training_admitted') is not False:
        raise ValueError('unlabelled diagnostic observation required')
    expected_id = digest({k: row[k] for k in ['market_slug', 'asset_id', 'decision_ms']})
    if row['row_id'] != expected_id or annotation != annotate(row):
        raise ValueError('exact original row/annotation identity required')
    when = row['decision_ms']
    if type(when) is not int or when < 0:
        raise ValueError('integer recorded observation clock required')
    expected_streams = {'polymarket_ticks_ms', *plan['context_streams']}
    if set(row['observations']) != expected_streams:
        raise ValueError('only the exact controller-selected streams may enter input cache')
    result = {name: np.nan for name in input_names(plan)}
    result['nominal_offset_seconds'] = annotation['nominal_offset_seconds']
    result['pm_recorded_events_since_previous_grid_tick'] = annotation['pm_recorded_events_since_previous_grid_tick']
    result['quiet_since_previous_grid_tick'] = int(annotation['quiet_since_previous_grid_tick'])
    for phase in ['before_nominal_window', 'within_nominal_window', 'after_nominal_window']:
        result['phase.' + phase] = int(annotation['nominal_phase'] == phase)
    for stream, observation in row['observations'].items():
        state = annotation['observation_states'][stream]
        for key in STATE_FIELDS:
            result[stream + '.' + key] = int(state[key])
        values = observation['values']
        if not values:
            if observation['reason'] == 'recorded_source_only_not_execution_proof':
                raise ValueError('available source cannot omit all values')
            continue
        if (observation['reason'] != 'recorded_source_only_not_execution_proof'
                or set(values) != set(source_fields(stream))):
            raise ValueError('exact admitted current source fields required')
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values.values()):
            raise ValueError('finite current source values required')
        arrival = observation.get('available_ms')
        age = observation.get('max_source_age_ms')
        if (type(arrival) is not int or arrival < 0 or arrival > when
                or type(age) is not int or age < 0
                or max(when - arrival, age) > plan['max_age_ms']):
            raise ValueError('future or stale source cannot supply an input value')
        if stream == 'polymarket_ticks_ms':
            bid, ask, mid = [values[f] for f in source_fields(stream)]
            if not 0 <= bid <= ask <= 1 or not math.isclose(mid, (bid + ask) / 2, rel_tol=0, abs_tol=1e-12):
                raise ValueError('co-reported valid probability BBO required')
            result[stream + '.spread'] = ask - bid
            result[stream + '.spread_squared'] = (ask - bid)**2
        elif stream == 'binance_trades':
            if values['trade_price'] <= 0 or values['trade_quantity'] < 0:
                raise ValueError('positive trade price and nonnegative quantity required')
        else:
            o, h, low, c = [values[f] for f in source_fields(stream)]
            if not 0 < low <= min(o, c) <= max(o, c) <= h:
                raise ValueError('valid observed final candle OHLC required')
        for field, value in values.items():
            result[stream + '.' + field] = float(value)
        result[stream + '.arrival_age_ms'] = when - arrival
        result[stream + '.source_event_age_ms'] = age
    return result


def project_rows(rows, annotations, plan, panel, row_ids):
    names = input_names(plan)
    n = len(row_ids)
    matrix = np.full((n, len(names)), np.nan)
    count = 0
    reasons = Counter()
    for i, (row, side) in enumerate(zip(rows, annotations, strict=True)):
        if i >= n:
            raise ValueError('extra source row; never truncate')
        if row['row_id'] != row_ids[i] or row['decision_ms'] != int(panel.time_ms[i]):
            raise ValueError('feature cache must preserve exact unlabelled panel order')
        value = current_inputs(row, side, plan)
        mid = value['polymarket_ticks_ms.midpoint_from_reported_bbo']
        if not (mid == panel.midpoint[i] or (np.isnan(mid) and np.isnan(panel.midpoint[i]))):
            raise ValueError('feature midpoint and target-anchor panel disagree')
        matrix[i] = [value[name] for name in names]
        for stream, observation in row['observations'].items():
            reasons[stream + ':' + observation['reason']] += 1
        count = i + 1
    if count != n:
        raise ValueError('incomplete input projection; no partial population accepted')
    return matrix, names, dict(reasons)


def run(controller, materialized, annotations, output):
    identifier(output.name)
    workspace = controller / 'workspace'
    panel, ids, panel_result = read_panel(workspace)
    selected = load_json(workspace / 'data-use-proposal.json'); _signed(selected, 'proposal_sha256')
    material = load_json(materialized / 'result.json'); _signed(material, 'result_sha256')
    side = load_json(annotations / 'result.json'); _signed(side, 'result_sha256')
    rows_path = materialized / 'diagnostic-states.jsonl.gz'
    annotation_path = annotations / 'annotations.jsonl.gz'
    if (material.get('source_scan_complete') is not True or side.get('complete') is not True
            or file_hash(rows_path) != material['rows_sha256']
            or file_hash(annotation_path) != side['annotation_rows_sha256']
            or side['original_observations_sha256'] != material['rows_sha256']
            or side['row_count'] != len(ids) or material['row_count'] != len(ids)
            or side['proposal_sha256'] != selected['proposal_sha256']
            or file_hash(annotations / 'result.json') != panel_result['input_hashes']['annotations']
            or file_hash(workspace / 'data-use-proposal.json') != panel_result['input_hashes']['proposal']):
        raise ValueError('completed matching audited observations and controller-selected panel required')
    paths = [rows_path, annotation_path, annotations / 'result.json', materialized / 'result.json',
             workspace / 'unlabelled-grid.npz', workspace / 'panel-result.json',
             workspace / 'data-use-proposal.json']
    hashes = {str(p.resolve()): file_hash(p) for p in paths}
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    source_root = Path(__file__).resolve().parent
    modules = ['historical_feature_inputs.py', 'historical_phase_annotations.py',
               'historical_grid_panel.py', 'historical_grid_objective_controller.py',
               'materialize_selected_grid_objective.py']
    code = {name: file_hash(source_root / name) for name in modules}
    fresh_json(output / 'claim.json', {'schema': 'historical_current_input_projection_claim_v1',
        'input_hashes': hashes, 'code_hashes': code, 'panel_sha256': panel_result['panel_sha256'],
        'data_use_proposal_sha256': selected['proposal_sha256'],
        'new_scientific_feature_selection': False, 'new_paid_or_download_calls': 0})
    try:
        values, names, reasons = project_rows(bounded_rows(rows_path, 1500000000),
            bounded_rows(annotation_path, 750000000), selected['plan'], panel, ids)
        arrays = {'row_id': ids, 'entity': panel.entity, 'decision_ms': panel.time_ms,
                  'date': panel.date, 'field_names': np.array(names), 'values': values}
        path = output / 'current-inputs.npz'
        write_archive(path, arrays)
        with np.load(path, allow_pickle=False) as saved:
            if set(saved.files) != set(arrays):
                raise ValueError('input cache schema changed')
            for name, original in arrays.items():
                np.testing.assert_array_equal(saved[name], original)
        if hashes != {str(p.resolve()): file_hash(p) for p in paths}:
            raise ValueError('source inputs changed during projection')
        if code != {name: file_hash(source_root / name) for name in modules}:
            raise ValueError('projection source changed while executing')
        result = {'schema': 'historical_current_input_cache_v1', 'complete': True,
            'claim_sha256': file_hash(output / 'claim.json'), 'panel_sha256': panel_result['panel_sha256'],
            'archive_sha256': file_hash(path), 'stored_bytes': path.stat().st_size,
            'rows': len(ids), 'field_names': names,
            'finite_rows_per_field': {name: int(np.isfinite(values[:, i]).sum()) for i, name in enumerate(names)},
            'source_reason_counts': reasons, 'all_rows_retained_in_original_order': True,
            'labels_present': False, 'selected_model_features': False, 'training_admitted': False,
            'fresh_holdout': False, 'new_paid_or_download_calls': 0,
            'limitations': ['Current cached fields are not a selected model feature set.',
                'No bid/ask sizes, signed trade-flow or book-delta history is fabricated.',
                'Nominal contract clock is not verified settlement.',
                'Binance trade_price is a last recorded trade, not executable BBO.',
                'Missing values remain NaN; missingness indicators do not fill prices.',
                'Researcher must explicitly choose formulas/windows, normalization, Train use and model.']}
        result['result_sha256'] = digest(result); fresh_json(output / 'result.json', result)
        return result
    except Exception as exc:
        fresh_json(output / 'failure.json', {'error_type': type(exc).__name__, 'error': str(exc), 'complete': False})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['controller', 'materialized', 'annotations', 'output']:
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    with (Path(__file__).parent / 'artifacts/historical-ingest-controller.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = run(**vars(args))
    print(canonical({k: result[k] for k in ['complete', 'rows', 'stored_bytes', 'result_sha256', 'labels_present']}))
