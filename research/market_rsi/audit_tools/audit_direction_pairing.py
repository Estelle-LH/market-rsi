"""Read-only paired-token cancellation diagnostic on already-open Train.

This measures row structure, not a fitted feature or a proposed trading rule.
No rows are deleted, labels changed, model refitted, or new holdout opened.
"""
import argparse
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from historical_grid_learning import read_inputs
from market_rsi import canonical, digest, file_hash, fresh_json, load_json


def inspect_pairs(x, y, names):
    keys = np.rec.fromarrays([x['market'], x['decision_ms']], names=['market', 'decision'])
    _, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
    order = np.argsort(inverse, kind='stable')
    starts = np.r_[0, np.cumsum(counts)[:-1]]
    pair_starts = starts[counts == 2]
    a, b = order[pair_starts], order[pair_starts + 1]
    both = y['available'][a] & y['available'][b]
    aa, bb = a[both], b[both]
    target = y['delta_probability']
    pair_sum = target[aa] + target[bb]
    fields = {}
    for j, name in enumerate(names):
        value = x['values'][:, j]
        finite = np.isfinite(value[a]) & np.isfinite(value[b])
        shared = finite & (value[a] == value[b])
        m = shared & both
        left, right = a[m], b[m]
        moment = value[left] * target[left] + value[right] * target[right]
        fields[name] = {
            'both_finite_pairs': int(finite.sum()),
            'exactly_equal_value_pairs': int(shared.sum()),
            'shared_value_and_both_labels_pairs': int(m.sum()),
            'absolute_sum_of_pair_feature_target_products': float(np.abs(moment).sum()),
            'max_abs_pair_feature_target_product_sum': float(np.max(np.abs(moment))) if len(moment) else None,
        }
    by_date = {}
    for date in sorted(set(x['date'])):
        m = x['date'][aa] == date
        sums = pair_sum[m]
        by_date[str(date)] = {
            'both_label_pairs': int(m.sum()),
            'exact_opposite_label_pairs': int(np.count_nonzero(sums == 0)),
            'max_abs_pair_label_sum': float(np.max(np.abs(sums))) if len(sums) else None,
        }
    role = {}
    for name in names:
        if name.endswith(('publisher_up_token', 'publisher_down_token')):
            v = x['values'][:, names.index(name)]
            m = np.isfinite(v[a]) & np.isfinite(v[b])
            role[name] = {'both_finite_pairs': int(m.sum()),
                          'opposite_0_1_pairs': int(np.count_nonzero(v[a[m]] + v[b[m]] == 1))}
    return {
        'population_rows': len(x['row_id']), 'market_timestamp_groups': len(counts),
        'group_size_counts': {str(n): int(np.count_nonzero(counts == n)) for n in np.unique(counts)},
        'two_row_groups': len(a), 'two_distinct_entities': int(np.count_nonzero(x['entity'][a] != x['entity'][b])),
        'both_labels_pairs': int(both.sum()),
        'one_label_only_pairs': int(np.count_nonzero(y['available'][a] ^ y['available'][b])),
        'both_missing_label_pairs': int(np.count_nonzero(~y['available'][a] & ~y['available'][b])),
        'exact_opposite_label_pairs': int(np.count_nonzero(pair_sum == 0)),
        'max_abs_pair_label_sum': float(np.max(np.abs(pair_sum))) if len(pair_sum) else None,
        'both_zero_label_pairs_retained': int(np.count_nonzero((target[aa] == 0) & (target[bb] == 0))),
        'nonzero_label_pairs': int(np.count_nonzero((target[aa] != 0) | (target[bb] != 0))),
        'field_pairing': fields, 'recorded_token_role_pairing': role, 'by_date': by_date,
    }


def run(session, output):
    assessment = load_json(session / 'session/assessment.json')
    if not assessment['valid'] or not assessment['process_reaped'] or output.exists():
        raise ValueError('completed session and fresh audit output required')
    workspace = session / 'workspace'
    paths = [workspace / n for n in ('current-inputs.npz', 'primary-labels.npz', 'panel-result.json')]
    before = {str(p): file_hash(p) for p in paths}
    inputs = read_inputs(workspace)
    report = inspect_pairs(inputs['x'], inputs['y'], inputs['names'])
    if before != {str(p): file_hash(p) for p in paths}:
        raise ValueError('frozen inputs changed during diagnostic')
    result = {
        'schema': 'historical_open_train_pairing_audit_v1', 'session_id': session.name,
        'assessment_sha256': file_hash(session / 'session/assessment.json'),
        'input_hashes': before, 'pairing': report, 'fits': 0, 'provider_calls': 0,
        'rows_removed': 0, 'labels_changed': False, 'fresh_holdout_opened': False,
        'interpretation_boundary': 'A shared feature times equal-and-opposite paired labels cancels algebraically. '
            'A pooled near-zero linear moment alone cannot establish absence of role-conditioned or nonlinear information. '
            'This audit does not select a replacement feature, target, model or sample mask.',
        'auditor_sha256': file_hash(Path(__file__)),
    }
    result['result_sha256'] = digest(result)
    output.mkdir(parents=True, exist_ok=False)
    fresh_json(output / 'audit.json', result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = run(args.session.resolve(), args.output.resolve())
    print(canonical({k: result[k] for k in ('session_id', 'result_sha256', 'fits', 'provider_calls')}))
