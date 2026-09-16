"""Mechanics-only real-byte window canary; no labels, fitting or feature selection."""
import argparse
import fcntl
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from historical_trade_windows import RecordedTradeWindows, SOURCE, STATISTICS, load_audited_index
from market_rsi import canonical, digest, file_hash, fresh_json, load_json


def direct(a, dates, decision, spec):
    """Independent small-window slices and sums, no prefix implementation reuse."""
    start = decision-spec['window_ms']
    t = a['received_ms']
    lo, hi = np.searchsorted(t, [start, decision], side='right')
    times = t[lo:hi]
    days = set(dates)
    start_day, end_day = start//86_400_000, decision//86_400_000
    if any(str(np.datetime64(day, 'D')) not in days for day in range(start_day, end_day+1)):
        return np.nan, 1, len(times)
    begin = start_day
    while str(np.datetime64(begin-1, 'D')) in days:
        begin -= 1
    first = np.searchsorted(t, begin*86_400_000)
    if first >= len(t) or start < int(t[first]):
        return np.nan, 2, len(times)
    if len(times) < spec['minimum_records']:
        return np.nan, 3, len(times)
    gaps = np.diff(np.r_[start, times, decision])
    if np.any(gaps > spec['maximum_recorded_gap_ms']):
        return np.nan, 4, len(times)
    q, v, m = (a[k][lo:hi] for k in ('quantity', 'reported_quote_volume', 'reported_maker'))
    if (np.any(a['quality_bits'][lo:hi]) or np.any(a['event_ms'][lo:hi] > times)
            or np.any(~np.isfinite(q) | (q < 0) | ~np.isfinite(v) | (v < 0) | ~np.isin(m, [0, 1]))):
        return np.nan, 5, len(times)
    quantity = np.sum(q, dtype=np.longdouble)
    amount = np.sum(v, dtype=np.longdouble)
    signed_q = np.sum(q[m == 0], dtype=np.longdouble)-np.sum(q[m == 1], dtype=np.longdouble)
    signed_v = np.sum(v[m == 0], dtype=np.longdouble)-np.sum(v[m == 1], dtype=np.longdouble)
    kind = spec['statistic']
    if kind == 'record_count': value = len(times)
    elif kind == 'quantity_sum': value = quantity
    elif kind == 'quote_volume_sum': value = amount
    elif kind == 'maker0_minus_maker1_quantity': value = signed_q
    elif kind == 'maker0_minus_maker1_quote_volume': value = signed_v
    else:
        denominator = amount if kind == 'maker_quote_volume_imbalance' else quantity
        if denominator <= 0: return np.nan, 6, len(times)
        numerator = amount if kind == 'recorded_vwap' else signed_v if kind == 'maker_quote_volume_imbalance' else signed_q
        value = numerator/denominator
    return float(value), 0, len(times)


def run(index, audit, input_cache, output):
    root = Path(__file__).resolve().parents[1]
    with (root/'artifacts/historical-ingest-controller.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = load_json(input_cache/'result.json')
        if (result['result_sha256'] != digest({k: v for k, v in result.items() if k != 'result_sha256'})
                or file_hash(input_cache/'current-inputs.npz') != result['archive_sha256']):
            raise ValueError('existing current-input cache changed')
        arrays, dates, binding = load_audited_index(index, audit)
        hashes = {str(p): file_hash(p) for p in (Path(__file__), root/'historical_trade_windows.py',
                  root/'market_rsi.py', index/'result.json', index/'events.npz', audit,
                  input_cache/'result.json', input_cache/'current-inputs.npz')}
        with np.load(input_cache/'current-inputs.npz', allow_pickle=False) as data:
            decision = data['decision_ms']
        population_rows = len(decision)
        selected = []
        for day in dates:
            begin = int(np.datetime64(day, 'ms').astype(np.int64))
            available = np.unique(decision[(decision >= begin) & (decision < begin+86_400_000)])
            if not len(available): raise ValueError('missing original opened-day decisions')
            selected.extend(available[[0, len(available)//3, 2*len(available)//3, -1]].tolist())
        selected = np.array(sorted(set(selected)), dtype=np.int64)
        # Two predeclared interface test windows, ALL supported statistics. No score,
        # target or feature preference enters this selection. Not controller choices.
        specs = [{'name': 'mechanics-'+stat+'-'+str(w), 'source': SOURCE, 'statistic': stat,
                  'window_ms': w, 'minimum_records': 1, 'maximum_recorded_gap_ms': w}
                 for w in (60_000, 300_000) for stat in sorted(STATISTICS)]
        output.mkdir(parents=True, exist_ok=False)
        fresh_json(output/'claim.json', {'schema': 'recorded_trade_window_canary_claim_v1',
            'bindings': binding, 'input_hashes': hashes, 'decision_ms': selected.tolist(), 'specs': specs,
            'selection': 'first, one-third, two-thirds, last existing decision per opened day, no target inspection',
            'researcher_feature_selected': False, 'mechanical_parameters_only': True,
            'labels_read': False, 'provider_calls': 0, 'fits': 0, 'new_downloads': 0})
        try:
            engine = RecordedTradeWindows(arrays, dates)
            comparisons = []
            for spec in specs:
                got = engine.derive(selected, spec=spec)
                errors = []
                for j, point in enumerate(selected):
                    value, reason, count = direct(arrays, dates, int(point), spec)
                    if int(got['reason'][j]) != reason or int(got['observations_used'][j]) != count:
                        raise ValueError('independent receipt/count/gap/quality gate mismatch')
                    if reason:
                        if not np.isnan(got['values'][j]): raise ValueError('unknown window filled')
                    elif not np.isclose(got['values'][j], value, rtol=1e-9, atol=1e-8):
                        raise ValueError('prefix aggregate differs from independent direct-window sum')
                    else: errors.append(abs(float(got['values'][j])-value))
                comparisons.append({'spec': spec, 'windows_checked': len(selected),
                    'available_windows': int(got['available'].sum()),
                    'reason_counts': {name: int(np.count_nonzero(got['reason'] == code)) for name, code in got['reason_codes'].items()},
                    'max_abs_prefix_vs_direct_error': max(errors) if errors else None})
            if any(file_hash(Path(p)) != h for p, h in hashes.items()):
                raise ValueError('source or code changed during canary')
            report = {'schema': 'recorded_trade_window_real_canary_v1', 'passed': True,
                'claim_sha256': file_hash(output/'claim.json'), 'bindings': binding,
                'original_population_rows': population_rows,
                'distinct_existing_decisions': len(selected), 'specifications_tested': len(specs),
                'independent_window_comparisons': len(selected)*len(specs), 'comparisons': comparisons,
                'raw_or_old_inputs_modified': False, 'labels_read': False, 'features_selected_for_learning': False,
                'fits': 0, 'provider_calls': 0, 'new_downloads': 0, 'training_admitted': False,
                'connected_to_controller': False,
                'boundary': 'Interface correctness on already-open bytes only, not evidence of predictive value or full exchange coverage.'}
            report['result_sha256'] = digest(report)
            fresh_json(output/'result.json', report)
            return report
        except Exception as error:
            fresh_json(output/'failure.json', {'type': type(error).__name__, 'error': str(error), 'no_automatic_retry': True})
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('index', 'audit', 'input-cache', 'output'):
        parser.add_argument('--'+name, required=True, type=Path)
    report = run(**{k: v.resolve() for k, v in vars(parser.parse_args()).items()})
    print(canonical({k: report[k] for k in ('passed', 'independent_window_comparisons', 'result_sha256')}))
