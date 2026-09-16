"""Read-only explanations of an existing learning trial; never refit or select.

Missingness is measured for every declared feature. It is not repaired, and
no counterfactual score is assigned to removing a feature. All dates remain
already-open Train. Cosmetic alias hints never relax exact-profile checks.
"""
import numpy as np

from historical_recorded_features import derive
from market_rsi import digest


def without_names(value):
    if isinstance(value, dict):
        return {k: without_names(v) for k, v in value.items() if k != 'name'}
    if isinstance(value, list):
        return [without_names(v) for v in value]
    return value


def missing_profiles(features, profiles):
    exact = {digest(p['spec']) for p in profiles}
    missing = []
    for spec in features:
        if digest(spec) in exact:
            continue
        aliases = [{'query_id': p['query_id'], 'profiled_name': p['spec']['name'],
                    'profiled_spec_sha256': digest(p['spec'])}
                   for p in profiles if without_names(p['spec']) == without_names(spec)]
        missing.append({'feature_name': spec['name'], 'spec_sha256': digest(spec),
                        'same_formula_different_names': aliases})
    return missing


def plan_difference(parent, candidate):
    old = {f['name']: f for f in parent['features']}
    new = {f['name']: f for f in candidate['features']}
    return {
        'added_features': sorted(new.keys() - old.keys()),
        'removed_features': sorted(old.keys() - new.keys()),
        'changed_named_features': sorted(k for k in old.keys() & new.keys() if old[k] != new[k]),
        'feature_order_changed': [f['name'] for f in parent['features']] !=
                                 [f['name'] for f in candidate['features']],
        'changed_nonfeature_fields': sorted(k for k in candidate
            if k not in {'features', 'rationale'} and parent.get(k) != candidate[k]),
        'interpretation': 'A feature-stage comparison may add AND remove features. '
            'Do not attribute its score difference to just one addition unless the actual diff supports it.'}


def diagnose(inputs, trial, arrays, parent=None):
    x, y = inputs['x'], inputs['y']; plan = trial['plan']
    if not np.array_equal(arrays['row_id'], x['row_id']):
        raise ValueError('trial row identity changed')
    features = plan['features']
    finite = np.column_stack([np.isfinite(derive(x['entity'], x['decision_ms'], x['values'],
        inputs['names'], spec=f, cadence_ms=inputs['cadence_ms'],
        recorded_events=inputs.get('recorded_events'))['values']) for f in features])
    complete = np.all(finite, axis=1)
    check = np.isin(x['date'], plan['check_utc_dates'])
    if not np.array_equal(arrays['check'], check):
        raise ValueError('trial check population changed')
    supported = np.ones(len(check), dtype=bool) if plan['missing_input_action'] == 'native_nan' else complete
    if not np.array_equal(arrays['check_model_prediction'], check & supported):
        raise ValueError('saved support disagrees with declared missing-input handling')
    cutoff = int(np.datetime64(min(plan['check_utc_dates']), 'ms').astype(np.int64))
    eligible = np.isin(x['date'], plan['train_utc_dates']) & y['available']
    eligible &= (x['decision_ms'] < cutoff) & (y['label_available_ms'] < cutoff)
    eligible &= ~np.isin(x['market'], np.unique(x['market'][check]))
    if not np.array_equal(arrays['fit'], eligible & supported):
        raise ValueError('saved fit mask disagrees with causal eligibility')

    def population(mask):
        labelled = mask & y['available']; quiet = labelled & (y['delta_probability'] == 0)
        n = int(mask.sum()); labels = int(labelled.sum())
        return {'population_rows': n, 'labelled_rows': labels,
            'unlabelled_rows': n - labels, 'complete_input_rows': int((mask & complete).sum()),
            'missing_input_rows': int((mask & ~complete).sum()),
            'model_supported_rows': int((mask & supported).sum()),
            'persistence_fallback_rows': int((mask & ~supported).sum()),
            'labelled_fallback_rows': int((labelled & ~supported).sum()),
            'quiet_labelled_rows': int(quiet.sum()),
            'quiet_share_of_labelled_rows_equal_row': float(quiet.sum() / labels) if labels else None}

    per_feature = []
    for j, feature in enumerate(features):
        item = {'name': feature['name'], 'spec_sha256': digest(feature), 'populations': {}}
        for label, mask in [('causally_eligible_train', eligible), ('check_all', check),
                            ('check_labelled', check & y['available'])]:
            missing = mask & ~finite[:, j]
            only_missing = missing & (np.count_nonzero(~finite, axis=1) == 1)
            item['populations'][label] = {'rows': int(mask.sum()),
                'missing_rows': int(missing.sum()), 'only_this_feature_missing_rows': int(only_missing.sum())}
        per_feature.append(item)
    prediction = arrays['prediction_delta_probability']
    mid = x['values'][:, inputs['names'].index('polymarket_ticks_ms.midpoint_from_reported_bbo')]
    projected = check & np.isfinite(mid)
    at_bound = projected & ((prediction == -mid) | (prediction == 1 - mid))
    return {'schema': 'historical_learning_trial_explanation_v1', 'trial_id': trial['trial_id'],
        'trial_result_sha256': trial['result_sha256'],
        'parent_difference': plan_difference(parent['plan'], plan) if parent else None,
        'check': population(check), 'causally_eligible_train': population(eligible),
        'check_by_date': {d: population(check & (x['date'] == d)) for d in plan['check_utc_dates']},
        'per_feature': per_feature,
        'projection': {'declared_transform': plan['output_transform'],
            'saved_predictions_exactly_at_probability_bound': int(at_bound.sum()),
            'actual_clipped_rows': None,
            'reason': 'Pre-projection predictions were not saved. Bound hits alone cannot establish how many values changed.'},
        'fits': 0, 'new_provider_calls': 0, 'rows_removed': 0, 'source_values_imputed': False,
        'fresh_holdout': False,
        'limits': 'Missing counts overlap across features. only_this_feature_missing_rows is an availability count, '
            'NOT a score or recommendation to remove it. This explains existing artifacts, not the optimal model. '
            'A failed candidate does not falsify its entire feature family. Quiet fractions use explicit row denominators.'}
